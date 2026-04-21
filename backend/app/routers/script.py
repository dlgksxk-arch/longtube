"""Script generation router"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import DATA_DIR
from app.services.llm.factory import get_llm_service

router = APIRouter()


def _asset_exists(project_dir: Path, asset_path: str) -> bool:
    """Check if an asset file exists. Handles both absolute and relative paths."""
    p = Path(asset_path)
    if p.is_absolute():
        return p.exists()
    return (project_dir / asset_path).exists()


def _normalize_path(project_id: str, asset_path: str) -> str:
    """Convert absolute path to relative path from project dir. Fix legacy data."""
    if not asset_path:
        return asset_path
    project_dir = str(DATA_DIR / project_id)
    p = str(asset_path).replace("\\", "/")
    pd = project_dir.replace("\\", "/")
    if p.startswith(pd):
        rel = p[len(pd):]
        return rel.lstrip("/")
    return asset_path


class CutUpdate(BaseModel):
    narration: Optional[str] = None
    image_prompt: Optional[str] = None


class CutCreate(BaseModel):
    cut_number: int
    narration: str
    image_prompt: str
    scene_type: Optional[str] = "narration"


class CutReorder(BaseModel):
    order: List[int]


def _load_script(project_id: str) -> dict:
    """Load script.json from disk"""
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_script(project_id: str, script: dict):
    """Save script.json to disk"""
    script_path = DATA_DIR / project_id / "script.json"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)


@router.post("/{project_id}/generate")
async def generate_script(project_id: str, db: Session = Depends(get_db)):
    """Generate script using LLM"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    model_id = project.config.get("script_model", "claude-sonnet-4-6")

    # API 키 확인
    # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
    from app import config as app_config
    provider = "anthropic" if "claude" in model_id else "openai"
    if provider == "anthropic" and not app_config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY not set. Add it to backend/.env file.")
    if provider == "openai" and not app_config.OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY not set. Add it to backend/.env file.")

    llm_service = get_llm_service(model_id)

    try:
        script = await llm_service.generate_script(project.topic, project.config)
    except Exception as e:
        raise HTTPException(500, f"LLM script generation failed: {str(e)}")

    for cut_data in script.get("cuts", []):
        existing = db.query(Cut).filter(
            Cut.project_id == project_id,
            Cut.cut_number == cut_data["cut_number"]
        ).first()

        if existing:
            existing.narration = cut_data.get("narration")
            existing.image_prompt = cut_data.get("image_prompt")
            existing.scene_type = cut_data.get("scene_type")
            # Reset generated assets — new script means re-generation needed
            existing.audio_path = None
            existing.audio_duration = None
            existing.image_path = None
            existing.image_model = None
            existing.video_path = None
            existing.status = "pending"
        else:
            cut = Cut(
                project_id=project_id,
                cut_number=cut_data["cut_number"],
                narration=cut_data.get("narration"),
                image_prompt=cut_data.get("image_prompt"),
                scene_type=cut_data.get("scene_type"),
                status="pending"
            )
            db.add(cut)

    db.commit()
    project.total_cuts = len(script.get("cuts", []))

    # Mark script step as completed, reset subsequent steps
    # v1.1.26 스텝 순서: 2 대본 · 3 음성 · 4 간지 · 5 이미지 · 6 영상 · 7 자막
    step_states = dict(project.step_states or {})
    step_states["2"] = "completed"
    step_states.pop("3", None)  # voice
    step_states.pop("5", None)  # image
    step_states.pop("6", None)  # video
    step_states.pop("7", None)  # subtitle
    project.step_states = step_states
    if project.current_step < 2:
        project.current_step = 2

    db.commit()

    _save_script(project_id, script)
    return script


