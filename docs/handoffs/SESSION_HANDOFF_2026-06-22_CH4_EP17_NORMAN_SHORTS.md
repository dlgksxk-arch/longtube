# 새 세션 인수인계 - 2026-06-22 CH4 EP17 / Norman 이미지 QA / Shorts 렌더 수정

## 1. 현재 상태

- 작업 위치: `C:\Users\Ai_M9\Desktop\longtube`
- 현재 서버: `http://127.0.0.1:8000`
- 확인된 서버 PID: `21692`
- PowerShell 기준 확인 명령:
  - `Get-NetTCPConnection -LocalPort 8000 -State Listen`
- 현재 작업은 CH4 EP17 완료 및 업로드까지 진행됨.
- 워크트리에는 기존 변경이 다수 있을 수 있음. 이번 세션에서 직접 확인/수정한 범위 외 파일은 되돌리지 말 것.

## 2. 완료된 작업

### CH4 EP17

- 채널: CH4
- 시리즈: `Empire Errors`
- 에피소드: `EP.17`
- task_id: `acfd4549`
- project_id: `V3_CH4_EP17_2606220806185e5723`
- 결과 폴더: `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723`
- 주제: `The Explosive Conqueror: The Bizarre Death of William I`
- 제목: `The Explosive Conqueror: The Bizarre Death of Will EP.17`
- 상태: `completed`
- 완료 step_states:
  - `2`: completed
  - `3`: completed
  - `4`: completed
  - `5`: completed
  - `6`: completed
  - `7`: completed
- 사용 모델:
  - script/story: `gpt-5.5`
  - image: `comfyui-flux2-klein-4b`
  - thumbnail: `comfyui-dreamshaper-xl-longtube`
  - tts: `elevenlabs`
  - video: `ffmpeg-static`

## 3. 업로드 결과

### Main

- YouTube URL: `https://youtube.com/watch?v=8JjBqmMhzYE`

### Shorts

- Short 1: `https://youtube.com/watch?v=EHPIXtBVv-s`
- Short 2: `https://youtube.com/watch?v=HZe3YQElnMY`
- Short 3: `https://youtube.com/watch?v=3Dxel8d6zfc`
- Short 4: `https://youtube.com/watch?v=w8AxHwmuO3k`

### 업로드 메타 확인

- 파일: `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\shorts_uploads.json`
- 확인된 상태:
  - `studio_verified`: `true`
  - `processing_verified`: `false`
  - 위 상태는 모든 shorts에 동일하게 확인됨.

## 4. 최종 산출물 검증

- Main video:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\final_with_subtitles.mp4`
  - ffmpeg 검증 rc: `0`
- Shorts:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\short_1.mp4`
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\short_2.mp4`
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\short_3.mp4`
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\short_4.mp4`
  - ffmpeg 검증 rc: 모두 `0`
- Shorts manifest:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts\shorts.json`
  - results count: `4`

## 5. 이미지 QA 및 재생성 내역

### 최초 문제 컷

- Cut 36:
  - 문 위/주변에 `ROUEN`, `MANTES`처럼 읽히는 장소 표식 위험.
- Cut 79:
  - 문 위 sign 또는 읽히는 텍스트 위험.
- Cut 108:
  - 거대한 얼굴, 병사 눈 속 장면 같은 초현실 오버레이 위험.
- Cut 134:
  - 펼쳐진 양피지에 글자/낙서처럼 보이는 표면 위험.
- Cut 139:
  - 벽 스위치 같은 판/액자/종이 글자 위험.

### 1차 로직 수정 및 재생성

- 수정 파일:
  - `backend/app/services/image/comfyui_service.py`
- 내용:
  - Anglo-Norman / William I / 1087 맥락 감지 추가.
  - CH4 EP17 William I 장면이 기존 high-medieval crusading 기본 맥락으로 떨어지지 않도록 분기 추가.
- 재생성 컷:
  - `36`, `79`, `108`, `134`, `139`
- 결과:
  - open paper / writing 위험과 helmeted monk 문제가 일부 남아 추가 수정 필요했음.

### 2차 로직 수정 및 재생성

- 수정 내용:
  - 수도원/수도사 맥락을 갑옷/헬멧 맥락에서 분리.
  - corridor/material context에서 paper/parchment trigger 제거.
  - workbench prompt를 열린 기록물이 아닌 닫힌 leather record packets, tied cylindrical roll ends, wax, cords, cross, lamp 중심으로 변경.
  - corridor prompt에서 side table/work surface 위험 제거.
- 재생성 컷:
  - `36`, `79`, `108`, `134`, `139`
- 결과:
  - `36`, `108`, `134`, `139` 통과.
  - `79`는 흰 외곽 border 문제가 남음.

### 3차 로직 수정 및 재생성

- 수정 내용:
  - corridor prompt에 full-bleed edge-to-edge 조건 추가.
  - Anglo-Norman negative prompt에 white/black/rounded/postcard border, margin, image matting 관련 금지 추가.
- 재생성 컷:
  - `79`
- 결과:
  - `79` 통과.

