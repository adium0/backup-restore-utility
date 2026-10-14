#!/usr/bin/env python3
"""Performance evaluation: full vs incremental (hard-link) backups.

Creates a test dataset, runs a series of backups, and reports time taken,
files copied vs linked, and the REAL disk space used (counting each inode once).
Results are printed as a table and saved to benchmark_results.csv.

    python benchmark.py                 # default: 300 files
    python benchmark.py --files 1000    # bigger dataset
    python benchmark.py --files 40 --min-kb 2000 --max-kb 8000   # fewer, larger files
"""

import argparse
import csv
import os
import random
import shutil
import tempfile

from core import create_backup
from core.utils import human_size


def make_dataset(root, n_files, min_kb=10, max_kb=200, seed=42):
    rng = random.Random(seed)
    paths = []
    for i in range(n_files):
        folder = os.path.join(root, f"folder_{i % 10}", f"sub_{i % 3}")
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"file_{i}.bin")
        with open(path, "wb") as fh:
            fh.write(os.urandom(rng.randint(min_kb * 1000, max_kb * 1000)))
        paths.append(path)
    return paths


def modify_fraction(paths, fraction, seed):
    rng = random.Random(seed)
    chosen = rng.sample(paths, max(1, int(len(paths) * fraction)))
    for path in chosen:
        with open(path, "ab") as fh:
            fh.write(os.urandom(1024))
    return len(chosen)


def disk_usage(root):
    """Bytes actually used on disk: hard-linked files are counted only once."""
    seen, total = set(), 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            st = os.stat(os.path.join(dirpath, f))
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                total += st.st_size
    return total


def run_scenario(n_files, mode, min_kb, max_kb):
    work = tempfile.mkdtemp(prefix="bkp_bench_")
    try:
        src, dest = os.path.join(work, "src"), os.path.join(work, "backups")
        paths = make_dataset(src, n_files, min_kb, max_kb)
        rows = []
        steps = [("Initial backup", 0), ("No changes", 0), ("10% files changed", 0.10),
                 ("30% files changed", 0.30)]
        for i, (label, frac) in enumerate(steps):
            changed = modify_fraction(paths, frac, seed=i) if frac else 0
            res = create_backup(src, dest, keep=10, mode=mode)
            s = res["stats"]
            rows.append({
                "mode": mode, "step": label, "files_changed": changed,
                "copied": s["copied"], "linked": s["linked"], "seconds": s["seconds"],
                "data_copied_bytes": s["bytes_copied"],
                "total_disk_used_bytes": disk_usage(dest),
            })
        return rows
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--files", type=int, default=300)
    parser.add_argument("--min-kb", type=int, default=10, help="smallest file size in KB")
    parser.add_argument("--max-kb", type=int, default=200, help="largest file size in KB")
    parser.add_argument("--out", default="benchmark_results.csv")
    args = parser.parse_args()

    if not 0 < args.min_kb <= args.max_kb:
        parser.error("need 0 < --min-kb <= --max-kb")
    rows = (run_scenario(args.files, "full", args.min_kb, args.max_kb)
            + run_scenario(args.files, "incremental", args.min_kb, args.max_kb))

    print(f"\nBenchmark with {args.files} files of {args.min_kb}-{args.max_kb} KB\n")
    print(f"{'Mode':<12} {'Step':<20} {'Changed':>8} {'Copied':>7} {'Linked':>7} "
          f"{'Time (s)':>9} {'Data copied':>12} {'Disk used':>11}")
    print("-" * 92)
    for r in rows:
        print(f"{r['mode']:<12} {r['step']:<20} {r['files_changed']:>8} {r['copied']:>7} "
              f"{r['linked']:>7} {r['seconds']:>9.3f} {human_size(r['data_copied_bytes']):>12} "
              f"{human_size(r['total_disk_used_bytes']):>11}")

    full_disk = rows[3]["total_disk_used_bytes"]
    inc_disk = rows[7]["total_disk_used_bytes"]
    full_time = sum(r["seconds"] for r in rows[1:4])
    inc_time = sum(r["seconds"] for r in rows[5:8])
    print(f"\nAfter 4 versions: full mode uses {human_size(full_disk)}, "
          f"incremental uses {human_size(inc_disk)} "
          f"({100 * (1 - inc_disk / full_disk):.1f}% less storage).")
    print(f"Repeat backups took {full_time:.3f}s (full) vs {inc_time:.3f}s (incremental) "
          f"({100 * (1 - inc_time / full_time):+.1f}% time saved).")

    with open(args.out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved results to {args.out}")


if __name__ == "__main__":
    main()
