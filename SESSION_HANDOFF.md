# 새 세션 인계 메모 - 2026-05-09 21:50 KST

## 작업 원칙

- 추측으로 수정하지 말 것. 실제 파일, 실제 API, 실제 브라우저 상태 기준으로만 판단.
- 생성 결과물 직접 수정 금지. 결과물 문제는 로직 수정으로 다음 생성물에 반영.
- 실행 중 작업이 있으면 백엔드/ComfyUI 재시작은 사용자 허락 없이 하지 말 것.
- 현재 워킹트리에 이전 세션 변경이 다수 섞여 있음. 이번 큐 정리와 무관한 변경은 되돌리지 말 것.

## 이번 세션 핵심 목표

사용자가 지적한 문제:
- 전체 작업큐에서 실제 진행 중인 에피소드가 최상단 고정되지 않음.
- 진행 중 작업인데 `1번 지정`, 이동, 삭제 버튼이 살아 있음.
- 완료/실패/취소/중단 상태가 큐에 섞여 다음 실행 순서와 작업대 표시가 틀어짐.
- 프론트가 자체 정렬을 하면서 백엔드 실제 순서와 화면 순서가 어긋날 수 있음.

정한 동작 규칙:
1. 백엔드가 제작큐의 단일 기준이다.
2. 작업큐에는 `pending`과 `running`만 남긴다.
3. `completed / failed / cancelled / paused`는 작업큐에서 제거한다.
4. `running / queued / prepared / uploading`은 작업큐 표시상 `running`으로 취급한다.
5. 실행 중 작업은 항상 최상단에 고정한다.
6. 실행 중 작업의 선택, `1번 지정`, 위/아래 이동, 삭제는 비활성화한다.
7. 실행 순서는 `running` -> 작업대 수동 1번 지정 -> 일반 자동 큐 순서다.
8. 일반 자동 큐는 채널 실행 시간 순, 같은 채널 내부는 EP 오름차순이다.
9. 프론트는 서버가 내려준 큐 순서를 그대로 표시한다.
10. 프론트가 PUT으로 실행 중 항목을 빼거나 바꿔 보내도 백엔드가 실행 중 항목을 보존한다.

## 이번 세션 수정 파일

### `backend/app/services/oneclick_stability_helpers.py`

추가/수정:
- `QUEUE_ACTIVE_STATUSES = {"running", "uploading", "queued", "prepared"}`
- `QUEUE_TERMINAL_STATUSES = {"completed", "failed", "cancelled", "paused"}`
- `normalized_queue_status(value)`
- `is_active_queue_status(value)`
- `is_terminal_queue_status(value)`
- `sort_queue_items_for_execution()`에서 terminal 상태 항목은 실행 정렬 결과에서 제외.
- active 상태는 모두 `running` 그룹으로 정렬.

의도:
- 큐 정렬 기준을 순수 헬퍼에 고정.
- 서비스/테스트가 같은 상태 해석을 쓰게 함.

### `backend/app/services/oneclick_service.py`

주요 추가/수정 지점:
- `_sync_queue_items_from_tasks_for_save(save: bool = True)`
  - 큐 행과 `_TASKS` 상태를 동기화.
  - linked task가 terminal이면 큐에서 제거.
  - linked task가 active이면 큐 행을 `running`으로 보정.
  - 큐 행이 `running`인데 linked task가 없으면 `pending`으로 내리고 task 관련 필드 제거.
  - 실행 중 task가 있는데 큐 행이 없으면 `running` 큐 행을 새로 생성.
  - `_STATE_LOADED` 전이고 실제 큐 파일이 존재하는 경우, task 저장 시 빈 `_QUEUE`가 실제 큐를 덮어쓰지 않도록 early return 추가.

- `_queue_item_identity_values(item)`
  - `id`, `task_id`, `project_id`, `result_dir`, `(channel, episode_number, topic)` 기반 identity 생성.

- `_queue_item_matches_identity(item, identities)`
  - 프론트 PUT 입력에서 실행 중 행 중복/삭제 방지에 사용.

