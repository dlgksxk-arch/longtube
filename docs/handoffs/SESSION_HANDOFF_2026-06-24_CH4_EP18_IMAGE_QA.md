# CH4 EP18 Image Logic Handoff - 2026-06-24

## Current Target

- Workspace: `C:\Users\Ai_M9\Desktop\longtube`
- Episode/project: `V3_CH4_EP18_2606230944454466ae`
- Result folder: `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae`
- Images folder: `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\images`
- Main code file changed: `backend/app/services/image/comfyui_service.py`
- Test file changed: `backend/tests/test_image_prompt_guards.py`

## User Operating Rule

- Do not directly edit generated image results.
- Fix logic/prompt routing, then regenerate only the bad cut.
- Inspect images one by one with zoom crops.
- Do not restart whole generation when only one cut is bad.
- Historical accuracy matters.

## Completed Cuts

### cut_009

Original issue:
- User pointed out the leftmost person had three legs.

Logic fixes applied:
- Strengthened Late Roman crisis route:
  - side-edge guard weapon placement contract
  - cold Danube frontier legwear contract
  - single-emperor head lock
  - medical-collapse pose lock
  - empty chair-back lock
  - door hardware exclusion
  - crisis first rendering rule
  - wall hardware exclusion for crisis route
  - stronger Late Roman gear negative list

Result:
- Regenerated `cut_9.png`.
- Final inspected crop set included `_qa_cut009_regen13_*`.
- Passed: leftmost person has two legs, no extra limb, central emperor has one head, collapse pose works, no modern switch/knob.

### cut_065

Original issue:
- Scene became soldier-only.
- Source required frightened Pannonian civilians in foreground.

Root cause:
- `_flux2_klein_late_roman_military_assembly_prompt` checked uppercase `Pannonian` / `Valentinian` against lowercase text.

Logic fixes applied:
- Fixed routing regex for:
  - `frightened pannonian civilians`
  - `justifying`
  - `valentinian listens`
- Added civilian foreground contract:
  - four foreground unarmored adult Pannonian civilians
  - plain caps / rough beards / bare hair
  - no helmets, armor, shields, swords on civilians
- Added negatives:
  - `helmeted civilian`
  - `metal helmet on civilian`
  - `armored civilian foreground`
  - `civilian holding shield`
  - `civilian holding sword`
- Added test:
  - `test_flux2_klein_late_roman_punitive_justification_keeps_civilians_foreground`

Result:
- Regenerated `cut_65.png`.
- Inspected `_qa_cut065_regen2_*`.
- Passed: unarmored civilians foreground, soldiers only background, no building issue.

### cut_066

Original issue:
- Output showed building/interior-ish infantry scene.
- Source required Roman cavalry demonstrating punitive reach through frosted grass, Quadi scouts retreating to wooded ridge.

Logic fixes applied:
- Added route:
  - `_flux2_klein_is_late_roman_cavalry_deterrence_patrol_scene`
  - `_flux2_klein_late_roman_cavalry_deterrence_patrol_prompt`
- Prompt locks:
  - open cavalry deterrence patrol contract
  - horse-first composition
  - three to five mounted Roman cavalrymen
  - Quadi scouts retreating toward wooded ridge
  - open sky, frosted grass, muddy hoofprints, wooded ridge
  - building inventory empty
  - horse anatomy contract
  - Quadi scout identity lock
- Added test:
  - `test_flux2_klein_late_roman_cavalry_deterrence_patrol_stays_mounted`

Result:
- Regenerated `cut_66.png`.
- Inspected `_qa_cut066_regen_*`.
- Passed: mounted cavalry dominate, open frosted terrain, no buildings, horse anatomy acceptable.

### cut_067

Original issue:
- Young/dark-haired man.
- Wall map/plaque.
- Door hardware / modern-ish door.
- Source required older Valentinian pressing both palms on blank map while officers avoid hard stare.

Root cause:
- Command table route did not detect:
  - `blank map`
  - `both palms`
  - `hard stare`
  - `narrowing his own options`

