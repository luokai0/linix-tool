# luonetscan — Async Network Port Scanner + CVE Detector

> **luo**netscan — Built from the ground up inspired by porthawk & portfinder, with full service fingerprinting, CVE lookup, geo-IP, and colored output. Pure Python, zero heavy dependencies.

## Features

- ⚡ **Async TCP/UDP scanning** — up to 1000 concurrent connections
- 🔍 **Service fingerprinting** — banner grabbing, SSH/MySQL/Redis version detection
- 🔎 **CVE lookup** — live NVD API query with in-memory + disk cache
- 🗺️ **Geo-IP + ASN lookup** — via ip-api.com (free, no key needed)
- 🌐 **CIDR range expansion** — `10.0.0.0/24` → all hosts scanned
- 📊 **Colored live output** — risk levels, state, latency per port
- 📤 **JSON output** — for scripting and automation
- 🎯 **Top-N port scan** — scan the 50 most common ports instantly
- 🔄 **5 commands** — scan, top, deep, range, ping, cve

## Installation

```bash
# Clone the repo
git clone https://github.com/luokai0/linix-tool.git
cd linix-tool/tools/netscan

# Or add to PATH
chmod +x luonetscan.py
sudo cp luonetscan.py /usr/local/bin/luonetscan
```

## Commands

### scan — Scan hosts with custom ports
```bash
python3 luonetscan.py scan -t 192.168.1.1 -p 22,80,443,3306 --timeout 2
python3 luonetscan.py scan -t 10.0.0.0/24 -p 80,443 --tcp --json
```

### top — Scan top-N most common ports
```bash
python3 luonetscan.py top -t github.com -n 50
```

### deep — Full port scan (1-65535)
```bash
python3 luonetscan.py deep -t 192.168.1.1
```

### range — Scan IP range or CIDR
```bash
python3 luonetscan.py range -t 192.168.1.1-50 -p 1-1000
python3 luonetscan.py range -t 10.0.0.0/24 -p 80,443
```

### ping — Host info + geo + ASN
```bash
python3 luonetscan.py ping -t google.com
```

### cve — CVE lookup from NVD
```bash
python3 luonetscan.py cve redis --version 6.0
python3 luonetscan.py cve openssh
```
> Set `NVD_API_KEY` env var for higher rate limits (free at nvd.nist.gov)

## Output Example

```
  22/tcp  OPEN    1.5ms  MEDIUM  ssh
  80/tcp  OPEN    1.2ms  LOW    http
 443/tcp  OPEN    1.3ms  LOW    https

  Scanned 1 host(s) × 4 ports = 4 total
  Open: 3  |  Closed: 0  |  Filtered: 1
```

## Risk Levels

| Color | Level | Meaning |
|-------|-------|---------|
| 🔴 Red | HIGH | Never expose to internet |
| 🟡 Yellow | MEDIUM | Needs auth/TLS if public |
| 🟢 Green | LOW | Standard web ports |
| ⚪ Gray | INFO | Informational |

## Dependencies

```
pip install httpx
```
httpx is the only dependency — everything else is stdlib.

## Compared to nmap

| Feature | nmap | luonetscan |
|---------|------|------------|
| Speed | Fast | Fast (async) |
| CVE lookup | External script | Built-in |
| Geo-IP | External | Built-in |
| Banner grab | -sV | Built-in + MySQL/Redis/SSH |
| JSON output | -oJ | Native --json |
| Dependencies | None | httpx only |
| Pure Python | ❌ | ✅ |

Author: luo kai | linix-tool
MIT License