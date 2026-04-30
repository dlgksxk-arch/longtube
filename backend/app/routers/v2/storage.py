"""/api/v2/storage — 결과 저장소 경로 설정.

기획 §4 / §15.3. 현재 DATA_DIR 표시, 디스크 용량, 하위 디렉터리 용량 요약.
저장소 변경은 v2.3.0 에서 `.env` 쓰기 + 프로세스 재시작 안내 패턴으로 붙인다.
v2.1.0 은 조회만 연다.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import DATA_DIR, LEGACY_DATA_DIR, BASE_DIR


router = APIRouter()


def _dir_size_bytes(p: Path) -> int:
    total = 0
    if not p.exists():
        return 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


class StorageInfo(BaseModel):
    data_dir: str
    legacy_data_dir: str
    base_dir: str
    disk_total_bytes: int
    disk_free_bytes: int
    data_dir_bytes: int
    legacy_bytes: int
    presets_bytes: int
    tasks_bytes: int


@router.get("/info", response_model=StorageInfo)
def info():
    data_dir = Path(DATA_DIR)
    try:
        total, used, free = shutil.disk_usage(
            data_dir if data_dir.exists() else BASE_DIR
        )
    except OSError:
        total, used, free = 0, 0, 0
    return StorageInfo(
        data_dir=str(data_dir),
        legacy_data_dir=str(LEGACY_DATA_DIR),
        base_dir=str(BASE_DIR),
        disk_total_bytes=int(total),
        disk_free_bytes=int(free),
        data_dir_bytes=_dir_size_bytes(data_dir),
        legacy_bytes=_dir_size_bytes(Path(LEGACY_DATA_DIR)),
        presets_bytes=_dir_size_bytes(data_dir / "presets"),
        tasks_bytes=_dir_size_bytes(data_dir / "tasks"),
    )
