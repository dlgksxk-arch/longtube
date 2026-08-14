from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

from app.services.tts import sfx_mix_service


def test_factory_v5_catalog_covers_ep01_audio_ids():
    expected = {
        "AMB_FOREST_DAWN_01",
        "AMB_FOREST_NIGHT_01",
        "AMB_ANCIENT_VILLAGE_DAY_01",
        "AMB_ANCIENT_VILLAGE_NIGHT_01",
        "AMB_STREAM_01",
        "AMB_ANCIENT_STOREHOUSE_01",
        "WEATHER_WIND_GENTLE_01",
        "AMB_FIELD_DRY_01",
        "FIRE_TORCH_01",
        "CROWD_SHOCK_01",
        "CROWD_MURMUR_01",
        "GASP_SINGLE_01",
        "DOOR_WOOD_OPEN_01",
        "HIT_DRUM_01",
        "FIRE_BUILDING_01",
        "STEP_DIRT_RUN_01",
        "CROWD_SILENCE_01",
        "HIT_LOW_01",
        "CLIFFHANGER_01",
    }

    assert expected.issubset(sfx_mix_service.SOUND_CATALOG)


def test_mix_applies_sheet_timing_volume_duck_and_keeps_raw(tmp_path: Path, monkeypatch):
    project_dir = tmp_path / "project"
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True)
    output = audio_dir / "cut_001.mp3"
    original_voice = b"original-voice" * 16
    output.write_bytes(original_voice)
    amb = tmp_path / "amb.wav"
    sfx = tmp_path / "sfx.wav"
    amb.write_bytes(b"ambience")
    sfx.write_bytes(b"effect")
    captured: list[str] = []

    monkeypatch.setattr(
        sfx_mix_service,
        "ensure_sound_library",
        lambda _ids, log=print: {"AMB_FOREST_DAWN_01": amb, "HIT_LOW_01": sfx},
    )
    monkeypatch.setattr(
        sfx_mix_service.FFmpegService,
        "probe_duration",
        AsyncMock(return_value=4.0),
    )

    async def fake_run(command, timeout=180.0):
        captured.extend(command)
        Path(command[-1]).write_bytes(b"mixed-audio")
        return ""

    monkeypatch.setattr(sfx_mix_service.FFmpegService, "_run_ffmpeg", fake_run)
    script = {
        "cuts": [
            {
                "cut_number": 1,
                "amb_id": "AMB_FOREST_DAWN_01",
                "sfx_id": "HIT_LOW_01",
                "sfx_timing_sec": 0.8,
                "sfx_volume_db": -20,
                "sfx_direction": "인용 구간은 환경음 추가 -6dB 덕킹",
                "audio_lead_in_sec": 0.2,
                "audio_tail_sec": 0.3,
            }
        ]
    }

    summary = asyncio.run(sfx_mix_service.mix_script_audio(script, project_dir, log=lambda _msg: None))

    assert summary["mixed"] == 1
    assert (audio_dir / "voice_raw" / "cut_001.mp3").read_bytes() == original_voice
    assert output.read_bytes() == b"mixed-audio"
    filter_complex = captured[captured.index("-filter_complex") + 1]
    assert "adelay=800:all=1" in filter_complex
    assert "volume=0.10000000" in filter_complex
    assert "0.501187" in filter_complex
    assert "amix=inputs=3" in filter_complex
    marker = json.loads((audio_dir / "cut_1.sfx.json").read_text(encoding="utf-8"))
    assert marker["sfx_timing_sec"] == 0.8
    assert marker["volume_db"] == -20.0
