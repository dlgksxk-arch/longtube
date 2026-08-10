# LongTube Session Handoff - 2026-07-08 CH3 V3.2 TTS/Subtitles/Upload

이 문서는 새 세션이 현재 상태를 그대로 이어받기 위한 상세 인수인계입니다.

## Must Follow

- 추측하지 말고 실제 파일, 로그, DB, API 응답 기준으로 판단한다.
- 생성 결과물에 문제가 있으면 결과물 파일을 직접 수정하지 않는다.
- 문제를 해결하는 로직을 수정한 뒤 다음 생성물 또는 해당 컷 재생성에 적용한다.
- 일본어 채널의 제목, 설명, 태그, 재생목록명 등 공개 메타데이터는 일본어로 넣는다.
- dirty worktree에서 사용자 또는 이전 작업 변경을 되돌리지 않는다.
- `git add -A`를 쓰지 않는다. 저장소에 QA/temp/output 계열 untracked 파일이 매우 많다.

## Current Repo State

- Workspace: `C:\Users\Ai_M9\Desktop\longtube`
- Branch: `main`
- HEAD: `4b025cb`
- Current backend version reported by API: `V3.2`
- Current tracked code diff before this handoff document:
  - 10 files changed
  - 367 insertions
  - 106 deletions
- Current tracked code files modified:
  - `backend/app/config.py`
  - `backend/app/routers/interlude.py`
  - `backend/app/routers/projects.py`
  - `backend/app/routers/subtitle.py`
  - `backend/app/routers/video.py`
  - `backend/app/services/oneclick_service.py`
  - `backend/app/services/subtitle_service.py`
  - `backend/app/services/video/ffmpeg_service.py`
  - `backend/app/tasks/pipeline_tasks.py`
  - `backend/tests/test_oneclick_stability.py`
- This handoff adds/updates documentation files only. It does not commit.

## Runtime State Verified

- Backend is running on port `8000`.
- Backend process PID: `21036`
- Health check result:
  - URL: `http://127.0.0.1:8000/api/health`
  - Response: `{"status":"ok","version":"V3.2","comfyui_base_url":"http://127.0.0.1:8188"}`
- Backend restart logs:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\uvicorn_after_fullcut_subtitle_20260708.out.log`
  - `C:\Users\Ai_M9\Desktop\longsult\_system\uvicorn_after_fullcut_subtitle_20260708.err.log`
  - PID file: `C:\Users\Ai_M9\Desktop\longsult\_system\uvicorn_after_fullcut_subtitle_20260708.pid`

Backend restart command used:

```powershell
$env:PYTHONPATH = 'C:\Users\Ai_M9\Desktop\longtube\backend'
python -X utf8 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Active CH3 EP1 Facts

- Channel: CH3 Japanese history channel.
- Active project id: `V3_CH3_EP1_260707150546824d6c`
- Active task id: `04d7fb22`
- Result directory:
  - `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.1.260707150546824d6c`
- Final video path:
  - `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.1.260707150546824d6c\output\final_with_subtitles.mp4`
- Thumbnail path:
  - `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.1.260707150546824d6c\output\thumbnail.png`

## YouTube Upload Facts

The previous upload attempt used Korean metadata by mistake. The user deleted it. The corrected upload was done with Japanese metadata.

- Main video:
  - `https://youtube.com/watch?v=ftKnP25XVz0`
- Shorts:
  - `https://youtube.com/watch?v=WPX1liRBhv4`
  - `https://youtube.com/watch?v=1um5UX1nC6s`
  - `https://youtube.com/watch?v=UjAqUXSYKRk`
  - `https://youtube.com/watch?v=f7ZYvH5j9ec`
- Playlist title:
  - `神々の時代と日本誕生の謎`
- Playlist id recorded in session context:
  - `PLA-xq-0HRzyo`
- YouTube channel verified in session context:
  - `闇解き日本史`
- Privacy used in session context:
  - `private`
- Language:
  - `ja`
- Removed old playlist items:
  - `LBZkGYjbAeo`
  - `llBxvomA_a4`

## Source Data Facts From This Session

- User provided CH3 chapter script workbook:
  - `Z:\HDD2\longtube\CH3 일본역사\제1장\제1장_대본.xlsx`
- User requested full review of typos, wrong parts, dialogue length, and image prompt suitability.
- User requested creating a corrected copy, not editing the original directly.
- User later provided or referenced corrected file:
  - `제1장_대본_수정본_20260707`
- User stated episode 32 was manually corrected there and requested it be applied.
- User provided cuesheet CSV:
  - `Z:\HDD2\longtube\CH3 일본역사\제1장\#제1장 신들의 시대와 한반도의 그림자 (40편).csv`
