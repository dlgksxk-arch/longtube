# Session Handoff 2026-07-14 - CH1 EP30 Image QA Continue

- 저장 시각: 2026-07-14 12:26:38 +09:00
- 목적: 새 세션에서 CH1 EP30 이미지 검수와 로직 교정을 정확히 이어가기 위한 상태 원장
- 이 문서는 실제 DB, 파일시스템, ComfyUI 큐, 테스트 결과를 다시 조회해 작성함

## 절대 작업 규칙

1. 생성 이미지 자체를 직접 보정하지 않는다.
2. 실패 원인을 생성 로직에서 수정하고 해당 컷을 재생성한다.
3. 일회성 장면 문제도 원본 출력 수정이 아니라 프롬프트 생성 로직과 계약을 수정한다.
4. 모든 생성 이미지는 원본 크기로 한 장씩 확인한다.
5. 인체, 손가락, 손, 팔, 다리, 목, 머리 수, 신체 연결, 동물 해부학을 확인한다.
6. 복식, 무기, 건축, 오브젝트의 시대 고증과 대사 연계를 확인한다.
7. 성인용 굵은 선의 스타일리시한 카툰 이미지, 감정선과 액션이 드러나는 방향을 유지한다.
8. 한 에피소드 전체 제작 시간은 3시간을 넘기지 않는다.
9. EP30은 기존 139컷을 그대로 사용한다. 대본을 새 모델로 다시 생성하거나 컷 수를 늘리지 않는다.
10. 썸네일은 기존 썸네일 프롬프트 파이프라인을 사용한다. 임의 프롬프트로 우회하지 않는다.
11. 다른 컴퓨터의 ComfyUI 작업을 중지, 삭제, 큐 초기화하지 않는다.
12. cut 60은 현재 확정 통과본이다. 다시 이동하거나 재생성하지 않는다.

## 활성 프로젝트

- 채널: CH1
- 시리즈: 고구려
- 에피소드: EP30
- 작업 식별자: 8ec5181a
- 프로젝트 ID: V3_CH1_EP30_260713155401150579
- 프로젝트 DB 상태: draft
- 프로젝트 DB current_step: 2
- 프로젝트 DB total_cuts: 139
- 프로젝트 DB youtube_url: None
- 프로젝트 DB api_cost: 0.0
- 결과 루트: D:\long_result\CH1\고구려\EP.30.260713155401150579
- 이미지 폴더: D:\long_result\CH1\고구려\EP.30.260713155401150579\images
- 원본 대본: C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts\고구려-EP30_script.json
- 프로젝트 대본 복사본: D:\long_result\CH1\고구려\EP.30.260713155401150579\script.json
- 재생성 실행기: C:\Users\Ai_M9\Desktop\longtube\_regen_project_cuts.py
- 이미지 모델: comfyui-flux2-klein-4b
- ComfyUI: http://127.0.0.1:8188
- Python: C:\Users\Ai_M9\AppData\Local\Programs\Python\Python313\python.exe

## 저장 시점 실제 상태

- ComfyUI queue_running: 0
- ComfyUI queue_pending: 0
- 실제 images 폴더의 cut_N.png: 94개
- 실제 누락 컷: 45개
- videos 폴더 파일: 0개
- 로컬 output에는 thumbnail_bg.png, thumbnail.png와 각 QA JSON만 존재한다.
- 최종 영상은 아직 생성되지 않았다.
- YouTube URL은 DB에 없다.

DB와 파일시스템은 현재 동기화되어 있지 않다.

- DB cuts 행: 139개
- DB cuts status: completed 139개
- DB image_model: comfyui-flux2-klein-4b 139개
- DB video_path 존재: 0개
- 실제 이미지가 없는 컷도 DB status가 completed로 남아 있다.
- cut 111과 cut 127은 DB image_path 자체가 None이다.
- 다음 세션은 DB status만 보고 이미지 완료로 판단하면 안 된다.

## 실제 확정 잔존 이미지 94개

1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 79, 83, 87, 88, 92, 93, 95, 97, 103, 105, 107, 109, 114, 126, 131, 132, 138

### 원본 확정 통과 52개

