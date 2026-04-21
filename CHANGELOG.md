# LongTube Changelog

## v1.1.63 (2026-04-20)

### 새 기능 — Claude Opus 4.7 대본 모델 추가

- **배경**: Anthropic 이 2026-04-16 에 Claude Opus 4.7 을 GA 로 출시. 1M 토큰
  context / 128k max output / 고해상도 이미지 입력 (2576px / 3.75MP) 지원.
  가격은 input $5 / output $25 per 1M tokens (Opus 4.6 과 동일).
- **수정**:
  - `backend/app/services/llm/factory.py` — `LLM_REGISTRY` 에 `claude-opus-4-7`
    엔트리 추가. 프론트 `/api/models/llm` 드롭다운에 자동 노출.
  - `backend/app/services/llm/claude_service.py` — `_model_map` 에 매핑 추가.
    Anthropic API model string 은 `claude-opus-4-7` (날짜 suffix 없음).

### 버그 수정 — UI 에서 API 키를 바꿔도 반영 안 되던 문제

- **증상**: `/api/api-keys/save` 로 키를 교체하면 `.env` 와 `os.environ` 과
  `app.config` 모듈 속성은 갱신되는데, 실제 API 호출에는 옛날 키가 계속 사용됨.
  서버를 재시작해야 반영됨.
- **원인**: 서비스 파일들이 `from app.config import ANTHROPIC_API_KEY` 같은 형식
  으로 모듈 레벨에서 값을 자기 네임스페이스에 복사. `from X import Y` 는 "객체
  바인딩" 이라 원본 변수가 이후에 바뀌어도 복사본은 옛 값을 계속 가리킨다.
- **수정 패턴**: 각 서비스에서 `from app import config` 로 바꾸고, 사용처를
  `config.ANTHROPIC_API_KEY` 로 변경. 서비스 인스턴스는 팩토리에서 매 요청마다
  새로 만들어지므로 `__init__` 에서 `config.XXX` 를 참조하면 최신 키가 즉시 반영된다.
- **수정 파일** (총 13개):
  - 서비스 10개: `llm/claude_service`, `llm/gpt_service`, `tts/openai_tts_service`,
    `tts/elevenlabs_service`, `image/openai_image_service`, `image/nano_banana_service`,
    `image/midjourney_service`, `image/grok_service`, `image/flux_service`,
    `image/fal_generic_service`
  - 라우터/태스크 3개: `routers/voice.py` (3곳), `routers/script.py` (2곳),
    `tasks/pipeline_tasks.py` (1곳) — 로컬 변수 `config` 와 충돌 회피 위해
    `from app import config as app_config` 별칭 사용.
- **특이 사항**: `ElevenLabsService.headers` 는 `__init__` 에서 dict 를 만들어
  재사용하던 구조라 `@property` 로 변환, 매 접근마다 최신 키를 조합.
- **하위 호환**: `.env` 기반 실행 경로는 그대로 유지. 기존 동작 회귀 없음.

### 유지보수 — 런타임 로그 / 빌드 캐시 추적 중단

- `.gitignore` 에 `*.log`, `backend/logs/`, `*.tsbuildinfo` 추가.
- 기존 추적 중이던 `backend/logs/image_async.log`, `backend/logs/video_async.log`,
  `frontend/tsconfig.tsbuildinfo` 는 `git rm --cached` 로 인덱스에서 제거 (파일은 유지).

### 유지보수 — 버전 표기 4곳 통일

- `backend/app/main.py` (FastAPI metadata + `/api/health` 응답)
- `frontend/src/lib/version.ts` (`APP_VERSION`)
- `frontend/package.json`, `frontend/package-lock.json`
- 이전에는 frontend 만 1.1.55 에 멈춰있었고 backend 코드 주석은 v1.1.61 / v1.1.62
  까지 진행된 상태여서 표기 갭이 있었다. 이번 릴리스에서 전부 1.1.63 으로 통일.

### 유지보수 — 팩토리 주석 & README 모델 목록 교정

- `backend/app/services/image/factory.py` — 주석 "DreamShaper XL 하나만 유지"
  를 실제 상태로 교정. 현재는 DreamShaper XL 베이스 5종 (기본 / Vector /
  LongTube 2K·3K·4K) + Qwen-Image-Edit 2509 fp8 레퍼런스 모델 총 6개가 등록됨.
- `backend/app/services/video/factory.py` — 주석 갱신. LTX Video 2B distilled
  + HunyuanVideo 1.5 480p 가 현재 등록된 ComfyUI 영상 모델. WAN 2.2 및
  LTX 13B distilled 는 워크플로 JSON 만 `workflows/comfyui/` 에 남아있고
  체크포인트 미설치 상태라 레지스트리 미등록 (사용 불가).
  - 참고: WAN 2.2 는 v1.1.55 에서 `comfyui-wan22-i2v-fast` 로 최초 등록됐으나,
    이후 체크포인트 문제로 레지스트리에서 제거됨. 정확한 제거 시점은
    v1.1.56 ~ v1.1.62 사이 (커밋 로그 별도 확인 필요).
- `README.md` — ComfyUI 이미지·영상 모델 표에서 "DreamShaper XL 등", "WAN 2.2
  등" 같은 모호/허위 기재를 현재 등록된 모델 정확 목록으로 교체.
- `docs/ARCHITECTURE.md` — 최상단에 "초기 설계 문서, 현재 구현과 갭 있음" 표시
  + 현행 문서 링크 테이블 + 주요 갭 요약 섹션 추가. 987줄 본문은 역사적 기록
  으로 보존 (추상적 재작성 회피).

---

## v1.1.55 (2026-04-15)

### 새 기능 — 같은 네트워크 ComfyUI 서버로 이미지·영상 생성 위임 (비용 0)

- **배경**: 사용자의 JERRY PC (RTX 5070 Ti Laptop 12GB VRAM, i9-14900HX,
  32GB RAM) 에 ComfyUI Desktop v0.19.0 설치. 받아둔 모델:
  - 이미지: `flux2_dev_fp8mixed`, `z_image_turbo_bf16`
  - 영상: `wan2.2_i2v_high_noise_14B_fp8_scaled`, `wan2.2_i2v_low_noise_14B_fp8_scaled`
  - LoRA: `Flux_2-Turbo-LoRA`, `wan2.2_i2v_lightx2v_4steps_lora` (high/low)
  - CLIP: `mistral_3_small_flux2`, `umt5_xxl_fp8_e4m3fn_scaled`
  - VAE: `ae.safetensors`, `wan_2.1_vae.safetensors`
- **설정**: `.env` 에 `COMFYUI_BASE_URL=http://192.168.0.45:8188` 추가.
  ComfyUI Desktop Settings → Server-Config → Host = `0.0.0.0` 필수
  (기본 `127.0.0.1` 이면 다른 PC 에서 접근 불가).
- **추가된 모델 (팩토리 등록)**:
  - `comfyui-flux2-turbo` — Flux.2 Dev + Turbo LoRA, 8 steps, cfg 1.0
  - `comfyui-wan22-i2v-fast` — WAN 2.2 I2V 14B, 2단(high→low) 샘플링 각 2
    step + lightx2v 4-step LoRA. 5초 @ 16fps mp4 출력.
- **파일**:
  - `app/services/comfyui_client.py` — `/upload/image`, `/prompt`,
    `/history/{id}` 폴링, `/view` 다운로드 및 `${KEY}` 치환 유틸.
  - `app/services/image/comfyui_service.py` — `BaseImageService` 구현.
  - `app/services/video/comfyui_service.py` — `BaseVideoService` 구현.
    소스 이미지를 `/upload/image` 로 올려 `LoadImage` 노드에 주입, 종횡비에
    맞춰 WAN 권장 해상도(832×480 등) + 4n+1 프레임 길이 자동 산출.
  - `backend/workflows/comfyui/flux2_turbo_text2img.json`
  - `backend/workflows/comfyui/wan22_i2v_fast.json`
- **비용/성능**: fal.ai Kling 2.5 Turbo ($0.35/5s) / Seedance Lite ($0.18/5s)
  대비 비용 0. 5070 Ti 에서 WAN 2.2 I2V 5초 클립 ~30~60s 예상.
- **한계/추후**: 레퍼런스 이미지(IPAdapter/Flux Kontext) 미구현 —
  `supports_reference_images=False`. 필요 시 워크플로 JSON 만 교체하면 확장.

### HOTFIX — 컷별 자막 번인 실패 (async 컨텍스트에서 이벤트 루프 충돌)

- **증상**: "자막이 안 붙는다." 컷 단계 자막 번인이 전혀 동작하지 않음.
- **원인**: `_burn_cut_subtitle` 이 동기 함수로 선언돼 있고 내부에서
  `run_async(_FF.burn_subtitles(...))` 를 호출했는데, 호출부 `_one` 은
  이미 async 컨텍스트. 새 이벤트 루프를 `run_until_complete` 로 돌리려고
  하면 "This event loop is already running" RuntimeError 가 나고,
  `_one` 의 광범위한 except 에서 조용히 삼켜져 자막이 통째로 누락됨.
- **수정**: `_burn_cut_subtitle` 을 `async def` 로 전환, 내부는
  `await _FF.burn_subtitles(...)` 로 직접 await. 호출부도 `await` 로 변경.
  이제 컷 mp4 가 생기자마자 자기 대사가 0~audio_duration 에 제대로 번인된다.

### 진단 — 프리셋 이름으로 자산 디스크 실태 조회 엔드포인트

- **사용자 요구**: "프로젝트 ID 로 관리하지 말고 프리셋 이름으로 관리해
  야지" — project_id (8자리 해시) 를 모르면 자산 누락 조사도 못 하던
  문제. 폴더 이름 자체를 프리셋명으로 바꾸는 본격 마이그레이션은 별도
  작업으로 두고, 우선 임시 진단 라우터부터 추가.
- `GET /api/projects/_diagnose/by-title?title=딸깍폼-제리스아케오` →
  제목 ILIKE 매칭되는 모든 프로젝트의 reference/character/logo/interlude
  자산을 (a) 디스크 존재 여부, (b) 누락 시 DATA_DIR 다른 폴더에서 발견
  되는 고아 후보까지 한 번에 보고. project_id 모르는 상태에서 사용 가능.

### UX — 진행 중·실패·완료 태스크 행에 채널/프리셋 칩 추가

- **사용자 요구**: "제작 큐에서 실행했을 때 여기에 채널하고 프리셋
  표시해" — 큐 항목에는 CH 칩 + 프리셋명이 보였지만 실행 시작 후
  상단 진행 행으로 올라가면 두 정보가 사라져서 어느 채널·어느 프리셋이
  돌고 있는지 알 수가 없었다.
- **변경**: `app/oneclick/page.tsx` 의 진행 중(amber) / 실패·취소(red) /
  완료(green) 세 행 모두에 큐 항목과 동일한 형식의 `CH N` 칩 +
  프리셋명을 제목 아래로 노출. 색상 매핑(파랑/초록/앰버/보라) 도 큐와
  통일해서 시각적으로 즉시 식별 가능. 진행 중 행은 `triggered_by` 가
  schedule 인 경우 "· 스케줄" 추가 표기.

### 기능 — 컷별 자막 즉시 번인 (`cut_level_subtitles`) — 머지 후 싱크 깨짐 차단

- **사용자 요구**: "머지를 만들때 자막을 붙이면 씽크가 안맞아. 영상
  개별생성할때 해당 대사에 맞는 자막을 바로 입혀."
- **원인**: 기존 본편 ASS 는 각 컷을 `CUT_VIDEO_DURATION` 고정 창에
  배치했지만, 렌더 단계의 `ensure_min_duration(min=5s)` 로 짧은 컷이
  늘어나 실제 mp4 타임라인과 ASS 타임라인이 어긋났다.
- **변경**:
  - 새 헬퍼 `subtitle_service.generate_single_cut_ass(narration,
    duration, style, aspect)` — 0~`duration` 안에 문장 균등 분배.
  - `tasks/pipeline_tasks._step_video` — 각 컷 mp4 가 만들어지면 즉시
    자기 대사 자막을 in-place 로 번인 (`_burn_cut_subtitle`). 오디오
    길이는 DB `audio_duration` 우선, 없으면 `ffprobe` 로 측정.
  - `routers/subtitle.render_video_with_subtitles` — `cut_level_subtitles`
    True (기본) 면 본편 단계의 ASS 생성/burn 을 모두 건너뛰고 머지·페이드
    만 수행. 컷 클립이 늘어나도 자막은 자기 클립 안에서만 살아 있어 싱크
    절대 안 깨짐.
- **새 설정**: `DEFAULT_CONFIG.cut_level_subtitles = True`. 옛 동작이
  필요하면 프리셋에서 False 로 토글.
- **실패 격리**: 컷별 burn 이 실패해도 영상 자체는 보존, 다음 컷 진행.

### 기능 — 영상 생성 후 자동 렌더 (자막 + 오프닝/엔딩 통합)

- **사용자 요구**: "렌더할 때 오프닝 꼭 집어 넣고. 영상만들때 자막도
  한꺼번에 붙여." — 그동안 step 5(영상 생성) 이 끝난 뒤 자막 번인 +
  오프닝/엔딩 합성은 수동 트리거(step 6) 였다. 자주 누락 사고가 발생.
- **변경**: `tasks/pipeline_tasks._step_video` 가 `merged.mp4` 생성을
  마치는 즉시 `routers/subtitle.render_video_with_subtitles` 를 호출해
  `final_with_subtitles.mp4` 를 함께 만들도록 자동화. 결과적으로 step 5
  하나만 돌려도 자막 + 오프닝 + 엔딩 까지 포함된 최종 영상이 나온다.
- **오프닝 누락 경고 강화**: 렌더러가 오프닝 파일을 찾지 못하면 두 가지
  메시지로 분기 — (a) interlude 에 등록은 돼 있는데 디스크 파일이 사라진
  경우 / (b) 아예 미등록 — 사용자가 어느 쪽을 손봐야 할지 즉시 식별.
- **실패 격리**: 후속 자동 렌더가 실패해도 step 5 자체는 완료로 마킹.
  사용자가 수동으로 `/render-async` 재시도 가능.

### 기능 — 인트로 N 컷 강제 AI 생성 (`ai_video_first_n`)

- **목적**: 영상 후킹의 핵심인 인트로 컷의 품질을 항상 보장. 사용자 요구
  "앞에 5장은 무조껀 ai로 제작 하라고 했는데?" — 실제로 코드에 그 규칙이
  없어서 `video_target_selection=every_5` 같은 옵션을 쓰면 인트로마저
  ffmpeg-static 폴백으로 떨어지던 사고를 차단.
- **새 설정**: `DEFAULT_CONFIG.ai_video_first_n = 5`. 양수면 컷 1..N 은
  `video_target_selection` 과 무관하게 무조건 primary `video_model` 로 생성.
  `0` 으로 두면 비활성 (selection 규칙만 적용).
- **반영 지점** (모두 동일 규칙으로 동기화):
  - `services/video/prompt_builder.should_generate_ai_video(cut_number,
    selection, ai_first_n=5)` — 파이프라인용 헬퍼.
  - `routers/video.py` 의 `should_generate_ai_video` /
    `count_ai_video_cuts` — 스튜디오 수동 생성 / 비동기 / resume 3 경로.
  - `tasks/pipeline_tasks._step_video` — 딸깍 파이프라인.
  - `services/estimation_service._count_ai_video_cuts` — 비용 견적이 실제
    생성 컷 수와 어긋나지 않도록 동일 규칙 미러링.

### 핫픽스 — 큐 업로드가 잘못된 계정으로 가던 버그 (실제 원인)

- **증상**: 큐에서 "무서운이야기" 프리셋을 골라도 업로드는 다른 계정
  ("제리스 아키오") 으로 자꾸 들어가던 사고. 재발성.
- **진짜 원인**: 프리셋에 OAuth 인증한 토큰은 `DATA_DIR/{preset_id}/
  youtube_token.json` 으로 저장된다. 그런데 큐가 발화해서 `_clone_project_
  from_template` 이 새 project_id 를 만들 때, **에셋 복사 함수
  (`_copy_template_assets`) 가 youtube_token.json 을 복사하지 않아서**
  클론 디렉토리에 토큰이 없었다. 결과: `_step_youtube_upload` 가
  프로젝트 토큰을 못 찾고 채널 기본값(CH1) 토큰으로 폴백 → 전혀 다른
  계정으로 업로드.
- **수정**:
  - `_copy_template_assets`: 프리셋 디렉토리의 `youtube_token.json` 을
    클론 디렉토리로 복사. 프리셋에 묶인 계정이 그대로 따라간다.
  - `_step_youtube_upload`: 우선순위를 **프로젝트 토큰 → 채널 → 전역**
    으로 재배치. 프리셋의 토큰이 항상 채널 기본값을 이기게 만들어
    같은 사고가 다시 못 일어나도록 방어.
- 추가 보강: `_queue_normalize` 와 `_step_youtube_upload` 에 채널
  우선순위 정리 로직도 같이 들어갔지만 (`config.youtube_channel`
  상속), 실제 본질 원인은 토큰 파일 복사 누락이었다.

### 기능 — API 잔액 실시간 감산 + 부족 경고 + 스타일 레퍼런스 락 통합

- **수동 입력 잔액 관리 (`/settings`)**: Anthropic / OpenAI / ElevenLabs /
  fal.ai / xAI 5 개 제공자에 대해 콘솔에서 확인한 잔액을 직접 입력.
  단위(USD/KRW/chars/credits), 경고선(low_threshold), 메모 지원.
  저장소: `DATA_DIR/api_balances.json`.
- **실시간 지출 감산**: 새 `app.services.spend_ledger` 모듈이 파이프라인의
  LLM·TTS·이미지·비디오 호출마다 예상 비용(estimation_service 가격표 기준)을
  JSONL 원장(`api_spend_log.jsonl`)에 append. `remaining = initial_amount -
  spend_since(set_at)` 으로 대시보드 타일에 남은 잔액을 실시간 표시.
- **잔액 부족 경고**: `low_threshold` 설정 시 남은 잔액이 미만이면 대시보드
  상단에 빨간 배너 + 해당 타일 빨강/`부족` 배지.
- **지출 리셋 버튼**: 크레딧 충전 후 "지금부터 감산" 으로 기준점 재설정
  (`POST /api/api-balances/{provider}/reset-spend`). 이전 레코드는 prune.
- **"API 설정" 메뉴 추가**: 헤더에 키 + 잔액 + 경고선을 한 화면에서 관리.
  런웨이 / 미드저니 / 클링 타일은 대시보드에서 삭제됨.
- **API 상태 패널 무한로딩 수정**: 5 개 체크를 `asyncio.gather` 로 병렬화 +
  15s 하드 타임아웃, 프론트에 18s `AbortController`. 직렬 50s 시나리오 해소.
- **스타일 레퍼런스 락 프리픽스 통합**: 모든 이미지 생성 경로(딸깍 컷/썸네일,
  스튜디오 재생성, 유튜브 썸네일, nano-banana edit)에서 동일한
  `REFERENCE_STYLE_PREFIX` 를 사용. 레퍼런스가 있는데 하나도 못 읽으면
  조용히 t2i 로 떨어지던 사고 차단 (명시적 RuntimeError).

---

## v1.1.54 (2026-04-14)

### 버그 수정 — TTS 음성 3초 문제 + 중지 즉시 반영 + 썸네일 생성 안정화

- **TTS 음성 3초 고정 버그**: `_get_duration()`이 bare `ffprobe`를 호출하여
  Windows에서 PATH 누락으로 실패 → 파일 크기 추정(`size/16000`)이 부정확한
  duration을 반환 → `enforce_min_duration`이 미발동. `_resolve_bins()`로
  ffprobe 절대경로 사용하도록 수정. (openai_tts_service, elevenlabs_service)
- **중지 시 API 크레딧 낭비**: 병렬 실행(음성+이미지) 중 cancel 시
  `ThreadPoolExecutor.__exit__`이 `shutdown(wait=True)`로 나머지 스레드를
  끝까지 기다림. `with` 블록 대신 수동 생성 + `shutdown(wait=False, cancel_futures=True)`
  로 즉시 탈출.
- **썸네일 생성 실패**: (1) fallback 프롬프트의 "provocative/shocking" 등이
  OpenAI content policy 위반 가능 → 안전한 표현으로 완화. (2) `/edits`
  엔드포인트에 재시도 로직 없음 → 3회 재시도 + 표준 생성 폴백 추가.
- **자동저장 디바운스**: 1초 → 5초. 주제 입력 중 저장되어 추가 불가 문제 해결.

---

## v1.1.52 (2026-04-13)

### 버그 수정 — 템플릿 에셋 미복사 + cancel 시그널 라우팅 오류

- **템플릿 에셋 물리 복사**: 딸깍 프리셋 사용 시 `_clone_project_from_template`가
  config dict만 복사하고 실제 레퍼런스/캐릭터/로고/간지 파일은 복사하지 않아
  생성 이미지에 스타일이 전혀 반영되지 않던 문제 수정. `_copy_template_assets()`
  함수 추가.
- **cancel 시그널 라우팅**: `cancel_task()`가 `app.routers.pipeline._redis_set`에
  기록하고 `check_pause_or_cancel()`은 `app.tasks.pipeline_tasks._redis_get`에서
  읽어 cancel이 도달하지 않던 문제 수정. import를 `pipeline_tasks`로 통일.
- **이미지/영상 삭제 기능**: `clear_step_outputs()` + `POST /{task_id}/clear-step/{step}`
  엔드포인트 추가. 프론트엔드에 "이미지 삭제" / "영상 삭제" 버튼 추가.
- **실패 배너에 토픽명 표시**: 큐 이름을 배너에 함께 표시.
- **cmd 창 최소화**: `start.bat`에서 backend/frontend 창을 `/min`으로 실행.
- **`_step_video` NameError**: 미정의 `ffmpeg` 참조를 `FFmpegService` import로 수정.
- **ghost test 호환성**: `DummyVideoService`에 `generate()` 메서드 추가.

---

## v1.1.48 (2026-04-12)

### 버그 수정 — 딸깍 제작 "중지" 버튼이 실제로 멈추게 수선

사용자 보고: "중지가 안되네." 스크린샷은 `대본 생성` 단계에서 0.0% 로 고정된
딸깍 태스크였다.

원인은 세 군데에 나뉘어 있었다.

**1. `_step_script` 에 취소 체크가 전무했다.**

대본 생성은 LLM 호출 한 방이라(30~60초) 컷 단위 루프가 없다. 기존 코드는
`service.generate_script(...)` 를 그대로 `run_async` 로 돌릴 뿐, 전후에
`check_pause_or_cancel` 호출이 하나도 없었다. 그래서 사용자가 중지를 눌러 Redis
`pipeline:cancel:{pid}` 플래그가 세팅돼도 LLM 이 끝날 때까지는 아무도 그 플래그를
읽지 않았다. LLM 호출 자체는 중간 인터럽트가 불가능하지만, **호출 직전/직후**
에는 플래그를 볼 수 있다. 이번에 두 지점에 `check_pause_or_cancel(project_id, 2)`
를 추가해 LLM 응답이 돌아온 순간 저장/컷 생성 전에 깔끔히 빠지게 했다.

**2. `_run_oneclick_task` 가 `PipelineCancelled` 를 못 잡고 `failed` 로 기록했다.**

기존엔 `except Exception` 만 있어 사용자 취소조차 `failed` 로 마감됐다. 이제
`PipelineCancelled` 를 별도로 catch 해 단계 상태를 `cancelled`, task 상태를
`cancelled` 로 기록하고 프로젝트 상태도 `cancelled` 로 갱신한다. 또 각 단계 진입
**전/후** 에 `task["status"] == "cancelled"` 를 확인해, 다음 단계로 들어가기 전에
조용히 빠져나온다.

**3. `cancel_task` 가 running 일 때는 UI 를 갱신하지 않았다.**

이전에는 prepared/queued 일 때만 status 를 cancelled 로 바꾸고 running 인 경우
에는 Redis 플래그만 세팅한 채 status 를 그대로 뒀다. 결과적으로 사용자가 중지를
눌러도 UI 상 여전히 `running` 으로 보여 "중지가 안된다" 는 체감이 만들어졌다.
v1.1.48 부터는 상태와 무관하게 즉시 `cancelled + finished_at` 으로 낙관적 마킹한다.
Runner 는 다음 단계 진입 체크에서 이 status 를 읽고 깔끔히 종료한다.

**수정 파일:**
- `backend/app/tasks/pipeline_tasks.py` — `_step_script` 에 LLM 전후 취소 체크 2개.
- `backend/app/services/oneclick_service.py`
  - `_run_oneclick_task`: `PipelineCancelled` 별도 catch + 매 단계 전/후 status 체크.
  - `cancel_task`: running 이든 아니든 즉시 `cancelled` 로 낙관적 마킹.

즉 pipeline 내부 컷 루프(_step_voice/image/video)는 기존처럼 Redis 플래그로 깨어나고,
대본 단계는 LLM 전후 체크 + status 폴링으로 빠지고, UI 는 즉시 업데이트된다.

## v1.1.47 (2026-04-12)

### 변경 — StepSettings 에 TTS 미리듣기 버튼 추가

사용자 요구: "TTS 미리듣기 해줘야지."

v1.1.46 에서 TTS 모델·목소리 선택을 프로젝트 설정으로 옮겼지만, 정작
**그 자리에서 바로 들어볼 방법이 없었다**. 미리듣기 버튼은 여전히 StepVoice
(음성 생성 스텝) 툴바에만 있었기 때문에, 사용자가 목소리를 고르려면 설정에서
골라 → 저장 → 음성 스텝으로 넘어가 → 미리듣기 → 마음에 안 들면 다시 설정으로
돌아가는 순회를 해야 했다. 이번 변경은 그 순회를 없앤다.

**1. 백엔드 — `/voice/{id}/preview` 에 옵셔널 override JSON body 추가**

`backend/app/routers/voice.py`:
- `PreviewOverride` Pydantic 모델 신설: `tts_model`, `tts_voice_id`,
  `tts_voice_preset`, `tts_voice_lang`, `tts_speed` 전부 옵셔널.
- `preview_voice()` 는 body override 값이 있으면 그걸 사용하고, 없으면 기존처럼
  저장된 `project.config` 로 폴백. `pick()` 헬퍼로 필드 단위 병합.
- 기존 호출자(빈 body) 와 완전히 하위 호환.

**2. 프런트 — `voiceApi.preview(id, override?)` 시그니처 확장**

`frontend/src/lib/api.ts`:
- 두 번째 파라미터에 `{ tts_model?, tts_voice_id?, tts_voice_preset?,
  tts_voice_lang?, tts_speed? }` 를 받도록 확장.
- 없으면 빈 객체 `{}` 를 보낸다 (서버가 옵셔널로 처리).

**3. StepSettings — AI 모델 섹션에 "TTS 미리듣기" 버튼 + 핸들러**

`frontend/src/components/studio/StepSettings.tsx`:
- `ttsPreviewLoading`, `ttsPreviewPlaying` 상태 신설.
- `previewTts()` 핸들러: 저장 없이 현재 local `config` 의 TTS 필드 5개를
  override 로 서버에 보내고 결과 mp3 를 Audio 로 재생.
- AI 모델 선택 그리드 바로 아래에 우측 정렬된 "TTS 미리듣기" 버튼 + 안내 문구
  (`저장 없이 현재 선택된 모델·목소리·속도로 짧은 샘플을 생성합니다`).
- 버튼 상태: `생성 중...` / `재생 중...` / `TTS 미리듣기` 로 전환.
- 목소리가 선택돼 있지 않으면 disabled.

### 사용자 체감 결과

- 설정 화면에서 목소리 드롭다운을 열어 하나 고르고 → 바로 아래 "TTS 미리듣기"
  버튼을 눌러 즉시 샘플 재생. 마음에 안 들면 다시 드롭다운 → 미리듣기 반복.
- 저장을 하지 않은 상태에서도 정확히 **현재 화면에서 보이는 설정대로** 들린다.
- 기존 StepVoice 의 미리듣기 버튼은 그대로 유지 (역호환).

### 호환성

- `/voice/{id}/preview` 는 빈 body 로도 동작하므로 StepVoice 의 기존 호출도
  동일하게 작동한다.
- `voice_preview.mp3` 파일은 기존과 동일하게 `DATA_DIR/{project_id}/audio/` 에
  저장된다. 설정 화면과 음성 스텝이 같은 파일에 덮어쓰기 때문에 마지막 미리듣기
  결과만 남는다 (의도된 동작).

---

## v1.1.46 (2026-04-12)

### 변경 — TTS 모델/목소리 선택을 프로젝트 설정으로 이관

사용자 요구: "음성 TTS 모델 목소리 선택 도 프로젝트 설정으로 옮기자."

