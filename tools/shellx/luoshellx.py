#!/usr/bin/env python3
"""
luoshellx — Async Shell Executor + Pipeline Builder
Built from shellous + sh + shlax + exec-helpers best patterns
"""

import os
import sys
import json
import time
import asyncio
import signal
import shlex
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal
from concurrent.futures import ThreadPoolExecutor
from functools import partial

try:
    import httpx
except ImportError:
    httpx = None

# ═══════════════════════════════════════════════════════════
# RESULT OBJECT
# ═══════════════════════════════════════════════════════════

class CmdResult:
    """Holds the result of a shell command execution."""

    def __init__(
        self,
        cmd: str,
        rc: int,
        out: str = '',
        err: str = '',
        ok: bool = False,
        duration_ms: float = 0.0,
        ts: str = None,
    ):
        self.cmd = cmd
        self.rc = rc
        self.out = out
        self.err = err
        self.ok = ok
        self.duration_ms = duration_ms
        self.ts = ts or datetime.now(timezone.utc).isoformat()

    def __repr__(self) -> str:
        status = '✅' if self.ok else f'❌ [{self.rc}]'
        return f'<CmdResult {status} {self.duration_ms:.0f}ms>'

    def json(self) -> dict:
        return {
            'cmd': self.cmd,
            'rc': self.rc,
            'out': self.out,
            'err': self.err,
            'ok': self.ok,
            'duration_ms': round(self.duration_ms, 2),
            'ts': self.ts,
        }

    def raise_on_error(self) -> 'CmdResult':
        if not self.ok:
            raise RuntimeError(f"Command failed with rc={self.rc}: {self.cmd}\n{self.err}")
        return self

    @property
    def stdout(self) -> str: return self.out
    @property
    def stderr(self) -> str: return self.err

    def try_json(self) -> dict | None:
        try: return json.loads(self.out)
        except: return None

# ═══════════════════════════════════════════════════════════
# STREAM PROCESS
# ═══════════════════════════════════════════════════════════

async def _stream_read(reader: asyncio.StreamReader, chunk_size: int = 65536) -> AsyncIterator[bytes]:
    while True:
        chunk = await reader.read(chunk_size)
        if not chunk:
            break
        yield chunk

# ═══════════════════════════════════════════════════════════
# ASYNC SUBPROCESS
# ═══════════════════════════════════════════════════════════

async def _run_async(
    cmd: str,
    *,
    timeout: float = 0,
    env: dict = None,
    cwd: str = None,
    shell: bool = True,
    capture: bool = True,
    stream: bool = False,
    prefix: str = '',
    ctx_env: dict = None,
) -> CmdResult:
    """Core async subprocess runner — works with shell or raw exec."""
    merged_env = {**os.environ, **(ctx_env or {}), **(env or {})}
    start = time.monotonic()

    if stream:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
            cwd=cwd,
        )
        out_chunks, err_chunks = [], []
        async for raw in _stream_read(proc.stdout):
            out_chunks.append(raw)
            if prefix:
                sys.stdout.write(prefix + raw.decode())
            else:
                sys.stdout.write(raw.decode())
        async for raw in _stream_read(proc.stderr):
            err_chunks.append(raw)
            if prefix:
                sys.stderr.write(prefix + raw.decode())
        rc = await proc.wait()
        duration = (time.monotonic() - start) * 1000
        return CmdResult(
            cmd=cmd, rc=rc,
            out=b''.join(out_chunks).decode(errors='replace'),
            err=b''.join(err_chunks).decode(errors='replace'),
            ok=rc == 0,
            duration_ms=duration,
        )

    if capture:
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
            cwd=cwd,
        )
        try:
            out_bytes, err_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout) if timeout else await proc.communicate()
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return CmdResult(cmd=cmd, rc=-1, ok=False, err='Timed out')
        rc = proc.returncode
        duration = (time.monotonic() - start) * 1000
        return CmdResult(
            cmd=cmd, rc=rc,
            out=out_bytes.decode(errors='replace'),
            err=err_bytes.decode(errors='replace'),
            ok=rc == 0,
            duration_ms=duration,
        )

    # no capture — live output
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.STDOUT,
        stderr=asyncio.subprocess.STDOUT,
        env=merged_env,
        cwd=cwd,
    )
    await proc.wait()
    duration = (time.monotonic() - start) * 1000
    return CmdResult(cmd=cmd, rc=proc.returncode, ok=proc.returncode == 0, duration_ms=duration)


