"""TTS generation wrapper with optional local duration fitting.

V3.2 keeps generated cut audio at its measured TTS duration by default. Legacy
fixed-slot fitting is still available with ``tts_audio_timing_fit=True``.
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


def _duration_ok(duration: float, config: dict | None = None) -> bool:
    min_sec, max_sec, _ = app_config.resolve_tts_timing_window(config)
    return min_sec <= duration <= min(max_sec, _hard_max_duration(config))


def _duration_status(duration: float, config: dict | None = None) -> str:
    """Classify measured spoken TTS against the configured narration target."""
    if duration <= 0:
        return "unknown"
    min_sec, max_sec, target = app_config.resolve_tts_timing_window(config)
    hard_max = _hard_max_duration(config)
    if duration > hard_max:
        return "too_long"
    if duration > max_sec + 0.02:
        return "long"
    if duration < min_sec - 0.02:
        return "short"
    if abs(duration - target) <= 0.02:
        return "target_fit"
    return "window_fit"


def _hard_max_duration(config: dict | None = None) -> float:
    try:
        return float(app_config.resolve_tts_hard_max_duration(config))
    except (TypeError, ValueError):
        return 4.8


def _final_cut_audio_duration(config: dict | None = None) -> float:
    try:
        return float(app_config.resolve_cut_video_duration(config))
    except (TypeError, ValueError):
        return 4.0


def _unit_count(text: str, language: str) -> int:
    return len(text or "")


def _unit_label(language: str) -> str:
    return "chars"


def _target_units_for_duration(text: str, duration: float, language: str, config: dict | None = None) -> int:
    if duration <= 0:
        return _unit_count(text, language)
    _, _, target_mid = app_config.resolve_tts_timing_window(config)
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


def _duration_distance(duration: float, config: dict | None = None) -> float:
    if duration <= 0:
        return 999.0
    min_sec, max_sec, target = app_config.resolve_tts_timing_window(config)
    hard_max = _hard_max_duration(config)
    if duration > hard_max:
        return 1000.0 + (duration - hard_max)
    if _duration_ok(duration, config):
        return abs(duration - target)
    if duration < min_sec:
        return min_sec - duration
    return duration - max_sec


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
        pass
    try:
        ffmpeg, _ = _resolve_bins()
        result = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", path, "-f", "null", "-"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
            check=False,
        )
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", (result.stderr or "") + (result.stdout or ""))
        if match:
            hours, minutes, seconds = match.groups()
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        pass
    return 0.0


def _fit_audio_duration_in_place(path: str, current_duration: float, config: dict | None = None, log=None) -> float:
    """Fit audio to the fixed cut slot without spending API credits.

    Spoken narration may target a longer configured narration window, but the
    saved audio file itself must still match the fixed video cut duration so
    muxing and subtitles stay aligned.
    """
    if current_duration <= 0:
        return current_duration

    final_target = _final_cut_audio_duration(config)
    if abs(current_duration - final_target) <= 0.02:
        return current_duration

    audio_filter: str | None = None
    output_args: list[str] = ["-t", f"{final_target:.3f}"]

    if current_duration > final_target:
        audio_filter = _atempo_filter(current_duration / final_target)
    else:
        pad = max(0.0, final_target - current_duration)
        audio_filter = f"apad=pad_dur={pad:.3f}"

    if not audio_filter:
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
        measured = _probe_audio_duration(path) or final_target
        if log:
            log(f"local duration fit: {current_duration:.2f}s -> {measured:.2f}s")
        return measured
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def ensure_audio_duration_window(path: str, current_duration: float, config: dict | None = None, log=None) -> float:
    """Final no-credit guard before saving a cut audio file.

    Returns the saved file duration. V3.2 keeps generated TTS at its natural
    duration by default; legacy fixed-slot fitting remains available through
    ``tts_audio_timing_fit=True``.
    """
    if not app_config.should_fit_tts_audio_to_cut(config):
        return current_duration
    final_target = _final_cut_audio_duration(config)
    if abs(current_duration - final_target) <= 0.02:
        return current_duration
    fitted = _fit_audio_duration_in_place(path, current_duration, config=config, log=log)
    if abs(fitted - final_target) > 0.03:
        fitted = _fit_audio_duration_in_place(path, fitted, config=config, log=log)
    return fitted


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
    original_duration = 0.0
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
        if attempt == 0:
            original_duration = duration
        candidate = {
            "path": candidate_path,
            "duration": duration,
            "narration": current,
            "result": dict(result),
            "attempt": attempt,
        }
        if best is None or _duration_distance(duration, config) < _duration_distance(float(best.get("duration") or 0.0), config):
            best = candidate
        if _duration_ok(duration, config) or attempt >= configured_max_rewrites:
            break

        if config and config.get("tts_auto_timing_fit") is False:
            break

        min_sec, max_sec, target_mid = app_config.resolve_tts_timing_window(config)
        direction = "short" if duration < min_sec else "long"
        target_units = _target_units_for_duration(current, duration, language, config)
        if duration > _hard_max_duration(config):
            # Hard ceiling breach: push the rewrite shorter than the normal
            # target midpoint so the next measured candidate cannot slip past
            # the configured hard ceiling again.
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
                target_min=min_sec,
                target_max=max_sec,
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
                f"{duration:.2f}s -> target {min_sec:.1f}~{max_sec:.1f}s, "
                f"{current_units}->{_unit_count(rewritten, language)} {_unit_label(language)}"
            )
        current = rewritten

    chosen = best
    if chosen is None:
        raise RuntimeError("TTS generation did not produce a result")

    chosen_path = str(chosen.get("path") or audio_path)
    final_result = dict(chosen.get("result") or {})
    final_narration = str(chosen.get("narration") or current)
    spoken_duration = float(chosen.get("duration") or final_result.get("duration") or 0.0)
    final_duration = ensure_audio_duration_window(chosen_path, spoken_duration, config=config, log=log)
    fitted_spoken_duration = spoken_duration
    _, max_sec, _ = app_config.resolve_tts_timing_window(config)
    if spoken_duration > min(max_sec, _hard_max_duration(config)):
        fitted_spoken_duration = min(max_sec, _hard_max_duration(config))
    if chosen_path != audio_path:
        shutil.copyfile(chosen_path, audio_path)
    for path in temp_paths:
        try:
            os.remove(path)
        except OSError:
            pass
    final_result["path"] = _relative_output_path(audio_path)
    final_result["original_duration"] = original_duration or final_duration
    final_result["spoken_duration"] = fitted_spoken_duration
    final_result["duration"] = final_duration
    final_result["adjusted_duration"] = final_duration
    final_result["narration"] = final_narration
    final_result["narration_changed"] = final_narration != original
    final_result["rewrite_count"] = rewrite_count
    final_result["timing_ok"] = _duration_ok(fitted_spoken_duration, config)
    final_result["timing_status"] = _duration_status(spoken_duration, config)
    final_result["duration_was_long"] = final_result["timing_status"] in {"long", "too_long"}
    final_result["duration_was_too_long"] = final_result["timing_status"] == "too_long"
    final_result["timing_distance"] = round(_duration_distance(fitted_spoken_duration, config), 3)
    if log and not _duration_ok(fitted_spoken_duration, config):
        min_sec, max_sec, _ = app_config.resolve_tts_timing_window(config)
        log(
            f"timing best-effort cut {cut_number}: spoken {fitted_spoken_duration:.2f}s, file {final_duration:.2f}s "
            f"(target {min_sec:.1f}~{max_sec:.1f}s), "
            f"{len(final_narration)} chars"
        )
    return final_result