기존에는 **TTS 모델** 선택이 두 곳(프로젝트 설정 + 음성 생성 스텝)에 있었고
**목소리 선택** 은 음성 생성 스텝에만 있었다. 한 프로젝트를 만들 때 모델과
목소리를 결정하는 맥락이 설정 화면에 모여 있지 않아서 왔다갔다 해야 했다.
이제 두 가지 모두 프로젝트 설정(`StepSettings`) 으로 완전히 이관된다.

**1. VoiceSelector 컴포넌트 추출** — `frontend/src/components/studio/VoiceSelector.tsx`

- 기존 StepVoice 안에만 있던 목소리 선택 드롭다운을 재사용 가능한 컴포넌트로 추출.
- Props: `projectId`, `ttsModel`, `voiceId`, `voicePreset`, `onChange(patch)`.
- ElevenLabs 모드: 백엔드 `/voice/{id}/voices` 를 호출해 계정에 있는
  실제 보이스를 ko/en/ja/other 그룹 드롭다운으로 보여준다.
- OpenAI TTS 모드: 고정 프리셋(`ko-child-boy` 등 21개) 과 `OPENAI_VOICE_MAP`
  으로 실제 voice_id(alloy/nova/...) 를 매핑.
- 상태 저장은 직접 수행하지 않고 `onChange(patch)` 로 부모에게 전달해 부모가
  local config state 에 반영하도록 했다. StepSettings 의 "저장" 버튼이
  한 번에 영속화하는 기존 패턴과 맞아떨어진다.

**2. 백엔드 — `/voice/{id}/voices` 에 `tts_model` 쿼리 파라미터 추가**

`backend/app/routers/voice.py`:
- `list_voices()` 에 `tts_model: Optional[str] = Query(None)` 추가.
- 프로젝트 설정 화면에서 사용자가 모델 드롭다운을 바꿨지만 아직 저장 버튼을
  누르지 않은 경우, 새 모델의 보이스 목록을 즉시 보려면 저장된 config 의
  `tts_model` 이 아닌 로컬 편집값을 서버에 보낼 필요가 있다.
- 값이 없으면 기존처럼 `project.config["tts_model"]` 을 사용한다 (기존 호출 호환).

**3. 프런트 — `voiceApi.listVoices(id, ttsModel?)` 시그니처 확장**

`frontend/src/lib/api.ts`:
- 두 번째 파라미터 `ttsModel?: string` 추가. 존재할 때만 `?tts_model=…` 쿼리를 붙인다.
- VoiceSelector 는 현재 편집 중인 `ttsModel` 을 항상 넘긴다.

**4. StepSettings — AI 모델 섹션에 목소리 선택 추가 + 모델 변경 훅**

`frontend/src/components/studio/StepSettings.tsx`:
- 기존 2-col `AI 모델 선택` 그리드에 `<VoiceSelector />` 셀 추가 (총 5셀).
- `changeTtsModel()` 신설: 모델을 바꾸면 `tts_voice_id` 와 `tts_voice_preset`
  을 빈 문자열로 리셋. VoiceSelector 가 fetchVoices 후 첫 번째 보이스로 자동
  채우거나, OpenAI TTS 기본 프리셋으로 표시만 된다.
- `applyVoicePatch()` 신설: VoiceSelector 가 돌려주는 patch 를 local config
  state 에 병합한다. 저장은 기존 "저장" 버튼이 한 번에 처리.

**5. StepVoice — 모델/목소리 UI 제거, 생성·재생성·미리듣기·진행률에 집중**

`frontend/src/components/studio/StepVoice.tsx`:
- `VOICE_PRESETS`, `OPENAI_VOICE_MAP`, `inferVoiceLangCode`, `ApiVoice`,
  `VoicePreset` 타입 전체 제거 (VoiceSelector 로 이사).
- `apiVoices`, `voicesLoading`, `voicesError`, `voiceDropdownOpen`,
  `selectedPreset` 상태 제거.
- `fetchVoices`, `changeModel`, `changeVoicePreset`, `changeVoiceDirect`,
  `previewApiVoice` 핸들러 제거.
- 기존 `grid-cols-3` (Model + Voice + Cost) 블록 → 간단한 한 줄 툴바로 교체:
  현재 선택된 TTS 모델 이름 + voice_id + 미리듣기 버튼 + 비용 요약.
- 툴바에 `모델/목소리는 프로젝트 설정에서 변경합니다` 안내 문구 표시.
- `modelsApi.listTTS()` 호출은 유지 (비용 계산용 `cost_value` 조회 때문).

### 사용자 체감 결과

- 프로젝트를 만들 때 **설정 화면 한 곳** 에서 LLM / 이미지 / 영상 / TTS 모델 /
  목소리 / 음성 속도를 모두 결정하고 "저장" 한 뒤 다음 스텝으로 넘어갈 수 있다.
- 음성 생성 스텝은 "전체 생성 / 이어서 생성 / 재생성" 이라는 핵심 기능에 집중.
- StepSettings 에서 모델을 바꾼 직후에도 아직 저장 전이지만 해당 모델의 실제
  목소리 목록이 드롭다운에 떠서 선택할 수 있다 (tts_model 쿼리 파라미터 덕분).

### 호환성

- 기존 프로젝트 DB 의 `config.tts_model` / `tts_voice_id` / `tts_voice_preset` /
  `tts_voice_lang` 필드는 그대로 사용된다 (스키마 변경 없음).
- `/voice/{id}/voices` API 는 `tts_model` 쿼리 파라미터가 **옵션** 이라
  기존 호출자(예: StepVoice) 도 계속 호환되지만 v1.1.46 에서는 사용처가 없다.

### 알려진 주의사항

- 모델을 바꾸면 `tts_voice_id` 와 `tts_voice_preset` 이 리셋된다. ElevenLabs →
  OpenAI TTS 전환 같은 경우 기본 voice 가 첫 번째 값으로 자동 설정된다. 구체
  voice 를 유지하고 싶다면 모델 변경 후 드롭다운에서 다시 선택해야 한다.
- StepSettings 의 "저장" 버튼을 누르지 않으면 선택이 프로젝트에 반영되지 않는다.
  기존 StepVoice 의 즉시 저장 방식과 다르므로, 모델·목소리를 바꾼 뒤에는 반드시
  저장해야 음성 생성이 새 설정으로 동작한다.

---

## v1.1.45 (2026-04-12)

### 변경 — 컷당 영상 길이 5초 고정 (시간 계산 + 자막 싱크)

사용자 요구: "무조껀 영상당 5초 여야 되. 음성은 4초쯤 정도여야겠지? 이런식이면 시간계산 안되고 자막 싱크도 안맞자나."

v1.1.44 까지는 각 컷의 길이가 **TTS 음성 길이에 따라 제각각** 이었다 (`duration = cut.audio_duration or 5.0`).
120컷 런에서 평균 음성 길이가 3.7초였기 때문에 최종 병합본이 7분 24초 (444초) 가 되어
"5초 × 120 = 10분" 이 맞지 않았고, 자막 싱크도 컷마다 간격이 달라 계산이 어려웠다.

**1. CUT_VIDEO_DURATION 상수 도입**

`backend/app/config.py`:
- `CUT_VIDEO_DURATION = 5.0` 추가. 모든 비디오/자막/병합 로직이 이 상수를 본다.
- 값만 바꾸면 파이프라인 전체가 따라 바뀐다 (6초/8초 등 미래 변경 대비).

**2. video.py — 컷 생성 시 무조건 5초**

- `generate_all_videos_async` / `resume_videos_async` / 레거시 `generate_all_videos`:
  `duration=cut.audio_duration or 5.0` → `duration=CUT_VIDEO_DURATION` 로 교체.

**3. ffmpeg_service.py — `-shortest` 제거, `apad` + `-t` 로 고정 길이**

- 과거: `-shortest` 가 음성 길이에 맞춰 영상을 짧게 잘라냈다.
- 지금: `-af apad` 로 음성을 무한 무음 패딩 → `-t {duration}` 로 영상을 정확히 5초로 trim.
- 음성이 5초보다 길면 `-t` 가 자른다 (뒤쪽 자음이 잘릴 수 있음 — 대본 단계에서 관리).
- 음성이 5초보다 짧으면 뒤에 무음이 붙고 영상은 끝까지 재생된다.
- 적용 대상: `FFmpegService.generate()` / `FFmpegStaticService.generate()` (audio 분기).

**4. fal_service.py — mux 파이프라인 동일 규칙 적용**

- fal.ai 가 반환하는 5초 클립을 음성과 합칠 때:
  - `-shortest` 제거
  - `-af apad` 로 음성 무음 패딩
  - `-t CUT_VIDEO_DURATION` 으로 정확히 5초 고정
- fal.ai 요청 payload 의 `"duration"` 도 하드코딩 `"5"` 에서 `str(int(round(CUT_VIDEO_DURATION)))` 로 교체 — 상수와 sync.

**5. subtitle_service.py — 컷 경계는 고정, 문장 분포는 실제 음성 길이**

자막 싱크 로직은 두 가지 구간을 구분해야 한다:
- **컷 창(cut window)**: 5초 고정. 다음 컷 시작 시각을 계산할 때 쓴다.
- **발화 구간(speech span)**: 실제 음성 길이. 이 안에서 문장들을 균등 분배.

변경:
```
old:  current_time += duration            # duration = actual_duration, 가변
new:  current_time += CUT_VIDEO_DURATION  # 항상 5초씩 전진
```

문장별 `Dialogue` 줄의 start/end 는 `current_time` 부터 발화 구간 안쪽에 찍힌다.
음성이 3.7초면 3.7초 안에 문장들이 끝나고, 뒤 1.3초는 자막 없음 + 무음.

**6. interlude.py — intermission 위치 계산도 5초 × N 으로**

`build_interlude_sequence` 의 accumulator 가 `audio_duration` 으로 누적하고 있었던
것을 `CUT_VIDEO_DURATION` 으로 교체. 이제 "5분마다 intermission" 같은 규칙이 컷 수 기준으로 정확히 동작.

### 사용자 체감 결과

- 120컷 → 정확히 **600초 (10분 00초)** 병합.
- 자막 시작 시각 = `(cut_number - 1) × 5.0`. 소수점 오차 없음.
- 음성 ~4초, 뒤 ~1초 무음 — 사용자 요구사항 그대로.

### 호환성

- DB 스키마 변경 없음. `cut.audio_duration` 컬럼은 여전히 기록되지만 병합/자막 로직에서는 **참조만** 하고 길이 기준으로 쓰지 않는다 (subtitle sentence 분배 한정).
- 기존 프로젝트는 영상 스텝 재실행으로 5초 고정 버전으로 재생성 가능.
- 프런트엔드 변경 없음 (버전 번프만).

### 알려진 주의사항

- 음성이 5초를 넘으면 `-t` 로 자르므로 문장 끝이 잘린다. TTS 프롬프트/대본에서 컷당 글자수를 제한하는 게 근본 해결책.
- `apad` 는 디지털 무음(0)을 붙이므로 일부 오디오에서 노이즈 플로어 변화로 클릭이 들릴 수 있음 — 실제 발생 시 crossfade 로 교체 필요.

---

## v1.1.44 (2026-04-12)

### 변경 — 영상 생성 자동 폴백 + 4컷 병렬 실행 + 사전 잔액 체크

사용자 요구: "에러가 절대 나지 않는 방법을 마련해. 그리고 너무 느리다 영상생성이 대체 방안 마련해봐."

v1.1.43 런에서 fal.ai 잔액이 120컷 중 87컷 시점에 소진돼 33컷이 한 번에 빨간 "failed" 로 터졌다.
또 컷이 직렬 처리라 60~120분이 걸렸다. 이 두 문제를 한 번에 고친다.

**사전 고지**: "에러가 절대 안 난다" 는 글자 그대로는 불가능하다 (네트워크/디스크/ffmpeg 자체 실패 등).
여기서는 **사용자가 빨간 에러 화면을 마주치지 않도록** 모든 경로에 자동 폴백을 건다.

**1. fal.ai submit 재시도 추가**

`backend/app/services/video/fal_service.py`:
- `_post_with_retries` 정적 메서드 신설. 기존 `_get_with_retries` 와 동일한 정책:
  - HTTP 409/429/5xx → 지수 backoff 2s → 4s → 8s, 최대 4회
  - 401/403/404/400 → 영구 에러, 즉시 반환 (호출자가 raise)
  - TransportError/Timeout → 네트워크 재시도
- 과거엔 submit 한 번이 일시적 5xx 로 터지면 그 컷이 즉시 죽었다.

**2. 사전 잔액/키 체크 (preflight probe)**

`backend/app/routers/video.py` — `_preflight_fal_probe(video_model)`:
- `video_model` 이 fal 계열이면 `api_status._probe_fal_video_model` 로 dummy status GET.
- 401/403/잔액 소진/timeout → `force_full_fallback=True` 로 전체 런을 **ffmpeg-kenburns** 로 전환.
- 키 정상이면 primary 그대로 사용.
- probe 자체가 예외를 던져도 안전하게 ffmpeg 로 떨어뜨린다.

**3. 자동 폴백 헬퍼 `_generate_one_cut_safe`**

한 컷을 생성하는 통합 진입점. source tag 로 실제 사용 경로를 돌려준다:
- `"ai"` — primary (seedance 등) 가 성공
- `"ai_fallback_kenburns"` — primary 실패 후 kenburns 로 성공
- `"ffmpeg_forced"` — 사전 체크/런 중 primary 불가 판정으로 kenburns 강제
- `"ffmpeg_selection"` — selection(every_N/character_only) 에 의해 원래부터 static

primary 가 실패했을 때 `_is_terminal_primary_error` 로 에러 문자열에서
"HTTP 401/403/Exhausted balance/User is locked" 를 감지하면 공유 플래그
`primary_disabled` 를 세워 남은 컷들은 primary 재시도를 건너뛴다 — 잔액 소진
감지 후 낭비되는 retry 시간 0.

**4. 4컷 동시 실행 (asyncio.Semaphore)**

`generate_all_videos_async` / `resume_videos_async` 의 직렬 for-loop 을
`asyncio.gather` + `asyncio.Semaphore(VIDEO_PARALLELISM=4)` 로 교체.
- 모든 컷의 워커를 한 번에 `create_task` 로 띄우지만 Semaphore 가 실제 동시 수를 4개로 고정.
- 네트워크 bound 작업이라 병렬화 이득이 크다. 120컷 기준 60~120분 → 약 15~30분 기대.
- 각 워커는 자체 `SessionLocal` 을 열어 SQLAlchemy 스레드 이슈 회피.
- 진행률 카운터는 공유 `completed_counter` 로 단조 증가 (완료/실패 무관).
- 최종 merge 순서는 `cut_results[cut_number]` 를 정렬해 보장.

**5. 결과 태깅**

`cut.video_model` 컬럼에 실제 사용된 소스가 기록된다:
- `"seedance-lite"` — 원래 모델
- `"ffmpeg-kenburns (auto-fallback)"` — 개별 컷 폴백
- `"ffmpeg-kenburns (preflight-fallback)"` — 사전 체크 실패로 강제 폴백
- `"ffmpeg-static"` — selection 미선택

서버 로그에 `[video-async] SUMMARY ai=... ai_fallback_kenburns=... ffmpeg_forced=... failed=...`
한 줄이 찍혀 얼마나 폴백으로 채웠는지 사용자가 확인 가능.

**호환성**

- API 변경 없음. 프런트엔드는 수정할 게 없다 (version 만 번프).
- DB 스키마 변경 없음. `cut.video_model` 컬럼에 문자열이 조금 더 길어질 뿐.
- 기존 프로젝트는 아무 조치 없이 다음 런부터 자동으로 병렬 + 폴백 적용.

---

## v1.1.43 (2026-04-12)

### 변경 — 딸깍 주제 큐 + 매일 HH:MM 자동 실행 재도입

사용자 요구: "딸깍제작 주제 입력 리스트 만들고 매일 몇시에 시작 할지 입력 할 수 있게해."

v1.1.42 에서 "인스턴트 1 건 입력" 으로 갔던 딸깍 UI 를 **주제 큐 편집기** 로 교체.

**1. 주제 큐 데이터 모델**

- 각 큐 항목: `{id, topic, template_project_id, target_duration}` — 주제마다 프리셋/길이 개별 지정
- 저장 위치: `DATA_DIR/oneclick_queue.json` (JSON 파일, 프로세스 재시작에도 복원)
- 스키마 변경 없음

**2. 발화 규칙**

- 30 초 간격 `_queue_loop` 가 `daily_time` HH:MM 을 감시
- 오늘 지정 시각을 지났고 `last_run_date ≠ 오늘` 이면 큐 맨 위 1 건을 pop → `prepare_task` → `start_task`
- 성공/실패 무관하게 pop-on-start (일회성 소비 시맨틱)
- `last_run_date` 는 큐가 비어 있어도 시간 조건만 충족하면 "오늘 점검 완료" 로 표기 → 내일까지 대기 (사용자 요구 "조용히 대기")
- 서버가 HH:MM 에 죽었다가 늦게 올라와도 오늘 안 돌았으면 catch-up 즉시 발화

**3. 새 엔드포인트 (`routers/oneclick.py`)**

- `GET /api/oneclick/queue` — 현재 큐 상태 + daily_time
- `PUT /api/oneclick/queue` — 큐 전체 교체 (프론트 "저장")
- `POST /api/oneclick/queue/run-next` — 맨 위 1 건 즉시 pop 실행

**4. OneClickWidget 재작성 (모달 = 큐 편집기)**

- 모달 상단: `<input type="time">` 으로 매일 실행 시각 설정 (빈 값 = 스케줄 꺼짐)
- 본체: 주제 row 리스트 — 각 row 마다 `[주제] [프리셋 select] [길이(분)] [X 제거]`
- "+ 주제 추가" 로 새 row 생성
- 실행 중인 태스크가 있으면 모달 상단에 진행률 배너 + 중지 버튼
- 푸터: "저장" / "지금 1 건 실행"
- 버튼 자체는 여전히 진행률(`진행 중 N%`) 을 표시

**5. 백엔드 생명주기**

- `main.py` 의 FastAPI `lifespan` 에서 `start_queue_scheduler` / `stop_queue_scheduler` 호출
- v1.1.42 에서 없애버렸던 스케줄러 루프가 "주제 큐" 라는 완전히 다른 모델로 복귀

### 삭제 / 폐기

- v1.1.42 의 "즉시 실행 1 건 입력" UI (`InputView` / `RunningView` / `FinishedView` 서브 뷰) 제거. 대신 큐 편집기 단일 뷰.
- 프론트의 즉시 실행 API 자체(`prepare`, `start`) 는 유지 — `run-next` 가 내부적으로 사용.

### 호환성

- SQLite 스키마 변경 없음
- v1.1.42 의 `/api/oneclick/prepare` / `/api/oneclick/{task_id}/start` 엔드포인트는 그대로 유지 (내부에서 호출)
- 기존 진행 중 태스크 폴링 경로(`/api/oneclick/tasks`) 변경 없음
- 첫 기동 시 `DATA_DIR/oneclick_queue.json` 이 없으면 빈 큐 + 스케줄 꺼짐 상태로 시작

---

## v1.1.42 (2026-04-12)

### 변경 — 자동화 스케줄 전면 삭제, 딸깍 제작은 "버튼 + 팝업" 으로 재설계

사용자 요청: "딸깍 셋팅하면 프리셋이 생성되네? 이럼 안되지. 이건 아니야. 이런 방식이 아니야. 딸깍은 인스턴트야. 프리셋이 중요한거라고. 딸깍 제작은 팝업띄우자. 팝업 띄워서 주제 넣고 시간 넣으면 순차적으로 진행하게 해. 자동화 스케쥴 삭제하고 그자리에 버튼 넣어."

이전(v1.1.41 까지) 의 동작:

- 대시보드 안에 거대한 "딸깍 제작" 카드가 인라인으로 박혀 있고, 거기서 "프리셋 선택 → 주제/제목 입력 → 저장 → 예상 비용 확인 → 시작" 이라는 다단계 플로우를 거쳐야 했음.
- 저장 버튼을 누르는 순간 백엔드가 템플릿 프로젝트를 **복제해 새로운 Project 행을 DB 에 만들었음** (`_clone_project_from_template`). 그 결과 대시보드의 "프리셋 목록" 이 딸깍 실행마다 한 줄씩 오염됨. 사용자 관점에서는 "딸깍 눌렀는데 왜 프리셋 목록이 늘어나지?" 라는 상태.
- 별도로 두 가지 자동화 스케줄이 있었음: (a) `/schedule` 페이지의 17-row EP 그리드, (b) OneClickWidget 내부의 "매일 HH:MM 자동 실행" 패널.

v1.1.42 에서 바뀐 것:

**1. 딸깍 = 인스턴트 팝업**

- `OneClickWidget.tsx` 가 인라인 카드에서 **버튼 + 모달** 로 재작성됨. 평시에는 보라색 "딸깍 제작" 버튼 하나만 노출. 클릭하면 모달이 뜨고, 모달 안에서 `프리셋` (선택) / `주제` / `시간(분)` 세 필드만 입력하면 됨.
- 제작 시작 버튼 한 번으로 `prepare` 와 `start` 가 연달아 호출되어 대본→음성→이미지→영상→렌더링이 즉시 순차 실행됨. "예상 비용 확인" 중간 단계는 삭제 — 인스턴트라는 컨셉에 부합하지 않음.
- 진행 중에는 같은 버튼이 `Loader2` 스피너 + 진행률 % 로 바뀌어 한눈에 보이고, 다시 누르면 모달이 열려 현재 태스크의 상세 진행 상태를 표시. 모달을 닫아도 백엔드 태스크는 계속 돔. 대시보드를 벗어났다가 돌아와도 mount 시 `/api/oneclick/tasks` 를 조회해 running 태스크를 자동 복구함.

**2. 프리셋 목록 오염 해소**

- `_clone_project_from_template` 가 만드는 Project 행에 `config["__oneclick__"] = True` 마커를 추가.
- `GET /api/projects` (대시보드 프리셋 목록) 에서 이 마커가 켜진 행을 자동 제외. 파이프라인 스텝 함수들이 DB 에 Project 가 있어야 동작하므로 행 자체는 여전히 만들되, UI 에서만 숨김. 이로써 딸깍을 백 번 눌러도 프리셋 목록은 오염되지 않음.
- 기존에 누적된 오염 데이터는 자동 정리하지 않음 — 필요하면 사용자가 대시보드에서 수동 삭제. (신규 생성분부터만 필터링됨.)

**3. "시간" 입력 = 목표 영상 길이**

- `oneclickApi.prepare()` 와 백엔드 `prepare_task` 가 `target_duration` (초) 파라미터를 받음. 모달의 "시간 (분)" 입력값이 여기로 전달되어 새 클론 프로젝트의 `config["target_duration"]` 에 반영됨. 프리셋을 선택하면 해당 프리셋의 기본 target_duration 이 자동으로 초기값으로 채워짐.
- 주의: "시간" 은 업로드 **시각(time-of-day)** 이 아니라 영상 **길이(duration)**. 딸깍에는 더 이상 시각 개념이 없음 — 인스턴트니까.

**4. 자동화 스케줄 완전 삭제**

- `frontend/src/app/schedule/page.tsx`: 17-row EP 그리드 UI 제거. 파일 자체는 남겼지만 진입 즉시 `/` 로 리다이렉트하는 스텁으로 교체 (북마크/히스토리 보호용).
- `frontend/src/lib/api.ts`: `scheduleApi`, `ScheduleItem`, `ScheduleItemInput`, `SchedulePrivacy`, `ScheduleStatus`, `OneClickSchedule`, `OneClickScheduleUpdate`, `oneclickApi.getSchedule`, `oneclickApi.updateSchedule` 모두 삭제.
- `frontend/src/app/studio/[projectId]/page.tsx`: 스튜디오 상단바의 `<a href="/schedule">스케줄</a>` 링크 삭제, 사이드바의 "자동화 스케줄" 카드 삭제.
- `frontend/src/app/page.tsx`: 대시보드 상단의 `<a href="/schedule">자동화 스케줄</a>` 버튼 삭제. 그 자리에 `<OneClickWidget />` (= 딸깍 버튼) 배치. 딸깍 카드는 본문에서 완전히 빠지고 상단바로만 노출됨.
- `backend/app/main.py`:
    - `schedule` 라우터 import 및 `include_router` 삭제 → `/api/schedule/*` 엔드포인트 사라짐.
    - `scheduler_service.start_scheduler/stop_scheduler` 호출 삭제 → 17-row EP 루프 기동 안 함.
    - `oneclick_service.start_scheduler/stop_scheduler` 호출 삭제 → 매일 HH:MM 자동 실행 루프 기동 안 함.
- `backend/app/routers/oneclick.py`: `ScheduleUpdateRequest` 와 `GET/PUT /schedule` 엔드포인트 삭제.
- `backend/app/services/oneclick_service.py`: 스케줄러 서브시스템 (~200 줄, `_SCHEDULE_FILE`, `_SCHEDULE`, `_load_schedule_from_disk`, `_save_schedule_to_disk`, `_compute_next_run`, `get_schedule`, `set_schedule`, `_trigger_scheduled_run`, `_schedule_loop`, `start_scheduler`, `stop_scheduler`) 전면 삭제. `prepare_task` 가 `target_duration` 파라미터를 받는 것도 여기.

**삭제하지 않고 남겨둔 것**

- `backend/app/routers/schedule.py`, `backend/app/services/scheduler_service.py`, `backend/app/models/scheduled_episode.py` 파일 자체는 디스크에 그대로 남김. main.py 가 더 이상 import 하지 않으므로 dead code 이고, 다른 곳에서 참조하는 것도 없어 컴파일/기동에는 아무 영향 없음. 물리 삭제는 다른 곳에서 우연히 참조될 때의 리스크를 피하기 위해 이번 릴리스에서 보류. 다음 릴리스에서 제거 예정.
- `data/oneclick_schedule.json` 파일이 로컬에 남아 있을 수 있음. 새 코드는 이 파일을 읽지도 쓰지도 않으므로 무해한 유물 — 원하면 사용자가 수동 삭제.

**호환성**

- 이미 진행 중이던 딸깍 태스크가 있으면 그대로 계속 달림 — 백엔드 `_TASKS` 레지스트리는 그대로.
- 기존에 자동화 스케줄에 등록돼 있던 항목은 더이상 실행되지 않음. 사용자가 의도한 바.
- 프리셋 목록에 이미 섞여 있던 과거 딸깍 프로젝트들은 여전히 보임 (마커가 없으므로). 필요하면 대시보드에서 직접 삭제.

## v1.1.41 (2026-04-12)

### 버그 수정 — 긴 영상 생성이 중간에 멈추는 현상 + 다른 스텝 탭으로 가면 진행 상태가 안 보이는 문제

사용자 요청: "영상 생성이 왜자꾸 멈추는 거 같지? 한번 시작하면 페이지 변경 되도 계속 진행 되게 해. 중지 누를때까진 계속 진행."

**원인 1 — `task_manager.is_running` 의 30분 auto-expire**

`backend/app/services/task_manager.py::is_running` 은 진행 중인 태스크의 상태를 읽으면서, 만약 `state.started_at` 으로부터 30분이 지났으면 "스턱 태스크" 로 간주해 `state.status = "failed"` 로 바꾸고 asyncio.Task 를 취소함. 이 판단이 들어간 초기 의도는 "태스크가 진짜로 멈췄는데 메모리에 running 상태가 남아있으면 사용자가 새 태스크를 시작 못함" 이었음.

문제: 120 컷짜리 롱폼을 Fal.ai 영상 모델로 생성하면 컷당 30~60초가 걸려 전체 1~2시간이 소요됨. 30분 경계가 오자마자 아직 멀쩡히 돌고 있는 태스크가 실패 처리 → `_run` 루프의 `if state.status != "running": break` 가 작동 → 루프 중단 → 나머지 컷이 전부 유실. 사용자에게는 "영상 생성이 알아서 멈춤" 으로 보임.

**원인 2 — 다른 스텝 탭으로 이동하면 진행 상태가 UI 에서 사라짐**

StepVideo/StepImage/StepVoice 의 `GenerationTimer` 컴포넌트는 해당 스텝 안에만 렌더링되므로, 사용자가 StepSettings/StepScript 등으로 이동하면 "진행 중" 표시가 사라짐. 사용자 체감으로는 "페이지 바꾸니까 멈춘 것 같다". 실제 백엔드에선 돌고 있음에도.

**수정**

`backend/app/services/task_manager.py::is_running`:

- Hard ceiling 30분 → **6시간**. 현실적 최대 소요시간 (120 컷 × 2분 = 4시간) 을 여유 있게 커버.
- 만료 판단 앞에 **asyncio.Task done 리컨사일** 추가. 기저 태스크가 이미 done() 이면 — 즉, 크래시 / 프로세스 재시작 / hot reload 로 정말 죽었으면 — 즉시 `state.status = "failed"` 로 바꾸고 dangling running 상태를 해소함. 6시간 기다릴 필요 없이. 이 덕분에 진짜로 죽은 태스크는 빨리 치우고, 멀쩡히 돌고 있는 태스크는 6시간까지 절대 건드리지 않음.

`frontend/src/app/studio/[projectId]/page.tsx`:

- 최상단 top bar 바로 아래에 `GenerationTimer` 3 개 (voice/image/video) 를 글로벌 영역에 배치. 어느 스텝 탭에 있든 진행 중인 작업이 있으면 배너가 표시되고, 거기서 바로 중지 버튼을 누를 수도 있음.
- `GenerationTimer` 는 서버 상태가 `running` 아닐 때 `null` 을 반환하므로, 작업이 없을 땐 배너 영역이 `empty:hidden` 으로 완전히 사라져서 UI 에 여백도 안 남음.

**호환성**

- 기존 프로젝트에 영향 없음. 설정/DB/파일 스키마 변경 없음.
- v1.1.40 까지 30분 auto-expire 에 걸려 실패 처리된 과거 태스크 상태는 그대로 유지 (굳이 되돌릴 이유 없음).

**주의할 점**

- 6시간이라는 새로운 상한선은 여전히 "완전히 고장난 태스크" 를 청소하기 위한 안전망. 이걸 넘어가는 비정상 상황은 사용자 수동 개입 영역.
- 정상적으로 끝나는 태스크는 `complete_task` / `fail_task` 가 즉시 상태를 갱신하므로 6시간 대기 같은 건 발생하지 않음.

## v1.1.40 (2026-04-12)

### 변경 — 영상 폴백에서 켄번 효과 제거

사용자 요청: "나머지에 켄번 효과 느치 말라고." 영상 제작 대상 선택 모드 (예: 4 컷당 1 컷만 AI 영상 모델로 생성) 에서 **선택되지 않은 나머지 컷** 에 자동으로 적용되던 FFmpeg Ken Burns 줌/팬 효과를 제거. 이제 미선택 컷은 모션 0 의 정지 이미지 영상으로 출력.

배경: v1.1.36 에서 영상 모델 비용 절감용으로 "영상 제작 대상 선택" 기능을 도입했을 때, 미선택 컷의 폴백을 기존 `ffmpeg-kenburns` 로 자동 지정했음 — 비용 0 이라는 점만 보고 효과 차원은 고려 안 했던 결정. 결과적으로 사용자가 "AI 영상 컷"과 "Ken Burns 컷"이 섞인 영상을 받게 됐고, Ken Burns 의 자동 줌 인/아웃이 의도된 시각 디자인이 아니라 어색하게 들어간다는 피드백.

수정:

- `backend/app/services/video/ffmpeg_service.py`: 새 클래스 `FFmpegStaticService` 추가. 기존 `FFmpegService` 와 동일한 입출력 인터페이스를 따르되, FFmpeg `vf` 필터에서 `zoompan` 을 빼고 `scale + pad + setsar + fps=30 + format=yuv420p` 만 적용. 한 컷이 정확히 1 장의 정지 이미지 + 오디오로 구성됨. 인코딩은 `libx264 -preset ultrafast -crf 23` — Ken Burns 보다 살짝 더 빠름 (zoompan 이 빠지면서 컷당 약 0.6s 로 단축, 기존 0.8s).
- `backend/app/services/video/factory.py`: `VIDEO_REGISTRY` 에 `ffmpeg-static` 모델 등록 (provider `local-static`, cost 0). 사용자가 "주 모델" 드롭다운에서 명시적으로 고를 수도 있긴 하지만, 본 기능의 1차 목적은 폴백.
- `backend/app/routers/video.py`: 동기/비동기 두 생성 경로 모두 폴백 모델 이름을 `ffmpeg-kenburns` → `ffmpeg-static` 으로 교체. `used_model` 기록도 같이 변경.
- `backend/app/services/estimation_service.py`: 비용/시간 추정에서 폴백 컷 부분을 `ffmpeg-static` 기준으로 산정. cost 는 동일 (0), 시간만 컷당 0.8s → 0.6s 로 살짝 단축.

**왜 새 서비스인가 (기존 `FFmpegService` 수정 안 함)**

기존 `FFmpegService` 가 Ken Burns 효과의 유일한 구현이라, 그걸 그냥 무효화하면 사용자가 "주 모델"로 Ken Burns 를 명시 선택한 경우에도 효과가 사라짐. 폴백 경로만 떼어내려면 별도 클래스가 가장 깔끔. 두 서비스는 같은 파일 안에 두되 책임이 명확히 분리됨 — `FFmpegService` = 의도된 줌/팬 효과, `FFmpegStaticService` = 비용 0 폴백.

**호환성**

- 기존 프로젝트의 `config.video_model` 기본값 (`ffmpeg-kenburns`) 은 그대로 유지. 주 모델 선택은 사용자 결정 영역.
- 영상 제작 대상 선택이 `all` 인 경우 폴백 경로 자체가 안 타므로 이 변경의 영향 없음.
- 기존 v1.1.36~v1.1.39 에서 생성된 영상 파일 자체엔 영향 없음. 새 변경은 앞으로 생성될 영상부터 적용.

## v1.1.39 (2026-04-12)

### 버그 수정 — Fal.ai 영상 다운로드 일시 에러 (HTTP 409) 자동 재시도

증상: 딸깍 영상 생성 중 120 컷 중 9 번 컷 하나가 `RuntimeError: Fal video download HTTP 409` 로 실패. 나머지 컷은 정상 처리됐고 Fal 쪽에선 생성 자체는 "COMPLETED" 로 응답이 왔는데, 결과물을 CDN 에서 내려받는 마지막 GET 이 409 를 반환해 그 한 컷만 죽은 상황.

원인: `app/services/video/fal_service.py::generate` 의 다운로드 단계가 **재시도 없이 단 1 회 시도만** 함. 409/429/5xx 같은 일시적 에러도 곧바로 `RuntimeError` 로 승격돼 그 컷 하나가 통째로 실패. 이미 LLM/이미지/Fal 큐 비용을 다 낸 뒤라 재생성 비용은 실질적으로 중복 지출.

409 자체는 Fal CDN 이 생성 직후 같은 URL 에 들어오는 첫 요청을 간헐적으로 거절하는 알려진 패턴. 2~8초만 기다렸다가 다시 요청하면 대부분 통과.

수정: `FalVideoService._get_with_retries` 정적 메서드 신설 — 일시 에러에 한해 exponential backoff (2s → 4s → 8s) 로 최대 4 회 재시도. 적용 기준은 이렇게 분류:

- **재시도 대상**: HTTP 409, 429, 5xx, `httpx.TransportError`, `httpx.TimeoutException`
- **즉시 실패**: 그 외 4xx (401 인증 만료, 403 권한, 404 없음, 400 잘못된 요청 등) — 재시도해도 해결 안 됨

이 헬퍼를 다음 두 호출에 적용:

1. **영상 다운로드** (`client.get(video_url)`) — 실제로 터졌던 지점. CDN URL 은 서명된 presigned 라 `Authorization` 헤더를 빼고 호출 (혹시 Fal CDN 이 서명과 Authorization 이중을 이상 처리할 가능성 차단).
2. **결과 JSON 페치** (`client.get(result_url)`) — 동일 CDN/큐 경로라 같은 부류 이슈에 노출돼 있음. 예방적 적용.

status polling 쪽 (`status_url`) 은 기존대로 유지 — 이미 5초 간격으로 최대 120 회 돌리는 자체 루프가 재시도 역할을 하므로 중복 로직 불필요.

**주의할 점**

- 재시도는 한 컷 기준 최대 14초 추가 지연. 120 컷 짜리에서 최악의 경우 4 번 연속 재시도는 매우 드물지만, 총 실행 시간이 늘어날 수는 있음 — 기존에는 실패 처리돼 컷이 사라졌던 걸 살려내는 거라 이 지연은 감수할 가치가 있음.
- Fal 큐 자체 (`submit`/`status`) 에 대한 재시도는 이번 버전에서 건드리지 않음. 그 경로는 다른 실패 패턴 (인증/요청 포맷) 이 더 흔해서 재시도가 오히려 잘못된 요청을 반복하게 만들 위험이 있음.
- `max_attempts=4` 는 임의 선택 — 2~3 회로 안 풀리는 CDN 이슈는 어차피 수동 개입이 필요한 수준.

## v1.1.38 (2026-04-12)

### 추가 — 딸깍 진행률 세부화 & 매일 자동 실행 스케줄

사용자 요청: "딸깍 시작하면 진행상황을 좀더 세밀하게 표현해 줄수 없을까? 그리고 딸깍에 옵션 하나 추가하자. 시간 입력 받게 해서 매일 몇시에 자동으로 생성하게. 활성화 버튼도 만들고." 두 가지를 한 번에 처리.

**1. 진행률 세부화 — "N/M 컷" 실시간 노출**

기존: 딸깍 실행 중 UI 가 전체 진행률 % + 현재 단계 이름만 표시. 대본/음성/이미지/영상 4 개 컷 단위 스텝이 몇 컷까지 처리됐는지는 보이지 않아서 "멈춘 건지 돌고 있는 건지" 판단 불가.

수정:

- `backend/app/services/oneclick_service.py::_compute_progress_pct` 가 부수효과로 task 레코드에 `current_step_completed` / `current_step_total` / `current_step_label` 을 채우도록 확장. 기존 Redis 카운터 (`pipeline:step_progress:{pid}:{step}`) 를 그대로 재사용 — 백엔드 데이터 파이프라인엔 손을 안 댐.
- `_make_task_record` 초기값에 이 세 필드 + `triggered_by` 추가. `triggered_by` 는 스케줄에서 트리거된 태스크를 구분하기 위한 태그.
- `frontend/src/lib/api.ts::OneClickTask` 에 동일 필드 추가 (optional).
- `frontend/src/components/studio/OneClickWidget.tsx` running phase:
  - 단계 이름 옆에 "N/M 컷" 배지 (step 2 는 대본 작성 중이라 total 이 없어 "N 컷 작성" 표시)
  - 5 개 단계 점 아래에도 각 단계별 `completed/total` 을 작게 표시 — 완료된 단계는 그대로 유지, 진행 중 단계는 실시간 증가.
  - 스케줄 트리거된 태스크에는 "스케줄" 배지를 달아 수동 실행과 구분.

**2. 매일 자동 실행 스케줄**

요구: 특정 시각을 넣으면 매일 그 시간에 딸깍이 자동으로 돌고, 활성/비활성 토글 버튼이 있어야 함.

설계 판단:

- APScheduler / cron 의존성은 추가하지 않음. 이미 `scheduler_service` 가 APS 없이 in-process loop 으로 자동화를 돌리고 있어서 동일 스타일을 유지 — `oneclick_service._schedule_loop` 이 30초 간격 polling 으로 "지금이 HH:MM 인가?" 체크. 정확도가 분 단위면 충분.
- 설정 영속화는 `data/oneclick_schedule.json` 단일 파일로 처리. DB 스키마 변경을 피함.
- 동시성: 수동 실행과 동일한 `_RUN_LOCK` 을 공유. 스케줄이 트리거해도 이미 딸깍이 돌고 있으면 뒤에서 대기 → 자원 경합 방지.
- 트리거 경로: 새 코드 패스를 만들지 않고 기존 `prepare_task` + `start_task` 를 그대로 호출. 스케줄 실행도 수동 실행과 같은 태스크 레코드가 `_TASKS` 에 쌓임.

**백엔드**

- `app/services/oneclick_service.py`:
  - `_SCHEDULE_FILE = DATA_DIR / "oneclick_schedule.json"` + `_SCHEDULE` 전역 dict
  - `_load_schedule_from_disk()` / `_save_schedule_to_disk()` — 부팅 시 로드, 변경 시 즉시 저장
  - `_compute_next_run(now)` — 오늘 시각이 지났으면 내일로
  - `get_schedule()` — `next_run_at` 포함해 즉석 반환
  - `set_schedule(...)` — 부분 업데이트, hour/minute 범위 검증
  - `_trigger_scheduled_run()` — topic 비면 스킵, 아니면 prepare+start. 결과를 `last_run_at` / `last_task_id` / `last_error` 에 기록
  - `_schedule_loop()` — 30초 polling, `last_fired_key = (Y,M,D,H,M)` 로 같은 분 중복 발화 차단
  - `start_scheduler()` / `stop_scheduler()` — lifespan 훅용
- `app/routers/oneclick.py`: `GET /schedule`, `PUT /schedule` 추가. `ScheduleUpdateRequest` Pydantic 모델
- `app/main.py` lifespan: startup 에서 `start_scheduler()`, shutdown 에서 `await stop_scheduler()`

**프론트엔드**

- `src/lib/api.ts`: `OneClickSchedule` 타입 + `oneclickApi.getSchedule/updateSchedule` 추가
- `src/components/studio/OneClickWidget.tsx`:
  - 위젯 하단에 접을 수 있는 "매일 자동 실행" 섹션 추가
  - 닫힌 상태: 활성/비활성 배지 + "다음: 09:00 (5시간 21분 후)" 요약
  - 열린 상태: HH:MM 입력, 프리셋 드롭다운, 주제 input, 마지막 실행 기록, [설정 저장] / [활성화/비활성화] 버튼
  - `formatNextRun(iso)` 헬퍼로 상대 시간 포맷. 24시간 이상 남으면 "M/D HH:MM" 폴백
  - 활성화 전 topic 공백 검증을 프론트에서 선검사

**주의할 점**

- 스케줄은 **같은 주제로 반복 실행**. 토픽 로테이션은 이번 턴 범위 밖. UI 에 "주기적으로 주제를 바꿔 주세요" 안내 포함.
- 서버가 꺼져 있으면 트리거 안 됨. 백그라운드 서비스 등록은 사용자 책임.
- 타임존은 로컬 시간 기준 (`datetime.now()`) — 사용자가 KST 환경이라 무해.

## v1.1.37 (2026-04-12)

### 버그 수정 — `load_script` cp949 UnicodeDecodeError (음성 스텝)

증상: 딸깍 실행 중 음성 스텝에서 `UnicodeDecodeError: 'cp949' codec can't decode byte 0xe2 in position 287: illegal multibyte sequence`. 사용자 스크린샷으로 확인.

원인: `app/tasks/pipeline_tasks.py::load_script` 가 `with open(path) as f:` 로 encoding 을 지정하지 않음. Windows 환경에서 `open()` 의 기본 encoding 은 locale 의존 (한국어 로케일 = cp949). `save_script` 는 `encoding="utf-8", ensure_ascii=False` 로 한글/특수문자를 UTF-8 로 저장하므로 읽는 쪽 기본 cp949 와 불일치 → 첫 UTF-8 multi-byte 문자(em-dash 등 0xe2 시작 시퀀스) 만나자마자 터짐.

v1.1.34 의 딸깍 경로가 동일한 `load_script` 를 재사용해서 문제가 음성 스텝에서 표면화. 기존 수동 작업 흐름에서도 동일 버그가 잠복 중이었을 가능성.

수정: `app/tasks/pipeline_tasks.py::load_script` 를 `open(path, "r", encoding="utf-8")` 로 교체. 해당 파일의 `save_script` 와 입출력 쌍이 맞아떨어짐.

검사: grep 으로 백엔드 전체 `open(...)` 호출을 훑어 다른 잠재적 지뢰 여부 확인. 텍스트 경로는 모두 `encoding="utf-8"` 명시 또는 바이너리 모드 (`"rb"`/`"wb"`) 라 이 한 곳이 단일 누락이었음.

### 버그 수정 — 딸깍 `/oneclick/{task_id}/start` 500 RuntimeError

증상: `HTTP 500 POST /oneclick/26664a23/start: start 실패: RuntimeError: There is no current event loop in thread 'AnyIO worker thread'.`

원인: `oneclick.start()` 라우터가 `def` (sync) 로 선언돼 있어서 FastAPI 가 AnyIO worker thread 에서 실행. worker thread 엔 이벤트 루프가 없음. 이 상태로 `oneclick_service.start_task()` 가 `asyncio.get_event_loop()` 를 호출하니 RuntimeError. v1.1.34 에서 코드를 짤 때 "라우터에선 당연히 loop 가 있을 것" 이라고 가정했던 게 문제.

수정:

- `app/routers/oneclick.py::start` 를 `async def` 로 변경. FastAPI 메인 이벤트 루프 위에서 직접 실행되게.
- `app/services/oneclick_service.py::start_task` 에서 `asyncio.get_event_loop()` → `asyncio.get_running_loop()`. 실수로 sync 컨텍스트에서 호출되면 즉시 실패하도록 의도를 명확히 표현.

prepare/cancel 는 async 호출이 없어서 sync 유지해도 무해. `_RUN_LOCK = asyncio.Lock()` 모듈 레벨 선언은 Python 3.10+ 에서 지연 바인딩이라 문제 없음.

### 변경 — 딸깍 제작 위젯을 대시보드로 이동, 프로젝트를 "프리셋" 개념으로 재프레이밍

사용자 피드백: "프로젝트는 그냥 프로젝트고 딸깍은 그냥 딸깍인건데. 딸깍제작은 대시보드로 옮기고. 프로젝트는 프리셋같은 개념으로 가야해." 구조를 정리: 대시보드 = 딸깍 실행 + 프리셋 목록, Studio = 프리셋 편집 + (원할 때) 수동 작업. DB 스키마 자체는 이번 턴에서 건드리지 않고 UI / 용어 레이어만 먼저 정리합니다. 별도 엔티티 (preset vs run) 로의 실제 분할은 v1.1.38 이후에서 진행 예정.

**Frontend — `src/app/page.tsx` (대시보드)**

- 상단 헤더 아래 설명문을 "프로젝트는 프리셋, 아래 딸깍 제작에서 프리셋 하나를 골라 주제만 넣으면 자동으로 새 영상이 만들어집니다" 로 교체 → 신규 유저가 첫 화면에서 용어를 이해하도록.
- API 상태 패널 바로 위에 `<OneClickWidget />` 을 배치 → 메인 액션이 됨.
- "New Project" 섹션을 "프리셋 목록" 소제목 + "새 프리셋" 버튼으로 리네이밍.
- 프로젝트 목록 텅 빈 상태 카피, 삭제 확인 카피 모두 "프로젝트" → "프리셋" 으로 교체.

**Frontend — `src/components/studio/OneClickWidget.tsx`**

- 헤더 주석을 "v1.1.37: 대시보드로 이동" 으로 갱신.
- idle phase 를 가로 12-grid 로 재배치 (프리셋 4 / 주제 5 / 제목 3 / 버튼은 그 아래 full-width). 기존 세로-스택 narrow-sidebar 디자인은 대시보드에선 답답해서 수정.
- 내부 글꼴 크기를 `text-[11px]` → `text-sm` 으로 올려 메인 액션에 걸맞는 무게감.
- `mt-4` 제거, `mb-8` 추가 (대시보드 맥락의 여백).
- "템플릿 프로젝트" 라벨 → "프리셋".

**Frontend — `src/app/studio/[projectId]/page.tsx`**

- 사이드바의 `<OneClickWidget />` 마운트와 import 제거. Studio 는 프리셋/수동 작업 전용으로 단순화.

### 검증

- `tsc --noEmit` → exit 0
- OneClickWidget 은 Studio 의 project context 에 의존하지 않는 self-contained 컴포넌트 (자체 projectsApi.list() 호출) 라 이동 후에도 동작에 영향 없음을 코드로 확인.

### 설계 노트 — 왜 스키마 분할을 이번 턴에 안 했는가

사용자가 AskUserQuestion 에서 "실행 결과를 별도 엔티티로" 를 선택했고 이는 명시적으로 DB 마이그레이션이 필요한 옵션입니다. 다만 schema 분할은 (a) 기존 projects 테이블의 cuts FK 이관, (b) 전체 pipeline/scheduler 경로의 project_id → run_id 변경, (c) 기존 데이터 마이그레이션 (cuts 가 있는 프로젝트는 run, 없는 프로젝트는 preset 으로 분류) 이 얽혀있어 한 턴에 안전하게 끝내기 어렵습니다. 그래서 이번 턴에는 **UI 재프레이밍** 만 하고, 실제 엔티티 분할은 다음 버전에서 `kind` / `parent_preset_id` 컬럼 추가 → 라우터 필터 → 딸깍 clone 분류 순으로 단계적으로 진행할 계획입니다. 이 방식이 롤백도 쉽고 중간 브레이크도 적음.

---

## v1.1.36 (2026-04-12)

### 추가 — 영상 제작 대상 선택 (3/4/5컷당 1장, 캐릭터만)

v1.1.35 에서 경고만 띄우고 손대지 않은 실제 원가. 사용자가 직접 비용 절감 레버를 제공하자는 방향으로 결정: "영상 스텝에 제작 대상 기능 넣자 3컷당 1장 4컷당 한장 5컷당 한장, 캐릭터만 뭐 이런식으로. 선택할 수 있게도 해주고." 영상 단계는 비용의 80~90% 를 차지하는 구간이라 여기에 선택 필터만 넣어도 총 비용이 1/3~1/5 로 떨어집니다.

**핵심 전략** — 선택되지 않은 컷을 *건너뛰지* 않고 **`ffmpeg-kenburns` 폴백** (비용 0) 으로 대체합니다. 최종 렌더 단계가 `cut_N.mp4` 파일을 전체 컷에 대해 요구하기 때문에 skip 은 불가능. 대신 정지 이미지에 Ken Burns 효과를 입힌 로컬 클립으로 싸게 때우는 전략입니다.

**Backend — `app/routers/projects.py`**

- `DEFAULT_CONFIG` 에 `video_target_selection: "all"` 기본값 추가. 후보: `"all" | "every_3" | "every_4" | "every_5" | "character_only"`.

**Backend — `app/routers/video.py`**

- 모듈 레벨 헬퍼 `should_generate_ai_video(cut_number, selection)` / `count_ai_video_cuts(total, selection)` 추가. 1-based 컷 번호 기준 `(n - 1) % N == 0` 규칙. `character_only` 는 `every_3` 과 동일 (image.py 의 `cut_has_character` 와 일치).
- `generate_all_videos` (sync) 와 `generate_all_videos_async` (`_run` 코루틴) 양쪽에 동일 분기 적용:
  - `primary_service` = 사용자가 고른 video_model, `fallback_service` = `ffmpeg-kenburns` (model 이 이미 ffmpeg-kenburns 면 동일 인스턴스 재사용)
  - 컷 루프 안에서 `use_ai = should_generate_ai_video(cut.cut_number, selection)` 로 분기. 비-AI 컷은 fallback_service.generate(...) 호출 → 비용 0
  - `cut.video_model` 과 로그에 실제 사용된 모델을 기록 (추적성 유지)
  - 결과 dict 에 `ai_video: use_ai` 필드 추가

**Backend — `app/services/estimation_service.py`**

- 순환 임포트를 피하려고 `_count_ai_video_cuts` 규칙을 duplicate (원본은 video.py). 변경 시 양쪽을 맞춰야 함에 유의.
- `estimate_project(config)` 가 `video_target_selection` 을 읽어 `ai_video_cuts`, `fallback_video_cuts = cuts - ai_video_cuts` 로 분리 계산.
  - `video_cost` = AI 컷은 선택 모델 × cost, 폴백 컷은 ffmpeg-kenburns × cost (값 0). 규칙을 명시적으로 남겨둬야 나중에 ffmpeg-kenburns 가 유료가 되더라도 알아서 반영됨.
  - `video_sec` 도 동일 분리 — AI 컷은 선택 모델 초, 폴백 컷은 0.8s/컷 → 총 시간이 대폭 단축.
- 반환 dict 에 `video_target_selection`, `ai_video_cuts`, `fallback_video_cuts` 3 개 필드 추가.

**Frontend — `src/lib/api.ts`**

- `ProjectConfig` 에 `video_target_selection?: string` optional 필드 추가.
- `ProjectEstimate` 에 `video_target_selection?`, `ai_video_cuts?`, `fallback_video_cuts?` optional 필드 추가 (구버전 응답과 호환).

**Frontend — `src/components/studio/StepSettings.tsx`**

- "AI 모델 선택" 카드 안, 영상 모델 선택 아래쪽에 5 옵션 (전체 / 3컷당 1장 / 4컷당 1장 / 5컷당 1장 / 캐릭터만) 버튼 그리드를 배치. `updateConfig("video_target_selection", ...)` 로 일반 설정 저장 플로우와 동일하게 처리.
- 실시간 "총 N컷 중 AI M컷" 카운터를 우측 상단에 표시.
- **왜 StepVideo 가 아니라 StepSettings 인가** — 사용자 피드백으로 "영상제작 대상은 프로젝트 설정으로 옮기자" 결정. 모델/해상도/언어 같은 "프로젝트 사양" 성격이지 "이번 한 번의 생성 액션" 성격이 아니라서 설정 화면이 자연스러운 자리입니다.

**Frontend — `src/components/studio/StepVideo.tsx`**

- 로컬 `countAiCuts` 헬퍼로 CostEstimate detail 을 "AI {ai}컷 / 폴백 {fallback}컷" 으로 표시 (selection 이 `all` 이 아닐 때).
- "영상 제작 대상은 설정에서 변경" 안내 라벨 추가. 선택 UI 자체는 StepSettings 로 이관됨.

### 검증

- 규칙 일관성 확인: `should_generate_ai_video` (video.py) 와 `_count_ai_video_cuts` (estimation_service.py) 와 `countAiCuts` (StepVideo.tsx) 모두 `(n-1) % step == 0` 로 일치.
- seedance-1.5-pro + 120컷(10분) 기준 감소량:
  - all: 120컷 × $0.28 ≈ $33.60 (약 45,696원)
  - every_3: 40컷 → $11.20 (약 15,232원) — **1/3 로 감소**
  - every_4: 30컷 → $8.40 (약 11,424원)
  - every_5: 24컷 → $6.72 (약 9,139원) — **1/5 로 감소**
- `python -m py_compile` → OK
- `tsc --noEmit` → exit 0

### 설계 노트

- **왜 skip 이 아니라 폴백인가** — 렌더 단계 (`subtitle.render_video_with_subtitles`) 가 `cut_N.mp4` 파일을 전체 컷에 대해 요구하고, 그 파일들을 concat 해서 최종 영상을 만듭니다. 선택되지 않은 컷을 skip 하면 타임라인에 구멍이 뚫리고 나레이션/자막과 싱크가 깨집니다. Ken Burns 폴백은 이미지만 있으면 되므로 (이미지 스텝은 그대로 모두 생성됨) 추가 리소스 없이 자연스럽게 때워집니다.
- **`character_only` == `every_3` 인 이유** — `backend/app/routers/image.py` 의 `cut_has_character(n)` 가 `(n - 1) % 3 == 0` 로 캐릭터 등장 여부를 정의합니다. 같은 규칙을 재사용해서 "캐릭터 컷만 AI 비디오" 가 자동으로 성립. 나중에 캐릭터 등장 규칙이 바뀌면 3 곳을 다 맞춰야 합니다.
- **순환 임포트 회피** — estimation_service.py 는 `services/` 계층이고 routers/video.py 는 `routers/` 계층이라, services 에서 routers 를 임포트하는 건 레이어링 위반. 그래서 헬퍼 규칙을 양쪽에 복제했습니다. 복제는 버그 원천이므로 주석으로 "반드시 일치시켜야 함" 을 명시.

---

## v1.1.35 (2026-04-12)

### 추가 — 예상 비용 원화 표기 + 월 예상 + 과다 비용 경고

사용자 피드백: "하나 만드는데 4만원이면 한달에 120만원이라는거자녀." 실제로 프리미엄 조합(claude-opus-4-6 + midjourney + elevenlabs + seedance-1.5-pro) 로 10분짜리 1 편을 만들면 $35.07 ≈ **47,692원** 이 나오고, 일일 업로드 기준 월 **143만원** 에 도달합니다. 사용자는 기본값을 건드리진 말되 **경고만 표시** 하는 방향을 선택했습니다. 모델 선택권은 사용자에게 남기고, UI 가 "이거 지금 얼마짜리인지" 를 바로 체감할 수 있게 합니다.

**Backend — `app/services/estimation_service.py`**

- 환율 상수 `USD_TO_KRW = 1360.0` (2026-04 대략 평균치). 실시간 조회가 아니므로 표기 옆에 항상 "≈ 1,360원/달러 가정" 주석을 붙입니다.
- `DAYS_PER_MONTH = 30` — 일일 업로드 가정의 월 곱 factor.
- 편당 USD 기준 tier 임계치:
  - `cheap` ≤ $3 (한 편 ≈ 4,080원 / 월 ≈ 12만원) — 초록
  - `normal` $3~$8 (월 12~33만원) — 노랑
  - `expensive` > $8 (월 > 33만원) — 빨강
