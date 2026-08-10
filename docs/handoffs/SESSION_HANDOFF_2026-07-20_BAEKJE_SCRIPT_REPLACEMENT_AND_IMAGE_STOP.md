# Session Handoff — CH1 백제사 대본 교체 완료 / CH2 EP02 이미지 생성 취소 상태

저장 시각: 2026-07-20 17:17 KST

이 문서는 새 세션의 최신 상세 원장이다. 채팅 요약으로 대체하지 말고 끝까지 읽은 뒤 실제 파일, DB, task JSON, 큐, 프로세스를 다시 확인한다.

## 새 세션 필수 시작 순서

1. `AGENTS.md`
2. `docs/SESSION_PROTOCOL.md`
3. `SESSION_HANDOFF.md`
4. 이 문서 전체
5. `docs/handoffs/SESSION_HANDOFF_2026-07-20_ZIMAGE_CH2_EP02_CH3_EP07_CLEAN_REBUILD.md` 전체
6. `docs/handoffs/SESSION_QA_V3_2026-05-08.md` 전체
7. `CONTEXT.md`
8. 새 사용자가 지시한 작업과 직접 관련된 실제 코드

새 세션은 문서를 읽기만 하고 임의로 생산 재개, 모델 전환, 큐 실행, 결과물 삭제, 중요 로직 수정을 시작하지 않는다. 사용자의 새 지시를 먼저 받는다.

## 절대 규칙

- 추측하지 않는다. 파일, DB, JSON, API, 실제 프로세스와 결과물 기준으로 판단한다.
- 생성 결과물을 직접 보정하지 않는다. 문제를 만든 프롬프트·워크플로·로직을 수정하고 실패 결과물을 버린 뒤 재생성한다.
- 이미지 모델을 조용히 바꾸지 않는다. Z-Image Base, Turbo, Flux2, SDXL 등 모델 변경은 사용자 명시 승인이 필요하다.
- 이미지 시대 고증은 필수다. 시대·지역·문화·복식·머리·도구·무기·건축·운송·의례물·재료·경관이 컷과 맞아야 한다.
- 자동 사후 검출기 결과로 이미지를 승인하지 않는다. 접촉 시트와 원본을 직접 검수한다.
- 손 디테일러의 `hand_yolov8s`는 사용자가 요청한 인페인트 경로다. 제거된 자동 사후 거부 검출기와 혼동하지 않는다.
- 손 디테일러는 기존 손동작과 물체 접촉을 보존해야 한다. 손가락을 보이려고 손바닥을 강제로 펴지 않는다.
- dirty worktree를 reset, checkout, clean, 광범위 stage하지 않는다.
- 원격 YouTube 영상 삭제는 명시 승인 없이는 하지 않는다.

## 저장 시 런타임 상태

- Backend health: `status=ok`, version `V3.2`.
- Backend URL: `http://127.0.0.1:8000`.
- Backend PID: `17288`.
- ComfyUI URL: `http://127.0.0.1:8188`.
- ComfyUI PID: `20484`.
- ComfyUI queue: running `0`, pending `0`.
- `/api/oneclick/safety`는 무인증 호출 시 HTTP 401이다. 인증 없이 실패했다고 안전 상태를 추측하지 않는다.
- `oneclick_queue.json`의 모든 `channel_times`는 `null`이다. 자동 스케줄 실행은 비활성 상태다.
- Queue presets:
  - CH1: `f60d6b0b`
  - CH2: `e6619f7e`
  - CH3: `7d8b63e5`
  - CH4: `83cca89d`

## CH2 EP02 실제 중단 상태

### Task / project

