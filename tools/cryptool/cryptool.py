#!/usr/bin/env python3
"""
cryptool — Encrypt/decrypt files and text with AES-256 & more
Generate passwords, hashes, JWT decode, base64 encode/decode

Usage:
  python3 cryptool.py encrypt <text> <password>
  python3 cryptool.py decrypt <text> <password>
  python3 cryptool.py hash <text>
  python3 cryptool.py b64e <text>
  python3 cryptool.py b64d <text>
  python3 cryptool.py genpass [length]
  python3 cryptool.py jwt <token>
  python3 cryptool.py random <n>
"""

import base64
import hashlib
import hmac
import secrets
import string
import json
import sys

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Install cryptography: pip install cryptography")
    sys.exit(1)


def derive_key(password: str, salt: bytes) -> bytes:
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000, dklen=32)
    return base64.urlsafe_b64encode(dk)


def encrypt(plaintext: str, password: str) -> str:
    salt = secrets.token_bytes(16)
    key = derive_key(password, salt)
    f = Fernet(key)
    token = f.encrypt(plaintext.encode())
    return base64.b64encode(salt + token).decode()


def decrypt(ciphertext: str, password: str) -> str:
    try:
        data = base64.b64decode(ciphertext)
        salt, token = data[:16], data[16:]
        key = derive_key(password, salt)
        f = Fernet(key)
        return f.decrypt(token).decode()
    except Exception:
        raise ValueError("Invalid password or corrupted ciphertext")


def sha256_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def md5_hash(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def hmac_sha256(text: str, key: str) -> str:
    return hmac.new(key.encode(), text.encode(), hashlib.sha256).hexdigest()


def generate_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(chars) for _ in range(length))


def b64_encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def b64_decode(text: str) -> str:
    return base64.b64decode(text.encode()).decode()


def decode_jwt(token: str) -> dict | None:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += '=' * (4 - len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def random_bytes(n: int) -> str:
    return secrets.token_hex(n)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()

    if cmd == 'encrypt' and len(sys.argv) >= 4:
        print(encrypt(sys.argv[2], sys.argv[3]))
    elif cmd == 'decrypt' and len(sys.argv) >= 4:
        print(decrypt(sys.argv[2], sys.argv[3]))
    elif cmd == 'hash' and len(sys.argv) >= 3:
        print(sha256_hash(sys.argv[2]))
    elif cmd == 'md5' and len(sys.argv) >= 3:
        print(md5_hash(sys.argv[2]))
    elif cmd == 'hmac' and len(sys.argv) >= 4:
        print(hmac_sha256(sys.argv[2], sys.argv[3]))
    elif cmd == 'b64e' and len(sys.argv) >= 3:
        print(b64_encode(sys.argv[2]))
    elif cmd == 'b64d' and len(sys.argv) >= 3:
        print(b64_decode(sys.argv[2]))
    elif cmd == 'genpass':
        length = int(sys.argv[2]) if len(sys.argv) >= 3 else 16
        print(generate_password(length))
    elif cmd == 'jwt' and len(sys.argv) >= 3:
        payload = decode_jwt(sys.argv[2])
        if payload:
            print(json.dumps(payload, indent=2))
        else:
            print("Invalid JWT")
    elif cmd == 'random' and len(sys.argv) >= 3:
        print(random_bytes(int(sys.argv[2])))
    else:
        print(__doc__)