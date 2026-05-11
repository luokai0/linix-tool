#!/usr/bin/env python3
"""
srvemon — Service uptime monitor
Monitor HTTP/TCP services, alert on downtime, log latency

Usage:
  python3 srvemon.py monitor <url> [interval]
  python3 srvemon.py batch <file>             -- monitor all URLs from file
  python3 srvemon.py latency <url>            -- measure response time
"""

import sys
import time
import json
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path


ALERTS = []


def check_service(url: str) -> dict:
    start = time.time()
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            latency = (time.time() - start) * 1000
            return {'url': url, 'ok': True, 'status': resp.status, 'latency_ms': round(latency, 1)}
    except urllib.error.HTTPError as e:
        return {'url': url, 'ok': False, 'status': e.code, 'error': str(e)}
    except Exception as e:
        return {'url': url, 'ok': False, 'status': 0, 'error': str(e)}


def monitor_loop(url: str, interval: int = 30) -> None:
    print(f"Monitoring {url} every {interval}s — Ctrl+C to stop\n")
    while True:
        result = check_service(url)
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if result['ok']:
            print(f"  ✅ [{ts}] {result['status']}  {result['latency_ms']}ms")
        else:
            print(f"  ❌ [{ts}] {result.get('status','?')}  {result.get('error','?')}")
            ALERTS.append((url, result))
        time.sleep(interval)


def batch_monitor(filepath: str, interval: int = 30) -> None:
    urls = [u.strip() for u in open(filepath) if u.strip() and not u.startswith('#')]
    print(f"Monitoring {len(urls)} services every {interval}s\n")
    while True:
        ts = datetime.now().strftime('%H:%M:%S')
        results = [check_service(u) for u in urls]
        up = sum(1 for r in results if r['ok'])
        print(f"\n[{ts}] {up}/{len(urls)} up")
        for r in results:
            icon = '✅' if r['ok'] else '❌'
            detail = str(r.get('status', r.get('error', '?')))
            print(f"  {icon} {r['url'][:60]:60s}  {detail}")
        time.sleep(interval)


def measure_latency(url: str) -> dict:
    results = []
    for _ in range(5):
        r = check_service(url)
        if r['ok']:
            results.append(r['latency_ms'])
    if results:
        return {
            'url': url, 'samples': len(results),
            'min_ms': min(results), 'max_ms': max(results),
            'avg_ms': round(sum(results)/len(results), 1)
        }
    return {'url': url, 'error': 'all requests failed'}


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == 'monitor':
        url = sys.argv[2]
        interval = int(sys.argv[3]) if len(sys.argv) >= 4 else 30
        monitor_loop(url, interval)
    elif cmd == 'batch':
        interval = int(sys.argv[3]) if len(sys.argv) >= 4 else 30
        batch_monitor(sys.argv[2], interval)
    elif cmd == 'latency':
        result = measure_latency(sys.argv[2])
        if 'error' in result:
            print(f"❌ {result['error']}")
        else:
            print(f"  min:  {result['min_ms']}ms")
            print(f"  avg:  {result['avg_ms']}ms")
            print(f"  max:  {result['max_ms']}ms")
            print(f"  samples: {result['samples']}")
    else:
        print(__doc__)