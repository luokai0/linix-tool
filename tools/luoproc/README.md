# luoproc — Advanced Process Explorer & Manager

> Smarter than `ps`, lighter than `htop`. Filter, sort, kill, tree-view, and watch processes — pure Python, zero dependencies.

## Why luoproc?

| Feature | `ps aux` | `htop` | **luoproc** |
|---|---|---|---|
| No install needed | ✓ | ✗ | ✓ |
| Process tree | ✗ | ✓ | ✓ |
| Filter by name/user | partial | partial | ✓ |
| Detailed per-PID info | ✗ | ✗ | ✓ |
| Colour-coded output | ✗ | ✓ | ✓ |
| Live watch mode | ✗ | ✓ | ✓ |
| Show env vars | ✗ | ✗ | ✓ |

## Install

```bash
chmod +x luoproc.py
sudo ln -s $(pwd)/luoproc.py /usr/local/bin/luoproc
```

## Usage

```
luoproc list                        # all processes, sorted by CPU
luoproc list --sort mem -n 20       # top 20 by memory
luoproc list --name python          # filter by name
luoproc list --user www-data        # filter by user

luoproc tree                        # full process tree
luoproc tree --name bash            # filtered tree

luoproc watch                       # live dashboard (2s refresh)
luoproc watch --sort mem -n 15      # live by memory
luoproc watch -i 5                  # custom refresh interval

luoproc info 1234                   # detailed info for PID
luoproc info 1234 --env             # include env variables

luoproc kill 1234 1235              # SIGTERM
luoproc kill 1234 --signal SIGKILL  # force kill

luoproc find nginx                  # find by name pattern
```

## Output Columns

- **PID** — process ID  
- **USER** — owner username  
- **ST** — state: `R`=running `S`=sleeping `D`=disk wait `Z`=zombie `T`=stopped  
- **CPU%** — CPU usage (green < 10%, yellow < 50%, red ≥ 50%)  
- **MEM(MB)** — resident set size in MB  
- **VIRT(MB)** — virtual memory size in MB  
- **THR** — thread count  

## License
MIT — luokai
