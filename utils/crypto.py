"""
utils/crypto.py
---------------
AES-256-GCM encryption / decryption for the Python bot side.
Must use the SAME ENCRYPTION_KEY as the Node.js Vercel backend
so the dashboard can decrypt data written by the bot.

Set ENCRYPTION_KEY in your .env as a 64-char hex string:
  python -c "import secrets; print(secrets.token_hex(32))"
"""
import os
import base64
import hmac
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_IV_LENGTH = 12   # 96-bit nonce — GCM recommended


def _get_key() -> bytes:
    hex_key = os.getenv("ENCRYPTION_KEY", "")
    if len(hex_key) != 64:
        raise RuntimeError(
            "ENCRYPTION_KEY must be a 64-character hex string. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return bytes.fromhex(hex_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 string with AES-256-GCM.
    Returns "<iv_b64>:<tag_b64>:<ciphertext_b64>" — identical format to the Node.js lib.
    Note: cryptography library returns ciphertext+tag concatenated; we split the last 16 bytes as the tag.
    """
    key  = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(_IV_LENGTH)
    # AESGCM.encrypt returns ciphertext || tag (16 bytes)
    ct_with_tag = aesgcm.encrypt(nonce, plaintext.encode(), None)
    ct, tag = ct_with_tag[:-16], ct_with_tag[-16:]
    return ":".join([
        base64.b64encode(nonce).decode(),
        base64.b64encode(tag).decode(),
        base64.b64encode(ct).decode(),
    ])


def decrypt(payload: str) -> str:
    """Decrypt a payload produced by encrypt() or the Node.js counterpart."""
    parts = payload.split(":")
    if len(parts) != 3:
        raise ValueError("Invalid encrypted payload.")
    iv_b64, tag_b64, ct_b64 = parts
    key   = _get_key()
    nonce = base64.b64decode(iv_b64)
    tag   = base64.b64decode(tag_b64)
    ct    = base64.b64decode(ct_b64)
    aesgcm = AESGCM(key)
    # cryptography expects ciphertext || tag
    plaintext = aesgcm.decrypt(nonce, ct + tag, None)
    return plaintext.decode()


def hmac_hash(value: str) -> str:
    """HMAC-SHA256 of a value using the encryption key — for indexing without exposing data."""
    return hmac.new(_get_key(), value.encode(), hashlib.sha256).hexdigest()
