"""Password hashing (stdlib-only fallback + optional bcrypt)."""

from __future__ import annotations

import hashlib
import hmac
import secrets


def hash_password(password: str) -> str:
    try:
        import bcrypt

        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")
    except ImportError:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
        ).hex()
        return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("pbkdf2_sha256$"):
        _, salt, digest = password_hash.split("$", 2)
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
        ).hex()
        return hmac.compare_digest(check, digest)
    try:
        import bcrypt

        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ImportError:
        return False
