"""LongTube 자동화 스케줄러.

v1.1.25 동작 방식:
    - 각 episode 는 `scheduled_time` (HH:MM, 로컬시간) 만 가진다.
    - 실행 순서는 "scheduled_time 오름차순". episode_number 는 식별용.
    - 현재 시각이 어느 row 의 scheduled_time 을 지났고, 그 row 가
      '오늘' 아직 시작되지 않았으면 즉시 실행.
    - 동시에 여러 개 time 이 지나 있다면, 시간 오름차순으로 하나씩 소화.
    - 이미 시작/완료된 row 는 status 가 바뀌었거나 started_at 이 오늘
      날짜이므로 다시 뽑히지 않는다.
    - 사용자가 날짜를 손으로 밀어줄 필요 없이, 주제와 시각만 한 번
      넣어두면 스케줄러가 알아서 각 시각에 파이프라인을 돌린다.

실행 흐름:
    1) 오늘 끝난 게 없고, 지금 시각 >= 가장 이른 pending episode 의
       scheduled_time 이면 그 episode 선택
    2) `template_project_id` 에서 config 복사해 새 Project 생성
    3) _step_script → _step_voice → _step_image → _step_video → _step_subtitle
    4) LLM 으로 title/description/tags 메타데이터 생성
    5) AI 썸네일 생성
    6) YouTubeUploader.upload 호출
    7) episode 상태 업데이트 → 다음 iteration

동시 실행은 `_lock` 으로 막아 한 번에 하나의 episode 만 실행합니다.
(YouTube Data API 일일 쿼터, 로컬 GPU/FFmpeg 동시성 때문)
"""
from __future__ import annotations

import asyncio
import traceback
import uuid
from datetime import datetime, date, time as dtime
from pathlib import Path
from typing import Optional

from sqlalchemy import and_, or_, func as sqlfunc
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.database import SessionLocal
from app.models.project import Project
from app.models.scheduled_episode import ScheduledEpisode

# ─── 전역 상태 ──────────────────────────────────────────────────
# lifespan 에서 start_scheduler() 로 생성, stop_scheduler() 로 취소.
_scheduler_task: Optional[asyncio.Task] = None
_lock = asyncio.Lock()
_stop_event: Optional[asyncio.Event] = None

# 폴링 주기 (초). 너무 짧으면 DB 부하, 너무 길면 예약 시각이 밀림.
POLL_INTERVAL = 30.0


# ─── 헬퍼 ──────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.utcnow()


def _now_local() -> datetime:
    """스케줄러 비교용 로컬 현재시각.

    YouTube 업로드는 사용자 로컬시간대 기준으로 움직이는 게 자연스럽다.
    finished_at 은 utcnow 로 저장되므로 비교 시 동일하게 utcnow 를 쓰고,
    HH:MM 비교만 로컬 시각을 쓴다.
    """
    return datetime.now()


def _same_local_day(ts: Optional[datetime], today_local: date) -> bool:
    """started_at/finished_at 은 utcnow() 로 저장되어 있다.

    사용자 로컬 날짜 경계와 달라질 수 있으므로 "로컬 오늘과 UTC 오늘"
    둘 중 하나라도 매칭되면 '오늘 돌았다'고 본다. 보수적인 판정.
    """
    if ts is None:
        return False
    try:
        d = ts.date()
    except Exception:
        return False
    today_utc = _utcnow().date()
    return d == today_local or d == today_utc


def _parse_hhmm(s: Optional[str]) -> Optional[dtime]:
    if not s:
        return None
    s = s.strip()
    if len(s) < 4 or ":" not in s:
        return None
    try:
        hh, mm = s.split(":", 1)
        return dtime(hour=int(hh), minute=int(mm[:2]))
    except Exception:
        return None


