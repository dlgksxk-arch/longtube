# LongTube v1.1.2

유튜브 롱폼 영상을 주제 입력 하나로 자동 생성하는 파이프라인 도구.

대본(Claude/GPT) → 음성(OpenAI TTS/ElevenLabs) → 이미지(OpenAI gpt-image-1/Flux 등) → 영상(FFmpeg/Kling 등) → 자막 → 유튜브 업로드

---

## Quick Start

```bash
# 1. 환경 설정
cp backend/.env.example backend/.env    # API 키 입력

# 2. 백엔드 셋업
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 3. 프론트엔드 셋업
cd frontend
pnpm install

# 4. 실행
start.bat
# 또는 수동:
#   터미널1: cd backend && uvicorn app.main:app --reload --port 8000
#   터미널2: cd frontend && pnpm dev
```

- 프론트엔드: http://localhost:3000
- 백엔드 API: http://localhost:8000
- API 문서: http://localhost:8000/docs

---

## 프로젝트 정보

- **코드**: `C:\Users\Jevis\Desktop\longtube` (로컬)
- **에셋**: `C:\Users\Jevis\Desktop\longtube_net\projects\` (NAS)
- **Git**: https://github.com/dlgksxk-arch/longtube.git

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| 프론트엔드 | Next.js 14 + TypeScript + Tailwind CSS | 다크 UI |
| 백엔드 | Python FastAPI | 비동기 API, FFmpeg 제어 |
| 백그라운드 작업 | asyncio.create_task + in-memory TaskManager | Celery/Redis 대체 |
| 데이터베이스 | SQLite | 1인 사용, 프로젝트 메타데이터 |
| 영상 처리 | FFmpeg | Ken Burns 효과, 자막 삽입, 병합 |
| 패키지 관리 | pnpm (프론트) / pip venv (백엔드) | |

---

## 지원 AI 모델

### 대본 생성 (Step 2)
| 모델 ID | 표시명 | API |
|---------|--------|-----|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Anthropic | **기본값** |
| `claude-opus-4-6` | Claude Opus 4.6 | Anthropic |
| `claude-haiku-4-5` | Claude Haiku 4.5 | Anthropic |
| `gpt-4o` | GPT-4o | OpenAI |
| `gpt-4o-mini` | GPT-4o Mini | OpenAI |
| `gpt-4.1` | GPT-4.1 | OpenAI |

### 이미지 생성 (Step 4)
| 모델 ID | 표시명 | API |
|---------|--------|-----|
| `openai-image-1` | GPT Image 1 | OpenAI | **기본값** |
| `openai-dalle3` | DALL-E 3 | OpenAI |
| `flux-dev` | Flux Dev | fal.ai |
| `flux-schnell` | Flux Schnell | fal.ai |
| `nano-banana-2` | Nano Banana 2 | bbanana |
| `grok-imagine` | Grok Imagine | xAI |
| `midjourney` | Midjourney | 외부 API |

### 음성 생성 (Step 3)
| 모델 ID | 표시명 | API |
|---------|--------|-----|
| `openai-tts` | OpenAI TTS | OpenAI | alloy, echo, fable, onyx, nova, shimmer |
| `elevenlabs` | ElevenLabs | ElevenLabs | 다국어, 커스텀 보이스 |

### 영상 생성 (Step 5)
| 모델 ID | 표시명 | API |
|---------|--------|-----|
| `ffmpeg-kenburns` | FFmpeg Ken Burns | 로컬 | **기본값**, 무료 |
| `kling-v2` | Kling V2 | Kling API |
| `runway-gen3` | Runway Gen-3 | Runway API |

---

## 파이프라인 흐름

```
[주제 입력]
    │
    ▼
[Step 1: 설정] ─── 비율, 스타일, 타겟 길이, 모델 선택
    │
    ▼
[Step 2: 대본 생성] ─── Claude/GPT → 컷 단위 JSON (나레이션 + 이미지 프롬프트)
    │  └ 컷별 나레이션/프롬프트 수정, 컷 추가/삭제/순서변경 가능
    ▼
[Step 3: 음성 생성] ─── OpenAI TTS / ElevenLabs → 컷별 MP3
    │  └ 중지/이어서 생성 가능, 컷별 재생성 가능
    ▼
[Step 4: 이미지 생성] ─── OpenAI gpt-image-1 등 → 컷별 PNG
    │  └ 중지/이어서 생성 가능, 레퍼런스/캐릭터 이미지 참조, 개별 재생성/업로드
    ▼
