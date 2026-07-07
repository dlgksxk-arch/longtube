# Session Handoff 2026-07-06 - Studio Script Timing / SMB Share

## User Instruction Baseline

- 추측하지 말고 실제 확인값으로만 답변.
- 생성 결과물 문제는 결과물 직접 수정 금지. 로직을 고쳐 다음 생성물에 적용.
- 중요한 수정은 사용자 허락 후 진행.
- 짧고 정확하게, Jarvis 톤.

## Studio Pipeline Changes

- Studio dashboard project tested at:
  - `http://192.168.0.221:3000/studio/3f9d31d1`
  - project id: `3f9d31d1`
  - title: `보이지 않는 선`
- Story step removed from Studio UI:
  - `frontend/src/app/studio/[projectId]/page.tsx`
  - pipeline now starts `설정 -> 대본 -> 음성 -> 이미지 -> 영상 -> 렌더링 -> 유튜브`
- Backend script generation now skips story plan generation for Studio/script route:
  - `backend/app/routers/script.py`
  - `backend/app/tasks/pipeline_tasks.py`
  - `backend/app/services/llm/base.py`
- Script success no longer marks story step complete; it removes the story step state.

## V3.1 Story Contract Fix

- Error fixed:
  - `story plan validation failed`
  - `V3.1 scene_blocks count mismatch: 5 expected 2`
- Added V3.1 normalization:
  - `BaseLLMService.normalize_v31_story_contract(...)`
  - file: `backend/app/services/llm/base.py`
- Called after visual context strengthening in:
  - `backend/app/services/llm/claude_service.py`
  - `backend/app/services/llm/gpt_service.py`
  - `backend/app/services/llm/ollama_service.py`
- Actual project verification:
  - `script.json` saved at `C:\Users\Ai_M9\Desktop\longsult\_system\projects\3f9d31d1\script.json`
  - 15 cuts
  - 2 scene blocks
  - ranges `1-10`, `11-15`

## Script Timing Fix

- User required no manual regeneration/editing of existing output.
- Existing generated script was not edited.
- Root problem found:
  - `BaseLLMService.assert_script_timing()` only warned before.
  - Long narration was saved because validation did not block.
- Fixed logic:
  - `backend/app/config.py`
    - default script TTS window is now 4.0-6.0 seconds, target 5.0 seconds.
    - old `script_tts_target_sec=3.6` and `script_tts_tolerance_sec` no longer shrink the window.
  - `backend/app/services/oneclick_service.py`
    - OneClick sets `script_tts_min_sec=4.0`, `script_tts_target_sec=5.0`, `script_tts_max_sec=6.0`.
  - `backend/app/services/llm/base.py`
    - prompt now states the upper bound is a save-blocking validation limit.
    - `assert_script_timing()` now raises `ValueError`.
    - added retry instruction builder for timing failures.
  - `backend/app/services/llm/claude_service.py`
    - Claude script generation retries up to 3 times when narration timing fails.
    - retry prompt includes failed cut numbers and actual lengths.
  - `backend/app/services/llm/gpt_service.py`
    - GPT gets the same timing retry loop.
- Current project `3f9d31d1` timing calculation:
  - min: `4.0s`
  - target: `5.0s`
  - max: `6.0s`
  - current voice-profile Korean range: `32~48 chars`
- Legacy config calculation verified:
  - min: `4.0s`
  - target: `5.0s`
  - max: `6.0s`
  - range: `40~60 chars`

## Tests Run

- `python -m py_compile backend/app/config.py backend/app/services/llm/base.py backend/app/services/llm/claude_service.py backend/app/services/llm/gpt_service.py backend/tests/test_oneclick_stability.py`
- Focused unittest passed:
  - `OneClickQueueStabilityTests.test_oneclick_main_length_is_150_four_second_cuts`
  - `InterludeStabilityTests.test_script_uses_four_to_six_second_tts_window`
  - `InterludeStabilityTests.test_cut_video_duration_does_not_expand_script_tts_window`
  - `InterludeStabilityTests.test_legacy_script_tts_tolerance_cannot_shrink_four_to_six_window`
  - `InterludeStabilityTests.test_timing_retry_instruction_is_added_to_script_prompt`
  - `InterludeStabilityTests.test_script_timing_violation_blocks_save`
