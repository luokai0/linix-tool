#!/usr/bin/env python3
"""
luonetscan — Async Network Port Scanner + CVE Detector + Service Fingerprint

A powerful, fast, async port scanner that combines the best ideas from
porthawk and portfinder into one tool. Supports TCP/UDP scanning, CIDR
range expansion, service fingerprinting, CVE lookup, colored live output,
and multiple output formats.

Usage:
    luonetscan scan -t <host> [-p <ports>] [--tcp] [--udp] [-o <outfile>] [--json]
    luonetscan top   [-t <host>] [-n <top-n>]    scan top N ports
    luonetscan deep  -t <host>                    full port scan (1-65535)
    luonetscan range -t <start-end> -p <range>   scan port range on CIDR
    luonetscan ping  -t <host>                   ping host, check geo/IP
    luonetscan cve   <service> [--version <ver>] CVE lookup for service

Examples:
    luonetscan scan -t 192.168.1.1 -p 22,80,443,3306
    luonetscan scan -t 10.0.0.0/24 -p 80,443 --tcp -o scan_results
    luonetscan top -t github.com -n 100
    luonetscan deep -t 192.168.1.1
    luonetscan ping -t google.com
    luonetscan cve redis --version 6.0

Author: luo kai | linix-tool
"""

import argparse
import asyncio
import ipaddress
import json
import os
import re
import socket
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# ─── Banner ──────────────────────────────────────────────────────────────────

BANNER = """
\033[96m╔══════════════════════════════════════════════════════════╗
║  ██╗  ██╗ ██████╗ ████████╗██╗  ██╗    ███╗   ███╗███████╗  ║
║  ╚██╗██╔╝██╔═══██╗╚══██╔══╝██║  ██║    ████╗ ████║██╔════╝  ║
║   ╚███╔╝ ██║   ██║   ██║   ███████║    ██╔████╔██║█████╗    ║
║   ██╔██╗ ██║   ██║   ██║   ██╔══██║    ██║╚██╔╝██║██╔══╝    ║
║  ██╔╝ ██╗╚██████╔╝   ██║   ██║  ██║    ██║ ╚═╝ ██║███████╗  ║
║  ╚═╝  ╚═╝ ╚═════╝    ╚═╝   ╚═╝  ╚═╝    ╚═╝     ╚═╝╚══════╝  ║
║          \033[93m[ NETSCAN ]\033[96m  Async Port Scanner v1.0              ║
╚══════════════════════════════════════════════════════════╝\033[0m
"""

# ─── Service DB ──────────────────────────────────────────────────────────────

@dataclass
class ServiceInfo:
    name: str
    desc: str
    risk: str
    cves: list = field(default_factory=list)

