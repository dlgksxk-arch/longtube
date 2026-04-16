"""Project cost & duration estimation service.

프로젝트의 `config` 만으로 선택된 모델 조합에 근거해 예상 API 비용(USD)과
예상 처리 시간(초) 을 산정한다. DB / 외부 호출 없이 순수 계산이라
`/api/projects` 목록 직렬화 시마다 호출해도 비용이 거의 없다.

산정 근거는 아래 상수 블록에 명시되어 있으며, 실측값이 아닌 **공식 가격표 +
실전 관측 평균** 의 보수적 추정이다. 실제 청구액과 완벽히 일치하지 않으므로
UI 쪽에서 "예상" / "대략" 임을 반드시 표기한다.
"""
from __future__ import annotations

from typing import Any

from app.services.llm.factory import LLM_REGISTRY
from app.services.image.factory import IMAGE_REGISTRY
from app.services.tts.factory import TTS_REGISTRY
from app.services.video.factory import VIDEO_REGISTRY


# --------------------------------------------------------------------------- #
# 상수 — 산정 가정
# --------------------------------------------------------------------------- #

# 컷당 길이 (초). base.py SCRIPT_SYSTEM_PROMPT_KO 가 "각 컷 나레이션은 5초 분량"
# 을 강제하므로 고정.
SECONDS_PER_CUT = 5

# LLM 스크립트 생성 입력 토큰 추정 (시스템 프롬프트 + 토픽 + 예시)
LLM_INPUT_TOKENS = 2500

# 컷당 LLM 출력 토큰 (claude_service.py dynamic_max 산식과 동일)
LLM_TOKENS_PER_CUT = 180
LLM_OUTPUT_OVERHEAD = 2048

# 컷당 TTS 문자수 (한국어 기준 20~28자, 평균 24자)
TTS_CHARS_PER_CUT = 24

# 모델별 실측 평균 처리 시간 (초). 순차 호출 기준, 네트워크 지연 포함.
# "없으면 기본값" 원칙 — dict 에 없으면 IMAGE_DEFAULT_SEC 사용.
IMAGE_SEC_PER_CUT = {
    "openai-image-1":  18.0,
    "openai-dalle3":   22.0,
    "nano-banana-3":   12.0,
    "nano-banana-2":   10.0,
    "nano-banana-pro": 14.0,
    "nano-banana":     9.0,
    "seedream-v4.5":   12.0,
    "z-image-turbo":   4.0,
    "grok-imagine":    14.0,
    "flux-dev":        15.0,
    "flux-schnell":    3.0,
    "midjourney":      45.0,
}
IMAGE_DEFAULT_SEC = 15.0

# TTS 모델별 컷당 처리 시간
TTS_SEC_PER_CUT = {
    "elevenlabs":  2.5,
    "openai-tts":  1.8,
}
TTS_DEFAULT_SEC = 2.5

# 비디오 모델별 **컷당** 생성/렌더 시간
VIDEO_SEC_PER_CUT = {
    "ffmpeg-kenburns":  0.8,   # 로컬 FFmpeg Ken Burns 효과 — 매우 빠름
    "ffmpeg-static":    0.6,   # v1.1.40: 효과 없음 — Ken Burns 보다 살짝 더 빠름
    "ltx2-fast":        20.0,
    "ltx2-pro":         30.0,
    "seedance-lite":    35.0,
    "seedance-1.5-pro": 45.0,
    "seedance-1.0":     60.0,
    "kling-v2":         55.0,
    "kling-2.5-turbo":  50.0,
    "kling-2.6-pro":    70.0,
}
VIDEO_DEFAULT_SEC = 30.0

# LLM 스크립트 생성 자체 소요 (단일 호출, 토큰 길이와 거의 무관)
LLM_BASE_SEC = 45.0

# 자막 + 최종 합성 고정 비용 (초)
POST_PROCESS_SEC = 30.0

# v1.1.35: 원화 환산용 환율. 실시간 조회가 아니라 2026-04 대략 평균치 상수.
# 프론트/백엔드 어디서 노출하든 반드시 "≈ 1,360원/달러 가정" 주석을 곁들여야 한다.
USD_TO_KRW = 1360.0

# 일일 업로드 가정 — 월 예상 비용 계산의 분모.
DAYS_PER_MONTH = 30

# 편당 USD 기준 tier 임계치.
# - cheap     : ≤ $3  (한 편 ≈ 4,080원 / 월 ≈ 12만원)  green
# - normal    : $3~$8 (한 편 ≈ 4~11천원 / 월 ≈ 12~33만원)  yellow
# - expensive : > $8  (한 편 > 11,000원 / 월 > 33만원)  red
COST_TIER_CHEAP_MAX = 3.0
COST_TIER_NORMAL_MAX = 8.0

