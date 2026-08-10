from __future__ import annotations

import json
import unittest

from app.services.image.scene_contract import (
    SCENE_CONTRACT_VERSION,
    build_scene_contract,
)


class SceneContractTests(unittest.TestCase):
    def test_extracts_only_explicit_single_actor_geometry(self) -> None:
        contract = build_scene_contract(
            narration="남건은 패배를 직감했다.",
            visual_subject="exactly one adult Goguryeo commander Namgeon",
            visual_scene=(
                "Chest-up view; Namgeon stands at center with exactly zero visible hands; "
                "his face is clearly visible; one breached timber gate remains behind him"
            ),
        )

        self.assertEqual(contract.person_count, 1)
        self.assertEqual(contract.framing, "chest-up")
        self.assertEqual(contract.face_visibility, "visible")
        self.assertEqual(len(contract.actors), 1)
        self.assertEqual(contract.actors[0].identity, "Namgeon")
        self.assertEqual(contract.actors[0].slot, "center")
        self.assertEqual(contract.actors[0].visible_hand_count, 0)
        self.assertEqual(contract.visible_hand_count, 0)
        self.assertTrue(any("timber gate" in prop for prop in contract.essential_props))

    def test_keeps_per_actor_hand_counts_and_poses(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults: Namsaeng and one Tang envoy",
            visual_scene=(
                "Namsaeng stands at left with exactly one visible right hand gripping one sealed packet; "
                "one Tang envoy stands at right with exactly one visible left hand receiving the packet"
            ),
        )

        self.assertEqual(contract.person_count, 2)
        self.assertEqual([actor.slot for actor in contract.actors], ["left", "right"])
        self.assertEqual([actor.visible_hand_count for actor in contract.actors], [1, 1])
        self.assertEqual(contract.visible_hand_count, 2)
        self.assertTrue(all(actor.hand_poses for actor in contract.actors))
        self.assertTrue(any("packet" in prop for prop in contract.essential_props))
        self.assertEqual(len(contract.contacts), 2)

    def test_does_not_infer_visual_geometry_from_narration(self) -> None:
        contract = build_scene_contract(
            narration="세 명의 장수가 성문 앞에서 논쟁했다.",
            visual_subject="Goguryeo commanders",
            visual_scene="Commanders argue near the fortress",
        )

        self.assertIsNone(contract.person_count)
        self.assertIsNone(contract.visible_hand_count)
        self.assertIsNone(contract.framing)
        self.assertIsNone(contract.face_visibility)
        self.assertEqual(contract.actors, ())
        self.assertIn("person_count:unknown", contract.diagnostics)
        self.assertEqual(contract.source_facts[0].source, "narration")
        self.assertEqual(contract.source_facts[0].text, "세 명의 장수가 성문 앞에서 논쟁했다.")

    def test_reports_conflicts_without_selecting_a_value(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly one adult commander",
            visual_scene=(
                "exactly two adults in a chest-up view and a wide shot; "
                "the face is visible but the face is hidden"
            ),
        )

        self.assertIsNone(contract.person_count)
        self.assertIsNone(contract.framing)
        self.assertIsNone(contract.face_visibility)
        self.assertIn("person_count:visual_subject_scene_conflict", contract.diagnostics)
        self.assertIn("framing:conflicting_explicit_values", contract.diagnostics)
        self.assertIn("face_visibility:conflicting_explicit_values", contract.diagnostics)

    def test_unspecified_hand_count_remains_unknown(self) -> None:
        contract = build_scene_contract(
            visual_subject="one adult Namgeon",
            visual_scene="Namgeon stands at left and his right hand grips a sword",
        )

        self.assertEqual(len(contract.actors), 1)
        self.assertIsNone(contract.actors[0].visible_hand_count)
        self.assertTrue(contract.actors[0].hand_poses)

    def test_accepts_explicit_adult_bodies_and_described_visible_hands(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two separate adult bodies",
            visual_scene=(
                "Namsaeng stands at left with exactly two visible empty hands resting at his sides; "
                "one envoy stands at right with both hands visible"
            ),
        )

        self.assertEqual(contract.person_count, 2)
        self.assertEqual([actor.visible_hand_count for actor in contract.actors], [2, 2])
        self.assertEqual(contract.visible_hand_count, 4)

    def test_parses_only_explicit_screen_wide_hand_count_phrases(self) -> None:
        cases = (
            ("exactly four visible hands", 4),
            ("four visible hands total", 4),
            ("all six hands visible", 6),
            ("both hands visible", 2),
            ("zero visible hands/fingers", 0),
        )
        for visual_scene, expected in cases:
            with self.subTest(visual_scene=visual_scene):
                contract = build_scene_contract(visual_scene=visual_scene)
                self.assertEqual(contract.visible_hand_count, expected)

    def test_does_not_promote_an_incomplete_actor_hand_count_to_global(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults",
            visual_scene=(
                "one guard stands at left with exactly two visible empty hands; "
                "one envoy stands at right"
            ),
        )

        self.assertEqual([actor.visible_hand_count for actor in contract.actors], [2, None])
        self.assertIsNone(contract.visible_hand_count)
        self.assertIn("visible_hand_count:unknown", contract.diagnostics)

    def test_reports_conflicting_global_hand_counts(self) -> None:
        contract = build_scene_contract(
            visual_scene="exactly four visible hands; all six hands visible",
        )

        self.assertIsNone(contract.visible_hand_count)
        self.assertIn("visible_hand_count:conflicting_explicit_values", contract.diagnostics)

    def test_reports_explicit_global_and_complete_actor_sum_conflict(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults",
            visual_scene=(
                "four visible hands total; "
                "one guard stands at left with exactly one visible left hand; "
                "one envoy stands at right with exactly one visible right hand"
            ),
        )

        self.assertIsNone(contract.visible_hand_count)
        self.assertIn("visible_hand_count:explicit_actor_sum_conflict", contract.diagnostics)

    def test_hand_poses_preserve_open_palm_pointing_and_fist_grip_phrases(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults",
            visual_scene=(
                "one guard stands at left with exactly one visible left hand pointing toward the gate "
                "with an open palm; "
                "one envoy stands at right with exactly one visible right hand gripping a sword "
                "in a clenched fist"
            ),
        )

        left_pose = contract.actors[0].hand_poses
        right_pose = contract.actors[1].hand_poses
        self.assertEqual(
            left_pose,
            ("exactly one visible left hand pointing toward the gate with an open palm",),
        )
        self.assertEqual(
            right_pose,
            ("exactly one visible right hand gripping a sword in a clenched fist",),
        )
        self.assertNotEqual(left_pose, right_pose)

    def test_standalone_open_palm_state_is_preserved(self) -> None:
        contract = build_scene_contract(
            visual_subject="one adult guard",
            visual_scene=(
                "one guard stands at left with exactly one visible left hand, "
                "open palm facing the viewer"
            ),
        )

        self.assertIn("open palm facing the viewer", contract.actors[0].hand_poses)

    def test_preserves_each_actor_hand_ownership_and_unused_hand_occlusion(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adult gate guards",
            visual_scene=(
                "Waist-up view; one guard stands at left and one envoy stands at right; "
                "exactly two visible hands total grip opposite beam ends with one hand from each adult; "
                "both far arms remain fully hidden behind their own torsos outside the frame"
            ),
        )

        self.assertEqual([actor.identity for actor in contract.actors], ["one guard", "one envoy"])
        self.assertEqual([actor.slot for actor in contract.actors], ["left", "right"])
        self.assertEqual([actor.visible_hand_count for actor in contract.actors], [1, 1])
        self.assertEqual(contract.visible_hand_count, 2)
        self.assertEqual(
            contract.unused_hand_constraints,
            ("both far arms remain fully hidden behind their own torsos outside the frame",),
        )

    def test_does_not_apply_each_actor_hand_count_when_actor_slots_are_incomplete(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults",
            visual_scene=(
                "one guard stands at left; one hand from each adult holds the beam; "
                "all other hands remain completely outside the frame"
            ),
        )

        self.assertEqual(len(contract.actors), 1)
        self.assertIsNone(contract.actors[0].visible_hand_count)
        self.assertIn("actor_hand_distribution:unresolved", contract.diagnostics)

    def test_leading_slot_actor_actions_preserve_hand_ownership(self) -> None:
        contract = build_scene_contract(
            visual_subject="exactly two adults, one envoy and one guard",
            visual_scene=(
                "waist-up view; exactly two visible hands total; "
                "the left envoy passes one sealed packet with his one visible right hand; "
                "the right guard receives the packet with his one visible left hand; "
                "every other hand and wrist remains fully hidden outside the frame"
            ),
        )

        self.assertEqual([actor.identity for actor in contract.actors], ["envoy", "guard"])
        self.assertEqual([actor.slot for actor in contract.actors], ["left", "right"])
        self.assertEqual([actor.visible_hand_count for actor in contract.actors], [1, 1])
        self.assertEqual(contract.visible_hand_count, 2)
        self.assertEqual(
            contract.unused_hand_constraints,
            ("every other hand and wrist remains fully hidden outside the frame",),
        )

    def test_serialization_and_hash_are_stable_after_whitespace_normalization(self) -> None:
        first = build_scene_contract(
            narration="한 문장",
            visual_subject="exactly   one adult Namgeon",
            visual_scene="Chest-up view; Namgeon stands at center",
        )
        second = build_scene_contract(
            narration="  한   문장  ",
            visual_subject=" exactly one adult Namgeon ",
            visual_scene=" Chest-up view;  Namgeon stands at center ",
        )

        self.assertEqual(first.version, SCENE_CONTRACT_VERSION)
        self.assertEqual(first.stable_hash(), second.stable_hash())
        payload = json.loads(first.canonical_json())
        self.assertEqual(payload["version"], SCENE_CONTRACT_VERSION)
        self.assertIn("visible_hand_count", payload)
        self.assertIn("unused_hand_constraints", payload)
        self.assertEqual(payload["actors"][0]["slot"], "center")


if __name__ == "__main__":
    unittest.main()
