"""Subtitle router"""
import json
import os
import re
import hashlib
import shutil
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import (
    CUT_VIDEO_DURATION,
    CHANNELS_ROOT,
    DATA_DIR,
    FIRST_CUT_FADE_IN_SECONDS,
    NARRATION_VOLUME_GAIN,
    SYSTEM_DIR,
    infer_project_channel,
    resolve_project_dir,
)
from app.services.subtitle_service import (
    DEFAULT_SUBTITLE_STYLE,
    burn_cut_subtitle_file,
    generate_ass,
    generate_srt,
)
from app.services.shorts_service import (
    load_script as load_shorts_script,
    render_shorts_from_final,
    select_shorts_segments,
)
from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess
from app.services.interlude_service import (
    DEFAULT_INTERMISSION_EVERY,
    INTERMISSION_CLIP_SECONDS,
    existing_kind_path,
)

router = APIRouter()

BGM_CHANNEL_LENGTH_MS = 180_000
FIRST_INTERMISSION_AFTER_CUTS = 3
DEFAULT_RENDER_BGM_VOLUME = 0.42
DEFAULT_RENDER_BGM_DUCKING = "low"
DEFAULT_RENDER_BGM_START_OFFSET_SEC = 60.0


def _channel_bgm_cache_path(project_id: str, cfg: dict | None, prompt: str) -> tuple[Path, str, str]:
    channel = infer_project_channel(project_id, cfg)
    if channel is not None:
        cache_dir = CHANNELS_ROOT / f"CH{channel}" / "bgm" / "cache"
        scope = f"CH{channel}"
    else:
        cache_dir = SYSTEM_DIR / "bgm" / "cache"
        scope = "system"
    cache_key = hashlib.sha1(
        f"channel-bgm-v1|{scope}|{prompt}|{BGM_CHANNEL_LENGTH_MS}".encode("utf-8")
    ).hexdigest()[:16]
    return cache_dir / f"{cache_key}_180s.mp3", scope, cache_key


def _is_channel_bgm_cache(path: str | Path) -> bool:
    p = Path(path)
    parts = {part.lower() for part in p.parts}
    return "bgm" in parts and "cache" in parts and (
        "channels" in parts or "_system" in parts
    )


def _intermission_every_cuts(project: Project) -> int:
    inter = (project.config or {}).get("interlude") or {}
    try:
        if inter.get("intermission_every_cuts"):
            every = int(inter.get("intermission_every_cuts"))
        elif inter.get("intermission_every_sec"):
            every = int(round(float(inter.get("intermission_every_sec")) / float(CUT_VIDEO_DURATION)))
        else:
            every = DEFAULT_INTERMISSION_EVERY
    except (TypeError, ValueError):
        every = DEFAULT_INTERMISSION_EVERY
    return max(1, every)


def _insert_intermissions_after_cuts(
    cut_paths: list[str],
    intermission_path: str | None,
    every_cuts: int,
) -> tuple[list[str], int]:
    sequence: list[str] = []
    intermission_count = 0
    every = max(1, int(every_cuts or DEFAULT_INTERMISSION_EVERY))

    for idx, path in enumerate(cut_paths):
        sequence.append(path)
        if not intermission_path or idx == len(cut_paths) - 1:
            continue

        cut_count = idx + 1
        should_insert = cut_count == FIRST_INTERMISSION_AFTER_CUTS
        if cut_count != FIRST_INTERMISSION_AFTER_CUTS and cut_count % every == 0:
            should_insert = True

        if should_insert:
            sequence.append(intermission_path)
            intermission_count += 1

    return sequence, intermission_count


async def _prepare_intermission_clip(input_path: str, output_path: str, resolution: str) -> str:
    return await _prepare_interlude_timeline_clip(
        input_path,
        output_path,
        resolution,
        duration=INTERMISSION_CLIP_SECONDS,
    )


async def _prepare_interlude_timeline_clip(
    input_path: str,
    output_path: str,
    resolution: str,
    *,
    duration: float | None = None,
) -> str:
    pad_wh = resolution.replace("x", ":")
    vf = (
        f"scale={resolution}:force_original_aspect_ratio=decrease,"
        f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p"
    )
    af = "volume=0.0000,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=mono"
    if duration is not None:
        af = f"apad,{af}"
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-vf", vf,
        "-map", "0:v:0",
        "-map", "0:a?",
        "-af", af,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
        "-video_track_timescale", "15360",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    if duration is not None:
        cmd[4:4] = ["-t", f"{float(duration):.3f}"]
    await FFmpegService._run_ffmpeg(cmd, timeout=180.0)
    return output_path


