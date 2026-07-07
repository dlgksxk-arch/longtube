# SESSION HANDOFF - 2026-06-15 - CH1 EP12 / image prompt logic

## 0. 기준

- 작업 위치: `C:\Users\Ai_M9\Desktop\longtube`
- 사용자 최신 요청: 새 세션으로 갈 수 있도록 변경사항을 세세하게 기록.
- 기록 원칙: 확인된 사실만 기록. 추측성 판단 금지.
- 중요 운영 원칙:
  - 문제 이미지가 나오면 결과물 직접 보정 금지.
  - 공통 이미지 생성 로직을 수정한 뒤 해당 실패 컷만 재생성.
  - 채널 특화 프롬프트 대체 금지.
  - 시대/배경은 대본 프롬프트에서 읽어 범용 로직으로 반영.

## 1. 현재 완료 상태

### 실행 프로세스

- 확인 명령:
  - `_tmp_run_queue_top_wait`
  - `task_queue`
  - `auto.*render`
  - `_tmp_regen_cut_image_model`
- 위 패턴으로 현재 실행 중인 별도 제작/재생성 프로세스는 없음.
- 확인 시각: `2026-06-15 09:50 KST` 전후.

### CH1 EP12

- 프로젝트 ID: `V3_CH1_EP12_260615062704bdba74`
- 결과 폴더: `D:\long_result\CH1\고구려\EP.12.260615062704bdba74`
- 제목: `영락(永樂)의 시대, 대제국의 팽창 EP.12`
- 이미지 수: `150`
- 최종 본편 파일:
  - `D:\long_result\CH1\고구려\EP.12.260615062704bdba74\output\final_with_subtitles.mp4`
  - 크기: `130,423,176 bytes`
  - 수정 시각: `2026-06-15 09:38:55 KST`
- 병합 파일:
  - `D:\long_result\CH1\고구려\EP.12.260615062704bdba74\output\merged.mp4`
  - 크기: `128,914,991 bytes`
  - 수정 시각: `2026-06-15 09:38:34 KST`
- 업로드 확인:
  - 본편 URL: `https://youtube.com/watch?v=LUfoBkVMCIU`
  - 업로드 완료 시각 기록: `2026-06-15T00:43:19Z`

### CH1 EP12 Shorts 업로드

파일: `D:\long_result\CH1\고구려\EP.12.260615062704bdba74\output\shorts\shorts_uploads.json`

- `short_1.mp4`
  - 제목: `무너진 백제, 판이 뒤집힌 순간 #Shorts #영락 #시대 #대제국`
  - URL: `https://youtube.com/watch?v=zgIF8qBOqC0`
  - Studio verified: `true`
  - Processing verified: `false`
- `short_2.mp4`
  - 제목: `이 장면 하나로 끝났습니다 #Shorts #영락 #시대 #대제국`
  - URL: `https://youtube.com/watch?v=SNtiN6-dc-0`
  - Studio verified: `true`
  - Processing verified: `false`
- `short_3.mp4`
  - 제목: `백제의 마지막 장군, 진짜 반전은 따로 있다 #Shorts #영락 #시대 #대제국`
  - URL: `https://youtube.com/watch?v=YfPldsaAI1w`
  - Studio verified: `true`
  - Processing verified: `false`
- `short_4.mp4`
  - 제목: `나라가 흔들린 선택 하나 #Shorts #영락 #시대 #대제국`
  - URL: `https://youtube.com/watch?v=MFCfE9p4eic`
  - Studio verified: `true`
  - Processing verified: `false`

### 자동 렌더 로그 확인

파일: `D:\long_result\CH1\고구려\EP.12.260615062704bdba74\auto_render.log`

- `auto-render DONE`
- `cuts: 150`
- `opening_used: True`
- `intermission_used: True`
- `intermission_count: 4`
- `ending_used: True`
- Shorts 4개 생성 기록 있음.

## 2. 최우선 주의사항

### 컷 122, 123 최신 이미지가 최종 영상에 반영되지 않았을 가능성이 높음

확인된 시각:

- `videos\cut_122.mp4`: `2026-06-15 09:37:39 KST`
- `images\cut_122.png`: `2026-06-15 09:34:05 KST`
- `videos\cut_123.mp4`: `2026-06-15 09:37:40 KST`
- `images\cut_123.png`: `2026-06-15 09:39:32 KST`
- `output\final_with_subtitles.mp4`: `2026-06-15 09:38:55 KST`

