#!/usr/bin/env python3
"""
luoproc — Advanced Process Explorer & Manager
by luokai | MIT License

Smarter than ps, lighter than htop. Filter, sort, kill, tree-view,
and watch processes — all from one unified CLI.
"""

import os
import sys
import re
import time
import signal
import argparse
import subprocess
from pathlib import Path
from typing import Optional

# ── ANSI colours ──────────────────────────────────────────────────────────────
R = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
YLW = "\033[93m"
GRN = "\033[92m"
CYN = "\033[96m"
BLU = "\033[94m"
MGN = "\033[95m"

def c(text, *codes): return "".join(codes) + str(text) + R

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_proc_file(pid: int, name: str) -> str:
    try:
        return Path(f"/proc/{pid}/{name}").read_text(errors="replace")
    except Exception:
        return ""

def parse_stat(pid: int) -> dict:
    raw = read_proc_file(pid, "stat")
    if not raw:
        return {}
    # stat fields after comm (name may contain spaces/parens)
    m = re.match(r"(\d+)\s+\((.+)\)\s+(\S+)\s+(.*)", raw)
    if not m:
        return {}
    fields = m.group(4).split()
    try:
        return {
            "pid": int(m.group(1)),
            "name": m.group(2),
            "state": m.group(3),
            "ppid": int(fields[0]),
            "utime": int(fields[11]),
            "stime": int(fields[12]),
            "vsize": int(fields[20]),      # bytes
            "rss": int(fields[21]),        # pages
        }
    except (IndexError, ValueError):
        return {}

def page_size() -> int:
    try:
        return os.sysconf("SC_PAGE_SIZE")
    except Exception:
        return 4096

def clk_tck() -> int:
    try:
        return os.sysconf("SC_CLK_TCK")
    except Exception:
        return 100

def uptime_secs() -> float:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        return 1.0

def cpu_total() -> int:
    try:
        line = Path("/proc/stat").read_text().splitlines()[0]
        return sum(int(x) for x in line.split()[1:])
    except Exception:
        return 1

def parse_status(pid: int) -> dict:
    out = {}
    for line in read_proc_file(pid, "status").splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out

def get_username(uid: str) -> str:
    try:
        import pwd
        return pwd.getpwuid(int(uid)).pw_name
    except Exception:
        return uid

def get_cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.replace(b"\x00", b" ").decode(errors="replace").strip() or f"[{parse_stat(pid).get('name', '?')}]"
    except Exception:
        return "?"

def all_pids() -> list[int]:
    return sorted(
        int(p.name) for p in Path("/proc").iterdir()
        if p.name.isdigit()
    )

def build_process_list(filter_name: str = "", filter_user: str = "", sort_by: str = "cpu") -> list[dict]:
    PAGE = page_size()
    CLK = clk_tck()
    UP = uptime_secs()
    procs = []

    for pid in all_pids():
        stat = parse_stat(pid)
        if not stat:
            continue
        status = parse_status(pid)
        uid = status.get("Uid", "0 0 0 0").split()[0]
        user = get_username(uid)

        if filter_user and filter_user.lower() not in user.lower():
            continue
        if filter_name and filter_name.lower() not in stat["name"].lower():
            continue

        # CPU %
        total_time = stat["utime"] + stat["stime"]
        try:
            start_raw = int(parse_stat(pid).get("_raw_start", 0))
        except Exception:
            start_raw = 0
        # simplified: use total_time / uptime * clk
        cpu_pct = (total_time / CLK) / max(UP, 0.001) * 100

        # Memory MB
        mem_mb = (stat["rss"] * PAGE) / (1024 * 1024)
        virt_mb = stat["vsize"] / (1024 * 1024)

        procs.append({
            "pid": pid,
            "ppid": stat["ppid"],
            "name": stat["name"],
            "state": stat["state"],
            "user": user,
            "cpu": round(cpu_pct, 1),
            "mem_mb": round(mem_mb, 1),
            "virt_mb": round(virt_mb, 1),
            "threads": status.get("Threads", "1"),
        })

    key_map = {"cpu": "cpu", "mem": "mem_mb", "pid": "pid", "name": "name"}
    procs.sort(key=lambda x: x.get(key_map.get(sort_by, "cpu"), 0), reverse=(sort_by != "name"))
    return procs

