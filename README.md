# Automated File Backup and Restore Utility with Version Control

**Course:** BITE303P – Operating Systems Lab  
**Language:** Python 3.8+ (standard library only, nothing to install)  
**Runs on:** macOS, Linux, Windows

A command-line tool that backs up a folder into timestamped versions, keeps only the
last *N* versions, and restores any version (whole folder or single file). Unchanged
files are stored as **hard links**, so every version looks complete but repeated
backups use almost no extra disk space — the same idea behind macOS Time Machine.

---

## 1. Features

| Feature | What it does |
|---|---|
| Timestamped backups | Each run creates a folder like `2026-10-14_18-05-00` |
| Incremental mode (default) | Copies only new/changed files; unchanged files are hard-linked |
| Full mode (`--full`) | Copies every file every time (used for comparison) |
| Version retention | Keeps the newest *N* versions (default 3), deletes older ones |
| Restore | Whole backup or one file/sub-folder, to original or new location |
| Integrity check | SHA-256 checksum of every file stored in `manifest.json`; `verify` detects corruption |
| Change detection | `status` shows files added / modified / deleted since last backup |
| Exclusions | Skips `.DS_Store`, `Thumbs.db`, `*.tmp`, Office lock files, plus any `--exclude` pattern |
| Crash safety | Backup is built in a hidden `.inprogress_` folder and renamed only when complete |
| Logging | Every action is appended to `backup.log` |
| Interactive menu | Run with no arguments for a numbered menu |
| Graphical interface | `python3 gui.py` opens the tool in your web browser: buttons, folder pickers, a version table |

## 2. Project structure

```
backup_utility/
├── backup_tool.py        # CLI entry point + interactive menu
├── gui.py                # graphical interface: local web server (http.server)
├── web/                  # the interface page: index.html, style.css, app.js
├── core/
│   ├── backup.py         # scanning, hashing, copy vs hard-link, manifest
│   ├── restore.py        # restore + verify
│   ├── versioning.py     # list / load / prune versions
│   └── utils.py          # checksums, logging, path safety
├── demo_tools.py         # Test Lab: cause problems on purpose (corruption, crash, attack...)
├── tests/
│   ├── test_backup.py      # 20 test cases (TC01-TC20)
│   └── test_demo_tools.py  # 8 test cases for the Test Lab tools
├── benchmark.py          # performance evaluation (full vs incremental)
└── make_sample_data.py   # creates a demo folder
```

## 3. Installation

1. Install Python 3.8 or newer (macOS: `python3 --version` to check).
2. Unzip the project and open a terminal in the `backup_utility` folder.

No other packages are needed.

## 4. Usage

### Graphical interface
```
python3 gui.py
```
This starts a small web server **on your own computer only** (address `http://127.0.0.1:8765`)
and opens the interface in your browser. Nothing is sent over the internet. Keep the terminal
open while you use it; press **Ctrl+C** there to stop. If the page doesn't open by itself,
copy the address from the terminal into your browser.

- **Folders** (top): the folder to back up and the backup location. *Choose…* opens the
  normal macOS folder picker (on other systems, type the path) and *Open* shows the folder
  in Finder. If you choose a backup location that already holds other files, it offers a
  `my_backups` subfolder instead, so backups don't get mixed in with them.
- **Backup tab**: versions to keep, full or incremental, extra patterns to skip,
  *Create Backup* and *Show Changes Since Last Backup*.
- **Versions & Restore tab**: table of all versions. Click one to select it (click again,
  or *use latest*, to go back to the latest) and *Verify* or *Restore* it. Restore into a
  different folder, restore only one file or folder (suggestions come from the backup),
  and choose whether to overwrite (you are asked to confirm).
  **Files in …** lists everything stored in the selected version (size, copied or
  hard-linked, modified time); click a file to restore just that one, or *Show in Finder*
  to see the version folder on disk.
- **Log tab**: the contents of `backup.log`.
- **Output** (bottom): the result of every action, in the same format as the terminal.
  Errors are shown in red.

If `sample_data/` exists next to `gui.py`, the folders are pre-filled for the demo.

**Why a browser page and not a desktop window?** The Tk window toolkit that ships with
macOS's built-in Python (Tk 8.5) cannot draw its widgets on recent macOS versions, so a
Tkinter window shows up blank. The browser approach needs only the standard library and
works on any system.

**How it works:** each button sends a request to `gui.py`, which calls the same `core`
functions as the command line. `ThreadingHTTPServer` handles every request in its own
thread, and a lock makes sure only one backup/restore/verify runs at a time. The server
only accepts connections from this computer, and every request must carry a random token
that only the served page knows, so other websites can't trigger actions.

### Test Lab (demonstrating that it works)
The **Test Lab** tab causes problems on purpose so you can show the tool catching and fixing
them. Every result says which button to press next.

