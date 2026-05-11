#!/usr/bin/env python3
"""
shellx — Shell command runner with output capture & formatting
Run commands, capture output, pipe data, retry on failure

Usage:
  python3 shellx.py run <cmd>                -- run and print output
  python3 shellx.py capture <cmd>            -- run and return JSON with stdout/stderr/exit
  python3 shellx.py retry <cmd> <n>         -- retry n times until success
  python3 shellx.py pipe <file> <cmd>        -- pipe file content to command
  python3 shellx.py watch <cmd> <interval>   -- run command repeatedly
"""

import sys
import subprocess
import json
import time
import shlex


def run_cmd(cmd: str) -> tuple[int, str, str]:
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return result.returncode, result.stdout, result.stderr


def capture(cmd: str) -> dict:
    code, stdout, stderr = run_cmd(cmd)
    return {'command': cmd, 'exit_code': code, 'stdout': stdout, 'stderr': stderr, 'ok': code == 0}


def retry(cmd: str, attempts: int = 3) -> dict:
    for i in range(attempts):
        code, stdout, stderr = run_cmd(cmd)
        if code == 0:
            return {'ok': True, 'attempt': i+1, 'stdout': stdout}
        time.sleep(1)
    return {'ok': False, 'attempts': attempts, 'stderr': stderr}


def pipe_content(filepath: str, cmd: str) -> str:
    with open(filepath) as f:
        result = subprocess.run(cmd, shell=True, input=f.read(), capture_output=True, text=True, timeout=30)
    return result.stdout or result.stderr


def watch(cmd: str, interval: int = 5) -> None:
    print(f"Watching every {interval}s — Ctrl+C to stop\n")
    count = 0
    while True:
        count += 1
        code, stdout, stderr = run_cmd(cmd)
        print(f"\n── Run #{count} @ {time.strftime('%H:%M:%S')} ──")
        print(stdout or stderr)
        time.sleep(interval)


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(0)

    cmd_type = sys.argv[1]

    if cmd_type == 'run':
        _, stdout, stderr = run_cmd(sys.argv[2])
        print(stdout or stderr)
    elif cmd_type == 'capture':
        print(json.dumps(capture(sys.argv[2]), indent=2))
    elif cmd_type == 'retry' and len(sys.argv) >= 4:
        result = retry(sys.argv[2], int(sys.argv[3]))
        print(json.dumps(result, indent=2))
    elif cmd_type == 'pipe' and len(sys.argv) >= 4:
        print(pipe_content(sys.argv[2], sys.argv[3]))
    elif cmd_type == 'watch' and len(sys.argv) >= 4:
        watch(sys.argv[2], int(sys.argv[3]))
    else:
        print(__doc__)