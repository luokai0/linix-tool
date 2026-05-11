#!/usr/bin/env python3
"""
luodiff — Smart File & Directory Differ
by luokai | MIT License

Side-by-side, word-level, JSON-aware, and directory-tree diffs.
Beats plain `diff` and `colordiff` with smarter output and more modes.
"""

import os
import sys
import json
import argparse
import difflib
import hashlib
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
BG_R = "\033[41m"
BG_G = "\033[42m"

def c(*args):
    codes = args[1:]
    return "".join(codes) + str(args[0]) + R

# ── Word-level inline diff ─────────────────────────────────────────────────────

def word_diff_line(a: str, b: str) -> tuple[str, str]:
    """Return two lines with word-level highlighting."""
    aw = a.split()
    bw = b.split()
    sm = difflib.SequenceMatcher(None, aw, bw, autojunk=False)
    left = right = ""
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        la = " ".join(aw[i1:i2])
        lb = " ".join(bw[j1:j2])
        if tag == "equal":
            left  += la + " "
            right += lb + " "
        elif tag == "replace":
            left  += c(la, BG_R) + " "
            right += c(lb, BG_G) + " "
        elif tag == "delete":
            left  += c(la, BG_R) + " "
        elif tag == "insert":
            right += c(lb, BG_G) + " "
    return left.rstrip(), right.rstrip()

# ── Unified coloured diff ──────────────────────────────────────────────────────

def unified_diff(a_lines, b_lines, a_label, b_label, context=3, word_level=False):
    ops = list(difflib.unified_diff(a_lines, b_lines, fromfile=a_label, tofile=b_label, n=context))
    if not ops:
        print(c("  No differences found.", GRN, BOLD))
        return

    added = deleted = changed = 0
    for line in ops:
        line = line.rstrip("\n")
        if line.startswith("+++") or line.startswith("---"):
            print(c(line, BOLD, CYN))
        elif line.startswith("@@"):
            print(c(line, MGN))
        elif line.startswith("+"):
            added += 1
            print(c(line, GRN))
        elif line.startswith("-"):
            deleted += 1
            print(c(line, RED))
        else:
            print(c(line, DIM))

    print()
    print(c(f"  +{added} added  -{deleted} removed", BOLD))

# ── Side-by-side diff ─────────────────────────────────────────────────────────

