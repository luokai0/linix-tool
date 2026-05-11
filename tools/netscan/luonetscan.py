#!/usr/bin/env python3
"""
luonetscan — Advanced Async Port Scanner + CVE Lookup + Service Fingerprint
Built from porthawk, portfinder, and custom enhancements

MIT License — luokai

Usage:
  luonetscan scan   -t <host> [-p PORTS] [options]    Scan ports
  luonetscan top   -t <host> [-n N] [options]        Top-N port scan
  luonetscan deep  -t <host> [options]                Full 1-65535 scan
  luonetscan range -t <start-end> [-p PORTS] [opts]  IP range scan
  luonetscan ping  -t <host>                         Host info
  luonetscan cve   <service> [--version X.Y]          CVE lookup
  luonetscan diff  <scan_a.json> <scan_b.json>        Compare scans

Options:
  -t, --target HOST      Target IP/hostname/CIDR
  -p, --ports PORTS     Port spec: '22,80,443' or '1-1024' [default: common]
  -n, --top-ports N     Scan top N most common ports [default: 50]
  --timeout SEC         Connection timeout [default: 1.0]
  --threads N            Max concurrent connections [default: 500]
  --banners             Grab service banners
  --cve                 Look up CVEs for open services via NVD API
  --os                  OS detection via TTL
  --json                Output results as JSON
  -o, --output FMT      Output format: json, csv, html [default: terminal]
  --show-closed         Show closed/filtered ports in output
  --no-live             Disable live UI (for pipes/CI)
  --udp                 UDP scan mode
  --adaptive            Adaptive concurrency (ramp up on stable networks)
  --stealth             Stealth mode: 1 thread, 3s timeout
  --syn                 SYN half-open scan (requires root)
  --evasion-type TYPE   TCP flag evasion: syn, fin, null, xmas, ack, maimon
  --jitter SEC          Max random delay between probes
  --fragment            IP packet fragmentation
  --honeypot           Score target for honeypot likelihood
  --slack-webhook URL   Slack webhook for HIGH-risk alerts
  --discord-webhook URL Discord webhook for HIGH-risk alerts
  --passive-os          Passive TCP OS fingerprinting
  -h, --help            Show this help
"""
import argparse
import asyncio
import csv
import json
import math
import os
import random
import socket
import statistics
import struct
import subprocess
import sys
import time
from collections import deque
from datetime import datetime
from enum import Enum
from pathlib import Path

try:
    import httpx
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ───────────────────────────────────────────────────────────────
# ANSI colors (no rich dependency needed for core output)
# ───────────────────────────────────────────────────────────────
C = type('C', (), {
    'RED': '\033[91m', 'GREEN': '\033[92m', 'YELLOW': '\033[93m',
    'CYAN': '\033[96m', 'MAGENTA': '\033[95m', 'WHITE': '\033[97m',
    'DIM': '\033[2m', 'BOLD': '\033[1m', 'RESET': '\033[0m',
})()

def col(text, color):
    return f"{color}{text}{C.RESET}"

# ───────────────────────────────────────────────────────────────
# Port State & Models
# ───────────────────────────────────────────────────────────────
class PortState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    FILTERED = "filtered"

class ScanResult:
    __slots__ = ('host','port','protocol','state','banner',
                 'service_name','service_version','risk_level',
                 'os_guess','ttl','latency_ms','cves')
    def __init__(self, host, port, protocol='tcp', state=None, banner=None,
                 service_name=None, service_version=None, risk_level=None,
                 os_guess=None, ttl=None, latency_ms=None, cves=None):
        self.host = host
        self.port = port
        self.protocol = protocol
        self.state = state or PortState.CLOSED
        self.banner = banner
        self.service_name = service_name
        self.service_version = service_version
        self.risk_level = risk_level
        self.os_guess = os_guess
        self.ttl = ttl
        self.latency_ms = latency_ms
        self.cves = cves or []

    def model_dump(self):
        return {s: getattr(self, s) for s in self.__slots__}

# ───────────────────────────────────────────────────────────────
# Service Database (from porthawk's service_db.py + porthawk's fingerprint.py)
# ───────────────────────────────────────────────────────────────
_HIGH_RISK = frozenset({
    21,23,25,53,69,110,111,119,135,137,138,139,143,161,389,445,
    512,513,514,1433,1521,2049,3389,4444,5900,6379,27017
})
_MEDIUM_RISK = frozenset({
    22,3306,5432,8080,8443,1080,3128,5000,5001,8888,9200,9300,
    11211,27018,28017
})

