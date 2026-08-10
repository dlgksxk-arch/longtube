# Session Handoff — Z-Image Production Style / CH2 EP02 + CH3 EP07 Clean Rebuild

Date: 2026-07-20 (Asia/Seoul)

## 2026-07-20 15:05 KST - Z-Image Base installed, QA passed, CH2 EP02 started

- The user explicitly authorized installation and use of Z-Image Base.
- Installed checkpoint: `C:\models\diffusion_models\z_image_bf16.safetensors`.
  - Exact size: `12,309,866,400` bytes.
  - SHA-256: `996a67d3ff666946b1c25cbc16d1b1918b6cc0ac166309e23fe3b3d830263dee`.
  - The size and SHA-256 matched the official Comfy-Org repository metadata before the `.part` file was renamed into service.
- Registered model ID: `comfyui-z-image-base`.
  - Factory and ComfyUI display/workflow maps now include the Base model.
  - Both source studios `e6619f7e` and `7d8b63e5` now have `config.image_model=comfyui-z-image-base`; no other template config field was intentionally changed.
- Added Base workflows:
  - `backend/workflows/comfyui/z_image_base_text2img.json`
  - `backend/workflows/comfyui/z_image_base_text2img_ref.json`
  - Main sampling uses the official Base settings used here: 50 steps, CFG 4.0, Euler/simple, real `${NEGATIVE}` conditioning.
  - Hand refinement remains `hand_yolov8s` -> `BboxDetectorSEGS` -> `DetailerForEach`, with 28 steps, CFG 4.0, `denoise=0.22`, `force_inpaint=true`, `feather=48`.
  - The final route remains hand detailer -> deterministic safe-edge crop -> save. The automatic post-generation rejection detector remains removed.
- Base support uses the same `scene_contract_v2`, Priest-reference dark hard-boiled historical manhwa style, hand gesture-preservation logic, and safe-edge crop as the Z family.
- Focused verification after Base registration: 8 tests passed. Python syntax, both Base workflow JSON files, and targeted `git diff --check` passed; the latter reported only existing LF/CRLF warnings.
- Direct Base QA folder: `D:\long_result\_qa_trials\z_image_base_20260720`.
  - Rejected `ch2_cut_136.png`: although CFG/negative conditioning was active, the positive scene lock still requested a wagon token and generated a wheeled cart.
  - Logic fix: the CH2 return-to-chief scene now contains only one hand-hidden chief, one low sealed kurgan, and empty grass. Wagon/cart/wheel/herd tokens were removed from positive material/evidence and added to the locked negative. No output image was edited.
  - Accepted `ch2_cut_136_v2.png`: no wagon, cart, wheel, animal, or token; one chief, one low mound, open grass.
  - Accepted `ch2_cut_1.png`: two modern archaeologists use small natural brush/trowel grips; no forced open palm or extra limb.
  - Rejected `ch3_cut_102.png`: hands were natural, but an abstract jagged black brush frame surrounded the scene.
  - Logic fix: all Z character/object/landscape style locks now require every black mass to belong to depicted scene content and forbid abstract perimeter slashes, spikes, wedges, arrow shapes, torn-paper edges, vignettes, panel borders, and enclosing ink frames. Matching negative terms were added. No output image was edited.
  - Accepted `ch3_cut_102_v2.png`: no abstract black perimeter; four women use small closed loom grips with no forced palm.
- Latest backend: PID `15532`, port `8000`; `/api/health` returned `status=ok`, version `V3.2`, ComfyUI URL `http://127.0.0.1:8188`.
- ComfyUI remains PID `20484`, port `8188`; its live `UNETLoader` model list contains both `z_image_bf16.safetensors` and `z_image_turbo_bf16.safetensors`.
- CH2 EP02 was started through the authenticated official queue API after confirming no task was running:
  - Queue item: `66127fe7`.
  - Task: `d095a187`.
  - Project: `V3_CH2_EP2_260720150248078b10`.
  - Result directory: `D:\long_result\CH2\Scartography\EP.2.260720150248078b10`.
  - The created project was verified to use `comfyui-z-image-base` and `scene_contract_v2`.
  - Last verified state at this handoff update: `running`, Step 3 audio, progress `5.9%`, no error.
