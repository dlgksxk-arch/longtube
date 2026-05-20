"""OpenAI official Costs API synchronization.

OpenAI does not expose a balance endpoint.  This module stores a local
top-up baseline and subtracts the official organization costs returned by
`/v1/organization/costs`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

from app.config import DATA_DIR


SYNC_FILE = Path(DATA_DIR) / "api_official_cost_sync.json"
OPENAI_PROVIDER = "OpenAI"
OPENAI_COSTS_URL = "https://api.openai.com/v1/organization/costs"


class OpenAICostSyncError(RuntimeError):
    pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Optional[str], *, default_now: bool = False) -> datetime:
    text = (value or "").strip()
    if not text:
        if default_now:
            return _now_utc()
        raise ValueError("timestamp is empty")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_usd_amount(value: Optional[str]) -> Optional[float]:
    """Parse a loose USD text value like "$50.00" or "50달러"."""
    text = (value or "").replace(",", "").strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    amount = float(match.group(0))
    if amount < 0:
        return None
    return amount


def _load() -> dict:
    try:
        if SYNC_FILE.exists():
            return json.loads(SYNC_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict) -> None:
    SYNC_FILE.parent.mkdir(parents=True, exist_ok=True)
    SYNC_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _state_from_entry(entry: Optional[dict]) -> dict:
    if not entry:
        return {
            "configured": False,
            "status": "not_configured",
            "initial_balance_usd": None,
            "baseline_at": None,
            "official_spend_usd": None,
            "remaining_usd": None,
            "last_sync_at": None,
            "last_error": None,
            "credential_source": None,
        }
    return {
        "configured": True,
        "status": entry.get("status") or "configured",
        "initial_balance_usd": entry.get("initial_balance_usd"),
        "baseline_at": entry.get("baseline_at"),
        "official_spend_usd": entry.get("official_spend_usd"),
        "remaining_usd": entry.get("remaining_usd"),
        "last_sync_at": entry.get("last_sync_at"),
        "last_error": entry.get("last_error"),
        "credential_source": entry.get("credential_source"),
    }


def get_openai_cost_sync_state() -> dict:
    return _state_from_entry(_load().get(OPENAI_PROVIDER))


def set_openai_baseline(initial_balance_usd: float, baseline_at: Optional[str] = None) -> dict:
    baseline_dt = _parse_iso(baseline_at, default_now=True)
    data = _load()
    data[OPENAI_PROVIDER] = {
        "initial_balance_usd": round(float(initial_balance_usd), 6),
        "baseline_at": _iso(baseline_dt),
        "official_spend_usd": None,
        "remaining_usd": round(float(initial_balance_usd), 6),
        "status": "configured",
        "last_sync_at": None,
        "last_error": None,
        "credential_source": None,
        "updated_at": _iso(_now_utc()),
    }
    _save(data)
    return _state_from_entry(data[OPENAI_PROVIDER])


def clear_openai_baseline() -> dict:
    data = _load()
    if OPENAI_PROVIDER in data:
        del data[OPENAI_PROVIDER]
        _save(data)
    return get_openai_cost_sync_state()


def _save_error(entry: dict, message: str, credential_source: Optional[str] = None) -> dict:
    entry = dict(entry)
    entry["status"] = "error"
    entry["last_error"] = message
    entry["last_sync_at"] = _iso(_now_utc())
    if credential_source:
        entry["credential_source"] = credential_source
    data = _load()
    data[OPENAI_PROVIDER] = entry
    _save(data)
    return _state_from_entry(entry)


async def _fetch_openai_costs(
    *,
    admin_key: str,
    start_dt: datetime,
    end_dt: datetime,
    organization_id: Optional[str] = None,
) -> float:
    if end_dt <= start_dt:
        return 0.0

    headers = {
        "Authorization": f"Bearer {admin_key}",
        "Content-Type": "application/json",
    }
    if organization_id:
        headers["OpenAI-Organization"] = organization_id

    params = {
        "start_time": str(int(start_dt.timestamp())),
        "end_time": str(int(end_dt.timestamp())),
        "bucket_width": "1d",
        "limit": "180",
    }

    total = 0.0
    page_count = 0
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(OPENAI_COSTS_URL, headers=headers, params=params)
            if resp.status_code >= 400:
                body = resp.text[:800]
                if resp.status_code == 403 and "api.usage.read" in body:
                    raise OpenAICostSyncError(
                        "OpenAI Costs API HTTP 403: api.usage.read 권한이 있는 Admin key가 필요합니다."
                    )
                raise OpenAICostSyncError(f"OpenAI Costs API HTTP {resp.status_code}: {body}")

            payload = resp.json()
            for bucket in payload.get("data") or []:
                for result in bucket.get("results") or []:
                    amount = result.get("amount") or {}
                    currency = str(amount.get("currency") or "usd").lower()
                    if currency != "usd":
                        continue
                    total += float(amount.get("value") or 0.0)

            page_count += 1
            next_page = payload.get("next_page")
            if not payload.get("has_more") or not next_page:
                break
            if page_count >= 20:
                raise OpenAICostSyncError("OpenAI Costs API pagination limit exceeded")
            params["page"] = next_page

    return total


async def sync_openai_costs(
    *,
    admin_key: str,
    credential_source: str,
    organization_id: Optional[str] = None,
) -> dict:
    data = _load()
    entry = data.get(OPENAI_PROVIDER)
    if not entry:
        return get_openai_cost_sync_state()

    if not admin_key:
        return _save_error(
            entry,
            "OPENAI_ADMIN_KEY 또는 OpenAI Admin vault key가 없습니다.",
            credential_source=None,
        )

    try:
        start_dt = _parse_iso(entry.get("baseline_at"))
        end_dt = _now_utc()
        official_spend = await _fetch_openai_costs(
            admin_key=admin_key,
            start_dt=start_dt,
            end_dt=end_dt,
            organization_id=organization_id,
        )
        initial = float(entry.get("initial_balance_usd") or 0.0)
        remaining = max(0.0, initial - official_spend)
        entry = dict(entry)
        entry.update(
            {
                "official_spend_usd": round(official_spend, 6),
                "remaining_usd": round(remaining, 6),
                "status": "synced",
                "last_sync_at": _iso(end_dt),
                "last_error": None,
                "credential_source": credential_source,
                "updated_at": _iso(end_dt),
            }
        )
        data[OPENAI_PROVIDER] = entry
        _save(data)
        return _state_from_entry(entry)
    except Exception as exc:
        return _save_error(entry, str(exc), credential_source=credential_source)
