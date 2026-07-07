# Session Handoff - 2026-06-29 CH4 EP18 Continue

## User Rules

- 추론하지 말고 실제 파일과 실제 상태를 기준으로 진행.
- 생성 결과물에 문제가 있으면 이미지 파일을 직접 수정하지 않음.
- 문제 해결 로직을 수정한 뒤 다음 생성물/재생성 컷에 적용.
- 주요 수정은 허락이 필요하나, 이번 작업 범위의 로직 수정은 사용자가 전체 승인함.
- CH1, CH3, CH4 다음 에피소드 순차 진행 지시가 있었고, CH1/CH3는 완료됨. 남은 핵심은 CH4 EP18.
- 모든 생성 이미지는 확대해서 하나씩 확인해야 함.

## Current Workspace

- Workspace: `C:\Users\Ai_M9\Desktop\longtube`
- Current date in latest user context: `2026-06-29`
- Shell: PowerShell
- Approval policy: `never`
- Filesystem: unrestricted

## Completed Uploads In This Run

### CH1 EP18

- Main: `https://youtube.com/watch?v=pYzqsDRXhks`
- Shorts:
  - `https://youtube.com/watch?v=EgU16NtQslw`
  - `https://youtube.com/watch?v=RrSlyPalhrI`
  - `https://youtube.com/watch?v=VdoST3CjQYw`
  - `https://youtube.com/watch?v=WU4bVH29MG8`

### CH3 EP74

- Main: `https://youtube.com/watch?v=PSZ327-nKKs`
- Shorts:
  - `https://youtube.com/watch?v=LN5pTSDhKRY`
  - `https://youtube.com/watch?v=kJovJbz55Do`
  - `https://youtube.com/watch?v=EBVVjejZF5c`
  - `https://youtube.com/watch?v=vi44wwPL1Nk`
- Thumbnail applied successfully:
  - `YouTubeUploader(channel_id=3).set_thumbnail('PSZ327-nKKs', 'D:\long_result\CH3\EP.74.260625200613a2a578\output\thumbnail.png')`
- CH3 image QA was completed before this handoff. All 150 images were enlarged and inspected; failed images were moved/regenerated until final auto check had no flags.

## CH4 EP18 Current State

- Task id: `e916e91f`
- Project id: `V3_CH4_EP18_2606230944454466ae`
- Result folder: `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae`
- Images folder: `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\images`
- Output folder: `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\output`
- Topic/title: `The Fatal Rage: The Apocalyptic Anger of Valentinian I EP.18`
- Image count checked on 2026-06-29:
  - `cut_*.png`: 150
  - `cut_*.png.prompt.json`: 150
- Output files checked:
  - `thumbnail_bg.png`
  - `thumbnail_bg.png.qa.json`
  - `thumbnail.png`
- No `_tmp_start_channel_queue_until_qa.py`, `_tmp_run_task_until_image_qa.py`, or `_tmp_resume_upload_task.py` Python runner was active when checked.

### Pipeline State Before Handoff

The CH4 EP18 task was intentionally returned to image-QA wait state after it had started moving beyond image generation.

Expected state:

- `status="paused"`
- `current_step=4`
- `current_step_name="이미지 QA 대기"`
- `step_states`: steps 2, 3, 4 completed; steps 5, 6, 7 pending
- `image_qa_required_before_video=True`
- `image_qa_approved_before_video=False`

Do not resume video/upload until bad image logic is fixed, failed cuts are regenerated, and regenerated cuts are enlarged/rechecked.

## Code Changes Already Made

### `backend/app/services/llm/base.py`

- `visual_plan.overall_ratio.character_closeup` changed from `5` to `10`.
- Story plan prompts now force major first appearances into medium-close or close-up `character entrance` cuts.
- First appearance requirements added:
  - face
  - eyes
  - expression
  - shoulder angle
  - hand gesture
  - period costume silhouette
- Male first appearances require:
  - intense eyes
  - controlled expression
  - dramatic rim light
  - strong silhouette
  - period-correct armor or command robes
- Adult female first appearances require:
  - adult woman
  - attractive charisma
  - confident eyes
  - elegant period-correct clothing
  - strong silhouette
  - tasteful mature styling
- Female rule explicitly forbids exposure-focused or underage-looking presentation.
- Scene-block expansion now forces character introduction cuts to:
  - `visual_subject=person`
  - `visual_scene=character entrance`

### `backend/app/services/llm/visual_policy.py`

- Added/extended historical character aliases for forced visual identity:
  - Toyotomi Hideyoshi
  - Seonjo
  - Oda
  - Akechi
  - Valentinian
  - Gwanggaeto
  - Murong variants
  - Cleopatra
  - Wu Zetian
  - Seondeok
  - Soseono
  - Yuhwa
  - Yaa Asantewaa
