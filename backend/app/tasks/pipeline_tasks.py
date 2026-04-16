"""Celery pipeline tasks with pause/resume/cancel + progress tracking"""
import json
import os
import time
import asyncio
import redis as redis_lib
from celery import Celery
from app.config import REDIS_URL, DATA_DIR, CUT_VIDEO_DURATION
from app.models.database import SessionLocal
from app.models.project import Project
from app.models.cut import Cut

celery_app = Celery("longtube", broker=REDIS_URL, backend=REDIS_URL)

try:
    redis_client = redis_lib.from_url(REDIS_URL)
    redis_client.ping()
except Exception:
    redis_client = None

# v1.1.52: 인메모리 fallback — Redis 없어도 같은 프로세스(OneClick) 내에서
# 진행률을 정확히 추적한다. Celery 워커는 별도 프로세스이므로 Redis 필수.
_progress_mem: dict[str, int | str] = {}


def _redis_set(key, value):
    if redis_client:
        redis_client.set(key, value)
    # 항상 인메모리에도 기록 (OneClick 용 fallback)
    try:
        _progress_mem[key] = int(value)
    except (TypeError, ValueError):
        _progress_mem[key] = value

def _redis_get(key):
    if redis_client:
        val = redis_client.get(key)
        if val is not None:
            return val
    # Redis 없거나 값 없으면 인메모리 확인
    return _progress_mem.get(key)

def _redis_incr(key):
    if redis_client:
        redis_client.incr(key)
    # 항상 인메모리에도 반영
    _progress_mem[key] = (_progress_mem.get(key, 0) if isinstance(_progress_mem.get(key), int) else 0) + 1

def _redis_delete(*keys):
    if redis_client:
        redis_client.delete(*keys)
    for k in keys:
        _progress_mem.pop(k, None)


class PipelineCancelled(Exception):
    pass


def check_pause_or_cancel(project_id: str, step: int):
    """v1.1.53: cancel 키를 삭제하지 않고 체크만 한다.
    병렬 실행(음성+이미지) 시 한 스레드가 키를 지우면 다른 스레드가 감지 못하는 문제 방지.
    cancel 키 정리는 파이프라인 종료 시점(run_pipeline/_run_sync_pipeline)에서 한다.
    """
    if _redis_get(f"pipeline:cancel:{project_id}"):
        raise PipelineCancelled(f"Step {step} cancelled")

    while _redis_get(f"pipeline:pause:{project_id}"):
        time.sleep(1)
        if _redis_get(f"pipeline:cancel:{project_id}"):
            raise PipelineCancelled(f"Step {step} cancelled while paused")


def track_progress(project_id: str, step: int):
    """컷 하나 처리 완료 후 호출 — Redis 진행률 +1"""
    _redis_incr(f"pipeline:step_progress:{project_id}:{step}")


def init_progress(project_id: str, step: int):
    """단계 시작 시 호출 — 진행률 초기화"""
    _redis_set(f"pipeline:step_progress:{project_id}:{step}", "0")
    _redis_set(f"pipeline:step_start:{project_id}:{step}", str(time.time()))


def update_project(project_id: str, **kwargs):
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        for k, v in kwargs.items():
            setattr(project, k, v)
        db.commit()
    finally:
        db.close()


def update_step_state(project_id: str, step: int, state: str):
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        states = dict(project.step_states or {})
        states[str(step)] = state
        project.step_states = states
        project.current_step = step
        db.commit()
    finally:
        db.close()


def load_script(project_id: str) -> dict:
    path = DATA_DIR / project_id / "script.json"
    # v1.1.37 bugfix: encoding 미지정 시 Windows 에선 기본이 cp949 로 떨어져
    # "UnicodeDecodeError: 'cp949' codec can't decode byte 0xe2 ..." 발생.
    # save_script 가 utf-8 + ensure_ascii=False 로 저장하므로 읽기도 동일하게 맞춘다.
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_script(project_id: str, script: dict):
    path = DATA_DIR / project_id / "script.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True)
