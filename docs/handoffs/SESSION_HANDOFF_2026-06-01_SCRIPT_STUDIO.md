# LongTube Session Handoff - 2026-06-01 Script Studio

## 작업 원칙

- 생성 결과물에 문제가 있어도 결과물 파일을 직접 고치지 않는다.
- 문제 해결은 로직 수정으로 다음 생성물에 적용한다.
- 중요한 기능 수정은 사용자 허락을 받고 진행한다.
- 추측하지 말고 실제 파일과 상태를 확인한다.

## 현재 워크스페이스

- 경로: `C:\Users\Ai_M9\Desktop\longtube`
- 현재 브랜치 확인은 다음 세션에서 `git branch --show-current`로 다시 확인할 것.
- 작업트리는 매우 더럽다. 커밋하지 않았다.
- 마지막 확인 시각 기준 검증:
  - `python -m py_compile backend/app/services/script_studio_service.py backend/app/services/llm/ollama_service.py backend/app/services/llm/base.py backend/app/services/llm/script_quality.py backend/app/routers/script_studio.py` 통과
  - `cd frontend && npx tsc --noEmit` 통과

## Git 변경 상태

수정된 추적 파일:

- `backend/app/main.py`
- `backend/app/routers/api_status.py`
- `backend/app/routers/projects.py`
- `backend/app/routers/script.py`
- `backend/app/routers/subtitle.py`
- `backend/app/services/estimation_service.py`
- `backend/app/services/image/prompt_builder.py`
- `backend/app/services/llm/base.py`
- `backend/app/services/llm/claude_service.py`
- `backend/app/services/llm/gpt_service.py`
- `backend/app/services/llm/script_quality.py`
- `backend/app/services/llm/visual_policy.py`
- `backend/app/services/oneclick_service.py`
- `backend/app/services/shorts_service.py`
- `backend/app/services/thumbnail_service.py`
- `backend/app/services/video/comfyui_service.py`
- `backend/app/services/video/prompt_builder.py`
- `backend/app/services/video/wan_control.py`
- `backend/app/tasks/pipeline_tasks.py`
- `backend/tests/test_ghost_pipeline.py`
- `backend/tests/test_oneclick_stability.py`
- `docs/oneclick_queue_template.xlsx`
- `frontend/src/app/oneclick/layout.tsx`
- `frontend/src/app/oneclick/live/displayHelpers.ts`
- `frontend/src/app/oneclick/live/page.tsx`
- `frontend/src/app/oneclick/live/taskHelpers.ts`
- `frontend/src/app/oneclick/page.tsx`
- `frontend/src/app/page.tsx`
- `frontend/src/app/studio/[projectId]/page.tsx`
- `frontend/src/app/v2/presets/[id]/page.tsx`
- `frontend/src/components/common/LocalServiceStatus.tsx`
- `frontend/src/components/studio/StepSettings.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/version.ts`

새 파일/디렉터리:

- `backend/app/routers/script_studio.py`
- `backend/app/services/llm/ollama_service.py`
- `backend/app/services/script_studio_service.py`
- `backend/app/services/story_plan_stage.py`
- `docs/oneclick_queue_template.before_ch1_remaining_20260601T043859Z.xlsx`
- `frontend/src/app/oneclick/script-studio/`
- `frontend/src/app/script-studio/`
- `frontend/src/components/script-studio/`
- `frontend/src/components/studio/StepStory.tsx`
- `output/`
- `tmp/run_gemma4_ep18_block_test.py`

주의:

- `tmp/run_gemma4_ep18_block_test.py`는 Gemma4 EP.18 1~3블럭 비교 테스트용으로 추가됨.
- 사용자가 중단해서 실제 테스트 실행 결과 파일은 아직 없다.

## 큰 변경 요약

### 1. 대본실 Script Studio 추가

목표:

- 롱폼공장 안에 `대본실` 메뉴를 넣고, 제작큐 주제를 선택해 스토리 설계와 대본 생성을 따로 수행한다.
- 롱폼공장 프로젝트 설정과 채널별 프로젝트를 자동 연결한다.
- 작업 중 다른 메뉴로 이동하거나 창을 닫아도 서버 작업은 계속 진행된다.
- 사용자가 중지 버튼을 누르면 서버 작업 중지 요청이 강하게 반영되도록 했다.

주요 파일:

