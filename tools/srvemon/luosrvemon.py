#!/usr/bin/env python3
"""
luosrvemon — Service Uptime & Health Monitor
Complete monitor with alerting, history, badges, SSL checks, cron scheduling
Built from uptime-kuma + healthchecks concepts

MIT License — luokai
"""

import asyncio
import csv
import hashlib
import hmac
import json
import os
import random
import re
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
import urllib.error
import zlib
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Literal, Optional

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    SSL_SUPPORT = True
except ImportError:
    SSL_SUPPORT = False

try:
    import rich
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import Progress, SpinnerColumn, BarColumn, TimeElapsedColumn, MofNCompleteColumn
    RICH = True
    console = Console()
except ImportError:
    RICH = False
    console = Console(stderr=True)

# ─────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────

class Status(str):
    UP = "up"
    DOWN = "down"
    PAUSED = "paused"
    UNKNOWN = "unknown"
    STARTING = "starting"

class CheckKind(str):
    HTTP = "http"
    TCP = "tcp"
    ICMP = "icmp"
    SSL = "ssl"
    SSH = "ssh"
    DNS = "dns"
    HEARTBEAT = "heartbeat"

@dataclass
class PingRecord:
    id: int
    created: float
    status: str
    duration_ms: float | None = None
    remote_addr: str = ""
    exitstatus: int | None = None
    manual: bool = False
    body_preview: str = ""
    tags: list[str] = field(default_factory=list)

@dataclass
class Downtime:
    start: float
    end: float | None = None
    duration_s: float | None = None

@dataclass
class Alert:
    ts: float
    channel: str
    message: str
    sent: bool = False

@dataclass
class MonitorCheck:
    id: str
    name: str
    url: str
    kind: str
    port: int = 80
    path: str = "/"
    timeout: float = 10.0
    interval: int = 60
    grace: int = 60
    retry: int = 3
    max_retries: int = 3
    method: str = "GET"
    expected_code: int = 200
    expected_keyword: str = ""
    failure_keyword: str = ""
    start_kw: str = ""
    success_kw: str = ""
    filter_body: bool = False
    filter_subject: bool = False
    filter_default_fail: bool = False
    tags: list[str] = field(default_factory=list)
    status: str = Status.UNKNOWN
    last_ping: float = 0
    last_start: float = 0
    last_duration_ms: float = 0
    last_status_code: int = 0
    last_error: str = ""
    last_response_body: str = ""
    last_ping_id: int = 0
    ping_history: list = field(default_factory=list)
    downtimes: list = field(default_factory=list)
    current_downtime: Downtime | None = None
    alerts: list = field(default_factory=list)
    next_check: float = 0
    consecutive_failures: int = 0
    ssl_expiry_days: int = 30
    dns_resolve_type: str = "A"
    is_paused: bool = False
    webhook_url: str = ""
    slack_webhook: str = ""
    discord_webhook: str = ""
    email_to: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    schedule: str = ""  # cron expression
    timezone: str = "UTC"
    manual_resume: bool = False
    unique: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop('ping_history', None)
        d.pop('downtimes', None)
        d.pop('alerts', None)
        return d

# ─────────────────────────────────────────────────────────
# CORE CHECK ENGINE
# ─────────────────────────────────────────────────────────