`cut_123.png`는 컷 mp4와 최종 본편 mp4보다 뒤에 수정됨. 따라서 업로드된 본편은 최신 `cut_123.png`를 포함하지 않았을 가능성이 높다.

다음 세션에서 먼저 해야 할 일:

1. 업로드된 본편 또는 로컬 `final_with_subtitles.mp4`에서 컷 123 구간 확인.
2. 문제가 있으면 이미지 전체 재생성 금지.
3. 최신 이미지 기준으로 컷 비디오/최종 영상/업로드 단계만 다시 처리.

## 3. 코드 변경 파일

현재 확인된 주요 수정 파일:

- `backend/app/services/image/comfyui_service.py`
- `backend/app/services/image/prompt_builder.py`

확인 명령:

```powershell
git status --short -- backend/app/services/image/comfyui_service.py backend/app/services/image/prompt_builder.py
git diff --stat -- backend/app/services/image/comfyui_service.py backend/app/services/image/prompt_builder.py
```

확인 결과:

- `backend/app/services/image/comfyui_service.py`: modified
- `backend/app/services/image/prompt_builder.py`: modified
- diff stat:
  - `backend/app/services/image/comfyui_service.py | 18389 +++++++++++++++++++++++-`
  - `backend/app/services/image/prompt_builder.py  | 9617 ++++++++++++-`
  - `2 files changed, 27340 insertions(+), 666 deletions(-)`

