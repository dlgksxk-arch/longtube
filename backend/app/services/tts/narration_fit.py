"""TTS generation wrapper with text-only timing repair.

The audio itself is never sped up, slowed down, stretched, or cut. When the
measured TTS duration misses the target window, this wrapper asks the selected
script LLM to rewrite the narration text, then regenerates TTS with that new
text. The generated audio is always kept so failures remain inspectable.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from app import config as app_config
from app.services.llm.factory import get_llm_service
from app.services.tts.base import _resolve_bins


def _compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _duration_ok(duration: float) -> bool:
    return app_config.TTS_MIN_DURATION <= duration <= app_config.TTS_MAX_DURATION


def _hard_max_duration() -> float:
    try:
        return float(getattr(app_config, "TTS_HARD_MAX_DURATION", 4.8))
    except (TypeError, ValueError):
        return 4.8


def _unit_count(text: str, language: str) -> int:
    if language == "en":
        return len(re.findall(r"\b[\w']+\b", text or ""))
    return len(text or "")


def _unit_label(language: str) -> str:
    return "words" if language == "en" else "chars"


def _target_units_for_duration(text: str, duration: float, language: str) -> int:
    if duration <= 0:
        return _unit_count(text, language)
    target_mid = (app_config.TTS_MIN_DURATION + app_config.TTS_MAX_DURATION) / 2
    return max(1, round(_unit_count(text, language) * target_mid / duration))


def _near_target(text: str, target_units: int, language: str, tolerance: int = 1) -> bool:
    return abs(_unit_count(text, language) - target_units) <= tolerance


def _ko_long_variants(text: str) -> list[str]:
    """Deterministic Korean compression candidates for hard TTS overruns."""
    text = _compact(text)
    variants: list[str] = []

    replacements = [
        ("인간처럼 자연스레", "사람처럼"),
        ("인간처럼 자연스럽게", "사람처럼"),
        ("자연스레 ", ""),
        ("자연스럽게 ", ""),
        ("처음으로 ", ""),
        ("완전히 ", ""),
        ("극적으로 ", ""),
        ("직접 ", ""),
        ("도저히 ", ""),
        ("바로 ", ""),
        ("정말 ", ""),
        ("진짜 ", ""),
        ("다시 ", ""),
        ("그 단어가 바로 ", "그 단어가 "),
        ("입 밖에 나옵니다", "나옵니다"),
        ("글을 쓰기 시작했죠", "글을 썼죠"),
        ("쓰기 시작했죠", "썼죠"),
        ("만들어냅니다", "만듭니다"),
        ("경고하고 있고요", "경고합니다"),
        ("있는 겁니다", "있습니다"),
        ("했다는 사실입니다", "했습니다"),
        ("찾아옵니다", "옵니다"),
    ]

    candidate = text
    for old, new in replacements:
        if old in candidate:
            candidate = _compact(candidate.replace(old, new, 1))
            if candidate and candidate != text:
                variants.append(candidate)

    if "," in text:
        parts = [_compact(part) for part in text.split(",") if _compact(part)]
        if len(parts) >= 2:
            variants.append(_compact(", ".join(parts[:2])))
            variants.append(_compact(" ".join(parts[:2])))

    soft_prefixes = ["그리고 ", "하지만 ", "그런데 ", "근데 ", "결국 ", "이제 "]
    for prefix in soft_prefixes:
        if text.startswith(prefix):
            variants.append(_compact(text[len(prefix):]))
            break

    unique: list[str] = []
    seen = {text}
    for item in variants:
        item = _compact(item)
        if item and item not in seen and len(item) < len(text):
            seen.add(item)
            unique.append(item)
    return unique


def _duration_distance(duration: float) -> float:
    if duration <= 0:
        return 999.0
    hard_max = _hard_max_duration()
    if duration > hard_max:
        return 1000.0 + (duration - hard_max)
    if _duration_ok(duration):
        return 0.0
    if duration < app_config.TTS_MIN_DURATION:
        return app_config.TTS_MIN_DURATION - duration
    return duration - app_config.TTS_MAX_DURATION


def _candidate_audio_path(audio_path: str, attempt: int) -> str:
    path = Path(audio_path)
    suffix = path.suffix or ".mp3"
    return str(path.with_name(f"{path.stem}.fit{attempt:02d}{suffix}"))


def _relative_output_path(audio_path: str) -> str:
    if not os.path.isabs(audio_path):
        return audio_path.replace("\\", "/")
    parts = audio_path.replace("\\", "/").split("/")
    try:
        audio_idx = parts.index("audio")
        return "/".join(parts[audio_idx:])
    except ValueError:
        return os.path.basename(audio_path)


def _atempo_filter(ratio: float) -> str:
    parts: list[str] = []
    value = max(0.5, float(ratio or 1.0))
    while value > 2.0:
        parts.append("atempo=2.0")
        value /= 2.0
    while value < 0.5:
        parts.append("atempo=0.5")
        value /= 0.5
    parts.append(f"atempo={value:.6f}")
    return ",".join(parts)


def _probe_audio_duration(path: str) -> float:
    try:
        _, ffprobe = _resolve_bins()
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        return float((result.stdout or "").strip() or 0.0)
    except Exception:
        return 0.0


def _fit_audio_duration_in_place(path: str, current_duration: float, log=None) -> float:
    """Local, no-credit duration guard for generated narration audio."""
    if current_duration <= 0:
        return current_duration

    target: float | None = None
    audio_filter: str | None = None
    output_args: list[str] = []

    if current_duration > app_config.TTS_MAX_DURATION:
        target = float(app_config.TTS_MAX_DURATION)
        audio_filter = _atempo_filter(current_duration / target)
    elif current_duration < app_config.TTS_MIN_DURATION:
        target = float(app_config.TTS_MIN_DURATION)
        pad = max(0.0, target - current_duration)
        audio_filter = f"apad=pad_dur={pad:.3f}"
        output_args = ["-t", f"{target:.3f}"]

    if target is None or not audio_filter:
        return current_duration

    tmp = str(Path(path).with_name(f"{Path(path).stem}.durationfit{Path(path).suffix or '.mp3'}"))
    try:
        ffmpeg, _ = _resolve_bins()
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            path,
            "-filter:a",
            audio_filter,
            *output_args,
            "-vn",
            tmp,
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
            check=False,
        )
        if proc.returncode != 0 or not os.path.exists(tmp) or os.path.getsize(tmp) <= 100:
            if log:
                log(f"local duration fit failed: {proc.stderr[-300:] if proc.stderr else proc.returncode}")
            return current_duration
        os.replace(tmp, path)
        measured = _probe_audio_duration(path) or target
        if log:
            log(f"local duration fit: {current_duration:.2f}s -> {measured:.2f}s")
        return measured
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _length_fallback(text: str, direction: str, target_chars: int, language: str) -> str:
    text = _compact(text)
    if language != "ko":
        return text

    candidates: list[str] = []
    if direction == "short":
        # Do not pad short narration with generic filler. If the LLM cannot add
        # meaningful content, keep the generated audio inspectable instead of
        # damaging the script with repeated tag-on phrases.
        return text
    else:
        removals = [
            "여러분은 ",
            "단 ",
            "작은 ",
            "진짜 ",
            "정말 ",
            "바로 ",
            "과연 ",
            "모든 것의 ",
            "이제 ",
            "그렇죠.",
            "맞죠.",
            "정말로요.",
            "여기서부터죠.",
            "이제 시작이죠.",
            "그게 핵심입니다.",
        ]
        for token in removals:
            if token in text:
                candidates.append(_compact(text.replace(token, "", 1)))
        candidates.extend(_ko_long_variants(text))

    viable = [
        item
        for item in candidates
        if item
        and item != text
        and ((direction == "short" and len(item) > len(text)) or (direction == "long" and len(item) < len(text)))
    ]
    if not viable:
        return text
    return min(viable, key=lambda item: (abs(len(item) - target_chars), abs(len(item) - len(text))))


def _neighbor_narration(script: dict | None, cut_number: int, offset: int) -> str:
    cuts = (script or {}).get("cuts", []) if isinstance(script, dict) else []
    target = cut_number + offset
    for cut in cuts:
        try:
            if int(cut.get("cut_number")) == target:
                return _compact(cut.get("narration") or "")
        except Exception:
            continue
    return ""


async def generate_tts_with_auto_narration_fit(
    tts_service: Any,
    narration: str,
    voice_id: str,
    audio_path: str,
    *,
    speed: float,
    voice_settings: Optional[dict] = None,
    config: dict | None = None,
    topic: str = "",
    language: str = "ko",
    cut_number: int = 0,
    total_cuts: int = 0,
    cut_data: dict | None = None,
    script: dict | None = None,
    same_text_attempts: int = 1,
    max_rewrites: int = 0,
    log=None,
) -> dict:
    """Generate TTS, repairing narration text only when measured timing misses."""
    original = _compact(narration)
    current = original
    rewrite_count = 0
    result: dict | None = None
    best: dict | None = None
    temp_paths: list[str] = []
    try:
        configured_max_rewrites = int((config or {}).get("tts_timing_max_rewrites", max_rewrites))
    except (TypeError, ValueError):
        configured_max_rewrites = max_rewrites
    configured_max_rewrites = 0

    for attempt in range(configured_max_rewrites + 1):
        candidate_path = _candidate_audio_path(audio_path, attempt)
        temp_paths.append(candidate_path)
        result = await tts_service.generate(
            current,
            voice_id,
            candidate_path,
            speed=speed,
            voice_settings=voice_settings,
        )
        duration = float(result.get("duration") or 0.0)
        candidate = {
            "path": candidate_path,
            "duration": duration,
            "narration": current,
            "result": dict(result),
            "attempt": attempt,
        }
        if best is None or _duration_distance(duration) < _duration_distance(float(best.get("duration") or 0.0)):
            best = candidate
        if _duration_ok(duration) or attempt >= configured_max_rewrites:
            break

        if config and config.get("tts_auto_timing_fit") is False:
            break

        direction = "short" if duration < app_config.TTS_MIN_DURATION else "long"
        target_units = _target_units_for_duration(current, duration, language)
        if duration > _hard_max_duration():
            # Hard ceiling breach: push the rewrite shorter than the normal
            # target midpoint so the next measured candidate cannot slip past
            # 4.8s again.
            target_mid = (app_config.TTS_MIN_DURATION + app_config.TTS_MAX_DURATION) / 2
            target_units = max(
                1,
                min(
                    target_units,
                    round(_unit_count(current, language) * target_mid / duration),
                ),
            )

        try:
            script_model = (config or {}).get("script_model") or "claude-sonnet-4-6"
            llm_service = get_llm_service(script_model)
            rewritten = await llm_service.rewrite_narration_for_timing(
                topic=topic,
                narration=current,
                language=language,
                cut_number=cut_number,
                total_cuts=total_cuts,
                measured_duration=duration,
                target_min=app_config.TTS_MIN_DURATION,
                target_max=app_config.TTS_MAX_DURATION,
                direction=direction,
                target_chars=target_units,
                image_prompt=(cut_data or {}).get("image_prompt") or "",
                scene_type=(cut_data or {}).get("scene_type") or "",
                previous_narration=_neighbor_narration(script, cut_number, -1),
                next_narration=_neighbor_narration(script, cut_number, 1),
            )
        except Exception as exc:
            if log:
                log(f"timing rewrite skipped cut {cut_number}: {exc}")
            break

        rewritten = _compact(rewritten)
        fallback = _length_fallback(current, direction, target_units, language)
        if not rewritten or rewritten == current:
            rewritten = fallback

        # Reject rewrites that move in the wrong direction.
        current_units = _unit_count(current, language)
        rewritten_units = _unit_count(rewritten, language)
        if direction == "long" and rewritten_units >= current_units:
            rewritten = fallback
        if direction == "short" and rewritten_units <= current_units:
            rewritten = fallback
        # Measured TTS timing is more important than an exact character count.
        # Allow a wider text target so useful LLM rewrites are actually tested.
        if not _near_target(rewritten, target_units, language, tolerance=4):
            rewritten = fallback
        if not rewritten or rewritten == current:
            if log:
                log(f"timing rewrite unavailable cut {cut_number}; keeping generated audio")
            break

        rewrite_count += 1
        if log:
            log(
                f"timing rewrite cut {cut_number} attempt {attempt + 1}: "
                f"{duration:.2f}s -> target {app_config.TTS_MIN_DURATION:.1f}~{app_config.TTS_MAX_DURATION:.1f}s, "
                f"{current_units}->{_unit_count(rewritten, language)} {_unit_label(language)}"
            )
        current = rewritten

    chosen = best
    if chosen is None:
        raise RuntimeError("TTS generation did not produce a result")

    chosen_path = str(chosen.get("path") or audio_path)
    final_result = dict(chosen.get("result") or {})
    final_narration = str(chosen.get("narration") or current)
    final_duration = float(chosen.get("duration") or final_result.get("duration") or 0.0)
    hard_max = _hard_max_duration()
    if final_duration > hard_max or final_duration < app_config.TTS_MIN_DURATION:
        final_duration = _fit_audio_duration_in_place(chosen_path, final_duration, log=log)
    if chosen_path != audio_path:
        shutil.copyfile(chosen_path, audio_path)
    for path in temp_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    final_result["path"] = _relative_output_path(audio_path)
    final_result["duration"] = final_duration
    final_result["narration"] = final_narration
    final_result["narration_changed"] = final_narration != original
    final_result["rewrite_count"] = rewrite_count
    final_result["timing_ok"] = _duration_ok(final_duration)
    final_result["timing_distance"] = round(_duration_distance(final_duration), 3)
    if log and not _duration_ok(final_duration):
        log(
            f"timing best-effort cut {cut_number}: {final_duration:.2f}s "
            f"(target {app_config.TTS_MIN_DURATION:.1f}~{app_config.TTS_MAX_DURATION:.1f}s), "
            f"{len(final_narration)} chars"
        )
    return final_result