def side_by_side_diff(a_lines, b_lines, a_label, b_label, width=None, word_level=True):
    if width is None:
        try:
            width = os.get_terminal_size().columns
        except Exception:
            width = 160
    col = max((width - 5) // 2, 40)

    print(c(f"  {'LEFT: '+a_label:<{col}}  │  {'RIGHT: '+b_label}", BOLD, CYN))
    print(c("  " + "─" * col + "  ┼  " + "─" * col, DIM))

    sm = difflib.SequenceMatcher(None, a_lines, b_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        la = a_lines[i1:i2]
        lb = b_lines[j1:j2]
        max_len = max(len(la), len(lb))
        for idx in range(max_len):
            left  = la[idx].rstrip("\n") if idx < len(la) else ""
            right = lb[idx].rstrip("\n") if idx < len(lb) else ""
            if tag == "equal":
                lc = c(left[:col], DIM)
                rc = c(right[:col], DIM)
                sep = c("│", DIM)
            elif tag == "replace":
                if word_level and left and right:
                    lw, rw = word_diff_line(left, right)
                    lc = lw[:col]
                    rc = rw[:col]
                else:
                    lc = c(left[:col], RED)
                    rc = c(right[:col], GRN)
                sep = c("│", YLW)
            elif tag == "delete":
                lc = c(left[:col], RED)
                rc = ""
                sep = c("│", RED)
            else:  # insert
                lc = ""
                rc = c(right[:col], GRN)
                sep = c("│", GRN)

            # pad without ANSI codes for alignment
            visible_left = re.sub(r"\033\[[^m]*m", "", lc) if "lc" in dir() else lc
            pad = col - len(lc.encode("utf-8").replace(b"\033", b"")) + len(lc)
            print(f"  {lc:<{col}}  {sep}  {rc}")

    # Import re for ANSI stripping
    import re

# ── JSON-aware diff ───────────────────────────────────────────────────────────

def json_diff(a_path: Path, b_path: Path, side: bool):
    def load(p):
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as e:
            print(c(f"  JSON parse error in {p}: {e}", RED)); sys.exit(1)

    def flatten(obj, prefix=""):
        items = {}
        if isinstance(obj, dict):
            for k, v in obj.items():
                key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, (dict, list)):
                    items.update(flatten(v, key))
                else:
                    items[key] = v
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                key = f"{prefix}[{i}]"
                if isinstance(v, (dict, list)):
                    items.update(flatten(v, key))
                else:
                    items[key] = v
        return items

    fa = flatten(load(a_path))
    fb = flatten(load(b_path))
    all_keys = sorted(set(fa) | set(fb))
    diffs = 0

    print(c(f"\n  JSON diff: {a_path.name} vs {b_path.name}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    for key in all_keys:
        va = fa.get(key, "__MISSING__")
        vb = fb.get(key, "__MISSING__")
        if va == vb:
            continue
        diffs += 1
        if va == "__MISSING__":
            print(f"  {c('+', GRN, BOLD)} {c(key, GRN)}: {c(json.dumps(vb), GRN)}")
        elif vb == "__MISSING__":
            print(f"  {c('-', RED, BOLD)} {c(key, RED)}: {c(json.dumps(va), RED)}")
        else:
            print(f"  {c('~', YLW, BOLD)} {c(key, YLW)}: {c(json.dumps(va), RED)} → {c(json.dumps(vb), GRN)}")

    if diffs == 0:
        print(c("  JSON structures are semantically identical.", GRN, BOLD))
    else:
        print(c(f"\n  {diffs} differences found.", YLW, BOLD))

# ── Directory diff ─────────────────────────────────────────────────────────────

def file_hash(p: Path) -> str:
    try:
        h = hashlib.md5()
        with p.open("rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""

def dir_diff(a: Path, b: Path, show_same=False):
    def collect(base: Path):
        files = {}
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(base)
                files[str(rel)] = p
        return files

    fa = collect(a)
    fb = collect(b)
    all_rel = sorted(set(fa) | set(fb))

    print(c(f"\n  Directory diff: {a}  vs  {b}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    only_a = only_b = changed = same = 0

    for rel in all_rel:
        if rel in fa and rel not in fb:
            only_a += 1
            print(f"  {c('─', RED, BOLD)} {c(rel, RED)}")
        elif rel in fb and rel not in fa:
            only_b += 1
            print(f"  {c('+', GRN, BOLD)} {c(rel, GRN)}")
        else:
            ha = file_hash(fa[rel])
            hb = file_hash(fb[rel])
            if ha != hb:
                changed += 1
                sa = fa[rel].stat().st_size
                sb = fb[rel].stat().st_size
                diff = sb - sa
                diff_str = f"{'+' if diff >= 0 else ''}{diff} bytes"
                print(f"  {c('~', YLW, BOLD)} {c(rel, YLW)}  {c(diff_str, DIM)}")
            else:
                same += 1
                if show_same:
                    print(f"  {c('=', DIM)} {c(rel, DIM)}")

    print()
    print(f"  {c(f'─{only_a} only in left', RED)}  {c(f'+{only_b} only in right', GRN)}  {c(f'~{changed} changed', YLW)}  {c(f'={same} identical', DIM)}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="luodiff",
        description=c("luodiff", BOLD, CYN) + " — Smart File & Directory Differ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  luodiff file.txt file2.txt              Unified diff (default)
  luodiff -s file.txt file2.txt           Side-by-side diff
  luodiff -w file.txt file2.txt           Side-by-side with word highlights
  luodiff -j a.json b.json               JSON-aware semantic diff
  luodiff -d dir1/ dir2/                 Directory tree diff
  luodiff -d dir1/ dir2/ --same          Also show identical files
  luodiff -c 5 a.py b.py                 Unified with 5 lines of context
""",
    )
    ap.add_argument("a", help="First file or directory")
    ap.add_argument("b", help="Second file or directory")
    ap.add_argument("-s", "--side", action="store_true", help="Side-by-side")
    ap.add_argument("-w", "--word", action="store_true", help="Word-level highlights (implies --side)")
    ap.add_argument("-j", "--json", action="store_true", help="JSON semantic diff")
    ap.add_argument("-d", "--dir", action="store_true", help="Directory diff")
    ap.add_argument("-c", "--context", type=int, default=3, help="Context lines")
    ap.add_argument("--same", action="store_true", help="Show identical files in dir diff")
    ap.add_argument("--width", type=int, help="Terminal width override")

    args = ap.parse_args()
    a, b = Path(args.a), Path(args.b)

    if not a.exists(): print(c(f"  Not found: {a}", RED)); sys.exit(1)
    if not b.exists(): print(c(f"  Not found: {b}", RED)); sys.exit(1)

    if args.dir or (a.is_dir() and b.is_dir()):
        dir_diff(a, b, show_same=args.same)
        return

    if args.json or (a.suffix == ".json" and b.suffix == ".json"):
        json_diff(a, b, side=args.side)
        return

    a_lines = a.read_text(errors="replace").splitlines(keepends=True)
    b_lines = b.read_text(errors="replace").splitlines(keepends=True)

    if args.word or args.side:
        side_by_side_diff(a_lines, b_lines, str(a), str(b),
                          width=args.width, word_level=args.word)
    else:
        unified_diff(a_lines, b_lines, str(a), str(b), context=args.context)

if __name__ == "__main__":
    main()
