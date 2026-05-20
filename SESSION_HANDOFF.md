# 새 세션 인계 메모 - 2026-05-20 12:27 KST

## 작업 원칙

- `AGENTS.md` 지시 준수: 추측 금지, 실제 파일/로그/응답 기준으로만 판단.
- 생성 결과물 직접 수정 금지. 결과물 문제는 로직 수정으로 다음 생성물에 반영.
- 중요 수정 또는 기능 수정은 사용자 허락 후 진행.
- 기능 저장 커밋 기준: `1ce89fe Save LongTube automation updates`.

## 현재 확인 상태

- 작업트리는 이 메모 작성 직전 clean 상태였다.
- `/api/oneclick/running`, `/api/oneclick/tasks` 직접 호출은 401 Unauthorized였다.
- 실제 작업 상태는 `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_tasks.json` 기준으로 확인했다.
- 실행 중 작업:
  - task_id: `5da7e3db`
  - project_id: `V3_CH1_EP3_260520010025dc8282`
  - result_dir: `D:\long_result\CH1\EP.3.260520010025dc8282`
  - title: `비파형 동검의 주인, 이름 없는 권력자들 EP.03`
  - status: `running`
  - current_step: `4`
  - progress_pct: `45.6`
  - started_at: `2026-05-19T16:00:28Z`
- `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.json` 첫 항목도 위 CH1 EP3 running 상태다.
- CH1 EP4는 큐에 pending으로 있다.

## 이번 세션 주요 변경

### 1. Windows Update 자동 재부팅 차단

- 재부팅 사유 확인:
  - 마지막 부팅: `2026-05-20 01:31:59`
  - Event 1074: `MoUsoCoreWorker.exe`, `TrustedInstaller.exe`의 planned update/upgrade 재시작
  - Setup 로그: `KB5087051`, `KB5089549` 설치
  - 확인 구간에서 `Kernel-Power 41`, `6008` 없음
