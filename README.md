# LongTube v1.1.63

유튜브 롱폼 영상을 주제 입력 하나로 자동 생성하는 파이프라인 도구. 1인 사용자 로컬 운용 기준.

대본(Claude/GPT) → 음성(OpenAI TTS/ElevenLabs) → 이미지(7종) → 영상(ComfyUI/Kling/FFmpeg) → 자막 → 유튜브 업로드

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

- **코드 / DB**: `C:\Users\Jevis\Desktop\longtube` (로컬)
- **에셋 (영상/이미지/음성)**: `C:\Users\Jevis\Desktop\longtube_net\projects\` (NAS)
- **Git**: https://github.com/dlgksxk-arch/longtube.git

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| 프론트엔드 | Next.js 14 (App Router) + TypeScript + Tailwind + lucide-react | 다크 UI |
| 백엔드 | Python FastAPI + SQLAlchemy | 비동기 API |
| 백그라운드 | `asyncio.create_task` + 인메모리 `TaskManager` | Celery/Redis 는 requirements 에만 있고 graceful fallback |
| 데이터베이스 | SQLite (`data/longtube.db`) | 1인 사용, 프로젝트 메타데이터 |
| 영상 처리 | FFmpeg | Ken Burns 효과, 자막 번인, 병합 |
| 로컬 AI (선택) | ComfyUI | 같은 네트워크 GPU PC, 기본 `http://192.168.0.45:8188` |
| 패키지 관리 | pnpm (프론트) / pip venv (백엔드) | |

---

## 지원 AI 모델

### 대본 생성
| 모델 ID | 표시명 | Provider | 비고 |
|---------|--------|----------|------|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Anthropic | **기본값** |
| `claude-opus-4-7` | Claude Opus 4.7 | Anthropic | v1.1.63 추가, 1M context |
| `claude-opus-4-6` | Claude Opus 4.6 | Anthropic | |
| `claude-haiku-4-5` | Claude Haiku 4.5 | Anthropic | 저비용 |
| `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` | GPT 계열 | OpenAI | |

### 이미지 생성
| Provider | 모델 | 비고 |
|----------|------|------|
| OpenAI | `openai-image-1` (gpt-image-1), `openai-dalle3` | gpt-image-1 은 `/edits` 로 레퍼런스 이미지 지원 |
| fal.ai | `flux-dev`, `flux-schnell`, `seedream-v4.5`, `z-image-turbo`, `nano-banana`, `nano-banana-2`, `nano-banana-3`, `nano-banana-pro` | |
| xAI | `grok-imagine` | 고정 해상도 |
| Midjourney | `midjourney` | 공식 API 없음 → `NotImplementedError` (프록시 연동 TODO) |
| ComfyUI (로컬) | DreamShaper XL 베이스 5종 (기본/Vector/LongTube 2K·3K·4K), Qwen-Image-Edit 2509 (레퍼런스 필수) | v1.1.55 도입 |

정확한 현재 등록 목록은 `backend/app/services/image/factory.py` 또는 `/api/models/image` 로 확인.

### 음성 생성
| 모델 ID | 표시명 | 비고 |
|---------|--------|------|
| `openai-tts` | OpenAI TTS | alloy, echo, fable, onyx, nova, shimmer |
| `elevenlabs` | ElevenLabs | 계정의 모든 보이스 노출 |

### 영상 생성
| Provider | 모델 | 비고 |
|----------|------|------|
| 로컬 | `ffmpeg-kenburns` | **기본값**, 무료 |
| fal.ai | Seedance 1.0 Lite/Pro, Kling 등 | |
| Kling | `kling-v2` 등 | JWT HS256 (stdlib 구현, PyJWT 비의존) |
| ComfyUI (로컬) | LTX Video 2B distilled, HunyuanVideo 1.5 480p | v1.1.55 이후 도입. WAN 2.2 / LTX 13B 는 워크플로 JSON 만 있고 체크포인트 미설치 |

정확한 현재 등록 목록은 `backend/app/services/video/factory.py` 또는 `/api/models/video` 로 확인.

---

## 파이프라인 흐름

```
[주제 입력]
    │
    ▼
[Step 1: 설정] ─── 비율, 스타일, 타겟 길이, 모델 선택
    │
    ▼
[Step 2: 대본 생성] ─── Claude/GPT → 컷 단위 JSON (나레이션 + image_prompt)
    │  └ 컷별 편집, 추가/삭제/순서변경 가능
    ▼
[Step 3: 음성 생성] ─── OpenAI TTS / ElevenLabs → 컷별 MP3
    │  └ 중지/이어서 생성, 컷별 재생성
    ▼
[Step 4: 이미지 생성] ─── 7종 중 선택 → 컷별 PNG
    │  └ 레퍼런스/캐릭터 이미지 참조, 개별 재생성/업로드
    ▼
[Step 5: 영상 생성] ─── FFmpeg / ComfyUI / Kling 등 → 컷별 MP4 → 병합
    │
    ▼
[Step 6: 자막 + 합성] ─── 자막 스타일 편집 → 최종 렌더링
    │
    ▼
[다운로드 / YouTube 업로드]
```