검증:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m py_compile backend/app/services/image/comfyui_service.py backend/app/services/image/prompt_builder.py
```

마지막 실행 결과: 통과. 출력 없음.

## 4. `comfyui_service.py` 주요 변경 지점

### 신규/강화된 장면 감지 helper

확인된 라인:

- `_local_scene_requests_bronze_bowl_object`: `backend/app/services/image/comfyui_service.py:3955`
- `_local_scene_requests_shattering_vase_object`: `backend/app/services/image/comfyui_service.py:4016`
- `_local_scene_requests_bowing_humility`: `backend/app/services/image/comfyui_service.py:4385`
- `_local_scene_requests_whispering_into_ear`: `backend/app/services/image/comfyui_service.py:4403`
- `_local_scene_requests_carriage_removal_scene`: `backend/app/services/image/comfyui_service.py:4419`
- `_local_scene_requests_wall_overlooking_river`: `backend/app/services/image/comfyui_service.py:4434`
- `_local_scene_requests_frozen_wasteland_march`: `backend/app/services/image/comfyui_service.py:4445`
- `_local_scene_requests_shattering_vase_object`: `backend/app/services/image/comfyui_service.py:4455`
- `_local_scene_requests_sword_hilt_grip`: `backend/app/services/image/comfyui_service.py:4465`

주의:

- `_local_scene_requests_shattering_vase_object`가 두 번 정의되어 있음.
- Python에서는 뒤쪽 정의가 앞쪽 정의를 덮음.
- 컴파일은 통과했지만, 다음 세션에서 중복 정리 여부를 판단해야 함.
- 현재 요청은 기록이므로 코드 정리는 하지 않았음.

### 신규/강화된 ComfyUI front prompt lock

확인된 라인:

- `MAP_OBJECT_FINAL_TEXTLESS_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:4924`
- `MAP_OBSERVER_STORY_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:4970`
- `HISTORICAL_CLOTHING_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5010`
- `BOWING_HUMILITY_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5071`
- `WHISPERING_EAR_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5098`
- `CARRIAGE_REMOVAL_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5127`
- `WALL_OVERLOOKING_RIVER_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5158`
- `FROZEN_WASTELAND_MARCH_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5180`
- `SHATTERING_VASE_OBJECT_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5199`
- `SWORD_HILT_GRIP_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5216`
- `PREMODERN_INTERIOR_PROP_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5234`
- `BRONZE_BOWL_FINAL_OBJECT_COMFYUI_FRONT_PROMPT`: `backend/app/services/image/comfyui_service.py:5262`

### 최종 프롬프트 승격 단계

확인된 라인:

- 최종 장면 플래그 계산 시작: `backend/app/services/image/comfyui_service.py:18731`
- 주요 final flags:
  - `final_is_map_or_planning_scene`
  - `final_is_map_observer_scene`
  - `final_is_prompt_named_symbol_flag`
  - `final_is_bowing_humility_scene`
  - `final_is_whispering_ear_scene`
  - `final_is_carriage_removal_scene`
  - `final_is_wall_overlooking_river_scene`
  - `final_is_frozen_wasteland_march_scene`
  - `final_is_shattering_vase_scene`
  - `final_is_sword_hilt_grip_scene`
  - `final_is_bronze_bowl_object_scene`
  - `final_needs_historical_clothing`
  - `final_needs_premodern_material_world`
- 최종 prompt lock 승격 시작: `backend/app/services/image/comfyui_service.py:18763`
- 각 lock 승격 확인 라인:
  - historical clothing: `18771`
  - premodern interior/prop: `18777`
  - bronze bowl: `18788`
  - bowing/humility: `18794`
  - whispering ear: `18800`
  - carriage removal: `18806`
  - wall overlooking river: `18812`
  - frozen wasteland march: `18818`
  - shattering vase: `18824`
  - sword hilt grip: `18830`
  - map observer: `18836`
  - map object final textless: `18845`

## 5. 로직별 변경 내용

### 5.1 지도 / 전략판 object-only 로직

목표:

- 대본이 지도/전략판을 요구할 때 현대식 벽지도, 종이 지도, 국가 윤곽선, 빨간 선, 글자/표식을 줄임.
- 사람이 필요 없는 object-only 컷에서 인물이 튀어나오는 문제 억제.

변경:

- `MAP_OBJECT_FINAL_TEXTLESS_COMFYUI_FRONT_PROMPT` 강화.
- `MAP_OBJECT_FINAL_TEXTLESS_COMFYUI_EXTRA_NEGATIVE` 강화.
- `MAP_OBJECT_COMFYUI_FRONT_PROMPT` 강화.
- object-only map branch에서 dark wood/coarse cloth/dark mat/clay/stone, thick braided cords, stones, bronze pins 중심으로 유도.
- no wall map / no framed display / no paper parchment / no country outline / no red route lines / no readable text 강화.

적용 컷:

- `cut_61`

결과:

- 최초 문제: 현대 정장 인물 + 벽지도.
- 최종 확인: 어두운 목재/돌/끈 기반 textless object surface로 수용.

### 5.2 지도 관찰자 / 전략 관찰 장면

목표:

- 사람이 지도를 보는 장면은 살리되, 텍스트/기호/벽지도/현대식 자료판을 억제.

변경:

- `MAP_OBSERVER_STORY_COMFYUI_FRONT_PROMPT` 강화.
- textless tactical surface, gaze/cords/stones로 방향성 표현.
- pseudo-characters, rows/columns marks, labels, paper/parchment map 억제.

적용 컷:

- `cut_89`

결과:

- 최초 문제: 지도에 글자/표식 과다.
- 재생성 후 수용: 인물 + rope/pin board, readable text 없음.

### 5.3 역사 복식 / 현대 정장 억제

목표:

- 고대/중세/전근대 장면에서 현대 양복, 블레이저, 셔츠 칼라, 넥타이, 단추열이 나오는 문제 억제.

변경:

- `HISTORICAL_CLOTHING_COMFYUI_FRONT_PROMPT` 강화.
- `HISTORICAL_CLOTHING_COMFYUI_EXTRA_NEGATIVE` 강화.
- non-modern historical scene에 final promotion 적용.

적용 컷:

- `cut_86`
- `cut_99`
- `cut_100`
- 기타 non-modern historical 컷 전반.

결과:

- `cut_86`: 현대 버튼 재킷 문제 이후 bowing/humility와 함께 재생성, 수용.
- `cut_99`: 현대 실내 조명/스위치/표지판 문제와 함께 개선.
- `cut_100`: 현대 바지/신발 문제 완화.

### 5.4 고개 숙임 / 굴복 / 절박함 감정선

목표:

- 대사/프롬프트가 bowing, lowered head, humility, desperation, pleading, submission, kneeling을 요구할 때 정면 무표정 클로즈업으로 빠지는 문제 억제.

변경:

- `_local_scene_requests_bowing_humility` 추가.
- `BOWING_HUMILITY_COMFYUI_FRONT_PROMPT` 추가.
- `BOWING_HUMILITY_COMFYUI_EXTRA_NEGATIVE` 추가.
- final prompt 단계에서 해당 lock 승격.

적용 컷:

- `cut_86`

결과:

- 최초 문제: 현대식 재킷 인물, bowing 부족.
- 재생성 후 수용: 인물이 고개를 숙인 굴복/절박 장면으로 개선.

### 5.5 귀에 속삭임 장면

목표:

- 대본이 whisper into ear를 요구할 때 단순 정면 인물, 간판/문자/실내 현대 소품으로 흐르는 문제 억제.

변경:

- `_local_scene_requests_whispering_into_ear` 추가.
- 초기 정규식이 `into the Silla king's ear` 형태를 놓쳐 수정.
- `WHISPERING_EAR_COMFYUI_FRONT_PROMPT` 추가.
- `WHISPERING_EAR_COMFYUI_EXTRA_NEGATIVE` 추가.
- exactly two period-correct adults, mouth close to ear, tight crop 중심으로 유도.