def _pick_next_episode(db: Session) -> Optional[ScheduledEpisode]:
    """실행 대상 episode 한 건 반환. 없으면 None.

    v1.1.25 규칙:
    - running 중인 episode 가 하나라도 있으면 None (직렬 실행)
    - enabled=True, status='pending' 인 행 중,
      오늘 아직 started_at 이 없고 scheduled_time <= 현재 로컬시각인 것들을 후보로
    - 후보가 여러 개면 scheduled_time 오름차순으로 가장 이른 것 선택
      (= 지나간 시각들을 순서대로 catch-up)
    """
    running_exists = (
        db.query(ScheduledEpisode.id)
        .filter(ScheduledEpisode.status == "running")
        .first()
    )
    if running_exists:
        return None

    pending_rows = (
        db.query(ScheduledEpisode)
        .filter(ScheduledEpisode.enabled == True)  # noqa: E712
        .filter(ScheduledEpisode.status == "pending")
        .all()
    )
    if not pending_rows:
        return None

    now_local = _now_local()
    now_t = now_local.time()
    today_local = now_local.date()

    ready: list[tuple[dtime, int, ScheduledEpisode]] = []
    for ep in pending_rows:
        # 오늘 이미 시작된 행은 스킵 (재시도가 아니라면 한 번만)
        if _same_local_day(ep.started_at, today_local):
            continue
        target = _parse_hhmm(ep.scheduled_time) or dtime(9, 0)
        if target <= now_t:
            ready.append((target, ep.episode_number, ep))

    if not ready:
        return None

    # 시각 오름차순 → 동률이면 episode_number 오름차순
    ready.sort(key=lambda x: (x[0], x[1]))
    return ready[0][2]


def _update_episode(episode_id: str, **kwargs) -> None:
    db = SessionLocal()
    try:
        ep = db.query(ScheduledEpisode).filter(ScheduledEpisode.id == episode_id).first()
        if not ep:
            return
        for k, v in kwargs.items():
            setattr(ep, k, v)
        db.commit()
    finally:
        db.close()


