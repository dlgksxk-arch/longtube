# LongTube 세션 인계 (v1.1.63 기준)

> **2026-04-23 직전 세션 요약 (v1.2.26 까지 진행)**
>
> **이번 세션 핵심 작업** — "유령 API 호출" 차단선 완성 + "제작 중단" 버튼 정상화
>
> 1. **v1.2.25**: 모든 외부 API 모델(fal.ai 8개 / OpenAI 이미지·TTS / Grok / Flux / Kling / ElevenLabs)
>    에 thread-local cancel 가드 일반화. `backend/app/services/cancel_ctx.py` 신설 →
>    `OperationCancelled`, `set_cancel_key/get_cancel_key/is_cancelled/raise_if_cancelled`.
>    각 서비스 submit / 폴링 / 재시도 진입점에 `raise_if_cancelled(태그)` 박음.
>    `_step_script` / `_step_voice` / `_generate_thumbnail_sync` 진입 시 `set_cancel_key(pid)` 호출.
>
> 2. **v1.2.26**: 사용자 보고 — "제작 중단 버튼 동작 안한다." 원인은 `_step_image` /
>    `_step_video` 가 `cancel_ctx.set_cancel_key(pid)` 를 호출하지 않아서 외부 API
>    서비스의 `raise_if_cancelled()` 가드가 영원히 False 였음(thread-local key 가 None).
>    수정:
>    - `pipeline_tasks._step_image` / `_step_video` 진입 시 `set_cancel_key(pid)` + 종료 시 `(None)`
>    - 두 step 의 per-cut `_one()` 안에 `raise_if_cancelled()` 직접 호출 추가
>    - `oneclick_service._run_sync_pipeline` 의 모든 `except PipelineCancelled` →
>      `except _CancelTypes`(= `(PipelineCancelled, OperationCancelled)`) 통일
>    - `cancel_task()` 가 redis/comfyui 정리보다 **먼저** task 상태를 cancelled 로
>      마킹 (UI 즉시 반응) + "⏹ 사용자 중단 요청" 로그 한 줄
>
> **버전**: backend `app/main.py` 두 곳, `frontend/src/lib/version.ts`,
> `frontend/package.json` 모두 1.2.26.
>
> **세션 중 발생한 사고** — Edit 툴이 큰 파이썬 파일 끝부분을 두 번 잘라먹음.
> `pipeline_tasks.py` (1126줄 print 미닫힘 → git HEAD tail 로 복원),
> `oneclick_service.py` (`run_queue_top_now` 의 `if loo` 미완 → 재구성).
> 두 파일 모두 `py_compile` 통과 확인. **다음 세션에서 큰 .py 편집할 때는 Edit 보다
> bash + python heredoc 권장.** CONTEXT.md / HANDOFF.md 도 같은 사고 → 재구성됨.
>
> **남아있는 보류 작업** (이전 세션 priority shift 로 잠시 멈춤):
> - 진행상태 실시간 세분화 (`sub_status` 필드) — 이미지/영상 컷 단위 "현재 N/M컷
>   생성 중" 같은 텍스트를 task 에 박아 Live 페이지 stale 60초 경고 대신 살아있는
>   상태가 보이도록. 백엔드 `oneclick_service` 에 `sub_status` 필드 + helper
>   (`update_task_sub_status`, `append_task_log`) 는 이미 추가됨. 남은 일:
>   각 step 안에서 호출 + 프론트 ActivityPanel 에 렌더링 + `frontend/src/lib/api.ts`
>   `OneClickTask` 타입에 `sub_status` 추가.
>
> ---


> v1.1.61 시점 작성본을 v1.1.63 에서 전면 재작성. stale 된 ComfyUI 모델 개수,
> SDXL 해상도, Qwen-Image-Edit 상태 등 교정. 과거 교훈 섹션은 보존.

## 프로젝트