1, 2, 3, 6, 7, 8, 11, 12, 17, 19, 20, 21, 22, 23, 26, 29, 34, 38, 40, 43, 45, 49, 50, 52, 53, 55, 57, 65, 67, 68, 72, 73, 75, 76, 77, 79, 83, 87, 88, 92, 93, 95, 97, 103, 105, 107, 109, 114, 126, 131, 132, 138

### 로직 수정 후 재생성·확정 통과 42개

4, 5, 9, 10, 13, 14, 15, 16, 18, 24, 25, 27, 28, 30, 31, 32, 33, 35, 36, 37, 39, 41, 42, 44, 46, 47, 48, 51, 54, 56, 58, 59, 60, 61, 62, 63, 64, 66, 69, 70, 71, 74

## 실제 미완료 45개

78, 80, 81, 82, 84, 85, 86, 89, 90, 91, 94, 96, 98, 99, 100, 101, 102, 104, 106, 108, 110, 111, 112, 113, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 127, 128, 129, 130, 133, 134, 135, 136, 137, 139

이 목록은 1부터 139까지와 실제 images 폴더를 대조해 산출했다.

## 마지막 확정 검수 결과

- cut 66: 통과. 마른 붉은 흙 위에 뒤집힌 납작한 인장 1개와 정렬된 띠 조각 2개. 문자, 인물, 철사, 하늘 없음.
- cut 69: 통과. 끊어지지 않은 석축·판축 외벽 뒤에서 보이지 않는 내부 화재와 연기. 건물, 인물, 문자 없음.
- cut 70: 통과. 갈라진 거대한 성문 들보 1개와 뒤집힌 무문 청동 인장 정확히 2개. 인물과 문자 없음.
- cut 71: 통과. 닫힌 단일 지휘 인장 1개와 끝이 정확히 2개인 곧은 어두운 띠 1개. 매듭, 목간, 문자 없음.
- cut 74: 통과. 무유 토기 1개 내부의 검푸른 부패와 뭉친 상한 조. 인물과 문자 없음.
- cut 61: 통과. 눈을 완전히 감은 남생의 얼굴, 손 0개, 어두운 비단, 방과 문자 없음.
- cut 51, 54, 56, 58, 59, 60, 62, 63, 64도 원본 크기 검수 후 통과 상태다.

## 중단된 다음 검수 묶음

다음 묶음은 cut 78, 80, 81, 82, 84다.

모든 기존 원본은 아래 보관 폴더에 존재한다.

D:\long_result\CH1\고구려\EP.30.260713155401150579\qa_rejected\20260713_prompt_logic_v2

### cut 78

- 대사: 압도적인 무력을 가졌어도, 내부가 곪아 터진 제국은 멸망합니다.
- 원본 Scene: A flawless, sharp sword bending and cracking before it strikes.
- 수동 검수: 실패.
- 실제 문제: 순백 배경, 환경 부재, 환두대도 장식에 가짜 문자형 무늬, 검이 폭발하듯 깨지는 표현.
- 로직 수정: 아직 하지 않음.
- 재생성: 아직 하지 않음.

### cut 80

- 대사: 고구려의 처참한 몰락은 오늘날 우리에게도 서늘한 경고를 남기죠.
- 원본 Scene: A heavy iron boot stepping firmly on a delicate white flower.
- 수동 검수: 실패.
- 실제 문제: 현대식 검은 가죽 부츠, 흰 꽃, 후대 또는 조선풍으로 보이는 도시 건축, 흰 하늘.
- 로직 수정: 아직 하지 않음.
- 재생성: 아직 하지 않음.

### cut 81

- 대사: 우리는 광개토대왕과 을지문덕의 화려한 영광만을 기억하려 애쓰죠.
- 원본 Scene: A glorious, idealized painting of an ancient warrior on horseback.
- 수동 원본 검수: 아직 하지 않음.
- 로직 수정과 재생성: 아직 하지 않음.

### cut 82

- 대사: 통쾌한 영웅담에 취해 멸망의 씁쓸한 진실을 애써 외면하고 맙니다.
- 원본 Scene: A golden chalice spilling dark red wine onto a dry, cracked earth.
- 수동 원본 검수: 아직 하지 않음.
- 로직 수정과 재생성: 아직 하지 않음.