- `estimate_project(config)` 반환 dict 에 신규 필드 추가: `estimated_cost_krw`, `monthly_cost_usd`, `monthly_cost_krw`, `cost_tier`, `usd_to_krw`, `days_per_month`.
- 신규 `format_krw(amount)` 유틸 — "12,345원" 포맷.

**Frontend — `src/lib/format.ts`**

- 신규 `formatKrw(amount)` — `Intl` 기반 천 단위 콤마 + "원" 접미.
- 신규 `costTierClasses(tier)` → Tailwind 색상 클래스 (cheap=accent-success, normal=accent-warning, expensive=accent-danger) + 라벨 반환. 각 뷰에서 배지 색을 일관되게 유지.

**Frontend — `src/lib/api.ts`**

- `ProjectEstimate` 인터페이스에 v1.1.35 필드를 optional 로 추가. 구버전 백엔드 응답과도 호환.

**Frontend — `src/app/page.tsx` (대시보드)**

- 기존 "예상 $2.81" 배지를 **원화 우선** 표기로 교체: "3,820원/편" + 옆에 "월 114,460원" 작은 배지. tier 색상을 따라가며, `expensive` 일 때는 "⚠ 비용 과다" 경고 배지를 같이 렌더.
- Tooltip 에 `1편 $x.xx (KRW)` / `월 30편 예상: KRW` / `환율 가정 1 USD ≈ 1,360 KRW` / 단계별 USD breakdown 전부 노출.

**Frontend — `src/app/studio/[projectId]/page.tsx` (Studio 상단바)**

- 동일한 "원화/편 + 월 / tier 색상 + 경고" 구조로 교체.
- `project.estimate!` non-null 어서션으로 IIFE 안에서 타입 좁힘.

**Frontend — `src/components/studio/OneClickWidget.tsx` (딸깍 제작 위젯)**

- `prepared` phase 의 estimate 카드 배경/테두리 색을 tier 기반으로 동적 변경.
- "예상 비용 $x.xx" 였던 한 줄을 "1편 비용: **XXX원** ($x.xx)" + "월 30편: **XXX원**" 두 줄로 확장.
- `expensive` tier 이면 카드 안에 "⚠ 비용이 높습니다 — 모델을 낮추는 걸 권장합니다" 경고문 삽입.

### 검증

- 숫자 sanity 테스트 (5 조합):
  - 기본(sonnet+openai-image-1+openai-tts+ffmpeg) → $2.81 = 3,815원 / 월 114,461원 → `cheap`
  - 초저가(haiku+z-image-turbo+openai-tts+ffmpeg) → $0.74 = 1,006원 / 월 30,184원 → `cheap`
  - 중급(sonnet+openai-image-1+elevenlabs+kling-v2) → $20.43 = 27,780원 / 월 833,390원 → `expensive`
  - 프리미엄(opus+midjourney+elevenlabs+seedance-1.5-pro) → $35.07 = 47,692원 / 월 1,430,762원 → `expensive`
  - 5분 기본 → $1.42 = 1,934원 / 월 58,010원 → `cheap`
- `python -m py_compile` → OK
- `tsc --noEmit` → exit 0

### 설계 노트

- 환율을 실시간 조회(예: ECB / 한국은행 API) 로 가져올까 고민했지만, (a) 네트워크 실패 시 estimate 전체가 망가질 수 있고 (b) 추정치 자체가 ±10% 오차 범위라 환율 ±1% 의 차이는 의미가 없고 (c) 대시보드 목록 로드마다 외부 호출을 넣기 싫어서 상수 처리. 환율이 크게 움직이면 `USD_TO_KRW` 상수 한 줄만 갱신하면 전체 UI 에 반영됩니다.
- tier 임계치는 "월 예상 33만원" 을 "이거 비싸다" 의 체감 기준으로 잡음. 사용자가 말한 "4만원/편 → 월 120만원" 은 정확히 `expensive` tier 에 걸리고 경고 배지가 뜨게 됩니다.
- **기본값은 의도적으로 건드리지 않음** — 사용자가 AskUserQuestion 에서 "일단 경고만 표시" / "비디오 유지" / "TTS 유지" 를 모두 골랐기 때문. 기본값 변경은 기존 사용자에게 파괴적이라 별도 논의가 필요한 사안.

### 버전

4개 파일 동반 범프: `backend/app/main.py` (×2), `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` (×2).

---

## v1.1.34 (2026-04-12)

### 추가 — 딸깍 제작 (Studio 좌측 사이드바 독립 실행 위젯)

사용자 요청: "딸깍 제작 기능 만들자. 프로젝트 선택가능하게 하고 그 프로젝트의 모든 시퀀스대로 자동으로 최종 렌더링까지. 다른 작업들과 관계없이 따로 작업되도록. 주제 넣고 저장 누르면 예상 시간/비용(모델별로), 시작 누르면 프로세스게이지."

현재 Studio 에서 열려 있는 프로젝트에 손대지 않고, **새 프로젝트 한 건을 통째로 만들어서 대본→음성→이미지→영상→최종 렌더링까지 한 방에 돌리는** 위젯을 사이드바 하단(자동화 스케줄 카드 아래)에 박았습니다. 스케줄러/Celery 대기열과 별개 경로로 돌기 때문에 사용자가 다른 프로젝트를 편집하거나 다른 스텝을 실행해도 간섭이 없습니다.

**Backend — `app/services/oneclick_service.py` (신규, ~426 lines)**

- 인메모리 `_TASKS` dict + `asyncio.Lock` 기반 단일 실행 큐. 서버 재시작 시 in-flight 태스크는 잃는 것을 허용 (사용자가 다시 누르면 됨 — 복잡도보다 단순함 우선).
- `_clone_project_from_template(template_project_id, topic, title)` — 템플릿 프로젝트의 config 를 얕은 복사해 새 Project 를 만들고, `auto_pause_after_step=False` 를 강제해 자동 일시정지가 튀어나오지 않게 함. `data/{project_id}/{audio,images,videos,subtitles,output}` 디렉토리도 미리 생성.
- `_run_oneclick_task(task_id)` — 메인 러너. `async with _RUN_LOCK` 안에서:
  1. `pipeline_tasks._step_script/_step_voice/_step_image/_step_video` 를 `asyncio.to_thread` 로 감싸 순차 실행 (기존 sync 함수 재사용 — 동작 검증된 코드 패스).
  2. 각 스텝 전에 `init_progress(project_id, step_num)` 을 호출해 Redis `pipeline:step_progress:{pid}:{step}` 카운터를 0 으로 리셋. 컷 단위 진행률을 프론트에서 그대로 읽을 수 있도록.
  3. 스텝 2(대본) 가 끝나면 fresh 로딩으로 `total_cuts` 를 task 레코드에 반영 — 이후 진행률 계산은 이 값을 분모로 사용.
  4. 최종 렌더링(Step 6) 은 `app.routers.subtitle.render_video_with_subtitles(project_id, db)` 를 **router handler 직접 호출** 로 실행. 이 함수는 async 이며 Depends 가 풀리기 전이라 db 세션만 명시적으로 넘기면 됨. ASS 자막 생성 → 컷 오디오 정규화 → concat → 자막 번인 → 오프닝/엔딩 페이드까지 한 번에 처리.
  5. 각 스텝 상태는 `task["step_states"][str(n)]` 에 `pending | running | completed | failed` 로 기록, `Project.status` 도 완료/실패 시 동기 갱신.
- `_compute_progress_pct(task)` — 단계별 가중치 (`{2:5, 3:20, 4:35, 5:25, 6:15}`, 합=100). 완료 스텝은 풀 가중치, 진행 중 스텝은 `(Redis 컷 카운터 / total_cuts) × 가중치`. 렌더링 단계는 컷 단위 진행이 없어 시작→0 / 완료→15 로만 변동.
- Public API: `prepare_task`, `start_task` (asyncio.create_task 로 백그라운드 띄움), `cancel_task` (Redis `pipeline:cancel:{pid}` 플래그 set — 기존 `check_pause_or_cancel` 이 다음 컷에서 잡음), `get_task`, `list_tasks`, `prune_tasks(keep=20)`.

**Backend — `app/routers/oneclick.py` (신규, ~80 lines)**

FastAPI 라우터로 `oneclick_service` 를 HTTP 로 노출:

- `POST /api/oneclick/prepare` — body `{template_project_id?, topic, title?}` → 새 프로젝트 + 예상치 포함 task 반환
- `POST /api/oneclick/{task_id}/start` — 백그라운드 실행 시작
- `POST /api/oneclick/{task_id}/cancel` — 취소
- `GET /api/oneclick/tasks` — 전체 목록
- `GET /api/oneclick/tasks/{task_id}` — 단일 조회 (매 호출마다 `progress_pct` 최신화)
- `POST /api/oneclick/prune` — 완료/실패 태스크 정리

`app/main.py` — import 추가 + `app.include_router(oneclick.router, prefix="/api/oneclick", tags=["oneclick"])`.

**Frontend — `src/lib/api.ts`**

- `OneClickTask` 인터페이스 (task_id, project_id, status, current_step/name, step_states, progress_pct, estimate, error 등) 추가
- `oneclickApi.prepare/start/cancel/get/list/prune` 메서드 묶음

**Frontend — `src/components/studio/OneClickWidget.tsx` (신규, ~380 lines)**

3 phase state machine:

1. **idle** — 템플릿 드롭다운(기존 프로젝트 목록에서 선택, 비우면 기본 설정) + 주제 textarea + 제목 선택 input + `[저장 후 예상 비용 확인]` 버튼. `oneclickApi.prepare()` 호출.
2. **prepared** — 새 프로젝트가 만들어진 뒤, 예상 컷/시간/비용 총합 + 단계별(script/image/tts/video) breakdown 을 모델 이름과 함께 표시. `[시작]` / `[X 다시]` 버튼.
3. **running** — 진행률 게이지 (0~100%) + 현재 단계명 (`대본 생성`/`음성 생성`/.../`최종 렌더링`) + 5개 스텝 점 인디케이터 (대본/음성/이미지/영상/렌더링). `[중지]` 또는 완료 후 `[새로 만들기]`. 2초 간격 `oneclickApi.get()` 폴링.

게이지 색상은 상태별로 primary/success/danger 로 바뀌고, 실패 시 에러 메시지를 전체 폭으로 렌더.

**Frontend — `src/app/studio/[projectId]/page.tsx`**

사이드바 자동화 스케줄 카드 바로 아래에 `<OneClickWidget />` 마운트. 현재 열려 있는 프로젝트의 ID 를 넘기지 않음 — 의도적으로 독립 실행이기 때문.

### 검증

- 백엔드 `python -m py_compile` → OK (main.py, routers/oneclick.py, services/oneclick_service.py, services/estimation_service.py)
- 프론트엔드 `tsc --noEmit` → exit 0 (전체 프로젝트 에러 0)

### 설계 노트

- **왜 Celery 가 아니라 `asyncio.create_task` 인가** — 사용자가 "다른 작업들과 관계없이 따로" 를 명시. Celery 큐에 섞으면 기존 pipeline 작업과 worker 경쟁이 생기고 우선순위 관리가 어려워집니다. FastAPI 프로세스 안 asyncio 루프에서 `_RUN_LOCK` 한 개로 직렬화하면 다른 API 요청도 안 막히고, 기존 스케줄러 패턴(`scheduler_service._run_episode`) 과도 일관됩니다.
- **왜 `_step_*` 을 `asyncio.to_thread` 로 감싸나** — 기존 pipeline sync 함수는 내부적으로 `run_async` 헬퍼를 써서 이벤트 루프를 직접 만드는데, FastAPI 메인 루프 위에서 그대로 부르면 "loop already running" 예외가 납니다. 별도 스레드로 띄우면 각자 독립 루프를 쓸 수 있어 안전합니다.
- **업로드(Step 7)는 제외** — 사용자가 "최종 렌더링까지" 라고 명시. YouTube 업로드는 승인 게이트가 있는 편이 안전하므로 별도 스텝에서 수동 실행 유지.

### 버전

4개 파일 동반 범프: `backend/app/main.py` (×2), `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` (×2).

---

## v1.1.33 (2026-04-12)

### 추가 — 프로젝트별 예상 소요시간 / 예상 비용 표시

사용자 요청: "프로젝트 별 예상 소요시간하고 비용 표시해."

어떤 모델 조합을 고르느냐에 따라 600초 한 편 제작 비용이 `$2.8` 에서 `$35` 까지 **12배** 가 벌어지고 소요 시간도 `42분` 에서 `3시간 6분` 까지 차이납니다. 실행 전에 이걸 미리 보여주지 않으면 모델을 잘못 골랐을 때 돈이 줄줄 새게 됩니다. 그래서 프로젝트 config 로부터 예상 비용/시간을 계산해 대시보드와 Studio 상단에 띄웁니다.

**Backend — `app/services/estimation_service.py` (신규, +~200 lines)**

DB / 외부 호출 없이 `config` 만 받아 계산하는 순수 함수. 대시보드 목록 직렬화마다 호출되어도 비용이 거의 없습니다.

- 컷 수 = `target_duration // 5` (시스템 프롬프트가 "각 컷 = 5초" 를 강제)
- **LLM 비용** — `LLM_REGISTRY[model]['cost_input' | 'cost_output']` × (입력 2500 tokens + 출력 `cuts * 180 + 2048` tokens). 출력 산식은 v1.1.32 `claude_service.py::generate_script` 의 `dynamic_max` 와 완전히 동일하게 맞춰 실제 청구액과 gap 을 최소화.
- **이미지 비용** — `IMAGE_REGISTRY[model]['cost_value']` × cuts (개당 단가 × 컷 수)
- **TTS 비용** — `TTS_REGISTRY[model]['cost_value']` × (`cuts * 24` / 1000) — 한국어 평균 나레이션 24자 가정
- **비디오 비용** — `VIDEO_REGISTRY[model]['cost_value']` × cuts (5초 clip 기준 단가)
- **시간 산정** — 모델별 컷당 실측 평균치 테이블 (`IMAGE_SEC_PER_CUT`, `TTS_SEC_PER_CUT`, `VIDEO_SEC_PER_CUT`) 과 LLM 기본 45s, post-process 30s 를 합산. 순차 호출 기준의 보수적 추정.
- `estimate_project(config)` → `{estimated_cuts, target_duration, estimated_cost_usd, estimated_seconds, cost_breakdown, time_breakdown, models_used}`
- `format_duration_ko(seconds)` — 초를 "3시간 12분" / "27분" / "45초" 로 포맷

**Backend — `app/routers/projects.py`**

- `_to_dict(p)` 반환 dict 에 `"estimate": estimate_project(p.config or {})` 추가. `GET /api/projects`, `GET /api/projects/{id}`, `POST /api/projects`, `PUT /api/projects/{id}` 응답 전부에 자동 포함.
- 신규 `GET /api/projects/{project_id}/estimate` — 프로젝트 단일 estimate 를 독립 반환. 부분 갱신용.

**Frontend**

- `src/lib/api.ts` — `ProjectEstimate` 인터페이스 추가, `Project.estimate?` 필드 추가.
- `src/lib/format.ts` (신규) — `formatDurationKo(seconds)` 공용 헬퍼. 백엔드 `format_duration_ko` 와 규칙 일치.
- `src/app/page.tsx` (대시보드) — 프로젝트 카드에 두 배지 (`<Clock/> 예상 42분`, `<DollarSign/> 예상 $2.81`) 와 모델 요약 (`gpt-image-1 · ffmpeg-kenburns`) 을 추가. 기존 `api_cost` 배지는 `실사용 $x.xx` 로 라벨 변경해 예상과 실제를 구분. 배지 `title` 에 breakdown tooltip (LLM/이미지/TTS/비디오/합성 단계별 수치).
- `src/app/studio/[projectId]/page.tsx` (Studio 상단바) — `예상 42분` / `예상 $2.81` 배지 + 기존 라벨을 `실사용 $0.00` 으로 교체. `handleUpdate → loadProject()` 파이프라인이 이미 모든 step 이벤트에서 호출되므로, StepSettings 에서 모델을 바꾸고 저장하면 자동으로 배지가 갱신됩니다 (별도 코드 불필요).

### 검증

- 백엔드 `python -m py_compile` → OK (main.py, projects.py, estimation_service.py)
- 프론트엔드 `tsc --noEmit` → exit 0
- estimation 산식 단위 테스트 (600s 기본 / 600s claude+dalle3+eleven / 600s opus+midjourney+eleven+seedance / 300s 기본 / 60s 최소) 전부 합리적 수치 (예: 600s 기본 → 120컷 · $2.81 · 42분 27초).

### 버전

4개 파일 동반 범프: `backend/app/main.py` (×2), `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` (×2).

---

## v1.1.32 (2026-04-12)

### 버그픽스 — 600초(10분) 대본 생성 시 JSON 파싱 실패

사용자 보고: "600초로 대본생성하니까 에러난다 이거 부터 처리해." 증상 스크린샷은 `HTTP 500 POST /script/.../generate: LLM script generation failed: Expecting ',' delimiter: line 545 column 6 (char 29325)`.

**원인.** `claude_service.py::generate_script` 가 `max_tokens=8192` 로 하드코딩되어 있었습니다. 시스템 프롬프트(`base.py::SCRIPT_SYSTEM_PROMPT_KO`) 는 "600초(10분) = 120컷" 을 명시하고 각 컷당 나레이션/영어 image_prompt/메타데이터를 요구하므로 완성된 JSON 은 실측 20k~30k 자 수준입니다. Claude 응답이 8192 output token 상한에 도달하면서 배열 한가운데에서 잘려 `json.loads` 가 `char 29325` 에서 터졌습니다. GPT 쪽 `gpt_service.py::generate_script` 도 `max_tokens` 미지정이라 모델 기본값에 종속되는 동일한 위험 구조였습니다.

**수정.**

- `backend/app/services/llm/claude_service.py`
  - `generate_script` 가 `config['target_duration']` 을 읽어 `max_tokens` 를 동적으로 산정: `max(8192, (target_duration // 5) * 180 + 2048)`, 상한 64000. 600초(120컷) 기준 약 23,648 토큰이 할당되어 truncation 여지가 사라집니다.
  - `_safe_int` 유틸 추가 — config 값이 문자열/None 이어도 안전하게 정수로 변환.
  - `_parse_json` 에 **truncation 복구 방어선** 추가. 원문 파싱이 실패하면 `_repair_truncated_json` 으로 미완결 JSON 을 구조적으로 닫은 뒤 재시도합니다. 알고리즘은 한 번의 선형 스캔으로 문자열/이스케이프/스택 상태를 추적하면서 "안전하게 잘라도 되는 위치" 를 기록합니다: ① `{`/`[` 직후 (빈 컨테이너), ② `}`/`]` 직후 (값 완결), ③ value 포지션의 `"` 닫힘 직후 (object 안에서는 `:` 뒤인지로 key/value 를 구분). 스캔 종료 후 마지막 safe cut 까지 자르고 당시 열려 있던 괄호들을 역순으로 닫아 valid JSON 을 복원합니다. 테스트: 120컷 샘플 JSON(14,861자)을 80/150/200/300/500/1500/5000/10000/14000/14861 위치에서 잘라본 결과 모두 `json.loads` 통과 (회수된 컷 수는 각각 1/1/1/2/4/12/41/81/114/120).
- `backend/app/services/llm/gpt_service.py`
  - `generate_script` 에 동일한 동적 max_tokens 로직 적용 (상한 16000 — GPT-4o 실용 상한).

이 수정으로 600초 이상 대본이 정상 생성됩니다. truncation 복구는 1차 방어선이 뚫렸을 때를 대비한 2차 안전장치입니다.

**검증.**

- `python -m py_compile` — claude_service.py, gpt_service.py, main.py 모두 OK.
- 복구 알고리즘 단위 시뮬레이션 — 120컷 스트레스 샘플 10개 truncation 포인트 전부 통과.

**버전.** 4개 파일 동반 범프: `backend/app/main.py` (×2), `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` (×2).

---

## v1.1.31 (2026-04-12)

### 추가 — YouTube Studio (채널 관리 UI 전면 구축)

사용자 요청: "자 이제 유튜브 스튜디오 콘텐츠 업로드 페이지 하고 관리 페이지 만들자. 가져올수 있는 기능 모두 다 가져와 싹다. 업로드부터 게시 게시 설정 삭제까지 싹다."

LongTube 파이프라인과 **독립** 된 채널 관리 기능을 통째로 추가했습니다. 이미 올라가 있는 영상이든, LongTube 로 만든 영상이든 전부 한곳에서 조회/편집/게시설정/삭제/업로드/재생목록/댓글 관리가 가능합니다. YouTube Data API v3 의 `youtube` + `youtube.force-ssl` 범위 안에서 할 수 있는 것은 모두 붙였습니다 — 다만 YouTube Analytics (조회수 그래프, 수익, Audience retention 등) 는 별도 scope 와 별도 API 라 이번 범위에서는 빠집니다.

**Backend — `app/services/youtube_service.py` 확장 (+~640 lines)**

기존 `YouTubeUploader` 클래스에 Studio 전용 메서드 추가. 모두 blocking googleapiclient 호출이라 라우터에서 `asyncio.to_thread` 로 감쌉니다.

- `list_my_videos(max_results, page_token, query)` — `search.list(forMine=True)` 로 내 영상 목록. `videos.list(part=status,statistics,contentDetails)` 로 privacyStatus / 조회수 / 좋아요 / 댓글수 / duration 을 2 차 보강.
- `get_video(video_id)` — snippet + status + statistics + contentDetails 전부.
- `update_video(video_id, ...)` — `videos.update` 는 `part` 를 통째로 덮어쓰기 때문에 현재 상태를 먼저 읽어와 None 이 아닌 필드만 바꿔서 다시 보내는 **merge 방식**. `publish_at` 이 들어오면 자동으로 `privacyStatus=private` 로 내리고 YouTube 가 해당 시각에 public 으로 전환하도록 예약.
- `set_thumbnail(video_id, path)` — mime 자동 판별 후 `thumbnails.set`.
- `list_playlists` / `create_playlist` / `update_playlist` (merge) / `delete_playlist`.
- `list_playlist_items` / `add_to_playlist` / `remove_from_playlist`.
- `list_comment_threads(video_id, ..., order)` — topLevelComment + replies 까지 한 번에.
- `reply_to_comment` / `set_comment_moderation(heldForReview|published|rejected, banAuthor)` / `delete_comment` / `mark_comment_as_spam`.
- `list_video_categories(region_code)` — 카테고리 드롭다운용.

**Backend — `app/routers/youtube_studio.py` (신규, +~470 lines)**

새 FastAPI 라우터. prefix `/api/youtube-studio`, tag `youtube-studio`. 모든 엔드포인트에 `project_id` 쿼리 파라미터가 선택 — 생략하면 전역 `token.json`, 있으면 `DATA_DIR/{project_id}/youtube_token.json` 토큰 사용.

- `GET  /auth/status` — 로그인 + 채널 정보 동시 반환.
- `GET  /videos` + `GET /videos/{id}` + `PATCH /videos/{id}` (VideoUpdateRequest) + `POST /videos/{id}/thumbnail` (multipart) + `DELETE /videos/{id}?confirm=true`.
- `POST /upload` — 파이프라인 없이 직접 업로드. multipart form 으로 file + title + description + tags + privacy_status + category_id + default_language + made_for_kids + publish_at + 썸네일 파일. 큰 파일도 메모리 폭탄 없이 디스크로 흘려보내고 `YouTubeUploader.upload` resumable 업로드에 넘김. `publish_at` 이 있으면 업로드 성공 직후 `update_video` 로 예약 게시를 건다(`videos.insert` 는 publishAt 를 안 받아서 별도 호출).
- `GET/POST /playlists`, `PATCH/DELETE /playlists/{id}`, `GET/POST /playlists/{id}/items`, `DELETE /playlists/{id}/items/{item_id}`.
- `GET /videos/{id}/comments` + `POST /comments/{parent_id}/reply` + `POST /comments/{id}/moderation` + `POST /comments/{id}/spam` + `DELETE /comments/{id}`.
- `GET /categories?region_code=KR`.
- 에러 변환: `YouTubeAuthError → 401`, `YouTubeUploadError → 400`, 그 외 → 500.

`app/main.py` 에 `app.include_router(youtube_studio.router, prefix="/api/youtube-studio", tags=["youtube-studio"])` 등록.

**Frontend — `/youtube` 라우트 트리 신규 (Next.js 14 app router)**

- `/youtube/layout.tsx` — 좌측 사이드바(대시보드/영상/업로드/재생목록/댓글) + 전역 인증 배너 + 채널 카드. 인증 안 됐으면 버튼으로 `/api/youtube/auth` 를 쏴서 로컬 OAuth 팝업.
- `/youtube/page.tsx` — 대시보드. 최근 6편 요약 (합계 조회/좋아요/댓글) + 썸네일 그리드 + 재생목록 요약 카드.
- `/youtube/videos/page.tsx` — 목록 페이지. 검색 + 페이지네이션(next/prev 토큰 스택) + 공개상태 배지(예약/공개/일부공개/비공개) + 조회/좋아요/댓글 숫자 + 빠른 삭제.
- `/youtube/videos/[videoId]/page.tsx` — 편집 페이지. 제목/설명/태그/카테고리/언어/공개상태/예약게시/아동용/퍼가기/좋아요공개 전 필드. 썸네일 호버로 교체. `datetime-local` 입력을 RFC3339 로 변환해 백엔드로 전송. 빈 문자열 `""` 을 보내면 예약 해제.
- `/youtube/upload/page.tsx` — 파이프라인 없는 직접 업로드. 영상 + 썸네일 + 메타/공개/예약 설정 한 폼.
- `/youtube/playlists/page.tsx` — 재생목록 CRUD + 인라인 편집.
- `/youtube/playlists/[playlistId]/page.tsx` — 재생목록 항목 조회 + video_id 로 추가/제거.
- `/youtube/comments/page.tsx` — 좌측에서 영상 선택 → 우측에 댓글 스레드. 답글/보류/승인/차단/스팸/삭제 버튼. `heldForReview|published|rejected` + `banAuthor` 전부 한 UI 에서 호출 가능.

**Frontend — `src/lib/api.ts`**

`youtubeStudioApi` 네임스페이스 추가. 모든 엔드포인트에 대응하는 type-safe 래퍼 + `StudioAuthStatus`/`StudioVideoListItem`/`StudioVideoDetail`/`StudioVideoUpdateBody`/`StudioPlaylist`/`StudioPlaylistItem`/`StudioCommentThread`/`StudioCommentReply`/`StudioCategory` interface. 쿼리스트링 빌더 `qs()` 는 undefined/null/"" 를 자동 스킵.

**Frontend — `src/app/page.tsx`**

메인 대시보드 헤더에 `YouTube Studio` 빨간 버튼을 `자동화 스케줄` 옆에 추가.

### 의도적으로 포함하지 않은 것 (솔직 공지)

- **YouTube Analytics (조회수 그래프, CTR, 시청 지속시간, 수익, Audience retention)** — `yt-analytics.readonly` scope 및 `youtubeAnalytics` API 가 따로 필요. 별도 기능으로 추후 작업.
- **커뮤니티 탭 포스트** — YouTube Data API 에 write 엔드포인트가 없음.
- **수익화 / 광고 설정 / 챕터 편집 / 엔드 스크린 / 카드** — Public Data API 범위 밖. Studio 웹 UI 전용.
- **썸네일 A/B 테스트** — 2024-06 부터 웹 UI 에만 존재, API 없음.

### 버전 1.1.31 bump
- backend/app/main.py (FastAPI `version=` + `/api/health`)
- frontend/src/lib/version.ts
- frontend/package.json
- frontend/package-lock.json (root + `packages[""]`)

### 검증
- `py_compile` 통과: `youtube_service.py`, `youtube_studio.py`, `main.py`.
- `tsc --noEmit` 통과 (frontend 전체 타입체크 에러 0).

---

## v1.1.30 (2026-04-12)

### 수정 — 최종 렌더링 실패 (FFmpeg pad 필터) + 썸네일/컷 이미지 비율 복구

사용자 보고: "이미지 비율이 왜이래. 그리고. 최종렌더링 안된다". 스크린샷에 두 가지 증상이 겹쳐 있었음.
- 썸네일 배경이 왼쪽에 치우치고 오른쪽이 비어 보이는 비율 이상
- 최종 렌더링이 `HTTP 500 ... Cut normalization failed: RuntimeError: FFmpeg failed (code 4294967274): configure input pad on Parsed_pad_1 ... Error reinitializing filters!` 로 즉시 실패

**1. FFmpeg pad 필터 버그 (렌더링 즉시 실패)**

