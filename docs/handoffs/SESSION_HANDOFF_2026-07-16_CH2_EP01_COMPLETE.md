# CH2 Scartography EP001 Complete

## Final state

- Task: `1f43c3f6`
- Project: `V3_CH2_EP1_260715210908673297`
- Result: `D:\long_result\CH2\Scartography\EP.1.260715210908673297`
- Registered script: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts\EP001.json`
- Main video: `https://youtube.com/watch?v=XyKuCORfH0I`
- YouTube: public, HD, processing succeeded, 19m38s
- Title: `Manu, Yemo, and the Proto-Indo-European Creation Myth: The Shocking Turn EP.01`
- Thumbnail copy: `BROTHER'S DEATH / CREATED WORLD`
- Captions: English standard track serving; YouTube ASR track also present
- Localizations: en, de, es, fr
- Shorts: `u-YoCfIFyWY`, `bDTCtW3ebcI`, `CewbHM6b_1A`, `8qoVc_-YWp0`; all public HD processed

## Verified production facts

- 150/150 images and prompt sidecars exist at 1280x720.
- Registered and runtime scripts both contain 150 cuts.
- Narration, narration_en, source, source_text, and source_cue match for all 150 cuts.
- No GPT script generation was used; `prepared_source=true` remains set.
- Final video decoded successfully with FFmpeg.
- Opening, four intermissions, ending, BGM, and four Shorts were rendered.
- The remote YouTube max-resolution thumbnail matches the corrected local thumbnail.

## Saved logic changes

- CH2 literal scene locks and scene-scoped image QA exceptions are in `backend/app/services/image/prompt_compiler.py` and `backend/app/services/image/comfyui_service.py`.
- Registered thumbnail copy now takes priority; fallback text width is 40%; cartoon face-safe geometry was corrected in `backend/app/services/thumbnail_service.py`.
- YouTube caption listing and standard SRT upload are implemented in `backend/app/services/youtube_service.py` and `backend/app/services/oneclick_service.py`.
- ASR captions do not satisfy the registered-script caption check.
- Targeted regression suite: 20 tests passed on 2026-07-16.

## Workspace caution

The worktree already contains many unrelated user changes and QA artifacts. Do not reset, checkout, or broadly stage it.