- 적용 스크립트:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\disable_windows_update_20260520_121530.ps1`
  - 로그: `C:\Users\Ai_M9\Desktop\longsult\_system\disable_windows_update_20260520_121530.log`
- 확인된 적용 상태:
  - `wuauserv`: `Stopped / Disabled`
  - `UsoSvc`: `Stopped / Disabled`
  - `WaaSMedicSvc`: `Stopped`, registry `Start=4`
  - `NoAutoUpdate=1`, `AUOptions=2`, `NoAutoRebootWithLoggedOnUsers=1`, `SetDisableUXWUAccess=1`
  - `\Microsoft\Windows\WindowsUpdate\Scheduled Start`: `Disabled`
- 일부 보호된 UpdateOrchestrator 작업은 Access denied 또는 경로 없음으로 처리되지 않았다.

### 2. 썸네일 문자 오버레이 70% 축소

- 수정 파일:
  - `backend/app/services/thumbnail_service.py`
  - `backend/tests/test_oneclick_stability.py`
- 변경:
  - `THUMBNAIL_TEXT_OVERLAY_SCALE = 0.70` 추가
  - Pillow 폰트 후보, subtitle threshold, EP badge, Devanagari browser CSS 경로 모두 70% 스케일 적용
- 검증:
  - `python -m py_compile backend/app/services/thumbnail_service.py backend/tests/test_oneclick_stability.py`
  - `python -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_overlay_font_candidates_are_scaled_to_seventy_percent backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_prompt_forces_visible_character_face`
  - `python -m unittest backend.tests.test_oneclick_stability` -> 78 tests OK
  - 샘플 생성 확인: scale `0.7`, candidates `(140, 126, 29)`, 출력 파일 생성됨
- 주의:
  - CH1 EP3 작업이 실행 중이라 이 변경 직후 백엔드 재시작은 하지 않았다.
  - 다음 세션에서 실행 작업이 없을 때 백엔드 재시작해야 런타임에 즉시 반영된다.

### 3. CH1 EP2 중복 폴더/재생성 방지 로직

- 실제 원인:
  - `prepare_task()`가 V3 Studio-linked 경로에서 기존 프로젝트 재사용 로직을 우회했다.
  - 큐 실행 `_fire_queue_for_channel()`이 인메모리 task만 보고 DB/결과 폴더를 먼저 복구하지 않았다.
  - 빈 retry 폴더가 기존 완료 폴더보다 우선 선택될 수 있었다.
- 수정 파일:
  - `backend/app/services/oneclick_service.py`
  - `backend/tests/test_oneclick_stability.py`
- 추가/수정 로직:
  - `D:\long_result\CHn\EP.n.*` orphan 결과 폴더 복구
  - 빈 retry 폴더 skip
  - `prepare_task()`, `_fire_queue_for_channel()`, `start_task()`, `resume_task()`에서 기존 episode 결과를 먼저 연결
  - `_inspect_backup_progress()`가 `script.json` cut 수를 먼저 읽어 EP2를 150컷으로 판단
- 검증:
  - `test_orphan_v3_result_lookup_skips_empty_retry_folders`
  - `test_fire_queue_recovers_existing_project_before_preparing_new_v3_run`
  - `test_empty_v3_retry_task_redirects_to_existing_episode_outputs`
  - 이후 full `backend.tests.test_oneclick_stability` 통과
- 처리 이력:
  - 백엔드 재시작 후 자동 복구된 CH1 EP2 업로드 task `63b6a541`은 의도치 않은 재업로드라 취소했다.

### 4. YouTube Studio 기능 삭제 및 채널운영 추가

- YouTube Studio 메뉴/라우트는 삭제했다. 복구 예정 없음.
- 작업대 아래 `채널운영` 메뉴 추가.
- 댓글 기능 구현:
  - 사용자가 `댓글 불러오기`를 눌러야 조회
  - 댓글 있는 영상들을 대상으로 조회
  - 개별 답변 / 전체 답변
  - GPT 5.5 답변 생성
  - 댓글 언어와 같은 언어로 답변
  - 비한국어 댓글 번역 표시
  - 채널 이동 후 불러온 댓글 상태 유지
- 주의:
  - 화면에서 403/OAuth scope 관련 오류가 보였던 부분은 다음 세션에서 실제 채널 불러오기 재검증 필요.

### 5. 제목/볼륨/TTS 로직

- Shorts 제목에서 `#1`, `#2`, `#3`, `#4` 형식 제거.
- Shorts와 본영상 모두:
  - BGM 볼륨 30% 감소
  - 나레이션 볼륨 30% 증가
- 일본어 TTS 독음 사전 추가:
  - `backend/app/services/tts/japanese_reading_dictionary.py`
  - `pykakasi==2.3.0`
  - `data/_system/japanese_readings.json`
  - `data/_system/japanese_readings.generated.json`
  - 미해결 로그: `C:\Users\Ai_M9\Desktop\longsult\_system\japanese_reading_missing.jsonl`
- 한자/한글 누수 용어를 일본어 독음으로 치환하도록 로직 수정.

## 다음 세션 우선 확인

1. CH1 EP3 running 작업이 끝났는지 먼저 확인.
2. 작업이 없으면 백엔드 재시작해서 썸네일 70% 변경을 런타임 반영.
3. 채널운영 댓글 불러오기 403/OAuth scope 문제를 실제 인증 상태로 재확인.
4. CH1 EP2/EP3/EP4를 다시 시작할 때 새 폴더 생성 없이 기존 결과/큐 연결이 되는지 확인.

---

# 새 세션 인계 메모 - 2026-05-12 12:52 KST

## 작업 원칙

- 추측으로 수정하지 말 것. 실제 파일, 실제 API, 실제 브라우저/파일 상태 기준으로만 판단.
- 생성 결과물 직접 수정 금지. 결과물 문제는 로직 수정으로 다음 생성물에 반영.
- 중요 수정 또는 기능 수정은 사용자 허락 후 진행.
- 현재 워킹트리에는 이전 작업 변경이 다수 섞여 있음. 무관한 변경은 되돌리지 말 것.