- `backend/app/routers/script_studio.py`
- `backend/app/services/script_studio_service.py`
- `backend/app/services/story_plan_stage.py`
- `frontend/src/app/script-studio/`
- `frontend/src/app/oneclick/script-studio/`
- `frontend/src/components/script-studio/`
- `frontend/src/lib/api.ts`

### 2. 스토리 설계 단계 추가

대본 생성 전에 story plan을 만든다.

스토리 플랜 주요 구조:

- `story_core`
- `story_beats`
- `scene_blocks`
- `fact_ledger`
- `visual_plan`
- `visual_world`
- `character_map`
- `causality_chain`
- `script_checklist`

중요 규칙:

- `scene_blocks`는 150컷 기준 30개.
- 각 block은 5컷 단위.
- 대본 생성 모델은 새 줄거리를 만들지 않고 scene_block을 확장해야 한다.
- `story_core`, `story_beats`, `scene_blocks`는 일반 대본 규칙보다 우선한다.
- 사실성 규칙은 항상 최우선이다.

### 3. 대본 생성 방식 변경

기존:

- 150컷 전체를 한 번에 생성.

변경:

- Ollama 로컬 모델은 `scene_block`별 5컷씩 생성.
- 총 30블럭.
- 블럭마다 Python 기계 검수 후 다음 블럭으로 진행.
- 블럭 생성 실패 시 로컬 재시도.
- 3회 실패 후 GPT-5.5 폴백 1회 호출 로직이 들어가 있음.

주요 파일:

- `backend/app/services/llm/ollama_service.py`
- `backend/app/services/llm/base.py`

중요 상수:

- `OLLAMA_NUM_CTX = 65536`
- `SCENE_BLOCK_MAX_REGENERATIONS = 2`

### 4. partial_script / script 승격 정책 변경

의도:

- 대본 생성이 끝났다고 바로 `script.json`으로 확정하지 않는다.
- 먼저 `partial_script.json`에 저장한다.
- 1차 검사가 끝나고 통과한 뒤 `script.json`으로 승격한다.

현재 반영:

- `partial_script.json` 읽기/표시 로직 있음.
- `script.json` 승격 로직 있음.
- 1차 검사 후 쇼츠 선정해서 script에 반영하려는 구조로 변경.

관련 파일:

- `backend/app/services/script_studio_service.py`
- `frontend/src/components/script-studio/ScriptStudioWorkspace.tsx`

### 5. 쇼츠 선정 시점 변경

요청:

- 대본 생성 단계에서 쇼츠 후보 선정하지 말 것.
- 1차 검사에서 쇼츠 대상 선정.
- 쇼츠 4개 중 3개만 통과해도 생성/업로드 가능하게 할 것.

현재 반영:

- `backend/app/services/llm/base.py`의 대본 생성 규칙에서 쇼츠 후보 생성 금지.
- `backend/app/services/llm/ollama_service.py`에서 scene_block 생성 결과의 `shorts_candidate=false` 강제.
- `shorts_group`, `shorts_reason`, `shorts_score`, `shorts_title` 제거.
- `script_quality.py`에서 쇼츠 하드 실패 성격 약화/조정.

주의:

- 이전 실패 초안 `a25926952b`의 `script.json`에는 아직 쇼츠 60컷이 들어가 있음. 과거 실패 결과물이다.
- 현재 새 초안에서는 생성 단계 쇼츠 선정이 되면 안 된다.

### 6. 검수 프로세스 설계/일부 구현

사용자가 원하는 구조:

- 생성
- Python 기계검수
- 1차 전체검수: Gemma
- 1차 수정: Mistral
- 2차 전체검수: Gemma
- 2차 수정: Qwen
- 3차 전체검수: Gemma
- 3차 수정: Gemma
- 발악검수: GPT-5.5
- 최종 전체검수: Gemma

추가 합의:

- Python은 기계 검수 담당.
- Mistral/Qwen/Gemma는 기계적 문제를 억까로 잡지 말고, 역할에 맞는 문제만 봐야 한다.
- Gemma 최종 판단은 실제 시청자 관점으로 전체 흐름을 본다.
- Gemma가 실패 판정할 때는 블럭 단위 수정 지시를 작성한다.
- 수정은 블럭 단위로 다음 수정 모델에 전달한다.

현재 UI 반영:

