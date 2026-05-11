# syspeek — Real-time Linux System Monitor

A lightweight, no-dependency real-time system monitor for Linux terminal.

![syspeek](https://img.shields.io/badge/Python-3.12+-blue.svg)
![Platform](https://img.shields.io/badge/Linux-lightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- **CPU Usage** — Live CPU % with visual bar
- **RAM Usage** — Memory used/total with bar
- **Disk Usage** — Root disk usage with bar
- **Network** — Live RX/TX speed + total cached
- **Top Processes** — Top 5 CPU-consuming processes
- **Uptime Tracker** — Shows how long syspeek has been running

## Installation

```bash
# No install needed — runs directly with Python 3
python3 syspeek.py
```

## Usage

```bash
# Default 1-second refresh
python3 syspeek.py

# 2-second refresh
python3 syspeek.py 2
```

Exit anytime with `Ctrl+C`.

## Requirements

- Python 3.6+
- Linux `/proc` filesystem (standard on all Linux distros)
- No pip packages needed — pure stdlib

## Output Preview

```
================================================================
  SYSPEEK | 2026-05-11 02:45:00 | Uptime: 0d 0h 2m 15s
  ──────────────────────────────────────────────────────
  CPU      ████████████████████░░░░░░░░░░  65.3%
  RAM      ██████████████░░░░░░░░░░░░░░░  42.1%
  DISK     █████████████░░░░░░░░░░░░░░░░  38.7%

  NETWORK (live)  ↓ 1.2MB/s   ↑ 0.8MB/s
  CACHE (total)  ↓ 2.3GB     ↑ 1.1GB

  ──────────────────────────────────────────────────────
                      TOP PROCESSES
  ──────────────────────────────────────────────────────
    CPU%    MEM%  COMMAND
  ──────────────────────────────────────────────────────
    25.3%   12.4%  node server.js
    15.7%    8.2%  python3 ai-agent.py
     8.2%    4.1%  redis-server

  ──────────────────────────────────────────────────────
  Refreshing every 1s...
```

## License

MIT — Free to use, modify, and distribute.