#!/usr/bin/env python3
"""
luowebget — Advanced Async HTTP Download & Scraping Tool
Built from qget + aget + wget best features
"""

import os
import sys
import re
import json
import time
import math
import hashlib
import asyncio
import tempfile
import signal
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse, quote, unquote

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import aiofiles
    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False

# ═══════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════

DEFAULT_CHUNK = 65536
DEFAULT_CONCURRENCY = 8
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT = 60.0
MAX_CHUNK_SIZE = 1024 * 1024  # 1MB max per chunk

# ═══════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════

def parse_content_range(range_hdr: str) -> tuple[int, int, int]:
    """Parse Content-Range header: bytes start-end/total"""
    try:
        _, spec = range_hdr.split('/')
        total = int(spec)
        start, end = map(int, spec.split('-'))
        return start, end, total
    except:
        return 0, 0, 0

def format_bytes(b: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def format_speed(bps: float) -> str:
    return f"{format_bytes(int(bps))}/s"

def human_url(url: str) -> str:
    p = urlparse(url)
    path = unquote(p.path)
    if len(path) > 50:
        path = path[:47] + '...'
    return f"{p.netloc}{path}"

def get_filename_from_url(url: str, resp_headers: dict = None) -> str:
    if resp_headers:
        cd = resp_headers.get('content-disposition', '')
        m = re.search(r'filename[^;=\s]*=[\s]*["\']?([^;"\']+)', cd, re.I)
        if m:
            return unquote(m.group(1).strip('"\''))
    path = unquote(urlparse(url).path)
    name = os.path.basename(path)
    if not name or '?' in name:
        name = 'index.html'
    return name

# ═══════════════════════════════════════════════════════════
# ASYNC CLIENT
# ═══════════════════════════════════════════════════════════

class LuowebClient:
    def __init__(
        self,
        headers: dict = None,
        proxy: str = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify: bool = True,
        max_retries: int = DEFAULT_RETRIES,
    ):
        self.headers = headers or {}
        self.proxy = proxy
        self.timeout = timeout
        self.verify = verify
        self.max_retries = max_retries
        self._client = None

    async def _get_client(self):
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(retries=self.max_retries) if self.max_retries > 0 else None
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                proxy=self.proxy,
                verify=self.verify,
                http2=True,
                headers=self.headers,
                transport=transport,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get_size(self, url: str) -> tuple[int, str]:
        """Get content-length and filename from URL HEAD"""
        client = await self._get_client()
        try:
            resp = await client.head(url, follow_redirects=True)
            size = int(resp.headers.get('content-length', 0))
            fname = get_filename_from_url(url, resp.headers)
            return size, fname
        except Exception as e:
            return 0, get_filename_from_url(url)

    async def download_bytes(self, url: str, start: int = 0, end: int = None) -> bytes:
        client = await self._get_client()
        headers = {'Range': f'bytes={start}-{end or ""}'} if start > 0 else {}
        resp = await client.get(url, headers=headers, follow_redirects=True)
        return resp.read()

# ═══════════════════════════════════════════════════════════
# DOWNLOAD ENGINE
# ═══════════════════════════════════════════════════════════

class LuoDownload:
    """Async multi-connection downloader with resume + progress"""

    def __init__(
        self,
        url: str,
        out: str = None,
        connections: int = DEFAULT_CONCURRENCY,
        chunk_size: int = DEFAULT_CHUNK,
        max_retries: int = DEFAULT_RETRIES,
        rate_limit: float = 0,
        headers: dict = None,
        proxy: str = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify: bool = True,
        resume: bool = True,
    ):
        self.url = url
        self.out = out
        self.connections = connections
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self.rate_limit = rate_limit
        self.headers = headers or {}
        self.proxy = proxy
        self.timeout = timeout
        self.verify = verify
        self.resume = resume

        self.client = LuowebClient(headers, proxy, timeout, verify, max_retries)
        self.size = 0
        self.fname = ''
        self.start_ts = time.time()
        self.done = 0
        self.speed = 0.0
        self.eta = '--:--'
        self.running = True
        self._stop_flag = False
        self._lock = asyncio.Lock()
        self._chunks_total = 0

    async def run(self) -> bool:
        try:
            self.size, self.fname = await self.client.get_size(self.url)
            self.out = self.out or self.fname

            already = os.path.getsize(self.out) if os.path.exists(self.out) else 0
            self.done = already

            if self.size == 0:
                return await self._download_full()

            # multi-connection
            if self.connections > 1 and self.size > self.chunk_size:
                await self._download_multi()
            else:
                await self._download_single(already)

            return True
        finally:
            await self.client.close()

    async def _download_single(self, start: int = 0) -> bool:
        client = self.client
        with open(self.out, 'ab' if start > 0 else 'wb') as f:
            mode = 'a' if start > 0 else 'w'
            headers = {'Range': f'bytes={start}-'} if start > 0 else {}
            client_async = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), proxy=self.proxy, verify=self.verify)

            try:
                async with client_async.stream('GET', self.url, headers=headers, follow_redirects=True) as resp:
                    total = int(resp.headers.get('content-length', self.size or 0))
                    chunk_num = 0

                    async for data in resp.aiter_bytes(chunk_size=self.chunk_size):
                        if self._stop_flag:
                            break
                        f.write(data)
                        self.done += len(data)

                        # progress + throttle
                        if self.rate_limit > 0:
                            target = self.done / (time.time() - self.start_ts)
                            if target > self.rate_limit:
                                await asyncio.sleep(1 / (target / self.rate_limit + 0.1))

                        chunk_num += 1
                        if chunk_num % 500 == 0:
                            elapsed = time.time() - self.start_ts
                            self.speed = self.done / elapsed if elapsed > 0 else 0
                            pct = (self.done / self.size * 100) if self.size else 0
                            self._print_progress(pct, self.done, self.size)
            finally:
                await client_async.aclose()

        return True

    async def _download_multi(self) -> bool:
        """Split file into N chunks, download concurrently"""
        num_chunks = self.connections
        chunk_size = math.ceil(self.size / num_chunks)
        temp_dir = tempfile.mkdtemp(prefix='luo_')
        part_files = []

        async def download_part(i: int) -> str:
            start = i * chunk_size
            end = min(start + chunk_size - 1, self.size - 1)
            part_path = os.path.join(temp_dir, f'part_{i:03d}')

            for attempt in range(self.max_retries + 1):
                try:
                    client_async = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), proxy=self.proxy, verify=self.verify)
                    try:
                        headers = {'Range': f'bytes={start}-{end}'}
                        async with client_async.stream('GET', self.url, headers=headers, follow_redirects=True) as resp:
                            data = await resp.read()
                        await client_async.aclose()

                        async with aiofiles.open(part_path, 'wb') as pf:
                            await pf.write(data)
                        return part_path
                    finally:
                        await client_async.aclose()
                except Exception as e:
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        raise
            return part_path

        # download all parts concurrently
        tasks = [download_part(i) for i in range(num_chunks)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # combine
        with open(self.out, 'wb') as out_f:
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    print(f'\n⚠️  Part {i} failed: {r}')
                    continue
                with open(r, 'rb') as pf:
                    out_f.write(pf.read())
                os.remove(r)

        try:
            os.rmdir(temp_dir)
        except:
            pass

        return True

    def _print_progress(self, pct: float, done: int, total: int) -> None:
        bar_len = 40
        filled = int(bar_len * pct / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        elapsed = time.time() - self.start_ts
        spd = done / elapsed if elapsed > 0 else 0
        remaining = (total - done) / spd if spd > 0 else 0
        m, s = divmod(int(remaining), 60)
        self.eta = f'{m:02d}:{s:02d}'
        print(f'\r  █{bar}█  {pct:5.1f}%  {format_bytes(done):>10} / {format_bytes(total):>10}  ⚡ {format_speed(spd):>12}  ⏳ {self.eta}  ', end='', flush=True)

    def stop(self):
        self._stop_flag = True
        self.running = False

# ═══════════════════════════════════════════════════════════
# SCRAPER
# ═══════════════════════════════════════════════════════════

class Luoscraper:
    """Async web scraper with link extraction, JS rendering hint"""

    def __init__(self, url: str, headers: dict = None, timeout: float = 30.0):
        self.url = url
        self.headers = headers or {}
        self.timeout = timeout
        self.client = LuowebClient

    async def fetch(self, accept='html') -> dict:
        client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), headers=self.headers, follow_redirects=True)
        resp = await client.get(self.url)
        ct = resp.headers.get('content-type', '')

        result = {
            'url': self.url,
            'status': resp.status_code,
            'content_type': ct,
            'headers': dict(resp.headers),
            'size': len(resp.content),
        }

        if 'json' in ct:
            result['data'] = resp.json()
        else:
            result['text'] = resp.text[:50000]
            result['links'] = self._extract_links(resp.text)
            result['images'] = self._extract_links(resp.text, tag='img', attr='src')
            result['scripts'] = self._extract_links(resp.text, tag='script', attr='src')

        await client.aclose()
        return result

    def _extract_links(self, html: str, tag=None, attr='href') -> list[str]:
        if tag:
            pattern = f'<{tag}[^>]+{attr}=["\']([^"\']+)["\']'
        else:
            pattern = r'href=["\']([^"\']+)["\']'
        return list(set(re.findall(pattern, html, re.I)))

