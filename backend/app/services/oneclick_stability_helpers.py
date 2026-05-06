"""Pure OneClick helpers used by stability-sensitive paths."""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional


DEFAULT_CHANNELS = [1, 2, 3, 4]
QUEUE_EPISODE_FALLBACK = 10**9


def task_rank_for_project_dedupe(task: dict[str, Any]) -> tuple[int, str]:
    """Return ordering key for duplicate task records that point at one project."""
    status = str(task.get("status") or "")
    status_rank = {
        "running": 5,
        "queued": 4,
        "prepared": 3,
        "failed": 2,
        "paused": 2,
        "cancelled": 1,
        "completed": 0,
    }.get(status, 0)
    ts = (
        str(task.get("updated_at") or "")
        or str(task.get("finished_at") or "")
        or str(task.get("started_at") or "")
        or str(task.get("created_at") or "")
    )
    return status_rank, ts


def task_progress_signature(task: dict[str, Any]) -> str:
    """Small stable signature used to detect no-progress stalls."""
    completed = task.get("completed_cuts_by_step") or {}
    current_step = task.get("current_step")
    return json.dumps(
        {
            "status": task.get("status"),
            "step": current_step,
            "progress": round(float(task.get("progress_pct") or 0.0), 3),
            "step_completed": task.get("current_step_completed") or 0,
            "active_cut": task.get("current_step_active_cut"),
            "cut_pct": task.get("current_step_cut_progress_pct"),
            "sub_status": task.get("sub_status"),
            "completed": {str(k): int(v or 0) for k, v in sorted(completed.items())},
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def parse_queue_time_minutes(value: Any) -> Optional[int]:
    if not isinstance(value, str):
        return None
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value)
    if not m:
        return None
    try:
        hour = int(m.group(1))
        minute = int(m.group(2))
    except ValueError:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def queue_episode_sort_value(item: dict[str, Any]) -> int:
    try:
        ep = int(item.get("episode_number") or 0)
    except (TypeError, ValueError):
        ep = 0
    return ep if ep > 0 else QUEUE_EPISODE_FALLBACK


def queue_item_text_sort_value(item: dict[str, Any]) -> str:
    return str(item.get("topic") or item.get("title") or "").casefold()


def queue_item_channel(item: dict[str, Any] | None, channels: list[int] | None = None) -> int:
    valid_channels = channels or DEFAULT_CHANNELS
    try:
        ch = int((item or {}).get("channel") or 1)
    except Exception:
        ch = 1
    return ch if ch in valid_channels else 1


def is_immediate_queue_item(item: dict[str, Any] | None) -> bool:
    if not item:
        return False
    source = str(item.get("queued_source") or "").lower()
    note = str(item.get("queued_note") or "")
    return source == "manual" and (
        "\uc2e4\uc2dc\uac04 \ud604\ud669" in note or "\uc218\ub3d9 \uc2e4\ud589" in note
    )


def queue_channel_due_key(
    ch: int,
    state: dict[str, Any],
    *,
    now: Optional[datetime] = None,
) -> tuple[int, int, int]:
    """Return the next scheduled slot for a channel."""
    now = now or datetime.now()
    ch_key = str(ch)
    minute = parse_queue_time_minutes((state.get("channel_times") or {}).get(ch_key))
    if minute is None:
        return (99, ch, ch)
    today = now.date().isoformat()
    last_run = (state.get("last_run_dates") or {}).get(ch_key)
    day_offset = 1 if last_run == today else 0
    return (day_offset, minute, ch)


def sort_queue_items_for_execution(
    items: list[dict[str, Any]],
    state: dict[str, Any],
    *,
    channels: list[int] | None = None,
    now: Optional[datetime] = None,
) -> list[dict[str, Any]]:
    """Sort queue rows into the same order the scheduler should consume them."""
    valid_channels = channels or DEFAULT_CHANNELS
    immediate: list[dict[str, Any]] = []
    normal: list[dict[str, Any]] = []
    for item in items:
        if is_immediate_queue_item(item):
            immediate.append(item)
        else:
            normal.append(item)

    grouped: dict[int, list[dict[str, Any]]] = {ch: [] for ch in valid_channels}
    for item in normal:
        grouped.setdefault(queue_item_channel(item, valid_channels), []).append(item)

    for group in grouped.values():
        group.sort(
            key=lambda item: (
                queue_episode_sort_value(item),
                str(item.get("queued_at") or ""),
                queue_item_text_sort_value(item),
                str(item.get("id") or ""),
            )
        )

    channel_order = sorted(
        [ch for ch, group in grouped.items() if group],
        key=lambda ch: queue_channel_due_key(ch, state, now=now),
    )
    merged: list[dict[str, Any]] = []
    while any(grouped.get(ch) for ch in channel_order):
        for ch in channel_order:
            group = grouped.get(ch) or []
            if group:
                merged.append(group.pop(0))

    return immediate + merged
