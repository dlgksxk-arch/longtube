# LongTube Current Session Handoff

이 파일은 새 세션 시작 원장입니다. 과거 인계 전문은 `docs/handoffs/`에 보관합니다.

## Current Detail

- Latest detail: `docs/handoffs/SESSION_HANDOFF_2026-07-06_STUDIO_SCRIPT_TIMING_SMB.md`
- Previous detail: `docs/handoffs/SESSION_HANDOFF_2026-07-02_CH3_EP77_THUMBNAIL_IMAGE_QA_UPLOAD.md`
- V3 workbench/studio source Q&A: `docs/handoffs/SESSION_QA_V3_2026-05-08.md`
- Start protocol: `docs/SESSION_PROTOCOL.md`

## Current State

- Studio project `3f9d31d1` (`보이지 않는 선`) was used for pipeline/script testing.
- Story step was removed from the Studio pipeline UI and script generation path.
- Script narration timing is now enforced as 4.0-6.0 seconds, target 5.0 seconds.
- Claude/GPT script generation now retries on timing failure instead of saving invalid overlong narration.
- Existing generated script output was not edited directly.
- SMB share for `C:\Users\Ai_M9\Desktop\longtube` is `\\192.168.0.221\longtube`.
- If another PC cannot access the share, check `Test-NetConnection 192.168.0.221 -Port 445` on that PC.
- Worktree is heavily dirty. Do not run broad `git add -A`; generated/output folders are causing slow Git scans.

## Latest Runtime State

- Frontend: `0.0.0.0:3000`, PID `6408`, process `node`.
- Backend: `0.0.0.0:8000`, PID `5080`, process `python`.
- ComfyUI: `0.0.0.0:8188`, PID `17536`, process `python`.
- SMB: `0.0.0.0:445`, PID `4`, process `System`.
- Ethernet network category: `Private`.
- Explicit SMB firewall rule enabled: `LongTube SMB 445 LAN`.

## Latest Code Areas Changed

- `frontend/src/app/studio/[projectId]/page.tsx`
  - removed Story step from Studio pipeline.
- `backend/app/routers/script.py`
  - script generation skips story plan generation.
- `backend/app/tasks/pipeline_tasks.py`
  - pipeline script step skips story plan generation.
- `backend/app/services/llm/base.py`
  - V3.1 story contract normalization.
  - script timing failure now raises.
  - timing retry instruction builder added.
- `backend/app/services/llm/claude_service.py`
  - timing failure retries up to 3 times.
- `backend/app/services/llm/gpt_service.py`
  - timing failure retries up to 3 times.
- `backend/app/services/llm/ollama_service.py`
  - V3.1 story contract normalization call.
- `backend/app/config.py`
  - default script TTS window is 4.0-6.0 seconds, target 5.0 seconds.
  - old tolerance/target config can no longer shrink the window.
- `backend/app/services/oneclick_service.py`
  - OneClick script TTS config set to 4.0/5.0/6.0 seconds.
- `backend/tests/test_oneclick_stability.py`
  - focused tests added/updated for timing window, legacy config, retry prompt, story skip, V3.1 normalization.

## Latest Verification

- `npm run build` passed after Studio Story step removal.
- Python compile passed for changed backend files.
- Focused unittest passed for:
  - OneClick 4/5/6 timing config.
  - 4-6 second script TTS window.
  - cut duration not expanding script TTS window.
  - legacy timing config not shrinking the window.
  - retry instruction being added to script prompt.
  - timing violation blocking save.
  - dashboard script generation skipping story plan.
  - V3.1 scene block normalization.

## Latest Completed Uploads

### CH1 EP21

- Task id: `d018f46d`
- Project id: `V3_CH1_EP21_2607011534044c1ce3`
- Result folder: `D:\long_result\CH1\고구려\EP.21.2607011534044c1ce3`
- Main URL: `https://youtube.com/watch?v=p9_bPoJwNUo`
- Shorts:
  - `https://youtube.com/watch?v=DiRDpz7BjUc`
  - `https://youtube.com/watch?v=0JwADz6Dna8`
  - `https://youtube.com/watch?v=cN-eqnjuxXU`
  - `https://youtube.com/watch?v=Lu4P2jeD2LM`

### CH3 EP77

- Task id: `61748e71`
- Project id: `V3_CH3_EP77_260701162949edeb8e`
- Result folder: `D:\long_result\CH3\EP.77.260701162949edeb8e`
- Topic: `도쿠가와 이에야스는 왜 최후의 승자가 됐을까`
- Main URL: `https://youtube.com/watch?v=9HFi3nfg4Ec`
- Shorts:
  - `https://youtube.com/watch?v=JVe0t2BGb7U`
  - `https://youtube.com/watch?v=g7kwJ7Iaqs8`
  - `https://youtube.com/watch?v=FFWTzqBeGm0`
  - `https://youtube.com/watch?v=qr3jleAyysU`

