"""Shorts candidate selection and rendering helpers."""
from __future__ import annotations

import asyncio
import json
import hashlib
import os
import re
import tempfile
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from app.config import BGM_VOLUME_MULTIPLIER, CUT_VIDEO_DURATION, NARRATION_VOLUME_GAIN
from app.services.remotion_shorts_renderer import (
    SHARED_SHORTS_PIPELINE_ID,
    render_remotion_shorts,
)
from app.services.tts.alignment import alignment_sidecar_path
from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess


HOOK_RE = re.compile(
    r"(why|how|secret|hidden|truth|shocking|strange|but|however|suddenly|"
    r"왜|어떻게|비밀|숨겨|진실|충격|이상|그런데|하지만|사실|알고보니|반전|"
    r"なぜ|どうして|秘密|真実|衝撃|しかし|実は)",
    re.IGNORECASE,
)


def load_script(project_dir: Path) -> dict[str, Any]:
    script_path = project_dir / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _cut_score(cut: dict[str, Any], index: int, total: int) -> int:
    text = " ".join(
        str(cut.get(k) or "")
        for k in ("narration", "scene_type", "image_prompt", "shorts_reason")
    )
    score = 0
    try:
        score += max(0, min(10, int(cut.get("shorts_score") or 0))) * 2
    except (TypeError, ValueError):
        pass
    if HOOK_RE.search(text):
        score += 5
    if cut.get("shorts_candidate") is True:
        score += 8
    if str(cut.get("scene_type") or "").lower() in {"reversal", "reveal", "transition", "title"}:
        score += 2
    if 1 < index < max(2, total - 1):
        score += 1
    return score


SHORTS_SEGMENT_COUNT = 4
SHORTS_MIN_SEGMENT_COUNT = 3
SHORTS_CUT_COUNT = 15
SHORTS_EXPLICIT_MARKED_MIN_CUT_COUNT = 10
SHORTS_TOTAL_CANDIDATE_CUT_COUNT = SHORTS_SEGMENT_COUNT * SHORTS_CUT_COUNT
SHORTS_MIN_CANDIDATE_CUT_COUNT = SHORTS_MIN_SEGMENT_COUNT * SHORTS_CUT_COUNT
SHORTS_GROUP_PURPOSES = {
    1: "논쟁 질문",
    2: "충격 사실",
    3: "롱폼으로 넘기는 미스터리",
    4: "주요 인물 부각",
}
SHORTS_EXCLUDE_EDGE_CUTS = 5
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_CLIP_HEIGHT = 840
SHORTS_VIDEO_CRF = "16"
SHORTS_VIDEO_PRESET = "medium"
SHORTS_TEXT_SIZE = 104
SHORTS_TEXT_BORDER = 9
SHORTS_TITLE_ACCENT_COLOR = "0xffd24a"
SHORTS_CHANNEL_TEXT_SIZE = 92
SHORTS_CHANNEL_TEXT_BORDER = 5
SHORTS_CHANNEL_Y = 1502
SHORTS_CHANNEL_AVATAR_Y = 1490
SHORTS_CHANNEL_AVATAR_X = 318
SHORTS_CHANNEL_TEXT_X = 426
SHORTS_CHANNEL_AVATAR_SIZE = 112
SHORTS_CHANNEL_GAP = 30
SHORTS_CAPTION_Y = 1279
SHORTS_CAPTION_BOX_Y = 1279
SHORTS_CAPTION_BOX_HEIGHT = 190
SHORTS_CAPTION_TEXT_SIZE = 76
SHORTS_CAPTION_TEXT_BORDER = 7
SHORTS_CAPTION_WRAP_WIDTH = 18
SHORTS_SOURCE_PLAYBACK_SPEED = 1.0
SHORTS_PLAYBACK_SPEED = 1.2
SHORTS_SILENCE_THRESHOLD_DB = -42
SHORTS_SILENCE_MIN_DURATION = 0.35
SHORTS_SILENCE_EDGE_PADDING = 0.08
SHORTS_CLOSURE_LOOKAHEAD_CUTS = 6
_JA_TERMINAL_RE = re.compile(r"[。！？!?][\s\"'」』）)]*$")
_JA_DANGLING_END_RE = re.compile(r"(?:しかし|だが|ところが|けれども?|ものの|そして|すると)[、。…！？!?]*$")
_JA_TRANSITION_OPEN_RE = re.compile(r"^(?:しかし|だが|ところが|けれども|すると|そのとき|一方で)")
_JA_STRONG_CLOSURE_RE = re.compile(
    r"(?:でした|ました|なのです|のです|だった|である|となります|になります|といえます|といえる|ません)"
    r"[。！？!?][\s\"'」』）)]*$"
)
_JA_UNPUNCTUATED_FINITE_CLOSURE_RE = re.compile(
    r"(?:です|ます|でした|ました|なのです|のです|だった|である|"
    r"となります|になります|といえます|といえる|ません)"
    r"[\s\"'」』）)]*$"
)


def _silence_keep_segments(
    duration: float,
    silence_ranges: list[tuple[float, float]],
) -> list[dict[str, float]]:
    duration = max(0.0, float(duration or 0.0))
    if duration <= 0:
        return []

    removed: list[tuple[float, float]] = []
    padding = float(SHORTS_SILENCE_EDGE_PADDING)
    for raw_start, raw_end in silence_ranges:
        start = max(0.0, min(duration, float(raw_start)))
        end = max(start, min(duration, float(raw_end)))
        remove_start = min(end, start + padding)
        remove_end = max(remove_start, end - padding)
        if remove_end - remove_start >= 0.05:
            removed.append((remove_start, remove_end))

    if not removed:
        return [{"start": 0.0, "end": duration}]

    removed.sort()
    keep: list[dict[str, float]] = []
    cursor = 0.0
    for start, end in removed:
        if start > cursor + 0.01:
            keep.append({"start": cursor, "end": start})
        cursor = max(cursor, end)
    if cursor < duration - 0.01:
        keep.append({"start": cursor, "end": duration})
    return keep or [{"start": 0.0, "end": duration}]


async def _detect_silence_keep_segments(
    ffmpeg: str,
    source_path: Path,
    duration: float,
) -> list[dict[str, float]]:
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-i", str(source_path),
        "-af",
        (
            f"silencedetect=noise={SHORTS_SILENCE_THRESHOLD_DB}dB:"
            f"d={SHORTS_SILENCE_MIN_DURATION:.3f}"
        ),
        "-f", "null", "-",
    ]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=300.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0:
        error = (stderr or b"").decode(errors="replace")[-500:]
        raise RuntimeError(f"shorts silence detection failed: {error}")

    events = re.findall(
        r"silence_(start|end):\s*([0-9]+(?:\.[0-9]+)?)",
        (stderr or b"").decode(errors="replace"),
    )
    silence_ranges: list[tuple[float, float]] = []
    current_start: float | None = None
    for kind, raw_value in events:
        value = float(raw_value)
        if kind == "start":
            current_start = value
        elif current_start is not None:
            silence_ranges.append((current_start, value))
            current_start = None
    if current_start is not None:
        silence_ranges.append((current_start, float(duration)))
    return _silence_keep_segments(duration, silence_ranges)


async def _validate_rendered_video(ffmpeg: str, path: Path, label: str, *, timeout: float = 180.0) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} output is missing or empty: {path}")
    cmd = [
        ffmpeg,
        "-v", "error",
        "-i", str(path),
        "-map", "0:v:0",
        "-map", "0:a?",
        "-f", "null",
        "-",
    ]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=timeout,
        capture_stdout=False,
        capture_stderr=True,
    )
    err_text = (stderr or b"").decode(errors="replace")
    if rc != 0:
        err = err_text[-800:]
        raise RuntimeError(f"{label} validation failed: {err}")


async def _validate_rendered_audio(ffmpeg: str, path: Path, label: str, *, timeout: float = 180.0) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        raise RuntimeError(f"{label} output is missing or empty: {path}")
    cmd = [
        ffmpeg,
        "-v", "error",
        "-i", str(path),
        "-map", "0:a:0",
        "-f", "null",
        "-",
    ]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=timeout,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0:
        err = (stderr or b"").decode(errors="replace")[-800:]
        raise RuntimeError(f"{label} validation failed: {err}")


def _temp_render_path(final_path: Path) -> Path:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{final_path.stem}.",
        suffix=final_path.suffix,
        dir=final_path.parent,
        delete=False,
    )
    try:
        return Path(handle.name)
    finally:
        handle.close()


