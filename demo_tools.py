"""Demo tools: change files and damage backups on purpose, then show how the tool reacts.

Each function does one thing a real user, a failing disk, a crash or an attacker might
do, and returns a short report that says what happened and what to try next. The GUI's
Test Lab tab calls these; the real backup code in core/ never does.

  edit_source_file / delete_source_file / add_source_file  -> try Show Changes, Backup, Restore
  corrupt_backup_file / delete_backup_file                 -> try Verify
  simulate_crash                                           -> try Create Backup (cleans it up)
  path_traversal_attack                                    -> runs the attack, shows it is blocked
  hard_link_report                                         -> inode + link count in every version
"""

import json
import os
import shutil
import tempfile
from datetime import datetime

from core import BackupError, restore_backup
from core.backup import scan_source
from core.utils import IN_PROGRESS_PREFIX, MANIFEST_NAME, now_stamp, safe_join, sha256_of
from core.versioning import list_backups, load_manifest, resolve_name


# ---------------------------------------------------------------- helpers

def source_files(source):
    """Files in the source folder that a backup would include (relative, '/'-separated)."""
    if not source or not os.path.isdir(source):
        return []
    files, _ = scan_source(source)
    return [f.replace(os.sep, "/") for f in files]


def _require_in_latest_backup(source, backup_root, rel):
    """Only touch source files that are safely backed up, so the demo can always restore them.

    Returns (latest version name, full path of the file in the source folder)."""
    name = resolve_name(backup_root, None)
    if rel not in load_manifest(backup_root, name)["files"]:
        raise BackupError(f"'{rel}' is not in the latest backup ({name}). "
                          f"Create a backup first so it can be restored.")
    path = safe_join(source, rel)
    if not os.path.isfile(path):
        raise BackupError(f"'{rel}' is not in your folder any more.")
    return name, path


def _stored_path(backup_root, name, rel):
    name = resolve_name(backup_root, name)
    path = safe_join(os.path.join(backup_root, name), rel)
    if rel not in load_manifest(backup_root, name)["files"] or not os.path.isfile(path):
        raise BackupError(f"'{rel}' is not stored in version {name}.")
    return name, path


def _versions_sharing(backup_root, rel, path):
    """Names of the versions whose copy of `rel` is the same inode as `path` (hard links)."""
    st = os.stat(path)
    sharing = []
    for b in list_backups(backup_root):
        other = os.path.join(backup_root, b["name"], *rel.split("/"))
        if os.path.isfile(other):
            ost = os.stat(other)
            if (ost.st_dev, ost.st_ino) == (st.st_dev, st.st_ino):
                sharing.append(b["name"])
    return sharing


# ---------------------------------------------------------------- 1. change the source folder

def edit_source_file(source, backup_root, rel):
    name, path = _require_in_latest_backup(source, backup_root, rel)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\nEdited by the Test Lab at {datetime.now():%H:%M:%S}\n")
    return (f"✔ Edited {rel} in your folder (added one line).\n"
            f"  Its size and modified time changed, so it no longer matches backup {name}.\n"
            f"  Next: Show Changes Since Last Backup (Backup tab) lists it as modified,\n"
            f"        and Create Backup copies only this file and hard-links the rest.")


def delete_source_file(source, backup_root, rel):
    name, path = _require_in_latest_backup(source, backup_root, rel)
    os.remove(path)
    return (f"✔ Deleted {rel} from your folder (an \"accidental\" delete).\n"
            f"  It is still stored in backup {name}.\n"
            f"  Next: Versions & Restore tab, type {rel} in \"Only this file or folder\",\n"
            f"        click Restore. Show Changes also lists it as deleted.")


def add_source_file(source):
    if not os.path.isdir(source):
        raise BackupError(f"Source folder not found: {source}")
    rel = f"new_file_{now_stamp()}.txt"
    with open(os.path.join(source, rel), "w", encoding="utf-8") as fh:
        fh.write("A brand-new file created by the Test Lab.\n")
    return (f"✔ Created {rel} in your folder.\n"
            f"  Next: Show Changes lists it as added; Create Backup copies it (it is new).")


# ---------------------------------------------------------------- 2. damage a backup

