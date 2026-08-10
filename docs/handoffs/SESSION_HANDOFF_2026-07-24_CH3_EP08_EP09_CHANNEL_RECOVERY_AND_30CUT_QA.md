# LongTube Session Handoff — 2026-07-24

## 목적

이 문서는 2026-07-23~24 세션에서 변경한 이미지 생성/검수 흐름과 CH3 EP08·EP09 오채널 업로드 복구 상태를 다음 세션에 그대로 전달한다.

새 세션은 추측하지 말고 아래 순서로 실제 파일을 읽는다.

1. `AGENTS.md`
2. `docs/SESSION_PROTOCOL.md`
3. `SESSION_HANDOFF.md`
4. 이 문서 전체
5. `docs/handoffs/SESSION_QA_V3_2026-05-08.md` 전체
6. `CONTEXT.md`
7. 현재 요청과 직접 관련된 코드

## 사용자 절대 지시

- 생성 결과물의 문제는 결과물을 직접 수정하지 않고 생성/검수 로직을 수정한 뒤 재생성한다.
- 대사·스토리 연결성을 우선한다.
- 손·팔 해부학 오류, 가짜 문자, 유물/오브젝트 도배를 검수한다.
- 검수를 회피하기 위한 유물 도배를 금지한다.
- 이미지에 여성을 강제로 삽입하지 않는다. 대본에 실제로 필요한 인물만 사용한다.
- 이미지 모델은 명시적 허락 없이 변경하지 않는다.
- GPT 이미지 생성 및 GPT 비전 QA 크레딧을 더 사용하지 않는다.
- 현재 선택된 방식은 30장 생성 → 대사/스토리 연관성 수동 검수 → 실패 로직 수정 및 해당 컷 재생성 → 다음 30장이다.
- 150장 완료 뒤 손 전수검사와 전체 검수를 진행한다.

주의: `thumbnail_model=openai-image-1`인 기존 프리셋/프로젝트가 남아 있다. 다음 제작을 바로 실행하면 정상 AI 썸네일 경로가 OpenAI 이미지/비전 API를 호출할 수 있다. 모델을 임의로 바꾸지 말고, 사용자 지시가 유지되는 동안에는 검수된 본편 컷을 `thumbnail_base_cut_number`로 선택하는 로컬 썸네일 경로만 사용한다.

## 현재 이미지 생성/검수 로직

### 30장 단위 수동 게이트

- `backend/app/services/oneclick_service.py`
  - V3 실행 프로젝트에 `image_review_batch_size=30`과 `image_preflight_cut_count=30`을 강제한다.
  - `image_review_approved_through`를 런타임 상태로 보존한다.
  - 30장 생성 후 작업을 `paused`로 두고, 승인된 컷 범위 다음 30장만 재개한다.
  - 승인 시 실제 커밋된 이미지가 모두 있는지 확인한다.
- `backend/app/routers/image.py`
  - `_image_preflight_cut_count`
  - `_next_image_review_batch`
  - `_pause_for_manual_image_preflight_review`
  - 새 실행과 재개 실행 모두 승인 커서 다음 30장만 생성한다.

### 자동 후처리 검출 제거

- `backend/app/services/image/comfyui_service.py:52266`
  - 생성 직후 자동 검출/재시도/격리 QA를 제거했다.
  - 한 번 생성해 저장한 뒤 직접 검수 단계로 넘긴다.

### 아직 자동화되지 않은 부분

- 150장 완료 뒤 실행되는 별도의 손 전수검출/일괄 손 수정 오케스트레이션은 현재 코드에서 확인되지 않았다.
- 따라서 “150장 완료 뒤 손 전수검사 및 전체 검수”는 아직 수동 운영 단계다.
- 다음 세션은 이 부분을 구현 완료로 보고하지 말고, 실제 코드/실행 경로를 추가하거나 수동 검수를 수행해야 한다.

### 여성 강제 삽입 금지