- `_normalize_queue_runtime_state(save: bool = True)`
  - get/save/scheduler/fire 전에 큐를 동기화, dedupe, 정렬.

- `get_queue()`
  - 반환 전에 `_normalize_queue_runtime_state()` 실행.

- `set_queue(new_state)`
  - 기존 active/running 항목을 먼저 캡처.
  - 프론트가 보내온 항목 중 active identity와 겹치는 항목 제거.
  - active 항목을 맨 앞에 합쳐 저장.
  - `last_run_dates`는 기존 값 유지.

- `_fire_queue_for_channel()`
  - 실행 전 runtime normalize.
  - `pending`이 아닌 큐 행은 실행 대상으로 삼지 않음.

- `_queue_loop()`
  - 매 iteration에서 runtime normalize 후 head 확인.

- `run_queue_top_now()`
  - 실행 전 runtime normalize.

- `_dispatch_next_persisted_queue_item()`
  - 즉시 실행 dispatch 전 runtime normalize.

주의:
- 이 파일에는 이번 세션 이전부터 많은 변경이 이미 들어가 있었음.
- 이번 큐 수정 외 기존 V3 재시작 복구/스토리지 관련 변경을 되돌리지 말 것.

### `frontend/src/app/oneclick/live/page.tsx`

수정:
- `sortQueueItemsForWorkbench` import 제거.
- `refreshLiveSnapshot()`에서 `queueState.items || []`를 그대로 사용.
- 자동 tick에서도 `queueState.items || []`를 그대로 사용.
- `moveQueueItem`, `sortQueueItems`, `deleteQueueItem`, `deleteQueueItems`, `promoteQueueItemsToNext`에서 서버 응답 `updated.items || []` 그대로 반영.
- 실행 중 항목은 기존 `isQueueItemLocked()` 기준으로 선택/이동/삭제/1번 지정 비활성화.

의도:
- 프론트 자체 정렬 제거.
- 화면 순서와 백엔드 순서를 일치시킴.

### `frontend/src/app/oneclick/live/queueHelpers.ts`

현재 상태:
- `sortQueueItemsForWorkbench()` 함수는 남아 있으나 `page.tsx`에서는 더 이상 사용하지 않음.
- 필요 시 다음 세션에서 완전 제거 가능. 현재 `tsc` 통과.

### `backend/tests/test_oneclick_stability.py`

추가/수정:
- `test_sort_queue_keeps_running_first_and_removes_terminal_rows`
  - running 최상단, terminal 제거 검증.
- `test_queue_task_sync_prunes_terminal_rows_and_marks_active_as_running`
  - linked terminal 큐 제거, active task 큐 running 보정 검증.
- `test_queue_task_sync_keeps_active_task_visible_when_queue_row_is_missing`
  - active task가 있는데 큐 행이 없어도 running 큐 행이 생성되는지 검증.
- 기존 `test_queue_normalize_preserves_schema_and_rejects_bad_items`
  - 입력 순서 보존 전제를 제거하고 topic 기준 검증으로 수정. 현재 큐는 저장 시 실행 순서로 정렬하는 것이 맞음.

## 실제 큐 파일 확인 결과

기준 파일:
- `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.json`
- `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_tasks.json`

마지막 확인:
- 시각: `2026-05-09 21:50 KST`
- queue_count: `537`
- terminal_count: `0`
- 큐 상태 카운트: `pending 537`

큐 상단 6건:
1. `pending` CH3 EP10 `야요이인은 무엇을 바꿨을까` / note: `작업대에서 실행순 1번 지정`
2. `pending` CH1 EP41 `신생국이 대국을 먼저 공격한 날` / note: `실패/중단 태스크 복구`
3. `pending` CH2 EP22 `The # Symbol: Why Americans Call It 'Pound' and Brits Call It 'Hash'` / note: `실패/중단 태스크 복구`
4. `pending` CH3 EP11 `벼농사는 왜 일본 역사를 갈라놨을까` / note: `엑셀 업로드`
5. `pending` CH4 EP19 `칼링가 전쟁` / note: `실패/중단 태스크 복구`
6. `pending` CH1 EP42 `고구려보다 큰 나라가 만주에 있었다` / note: `실패/중단 태스크 복구`