### cut 84

- 대사: 승리의 이면에 도사린 지배층의 추악한 권력욕을 마주해야만 합니다.
- 원본 Scene: A dark, monstrous shadow emerging slowly from a cracked statue.
- 수동 원본 검수: 아직 하지 않음.
- 로직 수정과 재생성: 아직 하지 않음.

이 다섯 컷의 원본 JSON period 필드는 실제로 668year 9로 저장되어 있다. 다음 세션은 정규화·컴파일 결과를 먼저 출력해 확인한 뒤 로직을 수정한다.

## 구현 변경 사항

### backend/app/services/llm/visual_policy.py

- EP30 대사별 장면을 추상 은유가 아니라 수량, 재질, 배치, 시대 요소가 고정된 장면 계약으로 라우팅하는 규칙을 추가했다.
- cut 51: 인장 1개와 찢어진 띠 1개. 의복 오인 방지.
- cut 54: 하사된 흙 위에 반쯤 묻힌 뒤집힌 당 인장 1개. 인물 없음.
- cut 61: 어두운 비단 위 남생 얼굴만 보이는 시신 장면. 눈 완전 폐쇄, 손 0개, 방과 등불 없음.
- cut 63: 평범한 삼베 차양 1개 아래 완전히 염습된 관 1개. 모자, 인물, 벽, 문자 없음.
- cut 66: 마른 붉은 흙 위 납작한 인장 1개와 정렬된 띠 절반 2개.
- cut 69: 끊어지지 않은 외벽 뒤의 보이지 않는 내부 화재와 연기.
- cut 70: 갈라진 성문 들보 1개와 뒤집힌 인장 정확히 2개.
- cut 71: 닫힌 지휘 인장 1개와 끝이 2개인 곧은 띠 1개.
- cut 74: 검푸른 내부 부패가 드러난 무유 곡물 항아리 1개.

### backend/app/services/image/prompt_compiler.py

- 위 장면 계약을 최종 positive prompt 앞부분에 강제하는 컴파일 규칙을 추가했다.
- white background, upright seal, cord, wire, 후대 건축, 간판, 문자, 추가 오브젝트, 열린 U자 인장, 추가 목간·인장 등의 실패 요소를 negative prompt에 전면 배치했다.
- 인물 수, 보이는 손 수, 오브젝트 수, 장면 종류와 구성 diagnostics가 계약과 일치하도록 처리했다.
- 장례, 인장, 띠, 외벽, 성문 들보, 곡물 항아리 장면을 서로 다른 정확한 오브젝트 계약으로 분리했다.

### backend/app/services/image/comfyui_service.py

- _image_has_lower_right_signature_mark에 mirror_horizontal 옵션을 추가했다.
- _image_has_corner_artist_mark가 우하단뿐 아니라 좌하단도 수평 반전 검사로 탐지하도록 변경했다.
- 실제 cut 56 좌하단 서명형 워터마크를 탐지하도록 보강했다.
- featureless dark silk 위 사망한 남생 장면만 _should_ignore_dark_outer_frame_detector 예외로 처리했다.
- cut 61의 어두운 비단을 외곽 검은 프레임으로 오탐하지 않게 했다.
- 사람 없는 오브젝트 장면을 인물 누락으로 오탐하지 않도록 정확한 장면 마커를 추가했다.
- 적용 장면에는 cut 51, 54, 56, 63, 66, 69, 74가 포함된다.

### backend/workflows/comfyui/flux2_klein_4b_text2img.json

- 해부학 인페인트는 현재 최종 출력 경로에 연결되어 있다.
- node 31: 손 DetailerForEach, force_inpaint=true, 입력 node 12.
- node 30: 몸 DetailerForEach, force_inpaint=true, 입력 node 31.
- node 13 SaveImage: node 30 결과를 저장.
- node 41 최종 손 detector: node 30 결과를 검사하고 bbox detector node 14 사용.
- node 42가 node 41의 검출 수를 계산한다.
- node 43이 node 42의 값을 받는다.
- 손 인페인트 denoise 0.22, feather 48.
- 몸 인페인트 denoise 0.14, feather 48.

### backend/tests/test_image_prompt_compiler.py

