"""ApiKeyVault — v2.1.0 신규. API 키를 AES-GCM 으로 암호화해서 DB 에 보관.

기존 v1 흐름(.env 파일에 평문 저장) 은 **그대로 유지**된다. 본 테이블은
v2 UI(/v2/settings/api) 전용으로 **병렬**로 존재한다.

부팅 시 ``sync_env_into_vault()`` 가 .env 에서 발견되는 provider 키를
DB 에 암호화 형태로 동기화한다(이미 존재하면 덮지 않는다). 기존 평문을
빼앗지 않는다 — .env 값도 그대로 둔다.

v3.0 상용화 단계에서 사용자별 키 격리/로테이션이 들어가면 이 테이블을
확장한다.
"""
from __future__ import annotations

from sqlalchemy import Column, Integer, Text, DateTime, Boolean, Index
from sqlalchemy.sql import func

from app.models.database import Base


class ApiKeyVault(Base):
    __tablename__ = "api_key_vault"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 'Anthropic' / 'OpenAI' / 'ElevenLabs' / 'fal.ai' / 'xAI (Grok)' ...
    provider = Column(Text, nullable=False, unique=True)

    # 환경변수 이름(호환용). 예: 'ANTHROPIC_API_KEY'.
    env_var = Column(Text, nullable=False)

    # AES-GCM 암호문 ("v1:nonce:ct").
    ciphertext = Column(Text, nullable=False, default="")

    # 테스트 핑 결과 마지막 상태. 'ok' / 'fail' / 'unknown'.
    last_ping_status = Column(Text, nullable=False, default="unknown")
    last_ping_at = Column(DateTime, nullable=True)

    # 잔액(USD). API 자동 조회 + "충전했어요" 모달 수기 입력 중 최신값.
    balance_usd = Column(Text, nullable=True)  # 소수점 표시 안정성 위해 TEXT.

    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_api_key_vault_provider", "provider", unique=True),
    )
