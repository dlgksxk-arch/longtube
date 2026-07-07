# LongTube Session Handoff - 2026-05-05

> 보관 문서입니다. 새 세션 시작 기준은 `docs/SESSION_PROTOCOL.md` 와 `SESSION_HANDOFF.md` 입니다.

Saved at: 2026-05-05
Workspace: `C:\Users\Ai_M9\Desktop\longtube`

## 사용자 지시 / 작업 원칙

- 말투: 자비스 톤, 존댓말.
- 추론 금지. 실제 파일, 코드, API 응답, 로그 기준으로 답변.
- 과설명 금지.
- 기존 사용자 변경사항 되돌리지 말 것.
- 워크트리는 매우 dirty 상태. `git reset --hard`, `git checkout --` 금지.
- 토큰/OAuth 파일 커밋 금지:
  - `token.json`
  - `token_ch1.json`
  - `token_ch2.json`
  - `token_ch3.json`
  - `token_ch4.json`
  - 프로젝트별 `youtube_token.json`

## 이번 세션 큰 흐름

사용자는 LongTube oneclick 공장의 실시간 현황, 비용 누수, 썸네일/숏츠 품질, 업로드/재생목록 자동화, 안전장치 강화를 요구했습니다.

핵심 결론:

- 지금은 PC 분산 공장보다 `한 PC 공장 안정화 + 비용 누수 차단 + 멈춤 감지 + 자동 복구`가 우선.
- 남는 PC는 생성 분산보다 모니터링 PC로 쓰는 편이 더 합리적.
- YouTube 재생목록 대량 추가/정렬은 쿼터를 많이 먹음. 특히 `playlistItems.insert/update/list` 반복이 위험.

## 주요 구현 사항

### 1. 업로드 완료 후 새로고침

파일:

- `backend/app/services/oneclick_service.py`
- `frontend/src/app/oneclick/live/page.tsx`

내용:

- YouTube 업로드는 API 응답만 믿지 않고 Studio 업로드 목록에서 확인하도록 강화.
- 업로드 완료/확인 후 실시간 현황 화면이 새로고침되도록 프론트 조건 완화.
- `status=completed`이고 7단계 완료 또는 업로드 로그/URL이 있으면 reload 조건으로 처리.

검증:

```powershell
npx tsc --noEmit
```

### 2. 썸네일 언어/스타일 정리

파일:

- `backend/app/services/thumbnail_service.py`
- `backend/app/services/oneclick_service.py`
- `backend/app/routers/oneclick.py`
- `backend/app/tasks/pipeline_tasks.py`
- `backend/app/routers/youtube.py`
- `backend/app/services/scheduler_service.py`
- `backend/app/services/llm/base.py`
- `backend/app/services/llm/claude_service.py`

내용:

- 썸네일 AI 배경에는 글자를 그리게 하지 않고, 로컬 오버레이로 처리.
- 외국어 채널에서 한글 오버레이가 섞이지 않도록 `suppress_foreign_hangul_thumbnail_overlay` 사용.
- 힌디어/데바나가리 오버레이는 브라우저 렌더러로 처리.
- 10분 역공 스타일:
  - 큰 흰색/노란색 글자
  - 두꺼운 검은 외곽선
  - 하단/중앙 강한 후킹 문구
- 기존 제목을 그대로 박지 않고 `thumbnail_hook` 우선 사용.
- `thumbnail_hook`이 없으면 제목 기반으로 강한 2줄 문구 자동 생성.
- 새 대본 JSON 계약에 `thumbnail_hook` 추가.
- 썸네일 프롬프트 fallback을 더 자극적인 장면 중심으로 변경:
  - conflict, secret, betrayal, danger, impossible-looking evidence
  - one dominant subject
  - high contrast, red/yellow accent, strong foreground silhouette

샘플 재합성:

- `C:\Users\Ai_M9\Desktop\longsult\channels\CH1\projects\딸깍_CH1_EP35_260505-1\output\thumbnail.png`
- 비용 API 호출 없이 기존 배경으로 로컬 합성.
- 결과 문구: `정체가 뭐냐 / 바다 건넌 여인`

검증:

```powershell
python -m py_compile backend\app\services\thumbnail_service.py backend\app\services\oneclick_service.py backend\app\routers\oneclick.py backend\app\tasks\pipeline_tasks.py backend\app\routers\youtube.py backend\app\services\scheduler_service.py backend\app\services\llm\base.py backend\app\services\llm\claude_service.py
```

### 3. 썸네일 제목 언어/대본 제목 언어

파일:

- `backend/app/services/title_utils.py`
- `backend/app/routers/script.py`
- `backend/app/tasks/pipeline_tasks.py`

내용:

- 비한국어 스크립트 제목이 한국어 제목으로 덮이는 문제 수정.
- `script_title_for_language(...)` 추가.
- 비한국어 채널은 generated title 우선, 한국어는 project title/topic 우선.

### 4. 숏츠 자막/소스/선정 개선

파일:

- `backend/app/routers/subtitle.py`
- `backend/app/services/shorts_service.py`
- `backend/app/services/llm/base.py`

내용:

- 숏츠 소스는 `output/final_with_subtitles.mp4` 우선, 없으면 `videos/merged.mp4`.
- 대본 생성 단계에서 숏츠 후보 컷을 더 강하게 마킹:
  - 정확히 12개 컷
  - 모두 `shorts_group=1`
  - `shorts_score` 추가
  - 강한 훅/반전/위험/댓글 유도 포인트 우선
- 숏츠는 연속 구간만 쓰지 않고 비연속 selected cuts를 모아 만들 수 있게 변경.
- `cut_numbers` 기반으로 final source를 trim/concat.
- 숏츠 제목에서 EP 번호 제거.
- 숏츠 내부 source title 표시에서도 EP 제거.

관련 파일:

- `backend/app/services/title_utils.py`
  - `without_episode_prefix(title)` 추가.
- `backend/app/tasks/pipeline_tasks.py`
  - 숏츠 업로드 제목에서 `with_episode_prefix` 제거.
- `backend/app/services/oneclick_service.py`
  - oneclick 숏츠 자동 업로드 제목에서 EP 제거.
- `backend/app/routers/youtube_studio.py`
  - 스튜디오 숏츠 업로드 제목에서 EP 제거.
- `backend/app/services/shorts_service.py`
  - `_source_title()`에서 EP 제거.

검증:

```powershell
python -m py_compile backend\app\services\title_utils.py backend\app\tasks\pipeline_tasks.py backend\app\services\oneclick_service.py backend\app\routers\youtube_studio.py backend\app\services\shorts_service.py
```

### 5. 숏츠 채널명 위치 / 자막 크기

파일:

- `backend/app/services/shorts_service.py`
- `backend/app/services/subtitle_service.py`
- `frontend/src/components/studio/StepSettings.tsx`

내용:

- 숏츠 채널명/프로필 위치를 사용자 표시 위치로 이동.
- 숏츠 자막 크기 3pt 증가.
- 기존 DB 프로젝트 설정 중 과거 기본값과 일치하는 자막 프리셋은 +3pt 업데이트.

렌더 테스트:

- `C:\Users\Ai_M9\Desktop\longsult\channels\CH1\projects\딸깍_CH1_EP34_260505-1\output\shorts\short_1.mp4`

### 6. 숏츠 스타일 / 영상 모델 이름

파일:

- `backend/app/services/video/factory.py`
- `backend/app/services/video/ffmpeg_service.py`

내용:

- `FFmpeg Safe Static (source locked)` 계열을 사용자 요청에 맞춰 `숏츠`로 표시.
- source lock은 no motion과 유사하지만, 숏츠용 impact 효과 중심으로 구성.
- 효과는 source image를 크게 깨지 않도록 zoom punch, light shake, contrast flash 중심.

### 7. 자막 스타일 선택 UI

파일:

- `backend/app/services/subtitle_service.py`
- `frontend/src/components/studio/StepSettings.tsx`

내용:

- 스튜디오 설정에 자막 스타일 선택 UI 추가.
- 현재 사용 스타일을 기본값으로 유지.
- 임팩트 강한 스타일 프리셋 추가.
- 프리셋 키는 backend normalize 함수로 처리.

### 8. 이미지 재사용 설정

파일:

- `backend/app/tasks/pipeline_tasks.py`
- `backend/app/routers/projects.py`
- `frontend/src/lib/api.ts`
- `frontend/src/components/studio/StepSettings.tsx`

내용:

- `image_reuse_group_seconds` 설정 추가.
- 60초 이슈숏 같은 경우 이미지 1장을 60초 동안 재사용 가능.
- 프론트 설정 UI:
  - 컷마다
  - 15초
  - 30초
  - 60초
- `target_duration <= 60`이면 기본값 60으로 normalize.
- 기존 `딸깍폼-이슈숏` 프로젝트 `7d8b63e5`는 `target_duration=60`, `image_reuse_group_seconds=60` 업데이트.

### 9. 프롬프트/이미지 안전 정책

파일:

- `backend/app/services/llm/base.py`
- `backend/app/services/llm/visual_policy.py`
- `backend/app/services/image/prompt_builder.py`

내용:

- 어려운 단어 금지:
  - narration은 중학생도 이해할 쉬운 말.
  - image_prompt도 쉬운 영어 명사/동사 위주.
  - academic, ornate, poetic, esoteric, metaphorical류 금지.
- 현대 국기 연상 금지:
  - flag, national flag, country flag, flagpole, tricolor 등 금지.
  - 일장기/욱일기 연상 구도 금지:
    - red circle on white background
    - centered red disc
    - red sun disc
    - rising sun rays
    - red radial rays
    - hinomaru
- 단, "깃발 금지" 문구가 오히려 깃발을 유도할 수 있어 프롬프트 생성에서는 깃발 자체를 언급하지 않는 방향이 필요함.

### 10. TTS 발음 보정

파일:

- `backend/app/services/tts/number_normalizer.py`
- `backend/app/services/tts/pronunciation_normalizer.py`

내용:

- `EP.`를 TTS가 "이피쩜"으로 읽는 문제 대응.
- 문무왕 등 왕 이름을 잘못 읽는 문제 대응.
- script/subtitle 원문은 보존하고 TTS에 보내는 spoken narration만 보정.

### 11. 일레븐랩스 / LTX 관련 확인

실제 답변/판단:

- ElevenLabs 구독 중이면 음성 비용은 별도 API 크레딧 계산에서 제외해야 함.
- ElevenLabs Image & Video / lip sync / gesture 계열은 입모양/제스처 용도로 검토 대상.
- 현재 LongTube에는 ElevenLabs Image & Video 통합은 없음.
- LTX Desktop/로컬 영상 모델은 비용 절감 후보이나 품질/속도/일관성 검증 필요.
- Seedance는 앞 5장 + 5장마다 1장 구조에서도 편당 비용이 부담될 수 있음.

### 12. 비용 표시/예상비 현실화

파일:

- `backend/app/services/estimation_service.py`
- `frontend/src/app/oneclick/live/page.tsx`

내용:

- 실시간 현황 상단에 편당 예상비를 원화로 표시.
- ElevenLabs 구독 사용자는 음성비를 과대 계산하지 않도록 반영 필요.
- 사용자 지적:
  - 실제 편당 700원대인데 2,275원으로 표시되는 문제.
  - 이후 비용 추정 로직은 구독/로컬/무료 모델과 API 모델을 정확히 분리해야 함.

### 13. YouTube 재생목록 컨트롤 확인

파일:

- `backend/app/services/youtube_service.py`
- `backend/app/routers/youtube_studio.py`

확인된 실제 기능:

- `list_playlists`
- `create_playlist`
- `update_playlist`
- `delete_playlist`
- `list_playlist_items`
- `add_to_playlist`
- `remove_from_playlist`

확인된 권한:

- `backend/app/services/youtube_service.py`의 `SCOPES`:
  - `https://www.googleapis.com/auth/youtube.upload`
  - `https://www.googleapis.com/auth/youtube.force-ssl`
  - `https://www.googleapis.com/auth/youtube`
- 발견된 token들은 대부분 `youtube.upload` + `youtube` 권한 보유.
- `youtube` 전체 권한이 있으면 재생목록 제어 가능.

### 14. CH1 재생목록 작업

채널 확인:

- CH1: `10분역공`
- channel id: `UC-gy5GtNqjlYFBkdfLKEpRg`
- uploads playlist: `UU-gy5GtNqjlYFBkdfLKEpRg`

사용자 요청:

- `위대한 대한민국` 재생목록에 본영상 전부 추가 후 EP 순서 정렬.
- `숏츠보관함-한국사` 재생목록 만들고 숏츠 전부 추가.

실제 반영:

- `위대한 대한민국`
  - playlist id: `PL6emUPhVGAqqKX1xFBAZT6IgWdXQGPXgx`
  - 본영상 34개 들어감.
  - EP 순서 정렬 진행.
  - 마지막 확인 당시 EP.33/EP.34 순서가 바뀌어 있었으나, 이후 정렬 재시도 중 쿼터 초과.
- `숏츠보관함-한국사`
  - playlist id: `PL6emUPhVGAqpgo6oNPHoVXWK2iYuqzOp9`
  - 생성 완료.
  - 숏츠 63개 들어감.

중단 원인:

- YouTube API가 `quotaExceeded` 반환.
- 이후 CH1 설명 업데이트와 CH2 작업도 쿼터 초과로 막힘.

중요:

- 재생목록 "생성" 자체보다 영상 추가/정렬이 쿼터를 많이 씀.
- 특히 `playlistItems.list`, `playlistItems.insert`, `playlistItems.update` 반복이 위험.
- 앞으로 숏츠는 정렬하지 말고 누락분 추가만 권장.

### 15. 매일 오전 7시 재생목록 정리 자동화

Codex 앱 자동화 생성 완료.

자동화:

- 이름: `LongTube 4채널 재생목록 정리`
- ID: `longtube-4`
- 시간: 매일 오전 7시
- workspace: `C:\Users\Ai_M9\Desktop\longtube`
- 실행 환경: local

동작 목표:

- 4개 채널 모두 처리.
- 본영상:
  - 채널별 본영상 재생목록에 누락분만 추가.
  - EP 번호 순서로 필요한 이동만 최소 수행.
- 숏츠:
  - 채널별 숏츠 보관함에 누락분만 추가.
  - 정렬하지 않음.
- 설명:
  - 비어 있거나 다르면 적절한 설명으로 업데이트.
- `quotaExceeded`, 인증 오류, 추가/정렬 실패는 채널별로 보고 후 다음 채널 진행.

주의:

- 자동화는 생성됐지만 실제 다음 실행 시 YouTube API 쿼터 상태에 따라 실패 가능.

### 16. 롱폼 공장 안전장치

파일:

- `backend/app/services/oneclick_service.py`
- `backend/app/services/spend_ledger.py`
- `backend/app/routers/oneclick.py`
- `frontend/src/lib/api.ts`
- `frontend/src/app/oneclick/live/page.tsx`

추가된 핵심 함수:

- `get_safety_state()`
- `register_spend_record(record)`
- `_refresh_task_safety(task, force=False)`
- `_safety_stop_task(task, reason)`
- `_record_safety_event(kind, message, payload)`

새 파일:

- `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_safety.json`

백엔드 동작:

- `spend_ledger._append()`가 유료 비용 기록 후 `oneclick_service.register_spend_record(record)` 호출.
- `amount_usd > 0`인 비용 기록만 검사.
- 실행 중/대기/준비 중 OneClick task가 없는데 유료 비용 기록이 발생하면:
  - 자동제작 30분 중지.
  - emergency stop guard 30분 설정.
  - project_id가 있으면 `pipeline:cancel:<project_id>` 설정.
  - `cancel_ctx.mark_halted(project_id)` 호출.
  - `oneclick_safety.json`에 `spend_leak` 이벤트 저장.
- 실행 중 task는 진행 signature를 추적:
  - status
  - current_step
  - progress_pct
  - current_step_completed
  - current_step_active_cut
  - current_step_cut_progress_pct
  - sub_status
  - completed_cuts_by_step
- signature가 변하지 않으면 `stale_seconds` 갱신.
- 단계별 제한 시간:
  - 2 대본: 480초
  - 3 음성: 420초
  - 4 이미지: 480초
  - 5 영상: 480초
  - 6 렌더: 1200초
  - 7 업로드: 900초
