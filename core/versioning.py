"""Version control for backups: listing, loading manifests, and pruning old versions.

Each backup is a folder named by timestamp that contains the copied files plus a
manifest.json describing every file (size, modification time, SHA-256 checksum).
"""

import json
import os
import shutil

from .utils import IN_PROGRESS_PREFIX, MANIFEST_NAME, BackupError, log_event


def _snapshot_names(backup_root):
    """Folder names inside backup_root that are finished backups (have a manifest)."""
    if not os.path.isdir(backup_root):
        return []
    names = []
    for name in os.listdir(backup_root):
        path = os.path.join(backup_root, name)
        if name.startswith(".") or not os.path.isdir(path):
            continue
        if os.path.isfile(os.path.join(path, MANIFEST_NAME)):
            names.append(name)
    return names


def load_manifest(backup_root, name):
    """Read the manifest.json of one backup version."""
    path = os.path.join(backup_root, name, MANIFEST_NAME)
    if not os.path.isfile(path):
        raise BackupError(f"No backup named '{name}' in {backup_root}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_backups(backup_root):
    """All backup versions, oldest first, with a short summary of each."""
    backups = []
    for name in _snapshot_names(backup_root):
        manifest = load_manifest(backup_root, name)
        files = manifest["files"]
        backups.append({
            "name": name,
            "created": manifest["created"],
            "source": manifest["source"],
            "mode": manifest.get("mode", "full"),
            "files": len(files),
            "total_size": sum(f["size"] for f in files.values()),
            "stats": manifest.get("stats", {}),
        })
    backups.sort(key=lambda b: b["created"])
    return backups


def latest_backup(backup_root):
    """Name of the newest backup, or None if there are none."""
    backups = list_backups(backup_root)
    return backups[-1]["name"] if backups else None


def resolve_name(backup_root, name=None):
    """Turn None/'latest' into the newest backup name and check that the name exists."""
    if name in (None, "", "latest"):
        latest = latest_backup(backup_root)
        if latest is None:
            raise BackupError(f"No backups found in {backup_root}")
        return latest
    load_manifest(backup_root, name)  # raises if missing
    return name


def prune_old_backups(backup_root, keep):
    """Delete the oldest versions so only the newest `keep` remain.

    Unchanged files are hard links shared between versions, so deleting an old
    version only removes one directory entry; the data stays on disk as long as a
    newer version still links to it (the inode's link count is above zero).
    """
    if keep is None or keep < 1:
        return []
    removed = []
    for backup in list_backups(backup_root)[:-keep]:
        shutil.rmtree(os.path.join(backup_root, backup["name"]))
        removed.append(backup["name"])
        log_event(backup_root, f"PRUNE removed old version {backup['name']}")
    return removed


def clean_incomplete(backup_root):
    """Remove half-written backups left behind by a crash or Ctrl+C."""
    removed = []
    if os.path.isdir(backup_root):
        for name in os.listdir(backup_root):
            if name.startswith(IN_PROGRESS_PREFIX):
                shutil.rmtree(os.path.join(backup_root, name), ignore_errors=True)
                removed.append(name)
                log_event(backup_root, f"CLEANUP removed incomplete backup {name}")
    return removed