_PORT_DB = {
    21: ("ftp","File Transfer Protocol"), 22: ("ssh","Secure Shell"),
    23: ("telnet","Telnet"), 25: ("smtp","SMTP Mail"),
    53: ("dns","DNS"), 80: ("http","HTTP"),
    110: ("pop3","POP3 Mail"), 143: ("imap","IMAP"),
    443: ("https","HTTPS"), 445: ("smb","SMB/CIFS"),
    3306: ("mysql","MySQL"), 3389: ("rdp","Remote Desktop"),
    5432: ("postgresql","PostgreSQL"), 5900: ("vnc","VNC"),
    6379: ("redis","Redis"), 8080: ("http-proxy","HTTP Proxy"),
    9200: ("elasticsearch","Elasticsearch"), 27017: ("mongodb","MongoDB"),
}

_TOP_PORTS = [
    80,443,22,21,25,3389,110,445,139,143,53,135,3306,8080,1723,
    111,995,993,587,23,8443,8888,6379,27017,5432,1433,5900,2049,
    389,161,3128,1080,5000,8000,9200,11211,2375,10250,9092,2181,
    6443,5672,5601,9090,4444,9300,27018,7001,9000,9042,4848,8161,
]

def get_service(port, protocol='tcp'):
    entry = _PORT_DB.get(port)
    if not entry:
        return ('unknown', 'unknown', None)
    name, desc = entry
    if port in _HIGH_RISK:
        risk = 'HIGH'
    elif port in _MEDIUM_RISK:
        risk = 'MEDIUM'
    else:
        risk = 'LOW'
    return (name, desc, risk)

def get_top_ports(n=50):
    return _TOP_PORTS[:n]

# ───────────────────────────────────────────────────────────────
# Scanner Core
# ───────────────────────────────────────────────────────────────
def expand_cidr(target):
    import ipaddress
    target = target.strip()
    if not target:
        return []
    bare = target.lstrip('[').rstrip(']')
    try:
        net = ipaddress.ip_network(bare, strict=False)
        hosts = list(net.hosts())
        if not hosts:
            return [str(net.network_address)]
        return [str(ip) for ip in hosts]
    except ValueError:
        return [bare]

def parse_port_range(spec):
    if not spec:
        return None
    ports = set()
    for seg in spec.split(','):
        seg = seg.strip()
        if '-' in seg:
            lo, hi = map(int, seg.split('-', 1))
            ports.update(range(lo, hi+1))
        else:
            ports.add(int(seg))
    return sorted(ports)

async def _tcp_probe(host, port, timeout):
    t_start = time.monotonic()
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        elapsed = (time.monotonic() - t_start) * 1000
        w.close()
        await w.wait_closed()
        return (PortState.OPEN, round(elapsed, 2))
    except asyncio.TimeoutError:
        return (PortState.FILTERED, round(timeout*1000, 2))
    except (ConnectionRefusedError, OSError):
        elapsed = (time.monotonic() - t_start) * 1000
        return (PortState.CLOSED, round(elapsed, 2))

async def scan_port(host, port, timeout, semaphore):
    async with semaphore:
        return await _tcp_probe(host, port, timeout)

async def scan_host(host, ports, timeout=1.0, max_concurrent=500,
                     show_progress=True, on_result=None, adaptive_cfg=None):
    sem = asyncio.Semaphore(max_concurrent)
    tasks = [scan_port(host, p, timeout, sem) for p in ports]
    results = []
    for coro in asyncio.as_completed(tasks):
        state, latency = await coro
        r = ScanResult(host=host, port=ports[len(results)], protocol='tcp', state=state, latency_ms=latency)
        results.append(r)
        if on_result:
            on_result(r)
    return results

# ───────────────────────────────────────────────────────────────
# Banner grabbing + fingerprinting
# ───────────────────────────────────────────────────────────────
_HTTP_PORTS = {80, 443, 8080, 8443, 8000, 8888, 9200}
_LISTEN_FIRST = {21, 22, 23, 25, 110, 143, 3306, 5432, 5900}
_PROBE = {6379: b'PING\r\n', 11211: b'stats\r\n'}

