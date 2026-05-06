"""TTS service factory"""
from app.services.tts.base import BaseTTSService
from app.services.tts.elevenlabs_service import ElevenLabsService

TTS_REGISTRY: dict[str, dict] = {
    "elevenlabs": {"name": "ElevenLabs", "provider": "elevenlabs", "default": True,
                   "cost_per_unit": "~$0.30/1K chars", "cost_value": 0.30},
}


def get_tts_service(model_id: str) -> BaseTTSService:
    if model_id == "elevenlabs":
        return ElevenLabsService()
    raise ValueError(f"Unknown TTS model: {model_id}")


def list_tts_models() -> list[dict]:
    return [{"id": k, **v} for k, v in TTS_REGISTRY.items()]
