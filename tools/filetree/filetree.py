#!/usr/bin/env python3
"""
filetree — Directory tree visualizer + finder + size analyzer
Beats tree, fd, find, and ncdu combined — all in one pure Python tool.

Usage:
  filetree tree   [path] [-d N] [-a] [-f] [--hidden] [--exclude PAT] [--sort SIZE|TIME|NAME|EXT]
  filetree find   [path] <pattern> [-t TYPE] [-i]           regex search, type filter
  filetree size   [path] [-n N] [--min N] [--depth N]       biggest dirs with ASCII bars
  filetree stats  [path]                                    file type distribution
  filetree watch  [path] [-t SEC]                           live file monitor
  filetree diff   <dir1> <dir2>                             compare two dirs
  filetree json   [path]                                     output as JSON
  filetree flat   [path]                                     one file per line, full paths
  filetree dupes  [path]                                     find duplicate files by hash
"""

import sys
import os
import re
import json
import time
import hashlib
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

# ─── Color terminals ──────────────────────────────────────────
BOLD = '\033[1m'
CYAN = '\033[36m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
MAGENTA = '\033[35m'
RED = '\033[31m'
BLUE = '\033[34m'
DIM = '\033[2m'
RESET = '\033[0m'

COLORS = {
    'dir': CYAN,
    'file': RESET,
    'exe': GREEN,
    'link': MAGENTA,
    'img': YELLOW,
    'vid': YELLOW,
    'arc': RED,
    'doc': BLUE,
    'code': GREEN,
    'conf': DIM,
    'default': RESET,
}

def col(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"

def color_file(name: str, is_dir: bool, is_link: bool) -> str:
    if is_link:
        return col(name, COLORS['link'])
    if is_dir:
        return col(name, COLORS['dir'])
    ext = Path(name).suffix.lower()
    if ext in ('.py', '.js', '.ts', '.go', '.rs', '.c', '.cpp', '.h', '.java', '.rb', '.php'):
        return col(name, COLORS['code'])
    if ext in ('.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.ico', '.webp'):
        return col(name, COLORS['img'])
    if ext in ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm'):
        return col(name, COLORS['vid'])
    if ext in ('.zip', '.tar', '.gz', '.bz2', '.xz', '.rar', '.7z', '.deb', '.rpm'):
        return col(name, COLORS['arc'])
    if ext in ('.md', '.txt', '.pdf', '.doc', '.docx', '.odt', '.rtf'):
        return col(name, COLORS['doc'])
    if ext in ('.sh', '.bash', '.zsh', '.fish', '.ps1', '.bat', '.cmd'):
        return col(name, COLORS['exe'])
    if ext in ('.conf', '.cfg', '.ini', '.yaml', '.yml', '.toml', '.json', '.xml'):
        return col(name, COLORS['conf'])
    return col(name, COLORS['file'])

# ─── Core walker ──────────────────────────────────────────────
def walk_dir(root: str, max_depth: int = 999, exclude: list = None,
             include_hidden: bool = False, follow_links: bool = False,
             follow_ignores: bool = True):
    """Recursively walk a directory, yielding (path, is_dir, size, mtime, depth)."""
    exclude = exclude or []
    try:
        entries = list(Path(root).iterdir())
    except PermissionError:
        return
    except OSError:
        return

    # Sort: dirs first, then alphabetically
    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))

    for entry in entries:
        if not include_hidden and entry.name.startswith('.'):
            continue
        if any(re.match(e.replace('*', '.*'), entry.name) for e in exclude):
            continue

        is_link = entry.is_symlink()
        if is_link and not follow_links:
            yield str(entry), False, 0, 0, 0, True
            continue

        try:
            if is_link and follow_links:
                target = entry.resolve()
                is_dir = target.is_dir()
                size = 0 if is_dir else target.stat().st_size
                mtime = target.stat().st_mtime
            else:
                is_dir = entry.is_dir()
                size = 0 if is_dir else entry.stat().st_size
                mtime = entry.stat().st_mtime
        except (PermissionError, OSError):
            size, mtime = 0, 0

        depth = str(entry.parent).count(os.sep) - str(root).count(os.sep)
        yield str(entry), is_dir, size, mtime, depth, is_link

        if is_dir and depth < max_depth:
            # Skip __pycache__, .git, node_modules by default
            skip_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.venv',
                         'dist', 'build', '.pytest_cache', '.mypy_cache', 'target', '.next'}
            if follow_ignores and entry.name in skip_dirs:
                yield f"{str(entry)}/  {col('[skipped]', DIM)}", True, 0, 0, depth + 1, False
                continue
            yield from walk_dir(str(entry), max_depth, exclude, include_hidden, follow_links, follow_ignores)


