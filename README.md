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

## 2. Project structure

```
backup_utility/
├── backup_tool.py        # CLI entry point + interactive menu
├── core/
│   ├── backup.py         # scanning, hashing, copy vs hard-link, manifest
│   ├── restore.py        # restore + verify
│   ├── versioning.py     # list / load / prune versions
│   └── utils.py          # checksums, logging, path safety
├── tests/test_backup.py  # 20 automated test cases
├── benchmark.py          # performance evaluation (full vs incremental)
└── make_sample_data.py   # creates a demo folder
```

## 3. Installation

1. Install Python 3.8 or newer (macOS: `python3 --version` to check).
2. Unzip the project and open a terminal in the `backup_utility` folder.

No other packages are needed.

## 4. Usage

### Interactive menu
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
Runs 20 test cases (normal use, version retention, restore, corruption detection,
error handling, security). All pass.

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
