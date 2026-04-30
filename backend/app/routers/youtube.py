"""YouTube 업로드 + 썸네일 라우터.

주요 엔드포인트:
- GET  /api/youtube/auth/status         : 현재 token.json 유효성 체크
- POST /api/youtube/auth                : OAuth 로컬 서버 플로우 트리거 (브라우저 팝업)
- POST /api/youtube/{project_id}/thumbnail : 썸네일 생성 (첫 컷 이미지 + 제목 오버레이)
- GET  /api/youtube/{project_id}/thumbnail : 생성된 썸네일 파일 다운로드
- POST /api/youtube/{project_id}/upload : 영상 업로드 (async, to_thread 로 sync 서비스 감쌈)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import DATA_DIR, resolve_project_dir
from app.services.youtube_service import (
    YouTubeUploader,
    YouTubeAuthError,
    YouTubeUploadError,
    VALID_PRIVACY,
)
from app.services.thumbnail_service import (
    generate_thumbnail,
    generate_ai_thumbnail,
    ThumbnailError,
    extract_thumbnail_text_parts,
    normalize_episode_label,
)
from app.services.image.factory import resolve_image_model
from app.services.llm.factory import get_llm_service
from app.services.llm.base import BaseLLMService

router = APIRouter()


# ---------- Schemas ----------


class TagRecommendRequest(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    max_tags: int = 15
    language: Optional[str] = None  # None 이면 자동 감지 → config → "ko"


class MetadataRecommendRequest(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    max_tags: int = 15
    language: Optional[str] = None
    episode_number: Optional[int] = Field(
        default=None,
        description=(
            "시리즈 에피소드 번호. 주어지면 LLM 이 짧은 hook 만 쓰고, "
            "backend 는 최종 title 을 'EP. N - {hook}' 으로 조립합니다."
        ),
    )


class YouTubeUploadRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    privacy: Literal["private", "unlisted", "public"] = "private"
    language: Optional[str] = "ko"
    category_id: Optional[str] = None
    made_for_kids: bool = False
    use_generated_thumbnail: bool = True


class YouTubeDeleteRequest(BaseModel):
    video_id: Optional[str] = Field(
        default=None,
        description=(
            "삭제할 YouTube video id. 생략하면 project.youtube_url 에서 파싱해 사용합니다."
        ),
    )
    confirm: bool = Field(
        default=False,
        description=(
            "**복구 불가능** 한 작업이므로 반드시 true 여야 삭제가 실행됩니다. "
            "프론트엔드는 사용자에게 확인 다이얼로그를 띄운 뒤에만 true 로 보내야 합니다."
        ),
    )
    clear_project_url: bool = Field(
        default=True,
        description=(
            "삭제 성공 시 project.youtube_url 을 비울지 여부. true 면 프로젝트가 "
            "다시 '업로드 대기' 상태로 돌아갑니다."
        ),
    )


class ThumbnailGenerateRequest(BaseModel):
    title: Optional[str] = Field(
        default=None,
        description="썸네일 메인 후크 텍스트. 없으면 project.title 사용.",
    )
    subtitle: Optional[str] = Field(
        default=None,
        description="메인 후크 위에 들어가는 보조 라인. 없으면 생략.",
    )
    episode_label: Optional[str] = Field(
        default=None,
        description="좌상단 에피소드 배지 텍스트 (예: 'EP. 1', '#8-2'). 없으면 배지 생략.",
    )
    cut_number: Optional[int] = Field(
        default=None,
        description="`cut_overlay` 모드에서 베이스로 쓸 컷 번호. 없으면 첫 번째 이미지가 있는 컷.",
    )
    mode: Literal["ai_overlay", "ai_only", "cut_overlay"] = Field(
        default="ai_overlay",
        description=(
            "ai_overlay (기본): AI 이미지 생성 + 제목 텍스트 오버레이. "
            "ai_only: AI 이미지만, 텍스트 없음. "
            "cut_overlay: 첫 컷 이미지 + 텍스트 오버레이 (AI 호출 없음)."
        ),
    )
    image_model: Optional[str] = Field(
        default=None,
        description="override image 모델 ID. 없으면 project.config.image_model 사용.",
    )
    prompt: Optional[str] = Field(
        default=None,
        description="override image 프롬프트. 없으면 LLM 으로 자동 생성.",
    )


# ---------- 경로 헬퍼 ----------


def _final_video_path(project_id: str) -> Optional[Path]:
    """업로드 소스 결정.

    우선순위:
      1. 간지(오프닝/인터미션/엔딩) 포함 영상 (`final_with_interludes.mp4`)
      2. 자막 번인 영상 (`final_with_subtitles.mp4`)
      3. 컷 병합 영상 (`merged.mp4`)
    """
    output_dir = resolve_project_dir(project_id) / "output"
    with_interludes = output_dir / "final_with_interludes.mp4"
    if with_interludes.exists():
        return with_interludes
    with_subs = output_dir / "final_with_subtitles.mp4"
    if with_subs.exists():
        return with_subs
    merged = resolve_project_dir(project_id) / "videos" / "merged.mp4"
    if merged.exists():
        return merged
    return None


def _thumbnail_path(project_id: str) -> Path:
    return resolve_project_dir(project_id) / "output" / "thumbnail.png"


def _extract_video_id(url_or_id: Optional[str]) -> Optional[str]:
    """YouTube URL 또는 bare video id 에서 11자리 video id 를 추출.

    허용 포맷:
    - https://youtube.com/watch?v=<id>
    - https://www.youtube.com/watch?v=<id>&...
    - https://youtu.be/<id>
    - https://www.youtube.com/shorts/<id>
    - <id>  (이미 11자리면 그대로)
    """
    if not url_or_id:
        return None
    s = str(url_or_id).strip()
    if not s:
        return None
    # bare video id (대부분 11자, 영문+숫자+-_)
    import re
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)
    return None


def _resolve_cut_image(project_id: str, image_path: Optional[str]) -> Optional[str]:
    """DB 에 저장된 image_path 를 절대 경로로 해석.

    - None/빈 문자열이면 None
    - 이미 절대 경로면 그대로
    - 상대 경로면 DATA_DIR/{project_id}/{image_path} 로 해석
    - 파일이 실제로 존재하는 경우에만 반환, 아니면 None
    """
    if not image_path:
        return None
    p = Path(image_path)
    if not p.is_absolute():
        p = resolve_project_dir(project_id) / image_path
    if p.exists():
        return str(p)
    return None


def _pick_base_cut(project_id: str, db: Session, cut_number: Optional[int]) -> Optional[str]:
    """썸네일 베이스로 쓸 컷 이미지 경로를 결정. 항상 절대 경로 반환."""
    q = db.query(Cut).filter(Cut.project_id == project_id)
    if cut_number is not None:
        cut = q.filter(Cut.cut_number == cut_number).first()
        if cut:
            resolved = _resolve_cut_image(project_id, cut.image_path)
            if resolved:
                return resolved
    # 자동 선택: image_path 가 있고 파일이 실제 존재하는 가장 이른 컷
    for cut in q.order_by(Cut.cut_number.asc()).all():
        resolved = _resolve_cut_image(project_id, cut.image_path)
        if resolved:
            return resolved
    return None


# ---------- OAuth 엔드포인트 (legacy: 전역 토큰) ----------


@router.get("/auth/status")
def auth_status():
    """전역 token.json 이 있고 유효한지 체크. 브라우저 팝업 없음.

    v1.1.25 부터는 프로젝트별 인증(`/{project_id}/auth/...`) 사용을 권장합니다.
    """
    uploader = YouTubeUploader()
    return {"authenticated": uploader.is_authenticated()}


@router.post("/auth")
async def start_oauth_flow():
    """OAuth 로컬 서버 플로우 (legacy 전역 토큰).

    `flow.run_local_server()` 는 블로킹이고 localhost:8090 을 잠깐 연 뒤
    브라우저 팝업을 띄웁니다. FastAPI 이벤트 루프가 막히지 않도록
    `asyncio.to_thread` 로 감쌉니다. 최초 1회만 호출하면 됩니다.
    """
    try:
        uploader = YouTubeUploader()
        await asyncio.to_thread(uploader.authenticate)
        return {
            "status": "authenticated",
            "message": "YouTube OAuth 인증 완료. 이제 영상을 업로드할 수 있습니다.",
        }
    except YouTubeAuthError as e:
        raise HTTPException(500, f"OAuth 인증 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 OAuth 오류: {e}")


@router.get("/auth/channel")
async def get_auth_channel():
    """현재 인증된 Google 계정에 연결된 YouTube 채널 정보 조회 (legacy 전역 토큰).

    업로드 전에 "어느 채널로 올라가는지" 프론트에서 보여주기 위해 사용합니다.
    """
    uploader = YouTubeUploader()
    if not uploader.is_authenticated():
        raise HTTPException(401, "YouTube 인증이 필요합니다. /auth 먼저 호출하세요.")
    try:
        info = await asyncio.to_thread(uploader.get_channel_info)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"채널 정보 조회 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 채널 조회 오류: {e}")
    return info


@router.post("/auth/reset")
async def reset_auth():
    """저장된 전역 token.json 삭제. 다음 /auth 호출 시 계정 선택 팝업이 다시 뜹니다.

    "다른 계정으로 로그인" 플로우용 (legacy 전역 토큰).
    """
    try:
        uploader = YouTubeUploader()
        removed = await asyncio.to_thread(uploader.logout)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"인증 초기화 실패: {e}")
    return {"status": "reset", "token_removed": removed}


# ---------- OAuth 엔드포인트 (채널별 토큰: 딸깍 CH1~CH4) ----------


def _validate_channel(ch: int) -> int:
    if ch not in (1, 2, 3, 4):
        raise HTTPException(400, "channel 은 1~4 만 허용됩니다.")
    return ch


def _project_channel_id(project: Project) -> Optional[int]:
    cfg = project.config or {}
    raw = cfg.get("youtube_channel", cfg.get("channel"))
    try:
        ch = int(raw)
    except (TypeError, ValueError):
        return None
    return ch if ch in (1, 2, 3, 4) else None


def _uploader_for_project(project: Project) -> YouTubeUploader:
    ch = _project_channel_id(project)
    if ch is not None:
        return YouTubeUploader(channel_id=ch)

    project_uploader = YouTubeUploader(project_id=project.id)
    if project_uploader.is_authenticated():
        return project_uploader
    return YouTubeUploader()


@router.get("/auth/channel/{ch}/status")
def channel_auth_status(ch: int):
    """채널별 token 유효성 체크. 브라우저 팝업 없음."""
    _validate_channel(ch)
    uploader = YouTubeUploader(channel_id=ch)
    return {"channel": ch, "authenticated": uploader.is_authenticated()}


@router.post("/auth/channel/{ch}")
async def channel_start_oauth_flow(ch: int):
    """채널별 OAuth 로컬 서버 플로우.

    `BASE_DIR/token_ch{N}.json` 에 토큰을 저장한다. 브라우저 팝업이 뜨고
    사용자가 해당 채널 계정으로 로그인해야 한다.
    """
    _validate_channel(ch)
    try:
        uploader = YouTubeUploader(channel_id=ch)
        await asyncio.to_thread(uploader.authenticate)
        return {
            "status": "authenticated",
            "channel": ch,
            "message": f"CH{ch} YouTube OAuth 인증 완료.",
        }
    except YouTubeAuthError as e:
        raise HTTPException(500, f"OAuth 인증 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 OAuth 오류: {e}")


@router.get("/auth/channel/{ch}/info")
async def channel_get_auth_channel(ch: int):
    """채널별 인증 계정의 YouTube 채널 정보 조회."""
    _validate_channel(ch)
    uploader = YouTubeUploader(channel_id=ch)
    if not uploader.is_authenticated():
        raise HTTPException(
            401,
            f"CH{ch} YouTube 인증이 필요합니다. /auth/channel/{ch} 먼저 호출하세요.",
        )
    try:
        info = await asyncio.to_thread(uploader.get_channel_info)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"채널 정보 조회 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 채널 조회 오류: {e}")
    info["channel"] = ch
    return info


@router.post("/auth/channel/{ch}/reset")
async def channel_reset_auth(ch: int):
    """채널별 token 삭제. 다음 인증 시 계정 선택 팝업이 뜬다."""
    _validate_channel(ch)
    try:
        uploader = YouTubeUploader(channel_id=ch)
        removed = await asyncio.to_thread(uploader.logout)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"인증 초기화 실패: {e}")
    return {"status": "reset", "channel": ch, "token_removed": removed}


# ---------- OAuth 엔드포인트 (프로젝트별 토큰) ----------


@router.get("/{project_id}/auth/status")
def project_auth_status(project_id: str, db: Session = Depends(get_db)):
    """프로젝트별 YouTube 토큰이 있고 유효한지 체크.

    전역 토큰은 fallback 으로 같이 보고합니다. 프로젝트 토큰이 있으면
    `authenticated=true`, 없으면 `false`. 전역 토큰만 있는 상태는
    `global_authenticated=true` 로 별도 표시.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    project_uploader = YouTubeUploader(project_id=project_id)
    global_uploader = YouTubeUploader()
    return {
        "project_id": project_id,
        "authenticated": project_uploader.is_authenticated(),
        "global_authenticated": global_uploader.is_authenticated(),
    }


