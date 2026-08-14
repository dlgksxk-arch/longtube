from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config
from app.services.video.subprocess_helper import find_ffmpeg


LIBRARY_DIR = Path(r"D:\long_result\_sfx_library")
SOURCE_DIR = LIBRARY_DIR / "source_mp3"
MANIFEST_PATH = LIBRARY_DIR / "manifest.json"

PRESETS = [
    {
        "id": "AMB_FOREST_DAWN_01",
        "duration": 8.0,
        "loop": True,
        "prompt": "Quiet natural forest at dawn, soft wind through trees, distant birds beginning to call, light leaf rustle, spacious realistic ambience. No speech, no narration, no music, no logo sound, no branded sound.",
    },
    {
        "id": "WEATHER_RAIN_HEAVY_01",
        "duration": 8.0,
        "loop": True,
        "prompt": "Heavy rain striking a timber roof, bare ground, and vegetation, strong runoff and continuous natural downpour. No speech, no narration, no music, no logo sound, no branded sound.",
    },
    {
        "id": "AMB_ANCIENT_VILLAGE_NIGHT_01",
        "duration": 8.0,
        "loop": True,
        "prompt": "Quiet ancient village at night, low hearth fire crackles, insects, distant dogs, occasional soft footsteps, historically neutral premodern ambience. No intelligible speech, no narration, no music, no modern elements.",
    },
    {
        "id": "SWORD_DRAW_01",
        "duration": 2.0,
        "loop": False,
        "prompt": "One iron sword slowly drawn from a leather and wood scabbard, dry metallic scrape, isolated close recording. No speech, no narration, no music, no additional impacts.",
    },
    {
        "id": "DOOR_WOOD_SLAM_01",
        "duration": 2.0,
        "loop": False,
        "prompt": "One heavy wooden door slammed shut violently, strong solid timber impact and short natural room resonance. No speech, no narration, no music.",
    },
    {
        "id": "HORSE_GALLOP_01",
        "duration": 5.0,
        "loop": False,
        "prompt": "One powerful horse galloping at full speed across packed earth, rapid realistic hoof impacts and light tack movement. No rider speech, no narration, no music.",
    },
    {
        "id": "FIRE_BUILDING_01",
        "duration": 7.0,
        "loop": True,
        "prompt": "Large wooden building burning intensely, strong flames, timber cracking, occasional beam snap, realistic exterior fire. No people, no speech, no narration, no music.",
    },
    {
        "id": "BATTLE_ANCIENT_DISTANT_01",
        "duration": 8.0,
        "loop": True,
        "prompt": "Large ancient battle heard from far away, indistinct shouts, scattered metal impacts, horses and deep drums, realistic spacious battlefield distance. No intelligible speech, no narration, no music score, no firearms.",
    },
    {
        "id": "HIT_LOW_01",
        "duration": 2.0,
        "loop": False,
        "prompt": "Single deep cinematic low-frequency impact, short attack and long dark decay, clean isolated post-production sound effect. No melody, no speech, no narration.",
    },
    {
        "id": "WHOOSH_SHORT_01",
        "duration": 1.5,
        "loop": False,
        "prompt": "One short clean air whoosh for a fast dramatic transition, quick pass and abrupt finish, isolated post-production sound effect. No musical tone, no speech, no narration.",
    },
]


def _runtime_key() -> str:
    return str(config.get_runtime_api_key("ELEVENLABS_API_KEY") or "").strip()


def _probe_wav(ffprobe: str, path: Path) -> dict:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration:stream=codec_name,sample_rate,channels,bits_per_raw_sample",
        "-of",
        "json",
        str(path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def main() -> int:
    api_key = _runtime_key()
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    if not Path(ffprobe).exists():
        bundled_probe = Path(__file__).resolve().parents[2] / "remotion-shorts" / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffprobe.exe"
        ffprobe = str(bundled_probe) if bundled_probe.exists() else "ffprobe"

    entries: list[dict] = []
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    with httpx.Client(timeout=120.0) as client:
        subscription = client.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": api_key})
        subscription.raise_for_status()
        usage = subscription.json()
        print(
            json.dumps(
                {
                    "subscription": usage.get("tier"),
                    "character_count": usage.get("character_count"),
                    "character_limit": usage.get("character_limit"),
                },
                ensure_ascii=False,
            )
        )

        for index, preset in enumerate(PRESETS, start=1):
            sfx_id = preset["id"]
            wav_path = LIBRARY_DIR / f"{sfx_id}.wav"
            mp3_path = SOURCE_DIR / f"{sfx_id}.mp3"
            if wav_path.exists() and wav_path.stat().st_size > 1024:
                print(f"[{index}/10] reuse {sfx_id}")
            else:
                print(f"[{index}/10] generate {sfx_id}")
                response = client.post(
                    "https://api.elevenlabs.io/v1/sound-generation",
                    params={"output_format": "mp3_44100_128"},
                    headers=headers,
                    json={
                        "text": preset["prompt"],
                        "duration_seconds": preset["duration"],
                        "prompt_influence": 0.5,
                        "loop": preset["loop"],
                        "model_id": "eleven_text_to_sound_v2",
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError(f"{sfx_id}: HTTP {response.status_code}: {response.text[:500]}")
                mp3_path.write_bytes(response.content)
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-i",
                        str(mp3_path),
                        "-ar",
                        "48000",
                        "-c:a",
                        "pcm_s24le",
                        str(wav_path),
                    ],
                    capture_output=True,
                    check=True,
                )

            probe = _probe_wav(ffprobe, wav_path)
            stream = (probe.get("streams") or [{}])[0]
            entries.append(
                {
                    **preset,
                    "path": str(wav_path),
                    "source_path": str(mp3_path),
                    "provider": "ElevenLabs",
                    "model_id": "eleven_text_to_sound_v2",
                    "codec": stream.get("codec_name"),
                    "sample_rate": int(stream.get("sample_rate") or 0),
                    "channels": int(stream.get("channels") or 0),
                    "bits_per_raw_sample": stream.get("bits_per_raw_sample"),
                    "actual_duration": round(float((probe.get("format") or {}).get("duration") or 0.0), 3),
                    "bytes": wav_path.stat().st_size,
                }
            )

    manifest = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_dir": str(LIBRARY_DIR),
        "count": len(entries),
        "items": entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"count": len(entries), "manifest": str(MANIFEST_PATH)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
