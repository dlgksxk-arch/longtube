# Session Handoff 2026-07-14 - CH2 Europe English Queue

## Scope

- Channel: CH2
- YouTube brand: `Scartography`
- Template project id: `e6619f7e`
- User requirement: audio and captions must be English only.
- Source workbooks were read and validated; none of the XLSX files were edited.
- Generated prepared JSON files were never patched directly. Converter logic was fixed and the complete set was regenerated when validation found a problem.

## Source Workbooks

1. `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌1_EP01-34_한영_5100컷_통합대본.xlsx`
   - EP001-EP034, 5,100 cuts
   - SHA-256: `717167F2ED853B0A5A4DFB4C49ABAB6C9CF04F20E21F71AA00639EAD5D5BB9CE`
2. `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌2_EP035-069_한영_5250컷_통합대본.xlsx`
   - EP035-EP069, 5,250 cuts
   - SHA-256: `54228B3A8DBACF6B603259267AE9DA8354B9C017DE337E5715CF87EC0AB04888`
3. `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌3_EP070-101_한영_4800컷_통합대본.xlsx`
   - EP070-EP101, 4,800 cuts
   - SHA-256: `B5A1F2C8128E7DD5E6AFCB2D1B31EE22216EEAA0B40AB9E6022FA6B166B85343`
4. `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌4_EP102-130_한영_4350컷_통합대본.xlsx`
   - EP102-EP130, 4,350 cuts
   - SHA-256: `651281DE76D690ABEEFC4D98D6DADEF7ACF7EA14CCEB3ABAE9D0522DF065622B`
5. `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시즌5_EP131-179_한영_7350컷_통합대본.xlsx`
   - EP131-EP179, 7,350 cuts
   - SHA-256: `0B4FA4C88FBA57EBC6E44C34752EC91A168ED69223C55C20C5C57B1BC0A5898B`

Queue design workbook:

- `Z:\HDD2\longtube\CH2 유럽사\유럽사\유럽사_시크릿_179부작_큐시트_설계.xlsx`
- Sheet: `에피소드_설계`
- Used range: 180 rows x 22 columns
- Episode coverage: `유럽사 시크릿-EP001` through `유럽사 시크릿-EP179`

## Prepared Script Result

- Output: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts`
- Manifest: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts\manifest.json`
- Script version: `prepared-ch2-europe-en-v2`
- Generated at: `2026-07-14T05:30:44+00:00`
- Episodes: 179
- Cuts: 26,850
- Cuts per episode: 150
- Language: `en`
- Caption languages: `["en"]`
- Every cut has `caption_tracks={"en": narration}` only.
- Pipeline prepared-script validator: 179/179 passed.
- Manifest file hashes: 179/179 passed.
- Residual CJK in final narration/image prompts: 0.
- Residual `Narrative beat`, `Narrative moment`, `no modern objects`, `set around`, and prompt-level `next episode`: 0.
- Verified exact cell corrections: 37.
- Repeated exact corrections: 435.
- Cut-specific visual-period corrections: 21.

## CH2 Runtime Configuration

- `language`: `en`
- `tts_voice_lang`: `en`
- `tts_model`: `elevenlabs`
- `tts_voice_id`: `fIGaHjfrR8KmMy0vGEVJ`
  - This is the same voice id used by the existing completed CH2 English projects.
- `caption_languages`: `["en"]`
- `caption_source`: `script_tracks`
- `youtube_captions_enabled`: `true`
- `subtitle_delivery`: `youtube_caption`
- `cut_level_subtitles`: `false`
- `youtube_localization_languages`: `["fr", "es", "de"]`
  - These are YouTube title/description metadata localizations, not audio or caption tracks.

## Queue Registration

- CH2 queue items: 179.
- Episode coverage: EP001-EP179 exactly once.
- Status: all `pending`.
- CH2 active tasks: 0 at registration and final verification.
- CH2 schedule: `null`.
- CH2 preset: `e6619f7e`.
- Queue core declares `[Audio] English` and `[Captions] English` only.
- Registration does not start CH2 production.
- Current saved queue after CH1 EP30 moved out of the queue into its task:
  - total 257
  - CH1 40
  - CH2 179
  - CH3 35
  - CH4 3

