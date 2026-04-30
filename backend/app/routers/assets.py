"""Project asset serving helpers.

The raw /assets mount exposes DATA_DIR, but new projects live under
_system/projects/{id} or channels/CHn/projects/{id}. This API route resolves
the real project folder first so frontend previews can use stable project IDs.
"""
import mimetypes
from pathlib import Path
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.config import resolve_project_dir
from app.models.database import get_db
from app.models.project import Project

router = APIRouter()


CHUNK_SIZE = 1024 * 1024


def _safe_relative_path(relative_path: str) -> Path:
    rel = Path(str(relative_path or "").replace("\\", "/"))
    if rel.is_absolute() or any(part in ("", ".", "..") for part in rel.parts):
        raise HTTPException(400, "Invalid asset path")
    return rel


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _iter_range(path: Path, start: int, end: int) -> Iterator[bytes]:
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = end - start + 1
        while remaining > 0:
            chunk = fh.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _parse_range(range_header: str, file_size: int) -> tuple[int, int]:
    if not range_header.lower().startswith("bytes="):
        raise HTTPException(416, "Invalid range unit")

    spec = range_header.split("=", 1)[1].split(",", 1)[0].strip()
    if "-" not in spec:
        raise HTTPException(416, "Invalid byte range")

    start_raw, end_raw = spec.split("-", 1)
    try:
        if start_raw == "":
            suffix = int(end_raw)
            if suffix <= 0:
                raise ValueError
            start = max(file_size - suffix, 0)
            end = file_size - 1
        else:
            start = int(start_raw)
            end = int(end_raw) if end_raw else file_size - 1
    except ValueError as exc:
        raise HTTPException(416, "Invalid byte range") from exc

    if start < 0 or end < start or start >= file_size:
        raise HTTPException(416, "Requested range not satisfiable")
    return start, min(end, file_size - 1)


def _range_not_satisfiable(file_size: int) -> Response:
    return Response(
        status_code=416,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes */{file_size}",
            "Cache-Control": "no-cache",
        },
    )


@router.get("/project/{project_id}/{relative_path:path}")
@router.head("/project/{project_id}/{relative_path:path}")
def get_project_asset(
    project_id: str,
    relative_path: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Return a generated asset by project id and project-relative path."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    project_dir = resolve_project_dir(project_id, config=project.config or {})
    rel = _safe_relative_path(relative_path)
    target = (project_dir / rel).resolve()
    base = project_dir.resolve()

    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(400, "Asset path escapes project directory")

    if not target.exists() or not target.is_file():
        raise HTTPException(404, "Asset not found")

    file_size = target.stat().st_size
    media_type = _media_type(target)
    common_headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-cache",
    }

    range_header = request.headers.get("range")
    if range_header:
        try:
            start, end = _parse_range(range_header, file_size)
        except HTTPException as exc:
            if exc.status_code == 416:
                return _range_not_satisfiable(file_size)
            raise

        headers = {
            **common_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(end - start + 1),
        }
        if request.method.upper() == "HEAD":
            return Response(status_code=206, headers=headers, media_type=media_type)
        return StreamingResponse(
            _iter_range(target, start, end),
            status_code=206,
            media_type=media_type,
            headers=headers,
        )

    headers = {
        **common_headers,
        "Content-Length": str(file_size),
    }
    if request.method.upper() == "HEAD":
        return Response(status_code=200, headers=headers, media_type=media_type)
    return FileResponse(target, media_type=media_type, headers=common_headers)
