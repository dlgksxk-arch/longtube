# FLUX.2 Klein 4B Prompt Research - 2026-06-15

## Scope

- Target model: `comfyui-flux2-klein-4b`
- Local workflow: `backend/workflows/comfyui/flux2_klein_4b_text2img.json`
- Current episode under QA: `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7`
- Research and local inspection were done before code changes.

## Official Sources Checked

- BFL model page: https://bfl.ai/models/flux-2-klein
- BFL blog: https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence
- Hugging Face model card: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
- BFL GitHub: https://github.com/black-forest-labs/flux2
- BFL prompt guide: https://docs.bfl.ai/guides/prompting_guide_flux2
- ComfyUI guide: https://docs.comfy.org/tutorials/flux/flux-2-klein
- ComfyUI workflow template: https://github.com/Comfy-Org/workflow_templates/blob/main/templates/image_flux2_klein_text_to_image.json
- NVIDIA model card: https://build.nvidia.com/black-forest-labs/flux_2-klein-4b/modelcard

## Verified Model Notes

- `FLUX.2 [klein] 4B` is an official Black Forest Labs model.
- The 4B distilled path is documented around low-step generation. BFL/Hugging Face examples use `num_inference_steps=4` and `guidance_scale=1.0`.
- The local ComfyUI workflow previously used `steps=8`, `cfg=1.0`.
- Official FLUX.2 prompting guidance does not support SD-style negative-prompt dependence as the primary control method.
- Critical instructions should be placed early in the positive prompt.
- Forbidden concepts should not be repeated in the positive prompt. They should be replaced by the desired visible alternative.

## Local Evidence From EP13

Generated prompt sidecars:

- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_19.png.prompt.json`
- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_20.png.prompt.json`
- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_21.png.prompt.json`
- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_22.png.prompt.json`
- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_23.png.prompt.json`
- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\images\cut_24.png.prompt.json`

Observed prompt sizes:

| Cut | Positive prompt length | `no/do not` count | hand/finger count | gate/door count |
| --- | ---: | ---: | ---: | ---: |
| 19 | 43124 | 102 | 73 | 71 |
| 20 | 19858 | 118 | 43 | 36 |
| 21 | 19853 | 118 | 43 | 36 |
| 22 | 16801 | 72 | 39 | 33 |
| 23 | 4122 | 16 | 28 | 1 |
| 24 | 56336 | 140 | 92 | 73 |

Observed image failures in contact sheet `images\_qa_contact_19_24.png`:

- `cut_19`: rendered as later-style tiled gate/building, not period-safe early fifth-century scene.
- `cut_20`: rendered as two kneeling people around a basket, not Silla envoy prostrating before King Gwanggaeto.
- `cut_21`: rendered on a blank white background with weak era/place evidence.
- `cut_22`: rendered as a torii-like freestanding wooden gate.
- `cut_23`: object-only crown scene included large visible hands.
- `cut_24`: rendered as a group portrait instead of a single King Gwanggaeto command/decision scene.

## Script Data Problems

File:

- `D:\long_result\CH1\고구려\EP.13.2606151046569e71b7\script.json`

Verified issues:

- All 150 cuts have `visual_subject` set to Korean `광개토대왕`.
- All 150 cuts include non-English text in `visual_year`, `visual_period`, `visual_location`, `visual_evidence`, `visual_subject`, and final `image_prompt`.
- Several `visual_scene` values contain risky symbolic or modern terms such as `glass`, `textbook`, `scalpel`, `velvet`, `chess`, `emblem`, `flag`, `map`, `gate`, `hand`, and `sword`.
- Local instructions in `SESSION_HANDOFF_2026-06-05_GOGURYEO_PREPARED_SCRIPT.md` state that image prompts with Korean/CJK fail quality checks.
- `backend/app/services/llm/base.py` already instructs that `visual_world` should not contain long negative lists, but this EP13 script contains `No Joseon dynasty clothing, no modern objects, no medieval European castles, no readable text.` in `visual_world.continuity_rule`.

## Root Cause

The FLUX.2 klein path was receiving SDXL-style long prompt guards and long negative lists.

For FLUX.2 klein this is unsafe because:

- Repeated forbidden words in positive prompts can be rendered as visual targets.
- Long prompt guard stacking weakens the actual scene instruction.
- Scene fields can contradict each other: for example, `Exact place: Silla Jongbalseong` with a scene asking for `Goguryeo fortress gates`.
- Korean/CJK text in visible prompt fields increases fake writing and emblem-like artifacts.
- Object-only scenes can still get hands if the prompt repeatedly mentions hand/finger anatomy.

## Required Logic Direction

- Add a FLUX.2 klein-only final prompt compiler.
- Keep the normal legacy prompt path for other models.
- Compile FLUX.2 klein prompts into short positive scene contracts.
- Positive prompt order:
  1. era/place/culture
  2. exact subject
  3. visible action
  4. visible inventory
  5. composition
  6. style
- Remove or avoid positive `no`, `do not`, `avoid`, `without`, `negative`, `forbidden`, `text`, `letters`, `caption`, `title` phrasing where possible.
- For object-only scenes, do not mention hands in the positive prompt.
- For hands, prefer hidden/sleeve-covered geometry instead of detailed anatomy wording.
- For horse scenes, state exact positive animal geometry: one horse, one head, one neck, one torso, four legs, one tail, one rider.
- For early Korean/Silla/Goguryeo scenes, normalize Korean labels to English before final ComfyUI submission.
- Change distilled 4B workflow steps from `8` to `4` for first validation.

## Local Files To Change

- `backend/app/services/image/comfyui_service.py`
- `backend/workflows/comfyui/flux2_klein_4b_text2img.json`
- `backend/tests/test_image_prompt_guards.py`

## Verification Plan

- Unit-test FLUX.2 klein prompt compaction directly.
- Ensure compact prompt starts with a FLUX.2 klein scene contract.
- Ensure compact prompt removes `FINAL EP13`, excessive `no`, and positive hand spam for object-only scenes.
- Ensure cut-specific failures map to compact safe positive prompts:
  - `cut_19` gate scene becomes early Silla/Goguryeo frontier command threshold or earthwork setting, not tiled gate text.
  - `cut_22` emblem/flag submission becomes plain lowered Silla token under Goguryeo pressure, not a gate.
  - `cut_23` crown object becomes hands-free object-only crown scene.
  - `cut_24` raised-hand command becomes single King Gwanggaeto command gesture with sleeve-covered hand.