## Logic Files

- `backend/scripts/ch2_europe_titles_en.py`
  - Direct English title catalog for EP001-EP179.
- `backend/scripts/ch2_europe_workbook_to_prepared_scripts.py`
  - Reads the five integrated XLSX files through ZIP/XML.
  - Validates exact sheet ranges, metadata labels, headers, cut numbering, Shorts tags, and full episode coverage.
  - Applies guarded English corrections and cut-period corrections.
  - Removes narration/meta text from image prompts.
  - Emits English narration and one English caption track only.
  - Writes byte-stable JSON and a hash manifest.
- `backend/scripts/ch2_register_europe_queue.py`
  - Validates the queue design workbook, source hashes, manifest, all 179 JSON hashes, 26,850 cuts, English-only tracks, and pipeline acceptance.
  - Sets the CH2 template to English audio and English-only captions.
  - Uses an offline direct queue-file update while the backend is stopped.
  - Does not import `oneclick_service`; this prevents dry-run task mutation and other-channel queue normalization.
  - Preserves all non-CH2 queue items and unknown top-level queue fields exactly.
- Tests:
  - `backend/tests/test_ch2_europe_workbook_converter.py`
  - `backend/tests/test_ch2_europe_queue_registration.py`
  - Final focused result: 15/15 passed.

## Problems Found and Corrected

1. The first generated staging set had manifest hash mismatches because Windows newline conversion changed file bytes after the hash was computed.
   - The writer logic was changed to write exact UTF-8 bytes.
   - A new full staging set was generated.
2. EP002 cuts 136-150 contained prompt meta text `toward the next episode`.
   - Prompt cleanup logic was changed to remove the meta phrase.
   - All 179 episodes were regenerated.
3. The first queue writer imported `oneclick_service`.
   - That import normalized CH1 EP30 from 139 cuts/556 seconds to 150 cuts/600 seconds and refreshed finished timestamps in completed task records.
   - The flawed registration was backed up, the queue/tasks baseline was restored, and the registrar was rewritten as a side-effect-free offline file updater.
   - Final verification proved non-CH2 queue items were structurally exact and `oneclick_tasks.json` was byte-identical to the baseline before the corrected registration.

## Backups

- Pre-registration queue/tasks/DB baseline:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\ch2_europe_registration_backup_20260714_143325`
- Flawed registration capture:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\ch2_europe_failed_registration_20260714_143509`
- Original prepared-script directory backup:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts_backup_20260714_142705`
- Rejected intermediate prepared-script backup:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts_backup_20260714_143110`
- Corrected registration queue backup:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.before_ch2_europe_179_20260714_143521.json`
- Corrected registration DB backup:
  - `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch2_europe_179_20260714_143521.db`

## Runtime at Handoff

- Backend PID: `24476`
- Backend health: HTTP 200
- `LongTube Watchdog`: enabled and `Ready`
- CH2 active tasks: 0
- CH2 remains unscheduled.
- CH1 EP30 task `8ec5181a` resumed during the controlled backend restart, then failed at Step 4 after reaching 133/139 images.
- CH1 EP30 missing images reported by the task: 91, 100, 122, 127, 128, 134.
- Do not change CH1 EP30 to 150 cuts. Its actual target remains 139 cuts / 556 seconds.

## Known Unchanged Asset Issue

- `opening.mp4`, `intermission.mp4`, and `ending.mp4` still exist under the CH2 project `interlude` directory.
- Prior visual verification found the retired `Jerry's Archaeo` brand in all three videos.
- They were not modified because no disable/replace approval was given.

## Do Not Infer

- Do not edit any source XLSX file to repair generated data.
- Do not patch prepared JSON files directly. Fix the converter and regenerate the complete output set.
- Do not add French, Spanish, German, Korean, or Japanese audio/caption tracks. Audio and captions are English only.
- Metadata localization is separate from caption generation.
- Do not schedule or start CH2 without a new explicit instruction.
- Do not replace or disable the three interlude videos without explicit approval.
