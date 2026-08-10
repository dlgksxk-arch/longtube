"""Build and register Scartography opening/intermission/ending clips.

The script renders three deterministic five-second H.264/AAC clips from approved
brand backgrounds, validates every staged clip, backs up the previous assets and
database, then atomically registers the new files on the CH2 template project.
"""
from __future__ import annotations

import argparse
from array import array
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import wave

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy.orm.attributes import flag_modified


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import CHANNELS_ROOT, DB_PATH, DATA_DIR  # noqa: E402
from app.models.database import SessionLocal  # noqa: E402
from app.models.project import Project  # noqa: E402
from app.services.video.subprocess_helper import find_ffmpeg  # noqa: E402


PROJECT_ID = "e6619f7e"
CHANNEL_NUMBER = 2
WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION = 5.0
SAMPLE_RATE = 48_000
KINDS = ("opening", "intermission", "ending")

GOLD = (207, 177, 117, 255)
GOLD_MUTED = (183, 158, 110, 255)
RED = (116, 22, 21, 255)
SHADOW = (0, 0, 0, 220)


def _timestamp() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")


def _font_path(bold: bool = False) -> Path:
    candidates = (
        Path(r"C:\Windows\Fonts\georgiab.ttf") if bold else Path(r"C:\Windows\Fonts\georgia.ttf"),
        Path(r"C:\Windows\Fonts\timesbd.ttf") if bold else Path(r"C:\Windows\Fonts\times.ttf"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Georgia/Times font was not found in C:\\Windows\\Fonts")


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, spacing: int) -> float:
    if not text:
        return 0.0
    return sum(float(draw.textlength(ch, font=font)) for ch in text) + spacing * (len(text) - 1)


def _draw_spaced_text(
    layer: Image.Image,
    text: str,
    *,
    center_x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    spacing: int,
    fill: tuple[int, int, int, int],
    red_index: int | None = None,
    stroke_width: int = 0,
    stroke_fill: tuple[int, int, int, int] = (0, 0, 0, 255),
) -> None:
    draw = ImageDraw.Draw(layer)
    x = center_x - _text_width(draw, text, font, spacing) / 2
    for index, char in enumerate(text):
        color = RED if red_index is not None and index == red_index else fill
        draw.text(
            (x, y),
            char,
            font=font,
            fill=color,
            stroke_width=stroke_width,
            stroke_fill=stroke_fill,
        )
        x += float(draw.textlength(char, font=font)) + spacing


def _build_overlay(kind: str, output_path: Path) -> None:
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    glow = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    shadow = Image.new("RGBA", overlay.size, (0, 0, 0, 0))

    if kind == "opening":
        title_size, title_y, title_spacing = 142, 418, 12
        subtitle, subtitle_size, subtitle_y, subtitle_spacing = (
            "EUROPEAN HISTORY DOCUMENTARIES",
            34,
            605,
            7,
        )
    elif kind == "intermission":
        title_size, title_y, title_spacing = 102, 425, 11
        subtitle, subtitle_size, subtitle_y, subtitle_spacing = (
            "MYTHS  ·  EMPIRES  ·  BORDERS",
            38,
            578,
            7,
        )
    else:
        title_size, title_y, title_spacing = 132, 420, 12
        subtitle, subtitle_size, subtitle_y, subtitle_spacing = (
            "@SCARTOGRAPHY",
            38,
            595,
            8,
        )

    title_font = ImageFont.truetype(str(_font_path()), title_size)
    subtitle_font = ImageFont.truetype(str(_font_path(bold=True)), subtitle_size)

    _draw_spaced_text(
        glow,
        "SCARTOGRAPHY",
        center_x=WIDTH // 2,
        y=title_y,
        font=title_font,
        spacing=title_spacing,
        fill=(229, 200, 136, 150),
        red_index=4,
        stroke_width=4,
        stroke_fill=(75, 44, 18, 120),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(14))
    overlay.alpha_composite(glow)

    _draw_spaced_text(
        shadow,
        "SCARTOGRAPHY",
        center_x=WIDTH // 2 + 5,
        y=title_y + 7,
        font=title_font,
        spacing=title_spacing,
        fill=SHADOW,
        red_index=None,
        stroke_width=5,
        stroke_fill=SHADOW,
    )
    overlay.alpha_composite(shadow)
    _draw_spaced_text(
        overlay,
        "SCARTOGRAPHY",
        center_x=WIDTH // 2,
        y=title_y,
        font=title_font,
        spacing=title_spacing,
        fill=GOLD,
        red_index=4,
        stroke_width=2,
        stroke_fill=(55, 34, 17, 255),
    )

    draw = ImageDraw.Draw(overlay)
    line_y = subtitle_y - 23
    draw.line((610, line_y, 900, line_y), fill=(153, 126, 77, 180), width=2)
    draw.line((1020, line_y, 1310, line_y), fill=(153, 126, 77, 180), width=2)
    draw.ellipse((951, line_y - 4, 959, line_y + 4), fill=RED)
    draw.ellipse((961, line_y - 4, 969, line_y + 4), fill=GOLD_MUTED)

    _draw_spaced_text(
        overlay,
        subtitle,
        center_x=WIDTH // 2,
        y=subtitle_y,
        font=subtitle_font,
        spacing=subtitle_spacing,
        fill=GOLD_MUTED,
        stroke_width=1,
        stroke_fill=(20, 15, 10, 255),
    )
    overlay.save(output_path, format="PNG")


def _make_audio(kind: str, output_path: Path) -> None:
    rng = random.Random({"opening": 2201, "intermission": 2202, "ending": 2203}[kind])
    impact_at = {"opening": 1.02, "intermission": 1.55, "ending": 0.72}[kind]
    whoosh_start = {"opening": 0.15, "intermission": 0.55, "ending": 0.05}[kind]
    whoosh_duration = {"opening": 1.35, "intermission": 1.75, "ending": 1.10}[kind]
    drone_hz = {"opening": 43.65, "intermission": 48.99, "ending": 41.20}[kind]

    pcm = array("h")
    filtered_noise = 0.0
    total = int(DURATION * SAMPLE_RATE)
    for i in range(total):
        t = i / SAMPLE_RATE
        fade_in = min(1.0, t / 0.20)
        fade_out = min(1.0, max(0.0, (DURATION - t) / 0.72))
        master = fade_in * fade_out

        sample = 0.115 * math.sin(2 * math.pi * drone_hz * t)
        sample += 0.042 * math.sin(2 * math.pi * drone_hz * 1.5 * t + 0.4)
        sample += 0.018 * math.sin(2 * math.pi * drone_hz * 2.01 * t)

        noise = rng.uniform(-1.0, 1.0)
        filtered_noise = 0.94 * filtered_noise + 0.06 * noise
        wx = (t - whoosh_start) / whoosh_duration
        if 0.0 <= wx <= 1.0:
            sample += filtered_noise * (math.sin(math.pi * wx) ** 2) * 0.42

        delta = t - impact_at
        if delta >= 0.0:
            env = math.exp(-4.8 * delta)
            sample += env * (
                0.40 * math.sin(2 * math.pi * 52.0 * delta)
                + 0.17 * math.sin(2 * math.pi * 104.0 * delta)
                + 0.055 * math.sin(2 * math.pi * 487.0 * delta)
                + 0.035 * math.sin(2 * math.pi * 731.0 * delta)
            )

        if kind == "ending" and t >= 3.05:
            resolved = t - 3.05
            sample += 0.055 * math.exp(-1.0 * resolved) * math.sin(2 * math.pi * 61.74 * resolved)

        sample *= master
        sample = max(-0.92, min(0.92, sample))
        left = int(sample * 32767)
        right = int(sample * 0.97 * 32767)
        pcm.extend((left, right))

    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())


