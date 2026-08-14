import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.multilingual_caption_service import (  # noqa: E402
    caption_languages_for_config,
    ensure_multilingual_caption_files,
    should_upload_youtube_captions,
    upload_multilingual_captions,
)
from app.config import (  # noqa: E402
    apply_main_caption_delivery_policy,
    should_burn_cut_level_subtitles,
)


class MultilingualCaptionServiceTests(unittest.TestCase):
    def test_cut_subtitle_burn_remains_enabled_for_legacy_projects(self):
        self.assertTrue(should_burn_cut_level_subtitles({}))
        self.assertTrue(should_burn_cut_level_subtitles({"cut_level_subtitles": True}))
        self.assertTrue(should_burn_cut_level_subtitles({"cut_level_subtitles": False}))
        self.assertTrue(should_burn_cut_level_subtitles({"cut_level_subtitles": "false"}))

    def test_factory_v5_youtube_caption_mode_disables_cut_subtitle_burn(self):
        config = apply_main_caption_delivery_policy(
            {
                "factory_version": 5,
                "subtitle_delivery": "youtube_caption",
                "cut_level_subtitles": True,
            }
        )

        self.assertFalse(should_burn_cut_level_subtitles(config))
        self.assertTrue(should_upload_youtube_captions(config))

    def test_main_caption_policy_overrides_legacy_project_settings(self):
        config = apply_main_caption_delivery_policy(
            {
                "language": "ja",
                "cut_level_subtitles": True,
                "subtitle_delivery": "burn",
                "youtube_captions_enabled": False,
                "caption_languages": ["ko", "en"],
            }
        )

        self.assertTrue(config["cut_level_subtitles"])
        self.assertEqual(config["subtitle_delivery"], "burn")
        self.assertFalse(config["youtube_captions_enabled"])
        self.assertTrue(config["variety_highlights_enabled"])
        self.assertEqual(config["variety_highlight_panel_mode"], "emotion_auto")
        self.assertEqual(config["caption_language"], "ja")
        self.assertEqual(config["caption_languages"], ["ja"])
        self.assertFalse(should_upload_youtube_captions({"youtube_captions_enabled": True}))

    def test_caption_languages_follow_config_order_and_aliases(self):
        self.assertEqual(
            caption_languages_for_config({"caption_languages": "english fr spanish german"}),
            ["en", "fr", "es", "de"],
        )

    def test_uses_script_caption_tracks_without_translation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            subtitles_dir = project_dir / "subtitles"
            subtitles_dir.mkdir()
            source = subtitles_dir / "subtitles.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:04,000\nLine one.\n\n"
                "2\n00:00:04,000 --> 00:00:08,000\nLine two.\n",
                encoding="utf-8",
            )
            (project_dir / "script.json").write_text(
                json.dumps(
                    {
                        "cuts": [
                            {
                                "cut_number": 1,
                                "narration": "Line one.",
                                "caption_tracks": {
                                    "fr": "Ligne un.",
                                    "es": "Linea uno.",
                                    "de": "Zeile eins.",
                                },
                            },
                            {
                                "cut_number": 2,
                                "narration": "Line two.",
                                "caption_tracks": {
                                    "fr": "Ligne deux.",
                                    "es": "Linea dos.",
                                    "de": "Zeile zwei.",
                                },
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            result = asyncio.run(
                ensure_multilingual_caption_files(
                    source,
                    {
                        "language": "en",
                        "caption_languages": ["en", "fr", "es", "de"],
                        "caption_source": "script_tracks",
                    },
                )
            )

            self.assertEqual(list(result.keys()), ["en", "fr", "es", "de"])
            self.assertIn("Ligne deux.", Path(result["fr"]).read_text(encoding="utf-8"))
            self.assertIn("Linea dos.", Path(result["es"]).read_text(encoding="utf-8"))
            self.assertIn("Zeile zwei.", Path(result["de"]).read_text(encoding="utf-8"))

    def test_script_track_mode_fails_when_required_track_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            subtitles_dir = project_dir / "subtitles"
            subtitles_dir.mkdir()
            source = subtitles_dir / "subtitles.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:04,000\nLine one.\n",
                encoding="utf-8",
            )
            (project_dir / "script.json").write_text(
                json.dumps({"cuts": [{"cut_number": 1, "narration": "Line one."}]}),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                asyncio.run(
                    ensure_multilingual_caption_files(
                        source,
                        {
                            "language": "en",
                            "caption_languages": ["en", "fr"],
                            "caption_source": "script_tracks",
                        },
                    )
                )

    def test_upload_pipeline_uses_only_primary_channel_language(self):
        class FakeUploader:
            def __init__(self):
                self.languages = []

            def upload_caption(self, video_id, caption_path, language, name):
                self.languages.append(language)
                return {"caption_id": f"caption-{language}", "language": language}

        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp)
            subtitles_dir = project_dir / "subtitles"
            subtitles_dir.mkdir()
            source = subtitles_dir / "subtitles.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:04,000\n"
                "Primary Japanese caption text for the upload policy fixture.\n",
                encoding="utf-8",
            )
            uploader = FakeUploader()

            result = asyncio.run(
                upload_multilingual_captions(
                    uploader,
                    "video-id",
                    source,
                    {
                        "language": "ja",
                        "caption_languages": ["ja", "en", "ko"],
                    },
                )
            )

            self.assertEqual(result["languages"], ["ja"])
            self.assertEqual(uploader.languages, ["ja"])

    def test_upload_pipeline_requires_caption_id(self):
        class FakeUploader:
            def upload_caption(self, video_id, caption_path, language, name):
                return {"caption_id": None, "language": language}

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "subtitles.srt"
            source.write_text(
                "1\n00:00:00,000 --> 00:00:04,000\n"
                "Primary Korean caption text for the validation fixture.\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "caption_id"):
                asyncio.run(
                    upload_multilingual_captions(
                        FakeUploader(),
                        "video-id",
                        source,
                        {"language": "ko"},
                    )
                )


if __name__ == "__main__":
    unittest.main()
