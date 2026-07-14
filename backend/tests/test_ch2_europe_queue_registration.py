import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ch2_register_europe_queue import (  # noqa: E402
    CH2_ENGLISH_VOICE_ID,
    EXPECTED_EPISODE_CODES,
    EXPECTED_QUEUE_HEADER,
    QUEUE_EP_RE,
    SERIES_NAME,
    TEMPLATE_PROJECT_ID,
    _english_only_script_errors,
    _english_only_project_config,
    _manifest_file_index,
    _queue_item,
    _registration_state,
)
from scripts.ch2_europe_workbook_to_prepared_scripts import SCRIPT_VERSION  # noqa: E402


class Ch2EuropeQueueRegistrationTests(unittest.TestCase):
    def test_queue_item_matches_prepared_script_identity(self):
        item = _queue_item(
            episode_number=178,
            episode_code="EP178",
            title="Russia's Invasion of Ukraine and the Remaking of European Security",
            queued_at="2026-07-10T00:00:00Z",
        )
        self.assertEqual(item["id"], "ch2-europe-ep178")
        self.assertEqual(item["episode_code"], "EP178")
        self.assertEqual(item["episode_id"], "EP178")
        self.assertEqual(item["template_project_id"], TEMPLATE_PROJECT_ID)
        self.assertEqual(item["series"], SERIES_NAME)
        self.assertEqual(item["channel"], 2)
        self.assertEqual(item["status"], "pending")
        self.assertIn("[Audio] English", item["core_content"])
        self.assertIn("[Captions] English", item["core_content"])
        self.assertNotIn("French", item["core_content"])
        self.assertNotIn("Spanish", item["core_content"])
        self.assertNotIn("German", item["core_content"])

    def test_queue_sheet_contract_matches_179_episode_design(self):
        self.assertEqual(len(EXPECTED_QUEUE_HEADER), 22)
        self.assertEqual(QUEUE_EP_RE.fullmatch("유럽사 시크릿-EP001").group(1), "001")
        self.assertEqual(QUEUE_EP_RE.fullmatch("유럽사 시크릿-EP179").group(1), "179")
        self.assertIsNone(QUEUE_EP_RE.fullmatch("EP001"))

    def test_english_only_script_contract_accepts_only_en_track(self):
        script = {
            "language": "en",
            "caption_languages": ["en"],
            "caption_source": "script_tracks",
            "cuts": [
                {
                    "narration": "This is the English narration.",
                    "caption_tracks": {"en": "This is the English narration."},
                }
            ],
        }
        self.assertEqual(_english_only_script_errors(script), [])

    def test_english_only_script_contract_rejects_extra_tracks_and_cjk(self):
        script = {
            "language": "en",
            "caption_languages": ["en", "fr"],
            "caption_source": "script_tracks",
            "cuts": [
                {
                    "narration": "영어가 아닙니다.",
                    "caption_tracks": {
                        "en": "영어가 아닙니다.",
                        "fr": "Ce texte ne doit pas exister.",
                    },
                }
            ],
        }
        errors = _english_only_script_errors(script)
        self.assertIn("caption_languages must be ['en']", errors)
        self.assertIn("cut 1: caption_tracks must contain only en", errors)

    def test_project_config_enforces_english_audio_and_single_caption_track(self):
        configured = _english_only_project_config(
            {
                "language": "ko",
                "tts_voice_lang": "ko",
                "tts_voice_id": "",
                "caption_languages": ["en", "fr", "es", "de"],
                "youtube_localization_languages": ["fr", "es", "de"],
            }
        )
        self.assertEqual(configured["language"], "en")
        self.assertEqual(configured["tts_voice_lang"], "en")
        self.assertEqual(configured["tts_voice_id"], CH2_ENGLISH_VOICE_ID)
        self.assertEqual(configured["caption_languages"], ["en"])
        self.assertEqual(configured["caption_source"], "script_tracks")
        self.assertTrue(configured["youtube_captions_enabled"])
        self.assertEqual(
            configured["youtube_localization_languages"], ["fr", "es", "de"]
        )

    def test_manifest_contract_requires_179_english_files(self):
        files = [
            {
                "episode_code": code,
                "file": f"{code}.json",
                "sha256": "A" * 64,
                "cuts": 150,
            }
            for code in sorted(EXPECTED_EPISODE_CODES)
        ]
        manifest = {
            "script_version": SCRIPT_VERSION,
            "language": "en",
            "caption_languages": ["en"],
            "episode_count": 179,
            "cut_count": 26850,
            "sources": [],
            "files": files,
        }
        with patch(
            "scripts.ch2_register_europe_queue.EXPECTED_SOURCE_NAMES", set()
        ):
            file_index, source_index, errors = _manifest_file_index(manifest)
        self.assertEqual(errors, [])
        self.assertEqual(set(file_index), EXPECTED_EPISODE_CODES)
        self.assertEqual(source_index, {})

    def test_manifest_contract_verifies_source_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "source.xlsx"
            source_path.write_bytes(b"source workbook bytes")
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest().upper()
            manifest = {
                "script_version": SCRIPT_VERSION,
                "language": "en",
                "caption_languages": ["en"],
                "episode_count": 179,
                "cut_count": 26850,
                "sources": [
                    {
                        "path": str(source_path),
                        "sha256": digest,
                        "episode_count": 2,
                        "first_episode": 1,
                        "last_episode": 2,
                    }
                ],
                "files": [
                    {
                        "episode_code": code,
                        "file": f"{code}.json",
                        "sha256": "B" * 64,
                        "cuts": 150,
                    }
                    for code in sorted(EXPECTED_EPISODE_CODES)
                ],
            }
            with (
                patch(
                    "scripts.ch2_register_europe_queue.EXPECTED_SOURCE_NAMES",
                    {"source.xlsx"},
                ),
                patch(
                    "scripts.ch2_register_europe_queue.EXPECTED_SOURCE_RANGES",
                    {"source.xlsx": (1, 2)},
                ),
            ):
                _file_index, source_index, errors = _manifest_file_index(manifest)
        self.assertEqual(errors, [])
        self.assertEqual(set(source_index), {"source.xlsx"})

    def test_registration_preserves_other_channels_and_disables_ch2_schedule(self):
        current = {
            "channel_times": {"1": "03:00", "2": "04:00"},
            "last_run_dates": {"1": "2026-07-13", "2": "2026-07-12"},
            "channel_presets": {"1": "ch1", "2": "old"},
            "future_runtime_field": {"preserve": True},
            "items": [
                {"id": "keep", "channel": 1, "topic": "Keep", "status": "pending"},
                {"id": "replace", "channel": 2, "topic": "Old", "status": "pending"},
            ],
        }
        new_item = _queue_item(
            episode_number=1,
            episode_code="EP001",
            title="Title",
            queued_at="2026-07-10T00:00:00Z",
        )
        state, errors = _registration_state(current, [new_item])
        self.assertEqual(errors, [])
        self.assertEqual([item["id"] for item in state["items"]], ["keep", "ch2-europe-ep001"])
        self.assertIsNone(state["channel_times"]["2"])
        self.assertEqual(state["channel_presets"]["2"], TEMPLATE_PROJECT_ID)
        self.assertEqual(state["last_run_dates"], current["last_run_dates"])
        self.assertEqual(state["future_runtime_field"], {"preserve": True})


if __name__ == "__main__":
    unittest.main()
