from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


WIDTH = 1280
HEIGHT = 720
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "references"
    / "baekje_boat_cargo_close_layout_16x9.png"
)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#221913")
    draw = ImageDraw.Draw(image)

    # Tight top-down hull interior: only ribs, planks, and one cargo bundle.
    for y in range(0, HEIGHT, 52):
        shade = 42 + (y // 52) % 3 * 8
        draw.rectangle((0, y, WIDTH, y + 48), fill=(shade + 18, shade + 7, shade))
        draw.line((0, y + 47, WIDTH, y + 47), fill=(20, 14, 11), width=5)
        for x in range(20, WIDTH, 135):
            draw.line((x, y + 8, x + 65, y + 33), fill=(75, 51, 34), width=2)

    rib_color = (70, 45, 28)
    rib_highlight = (112, 74, 43)
    for x in (80, 300, 520, 760, 980, 1200):
        draw.arc((x - 250, -130, x + 250, 850), 78, 282, fill=(23, 14, 10), width=34)
        draw.arc((x - 250, -130, x + 250, 850), 78, 282, fill=rib_color, width=24)
        draw.arc((x - 245, -125, x + 245, 845), 78, 282, fill=rib_highlight, width=5)

    bundle_box = (430, 180, 860, 590)
    draw.rounded_rectangle(bundle_box, radius=95, fill=(104, 79, 45), outline=(31, 22, 14), width=14)
    for offset in range(-350, 500, 38):
        draw.line((430, 180 + offset, 860, 590 + offset), fill=(142, 111, 63), width=7)
        draw.line((430, 590 - offset, 860, 180 - offset), fill=(76, 55, 33), width=4)
    draw.line((645, 175, 645, 595), fill=(41, 29, 18), width=18)
    draw.line((425, 385, 865, 385), fill=(41, 29, 18), width=18)
    draw.ellipse((610, 350, 680, 420), fill=(54, 37, 22), outline=(160, 120, 67), width=6)

    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
