"""Download router"""
import json
import zipfile
import io
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pathlib import Path

from app.models.database import get_db
from app.models.project import Project
from app.config import DATA_DIR

router = APIRouter()


def _load_script(project_id: str) -> dict:
    """Load script.json from disk"""
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/{project_id}/download/{asset_type}")
def download_asset(
    project_id: str,
    asset_type: str,
    cut: int = Query(None),
    db: Session = Depends(get_db)
):
    """Download individual asset (script, audio, image, video, subtitle, final)"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    project_dir = DATA_DIR / project_id

    if asset_type == "script":
        script_path = project_dir / "script.json"
        if not script_path.exists():
            raise HTTPException(404, "Script not found")
        return FileResponse(script_path, filename="script.json")

    elif asset_type == "audio":
        if cut is None:
            raise HTTPException(400, "cut parameter required for audio download")
        audio_path = project_dir / "audio" / f"cut_{cut}.wav"
        if not audio_path.exists():
            raise HTTPException(404, f"Audio for cut {cut} not found")
        return FileResponse(audio_path, filename=f"cut_{cut}.wav")

    elif asset_type == "image":
        if cut is None:
            raise HTTPException(400, "cut parameter required for image download")
        image_path = project_dir / "images" / f"cut_{cut}.png"
        if not image_path.exists():
            image_path = project_dir / "images" / f"cut_{cut}_custom.png"
        if not image_path.exists():
            raise HTTPException(404, f"Image for cut {cut} not found")
        return FileResponse(image_path, filename=f"cut_{cut}.png")

    elif asset_type == "video":
        if cut is None:
            raise HTTPException(400, "cut parameter required for video download")
        video_path = project_dir / "videos" / f"cut_{cut}.mp4"
        if not video_path.exists():
            raise HTTPException(404, f"Video for cut {cut} not found")
        return FileResponse(video_path, filename=f"cut_{cut}.mp4")

    elif asset_type == "subtitle":
        subtitle_path = project_dir / "subtitles" / "subtitles.ass"
        if not subtitle_path.exists():
            raise HTTPException(404, "Subtitle file not found")
        return FileResponse(subtitle_path, filename="subtitles.ass")

    elif asset_type == "final":
        # Try final_with_subtitles first, then merged
        final_path = project_dir / "output" / "final_with_subtitles.mp4"
        if not final_path.exists():
            final_path = project_dir / "videos" / "merged.mp4"
        if not final_path.exists():
            raise HTTPException(404, "Final video not found")
        return FileResponse(final_path, filename="final_video.mp4")

    else:
        raise HTTPException(400, f"Unknown asset type: {asset_type}")


@router.get("/{project_id}/download-step/{step}")
def download_step_assets(
    project_id: str,
    step: str,
    db: Session = Depends(get_db)
):
    """Download step assets as ZIP"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    project_dir = DATA_DIR / project_id
    step_dirs = {
        "script": ["script.json"],
        "audio": ["audio"],
        "image": ["images"],
        "video": ["videos"],
        "subtitle": ["subtitles"],
        "final": ["output"]
    }

    if step not in step_dirs:
        raise HTTPException(400, f"Unknown step: {step}")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in step_dirs[step]:
            item_path = project_dir / item

            if item.endswith(".json"):
                # Single file
                if item_path.exists():
                    zf.write(item_path, arcname=item)
            else:
                # Directory
                if item_path.exists() and item_path.is_dir():
                    for file_path in item_path.rglob("*"):
                        if file_path.is_file():
                            arcname = file_path.relative_to(project_dir)
                            zf.write(file_path, arcname=arcname)

    zip_buffer.seek(0)

    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_id}_{step}.zip"}
    )


@router.get("/{project_id}/download-all")
def download_entire_project(
    project_id: str,
    db: Session = Depends(get_db)
):
    """Download entire project as ZIP"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    project_dir = DATA_DIR / project_id

    if not project_dir.exists():
        raise HTTPException(404, "Project directory not found")

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in project_dir.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(project_dir.parent)
                zf.write(file_path, arcname=arcname)

    zip_buffer.seek(0)

    return StreamingResponse(
        iter([zip_buffer.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={project_id}_complete.zip"}
    )