@router.post("/{project_id}/auth")
async def project_start_oauth_flow(project_id: str, db: Session = Depends(get_db)):
    """프로젝트별 OAuth 로컬 서버 플로우.

    `DATA_DIR/{project_id}/youtube_token.json` 에 토큰을 저장합니다.
    프로젝트마다 다른 YouTube 계정을 연결할 수 있습니다.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        uploader = YouTubeUploader(project_id=project_id)
        await asyncio.to_thread(uploader.authenticate)
        return {
            "status": "authenticated",
            "project_id": project_id,
            "message": f"프로젝트 {project_id} 의 YouTube OAuth 인증 완료.",
        }
    except YouTubeAuthError as e:
        raise HTTPException(500, f"OAuth 인증 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 OAuth 오류: {e}")


@router.get("/{project_id}/auth/channel")
async def project_get_auth_channel(project_id: str, db: Session = Depends(get_db)):
    """프로젝트별 인증 계정의 YouTube 채널 정보 조회."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    uploader = YouTubeUploader(project_id=project_id)
    if not uploader.is_authenticated():
        raise HTTPException(
            401,
            f"프로젝트 {project_id} 의 YouTube 인증이 필요합니다. /{project_id}/auth 먼저 호출하세요.",
        )
    try:
        info = await asyncio.to_thread(uploader.get_channel_info)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"채널 정보 조회 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 채널 조회 오류: {e}")
    return info


