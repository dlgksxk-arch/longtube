from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.video.ffmpeg_service import FFmpegService


@pytest.mark.asyncio
@pytest.mark.parametrize("cut_count", [2, 21])
async def test_longform_merge_uses_high_quality_youtube_encode(
    tmp_path: Path, cut_count: int
):
    inputs = []
    for index in range(cut_count):
        path = tmp_path / f"cut_{index}.mp4"
        path.write_bytes(b"video")
        inputs.append(str(path))

    output = tmp_path / "merged.mp4"
    with patch.object(FFmpegService, "_run_ffmpeg", new=AsyncMock()) as run:
        await FFmpegService.merge_videos_reencode(inputs, str(output))

    cmd = run.await_args.args[0]
    assert cmd[cmd.index("-preset") + 1] == "medium"
    assert cmd[cmd.index("-crf") + 1] == "16"
    assert cmd[cmd.index("-profile:v") + 1] == "high"
    assert cmd[cmd.index("-level:v") + 1] == "4.2"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