class CheckEngine:
    """Run health checks for all monitor types"""

    def __init__(self):
        self.ping_id_counter = 0

    def _next_ping_id(self) -> int:
        self.ping_id_counter += 1
        return self.ping_id_counter

    async def check(self, check: MonitorCheck) -> PingRecord:
        self.ping_id_counter += 1
        ping = PingRecord(
            id=self.ping_id_counter,
            created=time.time(),
            status="starting",
        )
        check.last_start = time.time()
        check.last_ping_id = ping.id

        try:
            if check.kind in (CheckKind.HTTP, CheckKind.SSL):
                result = await self._check_http(check)
            elif check.kind == CheckKind.TCP:
                result = await self._check_tcp(check)
            elif check.kind == CheckKind.ICMP:
                result = await self._check_icmp(check)
            elif check.kind == CheckKind.SSH:
                result = await self._check_ssh(check)
            elif check.kind == CheckKind.SSL:
                result = await self._check_ssl(check)
            elif check.kind == CheckKind.HEARTBEAT:
                result = PingRecord(id=ping.id, created=time.time(), status="up")
                check.last_status_code = 0
            else:
                result = await self._check_http(check)

            result.manual = False
            return result

        except Exception as e:
            check.last_error = str(e)
            return PingRecord(
                id=ping.id, created=time.time(), status="down",
                body_preview=str(e)[:200]
            )

    async def _check_http(self, check: MonitorCheck) -> PingRecord:
        start = time.time()
        url = check.url
        if not url.startswith("http"):
            url = f"http://{url}"

        req = urllib.request.Request(
            url,
            method=check.method or "GET",
            headers={"User-Agent": "luosrvemon/1.0"}
        )

        try:
            with urllib.request.urlopen(req, timeout=check.timeout) as resp:
                duration_ms = round((time.time() - start) * 1000, 1)
                status_code = resp.status
                body = resp.read(4096).decode("utf-8", errors="ignore")

                check.last_status_code = status_code
                check.last_response_body = body[:500]
                check.last_duration_ms = duration_ms

                action = self._evaluate_response(check, body, status_code)

                return PingRecord(
                    id=check.last_ping_id,
                    created=time.time(),
                    status=action,
                    duration_ms=duration_ms,
                    body_preview=body[:200]
                )
        except urllib.error.HTTPError as e:
            duration_ms = round((time.time() - start) * 1000, 1)
            body = e.read(4096).decode("utf-8", errors="ignore")
            check.last_status_code = e.code
            check.last_response_body = body[:500]
            check.last_duration_ms = duration_ms

            action = self._evaluate_response(check, body, e.code)
            return PingRecord(
                id=check.last_ping_id,
                created=time.time(),
                status=action,
                duration_ms=duration_ms,
                body_preview=body[:200]
            )
        except Exception as e:
            return PingRecord(
                id=check.last_ping_id,
                created=time.time(),
                status="down",
                body_preview=str(e)[:200]
            )

    def _evaluate_response(self, check: MonitorCheck, body: str, status_code: int) -> str:
        """Determine if this check is success/fail based on keyword rules"""
        if check.filter_body and check.failure_keyword:
            if check.failure_keyword.lower() in body.lower():
                return "down"
        if check.filter_body and check.success_kw:
            if check.success_kw.lower() in body.lower():
                return "up"
        if check.filter_body and check.start_kw:
            if check.start_kw.lower() in body.lower():
                return "starting"
        if check.filter_body and check.filter_default_fail:
            return "down"
        if status_code == check.expected_code:
            return "up"
        if check.expected_keyword:
            if check.expected_keyword.lower() in body.lower():
                return "up"
        return "down"

    async def _check_tcp(self, check: MonitorCheck) -> PingRecord:
        start = time.time()
        host = check.url.split(":")[0] if ":" in check.url else check.url
        port = check.port or 80

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=check.timeout
            )
            duration_ms = round((time.time() - start) * 1000, 1)
            writer.close()
            await writer.wait_closed()
            check.last_duration_ms = duration_ms
            return PingRecord(id=check.last_ping_id, created=time.time(), status="up", duration_ms=duration_ms)
        except asyncio.TimeoutError:
            return PingRecord(id=check.last_ping_id, created=time.time(), status="down", duration_ms=round(check.timeout * 1000, 1))
        except Exception as e:
            return PingRecord(id=check.last_ping_id, created=time.time(), status="down", body_preview=str(e)[:200])

    async def _check_icmp(self, check: MonitorCheck) -> PingRecord:
        start = time.time()
        host = check.url
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", str(int(check.timeout)), host,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            rc = await proc.wait()
            duration_ms = round((time.time() - start) * 1000, 1)
            check.last_duration_ms = duration_ms
            return PingRecord(id=check.last_ping_id, created=time.time(), status="up" if rc == 0 else "down", duration_ms=duration_ms)
        except Exception:
            return PingRecord(id=check.last_ping_id, created=time.time(), status="down", duration_ms=round(check.timeout * 1000, 1))

    async def _check_ssh(self, check: MonitorCheck) -> PingRecord:
        start = time.time()
        host = check.url
        port = check.port or 22
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=check.timeout
            )
            banner = (await reader.read(256)).decode("utf-8", errors="ignore").strip()
            duration_ms = round((time.time() - start) * 1000, 1)
            writer.close()
            await writer.wait_closed()
            check.last_response_body = banner
            check.last_duration_ms = duration_ms
            return PingRecord(id=check.last_ping_id, created=time.time(), status="up", duration_ms=duration_ms, body_preview=banner[:100])
        except Exception as e:
            return PingRecord(id=check.last_ping_id, created=time.time(), status="down", body_preview=str(e)[:200])

    async def _check_ssl(self, check: MonitorCheck) -> PingRecord:
        """SSL certificate expiry check"""
        if not SSL_SUPPORT:
            return await self._check_tcp(check)

        start = time.time()
        host = check.url.split(":")[0]
        port = check.port or 443

        try:
            context = ssl.create_default_context()
            with socket.create_connection((host, port), timeout=check.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=host) as ssock:
                    cert = ssock.getpeercert()
                    not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
                    now = datetime.utcnow()
                    days_left = (not_after - now).days
                    duration_ms = round((time.time() - start) * 1000, 1)

                    check.ssl_expiry_days = days_left
                    check.last_duration_ms = duration_ms

                    if days_left <= 0:
                        return PingRecord(id=check.last_ping_id, created=time.time(), status="down", body_preview=f"SSL expired {abs(days_left)} days ago", duration_ms=duration_ms)
                    elif days_left <= 30:
                        return PingRecord(id=check.last_ping_id, created=time.time(), status="down", body_preview=f"SSL expires in {days_left} days", duration_ms=duration_ms)
                    else:
                        return PingRecord(id=check.last_ping_id, created=time.time(), status="up", duration_ms=duration_ms, body_preview=f"SSL OK — {days_left} days left")
        except Exception as e:
            return PingRecord(id=check.last_ping_id, created=time.time(), status="down", body_preview=str(e)[:200])

