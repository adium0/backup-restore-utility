# Project Context: Automated File Backup and Restore Utility with Version Control

**Course:** BITE303P – Operating Systems Lab · Lab Project (40 marks)
**Project folder:** `backup_utility/`
**Language:** Python 3 (standard library only, nothing to install). The GUI is a web page served by Python.
**Last updated:** 21 Oct 2026

This document is the complete hand-over context for anyone preparing the submission documents
(proposal, Review-I design report, final report, presentation). It covers what the project is,
how every part works, how to run and demo it, the testing and performance results, the OS
concepts it demonstrates, the full history of the work done so far (including bugs found and
fixed, and the reasons behind each decision), the current state of the folder, known
limitations, and a checklist for the deliverables.

---

## Contents

1. [At a glance](#1-at-a-glance)
2. [Assignment requirements (from the question paper)](#2-assignment-requirements-from-the-question-paper)
3. [The project in plain words](#3-the-project-in-plain-words)
4. [Features](#4-features)
5. [How to run everything](#5-how-to-run-everything)
6. [Architecture](#6-architecture)
7. [How it works: the algorithms](#7-how-it-works-the-algorithms)
8. [File-by-file reference](#8-file-by-file-reference)
9. [The graphical interface (GUI)](#9-the-graphical-interface-gui)
10. [The Test Lab (demonstrating problems on purpose)](#10-the-test-lab-demonstrating-problems-on-purpose)
11. [Operating-system concepts used](#11-operating-system-concepts-used)
12. [Testing](#12-testing)
13. [Performance evaluation](#13-performance-evaluation)
14. [Error handling](#14-error-handling)
15. [Known limitations and future enhancements](#15-known-limitations-and-future-enhancements)
16. [Development history (everything done so far)](#16-development-history-everything-done-so-far)
17. [Current state of the folder](#17-current-state-of-the-folder)
18. [Deliverables guide](#18-deliverables-guide)
19. [Demo scripts](#19-demo-scripts)
20. [Viva preparation](#20-viva-preparation)
21. [Glossary](#21-glossary)
22. [Environment and troubleshooting](#22-environment-and-troubleshooting)

---

## 1. At a glance

| Item | Value |
|---|---|
| What it is | A backup tool that saves timestamped **versions** of a folder and can restore any version, a whole folder or a single file |
| Key idea | Unchanged files are stored as **hard links** to the previous version, so every version looks complete but repeated backups take almost no extra disk space (the technique behind macOS Time Machine and `rsync --link-dest`) |
| Integrity | Every stored file has a **SHA-256 checksum** in a `manifest.json`; `verify` detects damaged or missing files |
| Crash safety | Each backup is built in a hidden `.inprogress_…` folder and **atomically renamed** when complete |
| Interfaces | Command line (`backup_tool.py`), terminal menu, and a browser-based GUI (`gui.py`) with a **Test Lab** that simulates corruption, deletion, crashes and an attack |
| Tests | **28 automated tests**, all passing (20 core cases TC01–TC20 + 8 Test Lab cases) |
| Measured results | Incremental mode uses **~65% less disk space** than full mode. It is **~74% faster** with large files (2–8 MB) but **~18% slower** with many small files (10–200 KB), because a hard link has a fixed cost per file |
| Main OS concepts | File systems (directory traversal, metadata, inodes, hard links, link counts, atomic rename), Linux/Unix system calls, performance analysis; also threads + mutual exclusion (GUI server), buffered I/O, data integrity, protection (path-traversal defence) |
| Size | ~3,100 lines across Python, HTML/CSS/JS and docs (core logic ≈ 470 lines) |

---

## 2. Assignment requirements (from the question paper)

Source: *Operating Systems Lab Project (40 Marks) – Project Guidelines* (QP 7). Summary:

- **Objective:** apply OS concepts to a practical problem through design, implementation,
  testing and evaluation, by building a working application, simulator, utility or framework.
- **Teams:** maximum **three** members. Contributions must be equal and can be checked
  individually during reviews and the viva.
- **Must include implementation** (not only theory) and involve one or more OS concepts from
  the list: CPU scheduling, process management, threads, synchronization, deadlocks, memory
  management, paging, **file systems**, virtual memory, shell programming, IPC, process
  monitoring, resource allocation, **Linux system programming**, device management,
  **performance analysis**, etc.
- **"Mini Command-Line Backup and Restore Utility" is explicitly listed** among the example
  project topics, so this project fits the brief exactly.
- **Deliverables:** project proposal, source code, documentation, test cases and results,
  user manual, final presentation.
- **Review I:** problem statement, objectives, literature/background, system design,
  architecture, algorithm/flowchart, module division, a working prototype with
  60–70% implemented and core functionality executable.
- **Review II:** explain the OS concepts used; complete implementation, testing, performance
  evaluation, error handling, demonstration of all features, documentation, viva.
- **General rules:** open-source libraries allowed but the core must be the team's own; proper
  code documentation and modular code; no plagiarism; **maintain version history and backups**
  (we use Git); must run during the final demo; all members present; individual viva questions.
- **VTOP uploads (4 × 10 marks):**

| Upload | Contents expected |
|---|---|
| Project Proposal Report | Problem statement, objectives, scope, literature/background, methodology, tools/software, work plan, team responsibilities |
| Project Design & Progress Report (Review I) | Architecture, module design, algorithms/flowcharts, implementation progress (40–50%), screenshots, challenges faced |
| Final Project Report | Introduction, objectives, design, implementation, testing, results, conclusion, future enhancements, references, source-code appendix (if required) |
| Final Presentation (PPT) | 15–20 slides: problem, objectives, architecture, implementation, demo, results, conclusion, Q&A |

---

## 3. The project in plain words

**Problem.** People lose files by deleting them by mistake, saving over a good version, or
through silent disk corruption. Copying a whole folder every time you back it up wastes disk
space, and a backup you have never checked might be broken when you need it.

**Solution.** A tool that takes "snapshots" of a folder over time:

- Each backup is a **version**: a folder named by date and time, e.g. `2026-10-21_19-15-16`.
- Only **new or changed** files are copied. Unchanged files get a second *name* pointing to the
  data already saved in the previous version (a **hard link**), so they cost no extra space.
  Every version still looks like a complete copy of the folder.
- Only the **last N versions** are kept (default 3); older ones are deleted automatically.
  Deleting an old version never damages newer ones, because the data is only freed when no
  version points to it any more.
- Every file's **fingerprint** (SHA-256) is recorded, so the tool can prove a restored file is
  exact and detect a damaged backup.
- You can **restore** a whole version or a single file/folder, to the original place or
  elsewhere, and it never overwrites your newer work unless you say so.

**Analogy.** A librarian archiving a shelf each week: new or edited books are photocopied into
the archive; unchanged books are not copied again; the catalogue just says "same as last
week's copy, on shelf 3". Every week's archive looks complete, with no wasted paper.

---

## 4. Features

| Feature | What it does |
|---|---|
| Timestamped backups | Each run creates a folder like `2026-10-21_19-15-16` (a `-2` suffix is added if two runs happen in the same second) |
| Incremental mode (default) | Copies only new/changed files; unchanged files are hard-linked to the previous version |
| Full mode (`--full`) | Copies every file every time (used for comparison and to start a clean chain after corruption) |
| Version retention | Keeps the newest *N* versions (default 3) and deletes the rest |
| Restore | Whole version or one file/sub-folder, to the original location or a different folder; skips identical files; won't overwrite changed files without `--overwrite` |
| Verification after restore | Each restored file is re-hashed and compared with the manifest |
| Integrity check (`verify`) | Re-hashes every stored file; reports **missing** and **corrupted** files |
| Change detection (`status`) | Lists files **added / modified / deleted** since the last backup |
| Exclusions | Always skips `.DS_Store`, `Thumbs.db`, `*.tmp`, `~$*` (Office lock files) and symbolic links; extra patterns via `--exclude` |
| Crash safety | Backups are built in `.inprogress_<name>` and renamed only when complete; leftovers are deleted on the next run |
| Logging | Every action is appended to `backup.log` in the backup folder |
| Interactive terminal menu | Run `backup_tool.py` with no arguments |
| Browser GUI | `python3 gui.py`: folder pickers, version table, file list, restore options, log viewer, Finder buttons |
| Test Lab (in the GUI) | Buttons that edit/delete/add files, corrupt or delete stored files, simulate a crash, run a path-traversal attack, and show inode numbers and link counts |
| Benchmark | `benchmark.py` measures time, data copied and real disk usage for full vs incremental |
| Safety checks | Refuses a backup location inside the source folder; refuses restoring into the backup location; rejects manifest paths that escape the target folder (`../`) |

---

## 5. How to run everything

**Requirements:** Python 3.8+ (developed and tested on the Python 3.9.6 that ships with Apple's
Command Line Tools on macOS 26.5.2). No packages to install. Works on macOS and Linux; the
command line also works on Windows (hard links work on NTFS). The GUI's "Choose…" and "Open"
buttons are macOS-only; elsewhere you type paths.

Always start in the project folder (the quotes matter because the parent folder name has a space):

```bash
cd "/Users/adityamendiratta/Documents/os project/backup_utility"
```

### Command line

```bash
python3 make_sample_data.py                                   # create the demo folder sample_data/
python3 backup_tool.py backup sample_data my_backups          # create a backup (keep 3 by default)
python3 backup_tool.py backup sample_data my_backups --keep 5 --full --exclude "*.log"
python3 backup_tool.py list my_backups                        # list versions
python3 backup_tool.py status sample_data my_backups          # added / modified / deleted since last backup
python3 backup_tool.py restore my_backups                     # restore latest into the original folder
python3 backup_tool.py restore my_backups --only Projects/hello.py
python3 backup_tool.py restore my_backups --version 2026-10-21_19-15-16 --only Documents/notes.txt --overwrite
python3 backup_tool.py restore my_backups --target ~/Desktop/recovered
python3 backup_tool.py verify my_backups [--version NAME]     # check for corruption
python3 backup_tool.py                                        # interactive numbered menu
```

Exit codes: 0 success; 1 for errors, a restore with failed files, or a verify that found
problems; 130 if cancelled with Ctrl+C.

### GUI

```bash
python3 gui.py                 # opens http://127.0.0.1:8765 in your browser
python3 gui.py --port 9000     # different port
python3 gui.py --no-browser    # only print the address
```

Keep the terminal open while using it; press **Ctrl+C** there to stop. If port 8765 is busy
(for example a second copy is already running), the OS picks a free port and the address
printed in the terminal changes. If the page says the program isn't running, start it again;
if it says the page belongs to an earlier run, reload the page (Cmd+R).

### Tests and benchmark

```bash
python3 -m unittest discover -s tests -v                       # 28 tests
python3 benchmark.py                                           # 300 files of 10–200 KB
python3 benchmark.py --files 40 --min-kb 2000 --max-kb 8000    # 40 files of 2–8 MB
python3 benchmark.py --out results_large.csv                   # choose the CSV name
```

---

## 6. Architecture

```
                  ┌───────────────────────────────────────────┐
   User ────────▶ │ backup_tool.py  (CLI + terminal menu)     │
     │            └───────────┬───────────────────────────────┘
     │   browser              │
     └──────▶ web/ ──HTTP──▶ gui.py (local web server) ──┐  demo_tools.py (Test Lab)
                              │                         │        │
                ┌─────────────▼─────────┐   ┌───────────▼────────▼──┐
                │ core/backup.py        │   │ core/restore.py       │
                │ scan → hash →         │   │ read manifest →       │
                │ copy or hard-link →   │   │ copy back → verify    │
                │ manifest → rename     │   │ checksum; verify()    │
                └─────────────┬─────────┘   └───────────┬───────────┘
                              │                         │
                ┌─────────────▼─────────────────────────▼───────────┐
                │ core/versioning.py  list / load / prune / cleanup │
                │ core/utils.py       SHA-256, logging, path safety │
                └─────────────────────────┬─────────────────────────┘
                                          ▼
                 OS file system: os.walk, os.stat, os.link, shutil.copy2, os.rename
```

### Project structure

```
backup_utility/
├── backup_tool.py          # CLI entry point + interactive menu (237 lines)
├── gui.py                  # GUI: local web server on 127.0.0.1 + JSON API (420)
├── web/
│   ├── index.html          # the GUI page: tabs, forms, tables (186)
│   ├── style.css           # light/dark theme, responsive layout (204)
│   └── app.js              # browser logic: calls the API, renders results (423)
├── core/                   # the actual backup engine
│   ├── __init__.py         # exports the public functions (17)
│   ├── backup.py           # scanning, hashing, copy vs hard-link, manifest, status (203)
│   ├── restore.py          # restore + verify (89)
│   ├── versioning.py       # list / load / prune versions, crash cleanup (99)
│   └── utils.py            # SHA-256, logging, timestamps, path safety (65)
├── demo_tools.py           # Test Lab: cause problems on purpose (218)
├── make_sample_data.py     # creates the demo folder sample_data/ (31)
├── benchmark.py            # full vs incremental performance evaluation (121)
├── tests/
│   ├── test_backup.py      # 20 test cases TC01–TC20 (213)
│   └── test_demo_tools.py  # 8 Test Lab test cases (99)
├── README.md               # user manual
├── IMPLEMENTATION_GUIDE.md # build order, team split, test table, viva Qs, 2-day plan
├── PROJECT_CONTEXT.md      # this document
└── .gitignore              # ignores sample_data/, my_backups/, __pycache__/, benchmark CSV, .DS_Store
```

### What a backup folder looks like on disk

```
my_backups/
├── 2026-10-21_19-15-16/          ← version 1: real copies + manifest.json
│   ├── Documents/notes.txt
│   ├── Photos/holiday.jpg
│   ├── Projects/hello.py
│   └── manifest.json
├── 2026-10-21_19-16-02/          ← version 2: changed files copied, the rest hard-linked
│   └── …same tree…
├── .inprogress_2026-…/           ← only exists during a backup or after a crash
└── backup.log                    ← one line per action
```

### manifest.json (the record card of one version)

Example, shortened: checksums truncated, only 2 of the 5 files shown.

```json
{
  "name": "2026-10-21_19-16-02",
  "created": "2026-10-21T19:16:02.123456",
  "source": "/Users/…/backup_utility/sample_data",
  "mode": "incremental",
  "based_on": "2026-10-21_19-15-16",
  "files": {
    "Documents/notes.txt": {"size": 80, "mtime": 1792590962.41, "sha256": "a3f9…", "stored": "copied"},
    "Projects/hello.py":   {"size": 36, "mtime": 1792590916.02, "sha256": "7c1e…", "stored": "linked"}
  },
  "skipped": [{"file": ".DS_Store", "reason": "excluded"}, {"file": "temp_file.tmp", "reason": "excluded"}],
  "errors": [],
  "stats": {"copied": 1, "linked": 4, "bytes_copied": 80, "bytes_linked": 150119,
            "files": 5, "skipped": 2, "errors": 0, "seconds": 0.0047}
}
```

A folder counts as a version **only if it contains `manifest.json`**. The manifest is written
last, just before the atomic rename, so its presence means "this backup finished".

### backup.log

Example of the format:

```
[2026-10-21T19:15:16] BACKUP 2026-10-21_19-15-16 mode=incremental files=5 copied=5 linked=0 errors=0 time=0.0083s
[2026-10-21T19:16:02] BACKUP 2026-10-21_19-16-02 mode=incremental files=5 copied=1 linked=4 errors=0 time=0.0047s
[2026-10-21T19:16:40] RESTORE 2026-10-21_19-16-02 -> …/sample_data restored=1 skipped=0 failed=0
[2026-10-21T19:16:55] VERIFY 2026-10-21_19-16-02 OK ok=5 missing=0 corrupted=0
[2026-10-21T19:17:30] CLEANUP removed incomplete backup .inprogress_…_crashed
[2026-10-21T19:17:30] PRUNE removed old version 2026-10-21_19-15-16
```

---

## 7. How it works: the algorithms

### 7.1 Backup (`core/backup.py → create_backup`)

```
procedure BACKUP(source, dest, keep, mode)
    check: source exists; dest is not inside source; mode is full|incremental; keep ≥ 1
    remove any leftover .inprogress_* folders                     (crash recovery)
    prev ← manifest of the latest version, only if it backed up the same source (incremental only)
    work ← dest/.inprogress_<timestamp>
    for each regular file f in os.walk(source), skipping excluded names and symlinks
        st ← os.stat(f)
        if prev has f with the same size and mtime then h ← prev[f].sha256   (fast path: no re-read)
        else h ← SHA256(f)                                                     (read in 64 KB blocks)
        if prev has f and prev[f].sha256 = h then
            os.link(prev_version/f, work/f)       (hard link; if the FS refuses, fall back to copy)
        else
            shutil.copy2(f, work/f)               (copy; keeps timestamps and permission bits)
        manifest[f] ← {size, mtime, h, stored: copied|linked}
        (an unreadable file is recorded in "errors" and the backup continues)
    write manifest.json into work
    os.rename(work, dest/<timestamp>)             (atomic: the version appears all at once)
    delete the oldest versions until only `keep` remain
    append a BACKUP line to backup.log
```

**Copy-or-link decision for each file:**

| Situation | Result |
|---|---|
| First backup, or full mode | Copy |
| File not in previous version (new) | Copy |
| Same size and mtime as previous version | Reuse previous checksum → identical → Link |
| Size or mtime changed, content identical (e.g. "touched") | Re-hash → identical → Link |
| Content changed | Re-hash → different → Copy |
| Hard link fails (e.g. FAT32/exFAT USB drive) | Copy instead |

### 7.2 Restore (`core/restore.py → restore_backup`)

```
procedure RESTORE(dest, version, target, only, overwrite)
    m ← manifest of version (latest if none given)
    target ← target or m.source (the original folder)
    refuse if target is inside the backup location
    selected ← all files, or only the file / sub-folder named by `only`
    for each file f in selected
        src ← safe_join(version_folder, f); dst ← safe_join(target, f)   (rejects "../" escapes)
        if dst exists and SHA256(dst) = m[f].sha256 → skip "already up to date"
        if dst exists and not overwrite             → skip "exists (use overwrite)"
        create parent folders; shutil.copy2(src, dst)   (always a real copy, never a link)
        if SHA256(dst) ≠ m[f].sha256 → report "checksum mismatch after restore"
    append a RESTORE line to backup.log
```

Restored files are **real copies**, not hard links. Otherwise editing a restored file would
silently change the data stored in the backup too (test TC11).

### 7.3 Verify (`core/restore.py → verify_backup`)

For every file in the manifest: not present → **missing**; present but SHA-256 differs →
**corrupted**; otherwise OK. Logs `VERIFY … OK` or `VERIFY … PROBLEMS`.

### 7.4 Status (`core/backup.py → changes_since_backup`)

Set difference between the files in the folder now and the files in the latest manifest:
**added** = now − manifest; **deleted** = manifest − now; **modified** = in both and (size
differs, or mtime differs *and* the SHA-256 differs). A file that was only re-saved without
changes is not reported.

### 7.5 Retention (`core/versioning.py → prune_old_backups`)

Versions are sorted by the manifest's `created` time (microsecond precision, more exact than
the folder name). Everything except the newest `keep` is removed with `shutil.rmtree`. This is
safe with hard links: deleting a folder removes **names**; the inode's data is freed only when
its **link count** reaches 0, so files still referenced by newer versions survive (TC06).

### 7.6 Crash recovery (`core/versioning.py → clean_incomplete`)

At the start of every backup, any `.inprogress_*` folder (a backup that never reached its
rename) is deleted and a `CLEANUP` line is logged. Such folders are never listed as versions
because they start with `.` and have no manifest (TC20).

### 7.7 Path safety (`core/utils.py → is_inside, safe_join`)

`is_inside(child, parent)` resolves both paths with `realpath` (following `..` and symlinks)
and checks `commonpath`. `safe_join(base, rel)` joins and normalises a manifest path and raises
an error if the result is outside `base`. This blocks a tampered manifest containing
`../../evil.txt` from writing outside the restore folder (TC19, and the Test Lab attack).

---

## 8. File-by-file reference

### `core/utils.py` – shared helpers
- Constants: `MANIFEST_NAME = "manifest.json"`, `LOG_NAME = "backup.log"`,
  `TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"`, `IN_PROGRESS_PREFIX = ".inprogress_"`,
  `CHUNK_SIZE = 64 KB`.
- `BackupError`: the one exception type for user-facing problems; the CLI and GUI turn it into a
  clean message instead of a traceback.
- `sha256_of(path)`: reads in 64 KB blocks, so memory use is constant for any file size.
- `human_size(n)`: `150000` → `146.5 KB` (1024-based).
- `now_stamp()`: version names; sortable, and avoids `:` (not allowed in Windows file names).
- `log_event(root, msg)`: appends a timestamped line to `backup.log`.
- `is_inside(child, parent)`, `safe_join(base, rel)`: path-safety checks (section 7.7).

### `core/backup.py` – making backups
- `DEFAULT_EXCLUDES = [".DS_Store", "Thumbs.db", "*.tmp", "~$*"]`.
- `_is_excluded(rel, patterns)`: `fnmatch` on the file name or the relative path.
- `scan_source(source, excludes)`: `os.walk` with sorted traversal; returns files to back up
  and skipped items (with reason "excluded" or "symbolic link").
- `_unique_name(root)`: timestamp name, adding `-2`, `-3`… on collision.
- `create_backup(source, backup_root, keep=3, mode="incremental", excludes=None)`: section 7.1.
  Returns name, path, previous version, stats, skipped, errors, and pruned versions.
- `changes_since_backup(source, backup_root, name=None)`: section 7.4.

### `core/restore.py` – restoring and verifying
- `restore_backup(backup_root, name=None, target=None, only=None, overwrite=False, verify=True)`:
  section 7.2. Returns lists of restored, skipped (with reason) and failed (with error) files.
- `verify_backup(backup_root, name=None)`: section 7.3. Returns ok count and missing/corrupted lists.

### `core/versioning.py` – managing versions
- `_snapshot_names(root)`: folders that are finished versions (have a manifest, don't start with `.`).
- `load_manifest(root, name)`: reads one manifest, or raises "No backup named …".
- `list_backups(root)`: summaries sorted oldest → newest by `created`.
- `latest_backup(root)`: newest name or `None`.
- `resolve_name(root, name)`: turns `None`/`"latest"` into a real name; errors if there are no
  backups or the name is unknown.
- `prune_old_backups(root, keep)`: section 7.5. `clean_incomplete(root)`: section 7.6.

### `core/__init__.py`
Makes `core` a package and re-exports `BackupError`, `create_backup`, `changes_since_backup`,
`restore_backup`, `verify_backup`, `list_backups`, `latest_backup`, `prune_old_backups`.

### `backup_tool.py` – command line and terminal menu
- `argparse` sub-commands `backup`, `restore`, `list`, `verify`, `status`, `menu`; each maps to
  a 2–3 line handler that calls `core` and a `print_*` helper.
- `print_backup_result`, `print_backup_list`, `print_restore_result`, `print_verify_result`,
  `print_status`: formatting only (the GUI reuses them to show the same text).
- `interactive_menu()`: numbered options 1–6; remembers folders between choices; catches errors.
- `main()`: no arguments → menu; catches `BackupError` (exit 1) and Ctrl+C (exit 130).

### `make_sample_data.py`
Creates `sample_data/` with `Documents/notes.txt`, `Documents/report_draft.txt`,
`Projects/hello.py`, `Projects/config.json`, `Photos/holiday.jpg` (150 KB of random bytes,
different on every run), plus two junk files that must be skipped: `.DS_Store` and `temp_file.tmp`.

### `benchmark.py`
Generates a random dataset (`--files`, `--min-kb`, `--max-kb`), then for **full** and
**incremental** mode runs four backups: *initial*, *no changes*, *10% of files changed*,
*30% changed* (`keep=10` so nothing is pruned). Records files copied/linked, time, bytes copied
and **real disk usage** (each `(device, inode)` counted once, so hard links aren't double
counted). Prints a table and writes `benchmark_results.csv` (or `--out`).

### `demo_tools.py` – Test Lab tools
See section 10. Separate from `core/` on purpose: the real engine never damages anything.

### `gui.py` and `web/` – the GUI
See section 9.

### `tests/test_backup.py`, `tests/test_demo_tools.py`
See section 12.

---

## 9. The graphical interface (GUI)

### Why a browser page instead of a desktop window

A desktop window built with Tkinter was tried first and **does not work on this Mac**: the
Python that ships with macOS uses Apple's old Tk 8.5.9, which on macOS 26 (a) made its text
widget spin the CPU and leak memory (≈3.2 GB within a minute), and (b) after that was worked
around, drew a completely **blank window** with no buttons or fields. The options were to
install a newer Python via Homebrew (`python-tk@3.13`), or build the GUI as a web page served
by Python's built-in `http.server`. The browser approach was chosen: it needs nothing installed,
works on any machine (including the examiner's), and could be tested visually. (Details in
section 16.)

### How it works

```
browser page (web/app.js)
   │  POST /api/backup  {"source": …, "dest": …, "keep": 3, "full": false}
   │  header X-Token: <secret>
   ▼
gui.py  Handler.do_POST  ──▶  api_backup()  ──▶  core.create_backup()
   │                              │
   │◀── JSON {"ok": true, "text": "✔ Backup created: …"} ◀─ formatted with backup_tool.print_backup_result
   ▼
page shows the text in Output and reloads the version table, file list and log
```

- **Server:** `ThreadingHTTPServer` bound to **127.0.0.1** (this computer only), port 8765 by
  default (falls back to a free port if busy). Opens the browser automatically.
- **Threads:** every request is handled in its own thread, so the page stays responsive.
- **Mutual exclusion:** a `threading.Lock` (`WORK_LOCK`) lets only one operation that touches
  the backup folder run at a time (backup, status, restore, verify, all Test Lab actions that
  modify files). A second one is refused with "Another operation is still running" instead of
  racing the first. The lock is acquired non-blocking.
- **Security:**
  1. listens on 127.0.0.1 only;
  2. checks the `Host` header is `127.0.0.1:<port>` or `localhost:<port>` (defends against DNS rebinding);
  3. a random token (`secrets.token_urlsafe(16)`, new each start) is injected into the page
     and must be sent in an `X-Token` header with every API call. Other websites can't read
     our page, so they can't get the token and can't trigger a restore (CSRF protection);
  4. only three static files (`index.html`, `style.css`, `app.js`) are ever served.
- **Responses:** `200` with `{"ok": true, …}`; user errors (`BackupError`) → `400` with
  `{"ok": false, "error": …}`; unexpected errors → `500`; bad token/host → `403`; unknown route → `404`.
- **Folder picker:** "Choose…" runs a small AppleScript (`choose folder`) via `osascript` and
  returns the chosen path (Cancel → no change). If you choose a backup location that already
  contains other files, the page offers to use a `my_backups` subfolder instead.
- **Finder:** "Open"/"Show in Finder" run `open <folder>`.

### API routes (all `POST /api/<name>`)

| Route | Lock | Purpose |
|---|---|---|
| `config` | – | Defaults: pre-fills `sample_data/` and `my_backups/` if present, keep=3, default excludes, whether pickers are available |
| `versions` | – | Version list for the table |
| `version_files` | – | Every file in one version (size, copied/linked, modified) |
| `files` | – | Paths in a version, for "Only this file" suggestions |
| `log` | – | Lines of `backup.log` |
| `pick` | – | Native macOS folder chooser |
| `reveal` | – | Open a folder in Finder |
| `source_files` | – | Files in the source folder (Test Lab dropdown) |
| `backup`, `status`, `restore`, `verify` | ✔ | The four main operations |
| `lab_edit`, `lab_delete_source`, `lab_add` | ✔ | Test Lab: change the source folder |
| `lab_corrupt`, `lab_delete_backup`, `lab_crash`, `lab_attack` | ✔ | Test Lab: damage a backup |
| `lab_links` | – | Test Lab: inode / link-count report |
| `lab_sample`, `lab_reset` | ✔ | Create sample data / delete demo folders and start fresh |

### What the page contains

- **Folders card:** "Folder to back up" and "Backup location", each with **Choose…** and **Open**.
- **Backup tab:** versions to keep, extra skip patterns, Full backup checkbox,
  **Create Backup**, **Show Changes Since Last Backup**.
- **Versions & Restore tab:**
  - **version table:** number, name, mode, files, size, copied, linked, with a "latest" tag;
    click a row to select it, and click again or "use latest" to clear;
  - **Refresh**, **Verify Selected**;
  - **Files in …** table of every stored file, with **Show in Finder**; clicking a row fills
    "Only this file";
  - **Restore** options: Restore into (blank = original folder), Only this file or folder
    (with suggestions), Overwrite (asks for confirmation).
- **Log tab:** contents of `backup.log`.
- **Test Lab tab:** section 10.
- **Output panel:** every result, time-stamped, in the same format as the terminal; ✔ green,
  errors/✘/! red; auto-scrolls to the newest result; identical errors from one click are merged.
- **Status bar:** spinner and last status.
- Light/dark theme follows the system; layout works down to phone width.

---

## 10. The Test Lab (demonstrating problems on purpose)

A GUI tab backed by `demo_tools.py`. Each action returns a report that says what happened and
**which button to press next** to show the tool reacting. Destructive actions ask for
confirmation.

| Button | What it does | What to show next | OS concept |
|---|---|---|---|
| **Edit file** | Appends a line to a source file (only files present in the latest backup) | *Show Changes* lists it as modified; *Create Backup* copies 1 file, links the rest | Metadata (size/mtime), incremental backup |
| **Delete file** | Deletes a source file (only if it's in the latest backup, so it can always be restored) | *Restore* with "Only this file" brings it back | Recovery |
| **Add a new file** | Creates `new_file_<time>.txt` | *Show Changes* lists it as added | Change detection |
| **Corrupt file (flip 1 byte)** | Flips one byte in the middle of a stored file (size unchanged, like bit rot); reports which versions share that inode | *Verify* reports CORRUPTED, in **every** version that hard-links that data; repair with a **Full backup** | Data integrity, shared inodes |
| **Delete file from backup** | Removes one version's copy (its name) | *Verify* reports MISSING in that version only; other versions still have it (link count drops by 1) | Link counts |
| **Simulate a crash mid-backup** | Leaves `.inprogress_<time>_crashed` with a half-written file and no manifest | It isn't listed as a version; next *Create Backup* deletes it (`CLEANUP` in Log) | Atomic rename, crash consistency |
| **Try a path-traversal attack** | Plants `../../evil_demo.txt` in a manifest, attempts a restore into a temp folder, checks nothing was written outside, then **restores the original manifest** | Report ends "✔ Attack blocked by safe_join()" | Protection/security |
| **Show inode numbers & link counts** | For one file: version, inode number, link count, copied/linked, checksum OK/CORRUPTED | Same inode in several versions = one copy of the data | Inodes, hard links |
| **Create sample data** | (Re)creates `sample_data/` next to `gui.py` | Create Backup | – |
| **Reset demo (start fresh)** | Deletes `sample_data/` and `my_backups/` next to `gui.py`, recreates sample data and an empty `my_backups/` | Create Backup | – |

Example inode report:

```
Hard links for Projects/hello.py
  Version                        Inode  Links  Stored  Checksum
  2026-10-21_18-57-08         14973651      2  copied  OK
  2026-10-21_18-57-09         14973651      2  linked  OK
  -> 2 version(s) contain this file, using 1 separate copy of the data on disk.
```

---

## 11. Operating-system concepts used

Mapped to the question paper's list.

| Concept (QP list) | How strongly | Where / how |
|---|---|---|
| **File Systems** | Core concept | Directory traversal (`os.walk`); file metadata (`os.stat`: size, mtime, inode, link count); **inodes and hard links** (`os.link`); **link counting** (safe pruning); **atomic rename** for crash consistency (`os.rename`); copying with metadata (`shutil.copy2`); FAT32/exFAT lack hard links → fallback |
| **Linux System Programming** | Strong | Direct use of POSIX system calls through Python: `stat`, `link`, `rename`, `mkdir`, `unlink`, `readdir`, `open/read/write` |
| **Performance Analysis** | Strong | `benchmark.py`: time, data copied, real disk usage; space/time trade-off; the per-file cost of `link()` explains when incremental is faster (section 13) |
| **Thread Programming** | Moderate (GUI) | `ThreadingHTTPServer`: one thread per request |
| **Synchronization** | Moderate (GUI) | `threading.Lock` for mutual exclusion over the backup folder; non-blocking acquire avoids waiting |
| Memory Management | Minor | Buffered I/O in 64 KB blocks: constant memory regardless of file size |
| Resource Allocation | Minor | Storage management via retention (keep N) and data sharing via hard links |
| Device Management | Minor | Detects file systems without hard-link support and falls back to copying |
| *(Protection & security)* | Notable | SHA-256 integrity checks; path-traversal defence; localhost-only server with token and Host checks |
| Process Management | Minor | GUI starts child processes (`osascript`, `open`) via `subprocess`; the server process outlives the browser tab |
| Not used | – | CPU scheduling, deadlocks, paging, virtual memory, IPC, process monitoring, shell programming |

**Key explanations for the report and viva:**

- **Inode & hard link:** on APFS/ext4 a file's data and metadata live in an *inode*; a file name
  is just a directory entry pointing to it. `os.link` adds another name for the same inode (no
  data copied). The inode keeps a **link count**; data is freed only when it reaches 0. This is
  why deleting an old version never damages newer ones. Visible with `ls -li`: same inode
  number, link count 2.
- **Why not hard-link to the source files?** Editing the source would then silently change the
  backup. Links are made only between backup versions, which are never edited.
- **Atomic rename:** `rename()` within one file system is atomic: the version folder either
  fully exists or not at all. Databases and package managers use the same pattern.
- **SHA-256 vs mtime:** mtime can be preserved or changed by tools; a checksum proves the
  content. Size+mtime is only a fast pre-check, as rsync does.

---

## 12. Testing

Run: `python3 -m unittest discover -s tests -v` → **Ran 28 tests … OK.** Each test uses fresh
temporary folders.

### Core test cases (`tests/test_backup.py`)

| ID | Test | Expected result | Status |
|---|---|---|---|
| TC01 | First backup | All files copied, manifest created | Pass |
| TC02 | Second backup, nothing changed | 0 copied, all hard-linked, same inode | Pass |
| TC03 | One file modified | Only that file copied | Pass |
| TC04 | Full mode | Every file copied | Pass |
| TC05 | 5 backups with keep=3 | Only 3 versions remain | Pass |
| TC06 | Delete an old version that a newer one links to | Newer version still verifies OK | Pass |
| TC07 | Restore to a new folder | Checksums identical to the original | Pass |
| TC08 | Restore older version of an overwritten file | Old content returned | Pass |
| TC09 | Restore a deleted file | File recreated | Pass |
| TC10 | Restore without `--overwrite` over a changed file | File left untouched, reported as skipped | Pass |
| TC11 | Edit a restored file | Backup not affected (restored files are real copies) | Pass |
| TC12 | Tamper with / delete a stored file | `verify` reports corrupted / missing | Pass |
| TC13 | `status` after add, modify, delete | All three detected | Pass |
| TC14 | `.DS_Store` and `*.tmp` present | Skipped | Pass |
| TC15 | Source folder missing | Error message | Pass |
| TC16 | Backup folder inside source | Refused | Pass |
| TC17 | Unknown version name | Error message | Pass |
| TC18 | Restore when no backups exist | Error message | Pass |
| TC19 | Manifest contains `../../evil.txt` | Rejected, nothing written outside target | Pass |
| TC20 | Leftover `.inprogress_` folder | Cleaned up on next run | Pass |

### Test Lab test cases (`tests/test_demo_tools.py`)

These prove that every simulated problem is caught by the real code.

| ID | Test | Expected result | Status |
|---|---|---|---|
| TL01 | Edit + add file in source | `status` reports modified and added | Pass |
| TL02 | Delete a source file, then restore | File is back | Pass |
| TL03 | Try deleting a file that isn't backed up | Refused; file untouched | Pass |
| TL04 | Corrupt a file shared by two versions | `verify` reports it corrupted in **both** versions | Pass |
| TL05 | Delete a stored file from one version | Missing in that version, other version still OK | Pass |
| TL06 | Crash leftover | Not listed as a version; removed by next backup | Pass |
| TL07 | Path-traversal attack | Blocked; manifest restored byte-for-byte | Pass |
| TL08 | Inode report | One shared inode, appears in both versions | Pass |

### Manual / end-to-end testing done

- The full CLI demo script (section 19) was run end-to-end: hard links showed the same inode
  with link count 2; restore, verify and the error cases behaved correctly.
- The GUI was tested by clicking through every tab and button in a browser on a scratch copy:
  backup → show changes → incremental backup (1 copied, 4 linked) → select version → restore a
  deleted file → verify OK → corrupt → verify CORRUPTED (red) → full backup → verify OK →
  crash → backup (CLEANUP logged) → attack (blocked) → reset. Also checked: light and dark
  mode, phone width (no horizontal scrolling), error messages, auto-scroll, and the "program
  not running" and "page from an earlier run" messages.
- GUI server tested with scripts: every route, missing token → 403, wrong Host → 403, request
  for a non-whitelisted file → 404, and a second operation while the lock is held → refused.
- macOS folder picker: the AppleScript was run for real with a path containing a space and
  confirmed to open and wait for the user without error.

---

## 13. Performance evaluation

### Method
`benchmark.py` creates a dataset, then runs four backups per mode (*initial*, *no changes*,
*10% changed*, *30% changed*) with `keep=10`. Measured: time per backup, data copied, and real
disk usage counting each inode once. Machine: MacBook Air, macOS 26.5.2, APFS SSD, Python 3.9.6.
Timings vary between runs and machines; disk-space results are deterministic.

### Results: 300 files of 10–200 KB (≈29 MB) – `python3 benchmark.py`

| Mode | Step | Changed | Copied | Linked | Time (s) | Data copied | Disk used |
|---|---|---|---|---|---|---|---|
| full | Initial | 0 | 300 | 0 | 0.078 | 29.4 MB | 29.5 MB |
| full | No changes | 0 | 300 | 0 | 0.077 | 29.4 MB | 59.0 MB |
| full | 10% changed | 30 | 300 | 0 | 0.082 | 29.5 MB | 88.5 MB |
| full | 30% changed | 90 | 300 | 0 | 0.071 | 29.5 MB | 118.1 MB |
| incremental | Initial | 0 | 300 | 0 | 0.070 | 29.4 MB | 29.5 MB |
| incremental | No changes | 0 | 0 | 300 | 0.095 | 0 B | 29.5 MB |
| incremental | 10% changed | 30 | 30 | 270 | 0.091 | 2.3 MB | 32.0 MB |
| incremental | 30% changed | 90 | 90 | 210 | 0.092 | 8.9 MB | 40.9 MB |

After 4 versions: **118.1 MB vs 40.9 MB → 65.3% less storage.** The three repeat backups
took 0.230 s (full) vs 0.278 s (incremental) in this run → **incremental 20.7% slower**; a
second run gave 0.237 s vs 0.281 s (18.5% slower, the figure used in the README).

### Results: 40 files of 2–8 MB (≈181 MB) – `python3 benchmark.py --files 40 --min-kb 2000 --max-kb 8000`

| Mode | Step | Changed | Copied | Linked | Time (s) | Data copied | Disk used |
|---|---|---|---|---|---|---|---|
| full | Initial | 0 | 40 | 0 | 0.128 | 180.7 MB | 180.7 MB |
| full | No changes | 0 | 40 | 0 | 0.105 | 180.7 MB | 361.4 MB |
| full | 10% changed | 4 | 40 | 0 | 0.096 | 180.7 MB | 542.1 MB |
| full | 30% changed | 12 | 40 | 0 | 0.096 | 180.7 MB | 722.8 MB |
| incremental | Initial | 0 | 40 | 0 | 0.094 | 180.7 MB | 180.7 MB |
| incremental | No changes | 0 | 0 | 40 | 0.015 | 0 B | 180.7 MB |
| incremental | 10% changed | 4 | 4 | 36 | 0.023 | 17.5 MB | 198.2 MB |
| incremental | 30% changed | 12 | 12 | 28 | 0.039 | 54.8 MB | 253.0 MB |

After 4 versions: **722.8 MB vs 253.0 MB → 65.0% less storage.** Repeat backups: 0.296 s vs
0.077 s → **incremental 73.8% faster.**

### Crossover: repeat backup of an unchanged folder (best of 3)

| Dataset | Full | Incremental | Incremental vs full |
|---|---|---|---|
| 300 files × 100 KB | 0.071 s | 0.089 s | 26% slower |
| 100 files × 1 MB | 0.065 s | 0.029 s | 55% faster |
| 40 files × 5 MB | 0.099 s | 0.012 s | 88% faster |

### Interpretation (important for the report)
- **Storage savings are consistent (~65%)** at every file size: unchanged files cost zero extra bytes.
- **Time savings depend on file size.** Profiling showed `os.link()` costs ≈ **0.29 ms per file**
  on APFS (86 ms of a 100 ms run for 300 links), because creating a link is a journaled
  metadata update: write a directory entry and increment the inode's link count. Copying a
  small file that is already in the OS page cache costs about the same, so for many small files
  incremental mode is slightly slower. Copy time grows with file size while link time doesn't,
  so for files of about 1 MB and up incremental mode is much faster.
- The original README claimed "77.8% faster" for the 300-small-file case; that did **not**
  reproduce on this Mac and was corrected. Use the measured numbers above.

### Suggested graphs for the report
1. Disk used after each step: full vs incremental (both datasets); full grows linearly,
   incremental only grows by the changed data.
2. Data copied per step (bar chart).
3. Time per repeat backup vs file size (crossover table) to show the fixed per-link cost.

`benchmark_results.csv` (ignored by Git) holds the raw numbers; regenerate with the commands above.

---

## 14. Error handling

| Situation | Behaviour |
|---|---|
| Source folder doesn't exist | Clear error, exit code 1 (TC15) |
| Backup location inside the source folder | Refused: it would back up its own backups forever (TC16) |
| Unknown version / no backups yet | Clear error (TC17, TC18) |
| A file can't be read (permissions, deleted mid-backup, disk error) | Recorded in the manifest's `errors`; the rest of the backup continues |
| Restore would overwrite a changed file | Skipped unless `--overwrite` (TC10) |
| Restored file's checksum doesn't match | Reported as failed: "checksum mismatch after restore" |
| Restore target is the backup location (or inside it) | Refused, naming both folders |
| Tampered manifest with `../` paths | Rejected: "Unsafe path in manifest" (TC19) |
| Backup interrupted (Ctrl+C, crash, power loss) | Only `.inprogress_…` exists; removed on the next run (TC20) |
| File system without hard links (FAT32/exFAT) | Falls back to copying |
| `--keep` < 1, invalid mode | Clear error |
| GUI: program not running / page from an older run | Explicit message saying how to fix it |
| GUI: two operations at once | Second one refused until the first finishes |
| GUI: chosen backup location already has other files | Offers a `my_backups` subfolder |

---

## 15. Known limitations and future enhancements

Honest limitations, useful for the "limitations / future work" sections and likely viva questions:

1. **Corruption can propagate in incremental mode.** If a stored file is damaged but the
   source file's size and mtime are unchanged, the next incremental backup reuses the stored
   checksum and hard-links to the damaged copy (verified experimentally). **Remedy:** after
   `verify` reports problems, run a `--full` backup (copies everything fresh). The GUI's verify
   output says this. Possible enhancement: skip linking to files `verify` has flagged, or
   periodically re-hash link targets.
2. **Shared damage.** Because unchanged files share one inode, corrupting one stored copy damages
   every version that links to it. This is inherent to hard-link deduplication (Time Machine
   has the same trade-off).
3. **Size+mtime shortcut.** A change that keeps the same size and mtime (rare, e.g. tools that
   preserve timestamps) is not re-hashed in incremental mode.
4. **Restore leaves a bad copy in place on checksum mismatch.** The file is copied, then
   checked; on mismatch it is reported as failed but not deleted.
5. **Empty folders are not backed up** (only files are recorded); symbolic links are skipped
   on purpose.
6. **Ownership/ACLs are not preserved** (`copy2` keeps timestamps and permission bits only).
7. **"Automated" is manual today:** nothing schedules backups. Enhancement: a scheduler
   (cron/launchd on macOS/Linux, Task Scheduler on Windows) or a watch mode.
8. **No compression or encryption** of stored data; no remote/cloud target.
9. **GUI pickers are macOS-only** (AppleScript); other systems type paths. The GUI serves one
   local user; it is not meant to be exposed on a network.
10. **Single-threaded backup engine.** Enhancement: hash/copy files in parallel (thread pool),
    which would also add a new benchmark.
11. **Version names have one-second resolution** (a `-2` suffix handles collisions; ordering uses
    the microsecond `created` time).

Other enhancement ideas: block-level deduplication (rsync-style deltas), restore preview/diff,
per-file version history, email/notification on failures, CLI command for the inode report.

---

## 16. Development history (everything done so far)

The base code (core engine, CLI, 20 tests, benchmark, sample data, README, implementation
guide) already existed when this phase of work started; the files had been moved from
`~/Downloads/backup_utility` to `~/Documents/os project/backup_utility`. The work below was
done with Claude Code (an AI coding assistant) at the user's request.

### 14 Oct 2026 – verification, benchmark correction, Git
1. Read all files and followed the implementation guide's steps.
2. Ran the 20 tests: **all pass**.
3. Ran the full demo script in a scratch copy: incremental backup copied 1 and linked 4; `ls -li`
   showed the same inode with link count 2; restore, verify and the three error cases worked; log correct.
4. Ran the benchmark: storage saving matched the README (65.3%) but **incremental was slower**
   (−20.7%), contradicting the README's "77.8% faster". Profiled: 86 ms of 100 ms spent in
   `os.link` (~0.29 ms/link on APFS). Measured the crossover by file size (section 13).
5. Added `--min-kb/--max-kb` (with validation) to `benchmark.py`, so both regimes can be shown.
6. Updated README (measured results and explanation; fixed an example that listed 2 copied +
   4 linked for a 5-file folder) and the implementation guide (corrected the "~78% time" claim,
   added viva question 6). Added `.DS_Store` to `.gitignore`.
7. `git init` and the first commit **`8432f60`** ("Backup utility: core modules, CLI, tests,
   benchmark, docs"). It was committed with the machine's global Git identity (`adium0`) and
   carries a `Co-Authored-By: Claude` trailer.

### 14–15 Oct – explanations for the team (no code changes)
Plain-language walkthroughs of the project and every file (`backup_tool.py`,
`make_sample_data.py`, `core/__init__.py`, `backup.py`, `restore.py`, `utils.py`,
`versioning.py`), how to read `ls -li` (inode number, link count), how to open the log, and a
step-by-step demo for the professor.

### 15 Oct – corruption behaviour investigated
Question: "how do I restore a corrupted file?" Tested and found:
- the damage is inside the backup, not the user's folder;
- restoring from a corrupted version reports "checksum mismatch after restore";
- an incremental backup taken after the corruption **inherits** the damage if the source file
  is unchanged (it hard-links to the damaged copy), whereas a **`--full` backup repairs it**.
  This is documented as limitation 1.

### 15 Oct – mapped the project to the question paper (QP 7)
Section 11 above. Noted: the topic is a listed example; gaps were "Automated" (no scheduling),
team of up to 3 (the guide splits for 2), and the document deliverables.

### 15 Oct – GUI attempt 1: Tkinter (abandoned)
1. Built a Tkinter desktop GUI. A scripted test that pressed every button passed, but the user
   reported it "doesn't seem to be working".
2. Investigation: the running window used 75% CPU and **3.2 GB of memory after one minute**.
   Isolated it by measuring each widget separately: even an empty `tk.Text` widget leaked on
   Apple's Tk 8.5.9 + macOS 26. Replaced it with a `Listbox` (0% CPU, steady memory).
3. The user then sent a screenshot: the **window was blank** (Tk 8.5.9 can't draw widgets on
   macOS 26). The earlier scripted test had only checked results, not what was visible.
4. Decision (user's choice): rebuild as a **browser GUI** served by Python, rather than install
   Homebrew Python with a newer Tk.

### 15 Oct – GUI attempt 2: browser-based (current)
1. Wrote `gui.py` (ThreadingHTTPServer, JSON API, token, Host check, lock) and `web/`
   (`index.html`, `style.css`, `app.js`).
2. Tested every API route and the security checks with a script, then clicked through the real
   page in a browser: backup, show changes, incremental backup, versions table, restore,
   verify (including a tampered file shown in red), log, error cases, light/dark, phone width.
3. Fixes found while testing: results appeared below the visible area (now auto-scrolls), a
   stray "0" badge (CSS `[hidden]` override), squeezed path boxes on narrow screens.

### 21 Oct – folder picker bug
"Choose…" failed with `Can't set kind to "folder" (-10006)`. Cause: the AppleScript used a
variable named `kind`, a reserved word in AppleScript. Earlier it had only been compiled, not
run. Fixed (renamed variables, removed an unused file-picker branch) and verified by running the
logic with a path containing a space and by opening the real dialog.

### 21 Oct – Test Lab
Added `demo_tools.py`, the Test Lab tab, 11 new API routes, and `tests/test_demo_tools.py`
(8 tests; 28 total). Clicked through the full corrupt → verify → full-backup repair loop, and
every other button, in a browser. Tidied report text.

### 21 Oct – usability fixes from real use
1. "Can't reach the backup program": the server had been stopped. Made the message say how to
   start it again; merged duplicate errors from one click; added "page belongs to an earlier
   run, reload" for a restarted server (token mismatch → 403).
2. Two GUI copies were running (the second took a random port): explained, and stopped the extra one.
3. "Showing the older version": the user's real `my_backups` only had their own Oct 15
   backups; all of the assistant's testing happened in scratch copies, deliberately.
4. **Backup location set to the project folder** (picked with Choose… after Reset demo, when
   `my_backups` didn't exist): backups landed next to the code, and restoring into that same
   folder was refused. Fixes:
   - the picker offers a `my_backups` subfolder when the chosen folder has other files;
   - Reset demo creates an empty `my_backups`;
   - clearer restore error naming the folders;
   - duplicate-error merging limited to 3 seconds, so a user's retry always shows a result;
   - the misplaced backup was moved into `my_backups`.
5. Added **"Files in this version"** table (click a row to restore that file), **Show in
   Finder**, and **Open** buttons for both folders.

---

## 17. Current state of the folder

**As of 21 Oct 2026, ~19:40:**

- **All 28 tests pass.** The CLI and GUI work as described.
- **Git:** two commits on branch `main`:
  - `8432f60` – core modules, CLI, tests, benchmark, docs (14 Oct);
  - "Add browser GUI, Test Lab, file viewer and project context doc" – browser GUI, Test Lab,
    file viewer, clearer restore error, this document (21 Oct).

  The stray `Documents/` folder (below) was deliberately left out. Uploading to GitHub:
  create an empty repository on github.com, then
  `git remote add origin git@github.com:<account>/<repo>.git` and `git push -u origin main`.
  This Mac's SSH key is already linked to the GitHub account `adium0`.
- **Stray files from GUI experiments (safe to delete; review first):**
  - `backup_utility/Documents/report_draft.txt`: a restore that went into the project folder.
  - `os project/2026-10-21_18-51-44/` and `os project/backup.log` (in the **parent** folder):
    a backup made while the backup location was set to `os project`.
- **Demo folders:** `sample_data/` is freshly generated; `my_backups/` is currently **empty**
  (a Reset demo was run). Run one backup before demonstrating.
- **GUI server:** not running. Start with `python3 gui.py`.
- **Duplicate guide:** `os project/IMPLEMENTATION_GUIDE.md` (parent folder) is a copy of
  `backup_utility/IMPLEMENTATION_GUIDE.md`; the one inside `backup_utility/` is the one to use.
- **Course-policy note:** the guidelines require the core implementation to be the team's own
  and allow individual viva questions. This project was developed with AI assistance (the
  commit carries a co-author trailer). Decide as a team how to disclose that according to
  your course's policy, and make sure every member can explain every module (sections 7–11).

---

## 18. Deliverables guide

Where to find content for each upload in this document:

| Deliverable | Use sections |
|---|---|
| **Project Proposal Report** | Problem & motivation (§3), objectives (below), scope (§4, §15), background/literature (below), methodology (§7), tools (§22), work plan & responsibilities (below and `IMPLEMENTATION_GUIDE.md`) |
| **Design & Progress Report (Review I)** | Architecture (§6), module design (§8), algorithms/flowcharts (§7), implementation progress (§16), screenshots (list below), challenges (§16: benchmark discrepancy, Tk failures, AppleScript, folder mix-up) |
| **Final Project Report** | Everything: introduction (§3), objectives, design (§6–9), implementation (§8–10), testing (§12), results (§13), error handling (§14), OS concepts (§11), conclusion, future enhancements (§15), references (below), source appendix (the `.py`/`web` files) |
| **Final Presentation** | Slide outline below |
| **User manual** | `README.md` (+ §5, §9, §10 here) |
| **Test cases and results** | §12 |
| **Source code** | the `backup_utility/` folder (commit first) |

### Suggested objectives
1. Create versioned, timestamped backups of a folder with configurable retention.
2. Minimise storage with hard-link-based incremental backups, and quantify the saving.
3. Guarantee integrity with SHA-256 checksums: verify backups and every restored file.
4. Restore whole versions or single files safely (no unintended overwrites, no path escapes).
5. Make backups crash-safe using an atomic rename.
6. Provide CLI, menu and GUI interfaces with clear error handling and logging.
7. Evaluate performance (time and space) of full vs incremental strategies.

### Background / literature pointers (for the references section)
- **rsync** `--link-dest` and **rsnapshot**: hard-link snapshot backups (the same technique).
- **Apple Time Machine**: hard-link snapshots on HFS+; APFS snapshots today.
- **Inodes, hard links, link counts**: any OS textbook file-system chapter (e.g. Silberschatz,
  *Operating System Concepts*; Tanenbaum, *Modern Operating Systems*).
- **POSIX `rename()` atomicity**: the POSIX specification / Linux man pages `rename(2)`, `link(2)`, `stat(2)`.
- **SHA-256**: FIPS 180-4 (Secure Hash Standard).
- **Path traversal**: OWASP "Path Traversal" (CWE-22).
- **ZFS/Btrfs** block checksums for integrity, as related work.
- Python docs: `os`, `shutil`, `hashlib`, `http.server`, `threading`, `argparse`, `unittest`.

### Team split (from `IMPLEMENTATION_GUIDE.md`, written for 2 members)
| Member A – Backup & Versioning | Member B – Restore, Interface & Testing |
|---|---|
| `core/utils.py`, `core/backup.py`, `core/versioning.py`, `benchmark.py` | `core/restore.py`, `backup_tool.py`, `tests/test_backup.py`, `README.md` + demo |

The newer parts (`gui.py`, `web/`, `demo_tools.py`, `tests/test_demo_tools.py`) are not
assigned yet. With a **third member** (teams of up to 3 are allowed), a natural split is
**Member C – GUI & Test Lab**. Each member must be able to explain their modules and the
overall flow in the viva.

### Screenshots to capture
1. CLI: first backup (5 copied, 2 skipped), second backup (1 copied, 4 linked).
2. `ls -li my_backups/*/Projects/hello.py`: same inode, link count 2.
3. CLI `list`, `status`, `restore --only`, `verify` (healthy and corrupted).
4. Error messages (missing source, backup inside source).
5. `python3 -m unittest discover -s tests -v` showing 28 OK.
6. Benchmark tables (both datasets) and the graphs made from the CSV.
7. GUI: each tab (Backup, Versions & Restore with Files table, Log, Test Lab), a red
   corrupted verify, the inode report, and the blocked attack report.
8. Terminal menu (`python3 backup_tool.py`).

### Presentation outline (≈17 slides)
1. Title & team · 2. Problem statement · 3. Objectives · 4. Background (Time Machine, rsync,
inodes) · 5. Architecture diagram · 6. Modules & team split · 7. Backup algorithm (flowchart)
· 8. Hard links & link counts (diagram + `ls -li`) · 9. Atomic rename & crash safety ·
10. Restore & integrity (SHA-256, path safety) · 11. Interfaces (CLI, GUI) · 12. Test Lab ·
13. Testing (28 cases) · 14. Performance results (graphs) · 15. OS concepts mapping ·
16. Limitations & future work · 17. Conclusion / Q&A (+ live demo).

---

## 19. Demo scripts

### Command-line demo (≈5 minutes)

```bash
cd "/Users/adityamendiratta/Documents/os project/backup_utility"
rm -rf sample_data my_backups                                  # clean start
python3 -m unittest discover -s tests -v                       # 28 tests pass
python3 make_sample_data.py
python3 backup_tool.py backup sample_data my_backups           # 5 copied, 2 junk files skipped
echo "new line" >> sample_data/Documents/notes.txt
python3 backup_tool.py status sample_data my_backups           # notes.txt modified
python3 backup_tool.py backup sample_data my_backups           # 1 copied, 4 hard-linked
ls -li my_backups/*/Projects/hello.py                          # same inode, link count 2
python3 backup_tool.py list my_backups
rm sample_data/Projects/hello.py                               # "accidental" delete
python3 backup_tool.py restore my_backups --only Projects/hello.py
python3 backup_tool.py restore my_backups --version "$(ls my_backups | grep ^2 | head -1)" --only Documents/notes.txt --overwrite
python3 backup_tool.py verify my_backups
echo "hacked" >> "$(ls -d my_backups/2* | tail -1)/Documents/notes.txt"
python3 backup_tool.py verify my_backups                       # reports corrupted
python3 backup_tool.py backup sample_data my_backups --full    # repair: clean chain
python3 backup_tool.py verify my_backups                       # OK again
python3 backup_tool.py backup nothing_here my_backups          # clear error
python3 backup_tool.py backup sample_data sample_data/backups  # refused
python3 benchmark.py --files 40 --min-kb 2000 --max-kb 8000    # performance
cat my_backups/backup.log
```

### GUI demo (Test Lab order)

1. `python3 gui.py` → Test Lab → **Reset demo** → Backup tab → **Create Backup** twice.
2. Test Lab → **Show inode numbers** for `Projects/hello.py`: same inode, link count 2.
3. **Edit file** → **Show Changes** → **Create Backup** (1 copied).
4. **Delete file** → Versions & Restore → click it in **Files in …** → **Restore**.
5. **Corrupt file** → **Verify Selected** (red; all versions sharing the inode are damaged)
   → tick **Full backup** → **Create Backup** → **Verify** OK.
6. **Simulate a crash** → **Create Backup** → Log tab shows `CLEANUP`.
7. **Try a path-traversal attack** → "✔ Attack blocked".
8. **Show in Finder** to show the real version folders on disk.

---

## 20. Viva preparation

1. **Hard link vs symbolic link?** A hard link is another name for the same inode: the data
   survives deleting the original name, and it only works on the same file system. A symlink is
   a small file containing a path and breaks if the target moves. We skip symlinks in the
   source and use hard links between backup versions.
2. **Why not hard-link to the source files?** Editing the source would silently change the backup.
3. **Why SHA-256 instead of only mtime?** mtime can be preserved or changed by tools; a checksum
   proves the content. Size+mtime is only a fast pre-check.
4. **What happens if power fails mid-backup?** The `.inprogress_` folder is never renamed, so it's
   ignored and deleted on the next run. Older versions are untouched (atomic rename).
5. **Why no space saving on a USB stick?** FAT32/exFAT don't support hard links; the tool falls
   back to copying.
6. **Why is incremental sometimes slower for small files?** `link()` is a metadata operation with
   a fixed cost per file (directory entry, link count, journaling), about 0.29 ms here. Copying a
   cached 50 KB file costs about the same; linking wins on time only for larger files, but
   always wins on space.
7. **Why is deleting an old version safe?** Deleting removes names; the inode's data is freed only
   when its link count reaches 0, and newer versions still link to it.
8. **What if a backup file gets corrupted?** `verify` detects it via SHA-256. Every version sharing
   that inode is affected; a `--full` backup creates a clean chain (limitation 1).
9. **How do you stop a malicious manifest writing outside the folder?** `safe_join` resolves the
   path and refuses anything outside the base folder (CWE-22 path traversal).
10. **What is atomic about `rename`?** Within one file system the directory entry changes in
    one step; observers see either the old name or the new name, never a half state.
11. **Where are threads and synchronization used?** The GUI server handles each request in a
    thread; a mutex lets only one backup/restore run at a time.
12. **Why does memory stay constant for huge files?** Hashing reads in 64 KB blocks (buffered I/O).
13. **How is the GUI secured?** Localhost-only, Host-header check, a per-run secret token on every
    request, and only three static files are served.
14. **Why a browser GUI?** Apple's bundled Tk 8.5 can't draw widgets on current macOS; the web
    approach uses only the standard library and works everywhere.

---

## 21. Glossary

| Term | Meaning |
|---|---|
| **Version / snapshot** | One backup run, stored as a folder named by date and time |
| **Incremental backup** | Copies only new/changed files; unchanged ones are hard-linked to the previous version |
| **Full backup** | Copies every file regardless of changes |
| **Inode** | The file-system record holding a file's data location and metadata |
| **Hard link** | An additional directory entry (name) pointing to an existing inode |
| **Link count** | Number of names pointing to an inode; data is freed at 0 |
| **Symbolic link (symlink)** | A file containing a path to another file (skipped by this tool) |
| **Manifest** | `manifest.json`: list of every file in a version with size, mtime, SHA-256, copied/linked |
| **SHA-256** | Cryptographic hash used as a file "fingerprint"; any change gives a different value |
| **mtime** | Last-modified time of a file |
| **Atomic rename** | A rename that happens entirely or not at all |
| **Retention / pruning** | Keeping only the newest N versions |
| **Path traversal** | An attack using `../` to escape a directory |
| **Mutex / lock** | Mutual exclusion: only one thread may hold it at a time |
| **Bit rot** | Silent corruption of stored data over time |

---

## 22. Environment and troubleshooting

**Development machine:** MacBook Air, macOS 26.5.2 (Darwin 25.5.0), APFS SSD; Python 3.9.6
(Apple Command Line Tools, `/usr/bin/python3`); Tk 8.5.9 (unusable for GUIs on this macOS);
Git 2.50.1; Homebrew installed but not needed; tested in Brave/Chromium.

**Tools/software used:** Python standard library only (`os`, `shutil`, `hashlib`, `json`,
`argparse`, `unittest`, `http.server`, `threading`, `subprocess`, `secrets`), HTML/CSS/vanilla
JavaScript for the GUI, AppleScript (`osascript`) for the macOS folder picker, Git for version history.

| Problem | Fix |
|---|---|
| `python3: command not found` | Install Python 3 (python.org); on Windows use `python` |
| `can't open file 'gui.py'` | You're in the wrong folder; `cd` into `backup_utility` first |
| GUI page: "program isn't running" | Start `python3 gui.py` again (keep the terminal open) |
| GUI page: "belongs to an earlier run" | Reload the page (Cmd+R) |
| Address shows a port other than 8765 | Another copy is already running; stop it (Ctrl+C) or use the address printed |
| Backups landed in the wrong folder | Check "Backup location" ends with `/my_backups`; move version folders + `backup.log` into it if needed |
| "Can't restore into … backup location" | Clear "Restore into" (restores to the original folder) or pick a different folder |
| Permission denied on Desktop/Documents (macOS) | Allow Terminal in System Settings → Privacy & Security → Full Disk Access, or use a folder in your home directory |
| External drive copies everything each time | Drive is FAT32/exFAT (no hard links); format as APFS/ext4/NTFS |
| A Tkinter window appears blank | Expected with macOS's built-in Python; the project's GUI is the browser one (`gui.py`) |
