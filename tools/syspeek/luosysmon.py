#!/usr/bin/env python3
"""
luosysmon — Linux System Monitor
Complete CPU, memory, disk, network, process monitor
Built from glances + htop + psutil concepts
MIT License — luokai
"""

import csv
import fcntl
import json
import os
import socket
import struct
import sys
import termios
import time
from collections import defaultdict
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path

import psutil

# ── TERM UTIL ──────────────────────────────────────

def terminal_size():
    try:
        with open("/dev/tty") as tty:
            winsz = struct.unpack("HH", fcntl.ioctl(tty.fileno(), termios.TIOCGWINSZ, "8 Bytes"))
            return winsz[1], winsz[0]
    except Exception:
        try:
            import shutil
            return shutil.get_terminal_size()
        except Exception:
            return 120, 40

def color(code, text):
    return f"\x1b[{code}m{text}\x1b[0m"

C = type("C", (), {
    "RED": 31, "GREEN": 32, "YELLOW": 33, "BLUE": 34,
    "CYAN": 36, "WHITE": 37, "BRIGHT_RED": 91,
    "BRIGHT_GREEN": 92, "BRIGHT_YELLOW": 93,
})()

def c(val, thresholds):
    for t, col in thresholds:
        if val >= t:
            return color(col, f"{val:5.1f}")
    return f"{val:5.1f}"

CPU_T = [(90, C.BRIGHT_RED), (70, C.YELLOW), (50, C.GREEN), (0, C.CYAN)]
MEM_T = [(90, C.BRIGHT_RED), (70, C.YELLOW), (50, C.GREEN), (0, C.CYAN)]

def fmt_b(b):
    if b >= 1024**4: return f"{b/(1024**4):6.1f} TB"
    if b >= 1024**3: return f"{b/(1024**3):6.1f} GB"
    if b >= 1024**2: return f"{b/(1024**2):6.1f} MB"
    if b >= 1024:    return f"{b/1024:6.1f} KB"
    return f"{b:7d}  B"

def fmt_s(bps):
    if bps >= 1024**3: return f"{bps/(1024**3):6.1f} GB/s"
    if bps >= 1024**2: return f"{bps/(1024**2):6.1f} MB/s"
    if bps >= 1024:    return f"{bps/1024:6.1f} KB/s"
    return f"{bps:7.1f}  B/s"

def bar(pct, w=20):
    f = int(w * pct / 100)
    return "█" * f + "░" * (w - f)

# ── COLLECTOR ──────────────────────────────────────

