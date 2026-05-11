#!/usr/bin/env python3
"""
luocron — Cron Job Manager
by luokai | MIT License

Human-readable cron scheduling, add/remove/list/test jobs,
next-run preview, and real execution log. Beats raw crontab.
"""

import os
import sys
import re
import subprocess
import argparse
import datetime
import tempfile
from typing import Optional

# ── ANSI ──────────────────────────────────────────────────────────────────────
R    = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"
RED  = "\033[91m"
GRN  = "\033[92m"
YLW  = "\033[93m"
CYN  = "\033[96m"
MGN  = "\033[95m"

def c(*args):
    return "".join(args[1:]) + str(args[0]) + R

# ── Human-readable schedule parser ────────────────────────────────────────────

PRESETS = {
    "minutely":    "* * * * *",
    "hourly":      "0 * * * *",
    "daily":       "0 0 * * *",
    "midnight":    "0 0 * * *",
    "weekly":      "0 0 * * 0",
    "monthly":     "0 0 1 * *",
    "yearly":      "0 0 1 1 *",
    "annually":    "0 0 1 1 *",
    "workdays":    "0 9 * * 1-5",
    "weekdays":    "0 9 * * 1-5",
    "weekends":    "0 10 * * 0,6",
    "every5min":   "*/5 * * * *",
    "every10min":  "*/10 * * * *",
    "every15min":  "*/15 * * * *",
    "every30min":  "*/30 * * * *",
    "every2h":     "0 */2 * * *",
    "every6h":     "0 */6 * * *",
    "every12h":    "0 */12 * * *",
}

WEEKDAYS = {"mon":1,"tue":2,"wed":3,"thu":4,"fri":5,"sat":6,"sun":0,
            "monday":1,"tuesday":2,"wednesday":3,"thursday":4,"friday":5,"saturday":6,"sunday":0}

