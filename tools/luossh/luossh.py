#!/usr/bin/env python3
"""
luossh — SSH Config Manager & Session Launcher
by luokai | MIT License

Manage, search, test, and launch SSH connections from one smart CLI.
Reads ~/.ssh/config natively — no separate database needed.
"""

import os
import sys
import re
import time
import subprocess
import argparse
import shlex
from pathlib import Path
from typing import Optional

# ── ANSI ──────────────────────────────────────────────────────────────────────
R    = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"
RED  = "\033[91m"
GRN  = "\033[92m"
YLW  = "\033[93m"
CYN  = "\033[96m"
BLU  = "\033[94m"
MGN  = "\033[95m"

def c(*args):
    return "".join(args[1:]) + str(args[0]) + R

# ── SSH config parsing ─────────────────────────────────────────────────────────

SSH_CONFIG = Path.home() / ".ssh" / "config"

class Host:
    def __init__(self, name: str, props: dict):
        self.name     = name
        self.hostname = props.get("HostName", name)
        self.user     = props.get("User", os.environ.get("USER", ""))
        self.port     = props.get("Port", "22")
        self.identity = props.get("IdentityFile", "")
        self.forward  = props.get("ForwardAgent", "no").lower()
        self.proxy    = props.get("ProxyJump", "")
        self.extra    = {k: v for k, v in props.items()
                         if k not in ("HostName","User","Port","IdentityFile","ForwardAgent","ProxyJump")}

    @property
    def is_wildcard(self):
        return "*" in self.name or "?" in self.name

def parse_ssh_config(path: Path = SSH_CONFIG) -> list[Host]:
    if not path.exists():
        return []
    hosts = []
    current_name = None
    current_props: dict[str, str] = {}

    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("host "):
            if current_name:
                hosts.append(Host(current_name, current_props))
            current_name = line.split(None, 1)[1].strip()
            current_props = {}
        elif "=" in line or " " in line:
            sep = "=" if "=" in line else " "
            k, _, v = line.partition(sep)
            current_props[k.strip()] = v.strip()

    if current_name:
        hosts.append(Host(current_name, current_props))

    return [h for h in hosts if not h.is_wildcard]

def write_host(name: str, hostname: str, user: str, port: str,
               identity: str = "", proxy: str = "", forward: str = "no",
               extra: dict = None):
    config = SSH_CONFIG
    config.parent.mkdir(parents=True, exist_ok=True)

    block = f"\nHost {name}\n"
    block += f"    HostName {hostname}\n"
    block += f"    User {user}\n"
    block += f"    Port {port}\n"
    if identity:
        block += f"    IdentityFile {identity}\n"
    if proxy:
        block += f"    ProxyJump {proxy}\n"
    if forward == "yes":
        block += f"    ForwardAgent yes\n"
    if extra:
        for k, v in extra.items():
            block += f"    {k} {v}\n"

    existing = config.read_text() if config.exists() else ""

    # check duplicate
    pattern = re.compile(rf"^Host\s+{re.escape(name)}\s*$", re.MULTILINE)
    if pattern.search(existing):
        # remove old block
        blocks = re.split(r"(?=^Host\s)", existing, flags=re.MULTILINE)
        blocks = [b for b in blocks if not re.match(rf"Host\s+{re.escape(name)}\s*$", b.strip().split("\n")[0])]
        existing = "".join(blocks)

    with config.open("w") as f:
        f.write(existing.rstrip("\n") + block)

    config.chmod(0o600)

def remove_host(name: str) -> bool:
    if not SSH_CONFIG.exists():
        return False
    text = SSH_CONFIG.read_text()
    blocks = re.split(r"(?=^Host\s)", text, flags=re.MULTILINE)
    new_blocks = [b for b in blocks if not re.match(rf"Host\s+{re.escape(name)}\s*$", b.strip().split("\n")[0] if b.strip() else "")]
    if len(new_blocks) == len(blocks):
        return False
    SSH_CONFIG.write_text("".join(new_blocks))
    return True

# ── Connectivity test ─────────────────────────────────────────────────────────

