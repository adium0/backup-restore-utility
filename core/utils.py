"""Shared helpers: checksums, timestamps, size formatting, logging, path safety."""

import hashlib
import os
from datetime import datetime

MANIFEST_NAME = "manifest.json"
LOG_NAME = "backup.log"
TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
IN_PROGRESS_PREFIX = ".inprogress_"
CHUNK_SIZE = 64 * 1024  # read files in 64 KB blocks so big files never sit fully in RAM


class BackupError(Exception):
    """Raised for user-facing problems (bad paths, missing backups, etc.)."""


def sha256_of(path):
    """Return the SHA-256 checksum of a file, reading it block by block."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def human_size(num_bytes):
    """Format a byte count as B / KB / MB / GB."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def now_stamp():
    """Timestamp used to name each backup version, e.g. 2026-10-14_18-05-00."""
    return datetime.now().strftime(TIMESTAMP_FORMAT)


def log_event(backup_root, message):
    """Append one line to backup.log inside the backup folder."""
    os.makedirs(backup_root, exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}\n"
    with open(os.path.join(backup_root, LOG_NAME), "a", encoding="utf-8") as fh:
        fh.write(line)


def is_inside(child, parent):
    """True if path `child` is `parent` itself or somewhere beneath it."""
    child = os.path.realpath(child)
    parent = os.path.realpath(parent)
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:  # different drives on Windows
        return False


def safe_join(base, rel):
    """Join a manifest path onto `base`, refusing anything that escapes it (e.g. '../../etc')."""
    full = os.path.normpath(os.path.join(base, rel))
    if not is_inside(full, base):
        raise BackupError(f"Unsafe path in manifest: {rel}")
    return full