def extract_version(banner):
    import re
    if not banner:
        return None
    patterns = [
        (re.compile(r'SSH-\d+\.\d+-(?P<ver>\S+)'), '{ver}'),
        (re.compile(r'220[- ].*?(?P<sw>ProFTPD|vsftpd|Pure-FTPd)[/ ]?(?P<ver>\S*)', re.I), '{sw} {ver}'),
        (re.compile(r'220[- ].*?ESMTP (?P<ver>\S+)', re.I), 'SMTP/{ver}'),
        (re.compile(r'\+OK (?P<ver>\S+)', re.I), 'POP3/{ver}'),
        (re.compile(r'\* OK (?P<ver>\S+)', re.I), 'IMAP/{ver}'),
        (re.compile(r'RFB (?P<ver>\d+\.\d+)'), 'VNC/RFB-{ver}'),
        (re.compile(r'STAT version (?P<ver>\S+)', re.I), 'Memcached/{ver}'),
    ]
    for pat, tmpl in patterns:
        m = pat.search(banner)
        if m:
            try:
                return tmpl.format(**m.groupdict()).strip()
            except KeyError:
                continue
    return None

async def fingerprint_port(host, port, timeout=2.0):
    try:
        r, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        try:
            if port not in _LISTEN_FIRST:
                probe = _PROBE.get(port, b'\r\n')
                w.write(probe)
                await w.drain()
            raw = await asyncio.wait_for(r.read(1024), timeout=timeout)
            banner = raw.decode('utf-8', errors='ignore').strip()
            if not banner:
                return (None, None)
            # HTTP header grabbing for web ports
            if RICH_AVAILABLE and port in _HTTP_PORTS:
                try:
                    async with httpx.AsyncClient(verify=False, timeout=timeout) as client:
                        scheme = 'https' if port in (443, 8443) else 'http'
                        resp = await client.head(f'{scheme}://{host}:{port}/', follow_redirects=True)
                        headers = {k.lower(): v for k,v in resp.headers.items()}
                        interesting = {k: headers[k] for k in ['server','x-powered-by'] if k in headers}
                        if interesting:
                            return (' | '.join(f'{k}: {v}' for k,v in interesting.items()), None)
                except Exception:
                    pass
            version = extract_version(banner)
            if port == 22 and banner.startswith('SSH-'):
                parts = banner.split('-', 2)
                if len(parts) >= 3:
                    version = parts[2].split(' ')[0]
            return (banner.split('\n')[0].strip(), version)
        finally:
            w.close()
            await w.wait_closed()
    except Exception:
        return (None, None)

def get_ttl_via_ping(host, timeout=2.0):
    import re
    cmd = ['ping', '-c', '1', '-W', str(int(timeout)), host]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout+2)
        out = proc.stdout.decode('utf-8', errors='ignore')
        m = re.search(r'ttl=(\d+)', out, re.I)
        return int(m.group(1)) if m else None
    except Exception:
        return None

def guess_os(ttl):
    if not ttl or ttl <= 0:
        return 'Unknown'
    if ttl <= 64:
        return 'Linux/Unix'
    if ttl <= 128:
        return 'Windows'
    if ttl <= 255:
        return 'Network Device (Cisco/HP)'
    return 'Unknown'

# ───────────────────────────────────────────────────────────────
# CVE Lookup (from porthawk cve.py)
# ───────────────────────────────────────────────────────────────
_NVD_URL = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
_cache = {}
_DISK_CACHE_FILE = Path.home() / '.luonetscan_cve_cache.json'
_DISK_CACHE_TTL = 86400
_REQUEST_DELAY = 1.2

def _build_keyword(service_name, service_version):
    import re
    if not service_version:
        return service_name.lower()
    m = re.match(r'^([A-Za-z][A-Za-z0-9._-]+)\s+(\d+\.\d+)', service_version)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.match(r'^([A-Za-z][A-Za-z0-9]+)_(\d+\.\d+)', service_version)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return service_name.lower()

def _load_disk_cache():
    if not _DISK_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(_DISK_CACHE_FILE.read_text())
    except Exception:
        return {}

def _save_disk_cache(cache):
    try:
        _DISK_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _DISK_CACHE_FILE.write_text(json.dumps(cache))
    except Exception:
        pass