def run_sync(cmd: str, timeout: int = 30, env: dict = None, cwd: str = None) -> CmdResult:
    """Synchronous subprocess runner."""
    start = time.monotonic()
    merged_env = {**os.environ, **(env or {})}
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        return CmdResult(cmd=cmd, rc=-1, ok=False, err='Timed out')
    except Exception as e:
        return CmdResult(cmd=cmd, rc=-1, ok=False, err=str(e))
    duration = (time.monotonic() - start) * 1000
    return CmdResult(
        cmd=cmd,
        rc=result.returncode,
        out=result.stdout,
        err=result.stderr,
        ok=result.returncode == 0,
        duration_ms=duration,
    )

# ═══════════════════════════════════════════════════════════
# SHELL CONTEXT MANAGER
# ═══════════════════════════════════════════════════════════

class ShellContext:
    """Mutable shell execution context — cwd, env vars, defaults."""

    def __init__(self, cwd: str = None, env: dict = None, timeout: float = 30.0, prefix: str = ''):
        self.cwd = cwd or os.getcwd()
        self.env = env or {}
        self.timeout = timeout
        self.prefix = prefix
        self._prev_cwd = None

    def __enter__(self):
        self._prev_cwd = os.getcwd()
        if self.cwd:
            os.chdir(self.cwd)
        return self

    def __exit__(self, *args):
        if self._prev_cwd:
            os.chdir(self._prev_cwd)

    def cd(self, path: str) -> 'ShellContext':
        os.chdir(path)
        self.cwd = path
        return self

    def with_env(self, **kwargs) -> 'ShellContext':
        self.env.update(kwargs)
        return self

    def with_timeout(self, t: float) -> 'ShellContext':
        self.timeout = t
        return self

# ═══════════════════════════════════════════════════════════
# LUOSHELLX — MAIN SHELL RUNNER
# ═══════════════════════════════════════════════════════════

