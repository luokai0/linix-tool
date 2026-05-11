# filetree — Directory Tree Visualizer & Analyzer

**Beats `tree`, `fd`, `find`, and `ncdu` combined — pure Python, zero dependencies.**

`filetree` is a full-featured file system explorer that replaces 5+ separate tools with one unified interface. Colored output, regex search, size analysis, duplicate detection, live watching, and directory diffing — all with a beautiful ASCII tree UI.

## Features

- **`tree`** — Color-coded directory tree with size, sorting, and depth control
- **`find`** — Regex-powered file search with type filtering and result limits
- **`size`** — Biggest directories with ASCII progress bars and percentage breakdown
- **`stats`** — File type distribution with count, size, and date range
- **`watch`** — Live file system monitor — see new files appear in real time
- **`diff`** — Side-by-side comparison of two directory trees
- **`json`** — Full directory dump as JSON for piping into other tools
- **`flat`** — One file per line, full paths, with depth control
- **`dupes`** — Find duplicate files by content hash, shows wasted space

## Installation

```bash
# Download and run directly
curl -L https://raw.githubusercontent.com/luokai0/linix-tool/main/tools/filetree/filetree.py -o filetree.py
chmod +x filetree.py

# Or copy to your PATH
sudo cp filetree.py /usr/local/bin/filetree
```

## Commands

### tree — Directory Tree

```bash
# Basic tree
python3 filetree.py tree

# Tree with file sizes, max 3 levels deep
python3 filetree.py tree . -d 3 --sizes

# Sort by size (biggest first), show hidden files
python3 filetree.py tree /var -s SIZE -r -a

# Follow symlinks, exclude node_modules and .git
python3 filetree.py tree . -f -x "node_modules" -x ".git"

# Output only paths (good for piping)
python3 filetree.py tree . -q
```

### find — Regex File Search

```bash
# Find all .py files
python3 filetree.py find . "\.py$"

# Find files containing "config" (case insensitive)
python3 filetree.py find /etc "config" -i

# Find directories only, max depth 2
python3 filetree.py find . ".*" -t d -d 2

# Find and show full paths, limit to 20 results
python3 filetree.py find . "test" -p -l 20

# Count matching files
python3 filetree.py find /home ".*" -c
```

### size — Directory Size Analysis

```bash
# Top 20 largest directories
python3 filetree.py size .

# Top 10, minimum 10MB, 2 levels deep
python3 filetree.py size /home -n 10 --min-mb 10 -d 2

# Sort by size, exclude build artifacts
python3 filetree.py size . -x "build" -x "dist" -r
```

### stats — File Type Statistics

```bash
# Full statistics
python3 filetree.py stats /home/workspace

# Top 15 extensions only
python3 filetree.py stats . -t 15
```

### watch — Live File Monitor

```bash
# Watch current directory, 2-second refresh
python3 filetree.py watch .

# Watch with 1-second refresh, include hidden files
python3 filetree.py watch /tmp -t 1 -a
```

### diff — Directory Comparison

```bash
# Full diff
python3 filetree.py diff /home/backup /home/current

# Brief mode (only differences)
python3 filetree.py diff dir1 dir2 -b
```

### json — JSON Export

```bash
# Full JSON dump
python3 filetree.py json /home/workspace

# Max depth 3, exclude hidden
python3 filetree.py json /home -d 3
```

### flat — Flat Listing

```bash
# All files, full paths
python3 filetree.py flat /home/workspace

# Directories only, max 2 levels
python3 filetree.py flat /home -d 2 --dirs-only
```

### dupes — Find Duplicates

```bash
# Find all duplicates by SHA-256 hash
python3 filetree.py dupes /home/photos

# Exclude thumbnails
python3 filetree.py dupes . -x "*.thumb.jpg"
```

## Color Legend

| Color | Type |
|-------|------|
| `cyan` | Directories |
| `green` | Code files (.py, .js, .go, .rs...) |
| `yellow` | Images and videos |
| `red` | Archives and compressed files |
| `blue` | Documents |
| `magenta` | Symbolic links |

## Sorting

Available sort modes: `NAME`, `SIZE`, `TIME`, `EXT`
Use `-r` for reverse (largest/oldest first).

## Why filetree?

Most tools do one thing well. `filetree` combines the best features of 5+ tools into one zero-dependency Python script:

| Feature | filetree | tree | fd | find | ncdu |
|---------|:---:|:---:|:---:|:---:|:---:|
| Tree view | ✅ | ✅ | ❌ | ❌ | ❌ |
| File sizes | ✅ | partial | ❌ | ❌ | ✅ |
| Regex search | ✅ | ❌ | ✅ | ✅ | ❌ |
| Type filtering | ✅ | ❌ | ✅ | ✅ | ❌ |
| Live watch | ✅ | ❌ | ❌ | ❌ | ❌ |
| Dir diff | ✅ | ❌ | ❌ | ❌ | ❌ |
| Duplicate finder | ✅ | ❌ | ❌ | ❌ | ❌ |
| JSON export | ✅ | ❌ | ❌ | ❌ | ❌ |
| Zero deps | ✅ | ❌ | ❌ | ✅ | ❌ |
| Pure Python | ✅ | ❌ | ❌ | ❌ | ❌ |

## License

MIT — luokai