- 제한 시간 초과 시:
  - task `failed`
  - 해당 step `failed`
  - `resume_from_step` 설정
  - cancel/halt 플래그 설정
  - 자동제작 30분 중지
  - safety 이벤트 `stalled_stop` 저장

프론트 동작:

- `GET /api/oneclick/safety` 추가.
- `oneclickApi.getSafety()` 추가.
- 실시간 현황 상단에 `감시 정상` / `감시 경고` 표시.
- 감시 메시지는 title로 노출.

검증:

```powershell
python -m py_compile backend\app\services\oneclick_service.py backend\app\services\spend_ledger.py backend\app\routers\oneclick.py
cd frontend
npx tsc --noEmit
```

안전 상태 조회 실제 결과:

```json
{"status":"ok","last_event":null,"auto_production":{"enabled":true,"remaining_seconds":0}}
```

## 현재 막힌 점 / 다음 세션에서 확인할 것

### 1. YouTube 쿼터

현재 YouTube API가 `quotaExceeded`를 반환했습니다.

막힌 작업:

- CH1 재생목록 설명 업데이트.
- CH2 재생목록 생성/추가/정렬.
- CH1 최종 순서 재검증.

쿼터 회복 후 진행:

1. CH1 `위대한 대한민국` 설명 업데이트.
2. CH1 `숏츠보관함-한국사` 설명 업데이트.
3. CH1 본영상 EP.33/EP.34 순서 최종 확인.
4. CH2 채널 진행:
   - channel: `Jerry’s Archaeo`
   - 본영상 playlist 추천명: `Ancient Breakthroughs & Hidden Origins`
   - 숏츠 playlist 추천명: `Shorts Archive - Ancient History`
   - 본영상은 EP 순서 최소 정렬.
   - 숏츠는 누락분 추가만, 정렬 금지.

### 2. 안전장치 실전 검증

다음 실제 작업 중 확인할 것:

- 실시간 현황 상단 `감시 정상` 표시.
- 작업 진행 중 `safety.stale_seconds`가 진행 변화 시 리셋되는지.
- 고의로 진행 정지 상황에서 로그와 자동 중단이 정상 동작하는지.
- 실행 중 작업 없음 + 비용 기록 발생 시 자동제작이 30분 꺼지는지.

### 3. 서버 재시작 필요 여부

이번 세션에서 백엔드/프론트 코드를 수정했습니다.

다음 세션 시작 시 확인:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/oneclick/safety
```

엔드포인트가 404면 백엔드 재시작 필요.

프론트 상단에 감시 표시가 없으면 프론트 dev server 재시작 필요.

### 4. Dirty worktree 주의

이번 세션에서 실제로 많이 만진 주요 파일:

- `backend/app/services/oneclick_service.py`
- `backend/app/services/spend_ledger.py`
- `backend/app/routers/oneclick.py`
- `backend/app/services/thumbnail_service.py`
- `backend/app/services/title_utils.py`
- `backend/app/tasks/pipeline_tasks.py`
- `backend/app/services/shorts_service.py`
- `backend/app/services/llm/base.py`
- `backend/app/services/llm/claude_service.py`
- `backend/app/services/scheduler_service.py`
- `backend/app/routers/youtube.py`
- `backend/app/routers/youtube_studio.py`
- `backend/app/routers/projects.py`
- `backend/app/services/subtitle_service.py`
- `frontend/src/lib/api.ts`
- `frontend/src/app/oneclick/live/page.tsx`
- `frontend/src/components/studio/StepSettings.tsx`

`git diff --name-only`에는 이전 세션/사용자 변경도 많이 섞여 있습니다. 이 파일 목록만 보고 되돌리면 안 됩니다.

## 다음 세션 추천 시작 절차

1. 백엔드/프론트 상태 확인:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/oneclick/safety
```

2. 실시간 현황 브라우저 확인:

```text
http://localhost:3000/oneclick/live
```

3. 현재 실행/큐 확인:

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/oneclick/running
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/oneclick/queue
```

4. YouTube 쿼터가 회복됐으면 CH1 설명/CH2 재생목록 작업 재개.

5. 그 다음 실제 oneclick 작업 1건을 돌리며 안전장치가 `감시 정상`으로 작동하는지 확인.
