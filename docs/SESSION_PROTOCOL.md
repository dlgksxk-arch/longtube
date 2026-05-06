# LongTube Session Protocol

이 문서는 세션 변경 때 Codex가 반드시 따라야 하는 시작 절차입니다.

## 최상위 절대 지킴

- 채널 증가, 채널 수, 프리셋 수와 무관하게 대본 생성 프롬프트 소스는 단 1개 파일만 사용합니다.
- 전역 대본 생성은 반드시 `backend/app/services/llm/base.py`만 사용합니다.
- 추가 대본 생성 프롬프트 파일, 채널별 대본 생성 프롬프트, 프리셋별 대본 생성 프롬프트를 절대 만들지 않습니다.
- 대본 생성 기본 프롬프트 수정은 `backend/app/services/llm/base.py` 안에서만 허용합니다.

## Source Of Truth

- 현재 세션 시작 원장: `SESSION_HANDOFF.md`
- 최신 상세 보관본: `SESSION_HANDOFF_YYYY-MM-DD.md`
- 실행/경로/스택 기준: `CONTEXT.md`
- 사용자용 실행 기준: `README.md`
- 변경 이력: `CHANGELOG.md`, `DEVLOG.md`
- 초기 설계 기록: `docs/ARCHITECTURE.md`

`docs/ARCHITECTURE.md`는 현재 구현 기준 문서가 아닙니다.

## Start Procedure

새 세션 시작 시 아래 순서로 실제 파일을 읽습니다.

1. `docs/SESSION_PROTOCOL.md`
2. `SESSION_HANDOFF.md`
3. `CONTEXT.md`
4. 현재 요청과 직접 관련된 코드 파일

날짜별 `SESSION_HANDOFF_YYYY-MM-DD.md`는 `SESSION_HANDOFF.md`가 가리키는 경우에만 상세 보관본으로 읽습니다.

## Required Checks

작업 전 상태 확인:

```powershell
git status --short
git ls-files backend/logs frontend/tsconfig.tsbuildinfo data *.db token*.json client_secret*.json
```

서버 상태 확인이 필요한 작업:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/oneclick/safety
```

코드 변경 후 기본 검증:

```powershell
python -m py_compile backend\app\main.py backend\app\services\oneclick_service.py backend\app\tasks\pipeline_tasks.py
cd frontend
npx tsc --noEmit
```

## Rules

- 추측하지 않습니다. 파일, 로그, DB, API 응답 기준으로 판단합니다.
- dirty worktree의 기존 변경을 되돌리지 않습니다.
- 토큰/OAuth/DB/로그/캐시는 커밋하지 않습니다.
- `SESSION_HANDOFF.md`만 현재 세션 시작 원장으로 갱신합니다.
- 날짜별 handoff는 보관본입니다. 시작 기준을 여러 파일로 분산하지 않습니다.
- 압축요약으로 기존 사실을 재해석하지 않습니다.

## Dirty Worktree Notes

현재 저장소는 장기 디버깅 변경이 많이 섞일 수 있습니다.

- `git reset --hard`, `git checkout --` 사용 금지
- 생성물 추적 여부는 `git ls-files`로 확인
- 런타임 로그와 TypeScript build cache는 `.gitignore`에 따라 추적하지 않음
- 파일을 정리할 때는 “삭제”와 “Git 추적 해제”를 구분