| Button | What it does | Then show |
|---|---|---|
| Edit file | Adds a line to a file in your folder | *Show Changes* lists it as modified; *Create Backup* copies only that file |
| Delete file | Deletes a file from your folder (only files in the latest backup) | *Restore* with "Only this file" brings it back |
| Add a new file | Creates `new_file_<time>.txt` | *Show Changes* lists it as added |
| Corrupt file (flip 1 byte) | Changes one byte inside a stored backup file; size stays the same | *Verify* reports it corrupted. Hard-linked versions are damaged too. Repair with a *Full backup* |
| Delete file from backup | Removes a stored file from one version | *Verify* reports it missing in that version only (the others still link to the data) |
| Simulate a crash mid-backup | Leaves a half-written `.inprogress_` folder | It isn't listed as a version; the next *Create Backup* deletes it (`CLEANUP` in the Log) |
| Try a path-traversal attack | Plants `../../evil_demo.txt` in a manifest, tries to restore it, then puts the manifest back | Shows the restore was refused and nothing was written outside the folder |
| Show inode numbers & link counts | For one file, lists the inode and link count in every version | Same inode in several versions = one copy of the data (hard links) |
| Create sample data / Reset demo | (Re)creates `sample_data/`; Reset also deletes `my_backups/` | Start a rehearsal from scratch |

The damage buttons ask for confirmation first.

### Interactive menu (terminal)
```
python3 backup_tool.py
```

### Commands
```
# create a backup (keep last 3 versions)
python3 backup_tool.py backup <source_folder> <backup_folder> [--keep 3] [--full] [--exclude "*.log"]

# list versions
python3 backup_tool.py list <backup_folder>

# what changed since the last backup?
python3 backup_tool.py status <source_folder> <backup_folder>

# restore latest version to the original location (won't overwrite changed files)
python3 backup_tool.py restore <backup_folder>

# restore an older version of one file, overwriting the current one
python3 backup_tool.py restore <backup_folder> --version 2026-10-14_18-05-00 --only Documents/notes.txt --overwrite

# restore everything into a different folder
python3 backup_tool.py restore <backup_folder> --target ~/Desktop/recovered

# check a backup for corruption
python3 backup_tool.py verify <backup_folder> [--version NAME]
```

### Example session
```
$ python3 make_sample_data.py
$ python3 backup_tool.py backup sample_data my_backups
✔ Backup created: 2026-10-14_12-39-52
  Files backed up : 5
  Copied          : 5 files (146.7 KB)
  Skipped         : 2   Errors: 0

$ echo "extra line" >> sample_data/Documents/notes.txt
$ python3 backup_tool.py backup sample_data my_backups
✔ Backup created: 2026-10-14_12-39-53
  Copied          : 1 files (80 B)
  Hard-linked     : 4 files (146.6 KB not re-copied)
```

## 5. Testing

```
python3 -m unittest discover -s tests -v
```
Runs 28 test cases, all passing:
- `test_backup.py`: 20 cases, TC01–TC20 (normal use, version retention, restore, corruption
  detection, error handling, security).
- `test_demo_tools.py`: 8 cases that check every Test Lab problem is caught by the real code
  (corruption in shared hard links, missing files, crash leftovers, the path-traversal attack).

## 6. Performance evaluation

```
python3 benchmark.py --files 300                              # many small files (10–200 KB)
python3 benchmark.py --files 40 --min-kb 2000 --max-kb 8000   # fewer large files (2–8 MB)
```
Measured on macOS (APFS SSD), 4 versions each (initial, no change, 10 % changed, 30 % changed):

| Dataset | Disk used: full → incremental | Time for 3 repeat backups: full → incremental |
|---|---|---|
| 300 files, 10–200 KB (~29 MB) | 118.1 MB → 40.9 MB (**65.3 % less**) | 0.237 s → 0.281 s (**18.5 % slower**) |
| 40 files, 2–8 MB (~181 MB) | 722.8 MB → 253.0 MB (**65.0 % less**) | 0.296 s → 0.077 s (**73.8 % faster**) |

**Storage** savings are consistent: unchanged files cost zero extra bytes. **Time** savings
depend on file size. Creating a hard link is a fixed-cost metadata operation (≈0.3 ms per
file on APFS), while copying costs time proportional to file size. For small files already in
the OS page cache, copying is about as cheap as linking, so incremental mode can be slightly
slower. For larger files, linking wins clearly. Exact timings vary by machine and file system.

Results are saved to `benchmark_results.csv` (use `--out` to keep several runs) for graphs in the report.

## 7. Error handling

| Situation | Behaviour |
|---|---|
| Source folder doesn't exist | Clear error message, exit code 1 |
| Backup folder inside the source | Refused (would back up its own backups forever) |
| Unknown version name / no backups yet | Clear error message |
| A file can't be read (permissions, deleted mid-backup) | Logged as an error; the rest of the backup continues |
| Restore would overwrite a changed file | Skipped unless `--overwrite` is given |
| Tampered manifest with `../` paths | Rejected (path traversal protection) |
| Backup interrupted (Ctrl+C, crash) | Partial `.inprogress_` folder is removed on the next run |
| File system without hard links (e.g. FAT32 USB) | Falls back to normal copying |

## 8. Troubleshooting

- **`python3: command not found`** – install Python from python.org (on Windows use `python`).
- **Permission denied on macOS** for folders like Desktop/Documents – allow Terminal in
  *System Settings → Privacy & Security → Full Disk Access*, or test with a folder in your home directory.
- **Backups to an external drive copy everything every time** – the drive is probably FAT32/exFAT,
  which has no hard links. Format it as APFS/ext4/NTFS to get incremental savings.
