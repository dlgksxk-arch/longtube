"""In-memory background task manager for generation jobs"""
import asyncio
import time
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class TaskState:
    task_id: str
    project_id: str
    step: str  # "voice", "image", "video", "subtitle"
    status: str = "running"  # running, completed, failed, cancelled
    total: int = 0
    completed: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    error: Optional[str] = None
    results: list = field(default_factory=list)
    # Per-item failure records: [{"cut_number": int, "error": str}, ...]
    item_errors: list = field(default_factory=list)
    # Track individual item completion timestamps for accurate ETA
    _item_timestamps: list = field(default_factory=list)
    # v1.1.49: 단일 작업(대본/렌더링)의 시간 기반 추정을 위한 예상 총 소요 시간(초)
    estimated_total_seconds: float = 0.0

    def record_item_done(self):
        """Record timestamp when an item finishes."""
        self._item_timestamps.append(time.time())

    @property
    def progress_pct(self) -> int:
        if self.total <= 0:
            return 0
        # v1.1.49: 단일 작업(total=1, completed=0) + 예상 시간이 있으면 시간 기반 추정
        if self.total == 1 and self.completed == 0 and self.estimated_total_seconds > 0 and self.status == "running":
            elapsed = self.elapsed
            pct = min(95, int((elapsed / self.estimated_total_seconds) * 100))
            return max(1, pct)  # 최소 1% (사용자에게 진행 중임을 표시)
        return min(100, int(self.completed / self.total * 100))

    @property
    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at

    @property
    def eta_seconds(self) -> int:
        # v1.1.49: 단일 작업 시간 기반 ETA
        if self.total == 1 and self.completed == 0 and self.estimated_total_seconds > 0 and self.status == "running":
            remaining = max(0, self.estimated_total_seconds - self.elapsed)
            return int(remaining)
        if self.completed <= 0:
            return 0
        remaining = self.total - self.completed
        if remaining <= 0:
            return 0

        # Use recent items (last 5) for more accurate ETA
        timestamps = self._item_timestamps
        if len(timestamps) >= 2:
            # Calculate per-item duration from recent completions
            recent = timestamps[-min(5, len(timestamps)):]
            recent_durations = [recent[i] - recent[i-1] for i in range(1, len(recent))]
            avg_per_item = sum(recent_durations) / len(recent_durations)
            return int(avg_per_item * remaining)

        # Only 1 item done: use total elapsed but note first item often includes cold start
        # so slightly discount it
        per_item = self.elapsed / self.completed
        return int(per_item * remaining * 0.8)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "project_id": self.project_id,
            "step": self.step,
            "status": self.status,
            "total": self.total,
            "completed": self.completed,
            "progress_pct": self.progress_pct,
            "elapsed": round(self.elapsed, 1),
            "eta_seconds": self.eta_seconds,
            "error": self.error,
            "item_errors": list(self.item_errors),
        }


# Global task store: project_id:step -> TaskState
_tasks: dict[str, TaskState] = {}
# asyncio Task references to allow cancellation
_async_tasks: dict[str, asyncio.Task] = {}


def _key(project_id: str, step: str) -> str:
    return f"{project_id}:{step}"


def start_task(project_id: str, step: str, total: int, estimated_total_seconds: float = 0.0) -> TaskState:
    """Register a new background task.

    v1.1.49: estimated_total_seconds — 단일 작업(total=1)의 시간 기반 진행률
    추정에 사용. 예: 대본 생성 ~60s, 렌더링 ~120s.
    """
    key = _key(project_id, step)
    # Cancel existing task if running
    cancel_task(project_id, step)
    state = TaskState(
        task_id=key,
        project_id=project_id,
        step=step,
        total=total,
        started_at=time.time(),
        estimated_total_seconds=estimated_total_seconds,
    )
    _tasks[key] = state
    return state


def get_task(project_id: str, step: str) -> Optional[TaskState]:
    """Get current task state"""
    return _tasks.get(_key(project_id, step))


