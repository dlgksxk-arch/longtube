"""Video service factory"""
from app.services.video.base import BaseVideoService
from app.services.video.ffmpeg_service import (
    FFmpegSafeMotionService,
    FFmpegStaticService,
)
from app.services.video.fal_service import FalVideoService

DEFAULT_VIDEO_MODEL = "ffmpeg-static"
WAN22_TI2V_5B_MODEL = "comfyui-wan22-ti2v-5b"

# Keep old saved project configs safe: these local test models are no longer
# exposed in Studio, but if a preset still contains one, run FFmpeg Static instead.
DEPRECATED_LOCAL_VIDEO_MODEL_ALIASES = {
    "ffmpeg-kenburns": "ffmpeg-static",
    "comfyui-ltxv-2b": DEFAULT_VIDEO_MODEL,
    "comfyui-ltxv-13b": DEFAULT_VIDEO_MODEL,
    "comfyui-wan22-i2v-fast": DEFAULT_VIDEO_MODEL,
    WAN22_TI2V_5B_MODEL: DEFAULT_VIDEO_MODEL,
    "comfyui-wan22-5b": DEFAULT_VIDEO_MODEL,
}

VIDEO_REGISTRY: dict[str, dict] = {
    # --- Local (free) ---
    # v1.1.40: 폴백 전용 — 영상 제작 대상 선택 모드에서 미선택 컷에 적용.
    # 효과 없는 정지 이미지 영상. 사용자 선택 모델 드롭다운에는 default=False.
    "ffmpeg-static":    {"name": "FFmpeg Static (no motion)", "provider": "local-static",
                         "default": True, "cost_per_unit": "Free (local)", "cost_value": 0},
    "ffmpeg-safe-motion": {
        "name": "숏츠",
        "provider": "local-safe-motion",
        "cost_per_unit": "Free (local)",
        "cost_value": 0,
    },
    "seedance-lite":    {"name": "Seedance 1.0 Lite",     "provider": "fal",
                         "cost_per_unit": "$0.18/5s clip", "cost_value": 0.18},
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
        print(f"[video-factory] Unknown model '{model_id}', falling back to ffmpeg-static")
        return FFmpegStaticService()

    provider = VIDEO_REGISTRY[model_id]["provider"]

    if provider == "local-static":
        return FFmpegStaticService()
    elif provider == "local-safe-motion":
        return FFmpegSafeMotionService()
    elif provider == "fal":
        return FalVideoService(model_id)
    else:
        print(f"[video-factory] Provider '{provider}' not implemented, falling back to ffmpeg-static")
        return FFmpegStaticService()


def list_video_models() -> list[dict]:
    return [{"id": k, **v} for k, v in VIDEO_REGISTRY.items()]