- 일반 장면에 성인 여성을 일률적으로 주입하지 않는다.
- 성별·인물은 대본과 사건의 실제 주체를 따른다.
- CH3 EP09 썸네일은 이야기 주체가 실제로 아마테라스이기 때문에 여성 인물이 포함된 것이며, 임의 주입이 아니다.

## CH1·CH2·CH3 최신 실제 프로젝트 상태

2026-07-24 DB `data/longtube.db` 확인 결과:

- CH1 최신 완료: `V3_CH1_EP3_2607230605082df8ad`
  - `고이왕의 중앙집권 체제 정비 EP.03`
  - Step 7 / completed
  - `https://youtube.com/watch?v=K0Z2HGZ5Lyc`
- CH2 최신 완료: `V3_CH2_EP4_2607231522143e45da`
  - `Trito and the Three-Headed Serpent Myth EP.04`
  - Step 7 / completed
  - `https://youtube.com/watch?v=U_ahLsv6onY`
- CH3 최신 완료: EP09
  - 아래 복구 내역 참조

현재 `preset_tasks`와 `preset_queue_items`에는 활성/대기 항목이 없다. 다음 순차 후보는 CH1 EP04, CH2 EP05, CH3 EP10이지만 새 세션 시작 직후 자동 실행하지 말고 사용자의 명시 지시를 따른다.

## CH3 오채널 업로드 사고

### 정확한 채널

- 채널명: `闇解き日本史`
- YouTube channel ID: `UCSmk_wHxkZLf23gJN0c5NVQ`
- 토큰: `C:\Users\Ai_M9\Desktop\longtube\token_ch3.json`

### 잘못 사용된 채널

- 채널명: `Jerry`
- YouTube channel ID: `UC3Usftb6-nM4r6atrSBZtxA`
- 잘못 폴백한 프리셋 프로젝트: `7d8b63e5`

### 원인

OneClick 업로드가 명시된 CH3 토큰보다 프로젝트/프리셋에 복사된 `youtube_token.json`을 사용해 Jerry 채널로 업로드했다.

## 채널 업로드 방지 로직 수정

`backend/app/services/oneclick_service.py`

- `_assert_oneclick_youtube_channel_identity` 추가.
- 업로드 OAuth 우선순위를 다음으로 고정:
  1. `token_chN.json`
  2. 현재 프로젝트 토큰 — 채널이 명시되지 않은 경우만
  3. 프리셋 프로젝트 토큰 — 채널/현재 프로젝트 토큰이 없는 경우만
- 채널이 명시된 작업은 다른 토큰으로 폴백하지 않는다.
- 채널별 토큰이 없거나 인증되지 않았으면 업로드를 중단한다.
- config의 `youtube_channel_id`와 인증 토큰의 실제 `channels.list(mine=true)` 결과가 다르면 업로드를 중단한다.
- 검증된 채널명과 channel ID를 로그로 남긴다.

DB의 CH3 프리셋 및 EP08·EP09 프로젝트에는 다음 값이 저장돼 있다.

```text
youtube_channel_id=UCSmk_wHxkZLf23gJN0c5NVQ
```

## CH3 EP08 복구 완료

- 프로젝트: `V3_CH3_EP8_260723001812a36428`
- 결과 폴더:
  `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.8.260723001812a36428`
- 올바른 본편:
  - ID: `GnpG_6Gz4Fs`
  - URL: `https://www.youtube.com/watch?v=GnpG_6Gz4Fs`
  - 공개 / uploadStatus processed / processingStatus succeeded / HD
  - 길이: 20분 51초
- 올바른 숏츠:
  - `OlxTfEIpN2A`
  - `pX-veAO9Qn8`
  - `N0-hD-wdUo8`
  - `qMyc64-aUbk`
- 숏츠 4개 제목은 모두 서로 다르다.

### EP08 썸네일

- 로컬: `output\thumbnail.png`
- 문구는 일본어다.
- 실제 YouTube CDN `maxresdefault.jpg`와 로컬 파일을 비교한 MAE는 `1.03`으로 실제 반영을 확인했다.

