# cryptool — Encryption & Security Toolkit

AES-256 encryption/decryption, hash generation, JWT decoding, password generation, and more — all in pure Python.

## Install

```bash
pip install cryptography
```

## Features

- **encrypt/decrypt** — AES-256-CFB encryption with PBKDF2 key derivation
- **hash** — SHA-256 hash
- **md5** — MD5 hash
- **hmac** — HMAC-SHA256
- **b64e/b64d** — Base64 encode/decode
- **genpass** — Generate strong random password
- **jwt** — Decode JWT payload (no signature verify)
- **random** — Generate random hex bytes

## Usage

```bash
# Encrypt / Decrypt
python3 cryptool.py encrypt "Hello World" "mypassword"
python3 cryptool.py decrypt "<token>" "mypassword"

# Hash
python3 cryptool.py hash "Hello World"

# Password generator
python3 cryptool.py genpass 24

# JWT decode
python3 cryptool.py jwt "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

## License

MIT — luokai