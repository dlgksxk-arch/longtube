"""Generate Factory V5 dialogue groups with ElevenLabs Text to Dialogue."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

import httpx

from app import config as app_config
from app.services.tts.alignment import offset_alignment_sidecar, write_alignment_sidecar
from app.services.tts.base import probe_audio_duration
from app.services.video.subprocess_helper import find_ffmpeg


ELEVENLABS_DIALOGUE_URL = "https://api.elevenlabs.io/v1/text-to-dialogue/with-timestamps"
ELEVENLABS_DIALOGUE_MODEL = "eleven_v3"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dialogue_groups(script: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for cut in script.get("cuts") or []:
        if not isinstance(cut, dict):
            continue
        if _text(cut.get("voice_generation_mode")).upper() != "DIALOGUE":
            continue
        group = _text(cut.get("dialogue_group"))
        if not group:
            raise RuntimeError(f"DIALOGUE 컷의 대화그룹이 비어 있습니다: cut {cut.get('cut_number')}")
        groups.setdefault(group, []).append(cut)
    return groups


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _slice_alignment(
    value: Any,
    *,
    character_start: int,
    character_end: int,
    segment_start: float,
    speed: float,
    lead: float,
) -> dict[str, list[Any]] | None:
    if not isinstance(value, dict):
        return None
    characters = value.get("characters")
    starts = value.get("character_start_times_seconds")
    ends = value.get("character_end_times_seconds")
    if not all(isinstance(items, list) for items in (characters, starts, ends)):
        return None
    upper = min(character_end, len(characters), len(starts), len(ends))
    lower = max(0, min(character_start, upper))
    return {
        "characters": characters[lower:upper],
        "character_start_times_seconds": [
            round(max(0.0, (_float(item, segment_start) - segment_start) / speed + lead), 6)
            for item in starts[lower:upper]
        ],
        "character_end_times_seconds": [
            round(max(0.0, (_float(item, segment_start) - segment_start) / speed + lead), 6)
            for item in ends[lower:upper]
        ],
    }


def _render_turn(
    master_path: Path,
    output_path: Path,
    *,
    start: float,
    end: float,
    speed: float,
    lead: float,
    tail: float,
) -> float:
    if end <= start:
        raise RuntimeError(f"Dialogue 음성 구간이 잘못되었습니다: {start:.3f}~{end:.3f}")
    ffmpeg = find_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_name(f"{output_path.stem}.dialogue-tmp{output_path.suffix}")
    lead_ms = max(0, round(lead * 1000))
    filters = [
        f"atrim=start={max(0.0, start):.6f}:end={end:.6f}",
        "asetpts=PTS-STARTPTS",
        f"atempo={max(0.7, min(1.2, speed)):.6f}",
    ]
    if lead_ms:
        filters.append(f"adelay={lead_ms}:all=1")
    if tail > 0:
        filters.append(f"apad=pad_dur={tail:.6f}")
    cmd = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(master_path),
        "-af",
        ",".join(filters),
        "-c:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(tmp),
    ]
    completed = subprocess.run(cmd, capture_output=True, check=False, timeout=120)
    if completed.returncode != 0 or not tmp.is_file() or tmp.stat().st_size <= 100:
        message = completed.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"Dialogue 컷 분리 실패: {output_path.name}: {message}")
    os.replace(tmp, output_path)
    return float(probe_audio_duration(str(output_path)) or 0.0)


def apply_cut_audio_padding(audio_path: str | Path, *, lead: float, tail: float) -> float:
    """Bake the workbook's per-cut lead/tail into TTS audio exactly once."""
    path = Path(audio_path)
    lead = max(0.0, float(lead or 0.0))
    tail = max(0.0, float(tail or 0.0))
    if lead <= 0 and tail <= 0:
        return float(probe_audio_duration(str(path)) or 0.0)
    ffmpeg = find_ffmpeg()
    tmp = path.with_name(f"{path.stem}.padding-tmp{path.suffix}")
    filters = []
    if lead > 0:
        filters.append(f"adelay={round(lead * 1000)}:all=1")
    if tail > 0:
        filters.append(f"apad=pad_dur={tail:.6f}")
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-af",
            ",".join(filters),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "2",
            str(tmp),
        ],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if completed.returncode != 0 or not tmp.is_file() or tmp.stat().st_size <= 100:
        message = completed.stderr.decode("utf-8", errors="replace")[-1200:]
        raise RuntimeError(f"컷별 선행호흡·후행여백 적용 실패: {path.name}: {message}")
    os.replace(tmp, path)
    offset_alignment_sidecar(path, lead)
    return float(probe_audio_duration(str(path)) or 0.0)


