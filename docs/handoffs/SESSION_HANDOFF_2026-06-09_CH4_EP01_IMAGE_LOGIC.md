# Session Handoff - 2026-06-09 - CH4 EP01 Image Logic

## Current Objective
- CH4 EP01 `The Empire Defeated by Kittens: The Battle of Pelusium` upload까지 진행.
- 결과물 직접 수정 금지. 문제 발견 시 공통 로직 수정 후 step 4 이미지부터 재생성.
- 특정 채널 고정 금지. 대본의 `Year/period`, `Exact place`, `Scene` 기준으로 범용 처리.

## Important Current State
- Workspace: `C:\Users\Ai_M9\Desktop\longtube`
- Project id: `V3_CH4_EP1_26060813331190f1f0`
- Previous oneclick task id: `62e6a302`
- Result dir: `D:\long_result\CH4\EP.1.26060813331190f1f0`
- Latest status check after final code patch returned `404 Not Found` for `/api/oneclick/tasks/62e6a302`.
- Last generation was cancelled intentionally after inspecting cut 38.
- Final code patch after that cancellation was tested, but backend was not restarted after the final patch.
- Next session must restart backend, recover/reset task, then resume from step 4.

## Files Changed In This Work Segment
- `backend/app/services/image/prompt_builder.py`
- `backend/app/services/image/comfyui_service.py`
- `backend/tests/test_image_prompt_guards.py`

There are many unrelated dirty worktree files from prior work. Do not revert them.

## Latest Verification
Ran after the final code patch:

```powershell
python -m py_compile backend/app/services/image/prompt_builder.py backend/app/services/image/comfyui_service.py
python -m unittest backend.tests.test_image_prompt_guards -v
```

Result:
- `py_compile` passed.
- `backend.tests.test_image_prompt_guards` passed.
- 68 tests OK.

## Image Logic Changes Made

### 1. Inanimate Statue/Object Routing
Problem found:
- Cut 57 source prompt: `a beautiful golden statue of the goddess Bastet, half-woman, half-cat, glowing in a dark temple`
- Generated image became a living male human portrait.

Common logic fix:
- Added statue/idol/sculpture/figurine/monument/bust detection.
- If scene is a statue object without living people before/around it, route as object-only evidence, not character portrait.
- `half-woman`, `goddess`, `figure` inside a statue description no longer triggers living character routing.
- If people are actually acting beside/to a statue, it remains a people scene.

Key test coverage:
- `test_statue_scene_stays_inanimate_object_not_living_portrait`
- `test_people_bowing_to_statue_remains_people_scene`

### 2. Temple/Beam/Text-Like Surface Control
Problem found:
- Cut 60 had fake text/glyph-like marks on a temple upper lintel/beam.

Common logic fix:
- Strengthened positive blank-surface instructions.
- Temple lintels, friezes, column headers, crossbeams, upper wall bands, courtyard beam faces, and wide rectangular architectural bands resolve as blank structural surfaces.
- Cartouche/raised-oval/panel-shaped details resolve as blank material panels.
- Avoided banned prompt tokens like `signboard` and `plaque`.

Key test coverage:
- `test_temple_beam_surfaces_are_blank_structural_bands`
- Existing roadside shrine no-text tests updated and passing.

### 3. Achaemenid/Egyptian Battle Group Composition
Problem found:
- Cut 1 initially rendered a static row of soldiers instead of `massive ancient armies clashing`.

Common logic fix:
- Removed static `tight head-and-shoulders row` battle phrasing.
- Generic clash/battle/battlefield scenes now use:
  - staggered diagonal upper-body action cluster,
  - two compact opposing subgroups facing left/right,
  - clear center collision zone,
  - crossed spear angles,
  - dust,
  - turned shoulders,
  - tense faces,
  - stepped-in feet.
- March/advance without clash wording remains one diagonal moving formation.
- One visible selected handheld item per readable person remains enforced.

Observed result:
- Regenerated cut 1 improved from static row to two opposing groups, but still not a full melee. Current logic is better and tests passed.

Key test coverage:
- `test_achaemenid_generic_battlefield_does_not_seed_shields`
- `test_achaemenid_egyptian_scene_gets_period_local_material_lock`

### 4. Stealth/Sleeping Guards Routing
Existing fix preserved:
- Phanes stealth scene does not route to armed group.
- No weapon lock applied.
- Principal moving person is the only upright moving figure.

New issue found:
- Cut 38 regenerated with no weapons and no modern wall switch, but still had:
  - one standing guard/watchman,
  - modern-looking round door knob hardware.

Final common logic patch made:
- Stealth secondary figures now explicitly require low bodies only:
  - every non-principal head below principal waistline,
  - shoulders touching floor, mat, wall base, or threshold.
- Historical door hardware no longer uses ambiguous small round pull rings.
- Historical doors now use:
  - large hanging bronze/wooden pull rings suspended from loop plates,
  - horizontal wooden latch bars,
  - rope pull loops,
  - hinge barrels,
  - square nail heads,
  - wooden pegs,
  - blank metal strap plates.