# ─────────────────────────────────────────────────────────
# ALERTING ENGINE
# ─────────────────────────────────────────────────────────

class AlertEngine:
    def __init__(self, checks: list[MonitorCheck]):
        self.checks = checks

    def build_payload(self, check: MonitorCheck, status: str) -> dict:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
        emoji = "✅" if status == "up" else "❌"
        uptime_pct = self._calc_uptime(check)

        return {
            "check": check.name,
            "url": check.url,
            "kind": check.kind,
            "status": status,
            "message": f"{emoji} [{check.name}] is {status.upper()} — {check.url}",
            "ts": ts,
            "error": check.last_error,
            "latency_ms": check.last_duration_ms,
            "status_code": check.last_status_code,
            "uptime_pct": uptime_pct,
        }

    def _calc_uptime(self, check: MonitorCheck) -> float:
        if not check.downtimes:
            return 100.0
        total_down = sum(d.duration_s or 0 for d in check.downtimes)
        total_time = time.time() - (check.downtimes[0].start if check.downtimes else time.time())
        if total_time <= 0:
            return 100.0
        return round(max(0, (1 - total_down / total_time) * 100), 2)

    async def send_discord(self, webhook_url: str, payload: dict) -> bool:
        try:
            import urllib.request
            data = json.dumps({
                "embeds": [{
                    "title": f"{'✅' if payload['status']=='up' else '❌'} {payload['check']} — {payload['status'].upper()}",
                    "description": f"**URL:** {payload['url']}\n**Latency:** {payload['latency_ms']}ms\n**Uptime:** {payload['uptime_pct']}%\n**Error:** {payload['error'] or 'none'}",
                    "color": 0x3fb950 if payload['status'] == 'up' else 0xef4444,
                    "footer": {"text": f"luosrvemon • {payload['ts']}"}
                }]
            }).encode()
            req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            return True
        except Exception:
            return False

    async def send_slack(self, webhook_url: str, payload: dict) -> bool:
        try:
            import urllib.request
            icon = ":white_check_mark:" if payload['status'] == 'up' else ":x:"
            data = json.dumps({
                "blocks": [{
                    "type": "header",
                    "text": {"type": "plain_text", "text": f"{icon} {payload['check']} — {payload['status'].upper()}"}
                }, {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*URL:*\n{payload['url']}"},
                        {"type": "mrkdwn", "text": f"*Latency:*\n{round(payload['latency_ms'], 1) if payload['latency_ms'] else 'N/A'}ms"},
                        {"type": "mrkdwn", "text": f"*Uptime:*\n{payload['uptime_pct']}%"},
                        {"type": "mrkdwn", "text": f"*Error:*\n{payload['error'] or 'none'[:80]}"},
                    ]
                }, {
                    "type": "context", "elements": [{"type": "mrkdwn", "text": f"luosrvemon • {payload['ts']}"}]
                }]
            }).encode()
            req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            return True
        except Exception:
            return False

    async def send_telegram(self, bot_token: str, chat_id: str, payload: dict) -> bool:
        try:
            import urllib.request
            msg = f"*{payload['check']}* — {payload['status'].upper()}\n"
            msg += f"URL: {payload['url']}\n"
            if payload['error']:
                msg += f"Error: {payload['error']}\n"
            msg += f"Latency: {round(payload['latency_ms'],1) if payload['latency_ms'] else 'N/A'}ms\n"
            msg += f"Uptime: {payload['uptime_pct']}%\n"
            msg += f"Time: {payload['ts']}"

            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "Markdown"}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            return True
        except Exception:
            return False

    async def send_webhook(self, webhook_url: str, payload: dict) -> bool:
        try:
            import urllib.request
            data = json.dumps(payload).encode()
            req = urllib.request.Request(webhook_url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            return True
        except Exception:
            return False

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        try:
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body)
            msg["Subject"] = subject
            msg["From"] = "luosrvemon@localhost"
            msg["To"] = to
            # Read SMTP config from env
            smtp_host = os.getenv("SMTP_HOST", "localhost")
            smtp_port = int(os.getenv("SMTP_PORT", "25"))
            smtp_user = os.getenv("SMTP_USER", "")
            smtp_pass = os.getenv("SMTP_PASS", "")
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                if smtp_user:
                    s.starttls()
                    s.login(smtp_user, smtp_pass)
                s.sendmail(msg["From"], [to], msg.as_string())
            return True
        except Exception:
            return False

