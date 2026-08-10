"""Persist and maintain character timing sidecars for generated TTS audio."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any


ALIGNMENT_VERSION = 1


def alignment_sidecar_path(audio_path: str | Path) -> Path:
    path = Path(audio_path)
    return path.with_suffix(".alignment.json")


def _valid_alignment(value: Any) -> bool:
    if value is None:
        return True
    if not isinstance(value, dict):
        return False
    characters = value.get("characters")
    starts = value.get("character_start_times_seconds")
    ends = value.get("character_end_times_seconds")
    return (
        isinstance(characters, list)
        and isinstance(starts, list)
        and isinstance(ends, list)
        and len(characters) == len(starts) == len(ends)
    )


def write_alignment_sidecar(
    audio_path: str | Path,
    *,
    text: str,
    alignment: Any,
    normalized_alignment: Any,
    provider: str,
    model_id: str,
) -> Path:
    if not _valid_alignment(alignment) or not _valid_alignment(normalized_alignment):
        raise ValueError("TTS alignment arrays are invalid")
    if alignment is None and normalized_alignment is None:
        raise ValueError("TTS response did not include alignment timestamps")

    sidecar = alignment_sidecar_path(audio_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": ALIGNMENT_VERSION,
        "provider": provider,
        "model_id": model_id,
        "text": str(text or ""),
        "alignment": alignment,
        "normalized_alignment": normalized_alignment,
    }
    tmp = sidecar.with_name(f"{sidecar.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar)
    return sidecar


def copy_alignment_sidecar(source_audio: str | Path, target_audio: str | Path) -> bool:
    source = alignment_sidecar_path(source_audio)
    if not source.exists():
        return False
    target = alignment_sidecar_path(target_audio)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def remove_alignment_sidecar(audio_path: str | Path) -> None:
    try:
        alignment_sidecar_path(audio_path).unlink(missing_ok=True)
    except OSError:
        pass


def scale_alignment_sidecar(audio_path: str | Path, factor: float) -> None:
    """Scale timestamps after a local tempo change. Padding needs no scaling."""
    sidecar = alignment_sidecar_path(audio_path)
    if not sidecar.exists() or factor <= 0 or abs(factor - 1.0) <= 0.0001:
        return
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return

    for key in ("alignment", "normalized_alignment"):
        value = payload.get(key)
        if not isinstance(value, dict):
            continue
        for field in ("character_start_times_seconds", "character_end_times_seconds"):
            times = value.get(field)
            if isinstance(times, list):
                value[field] = [round(max(0.0, float(item)) * factor, 6) for item in times]

    tmp = sidecar.with_name(f"{sidecar.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, sidecar)
