# CH1 백제사 EP01 제작 완료 — 2026-07-15

## Final State

- Task ID: `a888810c`
- Project ID: `V3_CH1_EP1_2607150045456ce0aa`
- Episode code/id: `백제사-EP01`
- Status: `completed`
- Progress: 100%
- Steps 2-7: 모두 `completed`
- Error: 없음
- Start: `2026-07-15T01:46:59Z`
- Finish/upload completion: `2026-07-15T07:24:36Z`
- ComfyUI queue at save: running 0, pending 0

이 에피소드는 완료됐다. 다음 세션에서 재생성, 재렌더, 재업로드하지 않는다.

## Identity And Paths

- Title: `백제-EP.01 왕위에서 밀려난 온조, 형의 몰락 위에 세운 백제`
- Result root: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa`
- Images: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\images`
- Final video: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\output\final_with_subtitles.mp4`
- Final video size: 492,017,566 bytes
- Thumbnail: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\output\thumbnail.png`
- Shorts manifest: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\output\shorts\shorts_uploads.json`

## QA And Render Verification

- Original images: 150 PNG
- Prompt sidecars: 150 `.prompt.json`
- Cut videos: 150 MP4
- All original images verified at 1280x720.
- All sidecar commit records verified.
- Full contact-sheet visual QA completed.
- Failed images were not retouched. Detection/prompt logic was corrected and affected cuts were regenerated.
- Final late fixes included cuts 10, 42, 70, 109, 148, and 149.
- Final video includes opening, ending, BGM mix, and cut-level burned subtitles.
- Image QA approval was recorded before video generation.
- Thumbnail background and overlay were regenerated for the upload run; both QA JSON files record `passed: true`.

## Upload Verification

Main video:

- URL: `https://youtube.com/watch?v=B05sybOP6Fs`
- Video ID: `B05sybOP6Fs`
- Privacy: public
- Playlist: `위대한 백제`
- Playlist ID: `PLCynqmYs90mw`
- Upload execution result recorded the main playlist link with `already=False`.

Shorts:

1. `https://youtube.com/watch?v=PNKZD_lQyT8`
2. `https://youtube.com/watch?v=hRUL92wwpsQ`
3. `https://youtube.com/watch?v=pFTQnA4G950`
4. `https://youtube.com/watch?v=UObCsp3_M7w`

`shorts_uploads.json` records `studio_verified: true` and `metadata_pending: false` for all four. It records `processing_verified: false`; do not reinterpret that field as a completed remote processing check.

## Saved Pipeline Changes

Primary changed files:

- `backend/app/services/title_utils.py`
- `backend/app/services/oneclick_service.py`
- `backend/app/services/image/prompt_compiler.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/tests/test_youtube_metadata.py`
- `backend/tests/test_oneclick_stability.py`
- `backend/tests/test_image_prompt_compiler.py`

Applied behavior:

- CH1 series episode title prefix generation now supports `백제-EP.01` format.
- Run overrides are applied last, and upload runs can force thumbnail regeneration.
- The global history-image compiler gives the approved hard-boiled, rough masculine visual direction higher priority.
- Baekje EP01 scene contracts, historical-anachronism negatives, corner credit/logo/text guards, dark-frame handling, and nonhuman-relief false-positive guards were added or tightened.
- Failed detector retries remain bounded; failed outputs are regenerated only after logic correction.
- Exact scene locks were added where required, including the Pungnap low earthen-wall landscape and the closing clay-record relief.

## Verification Scope

- Relevant focused regression tests passed.
- Latest Baekje detector/scene-lock tests passed.
- Python compile checks passed.
- The full repository test suite was not run; do not report it as passed.
- The existing dirty worktree was preserved. No reset, checkout, broad stage, commit, or push was performed.

## Nonblocking Record

- A cached BGM copy logged `WinError 32` because the cache file was locked. BGM mixing had already completed, the final render exists, and the upload completed.
- Main upload completion was recorded without a separate YouTube processing monitor pass.

## Post-completion Thumbnail Correction

- The prepared script already specified `형이 죽자, 백제는 완성됐다`.
- Root cause: `_strong_korean_thumbnail_overlay()` treated every occurrence of `죽` as a generic death hook and replaced the factual cause-and-result phrase with `죽음의 순간`.
- Logic fix: short explicit Korean death-cause/result hooks now preserve both clauses instead of collapsing to the generic death label.
- Regression test added: `test_korean_thumbnail_overlay_preserves_short_causal_death_hook`.
- Focused Korean/English overlay tests passed; Python compile check passed.
- Regenerated overlay: `형이 죽자\n백제는 완성됐다`.
- Regenerated file: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\output\thumbnail.png`.
- Original-size visual check: 1280x720, exact Korean text, no missing characters, no face obstruction.
- YouTube `thumbnails.set` succeeded for channel 1 video `B05sybOP6Fs`.
- Remote CDN verification matched the new local thumbnail: correlation `0.999903`, mean absolute pixel difference `2.2674` after YouTube JPEG recompression.

Latest size correction:

- The two-line overlay was verified as too small at 38px.
- Root cause: the fallback face-safe column kept explicit two-line hooks inside 22% of the canvas width, forcing the long second line to shrink.
- Logic fix: short two-line hooks are reflowed to three lines only when face detection falls back, preserving every word while allowing a larger font.
- Final layout: `형이 죽자\n백제는\n완성됐다`, 60px.
- The AI background, wording, colors, and video were not changed.
- Focused tests and compile check passed; final overlay QA passed.
- YouTube thumbnail replacement succeeded for `B05sybOP6Fs`.
- Final remote CDN verification: correlation `0.999925`, mean absolute pixel difference `2.2605`.

## Next Session

Read this file for the completed state, then start only the next explicitly requested task. Do not resume the obsolete cut-29 continuation instructions in `SESSION_HANDOFF_2026-07-15_CH1_BAEKJE_EP01_CONTINUE.md`.