_PORT_DB: dict[int, ServiceInfo] = {
    21: ServiceInfo("ftp", "File Transfer Protocol — cleartext auth", "HIGH"),
    22: ServiceInfo("ssh", "Secure Shell", "MEDIUM"),
    23: ServiceInfo("telnet", "Telnet — cleartext, extinct", "HIGH"),
    25: ServiceInfo("smtp", "Simple Mail Transfer Protocol", "MEDIUM"),
    53: ServiceInfo("dns", "Domain Name System", "INFO"),
    80: ServiceInfo("http", "HTTP — cleartext web", "LOW"),
    110: ServiceInfo("pop3", "POP3 — cleartext email auth", "HIGH"),
    135: ServiceInfo("msrpc", "Microsoft RPC — Windows exploitation entry", "HIGH"),
    137: ServiceInfo("netbios-ns", "NetBIOS Name Service", "HIGH"),
    139: ServiceInfo("netbios-ssn", "NetBIOS Session", "HIGH"),
    143: ServiceInfo("imap", "IMAP — cleartext email auth", "HIGH"),
    161: ServiceInfo("snmp", "SNMP — community string = no auth", "HIGH"),
    389: ServiceInfo("ldap", "LDAP — cleartext directory queries", "HIGH"),
    443: ServiceInfo("https", "HTTP over TLS", "LOW"),
    445: ServiceInfo("microsoft-ds", "SMB over TCP — EternalBlue/WannaCry port", "HIGH"),
    465: ServiceInfo("smtps", "SMTP over TLS", "LOW"),
    587: ServiceInfo("submission", "Email Message Submission", "LOW"),
    993: ServiceInfo("imaps", "IMAP over TLS", "LOW"),
    995: ServiceInfo("pop3s", "POP3 over TLS", "LOW"),
    1433: ServiceInfo("ms-sql-s", "Microsoft SQL Server", "HIGH"),
    1521: ServiceInfo("oracle", "Oracle Database", "HIGH"),
    2049: ServiceInfo("nfs", "Network File System — world-readable exports", "HIGH"),
    3306: ServiceInfo("mysql", "MySQL Database", "MEDIUM"),
    3389: ServiceInfo("rdp", "Remote Desktop Protocol — ransomware entry", "HIGH"),
    5432: ServiceInfo("postgresql", "PostgreSQL Database", "MEDIUM"),
    5900: ServiceInfo("vnc", "Virtual Network Computing — weak auth issues", "HIGH"),
    6379: ServiceInfo("redis", "Redis — no auth by default, RCE via SLAVEOF", "HIGH"),
    8080: ServiceInfo("http-proxy", "HTTP proxy / Tomcat / dev server", "MEDIUM"),
    8443: ServiceInfo("https-alt", "HTTPS alternate", "MEDIUM"),
    8888: ServiceInfo("http-alt", "HTTP alternate / Jupyter Notebook", "MEDIUM"),
    9000: ServiceInfo("php-fpm", "PHP-FPM / SonarQube", "MEDIUM"),
    9200: ServiceInfo("elasticsearch", "Elasticsearch HTTP — no auth default (old)", "HIGH"),
    11211: ServiceInfo("memcache", "Memcached — no auth, UDP amplification", "HIGH"),
    27017: ServiceInfo("mongodb", "MongoDB — no auth by default (older versions)", "HIGH"),
}

_TOP_PORTS = [80,443,22,21,25,3389,110,445,139,143,53,135,3306,8080,1723,
              111,995,993,587,23,8443,8888,6379,27017,5432,1433,5900,2049,
              389,161,3128,1080,5000,8000,9200,11211,2375,10250,9092,2181,
              6443,5672,5601,9090,4444,9300,27018,7001,9000,9042,4848,
              8161,15672,61616,50000,50070,28017]