- User requested deleting remaining CH3 queued episodes and registering this cuesheet.
- User asked why there were 39 items; do not infer the reason without checking DB/queue.
- User asked whether subtitles can use original Japanese text while TTS uses hiragana reading. The intended policy is: use this method only for the Japanese channel.

## Japanese Script Corrections Requested By User

These are content-level fixes the user explicitly listed. They are not all represented in the current code diff.

- `予泉醜女` should be corrected to `黄泉醜女` or `予母都志許売` lineage.
- `八つ` hiragana written as `やつ つ` should be `やっつ`.
- `男神` read as `おとかみ` is unnatural; use `おがみ`, `おのかみ`, or change source to `男の神`.
- `敷葉工法` reading should be unified as `しきはこうほう`.
- For Japanese audience tone, prefer:
  - `朝鮮半島`
  - `古代朝鮮半島`
  - `百済・新羅・加耶`
  over `韓半島`, `古代韓国`.
- Soften risky terms such as:
  - `原住民`
  - `外国人`
  - `近代化`
  - `国家主義`
  - `乗っ取った`
- Next-episode previews were reported as mismatched in:
  - EP01, EP03, EP04, EP05, EP06, EP07, EP09, EP11, EP12, EP16, EP23, EP30, EP31, EP33.
- Historical year correction:
  - Sabi fall / Baekje capital fall: `660年`
  - Battle of Baekgang / Hakusukinoe: `663年`
  - Do not say `660年、白村江の戦い`.
  - Do not say Baekje collapsed at Baekgang as a direct simplification.
- EP37 Fujiwara no Kamatari claim:
  - Do not state as fact that he was a Baekje aristocrat.
  - If used, frame as `大胆な仮説`, `一説では`, `確定した史実ではありません`.
  - Avoid conspiracy tone such as `外国人が支配`, `乗っ取った`, `壮大な嘘`.
- EP34 `くだらない = 百済ない`:
  - Do not state as established etymology.
  - Use `そういう説があります`.
  - State that the etymology is unconfirmed.

## Main Timing Logic Change

User clarified the target timing:

- Do not force TTS to 4 seconds.
- Let TTS audio keep its natural generated length.
- Cut length should be driven by actual TTS length.
- Minimum cut length remains 4 seconds.
- Cut transition rule:
  - video starts
  - wait 0.5 seconds
  - TTS starts
  - after TTS ends, keep 0.5 seconds
  - then next cut starts

Implemented defaults:

- `backend/app/config.py:278`
  - `CUT_AUDIO_LEAD_IN_SECONDS = 0.5`
- `backend/app/config.py:279`
  - `CUT_AUDIO_TAIL_SECONDS = 0.5`
- `backend/app/config.py:280`
  - `MIN_TTS_DRIVEN_CUT_DURATION = 4.0`
- `backend/app/config.py:395`
  - effective duration is `max(MIN_TTS_DRIVEN_CUT_DURATION, spoken + lead + tail)`.
- `backend/app/routers/projects.py:41`
  - project default `cut_audio_lead_in_sec = 0.5`
- `backend/app/routers/projects.py:42`
  - project default `cut_audio_tail_sec = 0.5`
- `backend/app/services/oneclick_service.py:1466`
  - oneclick main config lead-in set to 0.5
- `backend/app/services/oneclick_service.py:1467`
  - oneclick main config tail set to 0.5
- `backend/app/services/oneclick_service.py:2656`
  - backup project restore config lead-in set to 0.5
- `backend/app/services/oneclick_service.py:2657`
  - backup project restore config tail set to 0.5
- `backend/app/services/oneclick_service.py:2814`
  - orphan V3 restore config lead-in set to 0.5
- `backend/app/services/oneclick_service.py:2815`
  - orphan V3 restore config tail set to 0.5

## Per-Cut TTS Mux Change

Problem observed by user:

- Audio/video sync was wrong.
- TTS needed to be attached immediately after each cut video is generated.

Implemented behavior:

- Video generators are called without audio.
- After each generated cut mp4 exists, TTS is muxed into that cut with the final timeline.
- Audio is delayed by `audio_start_offset`, normally 0.5 seconds.
- TTS is padded/truncated to the target cut duration.
- Video is padded by cloning final frame and trimmed to exact duration.

Core implementation:

- `backend/app/services/video/ffmpeg_service.py:513`
  - added `FFmpegService.mux_cut_audio(...)`.
