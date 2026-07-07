# SESSION HANDOFF - 2026-06-19 - CH1 EP14 / CH3 EP69 / CH4 EP14

## 0. 기준

- 작업 위치: `C:\Users\Ai_M9\Desktop\longtube`
- 시간대: `Asia/Seoul`
- 사용자 최신 지시:
  - 새 세션에서 이어갈 수 있게 변경/수정 사항을 세밀하게 저장.
  - 이미지 문제는 결과물 직접 수정 금지. 로직을 수정한 뒤 문제 컷만 재생성.
  - 문자 그리지 말 것.
  - 작업 중인 것은 작업대/현장 물체로 보이게 할 것.
  - 시대, 배경, 국가 고증 최우선.
  - 손 모양/개수, 동물, 무기, 비상식 구조를 확대 확인.
- 현재 작업 방식:
  - 이미지 파일 직접 보정 금지.
  - 불량 컷은 보존 폴더로 이동하고 DB 상태를 되돌린 뒤 이미지 재생성.
  - 로직 수정 후 재생성 결과를 다시 확대 검수.

## 1. 이번 세션에서 직접 수정한 핵심 파일

### `backend/app/services/image/comfyui_service.py`

확인된 직접 변경 범위:

- `comfyui-flux2-klein-4b`, `comfyui-flux2-klein-9b` 워크플로 매핑과 표시명 추가.
- `_pad_image_to_canvas()`가 기존 여백 패딩 방식에서 전체 캔버스 채움/크롭 방식으로 변경됨.
  - 목적: 16:9 이미지가 테두리/여백 카드처럼 나오지 않게 함.
- `DEFAULT_NEGATIVE_PROMPT` 대폭 강화.
  - 문자, 숫자, 가짜 글리프, 캡션, 서명, 문패, 현판, 벽보, 두루마리 글자 방지.
  - 사람 손/손가락/팔/다리/몸통/머리 구조 오류 방지.
  - 말/동물 다리, 머리, 몸통 중복 오류 방지.
  - 현대식 스위치, 콘센트, 벽면 플레이트, 전기 패널, 유리문, 현대 조명 방지.
  - 의복 문양, 가문 문장, 배지, 흉부 패치, 작은 밝은 표식 방지.
- 공통 마스터 스타일을 더 굵은 선과 스타일리시한 성인 그래픽노블/다큐 일러스트 방향으로 강화.
  - `visible ink linework`
  - `bold black ink contour lines`
  - `matte cel shading`
  - `high-contrast graphic shadow shapes`
- 상체/의복 표식 방지 로직 강화.
  - 흉부는 같은 색 천 주름/그림자로만 표현.
  - 정치/가문/계급 표식을 임의 배지로 그리지 않게 함.
- `TEXTLESS_SURFACE_COMFYUI_FRONT_PROMPT` 계열 강화.
  - 벽, 문, 기둥, 종이, 목재, 도구, 갑옷, 배너 표면에 문자/가짜 문자/작은 표식 방지.
- `HAND_ANATOMY_COMFYUI_FRONT_PROMPT` 계열 강화.
  - 보이는 인물은 머리 1, 몸통 1, 팔 2, 손 2, 다리 2 기준.
  - 큰 전경 손, 뒤틀린 손목, 추가 손가락, 융합 손가락, 분리 손 금지.
- 일본 전국시대/혼노지 계열 Flux2 Klein 4B 라우팅 추가 및 보강.
  - 일본 장면 positive prompt에서 `text`, `letter`, `sign`, `paper`, `scroll`, `calligraphy`, `kanji`, `switch`, `outlet` 같은 금지 단어가 positive로 들어가지 않게 필터.
  - 길/동선/전령/명령/문서/정치 회의/작전도 장면은 글자 대신 작업대 위 물체로 표현하도록 전환.
  - `Object-only late Sengoku Japanese relay-token workbench evidence`
  - `Top-down macro view of one continuous historical Japanese low wooden workbench`
  - 작업대에는 끈, 조약돌, 봉인된 묶음, 막대, 무기, 말 장비 등만 배치.
  - 인물/미니어처/문자/종이 글자/현대 벽 스위치 방지.
  - 배너/깃발은 글자 없는 천으로만 표현하고, 문패/현판으로 대체하지 않게 함.