def test_host(host: Host, timeout=5) -> tuple[bool, float]:
    import socket
    start = time.time()
    try:
        sock = socket.create_connection((host.hostname, int(host.port)), timeout=timeout)
        sock.close()
        return True, time.time() - start
    except Exception:
        return False, time.time() - start

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    hosts = parse_ssh_config()
    q = (args.query or "").lower()
    if q:
        hosts = [h for h in hosts if q in h.name.lower() or q in h.hostname.lower() or q in h.user.lower()]

    if not hosts:
        print(c("  No SSH hosts found." if not q else f"  No hosts matching '{q}'.", YLW))
        return

    print(c(f"\n  {'ALIAS':<20}  {'HOST':<28}  {'USER':<14}  {'PORT':>5}  {'PROXY':<14}  KEY", BOLD, CYN))
    print(c("  " + "─" * 90, DIM))

    for h in hosts:
        key = c("🔑", GRN) if h.identity else c("🔓", DIM)
        proxy = c(h.proxy[:14], YLW) if h.proxy else c("─", DIM)
        fwd = c(" +fwd", DIM) if h.forward == "yes" else ""
        print(f"  {c(h.name, BOLD, CYN):<28}  {h.hostname:<28}  {h.user:<14}  {h.port:>5}  {proxy:<22}  {key}{fwd}")

    print(c(f"\n  {len(hosts)} host(s) in {SSH_CONFIG}", DIM))

def cmd_add(args):
    write_host(
        name=args.name,
        hostname=args.hostname,
        user=args.user or os.environ.get("USER", "root"),
        port=str(args.port or 22),
        identity=args.identity or "",
        proxy=args.proxy or "",
        forward="yes" if args.forward else "no",
    )
    print(c(f"  ✓ Host '{args.name}' saved to {SSH_CONFIG}", GRN, BOLD))

def cmd_remove(args):
    if remove_host(args.name):
        print(c(f"  ✓ Removed '{args.name}' from {SSH_CONFIG}", GRN))
    else:
        print(c(f"  ✗ Host '{args.name}' not found.", RED))

def cmd_show(args):
    hosts = parse_ssh_config()
    matches = [h for h in hosts if h.name == args.name]
    if not matches:
        print(c(f"  Host '{args.name}' not found.", RED)); return
    h = matches[0]
    print(c(f"\n  SSH Host: {h.name}", BOLD, CYN))
    print(c("  " + "─" * 40, DIM))
    fields = [
        ("Alias",    h.name),
        ("HostName", h.hostname),
        ("User",     h.user),
        ("Port",     h.port),
        ("Identity", h.identity or "─"),
        ("ProxyJump",h.proxy or "─"),
        ("ForwardAgent", h.forward),
    ]
    for k, v in fields:
        print(f"  {c(k+':', BOLD):<22} {v}")
    if h.extra:
        for k, v in h.extra.items():
            print(f"  {c(k+':', DIM):<22} {v}")
    print()
    connect_cmd = f"ssh {h.name}"
    print(c(f"  Connect: ", DIM) + c(connect_cmd, BOLD))

def cmd_test(args):
    hosts = parse_ssh_config()
    targets = [h for h in hosts if not args.name or h.name in args.name]
    if not targets:
        print(c("  No hosts to test.", YLW)); return

    print(c(f"\n  luossh test — checking {len(targets)} host(s)", BOLD, CYN))
    print(c("  " + "─" * 50, DIM))

    ok = fail = 0
    for h in targets:
        reachable, elapsed = test_host(h, timeout=args.timeout or 5)
        ms = elapsed * 1000
        if reachable:
            ok += 1
            status = c(f"  ✓ OPEN   {ms:6.0f}ms", GRN, BOLD)
        else:
            fail += 1
            status = c(f"  ✗ CLOSED {ms:6.0f}ms", RED, BOLD)
        print(f"{status}  {c(h.name, BOLD):<20}  {h.user}@{h.hostname}:{h.port}")

    print()
    print(f"  {c(f'{ok} reachable', GRN)}  {c(f'{fail} unreachable', RED if fail else DIM)}")

