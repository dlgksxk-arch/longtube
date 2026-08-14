"""Factory V5 ambience and action-SFX provisioning/mixing."""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from app import config as app_config
from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.subprocess_helper import find_ffmpeg


LIBRARY_DIR = Path(r"D:\long_result\_sfx_library")
SOURCE_DIR = LIBRARY_DIR / "source_mp3"
MANIFEST_PATH = LIBRARY_DIR / "manifest.json"
SOUND_MODEL_ID = "eleven_text_to_sound_v2"


def _entry(prompt: str, duration: float, *, loop: bool) -> dict[str, Any]:
    return {"prompt": prompt, "duration": duration, "loop": loop}


SOUND_CATALOG: dict[str, dict[str, Any]] = {
    "AMB_FOREST_DAWN_01": _entry("Quiet natural forest at dawn, soft wind through trees, distant birds beginning to call, light leaf rustle, spacious realistic ambience. No speech, narration, or music.", 8.0, loop=True),
    "AMB_FOREST_NIGHT_01": _entry("Quiet forest at night, low wind through leaves, steady insects, one very distant owl, spacious realistic ambience. No speech, narration, music, or modern sounds.", 8.0, loop=True),
    "AMB_ANCIENT_VILLAGE_DAY_01": _entry("Quiet premodern village in daytime, light wind, timber creaks, distant work activity and soft indistinct crowd presence with no intelligible words. No narration, music, vehicles, or modern sounds.", 8.0, loop=True),
    "AMB_ANCIENT_VILLAGE_NIGHT_01": _entry("Quiet ancient village at night, low hearth fire crackles, insects, distant dogs, occasional soft footsteps, historically neutral premodern ambience. No intelligible speech, narration, or music.", 8.0, loop=True),
    "AMB_STREAM_01": _entry("Steady shallow natural stream flowing over small stones, soft bank vegetation and light breeze, clean realistic outdoor ambience. No speech, narration, music, or modern sounds.", 8.0, loop=True),
    "AMB_ANCIENT_STOREHOUSE_01": _entry("Interior of a premodern timber grain storehouse, faint wood creaks, dry grain sacks shifting, soft dust and distant footsteps outside. No intelligible speech, narration, music, machinery, or modern sounds.", 8.0, loop=True),
    "WEATHER_WIND_GENTLE_01": _entry("Gentle steady outdoor wind moving through dry grass and sparse leaves, natural open landscape ambience. No speech, narration, music, storm, or modern sounds.", 8.0, loop=True),
    "AMB_FIELD_DRY_01": _entry("Dry field under light wind, brittle grass and grain stalks rustling, sparse insects, realistic open rural ambience. No speech, narration, music, machinery, or modern sounds.", 8.0, loop=True),
    "FIRE_TORCH_01": _entry("One handheld pitch torch burning close by, steady flame flutter and small resin crackles, isolated realistic sound. No speech, narration, music, or other fire.", 4.0, loop=True),
    "CROWD_SHOCK_01": _entry("One brief collective shock reaction from a small premodern crowd, a unified gasp and restrained body movement, no intelligible words. No narration or music.", 2.0, loop=False),
    "CROWD_MURMUR_01": _entry("Low restrained murmur from a small premodern village crowd, worried atmosphere, no intelligible words and no individual voice foregrounded. No narration or music.", 5.0, loop=True),
    "GASP_SINGLE_01": _entry("One short human gasp of surprise, isolated close recording, no words, no additional voices, no narration, and no music.", 1.5, loop=False),
    "DOOR_WOOD_OPEN_01": _entry("One heavy rough wooden door slowly opening on dry wooden hinges, a single creak and soft timber movement. No slam, speech, narration, or music.", 2.5, loop=False),
    "HIT_DRUM_01": _entry("One deep strike on a large hide drum, short attack with a natural low resonance and clean decay. No rhythm, melody, speech, or narration.", 2.0, loop=False),
    "FIRE_BUILDING_01": _entry("Large wooden building burning intensely, strong flames, timber cracking, occasional beam snap, realistic exterior fire. No people, speech, narration, or music.", 7.0, loop=True),
    "STEP_DIRT_RUN_01": _entry("A short burst of one person running fast across packed dirt, realistic footfalls and light clothing movement. No speech, narration, music, horse, or vehicle.", 3.0, loop=False),
    "CROWD_SILENCE_01": _entry("A small worried crowd abruptly falls silent, leaving only faint clothing movement and room tone, no intelligible words. No narration or music.", 2.5, loop=False),
    "HIT_LOW_01": _entry("Single deep cinematic low-frequency impact, short attack and long dark decay, clean isolated post-production sound effect. No melody, speech, or narration.", 2.0, loop=False),
    "CLIFFHANGER_01": _entry("One short dark suspense impact that rises slightly then stops on an unresolved low tone, cinematic sound effect only. No melody, rhythm, speech, narration, or logo sound.", 2.5, loop=False),
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_manifest() -> dict[str, Any]:
    try:
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_manifest(items: dict[str, dict[str, Any]]) -> None:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_dir": str(LIBRARY_DIR),
        "count": len(items),
        "items": [items[key] for key in sorted(items)],
    }
    temporary = MANIFEST_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, MANIFEST_PATH)


