import unittest

from app.services.image.prompt_compiler import (
    _style_contract,
    compile_image_prompt,
    prepare_scene_contract_source,
    supports_scene_contract_v2_model,
)
from app.services.image.prompt_builder import apply_project_style_to_canonical_prompt


class SceneContractSourceTests(unittest.TestCase):
    def test_prepared_wrapper_uses_cut_scene_not_shared_global_world(self):
        raw = "Global visual world: shared style; Year/period: 850 AD; Exact place: Rome; Scene evidence: source row; Style: dark; Scene: Florus talks secretly with two inquisitors in a stone cellar"
        prepared = prepare_scene_contract_source(raw, "photorealistic historical reconstruction")
        self.assertTrue(prepared.startswith("Florus talks secretly with two inquisitors"))
        self.assertNotIn("Global visual world:", prepared)

    def test_cinematic_live_action_style_is_not_documentary(self):
        style = _style_contract(
            "comfyui-krea2",
            "",
            explicit_global_style="Cinematic live-action historical drama; photorealistic.",
        )
        self.assertIn("cinematic live-action historical drama", style)
        self.assertNotIn("documentary", style)

    def test_krea2_uses_shared_scene_contract_and_keeps_cinematic_scene(self):
        self.assertTrue(supports_scene_contract_v2_model("comfyui-krea2"))
        prepared = prepare_scene_contract_source(
            "Florus talks secretly with two inquisitors in a dark stone cellar",
            "Cinematic live-action historical drama frame, photorealistic.",
        )
        compiled = compile_image_prompt(prepared, model_id="comfyui-krea2")
        self.assertIn("Florus talks secretly with two inquisitors", compiled.positive)
        self.assertIn("cinematic live-action historical drama", compiled.positive)
        self.assertNotIn("manhwa", compiled.positive)

    def test_canonical_prompt_replaces_only_style_and_preserves_metadata_and_scene(self):
        source = (
            "Year/period: 855 AD; Exact place: medieval Rome; "
            "Style: old illustration style; "
            "Emotion direction: [quietly] [slowly]; "
            "Scene: Florus talks secretly with two inquisitors in a dark stone cellar"
        )
        prompt = apply_project_style_to_canonical_prompt(
            source,
            "Cinematic live-action historical drama, photorealistic.",
        )
        self.assertIn("Year/period: 855 AD", prompt)
        self.assertIn("Exact place: medieval Rome", prompt)
        self.assertIn("Cinematic live-action historical drama", prompt)
        self.assertIn("Scene: Florus talks secretly with two inquisitors in a dark stone cellar", prompt)
        self.assertIn("Emotion direction: [quietly] [slowly]", prompt)
        self.assertNotIn("old illustration style", prompt)
