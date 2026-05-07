"""Celery pipeline tasks with pause/resume/cancel + progress tracking"""
import json
import os
import re
import time
import asyncio
import redis as redis_lib
from celery import Celery
from app.config import REDIS_URL, DATA_DIR, CUT_VIDEO_DURATION, resolve_project_dir
from app.models.database import SessionLocal
from app.models.project import Project
from app.models.cut import Cut
from app.services.title_utils import script_title_for_language, with_episode_prefix, without_episode_prefix
from app.services.llm.visual_policy import apply_script_visual_policy, normalize_cut_image_prompt, normalize_image_prompt
from app.services.youtube_metadata import expand_tags, format_description
from app.services.multilingual_caption_service import should_upload_youtube_captions, upload_multilingual_captions

celery_app = Celery("longtube", broker=REDIS_URL, backend=REDIS_URL)

try:
    redis_client = redis_lib.from_url(REDIS_URL)
    redis_client.ping()
except Exception:
    redis_client = None

# v1.1.52: 인메모리 fallback — Redis 없어도 같은 프로세스(OneClick) 내에서
# 진행률을 정확히 추적한다. Celery 워커는 별도 프로세스이므로 Redis 필수.
_progress_mem: dict[str, int | str] = {}


def _safe_console(value) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _resolve_image_reuse_seconds(config: dict, db) -> int:
    """Use the current template value for oneclick projects before generating images."""
    try:
        reuse_seconds = int(float((config or {}).get("image_reuse_group_seconds") or 0))
    except (TypeError, ValueError):
        reuse_seconds = 0

    cfg = config or {}
    template_project_id = cfg.get("template_project_id")
    if not cfg.get("__oneclick__") or not template_project_id:
        return reuse_seconds

    try:
        tmpl = db.query(Project).filter(Project.id == template_project_id).first()
        tmpl_cfg = (tmpl.config or {}) if tmpl else {}
        if "image_reuse_group_seconds" in tmpl_cfg:
            return int(float(tmpl_cfg.get("image_reuse_group_seconds") or 0))
    except Exception as e:
        print(f"[Image] template image reuse lookup skipped: {e}")
    return reuse_seconds


def _redis_set(key, value):
    """v1.2.29: redis 가 중간에 죽어도 예외를 밖으로 올리지 않는다.
    redis 실패는 무시하고 `_progress_mem` 에 반드시 기록해, 같은 프로세스 안의
    cancel 체크는 절대 누락되지 않게 한다. (이전엔 redis.set 예외가 호출자의
    try/except 로 올라가면서 `_progress_mem` 업데이트가 스킵되어, 워커 스레드의
    cancel 체크가 영원히 False 를 반환하는 사고가 있었음.)
    """
    try:
        if redis_client:
            redis_client.set(key, value)
    except Exception:
        pass
    # 항상 인메모리에도 기록 (redis 장애 대비 + OneClick 용 fallback)
    try:
        _progress_mem[key] = int(value)
    except (TypeError, ValueError):
        _progress_mem[key] = value

def _redis_get(key):
    """v1.2.29: redis 예외 시 조용히 `_progress_mem` 로 떨어진다. None 반환이
    아니라 실패를 삼키는 이유: cancel 체크 경로에서 예외가 위로 전파되면 is_cancelled
    가 `except Exception: return False` 로 묵살해 긴급 정지가 무효화됐다.
    """
    try:
        if redis_client:
            val = redis_client.get(key)
            if val is not None:
                return val
    except Exception:
        pass
    # Redis 없거나 값 없으면 인메모리 확인
    return _progress_mem.get(key)

def _redis_incr(key):
    try:
        if redis_client:
            redis_client.incr(key)
    except Exception:
        pass
    # 항상 인메모리에도 반영
    _progress_mem[key] = (_progress_mem.get(key, 0) if isinstance(_progress_mem.get(key), int) else 0) + 1

def _redis_delete(*keys):
    try:
        if redis_client:
            redis_client.delete(*keys)
    except Exception:
        pass
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
    path = resolve_project_dir(project_id) / "script.json"
    # v1.1.37 bugfix: encoding 미지정 시 Windows 에선 기본이 cp949 로 떨어져
    # "UnicodeDecodeError: 'cp949' codec can't decode byte 0xe2 ..." 발생.
    # save_script 가 utf-8 + ensure_ascii=False 로 저장하므로 읽기도 동일하게 맞춘다.
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _ensure_project_layout(project_id: str):
    project_dir = resolve_project_dir(project_id, create=True)
    project_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("audio", "images", "videos", "subtitles", "output"):
        (project_dir / sub).mkdir(parents=True, exist_ok=True)
    return project_dir


def save_script(project_id: str, script: dict, language: str = "ko"):
    try:
        from app.services.shorts_service import annotate_script_shorts
        script = annotate_script_shorts(script)
    except Exception:
        pass
    for cut_data in script.get("cuts", []) or []:
        if isinstance(cut_data, dict):
            cut_data.pop("motion_prompt", None)
            cut_data.pop("video_motion_prompt", None)
    project_dir = _ensure_project_layout(project_id)
    path = project_dir / "script.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)


_PREPARED_SCRIPT_DIRS = ("대본", "scripts", "prepared_scripts")


def _compact_match_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def _prepared_episode_number(script: dict, path) -> int | None:
    for value in (
        script.get("episode_number"),
        script.get("episode"),
        script.get("ep"),
    ):
        try:
            number = int(value)
            if number > 0:
                return number
        except (TypeError, ValueError):
            pass
    match = re.search(r"(?:ep|episode)?[_\-. ]*0*(\d{1,4})", path.stem, re.IGNORECASE)
    if match:
        try:
            number = int(match.group(1))
            if number > 0:
                return number
        except (TypeError, ValueError):
            pass
    return None


def _validate_prepared_script(script: dict, source_path) -> None:
    if not isinstance(script, dict):
        raise RuntimeError(f"사전작성 대본 형식 오류: JSON object 아님 ({source_path})")
    cuts = script.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise RuntimeError(f"사전작성 대본 형식 오류: cuts 없음 ({source_path})")
    required_cut_keys = (
        "cut_number",
        "narration",
        "image_prompt",
        "visual_year",
        "visual_period",
        "visual_location",
        "visual_evidence",
    )
    for idx, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            raise RuntimeError(f"사전작성 대본 형식 오류: cut {idx} object 아님 ({source_path})")
        missing = [key for key in required_cut_keys if not str(cut.get(key) or "").strip()]
        if missing:
            raise RuntimeError(
                f"사전작성 대본 형식 오류: cut {idx} 필수값 누락 {missing} ({source_path})"
            )


