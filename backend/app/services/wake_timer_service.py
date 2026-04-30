"""Windows wake timer synchronization for LongTube channel schedules."""

from __future__ import annotations

import os
import platform
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from app.config import SYSTEM_DIR


CHANNELS = (1, 2, 3, 4)
TASK_PREFIX = "LongTube Wake CH"
WAKE_MARGIN_MINUTES = int(os.getenv("LONGTUBE_WAKE_MARGIN_MINUTES", "5"))


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def _task_name(channel: int) -> str:
    return f"{TASK_PREFIX}{int(channel)}"


def _wake_time(scheduled_time: str) -> str:
    hh, mm = scheduled_time.split(":")
    base = datetime(2000, 1, 1, int(hh), int(mm))
    wake = base - timedelta(minutes=WAKE_MARGIN_MINUTES)
    return wake.strftime("%H:%M")


def _valid_hhmm(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) != 5 or value[2] != ":":
        return None
    try:
        hh, mm = value.split(":")
        h = int(hh)
        m = int(mm)
    except Exception:
        return None
    if 0 <= h <= 23 and 0 <= m <= 59:
        return f"{h:02d}:{m:02d}"
    return None


def _task_xml(channel: int, scheduled_time: str, wake_time: str) -> str:
    today = datetime.now().date().isoformat()
    start_boundary = f"{today}T{wake_time}:00"
    log_path = SYSTEM_DIR / "wake-timer.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    args = (
        f'/c echo %DATE% %TIME% LongTube wake CH{channel} '
        f'target {scheduled_time} wake {wake_time} >> "{log_path}"'
    )
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>LongTube</Author>
    <Description>Wake this PC {WAKE_MARGIN_MINUTES} minutes before LongTube CH{channel} runs at {escape(scheduled_time)}.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>{escape(start_boundary)}</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>{escape(args)}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _run_schtasks(args: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["schtasks.exe", *args],
            capture_output=True,
            text=True,
            encoding="mbcs",
            errors="replace",
            timeout=15,
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    out = "\n".join(part for part in (proc.stdout.strip(), proc.stderr.strip()) if part)
    return proc.returncode == 0, out


def _register_task(channel: int, scheduled_time: str, wake_time: str) -> dict[str, Any]:
    xml = _task_xml(channel, scheduled_time, wake_time)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            suffix=".xml",
            prefix=f"longtube_wake_ch{channel}_",
            encoding="utf-16",
            delete=False,
        ) as tmp:
            tmp.write(xml)
            temp_path = Path(tmp.name)
        ok, message = _run_schtasks(
            ["/Create", "/TN", _task_name(channel), "/XML", str(temp_path), "/F"]
        )
        return {
            "channel": channel,
            "enabled": ok,
            "scheduled_time": scheduled_time,
            "wake_time": wake_time,
            "task_name": _task_name(channel),
            "message": message,
        }
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _delete_task(channel: int) -> dict[str, Any]:
    ok, message = _run_schtasks(["/Delete", "/TN", _task_name(channel), "/F"])
    # If the task does not exist, the desired disabled state is already true.
    benign = "cannot find" in message.lower() or "지정된 파일을 찾을 수 없습니다" in message
    return {
        "channel": channel,
        "enabled": False,
        "task_name": _task_name(channel),
        "deleted": ok or benign,
        "message": message,
    }


def build_wake_plan(channel_times: dict[str, Any] | None) -> list[dict[str, Any]]:
    times = channel_times or {}
    plan: list[dict[str, Any]] = []
    for channel in CHANNELS:
        scheduled_time = _valid_hhmm(times.get(str(channel)))
        if scheduled_time:
            plan.append(
                {
                    "channel": channel,
                    "enabled": True,
                    "scheduled_time": scheduled_time,
                    "wake_time": _wake_time(scheduled_time),
                    "task_name": _task_name(channel),
                    "margin_minutes": WAKE_MARGIN_MINUTES,
                }
            )
        else:
            plan.append(
                {
                    "channel": channel,
                    "enabled": False,
                    "scheduled_time": None,
                    "wake_time": None,
                    "task_name": _task_name(channel),
                    "margin_minutes": WAKE_MARGIN_MINUTES,
                }
            )
    return plan


def sync_wake_timers(channel_times: dict[str, Any] | None) -> dict[str, Any]:
    """Create/delete Windows tasks that wake the PC before channel schedules."""
    plan = build_wake_plan(channel_times)
    if not _is_windows():
        return {
            "ok": False,
            "supported": False,
            "message": "wake timers are only supported on Windows",
            "plan": plan,
            "results": [],
        }

    results: list[dict[str, Any]] = []
    ok = True
    for item in plan:
        if item["enabled"]:
            result = _register_task(
                int(item["channel"]),
                str(item["scheduled_time"]),
                str(item["wake_time"]),
            )
            ok = ok and bool(result.get("enabled"))
            results.append(result)
        else:
            result = _delete_task(int(item["channel"]))
            ok = ok and bool(result.get("deleted"))
            results.append(result)

    return {
        "ok": ok,
        "supported": True,
        "margin_minutes": WAKE_MARGIN_MINUTES,
        "plan": plan,
        "results": results,
    }
