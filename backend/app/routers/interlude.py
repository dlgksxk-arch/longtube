"""Interlude (오프닝/간지/엔딩 영상) router — v1 프로젝트 범위.

v1.1.29: 생성(generate) 방식 완전 폐기. 사용자가 설정 페이지에서 직접
업로드한 영상 파일을 오프닝/인터미션/엔딩으로 쓴다. 업로드된 파일은
``data/{project_id}/interlude/{kind}{ext}`` 로 저장되고, 경로는
``project.config["interlude"][kind] = {"video_path": ..., "filename": ...}``
에 기록된다.

본편 영상 병합(`build_interlude_sequence`) 쪽 로직은 이전과 동일 —
config 의 video_path 를 읽어서 최종 머지에 끼워 넣는다. 업로드가 돼 있으면
자동으로 final_with_interludes.mp4 가 생성된다.

v2.4.0: 업로드/삭제/ffprobe 공통 로직을 ``services.interlude_service`` 로
추출했다. 본 라우터는 DB-연동(프로젝트.config 갱신) + compose 쪽만 전담하고,
파일 IO 는 서비스 모듈을 호출한다. v2 의 프리셋 범위 라우터도 동일 서비스
모듈을 재사용한다 — 프로세스 중복 없이 한 곳에서 유지보수.
"""
from __future__ import annotations

import traceback
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import DATA_DIR, CUT_VIDEO_DURATION
from app.models.cut import Cut
from app.models.database import get_db
from app.models.project import Project
from app.services.video.ffmpeg_service import FFmpegService
from app.services.interlude_service import (
    VALID_KINDS,
    DEFAULT_INTERMISSION_EVERY,
    ffprobe_duration as _ffprobe_duration,
    save_uploaded_video,
    delete_uploaded_video,
)

router = APIRouter()


# ---------- 헬퍼 ----------


def _interlude_dir(project_id: str) -> Path:
    d = DATA_DIR / project_id / "interlude"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _output_dir(project_id: str) -> Path:
    d = DATA_DIR / project_id / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_rel(project_id: str, abs_path: str) -> str:
    project_dir = str(DATA_DIR / project_id).replace("\\", "/")
    p = str(abs_path).replace("\\", "/")
    if p.startswith(project_dir):
        return p[len(project_dir):].lstrip("/")
    return abs_path