- 좌하단 다중행 서명형 워터마크 탐지 테스트를 추가했다.
- 어두운 비단 외곽 프레임 예외 테스트를 추가했다.
- EP30 cut 51부터 64의 정확한 장면 계약 테스트를 추가·확장했다.
- EP30 cut 66부터 74의 역사 오브젝트·성곽 장면 계약 테스트를 추가했다.
- 0인 장면이 인물 검출을 요구하지 않는 범위를 검증한다.
- 실제 실패 이미지에 맞춘 detector scope를 검증한다.
- 손 수 계약이 생성 workflow와 최종 detector까지 도달하는지 검증한다.

### backend/tests/test_comfyui_flux2_hand_refine_workflow.py

- FLUX.2 Klein 4B 손·몸 refine workflow 연결과 안전 조건을 검증한다.

### C:\Users\Ai_M9\Desktop\longtube\_regen_project_cuts.py

- 프로젝트 ID와 지정 컷 번호만 받아 generate_one_image를 순차 호출한다.
- 각 컷마다 DB 세션을 별도로 열고 닫는다.
- 실패 컷 목록을 출력하고 하나라도 실패하면 종료 코드 1을 반환한다.
- 전체 프로젝트나 다른 컴퓨터의 큐를 지우는 동작은 없다.

## Git 작업 트리 상태

아래 파일은 저장 시점에 수정 또는 미추적 상태다.

- M backend/app/services/image/comfyui_service.py
- M backend/app/services/llm/visual_policy.py
- M backend/workflows/comfyui/flux2_klein_4b_text2img.json
- ?? backend/app/services/image/prompt_compiler.py
- ?? backend/tests/test_comfyui_flux2_hand_refine_workflow.py
- ?? backend/tests/test_image_prompt_compiler.py
- ?? _regen_project_cuts.py

작업 트리는 기존 변경이 많이 섞여 있다. 전체 diff를 이번 EP30 작업만의 변경으로 간주하면 안 된다. git reset --hard, git checkout --, 광범위한 git add -A를 사용하지 않는다.

## 테스트

저장 직전 실제 실행:

    cd C:\Users\Ai_M9\Desktop\longtube\backend
    C:\Users\Ai_M9\AppData\Local\Programs\Python\Python313\python.exe -m unittest tests.test_image_prompt_compiler tests.test_comfyui_flux2_hand_refine_workflow

결과:

- Ran 99 tests in 7.333s
- OK
- Pillow Image.getdata deprecation warning이 5곳에서 발생했다.
- 경고 위치: comfyui_service.py 43286, 43927, 44037, 44093, 44154
- 테스트 실패는 없다.

## 실패본 보관

모든 보관 폴더는 다음 루트 아래에 있다.

D:\long_result\CH1\고구려\EP.30.260713155401150579\qa_rejected

주요 원본 실패본:

- 20260713_prompt_logic_v2

이번 작업의 순차 재생성 실패본:

- 20260714_initial_regen_failures
- 20260714_second_regen_visual_failures
- 20260714_third_regen_visual_failures
- 20260714_fourth_regen_visual_failures
- 20260714_ep30_fifth_regen_weapon_inventory_failure
- 20260714_ep30_sixth_regen_spear_multiplication_failure
- 20260714_ep30_cuts18_27_28_30_31_32_33_logic_failures
- 20260714_ep30_batch1_visual_failures
- 20260714_ep30_batch1_round2_visual_failures
- 20260714_ep30_batch1_round3_visual_failures
- 20260714_ep30_batch1_round4_visual_failures
- 20260714_ep30_batch1_round5_visual_failures
- 20260714_ep30_batch1_round6_visual_failures
- 20260714_ep30_batch1_round7_visual_failures
- 20260714_ep30_batch1_round8_visual_failures
- 20260714_ep30_batch2_round2_visual_failures
- 20260714_ep30_batch2_round3_visual_failures
- 20260714_ep30_batch2_round4_visual_failures
- 20260714_ep30_batch2_round5_visual_failures
- 20260714_ep30_batch2_round6_dark_silk_frame_false_positive
- 20260714_ep30_batch3_round7_visual_failures
- 20260714_ep30_batch3_round8_visual_failures
- 20260714_ep30_batch3_round9_cut66_upright_marker

