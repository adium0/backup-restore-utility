"""Test cases for the backup utility. Run from the project folder:

    python -m unittest discover -s tests -v
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import (  # noqa: E402
    BackupError,
    changes_since_backup,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from core.utils import MANIFEST_NAME, sha256_of  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class BackupUtilityTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "source")
        self.dest = os.path.join(self.tmp, "backups")
        write(os.path.join(self.src, "a.txt"), "alpha")
        write(os.path.join(self.src, "docs", "b.txt"), "bravo")
        write(os.path.join(self.src, "docs", "deep", "c.txt"), "charlie")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # TC01
    def test_first_backup_copies_all_files_and_writes_manifest(self):
        res = create_backup(self.src, self.dest)
        self.assertEqual(res["stats"]["files"], 3)
        self.assertEqual(res["stats"]["copied"], 3)
        self.assertTrue(os.path.isfile(os.path.join(res["path"], MANIFEST_NAME)))
        self.assertEqual(read(os.path.join(res["path"], "docs", "deep", "c.txt")), "charlie")

    # TC02
    def test_unchanged_files_are_hard_linked(self):
        first = create_backup(self.src, self.dest)
        second = create_backup(self.src, self.dest)
        self.assertEqual(second["stats"]["copied"], 0)
        self.assertEqual(second["stats"]["linked"], 3)
        ino1 = os.stat(os.path.join(first["path"], "a.txt")).st_ino
        ino2 = os.stat(os.path.join(second["path"], "a.txt")).st_ino
        self.assertEqual(ino1, ino2, "unchanged file should share the same inode")

    # TC03
    def test_only_modified_file_is_copied(self):
        create_backup(self.src, self.dest)
        write(os.path.join(self.src, "a.txt"), "alpha version two")
        res = create_backup(self.src, self.dest)
        self.assertEqual(res["stats"]["copied"], 1)
        self.assertEqual(res["stats"]["linked"], 2)

    # TC04
    def test_full_mode_copies_everything(self):
        create_backup(self.src, self.dest)
        res = create_backup(self.src, self.dest, mode="full")
        self.assertEqual(res["stats"]["copied"], 3)
        self.assertEqual(res["stats"]["linked"], 0)

    # TC05
    def test_retention_keeps_only_last_n_versions(self):
        for i in range(5):
            write(os.path.join(self.src, "a.txt"), "x" * (i + 1))
            create_backup(self.src, self.dest, keep=3)
        self.assertEqual(len(list_backups(self.dest)), 3)

    # TC06
    def test_pruning_old_version_does_not_damage_newer_ones(self):
        create_backup(self.src, self.dest, keep=1)
        res = create_backup(self.src, self.dest, keep=1)   # first version deleted, files were linked
        self.assertEqual(len(list_backups(self.dest)), 1)
        rep = verify_backup(self.dest, res["name"])
        self.assertEqual(rep["ok"], 3)

    # TC07
    def test_full_restore_to_new_folder_is_identical(self):
        create_backup(self.src, self.dest)
        target = os.path.join(self.tmp, "restored")
        res = restore_backup(self.dest, target=target)
        self.assertEqual(len(res["restored"]), 3)
        for rel in ("a.txt", os.path.join("docs", "b.txt"), os.path.join("docs", "deep", "c.txt")):
            self.assertEqual(sha256_of(os.path.join(self.src, rel)), sha256_of(os.path.join(target, rel)))

    # TC08
    def test_restore_older_version_after_file_changed(self):
        first = create_backup(self.src, self.dest)
        write(os.path.join(self.src, "a.txt"), "accidentally overwritten!")
        create_backup(self.src, self.dest)
        restore_backup(self.dest, name=first["name"], only="a.txt", overwrite=True)
        self.assertEqual(read(os.path.join(self.src, "a.txt")), "alpha")

    # TC09
    def test_restore_deleted_file_to_original_location(self):
        create_backup(self.src, self.dest)
        os.remove(os.path.join(self.src, "docs", "b.txt"))
        res = restore_backup(self.dest, only="docs/b.txt")
        self.assertEqual(res["restored"], ["docs/b.txt"])
        self.assertEqual(read(os.path.join(self.src, "docs", "b.txt")), "bravo")

    # TC10
    def test_restore_does_not_overwrite_without_permission(self):
        create_backup(self.src, self.dest)
        write(os.path.join(self.src, "a.txt"), "newer local edit")
        res = restore_backup(self.dest)
        self.assertEqual(read(os.path.join(self.src, "a.txt")), "newer local edit")
        reasons = {s["file"]: s["reason"] for s in res["skipped"]}
        self.assertIn("exists", reasons["a.txt"])

    # TC11
    def test_restored_files_are_independent_copies(self):
        create_backup(self.src, self.dest)
        target = os.path.join(self.tmp, "restored")
        restore_backup(self.dest, target=target)
        write(os.path.join(target, "a.txt"), "editing the restored copy")
        self.assertEqual(verify_backup(self.dest)["corrupted"], [])

    # TC12
    def test_verify_detects_corruption_and_missing_files(self):
        res = create_backup(self.src, self.dest)
        write(os.path.join(res["path"], "a.txt"), "tampered")
        os.remove(os.path.join(res["path"], "docs", "b.txt"))
        rep = verify_backup(self.dest)
        self.assertEqual(rep["corrupted"], ["a.txt"])
        self.assertEqual(rep["missing"], ["docs/b.txt"])

    # TC13
    def test_status_reports_added_modified_deleted(self):
        create_backup(self.src, self.dest)
        write(os.path.join(self.src, "new.txt"), "new file")
        write(os.path.join(self.src, "a.txt"), "changed content")
        os.remove(os.path.join(self.src, "docs", "deep", "c.txt"))
        ch = changes_since_backup(self.src, self.dest)
        self.assertEqual(ch["added"], ["new.txt"])
        self.assertEqual(ch["modified"], ["a.txt"])
        self.assertEqual(ch["deleted"], ["docs/deep/c.txt"])

    # TC14
    def test_excluded_files_are_skipped(self):
        write(os.path.join(self.src, ".DS_Store"), "junk")
        write(os.path.join(self.src, "scratch.tmp"), "junk")
        res = create_backup(self.src, self.dest)
        self.assertEqual(res["stats"]["files"], 3)
        self.assertEqual(res["stats"]["skipped"], 2)

    # TC15
    def test_error_when_source_missing(self):
        with self.assertRaises(BackupError):
            create_backup(os.path.join(self.tmp, "nope"), self.dest)

    # TC16
    def test_error_when_backup_folder_inside_source(self):
        with self.assertRaises(BackupError):
            create_backup(self.src, os.path.join(self.src, "backups"))

    # TC17
    def test_error_when_restoring_unknown_version(self):
        create_backup(self.src, self.dest)
        with self.assertRaises(BackupError):
            restore_backup(self.dest, name="1999-01-01_00-00-00")

    # TC18
    def test_error_when_no_backups_exist(self):
        with self.assertRaises(BackupError):
            restore_backup(self.dest)

    # TC19
    def test_unsafe_manifest_path_is_rejected(self):
        res = create_backup(self.src, self.dest)
        mpath = os.path.join(res["path"], MANIFEST_NAME)
        with open(mpath, encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest["files"]["../../evil.txt"] = manifest["files"]["a.txt"]
        with open(mpath, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)
        target = os.path.join(self.tmp, "restored")
        res = restore_backup(self.dest, target=target)
        self.assertIn("../../evil.txt", [f["file"] for f in res["failed"]])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "evil.txt")))

    # TC20
    def test_interrupted_backup_is_cleaned_up(self):
        stale = os.path.join(self.dest, ".inprogress_2026-01-01_00-00-00")
        os.makedirs(stale)
        create_backup(self.src, self.dest)
        self.assertFalse(os.path.exists(stale))
        self.assertEqual(len(list_backups(self.dest)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
