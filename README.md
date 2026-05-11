# linix-tool

A collection of free & useful CLI tools made by luokai — pure Python, zero dependencies.

## Tools

| Tool | Description | Category |
|---|---|---|
| [luoproc](tools/luoproc/) | Advanced process explorer — filter, sort, tree, kill, watch | System |
| [luodisk](tools/luodisk/) | Disk usage analyzer with visual bar charts | System |
| [syspeek](tools/syspeek/) | Real-time system monitor | System |
| [luodiff](tools/luodiff/) | Smart file/dir differ — side-by-side, word-level, JSON-aware | Dev |
| [luoenv](tools/luoenv/) | .env manager — list, diff, validate, scan secrets, export | Dev |
| [luocron](tools/luocron/) | Cron job manager with human-readable scheduling | Automation |
| [luossh](tools/luossh/) | SSH config manager & session launcher | Network |
| [netscan](tools/netscan/) | Advanced async port scanner | Network |
| [webget](tools/webget/) | Async HTTP downloader & scraper | Network |
| [pingpong](tools/pingpong/) | Network connectivity — ping, DNS, traceroute | Network |
| [srvemon](tools/srvemon/) | Service uptime & health monitor | Network |
| [filetree](tools/filetree/) | Directory tree visualizer & analyzer | Files |
| [imgx](tools/imgx/) | Image resize, compress, convert, compare | Files |
| [jsontool](tools/jsontool/) | CLI JSON processor — query, transform, validate | Data |
| [loggrep](tools/loggrep/) | Pattern-based log analyzer | Data |
| [cryptool](tools/cryptool/) | AES-256 encryption, hash, JWT, password gen | Security |
| [dockerman](tools/dockerman/) | Docker container manager | Containers |

## Quick Install (any tool)

```bash
git clone https://github.com/luokai0/linix-tool
cd linix-tool/tools/<toolname>
chmod +x <toolname>.py
sudo ln -s $(pwd)/<toolname>.py /usr/local/bin/<toolname>
```

## Philosophy

- **Zero dependencies** — pure Python stdlib only
- **No setup needed** — just `chmod +x` and run
- **Better defaults** — coloured output, sensible flags, helpful errors
- **luo prefix** — new tools start with `luo` to avoid conflicts

## License

MIT — luokai