# ─── TREE command ─────────────────────────────────────────────
def cmd_tree(args):
    path = args.path or '.'
    depth = args.depth or 999
    sort = args.sort or 'NAME'
    asc = not args.reverse  # default NAME is A-Z

    # Pre-load everything
    items = list(walk_dir(path, depth, args.exclude, args.hidden, args.follow))
    if not items:
        return

    # Separate dirs and files for sorting
    dirs = [(p, d, s, m, dep, lnk) for p, d, s, m, dep, lnk in items if d and not lnk]
    links = [(p, d, s, m, dep, lnk) for p, d, s, m, dep, lnk in items if lnk]
    files = [(p, d, s, m, dep, lnk) for p, d, s, m, dep, lnk in items if not d and not lnk]

    sort_key_map = {
        'NAME': lambda x: Path(x[0]).name.upper(),
        'SIZE': lambda x: x[2],
        'TIME': lambda x: x[3],
        'EXT': lambda x: Path(x[0]).suffix.upper(),
    }
    sk = sort_key_map.get(sort.upper(), sort_key_map['NAME'])
    rev = args.reverse if sort != 'NAME' else not asc

    dirs.sort(key=sk, reverse=rev)
    files.sort(key=sk, reverse=rev)

    # Build tree
    lines = []
    last_items = {}

    def format_size(s):
        if s < 1024: return f"{s}B"
        elif s < 1024**2: return f"{s/1024:.1f}K"
        elif s < 1024**3: return f"{s/1024**2:.1f}M"
        else: return f"{s/1024**3:.1f}G"

    for p, is_dir, size, mtime, dep, is_link in sorted(dirs + files + links,
            key=lambda x: (x[4], sort_key_map.get(sort.upper(), lambda a: Path(a[0]).name.upper())(x))):

        name = Path(p).name
        if not name:
            name = p  # root
        rel = Path(p).relative_to(path) if p != path else Path(p).name
        if str(rel) == path:
            rel = Path(p).name

        indent = '│   ' * dep
        entry_name = color_file(name, is_dir, is_link)

        size_str = ""
        if not is_dir and size > 0 and args.sizes:
            size_str = "  " + col(f"[{format_size(size)}]", DIM)

        if is_link:
            try:
                target = os.readlink(p)
                entry_name += f" {col(f'-> {target}', DIM)}"
            except OSError:
                pass

        if args.quiet:
            lines.append(str(p))
        else:
            if dep == 0:
                lines.append(f"{BOLD}{entry_name}{RESET}{size_str}")
            else:
                lines.append(f"{indent}└── {entry_name}{size_str}")

    for line in lines:
        print(line)

    # Stats footer
    n_dirs = len(dirs)
    n_files = len(files)
    total_size = sum(s for _, _, s, _, _, _ in files)
    print(f"\n{DIM}{n_dirs} directories, {n_files} files, {format_size(total_size)} total{RESET}")


# ─── FIND command ─────────────────────────────────────────────
def cmd_find(args):
    path = args.path or '.'
    pattern = re.compile(args.pattern, re.I if args.ignore_case else 0)
    ftype = args.type  # 'f', 'd', 'l'
    max_depth = args.depth or 999
    count_only = args.count
    max_results = args.limit or 0

    results = []
    for p, is_dir, size, mtime, dep, is_link in walk_dir(path, max_depth,
                                                           args.exclude, args.hidden, args.follow):
        if dep > max_depth:
            continue
        name = Path(p).name
        if not pattern.search(name):
            continue
        if ftype == 'd' and not is_dir:
            continue
        if ftype == 'f' and (is_dir or is_link):
            continue
        if ftype == 'l' and not is_link:
            continue

        if args.name_only:
            print(name)
        elif args.full_path:
            print(p)
        else:
            rel = Path(p).relative_to(path) if p.startswith(path) else p
            col_name = color_file(name, is_dir, is_link)
            if is_link:
                try:
                    target = os.readlink(p)
                    print(f"{col_name}  {col(f'-> {target}', DIM)}")
                except OSError:
                    print(col_name)
            else:
                print(col_name)
        results.append(p)
        if max_results and len(results) >= max_results:
            break

    if count_only:
        print(f"\n{DIM}{len(results)} matches{RESET}")


