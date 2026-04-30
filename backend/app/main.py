"""LongTube Backend - FastAPI Application"""
# reload-trigger: 2026-04-14 v1.1.54 tts-duration-fix-cancel-thumbnail
import sys
import asyncio


def _configure_stdio_encoding() -> None:
    """Keep diagnostic prints from failing on Windows code pages."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass


_configure_stdio_encoding()

# Windows: force ProactorEventLoopPolicy before anything else imports asyncio.
# asyncio.create_subprocess_exec() raises NotImplementedError on the default
# SelectorEventLoop on Windows, which our fal/ffmpeg video services rely on.
if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os

from app.config import DATA_DIR, DEBUG
from app.models.database import init_db
# v1.1.43: `schedule` 라우터와 `scheduler_service` (17 행 EP 그리드) 는 자동화
# 스케줄 기능 제거로 더 이상 사용하지 않는다. 파일 자체는 안전을 위해 디스크
# 에 남겨두지만, FastAPI 앱에는 등록하지 않는다.
# v1.1.43: oneclick_service 에 "주제 큐 + 매일 HH:MM" 형태의 새 스케줄러가
# 다시 붙었다 (구 17 행 그리드 와는 완전히 다른 모델). startup/shutdown 에서
# `start_queue_scheduler` / `stop_queue_scheduler` 를 호출한다.
from app.routers import projects, pipeline, script, voice, image, video, subtitle, interlude, youtube, youtube_studio, downloads, models, api_status, api_keys, api_balances, tasks, oneclick, assets
# v2.1.0 병렬 라우터. 구 라우터와 독립적으로 /api/v2/* 에 마운트된다.
from app.routers.v2 import (
    keys as v2_keys,
    presets as v2_presets,
    queue as v2_queue,
    tasks as v2_tasks,
    events as v2_events,
    storage as v2_storage,
    usage as v2_usage,
)
from app.services import oneclick_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    os.makedirs(DATA_DIR, exist_ok=True)
    # v1.1.29: 오염된 project.topic 레코드 1 회성 마이그레이션.
    # 과거 버그로 StepYouTube 가 YouTube 영상 설명 전문(수천자 + bullet) 을
    # project.topic 에 덮어써서 헤더가 거대한 벽이 되던 문제가 있었음. 이를
    # 자동 복구 — topic 길이가 300자 초과거나 줄바꿈/bullet 마커가 섞여 있으면
    # config.youtube_description 으로 이관하고 topic 을 title 또는 첫 문장으로 대체.
    try:
        from app.models.database import SessionLocal
        from app.models.project import Project
        from sqlalchemy.orm.attributes import flag_modified
        db = SessionLocal()
        try:
            migrated = 0
            for p in db.query(Project).all():
                topic = (p.topic or "").strip()
                if not topic:
                    continue
                looks_polluted = (
                    len(topic) > 300
                    or "\n" in topic
                    or "• " in topic
                    or "· " in topic
                )
                if not looks_polluted:
                    continue
                cfg = dict(p.config or {})
                if not (cfg.get("youtube_description") or "").strip():
                    cfg["youtube_description"] = topic
                # 복구용 새 topic: title 이 있으면 그걸, 없으면 topic 의 첫 문장(최대 120자)
                fallback_topic = (p.title or "").strip()
                if not fallback_topic:
                    first_sentence = topic.split(".")[0].strip()
                    fallback_topic = first_sentence[:120] or "주제 미정"
                p.topic = fallback_topic[:200]
                p.config = cfg
                flag_modified(p, "config")
                migrated += 1
            if migrated:
                db.commit()
                print(f"[startup] migrated {migrated} polluted project.topic → config.youtube_description")
            else:
                print("[startup] topic migration: nothing to do")
        finally:
            db.close()
    except Exception as e:
        print(f"[startup] topic migration error (non-fatal): {e}")
    # Probe ffmpeg binary so we log the resolved path (or failure) at startup.
    try:
        from app.services.video.subprocess_helper import find_ffmpeg
        ffpath = find_ffmpeg()
        print(f"[startup] ffmpeg OK: {ffpath}")
    except Exception as e:
        print(f"[startup] ffmpeg NOT FOUND: {e}")
    # v1.1.43: oneclick 주제 큐 스케줄러 기동. 사용자 요구: "딸깍제작 주제
    # 입력 리스트 만들고 매일 몇시에 시작 할지 입력 할 수 있게해". 30 초 간격
    # 루프가 DATA_DIR/oneclick_queue.json 을 감시하다가 설정된 HH:MM 에
    # 맨 위 주제 1 건을 pop 해 실행한다. 큐가 비면 조용히 대기.
    try:
        oneclick_service.start_queue_scheduler()
    except Exception as e:
        print(f"[startup] oneclick queue scheduler start failed: {e}")
    # v2.1.0: .env 평문 API 키 → api_key_vault 1회 암호화 동기화.
    # .env 파일은 건드리지 않으며, DB 에 이미 같은 provider 행이 있으면 덮지 않는다.
    try:
        from app.security.vault_sync import sync_env_into_vault
        report = sync_env_into_vault()
        ins = len(report.get("inserted", []))
        skp = len(report.get("skipped", []))
        emp = len(report.get("empty", []))
        print(f"[startup] vault sync: inserted={ins} skipped={skp} empty={emp}")
    except Exception as e:
        print(f"[startup] vault sync failed (non-fatal): {e}")
    yield
    # Shutdown
    try:
        oneclick_service.stop_queue_scheduler()
    except Exception as e:
        print(f"[shutdown] oneclick queue scheduler stop error: {e}")


app = FastAPI(
    title="LongTube",
    description="YouTube longform video automation pipeline",
    version="1.2.29",
    lifespan=lifespan,
)

# v2.0.74: 같은 사무실 다른 PC 에서 http://<호스트IP>:3000 으로 들어오는 경우를 허용한다.
# 사설 IP 대역(10/8, 172.16/12, 192.168/16) + localhost + 127.0.0.1 + :3000 만 화이트리스트.
# 공인 IP 에서의 접근은 여전히 차단된다(사무실 내부 신뢰 범위 안에서만 허용).
_LAN_CORS_REGEX = (
    r"http://("
    r"localhost"
    r"|127\.0\.0\.1"
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"):3000"
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_LAN_CORS_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(pipeline.router, prefix="/api/pipeline", tags=["pipeline"])
app.include_router(script.router, prefix="/api/script", tags=["script"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(image.router, prefix="/api/image", tags=["image"])
app.include_router(video.router, prefix="/api/video", tags=["video"])
app.include_router(subtitle.router, prefix="/api/subtitle", tags=["subtitle"])
app.include_router(interlude.router, prefix="/api/interlude", tags=["interlude"])
app.include_router(youtube.router, prefix="/api/youtube", tags=["youtube"])
app.include_router(youtube_studio.router, prefix="/api/youtube-studio", tags=["youtube-studio"])
app.include_router(downloads.router, prefix="/api/downloads", tags=["downloads"])
app.include_router(assets.router, prefix="/api/assets", tags=["assets"])
app.include_router(models.router, prefix="/api/models", tags=["models"])
app.include_router(api_status.router, prefix="/api/api-status", tags=["api-status"])
app.include_router(api_keys.router, prefix="/api/api-keys", tags=["api-keys"])
app.include_router(api_balances.router, prefix="/api/api-balances", tags=["api-balances"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
# v1.1.43: /api/schedule 라우터 비활성화 (자동화 스케줄 기능 삭제)
app.include_router(oneclick.router, prefix="/api/oneclick", tags=["oneclick"])

# v2.1.0 병렬 라우터 — 구 라우터와 독립. /api/v2/* 에 마운트.
app.include_router(v2_keys.router, prefix="/api/v2/keys", tags=["v2-keys"])
app.include_router(v2_presets.router, prefix="/api/v2/presets", tags=["v2-presets"])
app.include_router(v2_queue.router, prefix="/api/v2/queue", tags=["v2-queue"])
app.include_router(v2_tasks.router, prefix="/api/v2/tasks", tags=["v2-tasks"])
app.include_router(v2_events.router, prefix="/api/v2/events", tags=["v2-events"])
app.include_router(v2_storage.router, prefix="/api/v2/storage", tags=["v2-storage"])
app.include_router(v2_usage.router, prefix="/api/v2/usage", tags=["v2-usage"])

# Serve generated assets — ensure directory exists before mounting
os.makedirs(DATA_DIR, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(DATA_DIR)), name="assets")


@app.get("/api/health")
async def health():
    from app.config import COMFYUI_BASE_URL as _CU
    return {"status": "ok", "version": "1.2.29", "comfyui_base_url": _CU or None}
