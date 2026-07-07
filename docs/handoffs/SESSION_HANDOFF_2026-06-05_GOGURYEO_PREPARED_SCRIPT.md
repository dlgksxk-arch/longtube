# Session Handoff - 2026-06-05 - Goguryeo Prepared Script Import

## 사용자 지시/운영 원칙
- 답변은 실제 확인한 내용 기준으로 한다. 추측으로 변경하지 않는다.
- 생성 결과물에 문제가 있으면 결과물을 직접 손보지 말고, 다음 생성/변환에 적용될 로직을 수정한다.
- 중요한 기능/로직 수정은 사용자 허락 후 진행한다.
- 설명은 짧게 한다. 새 세션에서는 이 문서를 먼저 읽고 이어간다.

## 현재 작업 주제
- 외부에서 받은 고구려사 대본/큐시트를 우리 `script.json` 구조로 변환해 실제 파이프라인에서 쓸 수 있는지 검증했다.
- 사용자가 지정한 파일:
  - `C:/Users/Ai_M9/Desktop/큐시트_고구려사_대본.xlsx`
  - `Z:/HDD2/longtube/CH1 10분역공/큐시트_고구려사_0605.xlsx`

## 확인한 원본 파일 구조
- 큐시트 파일 `큐시트_고구려사_0605.xlsx`
  - 시트: `큐시트`
  - 헤더 행: 2행
  - `고구려-1`부터 `고구려-30`까지 30개 행 확인
- 대본 파일 `큐시트_고구려사_대본.xlsx`
  - 시트: `1`부터 `30`
  - 대본은 최초 확인 기준 21편까지만 있음
  - 22~30편은 빈 템플릿 성격
  - 3편은 사용자가 스크린샷으로 준 내용 기준으로 150컷 대본을 변환 대상으로 봄

## 대본 변환 방식
1. 큐시트에서 에피소드 번호, 제목, 배경/시대 관련 정보를 읽는다.
2. 대본 엑셀의 해당 시트에서 컷 번호, 나레이션, 이미지 프롬프트를 읽는다.
3. 컷 번호가 `21 #1`, `41 #2`처럼 되어 있으면:
   - 실제 컷 번호는 앞 숫자 `21`, `41`
   - `#1`, `#2`는 숏츠 그룹 번호로 해석한다.
4. 한국어 나레이션은 그대로 둔다.
5. 이미지 프롬프트는 최종 `script.json` 품질검사 때문에 영어만 남긴다.
6. 이미지 프롬프트에는 연도/시대/장소/근거를 덧붙인다.
   - 예: `Year/period`, `Exact place`, `Scene evidence`, `Style`, `Scene`, `Composition`
7. `script_version`은 `"3.1"`로 만든다.
8. 150컷 기준 `scene_blocks`는 15개로 만든다.
   - 현재 품질검사 로직은 `ceil(len(cuts) / 10)` 블럭 수를 요구한다.
   - 각 컷에는 `scene_block_id`를 넣는다.
9. `story_core`는 V3.1 필수 필드를 모두 채운다.
   - `story_axis`
   - `episode_scope`
   - `central_question`
   - `central_answer`
   - `protagonist`
   - `goal`
   - `obstacle`
   - `first_turn`
   - `mid_crisis`
   - `cost`
   - `ending_memory`
10. 각 컷 필수 필드:
   - `cut_number`
   - `scene_block_id`
   - `narration`
   - `image_prompt`
   - `visual_year`
   - `visual_period`
   - `visual_location`
   - `visual_evidence`
   - `shorts_candidate`
   - `shorts_group`

## 백엔드에서 확인한 제약
- 준비 대본 로더 위치:
  - `backend/app/tasks/pipeline_tasks.py`
  - `_PREPARED_SCRIPT_DIRS = ("대본", "scripts", "prepared_scripts")`
- 준비 대본 검증 함수:
  - `_validate_prepared_script()`
- 준비 대본은 프로젝트 폴더 하위의 `대본`, `scripts`, `prepared_scripts` 중 하나에 넣으면 로더가 찾는다.
- `_validate_prepared_script()`는 각 컷에 아래 필드를 요구한다.
  - `cut_number`
  - `narration`
  - `image_prompt`
  - `visual_year`
  - `visual_period`
  - `visual_location`
  - `visual_evidence`
- `assert_script_quality()`는 V3.1에서 `story_core`, `scene_blocks`, `scene_block_id`를 검사한다.
- `image_prompt`에 한글/CJK가 들어가면 품질검사에서 실패한다.
- `image_prompt`에서 `Main subject:`를 150번 반복하면 반복 검사에 걸릴 수 있어 사용하지 않는 방식으로 바꿨다.
- `save_script()`는 `config.result_dir`를 보지 않고 `resolve_project_dir(project_id)` 기준으로 저장한다.

## 생성/검증한 변환 결과 파일
- 1편 초안:
  - `C:/Users/Ai_M9/Desktop/longtube/outputs/import_preview/goguryeo_ep01_script.json`
  - 실제 품질검사 실패 사유:
    - V3.1 필수 `story_core` 부족
    - `scene_blocks` 부족
    - `scene_block_id` 부족
    - 이미지 프롬프트에 한글 포함
- 1편 고스트용:
  - `C:/Users/Ai_M9/Desktop/longtube/outputs/import_preview/goguryeo_ep01_script_ghost_ready.json`
  - 150컷, 15블럭, 영어 이미지 프롬프트
  - 고스트 Step 2 통과
  - LLM 대본 호출 0회
  - 저장 DB 컷 수 150
  - 원본에 `#` 숏츠 마커 없음
