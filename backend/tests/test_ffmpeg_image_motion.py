from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.config import (
    should_burn_cut_level_subtitles,
    should_burn_variety_highlights,
)
from app.services import shorts_service
from app.services.subtitle_service import explicit_variety_highlight_caption
from app.services.video.factory import get_video_service
from app.services.video.ffmpeg_service import (
    FFmpegImageMotionService,
    FFmpegService,
)


def test_image_motion_cycles_through_eight_smooth_profiles(tmp_path: Path):
    labels = []
    graphs = []
    for cut_number in range(1, 9):
        graph, label = FFmpegImageMotionService.motion_filter(
            image_path=str(tmp_path / f"cut_{cut_number}.png"),
            prompt="slow historical scene motion",
            duration=5.0,
            aspect_ratio="16:9",
        )
        labels.append(label)
        graphs.append(graph)

    assert len(set(labels)) == 8
    assert len(set(graphs)) == 8
    assert all("zoompan=" in graph for graph in graphs)
    assert all(":d=1:" in graph for graph in graphs)
    assert all("fps=30" in graph for graph in graphs)
    assert all("sin(" not in graph and "cos(" not in graph for graph in graphs)


@pytest.mark.asyncio
async def test_image_motion_generate_uses_oversampled_zoompan(tmp_path: Path):
    image = tmp_path / "cut_5.png"
    image.write_bytes(b"image")
    output = tmp_path / "cut_5.mp4"
    service = FFmpegImageMotionService()

    with patch.object(FFmpegService, "_run_ffmpeg", new=AsyncMock()) as run:
        result = await service.generate(
            image_path=str(image),
            duration=4.0,
            output_path=str(output),
            aspect_ratio="16:9",
            prompt="close-up",
        )

    assert result == str(output)
    cmd = run.await_args.args[0]
    graph = cmd[cmd.index("-filter_complex") + 1]
    assert "scale=3840:2160" in graph
    assert "s=1920x1080:fps=30" in graph
    assert "zoompan=" in graph
    assert "-an" in cmd


def test_video_factory_exposes_image_motion_service():
    service = get_video_service("ffmpeg-image-motion")

    assert isinstance(service, FFmpegImageMotionService)
    assert service.model_id == "ffmpeg-image-motion"


def test_shorts_requires_videoized_cut_concat_without_timeline_fallback():
    source = Path(shorts_service.__file__).read_text(encoding="utf-8")

    assert "videoized cut assembly failed" in source
    assert "image/timeline fallback is disabled" in source
    assert "_timeline_short_" not in source
    assert '"source_clip_type": "videoized-cut-concat"' in source


def test_shorts_prefers_minimax_videoized_cut_over_static_base(tmp_path: Path):
    output_dir = tmp_path / "output"
    video_dir = tmp_path / "videos"
    minimax_dir = video_dir / "minimax_h3"
    output_dir.mkdir()
    minimax_dir.mkdir(parents=True)
    base = video_dir / "cut_21.mp4"
    videoized = minimax_dir / "cut_021.mp4"
    base.write_bytes(b"static-base")
    videoized.write_bytes(b"minimax-video")

    assert shorts_service._cut_video_path(output_dir, 21) == videoized


def test_variety_captions_are_independent_from_youtube_caption_delivery():
    config = {
        "factory_version": 5,
        "subtitle_delivery": "youtube_caption",
        "variety_highlights_enabled": True,
    }

    assert should_burn_cut_level_subtitles(config) is False
    assert should_burn_variety_highlights(config) is True


@pytest.mark.parametrize("caption", ["첫 번째 강조", "두 번째 강조", "세 번째 강조"])
def test_every_nonempty_authored_variety_caption_is_kept(caption: str):
    assert explicit_variety_highlight_caption({"highlight_caption": caption}) == caption