# v1.1.36: 영상 제작 대상 선택 — 선택되지 않은 컷은 ffmpeg-kenburns 폴백으로
# 처리되어 비용 0. 규칙은 backend/app/routers/video.py 의 should_generate_ai_video
# 와 **반드시** 일치해야 한다. 순환 임포트를 피하려고 여기선 복제한다.
VIDEO_TARGET_OPTIONS = {"all", "every_3", "every_4", "every_5", "character_only"}


def _count_ai_video_cuts(total_cuts: int, selection: str, ai_first_n: int = 5) -> int:
    """selection 에 따라 AI 비디오 모델로 생성될 컷 수를 계산.

    router/video.py 의 should_generate_ai_video 와 동일한 규칙:
    - all           : 전체
    - every_3/4/5   : (n-1) % N == 0  (1,4,7... / 1,5,9... / 1,6,11...)
    - character_only: every_3 과 동일 — image.py 의 cut_has_character 규칙과 일치

    v1.1.55: `ai_first_n` 양수면 컷 1..N 은 selection 무시하고 AI 로 카운트.
    """
    if total_cuts <= 0:
        return 0
    try:
        n_force = int(ai_first_n)
    except (TypeError, ValueError):
        n_force = 0
    if selection not in VIDEO_TARGET_OPTIONS or selection == "all":
        return total_cuts
    if selection == "every_3" or selection == "character_only":
        step = 3
    elif selection == "every_4":
        step = 4
    elif selection == "every_5":
        step = 5
    else:
        return total_cuts
    return sum(
        1 for n in range(1, total_cuts + 1)
        if (n_force > 0 and n <= n_force) or (n - 1) % step == 0
    )


# --------------------------------------------------------------------------- #
# 공용 헬퍼
# --------------------------------------------------------------------------- #