def _group_payload(
    group: str,
    cuts: list[dict[str, Any]],
    character_ids: dict[str, str],
    *,
    episode_id: str,
) -> dict[str, Any]:
    inputs = []
    turn_settings = []
    for cut in cuts:
        speaker = _text(cut.get("speaker"))
        voice_id = _text(character_ids.get(speaker))
        if not voice_id:
            raise RuntimeError(f"DIALOGUE 화자 전용 voice_id가 없습니다: {speaker}")
        narration = _text(cut.get("narration"))
        if not narration:
            raise RuntimeError(f"DIALOGUE 대사가 비어 있습니다: cut {cut.get('cut_number')}")
        inputs.append({"text": narration, "voice_id": voice_id})
        turn_settings.append({
            "cut_number": int(cut.get("cut_number") or 0),
            "speed": max(0.7, min(1.2, _float(cut.get("tts_speed"), 1.0))),
            "lead": max(0.0, _float(cut.get("audio_lead_in_sec"), 0.0)),
            "tail": max(0.0, _float(cut.get("audio_tail_sec"), 0.0)),
            "voice_direction": _text(cut.get("voice_direction")),
            "emotion_intensity": _text(cut.get("emotion_intensity")),
        })
    if sum(len(item["text"]) for item in inputs) > 2000:
        raise RuntimeError(f"Dialogue 그룹이 2,000자를 초과합니다: {group}")
    if len({item["voice_id"] for item in inputs}) > 10:
        raise RuntimeError(f"Dialogue 그룹의 고유 음성이 10개를 초과합니다: {group}")
    seed_source = f"{episode_id}:{group}:" + json.dumps(inputs, ensure_ascii=False, sort_keys=True)
    return {
        "version": 1,
        "group": group,
        "model_id": ELEVENLABS_DIALOGUE_MODEL,
        "language_code": "ko",
        "seed": int(hashlib.sha256(seed_source.encode("utf-8")).hexdigest()[:8], 16),
        "inputs": inputs,
        "turn_settings": turn_settings,
    }


