# loggrep — Pattern-based Log Analyzer

Search, filter, aggregate, and visualize patterns in log files.

## Features

- **search** — Grep-like regex search with line numbers
- **errors** — Extract all error/fatal/critical lines
- **stats** — Count log events by level (DEBUG/INFO/WARN/ERROR/etc)
- **timeline** — Show event frequency per minute/hour

## Usage

```bash
# Search for pattern
python3 loggrep.py search /var/log/syslog "connection refused"

# Extract all errors
python3 loggrep.py errors /var/log/syslog

# Log level stats
python3 loggrep.py stats /var/log/syslog

# Timeline view
python3 loggrep.py timeline /var/log/syslog
```

## License

MIT — luokai