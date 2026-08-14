"""Build and optionally upload the CH1 Goguryeo EP01-EP30 compilation.

The script preserves every episode's already rendered body, removes repeated
opening/ending clips, overlays the current long-form title/channel header per
episode, inserts one opening, one midpoint intermission, and one ending, then
writes detailed YouTube chapters and upload metadata.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.thumbnail_service import generate_thumbnail  # noqa: E402
from app.services.video.longform_header import create_longform_header_overlay  # noqa: E402
from app.services.video.subprocess_helper import find_ffmpeg  # noqa: E402
from app.services.youtube_publish_schedule import next_main_publish_at  # noqa: E402
from app.services.youtube_service import YouTubeUploader  # noqa: E402


TITLE = "🌙자면서 듣는 고구려사🇰🇷 몰아보기 5시간"
CHANNEL_NAME = "10분역공"
OUTPUT_ROOT = Path(r"D:\long_result\CH1\고구려사_몰아보기_5시간")
EP1_ROOT = Path(r"D:\long_result\CH1\고구려사\EP.1.2606052213471bd449")
EPISODES_ROOT = Path(r"D:\long_result\CH1\고구려")
BGM_PATH = Path(r"C:\Users\Ai_M9\Desktop\longsult\channels\CH1\bgm\cache\ca685264022cae82_180s.mp3")
RESOLUTION = "1920x1080"
FPS = 30


def _timestamp(seconds: float) -> str:
    value = max(0, int(round(float(seconds or 0.0))))
    hours, rem = divmod(value, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _probe(path: Path, ffmpeg: str) -> dict[str, Any]:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    text = proc.stderr or ""
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        raise RuntimeError(f"Could not probe duration: {path}")
    duration = int(match.group(1)) * 3600 + int(match.group(2)) * 60 + float(match.group(3))
    video = re.search(r"Video:\s*([^\r\n]+)", text)
    audio = re.search(r"Audio:\s*([^\r\n]+)", text)
    return {
        "path": str(path),
        "duration": duration,
        "video": video.group(1).strip() if video else "",
        "audio": audio.group(1).strip() if audio else "",
        "bytes": path.stat().st_size,
    }


def _episodes() -> list[dict[str, Any]]:
    roots: dict[int, Path] = {1: EP1_ROOT}
    for path in EPISODES_ROOT.glob("EP.*"):
        if not path.is_dir():
            continue
        match = re.match(r"EP\.(\d+)\.", path.name)
        if match:
            roots[int(match.group(1))] = path
    if sorted(roots) != list(range(1, 31)):
        raise RuntimeError(f"Expected EP01-EP30, found: {sorted(roots)}")

    rows: list[dict[str, Any]] = []
    for number in range(1, 31):
        root = roots[number]
        script_path = root / "script.json"
        videos_dir = root / "videos"
        if not script_path.is_file() or not videos_dir.is_dir():
            raise RuntimeError(f"Missing source for EP{number:02d}: {root}")
        script = json.loads(script_path.read_text(encoding="utf-8"))
        expected_cuts = len(script.get("cuts") or [])
        if expected_cuts <= 0:
            raise RuntimeError(f"Script has no cuts for EP{number:02d}: {script_path}")
        cut_paths: list[str] = []
        for cut_number in range(1, expected_cuts + 1):
            candidates = (
                videos_dir / f"cut_{cut_number}.mp4",
                videos_dir / f"cut_{cut_number:03d}.mp4",
            )
            found = next((path for path in candidates if path.is_file()), None)
            if found is None:
                raise RuntimeError(
                    f"Missing body cut EP{number:02d} cut {cut_number}: {videos_dir}"
                )
            cut_paths.append(str(found))
        title = str(script.get("topic") or script.get("title") or "").strip()
        title = re.sub(r"\s*EP\.?\s*\d+\s*$", "", title, flags=re.IGNORECASE).strip()
        description = str(script.get("description") or "").strip()
        rows.append(
            {
                "episode": number,
                "root": str(root),
                "script": str(script_path),
                "cuts": cut_paths,
                "title": title,
                "description": description,
            }
        )
    return rows


def _run(cmd: list[str], *, log_path: Path | None = None) -> None:
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log:
            log.write("\n$ " + subprocess.list2cmdline(cmd) + "\n")
            log.flush()
            proc = subprocess.run(cmd, stdout=log, stderr=log, check=False)
    else:
        proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed ({proc.returncode}): {cmd[0]}")


def _write_concat_file(paths: list[Path], destination: Path) -> Path:
    destination.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in paths),
        encoding="utf-8",
    )
    return destination


def _normalize_body(
    *,
    ffmpeg: str,
    sources: list[Path],
    overlay: Path,
    output: Path,
    log_path: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    concat_input = _write_concat_file(
        sources,
        output.with_name(f".{output.stem}.cuts.txt"),
    )
    cmd = [
        ffmpeg,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_input),
        "-loop", "1",
        "-i", str(overlay),
        "-filter_complex",
        (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p[vbase];"
            "[vbase][1:v]overlay=0:0:eof_action=repeat:shortest=1,format=yuv420p[vout];"
            "[0:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:"
            "channel_layouts=stereo[aout]"
        ),
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "h264_nvenc",
        "-preset", "p5",
        "-tune", "hq",
        "-rc", "vbr",
        "-cq", "17",
        "-b:v", "0",
        "-profile:v", "high",
        "-level", "4.2",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        str(output),
    ]
    _run(cmd, log_path=log_path)


def _normalize_interlude(
    *,
    ffmpeg: str,
    source: Path,
    output: Path,
    log_path: Path,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(source),
        "-vf",
        (
            "scale=1920:1080:force_original_aspect_ratio=decrease,"
            "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
        ),
        "-af", "aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
        "-c:v", "h264_nvenc",
        "-preset", "p5",
        "-tune", "hq",
        "-rc", "vbr",
        "-cq", "17",
        "-b:v", "0",
        "-profile:v", "high",
        "-level", "4.2",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        str(output),
    ]
    _run(cmd, log_path=log_path)


def _concat(ffmpeg: str, parts: list[Path], output: Path, log_path: Path) -> None:
    concat_path = _write_concat_file(parts, output.parent / "concat.txt")
    _run(
        [
            ffmpeg,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_path),
            "-c", "copy",
            "-movflags", "+faststart",
            str(output),
        ],
        log_path=log_path,
    )


def _mix_bgm(ffmpeg: str, source: Path, output: Path, log_path: Path) -> None:
    if not BGM_PATH.is_file():
        shutil.copy2(source, output)
        return
    duration = _probe(source, ffmpeg)["duration"]
    cmd = [
        ffmpeg,
        "-y",
        "-i", str(source),
        "-stream_loop", "-1",
        "-ss", "60.000",
        "-i", str(BGM_PATH),
        "-filter_complex",
        (
            f"[1:a]volume=0.1050,aformat=sample_fmts=fltp:sample_rates=48000:"
            f"channel_layouts=stereo,apad,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[bgm];"
            f"[0:a]volume=1.0000,aformat=sample_fmts=fltp:sample_rates=48000:"
            f"channel_layouts=stereo,apad,atrim=0:{duration:.3f},asetpts=PTS-STARTPTS[main];"
            "[bgm][main]sidechaincompress=threshold=0.150:ratio=1.5:attack=80:release=650[ducked];"
            "[main][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
            "alimiter=limit=0.85:level=false[aout]"
        ),
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-t", f"{duration:.3f}",
        "-movflags", "+faststart",
        str(output),
    ]
    _run(cmd, log_path=log_path)


def _write_metadata(rows: list[dict[str, Any]], timeline: list[dict[str, Any]]) -> dict[str, Any]:
    episode_items = [item for item in timeline if item.get("kind") == "episode"]
    intermission_item = next(
        (item for item in timeline if item.get("kind") == "intermission"), None
    )
    episode_lines: list[str] = []
    detailed_timeline_lines: list[str] = []
    for item in episode_items:
        episode = int(item["episode"])
        chapter_start = str(item["start"])
        chapter_label = f"EP.{episode:02d} {item['title']}"
        # YouTube requires every chapter to be at least 10 seconds long. The
        # five-second opening/intermission therefore belongs to the adjacent
        # episode chapter rather than becoming an invalid standalone chapter.
        if episode == 1:
            chapter_start = "00:00:00"
            chapter_label = f"오프닝 · {chapter_label}"
        elif episode == 16 and intermission_item:
            chapter_start = str(intermission_item["start"])
            chapter_label = f"인터루드 · {chapter_label}"
        chapter_line = f"{chapter_start} {chapter_label}"
        episode_lines.append(chapter_line)
        detailed_timeline_lines.extend(
            [chapter_line, f"  └ {str(item.get('summary') or '').strip()}"]
        )
    description_lines = [
        "고구려의 건국부터 700년 제국의 몰락까지, 고구려사 30편을 한 번에 이어 듣는 몰아보기입니다.",
        "잠들기 전 편안하게 들을 수 있도록 각 편의 반복 오프닝과 엔딩은 제거하고, 전체 오프닝·인터루드·엔딩을 한 번씩만 배치했습니다.",
        "",
        "[전체 타임라인]",
        *detailed_timeline_lines,
        "",
        "※ 오프닝은 시작에 1회, 인터루드는 EP.15와 EP.16 사이에 1회, 엔딩은 마지막에 1회만 들어갑니다.",
        "",
        "고구려 건국 신화, 왕위 계승과 권력 투쟁, 광개토대왕과 장수왕의 팽창, 수·당과의 전쟁, 연개소문과 고구려 멸망까지 시간 순서로 정리했습니다.",
        "",
        "#고구려 #고구려사 #한국사 #삼국시대 #역사몰아보기 #자면서듣는 #10분역공",
    ]
    description = "\n".join(line for line in description_lines if line is not None).strip()
    tags = [
        "고구려", "고구려사", "한국사", "삼국시대", "역사", "역사몰아보기",
        "자면서 듣는", "수면 역사", "광개토대왕", "장수왕", "을지문덕",
        "살수대첩", "안시성", "연개소문", "고대사", "10분역공",
    ]
    metadata = {
        "title": TITLE,
        "description": description[:5000],
        "tags": tags,
        "language": "ko",
        "category_id": "27",
        "comment_topic": "고구려의 건국부터 멸망까지 이어지는 700년 역사",
        "chapters": episode_lines,
    }
    (OUTPUT_ROOT / "youtube_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUTPUT_ROOT / "youtube_description.txt").write_text(description, encoding="utf-8")
    return metadata


def build() -> dict[str, Any]:
    ffmpeg = find_ffmpeg()
    rows = _episodes()
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    overlays_dir = OUTPUT_ROOT / "overlays"
    normalized_dir = OUTPUT_ROOT / "normalized"
    logs_dir = OUTPUT_ROOT / "logs"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    render_log = logs_dir / "render.log"

    opening_source = EP1_ROOT / "interlude" / "opening.mp4"
    intermission_source = EP1_ROOT / "interlude" / "intermission.mp4"
    ending_source = EP1_ROOT / "interlude" / "ending.mp4"
    for source in (opening_source, intermission_source, ending_source):
        if not source.is_file():
            raise RuntimeError(f"Missing interlude source: {source}")

    parts: list[Path] = []
    timeline: list[dict[str, Any]] = []
    cursor = 0.0

    opening_output = normalized_dir / "000_opening.mp4"
    if not opening_output.is_file():
        _normalize_interlude(ffmpeg=ffmpeg, source=opening_source, output=opening_output, log_path=render_log)
    opening_info = _probe(opening_output, ffmpeg)
    parts.append(opening_output)
    timeline.append({"kind": "opening", "start_seconds": cursor, "start": _timestamp(cursor), **opening_info})
    cursor += float(opening_info["duration"])

    for row in rows:
        number = int(row["episode"])
        overlay_path = overlays_dir / f"ep_{number:02d}.png"
        create_longform_header_overlay(
            overlay_path,
            resolution=RESOLUTION,
            title=str(row["title"]),
            channel_name=CHANNEL_NAME,
        )
        output = normalized_dir / f"ep_{number:02d}.mp4"
        if not output.is_file() or output.stat().st_size <= 0:
            _normalize_body(
                ffmpeg=ffmpeg,
                sources=[Path(path) for path in row["cuts"]],
                overlay=overlay_path,
                output=output,
                log_path=render_log,
            )
        info = _probe(output, ffmpeg)
        parts.append(output)
        timeline.append(
            {
                "kind": "episode",
                "episode": number,
                "title": row["title"],
                "summary": row["description"],
                "start_seconds": cursor,
                "start": _timestamp(cursor),
                **info,
            }
        )
        cursor += float(info["duration"])

        if number == 15:
            intermission_output = normalized_dir / "015_intermission.mp4"
            if not intermission_output.is_file():
                _normalize_interlude(
                    ffmpeg=ffmpeg,
                    source=intermission_source,
                    output=intermission_output,
                    log_path=render_log,
                )
            intermission_info = _probe(intermission_output, ffmpeg)
            parts.append(intermission_output)
            timeline.append(
                {
                    "kind": "intermission",
                    "start_seconds": cursor,
                    "start": _timestamp(cursor),
                    **intermission_info,
                }
            )
            cursor += float(intermission_info["duration"])

    ending_output = normalized_dir / "999_ending.mp4"
    if not ending_output.is_file():
        _normalize_interlude(ffmpeg=ffmpeg, source=ending_source, output=ending_output, log_path=render_log)
    ending_info = _probe(ending_output, ffmpeg)
    parts.append(ending_output)
    timeline.append({"kind": "ending", "start_seconds": cursor, "start": _timestamp(cursor), **ending_info})
    cursor += float(ending_info["duration"])

    nomusic = OUTPUT_ROOT / "고구려사_몰아보기_5시간_nomusic.mp4"
    final = OUTPUT_ROOT / "고구려사_몰아보기_5시간.mp4"
    if not nomusic.is_file() or nomusic.stat().st_size <= 0:
        _concat(ffmpeg, parts, nomusic, render_log)
    if not final.is_file() or final.stat().st_size <= 0:
        _mix_bgm(ffmpeg, nomusic, final, render_log)

    final_info = _probe(final, ffmpeg)
    if not (cursor - 2.0 <= float(final_info["duration"]) <= cursor + 2.0):
        raise RuntimeError(
            f"Final duration mismatch: timeline={cursor:.3f}, final={final_info['duration']:.3f}"
        )

    thumbnail_bg = OUTPUT_ROOT / "thumbnail_bg.png"
    shutil.copy2(EP1_ROOT / "output" / "thumbnail_bg.png", thumbnail_bg)
    thumbnail = Path(
        generate_thumbnail(
            "GOGURYEO_COMPILATION_5H",
            "자면서 듣는\n고구려사 5시간",
            base_image_path=str(thumbnail_bg),
            output_path=str(OUTPUT_ROOT / "thumbnail.png"),
            subtitle="고구려 700년 몰아보기",
            config={},
        )
    )

    metadata = _write_metadata(rows, timeline)
    manifest = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": TITLE,
        "channel": CHANNEL_NAME,
        "pipeline": "goguryeo-compilation-dynamic-longform-header-v1",
        "source_rule": "opening once + EP01-EP15 + intermission once + EP16-EP30 + ending once",
        "episode_count": 30,
        "timeline_duration": cursor,
        "final": final_info,
        "thumbnail": str(thumbnail),
        "timeline": timeline,
        "metadata": metadata,
    }
    (OUTPUT_ROOT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def upload(manifest: dict[str, Any]) -> dict[str, Any]:
    final = Path(str(manifest["final"]["path"]))
    thumbnail = Path(str(manifest["thumbnail"]))
    metadata = dict(manifest["metadata"])
    publish_at = next_main_publish_at()
    uploader = YouTubeUploader(channel_id=1)
    channel = uploader.get_channel_info()
    if str(channel.get("title") or "").strip() != CHANNEL_NAME:
        raise RuntimeError(f"Wrong authenticated channel: {channel}")
    progress_path = OUTPUT_ROOT / "upload_progress.json"

    def progress(value: int) -> None:
        progress_path.write_text(
            json.dumps(
                {"progress": int(value), "updated_at": datetime.now(timezone.utc).isoformat()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    result = uploader.upload(
        video_path=str(final),
        title=str(metadata["title"]),
        description=str(metadata["description"]),
        tags=list(metadata["tags"]),
        thumbnail_path=str(thumbnail),
        privacy="public",
        language="ko",
        category_id=str(metadata["category_id"]),
        made_for_kids=False,
        progress_callback=progress,
        comment_topic=str(metadata["comment_topic"]),
        publish_at=publish_at,
    )
    result["authenticated_channel"] = channel
    result["publish_at"] = publish_at
    (OUTPUT_ROOT / "upload_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upload", action="store_true", help="Upload after a successful build")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build()
    print(json.dumps({"status": "built", "final": manifest["final"]}, ensure_ascii=False))
    if args.upload:
        result = upload(manifest)
        print(json.dumps({"status": "uploaded", "result": result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
