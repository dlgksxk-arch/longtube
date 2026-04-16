# LongTube 컨텍스트

> 새 세션: "CONTEXT.md 읽고 이어서 개발하자"

## 한줄 요약
주제 입력 → 대본(Claude/GPT) → 음성(ElevenLabs) → 이미지(9종) → 영상(FFmpeg/Kling 등) → 자막 → 유튜브 업로드 자동화. 단계별 일시중지·편집·재시작 가능.

## 경로
- **코드**: `C:\Users\Jevis\Desktop\longtube` (로컬)
- **에셋**: `C:\Users\Jevis\Desktop\longtube_net\projects\` (NAS)
- **Git**: https://github.com/dlgksxk-arch/longtube.git

## 스택
Next.js 14 + Tailwind (프론트) / FastAPI + Celery + Redis (백엔드) / SQLite / FFmpeg

## 현재 상태: Phase 2 완료 + 실행 검증 통과
- [x] 설계 문서 v2.0 (`docs/ARCHITECTURE.md`)
- [x] **백엔드** (FastAPI + Celery)
  - 라우터 10개, LLM/Image/Video/TTS 팩토리
  - 프로젝트 CRUD, 컷 CRUD + reorder, 파이프라인 제어
  - Redis graceful fallback
  - uvicorn 기동 + 전체 API 통합 테스트 통과
- [x] **프론트엔드** (Next.js 14 + Tailwind)
  - 대시보드 + 6단계 스튜디오 UI 완성
  - 공통 컴포넌트: ModelSelector, LoadingButton, Toast
  - 타입 안전 API 클라이언트 (전체 엔드포인트)
  - next build 통과
- [x] **Git 커밋** (89파일, 7691줄)
- [ ] git push (로컬에서 `git-push.bat` 더블클릭)
- [ ] **→ 다음: Phase 3**

## 수정된 버그 (이번 세션)
1. `config.py`: docstring `\U` 유니코드 에스케이프 → 주석으로 변경
2. `main.py`: DATA_DIR makedirs 추가
3. `pipeline.py`: Redis 미연결 시 graceful fallback
4. `script.py`: `/cuts/reorder` 라우트 순서 버그 (동적 `{cut_number}` 에 먹힘) → 고정 라우트 먼저 배치
5. `script.py`: 컷 목록 조회 API 누락 → `GET /cuts` 추가

## 다음 할 일 (Phase 3)
1. `.env`에 API 키 입력 (ANTHROPIC, OPENAI, ELEVENLABS, FAL 등)
2. Docker Redis 실행 (`docker-compose up -d`)
3. 실전 대본 생성 테스트 (Claude API 호출)
4. TTS → 이미지 → FFmpeg 영상 → 자막 → 최종 렌더링
5. YouTube OAuth 셋업 + 업로드 테스트
6. WebSocket 실시간 진행률 (선택)

## 파일 구조
```
longtube/
├── CONTEXT.md, DEVLOG.md, README.md
├── .env.example, .gitignore, docker-compose.yml
├── start.bat, git-push.bat
├── docs/ARCHITECTURE.md
├── backend/
│   ├── .env (API 키 — git 제외)
│   ├── requirements.txt
│   └── app/
│       ├── main.py, config.py
│       ├── models/ (project, cut, api_log, database)
│       ├── routers/ (projects, pipeline, script, voice, image, video, subtitle, youtube, downloads, models)
│       ├── services/
│       │   ├── llm/ (claude, gpt, factory)
│       │   ├── tts/ (elevenlabs, openai_tts, factory)
│       │   ├── image/ (flux, fal_generic, grok, nano_banana, midjourney, factory)
│       │   ├── video/ (ffmpeg, kling, factory)
│       │   ├── subtitle_service.py
│       │   └── youtube_service.py
│       └── tasks/pipeline_tasks.py
└── frontend/
    ├── package.json, tailwind.config.ts, tsconfig.json
    └── src/
        ├── lib/api.ts
        ├── app/ (layout, page, globals.css, studio/[projectId])
        └── components/
            ├── common/ (ModelSelector, LoadingButton, Toast, Providers)
            └── studio/ (StepSettings, StepScript, StepVoice, StepImage, StepVideo, StepSubtitle)
```

## 주의
- Nano Banana API → Flux fallback
- Midjourney → NotImplementedError
- Claude JSON 모드 없음 → regex 파서
- `auto_pause_after_step=true` 기본

> 업데이트: 2026-04-09 (Phase 2 완료 + 실행 검증 + 버그 5건 수정)