def _load_prepared_script(project_id: str, config: dict, topic: str) -> tuple[dict, str] | None:
    project_dir = resolve_project_dir(project_id)
    try:
        target_episode = int(config.get("episode_number") or 0)
    except (TypeError, ValueError):
        target_episode = 0
    target_topic = _compact_match_key(topic)
    candidates: list[tuple[int, dict, str]] = []
    for dirname in _PREPARED_SCRIPT_DIRS:
        script_dir = project_dir / dirname
        if not script_dir.is_dir():
            continue
        for path in sorted(script_dir.glob("*.json")):
            try:
                script = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise RuntimeError(f"사전작성 대본 읽기 실패: {path} ({type(exc).__name__}: {exc})") from exc
            _validate_prepared_script(script, path)
            episode = _prepared_episode_number(script, path)
            script_topic = _compact_match_key(script.get("topic") or script.get("title"))
            stem_key = _compact_match_key(path.stem)
            episode_match = bool(target_episode and episode == target_episode)
            topic_match = bool(target_topic and (target_topic in script_topic or target_topic in stem_key))
            score = 0
            if episode_match:
                score += 100
            if topic_match:
                score += 50
            if score:
                candidates.append((score, script, str(path)))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]


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
    from app.services.tts.voice_profile import ensure_voice_profile_from_config
    # v1.2.25: 서비스 레이어의 raise_if_cancelled() 가 작동하도록
    # 현재 워커 스레드의 cancel 키 세팅. 함수 끝에서 None 으로 해제.
    from app.services.cancel_ctx import (
        OperationCancelled as _OperationCancelled,
        set_cancel_key as _set_cancel_key,
    )
    _set_cancel_key(project_id)

    # v1.1.48: LLM 호출 전 취소 확인
    check_pause_or_cancel(project_id, 2)
    _ensure_project_layout(project_id)

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()

    script_config = dict(config or {})
    script_config["__project_id"] = project_id
    service = get_llm_service(script_config["script_model"])
    try:
        run_async(ensure_voice_profile_from_config(script_config, log=print))
    except Exception as _e:
        print(f"[voice-profile] warning: using default timing because profiling failed: {_e}")
    prepared = _load_prepared_script(project_id, script_config, project.topic)
    # v2.1.2: API 500 등 일시적 에러 시 최대 3회 재시도 (5초 간격)
    import time as _time
    _max_api_retries = 3
    script = None

    def _sleep_with_cancel(seconds: float):
        deadline = _time.monotonic() + float(seconds)
        while True:
            check_pause_or_cancel(project_id, 2)
            remaining = deadline - _time.monotonic()
            if remaining <= 0:
                return
            _time.sleep(min(0.25, remaining))

    if prepared:
        script, prepared_path = prepared
        print(f"[Script] prepared script 사용: {_safe_console(prepared_path)}")
    else:
        for _attempt in range(1, _max_api_retries + 1):
            check_pause_or_cancel(project_id, 2)
            try:
                script = run_async(service.generate_script(project.topic, script_config))
                check_pause_or_cancel(project_id, 2)
                break
            except (_OperationCancelled, PipelineCancelled):
                raise
            except Exception as _e:
                _err_str = str(_e)
                _timed_out = "timed out" in _err_str.lower() or "timeout" in _err_str.lower()
                _is_retryable = (
                    not _timed_out
                    and any(k in _err_str for k in ("500", "502", "503", "529", "overloaded"))
                )
                if _is_retryable and _attempt < _max_api_retries:
                    print(f"[Script] attempt {_attempt}/{_max_api_retries} failed ({_err_str[:100]}), retrying in 5s...")
                    _sleep_with_cancel(5)
                    continue
                raise
    if script is None:
        raise RuntimeError("Script generation failed")
    script = apply_script_visual_policy(script)
    service.assert_script_timing(script, script_config)

    # v1.1.48: LLM 완료 후에도 취소 여부 확인
    check_pause_or_cancel(project_id, 2)

    script["title"] = script_title_for_language(
        generated_title=script.get("title"),
        project_title=project.title,
        topic=project.topic,
        episode_number=config.get("episode_number"),
        language=config.get("language", "ko"),
        first_narration=(script.get("cuts") or [{}])[0].get("narration") if script.get("cuts") else None,
    )
    save_script(project_id, script, config.get("language", "ko"))

    db.query(Cut).filter(Cut.project_id == project_id).delete()
    for c in script.get("cuts", []):
        cut = Cut(
            project_id=project_id,
            cut_number=c["cut_number"],
            narration=c.get("narration"),
            image_prompt=normalize_image_prompt(c.get("image_prompt") or ""),
            scene_type=c.get("scene_type"),
            status="pending",
        )
        db.add(cut)
        track_progress(project_id, 2)

    project.total_cuts = len(script.get("cuts", []))
    db.commit()
    db.close()

    # v1.1.53: 대본 완성 직후 썸네일 생성 — 이미지 단계 전에 미리 만들어 UI에 표시
    _generate_thumbnail_sync(project_id, config, script)

    # v1.2.25: cancel 키 해제 — 다음 step 에서 같은 스레드가 재사용될 때
    # 이전 project 의 플래그를 오인하지 않도록.
    try:
        from app.services.cancel_ctx import set_cancel_key as _set_cancel_key
        _set_cancel_key(None)
    except Exception:
        pass


def _step_voice(project_id: str, config: dict):
    """Step 3: 음성 생성 — 스튜디오(voice.py)와 동일한 로직.

    v1.2.25: ElevenLabs / OpenAI TTS 레이어가 cancel 시 바로 이탈하도록
    워커 스레드의 cancel 키를 세팅. 함수 끝에서 해제.
    """
    from app.services.tts.factory import get_tts_service
    from app.services.tts.narration_fit import generate_tts_with_auto_narration_fit
    # v1.2.25: TTS 서비스들이 raise_if_cancelled() 를 탈 수 있게 키 세팅.
    from app.services.cancel_ctx import (
        OperationCancelled as _OperationCancelled,
        set_cancel_key as _set_cancel_key,
    )
    _set_cancel_key(project_id)
    project_dir = _ensure_project_layout(project_id)

    script = load_script(project_id)

    # v1.1.55: 스튜디오와 동일 — TTS 폴백 + voice_preset + voice_settings
    tts_model = config.get("tts_model", "openai-tts")
    voice_id = config.get("tts_voice_id", "alloy")
    voice_preset = config.get("tts_voice_preset", "")

    # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
    # (로컬 변수 `config` 와의 이름 충돌을 피하기 위해 별칭 사용)
    # v1.2.20: ElevenLabs → OpenAI TTS 폴백 제거. 사용자 요구 — 선택 모델의
    # API 가 없으면 다른 모델로 갈아치우지 않고 명시적 에러로 실패.
    from app import config as app_config
    if tts_model == "elevenlabs" and not app_config.ELEVENLABS_API_KEY:
        raise RuntimeError(
            "[Voice] ElevenLabs 가 선택되어 있는데 ELEVENLABS_API_KEY 가 비어있습니다. "
            "폴백 비활성화 — 키를 등록하거나 TTS 모델을 OpenAI 로 바꾸세요."
        )
    if tts_model == "openai-tts" and not app_config.OPENAI_API_KEY:
        raise RuntimeError(
            "[Voice] OpenAI TTS 가 선택되어 있는데 OPENAI_API_KEY 가 비어있습니다. "
            "키를 등록하거나 TTS 모델을 ElevenLabs 로 바꾸세요."
        )

    service = get_tts_service(tts_model)

    try:
        speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        speed = 1.0

    # voice_preset 에 따른 보정 (스튜디오와 동일)
    voice_settings = None
    if voice_preset and "child" in voice_preset:
        if tts_model == "elevenlabs":
            voice_settings = {"stability": 0.7, "similarity_boost": 0.85}

    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    topic = project.topic if project else ""

    def _generate_tts_result(cut_data: dict, output_path: str, total_cuts: int, spoken_narration: str) -> dict:
        spoken_cut_data = dict(cut_data)
        spoken_cut_data["narration"] = spoken_narration
        return run_async(
            generate_tts_with_auto_narration_fit(
                service,
                spoken_narration,
                voice_id,
                output_path,
                speed=speed,
                voice_settings=voice_settings,
                config=config,
                topic=topic,
                language=config.get("language", "ko"),
                cut_number=int(cut_data.get("cut_number") or 0),
                total_cuts=total_cuts,
                cut_data=spoken_cut_data,
                script=script,
                log=lambda msg: print(f"[Voice] {msg}"),
            )
        )

    script_cuts = script.get("cuts", [])
    script_dirty = False
    for cut_data in script_cuts:
        check_pause_or_cancel(project_id, 3)
        num = cut_data["cut_number"]
        output = str(project_dir / "audio" / f"cut_{num:03d}.mp3")
        original_narration = (cut_data.get("narration") or "").strip()
        cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
        has_matching_db_audio = bool(
            cut
            and (cut.audio_path or "").strip()
            and (cut.narration or "").strip() == original_narration
        )

        # 이미 생성된 파일은 절대 삭제/재생성하지 않는다. API 비용 누수를 막기 위해
        # 길이가 어긋난 기존 음성도 로컬 FFmpeg 보정만 수행한다.
        if has_matching_db_audio and os.path.exists(output) and os.path.getsize(output) > 100:
            try:
                from app.services.tts.narration_fit import ensure_audio_duration_window
                existing_dur = service._get_duration(output)
                fitted_dur = ensure_audio_duration_window(
                    output,
                    float(existing_dur or 0.0),
                    config=config,
                    log=lambda msg: print(f"[Voice] {msg}"),
                )
                if fitted_dur != existing_dur:
                    print(
                        f"[Voice] Cut {num} 기존 음성 FFmpeg 보정 "
                        f"{existing_dur:.2f}s -> {fitted_dur:.2f}s, API 재호출 없음"
                    )
                else:
                    print(f"[Voice] Cut {num} 이미 존재 — 길이 OK({existing_dur:.2f}s), 건너뜀")
                cut_data["actual_duration"] = fitted_dur
                cut_data["actual_original_duration"] = existing_dur or fitted_dur
                if cut:
                    cut.audio_path = f"audio/cut_{num:03d}.mp3"
                    cut.audio_duration = fitted_dur
                    cut.audio_original_duration = existing_dur or fitted_dur
                    cut.status = "voice_done"
                track_progress(project_id, 3)
                continue
            except Exception as e:
                print(f"[Voice] Cut {num} 기존 음성 로컬 보정 실패, API 재생성 차단: {e}")
                track_progress(project_id, 3)
                continue

        from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts
        spoken_narration = prepare_spoken_narration_for_tts(
            original_narration,
            config.get("language", "ko"),
        )
        result = _generate_tts_result(cut_data, output, len(script_cuts), spoken_narration)
        try:
            from app.services.tts.narration_fit import ensure_audio_duration_window
            original_duration = result.get("original_duration") or result.get("duration", 0.0)
            result["duration"] = ensure_audio_duration_window(
                output,
                float(result.get("duration") or 0.0),
                config=config,
                log=lambda msg: print(f"[Voice] {msg}"),
            )
            result["original_duration"] = original_duration
        except Exception as _fit_e:
            print(f"[Voice] final duration guard skipped cut {num}: {_fit_e}")

        # v1.1.55: 지출 기록 — TTS 는 문자수 * per_1k. 실제 과금 단위와 동일.
        try:
            from app.services import spend_ledger
            spend_ledger.record_tts(
                tts_model,
                chars=len(original_narration),
                project_id=project_id,
                note=f"cut_{num:03d}",
            )
        except Exception as _e:
            print(f"[spend_ledger] tts record skipped: {_e}")

        # v1.1.55: TTS 호출 완료 직후에도 취소 확인 — 다음 컷 진입 전에 빠져나감
        check_pause_or_cancel(project_id, 3)

        cut_data["actual_duration"] = result["duration"]
        cut_data["actual_original_duration"] = result.get("original_duration") or result["duration"]

        cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
        if cut:
            cut.narration = original_narration
            cut.audio_path = result["path"]
            cut.audio_duration = result["duration"]
            cut.audio_original_duration = result.get("original_duration") or result["duration"]
            cut.status = "voice_done"

        track_progress(project_id, 3)

    db.commit()
    db.close()
    save_script(project_id, script, config.get("language", "ko"))

    # v1.2.25: cancel 키 해제.
    try:
        _set_cancel_key(None)
    except Exception:
        pass