- CH3 EP07 queue item `clean-rebuild-ch3-ep007-20260720` is pending at global queue index 0. It is the next persisted queue item after CH2 EP02 and must inherit `comfyui-z-image-base` from template `7d8b63e5` when prepared.
- Manual image QA is mandatory before video/render/upload. Both source templates now have `image_qa_required_before_video=true` and `image_qa_approved_before_video=false`. CH2 synchronizes this live source config at the start of Step 4 and must pause at `image_qa_pending` after all 150 images. Do not approve or resume Step 5 until direct full-resolution/contact-sheet review is complete. CH3 inherits the same hold when it starts.
- The old public YouTube videos remain preserved. They are not authorized for remote deletion. Verify the new uploads completely before requesting any remote replacement/deletion decision.

## 2026-07-20 13:30 KST - forced-palm fix verified; Turbo historical-control blocker

- The user reported hands that looked forcibly opened. The hand-detailer prompt was changed to preserve each detected hand's existing gesture, scale, orientation, depth, and object contact. It may repair local anatomy but may not turn a closed, curled, gripping, foreshortened, or partly hidden hand into an open palm or spread all digits for display.
- Direct current-logic samples confirmed the hand fix:
  - `D:\long_result\_qa_trials\ch2_ep2_hand_pose_v2_20260720\cut_1.png`: two archaeologists use curled brush/trowel grips; no palm faces the camera and no forced digit fan appears.
  - `D:\long_result\_qa_trials\ch2_ep2_hand_pose_v2_20260720\ch3_cut_102.png`: exactly four women grip their looms naturally; no extra limb or forced open palm.
  - `D:\long_result\_qa_trials\ch2_ep2_hand_pose_v2_20260720\ch3_cut_129.png`: two hands hold hair/topknot naturally; no palm display or extra arm.
- The Z workflows now generate a 64-by-48-pixel larger safety canvas, run the requested hand detailer, and deterministically center-crop 32 pixels horizontally and 24 pixels vertically to the requested output size. This removes the icon-sized corner marks that survived prompt-only controls. The generated image is not manually edited.
- Z object and landscape style locks no longer seed the literal word `signature` in the positive prompt. Object-only and landscape-only scenes now have separate unoccupied rendering locks.
- The failed production retry `e50bea91` / `V3_CH2_EP2_260720125551fcdbe5` was cancelled after direct review found a lower-right artist-stamp mark in cut 51 and historically invalid handled tools. Official requeue cleanup deleted 51,765,486 bytes and created CH2 queue item `66127fe7`.
- Additional direct QA exposed a separate historical-control blocker:
  - `cut_136.png` produced spoked wheels, a wheeled hut, and a spoked-wheel cart even though the prompt required solid disk wheels and the negative listed spoked wheels.
  - `cut_17.png` produced handled tools and a hilted blade from an object-only archaeological prompt.
- Confirmed from the official Tongyi-MAI model cards and the local files:
  - Z-Image Turbo is the installed `C:\models\diffusion_models\z_image_turbo_bf16.safetensors` checkpoint, 8-step, CFG disabled, negative prompting unavailable.
  - Z-Image Base supports CFG, 28-50 steps, and negative prompting, but it is not installed on this PC.
