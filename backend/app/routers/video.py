"""Video generation router"""
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
import datetime as _dt
from app.config import BASE_DIR as _BASE_DIR_FOR_LOG

# v1.1.60: 로그는 코드 디렉토리(BASE_DIR/backend/logs) 에 기록 — NAS 가 아닌 로컬 코드 폴더.
_VIDEO_LOG_PATH = Path(_BASE_DIR_FOR_LOG) / "backend" / "logs" / "video_async.log"
_MODULE_LOAD_TIME = _dt.datetime.now().isoformat(timespec="seconds")


def _vlog(msg: str) -> None:
    """video-async 디버그 로그 파일에 타임스탬프 찍어 한 줄 기록 (best-effort)."""
    try:
        _VIDEO_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        with open(_VIDEO_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import DATA_DIR, CUT_VIDEO_DURATION
from app.services.video.factory import DEFAULT_VIDEO_MODEL, get_video_service, resolve_video_model
from app.services.video.ffmpeg_service import FFmpegService

router = APIRouter()


def _to_relative(project_id: str, abs_path: str) -> str:
    """Convert absolute path to relative path from project dir for DB storage."""
    project_dir = str(DATA_DIR / project_id)
    p = str(abs_path).replace("\\", "/")
    pd = project_dir.replace("\\", "/")
    if p.startswith(pd):
        rel = p[len(pd):]
        return rel.lstrip("/")
    return abs_path


def _to_absolute(project_id: str, rel_path: str) -> str:
    """Convert relative path to absolute path for file access."""
    p = Path(rel_path)
    if p.is_absolute():
        return rel_path
    return str(DATA_DIR / project_id / rel_path)


def _load_script_cut_map(project_id: str) -> dict[int, dict]:
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {}
    try:
        with open(script_path, "r", encoding="utf-8") as fh:
            script = json.load(fh)
    except Exception as exc:
        _vlog(f"script cut map load failed project={project_id}: {exc}")
        return {}

    cut_map: dict[int, dict] = {}
    for cut_data in script.get("cuts", []):
        try:
            cut_map[int(cut_data.get("cut_number"))] = cut_data
        except (TypeError, ValueError):
            continue
    return cut_map


# --------------------------------------------------------------------------- #
# v1.1.36 — 영상 제작 대상 선택
# --------------------------------------------------------------------------- #
#
# 사용자가 "3컷당 1장 / 4컷당 1장 / 5컷당 1장 / 캐릭터만" 중 고를 수 있게 한다.
# 선택되지 않은 컷은 비용 0 인 폴백 서비스로 처리해 renderer 단계에서
# concat 할 수 있는 cut_N.mp4 파일을 여전히 만들어둔다. 렌더는 모든 컷의 mp4 가
# 존재해야 합성 가능한 구조이므로 **skip 은 쓸 수 없다** — 싸게 때우는 전략.
#
# v1.1.40: 폴백을 ffmpeg-kenburns(줌인 효과) → ffmpeg-static(효과 없음) 으로
# 변경. 사용자 요청 — "나머지에 켄번 효과 넣지 말라고".
#
# 선택 규칙 (모두 1-based cut_number):
#   - "all"            : 전부 AI 비디오 (기본, 현재 동작)
#   - "every_3"        : cut 1, 4, 7, 10 ...     ((n-1) % 3 == 0)
#   - "every_4"        : cut 1, 5, 9, 13 ...     ((n-1) % 4 == 0)
#   - "every_5"        : cut 1, 6, 11, 16 ...    ((n-1) % 5 == 0)
#   - "character_only" : 기존 캐릭터 슬롯 기반 절약 모드 (현재는 every_5 와 동일)

VIDEO_TARGET_OPTIONS = {"all", "every_3", "every_4", "every_5", "character_only", "none"}


def should_generate_ai_video(cut_number: int, selection: str, ai_first_n: int = 5) -> bool:
    """주어진 cut 이 primary video_model 로 처리돼야 하는지 판단.

    v1.1.55: `ai_first_n` 이 양수이면 컷 1..N 은 selection 과 무관하게 항상 AI
    모델로 생성한다. 영상 초반부가 시청자 이탈률을 좌우하므로 품질 보장. 설정
    키는 `ai_video_first_n` (DEFAULT_CONFIG 기본 5).
    """
    if cut_number is None or cut_number < 1:
        return False
    # v2.1.1: "none" → AI 영상 생성 완전 비활성화
    if selection == "none":
        return False
    # v1.1.55: 앞 N 컷은 무조건 AI — selection 보다 우선
    try:
        n = int(ai_first_n)
    except (TypeError, ValueError):
        n = 0
    if n > 0 and cut_number <= n:
        return True
    if selection not in VIDEO_TARGET_OPTIONS:
        return True  # 알 수 없는 값이면 안전하게 "전부 생성" 으로 취급
    if selection == "all":
        return True
    if selection == "every_3":
        return (cut_number - 1) % 3 == 0
    if selection == "every_4":
        return (cut_number - 1) % 4 == 0
    if selection == "every_5":
        return (cut_number - 1) % 5 == 0
    if selection == "character_only":
        # legacy 절약 모드 유지 — 현재는 every_5 와 동일
        return (cut_number - 1) % 5 == 0
    return True


def count_ai_video_cuts(total_cuts: int, selection: str, ai_first_n: int = 5) -> int:
    """selection 기준 AI 비디오가 실제로 생성될 컷 수. estimation_service 에서 재사용."""
    if total_cuts <= 0:
        return 0
    if selection == "none":
        return 0
    if selection == "all" or selection not in VIDEO_TARGET_OPTIONS:
        return total_cuts
    return sum(
        1 for n in range(1, total_cuts + 1)
        if should_generate_ai_video(n, selection, ai_first_n)
    )


def _build_video_motion_prompt(
    cut_number: int,
    total_cuts: int,
    config: dict,
    cut_data: dict | None = None,
    video_model: str | None = None,
) -> str:
    """컷별 영상 모션 프롬프트 생성.

    - 캐릭터 컷(3의 배수 규칙)에서는 캐릭터가 자연스럽게 움직이도록 지시.
    - 1번 컷은 오프닝 느낌, 마지막 컷은 엔딩 느낌의 카메라워크.
    - 그 외에는 부드러운 시네마틱 카메라 모션.

    FFmpeg KenBurns 서비스는 이 프롬프트를 사용하지 않지만, fal/kling 등
    AI 영상 모델은 prompt 를 실제 모션 지시로 해석한다.
    """
    from app.services.video.prompt_builder import build_video_motion_prompt
    prompt_config = dict(config or {})
    if video_model:
        prompt_config["resolved_video_model"] = video_model
    return build_video_motion_prompt(cut_number, total_cuts, prompt_config, cut_data=cut_data)


def _should_force_safe_motion(cut_data: dict | None, config: dict, video_model: str) -> bool:
    from app.services.video.prompt_builder import should_force_safe_motion
    return should_force_safe_motion(cut_data, config, video_model)

    character_description = (config.get("character_description") or "").strip()
    has_character_anchor = bool(character_description or (config.get("character_images") or []))

    is_first = cut_number == 1
    is_last = total_cuts > 0 and cut_number == total_cuts
    is_character_cut = has_character_anchor

    parts: list[str] = []

    if is_first:
        parts.append(
            "The camera slowly pushes in from wide to medium shot. "
            "Soft ambient motion in the scene: dust particles drift through the air, "
            "light flickers gently, background elements sway. "
            "Opening shot energy, building anticipation."
        )
    elif is_last:
        parts.append(
            "The camera slowly pulls out and drifts upward. "
            "Ambient motion continues: gentle wind, soft light shift, "
            "subtle atmospheric movement. Satisfying closing beat."
        )
    else:
        parts.append(
            "The camera slowly pans and drifts with subtle parallax. "
            "Things in the scene move naturally: wind moves fabric and hair, "
            "light shimmers, particles float, water or smoke flows. "
            "Continuous cinematic motion throughout the shot."
        )

    if is_character_cut and character_description:
        parts.append(
            f"The main character ({character_description}) is present and MUST move "
            f"naturally — subtle head turn, eye blink, hair/clothes drift, small hand "
            f"or shoulder gesture, breathing motion. Keep the face and outfit "
            f"perfectly consistent with the reference image. No teleporting, no "
            f"identity drift, no extra limbs."
        )
    elif is_character_cut:
        parts.append(
            "The main focal character moves naturally — subtle gestures, breathing, "
            "tiny idle motion. Preserve identity exactly."
        )
    else:
        parts.append("No hard cuts inside the clip; keep motion gentle and continuous.")

    return " ".join(parts)


# --------------------------------------------------------------------------- #
# v1.1.44 — 자동 폴백 + 병렬 실행 + 사전 잔액 체크
# --------------------------------------------------------------------------- #
#
# 문제 (v1.1.43 까지):
#   1) fal.ai 잔액이 소진되면 submit 이 HTTP 403 으로 터지면서 그 컷 전체가
#      "failed" 로 마킹되고, 사용자는 빨간 에러 화면을 마주한다. 120컷 중
#      87컷 후에 잔액이 바닥나 33컷이 한 번에 실패하는 사고가 발생했다.
#   2) 컷 처리가 직렬(for 루프)이라 120컷 × 30~60초 = 60~120분이 걸렸다.
#
# 해결:
#   A) 런 시작 전에 `_probe_fal_video_model` 로 키/잔액 상태를 확인한다.
#      401/403/잔액 소진이면 전체 런을 ffmpeg-kenburns 로 전환 (force_full_fallback).
#   B) 런 중에 primary 가 실패한 개별 컷은 즉시 ffmpeg-kenburns 로 재시도.
#      사용자가 "failed" 컷을 보는 대신 "ai_fallback" 컷을 받는다.
#   C) primary 가 연속 실패로 "잔액 소진/인증 실패" 로 판명되면 공유 플래그
#      `_primary_disabled` 를 세워 남은 컷은 바로 kenburns 로 간다 (재시도 낭비 방지).
#   D) `asyncio.Semaphore(VIDEO_PARALLELISM)` 로 4컷 동시 처리. 네트워크 bound
#      작업이므로 병렬화 이득이 크다. 프로그레스는 공유 카운터로 증가.

VIDEO_PARALLELISM = 4


def _parallelism_for(video_model: str) -> int:
    """v1.1.56: ComfyUI 로컬 모델은 GPU 1개 큐라 동시성 무의미 → 1.
    fal.ai/kling 같은 클라우드 API 는 네트워크 bound 라 4 병렬이 유리."""
    from app.services.video.factory import VIDEO_REGISTRY, resolve_video_model
    video_model = resolve_video_model(video_model)
    if VIDEO_REGISTRY.get(video_model, {}).get("provider") == "comfyui":
        return 1
    return VIDEO_PARALLELISM

# fal.ai 로 라우팅되는 내부 모델 id — 사전 잔액 체크 대상.
# fal_service.FAL_MODEL_MAP 과 sync 되어야 한다.
_FAL_VIDEO_MODEL_IDS = {
    "seedance-lite",
    "seedance-1.0",
    "seedance-1.5-pro",
    "ltx2-fast",
    "ltx2-pro",
    "kling-2.5-turbo",
    "kling-2.6-pro",
}


def _is_fal_video_model(video_model: str) -> bool:
    return video_model in _FAL_VIDEO_MODEL_IDS


def _is_terminal_primary_error(err_str: str) -> bool:
    """primary 서비스가 남은 런 동안 회복 불가능한 상태인지 판단.

    아래 문자열이 포함되면 남은 컷들에 대해 primary 재시도를 건너뛴다:
    - HTTP 401 / 403           → 키 거부 혹은 잔액 소진
    - "Exhausted balance"      → fal.ai 가 직접 알려준 잔액 소진
    - "User is locked"         → fal.ai 계정 잠금
    """
    if not err_str:
        return False
    markers = ("HTTP 401", "HTTP 403", "Exhausted balance", "User is locked")
    return any(m in err_str for m in markers)


async def _preflight_fal_probe(video_model: str) -> tuple[bool, str]:
    """런 시작 전 fal.ai 키/잔액 상태 확인.

    Returns `(should_disable_primary, reason)`:
    - True  → 전체 런을 ffmpeg 로 전환해야 한다 (auth_failed/timeout/error)
    - False → primary 사용해도 안전

    non-fal 모델이면 즉시 `(False, "not_fal")` 반환.
    """
    if not _is_fal_video_model(video_model):
        return False, "not_fal"

    # fal_service.FAL_MODEL_MAP 의 값이 필요 — 순환 import 회피 위해 함수 안에서 import.
    try:
        from app.services.video.fal_service import FAL_MODEL_MAP
        from app.routers.api_status import _probe_fal_video_model
    except ImportError as e:
        print(f"[preflight] probe import failed: {e}")
        return False, "import_failed"

    fal_model_path = FAL_MODEL_MAP.get(video_model)
    if not fal_model_path:
        return False, "unknown_mapping"

    try:
        result = await _probe_fal_video_model(fal_model_path)
    except Exception as e:
        print(f"[preflight] probe threw {type(e).__name__}: {e} — 전체 런을 ffmpeg 로 전환")
        return True, f"probe_exception:{type(e).__name__}"

    status = result.get("status", "")
    if status == "auth_failed":
        detail = result.get("detail", "")
        print(f"[preflight] fal.ai 키/잔액 문제 감지 → 전체 런을 ffmpeg 로 전환. {detail}")
        return True, f"auth_failed:{detail[:200]}"
    if status in ("timeout", "error", "not_configured"):
        print(f"[preflight] fal.ai probe {status} → 안전하게 ffmpeg 로 전환. {result.get('detail','')}")
        return True, f"{status}:{result.get('detail','')[:200]}"

    # key_valid / unknown_ok → primary 사용 OK
    print(f"[preflight] fal.ai probe OK (status={status}, http={result.get('http_code')})")
    return False, f"ok:{status}"


async def _generate_one_cut_safe(
    *,
    primary_service,
    kenburns_service,
    safe_motion_service,
    static_service,
    video_model: str,
    use_ai: bool,
    force_full_fallback: bool,
    primary_disabled: list,  # 길이 1 mutable flag — [bool]
    img_abs: str,
    aud_abs: str,
    duration: float,
    output_path: str,
    aspect_ratio: str,
    motion_prompt: str,
    cut_number: int = 0,
    force_safe_motion: bool = False,
    is_cancelled=None,
) -> tuple[str, str]:
    """단일 컷을 생성한다. Primary 가 실패하면 자동으로 ffmpeg-kenburns 로 폴백.

    Returns `(output_path, source_tag)` 여기서 source_tag ∈
        "ai"                    — primary 가 성공
        "ai_fallback_kenburns"  — primary 실패 후 kenburns 성공
        "ffmpeg_forced"         — 사전 체크 실패로 kenburns 강제
        "ffmpeg_selection"      — selection="every_N"/"character_only" 으로 static 선택

    kenburns 마저 실패하면 예외를 raise — 호출자가 컷을 "failed" 로 기록한다.

    v1.1.55: cut_number <= 5 인 컷은 AI 재시도를 최대 3회까지 시도한다.
    force_full_fallback / primary_disabled 도 무시하고 AI 를 시도한다.
    """
    import asyncio as _aio

    def _cancel_requested() -> bool:
        if is_cancelled is None:
            return False
        try:
            return bool(is_cancelled())
        except Exception:
            return False

    # 앞 5컷 강제 AI 여부
    is_forced_ai = cut_number >= 1 and cut_number <= 5
    # 앞 5컷이면 재시도 3회, 그 외 1회
    max_retries = 3 if is_forced_ai else 1

    if _cancel_requested():
        raise _aio.CancelledError(f"video cut {cut_number} cancelled before generation")

    if force_safe_motion:
        await safe_motion_service.generate(
            image_path=img_abs,
            audio_path=aud_abs,
            duration=duration,
            output_path=output_path,
            aspect_ratio=aspect_ratio,
            prompt=motion_prompt,
        )
        return output_path, "ffmpeg_safe_motion"

    # 1) AI 대상이 아닌 컷 → 원래 동작: ffmpeg-static 으로 채워넣기
    if not use_ai:
        await static_service.generate(
            image_path=img_abs,
            audio_path=aud_abs,
            duration=duration,
            output_path=output_path,
            aspect_ratio=aspect_ratio,
            prompt=motion_prompt,
        )
        return output_path, "ffmpeg_selection"

    # v1.2.20: 폴백 제거. 사용자 요구 — "API 이용할 때 설정된 모델의 API 연결
    # 안되있을때 알림창 띄우고 풀백으로 처리하지마." preflight 실패 / primary
    # 사용 불가 시 kenburns 로 갈아치우지 않고 명시적 RuntimeError 를 올려 컷
    # 단위 실패로 기록한다. (use_ai=False 인 컷이 처음부터 ffmpeg-static 으로
    # 가는 건 사용자 설정이므로 폴백 아님 — 위에서 그대로 처리)
    if (force_full_fallback or primary_disabled[0]) and not is_forced_ai:
        raise RuntimeError(
            f"primary 영상 모델({video_model}) 사용 불가 (preflight 실패 또는 잔액 소진). "
            f"폴백 비활성화 — API 키와 잔액을 확인하거나 영상 모델을 ffmpeg-kenburns/static "
            f"으로 직접 바꾸세요."
        )

    # AI 대상 컷 → primary 시도 (앞 5컷은 최대 3회 재시도)
    last_err = None
    _vlog(f"_gen_safe cut={cut_number} primary={type(primary_service).__name__} max_retries={max_retries}")
    for attempt in range(1, max_retries + 1):
        if _cancel_requested():
            raise _aio.CancelledError(f"video cut {cut_number} cancelled before attempt {attempt}")
        try:
            _vlog(f"_gen_safe cut={cut_number} attempt={attempt} → primary.generate() 호출")
            await primary_service.generate(
                image_path=img_abs,
                audio_path=aud_abs,
                duration=duration,
                output_path=output_path,
                aspect_ratio=aspect_ratio,
                prompt=motion_prompt,
            )
            _vlog(f"_gen_safe cut={cut_number} attempt={attempt} PRIMARY SUCCESS")
            return output_path, "ai"
        except Exception as e:
            last_err = e
            err_str = f"{type(e).__name__}: {e}"
            import traceback as _tb2
            _vlog(f"_gen_safe cut={cut_number} attempt={attempt} PRIMARY FAILED: {err_str}\n{_tb2.format_exc()[-700:]}")
            if _cancel_requested():
                raise _aio.CancelledError(f"video cut {cut_number} cancelled after failed attempt {attempt}")
            if attempt < max_retries:
                wait = attempt * 5
                print(
                    f"[video-async] cut {cut_number} AI 실패 ({attempt}/{max_retries}), "
                    f"{wait}초 후 재시도: {err_str[:200]}"
                )
                await _aio.sleep(wait)
                if _cancel_requested():
                    raise _aio.CancelledError(f"video cut {cut_number} cancelled during retry wait")
                continue
            # 마지막 시도까지 실패 — terminal 이면 같은 런 안의 후속 컷도 즉시 실패시키도록 플래그 set
            if _is_terminal_primary_error(err_str):
                if not primary_disabled[0]:
                    primary_disabled[0] = True
                    print(
                        f"[video-async] primary({video_model}) 사용 불가로 판명. 사유: {err_str[:200]}"
                    )

    # v1.2.20: kenburns 폴백 제거 — 그대로 raise
    raise RuntimeError(
        f"영상 컷 {cut_number} 생성 실패 — 모델 {video_model}. "
        f"폴백 비활성화. 마지막 오류: {last_err}"
    )


@router.get("/diagnose-ping")
async def diagnose_ping():
    """백엔드 프로세스 가동 확인용."""
    return {
        "ok": True,
        "module_load_time": _MODULE_LOAD_TIME,
        "now": _dt.datetime.now().isoformat(timespec="seconds"),
        "log_path": str(_VIDEO_LOG_PATH),
    }


@router.get("/diagnose-log")
async def diagnose_log(tail: int = 200, clear: bool = False):
    """video-async 디버그 로그 파일 마지막 N 줄 읽기.

    /api/video/diagnose-log?tail=100
    /api/video/diagnose-log?clear=true   (로그 비우기)
    """
    try:
        if clear and _VIDEO_LOG_PATH.exists():
            _VIDEO_LOG_PATH.unlink()
            return {"cleared": True, "path": str(_VIDEO_LOG_PATH)}
        if not _VIDEO_LOG_PATH.exists():
            return {"exists": False, "path": str(_VIDEO_LOG_PATH)}
        with open(_VIDEO_LOG_PATH, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        return {
            "exists": True,
            "path": str(_VIDEO_LOG_PATH),
            "total_lines": len(lines),
            "tail": "".join(lines[-tail:]),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


@router.get("/diagnose-comfyui")
async def diagnose_comfyui(model_id: str = "comfyui-hunyuan15-480p"):
    """진단용 — 해당 ComfyUI 영상 모델로 실제 워크플로 dry-run 제출.

    브라우저에서 URL 만 치면 JSON 으로 에러 반환.
    예: /api/video/diagnose-comfyui?model_id=comfyui-hunyuan15-480p
    """
    import traceback
    from app.services.video.factory import get_video_service, VIDEO_REGISTRY, resolve_video_model
    from app.services import comfyui_client as _cc
    from pathlib import Path as _P

    resolved_model_id = resolve_video_model(model_id)
    result = {
        "model_id": model_id,
        "resolved_model_id": resolved_model_id,
        "registry_hit": resolved_model_id in VIDEO_REGISTRY,
        "provider": VIDEO_REGISTRY.get(resolved_model_id, {}).get("provider"),
        "stage": None,
        "ok": False,
        "error": None,
    }

    # 1) 서비스 인스턴스 (워크플로 JSON 로드)
    try:
        result["stage"] = "service_init"
        svc = get_video_service(resolved_model_id)
        result["service_class"] = type(svc).__name__
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        return result

    # 2) 아무 이미지나 하나 픽 → upload
    try:
        result["stage"] = "find_image"
        from app.config import DATA_DIR as _DD
        candidates = list(_P(_DD).glob("*/images/cut_*.png"))
        if not candidates:
            result["error"] = "테스트용 이미지 파일이 없음 (DATA_DIR/*/images/cut_*.png)"
            return result
        test_img = str(candidates[0])
        result["test_image"] = test_img
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    try:
        result["stage"] = "upload_image"
        uploaded = await _cc.upload_image(test_img)
        result["uploaded_name"] = uploaded
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        return result

    # 3) 워크플로 렌더 → /prompt 제출 (dry-run: 실제 실행되지만 결과는 버림)
    try:
        result["stage"] = "render_workflow"
        import random as _r
        w, h = 640, 384
        length = 25
        graph = _cc.render_workflow(
            svc._template,
            {
                "INPUT_IMAGE_NAME": uploaded,
                "PROMPT": "a cinematic shot, diagnostic test",
                "WIDTH": w, "HEIGHT": h, "LENGTH": length,
                "SEED": _r.randint(0, 2**31 - 1),
                "PREFIX": "longtube/__diag__",
            },
        )
        result["graph_node_count"] = len(graph)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        return result

    try:
        result["stage"] = "submit_to_comfyui"
        pid = await _cc.submit(graph)
        result["prompt_id"] = pid
        result["ok"] = True
        result["stage"] = "done"
        result["note"] = "ComfyUI 큐에 들어갔습니다. 이제 서버에서 처리 중일 것임."
        return result
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}"
        return result


@router.get("/{project_id}/diagnose-state")
async def diagnose_state(project_id: str, db: Session = Depends(get_db)):
    """진단용 — 프로젝트의 실제 video 관련 상태를 통째로 덤프.

    브라우저 URL: /api/video/{project_id}/diagnose-state
    """
    from app.services.task_manager import is_running, _tasks, _key
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return {"error": "project not found", "project_id": project_id}

    cfg = project.config or {}
    video_model = cfg.get("video_model")
    step_states = project.step_states or {}

    # task_manager 상태
    vkey = _key(project_id, "video")
    ikey = _key(project_id, "image")
    vstate = _tasks.get(vkey)
    istate = _tasks.get(ikey)

    def _state_info(st):
        if st is None:
            return None
        return {
            "status": getattr(st, "status", None),
            "completed": getattr(st, "completed", None),
            "total": getattr(st, "total", None),
            "error": getattr(st, "error", None),
        }

    # 컷 상태 요약
    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
    cut_summary = [
        {
            "n": c.cut_number,
            "status": c.status,
            "image": bool(c.image_path),
            "audio": bool(c.audio_path),
            "video": bool(c.video_path),
            "video_model_saved": c.video_model,
        }
        for c in cuts
    ]

    return {
        "project_id": project_id,
        "config_video_model": video_model,
        "config_video_target_selection": cfg.get("video_target_selection"),
        "config_ai_video_first_n": cfg.get("ai_video_first_n"),
        "step_states": step_states,
        "task_video": _state_info(vstate),
        "task_image": _state_info(istate),
        "is_video_running": is_running(project_id, "video"),
        "is_image_running": is_running(project_id, "image"),
        "cuts_total": len(cuts),
        "cuts": cut_summary,
    }


@router.post("/{project_id}/generate")
async def generate_all_videos(project_id: str, db: Session = Depends(get_db)):
    """Generate all video clips and merge them"""
    _vlog(f"=== generate_all_videos (SYNC) called project={project_id} ===")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()

    if not cuts:
        raise HTTPException(400, "No cuts found in project")

    video_model = resolve_video_model(project.config.get("video_model", DEFAULT_VIDEO_MODEL))
    aspect_ratio = project.config.get("aspect_ratio", "16:9")
    # v2.1.1: enable_ai_video=False → 모든 컷 Ken Burns 폴백
    enable_ai_video = bool((project.config or {}).get("enable_ai_video", True))
    selection = (project.config or {}).get("video_target_selection", "all") if enable_ai_video else "none"
    ai_first_n = int((project.config or {}).get("ai_video_first_n", 5) or 0) if enable_ai_video else 0
    total_cuts = len(cuts)
    script_cut_map = _load_script_cut_map(project_id)

    primary_service = get_video_service(video_model)
    # v1.1.40: 선택되지 않은 컷은 효과 없는 ffmpeg-static 폴백 (비용 0).
    # primary 가 이미 ffmpeg-static 이면 동일 인스턴스를 재사용.
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
    video_dir = DATA_DIR / project_id / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    results = []
    clip_paths = []

    # Generate individual video clips
    for cut in cuts:
        if not cut.image_path or not cut.audio_path:
            results.append({
                "cut_number": cut.cut_number,
                "status": "skipped",
                "reason": "Missing image or audio"
            })
            continue

        try:
            video_path = str(video_dir / f"cut_{cut.cut_number}.mp4")
            motion_prompt = _build_video_motion_prompt(
                cut.cut_number,
                total_cuts,
                project.config or {},
                script_cut_map.get(int(cut.cut_number)),
                video_model,
            )

            use_ai = should_generate_ai_video(cut.cut_number, selection, ai_first_n)
            force_safe_motion = use_ai and _should_force_safe_motion(
                script_cut_map.get(int(cut.cut_number)),
                project.config or {},
                video_model,
            )
            if force_safe_motion:
                svc = safe_motion_service
                used_model = "ffmpeg-safe-motion"
            else:
                svc = primary_service if use_ai else fallback_service
                used_model = video_model if use_ai else "ffmpeg-static"

            result_path = await svc.generate(
                image_path=_to_absolute(project_id, cut.image_path),
                audio_path=_to_absolute(project_id, cut.audio_path),
                duration=CUT_VIDEO_DURATION,
                output_path=video_path,
                aspect_ratio=aspect_ratio,
                prompt=motion_prompt,
            )

            cut.video_path = _to_relative(project_id, result_path)
            cut.video_model = used_model
            cut.status = "completed"
            # v1.1.55-fix: 단건 영상 생성 비용 기록
            if used_model and not str(used_model).startswith("ffmpeg-"):
                try:
                    from app.services import spend_ledger
                    spend_ledger.record_video(
                        video_model, n_clips=1,
                        project_id=project_id, note=f"studio single cut_{cut.cut_number}",
                    )
                except Exception as _le:
                    print(f"[spend_ledger] studio single video record skipped: {_le}")
            db.commit()

            clip_paths.append(result_path)
            results.append({
                "cut_number": cut.cut_number,
                "status": "completed",
                "path": result_path,
                "model": used_model,
                "ai_video": use_ai,
            })
        except Exception as e:
            cut.status = "failed"
            db.commit()
            results.append({
                "cut_number": cut.cut_number,
                "status": "failed",
                "error": str(e)
            })

    # Merge all clips into final video
    merged_path = None
    if clip_paths:
        try:
            ffmpeg_service = FFmpegService()
            merged_path = str(video_dir / "merged.mp4")
            await ffmpeg_service.merge_videos(clip_paths, merged_path)

            # Mark step completed
            step_states = dict(project.step_states or {})
            step_states["5"] = "completed"
            project.step_states = step_states
            db.commit()

            # 간지영상이 준비돼 있으면 final_with_interludes.mp4 까지 자동 생성
            interlude_info = None
            try:
                from app.routers.interlude import build_interlude_sequence
                interlude_info = await build_interlude_sequence(project, project_id, db)
                if interlude_info and interlude_info.get("status") == "composed":
                    print(
                        f"[video/generate] interlude auto-compose → "
                        f"{interlude_info.get('output_path')}"
                    )
            except Exception as ie:
                import traceback
                print(
                    f"[video/generate] interlude auto-compose failed (non-fatal): "
                    f"{ie}\n{traceback.format_exc()}"
                )

            return {
                "project_id": project_id,
                "video_model": video_model,
                "results": results,
                "total": len(cuts),
                "completed": sum(1 for r in results if r["status"] == "completed"),
                "merged_video": merged_path,
                "interlude": interlude_info,
            }
        except Exception as e:
            raise HTTPException(500, f"Video merge failed: {str(e)}")
    else:
        return {
            "project_id": project_id,
            "video_model": video_model,
            "results": results,
            "total": len(cuts),
            "completed": 0,
            "error": "No clips to merge"
        }


@router.post("/{project_id}/generate-async")
async def generate_all_videos_async(project_id: str, db: Session = Depends(get_db)):
    """Start video generation in background.

    v1.1.49: 이미지 생성이 진행 중이면 자동 대기 → 이미지 완료 3초 후 영상 순차 생성.
    사용자가 이미지 전에 눌러도 대기 → 이미지 끝나면 3초 후 시작.
    """
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, cancel_task, register_async_task, is_running, record_item_error

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "video"):
        return {"status": "already_running", "step": "video"}

    cut_count = db.query(Cut).filter(Cut.project_id == project_id).count()
    state = start_task(project_id, "video", cut_count)

    # 이미지가 아직 진행 중이면 step_states 를 "waiting" 으로, 아니면 "running"
    image_running = is_running(project_id, "image")
    step_states = dict(project.step_states or {})
    step_states["5"] = "waiting" if image_running else "running"
    project.step_states = step_states
    db.commit()

    _vlog(f"=== generate_all_videos_async called project={project_id} cut_count={cut_count} ===")

    async def _run():
        from app.models.database import SessionLocal
        import os as _os
        import time as _t
        _vlog(f"_run ENTER project={project_id}")
        local_db = SessionLocal()
        try:
            # ── 1) 이미지 완료 대기 ──────────────────────────────
            if is_running(project_id, "image"):
                print(f"[video-async] 이미지 생성 진행 중 → 완료 대기 시작")
                while is_running(project_id, "image"):
                    if state.status != "running":
                        print(f"[video-async] 대기 중 취소됨")
                        return
                    await asyncio.sleep(2)
                print(f"[video-async] 이미지 생성 완료 감지 → 3초 후 영상 시작")
                await asyncio.sleep(3)

            # step_states 를 "running" 으로 전환
            proj_for_state = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj_for_state.step_states or {})
            ss["5"] = "running"
            proj_for_state.step_states = ss
            local_db.commit()

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            proj_config = dict(proj.config or {})
            video_model = resolve_video_model(proj_config.get("video_model", DEFAULT_VIDEO_MODEL))
            aspect_ratio = proj_config.get("aspect_ratio", "16:9")
            enable_ai_video = bool(proj_config.get("enable_ai_video", True))
            selection = proj_config.get("video_target_selection", "all") if enable_ai_video else "none"
            ai_first_n = int(proj_config.get("ai_video_first_n", 5) or 0) if enable_ai_video else 0

            print(
                f"[video-async] START project={project_id} model={video_model} "
                f"aspect={aspect_ratio} total={cut_count} selection={selection} "
                f"mode=parallel({VIDEO_PARALLELISM})"
            )
            _vlog(f"_run config loaded model={video_model} aspect={aspect_ratio} selection={selection} ai_first_n={ai_first_n}")

            # v1.1.44: 사전 잔액/키 체크 — 문제 있으면 전체 런을 kenburns 로
            force_full_fallback, preflight_reason = await _preflight_fal_probe(video_model)
            _vlog(f"_run preflight force_full_fallback={force_full_fallback} reason={preflight_reason}")
            if force_full_fallback:
                print(f"[video-async] force_full_fallback=TRUE (reason={preflight_reason})")

            try:
                primary_service = get_video_service(video_model)
                _vlog(f"_run primary_service={type(primary_service).__name__}")
            except Exception as _e:
                import traceback as _tb
                _vlog(f"_run PRIMARY SERVICE INIT FAILED: {type(_e).__name__}: {_e}\n{_tb.format_exc()[-600:]}")
                raise
            kenburns_service = (
                primary_service
                if video_model == "ffmpeg-kenburns"
                else get_video_service("ffmpeg-kenburns")
            )
            static_service = (
                primary_service
                if video_model == "ffmpeg-static"
                else get_video_service("ffmpeg-static")
            )
            safe_motion_service = (
                primary_service
                if video_model == "ffmpeg-safe-motion"
                else get_video_service("ffmpeg-safe-motion")
            )
            v_dir = DATA_DIR / project_id / "videos"
            v_dir.mkdir(parents=True, exist_ok=True)

            cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
            total = len(cuts)
            _vlog(f"_run loaded {total} cuts from DB")
            script_cut_map = _load_script_cut_map(project_id)

            cut_specs = []
            for c in cuts:
                cut_specs.append({
                    "idx": c.cut_number,
                    "cut_number": c.cut_number,
                    "image_path": c.image_path,
                    "audio_path": c.audio_path,
                    "audio_duration": c.audio_duration or 5.0,
                    "script_cut": script_cut_map.get(int(c.cut_number), {}),
                })
            local_db.close()

            primary_disabled = [False]
            completed_counter = [0]
            cut_results: dict[int, str] = {}
            counts = {
                "ai": 0,
                "ai_fallback_kenburns": 0,
                "ffmpeg_forced": 0,
                "ffmpeg_safe_motion": 0,
                "ffmpeg_selection": 0,
                "failed": 0,
            }

            def _bump_progress():
                completed_counter[0] += 1
                update_task(project_id, "video", completed_counter[0])

            # ── 2) 병렬 생성 (Semaphore 로 동시 N개 제한) ─────────────────
            # v1.1.56: ComfyUI 로컬 모델이면 1로 강제.
            _par = _parallelism_for(video_model)
            sem = asyncio.Semaphore(_par)

            async def _worker(spec: dict):
                cut_number = spec["cut_number"]
                _vlog(f"_worker ENTER cut={cut_number} state.status={state.status}")
                if state.status != "running":
                    _vlog(f"_worker cut={cut_number} EARLY EXIT state.status={state.status}")
                    return

                if not spec["image_path"] or not spec["audio_path"]:
                    msg = (
                        f"image/audio path missing in DB "
                        f"(img={bool(spec['image_path'])}, aud={bool(spec['audio_path'])})"
                    )
                    print(f"[video-async] cut {cut_number} skipped: {msg}")
                    _vlog(f"_worker cut={cut_number} SKIP missing_path img={bool(spec['image_path'])} aud={bool(spec['audio_path'])}")
                    record_item_error(project_id, "video", cut_number, msg)
                    counts["failed"] += 1
                    _bump_progress()
                    return

                img_abs = _to_absolute(project_id, spec["image_path"])
                aud_abs = _to_absolute(project_id, spec["audio_path"])
                if not _os.path.exists(img_abs):
                    msg = f"image file not found on disk: {img_abs}"
                    print(f"[video-async] cut {cut_number} {msg}")
                    _vlog(f"_worker cut={cut_number} SKIP image_missing {img_abs}")
                    worker_db = SessionLocal()
                    try:
                        wc = worker_db.query(Cut).filter(
                            Cut.project_id == project_id,
                            Cut.cut_number == cut_number,
                        ).first()
                        if wc:
                            wc.status = "failed"
                            worker_db.commit()
                    finally:
                        worker_db.close()
                    record_item_error(project_id, "video", cut_number, msg)
                    counts["failed"] += 1
                    _bump_progress()
                    return
                if not _os.path.exists(aud_abs):
                    msg = f"audio file not found on disk: {aud_abs}"
                    print(f"[video-async] cut {cut_number} {msg}")
                    _vlog(f"_worker cut={cut_number} audio_missing {aud_abs}")
                    record_item_error(project_id, "video", cut_number, msg)

                _vlog(f"_worker cut={cut_number} waiting sem")
                async with sem:
                    _vlog(f"_worker cut={cut_number} acquired sem state.status={state.status}")
                    if state.status != "running":
                        _vlog(f"_worker cut={cut_number} EXIT_AFTER_SEM status={state.status}")
                        return
                    video_path_out = str(v_dir / f"cut_{cut_number}.mp4")
                    motion_prompt = _build_video_motion_prompt(
                        cut_number,
                        total,
                        proj_config,
                        spec.get("script_cut"),
                        video_model,
                    )
                    use_ai = should_generate_ai_video(cut_number, selection, ai_first_n)
                    force_safe_motion = use_ai and _should_force_safe_motion(
                        spec.get("script_cut"),
                        proj_config,
                        video_model,
                    )
                    print(
                        f"[video-async] cut {cut_number}/{total} START "
                        f"duration={spec['audio_duration']} "
                        f"model={'ffmpeg-safe-motion' if force_safe_motion else (video_model if use_ai else 'ffmpeg-static')} ai={use_ai} "
                        f"motion={motion_prompt[:60]}..."
                    )
                    _s = _t.time()
                    try:
                        # per-cut 타임아웃 12분 — fal 폴링 10분 + 다운로드/mux 여유 2분
                        result_path, source = await asyncio.wait_for(
                            _generate_one_cut_safe(
                                primary_service=primary_service,
                                kenburns_service=kenburns_service,
                                safe_motion_service=safe_motion_service,
                                static_service=static_service,
                                video_model=video_model,
                                use_ai=use_ai,
                                force_safe_motion=force_safe_motion,
                                force_full_fallback=force_full_fallback,
                                primary_disabled=primary_disabled,
                                img_abs=img_abs,
                                aud_abs=aud_abs,
                                duration=CUT_VIDEO_DURATION,
                                output_path=video_path_out,
                                aspect_ratio=aspect_ratio,
                                motion_prompt=motion_prompt,
                                cut_number=cut_number,
                                is_cancelled=lambda: state.status != "running",
                            ),
                            timeout=720,  # 12분
                        )
                        elapsed = _t.time() - _s
                        print(f"[video-async] cut {cut_number} DONE in {elapsed:.1f}s (source={source})")
                        counts[source] += 1
                        cut_results[cut_number] = result_path

                        worker_db = SessionLocal()
                        try:
                            wc = worker_db.query(Cut).filter(
                                Cut.project_id == project_id,
                                Cut.cut_number == cut_number,
                            ).first()
                            if wc:
                                wc.video_path = _to_relative(project_id, result_path)
                                if source == "ai":
                                    wc.video_model = video_model
                                elif source == "ai_fallback_kenburns":
                                    wc.video_model = "ffmpeg-kenburns (auto-fallback)"
                                elif source == "ffmpeg_forced":
                                    wc.video_model = "ffmpeg-kenburns (preflight-fallback)"
                                elif source == "ffmpeg_safe_motion":
                                    wc.video_model = "ffmpeg-safe-motion"
                                else:
                                    wc.video_model = "ffmpeg-static"
                                wc.status = "completed"
                                # v1.1.55-fix: 스튜디오 영상 생성 비용 기록 (AI 모델만)
                                if source == "ai":
                                    try:
                                        from app.services import spend_ledger
                                        spend_ledger.record_video(
                                            video_model, n_clips=1,
                                            project_id=project_id, note=f"studio cut_{cut_number}",
                                        )
                                    except Exception as _le:
                                        print(f"[spend_ledger] studio video record skipped: {_le}")
                                worker_db.commit()
                        finally:
                            worker_db.close()
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        print(f"[video-async] Cut {cut_number} FAILED: {e}\n{tb}")
                        counts["failed"] += 1
                        worker_db = SessionLocal()
                        try:
                            wc = worker_db.query(Cut).filter(
                                Cut.project_id == project_id,
                                Cut.cut_number == cut_number,
                            ).first()
                            if wc:
                                wc.status = "failed"
                                worker_db.commit()
                        finally:
                            worker_db.close()
                        tb_lines = [ln for ln in tb.strip().splitlines() if ln.strip()]
                        tail = "\n".join(tb_lines[-8:])
                        exc_line = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__}: (no message)"
                        err_msg = f"{exc_line}\n---\n{tail}"
                        record_item_error(project_id, "video", cut_number, err_msg)
                    finally:
                        _bump_progress()

            tasks = [asyncio.create_task(_worker(spec)) for spec in cut_specs]
            await asyncio.gather(*tasks, return_exceptions=True)

            # cut_number 순으로 clip_paths 구성
            clip_paths = [cut_results[k] for k in sorted(cut_results.keys())]
            print(
                f"[video-async] SUMMARY ai={counts['ai']} "
                f"ai_fallback_kenburns={counts['ai_fallback_kenburns']} "
                f"ffmpeg_forced={counts['ffmpeg_forced']} "
                f"ffmpeg_safe_motion={counts['ffmpeg_safe_motion']} "
                f"ffmpeg_selection={counts['ffmpeg_selection']} "
                f"failed={counts['failed']} "
                f"primary_disabled={primary_disabled[0]}"
            )

            # 메인 세션 재개 — merge & step_state 업데이트
            local_db = SessionLocal()

            # Merge
            merge_ok = True
            if clip_paths:
                try:
                    ffmpeg_svc = FFmpegService()
                    await ffmpeg_svc.merge_videos(clip_paths, str(v_dir / "merged.mp4"))
                except Exception as merge_err:
                    import traceback
                    merge_tb = traceback.format_exc()
                    print(f"[video-async] Merge failed: {merge_err}\n{merge_tb}")
                    merge_ok = False
                    tb_lines = [ln for ln in merge_tb.strip().splitlines() if ln.strip()]
                    tail = "\n".join(tb_lines[-6:])
                    exc_line = (
                        f"{type(merge_err).__name__}: {merge_err}"
                        if str(merge_err)
                        else f"{type(merge_err).__name__}: (no message)"
                    )
                    record_item_error(
                        project_id,
                        "video",
                        0,  # 0 = merge step, not a specific cut
                        f"MERGE FAILED — {exc_line}\n---\n{tail}\n(컷은 전부 생성됐지만 병합이 실패했습니다. 자막 렌더 단계에서 자동 재시도합니다.)",
                    )

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj.step_states or {})
            if clip_paths:
                ss["5"] = "completed"
                proj.step_states = ss
                local_db.commit()
                complete_task(project_id, "video")
                print(f"[video-async] DONE: {len(clip_paths)}/{len(cuts)} clips succeeded")

                # Auto-compose final_with_interludes.mp4 if interlude clips exist
                if merge_ok:
                    try:
                        from app.routers.interlude import build_interlude_sequence
                        inter_info = await build_interlude_sequence(
                            proj, project_id, local_db
                        )
                        if inter_info and inter_info.get("status") == "composed":
                            print(
                                f"[video-async] interlude auto-compose → "
                                f"{inter_info.get('output_path')} "
                                f"(clips={inter_info.get('total_clips')})"
                            )
                        else:
                            print(
                                f"[video-async] interlude auto-compose skipped: "
                                f"{inter_info.get('reason') if inter_info else 'no result'}"
                            )
                    except Exception as ie:
                        import traceback
                        print(
                            f"[video-async] interlude auto-compose FAILED "
                            f"(non-fatal): {ie}\n{traceback.format_exc()}"
                        )

                # v2.1.1: 영상 생성 완료 후 자동 렌더링 (자막 번인 포함)
                _auto_render_log = str(DATA_DIR / project_id / "auto_render.log")
                try:
                    from app.routers.subtitle import render_video_with_subtitles
                    from app.models.database import SessionLocal
                    with open(_auto_render_log, "w") as _lf:
                        _lf.write("auto-render START\n")
                    render_db = SessionLocal()
                    try:
                        result = await render_video_with_subtitles(project_id, db=render_db)
                        with open(_auto_render_log, "a") as _lf:
                            _lf.write(f"auto-render DONE: {result}\n")
                    finally:
                        render_db.close()
                except Exception as re:
                    import traceback
                    tb = traceback.format_exc()
                    with open(_auto_render_log, "a") as _lf:
                        _lf.write(f"auto-render FAILED: {re}\n{tb}\n")
                    print(f"[video-async] auto-render FAILED (non-fatal): {re}")
            else:
                ss["5"] = "failed"
                proj.step_states = ss
                local_db.commit()
                fail_task(project_id, "video", "모든 컷 생성 실패 — 백엔드 콘솔의 [video-async] 로그를 확인하세요")
                print(f"[video-async] FAILED: 0/{len(cuts)} clips succeeded — all cuts failed")
        except asyncio.CancelledError:
            # v1.1.55: cancel 시 failed 가 아닌 cancelled 상태로 처리
            print(f"[video-async] Task CANCELLED (asyncio)")
            cancel_task(project_id, "video")
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                ss = dict(proj.step_states or {})
                ss["5"] = "cancelled"
                proj.step_states = ss
                local_db.commit()
            except:
                pass
        except BaseException as e:
            import traceback
            print(f"[video-async] Task failed: {e}\n{traceback.format_exc()}")
            fail_task(project_id, "video", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                ss = dict(proj.step_states or {})
                ss["5"] = "failed"
                proj.step_states = ss
                local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "video", task)
    return {"status": "started", "step": "video", "total": cut_count}


