# 2026-07-27 OpenAI 전면 중지 · CH3 EP07 재제작/비용 감사 인수인계

저장 시각: 2026-07-27 12:41 KST

## 새 세션 시작 순서

1. `AGENTS.md`
2. `docs/SESSION_PROTOCOL.md`
3. `SESSION_HANDOFF.md`
4. 이 문서 전체
5. `docs/handoffs/SESSION_QA_V3_2026-05-08.md` 전체
6. `CONTEXT.md`
7. 아래 작업 ID·DB·API·프로세스·파일을 실제로 다시 확인

추측으로 생성·재개·업로드·모델 변경을 실행하지 않는다.

## 최우선 사용자 지시

- LongTube에서 OpenAI API 및 OpenAI 유료 모델 사용을 전면 중지한다.
- 금지 범위는 대본/스토리 생성, 타이밍 재작성, 이미지 생성, 비전 QA, 썸네일, TTS, 다국어 자막/YouTube 메타데이터 번역, 댓글 기능, 비용 동기화와 자동 폴백을 포함한다.
- 썸네일은 전부 자체 로컬 생성만 사용한다.
- 사용자가 명시적으로 다시 허가하기 전에는 OpenAI 크레딧을 단 한 번도 사용하지 않는다.
- OpenAI가 설정된 경우 다른 모델로 몰래 폴백하지 않는다. 즉시 실패시킨다.
- 대본 대체 모델은 사용자가 지정하지 않았다. Anthropic 등으로 임의 변경하지 않는다.
- 기존 생성 대본이 있으면 반드시 그 대본을 재사용한다. “다시 만들어서 올려”를 대본 전면 재생성으로 임의 해석하지 않는다.
- 중요 기능/모델 변경은 반드시 사용자 허락 후 실행한다.
- 생성 결과물에 문제가 있으면 결과물을 직접 고치지 않고 원인 로직을 수정한 뒤 재생성한다.
- 편당 전체 제작 시간은 3~4시간 안에 끝내도록 처음부터 계획한다.
- 제목·썸네일 문구·숏츠 제목·히어로 문구는 반복하지 않고 강한 클릭 유도형으로 다양하게 구성한다.

영구 메모에도 아래 파일로 저장했다.

`C:\Users\Ai_M9\.codex\memories\extensions\ad_hoc\notes\20260727-122616-longtube-openai-full-stop.md`

## 현재 런타임

- Backend PID: `279228`
- Backend 시작: 2026-07-27 12:36:59 KST
- 명령: `python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Health: `{"status":"ok","version":"V3.2","comfyui_base_url":"http://127.0.0.1:8188"}`
- OpenAI API 상태: `not_configured`
- 실행 중/대기/준비 상태 OneClick 작업: `0건`

확인 명령:

```powershell
python .codex_tmp\oneclick_auth_call.py GET /api/health
python .codex_tmp\oneclick_auth_call.py GET /api/api-status/status
```

`/api/api-status/status`는 현재 OpenAI 키를 노출하지 않고 OpenAI 네트워크 요청도 하지 않는다.

## 현재 제작·업로드 상태

### CH1 EP05

- Task: `1411187c`
- Project: `V3_CH1_EP5_260726151249b253b0`
- Result: `D:\long_result\CH1\백제사\EP.5.260726151249b253b0`
- 상태: `completed`
- Step 2~7: 전부 `completed`
- 이미지: 150/150
- 승인 커서: 150
- 본편: `https://youtube.com/watch?v=qXIQkPx54r8`
- Shorts artifact:
  - `GuEvZzRRLwg`
  - `QIC-cDgQ5kI`
  - `040mGuavcMY`
  - `LCHIps7N9VE`
- 로컬 `shorts_uploads.json`에서 1~3은 `processing_verified=false`, 4만 `true`다. 현재 공개/HD 상태를 주장하려면 YouTube API로 다시 검증한다.

### CH2 EP06

- Task: `2799640b`
- Project: `V3_CH2_EP6_2607261531487be407`
- Result: `D:\long_result\CH2\Scartography\EP.6.2607261531487be407`
- 상태: `completed`
- Step 2~7: 전부 `completed`
- 이미지: 150/150
- 승인 커서: 150
- 본편: `https://youtube.com/watch?v=DtQ7V3IsKm8`
- Shorts artifact:
  - `qccsxY23PLU`
  - `9NAYCJYIkXQ`
  - `N0pbmLpauxQ`
  - `b3F6fmQhqjM`