def _create_project_from_template(
    episode: ScheduledEpisode,
) -> Project:
    """스케줄용 새 Project 를 DB 에 insert 하고 반환.

    템플릿이 지정돼 있으면 그 프로젝트의 config 를 얕은 복사해서 사용.
    `auto_pause_after_step` 는 스케줄러에서는 무조건 False 로 강제.
    """
    from app.routers.projects import DEFAULT_CONFIG

    db = SessionLocal()
    try:
        base_config: dict = dict(DEFAULT_CONFIG)
        if episode.template_project_id:
            tmpl = (
                db.query(Project)
                .filter(Project.id == episode.template_project_id)
                .first()
            )
            if tmpl and tmpl.config:
                base_config.update(tmpl.config)

        # 스케줄러에서는 사용자 개입 없이 끝까지 달려야 한다.
        base_config["auto_pause_after_step"] = False

        project_id = str(uuid.uuid4())[:8]
        project = Project(
            id=project_id,
            title=(episode.topic or "Scheduled upload")[:100],
            topic=episode.topic or "",
            config=base_config,
            status="processing",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # 파일 디렉토리 생성
        project_dir = Path(DATA_DIR) / project_id
        for sub in ["audio", "images", "videos", "subtitles", "output"]:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

        return project
    finally:
        db.close()


# ─── 실제 실행 로직 ─────────────────────────────────────────────


async def _run_episode(episode: ScheduledEpisode) -> None:
    """단일 episode 를 끝까지 실행. 실패/성공 모두 episode 상태를 갱신."""
    from app.tasks.pipeline_tasks import (
        _step_script,
        _step_voice,
        _step_image,
        _step_video,
        _step_subtitle,
    )
    from app.services.thumbnail_service import generate_ai_thumbnail, ThumbnailError
    from app.services.youtube_service import (
        YouTubeUploader,
        YouTubeAuthError,
        YouTubeUploadError,
    )
    from app.services.llm.factory import get_llm_service

    episode_id = episode.id
    episode_number = episode.episode_number
    privacy = episode.privacy or "private"
    template_project_id = episode.template_project_id

    print(
        f"[scheduler] ▶ 실행 시작 episode={episode_id} "
        f"EP.{episode_number} topic={episode.topic!r}"
    )

    _update_episode(
        episode_id,
        status="running",
        started_at=_utcnow(),
        error_message=None,
    )

    # 1) Project 생성
    try:
        project = _create_project_from_template(episode)
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[scheduler] ✗ project 생성 실패: {e}\n{tb}")
        _update_episode(
            episode_id,
            status="failed",
            finished_at=_utcnow(),
            error_message=f"project 생성 실패: {e}",
        )
        return

    project_id = project.id
    config = dict(project.config or {})
    _update_episode(episode_id, project_id=project_id)

    # 2) 파이프라인 step 2~6 순차 실행.
    #    각 _step_* 은 sync 이고 내부에서 run_async() 로 coroutine 돌린다.
    #    blocking 이므로 to_thread 로 감싼다.
    steps = [
        ("script", _step_script),
        ("voice", _step_voice),
        ("image", _step_image),
        ("video", _step_video),
        ("subtitle", _step_subtitle),
    ]
    for name, func in steps:
        print(f"[scheduler]   → step {name}")
        try:
            await asyncio.to_thread(func, project_id, config)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[scheduler] ✗ step {name} 실패: {e}\n{tb}")
            _update_episode(
                episode_id,
                status="failed",
                finished_at=_utcnow(),
                error_message=f"step {name} 실패: {e}",
            )
            _update_project_status(project_id, "failed")
            return

    # 3) LLM 메타데이터 생성 (title_hook → EP. N - hook)
    try:
        final_title, description, tags, _language = await _generate_metadata(
            project_id=project_id,
            topic=episode.topic or "",
            episode_number=episode_number,
            config=config,
        )
    except Exception as e:
        print(f"[scheduler] 메타데이터 생성 실패 → 폴백 사용: {e}")
        final_title = _fallback_title(episode.topic, episode_number)
        description = episode.topic or ""
        tags = []

    # project.title 갱신
    _update_project_title(project_id, final_title)

    # 4) 썸네일 생성 (AI + 텍스트 오버레이)
    thumb_path: Optional[str] = None
    try:
        thumb_path = await _generate_thumbnail_for_episode(
            project_id=project_id,
            title=final_title,
            episode_number=episode_number,
            config=config,
        )
    except Exception as e:
        print(f"[scheduler] 썸네일 생성 실패 → 썸네일 없이 업로드 시도: {e}")

    # 5) YouTube 업로드
    # 우선순위: 간지 포함 > 자막 번인 > 컷 병합. 어느 것도 없으면 실패.
    output_dir = Path(DATA_DIR) / project_id / "output"
    candidates = [
        output_dir / "final_with_interludes.mp4",
        output_dir / "final_with_subtitles.mp4",
        output_dir / "final.mp4",
        Path(DATA_DIR) / project_id / "videos" / "merged.mp4",
    ]
    final_video: Optional[Path] = None
    for cand in candidates:
        if cand.exists():
            final_video = cand
            break
    if final_video is None:
        _update_episode(
            episode_id,
            status="failed",
            finished_at=_utcnow(),
            error_message=(
                "최종 영상 파일을 찾지 못함 "
                "(final_with_interludes.mp4 / final_with_subtitles.mp4 / final.mp4 / merged.mp4)"
            ),
        )
        _update_project_status(project_id, "failed")
        return

    # 프로젝트별 YouTube 계정이 연결돼 있으면 그걸 사용, 없으면 전역 토큰 fallback.
    _project_uploader = YouTubeUploader(project_id=project_id)
    if _project_uploader.is_authenticated():
        uploader = _project_uploader
    else:
        uploader = YouTubeUploader()
    try:
        result = await asyncio.to_thread(
            uploader.upload,
            str(final_video),
            final_title,
            description,
            tags,
            thumb_path,
            privacy,
            config.get("language", "ko"),
            None,        # category_id
            False,       # made_for_kids
            None,        # progress_callback
        )
    except (YouTubeAuthError, YouTubeUploadError) as e:
        tb = traceback.format_exc()
        print(f"[scheduler] ✗ 업로드 실패: {e}\n{tb}")
        _update_episode(
            episode_id,
            status="failed",
            finished_at=_utcnow(),
            error_message=f"업로드 실패: {e}",
            final_title=final_title,
        )
        _update_project_status(project_id, "failed")
        return
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[scheduler] ✗ 예상치 못한 업로드 오류: {e}\n{tb}")
        _update_episode(
            episode_id,
            status="failed",
            finished_at=_utcnow(),
            error_message=f"예상치 못한 업로드 오류: {e}",
            final_title=final_title,
        )
        _update_project_status(project_id, "failed")
        return

    video_url = result.get("url") or ""

    # 6) 성공
    _update_episode(
        episode_id,
        status="uploaded",
        finished_at=_utcnow(),
        video_url=video_url,
        final_title=final_title,
        error_message=None,
    )
    _update_project_youtube(project_id, video_url)
    _update_project_status(project_id, "completed")
    print(
        f"[scheduler] ✔ 업로드 완료 episode={episode_id} "
        f"project={project_id} url={video_url}"
    )


# ─── 보조 함수들 ─────────────────────────────────────────────────


def _fallback_title(topic: Optional[str], episode_number: int) -> str:
    base = (topic or "Untitled").strip()
    if len(base) > 48:
        base = base[:48]
    return f"EP. {episode_number} - {base}"


async def _generate_metadata(
    project_id: str,
    topic: str,
    episode_number: int,
    config: dict,
) -> tuple[str, str, list[str], str]:
    """메타데이터 생성. 실패하면 예외를 던져 상위에서 폴백을 쓰게 한다.

    Returns: (final_title, description, tags, language)
    """
    from app.services.llm.factory import get_llm_service
    from app.models.cut import Cut

    db = SessionLocal()
    try:
        cuts = (
            db.query(Cut)
            .filter(Cut.project_id == project_id)
            .order_by(Cut.cut_number.asc())
            .all()
        )
        narration = " ".join((c.narration or "").strip() for c in cuts if c.narration)[
            :2500
        ]
    finally:
        db.close()

    language = config.get("language", "ko")
    llm_model_id = config.get("script_model") or "claude-sonnet-4-6"
    llm = get_llm_service(llm_model_id)

    result: dict = {}
    if hasattr(llm, "generate_metadata"):
        result = await llm.generate_metadata(
            title=topic,
            topic=topic,
            narration=narration,
            language=language,
            max_tags=15,
            episode_number=episode_number,
        )

    hook_raw = (result.get("title_hook") or result.get("title") or "").strip()
    # 접두어 중복 방지
    from app.routers.youtube import _strip_episode_prefix, _clean_tag_list

    hook_clean = _strip_episode_prefix(hook_raw)
    if hook_clean:
        final_title = f"EP. {episode_number} - {hook_clean}"
    else:
        final_title = _fallback_title(topic, episode_number)

    description = (result.get("description") or topic or "")[:5000]
    tags = _clean_tag_list(result.get("tags") or [], 15)

    return final_title[:100], description, tags, language


async def _generate_thumbnail_for_episode(
    project_id: str,
    title: str,
    episode_number: int,
    config: dict,
) -> str:
    """AI 썸네일(+ 텍스트 오버레이) 생성. 성공 시 파일 경로 반환."""
    from app.services.thumbnail_service import generate_ai_thumbnail
    from app.services.llm.factory import get_llm_service
    from app.services.llm.base import BaseLLMService
    from app.models.cut import Cut

    image_model_id = config.get("image_model") or "openai-image-1"
    language = config.get("language", "ko")

    db = SessionLocal()
    try:
        cuts = (
            db.query(Cut)
            .filter(Cut.project_id == project_id)
            .order_by(Cut.cut_number.asc())
            .all()
        )
        narration = " ".join((c.narration or "").strip() for c in cuts if c.narration)[
            :1500
        ]
    finally:
        db.close()

    # 프롬프트 생성
    image_prompt: Optional[str] = None
    try:
        llm = get_llm_service(config.get("script_model") or "claude-sonnet-4-6")
        image_prompt = await llm.generate_thumbnail_image_prompt(
            title=title,
            topic=title,
            narration=narration,
            language=language,
        )
    except Exception:
        image_prompt = None
    if not image_prompt:
        image_prompt = BaseLLMService._fallback_thumbnail_prompt(title, title, language)

    # 오버레이: EP 배지 + title hook
    # LLM 이 반환한 "EP. N - hook" 에서 hook 부분만 뽑아 오버레이에 크게 박는다.
    overlay_title = title
    prefix = f"EP. {episode_number} - "
    if title.startswith(prefix):
        overlay_title = title[len(prefix):]

    result = await generate_ai_thumbnail(
        project_id=project_id,
        image_prompt=image_prompt,
        image_model_id=image_model_id,
        overlay_title_text=overlay_title,
        overlay_subtitle=None,
        overlay_episode_label=f"EP. {episode_number}",
    )
    return result["path"]


def _update_project_status(project_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.status = status
            db.commit()
    finally:
        db.close()


def _update_project_title(project_id: str, title: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.title = title[:200]
            db.commit()
    finally:
        db.close()


def _update_project_youtube(project_id: str, url: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.youtube_url = url
            db.commit()
    finally:
        db.close()


# ─── 메인 루프 ──────────────────────────────────────────────────


async def _scheduler_loop() -> None:
    """POLL_INTERVAL 초마다 DB 를 확인하고 실행 가능한 episode 를 처리."""
    assert _stop_event is not None
    print(f"[scheduler] 루프 시작 (polling every {POLL_INTERVAL:.0f}s)")
    while not _stop_event.is_set():
        try:
            await _tick_once()
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[scheduler] 루프 예외 무시하고 계속: {e}\n{tb}")

        # interruptible sleep
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass

    print("[scheduler] 루프 종료")


async def _tick_once() -> None:
    """DB 에서 한 건 골라 실행. 없으면 바로 리턴."""
    db = SessionLocal()
    try:
        episode = _pick_next_episode(db)
    finally:
        db.close()

    if not episode:
        return

    async with _lock:
        # lock 획득 사이에 다른 쪽에서 상태가 바뀌었을 수 있으니 다시 확인
        db = SessionLocal()
        try:
            fresh = (
                db.query(ScheduledEpisode)
                .filter(ScheduledEpisode.id == episode.id)
                .first()
            )
            if not fresh or fresh.status != "pending" or not fresh.enabled:
                return
            now_local = _now_local()
            if _same_local_day(fresh.started_at, now_local.date()):
                return
            target = _parse_hhmm(fresh.scheduled_time) or dtime(9, 0)
            if now_local.time() < target:
                return
            # expunge 해서 session 닫은 뒤에도 attribute 읽기 가능
            db.expunge(fresh)
        finally:
            db.close()

        await _run_episode(fresh)


# ─── 외부에서 부르는 API ─────────────────────────────────────────


def start_scheduler() -> None:
    """FastAPI lifespan 에서 호출. idempotent."""
    global _scheduler_task, _stop_event
    if _scheduler_task and not _scheduler_task.done():
        return
    _stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    _scheduler_task = loop.create_task(_scheduler_loop(), name="longtube-scheduler")


async def stop_scheduler() -> None:
    """FastAPI lifespan 에서 호출. 진행 중인 episode 는 기다려준다."""
    global _scheduler_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _scheduler_task is not None:
        try:
            await asyncio.wait_for(_scheduler_task, timeout=5.0)
        except asyncio.TimeoutError:
            _scheduler_task.cancel()
            try:
                await _scheduler_task
            except (asyncio.CancelledError, Exception):
                pass
    _scheduler_task = None
    _stop_event = None


def is_running() -> bool:
    return _scheduler_task is not None and not _scheduler_task.done()


async def run_episode_now(episode_id: str) -> None:
    """수동 트리거 — '지금 실행' 버튼에서 호출.

    루프와 같은 `_lock` 을 공유하므로, 루프가 다른 episode 를 돌리고 있으면
    기다렸다가 실행된다.
    """
    async with _lock:
        db = SessionLocal()
        try:
            ep = (
                db.query(ScheduledEpisode)
                .filter(ScheduledEpisode.id == episode_id)
                .first()
            )
            if not ep:
                raise ValueError(f"episode not found: {episode_id}")
            if ep.status == "running":
                raise ValueError("이미 실행 중입니다.")
            db.expunge(ep)
        finally:
            db.close()
        await _run_episode(ep)
