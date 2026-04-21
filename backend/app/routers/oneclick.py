"""v1.1.34 — '딸깍 제작' 라우터.

엔드포인트
---------
POST /api/oneclick/prepare          — 새 프로젝트 + task 레코드 생성 (예상 비용/시간 반환)
POST /api/oneclick/{task_id}/start  — 백그라운드 실행 시작
POST /api/oneclick/{task_id}/cancel — 취소 요청
GET  /api/oneclick/tasks            — 전체 태스크 목록
GET  /api/oneclick/tasks/{task_id}  — 단일 태스크 상태 + 진행률
POST /api/oneclick/prune            — 완료 태스크 정리 (기본 20개 유지)

v1.1.42
-------
- 매일 자동 실행 스케줄(`GET/PUT /schedule`) 엔드포인트 삭제. 딸깍은 이제
  모달에서 주제/시간을 입력해 즉시 실행하는 "인스턴트" 경로만 제공한다.
- `PrepareRequest` 가 `target_duration` (초) 을 받는다 — 모달의 "시간" 입력값.

v1.1.43
-------
- 주제 큐 + 매일 HH:MM 스케줄 재도입 (새 모델). 엔드포인트:
    GET  /api/oneclick/queue          — 현재 큐 상태 + daily_time
    PUT  /api/oneclick/queue          — 큐 전체 교체 (저장)
    POST /api/oneclick/queue/run-next — 큐 맨 위 1건 즉시 실행 (pop)
"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import oneclick_service

router = APIRouter()


class PrepareRequest(BaseModel):
    template_project_id: Optional[str] = None
    topic: str
    title: Optional[str] = None
    # v1.1.42: 모달 "시간" 입력. None 이면 템플릿/기본값 유지.
    target_duration: Optional[int] = None


@router.post("/prepare")
def prepare(req: PrepareRequest):
    topic = (req.topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic 이 비어 있습니다")
    try:
        task = oneclick_service.prepare_task(
            template_project_id=req.template_project_id,
            topic=topic,
            title=req.title,
            target_duration=req.target_duration,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"prepare 실패: {type(e).__name__}: {e}")
    return task


@router.post("/{task_id}/start")
async def start(task_id: str):
    # v1.1.37 bugfix: sync def 로 두면 FastAPI 가 AnyIO worker thread 에서 실행 →
    # 그 스레드엔 이벤트 루프가 없어서 start_task 안의 asyncio.create_task 가
    # "There is no current event loop in thread 'AnyIO worker thread'" 로 터진다.
    # async def 로 선언해서 FastAPI 메인 이벤트 루프 위에서 직접 호출되게 한다.
    try:
        return oneclick_service.start_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"start 실패: {type(e).__name__}: {e}")


@router.post("/{task_id}/resume")
async def resume(task_id: str):
    """v1.1.49: 실패/취소된 태스크를 실패 지점부터 이어서 재실행.

    async def — start 와 동일한 이유로 이벤트 루프 보장 필요.
    """
    try:
        return oneclick_service.resume_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"resume 실패: {type(e).__name__}: {e}")


@router.post("/{task_id}/cancel")
def cancel(task_id: str):
    try:
        return oneclick_service.cancel_task(task_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")


@router.post("/emergency-stop")
async def emergency_stop():
    """v1.1.70 — 비상 정지. 서버에서 진행/대기 중인 모든 작업 강제 중단.

    Python asyncio 태스크 + Redis cancel 플래그 + ComfyUI `/interrupt` +
    ComfyUI `/queue` clear 를 한번에 호출한다. UI 에 큐가 비어 보이는데
    ComfyUI 는 계속 이미지를 뱉는 desync 상황을 해소하기 위한 수단.

    생성된 파일(프로젝트 디렉토리)은 건드리지 않는다. 필요하면 라이브러리
    에서 개별 삭제.
    """
    try:
        return await oneclick_service.emergency_stop_all()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"emergency stop 실패: {type(e).__name__}: {e}",
        )


@router.get("/running")
def get_running():
    """v1.1.58: 현재 실행 중인 태스크 정보. 없으면 null."""
    return {"running": oneclick_service.get_running_task_info()}


@router.get("/tasks")
def list_all():
    return {"tasks": oneclick_service.list_tasks()}


@router.get("/tasks/{task_id}")
def get_one(task_id: str):
    task = oneclick_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    ok = oneclick_service.delete_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="task not found or still running")
    return {"ok": True, "task_id": task_id}


@router.post("/{task_id}/clear-step/{step}")
def clear_step(task_id: str, step: int):
    """v1.1.52: 특정 단계의 생성물을 삭제한다.

    step 4(이미지) → images/ 폴더 내 파일 삭제
    step 5(영상)  → videos/ 폴더 내 파일 + output/merged.mp4 삭제
    step 3(음성)  → audio/ 폴더 내 파일 삭제

    삭제 후 해당 step_state 를 pending 으로 되돌린다.
    "이어서 하기" 전에 특정 단계만 초기화하여 재생성할 때 사용.
    """
    try:
        result = oneclick_service.clear_step_outputs(task_id, step)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


class ResetRequest(BaseModel):
    from_step: int = 2


@router.post("/{task_id}/reset")
def reset_task(task_id: str, body: ResetRequest = ResetRequest()):
    """v1.1.53: 프로젝트 초기화 — from_step 부터 모든 단계를 리셋한다.

    from_step=2 → 대본부터 전체 초기화 (기본)
    from_step=3 → 음성부터 초기화 (대본 유지)
    """
    try:
        result = oneclick_service.reset_task(task_id, body.from_step)
    except KeyError:
        raise HTTPException(status_code=404, detail="task not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


class ThumbnailRegenRequest(BaseModel):
    image_model: Optional[str] = None


@router.post("/{task_id}/regenerate-thumbnail")
async def regenerate_thumbnail(task_id: str, body: ThumbnailRegenRequest = ThumbnailRegenRequest()):
    """v1.1.52: 썸네일을 재생성한다. image_model 을 지정하면 해당 모델로 생성."""
    task = oneclick_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")

    project_id = task["project_id"]
    from app.services.oneclick_service import _load_project
    project = _load_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")

    config = dict(project.config or {})
    if body.image_model:
        config["thumbnail_model"] = body.image_model

    from app.tasks.pipeline_tasks import load_script, build_thumbnail_prompt, _redis_set
    from app.services.image.prompt_builder import collect_reference_images, collect_character_images
    from app.services.thumbnail_service import generate_ai_thumbnail
    from app.config import DATA_DIR
    from pathlib import Path
    import re

    script = load_script(project_id)
    thumb_prompt = build_thumbnail_prompt(script)

    image_model = config.get("thumbnail_model") or config.get("image_model") or "openai-image-1"
    thumb_path = Path(DATA_DIR) / project_id / "output" / "thumbnail.png"
    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    # 기존 썸네일 삭제
    if thumb_path.exists():
        thumb_path.unlink()
    bg_path = thumb_path.with_name("thumbnail_bg.png")
    if bg_path.exists():
        bg_path.unlink()

    _redis_set(f"thumbnail:status:{project_id}", "generating")

    # 메인 후크 텍스트: title 에서 "EP. N · " 접두사 제거
    title = (script.get("title") or "").strip()
    overlay_title = re.sub(r"^EP\.\s*\d+\s*[·\-]\s*", "", title).strip() or title

    # 레퍼런스 + 캐릭터 이미지 수집 — 스튜디오와 동일
    char_paths = collect_character_images(project_id, config)
    ref_paths = collect_reference_images(project_id, config)
    seen: set[str] = set()
    combined_refs: list[str] = []
    for p in [*char_paths, *ref_paths]:
        if p not in seen:
            seen.add(p)
            combined_refs.append(p)

    # v2.1.2: 레퍼런스 미지원 모델이면 폴백. ComfyUI 로컬 모델은 API 폴백 방지.
    if combined_refs:
        from app.services.image.factory import get_image_service, IMAGE_REGISTRY as _IMG_REG
        _probe = get_image_service(image_model)
        if not getattr(_probe, "supports_reference_images", False):
            if _IMG_REG.get(image_model, {}).get("provider") == "comfyui":
                combined_refs = []
            else:
                image_model = "nano-banana-3"

    # v1.1.55: 공통 REFERENCE_STYLE_PREFIX 사용 — 컷/썸네일/재생성 문구 통일
    if combined_refs and thumb_prompt:
        from app.services.image.prompt_builder import apply_reference_style_prefix
        thumb_prompt = apply_reference_style_prefix(thumb_prompt, has_reference=True)

    try:
        # v1.1.55: 스튜디오와 동일 — generate_ai_thumbnail + 텍스트 오버레이
        result = await generate_ai_thumbnail(
            project_id=project_id,
            image_prompt=thumb_prompt,
            image_model_id=image_model,
            overlay_title_text=overlay_title,
            overlay_subtitle=None,
            overlay_episode_label=None,
            output_path=str(thumb_path),
            reference_images=combined_refs or None,
        )
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return {"ok": True, "path": result["path"], "model": image_model, "overlay": result["overlay_applied"]}
    except Exception as e:
        import traceback
        err_detail = f"{type(e).__name__}: {e}"
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_detail[:300]}")
        print(f"[Thumbnail][재생성] 실패: {err_detail}")
        print(f"[Thumbnail][재생성] traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"썸네일 생성 실패: {err_detail}")


class RecoverRequest(BaseModel):
    project_id: str


@router.post("/recover")
async def recover_project(req: RecoverRequest):
    """v1.1.56: 프로젝트 ID 로 태스크를 복구한다.

    큐에서 사라졌거나 유실된 태스크를 디스크 파일 기반으로 복구해
    이어하기 가능한 상태로 만든다.
    """
    try:
        task = oneclick_service.recover_project(req.project_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"복구 실패: {type(e).__name__}: {e}")
    return task


@router.post("/prune")
def prune(keep: int = 20):
    oneclick_service.prune_tasks(keep=keep)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# v1.1.54 — 완성작 관리 (라이브러리)
# --------------------------------------------------------------------------- #


@router.get("/tasks/{task_id}/detail")
def task_detail(task_id: str):
    """완성작 상세 정보 — 프로젝트 메타 + 디스크 용량 + 컷 목록."""
    task = oneclick_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    try:
        detail = oneclick_service.get_task_detail(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return detail


@router.post("/tasks/{task_id}/upload")
async def manual_upload(task_id: str):
    """완성작을 수동으로 YouTube 에 업로드한다."""
    task = oneclick_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail="완료된 태스크만 업로드 가능합니다")
    try:
        result = await oneclick_service.manual_youtube_upload(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return result


class BulkDeleteRequest(BaseModel):
    task_ids: List[str]


@router.post("/tasks/bulk-delete")
def bulk_delete(req: BulkDeleteRequest):
    """여러 태스크를 한번에 삭제 + 디스크 정리."""
    result = oneclick_service.bulk_delete_tasks(req.task_ids)
    return result


@router.get("/library/stats")
def library_stats():
    """완성작 라이브러리 전체 통계."""
    return oneclick_service.get_library_stats()


# --------------------------------------------------------------------------- #
# v1.1.43 — 주제 큐 + 매일 HH:MM 스케줄
# --------------------------------------------------------------------------- #


class QueueItemModel(BaseModel):
    id: Optional[str] = None
    topic: str
    template_project_id: Optional[str] = None
    # 초 단위. None/0 이면 템플릿 기본값 사용.
    target_duration: Optional[int] = None
    # v1.1.57: 채널 번호 (1~4). None/0 이면 채널 1.
    channel: Optional[int] = None


class QueueStateModel(BaseModel):
    # v1.1.57: 기존 daily_time 은 하위호환용으로 유지 (채널 1 기본값).
    # 채널별 스케줄은 channel_times 로 관리.
    daily_time: Optional[str] = None  # 레거시 — channel_times["1"] 로 마이그레이션
    channel_times: Optional[dict] = None  # {"1": "07:00", "2": "12:00", ...}
    items: List[QueueItemModel] = []


@router.get("/queue")
def get_queue():
    return oneclick_service.get_queue()


@router.put("/queue")
def put_queue(state: QueueStateModel):
    try:
        return oneclick_service.set_queue(state.model_dump())
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"queue save failed: {type(e).__name__}: {e}",
        )


@router.post("/queue/run-next")
async def run_queue_next():
    """큐 맨 위 1 건을 즉시 pop 해 실행. 없으면 204.

    async def 로 선언해서 FastAPI 이벤트 루프에서 직접 호출되게 함.
    `start_task` 내부에서 `asyncio.get_running_loop()` 가 필요하기 때문.
    """
    try:
        task = oneclick_service.run_queue_top_now()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"run-next failed: {type(e).__name__}: {e}",
        )
    if task is None:
        raise HTTPException(status_code=404, detail="queue is empty")
    return task
