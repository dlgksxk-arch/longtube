"""Cross-call guard for script generation.

The guard keeps one project from issuing duplicate script LLM calls.  When a
generation is already active, later callers wait without a timeout and reuse the
completed script instead of starting another provider request.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from app.config import resolve_project_dir
from app.services.cancel_ctx import raise_if_cancelled


class ScriptGenerationGuard:
    def __init__(
        self,
        project_id: str,
        config: Optional[dict] = None,
        *,
        reuse_existing: bool = False,
        poll_interval: float = 2.0,
        log: Optional[Callable[[str], None]] = None,
    ):
        self.project_id = str(project_id or "")
        self.config = dict(config or {})
        self.reuse_existing = bool(reuse_existing)
        self.poll_interval = max(0.5, float(poll_interval or 2.0))
        self.log = log
        self.token = uuid.uuid4().hex
        self.lock_path: Optional[Path] = None
        self._fd: Optional[int] = None
        self.acquired = False
        self.reused_existing = False

    def _project_dir(self, create: bool) -> Path:
        return resolve_project_dir(self.project_id, self.config, create=create)

    def _script_path(self) -> Path:
        return self._project_dir(create=False) / "script.json"

    def _expected_cuts(self) -> int:
        for key in ("target_cuts", "total_cuts"):
            try:
                value = int(self.config.get(key) or 0)
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                return value
        return 0

    def _load_completed_script(self) -> Optional[dict]:
        path = self._script_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        cuts = payload.get("cuts") if isinstance(payload, dict) else None
        if not isinstance(cuts, list) or not cuts:
            return None
        expected = self._expected_cuts()
        if expected > 0 and len(cuts) != expected:
            return None
        return payload

    def _ensure_lock_path(self) -> Path:
        if self.lock_path is None:
            lock_dir = self._project_dir(create=True) / "llm_raw"
            lock_dir.mkdir(parents=True, exist_ok=True)
            self.lock_path = lock_dir / "script_generation.lock"
        return self.lock_path

    @staticmethod
    def _pid_exists(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                return str(pid) in (result.stdout or "")
            except Exception:
                return True
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True

    def _lock_owner_alive(self, path: Path) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pid = int(data.get("pid") or 0)
        except Exception:
            return True
        return self._pid_exists(pid)

    def _try_acquire(self) -> bool:
        path = self._ensure_lock_path()
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        fd = os.open(str(path), flags)
        meta = {
            "project_id": self.project_id,
            "pid": os.getpid(),
            "token": self.token,
            "started_at": time.time(),
        }
        os.write(fd, json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        os.close(fd)
        self._fd = None
        self.acquired = True
        return True

    def acquire(self) -> Optional[dict]:
        last_log = 0.0
        waited_for_lock = False
        while True:
            raise_if_cancelled(f"script generation lock {self.project_id}")
            if self.reuse_existing or waited_for_lock:
                script = self._load_completed_script()
                if script is not None:
                    self.reused_existing = True
                    return script
            try:
                self._try_acquire()
                if self.reuse_existing:
                    script = self._load_completed_script()
                    if script is not None:
                        self.reused_existing = True
                        self.release()
                        return script
                return None
            except FileExistsError:
                waited_for_lock = True
                path = self._ensure_lock_path()
                if not self._lock_owner_alive(path):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                now = time.monotonic()
                if self.log and now - last_log >= 30:
                    self.log(f"[Script] 대본 생성 중복 호출 차단: {self.project_id} 기존 호출 완료 대기")
                    last_log = now
                time.sleep(self.poll_interval)

    async def acquire_async(self) -> Optional[dict]:
        last_log = 0.0
        waited_for_lock = False
        while True:
            raise_if_cancelled(f"script generation lock {self.project_id}")
            if self.reuse_existing or waited_for_lock:
                script = self._load_completed_script()
                if script is not None:
                    self.reused_existing = True
                    return script
            try:
                self._try_acquire()
                if self.reuse_existing:
                    script = self._load_completed_script()
                    if script is not None:
                        self.reused_existing = True
                        self.release()
                        return script
                return None
            except FileExistsError:
                waited_for_lock = True
                path = self._ensure_lock_path()
                if not self._lock_owner_alive(path):
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                now = time.monotonic()
                if self.log and now - last_log >= 30:
                    self.log(f"[Script] 대본 생성 중복 호출 차단: {self.project_id} 기존 호출 완료 대기")
                    last_log = now
                await asyncio.sleep(self.poll_interval)

    def release(self) -> None:
        if not self.acquired:
            return
        path = self._ensure_lock_path()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("token") == self.token:
                path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass
        finally:
            self.acquired = False

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
