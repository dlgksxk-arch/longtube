"""Shorts candidate selection and rendering helpers."""
from __future__ import annotations

import json
import hashlib
import os
import re
import unicodedata
import urllib.request
from pathlib import Path
from typing import Any

from app.config import CUT_VIDEO_DURATION, NARRATION_VOLUME_GAIN
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


SHORTS_CUT_COUNT = 12
SHORTS_EXCLUDE_EDGE_CUTS = 5
SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920
SHORTS_CLIP_HEIGHT = 840
SHORTS_VIDEO_CRF = "16"
SHORTS_VIDEO_PRESET = "medium"


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


def select_shorts_segments(script: dict[str, Any], *, count: int = 1) -> list[dict[str, Any]]:
    """Return up to count shorts segments using script metadata first, heuristics second."""
    cuts = [c for c in script.get("cuts", []) or [] if isinstance(c, dict)]
    if not cuts:
        return []
    bounds = _eligible_shorts_bounds(len(cuts))
    if not bounds:
        return []
    eligible_first, eligible_last = bounds

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
        if cut.get("shorts_candidate") is True and group > 0 and eligible_first <= cut_num <= eligible_last:
            by_group.setdefault(group, []).append(cut)

    segments: list[dict[str, Any]] = []
    used: set[int] = set()
    for group in sorted(by_group):
        nums = sorted(int(c["cut_number"]) for c in by_group[group] if c.get("cut_number"))
        if not nums:
            continue
        start, end = _expand_segment(
            max(eligible_first, min(nums)),
            min(eligible_last, max(nums)),
            len(cuts),
            min_start=eligible_first,
            max_end=eligible_last,
        )
        if end - start + 1 > SHORTS_CUT_COUNT:
            end = min(eligible_last, start + SHORTS_CUT_COUNT - 1)
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


def annotate_script_shorts(script: dict[str, Any], *, count: int = 1) -> dict[str, Any]:
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


def _font_path(language: str | None = None) -> str:
    lang = str(language or "").lower()
    if lang in {"hi", "hindi"}:
        candidates = (
            r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf",
            r"C:\Windows\Fonts\NirmalaS.ttf",
        )
    else:
        candidates = (
            r"C:\Windows\Fonts\malgunbd.ttf",
            r"C:\Windows\Fonts\NotoSansKR-VF.ttf",
            r"C:\Windows\Fonts\malgun.ttf",
            r"C:\Windows\Fonts\NirmalaB.ttf",
            r"C:\Windows\Fonts\Nirmala.ttf",
        )
    for candidate in candidates:
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
    if explicit.startswith(("hi", "hindi")):
        return "hi"
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
    devanagari = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari > 0:
        return "hi"
    latin = len(re.findall(r"[A-Za-z]", text))
    hangul = len(re.findall(r"[\uAC00-\uD7A3]", text))
    return "en" if latin > hangul * 2 else "ko"


def _shorts_labels(language: str) -> dict[str, str]:
    if language == "hi":
        return {
            "badge": "देखना जरूरी",
            "default_title_1": "जरूरी पल",
            "default_title_2": "आगे देखिए",
            "fallback_channel": "CH4",
        }
    if language == "en":
        return {
            "badge": "MUST WATCH",
            "default_title_1": "Must-see moment",
            "default_title_2": "Watch what happens",
            "fallback_channel": "CH4",
        }
    return {
        "badge": "지금 봐야 할 장면",
        "default_title_1": "이 장면",
        "default_title_2": "끝까지 보면 달라집니다",
        "fallback_channel": "CH1",
    }


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
    # line is still too wide, slice by visual width so drawtext stays on canvas.
    normalized: list[str] = []
    for line in lines:
        while _visual_width(line) > width and len(normalized) < max_lines:
            head, line = _visual_slice(line, width)
            normalized.append(head)
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
        elif _visual_width(current) + 1 + _visual_width(word) <= width:
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

    if "백제" in full_text and ("계백" in full_text or "결사대" in full_text or "맞섰" in full_text or "맞선" in full_text):
        if any("5만" in n for n in nums):
            return _headline_pair("5만 대군에 맞선", subject)
        if len(nums) >= 2:
            return _headline_pair(f"{nums[0]}이 {nums[1]}에 맞선", subject)
        return _headline_pair("끝까지 맞서 싸운", subject)
    if "백제" in full_text and ("멸망" in full_text or "망한" in full_text or "다시 시작" in full_text):
        return _headline_pair("멸망 뒤 다시 시작한", subject)
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
    if "숨은" in full_text or "감춘" in full_text or "비밀" in full_text:
        return _headline_pair("비밀을 숨긴", subject)
    if "죽" in compact or "무너" in compact or "사라" in compact:
        return _headline_pair("결말을 바꿔버린", subject)
    return _headline_pair("운명을 바꾼", subject)


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
    base_title = _strip_title_noise(script.get("title"))

    if language in {"en", "hi"} and segment_title:
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
        return _korean_action_headline(base_title, twist.group(1), full_text)
    if strong_number:
        return _korean_action_headline(base_title, segment_text, full_text)
    if segment_title:
        return _korean_action_headline(base_title, segment_title, full_text)

    title = _clean_sentence(base_title) or _clean_sentence(segment_text)
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
        dur = float(CUT_VIDEO_DURATION)
        timeline[num] = (elapsed, dur)
        elapsed += dur
    return timeline