## 현재 상태

- LongTube 백엔드/프론트 재시작 완료.
  - 백엔드 PID: `13160`
  - 프론트 PID: `15492`
- 현재 실행 중 oneclick 작업 없음.
- 마지막 추적 작업 `31f18df4` 완료.
  - 작업: `CH3 EP.15`
  - 제목: `埴輪はなぜ墓の上に立ったのか？知られざる古代日本の境界線 EP.15`
  - 결과 폴더: `D:\long_result\CH3\EP.15.2605121137376a5eb5`
  - YouTube URL: `https://www.youtube.com/watch?v=WM49E5sBMU0`
  - 생성물 확인: 이미지 150개, 음성 150개, 영상 151개, 최종 output 파일 6개
  - 완료 로그: `YouTube 처리 완료 확인`, `제작 완료`

## 이번 세션에서 완료한 일

### 1. OpenAI 공식 비용 동기화 기능 추가

추가/수정 파일:
- `backend/app/services/openai_cost_sync.py`
- `backend/app/routers/v2/keys.py`
- `backend/app/security/vault_sync.py`
- `frontend/src/app/v2/settings/api/page.tsx`

동작:
- OpenAI는 잔액 API가 없으므로 공식 `organization/costs` API 사용액을 조회한다.
- 표시 계산은 `사용자가 입력한 충전액 - 공식 Costs API 사용액`.
- `OpenAI Admin` provider를 추가했다.
- `OPENAI_ADMIN_KEY` 또는 vault의 `OpenAI Admin` 키가 필요하다.
- 현재 일반 `OPENAI_API_KEY`는 모델 조회는 되지만 costs 조회는 `api.usage.read` 권한 부족으로 실패했었다.

검증:
- `python -m py_compile` 통과
- v2 keys 라우터 등록 확인
- `npx tsc --noEmit` 통과
- ESLint는 프로젝트 설정이 없어 Next 설정 프롬프트가 떠서 실행 불가

### 2. CH3 EP.15 작업 팔로우

- 재시작 후 `queued -> running` 복구 확인.
- 이미지 생성 Step 4 정상 증가 확인.
- 영상 생성 Step 5 정상 전환 확인.
- 업로드 Step 7 정상 완료 확인.
- `follow-ch3-ep15` heartbeat automation은 완료 후 삭제했다.

## 남은 핵심 이슈

### 이미지 얼굴 뭉개짐

사용자 지적:
- 생성 이미지에서 얼굴이 뭉개짐.

확인된 사실:
- 현재 EP.15 결과물의 문제는 단순 모델 품질 문제가 아니라 프롬프트 로직 문제다.
- 실제 프롬프트에서 `workers in plain hemp garments... focused faces` 같은 문장이 이미지 생성 전 `one faceless rounded-head worker... focused faces`처럼 바뀌고 있다.
- 즉 `faceless`와 `focused faces`가 동시에 들어가는 모순 프롬프트가 생긴다.

문제 위치:
- `backend/app/services/image/prompt_builder.py`
  - `_ANATOMY_RISK_IMAGE_PATTERNS`
    - `crowd of people -> one simplified faceless rounded-head character`
    - `group of people -> one simplified faceless rounded-head character`
    - `workers -> one faceless rounded-head worker`
    - `researchers -> one faceless rounded-head researcher`
  - `CARTOON_FACELESS_DIRECTIVE`
    - `blank smooth round head, featureless face area...`
  - `SIMPLE_CHARACTER_COUNT_DIRECTIVE`
    - `single faceless round-head character...`
- `backend/app/services/llm/visual_policy.py`
  - `_PROMPT_REWRITES`에도 `faceless round-head` 계열 리라이트가 정의되어 있다.
  - 단, 현재 코드상 `_PROMPT_REWRITES`는 직접 적용되는 흔적이 약하고, EP.15 실제 프롬프트에서는 `prompt_builder.py` 쪽 리라이트가 직접 확인됐다.