def _resolve_under_project(project_id: str, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return DATA_DIR / project_id / rel_or_abs


def _get_interlude_config(project: Project) -> dict:
    """Always returns a dict (copy) so caller can mutate safely."""
    cfg = dict(project.config or {})
    inter = dict(cfg.get("interlude") or {})
    if "intermission_every_sec" not in inter:
        inter["intermission_every_sec"] = DEFAULT_INTERMISSION_EVERY
    return inter


def _save_interlude_config(project: Project, inter: dict, db: Session) -> None:
    cfg = dict(project.config or {})
    cfg["interlude"] = inter
    project.config = cfg
    # v1.1.29: SQLAlchemy JSON 컬럼 mutation 감지 실패 대응 — 명시적 dirty 마킹.
    flag_modified(project, "config")
    db.commit()


# ---------- Pydantic 스키마 ----------


class InterludeConfigUpdate(BaseModel):
    intermission_every_sec: Optional[int] = Field(
        default=None, ge=30, le=1800,
        description="본편 중간에 인터미션을 끼워넣을 간격(초). 기본 180(3분).",
    )


class InterludeComposeRequest(BaseModel):
    intermission_every_sec: Optional[int] = Field(
        default=None, ge=30, le=1800,
        description="override 인터미션 간격(초). 없으면 config 값 사용.",
    )


# ---------- 엔드포인트: 조회 ----------


@router.get("/{project_id}")
def get_interludes(project_id: str, db: Session = Depends(get_db)):
    """현재 저장된 오프닝/인터미션/엔딩 영상 상태 반환."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    inter = _get_interlude_config(project)
    # disk 존재 여부 검증 — DB 에 기록은 남아 있는데 파일이 사라진 경우 null 처리.
    for kind in VALID_KINDS:
        entry = inter.get(kind)
        if not entry:
            continue
        vp = entry.get("video_path")
        if vp and not _resolve_under_project(project_id, vp).exists():
            entry["video_path"] = None
        inter[kind] = entry

    return {
        "project_id": project_id,
        "opening": inter.get("opening"),
        "intermission": inter.get("intermission"),
        "ending": inter.get("ending"),
        "intermission_every_sec": inter.get(
            "intermission_every_sec", DEFAULT_INTERMISSION_EVERY
        ),
    }


@router.put("/{project_id}/config")
def update_interlude_config(
    project_id: str,
    body: InterludeConfigUpdate,
    db: Session = Depends(get_db),
):
    """intermission_every_sec 등 설정값 갱신."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    inter = _get_interlude_config(project)
    if body.intermission_every_sec is not None:
        inter["intermission_every_sec"] = body.intermission_every_sec
    _save_interlude_config(project, inter, db)
    return {
        "status": "updated",
        "intermission_every_sec": inter.get("intermission_every_sec"),
    }


# ---------- 엔드포인트: 업로드 / 삭제 ----------


@router.post("/{project_id}/upload/{kind}")
async def upload_interlude_video(
    project_id: str,
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """오프닝 / 인터미션 / 엔딩 영상 업로드.

    파일 IO 는 ``services.interlude_service.save_uploaded_video`` 가 담당하고,
    본 핸들러는 프로젝트 존재 검증 + 저장된 메타를 ``project.config`` 에
    기록하는 일만 한다. 용량/확장자 검증은 서비스 쪽에서 HTTPException 으로
    올라오므로 중복 검사 없음.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    inter_dir = _interlude_dir(project_id)
    meta = await save_uploaded_video(inter_dir, kind, file)

    inter = _get_interlude_config(project)
    inter[kind] = {
        "video_path": _to_rel(project_id, meta["video_path"]),
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
        "duration": meta["duration"],
        "source": meta["source"],
    }
    _save_interlude_config(project, inter, db)

    print(
        f"[interlude] uploaded project={project_id} kind={kind} "
        f"file={meta['filename']} size={meta['size_bytes']} "
        f"duration={meta['duration']:.2f}s"
    )

    return {
        "status": "uploaded",
        "project_id": project_id,
        "kind": kind,
        **inter[kind],
    }


@router.delete("/{project_id}/{kind}")
def delete_interlude(project_id: str, kind: str, db: Session = Depends(get_db)):
    """저장된 오프닝/인터미션/엔딩 영상 삭제."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # 파일 삭제 — video_path 에 적힌 것 + 같은 kind 잔존 파일 전부.
    inter = _get_interlude_config(project)
    entry = inter.get(kind) or {}
    vp = entry.get("video_path")
    if vp:
        abs_p = _resolve_under_project(project_id, vp)
        if abs_p.exists():
            try:
                abs_p.unlink()
            except OSError:
                pass
    delete_uploaded_video(_interlude_dir(project_id), kind)

    inter.pop(kind, None)
    _save_interlude_config(project, inter, db)
    return {"status": "deleted", "kind": kind}


# ---------- 시퀀스 빌더 (다른 라우터에서도 재사용) ----------


async def build_interlude_sequence(
    project: Project,
    project_id: str,
    db: Session,
    *,
    override_every_sec: Optional[int] = None,
) -> dict:
    """본편 컷 + 업로드된 간지 영상 시퀀스를 조립해 ``final_with_interludes.mp4`` 를 생성.

    video 라우터에서 병합 직후 이 함수를 호출해 자동으로 오프닝/인터미션/
    엔딩이 끼워진 최종본을 만든다. 간지 영상이 하나도 업로드돼 있지 않으면
    아무 것도 하지 않고 ``{"status": "skipped", ...}`` 를 반환한다.

    Returns 예시::
        {
          "status": "composed",
          "output_path": "output/final_with_interludes.mp4",
          "total_clips": 12,
          "cuts_used": 9,
          "opening_used": True,
          "intermission_used": True,
          "ending_used": True,
          "intermission_every_sec": 180,
        }
    """
    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number.asc())
        .all()
    )
    if not cuts or not any(c.video_path for c in cuts):
        return {"status": "skipped", "reason": "no cut videos"}

    cut_entries: list[tuple[str, float]] = []
    for c in cuts:
        if not c.video_path:
            continue
        abs_p = _resolve_under_project(project_id, c.video_path)
        if not abs_p.exists():
            continue
        # v1.1.45: 모든 컷 영상은 CUT_VIDEO_DURATION 초 고정이므로 여기도 상수 사용.
        # (legacy 프로젝트나 수동 업로드 컷 대비 ffprobe 폴백은 그대로 유지)
        dur = float(CUT_VIDEO_DURATION)
        if dur <= 0.0:
            dur = await _ffprobe_duration(str(abs_p))
        if dur <= 0.0:
            dur = 5.0
        cut_entries.append((str(abs_p), dur))

    if not cut_entries:
        return {"status": "skipped", "reason": "no cut video files on disk"}

    inter = _get_interlude_config(project)
    every = override_every_sec or int(
        inter.get("intermission_every_sec") or DEFAULT_INTERMISSION_EVERY
    )

    def _inter_abs(kind: str) -> Optional[str]:
        entry = inter.get(kind) or {}
        vp = entry.get("video_path")
        if not vp:
            return None
        abs_p = _resolve_under_project(project_id, vp)
        return str(abs_p) if abs_p.exists() else None

    opening = _inter_abs("opening")
    intermission = _inter_abs("intermission")
    ending = _inter_abs("ending")

    if not (opening or intermission or ending):
        return {"status": "skipped", "reason": "no interlude clips uploaded"}

    # 컷 클립과 업로드 영상은 코덱/해상도가 다를 수 있다.
    # v2.1.1: 오프닝 뒤 / 엔딩 앞에 0.5초 크로스페이드 적용.
    # 1) 본편 시퀀스 구성
    body_sequence: list[str] = []

    accumulated = 0.0
    for idx, (path, dur) in enumerate(cut_entries):
        body_sequence.append(path)
        accumulated += dur
        is_last = idx == len(cut_entries) - 1
        if intermission and not is_last and accumulated >= every:
            body_sequence.append(intermission)
            accumulated = 0.0

    if not body_sequence:
        return {"status": "skipped", "reason": "no body clips"}

    # 2) 본편을 먼저 stream copy 병합
    output_dir = _output_dir(project_id)
    body_path = str(output_dir / "body_merged.mp4")
    ff = FFmpegService()
    await ff.merge_videos(body_sequence, body_path)

    # 3) 오프닝 + 본편을 크로스페이드로 이어붙이기
    FADE_SEC = 0.5
    aspect_ratio = (project.config or {}).get("aspect_ratio", "16:9")
    if aspect_ratio == "9:16":
        resolution = "1080x1920"
    elif aspect_ratio == "1:1":
        resolution = "1080x1080"
    else:
        resolution = "1920x1080"

    current = body_path
    if opening:
        opening_body_path = str(output_dir / "opening_body.mp4")
        await ff.merge_with_crossfade(
            opening, current, opening_body_path,
            fade_seconds=FADE_SEC, resolution=resolution,
        )
        current = opening_body_path

    # 4) 현재까지 결과 + 엔딩을 크로스페이드로 이어붙이기
    if ending:
        with_ending_path = str(output_dir / "with_ending.mp4")
        await ff.merge_with_crossfade(
            current, ending, with_ending_path,
            fade_seconds=FADE_SEC, resolution=resolution,
        )
        current = with_ending_path

    # 5) 최종 파일 이름으로 이동
    output_path = output_dir / "final_with_interludes.mp4"
    import shutil as _shutil
    _shutil.move(current, str(output_path))

    # 임시 파일 정리
    for tmp_name in ("body_merged.mp4", "opening_body.mp4", "with_ending.mp4"):
        tmp = output_dir / tmp_name
        if tmp.exists() and str(tmp) != str(output_path):
            try:
                tmp.unlink()
            except OSError:
                pass

    return {
        "status": "composed",
        "project_id": project_id,
        "output_path": _to_rel(project_id, str(output_path)),
        "total_clips": len(body_sequence) + (1 if opening else 0) + (1 if ending else 0),
        "cuts_used": len(cut_entries),
        "opening_used": bool(opening),
        "intermission_used": bool(intermission),
        "ending_used": bool(ending),
        "intermission_every_sec": every,
    }


