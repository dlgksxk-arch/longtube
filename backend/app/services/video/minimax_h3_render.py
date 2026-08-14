"""Render-stage orchestration for script cuts carrying a ``video_tag``.

H3 generation runs as the first expensive render operation, in cut order, on
one persistent service instance.  Raw H3 clips are cached separately from the
TTS-muxed cut clips so rerendering does not regenerate unchanged H3 motion.
"""
from __future__ import annotations

import hashlib
import json
import os
import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import (
    resolve_cut_audio_start_offset,
    resolve_cut_video_duration,
    resolve_cut_video_duration_for_audio,
)
from app.models.cut import Cut
from app.services.cancel_ctx import raise_if_cancelled
from app.services.image.asset_guard import find_existing_cut_image
from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.minimax_h3_service import (
    MODEL_ID,
    MiniMaxH3VideoService,
    video_tag_prompt,
)


_RAW_REVISION = "minimax-h3-render-v1-608x352-124f-20steps"
_BATCH_LOCK = threading.Lock()


@dataclass(frozen=True)
class TaggedH3Cut:
    cut_number: int
    video_tag: str
    aspect_ratio: str
    image_path: Path
    raw_path: Path
    fingerprint: str


def _absolute_project_asset(project_dir: Path, stored_path: str | None) -> Path | None:
    if not stored_path:
        return None
    path = Path(stored_path)
    if not path.is_absolute():
        path = project_dir / path
    try:
        if path.exists() and path.is_file() and path.stat().st_size > 50:
            return path
    except OSError:
        pass
    return None