진단: `app/services/video/ffmpeg_service.py` 의 `ensure_min_duration` / `merge_videos_reencode` / `add_fade_in_out` 세 함수가 `pad={resolution}:(ow-iw)/2:(oh-ih)/2` 식으로 필터 문자열을 만들고 있었음. `{resolution}` 은 `"1920x1080"` 처럼 `WxH` 지름길 포맷이라 pad 필터에 들어가면 이게 그대로 `w` 파라미터 expression 으로 eval 되어 `Invalid chars 'x1080' at the end of expression '1920x1080'` 로 터짐. scale 필터는 `"size"` 지름길을 내부에서 특수 처리해서 통과되지만 pad 는 그런 처리가 없음. sandbox ffmpeg 4.4.2 로 동일 에러 완전 재현 → 수정 후 동일 입력으로 통과 확인.

수정: 세 함수 모두 `pad_wh = resolution.replace("x", ":")` 로 콜론 형식을 따로 만들어서 pad 쪽에만 사용. scale 은 `WxH` 지름길이 멀쩡하니 그대로 둠.

**2. 썸네일 / 컷 이미지 비율 이상 (nano-banana edit 모드에서 image_size 누락)**

진단: `app/services/image/nano_banana_service.py` 가 edit 모드(`reference_images` 가 주어진 경우)에서 `image_size` 파라미터를 일부러 생략하고 있었음 — 주석에 "edit 쪽은 ref 크기를 상속" 이라고 되어 있었는데, 사용자의 레퍼런스가 1:1 square 면 16:9 요청을 줘도 결과가 square 로 나오고 썸네일 pipeline 에서 center-crop 되어 시각적으로 "왼쪽에 몰린" 모양이 됨. 컷 이미지도 같은 이유로 square 가 되어 영상 단계 전체가 1:1 로 흐른 뒤 렌더링 pad 단계에서 letterbox 를 넣는 과정에서 위 버그와 겹쳐 터졌음.

수정: edit 모드에서도 항상 `image_size: {width, height}` 를 payload 에 포함. fal.ai nano-banana edit 엔드포인트가 이 파라미터를 허용하므로 ref 스타일은 유지하면서 출력 비율은 요청 비율을 따름.

**3. 버전 1.1.30 bump** — backend/app/main.py ×2, frontend/src/lib/version.ts, frontend/package.json, frontend/package-lock.json ×2.

### 영향 범위
- 썸네일 생성: 레퍼런스가 square/portrait 인 프로젝트도 이제 1280x720 으로 맞춰서 나옴.
- 컷 이미지 생성: 16:9 프로젝트에서 1280x720 으로 고정, 9:16 은 720x1280.
- 최종 렌더링: 컷 영상 해상도가 project aspect 와 달라도 pad letterbox 로 정상 출력 (v1.1.29 까지는 pad 단계에서 즉시 실패).

### 검증
- sandbox ffmpeg 4.4.2 로 버그 완전 재현 → 수정 버전으로 800x600 / 1024x1024 / 512x512 입력 모두 1920x1080 / 1080x1920 출력 성공.
- py_compile 통과: ffmpeg_service.py, nano_banana_service.py, main.py.

---

## v1.1.29 (2026-04-12)

### 수정 — 레퍼런스 스타일 강제 적용 + project.topic 오염 복구

사용자 2 건 보고:
1. "이거 뭐야. 이미지가 영 똥망인데? 레퍼런스 이미지 스타일 따라가야지" (v1.1.28 핫픽스 후 생성이 성공했지만 배경 이미지가 프로젝트 레퍼런스 스타일과 완전히 무관한 사진풍으로 나옴)
2. "이게 뭐냐 이거 수정해" (헤더 바로 아래에 YouTube 설명 전문 수천자가 한 줄 벽으로 찍혀 있음)

**1. 레퍼런스 스타일이 전혀 반영되지 않던 문제 — 3 layer 강화**

진단: `nano_banana_service.generate` 는 `reference_images` 가 들어와도 `_file_to_data_uri` 가 전부 None 을 돌려주면 `ref_data_uris` 가 비고 조용히 순수 t2i 경로로 떨어짐. 게다가 "스타일 락" 프리픽스는 `nano-banana-3` 변종 + `use_edit=True` 일 때만 붙었고, 다른 변종에서는 레퍼런스를 받더라도 프롬프트에 지시가 안 박혔음.

- `nano_banana_service.py` — 레퍼런스가 주어졌는데 하나도 못 읽으면 **명시적 RuntimeError** 를 올려 조용한 t2i 폴백을 차단. 어떤 경로가 실패했는지 메시지에 남김.
- `nano_banana_service.py` — `_style_lock` 조건 제거. 모든 nano-banana 변종에서 `use_edit` 이면 스타일 락 프리픽스를 항상 prepend. 프리픽스 문구도 더 강경하게("copy it, do not reinterpret").
- `routers/youtube.py::create_thumbnail` — `combined_refs` 가 있으면 LLM 이 만든 `image_prompt` 앞에 한 번 더 STYLE REFERENCE LOCK 블록을 prepend. 서비스 레벨 프리픽스가 끊기는 경우를 대비한 2 중 방어선.
- `routers/youtube.py::create_thumbnail` — 응답에 `reference_diagnostics` 필드 추가: `registered_reference_images`, `resolved_reference_images`, `missing_reference_images`, `sent_to_model` 등 진단 정보를 내려서 프론트가 이유를 노출할 수 있게 함.
- `frontend/src/lib/api.ts` — `ThumbnailGenerateResult` 타입에 `reference_images_used`, `reference_fallback`, `reference_diagnostics` 추가.
- `frontend/src/components/studio/StepYouTube.tsx` — 썸네일 카드 하단에 레퍼런스 진단 배너 추가. 0 장이면 노란 경고 + "스타일 레퍼런스를 이미지 탭에서 업로드하라" 안내. 전달됐으면 녹색 + 장수 + 폴백 사유.

**2. `project.topic` 이 YouTube 설명 전문으로 덮어써져 헤더가 벽이 되던 버그**

진단: `StepYouTube.tsx` 가 영상 설명(description) state 를 `project.topic` 에서 초기화하고, `persistProjectMeta(title, description)` 이 두 번째 인자를 `project.topic` 에 그대로 PUT 했음. AI 메타 추천을 돌리면 5000자짜리 설명 전문(+ bullet 목차) 이 DB 의 `project.topic` 을 덮어쓰고, 스튜디오 상단 `<p>{project.topic}</p>` 가 그 벽을 그대로 뿌렸음.

- `StepYouTube.tsx` — `description` state 초기값을 `project.config.youtube_description` 에서 읽도록 변경.
- `StepYouTube.tsx::persistProjectMeta` — description 을 `config.youtube_description` 에 저장하도록 리팩터. 더 이상 `project.topic` 을 건드리지 않음.
- `StepYouTube.tsx::handleRecommendMetadata` / `handleRecommendTags` — LLM 호출 시 `topic` 인자로 `project.topic` (원본 짧은 주제어) 를 넘기도록 수정. 이전엔 description 을 넘겨서 점점 길어지는 피드백 루프가 있었음.
- `app/studio/[projectId]/page.tsx` — 헤더 topic 을 1 줄 `truncate` + `title` 툴팁으로 노출. 과거 오염 데이터에도 레이아웃이 무너지지 않도록 하는 안전망.
- `backend/app/main.py` — lifespan startup 에 1 회성 마이그레이션 추가. `project.topic` 이 300자 초과거나 줄바꿈/`• `/`· ` 마커를 포함하면 `config.youtube_description` 으로 이관하고 topic 을 `title` 또는 첫 문장(최대 120자) 으로 대체. `config.youtube_description` 이 이미 있으면 덮어쓰지 않음. 마이그레이션 결과를 로그에 남김.

**3. 버전 1.1.29 bump**

- `backend/app/main.py`, `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json`

---

## v1.1.28 (2026-04-12) — HOTFIX: fal.ai 큐 status URL 405

### 수정 — fal.ai 이미지 생성이 전부 405 Method Not Allowed 로 터지던 버그

사용자 보고: 썸네일 재생성 시 `HTTP 500 … AI 썸네일 배경 생성 실패: Client error '405 Method Not Allowed' for url 'https://queue.fal.run/fal-ai/flux/dev/requests/.../status'`.

**원인**

`FluxService._poll_result`, `NanoBananaService._poll`, `FalGenericService._poll` 이 fal.ai 큐 status URL 을 손수 조립하고 있었음:

```
f"{FAL_BASE}/{endpoint}/requests/{request_id}/status"
```

그런데 fal.ai 큐 API 의 status 경로는 **submit 경로의 서브경로를 떼낸** 형태여야 함. 예: submit 은 `POST fal-ai/flux/dev` 이지만 status 는 `GET fal-ai/flux/requests/{id}/status` (끝의 `/dev` 가 빠짐). nano-banana 의 `/edit` 서브경로도 마찬가지. 잘못된 경로를 GET 으로 치면 fal.ai 는 405 로 응답. 결과적으로 fal.ai 를 쓰는 모든 이미지 모델(flux/nano-banana/seedream/z-image) 이 비동기 job 으로 넘어가는 순간 터졌음.

추가로 나노바나나는 실패 시 Flux 로 조용히 폴백하게 돼 있어서, 사용자가 UI 에서 "Nano Banana" 를 선택했는데도 에러 URL 에는 `flux/dev` 가 박히는 혼란 발생.

**수정 — 3 파일**

fal.ai 큐는 submit 응답에 `status_url` 과 `response_url` 을 명시적으로 내려줌. 이걸 그대로 쓰면 된다.

- `app/services/image/flux_service.py`: submit 응답에서 `status_url`, `response_url` 추출 → `_poll_result` 에 그대로 전달. 누락 시 명확한 RuntimeError.
- `app/services/image/nano_banana_service.py`: 동일하게 `_poll` 시그니처를 `(status_url, response_url)` 로 변경. 이로써 `/edit` 서브경로 케이스도 한 번에 해결.
- `app/services/image/fal_generic_service.py`: 동일 패턴 적용 (seedream, z-image 용).

이제 fal.ai 에 등록된 모든 모델이 큐 job 으로 넘어가도 정상 poll.

**버전 1.1.28 bump**

- `backend/app/main.py`, `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json`

---

## v1.1.27 (2026-04-12)

### 수정 — 썸네일 그림텍스트(MrBeast) 스타일 + 레퍼런스 미지원 모델 자동 폴백

사용자 보고 원문: "이미지가 설정의 레퍼런스와 스타일이 같아야지. 그리고 문구가 너무 재미 없지 않냐? 자막 형식으로 하지말고 그림텍스트로 해."

**1. 썸네일 텍스트 오버레이를 자막 박스 → 그림텍스트로 리팩터 — `app/services/thumbnail_service.py`**

v1.1.26 에서 축소한 "라운드 박스 안에 자막" 스타일이 여전히 자막처럼 보여서 몰입을 깼음. YouTube 상위 채널(MrBeast 류) 스타일로 전면 재작업.

- 박스·테두리·라운드 사각형 전부 제거. 순수 스트로크 텍스트 + 드롭섀도우만 사용.
- 후보 폰트 크기 상향: `(88, 78, 68, 60, 52, 46) → (160, 140, 124, 108, 96, 86, 76, 68, 60)`. 최대 3 줄, 블록 높이 `THUMB_H * 0.18 → 0.38`.
- 스트로크 굵기 폰트 크기 비례 `max(6, min(14, title_size // 9))` — 화면이 크든 작든 외곽선이 비슷한 비율로 보임.
- `ImageFilter.GaussianBlur(radius=6)` 드롭섀도우 레이어(오프셋 6px) 를 텍스트 뒤에 알파 합성 — 배경이 복잡해도 글자가 떠오름.
- 멀티라인일 때 마지막 줄만 노란색(`255, 226, 32`), 그 외는 흰색 — MrBeast 의 "마지막 단어 강조" 패턴.
- 하단에 20 단계 그라디언트 darken 오버레이 추가. 하단 55~100% 영역이 점점 어두워져서 텍스트 가독성 확보 + 이미지 상단 구도 유지.
- 좌측 정렬 `pad_x=60`. 썸네일 배경 이미지의 hero subject 는 주로 오른쪽/가운데 있으므로 왼쪽 하단 텍스트와 겹치지 않음.
- EP 배지 블록은 기존 v1.1.26 스펙 유지(작은 노란 라운드 배지).

**2. 레퍼런스 이미지 미지원 모델 자동 폴백 — `app/services/image/base.py` / `flux_service.py` / `nano_banana_service.py` / `openai_image_service.py` / `app/routers/youtube.py`**

사용자가 프로젝트에 스타일 레퍼런스를 등록해 놨는데도 생성된 썸네일이 그 스타일과 전혀 다른 이유를 추적 → `FluxService.generate()` 가 `reference_images` 파라미터를 **받기만 하고 fal.ai 페이로드에 안 넣음**. 같은 문제가 `fal_generic` (seedream / z-image), `grok`, `midjourney`, `dall-e-3` 에도 있음.

- `BaseImageService` 에 `supports_reference_images: bool = False` 클래스 속성 추가.
- `NanoBananaService.supports_reference_images = True` (이미 `/edit` 엔드포인트로 레퍼런스 지원).
- `OpenAIImageService` 는 `self.supports_reference_images = (model_id == "openai-image-1")` — gpt-image-1 만 `/edits` 가능, dall-e-3 은 불가.
- `FluxService` 는 `supports_reference_images = False` 로 명시 + `reference_images` 가 들어오면 그냥 드롭하지 않고 `logging.warning` 으로 남김 (폴백이 실패해도 원인이 로그에 보이도록).
- `routers/youtube.py::create_thumbnail`: 프로젝트에 레퍼런스가 하나라도 있고 선택한 `image_model_id` 가 `supports_reference_images == False` 면 **자동으로 `nano-banana-3` 로 폴백**. 응답에 `reference_fallback` 필드로 이유를 내려줘서 UI 가 사용자에게 알릴 수 있음.

**3. 버전 1.1.27 로 bump**

- `backend/app/main.py`, `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json`

---

## v1.1.26 (2026-04-12)

### 수정 — 썸네일 오버레이 리팩터 (오버레이 축소 + 외곽 프레임 제거 + 채널명 유출 방지)

사용자 보고 원문: "응 썸네일이 여전히 좆구려." + 2차: "채널이름이자나 씨발년아. 근데 썸네일에는 넣으면 안되지"

**1. 오버레이 전체 크기 축소 — `app/services/thumbnail_service.py`**

- `_fit_font` 후보 크기 `(150, 130, 115, 100, 88, 78) → (88, 78, 68, 60, 52, 46)`. 이전엔 메인 후크 박스가 화면 하단 1/3 이상을 집어삼켜 이미지가 안 보였음.
- 박스 허용 높이 `THUMB_H * 0.28 → 0.18`. subtitle 쪽도 `0.14 → 0.10` 으로 축소.
- subtitle seed 폰트도 `max(56, …) → max(36, …)` 로 하향.
- `box_pad_x 34 → 22`, `box_pad_y 18 → 12`, `line_gap 20 → 12`.
- `outline_width 6 → 4`, `radius 22 → 14`. 박스 테두리가 덜 묵직해서 배경 이미지가 살아난다.
- EP 배지 크기도 동일 톤 다운: 폰트 `(92, 80, 70, 60, 52) → (64, 56, 48, 42, 36)`, 패딩 `26/14 → 18/10`, 외곽선 `6 → 4`, radius `18 → 12`.
- 하단 여백 `bottom_margin 60 → 48`.

**2. 외곽 초록 프레임 완전 제거**

- `generate_thumbnail(…, frame: bool = True)` 파라미터 삭제. 프레임 렌더링 블록(`if frame: …`) 통째로 제거. 이미지가 액자처럼 보이던 문제 해결.
- `generate_ai_thumbnail(…, overlay_frame: bool = True)` 파라미터도 제거.
- 호출부 동시 정리:
  - `app/routers/youtube.py` — `ThumbnailGenerateRequest.frame` 필드 제거, `cut_overlay` / `ai_overlay` 경로의 `frame=body.frame` / `overlay_frame=body.frame` 삭제.
  - `app/services/scheduler_service.py::_run_thumbnail` — `overlay_frame=True` 인자 제거.
  - `frontend/src/lib/api.ts` — `ThumbnailGenerateRequest.frame?: boolean` 필드 제거.

**3. 채널명이 썸네일에 박히던 버그 수정 — `frontend/src/components/studio/StepYouTube.tsx`**

- **버그**: `handleGenerateThumbnail` 이 `titleHook.trim() || title.trim().replace(/^EP\.?\s*\d+\s*[-–—:·]\s*/i, "").trim() || title.trim()` 체인으로 메인 후크 텍스트를 자동 계산했음. `titleHook` 이 비어 있고(= AI 추천 한 번도 안 돌렸을 때) `project.title` 이 채널명("jerry's aecheo") 으로 잡혀 있으면 **채널명이 썸네일에 그대로 박혔음**.
- **수정**:
  - `thumbMainHook` 전용 state + `thumbMainHookTouched` 플래그 추가.
  - `useEffect(…)` 로 `titleHook` / `title` 이 바뀌면 자동 기본값(`titleHook > title에서 'EP. N - ' 접두어 제거`)을 세팅. 사용자가 한 번이라도 직접 편집했으면 (`touched=true`) 덮어쓰지 않음.
  - 썸네일 카드 상단에 **"메인 후크 텍스트 (썸네일에 크게 박힘)"** 전용 input 추가. maxLength 60. 사용자가 생성 전에 썸네일에 뭐가 박힐지 눈으로 확인 + 수정 가능.
  - `handleGenerateThumbnail` 에서 자동 계산 대신 `thumbMainHook.trim()` 을 그대로 `title` 로 전송. 비어있으면 에러 표시 후 early return — 다시는 의도치 않은 값이 썸네일에 박히지 않음.

**4. 버전 1.1.26 으로 bump**

- `backend/app/main.py` (FastAPI version + health endpoint)
- `frontend/src/lib/version.ts` (`APP_VERSION`)
- `frontend/package.json` / `frontend/package-lock.json`

---

## v1.1.25 (2026-04-10)

### 추가 — 간지영상 탭 (오프닝 / 인터미션 / 엔딩)

사용자 요청 원문: "자막-유튜브 사이에. 간지영상 탭 만들고 캐릭터와 주제를 사용 해서 오프닝, 엔딩, 인터미션 영상 만들 수 있도록 해. 그리고 영상의 시작 부분에 오프닝 넣고, 3분마다 인터미션, 마지막에 엔딩 넣을 수 있게 렌더링 시퀀스 만들어."

**1. 간지영상 라우터 — `app/routers/interlude.py` 신규**

- `InterludeKind = Literal["opening", "intermission", "ending"]`. 세 종류 모두 동일한 파이프라인(이미지 1장 → Ken Burns → mp4)으로 만들고, 종류별 메타(길이/프롬프트/경로)만 `project.config["interlude"]` 딕셔너리에 저장. 새 DB 테이블/마이그레이션 없음.
- 저장 경로: `data/{project_id}/interlude/{kind}.png` + `{kind}.mp4`.
- 프롬프트 결정 순서: (1) 사용자가 입력한 커스텀 프롬프트 → (2) LLM `generate_thumbnail_image_prompt(character_description=...)` 재활용 → (3) kind 별 템플릿 폴백 (`_fallback_interlude_prompt`). 기본 길이 5초(1–30초), 인터미션 기본 간격 180초(30–1800초).
- 엔드포인트:
  - `GET    /api/interlude/{project_id}` — 현재 세 종류의 상태 + `intermission_every_sec` 반환.
  - `PUT    /api/interlude/{project_id}/config` — 인터미션 간격 변경.
  - `POST   /api/interlude/{project_id}/generate/{kind}` — 이미지 1장 생성 → FFmpeg Ken Burns 으로 mp4 렌더 → config 갱신.
  - `DELETE /api/interlude/{project_id}/{kind}` — 파일 + config 항목 정리.
  - `POST   /api/interlude/{project_id}/compose` — 시퀀스 조립. `[opening?] + cut1 + cut2 + ... (누적 길이 ≥ every 일 때마다 intermission 삽입, 마지막 컷 뒤는 제외) + [ending?]` 를 `FFmpegService.merge_videos()` 의 stream-copy concat 으로 합쳐 `data/{project_id}/output/final_with_interludes.mp4` 생성. 컷 길이는 `Cut.audio_duration` 우선, 없으면 `ffprobe` 폴백, 그래도 없으면 5초 기본값.

**2. 최종 업로드 소스 우선순위 — `app/routers/youtube.py` `_final_video_path()`**

- 새 우선순위: `final_with_interludes.mp4` → `final_with_subtitles.mp4` → `merged.mp4`. 간지가 포함된 영상이 있으면 자동으로 그걸 업로드하도록 수정.
- 자동화 스케줄러(`app/services/scheduler_service.py`) 의 `_run_episode` 와 레거시 파이프라인 태스크(`app/tasks/pipeline_tasks.py::_step_upload`) 도 동일한 우선순위로 정렬.

**3. 프론트 — `StepInterlude` 탭**

- `frontend/src/components/studio/StepInterlude.tsx` 신규. 세 개의 kind 카드(오프닝 / 인터미션 / 엔딩) 각각에:
  - 길이(초) 입력 + 커스텀 프롬프트 입력 + `생성 / 재생성` 버튼 + 인라인 `<video controls>` 미리보기 + 삭제 버튼.
  - `hasCharacter` 체크: `project.config.character_description` 또는 `image_global_prompt` 가 비어 있으면 상단에 경고 배너 표시.
- 하단 `렌더 시퀀스` 섹션: `intermission_every_sec` 입력 (30–1800초), `설정 저장`, `간지 포함 영상 렌더` 버튼. 렌더 성공 시 출력 경로 / 총 클립 수 / 사용된 컷 수 / opening·intermission·ending 포함 여부를 초록 배너로 표시.
- `frontend/src/lib/api.ts`: `InterludeKind`, `InterludeEntry`, `InterludeState`, `InterludeGenerateRequest/Result`, `InterludeComposeResult` 타입 + `interludeApi` (`get / updateConfig / generate / remove / compose`) 추가.
- `frontend/src/app/studio/[projectId]/page.tsx`: STEPS 배열에 `{ num: 7, name: "간지영상" }` 삽입, 유튜브를 8번으로 이동. `renderStepContent` 의 `case 7 → StepInterlude`, `case 8 → StepYouTube`. 업로드 완료 감지(`stepStates["8"]`)와 사이드바 라벨도 동일하게 갱신. 파이프라인 스텝 컨트롤 UI(일시정지/진행바/ETA)는 2–6번만 유지.

### 추가 — 유튜브 계정 프로젝트별 분리

사용자 요청 원문: "유튜브 탭에 계정은 프로젝트로 옴겨 프로젝트별로 다른 계정 사용 할수 있도록 해."

- `app/services/youtube_service.py` `YouTubeUploader.__init__(self, project_id: Optional[str] = None)` 확장. `project_id` 가 있으면 토큰 경로를 `DATA_DIR/{project_id}/youtube_token.json` 으로, 없으면 레거시 전역 경로(`TOKEN_PATH`) 로 폴백. `authenticate / is_authenticated / get_channel_info / logout` 모두 인스턴스 `self.token_path` 를 사용하도록 수정.
- `app/routers/youtube.py` 에 프로젝트별 엔드포인트 신규: `GET /{project_id}/auth/status`, `POST /{project_id}/auth`, `GET /{project_id}/auth/channel`, `POST /{project_id}/auth/reset`. 업로드 엔드포인트는 `YouTubeUploader(project_id=...)` 가 인증돼 있으면 그걸 쓰고, 아니면 전역 토큰으로 폴백.
- 스케줄러(`_run_episode`)와 레거시 파이프라인 태스크(`_step_upload`) 도 동일한 fallback 로직 적용.
- 프론트: `frontend/src/components/studio/StepYouTube.tsx` 가 `projectAuthStatus / projectAuthenticate / projectAuthChannel / projectAuthReset` 를 호출하도록 교체, `useEffect([project.id])` 로 프로젝트 변경 시 재조회. 레거시 채널 ID 화이트리스트(`EXPECTED_CHANNEL_ID`) 경고 UI 제거. `api.ts` 에 네 가지 projectAuth* 메서드와 `YouTubeAuthStatus.project_id / global_authenticated` 필드 추가.

### 추가 — 썸네일에 메인 캐릭터 강제 포함

사용자 요청 원문: "유튜브 탭에 썸네일에는 캐릭터가 꼭 포함되게 생성해."

- `app/services/llm/base.py` `generate_thumbnail_image_prompt(..., character_description: str = "")` 시그니처 확장. `_build_thumbnail_prompt_request` 는 캐릭터 설명이 있으면 프롬프트 앞에 별표 강조로 "The main focal subject MUST be this character: {desc}. The character must be clearly visible and centered." 를 강제 삽입. `_fallback_thumbnail_prompt` 도 동일한 `char_clause` 로 교체.
- `app/services/llm/claude_service.py`, `app/services/llm/gpt_service.py` 두 구현체가 새 파라미터를 받아서 베이스로 전달하도록 수정.
- `app/routers/youtube.py::create_thumbnail` 은 `project.config.character_description` 또는 `image_global_prompt` 에서 설명을 추출해 LLM 호출에 전달.

### 추가 — 대본 초기화 버튼

사용자 요청 원문: "대본도 초기화 기능 넣어."

- `StepScript` 의 상단 액션 영역에 `초기화` 버튼 추가. 누르면 기존 `pipelineApi.resetStep(projectId, 2)` 로 컷/오디오/이미지/영상을 재귀적으로 삭제하고 대본 탭만 남긴 뒤 `onCutsChange([])` 로 로컬 상태도 비움.

### 수정 — ElevenLabs 4종 보이스 목록

사용자 요청 원문: "일레븐 렙스 api 추가 했어. 걔네가 제공하는 목소리 리스트 가져와. Blondie - Intense Woman / LARRY FLICKER / EMMALINE PETER / Nothern Terry 이거 만 가져와두 될거 같애."

- ElevenLabs `/v1/voices` 를 실제로 호출해 허용 보이스 4종(정규화된 이름 매칭)만 필터링해서 `voiceApi.listElevenLabs()` 응답으로 돌려주도록 수정. 프론트 `StepVoice` 드롭다운이 이 리스트를 그대로 렌더.

## v1.1.24 (2026-04-10)

### 추가 — 자동화 스케줄 (주제 + 시간 → 매일 자동 업로드)

사용자 피드백 요약: "주제 리스트와 일정 딱 넣으면 정해진 시간에 딱딱 영상이 올라가게 하는 거야. 그냥 매일 매일 올리는 거지." UI 스크린샷은 스튜디오 좌측 사이드바의 유튜브 스텝 아래 빈 영역, 그리고 `EP./주제/시간/명령/상태` 컬럼을 가진 17행짜리 테이블 목업. 확인 질문 4개에 대한 답: 전체 파이프라인 자동화 / in-process 스케줄러 / 별도 스케줄 페이지 / xlsx 는 계획용 템플릿만.

**1. DB 모델 — `ScheduledEpisode`**

- `backend/app/models/scheduled_episode.py` 신규. 한 행 = 하루 한 번의 예약 업로드 슬롯.
- 필드: `id`, `episode_number`, `topic`, `scheduled_at`, `template_project_id`, `privacy`, `enabled`, `status` (pending/running/uploaded/failed/skipped), `project_id`, `video_url`, `final_title`, `error_message`, `started_at`, `finished_at`, `created_at`, `updated_at`.
- `backend/app/models/database.py` `init_db()` 가 새 모델을 import 하도록 추가.

**2. 스케줄러 루프 — `app/services/scheduler_service.py`**

- 외부 의존성(APScheduler, Celery) 없이 순수 `asyncio` 로 동작하는 in-process 백그라운드 루프.
- `start_scheduler()` 를 FastAPI lifespan 에서 호출 → `asyncio.Event` 로 제어 가능한 30초 폴링 task 생성.
- `_tick_once()`: `enabled=True`, `status='pending'`, `scheduled_at <= utcnow()` 인 행 중 가장 오래 지연된 1건을 선택. 전역 `asyncio.Lock()` 으로 감싸 한 번에 **한 에피소드만** 실행 (YouTube Data API 쿼터, 로컬 FFmpeg/GPU 동시성 보호).
- `_run_episode()` 실행 단계:
  1. `template_project_id` 의 config 를 얕은 복사 + `auto_pause_after_step = False` 강제 + 새 `Project` row + 디렉토리 생성.
  2. `_step_script → _step_voice → _step_image → _step_video → _step_subtitle` 순차 실행 (각 step 은 sync blocking 이므로 `asyncio.to_thread` 로 감쌈). 각 단계 실패 시 `episode.error_message` + `status='failed'` 기록 후 리턴.
  3. `LLM.generate_metadata(episode_number=N)` 로 title_hook/description/tags 생성 → `EP. N - {hook}` 조립 + `_strip_episode_prefix()` 중복 제거.
  4. `generate_ai_thumbnail()` 로 1280x720 배경 생성 + 좌상단 `EP. N` 배지 + 메인 훅 오버레이. 실패해도 썸네일 없이 업로드 시도.
  5. `YouTubeUploader.upload()` 를 `asyncio.to_thread` 로 호출. 성공 시 `episode.video_url`, `episode.final_title`, `status='uploaded'`, `project.status='completed'`, `project.youtube_url` 저장.
