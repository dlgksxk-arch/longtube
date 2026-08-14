import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.image import _product_edit_prompt  # noqa: E402
from app.services import comfyui_client  # noqa: E402
from app.services.image.comfyui_service import (  # noqa: E402
    _QWEN_FAMILY,
    _attach_qwen_edit_reference_nodes,
)
from app.services.image.factory import IMAGE_REGISTRY  # noqa: E402


class QwenProductEditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "qwen_image_edit_2509_text2img_ref.json"
        )
        cls.template = json.loads(workflow_path.read_text(encoding="utf-8"))

    def _render(self, names: list[str]) -> dict:
        graph = comfyui_client.render_workflow(
            self.template,
            {
                "PROMPT": "edit request",
                "NEGATIVE": "low quality",
                "WIDTH": 1024,
                "HEIGHT": 1024,
                "SEED": 1,
                "PREFIX": "longtube/product_edit_test",
                "REF_IMAGE": names[0],
            },
        )
        return _attach_qwen_edit_reference_nodes(graph, names)

    def test_model_is_registered_as_qwen_reference_editor(self):
        model_id = "comfyui-qwen-image-edit-2509"
        self.assertIn(model_id, IMAGE_REGISTRY)
        self.assertIn(model_id, _QWEN_FAMILY)

    def test_model_only_uses_image1_for_clothing_background_edit(self):
        graph = self._render(["model.png"])
        self.assertEqual(graph["5"]["inputs"]["image"], "model.png")
        self.assertEqual(graph["6"]["inputs"]["image1"], ["5", 0])
        self.assertEqual(graph["14"]["class_type"], "FluxKontextImageScale")
        self.assertEqual(graph["14"]["inputs"]["image"], ["5", 0])
        self.assertEqual(graph["8"]["class_type"], "VAEEncode")
        self.assertEqual(graph["8"]["inputs"]["pixels"], ["14", 0])
        self.assertEqual(graph["9"]["inputs"]["latent_image"], ["8", 0])
        self.assertNotIn("image2", graph["6"]["inputs"])
        self.assertNotIn("image3", graph["6"]["inputs"])

        prompt = _product_edit_prompt(
            "검은 정장으로 바꾸고 배경을 호텔 로비로 변경",
            product_count=0,
        )
        self.assertIn("No product reference image was supplied", prompt)
        self.assertIn("clothing and/or background edit", prompt)

    def test_model_and_two_products_use_native_image1_image2_image3(self):
        graph = self._render(["model.png", "product_front.png", "product_side.png"])
        self.assertEqual(graph["5"]["inputs"]["image"], "model.png")
        self.assertEqual(graph["12"]["inputs"]["image"], "product_front.png")
        self.assertEqual(graph["13"]["inputs"]["image"], "product_side.png")
        self.assertEqual(graph["6"]["inputs"]["image2"], ["12", 0])
        self.assertEqual(graph["6"]["inputs"]["image3"], ["13", 0])
        self.assertEqual(graph["7"]["inputs"]["image2"], ["12", 0])
        self.assertEqual(graph["7"]["inputs"]["image3"], ["13", 0])

        prompt = _product_edit_prompt(
            "제품을 자연스럽게 착용",
            product_count=2,
            product_name="테스트 운동화",
        )
        self.assertIn("Images 2 and 3 are product reference images only", prompt)
        self.assertIn("Product name supplied by the user: 테스트 운동화", prompt)

    def test_wearable_product_replaces_existing_item_and_requested_pose_wins(self):
        prompt = _product_edit_prompt(
            "Replace the shorts and change to a three-quarter full-body pose.",
            product_count=2,
            product_name="blue biker shorts",
        )
        self.assertIn("completely replace the existing garment", prompt)
        self.assertIn("do not retain the original item's color", prompt)
        self.assertIn("overrides the source image and must be carried out", prompt)
        self.assertIn("blue biker shorts", prompt)

    def test_more_than_three_inputs_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "at most three"):
            self._render(["model.png", "product1.png", "product2.png", "product3.png"])


if __name__ == "__main__":
    unittest.main()