@router.post("/{project_id}/auth/reset")
async def project_reset_auth(project_id: str, db: Session = Depends(get_db)):
    """프로젝트별 token.json 삭제. 다음 /{project_id}/auth 호출 시 계정 선택 팝업이 다시 뜹니다."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    try:
        uploader = YouTubeUploader(project_id=project_id)
        removed = await asyncio.to_thread(uploader.logout)
    except YouTubeAuthError as e:
        raise HTTPException(500, f"인증 초기화 실패: {e}")
    return {"status": "reset", "project_id": project_id, "token_removed": removed}


# ---------- 썸네일 엔드포인트 ----------


@router.post("/{project_id}/thumbnail")
async def create_thumbnail(
    project_id: str,
    body: ThumbnailGenerateRequest,
    db: Session = Depends(get_db),
):
    """썸네일 생성. mode 에 따라 3가지 경로 중 하나:

    - **ai_overlay** (default): image 모델(Nano Banana / DALL-E / Flux 등) 로 1280x720
      배경을 새로 생성 → Pillow 로 제목 텍스트 오버레이 합성.
    - **ai_only**: image 모델로 1280x720 생성, 텍스트 없음. 썸네일에 텍스트를
      직접 넣고 싶지 않거나 image 모델이 자체적으로 타이포를 넣는 경우.
    - **cut_overlay**: 기존 결정론적 경로. 첫 번째 컷 이미지 + Pillow 텍스트.
      AI 호출 없이 무료.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # body.title (프론트 thumbMainHook) 이 반드시 와야 한다. project.title 로는
    # 절대 폴백하지 않는다 — 그게 채널명으로 잘못 잡힌 과거 사례 때문.
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(
            400,
            "썸네일 메인 후크 텍스트가 비어있습니다. 프론트에서 직접 입력하거나 'AI 전체 추천' 을 먼저 누르세요.",
        )
    subtitle = (body.subtitle or "").strip() or None
    title, extracted_episode_label = extract_thumbnail_text_parts(title, body.episode_label)
    episode_label = normalize_episode_label(body.episode_label) or extracted_episode_label
    config = project.config or {}
    asset_url = f"/assets/{project_id}/output/thumbnail.png"

    # ─── 모드 1: cut_overlay (AI 호출 없음) ───
    if body.mode == "cut_overlay":
        base_image = _pick_base_cut(project_id, db, body.cut_number)
        try:
            saved = generate_thumbnail(
                project_id=project_id,
                title=title,
                base_image_path=base_image,
                episode_label=episode_label,
                subtitle=subtitle,
            )
        except ThumbnailError as e:
            raise HTTPException(500, f"썸네일 생성 실패: {e}")
        return {
            "status": "generated",
            "project_id": project_id,
            "thumbnail_path": saved,
            "thumbnail_url": asset_url,
            "mode": "cut_overlay",
            "title": title,
            "subtitle": subtitle,
            "episode_label": episode_label,
            "base_image_used": base_image,
        }

    # ─── 모드 2/3: AI 기반 ───
    # image 모델 결정
    image_model_id = resolve_image_model(
        body.image_model or config.get("image_model")
    )

    # 프롬프트 결정 (사용자 override → LLM → 템플릿 폴백)
    image_prompt = (body.prompt or "").strip() or None
    prompt_source = "user" if image_prompt else "llm"
    narration_snippet = _collect_narration(db, project_id, limit=1500)
    language = _resolve_language(None, config, narration_snippet)

    # 썸네일에는 반드시 메인 캐릭터가 포함되도록 character_description 을 추출해서 전달.
    # 캐릭터 정보는 (1) config.character_description 전용 필드 > (2) image_global_prompt 순으로 찾음.
    character_description = (
        (config.get("character_description") or "").strip()
        or (config.get("image_global_prompt") or "").strip()
    )

    if image_prompt is None:
        llm_model_id = config.get("script_model") or "claude-sonnet-4-6"
        try:
            llm = get_llm_service(llm_model_id)
            image_prompt = await llm.generate_thumbnail_image_prompt(
                title=title,
                topic=(project.topic or "").strip(),
                narration=narration_snippet,
                language=language,
                character_description=character_description,
            )
        except Exception:
            image_prompt = None
        if not image_prompt:
            prompt_source = "template"
            image_prompt = BaseLLMService._fallback_thumbnail_prompt(
                title,
                (project.topic or "").strip(),
                language,
                character_description,
            )

    overlay_text = title if body.mode == "ai_overlay" else None

    # 레퍼런스 + 캐릭터 이미지 경로 수집 — 이미지 모델이 스타일을 따라가도록
    # 프로젝트 설정에 등록된 레퍼런스 이미지를 썸네일 생성에도 그대로 넘김.
    # 캐릭터 이미지를 우선으로 (메인 주인공) 넣고, 그 뒤에 스타일 레퍼런스.
    project_dir = resolve_project_dir(project_id)

    def _resolve_asset_list(rels) -> list[str]:
        out: list[str] = []
        for rel in (rels or []):
            if not rel:
                continue
            p = Path(rel)
            abs_p = p if p.is_absolute() else project_dir / rel
            if abs_p.exists() and abs_p.is_file():
                out.append(str(abs_p))
        return out

    char_image_paths = _resolve_asset_list(config.get("character_images"))
    ref_image_paths = _resolve_asset_list(config.get("reference_images"))
    # 중복 제거하면서 순서 유지 — 캐릭터 먼저, 그 뒤 스타일 레퍼런스
    seen: set[str] = set()
    combined_refs: list[str] = []
    for p in [*char_image_paths, *ref_image_paths]:
        if p not in seen:
            seen.add(p)
            combined_refs.append(p)

    # 설정에 등록은 됐는데 디스크에서 못 찾은 경로 — 진단용.
    registered_ref_count = len(config.get("reference_images") or [])
    registered_char_count = len(config.get("character_images") or [])
    missing_refs = max(0, registered_ref_count - len(ref_image_paths))
    missing_chars = max(0, registered_char_count - len(char_image_paths))

    # v1.2.20: 폴백 제거. 사용자 요구 — "API 이용할 때 설정된 모델의 API 연결
    # 안되있을때 알림창 띄우고 풀백으로 처리하지마." ComfyUI 로컬 모델만 레퍼런스
    # 무시(GPU 비용 0). API 모델이 레퍼런스 미지원이면 명시적 HTTPException.
    ref_fallback_reason = None
    if combined_refs:
        from app.services.image.factory import get_image_service, IMAGE_REGISTRY as _IMG_REG
        try:
            _probe = get_image_service(image_model_id)
            _supports = getattr(_probe, "supports_reference_images", False)
        except Exception:
            _probe = None
            _supports = True  # 프로브 자체 실패면 일단 진행
        if _probe is not None and not _supports:
            if _IMG_REG.get(image_model_id, {}).get("provider") == "comfyui":
                ref_fallback_reason = (
                    f"{image_model_id} 는 레퍼런스 미지원이지만 로컬 GPU 모델 → 레퍼런스 무시"
                )
                combined_refs = []
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"선택한 이미지 모델 '{image_model_id}' 은(는) 레퍼런스 이미지를 "
                           f"지원하지 않습니다. 폴백 비활성화 — 모델을 nano-banana 계열로 "
                           f"바꾸거나 레퍼런스를 제거하세요.",
                )

    # v1.1.55: 공통 REFERENCE_STYLE_PREFIX 사용 — 컷/썸네일/재생성 문구 통일.
    # 이미지 모델 서비스 레벨에서도 붙이지만, 서비스에 따라 다르게 붙을 수 있어
    # 여기서도 한 번 더 박는다 (apply_* 가 중복 검사로 이중 부착 방지).
    if combined_refs and image_prompt:
        from app.services.image.prompt_builder import apply_reference_style_prefix
        image_prompt = apply_reference_style_prefix(image_prompt, has_reference=True)

    try:
        result = await generate_ai_thumbnail(
            project_id=project_id,
            image_prompt=image_prompt,
            image_model_id=image_model_id,
            overlay_title_text=overlay_text,
            overlay_subtitle=subtitle if body.mode == "ai_overlay" else None,
            overlay_episode_label=episode_label if body.mode == "ai_overlay" else None,
            reference_images=combined_refs or None,
        )
    except ThumbnailError as e:
        raise HTTPException(500, f"AI 썸네일 생성 실패: {e}")
    except Exception as e:
        raise HTTPException(500, f"예상치 못한 AI 썸네일 오류: {e}")

    return {
        "status": "generated",
        "project_id": project_id,
        "thumbnail_path": result["path"],
        "thumbnail_url": asset_url,
        "mode": body.mode,
        "title": title,
        "subtitle": subtitle,
        "episode_label": episode_label,
        "image_model": result["model"],
        "prompt_used": result["prompt_used"],
        "prompt_source": prompt_source,
        "overlay_applied": result["overlay_applied"],
        "language": language,
        "reference_images_used": len(combined_refs),
        "reference_fallback": ref_fallback_reason,
        # ★ 진단 정보 — 사용자가 "레퍼런스 스타일 안 따라감" 을 신고했을 때
        # 프론트가 이 값을 보고 원인을 즉시 안내할 수 있게 내려준다.
        "reference_diagnostics": {
            "registered_reference_images": registered_ref_count,
            "registered_character_images": registered_char_count,
            "resolved_reference_images": len(ref_image_paths),
            "resolved_character_images": len(char_image_paths),
            "missing_reference_images": missing_refs,
            "missing_character_images": missing_chars,
            "sent_to_model": len(combined_refs),
        },
    }