- Consequently, the forced-palm defect is fixed, but CH2 EP02 and CH3 EP07 production remains stopped because the user's mandatory historical-accuracy requirement cannot be guaranteed by the installed Turbo checkpoint on complex transport/tool scenes. Do not start queue item `66127fe7` or CH3 item `clean-rebuild-ch3-ep007-20260720` until the user authorizes either installation/use of Z-Image Base or a different explicit fallback strategy.
- Current focused verification:
  - Z workflow/style/safe-edge tests: 5 passed.
  - hand anatomy, Z scene-contract registration, and CH2 hierarchy prompt tests: 3 passed.
  - Python syntax and both Z workflow JSON files validated.
- Backend was restarted after the latest safe-edge/style source edits and is now PID `21672` on port 8000. `/api/health` returned `status=ok`, version `V3.2`. No production queue item was started.

## 2026-07-20 12:56 KST - Z-Image hand-pose root cause, direct QA, and current retry

- Root cause of the forced-open-palm images was confirmed in code: `supports_scene_contract_v2_model()` did not include `comfyui-z-image-*`, so Z-Image Turbo bypassed the compact scene-contract compiler and received the huge legacy prompt containing the old hand-count display lock. Production Z prompts had expanded to roughly 20,000-57,000 characters.
- `backend/app/services/image/prompt_compiler.py` now treats `comfyui-z-image-*` as `scene_contract_v2` capable. The current real CH2 prompt is about 2,000 characters before the Z style prefix instead of tens of thousands.
- The hand prompt no longer tells the model to display five visible digits. Natural curled, gripping, foreshortened, overlapped, sleeve-covered, occluded, and cropped poses are allowed. It explicitly forbids opening or spreading a hand merely to show digits.
- Z-Image hand refinement preserves the existing gesture and may not convert a closed, curled, gripping, foreshortened, or occluded hand into an open palm. The hand-refine negative contains forced open palm, palm facing camera, five extended fingers, and all fingers fully spread.
- Z-Image negative prompting now includes open palm, spread fingers, splayed fingers, and common malformed/duplicated hand terms. The automatic post-generation rejection detector remains removed; the `hand_yolov8s` inpaint/detailer remains because it is the explicitly requested hand refinement workflow.
- A Z-specific style front lock was added for the supplied `Priest` reference direction: irregular heavy black outer contours, scratchy variable-width dip-pen interiors, dense cross-hatching, dry-brush abrasion, soot-black shadow masses, aged print stock, and restrained dirty-ivory/tobacco/rust/burgundy/black washes.
- The word `horror-western` was removed after direct QA proved that it imported cowboy hats, dusters, belts, and modern Western clothing into unrelated historical scenes. Cowboy/frontier clothing is now explicitly negative.
- Object-only scenes use a separate Z style lock that does not mention adult faces and explicitly forbids people, faces, hands, bodies, costumes, hats, weapon belts, and silhouettes.
- Both Z style locks require all four corners to remain uninterrupted scene material with no signature, stamp, seal, emblem, monogram, initials, logo, or compact mark. Matching negative terms include corner emblems, artist stamps, and monograms.
- CH2 EP02 cut 1 was simplified to a conservative, historically valid present-day German excavation: exactly two archaeologists, one small unlined Corded Ware grave, one partly buried side-profile skull, one curled brush grip, one trowel grip, and no hand touching bone. This removed the forced palms, duplicated archaeologists, duplicated skulls, timber shoring, and map imagery seen during failed iterations.
- CH2 object locks were made less count-fragile where the narration does not require an exact number. Cut 84 now uses several source/alliance disks instead of forcing 3+6. Cut 34 now requires one rich grave against a sparse group of plain graves and uses two flat unhafted copper sheets rather than weapon words that produced swords and hafted axes. Cut 150 uses three separated material groups, clay rut impressions, an earthen mound, and loose ancestry tokens instead of a wheel, chest, skull, or tile grid.
- Directly approved standalone samples from current logic:
  - `D:\long_result\_qa_trials\ch2_ep2_style_era_fix_v8_20260720\cut_1.png`: two modern archaeologists, natural curled tool grips, no forced open palm or added limb.
  - `D:\long_result\_qa_trials\ch2_ep2_preflight_fix_v1_20260720\cut_18.png`: no signature/corner mark after the four-corner lock.
  - `D:\long_result\_qa_trials\ch2_ep2_preflight_fix_v1_20260720\cut_34.png`: no hafted sword or axe; flat copper sheet forms and closed shroud only.
