# luonetscan — Advanced Async Port Scanner by luokai

> Built from porthawk, portfinder, and custom enhancements. Licensed under MIT.

## Features

| Feature | Description |
|---------|-------------|
| ⚡ **Async TCP/UDP scanning** | Up to 1000 concurrent connections |
| 🔍 **Service fingerprinting** | Banner grabbing, SSH/MySQL/Redis version detection |
| 🔎 **CVE lookup** | Live NVD API query with in-memory + disk cache |
| 🗺️ **Geo-IP + ASN** | Via ip-api.com (free, no key needed) |
| 🌐 **CIDR range expansion** | `10.0.0.0/24` → all hosts scanned |
| 🕵️ **Honeypot detection** | Cowrie SSH, Dionaea FTP, ICS multi-port, latency uniformity |
| 📊 **Live progress UI** | Colored real-time scan updates |
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
# Scan common ports
python3 luonetscan.py scan -t 192.168.1.1 -p 22,80,443

# Top 50 ports
python3 luonetscan.py top -t github.com -n 50

# Full 1-65535 scan
python3 luonetscan.py deep -t 192.168.1.1

# With banners + CVE lookup
python3 luonetscan.py scan -t github.com -p 22,80,443 --banners --cve

# Scan a network range
python3 luonetscan.py range -t 192.168.1.1-50 -p 80,443

# Host info + geo
python3 luonetscan.py ping -t google.com

# CVE lookup
python3 luonetscan.py cve redis --version 6.0

# Compare scans
python3 luonetscan.py diff scan_a.json scan_b.json

# Save as HTML report
python3 luonetscan.py scan -t github.com -o html --json
```

## Options

```
-t, --target HOST      Target IP/hostname/CIDR
-p, --ports PORTS     Port spec: '22,80,443' or '1-1024'
-n, --top-ports N     Scan top N most common ports [default: 50]
--timeout SEC         Connection timeout [default: 1.0]
--threads N            Max concurrent connections [default: 500]
--banners             Grab service banners
--cve                 Look up CVEs for open services via NVD API
--os                  OS detection via TTL
--json                Output results as JSON
-o, --output FMT      Output format: json, csv, html
--show-closed         Show closed/filtered ports
--no-live             Disable live UI (for pipes/CI)
--udp                 UDP scan mode
--adaptive            Adaptive concurrency
--stealth             Stealth mode: 1 thread, 3s timeout
--honeypot            Score target for honeypot likelihood
--slack-webhook URL   Slack webhook for HIGH-risk alerts
--discord-webhook URL Discord webhook for HIGH-risk alerts
```

## Compared to nmap

| Feature | nmap | luonetscan |
|---------|------|------------|
| Speed | Fast | Fast (async) |
| CVE lookup | External script | ✅ Built-in |
| Geo-IP/ASN | External | ✅ Built-in |
| Service fingerprint | -sV | ✅ Built-in |
| Honeypot detection | ❌ | ✅ Built-in |
| Banner grab | ❌ | ✅ SSH/MySQL/Redis |
| JSON/CSV/HTML output | ✅ | ✅ All three |
| Pure Python | ❌ | ✅ |
| No dependencies | ❌ | ✅ (httpx + rich = optional) |

## Dependencies

```bash
pip install httpx rich
```
httpx is the only hard dependency — everything else uses Python stdlib.
Rich is optional (used only for HTTP header grabbing).

## Risk Levels

| Color | Level | Meaning |
|-------|-------|---------|
| 🔴 | HIGH | Never expose to internet |
| 🟡 | MEDIUM | Needs auth/TLS if public |
| 🟢 | LOW | Standard web ports |
| ⚪ | INFO | Informational |

## Honeypot Detection

luonetscan detects these honeypot signatures:
- **Cowrie SSH** — Known Cowrie default SSH banners
- **Dionaea FTP** — Synology FTP banner from Dionaea honeypot
- **ICS multi-port** — Multiple ICS/SCADA ports = Conpot signature
- **Port flood** — >20 open ports unusual on real hosts
- **Uniform latency** — Suspiciously uniform response times

## Set NVD_API_KEY

For higher CVE lookup rate limits:
```bash
export NVD_API_KEY=your_key_here
```

Get a free key at: https://nvd.nist.gov/developers/request-an-api-key

Author: **luokai** | MIT License