import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routers import video as video_router
from app.services.tts.base import probe_audio_duration
from app.tasks import pipeline_tasks


class TTSDurationProbeTests(unittest.TestCase):
    @patch("app.services.tts.base.subprocess.run")
    @patch("app.services.tts.base.shutil.which", return_value=None)
    @patch("app.services.tts.base._resolve_bins", return_value=("ffmpeg-test", "ffprobe"))
    def test_probe_uses_ffmpeg_stderr_when_ffprobe_is_unavailable(
        self,
        _resolve_bins,
        _which,
        run,
    ):
        run.return_value = SimpleNamespace(
            stdout="",
            stderr="Duration: 00:00:04.73, start: 0.000000, bitrate: 64 kb/s",
        )

        self.assertAlmostEqual(probe_audio_duration("cut_2.mp3"), 4.73)
        self.assertEqual(run.call_args.args[0][0], "ffmpeg-test")

    @patch("app.routers.video._probe_media_seconds", return_value=4.73)
    def test_studio_video_timeline_prefers_measured_audio_over_stale_db(self, _probe):
        clip, speech, offset = video_router._timeline_for_audio(
            {
                "cut_duration_mode": "tts_audio",
                "cut_audio_lead_in_sec": 0.5,
                "cut_audio_tail_sec": 0.5,
            },
            2.4,
            4.0,
            "cut_2.mp3",
        )

        self.assertAlmostEqual(speech, 4.73)
        self.assertAlmostEqual(clip, 5.73)
        self.assertAlmostEqual(offset, 0.5)

    @patch("app.tasks.pipeline_tasks._probe_audio_seconds", return_value=2.9)
    def test_pipeline_timeline_preserves_four_second_minimum(self, _probe):
        cut = SimpleNamespace(audio_duration=1.5)
        clip, speech, offset = pipeline_tasks._resolve_cut_timeline_seconds(
            {
                "cut_duration_mode": "tts_audio",
                "cut_audio_lead_in_sec": 0.5,
                "cut_audio_tail_sec": 0.5,
            },
            cut,
            "cut_17.mp3",
            4.0,
        )

        self.assertAlmostEqual(speech, 2.9)
        self.assertAlmostEqual(clip, 4.0)
        self.assertAlmostEqual(offset, 0.5)


if __name__ == "__main__":
    unittest.main()