- `mux_cut_audio` uses:
  - video: `scale`, `pad`, `setsar`, `fps=30`, `format=yuv420p`, `tpad=stop_mode=clone`, `trim`, `setpts`
  - audio: `adelay={offset_ms}:all=1`, `apad`, `atrim=duration`, `asetpts`
  - encode: `libx264`, `aac`, `48000 Hz`

Pipeline application points:

- `backend/app/tasks/pipeline_tasks.py:1973`
  - `svc.generate(... audio_path=None, audio_start_offset=0.0)`
- `backend/app/tasks/pipeline_tasks.py:1984`
  - calls `_CutMuxFFmpeg.mux_cut_audio(...)` immediately after cut generation.
- `backend/app/routers/video.py:462`
  - safe motion generation now receives `audio_path=None`.
- `backend/app/routers/video.py:475`
  - static generation now receives `audio_path=None`.
- `backend/app/routers/video.py:506`
  - primary AI generation now receives `audio_path=None`.
- `backend/app/routers/video.py:826`
  - studio `generate_all_videos` muxes TTS immediately after cut generation.
- `backend/app/routers/video.py:1188`
  - async generation muxes TTS immediately after cut generation.
- `backend/app/routers/video.py:1635`
  - resume generation muxes TTS immediately after cut generation.

## Merge / Render Sync Change

Problem:

- Stream-copy concat could preserve bad timestamps and cause desync.

Implemented:

- Re-encode merges are used for final body/final renders instead of stream copy.
- Long concat path adds timestamp/audio resampling safeguards.

Changed locations:

- `backend/app/services/video/ffmpeg_service.py:315`
  - `merge_videos_reencode(...)`
- `backend/app/services/video/ffmpeg_service.py:353`
  - long concat path adds `-af aresample=async=1:first_pts=0`
- `backend/app/services/video/ffmpeg_service.py:382`
  - short concat path uses `aresample=async=1:first_pts=0,aformat=sample_rates=48000`
- `backend/app/tasks/pipeline_tasks.py:2106`
  - pipeline step 5 merged output now uses `merge_videos_reencode(...)`
- `backend/app/routers/video.py:893`
  - studio all-video merge uses `merge_videos_reencode(...)`
- `backend/app/routers/video.py:1300`
  - async video merge uses `merge_videos_reencode(...)`
- `backend/app/routers/video.py:1749`
  - resume video merge uses `merge_videos_reencode(...)`
- `backend/app/routers/subtitle.py:1191`
  - shorts body source merge uses `merge_videos_reencode(...)`
- `backend/app/routers/subtitle.py:1227`
  - body merge uses `merge_videos_reencode(...)`
- `backend/app/routers/subtitle.py:1308`
  - final sequence merge uses `merge_videos_reencode(...)`
- `backend/app/routers/interlude.py:421`
  - interlude body merge uses `merge_videos_reencode(...)`

## BGM Mix Change

Problem:

- `-shortest` can cut output early when audio tracks differ in length.

Implemented:

- `backend/app/routers/subtitle.py:894`
  - BGM track gets `apad`, `atrim=0:{duration}`, `asetpts=PTS-STARTPTS`
- `backend/app/routers/subtitle.py:908`
  - narration track gets the same duration normalization when source has audio.
- `backend/app/routers/subtitle.py:948`
  - uses `-t {duration}` when duration is known, otherwise falls back to `-shortest`.

## Duration Probe Change

Problem:

- Some systems may not have `ffprobe.exe` located by the old string replacement.

Implemented:

- `backend/app/services/video/ffmpeg_service.py:161`
  - `probe_duration` first tries sibling `ffprobe.exe`.
  - if missing or failing, falls back to parsing `ffmpeg -i` stderr `Duration`.
- `backend/app/tasks/pipeline_tasks.py:1560`
  - `_probe_audio_seconds` now uses the same ffprobe-then-ffmpeg-stderr fallback.
- `backend/app/tasks/pipeline_tasks.py:1594`
  - `_probe_media_seconds` now uses the same fallback.
- `backend/app/routers/video.py:101`
  - router-side `_probe_media_seconds` now uses the same fallback.

## Subtitle Full-Cut Display Change

Latest user request:

- "다음부터는 자막이 각컷의 전체에 표시 될수 있도록 해."

Implemented behavior:

- Applies to newly generated or regenerated cuts.
- Each cut's subtitles now cover the whole cut duration from `0.00` to actual cut end.
- The implementation does not display the entire narration as one static block. It still splits narration into sentences and distributes those sentence subtitles evenly across the full cut window, so there is no subtitle gap inside the cut.

Changed locations:

- `backend/app/services/subtitle_service.py:13`
  - `CUT_SUBTITLE_MARKER_VERSION = 6`
