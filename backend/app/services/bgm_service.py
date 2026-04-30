"""BGM generation service."""
from __future__ import annotations

from pathlib import Path

import httpx

from app import config

BASE_URL = "https://api.elevenlabs.io/v1"


def build_bgm_prompt(
    *,
    topic: str = "",
    title: str = "",
    style_prompt: str = "",
    language: str = "ko",
) -> str:
    base = (style_prompt or "").strip()
    if not base:
        subject = (title or topic or "documentary narration").strip()
        base = (
            "subtle cinematic documentary background music, instrumental only, "
            "no vocals, no lyrics, soft percussion, low tension, supports narration"
        )
        if subject:
            base += f", topic: {subject}"
    if "no vocals" not in base.lower() and "instrumental" not in base.lower():
        base += ", instrumental only, no vocals, no lyrics"
    if language:
        base += f", suitable for {language} narration"
    return base


async def generate_bgm(
    *,
    prompt: str,
    output_path: str | Path,
    length_ms: int,
) -> dict:
    api_key = config.ELEVENLABS_API_KEY
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured")

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Keep generated loops moderate. The renderer loops this under the full video.
    length_ms = max(10_000, min(int(length_ms or 60_000), 180_000))

    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(
            f"{BASE_URL}/music/compose",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "prompt": prompt,
                "music_length_ms": length_ms,
            },
        )
        if resp.status_code >= 400:
            detail = resp.text[:1000]
            raise RuntimeError(f"ElevenLabs Music failed HTTP {resp.status_code}: {detail}")
        target.write_bytes(resp.content)

    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError("ElevenLabs Music returned an empty audio file")

    return {
        "path": str(target),
        "size": target.stat().st_size,
        "length_ms": length_ms,
        "prompt": prompt,
    }
