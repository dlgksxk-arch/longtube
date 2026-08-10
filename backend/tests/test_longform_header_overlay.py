from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.longform_header import (
    create_longform_header_overlay,
    resolve_longform_channel_name,
    resolve_longform_title,
)


def test_longform_header_uses_registered_channel_names_and_script_title(tmp_path: Path):
    assert resolve_longform_channel_name({}, 1) == "10분역공"
    assert resolve_longform_channel_name({}, 2) == "Scartography"
    assert resolve_longform_channel_name({}, 3) == "闇解き日本史"
    assert resolve_longform_channel_name({}, 4) == "Empire Errors"
    assert resolve_longform_channel_name({"longform_channel_name": "Custom"}, 4) == "Custom"
    assert resolve_longform_title("DB title", {"title": "백제사-EP15: 이전 제목", "topic": "  실제   제목  "}) == "실제 제목"
    assert resolve_longform_title("DB title", {"title": "백제사-EP15: 불교 문화의 황금기"}) == "불교 문화의 황금기"
    assert resolve_longform_title("DB title", {"title": "Ep.10 10,000m 추락 생존자"}) == "10,000m 추락 생존자"

    output = create_longform_header_overlay(
        tmp_path / "header.png",
        resolution="1280x720",
        title="백제사 EP15 불교 문화의 황금기와 전파",
        channel_name="10분역공",
    )
    with Image.open(output) as image:
        assert image.size == (1280, 720)
        assert image.mode == "RGBA"
        alpha = image.getchannel("A")
        assert alpha.crop((0, 0, 850, 150)).getbbox() is not None
        assert alpha.crop((900, 0, 1280, 150)).getbbox() is not None
        assert alpha.crop((0, 250, 1280, 720)).getbbox() is None
        # There is no background plate; only anti-aliased text pixels remain.
        assert alpha.histogram()[128] < 1000
        pixels = image.load()
        assert any(
            pixels[x, y] == (255, 255, 255, 102)
            for x in range(0, 850)
            for y in range(0, 150)
        )
        assert any(
            pixels[x, y] == (255, 210, 74, 102)
            for x in range(900, 1280)
            for y in range(0, 150)
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("cut_count", [2, 21])
async def test_longform_merge_composites_header_in_same_encode(tmp_path: Path, cut_count: int):
    inputs = []
    for index in range(cut_count):
        path = tmp_path / f"cut_{index}.mp4"
        path.write_bytes(b"video")
        inputs.append(str(path))
    overlay = tmp_path / "header.png"
    overlay.write_bytes(b"png")

    with patch.object(FFmpegService, "_run_ffmpeg", new=AsyncMock()) as run:
        await FFmpegService.merge_videos_reencode(
            inputs,
            str(tmp_path / "merged.mp4"),
            overlay_image_path=str(overlay),
        )

    cmd = run.await_args.args[0]
    assert str(overlay) in cmd
    assert "-filter_complex" in cmd
    filter_graph = cmd[cmd.index("-filter_complex") + 1]
    assert "overlay=0:0:shortest=1" in filter_graph
    assert cmd[cmd.index("-preset") + 1] == "medium"
    assert cmd[cmd.index("-crf") + 1] == "16"