def ensure_sound_library(sound_ids: set[str], *, log: Callable[[str], None] = print) -> dict[str, Path]:
    requested = {str(value or "").strip() for value in sound_ids if str(value or "").strip()}
    unknown = sorted(requested.difference(SOUND_CATALOG))
    if unknown:
        raise ValueError(f"등록되지 않은 AMB/SFX ID: {', '.join(unknown)}")

    manifest = _load_manifest()
    manifest_items = {
        str(item.get("id") or ""): dict(item)
        for item in (manifest.get("items") or [])
        if isinstance(item, dict) and item.get("id")
    }
    ready: dict[str, Path] = {}
    missing: list[str] = []
    for sound_id in sorted(requested):
        path = LIBRARY_DIR / f"{sound_id}.wav"
        if path.exists() and path.stat().st_size > 1024:
            ready[sound_id] = path
        else:
            missing.append(sound_id)

    if missing:
        api_key = str(app_config.get_runtime_api_key("ELEVENLABS_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("효과음 생성에 필요한 ELEVENLABS_API_KEY가 없습니다.")
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        ffmpeg = find_ffmpeg()
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        with httpx.Client(timeout=180.0) as client:
            for index, sound_id in enumerate(missing, start=1):
                spec = SOUND_CATALOG[sound_id]
                log(f"SFX library {index}/{len(missing)} generate {sound_id}")
                response = client.post(
                    "https://api.elevenlabs.io/v1/sound-generation",
                    params={"output_format": "mp3_44100_128"},
                    headers=headers,
                    json={
                        "text": spec["prompt"],
                        "duration_seconds": spec["duration"],
                        "prompt_influence": 0.5,
                        "loop": bool(spec["loop"]),
                        "model_id": SOUND_MODEL_ID,
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"{sound_id} 생성 실패 HTTP {response.status_code}: {response.text[:400]}"
                    )
                mp3_path = SOURCE_DIR / f"{sound_id}.mp3"
                wav_path = LIBRARY_DIR / f"{sound_id}.wav"
                mp3_path.write_bytes(response.content)
                import subprocess

                converted = subprocess.run(
                    [ffmpeg, "-y", "-i", str(mp3_path), "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(wav_path)],
                    capture_output=True,
                    check=False,
                )
                if converted.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size <= 1024:
                    raise RuntimeError(f"{sound_id} WAV 변환 실패")
                ready[sound_id] = wav_path

    for sound_id in sorted(requested):
        spec = SOUND_CATALOG[sound_id]
        wav_path = ready[sound_id]
        manifest_items[sound_id] = {
            "id": sound_id,
            **spec,
            "path": str(wav_path),
            "source_path": str(SOURCE_DIR / f"{sound_id}.mp3"),
            "provider": "ElevenLabs",
            "model_id": SOUND_MODEL_ID,
            "sample_rate": 48000,
            "channels": 2,
            "bytes": wav_path.stat().st_size,
        }
    _write_manifest(manifest_items)
    return ready


def _audio_path(audio_dir: Path, cut_number: int) -> Path | None:
    for name in (f"cut_{cut_number}.mp3", f"cut_{cut_number:03d}.mp3"):
        candidate = audio_dir / name
        if candidate.exists() and candidate.stat().st_size > 100:
            return candidate
    return None


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


async def mix_script_audio(
    script: dict[str, Any],
    project_dir: Path,
    *,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    cuts = [item for item in (script.get("cuts") or []) if isinstance(item, dict)]
    ids = {
        str(cut.get(key) or "").strip()
        for cut in cuts
        for key in ("amb_id", "sfx_id")
        if str(cut.get(key) or "").strip()
    }
    if not ids:
        return {"mixed": 0, "skipped": len(cuts), "sound_ids": []}
    library = ensure_sound_library(ids, log=log)
    audio_dir = project_dir / "audio"
    raw_dir = audio_dir / "voice_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    mixed = 0
    skipped = 0
    current_amb = ""
    amb_elapsed = 0.0
    for cut in sorted(cuts, key=lambda item: int(item.get("cut_number") or 0)):
        cut_number = int(cut.get("cut_number") or 0)
        output = _audio_path(audio_dir, cut_number)
        if output is None:
            raise FileNotFoundError(f"SFX 믹싱 대상 음성 누락: cut {cut_number}")
        marker_path = audio_dir / f"cut_{cut_number}.sfx.json"
        raw_path = raw_dir / output.name
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except Exception:
            marker = {}
        current_hash = _sha256(output)
        if not raw_path.exists() or marker.get("mixed_sha256") != current_hash:
            shutil.copy2(output, raw_path)

        duration = float(await FFmpegService.probe_duration(str(raw_path)) or 0.0)
        if duration <= 0:
            raise RuntimeError(f"SFX 믹싱 대상 음성 길이 확인 실패: cut {cut_number}")
        amb_id = str(cut.get("amb_id") or "").strip()
        sfx_id = str(cut.get("sfx_id") or "").strip()
        if amb_id != current_amb:
            current_amb = amb_id
            amb_elapsed = 0.0
        amb_phase = amb_elapsed
        if amb_id:
            amb_elapsed += duration

        if not amb_id and not sfx_id:
            if output.read_bytes() != raw_path.read_bytes():
                shutil.copy2(raw_path, output)
            marker_path.unlink(missing_ok=True)
            cut["audio_mix"] = {"amb_id": "", "sfx_id": ""}
            skipped += 1
            continue

        volume_db = _number(cut.get("sfx_volume_db"), -22.0)
        gain = math.pow(10.0, volume_db / 20.0)
        inputs = [find_ffmpeg(), "-y", "-i", str(raw_path)]
        filters = ["[0:a]aformat=sample_rates=48000:channel_layouts=stereo[voice]"]
        mix_labels = ["[voice]"]
        input_index = 1
        if amb_id:
            spec = SOUND_CATALOG[amb_id]
            phase = amb_phase % float(spec["duration"])
            inputs.extend(["-stream_loop", "-1", "-ss", f"{phase:.3f}", "-i", str(library[amb_id])])
            lead = max(0.0, _number(cut.get("audio_lead_in_sec"), 0.0))
            tail = max(0.0, _number(cut.get("audio_tail_sec"), 0.0))
            direction = str(cut.get("sfx_direction") or "")
            volume_expr = f"{gain:.8f}"
            if "-6dB" in direction or "-6 dB" in direction:
                duck_start = max(0.0, lead - 0.4)
                duck_end = max(duck_start, duration - tail + 0.4)
                volume_expr = f"{gain:.8f}*if(between(t,{duck_start:.3f},{duck_end:.3f}),0.501187,1)"
            filters.append(
                f"[{input_index}:a]atrim=0:{duration:.3f},asetpts=PTS-STARTPTS,"
                f"aformat=sample_rates=48000:channel_layouts=stereo,"
                f"volume='{volume_expr}':eval=frame[amb]"
            )
            mix_labels.append("[amb]")
            input_index += 1
        if sfx_id:
            timing_ms = max(0, int(round(_number(cut.get("sfx_timing_sec"), 0.0) * 1000.0)))
            inputs.extend(["-i", str(library[sfx_id])])
            filters.append(
                f"[{input_index}:a]adelay={timing_ms}:all=1,atrim=0:{duration:.3f},"
                f"aformat=sample_rates=48000:channel_layouts=stereo,"
                f"volume={gain:.8f}[sfx]"
            )
            mix_labels.append("[sfx]")
        filters.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=first:dropout_transition=0:normalize=0,"
            + "alimiter=limit=0.95:level=false[out]"
        )
        temporary = output.with_suffix(".sfx.tmp.mp3")
        command = inputs + [
            "-filter_complex", ";".join(filters),
            "-map", "[out]", "-t", f"{duration:.3f}",
            "-c:a", "libmp3lame", "-b:a", "192k", "-ar", "48000",
            str(temporary),
        ]
        await FFmpegService._run_ffmpeg(command, timeout=180.0)
        os.replace(temporary, output)
        payload = {
            "version": "factory-v5-sfx-v1",
            "cut_number": cut_number,
            "amb_id": amb_id,
            "amb_phase_sec": round(amb_phase, 3) if amb_id else None,
            "sfx_id": sfx_id,
            "sfx_timing_sec": _number(cut.get("sfx_timing_sec"), 0.0) if sfx_id else None,
            "volume_db": volume_db,
            "raw_sha256": _sha256(raw_path),
            "mixed_sha256": _sha256(output),
        }
        marker_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        cut["audio_mix"] = payload
        mixed += 1
        log(f"SFX mixed cut {cut_number}: amb={amb_id or '-'} sfx={sfx_id or '-'}")
    return {"mixed": mixed, "skipped": skipped, "sound_ids": sorted(ids)}