def _safe_int(value: Any, default: int) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _estimated_cuts(config: dict) -> int:
    target_duration = _safe_int(config.get("target_duration"), 300)
    return max(1, target_duration // SECONDS_PER_CUT)


# --------------------------------------------------------------------------- #
# 개별 단계 비용 산정
# --------------------------------------------------------------------------- #

def _estimate_llm_cost_usd(model_id: str, cuts: int) -> float:
    meta = LLM_REGISTRY.get(model_id)
    if not meta:
        return 0.0
    input_tokens = LLM_INPUT_TOKENS
    output_tokens = cuts * LLM_TOKENS_PER_CUT + LLM_OUTPUT_OVERHEAD
    cost_input = float(meta.get("cost_input") or 0.0)   # USD per 1M tokens
    cost_output = float(meta.get("cost_output") or 0.0)
    return (input_tokens * cost_input + output_tokens * cost_output) / 1_000_000.0


def _estimate_image_cost_usd(model_id: str, cuts: int) -> float:
    meta = IMAGE_REGISTRY.get(model_id)
    if not meta:
        return 0.0
    per_unit = float(meta.get("cost_value") or 0.0)
    return per_unit * cuts


def _estimate_tts_cost_usd(model_id: str, cuts: int) -> float:
    meta = TTS_REGISTRY.get(model_id)
    if not meta:
        return 0.0
    # cost_value 는 1K chars 당 USD
    chars = cuts * TTS_CHARS_PER_CUT
    per_1k = float(meta.get("cost_value") or 0.0)
    return (chars / 1000.0) * per_1k


def _estimate_video_cost_usd(model_id: str, cuts: int) -> float:
    meta = VIDEO_REGISTRY.get(model_id)
    if not meta:
        return 0.0
    # cost_value 는 5초 clip 당 USD. 한 컷 = 5초 = 1 clip.
    per_clip = float(meta.get("cost_value") or 0.0)
    return per_clip * cuts


# --------------------------------------------------------------------------- #
# 개별 단계 시간 산정
# --------------------------------------------------------------------------- #

def _estimate_image_seconds(model_id: str, cuts: int) -> float:
    per = IMAGE_SEC_PER_CUT.get(model_id, IMAGE_DEFAULT_SEC)
    return per * cuts


def _estimate_tts_seconds(model_id: str, cuts: int) -> float:
    per = TTS_SEC_PER_CUT.get(model_id, TTS_DEFAULT_SEC)
    return per * cuts


def _estimate_video_seconds(model_id: str, cuts: int) -> float:
    per = VIDEO_SEC_PER_CUT.get(model_id, VIDEO_DEFAULT_SEC)
    return per * cuts


# --------------------------------------------------------------------------- #
# Public — 프로젝트 단위 estimate
# --------------------------------------------------------------------------- #

def estimate_project(config: dict | None) -> dict:
    """Config 하나를 받아 비용/시간 추정치를 반환.

    Returns
    -------
    dict with keys:
        estimated_cuts: int
        target_duration: int  (seconds)
        estimated_cost_usd: float
        estimated_seconds: float
        cost_breakdown: dict[str, float]  (USD per stage)
        time_breakdown: dict[str, float]  (seconds per stage)
    """
    cfg = config or {}
    cuts = _estimated_cuts(cfg)
    target_duration = _safe_int(cfg.get("target_duration"), 300)

    script_model = cfg.get("script_model") or "claude-sonnet-4-6"
    image_model = cfg.get("image_model") or "openai-image-1"
    tts_model = cfg.get("tts_model") or "openai-tts"
    video_model = cfg.get("video_model") or "ffmpeg-kenburns"
    # v1.1.36: 영상 제작 대상 선택 — 미선택 컷은 ffmpeg-kenburns 폴백 (비용 0).
    video_target_selection = cfg.get("video_target_selection") or "all"
    ai_video_first_n = int(cfg.get("ai_video_first_n", 5) or 0)
    ai_video_cuts = _count_ai_video_cuts(cuts, video_target_selection, ai_video_first_n)
    fallback_video_cuts = max(0, cuts - ai_video_cuts)

    # ---- 비용 ----
    llm_cost = _estimate_llm_cost_usd(script_model, cuts)
    image_cost = _estimate_image_cost_usd(image_model, cuts)
    tts_cost = _estimate_tts_cost_usd(tts_model, cuts)
    # v1.1.36: 선택된 컷만 선택 모델, 나머지는 폴백 (cost_value=0)
    # v1.1.40: 폴백 모델이 ffmpeg-kenburns → ffmpeg-static 으로 변경 (효과 없음)
    video_cost = (
        _estimate_video_cost_usd(video_model, ai_video_cuts)
        + _estimate_video_cost_usd("ffmpeg-static", fallback_video_cuts)
    )
    total_cost = llm_cost + image_cost + tts_cost + video_cost

    # ---- 시간 ----
    llm_sec = LLM_BASE_SEC
    image_sec = _estimate_image_seconds(image_model, cuts)
    tts_sec = _estimate_tts_seconds(tts_model, cuts)
    # v1.1.36+v1.1.40: AI 컷은 선택 모델 시간, 나머지는 ffmpeg-static 의 0.6s/컷
    video_sec = (
        _estimate_video_seconds(video_model, ai_video_cuts)
        + _estimate_video_seconds("ffmpeg-static", fallback_video_cuts)
    )
    post_sec = POST_PROCESS_SEC
    total_sec = llm_sec + image_sec + tts_sec + video_sec + post_sec

    # ---- v1.1.35: 원화 환산 + 월 예상 + 경고 tier ----
    cost_krw = total_cost * USD_TO_KRW
    monthly_krw = cost_krw * DAYS_PER_MONTH
    monthly_usd = total_cost * DAYS_PER_MONTH

    if total_cost <= COST_TIER_CHEAP_MAX:
        cost_tier = "cheap"
    elif total_cost <= COST_TIER_NORMAL_MAX:
        cost_tier = "normal"
    else:
        cost_tier = "expensive"

    return {
        "estimated_cuts": cuts,
        "target_duration": target_duration,
        "estimated_cost_usd": round(total_cost, 4),
        # v1.1.35
        "estimated_cost_krw": round(cost_krw),
        "monthly_cost_usd": round(monthly_usd, 2),
        "monthly_cost_krw": round(monthly_krw),
        "cost_tier": cost_tier,
        "usd_to_krw": USD_TO_KRW,
        "days_per_month": DAYS_PER_MONTH,
        "estimated_seconds": round(total_sec, 1),
        "cost_breakdown": {
            "llm_script": round(llm_cost, 4),
            "image_generation": round(image_cost, 4),
            "tts": round(tts_cost, 4),
            "video": round(video_cost, 4),
        },
        "time_breakdown": {
            "llm_script": round(llm_sec, 1),
            "image_generation": round(image_sec, 1),
            "tts": round(tts_sec, 1),
            "video": round(video_sec, 1),
            "post_process": round(post_sec, 1),
        },
        "models_used": {
            "script": script_model,
            "image": image_model,
            "tts": tts_model,
            "video": video_model,
        },
        # v1.1.36
        "video_target_selection": video_target_selection,
        "ai_video_cuts": ai_video_cuts,
        "fallback_video_cuts": fallback_video_cuts,
    }


def format_krw(amount: float | int) -> str:
    """숫자를 '12,345원' 형태로 포맷. 소수점 버림."""
    try:
        n = int(round(float(amount)))
    except (TypeError, ValueError):
        return "-원"
    return f"{n:,}원"


def format_duration_ko(seconds: float) -> str:
    """초 단위 실수를 '3시간 12분' / '27분' / '45초' 형태로 포맷."""
    try:
        s = int(round(float(seconds)))
    except (TypeError, ValueError):
        return "-"
    if s < 60:
        return f"{s}초"
    m, sec = divmod(s, 60)
    if m < 60:
        return f"{m}분" if sec == 0 else f"{m}분 {sec}초"
    h, m = divmod(m, 60)
    if m == 0:
        return f"{h}시간"
    return f"{h}시간 {m}분"
