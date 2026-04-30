"""API 지출 원장 (v1.1.55).

목적: 수동 입력 잔액을 실시간으로 감산하기 위해 모든 API 호출의 예상 비용을
JSONL 원장에 append 한다. 원장은 provider 이름 단위로 집계되며, 사용자가 마지막으로
잔액을 설정한 시각(`set_at`) 이후의 합계를 `manual_balance - spend_since = remaining`
형태로 계산해 대시보드에 노출한다.

- 저장소: DATA_DIR/api_spend_log.jsonl  (각 줄 1 레코드)
- 레코드 포맷:
    {"ts": "2026-04-15T12:34:56Z",
     "provider": "Anthropic",
     "amount_usd": 0.0123,
     "kind": "llm"|"image"|"tts"|"video"|"other",
     "model": "claude-sonnet-4-6",
     "project_id": "abc",
     "units": 120,
     "note": ""}

주의:
- 여기서 기록하는 값은 `estimation_service` 의 공식 가격표 기반 "예상" 비용이다.
  실제 청구액과 정확히 일치하진 않지만 잔액 추세 파악용으로는 충분하다.
- 기록 실패가 파이프라인을 깨뜨리면 안 되므로 모든 함수는 예외를 삼킨다.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.config import DATA_DIR

LOG_FILE = Path(DATA_DIR) / "api_spend_log.jsonl"

# Registry provider 토큰 → api_balances 화이트리스트의 공식 이름
PROVIDER_MAP = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "elevenlabs": "ElevenLabs",
    "fal": "fal.ai",
    "bbanana": "fal.ai",          # nano-banana 는 fal 인프라 사용
    "xai": "xAI (Grok)",
    "xai-grok": "xAI (Grok)",
    "comfyui": "ComfyUI (Local)",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_provider(token: Optional[str]) -> Optional[str]:
    if not token:
        return None
    t = str(token).strip().lower()
    return PROVIDER_MAP.get(t)


def _append(record: dict):
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[spend_ledger] append failed: {e}")


def _read_all() -> list[dict]:
    if not LOG_FILE.exists():
        return []
    out: list[dict] = []
    try:
        with LOG_FILE.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    continue
    except Exception as e:
        print(f"[spend_ledger] read failed: {e}")
    return out


def _iso_gt(a: str, b: str) -> bool:
    """ISO 타임스탬프 문자열 비교. 'Z' suffix 포함."""
    try:
        return a >= b
    except Exception:
        return False


def spend_since(provider: str, since_iso: Optional[str]) -> float:
    """provider 의 since_iso 이후 누적 USD 지출."""
    total = 0.0
    for r in _read_all():
        if r.get("provider") != provider:
            continue
        if since_iso and not _iso_gt(r.get("ts", ""), since_iso):
            continue
        try:
            total += float(r.get("amount_usd") or 0.0)
        except Exception:
            pass
    return total


def record(
    provider_token: str,
    amount_usd: float,
    *,
    kind: str = "other",
    model: str = "",
    project_id: Optional[str] = None,
    units: Optional[float] = None,
    note: str = "",
):
    """원시 지출 기록. provider_token 은 registry 의 'provider' 필드 값."""
    prov = _canonical_provider(provider_token)
    if not prov:
        return
    if amount_usd is None or amount_usd <= 0:
        return
    _append({
        "ts": _now_iso(),
        "provider": prov,
        "amount_usd": round(float(amount_usd), 6),
        "kind": kind,
        "model": model or "",
        "project_id": project_id or "",
        "units": units,
        "note": note or "",
    })


# --------------------------------------------------------------------------- #
# 모델별 비용 계산 + 기록 헬퍼. estimation_service 와 동일한 가격표 사용.
# --------------------------------------------------------------------------- #

def record_llm(model_id: str, input_tokens: int, output_tokens: int, *, project_id: Optional[str] = None, note: str = ""):
    try:
        from app.services.llm.factory import LLM_REGISTRY
        meta = LLM_REGISTRY.get(model_id)
        if not meta:
            return
        ci = float(meta.get("cost_input") or 0.0)
        co = float(meta.get("cost_output") or 0.0)
        cost = (input_tokens * ci + output_tokens * co) / 1_000_000.0
        record(meta.get("provider"), cost, kind="llm", model=model_id,
               project_id=project_id, units=input_tokens + output_tokens, note=note)
    except Exception as e:
        print(f"[spend_ledger] record_llm error: {e}")


def record_image(model_id: str, n_images: int, *, project_id: Optional[str] = None, note: str = ""):
    try:
        from app.services.image.factory import IMAGE_REGISTRY
        meta = IMAGE_REGISTRY.get(model_id)
        if not meta:
            return
        per = float(meta.get("cost_value") or 0.0)
        cost = per * max(0, int(n_images))
        record(meta.get("provider"), cost, kind="image", model=model_id,
               project_id=project_id, units=n_images, note=note)
    except Exception as e:
        print(f"[spend_ledger] record_image error: {e}")


def record_tts(model_id: str, chars: int, *, project_id: Optional[str] = None, note: str = ""):
    try:
        from app.services.tts.factory import TTS_REGISTRY
        meta = TTS_REGISTRY.get(model_id)
        if not meta:
            return
        per_1k = float(meta.get("cost_value") or 0.0)
        cost = (max(0, int(chars)) / 1000.0) * per_1k
        record(meta.get("provider"), cost, kind="tts", model=model_id,
               project_id=project_id, units=chars, note=note)
    except Exception as e:
        print(f"[spend_ledger] record_tts error: {e}")


def record_video(model_id: str, n_clips: int, *, project_id: Optional[str] = None, note: str = ""):
    try:
        from app.services.video.factory import VIDEO_REGISTRY
        meta = VIDEO_REGISTRY.get(model_id)
        if not meta:
            return
        per = float(meta.get("cost_value") or 0.0)
        cost = per * max(0, int(n_clips))
        record(meta.get("provider"), cost, kind="video", model=model_id,
               project_id=project_id, units=n_clips, note=note)
    except Exception as e:
        print(f"[spend_ledger] record_video error: {e}")


def prune_before(iso_ts: str):
    """iso_ts 이전 레코드를 물리적으로 삭제 (선택). 잔액 리셋 시 호출."""
    try:
        if not LOG_FILE.exists():
            return
        kept = [r for r in _read_all() if _iso_gt(r.get("ts", ""), iso_ts)]
        with LOG_FILE.open("w", encoding="utf-8") as f:
            for r in kept:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[spend_ledger] prune error: {e}")