[Step 5: 영상 생성] ─── FFmpeg Ken Burns 등 → 컷별 MP4 → 병합
    │  └ 중지/이어서 생성 가능
    ▼
[Step 6: 자막 + 합성] ─── 자막 스타일 편집 → 최종 렌더링
    │
    ▼
[다운로드] ─── 단계별/전체 다운로드
```

---

## 파일 구조

```
longtube/
├── README.md                       # 이 파일 (통합 문서)
├── CHANGELOG.md                    # 버전별 변경사항
├── start.bat, docker-compose.yml
├── backend/
│   ├── .env                        # API 키 (git 제외)
│   ├── requirements.txt
│   └── app/
│       ├── main.py, config.py
│       ├── models/                 # SQLAlchemy 모델
│       │   ├── project.py, cut.py, api_log.py, database.py
│       ├── routers/                # API 엔드포인트
│       │   ├── projects.py         # 프로젝트 CRUD
│       │   ├── script.py           # 대본 생성/편집/컷 관리
│       │   ├── voice.py            # 음성 생성/이어서 생성
│       │   ├── image.py            # 이미지 생성/이어서 생성
│       │   ├── video.py            # 영상 생성/이어서 생성
│       │   ├── subtitle.py         # 자막 생성
│       │   ├── models.py           # AI 모델 목록 + 가용성
│       │   ├── tasks.py            # 백그라운드 태스크 상태
│       │   ├── downloads.py        # 다운로드 API
│       │   └── youtube.py          # 유튜브 업로드
│       └── services/
│           ├── llm/                # Claude, GPT 등
│           ├── tts/                # OpenAI TTS, ElevenLabs
│           ├── image/              # OpenAI Image, Flux, Grok 등
│           ├── video/              # FFmpeg, Kling, Runway
│           ├── task_manager.py     # in-memory 태스크 관리
│           ├── subtitle_service.py
│           └── youtube_service.py
├── frontend/
│   ├── package.json, tailwind.config.ts
│   └── src/
│       ├── lib/api.ts              # 타입 안전 API 클라이언트
│       ├── app/
│       │   ├── page.tsx            # 대시보드
│       │   └── studio/[projectId]/page.tsx  # 스튜디오
│       └── components/
│           ├── common/             # ModelSelector, LoadingButton, GenerationTimer 등
│           └── studio/             # StepSettings ~ StepSubtitle
└── data/                           # SQLite DB (로컬)
```

---

## 핵심 설계 결정

| 결정 | 이유 |
|------|------|
| 대본 기본 = Claude Sonnet 4.6 | 비용 대비 품질 우수 |
| 이미지 기본 = OpenAI gpt-image-1 | 레퍼런스 이미지 참조 지원 (/edits 엔드포인트) |
| 영상 기본 = FFmpeg Ken Burns | 무료, 빠름, API 비용 절약 |
| asyncio.create_task 백그라운드 | Celery+Redis 없이 간단하게 비동기 처리 |
| SQLite | 1인 사용, 별도 DB 서버 불필요 |
| in-memory TaskManager | 태스크 상태 추적, 30분 타임아웃 자동 만료 |
| 레퍼런스/캐릭터 이미지 분리 | 레퍼런스=스타일(항상), 캐릭터=등장(조건부) |

---

## 주의사항

- Nano Banana API → 별도 키 필요
- Midjourney → 외부 API 연동 필요
- Claude에는 JSON 모드 없음 → regex 파서로 JSON 추출
- NAS 경로(`longtube_net`)가 마운트되어 있어야 에셋 저장/읽기 가능
- DB의 에셋 경로는 상대경로로 저장 (`images/cut_1.png`)

---

## Changelog

### v1.1.2 (2026-04-10) — UX 개선
- **각 단계 정리/삭제 버튼 상시 표시**: 음성/이미지/영상 단계의 휴지통 버튼이 생성 중이 아닐 때는 항상 보이도록 변경
  - 완료 항목 0개여도 "단계 초기화" 로 동작 (`clearStep` + `taskApi.cancel` 병행) → 1% 멈춤처럼 부분 실패 상태 복구 가능
  - 확인 다이얼로그에 삭제 개수 명시, `clearStep` 실패 시 에러 alert 표시
- 변경 파일: `frontend/src/components/studio/Step{Video,Image,Voice}.tsx`, `src/lib/version.ts`, `backend/app/main.py`, `frontend/package.json(-lock).json`

### v1.1.1 (2026-04-10) — 버그 수정
- **API 키 스테일 임포트 버그 수정**: `from app.config import XXX_KEY` 방식은 모듈 로드 시점의 값을 복사해 버려서 UI 에서 키를 저장해도 `api_status.py` 에 반영이 안 되던 문제 수정. `_key()` 헬퍼로 매 요청마다 `.env 파일 → os.environ → cfg 모듈` 순서로 직접 읽도록 변경
- **xAI (Grok) API 실제 검증 추가**: 단순 키 존재 확인이 아니라 `https://api.x.ai/v1/models` 를 실제 호출해 200/401 로 유효성 판정
- **Kling 검증 개선**: access key + secret key 둘 다 있는지 확인
- **영상 생성 1%에서 멈춤 현상 수정**:
  - FFmpeg 필터 `scale=8000:-1` → `scale=2880:-1` (4x 축소, 속도 대폭 개선)
  - `preset medium` → `preset ultrafast`, `crf 18` → `crf 23`
  - 컷당 180초 타임아웃 (asyncio.wait_for)
  - FFmpeg 바이너리 PATH 미발견 시 명확한 에러 메시지
  - stderr 버퍼 deadlock 방지를 위해 stdout → DEVNULL
  - 병합(merge) 은 같은 코덱이므로 `-c copy` stream copy 로 변경 (수십 배 빠름)
