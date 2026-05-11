# luodisk — Disk Usage Analyzer

> Visual, fast, sorted disk usage explorer. Beats `du` and `ncdu` for quick human-readable analysis — pure Python, zero dependencies.

## Why luodisk?

| Feature | `du -sh *` | `ncdu` | **luodisk** |
|---|---|---|---|
| Visual bar charts | ✗ | ✓ | ✓ |
| Extension breakdown | ✗ | ✗ | ✓ |
| Largest files search | ✗ | partial | ✓ |
| All mounts overview | ✗ | ✗ | ✓ |
| No install needed | ✓ | ✗ | ✓ |
| Depth control | partial | ✓ | ✓ |

## Install

```bash
chmod +x luodisk.py
sudo ln -s $(pwd)/luodisk.py /usr/local/bin/luodisk
```

## Usage

```bash
luodisk                            # analyze current directory
luodisk /var                       # analyze /var
luodisk -d 3 /home/user            # depth-3 tree breakdown
luodisk -n 30 /                    # show top 30 entries
luodisk --min 50MB /home           # only items > 50 MB

luodisk largest /home              # top 20 largest files
luodisk largest /home --ext py     # top 20 largest .py files

luodisk types /project             # breakdown by file extension
luodisk mounts                     # all mounted filesystems with usage bars
```

## Sample Output

```
  luodisk — /home/user
  ────────────────────────────────────────────────────────────
  ████████░░░░░░░░░░░░   2.3 GB   45.2%  📁 Downloads/
  █████░░░░░░░░░░░░░░░   1.1 GB   21.6%  📁 Videos/
  ███░░░░░░░░░░░░░░░░░   640.0 MB  12.5%  📁 .local/
  ██░░░░░░░░░░░░░░░░░░   401.0 MB   7.9%  📁 Documents/
```

## License
MIT — luokai
