"""Voice generation router"""
import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import DATA_DIR
from app.services.tts.factory import get_tts_service

router = APIRouter()


def _load_script(project_id: str) -> dict:
    """Load script.json from disk"""
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.post("/{project_id}/generate")
async def generate_all_voices(project_id: str, db: Session = Depends(get_db)):
    """Generate all voices"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # Get TTS service
    tts_model = project.config.get("tts_model", "elevenlabs")
    tts_service = get_tts_service(tts_model)
    try:
        speed = float(project.config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    script = _load_script(project_id)
    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    cut_dict = {c.cut_number: c for c in cuts}

    results = []
    for cut_data in script.get("cuts", []):
        cut_number = cut_data["cut_number"]
        narration = cut_data.get("narration", "")

        if not narration:
            results.append({
                "cut_number": cut_number,
                "status": "skipped",
                "reason": "No narration"
            })
            continue

        cut = cut_dict.get(cut_number)
        if not cut:
            continue

        try:
            voice_id = project.config.get("tts_voice_id", "")
            audio_dir = DATA_DIR / project_id / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            audio_path = str(audio_dir / f"cut_{cut_number}.wav")

            result = await tts_service.generate(narration, voice_id, audio_path, speed=speed)

            cut.audio_path = result["path"]
            cut.audio_duration = result.get("duration", 0.0)
            cut.status = "completed"
            db.commit()

            results.append({
                "cut_number": cut_number,
                "status": "completed",
                "duration": cut.audio_duration,
                "path": cut.audio_path
            })
        except Exception as e:
            cut.status = "failed"
            db.commit()
            results.append({
                "cut_number": cut_number,
                "status": "failed",
                "error": str(e)
            })

    # Mark step completed
    step_states = dict(project.step_states or {})
    step_states["3"] = "completed"
    project.step_states = step_states
    db.commit()

    return {
        "project_id": project_id,
        "results": results,
        "total": len(script.get("cuts", [])),
        "completed": sum(1 for r in results if r["status"] == "completed")
    }


@router.post("/{project_id}/generate-async")
async def generate_all_voices_async(project_id: str, db: Session = Depends(get_db)):
    """Start voice generation in background — returns immediately"""
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, register_async_task, is_running

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "voice"):
        return {"status": "already_running", "step": "voice"}

    script = _load_script(project_id)
    cut_list = script.get("cuts", [])
    state = start_task(project_id, "voice", len(cut_list))

    # Update step_states to running
    step_states = dict(project.step_states or {})
    step_states["3"] = "running"
    project.step_states = step_states
    db.commit()

    async def _run():
        from app.models.database import SessionLocal
        local_db = SessionLocal()
        try:
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            if not proj:
                raise ValueError(f"Project {project_id} not found")

            tts_model = proj.config.get("tts_model", "openai-tts")
            voice_id = proj.config.get("tts_voice_id", "alloy")
            voice_preset = proj.config.get("tts_voice_preset", "ko-child-boy")

            # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
            from app import config as app_config
            if tts_model == "elevenlabs" and not app_config.ELEVENLABS_API_KEY:
                if app_config.OPENAI_API_KEY:
                    tts_model = "openai-tts"
                    voice_id = "alloy"
                else:
                    raise ValueError("No TTS API key configured (neither ElevenLabs nor OpenAI)")

            if tts_model == "openai-tts" and not app_config.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY not set for OpenAI TTS")

            tts_service = get_tts_service(tts_model)

            try:
                speed = float(proj.config.get("tts_speed", 1.0) or 1.0)
            except (TypeError, ValueError):
                speed = 1.0
            voice_settings = None
            if "child" in voice_preset:
                if tts_model == "openai-tts":
                    speed = min(4.0, speed + 0.15)
                elif tts_model == "elevenlabs":
                    voice_settings = {"stability": 0.7, "similarity_boost": 0.85}

            cuts = local_db.query(Cut).filter(Cut.project_id == project_id).all()
            cut_dict = {c.cut_number: c for c in cuts}

            if not cuts:
                raise ValueError("No cuts found — generate script first")

            for i, cut_data in enumerate(cut_list):
                if state.status != "running":
                    break
                cut_number = cut_data["cut_number"]
                narration = cut_data.get("narration", "")
                if not narration:
                    update_task(project_id, "voice", i + 1)
                    continue

                cut = cut_dict.get(cut_number)
                if not cut:
                    update_task(project_id, "voice", i + 1)
                    continue

                try:
                    audio_dir = DATA_DIR / project_id / "audio"
                    audio_dir.mkdir(parents=True, exist_ok=True)
                    audio_path = str(audio_dir / f"cut_{cut_number}.mp3")
                    result = await tts_service.generate(narration, voice_id, audio_path, speed=speed, voice_settings=voice_settings)
                    cut.audio_path = result["path"]
                    cut.audio_duration = result.get("duration", 0.0)
                    cut.status = "completed"
                    # v1.1.55-fix: 스튜디오 TTS 비용 기록
                    try:
                        from app.services import spend_ledger
                        spend_ledger.record_tts(
                            tts_model, chars=len(narration),
                            project_id=project_id, note=f"studio cut_{cut_number}",
                        )
                    except Exception as _le:
                        print(f"[spend_ledger] studio tts record skipped: {_le}")
                    local_db.commit()
                except Exception as e:
                    import traceback
                    print(f"[voice] Cut {cut_number} failed: {e}\n{traceback.format_exc()}")
                    cut.status = "failed"
                    local_db.commit()

                update_task(project_id, "voice", i + 1)

            # v1.1.55-fix: 실제 생성된 오디오 수 검증
            _audio_dir = DATA_DIR / project_id / "audio"
            _generated_audio = [
                f for f in _audio_dir.glob("cut_*.mp3")
                if f.stat().st_size > 100
            ] if _audio_dir.exists() else []

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj.step_states or {})
            if _generated_audio:
                ss["3"] = "completed"
                proj.step_states = ss
                local_db.commit()
                complete_task(project_id, "voice")
            else:
                ss["3"] = "failed"
                proj.step_states = ss
                local_db.commit()
                fail_task(project_id, "voice", f"음성 0/{len(cut_list)}개 생성됨 — TTS API 확인 필요")
        except BaseException as e:
            import traceback
            print(f"[voice] Task failed: {e}\n{traceback.format_exc()}")
            fail_task(project_id, "voice", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["3"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "voice", task)
    return {"status": "started", "step": "voice", "total": len(cut_list)}


@router.post("/{project_id}/resume-async")
async def resume_voices_async(project_id: str, db: Session = Depends(get_db)):
    """Resume voice generation — only generate cuts that don't have audio yet"""
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, register_async_task, is_running

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "voice"):
        return {"status": "already_running", "step": "voice"}

    # Find cuts missing audio
    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
    pending_cuts = [c for c in cuts if not c.audio_path and c.narration]
    if not pending_cuts:
        return {"status": "nothing_to_resume", "step": "voice", "total": 0}

    script = _load_script(project_id)
    cut_list = script.get("cuts", [])
    # Filter cut_list to only pending ones
    pending_numbers = {c.cut_number for c in pending_cuts}
    pending_cut_list = [cd for cd in cut_list if cd["cut_number"] in pending_numbers]

    state = start_task(project_id, "voice", len(pending_cut_list))

    step_states = dict(project.step_states or {})
    step_states["3"] = "running"
    project.step_states = step_states
    db.commit()

    async def _run():
        from app.models.database import SessionLocal
        local_db = SessionLocal()
        try:
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            if not proj:
                raise ValueError(f"Project {project_id} not found")

            tts_model = proj.config.get("tts_model", "openai-tts")
            voice_id = proj.config.get("tts_voice_id", "alloy")
            voice_preset = proj.config.get("tts_voice_preset", "ko-child-boy")

            # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
            from app import config as app_config
            if tts_model == "elevenlabs" and not app_config.ELEVENLABS_API_KEY:
                if app_config.OPENAI_API_KEY:
                    tts_model = "openai-tts"
                    voice_id = "alloy"

            tts_service = get_tts_service(tts_model)

            try:
                speed = float(proj.config.get("tts_speed", 1.0) or 1.0)
            except (TypeError, ValueError):
                speed = 1.0
            voice_settings = None
            if "child" in voice_preset:
                if tts_model == "openai-tts":
                    speed = min(4.0, speed + 0.15)
                elif tts_model == "elevenlabs":
                    voice_settings = {"stability": 0.7, "similarity_boost": 0.85}

            db_cuts = local_db.query(Cut).filter(Cut.project_id == project_id).all()
            cut_dict = {c.cut_number: c for c in db_cuts}

            for i, cut_data in enumerate(pending_cut_list):
                if state.status != "running":
                    break
                cut_number = cut_data["cut_number"]
                narration = cut_data.get("narration", "")
                cut = cut_dict.get(cut_number)
                if not cut or not narration:
                    update_task(project_id, "voice", i + 1)
                    continue

                try:
                    audio_dir = DATA_DIR / project_id / "audio"
                    audio_dir.mkdir(parents=True, exist_ok=True)
                    audio_path = str(audio_dir / f"cut_{cut_number}.mp3")
                    result = await tts_service.generate(narration, voice_id, audio_path, speed=speed, voice_settings=voice_settings)
                    cut.audio_path = result["path"]
                    cut.audio_duration = result.get("duration", 0.0)
                    cut.status = "completed"
                    local_db.commit()
                except Exception as e:
                    import traceback
                    print(f"[voice-resume] Cut {cut_number} failed: {e}\n{traceback.format_exc()}")
                    cut.status = "failed"
                    local_db.commit()

                update_task(project_id, "voice", i + 1)

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj.step_states or {})
            ss["3"] = "completed"
            proj.step_states = ss
            local_db.commit()
            complete_task(project_id, "voice")
        except BaseException as e:
            import traceback
            print(f"[voice-resume] Task failed: {e}\n{traceback.format_exc()}")
            fail_task(project_id, "voice", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["3"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "voice", task)
    return {"status": "started", "step": "voice", "total": len(pending_cut_list), "skipped": len(cuts) - len(pending_cuts)}


@router.post("/{project_id}/generate/{cut_number}")
async def generate_one_voice(
    project_id: str,
    cut_number: int,
    db: Session = Depends(get_db)
):
    """Regenerate one cut's voice"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cut = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == cut_number
    ).first()

    if not cut:
        raise HTTPException(404, f"Cut {cut_number} not found")

    if not cut.narration:
        raise HTTPException(400, "Cut has no narration")

    # Get TTS service
    tts_model = project.config.get("tts_model", "elevenlabs")
    tts_service = get_tts_service(tts_model)
    try:
        speed = float(project.config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    try:
        voice_id = project.config.get("tts_voice_id", "")
        audio_dir = DATA_DIR / project_id / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(audio_dir / f"cut_{cut_number}.wav")

        result = await tts_service.generate(cut.narration, voice_id, audio_path, speed=speed)

        cut.audio_path = result["path"]
        cut.audio_duration = result.get("duration", 0.0)
        cut.status = "completed"
        # v1.1.55-fix: 단건 TTS 비용 기록
        try:
            from app.services import spend_ledger
            spend_ledger.record_tts(
                tts_model, chars=len(cut.narration or ""),
                project_id=project_id, note=f"studio single cut_{cut_number}",
            )
        except Exception as _le:
            print(f"[spend_ledger] studio single tts record skipped: {_le}")
        db.commit()

        return {
            "cut_number": cut_number,
            "status": "completed",
            "duration": cut.audio_duration,
            "path": cut.audio_path
        }
    except Exception as e:
        cut.status = "failed"
        db.commit()
        raise HTTPException(500, f"Voice generation failed: {str(e)}")


class PreviewOverride(BaseModel):
    """v1.1.47: StepSettings 에서 아직 저장되지 않은 local config 로 미리듣기를
    하기 위한 오버라이드. 모든 필드는 옵셔널이고, 값이 비어있으면 저장된
    프로젝트 config 의 해당 필드로 폴백한다."""
    tts_model: Optional[str] = None
    tts_voice_id: Optional[str] = None
    tts_voice_preset: Optional[str] = None
    tts_voice_lang: Optional[str] = None
    tts_speed: Optional[float] = None


@router.post("/{project_id}/preview")
async def preview_voice(
    project_id: str,
    override: Optional[PreviewOverride] = None,
    db: Session = Depends(get_db),
):
    """Generate a short preview of the selected voice.

    v1.1.47: 옵셔널 JSON body 로 tts_model / tts_voice_id / tts_voice_preset /
    tts_voice_lang / tts_speed 를 덮어쓸 수 있다. StepSettings 화면에서
    사용자가 아직 "저장" 하지 않은 local config 로 미리듣기를 지원한다.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = project.config or {}

    def pick(attr: str, default):
        if override is not None:
            val = getattr(override, attr, None)
            if val not in (None, ""):
                return val
        return cfg.get(attr, default)

    tts_model = pick("tts_model", "openai-tts")
    voice_id = pick("tts_voice_id", "alloy")
    voice_lang = pick("tts_voice_lang", "ko")

    # API key check — fallback to openai-tts if elevenlabs key is missing
    # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
    from app import config as app_config
    if tts_model == "elevenlabs" and not app_config.ELEVENLABS_API_KEY:
        if app_config.OPENAI_API_KEY:
            tts_model = "openai-tts"
            voice_id = "alloy"
        else:
            raise HTTPException(400, "TTS API 키가 설정되지 않았습니다. 대시보드에서 API 키를 입력해주세요.")

    tts_service = get_tts_service(tts_model)
    voice_preset = pick("tts_voice_preset", "ko-child-boy")

    if voice_lang == "en":
        preview_text = "Hello! This is the voice that will narrate your video. Do you like it?"
    elif voice_lang == "ja":
        preview_text = "こんにちは！この声で動画のナレーションを行います。いかがですか？"
    else:
        preview_text = "안녕하세요! 이 목소리로 영상 나레이션을 진행하게 됩니다. 마음에 드시나요?"

    # 프로젝트 설정의 tts_speed 를 기본값으로 사용.
    try:
        raw_speed = pick("tts_speed", 1.0)
        speed = float(raw_speed if raw_speed is not None else 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    voice_settings = None
    is_child = "child" in voice_preset
    if is_child:
        if tts_model == "openai-tts":
            # OpenAI: speed up slightly to sound younger
            speed = min(4.0, speed + 0.15)
        elif tts_model == "elevenlabs":
            # ElevenLabs: higher stability for child-like consistency
            voice_settings = {"stability": 0.7, "similarity_boost": 0.85}

    try:
        preview_dir = DATA_DIR / project_id / "audio"
        preview_dir.mkdir(parents=True, exist_ok=True)
        preview_path = str(preview_dir / "voice_preview.mp3")

        result = await tts_service.generate(preview_text, voice_id, preview_path, speed=speed, voice_settings=voice_settings)

        return {
            "status": "ok",
            "path": f"audio/voice_preview.mp3",
            "duration": result.get("duration", 0),
            "voice_id": voice_id,
            "tts_model": tts_model,
        }
    except Exception as e:
        raise HTTPException(500, f"Preview failed: {str(e)}")


@router.get("/{project_id}/voices")
async def list_voices(
    project_id: str,
    tts_model: Optional[str] = Query(
        None,
        description="Optional override. 프로젝트 설정 화면에서 아직 저장되지 않은 "
                    "로컬 config 의 tts_model 로 보이스 목록을 미리 보고 싶을 때 사용.",
    ),
    db: Session = Depends(get_db),
):
    """List available voices for the requested TTS model.

    v1.1.46: optional `tts_model` query param 추가. StepSettings 에서 사용자가
    드롭다운으로 모델을 바꿨지만 아직 저장 버튼을 누르지 않은 상태에서도
    새 모델의 보이스 목록을 즉시 볼 수 있게 한다. 값이 없으면 기존처럼
    프로젝트 저장된 config 의 tts_model 을 사용.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    effective_model = tts_model or project.config.get("tts_model", "elevenlabs")
    tts_service = get_tts_service(effective_model)

    try:
        voices = await tts_service.list_voices()
        return {
            "tts_model": effective_model,
            "voices": voices,
            "current_voice_id": project.config.get("tts_voice_id", "")
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch voices: {str(e)}")