실제 확인 예:
- `D:\long_result\CH3\EP.15.2605121137376a5eb5\images\cut_4.png.prompt.json`
- 원본 성격: `workers ... focused faces`
- 최종 프롬프트 일부: `one faceless rounded-head worker ... focused faces`

수정 방향:
1. 역사 다큐 컷에서는 `faceless` 리라이트를 비활성화한다.
2. 실제 사람 인물은 `simple readable face`, `small readable facial features`, `medium-wide shot` 쪽으로 유도한다.
3. `haniwa`, `clay figure`, `statue`, `ceramic figure`는 얼굴 단순/무표정 허용.
4. 글자 금지, 지도 금지, 시대 고증 잠금은 유지한다.
5. 군중/다수 인물은 `faceless`로 뭉개지 말고 `small background crowd with simplified readable faces`처럼 바꾼다.

추가 확인 사항:
- 현재 이미지 모델: `comfyui-dreamshaper-xl-longtube`
- 워크플로: `backend/workflows/comfyui/dreamshaper_xl_longtube_text2img.json`
- 파일 메모 권장값:
  - LoRA `0.85`
  - CFG `2.0`
  - Steps `6~8`
- 현재 실제 워크플로 값:
  - LoRA strength `1.0 / 1.0`
  - CFG `5.0`
  - Steps `20`
- 얼굴/선 뭉개짐에는 이 과한 설정도 영향을 줄 수 있다. 다만 우선순위는 `faceless` 리라이트 제거다.

## 다음 세션 첫 작업 권장

사용자에게 확인받고 진행:

`역사 다큐 컷에서 faceless 리라이트가 적용되지 않게 prompt_builder.py 로직을 수정하고, 사람 인물은 readable face로 유도하게 바꾼다. 하니와/조각상은 예외로 둔다.`

수정 후 검증:
- 새 프롬프트 샘플에 `faceless`, `blank round head`, `featureless face`가 사람 컷에 붙지 않는지 확인.
- 하니와/토기 컷에는 과도한 얼굴 디테일 유도가 들어가지 않는지 확인.
- `python -m py_compile backend/app/services/image/prompt_builder.py backend/app/services/llm/visual_policy.py`
- 가능하면 소량 테스트 컷만 생성해서 결과 확인.

---

# 새 세션 인계 메모 - 2026-05-13 KST

## 작업 원칙 유지

- 추측 금지. 실제 파일/로그/산출물 기준으로만 답변.
- 생성 결과물 직접 수정 금지. 문제는 로직 수정으로 다음 생성물에 반영.
- 중요 수정 또는 기능 수정은 사용자 허락 후 진행.
- 워킹트리에는 기존 변경이 매우 많음. 무관한 변경 되돌리지 말 것.

## 이번 세션에서 확인/수정한 핵심

### 1. 150컷 길이 문제

사용자 지적:
- 컷 150개면 컷당 4초인데 결과가 12분을 넘음.

확인:
- `D:\long_result\CH3\EP.15.2605121137376a5eb5`
- DB/대본 설정은 `cut_video_duration=4.0`, `target_cuts=150`, `target_duration=600`.
- 실제 컷 영상/자막은 5초 기반.
- 원인: `backend/app/routers/video.py`가 설정값 대신 `CUT_VIDEO_DURATION=5.0` 상수를 사용.

수정:
- `backend/app/routers/video.py`
  - `CUT_VIDEO_DURATION` 직접 사용 제거.
  - `resolve_cut_video_duration(project.config or {})` 사용.
  - fallback `audio_duration or 5.0`도 `or cut_duration`으로 변경.

검증:
- `rg "CUT_VIDEO_DURATION|duration=5\.0|audio_duration.*5\.0" backend\app\routers\video.py` 결과 없음.
- `python -m py_compile backend\app\routers\video.py` 통과.

