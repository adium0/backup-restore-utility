"""Tests for the Test Lab tools: each simulated problem must be caught by the real code.

    python -m unittest discover -s tests -v
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import demo_tools  # noqa: E402
from core import (  # noqa: E402
    BackupError,
    changes_since_backup,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from core.utils import MANIFEST_NAME  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class DemoToolsTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.src = os.path.join(self.tmp, "source")
        self.dest = os.path.join(self.tmp, "backups")
        write(os.path.join(self.src, "a.txt"), "alpha")
        write(os.path.join(self.src, "docs", "b.txt"), "bravo")
        self.v1 = create_backup(self.src, self.dest)["name"]
        self.v2 = create_backup(self.src, self.dest)["name"]   # everything hard-linked to v1

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_edit_and_add_are_detected_by_status(self):
        demo_tools.edit_source_file(self.src, self.dest, "a.txt")
        demo_tools.add_source_file(self.src)
        ch = changes_since_backup(self.src, self.dest)
        self.assertEqual(ch["modified"], ["a.txt"])
        self.assertEqual(len(ch["added"]), 1)

    def test_deleted_source_file_can_be_restored(self):
        demo_tools.delete_source_file(self.src, self.dest, "docs/b.txt")
        self.assertFalse(os.path.exists(os.path.join(self.src, "docs", "b.txt")))
        restore_backup(self.dest, only="docs/b.txt")
        self.assertTrue(os.path.exists(os.path.join(self.src, "docs", "b.txt")))

    def test_source_tools_refuse_files_not_backed_up(self):
        write(os.path.join(self.src, "unsaved.txt"), "not backed up")
        with self.assertRaises(BackupError):
            demo_tools.delete_source_file(self.src, self.dest, "unsaved.txt")
        self.assertTrue(os.path.exists(os.path.join(self.src, "unsaved.txt")))

    def test_corruption_is_caught_in_every_version_sharing_the_inode(self):
        report = demo_tools.corrupt_backup_file(self.dest, self.v1, "a.txt")
        self.assertIn("shared by 2 versions", report)
        for name in (self.v1, self.v2):
            self.assertEqual(verify_backup(self.dest, name)["corrupted"], ["a.txt"])

    def test_deleting_from_one_version_leaves_the_other_intact(self):
        demo_tools.delete_backup_file(self.dest, self.v1, "a.txt")
        self.assertEqual(verify_backup(self.dest, self.v1)["missing"], ["a.txt"])
        self.assertEqual(verify_backup(self.dest, self.v2)["ok"], 2)

    def test_crash_leftover_is_ignored_then_cleaned_up(self):
        demo_tools.simulate_crash(self.dest)
        self.assertEqual(len(list_backups(self.dest)), 2)        # leftover is not a version
        create_backup(self.src, self.dest)
        self.assertFalse(any(n.startswith(".inprogress_") for n in os.listdir(self.dest)))

    def test_path_traversal_attack_is_blocked_and_manifest_restored(self):
        manifest = os.path.join(self.dest, self.v2, MANIFEST_NAME)
        with open(manifest, "rb") as fh:
            before = fh.read()
        report = demo_tools.path_traversal_attack(self.dest, self.v2)
        self.assertIn("Attack blocked", report)
        with open(manifest, "rb") as fh:
            self.assertEqual(fh.read(), before)

    def test_hard_link_report_shows_one_shared_inode(self):
        report = demo_tools.hard_link_report(self.dest, "a.txt")
        self.assertIn("using 1 separate copy", report)
        ino = os.stat(os.path.join(self.dest, self.v1, "a.txt")).st_ino
        self.assertEqual(report.count(str(ino)), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