def state_colour(s: str) -> str:
    return {
        "R": c(s, GRN, BOLD),
        "S": c(s, GRN),
        "D": c(s, YLW, BOLD),
        "Z": c(s, RED, BOLD),
        "T": c(s, YLW),
    }.get(s, c(s, DIM))

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    procs = build_process_list(
        filter_name=args.name or "",
        filter_user=args.user or "",
        sort_by=args.sort
    )
    limit = args.n or len(procs)
    procs = procs[:limit]

    hdr = f"{'PID':>7}  {'USER':<12}  {'ST':2}  {'CPU%':>6}  {'MEM(MB)':>8}  {'VIRT(MB)':>9}  {'THR':>4}  COMMAND"
    print(c(hdr, BOLD, CYN))
    print(c("─" * 80, DIM))

    for p in procs:
        cpu_col = c(f"{p['cpu']:>6.1f}", RED if p["cpu"] > 50 else YLW if p["cpu"] > 10 else GRN)
        mem_col = c(f"{p['mem_mb']:>8.1f}", RED if p["mem_mb"] > 500 else YLW if p["mem_mb"] > 100 else GRN)
        st = state_colour(p["state"])
        print(f"{p['pid']:>7}  {p['user']:<12}  {st}   {cpu_col}  {mem_col}  {p['virt_mb']:>9.1f}  {p['threads']:>4}  {c(p['name'], BOLD)}")

    print(c(f"\n  {len(procs)} processes shown", DIM))

def cmd_tree(args):
    procs = build_process_list(filter_name=args.name or "")
    by_pid = {p["pid"]: p for p in procs}
    children: dict[int, list] = {}
    for p in procs:
        children.setdefault(p["ppid"], []).append(p["pid"])

    shown = set()
    def draw(pid, prefix="", last=True):
        if pid in shown:
            return
        shown.add(pid)
        p = by_pid.get(pid)
        if not p:
            return
        conn = "└── " if last else "├── "
        ext  = "    " if last else "│   "
        print(f"{prefix}{c(conn, DIM)}{c(p['pid'], MGN)} {c(p['name'], BOLD)}  {c(p['user'], DIM)}  cpu={c(p['cpu'], YLW)}%  mem={c(p['mem_mb'], CYN)}MB")
        kids = sorted(children.get(pid, []))
        for i, kid in enumerate(kids):
            draw(kid, prefix + ext, i == len(kids) - 1)

    roots = [p["pid"] for p in procs if p["ppid"] not in by_pid or p["ppid"] == p["pid"]]
    for i, r in enumerate(roots):
        draw(r, "", i == len(roots) - 1)

def cmd_watch(args):
    interval = args.interval or 2
    try:
        while True:
            os.system("clear")
            print(c(f"  luoproc watch  —  refresh every {interval}s  —  {time.strftime('%H:%M:%S')}  —  Ctrl+C to quit", BOLD, CYN))
            print()
            args.n = args.n or 20
            cmd_list(args)
            time.sleep(interval)
    except KeyboardInterrupt:
        print(c("\n  Stopped.", DIM))

def cmd_kill(args):
    sig = getattr(signal, f"SIG{args.signal.upper()}", signal.SIGTERM)
    for pid in args.pids:
        try:
            os.kill(pid, sig)
            print(c(f"  ✓ Sent {args.signal.upper()} to PID {pid}", GRN))
        except ProcessLookupError:
            print(c(f"  ✗ PID {pid} not found", RED))
        except PermissionError:
            print(c(f"  ✗ Permission denied for PID {pid}", RED))

