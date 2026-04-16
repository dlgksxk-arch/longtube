"""수동 입력 API 잔액 관리 (v1.1.55).

공식 잔액 조회 API 가 없는 제공자(Anthropic/OpenAI 일반 키, fal.ai, xAI)를 위해
사용자가 콘솔에서 확인한 잔액을 직접 입력하고, 대시보드 타일에 표시한다.

v1.1.55 확장:
- `initial_amount` + `set_at` 기록 → `remaining = initial_amount - spend_since(set_at)`
  형태의 실시간 감산을 지원.
- `low_threshold` (옵션) → 프론트 대시보드가 이 값 미만이면 경고 배너를 띄움.
- `POST /{provider}/reset-spend` → 해당 시점 이전 지출 레코드를 prune 하고
  `set_at` 을 now 로 초기화. "방금 충전했어요" 버튼용.

저장소: DATA_DIR/api_balances.json
포맷:
  {
    "Anthropic": {
      "amount": 12.34,           # 현재 표시용(= initial_amount 와 같게 저장)
      "initial_amount": 12.34,   # set_at 기준 잔액
      "unit": "USD",
      "set_at": "2026-04-15T...Z",  # 이 시점 이후의 지출을 감산한다
      "low_threshold": 2.0,         # 옵션. 이 값 미만이면 경고.
      "note": "",
      "updated_at": "..."
    },
    ...
  }
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import DATA_DIR
from app.services import spend_ledger

router = APIRouter()

BALANCE_FILE = Path(DATA_DIR) / "api_balances.json"

# 허용 제공자 화이트리스트. Kling/Runway/Midjourney 는 UI 에서 제거됨.
ALLOWED_PROVIDERS = {"Anthropic", "OpenAI", "ElevenLabs", "fal.ai", "xAI (Grok)"}

# 단위 옵션 (자유 문자열이지만 UI 드롭다운 참고용)
DEFAULT_UNITS = ["USD", "KRW", "credits", "chars"]


class BalanceUpsert(BaseModel):
    provider: str
    amount: float
    unit: str = "USD"
    note: Optional[str] = ""
    low_threshold: Optional[float] = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load() -> dict:
    try:
        if BALANCE_FILE.exists():
            return json.loads(BALANCE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict):
    BALANCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BALANCE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _format_amount(amt: float, unit: str) -> str:
    u = (unit or "").strip()
    if u.upper() == "USD":
        return f"${amt:,.2f}"
    if u.upper() == "KRW":
        return f"₩{int(amt):,}"
    if u.lower() == "chars":
        return f"{int(amt):,} chars"
    return f"{amt:,.2f} {u}".strip() if u else f"{amt:,.2f}"


def _compute_remaining(provider: str, entry: dict) -> tuple[float, float]:
    """(remaining_amount, spent_amount) 반환. unit 이 USD 가 아니면 감산 없음."""
    initial = float(entry.get("initial_amount", entry.get("amount", 0)) or 0)
    unit = (entry.get("unit") or "").strip().upper()
    set_at = entry.get("set_at")
    # USD 만 실시간 감산. 다른 단위(KRW/chars/credits)는 입력값 그대로 표시.
    if unit != "USD":
        return initial, 0.0
    spent = spend_ledger.spend_since(provider, set_at)
    remaining = max(0.0, initial - spent)
    return remaining, spent


def _build_row(provider: str, entry: Optional[dict]) -> dict:
    if not entry:
        return {
            "provider": provider,
            "has_balance": False,
            "amount": None,
            "initial_amount": None,
            "remaining": None,
            "spent": None,
            "unit": "USD",
            "note": "",
            "set_at": None,
            "updated_at": None,
            "low_threshold": None,
            "low": False,
            "display": None,
            "display_initial": None,
        }
    unit = entry.get("unit") or "USD"
    remaining, spent = _compute_remaining(provider, entry)
    threshold = entry.get("low_threshold")
    low = bool(threshold is not None and remaining is not None and remaining < float(threshold))
    initial = float(entry.get("initial_amount", entry.get("amount", 0)) or 0)
    return {
        "provider": provider,
        "has_balance": True,
        "amount": remaining,
        "initial_amount": initial,
        "remaining": remaining,
        "spent": spent,
        "unit": unit,
        "note": entry.get("note") or "",
        "set_at": entry.get("set_at"),
        "updated_at": entry.get("updated_at"),
        "low_threshold": threshold,
        "low": low,
        "display": _format_amount(remaining, unit),
        "display_initial": _format_amount(initial, unit),
    }


@router.get("")
async def list_balances():
    """모든 수동 입력 잔액 조회 — 실시간 감산 포함."""
    data = _load()
    out = [_build_row(p, data.get(p)) for p in ALLOWED_PROVIDERS]
    return {"balances": out, "default_units": DEFAULT_UNITS}


@router.put("")
async def upsert_balance(body: BalanceUpsert):
    if body.provider not in ALLOWED_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {body.provider}")
    now = _now_iso()
    data = _load()
    data[body.provider] = {
        "amount": float(body.amount),
        "initial_amount": float(body.amount),
        "unit": body.unit or "USD",
        "note": body.note or "",
        "set_at": now,
        "updated_at": now,
        "low_threshold": float(body.low_threshold) if body.low_threshold is not None else None,
    }
    _save(data)
    return {"status": "saved", **_build_row(body.provider, data[body.provider])}


@router.delete("/{provider}")
async def delete_balance(provider: str):
    data = _load()
    if provider in data:
        del data[provider]
        _save(data)
        return {"status": "deleted", "provider": provider}
    return {"status": "not_found", "provider": provider}


@router.post("/{provider}/reset-spend")
async def reset_spend(provider: str):
    """`set_at` 을 now 로 갱신하고, 이전 지출 레코드를 prune.

    "방금 새 크레딧 충전했어요" 용 — 감산 기준점을 재설정한다.
    """
    if provider not in ALLOWED_PROVIDERS:
        raise HTTPException(400, f"Unknown provider: {provider}")
    data = _load()
    entry = data.get(provider)
    if not entry:
        raise HTTPException(404, "balance not set")
    now = _now_iso()
    # 기존 기록 물리적 삭제 (선택) — 이후 spend_since(now) 는 0 에서 시작
    try:
        spend_ledger.prune_before(now)
    except Exception:
        pass
    entry["set_at"] = now
    entry["updated_at"] = now
    # amount 를 initial 로 리셋
    entry["amount"] = float(entry.get("initial_amount", entry.get("amount", 0)) or 0)
    data[provider] = entry
    _save(data)
    return {"status": "reset", **_build_row(provider, entry)}


def get_manual_balance(provider: str) -> Optional[dict]:
    """다른 모듈(api_status)에서 참조하는 헬퍼. `remaining` 을 amount 로 제공."""
    data = _load()
    entry = data.get(provider)
    if not entry:
        return None
    remaining, spent = _compute_remaining(provider, entry)
    unit = entry.get("unit") or "USD"
    threshold = entry.get("low_threshold")
    low = bool(threshold is not None and remaining is not None and remaining < float(threshold))
    initial = float(entry.get("initial_amount", entry.get("amount", 0)) or 0)
    return {
        "amount": remaining,
        "initial_amount": initial,
        "remaining": remaining,
        "spent": spent,
        "unit": unit,
        "display": _format_amount(remaining, unit),
        "display_initial": _format_amount(initial, unit),
        "set_at": entry.get("set_at"),
        "updated_at": entry.get("updated_at"),
        "low_threshold": threshold,
        "low": low,
        "note": entry.get("note") or "",
    }