def _source_fingerprint(image_path: Path, video_tag: str, aspect_ratio: str) -> str:
    stat = image_path.stat()
    payload = {
        "revision": _RAW_REVISION,
        "video_tag": video_tag,
        "aspect_ratio": aspect_ratio,
        "image_size": stat.st_size,
        "image_mtime_ns": stat.st_mtime_ns,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _marker_path(raw_path: Path) -> Path:
    return raw_path.with_suffix(raw_path.suffix + ".json")


def _raw_is_current(spec: TaggedH3Cut) -> bool:
    try:
        if not spec.raw_path.exists() or spec.raw_path.stat().st_size <= 1024:
            return False
        marker = json.loads(_marker_path(spec.raw_path).read_text(encoding="utf-8"))
        return marker.get("fingerprint") == spec.fingerprint
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def _write_marker(spec: TaggedH3Cut) -> None:
    marker_path = _marker_path(spec.raw_path)
    temporary = marker_path.with_suffix(marker_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "model": MODEL_ID,
                "revision": _RAW_REVISION,
                "cut_number": spec.cut_number,
                "fingerprint": spec.fingerprint,
                "image_path": str(spec.image_path),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    os.replace(temporary, marker_path)


def _collect_tagged_cuts(
    project_id: str,
    project_dir: Path,
    script_data: dict,
    db: Session,
    aspect_ratio: str,
) -> list[TaggedH3Cut]:
    db_cuts = {
        int(cut.cut_number): cut
        for cut in db.query(Cut).filter(Cut.project_id == project_id).all()
    }
    configured_aspect = str(aspect_ratio or "16:9")
    raw_dir = project_dir / "videos" / "minimax_h3_raw"
    specs: list[TaggedH3Cut] = []
    for cut_data in script_data.get("cuts", []) or []:
        if not isinstance(cut_data, dict):
            continue
        tag = video_tag_prompt(cut_data)
        if not tag:
            continue
        try:
            cut_number = int(cut_data.get("cut_number"))
        except (TypeError, ValueError):
            raise ValueError("영상 태그가 있는 컷의 cut_number가 올바르지 않습니다.")
        db_cut = db_cuts.get(cut_number)
        image_path = _absolute_project_asset(
            project_dir,
            getattr(db_cut, "image_path", None),
        )
        if image_path is None:
            image_path = find_existing_cut_image(project_dir, cut_number)
        if image_path is None:
            raise FileNotFoundError(
                f"MiniMax H3 영상 태그 컷 {cut_number}의 입력 이미지가 없습니다."
            )
        raw_path = raw_dir / f"cut_{cut_number:03d}.mp4"
        specs.append(
            TaggedH3Cut(
                cut_number=cut_number,
                video_tag=tag,
                aspect_ratio=configured_aspect,
                image_path=image_path,
                raw_path=raw_path,
                fingerprint=_source_fingerprint(image_path, tag, configured_aspect),
            )
        )
    return sorted(specs, key=lambda item: item.cut_number)


async def prepare_tagged_minimax_h3_raw_videos(
    project_id: str,
    project_dir: Path,
    script_data: dict,
    db: Session,
    *,
    aspect_ratio: str,
) -> list[TaggedH3Cut]:
    """Generate every stale tagged cut consecutively before normal rendering."""
    specs = _collect_tagged_cuts(
        project_id,
        project_dir,
        script_data,
        db,
        aspect_ratio,
    )
    pending = [spec for spec in specs if not _raw_is_current(spec)]
    if not specs:
        return []
    print(
        f"[minimax-h3/render] tagged={len(specs)} pending={len(pending)} "
        "phase=first-consecutive-batch"
    )
    if not pending:
        return specs

    # One process-wide lock prevents tagged batches from two simultaneous
    # renders from interleaving on the single H3 GPU queue.
    while not _BATCH_LOCK.acquire(blocking=False):
        raise_if_cancelled("minimax-h3-batch-lock")
        await asyncio.sleep(0.25)
    try:
        # Recheck after waiting: an earlier render may have completed the same
        # raw clips while this request was blocked on the batch lock.
        pending = [spec for spec in specs if not _raw_is_current(spec)]
        if not pending:
            return specs
        service = MiniMaxH3VideoService()
        await service.prepare_batch()
        for index, spec in enumerate(pending, start=1):
            spec.raw_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = spec.raw_path.with_suffix(".tmp.mp4")
            temporary.unlink(missing_ok=True)
            print(
                f"[minimax-h3/render] cut={spec.cut_number} "
                f"batch={index}/{len(pending)}"
            )
            try:
                await service.generate(
                    image_path=str(spec.image_path),
                    audio_path=None,
                    duration=5.0,
                    output_path=str(temporary),
                    aspect_ratio=aspect_ratio,
                    prompt=spec.video_tag,
                    audio_start_offset=0.0,
                )
                if not temporary.exists() or temporary.stat().st_size <= 1024:
                    raise RuntimeError(
                        f"MiniMax H3 컷 {spec.cut_number} 결과 파일이 비어 있습니다."
                    )
                os.replace(temporary, spec.raw_path)
                _write_marker(spec)
            finally:
                temporary.unlink(missing_ok=True)
    finally:
        _BATCH_LOCK.release()
    print(
        f"[minimax-h3/render] consecutive generation completed: {len(pending)} cuts; "
        "server and weights kept alive"
    )
    return specs


def _audio_path(project_dir: Path, cut: Cut) -> Path | None:
    stored = _absolute_project_asset(project_dir, cut.audio_path)
    if stored is not None:
        return stored
    for filename in (
        f"cut_{int(cut.cut_number):03d}.mp3",
        f"cut_{int(cut.cut_number)}.mp3",
        f"cut_{int(cut.cut_number):03d}.wav",
        f"cut_{int(cut.cut_number)}.wav",
    ):
        candidate = project_dir / "audio" / filename
        if candidate.exists() and candidate.is_file() and candidate.stat().st_size > 100:
            return candidate
    return None


async def mux_tagged_minimax_h3_videos(
    project_id: str,
    project_dir: Path,
    specs: list[TaggedH3Cut],
    db: Session,
    *,
    config: dict,
    resolution: str,
) -> int:
    """Mux the project's existing TTS onto the cached raw H3 clips."""
    if not specs:
        return 0
    cuts = {
        int(cut.cut_number): cut
        for cut in db.query(Cut).filter(Cut.project_id == project_id).all()
    }
    default_duration = resolve_cut_video_duration(config)
    audio_offset = resolve_cut_audio_start_offset(config)
    completed = 0
    for spec in specs:
        cut = cuts.get(spec.cut_number)
        if cut is None:
            raise RuntimeError(f"MiniMax H3 컷 {spec.cut_number} DB 항목이 없습니다.")
        audio_path = _audio_path(project_dir, cut)
        if audio_path is None:
            raise FileNotFoundError(
                f"MiniMax H3 컷 {spec.cut_number}의 TTS 오디오가 없습니다."
            )
        measured = await FFmpegService.probe_duration(str(audio_path))
        if measured > 0:
            cut.audio_duration = measured
        clip_duration = resolve_cut_video_duration_for_audio(
            config,
            measured or cut.audio_duration,
            default=default_duration,
        )
        # Keep the Step 5/static source clip intact. The DB points render to
        # this tagged derivative, and clearing the tag can immediately restore
        # the untouched base clip.
        final_path = project_dir / "videos" / "minimax_h3" / f"cut_{spec.cut_number:03d}.mp4"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = final_path.with_suffix(".minimax-h3.tmp.mp4")
        temporary.unlink(missing_ok=True)
        try:
            await FFmpegService.mux_cut_audio(
                video_path=str(spec.raw_path),
                audio_path=str(audio_path),
                output_path=str(temporary),
                duration=float(clip_duration),
                audio_start_offset=float(audio_offset),
                resolution=resolution,
            )
            if not temporary.exists() or temporary.stat().st_size <= 1024:
                raise RuntimeError(
                    f"MiniMax H3 컷 {spec.cut_number} TTS 결합 결과가 비어 있습니다."
                )
            os.replace(temporary, final_path)
        finally:
            temporary.unlink(missing_ok=True)
        cut.video_path = final_path.relative_to(project_dir).as_posix()
        cut.video_model = MODEL_ID
        cut.status = "completed"
        completed += 1
    db.commit()
    print(f"[minimax-h3/render] TTS mux completed: {completed} cuts")
    return completed