- **영상 라우터 강화 (`video.py`)**:
  - 각 컷마다 `[video-async] cut N/M START/DONE in Xs/FAILED` 로그를 stdout 출력
  - 영상/오디오 파일 디스크 존재 여부 pre-flight 체크
  - 이미지 없으면 해당 컷만 실패, 오디오 없으면 경고 후 이미지 전용 폴백
- **kling_service, fal_service 동일한 스테일 임포트 수정**: `os.environ` 에서 매번 재조회
- **version.ts 단일 소스**: 프론트엔드 `src/lib/version.ts` 생성, 모든 UI 버전 표시가 여기서 자동 참조. 더 이상 하드코딩된 `v1.0.1` 문자열 없음

### v1.1.0 (2026-04-10) — 기능 추가
- **실시간 미리보기 + 개별 로딩 인디케이터** (이미지/보이스/영상):
  - `StepImage`, `StepVoice`, `StepVideo` 에 `generatingIndex` 상태 추가
  - 2초마다 백엔드 태스크 상태 polling → 완료된 항목이 늘면 즉시 `onUpdate()` 호출해 UI 반영
  - 현재 생성 중 컷은 border ring + spinner, 대기 컷은 dim 상태, 완료 컷은 "완료" 배지
- **ETA 계산 정확도 개선**: `TaskState` 에 `_item_timestamps` 추가, 최근 5개 항목의 실제 완료 간격을 rolling average 로 계산
- **영상 AI 모델 재정비**:
  - Kling: 베이징 엔드포인트(`api-beijing.klingai.com`) → 글로벌(`api.klingai.com`) 로 교체
  - Kling 인증: `Authorization: Bearer {access_key}` 잘못된 방식 → 정식 JWT HS256 (AccessKey + SecretKey)
  - JWT 구현은 Python 표준 라이브러리만 사용 (`hmac`, `hashlib`, `base64`, `json`) → PyJWT 의존성 불필요
  - Seedance 1.0 Lite / Pro 신규 추가 (fal.ai REST API)
  - 미구현 모델(runway/luma/pika/minimax) 제거 + 알 수 없는 모델은 ffmpeg 로 자동 폴백
- **영상 생성 블로킹 버그 수정**: `subprocess.run()` 이 asyncio 이벤트 루프를 막아 태스크 상태 polling 이 함께 멈추던 치명적 버그 → 모든 FFmpeg 호출을 `asyncio.create_subprocess_exec()` 로 교체
- **이미지 스타일 일관성 강화**: LLM 시스템 프롬프트에 "모든 image_prompt 가 동일한 스타일 접두사로 시작", "sub-style 변형 금지 (graphic/illustration/infographic 등)", "캐릭터 외형을 image_prompt 텍스트에 직접 기술" 규칙 추가
- **이미지 라우터에 `_build_image_prompt()` 추가**: 글로벌 스타일이 이미 프롬프트에 포함돼 있으면 중복 제거, 없으면 prefix 로 붙임