- 고구려 EP13/EP14 계열 Flux2 Klein 4B 라우팅 보강.
  - 전장, 성곽, 기마, 지도/서류/왕관/무기/작업대 장면을 문자 없이 물체 증거 중심으로 전환.
  - 손이 문제될 가능성이 높은 장면은 손을 숨기거나 소매로 덮도록 프롬프트를 조정.
  - 말/동물 장면은 몸 1, 머리 1, 다리 4 원칙을 네거티브에 반영.
- 20세기 과학/CH4 계열 기본 오염 방지 보강.
  - 중세 오염, 현대 신호/전기장치, 라벨, 문서 글자, 현대 방/스위치 방지.

### `backend/tests/test_image_prompt_guards.py`

확인된 직접 변경 범위:

- Flux2 Klein 4B 프롬프트 가드 테스트가 대량 추가/보강됨.
- 주요 테스트 위치:
  - 일본 전국시대 관련: `4688` 이후
    - `test_flux2_klein_japanese_positive_avoids_text_forbidden_words`
    - `test_flux2_klein_japanese_route_markers_use_object_workbench`
    - `test_flux2_klein_japanese_street_scabbards_are_plain`
    - `test_flux2_klein_japanese_rushing_retainers_avoid_wall_switches`
    - `test_flux2_klein_japanese_dispatches_become_textless_packets`
    - `test_flux2_klein_japanese_political_meeting_desks_avoid_paper`
    - `test_flux2_klein_japanese_honnoji_lanterns_avoid_signboards`
    - `test_flux2_klein_japanese_ground_plan_routes_to_workbench`
    - `test_flux2_klein_japanese_banners_become_bare_standard_poles`
    - `test_flux2_klein_japanese_allied_banners_keep_one_command_boundary`
    - `test_flux2_klein_japanese_street_edges_block_signatures_and_nameplates`
  - CH1 고구려 EP13/EP14 관련: `5787`, `7116` 이후
    - `test_flux2_klein_compacts_ep13_cuts_109_111_113_are_full_bleed_and_not_european_castles`
    - `test_flux2_klein_goguryeo_ep14_removes_hand_text_and_modern_metaphors`
- 검증 완료 명령:
  - `python -m py_compile backend\app\services\image\comfyui_service.py backend\tests\test_image_prompt_guards.py`
  - `python -m unittest backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_goguryeo_ep14_removes_hand_text_and_modern_metaphors backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_compacts_ep13_gaya_siege_as_earth_timber_fieldstone backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_compacts_ep13_cuts_109_111_113_are_full_bleed_and_not_european_castles`
  - 마지막 결과: `OK`

### 임시 실행 스크립트

- `_tmp_regen_ch1_ep14\regen_step_image.py`
  - CH1 EP14 문제 컷만 이미지 재생성하기 위해 사용.
- `_tmp_regen_ch1_ep14\rerender_video.py`
  - CH1 EP14 최종 영상 재렌더에 사용.
- `_tmp_regen_ch1_ep14\upload_corrected.py`
  - CH1 EP14 수정본 본편/쇼츠 재업로드에 사용.
- `_tmp_run_pipeline_project.py`
  - CH3 EP69 step 2-4 실행에 사용.

## 2. Flux2 Klein 4B 조사 문서

- 문서 경로: `docs\FLUX2_KLEIN_4B_PROMPT_RESEARCH_2026-06-15.md`
- 사용자 요청으로 Flux2 Klein 4B 관련 조사 내용을 MD로 저장한 파일.
- 이후 프롬프트/운용 로직 수정 근거로 사용.

## 3. CH1 고구려 EP14 완료 상태