- 로컬 `shorts_uploads.json` 네 건 모두 `processing_verified=false`다. 현재 공개/HD 상태를 주장하려면 YouTube API로 다시 검증한다.

### CH3 EP07 기존 복구본

- Task: `10883b35`
- Project: `V3_CH3_EP7_2607220507162703a5`
- Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.2607220507162703a5`
- 상태: `completed`
- 본편: `https://youtube.com/watch?v=e82J2CUe58E`
- 기존 영상은 새 EP07 제작 전까지 공개 유지한다고 처리됐으며, 현재도 DB에 완료 상태로 남아 있다.
- 새 EP07과 중복 공개 여부를 실제 YouTube API로 확인한 뒤, 기존 영상을 내리거나 비공개로 바꾸려면 반드시 사용자 지시를 받는다.

### CH3 EP07 신규 재제작본

- Task: `394cb599`
- Project: `V3_CH3_EP7_260726223425008607`
- Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.260726223425008607`
- Episode code: `CH3_C1_EP007_REMAKE_20260726`
- 상태: `completed`
- Step 2~7: 전부 `completed`
- 이미지: 150/150
- 승인 커서: 150
- 본편: `https://youtube.com/watch?v=2VxKK2vano8`
- Shorts:
  - `YPBacdcHbAA`
  - `ccJ79SEJboE`
  - `XIUihDW5vVE`
  - `hYCqtKe1HwU`
- 네 Shorts는 저장된 YouTube API 검증상 모두:
  - `privacy_status=public`
  - `upload_status=processed`
  - `processing_status=succeeded`
  - `definition=hd`
  - `channel_id=UCSmk_wHxkZLf23gJN0c5NVQ`
- 마지막 저장 검증 시각: `2026-07-26T20:31:48Z`

### CH3 EP10