## CH3 EP09 복구 완료

- 프로젝트: `V3_CH3_EP9_260723203548b256c7`
- 결과 폴더:
  `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.9.260723203548b256c7`
- 올바른 본편:
  - ID: `UXCpCU1Ey1c`
  - URL: `https://www.youtube.com/watch?v=UXCpCU1Ey1c`
  - 공개 / uploadStatus processed / processingStatus succeeded / HD
  - 길이: 19분 29초
- 올바른 숏츠:
  - `aWtGm_FUHMY`
  - `zUvHjOq2Ah4`
  - `4yQ19cx9qa0`
  - `_YDIb3NqPgo`
- 숏츠 4개 제목은 모두 서로 다르다.

### EP09 썸네일

- 새 GPT 생성은 중단했다.
- 본편의 검수된 `images\cut_41.png`를 사용했다.
- 컷 내용은 아마테라스가 부서진 제구를 물가에서 다루는 실제 이야기 장면이다.
- 로컬 썸네일 생성 설정:

```text
thumbnail_base_cut_number=41
thumbnail_overlay_text=剣と勾玉を噛み砕いた
```

- 로컬 결과: `output\thumbnail.png`
- 실제 YouTube CDN과 로컬 파일 비교 MAE는 `0.78`로 실제 반영을 확인했다.
- 사용자 중단 지시 이후 외부 GPT 이미지 생성 호출은 0회였다.

## 로컬 썸네일 경로 추가

`backend/app/services/thumbnail_service.py`

- `_configured_thumbnail_base_image_path` 추가.
- config의 `thumbnail_base_cut_number`로 기존 프로젝트 컷을 선택한다.
- 선택한 컷이 없거나 번호가 잘못되면 즉시 실패한다.
- `ensure_standard_thumbnail`은 해당 값이 있으면 AI 생성/비전 QA로 가지 않고 `generate_thumbnail` 로컬 합성만 실행한다.
- 결과는 `_basic_thumbnail_file_check`로 최소 파일 검증한다.
- 일본어 오버레이 원문이 명시된 경우 그대로 일본어 레이아웃을 만든다.
- EP08·EP09 일반 AI 경로에는 이야기 고정 프롬프트와 엄격한 주체 불일치 검사가 추가돼 있으나, GPT 크레딧 금지 상태에서는 이 AI 경로를 실행하지 않는다.

## 잘못 올라간 Jerry 영상 삭제 완료

다음 10개는 올바른 채널의 대체 영상 10개가 모두 공개·처리 성공·HD임을 확인한 뒤 삭제했다.

### EP08 삭제 ID

- `Ce9N0EDYHxg`
- `h6s1TDX9ZQo`
- `RV4UhWpsJJQ`
- `siEPDB4d1BU`
- `t54sntoV7pE`

### EP09 삭제 ID

- `hayCwWO0Nsg`
- `XY8yzhu-mnM`
- `xHMpGw47pf0`
- `0Bj6aVJs0iA`
- `EHMSz7KlLV8`

YouTube API 재조회 결과 남은 기존 영상 수는 `0`이다.

## DB 및 산출물 메타데이터 반영

- EP08 `project.youtube_url`:
  `https://youtube.com/watch?v=GnpG_6Gz4Fs`
- EP09 `project.youtube_url`:
  `https://youtube.com/watch?v=UXCpCU1Ey1c`
- 두 프로젝트의 `youtube_shorts_urls`를 새 ID로 교체했다.
- `youtube_upload_result`는 다음으로 저장했다.
  - `uploader_token_source=channel`
  - `uploader_channel_id=3`
  - 실제 channel ID
  - `processed=true`
  - `definition=hd`
  - `verification_method=videos.list_api`
- 두 결과 폴더의 `output\shorts\shorts_uploads.json`도 새 숏츠 ID와 실제 처리 상태로 재작성했다.

