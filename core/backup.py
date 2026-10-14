"""Backup module: scans the source folder and creates a new timestamped version.

How a backup works
1. Walk the source directory tree and collect regular files (skip symlinks and
   excluded patterns such as .DS_Store).
2. For each file, compute its SHA-256 checksum. If size and modification time
   match the previous backup, reuse the stored checksum instead of re-reading
   the file (the same quick check rsync uses).
3. Incremental mode: if the file is identical to the previous version, create a
   HARD LINK to the copy already in the previous backup instead of copying it
   again. Every version still looks like a complete folder, but unchanged files
   use no extra disk space (the idea behind macOS Time Machine).
   Full mode: always copy every file.
4. Write everything into a hidden ".inprogress_<name>" folder, then rename it to
   its final name in one step. A crash never leaves a half-finished backup that
   looks complete.
5. Delete the oldest versions beyond the retention limit and log the result.
"""

import fnmatch
import json
import os
import shutil
import time
from datetime import datetime

from .utils import (
    IN_PROGRESS_PREFIX,
    MANIFEST_NAME,
    BackupError,
    is_inside,
    log_event,
    now_stamp,
    sha256_of,
)
from .versioning import (
    clean_incomplete,
    latest_backup,
    load_manifest,
    prune_old_backups,
    resolve_name,
)

DEFAULT_EXCLUDES = [".DS_Store", "Thumbs.db", "*.tmp", "~$*"]


def _is_excluded(rel_path, patterns):
    name = os.path.basename(rel_path)
    return any(fnmatch.fnmatch(name, p) or fnmatch.fnmatch(rel_path, p) for p in patterns)


def scan_source(source, excludes=None):
    """Return (files, skipped): relative paths of files to back up and those skipped."""
    excludes = DEFAULT_EXCLUDES if excludes is None else excludes
    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames.sort()
        for fname in sorted(filenames):
            full = os.path.join(dirpath, fname)
            rel = os.path.relpath(full, source)
            if _is_excluded(rel.replace(os.sep, "/"), excludes):
                skipped.append({"file": rel, "reason": "excluded"})
            elif os.path.islink(full):
                skipped.append({"file": rel, "reason": "symbolic link"})
            else:
                files.append(rel)
    return files, skipped


def _unique_name(backup_root):
    base = now_stamp()
    name, n = base, 2
    while (os.path.exists(os.path.join(backup_root, name))
           or os.path.exists(os.path.join(backup_root, IN_PROGRESS_PREFIX + name))):
        name = f"{base}-{n}"
        n += 1
    return name


def create_backup(source, backup_root, keep=3, mode="incremental", excludes=None):
    """Back up `source` into a new version inside `backup_root`. Returns a summary dict."""
    source = os.path.abspath(source)
    backup_root = os.path.abspath(backup_root)

    if not os.path.isdir(source):
        raise BackupError(f"Source folder not found: {source}")
    if is_inside(backup_root, source):
        raise BackupError("The backup location cannot be inside the folder being backed up")
    if mode not in ("full", "incremental"):
        raise BackupError("Mode must be 'full' or 'incremental'")
    if keep is not None and keep < 1:
        raise BackupError("Number of versions to keep must be at least 1")

    os.makedirs(backup_root, exist_ok=True)
    clean_incomplete(backup_root)
    start = time.perf_counter()

    # Find the previous version of this same source folder (for incremental linking).
    prev_name, prev_files = None, {}
    if mode == "incremental":
        candidate = latest_backup(backup_root)
        if candidate:
            prev_manifest = load_manifest(backup_root, candidate)
            if prev_manifest.get("source") == source:
                prev_name, prev_files = candidate, prev_manifest["files"]

    name = _unique_name(backup_root)
    work_dir = os.path.join(backup_root, IN_PROGRESS_PREFIX + name)
    os.makedirs(work_dir)

    files, skipped = scan_source(source, excludes)
    manifest_files, errors = {}, []
    stats = {"copied": 0, "linked": 0, "bytes_copied": 0, "bytes_linked": 0}

    for rel in files:
        key = rel.replace(os.sep, "/")
        src = os.path.join(source, rel)
        dst = os.path.join(work_dir, rel)
        try:
            st = os.stat(src)
            old = prev_files.get(key)
            if old and old["size"] == st.st_size and old["mtime"] == st.st_mtime:
                digest = old["sha256"]          # unchanged: skip re-reading the file
            else:
                digest = sha256_of(src)

            os.makedirs(os.path.dirname(dst), exist_ok=True)
            stored = "copied"
            if old and old["sha256"] == digest:
                try:
                    os.link(os.path.join(backup_root, prev_name, rel), dst)
                    stored = "linked"
                except OSError:
                    pass                         # e.g. file system without hard links: fall back to copy
            if stored == "copied":
                shutil.copy2(src, dst)           # copy2 keeps timestamps and permission bits

            stats[stored] += 1
            stats["bytes_" + stored] += st.st_size
            manifest_files[key] = {
                "size": st.st_size,
                "mtime": st.st_mtime,
                "sha256": digest,
                "stored": stored,
            }
        except OSError as exc:                   # unreadable file, vanished mid-backup, disk full...
            errors.append({"file": key, "error": str(exc)})

    stats["files"] = len(manifest_files)
    stats["skipped"] = len(skipped)
    stats["errors"] = len(errors)
    stats["seconds"] = round(time.perf_counter() - start, 4)

    manifest = {
        "name": name,
        "created": datetime.now().isoformat(timespec="microseconds"),
        "source": source,
        "mode": mode,
        "based_on": prev_name,
        "files": manifest_files,
        "skipped": skipped,
        "errors": errors,
        "stats": stats,
    }
    with open(os.path.join(work_dir, MANIFEST_NAME), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    final_dir = os.path.join(backup_root, name)
    os.rename(work_dir, final_dir)               # atomic: the version appears all at once

    pruned = prune_old_backups(backup_root, keep)
    log_event(backup_root,
              f"BACKUP {name} mode={mode} files={stats['files']} copied={stats['copied']} "
              f"linked={stats['linked']} errors={stats['errors']} time={stats['seconds']}s")

    return {"name": name, "path": final_dir, "based_on": prev_name, "stats": stats,
            "skipped": skipped, "errors": errors, "pruned": pruned}


def changes_since_backup(source, backup_root, name=None, excludes=None):
    """Compare the source folder with a backup: which files were added, modified or deleted."""
    source = os.path.abspath(source)
    backup_root = os.path.abspath(backup_root)
    if not os.path.isdir(source):
        raise BackupError(f"Source folder not found: {source}")
    name = resolve_name(backup_root, name)
    old = load_manifest(backup_root, name)["files"]

    files, _ = scan_source(source, excludes)
    current = {rel.replace(os.sep, "/") for rel in files}

    added = sorted(current - old.keys())
    deleted = sorted(old.keys() - current)
    modified = []
    for key in sorted(current & old.keys()):
        path = os.path.join(source, *key.split("/"))
        st = os.stat(path)
        info = old[key]
        if st.st_size != info["size"]:
            modified.append(key)
        elif st.st_mtime != info["mtime"] and sha256_of(path) != info["sha256"]:
            modified.append(key)
    return {"backup": name, "added": added, "modified": modified, "deleted": deleted}
