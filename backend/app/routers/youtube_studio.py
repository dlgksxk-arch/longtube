"""YouTube Studio 라우터 (v1.1.31).

LongTube 파이프라인에 묶여 있지 않은 **일반 YouTube 채널 관리** 기능을
노출합니다. 이미 올라가 있는 영상을 Studio 대시보드처럼 조회/편집/삭제
하고, 새 영상을 파이프라인 없이 직접 업로드하며, 재생목록과 댓글까지
API v3 가 허용하는 범위 안에서 전부 만질 수 있도록 설계했습니다.

- 프로젝트에 종속되지 않기 때문에 `YouTubeUploader()` (전역 token.json) 을
  기본값으로 씁니다. 프로젝트 토큰을 쓰고 싶으면 쿼리 파라미터
  `project_id=<id>` 로 넘기면 됩니다.
- 파일 업로드는 fastapi UploadFile 로 받고 임시 파일로 flush 한 뒤
  기존 `YouTubeUploader.upload` 에 넘기는 방식 — 파이프라인 없이도
  resumable 업로드가 그대로 동작합니다.
- 모든 blocking googleapiclient 호출은 `asyncio.to_thread` 로 감쌉니다.
- YouTube Analytics (조회수 그래프, 수익 등) 는 별도 scope 라 여기서는
  다루지 않습니다. statistics (단순 viewCount/likeCount) 는 videos.list
  에서 같이 내려받기 때문에 list/detail 응답에 포함돼 있습니다.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field

from app.services.youtube_service import (
    YouTubeUploader,
    YouTubeAuthError,
    YouTubeUploadError,
    VALID_PRIVACY,
)
from app.models.database import SessionLocal
from app.models.project import Project

router = APIRouter()


# ---------- Helpers ----------


def _uploader(project_id: Optional[str]) -> YouTubeUploader:
    """project_id 가 있으면 프로젝트 토큰, 없으면 전역 토큰 사용.

    v1.1.25 부터 프로젝트별 토큰을 권장하지만 Studio 화면에서는 "채널 단위"
    로 여러 프로젝트를 가로질러 관리하므로 전역 토큰을 기본값으로 둡니다.
    """
    pid = (project_id or "").strip() or None
    return YouTubeUploader(project_id=pid)


def _require_auth(up: YouTubeUploader) -> None:
    if not up.is_authenticated():
        raise HTTPException(
            401,
            "YouTube 인증이 필요합니다. /api/youtube/auth 먼저 호출해 토큰을 발급받으세요.",
        )


def _wrap_errors(e: Exception) -> HTTPException:
    if isinstance(e, YouTubeAuthError):
        return HTTPException(401, str(e))
    if isinstance(e, YouTubeUploadError):
        return HTTPException(400, str(e))
    return HTTPException(500, f"예상치 못한 오류: {e}")


# ---------- Schemas ----------


class StudioAuthStatus(BaseModel):
    authenticated: bool
    project_id: Optional[str] = None
    channel_id: Optional[str] = None
    channel_title: Optional[str] = None


class VideoUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    category_id: Optional[str] = None
    default_language: Optional[str] = None
    privacy_status: Optional[Literal["private", "unlisted", "public"]] = None
    publish_at: Optional[str] = Field(
        default=None,
        description=(
            "RFC3339 (예: 2026-04-13T15:00:00Z). 이 값이 들어오면 privacy_status "
            "가 자동으로 private 로 내려가며 해당 시각에 YouTube 가 public 으로 "
            "전환합니다. 예약을 해제하려면 빈 문자열 \"\" 을 보내세요."
        ),
    )
    made_for_kids: Optional[bool] = None
    embeddable: Optional[bool] = None
    public_stats_viewable: Optional[bool] = None


class PlaylistCreateRequest(BaseModel):
    title: str
    description: str = ""
    privacy_status: Literal["private", "unlisted", "public"] = "private"


class PlaylistUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    privacy_status: Optional[Literal["private", "unlisted", "public"]] = None


class PlaylistAddItemRequest(BaseModel):
    video_id: str


class CommentReplyRequest(BaseModel):
    text: str


class CommentModerationRequest(BaseModel):
    status: Literal["heldForReview", "published", "rejected"]
    ban_author: bool = False


# ---------- Auth ----------


@router.get("/auth/status", response_model=StudioAuthStatus)
async def studio_auth_status(project_id: Optional[str] = Query(default=None)):
    """Studio 화면 진입 시 호출 — 로그인 여부 + 채널 정보 한 번에 반환.

    인증돼 있지 않아도 200 으로 `authenticated=false` 를 내려줍니다.
    """
    up = _uploader(project_id)
    if not up.is_authenticated():
        return StudioAuthStatus(authenticated=False, project_id=project_id)
    try:
        info = await asyncio.to_thread(up.get_channel_info)
    except Exception as e:
        # 토큰은 있으나 채널 조회 실패 — 로그만 남기고 authenticated=true 로 반환
        print(f"[youtube-studio] channel_info 실패 (non-fatal): {e}")
        return StudioAuthStatus(authenticated=True, project_id=project_id)
    return StudioAuthStatus(
        authenticated=True,
        project_id=project_id,
        channel_id=info.get("channel_id"),
        channel_title=info.get("title") or info.get("channel_title"),
    )


# ---------- Videos ----------


def _match_longtube_projects(video_ids: list[str]) -> dict[str, dict]:
    """YouTube video_id 목록을 LongTube 프로젝트와 매칭.

    Project.youtube_url 에 video_id 가 포함된 행을 찾아서
    {video_id: {project_id, title, created_at, source}} 형태로 반환.
    source: "oneclick" | "preset" (config.__oneclick__ 여부)
    """
    if not video_ids:
        return {}
    db = SessionLocal()
    try:
        projects = db.query(Project).filter(
            Project.youtube_url.isnot(None),
            Project.youtube_url != "",
        ).all()

        result: dict[str, dict] = {}
        for p in projects:
            url = p.youtube_url or ""
            for vid in video_ids:
                if vid in url:
                    cfg = p.config or {}
                    result[vid] = {
                        "project_id": p.id,
                        "project_title": p.title,
                        "uploaded_at": p.updated_at.isoformat() if p.updated_at else (
                            p.created_at.isoformat() if p.created_at else None
                        ),
                        "source": "oneclick" if cfg.get("__oneclick__") else "preset",
                    }
                    break
        return result
    finally:
        db.close()


@router.get("/videos")
async def list_videos(
    project_id: Optional[str] = Query(default=None),
    query: Optional[str] = Query(default=None),
    page_token: Optional[str] = Query(default=None),
    max_results: int = Query(default=25, ge=1, le=50),
):
    """내 채널 영상 목록 (status/statistics/duration 보강됨).

    v1.1.51: 각 영상에 LongTube 프로젝트 매칭 정보 추가
    (longtube.source = "oneclick" | "preset" | null).
    """
    up = _uploader(project_id)
    _require_auth(up)
    try:
        data = await asyncio.to_thread(
            up.list_my_videos,
            max_results=max_results,
            page_token=page_token,
            query=query,
        )
    except Exception as e:
        raise _wrap_errors(e)

    # LongTube 프로젝트 매칭
    items = data.get("items") or []
    video_ids = [v["video_id"] for v in items if v.get("video_id")]
    matches = _match_longtube_projects(video_ids)

    for v in items:
        vid = v.get("video_id", "")
        v["longtube"] = matches.get(vid)  # None 이면 LongTube 외부 업로드

    return data


@router.get("/videos/{video_id}")
async def get_video(video_id: str, project_id: Optional[str] = Query(default=None)):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(up.get_video, video_id)
    except Exception as e:
        raise _wrap_errors(e)


@router.patch("/videos/{video_id}")
async def update_video(
    video_id: str,
    body: VideoUpdateRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(
            up.update_video,
            video_id,
            title=body.title,
            description=body.description,
            tags=body.tags,
            category_id=body.category_id,
            default_language=body.default_language,
            privacy_status=body.privacy_status,
            publish_at=body.publish_at,
            made_for_kids=body.made_for_kids,
            embeddable=body.embeddable,
            public_stats_viewable=body.public_stats_viewable,
        )
    except Exception as e:
        raise _wrap_errors(e)


@router.post("/videos/{video_id}/thumbnail")
async def set_video_thumbnail(
    video_id: str,
    file: UploadFile = File(...),
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)

    suffix = Path(file.filename or "thumb.png").suffix.lower() or ".png"
    if suffix not in (".png", ".jpg", ".jpeg", ".webp"):
        raise HTTPException(400, f"지원하지 않는 썸네일 포맷: {suffix}")

    tmp_dir = Path(tempfile.gettempdir()) / "longtube_studio_thumbs"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4().hex}{suffix}"
    try:
        with tmp_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        return await asyncio.to_thread(up.set_thumbnail, video_id, str(tmp_path))
    except Exception as e:
        raise _wrap_errors(e)
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@router.delete("/videos/{video_id}")
async def delete_video(
    video_id: str,
    confirm: bool = Query(default=False),
    project_id: Optional[str] = Query(default=None),
):
    """영상 삭제. 복구 불가 — `confirm=true` 필수."""
    if not confirm:
        raise HTTPException(
            400,
            "영상 삭제는 복구 불가입니다. confirm=true 쿼리 파라미터가 반드시 필요합니다.",
        )
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(up.delete_video, video_id)
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "deleted", "video_id": video_id}


# ---------- Direct upload ----------


@router.post("/upload")
async def direct_upload(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy_status: Literal["private", "unlisted", "public"] = Form("private"),
    category_id: Optional[str] = Form(None),
    default_language: Optional[str] = Form(None),
    made_for_kids: bool = Form(False),
    publish_at: Optional[str] = Form(None),
    thumbnail: Optional[UploadFile] = File(None),
    project_id: Optional[str] = Query(default=None),
):
    """LongTube 파이프라인을 거치지 않고 바로 업로드.

    `tags` 는 콤마로 구분된 문자열 (프론트에서 form-data 로 묶기 편하게).
    `publish_at` 이 있으면 업로드 직후 `update_video` 로 예약 발행을 겁니다.
    썸네일을 같이 보내면 업로드 성공 후 바로 등록합니다.

    큰 파일은 메모리에 다 올리지 않고 디스크로 흘려보낸 뒤 resumable 업로드.
    """
    if privacy_status not in VALID_PRIVACY:
        raise HTTPException(400, f"privacy_status 값이 유효하지 않습니다: {privacy_status!r}")

    up = _uploader(project_id)
    _require_auth(up)

    # 업로드 파일을 임시 디스크로 flush (메모리 폭탄 방지)
    orig_name = Path(file.filename or "upload.mp4").name
    suffix = Path(orig_name).suffix.lower() or ".mp4"
    if suffix not in (".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"):
        raise HTTPException(400, f"지원하지 않는 영상 포맷: {suffix}")

    tmp_dir = Path(tempfile.gettempdir()) / "longtube_studio_uploads"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    video_tmp = tmp_dir / f"{uuid.uuid4().hex}{suffix}"

    thumb_tmp: Optional[Path] = None
    try:
        with video_tmp.open("wb") as out:
            shutil.copyfileobj(file.file, out, length=1024 * 1024)

        if thumbnail is not None:
            t_suffix = Path(thumbnail.filename or "thumb.png").suffix.lower() or ".png"
            if t_suffix not in (".png", ".jpg", ".jpeg", ".webp"):
                raise HTTPException(400, f"지원하지 않는 썸네일 포맷: {t_suffix}")
            thumb_tmp = tmp_dir / f"{uuid.uuid4().hex}{t_suffix}"
            with thumb_tmp.open("wb") as tf:
                shutil.copyfileobj(thumbnail.file, tf, length=1024 * 1024)

        tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]

        upload_result = await asyncio.to_thread(
            up.upload,
            str(video_tmp),
            title,
            description or "",
            tag_list,
            str(thumb_tmp) if thumb_tmp else None,
            privacy_status,
            default_language,
            category_id,
            bool(made_for_kids),
            None,  # progress_callback — 직접 업로드는 polling 없이 동기 응답
        )
    except Exception as e:
        raise _wrap_errors(e)
    finally:
        try:
            video_tmp.unlink(missing_ok=True)
        except Exception:
            pass
        if thumb_tmp:
            try:
                thumb_tmp.unlink(missing_ok=True)
            except Exception:
                pass

    # 예약 발행: upload 는 privacy_status 를 이미 설정했지만 publish_at 은
    # videos.insert 의 status 가 아니라 update 로만 설정 가능 — 별도 호출.
    if publish_at:
        try:
            await asyncio.to_thread(
                up.update_video,
                upload_result["video_id"],
                privacy_status="private",
                publish_at=publish_at,
            )
            upload_result["publish_at"] = publish_at
        except Exception as e:
            # 업로드는 성공했으니 fail-soft — 에러만 응답에 기록
            upload_result["publish_at_error"] = str(e)

    return upload_result


# ---------- Playlists ----------


@router.get("/playlists")
async def list_playlists(project_id: Optional[str] = Query(default=None)):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        items = await asyncio.to_thread(up.list_playlists)
        return {"items": items}
    except Exception as e:
        raise _wrap_errors(e)


@router.post("/playlists")
async def create_playlist(
    body: PlaylistCreateRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(
            up.create_playlist,
            body.title,
            body.description,
            body.privacy_status,
        )
    except Exception as e:
        raise _wrap_errors(e)


@router.patch("/playlists/{playlist_id}")
async def update_playlist(
    playlist_id: str,
    body: PlaylistUpdateRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(
            up.update_playlist,
            playlist_id,
            title=body.title,
            description=body.description,
            privacy_status=body.privacy_status,
        )
    except Exception as e:
        raise _wrap_errors(e)


@router.delete("/playlists/{playlist_id}")
async def delete_playlist(
    playlist_id: str,
    confirm: bool = Query(default=False),
    project_id: Optional[str] = Query(default=None),
):
    if not confirm:
        raise HTTPException(400, "재생목록 삭제는 confirm=true 가 필요합니다.")
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(up.delete_playlist, playlist_id)
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "deleted", "playlist_id": playlist_id}


@router.get("/playlists/{playlist_id}/items")
async def list_playlist_items(
    playlist_id: str,
    page_token: Optional[str] = Query(default=None),
    max_results: int = Query(default=50, ge=1, le=50),
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(
            up.list_playlist_items,
            playlist_id,
            max_results=max_results,
            page_token=page_token,
        )
    except Exception as e:
        raise _wrap_errors(e)


@router.post("/playlists/{playlist_id}/items")
async def add_playlist_item(
    playlist_id: str,
    body: PlaylistAddItemRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(up.add_to_playlist, playlist_id, body.video_id)
    except Exception as e:
        raise _wrap_errors(e)


@router.delete("/playlists/{playlist_id}/items/{item_id}")
async def remove_playlist_item(
    playlist_id: str,  # URL 식별성만 위해 받음
    item_id: str,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(up.remove_from_playlist, item_id)
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "removed", "item_id": item_id}


# ---------- Comments ----------


@router.get("/videos/{video_id}/comments")
async def list_video_comments(
    video_id: str,
    order: Literal["time", "relevance"] = Query(default="time"),
    page_token: Optional[str] = Query(default=None),
    max_results: int = Query(default=50, ge=1, le=100),
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(
            up.list_comment_threads,
            video_id,
            max_results=max_results,
            page_token=page_token,
            order=order,
        )
    except Exception as e:
        raise _wrap_errors(e)


@router.post("/comments/{parent_id}/reply")
async def reply_comment(
    parent_id: str,
    body: CommentReplyRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        return await asyncio.to_thread(up.reply_to_comment, parent_id, body.text)
    except Exception as e:
        raise _wrap_errors(e)


@router.post("/comments/{comment_id}/moderation")
async def moderate_comment(
    comment_id: str,
    body: CommentModerationRequest,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(
            up.set_comment_moderation,
            comment_id,
            body.status,
            body.ban_author,
        )
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "ok", "comment_id": comment_id, "moderation": body.status}


@router.post("/comments/{comment_id}/spam")
async def mark_comment_spam(
    comment_id: str,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(up.mark_comment_as_spam, comment_id)
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "spammed", "comment_id": comment_id}


@router.delete("/comments/{comment_id}")
async def delete_comment(
    comment_id: str,
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        await asyncio.to_thread(up.delete_comment, comment_id)
    except Exception as e:
        raise _wrap_errors(e)
    return {"status": "deleted", "comment_id": comment_id}


# ---------- Categories ----------


@router.get("/categories")
async def list_categories(
    region_code: str = Query(default="KR"),
    project_id: Optional[str] = Query(default=None),
):
    up = _uploader(project_id)
    _require_auth(up)
    try:
        items = await asyncio.to_thread(up.list_video_categories, region_code)
        return {"items": items, "region_code": region_code}
    except Exception as e:
        raise _wrap_errors(e)