@router.get("/{project_id}/thumbnail")
def get_thumbnail(project_id: str):
    """생성된 썸네일 파일 다운로드."""
    path = _thumbnail_path(project_id)
    if not path.exists():
        raise HTTPException(404, "썸네일이 아직 생성되지 않았습니다.")
    return FileResponse(str(path), media_type="image/png", filename="thumbnail.png")


# ---------- 태그 / 메타데이터 추천 엔드포인트 ----------


def _detect_language(text: str, fallback: str = "ko") -> str:
    """한글/가나/CJK/라틴 문자 개수를 세서 주 언어 코드 반환.

    - 히라가나/가타카나가 어느 정도 있으면 무조건 ja (일본어는 CJK 와 혼용하므로 먼저 체크)
    - 그 외엔 한글 > CJK > 라틴 알파벳 중 최다
    - 표본 부족 시 fallback 반환
    """
    if not text:
        return fallback
    hangul = 0
    kana = 0
    cjk = 0
    latin = 0
    for c in text:
        o = ord(c)
        if 0xAC00 <= o <= 0xD7A3:
            hangul += 1
        elif 0x3040 <= o <= 0x30FF:
            kana += 1
        elif 0x4E00 <= o <= 0x9FFF:
            cjk += 1
        elif (0x41 <= o <= 0x5A) or (0x61 <= o <= 0x7A):
            latin += 1

    if kana >= 10:
        return "ja"
    counts = {"ko": hangul, "zh": cjk, "en": latin}
    best = max(counts, key=counts.get)
    if counts[best] < 10:
        return fallback
    return best


