"""Create an isolated CH4 voice-cast image/TTS/render verification project."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.config import resolve_project_dir
from app.models.cut import Cut
from app.models.database import SessionLocal
from app.models.project import Project
from app.routers.image import generate_one_image
from app.routers.subtitle import render_video_with_subtitles
from app.routers.video import generate_all_videos
from app.routers.voice import generate_one_voice
from app.services.tts.voice_cast import apply_emotion_to_tts_text, resolve_tts_voice


SOURCE_PROJECT_ID = "83cca89d"
SOURCE_SCRIPT = Path(r"C:\Users\Ai_M9\Desktop\longsult\channels\CH4\projects\83cca89d\prepared_scripts\CH4-WH-S01-EP02.json")
ROLES = ("narrator", "male_1", "male_2", "female_1")


def _source_cuts(config: dict, source_path: Path, selected_numbers: list[int] | None = None) -> list[dict]:
    script = json.loads(source_path.read_text(encoding="utf-8"))
    if selected_numbers:
        by_number = {int(cut["cut_number"]): dict(cut) for cut in script["cuts"]}
        if any(number not in by_number for number in selected_numbers):
            raise RuntimeError("source cut selection contains a cut that does not exist")
        selected = [by_number[number] for number in selected_numbers]
        if len(selected_numbers) == len(ROLES):
            actual_roles = [resolve_tts_voice(cut, config).role for cut in selected]
            if actual_roles != list(ROLES):
                raise RuntimeError(f"source cut roles do not match {ROLES}: {actual_roles}")
        return selected
    selected: dict[str, dict] = {}
    for cut in script["cuts"]:
        role = resolve_tts_voice(cut, config).role
        speaker = str(cut.get("speaker") or "").strip()
        if role == "narrator" and speaker != "해설자":
            continue
        if role in ROLES and role not in selected:
            selected[role] = dict(cut)
    missing = [role for role in ROLES if role not in selected]
    if missing:
        raise RuntimeError(f"source script is missing test roles: {missing}")
    return [selected[role] for role in ROLES]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def run(project_id: str, source_path: Path = SOURCE_SCRIPT, selected_numbers: list[int] | None = None) -> dict:
    db = SessionLocal()
    try:
        existing = db.query(Project).filter(Project.id == project_id).first()
        source = db.query(Project).filter(Project.id == SOURCE_PROJECT_ID).first()
        if source is None:
            raise RuntimeError(f"source preset project not found: {SOURCE_PROJECT_ID}")
        config = dict((existing.config if existing is not None else source.config) or {})
        config.update({
            "video_model": "ffmpeg-static",
            "enable_ai_video": False,
            "video_target_selection": "none",
            "ai_video_first_n": 0,
            "cut_level_subtitles": False,
            "subtitle_delivery": "youtube_caption",
            "target_duration": 16,
            "bgm_enabled": False,
            "shorts_enabled": False,
            "shorts_upload_enabled": False,
            "interlude": {},
        })
        cuts = _source_cuts(config, source_path, selected_numbers)
        script_cuts = []
        manifest_cuts = []
        for number, source_cut in enumerate(cuts, start=1):
            item = dict(source_cut)
            item["cut_number"] = number
            script_cuts.append(item)
            resolved = resolve_tts_voice(item, config)
            manifest_cuts.append({
                "cut_number": number,
                "source_cut_number": source_cut["cut_number"],
                "speaker": item.get("speaker", ""),
                "emotion": item.get("emotion", ""),
                "role": resolved.role,
                "voice_id": resolved.voice_id,
                "tts_text": apply_emotion_to_tts_text(item.get("narration", ""), resolved, config["tts_model"]),
            })
            if existing is None:
                db.add(Cut(
                    project_id=project_id,
                    cut_number=number,
                    narration=item.get("narration", ""),
                    image_prompt=item.get("image_prompt", ""),
                    scene_type=item.get("scene_type", "dialogue"),
                    status="pending",
                ))
        if existing is None:
            db.add(Project(
                id=project_id,
                title="CH4 화자 더빙 매핑 검증",
                topic="CH4 화자별 음성 및 감성 태그 검증",
                config=config,
                total_cuts=len(script_cuts),
                status="draft",
            ))
            db.commit()
        else:
            existing.config = config
            db.commit()

        project_dir = resolve_project_dir(project_id, config, create=True)
        if existing is None:
            (project_dir / "script.json").write_text(
                json.dumps({"title": "CH4 화자 더빙 매핑 검증", "cuts": script_cuts}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        for number in range(1, len(script_cuts) + 1):
            row = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == number).first()
            if row is not None and not row.image_path:
                await generate_one_image(project_id, number, db)
        for number in range(1, len(script_cuts) + 1):
            row = db.query(Cut).filter(Cut.project_id == project_id, Cut.cut_number == number).first()
            if row is not None and not row.audio_path:
                await generate_one_voice(project_id, number, db)
        render_result = await generate_all_videos(project_id, db)
        final_render_result = await render_video_with_subtitles(project_id, db)

        db.expire_all()
        rows = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
        for entry, row in zip(manifest_cuts, rows):
            image = project_dir / str(row.image_path)
            audio = project_dir / str(row.audio_path)
            video = project_dir / str(row.video_path)
            entry.update({
                "image_path": str(image), "image_sha256": _sha256(image),
                "audio_path": str(audio), "audio_sha256": _sha256(audio), "audio_duration": row.audio_duration,
                "video_path": str(video), "video_sha256": _sha256(video),
            })
        result = {
            "project_id": project_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "render": render_result,
            "final_render": final_render_result,
            "cuts": manifest_cuts,
        }
        (project_dir / "voice_cast_validation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return result
    finally:
        db.close()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default="CH4_VOICE_CAST_TEST_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--source-script", default=str(SOURCE_SCRIPT))
    parser.add_argument("--source-cut-numbers", default="", help="narrator,male_1,male_2,female_1")
    args = parser.parse_args()
    selected_numbers = [int(value.strip()) for value in args.source_cut_numbers.split(",") if value.strip()] or None
    result = asyncio.run(run(args.project_id, Path(args.source_script), selected_numbers))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