- Task: `6c35cd5d`
- Project: `V3_CH3_EP10_260726161148299480`
- Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.10.260726161148299480`
- Task 상태: `cancelled`
- DB Project 상태: `paused`
- Step 2·3 완료
- 이미지: 60/150
- 승인 커서: 60
- 오류: `사용자 취소`
- 산출물은 보존돼 있다.
- 자동 재개하지 않는다. 사용자가 EP10 재개를 명시하면 OpenAI 차단 상태와 기존 대본 재사용 여부를 먼저 확인한다.

작업 조회:

```powershell
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/1411187c
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/2799640b
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/10883b35
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/394cb599
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/6c35cd5d
```

## CH3 EP07 대본 재생성 사고

기존 대본은 실제로 존재했다.

1. 최신 기존 대본
   - `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.2607220507162703a5\script.json`
   - 크기: `451832`
   - SHA256: `18e2635885b648b2f49548e368c483824c560d2cf597936223ce155852935c43`
2. 5월 기존 대본
   - `C:\Users\Ai_M9\Desktop\longsult\_system\projects\V3_CH3_EP7_딸깍_CH3_EP7_260506-1\script.json`
   - 크기: `187338`
   - SHA256: `7bddc8950ec1b6a5ea41505bd006d0c7aac4140693a0810c7ffd4b86d9c20ded`
3. 잘못 새로 생성한 대본
   - `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.260726223425008607\script.json`
   - 크기: `488112`
   - SHA256: `c47086f360651b570ae82a3b392240c3633c1fd8541f71dfc392a8d7701139d4`

실제 잘못된 실행 순서:

1. `/api/oneclick/prepare`가 기존 `V3_CH3_EP7_딸깍_CH3_EP7_260506-1` 프로젝트를 정상 복구했다.
2. 이 작업은 Step 2·3이 완료된 기존 120컷 프로젝트였다.
3. 이를 “5월의 오래된 프로젝트”라고 임의 판단해 실행하지 않고 취소했다.
4. 고유 episode code `CH3_C1_EP007_REMAKE_20260726`를 넣어 모든 단계가 pending인 새 프로젝트를 강제로 만들었다.
5. “7편 다시 만들어서 올려”를 기존 대본 기반 영상 재제작이 아니라 대본까지 전면 재생성하라는 뜻으로 잘못 해석했다.
6. 이미지 프롬프트 위치 오염 문제를 발견한 뒤 Step 4만 다시 해야 했지만 task `394cb599`를 Step 2부터 reset했다.
7. 그 결과 전체 대본이 두 번 생성됐다.

정정 원칙:

- 기존 대본이 있으면 해시·경로·프로젝트를 먼저 확인하고 그대로 재사용한다.
- 영상/이미지 문제는 Step 4부터 재개한다.
- Step 2 reset은 사용자가 대본 재생성을 명시적으로 허가한 경우에만 실행한다.

## OpenAI 비용 감사

근거: `C:\Users\Ai_M9\Desktop\longsult\api_spend_log.jsonl`

2026-07-26 00:00Z 이후 로컬 OpenAI 원장:

- 총액: `$6.385672`
- 총 레코드: `171`
- CH3 신규 EP07 전체 대본 생성 2회: `$2.869410`
  - 1차: `$1.456305`
  - 2차: `$1.413105`
- 자동 타이밍 재작성 153회: `$3.398935`
  - 1차 대본 직후 113회: `$2.604395`
  - 2차 대본 직후 40회: `$0.794540`
- CH3 신규 EP07 썸네일 2회: `$0.040000`
- 신규 EP07 관련 합계: `$6.308345`
- 전체 OpenAI 지출의 약 98.8%
- 최신 OpenAI 원장 기록:
  - `2026-07-26T15:54:26Z`
  - `openai-image-1`
  - 신규 EP07 썸네일 `$0.02`
- OpenAI 전면 차단 적용 이후 신규 원장 기록은 없다.

공식 OpenAI Usage API는 현재 키에 `api.usage.read` 권한이 없어 확인하지 못했다. 위 수치는 로컬 원장 기준이다.

차단 검증 중 기존 `/api/api-status/status`가 `.env` 키를 직접 읽어 OpenAI `/v1/models`를 한 번 조회했다. 생성/과금 요청은 아니지만 사용자 지시와 맞지 않아 해당 경로도 차단했다. 현재 같은 API 응답은 OpenAI `not_configured`다.

## OpenAI 전면 중지 코드 변경

이번 지시로 추가한 핵심 로직:

### 중앙 차단

`backend/app/config.py`

- `OPENAI_API_DISABLED = True`
- `OPENAI_API_KEY`를 빈 문자열로 강제
- `get_runtime_api_key()`가 `OPENAI_API_KEY`와 `OPENAI_ADMIN_KEY`를 반환하지 않음
- `require_openai_api_enabled()` 추가

### 호출 전 하드 실패

- `backend/app/services/llm/gpt_service.py`
- `backend/app/services/image/openai_image_service.py`
- `backend/app/services/tts/openai_tts_service.py`
- `backend/app/services/youtube_localization_service.py`
- `backend/app/services/multilingual_caption_service.py`
- `backend/app/services/openai_cost_sync.py`

OpenAI 호출 전 `require_openai_api_enabled()`가 즉시 예외를 발생시킨다.

### 키 저장/상태 확인 경로

- `backend/app/routers/api_keys.py`
  - UI에서 OpenAI 키를 저장해도 실행 중 config에 다시 활성화하지 않음
- `backend/app/routers/api_status.py`
  - `.env`의 OpenAI 키를 직접 읽지 않음
  - OpenAI 상태 확인 네트워크 요청도 실행하지 않음

### 썸네일 로컬 강제

`backend/app/services/image/factory.py`

- `DEFAULT_THUMBNAIL_MODEL = "comfyui-z-image-turbo"`
- `resolve_thumbnail_model()` 추가
- OpenAI/Nano Banana 등 비로컬 썸네일 모델은 `comfyui-z-image-turbo`로 강제
- 이미 ComfyUI 로컬 모델이면 해당 모델을 유지

실제 생성/비용 예상/수동 재생성 경로가 모두 같은 로컬 resolver를 사용하도록 아래 파일을 연결했다.

- `backend/app/services/thumbnail_service.py`
- `backend/app/tasks/pipeline_tasks.py`
- `backend/app/routers/youtube.py`
- `backend/app/routers/oneclick.py`
- `backend/app/services/oneclick_service.py`
- `backend/app/services/scheduler_service.py`
- `backend/app/services/estimation_service.py`

### 테스트

- 신규: `backend/tests/test_openai_usage_disabled.py`
- 이 파일과 `backend/app/services/youtube_localization_service.py`는 현재 Git 미추적 상태이므로 삭제하거나 정리하지 않는다.

## Studio 프리셋 DB 변경

DB: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.db`