# ─── SIZE command ─────────────────────────────────────────────
def cmd_size(args):
    path = args.path or '.'
    min_mb = args.min_mb or 0
    top_n = args.top or 20
    depth = args.depth or 1

    dir_sizes = {}

    for p, is_dir, size, mtime, dep, _ in walk_dir(path, depth, args.exclude, args.hidden, args.follow):
        if not is_dir:
            continue
        try:
            total = sum(
                f.stat().st_size
                for f in Path(p).rglob('*')
                if f.is_file() and not f.is_symlink()
            )
        except (PermissionError, OSError):
            total = 0
        if total >= min_mb * 1024 * 1024:
            dir_sizes[p] = total

    sorted_dirs = sorted(dir_sizes.items(), key=lambda x: x[1], reverse=True)[:top_n]
    if not sorted_dirs:
        print("No directories found matching criteria.")
        return

    max_sz = sorted_dirs[0][1]
    grand_total = sum(s for _, s in sorted_dirs)

    for p, sz in sorted_dirs:
        name = Path(p).name or p
        mb = sz / (1024 ** 2)
        pct = (sz / grand_total * 100) if grand_total else 0
        bar_len = max(1, int((sz / max_sz) * 40))
        bar = '█' * bar_len + '░' * (40 - bar_len)
        print(f"  {mb:8.2f}MB  {col(bar, CYAN)}  {col(name, COLORS['dir'])}  {col(f'({pct:.1f}%)', DIM)}")

    print(f"\n{DIM}Total: {grand_total/(1024**2):.2f}MB in {len(sorted_dirs)} directories{RESET}")


# ─── STATS command ─────────────────────────────────────────────
def cmd_stats(args):
    path = args.path or '.'
    counter = Counter()
    total_size = 0
    total_files = 0

    for p, is_dir, size, mtime, dep, is_link in walk_dir(path, 999, args.exclude, args.hidden):
        if is_dir or is_link:
            continue
        ext = Path(p).suffix.lower() or 'no-ext'
        counter[ext] += 1
        total_size += size
        total_files += 1

    print(f"\n  {BOLD}Total files:{RESET} {total_files}  {BOLD}Total size:{RESET} {total_size/(1024**2):.2f} MB\n")
    print(f"  {BOLD}{'Count':>8}  {'Size':>10}  {'Pct':>6}  Extension{RESET}")

    sorted_ext = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    ext_sizes = defaultdict(int)
    for p, is_dir, size, mtime, dep, _ in walk_dir(path, 999, args.exclude, args.hidden):
        if is_dir or is_link: continue
        ext_sizes[Path(p).suffix.lower() or 'no-ext'] += size

    for ext, count in sorted_ext[:args.top or 20]:
        sz = ext_sizes[ext]
        pct = (sz / total_size * 100) if total_size else 0
        bar_len = max(1, int((count / sorted_ext[0][1]) * 30))
        bar = '▓' * bar_len
        print(f"  {count:8d}  {sz/(1024**2):9.2f}MB  {pct:5.1f}%  {bar}  {col(ext, COLORS['arc'] if ext in ('.zip','.tar','.gz') else COLORS['file'])}")

    # Date range
    mtimes = [m for p, _, _, m, _, _ in walk_dir(path, 999, args.exclude, args.hidden)
              if m and not Path(p).is_dir()]
    if mtimes:
        print(f"\n  {DIM}Oldest: {datetime.fromtimestamp(min(mtimes))}  Newest: {datetime.fromtimestamp(max(mtimes))}{RESET}")


# ─── WATCH command ─────────────────────────────────────────────
def cmd_watch(args):
    path = args.path or '.'
    interval = args.interval or 2
    shown = set()

    print(f"{DIM}Watching {path}... Ctrl+C to stop{RESET}\n")
    try:
        while True:
            for p, is_dir, _, _, dep, _ in walk_dir(path, 1, [], args.hidden):
                if p not in shown:
                    prefix = '  ' * dep
                    if is_dir:
                        print(f"{prefix}{col('+ ', GREEN)}{color_file(Path(p).name, True, False)}")
                    else:
                        print(f"{prefix}{col('  ', YELLOW)}{color_file(Path(p).name, False, False)}")
                    shown.add(p)
            time.sleep(interval)
    except KeyboardInterrupt:
        pass