적용 컷:

- `cut_99`

결과:

- 최초 문제: readable text, modern lamp, wall switch.
- 2차 문제: whispering 부족.
- 3차 문제: signboard text.
- 최종 확인: 두 인물 귀속말 장면, 텍스트/현대 fixture 없음.

### 5.6 전근대 실내 / 소품 / 문자 억제

목표:

- 전근대 실내 장면에서 전등, 벽 스위치, 콘센트, 현대 문고리, 표지판, 벽패, 글자 패널이 나오는 문제 억제.

변경:

- `PREMODERN_INTERIOR_PROP_COMFYUI_FRONT_PROMPT` 추가.
- `PREMODERN_INTERIOR_PROP_COMFYUI_EXTRA_NEGATIVE` 추가.
- non-modern historical scene에 final promotion 적용.
- light source를 candle/oil lamp/brazier/torch/window/off-frame로 유도.
- blank props/wood/boards, no text/pseudo-writing 강화.

적용 컷:

- `cut_99`
- `cut_101`
- `cut_102`
- 기타 전근대 실내 컷 전반.

결과:

- `cut_99`에서 현대 조명/스위치/표지판 문제가 개선됨.

### 5.7 청동 그릇 object-only

목표:

- 대본이 bronze bowl / inscribed bowl을 요구할 때 사람이 그릇을 들거나 건축물/문/간판으로 변하는 문제 억제.

변경:

- `_local_scene_requests_bronze_bowl_object` 추가.
- 기존 `_local_scene_requests_inscribed_bowl_object` branch 강화.
- `BRONZE_BOWL_FINAL_OBJECT_COMFYUI_FRONT_PROMPT` 추가.
- `BRONZE_BOWL_FINAL_OBJECT_COMFYUI_EXTRA_NEGATIVE` 추가.
- bowl-only, tight object crop, dark cloth/table, patina/dents/grooves 유도.
- no people/hands/architecture/gate/roofline/signage/readable characters 강화.

적용 컷:

- `cut_101`
- `cut_102`

결과:

- `cut_101`: 현대 정장 인물이 그릇 든 문제 -> bowl-only close-up으로 수용.
- `cut_102`: 건축/인물 중심 문제 -> bowl-only close-up으로 수용.

### 5.8 수레/마차 제거 장면

목표:

- 대본이 carriage/cart/wagon/royal removal scene을 요구할 때 정지된 인물 초상, 현대 바지/신발, 사진풍 결과로 흐르는 문제 억제.

변경:

- `_local_scene_requests_carriage_removal_scene` 추가.
- `CARRIAGE_REMOVAL_COMFYUI_FRONT_PROMPT` 추가.
- `CARRIAGE_REMOVAL_COMFYUI_EXTRA_NEGATIVE` 추가.
- visible period wooden carriage/cart/wagon/ox cart, large wheels/axle/shafts, royals looking back sadly 유도.
- 2D adult graphic novel style 강화.
- photo/live-action/sepia 억제.

적용 컷:

- `cut_100`

결과:

- 최초 문제: 수레 없음, 현대 바지/신발.
- 2차 문제: 사진풍.
- 최종 확인: 목재 수레가 보이고 2D 스타일로 개선. 신발/하체 완성도는 완전하다고 단정하지 않음.

### 5.9 높은 성벽에서 강을 내려다보는 장면

목표:

- high wall overlooking river 장면이 성문/간판/마당/건물 입구로 변하는 문제 억제.