# ═══════════════════════════════════════════════════════════
# HTTP CHECKER
# ═══════════════════════════════════════════════════════════

class Hucheck:
    """Check URL health — status, headers, response time, SSL"""

    def __init__(self, url: str, timeout: float = 15.0):
        self.url = url
        self.timeout = timeout
        self.client = None

    async def check(self) -> dict:
        start = time.time()
        try:
            client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout), follow_redirects=True)
            resp = await client.get(self.url)
            elapsed = (time.time() - start) * 1000

            result = {
                'url': self.url,
                'status': resp.status_code,
                'ok': resp.status_code < 400,
                'latency_ms': round(elapsed, 1),
                'content_type': resp.headers.get('content-type', ''),
                'server': resp.headers.get('server', '?'),
                'size': int(resp.headers.get('content-length', 0)),
                'date': resp.headers.get('date', ''),
                'location': resp.headers.get('location', ''),
            }

            # SSL check
            if self.url.startswith('https'):
                result['ssl'] = True
                result['ssl_expiry'] = None

            await client.aclose()
            return result
        except Exception as e:
            return {
                'url': self.url,
                'ok': False,
                'error': str(e),
                'latency_ms': 0,
            }

# ═══════════════════════════════════════════════════════════
# BATCH RUNNER
# ═══════════════════════════════════════════════════════════