- `run_episode_now(episode_id)` — 같은 `_lock` 을 공유하는 수동 트리거. 루프가 다른 에피소드를 돌리고 있으면 기다렸다가 실행.
- `stop_scheduler()` — lifespan shutdown 에서 event 를 set 하고 5초 대기, 그래도 안 죽으면 cancel.

**3. 스케줄 라우터 — `app/routers/schedule.py`**

- `GET    /api/schedule` — 전체 목록.
- `GET    /api/schedule/status` — 루프 동작 여부 + poll interval.
- `POST   /api/schedule` — episode_number 기준 upsert. 완료/실패 상태에서 다시 저장하면 자동으로 `pending` 으로 되돌림.
- `PUT    /api/schedule/{id}` — 부분 수정. `status` 는 `pending` / `skipped` 로만 수동 변경 허용.
- `DELETE /api/schedule/{id}` — 삭제.
- `POST   /api/schedule/bulk` — 17행 한 번에 저장 (`replace_all: bool` 플래그 지원).
- `POST   /api/schedule/{id}/run` — `BackgroundTasks.add_task(run_episode_now, id)` 로 지금 실행.
- `POST   /api/schedule/{id}/reset` — failed/uploaded 상태를 pending 으로 되돌려 재시도.
- privacy 검증(`private|unlisted|public`), 공통 `_to_dict` 직렬화.

**4. FastAPI 통합**

- `backend/app/main.py`:
  - `schedule` 라우터 등록 (`/api/schedule`).
  - lifespan startup 에서 `scheduler_service.start_scheduler()` 호출, shutdown 에서 `stop_scheduler()`.
  - 버전 1.1.24 + reload-trigger 갱신.

**5. 프론트 — 자동화 스케줄 페이지**

- `frontend/src/app/schedule/page.tsx` 신규. Next.js App Router `/schedule` 라우트.
  - 17행짜리 테이블 (목업과 동일): EP. / 주제 / 날짜 / 시간 / 템플릿 프로젝트 / 공개 / 사용 / 상태 / 명령.
  - 로컬 행 상태(`Row[]`) ↔ 백엔드 `ScheduleItem[]` 양방향 매핑. `episode_number` 가 동일한 백엔드 행을 row 에 병합.
  - `rowToScheduledAt()` — 로컬 `<input type="date">` + `<input type="time">` 값을 ISO 8601 UTC 로 변환해 서버로 전송.
  - `전체 저장` 버튼 — 주제 + 날짜 + 시간이 모두 입력된 행만 모아 `scheduleApi.bulkSave()`.
  - 행별 **실행 버튼** → `/api/schedule/{id}/run` 호출, **리셋 버튼** → `/api/schedule/{id}/reset`, **사용 체크박스** → 즉시 `PUT /api/schedule/{id}`.
  - 실행중 행이 있으면 4초마다 `loadAll()` 자동 폴링 (상태 뱃지가 실시간으로 대기 → 실행중 → 완료 로 바뀜).
  - 템플릿 프로젝트 `<select>` — `projectsApi.list()` 결과를 그대로 사용.
  - 상태 뱃지 5종(대기/실행중/완료/실패/건너뜀), 업로드 성공 시 영상 링크 inline 표시.
- `frontend/src/lib/api.ts`:
  - `SchedulePrivacy`, `ScheduleStatus`, `ScheduleItem`, `ScheduleItemInput` 타입.
  - `scheduleApi = { list, status, bulkSave, upsert, update, remove, runNow, reset }` 바인딩.

**6. 프론트 — 진입점 연결**

- `frontend/src/app/page.tsx`: 대시보드 헤더 우측에 `<CalendarClock> 자동화 스케줄` 버튼 추가 → `/schedule` 이동.
- `frontend/src/app/studio/[projectId]/page.tsx`:
  - 상단바에 `스케줄` 링크 버튼 추가.
  - 좌측 사이드바 파이프라인 리스트 바로 아래(사용자가 빨간 동그라미로 가리킨 위치) 에 "자동화 스케줄" 카드 — 노란 `CalendarClock` 아이콘 + 설명 문구 + `/schedule` 링크.

**7. xlsx 계획 템플릿**

- `docs/schedule_template.xlsx` 신규. 사용자가 스케줄을 미리 종이에 정리할 때 쓸 수 있는 비어있는 17행 템플릿. 시트: 자동화 스케줄, 사용법.
- 컬럼: EP. / 주제 / 시간(yyyy-mm-dd hh:mm) / 공개 / 명령 / 상태. 공개·명령·상태는 데이터 검증 리스트 드롭다운. 보라색 타이틀 밴드 + 회색 헤더 + 교차 행 배경. `xlsx` 스킬 `recalc.py` 로 0 error 검증.
- **주의**: 이 파일은 단순 계획용 참조이며, 실제 스케줄러는 `/schedule` 웹 페이지에서만 관리합니다 (import/export 경로 없음).

### 버전

- `backend/app/main.py`, `frontend/package.json`, `frontend/src/lib/version.ts` → 1.1.24.

---

## v1.1.23 (2026-04-10)

### 추가 — 에피소드 기반 제목 + 레퍼런스 스타일 썸네일 + 채널 확인

사용자 피드백 요약: (1) 제목이 너무 길다, "EP. 1 - 블라블라" 형식으로 짧게; (2) 업로드가 어느 계정으로 가는지 불확실하다 (본인 채널 ID: `UCRJbxZoVj7l41Fsw_S9a23A`); (3) 썸네일이 레퍼런스 이미지처럼 굵은 검정 테두리 + 노랑/라임 텍스트 박스 + 좌상단 EP 배지 스타일이어야 한다.

**1. 에피소드 번호 + 짧은 hook 기반 제목**

- `backend/app/services/llm/base.py` `_build_metadata_prompt()` 에 `episode_number: Optional[int]` 파라미터 추가. 값이 주어지면:
  - "★ EPISODE MODE ★" 블록 삽입 — LLM 이 "EP"/"Episode"/"에피소드"/"제N화" 같은 접두어를 직접 붙이지 못하도록 금지.
  - JSON 응답 키가 `title` 이 아니라 `title_hook` — 짧은 hook 단어/구(句) 하나만 쓰라고 강제. CJK 언어는 22자, 그 외엔 48자 제한. 풀문장 / 물음표 / 말줄임표 / 따옴표 / 이모지 / trailing punctuation 전부 금지.
- `_parse_metadata_response()` 는 `title_hook` 과 구버전 `title` 키를 둘 다 흡수. 호환성 유지.
- `ClaudeService` / `GPTService` `generate_metadata()` 시그니처에 `episode_number` 추가. system 프롬프트 JSON 키 설명도 `title_hook` 으로 업데이트.
- `backend/app/routers/youtube.py`:
  - `MetadataRecommendRequest.episode_number` 필드 추가.
  - `_strip_episode_prefix()` 헬퍼 — LLM 이 혹시 "EP. 1 - " 접두어를 실수로 붙여와도 중복 방지로 제거.
  - `recommend_metadata` 가 `episode_number` 가 있으면 최종 `title` 을 `f"EP. {N} - {hook}"` 으로 조립. 응답에 `title_hook`, `episode_number` 도 포함.

**2. 레퍼런스 스타일 썸네일 (EP 배지 + 컬러 박스)**

- `backend/app/services/thumbnail_service.py` `generate_thumbnail()` 완전 재작성:
  - 색상 팔레트: 노랑 배지 `(255, 222, 23)`, 라임 훅 박스 `(182, 255, 0)`, 외곽 프레임 초록 `(0, 220, 120)`. 모두 모바일 해상도에서 확 튀는 saturation.
  - 레이아웃: (a) 배경 cover-crop + 18% 어둡게, (b) 하단 1~2 줄 굵은 텍스트 박스 — 22px 라운드 사각형 + 6px 검정 아웃라인, 제목 여러 줄이면 노랑/라임 alternate, (c) 좌상단 EP 배지(노랑 라운드 + 검정 아웃라인), (d) 14px 둥근 초록 외곽 프레임 옵션.
  - `_fit_font()` 헬퍼 — 폰트 후보 리스트 `(150, 130, 115, 100, 88, 78)` 안에서 텍스트가 들어가는 최대 크기를 자동 선택.
  - 새 파라미터: `episode_label`, `subtitle`, `frame`.
- `generate_ai_thumbnail()` 도 `overlay_subtitle` / `overlay_episode_label` / `overlay_frame` 을 받아서 그대로 오버레이에 전달.
- 라우터 `ThumbnailGenerateRequest` 에 `subtitle` / `episode_label` / `frame` 필드 추가. `cut_overlay` / `ai_overlay` 양쪽 모두에 전달.

**3. YouTube 채널 확인 + 재인증**

- `backend/app/services/youtube_service.py`:
  - `YouTubeUploader.get_channel_info()` 신규 — `channels.list(mine=True, part="id,snippet,statistics")` 로 현재 인증된 계정의 채널 ID / 제목 / 썸네일 / 구독자 수 / 영상 수 반환.
  - `YouTubeUploader.logout()` 신규 (classmethod) — `token.json` 삭제. 다음 `/auth` 호출 시 계정 선택 팝업이 다시 뜸.
- `backend/app/routers/youtube.py`:
  - `GET /api/youtube/auth/channel` — 현재 인증된 채널 정보 반환. 인증 안 돼 있으면 401.
  - `POST /api/youtube/auth/reset` — token.json 삭제. 다른 Google 계정으로 전환할 때 사용.
  - 업로드 에러 로깅 개선: 401/500 에서 traceback 을 stdout 으로 덤프(콘솔에서 원인 추적 가능).
- `frontend/src/lib/api.ts`:
  - `YouTubeChannelInfo` 타입, `youtubeApi.authChannel()` / `authReset()` 바인딩 추가.
- `frontend/src/components/studio/StepYouTube.tsx`:
  - OAuth 섹션 — 인증 완료 시 채널 썸네일 + 제목 + 채널 ID + 구독자/영상 수 + Studio 바로가기 링크 표시.
  - 예상 채널 ID(`UCRJbxZoVj7l41Fsw_S9a23A`) 와 다르면 경고 뱃지 표시.
  - "다른 계정으로 전환" ghost 버튼 — confirm → reset → 즉시 재인증 플로우.
  - 영상 정보 섹션에 **에피소드** 숫자 입력칸 추가(제목 좌측). 값이 있으면 "AI 전체 추천" 호출 시 `episode_number` 를 백엔드에 전달 → 반환된 `title = "EP. N - {hook}"` 로 제목 덮어쓰기. `titleHook` 도 별도 state 로 보관 → 제목 입력칸 아래에 "후크: '{hook}'" 표시.
  - 에피소드 번호가 바뀌면 썸네일 "에피소드 배지" 기본값이 `EP. {N}` 으로 자동 갱신(사용자가 수동 편집 안 했을 때만, `/^EP\. \d+$/` 패턴일 때).
  - 썸네일 섹션 — "에피소드 배지" + "보조 라인" 입력칸 2개 추가. 메인 후크 텍스트는 `titleHook` 우선, 없으면 제목에서 "EP. N - " 접두어 제거한 부분을 자동 사용.

### 버전

- 모든 버전 파일 1.1.23 일치.

---

## v1.1.22 (2026-04-10)

### 수정 — YouTube 메타데이터가 대사 언어를 따라가지 않던 버그

**문제**: v1.1.21 에서 태그 추천을 붙일 때 `_build_tag_prompt()` 안에 "Korean documentary-style" 과 "Mix Korean and English tags naturally" 를 하드코딩해놓아서, 대사가 영어/일본어/중국어여도 태그가 한국어-영어 섞인 채로 나왔습니다. 설명(description) 은 아예 LLM 에 넘기지도 않고 프론트가 `project.topic` 짧은 문자열만 그대로 보여주고 있었고, 제목도 생성 기능 없이 스크립트 단계에서 만든 원본만 유지됐습니다.

**수정 — 전 필드 "대사 언어 단일 잠금"**

1. `backend/app/routers/youtube.py`:
   - `_detect_language(text)` 헬퍼 추가. 한글/가나/CJK/라틴 문자 개수를 세서 주 언어 코드(`ko`/`ja`/`zh`/`en`) 반환. 가나가 10자 이상이면 일본어 우선(일본어는 CJK 와 혼용).
   - `_resolve_language(requested, config, narration)` — 요청값 > 나레이션 자동 감지 > `project.config.language` > `"ko"` 순으로 결정.
   - `POST /api/youtube/{project_id}/tags/recommend` 가 이제 `language` 를 LLM 에 전달.
   - **신규**: `POST /api/youtube/{project_id}/metadata/recommend` — `title` / `description` / `tags` 를 한 번에 반환. `description` 은 LLM 이 600~1500자 범위로 hook + 요약 + 하이라이트 bullet + 마무리 구조로 작성하도록 프롬프트로 강제. 응답엔 `source` (`llm` / `partial` / `heuristic`) 와 감지된 `language` 도 포함.

2. `backend/app/services/llm/base.py`:
   - `_build_tag_prompt()` 와 `_build_metadata_prompt()` 에 `language` 파라미터 추가 + `_language_name()` 매핑 (`ko`→"Korean (한국어)" 식).
   - 두 프롬프트 상단에 **★ CRITICAL LANGUAGE RULE ★** 블록 추가. "EVERY field MUST be written in {LANGUAGE} only. Do NOT mix languages. No translations, no transliterations, no romanizations." 라고 명시.
   - `_build_metadata_prompt()` — 출력 포맷을 JSON 으로 엄격히 고정. `title` < 100자, `description` 600~1500자 / 4블록 구조(hook → summary → bullets → CTA), `tags` 배열 10~max개 / 각 30자 이하.
   - `generate_metadata()` 추상 기본 구현 추가(빈 dict 반환). `_extract_json_object()` / `_parse_metadata_response()` 헬퍼.

3. `backend/app/services/llm/claude_service.py` / `gpt_service.py`:
   - `generate_tags()` 시그니처에 `language` 추가.
   - `generate_metadata()` 오버라이드 신규. 둘 다 system 프롬프트로 "Match the language requested EXACTLY — do not mix languages." 추가. GPT 는 `response_format={"type":"json_object"}` 유지.

4. `frontend/src/lib/api.ts`:
   - `TagRecommendRequest` 에 `language?` 추가, `TagRecommendResult` 에 `language: string` 추가.
   - `MetadataRecommendRequest` / `MetadataRecommendResult` 타입 신규, `youtubeApi.recommendMetadata()` 바인딩 추가.

5. `frontend/src/components/studio/StepYouTube.tsx`:
   - "영상 정보" 섹션 헤더 우측에 **"AI 전체 추천 (제목·설명·태그)"** primary 버튼 추가. 클릭 시 현재 제목/설명을 백엔드에 힌트로 넘기고, 반환된 title/description/tags 로 전체 필드를 **덮어쓰기**.
   - 버튼 아래에 감지된 언어 뱃지(`KO` / `EN` / `JA` ...) 와 소스(`LLM 전체 생성` / `LLM 부분 + 폴백 일부` / `휴리스틱 폴백`) 표시.
   - description textarea 를 `min-h-[120px]` → `min-h-[220px]` 로 키우고 `font-mono` 적용 — LLM 이 만든 긴 멀티블록 설명이 잘리지 않고 보이도록.
   - 기존 "AI 태그 추천" 버튼은 유지(태그만 리프레시하고 싶을 때).

### 버전

- 모든 버전 파일 1.1.22 일치.

## v1.1.21 (2026-04-10)

### 수정 — 썸네일 생성 실패 버그

**원인**: `backend/app/routers/youtube.py` 의 `_pick_base_cut()` 이 DB 에 저장된 `cut.image_path` (상대 경로, 예: `cuts/001/cut_1.png`) 를 그대로 `os.path.exists()` 에 넘기고 있었음. 상대 경로는 백엔드 프로세스의 CWD 기준으로 해석되기 때문에 NAS (`C:\Users\Jevis\Desktop\longtube_net\projects`) 에 실제 파일이 있어도 항상 False → `base_image_path=None` → 썸네일은 "이미지 없는" 폴백 경로만 타고, 프론트에선 버튼이 `disabled={!hasImageCut}` 로 묶여 있어 아예 클릭조차 못 하는 상황이 발생.

**수정**:

1. `_pick_base_cut()` 을 `_resolve_cut_image()` 헬퍼로 분리하고 상대 경로를 `DATA_DIR / project_id / image_path` 로 해석하도록 고침. 절대 경로는 그대로 통과.
2. 프론트 `StepYouTube.tsx` 의 썸네일 생성 버튼에서 `disabled={!hasImageCut}` 제거. 컷 이미지가 없어도 다크 그라데이션 폴백으로 썸네일이 생성되도록 허용하고, 안내 문구만 경고색으로 표시.

### 추가 — AI 기반 YouTube 태그 자동 추천

사용자가 "태그는 니가 추천하는 걸로 넣어 주고" 라고 요청 → 프로젝트 제목/주제/대본 스니펫을 LLM 에 넘겨 태그 10~15개를 JSON 으로 받아오는 기능 추가.

**백엔드**

- `backend/app/services/llm/base.py` — `BaseLLMService` 에 `async def generate_tags(...)` 기본 구현(빈 리스트 반환) + `_build_tag_prompt()` / `_parse_tag_response()` 헬퍼 추가. 하위 서비스가 오버라이드 안 해도 라우터는 안전하게 휴리스틱 폴백으로 넘어감.
- `backend/app/services/llm/claude_service.py` — Anthropic messages API 로 태그 1024 토큰 생성. system prompt 로 JSON-only 응답 강제.
- `backend/app/services/llm/gpt_service.py` — OpenAI chat completions API, `response_format={"type": "json_object"}` 로 JSON 모드 강제.
- `backend/app/routers/youtube.py` — `POST /api/youtube/{project_id}/tags/recommend` 신규. 프로젝트 `config["script_model"]` 에 등록된 LLM 을 재사용(새 API 키 요구 X). LLM 호출이 실패하거나 빈 리스트면 `_heuristic_tags()` 로 폴백 → 한국어/영문 2자 이상 토큰 빈도 분석 + 제목/주제를 seed 로 사용. 응답은 `{tags, source: "llm"|"heuristic", error}`.

**프론트**

- `frontend/src/lib/api.ts` — `TagRecommendRequest` / `TagRecommendResult` 타입 + `youtubeApi.recommendTags()` 메서드 추가.
- `frontend/src/components/studio/StepYouTube.tsx` — 태그 입력 라벨 우측에 "AI 태그 추천" 고스트 버튼 추가. 클릭 시 제목/주제를 백엔드에 전달하고 반환된 태그를 기존 입력과 **중복 없이 병합** (사용자가 먼저 친 태그는 보존). 결과 아래에 LLM/휴리스틱 소스 뱃지 표시. 에러 발생 시 경고 메시지.

### 버전

- 모든 버전 파일 1.1.21 일치 (main.py 2곳, version.ts, package.json, package-lock.json 2곳).

## v1.1.20 (2026-04-10)

### 추가 — YouTube 업로드 + 썸네일 생성 파이프라인

Phase 3 의 핵심 잔여 작업이었던 **YouTube Data API 연동** 을 마무리했습니다. 기존 코드엔 라우터/서비스 골격은 있었지만 실제로 호출하면 즉시 깨지는 버그가 여러 개 있어서, 먼저 버그를 전부 수정하고 그 다음에 UI + 썸네일 파이프라인을 덧붙였습니다.

**버그 수정 — `backend/app/services/youtube_service.py` 완전 재작성**

기존 구현의 치명적 버그:

1. `upload()` 가 `async def` 로 선언되어 있었는데 라우터에서 `def upload_to_youtube` 안에서 동기 호출했음. 파이썬이 **코루틴 객체만 돌려주고 실제 업로드는 시작도 안 됨**. 결과로 받은 코루틴을 문자열인 양 `project.youtube_url` 에 대입.
2. 라우터는 `is_public`, `is_unlisted` 두 bool 인자를 넘기는데, 서비스 시그니처엔 이 인자들이 존재하지 않고 `privacy="private"` 한 개의 문자열만 받음 → `TypeError` 즉사.
3. 서비스는 `{"video_id": ..., "url": ...}` dict 를 반환하는데 라우터는 이걸 문자열 URL 로 취급.
4. 라우터가 받은 `language` 필드를 서비스에 전달하지 않고 버림. 서비스는 `defaultLanguage="ko"` 하드코딩.
5. 썸네일 파이프라인 부재. 서비스엔 `thumbnail_path` 파라미터가 있었지만 라우터는 아예 전달 안 함.

수정 내용:

- **동기화**: `upload()` 를 `def` (sync) 로 고정. `googleapiclient` 의 resumable upload 는 내부적으로 블로킹이므로 async 로 포장해 봐야 실익 없음. 라우터에서 `asyncio.to_thread(uploader.upload, ...)` 로 감싸 이벤트 루프 블로킹 방지.
- **시그니처 정리**: `upload(video_path, title, description, tags=None, thumbnail_path=None, privacy="private", language=None, category_id=None, made_for_kids=False, progress_callback=None) -> dict`. 모든 파라미터 명시적 문서화.
- **Privacy enum**: `VALID_PRIVACY = {"private", "unlisted", "public"}` 집합으로 런타임 검증. 잘못된 값이면 `YouTubeUploadError`.
- **전용 예외**: `YouTubeAuthError`, `YouTubeUploadError` 두 클래스로 분리. 라우터에서 각각 401/500 으로 매핑.
- **Non-destructive 인증 체크**: `is_authenticated()` 메서드 — token.json 존재 여부만 확인, 브라우저 팝업 없음. 프론트에서 주기적으로 상태 확인 용도.
- **Scope 확장**: 썸네일 API 호출을 위해 `https://www.googleapis.com/auth/youtube` 스코프 추가.

**라우터 재작성 — `backend/app/routers/youtube.py`**

엔드포인트 재정리:

- `GET /api/youtube/auth/status` (신규): token.json 유효성 non-destructive 체크. 프론트에서 OAuth 상태 배지로 사용.
- `POST /api/youtube/auth`: OAuth 로컬 서버 플로우 트리거. `run_local_server` 는 블로킹이라 `asyncio.to_thread` 로 감쌈. 기존 방식 유지(사용자 선택).
- `POST /api/youtube/{project_id}/thumbnail` (신규): 썸네일 생성. 요청 바디로 `title`, `cut_number` 선택 가능.
- `GET /api/youtube/{project_id}/thumbnail` (신규): 생성된 썸네일 PNG 다운로드 (`FileResponse`).
- `POST /api/youtube/{project_id}/upload`: 업로드 본체. Pydantic 스키마를 `Literal["private","unlisted","public"]` 로 강제. 최종 영상은 `final_with_subtitles.mp4` → `merged.mp4` 순으로 탐색. `use_generated_thumbnail: bool` 플래그로 이전에 생성한 썸네일 자동 첨부.

**신규 — `backend/app/services/thumbnail_service.py`**

Pillow 만 써서 결정론적으로 썸네일을 생성합니다. 추가 API 비용 0원.

- 입력: 프로젝트의 첫 번째 `image_path` 가 있는 컷 이미지 (수동 `cut_number` 지정 가능).
- 처리: `_cover_resize()` 로 1280×720 cover crop → 25% 어둡게 블렌드 → 하단 45% 에 반투명 검은 오버레이(`alpha=160`) → 제목 텍스트를 흰색 볼드 + 검정 stroke(3px) 로 렌더.
- 줄바꿈: `_wrap_text()` 가 단어 단위로 우선 줄바꿈하고, 한글처럼 띄어쓰기가 적어 단어 하나가 너무 길면 문자 단위로 폴백. 폰트 크기는 110→96→84→74→66→58→52→46 후보 중 3줄 이내에 들어가는 가장 큰 크기 선택.
- 폰트 탐색: Windows(`malgunbd.ttf`), Linux(`NanumGothicBold`, `DejaVuSans-Bold`), macOS(`AppleSDGothicNeo`) 순서로 탐색. 전부 실패하면 `ImageFont.load_default()` 로 폴백.
- 구버전 Pillow 호환: `draw.text(..., stroke_width=..., stroke_fill=...)` 를 지원하지 않는 환경에서는 `TypeError` 를 잡고 stroke 없이 렌더.
- 출력: `DATA_DIR/{project_id}/output/thumbnail.png`, `/assets/{project_id}/output/thumbnail.png` 로 프론트에서 즉시 접근 가능.

**프론트 — `frontend/src/lib/api.ts`**

- `YouTubePrivacy = "private" | "unlisted" | "public"` 타입.
- `YouTubeUploadRequest`, `YouTubeUploadResult`, `YouTubeAuthStatus`, `ThumbnailGenerateRequest`, `ThumbnailGenerateResult` 인터페이스.
- `youtubeApi.authStatus()`, `youtubeApi.authenticate()`, `youtubeApi.generateThumbnail()`, `youtubeApi.upload()` 네 개 바인딩.

**프론트 — `frontend/src/components/studio/StepYouTube.tsx` (신규)**

4개 섹션으로 구성된 업로드 패널:

1. **OAuth 상태 카드**: 마운트 시 `authStatus()` 폴링 → 녹색 `ShieldCheck` 또는 노란색 `ShieldAlert` 배지. 인증 안 됨이면 "Google 계정으로 인증" 버튼 표시. 누르면 백엔드가 `flow.run_local_server(port=8090)` 를 열고 브라우저 팝업 → 동의 → 토큰 저장. 최초 1회만 필요.
2. **메타데이터 폼**: 제목(100자 카운터), 설명(5000자 카운터), 태그(쉼표 구분), 공개 범위 3단계 라디오 (private/unlisted/public 각각 설명문 포함), 아동용 콘텐츠 체크박스.
3. **썸네일 카드**: "썸네일 생성" 버튼 → `generateThumbnail()` 호출 → 응답의 `thumbnail_url` 을 `?t={Date.now()}` 캐시 버스터와 함께 `<img>` 로 표시. 16:9 프리뷰 박스. 이미지가 없는 프로젝트는 "이미지가 생성된 컷이 없어서..." 안내 메시지. `disabled` 처리.
4. **업로드 카드**: "YouTube 에 업로드" 버튼. `authenticated === false` 이면 `disabled`. 성공 시 녹색 카드에 `video_url` 링크(새 탭). 썸네일 부분 실패 시 노란색 경고 배너로 `thumbnail_error` 노출 (영상 업로드 자체는 성공 처리).

**프론트 — `frontend/src/app/studio/[projectId]/page.tsx`**

- `STEPS` 배열 6개 → 7개 확장: `{ num: 7, name: "유튜브" }` 추가.
- `renderStepContent()` 에 `case 7: <StepYouTube />` 추가.
- `stepStates["7"]` 자동 감지: `project.youtube_url` 이 truthy 면 `completed` (이미 업로드된 프로젝트 복귀 시 녹색 체크).
- **사이드바 조건부 렌더**: 새 `isPipelineStep = step.num >= 2 && step.num <= 6` 로 파이프라인 스텝(2~6)과 수동 스텝(1, 7) 분리. 유튜브 스텝은 진행률 바/ETA/일시정지 컨트롤을 그리지 않고 "수동 업로드" 라벨만 표시. 파이프라인 API 가 step 7 을 모르기 때문에 `pauseStep(7)` 등 호출하면 404 가 나는 것을 사전에 차단.

**검증**

- `py_compile` 통과 (youtube_service.py, thumbnail_service.py, routers/youtube.py, main.py).
- `tsc --noEmit -p .` 통과.
- 모든 버전 파일 1.1.20 일치 (main.py 2곳, version.ts, package.json, package-lock.json 2곳).

**미처리/주의사항 (의도적으로 뺌)**

- `progress_callback` 훅은 서비스에 있지만 프론트로 연결되는 WebSocket/SSE 는 아직 없음. 업로드 진행률 UI 는 "업로드 중..." 스피너만. 큰 파일은 긴 시간 걸릴 수 있음.
- `client_secret.json` / `token.json` 은 `backend/` 루트에 저장됨. `.gitignore` 에 이미 들어있는지는 확인 필요 (현 PR 에서 수정 안 함).
- `YOUTUBE_CLIENT_ID` / `YOUTUBE_CLIENT_SECRET` 환경변수는 사용자가 직접 Google Cloud Console 에서 OAuth 2.0 Desktop 앱 credentials 를 만들어서 `.env` 에 넣어야 합니다.

