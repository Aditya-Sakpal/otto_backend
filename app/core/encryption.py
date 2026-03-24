"""
API key encryption utilities.
Handles encryption and decryption of API keys using AES-256.
"""
import base64
import functools
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@functools.lru_cache(maxsize=1)
def get_encryption_key() -> bytes:
    """
    Get encryption key from environment or generate a default.

    For production, ENCRYPTION_KEY should be a 32-byte (256-bit) key encoded in base64.
    For development, a default key is used (DO NOT use in production).

    Returns:
        32-byte encryption key
    """
    encryption_key_env = settings.ENCRYPTION_KEY

    if encryption_key_env:
        try:
            # Try to decode as base64 first
            try:
                key_bytes = base64.b64decode(encryption_key_env)
                if len(key_bytes) == 32:
                    return key_bytes
            except Exception:
                pass

            # If base64 decode failed or wrong length, derive key from the string
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            # Use PBKDF2 to derive a proper 32-byte key from whatever string was provided
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'otto-encryption-salt',  # Static salt for deterministic key derivation
                iterations=100000,
                backend=default_backend()
            )
            key_bytes = kdf.derive(encryption_key_env.encode('utf-8'))
            return key_bytes

        except Exception as e:
            logger.warning(f"Error parsing ENCRYPTION_KEY: {e}. Using default key (NOT FOR PRODUCTION)")

    # Default key for development (32 bytes = 256 bits)
    # WARNING: This is insecure for production use
    default_key = b"otto-default-encryption-key-256!!"  # Exactly 32 bytes
    logger.warning("Using default encryption key. Set ENCRYPTION_KEY environment variable for production.")
    return default_key


def encrypt_api_key(plain_key: str) -> str:
    """
    Encrypt an API key using AES-256 in CBC mode.

    Args:
        plain_key: Plain text API key

    Returns:
        Base64-encoded encrypted key with IV prefix
    """
    try:
        key = get_encryption_key()

        # Validate key length
        if len(key) != 32:
            raise ValueError(f"Encryption key must be exactly 32 bytes, got {len(key)} bytes")

        backend = default_backend()

        # Generate random IV (16 bytes for AES)
        iv = os.urandom(16)

        # Create cipher
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
        encryptor = cipher.encryptor()

        # Pad the plaintext to block size (16 bytes for AES)
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(plain_key.encode('utf-8'))
        padded_data += padder.finalize()

        # Encrypt
        ciphertext = encryptor.update(padded_data) + encryptor.finalize()

        # Prepend IV to ciphertext and encode as base64
        encrypted_with_iv = iv + ciphertext
        encrypted_b64 = base64.b64encode(encrypted_with_iv).decode('utf-8')

        return encrypted_b64

    except Exception as e:
        logger.error(f"Error encrypting API key: {e}")
        raise ValueError(f"Failed to encrypt API key: {e}")


def decrypt_api_key(encrypted_key: str) -> str:
    """
    Decrypt an API key that was encrypted with encrypt_api_key.

    Args:
        encrypted_key: Base64-encoded encrypted key with IV prefix

    Returns:
        Plain text API key
    """
    try:
        key = get_encryption_key()

        # Validate key length
        if len(key) != 32:
            raise ValueError(f"Encryption key must be exactly 32 bytes, got {len(key)} bytes")

        backend = default_backend()

        # Decode base64
        encrypted_with_iv = base64.b64decode(encrypted_key)

        # Extract IV (first 16 bytes) and ciphertext
        iv = encrypted_with_iv[:16]
        ciphertext = encrypted_with_iv[16:]

        # Create cipher
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=backend)
        decryptor = cipher.decryptor()

        # Decrypt
        padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        # Unpad
        unpadder = padding.PKCS7(128).unpadder()
        plaintext = unpadder.update(padded_plaintext)
        plaintext += unpadder.finalize()

        return plaintext.decode('utf-8')

    except Exception as e:
        logger.error(f"Error decrypting API key: {e}")
        raise ValueError(f"Failed to decrypt API key: {e}")