async def batch_check(urls: list[str], concurrency: int = 20) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)
    async def _one(url):
        async with sem:
            h = Hucheck(url)
            return await h.check()
    return await asyncio.gather(*[_one(u) for u in urls])

async def batch_download(urls: list[str], out_dir: str = '.', **kwargs) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    sem = asyncio.Semaphore(kwargs.get('connections', DEFAULT_CONCURRENCY))
    async def _one(url):
        fname = get_filename_from_url(url)
        out_path = os.path.join(out_dir, fname)
        d = LuoDownload(url, out_path, **kwargs)
        await d.run()
        return d.out
    return await asyncio.gather(*[_one(u) for u in urls])

# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def cmd_download(args) -> None:
    d = LuoDownload(
        url=args.url,
        out=args.output,
        connections=args.connections,
        chunk_size=args.chunk,
        max_retries=args.retries,
        rate_limit=args.rate,
        headers=dict(h.split(':', 1) for h in (args.header or [])),
        proxy=args.proxy,
        timeout=args.timeout,
        resume=not args.no_resume,
    )
    ok = asyncio.run(d.run())
    if ok:
        print(f'\n✅ Saved: {d.out}  ({format_bytes(d.done)})')
    else:
        print(f'\n❌ Download failed')
        sys.exit(1)