def generate_dialogue_groups(
    script: dict[str, Any],
    config: dict[str, Any],
    project_dir: str | Path,
    *,
    request_dialogue: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    log: Callable[[str], None] | None = None,
) -> dict[int, dict[str, Any]]:
    """Generate each DIALOGUE group once and split it back into cut audio."""
    groups = _dialogue_groups(script)
    if not groups:
        return {}
    if _text(config.get("tts_model")).lower() != "elevenlabs":
        raise RuntimeError("DIALOGUE 그룹은 ElevenLabs Text-to-Dialogue로만 생성할 수 있습니다.")
    character_ids = config.get("tts_character_voice_ids")
    if not isinstance(character_ids, dict):
        raise RuntimeError("DIALOGUE 화자 음성 매핑이 없습니다.")

    root = Path(project_dir)
    audio_dir = root / "audio"
    group_dir = audio_dir / "dialogue_groups"
    group_dir.mkdir(parents=True, exist_ok=True)
    api_key = app_config.get_runtime_api_key("ELEVENLABS_API_KEY")

    if request_dialogue is None:
        if not api_key:
            raise RuntimeError("ElevenLabs Text-to-Dialogue API 키가 비어 있습니다.")

        def request_dialogue(payload: dict[str, Any]) -> dict[str, Any]:
            with httpx.Client(timeout=240.0) as client:
                response = client.post(
                    ELEVENLABS_DIALOGUE_URL,
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": api_key, "Content-Type": "application/json"},
                    json={
                        "inputs": payload["inputs"],
                        "model_id": payload["model_id"],
                        "language_code": payload["language_code"],
                        "seed": payload["seed"],
                    },
                )
                response.raise_for_status()
                return response.json()

    results: dict[int, dict[str, Any]] = {}
    episode_id = _text(config.get("episode_id") or script.get("episode_id") or script.get("episode_code"))
    for group, cuts in groups.items():
        payload = _group_payload(group, cuts, character_ids, episode_id=episode_id)
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        manifest_path = group_dir / f"{group}.manifest.json"
        cached = None
        if manifest_path.is_file():
            try:
                cached = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cached = None
        if isinstance(cached, dict) and cached.get("fingerprint") == fingerprint:
            cached_turns = cached.get("turns") or []
            if all((audio_dir / str(item.get("file") or "")).is_file() for item in cached_turns):
                for item in cached_turns:
                    results[int(item["cut_number"])] = dict(item)
                if log:
                    log(f"Dialogue {group} 캐시 재사용")
                continue

        if log:
            log(f"Dialogue {group} 생성: {len(cuts)}턴")
        response_data = request_dialogue(payload)
        audio_base64 = _text(response_data.get("audio_base64"))
        try:
            audio_bytes = base64.b64decode(audio_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(f"Dialogue {group} 응답 음성이 손상되었습니다.") from exc
        if not audio_bytes:
            raise RuntimeError(f"Dialogue {group} 응답 음성이 비어 있습니다.")
        master_path = group_dir / f"{group}.mp3"
        master_tmp = master_path.with_name(f"{master_path.name}.tmp")
        master_tmp.write_bytes(audio_bytes)
        os.replace(master_tmp, master_path)

        segments = response_data.get("voice_segments") or []
        by_input: dict[int, list[dict[str, Any]]] = {}
        for segment in segments:
            if isinstance(segment, dict):
                by_input.setdefault(int(segment.get("dialogue_input_index") or 0), []).append(segment)
        if set(by_input) != set(range(len(cuts))):
            raise RuntimeError(
                f"Dialogue {group} 턴 분리 정보가 불완전합니다: "
                f"expected={list(range(len(cuts)))}, actual={sorted(by_input)}"
            )

        turn_records = []
        for index, cut in enumerate(cuts):
            spans = by_input[index]
            start = min(_float(item.get("start_time_seconds"), 0.0) for item in spans)
            end = max(_float(item.get("end_time_seconds"), 0.0) for item in spans)
            character_start = min(int(item.get("character_start_index") or 0) for item in spans)
            character_end = max(int(item.get("character_end_index") or 0) for item in spans)
            turn = payload["turn_settings"][index]
            cut_number = int(turn["cut_number"])
            output_path = audio_dir / f"cut_{cut_number:03d}.mp3"
            duration = _render_turn(
                master_path,
                output_path,
                start=start,
                end=end,
                speed=float(turn["speed"]),
                lead=float(turn["lead"]),
                tail=float(turn["tail"]),
            )
            alignment = _slice_alignment(
                response_data.get("alignment"),
                character_start=character_start,
                character_end=character_end,
                segment_start=start,
                speed=float(turn["speed"]),
                lead=float(turn["lead"]),
            )
            write_alignment_sidecar(
                output_path,
                text=_text(cut.get("narration")),
                alignment=alignment,
                normalized_alignment=None,
                provider="elevenlabs-text-to-dialogue",
                model_id=ELEVENLABS_DIALOGUE_MODEL,
            )
            record = {
                "cut_number": cut_number,
                "file": output_path.name,
                "path": f"audio/{output_path.name}",
                "duration": duration,
                "original_duration": max(0.0, end - start),
                "dialogue_group": group,
                "dialogue_input_index": index,
            }
            turn_records.append(record)
            results[cut_number] = record

        _atomic_json(
            manifest_path,
            {
                "version": 1,
                "fingerprint": fingerprint,
                "payload": payload,
                "turns": turn_records,
            },
        )
    return results
