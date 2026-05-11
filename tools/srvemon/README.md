# luosrvemon — Service Uptime & Health Monitor

> Built from uptime-kuma + healthchecks concepts. Licensed under MIT.

## Features

| Feature | Description |
|---------|-------------|
| ⚡ **Async monitoring** | HTTP, HTTPS, TCP, SSH, ICMP, SSL certificate |
| 🔍 **Keyword filtering** | success_kw, failure_kw, start_kw |
| 📊 **Uptime tracking** | Downtime tracking, duration, % calculation |
| 🕵️ **Honeypot detection** | Cowrie SSH, Dionaea FTP, ICS multi-port, latency uniformity |
| 🔎 **CVE lookup** | Live NVD API query with in-memory + disk cache |
| 🗺️ **Geo-IP + ASN** | Via ip-api.com (free, no key needed) |
| 📤 **Multi-format output** | JSON, CSV, HTML reports |
| 🔄 **5 scan modes** | scan, top, deep, range, ping, cve, diff |
| 🛡️ **Evasion techniques** | SYN, FIN, NULL, XMAS, ACK, Maimon scans |
| 🎯 **OS detection** | TTL-based OS fingerprinting |
| 📬 **Webhook alerts** | Slack + Discord for HIGH-risk port alerts |
| 🧠 **ML-based port ordering** | Smart port order (needs scikit-learn) |
| 📡 **Passive OS fingerprinting** | TCP option analysis |
| 📊 **Scan diff** | Compare two scans for changes |

## Quick Start

```bash
# Add a monitor
python3 luosrvemon.py add github.com --name "GitHub" --tags production,critical

# Check a service now
python3 luosrvemon.py check 8a75e48eaa7a

# List all monitors
python3 luosrvemon.py list

# Show stats
python3 luosrvemon.py stats

# Run continuous monitoring
python3 luosrvemon.py monitor

# Show uptime report
python3 luosrvemon.py report

# Pause / resume
python3 luosrvemon.py pause 8a75e48eaa7a
python3 luosrvemon.py resume 8a75e48eaa7a

# Generate badge
python3 luosrvemon.py badge 8a75e48eaa7a --format svg

# Ping history
python3 luosrvemon.py history 8a75e48eaa7a --limit 20

# Export / Import
python3 luosrvemon.py export > backup.json
python3 luosrvemon.py import backup.json
```

## Add Options

```
python3 luosrvemon.py add <url>
  --name/-n              Display name
  --interval/-i           Check interval (seconds) [default: 60]
  --timeout/-t           Request timeout (seconds) [default: 10]
  --port/-p              Port override
  --grace/-g             Grace period before alerting [default: 60]
  --retries/-r           Max failures before declaring down [default: 3]
  --tags                 Comma-separated tags
  --webhook              Generic webhook URL
  --slack                Slack webhook URL
  --discord              Discord webhook URL
  --telegram-bot         Telegram bot token
  --telegram-chat        Telegram chat ID
  --expected-code        Expected HTTP status code [default: 200]
  --keyword/-k           Keyword expected in response
  --fail-keyword         Keyword that means failure
  --success-kw           Keyword that means success
```

## Compared to Uptime Kuma

| Feature | Uptime Kuma | luosrvemon |
|---------|-------------|------------|
| Self-hosted | ✅ | ✅ (pure Python) |
| HTTP/HTTPS checks | ✅ | ✅ |
| TCP checks | ✅ | ✅ |
| SSH checks | ✅ | ✅ |
| ICMP/Ping | ✅ | ✅ |
| SSL expiry check | ✅ | ✅ |
| Keyword filtering | ✅ | ✅ |
| Keyword failure filtering | ✅ | ✅ |
| Multiple intervals | ✅ | ✅ |
| Retry tracking | ✅ | ✅ |
| Status pages | ✅ | ❌ (coming soon) |
| Webhook alerts | ✅ | ✅ (Slack, Discord, Telegram, generic) |
| Email alerts | via SMTP | ✅ (via SMTP env vars) |
| History log | ✅ | ✅ (last 100 pings) |
| Downtime tracking | ✅ | ✅ |
| Uptime % calculation | ✅ | ✅ |
| Status badges | ✅ | ✅ (SVG, JSON, shields.io) |
| Export/Import | ✅ | ✅ JSON |
| Multi-protocol | ✅ | ✅ (HTTP, TCP, SSH, ICMP, SSL, Heartbeat) |
| Dark mode UI | ✅ | ❌ (CLI-focused) |
| Auto-resume | ✅ | ❌ (coming soon) |
| Cron scheduling | ❌ | ✅ (schedule field) |
| **Pure Python** | ❌ | ✅ |
| **No Node.js** | ❌ | ✅ |
| **No npm/yarn** | ❌ | ✅ |

## Dependencies

```bash
pip install rich httpx
```
Rich is optional (enables pretty tables). Everything else uses Python stdlib.

## Environment Variables

```bash
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=alerts@example.com
SMTP_PASS=password
```

## Status Badge Formats

```bash
# SVG badge
python3 luosrvemon.py badge <id> --format svg

# JSON (shields.io compatible)
python3 luosrvemon.py badge <id> --format json

# shields.io format
python3 luosrvemon.py badge <id> --format shields
```

Author: **luokai** | MIT License