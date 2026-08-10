# CH1 백제사 EP01 제작 계속 — 2026-07-15

## Goal

CH1 다음 에피소드인 백제사 EP01을 150컷으로 제작하고, 기존 방식대로 원본 검수한 뒤 영상·음성·자막·썸네일 최종 QA를 거쳐 공개 업로드하고 새 재생목록에 정확히 한 번 넣는다.

## Identity And Paths

- Task ID: `ba81c476`
- Template project: `f60d6b0b`
- Project ID: `V3_CH1_EP1_2607150045456ce0aa`
- Episode code/id: `백제사-EP01`
- Result root: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa`
- Live images: `D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\images`
- Prepared script: `C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts\백제사-EP01_script.json`
- Source workbook: `Z:\HDD2\longtube\CH1 10분역공\2. 삼한시대\백제사\백제사_01-40화_6000컷_통합대본.xlsx`
- Workbook sheet: `01화`
- Source SHA-256: `AA6F37C166B4F135823201FA5EBBC6855C2F6F1202BE0D117844096DE7C1339C`
- Prepared SHA-256: `7CBA6872E0B6281D7C062A46E87E59D95CAA5F02A6E2C3270C2276117BD7761C`
- Playlist title: `위대한 백제`
- Playlist ID: `PLCynqmYs90mw`
- Playlist visibility: public
- Shorts playlist fields: blank

## Actual State At Save

- Script generation: completed
- TTS/audio: completed
- Thumbnail background and overlay: completed and previously accepted
  - `output\thumbnail_bg.png`
  - `output\thumbnail.png`
- Approved images: cuts 1-28
- Live file count: 28 PNG + 28 `.prompt.json` sidecars
- Cut 29: no live file; failed image quarantined
- Cuts 30-150: no approved live files
- Video: not rendered
- YouTube upload: not started
- Playlist insertion: not started
- Task state: `cancelled`, `current_step=None`
- Active runs: empty
- Queue: empty
- DB `completed_cuts_by_step['4']` is stale at 29; do not trust it.

## Approved Image QA

- Cuts 1-22: original-size QA PASS; PNG and sidecar continuous, no zero-byte files.
- Cut 23: rear Yuri at open entrance, hands hidden, PASS.
- Cut 24: exact four separate faces; Biryu male, Soseono sole woman, Onjo male, moustached male heir Yuri; hands absent, PASS.
- Cut 25: one centered rear Yuri, face hidden, hands/lower body absent, PASS.
- Cut 26: Jumong and Yuri, natural two-shot, hands absent, PASS.
- Cut 27: Biryu and Onjo chest-up facing each other; no forearms/wrists/hands, PASS.
- Cut 28: Jumong faces screen-left and Soseono faces screen-right; divergent eye lines, no hands, PASS.

Do not regenerate cuts 1-28 unless a new verified defect is found.

## Cut 29 Failure Evidence

Narration: `그 평온을 깨뜨릴 청년이 마침내 졸본의 성문 앞에 섰고`

First rejected generation:

- Exactly one rear Yuri, no hands, closed gate, but black Western suit jacket/white shirt collar.
- Curved later-period eaves and tiled roof rows appeared over the gate.
- Quarantine: `qa_rejected\cut29_roof_suit_20260715`

Second rejected generation:

- Roof and tiles were removed; one rear figure and anatomy were correct.
- Hair remained a modern short haircut.
- Brown garment still had a modern jacket-like rear collar and a strong tailored center-back seam.
- Independent QA result: FAIL.
- Quarantine: `qa_rejected\cut29_short_hair_tailored_seam_20260715`

No failed image was directly retouched.

## Latest Cut 29 Logic — Not Yet Generated

The current prompt logic now requires:

- one closed plain timber gate made from two uninterrupted bare-wood panels;
- roofless vertical raw-log defensive palisade with open sky;
- one centered direct-rear head-and-shoulders close-up;
- long black hair gathered into one compact tied crown knot with covered nape;
- face fully hidden;
- exactly zero visible hands/fingers and no torso below the armpits;
- undyed brown coarse woven wrap-front robe;
- narrow flat neck band;
- one unbroken rear cloth panel across loose shoulders.

Current cut-specific negatives include modern cropped haircut/undercut, roofed or tiled gate, gatehouse, black tailored jacket, Western suit jacket, lapels, white shirt collar, and tailored center-back seam.

Generate cut 29 once from this logic and inspect the original. Do not treat the logic test as visual approval.

## Cut 30 Logic — Tested, Not Yet Generated

Narration: `문이 열리는 순간, 소서노 가족이 의지하던 권력의 균형도 함께 흔들렸죠`

The current contract requires:

- exactly four named adults;
- adult male heir Yuri, sole adult woman Soseono, adult male Biryu, adult male Onjo;
- a continuous four-face close-up reaction strip at one open roofless timber-palisade gate;
- fixed left-to-right roles;
- Soseono, Biryu, and Onjo turn their eyes toward Yuri with unsettled expressions;
- four separate complete faces cropped at collarbones;
- exactly zero visible upper arms, elbows, forearms, wrists, hands, or fingers;
- crossed wrap-front woven robe collars;
- no fifth person, second woman, gender swaps, closed gate, writing, domestic doorway, or modern sweater.

The internal text detector skip is narrowly limited to the exact cut 29 and cut 30 narrations when the prompt also contains a plain timber gate and uninterrupted bare wood. Existing true-risk gate checks such as cut 44 remain enabled.

## Changed Logic And Tests

Primary files for this work:

- `backend/app/services/image/prompt_compiler.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/app/services/image/scene_contract.py`
- `backend/tests/test_image_prompt_compiler.py`
- `backend/tests/test_baekje_ep01_generation_guards.py`
- `backend/tests/test_image_anatomy_contract.py`
- `backend/tests/test_thumbnail_text_space_normalization.py`
- `backend/scripts/ch1_baekje_workbook_to_prepared_scripts.py`
- `backend/tests/test_ch1_baekje_workbook_converter.py`
- `_regen_project_cuts.py`

The worktree already contains many unrelated user changes. Do not reset, checkout, or broadly stage.

## Verification At Save

Focused suite:

`python -X utf8 -m unittest tests.test_image_prompt_compiler tests.test_baekje_ep01_generation_guards tests.test_image_anatomy_contract tests.test_thumbnail_text_space_normalization`

Result: `Ran 152 tests ... OK (skipped=1)`

Working directory: `C:\Users\Ai_M9\Desktop\longtube\backend`

## Safe Resume Commands

Before generation, cancel/save once more and verify queue/runner state if there is any doubt.

Generate only cut 29:

```powershell
$env:DATA_DIR='C:\Users\Ai_M9\Desktop\longsult'
$env:PYTHONIOENCODING='utf-8'
python -X utf8 _regen_project_cuts.py V3_CH1_EP1_2607150045456ce0aa 29
```

After cut 29 original QA PASS, generate only cut 30:

```powershell
$env:DATA_DIR='C:\Users\Ai_M9\Desktop\longsult'
$env:PYTHONIOENCODING='utf-8'
python -X utf8 _regen_project_cuts.py V3_CH1_EP1_2607150045456ce0aa 30
```

## Pipeline Hazard

`_tmp_resume_oneclick_task_until_qa.py` may remove a detector-failed cut after retry exhaustion and continue to the next number. That previously left cut 29/30 gaps while cut 31 started. Until continuity is restored, use `_regen_project_cuts.py` for the current failed cut and verify that every live cut has both PNG and sidecar.

Once cuts 29 and 30 pass, continue generation in bounded batches with original-size QA running in parallel. Stop at the first verified failure, fix logic, quarantine the failed output, regenerate, then continue. Do not spend the entire pipeline time repeatedly polishing one failed file while all independent work is idle.

## Completion Requirements

1. All 150 images present with sidecars and original-size QA PASS.
2. Render final video only after image QA approval flag is set correctly.
3. Verify narration audio, timing, burned subtitles, multilingual caption assets, intro/intermission/ending, BGM, thumbnail, and final video duration/integrity.
4. Upload public to CH1.
5. Add the uploaded video exactly once to playlist `위대한 백제` (`PLCynqmYs90mw`).
6. Verify remotely that the video appears exactly once in that playlist.