- 검사 탭에 블럭 진행표가 있음.
- 생성작업록은 공장 적용 탭으로 이동.
- 대본생성 탭에서 블럭 진행표는 삭제.
- 대본생성 탭에는 블럭별 대본 결과 표시.
- 검사 탭의 생성작업록은 삭제.

주의:

- 검수 전체 로직은 계속 손봐야 한다.
- 특히 `script.json` 승격 타이밍과 쇼츠 선정 타이밍을 실제 실행으로 재검증해야 한다.

### 7. UI 변경

대본실 탭:

- `스토리 생성`
- `대본 생성`
- `검사`
- `공장 적용`

주요 UI 요청 반영:

- 작업 중 프로그레스 표시.
- 대본 생성 중 실시간 어느 블럭인지 표시.
- 생성된 블럭별 결과를 대본생성 화면에 표시.
- 작업 기록과 평균 소요시간 표시.
- 작업 중지 기능.
- 선택 주제 다중선택.
- 선택된 주제 연속 생성.
- 제작큐에서 기존 대본 여부 표시.
- 초안 삭제 기능.
- 같은 주제로 재생성 시 기존 초안 삭제 확인창.
- 서버 상태에 대본서버 상태 추가.
- 기본 모델 표시 관련 수정 요청 있었음.

### 8. 제작큐 엑셀 템플릿 변경

요청된 컬럼:

- `에피소드번호`
- `주제`
- `연도`
- `배경`
- `핵심인물`
- `주요인물1`
- `주요인물2`
- `주요인물3`
- `사건의출발`
- `주요사건`
- `갈림길/반전`
- `핵심내용`
- `결과/의미`

관련 파일:

- `docs/oneclick_queue_template.xlsx`
- 백업: `docs/oneclick_queue_template.before_ch1_remaining_20260601T043859Z.xlsx`

주의:

- 채널1 남은 에피소드 내용 업데이트를 진행했음.
- 새 세션에서 필요하면 실제 엑셀 내용을 다시 열어 확인할 것.

### 9. 이미지/비주얼 프롬프트 변경

사용자 요구:

- 시대/장소/문화 고증을 최상위에 박고 시작.
- 매 컷마다 중복되는 시대/장소 고증을 줄이되, 이미지 생성 시 최상위 `visual_world`를 계속 참조.
- 사전 방식 금지. 한국사 전용으로 만들지 말고 범용 고증 요구.
- 이미지가 재미없으니 전쟁/공격 장면은 강한 액션을 넣는다.
- 전체 이미지 중 일부는 인물 클로즈업, 일부는 격렬한 액션.
- 인물 수 제한/군중 제한 관련 네거티브/포지티브는 삭제 요청이 있었음.

관련 파일:

- `backend/app/services/image/prompt_builder.py`
- `backend/app/services/video/prompt_builder.py`
- `backend/app/services/llm/base.py`
- `backend/app/services/llm/visual_policy.py`

주의:

- 사용자는 네거티브 프롬프트가 오히려 모델에 표현되는 문제를 강하게 지적했다.
- 다음 수정 때도 네거티브를 늘리는 방식은 피해야 한다.

### 10. 썸네일 규칙 변경

반영 요청:

- 썸네일 문구는 반드시 2줄.
- 각 줄 4~10자 정도.
- 쉬운 장면어 사용.
- 반전형/대립형/미스터리형/위험형/숫자형 중 하나.
- 제목과 썸네일 문구는 같은 말 반복 금지.

썸네일 이미지 프롬프트 조정:

- 반복 규칙 줄임.
- hero subject는 40~55% 권장.
- negative space는 35~45%.
- 고정 색상 대신 story-matched accent color.
- most important person 대신 most clickable story-critical character.
- `4K ultra-detailed` 대신 `high-resolution documentary cartoon thumbnail, clean bold shapes` 방향.

관련 파일:

- `backend/app/services/llm/base.py`
- `backend/app/services/thumbnail_service.py`

## 현재 데이터 상태

### 활성 초안

경로:

- `C:\Users\Ai_M9\Desktop\longtube\data\script_studio\drafts\f5e0b56733`

상태:

- 제목: `역계경 2천 호 남하, 고조선 내부가 갈라졌다`
- 채널: `1`
- 프로젝트: `딸깍폼-10분역공`
- `status`: `story_ready`
- `story_status`: `completed`
- `script_status`: `running`
- `active_job_id`: `e6c6ee36c6d1`
- `active_job_pid`: `17048`
- `active_stage`: `script`
- `generation_progress.message`: `scene_block 1/30 생성 중 (1-5컷)`
- `generation_progress.model`: `ollama:qwen3:32b`

