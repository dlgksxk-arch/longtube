"""/api/v2/keys — 암호화된 API 키 금고(api_key_vault) CRUD + 테스트 핑.

기획 문서 §15.1 (3영역 카드) 대응:
    - 상태: last_ping_status / last_ping_at
    - 키: encrypt 해서 ciphertext 에 저장. 조회 시 마스킹으로만 반환.
    - 잔액: balance_usd 텍스트. "충전했어요" 모달 수기 입력만 허용.

본 라우터는 기존 ``/api/api-keys`` 와 **병렬**이다. 기존 .env 파일은
건드리지 않는다. v2 UI 만 이 라우터를 바라본다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.api_key_vault import ApiKeyVault
from app.security.crypto import encrypt, decrypt, is_ciphertext


router = APIRouter()


# --- 스키마 ----------------------------------------------------------------


class VaultItemOut(BaseModel):
    provider: str
    env_var: str
    has_key: bool
    masked_key: str
    last_ping_status: str
    last_ping_at: Optional[datetime] = None
    balance_usd: Optional[str] = None
    enabled: bool


class KeyUpdateBody(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=0, max_length=4096)


class BalanceUpdateBody(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    balance_usd: str = Field(min_length=0, max_length=32)


# --- 헬퍼 ------------------------------------------------------------------


def _mask(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) > 12:
        return plain[:6] + "..." + plain[-4:]
    return "***"


def _to_out(row: ApiKeyVault) -> VaultItemOut:
    plain = ""
    if row.ciphertext:
        try:
            plain = decrypt(row.ciphertext)
        except Exception:
            plain = ""
    return VaultItemOut(
        provider=row.provider,
        env_var=row.env_var,
        has_key=bool(plain),
        masked_key=_mask(plain),
        last_ping_status=row.last_ping_status or "unknown",
        last_ping_at=row.last_ping_at,
        balance_usd=row.balance_usd,
        enabled=bool(row.enabled),
    )


# --- 엔드포인트 ------------------------------------------------------------


@router.get("/", response_model=list[VaultItemOut])
def list_keys(db: Session = Depends(get_db)):
    rows = db.query(ApiKeyVault).order_by(ApiKeyVault.provider.asc()).all()
    return [_to_out(r) for r in rows]


@router.post("/save", response_model=VaultItemOut)
def save_key(body: KeyUpdateBody, db: Session = Depends(get_db)):
    row = (
        db.query(ApiKeyVault)
        .filter(ApiKeyVault.provider == body.provider)
        .first()
    )
    if row is None:
        raise HTTPException(
            404, f"provider '{body.provider}' not registered in vault"
        )
    row.ciphertext = encrypt(body.api_key)
    row.enabled = bool(body.api_key)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/balance", response_model=VaultItemOut)
def update_balance(body: BalanceUpdateBody, db: Session = Depends(get_db)):
    row = (
        db.query(ApiKeyVault)
        .filter(ApiKeyVault.provider == body.provider)
        .first()
    )
    if row is None:
        raise HTTPException(404, f"provider '{body.provider}' not registered")
    row.balance_usd = body.balance_usd
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.post("/ping/{provider}")
def ping_key(provider: str, db: Session = Depends(get_db)):
    """테스트 핑 (스켈레톤). v2.3.0 에서 프로바이더별 실제 호출로 확장."""
    row = (
        db.query(ApiKeyVault).filter(ApiKeyVault.provider == provider).first()
    )
    if row is None:
        raise HTTPException(404, f"provider '{provider}' not registered")
    # 현재는 "키가 존재하면 ok" 수준. 각 프로바이더 호출은 후속 릴리즈.
    try:
        plain = decrypt(row.ciphertext) if row.ciphertext else ""
    except Exception:
        plain = ""
    row.last_ping_status = "ok" if plain else "fail"
    row.last_ping_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return {
        "provider": row.provider,
        "status": row.last_ping_status,
        "at": row.last_ping_at.isoformat() if row.last_ping_at else None,
    }


@router.get("/_introspect_ciphertext_format")
def introspect_ciphertext_format(db: Session = Depends(get_db)):
    """개발용: 저장된 ciphertext 가 올바른 버전 포맷인지 간이 점검."""
    rows = db.query(ApiKeyVault).all()
    total = len(rows)
    valid = sum(1 for r in rows if is_ciphertext(r.ciphertext or ""))
    empty = sum(1 for r in rows if not (r.ciphertext or ""))
    return {"total": total, "valid_format": valid, "empty": empty}
