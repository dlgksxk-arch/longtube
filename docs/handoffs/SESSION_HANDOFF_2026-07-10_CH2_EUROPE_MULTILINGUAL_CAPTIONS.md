# CH2 Europe Multilingual Caption Handoff

## Scope

- Channel: CH2
- YouTube channel: `Scartography` (`@scartography`)
- YouTube channel id: `UCRJbxZoVj7l41Fsw_S9a23A`
- Template project id: `e6619f7e`
- Source workbook: `Z:\HDD2\longtube\CH2 유럽사\유럽사\#유럽사_시크릿_179편_전체_대본.xlsx`
- EP sheets are the source of truth.
- Audio language: English only.
- YouTube selectable captions: English, French, Spanish, German.
- Burned-in cut subtitles: disabled for CH2.

## Workbook Facts

- Sheets: 182 total (`INDEX`, `SHORTS_MAP`, `EP001`-`EP179`, `PROMPT_QA`).
- Episodes: 179.
- Cuts: 150 per episode, 26,850 total.
- Caption contamination found: 870 cut rows, 3,480 language cells.
- Contamination was limited to 19 repeated cut patterns.
- The source workbook was not edited.
- Source SHA-256 after conversion: `BAD0A5B705F9763C5E4187FC667464EB879C5743611E154C7C098757CDD031AE`.

## Conversion Result

- Converter: `backend/scripts/ch2_europe_workbook_to_prepared_scripts.py`
- Actual output directory: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\e6619f7e\prepared_scripts`
- Generated: 179 JSON files.
- Generated cuts: 26,850.
- Full-sentence translations applied: 870 rows.
- Caption tracks per cut: `en`, `fr`, `es`, `de`.
- English narration equals the English caption track.
- Residual Hangul in caption tracks: 0.
- Residual Hangul in cleaned image prompts: 0.
- Pipeline prepared-script validator: 179/179 passed.
- Actual selector check: `EP002` resolved to `prepared_scripts\EP002.json`, 150 cuts.
- CH2 production queue registration was completed after prepared-script validation.

## Production Queue Registration

- CH2 queue items registered: 179, all `pending`.
- Queue episode codes: exact sequence `EP001`-`EP179`.
- Queue topics: direct English title catalog, one unique title per episode.
- Series: `Scartography`.
- Template project id on every item: `e6619f7e`.
- Total queue after registration: 220 (`41` existing non-CH2 items preserved + `179` CH2 items).
- CH2 schedule: `null`.
- CH2 queue source: `import`, so items are not immediate-run items.
- Latest queue backup: `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.before_ch2_europe_179_20260710_170611.json`.
- One scheduler cycle after registration: CH2 still 179 pending, active tasks 0, active DB projects 0.

## Logic Changes

- `backend/scripts/ch2_europe_workbook_to_prepared_scripts.py`
  - Reads XLSX through a standard-library ZIP/XML reader; no `openpyxl` dependency.
  - Uses EP row 9 headers and rows 10-159.
  - Rewrites contaminated caption rows as complete English/French/Spanish/German sentences.
  - Localizes year, year range, century, BCE, tradition, and month expressions.
  - Blocks writes if any validation error or residual Hangul remains.
  - Resolves the output directory through the application's actual project path logic.
- `backend/scripts/ch2_europe_titles_en.py`
  - Contains the direct English title catalog for all 179 episodes.
- `backend/scripts/ch2_register_europe_queue.py`
  - Validates INDEX, prepared scripts, captions, titles, and pipeline acceptance before registration.
  - Preserves other channels and replaces only CH2 queue rows through `set_queue()`.
  - Refuses writes while the backend is running and creates a queue backup before registration.
- `backend/app/services/multilingual_caption_service.py`
  - Reads configured caption languages.
  - Supports German.
  - Builds SRT tracks from `script.json` cut-level `caption_tracks`.
  - Strict `script_tracks` mode fails instead of silently translating missing tracks.
- `backend/app/config.py` and `backend/app/tasks/pipeline_tasks.py`
  - Cut-level subtitle burn now respects `cut_level_subtitles`.
  - Default remains enabled for projects without the setting.
- `backend/app/services/youtube_metadata.py`
  - Adds the explicit `european_history` metadata profile used only when configured.
  - Removes unrelated horror/mystery tags, limits tags to 12, and validates metadata before upload.
  - Produces English Scartography descriptions with the configured caption-language notice.
- `backend/app/services/youtube_localization_service.py`
  - Accepts script-provided YouTube localizations first.
  - Generates missing French, Spanish, and German titles/descriptions before upload.
  - Blocks upload when a required localization is missing or exceeds YouTube limits.
- `backend/app/services/youtube_service.py`, `backend/app/services/oneclick_service.py`
  - Upload `defaultLanguage=en` and `defaultAudioLanguage=en`.
  - Merge localized video metadata without dropping the existing snippet.
  - Use configured category and main/Shorts playlist IDs.

## CH2 Template Config

- `language`: `en`
- `tts_voice_lang`: `en`
- `caption_languages`: `["en", "fr", "es", "de"]`
- `caption_source`: `script_tracks`
- `subtitle_delivery`: `youtube_caption`
- `youtube_captions_enabled`: `true`
- `cut_level_subtitles`: `false`
- `youtube_metadata_profile`: `european_history`
- `youtube_category_id`: `27` (`Education`)
- `youtube_playlist_id`: `PLTQZqphQcmJE`
- `youtube_shorts_playlist_id`: `PLBTk63lMj3yw`
- `youtube_metadata_localizations_enabled`: `true`
- `youtube_localization_languages`: `["fr", "es", "de"]`
- `youtube_metadata_translation_model`: `gpt-5.4-mini`
- `shorts_channel_name`: `Scartography`
- DB backup: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch2_caption_config_20260710_132210.db`
- Missing stale reference/logo/character paths were removed after confirming the files did not exist in data, repo, NAS, or CH2 result roots.
- Start-readiness DB backup: `C:\Users\Ai_M9\Desktop\longtube\data\longtube.before_ch2_start_ready_20260710_141231.db`