class LuoShell:
    """
    Async shell executor with pipeline support, streaming, and context.

    Usage:
        sx = luoshellx()
        r = await sx('ls -la')
        print(r.out)

        async for r in sx.stream('tail -f /var/log/syslog'):
            print(r.out)

        # with context
        async with luoshellx(cwd='/tmp') as sx:
            r = await sx('pwd')
    """

    def __init__(
        self,
        cwd: str = None,
        env: dict = None,
        timeout: float = 30.0,
        prefix: str = '',
    ):
        self.cwd = cwd
        self.env = env or {}
        self.timeout = timeout
        self.prefix = prefix
        self._ctx_stack: list[ShellContext] = []

    # ── Core execution ────────────────────────────────

    async def __call__(
        self,
        cmd: str,
        *,
        timeout: float = None,
        env: dict = None,
        cwd: str = None,
        capture: bool = True,
        stream: bool = False,
    ) -> CmdResult:
        merged_env = {**self.env, **(env or {})}
        ctx_cwd = cwd or self.cwd or None
        t = timeout if timeout is not None else self.timeout

        return await _run_async(
            cmd,
            timeout=t,
            env=merged_env,
            cwd=ctx_cwd,
            capture=capture,
            stream=stream,
            prefix=self.prefix,
        )

    def run_sync(self, cmd: str, **kwargs) -> CmdResult:
        """Synchronous version of call()."""
        merged_env = {**self.env, **kwargs.pop('env', {})}
        return run_sync(cmd, env=merged_env, cwd=kwargs.pop('cwd', None) or self.cwd, **kwargs)

    async def batch(self, *cmds: str, concurrency: int = 10) -> list[CmdResult]:
        """Run multiple commands concurrently."""
        sem = asyncio.Semaphore(concurrency)
        async def _one(cmd):
            async with sem:
                return await self(cmd)
        return await asyncio.gather(*[_one(c) for c in cmds])

    # ── Pipeline support ──────────────────────────────

    def pipe(self, *cmds: str) -> 'LuoShell':
        """Chain commands with pipes."""
        combined = ' | '.join(cmds)
        return LuoShell(cwd=self.cwd, env=self.env, timeout=self.timeout, prefix=self.prefix)

    # ── Streaming ────────────────────────────────────

    async def stream(self, cmd: str, timeout: float = None) -> AsyncIterator[CmdResult]:
        """Yield results line-by-line as command runs."""
        async for line in _stream_lines(self, cmd, timeout):
            yield line

    # ── Context manager ───────────────────────────────

    async def __aenter__(self):
        if self.cwd:
            self._prev_cwd = os.getcwd()
            os.chdir(self.cwd)
        return self

    async def __aexit__(self, *args):
        if getattr(self, '_prev_cwd', None):
            os.chdir(self._prev_cwd)

    # ── Convenience shortcuts ──────────────────────────

    async def grep(self, pattern: str, *files: str) -> CmdResult:
        cmd = f"grep {shlex.quote(pattern)} " + ' '.join(shlex.quote(f) for f in files)
        return await self(cmd)

    async def find(self, path: str = '.', pattern: str = '*', type_flag: str = 'f') -> CmdResult:
        return await self(f"find {shlex.quote(path)} -{type_flag} {shlex.quote(pattern)}")

    async def cat(self, *files: str) -> CmdResult:
        cmd = ' '.join(shlex.quote(f) for f in files)
        return await self(f"cat {cmd}")

    async def httpget(self, url: str) -> CmdResult:
        return await self(f"curl -sL {shlex.quote(url)}")

    async def upload(self, file_path: str, dest_url: str) -> CmdResult:
        return await self(f"curl -sT {shlex.quote(file_path)} {shlex.quote(dest_url)}")

    async def ping(self, host: str, count: int = 4) -> CmdResult:
        return await self(f"ping -c {count} {shlex.quote(host)}")

    async def nslookup(self, host: str) -> CmdResult:
        return await self(f"nslookup {shlex.quote(host)}")

    async def which(self, cmd: str) -> CmdResult:
        return await self(f"which {shlex.quote(cmd)}")

    async def pgrep(self, pattern: str) -> CmdResult:
        return await self(f"pgrep -fa {shlex.quote(pattern)}")

    async def kill_by_name(self, name: str, signal_num: int = 15) -> CmdResult:
        return await self(f"kill -{signal_num} $(pidof {shlex.quote(name)})")


# ═══════════════════════════════════════════════════════════
# STREAMING HELPERS
# ═══════════════════════════════════════════════════════════

async def _stream_lines(sx: LuoShell, cmd: str, timeout: float = None) -> AsyncIterator[str]:
    """Stream output line by line from a running command."""
    merged_env = {**sx.env}
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=merged_env,
        cwd=sx.cwd,
    )
    async for raw in _stream_read(proc.stdout):
        for line in raw.decode().splitlines(keepends=True):
            yield line
    await proc.wait()


# ═══════════════════════════════════════════════════════════
# WATCH MODE
# ═══════════════════════════════════════════════════════════

async def watch(cmd: str, interval: float = 5.0, limit: int = 0) -> None:
    """Repeatedly run a command, printing output each interval."""
    count = 0
    while True:
        count += 1
        ts = datetime.now().strftime('%H:%M:%S')
        r = await _run_async(cmd, capture=True)
        status = '✅' if r.ok else f'❌ [{r.rc}]'
        print(f"\n── Run #{count} @ {ts} {status} ({r.duration_ms:.0f}ms) ──")
        print(r.out or r.err)
        if limit and count >= limit:
            break
        await asyncio.sleep(interval)


# ═══════════════════════════════════════════════════════════
# THREADED SYNC PROXY (for non-async code)
# ═══════════════════════════════════════════════════════════

_executor = ThreadPoolExecutor(max_workers=10)

