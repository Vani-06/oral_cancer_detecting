"""Time-based one-time passwords (RFC 6238, SHA-1, 6 digits, 30 s), as used by
Google Authenticator, Microsoft Authenticator and similar apps. Small enough
to keep in-house rather than add a dependency."""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6


def new_secret() -> str:
    """A random 160-bit secret, base32 as authenticator apps expect."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def code_at(secret: str, counter: int) -> str:
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def verify(secret: str, code: str, now: float | None = None, window: int = 1) -> bool:
    """True if `code` matches the current step or one step either side
    (allows for small clock differences)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != DIGITS:
        return False
    counter = int((time.time() if now is None else now) // STEP_SECONDS)
    return any(hmac.compare_digest(code_at(secret, counter + d), code) for d in range(-window, window + 1))


def provisioning_uri(secret: str, account: str, issuer: str = "OralSentinel") -> str:
    return (f"otpauth://totp/{quote(issuer)}:{quote(account)}"
            f"?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP_SECONDS}")