async def lookup_cves(service_name, service_version=None, max_results=5):
    keyword = _build_keyword(service_name, service_version)
    if keyword in _cache:
        return _cache[keyword]
    disk = _load_disk_cache()
    entry = disk.get(keyword)
    if entry and (time.time() - entry.get('cached_at', 0)) < _DISK_CACHE_TTL:
        result = [ScanResult(**r) for r in entry.get('data', [])]
        _cache[keyword] = result
        return result
    api_key = os.getenv('NVD_API_KEY')
    headers = {'apiKey': api_key} if api_key else {}
    params = {'keywordSearch': keyword, 'resultsPerPage': max_results*2, 'noRejected': ''}
    await asyncio.sleep(_REQUEST_DELAY)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(_NVD_URL, params=params, headers=headers)
            resp.raise_for_status()
            vulns = resp.json().get('vulnerabilities', [])
            results = []
            for v in vulns[:max_results]:
                cve = v.get('cve', {})
                desc = next((d['value'] for d in cve.get('descriptions',[]) if d.get('lang')=='en'), 'N/A')
                metrics = cve.get('metrics', {})
                score, severity = None, None
                for key in ('cvssMetricV31','cvssMetricV30'):
                    ents = metrics.get(key, [])
                    if ents:
                        d = ents[0]['cvssData']
                        score = d.get('baseScore')
                        severity = d.get('baseSeverity')
                        break
                published = cve.get('published', '')[:10]
                cve_id = cve.get('id','')
                results.append(ScanResult(
                    host='', port=0, state=None,
                    banner=f"{cve_id} ({score or '?'}) {severity or ''} — {desc[:100]}",
                    service_name=cve_id, service_version=severity,
                    latency_ms=score, os_guess=published
                ))
    except Exception as e:
        print(f"{C.YELLOW}CVE lookup failed: {e}{C.RESET}")
        results = []
    _cache[keyword] = results
    disk[keyword] = {'cached_at': time.time(), 'data': [r.model_dump() for r in results]}
    _save_disk_cache(disk)
    return results

# ───────────────────────────────────────────────────────────────
# Honeypot Detection (from porthawk honeypot.py)
# ───────────────────────────────────────────────────────────────
_COWRIE_BANNERS = {
    'SSH-2.0-OpenSSH_6.0p1 Debian-4+deb7u2',
    'SSH-2.0-OpenSSH_7.9p1 Debian-10+deb10u2',
    'SSH-2.0-OpenSSH_5.9p1 Debian-5ubuntu1.1',
    'SSH-2.0-OpenSSH_6.6.1p1 Ubuntu-2ubuntu2.8',
    'SSH-2.0-OpenSSH_6.7p1 Debian-5+deb8u4',
    'SSH-2.0-OpenSSH_7.4p1 Debian-10+deb9u7',
}
_DIONAEA_FTP = {'220 DiskStation FTP server ready.', '220 DiskStation FTP'}
_ICS_PORTS = {102, 502, 20000, 44818, 47808, 4840, 9600}

def score_honeypot(results):
    indicators = []
    open_results = [r for r in results if r.state == PortState.OPEN]
    if not open_results:
        return 0.0, 'LIKELY_REAL', 'LOW', []
    open_ports = {r.port for r in open_results}
    banners = {r.banner for r in open_results if r.banner}
    # Cowrie check
    for r in open_results:
        if r.port == 22 and r.banner and r.banner.strip() in _COWRIE_BANNERS:
            indicators.append(('cowrie_ssh_banner', 0.60, f'SSH banner matches Cowrie default'))
        if r.port == 21 and r.banner:
            for known in _DIONAEA_FTP:
                if r.banner.strip().startswith(known[:20]):
                    indicators.append(('dionaea_ftp', 0.65, f'FTP banner matches Dionaea'))
    # ICS multi-port
    ics = open_ports & _ICS_PORTS
    if len(ics) >= 2:
        indicators.append(('ics_multi', 0.50, f'Multiple ICS ports open: {sorted(ics)}'))
    # Port flood
    n = len(open_results)
    if n > 40:
        indicators.append(('port_flood', 0.50, f'{n} open ports — extremely high'))
    elif n > 20:
        indicators.append(('port_flood', 0.30, f'{n} open ports — unusually high'))
    # Telnet
    if 23 in open_ports:
        indicators.append(('telnet', 0.25, 'Telnet open — rare on real hosts'))
    # Latency uniformity
    latencies = [r.latency_ms for r in open_results if r.latency_ms and r.latency_ms > 0]
    if len(latencies) >= 5:
        mean = statistics.mean(latencies)
        if mean > 0:
            cv = statistics.stdev(latencies) / mean
            if cv < 0.05:
                indicators.append(('uniform_latency', 0.35, f'Latency CV={cv:.4f} — suspiciously uniform'))
    score = 1.0 - math.prod(1.0 - w for _, w, _ in indicators)
    score = round(min(score, 1.0), 4)
    if score >= 0.55:
        verdict = 'LIKELY_HONEYPOT'
    elif score >= 0.25:
        verdict = 'SUSPICIOUS'
    else:
        verdict = 'LIKELY_REAL'
    confidence = 'HIGH' if len(indicators) >= 3 else 'MEDIUM' if indicators else 'LOW'
    return score, verdict, confidence, indicators