def _load_script(project_id: str) -> dict:
    """Load script.json from disk"""
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_and_write_ass(project_id: str, project: Project, db: Session) -> tuple[str, int]:
    """Build cut data, render ASS/SRT, and persist subtitle files to disk.

    Shared by the explicit generate endpoint and the auto-generation path
    inside the render endpoint.

    Returns: (subtitle_path, cut_count)
    Raises: HTTPException on missing data.
    """
    script = _load_script(project_id)
    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()

    if not cuts or not script.get("cuts"):
        raise HTTPException(400, "No cuts or script found")

    cuts_data = []
    for cut in cuts:
        cut_script = next((c for c in script.get("cuts", []) if c["cut_number"] == cut.cut_number), {})
        spoken_duration = getattr(cut, "audio_original_duration", None) or cut.audio_duration
        cuts_data.append({
            "cut_number": cut.cut_number,
            "narration": cut.narration or cut_script.get("narration", ""),
            "actual_duration": spoken_duration,
            "duration_estimate": cut_script.get("duration_estimate", 5.0)
        })

    style_config = project.config.get("subtitle_style", dict(DEFAULT_SUBTITLE_STYLE))
    aspect_ratio = project.config.get("aspect_ratio", "16:9")

    ass_content = generate_ass(cuts_data, style_config, aspect_ratio)

    subtitle_dir = DATA_DIR / project_id / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = subtitle_dir / "subtitles.ass"

    with open(subtitle_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

    srt_path = subtitle_dir / "subtitles.srt"
    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(generate_srt(cuts_data))

    return str(subtitle_path), len(cuts_data)


@router.post("/{project_id}/generate")
def generate_subtitles(project_id: str, db: Session = Depends(get_db)):
    """Generate ASS subtitle file"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        subtitle_path, count = _build_and_write_ass(project_id, project, db)

        # v1.1.32 이후: 프런트에서 호출되지는 않지만 호환성 위해 남겨둠.
        # 별도 step_states 업데이트는 하지 않는다 (렌더링 스텝 6에서 일괄 처리).

        return {
            "status": "generated",
            "path": subtitle_path,
            "srt_path": str(DATA_DIR / project_id / "subtitles" / "subtitles.srt"),
            "cuts": count,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Subtitle generation failed: {str(e)}")


def _abs_cut_path(project_id: str, rel_path: str) -> str:
    """Convert a cut.video_path (stored as relative) to an absolute path."""
    if not rel_path:
        return ""
    from pathlib import Path as _P
    p = _P(rel_path)
    if p.is_absolute():
        return str(p)
    return str(DATA_DIR / project_id / rel_path)


def _safe_audio_ext(filename: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return ext if ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"} else ".mp3"


@router.post("/{project_id}/bgm/upload")
async def upload_render_bgm(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    content_type = (file.content_type or "").lower()
    if content_type and not content_type.startswith("audio/") and content_type not in {
        "application/octet-stream",
        "video/mp4",
    }:
        raise HTTPException(400, "오디오 파일만 업로드할 수 있습니다.")

    content = await file.read()
    if not content:
        raise HTTPException(400, "빈 파일입니다.")

    try:
        cfg = dict(project.config or {})
        bgm_dir = resolve_project_dir(project_id, cfg, create=True) / "bgm"
        bgm_dir.mkdir(parents=True, exist_ok=True)
        ext = _safe_audio_ext(file.filename or "")
        safe_stem = re.sub(r"[^0-9A-Za-z가-힣_.-]+", "_", os.path.splitext(file.filename or "bgm")[0]).strip("._")
        if not safe_stem:
            safe_stem = "bgm"
        bgm_path = bgm_dir / f"{safe_stem}{ext}"
        with open(bgm_path, "wb") as f:
            f.write(content)

        cfg["bgm_enabled"] = True
        cfg["bgm_path"] = f"bgm/{bgm_path.name}"
        cfg["bgm_volume"] = float(cfg.get("bgm_volume", DEFAULT_RENDER_BGM_VOLUME) or DEFAULT_RENDER_BGM_VOLUME)
        cfg["bgm_ducking_strength"] = str(cfg.get("bgm_ducking_strength") or DEFAULT_RENDER_BGM_DUCKING)
        cfg["bgm_start_offset_sec"] = float(
            cfg.get("bgm_start_offset_sec", DEFAULT_RENDER_BGM_START_OFFSET_SEC)
            or DEFAULT_RENDER_BGM_START_OFFSET_SEC
        )
        if isinstance(cfg.get("audio"), dict):
            cfg["audio"]["bgm_enabled"] = True
            cfg["audio"]["bgm_path"] = cfg["bgm_path"]
            cfg["audio"]["bgm_volume"] = cfg["bgm_volume"]
            cfg["audio"]["bgm_ducking_strength"] = cfg["bgm_ducking_strength"]
            cfg["audio"]["bgm_start_offset_sec"] = cfg["bgm_start_offset_sec"]
        project.config = cfg
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "config")
        db.commit()
        return {
            "status": "uploaded",
            "path": cfg["bgm_path"],
            "filename": bgm_path.name,
            "size": len(content),
            "enabled": True,
            "volume": cfg["bgm_volume"],
        }
    except Exception as e:
        raise HTTPException(500, f"BGM upload failed: {str(e)}")


@router.post("/{project_id}/bgm/generate")
async def generate_render_bgm(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = dict(project.config or {})
    from app.services.bgm_service import build_bgm_prompt, generate_bgm

    prompt = build_bgm_prompt(
        topic="",
        title="",
        style_prompt=str(cfg.get("bgm_style_prompt") or ""),
        language=str(cfg.get("language") or "ko"),
    )
    length_ms = BGM_CHANNEL_LENGTH_MS
    bgm_abs, bgm_scope, cache_key = _channel_bgm_cache_path(project_id, cfg, prompt)
    bgm_abs.parent.mkdir(parents=True, exist_ok=True)
    bgm_path_value = str(bgm_abs)

    try:
        if bgm_abs.exists() and bgm_abs.is_file() and bgm_abs.stat().st_size > 0:
            result = {
                "path": str(bgm_abs),
                "size": bgm_abs.stat().st_size,
                "length_ms": length_ms,
                "prompt": prompt,
                "cached": True,
            }
        else:
            result = await generate_bgm(prompt=prompt, output_path=bgm_abs, length_ms=length_ms)
        cfg["bgm_enabled"] = True
        cfg["bgm_path"] = bgm_path_value
        cfg["bgm_prompt_used"] = prompt
        cfg["bgm_scope"] = bgm_scope
        cfg["bgm_cache_key"] = cache_key
        cfg["bgm_volume"] = float(cfg.get("bgm_volume", DEFAULT_RENDER_BGM_VOLUME) or DEFAULT_RENDER_BGM_VOLUME)
        cfg["bgm_ducking_strength"] = str(cfg.get("bgm_ducking_strength") or DEFAULT_RENDER_BGM_DUCKING)
        cfg["bgm_start_offset_sec"] = float(
            cfg.get("bgm_start_offset_sec", DEFAULT_RENDER_BGM_START_OFFSET_SEC)
            or DEFAULT_RENDER_BGM_START_OFFSET_SEC
        )
        if isinstance(cfg.get("audio"), dict):
            cfg["audio"]["bgm_enabled"] = True
            cfg["audio"]["bgm_path"] = bgm_path_value
            cfg["audio"]["bgm_prompt_used"] = prompt
            cfg["audio"]["bgm_scope"] = bgm_scope
            cfg["audio"]["bgm_cache_key"] = cache_key
            cfg["audio"]["bgm_volume"] = cfg["bgm_volume"]
            cfg["audio"]["bgm_ducking_strength"] = cfg["bgm_ducking_strength"]
            cfg["audio"]["bgm_start_offset_sec"] = cfg["bgm_start_offset_sec"]
        project.config = cfg
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "config")
        db.commit()
        return {
            "status": "generated",
            "path": cfg["bgm_path"],
            "scope": bgm_scope,
            "size": result["size"],
            "length_ms": result["length_ms"],
            "prompt": prompt,
            "enabled": True,
            "volume": cfg["bgm_volume"],
            "cached": bool(result.get("cached")),
        }
    except Exception as e:
        raise HTTPException(500, f"BGM generation failed: {str(e)}")


@router.delete("/{project_id}/bgm")
def delete_render_bgm(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cfg = dict(project.config or {})
    rel_path = str(cfg.get("bgm_path") or "")
    deleted = False
    if rel_path:
        try:
            raw_path = Path(rel_path)
            path = raw_path if raw_path.is_absolute() else resolve_project_dir(project_id, cfg, create=False) / rel_path
            if path.exists() and path.is_file():
                if _is_channel_bgm_cache(path):
                    deleted = False
                else:
                    path.unlink()
                    deleted = True
        except Exception:
            deleted = False
    cfg["bgm_enabled"] = False
    cfg["bgm_path"] = ""
    if isinstance(cfg.get("audio"), dict):
        cfg["audio"]["bgm_enabled"] = False
        cfg["audio"]["bgm_path"] = ""
    project.config = cfg
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "config")
    db.commit()
    return {"ok": True, "deleted": deleted}


async def _video_has_audio(ffmpeg_bin: str, video_path: str) -> bool:
    """Return True if the video file contains at least one audio stream.

    We run ``ffmpeg -hide_banner -i <file>`` which exits non-zero but always
    prints the stream list to stderr, and look for ``" Audio:"`` in the
    output. This avoids needing a separate ffprobe binary.
    """
    try:
        _, _, stderr = await run_subprocess(
            [ffmpeg_bin, "-hide_banner", "-i", video_path],
            timeout=30.0,
            capture_stdout=False,
            capture_stderr=True,
        )
    except Exception as e:
        print(f"[subtitle/render] audio probe failed for {video_path}: {e}")
        # On probe failure, assume audio is present so we don't corrupt a
        # good file by re-muxing.
        return True
    text = (stderr or b"").decode("utf-8", errors="replace")
    return " Audio:" in text


async def _heal_cut_audio(project_id: str, db: Session) -> dict:
    """For every cut whose video file is missing its audio track, mux the
    cut's TTS audio file into the video in place.

    This exists because earlier versions of fal_service silently skipped the
    audio mux step when ffmpeg couldn't be located, leaving video clips on
    disk without any audio stream. Those files then flow through merge and
    burn_subtitles unchanged, producing a silent final render.

    Returns a small summary dict for logging.
    """
    summary = {"checked": 0, "healed": 0, "skipped_no_audio_file": 0, "failed": 0}
    try:
        ffmpeg_bin = find_ffmpeg()
    except RuntimeError as e:
        print(f"[subtitle/render] audio heal skipped — ffmpeg not found: {e}")
        return summary

    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number)
        .all()
    )
    for cut in cuts:
        if not cut.video_path:
            continue
        vp = _abs_cut_path(project_id, cut.video_path)
        if not vp or not os.path.exists(vp):
            continue
        summary["checked"] += 1

        if await _video_has_audio(ffmpeg_bin, vp):
            continue

        # Video is silent — try to mux the cut's TTS audio into it in place.
        audio_rel = cut.audio_path or ""
        audio_abs = _abs_cut_path(project_id, audio_rel) if audio_rel else ""
        if not audio_abs or not os.path.exists(audio_abs):
            print(
                f"[subtitle/render] cut {cut.cut_number} video has no audio AND "
                f"no TTS file on disk → leaving silent"
            )
            summary["skipped_no_audio_file"] += 1
            continue

        print(
            f"[subtitle/render] cut {cut.cut_number} video is silent — muxing "
            f"TTS audio: {os.path.basename(audio_abs)} → {os.path.basename(vp)}"
        )
        tmp_path = vp + ".mux.mp4"
        mux_cmd = [
            ffmpeg_bin, "-y",
            "-i", vp,
            "-i", audio_abs,
            "-map", "0:v", "-map", "1:a",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            tmp_path,
        ]
        try:
            rc, _, stderr = await run_subprocess(
                mux_cmd, timeout=300.0, capture_stdout=False, capture_stderr=True
            )
        except Exception as e:
            print(f"[subtitle/render] cut {cut.cut_number} mux exception: {e}")
            summary["failed"] += 1
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            continue

        if rc == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            try:
                os.replace(tmp_path, vp)
                summary["healed"] += 1
            except Exception as e:
                print(f"[subtitle/render] cut {cut.cut_number} replace failed: {e}")
                summary["failed"] += 1
        else:
            err_tail = (stderr or b"").decode(errors="replace")[-300:]
            print(
                f"[subtitle/render] cut {cut.cut_number} mux failed rc={rc}: {err_tail}"
            )
            summary["failed"] += 1
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    return summary


def _resolution_for_aspect(aspect_ratio: str, target_resolution: str = "1080p") -> str:
    if str(target_resolution).lower() in {"1080", "1080p", "fullhd", "fhd"}:
        if aspect_ratio == "9:16":
            return "1080x1920"
        if aspect_ratio == "1:1":
            return "1080x1080"
        if aspect_ratio == "3:4":
            return "1080x1440"
        return "1920x1080"
    if aspect_ratio == "9:16":
        return "720x1280"
    if aspect_ratio == "1:1":
        return "720x720"
    if aspect_ratio == "3:4":
        return "720x960"
    return "1280x720"


def _resolve_interlude_path(project_id: str, project: Project, kind: str) -> str | None:
    """project.config['interlude'][kind].video_path 또는 실제 업로드 파일 경로."""
    inter = (project.config or {}).get("interlude") or {}
    entry = inter.get(kind) or {}
    vp = entry.get("video_path")
    if vp:
        from pathlib import Path as _P
        p = _P(vp)
        if not p.is_absolute():
            p = resolve_project_dir(project_id, project.config or {}, create=False) / vp
        if p.exists() and p.is_file():
            return str(p)

    fallback = existing_kind_path(
        resolve_project_dir(project_id, project.config or {}, create=False) / "interlude",
        kind,
    )
    return str(fallback) if fallback else None


def _resolve_bgm_path(project_id: str, project: Project) -> str | None:
    cfg = project.config or {}
    bgm_cfg = _read_bgm_config(cfg)
    if not bgm_cfg["enabled"]:
        return None
    raw = str(bgm_cfg["path"] or "").strip()
    if not raw:
        return None
    from pathlib import Path as _P
    p = _P(raw)
    if not p.is_absolute():
        p = resolve_project_dir(project_id, cfg, create=False) / raw
    if p.exists() and p.is_file():
        return str(p)

    template_project_id = str(cfg.get("template_project_id") or "").strip()
    if template_project_id and not _P(raw).is_absolute():
        tp = resolve_project_dir(template_project_id, create=False) / raw
        if tp.exists() and tp.is_file():
            return str(tp)
    return None


def _read_bgm_config(cfg: dict | None) -> dict:
    data = cfg or {}
    audio = data.get("audio") if isinstance(data.get("audio"), dict) else {}

    enabled_raw = data.get("bgm_enabled", audio.get("bgm_enabled", False))
    path = data.get("bgm_path", audio.get("bgm_path", ""))
    style_prompt = data.get("bgm_style_prompt", audio.get("bgm_style_prompt", ""))
    ducking = str(
        data.get(
            "bgm_ducking_strength",
            data.get("ducking_strength", audio.get("ducking_strength", "normal")),
        )
        or "normal"
    ).strip().lower()
    if ducking not in {"low", "normal", "strong", "off", "none", "disabled"}:
        ducking = "normal"

    def _to_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "y", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "n", "off", "disabled", "none", ""}:
            return False
        return bool(value)

    def _to_float(value, default: float = 0.0) -> float:
        try:
            if value is not None and str(value).strip() != "":
                return float(value)
        except Exception:
            pass
        return default

    volume = data.get("bgm_volume", audio.get("bgm_volume", None))
    if volume is None:
        db_value = data.get("bgm_volume_db", audio.get("bgm_volume_db", None))
        try:
            if db_value is not None and str(db_value).strip() != "":
                volume = 10 ** (float(db_value) / 20.0)
        except Exception:
            volume = None

    try:
        volume_f = float(volume if volume is not None else DEFAULT_RENDER_BGM_VOLUME)
    except Exception:
        volume_f = DEFAULT_RENDER_BGM_VOLUME

    if (
        data.get("bgm_ducking_strength") is None
        and data.get("ducking_strength") is None
        and audio.get("ducking_strength") is None
    ):
        ducking = DEFAULT_RENDER_BGM_DUCKING

    return {
        "enabled": _to_bool(enabled_raw),
        "path": str(path or ""),
        "style_prompt": str(style_prompt or ""),
        "volume": max(0.0, min(1.0, volume_f)),
        "ducking_strength": ducking,
        "start_offset_sec": max(0.0, min(170.0, _to_float(data.get("bgm_start_offset_sec", audio.get("bgm_start_offset_sec", None)), DEFAULT_RENDER_BGM_START_OFFSET_SEC))),
        "fade_in_sec": max(0.0, min(30.0, _to_float(data.get("fade_in_sec", audio.get("fade_in_sec", None)), 0.0))),
        "fade_out_sec": max(0.0, min(30.0, _to_float(data.get("fade_out_sec", audio.get("fade_out_sec", None)), 0.0))),
    }


def _subtitle_delivery_mode(cfg: dict | None) -> str:
    data = cfg or {}
    mode = str(data.get("subtitle_delivery") or data.get("subtitle_mode") or "").strip().lower()
    if mode in {"youtube", "youtube_caption", "youtube_captions", "srt", "external"}:
        return "youtube_caption"
    if mode in {"none", "off", "disabled"}:
        return "none"
    return "burn"


async def _ensure_bgm_for_render(project_id: str, project: Project, db: Session) -> str | None:
    cfg = dict(project.config or {})
    bgm_cfg = _read_bgm_config(cfg)
    if not bgm_cfg["enabled"]:
        return None

    existing = _resolve_bgm_path(project_id, project)
    if existing and not _is_channel_bgm_cache(existing):
        return existing

    from app.services.bgm_service import build_bgm_prompt, generate_bgm

    prompt = build_bgm_prompt(
        topic="",
        title="",
        style_prompt=str(bgm_cfg["style_prompt"] or ""),
        language=str(cfg.get("language") or "ko"),
    )
    length_ms = BGM_CHANNEL_LENGTH_MS
    bgm_abs, bgm_scope, cache_key = _channel_bgm_cache_path(project_id, cfg, prompt)
    bgm_abs.parent.mkdir(parents=True, exist_ok=True)
    bgm_path_value = str(bgm_abs)

    if bgm_abs.exists() and bgm_abs.is_file() and bgm_abs.stat().st_size > 0:
        cfg["bgm_path"] = bgm_path_value
        cfg["bgm_prompt_used"] = prompt
        cfg["bgm_scope"] = bgm_scope
        cfg["bgm_cache_key"] = cache_key
        cfg["bgm_volume"] = float(cfg.get("bgm_volume", bgm_cfg["volume"]) or bgm_cfg["volume"])
        cfg["bgm_ducking_strength"] = str(cfg.get("bgm_ducking_strength") or bgm_cfg["ducking_strength"])
        cfg["bgm_start_offset_sec"] = float(
            cfg.get("bgm_start_offset_sec", bgm_cfg["start_offset_sec"])
            or bgm_cfg["start_offset_sec"]
        )
        if isinstance(cfg.get("audio"), dict):
            cfg["audio"]["bgm_enabled"] = True
            cfg["audio"]["bgm_path"] = bgm_path_value
            cfg["audio"]["bgm_prompt_used"] = prompt
            cfg["audio"]["bgm_scope"] = bgm_scope
            cfg["audio"]["bgm_cache_key"] = cache_key
            cfg["audio"]["bgm_volume"] = cfg["bgm_volume"]
            cfg["audio"]["bgm_ducking_strength"] = cfg["bgm_ducking_strength"]
            cfg["audio"]["bgm_start_offset_sec"] = cfg["bgm_start_offset_sec"]
        project.config = cfg
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "config")
        db.commit()
        print(f"[subtitle/render] channel BGM cache reused ({bgm_scope}): {bgm_abs}")
        return str(bgm_abs)

    print(f"[subtitle/render] generating BGM via ElevenLabs Music ({length_ms}ms): {prompt!r}")
    result = await generate_bgm(
        prompt=prompt,
        output_path=bgm_abs,
        length_ms=length_ms,
    )
    cfg["bgm_path"] = bgm_path_value
    cfg["bgm_prompt_used"] = prompt
    cfg["bgm_scope"] = bgm_scope
    cfg["bgm_cache_key"] = cache_key
    cfg["bgm_volume"] = float(cfg.get("bgm_volume", bgm_cfg["volume"]) or bgm_cfg["volume"])
    cfg["bgm_ducking_strength"] = str(cfg.get("bgm_ducking_strength") or bgm_cfg["ducking_strength"])
    cfg["bgm_start_offset_sec"] = float(
        cfg.get("bgm_start_offset_sec", bgm_cfg["start_offset_sec"])
        or bgm_cfg["start_offset_sec"]
    )
    if isinstance(cfg.get("audio"), dict):
        cfg["audio"]["bgm_enabled"] = True
        cfg["audio"]["bgm_path"] = bgm_path_value
        cfg["audio"]["bgm_prompt_used"] = prompt
        cfg["audio"]["bgm_scope"] = bgm_scope
        cfg["audio"]["bgm_cache_key"] = cache_key
        cfg["audio"]["bgm_volume"] = cfg["bgm_volume"]
        cfg["audio"]["bgm_ducking_strength"] = cfg["bgm_ducking_strength"]
        cfg["audio"]["bgm_start_offset_sec"] = cfg["bgm_start_offset_sec"]
    project.config = cfg
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "config")
    db.commit()
    print(
        f"[subtitle/render] channel BGM generated ({bgm_scope}): {bgm_abs} "
        f"size={result.get('size')} length_ms={result.get('length_ms')}"
    )
    return str(bgm_abs)


async def _mix_bgm_into_video(
    input_path: str,
    bgm_path: str,
    output_path: str,
    volume: float,
    *,
    ducking_strength: str = "normal",
    start_offset_sec: float = 0.0,
    fade_in_sec: float = 0.0,
    fade_out_sec: float = 0.0,
) -> str:
    ffmpeg_bin = find_ffmpeg()
    vol = max(0.0, min(1.0, float(volume)))
    narration_gain = max(0.5, min(4.0, float(NARRATION_VOLUME_GAIN)))
    has_audio = await _video_has_audio(ffmpeg_bin, input_path)
    duration = await FFmpegService.probe_duration(input_path)
    bgm_offset = max(0.0, min(170.0, float(start_offset_sec or 0.0)))
    fade_in = max(0.0, min(float(fade_in_sec or 0.0), max(0.0, duration / 2) if duration > 0 else 30.0))
    fade_out = max(0.0, min(float(fade_out_sec or 0.0), max(0.0, duration / 2) if duration > 0 else 30.0))
    bgm_filters = [
        f"volume={vol:.4f}",
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo",
    ]
    if fade_in > 0:
        bgm_filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0 and duration > 0:
        bgm_filters.append(f"afade=t=out:st={max(0.0, duration - fade_out):.3f}:d={fade_out:.3f}")
    bgm_filter = ",".join(bgm_filters)

    if has_audio:
        duck = str(ducking_strength or "normal").strip().lower()
        filter_complex = (
            f"[1:a]{bgm_filter}[bgm];"
            f"[0:a]volume={narration_gain:.4f},"
            f"aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[main];"
        )
        if duck in {"low", "normal", "strong"}:
            duck_params = {
                "low": ("0.150", "1.5"),
                "normal": ("0.100", "2.5"),
                "strong": ("0.050", "5"),
            }[duck]
            threshold, ratio = duck_params
            filter_complex += (
                f"[bgm][main]sidechaincompress=threshold={threshold}:ratio={ratio}:"
                f"attack=80:release=650[ducked];"
                f"[main][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                f"alimiter=limit=0.55:level=false[aout]"
            )
        else:
            filter_complex += (
                f"[main][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
                f"alimiter=limit=0.55:level=false[aout]"
            )
    else:
        filter_complex = (
            f"[1:a]{bgm_filter}[aout]"
        )
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-stream_loop", "-1",
        "-ss", f"{bgm_offset:.3f}",
        "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-map", "0:v:0",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        output_path,
    ]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=900.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        err_tail = (stderr or b"").decode(errors="replace")[-800:]
        raise RuntimeError(f"BGM mix failed: {err_tail}")
    return output_path


async def _apply_narration_gain_to_video(
    input_path: str,
    output_path: str,
) -> str:
    ffmpeg_bin = find_ffmpeg()
    if not await _video_has_audio(ffmpeg_bin, input_path):
        shutil.copyfile(input_path, output_path)
        return output_path

    narration_gain = max(0.5, min(4.0, float(NARRATION_VOLUME_GAIN)))
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-map", "0:v:0",
        "-map", "0:a:0",
        "-c:v", "copy",
        "-af", f"volume={narration_gain:.4f},alimiter=limit=0.55:level=false",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-shortest",
        output_path,
    ]
    rc, _, stderr = await run_subprocess(
        cmd,
        timeout=600.0,
        capture_stdout=False,
        capture_stderr=True,
    )
    if rc != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
        err_tail = (stderr or b"").decode(errors="replace")[-800:]
        raise RuntimeError(f"Narration gain failed: {err_tail}")
    return output_path


@router.post("/{project_id}/render")
async def render_video_with_subtitles(project_id: str, db: Session = Depends(get_db)):
    """Render final video with subtitles + 5s min per cut + opening/ending fade.

    파이프라인(v1.1.32 이후):
      1. 자막 ASS 자동 생성 (설정 기반)
      2. 컷 오디오 무음 치유
      3. 각 컷을 최소 5초로 보정(필요 시 루프)
      4. 본편 컷 재인코딩 concat → body.mp4
      5. body.mp4 에 자막 번인 → body_sub.mp4
      6. opening/ending 업로드가 있으면 2초 페이드 인/아웃 추가
      7. [opening_faded?] + body_sub + [ending_faded?] → final_with_subtitles.mp4
    """
    import time as _t

    t0 = _t.time()
    print(f"[subtitle/render] START project={project_id}")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    video_dir = DATA_DIR / project_id / "videos"
    subtitle_dir = DATA_DIR / project_id / "subtitles"
    output_dir = DATA_DIR / project_id / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = DATA_DIR / project_id / "tmp_render"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    subtitle_file = subtitle_dir / "subtitles.ass"
    output_path = output_dir / "final_with_subtitles.mp4"

    aspect_ratio = (project.config or {}).get("aspect_ratio", "16:9")
    target_resolution = (project.config or {}).get("render_resolution", "1080p")
    resolution = _resolution_for_aspect(aspect_ratio, target_resolution)

    # v1.1.55: 컷 단계에서 이미 자막을 번인했으면 본편 단계의 ASS 생성/번인은
    # 건너뛴다. 머지 후 자막 입히면 ensure_min_duration 등으로 컷 길이가
    # 변형돼 싱크가 깨지는 사고 차단. 기본 True — 옛 프로젝트는 config 에서
    # Global policy: subtitles are burned into each cut video during video
    # generation. Final render must not burn a second subtitle layer.
    cut_level_subs = True
    subtitle_delivery = _subtitle_delivery_mode(project.config or {})
    burn_main_subtitles = subtitle_delivery == "burn"

    if not cut_level_subs or subtitle_delivery == "youtube_caption":
        # ── Step 1: 자막 ASS 항상 새로 생성 (설정값이 바뀌었을 수 있음) ──
        try:
            print(f"[subtitle/render] generating subtitle ASS → {subtitle_file}")
            t_sub = _t.time()
            _build_and_write_ass(project_id, project, db)
            print(f"[subtitle/render] ASS generated in {_t.time()-t_sub:.1f}s")
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"[subtitle/render] ASS GEN FAILED: {e}\n{traceback.format_exc()}")
            raise HTTPException(500, f"Subtitle generation failed: {type(e).__name__}: {e}")
        if not subtitle_file.exists():
            raise HTTPException(500, "Generated subtitle file is missing")
    else:
        print("[subtitle/render] cut_level_subtitles=True — 본편 ASS 생성 건너뜀")

    # ── Step 2: 음성 누락 치유 ──
    try:
        t_heal = _t.time()
        heal_summary = await _heal_cut_audio(project_id, db)
        print(f"[subtitle/render] audio heal done in {_t.time()-t_heal:.1f}s: {heal_summary}")
    except Exception as e:
        import traceback
        print(f"[subtitle/render] audio heal EXCEPTION (non-fatal): {e}\n{traceback.format_exc()}")

    if not cut_level_subs or subtitle_delivery == "youtube_caption":
        # Audio heal/mux can update DB timing fields. Regenerate subtitles after
        # that step so burn-in and caption files use the final spoken timings.
        try:
            print(f"[subtitle/render] regenerating subtitle ASS after audio heal → {subtitle_file}")
            t_sub = _t.time()
            _build_and_write_ass(project_id, project, db)
            print(f"[subtitle/render] ASS regenerated in {_t.time()-t_sub:.1f}s")
        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"[subtitle/render] ASS REGEN FAILED: {e}\n{traceback.format_exc()}")
            raise HTTPException(500, f"Subtitle regeneration failed: {type(e).__name__}: {e}")

    # ── Step 3: 각 컷 최소 5초 보정 ──
    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number)
        .all()
    )
    script_cut_map = {
        int(item.get("cut_number")): item
        for item in (_load_script(project_id).get("cuts", []) or [])
        if item.get("cut_number") is not None
    }
    subtitle_style_cfg = (project.config or {}).get("subtitle_style") or {}
    clip_paths: list[str] = []
    video_dir_path = DATA_DIR / project_id / "videos"
    for c in cuts:
        # v1.1.55: DB video_path 우선, 없으면 디스크 파일 폴백
        ap = ""
        if c.video_path:
            ap = _abs_cut_path(project_id, c.video_path)
        # DB 에 경로가 없거나 파일이 없으면 규칙 기반 경로로 폴백
        if not ap or not os.path.exists(ap):
            fallback = str(video_dir_path / f"cut_{c.cut_number:03d}.mp4")
            if os.path.exists(fallback):
                ap = fallback
                # DB 도 보정
                c.video_path = f"videos/cut_{c.cut_number:03d}.mp4"
            else:
                print(f"[subtitle/render] Cut {c.cut_number}: 영상 파일 없음 — 건너뜀")
                continue
        if cut_level_subs:
            narration = (
                (c.narration or "").strip()
                or (script_cut_map.get(int(c.cut_number), {}) or {}).get("narration", "").strip()
            )
            if narration:
                try:
                    await burn_cut_subtitle_file(
                        ap,
                        narration,
                        aspect_ratio=aspect_ratio,
                        style_config=subtitle_style_cfg,
                        duration=float(CUT_VIDEO_DURATION),
                    )
                except Exception as e:
                    print(f"[subtitle/render] Cut {c.cut_number}: cut subtitle burn failed: {e}")
        clip_paths.append(ap)

    db.commit()  # DB 보정 반영

    if not clip_paths:
        raise HTTPException(
            400,
            "컷 영상이 없습니다. 영상 생성 단계를 먼저 완료하세요.",
        )

    print(f"[subtitle/render] {len(clip_paths)}/{len(cuts)} 컷 영상 수집 완료")

    MIN_CUT_DURATION = float(CUT_VIDEO_DURATION)
    normalized_cuts: list[str] = []
    preserve_cut_audio = bool(cut_level_subs)
    if preserve_cut_audio:
        normalized_cuts = list(clip_paths)
        print(
            f"[subtitle/render] preserving original cut audio "
            f"({len(normalized_cuts)} cuts; normalization skipped)"
        )
    else:
        try:
            t_norm = _t.time()
            for idx, cp in enumerate(clip_paths, start=1):
                norm_out = str(tmp_dir / f"norm_{idx:03d}.mp4")
                await FFmpegService.ensure_min_duration(
                    cp, norm_out, min_seconds=MIN_CUT_DURATION, resolution=resolution
                )
                if idx == 1 and FIRST_CUT_FADE_IN_SECONDS > 0:
                    fade_out = str(tmp_dir / "norm_001_fadein.mp4")
                    await FFmpegService.add_fade_in(
                        norm_out,
                        fade_out,
                        fade_seconds=min(float(FIRST_CUT_FADE_IN_SECONDS), MIN_CUT_DURATION),
                        resolution=resolution,
                    )
                    normalized_cuts.append(fade_out)
                else:
                    normalized_cuts.append(norm_out)
            print(
                f"[subtitle/render] normalized {len(normalized_cuts)} cuts "
                f"(min={MIN_CUT_DURATION}s) in {_t.time()-t_norm:.1f}s"
            )
        except Exception as e:
            import traceback
            print(f"[subtitle/render] NORMALIZE FAILED: {e}\n{traceback.format_exc()}")
            raise HTTPException(500, f"Cut normalization failed: {type(e).__name__}: {e}")

    # ── Step 4: 본편 concat (재인코딩) ──
    shorts_body_path = str(tmp_dir / "shorts_body_no_interludes.mp4")
    try:
        t_shorts_body = _t.time()
        if preserve_cut_audio:
            await FFmpegService.merge_videos(normalized_cuts, shorts_body_path)
        else:
            await FFmpegService.merge_videos_reencode(
                normalized_cuts, shorts_body_path, resolution=resolution
            )
        print(
            f"[subtitle/render] shorts source merged without opening/intermission/ending "
            f"in {_t.time()-t_shorts_body:.1f}s"
        )
    except Exception as e:
        import traceback
        shorts_body_path = ""
        print(f"[subtitle/render] SHORTS SOURCE MERGE FAILED: {e}\n{traceback.format_exc()}")

    intermission_raw = _resolve_interlude_path(project_id, project, "intermission")
    body_sequence = normalized_cuts
    intermission_count = 0
    if intermission_raw:
        every = _intermission_every_cuts(project)
        intermission_clip = await _prepare_intermission_clip(
            intermission_raw,
            str(tmp_dir / "intermission_3s.mp4"),
            resolution,
        )
        body_sequence, intermission_count = _insert_intermissions_after_cuts(
            normalized_cuts,
            intermission_clip,
            every,
        )
        print(
            f"[subtitle/render] intermission inserted count={intermission_count} "
            f"first_after={FIRST_INTERMISSION_AFTER_CUTS} cuts every={every} cuts "
            f"duration={INTERMISSION_CLIP_SECONDS:.1f}s"
        )

    body_path = str(tmp_dir / "body.mp4")
    try:
        t_body = _t.time()
        if preserve_cut_audio:
            await FFmpegService.merge_videos(body_sequence, body_path)
        else:
            await FFmpegService.merge_videos_reencode(
                body_sequence, body_path, resolution=resolution
            )
        print(f"[subtitle/render] body merged in {_t.time()-t_body:.1f}s")
    except Exception as e:
        import traceback
        print(f"[subtitle/render] BODY MERGE FAILED: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Body merge failed: {type(e).__name__}: {e}")

    # 과거 호환: videos/merged.mp4 는 본편 컷 병합본으로 유지한다.
    # output/merged.mp4 는 아래에서 오프닝/인터미션/엔딩까지 들어간 무BGM 기준본으로 저장한다.
    try:
        video_dir.mkdir(parents=True, exist_ok=True)
        from shutil import copyfile
        copyfile(body_path, str(video_dir / "merged.mp4"))
    except Exception as e:
        print(f"[subtitle/render] WARN: could not copy body to videos/merged.mp4: {e}")

    # ── Step 5: 본편 자막 처리 ──
    # 컷 단계에서 이미 자막/음성이 들어간 프로젝트는 본편을 더 건드리지 않는다.
    body_sub_path = body_path
    if not cut_level_subs and burn_main_subtitles:
        body_sub_path = str(tmp_dir / "body_sub.mp4")
        try:
            t_burn = _t.time()
            await FFmpegService.burn_subtitles(body_path, str(subtitle_file), body_sub_path)
            print(f"[subtitle/render] burn_subtitles done in {_t.time()-t_burn:.1f}s")
        except Exception as e:
            import traceback
            print(f"[subtitle/render] BURN FAILED: {e}\n{traceback.format_exc()}")
            raise HTTPException(
                500, f"Subtitle burn failed: {type(e).__name__}: {e}"
            )
    elif not burn_main_subtitles:
        print(f"[subtitle/render] subtitle_delivery={subtitle_delivery} — main burn skipped")
    else:
        print("[subtitle/render] cut_level_subtitles=True — 본편 추가 처리 없음")

    # ── Step 6: 오프닝/엔딩 resolve ──
    opening_raw = _resolve_interlude_path(project_id, project, "opening")
    ending_raw = _resolve_interlude_path(project_id, project, "ending")
    if opening_raw:
        print(f"[subtitle/render] opening: {opening_raw}")
    else:
        # v1.1.55: 사용자 요구 "렌더할 때 오프닝 꼭 집어 넣고" — 오프닝이
        # 등록돼 있지만 디스크에 파일이 없거나 아예 미등록이면 즉시 경고.
        # 클론 시 _copy_template_assets 가 interlude/ 디렉토리를 통째로
        # 복사하므로 프리셋에 오프닝이 있으면 여기까지 누락될 일이 없다.
        inter_cfg = (project.config or {}).get("interlude") or {}
        op_entry = inter_cfg.get("opening") or {}
        if op_entry.get("video_path"):
            print(
                f"[subtitle/render] ⚠ 오프닝 등록은 돼 있는데 파일을 찾지 못했습니다 "
                f"(config={op_entry.get('video_path')!r}). 최종 영상에서 오프닝이 빠집니다."
            )
        else:
            print(
                "[subtitle/render] ⚠ 오프닝 미설정 — interlude.opening 을 등록하면 "
                "자동으로 본편 앞에 합쳐집니다."
            )
    if ending_raw:
        print(f"[subtitle/render] ending: {ending_raw}")

    # ── Step 7: output/merged.mp4 생성 ──
    # 컷 mp4 에 자막/음성이 이미 들어간다. 여기서는 오프닝/인터미션/엔딩을
    # 순서대로 붙인 무BGM 기준본만 만든다. BGM 은 다음 단계에서만 입힌다.
    merged_output_path = output_dir / "merged.mp4"
    final_sequence: list[str] = []
    if opening_raw:
        opening_timeline = str(tmp_dir / "opening_timeline.mp4")
        await _prepare_interlude_timeline_clip(opening_raw, opening_timeline, resolution)
        final_sequence.append(opening_timeline)
    final_sequence.append(body_sub_path)
    if ending_raw:
        ending_timeline = str(tmp_dir / "ending_timeline.mp4")
        await _prepare_interlude_timeline_clip(ending_raw, ending_timeline, resolution)
        final_sequence.append(ending_timeline)

    try:
        t_final = _t.time()
        if len(final_sequence) == 1:
            from shutil import copyfile
            copyfile(final_sequence[0], str(merged_output_path))
        elif preserve_cut_audio:
            await FFmpegService.merge_videos(final_sequence, str(merged_output_path))
        else:
            await FFmpegService.merge_videos_reencode(
                final_sequence, str(merged_output_path), resolution=resolution
            )
        print(f"[subtitle/render] merged baseline saved in {_t.time()-t_final:.1f}s → {merged_output_path}")
    except Exception as e:
        import traceback
        print(f"[subtitle/render] MERGED CONCAT FAILED: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Merged concat failed: {type(e).__name__}: {e}")

    final_nomusic_path = str(merged_output_path)

    bgm_cfg = _read_bgm_config(project.config or {})
    bgm_enabled = bool(bgm_cfg["enabled"])
    bgm_path = None
    try:
        bgm_path = await _ensure_bgm_for_render(project_id, project, db)
    except Exception as e:
        import traceback
        print(
            f"[subtitle/render] BGM GENERATION FAILED (non-fatal, rendering without BGM): "
            f"{e}\n{traceback.format_exc()}"
        )
        if bgm_enabled:
            raise HTTPException(500, f"BGM generation failed: {type(e).__name__}: {e}")
    if bgm_path:
        try:
            t_bgm = _t.time()
            bgm_cfg = _read_bgm_config(project.config or {})
            volume = float(bgm_cfg["volume"])
            await _mix_bgm_into_video(
                final_nomusic_path,
                bgm_path,
                str(output_path),
                volume,
                ducking_strength=str(bgm_cfg.get("ducking_strength") or "normal"),
                start_offset_sec=float(bgm_cfg.get("start_offset_sec") or 0.0),
                fade_in_sec=float(bgm_cfg.get("fade_in_sec") or 0.0),
                fade_out_sec=float(bgm_cfg.get("fade_out_sec") or 0.0),
            )
            print(
                f"[subtitle/render] BGM mixed volume={volume:.3f} "
                f"narration_gain={NARRATION_VOLUME_GAIN:.2f} "
                f"ducking={bgm_cfg.get('ducking_strength')} "
                f"offset={bgm_cfg.get('start_offset_sec')} "
                f"fade=({bgm_cfg.get('fade_in_sec')},{bgm_cfg.get('fade_out_sec')}) "
                f"file={bgm_path} in {_t.time()-t_bgm:.1f}s"
            )
        except Exception as e:
            import traceback
            print(
                f"[subtitle/render] BGM MIX FAILED (non-fatal, falling back to no BGM): "
                f"{e}\n{traceback.format_exc()}"
            )
            if bgm_enabled:
                raise HTTPException(500, f"BGM mix failed: {type(e).__name__}: {e}")
            from shutil import copyfile
            copyfile(final_nomusic_path, str(output_path))
    else:
        try:
            t_gain = _t.time()
            await _apply_narration_gain_to_video(final_nomusic_path, str(output_path))
            print(
                f"[subtitle/render] narration gain={NARRATION_VOLUME_GAIN:.2f} "
                f"applied in {_t.time()-t_gain:.1f}s"
            )
        except Exception as e:
            import traceback
            print(
                f"[subtitle/render] NARRATION GAIN FAILED (non-fatal, using original audio): "
                f"{e}\n{traceback.format_exc()}"
            )
            from shutil import copyfile
            copyfile(final_nomusic_path, str(output_path))

    if not output_path.exists():
        raise HTTPException(500, "Final render reported success but output file is missing")

    file_size = output_path.stat().st_size
    shorts_results = []
    try:
        shorts_enabled = bool((project.config or {}).get("shorts_enabled", True))
        if shorts_enabled:
            script_for_shorts = load_shorts_script(DATA_DIR / project_id)
            shorts_segments = select_shorts_segments(script_for_shorts, count=1)
            cfg = project.config or {}
            if isinstance(script_for_shorts, dict) and not script_for_shorts.get("language"):
                script_for_shorts["language"] = (
                    cfg.get("language")
                    or cfg.get("script_language")
                    or cfg.get("subtitle_language")
                    or cfg.get("target_language")
                )
            shorts_channel_name = (
                cfg.get("shorts_channel_name")
                or cfg.get("channel_display_name")
                or cfg.get("youtube_channel_name")
                or cfg.get("brand_name")
            )
            raw_channel = cfg.get("channel") or cfg.get("youtube_channel")
            try:
                shorts_channel_id = int(raw_channel or 0)
            except (TypeError, ValueError):
                shorts_channel_id = 0
            cached_channel_avatars = {
                1: "https://yt3.ggpht.com/lZRG--gQU8wZ5Gzeethzm6NBlG6FD9Jx4QxR4djz4kOgIj-LS9Dm1fO0ruuMEhrZE1AjEFeXQ3Q=s88-c-k-c0x00ffffff-no-rj",
                2: "https://yt3.ggpht.com/NY92X-Yu-tgLBOvUtCPJBhqmuM47ZILmU33lPBSKiPEeC06imNtxH6Kdd1EVldLmBtPG590miA=s88-c-k-c0x00ffffff-no-rj",
                3: "https://yt3.ggpht.com/lRHg7iB8VCuQYJPyiu6P4mKHK6jslowo8ZURRESjmTbiVYqvXCOn0draMc_XV_dGMS6tbjj8DJs=s88-c-k-c0x00ffffff-no-rj",
                4: "https://yt3.ggpht.com/GmMBiNYytpUfw14ZP9SeX5kllM6j-uJcPhW0re1qcAz6n_FHUP1nTXKp_T2BmeFrxup9HYTm6Q=s88-c-k-c0x00ffffff-no-rj",
            }
            cached_channel_names = {
                1: "10\ubd84\uc5ed\uacf5",
                2: "Jerry's Archaeo",
                3: "\u95c7\u89e3\u304d\u65e5\u672c\u53f2",
                4: "10 \u092e\u093f\u0928\u091f \u092a\u0932\u091f\u0935\u093e\u0930",
            }
            if not shorts_channel_name:
                shorts_channel_name = cached_channel_names.get(shorts_channel_id)
            shorts_channel_avatar_url = (
                cfg.get("shorts_channel_avatar_url")
                or cfg.get("channel_avatar_url")
                or cached_channel_avatars.get(shorts_channel_id)
            )
            if not shorts_channel_name:
                try:
                    from app.services.youtube_service import YouTubeUploader

                    ch = shorts_channel_id
                    if ch >= 1:
                        channel_info = YouTubeUploader(channel_id=ch).get_channel_info()
                        shorts_channel_name = channel_info.get("title") or None
                        shorts_channel_avatar_url = (
                            channel_info.get("thumbnail")
                            or shorts_channel_avatar_url
                        )
                except Exception as e:
                    print(f"[subtitle/render] shorts channel name lookup skipped: {e}")
            elif not shorts_channel_avatar_url:
                try:
                    from app.services.youtube_service import YouTubeUploader

                    ch = shorts_channel_id
                    if ch >= 1:
                        shorts_channel_avatar_url = (
                            YouTubeUploader(channel_id=ch).get_channel_info().get("thumbnail")
                            or None
                        )
                except Exception as e:
                    print(f"[subtitle/render] shorts channel avatar lookup skipped: {e}")
            shorts_source_path = Path(shorts_body_path) if shorts_body_path else video_dir / "merged.mp4"
            if not shorts_source_path.exists():
                shorts_source_path = video_dir / "merged.mp4"
            shorts_results = await render_shorts_from_final(
                shorts_source_path,
                output_dir,
                shorts_segments,
                script=script_for_shorts,
                channel_name=shorts_channel_name,
                channel_avatar_url=shorts_channel_avatar_url,
                source_title=script_for_shorts.get("title") or project.title,
                bgm_path=bgm_path,
                bgm_volume=float((_read_bgm_config(project.config or {})).get("volume") or DEFAULT_RENDER_BGM_VOLUME),
                bgm_ducking_strength=str((_read_bgm_config(project.config or {})).get("ducking_strength") or "normal"),
            )
            shorts_meta_path = output_dir / "shorts" / "shorts.json"
            shorts_meta_path.parent.mkdir(parents=True, exist_ok=True)
            with open(shorts_meta_path, "w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "enabled": True,
                        "segments": shorts_segments,
                        "results": shorts_results,
                    },
                    fh,
                    ensure_ascii=False,
                    indent=2,
                )
            print(f"[subtitle/render] shorts rendered: {len(shorts_results)}")
    except Exception as e:
        import traceback
        shorts_results = []
        print(f"[subtitle/render] SHORTS FAILED (non-fatal): {e}\n{traceback.format_exc()}")

    # tmp 파일 청소
    try:
        for f in tmp_dir.iterdir():
            try:
                f.unlink()
            except Exception:
                pass
    except Exception:
        pass

    # Step 6(렌더링) 완료 플래그.
    try:
        fresh = db.query(Project).filter(Project.id == project_id).first()
        if fresh:
            ss = dict(fresh.step_states or {})
            ss["6"] = "completed"
            fresh.step_states = ss
            if fresh.current_step is not None and fresh.current_step < 6:
                fresh.current_step = 6
            db.commit()
    except Exception as e:
        print(f"[subtitle/render] WARN: step_states persist failed: {e}")

    elapsed = _t.time() - t0
    print(
        f"[subtitle/render] DONE project={project_id} size={file_size}B "
        f"elapsed={elapsed:.1f}s → {output_path} "
        f"(opening={'Y' if opening_raw else 'N'}, ending={'Y' if ending_raw else 'N'})"
    )

    return {
        "status": "rendered",
        "path": str(output_path),
        "subtitles": str(subtitle_file),
        "size": file_size,
        "elapsed_seconds": round(elapsed, 1),
        "opening_used": bool(opening_raw),
        "intermission_used": bool(intermission_count),
        "intermission_count": intermission_count,
        "ending_used": bool(ending_raw),
        "cuts": len(normalized_cuts),
        "shorts": shorts_results,
        "download_url": f"/assets/{project_id}/output/final_with_subtitles.mp4",
    }


@router.post("/{project_id}/render-async")
async def render_video_async(project_id: str, db: Session = Depends(get_db)):
    """v1.1.49: 렌더링을 백그라운드로 실행 — 즉시 반환.

    탭 이동/페이지 닫기에도 작업이 계속 진행된다.
    기존 render_video_with_subtitles 함수를 내부적으로 재사용한다.
    """
    import asyncio
    from app.services.task_manager import (
        start_task, complete_task, fail_task, register_async_task, is_running,
    )

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "render"):
        return {"status": "already_running", "step": "render"}

    # 렌더링은 단일 작업. 예상 시간: 설정의 예상치 또는 기본 120초
    est_seconds = float((project.config or {}).get("estimate", {}).get("time_breakdown", {}).get("post_process", 120))
    state = start_task(project_id, "render", 1, estimated_total_seconds=est_seconds)

    # step_states 를 running 으로 갱신
    step_states = dict(project.step_states or {})
    step_states["6"] = "running"
    project.step_states = step_states
    db.commit()

    async def _run():
        from app.models.database import SessionLocal
        local_db = SessionLocal()
        try:
            await render_video_with_subtitles(project_id, db=local_db)
            # 성공 시 step_states 갱신
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            if proj:
                ss = dict(proj.step_states or {})
                ss["6"] = "completed"
                proj.step_states = ss
                local_db.commit()
            complete_task(project_id, "render")
        except Exception as e:
            fail_task(project_id, "render", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["6"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except Exception:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "render", task)
    return {"status": "started", "step": "render", "task": state.to_dict()}
