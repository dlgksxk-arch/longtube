"""Shared Remotion long-form assembly adapter for every LongTube channel."""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess


SHARED_LONGFORM_PIPELINE_ID = "shared-all-channels-remotion-longform-v1"
LONGFORM_FPS = 30
LONGFORM_SILENCE_THRESHOLD_DB = -42
LONGFORM_SILENCE_MIN_DURATION = 0.35
LONGFORM_SILENCE_EDGE_PADDING = 0.08
LONGFORM_SILENCE_PLAYBACK_RATE = 2.0


def remotion_longform_root() -> Path:
    return Path(__file__).resolve().parents[3] / "remotion-shorts"


def _find_node() -> str:
    configured = str(os.environ.get("NODE_BIN") or "").strip().strip('"')
    if configured and Path(configured).is_file():
        return configured
    node = shutil.which("node") or shutil.which("node.exe")
    if node:
        return node
    raise RuntimeError("Remotion long-form renderer requires Node.js, but node was not found")


def _find_browser_executable() -> str | None:
    for candidate in (
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if Path(candidate).is_file():
            return candidate
    return None


def _parse_resolution(resolution: str) -> tuple[int, int]:
    try:
        width_text, height_text = str(resolution).lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid long-form resolution: {resolution!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid long-form resolution: {resolution!r}")
    return width, height


def _half_silence_segments(
    duration: float,
    silence_ranges: list[tuple[float, float]],
) -> list[dict[str, float | int]]:
    duration = max(0.0, float(duration or 0.0))
    if duration <= 0.0:
        return []
    padding = float(LONGFORM_SILENCE_EDGE_PADDING)
    compressed: list[tuple[float, float]] = []
    for raw_start, raw_end in sorted(silence_ranges):
        start = max(0.0, min(duration, float(raw_start)))
        end = max(start, min(duration, float(raw_end)))
        start = min(end, start + padding)
        end = max(start, end - padding)
        if end - start >= 0.05:
            if compressed and start <= compressed[-1][1]:
                compressed[-1] = (compressed[-1][0], max(compressed[-1][1], end))
            else:
                compressed.append((start, end))

    segments: list[dict[str, float | int]] = []

    def append_segment(start: float, end: float, rate: float) -> None:
        if end - start < 0.001:
            return
        segments.append({
            "startFrom": max(0, round(start * LONGFORM_FPS)),
            "endAt": max(1, round(end * LONGFORM_FPS)),
            "playbackRate": rate,
            "durationInFrames": max(1, round((end - start) * LONGFORM_FPS / rate)),
        })

    cursor = 0.0
    for start, end in compressed:
        append_segment(cursor, start, 1.0)
        append_segment(start, end, LONGFORM_SILENCE_PLAYBACK_RATE)
        cursor = end
    append_segment(cursor, duration, 1.0)
    return segments or [{
        "startFrom": 0,
        "endAt": max(1, round(duration * LONGFORM_FPS)),
        "playbackRate": 1.0,
        "durationInFrames": max(1, round(duration * LONGFORM_FPS)),
    }]


async def _detect_silence_ranges(path: Path, duration: float) -> list[tuple[float, float]]:
    rc, _, stderr = await run_subprocess(
        [
            find_ffmpeg(),
            "-hide_banner",
            "-i", str(path),
            "-af",
            (
                f"silencedetect=noise={LONGFORM_SILENCE_THRESHOLD_DB}dB:"
                f"d={LONGFORM_SILENCE_MIN_DURATION:.3f}"
            ),
            "-f", "null", "-",
        ],
        timeout=300.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    stderr_text = (stderr or b"").decode(errors="replace")
    if rc != 0:
        no_audio_markers = (
            "matches no streams",
            "does not contain any stream",
            "cannot find a matching stream",
        )
        if any(marker in stderr_text.lower() for marker in no_audio_markers):
            return [(0.0, duration)]
        raise RuntimeError(f"Long-form silence detection failed for {path}: {stderr_text[-1000:]}")

    events = re.findall(
        r"silence_(start|end):\s*(-?[0-9]+(?:\.[0-9]+)?)",
        stderr_text,
    )
    ranges: list[tuple[float, float]] = []
    current_start: float | None = None
    for kind, raw_value in events:
        value = max(0.0, min(duration, float(raw_value)))
        if kind == "start":
            current_start = value
        elif current_start is not None:
            ranges.append((current_start, value))
            current_start = None
    if current_start is not None:
        ranges.append((current_start, duration))
    return ranges


async def render_remotion_longform(
    video_paths: list[str | Path],
    output_path: str | Path,
    *,
    resolution: str = "1920x1080",
    title: str = "",
    channel_name: str = "",
    browser_executable: str | None = None,
    manifest_path: str | Path | None = None,
    shorten_silence: bool = True,
    timeline_out: list[dict] | None = None,
) -> str:
    """Concatenate ordered clips with audio through the shared Remotion composition."""
    width, height = _parse_resolution(resolution)
    valid_paths: list[Path] = []
    for raw_path in video_paths:
        path = Path(raw_path).resolve()
        if path.is_file() and path.stat().st_size > 0:
            valid_paths.append(path)
    if not valid_paths:
        raise RuntimeError("Remotion long-form assembly has no valid input clips")

    clips: list[dict] = []
    for path in valid_paths:
        duration = await FFmpegService.probe_duration(str(path))
        if duration <= 0.0:
            raise RuntimeError(f"Could not determine long-form clip duration: {path}")
        silence_ranges = await _detect_silence_ranges(path, duration) if shorten_silence else []
        segments = _half_silence_segments(duration, silence_ranges)
        output_frames = sum(int(item["durationInFrames"]) for item in segments)
        clips.append({
            "durationInFrames": output_frames,
            "segments": segments,
            "sourceDurationSeconds": duration,
            "outputDurationSeconds": output_frames / LONGFORM_FPS,
        })

    if timeline_out is not None:
        timeline_out.clear()
        timeline_out.extend(
            {
                "path": str(path),
                "source_duration_seconds": float(clip["sourceDurationSeconds"]),
                "output_duration_seconds": float(clip["outputDurationSeconds"]),
                "silence_shortened_seconds": max(
                    0.0,
                    float(clip["sourceDurationSeconds"]) - float(clip["outputDurationSeconds"]),
                ),
            }
            for path, clip in zip(valid_paths, clips)
        )

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    root = remotion_longform_root()
    renderer = root / "render-longform.mjs"
    package_lock = root / "package-lock.json"
    node_modules = root / "node_modules"
    if not renderer.is_file() or not package_lock.is_file():
        raise RuntimeError(f"Remotion long-form renderer is incomplete: {root}")
    if not node_modules.is_dir():
        raise RuntimeError(
            f"Remotion dependencies are missing. Run: npm install --prefix {root}"
        )

    manifest = (
        Path(manifest_path).resolve()
        if manifest_path
        else output.parent / f".{output.stem}.remotion-longform.json"
    )
    payload = {
        "version": 1,
        "pipeline": SHARED_LONGFORM_PIPELINE_ID,
        "browserExecutable": browser_executable or _find_browser_executable(),
        "renders": [
            {
                "outputPath": str(output),
                "assets": [str(path) for path in valid_paths],
                "props": {
                    "pipelineId": SHARED_LONGFORM_PIPELINE_ID,
                    "width": width,
                    "height": height,
                    "fps": LONGFORM_FPS,
                    "durationInFrames": sum(item["durationInFrames"] for item in clips),
                    "clips": clips,
                    "silenceCompressionRatio": 0.5 if shorten_silence else 1.0,
                    "title": str(title or "").strip(),
                    "channelName": str(channel_name or "").strip(),
                },
            }
        ],
    }
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    rc, _, stderr = await run_subprocess(
        [_find_node(), str(renderer), str(manifest)],
        timeout=14400.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0:
        stderr_text = (stderr or b"").decode(errors="replace")
        raise RuntimeError(f"Remotion long-form render failed: {stderr_text.strip()[-3000:]}")
    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError(f"Remotion long-form output is missing: {output}")
    return str(output)