변경:

- `_local_scene_requests_wall_overlooking_river` 추가.
- `WALL_OVERLOOKING_RIVER_COMFYUI_FRONT_PROMPT` 추가.
- `WALL_OVERLOOKING_RIVER_COMFYUI_EXTRA_NEGATIVE` 추가.
- wall parapet/rampart + visible river below/beyond 유도.
- gate entrance/courtyard/signboards 억제.

적용 컷:

- `cut_108`

결과:

- 최초 문제: 성문/간판 중심.
- 재생성 후 수용: 성벽 위에서 강이 보이는 구도.

### 5.10 설원 행군 / 혹한 전장

목표:

- frozen wasteland march 장면이 문/신사/사찰/궁궐/torii-like 구조물로 변하는 문제 억제.

변경:

- `_local_scene_requests_frozen_wasteland_march` 추가.
- `FROZEN_WASTELAND_MARCH_COMFYUI_FRONT_PROMPT` 추가.
- `FROZEN_WASTELAND_MARCH_COMFYUI_EXTRA_NEGATIVE` 추가.
- open snowy terrain, army marching, wind/snow/ice, no architecture 유도.

적용 컷:

- `cut_109`

결과:

- 최초 문제: 설원 군대 뒤로 torii/gate/building 류 구조물.
- 재생성 후 수용: 열린 설원 행군 장면.

### 5.11 깨지는 항아리 / 도자기 object-only

목표:

- shattering vase 장면이 건축물/성문/문자/인물로 변하는 문제 억제.

변경:

- `_local_scene_requests_shattering_vase_object` 추가.
- `SHATTERING_VASE_OBJECT_COMFYUI_FRONT_PROMPT` 추가.
- `SHATTERING_VASE_OBJECT_COMFYUI_EXTRA_NEGATIVE` 추가.
- one vessel breaking/shards only 유도.
- buildings/gates/people/text 억제.

적용 컷:

- `cut_122`

결과:

- 최초 문제: 항아리 대신 gate/text 계열.
- 재생성 후 수용: 항아리와 파편 중심.

### 5.12 검자루를 움켜쥐는 손

목표:

- sword hilt grip 장면이 손바닥 펼침/들어올린 손/검자루 누락으로 변하는 문제 억제.

변경:

- `_local_scene_requests_sword_hilt_grip` 추가.
- `SWORD_HILT_GRIP_COMFYUI_FRONT_PROMPT` 추가.
- `SWORD_HILT_GRIP_COMFYUI_EXTRA_NEGATIVE` 추가.
- hand wrapped around hilt, knuckles/closed grip 유도.
- open palm/counting/waving/missing hilt 억제.

적용 컷:

- `cut_123`

결과:

- 최초 문제: 검자루 대신 손을 들어 보이는 장면.
- 재생성 후 수용: 손이 검자루를 움켜쥔 장면.
- 단, 최신 `cut_123.png`가 최종 영상보다 늦게 저장되어 본편 반영 여부는 미확정.

### 5.13 기존 유지된 중요 로직

이 세션 이전 변경이지만 현재 파일에 남아 있고 CH1 EP12 작업에 영향 있음:

- 손 해부학 lock:
  - `HAND_ANATOMY_COMFYUI_FRONT_PROMPT`
  - `HAND_ANATOMY_COMFYUI_EXTRA_NEGATIVE`
- 이름 있는 상징 깃발 / 삼족오 로직:
  - `_local_scene_requests_prompt_named_symbol_flag`
  - `PROMPT_NAMED_SYMBOL_FLAG_COMFYUI_FRONT_PROMPT`
  - `PROMPT_NAMED_SYMBOL_FLAG_COMFYUI_EXTRA_NEGATIVE`
  - 명시적 named symbol flag에서 blank banner lock 비활성.
- 단일 인물 눈 클로즈업 로직:
  - `_local_scene_requests_single_person_eye_closeup`
- map false detection 방지:
  - `_local_scene_requests_map`에서 `no map` 같은 negative phrase 처리.
- map sanitizer 보호:
  - `_sanitize_comfyui_positive_text_triggers`에서 map lock이 있을 때 map을 다른 route surface로 치환하지 않음.

## 6. `prompt_builder.py` 변경 확인 사항

확인된 변경/잔존 지점:

- `backend/app/services/image/prompt_builder.py:5549`
  - `smooth round gold or bronze authority ornament, plain spherical ritual object held or indicated by period-local hands, no cartographic surface, no latitude-longitude grid, no meridian rings, no armillary rings, no astronomical stand, no writing`
- `backend/app/services/image/prompt_builder.py:5555`
  - round brass-and-wood cosmological globe / armillary sphere fallback 문구 존재.
- `backend/app/services/image/prompt_builder.py:5561`
  - round brass-and-wood cosmological globe / armillary sphere 문구 존재.

주의:

- 이전 요약 기준으로 `globe-like ornament` 계열 오인식을 줄이기 위한 수정이 있었음.
- 현재 파일에는 armillary/globe 관련 문구가 다른 문맥에도 여러 곳 남아 있음.
- 이 기록에서는 추가 수정하지 않았음.

## 7. CH1 EP12 이미지 QA / 재생성 로그

### 이전 세션에서 이미 처리된 범위

- `cut_1` ~ `cut_56`: 이전 세션에서 다수 QA/재생성 처리된 것으로 요약되어 있었음.
- 주요 주제: 손 해부학, 지도, single-eye close-up, named flag, globe-like ornament.
- 본 문서에서는 현재 세션에서 직접 확인한 구간 위주로 기록.

### 현재 세션에서 확인/처리한 컷

- `cut_61`
  - 문제: 현대 정장 인물 + 벽지도.
  - 처리: map object-only 로직 강화 후 해당 컷 재생성.
  - 최종: textless rope/stone tactical surface로 수용.
- `cut_82`, `cut_83`, `cut_84`
  - 확인: 수용.
- `cut_86`
  - 문제: 현대 버튼 재킷, bowing/humility 부족.
  - 처리: historical clothing + bowing/humility 로직 강화 후 해당 컷 재생성.
  - 최종: 고개 숙임/굴복 감정 장면으로 수용.
- `cut_89`
  - 문제: map text / pseudo label.
  - 처리: map observer 로직 강화 후 해당 컷 재생성.
  - 최종: textless observer tactical surface로 수용.
- `cut_99`
  - 문제 1: readable text, modern lamp, wall switch.
  - 문제 2: whispering into ear 표현 부족.
  - 문제 3: signboard text.
  - 처리: premodern interior/prop lock + whispering ear regex/prompt 강화 후 해당 컷 재생성.
  - 최종: 두 인물 귀속말, 텍스트/현대 fixture 없음.
- `cut_100`
  - 문제 1: 수레 없음, 현대 바지/신발.
  - 문제 2: 사진풍.
  - 처리: carriage removal 로직 + 2D adult graphic novel style 강화 후 해당 컷 재생성.
  - 최종: period wooden carriage가 보이는 2D 스타일로 수용. 신발/하체 완성도는 완전하다고 단정하지 않음.
- `cut_101`
  - 문제: 현대 정장 인물이 bowl을 들고 있음.
  - 처리: bronze bowl object-only 로직 강화 후 해당 컷 재생성.
  - 최종: bowl-only close-up으로 수용.
- `cut_102`
  - 문제: 건축/인물 중심, bowl 부족.
  - 처리: bronze bowl final object lock 강화 후 해당 컷 재생성.
  - 최종: bowl-only close-up으로 수용.
- `cut_108`
  - 문제: high wall/river 대신 gate/sign 중심.
  - 처리: wall overlooking river 로직 추가 후 해당 컷 재생성.
  - 최종: 성벽과 강 구도로 수용.
- `cut_109`
  - 문제: 설원 군대 뒤에 torii/gate/building 구조.
  - 처리: frozen wasteland march 로직 추가 후 해당 컷 재생성.
  - 최종: 열린 설원 행군으로 수용.
- `cut_122`
  - 문제: 깨지는 항아리 대신 gate/text 계열.
  - 처리: shattering vase object-only 로직 추가 후 해당 컷 재생성.
  - 최종: 항아리/파편 중심으로 수용.
- `cut_123`
  - 문제: 검자루를 움켜쥐는 장면 대신 손을 들어 보이는 장면.
  - 처리: sword hilt grip 로직 추가 후 해당 컷 재생성.
  - 최종: 손이 검자루를 잡은 장면으로 수용.
  - 주의: 최신 이미지 저장 시각이 최종 영상 생성 시각보다 늦음.

