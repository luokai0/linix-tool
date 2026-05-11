#!/usr/bin/env python3
"""
pingpong — Network connectivity toolkit
Ping hosts, trace routes, DNS lookups, port checks

Usage:
  pingpong.py ping <host> [count]
  pingpong.py trace <host>
  pingpong.py dns <domain>
  pingpong.py port <host> <port> [timeout]
  pingpong.py whois <domain>
  pingpong.py geo <host>
"""

import sys
import os
import time
import socket
import subprocess
import json
from datetime import datetime

# ─── Ping ───────────────────────────────────────────────────

def ping(host, count=4):
    print(f"\n  📡 Pinging {host} ({socket.gethostbyname(host)}) with {count} packets\n")
    cmd = ['ping', '-c', str(count), host]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=count * 5 + 5)
        lines = result.stdout.strip().split('\n')
        for line in lines[-6:]:
            print(f"  {line}")
        stats_line = [l for l in lines if 'rtt' in l or 'min/avg/max' in l]
        if stats_line:
            print(f"\n  ✅ {stats_line[0]}")
        return result.returncode == 0
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

# ─── Traceroute ─────────────────────────────────────────────

def traceroute(host):
    print(f"\n  🛤️  traceroute to {host}\n")
    cmd = ['traceroute', '-m', '15', '-w', '2', host]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
        return result.returncode == 0
    except Exception as e:
        print(f"  ❌ Error: {e}")
        # Try alternative
        try:
            cmd = ['tracert', host] if sys.platform == 'win32' else ['tracepath', host]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            print(result.stdout)
            return True
        except:
            return False

# ─── DNS Lookup ─────────────────────────────────────────────

def dns_lookup(domain):
    print(f"\n  🔍 DNS lookup for {domain}\n")
    try:
        ip = socket.gethostbyname(domain)
        print(f"  A record:  {ip}")
    except Exception as e:
        print(f"  ❌ A record: {e}")

    try:
        host, aliases, ips = socket.gethostbyaddr(socket.gethostbyname(domain))
        print(f"  PTR:       {host}")
    except:
        pass

    # Try common record types
    try:
        import dns.resolver
        for rtype in ['AAAA', 'MX', 'NS', 'TXT', 'CNAME']:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                for rdata in answers:
                    print(f"  {rtype}:    {rdata}")
            except:
                pass
    except ImportError:
        pass

    # nslookup fallback
    try:
        result = subprocess.run(
            ['nslookup', '-type=ANY', domain],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.split('\n')[2:8]:
            if line.strip():
                print(f"  ns:   {line.strip()}")
    except:
        pass

    return True

# ─── Port Check ─────────────────────────────────────────────

def port_check(host, port, timeout=3):
    print(f"\n  🔌 Checking {host}:{port} ... ", end='', flush=True)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, int(port)))
        sock.close()
        if result == 0:
            print(f"OPEN ✅")
            # Try to identify service
            try:
                service = socket.getservbyport(int(port))
                print(f"  Service: {service}")
            except:
                pass
            return True
        else:
            print(f"CLOSED ❌ (code: {result})")
            return False
    except Exception as e:
        print(f"ERROR ❌ {e}")
        return False

# ─── Whois ─────────────────────────────────────────────────

def whois(domain):
    print(f"\n  📋 Whois for {domain}\n")
    try:
        result = subprocess.run(
            ['whois', domain],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.split('\n')
        important = ['Domain Name', 'Registrar', 'Name Server', 'Created', 'Expiry', 'Status', 'Registrant']
        for line in lines:
            for keyword in important:
                if keyword in line:
                    print(f"  {line.strip()}")
        print(f"\n  Full whois saved. (Total {len(lines)} lines)")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

# ─── Geo IP ─────────────────────────────────────────────────

def geo_ip(host):
    print(f"\n  🗺️  Geolocation for {host}\n")
    try:
        ip = socket.gethostbyname(host)
    except:
        ip = host

    try:
        result = subprocess.run(
            ['curl', '-s', f'ip-api.com/json/{ip}?fields=status,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as'],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)
        if data.get('status') == 'fail':
            print(f"  ❌ Lookup failed")
            return False
        print(f"  IP:        {data.get('query', ip)}")
        print(f"  ISP:       {data.get('isp', 'N/A')}")
        print(f"  Org:       {data.get('org', 'N/A')}")
        print(f"  Location:  {data.get('city', '')}, {data.get('regionName', '')}, {data.get('country', '')}")
        print(f"  ZIP:       {data.get('zip', 'N/A')}")
        print(f"  Coords:    {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}")
        print(f"  Timezone:  {data.get('timezone', 'N/A')}")
        return True
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

# ─── Scan Common Ports ──────────────────────────────────────

def portscan(host, top_n=20):
    common_ports = [21, 22, 23, 25, 53, 80, 110, 143, 443, 465, 587, 993, 995,
                   1433, 1521, 3306, 3389, 5432, 5900, 6379, 8080, 8443, 27017]
    common_ports = common_ports[:top_n]
    print(f"\n  🔌 Scanning top {len(common_ports)} ports on {host} ...\n")
    open_ports = []
    for port in common_ports:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                try:
                    service = socket.getservbyport(port)
                except:
                    service = 'unknown'
                print(f"  ✅ {port}/tcp  {service}")
                open_ports.append(port)
        except:
            pass
    print(f"\n  Found {len(open_ports)} open ports: {open_ports}")
    return open_ports

# ─── Main ──────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'ping' and len(sys.argv) >= 3:
        host = sys.argv[2]
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 4
        ok = ping(host, count)
    elif cmd == 'trace' and len(sys.argv) >= 3:
        ok = traceroute(sys.argv[2])
    elif cmd == 'dns' and len(sys.argv) >= 3:
        ok = dns_lookup(sys.argv[2])
    elif cmd == 'port' and len(sys.argv) >= 4:
        host, port = sys.argv[2], sys.argv[3]
        timeout = float(sys.argv[4]) if len(sys.argv) > 4 else 3
        ok = port_check(host, port, timeout)
    elif cmd == 'scan' and len(sys.argv) >= 3:
        host = sys.argv[2]
        top_n = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        open_ports = portscan(host, top_n)
        ok = True
    elif cmd == 'whois' and len(sys.argv) >= 3:
        ok = whois(sys.argv[2])
    elif cmd == 'geo' and len(sys.argv) >= 3:
        ok = geo_ip(sys.argv[2])
    else:
        print(__doc__)
        ok = False

    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()