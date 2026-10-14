# Implementation Guide – Automated File Backup and Restore Utility

Step-by-step build order, team split, OS concepts to explain in the viva, and a
2-day plan. Every step ends with something you can run.

---

## Team split (2 members)

| Member A – Backup & Versioning | Member B – Restore, Interface & Testing |
|---|---|
| `core/utils.py` (shared helpers) | `core/restore.py` (restore + verify) |
| `core/backup.py` (scan, hash, copy/link, manifest) | `backup_tool.py` (commands + menu) |
| `core/versioning.py` (list, retention, cleanup) | `tests/test_backup.py` (20 test cases) |
| `benchmark.py` (performance evaluation) | `README.md` (user manual) + demo |

Both should understand the whole flow – the viva can ask either person anything.

---

## Architecture

```
                 ┌──────────────────────────────┐
   User ───────▶ │ backup_tool.py (CLI / menu)  │
                 └──────┬───────────┬───────────┘
                        │           │
          ┌─────────────▼──┐   ┌────▼──────────────┐
          │ backup.py      │   │ restore.py        │
          │ scan → hash →  │   │ read manifest →   │
          │ copy or link → │   │ copy back →       │
          │ manifest       │   │ verify checksum   │
          └──────┬─────────┘   └────┬──────────────┘
                 │                  │
          ┌──────▼──────────────────▼──────┐
          │ versioning.py  (list / prune)  │
          │ utils.py (SHA-256, log, paths) │
          └──────────────┬─────────────────┘
                         ▼
      backup_folder/
        2026-10-14_18-05-00/   ← version 1 (files + manifest.json)
        2026-10-14_19-10-12/   ← version 2 (changed files copied, rest hard-linked)
        backup.log
```

### Backup algorithm (pseudo-code)
```
procedure BACKUP(source, dest, keep, mode)
    validate source exists and dest is not inside source
    remove any leftover .inprogress_ folders
    prev ← manifest of latest backup of this source (incremental mode only)
    work ← dest/.inprogress_<timestamp>
    for each regular file f in walk(source), skipping excluded patterns and symlinks
        if prev has f with same size and mtime then h ← prev[f].hash
        else h ← SHA256(f)
        if prev has f and prev[f].hash = h then HARDLINK(prev_copy(f), work/f)
        else COPY(f, work/f)            // keeps timestamps + permissions
        manifest[f] ← {size, mtime, h}
    write manifest.json into work
    RENAME(work, dest/<timestamp>)      // atomic: version appears all at once
    delete oldest versions until only `keep` remain
    log the result
```

### Restore algorithm (pseudo-code)
```
procedure RESTORE(dest, version, target, only, overwrite)
    m ← manifest of version (latest if not given)
    for each file f in m (or only the requested file/folder)
        reject f if it escapes the folder (e.g. "../../x")
        if target/f exists and its hash = m[f].hash → skip (already up to date)
        if target/f exists and not overwrite → skip
        COPY(version/f, target/f)
        if SHA256(target/f) ≠ m[f].hash → report failure
```

---

## Step-by-step implementation

### Step 1 – Set up the project (15 min, both)
Create the folder structure shown in the README, an empty `core/__init__.py`,
and a Git repository (the guidelines ask for version history):
```
git init && git add . && git commit -m "Project skeleton"
```

### Step 2 – Shared helpers `core/utils.py` (30 min, A)
- `sha256_of(path)` – read the file in 64 KB chunks and hash it.
- `log_event(root, msg)` – append a timestamped line to `backup.log`.
- `is_inside()` / `safe_join()` – path checks used for safety.
- `BackupError` – one exception type for all user-facing errors.

**Check:** `python3 -c "from core.utils import sha256_of; print(sha256_of('README.md'))"`

### Step 3 – Simple full backup (1 hr, A)
In `core/backup.py`: walk the source with `os.walk`, copy each file with
`shutil.copy2` into a timestamped folder, and write `manifest.json`
(size, mtime, sha256 per file).

**Check:** back up a test folder and open the manifest.

