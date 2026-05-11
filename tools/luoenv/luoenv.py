#!/usr/bin/env python3
"""
luoenv — Environment & Secrets Manager
by luokai | MIT License

Manage .env files, compare environments, validate required vars,
export/import, and detect secrets in code — all in one tool.
"""

import os
import sys
import re
import json
import argparse
import hashlib
import base64
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
MGN  = "\033[95m"

def c(*args):
    return "".join(args[1:]) + str(args[0]) + R

# ── .env parsing ──────────────────────────────────────────────────────────────

def parse_env_file(path: Path) -> dict[str, str]:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            env[k] = v
    return env

def write_env_file(path: Path, env: dict[str, str], comments: dict[str, str] = None):
    lines = []
    comments = comments or {}
    for k, v in env.items():
        if k in comments:
            lines.append(f"# {comments[k]}")
        # quote values with spaces or special chars
        if " " in v or "$" in v or "#" in v:
            v = f'"{v}"'
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n")

# ── Secret detection ──────────────────────────────────────────────────────────

SECRET_PATTERNS = [
    (r"(?i)(password|passwd|pwd)\s*=\s*\S+",              "Password"),
    (r"(?i)(secret|token|api[_-]?key)\s*=\s*['\"]?\S+",  "Secret/Token"),
    (r"(?i)(aws_secret|aws_access_key)\s*=\s*\S+",       "AWS key"),
    (r"(?i)(private[_-]?key)\s*=\s*\S+",                 "Private key"),
    (r"-----BEGIN\s+\w+\s+PRIVATE KEY-----",               "PEM private key"),
    (r"(?i)(ghp_|gho_|github_token)\s*[\w]{30,}",         "GitHub token"),
    (r"(?i)bearer\s+[a-z0-9._\-]{20,}",                   "Bearer token"),
    (r"(?i)(connection_string|db_url|database_url)\s*=\s*\S+", "Database URL"),
    (r"[a-z0-9]{32,}[A-Z][a-z0-9]{10,}",                 "Possible secret (mixed case long)"),
]

def mask_value(v: str, show: int = 4) -> str:
    if len(v) <= show * 2:
        return "*" * len(v)
    return v[:show] + "*" * (len(v) - show * 2) + v[-show:]

def is_secret_key(key: str) -> bool:
    patterns = ["password","passwd","pwd","secret","token","key","credential",
                "auth","private","api","access","cert","signature","salt","hash"]
    k = key.lower()
    return any(p in k for p in patterns)

# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args):
    env_file = Path(args.file or ".env")
    env = parse_env_file(env_file)

    if not env:
        print(c(f"  No vars found in {env_file}", YLW)); return

    q = (args.query or "").lower()
    if q:
        env = {k: v for k, v in env.items() if q in k.lower() or q in v.lower()}

    print(c(f"\n  {env_file} — {len(env)} variable(s)", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    for k, v in sorted(env.items()):
        masked = args.secrets or not is_secret_key(k)
        display = v if masked else mask_value(v)
        k_colour = c(k, RED if is_secret_key(k) else YLW, BOLD)
        v_colour = c(display, DIM if not masked else GRN)
        print(f"  {k_colour:<40} = {v_colour}")

    if not args.secrets:
        print(c(f"\n  🔒 Secret values masked. Use --secrets to reveal.", DIM))

def cmd_get(args):
    env = parse_env_file(Path(args.file or ".env"))
    for key in args.keys:
        v = env.get(key)
        if v is None:
            print(c(f"  ✗ {key} not set", RED))
        else:
            if args.raw:
                print(v)
            else:
                print(f"  {c(key, YLW, BOLD)} = {c(v, GRN)}")

def cmd_set(args):
    env_file = Path(args.file or ".env")
    env = parse_env_file(env_file)

    for pair in args.pairs:
        if "=" not in pair:
            print(c(f"  ✗ Invalid pair (use KEY=VALUE): {pair}", RED)); continue
        k, _, v = pair.partition("=")
        old = env.get(k)
        env[k] = v
        if old is None:
            print(c(f"  ✓ Added   {k}={mask_value(v) if is_secret_key(k) else v}", GRN))
        else:
            print(c(f"  ✓ Updated {k}", YLW))

    write_env_file(env_file, env)

def cmd_unset(args):
    env_file = Path(args.file or ".env")
    env = parse_env_file(env_file)
    for key in args.keys:
        if key in env:
            del env[key]
            print(c(f"  ✓ Removed {key}", GRN))
        else:
            print(c(f"  ✗ {key} not found", YLW))
    write_env_file(env_file, env)

def cmd_diff(args):
    a = parse_env_file(Path(args.a))
    b = parse_env_file(Path(args.b))
    all_keys = sorted(set(a) | set(b))

    print(c(f"\n  diff: {args.a}  vs  {args.b}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    diffs = 0
    for key in all_keys:
        va = a.get(key)
        vb = b.get(key)
        if va == vb:
            continue
        diffs += 1
        if va is None:
            print(f"  {c('+', GRN, BOLD)} {c(key, GRN)}: {c(vb[:60], GRN)}")
        elif vb is None:
            print(f"  {c('─', RED, BOLD)} {c(key, RED)}: {c(va[:60], RED)}")
        else:
            mva = mask_value(va) if is_secret_key(key) else va[:40]
            mvb = mask_value(vb) if is_secret_key(key) else vb[:40]
            print(f"  {c('~', YLW, BOLD)} {c(key, YLW)}: {c(mva, RED)} → {c(mvb, GRN)}")

    if diffs == 0:
        print(c("  Both files are identical.", GRN, BOLD))
    else:
        print(c(f"\n  {diffs} differences", YLW, BOLD))

def cmd_validate(args):
    env = parse_env_file(Path(args.file or ".env"))
    current_env = {**os.environ, **env}

    required_file = Path(args.required or ".env.example")
    if not required_file.exists():
        print(c(f"  Reference file not found: {required_file}", YLW))
        print(c("  Pass keys directly: luocron validate --keys KEY1 KEY2", DIM))
        required_keys = args.keys or []
    else:
        example = parse_env_file(required_file)
        required_keys = list(example.keys())
        if args.keys:
            required_keys = list(set(required_keys) | set(args.keys))

    if not required_keys:
        print(c("  No keys to validate.", YLW)); return

    print(c(f"\n  Validating {len(required_keys)} required variable(s)", BOLD, CYN))
    print(c("  " + "─" * 50, DIM))

    ok = missing = empty = 0
    for key in sorted(required_keys):
        v = current_env.get(key)
        if v is None:
            missing += 1
            print(f"  {c('✗ MISSING', RED, BOLD):25}  {c(key, RED)}")
        elif v.strip() == "" or v in ("CHANGEME", "your_key_here", "TODO", "xxx"):
            empty += 1
            print(f"  {c('⚠ EMPTY/PLACEHOLDER', YLW, BOLD):25}  {c(key, YLW)}")
        else:
            ok += 1
            display = mask_value(v) if is_secret_key(key) else (v[:20] + "..." if len(v) > 20 else v)
            print(f"  {c('✓ OK', GRN, BOLD):25}  {c(key, GRN):<30}  {c(display, DIM)}")

    print()
    status = GRN if (missing + empty) == 0 else RED
    print(c(f"  {ok} OK  {missing} missing  {empty} empty/placeholder", status, BOLD))
    sys.exit(0 if (missing + empty) == 0 else 1)

def cmd_scan(args):
    root = Path(args.path or ".")
    exts = {".py",".js",".ts",".go",".rb",".sh",".yaml",".yml",".json",".toml",".tf",".env"}
    ignores = {".git","node_modules","__pycache__",".venv","dist","build"}

    print(c(f"\n  luoenv scan — searching for secrets in {root}", BOLD, CYN))
    print(c("  " + "─" * 60, DIM))

    findings = []
    for p in root.rglob("*"):
        if any(ig in p.parts for ig in ignores):
            continue
        if p.suffix not in exts and not p.name.startswith(".env"):
            continue
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                for pattern, label in SECRET_PATTERNS:
                    if re.search(pattern, line):
                        findings.append((p, i, label, line.strip()[:80]))
                        break
        except Exception:
            pass

    if not findings:
        print(c("  ✓ No obvious secrets detected.", GRN, BOLD))
        return

    for path, lineno, label, snippet in findings:
        rel = path.relative_to(root) if root != Path(".") else path
        print(f"  {c(label, RED, BOLD):<30}  {c(rel, YLW)}:{c(lineno, DIM)}")
        print(f"    {c(snippet, DIM)}")
        print()

    print(c(f"  ⚠ {len(findings)} potential secret(s) found. Review before committing!", YLW, BOLD))

def cmd_export(args):
    env = parse_env_file(Path(args.file or ".env"))
    fmt = args.format or "shell"

    if fmt == "shell":
        for k, v in env.items():
            print(f'export {k}="{v}"')
    elif fmt == "json":
        print(json.dumps(env, indent=2))
    elif fmt == "docker":
        for k, v in env.items():
            print(f"--env {k}={v}", end=" ")
        print()
    elif fmt == "k8s":
        print("env:")
        for k, v in env.items():
            print(f"  - name: {k}")
            print(f"    value: \"{v}\"")

def cmd_template(args):
    env_file = Path(args.file or ".env")
    out_file = Path(args.output or ".env.example")
    env = parse_env_file(env_file)

    lines = [f"# Auto-generated from {env_file} by luoenv", ""]
    for k, v in env.items():
        if is_secret_key(k):
            lines.append(f"{k}=CHANGEME")
        else:
            lines.append(f"{k}={v}")

    out_file.write_text("\n".join(lines) + "\n")
    print(c(f"  ✓ Template saved to {out_file} ({len(env)} vars)", GRN, BOLD))

# ── Entry ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        prog="luoenv",
        description=c("luoenv", BOLD, CYN) + " — Environment & Secrets Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  luoenv list                          List all vars in .env
  luoenv list --file .env.prod         List from specific file
  luoenv list --secrets                Reveal secret values
  luoenv get DATABASE_URL              Get a variable value
  luoenv set API_KEY=abc123            Set a variable
  luoenv set HOST=localhost PORT=5432  Set multiple vars
  luoenv unset OLD_KEY                 Remove a variable
  luoenv diff .env .env.prod           Compare two env files
  luoenv validate                      Check required vars vs .env.example
  luoenv validate --keys KEY1 KEY2     Check specific keys
  luoenv scan                          Scan code for hardcoded secrets
  luoenv scan /path/to/project         Scan a specific directory
  luoenv export                        Export as shell export statements
  luoenv export --format json          Export as JSON
  luoenv export --format docker        Export as Docker --env flags
  luoenv export --format k8s           Export as Kubernetes env block
  luoenv template                      Create .env.example from .env
""",
    )
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="List environment variables")
    p.add_argument("--file", "-f", help=".env file path")
    p.add_argument("--secrets", "-s", action="store_true", help="Show secret values unmasked")
    p.add_argument("query", nargs="?", help="Filter by key or value")

    p = sub.add_parser("get", help="Get variable value(s)")
    p.add_argument("keys", nargs="+")
    p.add_argument("--file", "-f")
    p.add_argument("--raw", action="store_true", help="Print raw value only")

    p = sub.add_parser("set", help="Set variable(s)")
    p.add_argument("pairs", nargs="+", metavar="KEY=VALUE")
    p.add_argument("--file", "-f")

    p = sub.add_parser("unset", help="Remove variable(s)")
    p.add_argument("keys", nargs="+")
    p.add_argument("--file", "-f")

    p = sub.add_parser("diff", help="Compare two .env files")
    p.add_argument("a")
    p.add_argument("b")

    p = sub.add_parser("validate", help="Validate required variables are set")
    p.add_argument("--file", "-f")
    p.add_argument("--required", help="Reference .env.example file")
    p.add_argument("--keys", nargs="+", help="Required keys to check")

    p = sub.add_parser("scan", help="Scan code for hardcoded secrets")
    p.add_argument("path", nargs="?", default=".")

    p = sub.add_parser("export", help="Export .env in different formats")
    p.add_argument("--file", "-f")
    p.add_argument("--format", choices=["shell","json","docker","k8s"], default="shell")

    p = sub.add_parser("template", help="Generate .env.example from .env")
    p.add_argument("--file", "-f")
    p.add_argument("--output", "-o")

    args = ap.parse_args()
    dispatch = {
        "list": cmd_list, "get": cmd_get, "set": cmd_set, "unset": cmd_unset,
        "diff": cmd_diff, "validate": cmd_validate, "scan": cmd_scan,
        "export": cmd_export, "template": cmd_template,
    }
    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        ap.print_help()

if __name__ == "__main__":
    main()