@router.post("/{project_id}/generate-async")
async def generate_script_async(project_id: str, db: Session = Depends(get_db)):
    """v1.1.49: 대본 생성을 백그라운드로 실행 — 즉시 반환.

    탭 이동/페이지 닫기에도 작업이 계속 진행된다.
    """
    import asyncio
    from app.services.task_manager import (
        start_task, complete_task, fail_task, register_async_task, is_running,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "script"):
        return {"status": "already_running", "step": "script"}

    model_id = project.config.get("script_model", "claude-sonnet-4-6")

    # API 키 확인
    # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
    from app import config as app_config
    provider = "anthropic" if "claude" in model_id else "openai"
    if provider == "anthropic" and not app_config.ANTHROPIC_API_KEY:
        raise HTTPException(400, "ANTHROPIC_API_KEY not set. Add it to backend/.env file.")
    if provider == "openai" and not app_config.OPENAI_API_KEY:
        raise HTTPException(400, "OPENAI_API_KEY not set. Add it to backend/.env file.")

    # 대본은 단일 LLM 호출. 예상 시간: 설정의 예상치 또는 기본 60초
    est_seconds = float((project.config or {}).get("estimate", {}).get("time_breakdown", {}).get("llm_script", 60))
    state = start_task(project_id, "script", 1, estimated_total_seconds=est_seconds)

    # step_states 를 running 으로 갱신
    step_states = dict(project.step_states or {})
    step_states["2"] = "running"
    project.step_states = step_states
    db.commit()

    # 작업에 필요한 값을 미리 캡처 (DB 세션은 공유 불가)
    topic = project.topic
    config = dict(project.config or {})

    async def _run():
        from app.models.database import SessionLocal
        local_db = SessionLocal()
        try:
            llm_service = get_llm_service(model_id)
            script = await llm_service.generate_script(topic, config)

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            if not proj:
                raise ValueError("Project not found")

            for cut_data in script.get("cuts", []):
                existing = local_db.query(Cut).filter(
                    Cut.project_id == project_id,
                    Cut.cut_number == cut_data["cut_number"],
                ).first()
                if existing:
                    existing.narration = cut_data.get("narration")
                    existing.image_prompt = cut_data.get("image_prompt")
                    existing.scene_type = cut_data.get("scene_type")
                    existing.audio_path = None
                    existing.audio_duration = None
                    existing.image_path = None
                    existing.image_model = None
                    existing.video_path = None
                    existing.status = "pending"
                else:
                    local_db.add(Cut(
                        project_id=project_id,
                        cut_number=cut_data["cut_number"],
                        narration=cut_data.get("narration"),
                        image_prompt=cut_data.get("image_prompt"),
                        scene_type=cut_data.get("scene_type"),
                        status="pending",
                    ))

            local_db.commit()
            proj.total_cuts = len(script.get("cuts", []))

            ss = dict(proj.step_states or {})
            ss["2"] = "completed"
            ss.pop("3", None)
            ss.pop("5", None)
            ss.pop("6", None)
            ss.pop("7", None)
            proj.step_states = ss
            if proj.current_step < 2:
                proj.current_step = 2
            local_db.commit()

            _save_script(project_id, script)
            # v1.1.55-fix: 스튜디오 LLM 스크립트 생성 비용 기록
            try:
                from app.services import spend_ledger
                spend_ledger.record_llm(
                    model_id, input_tokens=0, output_tokens=0,
                    project_id=project_id, note=f"studio script {len(script.get('cuts',[]))} cuts",
                )
            except Exception as _le:
                print(f"[spend_ledger] studio script record skipped: {_le}")
            complete_task(project_id, "script")
        except Exception as e:
            fail_task(project_id, "script", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["2"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except Exception:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "script", task)
    return {"status": "started", "step": "script", "task": state.to_dict()}


@router.get("/{project_id}/cuts")
def list_cuts(project_id: str, db: Session = Depends(get_db)):
    """List all cuts for a project"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()

    # Normalize absolute paths to relative + validate file existence
    dirty = False
    project_dir = DATA_DIR / project_id
    for c in cuts:
        # Normalize absolute paths to relative (fix legacy data)
        if c.audio_path:
            norm = _normalize_path(project_id, c.audio_path)
            if norm != c.audio_path:
                c.audio_path = norm
                dirty = True
        if c.image_path:
            norm = _normalize_path(project_id, c.image_path)
            if norm != c.image_path:
                c.image_path = norm
                dirty = True
        if c.video_path:
            norm = _normalize_path(project_id, c.video_path)
            if norm != c.video_path:
                c.video_path = norm
                dirty = True

        # Clear paths if file doesn't actually exist on disk
        if c.audio_path and not _asset_exists(project_dir, c.audio_path):
            c.audio_path = None
            c.audio_duration = None
            dirty = True
        if c.image_path and not _asset_exists(project_dir, c.image_path):
            c.image_path = None
            c.image_model = None
            c.is_custom_image = False
            dirty = True
        if c.video_path and not _asset_exists(project_dir, c.video_path):
            c.video_path = None
            c.video_model = None
            dirty = True
    if dirty:
        db.commit()

    return {
        "project_id": project_id,
        "total": len(cuts),
        "cuts": [
            {
                "cut_number": c.cut_number,
                "narration": c.narration,
                "image_prompt": c.image_prompt,
                "scene_type": c.scene_type,
                "audio_path": c.audio_path,
                "audio_duration": c.audio_duration,
                "image_path": c.image_path,
                "image_model": c.image_model,
                "video_path": c.video_path,
                "video_model": c.video_model,
                "status": c.status,
                "is_custom_image": c.is_custom_image,
            }
            for c in cuts
        ],
    }


# --- 고정 경로 라우트 먼저 (cuts/add, cuts/reorder) ---

@router.post("/{project_id}/cuts/add")
def add_cut(
    project_id: str,
    body: CutCreate,
    db: Session = Depends(get_db)
):
    """Add a new cut"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    existing = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == body.cut_number
    ).first()

    if existing:
        raise HTTPException(400, f"Cut {body.cut_number} already exists")

    cut = Cut(
        project_id=project_id,
        cut_number=body.cut_number,
        narration=body.narration,
        image_prompt=body.image_prompt,
        scene_type=body.scene_type,
        status="pending"
    )
    db.add(cut)
    db.commit()

    project.total_cuts = db.query(Cut).filter(Cut.project_id == project_id).count()
    db.commit()

    script = _load_script(project_id)
    script["cuts"].append({
        "cut_number": body.cut_number,
        "narration": body.narration,
        "image_prompt": body.image_prompt,
        "scene_type": body.scene_type
    })
    _save_script(project_id, script)

    return {
        "cut_number": cut.cut_number,
        "narration": cut.narration,
        "image_prompt": cut.image_prompt,
        "scene_type": cut.scene_type
    }