def corrupt_backup_file(backup_root, name, rel):
    """Flip one byte in the middle of a stored file: same size, different content (bit rot)."""
    name, path = _stored_path(backup_root, name, rel)
    sharing = _versions_sharing(backup_root, rel, path)
    size = os.path.getsize(path)
    with open(path, "r+b") as fh:
        if size == 0:
            fh.write(b"\x00")
        else:
            fh.seek(size // 2)
            byte = fh.read(1)
            fh.seek(size // 2)
            fh.write(bytes([byte[0] ^ 0xFF]))
    lines = [f"✔ Corrupted {rel} inside backup {name}: flipped 1 byte at position {size // 2}.",
             f"  The size is still {size} bytes, so only the SHA-256 checksum can notice."]
    if len(sharing) > 1:
        lines.append(f"  This copy is a hard link shared by {len(sharing)} versions ({', '.join(sharing)}).")
        lines.append("  They all point to the same data on disk, so ALL of them are now damaged.")
    lines.append("  Next: Versions & Restore tab, select a version and click Verify Selected.")
    lines.append("  To repair: Create Backup with \"Full backup\" ticked (copies everything fresh).")
    return "\n".join(lines)


def delete_backup_file(backup_root, name, rel):
    name, path = _stored_path(backup_root, name, rel)
    sharing = [n for n in _versions_sharing(backup_root, rel, path) if n != name]
    os.remove(path)
    lines = [f"✔ Deleted {rel} from inside backup {name} (the manifest still lists it)."]
    if sharing:
        links = os.stat(os.path.join(backup_root, sharing[0], *rel.split("/"))).st_nlink
        lines.append(f"  Only this version's name for the data was removed. Versions {', '.join(sharing)} "
                     f"still have it (link count now {links}), because data is freed only at link count 0.")
    lines.append(f"  Next: select {name} in Versions & Restore and click Verify Selected: it reports MISSING.")
    return "\n".join(lines)


def simulate_crash(backup_root):
    """Leave a half-written backup behind, as if the power failed in the middle of a backup."""
    os.makedirs(backup_root, exist_ok=True)
    work = os.path.join(backup_root, f"{IN_PROGRESS_PREFIX}{now_stamp()}_crashed")
    os.makedirs(os.path.join(work, "Documents"))
    with open(os.path.join(work, "Documents", "half_copied_file.txt"), "w", encoding="utf-8") as fh:
        fh.write("This file was only half cop")
    return (f"✔ Simulated a crash: left {os.path.basename(work)} in the backup folder,\n"
            f"  with a half-copied file and no manifest.json (the backup never finished).\n"
            f"  It does NOT appear in the versions list, because only finished backups count.\n"
            f"  Next: Create Backup. It deletes the leftover first; the Log tab shows a CLEANUP line.")


def path_traversal_attack(backup_root, name):
    """Plant '../../evil_demo.txt' in a manifest, try to restore it, then undo the change."""
    name = resolve_name(backup_root, name)
    manifest_path = os.path.join(backup_root, name, MANIFEST_NAME)
    with open(manifest_path, "rb") as fh:
        original = fh.read()
    manifest = json.loads(original)
    if not manifest["files"]:
        raise BackupError(f"Version {name} has no files to use for the attack.")
    evil = "../../evil_demo.txt"
    manifest["files"][evil] = next(iter(manifest["files"].values()))
    target = tempfile.mkdtemp(prefix="restore_target_")
    escaped = os.path.normpath(os.path.join(target, evil))
    try:
        with open(manifest_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, indent=2)
        result = restore_backup(backup_root, name, target=target, only=evil)
    finally:
        with open(manifest_path, "wb") as fh:          # always put the real manifest back
            fh.write(original)
        shutil.rmtree(target, ignore_errors=True)
    blocked = not os.path.exists(escaped)
    failed = result["failed"][0]["error"] if result["failed"] else "restored (NOT blocked!)"
    return "\n".join([
        f"Path-traversal attack on backup {name}:",
        f"  1. Planted a fake entry \"{evil}\" in its manifest.json.",
        f"     \"..\" means \"go up a folder\", so a careless restore would write it OUTSIDE",
        f"     the restore folder, at {escaped}",
        f"  2. Ran Restore on it -> {failed}",
        f"  3. Checked {escaped}: {'not created' if blocked else 'CREATED'}",
        f"  4. Put the original manifest.json back.",
        f"{'✔ Attack blocked' if blocked else '✘ Attack NOT blocked'} by safe_join() in core/utils.py.",
    ])


# ---------------------------------------------------------------- 3. look inside

def hard_link_report(backup_root, rel):
    """Show, for every version, which inode stores `rel` and how many names point to it."""
    if not rel or rel.endswith("/"):
        raise BackupError("Choose a file (not a folder) to inspect.")
    backups = list_backups(backup_root)
    if not backups:
        raise BackupError(f"No backups found in {backup_root}")
    rows, inodes = [], set()
    for b in backups:
        info = load_manifest(backup_root, b["name"])["files"].get(rel)
        path = safe_join(os.path.join(backup_root, b["name"]), rel)
        if info is None:
            rows.append((b["name"], "-", "-", "-", "not in this version"))
        elif not os.path.isfile(path):
            rows.append((b["name"], "-", "-", info.get("stored", "?"), "MISSING"))
        else:
            st = os.stat(path)
            inodes.add((st.st_dev, st.st_ino))
            check = "OK" if sha256_of(path) == info["sha256"] else "CORRUPTED"
            rows.append((b["name"], st.st_ino, st.st_nlink, info.get("stored", "?"), check))
    present = sum(1 for r in rows if r[1] != "-")
    lines = [f"Hard links for {rel}",
             f"  {'Version':<24}{'Inode':>12}{'Links':>7}  {'Stored':<8}Checksum"]
    lines += [f"  {v:<24}{str(i):>12}{str(n):>7}  {s:<8}{c}" for v, i, n, s, c in rows]
    lines.append(f"  -> {present} version(s) contain this file, using {len(inodes)} separate "
                 f"cop{'y' if len(inodes) == 1 else 'ies'} of the data on disk.")
    lines.append("     Same inode number = the same data with several names (hard links).")
    lines.append("     \"Links\" is the inode's link count: the data is freed only when it reaches 0.")
    return "\n".join(lines)