주의:
- 기존 EP.15 결과물은 그대로 5초 컷임.
- 다음 생성부터 4초 설정 적용.

### 2. 쇼츠 4개 생성/업로드 확인

EP.15 기준:
- `output/shorts/short_1.mp4` ~ `short_4.mp4` 존재.
- `output/shorts/shorts_uploads.json`에 4개 업로드 기록 존재.
- 문제:
  - 쇼츠 제목 일부에 줄바꿈 기반 공백 깨짐 있음.
  - `processing_verified: false`.

### 3. 얼굴 뭉개짐 원인 확인

확인된 원인:
- 이미지 프롬프트에서 사람 컷에 `faceless`, `featureless`, `blank round head` 계열 리라이트가 들어감.
- 동시에 `focused faces`, `readable face` 성격의 문장도 남아 모순 발생.

주요 위치:
- `backend/app/services/image/prompt_builder.py`
  - `CARTOON_FACELESS_DIRECTIVE`
  - `SIMPLE_CHARACTER_COUNT_DIRECTIVE`
  - `_ANATOMY_RISK_IMAGE_PATTERNS`

개선안:
- 역사 다큐/실사 컷에서는 사람 대상 `faceless` 리라이트 금지.
- 하니와/토기/조각상은 artifact로 별도 처리.
- 사람 컷은 `small readable facial features`, `natural readable face`, `medium shot` 계열로 유도.

### 4. 로컬 이미지 모델 v1.5 추가

추가 모델:
- `comfyui-dreamshaper-xl-longtube-v15`
- 이름: `SDXL 로컬모델 v1.5 실사`

수정/추가 파일:
- `backend/app/services/image/factory.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/app/services/estimation_service.py`
- `frontend/src/app/oneclick/layout.tsx`
- `frontend/src/app/oneclick/live/displayHelpers.ts`
- `backend/workflows/comfyui/dreamshaper_xl_longtube_v15_text2img.json`

v1.5 특징:
- DreamShaper XL Lightning 체크포인트 사용.
- LoRA 없음.
- steps `8`, cfg `2.0`, sampler `dpmpp_sde`, scheduler `karras`.
- 실사 다큐/고품질/자연스러운 얼굴 유도 프롬프트 추가.
- faceless/cartoon/anime/blank face 계열 negative 강화.

검증:
- `python -m py_compile backend\app\services\image\factory.py backend\app\services\image\comfyui_service.py backend\app\services\estimation_service.py`
- `npx tsc --noEmit` in frontend
- workflow JSON parse 확인.

### 5. 서버 재시작

실행:
- `cmd /c force-restart.bat`

확인:
- backend health OK.
- frontend `http://127.0.0.1:3000/` status 200.
- 당시 PID:
  - backend uvicorn python `31344`
  - frontend node `34916`

### 6. EP.15 대본으로 v1.5 이미지 10장 테스트

출력:
- `C:\Users\Ai_M9\Desktop\longtube\tmp\v15_ep15_image_test`

파일:
- `cut_001_v15.png` ~ `cut_010_v15.png`
- 각 prompt json
- `results.json`
- `contact_sheet_v15_10.png`

모델:
- `comfyui-dreamshaper-xl-longtube-v15`

### 7. CH4 EP.28 대본으로 v1.5 쇼츠 1편 생성

원본 최신 CH4:
- `D:\long_result\CH4\EP.28.26051309000787107e`

대본:
- `script.json`
- 제목: `समुद्री व्यापार और साम्राज्य: चोलों की खतरनाक समुद्री बाजी EP.28`
- 컷 수: 150

사용 구간:
- 쇼츠 group 1
- 컷 `25~36`
- 제목: `व्यापार बचाने के लिए युद्ध सही था?`

출력:
- `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_v15_short`
- 쇼츠:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_v15_short\output\shorts\short_1.mp4`
- 미리보기:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_v15_short\short_1_preview.jpg`

검증:
- `48.00초`
- `1080x1920`
- `30fps`
- 오디오 포함.

