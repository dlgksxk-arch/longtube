"""Video service factory"""
from app.services.video.base import BaseVideoService
from app.services.video.ffmpeg_service import (
    FFmpegSafeMotionService,
    FFmpegService,
    FFmpegStaticService,
)
from app.services.video.kling_service import KlingService
from app.services.video.fal_service import FalVideoService
from app.services.video.comfyui_service import ComfyUIVideoService

DEFAULT_VIDEO_MODEL = "comfyui-hunyuan15-480p"
WAN22_TI2V_5B_MODEL = "comfyui-wan22-ti2v-5b"

# Keep old saved project configs safe: these local test models are no longer
# exposed in Studio, but if a preset still contains one, run Hunyuan instead.
DEPRECATED_LOCAL_VIDEO_MODEL_ALIASES = {
    "comfyui-ltxv-2b": DEFAULT_VIDEO_MODEL,
    "comfyui-ltxv-13b": DEFAULT_VIDEO_MODEL,
    "comfyui-wan22-i2v-fast": DEFAULT_VIDEO_MODEL,
    WAN22_TI2V_5B_MODEL: DEFAULT_VIDEO_MODEL,
    "comfyui-wan22-5b": DEFAULT_VIDEO_MODEL,
}

# Studio/local video generation exposes stable ComfyUI workflows only. Wan2.2
# TI2V-5B can preserve scenes, but on this PC the useful track-control path is
# far too slow for 120-cut production, so saved Wan/LTX test presets map to
# Hunyuan instead.

VIDEO_REGISTRY: dict[str, dict] = {
    # --- Local (free) ---
    "ffmpeg-kenburns":  {"name": "FFmpeg Ken Burns",      "provider": "local", "default": False,
                         "cost_per_unit": "Free (local)", "cost_value": 0},
    # v1.1.40: 폴백 전용 — 영상 제작 대상 선택 모드에서 미선택 컷에 적용.
    # 효과 없는 정지 이미지 영상. 사용자 선택 모델 드롭다운에는 default=False.
    "ffmpeg-static":    {"name": "FFmpeg Static (no motion)", "provider": "local-static",
                         "cost_per_unit": "Free (local)", "cost_value": 0},
    "ffmpeg-safe-motion": {
        "name": "FFmpeg Safe Static (source locked)",
        "provider": "local-safe-motion",
        "cost_per_unit": "Free (local)",
        "cost_value": 0,
    },
    "comfyui-hunyuan15-480p": {
        "name": "HunyuanVideo 1.5 480p I2V (Local ComfyUI)",
        "provider": "comfyui",
        "default": True,
        "cost_per_unit": "Free (local ComfyUI)",
        "cost_value": 0,
    },
    # --- Cheapest fal.ai options (added v1.1.11) ---
    "ltx2-fast":        {"name": "LTX Video 2.0 Fast",    "provider": "fal",
                         "cost_per_unit": "$0.20/5s (1080p) — $0.04/s", "cost_value": 0.20},
    "ltx2-pro":         {"name": "LTX Video 2.0 Pro",     "provider": "fal",
                         "cost_per_unit": "$0.30/5s (1080p) — $0.06/s", "cost_value": 0.30},

    # --- Seedance family (ByteDance via fal.ai) ---
    "seedance-lite":    {"name": "Seedance 1.0 Lite",     "provider": "fal",
                         "cost_per_unit": "$0.18/5s clip", "cost_value": 0.18},
    "seedance-1.5-pro": {"name": "Seedance 1.5 Pro",      "provider": "fal",
                         "cost_per_unit": "$0.24/5s (720p, audio) — $0.047/s", "cost_value": 0.24},
    "seedance-1.0":     {"name": "Seedance 1.0 Pro (legacy)", "provider": "fal",
                         "cost_per_unit": "$0.62/5s clip", "cost_value": 0.62},

    # --- Kling (via fal.ai, newer versions) ---
    "kling-v2":         {"name": "Kling V2 (legacy, native API)", "provider": "kling",
                         "cost_per_unit": "$0.14/5s clip", "cost_value": 0.14},
    "kling-2.5-turbo":  {"name": "Kling 2.5 Turbo Pro",   "provider": "fal",
                         "cost_per_unit": "$0.35/5s — $0.07/s", "cost_value": 0.35},
    "kling-2.6-pro":    {"name": "Kling 2.6 Pro (audio)", "provider": "fal",
                         "cost_per_unit": "Premium — fal pricing", "cost_value": 0.40},
}


def resolve_video_model(model_id: str | None) -> str:
    model_id = model_id or DEFAULT_VIDEO_MODEL
    if model_id in DEPRECATED_LOCAL_VIDEO_MODEL_ALIASES:
        return DEPRECATED_LOCAL_VIDEO_MODEL_ALIASES[model_id]
    return model_id


def get_video_service(model_id: str) -> BaseVideoService:
    original_model_id = model_id
    model_id = resolve_video_model(model_id)
    if original_model_id != model_id:
        print(f"[video-factory] Remapped deprecated local model '{original_model_id}' -> '{model_id}'")

    # Fallback to ffmpeg if unknown model selected
    if model_id not in VIDEO_REGISTRY:
        print(f"[video-factory] Unknown model '{model_id}', falling back to ffmpeg-kenburns")
        return FFmpegService()

    provider = VIDEO_REGISTRY[model_id]["provider"]

    if provider == "local":
        return FFmpegService()
    elif provider == "local-static":
        return FFmpegStaticService()
    elif provider == "local-safe-motion":
        return FFmpegSafeMotionService()
    elif provider == "kling":
        return KlingService()
    elif provider == "comfyui":
        return ComfyUIVideoService(model_id)
    elif provider == "fal":
        return FalVideoService(model_id)
    else:
        print(f"[video-factory] Provider '{provider}' not implemented, falling back to ffmpeg-kenburns")
        return FFmpegService()


def list_video_models() -> list[dict]:
    return [{"id": k, **v} for k, v in VIDEO_REGISTRY.items()]