## Verification

- Focused metadata/caption/queue unit tests: 18 passed.
- Queue/YouTube/upload stability classes: 30 passed.
- Python compile checks passed.
- Actual EP002 SRT integration: 150 entries each for `en`, `fr`, `es`, `de`; residual Hangul 0.
- Caption tracks survived visual-policy and Shorts annotation processing unchanged.
- Backend restarted after confirming zero active jobs.
- Current backend PID: `33244`.
- `http://127.0.0.1:8000/api/health`: HTTP 200, `status=ok`.
- Current backend error log: `uvicorn_ch2_metadata_final_20260710_171659.err.log`.
- Current backend log: `uvicorn_ch2_metadata_final_20260710_171659.out.log`.
- Current backend startup: one Uvicorn process, scheduler loop started, HTTP 200.
- ComfyUI: reachable, one device.
- API key presence: ElevenLabs, FAL, OpenAI, Anthropic all present.
- Opening/intermission/ending: all exist and probe to 5.0 seconds, but all visibly contain the retired `Jerry's Archaeo` brand. They remain unchanged pending an explicit disable/replace decision.
- YouTube token: exists with refresh token.
- Broad `test_oneclick_stability` run: 229 tests, 20 unrelated existing image/thumbnail guard failures.

## YouTube Metadata State

- Channel default language: English; country setting: US.
- Channel localizations: `en_US`, `fr_FR`, `es_ES`, `de_DE`.
- Channel keywords and banner are present.
- Public playlists now present:
  - `Scartography: European History` (`PLTQZqphQcmJE`)
  - `Scartography: History Shorts` (`PLBTk63lMj3yw`)
- Both playlists are public, default to English, and have English/French/Spanish/German metadata.
- Retired public playlists containing 67 deleted-video tombstones were deleted after exact title/count validation.
- Exact-name YouTube Data API search did not return the renamed channel in the top 10 immediately after the rename. YouTube documents that rename/search propagation can take several days.

## Do Not Infer

- Do not edit the source workbook to repair generated data.
- Do not patch prepared JSON files directly; fix converter logic and regenerate.
- The user will provide replacement scripts. Register those through the converter/queue logic; do not patch the current prepared JSON files.
- CH2 is registered but intentionally unscheduled. Start only by an explicit manual CH2 run command.