def _discard_temp_render(path: Path | None) -> None:
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _cut_duration(cut: dict[str, Any]) -> float:
    for key in ("audio_duration", "actual_duration", "duration_estimate"):
        try:
            value = float(cut.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return float(CUT_VIDEO_DURATION)


def _eligible_shorts_bounds(total: int) -> tuple[int, int] | None:
    first = SHORTS_EXCLUDE_EDGE_CUTS + 1
    last = total - SHORTS_EXCLUDE_EDGE_CUTS
    if first > last:
        return None
    return first, last


def _expand_segment(
    start: int,
    end: int,
    total: int,
    *,
    target: int = SHORTS_CUT_COUNT,
    min_start: int = 1,
    max_end: int | None = None,
) -> tuple[int, int]:
    """Expand a selected hook area to a fixed shorts length when possible."""
    max_end = total if max_end is None else min(max_end, total)
    start = max(min_start, min(start, max_end))
    end = max(start, min(end, max_end))
    while end - start + 1 < target and (start > min_start or end < max_end):
        if end < max_end:
            end += 1
        if end - start + 1 >= target:
            break
        if start > min_start:
            start -= 1
    return start, end


def _japanese_shorts_end_is_closed(text: str) -> bool:
    narration = _compact_text(text)
    if not narration:
        return False
    has_terminal = bool(_JA_TERMINAL_RE.search(narration))
    has_unpunctuated_finite_closure = bool(
        _JA_UNPUNCTUATED_FINITE_CLOSURE_RE.search(narration)
    )
    if not has_terminal and not has_unpunctuated_finite_closure:
        return False
    if _JA_DANGLING_END_RE.search(narration):
        return False
    if (
        _JA_TRANSITION_OPEN_RE.search(narration)
        and not _JA_STRONG_CLOSURE_RE.search(narration)
        and not has_unpunctuated_finite_closure
    ):
        return False
    return True


def _adjust_japanese_window_to_closure(
    script: dict[str, Any],
    cuts: list[dict[str, Any]],
    start: int,
    end: int,
    *,
    min_start: int,
    max_end: int,
    blocked: set[int] | None = None,
) -> tuple[int, int] | None:
    if _detect_language(script) != "ja":
        return start, end
    by_number = {
        int(cut.get("cut_number")): cut
        for cut in cuts
        if str(cut.get("cut_number") or "").isdigit()
    }
    target = max(1, end - start + 1)
    candidates = [end]
    candidates.extend(range(end + 1, min(max_end, end + SHORTS_CLOSURE_LOOKAHEAD_CUTS) + 1))
    candidates.extend(range(end - 1, max(min_start + target - 2, end - SHORTS_CLOSURE_LOOKAHEAD_CUTS) - 1, -1))
    for candidate_end in candidates:
        candidate_start = candidate_end - target + 1
        if candidate_start < min_start or candidate_end > max_end:
            continue
        nums = set(range(candidate_start, candidate_end + 1))
        if blocked and nums.intersection(blocked):
            continue
        if any(number not in by_number for number in nums):
            continue
        if _japanese_shorts_end_is_closed(by_number[candidate_end].get("narration") or ""):
            return candidate_start, candidate_end
    return None


def _repair_japanese_marked_shorts_closure(
    script: dict[str, Any],
    cuts: list[dict[str, Any]],
    *,
    count: int,
) -> None:
    if _detect_language(script) != "ja":
        return
    bounds = _eligible_shorts_bounds(len(cuts))
    if not bounds:
        return
    eligible_first, eligible_last = bounds
    by_number = {
        int(cut.get("cut_number")): cut
        for cut in cuts
        if str(cut.get("cut_number") or "").isdigit()
    }
    for group in range(1, count + 1):
        group_cuts = sorted(
            (
                cut for cut in cuts
                if cut.get("shorts_candidate") is True and int(cut.get("shorts_group") or 0) == group
            ),
            key=lambda cut: int(cut.get("cut_number") or 0),
        )
        if len(group_cuts) < SHORTS_EXPLICIT_MARKED_MIN_CUT_COUNT:
            continue
        selected = group_cuts[:SHORTS_CUT_COUNT]
        nums = [int(cut.get("cut_number") or 0) for cut in selected]
        if not nums or nums != list(range(nums[0], nums[-1] + 1)):
            continue
        if _japanese_shorts_end_is_closed(selected[-1].get("narration") or ""):
            continue
        other_groups = {
            int(cut.get("cut_number") or 0)
            for cut in cuts
            if cut.get("shorts_candidate") is True
            and int(cut.get("shorts_group") or 0) not in {0, group}
        }
        adjusted = _adjust_japanese_window_to_closure(
            script,
            cuts,
            nums[0],
            nums[-1],
            min_start=eligible_first,
            max_end=eligible_last,
            blocked=other_groups,
        )
        reason = str(selected[0].get("shorts_reason") or SHORTS_GROUP_PURPOSES.get(group) or "")
        title = str(selected[0].get("shorts_title") or "")
        for cut in group_cuts:
            cut["shorts_candidate"] = False
            cut["shorts_group"] = 0
        if adjusted is None:
            continue
        adjusted_start, adjusted_end = adjusted
        for number in range(adjusted_start, adjusted_end + 1):
            cut = by_number[number]
            cut["shorts_candidate"] = True
            cut["shorts_group"] = group
            cut["shorts_reason"] = reason
            cut["shorts_score"] = max(int(cut.get("shorts_score") or 0), 7)
            if title and number == adjusted_start:
                cut["shorts_title"] = title


def select_shorts_segments(
    script: dict[str, Any],
    *,
    count: int = SHORTS_SEGMENT_COUNT,
    min_count: int = SHORTS_MIN_SEGMENT_COUNT,
) -> list[dict[str, Any]]:
    """Return shorts segments using script-marked cuts first."""
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    if not cuts:
        return []
    bounds = _eligible_shorts_bounds(len(cuts))
    if not bounds:
        return []
    eligible_first, eligible_last = bounds
    _repair_japanese_marked_shorts_closure(script, cuts, count=count)

    marked: list[tuple[int, int, dict[str, Any]]] = []
    by_group: dict[int, list[dict[str, Any]]] = {}
    for cut in cuts:
        try:
            group = int(cut.get("shorts_group") or 0)
        except (TypeError, ValueError):
            group = 0
        try:
            cut_num = int(cut.get("cut_number") or 0)
        except (TypeError, ValueError):
            cut_num = 0
        if cut.get("shorts_candidate") is True and group > 0 and cut_num > 0:
            by_group.setdefault(group, []).append(cut)
            marked.append((cut_num, _cut_score(cut, cut_num, len(cuts)), cut))

    segments: list[dict[str, Any]] = []
    used: set[int] = set()
    explicit_groups = [
        group for group in sorted(by_group)
        if 1 <= group <= count and len(by_group[group]) >= SHORTS_EXPLICIT_MARKED_MIN_CUT_COUNT
    ]
    if len(explicit_groups) >= min_count:
        for group in explicit_groups[:count]:
            nums = sorted(
                int(c["cut_number"])
                for c in by_group[group]
                if c.get("cut_number")
            )[:SHORTS_CUT_COUNT]
            span = set(nums)
            if not nums or used.intersection(span):
                continue
            used.update(span)
            first_cut = sorted(by_group[group], key=lambda c: int(c.get("cut_number") or 0))[0]
            segments.append({
                "group": group,
                "start_cut": nums[0],
                "end_cut": nums[-1],
                "cut_numbers": nums,
                "reason": first_cut.get("shorts_reason") or SHORTS_GROUP_PURPOSES.get(group) or "script-marked shorts cuts",
                "title": first_cut.get("shorts_title") or first_cut.get("headline") or "",
                "purpose": SHORTS_GROUP_PURPOSES.get(group) or "",
            })
        if len(segments) >= min_count:
            return segments

    for group in sorted(by_group):
        group_cuts = sorted(
            by_group[group],
            key=lambda c: (
                -_cut_score(c, int(c.get("cut_number") or 0), len(cuts)),
                int(c.get("cut_number") or 0),
            ),
        )
        nums = sorted(
            int(c["cut_number"])
            for c in group_cuts[:SHORTS_CUT_COUNT]
            if c.get("cut_number")
        )
        if len(nums) < SHORTS_CUT_COUNT:
            continue
        span = set(nums)
        if used.intersection(span):
            continue
        used.update(span)
        first_cut = by_group[group][0]
        segments.append({
            "group": group,
            "start_cut": nums[0],
            "end_cut": nums[-1],
            "cut_numbers": nums,
            "reason": first_cut.get("shorts_reason") or SHORTS_GROUP_PURPOSES.get(group) or "script-marked shorts cuts",
            "title": first_cut.get("shorts_title") or first_cut.get("headline") or "",
            "purpose": SHORTS_GROUP_PURPOSES.get(group) or "",
        })
        if len(segments) >= count:
            return segments
    if len(segments) >= max(1, min(count, min_count)):
        return segments

    ranked = sorted(
        (
            (i + 1, _cut_score(c, i + 1, len(cuts)))
            for i, c in enumerate(cuts)
            if eligible_first <= i + 1 <= eligible_last
        ),
        key=lambda item: item[1],
        reverse=True,
    )
    for cut_num, _score in ranked:
        if cut_num in used:
            continue
        start = max(eligible_first, cut_num - 2)
        end = min(eligible_last, start + SHORTS_CUT_COUNT - 1)
        start, end = _expand_segment(start, end, len(cuts), min_start=eligible_first, max_end=eligible_last)
        adjusted = _adjust_japanese_window_to_closure(
            script,
            cuts,
            start,
            end,
            min_start=eligible_first,
            max_end=eligible_last,
            blocked=used,
        )
        if adjusted is None:
            continue
        start, end = adjusted
        span = set(range(start, end + 1))
        if used.intersection(span):
            continue
        used.update(span)
        segments.append({
            "group": len(segments) + 1,
            "start_cut": start,
            "end_cut": end,
            "cut_numbers": list(range(start, end + 1)),
            "reason": SHORTS_GROUP_PURPOSES.get(len(segments) + 1) or "auto-selected hook/reveal segment",
            "purpose": SHORTS_GROUP_PURPOSES.get(len(segments) + 1) or "",
        })
        if len(segments) >= count:
            break
    eligible_count = eligible_last - eligible_first + 1
    if len(segments) < count and eligible_count >= SHORTS_CUT_COUNT:
        # Last-resort deterministic diversity: pick a non-overlapping window
        # from the opposite side of the episode so #1/#2 cannot become clones.
        last_start = eligible_last - SHORTS_CUT_COUNT + 1
        middle_start = max(
            eligible_first,
            min(last_start, (eligible_first + eligible_last) // 2 - SHORTS_CUT_COUNT // 2),
        )
        for start in (eligible_first, last_start, middle_start):
            end = min(eligible_last, start + SHORTS_CUT_COUNT - 1)
            adjusted = _adjust_japanese_window_to_closure(
                script,
                cuts,
                start,
                end,
                min_start=eligible_first,
                max_end=eligible_last,
                blocked=used,
            )
            if adjusted is None:
                continue
            start, end = adjusted
            span = set(range(start, end + 1))
            if used.intersection(span):
                continue
            used.update(span)
            segments.append({
                "group": len(segments) + 1,
                "start_cut": start,
                "end_cut": end,
                "cut_numbers": list(range(start, end + 1)),
                "reason": SHORTS_GROUP_PURPOSES.get(len(segments) + 1) or "auto-selected distinct fallback segment",
                "purpose": SHORTS_GROUP_PURPOSES.get(len(segments) + 1) or "",
            })
            if len(segments) >= count:
                break
    return segments


def annotate_script_shorts(
    script: dict[str, Any],
    *,
    count: int = SHORTS_SEGMENT_COUNT,
    min_count: int = SHORTS_MIN_SEGMENT_COUNT,
) -> dict[str, Any]:
    """Ensure script cuts contain deterministic shorts metadata."""
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    for cut in cuts:
        cut["shorts_candidate"] = bool(cut.get("shorts_candidate", False))
        try:
            cut["shorts_group"] = int(cut.get("shorts_group") or 0)
        except (TypeError, ValueError):
            cut["shorts_group"] = 0
        cut["shorts_reason"] = str(cut.get("shorts_reason") or "")
        try:
            cut["shorts_score"] = max(0, min(10, int(cut.get("shorts_score") or 0)))
        except (TypeError, ValueError):
            cut["shorts_score"] = 0

    _repair_japanese_marked_shorts_closure(script, cuts, count=count)

    existing_marked = [
        c for c in cuts
        if c.get("shorts_candidate") is True and int(c.get("shorts_group") or 0) > 0
    ]
    group_counts = {
        group: sum(1 for cut in existing_marked if int(cut.get("shorts_group") or 0) == group)
        for group in range(1, SHORTS_SEGMENT_COUNT + 1)
    }
    explicit_groups = [
        group for group in range(1, SHORTS_SEGMENT_COUNT + 1)
        if group_counts[group] >= SHORTS_EXPLICIT_MARKED_MIN_CUT_COUNT
    ]
    if len(explicit_groups) >= min_count:
        keep_groups = set(explicit_groups[:count])
        for cut in cuts:
            group = int(cut.get("shorts_group") or 0)
            if cut.get("shorts_candidate") is True and group in keep_groups:
                cut["shorts_group"] = group
                cut["shorts_score"] = max(int(cut.get("shorts_score") or 0), 7)
                if not cut.get("shorts_reason"):
                    cut["shorts_reason"] = SHORTS_GROUP_PURPOSES.get(group) or "script-marked shorts cuts"
            else:
                cut["shorts_candidate"] = False
                cut["shorts_group"] = 0
        return script

    if all(group_counts[group] >= SHORTS_CUT_COUNT for group in range(1, SHORTS_SEGMENT_COUNT + 1)):
        keep: set[int] = set()
        for group in range(1, SHORTS_SEGMENT_COUNT + 1):
            group_ranked = sorted(
                (cut for cut in existing_marked if int(cut.get("shorts_group") or 0) == group),
                key=lambda cut: (
                    -_cut_score(cut, int(cut.get("cut_number") or 0), len(cuts)),
                    int(cut.get("cut_number") or 0),
                ),
            )
            keep.update(id(cut) for cut in group_ranked[:SHORTS_CUT_COUNT])
        if len(keep) < SHORTS_TOTAL_CANDIDATE_CUT_COUNT:
            ranked = sorted(
                existing_marked,
                key=lambda cut: (
                    -_cut_score(cut, int(cut.get("cut_number") or 0), len(cuts)),
                    int(cut.get("cut_number") or 0),
                ),
            )
            for cut in ranked:
                if len(keep) >= SHORTS_TOTAL_CANDIDATE_CUT_COUNT:
                    break
                keep.add(id(cut))
        for cut in cuts:
            if id(cut) in keep:
                cut["shorts_candidate"] = True
                group = int(cut.get("shorts_group") or 0)
                cut["shorts_group"] = group if 1 <= group <= SHORTS_SEGMENT_COUNT else 1
                cut["shorts_score"] = max(int(cut.get("shorts_score") or 0), 7)
            else:
                cut["shorts_candidate"] = False
                cut["shorts_group"] = 0
        return script

    segments = select_shorts_segments(script, count=count, min_count=min_count)
    for cut in cuts:
        cut["shorts_candidate"] = False
        cut["shorts_group"] = 0
    by_number = {}
    for cut in cuts:
        try:
            by_number[int(cut.get("cut_number"))] = cut
        except (TypeError, ValueError):
            continue

    for idx, seg in enumerate(segments[:count], start=1):
        reason = str(seg.get("reason") or "auto-selected shorts segment")
        cut_numbers = seg.get("cut_numbers")
        if isinstance(cut_numbers, list) and cut_numbers:
            nums = [int(n) for n in cut_numbers if str(n).strip().isdigit()]
        else:
            nums = list(range(int(seg["start_cut"]), int(seg["end_cut"]) + 1))
        for num in nums[:SHORTS_CUT_COUNT]:
            cut = by_number.get(num)
            if not cut:
                continue
            cut["shorts_candidate"] = True
            cut["shorts_group"] = idx
            cut["shorts_reason"] = reason
            cut["shorts_score"] = max(int(cut.get("shorts_score") or 0), 7)
    return script


def _font_path(language: str | None = None) -> str:
    lang = str(language or "").lower()
    if lang in {"hi", "hindi"}:
        candidates = (
            r"C:\Windows\Fonts\Nirmala.ttc",
            r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\NirmalaS.ttf",
        )
    elif lang in {"ja", "jp", "japanese"}:
        candidates = (
            r"C:\Windows\Fonts\meiryob.ttc",
            r"C:\Windows\Fonts\YuGothB.ttc",
            r"C:\Windows\Fonts\msgothic.ttc",
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
        )
    else:
        candidates = (
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\meiryob.ttc",
            r"C:\Windows\Fonts\YuGothB.ttc",
            r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf",
        )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return r"C:\Windows\Fonts\malgun.ttf"


def _find_browser_executable() -> str | None:
    candidates = (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    )
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


def _ffmpeg_filter_path(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    return text.replace(":", r"\:")


def _compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _has_language_chars(text: str, language: str) -> bool:
    if language == "ja":
        return bool(re.search(r"[\u3040-\u30FF\u4E00-\u9FFF]", text))
    if language == "hi":
        return bool(re.search(r"[\u0900-\u097F]", text))
    if language == "ko":
        return bool(re.search(r"[\uAC00-\uD7A3]", text))
    return bool(_compact_text(text))


def _is_foreign_shorts_text(text: str, language: str) -> bool:
    if language == "en":
        return False
    text = _compact_text(text)
    if not text:
        return False
    return bool(re.search(r"[A-Za-z]", text)) and not _has_language_chars(text, language)


def _detect_language(script: dict[str, Any]) -> str:
    explicit = str(
        script.get("language")
        or script.get("lang")
        or script.get("locale")
        or ""
    ).lower()
    if explicit.startswith(("hi", "hindi")):
        return "hi"
    if explicit.startswith(("en", "english")):
        return "en"
    if explicit.startswith(("ko", "kr", "korean")):
        return "ko"
    if explicit.startswith(("ja", "jp", "japanese", "日本")):
        return "ja"

    text = " ".join(
        [_compact_text(script.get("title"))]
        + [
            _compact_text(c.get("narration"))
            for c in (script.get("cuts") or [])[:8]
            if isinstance(c, dict)
        ]
    )
    devanagari = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari > 0:
        return "hi"
    kana = len(re.findall(r"[\u3040-\u30FF]", text))
    cjk = len(re.findall(r"[\u4E00-\u9FFF]", text))
    hangul = len(re.findall(r"[\uAC00-\uD7A3]", text))
    if kana > 0 or (cjk > 0 and hangul == 0):
        return "ja"
    latin = len(re.findall(r"[A-Za-z]", text))
    return "en" if latin > hangul * 2 else "ko"


def _shorts_labels(language: str) -> dict[str, str]:
    if language == "hi":
        return {
            "badge": "देखना जरूरी",
            "default_title_1": "जरूरी पल",
            "default_title_2": "आगे देखिए",
            "fallback_channel": "Shorts",
        }
    if language == "en":
        return {
            "badge": "MUST WATCH",
            "default_title_1": "Must-see moment",
            "default_title_2": "Watch what happens",
            "fallback_channel": "Empire Errors",
        }
    if language == "ja":
        return {
            "badge": "注目",
            "default_title_1": "この瞬間",
            "default_title_2": "続きを見てください",
            "fallback_channel": "闇解き日本史",
        }
    return {
        "badge": "지금 봐야 할 장면",
        "default_title_1": "이 장면",
        "default_title_2": "끝까지 보면 달라집니다",
        "fallback_channel": "CH1",
    }


def _default_channel_avatar_url(channel_name: str, language: str) -> str | None:
    name = _compact_text(channel_name)
    by_name = {
        "10분역공": "https://yt3.ggpht.com/lZRG--gQU8wZ5Gzeethzm6NBlG6FD9Jx4QxR4djz4kOgIj-LS9Dm1fO0ruuMEhrZE1AjEFeXQ3Q=s88-c-k-c0x00ffffff-no-rj",
        "Scartography": "https://yt3.ggpht.com/kHPhHQSyGha1yRRa745pBE6YwPnNGwFTlIl7Z9zWZ4eFNiX5UPvUzStCD1AtsJR3ZAsg9UxU=s88-c-k-c0x00ffffff-no-rj",
        "闇解き日本史": "https://yt3.ggpht.com/lRHg7iB8VCuQYJPyiu6P4mKHK6jslowo8ZURRESjmTbiVYqvXCOn0draMc_XV_dGMS6tbjj8DJs=s88-c-k-c0x00ffffff-no-rj",
        "Empire Errors": "https://yt3.ggpht.com/8mFhhpKQW1HpFEPyq0qziMmY26fDaaNTsUayMxnKWf65WuPzR_NQKB_pIb1ULR4lOqwbh_0=s88-c-k-c0x00ffffff-no-rj",
    }
    if name in by_name:
        return by_name[name]
    by_language = {
        "ko": by_name["10분역공"],
        "en": by_name["Empire Errors"],
        "ja": by_name["闇解き日本史"],
    }
    return by_language.get(language)


def _visual_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def _visual_slice(text: str, width: int) -> tuple[str, str]:
    used = 0
    out: list[str] = []
    for idx, ch in enumerate(text):
        ch_width = 0 if unicodedata.combining(ch) else (2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1)
        if out and used + ch_width > width:
            return "".join(out).rstrip(), text[idx:].lstrip()
        out.append(ch)
        used += ch_width
    return "".join(out).rstrip(), ""


def _wrap_text(text: str, *, width: int, max_lines: int = 2) -> str:
    text = _compact_text(text)
    if not text:
        return ""
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif _visual_width(current) + 1 + _visual_width(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines and current:
        lines.append(current)

    # Korean/Hindi titles often have no spaces in the best split points. If a
    # line is still too wide, slice by visual width so the overlay stays on canvas.
    normalized: list[str] = []
    for line in lines:
        while _visual_width(line) > width and len(normalized) < max_lines:
            head, line = _visual_slice(line, width)
            normalized.append(head)
        if line and len(normalized) < max_lines:
            normalized.append(line)
    return "\n".join(normalized[:max_lines])


def _split_headline(
    text: str,
    *,
    width: int = 18,
    fallback_1: str = "Must-see moment",
    fallback_2: str = "Watch what happens",
) -> tuple[str, str]:
    text = _compact_text(text)
    if ":" in text:
        before, after = text.split(":", 1)
        text = after.strip() if len(after.strip()) >= 8 else before.strip()
    words = text.split()
    if not words:
        return fallback_1, fallback_2

    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif _visual_width(current) + 1 + _visual_width(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
            if len(lines) >= 2:
                break
    if current and len(lines) < 2:
        lines.append(current)
    if len(lines) == 1 and _visual_width(lines[0]) > width:
        head, rest = _visual_slice(lines[0], width)
        if rest:
            lines = [head, _visual_slice(rest, width)[0]]
    while len(lines) < 2:
        lines.append(fallback_2)
    return _visual_slice(lines[0], width)[0], _visual_slice(lines[1], width)[0]


def _clean_sentence(text: str) -> str:
    text = _compact_text(text)
    text = re.sub(r"^[\"'“”‘’<>\s]+|[\"'“”‘’<>\s]+$", "", text)
    text = re.split(r"[.!?。！？]", text)[0].strip() or text
    for suffix in ("입니다", "였습니다", "했습니다", "됩니다", "습니다", "했다", "였다", "이다"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
            break
    return text


def _strip_title_noise(text: str) -> str:
    text = _compact_text(text)
    text = re.sub(r"^EP\.?\s*\d+\s*[-:.)]?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+EP\.?\s*\d+\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#\d+\s*#?Shorts?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*#?Shorts?\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"여기서\s*진짜\s*이상한\s*일이\s*벌어집니다?", "", text)
    text = re.sub(r"진짜\s*이유가\s*있습니다?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -:|")
    return text


def _headline_pair(line1: str, line2: str) -> tuple[str, str]:
    line1 = _compact_text(line1)
    line2 = _compact_text(line2)
    if _visual_width(line1) > 18:
        line1, spill = _split_headline(line1, width=18)
        if not line2:
            line2 = spill
    if _visual_width(line2) > 18:
        line2 = "\n".join(_wrap_text(line2, width=18, max_lines=2).splitlines()[:2])
    return line1 or "숨겨진 선택", line2 or "결말이 달라졌습니다"


def _korean_subject(title: str, full_text: str) -> str:
    title = _strip_title_noise(title)
    title = _clean_sentence(title)
    if ":" in title:
        title = title.split(":", 1)[-1].strip()
    if "백제" in full_text:
        if "계백" in full_text or "결사대" in full_text or "5천" in full_text or "5만" in full_text:
            return "백제의 마지막 장군"
        if "일본" in full_text or "왜" in full_text:
            return "일본에 남은 백제"
        return "무너진 백제"
    if "고구려" in full_text or "수나라" in full_text or "살수" in full_text or "을지문덕" in full_text:
        return "고구려의 반격"
    if "고조선" in full_text or "비파형" in full_text:
        return "고조선의 증거"
    if "Post-it" in full_text or "glue" in full_text.lower():
        return "실패한 접착제"
    if "발명" in full_text or "실험" in full_text:
        return "세상을 바꾼 실패"
    if "왕의 선택" in full_text or "선택" in full_text:
        return "왕의 선택"
    return title[:18] if title else "숨겨진 이야기"


def _korean_action_headline(title: str, segment_text: str, full_text: str) -> tuple[str, str]:
    subject = _korean_subject(title, full_text)
    nums = re.findall(r"\d[\d,\.]*\s*(?:만|천|백|명|년|개|척|%)?", full_text)
    compact = full_text.replace(" ", "")

    if "사반왕" in full_text and "고이왕" in full_text and (
        "밀려났" in full_text or "밀어낸" in full_text
    ):
        return _headline_pair("어린 왕을 밀어낸", "고이왕의 선택")
    if "병마권" in full_text and (
        "국가의 군대" in full_text or "독자적인 무력" in full_text
    ):
        return _headline_pair("족장의 군대를 거둔", "고이왕의 병마권")
    if "관등" in full_text and "옷 색" in full_text and (
        "범장지법" in full_text or "뇌물" in full_text
    ):
        return _headline_pair("옷 색으로 줄 세운", "백제의 관등제")
    if "근초고왕" in full_text and (
        "보이지 않는 뼈대" in full_text or "핵심 토대" in full_text
    ):
        return _headline_pair("전성기 뼈대를 만든", "고이왕의 개혁")
    if "백제" in full_text and ("계백" in full_text or "결사대" in full_text or "맞섰" in full_text or "맞선" in full_text):
        if any("5만" in n for n in nums):
            return _headline_pair("5만 대군에 맞선", subject)
        if len(nums) >= 2:
            return _headline_pair(f"{nums[0]}이 {nums[1]}에 맞선", subject)
        return _headline_pair("끝까지 맞서 싸운", subject)
    if "백제" in full_text and ("멸망" in full_text or "망한" in full_text or "다시 시작" in full_text):
        return _headline_pair("멸망 뒤 다시 시작한", subject)
    if "왕인" in full_text and any(word in full_text for word in ("연대", "윤색", "전승", "맞지")):
        return _headline_pair("왕인 전설의 연대", "계산이 안 맞는다")
    if "백제" in full_text and ("일본" in full_text or "고대국가" in full_text or "형성" in full_text):
        return _headline_pair("일본 형성에 남은", subject)
    if "수나라" in full_text and "고구려" in full_text:
        if nums:
            return _headline_pair(f"{nums[0]} 대군을 무너뜨린", subject)
        return _headline_pair("제국의 침공을 막은", subject)
    if "고조선" in full_text or "비파형" in full_text:
        return _headline_pair("교과서 밖에서 발견된", subject)
    if "Post-it" in full_text or "glue" in full_text.lower():
        return _headline_pair("붙지 않아서 성공한", subject)
    if "발명" in full_text or "실험" in full_text:
        return _headline_pair("실패에서 시작된", subject)
    if "칠지도" in full_text and any(word in full_text for word in ("61", "예순한", "금빛", "녹")):
        return _headline_pair("녹을 벗기자 나온", "금빛 61자")
    if "칠지도" in full_text and any(word in full_text for word in ("하사", "헌상", "복종", "영수증")):
        return _headline_pair("복종의 증거인가", "칠지도의 외교전")
    if "칠지도" in full_text and any(word in full_text for word in ("연호", "한 글자", "판독", "해석")):
        return _headline_pair("한 글자가 뒤집은", "백제와 왜의 서열")
    if "숨은" in full_text or "감춘" in full_text or "비밀" in full_text:
        return _headline_pair("비밀을 숨긴", subject)
    if "죽" in compact or "무너" in compact or "사라" in compact:
        return _headline_pair("결말을 바꿔버린", subject)
    return _headline_pair("운명을 바꾼", subject)


def _english_action_headline(segment_text: str, full_text: str) -> tuple[str, str]:
    lower = full_text.casefold()
    if "earthquake" in lower and any(word in lower for word in ("cleanup", "final blast", "rubble")):
        return "The Quake Was Only", "The Final Warning"
    if "1952" in lower or ("linear b" in lower and "greek" in lower):
        return "One Decoding Exposed", "Crete's New Rulers"
    if "mycenaean" in lower and "minoan" in lower and any(
        word in lower for word in ("appropriate", "inherit", "new order", "warrior")
    ):
        return "The Invaders Kept", "The Minoan Machine"
    if "1450 bce" in lower and any(word in lower for word in ("fire", "burn", "destruction")):
        return "Crete Burned", "Almost All at Once"
    if any(word in lower for word in ("thera", "ash", "eruption", "volcano")) and any(
        word in lower for word in ("escape", "survivor", "no bodies", "disappear")
    ):
        return "They Escaped the City", "Before Ash Buried It"
    if "palace" in lower and any(word in lower for word in ("burn", "collapse", "destroy")):
        return "The Palaces Burned", "Who Took Control?"

    cleaned = _clean_sentence(segment_text)
    line1, line2 = _split_headline(
        cleaned,
        width=20,
        fallback_1="The Evidence Changed",
        fallback_2="The Entire Story",
    )
    return line1, line2 or "The Evidence Changed Everything"


def _japanese_action_headline(segment_text: str, full_text: str) -> tuple[str, str]:
    segment_compact = re.sub(r"\s+", "", segment_text)
    compact = re.sub(r"\s+", "", full_text)
    if (
        "ツクヨミ" in segment_compact
        and "ウケモチ" in segment_compact
        and any(word in segment_compact for word in ("殺し", "命を断", "倒れ"))
    ):
        return "神の食卓で殺害", "女神に何が起きた"
    if (
        "稲" in segment_compact
        and "米" in segment_compact
        and "蚕" in segment_compact
        and any(word in segment_compact for word in ("絹", "衣"))
    ):
        return "女神の体が田畑に", "食と衣の起源"
    if (
        "桑" in segment_compact
        and "蚕" in segment_compact
        and any(word in segment_compact for word in ("死の場", "死体", "からだ"))
        and any(word in segment_compact for word in ("芽", "穀物", "命"))
    ):
        return "死体から米と蚕", "神話最大の異変"
    if (
        "種" in segment_compact
        and any(word in segment_compact for word in ("拾", "集め"))
        and any(word in segment_compact for word in ("田", "農"))
    ):
        return "死体の種を拾った", "人類初の農業へ"
    if "大便" in compact or "汚物" in compact:
        return "神殿に汚物", "神々が激怒"
    if "皮を剥" in compact and "馬" in compact:
        return "皮を剥いだ馬", "神殿へ投げた"
    if "機織" in compact and any(word in compact for word in ("命を落", "突き刺", "殺")):
        return "機織りの悲劇", "一人が命を失う"
    if "アマテラス" in compact and any(word in compact for word in ("岩戸", "暗闇")):
        return "太陽神が消えた", "世界が暗闇へ"
    if "スサノオ" in compact and any(word in compact for word in ("暴走", "悪行", "蛮行")):
        return "スサノオ暴走", "天上界が崩れた"

    cleaned = re.sub(r"\s+", "", _clean_sentence(segment_text))
    return _split_headline(
        cleaned,
        width=10,
        fallback_1="神話の転換点",
        fallback_2="何が起きたのか",
    )


def _hook_title_lines(script: dict[str, Any], seg: dict[str, Any]) -> tuple[str, str]:
    """Create a curiosity-first headline instead of copying narration verbatim."""
    segment_text = " ".join(
        _compact_text(c.get("narration"))
        for c in _segment_cuts(script, seg)
        if _compact_text(c.get("narration"))
    )
    full_text = " ".join([_compact_text(script.get("title")), segment_text])
    language = _detect_language(script)
    labels = _shorts_labels(language)
    segment_title = _clean_sentence(segment_text)
    base_title = _strip_title_noise(script.get("title"))
    if _is_foreign_shorts_text(segment_title, language):
        segment_title = ""

    if language == "en" and segment_title:
        return _english_action_headline(segment_text, full_text)
    if language == "ja" and segment_title:
        return _japanese_action_headline(segment_text, full_text)
    if language == "hi" and segment_title:
        return _split_headline(
            segment_title,
            width=20,
            fallback_1=labels["default_title_1"],
            fallback_2=labels["default_title_2"] if language == "en" else "",
        )

    number_matches = re.findall(r"\d[\d,\.]*\s*(?:만|천|백|명|년|개|척|%)?", full_text)
    strong_number = ""
    for value in number_matches:
        if any(unit in value for unit in ("만", "천", "백", "명", "%")) and "년" not in value:
            strong_number = value.strip()
            break
    if "수나라" in full_text and "고구려" in full_text:
        if strong_number:
            return f"{strong_number} 대군", "왜 여기서 무너졌나?"
        if "살수" in full_text or "을지문덕" in full_text:
            return "을지문덕의 한 수", "수나라가 무너졌다"
        return "수나라가 무너진", "진짜 이유는 따로 있었다"
    if ("고조선" in full_text or "비파형" in full_text) and not segment_title:
        return "교과서가 놓친 증거", "이게 진짜 핵심입니다"
    if ("발명" in full_text or "실험" in full_text) and not segment_title:
        return "실패한 실험 하나가", "세상을 바꿨습니다"

    twist = re.search(
        r"(?:그런데|하지만|그러나|사실|알고보니|진짜|반전)[,\s]*(.{8,38})",
        segment_text,
    )
    if twist:
        return _korean_action_headline(base_title, twist.group(1), full_text)
    if strong_number:
        return _korean_action_headline(base_title, segment_text, full_text)
    if segment_title:
        return _korean_action_headline(base_title, segment_title, full_text)

    title = _clean_sentence(base_title) or _clean_sentence(segment_text)
    lower_text = full_text.lower()
    if language == "en" and ("post-it" in lower_text or "glue" in lower_text) and not segment_title:
        return "The Glue That Failed", "Changed Offices"
    if len(title) > 16:
        return _split_headline(
            title,
            width=20,
            fallback_1=labels["default_title_1"],
            fallback_2=labels["default_title_2"] if language == "en" else "",
        )
    return title or labels["default_title_1"], labels["default_title_2"] if language == "en" else ""


def _segment_cuts(script: dict[str, Any], seg: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    cut_numbers_raw = seg.get("cut_numbers")
    cut_numbers: set[int] = set()
    if isinstance(cut_numbers_raw, list):
        for value in cut_numbers_raw:
            try:
                cut_numbers.add(int(value))
            except (TypeError, ValueError):
                continue
    start = max(1, int(seg.get("start_cut") or 1))
    end = max(start, int(seg.get("end_cut") or start))
    selected: list[dict[str, Any]] = []
    for cut in cuts:
        try:
            num = int(cut.get("cut_number") or 0)
        except (TypeError, ValueError):
            continue
        if (cut_numbers and num in cut_numbers) or (not cut_numbers and start <= num <= end):
            selected.append(cut)
    return selected


def _cut_timeline(script: dict[str, Any]) -> dict[int, tuple[float, float]]:
    timeline: dict[int, tuple[float, float]] = {}
    elapsed = 0.0
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    for idx, cut in enumerate(cuts, start=1):
        try:
            num = int(cut.get("cut_number") or idx)
        except (TypeError, ValueError):
            num = idx
        dur = _cut_duration(cut)
        timeline[num] = (elapsed, dur)
        elapsed += dur
    return timeline


def _alignment_word_timings(
    audio_path: Path,
    display_text: str,
    cut_duration: float,
) -> list[dict[str, Any]]:
    """Map display words to the TTS character timeline, with a legacy fallback."""
    words = re.findall(r"\S+", _compact_text(display_text))
    if not words:
        return []

    entries: list[tuple[str, float, float]] = []
    sidecar = alignment_sidecar_path(audio_path)
    if sidecar.exists():
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            timing = payload.get("alignment") or payload.get("normalized_alignment") or {}
            characters = timing.get("characters") or []
            starts = timing.get("character_start_times_seconds") or []
            ends = timing.get("character_end_times_seconds") or []
            if len(characters) == len(starts) == len(ends):
                for character, start, end in zip(characters, starts, ends):
                    value = str(character)
                    if not value or value.isspace():
                        continue
                    entries.append((value, max(0.0, float(start)), max(0.0, float(end))))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            entries = []

    duration = max(0.01, float(cut_duration or 0.0))
    if not entries:
        total_weight = max(1, sum(len(word) for word in words))
        cursor = 0
        fallback: list[dict[str, Any]] = []
        for word in words:
            weight = max(1, len(word))
            start = duration * cursor / total_weight
            cursor += weight
            fallback.append({"text": word, "start": start, "end": duration * cursor / total_weight})
        return fallback

    aligned_text = "".join(item[0] for item in entries)
    display_compact = "".join(words)
    spans: list[tuple[int, int]] = []
    if aligned_text == display_compact:
        cursor = 0
        for word in words:
            end = cursor + len(word)
            spans.append((cursor, end))
            cursor = end
    else:
        aligned_words: list[tuple[float, float]] = []
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
            timing = payload.get("alignment") or payload.get("normalized_alignment") or {}
            characters = timing.get("characters") or []
            starts = timing.get("character_start_times_seconds") or []
            ends = timing.get("character_end_times_seconds") or []
            current_start: float | None = None
            current_end: float | None = None
            for character, start, end in zip(characters, starts, ends):
                if str(character).isspace():
                    if current_start is not None and current_end is not None:
                        aligned_words.append((current_start, current_end))
                    current_start = None
                    current_end = None
                    continue
                if current_start is None:
                    current_start = float(start)
                current_end = float(end)
            if current_start is not None and current_end is not None:
                aligned_words.append((current_start, current_end))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            aligned_words = []
        if len(aligned_words) == len(words):
            return [
                {"text": word, "start": max(0.0, start), "end": min(duration, max(start, end))}
                for word, (start, end) in zip(words, aligned_words)
            ]

        total_weight = max(1, sum(len(word) for word in words))
        cursor = 0
        entry_count = len(entries)
        for word in words:
            start_index = min(entry_count - 1, int(entry_count * cursor / total_weight))
            cursor += max(1, len(word))
            end_index = min(entry_count, max(start_index + 1, round(entry_count * cursor / total_weight)))
            spans.append((start_index, end_index))

    timings: list[dict[str, Any]] = []
    for word, (start_index, end_index) in zip(words, spans):
        if start_index >= len(entries):
            continue
        last_index = min(len(entries) - 1, max(start_index, end_index - 1))
        start = min(duration, entries[start_index][1])
        end = min(duration, max(start, entries[last_index][2]))
        timings.append({"text": word, "start": start, "end": end})
    return timings


def _map_caption_span_to_output(
    start: float,
    end: float,
    keep_segments: list[dict[str, float]],
    playback_rate: float,
) -> tuple[float, float] | None:
    elapsed = 0.0
    mapped_start: float | None = None
    mapped_end: float | None = None
    rate = max(0.01, float(playback_rate or 1.0))
    for segment in keep_segments:
        seg_start = float(segment.get("start") or 0.0)
        seg_end = max(seg_start, float(segment.get("end") or seg_start))
        overlap_start = max(float(start), seg_start)
        overlap_end = min(float(end), seg_end)
        if overlap_end > overlap_start:
            current_start = (elapsed + overlap_start - seg_start) / rate
            current_end = (elapsed + overlap_end - seg_start) / rate
            if mapped_start is None:
                mapped_start = current_start
            mapped_end = current_end
        elapsed += seg_end - seg_start
    if mapped_start is None or mapped_end is None or mapped_end <= mapped_start:
        return None
    return mapped_start, mapped_end


def _build_short_caption_cues(
    script: dict[str, Any],
    cut_numbers: list[int],
    output_dir: Path,
    keep_segments: list[dict[str, float]],
    playback_rate: float,
    cut_durations: dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    cuts_by_number: dict[int, dict[str, Any]] = {}
    for index, cut in enumerate(script.get("cuts", []) or [], start=1):
        if not isinstance(cut, dict):
            continue
        try:
            number = int(cut.get("cut_number") or index)
        except (TypeError, ValueError):
            number = index
        cuts_by_number[number] = cut

    source_cues: list[dict[str, Any]] = []
    source_offset = 0.0
    for number in cut_numbers:
        cut = cuts_by_number.get(number, {})
        cut_duration = float((cut_durations or {}).get(number) or _cut_duration(cut))
        audio_path = output_dir.parent / "audio" / f"cut_{number:03d}.mp3"
        words = _alignment_word_timings(
            audio_path,
            str(cut.get("narration") or ""),
            cut_duration,
        )
        for index in range(0, len(words), 3):
            group = words[index:index + 3]
            if not group:
                continue
            source_cues.append({
                "text": " ".join(str(item["text"]) for item in group),
                "start": source_offset + float(group[0]["start"]),
                "end": source_offset + float(group[-1]["end"]),
            })
        source_offset += cut_duration

    cues: list[dict[str, Any]] = []
    for cue in source_cues:
        mapped = _map_caption_span_to_output(
            float(cue["start"]),
            float(cue["end"]),
            keep_segments,
            playback_rate,
        )
        if mapped is None:
            continue
        start, end = mapped
        start_frame = max(0, int(start * 30))
        if cues:
            start_frame = max(start_frame, int(cues[-1]["endFrame"]))
        end_frame = max(start_frame + 1, int(end * 30 + 0.999999))
        cues.append({
            "text": str(cue["text"]),
            "startFrame": start_frame,
            "endFrame": end_frame,
        })
    return cues


def _cut_video_path(output_dir: Path, cut_num: int) -> Path | None:
    videos_dir = output_dir.parent / "videos"
    candidates = (
        videos_dir / "minimax_h3" / f"cut_{cut_num:03d}.mp4",
        videos_dir / "minimax_h3" / f"cut_{cut_num}.mp4",
        videos_dir / f"cut_{cut_num:03d}.mp4",
        videos_dir / f"cut_{cut_num}.mp4",
    )
    for candidate in candidates:
        if candidate.exists() and candidate.stat().st_size > 0:
            return candidate
    return None


def _short_title(
    script: dict[str, Any],
    seg: dict[str, Any],
    labels: dict[str, str],
    source_title: str | None = None,
) -> str:
    title = _strip_title_noise(
        _compact_text(source_title) or _compact_text(script.get("title"))
    )
    if _detect_language(script) == "ja" and "、" in title:
        first, second = (part.strip() for part in title.split("、", 1))
        if first and second and len(first) <= 16 and len(second) <= 16:
            return f"{first}\n{second}"
    return _wrap_text(title, width=24, max_lines=2)


def derive_shorts_segment_title(script: dict[str, Any], segment: dict[str, Any]) -> str:
    """Return a segment-specific upload title even when rendered metadata is stale."""
    parts = [part for part in _hook_title_lines(script, segment) if part]
    separator = "｜" if _detect_language(script) == "ja" else " "
    return separator.join(parts).strip()


def _short_caption(script: dict[str, Any], seg: dict[str, Any]) -> str:
    """A short punchline shown over the bottom of the central visual."""
    for key in ("caption", "shorts_caption", "subtitle"):
        value = _compact_text(seg.get(key))
        if value:
            return _wrap_text(_clean_sentence(value), width=18, max_lines=3)

    for cut in _segment_cuts(script, seg):
        narration = _clean_sentence(cut.get("narration"))
        if narration:
            return _wrap_text(narration, width=18, max_lines=3)
    return ""


def _source_title(script: dict[str, Any], source_title: str | None = None) -> str:
    title = _strip_title_noise(_compact_text(source_title) or _compact_text(script.get("title")))
    if not title:
        return ""
    return _wrap_text(title, width=18, max_lines=2)


async def resolve_shorts_source_title(
    script: dict[str, Any],
    source_title: str | None = None,
) -> str:
    """Return the episode title in the same language as the Shorts narration."""
    raw_title = _strip_title_noise(
        _compact_text(source_title) or _compact_text(script.get("title"))
    )
    if _detect_language(script) != "ja" or not re.search(r"[가-힣]", raw_title):
        return raw_title

    from app.services.youtube_localization_service import (
        ensure_primary_youtube_metadata_language,
    )

    translated_title, _ = await ensure_primary_youtube_metadata_language(
        title=raw_title,
        description=str(script.get("description") or script.get("topic") or raw_title),
        config={"language": "ja"},
    )
    if re.search(r"[가-힣]", translated_title):
        raise RuntimeError("Japanese Shorts title still contains Hangul")
    return _strip_title_noise(translated_title)


def _channel_name(value: str | None, labels: dict[str, str]) -> str:
    text = _compact_text(value)
    # Never let an episode/video title occupy the bottom brand slot.
    # The caller may not have a channel label configured, and older code passed
    # project.title here; that produces cropped "EP.xx ..." text in shorts.
    if re.match(r"^(?:EP\.?\s*\d+|#?\d+\s*[:.)-])", text, re.IGNORECASE):
        text = ""
    if text.startswith("딸깍폼-"):
        text = text.split("-", 1)[1].strip()
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if labels.get("fallback_channel") == "闇解き日本史" and _is_foreign_shorts_text(text, "ja"):
        text = ""
    if len(text) > 18:
        text = ""
    return text or labels["fallback_channel"]


def _prepare_channel_avatar(url: str | None, shorts_dir: Path) -> Path | None:
    raw_url = _compact_text(url)
    if not raw_url:
        return None
    cache_dir = shorts_dir / "_assets"
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:12]
    raw_path = cache_dir / f"avatar_{digest}.img"
    out_path = cache_dir / f"avatar_{digest}.png"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path
    try:
        req = urllib.request.Request(raw_url, headers={"User-Agent": "LongTube/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_path.write_bytes(resp.read())
        try:
            from PIL import Image, ImageDraw

            size = 96
            img = Image.open(raw_path).convert("RGBA").resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size, size), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
            img.putalpha(mask)
            img.save(out_path)
        except Exception:
            out_path.write_bytes(raw_path.read_bytes())
        return out_path if out_path.exists() and out_path.stat().st_size > 0 else None
    except Exception as e:
        print(f"[shorts] channel avatar download skipped: {e}")
        return None


def _channel_brand_layout(channel: str, *, has_avatar: bool) -> tuple[int, int]:
    if not has_avatar:
        return 0, 0
    return SHORTS_CHANNEL_AVATAR_X, SHORTS_CHANNEL_TEXT_X


_SHORTS_TITLE_ACTION_WORDS = (
    "무너뜨린", "무너진", "밀어낸", "뒤집은", "바꿔버린", "바꾼", "막아낸", "막은",
    "맞서 싸운", "맞선", "버린", "벌린", "거둔", "세운", "만든", "숨긴", "놓친",
    "사라진", "빼앗은", "불태운", "열어준", "열었다", "성공한", "실패한", "잃은",
    "changed", "failed", "destroyed", "defeated", "collapsed", "vanished", "opened",
    "追放", "崩れ", "消え", "失った", "倒した", "変えた",
)


def _title_accent_ranges(text: str) -> list[tuple[int, int]]:
    """Select at most two high-impact terms for the hero title's yellow accent."""
    source = str(text or "")
    ranges: list[tuple[int, int]] = []
    number_pattern = re.compile(
        r"\d+(?:[,.]\d+)*(?:\s*(?:일|년|명|만|천|백|개|척|%|days?|years?))?",
        re.IGNORECASE,
    )
    for match in number_pattern.finditer(source):
        ranges.append(match.span())
        if len(ranges) == 2:
            return ranges
    for word in _SHORTS_TITLE_ACTION_WORDS:
        start = source.casefold().find(word.casefold())
        if start < 0:
            continue
        candidate = (start, start + len(word))
        if any(candidate[0] < end and candidate[1] > begin for begin, end in ranges):
            continue
        ranges.append(candidate)
        if len(ranges) == 2:
            break
    return sorted(ranges)


def _title_accent_ranges_for_lines(lines: list[str]) -> list[list[list[int]]]:
    prepared: list[list[list[int]]] = []
    for line in lines:
        ranges = _title_accent_ranges(line)
        if not ranges:
            words = list(re.finditer(r"[0-9A-Za-z가-힣ぁ-んァ-ン一-龥]+", line))
            ranges = [match.span() for match in words[-2:] if len(match.group(0)) >= 2]
        prepared.append([[begin, end] for begin, end in ranges])
    return prepared


async def render_shorts_from_final(
    final_video: Path,
    output_dir: Path,
    segments: list[dict[str, Any]],
    *,
    script: dict[str, Any] | None = None,
    channel_name: str | None = None,
    channel_avatar_url: str | None = None,
    source_title: str | None = None,
    bgm_path: str | Path | None = None,
    bgm_volume: float = 0.21,
    bgm_ducking_strength: str = "low",
    shorts_subdir: str = "shorts",
    output_filename_prefix: str = "short",
) -> list[dict[str, Any]]:
    """Render composed 9:16 shorts from the final rendered video."""
    if not final_video.exists():
        return []
    if not segments:
        return []

    ffmpeg = find_ffmpeg()
    shorts_dir = output_dir / shorts_subdir
    shorts_dir.mkdir(parents=True, exist_ok=True)
    text_dir = shorts_dir / "_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    remotion_renders: list[dict[str, Any]] = []
    render_records: list[dict[str, Any]] = []
    temp_outputs: list[Path] = []
    script = script or {}
    language = _detect_language(script)
    labels = _shorts_labels(language)
    resolved_source_title = await resolve_shorts_source_title(script, source_title)
    source = _source_title(script, resolved_source_title)
    channel = _channel_name(channel_name, labels)
    timeline = _cut_timeline(script)
    channel_avatar_url = channel_avatar_url or _default_channel_avatar_url(channel, language)
    avatar_path = _prepare_channel_avatar(channel_avatar_url, shorts_dir)
    bgm_file = Path(bgm_path) if bgm_path else None
    if bgm_file and not bgm_file.exists():
        print(f"[shorts] BGM skipped, file not found: {bgm_file}")
        bgm_file = None

    for idx, seg in enumerate(segments[:SHORTS_SEGMENT_COUNT], start=1):
        start_cut = max(1, int(seg["start_cut"]))
        end_cut = max(start_cut, int(seg["end_cut"]))
        cut_numbers_raw = seg.get("cut_numbers")
        cut_numbers: list[int] = []
        if isinstance(cut_numbers_raw, list):
            for value in cut_numbers_raw:
                try:
                    num = int(value)
                except (TypeError, ValueError):
                    continue
                if num > 0 and num not in cut_numbers:
                    cut_numbers.append(num)
        cut_numbers = sorted(cut_numbers)[:SHORTS_CUT_COUNT]
        if not cut_numbers:
            raise RuntimeError("shorts segment has no script-marked cut_numbers")
        if timeline:
            start_sec = 0.0
            duration = sum(timeline.get(num, (0.0, float(CUT_VIDEO_DURATION)))[1] for num in cut_numbers)
            start_cut = cut_numbers[0]
            end_cut = cut_numbers[-1]
        else:
            start_sec = 0.0
            start_cut = cut_numbers[0]
            end_cut = cut_numbers[-1]
            duration = len(cut_numbers) * float(CUT_VIDEO_DURATION)
        out_path = shorts_dir / f"{output_filename_prefix}_{idx}.mp4"
        render_duration = duration

        title_text = _short_title(script, seg, labels, resolved_source_title)
        title_lines = title_text.splitlines() or [title_text]
        title1 = title_lines[0] if title_lines else labels["default_title_1"]
        title2 = title_lines[1] if len(title_lines) > 1 else (labels["default_title_2"] if language == "en" else "")
        title3 = title_lines[2] if len(title_lines) > 2 else ""
        title1 = _wrap_text(title1, width=16, max_lines=1) or labels["default_title_1"]
        title2_lines = _wrap_text(title2, width=16, max_lines=2).splitlines()
        if title2_lines:
            title2 = title2_lines[0]
            if not title3 and len(title2_lines) > 1:
                title3 = title2_lines[1]
        else:
            title2 = ""
        title3 = _wrap_text(title3, width=16, max_lines=1)
        remotion_title_lines = [title1, title2, title3]
        source_clip = final_video
        cut_video_paths = [_cut_video_path(output_dir, num) for num in cut_numbers]
        missing_cuts = [
            num for num, path in zip(cut_numbers, cut_video_paths)
            if path is None
        ]
        if missing_cuts:
            raise RuntimeError(
                f"shorts marked cut video files missing: {missing_cuts}. "
                "Shorts must be built from script-marked cut clips, not merged trim."
            )
        probed_durations = await asyncio.gather(*(
            FFmpegService.probe_duration(str(path))
            for path in cut_video_paths
            if path is not None
        ))
        cut_durations = {
            number: float(probed or timeline.get(number, (0.0, float(CUT_VIDEO_DURATION)))[1])
            for number, probed in zip(cut_numbers, probed_durations)
        }
        duration = sum(cut_durations.values())
        render_duration = duration
        start_sec = 0.0
        concat_source = shorts_dir / f"_cut_concat_short_{idx}.mp4"
        concat_list = shorts_dir / f"_cut_concat_short_{idx}.txt"
        concat_tmp: Path | None = None
        try:
            concat_list.write_text(
                "\n".join(
                    f"file '{str(path).replace(chr(39), chr(39) + '\\\\' + chr(39) + chr(39))}'"
                    for path in cut_video_paths
                    if path is not None
                ),
                encoding="utf-8",
            )
            concat_tmp = _temp_render_path(concat_source)
            concat_cmd = [
                ffmpeg, "-y",
                "-fflags", "+genpts",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-vf", "fps=30,format=yuv420p",
                "-af", "aresample=async=1:first_pts=0",
                "-c:v", "libx264",
                "-preset", SHORTS_VIDEO_PRESET,
                "-crf", SHORTS_VIDEO_CRF,
                "-pix_fmt", "yuv420p",
                "-profile:v", "high",
                "-level", "4.2",
                "-r", "30",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-movflags", "+faststart",
                str(concat_tmp),
            ]
            rc, _, stderr = await run_subprocess(
                concat_cmd,
                timeout=300.0,
                capture_stdout=False,
                capture_stderr=True,
            )
            if rc != 0:
                err = (stderr or b"").decode(errors="replace")[-500:]
                raise RuntimeError(f"shorts cut concat failed for short_{idx}: {err}")
            await _validate_rendered_video(ffmpeg, concat_tmp, f"short_{idx} concat")
            os.replace(concat_tmp, concat_source)
            concat_tmp = None
            source_clip = concat_source
        except Exception as concat_exc:
            raise RuntimeError(
                f"short_{idx} videoized cut assembly failed; image/timeline fallback is disabled: "
                f"{concat_exc}"
            ) from concat_exc
        finally:
            _discard_temp_render(concat_tmp)

        keep_segments = await _detect_silence_keep_segments(
            ffmpeg,
            source_clip,
            duration,
        )
        kept_duration = sum(
            max(0.0, float(segment["end"]) - float(segment["start"]))
            for segment in keep_segments
        )
        render_duration = kept_duration / SHORTS_PLAYBACK_SPEED
        caption_cues = _build_short_caption_cues(
            script,
            cut_numbers,
            output_dir,
            keep_segments,
            SHORTS_PLAYBACK_SPEED,
            cut_durations,
        )

        audio_path = shorts_dir / f"_remotion_audio_short_{idx}.m4a"
        audio_tmp = _temp_render_path(audio_path)
        audio_cmd = [ffmpeg, "-y", "-i", str(source_clip)]
        narration_gain = max(0.5, min(4.0, float(NARRATION_VOLUME_GAIN)))
        if bgm_file:
            vol = max(0.0, min(1.0, float(bgm_volume) * float(BGM_VOLUME_MULTIPLIER)))
            duck = str(bgm_ducking_strength or "normal").strip().lower()
            audio_filter = (
                f"[1:a]volume={vol:.4f},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[bgm];"
                f"[0:a]volume={narration_gain:.4f},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[main];"
            )
            if duck in {"low", "normal", "strong"}:
                threshold, ratio = {
                    "low": ("0.080", "3"),
                    "normal": ("0.050", "6"),
                    "strong": ("0.030", "10"),
                }[duck]
                audio_filter += (
                    f"[bgm][main]sidechaincompress=threshold={threshold}:ratio={ratio}:"
                    "attack=80:release=650[ducked];"
                    "[main][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    "alimiter=limit=0.85:level=false[aout]"
                )
            else:
                audio_filter += (
                    "[main][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    "alimiter=limit=0.85:level=false[aout]"
                )
            audio_cmd.extend([
                "-stream_loop", "-1", "-i", str(bgm_file),
                "-filter_complex", audio_filter,
                "-map", "[aout]",
            ])
        else:
            audio_cmd.extend([
                "-af",
                f"volume={narration_gain:.4f},"
                "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
                "alimiter=limit=0.85:level=false",
                "-map", "0:a:0",
            ])
        audio_cmd.extend([
            "-t", f"{duration:.3f}",
            "-vn",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(audio_tmp),
        ])
        try:
            rc, _, stderr = await run_subprocess(
                audio_cmd,
                timeout=300.0,
                capture_stdout=False,
                capture_stderr=True,
            )
            if rc != 0:
                err = (stderr or b"").decode(errors="replace")[-500:]
                raise RuntimeError(f"shorts audio preparation failed for short_{idx}: {err}")
            await _validate_rendered_audio(ffmpeg, audio_tmp, f"short_{idx} audio")
            os.replace(audio_tmp, audio_path)
            audio_tmp = None
        finally:
            _discard_temp_render(audio_tmp)

        out_tmp = _temp_render_path(out_path)
        temp_outputs.append(out_tmp)
        remotion_renders.append({
            "outputPath": str(out_tmp),
            "assets": {
                "video": str(source_clip),
                "audio": str(audio_path),
                "avatar": str(avatar_path) if avatar_path else None,
            },
            "props": {
                "pipelineId": SHARED_SHORTS_PIPELINE_ID,
                "titleLines": remotion_title_lines,
                "accentRanges": _title_accent_ranges_for_lines(remotion_title_lines),
                "channel": channel,
                "durationInFrames": max(1, round(render_duration * 30)),
                "playbackRate": SHORTS_PLAYBACK_SPEED,
                "keepSegments": keep_segments,
                "captionCues": caption_cues,
            },
        })
        render_records.append({
            "index": idx,
            "path": str(out_path),
            "download_url": f"output/{shorts_subdir}/{output_filename_prefix}_{idx}.mp4",
            "start_cut": start_cut,
            "end_cut": end_cut,
            "duration_seconds": render_duration,
            "source_duration_seconds": duration,
            "playback_speed": SHORTS_PLAYBACK_SPEED,
            "source_playback_speed": SHORTS_SOURCE_PLAYBACK_SPEED,
            "source_clip_type": "videoized-cut-concat",
            "silence_removed_seconds": max(0.0, duration - kept_duration),
            "keep_segments": keep_segments,
            "caption_cue_count": len(caption_cues),
            "reason": seg.get("reason") or "",
            "cut_numbers": cut_numbers or None,
            "layout": "ten-minute-history-white-channel-under-video",
            "renderer": "remotion",
            "pipeline_id": SHARED_SHORTS_PIPELINE_ID,
            "title": title_text,
            "channel_name": channel,
            "source_title": source,
            "language": language,
            "bgm": str(bgm_file) if bgm_file else None,
            "_temp_path": str(out_tmp),
        })

    try:
        await render_remotion_shorts(
            remotion_renders,
            manifest_path=text_dir / "remotion_render_manifest.json",
            browser_executable=_find_browser_executable(),
        )
        results: list[dict[str, Any]] = []
        for record in render_records:
            out_path = Path(record["path"])
            out_tmp = Path(record.pop("_temp_path"))
            await _validate_rendered_video(ffmpeg, out_tmp, f"short_{record['index']} Remotion")
            os.replace(out_tmp, out_path)
            if out_tmp in temp_outputs:
                temp_outputs.remove(out_tmp)
            record["size"] = os.path.getsize(out_path)
            results.append(record)
        return results
    finally:
        for temp_output in temp_outputs:
            _discard_temp_render(temp_output)
