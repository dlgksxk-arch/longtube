"""Shorts candidate selection and rendering helpers."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.config import CUT_VIDEO_DURATION
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
    if HOOK_RE.search(text):
        score += 5
    if cut.get("shorts_candidate") is True:
        score += 8
    if str(cut.get("scene_type") or "").lower() in {"reversal", "reveal", "transition", "title"}:
        score += 2
    if 1 < index < max(2, total - 1):
        score += 1
    return score


SHORTS_CUT_COUNT = 10


def _cut_duration(cut: dict[str, Any]) -> float:
    for key in ("audio_duration", "actual_duration", "duration_estimate"):
        try:
            value = float(cut.get(key) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    return float(CUT_VIDEO_DURATION)


def _expand_segment(start: int, end: int, total: int, *, target: int = SHORTS_CUT_COUNT) -> tuple[int, int]:
    """Expand a selected hook area to a fixed shorts length when possible."""
    start = max(1, min(start, total))
    end = max(start, min(end, total))
    while end - start + 1 < target and (start > 1 or end < total):
        if end < total:
            end += 1
        if end - start + 1 >= target:
            break
        if start > 1:
            start -= 1
    return start, end


def select_shorts_segments(script: dict[str, Any], *, count: int = 2) -> list[dict[str, Any]]:
    """Return up to count shorts segments using script metadata first, heuristics second."""
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    if not cuts:
        return []

    by_group: dict[int, list[dict[str, Any]]] = {}
    for cut in cuts:
        try:
            group = int(cut.get("shorts_group") or 0)
        except (TypeError, ValueError):
            group = 0
        if cut.get("shorts_candidate") is True and group > 0:
            by_group.setdefault(group, []).append(cut)

    segments: list[dict[str, Any]] = []
    used: set[int] = set()
    for group in sorted(by_group):
        nums = sorted(int(c["cut_number"]) for c in by_group[group] if c.get("cut_number"))
        if not nums:
            continue
        start, end = _expand_segment(max(1, min(nums)), min(len(cuts), max(nums)), len(cuts))
        if end - start + 1 > SHORTS_CUT_COUNT:
            end = min(len(cuts), start + SHORTS_CUT_COUNT - 1)
        span = set(range(start, end + 1))
        if used.intersection(span):
            continue
        used.update(span)
        segments.append({
            "group": group,
            "start_cut": start,
            "end_cut": end,
            "reason": by_group[group][0].get("shorts_reason") or "script candidate",
        })
        if len(segments) >= count:
            return segments

    ranked = sorted(
        ((i + 1, _cut_score(c, i + 1, len(cuts))) for i, c in enumerate(cuts)),
        key=lambda item: item[1],
        reverse=True,
    )
    for cut_num, _score in ranked:
        if cut_num in used:
            continue
        start = max(1, cut_num - 2)
        end = min(len(cuts), start + SHORTS_CUT_COUNT - 1)
        start, end = _expand_segment(start, end, len(cuts))
        span = set(range(start, end + 1))
        if used.intersection(span):
            continue
        used.update(span)
        segments.append({
            "group": len(segments) + 1,
            "start_cut": start,
            "end_cut": end,
            "reason": "auto-selected hook/reveal segment",
        })
        if len(segments) >= count:
            break
    if len(segments) < count and len(cuts) > SHORTS_CUT_COUNT:
        # Last-resort deterministic diversity: pick a non-overlapping window
        # from the opposite side of the episode so #1/#2 cannot become clones.
        for start in (1, max(1, len(cuts) - SHORTS_CUT_COUNT + 1), max(1, len(cuts) // 2 - SHORTS_CUT_COUNT // 2)):
            end = min(len(cuts), start + SHORTS_CUT_COUNT - 1)
            span = set(range(start, end + 1))
            if used.intersection(span):
                continue
            used.update(span)
            segments.append({
                "group": len(segments) + 1,
                "start_cut": start,
                "end_cut": end,
                "reason": "auto-selected distinct fallback segment",
            })
            if len(segments) >= count:
                break
    return segments


def annotate_script_shorts(script: dict[str, Any], *, count: int = 2) -> dict[str, Any]:
    """Ensure script cuts contain deterministic shorts metadata."""
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    for cut in cuts:
        cut["shorts_candidate"] = bool(cut.get("shorts_candidate", False))
        try:
            cut["shorts_group"] = int(cut.get("shorts_group") or 0)
        except (TypeError, ValueError):
            cut["shorts_group"] = 0
        cut["shorts_reason"] = str(cut.get("shorts_reason") or "")

    existing_groups = {
        int(c.get("shorts_group") or 0)
        for c in cuts
        if c.get("shorts_candidate") is True and int(c.get("shorts_group") or 0) > 0
    }
    if len(existing_groups) >= count:
        return script

    segments = select_shorts_segments(script, count=count)
    by_number = {}
    for cut in cuts:
        try:
            by_number[int(cut.get("cut_number"))] = cut
        except (TypeError, ValueError):
            continue

    for idx, seg in enumerate(segments[:count], start=1):
        reason = str(seg.get("reason") or "auto-selected shorts segment")
        for num in range(int(seg["start_cut"]), int(seg["end_cut"]) + 1):
            cut = by_number.get(num)
            if not cut:
                continue
            cut["shorts_candidate"] = True
            cut["shorts_group"] = idx
            cut["shorts_reason"] = reason
    return script


def _font_path() -> str:
    for candidate in (
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
        r"C:\Windows\Fonts\malgun.ttf",
    ):
        if Path(candidate).exists():
            return candidate
    return r"C:\Windows\Fonts\malgun.ttf"


def _ffmpeg_filter_path(path: Path | str) -> str:
    text = str(path).replace("\\", "/")
    return text.replace(":", r"\:")


def _compact_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _detect_language(script: dict[str, Any]) -> str:
    explicit = str(
        script.get("language")
        or script.get("lang")
        or script.get("locale")
        or ""
    ).lower()
    if explicit.startswith(("en", "english")):
        return "en"
    if explicit.startswith(("ko", "kr", "korean")):
        return "ko"

    text = " ".join(
        [_compact_text(script.get("title"))]
        + [
            _compact_text(c.get("narration"))
            for c in (script.get("cuts") or [])[:8]
            if isinstance(c, dict)
        ]
    )
    latin = len(re.findall(r"[A-Za-z]", text))
    hangul = len(re.findall(r"[가-힣]", text))
    return "en" if latin > hangul * 2 else "ko"


def _shorts_labels(language: str) -> dict[str, str]:
    if language == "en":
        return {
            "badge": "MUST WATCH",
            "default_title_1": "Must-see moment",
            "default_title_2": "Watch what happens",
            "fallback_channel": "LongTube",
        }
    return {
        "badge": "지금 봐야 할 장면",
        "default_title_1": "이 장면",
        "default_title_2": "끝까지 보면 달라집니다",
        "fallback_channel": "10분역공",
    }


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
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break
    if len(lines) < max_lines and current:
        lines.append(current)

    # Korean titles often have no spaces in the best split points. If a line is
    # still too long, slice by character count rather than letting drawtext run
    # off the canvas.
    normalized: list[str] = []
    for line in lines:
        while len(line) > width and len(normalized) < max_lines:
            normalized.append(line[:width].rstrip())
            line = line[width:].lstrip()
        if line and len(normalized) < max_lines:
            normalized.append(line)
    return "\n".join(normalized[:max_lines])


def _split_headline(text: str, *, width: int = 18) -> tuple[str, str]:
    text = _compact_text(text)
    if ":" in text:
        before, after = text.split(":", 1)
        text = after.strip() if len(after.strip()) >= 8 else before.strip()
    words = text.split()
    if not words:
        return "Must-see moment", "Watch what happens"

    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = word
            if len(lines) >= 2:
                break
    if current and len(lines) < 2:
        lines.append(current)
    while len(lines) < 2:
        lines.append("Watch what happens")
    return lines[0][:width].rstrip(), lines[1][:width].rstrip()


def _clean_sentence(text: str) -> str:
    text = _compact_text(text)
    text = re.sub(r"^[\"'“”‘’<>\s]+|[\"'“”‘’<>\s]+$", "", text)
    text = re.split(r"[.!?。！？]", text)[0].strip() or text
    for suffix in ("입니다", "였습니다", "했습니다", "됩니다", "습니다", "했다", "였다", "이다"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
            break
    return text


def _hook_title_lines(script: dict[str, Any], seg: dict[str, Any]) -> tuple[str, str]:
    """Create a curiosity-first headline instead of copying narration verbatim."""
    segment_text = " ".join(
        _compact_text(c.get("narration"))
        for c in _segment_cuts(script, seg)
        if _compact_text(c.get("narration"))
    )
    full_text = " ".join([_compact_text(script.get("title")), segment_text])
    language = _detect_language(script)
    segment_title = _clean_sentence(segment_text)

    if language == "en" and segment_title:
        return _split_headline(segment_title, width=20)

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
        return "여기서 진짜 이상한", f"일이 벌어집니다"
    if strong_number:
        return f"{strong_number}에 숨은", "진짜 이유가 있습니다"
    if segment_title:
        return _split_headline(segment_title, width=18)

    title = _clean_sentence(script.get("title")) or _clean_sentence(segment_text)
    lower_text = full_text.lower()
    if ("post-it" in lower_text or "glue" in lower_text) and not segment_title:
        return "The Glue That Failed", "Changed Offices"
    if len(title) > 16:
        return _split_headline(title, width=20)
    return title or "이 장면", "끝까지 보면 달라집니다"


def _segment_cuts(script: dict[str, Any], seg: dict[str, Any]) -> list[dict[str, Any]]:
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    start = max(1, int(seg.get("start_cut") or 1))
    end = max(start, int(seg.get("end_cut") or start))
    selected: list[dict[str, Any]] = []
    for cut in cuts:
        try:
            num = int(cut.get("cut_number") or 0)
        except (TypeError, ValueError):
            continue
        if start <= num <= end:
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
        dur = max(0.1, _cut_duration(cut))
        timeline[num] = (elapsed, dur)
        elapsed += dur
    return timeline


def _short_title(script: dict[str, Any], seg: dict[str, Any], labels: dict[str, str]) -> str:
    for key in ("title", "shorts_title", "headline"):
        value = _compact_text(seg.get(key))
        if value:
            return _wrap_text(value, width=15, max_lines=2)
    return "\n".join(_hook_title_lines(script, seg))


def _source_title(script: dict[str, Any], source_title: str | None = None) -> str:
    title = _compact_text(source_title) or _compact_text(script.get("title"))
    if not title:
        return ""
    return _wrap_text(title, width=18, max_lines=2)


def _channel_name(value: str | None, labels: dict[str, str]) -> str:
    text = _compact_text(value)
    if text.startswith("딸깍폼-"):
        text = text.split("-", 1)[1].strip()
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if len(text) > 24:
        text = text[:24].rstrip()
    return text or labels["fallback_channel"]


async def render_shorts_from_final(
    final_video: Path,
    output_dir: Path,
    segments: list[dict[str, Any]],
    *,
    script: dict[str, Any] | None = None,
    channel_name: str | None = None,
    source_title: str | None = None,
) -> list[dict[str, Any]]:
    """Render composed 9:16 shorts from the final rendered video."""
    if not final_video.exists():
        return []
    if not segments:
        return []

    ffmpeg = find_ffmpeg()
    shorts_dir = output_dir / "shorts"
    shorts_dir.mkdir(parents=True, exist_ok=True)
    text_dir = shorts_dir / "_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    script = script or {}
    font = _ffmpeg_filter_path(_font_path())
    language = _detect_language(script)
    labels = _shorts_labels(language)
    source = _source_title(script, source_title)
    channel = _channel_name(channel_name, labels)
    timeline = _cut_timeline(script)

    for idx, seg in enumerate(segments[:2], start=1):
        start_cut = max(1, int(seg["start_cut"]))
        end_cut = max(start_cut, int(seg["end_cut"]))
        if timeline:
            start_sec = timeline.get(start_cut, ((start_cut - 1) * float(CUT_VIDEO_DURATION), 0.0))[0]
            duration = 0.0
            actual_end_cut = start_cut
            for cut_num in range(start_cut, min(end_cut, start_cut + SHORTS_CUT_COUNT - 1) + 1):
                cut_start, cut_duration = timeline.get(
                    cut_num,
                    ((cut_num - 1) * float(CUT_VIDEO_DURATION), float(CUT_VIDEO_DURATION)),
                )
                duration += cut_duration
                actual_end_cut = cut_num
            end_cut = actual_end_cut
            duration = max(duration, 0.1)
        else:
            start_sec = (start_cut - 1) * float(CUT_VIDEO_DURATION)
            end_cut = min(end_cut, start_cut + SHORTS_CUT_COUNT - 1)
            duration = (end_cut - start_cut + 1) * float(CUT_VIDEO_DURATION)
        out_path = shorts_dir / f"short_{idx}.mp4"

        title_path = text_dir / f"short_{idx}_title.txt"
        channel_path = text_dir / f"short_{idx}_channel.txt"
        source_path = text_dir / f"short_{idx}_source.txt"
        title1_path = text_dir / f"short_{idx}_title_1.txt"
        title2_path = text_dir / f"short_{idx}_title_2.txt"
        title_text = _short_title(script, seg, labels)
        title_lines = title_text.splitlines() or [title_text]
        title1 = title_lines[0] if title_lines else labels["default_title_1"]
        title2 = title_lines[1] if len(title_lines) > 1 else labels["default_title_2"]
        title_path.write_text(title_text, encoding="utf-8")
        title1_path.write_text(title1, encoding="utf-8")
        title2_path.write_text(title2, encoding="utf-8")
        channel_path.write_text(channel, encoding="utf-8")
        source_path.write_text(source, encoding="utf-8")

        title1_file = _ffmpeg_filter_path(title1_path)
        title2_file = _ffmpeg_filter_path(title2_path)
        channel_file = _ffmpeg_filter_path(channel_path)
        source_file = _ffmpeg_filter_path(source_path)
        filter_complex = (
            f"color=c=black:s=720x1280:d={duration:.3f}[base];"
            "[0:v]scale=660:-2:force_original_aspect_ratio=decrease,setsar=1,fps=30[clip];"
            "[base]drawbox=x=0:y=0:w=720:h=1280:color=0x050505@1:t=fill[v0];"
            "[v0]drawbox=x=46:y=54:w=246:h=46:color=0xff2d2d@0.95:t=fill[v1];"
            f"[v1]drawtext=fontfile='{font}':text='{labels['badge']}':"
            "fontcolor=white:fontsize=24:borderw=0:x=70:y=62[v2];"
            "[v2]drawbox=x=46:y=118:w=7:h=126:color=0xffd43b@1:t=fill[v3];"
            f"[v3]drawtext=fontfile='{font}':textfile='{title1_file}':"
            "fontcolor=white:fontsize=54:borderw=3:bordercolor=black@0.8:"
            "x=68:y=130[v4];"
            f"[v4]drawtext=fontfile='{font}':textfile='{title2_file}':"
            "fontcolor=0xffd43b:fontsize=54:borderw=3:bordercolor=black@0.8:"
            "x=68:y=205[v5];"
            "[v5]drawbox=x=24:y=324:w=672:h=390:color=0xffd43b@1:t=5[v6];"
            "[v6][clip]overlay=(W-w)/2:333:shortest=1[v7];"
            "[v7]drawbox=x=48:y=754:w=624:h=2:color=0xffd43b@0.85:t=fill[v8];"
            f"[v8]drawtext=fontfile='{font}':textfile='{channel_file}':"
            "fontcolor=white:fontsize=36:borderw=2:bordercolor=black@0.8:"
            "x=(w-text_w)/2:y=805[v9];"
            "[v9]drawbox=x=58:y=866:w=604:h=150:color=0x111111@0.88:t=fill[v10];"
            "[v10]drawbox=x=58:y=866:w=604:h=150:color=0x444444@1:t=2[v11];"
            f"[v11]drawtext=fontfile='{font}':textfile='{source_file}':"
            "fontcolor=white:fontsize=26:line_spacing=10:borderw=1:bordercolor=black@0.8:"
            "x=(w-text_w)/2:y=914[vout]"
        )
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", str(final_video),
            "-t", f"{duration:.3f}",
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", "0:a?",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            "-shortest",
            str(out_path),
        ]
        rc, _, stderr = await run_subprocess(
            cmd,
            timeout=600.0,
            capture_stdout=False,
            capture_stderr=True,
        )
        if rc != 0:
            err = (stderr or b"").decode(errors="replace")[-500:]
            raise RuntimeError(f"shorts render failed for short_{idx}: {err}")
        results.append({
            "index": idx,
            "path": str(out_path),
            "download_url": f"output/shorts/short_{idx}.mp4",
            "start_cut": start_cut,
            "end_cut": end_cut,
            "duration_seconds": duration,
            "reason": seg.get("reason") or "",
            "layout": "title-video-channel-source",
            "title": title_text,
            "channel_name": channel,
            "source_title": source,
            "language": language,
            "size": os.path.getsize(out_path),
        })
    return results