def build_thumbnail_prompt(script: dict) -> str:
    """v1.1.55: 썸네일 프롬프트 — 파이프라인 & 재생성 공용.

    script.json 에 thumbnail_prompt 가 있으면 그대로 사용하고,
    없으면 title 기반 기본 프롬프트를 반환한다.
    """
    from app.services.thumbnail_service import build_standard_thumbnail_prompt
    return build_standard_thumbnail_prompt(script)


def _generate_thumbnail_sync(project_id: str, config: dict, script: dict):
    """v1.1.55: 대본 생성 직후 썸네일을 동기적으로 생성한다.

    스튜디오의 YouTube 썸네일 생성(ai_overlay)과 **완전 동일한 시퀀스**:
    1. thumbnail_prompt → AI 이미지 모델로 1280x720 배경 생성
    2. Pillow 텍스트 오버레이 (메인 후크 = title, EP 배지, 보조 라인)

    이미 thumbnail.png 가 있으면 건너뛴다. 실패해도 파이프라인을 막지 않는다.
    Redis 키 `thumbnail:status:{pid}` 에 generating / done / failed 를 기록.

    v1.2.25: 썸네일 이미지 API 호출이 cancel 시 바로 이탈하도록 thread-local
    cancel 키 세팅. _step_script 경로 안에서는 이미 세팅돼 있지만, 재생성 경로
    등 단독 호출 시에도 방어선이 서야 하므로 여기서도 한 번 더 건다.
    """
    from app.services.image.prompt_builder import (
        collect_reference_images,
        should_enable_historical_guard_for_context,
    )
    from app.services.thumbnail_service import (
        generate_ai_thumbnail,
        extract_thumbnail_text_parts,
        build_clickbait_thumbnail_overlay,
        suppress_foreign_hangul_thumbnail_overlay,
        normalize_episode_label,
    )
    from app.services.image.factory import resolve_image_model
    # v1.2.25: 썸네일 이미지 모델 호출 중 cancel 감지용.
    from app.services.cancel_ctx import (
        OperationCancelled as _OperationCancelled,
        set_cancel_key as _set_cancel_key,
    )
    _set_cancel_key(project_id)

    thumb_path = DATA_DIR / project_id / "output" / "thumbnail.png"
    if thumb_path.exists() and thumb_path.stat().st_size > 100:
        print(f"[Thumbnail] 이미 존재 — 건너뜀")
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return

    thumb_path.parent.mkdir(parents=True, exist_ok=True)

    # 상태: 생성 시작
    _redis_set(f"thumbnail:status:{project_id}", "generating")

    try:
        from app.services.thumbnail_service import ensure_standard_thumbnail

        result_path = run_async(ensure_standard_thumbnail(
            project_id=project_id,
            config=config,
            script=script,
            title=script.get("title"),
            topic=script.get("topic"),
            episode_number=config.get("episode_number"),
        ))
        try:
            from app.services import spend_ledger
            from app.services.image.factory import DEFAULT_THUMBNAIL_MODEL
            spend_ledger.record_image(
                resolve_image_model(config.get("thumbnail_model") or DEFAULT_THUMBNAIL_MODEL),
                n_images=1,
                project_id=project_id,
                note="thumbnail",
            )
        except Exception as _e:
            print(f"[spend_ledger] thumbnail record skipped: {_e}")
        _redis_set(f"thumbnail:status:{project_id}", "done")
        print(f"[Thumbnail] generated: {_safe_console(result_path)}")
        return
    except Exception as e:
        import traceback
        err_detail = f"{type(e).__name__}: {e}"
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_detail[:300]}")
        print(f"[Thumbnail] failed; continuing image cuts: {_safe_console(err_detail)}")
        print(f"[Thumbnail] traceback:\n{_safe_console(traceback.format_exc())}")
        return
    finally:
        try:
            _set_cancel_key(None)
        except Exception:
            pass

    thumb_prompt = build_thumbnail_prompt(script)
    from app.services.image.factory import DEFAULT_THUMBNAIL_MODEL

    image_model = resolve_image_model(
        config.get("thumbnail_model") or DEFAULT_THUMBNAIL_MODEL
    )

    title = (script.get("title") or "").strip()
    overlay_seed = build_clickbait_thumbnail_overlay(script, title, config)
    overlay_title, extracted_episode_label = extract_thumbnail_text_parts(overlay_seed or title, None)
    overlay_title = suppress_foreign_hangul_thumbnail_overlay(overlay_title, config)
    episode_no = config.get("episode_number")
    overlay_episode_label = normalize_episode_label(str(episode_no)) if episode_no else extracted_episode_label

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
    enable_historical_guard = should_enable_historical_guard_for_context(
        config,
        project_id,
        script.get("title"),
        script.get("topic"),
    )

    # v2.1.2 → v1.2.20: 레퍼런스 미지원 모델 처리.
    # ComfyUI 로컬: 레퍼런스만 무시 (모델 유지) — GPU 비용 0이라 사용자 의도 우선.
    # API 모델: 폴백 금지. 사용자 요구 — "API 이용할 때 설정된 모델의 API 연결
    # 안되있을때 알림창 띄우고 풀백으로 처리하지마." 명시적 RuntimeError 로 실패시켜
    # task.error 에 박힌다.
    if combined_refs:
        from app.services.image.factory import get_image_service as _get_img_svc, IMAGE_REGISTRY as _IMG_REG
        _probe = _get_img_svc(image_model)
        if not getattr(_probe, "supports_reference_images", False):
            _thumb_is_comfyui = _IMG_REG.get(image_model, {}).get("provider") == "comfyui"
            if _thumb_is_comfyui:
                print(f"[Thumbnail] {image_model} 는 레퍼런스 미지원이지만 로컬 GPU → 레퍼런스 무시")
                combined_refs = []
            else:
                raise RuntimeError(
                    f"[Thumbnail] 선택한 모델 '{image_model}' 은(는) 레퍼런스 이미지를 "
                    f"지원하지 않습니다. 폴백 비활성화 — 모델을 nano-banana 계열로 "
                    f"바꾸거나 레퍼런스를 제거하세요."
                )

    # v1.1.55: 공통 REFERENCE_STYLE_PREFIX 사용 — 컷/썸네일/재생성 문구 통일
    if combined_refs and thumb_prompt:
        from app.services.image.prompt_builder import apply_reference_style_prefix
        thumb_prompt = apply_reference_style_prefix(
            thumb_prompt,
            has_reference=True,
            enable_historical_guard=enable_historical_guard,
        )

    try:
        result = run_async(generate_ai_thumbnail(
            project_id=project_id,
            image_prompt=thumb_prompt,
            image_model_id=image_model,
            overlay_title_text=overlay_title,
            overlay_subtitle=None,
            overlay_episode_label=overlay_episode_label,
            output_path=str(thumb_path),
            reference_images=combined_refs or None,
            enable_historical_guard=enable_historical_guard,
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
        print(
            "[Thumbnail] generated "
            f"(overlay={result.get('overlay_applied')}): {_safe_console(result.get('path'))}"
        )
    except Exception as e:
        import traceback
        err_detail = f"{type(e).__name__}: {e}"
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_detail[:300]}")
        print(f"[Thumbnail] failed; continuing image cuts: {_safe_console(err_detail)}")
        print(f"[Thumbnail] traceback:\n{_safe_console(traceback.format_exc())}")
    finally:
        # v1.2.25: cancel 키 해제. (예외 경로에서도 반드시 돌려놔야 다음
        # 워커 스레드 재사용 시 오인하지 않는다.)
        try:
            _set_cancel_key(None)
        except Exception:
            pass


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
    from app.services.image.factory import (
        get_image_service,
        IMAGE_REGISTRY,
        resolve_image_model,
    )
    from app.services.image.base import get_size
    from app.services.image.prompt_builder import (
        append_prompt_specific_negative_prompt,
        build_image_prompt,
        collect_reference_images,
        collect_character_images,
        cut_has_character,
        should_enable_historical_guard_for_context,
        historical_negative_prompt,
        map_negative_prompt,
        symbol_negative_prompt,
        text_negative_prompt,
    )
    from app.services.image.asset_guard import (
        canonical_cut_image_path,
        find_existing_cut_image,
        image_matches_prompt,
        write_prompt_sidecar,
    )

    # v1.1.56: 로컬 ComfyUI 는 동시 1 로 강제 (GPU 순차 큐).
    _img_model = resolve_image_model(config.get("image_model"))
    _is_comfy_img = IMAGE_REGISTRY.get(_img_model, {}).get("provider") == "comfyui"
    CONCURRENT = 1 if _is_comfy_img else 4

    project_dir = _ensure_project_layout(project_id)
    script = load_script(project_id)
    script = apply_script_visual_policy(script)

    width, height = get_size(config.get("aspect_ratio", "16:9"))

    # ★ 레퍼런스/캐릭터 수집 — 레퍼런스가 있으면 스타일은 레퍼런스에서만
    ref_images = collect_reference_images(project_id, config)
    char_images = collect_character_images(project_id, config)
    global_style = config.get("image_global_prompt", "")
    character_description = (config.get("character_description") or "").strip()
    enable_historical_guard = should_enable_historical_guard_for_context(
        config,
        project_id,
        config.get("title"),
        config.get("topic"),
    )
    enable_historical_negative_guard = enable_historical_guard
    # v1.1.60: 캐릭터 이미지/설명이 실제로 있는 프리셋만 캐릭터 컷을 활성화한다.
    # 이게 없으면 cut_has_character() 가 1·4·7번에 무조건 "main character" 텍스트를
    # 주입해서, 스타일 레퍼런스에 등장하는 인물이 캐릭터로 차용되는 사고가 난다.
    has_character_anchor = bool(char_images) or bool(character_description)

    image_model_id = _img_model
    config["image_model"] = image_model_id
    _is_local_comfyui = IMAGE_REGISTRY.get(image_model_id, {}).get("provider") == "comfyui"
    if _is_local_comfyui:
        enable_historical_guard = True

    # v1.2.16: 이 시점의 실제 사용 모델을 oneclick task["models"]["image"] 에
    # 반영한다. Live 페이지의 "실제 사용 모델" 라벨이 폴백된 모델까지 반영하도록.
    # oneclick 이 아닌 Studio(Celery) 경로에서는 해당 task 가 없어 no-op.
    try:
        from app.services.oneclick_service import update_task_image_model
        update_task_image_model(project_id, image_model_id)
    except Exception:
        pass

    service = get_image_service(image_model_id)
    is_comfyui_image = IMAGE_REGISTRY.get(image_model_id, {}).get("provider") == "comfyui"
    if is_comfyui_image:
        try:
            from app.services.oneclick_service import append_task_log, update_task_sub_status

            service.progress_log = (
                lambda msg, level="info": append_task_log(project_id, msg, level)
            )
            service.progress_status = (
                lambda text: update_task_sub_status(project_id, text)
            )
        except Exception:
            pass
    # v1.1.59: 사용자 네거티브 프롬프트 주입 (ComfyUI 만 반영; 그 외 서비스는 무시)
    try:
        negative_prompt = (config.get("image_negative_prompt") or "").strip()
        text_negative = text_negative_prompt()
        if text_negative and text_negative not in negative_prompt:
            negative_prompt = f"{text_negative}, {negative_prompt}".strip(" ,")
        map_negative = map_negative_prompt()
        if map_negative and map_negative not in negative_prompt:
            negative_prompt = f"{map_negative}, {negative_prompt}".strip(" ,")
        symbol_negative = symbol_negative_prompt()
        if symbol_negative and symbol_negative not in negative_prompt:
            negative_prompt = f"{symbol_negative}, {negative_prompt}".strip(" ,")
        guard_negative = historical_negative_prompt(
            " ".join(
                str(x or "")
                for x in (
                    project_id,
                    config.get("title"),
                    config.get("topic"),
                    config.get("image_global_prompt"),
                    script.get("title"),
                    script.get("topic"),
                )
            ),
            enable_historical_negative_guard,
        )
        if guard_negative and guard_negative not in negative_prompt:
            negative_prompt = f"{guard_negative}, {negative_prompt}".strip(" ,")
        service.negative_prompt = negative_prompt
    except Exception:
        pass
    base_negative_prompt = (getattr(service, "negative_prompt", "") or "").strip()

    db = SessionLocal()
    all_cuts = script.get("cuts", [])
    shorts_cut_nums: set[int] = set()
    try:
        from app.services.shorts_service import select_shorts_segments
        for seg in select_shorts_segments(script):
            for value in seg.get("cut_numbers") or []:
                try:
                    shorts_cut_nums.add(int(value))
                except (TypeError, ValueError):
                    pass
    except Exception as _e:
        print(f"[Image] shorts cut reuse guard skipped: {_e}")
    reuse_seconds = _resolve_image_reuse_seconds(config, db)
    reuse_group_cuts = 0
    if reuse_seconds > 0:
        reuse_group_cuts = max(1, round(reuse_seconds / float(CUT_VIDEO_DURATION)))
    image_reuse_pairs: list[tuple[int, int]] = []

    # 커스텀 이미지는 유지하되, 일반 이미지는 현재 프롬프트와 맞을 때만 건너뛴다.
    to_generate = []
    custom_done_nums: set[int] = set()
    for cut_data in all_cuts:
        num = cut_data["cut_number"]
        cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == num).first()
        if cut and cut.is_custom_image:
            custom_done_nums.add(int(num))
            track_progress(project_id, 4)
            continue
        is_shorts_cut = (
            cut_data.get("shorts_candidate") is True
            or int(cut_data.get("shorts_group") or 0) > 0
            or int(num) in shorts_cut_nums
        )
        if reuse_group_cuts > 1 and not is_shorts_cut:
            anchor_num = ((int(num) - 1) // reuse_group_cuts) * reuse_group_cuts + 1
            if int(num) != anchor_num:
                image_reuse_pairs.append((int(num), int(anchor_num)))
                if cut:
                    cut.image_path = None
                    cut.status = "pending"
                continue
        is_char_cut = cut_has_character(num) and has_character_anchor
        prompt_source = (cut.image_prompt if cut and cut.image_prompt else cut_data.get("image_prompt", "")) or ""
        prompt_narration = (cut.narration if cut and cut.narration else cut_data.get("narration", "")) or ""
        prompt = build_image_prompt(
            normalize_cut_image_prompt(
                prompt_source,
                prompt_narration,
                " ".join(str(x or "") for x in (config.get("title"), config.get("topic"))),
            ),
            global_style,
            has_reference=bool(ref_images),
            has_character_slot=is_char_cut,
            character_description=character_description,
            enable_historical_guard=enable_historical_guard,
        )
        existing = find_existing_cut_image(project_dir, num)
        if existing:
            matches, reason = image_matches_prompt(
                existing,
                source_prompt=prompt_source,
                final_prompt=prompt,
                image_model=image_model_id,
            )
            if matches:
                print(f"[Image] Cut {num} 현재 프롬프트와 일치 — 건너뜀 ({reason})")
                if cut:
                    cut.image_path = str(existing.relative_to(project_dir)).replace("\\", "/")
                    cut.image_model = image_model_id
                    cut.status = "image_done"
                track_progress(project_id, 4)
                continue
            print(f"[Image] Cut {num} 기존 이미지 프롬프트 불일치 — 재생성 ({reason})")
            if cut:
                cut.image_path = None
                cut.status = "pending"
        to_generate.append((cut_data, cut, prompt))

    # v1.2.24: ComfyUI 호출층 (comfyui_client.submit/wait_for) 이 cancel 을
    # 감지할 수 있도록 현재 스레드의 cancel 키를 세팅. 워커 스레드가 `_step_image`
    # 진입시 한번 세팅하면, 같은 스레드 안에서 일어나는 모든 run_async → submit/
    # wait_for 가 이 키를 통해 `pipeline:cancel:<project_id>` 플래그를 확인한다.
    try:
        from app.services import comfyui_client as _cfy
        _cfy.set_cancel_key(project_id)
    except Exception as _e:
        print(f"[Image] cancel key 세팅 실패: {_e}")

    if is_comfyui_image:
        try:
            from app.services import comfyui_client as _cfy
            run_async(_cfy.system_stats())
        except Exception as e:
            msg = f"ComfyUI 연결 실패: {type(e).__name__}: {e}"
            try:
                from app.services.oneclick_service import append_task_log
                append_task_log(project_id, msg, "error")
            except Exception:
                pass
            raise RuntimeError(msg) from e

    # v1.2.26: 외부 API(이미지) 서비스 — fal.ai(nano-banana, seedream, z-image,
    # flux), OpenAI(dall-e), Grok 등 — 이 raise_if_cancelled() 로 즉시 이탈
    # 가능하도록 thread-local cancel 키도 같이 세팅. 사용자 보고 "제작 중단
    # 버튼 동작 안한다 — 누르면 모든 api 생성 요청도 중단 시켜야 해" 의 핵심
    # 누락분. 기존엔 ComfyUI 키만 있어 외부 API 호출에는 cancel 신호가 닿지
    # 않았다.
    from app.services.cancel_ctx import (
        OperationCancelled as _OperationCancelled,
        set_cancel_key as _set_cancel_key,
    )
    _set_cancel_key(project_id)

    # 병렬 생성 (배치 단위)
    for batch_start in range(0, len(to_generate), CONCURRENT):
        check_pause_or_cancel(project_id, 4)
        batch = to_generate[batch_start:batch_start + CONCURRENT]

        async def _gen_batch(items):
            sem = asyncio.Semaphore(CONCURRENT)

            async def _one(cut_data, cut_row, prompt):
                async with sem:
                    # v1.1.58 [HOTFIX 돈줄 차단]: 컷 단위 cancel 체크.
                    # 이전엔 배치 시작 시점에만 검사해서 4컷이 모두 in-flight 인
                    # 동안 사용자가 중지/삭제해도 API 호출이 모두 끝까지 진행되어
                    # 돈이 새는 사고가 났다. 이제는 매 컷 호출 직전에도 cancel 을
                    # 검사하여 즉시 중단한다.
                    if _redis_get(f"pipeline:cancel:{project_id}"):
                        raise PipelineCancelled(f"Step 4 cancelled before cut {cut_data.get('cut_number')}")
                    # v1.2.26: cancel_ctx 도 함께 검사 → OperationCancelled 로
                    # 깨워서 batch _gen_batch 가 즉시 빠져나가도록.
                    from app.services.cancel_ctx import raise_if_cancelled as _raise
                    _raise(f"image-step-cut:{cut_data.get('cut_number')}")
                    num = cut_data["cut_number"]
                    output = str(canonical_cut_image_path(project_dir, num))

                    # ★ 레퍼런스 이미지: 스타일 레퍼런스 + 캐릭터 슬롯이면 캐릭터 이미지
                    all_refs = list(ref_images)
                    is_char_cut = cut_has_character(num) and has_character_anchor
                    if char_images and is_char_cut:
                        all_refs.extend(char_images)

                    try:
                        try:
                            service.progress_context = {
                                "project_id": project_id,
                                "cut_number": num,
                                "total_cuts": len(all_cuts),
                            }
                        except Exception:
                            pass
                        service.negative_prompt = append_prompt_specific_negative_prompt(
                            base_negative_prompt,
                            prompt,
                        )
                        await service.generate(
                            prompt, width, height, output,
                            reference_images=all_refs if all_refs else None,
                        )
                        write_prompt_sidecar(
                            output,
                            cut_number=num,
                            image_model=image_model_id,
                            source_prompt=(cut_row.image_prompt if cut_row and cut_row.image_prompt else cut_data.get("image_prompt", "")),
                            final_prompt=prompt,
                            narration=(cut_row.narration if cut_row and cut_row.narration else cut_data.get("narration", "")),
                            comfyui_positive_prompt=getattr(service, "last_positive_prompt", ""),
                            comfyui_negative_prompt=getattr(service, "last_negative_prompt", ""),
                        )
                        service.negative_prompt = base_negative_prompt
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
                            cut_row.image_path = f"images/cut_{num}.png"
                            cut_row.image_model = image_model_id
                            cut_row.status = "image_done"
                        track_progress(project_id, 4)
                    except _OperationCancelled:
                        service.negative_prompt = base_negative_prompt
                        raise
                    except Exception as e:
                        service.negative_prompt = base_negative_prompt
                        msg = f"컷 {num}/{len(all_cuts)} 이미지 생성 실패: {type(e).__name__}: {e}"
                        print(f"[Image] {msg}")
                        try:
                            from app.services.oneclick_service import append_task_log
                            append_task_log(project_id, msg, "error")
                        except Exception:
                            pass
                        return e

            tasks = [_one(cd, cr, prompt) for cd, cr, prompt in items]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, (PipelineCancelled, _OperationCancelled)):
                    raise result
            failures = [r for r in results if isinstance(r, Exception)]
            if failures:
                preview = "; ".join(
                    f"{type(e).__name__}: {str(e)[:240]}" for e in failures[:3]
                )
                raise RuntimeError(f"이미지 생성 배치 실패: {preview}")

        run_async(_gen_batch(batch))

    if image_reuse_pairs:
        import shutil
        for target_num, anchor_num in image_reuse_pairs:
            check_pause_or_cancel(project_id, 4)
            anchor = find_existing_cut_image(project_dir, anchor_num)
            if not anchor:
                raise RuntimeError(
                    f"이미지 재사용 실패: 기준 컷 {anchor_num} 이미지가 없습니다 "
                    f"(대상 컷 {target_num})."
                )
            target = canonical_cut_image_path(project_dir, target_num)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(anchor, target)
            anchor_sidecar = anchor.with_name(anchor.name + ".prompt.json")
            target_sidecar = target.with_name(target.name + ".prompt.json")
            if anchor_sidecar.exists():
                shutil.copy2(anchor_sidecar, target_sidecar)
            cut = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == target_num).first()
            if cut:
                cut.image_path = f"images/cut_{target_num}.png"
                cut.image_model = f"{image_model_id} (reuse cut_{anchor_num})"
                cut.status = "image_done"
            track_progress(project_id, 4)
        print(
            f"[Image] 이미지 재사용: {reuse_group_cuts}컷마다 1장, "
            f"{len(image_reuse_pairs)}컷 복사 완료"
        )

    db.commit()
    db.close()

    # v1.1.55 hotfix: 이미지가 하나도 생성되지 않았으면 실패 처리.
    # 이전엔 개별 실패를 무시하고 step 을 "완료"로 마킹해서, 다음 step(영상)이
    # 이미지 없이 실행되어 머지 실패로 이어지는 사고가 났다.
    expected_nums = [
        int(cut_data["cut_number"])
        for cut_data in all_cuts
        if cut_data.get("cut_number") is not None
    ]
    generated_nums = set(custom_done_nums)
    for cut_data in all_cuts:
        num = int(cut_data["cut_number"])
        if find_existing_cut_image(project_dir, num):
            generated_nums.add(num)

    missing_nums = [n for n in expected_nums if n not in generated_nums]
    if missing_nums:
        preview = ", ".join(str(n) for n in missing_nums[:20])
        if len(missing_nums) > 20:
            preview += f", ... (+{len(missing_nums) - 20})"
        raise RuntimeError(
            f"이미지 생성이 일부 누락되었습니다: "
            f"{len(generated_nums)}/{len(expected_nums)}컷 완료, "
            f"누락 컷: {preview}. 이미지 모델({image_model_id}) 연결 상태를 확인하세요."
        )
    print(f"[Image] 완료: {len(generated_nums)}/{len(expected_nums)} 이미지 생성됨")

    # v1.1.59: ComfyUI 로컬 모델 사용 시, 배치 종료 후 VRAM 해제.
    # 외부 API(Nano/OpenAI/Fal)만 썼다면 호출해도 no-op 에 가까움 (서버가 놀고 있으므로).
    try:
        from app.services.image.factory import IMAGE_REGISTRY
        img_provider = IMAGE_REGISTRY.get(image_model_id, {}).get("provider")
        if img_provider == "comfyui":
            from app.services import comfyui_client
            run_async(comfyui_client.free_memory())
    except Exception as _e:
        print(f"[Image] VRAM 해제 스킵: {_e}")

    # v1.2.24: cancel 키를 해제 — 다음 step 에서 같은 스레드가 재사용될 때
    # 이전 project 의 플래그를 오인하지 않도록.
    try:
        from app.services import comfyui_client as _cfy
        _cfy.set_cancel_key(None)
    except Exception:
        pass
    # v1.2.26: thread-local cancel_ctx 키도 같이 해제.
    try:
        from app.services.cancel_ctx import set_cancel_key as _set_cancel_key
        _set_cancel_key(None)
    except Exception:
        pass


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
        from app.services.subtitle_service import burn_cut_subtitle_file
        return await burn_cut_subtitle_file(
            cut_video_path=cut_video_path,
            narration=narration,
            aspect_ratio=aspect_ratio,
            style_config=style_config or {},
            duration=float(CUT_VIDEO_DURATION),
        )
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
    from app.services.video.factory import (
        DEFAULT_VIDEO_MODEL,
        VIDEO_REGISTRY,
        get_video_service,
        resolve_video_model,
    )
    from app.services.video.prompt_builder import (
        should_generate_ai_video,
        build_video_motion_prompt,
        should_force_safe_motion,
    )
    from app.services.image.asset_guard import find_existing_cut_image

    # v1.1.56: 로컬 ComfyUI 는 GPU 1개 큐라 동시 N 개 보내도 순차 처리 → 동시 1 로 강제.
    # 체감상 1번 컷이 먼저 완료돼 progress 가 빨리 돌고 총 시간은 동일.
    _video_model = resolve_video_model(config.get("video_model", DEFAULT_VIDEO_MODEL))
    _is_comfy_video = VIDEO_REGISTRY.get(_video_model, {}).get("provider") == "comfyui"
    CONCURRENT = 1 if _is_comfy_video else 4

    project_dir = _ensure_project_layout(project_id)
    script = load_script(project_id)

    # ★ 스튜디오와 동일: config 에서 video_model, selection, aspect_ratio 읽기
    video_model = resolve_video_model(config.get("video_model", DEFAULT_VIDEO_MODEL))
    prompt_config = dict(config or {})
    prompt_config["resolved_video_model"] = video_model
    selection = config.get("video_target_selection", "all")
    ai_first_n = int(config.get("ai_video_first_n", 5) or 0)
    aspect_ratio = config.get("aspect_ratio", "16:9")

    primary_service = get_video_service(video_model)
    fallback_service = (
        primary_service
        if video_model == "ffmpeg-static"
        else get_video_service("ffmpeg-static")
    )
    safe_motion_service = (
        primary_service
        if video_model == "ffmpeg-safe-motion"
        else get_video_service("ffmpeg-safe-motion")
    )

    # v1.1.55: 컷 자막 스타일 — DEFAULT_CONFIG 의 subtitle_style 와 동일 키.
    subtitle_style_cfg = config.get("subtitle_style") or {}
    cut_level_subtitles = True

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

    # v1.2.24: ComfyUI 영상(LTX/WAN/HunyuanVideo 등)도 돈줄 차단 — 워커 스레드의
    # cancel 키를 세팅해서 comfyui_client.submit/wait_for 가 redis 플래그 확인.
    try:
        from app.services import comfyui_client as _cfy
        _cfy.set_cancel_key(project_id)
    except Exception as _e:
        print(f"[Video] cancel key 세팅 실패: {_e}")

    # v1.2.26: 외부 API(영상) 서비스 — fal.ai(seedance, ltx2-fast/pro, kling-via-fal),
    # Kling native — 도 raise_if_cancelled() 로 즉시 이탈 가능하도록 thread-local
    # cancel 키 세팅. 영상은 컷당 비용이 가장 크므로 cancel 즉시 차단이 핵심.
    from app.services.cancel_ctx import set_cancel_key as _set_cancel_key
    _set_cancel_key(project_id)

    # v1.1.52: 이미 생성된 영상은 건너뛰고 경로만 수집 (이어하기 지원)
    to_generate = []
    for cut_data in all_cuts:
        num = cut_data["cut_number"]
        cut = db.query(Cut).filter(
            Cut.project_id == project_id,
            Cut.cut_number == num,
        ).first()
        existing = project_dir / "videos" / f"cut_{num:03d}.mp4"
        img_path = find_existing_cut_image(project_dir, num)
        existing_is_current = (
            existing.exists()
            and existing.stat().st_size > 50
            and (not img_path or existing.stat().st_mtime >= img_path.stat().st_mtime)
        )
        if existing_is_current:
            print(f"[Video] Cut {num} 이미 존재 — 건너뜀")
            if cut_level_subtitles:
                try:
                    narration = (cut_data.get("narration") or "").strip()
                    if narration:
                        ok = run_async(_burn_cut_subtitle(
                            str(existing), narration, float(CUT_VIDEO_DURATION),
                            subtitle_style_cfg, aspect_ratio,
                        ))
                        if ok:
                            print(f"[Video] Cut {num} existing subtitle burn verified")
                except Exception as _se:
                    print(f"[Video] Cut {num} existing subtitle burn skipped: {_se}")
            video_paths.append(str(existing))
            if cut:
                cut.video_path = f"videos/cut_{num:03d}.mp4"
                cut.video_model = cut.video_model or video_model
                cut.status = "video_done"
            track_progress(project_id, 5)
            continue
        if existing.exists() and existing.stat().st_size > 50:
            print(f"[Video] Cut {num} 이미지가 더 최신 — 재생성")
        to_generate.append(cut_data)

    # 배치 단위 병렬 처리
    for batch_start in range(0, len(to_generate), CONCURRENT):
        check_pause_or_cancel(project_id, 5)
        batch = to_generate[batch_start:batch_start + CONCURRENT]

        async def _gen_batch(items):
            sem = asyncio.Semaphore(CONCURRENT)

            async def _one(cut_data):
                async with sem:
                    # v1.2.20 [돈줄 차단]: 컷 단위 cancel 체크.
                    # 배치 시작 시점에서 한 번 검사하지만, 4컷이 모두 in-flight 인
                    # 동안 사용자가 중지하면 영상 모델은 컷당 비용이 큼 — 매 컷
                    # 호출 직전에도 cancel 을 검사하여 새 API 요청을 막는다.
                    if _redis_get(f"pipeline:cancel:{project_id}"):
                        return
                    # v1.2.26: cancel_ctx 도 같이 검사 → 외부 영상 API 의
                    # poll 루프가 OperationCancelled 로 즉시 이탈하도록.
                    from app.services.cancel_ctx import raise_if_cancelled as _raise
                    _raise(f"video-step-cut:{cut_data.get('cut_number')}")
                    num = cut_data["cut_number"]
                    img_path = find_existing_cut_image(project_dir, num)
                    if not img_path:
                        raise RuntimeError(f"컷 {num} 이미지 파일 없음")
                    img = str(img_path)
                    aud = str(project_dir / "audio" / f"cut_{num:03d}.mp3")
                    out = str(project_dir / "videos" / f"cut_{num:03d}.mp4")

                    # ★ 스튜디오와 동일: AI/static 분기 + 모션 프롬프트
                    use_ai = should_generate_ai_video(num, selection, ai_first_n)
                    motion_prompt = build_video_motion_prompt(
                        num, total_cuts, prompt_config, cut_data=cut_data,
                    )
                    force_safe_motion = use_ai and should_force_safe_motion(cut_data, config, video_model)
                    if force_safe_motion:
                        svc = safe_motion_service
                        used_model = "ffmpeg-safe-motion"
                        print(f"[Video] Cut {num} source-lock guard -> ffmpeg-safe-motion")
                    else:
                        svc = primary_service if use_ai else fallback_service
                        used_model = video_model if use_ai else "ffmpeg-static"

                    # v1.2.20: AI 영상 실패 시 ffmpeg-static 폴백 제거. 사용자 요구 —
                    # "API 이용할 때 설정된 모델의 API 연결 안되있을때 알림창
                    # 띄우고 풀백으로 처리하지마." AI 컷이 실패하면 그대로
                    # 예외를 올려 task 가 실패하도록 한다. (use_ai=False 인
                    # 컷은 처음부터 ffmpeg-static 으로 가는 게 사용자 설정이라
                    # 폴백이 아님 — 그건 그대로 유지)
                    await svc.generate(
                        image_path=img,
                        audio_path=aud,
                        duration=float(CUT_VIDEO_DURATION),
                        output_path=out,
                        aspect_ratio=aspect_ratio,
                        prompt=motion_prompt,
                    )

                    # v1.1.55: 컷 mp4 가 생긴 직후 자기 대사 자막 번인.
                    # 머지/normalize 후에 자막 입히면 컷 길이 변경으로 싱크가
                    # 깨지는 사고 → 컷 단계에서 0~audio_duration 에 정확히
                    # 박아 둔다. 실패해도 영상 자체는 그대로.
                    if cut_level_subtitles:
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
            if used_model and not str(used_model).startswith("ffmpeg-"):
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

    expected_nums = [
        int(cut_data["cut_number"])
        for cut_data in all_cuts
        if cut_data.get("cut_number") is not None
    ]
    generated_nums: set[int] = set()
    video_dir = project_dir / "videos"
    if video_dir.exists():
        for f in video_dir.glob("cut_*.mp4"):
            if not f.is_file() or f.stat().st_size <= 50:
                continue
            try:
                generated_nums.add(int(f.stem.split("_", 1)[1]))
            except (IndexError, ValueError):
                continue

    missing_nums = [n for n in expected_nums if n not in generated_nums]
    if missing_nums:
        preview = ", ".join(str(n) for n in missing_nums[:20])
        if len(missing_nums) > 20:
            preview += f", ... (+{len(missing_nums) - 20})"
        raise RuntimeError(
            f"영상 생성이 일부 누락되었습니다: "
            f"{len(generated_nums)}/{len(expected_nums)}컷 완료, "
            f"누락 컷: {preview}. 영상 모델({video_model}) 연결 상태를 확인하세요."
        )

    # 컷별 video_path/status 는 병합 전에 먼저 보존한다. 이후 merge/render 단계가
    # 실패해도 생성 완료된 컷을 다시 만들지 않게 하기 위한 안전장치.
    db.commit()

    # 컷-only 병합본은 videos/merged.mp4 에 둔다.
    # output/merged.mp4 는 렌더 단계에서 오프닝/인터미션/엔딩까지 포함한 무BGM 기준본으로 만든다.
    merged = str(project_dir / "videos" / "merged.mp4")
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
        from app.services.video.factory import DEFAULT_VIDEO_MODEL, VIDEO_REGISTRY, resolve_video_model
        vid_model = resolve_video_model(config.get("video_model", DEFAULT_VIDEO_MODEL))
        vid_provider = VIDEO_REGISTRY.get(vid_model, {}).get("provider")
        if vid_provider == "comfyui":
            from app.services import comfyui_client
            run_async(comfyui_client.free_memory())
    except Exception as _e:
        print(f"[Video] VRAM 해제 스킵: {_e}")

    # v1.2.24: cancel 키 해제.
    try:
        from app.services import comfyui_client as _cfy
        _cfy.set_cancel_key(None)
    except Exception:
        pass
    # v1.2.26: thread-local cancel_ctx 키도 같이 해제.
    try:
        from app.services.cancel_ctx import set_cancel_key as _set_cancel_key
        _set_cancel_key(None)
    except Exception:
        pass

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

    # 업로드 OAuth 우선순위:
    # 1) 프리셋 프로젝트 토큰
    # 2) 현재 프로젝트 토큰
    # 3) 전역 토큰 (legacy)
    uploader = None
    template_project_id = config.get("template_project_id")
    if template_project_id:
        _tu = YouTubeUploader(project_id=str(template_project_id))
        if _tu.is_authenticated():
            uploader = _tu
            print(f"[upload] using preset-bound YouTube token ({template_project_id})")
    if uploader is None:
        _pu = YouTubeUploader(project_id=project_id)
        if _pu.is_authenticated():
            uploader = _pu
            print(f"[upload] using project-bound YouTube token ({project_id})")
    if uploader is None:
        uploader = YouTubeUploader()

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

    upload_title = with_episode_prefix(script.get("title", "Untitled"), config.get("episode_number"))
    narration_seed = " ".join((c.get("narration") or "") for c in script.get("cuts", [])[:30] if isinstance(c, dict))
    upload_description = format_description(
        script.get("description", ""),
        title=upload_title,
        topic=script.get("title", ""),
        narration=narration_seed,
        language=config.get("language") or "ko",
    )
    upload_tags = expand_tags(
        script.get("tags", []),
        title=upload_title,
        topic=script.get("title", ""),
        narration=narration_seed,
        language=config.get("language") or "ko",
    )
    try:
        from app.services.thumbnail_service import ensure_standard_thumbnail
        thumb_result = run_async(ensure_standard_thumbnail(
            project_id=project_id,
            config=config,
            script=script,
            title=script.get("title") or upload_title,
            topic=script.get("topic") or script.get("title"),
            episode_number=config.get("episode_number"),
        ))
        print(f"[upload] thumbnail ready: {thumb_result}")
    except Exception as e:
        print(f"[upload] thumbnail generation skipped: {e}")
    thumbnail_upload_path = project_dir / "output" / "thumbnail.png"
    if not thumbnail_upload_path.exists():
        thumbnail_upload_path = project_dir / "images" / "cut_001.png"

    existing_upload = uploader.find_existing_upload_by_title(upload_title)
    if existing_upload:
        existing_video_id = existing_upload.get("video_id")
        result = {
            "video_id": existing_video_id,
            "url": existing_upload.get("url") or (
                f"https://www.youtube.com/watch?v={existing_video_id}" if existing_video_id else None
            ),
            "already_uploaded": True,
        }
        print(f"[upload] main upload skipped, already exists: {result.get('url')}")
    else:
        result = run_async(uploader.upload(
        video_path=str(_video_path),
        title=upload_title,
        description=upload_description,
        tags=upload_tags,
        thumbnail_path=None,
            # v1.1.57: AI 생성 썸네일 우선, 없으면 첫 번째 컷 이미지 폴백
        privacy="private",
        ))
        verified = uploader.confirm_upload_processed_in_studio(
            video_id=result.get("video_id"),
            title=upload_title,
        )
        result = {**result, "studio_verified": True, "processing_verified": True, "studio_record": verified}
        if _Path(thumbnail_upload_path).exists() and result.get("video_id"):
            try:
                thumb_set = uploader.set_thumbnail(str(result.get("video_id")), str(thumbnail_upload_path))
                result["thumbnail_uploaded"] = True
                result["thumbnail_result"] = thumb_set
            except Exception as exc:
                result["thumbnail_error"] = str(exc)
                print(f"[upload] thumbnail upload failed: {exc}")
        print(f"[upload] Studio verified: {verified.get('url') or result.get('url')}")
    caption_path = project_dir / "subtitles" / "subtitles.srt"
    caption_upload = None
    caption_error = None
    if (
        result.get("video_id")
        and not result.get("already_uploaded")
        and caption_path.exists()
        and should_upload_youtube_captions(config)
    ):
        try:
            caption_upload = run_async(upload_multilingual_captions(
                uploader,
                str(result.get("video_id")),
                str(caption_path),
                config,
            ))
            print(f"[upload] caption uploaded: {caption_upload}")
        except Exception as exc:
            caption_error = str(exc)
            print(f"[upload] caption upload failed: {exc}")

    shorts_results = []
    if bool(config.get("shorts_upload_enabled", True)):
        shorts_dir = _output_dir / "shorts"
        shorts_files = [shorts_dir / "short_1.mp4"]
        for idx, shorts_path in enumerate(shorts_files, start=1):
            if not shorts_path.exists() or shorts_path.stat().st_size <= 0:
                continue
            shorts_base_title = without_episode_prefix(script.get("title", "Untitled")) or "Untitled"
            shorts_title = f"{shorts_base_title[:92]} #Shorts"
            shorts_description = format_description(
                upload_description,
                title=shorts_title,
                topic=script.get("title", ""),
                narration=narration_seed,
                language=config.get("language") or "ko",
                shorts=True,
            )
            shorts_tags = expand_tags(
                upload_tags,
                title=shorts_title,
                topic=script.get("title", ""),
                narration=narration_seed,
                language=config.get("language") or "ko",
                shorts=True,
            )
            try:
                existing_short = uploader.find_existing_upload_by_title(shorts_title[:100])
                if existing_short:
                    existing_short_id = existing_short.get("video_id")
                    shorts_upload = {
                        "video_id": existing_short_id,
                        "url": existing_short.get("url") or (
                            f"https://www.youtube.com/watch?v={existing_short_id}" if existing_short_id else None
                        ),
                        "already_uploaded": True,
                    }
                    print(f"[upload] shorts {idx} skipped, already exists: {shorts_upload.get('url')}")
                else:
                    shorts_upload = run_async(uploader.upload(
                        video_path=str(shorts_path),
                        title=shorts_title[:100],
                        description=shorts_description,
                        tags=shorts_tags,
                        thumbnail_path=None,
                        privacy=str(config.get("youtube_privacy", "private") or "private"),
                    ))
                    shorts_verified = uploader.confirm_upload_processed_in_studio(
                        video_id=shorts_upload.get("video_id"),
                        title=shorts_title[:100],
                    )
                    shorts_upload = {
                        **shorts_upload,
                        "studio_verified": True,
                        "processing_verified": True,
                        "studio_record": shorts_verified,
                    }
                    print(
                        "[upload] shorts Studio verified: "
                        f"{shorts_verified.get('url') or shorts_upload.get('url')}"
                    )
                shorts_results.append({
                    "index": idx,
                    "path": str(shorts_path),
                    "url": shorts_upload.get("url"),
                    "video_id": shorts_upload.get("video_id"),
                    "already_uploaded": bool(shorts_upload.get("already_uploaded")),
                })
                print(f"[upload] shorts {idx} uploaded: {shorts_upload.get('url')}")
            except Exception as exc:
                print(f"[upload] shorts {idx} upload failed: {exc}")

    new_config = dict(config or {})
    if result.get("thumbnail_error"):
        new_config["youtube_thumbnail_error"] = str(result.get("thumbnail_error"))
    if caption_upload:
        new_config["youtube_captions"] = caption_upload
        new_config["youtube_caption"] = caption_upload
        new_config.pop("youtube_caption_error", None)
        new_config.pop("youtube_caption_errors", None)
    if caption_error:
        new_config["youtube_caption_error"] = caption_error
        new_config["youtube_caption_errors"] = {"all": caption_error}
    if shorts_results:
        new_config["shorts_uploads"] = shorts_results
    update_project(project_id, youtube_url=result["url"], config=new_config)
    try:
        from app.services.project_archive import archive_uploaded_project

        archive_result = archive_uploaded_project(project_id, new_config)
        print(f"[upload] uploaded project archive: {archive_result}")
    except Exception as e:
        print(f"[upload] uploaded project archive skipped: {e}")
