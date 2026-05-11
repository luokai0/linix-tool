# pingpong — Network Connectivity Toolkit

A comprehensive network diagnostics CLI tool for ping, traceroute, DNS lookups, port scanning, and geolocation.

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![Platform](https://img.shields.io/badge/Linux-lightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- **ping** — ICMP ping with RTT stats
- **trace** — traceroute to visualize network path
- **dns** — Full DNS lookup (A, AAAA, MX, NS, TXT, CNAME, PTR)
- **port** — Check single port connectivity
- **scan** — Scan top N common ports
- **whois** — Domain registration info
- **geo** — IP geolocation via ip-api.com

## Usage

```bash
# Ping a host
python3 pingpong.py ping google.com 4

# Trace route
python3 pingpong.py trace google.com

# DNS lookup
python3 pingpong.py dns google.com

# Check port
python3 pingpong.py port google.com 443

# Scan top 20 ports
python3 pingpong.py scan github.com 20

# Whois domain
python3 pingpong.py whois google.com

# Geolocate IP
python3 pingpong.py geo github.com
```

## Installation

```bash
# No dependencies required (stdlib only)
# Optional: pip3 install dnspython for extended DNS records
pip3 install dnspython
```

## License

MIT — Free to use, modify, and distribute.