def run_in_thread(cmd: str, env: dict = None, cwd: str = None, timeout: int = 30) -> CmdResult:
    """Run a command in thread pool (for sync wrappers / callbacks)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run_async(cmd, env=env, cwd=cwd, timeout=timeout))
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════

def cmd_run(args) -> None:
    sx = LuoShell(timeout=args.timeout, cwd=args.cd)
    r = asyncio.run(sx(args.cmd, capture=True))
    print(r.out or r.err, end='')
    if not r.ok and not args.quiet:
        sys.exit(r.rc)

def cmd_capture(args) -> None:
    sx = LuoShell(timeout=args.timeout)
    r = asyncio.run(sx(args.cmd))
    output = r.json()
    if args.json:
        print(json.dumps(output, indent=2), flush=True)
    else:
        print(f"Command:    {r.cmd}", flush=True)
        print(f"Exit code:  {r.rc}  {'✅' if r.ok else '❌'}", flush=True)
        print(f"Duration:   {r.duration_ms:.0f}ms", flush=True)
        print(f"\n--- stdout ({len(r.out)} bytes) ---", flush=True)
        print(r.out or '(empty)', flush=True)
        print(f"\n--- stderr ({len(r.err)} bytes) ---", flush=True)
        print(r.err or '(empty)', flush=True)

async def _do_retry(args) -> None:
    sx = LuoShell(timeout=args.timeout)
    last = None
    for attempt in range(1, args.attempts + 1):
        r = await sx(args.cmd)
        if r.ok:
            print(f"✅ Succeeded on attempt {attempt}")
            print(r.out)
            return
        last = r
        print(f"❌ Attempt {attempt}/{args.attempts} failed (rc={r.rc}) — retrying in {attempt * 2}s...")
        await asyncio.sleep(attempt * 2)
    print(f"\n❌ All {args.attempts} attempts failed.")
    print(last.err if last else '')
    sys.exit(last.rc if last else 1)

def cmd_watch(args) -> None:
    asyncio.run(watch(args.cmd, interval=args.interval, limit=args.limit or 0))

def cmd_batch(args) -> None:
    sx = LuoShell(timeout=args.timeout)
    results = asyncio.run(sx.batch(*args.cmds, concurrency=args.concurrency))
    for r in results:
        status = '✅' if r.ok else '❌'
        print(f"  {status}  [{r.rc}]  {r.duration_ms:.0f}ms  {r.cmd}")

def cmd_json(args) -> None:
    sx = LuoShell()
    r = asyncio.run(sx(args.cmd))
    data = r.try_json()
    if data:
        print(json.dumps(data, indent=2))
    else:
        print(json.dumps(r.json(), indent=2))

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def build_parser():
    import argparse
    p = argparse.ArgumentParser(prog='luoshellx', description='Async shell executor + pipeline builder')
    sub = p.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('run', help='Run a command and print output')
    r.add_argument('cmd')
    r.add_argument('-t', '--timeout', type=float, default=30.0)
    r.add_argument('-C', '--cd')
    r.add_argument('-q', '--quiet', action='store_true')

    c = sub.add_parser('capture', help='Run and return structured JSON result')
    c.add_argument('cmd')
    c.add_argument('-t', '--timeout', type=float, default=30.0)
    c.add_argument('-j', '--json', action='store_true')

    rt = sub.add_parser('retry', help='Retry command until it succeeds')
    rt.add_argument('cmd')
    rt.add_argument('attempts', type=int, nargs='?', default=3)
    rt.add_argument('-t', '--timeout', type=float, default=30.0)

    w = sub.add_parser('watch', help='Watch command, run every N seconds')
    w.add_argument('cmd')
    w.add_argument('interval', type=float, nargs='?', default=5.0)
    w.add_argument('-n', '--limit', type=int, default=0)

    b = sub.add_parser('batch', help='Run multiple commands concurrently')
    b.add_argument('cmds', nargs='+')
    b.add_argument('-t', '--timeout', type=float, default=30.0)
    b.add_argument('-C', '--concurrency', type=int, default=10)

    j = sub.add_parser('json', help='Run and parse output as JSON')
    j.add_argument('cmd')

    return p

if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == 'run': cmd_run(args)
    elif args.cmd == 'capture': cmd_capture(args)
    elif args.cmd == 'retry': asyncio.run(_do_retry(args))
    elif args.cmd == 'watch': cmd_watch(args)
    elif args.cmd == 'batch': cmd_batch(args)
    elif args.cmd == 'json': cmd_json(args)