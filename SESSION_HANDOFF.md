# LongTube Session Handoff

Saved at: 2026-05-08 00:03 +09:00
Workspace: `C:\Users\Ai_M9\Desktop\longtube`

## 최상위 절대 지킴

- 채널 증가, 채널 수, 프리셋 수와 무관하게 대본 생성 프롬프트 소스는 단 1개 파일만 사용합니다.
- 전역 대본 생성은 반드시 `backend/app/services/llm/base.py`만 사용합니다.
- 추가 대본 생성 프롬프트 파일, 채널별 대본 생성 프롬프트, 프리셋별 대본 생성 프롬프트를 절대 만들지 않습니다.
- 대본 생성 기본 프롬프트 수정은 `backend/app/services/llm/base.py` 안에서만 허용합니다.

## Start Rule

- 새 세션 시작 순서:
  1. `docs/SESSION_PROTOCOL.md`
  2. `SESSION_HANDOFF.md`
  3. `SESSION_QA_V3_2026-05-08.md` 전체 원문
  4. `CONTEXT.md`
  5. 현재 요청과 직접 관련된 코드 파일
- `SESSION_QA_V3_2026-05-08.md`는 요약으로 대체하지 않고 처음부터 끝까지 읽습니다.
- 날짜별 `SESSION_HANDOFF_YYYY-MM-DD.md` 파일은 보관본입니다.
- `docs/ARCHITECTURE.md`는 초기 설계 기록이며 현재 구현 판단 기준이 아닙니다.

## V3 Naming

- 앞으로의 버전 명명은 사용자 지시대로 V3를 사용합니다.
- V3 작업대/스튜디오 문답 원문 파일:
  - `SESSION_QA_V3_2026-05-08.md`

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

### 2026-05-07 — ComfyUI 로컬모델 v1 프롬프트 분리/정리

- 대상:
  - `backend/app/services/image/comfyui_service.py`
  - `backend/app/services/image/asset_guard.py`
  - `backend/app/routers/image.py`
  - `backend/app/tasks/pipeline_tasks.py`
  - `backend/tests/test_oneclick_stability.py`
- 핵심 문제:
  - `CH3 딸깍폼-일본역사` 스튜디오 컷 1 미소국 프롬프트가 2020년대 현대 일본 식탁인데, ComfyUI 결과가 성/바다/번개/외부 풍경으로 이탈함.
  - 원인은 양성 프롬프트에 금지형 문장과 장면 단어가 들어가고, `SDXL LIGHTNING` 같은 모델/스타일 문구가 실제 번개 토큰으로 작동한 점.
- 최종 반영:
  - 로컬모델 v1 양성 마스터 프롬프트에서 `Do not`, `ABSOLUTELY NO`, `SDXL LIGHTNING`, 텍스트/지도 금지 문장 제거.
  - 로컬모델 v1 양성 프롬프트는 보여줄 장면/스타일만 남김.
  - 공통 양성 금지 지시(`HARD HISTORICAL...`, `ABSOLUTELY NO TEXT/MAPS`, `BOOK RENDERING LOCK`)는 로컬 v1 최종 양성 입력 전에 제거.
  - 현대 일본 주방/식탁/미소국 컷은 양성에 `Present-day modern setting`, `Ordinary modern Japanese home kitchen`, `The main subject is a bowl of miso soup` 보강.
  - 네거티브에는 장면 단어 자동 삽입을 하지 않음. `lightning`, `storm`, `temple`, `castle`, `ocean`, `road`, `building`, `fire`, `boat`, `mountain` 등을 네거티브에 자동 추가하지 않음.
  - 네거티브는 기본 품질/텍스트/지도/워터마크/로고 중심만 유지.
  - `.prompt.json`에 실제 ComfyUI 입력값 `comfyui_positive_prompt`, `comfyui_negative_prompt` 저장.
- 직접 검증:
  - 미소국 테스트 프롬프트로 `ComfyUIImageService("comfyui-dreamshaper-xl-longtube")` 직접 호출.
  - 생성 테스트 파일:
    - `C:\Users\Ai_M9\Desktop\longsult\_system\diagnostics\miso_local_v1_test.png`
    - `C:\Users\Ai_M9\Desktop\longsult\_system\diagnostics\miso_local_v1_test_after_fix.png`
  - 최종 조립 검증:
    - 양성에 `lightning/storm/temple/castle/ocean/fire/armor/battle/map/text/ABSOLUTELY NO/Do not` 없음.
    - 네거티브에 `lightning/storm/temple/castle/ocean/road/building/fire/boat/mountain` 없음.
    - 네거티브에 `map/text/watermark/logo` 있음.
- 검증 명령:
  - `python -m py_compile backend\app\services\image\comfyui_service.py`
  - `python -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests -q`
- 백엔드:
  - `GET http://127.0.0.1:8000/api/health` 정상.
  - 응답: `status=ok`, `version=1.2.29`, `comfyui_base_url=http://127.0.0.1:8188`
- 관련 커밋:
  - `47b8c58 fix: prioritize cut prompt for local v1 images`
  - `1b9d838 fix: split local v1 positive and negative prompts`
  - `ab4e710 fix: keep scene terms out of local v1 negatives`

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