- Failed production retry `90646419` / `V3_CH2_EP2_2607201231510705eb` was stopped during direct preflight after cut 18 showed a corner signature and cut 34 showed hafted weapons. Official requeue cleanup deleted 44,720,854 bytes, removed the project DB record and exact result directory, and created queue item `79de51b4`.
- Current backend is PID `21736`, listening on port 8000 with the latest code. ComfyUI remains PID `20484` on port 8188.
- Current clean CH2 retry is task `e50bea91`, project `V3_CH2_EP2_260720125551fcdbe5`, result directory `D:\long_result\CH2\Scartography\EP.2.260720125551fcdbe5`. At this update it is on Step 3 audio generation, `15/150`.
- CH3 EP07 has not started yet. Its queue item remains `clean-rebuild-ch3-ep007-20260720` at the head of channel 3.
- Relevant targeted tests currently pass, including the Z workflow/style tests, the hand-refine anatomy test, the Z scene-contract registration test, the CH2 cut-1 migration-grave lock, and the CH2 hierarchy/object evidence test. Do not claim the entire `test_image_prompt_compiler` module passes; a broad run earlier contained many unrelated existing failures.

## 2026-07-20 10:55 KST - non-negotiable visual acceptance rules

- The user explicitly requires mature dark historical manhwa matching the supplied `Priest` references: rough variable-width dip-pen lines, strong black silhouettes, dense hatching, aged muted sepia/rust/soot palette, and an adult hard-boiled tone.
- Bright, clean, lightweight generic cartoon/anime rendering is a style failure.
- Historical accuracy is mandatory per cut. Clothing, weapons, architecture, transport, tools, materials, landscape, and social setting must match the stated period and place.
- Automatic post-generation detector/retry/quarantine remains removed. The assistant directly reviews contact sheets and original images for anatomy, text/signature artifacts, style, and historical accuracy.
- A 2026-07-20 CH2 EP2 preflight produced 11 invalid images because the running backend still held stale prompt-composition code. Stored Z-Image positive prompts had expanded to about 20,000-57,000 characters and yielded repeated later East Asian gates, tiled roofs, paper-map/notice-board imagery, and a bright lightweight style. The run was cancelled, task `6cd365c3` and project `V3_CH2_EP2_26072010290273c6f2` were deleted, and 59,043,507 bytes of failed local output were removed. Queue item `7e6cb2b2` was created for a clean retry.
- Backend was restarted as PID `22148` so current compact prompt logic is loaded. Before full production, generate and directly approve a new preflight for both style and historical accuracy.

## Mandatory startup order

1. Read `docs/SESSION_PROTOCOL.md` in full.
2. Read `SESSION_HANDOFF.md`.
3. Read this document in full.
4. Read `docs/handoffs/SESSION_QA_V3_2026-05-08.md` in full.
5. Read `CONTEXT.md`.
6. Verify current files, DB, task JSON, result folders, backend, and ComfyUI before acting.

## User instruction in force

- Save the current changes and operational state in the handoff.
- Rebuild CH2 EP02 and CH3 EP07 from a clean state.
- Delete every local work result and generated-project record for those two channel/episode pairs before the clean rebuild.
- Generate, manually review, render, and upload the rebuilt episodes.
- Historical accuracy is mandatory for every generated image: exact era, region, culture, clothing, hair, tools, weapons, buildings, transport, ritual objects, landscape, and available materials must match the scene.
- Do not directly edit a generated image. Fix the prompt/workflow/logic and regenerate the affected cut.
- The old public YouTube uploads are not yet deleted. Remote deletion is irreversible and was not explicitly separated from the local clean-rebuild instruction. Preserve them until the new uploads are complete and the user explicitly confirms remote deletion/replacement.

