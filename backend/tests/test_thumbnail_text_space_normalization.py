import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.thumbnail_service import (  # noqa: E402
    _thumbnail_click_focus_prompt,
    _thumbnail_generation_prompt_for_model,
    _thumbnail_has_complete_layout_contract,
    _thumbnail_style_prompt_from_config,
    build_clickbait_thumbnail_overlay,
    build_standard_thumbnail_prompt,
    generate_ai_thumbnail,
)
from app.services.image.prompt_builder import apply_reference_style_prefix  # noqa: E402


EP01_THUMBNAIL_PROMPT = (
    "Biryu stands shattered outside a thriving Wirye settlement as his former followers "
    "lower a coastal banner and move toward Onjo's gate, early Korean timber palisade, "
    "plain woven clothing, divided crowd, hard dawn side light, strong facial tension, "
    "clear foreground and background separation, clean negative space at upper right for "
    "Korean title text, historically cautious cinematic realism, 35mm lens, 16:9 composition."
)


class ThumbnailTextSpaceNormalizationTests(unittest.TestCase):
    def test_thumbnail_keeps_task_historical_and_anatomy_hard_locks(self) -> None:
        prompt = _thumbnail_style_prompt_from_config(
            "King Muryeong at Garim Fortress.",
            {
                "thumbnail_style_prompt": "Dedicated Baekje thumbnail style.",
                "image_global_prompt": (
                    "Cinematic historical documentary illustration. "
                    "HISTORICAL HARD LOCK: Baekje, Ungjin, 501 CE only. "
                    "No Yamato hall, no Joseon architecture. "
                    "ANATOMY HARD LOCK: every person has natural hands and limbs."
                )
            },
        )

        self.assertTrue(prompt.startswith("Dedicated Baekje thumbnail style."))
        self.assertIn("King Muryeong at Garim Fortress.", prompt)
        self.assertNotIn("HISTORICAL HARD LOCK", prompt)
        self.assertNotIn("ANATOMY HARD LOCK", prompt)

    def test_standard_face_thumbnail_owns_its_complete_layout_contract(self) -> None:
        prompt = build_standard_thumbnail_prompt(
            {
                "thumbnail_prompt": (
                    "Newly crowned King Muryeong ordering the siege of Garim fortress "
                    "where Baek Ga rebels."
                )
            }
        )

        self.assertFalse(_thumbnail_has_complete_layout_contract(prompt))
        self.assertIn("Newly crowned King Muryeong ordering the siege", prompt)
        self.assertNotIn("scroll-stopping", prompt)
        self.assertIn("Landscape 16:9 composition", prompt)

    def test_explicit_korean_hook_is_not_reduced_to_generic_death_label(self) -> None:
        overlay = build_clickbait_thumbnail_overlay(
            {"thumbnail_hook": "왕을 죽인 반역자를 끝장내다"},
            "백제사-EP11: 무령왕의 즉위와 백가의 난 진압",
            {"language": "ko"},
        )

        self.assertIn("반역자", overlay)
        self.assertNotEqual(overlay, "죽음의 순간")

    def test_ep01_uses_only_canonical_lower_left_text_space(self) -> None:
        prompt = _thumbnail_click_focus_prompt(EP01_THUMBNAIL_PROMPT)
        prompt = _thumbnail_click_focus_prompt(prompt)

        self.assertNotIn(
            "clean negative space at upper right for Korean title text",
            prompt,
        )
        self.assertEqual(prompt.count("LOWER-LEFT TEXT-SAFE ZONE LOCK"), 1)
        self.assertIn("THUMBNAIL CLOSE-UP FACE FRAME LOCK", prompt)
        self.assertIn("Single dominant head-and-shoulders portrait", prompt)
        self.assertIn(
            "Put the dominant face on the right half or high upper area",
            prompt,
        )
        self.assertIn(
            "stays blurred, low-detail, secondary, and cannot compete with or replace the face",
            prompt,
        )
        self.assertNotIn("OBJECT OR EVENT THUMBNAIL LOCK", prompt)

        final_prompt = apply_reference_style_prefix(
            prompt,
            False,
            enable_historical_guard=True,
        )
        self.assertIn("THUMBNAIL CLOSE-UP FACE FRAME LOCK", final_prompt)
        self.assertIn("Single dominant head-and-shoulders portrait", final_prompt)
        self.assertNotIn(
            "PRIMARY IMAGE LOCK - first visible subject: the mounted travel moment",
            final_prompt,
        )
        self.assertNotIn("horse-and-rider pair", final_prompt)

    def test_subject_direction_is_preserved_while_text_space_is_removed(self) -> None:
        source = (
            "An ancient queen stands in the upper-right third, clean negative space at "
            "upper left for Korean title text, hard rim light."
        )

        prompt = _thumbnail_click_focus_prompt(source)

        self.assertIn("queen stands in the upper-right third", prompt)
        self.assertNotIn(
            "clean negative space at upper left for Korean title text",
            prompt,
        )
        self.assertIn("LOWER-LEFT TEXT-SAFE ZONE LOCK", prompt)

    def test_uke_mochi_life_thumbnail_uses_covered_mound_event_not_unrelated_face(self) -> None:
        prompt = build_standard_thumbnail_prompt(
            {
                "title": "일본사 시크릿 죽은 여신의 시신에서 피어난 생명 EP.07",
                "topic": "죽은 여신의 시신에서 피어난 생명",
                "thumbnail_prompt": (
                    "Extreme close up, crops erupting from a fallen goddess in a dark forest"
                ),
                "visual_world": {
                    "time_range": "Japanese mythic creation era",
                    "culture_scope": "Kojiki and Nihon Shoki Japanese creation myth",
                },
            }
        )

        lowered = prompt.lower()
        self.assertIn("crops erupting from a fallen goddess", lowered)
        self.assertNotIn("object or event thumbnail lock", lowered)
        self.assertNotIn("life from covered mound event lock", lowered)
        self.assertNotIn("single dominant head-and-shoulders portrait", lowered)
        self.assertIn("landscape 16:9 composition", lowered)


class ThumbnailPromptVerbatimTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_ai_thumbnail_passes_canonical_script_structure_verbatim(self) -> None:
        class FakeImageService:
            model_id = "comfyui-krea2"
            negative_prompt = ""

            def __init__(self) -> None:
                self.received_prompt = ""
                self.compact_thumbnail_prompt = False

            async def generate(
                self,
                prompt: str,
                width: int,
                height: int,
                output_path: str,
                reference_images=None,
            ) -> str:
                self.received_prompt = prompt
                Image.new("RGB", (width, height), (16, 16, 16)).save(output_path)
                return output_path

        canonical_prompt = build_standard_thumbnail_prompt(
            {
                "thumbnail_prompt": (
                    "Newly crowned King Muryeong ordering the siege of mountain-top Garim "
                    "fortress where Baek Ga rebels."
                ),
                "visual_world": {
                    "time_range": "501 AD",
                    "place_scope": "Ungjin and Garimseong Fortress",
                    "culture_scope": "Baekje",
                    "material_culture": "Use documented material culture.",
                    "continuity_rule": "Follow the source workbook scene.",
                },
            }
        )
        fake = FakeImageService()
        with tempfile.TemporaryDirectory() as td, patch(
            "app.services.image.factory.get_image_service",
            return_value=fake,
        ):
            await generate_ai_thumbnail(
                project_id="verbatim-thumbnail-test",
                image_prompt=canonical_prompt,
                image_model_id="comfyui-krea2",
                output_path=str(Path(td) / "thumbnail.png"),
                config={"thumbnail_quality_check": False},
                preserve_image_prompt=True,
            )

        self.assertEqual(fake.received_prompt, canonical_prompt)
        self.assertTrue(canonical_prompt.startswith("Newly crowned King Muryeong"))
        self.assertNotIn("Global visual world:", canonical_prompt)
        self.assertNotIn("THUMBNAIL FACE VISIBILITY LOCK", canonical_prompt)
        self.assertNotIn("LOWER-LEFT TEXT-SAFE ZONE LOCK", canonical_prompt)
        self.assertIn("Landscape 16:9 composition", canonical_prompt)
        self.assertTrue(fake.compact_thumbnail_prompt)


if __name__ == "__main__":
    unittest.main()
