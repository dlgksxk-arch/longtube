from __future__ import annotations

import base64
import json
from pathlib import Path

from app.services.tts import dialogue_service
from app.services.tts.alignment import offset_alignment_sidecar, write_alignment_sidecar


def test_dialogue_group_uses_audio_tags_voice_ids_and_cut_timing(tmp_path: Path, monkeypatch):
    script = {
        "episode_id": "SILLA_EP01",
        "cuts": [
            {
                "cut_number": 2,
                "speaker": "소벌공",
                "narration": "[firmly] 물길을 합칩시다.",
                "voice_generation_mode": "DIALOGUE",
                "dialogue_group": "D01",
                "voice_direction": "낮고 단단하게",
                "emotion_intensity": "4",
                "tts_speed": "0.95",
                "audio_lead_in_sec": "0.1",
                "audio_tail_sec": "0.2",
            },
            {
                "cut_number": 4,
                "speaker": "무녀",
                "narration": "[quietly] 먼저 사람을 보십시오.",
                "voice_generation_mode": "DIALOGUE",
                "dialogue_group": "D01",
                "voice_direction": "조용히",
                "emotion_intensity": "3",
                "tts_speed": "1.02",
                "audio_lead_in_sec": "0.15",
                "audio_tail_sec": "0.25",
            },
        ],
    }
    config = {
        "tts_model": "elevenlabs",
        "episode_id": "SILLA_EP01",
        "tts_character_voice_ids": {"소벌공": "voice-a", "무녀": "voice-b"},
    }
    captured = {}

    def request_dialogue(payload):
        captured.update(payload)
        return {
            "audio_base64": base64.b64encode(b"fake-master-audio").decode("ascii"),
            "voice_segments": [
                {"dialogue_input_index": 0, "start_time_seconds": 0.0, "end_time_seconds": 1.0, "character_start_index": 0, "character_end_index": 4},
                {"dialogue_input_index": 1, "start_time_seconds": 1.1, "end_time_seconds": 2.0, "character_start_index": 4, "character_end_index": 8},
            ],
            "alignment": {
                "characters": list("abcdefgh"),
                "character_start_times_seconds": [i * 0.25 for i in range(8)],
                "character_end_times_seconds": [(i + 1) * 0.25 for i in range(8)],
            },
            "normalized_alignment": None,
        }

    rendered = []

    def render_turn(_master, output, **kwargs):
        output.write_bytes(b"rendered-audio")
        rendered.append((output.name, kwargs))
        return 1.5

    monkeypatch.setattr(dialogue_service, "_render_turn", render_turn)
    results = dialogue_service.generate_dialogue_groups(
        script,
        config,
        tmp_path,
        request_dialogue=request_dialogue,
    )

    assert captured["inputs"] == [
        {"text": "[firmly] 물길을 합칩시다.", "voice_id": "voice-a"},
        {"text": "[quietly] 먼저 사람을 보십시오.", "voice_id": "voice-b"},
    ]
    assert rendered[0][1]["speed"] == 0.95
    assert rendered[0][1]["lead"] == 0.1
    assert rendered[0][1]["tail"] == 0.2
    assert rendered[1][1]["speed"] == 1.02
    assert results[2]["dialogue_group"] == "D01"
    assert results[4]["dialogue_input_index"] == 1
    manifest = json.loads((tmp_path / "audio" / "dialogue_groups" / "D01.manifest.json").read_text(encoding="utf-8"))
    assert manifest["payload"]["turn_settings"][0]["voice_direction"] == "낮고 단단하게"


def test_alignment_offset_moves_character_times(tmp_path: Path):
    audio = tmp_path / "cut_001.mp3"
    audio.write_bytes(b"audio")
    write_alignment_sidecar(
        audio,
        text="가나",
        alignment={
            "characters": ["가", "나"],
            "character_start_times_seconds": [0.0, 0.2],
            "character_end_times_seconds": [0.2, 0.4],
        },
        normalized_alignment=None,
        provider="test",
        model_id="test",
    )

    offset_alignment_sidecar(audio, 0.15)

    payload = json.loads(audio.with_suffix(".alignment.json").read_text(encoding="utf-8"))
    assert payload["alignment"]["character_start_times_seconds"] == [0.15, 0.35]
    assert payload["alignment"]["character_end_times_seconds"] == [0.35, 0.55]