## Image pipeline changes completed in this session

- Z-Image Turbo hand refinement is connected in both workflows:
  - `backend/workflows/comfyui/z_image_turbo_text2img.json`
  - `backend/workflows/comfyui/z_image_turbo_text2img_ref.json`
- The workflow route is `hand_yolov8s` -> `BboxDetectorSEGS` -> `DetailerForEach` -> `SaveImage`.
- `DetailerForEach` uses `force_inpaint=true`, `denoise=0.22`, and `feather=48`.
- The mature historical cartoon style was applied across Z-Image Turbo, Flux2 Klein 4B, and SDXL prompt routes:
  - variable-width ink contours;
  - rough dip-pen and cross-hatching texture;
  - aged print grain;
  - muted sepia, rust, burgundy, soot, and watercolor/gouache palette;
  - adult hard-boiled historical graphic-novel tone.
- A concise female historical-character route was added so female costume scenes receive the requested less-constricted silhouette without inheriting unrelated long historical prompt branches.
- The generic `linen + skin` trigger was narrowed so ordinary period linen does not falsely activate the wet-linen medical close-up guard.
- Automatic post-generation reject/retry/quarantine detector execution was removed from `ComfyUIImageService.generate` after the user explicitly ordered removal of the detector itself.
- The hand detector inside the Z-Image workflow remains. It is the requested hand inpaint/detailer and is not the removed post-generation rejection detector.
- Production image QA is now direct/manual. No generated image may be considered accepted solely from a detector result.

## Verification completed for the image changes

- Latest focused test run: 15 tests passed.
- Earlier combined focused run: 18 tests passed.
- `git diff --check` passed on the relevant tracked files at that point.
- Selected female Z-Image samples:
  - `D:\long_result\_qa_trials\zimage_dark_manhwa_female_20260720_v4`
  - selected: 01, 02, 03, 04, 06
  - candidate 05 was rejected for a small signature-like lower-right mark; it was not edited and replacement 06 was regenerated.

## Current source studios

### CH2

- Source/template project: `e6619f7e`
- Studio title: `딸깍폼-Scartography`
- Live image model: `comfyui-z-image-turbo`
- Language: English
- YouTube channel: 2
- Privacy: public
- Registered script:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts\EP002.json`
- Episode topic: `Yamnaya Migration Spreads Indo-European Languages`
- Episode code: `EP002`
- Series: `Scartography`

### CH3

- Source/template project: `7d8b63e5`
- Studio title: `CH3 딸깍폼-일본역사`
- Live image model: `comfyui-z-image-turbo`
- Language: Japanese
- YouTube channel: 3
- Privacy: public
- Episode topic: `죽은 여신의 시신에서 피어난 생명`
- Episode code: `CH3_C1_EP007`
- Series: `제1장 신들의 시대와 한반도의 그림자`

## Existing CH2 EP02 records that must be removed before the clean run

1. Completed task `c97e4876`
   - Project: `V3_CH2_EP2_260717202755d42fd8`
   - Result: `D:\long_result\CH2\Scartography\EP.2.260717202755d42fd8`
   - Empty compatibility directory: `D:\long_result\CH2\EP.2.260717202755d42fd8`
   - Old public main URL: `https://youtube.com/watch?v=eGW12Gg_LxY`
2. Cancelled task `3b009cab`
   - Project: `V3_CH2_EP2_260719150555ee93c4`
   - Result: `D:\long_result\CH2\Scartography\EP.2.260719150555ee93c4`
3. Paused image-QA task `88cdf886`
   - Project: `V3_CH2_EP2_2607192055343dcda3`
   - Result: `D:\long_result\CH2\Scartography\EP.2.2607192055343dcda3`
   - State at inspection: script 150, audio 150, images 150, video 0; Z-Image Turbo; not approved.