def update_task(project_id: str, step: str, completed: int, result: dict = None):
    """Update progress of a running task"""
    state = _tasks.get(_key(project_id, step))
    if state and state.status == "running":
        prev_completed = state.completed
        state.completed = completed
        # Record timestamp for each newly completed item
        if completed > prev_completed:
            for _ in range(completed - prev_completed):
                state.record_item_done()
        if result:
            state.results.append(result)


def complete_task(project_id: str, step: str):
    """Mark task as completed"""
    state = _tasks.get(_key(project_id, step))
    if state:
        if state.status == "cancelled":
            return
        state.status = "completed"
        state.completed = state.total
        state.finished_at = time.time()


def fail_task(project_id: str, step: str, error: str):
    """Mark task as failed"""
    state = _tasks.get(_key(project_id, step))
    if state:
        if state.status == "cancelled":
            return
        state.status = "failed"
        state.error = error or "Task failed"
        state.finished_at = time.time()


def record_item_error(project_id: str, step: str, cut_number: int, error: str):
    """Record a per-item failure (e.g. one cut failed out of N).
    Keeps the task running; does not affect overall status until fail_task is called.
    Error message is truncated to 1200 chars to keep API responses small.
    """
    state = _tasks.get(_key(project_id, step))
    if state is None:
        return
    msg = (error or "")[:1200]
    state.item_errors.append({"cut_number": cut_number, "error": msg})


def cancel_task(project_id: str, step: str):
    """Cancel a running task"""
    key = _key(project_id, step)
    state = _tasks.get(key)
    if state and state.status == "running":
        state.status = "cancelled"
        state.finished_at = time.time()
    # Cancel the asyncio task
    atask = _async_tasks.pop(key, None)
    if atask and not atask.done():
        atask.cancel()


def register_async_task(project_id: str, step: str, task: asyncio.Task):
    """Store asyncio.Task reference for cancellation"""
    _async_tasks[_key(project_id, step)] = task


def is_running(project_id: str, step: str) -> bool:
    """Check if a task is currently running.

    v1.1.41: Previously auto-expired at 30 minutes, which silently killed long
    AI video jobs mid-flight (120컷 × 30~60s/컷 = 1~2 시간 소요가 일반적).
    사용자 요청: "한번 시작하면 페이지 변경 되도 계속 진행 되게 해, 중지 누를때까진".

    변경:
    - 하드 실링을 6 시간으로 상향. 현실적 롱폼 영상 최대 길이(120컷 × 2분) 가
      약 4 시간이라, 6 시간이면 비정상적으로 오래 잡힌 경우만 잘라냄.
    - 기저 `asyncio.Task` 가 이미 종료됐는데 (프로세스 재시작, 예상치 못한
      크래시 등) state 가 갱신 안 된 dangling running 상태를 먼저 감지해
      리컨사일. 이건 6 시간 기다릴 필요 없이 즉시 해소됨.
    """
    key = _key(project_id, step)
    state = _tasks.get(key)
    if state is None or state.status != "running":
        return False
    # Reconcile against the underlying asyncio.Task:
    # If it's actually finished (e.g. crashed without calling fail_task, or
    # the event loop got hot-reloaded), treat the state as stale and fail it.
    atask = _async_tasks.get(key)
    if atask is not None and atask.done():
        state.status = "failed"
        state.error = "Task ended without status update (crash or reload)"
        state.finished_at = time.time()
        _async_tasks.pop(key, None)
        return False
    # Hard ceiling safety net: 6 hours. Only kicks in for genuinely stuck tasks.
    # Normal long video generation (1~4h) runs well within this window.
    elapsed = time.time() - state.started_at
    if elapsed > 6 * 3600:
        state.status = "failed"
        state.error = "Task timed out (exceeded 6 hours)"
        state.finished_at = time.time()
        if atask is not None and not atask.done():
            atask.cancel()
        _async_tasks.pop(key, None)
        return False
    return True