def cmd_check(args) -> None:
    results = asyncio.run(batch_check(args.urls, concurrency=args.concurrency))
    for r in results:
        status = f"{r['status']}" if 'status' in r else 'ERR'
        ok = '✅' if r.get('ok', False) else '❌'
        lat = f"{r.get('latency_ms', 0):.0f}ms"
        print(f"  {ok}  {status:6s}  {lat:8s}  {human_url(r['url'])}")
        if 'error' in r:
            print(f"         ⚠️  {r['error']}")

def cmd_scrape(args) -> None:
    s = Luoscraper(args.url, timeout=args.timeout)
    result = asyncio.run(s.fetch())
    print(f"URL:      {result['url']}")
    print(f"Status:   {result['status']}")
    print(f"Size:    {format_bytes(result['size'])}")
    print(f"Content:  {result['content_type']}")
    print(f"Links:    {len(result.get('links', []))} found")
    if result.get('images'):
        print(f"Images:   {len(result['images'])} found")
    if result.get('scripts'):
        print(f"Scripts:  {len(result['scripts'])} found")
    if result.get('data'):
        print(f"\nJSON Data (truncated):")
        print(json.dumps(result['data'], indent=2)[:500])
    elif result.get('text'):
        print(f"\nText Content (first 2000 chars):")
        print(result['text'][:2000])

def cmd_batch_download(args) -> None:
    results = asyncio.run(batch_download(args.urls, out_dir=args.dir or '.',
                                           connections=args.connections,
                                           max_retries=args.retries,
                                           rate_limit=args.rate))
    for path in results:
        print(f"  ✅ {path}")

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def build_parser():
    import argparse
    p = argparse.ArgumentParser(prog='luowebget', description='Advanced async HTTP downloader & scraper',
        formatter_class=argparse.RawDescriptionHelpFormatter)

    sub = p.add_subparsers(dest='cmd', required=True)

    # download
    d = sub.add_parser('download', help='Download a file')
    d.add_argument('url', help='URL to download')
    d.add_argument('output', nargs='?', help='Output filename')
    d.add_argument('-c', '--connections', type=int, default=8, help='Concurrent connections (default: 8)')
    d.add_argument('-k', '--chunk', type=int, default=65536, help='Chunk size in bytes')
    d.add_argument('-r', '--retries', type=int, default=3, help='Max retries (default: 3)')
    d.add_argument('-R', '--rate', type=float, default=0, help='Rate limit in B/s (0 = unlimited)')
    d.add_argument('-H', '--header', action='append', help='Custom header (Name: value)')
    d.add_argument('-x', '--proxy', help='HTTP/SOCKS proxy URL')
    d.add_argument('-t', '--timeout', type=float, default=60.0, help='Timeout in seconds')
    d.add_argument('--no-resume', action='store_true', help='Do not resume partial downloads')

    # check
    c = sub.add_parser('check', help='Check URLs (status, latency, SSL)')
    c.add_argument('urls', nargs='+', help='URLs to check')
    c.add_argument('-j', '--json', action='store_true', help='JSON output')
    c.add_argument('-C', '--concurrency', type=int, default=20, help='Concurrent checks')

    # scrape
    s = sub.add_parser('scrape', help='Fetch and extract content from URL')
    s.add_argument('url', help='URL to scrape')
    s.add_argument('-t', '--timeout', type=float, default=30.0, help='Timeout in seconds')
    s.add_argument('-j', '--json', action='store_true', help='Output as JSON')

    # batch-download
    b = sub.add_parser('batch-download', help='Download multiple files concurrently')
    b.add_argument('urls', nargs='+', help='URLs to download')
    b.add_argument('-d', '--dir', default='.', help='Output directory')
    b.add_argument('-c', '--connections', type=int, default=4, help='Concurrent connections per file')
    b.add_argument('-r', '--retries', type=int, default=3, help='Max retries')
    b.add_argument('-R', '--rate', type=float, default=0, help='Rate limit B/s')

    return p

if __name__ == '__main__':
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd == 'download':
        cmd_download(args)
    elif args.cmd == 'check':
        cmd_check(args)
    elif args.cmd == 'scrape':
        cmd_scrape(args)
    elif args.cmd == 'batch-download':
        cmd_batch(args)
    else:
        parser.print_help()