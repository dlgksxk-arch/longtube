"""Subtitle router"""
import json
import os
import re
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import CUT_VIDEO_DURATION, DATA_DIR, FIRST_CUT_FADE_IN_SECONDS, resolve_project_dir
from app.services.subtitle_service import generate_ass
from app.services.shorts_service import (
    load_script as load_shorts_script,
    render_shorts_from_final,
    select_shorts_segments,
)
from app.services.video.ffmpeg_service import FFmpegService
from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess

router = APIRouter()


def _load_script(project_id: str) -> dict:
    """Load script.json from disk"""
    script_path = DATA_DIR / project_id / "script.json"
    if not script_path.exists():
        return {"cuts": []}
    with open(script_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_and_write_ass(project_id: str, project: Project, db: Session) -> tuple[str, int]:
    """Build cut data, render ASS, and persist subtitles.ass to disk.

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
        cuts_data.append({
            "cut_number": cut.cut_number,
            "narration": cut.narration or cut_script.get("narration", ""),
            "actual_duration": cut.audio_duration,
            "duration_estimate": cut_script.get("duration_estimate", 5.0)
        })

    style_config = project.config.get("subtitle_style", {
        "font": "Pretendard Bold",
        "size": 48,
        "color": "#FFFFFF",
        "outline_color": "#000000",
        "position": "bottom"
    })
    aspect_ratio = project.config.get("aspect_ratio", "16:9")

    ass_content = generate_ass(cuts_data, style_config, aspect_ratio)

    subtitle_dir = DATA_DIR / project_id / "subtitles"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = subtitle_dir / "subtitles.ass"

    with open(subtitle_path, "w", encoding="utf-8") as f:
        f.write(ass_content)

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
        cfg["bgm_volume"] = float(cfg.get("bgm_volume", 0.24) or 0.24)
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
        topic=project.topic or "",
        title=project.title or "",
        style_prompt=str(cfg.get("bgm_style_prompt") or ""),
        language=str(cfg.get("language") or "ko"),
    )
    target_duration = int(cfg.get("target_duration") or 600)
    length_ms = min(max(target_duration * 1000, 30_000), 180_000)
    bgm_abs = resolve_project_dir(project_id, cfg, create=True) / "bgm" / "generated_bgm.mp3"

    try:
        result = await generate_bgm(prompt=prompt, output_path=bgm_abs, length_ms=length_ms)
        cfg["bgm_enabled"] = True
        cfg["bgm_path"] = "bgm/generated_bgm.mp3"
        cfg["bgm_prompt_used"] = prompt
        cfg["bgm_volume"] = float(cfg.get("bgm_volume", 0.24) or 0.24)
        project.config = cfg
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(project, "config")
        db.commit()
        return {
            "status": "generated",
            "path": cfg["bgm_path"],
            "size": result["size"],
            "length_ms": result["length_ms"],
            "prompt": prompt,
            "enabled": True,
            "volume": cfg["bgm_volume"],
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
            path = resolve_project_dir(project_id, cfg, create=False) / rel_path
            if path.exists() and path.is_file():
                path.unlink()
                deleted = True
        except Exception:
            deleted = False
    cfg["bgm_enabled"] = False
    cfg["bgm_path"] = ""
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


def _resolution_for_aspect(aspect_ratio: str, target_resolution: str = "720p") -> str:
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
    """project.config['interlude'][kind].video_path → 절대 경로 (파일 존재 시)."""
    inter = (project.config or {}).get("interlude") or {}
    entry = inter.get(kind) or {}
    vp = entry.get("video_path")
    if not vp:
        return None
    from pathlib import Path as _P
    p = _P(vp)
    if not p.is_absolute():
        p = DATA_DIR / project_id / vp
    return str(p) if p.exists() else None


def _resolve_bgm_path(project_id: str, project: Project) -> str | None:
    cfg = project.config or {}
    if not bool(cfg.get("bgm_enabled", False)):
        return None
    raw = str(cfg.get("bgm_path") or "").strip()
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


async def _ensure_bgm_for_render(project_id: str, project: Project, db: Session) -> str | None:
    existing = _resolve_bgm_path(project_id, project)
    if existing:
        return existing

    cfg = dict(project.config or {})
    if not bool(cfg.get("bgm_enabled", False)):
        return None

    from app.services.bgm_service import build_bgm_prompt, generate_bgm

    prompt = build_bgm_prompt(
        topic=project.topic or "",
        title=project.title or "",
        style_prompt=str(cfg.get("bgm_style_prompt") or ""),
        language=str(cfg.get("language") or "ko"),
    )
    target_duration = int(cfg.get("target_duration") or 600)
    length_ms = min(max(target_duration * 1000, 30_000), 180_000)
    bgm_rel = "bgm/generated_bgm.mp3"
    bgm_abs = resolve_project_dir(project_id, cfg, create=True) / bgm_rel
    print(f"[subtitle/render] generating BGM via ElevenLabs Music: {prompt!r}")
    result = await generate_bgm(
        prompt=prompt,
        output_path=bgm_abs,
        length_ms=length_ms,
    )
    cfg["bgm_path"] = bgm_rel
    cfg["bgm_prompt_used"] = prompt
    project.config = cfg
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(project, "config")
    db.commit()
    print(
        f"[subtitle/render] BGM generated: {bgm_rel} "
        f"size={result.get('size')} length_ms={result.get('length_ms')}"
    )
    return str(bgm_abs)


async def _mix_bgm_into_video(input_path: str, bgm_path: str, output_path: str, volume: float) -> str:
    ffmpeg_bin = find_ffmpeg()
    vol = max(0.0, min(1.0, float(volume)))
    has_audio = await _video_has_audio(ffmpeg_bin, input_path)
    if has_audio:
        filter_complex = (
            f"[1:a]volume={vol:.4f},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[bgm];"
            f"[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[main];"
            f"[main][bgm]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[aout]"
        )
    else:
        filter_complex = (
            f"[1:a]volume={vol:.4f},aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]"
        )
    cmd = [
        ffmpeg_bin, "-y",
        "-i", input_path,
        "-stream_loop", "-1", "-i", bgm_path,
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
    target_resolution = (project.config or {}).get("render_resolution", "720p")
    resolution = _resolution_for_aspect(aspect_ratio, target_resolution)

    # v1.1.55: 컷 단계에서 이미 자막을 번인했으면 본편 단계의 ASS 생성/번인은
    # 건너뛴다. 머지 후 자막 입히면 ensure_min_duration 등으로 컷 길이가
    # 변형돼 싱크가 깨지는 사고 차단. 기본 True — 옛 프로젝트는 config 에서
    # `cut_level_subtitles=False` 로 토글 가능.
    cut_level_subs = bool((project.config or {}).get("cut_level_subtitles", True))

    if not cut_level_subs:
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

    # ── Step 3: 각 컷 최소 5초 보정 ──
    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number)
        .all()
    )
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
    body_path = str(tmp_dir / "body.mp4")
    try:
        t_body = _t.time()
        await FFmpegService.merge_videos_reencode(
            normalized_cuts, body_path, resolution=resolution
        )
        print(f"[subtitle/render] body merged in {_t.time()-t_body:.1f}s")
    except Exception as e:
        import traceback
        print(f"[subtitle/render] BODY MERGE FAILED: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Body merge failed: {type(e).__name__}: {e}")

    # 과거 호환: videos/merged.mp4 도 덮어써 둬서 다른 곳에서 참조하는 코드가 있어도 OK.
    try:
        video_dir.mkdir(parents=True, exist_ok=True)
        from shutil import copyfile
        copyfile(body_path, str(video_dir / "merged.mp4"))
    except Exception as e:
        print(f"[subtitle/render] WARN: could not copy body to videos/merged.mp4: {e}")

    # ── Step 5: 자막 번인 (본편만) ──
    # v1.1.55: cut_level_subtitles=True 면 컷 단계에서 이미 번인 — 건너뜀.
    body_sub_path = str(tmp_dir / "body_sub.mp4")
    if cut_level_subs:
        from shutil import copyfile as _cp
        _cp(body_path, body_sub_path)
        print("[subtitle/render] cut_level_subtitles=True — 본편 burn 건너뜀")
    else:
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

    # ── Step 7: 최종 시퀀스 합성 (pre_final) ──
    # v1.1.55: 오프닝↔본편 사이 0.5초 크로스페이드, 엔딩은 단순 concat
    # v1.1.71: Step 7 은 tmp 파일에 쓰고, Step 8 에서 전단 pre-roll 을 얹어 최종 출력을 생성.
    CROSSFADE_SEC = 0.5
    pre_final_path = str(tmp_dir / "pre_final.mp4")
    try:
        t_final = _t.time()
        if not opening_raw and not ending_raw:
            # 오프닝/엔딩 없음 → body_sub 를 그대로 pre_final 로.
            from shutil import copyfile
            copyfile(body_sub_path, pre_final_path)
        elif opening_raw and not ending_raw:
            # 오프닝 + 본편 (크로스페이드)
            await FFmpegService.merge_with_crossfade(
                opening_raw, body_sub_path, pre_final_path,
                fade_seconds=CROSSFADE_SEC, resolution=resolution,
            )
        elif opening_raw and ending_raw:
            # 오프닝 + 본편 (크로스페이드) → + 엔딩 (단순 concat)
            crossfaded_path = str(tmp_dir / "opening_body_crossfade.mp4")
            await FFmpegService.merge_with_crossfade(
                opening_raw, body_sub_path, crossfaded_path,
                fade_seconds=CROSSFADE_SEC, resolution=resolution,
            )
            await FFmpegService.merge_videos_reencode(
                [crossfaded_path, ending_raw], pre_final_path, resolution=resolution,
            )
        else:
            # 엔딩만 있는 경우 (드묾) → 단순 concat
            await FFmpegService.merge_videos_reencode(
                [body_sub_path, ending_raw], pre_final_path, resolution=resolution,
            )
        print(f"[subtitle/render] final concat done in {_t.time()-t_final:.1f}s")
    except Exception as e:
        import traceback
        print(f"[subtitle/render] FINAL CONCAT FAILED: {e}\n{traceback.format_exc()}")
        raise HTTPException(500, f"Final concat failed: {type(e).__name__}: {e}")

    # ── Step 8: 전단 0.5초 무음 + 150ms 페이드 인 ──
    # v1.1.71: 시작이 급작스럽다는 피드백 대응. 재생 직후 0.5초 무음/정지 프레임
    # 을 삽입하고, 첫 150ms 동안 검정→첫 프레임 페이드 인. 자막은 본편에 이미
    # 번인돼 있어 타임라인이 같이 밀리므로 별도 조정 불필요.
    # config 에서 `pre_roll_sec=0` 을 주면 스킵(옛 프로젝트 하위호환).
    pre_roll_sec = float((project.config or {}).get("pre_roll_sec", 0.0) or 0)
    pre_roll_fade_sec = float((project.config or {}).get("pre_roll_fade_sec", 0.15) or 0)
    final_nomusic_path = str(tmp_dir / "final_nomusic.mp4")
    if pre_roll_sec > 0:
        try:
            t_pre = _t.time()
            await FFmpegService.prepend_silent_fade_in(
                pre_final_path, str(output_path),
                silent_seconds=pre_roll_sec,
                fade_seconds=min(pre_roll_fade_sec, pre_roll_sec),
                resolution=resolution,
            )
            print(
                f"[subtitle/render] pre-roll {pre_roll_sec:.2f}s "
                f"(fade {pre_roll_fade_sec:.3f}s) applied in {_t.time()-t_pre:.1f}s"
            )
        except Exception as e:
            import traceback
            print(f"[subtitle/render] PRE-ROLL FAILED (non-fatal, falling back to no pre-roll): "
                  f"{e}\n{traceback.format_exc()}")
            from shutil import copyfile
            copyfile(pre_final_path, final_nomusic_path)
        else:
            from shutil import copyfile
            copyfile(str(output_path), final_nomusic_path)
    else:
        from shutil import copyfile
        copyfile(pre_final_path, final_nomusic_path)

    bgm_enabled = bool((project.config or {}).get("bgm_enabled", False))
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
            volume = float((project.config or {}).get("bgm_volume", 0.24) or 0.24)
            await _mix_bgm_into_video(final_nomusic_path, bgm_path, str(output_path), volume)
            print(
                f"[subtitle/render] BGM mixed volume={volume:.3f} "
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
            shorts_segments = select_shorts_segments(script_for_shorts, count=2)
            shorts_results = await render_shorts_from_final(
                output_path,
                output_dir,
                shorts_segments,
                script=script_for_shorts,
                channel_name=(project.config or {}).get("shorts_channel_name") or project.title,
                source_title=script_for_shorts.get("title") or project.title,
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
