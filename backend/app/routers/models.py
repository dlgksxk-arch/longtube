"""Model listing router"""
from fastapi import APIRouter

from app.services.llm.factory import list_llm_models
from app.services.image.factory import list_image_models
from app.services.video.factory import list_video_models
from app.services.tts.factory import list_tts_models
from app import config

router = APIRouter()

# Map provider name → config attribute(s) that must be set
PROVIDER_KEY_MAP: dict[str, list[str]] = {
    "anthropic":  ["ANTHROPIC_API_KEY"],
    "openai":     ["OPENAI_API_KEY"],
    "elevenlabs": ["ELEVENLABS_API_KEY"],
    "fal":        ["FAL_KEY"],
    "xai":        ["XAI_API_KEY"],
    "kling":      ["KLING_ACCESS_KEY", "KLING_SECRET_KEY"],
    "comfyui":    ["COMFYUI_BASE_URL"],
    "replicate":  ["REPLICATE_API_TOKEN"],
    "runway":     ["RUNWAY_API_KEY"],
    "midjourney": ["MIDJOURNEY_API_KEY"],
    "bbanana":    ["FAL_KEY"],  # Banana uses fal key
    "ffmpeg":     [],  # local, always available
    "local":      [],  # local tools, always available
    "luma":       [],  # TODO: add key when implemented
    "pika":       [],  # TODO: add key when implemented
    "minimax":    [],  # TODO: add key when implemented
}


def _enrich_with_availability(models: list[dict]) -> list[dict]:
    """Add 'available' boolean to each model based on whether its provider API key is configured."""
    result = []
    for m in models:
        provider = m.get("provider", "")
        keys_needed = PROVIDER_KEY_MAP.get(provider, [])
        available = all(bool(getattr(config, k, "")) for k in keys_needed) if keys_needed else True
        result.append({**m, "available": available})
    return result


@router.get("/llm")
def list_llm():
    """List available LLM models"""
    return {
        "models": _enrich_with_availability(list_llm_models())
    }


@router.get("/image")
def list_image():
    """List available image models"""
    return {
        "models": _enrich_with_availability(list_image_models())
    }


@router.get("/video")
def list_video():
    """List available video models"""
    return {
        "models": _enrich_with_availability(list_video_models())
    }


@router.get("/tts")
def list_tts():
    """List available TTS models"""
    return {
        "models": _enrich_with_availability(list_tts_models())
    }