def cmd_connect(args):
    hosts = parse_ssh_config()
    matches = [h for h in hosts if h.name == args.name]
    if matches:
        h = matches[0]
    else:
        # treat as direct host
        parts = args.name.split("@")
        user = parts[0] if len(parts) == 2 else os.environ.get("USER","root")
        hostname = parts[-1]
        h = Host(args.name, {"HostName": hostname, "User": user})

    ssh_args = ["ssh"]
    if args.port:
        ssh_args += ["-p", str(args.port)]
    if args.cmd:
        ssh_args += [h.name, "--", *shlex.split(args.cmd)]
    else:
        ssh_args.append(h.name)

    print(c(f"  Connecting to {h.user}@{h.hostname}:{h.port} …", DIM))
    os.execvp("ssh", ssh_args)

def cmd_copy(args):
    """Copy SSH public key to remote host."""
    hosts = parse_ssh_config()
    matches = [h for h in hosts if h.name == args.name]
    h = matches[0] if matches else Host(args.name, {"HostName": args.name})

    key_path = args.key or str(Path.home() / ".ssh" / "id_rsa.pub")
    if not Path(key_path).exists():
        print(c(f"  Key not found: {key_path}", RED))
        print(c("  Generate one with: ssh-keygen -t ed25519", DIM))
        sys.exit(1)

    key = Path(key_path).read_text().strip()
    remote_cmd = f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "{key}" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
    ssh_cmd = ["ssh", "-p", h.port, f"{h.user}@{h.hostname}", remote_cmd]
    print(c(f"  Copying {key_path} to {h.user}@{h.hostname}...", DIM))
    result = subprocess.run(ssh_cmd)
    if result.returncode == 0:
        print(c("  ✓ Key copied successfully. You can now login without password.", GRN, BOLD))
    else:
        print(c("  ✗ Failed to copy key.", RED))

# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="luossh",
        description=c("luossh", BOLD, CYN) + " — SSH Config Manager & Session Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luossh list                          List all SSH hosts
  luossh list webserver                Search hosts by name/hostname
  luossh add myserver -H 1.2.3.4 -u ubuntu -p 2222 -i ~/.ssh/id_ed25519
  luossh show myserver                 Detailed view
  luossh remove myserver               Remove from config
  luossh test                          Test all hosts
  luossh test myserver staging         Test specific hosts
  luossh connect myserver              Launch SSH session
  luossh connect myserver -c "uptime"  Run remote command
  luossh copy-key myserver             Copy your public key
""",
    )
    sub = ap.add_subparsers(dest="cmd")

    # list
    p = sub.add_parser("list", help="List SSH hosts")
    p.add_argument("query", nargs="?", help="Filter string")

    # add
    p = sub.add_parser("add", help="Add a host to ~/.ssh/config")
    p.add_argument("name", help="Alias (Host entry name)")
    p.add_argument("-H", "--hostname", required=True, help="Hostname or IP")
    p.add_argument("-u", "--user", help="Username")
    p.add_argument("-p", "--port", type=int, default=22)
    p.add_argument("-i", "--identity", help="Path to private key")
    p.add_argument("--proxy", help="ProxyJump host")
    p.add_argument("--forward", action="store_true", help="ForwardAgent yes")

    # remove
    p = sub.add_parser("remove", aliases=["rm"], help="Remove a host")
    p.add_argument("name")

    # show
    p = sub.add_parser("show", help="Show host details")
    p.add_argument("name")

    # test
    p = sub.add_parser("test", help="Test TCP connectivity to hosts")
    p.add_argument("name", nargs="*", help="Host aliases (default: all)")
    p.add_argument("--timeout", type=float, default=5)

    # connect
    p = sub.add_parser("connect", aliases=["ssh"], help="Connect to a host")
    p.add_argument("name")
    p.add_argument("-p", "--port", type=int)
    p.add_argument("-c", "--cmd", help="Remote command to run")

    # copy-key
    p = sub.add_parser("copy-key", help="Copy SSH public key to remote host")
    p.add_argument("name")
    p.add_argument("--key", help="Path to public key (default: ~/.ssh/id_rsa.pub)")

    args = ap.parse_args()
    dispatch = {
        "list": cmd_list, "add": cmd_add, "remove": cmd_remove, "rm": cmd_remove,
        "show": cmd_show, "test": cmd_test, "connect": cmd_connect,
        "ssh": cmd_connect, "copy-key": cmd_copy,
    }

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