# ---------- 엔드포인트: 수동 병합 ----------


@router.post("/{project_id}/compose")
async def compose_with_interludes(
    project_id: str,
    body: InterludeComposeRequest,
    db: Session = Depends(get_db),
):
    """본편 cut 클립들 + 업로드된 오프닝/간지/엔딩을 조합해 최종 merged 영상 생성.

    시퀀스: [opening?] + cut1 + cut2 + ... (180초마다 intermission 삽입) + ... + [ending?]
    업로드가 없는 kind 는 건너뜀.
    출력: data/{project_id}/output/final_with_interludes.mp4
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        result = await build_interlude_sequence(
            project,
            project_id,
            db,
            override_every_sec=body.intermission_every_sec,
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[interlude] compose failed: {type(e).__name__}: {e}\n{tb}")
        raise HTTPException(500, f"Interlude merge failed: {e}")

    status = result.get("status")
    if status == "skipped":
        reason = result.get("reason", "unknown")
        if reason.startswith("no cut"):
            raise HTTPException(
                400,
                "본편 컷 영상이 아직 없습니다. 영상 생성 단계를 먼저 완료하세요.",
            )
        raise HTTPException(
            400,
            "업로드된 간지 영상이 없습니다. 오프닝/인터미션/엔딩 중 하나는 있어야 합니다.",
        )

    return result
