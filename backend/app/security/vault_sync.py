"""v2.1.0 부팅 동기화 — .env 에 있는 API 키들을 api_key_vault 테이블에
암호화된 형태로 1회 등록한다.

원칙:
    - .env 파일은 **건드리지 않는다**. 읽기만.
    - DB 테이블에 이미 같은 provider 행이 있으면 덮어쓰지 않는다.
    - 실패는 앱 기동을 막지 않는다 (예외 삼키고 경고만 출력).

실행 시점: main.py 의 startup 이벤트에서 init_db() 직후 호출.
"""
from __future__ import annotations

import os
from typing import Iterable

from app.models.database import SessionLocal
from app.models.api_key_vault import ApiKeyVault
from app.security.crypto import encrypt


# (provider, env_var) 쌍. 기존 app/routers/api_keys.py 의
# PROVIDER_KEY_MAP 과 정합을 맞춘다.
DEFAULT_VAULT_PROVIDERS: list[tuple[str, str]] = [
    ("Anthropic", "ANTHROPIC_API_KEY"),
    ("OpenAI", "OPENAI_API_KEY"),
    ("ElevenLabs", "ELEVENLABS_API_KEY"),
    ("fal.ai", "FAL_KEY"),
    ("xAI (Grok)", "XAI_API_KEY"),
    ("Kling", "KLING_ACCESS_KEY"),
    ("Replicate", "REPLICATE_API_TOKEN"),
    ("Runway", "RUNWAY_API_KEY"),
    ("Midjourney", "MIDJOURNEY_API_KEY"),
]


def sync_env_into_vault(
    providers: Iterable[tuple[str, str]] = tuple(DEFAULT_VAULT_PROVIDERS),
) -> dict:
    """env → DB 초기 동기화.

    반환값: {"inserted": [..], "skipped": [..], "empty": [..]}
    """
    inserted: list[str] = []
    skipped: list[str] = []
    empty: list[str] = []

    db = SessionLocal()
    try:
        for provider, env_var in providers:
            value = os.environ.get(env_var, "").strip()
            existing = (
                db.query(ApiKeyVault)
                .filter(ApiKeyVault.provider == provider)
                .first()
            )
            if existing is not None:
                skipped.append(provider)
                continue
            if not value:
                # 빈 레코드로 자리만 만들어 두면 UI 에서 즉시 편집 가능.
                row = ApiKeyVault(
                    provider=provider,
                    env_var=env_var,
                    ciphertext="",
                    enabled=False,
                )
                db.add(row)
                empty.append(provider)
                continue
            row = ApiKeyVault(
                provider=provider,
                env_var=env_var,
                ciphertext=encrypt(value),
                enabled=True,
            )
            db.add(row)
            inserted.append(provider)
        db.commit()
    except Exception as e:  # pragma: no cover — 부팅 실패 방지
        db.rollback()
        print(f"[vault] sync_env_into_vault 경고: {e}")
    finally:
        db.close()

    return {"inserted": inserted, "skipped": skipped, "empty": empty}
