from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
REFERENCES = ROOT / "assets" / "references"
SOURCE = REFERENCES / "shichishito_silhouette_16x9.png"
OUTPUT = REFERENCES / "shichishito_branch_impact_layout_16x9.png"


def main() -> None:
    random.seed(705)
    source = Image.open(SOURCE).convert("RGB")
    width, height = source.size

    paper = Image.new("RGB", source.size, (50, 48, 45))
    paper_noise = Image.effect_noise(source.size, 34).convert("L").filter(
        ImageFilter.GaussianBlur(0.7)
    )
    paper = ImageChops.add(paper, Image.merge("RGB", (paper_noise,) * 3), scale=3.8)
    draw = ImageDraw.Draw(paper, "RGBA")
    for y in range(18, height, 27):
        draw.line((0, y, width, y + random.randint(-4, 4)), fill=(190, 175, 145, 15), width=1)
    for x in range(10, width, 31):
        draw.line((x, 0, x + random.randint(-5, 5), height), fill=(20, 18, 16, 18), width=1)

    opponent = Image.new("RGBA", source.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(opponent, "RGBA")
    od.line((105, 618, 1175, 96), fill=(8, 7, 6, 180), width=72)
    od.line((105, 618, 1175, 96), fill=(82, 80, 72, 255), width=54)
    od.line((117, 607, 1162, 99), fill=(170, 158, 127, 170), width=8)
    od.polygon(((1128, 78), (1214, 77), (1173, 126)), fill=(78, 75, 68, 255))
    od.ellipse((80, 580, 150, 650), fill=(65, 53, 41, 255), outline=(12, 10, 9, 255), width=7)
    paper = Image.alpha_composite(paper.convert("RGBA"), opponent)

    gray = source.convert("L")
    sword_mask = gray.point(lambda value: 255 if value < 82 else 0).filter(
        ImageFilter.GaussianBlur(0.4)
    )
    shadow = Image.new("RGBA", source.size, (0, 0, 0, 0))
    shadow.putalpha(sword_mask.filter(ImageFilter.GaussianBlur(12)))
    shadow_color = Image.new("RGBA", source.size, (0, 0, 0, 130))
    shadow = Image.composite(shadow_color, Image.new("RGBA", source.size), shadow)
    paper.alpha_composite(shadow, (9, 11))

    iron = Image.new("RGBA", source.size, (45, 39, 32, 255))
    iron_noise = Image.effect_noise(source.size, 65).convert("L")
    rust = Image.new("RGBA", source.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(rust, "RGBA")
    for _ in range(340):
        x = random.randint(470, 815)
        y = random.randint(55, 680)
        radius = random.randint(2, 13)
        rd.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(132 + random.randint(0, 45), 57 + random.randint(0, 28), 25, random.randint(55, 145)),
        )
    rust = rust.filter(ImageFilter.GaussianBlur(1.1))
    iron = Image.alpha_composite(iron, rust)
    highlight = Image.merge("RGBA", (iron_noise, iron_noise, iron_noise, iron_noise.point(lambda v: v // 3)))
    iron = Image.alpha_composite(iron, highlight)
    iron.putalpha(sword_mask)
    paper = Image.alpha_composite(paper, iron)

    edge = sword_mask.filter(ImageFilter.FIND_EDGES).point(lambda value: min(255, value * 3))
    edge_layer = Image.new("RGBA", source.size, (12, 10, 8, 0))
    edge_layer.putalpha(edge)
    paper = Image.alpha_composite(paper, edge_layer)

    sparks = Image.new("RGBA", source.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(sparks, "RGBA")
    for _ in range(24):
        x = 770 + random.randint(-35, 65)
        y = 310 + random.randint(-35, 35)
        length = random.randint(8, 34)
        sd.line((x, y, x + length, y - random.randint(4, 24)), fill=(225, 158, 63, 170), width=2)
    paper = Image.alpha_composite(paper, sparks)
    paper.convert("RGB").save(OUTPUT, quality=96)
    print(OUTPUT)


if __name__ == "__main__":
    main()
