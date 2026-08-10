"""Read a manually saved Studio script without invoking an LLM."""
from __future__ import annotations

import json
from pathlib import Path

from app.config import resolve_project_dir

LOCAL_SCRIPT_MODEL_ID = "local-script"


def is_local_script_model(model_id: object) -> bool:
    return str(model_id or "").strip().lower() == LOCAL_SCRIPT_MODEL_ID


def load_local_saved_script(project_id: str, config: dict | None) -> dict:
    path = resolve_project_dir(project_id, config or {}, create=False) / "script.json"
    if not path.exists():
        raise ValueError("로컬 대본이 없습니다. Studio에서 수동 저장한 대본을 먼저 저장해야 합니다.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"로컬 대본을 읽을 수 없습니다: {exc}") from exc
    cuts = payload.get("cuts") if isinstance(payload, dict) else None
    if not isinstance(cuts, list) or not cuts:
        raise ValueError("로컬 대본에 유효한 cuts가 없습니다.")
    expected = 1
    for cut in cuts:
        if not isinstance(cut, dict):
            raise ValueError("로컬 대본 cuts 형식이 올바르지 않습니다.")
        if int(cut.get("cut_number") or 0) != expected:
            raise ValueError("로컬 대본 cut_number는 1부터 연속이어야 합니다.")
        if not str(cut.get("narration") or "").strip() or not str(cut.get("image_prompt") or "").strip():
            raise ValueError(f"로컬 대본 cut {expected}에 narration 또는 image_prompt가 없습니다.")
        expected += 1
    return payload