### 미확인 또는 제한 확인 범위

- `cut_126` ~ `cut_150`: 파일 생성은 확인됨.
- 이 세션에서 각 이미지를 수동으로 전부 시각 확인했다고 말할 수 없음.
- 다음 세션에서 본편 유지/재업로드 판단 전에 `126-150` contact sheet 확인 권장.

## 8. CH1 EP12 주요 파일 타임스탬프

이미지:

- `cut_121.png`: `2026-06-15 09:25:58 KST`
- `cut_122.png`: `2026-06-15 09:34:05 KST`
- `cut_123.png`: `2026-06-15 09:39:32 KST`
- `cut_124.png`: `2026-06-15 09:26:42 KST`
- `cut_125.png`: `2026-06-15 09:27:01 KST`
- `cut_126.png`: `2026-06-15 09:27:44 KST`
- `cut_127.png`: `2026-06-15 09:28:02 KST`
- `cut_128.png`: `2026-06-15 09:28:20 KST`
- `cut_129.png`: `2026-06-15 09:28:40 KST`
- `cut_130.png`: `2026-06-15 09:29:11 KST`
- `cut_131.png`: `2026-06-15 09:29:28 KST`
- `cut_132.png`: `2026-06-15 09:29:46 KST`
- `cut_133.png`: `2026-06-15 09:30:30 KST`
- `cut_134.png`: `2026-06-15 09:30:49 KST`
- `cut_135.png`: `2026-06-15 09:31:09 KST`
- `cut_136.png`: `2026-06-15 09:31:29 KST`
- `cut_137.png`: `2026-06-15 09:31:39 KST`
- `cut_138.png`: `2026-06-15 09:31:59 KST`
- `cut_139.png`: `2026-06-15 09:32:19 KST`
- `cut_140.png`: `2026-06-15 09:32:39 KST`
- `cut_141.png`: `2026-06-15 09:32:51 KST`
- `cut_142.png`: `2026-06-15 09:33:09 KST`
- `cut_143.png`: `2026-06-15 09:33:26 KST`
- `cut_144.png`: `2026-06-15 09:33:38 KST`
- `cut_145.png`: `2026-06-15 09:33:49 KST`
- `cut_146.png`: `2026-06-15 09:34:35 KST`
- `cut_147.png`: `2026-06-15 09:35:02 KST`
- `cut_148.png`: `2026-06-15 09:35:21 KST`
- `cut_149.png`: `2026-06-15 09:35:54 KST`
- `cut_150.png`: `2026-06-15 09:36:10 KST`

컷 mp4:

- `cut_121.mp4`: `2026-06-15 09:37:39 KST`
- `cut_122.mp4`: `2026-06-15 09:37:39 KST`
- `cut_123.mp4`: `2026-06-15 09:37:40 KST`
- `cut_124.mp4`: `2026-06-15 09:37:40 KST`
- `cut_125.mp4`: `2026-06-15 09:37:42 KST`
- `cut_126.mp4`: `2026-06-15 09:37:42 KST`
- `cut_127.mp4`: `2026-06-15 09:37:43 KST`
- `cut_128.mp4`: `2026-06-15 09:37:43 KST`
- `cut_129.mp4`: `2026-06-15 09:37:45 KST`
- `cut_130.mp4`: `2026-06-15 09:37:45 KST`
- `cut_131.mp4`: `2026-06-15 09:37:46 KST`
- `cut_132.mp4`: `2026-06-15 09:37:46 KST`
- `cut_133.mp4`: `2026-06-15 09:37:48 KST`
- `cut_134.mp4`: `2026-06-15 09:37:48 KST`
- `cut_135.mp4`: `2026-06-15 09:37:48 KST`
- `cut_136.mp4`: `2026-06-15 09:37:49 KST`
- `cut_137.mp4`: `2026-06-15 09:37:51 KST`
- `cut_138.mp4`: `2026-06-15 09:37:51 KST`
- `cut_139.mp4`: `2026-06-15 09:37:51 KST`
- `cut_140.mp4`: `2026-06-15 09:37:52 KST`
- `cut_141.mp4`: `2026-06-15 09:37:54 KST`
- `cut_142.mp4`: `2026-06-15 09:37:54 KST`
- `cut_143.mp4`: `2026-06-15 09:37:54 KST`
- `cut_144.mp4`: `2026-06-15 09:37:55 KST`
- `cut_145.mp4`: `2026-06-15 09:37:57 KST`
- `cut_146.mp4`: `2026-06-15 09:37:57 KST`
- `cut_147.mp4`: `2026-06-15 09:37:57 KST`
- `cut_148.mp4`: `2026-06-15 09:37:58 KST`
- `cut_149.mp4`: `2026-06-15 09:37:58 KST`
- `cut_150.mp4`: `2026-06-15 09:37:59 KST`