def _resolve_language(
    requested: Optional[str],
    project_config: Optional[dict],
    narration: str,
) -> str:
    """요청값 > 나레이션 자동 감지 > project.config.language > 'ko' 순."""
    if requested:
        return requested
    auto = _detect_language(narration, fallback="")
    if auto:
        return auto
    if project_config:
        cfg_lang = project_config.get("language")
        if cfg_lang:
            return cfg_lang
    return "ko"


def _collect_narration(db: Session, project_id: str, limit: int = 2500) -> str:
    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number.asc())
        .all()
    )
    joined = " ".join((c.narration or "").strip() for c in cuts if c.narration)
    return joined[:limit]


def _clean_tag_list(tags: list, max_tags: int) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for t in tags or []:
        if not isinstance(t, str):
            continue
        t = t.strip().lstrip("#").strip()
        if not t or len(t) > 30:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(t)
        if len(cleaned) >= max_tags:
            break
    return cleaned


@router.post("/{project_id}/tags/recommend")
async def recommend_tags(
    project_id: str,
    body: TagRecommendRequest,
    db: Session = Depends(get_db),
):
    """프로젝트 정보를 기반으로 태그만 생성. 대사 언어를 따라갑니다.

    - `language` 가 명시되지 않으면 나레이션 문자로 자동 감지.
    - LLM 호출 실패 시 제목/주제/나레이션 키워드 휴리스틱 폴백.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    title = (body.title or project.title or "").strip()
    topic = (body.topic or project.topic or "").strip()
    narration_snippet = _collect_narration(db, project_id, limit=1500)
    language = _resolve_language(body.language, project.config or {}, narration_snippet)

    tags: list[str] = []
    source = "llm"
    error: Optional[str] = None
    try:
        config = project.config or {}
        model_id = config.get("script_model") or "claude-sonnet-4-6"
        llm = get_llm_service(model_id)
        if hasattr(llm, "generate_tags"):
            tags = await llm.generate_tags(
                title=title,
                topic=topic,
                narration=narration_snippet,
                max_tags=body.max_tags,
                language=language,
            )
    except Exception as e:
        error = str(e)
        tags = []

    if not tags:
        source = "heuristic"
        tags = _heuristic_tags(title, topic, narration_snippet, body.max_tags)

    return {
        "tags": _clean_tag_list(tags, body.max_tags),
        "source": source,
        "language": language,
        "error": error,
    }


@router.post("/{project_id}/metadata/recommend")
async def recommend_metadata(
    project_id: str,
    body: MetadataRecommendRequest,
    db: Session = Depends(get_db),
):
    """title / description / tags 를 한 번에 생성. 모든 필드가 대사 언어로 통일됩니다.

    - 언어는 `body.language` > 나레이션 자동 감지 > `config.language` > "ko" 순
    - description 은 LLM 이 600~1500 자 범위로 hook + 요약 + 하이라이트 + 마무리 구조로 작성
    - LLM 호출 전체 실패 시: title 은 원본 유지, description 은 topic 폴백,
      tags 는 휴리스틱 폴백을 사용합니다.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    title_hint = (body.title or project.title or "").strip()
    topic = (body.topic or project.topic or "").strip()
    narration_snippet = _collect_narration(db, project_id, limit=2500)
    language = _resolve_language(body.language, project.config or {}, narration_snippet)

    result: dict = {}
    error: Optional[str] = None
    source = "llm"
    try:
        config = project.config or {}
        model_id = config.get("script_model") or "claude-sonnet-4-6"
        llm = get_llm_service(model_id)
        if hasattr(llm, "generate_metadata"):
            result = await llm.generate_metadata(
                title=title_hint,
                topic=topic,
                narration=narration_snippet,
                language=language,
                max_tags=body.max_tags,
                episode_number=body.episode_number,
            )
    except Exception as e:
        error = str(e)
        result = {}

    # title_hook 이 있으면 그걸로, 없으면 구버전 title 필드, 그것도 없으면 title_hint
    hook_raw = (result.get("title_hook") or result.get("title") or "").strip()
    # LLM 이 혹시 "EP. N -" 를 스스로 붙여 왔다면 제거
    hook_clean = _strip_episode_prefix(hook_raw)

    if body.episode_number is not None and hook_clean:
        final_title = f"EP. {body.episode_number} - {hook_clean}"
    elif body.episode_number is not None:
        # LLM 이 hook 을 못 줬을 때 폴백: 기존 프로젝트 title 이나 topic 사용
        fallback_hook = _strip_episode_prefix(title_hint or topic or "Untitled")[:48]
        final_title = f"EP. {body.episode_number} - {fallback_hook}"
    else:
        final_title = hook_clean or title_hint or "Untitled"

    final_description = (result.get("description") or "").strip()
    final_tags_raw = result.get("tags") or []

    # description 폴백: LLM 이 비워오면 topic + 나레이션 앞머리로 최소한의 문단 구성
    if not final_description:
        source = "heuristic" if error or not final_tags_raw else "partial"
        seed = topic or narration_snippet[:300]
        final_description = seed
    final_description = final_description[:5000]

    # tags 폴백
    if not final_tags_raw:
        final_tags = _heuristic_tags(final_title, topic, narration_snippet, body.max_tags)
        if source == "llm":
            source = "partial"
    else:
        final_tags = final_tags_raw

    return {
        "title": final_title[:100],
        "title_hook": hook_clean or None,
        "description": final_description,
        "tags": _clean_tag_list(final_tags, body.max_tags),
        "language": language,
        "episode_number": body.episode_number,
        "source": source,
        "error": error,
    }


