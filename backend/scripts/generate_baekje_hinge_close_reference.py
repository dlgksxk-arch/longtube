from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


WIDTH = 1280
HEIGHT = 720
OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "references"
    / "baekje_hinge_close_layout_16x9.png"
)


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), (89, 63, 42))
    draw = ImageDraw.Draw(image)
    for x in range(0, WIDTH, 155):
        shade = 78 + (x // 155) % 3 * 10
        draw.rectangle((x, 0, x + 148, HEIGHT), fill=(shade + 22, shade + 5, shade - 12))
        draw.line((x + 149, 0, x + 149, HEIGHT), fill=(38, 25, 17), width=8)
        for y in range(25, HEIGHT, 65):
            draw.line((x + 15, y, x + 130, y + 18), fill=(111, 78, 50), width=3)

    strap = [(0, 270), (460, 270), (560, 220), (720, 220), (820, 270), (1280, 270),
             (1280, 450), (820, 450), (720, 500), (560, 500), (460, 450), (0, 450)]
    draw.polygon(strap, fill=(42, 40, 37), outline=(17, 16, 15))
    draw.line(strap + [strap[0]], fill=(116, 70, 37), width=12, joint="curve")
    for x, y in ((170, 360), (620, 360), (1110, 360)):
        draw.ellipse((x - 48, y - 48, x + 48, y + 48), fill=(25, 24, 22), outline=(146, 84, 39), width=10)
        draw.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(91, 57, 34))

    image = image.filter(ImageFilter.GaussianBlur(radius=0.7))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT)
    print(OUTPUT)


if __name__ == "__main__":
    main()