현재 파일:

- `draft.json` 있음
- `story_plan.json` 있음
- `partial_script.json` 없음
- `script.json` 없음
- `validation_report.json` 없음

주의:

- 마지막 확인 시 `python` 프로세스 PID `17048`이 존재했다.
- 새 세션 시작 시 먼저 `Get-Process -Id 17048`와 초안 상태를 다시 확인할 것.
- 사용자가 멈추라고 하기 전에는 작업을 임의로 죽이지 말 것.

### 삭제된 실패 초안 EP.18

경로:

- `C:\Users\Ai_M9\Desktop\longtube\data\script_studio\deleted_drafts\a25926952b_20260601T102105Z`

상태:

- 제목: `역계경 2천 호 남하, 고조선 내부가 갈라졌다`
- 채널: `1`
- 프로젝트: `딸깍폼-10분역공`
- `story_status`: `completed`
- `script_status`: `failed`
- `story_plan.json` 있음
- `partial_script.json` 있음
- `script.json` 있음
- `validation_report.json` 없음

확인된 품질 문제:

- `script.json`은 150컷, scene_blocks 30개, scene_block_id 150개.
- 그러나 주제가 `역계경 2천 호 남하`인데 본문이 `왕준/위만`으로 많이 샜다.
- 단어 빈도 확인:
  - `왕준` 48회
  - `위만` 40회
  - `역계경` 40회
  - `우거왕` 0회
  - `한나라` 0회
  - `왕검성` 0회
- `visual_subject` / `visual_scene` 누락 컷: 106~110.
- TTS 길이 범위 밖: 119/150컷.
- 반복 문장 있음.
- `script.json`에는 쇼츠 후보 60컷이 들어가 있으나 `partial_script.json`은 0컷. 이전 실패 로직 흔적.

결론:

- 이 결과물은 사용하면 안 된다.
- 직접 수정 금지. 원인 로직을 고쳐 다음 생성물에 적용해야 한다.

### 삭제된 CH3 실패 초안

경로:

- `C:\Users\Ai_M9\Desktop\longtube\data\script_studio\deleted_drafts\57c8c89ab4_20260601T102211Z`

상태:

- 제목: `몽골은 왜 두 번이나 일본을 침공했을까`
- 채널: `3`
- 프로젝트: `CH3 딸깍폼-일본역사`
- `story_status`: `failed`
- `script_status`: `empty`

기존 문제:

- topic alignment 검사가 `몽골, 번이나, 일본, 침공했을까, 연도, 배경` 같은 부적절한 anchor를 요구해서 실패했다.

수정한 로직:

- `script_quality.py`에서 엑셀 템플릿 라벨 anchor 제외.
- 질문 어미 anchor 제외.
- 일본사 alias 일부 추가.
- `쿠빌라이` 같은 인명에서 마지막 `이`를 무조건 strip하지 않게 보완.

다음 세션 확인 필요:

- CH3 같은 주제로 재생성 시 topic alignment가 통과하는지 실제로 확인.

## 현재 서버/로컬 LLM 상태

Ollama API 확인:

- `http://127.0.0.1:11434/api/tags` 응답 확인됨.

등록 모델:

- `gemma4:31b`
- `mistral-small3.2:24b`
- `qwen3:32b`

주의:

- `ollama` CLI는 PATH에 잡히지 않았다.
- CLI 대신 API로 확인했다.

## Gemma4 테스트 상태

사용자 요청:

- EP.18 기존 story_plan 기준으로 Gemma4가 대본 생성하면 나은지 1~3블럭 테스트.

진행 상태:

- `tmp/run_gemma4_ep18_block_test.py` 파일만 생성됨.
- 사용자가 중단해서 실제 실행은 하지 않음.
- 기존 초안 파일은 건드리지 않음.

테스트 스크립트 기능:

- 삭제된 EP.18 초안의 `story_plan.json`을 읽음.
- `ollama:gemma4:31b`로 scene_block 1~3만 생성.
- 결과를 `tmp/gemma4_ep18_block_test/result_*.json`에 저장하도록 작성됨.
- 원본 `script.json`, `partial_script.json`은 수정하지 않음.

다음 세션에서 실행하려면:

```powershell
$env:PYTHONIOENCODING='utf-8'
python tmp\run_gemma4_ep18_block_test.py
```

실행 전 확인:

- 현재 활성 Qwen 대본 생성 작업이 돌고 있는지 먼저 확인.
- 동시에 무거운 Ollama 모델을 돌리면 GPU/CPU 자원 충돌 가능성이 있음.

## 주요 로직 파일별 메모

### `backend/app/services/llm/base.py`

주요 변경:

- 스토리 설계 프롬프트 강화.
- `scene_blocks` 30개 요구.
- `fact_ledger`, `visual_plan`, `visual_world`, `script_checklist` 포함.
- 대본 생성 시 story_plan 우선 규칙 추가.
- scene_block 대본 생성 system/user prompt 추가.
- 썸네일 문구/이미지 규칙 조정.
- 쇼츠 후보를 대본 생성 단계에서 만들지 않도록 변경.
- 비유/은유 관련 사용자 삭제 요청 반영됨.
- 첫 등장 인물 설명 규칙 추가 요청이 반영되어야 함. 실제 반영 상태는 새 세션에서 해당 문구 검색 필요.

주의:

- 프롬프트가 매우 길어졌다.
- 충돌 규칙이 남아 있을 수 있으니 `완성된 한 문장`, `단문`, `비유` 같은 문구 재검색 필요.

### `backend/app/services/llm/ollama_service.py`

주요 변경:

- Ollama 로컬 모델 서비스.
- `scene_block`별 5컷 생성.
- `partial_script.json` 진행 저장.
- Python 블럭 검수.
- 로컬 재시도.
- GPT-5.5 블럭 폴백.
- `shorts_candidate=false` 강제.
- `image_prompt=""` 강제.

주의:

- 현재 활성 초안 `f5e0b56733`이 이 로직으로 Qwen 생성 중이다.
- 진행 상태가 0/30에서 오래 멈춘다면 Ollama 모델 속도/컨텍스트 문제 확인 필요.

### `backend/app/services/script_studio_service.py`

주요 변경:

- 대본실 초안 CRUD.
- 작업 시작/중지/상태 저장.
- story/script/validate/apply 단계.
- active job pid/id 저장.
- 작업 기록과 평균 소요시간 저장.
- partial_script 읽기/표시.
- 1차 검사 후 script 승격 로직.
- 초안 삭제 시 deleted_drafts로 이동.

주의:

- 과거에 `status=failed`와 `story_status=running`이 같이 남는 상태 꼬임이 있었다.
- 새 초안에서 상태 전이가 정상인지 계속 확인 필요.

### `backend/app/services/llm/script_quality.py`

주요 변경:

- story_plan 구조 검사.
- scene_blocks 구조 검사.
- topic alignment 검사 개선.
- 엑셀 템플릿 라벨 anchor 제외.
- 일본사/몽골 관련 alias 일부 추가.
- script 구조 검사 강화.

주의:

- topic alignment가 너무 빡세거나 너무 느슨해질 수 있다.
- CH3 재생성으로 실제 확인 필요.

### `frontend/src/components/script-studio/ScriptStudioWorkspace.tsx`

주요 변경:

- 대본실 메인 UI.
- 탭 분리.
- 초안 목록.
- 제작큐 연동.
- 모델 선택.
- 블럭별 결과 표시.
- 검사 탭 블럭 진행표.
- 공장 적용 탭 생성 작업록.
- 삭제/중지/새로고침.

주의:

- UI가 빠르게 변경되어 실제 브라우저 동작 재확인 필요.
- 사용자가 "대본생성 탭에서 블럭별 결과물 표시"를 강하게 요청했고 반영됨.

## 사용자가 강하게 지적한 문제

반드시 기억:

- EP.18인데 다른 초안을 보면 안 된다.
- `D:\long_result`가 아니라 대본실 초안만 봐야 하는 요청이 있었다.
- 실패했다고 결과물을 버리거나 삭제하면 안 된다. 검수에서 선정/처리해야 한다.
- 생성 결과물이 시궁창이면 직접 고치는 것이 아니라 로직을 고쳐야 한다.
- 모델 선택이 Qwen인데 GPT-5.5로 되돌아가는 문제를 매우 싫어한다.
- 호출 중 모델 표시가 없음으로 뜨는 문제를 싫어한다.
- 진행 중인데 게이지/블럭표가 안 움직이는 문제를 싫어한다.
- 잘못했으면 변명하지 말고 사실만 말해야 한다.

