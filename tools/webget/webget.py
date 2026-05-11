#!/usr/bin/env python3
"""
webget — Smart CLI download tool
Download files, extract content, check URLs, mirror sites

Usage:
  webget.py download <url> [filename]
  webget.py extract <url>            -- show HTML/text content
  webget.py status <url>            -- check HTTP status
  webget.py headers <url>           -- show response headers
  webget.py mirror <url> <dir>      -- download all links from page
"""

import sys
import os
import re
import hashlib
from pathlib import Path

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ─── Download ───────────────────────────────────────────────

def download(url, filename=None, chunk_size=8192):
    if not HAS_HTTPX:
        print("ERROR: httpx not installed. Run: pip3 install httpx")
        return False

    try:
        filename = filename or url.split('/')[-1].split('?')[0] or "index.html"
        print(f"Downloading: {url}")
        print(f"Saving to: {filename}")

        headers = {}
        resume_pos = 0
        if os.path.exists(filename):
            resume_pos = os.path.getsize(filename)
            print(f"Resuming from byte {resume_pos}")
            headers['Range'] = f'bytes={resume_pos}-'

        with httpx.stream("GET", url, headers=headers, follow_redirects=True, timeout=30.0) as r:
            total = int(r.headers.get('content-length', 0))
            mode = 'ab' if resume_pos > 0 else 'wb'

            with open(filename, mode) as f:
                downloaded = resume_pos
                for chunk in r.iter_bytes(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            pct = (downloaded / total) * 100
                            bar = '█' * int(pct // 3) + '░' * (33 - int(pct // 3))
                            print(f"\r  {bar} {pct:.1f}%  {downloaded:,}/{total:,} bytes", end='', flush=True)
                        else:
                            print(f"\r  Downloaded: {downloaded:,} bytes", end='', flush=True)

        print(f"\n\n✅ Done: {filename}")
        return True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

# ─── Extract ────────────────────────────────────────────────

def extract(url):
    if not HAS_HTTPX:
        print("ERROR: httpx not installed. Run: pip3 install httpx")
        return False

    try:
        print(f"Fetching: {url}\n")
        r = httpx.get(url, follow_redirects=True, timeout=15.0)
        content_type = r.headers.get('content-type', '')

        if 'json' in content_type:
            import json
            data = r.json()
            print(json.dumps(data, indent=2)[:3000])
        elif 'html' in content_type:
            from html.parser import HTMLParser

            class TextExtractor(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.text = []
                    self.skip_tags = {'script', 'style', 'nav', 'footer', 'head'}
                    self.in_tag = None

                def handle_starttag(self, tag, attrs):
                    if tag in self.skip_tags:
                        self.in_tag = tag

                def handle_endtag(self, tag):
                    if tag == self.in_tag:
                        self.in_tag = None

                def handle_data(self, data):
                    if not self.in_tag and data.strip():
                        self.text.append(data.strip())

            parser = TextExtractor()
            parser.feed(r.text)
            text = '\n'.join(parser.text)
            print(text[:3000])
        else:
            print(r.text[:3000])

        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ─── Status ─────────────────────────────────────────────────

def check_status(url):
    if not HAS_HTTPX:
        print("ERROR: httpx not installed. Run: pip3 install httpx")
        return False

    try:
        print(f"Checking: {url}\n")
        r = httpx.head(url, follow_redirects=True, timeout=15.0)
        print(f"  Status:     {r.status_code} {'✅' if r.status_code < 400 else '❌'}")
        print(f"  Headers:")
        for k in ['content-type', 'content-length', 'server', 'date']:
            if k in r.headers:
                print(f"    {k}: {r.headers[k]}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ─── Headers ────────────────────────────────────────────────

def show_headers(url):
    if not HAS_HTTPX:
        print("ERROR: httpx not installed. Run: pip3 install httpx")
        return False

    try:
        r = httpx.get(url, follow_redirects=True, timeout=15.0)
        print(f"Response headers for: {url}\n")
        for k, v in r.headers.items():
            print(f"  {k}: {v}")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ─── Mirror ────────────────────────────────────────────────

def mirror(url, dir):
    if not HAS_HTTPX:
        print("ERROR: httpx not installed. Run: pip3 install httpx")
        return False

    try:
        Path(dir).mkdir(parents=True, exist_ok=True)
        print(f"Fetching: {url}")
        r = httpx.get(url, follow_redirects=True, timeout=30.0)
        content = r.text

        base_url = url.rstrip('/')
        links = re.findall(r'href=["\']([^"\']+)["\']', content)
        files = []
        for link in links:
            if link.startswith('http') and base_url not in link:
                continue
            if link.startswith('/') or not link.startswith('http'):
                full = base_url + link if link.startswith('/') else f"{base_url}/{link}"
                fname = hashlib.md5(full.encode()).hexdigest()[:12]
                ext = os.path.splitext(link)[1] or '.html'
                out = os.path.join(dir, fname + ext)
                try:
                    r2 = httpx.get(full, timeout=15.0)
                    with open(out, 'wb') as f:
                        f.write(r2.content)
                    files.append((full, out))
                    print(f"  ✅ {link} -> {out}")
                except:
                    print(f"  ⚠️  Failed: {link}")

        print(f"\n✅ Mirrored {len(files)} pages to {dir}/")
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

# ─── CLI ────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == 'download' and len(sys.argv) >= 3:
        url = sys.argv[2]
        filename = sys.argv[3] if len(sys.argv) > 3 else None
        ok = download(url, filename)
    elif cmd == 'extract' and len(sys.argv) >= 3:
        ok = extract(sys.argv[2])
    elif cmd == 'status' and len(sys.argv) >= 3:
        ok = check_status(sys.argv[2])
    elif cmd == 'headers' and len(sys.argv) >= 3:
        ok = show_headers(sys.argv[2])
    elif cmd == 'mirror' and len(sys.argv) >= 4:
        ok = mirror(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        ok = False

    sys.exit(0 if ok else 1)

if __name__ == '__main__':
    main()