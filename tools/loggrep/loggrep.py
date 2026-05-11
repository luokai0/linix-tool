#!/usr/bin/env python3
"""
loggrep — Pattern-based log analyzer
Search, filter, aggregate, and visualize patterns in log files

Usage:
  loggrep.py search <file> <pattern>     -- grep-like search
  loggrep.py errors <file>              -- show all error lines
  loggrep.py stats <file>               -- count by log level
  loggrep.py timeline <file>            -- events per minute/hour
  loggrep.py follow <file>              -- tail -f equivalent
"""

import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


LOG_LEVELS = re.compile(r'\b(DEBUG|INFO|WARN|WARNING|ERROR|FATAL|CRITICAL|NOTICE)\b', re.IGNORECASE)
TIMESTAMPS = re.compile(r'\[?(\d{4}[-/]\d{2}[-/]\d{2}[T\s][\d:]+)')


def search(filepath: str, pattern: str) -> list[tuple[int, str]]:
    results = []
    regex = re.compile(pattern, re.IGNORECASE)
    for i, line in enumerate(open(filepath), 1):
        if regex.search(line):
            results.append((i, line.rstrip()))
    return results


def errors(filepath: str) -> list[tuple[int, str]]:
    return search(filepath, r'\b(error|fatal|critical|exception|failed|fail)\b')


def stats(filepath: str) -> dict:
    counter = Counter()
    for line in open(filepath):
        m = LOG_LEVELS.search(line)
        if m:
            counter[m.group().upper()] += 1
        else:
            counter['UNKNOWN'] += 1
    return dict(counter.most_common())


def timeline(filepath: str, bucket: str = 'minute') -> dict:
    pattern = '%Y-%m-%d %H:%M' if bucket == 'minute' else '%Y-%m-%d %H'
    counter = Counter()
    for line in open(filepath):
        m = TIMESTAMPS.search(line)
        if m:
            try:
                dt = datetime.strptime(m.group(1), '%Y-%m-%d %H:%M:%S')
                key = dt.strftime(pattern)
                counter[key] += 1
            except ValueError:
                pass
    return dict(sorted(counter.items()))


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)

    cmd, filepath = sys.argv[1], sys.argv[2]

    if cmd == 'search' and len(sys.argv) >= 4:
        for lineno, line in search(filepath, sys.argv[3]):
            print(f"{lineno}: {line}")
    elif cmd == 'errors':
        for lineno, line in errors(filepath):
            print(f"{lineno}: {line}")
    elif cmd == 'stats':
        for level, count in stats(filepath).items():
            print(f"  {level:12s}  {count:,}")
    elif cmd == 'timeline':
        for ts, count in timeline(filepath).items():
            bar = '█' * min(count, 100)
            print(f"{ts}  {count:6d}  {bar}")
    else:
        print(__doc__)