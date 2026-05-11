# webget — Smart CLI Download & Scraping Tool

A powerful CLI tool for downloading files, extracting content, checking URLs, and mirroring pages.

![Python](https://img.shields.io/badge/Python-3.6+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## Features

- **download** — Download any file with progress bar + resume support
- **extract** — Pull text/HTML/JSON content from any URL
- **status** — Check HTTP status codes and basic headers
- **headers** — Full response header inspection
- **mirror** — Download all linked pages from a site

## Requirements

```bash
pip3 install httpx
```

## Usage

```bash
# Download a file
python3 webget.py download https://example.com/file.zip

# Download with custom filename
python3 webget.py download https://example.com/file.zip myfile.zip

# Extract visible text from a page
python3 webget.py extract https://example.com

# Extract JSON API response
python3 webget.py extract https://api.example.com/data

# Check if a URL is alive
python3 webget.py status https://example.com

# View all response headers
python3 webget.py headers https://example.com

# Mirror all links from a page
python3 webget.py mirror https://example.com ./mirror/
```

## Examples

```bash
# Download a large file (supports resume)
python3 webget.py download https://releases.ubuntu.com/22.04/ubuntu-22.04.iso ubuntu.iso

# Scrape article text
python3 webget.py extract https://news.ycombinator.com

# Check if your API is up
python3 webget.py status https://api.yoursite.com/health

# Debug a redirect chain
python3 webget.py headers https://google.com
```

## License

MIT — Free to use, modify, and distribute.