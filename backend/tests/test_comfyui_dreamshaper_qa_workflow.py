import json
import unittest
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parent.parent
    / "workflows"
    / "comfyui"
    / "dreamshaper_xl_longtube_text2img.json"
)


class DreamShaperQaWorkflowTests(unittest.TestCase):
    def test_final_person_face_and_cow_detectors_are_connected(self):
        graph = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

        self.assertEqual(graph["26"]["inputs"]["model_name"], "segm/person_yolov8m-seg.pt")
        self.assertEqual(graph["34"]["inputs"]["model_name"], "bbox/face_yolov8m.pt")
        self.assertEqual(graph["45"]["inputs"]["model_name"], "bbox/yolov8m.pt")
        self.assertEqual(graph["44"]["inputs"]["image"], ["6", 0])
        self.assertEqual(graph["35"]["inputs"]["image"], ["6", 0])
        self.assertEqual(graph["46"]["inputs"]["image"], ["6", 0])
        self.assertEqual(graph["46"]["inputs"]["labels"], "cow")
        self.assertEqual(graph["33"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["37"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["40"]["class_type"], "Display Int (rgthree)")
        self.assertEqual(graph["48"]["class_type"], "Display Int (rgthree)")


if __name__ == "__main__":
    unittest.main()