@router.put("/{project_id}/cuts/reorder")
def reorder_cuts(
    project_id: str,
    body: CutReorder,
    db: Session = Depends(get_db)
):
    """Reorder cuts"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    cut_dict = {c.cut_number: c for c in cuts}

    for cut_num in body.order:
        if cut_num not in cut_dict:
            raise HTTPException(400, f"Cut {cut_num} not found")

    for new_position, old_cut_number in enumerate(body.order, start=1):
        cut = cut_dict[old_cut_number]
        cut.cut_number = new_position

    db.commit()

    script = _load_script(project_id)
    old_cuts = {c["cut_number"]: c for c in script.get("cuts", [])}
    script["cuts"] = [old_cuts[num] for num in body.order if num in old_cuts]
    for new_pos, cut_data in enumerate(script["cuts"], start=1):
        cut_data["cut_number"] = new_pos
    _save_script(project_id, script)

    return {"status": "reordered", "order": body.order}


# --- 동적 경로 라우트 (cuts/{cut_number}) ---

@router.put("/{project_id}/cuts/{cut_number}")
def edit_cut(
    project_id: str,
    cut_number: int,
    body: CutUpdate,
    db: Session = Depends(get_db)
):
    """Edit a specific cut"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cut = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == cut_number
    ).first()

    if not cut:
        raise HTTPException(404, f"Cut {cut_number} not found")

    if body.narration is not None:
        cut.narration = body.narration
    if body.image_prompt is not None:
        cut.image_prompt = body.image_prompt

    db.commit()

    script = _load_script(project_id)
    for cut_data in script.get("cuts", []):
        if cut_data["cut_number"] == cut_number:
            if body.narration is not None:
                cut_data["narration"] = body.narration
            if body.image_prompt is not None:
                cut_data["image_prompt"] = body.image_prompt
            break
    _save_script(project_id, script)

    return {
        "cut_number": cut.cut_number,
        "narration": cut.narration,
        "image_prompt": cut.image_prompt,
        "scene_type": cut.scene_type
    }


