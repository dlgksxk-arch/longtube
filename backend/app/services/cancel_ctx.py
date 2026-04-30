"""v1.2.29 — 공용 thread-local cancel 컨텍스트 ("유령 API 호출" 차단).

v1.2.29 에서 추가된 프로세스 전역 halt 집합(`_HALT_KEYS`) 은 redis 장애 또는
is_cancelled() 내부 예외 묵살로 cancel 신호가 사라지는 사고를 막는 최후 안전선.
긴급정지를 눌렀는데 ComfyUI 가 6 컷 이상 더 생성한 사고의 근본 원인이 redis
경로였기 때문에, 이제는 프로세스 메모리 set() 에도 마킹해 어떤 경우에도 halt
가 무효화되지 않도록 한다.

원리
----
`cancel_task` 는 Python 레벨의 `asyncio.Task.cancel()` 과 redis
`pipeline:cancel:<pid>` 플래그 설정만 할 수 있다. 그런데 실제 작업은
`asyncio.to_thread(_run_sync_pipeline, ...)` 로 떨어진 OS 워커 스레드 안에서
돌고 있어서, 그 스레드는 파이썬이 강제 종료시킬 수 없다. 그 워커 스레드가
`run_async(service.generate(...))` 로 새 이벤트 루프를 만들어 async 서비스를
호출하는데, 서비스 내부의 submit/poll 루프는 cancel 신호를 전혀 보지 못한다.

해결
----
워커 스레드가 스텝(예: `_step_image`) 진입 시 `set_cancel_key(project_id)` 로
"이 스레드의 작업 키" 를 세팅해 두면, 각 서비스가 HTTP 를 쏘기 직전
`raise_if_cancelled()` 로 플래그를 확인하고 `OperationCancelled` 로 이탈한다.
플래그 소스는 3 단계:
  1) 프로세스 전역 halt 집합 `_HALT_KEYS` (redis 와 무관, 가장 안전)
  2) redis `pipeline:cancel:<key>`
  3) in-memory `_progress_mem` fallback

`threading.local()` 을 쓰는 이유
-------------------------------
`asyncio.to_thread` 의 각 워커 스레드는 별개 OS 스레드라 thread-local 이
분리된다. 같은 스레드 안에서 `run_async` 가 새 이벤트 루프를 만들어도 OS 스레드
자체는 바뀌지 않으므로 값이 유지된다.
"""
from __future__ import annotations

import threading
from typing import Optional


class OperationCancelled(RuntimeError):
    """사용자가 cancel 을 눌러 파이프라인이 중지된 상태에서 외부 API 호출을
    차단했을 때 올리는 예외.
    """


# 현재 워커 스레드가 어느 프로젝트/작업을 처리 중인지 기록하는 thread-local.
# 값은 pipeline:cancel:<key> 의 <key> 와 동일. None 이면 "관여 없음".
_CTX = threading.local()


# v1.2.29: 프로세스 전역 halt 집합 — redis 와 무관한 최후의 안전선.
# 긴급정지를 눌렀는데 ComfyUI 가 6 컷 이상 더 생성되는 사고 대응.
_HALT_KEYS: set[str] = set()
_HALT_LOCK = threading.Lock()


def mark_halted(key):
    """프로세스 전역 halt 집합에 `key` 추가.
    emergency_stop_all / cancel_task / delete_task 에서 호출.
    """
    if not key:
        return
    with _HALT_LOCK:
        _HALT_KEYS.add(str(key))


def unmark_halted(key):
    """halt 집합에서 제거. 새 run 시작 시점에만 호출."""
    if not key:
        return
    with _HALT_LOCK:
        _HALT_KEYS.discard(str(key))


def is_halted(key):
    """halt 집합에 들어있으면 True (redis 유무와 무관)."""
    if not key:
        return False
    with _HALT_LOCK:
        return str(key) in _HALT_KEYS


def clear_all_halted():
    """halt 집합 전체 비움. 테스트/초기화 용."""
    with _HALT_LOCK:
        _HALT_KEYS.clear()


def set_cancel_key(key):
    """현재 스레드의 cancel 키를 세팅 (None 이면 해제).

    스텝 진입 시:  set_cancel_key(project_id)
    스텝 종료 시:  set_cancel_key(None)
    """
    _CTX.key = key


def get_cancel_key():
    """현재 스레드에 세팅돼 있는 cancel 키. 없으면 None."""
    return getattr(_CTX, "key", None)


def is_cancelled():
    """현재 스레드의 cancel 키에 해당하는 cancel 플래그가 세팅돼 있으면 True.

    v1.2.29: 3 단계 OR 로 확인.
      1) 프로세스 halt 집합 `_HALT_KEYS` (예외 불가능 경로)
      2) redis `pipeline:cancel:<key>`
      3) `_progress_mem` fallback (pipeline_tasks._redis_get 안에서)
    """
    key = get_cancel_key()
    if not key:
        return False
    # 1) 프로세스 halt 집합 — redis 와 무관, 예외 발생 불가.
    if is_halted(key):
        return True
    # 2+3) redis 또는 _progress_mem
    try:
        from app.tasks.pipeline_tasks import _redis_get
        return bool(_redis_get("pipeline:cancel:" + str(key)))
    except Exception:
        return False


def raise_if_cancelled(where=""):
    """`is_cancelled()` 이면 즉시 `OperationCancelled` 로 이탈."""
    if is_cancelled():
        key = get_cancel_key()
        raise OperationCancelled(
            "[cancelled] pipeline:cancel:" + str(key) + " 세팅됨 — "
            + (where or "api") + " 차단"
        )
