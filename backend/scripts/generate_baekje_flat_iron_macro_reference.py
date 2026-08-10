import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


WIDTH = 1280
HEIGHT = 720
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "references"
    / "baekje_flat_iron_macro_layout_16x9.png"
)


def main() -> None:
    rng = random.Random(405)
    image = Image.new("RGB", (WIDTH, HEIGHT), (31, 25, 22))
    draw = ImageDraw.Draw(image, "RGBA")

    for _ in range(1900):
        x = rng.randrange(WIDTH)
        y = rng.randrange(HEIGHT)
        radius = rng.randrange(3, 34)
        rust = rng.choice(
            ((92, 45, 24, 85), (132, 62, 28, 60), (54, 42, 35, 110), (177, 94, 38, 30))
        )
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=rust)

    for _ in range(150):
        x1 = rng.randrange(WIDTH)
        y1 = rng.randrange(HEIGHT)
        x2 = x1 + rng.randrange(-170, 171)
        y2 = y1 + rng.randrange(-45, 46)
        draw.line((x1, y1, x2, y2), fill=(12, 10, 9, 145), width=rng.randrange(1, 5))

    gold_points = [
        (120, 430),
        (250, 405),
        (375, 425),
        (505, 390),
        (640, 410),
        (770, 378),
        (900, 399),
        (1035, 365),
        (1160, 390),
    ]
    draw.line(gold_points, fill=(195, 142, 55, 210), width=12, joint="curve")
    for x, y in ((355, 420), (705, 396), (1005, 373)):
        draw.ellipse((x - 17, y - 17, x + 17, y + 17), fill=(31, 25, 22, 255))

    image = image.filter(ImageFilter.GaussianBlur(radius=1.2))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