중요:
- 확인 시점에는 실행 중 task가 없었음.
- 그래서 큐 최상단 running 검증은 실제 화면이 아니라 단위 테스트와 로컬 service normalize 시뮬레이션으로 검증함.

## 검증 완료

성공:
- `python -m py_compile backend/app/services/oneclick_service.py backend/app/services/oneclick_stability_helpers.py`
- `python -m unittest backend.tests.test_oneclick_stability.OneClickQueueStabilityTests`
  - `7 tests OK`
- `npx tsc --noEmit`
  - frontend 통과

전체 안정성 테스트:
- `python -m unittest backend.tests.test_oneclick_stability`
  - 실패 2건 있음.
  - 이번 큐 수정과 직접 관련 없는 기존 기대값 불일치.
  - 실패 1: `test_script_prompt_uses_single_global_base_file`
    - `backend/app/services/llm/base.py`의 프롬프트 문구가 테스트 기대 문구와 다름.
  - 실패 2: `test_default_subtitle_size_is_ten_points_larger`
    - 테스트는 `CUT_SUBTITLE_MARKER_VERSION == 3` 기대, 실제는 `4`.

## 브라우저/API 확인 결과

브라우저로 접속:
- URL: `http://192.168.0.221:3000/oneclick/live`
- 페이지 title: `LongTube`

브라우저 콘솔 실제 오류:
- `GET http://192.168.0.221:8000/api/oneclick/queue Failed to fetch`
- `GET http://192.168.0.221:8000/api/oneclick/running Failed to fetch`
- `GET http://192.168.0.221:8000/api/oneclick/queue/auto-production Failed to fetch`
- 화면에는 `0건 대기`, `실행 상태 로드 실패`가 표시됨.

쉘 직접 확인:
- `Invoke-WebRequest http://192.168.0.221:8000/api/oneclick/queue`
- 결과: `401 Unauthorized`
- `127.0.0.1:8000`도 `401 Unauthorized`

판단 가능한 사실:
- 백엔드는 포트 8000에서 응답함.
- 쉘에서는 인증 없어서 401.
- 브라우저 세션에서는 fetch가 실패로 떨어져 큐 화면 검증을 완료하지 못함.
- 다음 세션에서 브라우저 인증/CORS/쿠키 상태부터 확인 필요.

## 다음 세션 우선순위

1. 브라우저에서 `http://192.168.0.221:3000/oneclick/live` API fetch 실패 원인 확인.
   - 인증 쿠키 누락인지, CORS인지, 프론트 API base 문제인지 실제 콘솔/네트워크 기준으로 확인.
2. 백엔드가 새 코드로 재로드됐는지 확인.
   - 실행 중 작업이 있으면 재시작하지 말 것.
3. 실행 중 task가 실제로 생긴 상태에서 작업큐 모달 확인.
   - running 행이 최상단인지.
   - `진행중` 표시가 붙는지.
   - checkbox, `1번 지정`, 위/아래/삭제 버튼이 disabled인지.
4. API `GET /api/oneclick/queue` 응답에서 terminal status가 섞이지 않는지 확인.
5. `frontend/src/app/oneclick/live/queueHelpers.ts`의 미사용 `sortQueueItemsForWorkbench()` 제거 여부 판단.
6. 전체 안정성 테스트 실패 2건은 큐 수정과 별개. 필요 시 별도 지시 받고 수정.

## 변경 파일 현황

`git status --short` 기준 수정 파일이 많음. 이번 세션에서 직접 건드린 핵심 파일:
- `SESSION_HANDOFF.md`
- `backend/app/services/oneclick_service.py`
- `backend/app/services/oneclick_stability_helpers.py`
- `backend/tests/test_oneclick_stability.py`
- `frontend/src/app/oneclick/live/page.tsx`

주의:
- 워킹트리에는 위 외에도 다수 파일 변경이 이미 존재함.
- 이번 작업과 무관한 파일은 다음 세션에서도 되돌리지 말 것.