- Task: `d095a187`
- Status: `cancelled`
- Error: `사용자 취소`
- Started: `2026-07-20T06:02:50Z`
- Finished/cancel request recorded: `2026-07-20T07:52:22Z`
- Project: `V3_CH2_EP2_260720150248078b10`
- Result directory: `D:\long_result\CH2\Scartography\EP.2.260720150248078b10`
- Episode code: `EP002`
- Topic: `Yamnaya Migration Spreads Indo-European Languages`
- Series: `Scartography`
- Current step stored in task: Step 4 image generation
- Progress: `35.6%`
- Step completion:
  - Step 2 script: `150/150`
  - Step 3 audio: `150/150`
  - Step 4 images: `59/150`
  - Step 5 videos: `0/150`
- No render or upload was completed for this cancelled project.

### Files actually present

- `images`: 59 PNG + 59 `.json` sidecars, 118 files total.
- PNG cut numbers: `1-53, 67, 84, 100, 117, 133, 150`.
- `audio`: 150 files.
- `videos`: 0 files.
- `output`: 4 pre-video assets totaling about 3.85 MB.
- Do not trust the 59 images as an approved continuous sequence. The user stopped the run after object-heavy output concerns.

### Mixed-model warning

- The task began with Z-Image Base during the 10-cut preflight.
- Task logs show Base as `ComfyUI Z-Image Base (local, CFG)`, 50 steps, CFG path active.
- The user later said Base was too slow and ordered a switch.
- Later task logs show `ComfyUI Z-Image Turbo (local, fast)`, 8 steps.
- The stored task config and current project DB config now report `comfyui-z-image-turbo` with `scene_contract_v2`.
- Therefore this cancelled result contains Base and Turbo images in one directory. It must not be resumed as a homogeneous approved production result.
- Do not silently switch it back to Base. Obtain the user's next instruction.

### Current source template state

Actual DB reads at handoff save:

- CH2 template `e6619f7e`
  - `image_model=comfyui-z-image-turbo`
  - `image_prompt_profile=scene_contract_v2`
  - `image_qa_required_before_video=true`
  - `image_qa_approved_before_video=false`
- CH3 template `7d8b63e5`
  - `image_model=comfyui-z-image-turbo`
  - `image_qa_required_before_video=true`
  - `image_qa_approved_before_video=false`
- CH1 template `f60d6b0b`
  - `image_model=comfyui-z-image-turbo`
  - `image_qa_required_before_video=true`
  - `image_qa_approved_before_video=false`

The earlier Z-Image handoff contains the Base installation and QA history. Its earlier statement that the templates were set to Base is no longer the current state; the live DB values above supersede it.

## CH3 EP07 actual queue state

- Queue item: `clean-rebuild-ch3-ep007-20260720`
- Global queue array index: `0`
- Status: `pending`
- Channel: `3`
- Episode number: `7`
- Episode code: `CH3_C1_EP007`
- Series: `제1장 신들의 시대와 한반도의 그림자`
- Topic: `죽은 여신의 시신에서 피어난 생명`
- Template project: `7d8b63e5`
- No current CH3 EP07 project/task has started from this queue item.
- `channel_times['3']=null`, so index 0 does not mean it will auto-run.
- Do not start it automatically in the new session. Wait for the user's next command.

## Current queue totals

