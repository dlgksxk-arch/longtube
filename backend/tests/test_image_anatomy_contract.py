from __future__ import annotations

import unittest

from app.services.image.comfyui_service import (
    _body_refine_prompt_for_contract,
    _expected_visible_hand_count,
    _hand_refine_prompt_for_contract,
)
from app.services.image.prompt_compiler import (
    compile_image_prompt,
    prepare_scene_contract_source,
)


MODEL_ID = "comfyui-flux2-klein-4b"


class ImageAnatomyContractTests(unittest.TestCase):
    def compile(self, source: str):
        return compile_image_prompt(source, model_id=MODEL_ID)

    def test_waist_up_pair_keeps_separate_bodies_and_owned_hand_actions(self):
        compiled = self.compile(
            "Main subject: exactly two adults, one envoy and one official; "
            "Scene: waist-up view; exactly two visible hands total; "
            "the envoy stands at the left slot, his exactly one visible hand points toward the packet; "
            "the official stands at the right slot, her exactly one visible hand grips the packet"
        )

        self.assertEqual(compiled.person_count, 2)
        self.assertEqual(compiled.scene_contract.visible_hand_count, 2)
        self.assertIn("exactly two separate adults", compiled.positive)
        self.assertIn("exactly two visible hands total", compiled.positive)
        self.assertIn("one visible hand points toward the packet", compiled.positive)
        self.assertIn("one visible hand grips the packet", compiled.positive)
        self.assertNotIn("one extended index finger", compiled.positive)
        self.assertNotIn("one opposing thumb and four naturally curled fingers", compiled.positive)
        self.assertIn("legs remain outside the crop", compiled.positive)
        self.assertNotIn("two grounded legs", compiled.positive)

    def test_chest_up_zero_hand_contract_does_not_force_hidden_limbs_visible(self):
        compiled = self.compile(
            "Main subject: exactly one adult commander; "
            "Scene: chest-up view, complete face visible, exactly zero visible hands or fingers, "
            "hands outside frame behind the body"
        )

        self.assertEqual(compiled.scene_contract.visible_hand_count, 0)
        self.assertIn("exactly zero visible hands or fingers", compiled.positive)
        self.assertIn("waist and legs remain outside the crop", compiled.positive)
        self.assertNotIn("two grounded legs", compiled.positive)
        self.assertIn("visible hand", compiled.negative)

    def test_catastrophic_anatomy_negatives_survive_flux_budget(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
            "Main subject: exactly three adults; "
            "Scene: full-body view of three soldiers pulling one gate beam"
        )

        for term in (
            "extra head",
            "fused bodies",
            "extra arms",
            "extra legs",
            "malformed hands",
            "extra fingers",
            "fused fingers",
        ):
            self.assertIn(term, compiled.negative)
        self.assertLessEqual(len(compiled.negative), 520)

    def test_narration_is_preserved_as_contract_source_but_not_sent_in_positive(self):
        narration = "성문 안쪽에서 두 사람이 봉인된 꾸러미를 넘겼습니다."
        source = prepare_scene_contract_source(
            "Main subject: exactly two adults; "
            "Scene: waist-up view, left envoy passes one sealed packet to the right guard",
            narration_context=narration,
        )
        compiled = self.compile(source)

        narration_facts = [
            fact.text
            for fact in compiled.scene_contract.source_facts
            if fact.source == "narration"
        ]
        self.assertEqual(narration_facts, [narration.rstrip(".")])
        self.assertNotIn(narration, compiled.positive)
        self.assertTrue(compiled.scene_contract_hash)

    def test_visible_hand_count_parser_accepts_explicit_total_forms_only(self):
        self.assertEqual(_expected_visible_hand_count("exactly two visible hands total"), 2)
        self.assertEqual(_expected_visible_hand_count("all six open hands are visible"), 6)
        self.assertEqual(_expected_visible_hand_count("both hands are visible"), 2)
        self.assertEqual(_expected_visible_hand_count("exactly zero visible hands or fingers"), 0)
        self.assertIsNone(_expected_visible_hand_count("a hand may be near the table"))

    def test_refine_prompts_follow_zero_hand_grip_and_crop_contracts(self):
        zero = self.compile(
            "Main subject: exactly one adult; Scene: chest-up view, exactly zero visible hands or fingers"
        )
        grip = self.compile(
            "Main subject: exactly one adult guard; Scene: waist-up view; exactly two visible hands total; "
            "the guard stands at the center slot, both hands grip one gate beam"
        )

        self.assertIn("continuous sleeve, garment, body occlusion or background", _hand_refine_prompt_for_contract(zero, zero.positive))
        grip_refine = _hand_refine_prompt_for_contract(grip, grip.positive)
        self.assertIn("preserves its existing gesture, scale, orientation, position, depth plane, and object contact", grip_refine)
        self.assertIn("repair local anatomy only", grip_refine)
        self.assertIn("never convert a closed, curled, gripping", grip_refine)
        self.assertIn("never spread or fully extend all digits", grip_refine)
        self.assertNotIn("opposing thumb and four naturally curled fingers", grip_refine)
        self.assertNotIn("pointing finger", grip_refine)
        self.assertIn("variable-width scratchy dip-pen contour lines", grip_refine)
        self.assertIn("dense hatching with intersecting hatch strokes", grip_refine)
        self.assertNotIn("matte cel shading", grip_refine)
        zero_body_refine = _body_refine_prompt_for_contract(zero)
        grip_body_refine = _body_refine_prompt_for_contract(grip)
        self.assertIn("waist and legs remain outside the crop", zero_body_refine)
        self.assertIn("legs remain outside the crop", grip_body_refine)
        self.assertIn("same explicitly named bare-skin boundaries", grip_body_refine)
        self.assertIn("aged fibrous print-stock grain", grip_body_refine)
        self.assertNotIn("matte cel shading", grip_body_refine)

    def test_leading_slot_handoff_keeps_owned_and_unused_hands_in_positive(self):
        compiled = self.compile(
            "Main subject: exactly two adults, one envoy and one guard; "
            "Scene: waist-up view; exactly two visible hands total; "
            "the left envoy passes one sealed packet with his one visible right hand; "
            "the right guard receives the packet with his one visible left hand; "
            "every other hand and wrist remains fully hidden outside the frame"
        )

        self.assertIn("hand ownership: left actor has one visible hand", compiled.positive)
        self.assertIn("right actor has one visible hand", compiled.positive)
        self.assertIn(
            "every other hand and wrist remains fully hidden outside the frame",
            compiled.positive,
        )
        self.assertNotIn("one opposing thumb and four naturally curled fingers", compiled.positive)

    def test_unspecified_hands_do_not_enter_the_positive_prompt(self):
        compiled = self.compile(
            "Main subject: exactly one adult traveler; "
            "Scene: full-body view of the traveler walking across a broad empty steppe"
        )

        for phrase in (
            "any visible hand has five digits",
            "visible hands have five digits each",
            "hands have five digits each",
        ):
            self.assertNotIn(phrase, compiled.positive)
        self.assertIn("malformed hands", compiled.negative)
        self.assertIn("extra fingers", compiled.negative)


if __name__ == "__main__":
    unittest.main()