def _motion_filter(kind: str) -> str:
    if kind == "opening":
        zoom = "min(zoom+0.00038,1.065)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif kind == "intermission":
        zoom = "1.055"
        x = "(iw-iw/zoom)*(on/149)"
        y = "ih/2-(ih/zoom/2)"
    else:
        zoom = "if(eq(on,0),1.065,max(zoom-0.00030,1.020))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    return (
        f"scale=2304:1296:flags=lanczos,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d={int(DURATION * FPS)}:"
        f"s={WIDTH}x{HEIGHT}:fps={FPS},"
        "eq=contrast=1.055:saturation=0.90:brightness=-0.018"
    )


def _render_clip(
    ffmpeg: str,
    kind: str,
    background: Path,
    overlay: Path,
    audio: Path,
    output: Path,
) -> None:
    overlay_in = {"opening": 0.52, "intermission": 0.28, "ending": 0.42}[kind]
    overlay_out = {"opening": 4.34, "intermission": 4.38, "ending": 4.28}[kind]
    filter_complex = (
        f"[0:v]{_motion_filter(kind)}[bg];"
        f"[1:v]format=rgba,fade=t=in:st={overlay_in}:d=0.78:alpha=1,"
        f"fade=t=out:st={overlay_out}:d=0.52:alpha=1[title];"
        "[bg][title]overlay=0:0:shortest=1,"
        "fade=t=in:st=0:d=0.24,fade=t=out:st=4.72:d=0.28,format=yuv420p[v]"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-loop",
        "1",
        "-i",
        str(background),
        "-loop",
        "1",
        "-i",
        str(overlay),
        "-i",
        str(audio),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "2:a:0",
        "-t",
        f"{DURATION:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        str(SAMPLE_RATE),
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    if result.returncode != 0:
        raise RuntimeError(f"{kind} render failed:\n{result.stderr[-6000:]}")


def _probe_clip(ffmpeg: str, path: Path) -> dict:
    decode = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if decode.returncode != 0:
        raise RuntimeError(f"decode validation failed for {path}: {decode.stderr[-3000:]}")

    info = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    details = f"{info.stdout}\n{info.stderr}"
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", details)
    if not match:
        raise RuntimeError(f"duration not found for {path}")
    duration = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    required = ("Video: h264", f"{WIDTH}x{HEIGHT}", "30 fps", "Audio: aac", "48000 Hz")
    missing = [token for token in required if token not in details]
    if missing:
        raise RuntimeError(f"media contract failed for {path}; missing={missing}\n{details[-4000:]}")
    if not 4.95 <= duration <= 5.08:
        raise RuntimeError(f"duration contract failed for {path}: {duration}")
    return {
        "duration": round(duration, 3),
        "size_bytes": path.stat().st_size,
        "video_codec": "h264",
        "audio_codec": "aac",
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "audio_rate": SAMPLE_RATE,
    }


def _backup_database(backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    source = sqlite3.connect(str(DB_PATH))
    target = sqlite3.connect(str(backup_path))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".tmp")
    shutil.copy2(source, temp)
    temp.replace(destination)


def _migrate_nonruntime_assets(project_dir: Path, interlude_dir: Path) -> None:
    """Keep template-cloned ``interlude`` limited to the three runtime clips."""
    legacy_backup_root = interlude_dir / "backups"
    backup_root = project_dir / "interlude_backups"
    if legacy_backup_root.is_dir():
        backup_root.mkdir(parents=True, exist_ok=True)
        for child in legacy_backup_root.iterdir():
            destination = backup_root / child.name
            if destination.exists():
                raise RuntimeError(f"backup migration destination already exists: {destination}")
            shutil.move(str(child), str(destination))
        legacy_backup_root.rmdir()

    legacy_source_root = interlude_dir / "source"
    source_root = project_dir / "brand_sources" / "interlude"
    if legacy_source_root.is_dir():
        source_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy_source_root, source_root, dirs_exist_ok=True)
        shutil.rmtree(legacy_source_root)


