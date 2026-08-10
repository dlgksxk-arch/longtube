import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import comfyui_client  # noqa: E402
from app.services.image.comfyui_service import (  # noqa: E402
    ComfyUIImageService,
    _history_int_output,
)
from app.services.image.prompt_compiler import SCENE_CONTRACT_V2  # noqa: E402


class Flux2Klein4BSafeWorkflowTest(unittest.TestCase):
    def test_history_int_output_reads_rgthree_display_payload(self):
        entry = {"outputs": {"33": {"ui": {"text": ["3"]}}}}
        self.assertEqual(_history_int_output(entry, "33"), 3)
        self.assertIsNone(_history_int_output(entry, "missing"))

    def test_flux2_klein_4b_workflow_refines_body_then_hands_and_checks_final_output(self):
        workflow_path = (
            Path(__file__).resolve().parent.parent
            / "workflows"
            / "comfyui"
            / "flux2_klein_4b_text2img.json"
        )
        template = json.loads(workflow_path.read_text(encoding="utf-8"))
        graph = comfyui_client.render_workflow(
            template,
            {
                "PROMPT": "scene prompt",
                "NEGATIVE": "negative prompt",
                "HAND_REFINE_PROMPT": "hand refine prompt",
                "HAND_REFINE_NEGATIVE": "hand refine negative",
                "BODY_REFINE_PROMPT": "body refine prompt",
                "BODY_REFINE_NEGATIVE": "body refine negative",
                "WIDTH": 512,
                "HEIGHT": 288,
                "SEED": 1,
                "HAND_SEED": 2,
                "BODY_SEED": 3,
                "PREFIX": "longtube/test",
            },
        )

        self.assertEqual(graph["14"]["class_type"], "UltralyticsDetectorProvider")
        self.assertEqual(graph["14"]["inputs"]["model_name"], "bbox/hand_yolov8s.pt")
        self.assertEqual(graph["15"]["class_type"], "BboxDetectorSEGS")
        self.assertEqual(graph["15"]["inputs"]["image"], ["30", 0])
        self.assertEqual(graph["16"]["class_type"], "SegsToCombinedMask")
        self.assertEqual(graph["17"]["class_type"], "VAEEncodeForInpaint")
        self.assertEqual(graph["17"]["inputs"]["pixels"], ["30", 0])
        self.assertEqual(graph["18"]["class_type"], "SetLatentNoiseMask")
        self.assertEqual(graph["19"]["inputs"]["text"], "hand refine prompt")
        self.assertEqual(graph["20"]["inputs"]["text"], "hand refine negative")
        self.assertEqual(graph["13"]["inputs"]["images"], ["31", 0])
        self.assertEqual(graph["25"]["class_type"], "VAEDecode")
        self.assertEqual(graph["31"]["class_type"], "DetailerForEach")
        self.assertEqual(graph["31"]["inputs"]["image"], ["30", 0])
        self.assertEqual(graph["31"]["inputs"]["segs"], ["15", 0])
        self.assertEqual(graph["31"]["inputs"]["denoise"], 0.22)
        self.assertEqual(graph["31"]["inputs"]["feather"], 48)
        self.assertEqual(graph["31"]["inputs"]["noise_mask_feather"], 48)
        self.assertEqual(graph["26"]["class_type"], "UltralyticsDetectorProvider")
        self.assertEqual(graph["26"]["inputs"]["model_name"], "segm/person_yolov8m-seg.pt")
        self.assertEqual(graph["27"]["class_type"], "SegmDetectorSEGS")
        self.assertEqual(graph["27"]["inputs"]["segm_detector"], ["26", 1])
        self.assertEqual(graph["27"]["inputs"]["image"], ["12", 0])
        self.assertEqual(graph["28"]["inputs"]["text"], "body refine prompt")
        self.assertEqual(graph["29"]["inputs"]["text"], "body refine negative")
        self.assertEqual(graph["30"]["class_type"], "DetailerForEach")
        self.assertEqual(graph["30"]["inputs"]["image"], ["12", 0])
        self.assertEqual(graph["30"]["inputs"]["segs"], ["27", 0])
        self.assertEqual(graph["30"]["inputs"]["denoise"], 0.14)
        self.assertEqual(graph["30"]["inputs"]["feather"], 48)
        self.assertEqual(graph["30"]["inputs"]["noise_mask_feather"], 48)
        self.assertEqual(graph["44"]["class_type"], "SegmDetectorSEGS")
        self.assertEqual(graph["44"]["inputs"]["segm_detector"], ["26", 1])
        self.assertEqual(graph["44"]["inputs"]["image"], ["31", 0])
        self.assertEqual(graph["32"]["class_type"], "ImpactCount_Elts_in_SEGS")
        self.assertEqual(graph["32"]["inputs"]["segs"], ["44", 0])
        self.assertEqual(graph["33"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["33"]["inputs"]["input"], ["32", 0])
        self.assertEqual(graph["34"]["class_type"], "UltralyticsDetectorProvider")
        self.assertEqual(graph["34"]["inputs"]["model_name"], "bbox/face_yolov8m.pt")
        self.assertEqual(graph["35"]["class_type"], "BboxDetectorSEGS")
        self.assertEqual(graph["35"]["inputs"]["bbox_detector"], ["34", 0])
        self.assertEqual(graph["35"]["inputs"]["image"], ["31", 0])
        self.assertEqual(graph["36"]["class_type"], "ImpactCount_Elts_in_SEGS")
        self.assertEqual(graph["36"]["inputs"]["segs"], ["35", 0])
        self.assertEqual(graph["37"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["37"]["inputs"]["input"], ["36", 0])
        self.assertEqual(graph["38"]["class_type"], "SegmDetectorSEGS")
        self.assertEqual(graph["38"]["inputs"]["segm_detector"], ["26", 1])
        self.assertEqual(graph["38"]["inputs"]["image"], ["31", 0])
        self.assertEqual(graph["38"]["inputs"]["threshold"], 0.25)
        self.assertEqual(graph["38"]["inputs"]["drop_size"], 32)
        self.assertEqual(graph["39"]["class_type"], "ImpactCount_Elts_in_SEGS")
        self.assertEqual(graph["39"]["inputs"]["segs"], ["38", 0])
        self.assertEqual(graph["40"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["40"]["inputs"]["input"], ["39", 0])
        self.assertEqual(graph["41"]["inputs"]["image"], ["31", 0])
        self.assertEqual(graph["45"]["class_type"], "UltralyticsDetectorProvider")
        self.assertEqual(graph["45"]["inputs"]["model_name"], "bbox/yolov8m.pt")
        self.assertEqual(graph["46"]["class_type"], "BboxDetectorSEGS")
        self.assertEqual(graph["46"]["inputs"]["bbox_detector"], ["45", 0])
        self.assertEqual(graph["46"]["inputs"]["image"], ["31", 0])
        self.assertEqual(graph["46"]["inputs"]["labels"], "cow")
        self.assertEqual(graph["47"]["class_type"], "ImpactCount_Elts_in_SEGS")
        self.assertEqual(graph["47"]["inputs"]["segs"], ["46", 0])
        self.assertEqual(graph["48"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["48"]["inputs"]["input"], ["47", 0])

        for node_id in ("10", "23", "30", "31"):
            self.assertEqual(graph[node_id]["inputs"]["cfg"], 1.0)

    def test_scene_contract_v2_missing_final_hand_result_deletes_output_and_fails_closed(self):
        async def write_output(_entry, output_path, **_kwargs):
            from PIL import Image

            Image.new("RGB", (64, 36), (120, 120, 120)).save(output_path)

        service = ComfyUIImageService("comfyui-flux2-klein-4b")
        service.prompt_profile = SCENE_CONTRACT_V2
        source = (
            "Year/period: 668 AD; Exact place: Pyongyang rampart; "
            "Main subject: exactly one adult Goguryeo archer; "
            "Scene: One waist-up archer grips one recurved bow with exactly two visible hands."
        )

        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "cut.png")
            with (
                patch(
                    "app.services.image.comfyui_service.comfyui_client.system_stats",
                    new=AsyncMock(return_value={}),
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.submit",
                    new=AsyncMock(return_value="prompt-id"),
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.wait_for",
                    new=AsyncMock(
                        return_value={
                            "outputs": {
                                "33": {"ui": {"text": ["1"]}},
                                "37": {"ui": {"text": ["1"]}},
                            }
                        }
                    ),
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.download_first_output",
                    new=AsyncMock(side_effect=write_output),
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.execution_seconds",
                    return_value=None,
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.cached_node_count",
                    return_value=0,
                ),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.new_client_id",
                    return_value="client-id",
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    r"최종 검출 결과 누락: final hand",
                ):
                    asyncio.run(service.generate(source, 1280, 720, output))

            self.assertFalse(Path(output).exists())


if __name__ == "__main__":
    unittest.main()
