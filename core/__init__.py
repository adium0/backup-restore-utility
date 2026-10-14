"""Core package for the Automated File Backup and Restore Utility."""

from .utils import BackupError
from .backup import create_backup, changes_since_backup
from .restore import restore_backup, verify_backup
from .versioning import list_backups, latest_backup, prune_old_backups

__all__ = [
    "BackupError",
    "create_backup",
    "changes_since_backup",
    "restore_backup",
    "verify_backup",
    "list_backups",
    "latest_backup",
    "prune_old_backups",
]