백업:

`C:\Users\Ai_M9\Desktop\longtube\data\backups\longtube.db.20260727-122616-openai-stop.bak`

썸네일 모델 변경:

- CH1 `f60d6b0b`: `openai-image-1` → `comfyui-z-image-turbo`
- CH2 `e6619f7e`: `openai-image-1` → `comfyui-z-image-turbo`
- CH3 `7d8b63e5`: `openai-image-1` → `comfyui-z-image-turbo`
- CH4 `83cca89d`: `openai-image-1` → `comfyui-flux2-klein-4b`

네 프리셋의 `story_model`·`script_model`은 아직 `gpt-5.5`다.

- 다른 LLM으로 임의 변경하지 않았다.
- 새 대본/스토리 생성이 실행되면 중앙 OpenAI 차단으로 즉시 실패한다.
- 기존 대본이 있는 제작은 Step 2를 재실행하지 않고 기존 대본을 사용한다.
- 정말 새 대본이 필요하면 사용자가 비-OpenAI 대본 모델을 먼저 지정해야 한다.

## 검증 완료

- 관련 Python 파일 `py_compile` 통과
- `backend/tests/test_openai_usage_disabled.py`: `2 passed`
- `backend/tests/test_thumbnail_text_space_normalization.py`: `3 passed`
- 대상 파일 `git diff --check` 통과
- 백엔드 재시작 완료
- `/api/health`: 정상
- `/api/api-status/status`: OpenAI `not_configured`
- 실행 중/대기/준비 OneClick 작업: `0건`
- 네 Studio 프리셋의 썸네일 모델이 로컬 ComfyUI로 저장된 것을 DB에서 확인

## 다음 세션 행동 순서

1. 이 문서와 필수 원문을 먼저 전부 읽는다.
2. OpenAI `not_configured`와 `OPENAI_API_DISABLED=True`를 확인한다.
3. 실행 중 OneClick 작업이 0건인지 확인한다.
4. 사용자의 다음 제작 지시를 기다린다.
5. 기존 대본이 있는 에피소드는 대본 경로·해시·프로젝트 ID를 확인한 뒤 Step 2를 건너뛴다.
6. 새 대본이 정말 필요하면 비-OpenAI 모델을 사용자에게 지정받기 전에는 시작하지 않는다.
7. 썸네일은 채널 프리셋의 ComfyUI 로컬 모델만 사용한다.
8. CH3 EP10 task `6c35cd5d`는 자동 재개하지 않는다.
9. 기존 CH3 EP07 `e82J2CUe58E`와 신규 `2VxKK2vano8`의 중복 공개 처리는 사용자 지시 없이 변경하지 않는다.
10. 업로드 완료를 주장할 때는 artifact/DB뿐 아니라 YouTube API 또는 oEmbed로 영상 존재·채널·공개·처리·HD를 다시 검증한다.

## Dirty worktree / 보안 경계

- 저장소는 이번 세션 이전부터 대규모 dirty 상태다.
- `git reset --hard`, `git checkout --`, `git clean`, 광범위 stage/commit 금지.
- 이번 OpenAI 차단 파일에도 이전 작업 변경이 함께 들어 있으므로 파일 전체를 되돌리지 않는다.
- `backend/app/config.py`, `backend/app/services/image/factory.py`에는 이전 사용자 변경도 함께 있다.
- `data/longtube.db`, 백업 DB, 토큰/OAuth, 로그, 생성물은 커밋하지 않는다.
- Git 미추적 파일을 임의 삭제하지 않는다.
- 이번 인수인계 저장은 커밋·스테이징하지 않았다.