def _short_title(script: dict[str, Any], seg: dict[str, Any], labels: dict[str, str]) -> str:
    for key in ("title", "shorts_title", "headline"):
        value = _compact_text(seg.get(key))
        if value:
            return _wrap_text(value, width=15, max_lines=2)
    return "\n".join(_hook_title_lines(script, seg))


def _short_caption(script: dict[str, Any], seg: dict[str, Any]) -> str:
    """A short punchline shown over the bottom of the central visual."""
    for key in ("caption", "shorts_caption", "subtitle"):
        value = _compact_text(seg.get(key))
        if value:
            return _wrap_text(_clean_sentence(value), width=19, max_lines=1)

    for cut in _segment_cuts(script, seg):
        narration = _clean_sentence(cut.get("narration"))
        if narration:
            return _wrap_text(narration, width=19, max_lines=1)
    return ""


def _source_title(script: dict[str, Any], source_title: str | None = None) -> str:
    title = _compact_text(source_title) or _compact_text(script.get("title"))
    if not title:
        return ""
    return _wrap_text(title, width=18, max_lines=2)


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
    bgm_volume: float = 0.24,
    bgm_ducking_strength: str = "normal",
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
    language = _detect_language(script)
    font = _ffmpeg_filter_path(_font_path(language))
    labels = _shorts_labels(language)
    source = _source_title(script, source_title)
    channel = _channel_name(channel_name, labels)
    timeline = _cut_timeline(script)
    avatar_path = _prepare_channel_avatar(channel_avatar_url, shorts_dir)
    bgm_file = Path(bgm_path) if bgm_path else None
    if bgm_file and not bgm_file.exists():
        print(f"[shorts] BGM skipped, file not found: {bgm_file}")
        bgm_file = None

    for idx, seg in enumerate(segments[:1], start=1):
        start_cut = max(1, int(seg["start_cut"]))
        end_cut = max(start_cut, int(seg["end_cut"]))
        if timeline:
            start_sec = timeline.get(start_cut, ((start_cut - 1) * float(CUT_VIDEO_DURATION), 0.0))[0]
            end_cut = min(end_cut, start_cut + SHORTS_CUT_COUNT - 1)
            duration = (end_cut - start_cut + 1) * float(CUT_VIDEO_DURATION)
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
        title3_path = text_dir / f"short_{idx}_title_3.txt"
        title_text = _short_title(script, seg, labels)
        title_lines = title_text.splitlines() or [title_text]
        title1 = title_lines[0] if title_lines else labels["default_title_1"]
        title2 = title_lines[1] if len(title_lines) > 1 else labels["default_title_2"]
        title3 = title_lines[2] if len(title_lines) > 2 else ""
        title1 = _wrap_text(title1, width=18, max_lines=1) or labels["default_title_1"]
        title2_lines = _wrap_text(title2, width=18, max_lines=2).splitlines()
        if title2_lines:
            title2 = title2_lines[0]
            if not title3 and len(title2_lines) > 1:
                title3 = title2_lines[1]
        else:
            title2 = labels["default_title_2"]
        title3 = _wrap_text(title3, width=18, max_lines=1)
        title_path.write_text(title_text, encoding="utf-8")
        title1_path.write_text(title1, encoding="utf-8")
        title2_path.write_text(title2, encoding="utf-8")
        title3_path.write_text(title3, encoding="utf-8")
        channel_path.write_text(channel, encoding="utf-8")
        source_path.write_text(source, encoding="utf-8")

        title1_file = _ffmpeg_filter_path(title1_path)
        title2_file = _ffmpeg_filter_path(title2_path)
        title3_file = _ffmpeg_filter_path(title3_path)
        channel_file = _ffmpeg_filter_path(channel_path)
        filter_base = (
            f"color=c=black:s={SHORTS_WIDTH}x{SHORTS_HEIGHT}:d={duration:.3f}[base];"
            f"[0:v]scale={SHORTS_WIDTH}:{SHORTS_CLIP_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={SHORTS_WIDTH}:{SHORTS_CLIP_HEIGHT},setsar=1,fps=30,format=yuv420p[clip];"
            f"[base]drawbox=x=0:y=0:w={SHORTS_WIDTH}:h={SHORTS_HEIGHT}:color=0x050505@1:t=fill[v0];"
            f"[v0]drawtext=fontfile='{font}':textfile='{title1_file}':"
            "fontcolor=white:fontsize=72:borderw=6:bordercolor=black@0.9:"
            "x=(w-text_w)/2:y=78[v1];"
            f"[v1]drawtext=fontfile='{font}':textfile='{title2_file}':"
            "fontcolor=0xf2ff1f:fontsize=72:borderw=6:bordercolor=black@0.9:"
            "x=(w-text_w)/2:y=178[v2];"
            f"[v2]drawtext=fontfile='{font}':textfile='{title3_file}':"
            "fontcolor=0xf2ff1f:fontsize=72:borderw=6:bordercolor=black@0.9:"
            "x=(w-text_w)/2:y=278[v3];"
            f"[v3]drawbox=x=0:y=423:w={SHORTS_WIDTH}:h={SHORTS_CLIP_HEIGHT}:color=0x050505@1:t=fill[v3b];"
            f"[v3b][clip]overlay=(W-w)/2:423+({SHORTS_CLIP_HEIGHT}-h)/2:shortest=1[v4];"
        )
        if avatar_path:
            filter_complex = (
                filter_base +
                "[1:v]scale=86:86,format=rgba[avatar];"
                "[v4][avatar]overlay=x=318:y=1672:format=auto[v5];"
                f"[v5]drawtext=fontfile='{font}':textfile='{channel_file}':"
                "fontcolor=white:fontsize=75:borderw=4:bordercolor=black@0.85:"
                "x=426:y=1680[v6];"
                "[v6]fps=30,format=yuv420p[vout]"
            )
            next_input_index = 2
        else:
            filter_complex = (
                filter_base +
                f"[v4]drawtext=fontfile='{font}':textfile='{channel_file}':"
                "fontcolor=white:fontsize=75:borderw=4:bordercolor=black@0.85:"
                "x=(w-text_w)/2:y=1680[v5];"
                "[v5]fps=30,format=yuv420p[vout]"
            )
            next_input_index = 1
        cmd = [
            ffmpeg, "-y",
            "-ss", f"{start_sec:.3f}",
            "-i", str(final_video),
        ]
        if avatar_path:
            cmd.extend(["-loop", "1", "-i", str(avatar_path)])
        if bgm_file:
            bgm_index = next_input_index
            vol = max(0.0, min(1.0, float(bgm_volume)))
            narration_gain = max(0.5, min(4.0, float(NARRATION_VOLUME_GAIN)))
            duck = str(bgm_ducking_strength or "normal").strip().lower()
            bgm_filter = (
                f"[{bgm_index}:a]volume={vol:.4f},"
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
                bgm_filter += (
                    f"[bgm][main]sidechaincompress=threshold={threshold}:ratio={ratio}:"
                    "attack=80:release=650[ducked];"
                    "[main][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    "alimiter=limit=0.95[aout]"
                )
            else:
                bgm_filter += (
                    "[main][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                    "alimiter=limit=0.95[aout]"
                )
            filter_complex = f"{filter_complex};{bgm_filter}"
            cmd.extend(["-stream_loop", "-1", "-i", str(bgm_file)])
        audio_filter_args = []
        if not bgm_file:
            narration_gain = max(0.5, min(4.0, float(NARRATION_VOLUME_GAIN)))
            audio_filter_args = ["-af", f"volume={narration_gain:.4f},alimiter=limit=0.95"]
        cmd.extend([
            "-t", f"{duration:.3f}",
            "-filter_complex", filter_complex,
            *audio_filter_args,
            "-map", "[vout]",
            "-map", "[aout]" if bgm_file else "0:a?",
            "-c:v", "libx264", "-preset", SHORTS_VIDEO_PRESET, "-crf", SHORTS_VIDEO_CRF,
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.2",
            "-r", "30",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            str(out_path),
        ])
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
            "bgm": str(bgm_file) if bgm_file else None,
            "size": os.path.getsize(out_path),
        })
    return results
