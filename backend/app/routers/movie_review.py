"""LongTube movie-review source workspace API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.services import movie_review_service


router = APIRouter()


class MovieReviewJobCreate(BaseModel):
    source_url: str = Field(min_length=10, max_length=2048)
    max_height: Literal[720, 1080, 1440, 2160] = 1080
    subtitle_languages: list[str] = Field(default_factory=lambda: ["ko", "ja", "en"])
    rights_confirmed: bool = False


class MovieReviewShortsLayoutUpdate(BaseModel):
    layout_version: Literal[2] = 2
    canvas_width: Literal[1080] = 1080
    canvas_height: Literal[1920] = 1920
    background_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    title_top: int = Field(ge=0, le=320)
    title_center_x: int = Field(ge=80, le=1000)
    title_font_size: int = Field(ge=48, le=140)
    title_accent_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    video_top: int = Field(ge=280, le=700)
    video_height: int = Field(ge=480, le=1050)
    caption_top: int = Field(ge=900, le=1600)
    caption_center_x: int = Field(ge=80, le=1000)
    caption_font_size: int = Field(ge=42, le=100)
    caption_background_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_background_opacity: int = Field(ge=0, le=100)
    caption_outline_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    caption_outline_width: int = Field(ge=0, le=15)
    movie_title_top: int = Field(ge=1200, le=1760)
    movie_title_center_x: int = Field(ge=80, le=1000)
    movie_title_font_size: int = Field(ge=36, le=96)
    movie_title_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    movie_title_outline_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    movie_title_outline_width: int = Field(ge=0, le=12)
    channel_top: int = Field(ge=1200, le=1830)
    channel_center_x: int = Field(ge=80, le=1000)
    channel_font_size: int = Field(ge=42, le=120)
    channel_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    intertitle_background_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    intertitle_text_top: int = Field(ge=120, le=1680)
    intertitle_text_center_x: int = Field(ge=80, le=1000)
    intertitle_text_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    intertitle_font_size: int = Field(ge=42, le=120)
    intertitle_outline_color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    intertitle_outline_width: int = Field(ge=0, le=15)


class MovieReviewThumbnailFrameSelect(BaseModel):
    time_seconds: float = Field(ge=0)


@router.get("/runtime")
def get_runtime() -> dict:
    return movie_review_service.runtime_info()


@router.get("/jobs")
def get_jobs(limit: int = Query(50, ge=1, le=200)) -> dict:
    jobs = movie_review_service.list_jobs(limit=limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    try:
        return movie_review_service.get_job(job_id)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str) -> dict:
    try:
        return movie_review_service.delete_job(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/jobs", status_code=202)
async def create_job(payload: MovieReviewJobCreate) -> dict:
    try:
        return await movie_review_service.start_job(
            source_url=payload.source_url,
            max_height=payload.max_height,
            subtitle_languages=payload.subtitle_languages,
            rights_confirmed=payload.rights_confirmed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.post("/jobs/{job_id}/transcribe", status_code=202)
async def transcribe_job(job_id: str) -> dict:
    try:
        return await movie_review_service.start_transcription(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/jobs/{job_id}/generate-preview", status_code=202)
async def generate_preview(job_id: str) -> dict:
    try:
        return await movie_review_service.start_preview_generation(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.put("/jobs/{job_id}/shorts-layout")
def update_shorts_layout(job_id: str, payload: MovieReviewShortsLayoutUpdate) -> dict:
    try:
        return movie_review_service.update_shorts_layout(job_id, payload.model_dump())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/jobs/{job_id}/thumbnail-frame")
async def select_thumbnail_frame(job_id: str, payload: MovieReviewThumbnailFrameSelect) -> dict:
    try:
        return await movie_review_service.select_thumbnail_frame(job_id, payload.time_seconds)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="작업을 찾을 수 없습니다.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/jobs/{job_id}/artifacts/{kind}")
def download_artifact(job_id: str, kind: str) -> FileResponse:
    try:
        path = movie_review_service.resolve_artifact(job_id, kind)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="산출물을 찾을 수 없습니다.")
    return FileResponse(path, filename=path.name)
