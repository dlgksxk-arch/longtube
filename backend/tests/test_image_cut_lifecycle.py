import json
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import oneclick_service as oneclick  # noqa: E402
from app.services.image.asset_guard import (  # noqa: E402
    image_has_prompt_sidecar_commit,
    write_prompt_sidecar,
)


def _write_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), (32, 64, 96)).save(path)


def _commit(path: Path, cut_number: int) -> None:
    write_prompt_sidecar(
        path,
        cut_number=cut_number,
        image_model="comfyui-flux2-klein-4b",
        source_prompt=f"source {cut_number}",
        final_prompt=f"final {cut_number}",
    )


class ImageCutLifecycleTests(unittest.TestCase):
    def test_prompt_sidecar_is_the_atomic_commit_marker(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "images" / "cut_7.png"
            _write_png(image)

            self.assertFalse(image_has_prompt_sidecar_commit(image, cut_number=7))
            _commit(image, 7)

            self.assertTrue(image_has_prompt_sidecar_commit(image, cut_number=7))
            self.assertFalse(image_has_prompt_sidecar_commit(image, cut_number=8))
            self.assertFalse(image.with_name(image.name + ".prompt.json.tmp").exists())

    def test_resume_integrity_check_rejects_corrupt_png_with_sidecar(self):
        with tempfile.TemporaryDirectory() as td:
            image = Path(td) / "images" / "cut_9.png"
            _write_png(image)
            _commit(image, 9)
            image.write_bytes(b"not-a-real-png" * 20)

            self.assertTrue(image_has_prompt_sidecar_commit(image, cut_number=9))
            self.assertFalse(
                image_has_prompt_sidecar_commit(
                    image,
                    cut_number=9,
                    verify_image=True,
                )
            )

    def test_oneclick_scan_counts_only_images_with_commit_markers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "script.json").write_text(
                json.dumps(
                    {"cuts": [{"cut_number": 1}, {"cut_number": 2}]},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            first = root / "images" / "cut_1.png"
            second = root / "images" / "cut_2.png"
            _write_png(first)
            _write_png(second)
            _commit(first, 1)

            states, counts, total, removed = oneclick._scan_project_outputs(
                "V3_CH1_EP1_test",
                config={"result_dir": str(root), "__oneclick_v3__": True},
            )

            self.assertEqual(total, 2)
            self.assertEqual(counts["4"], 1)
            self.assertEqual(states["4"], "pending")
            self.assertEqual(removed, [])


if __name__ == "__main__":
    unittest.main()
