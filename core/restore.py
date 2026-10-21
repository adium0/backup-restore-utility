"""Restore module: copies files from a chosen backup version back to disk and checks them.

Restored files are always real copies (never hard links), so editing a restored
file can never change the data stored inside the backup.
"""

import os
import shutil

from .utils import BackupError, is_inside, log_event, safe_join, sha256_of
from .versioning import load_manifest, resolve_name


def restore_backup(backup_root, name=None, target=None, only=None, overwrite=False, verify=True):
    """Restore a backup version.

    name      -- version to restore (None or 'latest' = newest)
    target    -- folder to restore into (default: the original source folder)
    only      -- restore just this file or sub-folder (path relative to the source)
    overwrite -- replace existing files that differ from the backup
    verify    -- re-check each restored file's SHA-256 against the manifest
    """
    backup_root = os.path.abspath(backup_root)
    name = resolve_name(backup_root, name)
    manifest = load_manifest(backup_root, name)
    snapshot = os.path.join(backup_root, name)
    target = os.path.abspath(target or manifest["source"])

    if is_inside(target, backup_root):
        raise BackupError(f"Can't restore into {target}: that is the backup location "
                          f"({backup_root}) or inside it. Choose a different folder to restore into.")

    files = manifest["files"]
    if only:
        key = only.replace(os.sep, "/").strip("/")
        selected = {k: v for k, v in files.items() if k == key or k.startswith(key + "/")}
        if not selected:
            raise BackupError(f"'{only}' is not in backup {name}")
    else:
        selected = files

    result = {"backup": name, "target": target, "restored": [], "skipped": [], "failed": []}
    for key, info in sorted(selected.items()):
        try:
            src = safe_join(snapshot, key)
            dst = safe_join(target, key)
            if os.path.exists(dst):
                if os.path.isfile(dst) and sha256_of(dst) == info["sha256"]:
                    result["skipped"].append({"file": key, "reason": "already up to date"})
                    continue
                if not overwrite:
                    result["skipped"].append({"file": key, "reason": "exists (use overwrite)"})
                    continue
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            if verify and sha256_of(dst) != info["sha256"]:
                result["failed"].append({"file": key, "error": "checksum mismatch after restore"})
            else:
                result["restored"].append(key)
        except (OSError, BackupError) as exc:
            result["failed"].append({"file": key, "error": str(exc)})

    log_event(backup_root,
              f"RESTORE {name} -> {target} restored={len(result['restored'])} "
              f"skipped={len(result['skipped'])} failed={len(result['failed'])}")
    return result


def verify_backup(backup_root, name=None):
    """Check every file in a backup against its stored checksum (detects corruption)."""
    backup_root = os.path.abspath(backup_root)
    name = resolve_name(backup_root, name)
    manifest = load_manifest(backup_root, name)
    snapshot = os.path.join(backup_root, name)

    report = {"backup": name, "ok": 0, "missing": [], "corrupted": []}
    for key, info in sorted(manifest["files"].items()):
        path = safe_join(snapshot, key)
        if not os.path.isfile(path):
            report["missing"].append(key)
        elif sha256_of(path) != info["sha256"]:
            report["corrupted"].append(key)
        else:
            report["ok"] += 1

    status = "OK" if not report["missing"] and not report["corrupted"] else "PROBLEMS"
    log_event(backup_root, f"VERIFY {name} {status} ok={report['ok']} "
                           f"missing={len(report['missing'])} corrupted={len(report['corrupted'])}")
    return report