## Existing CH3 EP07 records that must be removed before the clean run

1. Completed task `b05c1dbd`
   - Project: `V3_CH3_EP7_260717202757ed739b`
   - Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.260717202757ed739b`
   - Empty compatibility directory: `D:\long_result\CH3\EP.7.260717202757ed739b`
   - Old public main URL: `https://youtube.com/watch?v=VpsKhtWx3Kw`
2. Cancelled task `fd5ba483`
   - Project: `V3_CH3_EP7_260719150556ac91cf`
   - Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.260719150556ac91cf`
3. Queued/restart-recovery task `554bfc9a`
   - Project: `V3_CH3_EP7_26071920435209516e`
   - Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.7.26071920435209516e`
   - Task JSON state at inspection: queued, step 2 pending, Z-Image Turbo.
   - Queue JSON contained this item with stale `status=running`; normalize it by deleting the task/item before the clean prepare.

## Verified runtime and storage facts

- Repository and DB: `C:\Users\Ai_M9\Desktop\longtube`
- DB: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.db`
- DATA_DIR: `C:\Users\Ai_M9\Desktop\longsult`
- Result archive: `D:\long_result`
- Backend `127.0.0.1:8000`: listening; `/api/health` returned V3.2 OK.
- ComfyUI `127.0.0.1:8188`: listening.
- Frontend `127.0.0.1:3000`: listening.
- Worktree is heavily dirty. Never reset, checkout, broad-stage, or clean unrelated files.

## Clean-rebuild execution requirements

1. Confirm that no OneClick runner or image generation process is active for the six task IDs above.
2. Delete only those six OneClick task records, their six generated Project/Cut/API-log records, their exact result directories, and the two empty compatibility directories.
3. Remove only queue items for CH2 EP02 and CH3 EP07, then prepare exactly one fresh queue item per episode from the registered/current source data.
4. Start from Step 2. Do not reuse script, audio, image, video, render, thumbnail, caption, or upload files from any old run.
5. Each step must read the current source studio config at step start.
6. Validate script and image prompts for historical accuracy before image generation.
7. Manually review contact sheets and full-resolution problem crops. Check fingers, hands, limbs, faces, repeated bodies, period clothing, period objects, architecture, geography, readable text, watermarks, and signature-like marks.
8. If a cut fails, modify logic/prompt and regenerate that cut. Never paint over or directly modify the image.
9. Approve image QA only after direct inspection, then create videos, render, captions, thumbnail, main upload, and Shorts.
10. Verify final MP4 decode locally and verify YouTube public/processing/caption state through authoritative API responses before reporting completion.

## Historical accuracy locks for these episodes

- CH2 EP02: every cut must be anchored to the Yamnaya / Pontic-Caspian steppe context described by the registered script. Do not allow classical, Roman, medieval, early-modern, or modern clothing, weapons, writing, buildings, carts, saddles, armor, borders, flags, paper, or machinery.
- CH3 EP07: this is a Japanese mythic-origin narrative about Uke Mochi, Tsukuyomi, food grains, and silkworms. Keep the visual world consistent with the episode's mythic ancient-Japanese frame. Do not introduce later samurai armor, Edo clothing, modern shrine fixtures, paper signage, printed text, modern agriculture, or Western objects.
- When the script does not supply a firm date or material-culture fact, do not invent a precise historical artifact. Use a conservative scene that is compatible with the stated era and culture.

## Current deletion boundary

- Authorized: generated local files and generated Project/Cut/API-log/task/queue records for CH2 EP02 and CH3 EP07.
- Not authorized without an explicit follow-up: deleting the already-public old YouTube main videos or Shorts.
- Preserve source studio projects, prepared scripts, channel OAuth, channel configuration, reference assets, shared interludes, and unrelated episodes.