---

## 파일 구조 (요약)

자세한 구조는 `CONTEXT.md` 참고.

```
longtube/
├── CONTEXT.md, DEVLOG.md, CHANGELOG.md, HANDOFF.md, README.md
├── .env.example, .gitignore, docker-compose.yml
├── start.bat, git-push.bat
├── docs/ARCHITECTURE.md
├── backend/
│   ├── .env, requirements.txt
│   ├── workflows/comfyui/*.json
│   └── app/
│       ├── main.py, config.py
│       ├── models/ (SQLAlchemy)
│       ├── routers/ (18개)
│       ├── services/
│       │   ├── llm/, tts/, image/, video/
│       │   ├── task_manager.py, subtitle_service.py,
│       │   ├── youtube_service.py, oneclick_service.py, thumbnail_service.py
│       └── tasks/pipeline_tasks.py
└── frontend/
    ├── package.json, tailwind.config.ts
    └── src/
        ├── lib/ (api.ts, version.ts)
        ├── app/ (dashboard, studio, oneclick)
        └── components/ (common, studio)
```

---

## 핵심 설계 결정

| 결정 | 이유 |
|------|------|
| 대본 기본 = Claude Sonnet 4.6 | 비용 대비 품질 |
| 이미지 기본 = OpenAI gpt-image-1 | 레퍼런스 이미지 참조 지원 (`/edits`) |
| 영상 기본 = FFmpeg Ken Burns | 무료, 빠름, API 비용 0 |
| 컷 길이 = 5.0초 고정 (`CUT_VIDEO_DURATION`) | 시간 계산 단순화, fal.ai 5초 클립과 1:1 매칭 |
| 음성 3.0~4.5초 강제 (`TTS_MIN/MAX_DURATION`) | 컷 안에 여유 확보 |
| asyncio + 인메모리 TaskManager | Celery/Redis 없이 간단한 비동기 처리 |
| SQLite 로컬 | 1인 사용, 별도 DB 서버 불필요 |
| 에셋은 NAS, DB 는 로컬 | 대용량 분리, DB 는 빠른 IO |
| 레퍼런스 ≠ 캐릭터 | 레퍼런스=스타일(항상), 캐릭터=등장(조건부) |
| API 키 `config` 모듈 속성 참조 (v1.1.63~) | UI 에서 바꾼 키가 서버 재시작 없이 즉시 반영 |

---

## 주의사항

- **Midjourney**: 공식 API 없음. 프록시 서비스 연동 미구현 상태(`NotImplementedError`).
- **Nano Banana**: fal.ai 엔드포인트 최종 실패 시 Flux Dev 로 투명 폴백.
- **Claude JSON**: JSON 모드가 없어서 regex 파서 + 미완결 JSON 복구 로직으로 추출.
- **NAS 의존**: `longtube_net` 이 마운트되어 있어야 에셋 저장/읽기 가능.
- **경로 규약**: DB 에 저장되는 에셋 경로는 상대경로 (`images/cut_1.png`).
- **민감 파일 git 제외**: `.env`, `client_secret*.json`, `token.json`, `*.db`, `data/`, `backend/logs/`, `*.tsbuildinfo`.

---

## 버전 bump 규칙

버전을 바꿀 때는 **5곳을 동시에** 업데이트해야 한다.

- `backend/app/main.py` (FastAPI metadata + `/api/health`)
- `frontend/src/lib/version.ts` (`APP_VERSION` — 프론트 버전 단일 소스)
- `frontend/package.json`
- `frontend/package-lock.json` (최상단 + `packages.""` 의 version 두 곳)

패치 (버그 수정) = 세번째 자리 bump, 기능 추가 = 두번째 자리 bump.

---

## 히스토리 / 개발 일지

- 버전별 변경사항: [CHANGELOG.md](./CHANGELOG.md)
- 날짜별 개발 노트 (문제 진단 + 수정 내역): [DEVLOG.md](./DEVLOG.md)
- 세션 인수인계 메모: [HANDOFF.md](./HANDOFF.md)
- 초기 설계 문서 (현재 구현과 갭 있음): [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md)

---

> 새 세션 시작 시: "CONTEXT.md 읽고 이어서 개발하자"