Important:
- This final cut 38 fix has passed tests but has not yet been visually regenerated.

Key test coverage:
- `test_achaemenid_stealth_past_sleeping_guards_stays_story_scene`
- `test_premodern_scene_uses_historical_building_hardware`

### 5. Preindustrial Historical Building Hardware
Problem found:
- Ancient scene generated modern-looking switch/light/hardware.

Common logic fix:
- Added preindustrial historical context detection before later prompt augmentation.
- Applies only to ancient/classical/medieval/early-modern/preindustrial contexts.
- Does not apply to 2024/contemporary/modern scenes.
- Adds period-local lighting and hardware:
  - clay oil lamps,
  - bronze oil lamps,
  - candles,
  - torches,
  - braziers,
  - era-appropriate lanterns,
  - open doorway moonlight,
  - window slits,
  - sun/shadow,
  - wooden bars,
  - rope pull loops,
  - large hanging pull rings,
  - latch bars,
  - pegs,
  - plaster/clay/stone repairs.

Key test coverage:
- `test_premodern_scene_uses_historical_building_hardware`
- `test_modern_character_prompt_uses_modern_clothing_lock` confirms modern scene does not get historical hardware lock.

## Last Visual Checks

### Cut 1
Path:
- `D:\long_result\CH4\EP.1.26060813331190f1f0\images\cut_1.png`

Status:
- Latest inspected version had two opposing groups and no static row.
- Still not perfect full melee, but improved and acceptable enough to continue unless user demands stronger melee.

### Cut 38
Path:
- `D:\long_result\CH4\EP.1.26060813331190f1f0\images\cut_38.png`

Status before final patch:
- Stealth/no weapon routing was correct.
- Modern wall switch was gone.
- Still failed due to:
  - one standing secondary guard,
  - round modern-looking door knob.

Final patch was made for those two failures but image has not been regenerated after that final patch.

### Cut 57
Target issue:
- Statue must render as inanimate Bastet statue/object, not living human portrait.

Status:
- Logic and tests fixed.
- Must be visually regenerated and inspected.

### Cut 60
Target issue:
- Temple/courtyard beams must not show fake text/glyphs.

Status:
- Logic and tests fixed.
- Must be visually regenerated and inspected.

## Commands For Next Session

### Restart backend after final patches
```powershell
$old=Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'uvicorn app\.main:app' } | Select-Object -First 1
if($old){ Stop-Process -Id ([int]$old.ProcessId) -Force }
Start-Sleep -Seconds 3
$python='C:\Users\Ai_M9\AppData\Local\Programs\Python\Python313\python.exe'
$workdir='C:\Users\Ai_M9\Desktop\longtube\backend'
Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000') -WorkingDirectory $workdir -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 12
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health'
```

### Auth cookie
```powershell
$cookie = (& python -c "import sys; sys.path.insert(0, r'C:\Users\Ai_M9\Desktop\longtube\backend'); from app.security.auth import create_session_token, SESSION_COOKIE_NAME; print(SESSION_COOKIE_NAME + '=' + create_session_token('095a44ea-1d4c-4317-a546-8593898f4b1c', 'master', 'master'))")
$headers=@{Cookie=$cookie; 'Content-Type'='application/json'}
```

### Recover if task is missing
```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/oneclick/recover' -Headers $headers -Body '{ "project_id": "V3_CH4_EP1_26060813331190f1f0" }'
```

### Reset and resume from image step
```powershell
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/oneclick/62e6a302/reset' -Headers $headers -Body '{ "from_step": 4 }'
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/oneclick/62e6a302/resume' -Headers $headers
```

If recover returns a new task id, use that id instead of `62e6a302`.

### Status check
```powershell
$t=Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/oneclick/tasks/62e6a302' -Headers $headers
[pscustomobject]@{status=$t.status; step=$t.current_step; progress=$t.progress_pct; sub_status=$t.sub_status; completed=$t.current_step_completed; total=$t.current_step_total; active_cut=$t.current_step_active_cut; error=$t.error} | ConvertTo-Json -Depth 5
```

## Next Required Visual Inspection Points
1. Regenerate and inspect cut 38 after latest patch:
   - no standing secondary guard,
   - no modern knob/switch/electric fixture,
   - all non-principal guards low/sleeping,
   - Phanes only upright moving figure.
2. Inspect cut 57:
   - inanimate golden Bastet statue,
   - temple/pedestal object evidence,
   - not living human portrait.
3. Inspect cut 60:
   - priests/cats match scene,
   - temple lintels/friezes/beams blank structural material,
   - no fake glyph/text marks.
4. Continue step 4 to completion.
5. Continue through video/render/upload.
6. Confirm upload completion.

## Current Known Risk
- Local image model may still under-follow action pose prompts. If cut 1 or later battle cuts are too static again, do not edit outputs. Strengthen generic `battle/clash` action composition logic only.
- If door hardware still appears modern, strengthen historical hardware positive phrase only. Do not use channel-specific constraints.
- If cut 38 still shows standing extra guard, further constrain stealth scenes by placing all secondary bodies on mats/floor/threshold and making the principal the only vertical silhouette.
