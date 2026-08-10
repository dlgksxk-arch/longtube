import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import comfyui_client  # noqa: E402
from app.services.image.comfyui_service import (  # noqa: E402
    _apply_longtube_dark_manhwa_style,
    _z_image_baekje_boat_cargo_close_workflow,
    _z_image_baekje_flat_iron_macro_workflow,
    _z_image_baekje_hinge_close_workflow,
    _z_image_shichishito_branch_impact_workflow,
    _z_image_shichishito_object_workflow,
)


class ZImageTurboHandRefineWorkflowTest(unittest.TestCase):
    def _render(self, filename: str) -> dict:
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / filename
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))
        return comfyui_client.render_workflow(
            template,
            {
                "PROMPT": "hardboiled cartoon scene",
                "NEGATIVE": "malformed anatomy",
                "HAND_REFINE_PROMPT": "one normal adult human hand",
                "HAND_REFINE_NEGATIVE": "extra fingers",
                "WIDTH": 512,
                "HEIGHT": 288,
                "GEN_WIDTH": 576,
                "GEN_HEIGHT": 336,
                "EDGE_CROP_X": 32,
                "EDGE_CROP_Y": 24,
                "SEED": 1,
                "HAND_SEED": 2,
                "BODY_SEED": 3,
                "REF_IMAGE_NAME": "exact_layout.png",
                "REF_MASK_NAME": "side_mask.png",
                "PREFIX": "longtube/test",
            },
        )

    def _assert_connected_hand_inpaint(self, graph: dict) -> None:
        self.assertEqual(graph["11"]["class_type"], "UltralyticsDetectorProvider")
        self.assertEqual(graph["11"]["inputs"]["model_name"], "bbox/hand_yolov8s.pt")
        self.assertEqual(graph["12"]["class_type"], "BboxDetectorSEGS")
        expected_input_image = ["9", 0] if "7" in graph else ["23", 0]
        self.assertEqual(graph["12"]["inputs"]["image"], expected_input_image)
        self.assertEqual(graph["15"]["class_type"], "DetailerForEach")
        self.assertEqual(graph["15"]["inputs"]["image"], expected_input_image)
        self.assertEqual(graph["15"]["inputs"]["segs"], ["12", 0])
        self.assertTrue(graph["15"]["inputs"]["force_inpaint"])
        self.assertTrue(graph["15"]["inputs"]["noise_mask"])
        self.assertEqual(graph["15"]["inputs"]["feather"], 48)
        self.assertEqual(graph["15"]["inputs"]["noise_mask_feather"], 48)
        self.assertEqual(graph["15"]["inputs"]["denoise"], 0.22)
        if "7" in graph:
            self.assertEqual(graph["7"]["inputs"]["width"], 576)
            self.assertEqual(graph["7"]["inputs"]["height"], 336)
        else:
            self.assertEqual(graph["17"]["class_type"], "LoadImage")
            self.assertEqual(graph["17"]["inputs"]["image"], "exact_layout.png")
            self.assertEqual(graph["18"]["class_type"], "ImageScale")
            self.assertEqual(graph["18"]["inputs"]["width"], 576)
            self.assertEqual(graph["18"]["inputs"]["height"], 336)
            self.assertEqual(graph["19"]["class_type"], "VAEEncode")
            self.assertEqual(graph["8"]["inputs"]["latent_image"], ["19", 0])
            self.assertEqual(graph["20"]["inputs"]["image"], "side_mask.png")
            self.assertEqual(graph["21"]["class_type"], "VAEEncodeForInpaint")
            self.assertEqual(graph["22"]["inputs"]["latent_image"], ["21", 0])
            self.assertEqual(graph["23"]["class_type"], "VAEDecode")
        self.assertEqual(graph["16"]["class_type"], "ImageCrop")
        self.assertEqual(graph["16"]["inputs"]["image"], ["15", 0])
        self.assertEqual(graph["16"]["inputs"]["width"], 512)
        self.assertEqual(graph["16"]["inputs"]["height"], 288)
        self.assertEqual(graph["16"]["inputs"]["x"], 32)
        self.assertEqual(graph["16"]["inputs"]["y"], 24)
        self.assertEqual(graph["10"]["inputs"]["images"], ["16", 0])

    def _assert_no_automatic_detection(self, graph: dict, crop_source: list) -> None:
        classes = {node["class_type"] for node in graph.values()}
        self.assertNotIn("UltralyticsDetectorProvider", classes)
        self.assertNotIn("BboxDetectorSEGS", classes)
        self.assertNotIn("DetailerForEach", classes)
        self.assertEqual(graph["16"]["class_type"], "ImageCrop")
        self.assertEqual(graph["16"]["inputs"]["image"], crop_source)
        self.assertEqual(graph["10"]["inputs"]["images"], ["16", 0])

    def test_text2img_saves_base_render_without_automatic_detection(self):
        self._assert_no_automatic_detection(
            self._render("z_image_turbo_text2img.json"),
            ["9", 0],
        )

    def test_ref_compat_saves_base_render_without_automatic_detection(self):
        self._assert_no_automatic_detection(
            self._render("z_image_turbo_text2img_ref.json"),
            ["23", 0],
        )

    def test_shichishito_object_route_skips_second_inpaint_that_adds_extra_swords(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "z_image_turbo_text2img_ref.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))

        graph = _z_image_shichishito_object_workflow(template)

        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.35)
        self.assertEqual(graph["16"]["inputs"]["image"], ["9", 0])
        self.assertEqual(template["16"]["inputs"]["image"], ["23", 0])

    def test_shichishito_branch_impact_route_preserves_registered_collision(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "z_image_turbo_text2img_ref.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))

        graph = _z_image_shichishito_branch_impact_workflow(template)

        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.22)
        self.assertEqual(graph["16"]["inputs"]["image"], ["9", 0])
        self.assertEqual(template["16"]["inputs"]["image"], ["23", 0])

    def test_baekje_boat_cargo_close_route_preserves_tight_reference_layout(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "z_image_turbo_text2img_ref.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))

        graph = _z_image_baekje_boat_cargo_close_workflow(template)

        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.62)
        self.assertEqual(graph["16"]["inputs"]["image"], ["9", 0])
        self.assertEqual(template["16"]["inputs"]["image"], ["23", 0])

    def test_baekje_flat_iron_macro_route_preserves_full_frame_texture(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "z_image_turbo_text2img_ref.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))

        graph = _z_image_baekje_flat_iron_macro_workflow(template)

        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.40)
        self.assertEqual(graph["16"]["inputs"]["image"], ["9", 0])
        self.assertEqual(template["16"]["inputs"]["image"], ["23", 0])

    def test_baekje_hinge_close_route_preserves_full_frame_crop(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "z_image_turbo_text2img_ref.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))

        graph = _z_image_baekje_hinge_close_workflow(template)

        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.62)
        self.assertEqual(graph["16"]["inputs"]["image"], ["9", 0])
        self.assertEqual(template["16"]["inputs"]["image"], ["23", 0])

    def test_three_portrait_layout_uses_img2img_without_automatic_detection(self):
        graph = self._render("z_image_turbo_portrait_layout_ref.json")
        self.assertEqual(graph["17"]["class_type"], "LoadImage")
        self.assertEqual(graph["17"]["inputs"]["image"], "exact_layout.png")
        self.assertEqual(graph["19"]["class_type"], "VAEEncode")
        self.assertEqual(graph["8"]["inputs"]["latent_image"], ["19", 0])
        self.assertEqual(graph["8"]["inputs"]["denoise"], 0.15)
        self.assertEqual(graph["20"]["inputs"]["image"], "side_mask.png")
        self.assertEqual(graph["21"]["class_type"], "VAEEncodeForInpaint")
        self.assertEqual(graph["22"]["inputs"]["latent_image"], ["21", 0])
        self.assertEqual(graph["23"]["class_type"], "VAEDecode")
        self.assertEqual(graph["24"]["class_type"], "ImageCompositeMasked")
        self.assertEqual(graph["24"]["inputs"]["destination"], ["18", 0])
        self.assertEqual(graph["24"]["inputs"]["source"], ["23", 0])
        self._assert_no_automatic_detection(graph, ["24", 0])

    def test_base_routes_negative_cfg_and_saved_output_through_hand_detailer(self):
        for filename in (
            "z_image_base_text2img.json",
            "z_image_base_text2img_ref.json",
        ):
            with self.subTest(filename=filename):
                graph = self._render(filename)
                self._assert_connected_hand_inpaint(graph)
                self.assertEqual(graph["1"]["inputs"]["unet_name"], "z_image_bf16.safetensors")
                self.assertEqual(graph["6"]["inputs"]["text"], "malformed anatomy")
                self.assertEqual(graph["8"]["inputs"]["negative"], ["6", 0])
                self.assertEqual(graph["8"]["inputs"]["steps"], 50)
                self.assertEqual(graph["8"]["inputs"]["cfg"], 4.0)
                self.assertEqual(graph["15"]["inputs"]["steps"], 28)
                self.assertEqual(graph["15"]["inputs"]["cfg"], 4.0)

    def test_z_image_uses_dark_ink_dominant_hardboiled_style(self):
        styled = _apply_longtube_dark_manhwa_style(
            "historical scene",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("Z-IMAGE DARK HARD-BOILED HISTORICAL MANHWA STYLE LOCK", styled)
        self.assertIn("thick irregular black outer contours", styled)
        self.assertIn("aggressive dense cross-hatching", styled)
        self.assertIn("one quarter to one third of the frame", styled)
        self.assertIn("Historical accuracy outranks style", styled)
        self.assertIn("Broad irregular local ground and sky texture continues naturally", styled)
        self.assertNotIn("abstract black brush slashes", styled)
        self.assertNotIn("building", styled)
        self.assertNotIn("horror-western", styled)

    def test_z_image_base_uses_same_dark_ink_dominant_style(self):
        styled = _apply_longtube_dark_manhwa_style(
            "historical scene",
            model_id="comfyui-z-image-base",
        )

        self.assertIn("Z-IMAGE DARK HARD-BOILED HISTORICAL MANHWA STYLE LOCK", styled)
        self.assertIn("Historical accuracy outranks style", styled)

    def test_z_image_scene_contract_puts_visible_action_before_style_lock(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Style: dramatic historical documentary. Visible action: exactly three unarmed "
            "historians speak in one quiet room. Peaceful background staging: every secondary "
            "person is sparse, stationary, unarmed, calm, and directly relevant to the named "
            "setting. Body integrity: every visible arm connects to one shoulder. "
            "Historical setting: early Baekje.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertTrue(styled.startswith("exactly three unarmed historians"))
        self.assertLess(
            styled.index("exactly three unarmed historians"),
            styled.index("Z-IMAGE DARK HARD-BOILED HISTORICAL MANHWA STYLE LOCK"),
        )
        self.assertNotIn("Style: dramatic historical documentary", styled)
        self.assertIn("Body integrity:", styled)

    def test_z_image_object_only_style_does_not_seed_people_or_western_costume(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Primary subject: object-only archaeological model. Composition: object-only close view",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn(
            "Z-IMAGE DARK HARD-BOILED HISTORICAL MANHWA OBJECT STYLE LOCK",
            styled,
        )
        self.assertIn("Only the exact named items and their local ground material", styled)
        self.assertIn("Broad irregular local ground texture continues naturally", styled)
        self.assertNotIn("Adult faces are", styled)

    def test_z_image_landscape_only_style_does_not_seed_people(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Primary subject: landscape-only prehistoric river valley.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn(
            "Z-IMAGE DARK HARD-BOILED HISTORICAL MANHWA LANDSCAPE STYLE LOCK",
            styled,
        )
        self.assertIn("the environment remains completely unoccupied", styled)
        self.assertNotIn("Adult faces are", styled)


if __name__ == "__main__":
    unittest.main()
