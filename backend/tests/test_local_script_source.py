import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.routers import script as script_router
from app.services.local_script_source import is_local_script_model, load_local_saved_script


class LocalScriptSourceTests(unittest.TestCase):
    def test_local_model_id(self):
        self.assertTrue(is_local_script_model("local-script"))
        self.assertFalse(is_local_script_model("ollama:qwen"))

    def test_loads_saved_manual_script_without_generation(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "script.json").write_text(json.dumps({"cuts": [{"cut_number": 1, "narration": "수동 대본", "image_prompt": "manual scene"}]}), encoding="utf-8")
            with patch("app.services.local_script_source.resolve_project_dir", return_value=root):
                script = load_local_saved_script("project", {})
        self.assertEqual(script["cuts"][0]["narration"], "수동 대본")

    def test_rejects_missing_or_invalid_saved_script(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with patch("app.services.local_script_source.resolve_project_dir", return_value=root):
                with self.assertRaisesRegex(ValueError, "로컬 대본이 없습니다"):
                    load_local_saved_script("project", {})

    def test_registered_prepared_script_precedes_local_script_model(self):
        prepared = {"cuts": [{"cut_number": 1}]}
        with (
            patch.object(script_router, "_load_prepared_script_for_router", return_value=prepared),
            patch.object(script_router, "load_local_saved_script") as local_loader,
        ):
            selected, prepared_used = script_router._load_registered_or_local_script(
                "project",
                {"prepared_script_required": True},
                "topic",
                "local-script",
            )

        self.assertIs(selected, prepared)
        self.assertTrue(prepared_used)
        local_loader.assert_not_called()

    def test_required_prepared_script_never_falls_back_to_local_script(self):
        with (
            patch.object(script_router, "_load_prepared_script_for_router", return_value=None),
            patch.object(script_router, "load_local_saved_script") as local_loader,
        ):
            with self.assertRaisesRegex(RuntimeError, "등록 대본 필수 작업"):
                script_router._load_registered_or_local_script(
                    "project",
                    {"prepared_script_required": True},
                    "topic",
                    "local-script",
                )

        local_loader.assert_not_called()

    def test_local_script_remains_fallback_without_registered_requirement(self):
        local = {"cuts": [{"cut_number": 1}]}
        with (
            patch.object(script_router, "_load_prepared_script_for_router", return_value=None),
            patch.object(script_router, "load_local_saved_script", return_value=local) as local_loader,
        ):
            selected, prepared_used = script_router._load_registered_or_local_script(
                "project",
                {},
                "topic",
                "local-script",
            )

        self.assertIs(selected, local)
        self.assertFalse(prepared_used)
        local_loader.assert_called_once_with("project", {})
