#!/usr/bin/env python3
"""
gitree — Git repository visualizer
Show branch tree, commit graph, repo stats, staled branches, lost commits

Usage:
  python3 gitree.py tree [n]              -- show commit tree (last n commits)
  python3 gitree.py branches             -- list all branches with tracking
  python3 gitree.py stale                -- find stale local branches
  python3 gitree.py lost                 -- find lost commits (in reflog but not in any branch)
  python3 gitree.py stats                -- show repo statistics
  python3 gitree.py contributors         -- top contributors
"""

import sys
import subprocess
import re
from collections import Counter
from pathlib import Path


GIT = 'git'
REPO = Path.cwd()


def run(*args) -> str:
    return subprocess.run([GIT] + list(args), capture_output=True, text=True, cwd=REPO).stdout


def tree(n: int = 20) -> None:
    log = run('log', '--oneline', '--graph', f'-{n}')
    for line in log.splitlines():
        parts = re.split(r'[*|\\/ ]', line, 1)
        print(parts[-1].strip() if len(parts) > 1 else line)


def branches() -> None:
    for line in run('branch', '-vv').splitlines():
        print(line)


def stale() -> list[str]:
    result = run('branch', '--merged', 'HEAD')
    merged = {b.strip(' *') for b in result.splitlines()}
    all_br = {b.strip(' *') for b in run('branch').splitlines()}
    stale = all_br - merged - {'main', 'master', 'HEAD'}
    return list(stale)


def lost() -> list[str]:
    reflog = run('reflog', '--pretty=%H %s')
    committed = {l.split()[0] for l in run('rev-list', '--all', '--quiet').splitlines()}
    lost = []
    for line in reflog.splitlines():
        if line.strip():
            sha = line.split()[0]
            if sha not in committed:
                lost.append(line)
    return lost[:20]


def stats() -> dict:
    commits = run('rev-list', '--count', 'HEAD').strip()
    branches = len(run('branch').splitlines())
    contributors = len(run('shortlog', '-sn', '--all').splitlines())
    size_kb = sum(f.stat().st_size for f in REPO.rglob('*') if f.is_file()) // 1024
    return {'commits': commits, 'branches': branches, 'contributors': contributors, 'repo_size_kb': size_kb}


def contributors(n: int = 10) -> list[tuple[str, int]]:
    lines = run('shortlog', '-sn', '--all').splitlines()[:n]
    return [(l.split('\t')[1].strip(), int(l.split('\t')[0])) for l in lines]


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'tree':
        n = int(sys.argv[2]) if len(sys.argv) >= 3 else 20
        tree(n)
    elif cmd == 'branches':
        branches()
    elif cmd == 'stale':
        for b in stale():
            print(f"  stale: {b}")
    elif cmd == 'lost':
        for entry in lost():
            print(entry)
    elif cmd == 'stats':
        for k, v in stats().items():
            print(f"  {k:20s}  {v}")
    elif cmd == 'contributors':
        for name, count in contributors():
            print(f"  {count:5d}  {name}")
    else:
        print(__doc__)