### v1.0.1 (2026-04-10)
- 중지/이어서 생성 기능 (음성/이미지/영상 각 단계)
- 이미지 스타일 일관성 수정 (cinematic 하드코딩 제거, 아트 스타일 통일)
- 캐릭터 등장 30~50% 규칙 (매 프레임 강제 등장 방지)
- TTS API 60초 타임아웃 추가
- 태스크 stuck 감지 + 30분 자동 만료
- GenerationTimer stuck 경고 표시
- 버전 정보 표시 (v1.0.1)

### v1.0.0 (2026-04-09)
- 초기 버전: 6단계 파이프라인 완성
- 대본/음성/이미지/영상/자막 생성
- 비동기 백그라운드 생성 + 진행률 표시
- 레퍼런스/캐릭터 이미지 지원
- 다국어 지원 (KO/EN/JA)

---

## 개발 일지

### 2026-04-09 (Day 1)
- bbanana.ai 분석 → 6단계 파이프라인 설계
- 설계 문서 v2.0 작성 (모델 9종, 일시중지/편집/재시작)
- 백엔드(FastAPI) + 프론트엔드(Next.js 14) 전체 구현
- Git 초기 커밋 (89파일, 7691줄)
- 버그 5건 수정 (유니코드 이스케이프, Redis fallback, 라우트 순서 등)

### 2026-04-10 (Day 2)
- 비동기 백그라운드 생성 (asyncio.create_task)
- 단계 완료 자동 감지 + step_states 관리
- 절대/상대 경로 변환 시스템 구현
- 모델 가용성 표시 (API 키 미설정 시 비활성화)
- 이미지 스타일 일관성 시스템 (LLM 프롬프트 개선)
- 중지/이어서 생성 기능 구현
- OpenAI gpt-image-1 레퍼런스 이미지 지원 (/edits 엔드포인트)

### 2026-04-10 (Day 2, 오후 세션) — v1.1.0 / v1.1.1
#### 작업 요약
이미지 스타일 불일치 → 실시간 미리보기 개선 → ETA 정확도 개선 → 영상 생성 동작 안 함 → 영상 AI 모델 재정비 → 영상 블로킹 버그 수정 → Kling 글로벌 엔드포인트 + JWT 재구현 → PyJWT 의존성 제거 → 영상 1% 멈춤 수정 → xAI 키 반영 안 됨 수정 → 버전 체계 정상화

#### 핵심 변경 파일 (backend)
- `app/main.py` — 버전 1.1.1, reload trigger 주석
- `app/routers/api_status.py` — **완전 재작성**. `_key()` 헬퍼로 매 요청마다 `.env 파일 직접 읽기 → os.environ → cfg` 순 조회. `_check_xai()`, `_check_kling()` 실제 검증. 스테일 임포트 버그 해결
- `app/routers/api_keys.py` — (기존) 키 저장 시 `.env` 에 쓰고 `os.environ` + `cfg` 업데이트
- `app/routers/video.py` — `generate-async`, `resume-async` 양쪽에 per-cut logging, pre-flight 파일 존재 체크, 에러 traceback 출력
- `app/routers/image.py` — `_build_image_prompt()` 헬퍼로 글로벌 스타일 중복 방지, `_prompt_mentions_character()` 제네릭 키워드
- `app/services/video/base.py` — `generate()` 시그니처에 `audio_path`, `aspect_ratio`, `prompt` 추가
- `app/services/video/ffmpeg_service.py` — **완전 재작성**. `_run_ffmpeg()` async helper (timeout 180s), `scale=8000→2880`, `preset ultrafast crf 23`, `merge_videos` stream copy 로 전환
- `app/services/video/kling_service.py` — **완전 재작성**. 글로벌 엔드포인트 `api.klingai.com`, stdlib JWT (`hmac`+`hashlib`), async httpx polling, 스테일 임포트 해결
- `app/services/video/fal_service.py` — **신규**. Seedance 1.0 Lite/Pro 지원, queue-based submit → poll → fetch, 오디오 muxing
- `app/services/video/factory.py` — 미구현 모델 제거, unknown 모델은 ffmpeg 폴백
- `app/services/task_manager.py` — `_item_timestamps` 추가, `record_item_done()`, rolling-average ETA
- `app/services/llm/base.py` — LLM system prompt 강화 (KO/EN/JA): 동일 스타일 prefix 강제, sub-style 변형 금지, 캐릭터 외형 image_prompt 에 직접 기술
- `requirements.txt` — PyJWT 추가했다가 **제거** (stdlib 로 대체)