## 9. 실행/확인 명령

컴파일 확인:

```powershell
$env:PYTHONIOENCODING='utf-8'
python -m py_compile backend/app/services/image/comfyui_service.py backend/app/services/image/prompt_builder.py
```

프로젝트 산출물 확인:

```powershell
$project='D:\long_result\CH1\고구려\EP.12.260615062704bdba74'
Get-ChildItem -LiteralPath "$project\output" -File | Select-Object Name,Length,LastWriteTime
Get-ChildItem -LiteralPath "$project\output\shorts" -File | Select-Object Name,Length,LastWriteTime
Get-Content -LiteralPath "$project\output\shorts\shorts_uploads.json" -Raw
Get-Content -LiteralPath "$project\auto_render.log" -Tail 80
```

이미지/컷 비디오 타임스탬프 비교:

```powershell
$project='D:\long_result\CH1\고구려\EP.12.260615062704bdba74'
Get-ChildItem -LiteralPath "$project\images" -Filter 'cut_*.png' |
  ForEach-Object {
    if ($_.Name -match 'cut_(\d+)\.png') {
      [PSCustomObject]@{ Cut=[int]$matches[1]; Name=$_.Name; Length=$_.Length; LastWriteTime=$_.LastWriteTime }
    }
  } | Sort-Object Cut | Select-Object -Last 30

Get-ChildItem -LiteralPath "$project\videos" -Filter 'cut_*.mp4' |
  ForEach-Object {
    if ($_.Name -match 'cut_(\d+)\.mp4') {
      [PSCustomObject]@{ Cut=[int]$matches[1]; Name=$_.Name; Length=$_.Length; LastWriteTime=$_.LastWriteTime }
    }
  } | Sort-Object Cut | Select-Object -Last 30
```

실패 컷만 재생성할 때 사용했던 스크립트:

```powershell
python _tmp_regen_cut_image_model.py V3_CH1_EP12_260615062704bdba74 <CUT_NO> <MODEL_NAME>
```

주의:

- 전체 이미지 재생성 금지.
- 해당 실패 컷만 재생성.
- 로직 수정 후 재생성.

## 10. 다음 세션 우선순위

1. CH1 EP12 업로드 본편을 그대로 둘지 판단.
   - 이유: `cut_123.png`가 최종 mp4보다 늦게 수정됨.
   - 확인 대상: 검자루 움켜쥐는 컷이 본편에 반영되었는지.
2. `cut_126` ~ `cut_150` 수동 이미지 QA.
   - 이 세션에서 전부 눈으로 확인했다고 말할 수 없음.
3. 문제가 있으면 결과물 직접 보정 금지.
   - 공통 로직 수정.
   - 해당 컷만 재생성.
   - 필요한 경우 컷 비디오/최종 영상/업로드 단계만 재처리.
4. 다음 제작 큐로 이동.
   - 이전 대화 흐름상 채널 1/3/4 다음 에피소드 진행 요청이 있었음.
   - 이 문서에서는 다음 정확한 큐 ID를 확인하지 못했으므로 새 세션에서 실제 작업대/큐를 먼저 확인해야 함.
5. CH3 쪽은 이전 요약 기준 OpenAI `429 insufficient_quota` 이슈가 있었음.
   - 새 세션에서 실제 API/작업큐 상태 재확인 필요.

## 11. 금지 사항

- 이미지 결과물을 직접 포토샵식 수정하지 말 것.
- 실패했다고 전체 이미지를 다시 생성하지 말 것.
- 채널 1/3/4에만 맞춘 특화 프롬프트를 넣지 말 것.
- 대본 시대/국가/문화와 무관한 고정 복식/고정 배경을 넣지 말 것.
- 확인되지 않은 큐 상태를 완료/실패로 단정하지 말 것.
- 사용자 허락 없이 중요 기능 수정/대규모 정리 작업을 진행하지 말 것.
