# luodiff — Smart File & Directory Differ

> Side-by-side, word-level, JSON-aware, and directory-tree diffs. Pure Python, zero dependencies.

## Why luodiff?

| Feature | `diff` | `colordiff` | **luodiff** |
|---|---|---|---|
| Colour output | ✗ | ✓ | ✓ |
| Side-by-side | partial | partial | ✓ |
| Word-level highlights | ✗ | ✗ | ✓ |
| JSON semantic diff | ✗ | ✗ | ✓ |
| Directory tree diff | ✗ | ✗ | ✓ |
| No install needed | ✓ | ✗ | ✓ |

## Install

```bash
chmod +x luodiff.py
sudo ln -s $(pwd)/luodiff.py /usr/local/bin/luodiff
```

## Usage

```bash
luodiff a.txt b.txt              # unified diff with colour
luodiff -s a.txt b.txt           # side-by-side
luodiff -w a.txt b.txt           # side-by-side + word-level highlights
luodiff -j a.json b.json         # JSON semantic diff (key-by-key)
luodiff -d dir1/ dir2/           # directory tree diff
luodiff -d dir1/ dir2/ --same    # also show identical files
luodiff -c 5 a.py b.py           # 5 lines of context
```

## JSON Mode

Flattens both JSON files and compares key-by-key:

```
  ~ user.name: "Alice" → "Bob"
  + user.email: "bob@example.com"
  ─ user.phone: "+1234567890"
```

Works on arbitrarily nested objects and arrays.

## Directory Mode

```
  ─ src/old_file.py        (only in left)
  + src/new_feature.py     (only in right)
  ~ src/main.py  +240 bytes (changed)
  = tests/test_core.py      (identical)
```

## License
MIT — luokai