def cmd_info(args):
    pid = args.pid
    stat = parse_stat(pid)
    status = parse_status(pid)
    if not stat:
        print(c(f"  PID {pid} not found", RED)); return

    cmd = get_cmdline(pid)
    uid = status.get("Uid", "0").split()[0]
    user = get_username(uid)
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
    except Exception:
        cwd = "?"
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
    except Exception:
        exe = "?"

    PAGE = page_size()
    mem_mb = (stat["rss"] * PAGE) / (1024 * 1024)

    print(c(f"\n  Process Info — PID {pid}", BOLD, CYN))
    print(c("  ─────────────────────────────────────────", DIM))
    rows = [
        ("Name",     stat["name"]),
        ("State",    f"{state_colour(stat['state'])} ({stat['state']})"),
        ("User",     user),
        ("PPID",     stat["ppid"]),
        ("Threads",  status.get("Threads", "?")),
        ("Memory",   f"{mem_mb:.1f} MB RSS"),
        ("Virt",     f"{stat['vsize']/1024/1024:.1f} MB"),
        ("Exe",      exe),
        ("CWD",      cwd),
        ("Cmdline",  cmd[:120]),
    ]
    for k, v in rows:
        print(f"  {c(k+':',BOLD):<20} {v}")

    # open file descriptors
    try:
        fds = list(Path(f"/proc/{pid}/fd").iterdir())
        print(f"  {c('Open FDs:',BOLD):<20} {len(fds)}")
    except Exception:
        pass

    # environment snippet
    if args.env:
        env = read_proc_file(pid, "environ").replace("\x00", "\n")
        print(c("\n  Environment:", BOLD))
        for line in env.splitlines()[:20]:
            if "=" in line:
                k2, v2 = line.split("=", 1)
                print(f"    {c(k2, YLW)}={v2[:80]}")

def cmd_find(args):
    procs = build_process_list(filter_name=args.pattern)
    if not procs:
        print(c(f"  No processes matching '{args.pattern}'", YLW))
        return
    for p in procs:
        cmd = get_cmdline(p["pid"])[:80]
        print(f"  {c(p['pid'], MGN, BOLD)}  {c(p['name'], BOLD)}  {c(p['user'],DIM)}  {c(cmd,DIM)}")

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="luoproc",
        description=c("luoproc", BOLD, CYN) + " — Advanced Process Explorer & Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luoproc list                        List all processes sorted by CPU
  luoproc list --sort mem -n 20       Top 20 by memory
  luoproc list --name python          Filter by name
  luoproc list --user www-data        Filter by user
  luoproc tree                        Process tree view
  luoproc tree --name bash            Tree filtered by name
  luoproc watch --sort mem -n 15      Live dashboard (refresh 2s)
  luoproc watch -i 5                  Live dashboard every 5s
  luoproc info 1234                   Detailed info for PID
  luoproc info 1234 --env             Include environment variables
  luoproc kill 1234 1235              Kill PIDs (SIGTERM)
  luoproc kill 1234 --signal SIGKILL  Force kill
  luoproc find nginx                  Find processes by pattern
""",
    )
    sub = parser.add_subparsers(dest="cmd")

    # list
    p_list = sub.add_parser("list", help="List processes")
    p_list.add_argument("--sort", default="cpu", choices=["cpu","mem","pid","name"])
    p_list.add_argument("--name", help="Filter by name")
    p_list.add_argument("--user", help="Filter by username")
    p_list.add_argument("-n", type=int, help="Limit rows")

    # tree
    p_tree = sub.add_parser("tree", help="Process tree")
    p_tree.add_argument("--name", help="Filter by name")

    # watch
    p_watch = sub.add_parser("watch", help="Live process monitor")
    p_watch.add_argument("--sort", default="cpu", choices=["cpu","mem","pid","name"])
    p_watch.add_argument("--name", help="Filter by name")
    p_watch.add_argument("--user", help="Filter by user")
    p_watch.add_argument("-n", type=int, help="Limit rows")
    p_watch.add_argument("-i", "--interval", type=float, help="Refresh interval (s)")

    # kill
    p_kill = sub.add_parser("kill", help="Kill processes")
    p_kill.add_argument("pids", nargs="+", type=int, metavar="PID")
    p_kill.add_argument("--signal", default="TERM", metavar="SIG")

    # info
    p_info = sub.add_parser("info", help="Detailed process info")
    p_info.add_argument("pid", type=int)
    p_info.add_argument("--env", action="store_true", help="Show environment")

    # find
    p_find = sub.add_parser("find", help="Find process by name pattern")
    p_find.add_argument("pattern")

    args = parser.parse_args()
    dispatch = {"list": cmd_list, "tree": cmd_tree, "watch": cmd_watch,
                "kill": cmd_kill, "info": cmd_info, "find": cmd_find}

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
