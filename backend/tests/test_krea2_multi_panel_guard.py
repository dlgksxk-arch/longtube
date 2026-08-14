import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from app.services.image.comfyui_service import _image_has_multi_panel_layout


class Krea2MultiPanelGuardTests(unittest.TestCase):
    def _save(self, image: Image.Image, directory: str, name: str) -> Path:
        path = Path(directory) / name
        image.save(path)
        return path

    def test_rejects_borderless_two_by_two_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (640, 360))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 319, 179), fill=(20, 45, 80))
            draw.rectangle((320, 0, 639, 179), fill=(210, 170, 80))
            draw.rectangle((0, 180, 319, 359), fill=(45, 130, 65))
            draw.rectangle((320, 180, 639, 359), fill=(145, 45, 55))
            path = self._save(image, directory, "two_by_two.png")
            self.assertTrue(_image_has_multi_panel_layout(path))

    def test_rejects_asymmetric_three_panel_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (640, 360), (0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 319, 179), fill=(0, 0, 0))
            draw.rectangle((0, 180, 319, 359), fill=(220, 40, 40))
            draw.rectangle((320, 0, 639, 359), fill=(255, 255, 255))
            path = self._save(image, directory, "three_panel.png")
            self.assertTrue(_image_has_multi_panel_layout(path))

    def test_accepts_single_continuous_gradient(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Image.new("RGB", (640, 360))
            pixels = image.load()
            for y in range(image.height):
                for x in range(image.width):
                    pixels[x, y] = (
                        30 + x * 150 // image.width,
                        50 + y * 120 // image.height,
                        90 + (x + y) * 80 // (image.width + image.height),
                    )
            path = self._save(image, directory, "continuous.png")
            self.assertFalse(_image_has_multi_panel_layout(path))


if __name__ == "__main__":
    unittest.main()
