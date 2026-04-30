"""Interlude (오프닝/간지/엔딩) 공용 서비스.

v2.4.0 신규. 기존 v1 `routers/interlude.py` 에 갇혀 있던 업로드/삭제/ffprobe
로직을 재사용 가능한 서비스 모듈로 분리한다. v1 라우터(프로젝트 범위) 와
v2 프리셋 라우터(프리셋 범위) 가 모두 이 모듈을 호출한다.

설계 원칙:
    - 저장 경로와 config 위치는 **호출자가** 넘긴다. 이 모듈은 "주어진 디렉토리"
      에 "주어진 kind 의 파일을 저장/삭제/조회" 만 책임진다.
    - 사이드 이펙트(DB commit) 는 호출자가 직접 한다. 이 모듈은 파일 IO 와
      메타 dict 생성까지만.
    - FastAPI 의 `UploadFile` 을 stream-read 하는 코어 로직은 그대로 재현
      (500MB cap, 확장자 검증, 원자적 실패 복구).

v1 라우터와의 차이:
    - v1 은 ``DATA_DIR / {project_id} / interlude`` 고정이었지만, v2 는
      ``DATA_DIR / presets / {preset_id} / interlude`` 로 쓴다. 즉 "어느
      디렉토리냐" 만 다르고 나머지는 완전히 동일.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal

from fastapi import HTTPException, UploadFile

from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess


# ---------- 상수 ----------

InterludeKind = Literal["opening", "intermission", "ending"]
VALID_KINDS: tuple[str, ...] = ("opening", "intermission", "ending")
"""허용되는 3 가지 종류. 변경 시 프런트 UI 의 드롭다운도 맞춰야 한다."""

DEFAULT_INTERMISSION_EVERY = 180  # seconds
"""기본 인터미션 주기 — 3 분."""

ALLOWED_VIDEO_EXTS: frozenset[str] = frozenset({
    ".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi",
})
"""업로드 허용 확장자 (소문자 비교 기준)."""

MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB
"""단일 파일 최대 크기. 4K 60fps 3분짜리도 H.264 라면 300MB 대라 넉넉."""


# ---------- ffprobe ----------


async def ffprobe_duration(video_path: str) -> float:
    """영상 길이(초) 반환. 실패하면 0.0."""
    try:
        ffbin = find_ffmpeg()
        ffprobe = ffbin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        if not os.path.exists(ffprobe):
            return 0.0
        rc, stdout, _ = await run_subprocess(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            timeout=30.0,
            capture_stdout=True,
            capture_stderr=False,
        )
        if rc != 0:
            return 0.0
        txt = (stdout or b"").decode(errors="replace").strip()
        return float(txt) if txt else 0.0
    except Exception:
        return 0.0


# ---------- 업로드 ----------


async def save_uploaded_video(
    target_dir: Path,
    kind: str,
    file: UploadFile,
) -> dict:
    """``target_dir/{kind}{ext}`` 에 업로드 파일 저장 후 메타 dict 반환.

    같은 kind 의 기존 파일(확장자 무관) 은 전부 먼저 지운다. 용량 초과 시
    HTTP 413 을 던지며 부분 기록된 파일을 복구(unlink) 한다.

    반환값 예::
        {
          "video_path": "<abs path>",
          "filename": "원본 업로드 파일명",
          "size_bytes": 12345,
          "duration": 12.34,
          "source": "upload",
        }
    """
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"Invalid kind: {kind}. Must be one of {VALID_KINDS}")

    target_dir.mkdir(parents=True, exist_ok=True)

    orig_name = (file.filename or "").strip()
    ext = Path(orig_name).suffix.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        raise HTTPException(
            400,
            f"허용되지 않은 확장자: {ext or '(없음)'}. "
            f"허용: {sorted(ALLOWED_VIDEO_EXTS)}",
        )

    # 같은 kind 의 이전 업로드(확장자만 달라진 경우 포함) 정리.
    for old in target_dir.glob(f"{kind}.*"):
        try:
            old.unlink()
        except OSError:
            pass

    dest = target_dir / f"{kind}{ext}"
    total = 0
    try:
        with open(dest, "wb") as out_f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    out_f.close()
                    try:
                        dest.unlink()
                    except OSError:
                        pass
                    raise HTTPException(
                        413,
                        f"업로드 용량 초과: {total} bytes > {MAX_UPLOAD_BYTES} bytes",
                    )
                out_f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try:
            dest.unlink()
        except OSError:
            pass
        raise HTTPException(500, f"업로드 저장 실패: {type(e).__name__}: {e}")

    if not dest.exists() or dest.stat().st_size == 0:
        raise HTTPException(500, "업로드 파일이 저장되지 않았습니다.")

    duration = await ffprobe_duration(str(dest))

    return {
        "video_path": str(dest),
        "filename": orig_name or dest.name,
        "size_bytes": dest.stat().st_size,
        "duration": duration,
        "source": "upload",
    }


# ---------- 삭제 ----------


def delete_uploaded_video(target_dir: Path, kind: str) -> None:
    """해당 kind 의 모든 파일(확장자 무관) 삭제. 없으면 noop."""
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"Invalid kind: {kind}")

    if not target_dir.exists():
        return

    for old in target_dir.glob(f"{kind}.*"):
        try:
            old.unlink()
        except OSError:
            pass


# ---------- 조회 유틸 ----------


def existing_kind_path(target_dir: Path, kind: str) -> Optional[Path]:
    """``target_dir`` 아래에서 해당 kind 로 저장된 파일이 실제로 존재하면 그 경로를 반환."""
    if kind not in VALID_KINDS:
        return None
    if not target_dir.exists():
        return None
    for p in target_dir.glob(f"{kind}.*"):
        if p.is_file():
            return p
    return None