### QA 백업 폴더

- `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\qa_rejected_ep17_cuts_36_79_108_134_139_20260622_085118`
- `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\qa_rejected_ep17_cuts_36_79_108_134_139_round2_20260622_085627`
- `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\qa_rejected_ep17_cut_79_round3_20260622_090159`

### QA 시트

- `C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch4_ep17\ch4_ep17_regen_36_79_108_134_139.jpg`
- `C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch4_ep17\ch4_ep17_regen_round2_36_79_108_134_139.jpg`
- `C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch4_ep17\ch4_ep17_final_regen_36_79_108_134_139.jpg`

## 6. 수정된 코드 범위

### `backend/app/services/image/comfyui_service.py`

이번 세션에서 확인한 주요 추가/수정 지점:

- `_flux2_klein_is_anglo_norman_william_context`
  - 현재 확인 line: `2971`
- `_flux2_klein_anglo_norman_scene_text`
  - 현재 확인 line: `3003`
- `_flux2_klein_anglo_norman_text_surface_risk`
  - 현재 확인 line: `3015`
- `_flux2_klein_anglo_norman_doorway_risk`
  - 현재 확인 line: `3031`
- `_flux2_klein_anglo_norman_context_front`
  - 현재 확인 line: `3042`
- `_flux2_klein_anglo_norman_monastic_context_front`
  - 현재 확인 line: `3055`
- `_flux2_klein_anglo_norman_textless_front`
  - 현재 확인 line: `3066`
- `_flux2_klein_anglo_norman_corridor_textless_front`
  - 현재 확인 line: `3081`
- `_flux2_klein_anglo_norman_safe_action_text`
  - 현재 확인 line: `3092`
- `_flux2_klein_anglo_norman_workbench_prompt`
  - 현재 확인 line: `3110`
- `_flux2_klein_anglo_norman_corridor_prompt`
  - 현재 확인 line: `3148`
- `_flux2_klein_anglo_norman_negative`
  - 현재 확인 line: `3174`
- `_sanitize_flux2_klein_anglo_norman_positive_final`
  - 현재 확인 line: `3201`

`_compact_flux2_klein_4b_prompt` 안의 주요 통합 지점:

- `is_anglo_norman_william_source` 설정:
  - 현재 확인 line: `14478`
- high-medieval crusading normalization에서 Anglo-Norman 제외:
  - 현재 확인 line: `14502`
- monastic workbench / corridor direct branch:
  - 현재 확인 line: `14537` 이후
- generic Anglo-Norman compact rewrite:
  - 현재 확인 line: `14582` 이후
- context/textless/sanitize/negative append:
  - 현재 확인 line: `14931`, `15017`, `16407`, `16429`

수정 목적:

- 1087 Anglo-Norman / William I 장면이 `1190 AD high-medieval Holy Roman/German/Latin crusading/Anatolian/Byzantine/Seljuk` 기본 맥락으로 변환되는 문제 방지.
- 문 위 표식, 읽히는 글자, 열린 기록물, 헬멧 쓴 수도사, 흰 테두리 문제 방지.
- 생성된 이미지 자체를 직접 편집하지 않고, 프롬프트 로직 수정 후 재생성하는 방식으로 처리.

### `backend/tests/test_image_prompt_guards.py`

추가된 테스트:

- `test_flux2_klein_anglo_norman_context_avoids_crusade_context`
  - 현재 확인 line: `5401`
- `test_flux2_klein_anglo_norman_doorway_blocks_place_signs`
  - 현재 확인 line: `5420`
- `test_flux2_klein_anglo_norman_chronicler_reflection_avoids_face_overlay`
  - 현재 확인 line: `5444`
- `test_flux2_klein_anglo_norman_writing_uses_closed_parchment`
  - 현재 확인 line: `5464`

테스트 목적:

- Anglo-Norman 장면이 Crusade/Byzantine/Seljuk/Anatolian/Holy Roman 맥락으로 오염되지 않는지 확인.
- doorway prompt에서 place sign / label 위험이 제거되는지 확인.
- chronicler/reflection 계열에서 face overlay / surreal eye scene 위험이 제거되는지 확인.
- writing/parchment 계열에서 open written parchment 대신 closed record packet 계열로 전환되는지 확인.

### `backend/app/services/shorts_service.py`

수정 내용:

- `_validate_rendered_video`에서 ffmpeg return code가 `0`이어도 stderr에 decode error가 있으면 실패 처리하도록 변경.
- 확인된 핵심 지점:
  - `decode_error = re.search(...)`
    - 현재 확인 line: `113`
  - `if proc.returncode != 0 or decode_error:`
    - 현재 확인 line: `120`
- `render_shorts_from_final`에서 cut concat 결과 검증 실패 시 timeline trim으로 fallback하도록 변경.
- 확인된 fallback 로그:
  - `[shorts] cut concat fallback to timeline trim for short_{idx}: ...`
  - 현재 확인 line: `1218`

수정 이유:

