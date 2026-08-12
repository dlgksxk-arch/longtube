import json
from pathlib import Path

import pytest

from app.services import ffmpeg_longform_renderer as renderer


@pytest.mark.asyncio
async def test_shared_ffmpeg_manifest_contains_ordered_clips(monkeypatch, tmp_path: Path):
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    output = tmp_path / "merged.mp4"
    manifest = tmp_path / "manifest.json"

    durations = {str(clip_a.resolve()): 1.0, str(clip_b.resolve()): 2.5}

    async def fake_probe(path: str) -> float:
        return durations[path]

    async def fake_render(source, destination, **kwargs):
        destination.write_bytes(b"normalized")

    async def fake_has_audio(path):
        return True

    async def fake_concat(paths, destination):
        Path(destination).write_bytes(b"merged")

    async def fake_finalize(source, destination, **kwargs):
        Path(destination).write_bytes(b"final")

    monkeypatch.setattr(renderer.FFmpegService, "probe_duration", fake_probe)
    monkeypatch.setattr(renderer, "_render_clip", fake_render)
    monkeypatch.setattr(renderer, "_has_audio_stream", fake_has_audio)
    monkeypatch.setattr(renderer, "_concat_stream_copy", fake_concat)
    monkeypatch.setattr(renderer, "_finalize_pcm_timeline", fake_finalize)

    result = await renderer.render_ffmpeg_longform(
        [clip_a, clip_b],
        output,
        resolution="1920x1080",
        manifest_path=manifest,
        shorten_silence=False,
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert result == str(output.resolve())
    assert payload["pipeline"] == renderer.SHARED_LONGFORM_PIPELINE_ID
    assert payload["assets"] == [str(clip_a.resolve()), str(clip_b.resolve())]
    assert [item["durationInFrames"] for item in payload["props"]["clips"]] == [30, 75]
    assert payload["props"]["silenceCompressionRatio"] == 1.0
    assert payload["props"]["durationInFrames"] == 105
    status = json.loads(Path(f"{manifest}.status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "completed"
    assert status["progress"] == 1.0


def test_longform_silence_segments_are_exactly_half_length():
    segments = renderer._half_silence_segments(4.0, [(1.0, 3.0)])
    speech_frames = sum(
        int(item["durationInFrames"])
        for item in segments
        if float(item["playbackRate"]) == 1.0
    )
    silence_frames = sum(
        int(item["durationInFrames"])
        for item in segments
        if float(item["playbackRate"]) == 2.0
    )
    assert speech_frames == 64
    assert silence_frames == 28
    assert sum(int(item["durationInFrames"]) for item in segments) == 92


def test_ffmpeg_filter_halves_silence_and_composites_header():
    graph, video_output, audio_output = renderer._segment_filter_graph(
        playback_rate=2.0,
        resolution="1920x1080",
        trim_start=0.0,
        trim_end=2.0,
        output_duration=1.0,
        overlay_enabled=True,
    )
    assert "setpts=(PTS-STARTPTS)/2.000000" in graph
    assert "atempo=2.000000" in graph
    assert "overlay=0:0:eof_action=repeat:shortest=0" in graph
    assert video_output == "[vout]"
    assert audio_output == "[aout]"


def test_ffmpeg_filter_can_use_synthetic_audio_input():
    graph, _, _ = renderer._segment_filter_graph(
        playback_rate=1.0,
        resolution="1920x1080",
        trim_start=0.0,
        trim_end=2.0,
        output_duration=2.0,
        overlay_enabled=True,
        audio_input_index=1,
        overlay_input_index=2,
    )
    assert "[1:a]atrim=" in graph
    assert "[vbase][2:v]overlay=" in graph


@pytest.mark.asyncio
async def test_stream_copy_mode_remuxes_compatible_inputs(monkeypatch, tmp_path: Path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"source")
    output = tmp_path / "merged.mp4"

    async def fake_probe(path: str) -> float:
        return 1.0

    async def fake_has_audio(path: Path) -> bool:
        return True

    async def fake_remux(source: Path, destination: Path) -> None:
        destination.write_bytes(b"remuxed")

    async def fail_render(*args, **kwargs):
        raise AssertionError("stream-copy mode must not encode")

    async def fake_concat(paths, destination):
        Path(destination).write_bytes(b"merged")

    async def fake_finalize(source, destination, **kwargs):
        Path(destination).write_bytes(b"final")

    monkeypatch.setattr(renderer.FFmpegService, "probe_duration", fake_probe)
    monkeypatch.setattr(renderer, "_has_audio_stream", fake_has_audio)
    monkeypatch.setattr(renderer, "_remux_clip", fake_remux)
    monkeypatch.setattr(renderer, "_render_clip", fail_render)
    monkeypatch.setattr(renderer, "_concat_stream_copy", fake_concat)
    monkeypatch.setattr(renderer, "_finalize_pcm_timeline", fake_finalize)

    await renderer.render_ffmpeg_longform(
        [clip],
        output,
        shorten_silence=False,
        stream_copy_compatible_inputs=True,
    )

    manifest = json.loads(
        (output.parent / ".merged.ffmpeg-longform.json").read_text(encoding="utf-8")
    )
    assert manifest["props"]["assemblyMode"] == "timestamp-remux"


def test_all_main_assembly_call_sites_use_ffmpeg():
    root = Path(__file__).resolve().parents[1]
    sources = [
        root / "app" / "tasks" / "pipeline_tasks.py",
        root / "app" / "routers" / "video.py",
        root / "app" / "routers" / "subtitle.py",
        root / "app" / "routers" / "interlude.py",
    ]
    combined = "\n".join(source.read_text(encoding="utf-8") for source in sources)
    assert "render_remotion_longform" not in combined
    assert "remotion_longform_renderer" not in combined
    assert "render_ffmpeg_longform" in combined