def _strip_episode_prefix(text: str) -> str:
    """'EP. 1 - ', 'Episode 3: ', '제5화 ' 같은 접두어 제거.

    LLM 이 episode 모드에서 실수로 에피소드 접두어를 붙여 오면 중복을 막기 위해
    제거합니다. 접두어가 없으면 입력을 그대로 반환.
    """
    import re as _re
    t = (text or "").strip()
    if not t:
        return t
    patterns = [
        r"^EP\.?\s*\d+\s*[-–—:·]\s*",
        r"^Episode\s*\d+\s*[-–—:·]\s*",
        r"^에피소드\s*\d+\s*[-–—:·]?\s*",
        r"^제?\s*\d+\s*화\s*[-–—:·]?\s*",
        r"^#\d+(?:-\d+)?\s*[-–—:·]?\s*",
    ]
    for p in patterns:
        new = _re.sub(p, "", t, flags=_re.IGNORECASE)
        if new != t:
            t = new.strip()
            break
    return t


def _heuristic_tags(title: str, topic: str, narration: str, max_tags: int) -> list[str]:
    """LLM 없이 제목/주제/나레이션에서 키워드를 추출하는 단순 폴백.

    한국어 텍스트의 경우 조사/어미까지 섞이므로 완벽한 NLP 는 아니지만,
    최소한의 "내용 관련" 태그는 제공합니다.
    """
    import re as _re
    from collections import Counter

    text = " ".join([title, topic, narration])
    # 한글/영문/숫자만 남기고 토큰 분리 (2글자 이상)
    tokens = _re.findall(r"[가-힣]{2,}|[A-Za-z][A-Za-z0-9]{1,}", text)

    # 너무 흔한 한국어 불용어/조사 포함 단어 거르기
    stop = {
        "그리고", "하지만", "그런데", "그래서", "때문에", "그리하여",
        "이것", "저것", "그것", "우리", "여기", "저기", "거기",
        "있는", "없는", "되는", "하는", "이다", "있다", "없다", "하다",
        "합니다", "입니다", "있습니다", "없습니다", "되었습니다",
        "그리고서", "또한", "매우", "정말", "진짜", "아주",
    }
    filtered = [t for t in tokens if t not in stop]

    # 빈도 상위 추출
    counter = Counter(filtered)
    common = [w for w, _ in counter.most_common(max_tags * 2)]

    # 제목/주제는 무조건 앞쪽에 포함
    seed: list[str] = []
    for s in (title, topic):
        s = s.strip()
        if s and s not in seed:
            seed.append(s)

    out: list[str] = []
    seen: set[str] = set()
    for t in seed + common:
        if len(t) > 30:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
        if len(out) >= max_tags:
            break
    return out