- 프로젝트 ID: `V3_CH1_EP14_26061912271895d9c2`
- 제목: `거란과 후연 정벌, 사방의 위협을 지우다 EP.14`
- 결과 폴더: `D:\long_result\CH1\고구려\EP.14.26061912271895d9c2`
- DB 상태:
  - `status`: `completed`
  - `current_step`: `7`
  - `total_cuts`: `150`
  - cut 상태: `video_done: 150`
  - image_path 존재: `150`
- 모델:
  - image_model: `comfyui-flux2-klein-4b`
  - video_model: `ffmpeg-static`

### CH1 EP14 이미지 QA

- 이미지 150개 생성 완료.
- 전체 이미지 검수 후 문제 컷만 재생성 완료.
- 최종 문제 컷 검수 대상:
  - `19, 21, 22, 75, 76, 91, 92, 100, 115, 120, 123, 146, 150`
- 마지막 재생성은 `cut022`.
- `cut022` 최종 확인:
  - 손/무기 정상.
  - 문양/현대물/비상식 구조 없음으로 통과.
- 이전 불량 이미지는 직접 수정하지 않고 보존:
  - `D:\long_result\CH1\고구려\EP.14.26061912271895d9c2\images\qa_rejected_round*`

### CH1 EP14 영상 파일

- 최종 본편:
  - `D:\long_result\CH1\고구려\EP.14.26061912271895d9c2\output\final_with_subtitles.mp4`
  - 크기: `128,493,867 bytes`
  - 수정 시각: `2026-06-19 18:55:50 KST`
- 병합 파일:
  - `D:\long_result\CH1\고구려\EP.14.26061912271895d9c2\output\merged.mp4`
  - 크기: `127,195,587 bytes`
  - 수정 시각: `2026-06-19 18:55:31 KST`
- 썸네일:
  - `D:\long_result\CH1\고구려\EP.14.26061912271895d9c2\output\thumbnail.png`
  - 크기: `1,163,879 bytes`
  - 수정 시각: `2026-06-19 14:56:27 KST`
- 쇼츠 파일:
  - `short_1.mp4`: `5,631,267 bytes`, `2026-06-19 18:56:13 KST`
  - `short_2.mp4`: `5,699,912 bytes`, `2026-06-19 18:56:38 KST`
  - `short_3.mp4`: `5,450,906 bytes`, `2026-06-19 18:57:03 KST`
  - `short_4.mp4`: `5,304,264 bytes`, `2026-06-19 18:57:29 KST`

### CH1 EP14 업로드

수정본 재업로드 완료. 기존 불량 업로드는 삭제하지 않았음.

- 현재 DB `Project.youtube_url`:
  - `https://youtube.com/watch?v=4KZbWWvlByQ`
- 이전 불량 본편 URL:
  - `https://youtube.com/watch?v=hht489fiiiM`
- 수정본 본편 업로드 기록:
  - `corrected_reupload_main.url`: `https://youtube.com/watch?v=4KZbWWvlByQ`
  - `video_id`: `4KZbWWvlByQ`
  - `thumbnail_uploaded`: `true`
- 수정본 쇼츠 업로드:
  - `short_1`: `https://youtube.com/watch?v=lP7Om-kw-N4`
  - `short_2`: `https://youtube.com/watch?v=i7SHEuGyzm8`
  - `short_3`: `https://youtube.com/watch?v=CDrnR7UMYGw`
  - `short_4`: `https://youtube.com/watch?v=iIWsDMVAe2w`
- 주의:
  - config의 `youtube_shorts_urls`에는 이전 쇼츠 URL이 남아 있음.
  - 실제 수정본 쇼츠는 `corrected_reupload_shorts` 및 `shorts_uploads`에 기록되어 있음.

## 4. CH3 EP69 현재 상태