- Added forced entrance identities from:
  - `scene_blocks.character_introductions`
  - `character_map.first_appearance_cut`

### `backend/app/services/image/comfyui_service.py`

Already applied broader image-prompt fixes before this handoff:

- Imjin War / Salsu / text-gate-crate-wall-label fixes.
- `_is_imjin_context`
- `_imjin_plain_material_fragment`
- `_attach_imjin_plain_materials`
- Material fragment now uses a generic physical-material replacement:
  - `all flat surfaces and corners stay as continuous wood grain, cloth weave, rope fiber, paper grain, dust, smoke, water, or shadow`
- Material fragment is skipped for character entrance portraits.
- Added branches for:
  - Ming courier / officials
  - supply scenes
  - mountain road
  - fleet / harbor / channel / messenger ship
  - villagers / damaged / displaced
  - fortification / tired guard / armory
  - closed packet stacks
  - cracked bowl
  - divided council
  - armory upper-right spear rack / smoke
- Negative terms expanded for:
  - crate / box labels
  - wall plaques
  - vertical text
  - marked cargo boxes
  - wall switch
  - outlet
  - modern door handle
  - door plate

Important for next session:

- CH4 EP18 now reveals a Late Roman interior failure pattern: modern-style rooms, door handles, switches, tablet-like objects, office-table layouts.
- Next logic patch must target Late Roman / Valentinian scenes specifically, not globally.
- Preferred replacement direction:
  - open Roman military camp
  - canvas command tent
  - rough timber palisade
  - fieldstone / cracked lime plaster only when truly interior
  - oil lamps, torches, braziers
  - iron ring pulls or no visible door hardware
  - no wall switches, no outlet plates, no modern lock plates, no glass windows, no office desk, no tablet/clipboard objects

### `backend/app/services/thumbnail_service.py`

- Added `_thumbnail_quality_system_prompt()` clarification that pre-overlay image can include persons.
- Added:
  - `_THUMBNAIL_PERSON_PROMPT_RE`
  - `_THUMBNAIL_FACE_CLOSEUP_PROMPT_RE`
  - `_thumbnail_prompt_expects_person`
  - `_thumbnail_prompt_expects_face_closeup`
  - `_thumbnail_person_presence_misread(reason, image_prompt='')`
  - `_thumbnail_closeup_soft_quality_failure`
  - `THUMBNAIL_FACE_CLOSEUP_FRAME_LOCK`
  - `_first_cut_image_path`
- `_thumbnail_click_focus_prompt` now builds a concise head-and-shoulders portrait contract for explicit face close-up thumbnails.
- `_stable_thumbnail_closeup_base` added for Toyotomi/Hideyoshi thumbnail subject stabilization.
- `_openai_thumbnail_quality_check` now overrides object-only person-presence misreads when prompt expects a person, but still hard-fails real text/glyph/cropped/hidden problems.
- `generate_ai_thumbnail` can soft-pass face-closeup QA warnings when prompt explicitly expects face closeup and the failure is not hard failure.
- Fallback thumbnail paths now prefer `images/cut_1.png`, then `images/cut_001.png`.

### `backend/app/tasks/pipeline_tasks.py`

- Upload fallback thumbnail path changed:
  - Prefer `images/cut_1.png`
  - Fallback to `images/cut_001.png`

### Tests Added / Updated

- `backend/tests/test_image_prompt_guards.py`
  - Seonjo council
  - Imjin supply
  - cracked bowl
  - armory
  - displaced villagers
  - character entrances
- `backend/tests/test_oneclick_stability.py`
  - `test_thumbnail_closeup_prompt_blocks_rider_and_gate_composition`
  - extra checks in `test_thumbnail_vision_qa_detects_person_presence_misread`

### Tests Run Successfully

Commands that passed:

```powershell
python -X utf8 -m py_compile backend\app\services\thumbnail_service.py backend\app\tasks\pipeline_tasks.py
```

```powershell
python -X utf8 -m unittest backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_prompt_forces_visible_character_face backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_closeup_prompt_blocks_rider_and_gate_composition backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_basic_quality_rejects_flat_background backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_vision_qa_allows_prompt_matched_people backend.tests.test_oneclick_stability.InterludeStabilityTests.test_thumbnail_vision_qa_detects_person_presence_misread
```

Notes:

- `pytest` was unavailable in the active Python.
- Full suite was not claimed as passing because there were unrelated pre-existing failures.

## CH4 EP18 Enlarged Image QA Progress

Inspection method:

