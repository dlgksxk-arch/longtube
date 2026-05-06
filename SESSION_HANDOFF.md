# LongTube Session Handoff

Saved at: 2026-05-06 18:12 +09:00
Workspace: `C:\Users\Ai_M9\Desktop\longtube`

## Start Rule

- 새 세션 시작 순서:
  1. `docs/SESSION_PROTOCOL.md`
  2. `SESSION_HANDOFF.md`
  3. `CONTEXT.md`
  4. 현재 요청과 직접 관련된 코드 파일
- 날짜별 `SESSION_HANDOFF_YYYY-MM-DD.md` 파일은 보관본입니다.
- `docs/ARCHITECTURE.md`는 초기 설계 기록이며 현재 구현 판단 기준이 아닙니다.

## User Rules

- 추론하지 않습니다. 실제 파일, 로그, DB, API 응답 기준으로 답합니다.
- 추측성 변경을 하지 않습니다. 정확히 필요한 것만 합니다.
- 설명은 짧게 합니다.
- 한국어 존댓말, 자비스 말투를 사용합니다.
- 생성 결과물에 문제가 있으면 결과물을 직접 수정하지 않습니다. 로직을 고쳐 다음 생성물에 적용합니다.

## Current Verified Runtime State

- Backend health checked on 2026-05-06:
  - `GET http://127.0.0.1:8000/api/health`
  - response: `status=ok`, `version=1.2.29`, `comfyui_base_url=http://127.0.0.1:8188`
- Frontend is listening on `0.0.0.0:3000`.
- Backend is listening on `0.0.0.0:8000`.
- ComfyUI is listening on `0.0.0.0:8188`.
- `GET /api/oneclick/safety` without login cookie returns `401`. This matches the current auth middleware in `backend/app/main.py`.

## Current Source Of Truth

- Backend version:
  - `backend/app/main.py`: `1.2.29`
  - `/api/health`: `1.2.29`
- Frontend version:
  - `frontend/package.json`: `1.2.29`
  - `frontend/src/lib/version.ts`: `1.2.29`
- Actual workspace path:
  - `C:\Users\Ai_M9\Desktop\longtube`
- Current data root in code:
  - default `data/outputs`
  - `CHANNELS_ROOT = DATA_DIR / "channels"`
  - `SYSTEM_PROJECTS_ROOT = DATA_DIR / "_system" / "projects"`
  - archive root default `D:\long_result`

## Core Code Map

- App entry/auth/router mount:
  - `backend/app/main.py`
- Config/path resolution:
  - `backend/app/config.py`
- Pipeline steps:
  - `backend/app/tasks/pipeline_tasks.py`
- One-click queue/task runner:
  - `backend/app/services/oneclick_service.py`
  - `backend/app/routers/oneclick.py`
- Shorts selection/rendering:
  - `backend/app/services/shorts_service.py`
  - `backend/app/routers/subtitle.py`
- Script prompt rules:
  - `backend/app/services/llm/base.py`
- Image prompt rules:
  - `backend/app/services/image/prompt_builder.py`
- Live status UI:
  - `frontend/src/app/oneclick/live/page.tsx`
- One-click queue UI:
  - `frontend/src/app/oneclick/page.tsx`
- Frontend API client:
  - `frontend/src/lib/api.ts`

## Current Pipeline Facts

- One-click backend flow in `oneclick_service.py`:
  - Step 2: script
  - Step 3 and Step 4: voice + image run in parallel
  - Step 5: video
  - Step 6 render and Step 7 upload are handled after the sync pipeline path
- Shorts constants currently in `shorts_service.py`:
  - `SHORTS_CUT_COUNT = 12`
  - `SHORTS_EXCLUDE_EDGE_CUTS = 5`
  - `SHORTS_PLAYBACK_SPEED = 1.1`
  - canvas `1080x1920`
- TTS duration constants currently in `config.py`:
  - `TTS_TARGET_DURATION = 4.5`
  - `TTS_MIN_DURATION = 4.3`
  - `TTS_MAX_DURATION = 4.8`

## Recent Verified Fix Areas

- CH3 actual YouTube channel name verified by API in prior work:
  - `闇解き日本史`
  - channel id: `UCSmk_wHxkZLf23gJN0c5NVQ`
- Wrong CH3 fallback name `Whisper Hour` was fixed in:
  - `backend/app/services/shorts_service.py`
  - `backend/app/routers/subtitle.py`
- Japanese/non-English shorts fallback safeguards were added in `shorts_service.py`.
- Shorts image reuse issue was fixed in `backend/app/tasks/pipeline_tasks.py`:
  - deterministic shorts-selected cuts disable grouped image reuse.
  - stale cut videos regenerate when the image is newer than the video.

## Worktree Notes

- The worktree contained many stabilization changes from earlier sessions.
- Generated/runtime artifacts are ignored by `.gitignore`:
  - `data/`
  - `*.db`
  - `token*.json`
  - `client_secret*.json`
  - `backend/logs/`
  - `*.log`
  - `*.tsbuildinfo`
  - `tmp/`, `tmp_*`
- Do not commit OAuth/token/runtime output files.
- Do not use `git reset --hard` or broad checkout to discard work.

## Next Checks Before More Work

1. `git status --short`
2. `Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health`
3. If checking authenticated endpoints, use browser/session context or login first.
4. For UI truth, verify in browser rather than assuming from code.