class Collector:
    def __init__(self):
        self._prev_disk = None
        self._prev_net = {}
        self._prev_ts = None

    def _ctd(self, ct):
        return {
            "user": ct.user, "system": ct.system, "idle": ct.idle,
            "iowait": getattr(ct, "iowait", 0.0),
            "irq": getattr(ct, "irq", 0.0),
            "softirq": getattr(ct, "softirq", 0.0),
        }

    def cpu(self):
        ct = psutil.cpu_times()
        d = self._ctd(ct)
        tot = sum(d.values())
        def p(k): return (d[k]/tot*100) if tot else 0
        per_core = psutil.cpu_percent(percpu=True, interval=0)
        freq = psutil.cpu_freq()
        freq_mhz = freq.current if freq else 0
        temp = None
        try:
            temps = psutil.sensors_temperatures()
            for chip, entries in temps.items():
                for e in entries:
                    if "cpu" in chip.lower() or "core" in (e.label or "").lower():
                        temp = e.current
                        break
        except Exception:
            pass
        return dict(
            total=p("user")+p("system"),
            user=p("user"), system=p("system"), idle=p("idle"),
            iowait=p("iowait"), irq=p("irq"), softirq=p("softirq"),
            per_core=per_core, freq_mhz=freq_mhz, temperature=temp,
        )

    def mem(self):
        vm = psutil.virtual_memory()
        sw = psutil.swap_memory()
        return dict(
            total_gb=vm.total/(1024**3), available_gb=vm.available/(1024**3),
            used_gb=vm.used/(1024**3), percent=vm.percent,
            cached_gb=getattr(vm,"cached",0)/(1024**3),
            buffers_gb=getattr(vm,"buffers",0)/(1024**3),
            swap_total_gb=sw.total/(1024**3), swap_used_gb=sw.used/(1024**3),
            swap_percent=sw.percent,
        )

    def disks(self):
        now = time.time()
        dio = psutil.disk_io_counters(perdisk=True) or {}
        io_map = {}
        if self._prev_disk and self._prev_ts:
            dt = now - self._prev_ts
            for n, c in dio.items():
                p = self._prev_disk.get(n)
                if p:
                    io_map[n] = dict(
                        read_speed=max(0,(c.read_bytes-p.read_bytes)/dt),
                        write_speed=max(0,(c.write_bytes-p.write_bytes)/dt),
                    )
        self._prev_disk = dio
        self._prev_ts = now

        snaps = []
        for part in psutil.disk_partitions():
            skip_fs = {"squashfs","overlay","tmpfs","devtmpfs","proc","sysfs","devpts","cgroup","cgroup2"}
            if part.fstype in skip_fs:
                continue
            try:
                u = psutil.disk_usage(part.mountpoint)
                io = io_map.get(part.device, dict(read_speed=0, write_speed=0))
                snaps.append(dict(
                    mount=part.mountpoint, device=part.device,
                    total_gb=u.total/(1024**3), used_gb=u.used/(1024**3),
                    free_gb=u.free/(1024**3), percent=u.percent,
                    fs=part.fstype, read_speed=io["read_speed"], write_speed=io["write_speed"],
                ))
            except PermissionError:
                continue
        return snaps

    def net(self):
        now = time.time()
        counters = psutil.net_io_counters(pernic=True) or {}
        ifaces = []
        for n, c in counters.items():
            if n in ("lo","docker","bridge","veth","nat","flannel","cni","tun","tap"):
                continue
            prev = self._prev_net.get(n)
            rs = ss = 0
            if prev and self._prev_ts:
                dt = now - self._prev_ts
                rs = max(0,(c.bytes_recv-prev.bytes_recv)/dt) if dt else 0
                ss = max(0,(c.bytes_sent-prev.bytes_sent)/dt) if dt else 0
            ifaces.append(dict(name=n, bytes_recv=c.bytes_recv, bytes_sent=c.bytes_sent,
                              packets_recv=c.packets_recv, packets_sent=c.packets_sent,
                              errin=c.errin, errout=c.errout,
                              recv_speed=rs, sent_speed=ss))
            self._prev_net[n] = c

        total_rs = sum(x["recv_speed"] for x in ifaces)
        total_ss = sum(x["sent_speed"] for x in ifaces)
        self._prev_ts = now
        return dict(interfaces=ifaces, total_recv_speed=total_rs, total_sent_speed=total_ss)

    def load(self):
        l = psutil.getloadavg()
        return dict(load1=l[0], load5=l[1], load15=l[2])

    def procs(self, sort_key="cpu", limit=15):
        procs = []
        for p in psutil.process_iter(["pid","name","username","status","cpu_percent",
                                        "memory_percent","memory_info","num_threads",
                                        "create_time","cmdline","nice"]):
            try:
                m = p.memory_info()
                ct = p.cpu_times()
                procs.append(dict(
                    pid=p.info["pid"], name=(p.info["name"] or "?")[:30],
                    user=p.info["username"] or "?",
                    status=p.info["status"] or "?",
                    cpu=p.info["cpu_percent"] or 0.0,
                    mem=p.info["memory_percent"] or 0.0,
                    rss_mb=m.rss/(1024**2), virt_mb=m.vms/(1024**2),
                    threads=p.info["num_threads"] or 1,
                    user_t=ct.user, system_t=ct.system,
                    start=p.info["create_time"],
                    cmd=" ".join(p.info["cmdline"] or []),
                    nice=p.info["nice"] or 0,
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        if sort_key == "cpu": procs.sort(key=lambda x: x["cpu"], reverse=True)
        elif sort_key == "mem": procs.sort(key=lambda x: x["mem"], reverse=True)
        else: procs.sort(key=lambda x: x["name"].lower())
        return procs[:limit]

    def snapshot(self):
        cpu = self.cpu()
        mem = self.mem()
        disks = self.disks()
        net = self.net()
        load = self.load()
        return dict(
            ts=time.time(), hostname=socket.gethostname(),
            uptime_h=(time.time()-psutil.boot_time())/3600,
            cpu=cpu, mem=mem, disks=disks, net=net, load=load,
            procs=self.procs(),
        )

# ── RENDERER ───────────────────────────────────────

def render(snap, cols=120):
    lines = []
    W = min(cols, 120)
    cpu = snap["cpu"]
    mem = snap["mem"]
    net = snap["net"]
    load = snap["load"]
    disks = snap["disks"]
    procs = snap["procs"]
    up = snap["uptime_h"]
    d = int(up//24); h = int(up%24)

    hdr = color(C.BLUE, " luosysmon ")
    hdr += f"  {snap['hostname']}  up {d}d {h:02d}h  "
    hdr += f"load: {load['load1']:.2f} {load['load5']:.2f} {load['load15']:.2f}"
    lines.append(hdr)

    # CPU
    lines.append("")
    ct = cpu["total"]
    lines.append(f" CPU % {c(ct, CPU_T)} |{bar(ct,20)}|  user={c(cpu['user'],CPU_T)}%  sys={c(cpu['system'],CPU_T)}%  idle={cpu['idle']:.1f}%  iow={cpu['iowait']:.1f}%")
    if cpu["per_core"]:
        cb = " ".join(bar(x,4) for x in cpu["per_core"])
        lines.append(f"       per-core: {cb}")
    if cpu["temperature"]:
        lines.append(f"       temp: {cpu['temperature']:.1f}°C")
    if cpu["freq_mhz"]:
        lines.append(f"       freq: {cpu['freq_mhz']:.0f} MHz")

    # MEM
    mp = mem["percent"]
    lines.append("")
    lines.append(f" MEM  {c(mp,MEM_T)}% |{bar(mp,20)}|  used={mem['used_gb']:.1f}GB  avail={mem['available_gb']:.1f}GB/{mem['total_gb']:.1f}GB  cached={mem['cached_gb']:.1f}GB")
    if mem["swap_total_gb"] > 0:
        sp = mem["swap_percent"]
        lines.append(f" SWAP {c(sp,MEM_T)}% |{bar(sp,20)}|  used={mem['swap_used_gb']:.1f}GB/{mem['swap_total_gb']:.1f}GB")

    # DISKS
    if disks:
        lines.append("")
        lines.append(f" DISK  {'node':<25}  {'used/total':>10}  {'R/s':>10}  {'W/s':>10}")
        for d in disks:
            dev = d["mount"] if d["mount"] else d["device"]
            if len(dev) > 25: dev = dev[:22]+"..."
            lines.append(f"       {dev:<25}  {d['used_gb']:.1f}/{d['total_gb']:.1f}GB  {fmt_s(d['read_speed']):>10}  {fmt_s(d['write_speed']):>10}")

    # NET
    if net["interfaces"]:
        lines.append("")
        lines.append(f" NET  ↓{fmt_s(net['total_recv_speed']):>10}  ↑{fmt_s(net['total_sent_speed']):>10}")
        for iface in net["interfaces"][:4]:
            lines.append(f"       {iface['name']:<10}  ↓{fmt_b(iface['bytes_recv']):>10}  ↑{fmt_b(iface['bytes_sent']):>10}")

    # TOP PROCS
    if procs:
        lines.append("")
        lines.append(f" TOP   {'PID':>6}  {'USER':<12}  {'%CPU':>5}  {'%MEM':>5}  {'RSS(MB)':>8}  {'NAME':<28}")
        for p in procs[:12]:
            lines.append(f"       {p['pid']:6d}  {p['user']:<12}  {c(p['cpu'],CPU_T):>5}  {c(p['mem'],MEM_T):>5}  {p['rss_mb']:8.0f}  {p['name']:<28}")

    return "\n".join(lines)

# ── MAIN ────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="luosysmon — Linux System Monitor by luokai")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("top", help="Run continuous monitor")
    p.add_argument("-i","--interval", type=float, default=2.0)
    p.set_defaults(func=lambda a: None)

    p = sub.add_parser("snap", help="Single snapshot")
    p.set_defaults(func=lambda a: None)

    for name in ["cpu","mem","disk","net","load","procs"]:
        p = sub.add_parser(name)
        p.set_defaults(func=lambda a: None)

    p = sub.add_parser("json")
    p.set_defaults(func=lambda a: None)

    p = sub.add_parser("history")
    p.set_defaults(func=lambda a: None)

    args = parser.parse_args()
    cols, _ = terminal_size()
    col = Collector()

    if args.cmd == "top" or args.cmd is None:
        iv = getattr(args, "interval", 2.0) or 2.0
        prev = 0
        try:
            while True:
                snap = col.snapshot()
                out = render(snap, cols)
                if prev:
                    sys.stdout.write("\x1b[%dA" % prev)
                sys.stdout.write(out + "\n")
                sys.stdout.flush()
                prev = len(out.split("\n"))
                time.sleep(iv)
        except KeyboardInterrupt:
            pass
        return

    if args.cmd == "snap":
        print(render(col.snapshot(), cols))
        return

    if args.cmd == "cpu":
        c = col.cpu()
        print(f"CPU Total: {c['total']:.1f}%")
        print(f"  User:   {c['user']:.1f}%")
        print(f"  System: {c['system']:.1f}%")
        print(f"  Idle:   {c['idle']:.1f}%")
        print(f"  IOwait: {c['iowait']:.1f}%")
        if c["per_core"]:
            for i, v in enumerate(c["per_core"]): print(f"  Core {i}: {v:.1f}%")
        if c["freq_mhz"]: print(f"  Freq: {c['freq_mhz']:.0f} MHz")
        if c["temperature"]: print(f"  Temp: {c['temperature']:.1f}°C")
        return

    if args.cmd == "mem":
        m = col.mem()
        print(f"Memory: {m['percent']:.1f}%")
        print(f"  Total:  {m['total_gb']:.2f} GB")
        print(f"  Used:   {m['used_gb']:.2f} GB")
        print(f"  Avail:  {m['available_gb']:.2f} GB")
        print(f"  Cached:  {m['cached_gb']:.2f} GB")
        if m["swap_total_gb"] > 0:
            print(f"Swap: {m['swap_percent']:.1f}%  {m['swap_used_gb']:.2f}/{m['swap_total_gb']:.2f} GB")
        return

    if args.cmd == "disk":
        for d in col.disks():
            print(f"{d['mount']} ({d['device']})")
            print(f"  Total:  {d['total_gb']:.2f} GB")
            print(f"  Used:   {d['used_gb']:.2f} GB ({d['percent']:.1f}%)")
            print(f"  Free:   {d['free_gb']:.2f} GB")
            print(f"  R/s: {fmt_s(d['read_speed'])}  W/s: {fmt_s(d['write_speed'])}")
        return

    if args.cmd == "net":
        n = col.net()
        print(f"Total: ↓{fmt_s(n['total_recv_speed'])}  ↑{fmt_s(n['total_sent_speed'])}")
        for i in n["interfaces"]:
            print(f"\n  {i['name']}:")
            print(f"    RX: {fmt_b(i['bytes_recv'])}  TX: {fmt_b(i['bytes_sent'])}")
            if i["errin"] or i["errout"]:
                print(f"    Errors: in={i['errin']} out={i['errout']}")
        return

    if args.cmd == "load":
        l = col.load()
        print(f"Load: {l['load1']:.2f} / {l['load5']:.2f} / {l['load15']:.2f}")
        return

    if args.cmd == "procs":
        for p in col.procs():
            print(f"{p['pid']:6d}  {p['user']:<12}  {p['cpu']:5.1f}  {p['mem']:5.1f}  {p['rss_mb']:8.0f}  {p['name']}")
        return

    if args.cmd == "json":
        snap = col.snapshot()
        print(json.dumps(snap, indent=2))
        return

if __name__ == "__main__":
    main()
