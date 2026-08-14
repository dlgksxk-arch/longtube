"""Fixed YouTube publication schedule for newly uploaded production videos."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


PUBLISH_TIMEZONE = ZoneInfo("Asia/Seoul")
MAIN_PUBLISH_TIME = time(18, 0)
SHORTS_PUBLISH_TIMES = (time(9, 0), time(12, 0), time(15, 0), time(16, 0))
MINIMUM_SCHEDULE_LEAD = timedelta(minutes=10)


def _local_now(now: datetime | None = None) -> datetime:
    current = now or datetime.now(tz=PUBLISH_TIMEZONE)
    if current.tzinfo is None:
        return current.replace(tzinfo=PUBLISH_TIMEZONE)
    return current.astimezone(PUBLISH_TIMEZONE)


def _publish_at(day: date, clock: time) -> str:
    scheduled = datetime.combine(day, clock, tzinfo=PUBLISH_TIMEZONE)
    return scheduled.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def next_production_publish_schedule(now: datetime | None = None) -> dict[str, object]:
    """Return the earliest KST day where the complete main/Shorts batch is future."""
    current = _local_now(now)
    day = current.date()
    first_short = datetime.combine(day, SHORTS_PUBLISH_TIMES[0], tzinfo=PUBLISH_TIMEZONE)
    if current + MINIMUM_SCHEDULE_LEAD >= first_short:
        day += timedelta(days=1)

    return {
        "timezone": str(PUBLISH_TIMEZONE),
        "publish_date": day.isoformat(),
        "main": _publish_at(day, MAIN_PUBLISH_TIME),
        "shorts": [_publish_at(day, clock) for clock in SHORTS_PUBLISH_TIMES],
    }


def next_main_publish_at(now: datetime | None = None) -> str:
    """Return the next 18:00 KST publication slot for a standalone main upload."""
    current = _local_now(now)
    day = current.date()
    slot = datetime.combine(day, MAIN_PUBLISH_TIME, tzinfo=PUBLISH_TIMEZONE)
    if current + MINIMUM_SCHEDULE_LEAD >= slot:
        day += timedelta(days=1)
    return _publish_at(day, MAIN_PUBLISH_TIME)