- Earlier focused tests also passed for:
  - story plan skip from dashboard script route
  - V3.1 scene block normalization
- `npm run build` passed after Studio Story step removal.

## Runtime State

- Backend health passed:
  - `http://127.0.0.1:8000/api/health`
  - status `ok`
  - version `V3.1`
- Current listeners:
  - frontend: port `3000`, PID `6408`, process `node`
  - backend: port `8000`, PID `5080`, process `python`
  - ComfyUI: port `8188`, PID `17536`, process `python`
  - SMB: port `445`, PID `4`, process `System`

## SMB Share Work

- User requested sharing:
  - `C:\Users\Ai_M9\Desktop\longtube`
- Share already existed:
  - `\\192.168.0.221\longtube`
  - `\\M9\longtube`
  - share access: `Everyone / Full`
  - NTFS includes `Everyone:(OI)(CI)(M)`
- External access issue found:
  - network profile was `Public`
  - SMB-In firewall rules were disabled
- Applied with elevated PowerShell:
  - Ethernet profile set to `Private`
  - enabled `FPS-SMB-In-TCP`
  - enabled `FPS-SMB-In-TCP-V2`
  - started `FDResPub` and `fdPHost`
  - added explicit inbound rule:
    - display name: `LongTube SMB 445 LAN`
    - TCP local port `445`
    - remote address `192.168.0.0/24`
    - profile `Any`
- Verified current state:
  - Ethernet `Private`
  - `LongTube SMB 445 LAN` enabled
  - `0.0.0.0:445` and `[::]:445` listening
- If another PC still cannot access, check from that PC:
  - `ping 192.168.0.221`
  - `Test-NetConnection 192.168.0.221 -Port 445`
  - `net use * /delete`
  - `net use \\192.168.0.221\longtube /user:M9\Ai_M9`

## PC Slowdown Finding

- Main observed cause:
  - Codex parent process repeatedly launching Git commands.
  - commands included `git add -A`, `git diff`, `git write-tree`, `git status`.
- Worktree had many files:
  - `git status --porcelain=v1 --untracked-files=all` count: `2165`
  - heavy folders included:
    - `output`
    - `outputs`
    - `_tmp_inspection_*`
    - `.codex_inspection`
- Defender `MsMpEng` also used CPU while Git scanned files.
- Memory, disk, GPU were not bottlenecks in the sampled checks.
- Important: do not run broad `git add -A` in this repo until generated/output folders are cleaned or ignored.

## Dirty Worktree Warning

- The worktree has many pre-existing modified/deleted files unrelated to the latest Studio/script timing work.
- Do not revert broad changes.
- Do not stage everything blindly.
- Latest intentional code areas from this session are mainly:
  - `frontend/src/app/studio/[projectId]/page.tsx`
  - `backend/app/config.py`
  - `backend/app/routers/script.py`
  - `backend/app/tasks/pipeline_tasks.py`
  - `backend/app/services/llm/base.py`
  - `backend/app/services/llm/claude_service.py`
  - `backend/app/services/llm/gpt_service.py`
  - `backend/app/services/llm/ollama_service.py`
  - `backend/app/services/oneclick_service.py`
  - `backend/tests/test_oneclick_stability.py`

## Next Session Start Checklist

1. Read `SESSION_HANDOFF.md`.
2. Read this file.
3. Do not regenerate `보이지 않는 선` unless the user explicitly asks.
4. If script generation is tested again, expect timing retry rather than immediate save failure.
5. If SMB still fails, ask for the other PC result of `Test-NetConnection 192.168.0.221 -Port 445`.
