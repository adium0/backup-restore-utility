#!/usr/bin/env python3
"""Automated File Backup and Restore Utility with Version Control.

Run with no arguments for the interactive menu, or use commands:

  python backup_tool.py backup  <source> <backup_folder> [--keep 3] [--full] [--exclude PATTERN]
  python backup_tool.py restore <backup_folder> [--version NAME] [--target DIR] [--only PATH] [--overwrite]
  python backup_tool.py list    <backup_folder>
  python backup_tool.py verify  <backup_folder> [--version NAME]
  python backup_tool.py status  <source> <backup_folder>
"""

import argparse
import sys

from core import (
    BackupError,
    changes_since_backup,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from core.backup import DEFAULT_EXCLUDES
from core.utils import human_size

DEFAULT_KEEP = 3


# ---------------------------------------------------------------- printing helpers

def print_backup_result(res):
    s = res["stats"]
    print(f"\n✔ Backup created: {res['name']}")
    print(f"  Based on        : {res['based_on'] or 'nothing (first/full backup)'}")
    print(f"  Files backed up : {s['files']}")
    print(f"  Copied          : {s['copied']} files ({human_size(s['bytes_copied'])})")
    print(f"  Hard-linked     : {s['linked']} files ({human_size(s['bytes_linked'])} not re-copied)")
    print(f"  Skipped         : {s['skipped']}   Errors: {s['errors']}")
    print(f"  Time taken      : {s['seconds']} s")
    for err in res["errors"]:
        print(f"  ! {err['file']}: {err['error']}")
    if res["pruned"]:
        print(f"  Removed old versions: {', '.join(res['pruned'])}")


def print_backup_list(backups):
    if not backups:
        print("No backups found.")
        return
    print(f"\n{'#':<3} {'Version':<22} {'Mode':<12} {'Files':>6} {'Size':>10} {'Copied':>7} {'Linked':>7}")
    print("-" * 72)
    for i, b in enumerate(backups, 1):
        st = b["stats"]
        print(f"{i:<3} {b['name']:<22} {b['mode']:<12} {b['files']:>6} "
              f"{human_size(b['total_size']):>10} {st.get('copied', '-'):>7} {st.get('linked', '-'):>7}")
    print(f"\nSource folder: {backups[-1]['source']}")


def print_restore_result(res):
    print(f"\n✔ Restored version {res['backup']} into {res['target']}")
    print(f"  Restored: {len(res['restored'])}   Skipped: {len(res['skipped'])}   Failed: {len(res['failed'])}")
    for item in res["skipped"]:
        print(f"  - skipped {item['file']} ({item['reason']})")
    for item in res["failed"]:
        print(f"  ! failed  {item['file']}: {item['error']}")


def print_verify_result(rep):
    healthy = not rep["missing"] and not rep["corrupted"]
    print(f"\n{'✔' if healthy else '✘'} Verify {rep['backup']}: {rep['ok']} files OK, "
          f"{len(rep['missing'])} missing, {len(rep['corrupted'])} corrupted")
    for f in rep["missing"]:
        print(f"  ! missing   {f}")
    for f in rep["corrupted"]:
        print(f"  ! corrupted {f}")


def print_status(ch):
    print(f"\nChanges since backup {ch['backup']}:")
    if not (ch["added"] or ch["modified"] or ch["deleted"]):
        print("  No changes. Everything is backed up.")
    for f in ch["added"]:
        print(f"  + added    {f}")
    for f in ch["modified"]:
        print(f"  * modified {f}")
    for f in ch["deleted"]:
        print(f"  - deleted  {f}")


# ---------------------------------------------------------------- command handlers

def cmd_backup(args):
    excludes = DEFAULT_EXCLUDES + (args.exclude or [])
    res = create_backup(args.source, args.dest, keep=args.keep,
                        mode="full" if args.full else "incremental", excludes=excludes)
    print_backup_result(res)


def cmd_restore(args):
    res = restore_backup(args.dest, name=args.version, target=args.target,
                         only=args.only, overwrite=args.overwrite)
    print_restore_result(res)
    return 1 if res["failed"] else 0


def cmd_list(args):
    print_backup_list(list_backups(args.dest))


def cmd_verify(args):
    rep = verify_backup(args.dest, args.version)
    print_verify_result(rep)
    return 0 if not rep["missing"] and not rep["corrupted"] else 1


def cmd_status(args):
    print_status(changes_since_backup(args.source, args.dest))


# ---------------------------------------------------------------- interactive menu

def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def interactive_menu():
    print("=" * 52)
    print("  Automated File Backup & Restore Utility")
    print("=" * 52)
    source, dest = None, None
    while True:
        print("\n1. Create backup\n2. Restore backup\n3. List backup versions"
              "\n4. Verify a backup\n5. Show changes since last backup\n6. Exit")
        choice = input("Choose an option (1-6): ").strip()
        try:
            if choice == "1":
                source = ask("Folder to back up", source)
                dest = ask("Backup location", dest)
                keep = int(ask("How many versions to keep", str(DEFAULT_KEEP)))
                full = ask("Full backup instead of incremental? (y/n)", "n").lower() == "y"
                print_backup_result(create_backup(source, dest, keep=keep,
                                                  mode="full" if full else "incremental"))
            elif choice == "2":
                dest = ask("Backup location", dest)
                print_backup_list(list_backups(dest))
                version = ask("Version to restore (name or 'latest')", "latest")
                target = ask("Restore into folder (blank = original location)", "")
                only = ask("Restore only this file/folder (blank = everything)", "")
                overwrite = ask("Overwrite files that differ? (y/n)", "n").lower() == "y"
                print_restore_result(restore_backup(dest, version, target or None,
                                                    only or None, overwrite))
            elif choice == "3":
                dest = ask("Backup location", dest)
                print_backup_list(list_backups(dest))
            elif choice == "4":
                dest = ask("Backup location", dest)
                print_verify_result(verify_backup(dest, ask("Version (name or 'latest')", "latest")))
            elif choice == "5":
                source = ask("Folder to check", source)
                dest = ask("Backup location", dest)
                print_status(changes_since_backup(source, dest))
            elif choice == "6":
                print("Goodbye!")
                return 0
            else:
                print("Please enter a number from 1 to 6.")
        except BackupError as exc:
            print(f"Error: {exc}")
        except ValueError:
            print("Error: please enter a valid number.")


# ---------------------------------------------------------------- argument parsing

def build_parser():
    parser = argparse.ArgumentParser(
        description="Automated File Backup and Restore Utility with Version Control")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("backup", help="create a new backup version")
    p.add_argument("source", help="folder to back up")
    p.add_argument("dest", help="folder where backups are stored")
    p.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="versions to keep (default 3)")
    p.add_argument("--full", action="store_true", help="copy every file instead of hard-linking unchanged ones")
    p.add_argument("--exclude", action="append", help="extra file pattern to skip, e.g. '*.log'")
    p.set_defaults(func=cmd_backup)

    p = sub.add_parser("restore", help="restore a backup version")
    p.add_argument("dest", help="folder where backups are stored")
    p.add_argument("--version", default="latest", help="version name (default: latest)")
    p.add_argument("--target", help="restore into this folder (default: original location)")
    p.add_argument("--only", help="restore just this file or sub-folder")
    p.add_argument("--overwrite", action="store_true", help="replace files that differ")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("list", help="list backup versions")
    p.add_argument("dest")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("verify", help="check a backup for missing or corrupted files")
    p.add_argument("dest")
    p.add_argument("--version", default="latest")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="show what changed since the last backup")
    p.add_argument("source")
    p.add_argument("dest")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("menu", help="interactive menu")
    p.set_defaults(func=lambda a: interactive_menu())
    return parser


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if not argv:
            return interactive_menu()
        args = build_parser().parse_args(argv)
        if not getattr(args, "func", None):
            build_parser().print_help()
            return 1
        return args.func(args) or 0
    except BackupError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
