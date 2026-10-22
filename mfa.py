"""TOTP helpers for RetroRelay account MFA.

The authenticator secret must be encrypted at rest using a Fernet key kept
outside the SQLite database. All successful TOTP counters are single-use.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken


def encryption_key():
    """Fail closed if MFA data cannot be decrypted; never use a fallback key."""
    key = os.getenv("RETRORELAY_MFA_KEY", "").strip()
    if not key:
        raise ValueError("Server administrator must set RETRORELAY_MFA_KEY")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise ValueError("RETRORELAY_MFA_KEY is invalid; use a Fernet key") from exc


def create_secret():
    """160-bit random secret for RFC 6238 / standard authenticator apps."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret):
    return encryption_key().encrypt(secret.encode("ascii")).decode("ascii")


def decrypt_secret(ciphertext):
    try:
        return encryption_key().decrypt(ciphertext.encode("ascii")).decode("ascii")
    except InvalidToken as exc:
        raise ValueError("Stored MFA secret cannot be decrypted (server key changed?)") from exc


def provisioning_uri(username, secret):
    label = quote("RetroRelay:" + username, safe="")
    issuer = quote("RetroRelay", safe="")
    return "otpauth://totp/{0}?secret={1}&issuer={2}&algorithm=SHA1&digits=6&period=30".format(
        label, secret, issuer
    )


def totp_code(secret, counter):
    secret_bytes = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(secret_bytes, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7fffffff) % 1000000
    return "{:06d}".format(number)


def match_counter(secret, code, last_accepted=-1, timestamp=None):
    """Return unused matching 30-second time step or None.

    A successful step must be recorded atomically by the caller before issuing
    a session, so even adjacent-window code replay is rejected.
    """
    if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdecimal():
        return None
    counter = int((time.time() if timestamp is None else timestamp) // 30)
    for step in (counter - 1, counter, counter + 1):
        if step >= 0 and step > last_accepted:
            if hmac.compare_digest(code, totp_code(secret, step)):
                return step
    return None


def new_recovery_codes(count=8):
    # 128-bit unpredictable values; SHA-256 hashes resist offline guessing.
    return [secrets.token_hex(16) for _ in range(count)]


def recovery_hash(code):
    return hashlib.sha256(code.encode("ascii")).hexdigest()