@router.post("/{project_id}/resume-async")
async def resume_videos_async(project_id: str, db: Session = Depends(get_db)):
    """Resume video generation — only generate cuts that don't have video yet"""
    _vlog(f"=== resume_videos_async called project={project_id} ===")
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, cancel_task, register_async_task, is_running, record_item_error

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "video"):
        return {"status": "already_running", "step": "video"}

    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
    pending_cuts = [c for c in cuts if not c.video_path and c.image_path and c.audio_path]
    if not pending_cuts:
        return {"status": "nothing_to_resume", "step": "video", "total": 0}

    state = start_task(project_id, "video", len(pending_cuts))

    image_running = is_running(project_id, "image")
    step_states = dict(project.step_states or {})
    step_states["5"] = "waiting" if image_running else "running"
    project.step_states = step_states
    db.commit()

    async def _run():
        from app.models.database import SessionLocal
        import os as _os
        import time as _t
        local_db = SessionLocal()
        try:
            # ── 이미지 완료 대기 ──
            if is_running(project_id, "image"):
                print(f"[video-resume] 이미지 생성 진행 중 → 완료 대기")
                while is_running(project_id, "image"):
                    if state.status != "running":
                        return
                    await asyncio.sleep(2)
                print(f"[video-resume] 이미지 완료 → 3초 후 영상 시작")
                await asyncio.sleep(3)

            proj_for_state = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj_for_state.step_states or {})
            ss["5"] = "running"
            proj_for_state.step_states = ss
            local_db.commit()

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            proj_config = dict(proj.config or {})
            video_model = resolve_video_model(proj_config.get("video_model", DEFAULT_VIDEO_MODEL))
            aspect_ratio = proj_config.get("aspect_ratio", "16:9")
            enable_ai_video = bool(proj_config.get("enable_ai_video", True))
            selection = proj_config.get("video_target_selection", "all") if enable_ai_video else "none"
            ai_first_n = int(proj_config.get("ai_video_first_n", 5) or 0) if enable_ai_video else 0

            print(
                f"[video-resume] START project={project_id} model={video_model} "
                f"aspect={aspect_ratio} selection={selection} mode=parallel({VIDEO_PARALLELISM})"
            )

            force_full_fallback, preflight_reason = await _preflight_fal_probe(video_model)
            if force_full_fallback:
                print(f"[video-resume] force_full_fallback=TRUE (reason={preflight_reason})")

            primary_service = get_video_service(video_model)
            kenburns_service = (
                primary_service
                if video_model == "ffmpeg-kenburns"
                else get_video_service("ffmpeg-kenburns")
            )
            static_service = (
                primary_service
                if video_model == "ffmpeg-static"
                else get_video_service("ffmpeg-static")
            )
            safe_motion_service = (
                primary_service
                if video_model == "ffmpeg-safe-motion"
                else get_video_service("ffmpeg-safe-motion")
            )
            v_dir = DATA_DIR / project_id / "videos"
            v_dir.mkdir(parents=True, exist_ok=True)

            db_cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
            total_cuts_for_prompt = len(db_cuts)
            script_cut_map = _load_script_cut_map(project_id)

            pending_specs = []
            for c in db_cuts:
                if not c.video_path and c.image_path and c.audio_path:
                    pending_specs.append({
                        "cut_number": c.cut_number,
                        "image_path": c.image_path,
                        "audio_path": c.audio_path,
                        "audio_duration": c.audio_duration or 5.0,
                        "script_cut": script_cut_map.get(int(c.cut_number), {}),
                    })

            local_db.close()

            primary_disabled = [False]
            completed_counter = [0]
            cut_results: dict[int, str] = {}
            counts = {
                "ai": 0,
                "ai_fallback_kenburns": 0,
                "ffmpeg_forced": 0,
                "ffmpeg_safe_motion": 0,
                "ffmpeg_selection": 0,
                "failed": 0,
            }

            def _bump_progress():
                completed_counter[0] += 1
                update_task(project_id, "video", completed_counter[0])

            # ── 병렬 생성 ──
            # v1.1.56: ComfyUI 로컬 모델이면 1로 강제.
            _par = _parallelism_for(video_model)
            sem = asyncio.Semaphore(_par)

            async def _worker(spec: dict):
                cut_number = spec["cut_number"]
                if state.status != "running":
                    return
                img_abs = _to_absolute(project_id, spec["image_path"])
                aud_abs = _to_absolute(project_id, spec["audio_path"])
                if not _os.path.exists(img_abs):
                    msg = f"image file not found on disk: {img_abs}"
                    print(f"[video-resume] cut {cut_number} {msg}")
                    worker_db = SessionLocal()
                    try:
                        wc = worker_db.query(Cut).filter(
                            Cut.project_id == project_id,
                            Cut.cut_number == cut_number,
                        ).first()
                        if wc:
                            wc.status = "failed"
                            worker_db.commit()
                    finally:
                        worker_db.close()
                    record_item_error(project_id, "video", cut_number, msg)
                    counts["failed"] += 1
                    _bump_progress()
                    return

                async with sem:
                    if state.status != "running":
                        return
                    video_path_out = str(v_dir / f"cut_{cut_number}.mp4")
                    motion_prompt = _build_video_motion_prompt(
                        cut_number,
                        total_cuts_for_prompt,
                        proj_config,
                        spec.get("script_cut"),
                        video_model,
                    )
                    use_ai = should_generate_ai_video(cut_number, selection, ai_first_n)
                    force_safe_motion = use_ai and _should_force_safe_motion(
                        spec.get("script_cut"),
                        proj_config,
                        video_model,
                    )
                    print(
                        f"[video-resume] cut {cut_number} START "
                        f"model={'ffmpeg-safe-motion' if force_safe_motion else (video_model if use_ai else 'ffmpeg-static')} ai={use_ai}"
                    )
                    _s = _t.time()
                    try:
                        result_path, source = await asyncio.wait_for(
                            _generate_one_cut_safe(
                                primary_service=primary_service,
                                kenburns_service=kenburns_service,
                                safe_motion_service=safe_motion_service,
                                static_service=static_service,
                                video_model=video_model,
                                use_ai=use_ai,
                                force_safe_motion=force_safe_motion,
                                force_full_fallback=force_full_fallback,
                                primary_disabled=primary_disabled,
                                img_abs=img_abs,
                                aud_abs=aud_abs,
                                duration=CUT_VIDEO_DURATION,
                                output_path=video_path_out,
                                aspect_ratio=aspect_ratio,
                                motion_prompt=motion_prompt,
                                cut_number=cut_number,
                                is_cancelled=lambda: state.status != "running",
                            ),
                            timeout=720,
                        )
                        elapsed = _t.time() - _s
                        print(f"[video-resume] cut {cut_number} DONE in {elapsed:.1f}s (source={source})")
                        counts[source] += 1
                        cut_results[cut_number] = result_path

                        worker_db = SessionLocal()
                        try:
                            wc = worker_db.query(Cut).filter(
                                Cut.project_id == project_id,
                                Cut.cut_number == cut_number,
                            ).first()
                            if wc:
                                wc.video_path = _to_relative(project_id, result_path)
                                if source == "ai":
                                    wc.video_model = video_model
                                elif source == "ai_fallback_kenburns":
                                    wc.video_model = "ffmpeg-kenburns (auto-fallback)"
                                elif source == "ffmpeg_forced":
                                    wc.video_model = "ffmpeg-kenburns (preflight-fallback)"
                                elif source == "ffmpeg_safe_motion":
                                    wc.video_model = "ffmpeg-safe-motion"
                                else:
                                    wc.video_model = "ffmpeg-static"
                                wc.status = "completed"
                                # v1.1.55-fix: 스튜디오 영상 resume 비용 기록
                                if source == "ai":
                                    try:
                                        from app.services import spend_ledger
                                        spend_ledger.record_video(
                                            video_model, n_clips=1,
                                            project_id=project_id, note=f"studio resume cut_{cut_number}",
                                        )
                                    except Exception as _le:
                                        print(f"[spend_ledger] studio video resume record skipped: {_le}")
                                worker_db.commit()
                        finally:
                            worker_db.close()
                    except Exception as e:
                        import traceback
                        tb = traceback.format_exc()
                        print(f"[video-resume] Cut {cut_number} FAILED: {e}\n{tb}")
                        counts["failed"] += 1
                        worker_db = SessionLocal()
                        try:
                            wc = worker_db.query(Cut).filter(
                                Cut.project_id == project_id,
                                Cut.cut_number == cut_number,
                            ).first()
                            if wc:
                                wc.status = "failed"
                                worker_db.commit()
                        finally:
                            worker_db.close()
                        tb_lines = [ln for ln in tb.strip().splitlines() if ln.strip()]
                        tail = "\n".join(tb_lines[-8:])
                        exc_line = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__}: (no message)"
                        err_msg = f"{exc_line}\n---\n{tail}"
                        record_item_error(project_id, "video", cut_number, err_msg)
                    finally:
                        _bump_progress()

            tasks = [asyncio.create_task(_worker(spec)) for spec in pending_specs]
            await asyncio.gather(*tasks, return_exceptions=True)

            print(
                f"[video-resume] SUMMARY ai={counts['ai']} "
                f"ai_fallback_kenburns={counts['ai_fallback_kenburns']} "
                f"ffmpeg_forced={counts['ffmpeg_forced']} "
                f"ffmpeg_safe_motion={counts['ffmpeg_safe_motion']} "
                f"ffmpeg_selection={counts['ffmpeg_selection']} "
                f"failed={counts['failed']} "
                f"primary_disabled={primary_disabled[0]}"
            )

            local_db = SessionLocal()

            # Merge all clips (existing + newly generated). Always re-collect
            # from DB so already-completed clips are included in merge order.
            try:
                db_cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
                ordered_clips = [_to_absolute(project_id, c.video_path) for c in db_cuts if c.video_path]
            except Exception:
                ordered_clips = []
            if ordered_clips:
                try:
                    ffmpeg_svc = FFmpegService()
                    await ffmpeg_svc.merge_videos(ordered_clips, str(v_dir / "merged.mp4"))
                except Exception as merge_err:
                    import traceback
                    merge_tb = traceback.format_exc()
                    print(f"[video-resume] Merge failed: {merge_err}\n{merge_tb}")
                    tb_lines = [ln for ln in merge_tb.strip().splitlines() if ln.strip()]
                    tail = "\n".join(tb_lines[-6:])
                    exc_line = (
                        f"{type(merge_err).__name__}: {merge_err}"
                        if str(merge_err)
                        else f"{type(merge_err).__name__}: (no message)"
                    )
                    record_item_error(
                        project_id,
                        "video",
                        0,
                        f"MERGE FAILED — {exc_line}\n---\n{tail}\n(컷은 전부 생성됐지만 병합이 실패했습니다. 자막 렌더 단계에서 자동 재시도합니다.)",
                    )

            # Determine final step state based on whether ANY cut in the whole project has video
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            db_cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
            any_video = any(c.video_path for c in db_cuts)
            ss = dict(proj.step_states or {})
            if any_video:
                ss["5"] = "completed"
                proj.step_states = ss
                local_db.commit()
                complete_task(project_id, "video")
                print(f"[video-resume] DONE: {sum(1 for c in db_cuts if c.video_path)}/{len(db_cuts)} total clips")

                # Auto-compose final_with_interludes.mp4 if interlude clips exist
                try:
                    from app.routers.interlude import build_interlude_sequence
                    inter_info = await build_interlude_sequence(
                        proj, project_id, local_db
                    )
                    if inter_info and inter_info.get("status") == "composed":
                        print(
                            f"[video-resume] interlude auto-compose → "
                            f"{inter_info.get('output_path')} "
                            f"(clips={inter_info.get('total_clips')})"
                        )
                except Exception as ie:
                    import traceback
                    print(
                        f"[video-resume] interlude auto-compose FAILED "
                        f"(non-fatal): {ie}\n{traceback.format_exc()}"
                    )

                # v2.1.1: 영상 생성 완료 후 자동 렌더링 (자막 번인 포함)
                _auto_render_log = str(DATA_DIR / project_id / "auto_render.log")
                try:
                    from app.routers.subtitle import render_video_with_subtitles
                    from app.models.database import SessionLocal
                    with open(_auto_render_log, "w") as _lf:
                        _lf.write("auto-render START (resume)\n")
                    render_db = SessionLocal()
                    try:
                        result = await render_video_with_subtitles(project_id, db=render_db)
                        with open(_auto_render_log, "a") as _lf:
                            _lf.write(f"auto-render DONE: {result}\n")
                    finally:
                        render_db.close()
                except Exception as re:
                    import traceback
                    tb = traceback.format_exc()
                    with open(_auto_render_log, "a") as _lf:
                        _lf.write(f"auto-render FAILED: {re}\n{tb}\n")
                    print(f"[video-resume] auto-render FAILED (non-fatal): {re}")
            else:
                ss["5"] = "failed"
                proj.step_states = ss
                local_db.commit()
                fail_task(project_id, "video", "모든 컷 생성 실패 — 백엔드 콘솔의 [video-resume] 로그를 확인하세요")
                print(f"[video-resume] FAILED: 0 clips exist — all cuts failed")
        except asyncio.CancelledError:
            # v1.1.55: cancel 시 failed 가 아닌 cancelled 상태로 처리
            print(f"[video-resume] Task CANCELLED (asyncio)")
            cancel_task(project_id, "video")
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["5"] = "cancelled"
                    proj.step_states = ss
                    local_db.commit()
            except:
                pass
        except BaseException as e:
            import traceback
            print(f"[video-resume] Task failed: {e}\n{traceback.format_exc()}")
            fail_task(project_id, "video", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["5"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "video", task)
    return {"status": "started", "step": "video", "total": len(pending_cuts), "skipped": len(cuts) - len(pending_cuts)}
