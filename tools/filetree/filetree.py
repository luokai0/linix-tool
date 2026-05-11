#!/usr/bin/env python3
"""
filetree — Directory tree visualizer
Show beautiful tree of any directory with filtering, size, and stats

Usage:
  python3 filetree.py tree [path] [depth]     -- show tree
  python3 filetree.py find <path> <pattern>    -- find files matching pattern
  python3 filetree.py size <path>             -- show size of dirs
  python3 filetree.py stats <path>            -- file type statistics
  python3 filetree.py du <path>               -- disk usage top-down
"""

import sys
import os
from pathlib import Path
from collections import Counter


def build_tree(root: str, max_depth: int = 3, prefix: str = '', show_hidden: bool = False) -> None:
    root_path = Path(root)
    try:
        entries = sorted(root_path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return

    dirs = [e for e in entries if e.is_dir() and (show_hidden or not e.name.startswith('.'))]
    files = [e for e in entries if e.is_file() and (show_hidden or not e.name.startswith('.'))]

    for i, entry in enumerate(dirs + files):
        is_last = i == len(dirs) + len(files) - 1
        branch = '└── ' if is_last else '├── '
        size = entry.stat().st_size if entry.is_file() else ''
        size_str = f"  ({size // 1024}KB)" if isinstance(size, int) and size > 0 else ''
        print(f"{prefix}{branch}{entry.name}{size_str}")

        if entry.is_dir() and entry.name not in ('__pycache__', '.git', 'node_modules', '.venv'):
            deeper = prefix + ('    ' if is_last else '│   ')
            build_tree(entry, max_depth - 1, deeper, show_hidden)


def find_files(root: str, pattern: str) -> list[str]:
    matches = []
    for path in Path(root).rglob(pattern):
        matches.append(str(path))
    return matches


def dir_size(path: str) -> int:
    return sum(f.stat().st_size for f in Path(path).rglob('*') if f.is_file())


def show_sizes(root: str, top_n: int = 20) -> list[tuple[str, int]]:
    sizes = []
    for entry in Path(root).iterdir():
        if entry.is_dir():
            sizes.append((entry.name, dir_size(entry)))
    sizes.sort(key=lambda x: x[1], reverse=True)
    for name, size in sizes[:top_n]:
        mb = size / (1024 * 1024)
        bar = '█' * min(int(mb), 50)
        print(f"  {mb:7.1f}MB  {bar}  {name}")
    return sizes


def file_stats(path: str) -> dict:
    counter = Counter()
    total = 0
    for f in Path(path).rglob('*'):
        if f.is_file():
            ext = f.suffix or 'no-ext'
            sz = f.stat().st_size
            counter[ext] += 1
            total += sz
    print(f"\n  Total files: {sum(counter.values())}")
    print(f"  Total size:  {total / (1024**2):.1f} MB\n")
    for ext, count in counter.most_common(15):
        print(f"  {count:5d}  {ext}")
    return dict(counter)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'tree':
        path = sys.argv[2] if len(sys.argv) > 2 else '.'
        depth = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        print(f"{path}/")
        build_tree(path, depth)
    elif cmd == 'find' and len(sys.argv) >= 4:
        for f in find_files(sys.argv[2], sys.argv[3]):
            print(f)
    elif cmd == 'size' and len(sys.argv) >= 3:
        show_sizes(sys.argv[2])
    elif cmd == 'stats' and len(sys.argv) >= 3:
        file_stats(sys.argv[2])
    elif cmd == 'du' and len(sys.argv) >= 3:
        path = sys.argv[2]
        print(f"Disk usage for: {path}\n")
        show_sizes(path)
    else:
        print(__doc__)