- 프로젝트 ID: `V3_CH3_EP69_260619122724cc71c5`
- 제목: `혼노지의 변은 왜 일어났을까 EP.69`
- 결과 폴더: `D:\long_result\CH3\EP.69.260619122724cc71c5`
- DB 상태:
  - `status`: `completed`
  - `current_step`: `4`
  - `total_cuts`: `150`
  - step states: `2 completed`, `3 completed`, `4 completed`, `5 pending`, `6 pending`, `7 pending`, `story completed`
  - cut 상태: `image_done: 150`
  - image_path 존재: `150`
  - `youtube_url`: `None`
- 모델:
  - image_model: `comfyui-flux2-klein-4b`
  - video_model: `ffmpeg-static`

### CH3 EP69 step 2-4 실행 기록

- 실행 PID 파일:
  - `_tmp_run_ch3_ep69_step24.pid`
- 로그:
  - `_tmp_run_ch3_ep69_step24_stdout.log`
  - `_tmp_run_ch3_ep69_step24_stderr.log`
- 마지막 로그:
  - `[Image] 완료: 150/150 이미지 생성됨`
  - `[comfyui] /free 호출 성공 (unload=True, free=True)`
  - `[Thumbnail] generated: D:\long_result\CH3\EP.69.260619122724cc71c5\output\thumbnail.png`
  - `run_pipeline done project=V3_CH3_EP69_260619122724cc71c5 steps=2-4`
- 이미지 수:
  - `D:\long_result\CH3\EP.69.260619122724cc71c5\images`
  - `cut_*.png`: `150`

### CH3 EP69 검수 시트

- 검수 시트 폴더:
  - `C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch3_ep69`
- 방식:
  - 원본 1280x720 이미지 4개를 2x2로 묶은 원본 크기 확인용 시트.
  - `functions.view_image detail:"original"`로 확대 검수.
- 생성된 시트:
  - `ch3_ep69_001_004.png`부터 `ch3_ep69_149_150.png`
- 현재 검수 완료:
  - `ch3_ep69_001_004.png`부터 `ch3_ep69_137_140.png`까지 확인 완료.
- 아직 미확인:
  - `ch3_ep69_141_144.png`
  - `ch3_ep69_145_148.png`
  - `ch3_ep69_149_150.png`

### CH3 EP69 검수 결과 - 확정 재생성 후보

이미지 직접 수정 금지. 아래 컷은 로직 보강 후 해당 컷만 재생성해야 함.

- `cut002`
  - 오른쪽 벽면에 현대식 흰색 직사각 플레이트/스위치 의심.
- `cut019`
  - 왼쪽 벽에 현대식 스위치 형태 명확.
- `cut034`
  - 벽면에 현대식 패널/표식 형태.
- `cut054`
  - 양쪽 벽면에 현대식 스위치/콘센트 형태.
- `cut058`
  - 벽면 스위치 형태.
- `cut060`
  - 벽면 스위치 형태.
- `cut062`
  - 현대식 스위치 형태.
- `cut063`
  - 출입구 옆 작은 표찰이 문자처럼 보임.
- `cut078`
  - 벽면 스위치 형태.
- `cut090`
  - 벽면 스위치/콘센트 형태.
- `cut097`
  - 벽면 현대식 스위치.
- `cut102`
  - 오른쪽 벽에 문패/표찰처럼 보이는 사각 물체와 글자 유사 흔적.
- `cut113`
  - 왼쪽 건물 기둥 쪽 세로 표식이 문자처럼 보임.
- `cut130`
  - 바닥 매트 위 작은 흰 패들/표식에 기호나 문자처럼 보이는 요소.

### CH3 EP69 검수 결과 - 개별 확대 확인 필요

아래는 시트 기준 의심만 기록. 원본 개별 이미지를 확대해서 최종 판정 필요.

- `cut010`
  - 깃발/표식 유사 물체에 문자처럼 보이는 흔적 의심.
- `cut035`
  - 처마/문 쪽 문양이 문자처럼 보일 수 있어 확인 필요.