# ─── DIFF command ─────────────────────────────────────────────
def cmd_diff(args):
    d1 = Path(args.dir1)
    d2 = Path(args.dir2)

    def build_index(root, max_depth=999):
        idx = {}
        for p, is_dir, _, _, dep, is_link in walk_dir(str(root), max_depth, [], True):
            if dep == 0:
                continue
            rel = str(Path(p).relative_to(root))
            idx[rel] = (is_dir, is_link, p)
        return idx

    idx1 = build_index(d1)
    idx2 = build_index(d2)

    only1 = set(idx1) - set(idx2)
    only2 = set(idx2) - set(idx1)
    common = set(idx1) & set(idx2)

    if only1:
        print(f"\n{BOLD}{RED}Only in {d1}:{RESET}")
        for p in sorted(only1):
            is_dir, is_link, _ = idx1[p]
            print(f"  {col('-', RED)} {color_file(p, is_dir, is_link)}")

    if only2:
        print(f"\n{BOLD}{GREEN}Only in {d2}:{RESET}")
        for p in sorted(only2):
            is_dir, is_link, _ = idx2[p]
            print(f"  {col('+', GREEN)} {color_file(p, is_dir, is_link)}")

    if common and not args.brief:
        print(f"\n{DIM}Common: {len(common)} items{RESET}")


# ─── JSON command ─────────────────────────────────────────────
def cmd_json(args):
    path = args.path or '.'
    out = []
    for p, is_dir, size, mtime, dep, is_link in walk_dir(path, args.depth or 999,
                                                           args.exclude, args.hidden):
        item = {
            'path': p,
            'name': Path(p).name,
            'is_dir': is_dir,
            'is_link': is_link,
            'size': size,
            'mtime': mtime,
        }
        if is_link:
            try:
                item['link_target'] = os.readlink(p)
            except OSError:
                pass
        out.append(item)
    print(json.dumps(out, indent=2))


# ─── FLAT command ──────────────────────────────────────────────
def cmd_flat(args):
    path = args.path or '.'
    for p, is_dir, _, _, dep, is_link in walk_dir(path, args.depth or 999,
                                                    args.exclude, args.hidden):
        if args.dirs_only and not is_dir:
            continue
        print(p)


# ─── DUPES command ─────────────────────────────────────────────
def cmd_dupes(args):
    path = args.path or '.'
    size_index = defaultdict(list)

    for p, is_dir, size, _, _, _ in walk_dir(path, 999, args.exclude, args.hidden):
        if is_dir or size == 0:
            continue
        size_index[size].append(p)

    hash_index = defaultdict(list)
    for size, paths in size_index.items():
        if len(paths) < 2:
            continue
        for p in paths:
            try:
                h = hashlib.sha256(Path(p).read_bytes()).hexdigest()
                hash_index[h].append(p)
            except (PermissionError, OSError):
                pass

    n_dupes = 0
    for h, paths in sorted(hash_index.items()):
        if len(paths) > 1:
            total_waste = Path(paths[0]).stat().st_size * (len(paths) - 1)
            print(f"\n{RED}Duplicate files{RESET} ({len(paths)}) — waste: {total_waste/(1024**2):.2f}MB")
            for p in paths:
                print(f"  {col('█', RED)} {p}")
            n_dupes += len(paths)

    if n_dupes == 0:
        print("No duplicate files found.")
    else:
        print(f"\n{DIM}Total duplicate files: {n_dupes}{RESET}")


