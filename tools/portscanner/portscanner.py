#!/usr/bin/env python3
"""
portscanner — Fast async port scanner
Scan ports on a host, find open ports, detect services

Usage:
  python3 portscanner.py scan <host> [start_port] [end_port]
  python3 portscanner.py top <host>              -- scan top 100 ports
  python3 portscanner.py probe <host> <port>      -- detect service
"""

import sys
import socket
import asyncio
from concurrent.futures import ThreadPoolExecutor


async def check_port(host: str, port: int) -> tuple[int, bool, str]:
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=2
        )
        writer.close()
        await writer.wait_closed()
        try:
            service = socket.getservbyport(port)
        except OSError:
            service = 'unknown'
        return (port, True, service)
    except Exception:
        return (port, False, '')


async def scan_range(host: str, start: int = 1, end: int = 65535, concurrency: int = 500) -> list:
    ports = range(start, end + 1)
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(port):
        async with semaphore:
            return await check_port(host, port)

    results = await asyncio.gather(*[guarded(p) for p in ports])
    return [(p, svc) for p, open, svc in results if open]


def probe_service(host: str, port: int) -> dict:
    try:
        sock = socket.socket()
        sock.settimeout(3)
        sock.connect((host, port))
        banner = sock.recv(1024).decode('utf-8', errors='ignore').strip()
        sock.close()
        return {'port': port, 'open': True, 'banner': banner}
    except Exception as e:
        return {'port': port, 'open': False, 'error': str(e)}


TOP_PORTS = [21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443, 445, 993, 995,
             1723, 3306, 3389, 5900, 8080, 8443, 8888, 9000, 9200, 27017]


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)

    cmd, host = sys.argv[1], sys.argv[2]

    if cmd == 'scan':
        start = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        end = int(sys.argv[4]) if len(sys.argv) > 4 else 1024
        print(f"Scanning {host} ports {start}–{end}...")
        open_ports = asyncio.run(scan_range(host, start, end))
        for port, svc in sorted(open_ports):
            print(f"  ✅ {port:6d}  {svc:15s}")
        print(f"\nTotal open: {len(open_ports)}")

    elif cmd == 'top':
        print(f"Scanning top ports on {host}...")
        open_ports = asyncio.run(scan_range(host, 1, 10000))
        for port, svc in sorted(open_ports):
            print(f"  ✅ {port:6d}  {svc:15s}")
        print(f"\nTotal open: {len(open_ports)}")

    elif cmd == 'probe':
        result = probe_service(host, int(sys.argv[3]))
        if result['open']:
            print(f"  ✅ Port {result['port']} OPEN")
            if result.get('banner'):
                print(f"  Banner: {result['banner'][:200]}")
        else:
            print(f"  ❌ Port {result['port']} CLOSED")

    else:
        print(__doc__)