- `cut036`
  - 벽/목재 표식이 문자처럼 보일 수 있어 확인 필요.
- `cut073`
  - 작업대 위 종이/필기 동작이 있어 문자 생성 여부 확대 확인 필요.
- `cut075`
  - 작업대 위 종이/필기 동작이 있어 문자 생성 여부 확대 확인 필요.

### CH3 EP69 검수 중 통과로 본 주요 확인

- `cut061`
  - 말 머리/몸 구조 정상.
- `cut103`
  - 말 머리/몸 구조 정상.
- `cut122`, `cut124`
  - 말 포함 장면. 머리/몸 구조 문제 없음.
- 다수 인물 장면:
  - 현재 확인 구간에서 손 3개, 몸 2개, 머리 중복처럼 확정되는 오류는 발견하지 못함.
- 작업대 컷:
  - 대부분 도구, 조약돌, 로프, 주머니, 막대만 있고 문자 없음.

## 5. CH3 EP69 다음 작업 순서

### 1. 남은 시트 검수

다음 3개를 먼저 확대 확인.

```powershell
functions.view_image detail:"original" path="C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch3_ep69\ch3_ep69_141_144.png"
functions.view_image detail:"original" path="C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch3_ep69\ch3_ep69_145_148.png"
functions.view_image detail:"original" path="C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch3_ep69\ch3_ep69_149_150.png"
```

### 2. 의심 컷 개별 확대

개별 이미지 경로 예:

```powershell
D:\long_result\CH3\EP.69.260619122724cc71c5\images\cut_002.png
D:\long_result\CH3\EP.69.260619122724cc71c5\images\cut_010.png
D:\long_result\CH3\EP.69.260619122724cc71c5\images\cut_019.png
```

확정/의심 후보 전체:

```text
2, 10, 19, 34, 35, 36, 54, 58, 60, 62, 63, 73, 75, 78, 90, 97, 102, 113, 130
```

### 3. 로직 수정 방향

결과물 직접 수정 금지. 원인은 다음 로직에서 막아야 함.

- 일본 전국시대 건물/마당/복도 장면에서 벽면의 작은 직사각형 플레이트를 더 강하게 금지.
- positive prompt에 `blank plaster wall`, `uninterrupted wood grain`, `no isolated rectangular wall plate` 류를 앞쪽에 배치.
- negative prompt에 다음을 더 구체적으로 보강:
  - `small white switch on wall`
  - `two-button wall plate`
  - `vertical switch plate beside doorway`
  - `tiny wall label`
  - `small hanging tag on post`
  - `paper tag beside door`
  - `marked white object on floor mat`
  - `game token with glyph`
  - `paper with any mark`
- 종이/명령/작전/전령 장면은 작업대 위 `sealed blank packets`, `cord knots`, `plain counters`, `unmarked wooden sticks`만 허용.

### 4. 불량 컷 재생성 절차

원칙:

- 기존 불량 이미지는 삭제하지 말고 `images\qa_rejected_round1`로 이동.
- `.png.prompt.json`도 함께 이동.
- DB에서 해당 컷만 `image_path=None`, `status='pending'`으로 되돌림.
- 해당 컷만 `_step_image` 실행.

기존 참고 스크립트:

- `_tmp_regen_ch1_ep14\regen_step_image.py`
- `_tmp_regen_cut_image_model.py`

새 세션에서는 CH3 EP69용 헬퍼를 새로 만들거나 기존 `_tmp_regen_cut_image_model.py` 사용 가능 여부를 먼저 확인할 것.

### 5. CH3 EP69 이미지 통과 후 영상/업로드

이미지 재검수 통과 후에만 step 5-7 진행.