복구 상태 원장:

```text
C:\Users\Ai_M9\Desktop\longtube\.codex_tmp\reupload_ch3_ep8_ep9_state.json
verified_and_persisted_at=2026-07-24T01:15:44.045585Z
wrong_channel_deleted_at=2026-07-24T01:17:16.125900Z
```

복구 스크립트:

```text
C:\Users\Ai_M9\Desktop\longtube\.codex_tmp\reupload_ch3_ep8_ep9.py
```

이 스크립트는 이미 완료된 복구 작업용이다. 다음 세션에서 재실행하지 않는다.

## 백업

- DB — EP09 로컬 썸네일 설정 전:
  `data\longtube.before_ch3_ep9_local_thumbnail_20260724_100225.db`
- DB — 올바른 채널 업로드 상태 저장 전:
  `data\longtube.before_ch3_ep8_ep9_correct_channel_state_20260724_101528.db`
- EP08 숏츠 업로드 원장 백업:
  `output\shorts\shorts_uploads.before_correct_channel_20260724_101528.json`
- EP09 숏츠 업로드 원장 백업:
  `output\shorts\shorts_uploads.before_correct_channel_20260724_101528.json`

## 검증

2026-07-24 최종 확인:

- 올바른 CH3 영상 수: 10
- 10개 모두 channel ID `UCSmk_wHxkZLf23gJN0c5NVQ`
- 10개 모두 public
- 10개 모두 uploadStatus `processed`
- 10개 모두 processingStatus `succeeded`
- 10개 모두 HD
- EP08 숏츠 제목 4개 중복 없음
- EP09 숏츠 제목 4개 중복 없음
- Jerry 기존 영상 잔존 수 0
- EP08·EP09 원격 썸네일 실제 반영 확인
- 관련 테스트 15개 통과
- `git diff --check` 오류 없음. CRLF 경고만 있음.

## 런타임 저장 시점

- Backend PID: `20656`
- `http://127.0.0.1:8000/api/health`
  - `status=ok`
  - `version=V3.2`
- ComfyUI queue:
  - running 0
  - pending 0
- 확인된 ComfyUI 프로세스 PID: `20840`, `20484`
- 활성 `preset_tasks`: 없음
- `preset_queue_items`: 없음

## Dirty Worktree

작업 트리는 이전부터 대규모 dirty 상태다.

이번 세션과 직접 관련된 주요 파일:

- `backend/app/services/oneclick_service.py`
- `backend/app/routers/image.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/app/services/image/prompt_compiler.py` — 현재 untracked
- `backend/app/services/thumbnail_service.py`
- `backend/tests/test_oneclick_stability.py`
- `backend/tests/test_image_cut_lifecycle.py`
- `backend/tests/test_image_prompt_compiler.py` — 현재 untracked

`git reset --hard`, `git checkout --`, `git clean`, 광범위 stage/commit을 하지 않는다. 기존 변경을 되돌리지 않는다.

## 다음 세션 시작 시 확인할 것

1. 이 문서를 끝까지 읽는다.
2. DB의 CH1 EP03, CH2 EP04, CH3 EP09 URL을 실제 API로 다시 확인한다.
3. `preset_tasks`와 `preset_queue_items`가 여전히 비어 있는지 확인한다.
4. GPT 크레딧 금지 상태에서 AI 썸네일 경로를 실행하지 않는다.
5. 다음 에피소드를 시작한다면 30장 생성 게이트가 실제로 멈추는지 먼저 확인한다.
6. 매 30장마다 대사/스토리 연결성을 검수하고, 실패는 로직 수정 후 해당 컷만 재생성한다.
7. 150장 완료 뒤 손·팔 해부학, 가짜 문자, 유물 도배, 대사 연결성 전수검수를 한다.
8. 손 전수검출/일괄 수정 자동화는 아직 완료로 간주하지 않는다.
9. 업로드 전 채널별 토큰과 실제 channel ID를 다시 확인한다.
