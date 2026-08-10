from app import config
from app.routers.api_status import _key
from app.services.image.factory import (
    DEFAULT_THUMBNAIL_MODEL,
    resolve_thumbnail_model,
)


def test_openai_api_key_is_hard_disabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    monkeypatch.setenv("OPENAI_ADMIN_KEY", "must-not-be-used")

    assert config.OPENAI_API_DISABLED is True
    assert config.OPENAI_API_KEY == ""
    assert config.get_runtime_api_key("OPENAI_API_KEY") == ""
    assert config.get_runtime_api_key("OPENAI_ADMIN_KEY") == ""
    assert _key("OPENAI_API_KEY") == ""


def test_thumbnail_models_are_forced_to_local_comfyui():
    assert DEFAULT_THUMBNAIL_MODEL == "comfyui-z-image-turbo"
    assert resolve_thumbnail_model("openai-image-1") == DEFAULT_THUMBNAIL_MODEL
    assert resolve_thumbnail_model("nano-banana-pro") == DEFAULT_THUMBNAIL_MODEL
    assert resolve_thumbnail_model("comfyui-flux2-klein-4b") == "comfyui-flux2-klein-4b"