# ---------- 업로드 엔드포인트 ----------


@router.post("/{project_id}/upload")
async def upload_to_youtube(
    project_id: str,
    body: YouTubeUploadRequest,
    db: Session = Depends(get_db),
):
    """최종 영상을 YouTube 에 업로드."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    final_video = _final_video_path(project_id)
    if final_video is None:
        raise HTTPException(
            400,
            "최종 영상이 없습니다. 자막 렌더 또는 merged.mp4 를 먼저 만들어주세요.",
        )

    if body.privacy not in VALID_PRIVACY:
        raise HTTPException(422, f"privacy 는 {sorted(VALID_PRIVACY)} 중 하나여야 합니다.")

    title = (body.title or project.title or "Untitled").strip()
    # v1.1.55-fix: description 폴백 우선순위에 script.json 의 description 추가
    #   body.description > config.youtube_description > script.json description > project.topic
    _cfg_desc = ((project.config or {}).get("youtube_description") or "").strip()
    _script_desc = ""
    if not body.description and not _cfg_desc:
        try:
            import json
            _script_path = resolve_project_dir(project_id) / "script.json"
            if _script_path.exists():
                with open(_script_path, "r", encoding="utf-8") as _sf:
                    _script_data = json.load(_sf)
                _script_desc = (_script_data.get("description") or "").strip()
        except Exception:
            pass
    description = (body.description or _cfg_desc or _script_desc or project.topic or "").strip()

    # 썸네일 경로 결정
    thumb_path: Optional[str] = None
    if body.use_generated_thumbnail:
        tp = _thumbnail_path(project_id)
        if tp.exists():
            thumb_path = str(tp)

    uploader = _uploader_for_project(project)

    # 동기 서비스를 이벤트 루프 블로킹 없이 실행
    try:
        result = await asyncio.to_thread(
            uploader.upload,
            str(final_video),
            title,
            description,
            body.tags or [],
            thumb_path,
            body.privacy,
            body.language,
            body.category_id,
            body.made_for_kids,
            None,  # progress_callback (아직 프론트로 연결 안 함)
        )
    except YouTubeAuthError as e:
        import traceback as _tb
        print(f"[youtube upload] AUTH error: {e}\n{_tb.format_exc()}")
        raise HTTPException(401, f"YouTube 인증이 필요합니다: {e}")
    except YouTubeUploadError as e:
        import traceback as _tb
        print(f"[youtube upload] UPLOAD error: {e}\n{_tb.format_exc()}")
        raise HTTPException(500, f"YouTube 업로드 실패: {e}")
    except Exception as e:
        import traceback as _tb
        print(f"[youtube upload] UNEXPECTED error: {e}\n{_tb.format_exc()}")
        raise HTTPException(500, f"예상치 못한 업로드 오류: {e}")

    video_url = result.get("url")
    if not video_url:
        raise HTTPException(500, f"업로드는 성공했으나 URL 이 비어있습니다: {result!r}")

    # DB 에 YouTube URL 저장
    project.youtube_url = video_url
    db.commit()

    return {
        "status": "uploaded",
        "project_id": project_id,
        "video_id": result.get("video_id"),
        "video_url": video_url,
        "title": title,
        "privacy": body.privacy,
        "thumbnail_used": thumb_path is not None,
        "thumbnail_error": result.get("thumbnail_error"),
    }


@router.delete("/{project_id}/upload")
async def delete_uploaded_video(
    project_id: str,
    body: YouTubeDeleteRequest,
    db: Session = Depends(get_db),
):
    """업로드된 YouTube 영상을 삭제.

    **주의**: 이 작업은 복구 불가능합니다. `confirm=true` 를 반드시 보내야만
    실제로 API 가 실행됩니다. 프론트엔드는 사용자에게 확인 다이얼로그를 띄운
    뒤에만 호출해야 합니다.

    - `video_id` 가 주어지면 그 영상을 삭제
    - 없으면 `project.youtube_url` 에서 video id 를 파싱해서 삭제
    - 성공 시 `clear_project_url=true` (기본값) 면 `project.youtube_url` 을 비움
    """
    if not body.confirm:
        raise HTTPException(
            400,
            "삭제를 실행하려면 confirm=true 를 보내야 합니다. "
            "사용자에게 확인을 받은 뒤 요청을 다시 보내주세요.",
        )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # video_id 결정: 명시적 > project.youtube_url 파싱
    video_id = _extract_video_id(body.video_id) or _extract_video_id(project.youtube_url)
    if not video_id:
        raise HTTPException(
            400,
            "삭제할 video id 를 찾을 수 없습니다. body.video_id 에 영상 ID 또는 "
            "URL 을 직접 넘겨주세요.",
        )

    uploader = _uploader_for_project(project)

    try:
        await asyncio.to_thread(uploader.delete_video, video_id)
    except YouTubeAuthError as e:
        import traceback as _tb
        print(f"[youtube delete] AUTH error: {e}\n{_tb.format_exc()}")
        raise HTTPException(401, f"YouTube 인증이 필요합니다: {e}")
    except YouTubeUploadError as e:
        import traceback as _tb
        print(f"[youtube delete] DELETE error: {e}\n{_tb.format_exc()}")
        # 이미 사라진 영상(404)도 사용자 입장에선 "없앴다" 와 동일하게 받아주는 게 UX 상 낫다.
        msg = str(e)
        if "404" in msg or "videoNotFound" in msg or "not found" in msg.lower():
            if body.clear_project_url:
                project.youtube_url = ""
                db.commit()
            return {
                "status": "already_gone",
                "project_id": project_id,
                "video_id": video_id,
                "message": "YouTube 에서 이미 찾을 수 없는 영상입니다. 프로젝트 링크를 비웠습니다.",
            }
        raise HTTPException(500, f"YouTube 영상 삭제 실패: {e}")
    except Exception as e:
        import traceback as _tb
        print(f"[youtube delete] UNEXPECTED error: {e}\n{_tb.format_exc()}")
        raise HTTPException(500, f"예상치 못한 삭제 오류: {e}")

    if body.clear_project_url:
        project.youtube_url = ""
        db.commit()

    return {
        "status": "deleted",
        "project_id": project_id,
        "video_id": video_id,
        "cleared_project_url": body.clear_project_url,
    }
