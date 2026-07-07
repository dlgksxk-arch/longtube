# LongTube 컨텍스트

> 새 세션 시작 절차는 `docs/SESSION_PROTOCOL.md` 를 따른다.

## 최상위 절대 지킴

- 대본 생성 프롬프트 소스는 채널/프리셋 수와 무관하게 단 1개 파일만 사용합니다.
- 전역 대본 생성은 `backend/app/services/llm/base.py`만 사용합니다.
- 추가 대본 생성 프롬프트 파일, 채널별/프리셋별 대본 생성 프롬프트는 절대 만들지 않습니다.
- 기본 생성 프롬프트 수정만 허용하며, 수정 위치는 `backend/app/services/llm/base.py`입니다.

## 한줄 요약
주제 입력 → 대본(Claude/GPT) → 음성(ElevenLabs/OpenAI) → 이미지(7종) → 영상(ComfyUI/Kling/FFmpeg) → 자막 → 유튜브 업로드 자동화. 단계별 일시중지·편집·재시작 가능. 1인 사용자 로컬 운용.

## 경로
- **코드 / DB**: `C:\Users\Ai_M9\Desktop\longtube` (로컬)
- **새 에셋 기본값**: `C:\Users\Ai_M9\Desktop\longtube\data\outputs\`
- **완료 아카이브 기본값**: `D:\long_result`
- **Git**: https://github.com/dlgksxk-arch/longtube.git

## 스택
- **프론트**: Next.js 14 (App Router) + TypeScript + Tailwind + lucide-react
- **백엔드**: FastAPI + SQLAlchemy + SQLite + asyncio
  - Celery / Redis 는 requirements 에 있지만 실사용은 `asyncio.create_task` + 인메모리 task_manager (graceful fallback)
- **로컬 AI**: ComfyUI (동일 네트워크 GPU PC, 기본 `http://192.168.0.45:8188`)
- **클라우드 AI**: Anthropic / OpenAI / ElevenLabs / fal.ai / xAI / Kling / Runway / Midjourney

## 현재 버전
- **V3.2** — `backend/app/main.py`, `/api/health`, `frontend/src/lib/version.ts` 기준. `frontend/package.json` 메타 버전은 `3.2.0`.

## 폴더 구조
```
longtube/
├── CONTEXT.md, DEVLOG.md, CHANGELOG.md, README.md, SESSION_HANDOFF.md
├── .env.example, .gitignore, docker-compose.yml
├── start.bat, git-push.bat
├── docs/
│   ├── SESSION_PROTOCOL.md
│   ├── ARCHITECTURE.md
│   ├── handoffs/ (날짜별 세션 인계 보관본)
│   ├── research/ (모델/프롬프트 연구 메모)
│   └── archive/v2/ (폐기된 v2 기획 문서)
├── backend/
│   ├── .env (API 키 — git 제외)
│   ├── requirements.txt
│   ├── logs/ (런타임 로그 — git 제외)
│   ├── workflows/comfyui/ (ComfyUI 워크플로 JSON 프리셋)
│   └── app/
│       ├── main.py, config.py
│       ├── models/ (project, cut, api_log, database)
│       ├── routers/ (18개)
│       │   ├── projects, pipeline, script, voice, image, video, subtitle
│       │   ├── interlude, youtube, youtube_studio, downloads
│       │   ├── models, api_status, api_keys, api_balances
│       │   ├── tasks, oneclick, schedule
│       ├── services/
│       │   ├── llm/ (claude, gpt)
│       │   ├── tts/ (elevenlabs, openai_tts)
│       │   ├── image/ (comfyui, flux, fal_generic, grok, nano_banana, midjourney, openai_image)
│       │   ├── video/ (comfyui, fal, kling, ffmpeg)
│       │   ├── oneclick_service, thumbnail_service
│       │   ├── task_manager, subtitle_service, youtube_service
│       └── tasks/pipeline_tasks.py
└── frontend/
    ├── package.json, tailwind.config.ts, tsconfig.json
    └── src/
        ├── lib/ (api.ts, version.ts)
        ├── app/ (layout, dashboard, studio/[projectId], oneclick/live)
        └── components/ (common, studio)
```

## 핵심 설계 상수 (backend/app/config.py)
- `CUT_VIDEO_DURATION = 4.0` — 기본 컷 길이는 4초. 프로젝트 config의 `cut_video_duration`으로 재정의 가능.
- `TTS_TARGET_DURATION = 5.5`
- `TTS_MIN_DURATION = 5.0`
- `TTS_MAX_DURATION = 6.0`
- `TTS_HARD_MAX_DURATION = TTS_MAX_DURATION`

## 주의
- Midjourney 는 공식 API 없음 → `NotImplementedError` (프록시 서비스 연동 TODO)
- Nano Banana 는 fal.ai 엔드포인트 실패 시 Flux Dev 로 투명 폴백
- Claude 는 JSON 모드가 없어서 regex 파서로 추출 + 미완결 JSON 복구 로직 포함
- API 키는 `backend/.env` 에 저장, UI (`/api/api-keys`) 로 교체 시 v1.1.63 부터 즉시 반영
- `client_secret.json`, `token.json`, `*.db`, `data/`, `backend/logs/` 는 git 제외

> 업데이트: 2026-07-02 (V3)
