# luossh — SSH Config Manager & Session Launcher

> Manage, search, test, and launch SSH connections from one smart CLI. Reads `~/.ssh/config` natively — no separate database, pure Python, zero dependencies.

## Install

```bash
chmod +x luossh.py
sudo ln -s $(pwd)/luossh.py /usr/local/bin/luossh
```

## Usage

```bash
# List & search
luossh list                          # all hosts in ~/.ssh/config
luossh list web                      # filter by alias/hostname

# Add & remove
luossh add myserver -H 1.2.3.4 -u ubuntu -p 2222 -i ~/.ssh/id_ed25519
luossh add jumphost -H 10.0.0.1 -u admin --proxy bastion
luossh remove myserver

# Inspect
luossh show myserver

# Test connectivity (TCP port check, no SSH handshake needed)
luossh test                          # all hosts
luossh test myserver staging prod    # specific hosts

# Connect
luossh connect myserver              # opens SSH session
luossh connect myserver -c "df -h"   # run remote command

# Copy public key for passwordless login
luossh copy-key myserver
luossh copy-key myserver --key ~/.ssh/id_ed25519.pub
```

## How It Works

- **Reads & writes** `~/.ssh/config` directly — compatible with all SSH clients
- **No lock-in** — your config stays standard, works with plain `ssh` too
- **TCP test** — checks if the port is open before even attempting SSH

## License
MIT — luokai