## v1.1.19 (2026-04-10)

### 변경 — 스튜디오 페이지 레이아웃 재구성

사용자 요청으로 `frontend/src/app/studio/[projectId]/page.tsx` 의 상단 가로 스텝 탭을 **좌측 세로 사이드바**로 이동했습니다. 또한 최상단에 **대시보드 진입 버튼**을 추가했습니다.

**주요 변경점**

- **레이아웃 구조**: 기존 `min-h-screen > (Top bar) > (Horizontal Steps) > (Controls) > (Content)` 세로 스택 → `min-h-screen flex-col > (Top bar) > flex-row { (aside w-72 sidebar) + (main flex-1) }` 로 재구성. 메인 영역은 `overflow-y-auto` 로 독립 스크롤.
- **세로 스텝 사이드바**: 6개 스텝이 세로로 나열되고, 각 스텝은 `w-9 h-9` 원형 인디케이터 + 이름 + 진행률 바 + 상태 뱃지 + ETA 로 구성. 원 사이사이 세로 연결선(`absolute left-[22px] top-[44px]`)이 진행 흐름을 시각화합니다. 연결선은 `state === "completed"` 이면 녹색으로 바뀝니다.
- **원형 인디케이터**: 새 `stepCircle()` 헬퍼 도입. `completed` 체크, `running` 스피너, `paused` 일시정지, `failed` 경고, `pending` 은 숫자(1~6) 를 표시. 색상은 각 상태에 맞춰 border/bg/text 동기화.
- **상단 대시보드 버튼**: 기존 `<ArrowLeft />` 아이콘만 있던 자리에 `<LayoutDashboard /> 대시보드` 버튼으로 교체. 테두리 있는 패딩 버튼 스타일로 시각적 비중 강화. `href="/"` 로 대시보드 페이지 이동.
- **다운로드 버튼 이동**: 기존에 별도 `Controls` 영역에 있던 "다운로드" 버튼을 상단 바 우측 (API 비용 옆) 으로 옮김. `Controls` 영역 자체 제거.
- **미사용 import 정리**: `ArrowLeft`, `SkipForward`, `Square`, `Clock` 제거. `LayoutDashboard` 추가.

**보존된 기능**

- 스텝 클릭으로 `activeStep` 전환 (기존 동일).
- 각 스텝의 일시정지/이어하기/초기화 버튼 그대로 유지.
- 진행률 % · 컷 수 · ETA 계산 로직 그대로 유지.
- `stepStates` 자동 감지 로직(cut.audio_path/image_path/video_path 기반) 그대로 유지.
- 2초 간격 폴링 로직 그대로 유지.

**정리**

- 기존 `stepIcon()` 헬퍼는 새 `stepCircle()` 로 완전히 대체되므로 파일에서 제거 (미사용 warning 방지).
- `Clock` lucide 아이콘 import 제거 (`stepIcon` 에서만 쓰였음).

**검증**

- TypeScript 파싱 통과 (Next.js 파서).

## v1.1.18 (2026-04-10)

### 수정 — 자막 스타일 설정이 결과에 반영 안 되던 문제

사용자가 프로젝트 설정에서 자막 위치(position), 폰트, 크기, 색상 등을 바꿔도 최종 렌더에 반영되지 않는 버그. `subtitle_service.generate_ass` 코드를 추적한 결과 세 개의 독립적인 문제가 있었습니다.

**문제 1 — `position` 값이 완전히 무시됨**

기존 코드는 `style_config["position"]` 을 **아예 읽지 않고** Alignment 를 하드코딩 `2` (하단 중앙) 로 박아놨습니다. UI 에서 "중앙" 이나 "상단" 을 선택해도 ASS 파일엔 항상 `Alignment=2` 가 들어갔고, 결과적으로 자막이 항상 영상 하단에만 나왔습니다.

수정: `_POSITION_TO_ALIGNMENT` 매핑을 도입해 ASS 의 numpad 배치 표준을 따름. `bottom → 2`, `center → 5`, `top → 8` (추가로 `bottom-left/right`, `top-left/right` 도 지원).

**문제 2 — ASS Format 라인이 비표준 축소형**

기존 Format 은 `Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BorderStyle, Outline, Shadow, Alignment, MarginV` 10개 필드만 선언했고 `SecondaryColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, MarginL, MarginR, Encoding` 13개가 누락. libass 는 비표준 축소형도 받긴 하지만, 엄격한 파서나 플레이어에서는 필드 offset 이 밀려 색상이 엉뚱한 슬롯으로 들어가거나 style 이 통째로 무시될 수 있습니다. `ScaledBorderAndShadow` 디렉티브도 없어 PlayRes 와 실해상도가 다르면 outline 크기가 깨졌습니다.

수정: libass 의 공식 V4+ Styles Format 23필드 전체를 명시. `ScaledBorderAndShadow: yes` 추가. `WrapStyle: 2` 추가로 긴 문장 자동 줄바꿈. `BackColour` 에 반투명 검은색(`&H64000000`) 지정해 BorderStyle=1 에서 그림자가 제대로 표현됨.

**문제 3 — `PlayResX/Y` 항상 1920x1080 고정**

기존엔 프로젝트가 9:16 (숏폼) 이든 1:1 이든 상관없이 PlayRes 를 `1920x1080` 으로 박아놨습니다. libass 는 `PlayResY` 대비 `Fontsize` 를 상대적으로 스케일하므로, 실제 출력이 1080x1920 (세로) 인데 PlayResY 가 1080 이면 폰트가 "설정한 것보다 작게" 또는 "테두리가 얇게" 나옵니다.

수정: `_play_resolution(aspect_ratio)` 헬퍼로 `16:9 → 1920x1080`, `9:16 → 1080x1920`, `1:1 → 1080x1080`. `subtitle.py::_build_and_write_ass` 에서 `project.config["aspect_ratio"]` 를 꺼내 `generate_ass` 에 전달.

**부수 개선**

- `_hex_to_ass_color()` 헬퍼로 hex → ASS `&HAABBGGRR` 변환 로직 단일화. 잘못된 색상 입력 시 흰색으로 폴백.
- `outline_width`, `shadow`, `margin_v`, `bold` 를 `style_config` 파라미터로 수용 (기본값 유지). 폰트 이름에 "bold" 가 포함되면 Bold flag 기본 on.
- Dialogue 텍스트에서 `\r`, `\n` 을 ASS 줄바꿈 escape `\N` 으로 변환해 자막에 개행이 있어도 이벤트가 깨지지 않도록.
- `generate_ass(cuts, style_config, aspect_ratio="16:9")` — aspect_ratio 기본값이 있어 기존 호출부는 호환.

**프론트엔드 — `StepSubtitle.tsx` 미리보기도 position 반영**

자막 스타일 미리보기의 샘플 텍스트가 항상 `bottom-8` 로 고정돼 있어 UI 에서 "중앙" 을 골라도 미리보기엔 하단에 표시됐습니다. 사용자가 실제 ASS 결과와 비교할 수 없었던 이유.

수정: position 값에 따라 `top-8` / `top-1/2 -translate-y-1/2` / `bottom-8` 으로 동적 정렬. 폰트 이름에 "bold" 가 들어가면 `fontWeight: 700` 적용. 테두리 shadow 도 4방향 + blur 로 보강해 실제 burn-in 결과에 더 가깝게 미리보기.

**결과**

이제 프로젝트 설정에서 자막 위치를 "중앙" 으로 바꾸면 미리보기도 중앙에 표시되고, 실제 렌더된 mp4 도 중앙에 자막이 박힙니다. 9:16 숏폼 프로젝트에서도 폰트 크기가 올바르게 스케일됩니다.

## v1.1.17 (2026-04-10)

### 수정 — 최종 렌더링에 음성이 없던 문제

v1.1.16 에서 렌더링 플로우 자체는 정상 동작했지만, 결과 영상에 소리가 없었습니다. 원인 추적:

- 사용자가 Seedance (fal.ai) 로 비디오를 생성했을 때, fal.ai 의 image-to-video 모델은 **원래 무음 mp4** 를 만듭니다. `fal_service.py::generate` 는 생성된 무음 mp4 에 TTS 오디오를 mux 해서 최종 저장하는 로직을 가지고 있지만, v1.1.14 이전 버전에서는 ffmpeg 를 찾지 못하면 mux 를 스킵하고 **원본 무음 mp4 를 그대로 저장**했습니다.
- 그 상태에서 사용자가 v1.1.16 으로 업그레이드해 최종 렌더만 다시 돌린 경우, merge → burn_subtitles 파이프라인은 입력 클립에 이미 오디오가 없었기 때문에 출력에도 당연히 오디오가 없었습니다. `FFmpegService.burn_subtitles` 의 `-c:a copy` 는 "있는 오디오를 복사" 할 뿐 없는 오디오를 만들지는 못합니다.

**백엔드 변경 — `app/routers/subtitle.py`**

새 헬퍼 두 개 추가:

- `_video_has_audio(ffmpeg_bin, video_path)` — `ffmpeg -hide_banner -i <file>` 의 stderr 를 검사해 `" Audio:"` 문자열 유무로 오디오 stream 존재 여부를 판정. 별도 ffprobe 바이너리가 필요 없음.
- `_heal_cut_audio(project_id, db)` — 모든 cut 을 순회하며:
  1. 비디오 파일이 존재하는지 확인
  2. `_video_has_audio` 로 오디오 유무 probe
  3. 오디오가 없고 `cut.audio_path` 의 TTS 파일이 디스크에 있으면 → in-place mux (`-map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -shortest`) 후 `os.replace` 로 원본 덮어쓰기
  4. `{checked, healed, failed, skipped_no_audio_file}` 요약 반환
- 오디오 probe 실패 시엔 "있다" 고 가정 → 멀쩡한 파일이 손상되지 않도록 보수적으로 동작
- mux 성공 후 `os.replace` 는 원자적이므로 중간 실패 시 원본 파일은 그대로 보존됨

**render 엔드포인트 개선**

- merge 직전에 `_heal_cut_audio` 호출. 실행 시간과 summary 를 `[subtitle/render] audio heal done in Xs: {...}` 로 로깅
- heal 이 한 개라도 성공했으면 **기존 `merged.mp4` 를 삭제**. 이유: 기존 merged 는 무음 원본들로 만들어진 stale 파일이고, 그 위에 다시 concat 해봐야 여전히 무음이므로 강제로 재merge 해야 함
- heal 예외는 **non-fatal** — 렌더 전체를 멈추지 않고 경고 로그 후 계속 진행 (원본이 이미 오디오를 가진 정상 케이스는 heal 을 건너뛰므로 영향 없음)

**결과**: 과거 무음으로 저장된 Seedance/LTX/Kling 클립도 render 시점에 자동으로 복구되고, 복구가 일어나면 stale merged 를 지워 새로운 merge + burn_subtitles 가 오디오 포함된 최종 영상을 만듭니다. 앞으로 fal_service 가 정상적으로 mux 한 클립은 probe 통과해서 heal 을 스킵하므로 오버헤드 없음.

## v1.1.16 (2026-04-10)

### 수정 — 최종 영상 다운로드 404 + 자막 UI 재구성

v1.1.15 에서 렌더링은 잘 됐지만 "최종 영상 다운로드" 버튼을 누르면 Next.js 의 404 페이지가 떴습니다. 원인: 백엔드가 반환한 `download_url` 이 `/assets/<id>/output/final_with_subtitles.mp4` 라는 **상대 경로**였고, 프론트는 그걸 그대로 `<a href>` 에 넣었기 때문에 브라우저가 프론트 도메인(`localhost:3000`) 기준으로 해석해서 404 가 났습니다. 실제 정적 파일은 백엔드(`localhost:8000`)의 `/assets` 마운트에 있습니다.

더불어 자막 스텝 UI 자체도 재구성했습니다. 기존엔 "자막 스타일 미리보기" 검은 박스 + "1. 자막 생성" 카드 + "2. 최종 렌더링" 카드 3개가 따로 놀고, 렌더링이 끝나도 미리보기 박스는 여전히 정적 샘플 텍스트를 보여줬습니다.

**백엔드 변경 — `app/routers/subtitle.py`**

- 자막 생성 로직을 `_build_and_write_ass()` 헬퍼로 추출 (generate / render 두 엔드포인트가 공유)
- `render_video_with_subtitles` 에서 `subtitles.ass` 가 없으면 자동으로 생성 → UI 에서 별도의 "자막 생성" 버튼이 없어도 렌더 한 번으로 끝
- 자동 생성 실패 시 traceback 로그 + 명확한 에러 메시지

**프론트엔드 변경 — `frontend/src/lib/api.ts`**

- `ASSET_BASE = "http://localhost:8000"` 상수 추가
- `resolveAssetUrl(pathOrUrl)` 헬퍼: 절대 URL 은 passthrough, 슬래시로 시작하는 경로는 `ASSET_BASE` prefix, 그 외는 `${ASSET_BASE}/` prefix
- 기존 `assetUrl(projectId, relative)` 도 `ASSET_BASE` 를 사용하도록 리팩터

**프론트엔드 변경 — `components/studio/StepSubtitle.tsx`**

- "1. 자막 파일 생성" 카드 **삭제**. `generateSubtitle` 함수, `Wand2` / `UploadIcon` import, `GenerationTimer` 사용 모두 제거. 렌더 버튼 하나로 통합
- 미리보기 영역을 **통합 상태 패널**로 재설계:
  - 기본 상태 → 기존 스타일 샘플 텍스트 ("자막 미리보기 텍스트입니다.")
  - 렌더링 중 → 중앙에 큰 스피너 + "렌더링 중... N초 경과" + 안내 문구
  - 렌더 완료 → `<video controls>` 로 최종 결과 영상 인라인 재생
- 패널 제목도 상태에 따라 "자막 스타일 미리보기" / "렌더링 진행" / "최종 결과 영상" 으로 바뀜
- 성공 메타데이터 (소요 시간, 파일 크기, 다운로드 버튼) 는 패널 아래에 한 줄로 붙음
- 다운로드 링크는 `resolveAssetUrl(renderResult.download_url)` 로 절대 URL 변환 + `download` 속성 추가
- 최종 렌더링 카드 레이아웃 변경 → 설명 + 버튼 한 줄, 다시 렌더 시 버튼 텍스트 "다시 렌더링"

결과: 사용자는 렌더 버튼 한 번 누르면 (자막 자동 생성 → merge fallback → 번인 → 재생) 까지 한 흐름으로 진행되고, 끝나면 바로 미리보기 영역에서 영상을 재생하거나 다운로드할 수 있습니다.

## v1.1.15 (2026-04-10)

### 수정 — 최종 렌더링 UI 무반응 문제 (`눌럿는데 로딩 좀하더니 아무 반응 없는데?`)

v1.1.14 에서 ffmpeg 가 실제로 동작하기 시작했지만, 사용자 관점에서는 여전히 "로딩 돌다가 끝나고 아무 변화 없음" 으로 보였습니다. 코드 플로우를 추적한 결과 세 가지가 동시에 문제였습니다:

1. **백엔드**: `subtitle.py::render_video_with_subtitles` 는 `final_with_subtitles.mp4` 는 잘 만들었지만 DB 의 `step_states["6"]` 이나 `current_step` 을 업데이트하지 않음 → 프론트가 `onUpdate()` 로 재fetch 해봐야 프로젝트 상태가 똑같음
2. **백엔드**: 응답에 파일 경로만 있고 다운로드 URL/크기/소요 시간 같은 "성공했음을 보여줄" 메타데이터가 없었음
3. **프론트**: `renderFinal` 은 성공 시 아무 UI 피드백도 주지 않고 조용히 `onUpdate()` 만 호출

**백엔드 변경 — `app/routers/subtitle.py`**

- 렌더링 시작/종료/소요시간 로그 추가 (`[subtitle/render] START ... DONE ...`)
- merge fallback / burn_subtitles 각각 타이머 + traceback 로그
- `burn_subtitles` 완료 후 `output_path.exists()` 명시 검증
- DB 영속화: `project.step_states["6"] = "completed"`, 필요 시 `current_step = 6` 로 올림
- 응답에 추가: `size` (bytes), `elapsed_seconds`, `download_url` (`/assets/{project_id}/output/final_with_subtitles.mp4`)

**프론트엔드 변경 — `components/studio/StepSubtitle.tsx`**

- `renderResult` / `renderElapsed` state + `renderTimerRef` 추가
- `useEffect` 로 렌더링 중일 때 0.5초마다 경과 시간 갱신, 완료/언마운트 시 interval 정리
- 렌더링 중: 스피너 + "렌더링 중... N초 경과" + 안내 문구를 담은 카드 표시
- 렌더링 성공: 녹색 success 카드에 `CheckCircle2` 아이콘 + 소요 시간 + 파일 크기(MB) + 최종 영상 다운로드 버튼 표시
- `renderFinal` 이 응답을 `RenderResult` 로 저장, 다음 렌더 전에 초기화

이제 사용자는 렌더 버튼을 누르면 (1) 실시간 경과 시간을 보고, (2) 완료 후 명확한 성공 카드와 함께 바로 다운로드할 수 있습니다.

## v1.1.14 (2026-04-10)

### 수정 — ffmpeg 바이너리 자동 탐색 (`FFmpeg not found in PATH` 해결)

v1.1.13 의 자동 merge fallback 은 정상 동작했지만, `FFmpeg not found in PATH` 로 죽었습니다. 사용자 Windows 환경의 Python 프로세스 PATH 에 ffmpeg 가 등록돼있지 않은 것이 원인입니다. 지금까지 bare 문자열 `"ffmpeg"` 를 subprocess 에 넘겼기 때문에 Python 의 subprocess 는 PATH 에서만 찾고 포기했습니다.

**새 모듈 — `subprocess_helper.find_ffmpeg()`**

우선순위 순으로 ffmpeg 바이너리를 찾습니다:

1. `FFMPEG_BIN` / `FFMPEG_PATH` 환경변수 (절대경로)
2. `shutil.which("ffmpeg")` / `("ffmpeg.exe")` — PATH 조회
3. 흔한 Windows 설치 위치:
   - `C:\ffmpeg\bin\ffmpeg.exe`
   - `C:\Program Files\ffmpeg\bin\ffmpeg.exe`
   - `C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe`
   - scoop: `~\scoop\shims\ffmpeg.exe`, `~\scoop\apps\ffmpeg\current\bin\ffmpeg.exe`
   - winget: `~\AppData\Local\Microsoft\WinGet\Links\ffmpeg.exe`
   - chocolatey: `C:\ProgramData\chocolatey\bin\ffmpeg.exe`
4. `imageio-ffmpeg` 패키지의 번들 바이너리 — **requirements.txt 에 추가**. 사용자가 별도 설치 없이도 백엔드 재시작만 하면 ffmpeg 가 자동으로 작동하게 하는 마지막 안전망입니다.
5. 실패 시 한국어로 3가지 해결 방법을 안내하는 `RuntimeError`.

결과는 `@lru_cache` 로 캐싱되므로 첫 호출 이후엔 즉시 반환됩니다.

**교체된 호출 사이트**

- `ffmpeg_service.py` — 4곳 (generate×2, merge_videos, burn_subtitles) 전부 `_resolve_ffmpeg_cmd()` 헬퍼로 감싸서 첫 번째 토큰을 resolved path 로 교체
- `fal_service.py::generate` — mux 경로에서 `find_ffmpeg()` 호출, 실패 시 mux 스킵
- `kling_service.py::generate` — 동일

**진단 강화**

- **startup 로그**: `lifespan()` 에서 `find_ffmpeg()` 를 호출해 `[startup] ffmpeg OK: {path}` 또는 `[startup] ffmpeg NOT FOUND: ...` 출력. 백엔드 뜨자마자 상태 확인 가능.
- **API 엔드포인트**: `GET /api/api-status/ffmpeg` → `{ok, path, source, version}` 반환. `source` 는 path / imageio-ffmpeg / scoop / winget / chocolatey 등. `-version` 실행 결과의 첫 줄도 함께 반환.

**자막 렌더 사이드 수정**

`burn_subtitles` 의 libass 필터는 Windows 경로에서 `:` (드라이브 letter) 를 escape 해야 정상 작동합니다. `sub_escaped = subtitle_path.replace("\\", "/").replace(":", r"\:")` 로 처리.

**사용자 즉시 조치**

`pip install -r backend/requirements.txt` 로 `imageio-ffmpeg` 만 설치하면 그 뒤엔 자동. 이미 ffmpeg 를 따로 설치한 경우엔 `set FFMPEG_BIN=C:\full\path\to\ffmpeg.exe` 로 직접 지정하는 것도 가능합니다.

---

## v1.1.13 (2026-04-10)

### 수정 — 자막 렌더 단계 3종 버그 + merge 에러 은폐 수정

사용자가 v1.1.12 로 재시작해서 영상 단계를 정상 통과한 뒤, 자막 렌더 버튼에서 `렌더링 실패: Merged video not found. Generate videos first.` 경고가 떴습니다. 원인은 세 겹으로 겹쳐있었습니다.

**버그 1 — `subtitle.py` 가 존재하지 않는 메서드 호출.** `render_video_with_subtitles()` 가 `ffmpeg_service.add_subtitles(...)` 를 호출하는데, `FFmpegService` 에는 `add_subtitles` 가 없고 실제 메서드 이름은 `burn_subtitles` 입니다. 이 경로에 도달하면 `AttributeError` 가 터집니다.

**버그 2 — sync 라우터가 async 메서드 호출.** `render_video_with_subtitles()` 가 `def` (sync) 로 선언돼있는데 호출 대상인 `burn_subtitles` 는 `async`. 즉 `await` 없이 호출되면 coroutine 이 생성만 되고 실행되지 않아 `RuntimeWarning: coroutine was never awaited` 와 함께 결과 파일이 안 만들어집니다. `async def` 로 승격 필요.

**버그 3 — `video.py` 의 merge 실패가 은폐됨.** 이게 지금 실제로 터진 에러의 원인입니다. `video.py::_run()` 의 merge 블록은 `except Exception as merge_err: print(...)` 만 하고 태스크는 여전히 `completed` 로 마킹합니다. resume 경로는 더 심한 `except: pass`. 그래서 merge 단계가 조용히 실패해도 UI 엔 **영상 완료** 로 표시되고, 다음 단계인 자막 렌더가 `merged.mp4` 를 찾을 때서야 에러가 드러납니다.

v1.1.11 환경에서 생성된 프로젝트는 ffmpeg `merge_videos` 가 아직 `create_subprocess_exec` 를 쓰던 시절에 `NotImplementedError` 로 터졌을 가능성이 높습니다. 개별 컷 파일은 만들어졌지만 `merged.mp4` 가 없는 상태로 DB 에만 "완료" 로 박혀있게 됐습니다.

**수정 1 — `subtitle.py::render_video_with_subtitles` 전면 재작성:**

- `def` → `async def`
- `ffmpeg_service.add_subtitles(...)` → `await FFmpegService.burn_subtitles(...)`
- **자동 merge fallback** 추가: `merged.mp4` 가 없으면 DB 에서 `cuts.video_path` 들을 순서대로 읽어 존재하는 파일만 모아 `merge_videos` 를 즉석 실행. 성공하면 그 merged.mp4 로 계속 진행. 이로써 v1.1.11 이전 프로젝트도 "다시 영상 생성" 없이 자막 단계에서 복구 가능.
- 에러 발생 시 `{ExceptionType}: {msg}` 형태로 HTTPException 메시지 반환.

**수정 2 — `video.py` merge 에러 surface:**

두 군데(_run 메인 경로, resume 경로) 모두 merge 실패 시 traceback tail 을 `record_item_error(..., cut_number=0, ...)` 로 태스크 매니저에 기록합니다. cut_number=0 은 특정 컷이 아니라 merge step 전용 마커. UI 에러 카드에 `MERGE FAILED — ...` 로 바로 표시됩니다. "자막 렌더 단계에서 자동 재시도합니다" 라는 가이드도 함께 첨부.

**예상:** 지금 있는 프로젝트에서 "최종 렌더링" 버튼만 다시 누르면 subtitle.py 의 fallback merge 가 작동해서 `merged.mp4` 를 즉석 생성하고 자막 번인까지 완료됩니다. 앞으로 새 프로젝트에서 merge 가 실패하면 UI 에 에러가 **정확하게** 표시됩니다 — 더이상 은폐 안됨.

---

## v1.1.12 (2026-04-10)

### 수정 — Windows `NotImplementedError` 완전 제거 (`asyncio.to_thread` 우회)

v1.1.11 의 이벤트 루프 정책 고정이 **먹히지 않았습니다**. traceback 이 정확히 원인 지점을 알려줬습니다:

```
NotImplementedError: (no message)
--- transport, protocol = await loop.subprocess_exec(
File "...Python312\Lib\asyncio\base_events.py", line 1756, in subprocess_exec
  transport = await self._make_subprocess_transport(
File "...Python312\Lib\asyncio\base_events.py", line 528, in _make_subprocess_transport
  raise NotImplementedError
```

진단 그대로 — Windows `SelectorEventLoop` 에서 subprocess 미지원. 문제는 uvicorn `--reload` 와 FastAPI BackgroundTasks 조합에서 `main.py` 상단의 `set_event_loop_policy()` 가 실행 시점에 영향을 못 미친다는 점입니다. uvicorn reloader 의 자식 프로세스, 스레드풀에서 생성되는 loop 등 경로가 여러 개라 정책 push 만으론 모든 케이스를 막을 수 없습니다.

**정공법 수정:** 이벤트 루프 종류와 무관하게 동작하도록 **모든 `asyncio.create_subprocess_exec` 호출을 `asyncio.to_thread(subprocess.run, ...)` 로 교체**했습니다. 동기 `subprocess.run` 은 어떤 루프/어떤 플랫폼에서도 동작하고, `asyncio.to_thread` 는 기본 ThreadPoolExecutor 에서 실행해서 이벤트 루프를 블로킹하지 않습니다.

**신규 헬퍼:** `backend/app/services/video/subprocess_helper.py` — `async run_subprocess(cmd, timeout, capture_stdout, capture_stderr) -> (returncode, stdout_bytes, stderr_bytes)`. 타임아웃 시 `asyncio.TimeoutError`, 실행파일 없을 때 `FileNotFoundError` 를 그대로 전파합니다.

**교체된 호출 사이트 (5곳):**

1. `ffmpeg_service.py::_run_ffmpeg` — Ken Burns 로컬 렌더
2. `ffmpeg_service.py::merge_videos` — concat 병합
3. `ffmpeg_service.py::burn_subtitles` — 자막 번인
4. `fal_service.py::generate` — fal.ai 결과 영상 + 오디오 mux
5. `kling_service.py::generate` — Kling 결과 영상 + 오디오 mux

동작 의미는 100% 동일합니다 (stdout 캡처 여부, stderr 캡처, 타임아웃, rc 체크 전부 기존과 매칭). 단지 async wrapper 만 바뀌었습니다.

v1.1.11 의 `WindowsProactorEventLoopPolicy` 강제 코드는 **그대로 유지**합니다 — 혹시 다른 경로에서 직접 asyncio subprocess 를 건드리는 코드가 추가되더라도 안전망 역할.

**예상:** `NotImplementedError` 완전 제거. 모든 컷에서 fal/kling/ffmpeg 정상 동작.

---

## v1.1.11 (2026-04-10)

### 추가 — 신규 영상 모델 5종 (가격/성능 리서치 반영)

사용자 요청("지금 영상 제작 모델들 보다 더 저렴하고 성능 좋거나 쓰기 좋은거 더 찾어봐")에 따라 2026-04 시점 이미지-투-비디오 시장을 조사해서 아래 5종을 추가했습니다. 전부 fal.ai queue API 를 통하며 기존 `FalVideoService` 에 모델 ID 매핑만 추가하는 형태라 런타임 코드 변경은 없습니다.

- **LTX Video 2.0 Fast** (`ltx2-fast`) — $0.04/s (1080p). 현재 라인업 최저가.
- **LTX Video 2.0 Pro** (`ltx2-pro`) — $0.06/s (1080p). Lightricks 의 상위 품질 버전.
- **Seedance 1.5 Pro** (`seedance-1.5-pro`) — $0.047/s, 720p + native audio. 기존 Seedance 1.0 Pro($0.124/s) 대비 **62% 저렴**하면서 네이티브 오디오까지 지원.
- **Kling 2.5 Turbo Pro** (`kling-2.5-turbo`) — $0.07/s. Artificial Analysis Video Arena 2026 **벤치마크 1위**.
- **Kling 2.6 Pro** (`kling-2.6-pro`) — Kling 최신 프리미엄. 네이티브 오디오 생성 포함.

