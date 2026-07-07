"""Story-plan stage helpers.

The script prompt itself remains in app.services.llm.base. This module only
coordinates the visible pipeline stage, cache file, model selection, and DB
step state.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import resolve_project_dir
from app.models.project import Project

STORY_STEP_KEY = "story"
DEFAULT_STORY_MODEL = "claude-sonnet-4-6"


def resolve_story_model_id(config: dict | None) -> str:
    cfg = config or {}
    return str(cfg.get("story_model") or cfg.get("script_model") or DEFAULT_STORY_MODEL)


def story_plan_path(project_id: str, config: dict | None = None, *, create: bool = False) -> Path:
    return resolve_project_dir(project_id, config or {}, create=create) / "story_plan.json"


def load_story_plan(project_id: str, config: dict | None = None) -> dict | None:
    path = story_plan_path(project_id, config, create=False)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def story_plan_response(project_id: str, config: dict | None = None) -> dict:
    path = story_plan_path(project_id, config, create=False)
    plan = load_story_plan(project_id, config)
    if plan is None:
        return {
            "project_id": project_id,
            "exists": False,
            "story_model": resolve_story_model_id(config),
            "path": str(path),
            "story_plan": None,
        }
    return {
        "project_id": project_id,
        "exists": True,
        "story_model": str(plan.get("story_model") or resolve_story_model_id(config)),
        "path": str(path),
        "story_plan": plan,
    }


def mark_story_step_state(db: Session, project_id: str, state: str) -> None:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return
    states = dict(project.step_states or {})
    states[STORY_STEP_KEY] = state
    project.step_states = states
    flag_modified(project, "step_states")
    db.commit()


def assert_llm_provider_key(model_id: str) -> None:
    from app import config as app_config

    provider = "anthropic" if "claude" in model_id else "openai"
    if provider == "anthropic" and not app_config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to backend/.env file.")
    if provider == "openai" and not app_config.OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set. Add it to backend/.env file.")


async def generate_story_plan_for_project(topic: str, config: dict[str, Any]) -> dict:
    cfg = dict(config or {})
    model_id = resolve_story_model_id(cfg)
    from app.services.llm.factory import get_llm_service

    service = get_llm_service(model_id)
    load_cached = getattr(service, "_load_cached_story_plan", None)
    if callable(load_cached):
        cached = load_cached(topic, cfg)
        if cached is not None:
            return cached
    if str(service.__class__.__module__).startswith("app.services.llm."):
        assert_llm_provider_key(model_id)
    return await service.generate_story_plan(topic, cfg)