## Latest Verified Runtime State

- CH3 EP77 final task state was verified:
  - `status=completed`
  - steps `2` through `7`: completed
  - `error=null`
- Final video existed:
  - `D:\long_result\CH3\EP.77.260701162949edeb8e\output\final_with_subtitles.mp4`
  - size: `164664087` bytes
  - timestamp: `2026-07-01 19:36:29`
- Thumbnail checked:
  - `D:\long_result\CH3\EP.77.260701162949edeb8e\output\thumbnail.png`
  - Japanese text lower-left
  - face right/center
  - text does not cover eyes, nose, mouth, chin, forehead, or expression.

## Latest Code Areas Changed

- `backend/app/services/thumbnail_service.py`
  - final thumbnail overlay QA added.
  - overlay text covering face or expression now fails and retries.
  - first-cut/fallback thumbnail path now runs final overlay QA instead of silently accepting bad overlay.
- `backend/app/services/image/comfyui_service.py`
  - CH3 Japanese historical Flux2/Klein prompt contract tightened.
  - street/shop/sign triggers are converted away from buildings and writing surfaces.
  - sleeve badges, sleeve patches, paper maps, route lines, and document-like surfaces are blocked in Japanese historical contexts.
  - Osaka defense-board prompts now use raised rope, stone, clay, and bronze markers instead of maps/books/papers.
- `backend/tests/test_oneclick_stability.py`
  - focused tests added for thumbnail overlay fallback guard.
  - focused tests added for Japanese street/sign, sleeve patch, and Osaka defense-board prompt guards.

## Latest Regeneration / QA Facts

- CH3 EP77 was not fully regenerated.
- Only problem cuts were regenerated after logic changes.
- Problem cuts fixed and visually accepted:
  - `cut_145`: removed shop/building/sign risk by converting to open rice-field road composition.
  - `cut_66`: removed sleeve patch and paper-document risk by converting to sealed bundle/table composition.
  - `cut_123`: removed paper map/open-book/line-marking risk by converting to raised cord-and-stone marker table.
- Final candidate QA sheet:
  - `C:\Users\Ai_M9\Desktop\longtube\_qa_ch3_ep77_sheets\ch3_ep77_final_problem_candidates_after_66_123_145.jpg`

## Latest Data Repair

- During CH3 EP77 upload resume, final render first failed because DB rows for six cuts had `image_path=None` and `status=failed`.
- A DB backup was created before repair:
  - `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch3_ep77_missing_image_paths_20260701_193243.db`
- Repaired rows in `data\longtube.db` only for cuts:
  - `7`, `92`, `120`, `125`, `127`, `143`
- Repair values:
  - `image_path='images/cut_N.png'`
  - `image_model='comfyui-flux2-klein-4b'` when null
  - `status='completed'`
- Upload was resumed after repair and completed.

## Verification Completed

- `python -X utf8 -m py_compile backend\app\services\thumbnail_service.py backend\app\services\image\comfyui_service.py backend\tests\test_oneclick_stability.py`
- Focused unittest checks passed for:
  - thumbnail quality fallback rejection.
  - thumbnail overlay guard.
  - face-safe thumbnail overlay layout scoring.
  - Japanese street/sign trigger removal.
  - Japanese sleeve patch negative prompt guard.
  - Japanese Osaka defense-board raised marker conversion.
  - existing Japanese sign-zone and open-document replacements.

## Required Next Work

1. If continuing production, start only confirmed next episodes.
2. CH4 needs a valid next source before any new run.
3. Keep following image generation one by one until the workbench can enforce the same checks without manual follow-up.
4. For generated image issues, do not edit images directly. Fix logic, then regenerate only affected cuts.
5. For thumbnails, keep face-safe text placement and final overlay QA mandatory.

## Rules

- 추측하지 않습니다. 파일, 로그, DB, API 응답 기준으로 판단합니다.
- 생성 결과물은 직접 수정하지 않습니다.
- 문제는 로직 수정 후 다음 생성물/재생성 컷에 적용합니다.
- dirty worktree의 기존 변경을 되돌리지 않습니다.
- 토큰/OAuth/DB/로그/캐시는 커밋하지 않습니다.
- 대본 생성 프롬프트 소스는 `backend/app/services/llm/base.py` 하나만 사용합니다.