@router.delete("/{project_id}/cuts/{cut_number}")
def delete_cut(
    project_id: str,
    cut_number: int,
    db: Session = Depends(get_db)
):
    """Delete a cut"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cut = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == cut_number
    ).first()

    if not cut:
        raise HTTPException(404, f"Cut {cut_number} not found")

    db.delete(cut)
    db.commit()

    project.total_cuts = db.query(Cut).filter(Cut.project_id == project_id).count()
    db.commit()

    script = _load_script(project_id)
    script["cuts"] = [c for c in script.get("cuts", []) if c["cut_number"] != cut_number]
    _save_script(project_id, script)

    return {"status": "deleted", "cut_number": cut_number}


# --- Clear step results ---

@router.post("/{project_id}/clear/{step}")
def clear_step_results(project_id: str, step: str, db: Session = Depends(get_db)):
    """Clear all generated results for a specific step.
    step: 'script' (2) | 'voice' (3) | 'image' (4) | 'video' (5) | 'subtitle' (6)
    """
    import shutil

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    project_dir = DATA_DIR / project_id

    step_num_map = {"script": "2", "voice": "3", "image": "4", "video": "5", "subtitle": "6", "youtube": "7"}
    step_num = step_num_map.get(step)
    if not step_num:
        raise HTTPException(
            400, f"Invalid step: {step}. Use script, voice, image, video, subtitle, or youtube."
        )

    if step == "script":
        # 대본 초기화: 컷 전체 삭제 + 관련 미디어 디렉토리 몽땅 비우기.
        for c in cuts:
            db.delete(c)
        for sub in ("audio", "images", "video", "subtitles", "output"):
            d = project_dir / sub
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)

    elif step == "subtitle":
        # 자막/최종 렌더링 산출물 제거. cut 행 자체는 유지.
        # 진행 중인 렌더링 태스크가 있으면 취소
        try:
            from app.services.task_manager import cancel_task
            cancel_task(project_id, "render")
        except Exception:
            pass
        sub_dir = project_dir / "subtitles"
        if sub_dir.exists():
            shutil.rmtree(sub_dir, ignore_errors=True)
        output_dir = project_dir / "output"
        if output_dir.exists():
            for name in ("final.mp4", "merged.mp4", "final.srt", "final.vtt", "final_with_subtitles.mp4"):
                p = output_dir / name
                if p.exists():
                    try:
                        p.unlink(missing_ok=True)
                    except (PermissionError, OSError):
                        # Windows: 파일이 재생 중이면 삭제 불가 — 무시
                        pass

    elif step == "voice":
        for c in cuts:
            # Delete file if exists
            if c.audio_path:
                p = Path(c.audio_path)
                abs_p = p if p.is_absolute() else project_dir / c.audio_path
                if abs_p.exists():
                    abs_p.unlink(missing_ok=True)
            c.audio_path = None
            c.audio_duration = None
        # Remove audio dir
        audio_dir = project_dir / "audio"
        if audio_dir.exists():
            shutil.rmtree(audio_dir, ignore_errors=True)

    elif step == "image":
        for c in cuts:
            if c.image_path:
                p = Path(c.image_path)
                abs_p = p if p.is_absolute() else project_dir / c.image_path
                if abs_p.exists():
                    abs_p.unlink(missing_ok=True)
            c.image_path = None
            c.image_model = None
            c.is_custom_image = False
        image_dir = project_dir / "images"
        if image_dir.exists():
            shutil.rmtree(image_dir, ignore_errors=True)

    elif step == "video":
        for c in cuts:
            if c.video_path:
                p = Path(c.video_path)
                abs_p = p if p.is_absolute() else project_dir / c.video_path
                if abs_p.exists():
                    abs_p.unlink(missing_ok=True)
            c.video_path = None
            c.video_model = None
        video_dir = project_dir / "video"
        if video_dir.exists():
            shutil.rmtree(video_dir, ignore_errors=True)

    elif step == "youtube":
        # 유튜브 업로드 정보 초기화 (YouTube 에서 실제 삭제는 하지 않음 — 별도 API 사용)
        project.youtube_url = None
        # 썸네일 삭제
        thumb_dir = project_dir / "output"
        if thumb_dir.exists():
            for name in ("thumbnail.png", "thumbnail.jpg"):
                p = thumb_dir / name
                if p.exists():
                    try:
                        p.unlink(missing_ok=True)
                    except (PermissionError, OSError):
                        pass

    # Reset step_states
    step_states = dict(project.step_states or {})
    step_states.pop(step_num, None)
    # 대본 삭제 시 후속 스텝(음성·이미지·영상·렌더링·유튜브) 전부 초기화
    if step == "script":
        for k in ("3", "4", "5", "6", "7"):
            step_states.pop(k, None)
        project.youtube_url = None
    # 렌더링 삭제 시 유튜브 스텝도 초기화
    elif step == "subtitle":
        step_states.pop("7", None)
        project.youtube_url = None
    project.step_states = step_states
    db.commit()

    return {"status": "cleared", "step": step, "project_id": project_id}