def _register(project_dir: Path, metadata: dict[str, dict], generated_at: str) -> dict:
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == PROJECT_ID).first()
        if project is None:
            raise RuntimeError(f"project not found: {PROJECT_ID}")
        cfg = dict(project.config or {})
        if int(cfg.get("channel") or 0) != CHANNEL_NUMBER:
            raise RuntimeError(f"project {PROJECT_ID} is not registered to channel {CHANNEL_NUMBER}")
        if str((cfg.get("channel_brand") or {}).get("channel_name") or "") != "Scartography":
            raise RuntimeError("project channel brand is not Scartography")

        interlude = dict(cfg.get("interlude") or {})
        for kind in KINDS:
            entry = metadata[kind]
            interlude[kind] = {
                "video_path": f"interlude/{kind}.mp4",
                "filename": f"scartography_{kind}_5s.mp4",
                "size_bytes": entry["size_bytes"],
                "duration": entry["duration"],
                "source": "generated-brand",
                "generated_at": generated_at,
            }
        cfg["interlude"] = interlude
        project.config = cfg
        flag_modified(project, "config")
        db.commit()
        db.refresh(project)
        return dict(project.config or {}).get("interlude") or {}
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--opening-bg", type=Path, required=True)
    parser.add_argument("--intermission-bg", type=Path, required=True)
    parser.add_argument("--ending-bg", type=Path, required=True)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(DATA_DIR) / "_system" / "projects" / PROJECT_ID,
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preview-dir", type=Path)
    args = parser.parse_args()

    backgrounds = {
        "opening": args.opening_bg.resolve(),
        "intermission": args.intermission_bg.resolve(),
        "ending": args.ending_bg.resolve(),
    }
    for kind, path in backgrounds.items():
        if not path.is_file():
            raise FileNotFoundError(f"{kind} background not found: {path}")

    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"project directory not found: {project_dir}")
    interlude_dir = project_dir / "interlude"
    timestamp = _timestamp()
    staging = interlude_dir / f"_build_tmp_{timestamp}"
    source_dir = project_dir / "brand_sources" / "interlude"
    staging.mkdir(parents=True, exist_ok=False)
    source_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    metadata: dict[str, dict] = {}
    staged_videos: dict[str, Path] = {}
    try:
        for kind in KINDS:
            source_copy = source_dir / f"scartography_{kind}_background.png"
            shutil.copy2(backgrounds[kind], source_copy)
            overlay = staging / f"{kind}_overlay.png"
            audio = staging / f"{kind}_sfx.wav"
            video = staging / f"{kind}.mp4"
            _build_overlay(kind, overlay)
            _make_audio(kind, audio)
            _render_clip(ffmpeg, kind, source_copy, overlay, audio, video)
            metadata[kind] = _probe_clip(ffmpeg, video)
            staged_videos[kind] = video

        if args.dry_run:
            preview_dir = None
            if args.preview_dir:
                preview_dir = args.preview_dir.resolve()
                preview_dir.mkdir(parents=True, exist_ok=True)
                for kind in KINDS:
                    shutil.copy2(staged_videos[kind], preview_dir / f"{kind}.mp4")
            print(
                json.dumps(
                    {
                        "status": "validated_dry_run",
                        "metadata": metadata,
                        "preview_dir": str(preview_dir) if preview_dir else None,
                    },
                    indent=2,
                )
            )
            return 0

        _migrate_nonruntime_assets(project_dir, interlude_dir)
        asset_backup_dir = project_dir / "interlude_backups" / timestamp
        asset_backup_dir.mkdir(parents=True, exist_ok=False)
        for kind in KINDS:
            existing = interlude_dir / f"{kind}.mp4"
            if existing.exists():
                shutil.copy2(existing, asset_backup_dir / existing.name)

        db_backup = Path(DB_PATH).with_name(f"longtube.before_ch2_interludes_{timestamp}.db")
        _backup_database(db_backup)

        channel_interlude_dir = Path(CHANNELS_ROOT) / f"CH{CHANNEL_NUMBER}" / "interlude"
        for kind in KINDS:
            project_target = interlude_dir / f"{kind}.mp4"
            _atomic_copy(staged_videos[kind], project_target)
            _atomic_copy(staged_videos[kind], channel_interlude_dir / f"{kind}.mp4")
            metadata[kind]["project_path"] = str(project_target)
            metadata[kind]["channel_path"] = str(channel_interlude_dir / f"{kind}.mp4")

        generated_at = datetime.now(timezone.utc).isoformat()
        registered = _register(project_dir, metadata, generated_at)
        result = {
            "status": "registered",
            "project_id": PROJECT_ID,
            "channel": CHANNEL_NUMBER,
            "brand": "Scartography",
            "asset_backup_dir": str(asset_backup_dir),
            "database_backup": str(db_backup),
            "metadata": metadata,
            "registered_interlude": registered,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