# ─────────────────────────────────────────────────────────
# STATUS BADGE GENERATOR
# ─────────────────────────────────────────────────────────

BADGE_COLORS = {"up": "success", "down": "critical", "paused": "inactive", "late": "important"}

def get_status_badge_svg(label: str, status: str) -> str:
    color = {"up": "3fb950", "down": "ef4444", "paused": "8b949e", "late": "e3b341"}.get(status, "8b949e")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20">
  <rect width="120" height="20" rx="3" fill="#161b22"/>
  <rect x="60" width="60" height="20" rx="0 3 3 0" fill="#{color}"/>
  <text x="8" y="14" font-family="Courier New,monospace" font-size="11" fill="#e6edf3">{label}</text>
  <text x="66" y="14" font-family="Courier New,monospace" font-size="11" fill="#ffffff">{status.upper()}</text>
</svg>'''

def get_status_badge_json(status: str, total: int = 1, down: int = 0) -> dict:
    return {"schemaVersion": 1, "status": status, "total": total, "down": down}

# ─────────────────────────────────────────────────────────
# MONITOR STORE (persistent JSON)
# ─────────────────────────────────────────────────────────

class MonitorStore:
    def __init__(self, path: str = ".luosrvemon"):
        self.path = Path(path)
        self.checks: list[MonitorCheck] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                    for d in data.get("checks", []):
                        d.setdefault("ping_history", [])
                        d.setdefault("downtimes", [])
                        d.setdefault("alerts", [])
                        d.setdefault("current_downtime", None)
                        d.setdefault("is_paused", False)
                        d.setdefault("consecutive_failures", 0)
                        d.setdefault("last_ping_id", 0)
                        d.setdefault("last_status_code", 0)
                        d.setdefault("last_error", "")
                        d.setdefault("last_response_body", "")
                        d.setdefault("last_duration_ms", 0)
                        d.setdefault("last_start", 0)
                        self.checks.append(MonitorCheck(**d))
            except (json.JSONDecodeError, Exception):
                pass

    def save(self):
        data = {"checks": [c.to_dict() for c in self.checks], "saved_at": time.time()}
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def add_check(self, check: MonitorCheck):
        self.checks.append(check)
        self.save()

    def get_check(self, check_id: str) -> MonitorCheck | None:
        for c in self.checks:
            if c.id == check_id:
                return c
        return None

    def remove_check(self, check_id: str):
        self.checks = [c for c in self.checks if c.id != check_id]
        self.save()

    def pause_check(self, check_id: str):
        c = self.get_check(check_id)
        if c:
            c.is_paused = True
            c.status = Status.PAUSED
            self.save()

    def resume_check(self, check_id: str):
        c = self.get_check(check_id)
        if c:
            c.is_paused = False
            c.consecutive_failures = 0
            self.save()

# ─────────────────────────────────────────────────────────
# MAIN MONITOR RUNNER
# ─────────────────────────────────────────────────────────

class MonitorRunner:
    def __init__(self, store_path: str = ".luosrvemon"):
        self.store = MonitorStore(store_path)
        self.engine = CheckEngine()
        self.alert_engine = AlertEngine(self.store.checks)
        self._running = False

    async def run_check(self, check: MonitorCheck) -> PingRecord:
        result = await self.engine.check(check)
        check.last_ping = result.created
        check.last_duration_ms = result.duration_ms or 0

        prev_status = check.status

        if result.status == "starting":
            check.status = Status.STARTING
        elif result.status == "down":
            check.consecutive_failures += 1
            if check.consecutive_failures >= check.max_retries:
                check.status = Status.DOWN
        else:
            check.consecutive_failures = 0
            check.status = Status.UP

        # Track downtime
        if check.status == Status.DOWN and check.current_downtime is None:
            check.current_downtime = Downtime(start=time.time())

        if check.status == Status.UP and check.current_downtime:
            check.current_downtime.end = time.time()
            check.current_downtime.duration_s = check.current_downtime.end - check.current_downtime.start
            check.downtimes.append(check.current_downtime)
            check.current_downtime = None

        # Store ping history (last 100)
        check.ping_history.append(asdict(result))
        if len(check.ping_history) > 100:
            check.ping_history = check.ping_history[-100:]

        check.last_ping = time.time()

        # Alert on status change
        if prev_status != check.status:
            await self._alert(check)

        self.store.save()
        return result

    async def _alert(self, check: MonitorCheck):
        if check.is_paused:
            return

        payload = self.alert_engine.build_payload(check, check.status)
        tasks = []

        if check.discord_webhook:
            tasks.append(self.alert_engine.send_discord(check.discord_webhook, payload))
        if check.slack_webhook:
            tasks.append(self.alert_engine.send_slack(check.slack_webhook, payload))
        if check.telegram_bot_token and check.telegram_chat_id:
            tasks.append(self.alert_engine.send_telegram(check.telegram_bot_token, check.telegram_chat_id, payload))
        if check.webhook_url:
            tasks.append(self.alert_engine.send_webhook(check.webhook_url, payload))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def monitor_loop(self, interval: int = 30):
        self._running = True
        while self._running:
            tasks = []
            for check in self.store.checks:
                if check.is_paused:
                    continue
                now = time.time()
                if now >= check.next_check:
                    check.next_check = now + check.interval
                    tasks.append(self.run_check(check))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            await asyncio.sleep(5)

    def stop(self):
        self._running = False

# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

def generate_id() -> str:
    return hashlib.sha256(str(time.time() + random.random()).encode()).hexdigest()[:12]

def parse_url(url: str) -> tuple[str, str, int]:
    """Parse URL into (kind, host, port)"""
    if url.startswith("http://"):
        return "http", url[7:].split("/")[0], 80
    elif url.startswith("https://"):
        return "ssl", url[8:].split("/")[0], 443
    elif url.startswith("tcp://"):
        parts = url[6:].split(":")
        return "tcp", parts[0], int(parts[1]) if len(parts) > 1 else 80
    elif url.startswith("ssh://"):
        parts = url[6:].split(":")
        return "ssh", parts[0], int(parts[1]) if len(parts) > 1 else 22
    elif url.startswith("icmp://"):
        return "icmp", url[7:], 0
    else:
        return "http", url.split("/")[0], 80

async def cmd_monitor(args):
    """Run continuous monitoring"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    if RICH:
        console.print(Panel("[bold cyan]luosrvemon[/bold cyan] — running monitors", padding=(0,1)))
    print(f"Monitoring {len(runner.store.checks)} service(s)... Press Ctrl+C to stop")
    try:
        await runner.monitor_loop()
    except KeyboardInterrupt:
        runner.stop()
        print("\nStopped.")

async def cmd_list(args):
    """List all monitors"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    if not runner.store.checks:
        print("No monitors configured. Add one with: luosrvemon add <url>")
        return

    table = [["ID", "NAME", "URL", "KIND", "STATUS", "LATENCY", "LAST CHECK"]]
    for c in runner.store.checks:
        latency = f"{c.last_duration_ms:.0f}ms" if c.last_duration_ms else "—"
        last = datetime.fromtimestamp(c.last_ping).strftime("%H:%M:%S") if c.last_ping else "never"
        status_color = {"up": "✅", "down": "❌", "paused": "⏸", "starting": "⏳"}.get(c.status, "?")
        table.append([c.id[:8], c.name[:20], c.url[:35], c.kind, f"{status_color} {c.status}", latency, last])

    if RICH:
        t = Table(box=None, show_header=True, header_style="bold cyan")
        for col in table[0]:
            t.add_column(col)
        for row in table[1:]:
            t.add_row(*row)
        console.print(t)
    else:
        for row in table:
            print("  ".join(str(x)[:25] for x in row))

async def cmd_add(args):
    """Add a new monitor"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    kind, host, port = parse_url(args.url)
    check_id = generate_id()

    check = MonitorCheck(
        id=check_id,
        name=args.name or host,
        url=args.url,
        kind=kind,
        port=args.port or port,
        timeout=args.timeout or 10.0,
        interval=args.interval or 60,
        grace=args.grace or 60,
        max_retries=args.retries or 3,
        tags=args.tags.split(",") if args.tags else [],
        webhook_url=args.webhook or "",
        slack_webhook=args.slack or "",
        discord_webhook=args.discord or "",
        telegram_bot_token=args.telegram_bot or "",
        telegram_chat_id=args.telegram_chat or "",
        expected_code=args.expected_code or 200,
        expected_keyword=args.keyword or "",
        failure_keyword=args.fail_keyword or "",
        success_kw=args.success_kw or "",
        filter_body=bool(args.success_kw or args.fail_keyword),
    )

    runner.store.add_check(check)
    print(f"✅ Added: {check.name} [{kind}] → {args.url}")
    print(f"   ID: {check_id}")

async def cmd_remove(args):
    """Remove a monitor"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    runner.store.remove_check(args.check_id)
    print(f"🗑️  Removed check: {args.check_id}")

async def cmd_pause(args):
    """Pause a monitor"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    runner.store.pause_check(args.check_id)
    print(f"⏸️  Paused: {args.check_id}")

async def cmd_resume(args):
    """Resume a monitor"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    runner.store.resume_check(args.check_id)
    print(f"▶️  Resumed: {args.check_id}")

async def cmd_status(args):
    """Show detailed status of a monitor"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    check = runner.store.get_check(args.check_id)
    if not check:
        print(f"❌ Check not found: {args.check_id}")
        return

    print(f"\n=== {check.name} [{check.id[:8]}] ===")
    print(f"  URL:     {check.url}")
    print(f"  Kind:    {check.kind}")
    print(f"  Status:  {check.status}")
    print(f"  Latency: {check.last_duration_ms:.1f}ms" if check.last_duration_ms else "  Latency: —")
    print(f"  Last:    {datetime.fromtimestamp(check.last_ping).strftime('%Y-%m-%d %H:%M:%S') if check.last_ping else 'never'}")
    print(f"  Interval: {check.interval}s | Grace: {check.grace}s | Retries: {check.max_retries}")
    print(f"  Tags:    {', '.join(check.tags) or 'none'}")
    if check.last_error:
        print(f"  Error:   {check.last_error}")
    if check.last_response_body:
        print(f"  Banner:  {check.last_response_body[:100]}")

    # Uptime calculation
    if check.downtimes:
        total_down = sum(d.duration_s or 0 for d in check.downtimes)
        first = check.downtimes[0].start
        total = time.time() - first
        uptime = max(0, (1 - total_down / total) * 100) if total > 0 else 100
        print(f"  Uptime:  {uptime:.2f}%")
        print(f"  Downtimes: {len(check.downtimes)}")
    else:
        print(f"  Uptime:  100.00%")
        print(f"  Downtimes: 0")

async def cmd_history(args):
    """Show ping history"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    check = runner.store.get_check(args.check_id)
    if not check:
        print(f"❌ Check not found: {args.check_id}")
        return

    limit = args.limit or 20
    history = check.ping_history[-limit:]
    print(f"\n=== Ping History: {check.name} (last {len(history)}) ===")
    for p in reversed(history):
        ts = datetime.fromtimestamp(p['created']).strftime("%Y-%m-%d %H:%M:%S")
        icon = {"up": "✅", "down": "❌", "starting": "⏳"}.get(p['status'], "?")
        latency = f"{p['duration_ms']:.1f}ms" if p['duration_ms'] else "—"
        body = p.get('body_preview', '')[:60] or ""
        print(f"  {icon} {ts}  {p['status']:10s}  {latency:>10s}  {body}")

async def cmd_badge(args):
    """Generate status badge"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    check = runner.store.get_check(args.check_id)

    if args.format == "svg":
        label = check.name[:20] if check else args.check_id[:8]
        svg = get_status_badge_svg(label, check.status if check else "unknown")
        print(svg)
    elif args.format == "json":
        if not check:
            print('{"error": "check not found"}')
            return
        print(json.dumps(get_status_badge_json(check.status)))
    elif args.format == "shields":
        if not check:
            print('{"error": "check not found"}')
            return
        color = {"up": "success", "down": "critical", "paused": "inactive"}.get(check.status, "lightgrey")
        print(json.dumps({
            "schemaVersion": 1,
            "label": check.name[:20],
            "message": check.status.upper(),
            "color": color
        }))

async def cmd_check(args):
    """Run a single check now"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    check = runner.store.get_check(args.check_id)
    if not check:
        print(f"❌ Check not found: {args.check_id}")
        return

    result = await runner.run_check(check)
    icon = {"up": "✅", "down": "❌", "starting": "⏳"}.get(result.status, "?")
    latency = f"{result.duration_ms:.1f}ms" if result.duration_ms else "—"
    body = result.body_preview[:100] if result.body_preview else ""
    ts = datetime.fromtimestamp(result.created).strftime("%H:%M:%S")
    print(f"{icon} [{ts}] {result.status:10s}  latency={latency}  {body}")

async def cmd_stats(args):
    """Show aggregate stats"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    checks = runner.store.checks
    up = sum(1 for c in checks if c.status == Status.UP)
    down = sum(1 for c in checks if c.status == Status.DOWN)
    paused = sum(1 for c in checks if c.is_paused)

    print(f"\n=== luosrvemon Stats ===")
    print(f"  Total:   {len(checks)}")
    print(f"  Up:      {up} ✅")
    print(f"  Down:    {down} ❌")
    print(f"  Paused:  {paused} ⏸")
    print(f"  Unknown: {len(checks) - up - down - paused} ?")

    avg_latency = sum(c.last_duration_ms for c in checks if c.last_duration_ms) / max(1, sum(1 for c in checks if c.last_duration_ms))
    print(f"  Avg latency: {avg_latency:.1f}ms")

async def cmd_export(args):
    """Export monitors as JSON"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    data = {"checks": [c.to_dict() for c in runner.store.checks], "exported_at": time.time()}
    print(json.dumps(data, indent=2))

async def cmd_import(args):
    """Import monitors from JSON"""
    import json as j
    with open(args.file) as f:
        data = j.load(f)

    store_path = args.store or ".luosrvemon"
    runner = MonitorStore(store_path)

    for d in data.get("checks", []):
        d["ping_history"] = []
        d["downtimes"] = []
        d["alerts"] = []
        runner.checks.append(MonitorCheck(**d))

    runner.save()
    print(f"✅ Imported {len(runner.checks)} monitors")

async def cmd_report(args):
    """Generate a report"""
    runner = MonitorRunner(args.store or ".luosrvemon")
    for check in runner.store.checks:
        if check.downtimes:
            total_down = sum(d.duration_s or 0 for d in check.downtimes)
            first = check.downtimes[0].start
            total = time.time() - first
            uptime = max(0, (1 - total_down / total) * 100) if total > 0 else 100
            longest_down = max((d.duration_s or 0) for d in check.downtimes)
            down_count = len(check.downtimes)
        else:
            uptime = 100.0
            longest_down = 0
            down_count = 0

        print(f"{check.name:30s}  {uptime:6.2f}%  down={down_count}  longest={longest_down:.0f}s  latency={check.last_duration_ms:.0f}ms")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="luosrvemon — Service Uptime Monitor by luokai", prog="luosrvemon")
    sub = parser.add_subparsers(dest="cmd")

    # add
    p = sub.add_parser("add", help="Add a new monitor")
    p.add_argument("url", help="URL or host to monitor")
    p.add_argument("--name", "-n", help="Display name")
    p.add_argument("--interval", "-i", type=int, default=60, help="Check interval in seconds")
    p.add_argument("--timeout", "-t", type=float, default=10.0, help="Request timeout")
    p.add_argument("--port", "-p", type=int, help="Port override")
    p.add_argument("--grace", "-g", type=int, default=60, help="Grace period before alerting")
    p.add_argument("--retries", "-r", type=int, default=3, help="Max consecutive failures before alert")
    p.add_argument("--tags", help="Comma-separated tags")
    p.add_argument("--webhook", help="Webhook URL for alerts")
    p.add_argument("--slack", help="Slack webhook URL")
    p.add_argument("--discord", help="Discord webhook URL")
    p.add_argument("--telegram-bot", help="Telegram bot token")
    p.add_argument("--telegram-chat", help="Telegram chat ID")
    p.add_argument("--expected-code", type=int, default=200, help="Expected HTTP status code")
    p.add_argument("--keyword", "-k", help="Expected keyword in response body")
    p.add_argument("--fail-keyword", help="Keyword that means failure")
    p.add_argument("--success-kw", help="Keyword that means success")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_add)

    # list
    p = sub.add_parser("list", help="List all monitors")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_list)

    # monitor
    p = sub.add_parser("monitor", help="Run continuous monitoring")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_monitor)

    # status
    p = sub.add_parser("status", help="Show monitor status")
    p.add_argument("check_id", help="Check ID")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_status)

    # history
    p = sub.add_parser("history", help="Show ping history")
    p.add_argument("check_id", help="Check ID")
    p.add_argument("--limit", "-n", type=int, default=20)
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_history)

    # badge
    p = sub.add_parser("badge", help="Generate status badge")
    p.add_argument("check_id", help="Check ID")
    p.add_argument("--format", "-f", choices=["svg", "json", "shields"], default="svg")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_badge)

    # check (run now)
    p = sub.add_parser("check", help="Run a check immediately")
    p.add_argument("check_id", help="Check ID")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_check)

    # stats
    p = sub.add_parser("stats", help="Show aggregate stats")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_stats)

    # report
    p = sub.add_parser("report", help="Show uptime report")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_report)

    # pause/resume/remove
    for cmd, func in [("pause", cmd_pause), ("resume", cmd_resume), ("remove", cmd_remove)]:
        p = sub.add_parser(cmd, help=f"{cmd.capitalize()} a monitor")
        p.add_argument("check_id", help="Check ID")
        p.add_argument("--store", help="Store file path")
        p.set_defaults(func=func)

    # export/import
    p = sub.add_parser("export", help="Export monitors")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("import", help="Import monitors")
    p.add_argument("file", help="JSON file to import")
    p.add_argument("--store", help="Store file path")
    p.set_defaults(func=cmd_import)

    args = parser.parse_args()

    if args.cmd is None:
        parser.print_help()
        return

    if args.cmd == "monitor":
        asyncio.run(cmd_monitor(args))
    else:
        asyncio.run(args.func(args))

if __name__ == "__main__":
    main()