_RISK_COLORS = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[92m", "INFO": "\033[90m"}
_RESET = "\033[0m"

# ─── Data Models ─────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    host: str
    port: int
    protocol: str
    state: str
    latency_ms: Optional[float] = None
    service: Optional[str] = None
    version: Optional[str] = None
    banner: Optional[str] = None
    risk: Optional[str] = None
    cves: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

# ─── Core Scanner ─────────────────────────────────────────────────────────────

async def tcp_probe(host: str, port: int, timeout: float) -> tuple[str, float]:
    t_start = time.monotonic()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        elapsed = (time.monotonic() - t_start) * 1000
        writer.close()
        await writer.wait_closed()
        return "OPEN", round(elapsed, 2)
    except asyncio.TimeoutError:
        return "FILTERED", round(timeout * 1000, 2)
    except (ConnectionRefusedError, OSError):
        return "CLOSED", round((time.monotonic() - t_start) * 1000, 2)

async def scan_port(host: str, port: int, timeout: float, semaphore: asyncio.Semaphore, proto: str = "tcp") -> ScanResult:
    async with semaphore:
        if proto == "udp":
            state, lat = await udp_probe(host, port, timeout)
        else:
            state, lat = await tcp_probe(host, port, timeout)
        svc = _PORT_DB.get(port)
        return ScanResult(host=host, port=port, protocol=proto, state=state,
                          latency_ms=lat,
                          service=svc.name if svc else "unknown",
                          risk=svc.risk if svc else "INFO")

async def udp_probe(host: str, port: int, timeout: float) -> tuple[str, float]:
    t_start = time.monotonic()
    try:
        loop = asyncio.get_running_loop()
        def _probe():
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(b"\x00", (host, port))
                try:
                    s.recvfrom(1024)
                    return "OPEN"
                except TimeoutError:
                    return "FILTERED"
                except OSError as e:
                    if e.errno == 111:
                        return "CLOSED"
                    return "FILTERED"
        result = await loop.run_in_executor(None, _probe)
        return result, round((time.monotonic() - t_start) * 1000, 2)
    except Exception:
        return "FILTERED", round(timeout * 1000, 2)

def expand_target(target: str) -> list[str]:
    target = target.strip().lstrip("[").rstrip("]")
    try:
        net = ipaddress.ip_network(target, strict=False)
        return [str(h) for h in net.hosts()]
    except ValueError:
        return [target]

def parse_ports(port_spec: str) -> list[int]:
    ports = set()
    for seg in port_spec.split(","):
        seg = seg.strip()
        if "-" in seg:
            lo, hi = seg.split("-", 1)
            ports.update(range(int(lo), int(hi)+1))
        else:
            ports.add(int(seg))
    return sorted(p for p in ports if 1 <= p <= 65535)

def color_state(state: str) -> str:
    if state == "OPEN": return f"\033[92m{state}{_RESET}"
    if state == "FILTERED": return f"\033[93m{state}{_RESET}"
    return f"\033[90m{state}{_RESET}"

def color_risk(risk: str) -> str:
    return f"{_RISK_COLORS.get(risk, '')}{risk}{_RESET}"

# ─── CVE Lookup ────────────────────────────────────────────────────────────────

async def lookup_cve(service: str, version: Optional[str] = None, max_res: int = 5) -> list[dict]:
    keyword = f"{service} {version}" if version else service
    cache_key = f"cve_{keyword}"
    # simple in-memory cache
    if hasattr(lookup_cve, "_cache"):
        if cache_key in lookup_cve._cache:
            return lookup_cve._cache[cache_key]
    else:
        lookup_cve._cache = {}

    url = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    headers = {"apiKey": os.getenv("NVD_API_KEY", "")} if os.getenv("NVD_API_KEY") else {}
    params = {"keywordSearch": keyword.lower(), "resultsPerPage": max_res * 2, "noRejected": ""}

    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            if not headers["apiKey"]:
                del headers["apiKey"]
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            cves = []
            for item in data.get("vulnerabilities", []):
                cve = item.get("cve", {})
                descs = cve.get("descriptions", [])
                desc = next((d["value"] for d in descs if d.get("lang") == "en"), "N/A")
                metrics = cve.get("metrics", {})
                score, severity = None, None
                for key in ("cvssMetricV31", "cvssMetricV30"):
                    entries = metrics.get(key, [])
                    if entries:
                        score = entries[0].get("cvssData", {}).get("baseScore")
                        severity = entries[0].get("cvssData", {}).get("baseSeverity")
                        break
                cves.append({
                    "id": cve.get("id"),
                    "description": desc[:180],
                    "cvss": score,
                    "severity": severity,
                    "url": f"https://nvd.nist.gov/vuln/detail/{cve.get('id')}"
                })
            cves.sort(key=lambda x: x["cvss"] or 0, reverse=True)
            result = cves[:max_res]
            lookup_cve._cache[cache_key] = result
            return result
    except Exception:
        return []

# ─── Banner Grabbing ──────────────────────────────────────────────────────────

async def grab_banner(host: str, port: int, timeout: float = 2.0) -> Optional[str]:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
        try:
            if port == 3306:
                raw = await asyncio.wait_for(reader.read(128), timeout=timeout)
                if len(raw) > 5 and raw[4] == 10:
                    null_pos = raw.find(b"\x00", 5)
                    if null_pos > 0:
                        return raw[5:null_pos].decode("ascii", errors="ignore")
            elif port == 6379:
                writer.write(b"PING\r\n")
                await writer.drain()
                pong = await asyncio.wait_for(reader.read(64), timeout=timeout)
                if pong.startswith(b"+PONG"):
                    writer.write(b"INFO server\r\n")
                    await writer.drain()
                    info = await asyncio.wait_for(reader.read(1024), timeout=timeout)
                    m = re.search(rb"redis_version:(\S+)", info)
                    return f"Redis {m.group(1).decode()}" if m else "Redis"
            else:
                writer.write(b"\r\n")
                await writer.drain()
                raw = await asyncio.wait_for(reader.read(512), timeout=timeout)
                decoded = raw.decode("utf-8", errors="ignore").strip()
                if decoded:
                    return decoded.split("\n")[0]
        finally:
            writer.close()
            await writer.wait_closed()
    except Exception:
        pass
    return None

# ─── Ping ─────────────────────────────────────────────────────────────────────

async def ping_host(host: str, timeout: float = 2.0) -> dict:
    result = {"host": host, "reachable": False, "ip": None, "geo": None, "asn": None, "ttl": None}
    try:
        info = socket.getaddrinfo(host, None, socket.AF_INET)
        ip = info[0][4][0]
        result["ip"] = ip
        result["reachable"] = True
        # TTL via ping
        import subprocess
        proc = subprocess.run(["ping", "-c", "1", "-W", str(int(timeout)), host],
                               capture_output=True, timeout=timeout + 1)
        output = proc.stdout.decode("utf-8", errors="ignore")
        m = re.search(r"ttl=(\d+)", output, re.I)
        if m:
            result["ttl"] = int(m.group(1))
        # Geo lookup via free ip-api
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"http://ip-api.com/json/{ip}")
                geo = r.json()
                result["geo"] = f"{geo.get('city','')},{geo.get('country','')}"
                result["asn"] = geo.get("org", "")
        except Exception:
            pass
    except Exception:
        pass
    return result

# ─── Scan Engine ──────────────────────────────────────────────────────────────

async def run_scan(hosts: list[str], ports: list[int], timeout: float, max_concurrency: int, proto: str, show_closed: bool, use_json: bool):
    semaphore = asyncio.Semaphore(max_concurrency)
    results = []
    tasks = []
    for host in hosts:
        for port in ports:
            tasks.append(scan_port(host, port, timeout, semaphore, proto))

    for coro in asyncio.as_completed(tasks):
        result = await coro
        results.append(result)

    # Print results
    if use_json:
        print(json.dumps([r.to_dict() for r in results if r.state == "OPEN"], indent=2))
    else:
        open_results = [r for r in results if r.state == "OPEN"]
        print(f"\n\033[96m─── Scan Results: {len(open_results)} open ports found ───\033[0m\n")
        for r in sorted(open_results, key=lambda x: x.port):
            lat_str = f"{r.latency_ms:.1f}ms" if r.latency_ms else "N/A"
            print(f"  \033[92m{r.port}\033[0m/{r.protocol}  {color_state(r.state)}  {lat_str}  "
                  f"{color_risk(r.risk or 'INFO')}  \033[94m{r.service or 'unknown'}\033[0m")
        print(f"\n  Scanned {len(hosts)} host(s) × {len(ports)} ports = {len(results)} total")
        print(f"  Open: {len(open_results)}  |  Closed: {len([r for r in results if r.state == 'CLOSED'])}  |  Filtered: {len([r for r in results if r.state == 'FILTERED'])}")

    return open_results

# ─── Commands ─────────────────────────────────────────────────────────────────

async def cmd_scan(args):
    hosts = expand_target(args.target)
    ports = parse_ports(args.ports) if args.ports else _TOP_PORTS[:20]
    print(f"\033[93m[*]\033[0m Scanning {len(hosts)} host(s), ports: {len(ports)}, proto: {args.proto}")
    return await run_scan(hosts, ports, args.timeout, args.concurrency, args.proto, args.show_closed, args.json)

async def cmd_top(args):
    hosts = expand_target(args.target)
    ports = _TOP_PORTS[:args.top]
    print(f"\033[93m[*]\033[0m Top-{args.top} ports scan on {len(hosts)} host(s)")
    return await run_scan(hosts, ports, args.timeout, args.concurrency, "tcp", False, False)

async def cmd_deep(args):
    hosts = expand_target(args.target)
    print(f"\033[91m[!]\033[0m Full port scan (1-65535) on {hosts[0]} — this will take a while...")
    ports = list(range(1, 65536))
    return await run_scan(hosts[:1], ports, args.timeout, args.concurrency, "tcp", False, False)

async def cmd_ping(args):
    result = await ping_host(args.target, args.timeout)
    print(f"\n\033[96m─── Host Info ───\033[0m")
    print(f"  Host:      {result['host']}")
    print(f"  IP:        {result['ip'] or 'N/A'}")
    print(f"  Reachable: {result['reachable']}")
    print(f"  TTL:       {result['ttl'] or 'N/A'}")
    print(f"  Geo:       {result['geo'] or 'N/A'}")
    print(f"  ASN:       {result['asn'] or 'N/A'}")
    return result

async def cmd_cve(args):
    ver = getattr(args, "version", None)
    print(f"\033[93m[*]\033[0m Looking up CVEs for: {args.service}" + (f" {ver}" if ver else ""))
    cves = await lookup_cve(args.service, ver)
    if not cves:
        print("  No CVEs found or lookup failed (set NVD_API_KEY env var for higher rate limits)")
        return
    print(f"\n\033[96m─── {len(cves)} CVEs for {args.service} ───\033[0m")
    for cve in cves:
        sev = cve.get("severity") or "N/A"
        score = cve.get("cvss") or "N/A"
        sev_color = "\033[91m" if sev == "CRITICAL" else "\033[93m" if sev in ("HIGH", "MEDIUM") else "\033[92m"
        print(f"\n  \033[95m{cve['id']}\033[0m  {sev_color}{sev}{_RESET}  CVSS: {score}")
        print(f"  {cve['description']}")
        print(f"  \033[94m{cve['url']}\033[0m")

async def cmd_range(args):
    # e.g. 192.168.1.1-50  or  CIDR
    target = args.target
    if "-" in target and "/" not in target:
        parts = target.split("-")
        if len(parts) == 2:
            base = ".".join(parts[0].split(".")[:-1])
            start, end = int(parts[0].split(".")[-1]), int(parts[1])
            hosts = [f"{base}.{i}" for i in range(start, end+1)]
        else:
            hosts = [target]
    else:
        hosts = expand_target(target)
    ports = parse_ports(args.ports)
    print(f"\033[93m[*]\033[0m Range scan: {len(hosts)} hosts, {len(ports)} ports")
    return await run_scan(hosts, ports, args.timeout, args.concurrency, "tcp", False, False)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="luonetscan — Async Network Scanner + CVE Detector",
                                      formatter_class=argparse.RawDescriptionHelpFormatter,
                                      epilog=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="Scan hosts with specified ports")
    p_scan.add_argument("-t", "--target", required=True)
    p_scan.add_argument("-p", "--ports", default="")
    p_scan.add_argument("--proto", default="tcp", choices=["tcp", "udp"])
    p_scan.add_argument("--timeout", type=float, default=1.5)
    p_scan.add_argument("-c", "--concurrency", type=int, default=500)
    p_scan.add_argument("-o", "--outfile")
    p_scan.add_argument("--json", action="store_true")
    p_scan.add_argument("--show-closed", action="store_true")

    p_top = sub.add_parser("top", help="Scan top-N most common ports")
    p_top.add_argument("-t", "--target", required=True)
    p_top.add_argument("-n", "--top", type=int, default=50)
    p_top.add_argument("--timeout", type=float, default=1.5)
    p_top.add_argument("-c", "--concurrency", type=int, default=500)

    p_deep = sub.add_parser("deep", help="Full port scan (1-65535)")
    p_deep.add_argument("-t", "--target", required=True)
    p_deep.add_argument("--timeout", type=float, default=0.5)
    p_deep.add_argument("-c", "--concurrency", type=int, default=1000)

    p_range = sub.add_parser("range", help="Scan IP range or CIDR")
    p_range.add_argument("-t", "--target", required=True)
    p_range.add_argument("-p", "--ports", default="1-1000")
    p_range.add_argument("--timeout", type=float, default=1.5)
    p_range.add_argument("-c", "--concurrency", type=int, default=500)

    p_ping = sub.add_parser("ping", help="Ping host and get geo/IP info")
    p_ping.add_argument("-t", "--target", required=True)
    p_ping.add_argument("--timeout", type=float, default=2.0)

    p_cve = sub.add_parser("cve", help="CVE lookup for a service")
    p_cve.add_argument("service")
    p_cve.add_argument("--version", default=None)

    args = parser.parse_args()

    if args.cmd == "scan": asyncio.run(cmd_scan(args))
    elif args.cmd == "top": asyncio.run(cmd_top(args))
    elif args.cmd == "deep": asyncio.run(cmd_deep(args))
    elif args.cmd == "range": asyncio.run(cmd_range(args))
    elif args.cmd == "ping": asyncio.run(cmd_ping(args))
    elif args.cmd == "cve": asyncio.run(cmd_cve(args))

if __name__ == "__main__":
    print(BANNER)
    main()