- `backend/app/services/subtitle_service.py:408`
  - `generate_single_cut_ass(...)` now accepts `display_duration`.
- `backend/app/services/subtitle_service.py:486`
  - resolves `display_dur` from `display_duration` or spoken duration.
- `backend/app/services/subtitle_service.py:493`
  - subtitle start is now `0.0`.
- `backend/app/services/subtitle_service.py:494`
  - subtitle end is now `display_dur`.
- `backend/app/services/subtitle_service.py:509`
  - `_cut_subtitle_marker_payload(...)` now includes `display_duration`.
- `backend/app/services/subtitle_service.py:535`
  - `burn_cut_subtitle_file(...)` probes actual cut video duration before generating ASS.
- `backend/app/services/subtitle_service.py:569`
  - marker payload records actual display duration.
- `backend/app/services/subtitle_service.py:592`
  - `generate_single_cut_ass(...)` receives `display_duration=display_dur`.

Important limitation:

- Existing already-burned cut mp4 files are not directly rewritten for this change.
- If an existing cut has a current `.subtitle.json`, `burn_cut_subtitle_file` avoids re-burning to prevent duplicate captions.
- To apply full-cut subtitles to an existing episode, regenerate the relevant cut videos through the pipeline logic, not by direct output editing.

## Upload Metadata Fix

Problem:

- Japanese channel upload previously used wrong metadata language.

Implemented:

- `backend/app/services/oneclick_service.py:4212`
  - upload title now prioritizes config fields:
    - `youtube_title`
    - `youtube_upload_title`
    - `upload_title`
    - script title
    - project title/topic
- `backend/app/services/oneclick_service.py:4389`
  - metadata topic now prioritizes config fields:
    - `youtube_topic`
    - `upload_topic`
    - script topic
    - project topic
    - final title

## Tests / Verification

Commands recorded as passed:

```powershell
PYTHONPATH=backend python -m py_compile backend\app\services\subtitle_service.py backend\tests\test_oneclick_stability.py
```

```powershell
PYTHONPATH=backend python -m unittest backend.tests.test_oneclick_stability.SubtitleStyleStabilityTests.test_default_subtitle_size_is_ten_points_larger backend.tests.test_oneclick_stability.SubtitleStyleStabilityTests.test_single_cut_subtitle_spans_entire_cut_window
```

Expected focused unittest result:

```text
Ran 2 tests ... OK
```

Additional runtime verification in this handoff turn:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
```

Result:

```json
{"status":"ok","version":"V3.2","comfyui_base_url":"http://127.0.0.1:8188"}
```

## Test Changes

- `backend/tests/test_oneclick_stability.py:118`
  - expected lead/tail changed from `0.3` to `0.5`.
- `backend/tests/test_oneclick_stability.py:1961`
  - default start offset expected `0.5`.
- `backend/tests/test_oneclick_stability.py:1964`
  - `6.2s` spoken audio now expects `7.2s` cut duration.
- `backend/tests/test_oneclick_stability.py:1975`
  - `72.0s` spoken audio now expects `73.0s` cut duration.
- `backend/tests/test_oneclick_stability.py:2582`
  - subtitle marker version expected `6`.
- `backend/tests/test_oneclick_stability.py:2585`
  - added test that single-cut subtitle spans full cut window:
    - expected ASS event contains `Dialogue: 0,0:00:00.00,0:00:07.20`

## Remaining Cautions For Next Session

- Do not assume any generated video currently on disk already has full-cut subtitles. This is only guaranteed for cuts generated or regenerated after this logic is active.
- For CH3 EP1, if the user asks to rebuild with the latest subtitle behavior, regenerate through the pipeline. Do not hand-edit final mp4.
- If using existing images, it is acceptable only if user requests it. Audio and cut video mux/subtitle behavior still needs regeneration to apply timing/subtitle logic.
- If upload is repeated, verify YouTube metadata fields are Japanese before upload.
- If queue count is questioned again, inspect the DB/queue data directly. Do not infer why 40 became 39.
- Worktree has many untracked QA/temp files. Stage only the exact tracked files required for a commit.

## Quick Commands For Next Session

Check backend:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 5
```

Check current diff:

```powershell
git diff --stat
git status --short
```

Focused subtitle tests:

```powershell
$env:PYTHONPATH='backend'
python -m unittest backend.tests.test_oneclick_stability.SubtitleStyleStabilityTests.test_default_subtitle_size_is_ten_points_larger backend.tests.test_oneclick_stability.SubtitleStyleStabilityTests.test_single_cut_subtitle_spans_entire_cut_window
```
