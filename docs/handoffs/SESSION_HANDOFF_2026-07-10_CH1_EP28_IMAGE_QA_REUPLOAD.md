# Session Handoff 2026-07-10 - CH1 EP28 Image QA / Reupload

## Project

- Channel: CH1 `고구려`
- Project id: `V3_CH1_EP28_2607091629320ef297`
- Result directory: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297`
- Status in DB: `completed`
- Image model used: `comfyui-flux2-klein-4b`
- Video model used for regenerated cuts: `ffmpeg-static`

## Upload Facts

- Main public URL: `https://youtube.com/watch?v=rfEDsoZCeII`
- Main title: `"물과 고기처럼 화합하라" 권력의 분열 EP.28`
- Main thumbnail: uploaded
- Main captions: Korean captions uploaded
- Old main upload existed before reupload: `https://youtube.com/watch?v=bwU1iDT_IM4`
- The old main upload was not deleted. YouTube video files cannot be replaced in-place.

## Shorts Uploads

- `https://youtube.com/watch?v=vP63BMArrZw`
- `https://youtube.com/watch?v=X5Tqv0W2188`
- `https://youtube.com/watch?v=18HIm7BqnQ0`
- `https://youtube.com/watch?v=ryRCrRjIUP8`
- Shorts playlist id: `PL6emUPhVGAqqFRkp6vL4HIo-NtYbDHmiY`
- Public access confirmed through YouTube oEmbed for all five uploaded videos.

## Regenerated Cuts

- Cut 7
  - Problem: outdoor courtyard prompt inherited interior rafters/ceiling wording.
  - Fix: outdoor scenes now avoid forced rafters and use scene-edge material.
  - Regenerated image and cut video.
- Cut 9
  - Problem: `no skyline`, `no courtyard view` still triggered exterior skyline logic.
  - Fix: negated skyline/courtyard clauses are stripped before exterior skyline detection.
  - Regenerated image and cut video.
- Cut 11
  - Problem: exactly three sons was not locked strongly enough.
  - Fix: exactly-three negative lock added for four people/four sons/background extras.
  - Regenerated image and cut video.
- Cut 14
  - Problem: `dagger` alone triggered tabletop/dried-blood surface detail.
  - Fix: surface detection no longer treats dagger-only scenes as tabletop scenes.
  - Regenerated image and cut video.

## Local Outputs

- Final video: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297\output\final_with_subtitles.mp4`
- Body merge: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297\output\merged.mp4`
- Cut-video merge: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297\videos\merged.mp4`
- Final QA sheet for the four fixed cuts: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297\images\qa_cuts_7_9_11_14_final_checked3.png`
- Shorts upload record: `D:\long_result\CH1\고구려\EP.28.2607091629320ef297\output\shorts\shorts_uploads.json`

## DB / Metadata Fixes

- `project.youtube_url` restored to `https://youtube.com/watch?v=rfEDsoZCeII`.
- `project.config.youtube_url` restored to `https://youtube.com/watch?v=rfEDsoZCeII`.
- `project.config.youtube_video_id` set to `rfEDsoZCeII`.
- `project.config.youtube_main_upload_result` added for the main upload.
- `project.config.youtube_upload_result` now separates `main` and `shorts`.
- Cuts 7, 9, 11, and 14 had temporary `video_model='ai'` metadata from the direct regeneration script; corrected to `ffmpeg-static`.

## Code Changes From This Work

- `backend/app/services/image/prompt_builder.py`
  - Added stricter exactly-three-person negative prompt handling.
  - Updated preindustrial lamp/upper-frame language so outdoor scenes do not receive interior rafters.
- `backend/app/services/image/comfyui_service.py`
  - Added skyline negation handling for `no skyline` and `no courtyard view`.
  - Added stale `Ancient skyline detail` stripping when skyline is not appropriate.
  - Tightened surface-detail routing for object-only stone supports, interior halls/sickrooms, and dagger-only scenes.
  - Added top-caption retry logic that uses outdoor upper-edge material for courtyard/outdoor scenes.
- `backend/workflows/comfyui/flux2_klein_4b_text2img.json`
  - Hand/body refine nodes are present in the template but disconnected from `SaveImage`.
  - Reason: bbox/detailer inpaint produced visible rectangular paste artifacts during production QA.
- `backend/tests/test_comfyui_flux2_hand_refine_workflow.py`
  - Verifies the 4B workflow keeps refine nodes disconnected from output.
- `backend/tests/test_image_prompt_guards.py`
  - Existing and added guard coverage includes skyline/surface/object/person prompt behavior.

## Verification

- YouTube public access confirmed:
  - `rfEDsoZCeII`
  - `vP63BMArrZw`
  - `X5Tqv0W2188`
  - `18HIm7BqnQ0`
  - `ryRCrRjIUP8`
- DB final check:
  - Project status: `completed`
  - `project.youtube_url`: `https://youtube.com/watch?v=rfEDsoZCeII`
  - Cuts 7, 9, 11, 14: `completed`, `ffmpeg-static`
- Focused unittest passed:
  - `ImagePromptGuardTests.test_flux2_klein_4b_md_contract_does_not_push_dark_hall_to_exterior_skyline`
  - `ImagePromptGuardTests.test_flux2_klein_md_surface_uses_local_scene_over_global_workbench`
  - `Flux2Klein4BSafeWorkflowTest.test_flux2_klein_4b_workflow_keeps_refine_nodes_disconnected_from_output`
- `pytest` is not installed in the current Python environments.
- Full unittest attempt timed out at 124 seconds.

## Required Next Rules

1. Do not directly edit generated image or video outputs.
2. If a generated output has a problem, fix logic and regenerate the affected cut or next output.
3. For image QA, inspect the full cut image enlarged, not cropped-only fragments.
4. Check anatomy and physics explicitly: hands, fingers, arms, legs, head count, body attachment, animal legs, scene continuity, and dialogue fit.
5. Do not use broad `git add -A`; this worktree contains many QA/generated files.
