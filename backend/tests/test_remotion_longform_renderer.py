import json
from pathlib import Path

import pytest

from app.services import remotion_longform_renderer as renderer


@pytest.mark.asyncio
async def test_shared_longform_manifest_contains_ordered_clips(monkeypatch, tmp_path: Path):
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    output = tmp_path / "merged.mp4"
    manifest = tmp_path / "manifest.json"

    durations = {str(clip_a.resolve()): 1.0, str(clip_b.resolve()): 2.5}

    async def fake_probe(path: str) -> float:
        return durations[path]

    async def fake_run(cmd, **kwargs):
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        Path(payload["renders"][0]["outputPath"]).write_bytes(b"rendered")
        return 0, b"", b""

    monkeypatch.setattr(renderer.FFmpegService, "probe_duration", fake_probe)
    monkeypatch.setattr(renderer, "run_subprocess", fake_run)
    monkeypatch.setattr(renderer, "_find_node", lambda: "node")

    result = await renderer.render_remotion_longform(
        [clip_a, clip_b],
        output,
        resolution="1920x1080",
        title="Test title",
        channel_name="Test channel",
        manifest_path=manifest,
        shorten_silence=False,
    )

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    render = payload["renders"][0]
    assert result == str(output.resolve())
    assert payload["pipeline"] == renderer.SHARED_LONGFORM_PIPELINE_ID
    assert render["assets"] == [str(clip_a.resolve()), str(clip_b.resolve())]
    assert [item["durationInFrames"] for item in render["props"]["clips"]] == [30, 75]
    assert render["props"]["silenceCompressionRatio"] == 1.0
    assert render["props"]["durationInFrames"] == 105
    assert render["props"]["title"] == "Test title"
    assert render["props"]["channelName"] == "Test channel"


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
    # 80ms 안전 여백은 양쪽 대사 구간에 남기고, 내부 무음만 2배속한다.
    assert speech_frames == 64
    assert silence_frames == 28
    assert sum(int(item["durationInFrames"]) for item in segments) == 92


def test_all_main_assembly_call_sites_use_remotion():
    root = Path(__file__).resolve().parents[1]
    sources = [
        root / "app" / "tasks" / "pipeline_tasks.py",
        root / "app" / "routers" / "video.py",
        root / "app" / "routers" / "subtitle.py",
        root / "app" / "routers" / "interlude.py",
    ]
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert "merge_videos_reencode(" not in text, source
        assert "remotion_longform_renderer" in text, source
