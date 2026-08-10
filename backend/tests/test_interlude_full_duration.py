import unittest
from unittest.mock import AsyncMock, patch

from app.routers import interlude as interlude_router
from app.routers import subtitle as subtitle_router
from app.services.interlude_service import ffprobe_duration
from app.services.subtitle_service import (
    generate_ass,
    generate_srt,
    generate_variety_highlight_ass,
)
from app.services.video.ffmpeg_service import FFmpegService


def _two_cut_timeline() -> list[dict]:
    return [
        {
            "cut_number": 10,
            "narration": "첫 번째 핵심입니다.",
            "highlight_caption": "첫 번째 핵심",
            "cut_video_duration": 2.0,
            "actual_duration": 2.0,
        },
        {
            "cut_number": 99,
            "narration": "두 번째 핵심입니다.",
            "highlight_caption": "두 번째 핵심",
            "cut_video_duration": 2.0,
            "actual_duration": 2.0,
        },
    ]


class InterludeTimelineTests(unittest.TestCase):
    def test_ass_uses_full_intermission_duration_in_render_order(self):
        ass = generate_ass(
            _two_cut_timeline(),
            {},
            first_intermission_after_cuts=1,
            intermission_every_cuts=45,
            intermission_duration=10.01,
        )

        self.assertIn("Dialogue: 0,0:00:12.01,0:00:14.01", ass)

    def test_srt_uses_full_opening_and_intermission_durations(self):
        srt = generate_srt(
            _two_cut_timeline(),
            start_offset=10.01,
            first_intermission_after_cuts=1,
            intermission_every_cuts=45,
            intermission_duration=10.01,
        )

        self.assertIn("00:00:10,010 --> 00:00:12,010", srt)
        self.assertIn("00:00:22,020 --> 00:00:24,020", srt)

    def test_variety_overlay_uses_same_intermission_duration(self):
        ass = generate_variety_highlight_ass(
            _two_cut_timeline(),
            first_intermission_after_cuts=1,
            intermission_every_cuts=45,
            intermission_duration=10.01,
        )

        self.assertIn("0:00:12.13", ass)

    def test_empty_cut_before_intermission_still_advances_timeline(self):
        cuts = _two_cut_timeline()
        cuts[0]["narration"] = ""
        ass = generate_ass(
            cuts,
            {},
            first_intermission_after_cuts=1,
            intermission_every_cuts=45,
            intermission_duration=10.01,
        )

        self.assertIn("Dialogue: 0,0:00:12.01,0:00:14.01", ass)

    def test_default_timing_remains_backward_compatible(self):
        cuts = _two_cut_timeline()
        self.assertIn("Dialogue: 0,0:00:02.00,0:00:04.00", generate_ass(cuts, {}))
        self.assertIn("00:00:02,000 --> 00:00:04,000", generate_srt(cuts))


class InterludePreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_compose_does_not_trim_or_pad_intermission(self):
        with patch.object(FFmpegService, "_run_ffmpeg", new=AsyncMock()) as run:
            await interlude_router._prepare_intermission_clip(
                "input.mp4", "output.mp4", "1920x1080"
            )

        cmd = run.await_args.args[0]
        self.assertNotIn("-t", cmd)
        self.assertFalse(any("apad" in str(part) for part in cmd))
        vf = cmd[cmd.index("-vf") + 1]
        self.assertLess(vf.index("fps="), vf.index("scale="))

    async def test_oneclick_render_does_not_trim_or_pad_intermission(self):
        with patch.object(FFmpegService, "_run_ffmpeg", new=AsyncMock()) as run:
            await subtitle_router._prepare_intermission_clip(
                "input.mp4", "output.mp4", "1920x1080"
            )

        cmd = run.await_args.args[0]
        self.assertNotIn("-t", cmd)
        self.assertFalse(any("apad" in str(part) for part in cmd))
        vf = cmd[cmd.index("-vf") + 1]
        self.assertLess(vf.index("fps="), vf.index("scale="))

    async def test_upload_metadata_uses_robust_common_duration_probe(self):
        with patch.object(
            FFmpegService,
            "probe_duration",
            new=AsyncMock(return_value=10.006),
        ) as probe:
            duration = await ffprobe_duration("registered.mp4")

        self.assertEqual(duration, 10.006)
        probe.assert_awaited_once_with("registered.mp4")


if __name__ == "__main__":
    unittest.main()