세부 유형별 실패본 폴더도 유지한다.

- 20260714_archer_bundle_visual_failures
- 20260714_archer_fletching_failure
- 20260714_armor_panel_tablet_failure
- 20260714_black_tablet_bow_failures
- 20260714_bundle_on_top_foodlike_failure
- 20260714_duplicate_helmet_failure
- 20260714_duplicate_helmet_repeat_failure
- 20260714_forearm_arrow_fragment_failures
- 20260714_futou_text_failures
- 20260714_missing_armor_midshaft_failures
- 20260714_oversized_tally_failure
- 20260714_repeated_arm_double_fletching_failures
- 20260714_single_archer_arrow_multiplication_failure
- 20260714_sleeve_tally_arrowhead_failures
- 20260714_staff_giant_arrow_failures
- 20260714_tally_map_failures
- 20260714_window_arrow_count_failures

이 보관본은 삭제하거나 다시 live images 폴더로 복구하지 않는다.

## 썸네일 상태

- output\thumbnail_bg.png 존재.
- output\thumbnail.png 존재.
- 자동 QA JSON은 두 파일 모두 passed=true다.
- thumbnail.png의 원시 비전 판정은 얼굴 일부가 글자에 가린다는 false 판정을 냈고, 로컬 기하 검사에서 false positive로 override했다.
- thumbnail_bg.png는 face_closeup_soft_quality_warning override로 통과했다.
- 현재 세션의 이미지 컷 검수 과정에서는 썸네일 업로드나 교체를 하지 않았다.
- 다음 세션은 업로드 직전 기존 썸네일 프롬프트 파이프라인 사용 여부와 최종 썸네일을 별도로 확인한다.

## 다음 세션 정확한 재개 순서

1. docs/SESSION_PROTOCOL.md를 읽는다.
2. SESSION_HANDOFF.md를 읽는다.
3. 이 상세 문서를 읽는다.
4. ComfyUI queue_running과 queue_pending을 조회한다.
5. 둘 중 하나라도 0이 아니면 생성 제출, 중지, 삭제, 큐 초기화를 하지 않는다.
6. cut 81, 82, 84의 보관 원본을 원본 크기로 먼저 검수한다.
7. cut 78, 80, 81, 82, 84의 현재 정규화 prompt와 compiled positive/negative를 출력한다.
8. 실제 실패 원인에 대응하는 공용 로직과 회귀 테스트를 먼저 수정한다.
9. 99개 관련 테스트를 다시 통과시킨다.
10. 해당 다섯 컷만 재생성한다.
11. 저장된 다섯 이미지를 각각 원본 크기로 검수한다.
12. 실패하면 결과물을 직접 수정하지 말고 실패본을 새 qa_rejected 폴더에 보관한 뒤 로직을 다시 수정한다.
13. 다섯 컷이 통과하면 남은 목록을 작은 묶음으로 이어간다.
14. live cut_N.png가 정확히 139개가 되기 전에는 영상 조립과 업로드로 진행하지 않는다.
15. 이미지 139개 검수 완료 후 DB image_path/status를 실제 파일과 대조한다.
16. 영상, 자막, 썸네일 파이프라인을 순서대로 실행하고 실제 산출물을 확인한 뒤 업로드한다.

## 실행 명령

ComfyUI 큐 확인:

    Invoke-RestMethod -Uri http://127.0.0.1:8188/queue

관련 테스트:

    cd C:\Users\Ai_M9\Desktop\longtube\backend
    C:\Users\Ai_M9\AppData\Local\Programs\Python\Python313\python.exe -m unittest tests.test_image_prompt_compiler tests.test_comfyui_flux2_hand_refine_workflow

선택 컷 재생성 예시:

    cd C:\Users\Ai_M9\Desktop\longtube
    C:\Users\Ai_M9\AppData\Local\Programs\Python\Python313\python.exe _regen_project_cuts.py V3_CH1_EP30_260713155401150579 78 80 81 82 84

위 재생성 명령은 로직 수정과 테스트가 끝나고 ComfyUI 큐가 비어 있을 때만 실행한다.
