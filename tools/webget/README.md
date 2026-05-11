# luowebget — Advanced Async HTTP Downloader & Scraper by luokai

> Built from qget + aget + wget best features — pure Python, no dependencies on external tools

## Features

- **Async multi-connection downloads** — split file into N chunks, download concurrently
- **Resume support** — picks up partial downloads automatically
- **Rate limiting** — avoid saturating bandwidth
- **Batch URL checking** — status, latency, SSL expiry for 100s of URLs concurrently


- **Web scraping** — extract links, images, scripts from any HTML page
- **Batch downloads** — download multiple files concurrently
- **HTTP/2** by default for better performance

## Installation

```bash
pip install httpx aiofiles
```

## Usage

```bash
# Download a file (single connection)
python3 luowebget.py download https://example.com/file.zip

# Download with 8 concurrent connections
python3 luowebget.py download https://example.com/file.zip -c 8

# Check multiple URLs
python3 luowebget.py check https://google.com https://github.com https://twitter.com

# Scrape a page
python3 luowebget.py scrape https://news.ycombinator.com

# Batch download
python3 luowebget.py batch-download https://example.com/a.zip https://example.com/b.zip -d ./downloads/
```

## Commands

| Command | Description |
|---------|-------------|
| `download <url> [file]` | Download a file with resume + progress bar |
| `check <urls...>` | Check URL health (status, latency, SSL) |
| `scrape <url>` | Extract content, links, images from a page |
| `batch-download <urls...>` | Download multiple files concurrently |

## Options

- `-c, --connections N` — Number of concurrent connections (default: 8)
- `-k, --chunk N` — Chunk size in bytes (default: 65536)
- `-r, --retries N` — Max retries on failure (default: 3)
- `-R, --rate N` — Rate limit in B/s (0 = unlimited)
- `-H, --header "Name: value"` — Custom HTTP header
- `-x, --proxy URL` — HTTP/SOCKS proxy
- `-t, --timeout N` — Timeout in seconds (default: 60)
- `--no-resume` — Start download from scratch