## 다음 세션 첫 작업 권장 순서

1. 현재 활성 작업 확인:

```powershell
Get-Process -Id 17048 -ErrorAction SilentlyContinue
$env:PYTHONIOENCODING='utf-8'
python - <<'PY'
import json
from pathlib import Path
p=Path(r'C:\Users\Ai_M9\Desktop\longtube\data\script_studio\drafts\f5e0b56733\draft.json')
d=json.loads(p.read_text(encoding='utf-8'))
print(d.get('status'), d.get('story_status'), d.get('script_status'))
print(json.dumps(d.get('generation_progress'), ensure_ascii=False, indent=2))
PY
```

2. `partial_script.json` 생성 여부 확인:

```powershell
Get-ChildItem C:\Users\Ai_M9\Desktop\longtube\data\script_studio\drafts\f5e0b56733
```

3. UI에서 대본실 새로고침 후 상태가 실제 파일과 맞는지 확인.

4. 활성 Qwen 대본 생성이 멈췄으면 원인 확인:

- Ollama 서버 응답
- `qwen3:32b` 응답 시간
- `OLLAMA_NUM_CTX=65536` 영향
- active job 상태 저장 갱신 여부

5. Gemma4 테스트는 활성 생성 작업과 겹치지 않을 때만 실행.

## 확인 명령 모음

Ollama 모델 확인:

```powershell
$env:PYTHONIOENCODING='utf-8'
python - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=5) as r:
    data=json.loads(r.read().decode('utf-8'))
for m in data.get('models', []):
    print(m.get('name'), m.get('size'))
PY
```

대본실 초안 목록:

```powershell
$env:PYTHONIOENCODING='utf-8'
python - <<'PY'
import json
from pathlib import Path
root=Path(r'C:\Users\Ai_M9\Desktop\longtube\data\script_studio\drafts')
for p in root.iterdir():
    if not p.is_dir():
        continue
    dpath=p/'draft.json'
    if not dpath.exists():
        continue
    d=json.loads(dpath.read_text(encoding='utf-8'))
    print(p.name, d.get('title'), d.get('status'), d.get('story_status'), d.get('script_status'))
PY
```

EP.18 실패 결과 품질 재확인:

```powershell
$env:PYTHONIOENCODING='utf-8'
python - <<'PY'
import json
from pathlib import Path
root=Path(r'C:\Users\Ai_M9\Desktop\longtube\data\script_studio\deleted_drafts\a25926952b_20260601T102105Z')
j=json.loads((root/'script.json').read_text(encoding='utf-8'))
cuts=j.get('cuts') or []
text='\n'.join(c.get('narration') or '' for c in cuts)
for t in ['역계경','왕준','위만','우거왕','한나라','왕검성','2천','남하']:
    print(t, text.count(t))
print('cuts', len(cuts))
print('shorts', sum(1 for c in cuts if c.get('shorts_candidate') is True))
PY
```

## 아직 해결 필요

- EP.18 새 활성 초안 `f5e0b56733`이 끝난 뒤 결과 품질 확인.
- Qwen 생성 결과가 또 주제 이탈하는지 확인.
- Gemma4 1~3블럭 테스트 실행 및 Mistral/Qwen 결과와 비교.
- 1차 검사 후 `partial_script.json`에서 `script.json` 승격이 정확히 되는지 확인.
- 쇼츠 선정이 대본 생성 단계가 아니라 1차 검사 단계에서만 되는지 확인.
- 검사 UI 블럭 진행표가 실시간으로 실제 상태를 반영하는지 확인.
- CH3 일본사 topic alignment 수정이 실제 재생성에서 통과하는지 확인.
- 초안 삭제/재생성 확인창이 의도대로 동작하는지 브라우저에서 확인.
- 모델 선택값이 새로고침/탭 이동 후 GPT-5.5로 되돌아가지 않는지 확인.
- `output/` 디렉터리가 git에 포함될 필요가 있는지 확인. 보통 결과물이라 커밋 제외가 맞을 가능성이 높지만, 추측으로 삭제하지 말 것.

## 마지막 사용자 요청

사용자 요청:

- 새 세션으로 이동.
- 변경된 것이 많으니 빠짐없이 세세하게 기록하고 확실히 인수인계.

이 파일이 새 세션 인수인계 기준이다.
