# Session Handoff - 2026-05-28

## Ground Rules

- 답변은 실제 확인값 기준으로만 한다.
- YouTube 업로드는 API 사용 금지. 브라우저 컨트롤만 사용한다.
- 생성 결과물 자체를 직접 고치지 않는다. 문제가 있으면 로직을 고쳐 다음 생성물에 적용한다.
- 중요한 기능 수정은 사용자 허락 후 진행한다.

## Current Verified State

Checked at: `2026-05-28 18:53:08 +09:00`

- Running OneClick task: `null`
- Task summary:
  - `completed`: 66
  - `cancelled`: 1
  - `upload_failed`: 1
- Queue total: 170
  - CH1: 11
  - CH3: 157
  - CH4: 2

## Active / Non-Completed Tasks

### CH4 Upload Failed

- Task: `348665a3`
- Channel: CH4
- Topic: `Varus Leads Rome Into the Teutoburg Forest`
- Project: `V3_CH4_EP0_260528171327f6918e`
- Result dir: `D:\long_result\CH4\EP.0.260528171327f6918e`
- State: `upload_failed`
- Step states:
  - `2`: completed
  - `3`: completed
  - `4`: completed
  - `5`: completed
  - `6`: completed
  - `7`: pending
- Final render exists under `output`.
- Upload failed because the code attempted YouTube API upload and token refresh failed:
  - `invalid_grant: Account has been deleted`

### CH3 Cancelled

- Task: `e0437a83`
- Channel: CH3
- Episode: 43
- Topic: `겐페이 전쟁은 왜 벌어졌을까`
- Project: `V3_CH3_EP43_260528171204f0a424`
- State: `cancelled`
- Error: `사용자 취소`

## CH4 Queue

Only these two CH4 pending items were verified in the queue:

- `d83c7919` - `Xerxes Bets Persia on Greece`
- `c882c55a` - `Darius III Breaks at Gaugamela`

## CH4 Hindi / India Cleanup

User clarified all CH4 Hindi/India production projects were cancelled and should not remain.

Completed cleanup:

- Deleted CH4 Hindi/India DB `projects` rows for EP17 through EP39 where present.
- Removed task record that kept reviving EP39:
  - `e0db18fd`
  - `V3_CH4_EP39_260516090007e2077b`
  - `라마 전설은 사실일까`
- Removed result folder:
  - `D:\long_result\CH4\인도망`
- Verified after cleanup:
  - `/api/oneclick/running`: `null`
  - `oneclick_tasks.json`: no matching CH4 Hindi/Korean cancelled project strings
  - `oneclick_queue.json`: no matching CH4 Hindi/Korean cancelled project strings
  - `D:\long_result\CH4\인도망`: does not exist

Backup created before DB cleanup:

- `C:\Users\Ai_M9\Desktop\longsult\_system\backups\longtube.before_delete_all_ch4_hindi_cancelled_20260528T080915Z.db`
- `C:\Users\Ai_M9\Desktop\longsult\_system\backups\oneclick_tasks.before_delete_all_ch4_hindi_cancelled_20260528T080915Z.json`
- `C:\Users\Ai_M9\Desktop\longsult\_system\backups\oneclick_queue.before_delete_all_ch4_hindi_cancelled_20260528T080915Z.json`

## Important Bug / Next Fix Needed

The user required:

- Final rendered videos should move to upload pending.
- Browser upload only.
- No YouTube API upload.
- If upload fails, mark failed after one attempt.

Actual behavior observed:

- After CH4 `Varus Leads Rome Into the Teutoburg Forest` final render completed, `upload_pending_worker` automatically attempted YouTube API upload.
- It failed with `invalid_grant`.
- This means API upload path is still active and must be disabled or separated before continuing production/upload workflow.

Relevant code references:

- `backend/app/services/oneclick_service.py`
  - `_mark_task_upload_pending`
  - `_schedule_upload_pending_worker`
  - `_upload_pending_worker_once`
  - `manual_youtube_upload`
- `backend/app/routers/oneclick.py`
  - `/api/oneclick/tasks/{task_id}/upload`

## Files / Data Locations

- Queue file: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.json`
- Task file: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_tasks.json`
- Safety file: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_safety.json`
- DB: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.db`
- CH4 render root: `D:\long_result\CH4`

## Safety State

`oneclick_safety.json` is still in `alert` state from older spend-leak records.

Latest recorded safety event:

- Time: `2026-05-27T09:24:20Z`
- Kind: `spend_leak`
- Provider: OpenAI
- Note: `channel_comment_reply`
- Message: running OneClick task was absent but API cost was recorded.

## User Preference From Last Exchange

User asked whether Codex can write scripts directly.

Answer given: yes. Need minimum inputs:

- Channel
- Topic
- Language
- Target duration or cut count
- Tone / forbidden requirements

For CH4, expected style is English `Empire Errors`: serious, causal, historical decision failure narrative.
