"""OneClick queue input normalization."""
from __future__ import annotations

import uuid
from typing import Any, Callable, Optional


ProjectLoader = Callable[[str], Any]


def _base_channel_map(channels: list[int], value: Any = None) -> dict[str, Any]:
    return {str(ch): value for ch in channels}


def normalize_queue_state(
    raw: Any,
    *,
    channels: list[int],
    main_target_duration: int,
    main_cut_count: int,
    load_project: Optional[ProjectLoader] = None,
) -> dict[str, Any]:
    """Coerce persisted/UI queue payload into the canonical queue schema."""
    out: dict[str, Any] = {
        "channel_times": _base_channel_map(channels, None),
        "last_run_dates": _base_channel_map(channels, None),
        "channel_presets": _base_channel_map(channels, None),
        "items": [],
    }
    if not isinstance(raw, dict):
        return out

    ct = raw.get("channel_times")
    if isinstance(ct, dict):
        for ch in channels:
            v = ct.get(str(ch))
            if isinstance(v, str) and len(v) == 5 and v[2] == ":":
                out["channel_times"][str(ch)] = v
    legacy_dt = raw.get("daily_time")
    first_ch = str(channels[0]) if channels else "1"
    if isinstance(legacy_dt, str) and len(legacy_dt) == 5 and legacy_dt[2] == ":":
        if not out["channel_times"].get(first_ch):
            out["channel_times"][first_ch] = legacy_dt

    lrd = raw.get("last_run_dates")
    if isinstance(lrd, dict):
        for ch in channels:
            v = lrd.get(str(ch))
            if isinstance(v, str) and len(v) == 10:
                out["last_run_dates"][str(ch)] = v
    legacy_lrd = raw.get("last_run_date")
    if isinstance(legacy_lrd, str) and len(legacy_lrd) == 10:
        if not out["last_run_dates"].get(first_ch):
            out["last_run_dates"][first_ch] = legacy_lrd

    cp = raw.get("channel_presets")
    if isinstance(cp, dict):
        for ch in channels:
            v = cp.get(str(ch))
            if v is None or v == "":
                out["channel_presets"][str(ch)] = None
            else:
                out["channel_presets"][str(ch)] = str(v)

    items = raw.get("items")
    if not isinstance(items, list):
        return out

    clean: list[dict[str, Any]] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        topic = str(it.get("topic") or "").strip()
        if not topic:
            continue

        ch_raw = it.get("channel")
        ch: Optional[int] = None
        try:
            if ch_raw is not None and str(ch_raw).strip() != "":
                ch = int(ch_raw)
        except (TypeError, ValueError):
            ch = None
        if ch is None and load_project is not None:
            tpl_id = it.get("template_project_id")
            if tpl_id:
                try:
                    tpl = load_project(str(tpl_id))
                    cfg_ch = (tpl.config or {}).get("youtube_channel") if tpl else None
                    if cfg_ch is not None and str(cfg_ch).strip() != "":
                        ch = int(cfg_ch)
                except Exception:
                    ch = None
        if ch is None:
            ch = channels[0] if channels else 1
        if ch not in channels:
            ch = channels[0] if channels else 1

        def _clean_list_of_str(xs):
            if not isinstance(xs, list):
                return []
            return [str(x) for x in xs]

        ep_num: Optional[int] = None
        try:
            ep_raw = it.get("episode_number")
            if isinstance(ep_raw, (int, float)) and int(ep_raw) > 0:
                ep_num = int(ep_raw)
        except Exception:
            ep_num = None

        queued_source = str(it.get("queued_source") or "manual").strip().lower()
        if queued_source not in ("manual", "import", "requeue", "orphan", "schedule", "system"):
            queued_source = "manual"

        clean.append({
            "id": str(it.get("id") or uuid.uuid4().hex[:8]),
            "topic": topic,
            "template_project_id": (it.get("template_project_id") or None),
            "target_duration": main_target_duration,
            "target_cuts": main_cut_count,
            "channel": ch,
            "openings": _clean_list_of_str(it.get("openings")),
            "endings": _clean_list_of_str(it.get("endings")),
            "core_content": str(it.get("core_content") or ""),
            "episode_number": ep_num,
            "next_episode_preview": str(it.get("next_episode_preview") or ""),
            "queued_source": queued_source,
            "queued_at": str(it.get("queued_at") or "").strip() or None,
            "queued_note": str(it.get("queued_note") or "").strip(),
            "requeued_from_task_id": str(it.get("requeued_from_task_id") or "").strip(),
            "restored_from_project_id": str(it.get("restored_from_project_id") or "").strip(),
        })

    out["items"] = clean
    return out
