"""Factory V5 source intake routes."""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import resolve_project_dir
from app.models.database import get_db
from app.models.project import Project
from app.routers.projects import DEFAULT_CONFIG, normalize_default_config
from app.services.factory_v5_silla import (
    DEFAULT_ACTUAL_ASSET_ROOT,
    DEFAULT_SOURCE_ROOT,
    EXPECTED_CUT_COUNT,
    SOURCE_SCHEMA,
    import_silla_workbook,
    list_silla_workbooks,
    parse_silla_workbook,
    resolve_source_workbook,
)


router = APIRouter()


class SillaImportRequest(BaseModel):
    filename: str
    project_id: str


def _project_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "title": project.title,
        "topic": project.topic,
        "status": project.status,
        "config": project.config or {},
    }


@router.get("/silla/workbooks")
def silla_workbooks():
    return list_silla_workbooks(DEFAULT_SOURCE_ROOT)


@router.get("/silla/presets")
def silla_presets(db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    return [
        _project_dict(project)
        for project in projects
        if (project.config or {}).get("factory_series") == "신라사"
    ]


@router.post("/silla/presets")
def create_silla_preset(db: Session = Depends(get_db)):
    config = normalize_default_config(
        {
            **DEFAULT_CONFIG,
            "factory_version": 5,
            "factory_series": "신라사",
            "factory_source_schema": SOURCE_SCHEMA,
            "factory_source_root": str(DEFAULT_SOURCE_ROOT),
            "factory_actual_asset_root": str(DEFAULT_ACTUAL_ASSET_ROOT),
            "prepared_script_required": True,
            "script_model": "local-script",
            "image_model": "comfyui-krea2",
            "target_cuts": EXPECTED_CUT_COUNT,
            "target_duration": 600,
            "cut_level_subtitles": False,
            "subtitle_delivery": "youtube_captions",
            "youtube_captions_enabled": True,
            "caption_languages": ["ko"],
        }
    )
    project = Project(
        id=str(uuid.uuid4())[:8],
        title="신라사 공장",
        topic="신라사",
        config=config,
        status="draft",
    )
    db.add(project)
    db.commit()
    project_dir = resolve_project_dir(project.id, config=config, create=True)
    for subdir in (
        "audio",
        "images",
        "videos",
        "subtitles",
        "output",
        "prepared_scripts",
        "prepared_assets",
    ):
        os.makedirs(project_dir / subdir, exist_ok=True)
    return _project_dict(project)


@router.post("/silla/import")
def import_silla_episode(body: SillaImportRequest, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if not project:
        raise HTTPException(404, "프리셋을 찾을 수 없습니다.")
    config = dict(project.config or {})
    if config.get("factory_series") != "신라사" or config.get("factory_source_schema") != SOURCE_SCHEMA:
        raise HTTPException(400, "기존 프리셋에는 등록할 수 없습니다. 신라사 전용 프리셋을 사용하세요.")
    try:
        source_path = resolve_source_workbook(body.filename, DEFAULT_SOURCE_ROOT)
        parsed = parse_silla_workbook(source_path)
        project_dir = resolve_project_dir(project.id, config=config, create=True)
        result = import_silla_workbook(parsed, project_dir)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"XLSX 파일을 찾을 수 없습니다: {Path(exc.filename or body.filename).name}") from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {
        "factory_version": 5,
        "project": _project_dict(project),
        "workbook": parsed.summary,
        "import": result,
        "queue_changed": False,
        "source_workbook_changed": False,
    }