File source: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.json`

- Total: `105`
- CH1: `39`, all pending, `백제사-EP02` through `백제사-EP40`
- CH2: `32`, all pending, `EP003` through `EP034`
- CH3: `34`, all pending, `CH3_C1_EP007` through `CH3_C1_EP040`
- CH4: `0`
- CH2 EP02 is not currently in the queue because its run became task `d095a187` and was cancelled.

## Image pipeline state carried forward

The full history and evidence are in `SESSION_HANDOFF_2026-07-20_ZIMAGE_CH2_EP02_CH3_EP07_CLEAN_REBUILD.md`. The current facts that must not be lost are:

- Required visual style is the supplied `Priest` direction: mature dark historical manhwa, rough variable-width dip-pen contours, strong black silhouettes, dense hatching, aged muted sepia/rust/soot palette, adult hard-boiled tone.
- Bright clean generic cartoon/anime is a style failure.
- Automatic post-generation rejection/retry/quarantine detector execution was removed by user order.
- Manual original-image/contact-sheet QA is required.
- The Z workflows keep the user-requested hand detailer and safe-edge crop.
- Natural curled, gripping, foreshortened, overlapped, occluded, sleeve-covered and cropped hands are valid. Do not force open palms or spread fingers.
- Base remains installed at `C:\models\diffusion_models\z_image_bf16.safetensors`.
- Base verified size: `12,309,866,400` bytes.
- Base verified SHA-256: `996a67d3ff666946b1c25cbc16d1b1918b6cc0ac166309e23fe3b3d830263dee`.
- Base workflows remain in the repo as untracked files:
  - `backend/workflows/comfyui/z_image_base_text2img.json`
  - `backend/workflows/comfyui/z_image_base_text2img_ref.json`
- Base is installed but is not the active live template model at this handoff.
- The user objected that production was overproducing artifact/object-only cuts. Do not resume generation before verifying scene-kind routing and subject-vs-object balance from actual prompts.

## Known image test issue not fixed in the last task

Running the full `tests.test_ch1_baekje_workbook_converter` module produced three remaining failures:

- EP01 Pungnap cuts `106`, `107`, `108`
- Current compiled `scene_kind` was `object`
- Test expectation was `landscape`

These failures existed after the current prompt-compiler/style changes and were not fixed during the workbook replacement because the user asked only to replace CH1 Baekje scripts. This is directly relevant to the user's object-only complaint. Do not hide it and do not change classification logic without first inspecting actual prompt-compiler behavior and receiving permission for the important fix.

## CH1 백제사 최종검수본 교체 — 완료

### User request executed

The user supplied:

`Z:\HDD2\longtube\CH1 10분역공\2. 삼한시대\백제사\백제사_01-40화_6000컷_통합대본_최종검수완료.xlsx`

The existing CH1 Baekje prepared scripts were replaced with this workbook. The workbook itself was not edited.

### Source workbook evidence

- Size: `868,853` bytes
- SHA-256: `B99193FE2645311E0CD6DF39309E029467D42BE4645830B5797C6DB7710EA137`
- Sheets: exact `01화` through `40화`
- Each sheet used range: `A1:D159`
- Episode count: `40`
- Cuts per episode: `150`
- Total cuts: `6,000`
- Unique raw image prompts: `6,000`
- New-source prompt-cleanup count: `0`
- Shorts-tagged cuts: `2,293`
- Pungnap archaeology source-context overrides: `9`
- Pipeline-applied unique prompts: `6,000`
- First title: `왕위에서 밀려난 온조, 형의 몰락 위에 세운 백제`
- Last title: `후백제의 비극적 결말과 끈질긴 생명력`

The final-reviewed workbook differs materially from the old source:

- 597 narration cells changed versus the previously generated prepared scripts.
- 39 thumbnail prompts changed.
- All 6,000 image prompts changed.
- Shorts selection changed from the prior 2,321 to 2,293.
- This is a distinct exact-hash source contract, not a filename-only replacement.

### Prepared-script destination

`C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts`

Final state:

- `백제사-EP01_script.json` through `백제사-EP40_script.json`: exact 40 files
- Total cuts read back: 6,000
- Every file: 150 cuts
- Total shorts candidates read back: 2,293
- Every script source path points to the final-reviewed workbook
- Every script source SHA-256 equals `B99193FE...7710EA137`
- Manifest file hashes mismatching actual files: 0
- Same directory's `고구려-EP01_script.json` through `고구려-EP30_script.json`: preserved, 30 files

Manifest:

`C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts\백제사_manifest.json`

Manifest contract:

- `source_contract=baekje-final-review-v1`
- `episode_count=40`
- `cut_count=6000`
- `shorts_cut_count=2293`
- `cleaned_prompt_count=0`
- `source_context_override_count=9`
- `pipeline_unique_image_prompt_count=6000`

### Recovery backup

`C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts\_backup\baekje_before_20260720_170856`

- 40 previous Baekje prepared scripts
- previous `백제사_manifest.json`
- total backup files: 41
- Do not restore this backup without explicit user instruction.

### Queue behavior during replacement

- `oneclick_queue.json` was not rewritten by the Baekje prepared-script replacement.
- Queue file last-write time remained `2026-07-20 16:52:22 KST`, before the 17:08 prepared-script write.
- CH1 queue remains 39 pending items, EP02-EP40.
- Completed/public EP01 was not requeued.
- Other-channel queue contents were preserved.

## Baekje converter/registrar logic changes

### `backend/scripts/ch1_baekje_workbook_to_prepared_scripts.py`

- Default workbook path now points to `_최종검수완료.xlsx`.
- Added exact known source contracts:
  - legacy hash `AA6F37C1...C1339C`
  - final-review hash `B99193FE...10EA137`
- Unknown workbook hashes now fail explicitly instead of being treated as a known source.
- Final-review expected values are schema-bound:
  - cleaned prompts 0
  - shorts 2,293
- Legacy expected values remain represented:
  - cleaned prompts 5,850
  - shorts 2,321
- Added `source_contract` to the manifest.
- Added exact SHA-256 guards for the final-review prompts at EP01 cuts 106-114.
- Preserved the existing nine Pungnap archaeology corrections instead of allowing the final workbook's generic early-state prompts to turn those cuts into an inaccurate ancient court/gate scene.
- The corrected Pungnap route remains modern archaeological documentary/evidence context.
- Existing Baekje scripts are backed up before atomic replacement.
- Existing Baekje manifest is now also copied into the same recovery backup.

### `backend/scripts/ch1_register_baekje_queue.py`

- Expected source hash changed to the final-reviewed workbook.
- Expected cleaned prompts changed to 0.
- Expected shorts changed to 2,293.
- Manifest comparison now includes `source_contract`.
- This script was used only as a full canonical verifier in this task. It built 40 candidate queue items in memory/stdout but did not write the live queue.

### `backend/app/services/llm/visual_policy.py`

Two narrow source-locked idempotence fixes were required because the current broader prompt work appended a generic narration-alignment tail, then removed it on reapplication:

- `inject_source_locked_visual_context()` now strips `NARRATION VISUAL ALIGNMENT` from the source-locked scene before compiling the stored prompt.
- `_append_narration_alignment_hint()` no longer appends that tail to a prompt already compiled with both `Global visual world:` and `Scene evidence:`.

This restored source-locked first-application/reapplication equality and allowed the 40-episode converter to validate actual pipeline prompts.

### Test file

`backend/tests/test_ch1_baekje_workbook_converter.py`

- Added a final-review Pungnap row test using exact final-workbook cut 114 prompt content.
- It verifies the inaccurate Onjo/Wirye timber-gate scene is replaced by the guarded Pungnap archaeology contract.

## Baekje replacement verification executed

1. Artifact-tool import and render:
   - 40 sheets confirmed.
   - Representative renders visually inspected for 01화, 20화, 40화.
2. Read-only workbook audit:
   - 40 episodes, 6,000 cuts, 6,000 unique prompts, 2,293 shorts.
3. Converter dry run against copied final source:
   - success with contract `baekje-final-review-v1`.
4. Converter write against the original Z: source path:
   - success, 40 files written, backup created.
5. Canonical registrar verification against the written scripts:
   - source hash matched
   - 40 episodes
   - 6,000 cuts
   - 6,000 pipeline-unique prompts
   - 2,293 shorts
   - first ID `ch1-baekje-ep001`
   - last ID `ch1-baekje-ep040`
6. Manifest vs actual file SHA-256 comparison:
   - mismatch count 0.
7. Runtime prepared-script loader probes:
   - EP02 selected final script, 150 cuts, final source hash
   - EP20 selected final script, 150 cuts, final source hash
   - EP40 selected final script, 150 cuts, final source hash
8. Python compilation:
   - converter, registrar, visual policy, converter test file passed.
9. Focused unit tests:
   - 8 passed.

Do not state that the entire repository test suite passed. It was not run. Do not state that the full Baekje converter test module passed; its three current scene-kind failures are recorded above.

## Baekje inspection evidence

Directory:

`C:\Users\Ai_M9\Desktop\longtube\.codex_inspection\ch1_baekje_replace_20260720`

Important files:

- `inspect_workbook.mjs`
- `audit_new_workbook.py`
- `compare_workbooks.py`
- `qa\workbook_inspect.json`
- `qa\01화.png`
- `qa\20화.png`
- `qa\40화.png`
- `sources\new.xlsx`

These are inspection/support artifacts, not the production source of truth. The Z: workbook and the prepared-script manifest remain authoritative.

## Git/worktree state

- Branch: `main`
- HEAD: `b1f6113 Register CH2 Europe English production queue`
- `origin/main`: `4b025cb Smooth Japanese TTS tail delivery`
- Worktree is heavily dirty and contains old user changes, generated QA assets, untracked source files and current session edits.
- Latest observed tracked diff summary before this handoff: 49 files, about 22,114 insertions and 2,726 deletions.
- CH1 converter, registrar and converter test are untracked files in Git even though they are live and were used successfully.
- Z-Image Base workflow files are also untracked.
- `backend/app/services/llm/visual_policy.py` is tracked but contains thousands of pre-existing/current-session changes beyond the two narrow Baekje idempotence edits.
- Do not broadly stage or commit the code tree from this state.
- Do not reset, checkout or clean the tree.
- This handoff operation changes only `SESSION_HANDOFF.md` and this dated document.

## Public uploads preserved

- Completed CH2 EP01 remains public and complete; see `SESSION_HANDOFF_2026-07-16_CH2_EP01_COMPLETE.md`.
- Completed CH1 Baekje EP01 remains public and complete; see `SESSION_HANDOFF_2026-07-15_CH1_BAEKJE_EP01_COMPLETE.md`.
- The older CH2 EP02 public main video `https://youtube.com/watch?v=eGW12Gg_LxY` remains preserved.
- No remote deletion was performed in the last task.