```powershell
$env:DATA_DIR='C:\Users\Ai_M9\Desktop\longsult'
$env:PYTHONPATH='C:\Users\Ai_M9\Desktop\longtube\backend'
$env:PYTHONUTF8='1'
$out='C:\Users\Ai_M9\Desktop\longtube\_tmp_run_ch3_ep69_step57_stdout.log'
$err='C:\Users\Ai_M9\Desktop\longtube\_tmp_run_ch3_ep69_step57_stderr.log'
$p=Start-Process -FilePath python -ArgumentList '-X','utf8','_tmp_run_pipeline_project.py','V3_CH3_EP69_260619122724cc71c5','5','7' -WorkingDirectory 'C:\Users\Ai_M9\Desktop\longtube' -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden -PassThru
$p.Id | Set-Content -LiteralPath 'C:\Users\Ai_M9\Desktop\longtube\_tmp_run_ch3_ep69_step57.pid'
```

## 6. CH4 EP14 다음 작업

- 프로젝트 ID: `V3_CH4_EP14_260618152448a49657`
- 제목: `The Inventor Strangled by His Own Genius: Thomas M EP.14`
- 결과 폴더: `D:\long_result\CH4\Empire Errors\EP.14.260618152448a49657`
- DB 상태:
  - `status`: `failed`
  - `current_step`: `4`
  - `total_cuts`: `0`
  - step states: `2 failed`, `story completed`, `3 pending`, `4 pending`, `5 pending`, `6 pending`, `7 pending`
  - cut row: `0`
  - image_path: `0`
  - `youtube_url`: `None`
- 모델:
  - image_model: `comfyui-flux2-klein-4b`
  - video_model: `ffmpeg-static`

CH3 EP69 완료 후 CH4 EP14는 바로 full upload로 가지 말고 step 2-4부터 실행해 이미지 150개를 만든 뒤 확대 QA를 먼저 해야 함.

## 7. 작업트리 상태 주의

- `git status --short` 기준으로 많은 수정/미추적 파일이 이미 존재함.
- 이번 이미지 로직 작업에서 직접 건드린 핵심은 아래로 보면 됨.
  - `backend/app/services/image/comfyui_service.py`
  - `backend/tests/test_image_prompt_guards.py`
  - `_tmp_regen_ch1_ep14\*`
  - `_tmp_run_ch3_ep69_step24.*`
  - `_tmp_inspection_ch3_ep69\*`
- 기존 dirty 파일은 사용자/이전 세션 작업일 수 있으므로 절대 임의 revert 금지.

## 8. 다음 세션 첫 명령 추천

```powershell
git status --short
Get-Content -LiteralPath 'C:\Users\Ai_M9\Desktop\longtube\_tmp_run_ch3_ep69_step24_stdout.log' -Tail 30
Get-ChildItem -LiteralPath 'D:\long_result\CH3\EP.69.260619122724cc71c5\images' -File -Filter 'cut_*.png' | Measure-Object
```

DB 확인:

```powershell
$env:DATA_DIR='C:\Users\Ai_M9\Desktop\longsult'
$env:PYTHONPATH='C:\Users\Ai_M9\Desktop\longtube\backend'
$env:PYTHONUTF8='1'
@'
from collections import Counter
from app.models.database import SessionLocal
from app.models.project import Project
from app.models.cut import Cut
pid='V3_CH3_EP69_260619122724cc71c5'
db=SessionLocal()
try:
    p=db.query(Project).filter(Project.id==pid).first()
    rows=db.query(Cut).filter(Cut.project_id==pid).all()
    print(p.status, p.current_step, p.youtube_url)
    print(p.step_states)
    print(len(rows), dict(Counter(r.status for r in rows)), sum(1 for r in rows if r.image_path))
finally:
    db.close()
'@ | python -X utf8 -
```

## 9. 중단 지점

- CH1 EP14는 완료.
- CH3 EP69는 이미지 생성 완료, QA 진행 중.
- 현재 QA는 `ch3_ep69_137_140.png`까지 완료.
- 다음은 `ch3_ep69_141_144.png`부터 확인.
- CH3 문제 후보를 로직 수정 후 재생성하고 통과하면 CH3 영상/업로드.
- 그 다음 CH4 EP14 step 2-4 시작.
