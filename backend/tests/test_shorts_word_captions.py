import asyncio
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import shorts_service  # noqa: E402
from app.services.tts.alignment import (  # noqa: E402
    alignment_sidecar_path,
    write_alignment_sidecar,
)
from app.services.tts.elevenlabs_service import ElevenLabsService  # noqa: E402
from app.services.remotion_shorts_renderer import (  # noqa: E402
    SHARED_SHORTS_PIPELINE_ID,
    render_remotion_shorts,
)


def _character_alignment(text: str, step: float = 0.1) -> dict:
    return {
        "characters": list(text),
        "character_start_times_seconds": [round(index * step, 3) for index in range(len(text))],
        "character_end_times_seconds": [round((index + 1) * step, 3) for index in range(len(text))],
    }


class ShortsWordCaptionTests(unittest.TestCase):
    def test_shared_renderer_rejects_channel_specific_or_legacy_props(self):
        with self.assertRaisesRegex(RuntimeError, "invalid pipelineId"):
            asyncio.run(render_remotion_shorts(
                [{"props": {"pipelineId": "channel-1-special"}}],
                manifest_path=Path("unused.json"),
            ))

    def test_shared_pipeline_contract_is_wired_at_the_only_production_callsite(self):
        root = Path(__file__).resolve().parents[2]
        router_source = (root / "backend" / "app" / "routers" / "subtitle.py").read_text(
            encoding="utf-8"
        )
        service_source = (root / "backend" / "app" / "services" / "shorts_service.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(SHARED_SHORTS_PIPELINE_ID, "shared-all-channels-3word-captions-v2")
        self.assertIn("render_shorts_from_final(", router_source)
        self.assertIn('"pipeline_id": SHARED_SHORTS_PIPELINE_ID', service_source)
        self.assertIn('"pipelineId": SHARED_SHORTS_PIPELINE_ID', service_source)

    def test_caption_style_uses_seventy_percent_white_background_below_image(self):
        source = (
            Path(__file__).resolve().parents[2]
            / "remotion-shorts"
            / "src"
            / "ShortsComposition.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn('backgroundColor: "rgba(255,255,255,0.7)"', source)
        self.assertIn("const CAPTION_TOP = CLIP_TOP + CLIP_HEIGHT + 16", source)
        self.assertIn("top: CAPTION_TOP", source)
        self.assertNotIn("top: 1040", source)

    def test_three_word_groups_follow_alignment_and_final_speed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "audio").mkdir()
            audio = project / "audio" / "cut_001.mp3"
            audio.write_bytes(b"audio")
            text = "하나 둘 셋 넷 다섯 여섯"
            alignment = _character_alignment(text)
            write_alignment_sidecar(
                audio,
                text=text,
                alignment=alignment,
                normalized_alignment=alignment,
                provider="elevenlabs",
                model_id="eleven_v3",
            )
            script = {
                "cuts": [
                    {"cut_number": 1, "narration": text, "audio_duration": 2.0},
                ]
            }

            cues = shorts_service._build_short_caption_cues(
                script,
                [1],
                project / "output",
                [{"start": 0.0, "end": 2.0}],
                1.2,
            )

            self.assertEqual([cue["text"] for cue in cues], ["하나 둘 셋", "넷 다섯 여섯"])
            self.assertEqual(cues[0]["startFrame"], 0)
            self.assertGreater(cues[1]["startFrame"], cues[0]["startFrame"])
            self.assertLessEqual(cues[-1]["endFrame"], 50)

    def test_caption_span_is_remapped_across_removed_silence(self):
        mapped = shorts_service._map_caption_span_to_output(
            0.5,
            2.5,
            [{"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 3.0}],
            1.2,
        )

        self.assertIsNotNone(mapped)
        start, end = mapped or (0.0, 0.0)
        self.assertAlmostEqual(start, 0.5 / 1.2, places=6)
        self.assertAlmostEqual(end, 1.5 / 1.2, places=6)

    def test_existing_audio_without_sidecar_still_groups_three_words(self):
        timings = shorts_service._alignment_word_timings(
            Path("missing.mp3"),
            "one two three four",
            4.0,
        )

        self.assertEqual([item["text"] for item in timings], ["one", "two", "three", "four"])
        self.assertEqual(timings[0]["start"], 0.0)
        self.assertEqual(timings[-1]["end"], 4.0)

    def test_caption_offsets_use_measured_cut_video_durations(self):
        script = {
            "cuts": [
                {"cut_number": 1, "narration": "one two three", "audio_duration": 1.0},
                {"cut_number": 2, "narration": "four five six", "audio_duration": 1.0},
            ]
        }

        cues = shorts_service._build_short_caption_cues(
            script,
            [1, 2],
            Path("project/output"),
            [{"start": 0.0, "end": 5.0}],
            1.0,
            {1: 2.0, 2: 3.0},
        )

        self.assertEqual(cues[0]["text"], "one two three")
        self.assertEqual(cues[1]["text"], "four five six")
        self.assertEqual(cues[1]["startFrame"], 60)


class ElevenLabsTimestampTests(unittest.TestCase):
    def test_generate_writes_audio_and_alignment_sidecar(self):
        text = "one two three"
        alignment = _character_alignment(text)
        response_payload = {
            "audio_base64": base64.b64encode(b"fake-mp3").decode("ascii"),
            "alignment": alignment,
            "normalized_alignment": alignment,
        }
        calls = []

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return response_payload

        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, **kwargs):
                calls.append((url, kwargs))
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cut_001.mp3"
            service = ElevenLabsService()
            with (
                mock.patch("app.services.tts.elevenlabs_service.httpx.AsyncClient", FakeClient),
                mock.patch.object(service, "_get_duration", return_value=1.3),
                mock.patch("app.services.tts.elevenlabs_service.config.get_runtime_api_key", return_value="test-key"),
            ):
                result = asyncio.run(service.generate(text, "voice-id", str(output)))

            self.assertEqual(output.read_bytes(), b"fake-mp3")
            self.assertEqual(result["duration"], 1.3)
            self.assertTrue(calls[0][0].endswith("/text-to-speech/voice-id/with-timestamps"))
            sidecar = json.loads(alignment_sidecar_path(output).read_text(encoding="utf-8"))
            self.assertEqual(sidecar["text"], text)
            self.assertEqual(sidecar["alignment"]["characters"], list(text))


if __name__ == "__main__":
    unittest.main()