주의:
- 기존 CH4 결과물은 수정하지 않음.
- 별도 tmp 테스트 출력만 생성.

### 8. 등록 영상 모델 확인

현재 `backend/app/services/video/factory.py` 기준:
- 기본값: `ffmpeg-static`
- 등록:
  - `ffmpeg-static`
  - `ffmpeg-safe-motion`
  - `seedance-lite`
  - `comfyui-ltx23-v2`
  - `comfyui-ltx23-v3`
  - `comfyui-wan22-ti2v-5b`

폐기 alias:
- `ffmpeg-kenburns` -> `ffmpeg-static`
- `comfyui-ltxv-2b` -> `ffmpeg-static`
- `comfyui-ltxv-13b` -> `ffmpeg-static`
- `comfyui-wan22-i2v-fast` -> `ffmpeg-static`
- `comfyui-wan22-5b` -> `ffmpeg-static`

### 9. v1.5 이미지 12장으로 로컬 영상 모델별 쇼츠 테스트

사용 이미지:
- `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_v15_short\images`
- `cut_25.png` ~ `cut_36.png`

테스트 스크립트:
- `tmp/run_ch4_ep28_all_local_video_models.py`

출력 루트:
- `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts`

대상 로컬 모델:
- `ffmpeg-static`
- `ffmpeg-safe-motion`
- `comfyui-ltx23-v2`
- `comfyui-ltx23-v3`
- `comfyui-wan22-ti2v-5b`

완료 확인:
- `ffmpeg-static`
  - 쇼츠 완료:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts\ffmpeg-static\output\shorts\short_1.mp4`
  - size 로그: `5678954`
- `ffmpeg-safe-motion`
  - 쇼츠 완료:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts\ffmpeg-safe-motion\output\shorts\short_1.mp4`
  - size 로그: `14099584`
- `comfyui-ltx23-v2`
  - 쇼츠 완료:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts\comfyui-ltx23-v2\output\shorts\short_1.mp4`
  - size 로그: `38445141`
- `comfyui-ltx23-v3`
  - 쇼츠 완료:
  - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts\comfyui-ltx23-v3\output\shorts\short_1.mp4`
  - size 로그: `40280076`
- `comfyui-wan22-ti2v-5b`
  - 진행 중 사용자가 중단.
  - 마지막 확인 로그: 컷 `25`, `26` 완료.
  - 이후 사용자가 “새 세션가자” 요청.
  - 백그라운드 프로세스 확인 시 `24016`, `21760` 남아있지 않았음.
  - 따라서 Wan 전체 완료 여부는 다음 세션에서 파일로 재확인 필요.

중간 오류 및 수정:
- `ffmpeg-safe-motion` 첫 실행 실패.
- 원인: `backend/app/services/video/ffmpeg_service.py`의 `crop={resolution}`가 FFmpeg crop 필터에 `640x384` 형식으로 들어감.
- 수정:
  - `crop={resolution}` -> `crop={pad_wh}`
  - `crop={resolution}:` -> `crop={pad_wh}:`
- 검증:
  - `python -m py_compile backend\app\services\video\ffmpeg_service.py` 통과.
- 이 수정은 실제 코드 변경임.

주의:
- `comfyui-ltx23-v3`는 코드상 T2V 모델이라 입력 이미지를 직접 쓰지 않음.
- `comfyui-wan22-ti2v-5b`는 이미지 입력 사용 모델.
- 테스트 스크립트는 tmp용이며 운영 플로우에 직접 연결하지 않음.

## 다음 세션 시작 시 확인할 것

1. Wan 출력 폴더 확인:
   - `C:\Users\Ai_M9\Desktop\longtube\tmp\ch4_ep28_video_model_shorts\comfyui-wan22-ti2v-5b`
   - `videos\cut_25.mp4` ~ `cut_36.mp4` 개수
   - `output\shorts\short_1.mp4` 존재 여부
