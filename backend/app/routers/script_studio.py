"""Standalone Script Studio API.

This tool is separate from the production pipeline. It reads LongTube project
settings, creates script-only drafts, and only writes back to a project when the
user explicitly applies a draft.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.services import script_studio_service as studio


router = APIRouter()


class DraftCreate(BaseModel):
    source_project_id: str | None = None
    topic: str | None = None
    title: str | None = None
    config_overrides: dict | None = None


class DraftUpdate(BaseModel):
    topic: str | None = None
    title: str | None = None
    config: dict | None = None


class QueueDraftCreate(BaseModel):
    config_overrides: dict | None = None
    replace_existing: bool = False


class ApplyDraftRequest(BaseModel):
    target_project_id: str | None = None


class ScriptStartRequest(BaseModel):
    mode: str | None = None
    block_index: int | None = None


def _raise_400(exc: Exception):
    raise HTTPException(status_code=400, detail=studio.humanize_generation_error(exc))


@router.get("/sources")
def list_sources(db: Session = Depends(get_db)):
    return {"projects": studio.list_source_projects(db)}


@router.get("/models")
async def list_models():
    return {"models": await studio.list_script_studio_models()}


@router.get("/queue-topics")
def list_queue_topics(db: Session = Depends(get_db)):
    return studio.list_queue_topics(db)


@router.post("/queue-topics/{item_id}/draft")
def create_draft_from_queue_item(
    item_id: str,
    body: QueueDraftCreate | None = None,
    db: Session = Depends(get_db),
):
    try:
        return studio.create_draft_from_queue_item(
            db,
            item_id,
            config_overrides=(body.config_overrides if body else None),
            replace_existing=bool(body.replace_existing) if body else False,
        )
    except Exception as exc:
        _raise_400(exc)


@router.get("/drafts")
def list_drafts():
    return {"drafts": studio.list_drafts()}


@router.post("/drafts")
def create_draft(body: DraftCreate, db: Session = Depends(get_db)):
    try:
        return studio.create_draft(
            db,
            source_project_id=body.source_project_id,
            topic=body.topic,
            title=body.title,
            config_overrides=body.config_overrides,
        )
    except Exception as exc:
        _raise_400(exc)


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str):
    try:
        return studio.get_draft(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")


@router.delete("/drafts/{draft_id}")
def delete_draft(draft_id: str):
    try:
        return studio.delete_draft(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.put("/drafts/{draft_id}")
def update_draft(draft_id: str, body: DraftUpdate):
    try:
        return studio.update_draft(
            draft_id,
            {"topic": body.topic, "title": body.title, "config": body.config},
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/story-plan")
async def generate_story_plan(draft_id: str):
    try:
        return await studio.generate_story_for_draft(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/story-plan/start")
async def start_story_plan(draft_id: str):
    try:
        return studio.start_draft_job(draft_id, "story")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/script")
async def generate_script(draft_id: str, body: ScriptStartRequest | None = None):
    try:
        return await studio.generate_script_for_draft(
            draft_id,
            mode=(body.mode if body else None),
            block_index=(body.block_index if body else None),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/script/start")
async def start_script(draft_id: str, body: ScriptStartRequest | None = None):
    try:
        return studio.start_draft_job(
            draft_id,
            "script",
            script_mode=(body.mode if body else None),
            block_index=(body.block_index if body else None),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/validate")
async def validate_draft(draft_id: str):
    try:
        return await studio.validate_draft_with_llm(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/validate/start")
async def start_validate_draft(draft_id: str):
    try:
        return studio.start_draft_job(draft_id, "validate")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.get("/drafts/{draft_id}/export")
def export_draft(draft_id: str):
    try:
        return studio.export_draft_script(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/apply-to-project")
def apply_to_project(
    draft_id: str,
    body: ApplyDraftRequest | None = None,
    db: Session = Depends(get_db),
):
    try:
        return studio.apply_draft_to_project(
            db,
            draft_id,
            target_project_id=(body.target_project_id if body else None),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/apply-to-project/start")
async def start_apply_to_project(
    draft_id: str,
    body: ApplyDraftRequest | None = None,
):
    try:
        return studio.start_draft_job(
            draft_id,
            "apply",
            target_project_id=(body.target_project_id if body else None),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)


@router.post("/drafts/{draft_id}/cancel")
async def cancel_draft_job(draft_id: str):
    try:
        return studio.cancel_draft_job(draft_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="대본 초안을 찾을 수 없습니다.")
    except Exception as exc:
        _raise_400(exc)
