"""Image service factory."""

from app.services.image.base import BaseImageService
from app.services.image.comfyui_service import ComfyUIImageService
from app.services.image.nano_banana_service import NanoBananaService
from app.services.image.openai_image_service import OpenAIImageService

DEFAULT_IMAGE_MODEL = "comfyui-dreamshaper-xl-longtube"
DEFAULT_THUMBNAIL_MODEL = "nano-banana-2"

IMAGE_REGISTRY: dict[str, dict] = {
    "comfyui-dreamshaper-xl": {
        "name": "SDXL Lightning",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube": {
        "name": "SDXL 로컬모델 v1",
        "provider": "comfyui",
        "default": True,
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-dreamshaper-xl-longtube-v15": {
        "name": "SDXL 로컬모델 v1.5 실사",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU, ~7GB)",
        "cost_value": 0.0,
    },
    "comfyui-z-image-turbo": {
        "name": "Z-Image Turbo",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU)",
        "cost_value": 0.0,
    },
    "comfyui-flux2-klein-4b": {
        "name": "Flux.2 Klein 4B",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU)",
        "cost_value": 0.0,
    },
    "comfyui-flux2-klein-9b": {
        "name": "Flux.2 Klein 9B FP8",
        "provider": "comfyui",
        "cost_per_unit": "Free (local GPU)",
        "cost_value": 0.0,
    },
    "openai-image-1": {
        "name": "GPT Image 1 (gpt-image-1)",
        "provider": "openai",
        "cost_per_unit": "~$0.02/image",
        "cost_value": 0.02,
    },
    "openai-image-2": {
        "name": "OpenAI Image 2 (gpt-image-2)",
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
    if provider == "comfyui":
        return ComfyUIImageService(model_id)

    raise ValueError(f"Unknown provider: {provider}")


def list_image_models() -> list[dict]:
    return [{"id": key, **meta} for key, meta in IMAGE_REGISTRY.items()]