Logic fixes applied:
- Extended `_flux2_klein_is_late_roman_command_table_scene`.
- Added command table branch for both-palms blank-map pressure.
- Converted positive map surface to safer route-board wording:
  - `one blank unmarked parchment route board sheet`
- Added rear wall inventory:
  - featureless rough plaster
  - cracks, soot stains, timber posts, beam shadow
  - no separate wall objects
- Added command-table negatives:
  - wall map / map on wall / wall-mounted map / framed map / wall plaque map
  - side door / door handle / hinge plate / latch plate
  - young Valentinian / dark-haired Valentinian
- Added officer armor texture lock and Late Roman gear negatives.
- Added test:
  - `test_flux2_klein_late_roman_command_table_blank_map_keeps_older_valentinian`

Result:
- Regenerated `cut_67.png`.
- Inspected:
  - `_qa_cut067_regen2_center_valentinian_zoom.png`
  - `_qa_cut067_regen2_left_full_zoom.png`
  - `_qa_cut067_regen2_right_full_zoom.png`
  - `_qa_cut067_regen2_table_zoom.png`
  - `_qa_cut067_regen2_wall_zoom.png`
- Passed: older white-haired Valentinian, both palms, blank surface, no wall map, no door hardware, mail/scale gear acceptable.

### cut_068

Original issue:
- Initial output was a generic room lineup.
- Modern switch/outlet on wall.
- No clear attendant fastening cloak.
- Door panels/handles repeatedly appeared.
- Multiple purple-cloak / duplicated emperor failures in intermediate regens.

Logic fixes applied:
- Added route:
  - `_flux2_klein_is_late_roman_imperial_cloak_fastening_scene`
  - `_flux2_klein_late_roman_imperial_cloak_fastening_prompt`
- Added routing before audience setup route.
- Prompt evolved into extreme cloak-fastening close-up:
  - older white-haired Valentinian fills center
  - one attendant at viewer-right uses both hands at same shoulder clasp
  - Valentinian hands cropped/belt-height, not fastening his own cloak
  - dark military brown cloak fabric
  - purple only as thin edge trim
  - single-emperor composition lock
  - background covered by dark military wool curtain, spear shafts, blank cloth strips, shoulders, shield rims, smoke
- Important fix:
  - Excluded `CLOAK FASTENING FIRST RENDERING RULE` from the common `Door-adjacent wall integrity contract`.
  - That common contract included `Door hardware placement`, which was inducing repeated doors/handles.
- Added broad negatives:
  - wall switch / outlet / electrical outlet
  - door / doors / doorway / door handle / modern lever handle / ring handles / pull handles
  - window / windows / window frame
  - second purple cloak / two emperors / duplicate Valentinian / second white-haired man
  - full purple cloak / large purple mantle / wide lineup
  - emperor fastening own cloak
  - silver greaves / shiny lower-leg armor
- Added test:
  - `test_flux2_klein_late_roman_imperial_cloak_fastening_uses_attendant_route`

Result:
- Final regenerated `cut_68.png`.
- Inspected:
  - `_qa_cut068_final_center_hands_zoom.png`
  - `_qa_cut068_final_left_edge_zoom.png`
  - `_qa_cut068_final_right_edge_zoom.png`
  - `_qa_cut068_final_background_zoom.png`
  - `_qa_cut068_final_lower_zoom.png`
- Passed:
  - one older white-haired Valentinian
  - one attendant fastening at shoulder with both hands
  - no visible door handles/switches
  - left/right edges use curtain/spears/shields
  - thin purple trim
  - mail/scale torso acceptable

## Current Incomplete Cut

### cut_069

Source prompt:

```text
Year/period: 375 AD; Late Roman Empire and Quadi frontier society, 375 AD;
Exact place: strained Quadi settlement after Roman pressure;
Main subject: Quadi community under pressure after Roman operations;
Scene: Families gather belongings beside trampled fields while armed men stare toward distant Roman patrols.
```

Observed bad output:
- Indoor room.
- Doors and windows.
- Mostly armed Roman-looking figures.
- Missing Quadi families.
- Missing belongings.
- Missing trampled fields.
- Missing distant Roman patrols.

