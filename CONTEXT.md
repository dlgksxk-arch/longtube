# LongTube 컨텍스트

> 새 세션: "CONTEXT.md 읽고 이어서 개발하자"

## 한줄 요약
주제 입력 → 대본(Claude/GPT) → 음성(ElevenLabs/OpenAI) → 이미지(7종) → 영상(ComfyUI/Kling/FFmpeg) → 자막 → 유튜브 업로드 자동화. 단계별 일시중지·편집·재시작 가능. 1인 사용자 로컬 운용.

## 경로
- **코드 / DB**: `C:\Users\Jevis\Desktop\longtube` (로컬)
- **에셋 (영상/이미지/음성)**: `C:\Users\Jevis\Desktop\longtube_net\projects\` (NAS)
- **Git**: https://github.com/dlgksxk-arch/longtube.git

## 스택
- **프론트**: Next.js 14 (App Router) + TypeScript + Tailwind + lucide-react
- **백엔드**: FastAPI + SQLAlchemy + SQLite + asyncio
  - Celery / Redis 는 requirements 에 있지만 실사용은 `asyncio.create_task` + 인메모리 task_manager (graceful fallback)
- **로컬 AI**: ComfyUI (동일 네트워크 GPU PC, 기본 `http://192.168.0.45:8188`)
- **클라우드 AI**: Anthropic / OpenAI / ElevenLabs / fal.ai / xAI / Kling / Runway / Midjourney

## 현재 버전
- v1.1.63 (2026-04-20) — Opus 4.7 대본 모델 추가, 스테일 임포트 수정(UI 에서 API 키 교체 시 즉시 반영)

## 폴더 구조
```
longtube/
├── CONTEXT.md, DEVLOG.md, CHANGELOG.md, README.md, HANDOFF.md
├── .env.example, .gitignore, docker-compose.yml
├── start.bat, git-push.bat
├── docs/ARCHITECTURE.md
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
- `CUT_VIDEO_DURATION = 5.0` — 모든 컷은 정확히 5초 (fal.ai 5초 클립과 1:1 매칭, 시간 계산 단순화)
- `TTS_MAX_DURATION = 4.5` — 음성은 컷보다 짧아야 여유가 생김
- `TTS_MIN_DURATION = 3.0` — 이보다 짧으면 감속 보정

## 주의
- Midjourney 는 공식 API 없음 → `NotImplementedError` (프록시 서비스 연동 TODO)
- Nano Banana 는 fal.ai 엔드포인트 실패 시 Flux Dev 로 투명 폴백
- Claude 는 JSON 모드가 없어서 regex 파서로 추출 + 미완결 JSON 복구 로직 포함
- API 키는 `backend/.env` 에 저장, UI (`/api/api-keys`) 로 교체 시 v1.1.63 부터 즉시 반영
- `client_secret.json`, `token.json`, `*.db`, `data/`, `backend/logs/` 는 git 제외

> 업데이트: 2026-04-20 (v1.1.63)