- 2편 고스트용:
  - `C:/Users/Ai_M9/Desktop/longtube/outputs/import_preview/goguryeo_ep02_script_ghost_ready.json`
  - 150컷, 15블럭, 영어 이미지 프롬프트
  - 고스트 Step 2 통과
  - LLM 대본 호출 0회
  - 저장 DB 컷 수 150
  - 원본에 `#` 숏츠 마커 없음
- 3편 고스트용:
  - `C:/Users/Ai_M9/Desktop/longtube/outputs/import_preview/goguryeo_ep03_script_ghost_ready.json`
  - 제목: `제3화: 부러진 칼의 주인을 찾아라`
  - 150컷, 15블럭, 영어 이미지 프롬프트
  - 원본 `#` 숏츠 마커 파싱 결과:
    - 총 40컷
    - 그룹 1: 10컷
    - 그룹 2: 10컷
    - 그룹 3: 10컷
    - 그룹 4: 10컷
  - 고스트 Step 2 통과
  - LLM 대본 호출 0회
  - 저장 DB 컷 수 150

## 발견한 문제
- 기존 `annotate_script_shorts()`는 원본 `#` 숏츠 마커가 그룹당 10컷이면 보존하지 않았다.
- 기존 기준은 사실상 `4그룹 x 15컷` 또는 `3그룹 x 15컷`만 기존 마커로 인정했다.
- 그래서 3편 원본의 `#1~#4`, 각 10컷 숏츠가 저장 과정에서 자동 재선정되어 `60컷`, 그룹별 `15컷`으로 바뀌었다.

## 이번 세션에서 수정한 파일
- `C:/Users/Ai_M9/Desktop/longtube/backend/app/services/shorts_service.py`
- `C:/Users/Ai_M9/Desktop/longtube/backend/tests/test_oneclick_stability.py`

## 이번 세션의 숏츠 로직 수정 내용
- `backend/app/services/shorts_service.py`
  - `SHORTS_EXPLICIT_MARKED_MIN_CUT_COUNT = 10` 추가
  - 명시된 숏츠 마커가 있으면 자동 재선정하지 않고 보존하는 분기 추가
  - 기준:
    - 최소 3개 그룹
    - 각 그룹 최소 10컷
  - 이 조건을 만족하면:
    - `shorts_candidate=True`인 원본 컷 유지
    - `shorts_group` 유지
    - `shorts_reason`이 없으면 그룹 목적 기본값만 채움
    - 자동 60컷 재선정으로 넘어가지 않음
- `select_shorts_segments()`도 같은 기준을 적용해 10컷짜리 명시 그룹을 그대로 세그먼트로 반환하게 했다.

## 추가한 테스트
- `backend/tests/test_oneclick_stability.py`
  - `test_annotate_script_shorts_preserves_explicit_four_ten_cut_groups`
- 검증 내용:
  - 150컷 중 1~40컷에 `#1~#4`를 각 10컷씩 표시
  - `annotate_script_shorts()` 후에도 총 40컷 유지
  - `select_shorts_segments()`가 `[10, 10, 10, 10]` 컷 수로 반환

## 실행한 검증
- 단위 테스트:
  - `python -m unittest backend.tests.test_oneclick_stability.ShortsStabilityTests.test_annotate_script_shorts_keeps_four_fifteen_cut_groups backend.tests.test_oneclick_stability.ShortsStabilityTests.test_annotate_script_shorts_accepts_three_fifteen_cut_groups backend.tests.test_oneclick_stability.ShortsStabilityTests.test_annotate_script_shorts_preserves_explicit_four_ten_cut_groups`
  - 결과: 통과
- 컴파일:
  - `python -m compileall backend/app/services/shorts_service.py backend/tests/test_oneclick_stability.py`
  - 결과: 통과
- 3편 JSON 직접 확인:
  - 적용 전: 총 40컷, 그룹별 `10/10/10/10`
  - 적용 후: 총 40컷, 그룹별 `10/10/10/10`
  - 세그먼트:
    - 그룹 1: 21~30
    - 그룹 2: 41~50
    - 그룹 3: 71~80
    - 그룹 4: 91~100

## 주의할 점
- 현재 워크트리는 이미 많은 파일이 수정된 상태였다. 이번 세션에서 직접 수정한 핵심 파일은 위의 두 파일이다.
- 같은 파일 안에는 이전 작업의 변경도 섞여 있을 수 있다. 새 세션에서 diff를 볼 때 이번 숏츠 수정만 따로 분리해서 판단해야 한다.
- 서버가 이미 실행 중이면 백엔드 재시작이 필요하다.
- 1~3편 변환 파일은 `outputs/import_preview` 아래에 있다.
- 고스트 테스트용 임시 폴더는 `tmp/ghost_prepared_*` 계열로 생성되었을 수 있다.

## 다음 세션에서 바로 할 일
1. 이 파일을 먼저 읽는다.
2. 필요하면 백엔드를 재시작한다.
3. 3편 prepared script를 실제 프로젝트 `대본/EP_003.json`에 넣어 작업대/원클릭 경로에서 다시 확인한다.
4. 4편 이후도 같은 변환 규칙으로 처리한다.
5. 원본 `#` 마커가 있으면 숏츠 자동 재선정을 하지 않는 것이 현재 의도다.