- Each image was opened through `view_image` with `detail="original"`.
- Images were not directly edited.

Current progress:

- Cuts inspected: `1` through `101`
- Next image to inspect in new session: `cut_102.png`

### Confirmed / Priority Bad Candidates So Far

These should be compared with prompt sidecars, then moved aside and regenerated after logic patch. Do not edit pixels.

- `cut_1.png`: prompt was crown/bloodied sword; actual is indoor office-like scene.
- `cut_2.png`: prompt was army marching; actual is indoor people lineup including woman.
- `cut_3.png`: prompt was golden marble emperor-on-horse statue; actual is indoor council.
- `cut_4.png`: prompt was iron nail piercing purple velvet close-up; actual is table council.
- `cut_5.png`: generic soldier corridor; likely prompt mismatch.
- `cut_6.png`: same indoor lineup; no distinct requested scene.
- `cut_7.png`: same indoor council/guards; no distinct requested scene.
- `cut_33.png`: right door handle looks like modern metal lever.
- `cut_35.png`: modern-looking door handles/building despite trench/digging scene.
- `cut_38.png`: modern round door knob and possible glyph-like tunic pattern on right figure.
- `cut_62.png`: right table black box looks like a modern tool case.
- `cut_67.png`: table left/right objects look like modern tablet/notebook devices.
- `cut_69.png`: both doors have modern handles/lock hardware.
- `cut_70.png`: door handles, small wall plate, and table tools look modern.
- `cut_72.png`: wall switch, door handle, and modern window frame visible.
- `cut_73.png`: wall switch and modern door/interior composition visible.
- `cut_74.png`: both door handles look modern.
- `cut_75.png`: wall switch and modern door handles visible.
- `cut_76.png`: wall switch and modern door handles visible.
- `cut_79.png`: door handle/lock hardware looks modern.
- `cut_80.png`: right door handle looks modern.
- `cut_81.png`: center door handle looks modern.
- `cut_82.png`: right figure holds black tablet-like object; room/window also modern.
- `cut_83.png`: wall switch, door handle, tablet-like object, modern meeting-room layout.
- `cut_84.png`: door handles, switch, modern window.
- `cut_85.png`: modern office-like room, door/window structure.
- `cut_86.png`: door handle structure looks modern.
- `cut_87.png`: door handle, window, office-table layout.
- `cut_89.png`: wall switch, modern window, office-table / book-stack layout.
- `cut_90.png`: both wall switches, modern window, office-table layout.
- `cut_91.png`: wall switch and modern office/interior table layout.
- `cut_92.png`: wall switches and modern door handles on both sides.
- `cut_93.png`: door handle and tablet/clipboard-like objects.
- `cut_94.png`: door handle looks modern.
- `cut_95.png`: door handle looks modern.
- `cut_96.png`: modern whiteboard, switch, and office-table layout.
- `cut_97.png`: door handle looks modern.
- `cut_101.png`: sickbed/chair scene but left/right/center door hardware looks modern.

### Ambiguous / Prompt-Compare Candidates

Do not automatically regenerate without checking prompt sidecars.

- `cut_8.png`: general soldiers outside; no text, hold for prompt comparison.
- `cut_14.png`: generic indoor group; no major artifact; prompt comparison needed.
- `cut_16.png` to `cut_18.png`: generic indoor confrontation/strategy; prompt comparison needed.
- `cut_19.png`: riverside village/guards; architecture feels medieval; prompt comparison needed.
- `cut_24.png` to `cut_26.png`: outdoor village/movement; no text, architecture a bit medieval.
- `cut_29.png`: indoor argument/directive; no artifact, prompt comparison.
- `cut_32.png`: soldier/civilian movement; hold.
- `cut_46.png`: small center container may look like text/label; candidate.
- `cut_78.png`: no clear modern object, but repeats indoor corridor/doors pattern; prompt comparison.
- `cut_88.png`: no clear modern handle/switch, but repeats indoor pattern; prompt comparison.
- `cut_98.png`: no switch/tablet, but interior door hardware may be suspicious; prompt comparison.

### Pass Candidates Logged During Manual View

These were visually acceptable unless prompt comparison later proves mismatch:

- `cut_9.png`: collapsed emperor/guard.
- `cut_10.png`: empty throne/guards.
- `cut_11.png`: general soldier gathering.
- `cut_12.png` to `cut_13.png`: Roman/Barbarian envoys entering wooden palisade camp.
- `cut_15.png`: old emperor/guards.
- `cut_20.png`: outdoor labor/watch.
- `cut_21.png`: central person entrance.
- `cut_22.png` to `cut_23.png`: map/strategy tables, no readable text.
- `cut_27.png` to `cut_28.png`: riverside/envoy/horse movement.
- `cut_30.png`: horse/negotiation exterior.
- `cut_31.png`: marching/guard scene.
- `cut_34.png`: field tent/bowls scene.
- `cut_36.png`: campfire/camp scene.
- `cut_37.png`: field command/confrontation.
- `cut_39.png`: horses/soldiers river confrontation.
- `cut_40.png`: large field command tent.
- `cut_41.png`: outdoor camp envoy/warrior group.
- `cut_42.png`: tent command scene; top band is tent cloth, not artifact.
- `cut_43.png`: outdoor camp command.
- `cut_44.png`: camp table reception.
- `cut_45.png`: tent confrontation / dropped metal cup and nails.
- `cut_47.png`: camp rush scene.
- `cut_48.png`: camp elder with cup.
- `cut_49.png`: horsemen in camp.
- `cut_50.png`: document delivery at tent table.
- `cut_51.png` to `cut_55.png`: village movement / detention / wounded cart / planning; architecture should still be prompt-compared if needed.
- `cut_56.png` to `cut_61.png`: camp / ranks / march / horse entrance scenes.
- `cut_63.png` to `cut_66.png`: dock/river/camp/cavalry scenes.
- `cut_68.png`: close character preparation / cloak adjustment.
- `cut_71.png`: soldiers at open threshold; no switch/tablet obvious.
- `cut_77.png`: weapon/hand/blank tablet symbolic frame; no modern object obvious.
- `cut_99.png`: angry Valentinian indoor group; no switch/tablet visible.
- `cut_100.png`: sickbed/chair crisis scene; no switch/tablet visible.

## Immediate Next Steps For New Session

1. Confirm no rogue runner is active:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*_tmp_start_channel_queue_until_qa.py*' -or $_.CommandLine -like '*_tmp_run_task_until_image_qa.py*' -or $_.CommandLine -like '*_tmp_resume_upload_task.py*' } | Select-Object Id,ProcessName,CommandLine
```

2. Continue enlarged manual image QA from:

```text
D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\images\cut_102.png
```

3. Finish through `cut_150.png`.

4. Read sidecars for confirmed/ambiguous failures before regeneration:

```text
D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\images\cut_N.png.prompt.json
```

5. Patch logic, not result images. Target `backend/app/services/image/comfyui_service.py` with a Late Roman / Valentinian-specific guard:

- Prevent modern interior room fallback.
- Strongly prefer Roman command tent, palisade camp, open camp threshold, field command area, or period-local rough military shelter.
- For required interiors, force cracked lime plaster / rough timber / stone, torch or oil lamp only.
- Forbid wall switches, outlet plates, modern door handles, lock plates, glass window frames, whiteboards, office desks, tablet devices, clipboards, modern boxes.
- Force doors to be plain planks with iron ring pulls only, or keep all door hardware outside frame.
- For symbolic object cuts, preserve requested subject and avoid council-room substitution.

6. Add or update focused tests in `backend/tests/test_image_prompt_guards.py` for:

- Valentinian symbolic object cuts not becoming council rooms.
- Late Roman interiors excluding switch plates / modern door handles / office furniture.
- Late Roman command scenes preferring tent/open camp over modern wooden office.

7. Move failed PNG and matching sidecar into a rejected folder before regeneration.

Suggested folder:

```text
D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\rejected_images_20260629_late_roman_modern_interior
```

8. Regenerate only failed cuts using existing batch regeneration script after reading it first:

```text
C:\Users\Ai_M9\Desktop\longtube\_tmp_regen_cut_images_batch.py
```

9. Enlarge-check every regenerated image one by one.

10. Only after QA passes, resume:

```powershell
python _tmp_resume_upload_task.py e916e91f
```

11. Monitor until CH4 main and all shorts upload complete.

12. Confirm final YouTube URLs from channel 4 listing/uploader output.

## Git / Dirty Worktree Note

`git status --short` currently shows many modified and untracked files, many unrelated to this task. Do not revert any existing change. When committing or staging later, stage only the files required for the current task.

Task-related files from this handoff are mainly:

- `backend/app/services/llm/base.py`
- `backend/app/services/llm/visual_policy.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/app/services/thumbnail_service.py`
- `backend/app/tasks/pipeline_tasks.py`
- `backend/tests/test_image_prompt_guards.py`
- `backend/tests/test_oneclick_stability.py`
- `SESSION_HANDOFF_2026-06-29_CH4_EP18_CONTINUE.md`

## Final Reminder

Do not upload CH4 EP18 until all 150 images are enlarged-inspected and failed cuts are regenerated from corrected logic.