## What the next session must not do automatically

- Do not resume task `d095a187`; it is cancelled and contains mixed Base/Turbo output.
- Do not treat its 59 images as approved.
- Do not start CH3 EP07 only because it is global index 0.
- Do not switch models without a fresh explicit instruction.
- Do not approve image QA or continue to video/render/upload without direct review.
- Do not revert the Baekje final-reviewed scripts to the legacy backup.
- Do not requeue completed Baekje EP01.
- Do not modify workbook cells or generated prepared JSON by hand to solve logic problems.
- Do not claim the object-vs-landscape scene-kind issue is solved.

## Clean continuation points

If the user next asks about CH1 Baekje scripts:

1. Read the final manifest and exact target prepared script.
2. Confirm source SHA-256 remains `B99193FE...10EA137`.
3. Use the runtime loader by exact episode code.
4. Do not touch the queue unless explicitly asked.

If the user next asks to continue CH2 EP02 / CH3 EP07 production:

1. Re-read the prior Z-Image detailed handoff.
2. Recheck live template models and task/queue state.
3. Address the verified object-only/scene-kind problem at the prompt/compiler logic level before a new run.
4. Generate a small historically difficult preflight and directly inspect originals/contact sheet.
5. Stop on style or historical-accuracy failure.
6. Only after explicit direction, remove/requeue the cancelled mixed-model CH2 project using the official scoped cleanup route.
7. Keep manual QA hold active before Step 5.

## Final authoritative state at save

- CH1 Baekje prepared-script replacement: complete and verified.
- CH1 Baekje live queue: unchanged, pending EP02-EP40.
- CH2 EP02 clean rebuild: cancelled at 59 stored images, not approved, no video/upload.
- CH3 EP07 clean rebuild: pending queue index 0, not started.
- Backend: healthy.
- ComfyUI: idle.
- Next action: wait for the user's explicit instruction in the new session.
