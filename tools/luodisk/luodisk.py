#!/usr/bin/env python3
"""
luodisk — Disk Usage Analyzer
by luokai | MIT License

Visual, fast, sorted disk usage explorer.
Beats `du` and `ncdu` for quick human-readable analysis.
"""

import os
import sys
import argparse
import time
from pathlib import Path
from typing import Optional

# ── ANSI ──────────────────────────────────────────────────────────────────────
R    = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"
RED  = "\033[91m"
GRN  = "\033[92m"
YLW  = "\033[93m"
CYN  = "\033[96m"
BLU  = "\033[94m"
MGN  = "\033[95m"

def c(*args):
    return "".join(args[1:]) + str(args[0]) + R

def fmt_size(b: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"

def bar(fraction: float, width: int = 20) -> str:
    filled = int(fraction * width)
    empty  = width - filled
    colour = RED if fraction > 0.8 else YLW if fraction > 0.5 else GRN
    return c("█" * filled, colour) + c("░" * empty, DIM)

# ── Disk scanning ─────────────────────────────────────────────────────────────

def scan_dir(path: Path, follow_symlinks=False) -> int:
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_symlink() and not follow_symlinks:
                    continue
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    total += scan_dir(Path(entry.path), follow_symlinks)
                else:
                    total += entry.stat(follow_symlinks=False).st_size
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total

def get_children(path: Path, follow_symlinks=False) -> list[tuple[Path, int]]:
    results = []
    try:
        for entry in os.scandir(path):
            try:
                p = Path(entry.path)
                if entry.is_symlink() and not follow_symlinks:
                    continue
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    size = scan_dir(p, follow_symlinks)
                    results.append((p, size))
                else:
                    results.append((p, entry.stat(follow_symlinks=False).st_size))
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return sorted(results, key=lambda x: x[1], reverse=True)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_analyze(args):
    root = Path(args.path).resolve()
    if not root.exists():
        print(c(f"  Not found: {root}", RED)); sys.exit(1)

    depth    = args.depth or 1
    top_n    = args.n or 20
    min_size = args.min or 0
    show_files = args.files

    print(c(f"\n  luodisk — {root}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))
    print(c("  Scanning...", DIM), end="\r")

    total = scan_dir(root) if root.is_dir() else root.stat().st_size

    def recurse(path: Path, current_depth: int, prefix: str, parent_size: int):
        if current_depth > depth:
            return
        children = get_children(path, follow_symlinks=args.links)
        shown = 0
        for child, size in children:
            if size < min_size:
                continue
            if shown >= top_n and current_depth == 1:
                remaining = len(children) - shown
                print(f"  {prefix}{c(f'... {remaining} more items', DIM)}")
                break
            shown += 1
            frac = size / max(parent_size, 1)
            icon = "📁 " if child.is_dir() else "📄 " if not args.no_icons else ""
            name = child.name + ("/" if child.is_dir() else "")
            size_str = c(fmt_size(size), BOLD)
            pct  = c(f"{frac*100:5.1f}%", DIM)
            b = bar(frac, 18)
            print(f"  {prefix}{b} {size_str:>12}  {pct}  {icon}{c(name, BOLD if child.is_dir() else '')}")
            if child.is_dir() and current_depth < depth:
                recurse(child, current_depth + 1, prefix + "  ", size)

    recurse(root, 1, "", total)

    # Mount point info
    try:
        stat = os.statvfs(root)
        total_disk = stat.f_blocks * stat.f_frsize
        free_disk  = stat.f_bavail * stat.f_frsize
        used_disk  = total_disk - free_disk
        print()
        print(c("  Mount point usage:", BOLD))
        print(f"  {bar(used_disk/max(total_disk,1), 30)} {c(fmt_size(used_disk), YLW)} used / {c(fmt_size(total_disk), GRN)} total  ({c(fmt_size(free_disk), CYN)} free)")
    except Exception:
        pass
    print()

def cmd_largest(args):
    root = Path(args.path or ".").resolve()
    n = args.n or 20
    ext_filter = args.ext

    print(c(f"\n  luodisk largest — scanning {root}", BOLD, CYN))
    print(c("  Collecting files...", DIM), end="\r")

    files = []
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            if ext_filter and p.suffix.lstrip(".").lower() != ext_filter.lstrip(".").lower():
                continue
            try:
                files.append((p, p.stat().st_size))
            except (PermissionError, OSError):
                pass

    files.sort(key=lambda x: x[1], reverse=True)
    print(c(f"  Top {min(n, len(files))} largest files in {root}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    for i, (p, size) in enumerate(files[:n], 1):
        rel = p.relative_to(root)
        print(f"  {c(i, DIM):>4}  {c(fmt_size(size), BOLD):>14}  {rel}")
    print()

def cmd_types(args):
    root = Path(args.path or ".").resolve()
    print(c(f"\n  luodisk types — scanning {root}", BOLD, CYN))

    by_ext: dict[str, list[int]] = {}
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            ext = p.suffix.lower() or "(no ext)"
            try:
                size = p.stat().st_size
                by_ext.setdefault(ext, []).append(size)
            except (PermissionError, OSError):
                pass

    if not by_ext:
        print(c("  No files found.", YLW)); return

    stats = {ext: (len(sizes), sum(sizes)) for ext, sizes in by_ext.items()}
    top = sorted(stats.items(), key=lambda x: x[1][1], reverse=True)[:args.n or 20]
    grand_total = sum(s for _, (_, s) in top)

    print(c("  " + "─" * 60, DIM))
    print(f"  {'EXT':<12}  {'FILES':>7}  {'TOTAL SIZE':>12}  {'AVG SIZE':>10}  SHARE")
    print(c("  " + "─" * 60, DIM))

    for ext, (count, total) in top:
        avg = total / max(count, 1)
        frac = total / max(grand_total, 1)
        print(f"  {c(ext, CYN):<20}  {count:>7}  {c(fmt_size(total), BOLD):>20}  {fmt_size(avg):>10}  {bar(frac, 12)} {frac*100:.1f}%")
    print()

def cmd_mounts(args):
    print(c("\n  luodisk mounts — filesystem overview", BOLD, CYN))
    print(c("  " + "─" * 70, DIM))
    print(f"  {'FILESYSTEM':<25}  {'MOUNT':<20}  {'USED':>10}  {'FREE':>10}  {'TOTAL':>10}  USAGE")
    print(c("  " + "─" * 70, DIM))

    seen = set()
    try:
        mounts_raw = Path("/proc/mounts").read_text()
    except Exception:
        mounts_raw = ""

    for line in mounts_raw.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        dev, mount = parts[0], parts[1]
        if mount in seen or not mount.startswith("/"):
            continue
        seen.add(mount)
        try:
            st = os.statvfs(mount)
            total = st.f_blocks * st.f_frsize
            free  = st.f_bavail * st.f_frsize
            used  = total - free
            if total == 0:
                continue
            frac = used / total
            print(f"  {c(dev, DIM):<33}  {c(mount, BOLD):<28}  {fmt_size(used):>10}  {c(fmt_size(free), GRN):>18}  {fmt_size(total):>10}  {bar(frac, 12)} {frac*100:.0f}%")
        except (PermissionError, OSError):
            pass
    print()

# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="luodisk",
        description=c("luodisk", BOLD, CYN) + " — Disk Usage Analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luodisk                            Analyze current directory (depth 1)
  luodisk /var                       Analyze /var
  luodisk -d 3 /home/user            Depth-3 breakdown
  luodisk -n 30 /                    Show top 30 entries
  luodisk --min 50MB /home           Only show items > 50MB
  luodisk largest /home              Top 20 largest files
  luodisk largest /home --ext py     Top 20 largest .py files
  luodisk types /project             Breakdown by file extension
  luodisk mounts                     All mounted filesystems
""",
    )
    ap.add_argument("command", nargs="?", default="analyze",
                    choices=["analyze","largest","types","mounts"])
    ap.add_argument("path", nargs="?", default=".", help="Target path")
    ap.add_argument("-d", "--depth", type=int, default=1)
    ap.add_argument("-n", type=int, help="Max entries to show")
    ap.add_argument("--min", type=lambda s: parse_size(s), help="Min size (e.g. 10MB)")
    ap.add_argument("--files", action="store_true", help="Show files in analyze mode")
    ap.add_argument("--links", action="store_true", help="Follow symlinks")
    ap.add_argument("--ext", help="Filter by extension (largest mode)")
    ap.add_argument("--no-icons", action="store_true", dest="no_icons")

    args = ap.parse_args()

    dispatch = {
        "analyze": cmd_analyze,
        "largest": cmd_largest,
        "types":   cmd_types,
        "mounts":  cmd_mounts,
    }
    dispatch[args.command](args)

def parse_size(s: str) -> int:
    s = s.strip().upper()
    units = {"B":1,"KB":1024,"MB":1024**2,"GB":1024**3,"TB":1024**4}
    for unit, mult in sorted(units.items(), key=lambda x: -len(x[0])):
        if s.endswith(unit):
            return int(float(s[:-len(unit)]) * mult)
    return int(s)

if __name__ == "__main__":
    main()
