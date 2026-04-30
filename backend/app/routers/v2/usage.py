"""/api/v2/usage — 프리셋 사용량·비용 집계 읽기 전용.

v2.3.1 은 읽기만 연다. 행 삽입(쓰기)은 v2.4.0 task_runner 가 연결되면 거기서
호출하게 된다. 지금은 v1 pipeline_tasks 가 api_logs 에 적는 것과 별개로,
레코드가 생기지 않으면 전부 0 으로 응답한다 — 거짓말 금지 원칙으로
"데이터 없음" 을 그대로 0 으로 표현한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.channel_preset import ChannelPreset
from app.models.database import get_db
from app.models.preset_usage_record import PresetUsageRecord


router = APIRouter()


class UsageByChannel(BaseModel):
    channel_id: int
    total_cost_usd: float
    month_cost_usd: float
    record_count: int


class UsageSummaryOut(BaseModel):
    generated_at: datetime
    window_days: int
    total_cost_usd: float
    month_cost_usd: float
    record_count: int
    by_channel: list[UsageByChannel]


def _month_start_utc(now: datetime) -> datetime:
    """UTC 기준 이번 달 1일 00:00 (tz-aware)."""
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


@router.get("/summary", response_model=UsageSummaryOut)
def usage_summary(
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """전역 합계 + 채널별 합계 + 이번 달 합계.

    - `total_cost_usd` 는 최근 `window_days` 일의 합.
    - `month_cost_usd` 는 달력 기준 이번 달(UTC) 합.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)
    month_start = _month_start_utc(now)

    # preset_id → channel_id 매핑 (rows.preset_id 가 SET NULL 일 수 있으므로
    # 집계는 preset 테이블과 JOIN 해서 channel 로 묶는다).
    chan_col = ChannelPreset.channel_id

    # 전역 최근 window 합.
    total_row = (
        db.query(func.coalesce(func.sum(PresetUsageRecord.cost_usd), 0.0))
        .filter(PresetUsageRecord.recorded_at >= window_start)
        .first()
    )
    total_cost = float(total_row[0]) if total_row else 0.0

    # 이번 달 합.
    month_row = (
        db.query(func.coalesce(func.sum(PresetUsageRecord.cost_usd), 0.0))
        .filter(PresetUsageRecord.recorded_at >= month_start)
        .first()
    )
    month_cost = float(month_row[0]) if month_row else 0.0

    # 행 수 (window).
    count_row = (
        db.query(func.count(PresetUsageRecord.id))
        .filter(PresetUsageRecord.recorded_at >= window_start)
        .first()
    )
    record_count = int(count_row[0]) if count_row else 0

    # 채널별 합. 윈도우/월 각각.
    by_ch_window = dict(
        db.query(chan_col, func.coalesce(func.sum(PresetUsageRecord.cost_usd), 0.0))
        .join(ChannelPreset, ChannelPreset.id == PresetUsageRecord.preset_id)
        .filter(PresetUsageRecord.recorded_at >= window_start)
        .group_by(chan_col)
        .all()
    )
    by_ch_month = dict(
        db.query(chan_col, func.coalesce(func.sum(PresetUsageRecord.cost_usd), 0.0))
        .join(ChannelPreset, ChannelPreset.id == PresetUsageRecord.preset_id)
        .filter(PresetUsageRecord.recorded_at >= month_start)
        .group_by(chan_col)
        .all()
    )
    by_ch_count = dict(
        db.query(chan_col, func.count(PresetUsageRecord.id))
        .join(ChannelPreset, ChannelPreset.id == PresetUsageRecord.preset_id)
        .filter(PresetUsageRecord.recorded_at >= window_start)
        .group_by(chan_col)
        .all()
    )

    by_channel = [
        UsageByChannel(
            channel_id=ch,
            total_cost_usd=float(by_ch_window.get(ch, 0.0)),
            month_cost_usd=float(by_ch_month.get(ch, 0.0)),
            record_count=int(by_ch_count.get(ch, 0)),
        )
        for ch in (1, 2, 3, 4)
    ]

    return UsageSummaryOut(
        generated_at=now,
        window_days=window_days,
        total_cost_usd=total_cost,
        month_cost_usd=month_cost,
        record_count=record_count,
        by_channel=by_channel,
    )


class UsagePresetRow(BaseModel):
    preset_id: int
    channel_id: int
    name: str
    total_cost_usd: float
    record_count: int


@router.get("/by-preset", response_model=list[UsagePresetRow])
def usage_by_preset(
    channel_id: Optional[int] = None,
    window_days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """프리셋별 합계 (최근 window_days). 프리셋 카드 "총 비용" 렌더용."""
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(days=window_days)

    q = (
        db.query(
            ChannelPreset.id,
            ChannelPreset.channel_id,
            ChannelPreset.name,
            func.coalesce(func.sum(PresetUsageRecord.cost_usd), 0.0),
            func.count(PresetUsageRecord.id),
        )
        .outerjoin(
            PresetUsageRecord,
            (PresetUsageRecord.preset_id == ChannelPreset.id)
            & (PresetUsageRecord.recorded_at >= window_start),
        )
        .group_by(ChannelPreset.id)
    )
    if channel_id is not None:
        q = q.filter(ChannelPreset.channel_id == channel_id)
    rows = q.order_by(ChannelPreset.channel_id, ChannelPreset.id).all()
    return [
        UsagePresetRow(
            preset_id=r[0],
            channel_id=r[1],
            name=r[2],
            total_cost_usd=float(r[3]),
            record_count=int(r[4]),
        )
        for r in rows
    ]