# ─── Main ──────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    # Build parser
    parser = argparse.ArgumentParser(prog='filetree', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)

    sub = parser.add_subparsers(dest='subcommand')

    # tree
    p_tree = sub.add_parser('tree', help='Show directory tree')
    p_tree.add_argument('path', nargs='?', default='.')
    p_tree.add_argument('-d', '--depth', type=int, default=999)
    p_tree.add_argument('-a', '--hidden', action='store_true')
    p_tree.add_argument('-f', '--follow', action='store_true')
    p_tree.add_argument('--hidden-full', action='store_true', dest='hidden')
    p_tree.add_argument('-x', '--exclude', action='append', default=[])
    p_tree.add_argument('-s', '--sort', choices=['NAME', 'SIZE', 'TIME', 'EXT'], default='NAME')
    p_tree.add_argument('-r', '--reverse', action='store_true')
    p_tree.add_argument('--sizes', action='store_true')
    p_tree.add_argument('-q', '--quiet', action='store_true')

    # find
    p_find = sub.add_parser('find', help='Find files matching pattern')
    p_find.add_argument('path', nargs='?', default='.')
    p_find.add_argument('pattern', nargs='?', default='.*')
    p_find.add_argument('-t', '--type', choices=['f', 'd', 'l'])
    p_find.add_argument('-i', '--ignore-case', action='store_true')
    p_find.add_argument('-d', '--depth', type=int, default=999)
    p_find.add_argument('-x', '--exclude', action='append', default=[])
    p_find.add_argument('-a', '--hidden', action='store_true')
    p_find.add_argument('-f', '--follow', action='store_true')
    p_find.add_argument('-n', '--name-only', action='store_true')
    p_find.add_argument('-p', '--full-path', action='store_true')
    p_find.add_argument('-c', '--count', action='store_true')
    p_find.add_argument('-l', '--limit', type=int)

    # size
    p_size = sub.add_parser('size', help='Show biggest directories')
    p_size.add_argument('path', nargs='?', default='.')
    p_size.add_argument('-n', '--top', type=int, default=20)
    p_size.add_argument('--min-mb', type=float, default=0)
    p_size.add_argument('-d', '--depth', type=int, default=1)
    p_size.add_argument('-x', '--exclude', action='append', default=[])
    p_size.add_argument('-a', '--hidden', action='store_true')
    p_size.add_argument('-f', '--follow', action='store_true')

    # stats
    p_stats = sub.add_parser('stats', help='File type statistics')
    p_stats.add_argument('path', nargs='?', default='.')
    p_stats.add_argument('-x', '--exclude', action='append', default=[])
    p_stats.add_argument('-a', '--hidden', action='store_true')
    p_stats.add_argument('-t', '--top', type=int, default=20)

    # watch
    p_watch = sub.add_parser('watch', help='Watch directory live')
    p_watch.add_argument('path', nargs='?', default='.')
    p_watch.add_argument('-t', '--interval', type=float, default=2)
    p_watch.add_argument('-a', '--hidden', action='store_true')

    # diff
    p_diff = sub.add_parser('diff', help='Compare two directories')
    p_diff.add_argument('dir1')
    p_diff.add_argument('dir2')
    p_diff.add_argument('-b', '--brief', action='store_true')

    # json
    p_json = sub.add_parser('json', help='Output as JSON')
    p_json.add_argument('path', nargs='?', default='.')
    p_json.add_argument('-d', '--depth', type=int)
    p_json.add_argument('-x', '--exclude', action='append', default=[])
    p_json.add_argument('-a', '--hidden', action='store_true')

    # flat
    p_flat = sub.add_parser('flat', help='Flat listing')
    p_flat.add_argument('path', nargs='?', default='.')
    p_flat.add_argument('-d', '--depth', type=int, default=999)
    p_flat.add_argument('-x', '--exclude', action='append', default=[])
    p_flat.add_argument('-a', '--hidden', action='store_true')
    p_flat.add_argument('--dirs-only', action='store_true')

    # dupes
    p_dupes = sub.add_parser('dupes', help='Find duplicate files')
    p_dupes.add_argument('path', nargs='?', default='.')
    p_dupes.add_argument('-x', '--exclude', action='append', default=[])
    p_dupes.add_argument('-a', '--hidden', action='store_true')

    args = parser.parse_args(sys.argv[2:] if cmd == 'filetree' else sys.argv[1:])

    # Dispatch
    {
        'tree': cmd_tree,
        'find': cmd_find,
        'size': cmd_size,
        'stats': cmd_stats,
        'watch': cmd_watch,
        'diff': cmd_diff,
        'json': cmd_json,
        'flat': cmd_flat,
        'dupes': cmd_dupes,
    }.get(cmd, lambda _: parser.print_help())(args)
