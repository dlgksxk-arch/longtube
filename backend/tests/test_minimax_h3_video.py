from __future__ import annotations

import asyncio
import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.script import _strip_script_motion_prompts  # noqa: E402
from app.routers.subtitle import render_video_with_subtitles  # noqa: E402
from app.services import comfyui_client  # noqa: E402
from app.services.video.factory import VIDEO_REGISTRY  # noqa: E402
from app.services.video.minimax_h3_render import (  # noqa: E402
    prepare_tagged_minimax_h3_raw_videos,
)
from app.services.video.minimax_h3_service import (  # noqa: E402
    build_minimax_h3_i2v_prompt,
)
from app.services.video.prompt_builder import build_video_motion_prompt  # noqa: E402
from app.services.video.minimax_h3_service import MiniMaxH3VideoService  # noqa: E402


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    def query(self, model):
        return _FakeQuery(self._rows)


class MiniMaxH3VideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "minimax_h3_i2v.json"
        )
        cls.template = json.loads(workflow_path.read_text(encoding="utf-8"))

    def test_model_is_registered_with_exact_display_name(self):
        entry = VIDEO_REGISTRY["local-minimax-h3"]
        self.assertEqual(entry["name"], "로컬영상미니맥스")
        self.assertEqual(entry["provider"], "minimax-h3-local")

    def test_service_points_to_isolated_8190_runtime(self):
        from app import config

        self.assertEqual(config.MINIMAX_H3_BASE_URL, "http://127.0.0.1:8190")
        self.assertEqual(Path(config.MINIMAX_H3_ROOT), Path(r"D:\MiniMaxH3"))
        source = inspect.getsource(MiniMaxH3VideoService.generate)
        self.assertNotIn("free_memory", source)
        self.assertNotIn("/free", source)

    def test_workflow_has_no_embedded_image_prompt_or_audio_decode(self):
        graph = comfyui_client.render_workflow(
            self.template,
            {
                "INPUT_IMAGE_NAME": "cut.png",
                "PROMPT": "exact-tag-prompt",
                "WIDTH": 608,
                "HEIGHT": 352,
                "LENGTH": 124,
                "SEED": 7,
                "STEPS": 20,
                "PREFIX": "test/h3",
            },
        )
        self.assertEqual(graph["5"]["inputs"]["prompt"], "exact-tag-prompt")
        self.assertEqual(graph["5"]["inputs"]["first_frame"], ["1", 0])
        self.assertEqual(graph["2"]["inputs"]["unet_name"], "minimax_h3_fl2va_pruned_int8_convrot.safetensors")
        self.assertNotIn("MiniMaxH3VAEDecode", {node["class_type"] for node in graph.values()})

    def test_short_video_tag_is_compiled_to_official_i2va_contract(self):
        result = build_minimax_h3_i2v_prompt("She turns and keeps a fixed stare.")
        self.assertTrue(result.startswith("For the target video, at 0.00 seconds"))
        self.assertIn("integrated_multimodal_description:", result)
        self.assertIn("overall_soundscape: N/A", result)
        self.assertIn("non_diegetic_music: N/A", result)

    def test_complete_official_prompt_is_passed_through(self):
        original = (
            "integrated_multimodal_description: [Shot 1] exact motion\n"
            "overall_soundscape: N/A\n"
            "non_diegetic_music: N/A"
        )
        self.assertEqual(build_minimax_h3_i2v_prompt(original), original)

    def test_selected_minimax_model_uses_video_tag_verbatim(self):
        tag = "She takes one step while the camera tracks left."
        result = build_video_motion_prompt(
            3,
            10,
            {"resolved_video_model": "local-minimax-h3"},
            cut_data={"video_tag": tag, "image_prompt": "unused"},
        )
        self.assertEqual(result, tag)

    def test_script_save_policy_preserves_only_explicit_video_tag(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "video_tag": "  exact movement  ",
                    "motion_prompt": "obsolete",
                    "video_motion_prompt": "obsolete",
                }
            ]
        }
        result = _strip_script_motion_prompts(script)
        self.assertEqual(result["cuts"][0]["video_tag"], "exact movement")
        self.assertNotIn("motion_prompt", result["cuts"][0])
        self.assertNotIn("video_motion_prompt", result["cuts"][0])

    def test_render_places_consecutive_h3_batch_before_subtitle_and_audio_work(self):
        source = inspect.getsource(render_video_with_subtitles)
        h3_index = source.index("prepare_tagged_minimax_h3_raw_videos")
        subtitle_index = source.index("_build_and_write_ass")
        audio_index = source.index("_heal_cut_audio")
        self.assertLess(h3_index, subtitle_index)
        self.assertLess(h3_index, audio_index)

    def test_tagged_cuts_generate_in_order_once_then_use_raw_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            images.mkdir(parents=True)
            for number in (1, 2):
                (images / f"cut_{number}.png").write_bytes(b"image" * 100)
            rows = [
                SimpleNamespace(cut_number=1, image_path="images/cut_1.png"),
                SimpleNamespace(cut_number=2, image_path="images/cut_2.png"),
            ]
            script = {
                "cuts": [
                    {"cut_number": 2, "video_tag": "second motion"},
                    {"cut_number": 1, "video_tag": "first motion"},
                ]
            }

            generated: list[str] = []

            async def fake_generate(**kwargs):
                generated.append(kwargs["prompt"])
                Path(kwargs["output_path"]).write_bytes(b"video" * 500)
                return kwargs["output_path"]

            service = SimpleNamespace(
                prepare_batch=AsyncMock(),
                generate=AsyncMock(side_effect=fake_generate),
            )
            with patch(
                "app.services.video.minimax_h3_render.MiniMaxH3VideoService",
                return_value=service,
            ) as service_class:
                specs = asyncio.run(
                    prepare_tagged_minimax_h3_raw_videos(
                        "project",
                        root,
                        script,
                        _FakeDb(rows),
                        aspect_ratio="16:9",
                    )
                )
                self.assertEqual([spec.cut_number for spec in specs], [1, 2])
                self.assertTrue(all(spec.aspect_ratio == "16:9" for spec in specs))
                self.assertEqual(generated, ["first motion", "second motion"])
                service.prepare_batch.assert_awaited_once()
                self.assertEqual(service.generate.await_count, 2)

                generated.clear()
                specs_again = asyncio.run(
                    prepare_tagged_minimax_h3_raw_videos(
                        "project",
                        root,
                        script,
                        _FakeDb(rows),
                        aspect_ratio="16:9",
                    )
                )
                self.assertEqual([spec.cut_number for spec in specs_again], [1, 2])
                self.assertEqual(generated, [])
                self.assertEqual(service_class.call_count, 1)


if __name__ == "__main__":
    unittest.main()