#### 핵심 변경 파일 (frontend)
- `src/lib/version.ts` — **신규**. `APP_VERSION` 단일 소스
- `src/app/page.tsx`, `src/app/studio/[projectId]/page.tsx` — 하드코딩 `v1.0.1` → `{APP_VERSION}` 동적 참조
- `src/components/studio/StepImage.tsx`, `StepVoice.tsx`, `StepVideo.tsx` — `generatingIndex` 상태, 2초 polling, per-item 로딩 UI, 실시간 미리보기
- `src/components/common/GenerationTimer.tsx` — `isStuck` 감지 (2분 이상 0건)
- `package.json`, `package-lock.json` — 버전 1.1.1

#### 미해결 이슈 (새 세션에서 이어서 처리)
1. **xAI (Grok) / Kling 상태가 여전히 "API key not set" 으로 표시됨**:
   - `.env 파일`에는 `XAI_API_KEY`, `KLING_ACCESS_KEY`, `KLING_SECRET_KEY` 전부 존재 확인 완료
   - `api_status.py` 는 `_read_env_file()` 로 `.env` 를 직접 파싱하는 코드로 수정 완료
   - **의심**: uvicorn `--reload` 가 파일 변경을 감지 못 해 옛 코드가 계속 돌고 있을 가능성. `main.py` 에 reload-trigger 주석 추가해 강제 리로드 시도했으나 사용자 화면은 여전히 동일
   - 현재 `_check_xai()` 에 진단 정보(`v2: env_file=..., keys_in_env=..., os=..., cfg=...`) 를 응답 detail 에 박아둔 상태. 새 세션에서 이 detail 텍스트를 확인해 원인 파악 필요
   - 만약 진단 텍스트가 안 나오면 uvicorn 리로드 자체가 안 되는 것 → 사용자에게 수동 재시작 요청하거나 WatchFiles 설정 점검
   - 진단 텍스트가 나온다면 어떤 필드가 False 인지 보고 해당 경로 수정

2. **영상 생성 1% 멈춤**:
   - FFmpeg 필터 최적화 완료 (scale 8000→2880, ultrafast preset, 180s timeout)
   - per-cut 로깅 추가 완료 (`[video-async] cut N/M START/DONE/FAILED`)
   - 실제 동작 검증 필요. 사용자가 영상 생성 재시도 후 백엔드 콘솔 로그 확인해야 함

3. **프론트엔드 타 서비스 스테일 임포트**:
   - 다음 파일들도 `from app.config import XXX_KEY` 사용 중 → 런타임 키 변경 반영 안 됨:
     - `app/services/tts/openai_tts_service.py`, `elevenlabs_service.py`
     - `app/services/llm/gpt_service.py`, `claude_service.py`
     - `app/services/image/openai_image_service.py`, `fal_generic_service.py`, `midjourney_service.py`, `grok_service.py`, `flux_service.py`
   - `api_status.py`, `kling_service.py`, `fal_service.py` 만 수정했고 나머지는 미처리. 유저가 키를 변경하면 해당 서비스도 재시작해야 반영됨 (또는 동일하게 `cfg` 모듈 참조로 변경 필요)

#### 중요 참고
- **사용자 작업 환경**: Windows (`C:\Users\Jevis\Desktop\longtube`), NAS 는 `C:\Users\Jevis\Desktop\longtube_net`
- **백엔드 실행**: `start.bat` → `python -m uvicorn app.main:app --reload --reload-include *.env --host 0.0.0.0 --port 8000`
- **사용자는 "지시 없이 배치파일 재실행 요구" 를 극도로 싫어함**. 가능한 한 핫리로드로 해결. 그래도 안 되면 그 때만 "LongTube-Backend 창 닫고 `start.bat` 실행" 요청
- **사용자 선호**: 존댓말, 불필요한 설명/자랑질 금지, 빠른 액션 우선, 거짓말 금지
- **버전 관리 규칙**: 버그 수정 = patch (1.1.1 → 1.1.2), 기능 추가 = minor (1.1.1 → 1.2.0). 버전 바꿀 때 `src/lib/version.ts` + `backend/app/main.py` + `frontend/package.json` + `frontend/package-lock.json` **4곳 동시에**

---

> AI 어시스턴트 새 세션: "README.md 읽고 개발 일지의 '미해결 이슈' 섹션부터 이어서 작업"
