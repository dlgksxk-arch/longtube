"""Subprocess helper that avoids Windows asyncio SelectorEventLoop issues.

`asyncio.create_subprocess_exec()` raises `NotImplementedError` when the
current asyncio event loop is a `SelectorEventLoop` (Windows default on
Python 3.8+). Uvicorn's `--reload` mode and FastAPI's BackgroundTasks can
both end up with a SelectorEventLoop, even when we try to force
`WindowsProactorEventLoopPolicy` at import time.

Rather than fight asyncio about which loop policy is active, we run all
subprocess calls in a worker thread via `asyncio.to_thread`. This uses the
synchronous `subprocess.run`, which works on every platform and every event
loop without any policy dependency.

This module also provides `find_ffmpeg()` — a robust ffmpeg binary locator
that searches env vars, PATH, common Windows install locations, and as a
last resort falls back to the `imageio-ffmpeg` bundled binary so that
ffmpeg "just works" on most user machines without manual setup.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from functools import lru_cache
from typing import Optional, Tuple


@lru_cache(maxsize=1)
def find_ffmpeg() -> str:
    """Locate an ffmpeg executable. Cached on first successful call.

    Priority:
      1. FFMPEG_BIN or FFMPEG_PATH env var (absolute path to ffmpeg.exe)
      2. shutil.which("ffmpeg") / ("ffmpeg.exe") — PATH lookup
      3. Common Windows install locations
         (C:\\ffmpeg, Program Files, scoop, winget, chocolatey)
      4. imageio-ffmpeg bundled binary (pip install imageio-ffmpeg)

    Raises:
        RuntimeError: with an actionable installation hint in Korean if no
                      ffmpeg is found anywhere.
    """
    # 1. Env var override
    for var in ("FFMPEG_BIN", "FFMPEG_PATH"):
        env = os.environ.get(var, "").strip().strip('"')
        if env and os.path.exists(env):
            print(f"[ffmpeg] resolved via ${var} = {env}")
            return env

    # 2. PATH search
    for name in ("ffmpeg", "ffmpeg.exe"):
        p = shutil.which(name)
        if p:
            print(f"[ffmpeg] resolved via PATH: {p}")
            return p

    # 3. Common Windows install locations
    home = os.path.expanduser("~")
    candidates = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
        os.path.join(home, "scoop", "shims", "ffmpeg.exe"),
        os.path.join(home, "scoop", "apps", "ffmpeg", "current", "bin", "ffmpeg.exe"),
        os.path.join(home, "AppData", "Local", "Microsoft", "WinGet", "Links", "ffmpeg.exe"),
        r"C:\ProgramData\chocolatey\bin\ffmpeg.exe",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
    ]
    for c in candidates:
        if os.path.exists(c):
            print(f"[ffmpeg] resolved via common path: {c}")
            return c

    # 4. imageio-ffmpeg bundled binary (pip package ships one)
    try:
        import imageio_ffmpeg  # type: ignore

        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and os.path.exists(p):
            print(f"[ffmpeg] resolved via imageio-ffmpeg: {p}")
            return p
    except Exception as e:
        print(f"[ffmpeg] imageio-ffmpeg fallback unavailable: {e}")

    raise RuntimeError(
        "ffmpeg 을 찾을 수 없습니다. 다음 중 하나를 해주세요:\n"
        "  1. ffmpeg 설치 후 PATH 추가 (https://www.gyan.dev/ffmpeg/builds/ 에서 release build 다운로드)\n"
        "  2. 또는 FFMPEG_BIN 환경변수에 ffmpeg.exe 절대경로 지정\n"
        "     예) set FFMPEG_BIN=C:\\tools\\ffmpeg\\bin\\ffmpeg.exe\n"
        "  3. 또는 `pip install imageio-ffmpeg` 로 번들 바이너리 설치 (권장 — 백엔드 재시작 필요)\n"
        "검색한 위치: PATH, $FFMPEG_BIN, $FFMPEG_PATH, C:\\ffmpeg, Program Files, scoop, winget, chocolatey"
    )


def ffmpeg_status() -> dict:
    """Return current ffmpeg resolution status for diagnostic endpoints."""
    try:
        path = find_ffmpeg()
        return {"ok": True, "path": path, "source": _classify_ffmpeg_source(path)}
    except RuntimeError as e:
        return {"ok": False, "path": "", "source": "not_found", "error": str(e)}


def _classify_ffmpeg_source(path: str) -> str:
    p = path.lower().replace("\\", "/")
    if "imageio_ffmpeg" in p or "imageio-ffmpeg" in p:
        return "imageio-ffmpeg"
    if "winget" in p:
        return "winget"
    if "scoop" in p:
        return "scoop"
    if "chocolatey" in p:
        return "chocolatey"
    if "program files" in p:
        return "program files"
    if "/c/ffmpeg" in p or p.startswith("c:/ffmpeg"):
        return "c:\\ffmpeg"
    return "path"


async def run_subprocess(
    cmd: list[str],
    *,
    timeout: Optional[float] = None,
    capture_stdout: bool = False,
    capture_stderr: bool = True,
) -> Tuple[int, bytes, bytes]:
    """Run ``cmd`` in a worker thread. Returns (returncode, stdout, stderr).

    stdout/stderr are always returned as bytes (empty bytes if not captured).
    Raises ``asyncio.TimeoutError`` on timeout and ``FileNotFoundError`` if
    the executable isn't found. Never raises on non-zero exit codes — the
    caller should check ``returncode`` themselves.
    """

    def _run() -> Tuple[int, bytes, bytes]:
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
                stderr=subprocess.PIPE if capture_stderr else subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            return (
                int(result.returncode or 0),
                result.stdout if result.stdout is not None else b"",
                result.stderr if result.stderr is not None else b"",
            )
        except subprocess.TimeoutExpired as e:
            raise asyncio.TimeoutError(
                f"Subprocess timed out after {timeout}s: {cmd[0]}"
            ) from e

    return await asyncio.to_thread(_run)