def parse_schedule(s: str) -> str:
    """Convert human-readable schedule to cron expression."""
    s = s.strip().lower()

    # preset
    if s in PRESETS:
        return PRESETS[s]

    # already a cron expression (5 fields)
    parts = s.split()
    if len(parts) == 5 and all(re.match(r"[\d*/,\-]+", p) for p in parts):
        return s

    # "every N minutes/hours/days/weeks"
    m = re.match(r"every\s+(\d+)\s*(minute|min|hour|day|week)s?", s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ("minute","min"):
            return f"*/{n} * * * *"
        if unit == "hour":
            return f"0 */{n} * * *"
        if unit == "day":
            return f"0 0 */{n} * *"
        if unit == "week":
            return f"0 0 * * */{n}"

    # "at HH:MM daily"
    m = re.match(r"at\s+(\d{1,2}):(\d{2})(?:\s+(daily|weekly|monthly|workdays|weekends|weekdays))?", s)
    if m:
        hour, minute = m.group(1), m.group(2)
        qualifier = m.group(3) or "daily"
        dow = "*"
        dom = "*"
        if qualifier in ("weekly",):
            dow = "1"
        elif qualifier in ("monthly",):
            dom = "1"
        elif qualifier in ("workdays","weekdays"):
            dow = "1-5"
        elif qualifier == "weekends":
            dow = "0,6"
        return f"{minute} {hour} {dom} * {dow}"

    # "on monday at 09:00"
    m = re.match(r"on\s+(\w+)\s+at\s+(\d{1,2}):(\d{2})", s)
    if m:
        day_name, hour, minute = m.group(1), m.group(2), m.group(3)
        dow = WEEKDAYS.get(day_name)
        if dow is not None:
            return f"{minute} {hour} * * {dow}"

    raise ValueError(f"Cannot parse schedule: '{s}'. Use a preset, cron expression, or natural language.")

def describe_cron(expr: str) -> str:
    """Return a human description of a cron expression."""
    parts = expr.split()
    if len(parts) != 5:
        return expr
    minute, hour, dom, month, dow = parts

    if expr == "* * * * *":
        return "every minute"
    if minute.startswith("*/") and hour == "*":
        return f"every {minute[2:]} minutes"
    if minute == "0" and hour.startswith("*/"):
        return f"every {hour[2:]} hours"
    if minute == "0" and dom.startswith("*/") and hour == "0":
        return f"every {dom[2:]} days at midnight"
    if minute == "0" and hour == "0" and dom == "1" and month == "*":
        return "monthly at midnight on the 1st"
    if minute == "0" and hour == "0" and dow == "0":
        return "every Sunday at midnight"
    if minute == "0" and hour == "0" and dom == "1" and month == "1":
        return "annually on Jan 1st at midnight"
    if dow == "1-5":
        return f"weekdays at {hour.zfill(2)}:{minute.zfill(2)}"
    if dow == "0,6":
        return f"weekends at {hour.zfill(2)}:{minute.zfill(2)}"
    if dow == "*" and dom == "*":
        return f"daily at {hour.zfill(2)}:{minute.zfill(2)}"
    return expr

def next_runs(expr: str, n: int = 5) -> list[datetime.datetime]:
    """Calculate next N run times for a cron expression (simplified)."""
    parts = expr.split()
    if len(parts) != 5:
        return []
    minutes_str, hours_str, dom_str, month_str, dow_str = parts

    def expand(field, lo, hi):
        if field == "*":
            return list(range(lo, hi + 1))
        result = []
        for part in field.split(","):
            if "/" in part:
                base, step = part.split("/")
                base_range = range(lo, hi + 1) if base == "*" else range(int(base), hi + 1)
                result.extend(x for x in base_range if (x - lo) % int(step) == 0)
            elif "-" in part:
                a, b = part.split("-")
                result.extend(range(int(a), int(b) + 1))
            else:
                result.append(int(part))
        return sorted(set(result))

    valid_min   = expand(minutes_str, 0, 59)
    valid_hour  = expand(hours_str, 0, 23)
    valid_dom   = expand(dom_str, 1, 31)
    valid_month = expand(month_str, 1, 12)
    valid_dow   = expand(dow_str, 0, 6) if dow_str != "*" else None

    now = datetime.datetime.now().replace(second=0, microsecond=0) + datetime.timedelta(minutes=1)
    runs = []
    candidate = now

    for _ in range(50000):
        if candidate.month not in valid_month:
            candidate = (candidate.replace(day=1) + datetime.timedelta(days=32)).replace(day=1, hour=0, minute=0)
            continue
        if valid_dow is not None and candidate.weekday() not in [d % 7 for d in valid_dow]:
            candidate += datetime.timedelta(days=1)
            candidate = candidate.replace(hour=0, minute=0)
            continue
        if candidate.day not in valid_dom and dow_str == "*":
            candidate += datetime.timedelta(days=1)
            candidate = candidate.replace(hour=0, minute=0)
            continue
        if candidate.hour not in valid_hour:
            if candidate.hour > max(valid_hour):
                candidate += datetime.timedelta(days=1)
                candidate = candidate.replace(hour=min(valid_hour), minute=min(valid_min))
            else:
                nxt_h = next((h for h in valid_hour if h > candidate.hour), None)
                if nxt_h is None:
                    candidate += datetime.timedelta(days=1)
                    candidate = candidate.replace(hour=min(valid_hour), minute=min(valid_min))
                else:
                    candidate = candidate.replace(hour=nxt_h, minute=min(valid_min))
            continue
        if candidate.minute not in valid_min:
            nxt_m = next((m for m in valid_min if m > candidate.minute), None)
            if nxt_m is None:
                nxt_h = next((h for h in valid_hour if h > candidate.hour), None)
                if nxt_h is None:
                    candidate += datetime.timedelta(days=1)
                    candidate = candidate.replace(hour=min(valid_hour), minute=min(valid_min))
                else:
                    candidate = candidate.replace(hour=nxt_h, minute=min(valid_min))
            else:
                candidate = candidate.replace(minute=nxt_m)
            continue

        runs.append(candidate)
        if len(runs) == n:
            break
        candidate += datetime.timedelta(minutes=1)

    return runs

# ── Crontab I/O ───────────────────────────────────────────────────────────────

COMMENT_TAG = "# luocron:"

def read_crontab() -> list[str]:
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()

def write_crontab(lines: list[str]):
    content = "\n".join(lines) + "\n"
    with tempfile.NamedTemporaryFile("w", suffix=".cron", delete=False) as f:
        f.write(content)
        tmp = f.name
    subprocess.run(["crontab", tmp], check=True)
    os.unlink(tmp)

def parse_jobs(lines: list[str]) -> list[dict]:
    jobs = []
    comment = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(COMMENT_TAG):
            comment = stripped[len(COMMENT_TAG):].strip()
        elif stripped and not stripped.startswith("#"):
            parts = stripped.split(None, 5)
            if len(parts) >= 6:
                expr = " ".join(parts[:5])
                cmd  = parts[5]
                jobs.append({"expr": expr, "cmd": cmd, "label": comment})
                comment = ""
        else:
            comment = ""
    return jobs

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    lines = read_crontab()
    if not lines:
        print(c("  No crontab. Run 'luocron add' to create jobs.", YLW)); return

    jobs = parse_jobs(lines)
    if not jobs:
        print(c("  Crontab exists but no jobs found.", YLW)); return

    print(c(f"\n  {len(jobs)} cron job(s)", BOLD, CYN))
    print(c("  " + "─" * 70, DIM))

    for i, job in enumerate(jobs, 1):
        label = f"  [{c(job['label'], MGN)}]" if job["label"] else ""
        desc  = describe_cron(job["expr"])
        runs  = next_runs(job["expr"], 1)
        nxt   = runs[0].strftime("  next: %a %b %d %H:%M") if runs else ""
        print(f"  {c(i, DIM):>4}  {c(job['expr'], YLW):<22}  {c(desc, GRN):<30}  {c(nxt, DIM)}")
        print(f"       {c(job['cmd'], BOLD)}{label}")
        print()

def cmd_add(args):
    try:
        expr = parse_schedule(" ".join(args.schedule))
    except ValueError as e:
        print(c(f"  ✗ {e}", RED)); sys.exit(1)

    desc = describe_cron(expr)
    print(c(f"  Schedule: {expr}  ({desc})", GRN))

    if args.preview:
        runs = next_runs(expr, 5)
        print(c("  Next runs:", BOLD))
        for r in runs:
            print(f"    {r.strftime('%a %b %d %H:%M')}")
        if not args.yes:
            ans = input(c("  Add this job? [y/N] ", YLW))
            if ans.lower() != "y":
                print(c("  Aborted.", DIM)); return

    lines = read_crontab()
    if args.label:
        lines.append(f"{COMMENT_TAG} {args.label}")
    lines.append(f"{expr} {args.command}")
    write_crontab(lines)
    print(c(f"  ✓ Job added: {expr} {args.command}", GRN, BOLD))

def cmd_remove(args):
    lines = read_crontab()
    jobs = parse_jobs(lines)

    if args.index:
        idx = args.index - 1
        if idx < 0 or idx >= len(jobs):
            print(c(f"  ✗ Job #{args.index} not found.", RED)); return
        job = jobs[idx]
    elif args.pattern:
        matches = [j for j in jobs if args.pattern.lower() in j["cmd"].lower()]
        if not matches:
            print(c(f"  ✗ No jobs matching '{args.pattern}'.", RED)); return
        job = matches[0]
    else:
        print(c("  ✗ Specify --index or --pattern.", RED)); return

    print(f"  Removing: {c(job['expr'], YLW)} {c(job['cmd'], BOLD)}")
    if not args.yes:
        ans = input(c("  Confirm? [y/N] ", YLW))
        if ans.lower() != "y":
            print(c("  Aborted.", DIM)); return

    new_lines = []
    skip_comment = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(COMMENT_TAG) and job.get("label") and job["label"] in stripped:
            skip_comment = True
            continue
        if skip_comment or (job["cmd"] in stripped and job["expr"].split()[0] in stripped):
            skip_comment = False
            continue
        new_lines.append(line)

    write_crontab(new_lines)
    print(c("  ✓ Job removed.", GRN))

def cmd_next(args):
    try:
        expr = parse_schedule(" ".join(args.schedule))
    except ValueError as e:
        print(c(f"  ✗ {e}", RED)); sys.exit(1)

    desc = describe_cron(expr)
    print(c(f"\n  Schedule: {expr}  ({desc})", BOLD, CYN))
    print(c("  " + "─" * 40, DIM))

    now = datetime.datetime.now()
    runs = next_runs(expr, args.n or 10)
    for r in runs:
        delta = r - now
        mins = int(delta.total_seconds() / 60)
        if mins < 60:
            eta = f"in {mins}m"
        elif mins < 1440:
            eta = f"in {mins//60}h {mins%60}m"
        else:
            eta = f"in {delta.days}d"
        print(f"  {c(r.strftime('%a %b %d %Y  %H:%M'), BOLD)}  {c(eta, GRN)}")

def cmd_run(args):
    """Run a command now and show output (for testing)."""
    print(c(f"  Running: {args.command}", BOLD, CYN))
    print(c("  " + "─" * 50, DIM))
    start = __import__("time").time()
    result = subprocess.run(args.command, shell=True, capture_output=False)
    elapsed = __import__("time").time() - start
    colour = GRN if result.returncode == 0 else RED
    print(c(f"\n  Exit code: {result.returncode}  ({elapsed:.2f}s)", colour, BOLD))

def cmd_presets(args):
    print(c("\n  luocron presets — human-readable schedule keywords", BOLD, CYN))
    print(c("  " + "─" * 55, DIM))
    for name, expr in sorted(PRESETS.items()):
        desc = describe_cron(expr)
        print(f"  {c(name, YLW, BOLD):<20}  {c(expr, DIM):<20}  {desc}")

# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="luocron",
        description=c("luocron", BOLD, CYN) + " — Cron Job Manager with Human-Readable Scheduling",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luocron list                                  Show all cron jobs
  luocron add daily /scripts/backup.sh          Add a daily job
  luocron add "every 15 minutes" /scripts/sync.sh
  luocron add "at 09:00 weekdays" /scripts/report.sh --label "morning report"
  luocron add "0 2 * * *" /scripts/db_backup.sh --preview
  luocron remove --index 2                      Remove job #2
  luocron remove --pattern backup               Remove job matching 'backup'
  luocron next daily                            Preview next runs for 'daily'
  luocron next "every 15 minutes" -n 5          Preview 5 next runs
  luocron run "/scripts/test.sh"                Run a command now
  luocron presets                               List all schedule keywords
""",
    )
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="List all cron jobs")

    p = sub.add_parser("add", help="Add a cron job")
    p.add_argument("schedule", nargs="+", help="Schedule: preset, cron expr, or natural language")
    p.add_argument("command", help="Command to run")
    p.add_argument("--label", help="Human label for this job")
    p.add_argument("--preview", action="store_true", default=True, help="Show next runs before adding")
    p.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")

    p = sub.add_parser("remove", aliases=["rm"], help="Remove a job")
    p.add_argument("--index", type=int, help="Job number from 'list'")
    p.add_argument("--pattern", help="Match command substring")
    p.add_argument("-y", "--yes", action="store_true")

    p = sub.add_parser("next", help="Preview next run times for a schedule")
    p.add_argument("schedule", nargs="+")
    p.add_argument("-n", type=int, default=10, help="Number of runs to show")

    p = sub.add_parser("run", help="Run a command now (for testing)")
    p.add_argument("command")

    p = sub.add_parser("presets", help="List all schedule presets")

    args = ap.parse_args()
    dispatch = {
        "list": cmd_list, "add": cmd_add, "remove": cmd_remove, "rm": cmd_remove,
        "next": cmd_next, "run": cmd_run, "presets": cmd_presets,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
