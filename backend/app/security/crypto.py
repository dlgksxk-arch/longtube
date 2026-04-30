"""AES-GCM 대칭 암호화 유틸 — v2.1.0 신규.

용도: API 키, 토큰 등 비밀 문자열을 DB 에 안전하게 저장한다.

마스터 키 소스 우선순위:
    1) 환경변수 ``LONGTUBE_KEY_SECRET`` (base64url 인코딩된 32바이트).
    2) 파일 ``{BASE_DIR}/data/.key`` — 없으면 앱이 한 번 생성하고
       chmod 0600 으로 고정(가능한 플랫폼 한정).

암호문 포맷 (문자열 1줄):
    f"{VERSION}:{base64url(nonce)}:{base64url(ciphertext_with_tag)}"
    예) "v1:abc...:xyz..."

VERSION 필드를 둔 이유: 추후 키 로테이션/알고리즘 교체 시 하위 호환
디코딩이 가능하도록 하기 위함.

보안 메모:
    - AES-GCM 은 authenticated encryption. ciphertext 뒤 16바이트가
      tag 이며 ``AESGCM.decrypt`` 가 자동 검증한다(변조 탐지).
    - nonce 는 호출마다 os.urandom(12) 로 **반드시** 새로 생성.
    - 동일 평문이라도 nonce 가 달라 다른 ciphertext 가 나온다(패턴 노출 방지).
"""
from __future__ import annotations

import base64
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import BASE_DIR


_KEY_FILE_PATH = BASE_DIR / "data" / ".key"
_KEY_ENV_NAME = "LONGTUBE_KEY_SECRET"
_VERSION = "v1"

# 모듈 레벨 캐시. 매 호출마다 파일 I/O 하지 않기 위함.
_cached_key: Optional[bytes] = None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _load_from_env() -> Optional[bytes]:
    raw = os.environ.get(_KEY_ENV_NAME, "").strip()
    if not raw:
        return None
    try:
        key = _b64d(raw)
    except Exception:
        return None
    if len(key) != 32:
        return None
    return key


def _load_from_file() -> Optional[bytes]:
    if not _KEY_FILE_PATH.exists():
        return None
    try:
        text = _KEY_FILE_PATH.read_text(encoding="utf-8").strip()
        key = _b64d(text)
    except Exception:
        return None
    if len(key) != 32:
        return None
    return key


def _write_new_key_file(key: bytes) -> None:
    _KEY_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _KEY_FILE_PATH.write_text(_b64e(key), encoding="utf-8")
    # POSIX 에서만 chmod 유의미. Windows 는 무시해도 데이터는 안전.
    try:
        os.chmod(_KEY_FILE_PATH, 0o600)
    except Exception:
        pass


def get_master_key() -> bytes:
    """32바이트 AES-256 키 반환. 없으면 자동 생성."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    key = _load_from_env()
    if key is None:
        key = _load_from_file()
    if key is None:
        key = secrets.token_bytes(32)
        _write_new_key_file(key)
    _cached_key = key
    return key


def encrypt(plaintext: str) -> str:
    """평문 문자열 → ``{VERSION}:{nonce}:{ct}`` 형식 암호문."""
    if plaintext is None:
        plaintext = ""
    aesgcm = AESGCM(get_master_key())
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return f"{_VERSION}:{_b64e(nonce)}:{_b64e(ct)}"


def decrypt(token: str) -> str:
    """암호문 → 원본 평문. 포맷/버전이 맞지 않으면 ValueError."""
    if not token:
        return ""
    parts = token.split(":", 2)
    if len(parts) != 3:
        raise ValueError("ciphertext format invalid")
    version, nonce_b64, ct_b64 = parts
    if version != _VERSION:
        raise ValueError(f"unsupported cipher version: {version}")
    nonce = _b64d(nonce_b64)
    ct = _b64d(ct_b64)
    aesgcm = AESGCM(get_master_key())
    pt = aesgcm.decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def is_ciphertext(token: str) -> bool:
    """문자열이 본 모듈 형식의 암호문인지 판정."""
    if not token or not isinstance(token, str):
        return False
    return token.startswith(f"{_VERSION}:") and token.count(":") == 2
