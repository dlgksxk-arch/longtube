"""Create channel-wide CH4 interludes with local Pillow + FFmpeg only.

The design borrows the broad TV-variety mystery rhythm (short mystery lead-ins
and emphatic title cards) without copying any broadcaster branding, footage,
or music.  Files are written to the CH4 template project's interlude folder.
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.services.video.subprocess_helper import find_ffmpeg


WIDTH, HEIGHT = 1920, 1080
FONT = Path(r"C:\Windows\Fonts\malgunbd.ttf")
DEFAULT_DIR = Path(r"C:\Users\Ai_M9\Desktop\longsult\channels\CH4\projects\83cca89d\interlude")


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT), size=size)


def _text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, size: int, fill: tuple[int, int, int], *, anchor: str = "mm") -> None:
    draw.text(xy, text, font=_font(size), fill=fill, anchor=anchor, stroke_width=max(2, size // 22), stroke_fill=(11, 8, 8))


def _base(seed: int) -> Image.Image:
    random.seed(seed)
    img = Image.new("RGB", (WIDTH, HEIGHT), (12, 15, 22))
    px = img.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            # navy-black archival backdrop with a burgundy center glow
            radial = max(0.0, 1.0 - math.hypot((x - WIDTH * .52) / WIDTH, (y - HEIGHT * .48) / HEIGHT) * 1.8)
            grain = random.randint(-7, 7)
            px[x, y] = (
                int(12 + 40 * radial + grain),
                int(15 + 13 * radial + grain),
                int(22 + 10 * radial + grain),
            )

    draw = ImageDraw.Draw(img, "RGBA")
    # archival map grid and torn-document panels
    for x in range(-50, WIDTH + 80, 95):
        draw.line((x, 0, x + 260, HEIGHT), fill=(212, 176, 91, 26), width=2)
    for y in range(55, HEIGHT, 82):
        draw.line((0, y, WIDTH, y), fill=(212, 176, 91, 20), width=1)
    for _ in range(16):
        x = random.randint(40, WIDTH - 280)
        y = random.randint(80, HEIGHT - 170)
        w = random.randint(100, 370)
        h = random.randint(40, 120)
        draw.rectangle((x, y, x + w, y + h), fill=(7, 8, 12, random.randint(35, 80)), outline=(222, 179, 73, 65), width=2)
    draw.rectangle((54, 54, WIDTH - 54, HEIGHT - 54), outline=(224, 182, 65, 190), width=5)
    draw.rectangle((76, 76, WIDTH - 76, HEIGHT - 76), outline=(133, 33, 38, 180), width=2)
    draw.polygon([(0, 0), (WIDTH, 0), (WIDTH - 300, 190), (0, 345)], fill=(70, 15, 22, 185))
    draw.rectangle((0, HEIGHT - 165, WIDTH, HEIGHT), fill=(5, 7, 11, 210))
    return img.filter(ImageFilter.GaussianBlur(radius=0.22))


def _layer(text: str, size: int, fill: tuple[int, int, int], *, width: int = WIDTH, height: int = 180) -> Image.Image:
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    _text(ImageDraw.Draw(img), (width // 2, height // 2), text, size, fill)
    return img


def _objects(seed: int) -> Image.Image:
    random.seed(seed)
    img = Image.new("RGBA", (760, 610), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img, "RGBA")
    for i in range(7):
        x = 50 + (i % 3) * 230 + random.randint(-16, 16)
        y = 55 + (i // 3) * 175 + random.randint(-12, 12)
        w, h = random.randint(125, 195), random.randint(82, 126)
        shade = (45 + i * 13, 20 + i * 4, 21 + i * 3, 210)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=7, fill=shade, outline=(235, 190, 79, 185), width=3)
        draw.line((x + 18, y + 29, x + w - 18, y + 29), fill=(245, 211, 127, 110), width=3)
        draw.line((x + 18, y + 54, x + w - 38, y + 54), fill=(245, 211, 127, 75), width=2)
        draw.ellipse((x + w - 43, y + h - 43, x + w - 15, y + h - 15), outline=(183, 49, 51, 205), width=4)
    return img


def _render(ffmpeg: str, out: Path, kind: str, title: str, kicker: str, footer: str, seconds: float, seed: int) -> None:
    background = out / f"_{kind}_background.png"
    objects = out / f"_{kind}_objects.png"
    kicker_png = out / f"_{kind}_kicker.png"
    title_png = out / f"_{kind}_title.png"
    footer_png = out / f"_{kind}_footer.png"
    left_png = out / f"_{kind}_left.png"
    right_png = out / f"_{kind}_right.png"
    _base(seed).save(background)
    _objects(seed).save(objects)
    _layer(kicker, 42, (248, 210, 92), height=110).save(kicker_png)
    _layer(title, 112 if kind != "intermission" else 126, (255, 233, 153), height=210).save(title_png)
    _layer(footer, 42, (229, 228, 220), height=105).save(footer_png)
    _layer("CH4  |  CASE ARCHIVE", 27, (238, 195, 77), width=480, height=65).save(left_png)
    _layer("실화 재연 · 미스터리 기록", 27, (238, 195, 77), width=480, height=65).save(right_png)
    duration = f"{seconds:.2f}"
    # Individual overlay layers move independently; the background itself stays fixed.
    graph = (
        "[0:v]format=rgba[bg];"
        "[1:v]format=rgba[obj];"
        "[2:v]format=rgba[kicker];"
        "[3:v]scale=w='trunc(iw*(0.82+0.18*min(1\\,t/0.55)))':h=-2:eval=frame[title];"
        "[4:v]format=rgba[footer];[5:v]format=rgba[left];[6:v]format=rgba[right];"
        "[bg][obj]overlay=x='-420+150*t':y='390+18*sin(1.8*t)':format=auto[v1];"
        "[v1][kicker]overlay=x='(W-w)/2':y='if(lt(t\\,0.45)\\,-h+(190+h)*t/0.45\\,190)':format=auto[v2];"
        "[v2][title]overlay=x='(W-w)/2':y='if(lt(t\\,0.65)\\,H+(435-H)*t/0.65\\,435)':format=auto[v3];"
        "[v3][footer]overlay=x='(W-w)/2':y='if(lt(t\\,0.95)\\,H+(650-H)*t/0.95\\,650)':format=auto[v4];"
        "[v4][left]overlay=x='if(lt(t\\,0.7)\\,-w+95*t/0.7\\,95)':y='H-h-72':format=auto[v5];"
        "[v5][right]overlay=x='if(lt(t\\,0.7)\\,W-95*t/0.7\\,W-w-95)':y='H-h-72',format=yuv420p[outv]"
    )
    subprocess.run([
        ffmpeg, "-y", "-loop", "1", "-i", str(background),
        "-loop", "1", "-i", str(objects), "-loop", "1", "-i", str(kicker_png),
        "-loop", "1", "-i", str(title_png), "-loop", "1", "-i", str(footer_png),
        "-loop", "1", "-i", str(left_png), "-loop", "1", "-i", str(right_png),
        "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000",
        "-t", duration, "-filter_complex", graph,
        "-map", "[outv]", "-map", "7:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out / f"{kind}.mp4"),
    ], check=True)
    for path in (background, objects, kicker_png, title_png, footer_png, left_png, right_png):
        path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_DIR)
    args = parser.parse_args()
    if not FONT.exists():
        raise RuntimeError(f"Korean font not found: {FONT}")
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    specs = {
        "opening": ("기괴와 변칙의 세계사", "사건 기록이 열립니다", "한 장의 기록, 믿기 어려운 진실", 8.0),
        "intermission": ("다음 기록", "잠깐, 사건의 핵심을 확인합니다", "기록은 아직 끝나지 않았습니다", 3.0),
        "ending": ("기괴와 변칙의 세계사", "기록은 다음 이야기로 이어집니다", "구독하고 다음 사건을 확인하세요", 7.0),
    }
    for index, (kind, (title, kicker, footer, duration)) in enumerate(specs.items(), start=1):
        _render(ffmpeg, out, kind, title, kicker, footer, duration, 1700 + index)
        print(f"created {kind}: {out / f'{kind}.mp4'}")


if __name__ == "__main__":
    main()