기존 `seedance-1.0` 과 `kling-v2` 는 "legacy" 표기로 유지 (하위호환).

### 수정 — Windows asyncio `NotImplementedError` 방지

v1.1.10 배포 후 Seedance 1.0 Lite 선택 시 5개 컷 전부 `NotImplementedError:` (메시지 없음) 로 실패했습니다. 코드에 `raise NotImplementedError` 가 없고, 메시지가 비어있는 것은 **Python 내장 asyncio 에서 지원되지 않는 operation 호출** 시의 시그니처입니다.

가장 유력한 원인은 Windows 에서 asyncio 이벤트 루프가 기본값인 `SelectorEventLoop` 로 올라왔을 경우 `asyncio.create_subprocess_exec()` 가 `NotImplementedError` 를 던진다는 점입니다 (ffmpeg 호출용, audio mux 경로). `SelectorEventLoop` 은 Windows 에서 subprocess 를 지원하지 않습니다.

**수정:** `backend/app/main.py` 최상단에서 asyncio 가 import 되기 전에 `WindowsProactorEventLoopPolicy` 를 강제합니다.

```python
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
```

uvicorn 의 reload 워커가 자체 정책으로 덮어쓸 가능성에 대비해 `main.py` 가 로드되자마자 실행되도록 파일 맨 위에 배치했습니다.

### 수정 — UI 에러 카드에 traceback tail 노출

v1.1.10 의 에러 카드는 `{ExceptionType}: {str(e)}` 만 보여줘서 메시지가 빈 예외(`NotImplementedError:` 같은)가 나면 원인 지점을 알 수 없었습니다. 이제 `record_item_error()` 에 넘기는 메시지에 traceback 의 마지막 8줄을 함께 포함해서, 어느 파일/어느 함수에서 터졌는지가 UI 카드에 바로 보입니다.

```python
exc_line = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__}: (no message)"
err_msg = f"{exc_line}\n---\n{tail}"
```

`_run()` 과 resume 블록 두 곳 모두 동일하게 적용.

**예상:** v1.1.11 에서는 (1) Windows 이벤트 루프 수정으로 ffmpeg mux 경로가 정상 동작해서 `NotImplementedError` 가 사라지거나, (2) 만약 다른 원인이었다면 에러 카드의 traceback 으로 정확한 지점이 드러납니다. 둘 다 아니면 다음 라운드에 추가 진단.

---

## v1.1.10 (2026-04-10)

### 수정 — fal.ai status/result URL 경로 버그 (HTTP 405)

v1.1.9 배포 후 **submit 은 성공**하기 시작했지만(이미지 다운스케일 덕분), 그다음 status poll 에서 4컷 모두 `RuntimeError: Fal status HTTP 405` 로 죽었습니다. **405 Method Not Allowed** — POST 엔드포인트로 GET 을 보낸 전형적인 증상.

**원인.** fal.ai queue API 에서 submit 과 status/result 는 **경로 형태가 다릅니다**.

- Submit: `POST queue.fal.run/{full_model_path}` — 예: `fal-ai/bytedance/seedance/v1/pro/image-to-video`
- Status: `GET queue.fal.run/{app_id}/requests/{request_id}/status` — 여기서 `app_id` 는 앞 두 세그먼트만(`fal-ai/bytedance`)
- Result: `GET queue.fal.run/{app_id}/requests/{request_id}`

제 `fal_service.py` 는 status/result 도 full model path 로 조합하고 있었습니다. 그래서 fal.ai 는 `.../seedance/v1/pro/image-to-video/requests/{id}/status` 라는 존재하지 않는 GET 경로를 보고 405 를 돌려줬습니다. v1.1.2~1.1.8 에서 이 버그가 안 드러난 이유는 submit 자체가 403/JSONDecodeError 로 죽어서 status 단계에 **도달한 적이 없었기 때문**입니다. v1.1.9 에서 submit 이 뚫리니까 그 뒤의 버그가 처음으로 표면화됐습니다.

**수정 — 두 겹으로:**

1. fal.ai 가 submit 응답에 직접 넣어주는 `status_url` / `response_url` 를 **그대로 사용**합니다. 이게 fal.ai 의 권장 방식이고 가장 확실합니다.
2. 만약 응답에 그 필드가 없으면 `_app_id()` 헬퍼로 `self._fal_model.split("/")[:2]` 해서 `fal-ai/bytedance` 형태의 app id 를 뽑고 그걸 사용합니다. 이건 Seedance Lite/Pro 둘 다 커버됩니다.

백엔드 콘솔에 `[fal] status_url=...` 과 `[fal] result_url=...` 이 실제 사용된 URL 로 찍혀서 검증 가능합니다.

**같은 버그가 있던 진단 엔드포인트도 수정:**

v1.1.8 에서 추가한 `GET /api/api-status/fal/video-probe` 도 `fal_model` 을 그대로 박아서 dummy status 를 조회했습니다. 그래서 "키 유효" 판정이 405 가 404 로 해석되는 우연에 의존했던 건 아닙니다 — probe 는 전 버전에서 404 받았으니 인증 판정은 정확했지만, 이제부턴 app_id 경로로 질의하도록 수정해서 405 가 끼어들 여지를 없앴습니다.

**예상:** Seedance Pro 에서 6컷 정상 생성. 혹시 또 뭔가 터지면 에러 카드에 `[fal]` 로그가 정확한 HTTP 코드와 원문으로 나옵니다.

---

## v1.1.9 (2026-04-10)

### 수정 — fal.ai `JSONDecodeError` + 이미지 자동 다운스케일

v1.1.8 배포 후 키 진단은 통과했는데(결제 반영 완료) 실제 생성 시 6컷 모두
`JSONDecodeError: Expecting value: line 1 column 1 (char 0)` 로 다시 실패했습니다.
원인은 fal.ai queue 가 어느 단계에서 **빈 바디를 반환**했고 `resp.json()` 이 그대로 터진 것.
체계적으로 6컷 모두 같은 에러이므로 네트워크 플래키가 아니라 요청 자체 문제입니다.

**`backend/app/services/video/fal_service.py` 전면 보강:**

- 모든 HTTP 호출(submit / status poll / result fetch)에 대해 **status_code 와 body 앞 500자를 로그에 찍고**, `.json()` 실패 시 `_safe_json()` 이 `Fal {where} HTTP {code} non-JSON body (len=...): ...` 형태의 의미 있는 예외로 변환합니다. 이제 빈 바디가 터져도 UI 에러 카드에 정확히 어느 단계(submit / status / result)인지, 어떤 HTTP 코드였는지, raw 본문이 뭐였는지 그대로 드러납니다.
- HTTP 4xx/5xx 는 `raise_for_status()` 대신 직접 `RuntimeError(f"Fal ... HTTP {code}: {body[:400]}")` 로 던져서 body 를 잃지 않게 함.
- request_id 수신 시, poll 루프에서 30초마다 상태 로그.

**이미지 자동 다운스케일 — 빈 바디의 가장 흔한 원인 차단:**

fal.ai queue 는 큰 request body(특히 base64 data URL)를 받으면 proxy/gateway 가 빈 응답을 내뱉는 경우가 보고되어 있습니다. 이미지 생성 단계의 원본이 2048×2048 PNG 같은 것이면 base64 인코딩 후 3-6 MB 에 달하고, 이게 fal 앞단에서 조용히 잘릴 수 있습니다.

`_downscale_image_to_jpeg_bytes()` 를 추가해서 Pillow 가 설치돼 있으면:
- 긴 변이 1280px 를 넘으면 `LANCZOS` 로 축소 (Seedance 출력이 720p 대라 입력 해상도를 올려도 품질 이득이 없음)
- RGB 로 변환 후 JPEG quality 85 로 인코딩
- 결과 payload 는 보통 200–600 KB 수준으로 축소됨

Pillow 가 없으면 원본 바이트 그대로 사용 + 경고 로그만 남깁니다(crash 없음). `backend/requirements.txt` 에 `Pillow>=10.0.0` 을 추가했으니 새 환경에서는 `pip install -r requirements.txt` 로 자동 설치됩니다.

**예상 결과:**

다음 생성 시도에서 둘 중 하나가 일어납니다.
1. 정상 생성 성공 — 원인이 payload 크기였다는 뜻.
2. 여전히 실패하되 **에러 카드에 진짜 원인**이 드러남 (예: `Fal submit HTTP 200 returned EMPTY body`, 또는 `Fal status HTTP 500: {"error": "..."}` 등). 그 로그를 스크린샷으로 주시면 바로 다음 fix 갈 수 있습니다.

백엔드 콘솔에도 `[fal]` 프리픽스로 모든 호출이 찍히니 필요하시면 같이 봐주세요.

---

## v1.1.8 (2026-04-10)

### 추가 — fal.ai 영상 키 진단 엔드포인트 + 프리플라이트 UI

v1.1.7 의 에러 카드 덕분에 드디어 실제 원인(`HTTPStatusError: 403 Forbidden` from `queue.fal.run/fal-ai/bytedance/seedance/v1/lite/image-to-video`)이 수면 위로 올라왔습니다. 이제는 영상 생성을 돌려보지 않고도 키/계정 상태를 먼저 확인할 수 있어야 합니다.

**백엔드** — `backend/app/routers/api_status.py`
- 새 엔드포인트 `GET /api/api-status/fal/video-probe?model=seedance-lite` (또는 `seedance-1.0`) 추가.
- dummy request id(`00000000-0000-0000-0000-000000000000`)로 `GET https://queue.fal.run/{model}/requests/{id}/status` 를 호출해서 HTTP 코드로 분기:
  - `401/403` → `status: "auth_failed"` — 키를 fal.ai 가 거부 (키 revoke / 모델 권한 없음 / 결제 문제 중 하나).
  - `404` → `status: "key_valid"` — 인증은 통과, 단지 그 id 가 없을 뿐. 실제 호출도 성공할 가능성이 매우 높음.
  - 그 외 → `status: "unknown_ok"` — 응답 본문을 그대로 노출.
- 응답 본문(`body`)을 최대 800자까지 반환해서 fal.ai 가 남긴 에러 메시지를 그대로 UI 에서 볼 수 있게 함.
- 이 방식은 실제 영상 submit 이 아니라 **status 조회**라서 크레딧을 소모하지 않습니다.

**프런트엔드** — `frontend/src/lib/api.ts`, `frontend/src/components/studio/StepVideo.tsx`
- `apiStatusApi.probeFalVideo(modelId)` 클라이언트 함수 추가 + `FalVideoProbeResult` 타입.
- StepVideo 상단에 "영상 API 키 진단" 버튼 추가. 선택된 모델이 fal 계열일 때만 실제 호출하고, local/kling 이면 "의미 없음" 메시지만 띄움.
- 결과 카드: 초록(`key_valid`) / 빨강(`auth_failed`) / 회색(기타) 로 표시. HTTP 코드, fal.ai 원문 body, 그리고 `auth_failed` 일 때 fal.ai 대시보드 바로가기 링크(Keys, Billing) 를 제공.

### 참고 — 현재 LongTube 가 지원하는 영상 생성 모델

실제로 `backend/app/services/video/factory.py` 에 등록되어 있는 것은 네 가지이며, 공급자는 세 곳입니다. 이 정보는 UI 드롭다운 "영상 생성 모델"에서 그대로 선택 가능합니다.

| 모델 id | 이름 | 공급자 | 단가 |
|---|---|---|---|
| `ffmpeg-kenburns` | FFmpeg Ken Burns | local (FFmpeg) | 무료 |
| `kling-v2` | Kling V2 | Kling | $0.14 / 5초 클립 |
| `seedance-lite` | Seedance 1.0 Lite | fal.ai (ByteDance) | $0.18 / 5초 클립 |
| `seedance-1.0` | Seedance 1.0 | fal.ai (ByteDance) | $0.62 / 5초 클립 |

xAI Grok 은 현재 **이미지 생성** 쪽에만 연결되어 있고(`backend/app/services/image/grok_service.py`) 영상 쪽에는 등록되어 있지 않습니다.

---

## v1.1.7 (2026-04-10)

### 긴급 수정 — force-restart.bat 자살 버그
v1.1.6 의 force-restart.bat / start.bat 은 실행하면 **자기 자신의 창을 닫아버려서 스크립트가 중간에 죽었습니다**. 원인:

PowerShell 스크립트 안의 `$PID` 는 **PowerShell 자기 자신의 PID** 이지, `.bat` 을 실행 중인 **부모 cmd.exe 의 PID 가 아닙니다**. 그래서 `$_.ProcessId -ne $PID` 제외 조건은 PowerShell 만 지킬 뿐, 자기 부모 cmd.exe 는 보호하지 못했습니다. 그 결과 "command line 에 `force-restart.bat` 포함된 cmd.exe" 필터가 현재 실행 중인 자기 부모를 잡아 죽였고, 스크립트 실행이 그 자리에서 끊겼습니다.

**수정**: PowerShell 이 `Get-CimInstance Win32_Process -Filter "ProcessId=$PID"` 로 자기 부모 PID(= .bat 을 실행 중인 cmd.exe) 와 조부모 PID(= force-restart 가 start.bat 을 `call` 한 경우의 상위 cmd) 를 직접 계산해서 둘 다 kill 제외 대상에 추가합니다:

```powershell
$me = $PID
$parent = (Get-CimInstance Win32_Process -Filter ("ProcessId=" + $me)).ParentProcessId
$grandparent = (Get-CimInstance Win32_Process -Filter ("ProcessId=" + $parent)).ParentProcessId
Get-CimInstance Win32_Process -Filter "Name='cmd.exe'" |
  Where-Object { $_.CommandLine -like '*force-restart.bat*' -or ... } |
  Where-Object { $_.ProcessId -ne $me -and $_.ProcessId -ne $parent -and $_.ProcessId -ne $grandparent } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

start.bat 도 동일 패턴으로 수정 (force-restart.bat 에서 `call "%~dp0start.bat"` 로 호출된 경우에도 살아남도록).

### 변경 파일
- `start.bat`, `force-restart.bat` — 부모/조부모 PID 계산 후 kill 제외
- 버전 파일 4개 — 1.1.7

---

## v1.1.6 (2026-04-10)

### 배치 스크립트 - 이전 릴리즈의 거짓 수정 정정
v1.1.5 의 cmd 정리 로직은 실제로 동작하지 않았습니다. 원인:
- `taskkill /fi "WINDOWTITLE eq ..."` 는 **Microsoft 공식 문서상 콘솔 애플리케이션(cmd.exe)을 매치하지 못합니다**. WINDOWTITLE 필터는 GUI 창이 있는 프로세스 전용입니다.
- 결과적으로 v1.1.5 의 `"LongTube Server*"`, `"LongTube-Backend*"`, `"next-server*"` 필터는 모두 공회전했고, 유저 스크린샷에서 이전 cmd 창 10여 개가 그대로 누적됐음.

**진짜 수정 (v1.1.6)**: PowerShell `Get-CimInstance Win32_Process` 로 프로세스의 **command line 문자열**을 직접 검사해서 죽이는 방식으로 전면 교체. 더 이상 title 에 의존하지 않음.
- 백엔드: `python.exe` 중 command line 에 `uvicorn*app.main:app*` 포함된 것
- 프론트엔드: `node.exe` 중 command line 에 `next*dev*` 포함된 것
- 래퍼: `cmd.exe` 중 command line 에 `uvicorn`, `next dev`, `start.bat`, `force-restart.bat` 포함된 것 (단 자기 자신 `$PID` 제외)
- 포트 기반 kill (8000/3000) 은 폴백으로 유지
- `taskkill /im python.exe` broad kill 은 여전히 최후의 수단으로 존치

### 영상 생성 실패 진단 기능 (UI 에서 바로 보이는 에러)
이전까지 영상 생성이 실패하면 백엔드 콘솔의 `[video-async] Cut N FAILED: ...` 로그를 직접 뒤져야 했습니다. 이제:
- **task_manager 확장**: `TaskState.item_errors: list[{cut_number, error}]` 필드 추가. `record_item_error()` 헬퍼로 컷별 실패 이유 누적 저장. `to_dict()` 에도 포함되어 `/api/tasks/{pid}/{step}` 응답에 나옴.
- **video.py**: `_run()` / `resume-async` 양쪽 모두 모든 실패 지점에서 `record_item_error()` 호출. 이미지/오디오 파일 누락, 제너레이터 예외(FFmpeg stderr 포함), DB 경로 누락 전부 기록됨.
- **StepVideo.tsx**: 태스크가 실패했거나 `item_errors` 가 1개 이상이면 빨간색 카드가 영상 탭에 표시됨. 컷별 에러 메시지 (`컷 N: <type>: <message>`) 가 모노스페이스로 찍혀서 FFmpeg 리턴코드, 파일 경로 문제, 타임아웃 등을 바로 식별 가능. 백엔드 재시작 시 메모리가 비워져서 카드도 사라짐 (이 제한도 UI 에 명시).
- **StepVideo**: 마운트 시 항상 `taskApi.status()` 호출해서 이전 실패 기록이 있으면 복원 (탭 이동 후 돌아왔을 때 유지)

### 변경 파일
- `start.bat`, `force-restart.bat` — PowerShell commandline kill 전면 교체
- `backend/app/services/task_manager.py` — item_errors 필드, record_item_error 헬퍼
- `backend/app/routers/video.py` — 모든 실패 경로에서 record_item_error 호출
- `frontend/src/lib/api.ts` — TaskItemError 타입 + TaskStatus.item_errors 필드
- `frontend/src/components/studio/StepVideo.tsx` — 에러 카드 UI + 마운트 시 status 조회
- 버전 파일 4개 — 1.1.6

---

## v1.1.5 (2026-04-10)

### 버그 수정 (배치 스크립트)
- **재시작 시 기존 CMD 윈도우 누적 문제 수정**: `start.bat` 과 `force-restart.bat` 이 이전 실행에서 남은 cmd 윈도우를 완전히 정리하지 못해서 실행할 때마다 "LongTube Server", "LongTube-Backend", "LongTube-Frontend", "next-server (v14.2.15)" 윈도우가 계속 쌓이던 문제 수정
  - **원인 1**: `start.bat` 의 자체 윈도우 title 이 "LongTube Server" 로 고정되어 있어서, 다음 실행 때 `taskkill /fi "WINDOWTITLE eq LongTube Server*"` 를 하면 자기 자신도 죽일 위험이 있어 생략됨 → 윈도우 누적
  - **원인 2**: next.js dev 서버는 시작 후 자기 윈도우 title 을 "next-server (vX.Y.Z)" 로 바꿔서 `LongTube-Frontend*` 필터에 안 잡힘
  - **수정 1**: 스크립트 시작 직후 `title LongTube-Launcher-%RANDOM%%RANDOM%` 로 자기 윈도우를 고유값으로 바꿔놓고 cleanup 을 실행 → 자살 방지
  - **수정 2**: cleanup 필터에 `"next-server*"` 추가
  - **수정 3**: start.bat 은 모든 서버가 뜬 후 `title LongTube Server` 로 다시 rename → 다음 실행 때 정상적으로 매치되어 죽음
  - **수정 4**: `"LongTube Force Restart*"`, `"LongTube-Launcher*"` 타이틀도 cleanup 대상에 추가
  - force-restart.bat 에도 동일 패턴 적용

### 변경 파일
- `start.bat` — self-rename + 확장된 cleanup 필터
- `force-restart.bat` — self-rename + 확장된 cleanup 필터
- `frontend/src/lib/version.ts`, `backend/app/main.py`, `frontend/package.json`, `frontend/package-lock.json` — 1.1.5

---

## v1.1.4 (2026-04-10)

### 기능 추가
- **최종 병합 영상 미리보기**: 모든 컷의 영상 생성이 완료되면 영상 탭 하단 "최종 병합 영상" 카드에 `merged.mp4` 가 `<video controls>` 플레이어로 즉시 표시됩니다. 기존에는 설명 텍스트만 있었음. 캐시 방지를 위해 URL 에 `?t=<timestamp>` 버스터 부착.
- **탭 전환 시 생성 상태 유지**: StepVoice / StepImage / StepVideo 세 단계에 마운트-복원 로직 추가. 컴포넌트가 마운트될 때 `taskApi.status()` 를 한번 호출해서 백엔드 태스크가 `running` 이면 로컬 `generating=true` 로 복원합니다. 이 때문에:
  - 이미지 생성 도중 다른 탭(대본/음성/영상 등)으로 이동 후 다시 돌아와도 진행 바와 "생성 중..." 표시가 계속 유지됩니다
  - 백엔드는 이미 `asyncio.create_task` 로 백그라운드에서 돌고 있었기 때문에, 실제 생성 자체는 어차피 탭 이동과 무관하게 진행됩니다. 이번 수정은 그것을 UI 에 올바르게 반영시키는 것입니다.
  - 제한: 백엔드 자체를 재시작하면 인-메모리 `task_manager` 상태가 사라져서 UI 복원 불가 (이 경우엔 "이어서 생성" 버튼으로 재개)

### 변경 파일
- `frontend/src/components/studio/StepVideo.tsx` — 마운트 복원 useEffect + 병합 영상 `<video>` 플레이어
- `frontend/src/components/studio/StepImage.tsx` — 마운트 복원 useEffect
- `frontend/src/components/studio/StepVoice.tsx` — 마운트 복원 useEffect
- `frontend/src/lib/version.ts` — 1.1.4
- `backend/app/main.py` — 1.1.4
- `frontend/package.json`, `package-lock.json` — 1.1.4

---

## v1.1.3 (2026-04-10)

### 버그 수정
- **영상 단계 상태 불일치 수정**: 모든 컷이 실패해도 `step_states["5"] = "completed"` 로 저장되던 버그 수정 (`backend/app/routers/video.py` `_run`)
  - 이전: `clip_paths` 비어 있어도 무조건 completed → UI 상 "완료" 인데 실제 영상은 0개
  - 수정: 성공한 클립이 1개라도 있으면 completed, 0개면 failed 로 기록 + `fail_task` 호출
  - `resume-async` 에도 동일 로직 적용 (기존 완료분 + 신규 생성 합산으로 판단)
- **실패 원인 안내 추가**: 모든 컷 실패 시 task error 메시지에 "백엔드 콘솔의 `[video-async]` 로그를 확인하세요" 안내
- **DB 직접 복구**: 기존 프로젝트 `043a24df` 의 잘못 기록된 `step_states["5"]="completed"` 를 `"failed"` 로 교정 (실제 video_path 가 0개인 상태와 일치시킴)

### UX 개선
- **영상 대기 컷에 이미지 썸네일 표시**: 영상 단계에 진입했을 때 아직 생성되지 않은 컷에도 해당 이미지가 60% 불투명도로 배경에 표시됨 (`StepVideo.tsx`)
  - 기존: `<Film>` 아이콘만 덩그러니 → 어떤 컷인지 구분 불가
  - 수정: 이미지 위에 반투명 오버레이 + "영상 대기" 라벨
  - 생성 중/대기 상태는 기존대로 유지 (20~30% 오파시티)

### 변경 파일
- `backend/app/routers/video.py` — `_run` + `resume-async` step_states 로직 수정
- `frontend/src/components/studio/StepVideo.tsx` — placeholder 렌더링 개선
- `frontend/src/lib/version.ts` — 1.1.3
- `backend/app/main.py` — 1.1.3
- `frontend/package.json`, `package-lock.json` — 1.1.3

---

## v1.1.2 (2026-04-10)

### UX 개선
- **각 단계 정리/삭제 버튼 상시 표시**: 음성/이미지/영상 단계의 휴지통 버튼이 기존에는 완료된 항목이 1개 이상 있을 때만 보였으나, 이제 생성 중이 아닐 때는 항상 표시됨
  - 이유: 영상 1% 멈춤처럼 생성이 실패해 DB 에 완료 기록이 0개인 상태에서도 부분 파일/태스크 상태를 정리할 수단이 필요
  - 동작 변경:
    - 완료된 항목이 있으면 → 기존처럼 모든 파일 삭제 + DB 경로 비우기 + 폴더 제거
    - 완료된 항목이 0개여도 버튼 표시 → "단계 초기화" 로 동작 (`clearStep` + `taskApi.cancel` 순차 실행 → 태스크 상태까지 리셋)
  - 툴팁도 상황별로 다르게 표시 ("영상 모두 지우기" / "영상 단계 정리")
- **확인 다이얼로그에 개수 표시**: "영상 3개를 모두 삭제하시겠습니까?" 처럼 몇 개가 지워지는지 명시
- **에러 처리 추가**: `clearStep` 실패 시 alert 로 에러 메시지 표시 (기존엔 조용히 삼킴)

### 변경 파일
- `frontend/src/components/studio/StepVideo.tsx` — trash 버튼 조건 완화, 취소 호출 병행
- `frontend/src/components/studio/StepImage.tsx` — 동일
- `frontend/src/components/studio/StepVoice.tsx` — 동일
- `frontend/src/lib/version.ts` — 1.1.2
- `backend/app/main.py` — 1.1.2
- `frontend/package.json`, `package-lock.json` — 1.1.2

---

## v1.0.1 (2026-04-10)

### 신규 기능
- **중지 기능**: 음성/이미지/영상 각 단계에서 생성 중지 버튼 추가
  - 생성 중일 때만 빨간색 "중지" 버튼 활성화
  - 클릭 시 "중지하시겠습니까?" 확인 다이얼로그 표시
  - 확인 시 백엔드 태스크 강제 취소, 이미 완료된 컷은 유지
- **이어서 생성 기능**: 미완료 컷만 이어서 생성하는 기능 추가
  - 일부 컷이 완료되고 미완료 컷이 있으면 "이어서 생성" 버튼 표시
  - 백엔드에 `/resume-async` 엔드포인트 추가 (voice, image, video 각각)
  - 이미 완료된 컷은 건너뛰고 미완료 컷만 생성
- **버전 정보 표시**: 대시보드 및 스튜디오 우측 상단에 버전 표시 (v1.0.1)
- **GenerationTimer stuck 감지**: 2분 이상 0건 완료 시 경고 메시지 표시

### 버그 수정
- **이미지 스타일 불일치 수정**: LLM 시스템 프롬프트에서 "cinematic" 하드코딩 제거
  - 전체 이미지 스타일이 카툰/일러스트면 cinematic/realistic 용어 사용 금지
  - 아트 스타일은 모든 컷에 통일, 캐릭터는 30~50% 컷에만 등장하도록 변경
  - KO/EN/JA 3개 언어 프롬프트 모두 동일하게 적용
- **TTS API 타임아웃 추가**: OpenAI TTS 호출에 60초 타임아웃 (무한 대기 방지)
- **비동기 태스크 에러 처리 강화**: BaseException 처리 + 에러 로그 출력
- **task_manager 30분 타임아웃**: stuck 상태 태스크 자동 만료 처리
- **레퍼런스/캐릭터 이미지 분리**: 레퍼런스 이미지는 모든 컷에(스타일용), 캐릭터 이미지는 캐릭터 등장 컷에만 전달
- **이미지 서비스 안전장치**: 레퍼런스 파일 접근 실패 시 skip, 전부 실패 시 표준 생성 폴백

### 변경 파일
- `frontend/src/components/studio/StepVoice.tsx` — 중지/이어서 생성 버튼
- `frontend/src/components/studio/StepImage.tsx` — 중지/이어서 생성 버튼
- `frontend/src/components/studio/StepVideo.tsx` — 중지/이어서 생성 버튼
- `frontend/src/components/common/GenerationTimer.tsx` — stuck 감지
- `frontend/src/lib/api.ts` — resumeAsync API 추가
- `frontend/src/app/studio/[projectId]/page.tsx` — 버전 정보 표시
- `frontend/src/app/page.tsx` — 버전 정보 표시
- `backend/app/routers/voice.py` — resume-async 엔드포인트 + 에러 처리 강화
- `backend/app/routers/image.py` — resume-async 엔드포인트 + 캐릭터/레퍼런스 분리
- `backend/app/routers/video.py` — resume-async 엔드포인트
- `backend/app/services/llm/base.py` — 시스템 프롬프트 스타일/캐릭터 분리
- `backend/app/services/image/openai_image_service.py` — 안전장치 + 폴백
- `backend/app/services/tts/openai_tts_service.py` — 60초 타임아웃
- `backend/app/services/task_manager.py` — 30분 타임아웃 자동 만료

---

## v1.0.0 (초기 버전)
- 프로젝트 생성/관리
- LLM 대본 생성 (Claude, GPT)
- TTS 음성 생성 (OpenAI, ElevenLabs)
- 이미지 생성 (OpenAI gpt-image-1, DALL-E 3, Flux, Midjourney 등)
- 영상 생성 (FFmpeg Ken Burns, Kling, Runway 등)
- 자막 생성/합성
- 비동기 백그라운드 생성 + 진행률 표시
- 레퍼런스/캐릭터 이미지 지원
- 다국어 지원 (KO/EN/JA)
