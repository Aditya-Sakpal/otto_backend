#!/usr/bin/env python3
"""
Standalone script to encrypt an API key using the same AES-256 logic as app.core.encryption.

Usage:
  python scripts/encrypt_api_key.py "your-plain-api-key"
  echo "your-plain-api-key" | python scripts/encrypt_api_key.py

Optional: set ENCRYPTION_KEY in the environment (or in .env when run from project root).
  - Base64-encoded 32-byte key, or
  - Any string (will be derived to 32 bytes via PBKDF2).

If ENCRYPTION_KEY is not set, uses the same default dev key as the app (not for production).
"""
import base64
import os
import sys

# Optional: load .env when run from project root
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend


# 32-byte default (app/core/encryption.py uses same string but it's 33 bytes there; we use 32 so AES works)
DEFAULT_KEY = b"otto-default-encryption-key-256!!"[:32]


def get_encryption_key() -> bytes:
    raw = os.environ.get("ENCRYPTION_KEY", "").strip()
    if not raw:
        print("Warning: ENCRYPTION_KEY not set. Using default key (not for production).", file=sys.stderr)
        return DEFAULT_KEY

    try:
        key_bytes = base64.b64decode(raw)
        if len(key_bytes) == 32:
            return key_bytes
    except Exception:
        pass

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'otto-encryption-salt',
        iterations=100000,
        backend=default_backend(),
    )
    return kdf.derive(raw.encode("utf-8"))


def encrypt_api_key(plain_key: str) -> str:
    key = get_encryption_key()
    if len(key) != 32:
        raise ValueError(f"Encryption key must be 32 bytes, got {len(key)}")

    backend = default_backend()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
    encryptor = cipher.encryptor()

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain_key.encode("utf-8")) + padder.finalize()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    return base64.b64encode(iv + ciphertext).decode("utf-8")


def main() -> None:
    if len(sys.argv) > 1:
        plain = sys.argv[1]
    else:
        plain = sys.stdin.read().strip()

    if not plain:
        print("Usage: encrypt_api_key.py <api-key>  or  echo 'api-key' | encrypt_api_key.py", file=sys.stderr)
        sys.exit(1)

    try:
        encrypted = encrypt_api_key(plain)
        print(encrypted)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