- **스택**: FastAPI(backend) + Next.js(frontend) + SQLite + asyncio
- **경로**: `C:\Users\Jevis\Desktop\longtube\` (코드/DB) + `C:\Users\Jevis\Desktop\longtube_net\projects\` (NAS 에셋)
- **Git**: https://github.com/dlgksxk-arch/longtube.git
- **실행**: `start.bat` (uvicorn --reload + pnpm dev)

## 사용자 선호 (이전 세션에서 명시)

- 한국어 존댓말 사용
- 거짓말·추상적 추측으로 사실 왜곡 금지
- 쓸데없는 농담으로 열 받게 하지 말 것
- 사용자 탓하지 말 것
- 로그는 직접 읽을 것 (`backend/logs/*.log`)
- 할 수 있는 걸 사용자에게 시키지 말 것

---

## 이미지 생성 (v1.1.63 현재)

### 레지스트리 (`backend/app/services/image/factory.py`)

**로컬 ComfyUI (6개)**:
- `comfyui-dreamshaper-xl` — DreamShaper XL Lightning (SDXL, 기본)
- `comfyui-dreamshaper-xl-vector` — + Vector Art LoRA (카툰/벡터)
- `comfyui-dreamshaper-xl-longtube` — + LongTube Style 4K (커스텀 LoRA)
- `comfyui-dreamshaper-xl-longtube-2k` — 2K 변형
- `comfyui-dreamshaper-xl-longtube-3k` — 3K 변형
- `comfyui-qwen-image-edit-2509` — Qwen-Image-Edit 2509 fp8, **레퍼런스 필수** (픽셀 기반 스타일 전이), ~20GB VRAM

**클라우드**: `openai-image-1` (default, `/edits` 로 레퍼런스 지원), `openai-dalle3`, `nano-banana` / `-2` / `-3` (스타일 락) / `-pro`, `seedream-v4.5`, `z-image-turbo`, `grok-imagine`, `flux-dev`, `flux-schnell`, `midjourney` (프록시 미구현 `NotImplementedError`)

**폴백**: Unknown model_id → `openai-image-1` (log: `data/logs/image_factory_fallback.log`)

### `supports_reference_images` 매트릭스

| 모델 | 지원 | 소스 |
|------|------|------|
| `openai-image-1` | ✅ | `openai_image_service.py` L26 (gpt-image-1 만) |
| `openai-dalle3` | ❌ | 같은 파일 (dall-e-3 는 `/edits` 없음) |
| nano-banana 계열 전부 | ✅ | `nano_banana_service.py` L94 |
| comfyui-qwen-image-edit-2509 | ✅ | `comfyui_service.py` L157 (**인스턴스 레벨 오버라이드** — 클래스 default 는 False) |
| DreamShaper XL 5종 | ❌ | 클래스 default |
| flux (fal) / seedream / z-image-turbo / grok | ❌ | 각 서비스 default |

**미지원 모델에 레퍼런스 첨부 시** → 자동으로 `nano-banana-3` 로 폴백. 구현 위치 3곳 (동일 패턴):
- `routers/youtube.py` L577~597 (썸네일)
- `routers/oneclick.py` L227~231 (원클릭 파이프라인)
- `tasks/pipeline_tasks.py` L481~488 (썸네일), L574~584 (일반 이미지)

### ComfyUI 해상도 매핑 (`image/comfyui_service.py`)

**SDXL family** (`_SDXL_DIMS`):
- 16:9 = 1344×768, 9:16 = 768×1344, 1:1 = 1024×1024
- 3:4 = **832×1088**, 4:3 = **1088×832**

**Qwen family** (`_QWEN_DIMS`):
- 16:9 = 1344×768, 9:16 = 768×1344, 1:1 = 1024×1024
- 3:4 = **896×1152**, 4:3 = **1152×896**

**SD 1.5 family** (`_SD15_DIMS`, workflows 에 JSON 만 있고 레지스트리 미등록):
- 16:9 = 768×448, 9:16 = 448×768, 1:1 = 512×512, 3:4 = 512×640, 4:3 = 640×512

> ⚠️ 이전 HANDOFF 는 SDXL 의 3:4/4:3 값을 Qwen 값(896×1152, 1152×896)으로 잘못 기재했었음.

### 프롬프트 빌더 (`image/prompt_builder.py`)

- `REFERENCE_STYLE_PREFIX` — 레퍼런스 첨부 시 프롬프트 앞에 붙는 단일 상수. **텍스트 기반 메타 지시**, 픽셀 전이 아님.
- `build_image_prompt(..., has_reference=True)` — PREFIX + `global_style`(비어있지 않으면) + 캐릭터 설명(슬롯이면) + base 프롬프트 순으로 조합. 
- v1.1.61 로직: `has_reference=True` 여도 `global_style` 을 항상 주입. 이유는 로컬 ComfyUI 가 레퍼런스 픽셀을 모델에 안 넣어서 스타일 단어 자체가 모델에 전달되지 않으면 실사 결과로 회귀하기 때문.
- `cut_has_character(cut_number)` — **5컷마다 1장 캐릭터 배치** (cut 1, 6, 11, 16, ...). 공식: `(cut_number - 1) % 5 == 0`. `routers/image.py` 에도 동일한 함수 존재, `routers/video.py` 는 이걸 import 해서 사용.
  - ⚠️ `routers/video.py::_build_video_motion_prompt` 의 docstring 은 "3의 배수 규칙"이라고 써있지만 실제로는 위 5컷 규칙 함수를 호출. docstring 만 stale.

---

## 영상 생성 (v1.1.63 현재)

### 레지스트리 (`backend/app/services/video/factory.py`)

- `ffmpeg-kenburns` (default, 로컬, 무료)
- `ffmpeg-static` (폴백 전용, 정지 이미지 — 영상 선택 모드에서 미선택 컷에 적용)
- **로컬 ComfyUI 2개**: `comfyui-ltxv-2b` (LTX Video 2B distilled, ~3GB VRAM), `comfyui-hunyuan15-480p` (HunyuanVideo 1.5 480p, ~10GB VRAM)
- **클라우드 fal**: `ltx2-fast`, `ltx2-pro`, `seedance-lite`, `seedance-1.5-pro`, `seedance-1.0`, `kling-2.5-turbo`, `kling-2.6-pro`
- **Kling 네이티브 API**: `kling-v2` (JWT HS256 stdlib 직접 구현, PyJWT 비의존)
- **폴백**: Unknown → `ffmpeg-kenburns`

### ComfyUI 비디오 — 서비스 레벨 vs 레지스트리 갭

`video/comfyui_service.py::_WORKFLOW_FILES` 는 **5개 모델** 매핑 보유:
- `comfyui-wan22-i2v-fast`, `comfyui-wan22-5b`, `comfyui-ltxv-2b`, `comfyui-ltxv-13b`, `comfyui-hunyuan15-480p`

워크플로 JSON 도 `backend/workflows/comfyui/` 에 5개 모두 존재. 

그러나 `VIDEO_REGISTRY` 는 `ltxv-2b` + `hunyuan15-480p` 2개만 노출. 나머지 3개 제외 이유:
- WAN 2.2 2종 — 체크포인트 파일 미설치
- LTXV 13B — 튜닝/테스트 완료 안 됨

즉 **서비스 클래스는 준비된 상태**라 필요 시 factory 에 다시 추가하면 바로 동작 (단, 모델 체크포인트가 ComfyUI 에 실제로 있어야 submit 단계 통과).

### ComfyUI 해상도 매핑 (`_wan_dims`)

- 12GB VRAM + 속도 우선으로 작은 해상도: 16:9 = 640×384, 9:16 = 384×640, 1:1 = 512×512, 3:4 = 448×576
- LTXV 는 32 배수 요구 → 위 값이 32 로 나눠져서 그대로 호환
- WAN / Hunyuan 은 16 배수 요구 — 같은 값에서 OK

### 모션 프롬프트 (`routers/video.py::_build_video_motion_prompt`)

- 1번 컷: 오프닝 느낌 (카메라 push-in, 파티클 드리프트)
- 마지막 컷: 엔딩 느낌 (카메라 pull-out, 위로 드리프트)
- 그 외: 시네마틱 패닝 + 파티클/바람/물 흐름 등 명시적 모션 동사
- 캐릭터 컷이면 "character must move naturally" 명시적 추가 (identity preserve 조건 포함)
- FFmpeg KenBurns 는 이 프롬프트 무시, fal/kling/ComfyUI 영상 모델만 사용

### LTXV 움직임 튜닝 (참고)

- `ltxv_13b_distilled_i2v.json` (미등록): `image_noise_scale: 0.3` (과거 v1.1.x 에서 0.15 → 0.3 으로 올려 움직임 확보)
- `ltxv_2b_distilled_i2v.json` (현재 등록): `image_noise_scale: 0.05`
- 두 모델 튜닝이 다르게 잡혀있음. 2B 에서 움직임이 약하면 0.1~0.2 범위로 올려보는 실험 가능.

### `_enforce_duration` (comfyui_service.py)

- AI 모델이 요청보다 짧은 클립을 반환할 때 `setpts/atempo` 슬로모션으로 target_duration 에 강제 맞춤
- 비율이 2.5 배를 넘으면 스킵 (너무 느려서 부자연스러움) — 상위에서 루프 처리

---

## 로깅

- `backend/logs/image_async.log` — `routers/image.py::_ilog()`
- `backend/logs/video_async.log` — `routers/video.py::_vlog()`
- `data/logs/image_factory_fallback.log` — unknown model_id 폴백 기록
- 경로 모두 mount 로 접근 가능. **사용자에게 로그 붙여달라 하지 말고 직접 tail 할 것.**

---

## 과거 교훈 / 건드리지 말 것

### IPAdapter — 완전 폐기 (v1.1.61 이전)

- `ComfyUI_IPAdapter_plus` 설치 시도했으나 `IPAdapterModelLoader not found` HTTP 400 지속 발생 → 사용자 짜증 극에 달해 완전 제거.
- 현재 image `comfyui_service.py` 에 픽셀 기반 레퍼런스 주입 경로는 **Qwen-Image-Edit 하나뿐**.
- **IPAdapter 를 다시 들이지 말 것.** 픽셀 단위 레퍼런스가 필요하면 Qwen-Image-Edit (이미 통합됨) 또는 FLUX Kontext-dev (비상업 라이선스 주의) 로.

### Qwen-Image-Edit 통합 (v1.1.55~v1.1.63 사이에 완료됨)

- 워크플로: `backend/workflows/comfyui/qwen_image_edit_2509_text2img_ref.json`
- Factory: `comfyui-qwen-image-edit-2509`, provider=comfyui
- 레퍼런스 미제공 시 **조용한 폴백 없이** `RuntimeError("Qwen-Image-Edit 2509 은 레퍼런스 이미지가 필수입니다...")` 발생. 이건 의도된 설계 — 다른 경로가 있음에도 Qwen 을 골랐다는 건 레퍼런스 주입 스타일 전이를 기대한 호출이므로.
- `supports_reference_images` 는 클래스 default(False)를 `__init__` 에서 True 로 오버라이드.
- 20GB VRAM 권장.

### 레지스트리에서 제외된 ComfyUI 모델 (JSON 은 살아있음)

**이미지**: `flux2_turbo`, `z_image_turbo` (z-image-turbo 는 fal provider 로는 등록됨 — 이름만 같고 provider 다름), `sd15`, `toonyou_beta6`, `revanimated_v2`, `meinamix_v12` — 스타일 제어 한계 / 설치 난이도.

**영상**: `wan22_i2v_fast`, `wan22_ti2v_5b`, `ltxv_13b_distilled` — 체크포인트 미설치 / 튜닝 미완.

**처리 방침**: 워크플로 JSON 과 서비스 매핑은 보존 (복구 용이). 레지스트리만 제외. 모델 파일이 설치되면 factory 에 한 줄 추가로 복구 가능.

### `_WORKFLOW_FILES_REF` 의 dead-load (image/comfyui_service.py)

- Qwen 외 모델의 ref 워크플로도 `__init__` 에서 `self._template_ref` 로 로드됨 (파일이 있으면)
- 그러나 실제 `generate()` 에서는 Qwen 외 모델 경로가 `self._template` 만 사용 — `self._template_ref` 는 메모리에만 올라가고 사용 안 됨
- IPAdapter 폐기 과정에서 생긴 잔재. 제거 가능하나 파급 미미해서 보류 상태.

### LTXV 해결된 움직임 이슈 (v1.1.x)

- 13B 워크플로 `image_noise_scale` 0.15 → 0.3 으로 조정
- 모션 프롬프트에 명시적 동사(카메라 팬, 바람, 파티클) 주입
- 현재는 2B 가 기본 등록이라 이슈 재현 가능성 낮음. 2B 움직임 약하면 같은 파라미터 실험.

---

## 새 세션 시작 시 체크

1. **문서 읽는 순서**: `CONTEXT.md` → `CHANGELOG.md` (최상단 버전부터) → 이 파일
2. **버전 bump 필요하면** `README.md` 의 "버전 bump 규칙" 5곳 체크 (backend/main.py, frontend/version.ts, package.json, package-lock.json 2곳)
3. **모델 추가/변경 요청이면** 세 곳 동기화 확인:
   - `backend/app/services/image(or video)/factory.py` (레지스트리)
   - `backend/app/services/image(or video)/comfyui_service.py` (_WORKFLOW_FILES, _DISPLAY_NAMES, 필요 시 _DIMS)
   - `backend/workflows/comfyui/*.json` (워크플로 JSON)
4. **로그 관련 질문이면** 사용자한테 떠넘기지 말고 `backend/logs/image_async.log` / `video_async.log` 직접 tail
5. **API 키 관련 작업이면** v1.1.63 부터 서비스들이 `from app import config` 로 모듈 속성 참조 — UI 에서 키 바꾸면 다음 요청에 즉시 반영. `from app.config import X` 로 되돌리지 말 것 (캐싱됨)

---

> 마지막 업데이트: 2026-04-23 (v1.2.26)
> 작성 근거: 이 문서의 모든 기술 서술은 해당 커밋 시점의 실제 소스 코드와 워크플로 JSON 파일을 직접 대조해서 검증함.
