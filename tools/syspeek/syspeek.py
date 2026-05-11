#!/usr/bin/env python3
"""
syspeek — Real-time system monitor for Linux
Shows CPU, Memory, Disk, Network, and Top Processes live

Usage: python3 syspeek.py [refresh_rate]
Default refresh rate: 1 second
"""

import os
import sys
import time
import subprocess
from datetime import datetime

os.environ.setdefault('TERM', 'dumb')

def clear_screen():
    os.system('clear')

def get_cpu_usage():
    try:
        stat = open('/proc/stat').read().splitlines()[0]
        fields = stat.split()[1:]
        idle = int(fields[3])
        total = sum(int(f) for f in fields)
        return idle, total
    except:
        return 0, 1

def get_memory():
    try:
        meminfo = {}
        for line in open('/proc/meminfo'):
            parts = line.split()
            meminfo[parts[0]] = int(parts[1]) * 1024
        total = meminfo.get('MemTotal:', 0)
        available = meminfo.get('MemAvailable:', meminfo.get('MemFree', 0))
        used = total - available
        return used, total
    except:
        return 0, 0

def get_disk():
    try:
        result = subprocess.run(
            ['df', '-B1', '--output=used,size', '/'],
            capture_output=True, text=True, timeout=2
        )
        lines = result.stdout.strip().splitlines()
        if len(lines) >= 2:
            parts = lines[1].split()
            used = int(parts[0])
            total = int(parts[1])
            if total > 0:
                return used, total
    except:
        pass
    return None, None

def get_network():
    try:
        net = open('/proc/net/dev').read().splitlines()
        rx, tx = 0, 0
        for line in net[2:]:
            parts = line.split()
            if len(parts) >= 10:
                rx += int(parts[1])
                tx += int(parts[9])
        return rx, tx
    except:
        return 0, 0

def get_top_processes():
    try:
        result = subprocess.run(
            ['ps', 'aux', '--sort=-cpu'],
            capture_output=True, text=True, timeout=2
        )
        lines = result.stdout.strip().splitlines()[1:6]
        processes = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 11:
                cpu = float(parts[2])
                mem = float(parts[3])
                cmd = ' '.join(parts[10:])[:40]
                processes.append((cpu, mem, cmd))
        return processes
    except:
        return []

def format_bytes(num):
    if num is None:
        return "N/A"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if num < 1024:
            return f"{num:.1f}{unit}"
        num /= 1024
    return f"{num:.1f}PB"

def format_percent(part, total):
    if total is None or total == 0:
        return "N/A"
    return f"{(part/total)*100:.1f}%"

def bar_chart(percent, width=30):
    if percent is None:
        return '░' * width
    filled = int((min(percent, 100) / 100) * width)
    return '█' * filled + '░' * (width - filled)

def main():
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
    prev_idle, prev_total = get_cpu_usage()
    prev_rx, prev_tx = get_network()
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"  SYSPEEK — System Monitor (ctrl+c to exit)")
    print(f"{'='*60}\n")

    try:
        while True:
            mem_used, mem_total = get_memory()
            disk_used, disk_total = get_disk()
            curr_rx, curr_tx = get_network()
            processes = get_top_processes()

            curr_idle, curr_total = get_cpu_usage()
            cpu_delta = curr_total - prev_total
            idle_delta = curr_idle - prev_idle
            cpu_usage = 100 * (1 - idle_delta / cpu_delta) if cpu_delta > 0 else 0
            prev_idle, prev_total = curr_idle, curr_total

            net_delta = (curr_rx - prev_rx) / interval if interval > 0 else 0
            tx_delta = (curr_tx - prev_tx) / interval if interval > 0 else 0
            prev_rx, prev_tx = curr_rx, curr_tx

            uptime_seconds = time.time() - start_time
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            mins = int((uptime_seconds % 3600) // 60)
            secs = int(uptime_seconds % 60)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            clear_screen()
            print(f"\n  SYSPEEK  |  {timestamp}  |  Uptime: {days}d {hours}h {mins}m {secs}s")
            print(f"  {'─'*56}")

            mem_pct = (mem_used/mem_total)*100 if mem_total else None
            disk_pct = (disk_used/disk_total)*100 if disk_total else None

            print(f"\n  {'CPU':<8} {bar_chart(cpu_usage)} {format_percent(cpu_usage, 100)}")
            print(f"  {'RAM':<8} {bar_chart(mem_pct)} {format_bytes(mem_used)} / {format_bytes(mem_total)}")
            print(f"  {'DISK':<8} {bar_chart(disk_pct)} {format_bytes(disk_used) if disk_used else 'N/A'} / {format_bytes(disk_total) if disk_total else 'N/A'}")

            print(f"\n  {'NETWORK (live)':<18} ↓ {format_bytes(net_delta)}/s   ↑ {format_bytes(tx_delta)}/s")
            print(f"  {'CACHE (total)':<18} ↓ {format_bytes(curr_rx)}   ↑ {format_bytes(curr_tx)}")

            print(f"\n  {'─'*56}")
            print(f"  {'TOP PROCESSES':^54}")
            print(f"  {'─'*56}")
            print(f"  {'CPU%':>6}  {'MEM%':>6}  {'COMMAND':<40}")
            print(f"  {'─'*56}")
            for cpu, mem, cmd in processes:
                print(f"  {cpu:>5.1f}% {mem:>5.1f}%  {cmd:<40}")

            print(f"\n  {'─'*56}")
            print(f"  Refreshing every {interval}s...")
            time.sleep(interval)

    except KeyboardInterrupt:
        print(f"\n\n  Syspeek stopped.\n")

if __name__ == '__main__':
    main()