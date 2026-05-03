# LongTube Session Handoff

Saved at: 2026-05-03 09:40:08 +09:00
Workspace: `C:\Users\Ai_M9\Desktop\longtube`

## User Priorities

- Keep frontend, backend, and ComfyUI alive while this PC is on; if any server dies, it should restart automatically.
- Do not lose in-progress work on server restart. Resume the same task/stage instead of skipping to another queue item.
- Real-time status must show the actual running task and progress. Logs must not show stale or misleading progress.
- Production queue ordering:
  - Overall queue sorts by the next actual execution time across all channels.
  - Channel-specific queues sort episodes ascending.
  - Failed/canceled recovery must reinsert into the global queue in correct order.
- Upload flow:
  - YouTube quota/API usage is a real constraint; avoid unnecessary API calls.
  - Before/after upload, compare against YouTube Studio so already uploaded videos are removed from queue.
  - Upload completion should be confirmed from Studio, not only API return.
  - Failed upload items should appear under a dedicated Upload Waiting menu and be re-uploadable.
  - Completed/upload-processed projects move to `D:\long_result`; DB reconciliation should use that folder.
- Channels:
  - CH1/CH2/CH3/CH4 all need equal logic.
  - When a channel is added, it should automatically appear in queues/status filters.
  - Viewer needs channel filters.
- Subtitles/captions:
  - Do not burn unwanted lower cut-level subtitle text into shorts.
  - Upload captions through YouTube so viewers see language-appropriate subtitles.
  - Generate/upload captions per channel in Korean, English, and Hindi as configured.
- Shorts:
  - Make/upload only 1 short per project going forward.
  - Shorts font must support the target language.
  - Lower branding should show channel name/profile image, not `LongTube` or `???`.
  - Quality should be higher; avoid SD-looking output.
- Thumbnail:
  - All channels use the same thumbnail logic.
  - Upload thumbnail with video.
  - Future thumbnails should use Nano Banana 2 where supported/configured.
  - Avoid text in AI-generated thumbnail background if the font will break; overlay text locally with a proper font.
- Script/image quality:
  - Generated scripts must include concrete era/location context.
  - Image prompts must be tightly related to narration and historically accurate.
  - Strongly block anachronisms, wrong flags, wrong vehicles, random unrelated visuals.
  - Narration numbers must be written for TTS, not raw digits.

## Completed In This Session

### 1. Main menu: `작업기록`

Added `작업기록` to the one-click main menu.

Primary file:

- `frontend/src/app/oneclick/layout.tsx`

Notes:

- Existing `/oneclick/library` menu entry was exposed/renamed as `작업기록`.
- Frontend build passed after the change.

### 2. Live status task auto-selection

Adjusted live status so the detail panel follows the currently running task when `activeTasks` changes.

Primary file:

- `frontend/src/app/oneclick/live/page.tsx`

Notes:

- Build passed after this earlier change.

### 3. Restart recovery / Comfy orphan matching

Updated one-click service logic so server restart/orphaned Comfy work can be detected and attached back to the best matching task instead of being abandoned.

Primary file:

- `backend/app/services/oneclick_service.py`

Notes:

- Detects server-restart failed tasks and queues them.
- Detects ComfyUI orphan output under `longtube/cut_xxx`.
- Matches orphan progress to likely project/task by disk cut counts.
- Backend compile passed after the earlier change.
- This area should still be treated as high risk and verified with actual running tasks.

### 4. TTS number normalization across languages

User pointed out numeric TTS issue is not Korean-only. Implemented common multilingual normalization.

Primary file:

- `backend/app/services/tts/number_normalizer.py`

Removed:

- `backend/app/services/tts/korean_number_normalizer.py`

Integrated into:

- `backend/app/tasks/pipeline_tasks.py`
- `backend/app/routers/script.py`
- `backend/app/services/llm/base.py`

Verified examples:

- Korean: `544년` -> `오백사십사년`
- English: `544 CE` -> `five hundred forty-four CE`
- English: `year 2026` -> `year two thousand twenty-six`
- Hindi: `544 ईस्वी` -> `पाँच सौ चवालीस ईस्वी`
- Hindi: `544 ईसा पूर्व` -> `पाँच सौ चवालीस ईसा पूर्व`
- Japanese: `544年` -> `五百四十四年`

Verification command passed:

```powershell
python -m py_compile backend/app/services/tts/number_normalizer.py backend/app/tasks/pipeline_tasks.py backend/app/routers/script.py backend/app/services/llm/base.py
```

## Important Existing Worktree Changes

Several files already contain broader changes from this long debugging session. Do not revert unrelated edits.

Notable files with existing broad changes:

- `backend/app/tasks/pipeline_tasks.py`
  - Upload flow has thumbnail generation/upload, Studio verification, shorts limited to one, captions, archive move hooks.
  - Also includes video subtitle behavior changes and historical image guard wiring.
- `backend/app/services/llm/base.py`
  - Hindi support, historical visual contract, stronger image continuity fields, language handling.
- `backend/app/routers/script.py`
  - Script save/generation paths now normalize TTS numbers.
- `backend/app/services/oneclick_service.py`
  - Queue/recovery/orphan matching work.

## Known Current Symptoms To Investigate Next

- Live page can show `태스크 목록 로드 실패` while top summary still displays a running/next item. Need check API endpoint and backend logs.
- GPU/CPU can show load while UI says no active task. Need distinguish:
  - ComfyUI still generating orphaned work.
  - Backend lost task state.
  - Frontend polling endpoint failed.
- Stage activity panel sometimes gets stuck on script/audio/image even while logs show another stage. Need inspect task progress source of truth.
- If server restarts mid-task, the same task must resume first. Current logic attempts recovery, but needs live validation.
- CH4 EP.07 `카스트의 기원` failed after restart; expected behavior is immediate retry/resume before moving on.
- CH4 EP.06 uploaded video existed but thumbnail upload was missing; thumbnail upload path and set-thumbnail call need verified against Studio.
- YouTube API quota is tight. Need audit upload/search/Studio comparison calls and cache results aggressively.
- Completed uploaded queue reconciliation still needs robust Studio + `D:\long_result` + DB comparison.

## Suggested Next Session Start

1. Check server state:

```powershell
Get-Process | Where-Object { $_.ProcessName -match 'node|python|cmd|powershell' } | Select-Object Id,ProcessName,CPU,Path
```

2. Check app endpoints/logs for live status/task list failure.

3. Inspect current active ComfyUI queue/history and match it to DB/projects.

4. Fix the API endpoint causing `태스크 목록 로드 실패`.

5. Verify recovery behavior by checking whether the running task ID maps to the displayed queue item.

6. Only after status is truthful, continue upload/thumbnail reconciliation.

## Tone/Process Reminder

The user is frustrated because the system repeatedly claimed things were normal while the UI/Studio showed otherwise. In the next session:

- Do not guess.
- Verify from DB, disk, backend logs, ComfyUI, and YouTube Studio/API where possible.
- State exact evidence.
- Keep UI/UX changes minimal unless directly required.
- Focus first on correctness of state, recovery, queue ordering, and upload reconciliation.

---

## Latest Saved State

Saved at: 2026-05-04 02:23:45 +09:00

### Most Recent User Requirements

- Queue must auto-sort whenever new topics enter the production queue.
- The production queue must run from top to bottom in the actual scheduled order.
- Manually clicked `run` items must stay at the very top and run immediately after the current task finishes.
- Channel modal `top item run` must run that channel's actual top item.
- Korean TTS pronunciation must preserve script/subtitle text but send corrected spoken text to TTS.
- Shorts must include BGM and must not truncate the ending.
- New subtitles should be large white bold text with thick black outline near the lower center, like the provided reference.

### Latest Implemented Changes

- `backend/app/services/oneclick_service.py`
  - Added queue auto-sort on load, save, and API read.
  - Sort rule:
    - manual immediate rows stay pinned first.
    - remaining rows are sorted by each channel's next scheduled slot.
    - each channel's internal order is `episode_number` ascending.
  - `run_queue_top_now(channel)` now honors the channel argument and runs that channel's top queue item.
  - Current live queue file was backed up and sorted.
  - Backup path: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.before_auto_sort_20260504_015612.json`
- `frontend/src/app/oneclick/page.tsx`
  - Channel modal `맨 위 1건 실행` now calls `oneclickApi.runQueueNext(ch)`.
- Current queue after sorting begins:
  - `CH2 EP12`
  - `CH4 EP8`
  - `CH1 EP30`
  - `CH2 EP13`
  - `CH4 EP10`
  - `CH1 EP31`
- Backend restarted on port `8000`.

### Verification Passed

```powershell
python -m py_compile backend\app\services\oneclick_service.py backend\app\routers\oneclick.py
npm exec tsc -- --noEmit
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/health
```

### Important Safety Notes

- Do not commit OAuth/token files:
  - `token_ch1.json`
  - `token_ch2.json`
  - `token_ch3.json`
  - `token_ch4.json`
  - `token_ch1.before_fix_20260501_170633.json`
- Do not commit runtime logs, temp media, or generated output.
- The working tree contains many older broad changes from the long debugging session; avoid reverting them casually.
