#!/usr/bin/env python3
"""
jsontool — CLI JSON processor
Query, transform, validate, and format JSON data

Usage:
  jsontool.py parse <file>                -- pretty print
  jsontool.py query <file> <jq-like>      -- dotpath query
  jsontool.py validate <file>            -- JSON schema check
  jsontool.py tocsv <file>                -- convert JSON array to CSV
  jsontool.py merge <file1> <file2>       -- merge two JSON files
  jsontool.py flatten <file>              -- flatten nested JSON
"""

import json
import sys
import csv
from pathlib import Path


def parse_json(data):
    if isinstance(data, dict):
        return {k: parse_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [parse_json(i) for i in data]
    return data


def query(data, path: str):
    for key in path.split('.'):
        if isinstance(data, dict):
            data = data.get(key, None)
        elif isinstance(data, list):
            try:
                data = data[int(key)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return data


def flatten(data, prefix: str = '', sep: str = '.'):
    result = {}
    if isinstance(data, dict):
        for k, v in data.items():
            result.update(flatten(v, f"{prefix}{k}{sep}", sep))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            result.update(flatten(v, f"{prefix}[{i}]{sep}", sep))
    else:
        return {prefix.rstrip(sep): data}
    return result


def to_csv(data) -> str:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        rows = [[str(row.get(h, '')) for h in headers] for row in data]
        output = ',' .join(headers) + '\n'
        output += '\n'.join(','.join(row) for row in rows)
        return output
    return ''


def merge(a, b) -> dict:
    result = a.copy()
    for k, v in b.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = merge(result[k], v)
        elif k in result and isinstance(result[k], list) and isinstance(v, list):
            result[k] = result[k] + v
        else:
            result[k] = v
    return result


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'parse':
        with open(sys.argv[2]) as f:
            print(json.dumps(json.load(f), indent=2))
    elif cmd == 'query' and len(sys.argv) >= 4:
        with open(sys.argv[2]) as f:
            data = json.load(f)
        result = query(data, sys.argv[3])
        if result is not None:
            print(json.dumps(result, indent=2))
    elif cmd == 'validate':
        with open(sys.argv[2]) as f:
            try:
                json.load(f)
                print("✅ Valid JSON")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON: {e}")
    elif cmd == 'tocsv':
        with open(sys.argv[2]) as f:
            data = json.load(f)
        print(to_csv(data) or "(data is not a JSON array of objects)")
    elif cmd == 'merge' and len(sys.argv) >= 4:
        with open(sys.argv[2]) as f, open(sys.argv[3]) as g:
            a, b = json.load(f), json.load(g)
        print(json.dumps(merge(a, b), indent=2))
    elif cmd == 'flatten':
        with open(sys.argv[2]) as f:
            data = json.load(f)
        flat = flatten(data)
        print(json.dumps(flat, indent=2))
    else:
        print(__doc__)