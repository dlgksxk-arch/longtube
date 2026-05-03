"""Password hashing and signed session-cookie helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from app.config import BASE_DIR


SESSION_COOKIE_NAME = "longtube_session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14
_AUTH_SECRET_FILE = BASE_DIR / "data" / ".auth_secret"
_AUTH_SECRET_ENV = "LONGTUBE_AUTH_SECRET"
_cached_secret: bytes | None = None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def get_auth_secret() -> bytes:
    global _cached_secret
    if _cached_secret is not None:
        return _cached_secret

    raw = os.environ.get(_AUTH_SECRET_ENV, "").strip()
    if raw:
        _cached_secret = raw.encode("utf-8")
        return _cached_secret

    if _AUTH_SECRET_FILE.exists():
        _cached_secret = _AUTH_SECRET_FILE.read_text(encoding="utf-8").strip().encode("utf-8")
        return _cached_secret

    secret = secrets.token_urlsafe(48)
    _AUTH_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AUTH_SECRET_FILE.write_text(secret, encoding="utf-8")
    try:
        os.chmod(_AUTH_SECRET_FILE, 0o600)
    except Exception:
        pass
    _cached_secret = secret.encode("utf-8")
    return _cached_secret


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 240_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${_b64e(salt)}${_b64e(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        alg, rounds_text, salt_text, digest_text = stored_hash.split("$", 3)
        if alg != "pbkdf2_sha256":
            return False
        rounds = int(rounds_text)
        salt = _b64d(salt_text)
        expected = _b64d(digest_text)
    except Exception:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def create_session_token(user_id: str, username: str, role: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + max_age,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(get_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def parse_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, sig_text = token.rsplit(".", 1)
    expected_sig = hmac.new(get_auth_secret(), body.encode("ascii"), hashlib.sha256).digest()
    try:
        supplied_sig = _b64d(sig_text)
    except Exception:
        return None
    if not hmac.compare_digest(expected_sig, supplied_sig):
        return None
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