def run_pipeline(self, project_id: str, start_step: int = 2, end_step: int = 5):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    config = project.config
    auto_pause = config.get("auto_pause_after_step", True)
    db.close()

    # Pipeline 순서 (v1.1.32 이후, 자막 스텝 제거):
    #   2 대본 → 3+4 음성&이미지 (병렬) → 5 영상 → 6 렌더링(수동) → 7 유튜브(수동)
    steps = {
        2: ("대본 생성", _step_script),
        3: ("음성 생성", _step_voice),
        4: ("이미지 생성", _step_image),
        5: ("영상 생성", _step_video),
        7: ("유튜브 업로드", _step_upload),
    }

    # 단일 스텝 실행 헬퍼
    def _run_single(step_num):
        step_name, step_func = steps[step_num]
        update_step_state(project_id, step_num, "running")
        init_progress(project_id, step_num)
        update_project(project_id, status="processing")
        try:
            step_func(project_id, config)
            update_step_state(project_id, step_num, "completed")
        except PipelineCancelled:
            update_step_state(project_id, step_num, "cancelled")
            raise
        except Exception:
            update_step_state(project_id, step_num, "failed")
            raise

    # auto_pause 대기 헬퍼
    def _wait_if_auto_pause(step_num):
        if auto_pause and step_num < end_step:
            update_project(project_id, status="paused")
            _redis_set(f"pipeline:pause:{project_id}", "1")
            while _redis_get(f"pipeline:pause:{project_id}"):
                time.sleep(1)
                if _redis_get(f"pipeline:cancel:{project_id}"):
                    raise PipelineCancelled("Cancelled while paused")

    # v1.1.53: 실행 순서 결정 — step 3+4 는 병렬
    serial_order = []
    for s in range(start_step, end_step + 1):
        if s in steps:
            serial_order.append(s)

    i = 0
    while i < len(serial_order):
        step_num = serial_order[i]

        # ── step 3+4 병렬 실행 ──
        # start_step 이 3 또는 4 에 걸쳐 있으면 해당 범위만 병렬
        if step_num == 3 and (i + 1 < len(serial_order)) and serial_order[i + 1] == 4:
            parallel_steps = [3, 4]
            print(f"[Pipeline] ★ 음성(3) + 이미지(4) 병렬 실행 시작")
            errors = {}
            try:
                with ThreadPoolExecutor(max_workers=2, thread_name_prefix="step") as pool:
                    futures = {pool.submit(_run_single, s): s for s in parallel_steps}
                    for fut in as_completed(futures):
                        s = futures[fut]
                        try:
                            fut.result()
                        except PipelineCancelled:
                            raise
                        except Exception as e:
                            errors[s] = e
                if errors:
                    # 하나라도 실패하면 실패 처리 (첫 번째 에러 raise)
                    first_step = min(errors.keys())
                    update_project(project_id, status="failed")
                    raise errors[first_step]
            except PipelineCancelled:
                # 둘 다 cancelled 로 마킹
                for s in parallel_steps:
                    update_step_state(project_id, s, "cancelled")
                update_project(project_id, status="paused")
                return

            # 병렬 완료 후 auto_pause (4 기준)
            try:
                _wait_if_auto_pause(4)
            except PipelineCancelled:
                update_project(project_id, status="paused")
                return

            i += 2  # 3, 4 를 같이 처리했으므로 2칸 전진
            continue

        # ── 일반 순차 실행 ──
        try:
            _run_single(step_num)
            _wait_if_auto_pause(step_num)
        except PipelineCancelled:
            update_step_state(project_id, step_num, "cancelled")
            update_project(project_id, status="paused")
            return
        except Exception:
            update_project(project_id, status="failed")
            raise

        i += 1

    # v1.1.53: 파이프라인 종료 — cancel 키 정리
    _redis_delete(f"pipeline:cancel:{project_id}")
    update_project(project_id, status="completed")


