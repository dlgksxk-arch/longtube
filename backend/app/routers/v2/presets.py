"""/api/v2/presets — 채널 프리셋 CRUD + 인터루드(오프닝/간지/엔딩 영상).

기획 §9 (목록) / §10 (편집) 대응.
본 릴리즈(v2.1.0) 에서는 목록/생성/수정/삭제 골격만 연다.
9 섹션 설정 JSON 의 구체 스키마 검증은 v2.2.0 에서 보강한다.

v2.4.0: "영상 구조" 섹션(§10.3 섹션 4) 에 인터루드 업로드 슬롯이 추가됐다.
프리셋 단위로 오프닝/인터미션/엔딩 영상을 한 번 업로드해 두면 그 프리셋이
만드는 모든 태스크가 자동으로 끼워 넣는다. 파일 IO 는 v1 인터루드 라우터와
공통인 ``services.interlude_service`` 를 호출한다 — 중복 구현 없음.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.config import DATA_DIR
from app.models.database import get_db
from app.models.channel_preset import (
    ChannelPreset,
    FORM_TYPE_DDALKKAK,
)
from app.services.interlude_service import (
    VALID_KINDS,
    DEFAULT_INTERMISSION_EVERY,
    save_uploaded_video,
    delete_uploaded_video,
)


router = APIRouter()


# ---------- 인터루드 공통 헬퍼 ----------


def _preset_interlude_dir(preset_id: int) -> Path:
    """프리셋 단위 인터루드 저장 디렉토리.

    ``{DATA_DIR}/presets/{preset_id}/interlude/`` 아래에 ``opening.mp4`` /
    ``intermission.mov`` / ``ending.mkv`` 같은 식으로 저장된다. v1 의
    ``{DATA_DIR}/{project_id}/interlude/`` 와 구조만 한 단계 다르다.
    """
    d = DATA_DIR / "presets" / str(preset_id) / "interlude"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _to_rel(preset_id: int, abs_path: str) -> str:
    """DATA_DIR 기준 상대 경로로 변환. 정적 마운트(/assets) 경로와 정합."""
    root = str(DATA_DIR).replace("\\", "/")
    p = str(abs_path).replace("\\", "/")
    if p.startswith(root):
        return p[len(root):].lstrip("/")
    return abs_path


def _read_interlude_from_config(preset: ChannelPreset) -> dict:
    """preset.config["interlude"] 를 dict 로 안전 반환(복사본).

    intermission_every_sec 기본값 주입까지 포함.
    """
    cfg = dict(preset.config or {})
    inter = dict(cfg.get("interlude") or {})
    if "intermission_every_sec" not in inter:
        inter["intermission_every_sec"] = DEFAULT_INTERMISSION_EVERY
    return inter


def _save_interlude_to_config(
    preset: ChannelPreset, inter: dict, db: Session
) -> None:
    cfg = dict(preset.config or {})
    cfg["interlude"] = inter
    preset.config = cfg
    flag_modified(preset, "config")
    db.commit()


FormType = Literal["딸깍폼", "테스트폼"]


class PresetOut(BaseModel):
    """목록용 응답. v2.3.0 부터 카드에 표시할 rich meta 를 위해
    `config` 와 `updated_at` 을 함께 내려준다.

    v1.x 목록에서 카드 정보 밀도가 좋았는데 v2.2.0 목록이 name 만
    보여줘 허전하다는 피드백(디자인 크리틱 우선순위 1)을 반영.
    프리셋 개수는 최대 8개(딸깍폼 4 + 테스트폼 N, 실제로는 두 자리)
    수준이라 config 동봉이 부담되지 않는다.
    """

    id: int
    channel_id: int
    form_type: FormType
    name: str
    full_name: str
    is_modified: bool
    config: dict = Field(default_factory=dict)
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PresetDetail(PresetOut):
    pass


class PresetCreateBody(BaseModel):
    channel_id: int = Field(ge=1, le=4)
    form_type: FormType
    name: str = Field(min_length=1, max_length=64)
    config: dict = Field(default_factory=dict)


class PresetUpdateBody(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    channel_id: Optional[int] = Field(default=None, ge=1, le=4)
    form_type: Optional[FormType] = None
    config: Optional[dict] = None


@router.get("/", response_model=list[PresetOut])
def list_presets(
    channel_id: Optional[int] = None,
    form_type: Optional[FormType] = None,
    db: Session = Depends(get_db),
):
    q = db.query(ChannelPreset)
    if channel_id is not None:
        q = q.filter(ChannelPreset.channel_id == channel_id)
    if form_type is not None:
        q = q.filter(ChannelPreset.form_type == form_type)
    rows = q.order_by(ChannelPreset.updated_at.desc()).all()
    return rows


@router.get("/{preset_id}", response_model=PresetDetail)
def get_preset(preset_id: int, db: Session = Depends(get_db)):
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")
    return row


@router.post("/", response_model=PresetDetail, status_code=201)
def create_preset(body: PresetCreateBody, db: Session = Depends(get_db)):
    if body.form_type == FORM_TYPE_DDALKKAK:
        dup = (
            db.query(ChannelPreset)
            .filter(
                ChannelPreset.channel_id == body.channel_id,
                ChannelPreset.form_type == FORM_TYPE_DDALKKAK,
            )
            .first()
        )
        if dup is not None:
            raise HTTPException(
                409,
                f"channel {body.channel_id} already has a '딸깍폼' preset",
            )
    row = ChannelPreset(
        channel_id=body.channel_id,
        form_type=body.form_type,
        name=body.name,
        config=body.config or {},
    )
    row.recompute_full_name()
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{preset_id}", response_model=PresetDetail)
def update_preset(
    preset_id: int, body: PresetUpdateBody, db: Session = Depends(get_db)
):
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")

    if body.name is not None:
        row.name = body.name
    if body.channel_id is not None:
        row.channel_id = body.channel_id
    if body.form_type is not None:
        row.form_type = body.form_type
    if body.config is not None:
        row.config = body.config

    # 딸깍폼 유일성 재확인 (채널/폼타입이 변경될 수 있으므로).
    if row.form_type == FORM_TYPE_DDALKKAK:
        dup = (
            db.query(ChannelPreset)
            .filter(
                ChannelPreset.channel_id == row.channel_id,
                ChannelPreset.form_type == FORM_TYPE_DDALKKAK,
                ChannelPreset.id != row.id,
            )
            .first()
        )
        if dup is not None:
            raise HTTPException(
                409,
                f"channel {row.channel_id} already has a '딸깍폼' preset",
            )

    row.recompute_full_name()
    row.is_modified = False
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")
    db.delete(row)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# v2.4.0 — 프리셋 단위 인터루드 업로드/조회/삭제 (§10.3 섹션 4)
# ---------------------------------------------------------------------------


class InterludeEntryOut(BaseModel):
    """한 kind 의 현재 상태. 없으면 null 필드들을 그대로 내려준다."""

    video_path: Optional[str] = None
    """DATA_DIR 기준 상대 경로. 프런트는 ``{V2_API_BASE}/../assets/{video_path}`` 로 접근."""
    filename: Optional[str] = None
    size_bytes: Optional[int] = None
    duration: Optional[float] = None
    source: Optional[str] = None


class InterludeStateOut(BaseModel):
    preset_id: int
    opening: InterludeEntryOut = Field(default_factory=InterludeEntryOut)
    intermission: InterludeEntryOut = Field(default_factory=InterludeEntryOut)
    ending: InterludeEntryOut = Field(default_factory=InterludeEntryOut)
    intermission_every_sec: int = DEFAULT_INTERMISSION_EVERY


class InterludeConfigUpdate(BaseModel):
    intermission_every_sec: Optional[int] = Field(
        default=None, ge=30, le=1800,
        description="본편 중간에 인터미션을 끼워넣을 간격(초). 기본 180(3분).",
    )


def _entry_for_kind(
    preset_id: int, inter: dict, kind: str
) -> InterludeEntryOut:
    """config 에 기록된 kind 엔트리를 디스크와 교차 검증 후 응답 모델로 변환."""
    entry = dict(inter.get(kind) or {})
    vp = entry.get("video_path")
    if vp:
        abs_p = DATA_DIR / vp  # vp 는 DATA_DIR 기준 상대 경로
        if not abs_p.exists():
            # DB 에는 남았는데 파일이 사라진 경우 — null 처리해서 UI가 재업로드 유도.
            entry["video_path"] = None
    return InterludeEntryOut(
        video_path=entry.get("video_path"),
        filename=entry.get("filename"),
        size_bytes=entry.get("size_bytes"),
        duration=entry.get("duration"),
        source=entry.get("source"),
    )


@router.get("/{preset_id}/interlude", response_model=InterludeStateOut)
def get_preset_interludes(preset_id: int, db: Session = Depends(get_db)):
    """프리셋의 오프닝/인터미션/엔딩 영상 상태 조회."""
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")

    inter = _read_interlude_from_config(row)
    return InterludeStateOut(
        preset_id=preset_id,
        opening=_entry_for_kind(preset_id, inter, "opening"),
        intermission=_entry_for_kind(preset_id, inter, "intermission"),
        ending=_entry_for_kind(preset_id, inter, "ending"),
        intermission_every_sec=int(
            inter.get("intermission_every_sec") or DEFAULT_INTERMISSION_EVERY
        ),
    )


@router.put("/{preset_id}/interlude/config", response_model=InterludeStateOut)
def update_preset_interlude_config(
    preset_id: int,
    body: InterludeConfigUpdate,
    db: Session = Depends(get_db),
):
    """인터미션 주기 등 설정값 갱신."""
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")

    inter = _read_interlude_from_config(row)
    if body.intermission_every_sec is not None:
        inter["intermission_every_sec"] = body.intermission_every_sec
    _save_interlude_to_config(row, inter, db)

    return InterludeStateOut(
        preset_id=preset_id,
        opening=_entry_for_kind(preset_id, inter, "opening"),
        intermission=_entry_for_kind(preset_id, inter, "intermission"),
        ending=_entry_for_kind(preset_id, inter, "ending"),
        intermission_every_sec=int(
            inter.get("intermission_every_sec") or DEFAULT_INTERMISSION_EVERY
        ),
    )


@router.post("/{preset_id}/interlude/upload/{kind}", response_model=InterludeEntryOut)
async def upload_preset_interlude(
    preset_id: int,
    kind: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """오프닝/인터미션/엔딩 영상 업로드. 500MB cap, 6 확장자 허용.

    파일 IO 는 ``services.interlude_service.save_uploaded_video`` 에 위임.
    본 핸들러는 프리셋 존재 검증 + 저장된 메타를 ``preset.config`` 에 기록만 함.
    """
    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")

    target = _preset_interlude_dir(preset_id)
    meta = await save_uploaded_video(target, kind, file)

    inter = _read_interlude_from_config(row)
    inter[kind] = {
        "video_path": _to_rel(preset_id, meta["video_path"]),
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
        "duration": meta["duration"],
        "source": meta["source"],
    }
    _save_interlude_to_config(row, inter, db)

    print(
        f"[v2-interlude] uploaded preset={preset_id} kind={kind} "
        f"file={meta['filename']} size={meta['size_bytes']} "
        f"duration={meta['duration']:.2f}s"
    )

    return InterludeEntryOut(**inter[kind])


@router.delete("/{preset_id}/interlude/{kind}", status_code=204)
def delete_preset_interlude(
    preset_id: int, kind: str, db: Session = Depends(get_db)
):
    """저장된 인터루드 파일 + config 엔트리 삭제."""
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"Invalid kind: {kind}")

    row = db.query(ChannelPreset).filter(ChannelPreset.id == preset_id).first()
    if row is None:
        raise HTTPException(404, "preset not found")

    delete_uploaded_video(_preset_interlude_dir(preset_id), kind)

    inter = _read_interlude_from_config(row)
    inter.pop(kind, None)
    _save_interlude_to_config(row, inter, db)

    return None
