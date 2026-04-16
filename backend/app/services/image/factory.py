"""Image service factory"""
from app.services.image.base import BaseImageService
from app.services.image.flux_service import FluxService
from app.services.image.fal_generic_service import FalGenericService
from app.services.image.grok_service import GrokImageService
from app.services.image.nano_banana_service import NanoBananaService
from app.services.image.midjourney_service import MidjourneyService
from app.services.image.openai_image_service import OpenAIImageService
from app.services.image.comfyui_service import ComfyUIImageService

# v1.1.61: 로컬 ComfyUI 이미지 모델은 DreamShaper XL Lightning 하나만 유지.
# 나머지 SD1.5/Flux2/Z-Image/기타는 스타일 제어/설치 난이도 문제로 제거.

IMAGE_REGISTRY: dict[str, dict] = {
    "comfyui-dreamshaper-xl": {
        "name": "ComfyUI DreamShaper XL Lightning (local, SDXL)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-qwen-image-edit-2509": {
        "name": "ComfyUI Qwen-Image-Edit 2509 fp8 (local, 레퍼런스 필수)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~20GB VRAM 권장)",
        "cost_value": 0.0,
    },
    "openai-image-1":  {"name": "GPT Image 1 (gpt-image-1)", "provider": "openai", "default": True,
                        "cost_per_unit": "~$0.02/image", "cost_value": 0.02},
    "openai-dalle3":   {"name": "DALL-E 3",                   "provider": "openai",
                        "cost_per_unit": "~$0.04/image", "cost_value": 0.04},
    "nano-banana-3":   {"name": "Nano Banana 3 (레퍼런스 스타일 락)", "provider": "bbanana",
                        "cost_per_unit": "~$0.04/image", "cost_value": 0.04},
    "nano-banana-2":   {"name": "Nano Banana 2",      "provider": "bbanana",
                        "cost_per_unit": "~$0.03/image", "cost_value": 0.03},
    "nano-banana-pro": {"name": "Nano Banana Pro",     "provider": "bbanana",
                        "cost_per_unit": "~$0.05/image", "cost_value": 0.05},
    "nano-banana":     {"name": "Nano Banana",         "provider": "bbanana",
                        "cost_per_unit": "~$0.02/image", "cost_value": 0.02},
    "seedream-v4.5":   {"name": "Seedream V4.5",       "provider": "fal",
                        "cost_per_unit": "~$0.03/image", "cost_value": 0.03},
    "z-image-turbo":   {"name": "Z-IMAGE Turbo",       "provider": "fal",
                        "cost_per_unit": "~$0.005/image", "cost_value": 0.005},
    "grok-imagine":    {"name": "Grok Imagine Image",  "provider": "xai",
                        "cost_per_unit": "~$0.02/image", "cost_value": 0.02},
    "flux-dev":        {"name": "Flux Dev",             "provider": "fal",
                        "cost_per_unit": "~$0.04/image", "cost_value": 0.04},
    "flux-schnell":    {"name": "Flux Schnell",         "provider": "fal",
                        "cost_per_unit": "~$0.003/image", "cost_value": 0.003},
    "midjourney":      {"name": "Midjourney",           "provider": "midjourney",
                        "cost_per_unit": "$10~120/month", "cost_value": 0.04},
}


def get_image_service(model_id: str) -> BaseImageService:
    # v1.1.61: 기존 프로젝트 config 에 comfyui-* 가 남아있을 수 있어 기본값으로 폴백.
    if model_id not in IMAGE_REGISTRY:
        print(f"[image-factory] Unknown model '{model_id}', falling back to openai-image-1")
        model_id = "openai-image-1"

    provider = IMAGE_REGISTRY[model_id]["provider"]

    if provider == "openai":
        return OpenAIImageService(model_id)
    elif provider == "bbanana":
        return NanoBananaService(model_id)
    elif provider == "fal":
        if model_id.startswith("flux"):
            return FluxService(model_id)
        return FalGenericService(model_id)
    elif provider == "xai":
        return GrokImageService()
    elif provider == "midjourney":
        return MidjourneyService()
    elif provider == "comfyui":
        return ComfyUIImageService(model_id)

    raise ValueError(f"Unknown provider: {provider}")


def list_image_models() -> list[dict]:
    return [{"id": k, **v} for k, v in IMAGE_REGISTRY.items()]
