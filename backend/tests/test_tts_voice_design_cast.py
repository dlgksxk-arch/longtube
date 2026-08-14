from __future__ import annotations

from app.services.tts.voice_design_cast import _design_payload, ensure_dialogue_voice_cast


def test_voice_design_v3_payload_omits_unsupported_quality_parameter():
    payload = _design_payload(
        prompt="Korean male ceremonial officiant with a low steady voice.",
        series="신라사",
        speaker="장례 집전자",
    )

    assert payload["model_id"] == "eleven_ttv_v3"
    assert "quality" not in payload


def test_voice_design_minor_age_terms_are_removed_only_from_provider_payload():
    original = (
        "Korean adolescent boy around 13, clear youthful male voice, "
        "slightly formal from being raised as a sacred child."
    )

    payload = _design_payload(prompt=original, series="신라사", speaker="박혁거세")

    assert "13" not in payload["voice_description"]
    assert "adolescent" not in payload["voice_description"].lower()
    assert "child" not in payload["voice_description"].lower()
    assert "youthful male" in payload["voice_description"]
    assert "adolescent boy around 13" in original


def _script():
    return {
        "series": "신라사",
        "voice_cast": [
            {
                "인물명": "소벌공",
                "Voice Design Prompt": "Korean male in his 50s with a deep steady and controlled voice.",
                "voice_id": "",
                "유지정책": "장기유지",
            }
        ],
        "cuts": [
            {
                "cut_number": 1,
                "speaker": "해설자",
                "voice_generation_mode": "TTS",
            },
            {
                "cut_number": 2,
                "speaker": "소벌공",
                "voice_generation_mode": "DIALOGUE",
            },
        ],
    }


def test_voice_design_provisions_and_persists_character_mapping():
    script = _script()
    config = {"tts_model": "elevenlabs", "factory_series": "신라사"}
    calls = []

    def create_voice(**kwargs):
        calls.append(kwargs)
        return "new-character-voice"

    changed = ensure_dialogue_voice_cast(script, config, create_voice=create_voice)

    assert changed is True
    assert len(calls) == 1
    assert calls[0]["voice_name"] == "신라사 - 소벌공"
    assert script["voice_cast"][0]["voice_id"] == "new-character-voice"
    assert config["tts_character_voice_ids"] == {"소벌공": "new-character-voice"}
    assert config["tts_character_voice_registry"]["소벌공"]["voice_id"] == "new-character-voice"


def test_existing_registry_is_reused_without_voice_design_call():
    script = _script()
    prompt = script["voice_cast"][0]["Voice Design Prompt"]
    config = {
        "tts_model": "elevenlabs",
        "tts_character_voice_registry": {
            "소벌공": {
                "voice_id": "stored-character-voice",
                "prompt_sha256": __import__("hashlib").sha256(prompt.encode("utf-8")).hexdigest(),
                "policy": "장기유지",
                "updated_at": "earlier",
            }
        },
    }

    def unexpected_create(**_kwargs):
        raise AssertionError("Voice Design API must not be called")

    ensure_dialogue_voice_cast(script, config, create_voice=unexpected_create)

    assert script["voice_cast"][0]["voice_id"] == "stored-character-voice"
    assert config["tts_character_voice_ids"]["소벌공"] == "stored-character-voice"
