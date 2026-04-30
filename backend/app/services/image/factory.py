"""Image service factory."""

from app.services.image.base import BaseImageService
from app.services.image.comfyui_service import ComfyUIImageService
from app.services.image.fal_generic_service import FalGenericService
from app.services.image.flux_service import FluxService
from app.services.image.grok_service import GrokImageService
from app.services.image.midjourney_service import MidjourneyService
from app.services.image.nano_banana_service import NanoBananaService
from app.services.image.openai_image_service import OpenAIImageService

DEFAULT_IMAGE_MODEL = "comfyui-dreamshaper-xl-longtube"

IMAGE_REGISTRY: dict[str, dict] = {
    "comfyui-dreamshaper-xl": {
        "name": "DreamShaper XL Lightning",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-vector": {
        "name": "DreamShaper XL - Vector (Cartoon)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-mylora": {
        "name": "DreamShaper XL - MYLORA",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube": {
        "name": "DreamShaper XL + longtube_style_v1.safetensors (final)",
        "provider": "comfyui",
        "default": True,
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube-2k": {
        "name": "DreamShaper XL + longtube_style_v1-step00002000.safetensors (2K)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube-3k": {
        "name": "DreamShaper XL + longtube_style_v1-step00003000.safetensors (3K)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-qwen-image-edit-2509": {
        "name": "Qwen-Image-Edit 2509 (Reference required)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~20GB VRAM)",
        "cost_value": 0.0,
    },
    "openai-image-1": {
        "name": "GPT Image 1 (gpt-image-1)",
        "provider": "openai",
        "cost_per_unit": "~$0.02/image",
        "cost_value": 0.02,
    },
    "openai-dalle3": {
        "name": "DALL-E 3",
        "provider": "openai",
        "cost_per_unit": "~$0.04/image",
        "cost_value": 0.04,
    },
    "nano-banana-3": {
        "name": "Nano Banana 3 (Reference style lock)",
        "provider": "bbanana",
        "cost_per_unit": "~$0.04/image",
        "cost_value": 0.04,
    },
    "nano-banana-2": {
        "name": "Nano Banana 2",
        "provider": "bbanana",
        "cost_per_unit": "~$0.03/image",
        "cost_value": 0.03,
    },
    "nano-banana-pro": {
        "name": "Nano Banana Pro",
        "provider": "bbanana",
        "cost_per_unit": "~$0.05/image",
        "cost_value": 0.05,
    },
    "nano-banana": {
        "name": "Nano Banana",
        "provider": "bbanana",
        "cost_per_unit": "~$0.02/image",
        "cost_value": 0.02,
    },
    "seedream-v4.5": {
        "name": "Seedream V4.5",
        "provider": "fal",
        "cost_per_unit": "~$0.03/image",
        "cost_value": 0.03,
    },
    "z-image-turbo": {
        "name": "Z-IMAGE Turbo",
        "provider": "fal",
        "cost_per_unit": "~$0.005/image",
        "cost_value": 0.005,
    },
    "grok-imagine": {
        "name": "Grok Imagine Image",
        "provider": "xai",
        "cost_per_unit": "~$0.02/image",
        "cost_value": 0.02,
    },
    "flux-dev": {
        "name": "Flux Dev",
        "provider": "fal",
        "cost_per_unit": "~$0.04/image",
        "cost_value": 0.04,
    },
    "flux-schnell": {
        "name": "Flux Schnell",
        "provider": "fal",
        "cost_per_unit": "~$0.003/image",
        "cost_value": 0.003,
    },
    "midjourney": {
        "name": "Midjourney",
        "provider": "midjourney",
        "cost_per_unit": "$10~120/month",
        "cost_value": 0.04,
    },
}


def resolve_image_model(model_id: str | None) -> str:
    candidate = str(model_id or "").strip()
    return candidate if candidate in IMAGE_REGISTRY else DEFAULT_IMAGE_MODEL


def get_image_service(model_id: str) -> BaseImageService:
    requested_model_id = model_id
    model_id = resolve_image_model(model_id)

    if model_id != requested_model_id:
        import traceback as _tb

        _stack = "".join(_tb.format_stack()[-4:])
        print(
            f"[image-factory] Unknown/missing model '{requested_model_id}', "
            f"falling back to {DEFAULT_IMAGE_MODEL}"
        )
        try:
            from datetime import datetime as _dt

            from app.config import DATA_DIR

            _log = DATA_DIR / "logs" / "image_factory_fallback.log"
            _log.parent.mkdir(parents=True, exist_ok=True)
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(
                    f"[{_dt.now():%Y-%m-%d %H:%M:%S}] Unknown model "
                    f"'{requested_model_id}' -> {DEFAULT_IMAGE_MODEL}\n{_stack}\n"
                )
        except Exception:
            pass

    provider = IMAGE_REGISTRY[model_id]["provider"]

    if provider == "openai":
        return OpenAIImageService(model_id)
    if provider == "bbanana":
        return NanoBananaService(model_id)
    if provider == "fal":
        if model_id.startswith("flux"):
            return FluxService(model_id)
        return FalGenericService(model_id)
    if provider == "xai":
        return GrokImageService()
    if provider == "midjourney":
        return MidjourneyService()
    if provider == "comfyui":
        return ComfyUIImageService(model_id)

    raise ValueError(f"Unknown provider: {provider}")


def list_image_models() -> list[dict]:
    return [{"id": key, **meta} for key, meta in IMAGE_REGISTRY.items()]