### Step 4 – Version listing and retention `core/versioning.py` (45 min, A)
`list_backups()` reads every manifest and sorts by creation time.
`prune_old_backups(keep)` deletes the oldest folders with `shutil.rmtree`.

**Check:** run backup 5 times with `keep=3` → only 3 folders remain.

### Step 5 – Restore + verify `core/restore.py` (1.5 hr, B – can run in parallel with Steps 3–4)
Read the manifest, copy files back with `copy2`, re-hash each restored file
and compare. Add `--only` (single file/folder), `--overwrite`, and `--target`.
`verify_backup()` re-hashes every stored file to detect corruption.

**Check:** delete a file from the source, restore it, compare checksums.

### Step 6 – Incremental backups with hard links (1 hr, A)
Load the previous manifest. If a file's checksum matches the previous version,
call `os.link(previous_copy, new_path)` instead of copying. Add the
size+mtime shortcut so unchanged files aren't re-read.
Build in `.inprogress_<name>` and `os.rename` at the end.

**Check:** two backups in a row → second one says "Copied: 0, Hard-linked: all".
Run `ls -li` on the same file in both versions: identical inode number.

### Step 7 – CLI and menu `backup_tool.py` (1.5 hr, B)
`argparse` sub-commands: `backup`, `restore`, `list`, `verify`, `status`.
With no arguments, show a numbered menu. Catch `BackupError` and print a
clean message instead of a traceback.

### Step 8 – Change detection `status` (30 min, A or B)
Compare the current source with the latest manifest: set difference gives
added/deleted; size/mtime/hash comparison gives modified.

### Step 9 – Testing (1.5 hr, B)
Write the test cases in `tests/test_backup.py` using `unittest` and temporary
folders. Run: `python3 -m unittest discover -s tests -v`.
Put the test table (below) into the report.

### Step 10 – Performance evaluation (45 min, A)
`benchmark.py` generates a dataset, runs 4 backups in full mode and 4 in
incremental mode, and measures time, data copied, and real disk usage
(each inode counted once). Use the CSV to draw graphs for Chapter 4.

### Step 11 – Documentation and demo (1 hr, both)
README (user manual), screenshots of each command, and rehearse the demo below.

---

## Test cases (for the report)

| ID | Test | Expected result |
|---|---|---|
| TC01 | First backup | All files copied, manifest created |
| TC02 | Second backup, nothing changed | 0 copied, all hard-linked, same inode |
| TC03 | One file modified | Only that file copied |
| TC04 | Full mode | Every file copied |
| TC05 | 5 backups with keep=3 | Only 3 versions remain |
| TC06 | Delete old version that newer one links to | Newer version still verifies OK |
| TC07 | Restore to a new folder | Checksums identical to original |
| TC08 | Restore older version of an overwritten file | Old content returned |
| TC09 | Restore a deleted file | File recreated |
| TC10 | Restore without `--overwrite` over a changed file | File left untouched, reported as skipped |
| TC11 | Edit a restored file | Backup not affected (restored files are real copies) |
| TC12 | Tamper with / delete a stored file | `verify` reports corrupted / missing |
| TC13 | `status` after add, modify, delete | All three detected |
| TC14 | `.DS_Store` and `*.tmp` present | Skipped |
| TC15 | Source folder missing | Error message |
| TC16 | Backup folder inside source | Refused |
| TC17 | Unknown version name | Error message |
| TC18 | Restore when no backups exist | Error message |
| TC19 | Manifest contains `../../evil.txt` | Rejected, nothing written outside target |
| TC20 | Leftover `.inprogress_` folder | Cleaned up on next run |

---

## OS concepts used (viva preparation)

**File systems and directory traversal** – `os.walk` performs a depth-first
traversal of the directory tree; the backup mirrors that hierarchy.

**Inodes and hard links** – On Unix file systems (APFS, ext4) a file's data and
metadata live in an *inode*; a file name is just a directory entry pointing to an
inode. `os.link` adds a second name for the same inode, so no data is copied.
The inode keeps a *link count*; data is freed only when the count reaches 0.
That's why deleting an old version (TC06) never damages a newer one.
macOS Time Machine and `rsync --link-dest` use exactly this technique.