def _step_script(project_id: str, config: dict):
    """Step 2: 대본 생성

    v1.1.48: LLM 호출은 단건이라 중간 인터럽트가 불가능하지만,
    호출 직전/직후에 check_pause_or_cancel 을 걸어
    (a) 큐 대기 직후 사용자가 취소를 눌렀다면 LLM 을 아예 안 돌리고,
    (b) LLM 이 끝난 직후 취소가 들어와 있으면 저장/컷 생성 없이 빠진다.
    이전에는 이 단계에 cancel 체크가 전혀 없어 `중지` 가 먹통처럼 보였다.
    """
    from app.services.llm.factory import get_llm_service

    # v1.1.48: LLM 호출 전 취소 확인
    check_pause_or_cancel(project_id, 2)

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()

    service = get_llm_service(config["script_model"])
    script = run_async(service.generate_script(project.topic, config))

    # v1.1.55: 지출 기록 — LLM 호출 토큰을 근사치로 계산해 원장에 append.
    # 실제 토큰수를 서비스에서 안 돌려주므로 입력(주제) / 출력(대본 전체 텍스트)
    # 문자열 길이를 4자 = 1토큰 룰로 환산한다. 가격표 기반 감산이라 잔액 추세
    # 파악용으로 충분하다.
    try:
        from app.services import spend_ledger
        in_text = str(project.topic or "") + str(config or "")
        out_text = json.dumps(script, ensure_ascii=False)
        spend_ledger.record_llm(
            config["script_model"],
            input_tokens=max(1, len(in_text) // 4),
            output_tokens=max(1, len(out_text) // 4),
            project_id=project_id,
            note="script",
        )
    except Exception as _e:
        print(f"[spend_ledger] script record skipped: {_e}")

    # v1.1.48: LLM 완료 후에도 확인 — 여기서 raise 되면 저장/컷 생성 스킵
    check_pause_or_cancel(project_id, 2)

    save_script(project_id, script)

    db.query(Cut).filter(Cut.project_id == project_id).delete()
    for c in script.get("cuts", []):
        cut = Cut(
            project_id=project_id,
            cut_number=c["cut_number"],
            narration=c.get("narration"),
            image_prompt=c.get("image_prompt"),
            scene_type=c.get("scene_type"),
            status="pending",
        )
        db.add(cut)
        track_progress(project_id, 2)

    project.total_cuts = len(script.get("cuts", []))
    project.title = script.get("title", project.title)
    db.commit()
    db.close()

    # v1.1.53: 대본 완성 직후 썸네일 생성 — 이미지 단계 전에 미리 만들어 UI에 표시
    _generate_thumbnail_sync(project_id, config, script)


def _step_voice(project_id: str, config: dict):
    """Step 3: 음성 생성 — 스튜디오(voice.py)와 동일한 로직."""
    from app.services.tts.factory import get_tts_service

    script = load_script(project_id)

    # v1.1.55: 스튜디오와 동일 — TTS 폴백 + voice_preset + voice_settings
    tts_model = config.get("tts_model", "openai-tts")
    voice_id = config.get("tts_voice_id", "alloy")
    voice_preset = config.get("tts_voice_preset", "")

    from app.config import ELEVENLABS_API_KEY, OPENAI_API_KEY
    if tts_model == "elevenlabs" and not ELEVENLABS_API_KEY:
        if OPENAI_API_KEY:
            print(f"[Voice] ElevenLabs API 키 없음 → OpenAI TTS 폴백")
            tts_model = "openai-tts"
            voice_id = "alloy"
        else:
            raise ValueError("No TTS API key configured (neither ElevenLabs nor OpenAI)")
    if tts_model == "openai-tts" and not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY not set for OpenAI TTS")

    service = get_tts_service(tts_model)

    try:
        speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    # voice_preset 에 따른 보정 (스튜디오와 동일)
    voice_settings = None
    if voice_preset and "child" in voice_preset:
        if tts_model == "openai-tts":
            speed = min(4.0, speed + 0.15)
        elif tts_model == "elevenlabs":
            voice_settings = {"stability": 0.7, "similarity_boost": 0.85}

    project_dir = DATA_DIR / project_id

    db = SessionLocal()
    for cut_data in script.get("cuts", []):
        check_pause_or_cancel(project_id, 3)

        num = cut_data["cut_number"]
        output = str(project_dir / "audio" / f"cut_{num:03d}.mp3")

        # v1.1.52: 이미 생성된 파일이 있으면 건너뛴다 (이어하기 지원)
        if os.path.exists(output) and os.path.getsize(output) > 100:
            print(f"[Voice] Cut {num} 이미 존재 — 건너뜀")
            track_progress(project_id, 3)
            continue

        result = run_async(
            service.generate(cut_data["narration"], voice_id, output, speed=speed, voice_settings=voice_settings)
        )

        # v1.1.55: 지출 기록 — TTS 는 문자수 * per_1k. 실제 과금 단위와 동일.
        try:
            from app.services import spend_ledger
            spend_ledger.record_tts(
                tts_model,
                chars=len(cut_data.get("narration") or ""),
                project_id=project_id,
                note=f"cut_{num:03d}",
            )
        except Exception as _e:
            print(f"[spend_ledger] tts record skipped: {_e}")

        # v1.1.55: TTS 호출 완료 직후에도 취소 확인 — 다음 컷 진입 전에 빠져나감
        check_pause_or_cancel(project_id, 3)

        cut_data["actual_duration"] = result["duration"]

        cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
        if cut:
            cut.audio_path = result["path"]
            cut.audio_duration = result["duration"]
            cut.status = "voice_done"

        track_progress(project_id, 3)

    db.commit()
    db.close()
    save_script(project_id, script)


def build_thumbnail_prompt(script: dict) -> str:
    """v1.1.55: 썸네일 프롬프트 — 파이프라인 & 재생성 공용.

    script.json 에 thumbnail_prompt 가 있으면 그대로 사용하고,
    없으면 title 기반 기본 프롬프트를 반환한다.
    """
    thumb_prompt = (script.get("thumbnail_prompt") or "").strip()
    if thumb_prompt:
        return thumb_prompt
    title = script.get("title", "")
    return (
        f"A captivating, eye-catching YouTube thumbnail for '{title}'. "
        f"A dramatic close-up scene with vivid emotion (wide-eyed surprise, "
        f"intense curiosity, genuine awe). Cinematic lighting, high contrast, "
        f"rich saturated colors, shallow depth of field. "
        f"Designed to maximize viewer curiosity and clicks. "
        f"16:9 landscape composition, 4K ultra-detailed photo quality. "
        f"ABSOLUTELY NO text, letters, words, numbers, watermarks, or UI elements."
    )


def _generate_thumbnail_sync(project_id: str, config: dict, script: dict):
    """v1.1.55: 대본 생성 직후 썸네일을 동기적으로 생성한다.

    스튜디오의 YouTube 썸네일 생성(ai_overlay)과 **완전 동일한 시퀀스**:
    1. thumbnail_prompt → AI 이미지 모델로 1280x720 배경 생성
    2. Pillow 텍스트 오버레이 (메인 후크 = title, EP 배지, 보조 라인)

    이미 thumbnail.png 가 있으면 건너뛴다. 실패해도 파이프라인을 막지 않는다.
    Redis 키 `thumbnail:status:{pid}` 에 generating / done / failed 를 기록.
    """
    from app.services.image.prompt_builder import collect_reference_images
    from app.services.thumbnail_service import generate_ai_thumbnail

    thumb_path = DATA_DIR / project_id / "output" / "thumbnail.png"
    if thumb_path.exists() and thumb_path.stat().st_size > 100:
        print(f"[Thumbnail] 이미 존재 — 건너뜀")
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return

    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    # 상태: 생성 시작
    _redis_set(f"thumbnail:status:{project_id}", "generating")

    thumb_prompt = build_thumbnail_prompt(script)
    image_model = config.get("thumbnail_model") or config.get("image_model") or "openai-image-1"

    # 메인 후크 텍스트: title 에서 "EP. N · " 접두사 제거
    title = (script.get("title") or "").strip()
    import re
    overlay_title = re.sub(r"^EP\.\s*\d+\s*[·\-]\s*", "", title).strip() or title

    # 레퍼런스 + 캐릭터 이미지 수집
    from app.services.image.prompt_builder import collect_character_images
    char_paths = collect_character_images(project_id, config)
    ref_paths = collect_reference_images(project_id, config)
    seen: set[str] = set()
    combined_refs: list[str] = []
    for p in [*char_paths, *ref_paths]:
        if p not in seen:
            seen.add(p)
            combined_refs.append(p)

    # v1.1.55: 스튜디오와 동일 — 레퍼런스 미지원 모델이면 nano-banana-3 폴백
    if combined_refs:
        from app.services.image.factory import get_image_service as _get_img_svc
        _probe = _get_img_svc(image_model)
        if not getattr(_probe, "supports_reference_images", False):
            print(f"[Thumbnail] {image_model} 는 레퍼런스 미지원 → nano-banana-3 폴백")
            image_model = "nano-banana-3"

    # v1.1.55: 공통 REFERENCE_STYLE_PREFIX 사용 — 컷/썸네일/재생성 문구 통일
    if combined_refs and thumb_prompt:
        from app.services.image.prompt_builder import apply_reference_style_prefix
        thumb_prompt = apply_reference_style_prefix(thumb_prompt, has_reference=True)

    try:
        result = run_async(generate_ai_thumbnail(
            project_id=project_id,
            image_prompt=thumb_prompt,
            image_model_id=image_model,
            overlay_title_text=overlay_title,
            overlay_subtitle=None,
            overlay_episode_label=None,
            output_path=str(thumb_path),
            reference_images=combined_refs or None,
        ))
        # v1.1.55: 썸네일 이미지 1장 지출 기록
        try:
            from app.services import spend_ledger
            spend_ledger.record_image(
                image_model, n_images=1,
                project_id=project_id, note="thumbnail",
            )
        except Exception as _e:
            print(f"[spend_ledger] thumbnail record skipped: {_e}")
        _redis_set(f"thumbnail:status:{project_id}", "done")
        print(f"[Thumbnail] 생성 완료 (overlay={result.get('overlay_applied')}): {result.get('path')}")
    except Exception as e:
        import traceback
        err_detail = f"{type(e).__name__}: {e}"
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_detail[:300]}")
        print(f"[Thumbnail] 생성 실패 (컷 이미지 생성은 계속): {err_detail}")
        print(f"[Thumbnail] traceback:\n{traceback.format_exc()}")


def _step_image(project_id: str, config: dict):
    """Step 4: 이미지 생성

    v1.1.52: 스튜디오(image.py router)와 **완전히 동일한** 로직으로 이미지 생성.
    - _build_image_prompt: 글로벌 스타일, 레퍼런스 유무, 캐릭터 설명을 프롬프트에 반영
    - _collect_reference_images / _collect_character_images: 레퍼런스/캐릭터 이미지 수집
    - cut_has_character: 3컷마다 캐릭터 슬롯
    - reference_images 파라미터 전달
    - v1.1.52: 이미지 컷 생성 전에 썸네일을 먼저 생성

    v1.1.49: 동시 4장 병렬 생성.
    """
    from app.services.image.factory import get_image_service, IMAGE_REGISTRY
    from app.services.image.base import get_size
    from app.services.image.prompt_builder import (
        build_image_prompt,
        collect_reference_images,
        collect_character_images,
        cut_has_character,
    )

    # v1.1.56: 로컬 ComfyUI 는 동시 1 로 강제 (GPU 순차 큐).
    _img_model = config.get("image_model", "")
    _is_comfy_img = IMAGE_REGISTRY.get(_img_model, {}).get("provider") == "comfyui"
    CONCURRENT = 1 if _is_comfy_img else 4

    script = load_script(project_id)

    width, height = get_size(config.get("aspect_ratio", "16:9"))
    project_dir = DATA_DIR / project_id

    # ★ 레퍼런스/캐릭터 수집 — 레퍼런스가 있으면 스타일은 레퍼런스에서만
    ref_images = collect_reference_images(project_id, config)
    char_images = collect_character_images(project_id, config)
    # v1.1.58: 레퍼런스가 있으면 global_style 무시 (레퍼런스가 스타일의 전부)
    global_style = "" if ref_images else config.get("image_global_prompt", "")
    character_description = (config.get("character_description") or "").strip()
    # v1.1.60: 캐릭터 이미지/설명이 실제로 있는 프리셋만 캐릭터 컷을 활성화한다.
    # 이게 없으면 cut_has_character() 가 1·4·7번에 무조건 "main character" 텍스트를
    # 주입해서, 스타일 레퍼런스에 등장하는 인물이 캐릭터로 차용되는 사고가 난다.
    has_character_anchor = bool(char_images) or bool(character_description)

    # v1.1.55: 스튜디오와 동일 — 레퍼런스가 있는데 모델이 미지원이면 nano-banana-3 폴백
    image_model_id = config["image_model"]
    if ref_images or char_images:
        _probe = get_image_service(image_model_id)
        if not getattr(_probe, "supports_reference_images", False):
            print(f"[Image] {image_model_id} 는 레퍼런스 미지원 → nano-banana-3 폴백")
            image_model_id = "nano-banana-3"

    service = get_image_service(image_model_id)
    # v1.1.59: 사용자 네거티브 프롬프트 주입 (ComfyUI 만 반영; 그 외 서비스는 무시)
    try:
        service.negative_prompt = (config.get("image_negative_prompt") or "").strip()
    except Exception:
        pass

    db = SessionLocal()
    all_cuts = script.get("cuts", [])

    # 커스텀 이미지 또는 이미 생성된 이미지는 건너뛰기
    to_generate = []
    for cut_data in all_cuts:
        num = cut_data["cut_number"]
        cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
        if cut and cut.is_custom_image:
            track_progress(project_id, 4)
            continue
        # v1.1.52: 이미 생성된 파일이 있으면 건너뛴다 (이어하기 지원)
        existing = project_dir / "images" / f"cut_{num:03d}.png"
        if existing.exists() and existing.stat().st_size > 50:
            print(f"[Image] Cut {num} 이미 존재 — 건너뜀")
            track_progress(project_id, 4)
            continue
        to_generate.append((cut_data, cut))

    # 병렬 생성 (배치 단위)
    for batch_start in range(0, len(to_generate), CONCURRENT):
        check_pause_or_cancel(project_id, 4)
        batch = to_generate[batch_start:batch_start + CONCURRENT]

        async def _gen_batch(items):
            sem = asyncio.Semaphore(CONCURRENT)

            async def _one(cut_data, cut_row):
                async with sem:
                    # v1.1.58 [HOTFIX 돈줄 차단]: 컷 단위 cancel 체크.
                    # 이전엔 배치 시작 시점에만 검사해서 4컷이 모두 in-flight 인
                    # 동안 사용자가 중지/삭제해도 API 호출이 모두 끝까지 진행되어
                    # 돈이 새는 사고가 났다. 이제는 매 컷 호출 직전에도 cancel 을
                    # 검사하여 즉시 중단한다.
                    if _redis_get(f"pipeline:cancel:{project_id}"):
                        return
                    num = cut_data["cut_number"]
                    output = str(project_dir / "images" / f"cut_{num:03d}.png")

                    # ★ 스튜디오와 동일: 캐릭터 슬롯 + 프롬프트 조합
                    is_char_cut = cut_has_character(num) and has_character_anchor
                    prompt = build_image_prompt(
                        cut_data.get("image_prompt", ""),
                        global_style,
                        has_reference=bool(ref_images),
                        has_character_slot=is_char_cut,
                        character_description=character_description,
                    )

                    # ★ 레퍼런스 이미지: 스타일 레퍼런스 + 캐릭터 슬롯이면 캐릭터 이미지
                    all_refs = list(ref_images)
                    if char_images and is_char_cut:
                        all_refs.extend(char_images)

                    try:
                        await service.generate(
                            prompt, width, height, output,
                            reference_images=all_refs if all_refs else None,
                        )
                        # v1.1.55: 성공한 컷 이미지 1장 지출 기록
                        try:
                            from app.services import spend_ledger
                            spend_ledger.record_image(
                                image_model_id, n_images=1,
                                project_id=project_id, note=f"cut_{num:03d}",
                            )
                        except Exception as _e:
                            print(f"[spend_ledger] image record skipped: {_e}")
                        if cut_row:
                            cut_row.image_path = f"images/cut_{num:03d}.png"
                            cut_row.image_model = config["image_model"]
                            cut_row.status = "image_done"
                        track_progress(project_id, 4)
                    except Exception as e:
                        print(f"[Image] Cut {num} failed: {e}")
                        track_progress(project_id, 4)

            tasks = [_one(cd, cr) for cd, cr in items]
            await asyncio.gather(*tasks, return_exceptions=True)

        run_async(_gen_batch(batch))

    db.commit()
    db.close()

    # v1.1.55 hotfix: 이미지가 하나도 생성되지 않았으면 실패 처리.
    # 이전엔 개별 실패를 무시하고 step 을 "완료"로 마킹해서, 다음 step(영상)이
    # 이미지 없이 실행되어 머지 실패로 이어지는 사고가 났다.
    import os as _img_os
    _generated = [
        f for f in (project_dir / "images").glob("cut_*.png")
        if f.stat().st_size > 50
    ] if (project_dir / "images").exists() else []
    if not _generated:
        raise RuntimeError(
            f"이미지가 하나도 생성되지 않았습니다 (총 {len(all_cuts)}컷). "
            f"이미지 모델({config.get('image_model', '?')}) API 키와 연결 상태를 확인하세요."
        )
    print(f"[Image] 완료: {len(_generated)}/{len(all_cuts)} 이미지 생성됨")

    # v1.1.59: ComfyUI 로컬 모델 사용 시, 배치 종료 후 VRAM 해제.
    # 외부 API(Nano/OpenAI/Fal)만 썼다면 호출해도 no-op 에 가까움 (서버가 놀고 있으므로).
    try:
        from app.services.image.factory import IMAGE_REGISTRY
        img_provider = IMAGE_REGISTRY.get(config.get("image_model", ""), {}).get("provider")
        if img_provider == "comfyui":
            from app.services import comfyui_client
            run_async(comfyui_client.free_memory())
    except Exception as _e:
        print(f"[Image] VRAM 해제 스킵: {_e}")


def _probe_audio_seconds(audio_path: str) -> float:
    """ffprobe 로 오디오 길이(초) 측정. 실패시 0.0."""
    try:
        import subprocess as _sp
        from app.services.video.subprocess_helper import find_ffmpeg as _ff
        ffprobe = _ff().replace("ffmpeg", "ffprobe")
        out = _sp.check_output(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            timeout=10,
        )
        return float((out or b"0").decode().strip() or 0)
    except Exception as _e:
        print(f"[probe] {audio_path}: {_e}")
        return 0.0


async def _burn_cut_subtitle(
    cut_video_path: str,
    narration: str,
    duration: float,
    style_config: dict,
    aspect_ratio: str,
) -> bool:
    """v1.1.55: 단일 컷 mp4 에 자기 대사 자막을 in-place 로 번인.

    싱크 보장의 핵심: 대사가 0~`duration` 안에 균등 분포하므로 머지 후에도
    클립 길이 변형(ensure_min_duration 등) 과 무관하게 각 컷의 자막이 자기
    클립 안에서만 살아 있다. 실패해도 원본 파일은 보존되고 False 반환.

    v1.1.55 hotfix: 이전엔 `run_async()` 로 새 이벤트 루프를 돌렸는데,
    호출 지점(`_one`)이 이미 async 컨텍스트라 "This event loop is already
    running" RuntimeError 로 자막이 전혀 안 붙었다. async 함수로 바꿔서
    호출부에서 `await` 로 직접 돌린다.
    """
    if not narration or not narration.strip() or duration <= 0:
        return False
    try:
        from app.services.subtitle_service import generate_single_cut_ass
        from app.services.video.ffmpeg_service import FFmpegService as _FF
        ass_text = generate_single_cut_ass(
            narration, duration, style_config or {}, aspect_ratio,
        )
        from pathlib import Path as _P
        cut_p = _P(cut_video_path)
        ass_p = cut_p.with_suffix(".cut.ass")
        ass_p.write_text(ass_text, encoding="utf-8")
        tmp_out = str(cut_p.with_suffix(".sub.mp4"))
        await _FF.burn_subtitles(cut_video_path, str(ass_p), tmp_out)
        # 성공 → 원본 덮어쓰기
        import shutil as _sh
        _sh.move(tmp_out, cut_video_path)
        try:
            ass_p.unlink()
        except Exception:
            pass
        return True
    except Exception as _e:
        import traceback
        print(f"[Video] cut subtitle burn 실패 {cut_video_path}: {_e}")
        print(traceback.format_exc())
        return False


def _step_video(project_id: str, config: dict):
    """Step 5: 영상 생성

    v1.1.52: 스튜디오(video.py router)와 **완전히 동일한** 로직으로 영상 생성.
    - video_model 에 따라 AI 비디오 서비스(fal/kling 등) 또는 FFmpeg 사용
    - video_target_selection 에 따라 AI/static 분기
    - _build_video_motion_prompt 로 컷별 모션 프롬프트 생성
    - primary 실패 시 ffmpeg-static 폴백
    - 동시 4개 병렬 생성
    - v1.1.55: 각 컷 mp4 가 만들어지자마자 자기 대사 자막을 바로 번인
      (머지 후 자막 싱크 깨짐 사고 차단)
    """
    from app.services.video.factory import get_video_service, VIDEO_REGISTRY
    from app.services.video.prompt_builder import (
        should_generate_ai_video,
        build_video_motion_prompt,
    )

    # v1.1.56: 로컬 ComfyUI 는 GPU 1개 큐라 동시 N 개 보내도 순차 처리 → 동시 1 로 강제.
    # 체감상 1번 컷이 먼저 완료돼 progress 가 빨리 돌고 총 시간은 동일.
    _video_model = config.get("video_model", "ffmpeg-kenburns")
    _is_comfy_video = VIDEO_REGISTRY.get(_video_model, {}).get("provider") == "comfyui"
    CONCURRENT = 1 if _is_comfy_video else 4

    script = load_script(project_id)
    project_dir = DATA_DIR / project_id

    # ★ 스튜디오와 동일: config 에서 video_model, selection, aspect_ratio 읽기
    video_model = config.get("video_model", "ffmpeg-kenburns")
    selection = config.get("video_target_selection", "all")
    ai_first_n = int(config.get("ai_video_first_n", 5) or 0)
    aspect_ratio = config.get("aspect_ratio", "16:9")

    primary_service = get_video_service(video_model)
    fallback_service = (
        primary_service
        if video_model == "ffmpeg-static"
        else get_video_service("ffmpeg-static")
    )

    # v1.1.55: 컷 자막 스타일 — DEFAULT_CONFIG 의 subtitle_style 와 동일 키.
    subtitle_style_cfg = config.get("subtitle_style") or {}

    db = SessionLocal()
    all_cuts = script.get("cuts", [])
    total_cuts = len(all_cuts)
    video_paths = []

    # v1.1.55 hotfix: 이미지 파일 사전 검증 — 이미지가 없으면 영상 생성 불가
    _img_dir = project_dir / "images"
    _existing_imgs = [
        f for f in _img_dir.glob("cut_*.png") if f.stat().st_size > 50
    ] if _img_dir.exists() else []
    if not _existing_imgs:
        raise RuntimeError(
            f"이미지 파일이 하나도 없습니다 ({_img_dir}). "
            f"이미지 생성 단계(step 4)를 먼저 실행하세요."
        )
    print(f"[Video] 사전 검증: {len(_existing_imgs)}/{total_cuts} 이미지 존재")

    # v1.1.52: 이미 생성된 영상은 건너뛰고 경로만 수집 (이어하기 지원)
    to_generate = []
    for cut_data in all_cuts:
        num = cut_data["cut_number"]
        existing = project_dir / "videos" / f"cut_{num:03d}.mp4"
        if existing.exists() and existing.stat().st_size > 50:
            print(f"[Video] Cut {num} 이미 존재 — 건너뜀")
            video_paths.append(str(existing))
            track_progress(project_id, 5)
            continue
        to_generate.append(cut_data)

    # 배치 단위 병렬 처리
    for batch_start in range(0, len(to_generate), CONCURRENT):
        check_pause_or_cancel(project_id, 5)
        batch = to_generate[batch_start:batch_start + CONCURRENT]

        async def _gen_batch(items):
            sem = asyncio.Semaphore(CONCURRENT)

            async def _one(cut_data):
                async with sem:
                    num = cut_data["cut_number"]
                    img = str(project_dir / "images" / f"cut_{num:03d}.png")
                    aud = str(project_dir / "audio" / f"cut_{num:03d}.mp3")
                    out = str(project_dir / "videos" / f"cut_{num:03d}.mp4")

                    # ★ 스튜디오와 동일: AI/static 분기 + 모션 프롬프트
                    use_ai = should_generate_ai_video(num, selection, ai_first_n)
                    svc = primary_service if use_ai else fallback_service
                    used_model = video_model if use_ai else "ffmpeg-static"
                    motion_prompt = build_video_motion_prompt(
                        num, total_cuts, config,
                    )

                    try:
                        await svc.generate(
                            image_path=img,
                            audio_path=aud,
                            duration=float(CUT_VIDEO_DURATION),
                            output_path=out,
                            aspect_ratio=aspect_ratio,
                            prompt=motion_prompt,
                        )
                    except Exception as e:
                        # ★ primary 실패 시 fallback 으로 재시도
                        if use_ai and svc is not fallback_service:
                            print(f"[Video] Cut {num} primary({video_model}) 실패, ffmpeg-static 폴백: {e}")
                            await fallback_service.generate(
                                image_path=img,
                                audio_path=aud,
                                duration=float(CUT_VIDEO_DURATION),
                                output_path=out,
                                aspect_ratio=aspect_ratio,
                                prompt="",
                            )
                            used_model = "ffmpeg-static"
                        else:
                            raise

                    # v1.1.55: 컷 mp4 가 생긴 직후 자기 대사 자막 번인.
                    # 머지/normalize 후에 자막 입히면 컷 길이 변경으로 싱크가
                    # 깨지는 사고 → 컷 단계에서 0~audio_duration 에 정확히
                    # 박아 둔다. 실패해도 영상 자체는 그대로.
                    try:
                        narration = (cut_data.get("narration") or "").strip()
                        # 1) DB 에 audio_duration 이 이미 있으면 그거 사용
                        # 2) 없으면 ffprobe 로 측정
                        cut_row = (
                            db.query(Cut)
                            .filter(Cut.project_id == project_id, Cut.cut_number == num)
                            .first()
                        )
                        dur = float(getattr(cut_row, "audio_duration", 0) or 0)
                        if dur <= 0:
                            dur = _probe_audio_seconds(aud)
                        if narration and dur > 0:
                            ok = await _burn_cut_subtitle(
                                out, narration, dur,
                                subtitle_style_cfg, aspect_ratio,
                            )
                            if ok:
                                print(f"[Video] Cut {num} 자막 번인 완료 ({dur:.1f}s)")
                            else:
                                print(f"[Video] Cut {num} 자막 번인 건너뜀")
                    except Exception as _se:
                        print(f"[Video] Cut {num} subtitle stage 예외(무시): {_se}")

                    return num, out, used_model

            tasks = [_one(cd) for cd in items]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = run_async(_gen_batch(batch))

        for r in results:
            if isinstance(r, Exception):
                import traceback as _tb
                print(f"[Video] batch item failed: {type(r).__name__}: {r}")
                print(f"[Video]   traceback: {''.join(_tb.format_exception(type(r), r, r.__traceback__))[-500:]}")
                track_progress(project_id, 5)
                continue
            num, output, used_model = r
            # v1.1.55: AI 비디오 성공 클립만 지출 기록 (ffmpeg-static 은 무과금)
            if used_model and used_model != "ffmpeg-static":
                try:
                    from app.services import spend_ledger
                    spend_ledger.record_video(
                        used_model, n_clips=1,
                        project_id=project_id, note=f"cut_{num:03d}",
                    )
                except Exception as _e:
                    print(f"[spend_ledger] video record skipped: {_e}")
            video_paths.append(output)
            cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
            if cut:
                # v1.1.55: 스튜디오와 동일하게 상대 경로 저장
                cut.video_path = f"videos/cut_{num:03d}.mp4"
                cut.video_model = used_model
                cut.status = "video_done"
            track_progress(project_id, 5)

    merged = str(project_dir / "output" / "merged.mp4")
    from app.services.video.ffmpeg_service import FFmpegService as _FFmpeg
    if not video_paths:
        raise RuntimeError(
            f"영상 클립이 하나도 생성되지 않았습니다 (총 {len(all_cuts)}컷). "
            f"이미지/오디오 파일이 모두 존재하는지 확인하세요."
        )
    # 존재하지 않는 파일 필터링 + 경고
    import os as _os
    _missing = [p for p in video_paths if not _os.path.exists(p)]
    if _missing:
        print(f"[Video] WARNING: {len(_missing)}개 클립 파일 누락 — 제외하고 머지: {_missing[:3]}")
        video_paths = [p for p in video_paths if _os.path.exists(p)]
    if not video_paths:
        raise RuntimeError("영상 클립 파일이 모두 디스크에서 누락되었습니다.")
    run_async(_FFmpeg.merge_videos(video_paths, merged))

    db.commit()
    db.close()

    # v1.1.59: ComfyUI 로컬 영상 모델 사용 시 VRAM 해제.
    try:
        from app.services.video.factory import VIDEO_REGISTRY
        vid_provider = VIDEO_REGISTRY.get(config.get("video_model", ""), {}).get("provider")
        if vid_provider == "comfyui":
            from app.services import comfyui_client
            run_async(comfyui_client.free_memory())
    except Exception as _e:
        print(f"[Video] VRAM 해제 스킵: {_e}")

    # ── v1.1.55: 영상 생성 직후 자막 + 오프닝/엔딩 자동 합성 ──
    # 사용자 요구: "렌더할 때 오프닝 꼭 집어 넣고. 영상만들때 자막도 한꺼번에 붙여."
    # 기존엔 step 6(렌더링) 이 수동 트리거였는데, 이제 step 5 가 끝나면 자동으로
    # final_with_subtitles.mp4 를 생성한다 (오프닝/엔딩 + 자막 번인 포함).
    # 실패해도 step 5 자체는 완료로 마킹 — 사용자가 수동 재시도 가능.
    try:
        from app.routers.subtitle import render_video_with_subtitles
        from app.models.database import SessionLocal as _SL
        _local_db = _SL()
        try:
            print(f"[Pipeline] step5 후속 자동 렌더 시작 (자막+오프닝 통합)")
            res = run_async(render_video_with_subtitles(project_id, db=_local_db))
            opening_used = res.get("opening_used") if isinstance(res, dict) else None
            ending_used = res.get("ending_used") if isinstance(res, dict) else None
            if opening_used is False:
                print(
                    f"[Pipeline] ⚠ 오프닝 미설정 — 최종 영상에 오프닝이 포함되지 않았습니다. "
                    f"interlude 설정을 확인하세요."
                )
            else:
                print(
                    f"[Pipeline] ✓ 자동 렌더 완료 (opening={opening_used}, ending={ending_used})"
                )
        finally:
            _local_db.close()
    except Exception as _e:
        import traceback
        print(f"[Pipeline] ⚠ 후속 자동 렌더 실패 (step 5 는 완료 처리): {_e}")
        print(traceback.format_exc())


def _step_upload(project_id: str, config: dict):
    """Step 7: 유튜브 업로드 (v1.1.32 이후 자막 스텝 제거됨)"""
    from app.services.youtube_service import YouTubeUploader

    script = load_script(project_id)
    project_dir = DATA_DIR / project_id

    # 프로젝트별 YouTube 계정 우선, 없으면 전역 토큰 fallback.
    _pu = YouTubeUploader(project_id=project_id)
    uploader = _pu if _pu.is_authenticated() else YouTubeUploader()

    # 업로드 소스 우선순위:
    #   1. 자막 번인 + 오프닝/엔딩 페이드 영상 (final_with_subtitles.mp4)
    #   2. (v1.1.29) 간지 포함 영상 (final_with_interludes.mp4)
    #   3. (legacy) 파이프라인 기본 산출물 (final.mp4)
    from pathlib import Path as _Path
    _output_dir = project_dir / "output"
    _candidates = [
        _output_dir / "final_with_subtitles.mp4",
        _output_dir / "final_with_interludes.mp4",
        _output_dir / "final.mp4",
    ]
    _video_path = next((p for p in _candidates if _Path(p).exists()), _candidates[-1])

    result = run_async(uploader.upload(
        video_path=str(_video_path),
        title=script.get("title", "Untitled"),
        description=script.get("description", ""),
        tags=script.get("tags", []),
        thumbnail_path=str(
            # v1.1.57: AI 생성 썸네일 우선, 없으면 첫 번째 컷 이미지 폴백
            project_dir / "output" / "thumbnail.png"
            if _Path(project_dir / "output" / "thumbnail.png").exists()
            else project_dir / "images" / "cut_001.png"
        ),
        privacy="private",
    ))

    update_project(project_id, youtube_url=result["url"])
