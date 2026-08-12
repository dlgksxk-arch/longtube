"""Shared FFmpeg long-form assembler for every LongTube channel.

The long-form timeline consists of already rendered MP4 clips.  Replaying the
whole timeline in Chromium is unnecessary and was the dominant render cost.
This adapter normalizes clips with FFmpeg, optionally halves detected silence,
composites the static long-form header in the same encode, and stream-concats
the normalized results without another generation loss.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.video.ffmpeg_service import FFmpegService, LONGFORM_VIDEO_ENCODE_ARGS
from app.services.video.longform_header import create_longform_header_overlay
from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess


SHARED_LONGFORM_PIPELINE_ID = "shared-all-channels-ffmpeg-longform-v2"
LONGFORM_FPS = 30
LONGFORM_SILENCE_THRESHOLD_DB = -42
LONGFORM_SILENCE_MIN_DURATION = 0.35
LONGFORM_SILENCE_EDGE_PADDING = 0.08
LONGFORM_SILENCE_PLAYBACK_RATE = 2.0


def _parse_resolution(resolution: str) -> tuple[int, int]:
    try:
        width_text, height_text = str(resolution).lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid long-form resolution: {resolution!r}")
    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid long-form resolution: {resolution!r}")
    return width, height


def _worker_count() -> int:
    configured = str(os.environ.get("LONGFORM_FFMPEG_WORKERS") or "").strip()
    if configured:
        try:
            return max(1, min(8, int(configured)))
        except ValueError:
            pass
    # i5-13500/64GB: four concurrent x264 workers fill the hybrid CPU without
    # starting one encoder per logical thread or overwhelming the output disk.
    logical = max(1, int(os.cpu_count() or 1))
    return max(1, min(4, logical // 4))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


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
        start = 0.0 if start <= padding else min(end, start + padding)
        end = duration if duration - end <= padding else max(start, end - padding)
        if end - start >= 0.05:
            if compressed and start <= compressed[-1][1]:
                compressed[-1] = (compressed[-1][0], max(compressed[-1][1], end))
            else:
                compressed.append((start, end))

    segments: list[dict[str, float | int]] = []

    def append_segment(start: float, end: float, rate: float) -> None:
        if end - start < 0.001:
            return
        output_frames = max(1, round((end - start) * LONGFORM_FPS / rate))
        segments.append({
            "startSeconds": start,
            "endSeconds": end,
            "startFrom": max(0, round(start * LONGFORM_FPS)),
            "endAt": max(1, round(end * LONGFORM_FPS)),
            "playbackRate": rate,
            "durationInFrames": output_frames,
        })

    cursor = 0.0
    for start, end in compressed:
        append_segment(cursor, start, 1.0)
        append_segment(start, end, LONGFORM_SILENCE_PLAYBACK_RATE)
        cursor = end
    append_segment(cursor, duration, 1.0)
    return segments or [{
        "startSeconds": 0.0,
        "endSeconds": duration,
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


def _segment_filter_graph(
    *,
    playback_rate: float,
    resolution: str,
    trim_start: float,
    trim_end: float,
    output_duration: float,
    overlay_enabled: bool,
    audio_input_index: int = 0,
    overlay_input_index: int = 1,
) -> tuple[str, str, str]:
    """Build one bounded segment graph.

    Keeping each silence/speech segment in its own FFmpeg process prevents the
    concat filter from buffering later branches while it waits for the first
    branch, which can otherwise consume tens of gigabytes on long cuts.
    """
    pad_wh = resolution.replace("x", ":")
    filters = [
        f"[0:v]trim=start={trim_start:.6f}:end={trim_end:.6f},"
        f"setpts=(PTS-STARTPTS)/{playback_rate:.6f},"
        f"scale={resolution}:force_original_aspect_ratio=decrease,"
        f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={LONGFORM_FPS},"
        "format=yuv420p[vbase]"
    ]
    filters.append(
        f"[{audio_input_index}:a]atrim=start={trim_start:.6f}:end={trim_end:.6f},"
        "asetpts=PTS-STARTPTS,"
        f"atempo={playback_rate:.6f},aresample=48000,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"apad,atrim=duration={output_duration:.6f}[aout]"
    )
    if overlay_enabled:
        filters.append(
            f"[vbase][{overlay_input_index}:v]"
            "overlay=0:0:eof_action=repeat:shortest=0:format=auto,"
            "format=yuv420p[vout]"
        )
        video_output = "[vout]"
    else:
        video_output = "[vbase]"
    return ";".join(filters), video_output, "[aout]"


async def _has_audio_stream(path: Path) -> bool:
    """Probe audio without relying on a separate ffprobe installation."""
    _, _, stderr = await run_subprocess(
        [find_ffmpeg(), "-hide_banner", "-i", str(path)],
        timeout=30.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    return " Audio:" in (stderr or b"").decode(errors="replace")


async def _remux_clip(source: Path, destination: Path) -> None:
    """Copy video and decode audio to PCM for gap-free final concatenation."""
    rc, _, stderr = await run_subprocess(
        [
            find_ffmpeg(), "-y",
            "-fflags", "+genpts",
            "-i", str(source),
            "-map", "0:v:0",
            "-map", "0:a:0",
            "-c:v", "copy",
            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
            str(destination),
        ],
        timeout=300.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        stderr_text = (stderr or b"").decode(errors="replace")
        raise RuntimeError(
            f"FFmpeg long-form timestamp remux failed for {source}: "
            f"{stderr_text[-2000:]}"
        )


async def _concat_stream_copy(paths: list[Path], destination: Path) -> None:
    """Concatenate timestamp-normalized streams without another video pass."""
    concat_file = destination.with_name(f".{destination.name}.concat.txt")
    try:
        concat_file.write_text(
            "".join(
                f"file '{str(path.resolve()).replace(chr(92), '/').replace(chr(39), chr(92) + chr(39))}'\n"
                for path in paths
            ),
            encoding="utf-8",
        )
        rc, _, stderr = await run_subprocess(
            [
                find_ffmpeg(), "-y",
                "-fflags", "+genpts",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c", "copy",
                str(destination),
            ],
            timeout=600.0,
            capture_stdout=False,
            capture_stderr=True,
        )
    finally:
        concat_file.unlink(missing_ok=True)
    if rc != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        stderr_text = (stderr or b"").decode(errors="replace")
        raise RuntimeError(f"FFmpeg long-form concat failed: {stderr_text[-2000:]}")


async def _finalize_pcm_timeline(
    source: Path,
    destination: Path,
    *,
    output_duration: float,
) -> None:
    """Encode AAC once after all PCM segments are joined; copy H.264 video."""
    rc, _, stderr = await run_subprocess(
        [
            find_ffmpeg(), "-y", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-t", f"{output_duration:.6f}",
            "-video_track_timescale", "15360",
            "-movflags", "+faststart",
            str(destination),
        ],
        timeout=1200.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        stderr_text = (stderr or b"").decode(errors="replace")
        raise RuntimeError(f"FFmpeg long-form final mux failed: {stderr_text[-2000:]}")


async def _render_clip(
    source: Path,
    destination: Path,
    *,
    segments: list[dict[str, float | int]],
    resolution: str,
    source_duration: float,
    output_duration: float,
    overlay_path: Path | None,
    has_audio: bool,
) -> None:
    del source_duration, output_duration
    with tempfile.TemporaryDirectory(
        prefix=f".{destination.stem}-parts-",
        dir=str(destination.parent),
    ) as segment_dir:
        segment_root = Path(segment_dir)
        segment_paths: list[Path] = []
        for index, segment in enumerate(segments):
            start = float(segment["startSeconds"])
            end = float(segment["endSeconds"])
            rate = float(segment["playbackRate"])
            raw_duration = max(0.001, end - start)
            # A short preroll guarantees at least one decodable video packet
            # for tiny tail segments that begin close to the MP4 EOF.
            seek_start = max(0.0, start - 0.25)
            trim_start = start - seek_start
            trim_end = trim_start + raw_duration
            input_duration = max(0.001, end - seek_start)
            segment_duration = int(segment["durationInFrames"]) / LONGFORM_FPS
            segment_path = segment_root / f"segment_{index:03d}.mkv"
            audio_input_index = 0 if has_audio else 1
            overlay_input_index = 1 if has_audio else 2
            filter_graph, video_output, audio_output = _segment_filter_graph(
                playback_rate=rate,
                resolution=resolution,
                trim_start=trim_start,
                trim_end=trim_end,
                output_duration=segment_duration,
                overlay_enabled=overlay_path is not None,
                audio_input_index=audio_input_index,
                overlay_input_index=overlay_input_index,
            )
            cmd = [
                find_ffmpeg(), "-y",
                "-ss", f"{seek_start:.6f}",
                "-t", f"{input_duration:.6f}",
                "-i", str(source),
            ]
            if not has_audio:
                cmd.extend([
                    "-f", "lavfi",
                    "-t", f"{input_duration:.6f}",
                    "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                ])
            if overlay_path is not None:
                cmd.extend(["-i", str(overlay_path)])
            cmd.extend([
                "-filter_complex", filter_graph,
                "-map", video_output,
                "-map", audio_output,
                *LONGFORM_VIDEO_ENCODE_ARGS[:-2],
                "-r", str(LONGFORM_FPS),
                "-fps_mode", "cfr",
                "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2",
                "-t", f"{segment_duration:.6f}",
                str(segment_path),
            ])
            rc, _, stderr = await run_subprocess(
                cmd,
                timeout=600.0,
                capture_stdout=False,
                capture_stderr=True,
            )
            if rc != 0 or not segment_path.is_file() or segment_path.stat().st_size <= 0:
                stderr_text = (stderr or b"").decode(errors="replace")
                raise RuntimeError(
                    f"FFmpeg long-form segment failed for {source} "
                    f"({start:.3f}-{end:.3f}s): {stderr_text[-2000:]}"
                )
            segment_paths.append(segment_path)

        await _concat_stream_copy(segment_paths, destination)


async def render_ffmpeg_longform(
    video_paths: list[str | Path],
    output_path: str | Path,
    *,
    resolution: str = "1920x1080",
    title: str = "",
    channel_name: str = "",
    manifest_path: str | Path | None = None,
    shorten_silence: bool = True,
    stream_copy_compatible_inputs: bool = False,
    timeline_out: list[dict] | None = None,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> str:
    """Normalize, optionally silence-compress, overlay, and concatenate clips."""
    _parse_resolution(resolution)
    valid_paths: list[Path] = []
    for raw_path in video_paths:
        path = Path(raw_path).resolve()
        if path.is_file() and path.stat().st_size > 0:
            valid_paths.append(path)
    if not valid_paths:
        raise RuntimeError("FFmpeg long-form assembly has no valid input clips")

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = (
        Path(manifest_path).resolve()
        if manifest_path
        else output.parent / f".{output.stem}.ffmpeg-longform.json"
    )
    status_path = Path(f"{manifest}.status.json")
    workers = _worker_count()

    def write_status(stage: str, **detail: Any) -> None:
        payload = {
            "stage": stage,
            "pipeline": SHARED_LONGFORM_PIPELINE_ID,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            **detail,
        }
        _write_json(status_path, payload)
        if progress_callback is not None:
            progress_callback(dict(payload))

    write_status("analyzing", completedClips=0, totalClips=len(valid_paths), progress=0.0)
    analyze_semaphore = asyncio.Semaphore(workers)

    async def analyze(path: Path) -> dict[str, Any]:
        async with analyze_semaphore:
            duration = await FFmpegService.probe_duration(str(path))
            if duration <= 0.0:
                raise RuntimeError(f"Could not determine long-form clip duration: {path}")
            has_audio = await _has_audio_stream(path)
            silence_ranges = (
                await _detect_silence_ranges(path, duration)
                if shorten_silence and has_audio
                else []
            )
            segments = _half_silence_segments(duration, silence_ranges)
            output_frames = sum(int(item["durationInFrames"]) for item in segments)
            return {
                "path": path,
                "hasAudio": has_audio,
                "segments": segments,
                "sourceDurationSeconds": duration,
                "durationInFrames": output_frames,
                "outputDurationSeconds": output_frames / LONGFORM_FPS,
            }

    clips = list(await asyncio.gather(*(analyze(path) for path in valid_paths)))
    manifest_payload = {
        "version": 2,
        "pipeline": SHARED_LONGFORM_PIPELINE_ID,
        "assets": [str(path) for path in valid_paths],
        "outputPath": str(output),
        "props": {
            "width": _parse_resolution(resolution)[0],
            "height": _parse_resolution(resolution)[1],
            "fps": LONGFORM_FPS,
            "durationInFrames": sum(int(item["durationInFrames"]) for item in clips),
            "silenceCompressionRatio": 0.5 if shorten_silence else 1.0,
            "assemblyMode": "timestamp-remux" if (
                stream_copy_compatible_inputs
                and not shorten_silence
                and not str(title or "").strip()
                and not str(channel_name or "").strip()
                and all(bool(item["hasAudio"]) for item in clips)
            ) else "filter-encode",
            "title": str(title or "").strip(),
            "channelName": str(channel_name or "").strip(),
            "workers": workers,
            "clips": [
                {
                    key: value
                    for key, value in item.items()
                    if key != "path"
                }
                for item in clips
            ],
        },
    }
    _write_json(manifest, manifest_payload)

    if timeline_out is not None:
        timeline_out.clear()
        timeline_out.extend(
            {
                "path": str(item["path"]),
                "source_duration_seconds": float(item["sourceDurationSeconds"]),
                "output_duration_seconds": float(item["outputDurationSeconds"]),
                "silence_shortened_seconds": max(
                    0.0,
                    float(item["sourceDurationSeconds"]) - float(item["outputDurationSeconds"]),
                ),
            }
            for item in clips
        )

    with tempfile.TemporaryDirectory(prefix="longtube-longform-") as temporary_dir:
        temp_root = Path(temporary_dir).resolve()
        overlay_path: Path | None = None
        if str(title or "").strip() or str(channel_name or "").strip():
            overlay_path = create_longform_header_overlay(
                temp_root / "header.png",
                resolution=resolution,
                title=str(title or "").strip(),
                channel_name=str(channel_name or "").strip(),
            )

        encode_semaphore = asyncio.Semaphore(workers)
        progress_lock = asyncio.Lock()
        completed = 0
        use_timestamp_remux = bool(
            stream_copy_compatible_inputs
            and not shorten_silence
            and overlay_path is None
            and all(bool(item["hasAudio"]) for item in clips)
        )
        normalized_paths = [
            temp_root / f"clip_{index:04d}.mkv"
            for index in range(len(clips))
        ]

        async def encode_one(index: int, clip: dict[str, Any]) -> None:
            nonlocal completed
            async with encode_semaphore:
                if use_timestamp_remux:
                    await _remux_clip(clip["path"], normalized_paths[index])
                else:
                    await _render_clip(
                        clip["path"],
                        normalized_paths[index],
                        segments=clip["segments"],
                        resolution=resolution,
                        source_duration=float(clip["sourceDurationSeconds"]),
                        output_duration=float(clip["outputDurationSeconds"]),
                        overlay_path=overlay_path,
                        has_audio=bool(clip["hasAudio"]),
                    )
            async with progress_lock:
                completed += 1
                write_status(
                    "encoding-clips",
                    completedClips=completed,
                    totalClips=len(clips),
                    progress=round(0.05 + (0.90 * completed / len(clips)), 6),
                )

        await asyncio.gather(*(encode_one(index, clip) for index, clip in enumerate(clips)))
        write_status(
            "concatenating",
            completedClips=len(clips),
            totalClips=len(clips),
            progress=0.97,
        )
        joined_pcm = temp_root / "joined_pcm.mkv"
        await _concat_stream_copy(normalized_paths, joined_pcm)
        await _finalize_pcm_timeline(
            joined_pcm,
            output,
            output_duration=(
                sum(int(item["durationInFrames"]) for item in clips)
                / LONGFORM_FPS
            ),
        )

    if not output.is_file() or output.stat().st_size <= 0:
        raise RuntimeError(f"FFmpeg long-form output is missing: {output}")
    write_status(
        "completed",
        completedClips=len(clips),
        totalClips=len(clips),
        progress=1.0,
        outputPath=str(output),
    )
    return str(output)
