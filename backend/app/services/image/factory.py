"""Image service factory"""
from app.services.image.base import BaseImageService
from app.services.image.flux_service import FluxService
from app.services.image.fal_generic_service import FalGenericService
from app.services.image.grok_service import GrokImageService
from app.services.image.nano_banana_service import NanoBananaService
from app.services.image.midjourney_service import MidjourneyService
from app.services.image.openai_image_service import OpenAIImageService
from app.services.image.comfyui_service import ComfyUIImageService

# v1.1.63: 로컬 ComfyUI 이미지 모델 현황
#   - DreamShaper XL Lightning 베이스 5종 (기본 / Vector / LongTube 2K / 3K / 4K)
#   - Qwen-Image-Edit 2509 fp8 (레퍼런스 필수, 별개 모델)
# SD1.5/Flux2/MeinaMix/ReVAnimated/ToonYou/Z-Image 워크플로 JSON 은 workflows/ 에
# 남아있지만 스타일 제어·설치 난이도 문제로 레지스트리 미등록 (사용 불가).

IMAGE_REGISTRY: dict[str, dict] = {
    "comfyui-dreamshaper-xl": {
        "name": "ComfyUI DreamShaper XL Lightning (local, SDXL)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-vector": {
        "name": "ComfyUI DreamShaper XL + Vector Art (카툰/벡터, local)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube": {
        "name": "ComfyUI DreamShaper XL + LongTube Style 4K (커스텀, local)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube-2k": {
        "name": "ComfyUI DreamShaper XL + LongTube Style 2K (커스텀, local)",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube-3k": {
        "name": "ComfyUI DreamShaper XL + LongTube Style 3K (커스텀, local)",
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
        import traceback as _tb
        _stack = "".join(_tb.format_stack()[-4:])
        print(f"[image-factory] Unknown model '{model_id}', falling back to openai-image-1")
        # v2.1.2: 파일 로그로도 남김 (콘솔 없는 환경 디버깅용)
        try:
            from app.config import DATA_DIR
            _log = DATA_DIR / "logs" / "image_factory_fallback.log"
            _log.parent.mkdir(parents=True, exist_ok=True)
            from datetime import datetime as _dt
            with open(_log, "a", encoding="utf-8") as _f:
                _f.write(f"[{_dt.now():%Y-%m-%d %H:%M:%S}] Unknown model '{model_id}' → openai-image-1\n{_stack}\n")
        except Exception:
            pass
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