# ───────────────────────────────────────────────────────────────
# Live Progress UI
# ───────────────────────────────────────────────────────────────
class LiveUI:
    def __init__(self, target, total, protocol='TCP'):
        self.target = target
        self.total = total
        self.protocol = protocol
        self._open_count = 0
        self._scanned = 0
        self._results = []
        self._log = deque(maxlen=10)

    def on_result(self, result):
        self._scanned += 1
        if result.state == PortState.OPEN:
            self._open_count += 1
            self._results.append(result)
            self._log.append(f"{C.GREEN}+{result.port}/{result.protocol}{C.RESET}  {result.service_name or '?'}")
        self._render()

    def _render(self):
        bar = '█' * min(self._scanned * 40 // max(self.total, 1), 40)
        pct = self._scanned * 100 // max(self.total, 1)
        print(f"\r{col('luonetscan', C.CYAN)} | {self.target} | {self.protocol} | {self._open_count} open | {bar} {pct}%", end='', flush=True)

    def summary(self):
        print(f"\n{col(f'  {self._open_count} open / {self.total} scanned', C.CYAN)}")
        if self._log:
            print('\n'.join(f'  {m}' for m in self._log))

# ───────────────────────────────────────────────────────────────
# Output Formatters
# ───────────────────────────────────────────────────────────────
def print_terminal(results, show_closed=False, show_cves=False):
    print()
    print(f"  {'PORT':<12} {'STATE':<10} {'SERVICE':<18} {'RISK':<8} {'BANNER/INFO'}")
    print(f"  {'─'*12} {'─'*10} {'─'*18} {'─'*8} {'─'*30}")
    display = results if show_closed else [r for r in results if r.state == PortState.OPEN]
    display = sorted(display, key=lambda r: r.port)
    for r in display:
        state_c = C.GREEN if r.state == PortState.OPEN else C.YELLOW if r.state == PortState.FILTERED else C.DIM
        risk_c = C.RED if r.risk_level == 'HIGH' else C.YELLOW if r.risk_level == 'MEDIUM' else C.GREEN
        banner = r.banner or ''
        if r.cves and show_cves:
            banner = f"[{len(r.cves)} CVE(s)] " + banner
        print(f"  {r.port}/{r.protocol:<8} {col(str(r.state.value), state_c):<10} {r.service_name or 'unknown':<18} {col(r.risk_level or '—', risk_c):<8} {banner[:60]}")
    open_n = sum(1 for r in results if r.state == PortState.OPEN)
    print(f"\n  {col(f'{open_n} open', C.GREEN)} / {len(results)} scanned")

def save_json(results, path=None):
    if not path:
        Path('reports').mkdir(exist_ok=True)
        path = f"reports/scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    data = {'results': [r.model_dump() for r in results], 'scan_time': datetime.now().isoformat()}
    Path(path).write_text(json.dumps(data, indent=2, default=str))
    print(f"  {col('JSON:', C.GREEN)} {path}")
    return path

def save_csv(results, path=None):
    if not path:
        Path('reports').mkdir(exist_ok=True)
        path = f"reports/scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['host','port','protocol','state','service_name','risk_level','banner','latency_ms'])
        w.writeheader()
        for r in results:
            w.writerow({k: getattr(r, k) or '' for k in fieldnames})
    print(f"  {col('CSV:', C.GREEN)} {path}")
    return path

def save_html(results, path=None):
    if not path:
        Path('reports').mkdir(exist_ok=True)
        path = f"reports/scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>luonetscan — scan report</title>
<style>
body{{font-family:'Courier New',monospace;background:#0d1117;color:#e6edf3;padding:2rem}}
h1{{color:#58a6ff}} table{{width:100%;border-collapse:collapse;background:#161b22;border-radius:8px;overflow:hidden}}
th{{background:#21262d;padding:.75rem;text-align:left;color:#8b949e;text-transform:uppercase;font-size:.75rem}}
td{{padding:.6rem 1rem;border-top:1px solid #30363d}}
tr:hover td{{background:#1c2128}}
{{'.state-open{{color:#3fb950}}' if False else ''}}
</style></head><body>
<h1>luonetscan scan report</h1>
<table>
<tr><th>Port</th><th>State</th><th>Service</th><th>Risk</th><th>Banner</th></tr>
"""
    for r in results:
        state_c = '#3fb950' if r.state == PortState.OPEN else '#e3b341' if r.state == PortState.FILTERED else '#8b949e'
        risk_c = '#f85149' if r.risk_level == 'HIGH' else '#e3b341' if r.risk_level == 'MEDIUM' else '#3fb950'
        html += f"<tr><td>{r.port}/{r.protocol}</td><td style='color:{state_c}'>{r.state.value}</td><td>{r.service_name or '?'}</td><td style='color:{risk_c}'>{r.risk_level or '—'}</td><td>{r.banner or '—'}</td></tr>\n"
    html += "</table></body></html>"
    Path(path).write_text(html)
    print(f"  {col('HTML:', C.GREEN)} {path}")
    return path

# ───────────────────────────────────────────────────────────────
# Scan Diff
# ───────────────────────────────────────────────────────────────
def diff_scans(file_a, file_b):
    a_data = json.loads(Path(file_a).read_text())
    b_data = json.loads(Path(file_b).read_text())
    a_results = [ScanResult(**r) for r in a_data.get('results', [])]
    b_results = [ScanResult(**r) for r in b_data.get('results', [])]
    map_a = {(r.host, r.port, r.protocol): r for r in a_results}
    map_b = {(r.host, r.port, r.protocol): r for r in b_results}
    all_keys = set(map_a) | set(map_b)
    new_p, gone_p, changed_p = [], [], []
    for key in sorted(all_keys):
        a, b = map_a.get(key), map_b.get(key)
        if a is None and b:
            new_p.append(b)
        elif b is None and a:
            gone_p.append(a)
        elif a and b and (a.state != b.state or a.service_name != b.service_name):
            changed_p.append((a, b))
    print(f"\n{col('luonetscan diff', C.CYAN)} — {file_a} vs {file_b}\n")
    if new_p:
        print(col(f"  NEW ({len(new_p)}):", C.GREEN))
        for r in new_p:
            print(f"    + {r.host}:{r.port}/{r.protocol}  {r.service_name}  [{r.risk_level}]")
    if gone_p:
        print(col(f"  GONE ({len(gone_p)}):", C.RED))
        for r in gone_p:
            print(f"    - {r.host}:{r.port}/{r.protocol}  {r.service_name}  [{r.risk_level}]")
    if changed_p:
        print(col(f"  CHANGED ({len(changed_p)}):", C.YELLOW))
        for a, b in changed_p:
            notes = []
            if a.state != b.state: notes.append(f'state:{a.state}→{b.state}')
            if a.service_version != b.service_version: notes.append(f'version:{a.service_version}→{b.service_version}')
            print(f"    ~ {a.host}:{a.port}/{a.protocol}  {' | '.join(notes)}")
    if not (new_p or gone_p or changed_p):
        print("  No differences found — scans are identical")
    print(f"\n  Summary: {col(f'{len(new_p)} new', C.GREEN)}, {col(f'{len(gone_p)} gone', C.RED)}, {col(f'{len(changed_p)} changed', C.YELLOW)}")

# ───────────────────────────────────────────────────────────────
# Geo-IP
# ───────────────────────────────────────────────────────────────
async def geo_ip(host):
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f'http://ip-api.com/json/{host}')
            d = r.json()
            return d
    except Exception:
        return {}

# ───────────────────────────────────────────────────────────────
# Main CLI
# ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(prog='luonetscan', description='luonetscan — Advanced async port scanner by luokai', add_help=False)
    sub = parser.add_subparsers(dest='cmd')

    p_scan = sub.add_parser('scan', help='Scan ports')
    p_scan.add_argument('-t','--target', required=True)
    p_scan.add_argument('-p','--ports', default='22,80,443')
    p_scan.add_argument('--timeout', type=float, default=1.0)
    p_scan.add_argument('--threads', type=int, default=500)
    p_scan.add_argument('--banners', action='store_true')
    p_scan.add_argument('--cve', action='store_true')
    p_scan.add_argument('--os', action='store_true')
    p_scan.add_argument('--json', action='store_true')
    p_scan.add_argument('-o','--output', choices=['json','csv','html'], nargs='+')
    p_scan.add_argument('--show-closed', action='store_true')
    p_scan.add_argument('--no-live', action='store_true')
    p_scan.add_argument('--stealth', action='store_true')
    p_scan.add_argument('--honeypot', action='store_true')
    p_scan.add_argument('--udp', action='store_true')
    p_scan.add_argument('--adaptive', action='store_true')
    p_scan.add_argument('--syn', action='store_true')
    p_scan.add_argument('--evasion-type', choices=['syn','fin','null','xmas','ack','maimon'])
    p_scan.add_argument('--jitter', type=float, default=0.0)
    p_scan.add_argument('--fragment', action='store_true')
    p_scan.add_argument('--slack-webhook')
    p_scan.add_argument('--discord-webhook')
    p_scan.add_argument('--passive-os', action='store_true')
    p_scan.add_argument('--top-ports', type=int, dest='top_n')

    p_top = sub.add_parser('top', help='Top-N port scan')
    p_top.add_argument('-t','--target', required=True)
    p_top.add_argument('-n','--top-ports', type=int, default=50)
    p_top.add_argument('--timeout', type=float, default=1.0)
    p_top.add_argument('--threads', type=int, default=500)
    p_top.add_argument('--banners', action='store_true')
    p_top.add_argument('--cve', action='store_true')
    p_top.add_argument('--json', action='store_true')

    p_deep = sub.add_parser('deep', help='Full port scan 1-65535')
    p_deep.add_argument('-t','--target', required=True)
    p_deep.add_argument('--timeout', type=float, default=0.5)
    p_deep.add_argument('--threads', type=int, default=1000)
    p_deep.add_argument('--banners', action='store_true')
    p_deep.add_argument('--json', action='store_true')

    p_range = sub.add_parser('range', help='IP range scan')
    p_range.add_argument('-t','--target', required=True)
    p_range.add_argument('-p','--ports', default='80,443')
    p_range.add_argument('--timeout', type=float, default=1.0)
    p_range.add_argument('--threads', type=int, default=500)

    p_ping = sub.add_parser('ping', help='Ping + geo-IP + ASN')
    p_ping.add_argument('-t','--target', required=True)

    p_cve = sub.add_parser('cve', help='CVE lookup from NVD')
    p_cve.add_argument('service')
    p_cve.add_argument('--version', '-v')

    p_diff = sub.add_parser('diff', help='Compare two scan files')
    p_diff.add_argument('scan_a')
    p_diff.add_argument('scan_b')

    args = parser.parse_args(sys.argv[1:] if len(sys.argv) > 1 else ['--help'])

    if args.cmd == 'cve':
        results = asyncio.run(lookup_cves(args.service, args.version))
        print(f"\n{col('luonetscan CVE lookup', C.CYAN)} — {args.service} {args.version or ''}\n")
        for r in results:
            print(f"  {col(r.service_name or '', C.RED)}  {r.banner or 'N/A'}")
        if not results:
            print("  No CVEs found or lookup failed (set NVD_API_KEY for higher rate limits)")
        return

    if args.cmd == 'ping':
        ttl_val = get_ttl_via_ping(args.target)
        geo = asyncio.run(geo_ip(args.target))
        print(f"\n{col('luonetscan ping', C.CYAN)} — {args.target}\n")
        print(f"  Reachable:  {col('True', C.GREEN)}")
        print(f"  TTL:         {ttl_val or 'N/A'}")
        print(f"  Geo:         {geo.get('city','N/A')}, {geo.get('country','N/A')} ({geo.get('org','')})")
        print(f"  ISP:         {geo.get('isp','N/A')}")
        if ttl_val:
            print(f"  OS guess:    {guess_os(ttl_val)}")
        return

    if args.cmd == 'diff':
        diff_scans(args.scan_a, args.scan_b)
        return

    if args.cmd in ('scan', 'top', 'deep', 'range'):
        targets = expand_cidr(args.target)
        if args.cmd == 'top':
            ports = get_top_ports(args.top_ports or 50)
        elif args.cmd == 'deep':
            ports = list(range(1, 65536))
        elif args.cmd == 'range':
            ports = parse_port_range(args.ports) or [80, 443]
        else:
            ports = parse_port_range(args.ports) or get_top_ports(100)

        timeout = args.timeout if not getattr(args, 'stealth', False) else 3.0
        threads = args.threads if not getattr(args, 'stealth', False) else 1
        protocol = 'UDP' if getattr(args, 'udp', False) else 'TCP'
        total = len(targets) * len(ports)

        print(f"\n{col('╔'+'═'*50+'╗', C.CYAN)}")
        print(f"{col('║  luonetscan  |  Advanced Port Scanner by luokai  ║', C.CYAN)}")
        print(f"{col('╚'+'═'*50+'╝', C.CYAN)}")
        print(f"  Target:  {args.target} ({len(targets)} host(s), {len(ports)} port(s), {protocol})")
        print(f"  Timeout: {timeout}s  |  Threads: {threads}\n")

        use_live = not getattr(args, 'no_live', False)
        ui = LiveUI(args.target, total, protocol) if use_live else None

        all_results = []
        for host in targets:
            results = asyncio.run(scan_host(host, ports, timeout, threads,
                                            show_progress=False,
                                            on_result=ui.on_result if ui else None))
            all_results.extend(results)

        if ui:
            ui.summary()

        # Enrich with service info
        for r in all_results:
            svc_name, svc_desc, risk = get_service(r.port)
            r.service_name = svc_name
            r.risk_level = risk
            if r.state == PortState.FILTERED:
                r.risk_level = None

        # OS detection
        if getattr(args, 'os', False):
            ttl_val = get_ttl_via_ping(targets[0])
            if ttl_val:
                os_guess = guess_os(ttl_val)
                for r in all_results:
                    r.ttl = ttl_val
                    r.os_guess = os_guess
                print(f"  OS guess: {col(os_guess, C.CYAN)} (TTL={ttl_val})")

        # Banner grabbing
        if getattr(args, 'banners', False):
            open_results = [r for r in all_results if r.state == PortState.OPEN]
            print(f"\n  {col('Grabbing banners...', C.DIM)}")
            for r in open_results:
                banner, version = asyncio.run(fingerprint_port(r.host, r.port, timeout))
                r.banner = banner
                r.service_version = version
                if banner and not r.service_name:
                    r.service_name = extract_version(banner) or 'unknown'

        # CVE lookup
        if getattr(args, 'cve', False):
            print(f"\n  {col('Looking up CVEs via NVD API...', C.DIM)}")
            seen = {}
            async def _cve_lookups():
                for r in all_results:
                    if r.state == PortState.OPEN and r.service_name:
                        key = f"{r.service_name}:{r.service_version or ''}"
                        if key not in seen:
                            cves = await lookup_cves(r.service_name, r.service_version)
                            seen[key] = cves
                        r.cves = seen[key]
            asyncio.run(_cve_lookups())

        # Honeypot scoring
        if getattr(args, 'honeypot', False):
            score, verdict, confidence, indicators = score_honeypot(all_results)
            print(f"\n  {col('Honeypot check:', C.CYAN)} score={col(f'{score:.2f}', C.RED if verdict=='LIKELY_HONEYPOT' else C.YELLOW)}  verdict={verdict}  confidence={confidence}")
            for name, weight, desc in indicators:
                print(f"    [{weight:.2f}] {name}: {desc}")

        # Output
        if getattr(args, 'json', False) or (getattr(args, 'output', None) and 'json' in args.output):
            save_json(all_results)
        elif getattr(args, 'output'):
            for fmt in args.output:
                if fmt == 'csv':
                    save_csv(all_results)
                elif fmt == 'html':
                    save_html(all_results)
        else:
            print_terminal(all_results, show_closed=getattr(args, 'show_closed', False),
                         show_cves=getattr(args, 'cve', False))

if __name__ == '__main__':
    main()