**File metadata** – `os.stat` returns size, modification time (mtime), inode
number, permissions. `shutil.copy2` preserves mtime and permission bits.

**Atomic rename** – `rename()` within one file system is atomic: the version
folder either fully exists or doesn't. A crash mid-backup leaves only an
`.inprogress_` folder, which is cleaned up later. Databases and package
managers use the same pattern.

**Buffered file I/O** – Files are read in 64 KB blocks, so memory use stays
constant regardless of file size (like the OS buffer cache reading disk blocks).

**Data integrity** – SHA-256 checksums detect silent corruption (bit rot,
tampering). File systems like ZFS and Btrfs store block checksums for the same
reason.

**Storage management / space–time trade-off** – Incremental backups save
~65 % disk space vs full backups in our benchmark. Time savings depend on file
size: ~74 % faster with 2–8 MB files, but slightly *slower* with many small
(10–200 KB) files, because a hard link is a fixed-cost metadata write (directory
entry + inode link count, journaled by APFS) while copying a small cached file
is almost as cheap.

**Protection and security** – Path traversal checks stop a malicious manifest
from writing outside the target folder; permission errors are handled per file.

**Likely viva questions**
1. *What is the difference between a hard link and a symbolic link?* Hard link = another name for the same inode (data survives if the original name is deleted; same file system only). Symlink = a small file containing a path (breaks if the target moves). We skip symlinks in the source and use hard links in the backup.
2. *Why can't you hard-link to the source file directly?* Editing the source would silently change the backup too. We link only between backup versions, which are never edited.
3. *Why use SHA-256 instead of just comparing mtime?* mtime can be changed or preserved by tools; a checksum proves content is identical. mtime+size is used only as a fast pre-check.
4. *What happens if power fails mid-backup?* The `.inprogress_` folder is never renamed, so it's ignored and deleted next run. Previous versions are untouched.
5. *Why doesn't incremental mode save space on a USB stick?* FAT32/exFAT don't support hard links; the tool falls back to copying.
6. *Why is incremental sometimes slower for small files?* `link()` is a metadata operation with a fixed cost per file (update the directory, bump the inode's link count, journal the change). Copying a 50 KB file that is already in the page cache costs about the same, so linking only pays off in time for larger files. It always pays off in space.

---

## 2-day plan

| | Member A | Member B |
|---|---|---|
| **Day 1 – morning** | Steps 1–3 (skeleton, utils, full backup) | Step 1, then Step 5 (restore + verify) |
| **Day 1 – afternoon** | Steps 4 & 6 (retention, hard links) | Step 7 (CLI + menu) |
| **Day 1 – evening** | Integrate, run end-to-end together | Integrate, run end-to-end together |
| **Day 2 – morning** | Step 8 (status) + Step 10 (benchmark, graphs) | Step 9 (tests) |
| **Day 2 – afternoon** | Report: design, algorithms, results | Report: testing, user manual, screenshots |
| **Day 2 – evening** | Rehearse demo + viva questions | Rehearse demo + viva questions |

---

## Demo script (5 minutes)

```
python3 make_sample_data.py
python3 backup_tool.py backup sample_data my_backups          # first backup, .DS_Store skipped
echo "new line" >> sample_data/Documents/notes.txt
python3 backup_tool.py status sample_data my_backups          # shows the modified file
python3 backup_tool.py backup sample_data my_backups          # only 1 copied, rest hard-linked
ls -li my_backups/*/Projects/hello.py                         # same inode number = hard link
python3 backup_tool.py list my_backups
rm sample_data/Projects/hello.py                              # "accidental delete"
python3 backup_tool.py restore my_backups --only Projects/hello.py
python3 backup_tool.py verify my_backups
python3 -m unittest discover -s tests -v                      # 20 tests pass
python3 benchmark.py                                          # full vs incremental numbers
```
