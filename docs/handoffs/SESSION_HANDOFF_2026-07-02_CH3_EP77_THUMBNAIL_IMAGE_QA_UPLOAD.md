# Session Handoff - 2026-07-02 CH3 EP77 Thumbnail / Image QA / Upload

## User Rules

- 추론하지 말고 실제 파일과 실제 상태를 기준으로 진행.
- 생성 결과물에 문제가 있으면 이미지 파일을 직접 수정하지 않음.
- 문제 해결 로직을 수정한 뒤 다음 생성물/재생성 컷에 적용.
- 전체 재생성 금지. 문제 있는 이미지만 로직 수정 후 재생성.
- 인물 등장의 웅장함, 감정선, 스타일리쉬한 화면, 썸네일 프롬프트 품질을 중요하게 봄.
- 손가락 수, 손, 다리, 동물 형태, 시대에 맞지 않는 물품과 무기는 반드시 확인.
- 썸네일 문자는 얼굴을 가리면 안 됨.

## Workspace

- Workspace: `C:\Users\Ai_M9\Desktop\longtube`
- Shell: PowerShell
- Filesystem: unrestricted
- Approval policy: `never`
- Latest user context date: `2026-07-02`

## Completed Episodes In Latest Run

### CH1 EP21

- Task id: `d018f46d`
- Project id: `V3_CH1_EP21_2607011534044c1ce3`
- Result folder: `D:\long_result\CH1\고구려\EP.21.2607011534044c1ce3`
- Main URL: `https://youtube.com/watch?v=p9_bPoJwNUo`
- Shorts:
  - `https://youtube.com/watch?v=DiRDpz7BjUc`
  - `https://youtube.com/watch?v=0JwADz6Dna8`
  - `https://youtube.com/watch?v=cN-eqnjuxXU`
  - `https://youtube.com/watch?v=Lu4P2jeD2LM`

### CH3 EP77

- Task id: `61748e71`
- Project id: `V3_CH3_EP77_260701162949edeb8e`
- Result folder: `D:\long_result\CH3\EP.77.260701162949edeb8e`
- Topic: `도쿠가와 이에야스는 왜 최후의 승자가 됐을까`
- Main URL: `https://youtube.com/watch?v=9HFi3nfg4Ec`
- Shorts:
  - `https://youtube.com/watch?v=JVe0t2BGb7U`
  - `https://youtube.com/watch?v=g7kwJ7Iaqs8`
  - `https://youtube.com/watch?v=FFWTzqBeGm0`
  - `https://youtube.com/watch?v=qr3jleAyysU`

## CH4 Current Block

- CH4 next episode was not started.
- Latest checks did not find a valid CH4 EP21 source.
- Only stale CH4 EP04/EP06/EP11 queue entries were found.
- Do not start those stale entries unless the user explicitly approves.

## CH3 EP77 Runtime Verification

- Final task state checked:
  - `task_id=61748e71`
  - `status=completed`
  - step states `2`, `3`, `4`, `5`, `6`, `7`: completed
  - `error=null`
- Final video checked:
  - `D:\long_result\CH3\EP.77.260701162949edeb8e\output\final_with_subtitles.mp4`
  - size: `164664087` bytes
  - timestamp: `2026-07-01 19:36:29`
- Upload runner check after completion:
  - recent oneclick runner process was gone.
  - backend uvicorn and persistent ComfyUI/python processes remained.

## Thumbnail QA

- Thumbnail file:
  - `D:\long_result\CH3\EP.77.260701162949edeb8e\output\thumbnail.png`
- Visual check result:
  - Japanese overlay text is lower-left.
  - Main face is right/center.
  - Text does not cover eyes, nose, mouth, chin, forehead, or expression.
- This thumbnail was accepted.

## Image QA And Regeneration

- Full episode images were not regenerated.
- Only failed/problem cuts were regenerated after logic changes.
- Final candidate sheet viewed:
  - `C:\Users\Ai_M9\Desktop\longtube\_qa_ch3_ep77_sheets\ch3_ep77_final_problem_candidates_after_66_123_145.jpg`
- Sheet included:
  - `43`, `44`, `46`, `57`, `66`, `73`, `82`, `94`, `99`, `100`, `101`, `106`, `107`, `114`, `116`, `123`, `141`, `145`
- Accepted regenerated cuts:
  - `cut_145`: final output is open rice-field road with workers/child; no close sign/shop/building trigger accepted.
  - `cut_66`: final output has sealed bundles/cords; no sleeve patch or paper-document issue accepted.
  - `cut_123`: final output has cords/stones/clay/rope coils; no paper map/open book/line markings accepted.

## DB Repair During Upload Resume

- Final render initially failed because DB had six cuts with missing image paths.
- Affected cuts:
  - `7`, `92`, `120`, `125`, `127`, `143`