- CH4 EP17 shorts 생성 중 `_cut_concat_short_1.mp4`에 decode error가 있었지만 ffmpeg rc가 `0`이라 기존 검증을 통과함.
- 그 결과 최종 `short_1.mp4`가 `moov atom not found` 상태로 깨졌음.
- 검증 로직을 강화하고, cut concat 실패 시 final video timeline 기반 trim으로 fallback하게 수정함.

### `backend/tests/test_oneclick_stability.py`

- 이번 세션에서 코드 수정한 파일은 아님.
- shorts 관련 기존 테스트를 선택 실행하여 통과 확인함.

## 7. 실행한 검증

### Python compile

- `python -m py_compile backend\app\services\image\comfyui_service.py backend\tests\test_image_prompt_guards.py`
  - 결과: 통과
- `python -m py_compile backend\app\services\shorts_service.py`
  - 결과: 통과

### 이미지 프롬프트 가드 테스트

실행 명령:

```powershell
python -m unittest backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_anglo_norman_context_avoids_crusade_context backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_anglo_norman_doorway_blocks_place_signs backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_anglo_norman_chronicler_reflection_avoids_face_overlay backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_anglo_norman_writing_uses_closed_parchment
```

- 결과: 통과

추가로 기존 Anglo-Saxon 테스트와 신규 Anglo-Norman 테스트를 함께 실행했고 통과 확인:

- `test_flux2_klein_anglo_saxon_scene_avoids_crusade_context`
- `test_flux2_klein_anglo_saxon_map_becomes_object_workbench`
- `test_flux2_klein_anglo_saxon_riverside_meeting_blocks_signboard`
- 신규 Anglo-Norman 테스트 4개

주의:

- `ImagePromptGuardTests` 전체 클래스는 기존 dirty worktree 기반 실패가 다수 있을 수 있음.
- 이번 세션 성공 기준으로 전체 클래스 통과를 주장하면 안 됨.

### Shorts 안정성 테스트

초기에는 잘못된 클래스명 `OneClickStabilityTests`로 실행하여 실패했음.

실제 클래스명 확인 후 아래 명령으로 재실행:

```powershell
python -m unittest backend.tests.test_oneclick_stability.ShortsStabilityTests.test_shorts_keeps_marked_cut_clip_speed backend.tests.test_oneclick_stability.ShortsStabilityTests.test_shorts_channel_name_position_matches_ten_minute_history_layout backend.tests.test_oneclick_stability.ShortsStabilityTests.test_annotate_script_shorts_keeps_four_fifteen_cut_groups backend.tests.test_oneclick_stability.ShortsStabilityTests.test_shorts_renderer_does_not_slice_segments_to_one
```

- 결과: 통과

## 8. 재시작/서버 관련 참고

- 현재 서버는 `http://127.0.0.1:8000`에서 listen 중으로 확인됨.
- 확인된 PID는 `21692`.
- 새 세션에서 서버 상태를 먼저 확인할 것:

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen
```

- 서버가 죽어 있으면 기존 프로젝트의 서버 실행 방식과 로그를 확인한 뒤 실행할 것.
- 이미 8000 포트가 사용 중이면 동일 포트 중복 실행하지 말 것.

## 9. 다음 세션에서 주의할 점

- 이미지 결과물에 문제가 있으면 이미지 파일 자체를 직접 수정하지 말 것.
- 문제를 만든 프롬프트/로직을 수정하고 재생성할 것.
- 저장된 이미지 프롬프트 관련 MD와 기존 로직을 먼저 읽고 진행할 것.
- CH3는 사용자가 `gpt-5.5`로 대본 생성한다고 명시했음.
- 현재 사용자는 CH1, CH3, CH4 다음 에피소드까지 연속 진행 지시를 한 상태였음.
- 그러나 이번 인수인계 파일은 CH4 EP17 완료 및 관련 수정 내역 중심임.
- 다음 에피소드 진행 전에는 현재 task 상태와 업로드 상태를 실제 파일/API로 다시 확인할 것.
- 확인되지 않은 내용을 추측해서 답하지 말 것.
- 중요한 기능 수정은 사용자 허락 없이 임의 확장하지 말 것.

## 10. 중요 경로 모음

- 작업 루트:
  - `C:\Users\Ai_M9\Desktop\longtube`
- CH4 EP17 결과:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723`
- Main video:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\final_with_subtitles.mp4`
- Shorts folder:
  - `D:\long_result\CH4\Empire Errors\EP.17.2606220806185e5723\output\shorts`
- QA inspection temp:
  - `C:\Users\Ai_M9\Desktop\longtube\_tmp_inspection_ch4_ep17`
- Image prompt service:
  - `C:\Users\Ai_M9\Desktop\longtube\backend\app\services\image\comfyui_service.py`
- Shorts service:
  - `C:\Users\Ai_M9\Desktop\longtube\backend\app\services\shorts_service.py`
- Image prompt tests:
  - `C:\Users\Ai_M9\Desktop\longtube\backend\tests\test_image_prompt_guards.py`
- Shorts stability tests:
  - `C:\Users\Ai_M9\Desktop\longtube\backend\tests\test_oneclick_stability.py`