2. 모든 생성 쇼츠 duration/해상도 검증:
   - ffmpeg-static
   - ffmpeg-safe-motion
   - comfyui-ltx23-v2
   - comfyui-ltx23-v3
   - comfyui-wan22-ti2v-5b
3. `ffmpeg-safe-motion` crop 수정은 운영 코드 변경이므로 필요 시 별도 보고/테스트 유지.
4. 아직 근본 얼굴 개선 로직(`prompt_builder.py` faceless 제거)은 실제로 수정하지 않음. 다음 작업 후보.

---

## 2026-05-17 13:59 KST 세션 인계

### 사용자 지시

- 채널 전체 모든 영상과 숏츠의 BGM 음량을 반으로 줄임.
- 대본 작성/생성 로직에 남은 `120컷`, `5초`, `duration_estimate 5.0` 흔적을 확인하고 `150컷 / 4초` 기준으로 변경.
- 현재 내용 저장 후 새 세션으로 이동 요청.

### 완료한 변경

BGM:
- 기존 기본값 `0.42`를 `0.21`로 변경.
- 일반 렌더 기본값, 숏츠 렌더 기본값, 프론트 렌더 UI fallback, v2 프리셋 fallback을 맞춤.
- DB `projects` 111건, `channel_presets` 2건의 `bgm_volume`을 모두 `0.21`로 변경.
- 백업 DB:
  - `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_bgm_volume_half_20260517_134149.db`

150컷 / 4초:
- `backend/app/config.py`
  - `CUT_VIDEO_DURATION = 4.0`
  - fallback 설명을 4초 기준으로 변경.
- `backend/app/routers/projects.py`
  - `DEFAULT_CONFIG["cut_video_duration"] = 4.0`
  - `target_duration = 600`
- `backend/app/services/llm/base.py`
  - 시스템 프롬프트가 `duration_estimate: 4.0`을 쓰도록 확인.
  - `91~120컷` 표기가 `120컷`으로 오해될 수 있어 구간 수 설명으로 변경.
- `backend/app/services/tts/narration_fit.py`
  - 컷 길이 fallback `5.0`을 `4.0`으로 변경.
- DB `projects` 111건, `channel_presets` 2건 모두 아래 값으로 정규화:
  - `cut_video_duration: 4.0`
  - `target_cuts: 150`
  - `target_duration: 600`
- 백업 DB:
  - `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_150cuts_4s_20260517_134916.db`

### 검증

- `python -m py_compile backend/app/services/llm/base.py backend/app/config.py backend/app/routers/projects.py backend/app/routers/subtitle.py backend/app/services/tts/narration_fit.py backend/app/services/estimation_service.py` 통과.
- `python backend/tests/test_oneclick_stability.py` 통과.
- 결과: `51 tests OK`.
- 대본 생성 관련 범위에서 아래 검색어 잔여 없음:
  - `target_cuts: 120`
  - `cut_video_duration: 5.0`
  - `CUT_VIDEO_DURATION = 5.0`
  - `duration_estimate: 5.0`
  - `120컷`
  - `5초 컷`

### 현재 변경 파일

작업 관련 미커밋 파일:
- `backend/app/config.py`
- `backend/app/routers/projects.py`
- `backend/app/routers/subtitle.py`
- `backend/app/services/estimation_service.py`
- `backend/app/services/llm/base.py`
- `backend/app/services/tts/narration_fit.py`
- `backend/tests/test_oneclick_stability.py`
- `frontend/src/app/v2/presets/[id]/page.tsx`
- `frontend/src/components/studio/StepRender.tsx`

주의:
- DB `data/longtube.db`는 Git status에 표시되지 않지만 실제 변경됨.
- 기존에 이미 많은 unrelated dirty 파일이 있었으므로 다음 세션에서 커밋 시 staging 범위를 반드시 제한할 것.
- 이미 렌더된 MP4와 업로드된 영상의 소리는 설정만으로 바뀌지 않음. 실제 영상 파일 반영은 재렌더 필요.