- Actual image/audio files existed under the project directory.
- DB backup made before repair:
  - `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch3_ep77_missing_image_paths_20260701_193243.db`
- Repaired only those six rows in `data\longtube.db`:
  - `image_path='images/cut_N.png'`
  - `image_model='comfyui-flux2-klein-4b'` when null
  - `status='completed'`
- Resume command used after repair:
  - `python _tmp_resume_upload_task.py 61748e71`
- After repair:
  - image collection showed `ai=150 failed=0`
  - final render collected `150/150` cut videos
  - shorts rendered: `4`
  - upload completed.

## Code Changes - Thumbnail Logic

File: `backend/app/services/thumbnail_service.py`

- Added final thumbnail overlay QA path:
  - `_thumbnail_overlay_quality_system_prompt`
  - `_openai_thumbnail_overlay_quality_check`
  - `_validate_thumbnail_final_overlay`
- `generate_ai_thumbnail` now validates final `thumbnail.png` after overlay.
- Overlay text covering face, eyes, nose, mouth, chin, forehead, or emotional expression fails the attempt.
- Background QA prompt now fails if the lower-left text-safe zone contains:
  - face
  - eyes
  - nose
  - mouth
  - chin
  - hands
  - animal
  - main subject
- `generate_thumbnail` now uses OpenCV Haar best-effort face boxes for placement scoring:
  - `_detect_thumbnail_face_boxes`
  - `_thumbnail_text_layout_score`
- Text placement now chooses lower-left, upper-left, lower-right, or upper-right by overlap score.
- Fallback guard tightened:
  - `_thumbnail_error_allows_first_cut_fallback` now disallows fallback on `AI 썸네일 최종 오버레이 품질검증 실패`.
  - `_generate_thumbnail_with_overlay_guard(...)` runs final overlay QA after fallback/first-cut text rendering.
  - `ensure_standard_thumbnail` fallback now calls `_generate_thumbnail_with_overlay_guard`.
  - `generate_ai_thumbnail` internal first-cut fallback now calls `_generate_thumbnail_with_overlay_guard`.
- If fallback overlay QA fails, `ThumbnailError` is raised instead of accepting the bad thumbnail.

## Code Changes - CH3 Japanese Historical Image Logic

File: `backend/app/services/image/comfyui_service.py`

### Existing Guard Context Kept

- Late premodern interior prop guard remains:
  - no desk/task/anglepoise/electric table lamps
  - no power cords
- Internal text detection remains:
  - `_INTERNAL_TEXT_GENERATION_CHECK_RE`
  - `_ARCHITECTURE_TEXT_GENERATION_CHECK_RE`
  - `_should_check_internal_text_after_generation`
  - `_image_has_internal_text_like_marks`
- After-generation retry on internal text-like marks remains.
- Japanese sign-free helper functions remain:
  - `_flux2_klein_japanese_sign_free_composition_sentence(source_prompt: str = "")`
  - `_flux2_klein_japanese_textless_retry_sentence()`
  - `_flux2_klein_japanese_text_surface_negative()`
- Broad pixel panel detector must not be restored. It was removed earlier because it caused large false positives.

### Street / Merchant / Shop Trigger Fix

- `_flux2_klein_japanese_sign_free_composition_sentence(...)` street branch changed to rice-field road composition.
- Positive prompt now favors:
  - road
  - rice fields
  - reeds
  - handcarts
  - workers
  - open air
- Positive prompt now avoids buildings in Japanese street contexts.
- `_flux2_klein_md_positive_contract` detects `japanese_street_context`.
- In Japanese street context, raw source sentences are ignored and `_build_from_fields()` is used.
- This prevents source terms from surviving into positive prompt:
  - `Edo street`
  - `merchant quarters`
  - `stalls`
  - `shop`
  - `storefront`
  - `building`
  - `wood grain`
  - `doorway`
  - `wall`
  - `sign`
- `_build_from_fields` converts street/town/merchant/stall/shop/community sources to:
  - early Edo rural work road near Edo outskirts
  - rice paddies
  - reed banks
  - handcarts
  - baskets
  - workers
  - child in kosode
- `_finalize_md_contract` strips generic positive fragments containing document/sign/wall wording for Japanese street/document contexts.
- Japanese street negative terms expanded to include:
  - `building`
  - `house`
  - `roof`
  - `roof tile`
  - `roofed building`
  - `wooden shop`
  - `shop`
  - `shop doorway`
  - `shop counter`
  - `stall canopy`
  - `eave`
  - `hanging fabric`
  - `paper notice`
  - `wall notice`
  - `white notice sheet`
  - `kanji sheet`
  - `field stake with writing`
  - modern child clothing terms

### Sleeve Patch / Map / Document Fix

- Japanese text-surface negative now also blocks:
  - `sleeve emblem`
  - `sleeve badge`
  - `sleeve patch`
  - `robe sleeve mark`
  - `colored arm patch`
  - `red sleeve badge`
  - `white sleeve patch`
  - `clothing patch`
  - `red-and-white badge`