Logic patch already applied:
- Added route:
  - `_flux2_klein_is_late_roman_quadi_displaced_settlement_scene`
  - `_flux2_klein_late_roman_quadi_displaced_settlement_prompt`
- Added open-air Quadi displaced settlement contract:
  - exterior frontier terrain only
  - pale open sky
  - smoke haze
  - trampled field rows
  - crushed grass
  - muddy footprints
  - damaged woven fence rails
  - low hide tents / rough huts
  - household bundles, baskets, bedding rolls, small boxes, leather pouches, cooking pots
  - armed Quadi men looking toward far Roman patrol silhouettes
  - Roman patrols small/far at horizon only
- Added routing before frontier survey route in `_compact_flux2_klein_4b_prompt`.
- Added negatives:
  - interior room
  - audience hall
  - timber corridor
  - stone room
  - plaster wall
  - house wall
  - roofed room
  - doorway wall switch
  - wall switch
  - wall switch plate
  - outlet plate
  - side wall plate
  - two-button wall panel
  - ceiling
  - roof beams
  - wooden ceiling
  - window
  - door
  - doorway
  - door handle
  - indoor lineup
  - building interior
  - house interior
  - Roman soldiers in foreground
  - missing families
  - missing belongings
  - missing bundles
  - missing baskets
  - missing trampled fields
  - missing open sky
  - missing distant patrol
- Updated cleanup exclusions so `Open Quadi displaced settlement contract:` does not receive common interior wall contract.
- Added test:
  - `test_flux2_klein_late_roman_quadi_displaced_settlement_stays_outdoors`

Not yet done:
- Could not run py_compile/tests after this patch.
- Could not regenerate `cut_69.png`.
- Current shell calls failed with:
  - `windows sandbox: runner error: CreateProcessAsUserW failed: 1312`

Next session should run:

```powershell
python -m py_compile backend/app/services/image/comfyui_service.py backend/tests/test_image_prompt_guards.py
```

```powershell
$env:PYTHONPATH='C:\Users\Ai_M9\Desktop\longtube\backend'
python -m unittest backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_late_roman_quadi_displaced_settlement_stays_outdoors
```

Then regenerate only cut 69:

```powershell
$env:PYTHONPATH='C:\Users\Ai_M9\Desktop\longtube\backend'
python _tmp_regen_cut_images_batch.py V3_CH4_EP18_2606230944454466ae comfyui-flux2-klein-4b 69
```

Then inspect:

- full `D:\long_result\CH4\Empire Errors\EP.18.2606230944454466ae\images\cut_69.png`
- foreground families / belongings
- field ground / trampled rows
- horizon patrol silhouettes
- side edges for accidental doors/windows/switches
- Quadi clothing vs Roman foreground mix

Expected pass criteria:

- Exterior open Quadi settlement.
- Visible families gathering belongings.
- Tied cloth bundles, baskets, bedding rolls, small boxes or pots visible.
- Trampled muddy fields / crushed grass visible.
- Armed Quadi men in foreground/midground, not Roman soldiers.
- Roman patrols only distant, small, horizon silhouettes.
- No room, no door, no window, no wall switch, no indoor lineup.

## Verification Already Passed Before Shell Failure

These tests were run and passed before the shell failure:

```powershell
python -m py_compile backend/app/services/image/comfyui_service.py backend/tests/test_image_prompt_guards.py
```

```powershell
$env:PYTHONPATH='C:\Users\Ai_M9\Desktop\longtube\backend'
python -m unittest `
  backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_late_roman_command_table_blank_map_keeps_older_valentinian `
  backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_late_roman_audience_setup_blocks_wall_panels `
  backend.tests.test_image_prompt_guards.ImagePromptGuardTests.test_flux2_klein_late_roman_imperial_cloak_fastening_uses_attendant_route
```

## Important Note

The final state is not complete. Stop point is after applying the `cut_069` Quadi displaced settlement logic patch, before verification/regeneration.