- Map/document negatives expanded:
  - `paper map`
  - `parchment map`
  - `drawn map`
  - `map lines`
  - `ink route lines`
  - `drawn borders`
  - `contour lines`
  - `handwritten map symbols`
  - `labeled map`
  - `white map sheet`

### Japanese Document Context Fix

- Added `japanese_document_context`.
- Japanese document context now prioritizes `_build_from_fields()` before Imjin/character contracts.
- Raw source phrases like `reads blank document` no longer survive in positive prompt.
- Direct document branch in `_build_from_fields` returns:
  - Ieyasu studying sealed packet bundles at a low table
  - sealed cloth-wrapped bundles
  - cord knots
  - stone route markers
- Positive prompt avoids paper/document wording in this context.

### Osaka Defense Board Fix

- `_build_from_fields` detects:
  - `board of ... defenses`
  - `defense board`
  - `Osaka's defenses`
  - `council over Osaka`
- Converted to:
  - Tokugawa legitimacy council over raised cord-and-stone Osaka defense markers.
- Positive prompt uses:
  - raised rope cords
  - pebbles
  - plain clay blocks
  - bronze weights
  - rope coils
- Removed `closed cloth bundles` from Osaka defense-board composition because it generated book/paper-like objects.

### Compact Japanese Sign-Free Sentence Fix

- Compact Japanese sign-free sentence now passes `source`.
- This prevents generic `shopfront bands` / plain-wall sentence from appearing in street context.

## Code Changes - Tests

File: `backend/tests/test_oneclick_stability.py`

- Added import:
  - `from app.services import thumbnail_service as thumb_svc`
- Added/updated thumbnail tests:
  - `test_thumbnail_quality_failure_does_not_fallback_to_first_cut`
  - `test_thumbnail_fallback_overlay_guard_runs_final_qa`
  - `test_thumbnail_quality_prompts_reject_face_covered_by_overlay`
  - `test_thumbnail_overlay_layout_penalizes_face_overlap`
- Added/updated Japanese image prompt tests:
  - `test_flux2_klein_japanese_street_contract_removes_building_sign_triggers`
  - `test_flux2_klein_japanese_negative_blocks_sleeve_patches`
  - `test_flux2_klein_japanese_osaka_defense_board_uses_raised_markers`
  - existing `test_flux2_klein_japanese_contract_crops_out_sign_zones`
  - existing `test_flux2_klein_japanese_contract_replaces_open_documents`

## Verification Commands Passed

```powershell
python -X utf8 -m py_compile backend\app\services\thumbnail_service.py backend\app\services\image\comfyui_service.py backend\tests\test_oneclick_stability.py
```

Focused unittest targets passed:

```powershell
python -X utf8 -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_quality_failure_does_not_fallback_to_first_cut
python -X utf8 -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_fallback_overlay_guard_runs_final_qa
python -X utf8 -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_quality_prompts_reject_face_covered_by_overlay
python -X utf8 -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_overlay_layout_penalizes_face_overlap
python -X utf8 -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests.test_flux2_klein_japanese_street_contract_removes_building_sign_triggers
python -X utf8 -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests.test_flux2_klein_japanese_negative_blocks_sleeve_patches
python -X utf8 -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests.test_flux2_klein_japanese_osaka_defense_board_uses_raised_markers
python -X utf8 -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests.test_flux2_klein_japanese_contract_crops_out_sign_zones
python -X utf8 -m unittest backend.tests.test_oneclick_stability.HistoricalImagePromptStabilityTests.test_flux2_klein_japanese_contract_replaces_open_documents
```

## Git / File State Notes

- Relevant tracked files modified at handoff time:
  - `CHANGELOG.md`
  - `CONTEXT.md`
  - `SESSION_HANDOFF.md`
  - `backend/app/services/image/comfyui_service.py`
  - `backend/app/services/thumbnail_service.py`
  - `backend/tests/test_oneclick_stability.py`
- New detailed handoff file:
  - `docs/handoffs/SESSION_HANDOFF_2026-07-02_CH3_EP77_THUMBNAIL_IMAGE_QA_UPLOAD.md`
- `data\longtube.db` did not appear in the restricted tracked status output, but it was repaired locally as described above.
- No commit was made in this handoff step.

## Next Session Start Checklist

1. Read `docs/SESSION_PROTOCOL.md`.
2. Read root `SESSION_HANDOFF.md`.
3. Read this file as the latest detail.
4. Check actual git status before changing code.
5. Check current oneclick safety/runtime state before starting another episode.
6. Do not resume or start CH4 unless a valid next CH4 source is confirmed.
7. Keep image QA logic-first: patch logic, regenerate only bad cuts, inspect regenerated outputs.
