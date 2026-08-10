from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.routers.image import _apply_image_prompt_profile, _build_image_prompt
from app.services.image.prompt_compiler import (
    SCENE_CONTRACT_V2,
    compile_image_prompt,
    configured_prompt_profile,
    is_baekje_ep01_bottom_credit_risk_scene,
    prepare_scene_contract_source,
    supports_scene_contract_v2_model,
)
from app.services.image import prompt_compiler as prompt_compiler_module
from app.services.image.prompt_builder import append_prompt_specific_negative_prompt
from app.services.image.asset_guard import expected_comfyui_positive_prompt
from app.services.image.comfyui_service import ComfyUIImageService
from app.services.image.comfyui_service import _FLUX2_BAEKJE_EP06_SHOT_DIRECTIONS
from app.services.image.comfyui_service import _LONGTUBE_DARK_MANHWA_STYLE_MODELS
from app.services.image.comfyui_service import _apply_longtube_dark_manhwa_style
from app.services.image.comfyui_service import _exact_layout_reference_spec
from app.services.image.comfyui_service import expected_effective_image_model_id
from app.services.image.comfyui_service import _flux2_baekje_ep06_visual_direction
from app.services.image.comfyui_service import _expected_grey_stone_marker_count
from app.services.image.comfyui_service import _expected_visible_hand_count
from app.services.image.comfyui_service import _image_has_busy_burning_sheet_background
from app.services.image.comfyui_service import _image_has_center_infographic_arrow
from app.services.image.comfyui_service import _image_has_guthe_record_cover_glyph_cluster
from app.services.image.comfyui_service import _image_has_internal_text_like_marks
from app.services.image.comfyui_service import _image_has_light_top_band
from app.services.image.comfyui_service import _image_grey_stone_marker_count
from app.services.image.comfyui_service import _image_has_multiple_edge_light_panels
from app.services.image.comfyui_service import _image_has_multiple_upper_light_panels
from app.services.image.comfyui_service import _image_has_solid_dark_outer_frame
from app.services.image.comfyui_service import _image_has_split_panel_divider
from app.services.image.comfyui_service import _image_has_top_caption_like_text
from app.services.image.comfyui_service import _image_has_textured_dark_perimeter_overlay
from app.services.image.comfyui_service import _image_has_wide_bottom_corner_credit_row
from app.services.image.comfyui_service import _should_check_internal_text_after_generation
from app.services.image.comfyui_service import _should_check_registry_seal_background_panels
from app.services.image.comfyui_service import _should_check_secret_route_edge_panels
from app.services.image.comfyui_service import _should_check_six_stone_marker_count
from app.services.image.comfyui_service import _should_check_split_panel_after_generation
from app.services.image.comfyui_service import _should_check_burning_sheet_background
from app.services.image.comfyui_service import _should_check_ch2_wide_bottom_credit
from app.services.image.comfyui_service import _should_check_starvation_wall_top_edge
from app.services.image.comfyui_service import _should_ignore_strict_nonhuman_person_segmentation
from app.services.image.comfyui_service import _should_ignore_object_person_segmentation
from app.services.image.comfyui_service import _should_ignore_top_caption_detector
from app.services.image.comfyui_service import _should_ignore_corner_signature_detector
from app.services.image.comfyui_service import _should_ignore_dark_outer_frame_detector
from app.services.image.comfyui_service import _should_ignore_split_panel_for_intentional_center_gap
from app.services.image.comfyui_service import _should_enforce_scene_human_face_count
from app.services.image.comfyui_service import _should_skip_dense_internal_text_grid
from app.services.image.comfyui_service import _should_skip_internal_text_core
from app.services.image.comfyui_service import _should_use_continuous_montage_banner_text_detector
from app.services.image.comfyui_service import _should_use_reduced_internal_text_detector
from app.services.image.comfyui_service import _should_use_physicalized_narration_text_detector
from app.services.image.comfyui_service import _should_use_ch2_riderless_border_gate_layout
from app.services.image.comfyui_service import _ch2_ep03_preflight_layout_spec
from app.services.llm.visual_policy import normalize_cut_image_prompt


class ImagePromptCompilerTests(unittest.TestCase):
    def compile(self, prompt: str, model: str = "comfyui-flux2-klein-4b"):
        return compile_image_prompt(prompt, model_id=model)

    def test_configured_cast_direction_does_not_inject_unwritten_person(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Released rivers flowing past Indra as Vritra broken oath "
                "remains visible; Scene: Released rivers flowing past Indra as Vritra "
                "broken oath remains visible, kinetic "
                "comparative Indo-European myth reconstruction with grounded ancient "
                "weapons, animals, landscapes, and dramatic creature combat"
            ),
            (
                "2D hard-boiled rugged masculine historical action cartoon, no "
                "photorealism. CAST DIRECTION: In context-appropriate human and mythic "
                "scenes, frequently include glamorous visibly adult women age 25 or "
                "older with confident sensual expressions and bold draped garments "
                "showing shoulders, collarbone, or midriff. Keep them story-active as "
                "priestesses, noblewomen, warriors, witnesses, or herders. No minors."
            ),
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertNotIn("Foreground cast:", compiled.positive)
        self.assertNotIn("visibly adult woman age 25 or older", compiled.positive)
        self.assertIn("Released rivers flowing past Indra", compiled.positive)
        self.assertIn("configured_cast_direction=off", compiled.diagnostics)

    def test_registered_trito_cattle_cave_lock_keeps_only_narrated_cast(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Ngwhi driving sacred cattle into a cave while a defeated "
                "Trito lies beside a broken shield; Scene: Ngwhi driving sacred cattle "
                "into a cave while a defeated Trito lies beside a broken shield, kinetic "
                "comparative Indo-European myth reconstruction with grounded ancient "
                "weapons, animals, landscapes, and dramatic creature combat, character "
                "continuity: Trito: young steppe warrior"
            ),
            (
                "2D historical action cartoon. CAST DIRECTION: frequently include "
                "glamorous visibly adult women age 25 or older. No minors."
            ),
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertIn("exactly one adult man Trito", compiled.positive)
        self.assertNotIn("adult woman", compiled.positive)
        self.assertIn("Three enormous snake heads", compiled.positive)
        self.assertIn("Trito lies defeated at lower left", compiled.positive)
        self.assertIn("second man", compiled.negative)
        self.assertIn("cattle brand", compiled.negative)
        self.assertIn("person_count=1", compiled.diagnostics)
        self.assertIn("configured_cast_direction=off", compiled.diagnostics)

    def test_registered_ep04_review_locks_remove_fake_text_and_fix_europa(self):
        drink = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Unknown prehistoric "
                    "drink beside later Soma; Scene: Unknown prehistoric drink beside "
                    "later Soma, mead, and wine vessels marked as comparisons, kinetic "
                    "comparative Indo-European myth reconstruction with grounded ancient "
                    "weapons, animals, landscapes, and dramatic creature combat, "
                    "period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly four completely blank unmarked", drink.positive)
        self.assertIn("Soma text", drink.negative)
        self.assertIn("person_count=0", drink.diagnostics)

        erytheia = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Map to far-western "
                    "Erytheia ending at Geryon's guarded red cattle; Scene: Map to "
                    "far-western Erytheia ending at Geryon's guarded red cattle, kinetic "
                    "comparative Indo-European myth reconstruction with grounded ancient "
                    "weapons, animals, landscapes, and dramatic creature combat, "
                    "period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("Wide natural seascape", erytheia.positive)
        self.assertIn("zero maps", erytheia.positive)
        self.assertIn("map", erytheia.negative)

        europa = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Europa seated "
                    "uncertainly on the white bull as the Phoenician coast recedes; "
                    "Scene: Europa seated uncertainly on the white bull as the "
                    "Phoenician coast recedes, kinetic comparative Indo-European myth "
                    "reconstruction with grounded ancient weapons, animals, landscapes, "
                    "and dramatic creature combat, period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly one visibly adult woman Europa", europa.positive)
        self.assertIn("male rider", europa.negative)
        self.assertIn("person_count=1", europa.diagnostics)

    def test_registered_ep04_three_hero_lock_requires_distinct_identities(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Trito; Scene: Trito, "
                    "Indra, and Heracles completing parallel restorations beyond "
                    "differing creatures, kinetic comparative Indo-European myth "
                    "reconstruction with grounded ancient weapons, animals, landscapes, "
                    "and dramatic creature combat, period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly three visibly distinct adult men", compiled.positive)
        self.assertIn("Trito at left has braided dark hair", compiled.positive)
        self.assertIn("clean-shaven Indra at center", compiled.positive)
        self.assertIn("curly-haired bearded Heracles at right", compiled.positive)
        self.assertIn("three identical men", compiled.negative)

    def test_registered_ep04_vritra_swallowing_lock_rejects_riding(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Colossal Vritra "
                    "swallowing the armored Indra as the gods recoil; Scene: Colossal "
                    "Vritra swallowing the armored Indra as the gods recoil, kinetic "
                    "comparative Indo-European myth reconstruction with grounded ancient "
                    "weapons, animals, landscapes, and dramatic creature combat, "
                    "period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("one visibly distended central belly", compiled.positive)
        self.assertIn("zero visible Indra", compiled.positive)
        self.assertIn("completely hidden inside the enlarged belly", compiled.positive)
        self.assertIn("leaving no body, corpse, armor", compiled.positive)
        self.assertIn("mounted rider", compiled.negative)
        self.assertIn("Indra riding Vritra", compiled.negative)
        self.assertIn("human-snake fusion", compiled.negative)
        self.assertIn("body beside snake", compiled.negative)

    def test_registered_ep04_geryon_lock_requires_one_joined_three_torso_body(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Geryon displaying "
                    "three armored torsos; Scene: Geryon displaying three armored "
                    "torsos, shields, spears, and coordinated movement, "
                    "period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly one mythic adult man Geryon total", compiled.positive)
        self.assertIn("exactly three armored upper torsos physically joined", compiled.positive)
        self.assertIn("one continuous hip and lower-body silhouette", compiled.positive)
        self.assertIn("three separate warriors", compiled.negative)
        self.assertIn("duplicate soldiers", compiled.negative)
        self.assertIn("person_count=1", compiled.diagnostics)

    def test_registered_ep04_geryon_defense_lock_rejects_minotaur(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Geryon defending "
                    "cattle while Greek heroic imagery casts him as the obstacle; "
                    "Scene: Geryon defending cattle while Greek heroic imagery casts "
                    "him as the obstacle, period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly one adult human Geryon total", compiled.positive)
        self.assertIn("three side-by-side human heads and three paired sets of human arms", compiled.positive)
        self.assertIn("minotaur", compiled.negative)
        self.assertIn("three separate warriors", compiled.negative)
        self.assertIn("ordinary one-headed man", compiled.negative)
        self.assertIn("horned head", compiled.negative)
        self.assertIn("person_count=1", compiled.diagnostics)
        self.assertNotIn("one adult with one head, one torso", compiled.positive)

    def test_registered_ep04_cacus_theft_lock_keeps_sleeping_heracles_and_cave(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Cacus dragging "
                    "selected red cattle away from sleeping Heracles at night; Scene: "
                    "Cacus dragging selected red cattle away from sleeping Heracles "
                    "at night, period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("one awake cave-dweller Cacus", compiled.positive)
        self.assertIn("human Heracles in plain red-brown wool lies asleep", compiled.positive)
        self.assertIn("one dark natural cave entrance", compiled.positive)
        self.assertIn("awake Heracles", compiled.negative)
        self.assertIn("missing cave", compiled.negative)
        self.assertIn("animal replacing Heracles", compiled.negative)
        self.assertNotIn("lion skin", compiled.positive)

    def test_registered_ep04_vritra_revenge_lock_rejects_random_beast(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Year/period: Mythic Prehistory; Main subject: Vritra emerging "
                    "behind Tvashtri while Indra realizes the personal cause; Scene: "
                    "Vritra emerging behind Tvashtri while Indra realizes the personal "
                    "cause, period-accurate clothing"
                ),
                "2D historical action cartoon",
            ),
            "comfyui-z-image-turbo",
        )
        self.assertIn("ordinary long black limbless snake Vritra", compiled.positive)
        self.assertIn("one continuous scaled neck-to-tail body", compiled.positive)
        self.assertIn("horned beast", compiled.negative)
        self.assertIn("dragon", compiled.negative)
        self.assertIn("person_count=2", compiled.diagnostics)

    def test_registered_indra_vritra_lock_keeps_single_indra_and_serpent(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Released rivers flowing past Indra as Vritra's broken "
                "oath remains visible; Scene: Released rivers flowing past Indra as "
                "Vritra's broken oath remains visible, character continuity: Indra"
            ),
            "2D historical action cartoon",
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertIn("exactly one adult man Indra total", compiled.positive)
        self.assertIn("ordinary long black snake Vritra with zero limbs", compiled.positive)
        self.assertIn("One natural snake Vritra lies motionless", compiled.positive)
        self.assertIn("zero human anatomy, zero arms, zero legs", compiled.positive)
        self.assertNotIn("adult woman", compiled.positive)
        self.assertIn("second person", compiled.negative)
        self.assertIn("quadruped Vritra", compiled.negative)

    def test_registered_heracles_hoofprint_lock_does_not_create_living_lion(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Heracles studying backward hoofprints beside a visibly "
                "reduced herd; Scene: Heracles studying backward hoofprints beside a "
                "visibly reduced herd, character continuity: Heracles"
            ),
            "2D historical action cartoon",
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertIn("exactly one adult man Heracles total", compiled.positive)
        self.assertNotIn("lion skin", compiled.positive)
        self.assertIn("living lion", compiled.negative)
        self.assertNotIn("adult woman", compiled.positive)
        self.assertIn("empty left hand points at the prints", compiled.positive)
        self.assertIn("round object in hand", compiled.negative)

    def test_registered_tvashtri_lock_uses_serpent_not_wolf(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Grieving Tvashtri raising Vritra from sacrificial fire "
                "after his son's death; Scene: Grieving Tvashtri raising Vritra from "
                "sacrificial fire after his son's death, character continuity: Tvashtri"
            ),
            "2D historical action cartoon",
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertIn("exactly one adult man Tvashtri total", compiled.positive)
        self.assertIn("one continuous scaled limbless body rise from the smoke", compiled.positive)
        self.assertIn("wolf", compiled.negative)
        self.assertIn("person_count=1", compiled.diagnostics)

    def test_registered_final_battle_lock_keeps_monster_and_three_heroes(self):
        source = prepare_scene_contract_source(
            (
                "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
                "Main subject: Trito; Scene: Trito, Indra, Heracles, and their wounded "
                "monsters in a final battle montage, character continuity: Trito"
            ),
            "2D historical action cartoon",
        )

        compiled = self.compile(source, "comfyui-z-image-turbo")

        self.assertIn("exactly three adult men total", compiled.positive)
        self.assertIn("Indra full body at lower center foreground", compiled.positive)
        self.assertIn("exactly three natural snake heads", compiled.positive)
        self.assertIn("human-versus-human battle", compiled.negative)
        self.assertIn("person_count=3", compiled.diagnostics)

    def _actual_baekje_ep01_prepared_fixture(self) -> dict:
        path = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa"
            r"\prepared_scripts\백제사-EP01_script.json"
        )
        if not path.is_file():
            self.skipTest("actual Baekje EP01 prepared-script fixture is not present")
        return json.loads(path.read_text(encoding="utf-8"))

    def _actual_baekje_ep01_script_fixture(self) -> dict:
        path = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\script.json"
        )
        if not path.is_file():
            self.skipTest("actual Baekje EP01 script fixture is not present")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _runtime_baekje_ep01_cut(payload: dict, cut_number: int) -> str:
        cut = payload["cuts"][cut_number - 1]
        normalized = normalize_cut_image_prompt(
            cut["image_prompt"],
            cut["narration"],
        )
        return prepare_scene_contract_source(
            normalized,
            narration_context=cut["narration"],
        )

    @staticmethod
    def _compiled_contract_field(positive: str, label: str, next_label: str) -> str:
        return positive.split(f"{label}: ", 1)[1].split(f". {next_label}:", 1)[0]

    def test_ch2_registered_myth_scenes_preserve_visible_actor_counts(self):
        trailer = (
            ", symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe, "
            "Proto-Indo-European cultural community, period-accurate clothing, architecture, "
            "tools, and material culture, 50mm portrait lens, image only, no text, no watermark"
        )
        cases = (
            (
                "A heavy, bloody iron blade cleanly slicing through an elegant, peaceful dinner setting",
                "Tsukuyomi swings one archaic bronze blade",
            ),
            (
                "Tsukuyomi standing over a corpse, his silver sword dripping blood, his face cold and unfeeling",
                "fully shrouded Uke Mochi",
            ),
            (
                "Manu and Yemo walking through an empty cosmic plain beside a white cow",
                "pair",
                2,
            ),
            (
                "Trito, Trita, and Thraetona battling serpent figures beside recovered captives and cattle",
                "object",
                0,
            ),
            (
                "Sleeping Ymir generating a male and female beneath his arms and another being from his legs",
                "object",
                0,
            ),
            (
                "Vedic Trita confronting the massive serpent Vritra near trapped cattle and water",
                "single",
                1,
            ),
            (
                "Ritual blade, twin figures, serpent, and cattle forming a final symbolic tableau",
                "pair",
                2,
            ),
        )
        for scene, expected_kind, expected_count in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    scene + trailer,
                    "comfyui-dreamshaper-xl-longtube-v15",
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                if expected_kind != "single":
                    self.assertNotIn("Composition: one adult body", compiled.positive)
                if "white cow" in scene:
                    self.assertIn("exactly one cow total", compiled.positive)
                    self.assertIn("exactly three full-body slots", compiled.positive)
                    self.assertIn("second cow", compiled.negative)
                    self.assertIn("cattle herd", compiled.negative)
                    self.assertIn("green grass", compiled.negative)

    def test_ch2_symbolic_body_transformation_does_not_force_one_adult(self):
        compiled = self.compile(
            "Yemo's divided silhouette transforming into earth, sky, wind, water, sun, and moon, "
            "symbolic Proto-Indo-European myth reenactment grounded in prehistoric Pontic-Caspian "
            "steppe materials, Mythic Prehistory, Pontic-Caspian Steppe, 85mm portrait lens, image only",
            "comfyui-dreamshaper-xl-longtube-v15",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertNotIn("Composition: one adult body", compiled.positive)
        self.assertIn("Top-down stone relief", compiled.positive)

    def test_ch2_registered_myth_problem_scenes_receive_semantic_locks(self):
        trailer = (
            ", symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe, "
            "Proto-Indo-European cultural community, period-accurate clothing and tools"
        )
        cases = (
            (
                "Yemo's divided silhouette transforming into earth, sky, wind, water, sun, and moon",
                ("six separated", "earth, sky, wind, water, sun and moon"),
                ("trident", "intact standing man"),
            ),
            (
                "Defeated Ngwhi beneath Trito as frightened cattle stream out of the cave",
                ("ordinary black snake representing Ngwhi", "one adult man Trito"),
                ("minotaur", "horned humanoid"),
            ),
            (
                "Sleeping Ymir generating a male and female beneath his arms and another being from his legs",
                ("object-only one flat prehistoric stone relief panel", "three separate small silhouettes"),
                ("living giant", "bound prisoner"),
            ),
            (
                "Ritual blade, twin figures, serpent, and cattle forming a final symbolic tableau",
                ("exactly two ordinary adult human twin brothers", "one central straight bronze blade"),
                ("third person", "giant"),
            ),
        )
        for scene, positive_terms, negative_terms in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    scene + trailer,
                    "comfyui-dreamshaper-xl-longtube",
                )
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                for term in negative_terms:
                    self.assertIn(term, compiled.negative)
                if scene.startswith("Sleeping Ymir"):
                    self.assertIn("one dominant object", compiled.positive)
                    self.assertNotIn("far left, center-left", compiled.positive)

    def test_ch2_registered_symbolic_scenes_use_object_relief_fallback(self):
        trailer = (
            ", symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe, "
            "period-accurate clothing and tools"
        )
        cases = (
            "Human anatomical outline aligned with mountains, rivers, moon, clouds, and heavens",
            "Parallel Roman and Vedic sacrifice tables with portions assigned by rank",
            "Trito, Trita, and Thraetona battling serpent figures beside recovered captives and cattle",
        )
        for scene in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(scene + trailer, "comfyui-dreamshaper-xl-longtube")
                self.assertEqual(compiled.scene_kind, "object")
                self.assertEqual(compiled.person_count, 0)
                self.assertIn("object-only", compiled.positive)
                self.assertIn("living person", compiled.negative)

    def test_ch2_flux_registered_scenes_use_literal_semantic_composition(self):
        trailer = (
            ", symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe, "
            "period-accurate clothing and tools"
        )
        cases = (
            (
                "Featureless primordial darkness without land, sky, stars, or horizon",
                "landscape",
                0,
                ("only layered charcoal-black", "no central subject"),
            ),
            (
                "Deep primordial chasm with faint mist gathering but no defined landscape",
                "landscape",
                0,
                ("bottomless black chasm", "no human silhouette"),
            ),
            (
                "Yemo's uncertain silhouette before the ritual",
                "single",
                1,
                (
                    "exactly one adult human Yemo total",
                    "completely covers his entire head",
                ),
            ),
            (
                "Manu arranging ritual portions beside a fire as the first priestly figure",
                "single",
                1,
                ("exactly one adult human Manu total", "entire right half remains empty ground"),
            ),
            (
                "Red symbolic current clearing into rivers across a newborn landscape",
                "landscape",
                0,
                ("landscape-only empty newborn prehistoric steppe", "both banks remain completely empty"),
            ),
            (
                "Gayomart and the primeval ox standing before the destructive spirit Ahriman",
                "single",
                1,
                ("exactly one adult human Gayomart total", "one shapeless black smoke mass"),
            ),
            (
                "Early chieftain receiving a staff of authority beside an ancestral sacrificial hearth",
                "single",
                1,
                ("exactly one adult human early chieftain total", "no giver"),
            ),
            (
                "Ngwhi coiling around cattle and forcing them toward a mountain pass",
                "animal",
                0,
                ("one clearly visible natural snake head", "wide empty gaps keep every cow separate"),
            ),
            (
                "Trito knocked backward by Ngwhi during a failed first attack",
                "single",
                1,
                ("exactly one adult human Trito total", "serpent's single head lunges from far right"),
            ),
            (
                "Three serpent heads emerging from darkness beside an ancient negation symbol",
                "animal",
                0,
                ("exactly three natural black snake heads", "no decorative perimeter"),
            ),
            (
                "God, warrior, herder, and priest linked around a central sacrificial fire",
                "group",
                4,
                ("exactly four adult people total", "priest at far right"),
            ),
            (
                "War leader pointing toward enemy herders while invoking a serpent emblem",
                "group",
                3,
                ("exactly three adult people total", "flat-painted-black-serpent-emblem rawhide shield"),
            ),
            (
                "Ahriman's shadow over the fallen ox as animals and vegetation emerge",
                "animal",
                0,
                ("animal-only one ordinary fallen primeval ox", "one shapeless black smoke cloud"),
            ),
            (
                "Odin-like Norse figure marked as the Third beside an ash spear",
                "single",
                1,
                ("exactly one adult human Odin-like Norse figure total", "three small parallel notches visible"),
            ),
            (
                "Yama's warm ancestral hall transforming into a severe underworld court",
                "single",
                1,
                ("exactly one adult human Yama total", "one empty severe throne"),
            ),
            (
                "Yama stepping away from Yami with a firm raised hand",
                "pair",
                2,
                ("exactly two adult human twins total", "wide clear ground gap"),
            ),
            (
                "Twin silhouettes separating as a birth symbol fades and a funerary road appears",
                "pair",
                2,
                ("exactly two adult human twin silhouettes total", "one empty dark funerary road"),
            ),
            (
                "Yima directing construction of the underground Vara with timber chambers and stored seed",
                "single",
                1,
                ("exactly one adult human Yima total", "no worker, helper, or other person"),
            ),
            (
                "Families, livestock, seeds, and lamps sheltered inside the underground Vara",
                "group",
                None,
                ("broad rectangular timber chamber", "no cave mouth"),
            ),
            (
                "Three Iranian religious figures receiving separate ritual roles once associated with Manu",
                "pair",
                2,
                ("exactly two adult human Iranian religious figures total", "a shapeless black smoke mass at far left"),
            ),
            (
                "Three Norse gods hauling Ymir's colossal body into the center of Ginnungagap",
                "group",
                3,
                ("exactly three living standing adult Norse gods total", "one enormous full-length fallen human-shaped Ymir body"),
            ),
            (
                "Yama, Yima, Ymir, and Remus aligned with death roads, crowns, and foundations",
                "group",
                4,
                ("exactly four adult human men total", "no cave, arch, doorway, portal, canopy, or enclosing shape"),
            ),
            (
                "Yama walking the first death road and taking his seat before the underworld gate",
                "single",
                1,
                ("exactly one adult human Yama total", "one empty stone throne"),
            ),
            (
                "Ritual blade, ruler's staff, cattle herd, serpent, and warrior spear around one fire",
                "animal",
                0,
                ("object-and-animal-only symbolic arrangement", "with no human"),
            ),
            (
                "Prehistoric priests repeating a cattle ritual beneath a cosmic body diagram",
                "pair",
                2,
                ("exactly two adult prehistoric priests total", "one flat carved human outline"),
            ),
            (
                "Hands placing measured ritual portions around a circular cosmic diagram",
                "object",
                0,
                ("Exactly four separate hands", "one unmarked circular stone platter"),
            ),
            (
                "Recovered cattle crossing back toward a lawful ritual enclosure at sunrise",
                "animal",
                0,
                ("animal-only one ordinary cattle herd", "no signboard"),
            ),
            (
                "Two competing scholarly reconstructions displayed beside the same fragmentary myth",
                "object",
                0,
                ("one cracked blank stone relief", "two visibly different unmarked clay reconstruction models"),
            ),
            (
                "Competing flood and lethal winter scenes surrounding Yima's underground refuge",
                "landscape",
                0,
                ("one sealed low underground refuge", "with zero people and no split panel"),
            ),
            (
                "Jaan Puhvel comparing Yemo and Remus beside early Latin inscriptions",
                "single",
                1,
                ("exactly one older adult male scholar total", "two small unmarked featureless clay human figurines"),
            ),
            (
                "Three-headed Ngwhi driving sacred cattle toward a black mountain cave",
                "animal",
                0,
                ("Exactly three black snake heads", "shared body remains fully hidden"),
            ),
            (
                "Celestial cattle gift interrupted by Ngwhi sweeping the herd into darkness",
                "animal",
                0,
                ("exactly three ordinary snake heads", "wide empty ground gap"),
            ),
            (
                "Empty prehistoric ritual ground surrounded by later fragmented manuscripts",
                "landscape",
                0,
                ("exactly five closed face-down blank manuscript fragments", "no people anywhere"),
            ),
            (
                "Indian, Iranian, Norse, Roman, and Baltic sources aligned around shared actions",
                "object",
                0,
                ("exactly five blank closed manuscript bundles", "no people"),
            ),
            (
                "Split tableau of Manu's sacrifice and Ngwhi stealing Trito's cattle",
                "pair",
                2,
                ("One continuous undivided steppe view", "one long limbless black serpent"),
            ),
            (
                "Manu as priest, Yemo as first king, and Trito as armed protector",
                "group",
                3,
                ("Exactly three separated foreground men", "no background people"),
            ),
            (
                "Yemo's divided silhouette transforming into earth, sky, wind, water, sun, and moon",
                "single",
                1,
                ("exactly one adult Yemo total", "right eye into a silver moon"),
            ),
            (
                "Human anatomical outline aligned with mountains, rivers, moon, clouds, and heavens",
                "scene",
                None,
                ("monumental human anatomical outline", "river veins"),
            ),
            (
                "Sleeping Ymir generating a male and female beneath his arms and another being from his legs",
                "object",
                0,
                (
                    "one continuous flat prehistoric stone surface",
                    "exactly four separate simple petroglyphs total",
                ),
            ),
            (
                "Yima dividing cooked cattle portions while stern Zoroastrian priests observe",
                "group",
                5,
                ("exactly five adult people total", "priest four at far right"),
            ),
            (
                "Trito, Trita, and Thraetona battling serpent figures beside recovered captives and cattle",
                "group",
                5,
                ("exactly five adult people total", "exactly two fully visible rescued adults"),
            ),
        )
        for scene, expected_kind, expected_count, positive_terms in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(scene + trailer, "comfyui-flux2-klein-4b")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                if expected_kind != "object":
                    self.assertNotIn("object-only one flat prehistoric", compiled.positive)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                if scene.startswith("Manu arranging ritual portions"):
                    self.assertNotIn("with both hands", compiled.positive)
                    self.assertIn("hand close-up", compiled.negative)
                if scene.startswith("Early chieftain receiving a staff"):
                    self.assertNotIn("gripping", compiled.positive)
                    self.assertNotIn("right hand", compiled.positive)
                    self.assertIn("oversized foreground hand", compiled.negative)
                if scene.startswith("Trito knocked backward"):
                    self.assertNotIn("hand raised", compiled.positive)
                    self.assertIn("shoulders twisted and torso leaning away", compiled.positive)
                if scene.startswith("War leader pointing"):
                    self.assertIn("war leader at far left points toward two herders", compiled.positive)
                    self.assertIn("far-right herder keeps both arms lowered", compiled.positive)
                    self.assertIn("second pointing person", compiled.negative)
                    self.assertIn("pointing herder", compiled.negative)
                if scene.startswith("Hands placing measured ritual portions"):
                    self.assertIn("Exactly four separate hands", compiled.positive)
                if "three-headed" in scene.lower():
                    self.assertNotIn("one head, one jaw", compiled.positive)
                if scene.startswith("Split tableau"):
                    self.assertNotIn("Source workbook scene: Split tableau", compiled.positive)
                if scene.startswith("Sleeping Ymir"):
                    self.assertNotIn("male and female beneath his arms", compiled.positive)

    def test_ch2_registered_lock_survives_intervening_scene_qualifier(self):
        compiled = self.compile(
            "Year/period: Mythic Prehistory; Scene evidence: Source workbook scene: "
            "Yama stepping away from Yami with a firm raised hand; Main subject: "
            "Yama stepping away from Yami with a firm raised hand; Scene: "
            "Yama stepping away from Yami with a firm raised hand, no physical contact, "
            "symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe",
            "comfyui-flux2-klein-4b",
        )
        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("exactly two adult human twins total", compiled.positive)
        self.assertIn("Yami stands at the right foreground", compiled.positive)

    def test_ch2_registered_text_risk_scenes_force_internal_text_check(self):
        scenes = (
            "Prehistoric priests repeating a cattle ritual beneath a cosmic body diagram",
            "Hands placing measured ritual portions around a circular cosmic diagram",
            "Recovered cattle crossing back toward a lawful ritual enclosure at sunrise",
            "Two competing scholarly reconstructions displayed beside the same fragmentary myth",
            "Competing flood and lethal winter scenes surrounding Yima's underground refuge",
            "Jaan Puhvel comparing Yemo and Remus beside early Latin inscriptions",
        )
        for scene in scenes:
            with self.subTest(scene=scene):
                self.assertTrue(_should_check_internal_text_after_generation(scene))

    def test_ch2_text_risk_false_positive_exceptions_are_scene_scoped(self):
        self.assertTrue(
            _should_ignore_object_person_segmentation(
                "Exactly four separate hands place exactly four measured meat portions into four clean sectors"
            )
        )
        self.assertTrue(
            _should_ignore_object_person_segmentation(
                "one cracked blank stone relief at center and two visibly different unmarked clay reconstruction models"
            )
        )
        self.assertTrue(
            _should_skip_dense_internal_text_grid(
                "one sealed low underground refuge between rising floodwater and advancing snowdrifts"
            )
        )
        self.assertTrue(
            _should_skip_internal_text_core(
                "One older scholar at center studies two small blank stone face-relief casts"
            )
        )
        self.assertTrue(
            _should_use_reduced_internal_text_detector(
                "one unmarked circular stone platter viewed from directly overhead"
            )
        )
        self.assertTrue(
            _should_use_reduced_internal_text_detector(
                "Hands placing measured ritual portions around a circular cosmic diagram"
            )
        )
        self.assertTrue(
            _should_use_reduced_internal_text_detector(
                "Prehistoric priests repeating a cattle ritual beneath a cosmic body diagram"
            )
        )
        self.assertFalse(
            _should_enforce_scene_human_face_count(
                "single",
                "One older scholar at center studies two small blank stone face-relief casts",
            )
        )
        preflight_phrases = (
            "Decorated white stallion entering a rival kingdom as villagers and armed guards freeze",
            "Several Rival rulers receiving news of the approaching horse and weighing weapons against tribute",
            "Bards singing as four thousand symbolic cattle and gold gifts pass before priests",
            "Royal escorts reopening the gate as the defeated Rival ruler offers formal submission",
            "Sacrificing king receiving the procession from a raised platform before the capital",
            "Royal horse standing between divided factions as Yudhishthira approaches",
            "Large ritual cauldron and white mare imagery around the Irish claimant",
            "Royal stallion walking between open gates",
            "Gupta gold coin showing a horse before a sacrificial post in close detail",
            "Reverse of an Ashvamedha coin with queen figure and royal inscription shapes",
        )
        for phrase in preflight_phrases:
            with self.subTest(layout_phrase=phrase):
                spec = _ch2_ep03_preflight_layout_spec(
                    f"Year/period: 3000 BCE to 1000 BCE; Source workbook scene: {phrase}"
                )
                self.assertIsNotNone(spec)
                self.assertTrue(spec[1].exists())
        self.assertTrue(
            _should_enforce_scene_human_face_count(
                "single",
                "Jaan Puhvel comparing Yemo and Remus beside early Latin inscriptions",
            )
        )
        self.assertTrue(_should_enforce_scene_human_face_count("single", "generic portrait"))
        self.assertTrue(
            _should_ignore_dark_outer_frame_detector(
                "Jaan Puhvel comparing Yemo and Remus beside early Latin inscriptions"
            )
        )
        self.assertFalse(_should_ignore_dark_outer_frame_detector("generic scholar portrait"))
        self.assertFalse(_should_ignore_object_person_segmentation("generic object scene"))
        self.assertFalse(_should_skip_dense_internal_text_grid("generic landscape"))
        self.assertFalse(_should_skip_internal_text_core("generic scholar portrait"))

    def test_ch2_registered_generic_scene_rejects_humanoid_animal_hybrids(self):
        compiled = self.compile(
            "Sacred cattle surrounded by herders, ritual vessels, food stores, and armed guards, "
            "symbolic Proto-Indo-European myth reenactment grounded in prehistoric Pontic-Caspian "
            "steppe materials, Mythic Prehistory, Pontic-Caspian Steppe",
            "comfyui-flux2-klein-4b",
        )
        self.assertIn("minotaur", compiled.negative)
        self.assertIn("bull-headed humanoid", compiled.negative)
        self.assertIn("snake-cow hybrid", compiled.negative)

    def test_animal_scene_does_not_enforce_human_face_count(self):
        self.assertFalse(_should_enforce_scene_human_face_count("animal"))
        self.assertTrue(_should_enforce_scene_human_face_count("single"))
        self.assertTrue(_should_enforce_scene_human_face_count("object"))

    def test_featureless_primordial_darkness_ignores_false_person_segmentation(self):
        prompt = "Featureless primordial darkness without land, sky, stars, or horizon"
        self.assertTrue(_should_ignore_object_person_segmentation(prompt))

    def test_ch2_cattle_breath_scene_ignores_only_strict_partial_person_segmentation(self):
        prompt = "A final breath sweeping across grass, clouds, fire smoke, and grazing cattle"
        self.assertFalse(_should_ignore_object_person_segmentation(prompt))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(prompt))

    def test_ch2_red_river_scene_ignores_false_corner_signature(self):
        prompt = "Red symbolic current clearing into rivers across a newborn landscape"
        self.assertTrue(_should_ignore_corner_signature_detector(prompt))

    def test_ch2_serpent_emblem_scene_ignores_false_top_caption(self):
        prompt = "War leader pointing toward enemy herders while invoking a serpent emblem"
        self.assertTrue(_should_ignore_top_caption_detector(prompt))
        self.assertTrue(_should_check_ch2_wide_bottom_credit(prompt))

    def test_flux_hardboiled_global_style_normalizes_to_dark_manhwa(self):
        source = prepare_scene_contract_source(
            "Year/period: Mythic Prehistory; Exact place: Pontic-Caspian Steppe; "
            "Main subject: exactly one adult steppe warrior; Scene: One warrior stands in wind",
            "2D hard-boiled rugged adult historical story cartoon, extra-thick bold black ink "
            "contour lines, matte cel shading, no photorealism",
        )
        compiled = self.compile(source, "comfyui-flux2-klein-4b")

        self.assertIn("mature vintage dark historical", compiled.positive)
        self.assertIn("variable-width scratchy dip-pen contour lines", compiled.positive)
        self.assertIn("dense hatching with intersecting hatch strokes", compiled.positive)
        self.assertIn("aged fibrous print-stock grain", compiled.positive)
        self.assertNotIn("extra-thick bold black ink contour lines", compiled.positive)
        self.assertNotIn("matte cel shading", compiled.positive)
        self.assertNotIn("cinematic concept art", compiled.positive)

    def test_ch2_flux_table_and_central_blade_use_scoped_detector_exemptions(self):
        trailer = (
            ", symbolic Proto-Indo-European myth reenactment grounded in prehistoric "
            "Pontic-Caspian steppe materials, Mythic Prehistory, Pontic-Caspian Steppe"
        )
        tables = self.compile(
            "Parallel Roman and Vedic sacrifice tables with portions assigned by rank" + trailer,
            "comfyui-flux2-klein-4b",
        )
        blade = self.compile(
            "Ritual blade, twin figures, serpent, and cattle forming a final symbolic tableau" + trailer,
            "comfyui-flux2-klein-4b",
        )
        ymir = self.compile(
            "Sleeping Ymir generating a male and female beneath his arms and another being from his legs" + trailer,
            "comfyui-flux2-klein-4b",
        )

        self.assertTrue(_should_ignore_object_person_segmentation(tables.positive))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(tables.positive))
        self.assertTrue(_should_ignore_object_person_segmentation(ymir.positive))
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(ymir.positive))
        self.assertTrue(_should_ignore_split_panel_for_intentional_center_gap(blade.positive))

    def test_ch2_yima_tableau_uses_scoped_verified_top_caption_exemption(self):
        prompt = (
            "Yima visibly cuts cooked meat into three separate portions on one low table; "
            "four ancient Iranian ritualists watch his hands"
        )
        self.assertTrue(_should_ignore_top_caption_detector(prompt))
        self.assertFalse(_should_ignore_top_caption_detector("Generic historical ritual scene"))

    def test_ch2_role_triad_uses_scoped_wide_bottom_credit_detector(self):
        self.assertTrue(
            _should_check_ch2_wide_bottom_credit(
                "Manu as priest, Yemo as first king, and Trito as armed protector"
            )
        )
        self.assertFalse(_should_check_ch2_wide_bottom_credit("Generic historical trio"))

    @staticmethod
    def _structured_baekje_ep01_cut(payload: dict, cut_number: int) -> str:
        world = payload["visual_world"]
        cut = payload["cuts"][cut_number - 1]
        return (
            f"Global visual world: Time range: {world['time_range']}; "
            f"Place scope: {world['place_scope']}; Culture scope: {world['culture_scope']}; "
            f"Material culture: {world['material_culture']}; "
            f"Continuity rule: {world['continuity_rule']}; "
            f"Year/period: {cut['visual_year']}; {cut['visual_period']}; "
            f"Exact place: {cut['visual_location']}; Scene evidence: {cut['visual_evidence']}; "
            "Style: serious adult graphic novel illustration, mature documentary manhwa style, "
            "bold black ink outlines; "
            f"Scene: {cut['image_prompt']} || Narration context: {cut['narration']}"
        )

    def test_runtime_profile_defaults_to_v2_for_every_channel(self):
        for channel in (1, 2, 3, 4, 99):
            self.assertEqual(configured_prompt_profile({"channel": channel}), SCENE_CONTRACT_V2)
        self.assertEqual(configured_prompt_profile({"image_prompt_profile": "legacy"}), "")

        class Service:
            def __init__(self, model_id: str):
                self.model_id = model_id

        flux = Service("comfyui-flux2-klein-4b")
        sdxl = Service("comfyui-dreamshaper-xl-longtube")
        dreamshaper = Service("comfyui-dreamshaper-xl-longtube")
        z_image = Service("comfyui-z-image-turbo")
        sd15 = Service("comfyui-sd15")
        self.assertEqual(_apply_image_prompt_profile(flux, {"channel": 1}), SCENE_CONTRACT_V2)
        self.assertEqual(_apply_image_prompt_profile(sdxl, {"channel": 1}), SCENE_CONTRACT_V2)
        self.assertEqual(_apply_image_prompt_profile(z_image, {"channel": 1}), SCENE_CONTRACT_V2)
        self.assertEqual(_apply_image_prompt_profile(dreamshaper, {"image_prompt_profile": "legacy"}), "")
        self.assertEqual(_apply_image_prompt_profile(sd15, {"channel": 1}), "")
        self.assertTrue(supports_scene_contract_v2_model("comfyui-flux2-klein-9b"))
        self.assertTrue(supports_scene_contract_v2_model("comfyui-dreamshaper-xl-longtube-v15"))
        self.assertTrue(supports_scene_contract_v2_model("comfyui-z-image-turbo"))
        self.assertTrue(supports_scene_contract_v2_model("comfyui-z-image-base"))
        self.assertFalse(supports_scene_contract_v2_model("openai-image-2"))

    def test_goguryeo_architecture_negative_keeps_signboard_bans_in_budget(self):
        compiled = self.compile(
            "Era/period: late seventh-century Goguryeo succession; "
            "Exact place: Goguryeo court and fortress district; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            "Primary subject: one adult traitor; "
            "Visible action: the traitor stands at the front of the enemy army"
        )

        for term in (
            "gate signboard",
            "signboard above door",
            "overdoor plaque",
            "rectangular lintel plaque",
            "characters on building",
        ):
            self.assertIn(term, compiled.negative)
        self.assertLessEqual(len(compiled.negative), 520)

    def test_actual_baekje_ep01_brother_cuts_keep_declared_identity_when_fixture_exists(self):
        script_path = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\script.json"
        )
        if not script_path.is_file():
            self.skipTest("actual Baekje EP01 script fixture is not present")

        payload = json.loads(script_path.read_text(encoding="utf-8"))
        for cut_number in (14, 20, 39, 43):
            cut = payload["cuts"][cut_number - 1]
            normalized = normalize_cut_image_prompt(
                cut["image_prompt"],
                cut["narration"],
            )
            with self.subTest(cut=cut_number):
                self.assertIn(
                    "Year/period: Late 1st century BC foundation tradition through the early reign of King Onjo",
                    normalized,
                )
                self.assertIn(
                    "Exact place: Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, and Ugok Fortress",
                    normalized,
                )
                self.assertIn(
                    "Culture scope: Goguryeo, Mahan, and Baekje",
                    normalized,
                )
                self.assertNotIn("666-668 AD Goguryeo succession", normalized)
                self.assertNotIn("7th-c. Goguryeo and Tang", normalized)

    def test_late_seventh_century_goguryeo_succession_override_remains_enabled(self):
        normalized = normalize_cut_image_prompt(
            "Year/period: 666-668 AD; Exact place: Goguryeo court and fortress district; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            "Scene evidence: Yeon Namsaeng and the Goguryeo succession crisis; "
            "Scene: two brothers contest control of the court",
            "형제의 권력 다툼으로 고구려 조정이 갈라졌습니다.",
        )

        self.assertIn("Year/period: 666-668 AD Goguryeo succession", normalized)
        self.assertIn("Culture scope: 7th-c. Goguryeo and Tang", normalized)

    def test_declared_baekje_period_blocks_generic_pyongyang_succession_and_river_routing(self):
        normalized = normalize_cut_image_prompt(
            "Global visual world: Time range: 346-375 AD; "
            "Place scope: the Han River basin and the Pyongyang Fortress area in Hwanghae; "
            "Culture scope: Baekje and Goguryeo; Year/period: 346-375 AD; "
            "Exact place: the Han River basin and the Pyongyang Fortress area in Hwanghae; "
            "Scene evidence: Baekje succession and river transport; "
            "Scene: Baekje leaders secure maritime transport routes near the river",
            "백제는 서남부 세력과 해상 교통로를 붙잡아 맞설 힘을 키우고 있었죠",
        )

        self.assertIn("346-375 AD", normalized)
        for leaked_term in ("612 AD", "Sui-Goguryeo", "666-668 AD", "7th-c. Goguryeo and Tang"):
            self.assertNotIn(leaked_term, normalized)

    def test_baekje_focused_gestures_scene_is_not_demoted_to_object(self):
        compiled = self.compile(
            "Global visual world: Time range: 346-375 AD; "
            "Place scope: the Han River basin and the Pyongyang Fortress area in Hwanghae; "
            "Culture scope: Baekje and Goguryeo; Year/period: 346-375 AD; "
            "Scene: Documentary long-lens view at a historically grounded Baekje settlement, "
            "visualizing a decisive historical beat. Focused gestures, one decisive object, "
            "and surrounding reactions make the immediate historical stakes readable, "
            "35mm lens, cinematic 16:9"
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertIn("4th-century Hanseong Baekje", compiled.positive)
        self.assertIn("plain hemp cross-collar robes", compiled.positive)
        self.assertIn("undecorated timber-and-rammed-earth buildings", compiled.positive)
        for term in (
            "samurai",
            "katana",
            "Edo-period kimono",
            "hakama",
            "Japanese castle",
            "hanging gate signboard",
            "signboard above doorway",
        ):
            self.assertIn(term, compiled.negative)

    def test_baekje_fourth_century_audience_hall_blocks_fake_architecture_text(self):
        compiled = self.compile(
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje and "
            "Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
            "Scene: Ground-level action frame at a guarded Baekje audience hall, "
            "visualizing father-son succession through a royal seal and guarded doorway"
        )

        self.assertIn("undecorated timber-and-rammed-earth buildings", compiled.positive)
        for term in (
            "architectural signboard",
            "characters on architecture",
            "hanging gate signboard",
            "signboard above doorway",
        ):
            self.assertIn(term, compiled.negative)

    def test_baekje_384_reception_uses_early_hanseong_material_culture(self):
        compiled = self.compile(
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Year/period: 384 AD; Exact place: Hanseong and the western sea route; "
            "Scene evidence: Source workbook row 06-010 anchors this scene to 384 AD; "
            "Scene: Close material-detail composition in a timber temple courtyard during "
            "one ceremony, visualizing this decisive historical beat: In the year 384, the "
            "king of Baekje summoned a strange monk from across the sea to the palace. One "
            "ritual gesture and one crafted sacred object hold the frame. || "
            "Narration context: 삼백팔십사년, 바다 건너온 낯선 승려를 백제 왕이 궁으로 불러들였습니다"
        )

        self.assertIn("late-fourth-century Baekje court reception", compiled.positive)
        self.assertIn("exactly three adult men without hats or crowns", compiled.positive)
        self.assertIn("Buddhist monk Marananta", compiled.positive)
        self.assertIn("King Chimnyu has natural black hair fully covering his scalp", compiled.positive)
        self.assertIn("uninterrupted blank rough reed-mat", compiled.positive)
        self.assertIn("TIGHT THREE-PERSON CHEST-UP PORTRAIT", compiled.positive)
        self.assertNotIn("timber temple courtyard", compiled.positive)
        for term in (
            "tiled roof",
            "roof visible overhead",
            "black court cap",
            "architectural signboard",
        ):
            self.assertIn(term, compiled.negative)
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )
        self.assertTrue(styled.startswith("EARLY FOURTH-CENTURY MATERIAL LOCK:"))
        self.assertIn("EXACT BAEKJE RECEPTION CROP:", styled)
        self.assertIn("Marananta alone has one fully clean-shaven scalp", styled)
        self.assertIn("King Chimnyu and the official each have natural black hair", styled)
        self.assertNotIn("Broad irregular local ground and sky texture", styled)

    def test_baekje_384_record_scene_removes_bound_book_and_paper(self):
        compiled = self.compile(
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Year/period: 384 AD; Exact place: Hanseong; "
            "Scene: Documentary long-lens view at a quiet archive table beside a weathered "
            "chronicle, visualizing a disputed historical record"
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("Object-only strict overhead material-evidence view", compiled.positive)
        self.assertIn("one orderly row of separate blank narrow wooden slips", compiled.positive)
        self.assertIn("one continuous rough reed mat", compiled.positive)
        self.assertIn("bound book", compiled.negative)
        self.assertIn("paper sheet", compiled.negative)
        self.assertNotIn("quiet archive table", compiled.positive)
        self.assertNotIn("weathered chronicle", compiled.positive)

    def test_baekje_384_west_sea_route_uses_boats_instead_of_capital_walls(self):
        compiled = self.compile(
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Year/period: 384 AD; Exact place: Hanseong and the western sea route; "
            "Scene evidence: Source workbook row 06-016 anchors this scene to 384 AD; "
            "Scene: Closing wide composition across the earthen walls of the Hanseong capital. || "
            "Narration context: 무대는 백제의 한성과 중국 남조 동진을 잇는 서해 교통로입니다"
        )

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("Landscape-only elevated West Sea route panorama", compiled.positive)
        self.assertIn("Exactly two small fourth-century open wooden boats", compiled.positive)
        self.assertNotIn("earthen walls of the Hanseong capital", compiled.positive)

    def test_baekje_384_court_religion_scenes_use_blank_close_interior_contracts(self):
        cases = (
            (
                "귀족에게는 동진과 연결된 새로운 지식과 의례의 통로가 됐습니다",
                "Exactly three bareheaded adult men exist",
                "three-person Baekje court discussion",
            ),
            (
                "침류왕은 낯선 종교를 왕실의 문 안으로 들여놓았습니다",
                "Exactly two bareheaded adult men exist",
                "two-person royal acceptance",
            ),
            (
                "왕실 가까이에 절이 세워진다는 사실 자체가 새로운 권력 지도를 만들었고",
                "Exactly two bareheaded adult men",
                "two-person Baekje power-alignment tableau",
            ),
        )
        for index, (narration, count_lock, action_lock) in enumerate(cases, start=47):
            compiled = self.compile(
                "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
                "Year/period: 384 AD; Exact place: Hanseong and the western sea route; "
                f"Scene evidence: Source workbook row 06-{index:03d} anchors this scene to 384 AD; "
                "Scene: Eye-level medium shot at a guarded Baekje audience hall. A royal seal, guarded "
                "doorway, and shifting court posture make the change of power immediately legible. || "
                f"Narration context: {narration}"
            )

            self.assertIn(action_lock, compiled.positive)
            self.assertIn(count_lock, compiled.positive)
            self.assertIn("uninterrupted blank rough reed-mat and rammed-earth interior wall", compiled.positive)
            self.assertNotIn("royal seal", compiled.positive)
            self.assertNotIn("guarded doorway", compiled.positive)
            styled = _apply_longtube_dark_manhwa_style(
                compiled.positive,
                model_id="comfyui-z-image-turbo",
            )
            self.assertTrue(styled.startswith("EXACT BAEKJE BLANK-INTERIOR CROP:"))
            self.assertNotIn("EARLY FOURTH-CENTURY MATERIAL LOCK:", styled)

    def test_baekje_ep06_record_scenes_rotate_distinct_textless_material_layouts(self):
        narrations = (
            "삼국유사는 그의 이름을 동학이라는 뜻으로 풀이하기도 했습니다",
            "어린 시절부터 배우는 사람이라는 해석이지만 이름의 정확한 언어적 배경은 복잡하고",
            "이 부분은 역사적 능력을 확인한 기록이 아니라 종교적 찬양에 가깝죠",
            "확실한 핵심은 그가 동진에서 백제로 왔다는 사료의 짧은 문장입니다",
        )
        positives = []
        for row, narration in zip((30, 31, 35, 36), narrations):
            compiled = self.compile(
                "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
                "Year/period: 384 AD; Exact place: Hanseong; "
                f"Scene evidence: Source workbook row 06-{row:03d} anchors this scene to 384 AD; "
                "Scene: Documentary long-lens view at a quiet archive table beside a weathered chronicle. "
                f"|| Narration context: {narration}",
                model="comfyui-flux2-klein-9b",
            )
            self.assertEqual(compiled.scene_kind, "object")
            self.assertRegex(compiled.positive, r"blank (?:narrow )?wooden(?:-| )slips?")
            positives.append(compiled.positive)

        self.assertEqual(len(set(positives)), 4)
        self.assertTrue(any("asymmetrical fan" in positive for positive in positives))
        self.assertTrue(any("single blank narrow wooden slip isolated" in positive for positive in positives))

    def test_baekje_ep06_important_people_and_arrival_have_exact_identity_contracts(self):
        cases = (
            (
                11,
                "그의 이름은 마라난타, 동진에서 온 서역 승려로 기록돼 있죠",
                "single",
                1,
                "Tight head-and-shoulders emotional portrait",
            ),
            (
                13,
                "열 명이 승려가 되자 왕실의 선택은 개인 신앙을 넘어 국가의 선언이 됐고",
                "group",
                None,
                "SYMMETRICAL TEN-MONK GROUP PORTRAIT",
            ),
            (
                23,
                "그 변화의 문을 연 서역 승려가 바로 마라난타였고",
                "single",
                1,
                "Tight three-quarter emotional close-up",
            ),
            (
                38,
                "그 빈자리보다 중요한 건 마라난타가 동진의 불교를 직접 들고 백제에 도착했다는 사실입니다",
                "group",
                3,
                "Low river-landing arrival with exactly three adults",
            ),
            (
                39,
                "그의 도착으로 백제 왕실은 이전과 전혀 다른 종교와 국제 질서를 마주합니다",
                "pair",
                2,
                "King Chimnyu fills the foreground",
            ),
        )
        for row, narration, expected_kind, expected_count, action_lock in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
                    "Year/period: 384 AD; Exact place: Hanseong and the western sea route; "
                    f"Scene evidence: Source workbook row 06-{row:03d} anchors this scene to 384 AD; "
                    "Scene: generic court or archive fallback. "
                    f"|| Narration context: {narration}",
                    model="comfyui-flux2-klein-9b",
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(action_lock, compiled.positive)
                if "열 명이 승려" not in narration:
                    self.assertIn("Marananta", compiled.positive)

    def test_present_day_baekje_research_does_not_receive_ancient_clothing(self):
        compiled = self.compile(
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje; "
            "Year/period: present-day; Exact place: Seoul archaeology laboratory; "
            "Main subject: modern archaeologist; Scene: present-day modern archaeologist "
            "examines fourth-century Baekje soil samples"
        )

        self.assertNotIn("4th-century Hanseong Baekje", compiled.positive)

    def test_baekje_ep4_court_enclosure_frontloads_bare_early_architecture(self):
        compiled = self.compile(
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje and "
            "Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
            "Scene: Ground-level action frame at a guarded Baekje audience hall, "
            "visualizing a change of royal power through court posture"
        )

        self.assertIn("low thatched timber-post Hanseong Baekje court enclosure", compiled.positive)
        self.assertIn("continuous bare wood-grain lintels", compiled.positive)
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )
        self.assertTrue(styled.startswith("EARLY FOURTH-CENTURY MATERIAL LOCK:"))

    def test_baekje_ep4_damro_debate_uses_distributed_period_landscape(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
                    "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
                    "Scene: Closing wide composition across a quiet archive table beside "
                    "a weathered chronicle, visualizing controversy over the later Damro system"
                ),
                narration_context=(
                    "다만 후대의 완성된 담로제를 이 시기에 그대로 놓는 데는 논쟁이 있으며"
                ),
            ),
            "comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("three small fourth-century Baekje regional settlements", compiled.positive)
        self.assertIn("Extreme high aerial landscape", compiled.positive)
        self.assertIn("short local earthwork", compiled.positive)
        self.assertIn("dispersed southern Baekje river valleys", compiled.positive)
        for term in ("modern jacket", "map", "border line", "readable text"):
            self.assertIn(term, compiled.negative)

    def test_baekje_ep4_queen_alliance_keeps_queen_and_nobles_visible(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
                    "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
                    "Scene: Close material-detail composition in a guarded Baekje audience hall"
                ),
                narration_context=(
                    "진씨 가문의 여성을 왕비로 맞아 유력 귀족과 정치적 기반을 묶었고"
                ),
            ),
            "comfyui-z-image-turbo",
        )

        self.assertIn("exactly five adults total", compiled.positive)
        self.assertIn("visibly adult Queen from the Jin family", compiled.positive)
        self.assertIn("exactly three senior nobles bow", compiled.positive)
        self.assertIn("straight narrow ankle-length plain hemp cross-collar robe", compiled.positive)
        for term in (
            "missing Queen",
            "male Queen",
            "all-male group",
            "Joseon chima",
            "wide flared skirt",
            "ornate hairpin",
        ):
            self.assertIn(term, compiled.negative)

    def test_baekje_ep4_father_son_succession_keeps_both_adult_men_visible(self):
        compiled = self.compile(
            prepare_scene_contract_source(
                (
                    "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
                    "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
                    "Scene: Ground-level action frame at a guarded Baekje audience hall"
                ),
                narration_context=(
                    "그 뒤 왕위가 아들 근구수왕에게 이어지는 부자 계승의 틀도 세웁니다"
                ),
            ),
            "comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertIn("older King Geunchogo", compiled.positive)
        self.assertIn("adult son Geungusu", compiled.positive)
        self.assertIn("visibly younger adult son Geungusu", compiled.positive)
        for term in ("missing Geungusu", "same-age duplicate men", "single man"):
            self.assertIn(term, compiled.negative)

    def test_baekje_ep4_mid_episode_evidence_scenes_do_not_collapse_into_combat(self):
        cases = (
            (
                "근초고왕은 군사 압박과 연합을 함께 사용하며 남부 영향력을 넓힙니다",
                "group",
                (
                    "King Geunchogo and the local chief grasp forearms",
                    "plain spears held vertically",
                    "round wooden shields lowered",
                ),
                "rifle",
            ),
            (
                "해안과 내륙을 잇는 교역로의 주도권도 쉽게 내주지 않았죠",
                "group",
                ("transfer sealed grain jars", "one waiting ox cart"),
                "weapon clash",
            ),
            (
                "가야 여러 나라와 왜로 이어지는 교역망에도 가까이 다가갈 수 있었습니다",
                "group",
                ("Busy coastal exchange", "rough iron bloom"),
                "charging warriors",
            ),
            (
                "그 서술에는 편찬자의 정치적 왜곡과 과장이 섞였다고 봅니다",
                "pair",
                (
                    "fourth-century Baekje record keepers",
                    "removes a single blank wooden-slip bundle",
                    "every slip face points away from the camera",
                    "small Hanseong Baekje record room",
                ),
                "modern jacket",
            ),
            (
                "전라도 전역을 한 해에 완전히 직접 지배했다고 단정할 수는 없습니다",
                "landscape",
                (
                    "southwestern peninsula settlements",
                    "Extreme high aerial landscape",
                    "no continuous border",
                ),
                "route graphic",
            ),
            (
                "해안 거점과 교역 관계는 북쪽 전쟁을 버틸 경제적 힘이 됩니다",
                "group",
                ("Wide working harbor scene", "open thatched storehouses"),
                "opposing formations",
            ),
            (
                "남부에서 들어오는 곡물과 물자는 한강 유역의 왕실 창고로 모였습니다",
                "group",
                ("four porters", "low thatched timber granary"),
                "marching army",
            ),
            (
                "더 넓은 인구 기반은 군사를 늘리고 성곽을 지킬 사람을 확보하게 했으며",
                "group",
                ("recruits practice shield spacing", "workers pack earth"),
                "enemy army",
            ),
            (
                "근초고왕의 팽창은 지도를 색칠하는 일보다 물자의 흐름을 바꾸는 일이었습니다",
                "landscape",
                ("High-angle material-flow panorama", "one ox cart"),
                "route graphic",
            ),
            (
                "어느 항구가 백제 상인을 받아들이고 어느 세력이 군사를 보태는지가 중요했고",
                "group",
                ("foreground merchants exchange", "allied troop contingent"),
                "weapon clash",
            ),
            (
                "고구려 고국원왕은 사세기 중반 왕국의 위기를 견딘 제십육대 왕이었고",
                "single",
                ("one mature King Gogukwon", "Tight three-quarter command portrait"),
                "envoys",
            ),
            (
                "한강과 황해도 사이에서 백제와의 충돌은 피하기 어려워졌습니다",
                "group",
                ("two patrols halt on opposite riverbanks", "broad strip of water"),
                "active battle",
            ),
            (
                "치양성은 황해도 배천 일대로 비정되는 북방의 전략 거점이었고",
                "landscape",
                ("zero markings, symbols, writing", "bare-earth frontier rampart"),
                "foreground warrior",
            ),
            (
                "이곳이 무너지면 고구려군이 한강 방면으로 내려올 길이 더 넓어졌죠",
                "landscape",
                ("a narrow northern pass opens", "one tiny patrol descending"),
                "route graphic",
            ),
            (
                "기록은 이 전투의 세부 움직임보다 백제의 승리라는 결과를 선명하게 남겼고",
                "landscape",
                ("Wide dawn aftermath", "northbound footprints"),
                "book",
            ),
            (
                "결과는 백제의 승리였고 고구려군은 북쪽으로 물러났습니다",
                "group",
                ("Goguryeo soldiers climb a northern ridge", "Baekje shield line holds"),
                "face-to-face melee",
            ),
            (
                "남부의 자원과 중앙의 지휘 체계가 더 큰 공세를 위해 결집되며",
                "group",
                ("High-angle mobilization yard", "load tied grain sacks"),
                "battle",
            ),
            (
                "마침내 백제군의 목표는 국경 성 하나가 아니라 평양성으로 바뀝니다",
                "pair",
                (
                    "King Geunchogo and his adult crown prince",
                    "complete large Pyongyang earthwork fortress",
                ),
                "map",
            ),
            (
                "기록은 정예 기병을 포함한 병력 삼만 명이 움직였다고 전하며,",
                "group",
                ("High oblique moving-column view", "six foreground Baekje riders"),
                "book",
            ),
            (
                "한강에서 평양성까지 이어지는 길은 보급만으로도 거대한 부담이었고",
                "group",
                ("Extreme long diagonal tracking view", "supply column climbs"),
                "battle",
            ),
            (
                "남부에서 확보한 곡물과 인력이 없었다면 오래 유지하기 어려웠겠죠",
                "group",
                ("Water-level medium action", "uninterrupted open river water"),
                "empty huts",
            ),
            (
                "평양성은 고구려 남부 방어의 핵심 거점이자 왕의 권위를 상징하는 장소였고",
                "landscape",
                ("Aerial archaeological reconstruction", "sharpened wooden palisade stakes"),
                "foreground battle",
            ),
            (
                "성을 위협한다는 것은 국경을 넘어 왕실 자체에 도전하는 일이었습니다",
                "object",
                ("single visibly hollow helmet", "one dark lamellar royal helmet"),
                "person",
            ),
            (
                "이미 북방 침략으로 큰 상처를 입은 왕에게 또 다른 후퇴는 치명적이었고",
                "single",
                ("Tight chest-up command portrait", "exhausted scarred face"),
                "crowd",
            ),
            (
                "두 왕이 같은 전선에 선 순간 전쟁의 무게는 이전과 달라졌습니다",
                "pair",
                ("King Geunchogo drives", "King Gogukwon braces"),
                "two standing men alone",
            ),
            (
                "한쪽은 전성기를 열려는 정복왕, 다른 쪽은 왕국을 지켜야 할 수성왕이었고,",
                "pair",
                ("Extreme close-up opposing-profile two-shot", "every arm, hand, weapon"),
                "third person",
            ),
            (
                "전투가 격해지던 순간 고국원왕이 백제군의 화살에 맞았고,",
                "single",
                ("Tight chest-up impact moment", "exactly one plain wooden arrow"),
                "extra arrow",
            ),
        )
        source = (
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
            "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
            "Scene: Focused gestures, one decisive object, and surrounding reactions "
            "inside a historically grounded Baekje settlement"
        )

        for narration, scene_kind, positive_terms, negative_term in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prepare_scene_contract_source(
                        source,
                        narration_context=narration,
                    ),
                    "comfyui-z-image-turbo",
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                self.assertIn(negative_term, compiled.negative)
                if narration == "그 서술에는 편찬자의 정치적 왜곡과 과장이 섞였다고 봅니다":
                    self.assertNotIn("sealed parchment sheets", compiled.positive)

    def test_baekje_ep4_aftermath_diplomacy_and_record_scenes_keep_distinct_actions(self):
        cases = (
            (
                "누가 그 화살을 쐈는지는 기록에 남지 않아 영웅 한 명을 만들 수 없지만,",
                "object",
                ("Ground-level evidence still-life", "six identical unmarked arrows"),
                "book",
            ),
            (
                "왕의 전사 자체는 고구려 역사에 깊은 충격을 남긴 사건이었습니다.",
                "group",
                ("Wide quiet mourning scene", "exactly three separated Goguryeo soldiers"),
                "active battle",
            ),
            (
                "고구려군은 왕을 잃고 지휘와 사기가 흔들릴 수밖에 없었고,",
                "group",
                ("High-angle command-collapse action", "four small soldier groups"),
                "organized battle line",
            ),
            (
                "백제의 북쪽 세력권은 역사상 가장 멀리 뻗은 시기를 맞았습니다.",
                "landscape",
                ("Extreme high aerial landscape", "one tiny Baekje patrol"),
                "map",
            ),
            (
                "하지만 평양성을 점령해 오랫동안 직접 통치했다고 단정할 수는 없고,",
                "landscape",
                ("Wide dawn landscape", "intact low earthwork enclosure"),
                "occupation ceremony",
            ),
            (
                "공세의 성공과 지속적인 행정 지배는 구분해서 봐야 합니다.",
                "group",
                ("Medium working scene", "porters roll sleeping mats"),
                "official court",
            ),
            (
                "승리보다 더 오래 남은 것은 두 나라 사이의 복수심이었죠.",
                "pair",
                ("Extreme opposing-face close-up", "one scarred Baekje survivor"),
                "handshake",
            ),
            (
                "왕을 잃은 고구려는 백제를 단순한 국경 경쟁자가 아니라 원수로 기억했고,",
                "single",
                ("Tight kneeling mourning portrait", "single empty helmet"),
                "battle",
            ),
            (
                "훗날 광개토왕과 장수왕의 남진에는 이 원한의 역사도 겹쳐집니다.",
                "landscape",
                ("Long-lens landscape action", "distant cavalry column descends"),
                "map",
            ),
            (
                "백오 년 뒤 한성이 무너지는 비극의 씨앗도 함께 남겼습니다.",
                "landscape",
                ("Wide ominous landscape", "intact low earthen rampart"),
                "active battle",
            ),
            (
                "근초고왕은 군사 승리를 외교적 지위로 바꾸는 일도 놓치지 않았습니다.",
                "pair",
                ("Medium departure action", "closed cord-tied envoy case"),
                "weapon clash",
            ),
            (
                "왕은 동진으로부터 장군과 낙랑태수 계통의 작호를 받게 됩니다.",
                "pair",
                ("Formal medium two-shot", "plain bronze seal"),
                "standing lineup",
            ),
            (
                "이 작호는 백제가 중국의 지방정부가 됐다는 뜻으로만 볼 수 없으며,",
                "object",
                ("Tight object comparison", "solid square bronze seal blocks"),
                "Chinese characters",
            ),
            (
                "서해를 건넌 사신은 전쟁의 승리를 다른 왕조가 아는 정치 자산으로 만들었고,",
                "landscape",
                ("Low waterline action", "one wooden envoy ship"),
                "battle",
            ),
            (
                "백제는 남쪽으로 가야와 왜, 서쪽으로 동진을 잇는 위치를 활용합니다.",
                "group",
                ("High wide harbor action", "rough iron blooms"),
                "route graphic",
            ),
            (
                "물자와 기술, 외교 문서가 같은 항로를 따라 움직였고,",
                "object",
                ("Tight cargo still-life", "closed dispatch case"),
                "open document",
            ),
            (
                "군사력만으로는 얻을 수 없는 정보와 관계가 왕국에 쌓였습니다.",
                "pair",
                ("Tight seated briefing two-shot", "empty low table"),
                "battle",
            ),
            (
                "일부 기록에는 요서 지역 진출과 백제군 설치가 전하지만,",
                "landscape",
                ("Vertical aerial view", "uninterrupted open seawater"),
                "large occupied city",
            ),
            (
                "그 범위와 실체에는 논쟁이 커서 확정된 영토처럼 그릴 수 없습니다.",
                "landscape",
                ("Extreme wide environment-only establishing view", "uninhabited natural landscape"),
                "modern jacket",
            ),
            (
                "분명한 것은 백제의 활동 반경이 한강과 서남부에만 머물지 않았다는 점이며,",
                "landscape",
                ("Extreme high aerial landscape", "three tiny transports"),
                "route graphic",
            ),
            (
                "근초고왕은 전쟁과 외교, 교역을 하나의 전략으로 묶었습니다.",
                "group",
                ("High-angle strategy yard", "King Geunchogo directs"),
                "active battle",
            ),
            (
                "그 연결망을 안정시키려면 왕실의 역사를 정리할 필요도 생겼고,",
                "pair",
                ("Low rear three-quarter working view", "thin edges"),
                "visible writing",
            ),
            (
                "정복왕은 이제 칼이 아니라 기록으로 자신의 시대를 남기려 합니다.",
                "group",
                ("Lamplit closing court scene", "fully sheathed sword"),
                "drawn sword",
            ),
        )
        source = (
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
            "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
            "Scene: Focused gestures inside a historically grounded Baekje settlement"
        )

        for narration, scene_kind, positive_terms, negative_term in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prepare_scene_contract_source(source, narration_context=narration),
                    "comfyui-z-image-turbo",
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                self.assertIn(negative_term, compiled.negative)

    def test_intentional_material_detail_scene_remains_object(self):
        compiled = self.compile(
            "Year/period: 346-375 AD; Exact place: Baekje workshop; "
            "Main subject: one iron fitting; Scene: close material-detail composition of "
            "one iron fitting with focused gestures conveyed only through tool marks; "
            "object-only evidence view, image only"
        )

        self.assertEqual(compiled.scene_kind, "object")

    def test_baekje_ep4_final_synthesis_and_teaser_use_distinct_visual_actions(self):
        cases = (
            ("근초고왕은 박사 고흥에게 백제의 역사서 서기를 편찬하게 했다고 전합니다", "pair", "Tight commissioning action"),
            ("고흥은 왕실의 계보와 국가의 일을 기록한 학자로 알려져 있지만", "single", "Over-the-shoulder binding close-up"),
            ("그가 만든 서기는 오늘날 한 줄도 온전히 남아 있지 않습니다", "object", "Extreme archaeological evidence close-up"),
            ("따라서 책의 문장이나 목차를 상상해 사실처럼 말할 수는 없죠", "pair", "empty museum plinth"),
            ("다만 왜 전성기의 왕이 역사책을 필요로 했는지는 짐작할 수 있습니다", "single", "Tight thoughtful royal close-up"),
            ("새로 편입된 여러 세력에게 하나의 왕실 계보를 보여 줘야 했고", "group", "Low circular oath action"),
            ("전쟁의 승리와 외교 성과를 왕권의 정통성으로 묶을 필요가 있었습니다", "pair", "Dynamic low-angle reception"),
            ("기록은 후계자인 태자에게도 누가 어떤 나라를 물려주는지 설명하는 도구였고", "pair", "Medium succession handoff"),
            ("왕국의 기억을 귀족 개인의 전승에서 국가의 역사로 바꾸는 작업이었죠", "group", "Layered transfer action"),
            ("근초고왕은 땅만 넓힌 왕이 아니라 백제가 자신을 기억하는 방식도 바꿨습니다", "group", "Wide moving archive scene"),
            ("그러나 그의 최대 영토를 오늘날 국경선처럼 선명하게 그리면 또 다른 과장이 생깁니다", "landscape", "Extreme high aerial terrain view"),
            ("직접 행정이 닿은 땅과 군사적 영향권, 교역 관계를 구분해야 하고", "landscape", "High oblique geographic panorama"),
            ("남부와 요서에 대한 설명도 서로 다른 강도의 지배로 봐야 합니다", "landscape", "Wide sea-distance landscape"),
            ("그 구분을 지켜도 근초고왕대의 팽창이 압도적이었다는 사실은 달라지지 않으며", "landscape", "Sweeping dawn panorama"),
            ("백제는 군사와 외교, 기록이 함께 움직이는 전성기에 들어섰습니다", "group", "Busy diagonal state-yard action"),
            ("근초고왕의 시대는 한 왕의 승리보다 국가 운영 방식의 폭발이었습니다", "group", "High-angle capital operations scene"),
            ("안정된 계승은 군사를 한 방향으로 모았고 남부 영향력은 자원을 늘렸으며", "group", "Forward-moving yard action"),
            ("치양성의 승리는 평양성 공세로 이어져 고국원왕의 전사로 끝났습니다", "object", "Ground-level aftermath still-life"),
            ("동진 외교와 해상 교역은 전장의 성과를 동아시아의 지위로 바꿨고", "group", "Low waterline arrival action"),
            ("고흥의 서기는 그 모든 일을 왕실의 기억으로 묶으려 했죠", "single", "Extreme hand-action archive close-up"),
            ("다만 지도 위의 최대 영토는 직접 지배와 영향권을 나눠 봐야 합니다", "landscape", "Very high oblique landscape"),
            ("그 선을 지켜도 근초고왕은 백제 역사상 가장 공격적인 군주로 남습니다", "group", "Low tracking command action"),
            ("고국원왕의 죽음은 승리의 절정이자 고구려의 복수가 시작된 순간이었고", "single", "Tight kneeling emotional close-up"),
            ("백제의 황금기는 미래의 가장 위험한 적까지 함께 키웠습니다", "landscape", "Deep ominous landscape"),
            ("이제 전성기의 힘은 칼과 군대만이 아니라 물건과 문자로 바다를 건너갑니다", "object", "Object-only moving-deck cargo still-life"),
            ("다음 편에서는 일곱 갈래로 뻗은 칠지도의 금빛 글자를 따라갑니다", "object", "Extreme sealed-case macro teaser"),
            ("이 검은 실전 무기가 아니라 백제와 왜의 관계를 담은 외교 상징물이었고", "pair", "Formal kneeling exchange"),
            ("명문 한 글자를 어떻게 읽느냐에 따라 하사와 헌상의 방향까지 뒤집힙니다", "pair", "Tense opposing-direction close-up"),
            ("왕인과 아직기, 고흥의 전승도 함께 살펴보며 고대 한류의 실체를 보시죠", "group", "Busy harbor departure"),
            ("칠지도의 비밀이 궁금하시다면 구독과 좋아요로 함께해 주세요", "landscape", "Closing wide dawn sea action"),
        )
        source = (
            "Global visual world: Time range: 346-375 AD; Culture scope: Baekje "
            "and Goguryeo; Year/period: 346-375 AD; Exact place: Han River basin; "
            "Scene: Focused gestures, one decisive object, and surrounding reactions "
            "inside a historically grounded Baekje settlement"
        )

        for narration, scene_kind, action_term in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prepare_scene_contract_source(source, narration_context=narration),
                    "comfyui-z-image-turbo",
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertIn(action_term, compiled.positive)
                self.assertNotIn("Opposing formations lock into one clash", compiled.positive)
                self.assertNotIn("quiet archive table beside a weathered chronicle", compiled.positive)

    def test_z_image_seven_branch_sword_style_fixes_all_six_side_slots(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Visible action: Seven-branch-sword-only artifact macro: one central blade with "
            "six fixed side branches. Primary subject: one dark iron artifact. "
            "Style: elongated angular adult anatomy; weathered expressive adult faces.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("SEVEN-BRANCHED SWORD GEOMETRY LOCK", styled)
        self.assertIn("never a photograph", styled)
        self.assertIn("lower-left, middle-left, upper-left, lower-right, middle-right", styled)
        self.assertIn("exactly seven pointed tips total", styled)
        self.assertNotIn("elongated angular adult anatomy", styled)
        self.assertNotIn("weathered expressive adult faces", styled)

    def test_actual_europa_alignment_scenes_receive_identity_and_mount_continuity(self):
        trailer = (
            ", vivid Bronze Age Mediterranean myth reconstruction grounded in Phoenician, "
            "Cretan, and early Greek material culture, 2000 BCE to 1200 BCE, Eastern "
            "Mediterranean, Crete, Ancient Greek communities, Phoenician city-states, "
            "period-accurate clothing, architecture, tools, and material culture"
        )
        cases = (
            (
                "Family names spreading across maps of Cilicia, Phoenicia, Thasos, and Thebes",
                ("exactly three Phoenician merchant ships", "continuous natural seawater"),
                ("map", "readable text"),
                "landscape",
            ),
            (
                "Europa approaching the calm White bull while armed palace guards remain relaxed",
                ("exactly one ordinary white bull", "only bovine animal"),
                ("duplicate bull", "two bulls"),
                "group",
            ),
            (
                "White bull suddenly sprinting across the beach with Europa gripping its neck",
                ("exactly one visibly adult woman Europa", "remains clearly mounted"),
                ("male rider", "riderless bull"),
                "single",
            ),
            (
                "Phoenician attendants stumbling through sand as the bull reaches breaking waves",
                ("Europa age 25 or older seated side-saddle", "attendants stumble"),
                ("male rider", "missing Europa"),
                "group",
            ),
            (
                "Europa holding a horn above dark water as the Phoenician coast recedes",
                ("left palm touches the thick white curved horn", "same attached horn"),
                ("detached horn", "rein"),
                "single",
            ),
            (
                "White bull powering through surf while Europa twists toward the shore",
                ("Water-level close crop", "only Europa's upper body"),
                ("bull on land", "shallow water"),
                "single",
            ),
            (
                "Empty sea around the swimming bull while distant ships face other directions",
                ("Europa clings to the swimming white bull", "two tiny empty Phoenician ships"),
                ("shore observer", "missing Europa"),
                "single",
            ),
            (
                "Europa carried helplessly along a glowing route from Phoenicia toward Crete",
                ("Moonlit waterline view in open sea", "only their upper bodies"),
                ("glowing route", "bull on land"),
                "single",
            ),
            (
                "Dolphins and sea gods surrounding Europa and the bull in a deceptively celebratory scene",
                ("Water-level open-sea view", "heads and shoulders rise"),
                ("shore crowd", "bull on land"),
                "group",
            ),
        )

        for scene, positive_terms, negative_terms, scene_kind in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean, "
                    f"Crete; Main subject: {scene}; Scene: {scene}{trailer}; "
                    "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through "
                    "visible action, emotional expression, body posture, prop contact, "
                    "setting pressure, or object evidence"
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                for term in negative_terms:
                    self.assertIn(term, compiled.negative)
                if scene_kind == "single":
                    self.assertNotIn("one rider and one horse", compiled.positive)
                    if any(
                        token in scene.lower()
                        for token in (
                            "dark water",
                            "through surf",
                            "empty sea",
                            "glowing route",
                        )
                    ):
                        self.assertIn(
                            "composition=submerged_mounted_bull",
                            compiled.diagnostics,
                        )
                        self.assertIn("zero leg or hoof pixels", compiled.positive)
                    else:
                        self.assertIn(
                            "composition=single_mounted_bull",
                            compiled.diagnostics,
                        )

    def test_europa_crete_and_search_scenes_keep_identity_counts_and_text_bans(self):
        cases = (
            (
                "Decorative sea procession contrasted with Europa's clenched hands and frightened face",
                "single",
                ("exactly one visibly adult woman Europa", "featureless open water filling"),
                "procession",
            ),
            (
                "White bull emerging from the sea onto a Cretan beach with exhausted Europa",
                "single",
                ("Europa age 25 or older still mounted", "hind legs remain in the surf"),
                "riderless bull",
            ),
            (
                "White bull transforming into Zeus before Europa on the empty Cretan shore",
                "pair",
                ("exactly one adult male Zeus", "Europa in her fully covering"),
                "missing Zeus",
            ),
            (
                "Europa alone between distant Phoenicia and an unknown Cretan palace",
                "single",
                ("exactly one visibly adult woman Europa", "Wide solitary shore view"),
                "second person",
            ),
            (
                "Zeus presenting Europa with a necklace",
                "pair",
                ("exactly one adult male Zeus", "extends one plain gold necklace toward Europa"),
                "man receiving necklace",
            ),
            (
                "Harmonia-like gold necklace gleaming ominously in Europa's hands",
                "single",
                ("exactly one visibly adult woman Europa", "uneasy adult face remains dominant"),
                "male Europa",
            ),
            (
                "Europa among miraculous gifts while staring across the sea toward Phoenicia",
                "single",
                ("Over-shoulder medium view from behind Europa", "one seated hound"),
                "route graphic",
            ),
            (
                "Europa holding three young sons before a Cretan palace",
                "group",
                ("exactly four people total", "exactly three distinct young boys"),
                "two boys",
            ),
            (
                "Asterion welcoming Europa and the three boys into his royal family",
                "group",
                ("exactly five people total", "exactly three distinct young boys"),
                "missing Europa",
            ),
            (
                "Telephassa stepping onto Cadmus's ship with travel chests and a determined expression",
                "pair",
                ("exactly two people total", "Tight low gangplank two-shot"),
                "lone man",
            ),
            (
                "Agenor's closed palace gate behind departing search ships",
                "landscape",
                ("completely blank lintel", "three small wooden search ships"),
                "inscription",
            ),
            (
                "Cilix raising a settlement beside the Pyramus River under a new regional banner",
                "group",
                ("Medium active construction scene", "plain timber corner post"),
                "CILIX",
            ),
            (
                "Phoenix standing over a map where his name and Phoenicia overlap uncertainly",
                "group",
                ("exactly three human men total", "Tight head-and-shoulders three-human debate"),
                "PHOENICIA",
            ),
        )
        trailer = (
            ", vivid Bronze Age Mediterranean myth reconstruction grounded in Phoenician, "
            "Cretan, and early Greek material culture, 2000 BCE to 1200 BCE, Eastern "
            "Mediterranean, Crete, period-accurate clothing and architecture"
        )

        for scene, scene_kind, positive_terms, negative_term in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean, "
                    f"Crete; Main subject: {scene}; Scene: {scene}{trailer}; "
                    "NARRATION VISUAL ALIGNMENT: match the spoken moment"
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                self.assertIn(negative_term, compiled.negative)
                if scene.startswith(("Decorative sea procession", "Cilix raising", "Phoenix standing")):
                    self.assertNotIn("Visible evidence: Source workbook scene", compiled.positive)
                if scene.startswith("Phoenix standing"):
                    self.assertIn(
                        "composition=three_human_head_shoulders_debate",
                        compiled.diagnostics,
                    )

    def test_europa_brothers_scene_does_not_force_europa_or_bull(self):
        compiled = self.compile(
            "Year/period: 2000 BCE to 1200 BCE; Exact place: Tyre; "
            "Main subject: Agenor commanding Europa's brothers and Telephassa before ships "
            "depart from Tyre; Scene: Agenor commanding Europa's brothers and Telephassa "
            "before ships depart from Tyre, vivid Bronze Age Mediterranean myth "
            "reconstruction grounded in Phoenician, Cretan, and early Greek material "
            "culture, 2000 BCE to 1200 BCE, Eastern Mediterranean, Crete, Ancient Greek "
            "communities, Phoenician city-states, period-accurate clothing; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment"
        )

        self.assertNotIn("visibly adult woman Europa age 25 or older", compiled.positive)
        self.assertNotIn("ordinary white bull", compiled.positive)

    def test_europa_name_and_archaeology_scenes_remove_generated_text_triggers(self):
        cases = (
            (
                "Europa's written name expanding from a Phoenician princess across Greek maps",
                "single",
                ("Europa walks along a bare Phoenician shore", "every surface is plain and unmarked"),
                ("EUROPA", "readable text"),
            ),
            (
                "Anaximander and Hecataeus drawing tripartite world maps with Europe",
                "pair",
                ("press three continuous coastline grooves", "one damp circular clay slab"),
                ("Europe", "readable text"),
            ),
            (
                "Herodotus comparing different river boundaries between Europe and Asia",
                "single",
                ("two distinct rivers diverge", "he carries nothing"),
                ("map", "readable text"),
            ),
            (
                "European eastern boundary shifting across successive ancient and modern maps",
                "landscape",
                ("three distinct waterways advance eastward", "forested Caucasus foothills"),
                ("map", "readable text"),
            ),
            (
                "Europa's portrait beside a cautious question over the expanding continental name",
                "single",
                ("fork between two natural coastal footpaths", "turns uncertainly"),
                ("question mark", "male Europa"),
            ),
            (
                "Europa looking back from the bull as her route becomes the word Europe",
                "single",
                ("Low waterline action view", "remains clearly mounted"),
                ("Europe", "route graphic"),
            ),
            (
                "Excavators comparing Knossos ruins",
                "pair",
                ("exactly two modern adult archaeologists", "tablet seen strictly edge-on"),
                ("tablet face toward camera", "readable text"),
            ),
        )
        trailer = (
            ", vivid Bronze Age Mediterranean myth reconstruction grounded in Phoenician, "
            "Cretan, and early Greek material culture, 2000 BCE to 1200 BCE, Eastern "
            "Mediterranean, Crete, period-accurate clothing and architecture"
        )

        for scene, scene_kind, positive_terms, negative_terms in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean, "
                    f"Crete; Main subject: {scene}; Scene: {scene}{trailer}; "
                    f"Visible evidence: Source workbook scene: {scene}; "
                    "NARRATION VISUAL ALIGNMENT: match the spoken moment"
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                for term in negative_terms:
                    self.assertIn(term, compiled.negative)
                self.assertNotIn("Visible evidence: Source workbook scene", compiled.positive)

        archaeology = self.compile(
            "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean, "
            "Crete; Main subject: Excavators comparing Knossos ruins; "
            f"Scene: Excavators comparing Knossos ruins{trailer}; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment"
        )
        self.assertIn("Era/period: modern archaeological", archaeology.positive)
        self.assertIn("Exact place: Knossos excavation trench in Crete", archaeology.positive)

        archaic_geography = self.compile(
            "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean, "
            "Crete; Main subject: Anaximander and Hecataeus drawing tripartite world maps "
            "with Europe; Scene: Anaximander and Hecataeus drawing tripartite world maps "
            f"with Europe{trailer}; NARRATION VISUAL ALIGNMENT: match the spoken moment"
        )
        self.assertIn("Era/period: 6th century BCE", archaic_geography.positive)
        self.assertIn("Exact place: Ionian Greek workshop at Miletus", archaic_geography.positive)

    def test_actual_baekje_ep01_foundation_material_lock_covers_nonmodern_cuts(self):
        payload = self._actual_baekje_ep01_script_fixture()
        required_ancient_material = (
            "timber structures",
            "packed-earth walls",
            "rough thatch roofs",
        )
        required_negative = (
            "missing fingers",
            "fused fingers",
            "missing arms",
            "missing legs",
            "two heads on one body",
            "two bodies sharing one head",
            "modern T-shirt",
            "modern shorts",
            "barefoot",
            "tiled roof",
            "curved roof",
            "glazed roof tiles",
            "ornate palace",
            "later-period palace",
            "Joseon palace",
            "Chinese palace",
            "signboard",
        )
        later_compilation_cuts = {7, 14, 36, 89, 91, 99, 100}
        wilderness_material_cuts = {23, 25}
        compact_material_by_cut = {
            24: (
                "plain unmarked timber interior wall",
                "long-sleeved wrap-front woven robes",
            ),
            26: (
                "open timber-palisade entrance",
                "packed earth",
                "plain long-sleeved wrap-front woven robes",
            ),
            27: (
                "plain timber-and-packed-earth household",
                "plain long-sleeved wrap-front woven robes",
            ),
            28: (
                "plain unmarked timber court room",
                "long-sleeved wrap-front woven robes",
            ),
            29: (
                "roofless raw-log palisade",
                "undyed brown coarse woven wrap-front robe",
                "narrow flat neck band",
                "one unbroken rear cloth panel",
            ),
            30: (
                "open freestanding defensive timber-palisade gateway",
                "crossed wrap-front woven robe collars",
            ),
        }

        for cut_number in range(1, 101):
            with self.subTest(cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertLessEqual(len(compiled.positive), 1200)
                self.assertLessEqual(len(compiled.negative), 760)
                for term in required_negative:
                    self.assertIn(term, compiled.negative)
                if cut_number in later_compilation_cuts:
                    self.assertIn("later", compiled.positive.lower())
                    self.assertIn("closed blank unmarked", compiled.positive)
                    self.assertNotIn("plain woven long-sleeved garments", compiled.positive)
                    continue
                if cut_number in wilderness_material_cuts:
                    for term in (
                        "packed-earth wilderness path",
                        "natural grass, rocks, sparse trees",
                        "open timber-palisade entrance",
                        "plain woven wrap-front upper robe",
                    ):
                        self.assertIn(term, compiled.positive)
                    self.assertNotIn("rough thatch roofs", compiled.positive)
                    continue
                if cut_number in compact_material_by_cut:
                    for term in compact_material_by_cut[cut_number]:
                        self.assertIn(term, compiled.positive)
                    self.assertNotIn("modern T-shirt", compiled.positive)
                    continue
                for term in required_ancient_material:
                    self.assertIn(term, compiled.positive)
                if compiled.scene_kind in {"single", "pair", "group"}:
                    self.assertIn(
                        "plain woven long-sleeved garments",
                        compiled.positive,
                    )

    def test_actual_baekje_ep01_cut10_and_cut11_follow_their_narration_without_literal_maps(self):
        payload = self._actual_baekje_ep01_prepared_fixture()
        cases = {
            10: (
                "multiple separated small Mahan communities around the southern Han River basin",
                "each as a separate timber-and-packed-earth settlement linked by natural footpaths",
            ),
            11: (
                "many separate small local settlements between the river and the sea",
                "no single powerful Baekje capital dominates the view",
            ),
        }

        for cut_number, required in cases.items():
            with self.subTest(cut=cut_number):
                compiled = self.compile(
                    self._structured_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "landscape")
                self.assertIsNone(compiled.person_count)
                for phrase in required:
                    self.assertIn(phrase, compiled.positive)
                self.assertNotIn("map-like aerial landscape", compiled.positive)
                for term in ("literal map", "map diagram", "labels", "written place names"):
                    self.assertIn(term, compiled.negative)

    def test_actual_baekje_ep01_actor_and_action_locks_follow_each_cut(self):
        payload = self._actual_baekje_ep01_script_fixture()
        required_by_cut = {
            1: (
                "Displaced prince Onjo moves south and screen-right",
                "much smaller in the far-left rear",
                "no eye contact and no interaction",
                "simple hide shoes",
            ),
            2: ("Adult man Biryu stands alone", "none of his former followers remain"),
            3: ("Adult man Onjo stands at a plain timber defensive palisade", "distant Mahan"),
            4: ("Onjo's force disguised as hunters", "one last Mahan defender shields family members"),
            5: (
                "Exiled Onjo facing south",
                "walks screen-right across bare earth in low hide shoes",
                "Biryu remains standing on both feet",
                "Mahan settlement stays far-left across a broad empty field gap",
                "no eye contact",
            ),
            6: ("one modest timber-and-packed-earth settlement just beginning",),
            7: (
                "traditional East Asian thread-bound manuscript",
                "visible external binding thread",
                "stacked folded leaves",
            ),
            8: ("several small separated timber-and-earth settlement traces", "no single site"),
            9: ("adult man Jumong stands at the center", "gathers secondary followers"),
            10: ("multiple small Mahan communities", "separate timber-and-packed-earth settlement"),
            11: ("many separate small timber-and-packed-earth settlements", "no single powerful Baekje capital"),
            12: ("Soseono steps beside adult man Jumong", "hands lowered and relaxed"),
            13: ("Soseono stands with her sons Biryu and Onjo", "material resources under her control"),
            14: (
                "warm-brown wood tabletop with broad grain filling all four corners",
                "thread-bound genealogy manuscript",
                "exactly three flat rectangular wooden tags",
                "four square corners and no crossbar",
            ),
            15: (
                "Soseono stands centered",
                "two similarly aged younger adult male sons Biryu and Onjo",
                "no husband or father figure",
            ),
            16: (
                "Exactly one adult woman Soseono",
                "actively directing her organized local settlers",
                "exactly one adult man Jumong enters Jolbon at right",
            ),
            17: ("Soseono and adult man Jumong step together", "secondary unarmed settlers"),
            18: ("Soseono occupies the foreground center", "directs the founding settlers"),
            19: ("Soseono leads her sons Biryu and Onjo", "plain timber threshold"),
            20: (
                "Biryu and Onjo remain together",
                "visibly settled there as home",
                "fabric covers each calf to the ankles",
                "lowered hands remain apart with clear air",
            ),
            21: ("Soseono stands between Biryu and Onjo", "approach road remain empty"),
            22: ("Yuri stands alone in a plain Buyeo household", "future succession claimant"),
            23: (
                "Rear head-and-shoulders over-the-shoulder view",
                "Yuri's rear head, neck, shoulders and upper back fill lower center",
                "open Jolbon timber entrance",
                "small separated royal adults appear only as heads and shoulder tops beyond",
                "exactly zero visible hands",
                "packed-earth wilderness path",
                "plain woven wrap-front upper robe",
            ),
            24: (
                "exactly four named adults: adult woman Soseono with her adult male sons Biryu and Onjo, plus Jumong's adult male heir Yuri",
                "Extreme facial close-up four-person row indoors",
                "exactly four adult heads each fill 65-75 percent of frame height",
                "from left to right, adult male son Biryu",
                "adult woman Soseono as the sole woman",
                "adult male son Onjo",
                "Jumong's moustached adult male heir Yuri",
                "one continuous indoor four-face close-up strip against a plain timber wall",
                "exactly four fixed left-to-right face slots",
                "male Biryu, sole woman Soseono, male Onjo, Jumong's moustached adult male heir",
                "four separate complete faces, necks, collar tops and shoulder tops",
                "lower edge cuts at all four collarbones",
                "zero visible upper arms, elbows, forearms, wrists, hands or fingers",
                "long-sleeved wrap-front woven robes",
            ),
            25: (
                "Direct centered rear head-and-shoulders view",
                "exactly one adult East Asian man named Yuri",
                "the back of Yuri's head, neck, level shoulders and upper back fill lower center",
                "faces the open Jolbon timber entrance along the wilderness path",
                "his face, eyes, nose and cheeks are fully hidden",
                "exactly zero visible hands",
                "lower edge ends below the shoulder blades",
                "packed-earth wilderness path",
                "plain woven wrap-front upper robe",
            ),
            26: (
                "exactly two adult men: father Jumong and adult son Yuri",
                "middle-aged father Jumong at left",
                "younger adult son Yuri at right",
                "exactly zero visible hands",
                "one continuous head-and-shoulders two-shot",
                "lower frame ends at both collarbones",
            ),
            27: (
                "exactly two adult men: young men Biryu and Onjo",
                "Tight chest-up two-shot",
                "young men Biryu at far left and Onjo at far right face each other",
                "across a narrow empty center",
                "over the succession problem",
                "hair crowns, complete faces, necks, crossed robe collars, shoulders and upper chests appear",
                "one tight chest-up two-shot",
                "Biryu fills far-left and Onjo far-right across a narrow empty center",
                "exactly two complete male faces, connected necks, robe collars, shoulders and upper chests",
                "lower image edge crops above both elbows",
                "zero visible forearms, wrists, hands or fingers",
                "faces turn toward each other",
            ),
            28: (
                "Outward-facing chest-up profile two-shot",
                "adult man Jumong at far left is in strict left-facing profile",
                "his nose and pupils pointing screen-left",
                "adult woman Soseono at far right is in strict right-facing profile",
                "exactly two adults: adult man Jumong and adult woman Soseono",
                "one tight outward-facing chest-up profile two-shot",
                "Jumong fills far-left in strict left-facing profile with nose and pupils pointing screen-left",
                "Soseono fills far-right in strict right-facing profile with nose and pupils pointing screen-right",
                "their backs face center, eye lines diverge and never meet",
                "broad empty timber wall remains in the center",
                "exactly two complete heads, connected necks, collars, shoulders and upper chests",
                "lower image edge crops above both elbows",
                "zero visible forearms, wrists, hands or fingers",
            ),
            29: (
                "exactly one adult East Asian man named Yuri",
                "Direct centered rear head-and-shoulders view",
                "extreme direct-rear head-and-shoulders close-up",
                "long black hair gathers upward into one compact tied crown knot",
                "covered nape",
                "roofless vertical raw-log palisade",
                "before one closed bare-wood gate",
                "roofless raw-log palisade with open sky",
                "his face, eyes, nose and cheeks are fully hidden",
                "exactly zero visible hands or fingers",
                "undyed brown coarse woven wrap-front robe",
                "narrow flat neck band",
                "one unbroken rear cloth panel across loose shoulders",
            ),
            30: (
                "exactly four named adults: adult male heir Yuri with adult woman Soseono",
                "Extreme facial close-up four-person reaction row at one open plain timber gate",
                "Soseono, Biryu and Onjo turn their eyes toward Yuri",
                "sole woman Soseono, male Biryu, male Onjo",
                "exactly zero visible upper arms, elbows, forearms, wrists, hands or fingers",
                "crossed wrap-front woven robe collars",
                "one open freestanding defensive timber-palisade gateway",
            ),
            31: ("Before the secondary officials", "Jumong directly recognizes Yuri", "hands relaxed inside their long sleeves"),
            32: ("Jumong guides Yuri into the central position", "secondary officials remain behind them"),
            33: ("Jumong installs Yuri at the central plain wooden place", "as crown prince"),
            34: ("Yuri occupies the central court position", "Biryu and Onjo each step back"),
            35: ("Yuri remains in the central court position", "Soseono stands at the edge with Biryu and Onjo"),
            36: ("two closed blank unmarked manuscript covers", "opposite sides of one plain later archival surface"),
            37: ("Yuri stands in the central court position", "Biryu and Onjo remain clearly separated"),
            38: ("Biryu and Onjo pause together at one natural fork",),
            39: ("Biryu and Onjo choose the southbound path", "secondary unarmed households"),
            40: ("organized column of secondary adult political followers", "plain household goods"),
            41: ("Soseono joins adult sons Biryu and Onjo", "southbound road"),
            42: ("Ogan and Maryeo walk side by side", "secondary households follow"),
            43: ("Ogan and Maryeo occupy the visible middle link", "Biryu and Onjo"),
            44: ("Exactly eight distinct adult officials", "two clear rows of four"),
            45: ("Soseono and her sons Biryu and Onjo leave", "southbound movement"),
            46: ("Royal family members, officials, families, and civilians travel together south",),
            47: ("mixed migration leaves the old political center", "household goods south"),
            48: ("between exactly two separate broad river courses", "Paesu and Daesu"),
            49: ("exactly two distinct broad river corridors", "not assigned to any present-day river"),
            50: ("One distant migrant group moves south", "several plausible natural paths branch"),
            51: ("Biryu and Onjo travel south", "larger migration of families"),
            52: ("Exactly ten retainers total", "Ogan and Maryeo among the ten"),
            53: ("Biryu and Onjo lead the same migration", "choice separates them"),
            54: ("Han River basin historically called Hansan", "families and household goods"),
            55: ("Han River basin historically called Hansan", "tradition places Baekje's first center"),
            56: ("exactly ten retainers climb the wooded summit called Buahak",),
            57: ("exact modern location remains unidentified", "broad river, mountain, field, and western waterway"),
            58: ("one large river to the north", "high mountains to the east"),
            59: ("fertile southern fields", "western waterway toward the sea"),
            60: ("Exactly ten retainers advise Biryu and Onjo", "south of the Han River"),
            61: ("Onjo studies the defensible mountains", "western waterway"),
            62: ("Onjo accepts the ten retainers'", "Biryu turns separately toward the western coast"),
            63: ("western coastal capital candidate at Michuhol",),
            64: ("wet tidal ground and brackish water", "unidentified Michuhol"),
            65: ("Biryu refuses to yield", "exactly ten retainers"),
            66: ("Biryu looks toward the distant western tidal coast", "reason remains visually unresolved"),
            67: ("Biryu leads his followers", "toward Michuhol"),
            68: ("two separating migration groups", "goods divide between them"),
            69: ("Onjo remains south of the Han River", "exactly ten retainers"),
            70: ("Biryu leads families", "household goods"),
            71: ("Biryu leads one distinct migrant group", "Onjo leads the other distinct migrant group"),
            72: ("lead their two unarmed groups peacefully", "separate roads"),
            73: ("Onjo directs workers and settlers building", "riverside Wirye"),
            74: ("Biryu directs his followers as they establish", "capital settlement at Michuhol"),
            75: ("At one natural branch point", "without showing two distant capitals"),
            76: ("unidentified riverside Wirye settlement south of the Han River",),
            77: ("exactly ten retainers total, including Ogan and Maryeo",),
            78: ("Onjo governs the small new settlement", "exactly ten retainers total"),
            79: ("modest plain timber palisade", "exactly ten retainers organize"),
            80: ("Onjo turns the ten retainers' advice into settlement governance",),
            81: ("At wet coastal Michuhol", "exactly one blank unmarked woven banner"),
            82: ("wet tidal ground", "brackish wells"),
            83: ("Michuhol settlement visibly fails", "families prepare to leave"),
            84: ("one failing coastal Michuhol settlement", "Onjo and distant Wirye are not simultaneously shown"),
            85: ("Biryu enters the plain timber gate", "stable Wirye settlement"),
            86: ("ordered thatched houses", "grain stores"),
            87: ("Biryu stands inside the thriving settlement", "younger brother's organized polity"),
            88: ("Biryu stands alone in restrained remorse", "empty hands"),
            89: ("closed blank unmarked later historical record", "empty unoccupied place"),
            90: ("Deceased Biryu lies still", "cause and method of death not depicted"),
            91: ("closed blank unmarked later record", "no suicide claim or death method"),
            92: ("family members walk together", "no person carries another person"),
            93: ("former retainers and civilians", "move together toward Wirye"),
            94: ("officials and civilians pass peacefully", "Onjo is not added to the scene"),
            95: ("incoming former Michuhol group joins and mingles peacefully", "one resident Wirye group"),
            96: ("two formerly divided communities gather together around him", "shared leadership"),
            97: ("large merged population willingly gathers", "workers expand plain timber defenses"),
            98: ("Onjo's settlement grows", "Biryu remains absent"),
            99: ("closed blank unmarked later source manuscript", "no reenacted ancient event"),
            100: ("two closed blank unmarked genealogy manuscript covers", "two alternative lineages never merge"),
        }
        object_cuts = {7, 14, 36, 89, 91, 99, 100}
        landscape_cuts = {6, 8, 10, 11, 49}
        expected_negative_by_cut = {
            1: ("same village courtyard", "face-to-face pair", "both men in foreground", "barefoot"),
            5: (
                "lying man",
                "asphalt road",
                "road centerline",
                "modern brimmed hat",
                "ankle boots",
            ),
            7: ("modern hardcover book", "Western codex", "hardback spine"),
            14: (
                "white background",
                "modern hardcover book",
                "Christian cross",
                "crucifix",
                "cross-shaped marker",
            ),
            15: ("visible Utae", "young boy", "father figure"),
            16: ("all-male primary pair", "male Soseono", "bearded Soseono"),
            20: ("touching hands", "merged hands", "cropped trousers", "exposed calves"),
            23: (
                "front-facing Yuri",
                "visible Yuri face",
                "palisade entrance behind Yuri",
                "visible arms",
                "visible hands",
                "visible legs",
                "visible feet",
                "full-body Yuri",
            ),
            24: (
                "fifth person",
                "child",
                "second woman",
                "woman at far-right",
                "female face at far-right",
                "male Soseono",
                "female Biryu",
                "female Onjo",
                "female Yuri",
                "long-haired Yuri",
                "Yuri ponytail",
                "visible arms",
                "visible elbows",
                "visible hands",
            ),
            25: (
                "front-facing Yuri",
                "side-profile Yuri",
                "three-quarter Yuri face",
                "visible Yuri face",
                "visible Yuri eye nose or cheek",
                "palisade entrance behind Yuri",
                "visible hands",
                "visible legs",
                "visible feet",
            ),
            26: (
                "adult woman",
                "female face",
                "visible arms",
                "visible hands",
                "visible forearms",
                "visible elbows",
                "visible wrists",
                "chest below collarbones",
                "full body",
            ),
            27: (
                "adult woman",
                "visible Yuri",
                "visible hands",
                "visible fingers",
                "visible forearms",
                "visible elbows",
                "visible wrists",
                "visible waist",
                "visible legs",
                "full body",
                "crown",
                "throne",
                "weapon",
            ),
            28: (
                "third person",
                "extra background person",
                "visible Yuri",
                "looking at each other",
                "eye contact",
                "facing each other",
                "inward-facing profiles",
                "Soseono looking left",
                "Soseono nose pointing left",
                "Soseono facing Jumong",
                "guard",
            ),
            29: (
                "cropped modern haircut",
                "undercut",
                "roofed gate",
                "tiled eaves",
                "gatehouse",
                "black tailored jacket",
                "Western suit jacket",
                "lapels",
                "white shirt collar",
                "tailored center-back seam",
            ),
            30: (
                "fifth person",
                "house door",
                "domestic doorway",
                "crew-neck sweater",
                "second woman",
                "female Yuri",
                "female Biryu",
                "female Onjo",
                "male Soseono",
                "closed gate",
                "writing on gate",
            ),
        }

        self.assertEqual(set(required_by_cut), set(range(1, 101)))
        for cut_number, required_terms in required_by_cut.items():
            with self.subTest(cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertLessEqual(len(compiled.positive), 1200)
                self.assertLessEqual(len(compiled.negative), 760)
                for term in required_terms:
                    self.assertIn(term, compiled.positive)
                for term in expected_negative_by_cut.get(cut_number, ()):
                    self.assertIn(term, compiled.negative)
                if cut_number == 24:
                    self.assertEqual(compiled.person_count, 4)
                    self.assertIsNotNone(compiled.scene_contract)
                    self.assertEqual(compiled.scene_contract.person_count, 4)
                    self.assertEqual(compiled.scene_contract.visible_hand_count, 0)
                    self.assertEqual(
                        compiled.scene_contract.framing,
                        "extreme facial close-up",
                    )
                    self.assertEqual(compiled.scene_contract.face_visibility, "visible")
                if cut_number == 25:
                    self.assertIsNotNone(compiled.scene_contract)
                    self.assertEqual(compiled.scene_contract.face_visibility, "hidden")
                if cut_number in {27, 28}:
                    self.assertEqual(compiled.person_count, 2)
                    self.assertIsNotNone(compiled.scene_contract)
                    self.assertEqual(compiled.scene_contract.person_count, 2)
                    self.assertEqual(compiled.scene_contract.visible_hand_count, 0)
                if cut_number == 27:
                    self.assertIn(
                        "composition=baekje_ep01_cut27_paired_face_close",
                        compiled.diagnostics,
                    )
                if cut_number == 28:
                    self.assertEqual(compiled.scene_contract.framing, "chest-up")
                    self.assertIn(
                        "composition=baekje_ep01_cut28_diverging_gazes",
                        compiled.diagnostics,
                    )
                if cut_number == 29:
                    self.assertEqual(compiled.person_count, 1)
                    self.assertIsNotNone(compiled.scene_contract)
                    self.assertEqual(compiled.scene_contract.person_count, 1)
                    self.assertEqual(compiled.scene_contract.visible_hand_count, 0)
                    self.assertEqual(compiled.scene_contract.framing, "head-and-shoulders")
                    self.assertEqual(compiled.scene_contract.face_visibility, "hidden")
                    self.assertIn(
                        "composition=baekje_ep01_cut29_closed_gate_rear",
                        compiled.diagnostics,
                    )
                if cut_number == 30:
                    self.assertEqual(compiled.person_count, 4)
                    self.assertIsNotNone(compiled.scene_contract)
                    self.assertEqual(compiled.scene_contract.person_count, 4)
                    self.assertEqual(compiled.scene_contract.visible_hand_count, 0)
                    self.assertEqual(
                        compiled.scene_contract.framing,
                        "extreme facial close-up",
                    )
                    self.assertEqual(compiled.scene_contract.face_visibility, "visible")
                    self.assertIn(
                        "composition=baekje_ep01_cut30_open_gate_reaction",
                        compiled.diagnostics,
                    )
                if cut_number in {1, 5}:
                    self.assertNotIn("one interaction", compiled.positive)
                if cut_number in object_cuts:
                    self.assertEqual(compiled.scene_kind, "object")
                    self.assertIsNone(compiled.person_count)
                if cut_number in landscape_cuts:
                    self.assertEqual(compiled.scene_kind, "landscape")
                    self.assertIsNone(compiled.person_count)

        self.assertTrue(
            _should_ignore_object_person_segmentation(
                self._runtime_baekje_ep01_cut(payload, 14)
            )
        )
        self.assertFalse(
            _should_ignore_object_person_segmentation(
                self._runtime_baekje_ep01_cut(payload, 15)
            )
        )

    def test_baekje_ep01_locks_require_exact_structured_source_and_narration(self):
        payload = self._actual_baekje_ep01_prepared_fixture()

        raw_cut13 = payload["cuts"][12]["image_prompt"]
        raw = self.compile(raw_cut13)
        self.assertNotIn("Soseono stands with her sons Biryu and Onjo", raw.positive)
        self.assertNotIn(
            "timber structures, packed-earth walls, rough thatch roofs",
            raw.positive,
        )

        structured_cut13 = self._structured_baekje_ep01_cut(payload, 13)
        near_period = structured_cut13.replace(
            "Year/period: Late 1st century BC foundation tradition through the early reign of King Onjo; "
            "Goguryeo, Mahan, and Baekje historical context",
            "Year/period: Late 1st century BC; Goguryeo, Mahan, and Baekje historical context",
            1,
        )
        near_period_compiled = self.compile(near_period)
        self.assertNotIn(
            "Soseono stands with her sons Biryu and Onjo",
            near_period_compiled.positive,
        )
        self.assertNotIn(
            "timber structures, packed-earth walls, rough thatch roofs",
            near_period_compiled.positive,
        )

        near_scene = structured_cut13.replace(
            "directs people and supplies in the Jolbon settlement.",
            "coordinates people and supplies in the Jolbon settlement.",
            1,
        )
        near_scene_compiled = self.compile(near_scene)
        self.assertIn(
            "Soseono stands with her sons Biryu and Onjo",
            near_scene_compiled.positive,
        )
        self.assertIn(
            "timber structures, packed-earth walls, rough thatch roofs",
            near_scene_compiled.positive,
        )

        cut12 = self._structured_baekje_ep01_cut(payload, 12)
        near_narration = cut12.replace(
            "그때 주몽에게 손을 내민 인물이 졸본의 유력자 소서노였죠.",
            "그때 주몽에게 손을 내민 인물이 소서노였죠.",
            1,
        )
        near_narration_compiled = self.compile(near_narration)
        self.assertNotIn("hands lowered and relaxed", near_narration_compiled.positive)
        self.assertEqual(near_narration_compiled.scene_kind, "landscape")

        late_seventh = self.compile(
            "Year/period: 666-668 AD Goguryeo succession; "
            "Exact place: Goguryeo court and fortress district; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            f"Scene: {raw_cut13}"
        )
        self.assertIn("Era/period: late seventh-century Goguryeo succession", late_seventh.positive)
        self.assertNotIn("Soseono stands with her sons Biryu and Onjo", late_seventh.positive)
        self.assertNotIn(
            "timber structures, packed-earth walls, rough thatch roofs",
            late_seventh.positive,
        )

    def test_baekje_ep01_actor_locks_survive_retry_compilation(self):
        payload = self._actual_baekje_ep01_script_fixture()
        required_by_cut = {
            1: ("Displaced prince Onjo moves south and screen-right", "no eye contact and no interaction"),
            5: (
                "walks screen-right across bare earth in low hide shoes",
                "Biryu remains standing on both feet",
                "no eye contact",
            ),
            7: ("traditional East Asian thread-bound manuscript", "visible external binding thread"),
            12: ("Soseono steps beside adult man Jumong", "hands lowered and relaxed"),
            14: ("thread-bound genealogy manuscript", "exactly three flat rectangular wooden tags"),
            15: ("two similarly aged younger adult male sons", "no husband or father figure"),
            16: ("Exactly one adult woman Soseono", "exactly one adult man Jumong enters Jolbon at right"),
            20: ("fabric covers each calf to the ankles", "lowered hands remain apart with clear air"),
            33: ("Jumong installs Yuri", "as crown prince"),
            36: ("two closed blank unmarked manuscript covers",),
            44: ("eight distinct adult officials", "two clear rows of four"),
            48: ("exactly two separate broad river courses",),
            50: ("One distant migrant group moves south", "plausible natural paths branch"),
            52: ("Exactly ten retainers total", "Ogan and Maryeo"),
            71: ("one distinct migrant group", "other distinct migrant group"),
            75: ("one natural branch point", "without showing two distant capitals"),
            84: ("one failing coastal Michuhol settlement", "Onjo and distant Wirye are not simultaneously shown"),
            89: ("later historical record", "empty unoccupied place"),
            92: ("no person carries another person",),
            94: ("Onjo is not added to the scene",),
            95: ("incoming former Michuhol group joins", "resident Wirye group"),
            99: ("later source manuscript", "no reenacted ancient event"),
            100: ("two alternative lineages never merge",),
        }
        for cut_number, required in required_by_cut.items():
            with self.subTest(cut=cut_number):
                compiled = compile_image_prompt(
                    self._runtime_baekje_ep01_cut(payload, cut_number),
                    model_id="comfyui-flux2-klein-4b",
                    quality_hint=(
                        "Preserve exact actor count, separate complete bodies, and the requested visible action"
                    ),
                )
                self.assertLessEqual(len(compiled.positive), 1200)
                self.assertLessEqual(len(compiled.negative), 760)
                for term in required:
                    self.assertIn(term, compiled.positive)

    def test_actual_baekje_ep01_late_exact_locks_match_runtime_sources_and_retries(self):
        payload = self._actual_baekje_ep01_script_fixture()
        omitted_cuts = {109, 115, 117, 133}
        modern_cuts = set(range(106, 115))
        later_comparative_cuts = {103, 104, 105, 146, 147, 148, 149, 150}
        material_free_ancient_cuts = {116, 118, 119, 121, 122}
        expected_material_free_kinds = {
            116: "object",
            118: "animal",
            119: "animal",
            121: "landscape",
            122: "landscape",
        }
        locked_cuts = tuple(
            cut_number
            for cut_number in range(101, 151)
            if cut_number not in omitted_cuts
        )
        exact_locks = prompt_compiler_module._BAEKJE_EP01_LATE_EXACT_LOCKS

        self.assertEqual(len(locked_cuts), 46)
        self.assertEqual(len(exact_locks), 100)
        for cut_number in locked_cuts:
            with self.subTest(cut=cut_number):
                source = self._runtime_baekje_ep01_cut(payload, cut_number)
                fields = prompt_compiler_module._extract_fields(source)
                runtime_scene = prompt_compiler_module._field(fields, "Scene")
                runtime_narration = prompt_compiler_module._field(
                    fields, "Narration context"
                )
                matches = [
                    lock
                    for (scene, narration), lock in exact_locks.items()
                    if runtime_scene.startswith(scene)
                    and runtime_narration == narration
                ]
                self.assertEqual(len(matches), 1)
                expected_subject, expected_action, _, _ = matches[0]

                for quality_hint in (
                    "",
                    "Preserve exact roles, separate complete bodies, natural anatomy, and the requested action",
                ):
                    compiled = compile_image_prompt(
                        source,
                        model_id="comfyui-flux2-klein-4b",
                        quality_hint=quality_hint,
                    )
                    self.assertLessEqual(len(compiled.positive), 1200)
                    self.assertLessEqual(len(compiled.negative), 760)
                    expected_subject_prefix = expected_subject.split(";", 1)[0][:36]
                    self.assertIn(expected_subject_prefix, compiled.positive)
                    self.assertIn(expected_action[:36], compiled.positive)

                if cut_number in later_comparative_cuts:
                    self.assertEqual(compiled.scene_kind, "object")
                    self.assertIsNone(compiled.person_count)
                    self.assertIn(
                        "Era/period: Later comparative historical records",
                        compiled.positive,
                    )
                    self.assertIn(
                        "Exact place: a plain later archival setting",
                        compiled.positive,
                    )
                elif cut_number in modern_cuts:
                    self.assertNotIn(
                        "timber structures, packed-earth walls, thatch roofs, plain woven clothing",
                        compiled.positive,
                    )
                elif cut_number in material_free_ancient_cuts:
                    self.assertEqual(
                        compiled.scene_kind,
                        expected_material_free_kinds[cut_number],
                    )
                    self.assertIsNone(compiled.person_count)
                    self.assertIn(
                        "Era/period: Late 1st century BC foundation tradition through the early reign of King Onjo",
                        compiled.positive,
                    )
                else:
                    era = compiled.positive.split("Era/period: ", 1)[1].split(
                        ". Culture scope:", 1
                    )[0]
                    self.assertIn(
                        era,
                        {
                            "Late 1st century BC",
                            "Late 1st century BC foundation tradition through the early reign of King Onjo",
                        },
                    )
                    for term in (
                        "timber structures",
                        "packed-earth walls",
                        "rough thatch roofs",
                    ):
                        self.assertIn(term, compiled.positive)

                if cut_number not in modern_cuts:
                    for term in (
                        "tiled roof",
                        "curved roof",
                        "glazed roof tiles",
                        "ornate palace",
                        "later-period palace",
                        "Joseon palace",
                        "Chinese palace",
                        "signboard",
                    ):
                        self.assertIn(term, compiled.negative)

    def test_actual_baekje_ep01_late_actions_and_places_follow_the_script(self):
        payload = self._actual_baekje_ep01_script_fixture()
        required_by_cut = {
            101: ("exactly three named people", "Jumong stands with Biryu and Onjo"),
            102: ("exactly four named people", "Utae", "Soseono", "Biryu", "Onjo"),
            110: ("Multiple present-day archaeologists", "layered dwelling foundations"),
            111: ("Multiple present-day archaeologists", "layered dwellings", "repaired defenses"),
            116: ("closed blank unmarked", "one exposed settlement layer"),
            120: ("Workers reinforce", "Baekje defenders prepare"),
            125: (
                "exactly two plain timber and packed-earth frontier defenses",
                "unidentified approaches",
                "Nangnang-side group of unspecified role and count",
            ),
            126: ("exactly one Nangnang envoy", "hands concealed inside closed sleeves"),
            128: ("Malgal attackers advance from outside", "Baekje defenders hold separate positions inside"),
            129: ("Malgal raiders breach", "Baekje defenders retreat"),
            131: ("Onjo directs separate worker crews rebuilding exactly two", "Doksan and Gucheon"),
            132: ("Onjo turns his attention south", "Mahan political center"),
            134: (
                "Onjo calmly announces a hunting excursion",
                "unseen recipients beyond the frame",
                "weapons remain sheathed",
            ),
            135: ("secondary disguised Baekje soldiers", "concealed military equipment"),
            138: ("reorganizes into a Baekje attack formation", "Mahan defenders"),
            142: ("commander Jugun", "stronghold Ugokseong"),
            143: ("Jugun and the remaining resistance", "unidentified", "stronghold"),
            144: ("fully shrouded deceased Jugun", "method concealed"),
            145: (
                "exactly one fully shrouded body",
                "one continuous closed body-length covering on one bier",
                "one waist-level seam",
                "wife-and-children group remains behind it",
            ),
            146: ("closed face-down blank unmarked thread-bound later source manuscripts", "Guthe-hypothesis manuscript"),
            147: (
                "closed face-down blank unmarked traditional East Asian thread-bound later source manuscripts",
                "Guthe external-source hypothesis manuscript",
                "clay Daifang coastal relief",
            ),
        }

        for cut_number, required in required_by_cut.items():
            with self.subTest(cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertLessEqual(len(compiled.positive), 1200)
                self.assertLessEqual(
                    len(compiled.negative),
                    1300 if cut_number in {146, 147, 148, 149, 150} else 760,
                )
                for term in required:
                    self.assertIn(term, compiled.positive)

    def test_actual_baekje_ep01_late_role_and_anatomy_guards_are_explicit(self):
        payload = self._actual_baekje_ep01_script_fixture()

        required_final_negative = (
            "missing fingers",
            "fused fingers",
            "missing arms",
            "missing legs",
            "two heads on one body",
            "two bodies sharing one head",
            "modern T-shirt",
            "modern shorts",
            "barefoot",
        )
        for cut_number in range(1, 101):
            with self.subTest(finger_contract_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertLessEqual(len(compiled.positive), 1200)
                self.assertLessEqual(len(compiled.negative), 760)
                for term in required_final_negative:
                    self.assertIn(term, compiled.negative)
                if compiled.scene_kind not in {"single", "pair", "group"}:
                    continue
                for term in (
                    "six fingers",
                    "extra fingers",
                ):
                    self.assertIn(term, compiled.negative)
                if (
                    "exactly zero visible hands" in compiled.positive
                    or "zero visible arms, elbows, forearms, wrists, hands, waists, legs or feet"
                    in compiled.positive
                    or "zero visible forearms, wrists, hands or fingers" in compiled.positive
                    or "zero visible upper arms, elbows, forearms, wrists, hands or fingers"
                    in compiled.positive
                    or "zero visible upper arms, elbows, forearms, wrists, hands, chest below collarbones, waists, legs or feet"
                    in compiled.positive
                ):
                    self.assertTrue(
                        "wrists end outside the crop or behind stated occlusion" in compiled.positive
                        or "all forearms, lower bodies, legs and feet stay outside frame" in compiled.positive
                        or "trio arms below frame" in compiled.positive
                        or "lower frame ends at both collarbones" in compiled.positive
                        or "zero visible arms, hands, waists, legs or feet" in compiled.positive
                        or "zero visible arms, hands or fingers" in compiled.positive
                        or "zero visible arms, waists, legs or feet" in compiled.positive
                        or "zero visible arms, elbows, forearms, wrists, hands, waists, legs or feet"
                        in compiled.positive
                        or "zero visible forearms, wrists, hands or fingers" in compiled.positive
                        or "zero visible upper arms, elbows, forearms, wrists, hands or fingers"
                        in compiled.positive
                        or "zero visible upper arms, elbows, forearms, wrists, hands, chest below collarbones, waists, legs or feet"
                        in compiled.positive
                        or "lower edge ends below the shoulder blades" in compiled.positive
                        or "lower edge crops at the upper shoulder blades" in compiled.positive
                        or "torso below the armpits stays outside frame" in compiled.positive
                        or "clasped hands hidden behind his back" in compiled.positive
                    )
                else:
                    self.assertNotIn("any visible hand has five digits", compiled.positive)
                    self.assertNotIn("visible hands have five digits each", compiled.positive)
                    self.assertNotIn("hands have five digits each", compiled.positive)

        cut52 = self.compile(self._runtime_baekje_ep01_cut(payload, 52))
        self.assertIn("exactly ten adult retainers total including Ogan and Maryeo", cut52.positive)
        self.assertIn("with Ogan and Maryeo among the ten", cut52.positive)
        for term in ("eleventh retainer", "twelve retainers", "duplicate Ogan", "duplicate Maryeo"):
            self.assertIn(term, cut52.negative)

        for cut_number in (88, 90):
            with self.subTest(death_method_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                positive = compiled.positive.lower()
                for forbidden in (
                    "suicide",
                    "hanging",
                    "poison",
                    "stabbed",
                    "sword wound",
                    "weapon wound",
                    "blood pool",
                ):
                    self.assertNotIn(forbidden, positive)
                for guarded in ("suicide", "hanging", "poison", "blood"):
                    self.assertIn(guarded, compiled.negative)

        for cut_number in (89, 91):
            with self.subTest(absent_death_record_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "object")
                self.assertIsNone(compiled.person_count)
                self.assertIn("closed blank unmarked later", compiled.positive)
                self.assertIn("empty", compiled.positive)
                for guarded in ("suicide", "hanging", "poison", "blood"):
                    self.assertIn(guarded, compiled.negative)

        genealogy_contracts = {
            103: (
                "exactly two closed blank unmarked period-valid record media",
                ("Jumong", "Utae"),
                ("living Jumong", "living Utae", "living Biryu", "living Onjo"),
            ),
            104: (
                "exactly three closed blank unmarked period-valid record media",
                (),
                ("living historical figure", "fourth record medium"),
            ),
            105: (
                "exactly two closed blank unmarked period-valid record media",
                ("Onjo", "Biryu"),
                ("living Onjo", "living Biryu", "historical reenactment"),
            ),
        }
        for cut_number, (
            expected_records,
            expected_marker_names,
            expected_negative_guards,
        ) in genealogy_contracts.items():
            with self.subTest(object_only_genealogy_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "object")
                self.assertIsNone(compiled.person_count)
                subject = self._compiled_contract_field(
                    compiled.positive, "Primary subject", "Era/period"
                )
                action = self._compiled_contract_field(
                    compiled.positive, "Visible action", "Primary subject"
                )
                self.assertIn(expected_records, subject)
                for name in expected_marker_names:
                    self.assertIn(name, compiled.positive)
                for term in expected_negative_guards:
                    self.assertIn(term, compiled.negative)
                self.assertIn("person", compiled.negative)
                self.assertNotIn("human figure", action.lower())

        for cut_number in range(112, 115):
            with self.subTest(modern_archaeologists_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "group")
                self.assertIn("multiple present-day South Korean archaeologists", compiled.positive)
                self.assertIn("single archaeologist", compiled.negative)

        for cut_number in (118, 119):
            with self.subTest(single_dragon_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "animal")
                subject = self._compiled_contract_field(
                    compiled.positive, "Primary subject", "Era/period"
                )
                action = self._compiled_contract_field(
                    compiled.positive, "Visible action", "Primary subject"
                )
                self.assertIn("exactly one", subject)
                self.assertNotIn("Onjo", subject)
                self.assertNotIn("Onjo", action)
                for term in ("human Onjo", "second dragon", "human-dragon hybrid"):
                    self.assertIn(term, compiled.negative)
                self.assertIn("composition=single_blue_dragon", compiled.diagnostics)
                self.assertIn("one coherent silhouette", compiled.positive)
                self.assertNotIn("separated animal silhouettes", compiled.positive)

        cut120 = self.compile(self._runtime_baekje_ep01_cut(payload, 120))
        self.assertEqual(cut120.scene_kind, "group")
        self.assertIn("frontier defenders and workers", cut120.positive)
        self.assertNotIn("dragon", cut120.positive.lower())
        self.assertIn("blue dragon", cut120.negative)

        expected_kinds = {
            124: "group",
            125: "group",
            126: "pair",
            127: "pair",
            128: "group",
            129: "group",
            130: "group",
            134: "single",
            135: "group",
            138: "group",
        }
        expected_person_counts = {126: 2, 127: 2, 134: 1}
        for cut_number, expected_kind in expected_kinds.items():
            with self.subTest(separated_roles_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, expected_kind)
                if cut_number in expected_person_counts:
                    self.assertEqual(
                        compiled.person_count,
                        expected_person_counts[cut_number],
                    )

        cut125 = self.compile(self._runtime_baekje_ep01_cut(payload, 125))
        self.assertIn(
            "Nangnang-side group of unspecified role and count",
            cut125.positive,
        )
        self.assertIn("fixed Nangnang group count", cut125.negative)

        for cut_number in (126, 127):
            compiled = self.compile(self._runtime_baekje_ep01_cut(payload, cut_number))
            for term in ("second envoy", "third person", "visible hand", "visible fingers"):
                self.assertIn(term, compiled.negative)

        cut145 = self.compile(self._runtime_baekje_ep01_cut(payload, 145))
        self.assertEqual(cut145.scene_kind, "group")
        self.assertIn(
            "composition=ugok_single_jugun_identity_uncounted_family",
            cut145.diagnostics,
        )
        for term in (
            "exposed corpse",
            "visible severed waist",
            "exposed wound",
            "blood pool",
            "blood spray",
            "organs",
            "graphic gore",
            "duplicated Jugun body",
            "two Jugun bodies",
            "fixed family count",
        ):
            self.assertIn(term, cut145.negative)
        for term in (
            "exactly one fully shrouded body",
            "one continuous closed body-length covering on one bier",
            "one waist-level seam",
            "exactly one deceased Jugun identity",
            "never separates the shroud into two bodies",
            "uncounted fully covered wife-and-children group",
        ):
            self.assertIn(term, cut145.positive)
        self.assertNotIn("two fully covered shrouded bier sections", cut145.positive)
        self.assertFalse(_should_check_internal_text_after_generation(cut145.positive))

        cut90 = self.compile(self._runtime_baekje_ep01_cut(payload, 90))
        self.assertEqual(cut90.scene_kind, "single")
        self.assertEqual(cut90.person_count, 1)
        self.assertIn("composition=single_story", cut90.diagnostics)
        self.assertIn("Deceased Biryu lies still", cut90.positive)
        self.assertIn("complete period clothing", cut90.positive)
        self.assertIn("cause and method of death not depicted", cut90.positive)
        self.assertNotIn("fully shrouded", cut90.positive)

        guthe_positive_by_cut = {
            146: "Guthe-hypothesis manuscript",
            147: "Guthe external-source hypothesis manuscript",
        }
        for cut_number, expected_positive in guthe_positive_by_cut.items():
            with self.subTest(guthe_transition_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertIn(expected_positive, compiled.positive)
                self.assertIn("living Guthe", compiled.negative)

    def test_actual_baekje_ep01_late_text_risks_are_blocked(self):
        payload = self._actual_baekje_ep01_script_fixture()

        banner_positive_by_cut = {81: "blank unmarked woven banner"}
        for cut_number, expected_positive in banner_positive_by_cut.items():
            with self.subTest(blank_banner_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertIn(expected_positive, compiled.positive)
                for term in ("marked banner", "writing on banner"):
                    self.assertIn(term, compiled.negative)

        for cut_number in (70, 71, 72, 74, 94, 95, 96):
            with self.subTest(no_invented_banner_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertNotIn("blank unmarked woven banner", compiled.positive)
                self.assertNotIn("blank unmarked cloth", compiled.positive)

        cut100 = self.compile(self._runtime_baekje_ep01_cut(payload, 100))
        self.assertIn("blank unmarked genealogy manuscript covers", cut100.positive)
        for term in ("readable writing", "written name", "open scroll"):
            self.assertIn(term, cut100.negative)

        for cut_number in (101, 102, 103, 104, 105, 146, 147, 148, 149, 150):
            with self.subTest(blank_record_media_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertIn("blank unmarked period-valid record medi", compiled.positive)
                for term in ("readable writing", "written name", "open scroll"):
                    self.assertIn(term, compiled.negative)

        cut106 = self.compile(self._runtime_baekje_ep01_cut(payload, 106))
        self.assertIn("closed blank unmarked manuscript covers", cut106.positive)
        self.assertNotIn("unreadable weathered marks", cut106.positive)
        self.assertIn("high-oblique present-day archaeological evidence view", cut106.positive)
        self.assertIn("Pungnap soil ledge", cut106.positive)
        self.assertIn("brown soil texture fills every corner", cut106.positive)
        self.assertIn("composition=mixed_pungnap_manuscript_evidence", cut106.diagnostics)
        self.assertNotIn("archival wood surface", cut106.positive)
        self.assertNotIn("straight-down 90-degree", cut106.positive)
        for term in (
            "readable writing",
            "unreadable pseudo-writing",
            "weathered glyph marks",
            "open written page",
            "black vignette",
            "solid black edge band",
            "archival desk",
            "third manuscript",
            "writing on manuscript cover",
        ):
            self.assertIn(term, cut106.negative)

        for cut_number in (107, 108):
            with self.subTest(pungnap_location_only_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertIsNone(
                    re.search(
                        r"\b(?:manuscript|document|paper)\b",
                        compiled.positive.lower(),
                    )
                )
                for term in ("manuscript", "document", "paper", "readable writing"):
                    self.assertIn(term, compiled.negative)

        for cut_number in (121, 122, 123):
            with self.subTest(unmarked_terrain_cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertIsNone(re.search(r"\bmap\b", compiled.positive.lower()))
                for term in ("map", "map label", "written place name", "signboard"):
                    self.assertIn(term, compiled.negative)

    def test_baekje_ep01_late_locks_reject_near_miss_runtime_keys(self):
        payload = self._actual_baekje_ep01_script_fixture()

        cases = (
            (126, "Exactly one Nangnang envoy delivers an oral warning to Onjo"),
            (112, "multiple present-day South Korean archaeologists at layered Pungnap urban remains"),
        )
        for cut_number, forbidden_exact_action in cases:
            with self.subTest(narration_near_miss_cut=cut_number):
                source = self._runtime_baekje_ep01_cut(payload, cut_number)
                narration = prompt_compiler_module._field(
                    prompt_compiler_module._extract_fields(source),
                    "Narration context",
                )
                source = source.replace(
                    f"Narration context: {narration}",
                    f"Narration context: {narration} 변경",
                    1,
                )
                compiled = self.compile(source)
                self.assertNotIn(forbidden_exact_action, compiled.positive)

        cut128_source = self._runtime_baekje_ep01_cut(payload, 128)
        cut128_fields = prompt_compiler_module._extract_fields(cut128_source)
        cut128_runtime_scene = prompt_compiler_module._field(cut128_fields, "Scene")
        cut128_runtime_narration = prompt_compiler_module._field(
            cut128_fields, "Narration context"
        )
        cut128_scene = next(
            scene
            for scene, narration in prompt_compiler_module._BAEKJE_EP01_LATE_EXACT_LOCKS
            if cut128_runtime_scene.startswith(scene)
            and cut128_runtime_narration == narration
        )
        near_scene = cut128_source.replace(
            cut128_scene,
            f"X{cut128_scene[1:]}",
            1,
        )
        self.assertNotIn(
            "Malgal attackers advance from outside",
            self.compile(near_scene).positive,
        )

        cut112_source = self._runtime_baekje_ep01_cut(payload, 112)
        near_culture = cut112_source.replace(
            "Culture scope: Goguryeo, Mahan, and Baekje;",
            "Culture scope: Goguryeo, Mahan, and Baekje historical context;",
            1,
        )
        self.assertNotIn(
            "multiple present-day South Korean archaeologists at layered Pungnap urban remains",
            self.compile(near_culture).positive,
        )

    def test_flux_contract_follows_research_order_and_budget(self):
        compiled = self.compile(
            "Year/period: 1215 AD; Exact place: Runnymede; "
            "Main subject: King John and one baron; "
            "Scene: The baron points to a sealed charter bundle while King John turns toward him; "
            "Scene evidence: river meadow, canvas tent, wooden table; "
            "Style: historical documentary illustration; Negative: no text, no watermark.",
            "comfyui-flux2-klein-4b",
        )
        order = [
            compiled.positive.index("Visible action:"),
            compiled.positive.index("Primary subject:"),
            compiled.positive.index("Era/period:"),
            compiled.positive.index("Exact place:"),
            compiled.positive.index("Visible evidence:"),
            compiled.positive.index("Composition:"),
            compiled.positive.index("Style:"),
        ]
        self.assertEqual(order, sorted(order))
        self.assertLessEqual(len(compiled.positive), 950)
        self.assertLessEqual(len(compiled.negative), 520)
        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)

    def test_realistic_people_style_phrase_does_not_force_group_classification(self):
        empty_landscape = self.compile(
            "an empty rammed-earth fortress wall under dawn light. Ancient Korean historical drama, "
            "realistic people, cinematic realism, no modern objects, no readable text."
        )

        self.assertEqual(empty_landscape.scene_kind, "landscape")
        self.assertIsNone(empty_landscape.person_count)
        self.assertIn("realistic people", empty_landscape.positive)

        actual_group = self.compile(
            "Onjo leads refugees along a riverbank. Ancient Korean historical drama, realistic people, "
            "cinematic realism, no modern objects, no readable text."
        )
        self.assertEqual(actual_group.scene_kind, "group")
        self.assertIn("realistic people", actual_group.positive)

        actual_people_subject = self.compile("Realistic people evacuate the fortress road at dawn.")
        self.assertEqual(actual_people_subject.scene_kind, "group")

    def test_scroll_cylinder_rewrite_is_idempotent(self):
        first = self.compile(
            "Year/period: late 1st century BC; Exact place: Wirye; "
            "Scene: one open scroll rests on a timber surface."
        )
        second = self.compile(first.positive)

        for compiled in (first, second):
            self.assertEqual(compiled.positive.count("closed cord-tied scroll cylinder"), 1)
            self.assertNotIn("closed cord-tied closed cord-tied", compiled.positive)
            self.assertNotIn("scroll cylinder cylinder", compiled.positive)

    def test_baekje_ep01_opening_montage_is_one_textless_continuous_panorama(self):
        cameras = (
            "wide establishing shot with layered geographic depth",
            "low-angle tracking view centered on decisive movement",
            "tight profile composition with compressed background tension",
        )
        scope = (
            "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, and Ugok Fortress"
        )
        base_negative = (
            "extra fingers, missing fingers, fused fingers, malformed hands, extra arms, missing arms, "
            "extra legs, missing legs, twisted limbs, broken joints, duplicated body, deformed anatomy, "
            "malformed feet, unreadable text, letters, numbers, watermark, logo, UI"
        )
        required_negative = {
            "split panel",
            "split screen",
            "comic panel",
            "multi-panel layout",
            "triptych",
            "storyboard",
            "collage",
            "inset frame",
            "panel border",
            "vertical divider",
            "horizontal divider",
            "readable text",
            "text on banner",
            "writing on banner",
            "letters on banner",
            "latin letters",
            "fake english text",
            "chinese characters",
            "pseudo-glyph",
            "banner emblem",
            "flag insignia",
            "marked banner",
            "watermark",
            "logo",
            "signature",
        }

        for camera in cameras:
            with self.subTest(camera=camera):
                source = (
                    "Global visual world: Time range: Late 1st century BC; "
                    f"Place scope: {scope}; Culture scope: Goguryeo, Mahan, and Baekje; "
                    "Year/period: Late 1st century BC; "
                    f"Exact place: {scope}; "
                    "Scene: a tense historical montage shows exiled Onjo, defeated Biryu outside Wirye, "
                    "a broken coastal banner, and the looming Mahan campaign without modern collage effects. "
                    "Ancient Korean historical drama, realistic people, restrained tension, clear staging, "
                    f"{camera}, directional natural light, 35mm lens, cinematic realism, no modern objects."
                )
                compiled = compile_image_prompt(
                    source,
                    model_id="comfyui-flux2-klein-4b",
                    base_negative=base_negative,
                )
                negative_terms = {term.strip().lower() for term in compiled.negative.split(",")}

                self.assertEqual(compiled.scene_kind, "group")
                self.assertIsNone(compiled.person_count)
                self.assertIsNone(compiled.scene_contract.visible_hand_count)
                for term in (
                    "one continuous panoramic historical scene",
                    "one shared ground plane",
                    "one unbroken natural horizon",
                    "one continuous sky",
                    "defeated Biryu outside his younger brother's packed-earth settlement",
                    "small collapsed torn unmarked undyed woven-cloth banner",
                    "narrow crumpled folds on sandy ground",
                    "narrow crumpled folds on sandy ground in the midground",
                    "distant Mahan campaign silhouettes",
                ):
                    self.assertIn(term, compiled.positive)
                self.assertNotIn("historical montage", compiled.positive.lower())
                self.assertNotIn("modern collage effects", compiled.positive.lower())
                self.assertNotIn("defeated Biryu outside Wirye", compiled.positive)
                self.assertNotIn(
                    "torn blank unmarked undyed woven-cloth coastal banner",
                    compiled.positive,
                )
                self.assertTrue(_should_check_internal_text_after_generation(compiled.positive))
                self.assertTrue(
                    _should_use_continuous_montage_banner_text_detector(compiled.positive)
                )
                self.assertTrue(required_negative.issubset(negative_terms))
                self.assertTrue({"extra head", "malformed hands", "extra fingers"}.issubset(negative_terms))
                self.assertIn("composition=continuous_historical_panorama", compiled.diagnostics)
                self.assertLessEqual(len(compiled.negative), 520)

    def test_baekje_opening_montage_rewrite_requires_exact_source_condition(self):
        compiled = self.compile(
            "a tense historical montage shows exiled Onjo, defeated Biryu outside Wirye, "
            "a broken coastal banner, and the looming Mahan campaign under storm clouds. "
            "Ancient Korean historical drama, realistic people, cinematic realism."
        )

        self.assertIn("defeated Biryu outside Wirye", compiled.positive)
        self.assertIn("broken coastal banner", compiled.positive)
        self.assertNotIn("younger brother's packed-earth settlement", compiled.positive)
        self.assertNotIn("small collapsed torn unmarked undyed woven-cloth banner", compiled.positive)
        self.assertNotIn("composition=continuous_historical_panorama", compiled.diagnostics)
        self.assertFalse(
            _should_use_continuous_montage_banner_text_detector(compiled.positive)
        )

    def test_baekje_ep01_origin_transition_is_one_continuous_landscape(self):
        cameras = (
            "high-angle view showing the opposing groups clearly",
            "ground-level action view with strong foreground detail",
            "lateral cinematic composition showing cause and reaction",
        )
        required_negative = {
            "split panel",
            "split screen",
            "comic panel",
            "multi-panel layout",
            "triptych",
            "storyboard",
            "collage",
            "inset frame",
            "panel border",
            "vertical divider",
            "horizontal divider",
            "readable text",
            "latin letters",
            "fake english text",
            "chinese characters",
            "pseudo-glyph",
        }

        for camera in cameras:
            with self.subTest(camera=camera):
                compiled = self.compile(
                    "Onjo's disguised hunting force turns toward the Mahan center while the image "
                    "transitions into an ancient northern origin landscape. Ancient Korean historical "
                    "drama, realistic people, restrained tension, clear staging, "
                    f"{camera}, directional natural light, cinematic realism, no modern objects."
                )
                negative_terms = {term.strip().lower() for term in compiled.negative.split(",")}

                self.assertEqual(compiled.scene_kind, "group")
                self.assertIsNone(compiled.person_count)
                for term in (
                    "one continuous ancient northern origin landscape",
                    "one shared ground plane",
                    "one unbroken natural horizon",
                    "one continuous sky",
                    "Onjo's disguised hunting force",
                    "Mahan center",
                ):
                    self.assertIn(term, compiled.positive)
                self.assertNotIn("image transitions", compiled.positive.lower())
                self.assertTrue(_should_check_internal_text_after_generation(compiled.positive))
                self.assertTrue(required_negative.issubset(negative_terms))
                self.assertIn(
                    "composition=continuous_historical_transition_panorama",
                    compiled.diagnostics,
                )
                self.assertLessEqual(len(compiled.negative), 520)

    def test_baekje_named_people_roles_and_actions_remain_human_scenes(self):
        cases = (
            (
                "a tense historical montage shows exiled Onjo, defeated Biryu outside Wirye, "
                "a broken coastal banner, and the looming Mahan campaign",
                "group",
            ),
            ("Onjo's disguised hunting force turns toward the Mahan center", "group"),
            ("early Goguryeo settlers gather around timber palisades", "group"),
            ("young Biryu and Onjo grow within an early Goguryeo royal household", "group"),
            ("Yuri travels alone through a rugged northern landscape toward Jolbon", "single"),
            (
                "Jumong installs Yuri as crown prince while Biryu, Onjo, and Soseono remain at the edge of the court",
                "group",
            ),
            ("Biryu and Onjo lose political standing at the reorganized court", "group"),
            ("Soseono, Biryu, and Onjo confer beside packed belongings", "group"),
            ("Biryu indicates Michuhol as the retainers object", "group"),
            ("Biryu's followers struggle in wet tidal ground at Michuhol", "group"),
            ("Biryu stands isolated after recognizing the failure of Michuhol", "single"),
            ("a scribe records the change from Sipje to Baekje", "single"),
            ("archaeologists uncover layered dwellings inside Pungnap fortress", "group"),
            ("mounted Malgal raiders move along northern routes", "group"),
            ("a Nangnang envoy confronts Onjo inside a plain timber audience hall", "group"),
            ("Onjo orders new defensive lines at Doksan and Gucheon", "single"),
            ("Onjo's supposed hunting procession changes direction through forest roads", "group"),
            ("Baekje forces seize the Mahan center while survivors scatter", "group"),
            ("former Mahan commander Jugun gathers remaining fighters inside Ugokseong", "group"),
        )
        style = (
            ". Ancient Korean historical drama, realistic people, restrained tension, clear staging, "
            "cinematic realism, no modern objects, no readable text."
        )
        nonhuman_bans = {"person", "people", "human limbs", "face", "hands"}

        for scene, expected_kind in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(scene + style)
                negative_terms = {term.strip().lower() for term in compiled.negative.split(",")}
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertTrue(nonhuman_bans.isdisjoint(negative_terms))
                self.assertIsNone(compiled.person_count)
                self.assertIsNone(compiled.scene_contract.visible_hand_count)

    def test_baekje_empty_map_object_and_place_only_scenes_remain_nonhuman(self):
        cases = (
            (
                "map-like aerial landscape connecting northern Jolbon to the Mahan communities around the Han River basin",
                "landscape",
            ),
            ("an empty place where Biryu's death is recorded without method or witnesses", "scene"),
            (
                "two conflicting genealogy scrolls place Jumong and Utae in different positions above Biryu and Onjo",
                "object",
            ),
            (
                "ancient manuscripts fade into an archaeological view of Pungnap earthen fortress in modern Seoul",
                "landscape",
            ),
            ("massive rammed-earth walls of Pungnap fortress rise above the river plain", "landscape"),
            ("multiple occupation layers reveal a settlement growing over a long period", "scene"),
            ("a legendary blue dragon reflection appears in a Wirye well", "scene"),
            (
                "the fall of Ugokseong transitions into conflicting origin scrolls and a night sea route",
                "landscape",
            ),
            ("Jolbon, Wirye, and Michuhol connect through river and coastal roads", "landscape"),
            ("Jolbon grows along the river plain while Pungnap fortress rises in the distance", "landscape"),
        )
        style = ". Ancient Korean historical drama, realistic people, cinematic realism, no modern objects."

        for scene, expected_kind in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(scene + style)
                self.assertEqual(compiled.scene_kind, expected_kind)

    def test_repeated_episode_place_scope_does_not_override_scene_location(self):
        scope = (
            "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, and Ugok Fortress"
        )
        compiled = self.compile(
            "Global visual world: Time range: Late 1st century BC; "
            f"Place scope: {scope}; Culture scope: Goguryeo, Mahan, and Baekje; "
            "Year/period: Late 1st century BC; "
            f"Exact place: {scope}; "
            "Scene: Biryu indicates Michuhol on the coastal horizon as the retainers object."
        )

        self.assertNotIn("Exact place:", compiled.positive)
        self.assertIn("Michuhol on the coastal horizon", compiled.positive)

    def test_single_exact_place_and_pungnap_modern_override_remain_locked(self):
        scope = (
            "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, and Ugok Fortress"
        )
        cases = (
            ("Wirye", "Onjo receives settlers inside Wirye", "Exact place: Wirye"),
            (
                "Pungnap Toseong archaeological site, present-day Seoul, South Korea",
                "archaeologists uncover layered dwellings inside Pungnap fortress",
                "Exact place: Pungnap Toseong archaeological site, present-day Seoul, South Korea",
            ),
        )

        for exact_place, scene, expected in cases:
            with self.subTest(exact_place=exact_place):
                compiled = self.compile(
                    "Global visual world: Time range: source period; "
                    f"Place scope: {scope}; Year/period: source period; Exact place: {exact_place}; "
                    f"Scene: {scene}."
                )
                self.assertIn(expected, compiled.positive)

    def test_general_pair_prompt_preserves_one_hand_per_actor_and_unused_hand_occlusion(self):
        scenes = (
            (
                "Waist-up view; one guard stands at left with exactly one visible right hand "
                "gripping the left end of one timber beam; one envoy stands at right with exactly "
                "one visible left hand gripping the right end of the same beam; all other hands "
                "remain completely outside the frame behind their owners torsos"
            ),
            (
                "Waist-up view; one guard stands at left and one envoy stands at right; exactly two "
                "visible hands total grip opposite beam ends with one hand from each adult; both far "
                "arms remain fully hidden behind their own torsos outside the frame"
            ),
        )
        for model in (
            "comfyui-flux2-klein-4b",
            "comfyui-dreamshaper-xl-longtube",
        ):
            for scene in scenes:
                with self.subTest(model=model, scene=scene):
                    compiled = self.compile(
                        "Main subject: exactly two adult gate guards; Scene: " + scene,
                        model,
                    )

                    self.assertEqual(compiled.scene_contract.visible_hand_count, 2)
                    self.assertEqual(
                        [actor.visible_hand_count for actor in compiled.scene_contract.actors],
                        [1, 1],
                    )
                    self.assertIn("hand ownership: left actor has one visible hand", compiled.positive)
                    self.assertIn("right actor has one visible hand", compiled.positive)
                    self.assertIn("unused hands:", compiled.positive)
                    self.assertRegex(
                        compiled.positive,
                        r"unused hands: [^.]*outside the frame",
                    )
                    self.assertLessEqual(len(compiled.positive), 950)

    def test_recompiling_a_contract_keeps_primary_subject_and_named_roles(self):
        source = (
            "Year/period: 666 AD; Exact place: Chang'an Tang audience hall; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            "Primary subject: exactly two adults: kneeling Namsaeng; Emperor Gaozong; "
            "Visible action: Emperor Gaozong sits on a low timber dais while Namsaeng kneels at left; "
            "Material culture: black Tang futou, dark round-collar robe, wrap-front Goguryeo robe."
        )
        first = self.compile(source)
        second = self.compile(first.positive)
        for value in ("kneeling Namsaeng", "Emperor Gaozong", "black Tang futou"):
            self.assertIn(value, second.positive)
        self.assertEqual(second.person_count, 2)
        self.assertLessEqual(len(second.positive), 950)

    def test_nested_scene_metadata_does_not_replace_action_or_second_deity(self):
        source = (
            "Year/period: Japanese mythic creation era; "
            "Exact place: plain unpainted timber food hall on Takamagahara; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly two adult Japanese deities: adult male Tsukuyomi, East Asian face, "
            "long black hair tied low, small silver moon ornament, Japanese moon deity in an archaic white-blue "
            "wide-sleeve robe and adult female Uke Mochi, East Asian face, dark tied hair, Japanese food deity "
            "in an archaic earth-tone wide-sleeve robe; "
            "Scene: Scene evidence: queue EP06 topic/core-content alignment correction; "
            "Scene: Male Tsukuyomi approaches one timber food hall while female Uke Mochi waits in the doorway."
        )
        for model in ("comfyui-flux2-klein-4b", "comfyui-dreamshaper-xl-longtube-v15"):
            compiled = compile_image_prompt(
                source,
                model_id=model,
                quality_hint="Full-bleed edge-to-edge crop with material continuing beyond all four edges",
            )
            self.assertIn("Tsukuyomi", compiled.positive)
            self.assertIn("Uke Mochi", compiled.positive)
            self.assertIn("approaches one timber food hall", compiled.positive)
            self.assertIn("female Uke Mochi waits in the doorway", compiled.positive)
            self.assertNotIn("queue EP06", compiled.positive)
            self.assertEqual(compiled.person_count, 2)

    def test_z_image_japanese_myth_landscape_positive_path_forbids_invented_settlement(self):
        prompt = (
            "Visible action: Landscape-only strict top-down aerial view of one empty primordial "
            "river valley. Era/period: Japanese mythic creation era, Kojiki and Nihon Shoki. "
            "Exact place: primordial river valley. Culture scope: Japanese creation myth. "
            "Material culture: rough stone, unpainted timber only when "
            "named, woven cloth, water and aged bronze. Visible evidence: The visible action follows "
            "the narrated Japanese creation-myth moment and keeps named deities consistent."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("wild primordial island terrain", styled)
        self.assertIn("Continuous ground, wild vegetation, rock, water, and open sky", styled)
        self.assertNotIn("specifically named settlement evidence", styled)
        self.assertNotIn("settlement evidence", styled.lower())
        self.assertNotIn("houses", styled.lower())
        self.assertNotIn("roads", styled.lower())
        self.assertNotIn("signs", styled.lower())
        self.assertNotIn("writing", styled.lower())
        self.assertNotIn("timber", styled.lower())
        self.assertNotIn("cloth", styled.lower())
        self.assertNotIn("bronze", styled.lower())
        self.assertNotIn("named deities", styled.lower())
        self.assertNotIn("japanese", styled.lower())
        self.assertNotIn("historical", styled.lower())
        self.assertNotIn("Adult figure lock", styled)

    def test_z_image_japanese_myth_people_get_primordial_location_and_mature_anatomy_lock(self):
        prompt = (
            "Visible action: Hand-free chest-up two-shot of adult woman Uke Mochi and adult man "
            "Tsukuyomi beside one simple meal. Primary subject: exactly two adult Japanese deities. "
            "Historical setting: Kojiki and Nihon Shoki Japanese creation myth. Exact place: bare "
            "packed-earth court at an open-sided unpainted timber food shelter."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("exactly one isolated open-sided food shelter", styled)
        self.assertIn("mature natural East Asian facial proportions", styled)
        self.assertIn("every waist and belt area contains soft cloth only", styled)

    def test_z_image_japanese_myth_hall_pair_stays_inside_with_exactly_two_people(self):
        prompt = (
            "Visible action: medium-wide view with Amaterasu seated at center and one messenger "
            "kneeling at left. Primary subject: exactly two adult Japanese deities: adult female "
            "Amaterasu and adult male messenger. Era/period: Japanese mythic creation. "
            "Exact place: Amaterasu's audience chamber. Composition: exactly two adults."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("Archaic hall interior lock", styled)
        self.assertIn("no open sky", styled)
        self.assertIn("the total human count is two", styled)
        self.assertIn("no third person", styled)

    def test_z_image_japanese_myth_clay_bowl_reflection_becomes_safe_reaction_closeup(self):
        prompt = (
            "Visible action: close-up of the messenger's frightened face reflected in a dark clay "
            "bowl, sprouts rising below the frame. Primary subject: exactly one adult Japanese "
            "messenger deity. Era/period: Japanese mythic creation. Exact place: inside the heavenly hall."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("Messenger reaction close-up lock", styled)
        self.assertIn("strict head-and-shoulders close-up", styled)
        self.assertIn("face and head remain physically above", styled)
        self.assertIn("both arms, both hands and every finger stay outside", styled)
        self.assertNotIn("Adult figure lock", styled)

    def test_z_image_japanese_myth_hall_solo_gets_blank_background_and_zero_hand_crop(self):
        prompt = (
            "Visible action: medium-close view of Tsukuyomi alone studying one overturned clay "
            "vessel in tense doubt, exactly zero visible hands. Primary subject: exactly one adult "
            "female Amaterasu, mature East Asian face, long center-parted black hair. "
            "Era/period: Japanese mythic creation. Exact place: dim food hall."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertTrue(styled.startswith("CLOSED INTERIOR SOLO LOCK:"))
        self.assertIn("continuous blank reed-and-timber interior wall", styled)
        self.assertIn("No doorway, window, open side", styled)
        self.assertIn("SOLO IDENTITY LOCK", styled)
        self.assertIn("exactly one adult female Amaterasu", styled)
        self.assertIn("long center-parted black hair", styled)
        self.assertIn("ZERO-HAND CROP LOCK", styled)
        self.assertIn("no hand touches the face", styled)
        self.assertIn("single full-bleed enclosed-interior staging", styled)
        self.assertIn("no exterior opening or sky is visible", styled)
        self.assertNotIn("open full-bleed historical staging", styled)
        self.assertNotIn("local ground and sky texture", styled)
        negative = append_prompt_specific_negative_prompt("", styled)
        self.assertIn("visible hands", negative)
        self.assertIn("visible fingers", negative)
        self.assertIn("visible forearms", negative)

    def test_z_image_japanese_myth_object_only_hall_blocks_people_and_outdoor_drift(self):
        prompt = (
            "Visible action: Object-only close-up of two empty woven baskets beside grains and "
            "cocoons on reed mats, no people, no visible hands. Era/period: Japanese mythic "
            "creation. Exact place: heavenly hall floor with seed baskets."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertTrue(styled.startswith("ZERO-PERSON SCENE LOCK:"))
        self.assertIn("CLOSED OBJECT-INTERIOR LOCK", styled)
        self.assertIn("no doorway, open side, outdoor view, sky", styled)
        self.assertNotIn("Adult figure lock", styled)
        negative = append_prompt_specific_negative_prompt("", prompt)
        self.assertIn("living person", negative)
        self.assertIn("human face", negative)
        self.assertIn("background person", negative)

    def test_ch3_ep09_narration_locks_replace_symbolic_relic_scenes_with_story_actions(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: bare rocky boundary; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a glowing symbolic relic display; "
        )
        cases = (
            (
                "アマテラス は 髪 を 男 の ように 結び、 弓矢 で 完全 武装 しました。",
                "Amaterasu secures one quiver of reed arrows",
            ),
            (
                "天の安河 と 呼ばれる 神聖 な 川 を 挟んで、 二人 は 対峙 します。",
                "Small armed Amaterasu stands high on the far-left bank",
            ),
            (
                "こうして 二柱 の 神 は、 うけい と 呼ばれる 儀式 を 行う こと に なります。",
                "One plain bronze blade and one short magatama cord pass directly",
            ),
            (
                "天の安河 を 挟んで 向かい合った スサノオ は、 必死 に 弁明 します。",
                "Broad flowing river water reaches the bottom center edge",
            ),
            (
                "その 吐息 の 中 から 新しい 神様 が 生まれる という、 驚異 的 な 生命 創造。",
                "One complete newly formed adult deity stands clearly in the center foreground",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("Copy the registered full-frame ritual layout", compiled.positive)
                self.assertNotIn("artifact display", compiled.positive)
                self.assertIn("artifact display", compiled.negative)
                self.assertIn("configured_cast_direction=off", compiled.diagnostics)
                if "天の安河" in narration:
                    self.assertIn("looking straight down one broad river channel", compiled.positive)
                    self.assertIn("both people on same riverbank", compiled.negative)

    def test_ch3_ep09_second_batch_locks_replace_scales_weapons_and_torii_with_story_actions(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: bare rocky boundary; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a balanced golden scale beside swords and a torii gate; "
        )
        cases = (
            (
                "男 の 神 と 女 の 神、 どちら が 清らか さ の 証拠 なの か。",
                "one newly formed adult man and one newly formed adult woman",
            ),
            (
                "彼女 は 弟 の スサノオ が 持って いた、 十拳剣 を 要求 します。",
                "Amaterasu extends one empty receiving hand",
            ),
            (
                "なんと 硬い 鉄 の 剣 を、 素手 で ボキボキ と 三段 に 折って しまった の です。",
                "bronze dust and orange sparks burst between them",
            ),
            (
                "折った 剣 の 破片 を、 天の真名井 という 神聖 な 井戸 の 水 で 洗い 清め ます。",
                "washes exactly three dull-brown bronze fragments underwater",
            ),
            (
                "彼女 は その 頑丈 な 鉄 の 剣 を、 素手 で 三つ に へし折り ました。",
                "dense bronze dust cloud bursts between them",
            ),
            (
                "そして その 破片 を 口 の 中 に 放り込む と、 ガリガリ と 噛み砕き ました。",
                "bronze chip is visibly caught between Amaterasu's front teeth",
            ),
            (
                "鉄 を 食べる 女神 という、 非常に シュール で 迫力 の ある 描写 です。",
                "bronze chip is visibly caught between Amaterasu's front teeth",
            ),
            (
                "ガリガリ と 鉄 を 食べる 太陽 神 の 姿 は、 恐ろしく も 神秘 的 です。",
                "bronze chip is visibly caught between Amaterasu's front teeth",
            ),
            (
                "すると その 白い 霧 の 中 から、 三柱 の 美しい 女神 が 誕生 した の です。",
                "three separate adult women goddesses",
            ),
            (
                "福岡県 の 宗像 大社 に 祀られて いる、 非常に 有名 な 神様 です ね。",
                "three distant adult worshippers bow",
            ),
            (
                "彼 は 姉 の アマテラス が 身 に つけて いた、 勾玉 を 要求 しました。",
                "single short green-stone magatama cord",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("balanced golden scale", compiled.positive)
                self.assertNotIn("torii gate", compiled.positive.lower())
                self.assertIn("artifact display", compiled.negative)
                self.assertIn("configured_cast_direction=off", compiled.diagnostics)
                if "口 の 中" in narration or "鉄 を 食べる" in narration:
                    self.assertIn("Composition: extreme facial close-up", compiled.positive)
                    self.assertIn("plastic bottle", compiled.negative)

    def test_ch3_ep09_third_batch_locks_replace_mirror_seal_scale_and_relic_displays(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: bare rocky boundary; "
            "Main subject: exactly one adult deity; "
            "Scene: a silver mirror, golden scale, seal stamp, scroll, lotus, and glowing swords; "
        )
        cases = (
            (
                "アマテラス は 首 から 勾玉 を 外し、 弟 へ と 渡し ました。",
                "places that same cord into Susanoo's two open attached hands",
            ),
            (
                "スサノオ も 姉 と 同じ ように、 勾玉 を 井戸 の 水 で 洗い 清め ます。",
                "washes one short cord of five curved green magatama stones",
            ),
            (
                "美しい 宝石 から は、 力強い 男性 の 神様 たち が 誕生 した の です。",
                "Five bearded adult men only stand chest-up",
            ),
            (
                "その 息吹 の 中 から 姿 を 現した の は、 五柱 の 男神 でした。",
                "Five bearded adult men only stand chest-up",
            ),
            (
                "さて、 互い の 物 から 新たな 命 を 生み出した 二柱 の 神。",
                "Amaterasu and Susanoo face each other across the river",
            ),
            (
                "これ は 私 の 心 に 悪い 企み が なく、 清らか だから こそ です。",
                "Susanoo presses one attached open hand to his own chest",
            ),
            (
                "生まれた 子供 たち の 所有 権 について の 宣言 です。",
                "Amaterasu stands alone and speaks firmly",
            ),
            (
                "五柱 の 男神 は 私 の 勾玉 から 生まれた の だから、 私 の 子 である。",
                "Five bearded adult men only stand chest-up",
            ),
            (
                "三 女神 は お前 の 剣 から 生まれた の だから、 お前 の 子 である と。",
                "Three adult women only stand chest-up",
            ),
            (
                "アマテラス の 口 から は 三柱 の 女神、 スサノオ の 口 から は 五柱 の 男神。",
                "separated by one broad empty river",
            ),
            (
                "神聖 な 誓約 の 儀式 の 結果 が 出揃い、 ついに 判決 が 下され ます。",
                "face one another across the river",
            ),
            (
                "彼 が 吐き出した 息吹 の 中 から、 五柱 の 力強い 男神 が 誕生 します。",
                "Five bearded adult men only stand chest-up",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("silver mirror", compiled.positive.lower())
                self.assertNotIn("golden scale", compiled.positive.lower())
                self.assertNotIn("seal stamp", compiled.positive.lower())
                self.assertIn("artifact display", compiled.negative)
                self.assertIn("configured_cast_direction=off", compiled.diagnostics)

    def test_ch3_ep09_fourth_batch_locks_replace_symbols_with_verdict_and_rampage_actions(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: bare rocky boundary; "
            "Main subject: exactly one adult deity; "
            "Scene: a giant sun icon, two hourglasses, a cracked mirror, tiled palace, "
            "theatrical curtain, scroll, crown, and artifact display; "
        )
        cases = (
            (
                "私 の 心 が 清らか で 邪心 が ない から こそ、 たおやかな 神 が 生まれた。",
                "exactly three separate adult women goddesses",
            ),
            (
                "恐ろしい 姉弟 喧嘩 は 回避 され、 スサノオ の 疑い は 晴れた の です。",
                "Amaterasu lowers her single wooden bow completely",
            ),
            (
                "アマテラス は 弟 の 意見 を 受け入れ、 彼 の 潔白 を 認め ました。",
                "One wooden bow lies flat on bare ground",
            ),
            (
                "男神 は 私 の 物 から 生まれた から 私 の 子、 女神 は お前 の 子。",
                "single fully grown man beside her",
            ),
            (
                "ここ で 生まれた 男神 の 一 人 が、 後 に 皇室 の 祖先 と なります。",
                "Ame no Oshihomimi takes one full step forward",
            ),
            (
                "神話 の 血統 を 太陽 の 女神 に 結びつける、 重要 な エピソード です。",
                "rests one attached open hand on her adult son",
            ),
            (
                "儀式 は 平和 に 終わった か に 見え ました が、 悲劇 は 終わって いません。",
                "restrained triumphant smile",
            ),
            (
                "勝利 した 弟 の 勘違い が、 天上 界 に さらなる 悪夢 を もたらす の です。",
                "one careless foot crushing a planted ridge",
            ),
            (
                "疑い が 晴れた こと で、 スサノオ は 天上 界 に 滞在 すること を 許され ます。",
                "walks deeper into the cultivated highland",
            ),
            (
                "ここ で 素直 に 挨拶 して 帰れ ば、 何事 も なく 終わった の です が。",
                "looks over his shoulder at mizura-haired Amaterasu",
            ),
            (
                "姉 の 言う こと なんて 聞く 必要 は ない と、 完全に 調子 に 乗って しまい ました。",
                "Susanoo turns his back on her",
            ),
            (
                "彼 は 天上 界 の 田んぼ の 畦 を 壊し、 水路 を 埋めて しまい ます。",
                "shove wet earth into the adjacent irrigation channel",
            ),
            (
                "さらに 神聖 な 神殿 に 大便 を まき散らす という、 とんでもない 悪戯 を します。",
                "smears dark foul human waste across the clean plank floor",
            ),
            (
                "農業 の 豊か さ と 清潔 さ を 重んじる 神々 に とって は、 許しがたい 行為 です。",
                "cover their noses and recoil in visible anger",
            ),
            (
                "しかし アマテラス は、 初め は 弟 の 蛮行 を 必死 に 庇って いました。",
                "both attached open hands raised toward one angry deity",
            ),
            (
                "優しい 姉 として、 なんとか 穏便 に 済ませよう と 我慢 を 重ねた の です。",
                "holding both attached open hands outward",
            ),
            (
                "しかし その 姉 の 優しさ が、 弟 の 暴走 を さらに エスカレート させ ます。",
                "Susanoo tears apart one field boundary",
            ),
            (
                "誰も 自分 を 罰しない こと を いい こと に、 悪戯 は 凶悪 な 犯罪 へ と 変わります。",
                "climbs onto the low thatched roof",
            ),
            (
                "そして ついに、 アマテラス の 心 を 完全に へし折る 凄惨 な 事件 が 起き ます。",
                "Amaterasu crouches alone beside one overturned loom",
            ),
            (
                "屋根 に 穴 を 開け、 皮 を 剥いだ 馬 の 死骸 を 投げ込んだ の です。",
                "single red skinless dead horse carcass lies motionless",
            ),
            (
                "その 恐ろしい 衝撃 と 恐怖 で、 機織り の 侍女 が 命 を 落として しまい ました。",
                "One adult weaving attendant lies motionless",
            ),
            (
                "ただ の 悪戯 が、 ついに 神聖 な 空間 で の 殺人 事件 に 発展 した の です。",
                "One adult attendant lies flat on her back with closed eyes",
            ),
            (
                "そして 世界 を 永遠 の 暗闇 に 閉ざす、 最悪 の 選択 を する こと に なります。",
                "Amaterasu steps into one dark natural cave",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("giant sun icon", compiled.positive.lower())
                self.assertNotIn("hourglass", compiled.positive.lower())
                self.assertNotIn("cracked mirror", compiled.positive.lower())
                self.assertNotIn("tiled palace", compiled.positive.lower())
                self.assertNotIn("theatrical curtain", compiled.positive.lower())
                self.assertIn("artifact display", compiled.negative)
                self.assertIn("configured_cast_direction=off", compiled.diagnostics)
        punctuation_stripped = self.compile(
            prefix.replace(
                "Main subject: exactly one adult deity;",
                "Main subject: exactly one adult female Amaterasu;",
            )
            + "Narration context: 恐ろしい 姉弟 喧嘩 は 回避 され、 スサノオ の 疑い は 晴れた の です",
            "comfyui-z-image-turbo",
        )
        self.assertIn("completed archaic mizura hairstyle", punctuation_stripped.positive)

    def test_ch3_ep09_fifth_batch_locks_replace_icons_and_relics_with_cave_and_darkness_actions(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: bare rocky boundary; "
            "Main subject: exactly one adult deity; "
            "Scene: a giant question mark, sun disk, cracked mirror, silver statue, theatrical "
            "curtain, tiled palace, scroll, and artifact display; "
        )
        cases = (
            (
                "天上 界 の 美しい 田んぼ を 破壊 し、 神殿 に 便 を まき散らし ました。",
                "drives one bare foot through a rice-field ridge",
            ),
            (
                "アマテラス は 最初、 弟 に 悪気 は ない の だ と 必死 に 庇って いました。",
                "both attached open hands raised toward one angry deity",
            ),
            (
                "しかし その 姉 の 寛容 さ が、 取り返し の つかない 悲劇 を 招き ます。",
                "raises both attached open hands",
            ),
            (
                "神々 が 衣服 を 織る 神聖 な 建物 に、 スサノオ は 乱入 しました。",
                "forcefully steps through the open side",
            ),
            (
                "そして 生皮 を 剥いだ 血だらけ の 馬 の 死骸 を、 投げ込んだ の です。",
                "single red skinless dead horse carcass lies motionless",
            ),
            (
                "子供 じみた 悪戯 が、 神聖 な 場所 で の 殺人 事件 に なった 瞬間 です。",
                "One adult attendant lies motionless beside a broken loom",
            ),
            (
                "彼女 の 心 は 完全に 壊れ、 弟 を 庇う 気力 も 全て 失い ました。",
                "Amaterasu collapses onto both knees",
            ),
            (
                "激しい 絶望 に 襲われた 女神 は、 天の岩戸 と 呼ばれる 洞窟 に 引きこもり ます。",
                "Amaterasu walks alone into one dark natural rock cave",
            ),
            (
                "太陽 の 神 が 隠れた こと で、 世界 は 永遠 の 暗闇 に 包まれ ました。",
                "black cloud and deep shadow cover the entire rocky land",
            ),
            (
                "ついに 日本 神話 における、 最大 の 宇宙 的 パニック が 幕 を 開ける の です。",
                "Five adult deities stand separately in near darkness",
            ),
            (
                "武器 と 装飾 品 を 噛み砕いて 命 を 産む という、 奇妙 で 呪術 的 な 裁判。",
                "Amaterasu visibly bites one tiny bronze chip",
            ),
            (
                "太陽 神 が 鉄 の 剣 を ガリガリ 食べる 描写 は、 非常 に 衝撃 的 でした ね。",
                "tiny flat bronze crumb smaller than one front tooth",
            ),
            (
                "許された こと で 傲慢 に なり、 破滅 へ と 突き進む 愚か さ。",
                "strides with raised chin across a visibly ruined rice field",
            ),
            (
                "皆さん は この 命がけ の 神聖 な 裁判 について、 どう 感じ ました か。",
                "Four creators discuss the myth around one plain empty desk",
            ),
            (
                "面白い と 感じて 頂け たら、 チャンネル 登録 と 高評価 を お願い します。",
                "Four creators face the viewer while one creator raises one attached open hand",
            ),
            (
                "皆さん の 応援 が、 いつも 私 たち の 大きな 励み に なって います。",
                "Four creators smile warmly toward the viewer around one plain empty desk",
            ),
            (
                "さて、 弟 の 凄惨 な 悪行 に 心 を 閉ざして しまった 太陽 の 女神 アマテラス。",
                "Amaterasu kneels alone beside the broken weaving hall",
            ),
            (
                "彼女 が 天の岩戸 と 呼ばれる 洞窟 に 隠れ、 扉 を 閉ざして しまい ます。",
                "Amaterasu pulls one rough stone slab across the entrance",
            ),
            (
                "光 を 失った 世界 で は 悪霊 が 騒ぎ 出し、 宇宙 は 滅亡 の 危機 に 陥り ます。",
                "Three complete smoke-dark humanoid spirits climb separately",
            ),
            (
                "残された 天上 界 の 神々 は、 太陽 を 取り戻す ため に 奇想天外 な 作戦 を 立て ます。",
                "Five adult deities huddle in one tight circle",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("giant question mark", compiled.positive.lower())
                self.assertNotIn("cracked mirror", compiled.positive.lower())
                self.assertNotIn("silver statue", compiled.positive.lower())
                self.assertNotIn("theatrical curtain", compiled.positive.lower())
                self.assertNotIn("tiled palace", compiled.positive.lower())
                self.assertIn("configured_cast_direction=off", compiled.diagnostics)
                if "皆さん" in narration or "チーム 一同" in narration:
                    self.assertNotIn("tablet", compiled.positive.lower())
                    self.assertIn("tablet", compiled.negative.lower())
        creator_style = _apply_longtube_dark_manhwa_style(
            "Primary subject: exactly four present-day adult Japanese creators, exactly two women and exactly two men",
            model_id="comfyui-z-image-turbo",
        )
        self.assertIn("exactly zero hands appear", creator_style)
        self.assertIn("No tablet, monitor, screen", creator_style)
        self.assertNotIn("central modern tablet", creator_style)

    def test_z_image_japanese_myth_face_only_scene_does_not_seed_robe_or_sash(self):
        prompt = (
            "Visible action: Extreme inward-facing two-profile confrontation: adult woman Amaterasu "
            "at left and adult man Susanoo at right; both jawlines meet the lower edge. "
            "Primary subject: exactly two adult Japanese deity faces. Historical setting: Kojiki and "
            "Nihon Shoki Japanese creation myth. Exact place: open Takamagahara ridge."
        )

        styled = _apply_longtube_dark_manhwa_style(
            prompt,
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("Adult face lock", styled)
        self.assertIn("jawlines meet the lower edge", styled)
        self.assertNotIn("Adult figure lock", styled)
        self.assertNotIn("wrap robes", styled)
        self.assertNotIn("cloth sash", styled)

    def test_tang_two_generation_cup_pair_keeps_clothing_and_action(self):
        compiled = self.compile(
            "Year/period: late 7th century; Exact place: Chang'an Tang residence; "
            "Culture scope: 7th-c. Tang; "
            "Main subject: exactly two hardened adult Tang-clad descendants: one elderly man; one middle-aged man; "
            "Scene: Exactly two cups total: each Tang man raises one shallow bronze cup while wearing low black futou "
            "and dark paofu with smooth closed circular necklines."
        )

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("exactly two hardened tang men", compiled.positive.lower())
        self.assertIn("closed circular necklines", compiled.positive)
        self.assertIn("Exactly two cups total", compiled.positive)
        self.assertIn("single continuous three-quarter group view", compiled.positive)
        self.assertIn("vertical center divider", compiled.negative)
        self.assertIn("third cup", compiled.negative)
        self.assertNotIn("second cup", compiled.negative)
        self.assertIn("composition=tang_two_generation_cup_pair", compiled.diagnostics)

    def test_tang_two_generation_single_cup_scene_blocks_duplicates_and_books(self):
        compiled = self.compile(
            "Year/period: late 7th century; Exact place: Chang'an Tang residence; "
            "Culture scope: 7th-c. Tang; Main subject: exactly two hardened Tang adult men; "
            "Scene: Exactly one shallow footless bronze cup rests untouched at table center while exactly two Tang men "
            "fold their hands beside three dyed silk bolts."
        )

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("exactly one shallow footless bronze cup rests untouched", compiled.positive.lower())
        for term in (
            "second cup",
            "open book",
            "bound codex",
            "modern table lamp",
            "bare feet",
            "tatami mat",
            "vertical center divider",
        ):
            self.assertIn(term, compiled.negative)
        self.assertIn("composition=tang_two_generation_single_cup_pair", compiled.diagnostics)

    def test_guard_standing_alone_remains_a_single_person_scene(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Pyongyang Fortress corridor; "
            "Main subject: exactly one adult Goguryeo traitor guard; "
            "Scene: One Goguryeo traitor guard stands alone in a timber corridor and hides one dagger behind his back."
        )

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("dagger remains visible behind the right hip", compiled.positive)
        self.assertIn("foreground sword", compiled.negative)
        self.assertIn("composition=single_hidden_dagger", compiled.diagnostics)

    def test_shrouded_stretcher_scene_locks_one_survivor_and_one_stretcher(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Liaodong battlefield aftermath; "
            "Main subject: exactly one visible adult survivor beside one fully covered stretcher; "
            "Scene: Exactly one timber stretcher at left is covered by one hemp shroud while one adult survivor in "
            "wrapped shoes kneels at right."
        )

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("two side poles and cross slats", compiled.positive)
        self.assertIn("second stretcher", compiled.negative)
        self.assertIn("coffin", compiled.negative)
        self.assertIn("composition=single_survivor_shrouded_stretcher", compiled.diagnostics)

    def test_collapsed_beam_pair_locks_grim_rescue_composition(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Goguryeo settlement; "
            "Main subject: exactly two adult villagers lifting one collapsed granary beam; "
            "Scene: Exactly two villagers lift opposite ends of one fallen granary beam before one crushed home."
        )

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("clenched grim faces", compiled.positive)
        self.assertIn("smile", compiled.negative)
        self.assertIn("intact home", compiled.negative)
        self.assertIn("masonry wall", compiled.negative)
        self.assertIn("composition=pair_collapsed_beam_rescue", compiled.diagnostics)

    def test_hidden_dagger_sash_scene_is_object_only_and_blocks_full_swords(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Pyongyang Fortress corridor; "
            "Main subject: one hidden dagger beneath one guard sash; "
            "Scene: Object-only close view of one dagger half concealed beneath one guard sash beside one gate-key block."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("continuous rough floorboard grain in all four corners", compiled.positive)
        self.assertIn("full-size sword", compiled.negative)
        self.assertIn("cruciform guard", compiled.negative)
        self.assertIn("blade inscription", compiled.negative)
        self.assertIn("black corner vignette", compiled.negative)
        self.assertIn("composition=object_hidden_dagger_sash_overhead", compiled.diagnostics)

    def test_ep29_civil_war_scene_locks_three_brothers_in_one_courtyard(self):
        compiled = self.compile(
            "Year/period: 665 AD; Exact place: Pyongyang Fortress court courtyard; "
            "Culture scope: 7th-c. Goguryeo; Main subject: exactly three adult Goguryeo brothers; "
            "Scene: Exactly three adult Goguryeo brothers occupy separate left, center and right slots in one smoky "
            "packed-earth courtyard; left clenches empty fists, center shows open empty palms and right lifts one seal."
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 3)
        self.assertIn("one smoky courtyard, one viewpoint", compiled.positive)
        self.assertIn("sword", compiled.negative)
        self.assertIn("weapon", compiled.negative)
        self.assertIn("handheld object", compiled.negative)
        self.assertIn("barefoot", compiled.negative)
        self.assertIn("composition=three_brother_civil_war", compiled.diagnostics)

    def test_ep29_registry_handover_uses_one_continuous_pair_scene(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: windowless Tang registry chamber at Chang'an; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            "Main subject: exactly two adults: Goguryeo-robed Namsaeng; Tang registrar; "
            "Scene: In one continuous timber chamber, one Tang registrar presses exactly one blank-backed square bronze "
            "registry seal into kneeling Namsaeng's open palms."
        )

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("one continuous medium three-quarter two-shot", compiled.positive)
        self.assertIn("vertical center divider", compiled.negative)
        self.assertIn("duplicate Namsaeng", compiled.negative)
        self.assertIn("elderly Namsaeng", compiled.negative)
        self.assertIn("missing futou", compiled.negative)
        self.assertIn("lattice window", compiled.negative)
        self.assertIn("oversized seal", compiled.negative)
        self.assertIn("composition=namsaeng_tang_registry_pair", compiled.diagnostics)
        self.assertTrue(_should_check_internal_text_after_generation(compiled.positive))

    def test_ep29_secret_handover_uses_six_stone_textless_object_layout(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: windowless Liaodong Tang campaign room; "
            "Culture scope: 7th-c. Goguryeo and Tang; "
            "Main subject: one textless Goguryeo defense-route handover layout; "
            "Scene: Object-only straight-down view of exactly six smooth grey river-stone fortress markers linked by one "
            "red route cord running from one flat grey sash to one flat black sash."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("exactly six smooth grey river-stone fortress markers", compiled.positive)
        self.assertIn("exactly six grey stones form top three and bottom three", compiled.positive)
        self.assertTrue(_should_check_six_stone_marker_count(compiled.positive))
        self.assertEqual(_expected_grey_stone_marker_count(compiled.positive), 6)
        for term in (
            "stone in center gap",
            "fourth stone in either row",
            "five stones total",
            "seventh stone marker",
            "miniature fortress building",
            "cloth packet",
            "white background",
            "written characters",
            "person",
        ):
            self.assertIn(term, compiled.negative)
        self.assertIn("composition=six_stone_secret_transfer", compiled.diagnostics)
        self.assertTrue(_should_check_internal_text_after_generation(compiled.positive))

    def test_ep29_spy_route_enables_three_stone_count_guard(self):
        normalized = normalize_cut_image_prompt(
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Yeon Namsaeng and Goguryeo succession crisis; "
            "Main subject: symbolic history scene; Scene: abstract metaphor",
            "고구려의 약점을 가장 잘 아는 자가 치명적인 스파이가 된 겁니다.",
        )
        compiled = self.compile(normalized)

        self.assertEqual(_expected_grey_stone_marker_count(normalized), 3)
        self.assertEqual(_expected_grey_stone_marker_count(compiled.positive), 3)
        self.assertFalse(_should_check_six_stone_marker_count(compiled.positive))

    def test_ep29_failed_scene_repairs_keep_counts_props_and_prompt_budgets(self):
        source = (
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Yeon Namsaeng and Goguryeo succession crisis, stale silk bundles, lacquer table, snapped spears; "
            "Main subject: symbolic history scene; Scene: abstract metaphor"
        )
        cases = (
            (
                "오늘은 조국을 팔아넘긴 매국노, 남생 가문을 파헤칩니다.",
                "object",
                None,
                "composition=bloody_handprint_textless_terrain_relief",
                ("one flat blood-smeared five-finger handprint", "unmistakable raised mountain ridges", "one winding recessed river channel", "exactly five flat finger smears"),
                ("Tang commander", "fortress tally"),
            ),
            (
                "아버지가 평생을 바쳐 지킨 나라를 적국에 헌납한 자들.",
                "object",
                None,
                "composition=split_goguryeo_shield_two_overlapping_halves",
                ("one scarred Goguryeo layered-timber shield", "exactly two jagged halves", "overlap slightly at the break", "freezing wet mud"),
                ("Tang commander", "fortress tally"),
            ),
            (
                "적국인 당나라에 투항하여 자기 목숨을 구걸하기로 한 거죠.",
                "pair",
                2,
                "composition=namsaeng_empty_hands_surrender_pair",
                ("both empty open palms", "smooth-front dark round-neck paofu"),
                ("closed packet", "fortress tally"),
            ),
            (
                "조국을 짓밟으려던 늑대에게 스스로 성문을 열어준 셈입니다.",
                "single",
                1,
                "composition=single_traitor_removes_gate_bar",
                ("exactly one back-facing adult Goguryeo traitor guard", "sole thick horizontal locking beam at waist height", "both complete hands stay far apart", "vertical gate planks"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "그는 16살 난 둘째 아들 헌성을 당나라 장안으로 보냅니다.",
                "single",
                1,
                "composition=single_heonseong_changan_departure",
                ("exactly one male: slender sixteen-year-old Heonseong", "one small square cloth parcel", "looks backward in fear"),
                ("Tang escort", "second person"),
            ),
            (
                "인질을 바치며 당나라 황제에게 살려달라고 납작 엎드린 겁니다.",
                "single",
                1,
                "composition=single_heonseong_hostage_prostration",
                ("exactly one teenage boy Heonseong fully prostrate", "straight-down extreme close crop", "crown of black hair", "exactly two complete open hands"),
                ("Tang envoy", "second person"),
            ),
            (
                '"당나라 대군이 오면 고구려 정벌의 선봉에 서겠습니다."',
                "single",
                1,
                "composition=single_weaponless_namsaeng_points_east",
                ("exactly one weaponless adult Tang-armored Namsaeng", "one straight right index finger", "empty left fist", "low earthen ramparts"),
                ("Tang commander", "point-down"),
            ),
            (
                "666년, 남생은 자신이 지배하던 6개 성을 통째로 넘깁니다.",
                "object",
                None,
                "composition=six_stone_secret_transfer",
                ("exactly six smooth grey", "top three and bottom three"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "고구려의 약점을 가장 잘 아는 자가 치명적인 스파이가 된 겁니다.",
                "object",
                None,
                "composition=secret_route_cord_connects_goguryeo_to_tang",
                ("one secret red route cord joining one grey Goguryeo sash", "one narrow soft wrinkled grey woven sash strip", "narrow wrinkled black cloth right", "exactly three separate grey oval stones", "one red cord crosses all three centers", "dark floorboards fill all edges"),
                ("Gaozong", "Namsaeng"),
            ),
            (
                "황제는 반역자 남생에게 우위대장군이라는 높은 벼슬을 내립니다.",
                "object",
                None,
                "composition=blank_rank_seal_pressed_into_granted_earth",
                ("exactly one blank-backed gilt-bronze Tang rank seal", "half-buried in dark earth", "exactly one plain shallow land-grant tray"),
                ("adult Namsaeng", "seal face visible"),
            ),
            (
                "당 고종은 이 믿기 힘든 핏빛 배신에 극도로 기뻐했습니다.",
                "single",
                1,
                "composition=single_gaozong_triumphant_reaction",
                ("exactly one adult male Emperor Gaozong", "cold triumphant smile", "one raised open empty hand"),
                ("Namsaeng", "fortress tally"),
            ),
            (
                "고구려 대막리지가 적국 장수로 돌변하는 비참한 현실이죠.",
                "single",
                1,
                "composition=single_namsaeng_changes_to_tang_commander",
                ("exactly one adult male Namsaeng", "one plain grey Goguryeo rank sash", "one shoulder fastening"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "조국도, 가문의 이름도 권력 앞에서는 미련 없이 내던졌죠.",
                "object",
                None,
                "composition=severed_clan_sash_two_halves",
                ("one severed grey woven Goguryeo clan sash", "continuous dark brown floorboard grain filling all edges", "exactly two total objects", "left half and right half only"),
                ("command cloak", "Tang attendant"),
            ),
            (
                "살아남기 위해 악마의 발밑을 기는 징그러운 생존 본능입니다.",
                "animal",
                None,
                "composition=single_rat_beneath_boot_shadow",
                ("exactly one realistic brown rat", "four paws", "one long unbroken tail", "boot-shaped shadow"),
                ("Tang envoy", "fortress tally"),
            ),
            (
                "남쪽의 오랜 적인 신라로 몽땅 넘어가 투항해버린 겁니다.",
                "pair",
                2,
                "composition=jeongto_silla_surrender",
                ("one large plain ochre triangular", "one Silla guard in a low black segmented iron helmet", "low hide tents", "timber palisade"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "일인 독재의 축이 무너지자 제국 전체가 모래성처럼 붕괴합니다.",
                "landscape",
                None,
                "composition=rammed_earth_fortress_collapses_to_sand",
                ("one full-scale smooth unmarked Goguryeo rammed-earth defensive embankment", "roofless low sloped earthen embankment", "broad smooth unmarked ochre slope"),
                ("plank gate collapsing", "locking beam"),
            ),
            (
                "113만 대군도 못 뚫은 철벽이 권력욕이라는 독약에 녹아내렸죠.",
                "object",
                None,
                "composition=granite_fortress_wall_corroded_by_poison",
                ("irregular rough granite fieldstones", "broad low horizontal cavity", "at least twice as wide as tall", "sagging liquid-rock edges"),
                ("silk bundles", "lacquer table"),
            ),
            (
                "연개소문의 권력 세습은 고구려에 가장 치명적인 자살골이었습니다.",
                "object",
                None,
                "composition=succession_plaque_half_submerged_in_poison",
                ("one blank square bronze succession plaque half-submerged in black poison", "one thin flat blank bronze square fills the center", "lower half disappears beneath one viscous black poison pool", "smooth unbroken ochre clay surface fills every edge"),
                ("two adult Goguryeo brothers", "royal diadem"),
            ),
            (
                "배신자 남생은 조국의 산천을 짓밟으며 맹렬하게 진격했습니다.",
                "single",
                1,
                "composition=namsaeng_reined_gallop",
                ("both fists on paired reins", "one complete horse and rider", "broken clay pots", "burning timber-and-thatch homes"),
                ("Tang attendant", "stale silk bundles"),
            ),
            (
                "고구려 백성들은 어제까지 모시던 지도자의 배신에 피눈물을 흘렸죠.",
                "group",
                3,
                "composition=three_villagers_blood_tears",
                ("exactly three distinct villagers", "reddened eyes", "clear wet tears", "empty smoky sky"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "1차 방어선 신성마저 내부 반역으로 어이없이 성문이 열리고 맙니다.",
                "object",
                None,
                "composition=open_gate_chain_ground_evidence",
                ("exactly one short heavy chain segment forms one shallow diagonal line", "two free end links remain visible and far apart", "chain stays uncoiled", "smooth clay fills every edge"),
                ("stale silk bundles", "snapped spears"),
            ),
            (
                "공포로 억눌렸던 불만들이 조국을 팔아먹는 괴물로 돌변한 겁니다.",
                "object",
                None,
                "composition=cracked_statue_releases_betrayal_shadow",
                ("one cracked stone kneeling statue", "one chest-to-base fissure", "one flat black ground shadow"),
                ("two distinct Goguryeo guards", "fortress key"),
            ),
            (
                "피 묻은 왕좌를 차지하려다 국가 전체를 핏물에 던져버린 셈입니다.",
                "object",
                None,
                "composition=goguryeo_throne_sinks_in_blood",
                ("one unmistakable upright ceremonial timber throne", "one tall plain back", "two armrests", "lower half is submerged"),
                ("rank tablet", "overturned backless"),
            ),
            (
                "내부의 약점은 가장 처참하게 공격당했습니다.",
                "object",
                None,
                "composition=one_shield_one_spearhead",
                ("exactly one large detached triangular iron spearhead blade", "one convex oval layered-plank timber shield"),
                ("snapped spears", "stale silk bundles"),
            ),
            (
                "형제들의 권력 다툼은 고구려 700년 사직의 핏빛 조종을 울렸습니다.",
                "object",
                None,
                "composition=upright_flared_bell_one_rope_stub",
                ("one upright classic bell silhouette", "one short frayed rope stub"),
                ("tablet", "stale silk bundles"),
            ),
            (
                "추악한 이기심은 백성들의 삶을 거대한 지옥도로 만들었습니다.",
                "pair",
                2,
                "composition=two_bearers_one_closed_shroud",
                ("exactly two separate adult bearers", "one fully closed human-shaped hemp shroud", "one rectangular timber stretcher"),
                ("snapped spears", "soldiers"),
            ),
            (
                "남건과 남산 형제는 평양성을 걸어 잠그고 결사항전을 준비했습니다.",
                "pair",
                2,
                "composition=namgeon_namsan_last_stand_pair",
                ("exactly two adult male Goguryeo brothers: Namgeon and Namsan", "four empty hands visible", "low rammed-earth rampart with irregular stone facing", "Namsan right points with an empty hand"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "하지만 밖에는 당나라 대군, 안에는 극도의 공포와 불신뿐이었죠.",
                "group",
                3,
                "composition=three_soldiers_mutual_distrust",
                ("exactly three fearful Goguryeo soldiers with six empty hands", "exactly three separate soldiers form one tense triangle", "all six open empty hands visible", "center looks back"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "백성은 굶주림에 쓰러지고 병사는 절망적인 싸움에 내몰렸습니다.",
                "pair",
                2,
                "composition=starving_civilian_exhausted_soldier_pair",
                ("exactly two adults: starving civilian and kneeling lamellar soldier", "gaunt civilian left and lamellar soldier right", "four empty hands on knees", "exactly one empty basket total between them", "smooth earthen wall extends past top edge", "blank mud fills both lower corners"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "이것이 지도자의 탐욕이 빚어낸 대제국의 비참하고 서늘한 최후죠.",
                "object",
                None,
                "composition=goguryeo_hall_column_splits_at_base",
                ("one massive unpainted Goguryeo timber hall support column splitting", "one thick timber support column splits", "long fresh splinters", "one crossbeam sags above"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "무자비한 힘의 논리 앞에 혈육의 정은 종이 조각에 불과했습니다.",
                "object",
                None,
                "composition=single_blank_sheet_burns_to_ash",
                ("one blank unmarked fibrous sheet burning into ash", "one seamless cool grey stone surface", "pale blank left half and black curled right half", "one jagged burning edge with attached small flames"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "살아남아 권력을 쥐려는 짐승 같은 생존 본능만이 춤을 추는 지옥.",
                "animal",
                None,
                "composition=two_wolves_circle_in_earthen_pit",
                ("exactly two grey wolves in one dark earthen pit", "exactly two separate full-body wolves", "each with one head, four legs and one visible tail", "one crouches left and one braces right"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "지옥 한가운데서 고구려의 심장 평양성은 서서히 고립되어 갔습니다.",
                "landscape",
                None,
                "composition=pyongyang_fortress_encircled_by_tang_camp",
                ("one full-scale Pyongyang Goguryeo fortress encircled by Tang tents", "one full-scale roofless earthen fortress occupies center", "one surrounding ring of low tan Tang tents", "small fires sit only in bare gaps", "open dark ground isolates it"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "천하를 호령하던 대제국이 속에서부터 완전히 곪아 터져버렸습니다.",
                "object",
                None,
                "composition=single_jar_exposes_internal_rot",
                ("one plain unglazed Goguryeo grain jar ruptured open by black-green rot", "one plain unglazed jar keeps an intact rim and sides", "one jagged front rupture exposes black-green mold", "clumped spoiled millet"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "연개소문의 독재는 결국 제 살을 깎아 먹는 치명적인 독이었습니다.",
                "animal",
                None,
                "composition=single_snake_bites_own_body",
                ("one dark snake clamping its own continuous mid-body between closed jaws", "one complete open S-shaped snake spans the frame", "closed upper and lower jaws overlap that body section", "tapered tail ends far right", "featureless cold stone fills all edges"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "내부 결속력이 파괴된 국가는 더 이상 버텨낼 힘이 없었습니다.",
                "object",
                None,
                "composition=three_separated_goguryeo_shields",
                ("exactly three separate Goguryeo oval timber shields", "exactly three convex oval shields occupy left-center-right slots", "wide bare-earth gaps", "exactly one central iron boss appears on each shield"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "외적보다 무서운 것은 바로 내부의 썩어빠진 탐욕과 분열입니다.",
                "object",
                None,
                "composition=two_rank_seals_divided_by_floor_crack",
                ("exactly two blank bronze seals divided by one deep floor crack", "exactly two blank-backed bronze seals sit far left and far right", "one deep jagged vertical floor fissure", "packed clay fills every edge"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "국방력이 뛰어나도 지배층이 부패하면 나라는 단숨에 망해버립니다.",
                "object",
                None,
                "composition=one_shield_rotten_rear_bindings",
                ("one tall oval shield, back side up, with one broken leather grip", "exactly one tall oval shield lies flat backside-up", "exactly one broad horizontal leather grip crosses its center", "snapped once into two facing frayed ends", "packed earth fills every edge"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "권력을 사유화하려는 끝없는 탐욕이 만들어낸 거대한 핏빛 파국.",
                "object",
                None,
                "composition=toppled_authority_stamp_in_irregular_stain",
                ("one cracked bronze stamp with a low bridge knob in a dark-red stain", "one thick square bronze stamp lies toppled", "one low bridge knob is fixed directly to back center", "one chipped fracture and irregular dark-red stain", "rough charcoal stone"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "백성들이 흘린 뼈아픈 피눈물은 결코 씻을 수 없는 흉터가 되었죠.",
                "object",
                None,
                "composition=one_foundation_stone_permanent_red_scar",
                ("one flat foundation stone with one permanent red scar", "exactly one broad natural granite slab fills center", "one single unbranched near-vertical dark-red fissure", "top-center to bottom-center"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "제국의 수레바퀴는 억울한 죽음을 무자비하게 짓밟으며 굴러갑니다.",
                "object",
                None,
                "composition=helmet_half_buried_in_wheel_track",
                ("one empty dented segmented iron helmet in one fresh cart-wheel track", "dented cap rests directly on the floor of the broad fresh cart-wheel track", "shallow half-dome crown", "dented half-dome cap centered on its side", "featureless churned mud fills the frame"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "패자의 시체 위에서 춤추는 권력의 잔혹한 맨얼굴을 낱낱이 보십시오.",
                "object",
                None,
                "composition=tang_shoe_pins_goguryeo_helmet",
                ("exactly one cropped Tang-era cloth-wrapped forefoot pressing exactly one dented Goguryeo iron cap", "matte charcoal woven wraps, crossed cloth bands", "soft rounded toe, flat cloth underside", "the wrapped forefoot enters upper left", "flat cloth underside press directly onto the shallow segmented iron cap"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "낭만이 거세된 고대 동아시아의 피 튀기는 서늘하고 냉혹한 투기장.",
                "pair",
                2,
                "composition=two_weaponless_fighters",
                ("exactly two weaponless fighters: rust Goguryeo and black Tang", "rust fighter left drives a right fist", "black fighter right blocks with his left forearm", "four closed fists", "featureless ochre earthen wall fills the background edge to edge"),
                ("stale silk bundles", "lacquer table"),
            ),
            (
                "환상에서 깨어나 진짜 역사의 비릿한 무게를 견뎌내야만 합니다.",
                "object",
                None,
                "composition=golden_veil_beside_dented_helmet",
                ("one torn golden silk veil beside one shallow segmented Goguryeo iron cap", "exactly two total objects remain separate", "one torn golden veil at left", "one shallow segmented iron cap lying on its side", "open bottom and empty interior visible"),
                ("stale silk bundles", "lacquer table"),
            ),
        )
        for narration, kind, count, composition, required, forbidden in cases:
            with self.subTest(narration=narration):
                normalized = normalize_cut_image_prompt(source, narration)
                compiled = self.compile(normalized)
                self.assertEqual(compiled.scene_kind, kind)
                self.assertEqual(compiled.person_count, count)
                self.assertIn(composition, compiled.diagnostics)
                for term in required:
                    self.assertIn(term, compiled.positive)
                for term in forbidden:
                    self.assertNotIn(term, compiled.positive)
                self.assertFalse(re.search(r"(?:^|[,;.]\s*)(?:no|without|avoid|never|do not)\b", compiled.positive, re.IGNORECASE))
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertLessEqual(len(compiled.negative), 520)

        negative_cases = (
            (
                "아버지가 평생을 바쳐 지킨 나라를 적국에 헌납한 자들.",
                ("third shield piece", "two separate complete shields", "painted emblem"),
            ),
            (
                "인질을 바치며 당나라 황제에게 살려달라고 납작 엎드린 겁니다.",
                ("collar button", "standing collar", "visible feet"),
            ),
            (
                "고구려의 약점을 가장 잘 아는 자가 치명적인 스파이가 된 겁니다.",
                ("wooden tally", "face drawing", "fourth stone marker", "person"),
            ),
            (
                "조국도, 가문의 이름도 권력 앞에서는 미련 없이 내던졌죠.",
                ("sky background", "clouds", "missing floorboards"),
            ),
            (
                "일인 독재의 축이 무너지자 제국 전체가 모래성처럼 붕괴합니다.",
                ("tiled roof", "gatehouse", "vertical wall facade"),
            ),
            (
                "연개소문의 권력 세습은 고구려에 가장 치명적인 자살골이었습니다.",
                ("wooden beam", "tool", "missing black poison", "dry lower half"),
            ),
            (
                "1차 방어선 신성마저 내부 반역으로 어이없이 성문이 열리고 맙니다.",
                ("closed chain loop", "chain ends touching", "second chain", "hook", "door seam", "cracked ground"),
            ),
            (
                "남건과 남산 형제는 평양성을 걸어 잠그고 결사항전을 준비했습니다.",
                ("sword", "third commander", "rectangular ashlar masonry", "signboard"),
            ),
            (
                "하지만 밖에는 당나라 대군, 안에는 극도의 공포와 불신뿐이었죠.",
                ("sword", "floating weapon", "fourth soldier", "hidden hand"),
            ),
            (
                "백성은 굶주림에 쓰러지고 병사는 절망적인 싸움에 내몰렸습니다.",
                ("third person", "shield", "second basket", "white sky", "utility pole"),
            ),
            (
                "이것이 지도자의 탐욕이 빚어낸 대제국의 비참하고 서늘한 최후죠.",
                ("second column", "rolled scroll", "signboard", "Japanese temple"),
            ),
            (
                "무자비한 힘의 논리 앞에 혈육의 정은 종이 조각에 불과했습니다.",
                ("black background", "open book", "room wall", "person"),
            ),
            (
                "살아남아 권력을 쥐려는 짐승 같은 생존 본능만이 춤을 추는 지옥.",
                ("third wolf", "extra head", "five legs", "human"),
            ),
            (
                "지옥 한가운데서 고구려의 심장 평양성은 서서히 고립되어 갔습니다.",
                ("tiled roof", "hanok", "signboard", "miniature fortress"),
            ),
            (
                "천하를 호령하던 대제국이 속에서부터 완전히 곪아 터져버렸습니다.",
                ("second jar", "healthy grain", "missing mold", "written characters"),
            ),
            (
                "연개소문의 독재는 결국 제 살을 깎아 먹는 치명적인 독이었습니다.",
                ("second snake", "extra head", "missing bite contact", "tongue", "column", "lattice"),
            ),
            (
                "내부 결속력이 파괴된 국가는 더 이상 버텨낼 힘이 없었습니다.",
                ("fourth shield", "upright door panel", "Joseon street", "date caption"),
            ),
            (
                "외적보다 무서운 것은 바로 내부의 썩어빠진 탐욕과 분열입니다.",
                ("third seal", "second floor crack", "X-shaped crack", "red cord"),
            ),
            (
                "국방력이 뛰어나도 지배층이 부패하면 나라는 단숨에 망해버립니다.",
                ("front-facing shield", "second strap", "iron bar", "upright leaning shield"),
            ),
            (
                "권력을 사유화하려는 끝없는 탐욕이 만들어낸 거대한 핏빛 파국.",
                ("key-shaped object", "long stem", "lattice window", "UI icon"),
            ),
            (
                "백성들이 흘린 뼈아픈 피눈물은 결코 씻을 수 없는 흉터가 되었죠.",
                ("second fissure", "X-shaped crack", "horizontal red fissure", "corner initials"),
            ),
            (
                "제국의 수레바퀴는 억울한 죽음을 무자비하게 짓밟으며 굴러갑니다.",
                ("visible cart wheel", "corrugated metal sheet", "circular crater", "eye slit"),
            ),
            (
                "패자의 시체 위에서 춤추는 권력의 잔혹한 맨얼굴을 낱낱이 보십시오.",
                ("raised heel block", "separate shoe heel", "wooden heel block", "modern raised heel"),
            ),
            (
                "낭만이 거세된 고대 동아시아의 피 튀기는 서늘하고 냉혹한 투기장.",
                ("hidden hand", "spear", "sword", "tiled roof"),
            ),
            (
                "환상에서 깨어나 진짜 역사의 비릿한 무게를 견뎌내야만 합니다.",
                ("full-face helmet", "eye holes", "mask-shaped helmet", "European great helm"),
            ),
        )
        for narration, required_negative in negative_cases:
            with self.subTest(negative_narration=narration):
                compiled = self.compile(normalize_cut_image_prompt(source, narration))
                for term in required_negative:
                    self.assertIn(term, compiled.negative)

    def test_ep29_single_namsaeng_registry_scene_locks_male_age_and_cut_clan_cord(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Tang registry chamber at Chang'an; "
            "Main subject: exactly one adult male Namsaeng in his early thirties; "
            "Scene: Black-haired early-thirties Namsaeng kneels alone holding the two loose ends of exactly one short cut "
            "red clan cord in both hands."
        )

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("Primary subject: exactly one adult male Namsaeng in his early thirties", compiled.positive)
        self.assertIn("two loose ends of exactly one short cut red clan cord", compiled.positive)
        self.assertNotIn("no loop, tail, or extra strand", compiled.positive)
        for term in ("cord loop", "dangling cord tails", "extra red cord"):
            self.assertIn(term, compiled.negative)
        for term in (
            "third cord end",
            "multiple red strands",
            "woman",
            "second person",
            "elderly Namsaeng",
            "lattice window",
            "seal",
            "uncut cord",
        ):
            self.assertIn(term, compiled.negative)
        self.assertIn("composition=single_namsaeng_registry_shame", compiled.diagnostics)
        self.assertTrue(_should_check_internal_text_after_generation(compiled.positive))

    def test_relation_compact_prompt_keeps_flux2_field_order_without_duplication(self):
        source = (
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Yeon Namsaeng and Goguryeo succession crisis; "
            "Main subject: symbolic history scene; Scene: abstract metaphor"
        )
        cases = (
            (
                "패자의 시체 위에서 춤추는 권력의 잔혹한 맨얼굴을 낱낱이 보십시오.",
                "flat cloth underside press directly onto the shallow segmented iron cap",
                "modern lace-up boot",
            ),
        )
        for narration, required_geometry, required_negative in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(normalize_cut_image_prompt(source, narration))
                self.assertTrue(compiled.positive.startswith("Visible action:"))
                self.assertIn(required_geometry, compiled.positive)
                self.assertIn("prompt_order=relation_compact", compiled.diagnostics)
                self.assertNotIn("Visible evidence:", compiled.positive)
                self.assertLess(compiled.positive.index("Visible action:"), compiled.positive.index("Exact subject:"))
                self.assertLess(compiled.positive.index("Exact subject:"), compiled.positive.index("Visible inventory:"))
                self.assertLess(compiled.positive.index("Visible inventory:"), compiled.positive.index("Era/place/culture:"))
                self.assertLess(compiled.positive.index("Era/place/culture:"), compiled.positive.index("Composition:"))
                self.assertLess(compiled.positive.index("Composition:"), compiled.positive.index("Style:"))
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertIn(required_negative, compiled.negative)
                self.assertLess(compiled.negative.index(required_negative), 300)
                self.assertEqual(compiled.positive.count("exactly one cropped Tang-era cloth-wrapped forefoot"), 1)
                self.assertEqual(compiled.positive.count("exactly one dented Goguryeo iron cap"), 1)
                self.assertNotIn("Visible inventory: one ", compiled.positive)
                self.assertNotIn("exactly one shallow rimless iron cap", compiled.positive)
                self.assertNotIn("Visible action: and ", compiled.positive)
                self.assertIn("full-bleed 16:9", compiled.positive)

        wheel_track = self.compile(
            normalize_cut_image_prompt(
                source,
                "제국의 수레바퀴는 억울한 죽음을 무자비하게 짓밟으며 굴러갑니다.",
            )
        )
        self.assertTrue(wheel_track.positive.startswith("Visible action:"))
        self.assertIn("prompt_order=relation_compact", wheel_track.diagnostics)
        self.assertIn("dented cap rests directly on the floor of the broad fresh cart-wheel track", wheel_track.positive)
        self.assertEqual(wheel_track.positive.count("one empty dented segmented iron helmet"), 1)
        self.assertEqual(wheel_track.positive.count("one fresh cart-wheel track"), 1)
        self.assertNotIn("Visible inventory: one ", wheel_track.positive)
        self.assertTrue(_should_use_reduced_internal_text_detector(wheel_track.positive))

    def test_ep29_survivor_mud_and_prisoner_identity_locks_survive_compilation(self):
        source = (
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Goguryeo succession crisis after Yeon Gaesomun; "
            "Main subject: symbolic history scene; Scene: abstract metaphor"
        )
        survivor = self.compile(
            normalize_cut_image_prompt(
                source.replace("Scene: abstract metaphor", "Scene: A warrior's face covered in thick mud, looking like a demon"),
                "살기 위해 괴물이 된 자들의 서늘하고 끔찍한 생존 투쟁을 직시하십시오.",
            )
        )
        for term in ("mud-caked adult Goguryeo soldier", "mud visibly cakes his forehead", "both cheeks"):
            self.assertIn(term, survivor.positive)
        for term in ("clean face", "unsoiled face", "second soldier", "sword"):
            self.assertIn(term, survivor.negative)

        prisoners = self.compile(
            normalize_cut_image_prompt(
                source,
                "유민들은 사슬에 묶여 끌려가며 처절하고 차가운 피눈물을 삼켜야 했죠.",
            )
        )
        for term in ("grey-haired elder", "brown-robed man", "young grey-robed man", "separate side profiles", "Short taut chains"):
            self.assertIn(term, prisoners.positive)
        for term in (
            "duplicate face",
            "cloned face",
            "same man repeated",
            "fourth foreground person",
            "extra foreground body",
        ):
            self.assertIn(term, prisoners.negative)

    def test_ep29_endgame_repairs_keep_textless_objects_distinct_people_and_zero_person_scenes(self):
        source = (
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Goguryeo succession crisis after Yeon Gaesomun; "
            "Main subject: symbolic history scene; Scene: abstract metaphor"
        )

        siege = self.compile(
            normalize_cut_image_prompt(
                source,
                "형제의 난이 부른 핏빛 나비효과는 결국 평양성을 무섭게 옥죄어옵니다.",
            )
        )
        self.assertIn(siege.person_count, (None, 0))
        self.assertTrue(_should_use_reduced_internal_text_detector(siege.positive))

        betrayal = self.compile(
            normalize_cut_image_prompt(
                source,
                "조국을 판 배신자들은 적국에서 대대손손 비열한 부귀를 누렸습니다.",
            )
        )
        for term in ("white-bearded elder", "clean-shaven middle-aged man", "dark-red", "muted-green"):
            self.assertIn(term, betrayal.positive)
        for term in ("duplicate face", "same man repeated", "mirrored pose", "identical robe color"):
            self.assertIn(term, betrayal.negative)

        narration_cases = (
            (
                "영웅담에 가려진 백성들의 처참한 희생을 결코 잊어선 안 됩니다.",
                ("plain unmarked deep-red woven victory sash", "exactly three mismatched worn cloth shoes"),
                ("writing on sash", "Chinese character", "clean yellow banner"),
            ),
            (
                "충신은 죽고 매국노만 번성하는 끔찍하고 서늘한 핏빛 현실이죠.",
                ("collapsed cluster of cord-tied dark iron and rawhide Goguryeo cap plates",),
                ("smooth helmet dome", "modern steel helmet", "visor slit"),
            ),
            (
                "동화책은 태워버리고 진짜 역사의 비릿한 피 냄새를 맡아보십시오.",
                ("face-down blank hardwood tablet bundle", "lamellar shoulder plates"),
                ("writing on wood", "book cover text", "modern helmet"),
            ),
            (
                "핏빛 체스판 위에서 백성은 한낱 소모품 장기말에 불과했으니까요.",
                ("three palm-sized grey stone tokens", "three mismatched worn Goguryeo cloth shoes"),
                ("human body", "giant stone block", "chessboard"),
            ),
        )
        for narration, positive_terms, negative_terms in narration_cases:
            compiled = self.compile(normalize_cut_image_prompt(source, narration))
            self.assertEqual(compiled.scene_kind, "object")
            self.assertIn(compiled.person_count, (None, 0))
            for term in positive_terms:
                self.assertIn(term, compiled.positive)
            for term in negative_terms:
                self.assertIn(term, compiled.negative)

    def test_ep29_blocked_cut_repairs_preserve_detector_scope_and_failure_constraints(self):
        source = (
            "Year/period: 666-668 AD; Exact place: Goguryeo and Tang China; "
            "Scene evidence: Goguryeo succession crisis after Yeon Gaesomun; "
            "Main subject: symbolic history scene; Scene: abstract metaphor"
        )
        cases = (
            (
                "피로 물든 제국의 수레바퀴는 그 뼈들을 잘근잘근 부수며 계속 굴러가죠.",
                "dented cap rests directly on the floor of the broad fresh cart-wheel track",
                ("modern steel bowl helmet", "second helmet", "full wheel"),
            ),
            (
                "남생 일가의 배신은 나당 연합군에게 가장 치명적이고 완벽한 무기였습니다.",
                "only the dagger, cord and unmarked timber surface",
                ("tally blocks", "writing on blade", "Chinese characters"),
            ),
            (
                "환상적인 영웅 전설의 껍데기를 자비 없이 벗겨낸 날 것 그대로의 역사입니다.",
                "plain unmarked cracked gilt-bronze cover plate",
                ("body", "modern shoes", "stacked pages"),
            ),
            (
                "낡은 동화책을 찢어버리고 고대인들의 비릿한 피 냄새를 직접 맡아보십시오.",
                "plain unmarked dark-red woven cloth",
                ("body parts", "modern shoes", "yellow flag"),
            ),
            (
                "승자의 역사 뒤에 버려진 숱한 패자들의 고통을 피하지 말고 직시하십시오.",
                "flat heel-less wrapped-cloth shoe",
                ("background people", "rubber sole", "modern Oxford shoe"),
            ),
            (
                "아들들의 배신은 그 어떤 외부의 군대보다 제국에 끔찍하고 치명적이었습니다.",
                "flattened cluster of cord-tied dark iron and rawhide command-cap plates",
                ("wearer", "smooth helmet dome", "modern steel helmet"),
            ),
        )
        for narration, positive_term, negative_terms in cases:
            compiled = self.compile(normalize_cut_image_prompt(source, narration))
            self.assertIn(positive_term, compiled.positive)
            for term in negative_terms:
                self.assertIn(term, compiled.negative)

        terrain = self.compile(
            normalize_cut_image_prompt(
                source,
                "고구려의 모든 지형과 성곽의 약점이 적의 지도 위에 고스란히 표시되었죠.",
            )
        )
        self.assertTrue(_should_ignore_object_person_segmentation(terrain.positive))
        self.assertIn("installed edge-to-edge rough floorboards", terrain.positive)
        self.assertIn("white background", terrain.negative)

        brothers_source = source.replace("Scene: abstract metaphor", "Scene: two wolves from the same pack attack each other")
        brothers = self.compile(
            normalize_cut_image_prompt(
                brothers_source,
                "이익 앞에서 혈연마저 가차 없이 도륙하는 비정한 야생의 법칙 그 자체입니다.",
            )
        )
        self.assertIn("open snowy packed-earth slope", brothers.positive)
        self.assertTrue(_should_use_reduced_internal_text_detector(brothers.positive))

        collapse = self.compile(
            normalize_cut_image_prompt(
                source,
                "700년을 이어온 거대한 제국의 역사가 단 한 가문의 탐욕으로 증발합니다.",
            )
        )
        self.assertTrue(_should_ignore_corner_signature_detector(collapse.positive))

    def test_ep29_severed_clan_sash_uses_two_piece_object_only_evidence(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: dark timber registry wall at Chang'an; "
            "Main subject: one severed grey woven Goguryeo clan sash; "
            "Scene: Object-only straight-down view of one wide grey woven clan sash severed once into exactly two halves "
            "with one empty gap between facing frayed edges."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("exactly two total objects", compiled.positive)
        for term in ("uncut sash", "third sash piece", "fourth sash piece", "parallel sash strips", "room perimeter", "extra belt", "red cord", "person", "hands"):
            self.assertIn(term, compiled.negative)
        self.assertIn("composition=severed_clan_sash_two_halves", compiled.diagnostics)
        self.assertTrue(_should_ignore_split_panel_for_intentional_center_gap(compiled.positive))

    def test_ep29_two_registry_seals_remain_one_object_surface(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Tang imperial registry at Chang'an; "
            "Main subject: exactly two plain square bronze seal blocks; "
            "Scene: Object-only low oblique view of exactly two palm-sized squat square bronze seal blocks with short knob "
            "handles, stamp faces down, the left handle bare and one red cord tied around the right handle."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("bare rough tabletop fills the full frame", compiled.positive)
        self.assertIn("no room visible", compiled.positive)
        self.assertIn("left dark top knob bare", compiled.positive)
        self.assertIn("right green top knob tied with one compact red cord", compiled.positive)
        self.assertIn("cube", compiled.negative)
        self.assertIn("side-mounted knob", compiled.negative)
        self.assertIn("third seal", compiled.negative)
        self.assertIn("cord on left seal", compiled.negative)
        self.assertIn("written characters", compiled.negative)
        self.assertIn("visible room background", compiled.negative)
        self.assertIn("tassel", compiled.negative)
        self.assertIn("wooden tray", compiled.negative)
        self.assertIn("composition=two_registry_seals_single_surface", compiled.diagnostics)

    def test_object_only_gate_brace_is_not_misclassified_as_fortress_landscape(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: Goguryeo frontier fortress inner gate; "
            "Main subject: one sabotaged Goguryeo timber gate brace; "
            "Scene: Object-only interior close view of one horizontal timber gate brace with one deep V-shaped axe notch."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("defender", compiled.negative)
        self.assertIn("human silhouette", compiled.negative)
        self.assertIn("two locking beams", compiled.negative)
        self.assertIn("ashlar blocks", compiled.negative)
        self.assertIn("long horizontal crack", compiled.negative)
        self.assertIn("composition=single_axe_notched_gate_beam", compiled.diagnostics)

    def test_plural_defenders_make_a_group_scene(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: Goguryeo fortress breach; "
            "Main subject: Goguryeo defenders; Scene: Defenders recoil from one breached timber gate."
        )

        self.assertIsNone(compiled.person_count)

    def test_wilderness_escape_riders_block_modern_roadside_cues(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: mountain wilderness south of Pyongyang; "
            "Main subject: exactly four adult riders; "
            "Scene: Exactly four riders on four horses follow one muddy wilderness track between earthen banks and pine slopes."
        )

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        for term in ("fifth rider", "utility pole", "roadside house", "rail fence"):
            self.assertIn(term, compiled.negative)

    def test_survivor_casualty_gear_scene_blocks_modern_clothing_and_vignette(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Liaodong aftermath; "
            "Main subject: exactly one adult Goguryeo survivor beside abandoned casualty gear; "
            "Scene: One survivor kneels beside a broken shield, snapped spear and folded shroud on open ground."
        )

        self.assertEqual(compiled.scene_kind, "single")
        self.assertIn("wrap-front robe", compiled.positive)
        self.assertIn("black corner vignette", compiled.negative)
        self.assertIn("buttoned modern shirt", compiled.negative)
        self.assertIn("helmet", compiled.negative)
        self.assertIn("composition=single_survivor_casualty_gear", compiled.diagnostics)

    def test_low_command_stool_scene_blocks_throne_and_glyphs(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Liaodong aftermath; "
            "Main subject: one low backless Tang command stool over fallen gear; "
            "Scene: Object-only view of one low backless Tang stool pinning a torn sash and shroud over a broken shield."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("high-backed chair", compiled.negative)
        self.assertIn("glyph on furniture", compiled.negative)

    def test_object_only_fortress_relief_remains_a_tabletop_object(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Goguryeo command room; "
            "Main subject: one textless clay fortress relief model; "
            "Scene: Object-only high-angle close view of one dagger driven into a miniature clay fortress relief model."
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("composition=object_close", compiled.diagnostics)

    def test_isolated_full_size_fortress_is_a_landscape(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Pyongyang; "
            "Main subject: one isolated Goguryeo fortress; "
            "Scene: The fortress is surrounded by enemy tents."
        )

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("composition=wide_environment", compiled.diagnostics)

    def test_long_group_contract_keeps_scene_evidence_and_era_fidelity(self):
        compiled = self.compile(
            "Year/period: 378 AD; Exact place: Danube frontier; "
            "Main subject: exactly four unarmored adult civilians; "
            "Scene: Four adults walk across a trampled field carrying separate cloth bundles at waist height, "
            "all four full bodies visible from head to boots, each person separated by open ground; "
            "Scene evidence: frost, cart ruts, low tents, distant patrol silhouettes; "
            "Style: serious historical documentary illustration."
        )
        self.assertIn("Era fidelity:", compiled.positive)
        self.assertIn("Visible evidence: frost, cart ruts, low tents", compiled.positive)
        self.assertIn("Full-bleed 16:9; one viewpoint; scene reaches every edge", compiled.positive)
        self.assertIn("modern clothing", compiled.negative)
        self.assertLessEqual(len(compiled.positive), 950)

    def test_culture_and_material_fields_survive_with_scene_evidence(self):
        prompt = (
            "Year/period: 378 AD; Exact place: Danube frontier; "
            "Culture scope: Late Roman Danube frontier communities; "
            "Material culture: Late Roman wool tunics, wrapped cloaks, leather belts, fibula brooches, simple leather footwear; "
            "Main subject: exactly four unarmored adult civilians; "
            "Scene: Four adults walk across a trampled field carrying separate cloth bundles at waist height, "
            "all four full bodies visible from head to boots, each person separated by open ground; "
            "Scene evidence: frost, cart ruts, low tents, distant patrol silhouettes."
        )
        compiled = self.compile(prompt)
        self.assertIn("Culture scope: Late Roman Danube frontier", compiled.positive)
        self.assertIn("Material culture: Late Roman wool tunics, wrapped cloaks", compiled.positive)
        self.assertIn("open ground between silhouettes", compiled.positive)
        self.assertIn("Visible evidence: frost, cart ruts, low tents, distant patrol", compiled.positive)
        self.assertNotIn("Era fidelity:", compiled.positive)
        self.assertLessEqual(len(compiled.positive), 950)

        retry = compile_image_prompt(
            prompt,
            model_id="comfyui-flux2-klein-4b",
            quality_hint="Corner continuity: local ground, sky or shadow fills every corner",
        )
        self.assertIn("open ground between silhouettes", retry.positive)
        self.assertIn("Corner continuity: local ground, sky or shadow fills every corner", retry.positive)
        self.assertLessEqual(len(retry.positive), 950)

    def test_single_person_contract_blocks_extra_limbs_and_twisted_neck(self):
        compiled = self.compile(
            "Year/period: 1066 AD; Exact place: timber command tent; "
            "Main subject: one adult queen; Scene: The queen turns toward a cracked bronze crown; "
            "Scene evidence: wool cloak, timber table, side candlelight."
        )
        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("two connected arms", compiled.positive)
        self.assertIn("two grounded legs", compiled.positive)
        self.assertIn("natural head-neck-shoulder axis", compiled.positive)
        for term in ("extra arms", "third arm", "extra legs", "third leg", "twisted neck", "broken neck"):
            self.assertIn(term, compiled.negative)

    def test_two_roles_are_not_misclassified_as_one_person(self):
        compiled = self.compile(
            "Year/period: 1050 AD; Exact place: royal hall; Main subject: one adult envoy; "
            "Scene: The envoy kneels before the king while presenting a sealed letter; "
            "Scene evidence: rough stone wall and candlelight."
        )
        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("exactly two adults", compiled.positive.lower())
        self.assertNotIn("sealed sealed", compiled.positive.lower())

    def test_repeated_four_person_fields_count_once_and_allow_distant_patrol(self):
        compiled = self.compile(
            "Year/period: 378 AD; Exact place: Danube frontier; "
            "Main subject: four unarmored adults and distant mounted patrols; "
            "Scene: Four unarmored adults gather belongings while mounted patrols watch from far background; "
            "Scene evidence: trampled field, carts, frost."
        )
        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("Exactly four foreground adults in separated depth slots", compiled.positive)
        self.assertIn("distant mounted patrols", compiled.positive)
        self.assertNotIn("shield", compiled.positive.lower())
        self.assertNotIn("eighth person", compiled.negative)
        self.assertNotIn("extra background person", compiled.negative)

    def test_exact_total_overrides_redundant_role_count(self):
        pair = self.compile(
            "Main subject: exactly two adult figures, King John and one baron; "
            "Scene: King John and the baron stand across a table."
        )
        riders = self.compile(
            "Main subject: exactly three adult horse riders; "
            "Scene: Three riders cross the steppe, each on a separate horse."
        )
        self.assertEqual(pair.person_count, 2)
        self.assertIn("exactly two adults", pair.positive.lower())
        self.assertEqual(riders.person_count, 3)
        self.assertIn("Exactly three riders on exactly three separate horses", riders.positive)
        self.assertIn("fourth rider", riders.negative)
        self.assertIn("fourth horse", riders.negative)

    def test_crowded_rider_scene_overrides_macro_camera_and_separates_bodies(self):
        compiled = self.compile(
            "macro detail shot of horse riders crossing a vast windy steppe with families and wagons behind them; "
            "ancient historical reconstruction, mythic but grounded, no fantasy monsters; "
            "unique era-accurate foreground cue: linen cloak caught in sea wind; "
            "cinematic documentary still, realistic textures, no text, no watermark"
        )
        self.assertEqual(compiled.scene_kind, "group")
        self.assertIn("composition: wide action", compiled.positive.lower())
        self.assertIn("separate rider-horse silhouettes", compiled.positive)
        self.assertIn("four grounded legs", compiled.positive)
        self.assertIn("a body separate from the horse", compiled.positive)
        self.assertNotIn("macro detail shot", compiled.positive.lower())

    def test_indo_european_horse_ritual_scenes_do_not_invent_riders_or_symbolic_collages(self):
        trailer = (
            ", cinematic reconstruction of ancient Indo-European royal ritual grounded in Vedic, Roman, and medieval "
            "source evidence, 3000 BCE to 1000 BCE, period-accurate clothing, architecture, tools, and material culture"
        )
        cases = (
            (
                "Decorated white stallion entering a rival kingdom as villagers and armed guards freeze",
                "empty-backed decorated white stallion",
            ),
            (
                "Several Rival rulers receiving news of the approaching horse and weighing weapons against tribute",
                "three rival rulers stand inside one plain council shelter",
            ),
            (
                "Royal escorts reopening the gate as the defeated Rival ruler offers formal submission",
                "one defeated rival ruler kneels",
            ),
            (
                "Sacrificing king receiving the procession from a raised platform before the capital",
                "exactly four upright adults",
            ),
            (
                "Chanting priests surrounding a symbolic horse silhouette transforming into renewed cosmic order",
                "around one small smoking clay brazier",
            ),
            (
                "Palm-leaf ritual text opened beside a carefully arranged Vedic sacrificial ground",
                "single narrow palm-leaf strip below chest height",
            ),
            (
                "Krishna and Vyasa counseling the haunted Yudhishthira beside a ritual plan",
                "exactly three bare-headed ancient indian adult men",
            ),
            (
                "Bloodstained crown washed beside a sacred fire and decorated stallion",
                "yudhishthira kneels alone at left and washes both hands",
            ),
            (
                "Gold coin passing through markets while its horse image evokes armies and tribute",
                "exactly one tiny round gold coin flat at the center",
            ),
            (
                "Statue of Mars surrounded by weapons, grain, blood-red cloth, and new growth",
                "one roman citizen-soldier",
            ),
            (
                "Large ritual cauldron and white mare imagery around the Irish claimant",
                "shoulders-up inside one large iron cauldron",
            ),
            (
                "White stallion walking across a map while border markers fall behind it",
                "one continuous dirt road between two low physical boundary cairns",
            ),
            (
                "Fragmented ritual traditions connected tentatively to a missing prehistoric source",
                "two-present-day-scholar-only scene",
            ),
            (
                "Symbolic tableau of crown, grain, dead horse, royal couple, and gathered provinces",
                "four-late-vedic-adult-only scene",
            ),
            (
                "Full cast surrounding the horse with conflicting ambitions and unequal risks",
                "plain wrapped antariya or dhoti-like lower garments",
            ),
        )
        for source, required in cases:
            with self.subTest(source=source):
                compiled = self.compile(
                    f"Main subject: {source}; Scene: {source}{trailer}; "
                    "NARRATION VISUAL ALIGNMENT: match the spoken moment through visible action"
                )
                lowered = compiled.positive.lower()
                self.assertIn(required, lowered)
                self.assertNotIn("limited readable foreground riders", lowered)
                self.assertNotIn("separate rider-horse silhouettes", lowered)
                self.assertNotIn("symbolic horse silhouette", lowered)

        for source in (
            "Gupta gold coin showing a horse before a sacrificial post in close detail",
            "Reverse of an Ashvamedha coin with queen figure and royal inscription shapes",
        ):
            with self.subTest(source=source):
                compiled = self.compile(
                    f"Main subject: {source}; Scene: {source}{trailer}; "
                    "NARRATION VISUAL ALIGNMENT: match the spoken moment through visible object evidence"
                )
                lowered = compiled.positive.lower()
                self.assertIn("strict straight-down 90-degree object-only view", lowered)
                self.assertIn("exactly one small round gupta gold coin", lowered)
                self.assertNotIn("foreground adults", lowered)

        positive = _apply_longtube_dark_manhwa_style(
            "Visible action: One riderless decorated white stallion with a fully visible empty back walks through "
            "one open border gate while on-foot guards watch. Body integrity: each adult has one head and two feet.",
            model_id="comfyui-z-image-turbo",
        )
        self.assertTrue(positive.startswith("EMPTY HORSE BACK SPATIAL LOCK"))
        self.assertIn("continuous natural hair", positive.lower())
        self.assertIn("two visible feet", positive)
        self.assertTrue(
            _should_use_ch2_riderless_border_gate_layout(
                "Year/period: 3000 BCE to 1000 BCE; Source workbook scene: Decorated white stallion entering "
                "a rival kingdom as villagers and armed guards freeze"
            )
        )
        self.assertFalse(
            _should_use_ch2_riderless_border_gate_layout(
                "Year/period: 3000 BCE to 1000 BCE; Source workbook scene: Rival rulers receive news"
            )
        )

    def test_single_rider_pointing_contract_keeps_rein_hand_distinct(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: Liaodong military road; "
            "Main subject: one adult rider Yeon Namsaeng on one horse; "
            "Scene: Yeon Namsaeng rides one horse on a muddy road. His raised right arm alone points forward; "
            "his lowered left fist grips both leather reins at the saddle pommel. Storm clouds and split-log rails fill the frame."
        )
        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("raised right arm alone points forward", compiled.positive)
        self.assertIn("lowered left fist grips both leather reins", compiled.positive)
        self.assertIn("dark storm clouds fill upper half", compiled.positive)
        self.assertIn("thick split-log rails enter both edges", compiled.positive)
        self.assertIn("right arm points, left fist grips reins", compiled.positive)
        self.assertLessEqual(len(compiled.positive), 950)

    def test_single_rider_storm_road_contract_keeps_both_hands_on_reins(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: Liaodong military road; "
            "Main subject: one adult rider Yeon Namsaeng on one horse; "
            "Scene: Yeon Namsaeng leans forward as his horse turns into one muddy road fork. "
            "Both lowered fists grip the paired leather reins at the saddle pommel. "
            "Storm clouds and split-log rails fill the frame."
        )
        self.assertIn("Both lowered fists grip the paired leather reins", compiled.positive)
        self.assertIn("both elbows bend down and both fists grip paired reins", compiled.positive)
        self.assertIn("dark storm clouds fill upper half", compiled.positive)
        self.assertLessEqual(len(compiled.positive), 950)

    def test_three_adult_tang_cup_scene_locks_slots_props_and_plain_wall(self):
        compiled = self.compile(
            "Year/period: late 7th century; Exact place: Tang elite residence at Chang'an; "
            "Culture scope: Goguryeo-Korean and Tang-Chinese; "
            "Material culture: black folded Tang futou caps, dark round-collar silk robes, one low bronze drinking bowl; "
            "Main subject: exactly three adult men; "
            "Scene: Three adult men sit in one row; the center right palm holds the single low bronze drinking bowl; "
            "Scene evidence: plain dark timber wall and closed unmarked silk curtains."
        )
        self.assertEqual(compiled.person_count, 3)
        self.assertIn("elderly left, middle-aged center, young adult right", compiled.positive)
        self.assertIn("exactly six hands total", compiled.positive)
        self.assertIn("each man folds his own two hands", compiled.positive)
        self.assertIn("one small shallow bronze cup rests untouched", compiled.positive)
        self.assertIn("low black Tang futou caps cover tied hair", compiled.positive)
        self.assertIn("smooth closed circular necklines", compiled.positive)
        for term in ("wall calligraphy", "hanging scroll", "Japanese kimono", "stemmed goblet"):
            self.assertIn(term, compiled.negative)
        for term in ("second cup", "extra cup", "ceramic cup", "bare topknot", "cross-collar robe"):
            self.assertIn(term, compiled.negative)
        for term in ("handled mug", "pedestal goblet", "stemmed bowl", "second drinking bowl"):
            self.assertIn(term, compiled.negative)
        for term in ("oversized bowl", "cauldron", "large vessel"):
            self.assertIn(term, compiled.negative)
        self.assertLessEqual(len(compiled.positive), 950)

    def test_river_runs_is_landscape_not_human_action(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: Liaodong riverbank; "
            "Main subject: a rain-swollen river carrying broken war equipment; "
            "Scene: The wide river runs dark with red-clay runoff among muddy reeds."
        )
        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIsNone(compiled.person_count)
        self.assertNotIn("one adult body", compiled.positive)

    def test_exact_four_total_overrides_repeated_role_counts(self):
        compiled = self.compile(
            "Main subject: exactly four adults: two defenders; two soldiers; "
            "Scene: Exactly four adults clash at a breach: two defenders and two soldiers in separate body slots."
        )
        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("Exactly four foreground adults in separated depth slots", compiled.positive)

    def test_armed_full_body_action_does_not_collapse_to_face_portrait(self):
        compiled = self.compile(
            "Main subject: one adult defender; "
            "Scene: One adult defender raises a short straight sword beside a broken shield, fierce face visible."
        )
        self.assertEqual(compiled.scene_kind, "single")
        self.assertIn("Medium three-quarter story composition", compiled.positive)
        self.assertNotIn("Tight face-focused portrait", compiled.positive)

    def test_mounted_archer_contract_forces_full_background(self):
        compiled = self.compile(
            "Main subject: one adult rider on one horse; "
            "Scene: Adult rider releases one arrow from a recurved bow on one horse; "
            "Scene evidence: dark overcast sky, rough timber palisade, packed earth."
        )
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("dark overcast sky fills the upper third", compiled.positive)
        self.assertIn("rough timber palisade and packed earth reach every edge", compiled.positive)
        self.assertIn("one rider draws one recurved bow on one horse", compiled.positive)

    def test_burial_contract_integrates_marker_into_full_bleed_ground(self):
        compiled = self.compile(
            "Main subject: one Tang-period family burial mound and one blank stone marker; "
            "Scene: Object-only view of one mound and one marker in dry grass under dark clouds."
        )
        self.assertIn("full-bleed low landscape", compiled.positive)
        self.assertIn("dark clouded sky fills the top edge", compiled.positive)
        self.assertIn("stone marker stays integrated in the ground plane", compiled.positive)

    def test_bird_scene_uses_bird_geometry_instead_of_four_legs(self):
        compiled = self.compile(
            "wide shot of three ravens flying above an empty medieval battlefield; "
            "cold dawn light; historical documentary illustration"
        )
        self.assertEqual(compiled.scene_kind, "animal")
        self.assertIn("two connected wings", compiled.positive)
        self.assertIn("two legs", compiled.positive)
        self.assertNotIn("four grounded legs", compiled.positive)

    def test_object_only_positive_never_mentions_human_anatomy(self):
        compiled = self.compile(
            "Year/period: 800 AD; Exact place: monastery workbench; "
            "Main subject: one cracked bronze crown; "
            "Scene: The crown rests alone on dark wool beside a broken seal; "
            "Scene evidence: rough timber surface, side candlelight."
        )
        self.assertEqual(compiled.scene_kind, "object")
        for term in ("hand", "finger", "person", "people", "human", "arm", "leg", "neck"):
            self.assertIsNone(re.search(rf"\b{term}s?\b", compiled.positive, re.IGNORECASE), term)
        self.assertIn("hands", compiled.negative)

    def test_plural_weapon_still_life_is_an_object_scene(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Goguryeo court floor; "
            "Main subject: exactly three broken swords; "
            "Scene: Three separate short straight swords lie in mud under hard side light."
        )
        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("person", compiled.negative)

    def test_civilian_shoes_are_not_counted_as_civilians(self):
        compiled = self.compile(
            "Year/period: 668 AD; Exact place: fallen granary; "
            "Main subject: one elderly adult witness; "
            "Scene: One elderly witness kneels beside three separate worn civilian cloth shoes in ash."
        )
        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)

    def test_guard_sash_is_not_counted_as_a_guard(self):
        compiled = self.compile(
            "Year/period: 667 AD; Exact place: Sinseong Fortress inner gate; "
            "Main subject: one fortress gate breached by internal sabotage; "
            "Scene: Object-only view of one heavy plank gate above one discarded woven guard sash."
        )
        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIsNone(compiled.person_count)

    def test_object_scene_ignores_people_only_in_global_evidence(self):
        compiled = self.compile(
            "Year/period: 666-668 AD; Exact place: Goguryeo granary; "
            "Main subject: one cracked clay granary jar; "
            "Scene: Object-only close evidence view of one cracked jar spilling spoiled millet; "
            "Scene evidence: succession crisis, palace guards, officials, soldiers, smoke."
        )
        self.assertEqual(compiled.scene_kind, "object")
        self.assertNotIn("Each adult", compiled.positive)
        self.assertIn("person", compiled.negative)

    def test_flux_and_sdxl_use_mature_bold_line_style(self):
        prompt = (
            "Year/period: 666 AD; Exact place: Pyongyang Fortress; "
            "Main subject: one adult Goguryeo commander; "
            "Scene: The commander turns toward a broken timber gate."
        )
        for model in ("comfyui-flux2-klein-4b", "comfyui-dreamshaper-xl-longtube-v15"):
            compiled = self.compile(prompt, model)
            self.assertIn("2D mature adult historical action cartoon", compiled.positive)
            self.assertIn("bold black ink outlines", compiled.positive)
            self.assertIn("emotional dynamic action", compiled.positive)
            self.assertIn("chibi", compiled.negative)
            self.assertIn("children's book art", compiled.negative)

    def test_explicit_global_style_overrides_cut_internal_style(self):
        compiled = self.compile(
            "Year/period: Late 1st century BC; Exact place: Wirye; "
            "Main subject: exactly two adult men; "
            "Scene: Onjo advances while Biryu remains behind; "
            "Style: serious adult graphic novel illustration, documentary manhwa; "
            "Global style: Hard-boiled historical cinematic ink-and-gouache illustration, "
            "rugged masculine atmosphere, coarse dry-brush texture, weathered faces, "
            "desaturated earth pigments, harsh side light and deep shadows"
        )

        self.assertIn("hard-boiled rugged masculine historical cinematic concept art", compiled.positive)
        self.assertIn("gritty rough dry-brush paint texture", compiled.positive)
        self.assertIn("deep black shadows", compiled.positive)
        self.assertIn("desaturated brown-charcoal-dark-red", compiled.positive)
        self.assertNotIn("documentary manhwa", compiled.positive)
        self.assertNotIn("historical action cartoon", compiled.positive)
        for term in (
            "artist signature",
            "red seal stamp",
            "calligraphy",
            "split panel",
            "outer border",
            "white paper margin",
        ):
            self.assertIn(term, compiled.negative)

    def test_hardboiled_landscape_does_not_prime_people(self):
        compiled = self.compile(
            "Year/period: Late 1st century BC; Exact place: river plain; "
            "Main subject: landscape only: one modest timber-and-packed-earth settlement; "
            "Scene: A wide empty river-plain landscape shows one settlement under rough thatch roofs; "
            "Material culture: timber structures, packed-earth walls, rough thatch roofs, "
            "plain woven long-sleeved garments, loose trousers, hide footwear; "
            "Global style: Hard-boiled gritty historical cinematic concept art, rough dry-brush paint, "
            "weathered faces and deep shadows"
        )

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("weathered terrain and scarred timber", compiled.positive)
        for term in ("garments", "trousers", "footwear", "weathered faces"):
            self.assertNotIn(term, compiled.positive)
        self.assertIn("person", compiled.negative)

    def test_hardboiled_object_keeps_lit_surface_at_every_edge(self):
        compiled = self.compile(
            "Year/period: Late 1st century BC; Exact place: later archival surface; "
            "Main subject: object-only, exactly two closed blank unmarked manuscript covers; "
            "Scene: An object-only view shows two separate manuscript covers on one continuous rough wood tabletop; "
            "Global style: Hard-boiled gritty historical cinematic concept art, rough dry-brush paint, "
            "deep shadows and harsh side light"
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn(
            "evenly exposed warm medium-brown continuous surface material at every canvas edge and corner",
            compiled.positive,
        )
        self.assertIn("lifted shadow detail and crisp contact shadows", compiled.positive)
        for term in ("black vignette", "solid black edge band", "shadowed perimeter"):
            self.assertIn(term, compiled.negative)

    def test_baekje_cut106_mixed_evidence_uses_archaeological_full_bleed_composition(self):
        payload = self._actual_baekje_ep01_script_fixture()
        compiled = self.compile(self._runtime_baekje_ep01_cut(payload, 106))

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("high-oblique present-day archaeological evidence view", compiled.positive)
        self.assertIn("Pungnap soil", compiled.positive)
        self.assertIn("wide bare-soil gap visibly separates them", compiled.positive)
        self.assertIn("daylight-lit brown soil fill all four edges and corners", compiled.positive)
        self.assertIn("composition=mixed_pungnap_manuscript_evidence", compiled.diagnostics)
        self.assertNotIn("archival wood surface", compiled.positive)
        self.assertNotIn("straight-down 90-degree", compiled.positive)
        for term in (
            "black vignette",
            "solid black edge band",
            "archival desk",
            "third manuscript",
            "writing on manuscript cover",
            "unreadable pseudo-writing",
            "weathered glyph marks",
            "grunge border",
            "scratch border",
            "distressed edge overlay",
            "inked corner frame",
            "touching manuscript covers",
            "overlapping manuscript covers",
            "stacked manuscripts",
        ):
            self.assertIn(term, compiled.negative)

        generated = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\images\cut_106.png"
        )
        clean_comparison = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\images\cut_107.png"
        )
        failed_frame = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_review\images\cut_106__needs_review__컷_106_150_검은_외곽_프레임_감지_재시도_2회_후_실패.png"
        )
        if generated.is_file() and clean_comparison.is_file() and failed_frame.is_file():
            self.assertFalse(_image_has_textured_dark_perimeter_overlay(generated))
            self.assertFalse(_image_has_textured_dark_perimeter_overlay(clean_comparison))
            self.assertTrue(_image_has_textured_dark_perimeter_overlay(failed_frame))

    def test_baekje_cut118_dragon_is_not_counted_as_a_person_and_corner_logo_is_detected(self):
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        payload = self._actual_baekje_ep01_script_fixture()
        source = self._runtime_baekje_ep01_cut(payload, 118)
        compiled = self.compile(source)
        self.assertEqual(compiled.scene_kind, "animal")
        self.assertTrue(_should_ignore_object_person_segmentation(source))
        self.assertIn("intact early Baekje packed-earth settlement", compiled.positive)
        self.assertIn("lower right", compiled.positive)
        for term in (
            "artist logo",
            "credit line",
            "red corner emblem",
            "burning battlefield ruins",
            "destroyed settlement",
        ):
            self.assertIn(term, compiled.negative)

        failed = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_review\images\cut_118__needs_review__컷_118_150_인물_수_불일치_0명_요구_1명_검출_감지_재시도_3회_후_실패.png"
        )
        if failed.is_file():
            self.assertTrue(_image_has_corner_artist_mark(failed))

    def test_baekje_cut107_pungnap_landscape_blocks_bottom_credit_bands(self):
        payload = self._actual_baekje_ep01_script_fixture()
        compiled = self.compile(self._runtime_baekje_ep01_cut(payload, 107))

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertIn("contemporary Pungnap archaeological location view", compiled.positive)
        self.assertIn("long low grass-covered rammed-earth city-wall embankment", compiled.positive)
        self.assertIn("close low-angle full-bleed", compiled.positive)
        self.assertIn("entire bottom edge and both lower corners", compiled.positive)
        self.assertIn("composition=present_day_pungnap_full_bleed_landscape", compiled.diagnostics)
        for term in (
            "artist logo",
            "location name text",
            "lower corner text",
            "credit line",
            "white corner emblem",
            "bottom title strip",
            "black bottom title band",
            "high-rise building",
            "building signage",
            "pyramid mound",
            "freestanding trapezoid mound",
            "excavation spoil pile",
        ):
            self.assertIn(term, compiled.negative)

    def test_baekje_cut126_envoy_warning_uses_zero_hand_closeup_and_blocks_speech_bubbles(self):
        payload = self._actual_baekje_ep01_script_fixture()
        compiled = self.compile(self._runtime_baekje_ep01_cut(payload, 126))

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("extreme facial two-shot", compiled.positive)
        self.assertIn("each complete face fills 65-75 percent", compiled.positive)
        self.assertIn("lower frame edge ends at both collarbones", compiled.positive)
        self.assertIn("plus all upper arms", compiled.positive)
        self.assertIn("crossed-collar fabric at two collar tops only", compiled.positive)
        self.assertNotIn("ankle-length trousers", compiled.positive)
        self.assertNotIn("footwear", compiled.positive)
        self.assertIn(
            "composition=baekje_ep01_nangnang_envoy_zero_hand_closeup",
            compiled.diagnostics,
        )
        for term in (
            "visible hand",
            "visible fingers",
            "speech bubble",
            "dialogue balloon",
            "caption box",
            "floating text block",
            "comic lettering",
            "torso below collarbones",
            "upper arm",
            "folded hands",
            "clasped hands",
            "hands on chest",
        ):
            self.assertIn(term, compiled.negative)

    def test_baekje_closing_guthe_records_are_blank_separate_objects_without_infographic_marks(self):
        payload = self._actual_baekje_ep01_script_fixture()
        for cut_number in range(146, 151):
            with self.subTest(cut=cut_number):
                compiled = self.compile(
                    self._runtime_baekje_ep01_cut(payload, cut_number)
                )
                self.assertEqual(compiled.scene_kind, "object")
                self.assertIn("closed face-down blank", compiled.positive)
                self.assertIn("straight-down 90-degree full-canvas archival view", compiled.positive)
                self.assertNotIn("Chinese Guthe", compiled.positive)
                if cut_number == 146:
                    self.assertIn("composition=guthe_origin_records_only", compiled.diagnostics)
                else:
                    self.assertIn(
                        "composition=guthe_origin_records_with_separate_relief",
                        compiled.diagnostics,
                    )
                for term in (
                    "Chinese characters",
                    "GUTHE text",
                    "cover title",
                    "decorated cover",
                    "cover illustration",
                    "map on cover",
                    "relief printed on manuscript",
                    "ink mark on manuscript",
                    "carved character on clay relief",
                    "white arrow",
                    "connector arrow",
                    "black outer frame",
                    "grunge border",
                ):
                    self.assertIn(term, compiled.negative)

        result_dir = Path(r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa")
        clean_146 = result_dir / "images" / "cut_146.png"
        clean_147 = result_dir / "images" / "cut_147.png"
        marked_148 = result_dir / "images" / "cut_148.png"
        if clean_146.is_file():
            self.assertFalse(_image_has_center_infographic_arrow(clean_146))
            self.assertFalse(_image_has_guthe_record_cover_glyph_cluster(clean_146))
        if clean_147.is_file() and marked_148.is_file():
            self.assertFalse(_image_has_guthe_record_cover_glyph_cluster(clean_147))
            self.assertTrue(_image_has_guthe_record_cover_glyph_cluster(marked_148))

        cut148_prompt = self._runtime_baekje_ep01_cut(payload, 148)
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(cut148_prompt))

    def test_object_empty_background_becomes_full_canvas_support_surface(self):
        compiled = self.compile(
            "Year/period: later archival context; Exact place: archival desk; "
            "Main subject: object-only, exactly one closed blank unmarked manuscript; "
            "Scene: Exactly one closed blank unmarked later source manuscript rests on a plain "
            "archival desk before an empty background with no reenacted ancient event; "
            "Global style: Hard-boiled gritty historical cinematic concept art"
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertNotIn("empty background", compiled.positive)
        self.assertIn(
            "one continuous visibly lit archival desk surface fills every corner and all four canvas edges",
            compiled.positive,
        )
        self.assertIn("straight-down 90-degree overhead full-canvas tabletop crop", compiled.positive)
        for term in (
            "black vignette",
            "visible desk edge",
            "second manuscript",
            "stacked books",
        ):
            self.assertIn(term, compiled.negative)

        retry = compile_image_prompt(
            "Year/period: later archival context; Exact place: archival desk; "
            "Main subject: object-only, exactly one closed blank unmarked manuscript; "
            "Scene: Exactly one closed blank manuscript rests on a plain archival desk; "
            "Global style: Hard-boiled gritty historical cinematic concept art",
            model_id="comfyui-flux2-klein-4b",
            quality_hint=(
                "Straight-down 90-degree object-only crop: one continuous evenly lit warm medium-brown "
                "archival desk fills beyond every edge; exactly one closed blank manuscript rests on it"
            ),
        )
        self.assertIn("Retry correction: Straight-down 90-degree object-only crop", retry.positive)

    def test_genealogy_markers_become_face_down_bare_wood(self):
        compiled = self.compile(
            "Year/period: later archival context; Exact place: archival desk; "
            "Main subject: object-only: exactly two closed blank unmarked genealogy manuscript covers "
            "with two separate groups of plain unlabeled family markers; "
            "Scene: Two closed blank unmarked genealogy manuscript covers rest far apart; each cover "
            "has its own separate group of plain unlabeled family markers; "
            "Material culture: closed blank manuscript covers and plain unlabeled markers; "
            "Global style: Hard-boiled gritty historical cinematic concept art"
        )

        self.assertIn("face-down rectangular wood markers", compiled.positive)
        self.assertIn("uninterrupted bare wood grain", compiled.positive)
        self.assertNotIn("plain unlabeled family markers", compiled.positive)
        self.assertNotIn("second manuscript", compiled.negative)
        for term in ("third manuscript", "letter tile", "glyph tile", "inscribed marker"):
            self.assertIn(term, compiled.negative)

    def test_goguryeo_contract_blocks_anachronistic_props(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Tang; "
            "Main subject: exactly two adult Goguryeo guards; "
            "Scene: Two guards clash beside a timber gate."
        )
        for term in (
            "katana",
            "samurai armor",
            "cruciform sword hilt",
            "European throne",
            "stemmed wine glass",
            "chessboard",
            "European crenellations",
        ):
            self.assertIn(term, compiled.negative)

    def test_snake_contract_locks_one_head_and_continuous_body(self):
        compiled = self.compile(
            "Year/period: 666 AD; Exact place: stone courtyard; "
            "Main subject: exactly one dark snake; "
            "Scene: One snake bites its own tail on cold stone."
        )
        self.assertEqual(compiled.scene_kind, "animal")
        self.assertIn("one continuous snake body", compiled.positive)
        self.assertIn("two-headed snake", compiled.negative)

    def test_people_bowing_to_statue_remains_people_scene(self):
        object_scene = self.compile("A bronze goddess statue stands alone on a stone altar in an ancient temple")
        people_scene = self.compile("Two priests bow before a bronze goddess statue on a stone altar")
        self.assertEqual(object_scene.scene_kind, "object")
        self.assertEqual(people_scene.scene_kind, "pair")

    def test_burning_treaty_routes_to_object_without_doorway_boilerplate(self):
        compiled = self.compile(
            "Year/period: 402-410 AD; Exact place: Liao River northern frontier; "
            "Main subject: one ancient treaty document; "
            "Scene: A beautiful ancient treaty document suddenly bursting into flames; "
            "Scene evidence: blackened rough stone slab, ash, smoke, charred cord."
        )
        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("sealed cord-tied parchment bundle", compiled.positive)
        self.assertNotIn("doorway", compiled.positive.lower())
        self.assertNotIn("hand", compiled.positive.lower())

    def test_displaced_settlement_keeps_families_foreground_and_patrols_distant(self):
        compiled = self.compile(
            "Year/period: 374-375 AD; Exact place: Quadi frontier north of the Danube; "
            "Main subject: Quadi families under Roman pressure; "
            "Scene: Quadi families gather tied cloth bundles beside trampled fields while armed Quadi men "
            "watch distant Roman patrol silhouettes at the horizon; "
            "Scene evidence: pale open sky, smoke haze, crushed grass, muddy footprints, low hide tents."
        )
        self.assertEqual(compiled.scene_kind, "group")
        self.assertIn("Quadi families gather", compiled.positive)
        self.assertIn("distant Roman patrol silhouettes at the horizon", compiled.positive)
        self.assertIn("composition: wide action", compiled.positive.lower())
        self.assertNotIn("doorway", compiled.positive.lower())

    def test_positive_removes_guard_negatives_but_keeps_visible_avoidance_action(self):
        compiled = self.compile(
            "reflection shot in polished metal of a ruler pressing a seal while advisers avoid eye contact; "
            "no text; no subtitles; no logo; no watermark"
        )
        self.assertIn("advisers avoid eye contact", compiled.positive)
        for phrase in ("no text", "no subtitles", "no logo", "no watermark"):
            self.assertNotIn(phrase, compiled.positive.lower())

    def test_flux_style_and_action_survive_bounding(self):
        compiled = self.compile(
            "wide establishing shot of horse riders crossing a vast windy steppe with families and wagons behind them; "
            "ancient historical reconstruction, mythic but grounded, no fantasy monsters; "
            "unique era-accurate foreground cue: linen cloak caught in sea wind; "
            "deep cinematic chiaroscuro; exhausted survival; palette faded fresco colors; 24mm wide lens; "
            "cinematic documentary still, stylish historical atmosphere, realistic textures, clear subject separation, "
            "high detail, dramatic depth, 16:9, no text, no subtitles, no logo, no watermark"
        )
        self.assertIn("Visible action: horse riders crossing", compiled.positive)
        self.assertIn("Style: 2D mature adult historical action cartoon", compiled.positive)
        self.assertLessEqual(len(compiled.positive), 950)

    def test_router_v2_bypasses_legacy_guard_stack_for_comfyui(self):
        source = "one adult envoy kneels before a king in a rough stone hall; no text"
        prepared = _build_image_prompt(
            source,
            "historical documentary illustration",
            image_model="comfyui-flux2-klein-4b",
            prompt_profile=SCENE_CONTRACT_V2,
        )
        self.assertIn(source, prepared)
        self.assertNotIn("TOP-OF-PROMPT", prepared)
        self.assertNotIn("MASTER PROMPT", prepared)

    def test_router_v2_bypasses_legacy_guard_stack_for_local_sdxl(self):
        source = "one adult envoy kneels before a king in a rough stone hall; no text"
        prepared = _build_image_prompt(
            source,
            "historical documentary illustration",
            image_model="comfyui-dreamshaper-xl-longtube",
            prompt_profile=SCENE_CONTRACT_V2,
        )
        self.assertIn(source, prepared)
        self.assertNotIn("TOP-OF-PROMPT", prepared)
        self.assertNotIn("MASTER PROMPT", prepared)

    def test_sdxl_frontloads_action_and_exact_spatial_slots(self):
        compiled = self.compile(
            "Year/period: 378 AD; Exact place: Danube frontier; "
            "Culture scope: Late Roman Danube frontier communities; "
            "Material culture: Late Roman wool tunics, wrapped cloaks, leather belts, fibula brooches, simple leather footwear; "
            "Main subject: exactly four unarmored adult civilians; "
            "Scene: Four adults walk across a trampled field carrying separate cloth bundles at waist height, "
            "all four full bodies visible from head to boots, each person separated by open ground; "
            "Scene evidence: frost, cart ruts, low tents, distant patrol silhouettes.",
            "comfyui-dreamshaper-xl-longtube",
        )
        self.assertLess(compiled.positive.index("Visible action:"), compiled.positive.index("Primary subject:"))
        self.assertLess(compiled.positive.index("Primary subject:"), compiled.positive.index("Composition:"))
        self.assertLess(compiled.positive.index("Composition:"), compiled.positive.index("Historical setting:"))
        self.assertIn("Primary subject: (exactly four unarmored adult civilians:1.50), one quartet", compiled.positive)
        self.assertIn("Prop lock: (exactly four separate tied cloth bundles", compiled.positive)
        self.assertIn("four separated full-body slots: far left, center-left, center-right, far right", compiled.positive)
        self.assertIn("one separate named carried object per foreground adult", compiled.positive)
        self.assertIn("Visible evidence:", compiled.positive)
        self.assertIn("Style: longtubestyle", compiled.positive)
        self.assertIn("five foreground people", compiled.negative)
        self.assertIn("six foreground people", compiled.negative)
        self.assertIn("missing bundle", compiled.negative)
        self.assertLessEqual(len(compiled.positive), 1000)

    def test_corner_signature_detector_ignores_small_dark_ground_blobs(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "ground_texture.png"
            image = Image.new("RGB", (1280, 720), (104, 96, 68))
            draw = ImageDraw.Draw(image)
            draw.ellipse((1205, 650, 1216, 664), fill=(28, 27, 22))
            draw.ellipse((1230, 652, 1245, 665), fill=(24, 23, 20))
            image.save(output)

            self.assertFalse(_image_has_corner_artist_mark(output))

    def test_corner_signature_detector_catches_dense_black_lower_right_glyph(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dense_black_corner_glyph.png"
            image = Image.new("RGB", (1280, 720), (104, 96, 68))
            draw = ImageDraw.Draw(image)
            for line in (
                (1232, 695, 1264, 695),
                (1235, 695, 1235, 713),
                (1244, 695, 1244, 710),
                (1253, 695, 1253, 713),
                (1261, 695, 1261, 710),
                (1232, 701, 1264, 701),
                (1232, 708, 1260, 708),
                (1238, 713, 1256, 713),
            ):
                draw.line(line, fill=(15, 14, 12), width=3)
            image.save(output)

            self.assertTrue(_image_has_corner_artist_mark(output))

    def test_corner_signature_detector_catches_compact_multiline_white_mark(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "compact_white_signature.png"
            image = Image.new("RGB", (1280, 720), (104, 96, 68))
            draw = ImageDraw.Draw(image)
            for x, y in ((1188, 682), (1220, 680), (1248, 678), (1196, 702), (1230, 700), (1256, 698)):
                draw.line((x, y, x + 22, y), fill=(238, 235, 224), width=3)
                draw.line((x + 4, y - 5, x + 4, y + 8), fill=(238, 235, 224), width=3)
            image.save(output)

            self.assertTrue(_image_has_corner_artist_mark(output))

    def test_corner_signature_detector_catches_compact_multiline_lower_left_mark(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "compact_white_lower_left_signature.png"
            image = Image.new("RGB", (1280, 720), (104, 96, 68))
            draw = ImageDraw.Draw(image)
            for x, y in ((10, 682), (42, 680), (70, 678), (18, 702), (52, 700), (78, 698)):
                draw.line((x, y, x + 22, y), fill=(238, 235, 224), width=3)
                draw.line((x + 4, y - 5, x + 4, y + 8), fill=(238, 235, 224), width=3)
            image.save(output)

            self.assertTrue(_image_has_corner_artist_mark(output))

    def test_baekje_bottom_corner_credit_guard_catches_wide_rows_on_both_sides(self):
        from PIL import Image, ImageDraw

        prompts = (
            "Scene: map-like aerial landscape connecting northern Jolbon to the Mahan communities around the Han River basin.",
            "Scene: Soseono, Biryu, and Onjo confer beside packed belongings and lowered household banners before departure.",
            "Scene: families and retainers divide into two groups below Buahak, belongings and banners moving in opposite directions.",
            "Scene: massive rammed-earth walls of Pungnap fortress rise above the river plain, showing organized labor and defense.",
        )
        for prompt in prompts:
            self.assertTrue(is_baekje_ep01_bottom_credit_risk_scene(prompt))

        payload = self._actual_baekje_ep01_script_fixture()
        for cut_number in (10, 42, 70, 109):
            compiled = self.compile(self._runtime_baekje_ep01_cut(payload, cut_number))
            for term in (
                "bottom credit line",
                "lower-left location logo",
                "lower-right location logo",
                "corner calligraphy",
            ):
                self.assertIn(term, compiled.negative)
            if cut_number == 109:
                self.assertIn("long low grass-covered rammed-earth", compiled.positive)
                self.assertIn("reconstructed fortress tower", compiled.negative)

        with tempfile.TemporaryDirectory() as tmp:
            for side in ("left", "right"):
                output = Path(tmp) / f"{side}_credit.png"
                image = Image.new("RGB", (1280, 720), (42, 38, 31))
                draw = ImageDraw.Draw(image)
                origin = 18 if side == "left" else 1135
                for offset in (0, 18, 36, 54, 72, 90):
                    x = origin + offset
                    draw.line((x, 680, x + 10, 680), fill=(226, 222, 210), width=4)
                    draw.line((x + 3, 676, x + 3, 690), fill=(226, 222, 210), width=4)
                image.save(output)
                self.assertTrue(_image_has_wide_bottom_corner_credit_row(output))

    def test_caption_and_corner_detectors_ignore_heads_and_red_cloak_entering_from_below(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_corner_artist_mark

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "heads_and_cloak.png"
            image = Image.new("RGB", (1280, 720), (225, 229, 226))
            draw = ImageDraw.Draw(image)
            draw.ellipse((110, 92, 160, 143), fill=(28, 27, 24))
            draw.ellipse((520, 88, 570, 143), fill=(30, 29, 26))
            draw.rectangle((165, 112, 245, 143), fill=(142, 48, 40))
            draw.rectangle((0, 144, 1279, 719), fill=(108, 100, 74))
            image.save(output)

            self.assertFalse(_image_has_top_caption_like_text(output))
            self.assertFalse(_image_has_corner_artist_mark(output))

    def test_router_v2_leaves_external_api_on_legacy_path(self):
        prompt = _build_image_prompt(
            "one adult queen turns toward a cracked crown in a timber command tent; no text",
            "cinematic historical documentary",
            image_model="openai-image-2",
            prompt_profile=SCENE_CONTRACT_V2,
        )
        self.assertIn("TOP-OF-PROMPT", prompt)
        self.assertNotIn("Visible action:", prompt)
        self.assertNotIn("exactly five digits", prompt)
        self.assertNotIn("one thumb and four fingers", prompt)

    def test_comfyui_submission_uses_bounded_v2_prompts(self):
        async def write_output(_entry, output_path, **_kwargs):
            from PIL import Image

            Image.new("RGB", (64, 36), (120, 120, 120)).save(output_path)

        service = ComfyUIImageService("comfyui-flux2-klein-4b")
        service.prompt_profile = SCENE_CONTRACT_V2
        source = (
            "wide shot of two envoys arguing across a timber table in a medieval royal hall; "
            "sealed parchment bundles and candlelight; no text, no watermark"
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "cut.png")
            patches = (
                patch("app.services.image.comfyui_service.comfyui_client.system_stats", new=AsyncMock(return_value={})),
                patch("app.services.image.comfyui_service.comfyui_client.submit", new=AsyncMock(return_value="prompt-id")),
                patch(
                    "app.services.image.comfyui_service.comfyui_client.wait_for",
                    new=AsyncMock(
                        return_value={
                            "outputs": {
                                "33": {"ui": {"text": ["2"]}},
                                "37": {"ui": {"text": ["2"]}},
                            }
                        }
                    ),
                ),
                patch("app.services.image.comfyui_service.comfyui_client.download_first_output", new=AsyncMock(side_effect=write_output)),
                patch("app.services.image.comfyui_service.comfyui_client.execution_seconds", return_value=None),
                patch("app.services.image.comfyui_service.comfyui_client.cached_node_count", return_value=0),
                patch("app.services.image.comfyui_service.comfyui_client.new_client_id", return_value="client-id"),
                patch("app.services.image.comfyui_service._image_has_solid_light_outer_margin", return_value=False),
                patch("app.services.image.comfyui_service._image_has_solid_dark_outer_frame", return_value=False),
                patch("app.services.image.comfyui_service._image_has_horizontal_letterbox_bars", return_value=False),
                patch("app.services.image.comfyui_service._image_has_top_caption_like_text", return_value=False),
                patch("app.services.image.comfyui_service._image_has_internal_text_like_marks", return_value=False),
                patch("app.services.image.comfyui_service._image_has_inset_dark_rectangular_frame", return_value=False),
                patch("app.services.image.comfyui_service._image_has_split_panel_divider", return_value=False),
                patch("app.services.image.comfyui_service._image_has_corner_artist_mark", return_value=False),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], patches[12], patches[13], patches[14]:
                import asyncio

                asyncio.run(service.generate(source, 1280, 720, output))
            self.assertTrue(Path(output).exists())
        self.assertLessEqual(len(service.last_positive_prompt), 950)
        self.assertLessEqual(len(service.last_negative_prompt), 520)
        self.assertIn("Visible action:", service.last_positive_prompt)
        self.assertIn("natural head-neck-shoulder alignment", service.last_positive_prompt)
        self.assertNotIn("Visible action: wide shot", service.last_positive_prompt)
        self.assertNotIn("TOP-OF-PROMPT", service.last_positive_prompt)
        self.assertNotIn("MASTER PROMPT", service.last_positive_prompt)

    def test_internal_text_post_qa_is_removed_from_generation(self):
        async def write_output(_entry, output_path, **_kwargs):
            from PIL import Image

            Image.new("RGB", (64, 36), (120, 120, 120)).save(output_path)

        service = ComfyUIImageService("comfyui-flux2-klein-4b")
        service.prompt_profile = SCENE_CONTRACT_V2
        source = (
            "Onjo's disguised hunting force turns toward the Mahan center while the image "
            "transitions into an ancient northern origin landscape. Ancient Korean historical "
            "drama, realistic people, clear staging, no readable text."
        )
        download = AsyncMock(side_effect=write_output)
        internal_text = patch(
            "app.services.image.comfyui_service._image_has_internal_text_like_marks",
            side_effect=(True, False),
        )
        with tempfile.TemporaryDirectory() as tmp:
            output = str(Path(tmp) / "cut.png")
            with (
                patch("app.services.image.comfyui_service.comfyui_client.system_stats", new=AsyncMock(return_value={})),
                patch("app.services.image.comfyui_service.comfyui_client.submit", new=AsyncMock(return_value="prompt-id")) as submit,
                patch(
                    "app.services.image.comfyui_service.comfyui_client.wait_for",
                    new=AsyncMock(return_value={"outputs": {}}),
                ),
                patch("app.services.image.comfyui_service.comfyui_client.download_first_output", new=download),
                patch("app.services.image.comfyui_service.comfyui_client.execution_seconds", return_value=None),
                patch("app.services.image.comfyui_service.comfyui_client.cached_node_count", return_value=0),
                patch("app.services.image.comfyui_service.comfyui_client.new_client_id", return_value="client-id"),
                patch("app.services.image.comfyui_service._image_has_solid_light_outer_margin", return_value=False),
                patch("app.services.image.comfyui_service._image_has_solid_dark_outer_frame", return_value=False),
                patch("app.services.image.comfyui_service._image_has_horizontal_letterbox_bars", return_value=False),
                patch("app.services.image.comfyui_service._image_has_top_caption_like_text", return_value=False),
                internal_text as internal_text_detector,
                patch("app.services.image.comfyui_service._image_has_inset_dark_rectangular_frame", return_value=False),
                patch("app.services.image.comfyui_service._image_has_split_panel_divider", return_value=False),
                patch("app.services.image.comfyui_service._image_has_corner_artist_mark", return_value=False),
            ):
                import asyncio

                asyncio.run(service.generate(source, 1280, 720, output))

        self.assertEqual(submit.await_count, 1)
        self.assertEqual(download.await_count, 1)
        self.assertEqual(internal_text_detector.call_count, 0)
        self.assertNotIn("surface continuity", service.last_positive_prompt)
        self.assertNotIn("small glyph-like clusters", service.last_positive_prompt)

    def test_top_caption_detector_ignores_two_head_silhouettes_against_bright_sky(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "two_heads.png"
            image = Image.new("RGB", (1280, 720), (232, 234, 226))
            draw = ImageDraw.Draw(image)
            draw.ellipse((120, 24, 250, 132), fill=(24, 23, 21))
            draw.ellipse((920, 20, 1050, 128), fill=(28, 27, 24))
            draw.rectangle((0, 144, 1279, 719), fill=(105, 94, 78))
            image.save(output)

            self.assertFalse(_image_has_top_caption_like_text(output))

    def test_top_caption_detector_catches_large_dark_header_glyph_row(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "large_header.png"
            image = Image.new("RGB", (1280, 720), (232, 234, 226))
            draw = ImageDraw.Draw(image)
            for index in range(5):
                left = 350 + index * 60
                draw.rectangle((left, 22, left + 34, 58), fill=(18, 18, 18))
                draw.rectangle((left + 9, 30, left + 25, 50), fill=(232, 234, 226))
            draw.rectangle((0, 150, 1279, 719), fill=(105, 94, 78))
            image.save(output)

            self.assertTrue(_image_has_top_caption_like_text(output))

    def test_internal_text_detector_catches_five_large_marks_on_upper_banner(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "large_banner_marks.png"
            image = Image.new("RGB", (1280, 720), (98, 87, 72))
            draw = ImageDraw.Draw(image)
            banner_color = (214, 190, 145)
            draw.rectangle((780, 80, 1210, 310), fill=banner_color)
            for index in range(5):
                left = 880 + index * 50
                top = 200 - index * 12
                draw.rectangle((left, top, left + 36, top + 54), fill=(24, 23, 20))
                draw.rectangle(
                    (left + 9, top + 9, left + 27, top + 43),
                    fill=banner_color,
                )
            image.save(output)

            self.assertTrue(_image_has_internal_text_like_marks(output))

    def test_large_glyph_row_detector_ignores_five_heads_and_thin_landscape_lines(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            heads = Path(tmp) / "five_heads.png"
            lines = Path(tmp) / "thin_landscape_lines.png"

            head_image = Image.new("RGB", (1280, 720), (232, 234, 226))
            head_draw = ImageDraw.Draw(head_image)
            for index in range(5):
                left = 300 + index * 120
                head_draw.ellipse((left, 30, left + 50, 84), fill=(20, 20, 20))
            head_draw.rectangle((0, 150, 1279, 719), fill=(105, 94, 78))
            head_image.save(heads)

            line_image = Image.new("RGB", (1280, 720), (232, 234, 226))
            line_draw = ImageDraw.Draw(line_image)
            for index in range(5):
                left = 350 + index * 80
                line_draw.line((left, 20, left + 40, 90), fill=(20, 20, 20), width=3)
            line_draw.rectangle((0, 150, 1279, 719), fill=(105, 94, 78))
            line_image.save(lines)

            for path in (heads, lines):
                with self.subTest(path=path.name):
                    self.assertFalse(_image_has_top_caption_like_text(path))
                    self.assertFalse(_image_has_internal_text_like_marks(path))

    def test_panorama_banner_detector_distinguishes_glyph_cluster_from_roof_and_folds(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            marked = Path(tmp) / "marked_cloth.png"
            folded = Path(tmp) / "folded_cloth.png"

            for output, add_marks in ((marked, True), (folded, False)):
                image = Image.new("RGB", (640, 360), (112, 94, 70))
                draw = ImageDraw.Draw(image)
                draw.polygon(
                    ((20, 165), (245, 95), (315, 190), (5, 215)),
                    fill=(143, 116, 77),
                )
                draw.line((25, 145, 315, 145), fill=(68, 54, 39), width=3)
                for x in range(35, 285, 22):
                    draw.line((x, 145, x + 45, 190), fill=(68, 54, 39), width=3)
                draw.polygon(
                    ((300, 235), (575, 245), (555, 330), (285, 320)),
                    fill=(218, 193, 151),
                )
                if add_marks:
                    for x in (335, 405, 475):
                        draw.rectangle((x, 270, x + 24, 298), outline=(35, 29, 23), width=3)
                        draw.line((x + 12, 274, x + 12, 294), fill=(35, 29, 23), width=3)
                        draw.line((x + 5, 284, x + 19, 284), fill=(35, 29, 23), width=3)
                else:
                    draw.arc((315, 260, 440, 310), 190, 350, fill=(82, 67, 50), width=3)
                    draw.arc((430, 270, 545, 315), 190, 350, fill=(82, 67, 50), width=3)
                image.save(output)

            self.assertTrue(
                _image_has_internal_text_like_marks(marked, panorama_banner_only=True)
            )
            self.assertFalse(
                _image_has_internal_text_like_marks(folded, panorama_banner_only=True)
            )

    def test_actual_baekje_cut2_attempt_labels_match_panorama_detector_when_fixtures_exist(self):
        fixture_dir = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_diagnostics"
            r"\cut2_rejected_attempts_20260715_0133"
        )
        fixtures = tuple(fixture_dir / f"attempt_{index}.png" for index in range(1, 5))
        if not all(path.is_file() for path in fixtures):
            self.skipTest("actual Baekje cut2 attempt fixtures are not present")

        for path, expected in zip(fixtures, (False, True, True, False)):
            with self.subTest(path=path.name):
                self.assertEqual(
                    _image_has_internal_text_like_marks(
                        path,
                        panorama_banner_only=True,
                    ),
                    expected,
                )

    def test_actual_baekje_cut2_banner_text_is_rejected_when_fixture_exists(self):
        output = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_rejected"
            r"\text_detector_smoke_fail_20260715_0121\cut_2.png"
        )
        sidecar = output.with_name(output.name + ".prompt.json")
        if not output.is_file() or not sidecar.is_file():
            self.skipTest("actual Baekje cut2 fixture is not present")

        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertTrue(
            _image_has_internal_text_like_marks(output, panorama_banner_only=True)
        )
        self.assertTrue(
            _should_use_continuous_montage_banner_text_detector(
                payload["comfyui_positive_prompt"]
            )
        )
        self.assertTrue(
            _should_check_internal_text_after_generation(payload["comfyui_positive_prompt"])
        )

    def test_actual_baekje_cut6_top_caption_is_rejected_when_fixture_exists(self):
        output = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_rejected"
            r"\text_detector_smoke_fail_20260715_0121\cut_6.png"
        )
        sidecar = output.with_name(output.name + ".prompt.json")
        if not output.is_file() or not sidecar.is_file():
            self.skipTest("actual Baekje cut6 fixture is not present")

        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        self.assertTrue(_image_has_top_caption_like_text(output))
        self.assertTrue(
            _should_check_internal_text_after_generation(payload["comfyui_positive_prompt"])
        )

    def test_actual_baekje_cut41_gate_texture_is_not_internal_text_when_fixture_exists(self):
        output = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_review\images"
            r"\cut_41__needs_review__컷_41_150_내부_문서_벽면_글자_표식_감지_재시도_3회_후_실패.png"
        )
        if not output.is_file():
            self.skipTest("actual Baekje cut41 fixture is not present")

        self.assertFalse(_image_has_internal_text_like_marks(output))

    def test_actual_baekje_cut48_horizon_is_not_top_caption_when_fixture_exists(self):
        output = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_review\images"
            r"\cut_48__needs_review__컷_48_150_상단_캡션_텍스트_감지_재시도_2회_후_실패.png"
        )
        if not output.is_file():
            self.skipTest("actual Baekje cut48 fixture is not present")

        self.assertFalse(_image_has_top_caption_like_text(output))

    def test_actual_baekje_cut94_thatch_is_not_top_caption_when_fixture_exists(self):
        output = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa\qa_review\images"
            r"\cut_94__needs_review__컷_94_150_상단_캡션_텍스트_감지_재시도_2회_후_실패.png"
        )
        if not output.is_file():
            self.skipTest("actual Baekje cut94 fixture is not present")

        self.assertFalse(_image_has_top_caption_like_text(output))

    def test_split_panel_detector_scope_excludes_plain_petition_packet_scene(self):
        self.assertFalse(
            _should_check_split_panel_after_generation(
                "one envoy bows with a closed blank cloth petition packet in a timber hall"
            )
        )
        self.assertTrue(
            _should_check_split_panel_after_generation(
                "a framed painting burns while a mirror reflects the old ruler"
            )
        )

    def test_split_panel_detector_catches_bright_full_height_center_divider(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "bright_split.png"
            image = Image.new("RGB", (1280, 720), (72, 61, 48))
            draw = ImageDraw.Draw(image)
            draw.rectangle((635, 0, 647, 719), fill=(255, 255, 255))
            image.save(output)
            self.assertTrue(_image_has_split_panel_divider(output))

    def test_split_panel_detector_catches_dark_full_height_center_divider(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dark_split.png"
            image = Image.new("RGB", (1280, 720), (118, 91, 66))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 633, 719), fill=(88, 68, 52))
            draw.rectangle((646, 0, 1279, 719), fill=(126, 101, 78))
            draw.rectangle((634, 0, 645, 719), fill=(4, 4, 4))
            image.save(output)
            self.assertTrue(_image_has_split_panel_divider(output))

    def test_split_panel_detector_catches_bright_center_divider_above_shared_table(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "partial_bright_split.png"
            image = Image.new("RGB", (1280, 720), (102, 78, 58))
            draw = ImageDraw.Draw(image)
            draw.rectangle((646, 0, 1279, 530), fill=(150, 119, 86))
            draw.rectangle((635, 0, 645, 530), fill=(255, 255, 255))
            draw.rectangle((0, 531, 1279, 719), fill=(68, 47, 35))
            image.save(output)
            self.assertTrue(_image_has_split_panel_divider(output, include_inset=False))

    def test_internal_text_detector_catches_large_pseudo_glyph_cluster(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "large_pseudo_glyphs.png"
            image = Image.new("RGB", (1280, 720), (70, 58, 47))
            draw = ImageDraw.Draw(image)
            draw.rectangle((280, 100, 1000, 620), fill=(188, 154, 108))
            for x in (420, 610, 800):
                draw.line((x, 235, x + 48, 330), fill=(28, 24, 20), width=16)
                draw.line((x + 48, 235, x, 330), fill=(28, 24, 20), width=16)
                draw.line((x - 3, 282, x + 51, 282), fill=(28, 24, 20), width=14)
            image.save(output)
            self.assertTrue(_image_has_internal_text_like_marks(output))

    def test_internal_text_detector_ignores_upper_gate_branch_texture(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "gate_branches.png"
            image = Image.new("RGB", (1280, 720), (220, 222, 214))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 220, 185), fill=(54, 49, 40))
            draw.rectangle((1010, 0, 1279, 210), fill=(48, 43, 36))
            draw.rectangle((300, 20, 980, 74), fill=(45, 40, 34))
            draw.rectangle((390, 20, 445, 235), fill=(45, 40, 34))
            draw.rectangle((835, 20, 890, 235), fill=(45, 40, 34))
            for index in range(28):
                x = 930 + (index * 37) % 330
                y = (index * 19) % 155
                draw.line((x, y, x + 70, y - 35), fill=(35, 32, 27), width=5)
            image.save(output)

            self.assertFalse(_image_has_internal_text_like_marks(output))

    def test_historical_scene_protects_against_power_lines(self):
        compiled = self.compile(
            "Year/period: Late 1st century BC; Exact place: plain timber village gate; "
            "Culture scope: Goguryeo, Mahan, and Baekje; "
            "Main subject: exactly three adults leaving the settlement; "
            "Scene: Three adults walk beneath one rough timber gate and thatch roofs"
        )

        for term in (
            "utility pole",
            "power line",
            "overhead electrical wire",
            "modern fedora",
            "baseball cap",
        ):
            self.assertIn(term, compiled.negative)

    def test_internal_text_detector_catches_small_grid_glyphs_on_tally(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "small_tally_glyphs.png"
            image = Image.new("RGB", (1280, 720), (72, 62, 50))
            draw = ImageDraw.Draw(image)
            draw.rectangle((550, 280, 750, 440), fill=(178, 151, 104), outline=(35, 30, 24), width=8)
            for x in range(590, 731, 35):
                draw.line((x, 290, x, 430), fill=(45, 38, 30), width=4)
            for y in range(320, 421, 30):
                draw.line((560, y, 740, y), fill=(45, 38, 30), width=4)
            for row, y in enumerate((302, 332, 362, 392)):
                for col, x in enumerate((570, 605, 640, 675, 710)):
                    draw.line((x, y, x + 7, y + 8), fill=(30, 26, 22), width=2)
                    draw.line((x + 7, y + 8, x + 11, y + (2 if (row + col) % 2 else 5)), fill=(30, 26, 22), width=2)
            image.save(output)

            self.assertTrue(_image_has_internal_text_like_marks(output))

    def test_internal_text_detector_catches_dim_framed_wall_calligraphy(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "dim_framed_calligraphy.png"
            plain = Path(tmp) / "plain_framed_panel.png"
            for path, with_glyphs in ((output, True), (plain, False)):
                image = Image.new("RGB", (1280, 720), (48, 42, 36))
                draw = ImageDraw.Draw(image)
                draw.rectangle((674, 16, 818, 224), fill=(88, 84, 78), outline=(24, 24, 23), width=8)
                if with_glyphs:
                    draw.line((742, 66, 760, 84), fill=(18, 18, 18), width=7)
                    draw.line((760, 66, 742, 84), fill=(18, 18, 18), width=7)
                    draw.line((742, 104, 762, 124), fill=(18, 18, 18), width=7)
                    draw.line((762, 104, 742, 124), fill=(18, 18, 18), width=7)
                    for y in (72, 96, 120, 144):
                        draw.line((708, y, 708, y + 13), fill=(22, 22, 22), width=5)
                    for y in (154, 172, 190):
                        draw.line((724, y, 742, y), fill=(22, 22, 22), width=5)
                image.save(path)

            self.assertTrue(_image_has_internal_text_like_marks(output))
            self.assertFalse(_image_has_internal_text_like_marks(plain))

    def test_internal_text_detector_catches_multiple_upper_registry_placards(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "upper_registry_placards.png"
            image = Image.new("RGB", (1280, 720), (58, 48, 40))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 1279, 180), fill=(156, 142, 118))
            for index in range(12):
                x = 30 + index * 100
                draw.line((x, 24, x + 32, 54), fill=(24, 22, 20), width=9)
                draw.line((x + 32, 24, x, 54), fill=(24, 22, 20), width=9)
            image.save(output)

            self.assertTrue(_image_has_internal_text_like_marks(output))

    def test_registry_seal_gate_catches_multiple_top_clipped_light_panels(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "two_registry_panels.png"
            single = Path(tmp) / "single_registry_panel.png"
            for path, panel_count in ((output, 2), (single, 1)):
                image = Image.new("RGB", (1280, 720), (70, 52, 44))
                draw = ImageDraw.Draw(image)
                for index in range(panel_count):
                    left = 430 + index * 300
                    draw.rectangle((left, 0, left + 150, 210), fill=(170, 158, 132), outline=(24, 22, 20), width=10)
                image.save(path)

            prompt = "Primary subject: exactly two low flat bronze stamp seals on a bare timber tabletop."
            self.assertTrue(_should_check_registry_seal_background_panels(prompt))
            self.assertTrue(_image_has_multiple_upper_light_panels(output))
            self.assertFalse(_image_has_multiple_upper_light_panels(single))

    def test_secret_route_gate_catches_multiple_edge_light_panels(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "two_edge_panels.png"
            single = Path(tmp) / "single_edge_panel.png"
            for path, panel_count in ((output, 2), (single, 1)):
                image = Image.new("RGB", (1280, 720), (54, 44, 38))
                draw = ImageDraw.Draw(image)
                positions = ((20, 130, 160, 390), (1120, 180, 1260, 440))
                for left, top, right, bottom in positions[:panel_count]:
                    draw.rectangle((left, top, right, bottom), fill=(220, 206, 174), outline=(20, 18, 17), width=10)
                    for offset in (55, 115, 175):
                        draw.line((left + 42, top + offset, right - 42, top + offset + 25), fill=(24, 22, 20), width=8)
                        draw.line((right - 42, top + offset, left + 42, top + offset + 25), fill=(24, 22, 20), width=8)
                image.save(path)

            prompt = (
                "Primary subject: one red route cord between one grey Goguryeo sash and one black Tang sash; "
                "Scene: exactly three separate smooth grey oval stones in one row."
            )
            self.assertTrue(_should_check_secret_route_edge_panels(prompt))
            self.assertTrue(_image_has_multiple_edge_light_panels(output))
            self.assertFalse(_image_has_multiple_edge_light_panels(single))

    def test_stone_counter_handles_three_six_and_seven_markers_and_ignores_rectangular_sash(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            three_path = Path(tmp) / "three_stones.png"
            split_three_path = Path(tmp) / "three_stones_split_by_cord.png"
            touching_sash_path = Path(tmp) / "three_stones_left_marker_touches_sash.png"
            six_path = Path(tmp) / "six_stones.png"
            seven_path = Path(tmp) / "seven_stones.png"
            for path, count in ((three_path, 3), (six_path, 6), (seven_path, 7)):
                image = Image.new("RGB", (1280, 720), (74, 58, 46))
                draw = ImageDraw.Draw(image)
                draw.rectangle((10, 55, 160, 185), fill=(132, 132, 132))
                for index in range(count):
                    left = 45 + index * 170
                    draw.ellipse((left, 300, left + 120, 390), fill=(142, 144, 145), outline=(22, 22, 22), width=8)
                image.save(path)

            split_three = Image.new("RGB", (1280, 720), (74, 58, 46))
            split_draw = ImageDraw.Draw(split_three)
            split_draw.rectangle((10, 55, 160, 185), fill=(132, 132, 132))
            for index in range(3):
                left = 280 + index * 190
                split_draw.ellipse((left, 285, left + 120, 405), fill=(142, 144, 145), outline=(22, 22, 22), width=8)
            split_draw.line((250, 345, 900, 345), fill=(190, 22, 32), width=18)
            split_three.save(split_three_path)

            touching_sash = Image.new("RGB", (1280, 720), (74, 58, 46))
            touching_draw = ImageDraw.Draw(touching_sash)
            for index in range(3):
                left = 320 + index * 220
                touching_draw.ellipse((left, 270, left + 150, 420), fill=(142, 144, 145), outline=(22, 22, 22), width=8)
            touching_draw.rectangle((40, 355, 340, 420), fill=(142, 144, 145))
            touching_draw.rectangle((930, 290, 1190, 400), fill=(18, 18, 18))
            touching_draw.line((250, 345, 1080, 345), fill=(190, 22, 32), width=18)
            touching_sash.save(touching_sash_path)

            self.assertEqual(_image_grey_stone_marker_count(three_path), 3)
            self.assertEqual(_image_grey_stone_marker_count(split_three_path), 3)
            self.assertEqual(_image_grey_stone_marker_count(touching_sash_path), 3)
            self.assertEqual(_image_grey_stone_marker_count(six_path), 6)
            self.assertEqual(_image_grey_stone_marker_count(seven_path), 7)

    def test_dark_frame_detector_catches_four_corner_vignette(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            vignette_path = Path(tmp) / "corner_vignette.png"
            ground_path = Path(tmp) / "dark_ground_only.png"

            vignette = Image.new("RGB", (1280, 720), (188, 194, 181))
            draw = ImageDraw.Draw(vignette)
            draw.polygon(((0, 0), (150, 0), (0, 125)), fill=(2, 2, 2))
            draw.polygon(((1279, 0), (1129, 0), (1279, 125)), fill=(2, 2, 2))
            draw.polygon(((0, 719), (150, 719), (0, 594)), fill=(2, 2, 2))
            draw.polygon(((1279, 719), (1129, 719), (1279, 594)), fill=(2, 2, 2))
            vignette.save(vignette_path)

            ground = Image.new("RGB", (1280, 720), (188, 194, 181))
            ImageDraw.Draw(ground).rectangle((0, 560, 1279, 719), fill=(12, 12, 12))
            ground.save(ground_path)

            self.assertTrue(_image_has_solid_dark_outer_frame(vignette_path))
            self.assertFalse(_image_has_solid_dark_outer_frame(ground_path))

    def test_dark_frame_detector_ignores_textured_hardboiled_scene_corners(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "textured_corners.png"
            image = Image.new("RGB", (1280, 720), (145, 138, 120))
            draw = ImageDraw.Draw(image)
            corners = (
                ((0, 0), (180, 0), (0, 150)),
                ((1279, 0), (1099, 0), (1279, 150)),
                ((0, 719), (180, 719), (0, 569)),
                ((1279, 719), (1099, 719), (1279, 569)),
            )
            for points in corners:
                draw.polygon(points, fill=(8, 8, 8))
            for offset in range(0, 140, 8):
                shade = 2 if (offset // 8) % 2 == 0 else 18
                draw.line((0, offset, 150 - offset, 0), fill=(shade, shade, shade), width=3)
                draw.line((1279, offset, 1129 + offset, 0), fill=(shade, shade, shade), width=3)
                draw.line((0, 719 - offset, 150 - offset, 719), fill=(shade, shade, shade), width=3)
                draw.line((1279, 719 - offset, 1129 + offset, 719), fill=(shade, shade, shade), width=3)
            image.save(path)

            self.assertFalse(_image_has_solid_dark_outer_frame(path))

    def test_dark_frame_detector_catches_three_sided_rounded_border(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            framed_path = Path(tmp) / "rounded_outer_border.png"
            image = Image.new("RGB", (1280, 720), (226, 220, 205))
            draw = ImageDraw.Draw(image)
            draw.rectangle((0, 0, 4, 719), fill=(4, 4, 4))
            draw.rectangle((1275, 0, 1279, 719), fill=(4, 4, 4))
            draw.rectangle((0, 715, 1279, 719), fill=(4, 4, 4))
            draw.rectangle((250, 0, 1030, 4), fill=(4, 4, 4))
            image.save(framed_path)

            self.assertTrue(_image_has_solid_dark_outer_frame(framed_path))

    def test_object_only_tallies_enable_internal_text_check(self):
        self.assertTrue(
            _should_check_internal_text_after_generation(
                "Main subject: exactly six tally blocks; "
                "Scene: Object-only overhead view of six plain hardwood tally blocks."
            )
        )

    def test_ep30_gate_assault_keeps_action_and_loadout_after_compilation(self):
        normalized = normalize_cut_image_prompt(
            (
                "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
                "Main subject: historical subject; Scene: historical scene"
            ),
            "성문이 열리자 밖에서 대기하던 당나라 정예병이 쏟아집니다.",
            "668 AD Goguryeo succession crisis",
        )
        compiled = self.compile(normalized)

        self.assertEqual(compiled.person_count, 2)
        for required in (
            "windowless Pyongyang north-gate",
            "Left Tang shield-bearer braces one oval timber shield with both hands",
            "right Tang spear-bearer grips one upright straight spear with both hands",
            "fitted iron lamellar",
            "firelit gap",
            "blank vertical gate planks",
        ):
            with self.subTest(required=required):
                self.assertIn(required, compiled.positive)
        self.assertFalse(_should_use_reduced_internal_text_detector(compiled.positive))

    def test_ep30_failed_cut_scenes_compile_to_concrete_contracts(self):
        base_prompt = (
            "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
            "Style: serious adult graphic novel illustration, bold black ink outlines; "
            "Main subject: historical subject; Scene: historical scene"
        )
        cases = (
            (
                "성 안으로 쏟아진 당나라 군대는 자비 없이 도살을 시작하죠.",
                3,
                "group",
                ("two standing Tang infantry", "one prone Goguryeo defender", "blank charred wall"),
                ("burning Pyongyang street",),
            ),
            (
                "화려한 문화를 꽃피웠던 평양성은 철저하게 약탈당하고 파괴되죠.",
                None,
                "object",
                ("exactly one thin flat round bronze mirror disk", "one deep jagged crack runs continuously", "top rim through center to bottom rim"),
                ("scroll",),
            ),
            (
                "영광스러운 고구려의 역사는 이렇게 피비린내 속에 막을 내리죠.",
                None,
                "object",
                ("blank Goguryeo war banner", "dark-red rain mud"),
                ("painting",),
            ),
            (
                "지도층이 탐욕에 눈이 멀자, 국가는 안에서부터 썩어 문드러졌죠.",
                None,
                "object",
                ("one plain unglazed Goguryeo grain jar ruptured open by black-green rot", "one jagged front rupture exposes black-green mold", "clumped spoiled millet"),
                ("normal dry seeds",),
            ),
            (
                "강대국의 무자비한 침략보다 무서운 것이 내부의 분열과 배신이죠.",
                1,
                "single",
                ("one severed rope at lower right", "split shield stays left of his torso"),
                ("converging spear shadows",),
            ),
            (
                "국가를 장기말처럼 버린 지배층의 비열하고 끔찍한 이기심 말입니다.",
                None,
                "object",
                ("discarded cracked Goguryeo fortress tally", "exactly two matching flat solid rectangular bronze belt plaques", "closed faces and no holes"),
                ("chessboard", "stone slab"),
            ),
            (
                "권력자의 오만이 힘없는 백성을 처참한 핏빛 생지옥으로 밀어 넣었죠.",
                3,
                "group",
                ("separated left, center and right depth slots", "blank collapsed timber wall", "two connected legs"),
                ("clean intact room", "white floor"),
            ),
            (
                "권력이라는 괴물에게 삼켜진 제국의 처참한 최후를 깊이 새겨야 합니다.",
                None,
                "object",
                ("empty Goguryeo ruler seat", "fallen mortised roof beam"),
                ("dragon",),
            ),
            (
                "무너진 평양성 잔해 밑에는 이름 없는 자들의 피눈물이 서려 있죠.",
                None,
                "object",
                ("three empty segmented Goguryeo iron cap helmets", "radial plate seams", "riveted brow band"),
                ("modern steel bowl helmet",),
            ),
            (
                "권력의 체스판 위에서 백성들은 무참히 버려지는 소모품이었습니다.",
                None,
                "object",
                ("three shallow empty clay grain bowls", "rests across all three broken rims", "smoke-dark packed earth"),
                ("eggs", "white background"),
            ),
            (
                "패자는 흔적도 못 남기고 오직 강자만 살아남는 핏빛 세계입니다.",
                None,
                "object",
                ("soft wrinkled plain-hemp pouch", "puckered mouth", "more than half has collapsed into grey ash", "one short thin cut drawcord"),
                ("white background", "sealed pouch"),
            ),
            (
                "승자의 기록 속에 숨은 패자의 핏물을 차갑게 읽어내야만 합니다.",
                1,
                "single",
                ("fitted Tang iron lamellar", "conical iron helmet", "right wrapped boot presses the bundle center", "both empty hands stay behind his back"),
                ("inscription", "bronze plaque"),
            ),
            (
                "진실을 마주할 각오가 섰다면 핏빛 체스판에서 눈을 떼지 마십시오.",
                1,
                "single",
                ("weathered East Asian face", "exactly two visible empty hands", "tight centered frontal crop"),
                ("corpse", "shield", "spear"),
            ),
            (
                "낡은 위인전을 찢어버린 날 것 그대로의 잔혹한 생존기였습니다.",
                None,
                "object",
                ("exactly three separated face-down blank hardwood heroic record slips", "zero cord or rope", "one lower corner is clearly blackened and missing"),
                ("intact tied bundle", "large rocks"),
            ),
            (
                "역사의 차가운 메스는 앞으로도 권력의 환상을 도려낼 것입니다.",
                None,
                "object",
                ("single-edged iron knife", "one separate red cord half lies left", "two frayed cut ends face each other without touching"),
                ("multiple red cords", "rope knot around blade"),
            ),
        )

        for narration, person_count, scene_kind, required, forbidden in cases:
            with self.subTest(narration=narration):
                normalized = normalize_cut_image_prompt(
                    base_prompt,
                    narration,
                    "668 AD Goguryeo succession crisis",
                )
                compiled = self.compile(normalized)
                self.assertEqual(compiled.scene_kind, scene_kind)
                if person_count is not None:
                    self.assertEqual(compiled.person_count, person_count)
                for token in required:
                    self.assertIn(token, compiled.positive)
                for token in forbidden:
                    self.assertNotIn(token, compiled.positive)

    def test_ep30_runtime_title_routes_initial_regen_failures_to_exact_contracts(self):
        base_prompt = (
            "Year/period: 668year 9; Exact place: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; "
            "Material culture: iron weapons, bows, leather or lamellar armor, hemp garments, "
            "wooden halls, fortress walls; Main subject: historical subject; Scene: historical scene"
        )
        runtime_context = (
            "안에서 열린 성문, 700년 제국의 몰락 EP.30 "
            "안에서 열린 성문, 700년 제국의 몰락"
        )
        cases = (
            (
                "조국의 기밀을 팔아넘긴 연개소문의 맏아들 남생입니다.",
                None,
                "object",
                (
                    "straight-down object-only close-up",
                    "exactly one palm-sized thin flat warm-brown wood tally",
                    "diagonally at center as the sole object",
                    "continuous rough dark timber plank grain fills every edge",
                    "without any inset panel or base",
                ),
                (
                    "person",
                    "face",
                    "hand",
                    "helmet",
                    "extra tally",
                ),
            ),
            (
                "당나라 황제는 평양성을 부수기 위해 모든 힘을 쏟아붓죠.",
                1,
                "single",
                (
                    "black futou covers Gaozong's hair",
                    "solid unmarked earth relief with raised walls and recessed roads",
                    "blank windowless plaster fill the frame",
                ),
                (
                    "bare topknot on Gaozong",
                    "missing Gaozong futou",
                    "missing relief model",
                    "flat map",
                    "written map labels",
                    "calligraphy panel",
                    "lattice window",
                ),
            ),
            (
                "그는 빗발치는 화살 속에서도 직접 성벽을 오가며 지휘했죠.",
                1,
                "single",
                (
                    "Namgeon runs right",
                    "exactly three arrows are embedded arrowhead-first",
                    "only three straight shafts and one rear fletching set per shaft visible",
                    "no arrows in sky",
                ),
                (
                    "flying arrow",
                    "arrow in sky",
                    "extra arrow",
                    "double-ended arrow",
                    "arrow crossing torso",
                ),
            ),
            (
                "고구려 군민들은 최후의 순간까지 처절하게 활시위를 당겼죠.",
                1,
                "single",
                (
                    "waist-up side-profile archer",
                    "bow arm extends exactly one recurved bow",
                    "empty rear hand opens beside his cheek",
                    "empty bowstring snaps forward",
                    "exactly two visible hands",
                    "zero visible projectiles",
                    "fitted Goguryeo lamellar, segmented cap",
                ),
                ("visible arrow", "arrow shaft", "fletching", "quiver", "second bow"),
            ),
            (
                "국운이 완전히 기울었다고 판단한 신성은 음모를 꾸밉니다.",
                None,
                "object",
                (
                    "straight-down object-only close-up",
                    "one small beige tied cloth pouch is one-quarter the folded robe's width",
                    "one broad undyed hemp sash passes in front and covers the pouch's lower half",
                    "one folded monastic robe",
                    "warm medium-brown timber fills every edge",
                ),
                ("black outer frame", "room interior", "window", "person", "hand", "wood tablet", "pouch on top of sash"),
            ),
            (
                "살기 위해 조국을 버리고 적장 이세적과 은밀히 내통한 거죠.",
                2,
                "pair",
                (
                    "one Tang messenger stands right in fitted dark iron lamellar",
                    "one low conical iron helmet",
                    "exactly one soft unmarked packet passes between them",
                    "narrow torchlit drainage passage",
                ),
                ("second monk", "missing messenger lamellar", "missing conical helmet", "open town street"),
            ),
            (
                "식량은 바닥나고 부상자가 속출하는 끔찍한 생지옥이었죠.",
                3,
                "group",
                (
                    "three separated adults, bandaged defender left",
                    "six empty hands, one forearm bandage",
                    "one empty basket and one overturned bowl before bare shelves with zero grain",
                ),
                ("grain on shelves", "grain pile", "missing forearm bandage", "missing clay bowl"),
            ),
            (
                "신성과 그 무리들이 굳게 닫힌 성문의 빗장을 몰래 풀어버리죠.",
                2,
                "pair",
                (
                    "shaved Sinseong left and tied-haired male accomplice right carry one removed beam",
                    "exactly two visible hands total",
                    "wide air gap exposes two empty U-brackets below",
                ),
                ("third hand", "beam touching bracket", "missing air gap", "female accomplice"),
            ),
            (
                "700년을 버텨온 거대 제국의 문이 허무하게 열리는 순간이죠.",
                None,
                "object",
                (
                    "zero-person interior view of one massive studded timber gate",
                    "one narrow firelit gap",
                    "one removed locking beam on earth below two empty iron brackets",
                ),
                ("human silhouette in fire", "person in doorway", "wide-open gate", "two open gaps"),
            ),
            (
                "짐승처럼 밀려드는 적군 앞에 평양성은 아수라장이 되죠.",
                1,
                "single",
                (
                    "one crouching armored defender recoils behind one cracked oval shield",
                    "charcoal smoke, orange light and packed-earth dust surge inward",
                    "exactly one adult and one shield, zero weapons",
                ),
                ("second person", "enemy silhouette", "spear", "sword", "second shield"),
            ),
            (
                "믿었던 자의 배신. 남건은 그제야 모든 것이 끝났음을 깨닫죠.",
                1,
                "single",
                (
                    "rust-lamellar Namgeon stands with slumped shoulders and two lowered empty hands",
                    "continuous identical small lamellar rows cover his entire chest",
                    "bare earth around his boots contains zero objects",
                ),
                ("rectangular chest badge", "name tag", "chest patch", "sword on ground", "weapon in frame"),
            ),
            (
                "쏟아지는 적군을 보며 남건은 치밀어 오르는 피눈물을 흘리죠.",
                1,
                "single",
                (
                    "near-frontal Namgeon portrait turned under ten degrees",
                    "both eyes and cheeks fully visible",
                    "exactly two glossy dark-red tear trails start at the two lower eyelids",
                ),
                ("side profile", "hidden eye", "forehead cut", "tear not connected to eye"),
            ),
            (
                "적의 손에 치욕스럽게 묶이느니 명예로운 죽음을 스스로 택하죠.",
                1,
                "single",
                (
                    "right hand grips one dagger with one handle and one blade",
                    "before his chest across a clear air gap",
                    "empty left palm on earth, opaque smoke and blank wall at every edge",
                ),
                ("gate signboard", "Chinese characters", "building facade", "two dagger blades", "scabbard"),
            ),
        )

        for narration, person_count, scene_kind, required_positive, required_negative in cases:
            with self.subTest(narration=narration):
                normalized = normalize_cut_image_prompt(base_prompt, narration, runtime_context)
                compiled = self.compile(normalized)
                self.assertEqual(compiled.person_count, person_count)
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertLessEqual(len(compiled.negative), 520)
                for token in required_positive:
                    self.assertIn(token, compiled.positive)
                for token in required_negative:
                    self.assertIn(token, compiled.negative)

                if "신성은 음모" in narration:
                    self.assertIsNone(_expected_visible_hand_count(normalized))
                    self.assertFalse(_should_check_internal_text_after_generation(normalized))
                if "맏아들 남생" in narration:
                    self.assertNotIn("one red cord", normalized.lower())
                if "700년을 버텨온" in narration:
                    self.assertTrue(_should_ignore_object_person_segmentation(normalized))
                if "식량은 바닥나고" in narration:
                    self.assertEqual(_expected_visible_hand_count(normalized), 6)
                if "신성과 그 무리들이" in narration:
                    self.assertEqual(_expected_visible_hand_count(normalized), 2)

    def test_ep30_capture_and_aftermath_cuts_use_minimal_exact_contracts(self):
        base_prompt = (
            "Year/period: 668year 9; Exact place: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Material culture: iron weapons, bows, leather or "
            "lamellar armor, hemp garments, wooden halls, fortress walls; Main subject: historical subject; "
            "Scene: historical scene"
        )
        runtime_context = (
            "안에서 열린 성문, 700년 제국의 몰락 EP.30 "
            "안에서 열린 성문, 700년 제국의 몰락"
        )
        cases = (
            (
                "하지만 목숨은 질겼고, 결국 피투성이가 된 채 사로잡힙니다.",
                1,
                "single",
                None,
                (
                    "tight chest-up frontal Namgeon in continuous rust lamellar",
                    "one thick rope makes three clearly visible horizontal turns around his chest and both upper arms",
                    "one shared side knot",
                ),
                ("missing chest rope", "rope only around waist", "prison bars", "missing wound stain"),
                ("two Tang guards", "Tang role in black futou"),
            ),
            (
                "보장왕 역시 무기를 버리고 적장 이세적 앞에 엎드려 항복하죠.",
                2,
                "pair",
                4,
                (
                    "close-fitting low conical iron-helmeted Li Ji stands upper right in fitted dark Tang lamellar",
                    "grey wrap-robed Bojang kneels on both knees lower left",
                    "exactly four visible empty hands",
                ),
                ("both men standing", "missing helmet", "unarmored Li Ji", "grey wrap robe on Li Ji"),
                ("closed packet", "ring-pommel sword"),
            ),
            (
                "동북아시아를 호령하던 고구려 왕의 비참하고 서늘한 최후였죠.",
                None,
                "object",
                None,
                (
                    "exactly two matching flat gilt-bronze halves",
                    "one palm-sized flame-shaped royal ornament",
                    "jagged matching break edges",
                    "one narrow gap",
                ),
                ("circular band", "open ring", "more than two fragments"),
                ("open-arc headband", "central plate attached"),
            ),
            (
                "화려한 문화를 꽃피웠던 평양성은 철저하게 약탈당하고 파괴되죠.",
                None,
                "object",
                None,
                (
                    "exactly one thin flat round bronze mirror disk",
                    "one deep jagged crack runs continuously",
                    "top rim through center to bottom rim",
                ),
                ("second mirror disk", "uncracked mirror", "bronze bowl", "cylindrical object"),
                ("bronze ritual bell", "roof beams"),
            ),
            (
                "당나라 군대는 고구려의 귀중한 서적과 보물을 모조리 불태웠죠.",
                None,
                "object",
                None,
                (
                    "one blank wood-slip bundle overlaps half of one blank bronze plaque",
                    "one connected bright fire surrounds the combined stack",
                    "directly touches both wood and bronze",
                ),
                ("missing fire", "plaque outside fire", "black outer frame", "Chinese characters"),
                ("Tang soldiers", "low conical helmets", "archive boxes"),
            ),
            (
                "나라를 잃은 백성의 운명은 짐승보다 못한 처참한 밑바닥이었죠.",
                1,
                "single",
                None,
                (
                    "one cangue-bound Goguryeo captive",
                    "wearing one rectangular timber neck cangue",
                    "connected head and neck pass through its single centered opening",
                    "both hands stay hidden beneath the board",
                ),
                ("second person", "second cangue", "floating head", "visible hand"),
                ("cangue lying flat", "wrist openings"),
            ),
            (
                "포로로 끌려간 보장왕과 남건 형제는 장안의 흙바닥에 꿇어앉죠.",
                2,
                "pair",
                4,
                (
                    "exactly two separated men kneel on both knees",
                    "grey-robed Bojang lower left",
                    "rust-lamellar Namgeon lower right",
                    "four empty hands rest separately on four thighs",
                    "zero objects lie on earth",
                ),
                ("standing captive", "fighting pose", "seated bench"),
                ("closed packet", "Tang role in black futou"),
            ),
            (
                "천하를 다스리던 당 황제 앞에서 끔찍한 굴욕을 감내해야 했죠.",
                2,
                "pair",
                4,
                (
                    "Emperor Gaozong confronting kneeling King Bojang",
                    "Exactly four visible hands total",
                    "two separated men face a blank wall",
                    "black-capped Gaozong stands right",
                    "dark smooth-front Tang paofu",
                    "zero visible fasteners",
                    "grey-robed Bojang kneels left",
                ),
                ("front buttons on Gaozong", "frog closures", "vertical button row", "bare topknot on Gaozong"),
                ("Namgeon", "three same-scale men", "tight waist-up two-shot"),
            ),
        )

        for narration, person_count, scene_kind, hand_count, required, negative, forbidden in cases:
            with self.subTest(narration=narration):
                normalized = normalize_cut_image_prompt(base_prompt, narration, runtime_context)
                compiled = self.compile(normalized)
                self.assertEqual(compiled.person_count, person_count)
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertEqual(_expected_visible_hand_count(normalized), hand_count)
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertLessEqual(len(compiled.negative), 520)
                for token in required:
                    self.assertIn(token, compiled.positive)
                for token in negative:
                    self.assertIn(token, compiled.negative)
                for token in forbidden:
                    self.assertNotIn(token, compiled.positive)
                if "서적과 보물" in narration:
                    self.assertTrue(_should_ignore_object_person_segmentation(normalized))

    def test_ep30_traitor_aftermath_cuts_use_exact_evidence_contracts(self):
        base_prompt = (
            "Year/period: 668year 9; Exact place: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Material culture: iron weapons, bows, leather or "
            "lamellar armor, hemp garments, wooden halls, fortress walls; Main subject: historical subject; "
            "Scene: historical scene"
        )
        runtime_context = (
            "안에서 열린 성문, 700년 제국의 몰락 EP.30 "
            "안에서 열린 성문, 700년 제국의 몰락"
        )
        cases = (
            (
                51,
                "반면 조국을 멸망으로 밀어 넣은 매국노들의 삶은 어땠을까요.",
                "object",
                None,
                None,
                "composition=tang_rewards_above_discarded_goguryeo_sash",
                ("exactly one long narrow grey Goguryeo rank sash", "jagged torn center", "exactly two frayed ends", "exactly one face-down blank-backed square bronze Tang rank seal"),
                ("garment", "parallel sash strips"),
            ),
            (
                54,
                "당 고종은 그에게 우위대장군이라는 높은 벼슬과 땅을 하사하죠.",
                "object",
                None,
                None,
                "composition=blank_rank_seal_pressed_into_granted_earth",
                ("exactly one blank-backed gilt-bronze Tang rank seal", "half-buried in dark earth", "exactly one plain shallow land-grant tray"),
                ("person", "seal face visible"),
            ),
            (
                56,
                "조국을 팔아먹은 대가로 적국의 관리가 되어 동포를 짓밟은 거죠.",
                "object",
                None,
                None,
                "composition=blank_rank_seal_pins_torn_goguryeo_sash",
                ("exactly one palm-sized heavy square bronze Tang rank seal", "smooth blank back visible", "directly pinning the torn center of exactly one grey woven Goguryeo sash"),
                ("seal face visible", "shoe"),
            ),
            (
                58,
                "배신자는 자신의 배신을 정당화하기 위해 끝없이 괴물이 되었죠.",
                "object",
                None,
                None,
                "composition=single_cracked_mirror_one_reflected_collaborator_face",
                ("exactly one handleless round polished-bronze mirror disk", "sharply narrowed predatory eyes", "clearly bared teeth"),
                ("second face", "neutral expression"),
            ),
            (
                59,
                "충신은 유배지에서 죽어가고 매국노는 대대손손 번성하는 역설.",
                "landscape",
                None,
                None,
                "composition=exile_grave_against_warm_traitor_household",
                ("one low sealed convex snow-covered earth grave mound", "zero opening, hole, pit, stone lining or marker", "warm open Tang doorway", "exactly three shallow bronze cups"),
                ("stone-lined pit", "medal"),
            ),
            (
                60,
                "이것이 도덕과 정의가 거세된 고대 정치의 가장 차가운 민낯이죠.",
                "object",
                None,
                None,
                "composition=overturned_seat_two_broken_seals_two_cut_cords",
                ("one overturned low timber ruler seat", "exactly two cracked face-down blank square bronze rank seals", "exactly two severed red cord ends"),
                ("gold bar", "arena"),
            ),
            (
                61,
                "679년, 매국노 남생이 46세의 나이로 호위호식하다 죽습니다.",
                "single",
                1,
                0,
                "composition=deceased_namsaeng_overhead_face_zero_hands",
                ("Direct overhead edge-to-edge face-only mortuary close-up", "both eyelids fully shut with zero iris or pupil", "exactly zero visible hands or forearms", "short tied black hair with grey temples", "featureless dark silk"),
                ("open eyes", "lantern"),
            ),
            (
                62,
                "당나라 황제는 그의 죽음을 슬퍼하며 3일이나 조정 문을 닫았죠.",
                "object",
                None,
                None,
                "composition=closed_tang_gate_object_only",
                ("one completely closed plain Tang timber court gate", "two central adze-hewn plank leaves", "one narrow closed seam", "one plain iron ring pull on each leaf"),
                ("open gate", "signboard"),
            ),
            (
                63,
                "5품 이상의 고위 관료들을 총동원해 국장급 장례를 치러줍니다.",
                "object",
                None,
                None,
                "composition=shrouded_coffin_under_plain_mourning_canopy",
                ("exactly one plain hemp mourning canopy", "exactly one long coffin fully covered by one plain undyed hemp shroud", "packed earth only at frame edge"),
                ("person", "futou"),
            ),
            (
                64,
                "남생 가문은 중국 낙양 북망산에 화려한 무덤을 굳건히 남겼죠.",
                "landscape",
                None,
                None,
                "composition=mangshan_mound_fills_frame_plain_approach",
                ("one large rammed-earth burial mound fills the upper two-thirds", "one long plain stone approach", "distant dark hills filling both upper corners", "no open blank sky"),
                ("caption", "blank white sky"),
            ),
        )

        for cut_number, narration, kind, count, hand_count, composition, required, negative in cases:
            with self.subTest(cut_number=cut_number):
                normalized = normalize_cut_image_prompt(base_prompt, narration, runtime_context)
                compiled = self.compile(normalized)
                self.assertEqual(compiled.scene_kind, kind)
                self.assertEqual(compiled.person_count, count)
                self.assertEqual(_expected_visible_hand_count(normalized), hand_count)
                self.assertIn(composition, compiled.diagnostics)
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertLessEqual(len(compiled.negative), 520)
                for token in required:
                    self.assertIn(token, compiled.positive)
                for token in negative:
                    self.assertIn(token, compiled.negative)
                if cut_number in {51, 54, 56, 58, 63}:
                    self.assertTrue(_should_ignore_object_person_segmentation(normalized))
                if cut_number == 58:
                    self.assertTrue(_should_ignore_split_panel_for_intentional_center_gap(normalized))
                if cut_number == 61:
                    self.assertTrue(_should_ignore_dark_outer_frame_detector(normalized))
                if cut_number == 64:
                    self.assertFalse(_should_use_reduced_internal_text_detector(normalized))

    def test_ep30_visible_hand_contract_reaches_generation_and_final_detector(self):
        normalized = normalize_cut_image_prompt(
            "Year/period: 668 AD; Exact place: Fallen Pyongyang audience hall; Main subject: historical subject; Scene: historical scene",
            "텅 빈 옥좌를 위해 무수한 백성이 흙먼지 속에 쓰러졌습니다.",
            "668 AD Goguryeo succession crisis",
        )
        compiled = self.compile(normalized)

        self.assertEqual(_expected_visible_hand_count(normalized), 2)
        self.assertEqual(
            _expected_visible_hand_count("Composition: exactly zero visible hands; chest-up crop"),
            0,
        )
        self.assertIn("exactly two visible hands total", compiled.positive)
        self.assertIn("third hand", compiled.negative)
        self.assertIn("extra hand", compiled.negative)

        workflow_path = (
            Path(__file__).resolve().parents[1]
            / "workflows"
            / "comfyui"
            / "flux2_klein_4b_text2img.json"
        )
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
        self.assertTrue(workflow["31"]["inputs"]["force_inpaint"])
        self.assertTrue(workflow["30"]["inputs"]["force_inpaint"])
        self.assertEqual(workflow["30"]["inputs"]["image"], ["12", 0])
        self.assertEqual(workflow["15"]["inputs"]["image"], ["30", 0])
        self.assertEqual(workflow["31"]["inputs"]["image"], ["30", 0])
        self.assertEqual(workflow["41"]["inputs"]["image"], ["31", 0])
        self.assertEqual(workflow["44"]["inputs"]["image"], ["31", 0])
        self.assertEqual(workflow["41"]["inputs"]["bbox_detector"], ["14", 0])
        self.assertEqual(workflow["43"]["inputs"]["input"], ["42", 0])

    def test_ep30_cuts_66_to_74_use_historical_object_and_fortress_contracts(self):
        base_prompt = (
            "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
            "Main subject: historical subject; Scene: historical scene"
        )
        runtime_context = "안에서 열린 성문, 700년 제국의 몰락 EP.30"
        cases = (
            (
                66,
                "오직 당 황제에게 바친 충성과 얻어낸 권력만을 길게 자랑했죠.",
                "object",
                "composition=tang_rank_fittings_on_severed_sash_at_mound",
                (
                    "exactly one palm-sized thin flat face-down blank-backed weathered bronze Tang rank seal",
                    "exactly one severed dark-grey Goguryeo sash",
                    "exactly two straight aligned halves",
                ),
                ("wire", "isolated white background"),
            ),
            (
                69,
                "700년 역사의 고구려는 외적의 침략만으로 무너지지 않았죠.",
                "landscape",
                "composition=intact_outer_wall_burning_inside",
                (
                    "one continuous intact sloped Goguryeo fieldstone-and-rammed-earth outer wall",
                    "orange firelight and thick black smoke rise",
                    "unseen interior",
                ),
                ("visible building", "tiled roof"),
            ),
            (
                70,
                "수백만 대군도 못 뚫은 철벽을 허문 건 결국 내부의 탐욕이죠.",
                "object",
                "composition=gate_beam_split_by_two_rank_seals",
                (
                    "exactly one massive horizontal Goguryeo timber gate beam",
                    "one rotten center notch",
                    "exactly two small face-down blank-backed bronze rank seals",
                ),
                ("iron chain", "third seal"),
            ),
            (
                71,
                "일인 독재자 연개소문이 남긴 권력의 사유화는 치명적인 독이 됐죠.",
                "object",
                "composition=private_family_sash_binds_command_seal",
                (
                    "exactly one single straight dark family sash with exactly two ends crosses horizontally",
                    "exactly one solid closed face-down blank-backed square bronze Goguryeo command seal",
                    "with exactly two ends",
                ),
                ("knot", "open frame"),
            ),
            (
                74,
                "지도층이 탐욕에 눈이 멀자, 국가는 안에서부터 썩어 문드러졌죠.",
                "object",
                "composition=single_jar_exposes_internal_rot",
                (
                    "one plain unglazed Goguryeo grain jar ruptured open by black-green rot",
                    "one jagged front rupture exposes black-green mold",
                    "clumped spoiled millet",
                ),
                ("second jar", "normal dry seeds"),
            ),
        )

        for cut_number, narration, kind, composition, required, negative in cases:
            with self.subTest(cut_number=cut_number):
                normalized = normalize_cut_image_prompt(base_prompt, narration, runtime_context)
                compiled = self.compile(normalized)
                self.assertEqual(compiled.scene_kind, kind)
                self.assertIsNone(compiled.person_count)
                self.assertIn(composition, compiled.diagnostics)
                self.assertLessEqual(len(compiled.positive), 950)
                self.assertLessEqual(len(compiled.negative), 520)
                for token in required:
                    self.assertIn(token, compiled.positive)
                for token in negative:
                    self.assertIn(token, compiled.negative)
                if cut_number in {66, 69, 74}:
                    self.assertTrue(_should_ignore_object_person_segmentation(normalized))

    def test_ep30_zero_person_contracts_never_require_a_detected_person(self):
        base_prompt = (
            "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
            "Main subject: historical subject; Scene: historical scene"
        )
        gate = self.compile(
            normalize_cut_image_prompt(
                base_prompt,
                "700년을 버텨온 거대 제국의 문이 허무하게 열리는 순간이죠.",
                "668 AD Goguryeo succession crisis",
            )
        )
        street = self.compile(
            normalize_cut_image_prompt(
                base_prompt,
                "거리마다 붉은 피가 흐르고, 궁궐은 거대한 불길에 휩싸입니다.",
                "668 AD Goguryeo succession crisis",
            )
        )

        self.assertIn(gate.scene_kind, {"object", "landscape"})
        self.assertIsNone(gate.person_count)
        self.assertIn(street.scene_kind, {"object", "landscape"})
        self.assertIsNone(street.person_count)

    def test_ep30_detector_scopes_match_verified_failure_images(self):
        base_prompt = (
            "Year/period: 668 AD; Exact place: Pyongyang Fortress; "
            "Style: serious adult graphic novel illustration, bold black ink outlines; "
            "Main subject: historical subject; Scene: historical scene"
        )

        granary = normalize_cut_image_prompt(
            base_prompt,
            "지도층이 탐욕에 눈이 멀자, 국가는 안에서부터 썩어 문드러졌죠.",
            "668 AD Goguryeo succession crisis",
        )
        helmets = normalize_cut_image_prompt(
            base_prompt,
            "무너진 평양성 잔해 밑에는 이름 없는 자들의 피눈물이 서려 있죠.",
            "668 AD Goguryeo succession crisis",
        )
        discarded_tally = normalize_cut_image_prompt(
            base_prompt,
            "국가를 장기말처럼 버린 지배층의 비열하고 끔찍한 이기심 말입니다.",
            "668 AD Goguryeo succession crisis",
        )
        burning_alley = normalize_cut_image_prompt(
            base_prompt,
            "권력자의 오만이 힘없는 백성을 처참한 핏빛 생지옥으로 밀어 넣었죠.",
            "668 AD Goguryeo succession crisis",
        )
        survivor = normalize_cut_image_prompt(
            base_prompt,
            "진실을 마주할 각오가 섰다면 핏빛 체스판에서 눈을 떼지 마십시오.",
            "668 AD Goguryeo succession crisis",
        )
        pouch = normalize_cut_image_prompt(
            base_prompt,
            "패자는 흔적도 못 남기고 오직 강자만 살아남는 핏빛 세계입니다.",
            "668 AD Goguryeo succession crisis",
        )
        broken_mirror = normalize_cut_image_prompt(
            base_prompt,
            "화려한 문화를 꽃피웠던 평양성은 철저하게 약탈당하고 파괴되죠.",
            "668 AD Goguryeo succession crisis",
        )
        bowls = normalize_cut_image_prompt(
            base_prompt,
            "권력의 체스판 위에서 백성들은 무참히 버려지는 소모품이었습니다.",
            "668 AD Goguryeo succession crisis",
        )
        broken_bundle = normalize_cut_image_prompt(
            base_prompt,
            "낡은 위인전을 찢어버린 날 것 그대로의 잔혹한 생존기였습니다.",
            "668 AD Goguryeo succession crisis",
        )

        self.assertTrue(_should_ignore_object_person_segmentation(granary))
        self.assertTrue(_should_ignore_object_person_segmentation(helmets))
        self.assertTrue(_should_ignore_object_person_segmentation(discarded_tally))
        self.assertFalse(_should_ignore_object_person_segmentation(broken_mirror))
        self.assertFalse(_should_ignore_corner_signature_detector(broken_mirror))
        self.assertTrue(_should_ignore_object_person_segmentation(bowls))
        self.assertTrue(_should_ignore_object_person_segmentation(pouch))
        self.assertTrue(_should_ignore_object_person_segmentation(broken_bundle))
        self.assertTrue(_should_use_reduced_internal_text_detector(survivor))
        self.assertTrue(_should_use_reduced_internal_text_detector(pouch))
        self.assertTrue(
            _should_skip_dense_internal_text_grid(
                "Exact place: windowless Pyongyang north-gate interior breach"
            )
        )
        self.assertTrue(_should_skip_dense_internal_text_grid(burning_alley))
        self.assertFalse(_should_skip_dense_internal_text_grid(discarded_tally))

    def test_ep29_texture_heavy_scenes_use_scoped_text_and_person_detectors(self):
        self.assertFalse(
            _should_use_reduced_internal_text_detector(
                "Exact place: windowless Pyongyang north-gate interior passage; "
                "Scene: featureless vertical gate planks fill every background edge"
            )
        )

        for prompt in (
            "Main subject: exactly three starving Goguryeo civilians",
            "Main subject: exactly three dented Goguryeo segmented iron helmets",
            "Main subject: exactly two adult Goguryeo civilian bearers carrying one fully shrouded casualty",
            "Main subject: one low segmented iron cap helmet beside one flattened gilt-bronze cover",
            "Main subject: one blank square bronze succession plaque half-submerged in black poison",
            "Main subject: one full-scale smooth unmarked Goguryeo rammed-earth defensive embankment collapsing into loose sand",
            "Main subject: one full-scale Pyongyang Goguryeo fortress encircled by Tang tents",
            "Main subject: exactly two blank bronze seals divided by one deep floor crack",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(_should_use_reduced_internal_text_detector(prompt))

        self.assertTrue(
            _should_use_reduced_internal_text_detector(
                "Main subject: one empty dented segmented iron helmet in one fresh cart-wheel track"
            )
        )

        for prompt in (
            "Main subject: exactly three dented Goguryeo segmented iron helmets",
            "Main subject: one low segmented iron cap helmet beside one flattened gilt-bronze cover",
            "Main subject: one cracked oval Goguryeo timber shield pierced by exactly one detached spearhead",
            "Main subject: one upright uninscribed flared bronze alarm bell with one frayed rope stub",
            "Main subject: one cracked stone kneeling statue releasing one distorted black shadow",
            "Main subject: one full-scale low Goguryeo rammed-earth fortress collapsing into loose sand",
            "Main subject: one full-scale smooth unmarked Goguryeo rammed-earth defensive embankment collapsing into loose sand",
            "Main subject: one blank square bronze succession plaque half-submerged in black poison",
            "Main subject: one cracked handle-down plain square bronze succession seal leaking black poison",
            "Main subject: one cracked plain square bronze succession plaque leaking black poison",
            "Main subject: one cracked bronze stamp with a low bridge knob in a dark-red stain",
            "Main subject: one empty dented segmented iron helmet in one fresh cart-wheel track",
            "Main subject: exactly one cropped Tang-era cloth-wrapped forefoot pressing exactly one dented Goguryeo iron cap",
            "Main subject: one cropped Tang-era cloth-wrapped forefoot pressing one torn Goguryeo silk sash into freezing mud",
            "Main subject: one iron gate chain being unhooked by exactly one sleeve-covered right hand",
        ):
            with self.subTest(prompt=prompt):
                self.assertTrue(_should_ignore_object_person_segmentation(prompt))

        fortress_prompt = "Main subject: one full-scale Pyongyang Goguryeo fortress encircled by Tang tents"
        burning_sheet_prompt = "Main subject: one blank unmarked fibrous sheet burning into ash"
        qualified_burning_sheet_prompt = (
            "Exact place: featureless seamless cool grey stone surface; "
            "Main subject: one blank unmarked fibrous sheet burning into ash"
        )
        self.assertTrue(_should_ignore_strict_nonhuman_person_segmentation(fortress_prompt))
        self.assertFalse(_should_ignore_object_person_segmentation(fortress_prompt))
        self.assertFalse(_should_ignore_object_person_segmentation(burning_sheet_prompt))
        self.assertTrue(_should_check_burning_sheet_background(qualified_burning_sheet_prompt))
        self.assertTrue(_should_ignore_object_person_segmentation(qualified_burning_sheet_prompt))

    def test_burning_sheet_background_gate_rejects_busy_room_edges(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            clean = Path(tmp) / "clean_sheet.png"
            busy = Path(tmp) / "busy_sheet.png"

            clean_image = Image.new("RGB", (1280, 720), (45, 47, 48))
            clean_draw = ImageDraw.Draw(clean_image)
            clean_draw.rectangle((300, 175, 980, 555), fill=(224, 216, 190), outline=(12, 12, 12), width=8)
            clean_image.save(clean)

            busy_image = clean_image.copy()
            busy_draw = ImageDraw.Draw(busy_image)
            for y in range(35, 165, 24):
                busy_draw.line((0, y, 1279, y + 40), fill=(8, 8, 8), width=10)
            for x in range(0, 1280, 80):
                busy_draw.line((x, 0, x + 90, 160), fill=(8, 8, 8), width=8)
            busy_draw.rectangle((70, 0, 260, 125), fill=(20, 20, 20), outline=(235, 235, 235), width=8)
            busy_draw.rectangle((1020, 0, 1210, 125), fill=(20, 20, 20), outline=(235, 235, 235), width=8)
            busy_image.save(busy)

            self.assertFalse(_image_has_busy_burning_sheet_background(clean))
            self.assertTrue(_image_has_busy_burning_sheet_background(busy))

    def test_starvation_wall_gate_rejects_exposed_light_top_band(self):
        from PIL import Image, ImageDraw

        prompt = (
            "Main subject: exactly two adults: starving civilian and kneeling lamellar soldier; "
            "Scene: both kneel before a smooth earthen wall"
        )
        self.assertTrue(_should_check_starvation_wall_top_edge(prompt))

        with tempfile.TemporaryDirectory() as tmp:
            full_wall = Path(tmp) / "full_wall.png"
            exposed_top = Path(tmp) / "exposed_top.png"
            Image.new("RGB", (1280, 720), (158, 132, 102)).save(full_wall)
            exposed = Image.new("RGB", (1280, 720), (158, 132, 102))
            ImageDraw.Draw(exposed).rectangle((0, 0, 1279, 26), fill=(238, 238, 226))
            exposed.save(exposed_top)

            self.assertFalse(_image_has_light_top_band(full_wall))
            self.assertTrue(_image_has_light_top_band(exposed_top))

        self.assertFalse(
            _should_use_reduced_internal_text_detector(
                "Main subject: one fallen uninscribed bronze alarm bell and one severed hemp rope"
            )
        )

    def test_narration_aligned_baekje_ep02_keeps_registered_human_scene(self):
        prompt = (
            "Year/period: Baekje foundation traditions; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-010; "
            "Scene: Ancient Korean royal genealogies on silk beside two shadowed founders, "
            "coastal settlements and the Yellow Sea in the distance; "
            "Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: 백제의 첫 왕은 온조가 아니었다는 기록이 남아 있습니다"
        )

        compiled = self.compile(prompt)

        self.assertIn("Exactly two adult founder silhouettes", compiled.positive)
        self.assertIn("tightly rolled blank silk genealogy bundles", compiled.positive)
        self.assertIn("complete visible action dominates", compiled.positive)
        self.assertNotIn("백제의 첫 왕은 온조가 아니었다는 기록", compiled.positive)
        self.assertIn("prompt_order=narrative_fidelity_compact", compiled.diagnostics)
        self.assertNotIn("object-only alternative-founder record evidence", compiled.positive)
        self.assertNotIn("local-exact-layout", " ".join(compiled.diagnostics))

    def test_narrative_fidelity_marker_alone_enables_baekje_ep02_alignment(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-043; "
            "Scene: Layered depth composition within a historically grounded Baekje settlement, "
            "visualizing this decisive historical beat: Soon, a scene connecting with Gongsun Dao, "
            "the ruler of Liaodong, appears. Focused gestures and surrounding reactions make the "
            "immediate historical stakes readable. || "
            "Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1 || "
            "Narration context: 곧 요동의 지배자 공손도와 연결되는 장면이 튀어나옵니다."
        )

        compiled = self.compile(prompt)

        self.assertIn("narration_visual_alignment=on", compiled.diagnostics)
        self.assertIn("Gongsun", compiled.positive)
        self.assertNotIn("object-only", compiled.positive.lower())

    def test_narrative_fidelity_human_reactions_are_not_demoted_to_object_scene(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Reaction-focused medium shot in a Baekje settlement. Focused gestures, "
            "one decisive object, and surrounding reactions make the immediate historical "
            "stakes readable. || Global style: historical documentary "
            "NARRATIVE_FIDELITY_REGEN_V1 || Narration context: 해양 제국의 씨앗은 어디였을까요"
        )

        compiled = self.compile(prompt)

        self.assertEqual(compiled.scene_kind, "group")
        self.assertIn("Body integrity", compiled.positive)
        self.assertIn("hands attached to forearms", compiled.positive)
        self.assertNotIn("object-only", compiled.positive.lower())

    def test_narrative_fidelity_human_reactions_are_not_demoted_to_landscape_scene(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Wide view beside the river road in a Baekje settlement. Focused gestures, "
            "one decisive object, and surrounding reactions make the power struggle readable. "
            "|| Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1 || "
            "Narration context: 강 어귀를 차지한 세력이 주변 연맹을 압박했습니다"
        )

        compiled = self.compile(prompt)

        self.assertEqual(compiled.scene_kind, "group")
        self.assertIn("surrounding human reactions", compiled.positive)
        self.assertNotIn("one decisive object", compiled.positive)

    def test_narrative_fidelity_explicit_object_only_evidence_stays_object_scene(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: object-only one sealed blank chronicle bundle on bare packed earth, "
            "zero visible people. || Global style: historical documentary "
            "NARRATIVE_FIDELITY_REGEN_V1 || Narration context: 이 기록 한 점만 남았습니다"
        )

        compiled = self.compile(prompt)

        self.assertEqual(compiled.scene_kind, "object")

    def test_narrative_fidelity_keeps_human_staging_and_removes_decisive_object_template(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Reaction-focused medium shot in a Baekje settlement. Focused gestures, "
            "one decisive object, and surrounding reactions make the immediate historical "
            "stakes readable. || Global style: historical documentary "
            "NARRATIVE_FIDELITY_REGEN_V1 || Narration context: 서로 다른 기억이 충돌했습니다"
        )

        compiled = self.compile(prompt)

        self.assertIn("surrounding human reactions", compiled.positive)
        self.assertNotIn("one decisive object", compiled.positive)

    def test_narrative_fidelity_repairs_noncombat_baekje_maritime_scenes(self):
        cases = (
            (
                "배에 오른 건 군대만이 아니라 가족과 기술자, 생업 공동체였을 것이며,",
                "civilian families",
            ),
            (
                "답은 거대한 함대보다 한강과 서해가 만나는 지형에서 먼저 보입니다.",
                "tidal flats",
            ),
            (
                "하지만 건국 직후부터 원양 함대가 바다를 지배했다는 증거는 없습니다.",
                "fishers repairing a plain net",
            ),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Scene: Tight profile composition in a contested earthwork battlefield. "
            "Opposing formations lock into one clash as terrain and shields reveal cause and consequence."
        )

        for narration, expected in cases:
            with self.subTest(narration=narration):
                prompt = (
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("Opposing formations", compiled.positive)

    def test_narrative_fidelity_routes_baekje_dialogue_to_distinct_human_actions(self):
        cases = (
            (
                "그런데 구태의 혼인 상대를 따라가면 건국 연대가 수백 년 흔들립니다.",
                "late-second-century CE Liaodong-Daifang Eastern Han frontier",
            ),
            (
                "한 나라의 출생증명서에 창업자와 건국 시점이 둘씩 적힌 셈이죠.",
                "exactly three adult Korean historians",
            ),
            (
                "무대는 기원전후로 전하는 백제의 시작과 훗날의 대방 지역입니다.",
                "identical charcoal zip-front nylon field jackets",
            ),
            (
                "다만 이 이름은 온조의 건국 연대보다 뒤에 등장하므로 처음부터 수상합니다.",
                "later place-name does not fit an earlier proposed date",
            ),
            (
                "한강 유역 위례에 자리 잡아 십제를 세웠다는 이야기로 이어집니다.",
                "two builders setting one plain timber post",
            ),
            (
                "비류 세력이 합쳐지면서 국호가 백제로 바뀌었다는 설명도 붙죠.",
                "two unarmed adult male household leaders bowing",
            ),
            (
                "그런데 중국에서 편찬된 북사와 수서는 전혀 다른 이름을 꺼냅니다.",
                "three unarmed adult Chinese court chroniclers",
            ),
            (
                "그 이름이 바로 구태, 백제의 또 다른 창업자로 기록된 인물이죠.",
                "exactly one unarmed adult man, Gutae",
            ),
            (
                "이제 두 건국자가 한 왕조 안에서 충돌하기 시작합니다.",
                "Onjo in left profile and Gutae in right profile",
            ),
            (
                "삼국사기 편찬자는 온조 설화를 적은 뒤 북사와 수서의 문장도 함께 옮겼고,",
                "center compiler first listens to the left speaker",
            ),
            (
                "온조 설화의 출발점은 졸본과 고구려 왕실의 후계 다툼입니다.",
                "King Jumong sits at center",
            ),
            (
                "반면 구태 설화의 출발점은 대방과 요동의 공손씨 세력이죠.",
                "Gongsun clan ruler sits at center",
            ),
            (
                "한쪽은 형제가 무리를 이끌고 남하하는 이주 서사이며,",
                "brothers Onjo and Biryu leading unarmed civilian families",
            ),
            (
                "다른 쪽은 혼인동맹으로 주변 세력을 묶는 국제정치 이야기입니다.",
                "Two-face-only late-second-century marriage-alliance",
            ),
            (
                "주인공도 다르고 무대도 다르며 권력을 얻는 방법까지 달랐죠.",
                "different protagonists, stages, and paths to power",
            ),
            (
                "그런데 두 기록 모두 백제의 기원을 설명한다고 버티고 있습니다.",
                "left speaker insists on one founding origin",
            ),
            (
                "여기서 중요한 건 북사와 수서가 백제 건국 당시 기록이 아니라는 점입니다.",
                "compiled centuries after the founding",
            ),
            (
                "두 책은 백제가 이미 오랜 왕조가 된 뒤 중국에서 정리됐고,",
                "compiled only after Baekje was already an old dynasty",
            ),
            (
                "그 사이 백제 왕실의 계보와 주변 국가의 기억도 여러 번 재구성됐겠죠.",
                "royal lineages and neighboring memories were reconstructed repeatedly",
            ),
            (
                "따라서 구태 이야기는 현장 보고서가 아니라 후대에 남은 기원 전승입니다.",
                "later origin tradition, not an eyewitness field report",
            ),
            (
                "그렇다고 없던 이야기로 치워버리면 또 하나의 단서를 잃게 되며,",
                "discarding the tradition erases a historical clue",
            ),
            (
                "왜 중국 기록에만 구태가 강하게 남았는지 설명할 길도 막힙니다.",
                "why Gutae survived strongly only in Chinese records",
            ),
            (
                "북사와 수서가 전한 구태는 동명이라는 인물의 후손으로 등장합니다.",
                "claimed descendant Gutae",
            ),
            (
                "동명은 부여계 건국 전승의 영웅으로 여러 왕실이 계보를 잇던 이름이죠.",
                "shared lineage ancestor",
            ),
            (
                "구태는 그 혈통을 등에 업고 대방의 옛 땅에 나라를 세웠다고 하며,",
                "Gutae stands at center directing exactly three unarmed civilian builders",
            ),
            (
                "결혼 한 번으로 구태는 변방의 지도자에서 강자의 사위가 됐고,",
                "entering the ruler's family",
            ),
            (
                "기록은 마침내 그 나라가 동이의 강국이 되었다고 압축합니다.",
                "recognizing his state as a regional power",
            ),
            (
                "남하와 개척 대신 혈통, 영토, 혼인, 강국이라는 네 장면이 번개처럼 이어지죠.",
                "people alone embody lineage, territory, marriage, and political power",
            ),
            (
                "특히 혼인은 사적인 사랑이 아니라 두 세력의 안전을 묶는 동맹이었고,",
                "security between two powers rather than romance",
            ),
            (
                "요동과 대방 사이의 길을 장악하려는 계산이 깔린 정치 수단이었습니다.",
                "Liaodong-Daifang road scene",
            ),
            (
                "이 서사만 보면 백제는 시작부터 북방 국제정치의 한복판에 서지만,",
                "Gutae stands at center between Gongsun Du",
            ),
            (
                "바로 그럴듯함 때문에 더 위험한 함정도 생깁니다.",
                "plausibility creates a dangerous trap",
            ),
            (
                "기록 속 인물과 지명을 시간표 위에 올리는 순간 균열이 드러나죠.",
                "fail to share one chronology",
            ),
            (
                "온조 건국 전승은 기원전 십팔년을 출발점으로 제시합니다.",
                "Onjo stands at center at the beginning",
            ),
            (
                "하지만 공손도가 요동에서 세력을 잡은 때는 후한 말의 일이죠.",
                "final decades of Eastern Han rule",
            ),
            (
                "두 시점 사이에는 한두 세대가 아니라 수백 년의 간격이 놓입니다.",
                "separated by centuries, not one or two generations",
            ),
            (
                "대방군이라는 행정구역 역시 기원전 십팔년에 존재하던 이름이 아니며,",
                "Daifang Commandery did not exist in 18 BCE",
            ),
            (
                "공손씨 세력이 낙랑 남쪽을 나누어 설치한 뒤에야 역사에 등장합니다.",
                "setting a single plain timber boundary post",
            ),
            (
                "백제라는 이름도 백 가문이 바다를 건넜기 때문이라는 전승이 붙어 있고,",
                "Yellow Sea crossing",
            ),
            (
                "고구려 건국자 주몽의 아들 온조가 형 비류와 남쪽으로 내려왔고,",
                "southward migration",
            ),
            (
                "하지만 백가제해를 실제 승선 명단처럼 받아들이면 곤란합니다.",
                "two adult women, two children",
            ),
            (
                "백제는 바로 그 교차점에서 성장할 수 있는 조건을 얻었습니다.",
                "working river-coast junction",
            ),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Eye-level medium shot inside a historically grounded Baekje settlement. "
            "Focused gestures and surrounding reactions make the immediate historical stakes readable."
        )

        for narration, expected in cases:
            with self.subTest(narration=narration):
                prompt = (
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("historically grounded Baekje settlement", compiled.positive)
                self.assertIn("generic warrior crowd", compiled.negative)
                self.assertIn("drawn weapon", compiled.negative)

    def test_baekje_foundation_negative_blocks_later_korean_period_costume(self):
        negative = append_prompt_specific_negative_prompt(
            "",
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Scene: late-second-century CE Liaodong-Daifang marriage-alliance reception",
        )

        self.assertIn("Joseon gat", negative)
        self.assertIn("ceremonial bridal hanbok", negative)
        self.assertIn("ornate tiled royal palace", negative)

    def test_baekje_ep02_failed_cut_repair_actions_are_literal_and_human_centered(self):
        cases = (
            ("그를 곧바로 백제의 진짜 초대왕이라 부를 근거도 사라집니다.", "rejects calling Gutae the proven true first king"),
            ("혹시 구태는 훗날 백제를 크게 키운 다른 왕의 기억이었을까요?", "memory of a later expansion-era king"),
            ("어느 가설도 모든 연대와 기록을 깔끔하게 맞추지는 못했죠.", "no single hypothesis fits every date and record"),
            ("책부원귀에는 백제가 도성에 구태의 사당을 세웠다고 적혀 있고,", "small plain timber ancestor shrine"),
            ("왕실이 제사한 구태와 역사서가 내세운 온조는 어떻게 함께 존재했을까요?", "royal Gutae ritual and an official Onjo founding account coexisted"),
            ("이제 창업자의 수수께끼는 나라 이름의 수수께끼로 번집니다.", "from the disputed founder to the disputed origin"),
            ("왕자 한 명의 이름보다 집단 전체의 이동을 앞세운 설명입니다.", "The entire civilian community dominates"),
            ("전승은 그 거대한 이동의 기억을 네 글자로 눌러 담았습니다.", "oral-memory scene"),
            ("두 국호 풀이를 겹쳐 보면 승자가 패자를 지운 단순한 건국담은 무너집니다.", "neither side erased the other"),
            ("한강 유역에는 이미 여러 토착 집단이 각자의 정치체를 이루고 있었고,", "three separate local communities"),
            ("여기에 예계 주민과 중국 군현에서 이동한 사람들까지 섞이며,", "Chinese-commandery migrant woman right"),
            ("기록이 남기지 않은 전투와 배신을 구체적으로 꾸며낼 수는 없습니다.", "cautions against inventing unrecorded battles"),
            ("사람들은 물길을 따라 소금과 곡물, 금속과 정보를 옮겼고,", "one sealed message pouch"),
            ("그 반복된 왕래가 먼 지역과 거래하는 기술을 쌓게 했습니다.", "skills learned through repeated voyages"),
            ("구태 설화의 바다는 완성된 제국의 증거가 아니라,", "reject treating it as proof of a finished maritime empire"),
            ("특히 근초고왕 시대에는 정복과 외교, 교역이 함께 움직였고,", "one armored commander, one foreign envoy, and one merchant"),
            ("칠지도 같은 유물은 그 복잡한 관계가 물질로 남은 사례죠.", "exactly six branch blades"),
            ("건국의 바다와 전성기의 바다는 같은 물길 위에서도 다른 시대였죠.", "two unmistakably different human groups"),
            ("온조를 지우지 않아도 구태의 수수께끼는 살아남고,", "keeps the unresolved Gutae question alive"),
            ("결국 백제의 출생증명서는 한 장이 아니라 여러 장이었습니다.", "different surviving Baekje origin account"),
            ("국호도 백성이 즐겨 따랐다는 설명과 백가가 바다를 건넜다는 설명으로 갈렸죠.", "Equal human pairs embody the two name traditions"),
            ("후대의 편찬자들조차 어느 하나를 완전히 지우지 못했습니다.", "preserving rival founding accounts"),
            ("그래서 구태는 가짜 창업자도 확정된 초대왕도 아닌,", "legendary Gutae stands at center in a dark teal robe"),
            ("다음 편은 백제를 연맹의 한 나라에서 중앙집권 국가로 끌어올린 고이왕입니다.", "authority concentrating in the king"),
            ("왕의 옷 색깔까지 권력의 서열이 되는 순간을 다음 편에서 이어가겠습니다.", "clothing color visibly marks rank"),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Eye-level medium shot inside a historically grounded Baekje settlement. "
            "Focused gestures and surrounding reactions make the immediate historical stakes readable."
        )

        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("historically grounded Baekje settlement", compiled.positive)
                self.assertIn("readable writing", compiled.negative)

                if narration.startswith("그래서 구태는 가짜 창업자도"):
                    self.assertNotIn("Present-day", compiled.positive)
                    self.assertNotIn("zip-front", compiled.positive)
                    self.assertNotIn("crew-neck", compiled.positive)

    def test_baekje_marriage_two_shot_blocks_third_face(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Scene: formal marriage reception || Global style: NARRATIVE_FIDELITY_REGEN_V1 || "
            "Narration context: 그런데 구태의 혼인 상대를 따라가면 건국 연대가 수백 년 흔들립니다."
        )

        compiled = self.compile(prompt)
        negative = append_prompt_specific_negative_prompt("", compiled.positive)

        self.assertIn("Two-face-only close-up", compiled.positive)
        self.assertIn("exactly two faces total", compiled.positive)
        self.assertIn("third face", negative)
        self.assertIn("duplicate man", negative)

    def test_present_day_baekje_historians_block_mixed_ancient_costume(self):
        prompt = (
            "Present-day 2020s two-face-only close-up with exactly two faces total: "
            "one Korean woman historian and one Korean man historian in identical modern jackets"
        )

        negative = append_prompt_specific_negative_prompt("", prompt)

        self.assertIn("historical robe on modern historian", negative)
        self.assertIn("topknot on modern male historian", negative)
        self.assertIn("visible hand in face-only crop", negative)

    def test_baekje_founder_comparison_keeps_both_chests_covered(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Scene: generic confrontation || Global style: NARRATIVE_FIDELITY_REGEN_V1 || "
            "Narration context: 이제 두 건국자가 한 왕조 안에서 충돌하기 시작합니다."
        )

        compiled = self.compile(prompt)

        self.assertIn("fully closed plain cross-collar hemp robes", compiled.positive)
        self.assertIn("robe-covered shoulders", compiled.positive)

    def test_narrative_fidelity_limits_hands_in_baekje_record_and_artifact_scenes(self):
        cases = (
            (
                "둘 중 하나를 지우지 않고 모순 자체를 기록한 선택이었죠.",
                "exactly three unarmed adult male chroniclers",
            ),
            (
                "특정 유물을 곧바로 온조나 구태의 소유물이라 부를 수는 없죠.",
                "exactly two adult archaeologists",
            ),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Reaction-focused medium shot beside a weathered record."
        )

        for narration, expected in cases:
            with self.subTest(narration=narration):
                prompt = (
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected, compiled.positive)
                self.assertIn("overlapping hands", compiled.negative)
                self.assertIn("multiple hands on one object", compiled.negative)

    def test_narrative_fidelity_rewrites_generic_baekje_settlement_templates(self):
        cases = (
            ("공손도는 후한 말 요동에서 독자 세력을 키운 군벌이었습니다.", "Gongsun Du stands upright at center", False),
            ("중앙 왕조가 흔들리는 틈을 타 국경 밖까지 영향력을 넓혔고,", "sends two envoys walking outward", False),
            ("그 공손도가 자신의 딸을 구태의 아내로 삼게 했다는 겁니다.", "formally presents his adult daughter", False),
            ("확실한 건 백제 사람들에게조차 기원의 기억이 하나가 아니었다는 점,", "historical review", True),
            ("그렇다면 해양 제국의 씨앗은 정확히 어디에 있었을까요?", "river-coast scene", True),
            ("다음 편은 백제를 연맹의 한 나라에서 중앙집권 국가로 끌어올린 고이왕입니다.", "audience hall", True),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; Scene: Eye-level medium shot inside a historically "
            "grounded Baekje settlement, visualizing this decisive historical beat: The claim changes "
            "how the foundation story is understood. Focused gestures and surrounding reactions make "
            "the immediate historical stakes readable."
        )

        for narration, expected, expects_background_staging in cases:
            with self.subTest(narration=narration):
                prompt = (
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("historically grounded Baekje settlement", compiled.positive)
                if expects_background_staging:
                    self.assertIn("Peaceful background staging", compiled.positive)
                self.assertNotIn("generic warrior crowd", compiled.positive)

    def test_narrative_fidelity_repairs_baekje_modern_research_and_cta_scenes(self):
        cases = (
            (
                "특정 유물을 곧바로 온조나 구태의 소유물이라 부를 수는 없죠.",
                ("exactly two adult archaeologists", "present-day Korean archaeological", "modern plain field jackets"),
            ),
            (
                "그 차이를 구분해야 구태 이야기도 과장 없이 더 흥미로워집니다.",
                ("exactly three adult historians", "present-day Korean archaeological", "modern plain field jackets"),
            ),
            (
                "백제의 다음 권력투쟁이 궁금하시다면 구독과 좋아요로 함께해 주세요.",
                ("exactly three robed men", "foreshadow the next power struggle", "plain timber wall fills every background edge"),
            ),
        )
        source_scene = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; Scene: Closing wide composition across a guarded "
            "Baekje audience hall."
        )

        for narration, expected_parts in cases:
            with self.subTest(narration=narration):
                prompt = (
                    f"{source_scene} || Global style: historical documentary "
                    f"NARRATIVE_FIDELITY_REGEN_V1 || Narration context: {narration}"
                )
                compiled = self.compile(prompt)
                for expected in expected_parts:
                    self.assertIn(expected, compiled.positive)

    def test_narrative_fidelity_repairs_later_baekje_era_and_chiljido_scene(self):
        prompt = (
            "Year/period: Baekje foundation traditions preserved in conflicting later records; "
            "Culture scope: Baekje and Daifang; "
            "Scene: Eye-level medium shot inside an archaeological trench showing seven-color maps. "
            "|| Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1 || "
            "Narration context: 칠지도 같은 유물은 그 복잡한 관계가 물질로 남은 사례죠."
        )

        compiled = self.compile(prompt)

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertIn("Seven-Branched Sword", compiled.positive)
        self.assertIn("present-day conservation room", compiled.positive)
        self.assertIn("fourth-century iron", compiled.positive)
        self.assertNotIn("seven-color maps", compiled.positive)

    def test_narration_aligned_baekje_ep02_preserves_complete_action_and_period(self):
        prompt = (
            "Year/period: Baekje foundation traditions; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene evidence: Source workbook row 02-043; "
            "Scene: Gutae meeting the powerful Liaodong ruler Gongsun Du during a formal "
            "political marriage alliance inside a fortified hall. Korean historical-documentary image; "
            "Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: 곧 요동의 지배자 공손도와 연결되는 장면이 튀어나옵니다"
        )

        compiled = self.compile(prompt)

        self.assertIn("formal political marriage alliance inside a fortified hall", compiled.positive)
        self.assertNotIn("곧 요동의 지배자", compiled.positive)
        self.assertIn("late Han-to-early Three Kingdoms", compiled.positive)
        for term in ("Joseon dynasty palace", "Edo period", "samurai", "katana"):
            self.assertIn(term, compiled.negative)

    def test_narration_aligned_baekje_ep02_turns_abstract_chronology_into_story_frame(self):
        prompt = (
            "Year/period: Baekje foundation traditions; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene: Ancient chronological markers separating the early Baekje founding era from "
            "late Han Liaodong and the later Daifang commandery. Korean historical-documentary image; "
            "Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: 그렇다면 구태가 온조와 같은 시대의 경쟁 창업자였다는 해석은 흔들리고"
        )

        compiled = self.compile(prompt)

        self.assertIn("early Baekje founding party", compiled.positive)
        self.assertIn("late-Han Liaodong ruler and Daifang envoys", compiled.positive)
        self.assertIn("wide empty span of ground", compiled.positive)
        self.assertNotIn("그렇다면 구태가", compiled.positive)

        self.assertTrue(_should_skip_dense_internal_text_grid(prompt))
        self.assertTrue(_should_skip_internal_text_core(prompt))
        record_prompt = prompt.replace(
            "Ancient chronological markers separating the early Baekje founding era from "
            "late Han Liaodong and the later Daifang commandery",
            "Ancient Korean royal genealogies on silk beside two shadowed founders",
        )
        self.assertTrue(_should_skip_dense_internal_text_grid(record_prompt))
        self.assertFalse(_should_skip_internal_text_core(record_prompt))

    def test_narration_aligned_baekje_ep02_moves_gutae_rite_to_unmarked_courtyard(self):
        prompt = (
            "Year/period: Baekje foundation traditions; "
            "Culture scope: Baekje, Goguryeo, and Daifang Commandery; "
            "Scene: Baekje royal priests conducting a solemn ancestral rite at a shrine dedicated "
            "to Gutae inside an ancient walled capital. Korean historical-documentary image; "
            "Global style: historical documentary NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: 우태와 구태를 포함한 다른 계보에는 의심을 표시했습니다"
        )

        compiled = self.compile(prompt)

        self.assertIn("Exactly two Baekje royal priests", compiled.positive)
        self.assertIn("open-air packed-earth courtyard", compiled.positive)
        self.assertIn("visibly doubtful expression", compiled.positive)
        self.assertNotIn("우태와 구태를", compiled.positive)
        self.assertTrue(_should_skip_dense_internal_text_grid(prompt))
        self.assertTrue(_should_skip_internal_text_core(prompt))

    def test_narration_aligned_ch2_scene_disables_exact_layout_copy_route(self):
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; "
            "Scene evidence: Source workbook scene: population silhouettes and graves show demographic change; "
            "Main subject: migrating families entering a riverside settlement; "
            "Scene: migrating families walk beside solid-wheel wagons toward a riverside settlement; "
            "Global style: hard-boiled cartoon NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: The migration changed the population of Central Europe"
        )

        compiled = self.compile(prompt)

        self.assertIn("migrating families", compiled.positive)
        self.assertNotIn("object-only", compiled.positive.lower())
        self.assertIsNone(_exact_layout_reference_spec(prompt))
        self.assertEqual(
            expected_effective_image_model_id("comfyui-flux2-klein-4b", prompt),
            "comfyui-flux2-klein-4b",
        )

    def test_narration_aligned_ch2_text_risk_becomes_blank_physical_action(self):
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; "
            "European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
            "Yamnaya cultural horizon, Neolithic European communities; "
            "Main subject: Yamnaya wagon column with copper weapons and families moving "
            "beneath branching Indo-European language symbols; "
            "Scene: Yamnaya wagon column with copper weapons and families moving beneath "
            "branching Indo-European language symbols, archaeologically grounded late "
            "Neolithic and early Bronze Age reconstruction with tense human storytelling; "
            "Global style: stylish adult hard-boiled historical action cartoon, rough "
            "extra-thick bold black ink contour lines, matte cel shading, dry-brush texture, "
            "hard-edged deep black shadow masses NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: Their movement spread Indo-European languages"
        )

        compiled = self.compile(prompt)

        self.assertTrue(compiled.positive.startswith("Style: 2D hard-boiled"))
        self.assertIn("full-body Yamnaya family migration", compiled.positive)
        self.assertIn("one woman, one man, two children", compiled.positive)
        self.assertIn("two pack oxen", compiled.positive)
        self.assertIn("two broad parallel transport ruts", compiled.positive)
        self.assertNotIn("language symbols", compiled.positive)
        self.assertNotIn("object-only", compiled.positive.lower())
        self.assertIn("hands remain secondary", compiled.positive)
        self.assertIn("visible wheel", compiled.negative)
        self.assertIn("all-male group", compiled.negative)
        self.assertIsNone(compiled.person_count)
        self.assertTrue(_should_check_internal_text_after_generation(prompt))
        self.assertTrue(_should_skip_dense_internal_text_grid(prompt))
        self.assertFalse(_should_skip_internal_text_core(prompt))
        self.assertTrue(
            _should_use_physicalized_narration_text_detector(prompt, compiled.positive)
        )

    def test_narration_aligned_ch2_early_scenes_stay_human_and_story_driven(self):
        cases = (
            (
                "Ancient skeleton overlaid with a bold seventy-five percent ancestry connection to the Pontic-Caspian grasslands",
                ("present-day archaeogeneticist", "eastern-steppe women, men, and children"),
            ),
            (
                "Ochre-covered male burial beneath a kurgan with wagon wheels, dagger, animal offerings, and silent mourners",
                ("Adult Yamnaya mourners gather", "bare steppe soil fills every frame edge"),
            ),
            (
                "Yamnaya chief and farmer elder facing each other between armed followers and exchanged prestige gifts",
                ("folded wool cloak", "small grain sack"),
            ),
            (
                "Wide Pontic-Caspian grassland between distant rivers with cattle camps and wooden wagons",
                ("full-body adult herder households", "move cattle on foot"),
            ),
            (
                "High panoramic view of steppe routes between the Black Sea, Caspian Sea, Dnieper, Don, and Volga",
                ("adult herder households and cattle", "travel on foot"),
            ),
            (
                "Cattle searching sparse winter grass beside a frozen river and a worried pastoral camp",
                ("two low hide tents", "no permanent building or chimney"),
            ),
            (
                "Young herder driving cattle while families repair an ox-drawn wagon during a cold migration",
                ("one adult woman secures a closed food pack", "parallel transport ruts"),
            ),
            (
                "Seasonal Yamnaya camp being dismantled as wagons form a departing column",
                ("Full-body Yamnaya adults dismantle", "gather children and cattle"),
            ),
            (
                "Gorodtsov recording an exposed pit grave near the Donets River with early excavation workers",
                ("dark 1901 high-collar field coat", "1901-1903 AD"),
            ),
            (
                "Gorodtsov comparing three distinct grave plans on a field table beside excavated mounds",
                ("three adjacent top-open rectangular trenches", "1901-1903 AD"),
            ),
            (
                "Anonymous Yamnaya chief silhouetted before assembled clans with no inscription or written record",
                ("three-quarter full-body view", "visible weathered face"),
            ),
            (
                "Mobile wagons approaching the fortified riverside settlement of Mykhailivka on the lower Dnieper",
                ("packed-earth rampart scattered with loose irregular fieldstones", "no structure rising above it"),
            ),
            (
                "Anthropomorphic stone stela with carved belt, hands, axe, and dagger overlooking a burial",
                ("upright flat weathered stone slab", "living mourners dominate"),
            ),
            (
                "Busy Yamnaya camp with herding, fishing, pottery making, food preparation, and copper working",
                ("woman shapes a simple hand-built clay pot", "adult casts a net"),
            ),
            (
                "Long wagon column crossing exposed grassland under the watch of mounted scouts and armed leaders",
                ("walks on foot at center", "organized migration line"),
            ),
            (
                "Layered kurgan cross-section with successive burials arranged above the founding grave",
                ("Exactly two fully wrapped motionless bodies", "bare empty steppe fills"),
            ),
            (
                "Small group of elite male graves contrasted with a much larger living Yamnaya population",
                ("Three small separated foreground pits", "living community member remains at ground level"),
            ),
            (
                "Complete four-wheeled wooden wagon lowered into a deep grave beside the deceased chief",
                ("full-body adult mourners strain on fibre ropes", "undercarriage stays below"),
            ),
            (
                "Exhausted workers and oxen surrounding the chief's wagon burial as elite relatives supervise",
                ("Exhausted full-body workers", "completely hide its undercarriage"),
            ),
            (
                "Metalworker raising a newly cast copper blade beside a glowing crucible and watching chiefs",
                ("small cooled leaf-shaped copper blade blank", "fist-sized clay crucible"),
            ),
            (
                "Copper daggers, axes, spearheads, and ornaments arranged around one richly furnished burial",
                ("Adult elite mourners kneel", "ordinary herder families"),
            ),
            (
                "Reich comparing ancient Y chromosomes, rich male graves, and a narrowing ancestry chart",
                ("Present-day geneticist David Reich", "two adult research colleagues"),
            ),
            (
                "Young herder riding a compact steppe horse beside cattle with anatomical bone details inset",
                ("present-day excavation", "young unarmed herder seated bareback"),
            ),
            (
                "Archaeologists comparing disputed riding traces, horse teeth, and genetic timelines at an excavation",
                ("present-day adult horse researchers", "uncertain context on a blank clipboard"),
            ),
            (
                "Yamnaya migrants with ox wagons and a few riders, deliberately avoiding a mass cavalry charge",
                ("broad civilian Yamnaya community", "no military formation or charging movement"),
            ),
            (
                "Ox-drawn carts and wagons loaded with hides, vessels, food, tools, and families",
                ("Full-body Yamnaya adults and children", "families remain the dominant subject"),
            ),
            (
                "Powerful oxen straining against a loaded four-wheeled wagon on rough steppe ground",
                ("Two powerful oxen strain", "completely hide its undercarriage"),
            ),
            (
                "Families, cattle, wagons, ritual objects, and messengers moving along interconnected steppe routes",
                ("Full-body families and children walk", "adult messenger meets another family"),
            ),
            (
                "Yamnaya families dividing between two wagon columns while chiefs negotiate beside a fire",
                ("family groups depart on foot", "marriage pair stands between"),
            ),
            (
                "Multiple independent chiefs connected by marriage gifts, cattle exchanges, and shared burial customs",
                ("loose open circle with equal status", "welcomes a marriage pair"),
            ),
            (
                "Chain of matching kurgans stretching between the Dnieper, Don, and Volga river landscapes",
                ("high continuous panorama", "shorter than a standing adult"),
            ),
            (
                "Wagon column descending toward Danube farmland, timber houses, fields, and defensive fences",
                ("Mixed Yamnaya families descend on foot", "no building visible"),
            ),
            (
                "Yamnaya chief and farmer elder studying each other's cattle, fields, weapons, and households",
                ("one Yamnaya chief in a plain wool", "fenced barley field"),
            ),
            (
                "Central European farming village facing a temporary Yamnaya camp across a river",
                ("farming women, men, and children harvest", "pack oxen carrying rolled hide shelters"),
            ),
            (
                "Exchange feast shadowed by armed guards, a marriage procession, tense bargaining, and burned fencing",
                ("one continuous outdoor lower-Danube frontier scene", "plain brown or ochre woven"),
            ),
            (
                "Excavators carefully examining a burned house and injured skeleton without assigning an attacker",
                ("present-day adult excavators", "no attacker and no active violence"),
            ),
            (
                "Population silhouettes shifting dramatically as steppe ancestry spreads into Central Europe",
                ("large mixed community", "demographic scale"),
            ),
            (
                "Close view of hands pressing twisted cord into the surface of a wet clay beaker",
                ("full-body adult Corded Ware potter", "small working hands"),
            ),
            (
                "Corded Ware funeral with cord-decorated pottery, stone battle-axe, wool clothing, and single burial",
                ("women, men, children, and elders", "rigid horizontal human-sized burial bundle", "shroud is tied closed at both ends"),
            ),
            (
                "Corded Ware warrior buried alone with polished battle-axe and corded beaker",
                ("three separate parallel raw-earth grave pits", "mourners stand behind the pits outside every rim"),
            ),
            (
                "Yamnaya kurgan and Corded Ware grave linked by ancestry strands despite different burial arrangements",
                ("present-day adult archaeogeneticists", "different burial customs"),
            ),
            (
                "Ancient-DNA researchers sampling teeth and sequencing genomes across a map of prehistoric Europe",
                ("sterile 2015 ancient-DNA clean room", "laboratory coats, hair covers, face masks, and nitrile gloves"),
            ),
            (
                "Corded Ware warrior portrait formed from three parts steppe ancestry and one part local ancestry",
                ("Corded Ware household of women, men, and children", "one continuous human community"),
            ),
            (
                "Dense east-to-west migration arrows carrying families into Central European river valleys",
                ("full-body eastern-steppe families", "without military formation"),
            ),
            (
                "Yamnaya-related families arriving with children, livestock, wagons, tools, and household goods",
                ("Living Yamnaya-related women, men, and children", "without any vehicle"),
            ),
            (
                "Generations of Central European families connected through an enduring steppe ancestry line",
                ("elders, adult women and men", "persist naturally across mixed families"),
            ),
            (
                "Layered portraits of later European populations built from multiple ancestry streams without racial typology",
                ("Present-day European women and men", "visibly modern rather than a racial lineup"),
            ),
            (
                "Farming valley transforming as new households, graves, animals, and customs fill the region",
                ("much larger stream of full-body", "no pottery display"),
            ),
            (
                "Farmer families choosing among retreat, guarded resistance, intermarriage, and alliance with migrants",
                ("mixed local farmer family debates", "every civilian remains unarmed"),
            ),
            (
                "Panoramic Corded Ware cultural zone spanning forests, rivers, farmland, and eastern grassland",
                ("unarmed full-body Corded Ware families travel", "no freestanding structure, roofline"),
            ),
            (
                "Travelers carrying corded pottery and axes between distant but related settlements",
                ("Two mixed-age civilian households", "children and elders exchange food"),
            ),
            (
                "Bell Beaker archer arriving in western Europe with distinctive vessel, wrist guard, and mixed ancestry",
                ("mixed Bell Beaker household", "local farming family", "civilians and family contact dominating"),
            ),
            (
                "Migration paths continuing east toward fortified Sintashta settlements and later Andronovo herders",
                ("foreground mother leading a child", "low oval Sintashta fortification", "only low roof caps and entrances rise above ground"),
            ),
            (
                "Branching migration routes crossing, merging, and turning back across Eurasia over generations",
                ("wide Eurasian grassland crossroads", "Women carrying wrapped infants and older children"),
            ),
            (
                "Separate migrant columns carrying different combinations of livestock, tools, rituals, and ancestry",
                ("three clearly separated foreground adult women", "each walk beside one child", "Directly behind every woman-child pair"),
            ),
            (
                "Family tree of languages crossing but not perfectly matching an ancient ancestry map",
                ("migrant woman and one local man translate", "children repeat newly learned speech"),
            ),
            (
                "Village assembly divided between steppe migrants and local speakers during a tense negotiation",
                ("mixed-age prehistoric village assembly", "plain long-sleeved woven tunic"),
            ),
            (
                "Gimbutas tracing a connection from kurgans to a branching Proto-Indo-European language map",
                ("adult woman archaeologist Marija Gimbutas", "unmarked cords embedded in clay"),
            ),
            (
                "Armed mobile herders approaching a prosperous Neolithic farming settlement under Gimbutas's model",
                ("Under Gimbutas's interpretive reconstruction", "every surface blank", "no title area or writing"),
            ),
            (
                "Dramatic invasion mural breaking apart into scattered graves, settlements, and uncertain archaeological traces",
                ("full-body present-day archaeologists", "researchers confer with blank notebooks", "People dominate, with no battlefield, mural"),
            ),
            (
                "Farmer elder weighing a stone axe against offered copper weapon and marriage bracelet",
                ("local farming elder stands", "elder studies both groups with empty hands"),
            ),
            (
                "Village factions split as the farmer elder chooses between armed resistance and alliance",
                ("local farming elder steps toward", "long-sleeved prehistoric woven tunic"),
            ),
            (
                "Local chiefs entering a compact migrant coalition around a shared feast and weapons display",
                ("local elite couple and their children", "small dark undecorated handmade clay bowls", "no weapon is visible"),
            ),
            (
                "Copper dagger, rare ornament, livestock gift, and polished axe displayed before watching villagers",
                ("small shaggy dark-brown steppe cow", "same low rope lead rather than shake hands", "mixed families of women, men, children"),
            ),
            (
                "Wedding between steppe migrant and farming family before two watchful kin groups",
                ("adult migrant-local marriage pair", "Women, men, children, and elders"),
            ),
            (
                "Young villagers learning elite speech during feasting, oath making, guard service, and courtship",
                ("full-bleed feast scene with uninterrupted open sky", "long-sleeved prehistoric woven tunics", "copy an interpreter's mouth movements"),
            ),
            (
                "Three generations of one mixed household shifting gradually from local speech to steppe-derived speech",
                ("grandparent speaks to two adult parents", "Three generations remain clearly visible"),
            ),
            (
                "Towering kurgan overlooking smaller farms, paths, and graves across a settled valley",
                ("very low, wide, gently sloped earthen kurgan", "rising no higher than two standing adults", "stand upright in a loose arc"),
            ),
            (
                "One ancestral speech line dividing into increasingly distinct regional conversations",
                ("several separate full-body family clusters", "Every cluster visibly includes an adult woman", "continuous leggings covering both lower legs"),
            ),
            (
                "Single wagon route dividing into several independent migration columns under rival leaders",
                ("Several independent mixed-age civilian migration groups diverge on foot", "without central command"),
            ),
            (
                "Kin group, cattle, wagon wheel, and ritual fire linked to reconstructed word roots",
                ("complete low loaded wooden cart", "Two visible knee-high solid plank disk wheels", "nobody touches, holds, carries, or fits a wheel"),
            ),
            (
                "Steppe speakers learning local words while working fields and entering European forests",
                ("two compact shaggy dark-brown oxen", "one simple all-wood ard", "nobody holds any digging tool"),
            ),
            (
                "Mixed household speaking across generations during farming, herding, marriage, and ritual",
                ("On open grassland with no building", "mixed three-generation household", "continuous leggings covering both lower legs"),
            ),
            (
                "Branching language tree rising behind early European communities without modern national symbols",
                ("One unbroken wide landscape", "continuous ground and open sky", "appear at different depths"),
            ),
            (
                "Blank centuries between prehistoric migration maps and the first written Indo-European texts",
                ("Three full-body present-day researchers", "three faint ancient footpaths", "Every surface and sky is blank"),
            ),
            (
                "Battle-axe, ancient skeleton, and comparative word list aligned as three evidence columns",
                ("three full-body specialists in modern field jackets", "woman archaeologist indicates one grave", "closed blank notebook"),
            ),
            (
                "Three overlapping maps from archaeology, genetics, and linguistics with mismatched boundaries",
                ("present-day field station", "woman archaeologist", "conflicting judgments dominate"),
            ),
            (
                "Yamnaya family emerging from two older ancestry streams meeting north of the Caucasus",
                ("eastern hunter-gatherer family", "Caucasus-related pastoral family", "care for one child"),
            ),
            (
                "Pre-Yamnaya communities connected between the Caucasus foothills and lower Volga river",
                ("open river corridor", "mixed-age civilian households", "horizon is empty grassland"),
            ),
            (
                "Multiple older communities merging into the Yamnaya horizon before its expansion",
                ("Several mixed-age civilian households", "one shared open-air resting place", "only structure in the frame"),
            ),
            (
                "Four predecessor cultural zones converging around early Yamnaya settlements and graves",
                ("Four clearly separated mixed-age civilian family groups", "women and children", "long-sleeved prehistoric woven tunic"),
            ),
            (
                "Researchers debating separate maps of language origin, ancestry formation, and cultural development",
                ("mixed team of full-body present-day women and men", "Everyone is empty-handed", "completely bare soil"),
            ),
            (
                "Y chromosome lineages from Yamnaya graves failing to align perfectly with Corded Ware men",
                ("present-day ancient-DNA field lab", "mixed adult team of women and men", "Everyone is empty-handed"),
            ),
            (
                "Complex ancestry network replacing a simplistic arrow from one Yamnaya man to all Europeans",
                ("several mixed local and steppe-descended families", "different connected tasks", "The empty horizon"),
            ),
            (
                "Corded Ware settlement containing mixed families, local farming tools, steppe customs, and new graves",
                ("mixed local and migrant Corded Ware families", "migrant-local couple twists fibre rope", "empty horizon contains only grass and cattle"),
            ),
            (
                "Corded Ware community transitioning into Bell Beaker and later Bronze Age cultural scenes",
                ("mixed Corded Ware and Bell Beaker network households", "riverside meadow", "changing social networks dominate"),
            ),
            (
                "Successive generations passing movement, authority, and ancestry across a changing European map",
                ("Several generations of mixed women, men, and children", "grandparents pass a cattle lead", "daily movement"),
            ),
            (
                "Modern researchers entering a museum store filled with carefully boxed prehistoric skeletons",
                ("Three full-body present-day archaeologists", "two still-sealed grave outlines", "grave expressions dominate"),
            ),
            (
                "Gloved technicians processing ancient bone powder through clean laboratory equipment",
                ("mixed adult team in sterile coats", "one enclosed grinder", "every work surface is bare"),
            ),
            (
                "Sequencing screens linking prehistoric individuals across a time-scaled map of Europe",
                ("mixed full-body team of women and men", "face away from the camera", "coordinated analysis"),
            ),
            (
                "Ancient population map showing a major influx from the steppe into Central Europe",
                ("broad civilian movement of mixed-age women, men, children, and elders", "entirely on foot", "immense east-to-west movement"),
            ),
            (
                "Gimbutas's kurgan map beside DNA results with confirmed migration and unconfirmed battle scenes separated",
                ("plain present-day research room", "stand empty-handed face to face", "silent disagreement"),
            ),
            (
                "Mixed-ancestry couple at a prehistoric wedding with uncertain expressions and armed relatives",
                ("one adult migrant-local couple", "mothers, fathers, children, and elders", "unknowable choice dominate"),
            ),
            (
                "Two neighboring villages responding differently to the same approaching migrant group",
                ("one continuous open valley", "left step forward with welcoming expressions", "right-hand families turn away"),
            ),
            (
                "Rapid tableau of a shouted insult, sworn oath, guarded hostage, cattle raid, and handshake",
                ("one continuous open meadow", "a woman elder stands between them", "tense faces carry the uncertainty"),
            ),
            (
                "Individual faces in a tense frontier crowd emerging from an impersonal ancestry graph",
                ("open prehistoric meadow", "one migrant-local couple stays with children", "individual faces and human decisions dominate"),
            ),
            (
                "Competing homeland circles around the steppe, Caucasus, and western Asia",
                ("present-day Caucasus-Lower Volga field overlook", "a woman linguist", "complete bodies and disagreement dominate"),
            ),
            (
                "Firm evidence panel connecting Yamnaya-related groups to major Central European ancestry change",
                ("Yamnaya-related migrant women, men, children, and elders", "Migrant-local couples care for children", "riverside meadow"),
            ),
            (
                "Steppe migration routes aligned with several, but not all, Indo-European language branches",
                ("Several mixed-age steppe-descended families", "travel on foot", "conversations and varied routes dominate"),
            ),
            (
                "Yamnaya chief alive beside a fresh kurgan as followers, wagons, and herds assemble",
                ("anonymous middle-aged Yamnaya chief", "knee-high, very low, wide", "remains on flat ground"),
            ),
            (
                "Yamnaya chief looking west across empty grassland with distant future maps hidden in clouds",
                ("stands alone in full profile", "entirely empty grassland horizon", "natural blank clouds"),
            ),
            (
                "Chief surveying thin pasture, rival campfires, a marriage delegation, and dark winter clouds",
                ("plain close hide cap", "Two rival adult leaders wait apart", "mixed marriage delegation"),
            ),
            (
                "Chief pointing as one wagon group prepares westward and another negotiates with visitors",
                ("same Yamnaya chief in a plain close hide cap", "mixed families begin walking west", "form an alliance"),
            ),
            (
                "Small cattle skirmish contrasted with a vast allied route of camps, rivers, and kurgans",
                ("broad allied migration corridor", "Several mixed-age families relay food", "two herders dispute a single cow"),
            ),
            (
                "Wagons, marriage bonds, elite graves, armed retainers, and herds forming one power system",
                ("One coordinated Yamnaya civilian community", "one adult marriage pair walks with elders and children", "two empty-handed guards"),
            ),
            (
                "Successive farmer leaders joining the network while children learn the prestige language",
                ("open Corded Ware meadow", "grandparents, parents, and children speak face to face", "Children answer the adults"),
            ),
            (
                "Mixed children growing into a distinct Corded Ware community unlike either original group",
                ("mixed local-steppe children and adolescents", "every child and adult wears", "active learning dominate"),
            ),
            (
                "Night-to-dawn sequence of camps and graves spreading gradually across a European landscape",
                ("One continuous dawn panorama", "knee-high smooth sealed grave mound", "distant families walk toward a new horizon"),
            ),
            (
                "Opened graves and DNA charts surrounding unseen prehistoric negotiations beneath the soil",
                ("mixed full-body team of women and men", "several still-sealed grave outlines", "completely bare unmarked soil"),
            ),
            (
                "Horse beside an Indo-European royal sacrifice ground as priests and a tense claimant approach",
                ("open packed-earth ritual ground", "living unsaddled royal horse", "plain wrapped headcloth"),
            ),
            (
                "Priests arranging a horse sacrifice while the future king faces assembled warriors",
                ("Exactly three bare-headed adults", "one clear ritual hierarchy", "no horse, rider"),
            ),
            (
                "Horse-sacrifice traditions connected across the steppe, ancient India, Rome, and medieval Ireland",
                ("FOUR AND ONLY FOUR unmounted adult cultural delegates", "one waist-up group portrait", "No fifth person, horse"),
            ),
            (
                "Royal horse entering a guarded ritual enclosure before a crowd of rival nobles",
                ("HORSE-ONLY SCENE", "exactly one calm living horse", "no human, rider, saddle"),
            ),
            (
                "Abandoned Neolithic house beneath a later Corded Ware settlement with missing family silhouettes",
                ("three full-body archaeologists", "shallow scraped soil surface", "Empty Neolithic postholes and a dark hearth stain"),
            ),
            (
                "Ancient DNA chart fading into a tense face-to-face meeting between chiefs and villagers",
                ("migrant chief and local farming elders", "everyone is unarmed"),
            ),
            (
                "Table of battle-axes, copper daggers, beakers, marriage gifts, and burial plans under study",
                ("Three full-body present-day scholars", "still-sealed double-grave outline", "discussion of changing institutions dominates"),
            ),
            (
                "Gimbutas arranging kurgan maps, warrior stelae, and Old European settlement photographs",
                ("adult woman archaeologist Marija Gimbutas", "only woman and lead scholar"),
            ),
            (
                "Anthony comparing Gimbutas's invasion arrows with a network of alliances and elite contacts",
                ("Present-day archaeologist David Anthony", "no Gimbutas depiction"),
            ),
            (
                "Reich's laboratory sampling a petrous bone in a sterile clean room",
                ("present-day ancient-DNA clean room", "one sealed tiny sample tube", "Only that single tube is visible"),
            ),
            (
                "Scientists watching a clear steppe ancestry cluster emerge from ancient genome data",
                ("2015 modern ancient-DNA laboratory", "coordinated response dominate"),
            ),
            (
                "Klejn challenging a straight migration arrow with alternative ancestry distributions on a map",
                ("Late-twentieth-century archaeologist Leo Klejn", "mixed team of women and men", "completely clean bare floor"),
            ),
            (
                "Updated research map moving the earliest language origin toward the Caucasus-Lower Volga zone",
                ("present-day Lower Volga field overlook", "mixed full-body team of women and men", "stands empty-handed"),
            ),
            (
                "Ancient skull, wagon track, kurgan, and mixed family joined in a final cinematic tableau",
                (
                    "mixed-age prehistoric family gathers in grief",
                    "low smooth solid kurgan with no entrance, opening, poles, or structure",
                    "rigid horizontal human-sized burial bundle",
                    "opaque hide shroud seals the whole body",
                    "no head, face, hands, feet, or skin visible",
                ),
            ),
        )
        for scene, expected_phrases in cases:
            with self.subTest(scene=scene):
                prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary "
                    "scene, 3500 BCE to 2000 BCE; Exact place: Pontic-Caspian Steppe, Balkans, "
                    "Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
                    f"Main subject: {scene}; Scene: {scene}, archaeologically grounded late "
                    "Neolithic and early Bronze Age reconstruction; Global style: stylish adult "
                    "hard-boiled historical action cartoon, rough extra-thick bold black ink "
                    "contour lines NARRATIVE_FIDELITY_REGEN_V1; NARRATION VISUAL ALIGNMENT: "
                    "match the spoken moment; Narration context: historical evidence"
                )
                compiled = self.compile(prompt)
                for expected in expected_phrases:
                    self.assertIn(expected, compiled.positive)
                self.assertNotIn("object-only", compiled.positive.lower())
                self.assertNotIn("exactly four objects", compiled.positive.lower())
                self.assertNotIn("artifact arrangement dominates", compiled.positive.lower())
                self.assertIn("spoked wheel", compiled.negative)
                if scene.startswith("Layered kurgan"):
                    self.assertIn("Christian cross", compiled.negative)
                if scene.startswith("Small group of elite"):
                    self.assertIn("all-male living crowd", compiled.negative)
                if scene.startswith(("Complete four-wheeled", "Exhausted workers")):
                    self.assertIn("open wheel frame", compiled.negative)
                if scene.startswith("Metalworker"):
                    self.assertIn("large sword", compiled.negative)
                    self.assertIn("metal cauldron", compiled.negative)
                if scene.startswith("Copper daggers"):
                    self.assertIn("treasure chest", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith("Mobile wagons approaching"):
                    self.assertIn("standing building", compiled.negative)
                    self.assertIn("pitched roofline", compiled.negative)
                if scene.startswith("Anthropomorphic stone stela"):
                    self.assertIn("naturalistic statue", compiled.negative)
                    self.assertIn("muscular stone man", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith("Reich comparing"):
                    self.assertIn("present-day ancient-DNA laboratory", compiled.positive)
                    self.assertIn("speech bubble", compiled.negative)
                    self.assertIn("prehistoric clothing on modern scientist", compiled.negative)
                    self.assertIn("wall poster", compiled.negative)
                if scene.startswith(("Young herder riding", "Archaeologists comparing", "Excavators carefully", "Yamnaya kurgan", "Ancient-DNA researchers")):
                    self.assertIn("prehistoric clothing on modern researcher", compiled.negative)
                if scene.startswith("Yamnaya migrants"):
                    self.assertIn("cavalry charge", compiled.negative)
                    self.assertIn("3300-2600 BCE", compiled.positive)
                if scene.startswith(("Ox-drawn carts", "Powerful oxen")):
                    self.assertIn("open wheel frame", compiled.negative)
                    self.assertIn("radial plank seams", compiled.negative)
                if scene.startswith(("Families, cattle", "Yamnaya families dividing")):
                    self.assertIn("covered vehicle", compiled.negative)
                if scene.startswith("Multiple independent chiefs"):
                    self.assertIn("title text", compiled.negative)
                    self.assertIn("all-male warrior crowd", compiled.negative)
                if scene.startswith("Chain of matching kurgans"):
                    self.assertIn("literal metal chain", compiled.negative)
                    self.assertIn("pyramid", compiled.negative)
                if scene.startswith("Wagon column descending"):
                    self.assertIn("log cabin", compiled.negative)
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Yamnaya chief and farmer elder studying"):
                    self.assertIn("both leaders as pastoral herders", compiled.negative)
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Central European farming village"):
                    self.assertIn("all-male groups", compiled.negative)
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Exchange feast"):
                    self.assertIn("tablecloth", compiled.negative)
                    self.assertIn("vertical divider", compiled.negative)
                    self.assertIn("white wedding gown", compiled.negative)
                    self.assertIn("plate armor", compiled.negative)
                if scene.startswith(("Population silhouettes", "Corded Ware warrior portrait", "Dense east-to-west", "Generations of Central")):
                    self.assertIn("all-male population", compiled.negative)
                if scene.startswith("Population silhouettes"):
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Corded Ware warrior portrait"):
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Close view of hands"):
                    self.assertIn("macro hand shot", compiled.negative)
                if scene.startswith("Corded Ware funeral"):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("all-male mourners", compiled.negative)
                    self.assertIn("visible face on shrouded body", compiled.negative)
                    self.assertIn("oversized pottery", compiled.negative)
                    self.assertIn("stone coffin", compiled.negative)
                    self.assertIn("grave goods outside pit", compiled.negative)
                if scene.startswith("Corded Ware warrior buried"):
                    self.assertIn("single shared grave", compiled.negative)
                    self.assertIn("opposite body orientation", compiled.negative)
                    self.assertIn("face-down body", compiled.negative)
                    self.assertIn("artifact pile", compiled.negative)
                    self.assertIn("living man in grave", compiled.negative)
                    self.assertIn("grave goods outside pit", compiled.negative)
                if scene.startswith("Yamnaya kurgan"):
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith("Ancient skeleton"):
                    self.assertIn("modern house", compiled.negative)
                    self.assertIn("second modern scientist", compiled.negative)
                    self.assertIn("all-male migrant line", compiled.negative)
                if scene.startswith("Ancient-DNA researchers"):
                    self.assertIn("all-male laboratory team", compiled.negative)
                    self.assertIn("oversized bone", compiled.negative)
                    self.assertIn("wall poster", compiled.negative)
                    self.assertIn("framed paper", compiled.negative)
                    self.assertIn("bare hands handling specimen", compiled.negative)
                if scene.startswith("Yamnaya-related families"):
                    self.assertIn("wagon", compiled.negative)
                    self.assertIn("artifact arrangement", compiled.negative)
                if scene.startswith("Generations of Central"):
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Layered portraits"):
                    self.assertIn("prehistoric clothing", compiled.negative)
                    self.assertIn("all-male lineup", compiled.negative)
                if scene.startswith("Farming valley transforming"):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("building", compiled.negative)
                if scene.startswith("Farmer families choosing"):
                    self.assertIn("all-male group", compiled.negative)
                    self.assertIn("armed standoff", compiled.negative)
                if scene.startswith("Panoramic Corded Ware"):
                    self.assertIn("armed traveler", compiled.negative)
                    self.assertIn("artifact display", compiled.negative)
                    self.assertIn("timber house", compiled.negative)
                    self.assertIn("roofline", compiled.negative)
                if scene.startswith((
                    "Travelers carrying",
                    "Bell Beaker archer",
                    "Migration paths continuing east",
                    "Branching migration routes",
                    "Separate migrant columns",
                    "Family tree of languages",
                    "Village assembly divided",
                )):
                    self.assertIn("all-male war band", compiled.negative)
                    self.assertIn("readable writing", compiled.negative)
                    self.assertIn("firearm", compiled.negative)
                if scene.startswith("Armed mobile herders"):
                    self.assertIn("rifle", compiled.negative)
                    self.assertIn("all-male raiding party", compiled.negative)
                if scene.startswith("Dramatic invasion mural"):
                    self.assertIn("text banner", compiled.negative)
                    self.assertIn("battlefield map", compiled.negative)
                if scene.startswith((
                    "Farmer elder weighing",
                    "Village factions split",
                    "Local chiefs entering",
                    "Copper dagger, rare ornament",
                    "Wedding between steppe migrant",
                    "Young villagers learning",
                    "Three generations of one mixed",
                )):
                    self.assertIn("artifact table", compiled.negative)
                    self.assertIn("all-male council", compiled.negative)
                    self.assertIn("speech bubble", compiled.negative)
                if scene.startswith("Local chiefs entering"):
                    self.assertIn("glazed white plate", compiled.negative)
                if scene.startswith("Copper dagger, rare ornament"):
                    self.assertIn("Holstein cow", compiled.negative)
                if scene.startswith("Towering kurgan"):
                    self.assertIn("doorway in mound", compiled.negative)
                    self.assertIn("wooden poles on mound", compiled.negative)
                    self.assertIn("mountain-sized mound", compiled.negative)
                    self.assertIn("shrouded body", compiled.negative)
                if scene.startswith("One ancestral speech line"):
                    self.assertIn("speech bubble", compiled.negative)
                    self.assertIn("split panel", compiled.negative)
                    self.assertIn("vertical divider", compiled.negative)
                    self.assertIn("stationary gathering", compiled.negative)
                    self.assertIn("log cabin", compiled.negative)
                    self.assertIn("missing mother", compiled.negative)
                if scene.startswith("Single wagon route"):
                    self.assertIn("wagon", compiled.negative)
                    self.assertIn("spoked wheel", compiled.negative)
                    self.assertIn("all-male column", compiled.negative)
                    self.assertIn("Christian cross", compiled.negative)
                    self.assertIn("Holstein cow", compiled.negative)
                if scene.startswith("Kin group, cattle"):
                    self.assertIn("giant foreground wheel", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("person touching wheel", compiled.negative)
                if scene.startswith("Steppe speakers learning"):
                    self.assertIn("modern shovel", compiled.negative)
                    self.assertIn("all-male work crew", compiled.negative)
                    self.assertIn("pitchfork", compiled.negative)
                if scene.startswith("Mixed household speaking"):
                    self.assertIn("speech bubble", compiled.negative)
                    self.assertIn("large title", compiled.negative)
                    self.assertIn("building interior", compiled.negative)
                    self.assertIn("Holstein cow", compiled.negative)
                if scene.startswith("Branching language tree"):
                    self.assertIn("group portrait", compiled.negative)
                    self.assertIn("tree diagram", compiled.negative)
                    self.assertIn("split panel", compiled.negative)
                    self.assertIn("vertical divider", compiled.negative)
                if scene.startswith("Blank centuries between"):
                    self.assertIn("large title", compiled.negative)
                    self.assertIn("artist signature", compiled.negative)
                if scene.startswith("Battle-axe, ancient skeleton"):
                    self.assertIn("evidence columns", compiled.negative)
                    self.assertIn("skeleton display", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith("Three overlapping maps"):
                    self.assertIn("map-shaped slab", compiled.negative)
                    self.assertIn("ancient warrior", compiled.negative)
                if scene.startswith("Yamnaya family emerging"):
                    self.assertIn("all-male group", compiled.negative)
                    self.assertIn("ancestry stream graphic", compiled.negative)
                if scene.startswith("Pre-Yamnaya communities connected"):
                    self.assertIn("armed standoff", compiled.negative)
                    self.assertIn("military formation", compiled.negative)
                if scene.startswith("Multiple older communities merging"):
                    self.assertIn("male lineup", compiled.negative)
                    self.assertIn("weapon", compiled.negative)
                if scene.startswith("Four predecessor cultural zones"):
                    self.assertIn("all-male debate", compiled.negative)
                    self.assertIn("armed standoff", compiled.negative)
                if scene.startswith("Researchers debating separate maps"):
                    self.assertIn("prehistoric clothing on researcher", compiled.negative)
                    self.assertIn("language map", compiled.negative)
                    self.assertNotIn("plain woven wrap tunics", compiled.positive)
                if scene.startswith("Y chromosome lineages"):
                    self.assertIn("Y chromosome graphic", compiled.negative)
                    self.assertIn("long sword", compiled.negative)
                    self.assertNotIn("plain woven wrap tunics", compiled.positive)
                if scene.startswith("Complex ancestry network"):
                    self.assertIn("single Yamnaya man", compiled.negative)
                    self.assertIn("all-male war band", compiled.negative)
                    self.assertIn("ancestry network diagram", compiled.negative)
                if scene.startswith("Corded Ware settlement containing"):
                    self.assertIn("all-male work crew", compiled.negative)
                    self.assertIn("modern broom", compiled.negative)
                    self.assertIn("pottery display", compiled.negative)
                if scene.startswith((
                    "Corded Ware community transitioning",
                    "Successive generations passing",
                    "Modern researchers entering",
                    "Gloved technicians processing",
                    "Sequencing screens linking",
                    "Ancient population map showing",
                    "Gimbutas's kurgan map beside",
                )):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("all-male group", compiled.negative)
                    self.assertIn("readable writing", compiled.negative)
                if scene.startswith((
                    "Modern researchers entering",
                    "Gloved technicians processing",
                    "Sequencing screens linking",
                    "Gimbutas's kurgan map beside",
                )):
                    self.assertNotIn("plain woven wrap tunics", compiled.positive)
                if scene.startswith((
                    "Mixed-ancestry couple",
                    "Two neighboring villages",
                    "Rapid tableau of a shouted insult",
                    "Individual faces in a tense frontier crowd",
                    "Competing homeland circles",
                    "Firm evidence panel connecting",
                )):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("split panel", compiled.negative)
                    self.assertIn("all-male group", compiled.negative)
                if scene.startswith((
                    "Steppe migration routes aligned",
                    "Yamnaya chief alive beside",
                    "Yamnaya chief looking west",
                    "Chief surveying thin pasture",
                    "Chief pointing as one wagon group",
                    "Small cattle skirmish contrasted",
                    "Wagons, marriage bonds",
                )):
                    self.assertIn("spoked wheel", compiled.negative)
                    self.assertIn("conical tent", compiled.negative)
                    self.assertIn("all-male group", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith((
                    "Successive farmer leaders joining",
                    "Mixed children growing",
                    "Night-to-dawn sequence",
                    "Opened graves and DNA charts",
                    "Horse beside an Indo-European",
                    "Priests arranging a horse sacrifice",
                    "Horse-sacrifice traditions connected",
                    "Royal horse entering",
                )):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("exposed bones", compiled.negative)
                    self.assertIn("all-male group", compiled.negative)
                    self.assertIn("horse saddle", compiled.negative)
                    self.assertIn("dead horse", compiled.negative)
                if scene.startswith((
                    "Horse beside an Indo-European",
                    "Priests arranging a horse sacrifice",
                    "Royal horse entering",
                )):
                    self.assertIn("first millennium BCE", compiled.positive)
                    self.assertIn("living unsaddled horse", compiled.positive)
                if scene.startswith("Abandoned Neolithic"):
                    self.assertIn("military uniform", compiled.negative)
                    self.assertIn("all-male archaeologist team", compiled.negative)
                    self.assertIn("deep trench", compiled.negative)
                    self.assertIn("missing archaeologists", compiled.negative)
                    self.assertIn("ghost silhouette", compiled.negative)
                    self.assertIn("barn", compiled.negative)
                    self.assertIn("standing structure", compiled.negative)
                if scene.startswith("Ancient DNA chart"):
                    self.assertIn("DNA chart", compiled.negative)
                    self.assertIn("all-male meeting", compiled.negative)
                if scene.startswith("Table of battle-axes"):
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("exposed bones", compiled.negative)
                    self.assertIn("all-male scholar group", compiled.negative)
                    self.assertIn("empty tabletop", compiled.negative)
                    self.assertIn("foreground artifact", compiled.negative)
                if scene.startswith("Migration paths continuing east"):
                    self.assertIn("giant roundhouse", compiled.negative)
                    self.assertIn("yurt", compiled.negative)
                    self.assertIn("male-dominated foreground", compiled.negative)
                    self.assertIn("above-ground log cabin", compiled.negative)
                    self.assertIn("2100-1500 BCE", compiled.positive)
                if scene.startswith("Separate migrant columns"):
                    self.assertIn("women absent", compiled.negative)
                    self.assertIn("men-only route", compiled.negative)
                    self.assertIn("woman missing from a path", compiled.negative)
                if scene.startswith("Village assembly divided"):
                    self.assertIn("modern T-shirt", compiled.negative)
                    self.assertIn("modern shorts", compiled.negative)
                if scene.startswith("Armed mobile herders approaching"):
                    self.assertIn("large title", compiled.negative)
                    self.assertIn("upper-third lettering", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("modern collared shirt", compiled.negative)
                if scene.startswith("Village factions split"):
                    self.assertIn("modern T-shirt", compiled.negative)
                    self.assertIn("classical temple", compiled.negative)
                    self.assertIn("child in T-shirt", compiled.negative)
                if scene.startswith("Local chiefs entering"):
                    self.assertIn("drawn sword", compiled.negative)
                    self.assertIn("weapon held in hand", compiled.negative)
                if scene.startswith("Copper dagger, rare ornament"):
                    self.assertIn("artist signature", compiled.negative)
                if scene.startswith("Gimbutas arranging"):
                    self.assertIn("mid-twentieth-century", compiled.positive)
                    self.assertIn("prehistoric clothing on Gimbutas", compiled.negative)
                    self.assertIn("male Gimbutas", compiled.negative)
                if scene.startswith("Gimbutas tracing"):
                    self.assertIn("mid-twentieth-century", compiled.positive)
                    self.assertIn("male Gimbutas", compiled.negative)
                    self.assertIn("monstrous figure", compiled.negative)
                if scene.startswith("Anthony comparing"):
                    self.assertIn("present-day archaeological research room", compiled.positive)
                    self.assertIn("Gimbutas depiction", compiled.negative)
                if scene.startswith("Reich's laboratory"):
                    self.assertIn("present-day ancient-DNA laboratory", compiled.positive)
                    self.assertIn("bare hands touching specimen", compiled.negative)
                if scene.startswith("Scientists watching"):
                    self.assertIn("present-day ancient-DNA laboratory", compiled.positive)
                    self.assertIn("DNA helix", compiled.negative)
                if scene.startswith("Klejn challenging"):
                    self.assertIn("late-twentieth to early-twenty-first-century", compiled.positive)
                    self.assertIn("prehistoric clothing on Klejn", compiled.negative)
                    self.assertIn("exposed bone", compiled.negative)
                if scene.startswith("Updated research map"):
                    self.assertIn("present-day interdisciplinary ancient-DNA research", compiled.positive)
                    self.assertNotIn("plain woven wrap tunics", compiled.positive)
                    self.assertIn("prehistoric clothing on researcher", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                if scene.startswith("Ancient skull"):
                    self.assertIn("exposed skull", compiled.negative)
                    self.assertIn("wheel", compiled.negative)
                    self.assertIn("artifact-only display", compiled.negative)
                    self.assertIn("tire track", compiled.negative)
                    self.assertIn("visible face on shrouded body", compiled.negative)
                    self.assertIn("living person inside grave", compiled.negative)
                    self.assertIn("vertical draped figure", compiled.negative)
                    self.assertIn("doorway in mound", compiled.negative)
                    self.assertIn("timber portal", compiled.negative)

    def test_narration_aligned_ch2_migration_grave_stays_civilian_and_on_foot(self):
        scene = (
            "Archaeologists opening a Corded Ware grave as a ghosted migration map "
            "spreads eastward behind the skeleton"
        )
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene, "
            "3500 BCE to 2000 BCE; Exact place: Pontic-Caspian Steppe, Balkans, Central "
            "Europe; Yamnaya cultural horizon, Neolithic European communities; "
            f"Main subject: {scene}; Scene: {scene}; Global style: stylish adult "
            "hard-boiled historical action cartoon, rough extra-thick bold black ink "
            "contour lines NARRATIVE_FIDELITY_REGEN_V1; NARRATION VISUAL ALIGNMENT: "
            "match the spoken moment; Narration context: A grave exposed a major human migration"
        )

        compiled = self.compile(prompt)

        self.assertIn("Two present-day archaeologists in plain grey field jackets", compiled.positive)
        self.assertIn("one intact ancient skull lies on its left side", compiled.positive)
        self.assertIn("no fur garments", compiled.positive)
        self.assertNotIn("femur", compiled.positive)
        self.assertIn("prehistoric women, men, and children walk unarmed", compiled.positive)
        self.assertIn("mounted steppe warrior", compiled.negative)
        self.assertIn("long spear", compiled.negative)
        self.assertIn("modern fedora", compiled.negative)
        self.assertIn("person holding skull", compiled.negative)
        self.assertIn("duplicate skull", compiled.negative)
        self.assertIn("oversized skull", compiled.negative)
        self.assertIn("complete skeleton", compiled.negative)
        self.assertIn("femur", compiled.negative)
        self.assertIn("long bone", compiled.negative)
        self.assertIn("fur cloak on modern archaeologist", compiled.negative)
        self.assertIn("all-male migrant group", compiled.negative)
        self.assertTrue(
            _should_use_physicalized_narration_text_detector(prompt, compiled.positive)
        )

    def test_z_image_registered_ch2_migration_grave_separates_modern_excavation_from_prehistory(self):
        scene = (
            "Archaeologists opening a Corded Ware grave as a ghosted migration map "
            "spreads eastward behind the skeleton"
        )
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
            "Yamnaya cultural horizon, Neolithic European communities; "
            f"Main subject: {scene}; Scene: {scene}, archaeologically grounded late Neolithic "
            "and early Bronze Age reconstruction with tense human storytelling, 3500 BCE to "
            "2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya cultural horizon, "
            "Neolithic European communities, period-accurate clothing, architecture, tools, "
            "and material culture; "
            "Global style: mature dark historical manhwa"
        )

        compiled = self.compile(prompt, model="comfyui-z-image-base")

        self.assertEqual(compiled.person_count, 2)
        self.assertEqual(compiled.scene_kind, "pair")
        self.assertIn("exactly two present-day archaeologists", compiled.positive)
        self.assertIn("dark-grey field jackets", compiled.positive)
        self.assertIn("one small left-side half-buried skull", compiled.positive)
        self.assertIn("Only one tool exists", compiled.positive)
        self.assertIn("one small brush in one curled grip", compiled.positive)
        self.assertIn("keeps both hands hidden behind the torso", compiled.positive)
        self.assertNotIn("ghosted migration map", compiled.positive)
        self.assertIn("paper map", compiled.negative)
        self.assertIn("all-prehistoric excavation crew", compiled.negative)
        self.assertIn("third archaeologist", compiled.negative)
        self.assertIn("duplicate skull", compiled.negative)
        self.assertIn("complete skeleton", compiled.negative)
        self.assertIn("open palm", compiled.negative)
        self.assertIn("second or duplicate brush", compiled.negative)
        self.assertIn("two brushes", compiled.negative)
        self.assertIn("trowel", compiled.negative)
        self.assertIn("third or extra tool", compiled.negative)
        self.assertIn("hand touching skull", compiled.negative)
        self.assertIn("front-facing skull", compiled.negative)
        self.assertIn("fully exposed skull", compiled.negative)
        self.assertIn("oversized skull", compiled.negative)
        self.assertIn("upright skull", compiled.negative)
        self.assertIn("timber-lined grave", compiled.negative)

    def test_z_image_base_preflight_locks_remove_wheel_and_show_plain_graves(self):
        common = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
            "Yamnaya cultural horizon, Neolithic European communities; "
        )
        dispute_scene = (
            "Yamnaya chief judging a dispute before several clan representatives and tethered herds"
        )
        dispute = self.compile(
            common
            + f"Main subject: {dispute_scene}; Scene: {dispute_scene}, character continuity: "
            "Yamnaya chief, period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-base",
        )

        self.assertIn("exactly three separate clothed Yamnaya adults", dispute.positive)
        self.assertIn("one packed-earth route between two distant felt-tent camps", dispute.positive)
        self.assertIn("both hands hidden", dispute.positive)
        self.assertIn("two horned oxen", dispute.positive)
        self.assertNotIn("authority disk", dispute.positive)
        self.assertNotIn("camp disk", dispute.positive)
        self.assertIn("authority disk", dispute.negative)
        self.assertIn("spoked wheel", dispute.negative)

        cemetery_scene = (
            "Kurgan cemetery emphasizing richly furnished male graves beside sparse ordinary burials"
        )
        cemetery = self.compile(
            common
            + f"Main subject: {cemetery_scene}; Scene: {cemetery_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-base",
        )

        self.assertIn("exactly five rectangular earthen grave pits", cemetery.positive)
        self.assertIn("Left large pit", cemetery.positive)
        self.assertIn("exactly two small flat copper sheets", cemetery.positive)
        self.assertIn("exactly three tiny copper spiral rings", cemetery.positive)
        self.assertIn("exactly four smaller empty pits in a two-by-two grid", cemetery.positive)
        self.assertIn("missing plain graves", cemetery.negative)
        self.assertIn("barrel", cemetery.negative)
        self.assertIn("cylindrical vessel", cemetery.negative)

        dna_scene = (
            "Corded Ware cemetery in Germany with sampled teeth and a glowing ancient-DNA profile"
        )
        dna = self.compile(
            common
            + f"Main subject: {dna_scene}; Scene: {dna_scene}, period-accurate clothing, "
            "architecture, tools, and material culture",
            model="comfyui-z-image-base",
        )

        self.assertIn("one isolated ancient human molar", dna.positive)
        self.assertIn("exactly four equal blank clay ancestry tiles", dna.positive)
        self.assertIn("no grave, basket, tube, vessel, or other object", dna.positive)
        self.assertNotIn("corded beaker", dna.positive)
        self.assertNotIn("stone tool-head", dna.positive)
        self.assertNotIn("grave pit", dna.positive)
        self.assertIn("stone cist", dna.negative)
        self.assertIn("stone-lined grave", dna.negative)
        self.assertIn("woven basket", dna.negative)
        self.assertIn("cylindrical basket", dna.negative)

        zone_scene = (
            "Panoramic Corded Ware cultural zone spanning forests, rivers, farmland, and eastern grassland"
        )
        zone = self.compile(
            common
            + f"Main subject: {zone_scene}; Scene: {zone_scene}, period-accurate clothing, "
            "architecture, tools, and material culture",
            model="comfyui-z-image-base",
        )

        self.assertIn("dark forest at left", zone.positive)
        self.assertIn("one broad river at center", zone.positive)
        self.assertNotIn("pottery", zone.positive)
        self.assertNotIn("circular ground ring", zone.positive)
        self.assertNotIn("cord-impressed beakers", zone.positive)
        self.assertIn("pottery", zone.negative)
        self.assertIn("circular ground ring", zone.negative)
        self.assertIn("tree stump", zone.negative)

        delegation_scene = (
            "Compact Yamnaya delegation entering a village with copper weapons, horses, "
            "cattle, and ceremonial gifts"
        )
        delegation = self.compile(
            common
            + f"Main subject: {delegation_scene}; Scene: {delegation_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertIn("Era/period: 3300-2600 BCE", delegation.positive)
        self.assertIn("exactly three separate clothed adults", delegation.positive)
        self.assertIn("two Yamnaya migrants", delegation.positive)
        self.assertIn("one local farming ally", delegation.positive)
        self.assertIn("all six hands hidden", delegation.positive)
        self.assertIn("One ox and one cow", delegation.positive)
        self.assertIn("a closed hide roll", delegation.positive)
        self.assertIn("one small sheathed copper blade", delegation.positive)
        self.assertIn("One plain unornamented anthropomorphic stone stela", delegation.positive)
        self.assertNotIn("object-only small-group power package", delegation.positive)
        self.assertNotIn("Era/period: 2007 AD", delegation.positive)
        self.assertIn("open palm", delegation.negative)
        self.assertIn("handheld copper weapon", delegation.negative)
        self.assertIn("ornate stela", delegation.negative)
        self.assertIn("scholarly model", delegation.negative)

        fracture_scene = (
            "Rival heirs arguing over cattle while allied camps split and armed followers "
            "choose sides"
        )
        fracture = self.compile(
            common
            + f"Main subject: {fracture_scene}; Scene: {fracture_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(fracture.person_count, 3)
        self.assertEqual(fracture.scene_kind, "group")
        self.assertIn("Exactly three clothed Yamnaya adults", fracture.positive)
        self.assertIn("one empty cattle enclosure", fracture.positive)
        self.assertIn("all six hands stay hidden", fracture.positive)
        self.assertNotIn("leadership disk", fracture.positive)
        self.assertIn("leadership disk", fracture.negative)

        origin_scene = (
            "Updated research map moving the earliest language origin toward the "
            "Caucasus-Lower Volga zone"
        )
        origin = self.compile(
            common
            + f"Main subject: {origin_scene}; Scene: {origin_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(origin.person_count, 0)
        self.assertEqual(origin.scene_kind, "landscape")
        self.assertIn("dark stone Caucasus foothills", origin.positive)
        self.assertIn("exactly six small rectangular earth sampling pits", origin.positive)
        self.assertNotIn("sample disks", origin.positive)
        self.assertIn("padlock", origin.negative)
        self.assertIn("sample disk", origin.negative)

        final_scene = (
            "Ancient skull, wagon track, kurgan, and mixed family joined in a final "
            "cinematic tableau"
        )
        final_molar = self.compile(
            common
            + f"Main subject: {final_scene}; Scene: {final_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertIn("exactly one ancient human molar fills left-center", final_molar.positive)
        self.assertIn("two short roots clearly visible", final_molar.positive)
        self.assertIn("all surrounding soil remains empty", final_molar.positive)
        self.assertNotIn("ancestry tokens", final_molar.positive)
        self.assertIn("long bone", final_molar.negative)
        self.assertIn("femur", final_molar.negative)

        ancestry_scene = (
            "Ancient skeleton overlaid with a bold seventy-five percent ancestry "
            "connection to the Pontic-Caspian grasslands"
        )
        ancestry = self.compile(
            common
            + f"Main subject: {ancestry_scene}; Scene: {ancestry_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertIn("one small squat human molar", ancestry.positive)
        self.assertIn("one broad four-cusped crown and two short roots", ancestry.positive)
        self.assertIn("exactly four equal square tiles", ancestry.positive)
        self.assertNotIn("complete skeleton", ancestry.positive)
        self.assertIn("long bone", ancestry.negative)
        self.assertIn("hollow bone socket", ancestry.negative)

        wagon_scene = (
            "Yamnaya wagon column with copper weapons and families moving beneath "
            "branching Indo-European language symbols"
        )
        wagon = self.compile(
            common
            + f"Main subject: {wagon_scene}; Scene: {wagon_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(wagon.scene_kind, "landscape")
        self.assertIn("exactly one low wooden wagon", wagon.positive)
        self.assertIn("exactly four solid plank disk wheels", wagon.positive)
        self.assertIn("exactly two closed hide bundles", wagon.positive)
        self.assertIn("one small sheathed copper blade", wagon.positive)
        self.assertNotIn("language tile", wagon.positive)
        self.assertIn("spoked wheel", wagon.negative)
        self.assertIn("second wagon", wagon.negative)

        elite_grave_scene = (
            "Ochre-covered male burial beneath a kurgan with wagon wheels, dagger, "
            "animal offerings, and silent mourners"
        )
        elite_grave = self.compile(
            common
            + f"Main subject: {elite_grave_scene}; Scene: {elite_grave_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertIn("exactly five rectangular earthen grave pits", elite_grave.positive)
        self.assertIn("Center large elite pit", elite_grave.positive)
        self.assertIn("exactly four smaller plain pits", elite_grave.positive)
        self.assertNotIn("wooden disk", elite_grave.positive)
        self.assertIn("padlock", elite_grave.negative)
        self.assertIn("storage chest", elite_grave.negative)

        encounter_scene = (
            "Yamnaya chief and farmer elder facing each other between armed followers "
            "and exchanged prestige gifts"
        )
        encounter = self.compile(
            common
            + f"Main subject: {encounter_scene}; Scene: {encounter_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(encounter.person_count, 2)
        self.assertEqual(encounter.scene_kind, "pair")
        self.assertIn("Exactly two separate clothed adults", encounter.positive)
        self.assertIn("Both keep hands hidden inside cloaks", encounter.positive)
        self.assertIn("remains fully sheathed at the belt", encounter.positive)
        self.assertIn("handshake", encounter.negative)
        self.assertIn("drawn dagger", encounter.negative)

        empty_steppe_scene = (
            "Wide Pontic-Caspian grassland between distant rivers with cattle camps "
            "and wooden wagons"
        )
        empty_steppe = self.compile(
            common
            + f"Main subject: {empty_steppe_scene}; Scene: {empty_steppe_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(empty_steppe.scene_kind, "landscape")
        self.assertIn("one winding river", empty_steppe.positive)
        self.assertIn("completely empty", empty_steppe.positive)
        self.assertIn("no person, animal, tree, camp, shelter, wagon", empty_steppe.positive)
        self.assertNotIn("wooden wagon bed", empty_steppe.positive)
        self.assertIn("spoked wheel", empty_steppe.negative)

        river_scene = (
            "High panoramic view of steppe routes between the Black Sea, Caspian Sea, "
            "Dnieper, Don, and Volga"
        )
        rivers = self.compile(
            common
            + f"Main subject: {river_scene}; Scene: {river_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(rivers.scene_kind, "landscape")
        self.assertIn("exactly three broad winding river bands", rivers.positive)
        self.assertIn("no person, animal, mound, kurgan", rivers.positive)
        self.assertNotIn("six matching rounded earthen kurgans", rivers.positive)
        self.assertIn("helmet", rivers.negative)

        winter_scene = (
            "Cattle searching sparse winter grass beside a frozen river and a worried "
            "pastoral camp"
        )
        winter = self.compile(
            common
            + f"Main subject: {winter_scene}; Scene: {winter_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(winter.scene_kind, "animal")
        self.assertIn("exactly one lean horned ox", winter.positive)
        self.assertIn("exactly four separate grounded legs", winter.positive)
        self.assertIn("no human, camp, tent, building", winter.positive)
        self.assertIn("second animal", winter.negative)
        self.assertIn("five legs", winter.negative)

        mobility_scene = (
            "Young herder driving cattle while families repair an ox-drawn wagon "
            "during a cold migration"
        )
        mobility = self.compile(
            common
            + f"Main subject: {mobility_scene}; Scene: {mobility_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(mobility.scene_kind, "object")
        self.assertEqual(mobility.person_count, 0)
        self.assertIn("exactly four separate solid three-plank wooden transport disks", mobility.positive)
        self.assertIn("one plain cattle yoke", mobility.positive)
        self.assertIn("one closed woven food packet", mobility.positive)
        self.assertIn("no wagon body, person, animal, blade, lock, or metal object", mobility.positive)
        self.assertIn("spoked wheel", mobility.negative)
        self.assertIn("padlock", mobility.negative)

        dismantled_scene = (
            "Seasonal Yamnaya camp being dismantled as wagons form a departing column"
        )
        dismantled = self.compile(
            common
            + f"Main subject: {dismantled_scene}; Scene: {dismantled_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(dismantled.scene_kind, "landscape")
        self.assertEqual(dismantled.person_count, 0)
        self.assertIn("exactly two shallow parallel wagon ruts", dismantled.positive)
        self.assertIn("one collapsed pale hide shelter roll", dismantled.positive)
        self.assertIn("no person, animal, wagon, wheel, road, tent, building", dismantled.positive)
        self.assertNotIn("solid wooden transport disks", dismantled.positive)
        self.assertIn("wagon body", dismantled.negative)

        pit_scene = (
            "Cross-section of a simple pit grave beneath an earthen kurgan beside "
            "a living steppe camp"
        )
        pit = self.compile(
            common
            + f"Main subject: {pit_scene}; Scene: {pit_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(pit.scene_kind, "object")
        self.assertEqual(pit.person_count, 0)
        self.assertIn("one empty straight-sided rectangular pit", pit.positive)
        self.assertIn("uninterrupted dark packed soil", pit.positive)
        self.assertIn("no person, remains, fabric, face, portrait, pattern, or object", pit.positive)
        self.assertIn("repeated face", pit.negative)
        self.assertIn("decorative pattern", pit.negative)

        social_scene = (
            "Yamnaya chief, Young herder, Metalworker, women, children, and cattle "
            "gathered around a council fire"
        )
        social = self.compile(
            common
            + f"Main subject: Yamnaya chief; Scene: {social_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(social.scene_kind, "object")
        self.assertEqual(social.person_count, 0)
        self.assertIn("No writing, knife, hammer, handle, or jar", social.positive)
        self.assertIn("low shallow soot-dark clay bowl", social.positive)
        self.assertIn("three raw copper droplets", social.positive)
        self.assertIn("thin irregular flat copper sheet", social.positive)
        self.assertNotIn("hammerstone", social.positive)
        self.assertNotIn("blade blank", social.positive)
        self.assertIn("metal hammer", social.negative)
        self.assertIn("ceramic vase", social.negative)

        mykhailivka_scene = (
            "Mobile wagons approaching the fortified riverside settlement of "
            "Mykhailivka on the lower Dnieper"
        )
        mykhailivka = self.compile(
            common
            + f"Main subject: {mykhailivka_scene}; Scene: {mykhailivka_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(mykhailivka.scene_kind, "object")
        self.assertEqual(mykhailivka.person_count, 0)
        self.assertIn("one collapsed hide roll", mykhailivka.positive)
        self.assertIn("one excavated dry-stone wall base", mykhailivka.positive)
        self.assertIn("three low rectangular clay foundation outlines, all roofless", mykhailivka.positive)
        self.assertNotIn("three-plank wooden wheel disk", mykhailivka.positive)
        self.assertIn("spoked wheel", mykhailivka.negative)
        self.assertIn("standing house", mykhailivka.negative)
        self.assertIn("pitched roof", mykhailivka.negative)

        subsistence_scene = (
            "Busy Yamnaya camp with herding, fishing, pottery making, food "
            "preparation, and copper working"
        )
        subsistence = self.compile(
            common
            + f"Main subject: Busy Yamnaya camp with herding; Scene: {subsistence_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(subsistence.scene_kind, "object")
        self.assertEqual(subsistence.person_count, 0)
        self.assertIn("No knife, hammer, handle, jar, or basket", subsistence.positive)
        self.assertIn("fibre net with four stone sinkers", subsistence.positive)
        self.assertIn("unfired clay beaker with three coils", subsistence.positive)
        self.assertIn("blunt round copper sheet with dimples", subsistence.positive)
        self.assertNotIn("copper blade blank", subsistence.positive)
        self.assertIn("metal hammer", subsistence.negative)
        self.assertIn("pottery jar", subsistence.negative)

        herd_risk_scene = (
            "Young herder guarding a dense cattle herd while armed strangers watch "
            "from a distant ridge"
        )
        herd_risk = self.compile(
            common
            + f"Main subject: {herd_risk_scene}; Scene: {herd_risk_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(herd_risk.scene_kind, "landscape")
        self.assertEqual(herd_risk.person_count, 0)
        self.assertIn("One broad band of dense cattle hoofprints", herd_risk.positive)
        self.assertIn("one narrow muddy river ford", herd_risk.positive)
        self.assertIn("splits between two distant ridges", herd_risk.positive)
        self.assertNotIn("transport-wheel disk", herd_risk.positive)
        self.assertNotIn("copper blade blank", herd_risk.positive)
        self.assertIn("copper blade", herd_risk.negative)

        command_scene = (
            "Long wagon column crossing exposed grassland under the watch of mounted "
            "scouts and armed leaders"
        )
        command = self.compile(
            common
            + f"Main subject: {command_scene}; Scene: {command_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(command.scene_kind, "landscape")
        self.assertEqual(command.person_count, 0)
        self.assertIn("Three paired shallow track trails", command.positive)
        self.assertIn("merge into one ordered route", command.positive)
        self.assertIn("one distant river crossing", command.positive)
        self.assertNotIn("wooden wagon bed", command.positive)
        self.assertNotIn("copper blade blank", command.positive)
        self.assertIn("command staff", command.negative)

        prepared_grave_scene = (
            "Mourners lowering an elite Yamnaya chief into a rectangular grave lined "
            "with hides"
        )
        prepared_grave = self.compile(
            common
            + f"Main subject: {prepared_grave_scene}; Scene: {prepared_grave_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(prepared_grave.scene_kind, "object")
        self.assertEqual(prepared_grave.person_count, 0)
        self.assertIn("exactly one deep straight-sided rectangular earthen pit", prepared_grave.positive)
        self.assertIn("One dark hide lining lies flat against all four walls", prepared_grave.positive)
        self.assertIn("One broad red-ochre band", prepared_grave.positive)
        self.assertIn("uninterrupted packed-soil floor", prepared_grave.positive)
        self.assertNotIn("closed ochre shroud", prepared_grave.positive)
        self.assertNotIn("copper blade blank", prepared_grave.positive)
        self.assertIn("wrapped body", prepared_grave.negative)
        self.assertIn("wooden disk", prepared_grave.negative)

        kurgan_scene = (
            "Workers piling earth into a tall kurgan visible across an otherwise "
            "flat steppe"
        )
        kurgan = self.compile(
            common
            + f"Main subject: {kurgan_scene}; Scene: {kurgan_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(kurgan.scene_kind, "landscape")
        self.assertEqual(kurgan.person_count, 0)
        self.assertIn("exactly one tall rounded earthen kurgan", kurgan.positive)
        self.assertIn("spanning the middle two-thirds of the frame", kurgan.positive)
        self.assertIn("the mound blocks the distant horizon", kurgan.positive)
        self.assertIn("Unbroken dry grass fills the foreground", kurgan.positive)
        self.assertIn("hut", kurgan.negative)
        self.assertIn("cabin", kurgan.negative)
        self.assertIn("signpost", kurgan.negative)

        layered_scene = (
            "Layered kurgan cross-section with successive burials arranged above "
            "the founding grave"
        )
        layered = self.compile(
            common
            + f"Main subject: {layered_scene}; Scene: {layered_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(layered.scene_kind, "object")
        self.assertEqual(layered.person_count, 0)
        self.assertIn("exactly three flat dark-ochre horizontal burial bands", layered.positive)
        self.assertIn("one long founding band at bottom center", layered.positive)
        self.assertIn("one short later band at upper-left", layered.positive)
        self.assertIn("one short later band at upper-right", layered.positive)
        self.assertIn("Continuous packed earth separates all three bands", layered.positive)
        self.assertIn("fourth band", layered.negative)
        self.assertIn("open hole", layered.negative)

        offering_scene = (
            "Slaughtered sheep and cattle portions placed beside an elite burial "
            "during a solemn rite"
        )
        offering = self.compile(
            common
            + f"Main subject: {offering_scene}; Scene: {offering_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(offering.scene_kind, "object")
        self.assertEqual(offering.person_count, 0)
        self.assertIn("exactly two compact rectangular offering packets", offering.positive)
        self.assertIn("one large dark cattle-hide packet at left", offering.positive)
        self.assertIn("one smaller pale sheep-hide packet at right", offering.positive)
        self.assertIn("Both are fully closed with plain plant-fibre cord", offering.positive)
        self.assertNotIn("horn core", offering.positive)
        self.assertIn("cattle skull", offering.negative)
        self.assertIn("horn core", offering.negative)

        stela_scene = (
            "Anthropomorphic stone stela with carved belt, hands, axe, and dagger "
            "overlooking a burial"
        )
        stela = self.compile(
            common
            + f"Main subject: {stela_scene}; Scene: {stela_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(stela.scene_kind, "object")
        self.assertEqual(stela.person_count, 0)
        self.assertIn("one plain weathered stone stela filling the frame", stela.positive)
        self.assertIn("Exactly three shallow incised line motifs", stela.positive)
        self.assertIn("one featureless oval at top", stela.positive)
        self.assertIn("one tiny diagonal tool-outline near base", stela.positive)
        self.assertNotIn("one small axe outline", stela.positive)
        self.assertIn("portrait", stela.negative)
        self.assertIn("freestanding axe", stela.negative)

        rare_grave_scene = (
            "Small group of elite male graves contrasted with a much larger living "
            "Yamnaya population"
        )
        rare_grave = self.compile(
            common
            + f"Main subject: {rare_grave_scene}; Scene: {rare_grave_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(rare_grave.scene_kind, "object")
        self.assertEqual(rare_grave.person_count, 0)
        self.assertIn("one large flat rectangular ochre-hide swatch", rare_grave.positive)
        self.assertIn("many much smaller flat square grey clay tiles", rare_grave.positive)
        self.assertIn("covering the right half", rare_grave.positive)
        self.assertNotIn("grave-cover disks", rare_grave.positive)
        self.assertNotIn("household pebbles", rare_grave.positive)
        self.assertIn("round disk", rare_grave.negative)
        self.assertIn("hut", rare_grave.negative)

        regional_scene = (
            "Two regional Yamnaya burials with distinct body positions and sharply "
            "different grave goods"
        )
        regional = self.compile(
            common
            + f"Main subject: {regional_scene}; Scene: {regional_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(regional.scene_kind, "object")
        self.assertEqual(regional.person_count, 0)
        self.assertIn("exactly two rectangular pits", regional.positive)
        self.assertIn("one straight closed ochre shroud", regional.positive)
        self.assertIn("one bent L-shaped closed ochre shroud", regional.positive)
        self.assertIn("three flat dark hide floor layers", regional.positive)
        self.assertNotIn("copper axe head", regional.positive)
        self.assertNotIn("wooden disk", regional.positive)
        self.assertIn("handled axe", regional.negative)
        self.assertIn("bone", regional.negative)

        wagon_trace_scene = (
            "Complete four-wheeled wooden wagon lowered into a deep grave beside "
            "the deceased chief"
        )
        wagon_trace = self.compile(
            common
            + f"Main subject: {wagon_trace_scene}; Scene: {wagon_trace_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(wagon_trace.scene_kind, "object")
        self.assertEqual(wagon_trace.person_count, 0)
        self.assertIn("one long dark rectangular timber stain", wagon_trace.positive)
        self.assertIn("exactly four filled round dark-soil stains", wagon_trace.positive)
        self.assertIn("paired axle positions", wagon_trace.positive)
        self.assertIn("Every mark is flat soil discoloration", wagon_trace.positive)
        self.assertNotIn("plain wooden wagon bed", wagon_trace.positive)
        self.assertIn("wagon body", wagon_trace.negative)
        self.assertIn("wheel object", wagon_trace.negative)

        labor_scene = (
            "Exhausted workers and oxen surrounding the chief's wagon burial as "
            "elite relatives supervise"
        )
        labor = self.compile(
            common
            + f"Main subject: {labor_scene}; Scene: {labor_scene}, period-accurate "
            "clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(labor.scene_kind, "landscape")
        self.assertEqual(labor.person_count, 0)
        self.assertIn("One deep rectangular grave lies at center", labor.positive)
        self.assertIn("Two long parallel drag grooves", labor.positive)
        self.assertIn("bare-foot impressions and cattle hoofprints", labor.positive)
        self.assertNotIn("heavy wooden wagon bed", labor.positive)
        self.assertNotIn("rope coils", labor.positive)
        self.assertIn("living cattle", labor.negative)
        self.assertIn("wagon body", labor.negative)

        copper_work_scene = (
            "Metalworker raising a newly cast copper blade beside a glowing crucible "
            "and watching chiefs"
        )
        copper_work = self.compile(
            common
            + f"Main subject: {copper_work_scene}; Scene: {copper_work_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(copper_work.scene_kind, "object")
        self.assertEqual(copper_work.person_count, 0)
        self.assertIn("one low clay-lined hearth depression", copper_work.positive)
        self.assertIn("Black charcoal fills its center", copper_work.positive)
        self.assertIn("Exactly five tiny irregular copper droplets", copper_work.positive)
        self.assertIn("one green raw copper-ore stone", copper_work.positive)
        self.assertNotIn("stone hammer", copper_work.positive)
        self.assertNotIn("blade blank", copper_work.positive)
        self.assertIn("hammer head", copper_work.negative)
        self.assertIn("pottery jar", copper_work.negative)

        elite_metal_scene = (
            "Copper daggers, axes, spearheads, and ornaments arranged around one "
            "richly furnished burial"
        )
        elite_metal = self.compile(
            common
            + f"Main subject: Copper daggers; Scene: {elite_metal_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(elite_metal.scene_kind, "object")
        self.assertEqual(elite_metal.person_count, 0)
        self.assertIn("one compact dense cluster", elite_metal.positive)
        self.assertIn("small irregular green-corroded copper fragments", elite_metal.positive)
        self.assertIn("thin blunt copper sheets", elite_metal.positive)
        self.assertIn("unhafted, flat, edgeless, and nonrepresentational", elite_metal.positive)
        self.assertNotIn("dagger blade blanks", elite_metal.positive)
        self.assertNotIn("axe heads", elite_metal.positive)
        self.assertIn("spearhead", elite_metal.negative)
        self.assertIn("tool handle", elite_metal.negative)

        reich_scene = (
            "Reich comparing ancient Y chromosomes, rich male graves, and a "
            "narrowing ancestry chart"
        )
        reich = self.compile(
            common
            + f"Main subject: Reich comparing ancient Y chromosomes; Scene: {reich_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(reich.scene_kind, "face")
        self.assertEqual(reich.person_count, 1)
        self.assertIn("exactly one middle-aged geneticist David Reich", reich.positive)
        self.assertIn("shoulders outside frame", reich.positive)
        self.assertIn("three blurred ochre grave-soil samples", reich.positive)
        self.assertNotIn("ancient molar", reich.positive)
        self.assertNotIn("elite-male disk", reich.positive)
        self.assertIn("visible shoulder", reich.negative)
        self.assertIn("token", reich.negative)

        transport_trace_scene = (
            "Ox-drawn carts and wagons loaded with hides, vessels, food, tools, "
            "and families"
        )
        transport_trace = self.compile(
            common
            + f"Main subject: Ox-drawn carts and wagons loaded with hides; Scene: "
            f"{transport_trace_scene}, period-accurate clothing, architecture, tools, "
            "and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(transport_trace.scene_kind, "object")
        self.assertEqual(transport_trace.person_count, 0)
        self.assertIn("one short rectangular bed stain crossed by one axle line", transport_trace.positive)
        self.assertIn("one long rectangular bed stain crossed by exactly two axle lines", transport_trace.positive)
        self.assertIn("One collapsed hide roll", transport_trace.positive)
        self.assertIn("one closed woven provision packet", transport_trace.positive)
        self.assertNotIn("solid wooden disk wheels", transport_trace.positive)
        self.assertIn("wagon object", transport_trace.negative)
        self.assertIn("amphora", transport_trace.negative)

        ox_trace_scene = (
            "Powerful oxen straining against a loaded four-wheeled wagon on rough "
            "steppe ground"
        )
        ox_trace = self.compile(
            common
            + f"Main subject: {ox_trace_scene}; Scene: {ox_trace_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(ox_trace.scene_kind, "landscape")
        self.assertEqual(ox_trace.person_count, 0)
        self.assertIn("Two dense parallel bands of cattle hoofprints", ox_trace.positive)
        self.assertIn("two deep parallel wagon-rut grooves", ox_trace.positive)
        self.assertIn("toward the distant horizon", ox_trace.positive)
        self.assertNotIn("heavy wooden wagon bed", ox_trace.positive)
        self.assertNotIn("solid disk wheels", ox_trace.positive)
        self.assertIn("cattle yoke", ox_trace.negative)
        self.assertIn("wagon body", ox_trace.negative)

        riding_bone_scene = (
            "Young herder riding a compact steppe horse beside cattle with "
            "anatomical bone details inset"
        )
        riding_bone = self.compile(
            common
            + f"Main subject: {riding_bone_scene}; Scene: {riding_bone_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(riding_bone.scene_kind, "object")
        self.assertEqual(riding_bone.person_count, 0)
        self.assertIn("exactly one complete adult human pelvis", riding_bone.positive)
        self.assertIn("Both hip sockets remain visible and symmetrical", riding_bone.positive)
        self.assertIn("Exactly two small ochre wear areas", riding_bone.positive)
        self.assertNotIn("proximal human femur", riding_bone.positive)
        self.assertNotIn("ancient horse molar", riding_bone.positive)
        self.assertIn("long bone", riding_bone.negative)
        self.assertIn("molar", riding_bone.negative)

        horse_research_scene = (
            "Archaeologists comparing disputed riding traces, horse teeth, and "
            "genetic timelines at an excavation"
        )
        horse_research = self.compile(
            common
            + f"Main subject: Archaeologists comparing disputed riding traces; Scene: "
            f"{horse_research_scene}, period-accurate clothing, architecture, tools, "
            "and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(horse_research.scene_kind, "face")
        self.assertEqual(horse_research.person_count, 1)
        self.assertIn("exactly one modern female archaeogeneticist", horse_research.positive)
        self.assertIn("shoulders outside frame", horse_research.positive)
        self.assertIn("one dark blurred laboratory sample rack", horse_research.positive)
        self.assertNotIn("ancient horse molar", horse_research.positive)
        self.assertNotIn("metal caliper", horse_research.positive)
        self.assertIn("caliper", horse_research.negative)
        self.assertIn("ancestry disk", horse_research.negative)

        noncavalry_scene = (
            "Yamnaya migrants with ox wagons and a few riders, deliberately "
            "avoiding a mass cavalry charge"
        )
        noncavalry = self.compile(
            common
            + f"Main subject: Yamnaya migrants with ox wagons and a few riders; Scene: "
            f"{noncavalry_scene}, period-accurate clothing, architecture, tools, and "
            "material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(noncavalry.scene_kind, "landscape")
        self.assertEqual(noncavalry.person_count, 0)
        self.assertIn("exactly two separated bands of deep paired wagon ruts", noncavalry.positive)
        self.assertIn("dense cattle-hoof tracks", noncavalry.positive)
        self.assertIn("curve slowly around one marsh", noncavalry.positive)
        self.assertNotIn("solid-wheel wagons", noncavalry.positive)
        self.assertIn("wagon body", noncavalry.negative)
        self.assertIn("village", noncavalry.negative)

        route_network_scene = (
            "Families, cattle, wagons, ritual objects, and messengers moving along "
            "interconnected steppe routes"
        )
        route_network = self.compile(
            common
            + f"Main subject: Families; Scene: {route_network_scene}, "
            "period-accurate clothing, architecture, tools, and material culture",
            model="comfyui-z-image-turbo",
        )

        self.assertEqual(route_network.scene_kind, "landscape")
        self.assertEqual(route_network.person_count, 0)
        self.assertIn("Exactly three shallow travel paths", route_network.positive)
        self.assertIn("one central river ford", route_network.positive)
        self.assertIn("One irregular patch of trampled campsite grass", route_network.positive)
        self.assertIn("one low earthen kurgan", route_network.positive)
        self.assertIn("mixed hoofprints with paired ruts", route_network.positive)
        self.assertNotIn("clan disks", route_network.positive)
        self.assertIn("round token", route_network.negative)
        self.assertIn("signpost", route_network.negative)

    def test_z_image_narration_aligned_yamnaya_burials_stay_human_led_and_non_graphic(self):
        common = (
            "Year/period: 3500 BCE to 2000 BCE; European historical documentary scene; "
            "Exact place: Pontic-Caspian Steppe; Yamnaya cultural horizon; "
        )
        cases = (
            (
                "Red ochre scattered across the chief's wrapped body while mourners stand around the grave",
                "The body was often covered with red ochre, turning burial into a vivid public spectacle.",
                ("Exactly five clothed Yamnaya mourners", "dry granular red mineral ochre", "fully closed undyed woven shroud"),
                ("no wet liquid", "blood pool", "protruding body part"),
            ),
            (
                "Two regional Yamnaya burials with distinct body positions and sharply different grave goods",
                "Their bodies lay differently according to region, while goods made status impossible to miss.",
                ("Exactly two living Yamnaya mourners", "two shallow open grave pits", "one plain clay cup"),
                ("clear right angle", "one tightly curled side-lying"),
            ),
            (
                "Male war band displaying axes and spears beneath a lineage tree centered on fathers and sons",
                "Weapons, warrior imagery, and patrilineal organization seemed to explain their success in conflict.",
                ("Exactly one clothed Yamnaya father", "one adolescent son", "close waist-up portrait"),
                ("Both hands remain below the frame", "father-son warrior organization dominate"),
            ),
            (
                "Dramatic invasion mural breaking apart into scattered graves, settlements, and uncertain archaeological traces",
                "It is a compelling invasion story, but evidence does not reveal one continent-wide battlefield.",
                ("Exactly two present-day archaeologists", "one woman and one man", "matching plain field jackets"),
                ("All four hands stay inside jacket pockets", "several separated grave outlines"),
            ),
            (
                "Compact Yamnaya delegation entering a village with copper weapons, horses, cattle, and ceremonial gifts",
                "A small migrant group arrived with strong allies, useful weapons, animals, and impressive ritual authority.",
                ("Exactly two clothed adults", "Exactly one pack ox", "one low plain stone stela"),
                ("Human alliance, animal mobility", "ritual authority dominate"),
            ),
            (
                "Armed retainers standing behind negotiators as a reluctant village accepts new obligations",
                "Nor does elite recruitment erase violence; power works because refusal carries consequences.",
                ("Exactly two bare-headed adult negotiators", "face each other alone", "reluctant local elder"),
                ("nobody else present", "unequal leverage dominate"),
            ),
            (
                "Yamnaya chief distributing meat and gifts during a feast guarded by armed followers",
                "Feasts converted captured wealth into loyalty, placing generosity and intimidation at one table.",
                ("Exactly five clothed people", "one bare-headed Yamnaya chief", "exactly four seated guests"),
                ("faces show gratitude and unease", "open treeless steppe camp"),
            ),
            (
                "Metalworker presenting a polished copper axe to the Yamnaya chief before assembled followers",
                "Craft specialists gained patrons, and patrons gained objects that made authority visible.",
                ("Exactly one bare-headed copper worker", "small single-bitted copper axe", "exactly three clothed followers"),
                ("human faces dominate", "all other hands stay hidden"),
            ),
            (
                "Kin group, cattle, wagon wheel, and ritual fire linked to reconstructed word roots",
                "Shared words for kinship, animals, wheels, and ritual preserve echoes of an older language.",
                ("TWO AND ONLY TWO living people", "one small ritual fire", "Two broad parallel shallow transport ruts"),
                ("without any visible cart or wheel", "Kinship conversation"),
            ),
            (
                "Battle-axe, ancient skeleton, and comparative word list aligned as three evidence columns",
                "Archaeology supplies objects, genetics supplies biological relationships, and linguistics reconstructs vanished speech.",
                ("TWO AND ONLY TWO PRESENT-DAY WOMEN RESEARCHERS", "bright orange zippered safety vests", "one sealed sample vial"),
                ("hands remain below the frame", "discussion dominates"),
            ),
            (
                "Three overlapping maps from archaeology, genetics, and linguistics with mismatched boundaries",
                "None can tell the complete story alone, and their maps do not always agree.",
                ("Exactly two present-day women specialists", "stand back to back", "different trench boundary and opposite horizon"),
                ("All four hands stay inside jacket pockets", "incompatible conclusions dominate"),
            ),
            (
                "Four predecessor cultural zones converging around early Yamnaya settlements and graves",
                "Their origins may involve Khvalynsk, Repin, Sredny Stog, and lower Dnieper continuities.",
                ("FOUR AND ONLY FOUR clothed adult delegates", "four evenly spaced compass positions", "same empty center"),
                ("separated by visible grass", "no fifth person"),
            ),
            (
                "Y chromosome lineages from Yamnaya graves failing to align perfectly with Corded Ware men",
                "Even direct Yamnaya paternal lines do not perfectly match later Central European samples.",
                ("Exactly two present-day archaeogeneticists", "two separated low sample trays", "one capped vial"),
                ("hands hidden in coat pockets", "concerned glance across the mismatch"),
            ),
            (
                "Corded Ware community transitioning into Bell Beaker and later Bronze Age cultural scenes",
                "Their descendants changed again as Bell Beaker and later Bronze Age networks expanded.",
                ("TWO AND ONLY TWO clothed women", "visibly elderly white-haired grandmother", "visibly young adult brown-haired"),
                ("extreme close head-and-shoulders", "plain undyed woven textile wall"),
            ),
            (
                "Gloved technicians processing ancient bone powder through clean laboratory equipment",
                "Researchers grind a tiny sample, extract damaged genetic fragments, and guard against modern contamination.",
                ("TWO AND ONLY TWO PRESENT-DAY TECHNICIANS", "one seamless unbroken blank white wall", "one capped extraction tube"),
                ("identical white cleanroom coveralls", "bright-white sterile cleanroom"),
            ),
            (
                "Ancient population map showing a major influx from the steppe into Central Europe",
                "Central Europe's late Neolithic population had received ancestry from an enormous eastern movement.",
                ("Wide continuous prehistoric valley", "exactly two local farming families", "long mixed procession"),
                ("People and movement dominate", "hands lowered or hidden"),
            ),
            (
                "Mixed-ancestry couple at a prehistoric wedding with uncertain expressions and armed relatives",
                "Genes can reveal parents and populations; they cannot record whether a marriage was chosen.",
                ("Exactly two bare-headed prehistoric adults", "One bearded migrant man", "one clearly adult local woman"),
                ("extreme close head-and-shoulders", "plain undyed woven textile wall"),
            ),
            (
                "Firm evidence panel connecting Yamnaya-related groups to major Central European ancestry change",
                "The safest conclusion is narrower: Yamnaya-related migration transformed Central European ancestry profoundly.",
                ("Exactly three clothed people", "one Yamnaya-related migrant woman", "one local farming man"),
                ("their one child", "all three full bodies remain separated"),
            ),
            (
                "Steppe migration routes aligned with several, but not all, Indo-European language branches",
                "It also strongly supports steppe involvement in spreading at least some Indo-European language branches.",
                ("One large mixed migrant family procession", "three separate dirt paths", "one family remains at the camp"),
                ("separation, and travel dominate", "hands stay lowered or hidden"),
            ),
            (
                "Yamnaya chief looking west across empty grassland with distant future maps hidden in clouds",
                "He cannot see Germany, genetics, or the future languages tied to his descendants.",
                ("Exactly one Yamnaya chief", "one low kurgan", "completely empty treeless grassland"),
                ("both hands hidden", "unknowable empty horizon dominate"),
            ),
            (
                "Wagons, marriage bonds, elite graves, armed retainers, and herds forming one power system",
                "That was the deeper advantage: mobility joined to status, kinship, and organized force.",
                ("Exactly three clothed adults", "one bearded Yamnaya chief", "clearly adult long-braided wife"),
                ("Exactly two pack oxen", "Coordinated travel, marriage bond"),
            ),
            (
                "Successive farmer leaders joining the network while children learn the prestige language",
                "Across generations, local leaders entered that system and carried its speech into their households.",
                ("THREE AND ONLY THREE people", "one white-haired migrant elder", "one adult local farming mother"),
                ("one child", "no horizon or structure"),
            ),
        )
        for scene, narration, required, safeguards in cases:
            normalized = normalize_cut_image_prompt(
                common + f"Main subject: {scene}; Scene: {scene}, archaeologically grounded reconstruction",
                narration,
            )
            source = prepare_scene_contract_source(
                normalized,
                narration_context=narration,
            )
            compiled = self.compile(source, model="comfyui-z-image-turbo")
            for phrase in required:
                self.assertIn(phrase, compiled.positive)
            for phrase in safeguards:
                self.assertIn(phrase, compiled.positive)
            if scene.startswith("Compact Yamnaya delegation"):
                for phrase in ("horse", "rider", "saddle", "stirrup", "cup", "chalice", "authority staff", "missing third adult", "second animal"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Armed retainers standing"):
                for phrase in ("helmet", "visor", "metal armor", "medieval soldier", "head covering", "spear", "weapon"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Yamnaya chief distributing meat"):
                for phrase in ("stone tower", "castle tower", "church", "sixth person", "extra guest", "retainer", "spear", "shirtless person"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Metalworker presenting"):
                for phrase in ("double-headed axe", "oversized axe", "medieval axe", "halberd", "steel axe"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Kin group, cattle"):
                for phrase in ("spoked wheel", "radial spokes", "chariot wheel", "wagon", "cart", "fourth person"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Battle-axe, ancient skeleton"):
                for phrase in ("battle axe", "three evidence columns", "object grid", "ancient clothing", "robe", "open book", "clay pot"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Three overlapping maps"):
                for phrase in ("map display", "overlapping maps", "neutral portrait", "ancient clothing", "robe", "all-male group"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Four predecessor cultural zones"):
                for phrase in ("four-panel layout", "artifact grid", "fifth person", "family group", "utility pole", "modern house"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Y chromosome lineages"):
                for phrase in ("crowded laboratory", "lab crowd", "many vials", "DNA chart", "infographic"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Corded Ware community transitioning"):
                for phrase in ("chimney", "modern farmhouse", "glass window", "pottery row", "fourth person", "all-male group", "utility pole", "power line"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Gloved technicians processing"):
                for phrase in ("loose skull", "scattered skulls", "loose bones", "bone pile", "dirty laboratory", "artifact display", "ancient person", "brown robe", "third person"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Ancient population map showing"):
                for phrase in ("church", "steeple", "medieval village", "stone house", "chimney", "migration arrow"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Mixed-ancestry couple"):
                for phrase in ("church", "steeple", "medieval village", "white wedding gown", "bridal veil", "white robe", "headcloth", "armed relatives"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith(("Firm evidence panel", "Steppe migration routes", "Yamnaya chief looking west")):
                for phrase in ("church", "steeple", "watchtower", "castle tower", "medieval village", "chimney", "migration arrow"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Wagons, marriage bonds"):
                for phrase in ("spoked wheel", "radial spokes", "open wheel", "wheel gaps", "chariot wheel", "covered wagon", "medieval cart"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Male war band displaying"):
                for phrase in ("third person", "extra person", "double-headed axe", "halberd", "gripped weapon"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Dramatic invasion mural"):
                for phrase in ("open book", "notebook", "loose paper", "clipboard", "ancient clothing", "battlefield"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Two regional Yamnaya burials"):
                for phrase in ("third mourner", "extra mourner", "exposed corpse face", "visible corpse hair", "open shroud"):
                    self.assertIn(phrase, compiled.negative)
            if scene.startswith("Successive farmer leaders"):
                for phrase in ("stone tower", "castle tower", "church", "steeple", "medieval village", "classroom", "fourth person", "second child"):
                    self.assertIn(phrase, compiled.negative)
            self.assertNotIn("Object-only", compiled.positive)

    def test_narration_aligned_ch2_noncombat_scenes_do_not_invent_war(self):
        cases = (
            (
                "Yamnaya chief judging a dispute before several clan representatives and tethered herds",
                "raises one open palm to settle a verbal dispute",
                "copper dagger stays sheathed",
            ),
            (
                "Kurgan cemetery emphasizing richly furnished male graves beside sparse ordinary burials",
                "three open earthen pit burials",
                "without timber coffins",
            ),
            (
                "Corded Ware cemetery in Germany with sampled teeth and a glowing ancient-DNA profile",
                "Two separate full-body modern archaeogeneticists",
                "molar with forceps above a blank vial",
            ),
        )
        for scene, expected_a, expected_b in cases:
            with self.subTest(scene=scene):
                prompt = (
                    "Year/period: 3500 BCE to 2000 BCE; European historical documentary "
                    "scene, 3500 BCE to 2000 BCE; Exact place: Pontic-Caspian Steppe, Balkans, "
                    "Central Europe; Yamnaya cultural horizon, Neolithic European communities; "
                    f"Main subject: {scene}; Scene: {scene}, archaeologically grounded late "
                    "Neolithic and early Bronze Age reconstruction; Global style: stylish adult "
                    "hard-boiled historical action cartoon, rough extra-thick bold black ink "
                    "contour lines NARRATIVE_FIDELITY_REGEN_V1; NARRATION VISUAL ALIGNMENT: "
                    "match the spoken moment; Narration context: historical evidence"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected_a, compiled.positive)
                self.assertIn(expected_b, compiled.positive)
                self.assertIn("Visible action:", compiled.positive)
                self.assertIn("invented battle", compiled.negative)

    def test_narration_aligned_ch2_crowd_does_not_enforce_exact_headcount(self):
        prompt = (
            "Year/period: 3500 BCE to 2000 BCE; "
            "European historical documentary scene, 3500 BCE to 2000 BCE; "
            "Exact place: Pontic-Caspian Steppe, Balkans, Central Europe; "
            "Yamnaya cultural horizon, Neolithic European communities; "
            "Main subject: Kurgan cemetery emphasizing richly furnished male graves "
            "beside sparse ordinary burials; "
            "Scene: Kurgan cemetery emphasizing richly furnished male graves beside "
            "sparse ordinary burials, archaeologically grounded late Neolithic and "
            "early Bronze Age reconstruction with tense human storytelling, 3500 BCE "
            "to 2000 BCE, Pontic-Caspian Steppe, Balkans, Central Europe, Yamnaya "
            "cultural horizon, Neolithic European communities, period-accurate clothing, "
            "architecture, tools, and material culture; "
            "Global style: hard-boiled cartoon NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: Graves reveal hierarchy, gender, and concentrated privilege"
        )

        compiled = self.compile(prompt)

        self.assertIsNone(compiled.person_count)
        self.assertIn("hand-only composition", compiled.negative)
        self.assertIn("extra legs", compiled.negative)

    def test_narration_aligned_group_count_allows_five_or_six_people(self):
        prompt = (
            "Year/period: Japanese mythic creation era; Culture scope: Kojiki and Nihon "
            "Shoki Japanese creation myth; Main subject: exactly five adult deities; "
            "Scene: five adult deities gather around the harvested grains; Global style: "
            "stylish adult hard-boiled historical action cartoon, rough extra-thick bold "
            "black ink contour lines NARRATIVE_FIDELITY_REGEN_V1; NARRATION VISUAL "
            "ALIGNMENT: match the spoken moment; Narration context: the gods gather around life"
        )

        compiled = self.compile(prompt)

        self.assertIsNone(compiled.person_count)
        self.assertNotIn("sixth foreground person", compiled.negative)
        self.assertIn("extra legs", compiled.negative)

    def test_narration_aligned_hand_and_foot_macros_become_complete_body_scenes(self):
        cases = (
            (
                "Amaterasu pointing a harsh, judging finger directly at the silver moon god",
                "waist-up two-shot",
            ),
            (
                "A baby's hand reaching out from dark, rich soil to grab a golden stalk of rice",
                "full-body ancient farming household",
            ),
            (
                "The messenger god falling to his knees, pressing his hands together in pure reverence",
                "Ame no Kumahito kneels in full-body view",
            ),
            (
                "Amaterasu holding a single, glowing grain of rice gently in the palm of her hand",
                "three-quarter scene",
            ),
            (
                "A rugged, ancient farmer staring in awe at a sprouting seed in his dirt-covered hands",
                "kneels in full-body view",
            ),
            (
                "Two highly detailed hands pressed firmly together in prayer over a bowl of rice",
                "wide full-body scene",
            ),
            (
                "Divine hands gently offering fresh, green mulberry leaves to a cluster of white silkworms",
                "three-quarter full-body scene",
            ),
            (
                "Massive, armored feet violently striking a cloudy staircase, cracking the white stone",
                "dynamic full-body view",
            ),
            (
                "Amaterasu gripping the arms of her golden throne, trembling with sudden, intense emotion",
                "full-body throne scene",
            ),
            (
                "Glowing green jade beads clinking together as they are tightly wrapped around divine wrists",
                "three-quarter preparation scene",
            ),
            (
                "Divine bare feet stomping so hard into the heavenly ground that the stone shatters like ice",
                "full-body defensive stance",
            ),
            (
                "Susanoo standing up slowly, picking up his heavy iron sword from the dirt",
                "plain archaic straight bronze blade",
            ),
            (
                "Two incredibly sharp, polished iron swords crossing violently, creating bright golden sparks",
                "wide full-body confrontation",
            ),
            (
                "A beautifully crafted iron sword and green jade beads being crushed by massive divine teeth",
                "waist-up oath ritual",
            ),
        )
        for scene, expected in cases:
            with self.subTest(scene=scene):
                prompt = (
                    f"Scene: {scene}; Global style: stylish adult hard-boiled historical action "
                    "cartoon, rough extra-thick bold black ink contour lines "
                    "NARRATIVE_FIDELITY_REGEN_V1; NARRATION VISUAL ALIGNMENT: match the spoken "
                    "moment; Narration context: Japanese creation myth"
                )
                compiled = self.compile(prompt)
                self.assertIn(expected, compiled.positive)
                self.assertIn("hand-only composition", compiled.negative)
                self.assertIn("extra legs", compiled.negative)

    def test_narration_aligned_ch3_ep7_keeps_uke_mochi_story_action(self):
        prompt = (
            "Year/period: Japanese mythic creation era; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Uke Mochi in an archaic earth-tone robe; "
            "Scene: A heavy aged-bronze blade cuts through a peaceful meal as Uke Mochi recoils; "
            "Global style: historical cartoon NARRATIVE_FIDELITY_REGEN_V1; "
            "NARRATION VISUAL ALIGNMENT: match this cut's spoken moment through visible action; "
            "Narration context: 食べ物を司る女神ウケモチが殺される悲劇です"
        )

        compiled = self.compile(prompt)

        self.assertIn("Uke Mochi recoils", compiled.positive)
        self.assertIn("complete visible action dominates", compiled.positive)
        self.assertNotIn("食べ物を司る女神ウケモチ", compiled.positive)
        self.assertIn("isolated hand close-up", compiled.negative)
        self.assertIn("samurai", compiled.negative)
        self.assertIn("katana", compiled.negative)
        self.assertIn("torii gate", compiled.negative)
        self.assertNotIn("object-only non-graphic Uke Mochi", compiled.positive)
        self.assertIsNone(_exact_layout_reference_spec(prompt))

    def test_yamnaya_chief_return_shot_excludes_transport_and_tokens(self):
        compiled = self.compile(
            "Year/period: 3500 BCE to 2000 BCE; Exact place: Pontic-Caspian steppe; "
            "Culture scope: Yamnaya pastoral communities; "
            "Main subject: Yamnaya chief alive beside a fresh kurgan as followers; "
            "Scene: Yamnaya chief alive beside a fresh kurgan as followers, wagons, and herds assemble, "
            "character continuity: Yamnaya chief in a plain woven-wool cloak; "
            "Narration context: Return now to the anonymous chief standing above his newly raised burial mound."
        )

        self.assertIn("knee-high, very low, wide, smooth sealed earthen kurgan", compiled.positive)
        self.assertIn("no other person, animal, transport, token, or loose object appears", compiled.positive)
        self.assertNotIn("wagon token", compiled.positive)
        self.assertNotIn("herd disks", compiled.positive)
        self.assertNotIn("solid disk wheel", compiled.positive)
        self.assertIn("wagon", compiled.negative)
        self.assertIn("solid disk wheel", compiled.negative)
        self.assertIn("herd disk", compiled.negative)

    def test_cadmus_and_spartoi_scenes_replace_maps_duplicates_and_static_lineups(self):
        cases = (
            (
                "Delphic priestess turning Cadmus away from a map marked with Europa's face",
                "pair",
                2,
                ("mature priestess raises one open palm", "both empty hands lowered"),
                ("map", "readable text"),
            ),
            (
                "Cadmus discarding old search maps and walking behind the cow",
                "single",
                1,
                ("Cadmus's exhausted face", "exactly one ordinary dark cow"),
                ("map", "second cow"),
            ),
            (
                "Cadmus and cow traveling through rugged Phocian valleys toward Boeotian plains",
                "single",
                1,
                ("exactly one ordinary dark cow", "Cadmus follows alone"),
                ("second cow", "cattle herd"),
            ),
            (
                "Bronze spearheads and helmets pushing upward through the soil around Cadmus",
                "object",
                0,
                ("Extreme ground-level macro", "one bronze spearhead"),
                ("standing army", "skeleton"),
            ),
            (
                "Close combat among Spartoi with broken shields and scattered weapons",
                "object",
                0,
                ("Extreme material-detail close-up", "one split round shield"),
                ("crowd", "full-body warrior"),
            ),
            (
                "Five surviving Spartoi standing wounded among fallen earth-born warriors",
                "group",
                5,
                ("five distinct poses", "exactly five separate heads and bodies"),
                ("sixth person", "crowd"),
            ),
            (
                "Dragon teeth, stone trick, five nobles, and Theban walls connected in one genealogy",
                "group",
                5,
                ("Low wide construction action", "single weathered dragon jaw"),
                ("standing lineup", "genealogy chart"),
            ),
            (
                "Actaeon transformed as his hunting hounds turn against him on Mount Cithaeron",
                "group",
                1,
                ("Low diagonal chase action", "four separate hounds"),
                ("horse", "missing hounds"),
            ),
            (
                "War council placing aged Cadmus and Harmonia at the center of an invasion map",
                "group",
                3,
                ("Rocky outdoor oracle scene", "distant Illyrian mountain pass"),
                ("map", "young couple"),
            ),
            (
                "Cadmus as serpent looking back toward the spring dragon and Theban walls",
                "animal",
                0,
                ("Animal-only serpent wildlife plate", "sole living subject"),
                ("human Cadmus", "second serpent"),
            ),
            (
                "Europa's empty place branching into Cilicia, Thasos, Thebes, Illyria, and Crete",
                "landscape",
                0,
                ("Wide physical coastal panorama", "three small ships diverge"),
                ("map", "fragmented body"),
            ),
            (
                "Adult Minos standing before Europa and the Cretan royal throne",
                "pair",
                2,
                ("Medium mother-and-son two-shot", "simple undecorated stone seat"),
                ("Egyptian throne", "hieroglyph"),
            ),
        )
        trailer = (
            ", vivid Bronze Age Mediterranean myth reconstruction grounded in Phoenician, "
            "Cretan, and early Greek material culture, 2000 BCE to 1200 BCE, "
            "period-accurate clothing, architecture, tools, and material culture"
        )

        for scene, scene_kind, person_count, positive_terms, negative_terms in cases:
            with self.subTest(scene=scene):
                compiled = self.compile(
                    "Year/period: 2000 BCE to 1200 BCE; Exact place: Eastern Mediterranean; "
                    f"Main subject: {scene}; Scene: {scene}{trailer}"
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertEqual(compiled.person_count, person_count)
                for term in positive_terms:
                    self.assertIn(term, compiled.positive)
                for term in negative_terms:
                    self.assertIn(term, compiled.negative)

    def test_z_image_animal_only_style_does_not_reintroduce_people(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Visible action: Animal-only serpent wildlife plate: exactly one coiled snake is the "
            "sole living subject. Primary subject: exactly one solitary large serpent. "
            "Era/period: 2000 BCE to 1200 BCE. Exact place: bare ridge. "
            "Style: elongated angular adult anatomy; weathered expressive adult faces.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("HISTORICAL MANHWA ANIMAL STYLE LOCK", styled)
        self.assertIn("Zero people, human anatomy, clothing, buildings, walls", styled)
        self.assertNotIn("Adult faces are weathered", styled)
        self.assertNotIn("elongated angular adult anatomy", styled)
        self.assertNotIn("weathered expressive adult faces", styled)

    def test_historical_style_uses_neutral_daylight_full_color(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Visible action: one adult ruler crosses a stone courtyard. "
            "Primary subject: one adult ruler. Era/period: fourth century. "
            "Exact place: historical capital.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("NEUTRAL-DAYLIGHT FULL-COLOR LOCK", styled)
        self.assertIn("preserve soot-black ink, hatching, and shadow depth", styled)
        self.assertIn("muted mineral-blue, natural vegetation-green", styled)
        self.assertIn("chromatic separation remains clear across the complete frame", styled)
        self.assertNotRegex(styled, r"(?i)\bsepia\b|\btobacco(?:-brown|\s+brown)?\b")

    def test_flux2_9b_receives_full_color_historical_style_with_half_warmth(self):
        self.assertIn("comfyui-flux2-klein-9b", _LONGTUBE_DARK_MANHWA_STYLE_MODELS)
        styled = _apply_longtube_dark_manhwa_style(
            "Visible action: King Chimnyu receives Marananta. "
            "Style: sepia dirty ivory tobacco brown historical manhwa.",
            model_id="comfyui-flux2-klein-9b",
        )

        self.assertIn("NEUTRAL-DAYLIGHT FULL-COLOR LOCK", styled)
        self.assertIn("at no more than half strength", styled)
        self.assertIn("it never becomes a full-frame brown wash", styled)
        self.assertNotRegex(styled, r"(?i)\bsepia\b|\btobacco(?:-brown|\s+brown)?\b")

    def test_flux2_baekje_ep06_rotates_six_distinct_camera_directions(self):
        directions = []
        for row in range(10, 16):
            directions.append(
                _flux2_baekje_ep06_visual_direction(
                    "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
                    f"Scene evidence: Source workbook row 06-{row:03d} anchors this scene to 384 AD; "
                    "Scene: one court action. || Narration context: 관리들이 새로운 의례를 지켜봅니다"
                )
            )

        self.assertEqual(len(set(directions)), len(_FLUX2_BAEKJE_EP06_SHOT_DIRECTIONS))
        for direction in directions:
            self.assertIn("BAEKJE EP06 FLUX2 COMPOSITION VARIETY LOCK", direction)
            self.assertIn("Do not fall back to a repeated eye-level medium court lineup", direction)

    def test_flux2_baekje_ep06_rows_70_to_159_use_narration_specific_frames(self):
        cases = {
            70: "LOW-ANGLE SINGLE-PERSON ORDINATION PORTRAIT",
            77: "OBJECT-ONLY ADMINISTRATIVE FINANCE MACRO",
            81: "CAPITAL-TO-PROVINCES PANORAMA",
            92: "PEOPLE-FREE EMPTY-PEDESTAL INTERIOR",
            99: "RESPECTFUL DEATH-CHAMBER FRAME",
            100: "TIGHT SINGLE-PERSON CHIMNYU DEATHBED PORTRAIT",
            103: "TWO-PLANE JINSA-ASIN SUCCESSION PORTRAIT",
            107: "OBJECT-ONLY LAMP-AND-SEAL-CORD CONTRAST",
            110: "TIGHT SINGLE-PERSON KING ASIN PROCLAMATION",
            115: "TIGHT SINGLE-PERSON OLDER MARANANTA PORTRAIT",
            120: "LANDSCAPE-ONLY THREE-REGIONAL-HALL PANORAMA",
            124: "TIGHT PROTECTIVE CHIMNYU-MARANANTA PORTRAIT",
            129: "BACKLIT SINGLE-PERSON MARANANTA ARRIVAL",
            130: "HIGH WIDE EARLY-TO-LATER BAEKJE CULTURAL LANDSCAPE",
            134: "OBJECT-ONLY EXACT NEUNGSAN-RI BAEKJE GILT-BRONZE INCENSE BURNER",
            139: "LANDSCAPE-DOMINANT EASTBOUND SINGLE-BOAT ROUTE",
            144: "EXTREME SINGLE-PERSON CHIMNYU LEGACY CLOSE-UP",
            149: "PEOPLE-FREE COEXISTING-FAITH STILL LIFE",
            154: "INTIMATE EXACT-TWO DOMI-COUPLE PORTRAIT",
            159: "CLOSING WIDE EXACT-TWO DOMI-COUPLE SUNRISE",
        }
        for row, expected in cases.items():
            with self.subTest(row=row):
                direction = _flux2_baekje_ep06_visual_direction(
                    "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
                    f"Scene evidence: Source workbook row 06-{row:03d} anchors this scene to 384 AD; "
                    "Scene: one historical action. || Narration context: 장면별 대본"
                )
                self.assertIn(expected, direction)
                self.assertIn("Do not fall back to a repeated eye-level medium court lineup", direction)

    def test_flux2_baekje_ep06_important_figure_gets_emotional_closeup(self):
        direction = _flux2_baekje_ep06_visual_direction(
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Scene evidence: Source workbook row 06-010 anchors this scene to 384 AD; "
            "Scene: court reception. || Narration context: 삼백팔십사년, 바다 건너온 낯선 승려를 "
            "백제 왕이 궁으로 불러들였습니다"
        )

        self.assertIn("IMPORTANT-FIGURE EMOTION LOCK", direction)
        self.assertIn("head-and-shoulders or chest-up focal plane", direction)
        self.assertIn("eyes, brow, jaw, breath, and posture", direction)

    def test_flux2_baekje_ep06_resume_expected_prompt_keeps_visual_direction(self):
        source = (
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Scene evidence: Source workbook row 06-010 anchors this scene to 384 AD; "
            "Scene: court reception. || Narration context: 삼백팔십사년, 바다 건너온 낯선 승려를 "
            "백제 왕이 궁으로 불러들였습니다"
        )
        expected = expected_comfyui_positive_prompt(
            source,
            image_model="comfyui-flux2-klein-9b",
            prompt_profile=SCENE_CONTRACT_V2,
        )

        self.assertTrue(expected.startswith("BAEKJE EP06 FLUX2 COMPOSITION VARIETY LOCK"))
        self.assertIn("BAEKJE CLEAN-SURFACE LOCK", expected)
        self.assertIn("NEUTRAL-DAYLIGHT FULL-COLOR LOCK", expected)

    def test_flux2_baekje_ep06_object_only_does_not_add_important_figure_closeup(self):
        direction = _flux2_baekje_ep06_visual_direction(
            "Global visual world: Time range: 384 AD; Culture scope: Baekje and Eastern Jin; "
            "Scene evidence: Source workbook row 06-022 anchors this scene to 384 AD; "
            "Scene: Object-only strict overhead record view concerning Marananta. "
            "|| Narration context: 마라난타에 관한 기록을 살핍니다"
        )

        self.assertIn("Preserve the source scene's exact people count", direction)
        self.assertNotIn("IMPORTANT-FIGURE EMOTION LOCK", direction)

    def test_baekje_chiljido_ep05_uses_exact_sword_geometry_lock_automatically(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-010 anchors this scene to Late 4th century AD; "
            "Scene: Eye-level medium shot inside a historically grounded Baekje settlement, "
            "visualizing this decisive historical beat: There is a strange iron sword with six "
            "branches extending from both sides of the blade. Focused gestures and surrounding "
            "reactions make the immediate historical stakes readable. || "
            "Narration context: 칼날 양옆에서 여섯 개의 가지가 뻗어 나온 기묘한 철검이 있습니다"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("Seven-branch-sword-only artifact plate", compiled.positive)
        self.assertIn("exactly six side branches", compiled.positive)
        self.assertNotIn("historically grounded Baekje settlement", compiled.positive)
        self.assertIn("SEVEN-BRANCHED SWORD GEOMETRY LOCK", styled)

    def test_baekje_chiljido_ep05_1873_discovery_uses_action_closeup(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-029 anchors this scene to Late 4th century AD; "
            "Scene: Wide establishing view across a historically grounded Baekje settlement, "
            "visualizing this decisive historical beat. || "
            "Narration context: 칠지도에 붙은 녹을 조심스럽게 닦아내다가 예상하지 못한 빛을 발견합니다"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("1873 over-the-shoulder action close-up", compiled.positive)
        self.assertIn("one small soft brush", compiled.positive)
        self.assertIn("1873 AD; Isonokami Shrine", compiled.positive)
        self.assertNotIn("historically grounded Baekje settlement", compiled.positive)

    def test_baekje_chiljido_ep05_branch_collision_uses_impact_macro(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-002 anchors this scene to Late 4th century AD; "
            "Scene: one complete sword standing on a plain conservation cloth. || "
            "Narration context: 이 모양으로는 적을 베기도 어렵고 칼끼리 부딪치면 가지부터 걸리겠죠"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("dynamic impact macro", compiled.positive)
        self.assertIn("hooks across the flat of exactly one plain straight opposing iron blade", compiled.positive)
        self.assertNotIn("Seven-branch-sword-only", compiled.positive)
        self.assertNotIn("standing on a plain conservation cloth", compiled.positive)

    def test_baekje_chiljido_ep05_diplomatic_evidence_uses_handover_action(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-005 anchors this scene to Late 4th century AD; "
            "Scene: one generic sword on a blank table. || "
            "Narration context: 칠지도는 천육백 년 전 백제 외교를 둘러싼 가장 날카로운 증거가 됩니다"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 3)
        self.assertIn("diplomatic handover", compiled.positive)
        self.assertIn("long closed plain wooden gift case", compiled.positive)
        self.assertIn("Eastern Jin observer", compiled.positive)
        self.assertIn("each visible adult has one head and one coherent torso", compiled.positive)
        self.assertNotIn("one generic sword on a blank table", compiled.positive)

    def test_baekje_chiljido_ep05_period_scene_uses_empty_oared_port(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-006 anchors this scene to Late 4th century AD; "
            "Scene: King Geunchogo before a tiled palace. || "
            "Narration context: 이야기의 중심 시기는 근초고왕 전성기와 맞닿은 사세기 후반입니다"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("extreme close-up from inside exactly one", compiled.positive)
        self.assertIn("camera is below the gunwale", compiled.positive)
        self.assertNotIn("King Geunchogo before a tiled palace", compiled.positive)

    def test_baekje_chiljido_ep05_present_repository_excludes_modern_vehicle(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje; "
            "Scene evidence: Source workbook row 05-013 anchors this scene; "
            "Exact place: Isonokami Shrine, Tenri, Nara; "
            "Scene: broad parking area with a modern car. || "
            "Narration context: 현재 칠지도는 일본 나라현 덴리시의 이소노카미신궁에 보관돼 있고"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("hand-forged iron strap hinge", compiled.positive)
        self.assertIn("car, vehicle, parking area", compiled.positive)
        self.assertNotIn("broad parking area with a modern car", compiled.positive)

    def test_baekje_chiljido_ep05_hidden_gold_is_flat_iron_not_container(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje; "
            "Scene evidence: Source workbook row 05-015 anchors this scene; "
            "Scene: a bronze cauldron on a table. || "
            "Narration context: 하지만 오늘 우리가 보는 금빛 글자는 오랫동안 녹 아래 잠들어 있었죠"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("continuous solid flat ancient iron plane", compiled.positive)
        self.assertIn("granular black-brown corrosion", compiled.positive)
        self.assertIn("cauldron", compiled.negative)
        self.assertIn("teapot", compiled.negative)
        self.assertIn("geology", compiled.negative)
        self.assertIn("human face", compiled.negative)
        self.assertIn("mask", compiled.negative)
        self.assertNotIn("bronze cauldron on a table", compiled.positive)
        self.assertIn("MATERIAL SURFACE MACRO STYLE LOCK", styled)
        self.assertNotIn("HISTORICAL MANHWA OBJECT STYLE LOCK", styled)

    def test_baekje_chiljido_ep05_rust_macro_excludes_pipe_shape(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje; "
            "Scene evidence: Source workbook row 05-018 anchors this scene; "
            "Scene: one hollow rusted pipe. || "
            "Narration context: 표면을 뒤덮은 녹은 제작 당시의 이름과 목적을 완전히 가리고 있었죠"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("solid flat iron branch junction", compiled.positive)
        self.assertIn("Every frame edge cuts through dense rough", compiled.positive)
        self.assertIn("pipe", compiled.negative)
        self.assertIn("whole sword", compiled.negative)
        self.assertNotIn("one hollow rusted pipe", compiled.positive)

    def test_baekje_chiljido_ep05_late_inscription_scene_cannot_fall_back_to_modern_shirt(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-049 anchors this scene; "
            "Scene: a modern man in an English-print T-shirt holds an ordinary sword before a readable document. || "
            "Narration context: 뒷면에서는 지금까지 이런 칼이 없었다는 선언이 먼저 나타납니다"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("continuous flat forged-iron plane", compiled.positive)
        self.assertIn("modern T-shirt", compiled.negative)
        self.assertIn("English text", compiled.negative)
        self.assertIn("ordinary straight sword", compiled.negative)
        self.assertNotIn("modern man in an English-print T-shirt", compiled.positive)
        self.assertIn("MATERIAL SURFACE MACRO STYLE LOCK", styled)

    def test_baekje_chiljido_ep05_shape_explanation_uses_distinct_scene_contracts(self):
        cases = (
            (
                "칠지도의 전체 길이는 칠십사점구 센티미터로 알려져 있습니다",
                "pair",
                2,
                "two bareheaded Korean conservators",
            ),
            (
                "중앙의 긴 몸체 양쪽에는 가지가 세 개씩 일정한 간격으로 뻗고",
                "object",
                0,
                "Exactly six solid non-forked rectangular iron lugs",
            ),
            (
                "끝의 칼날까지 세면 모두 일곱 갈래처럼 보이기 때문에 이름도 붙었죠",
                "object",
                0,
                "Seven-branch-sword-only",
            ),
            (
                "이 독특한 형태와 정확히 같은 칼은 아직 다른 곳에서 확인되지 않았습니다",
                "object",
                0,
                "one long closed rectangular artifact case",
            ),
            (
                "전투에서 휘두르면 옆 가지가 방패나 무기에 걸리고 쉽게 손상될 수 있어",
                "object",
                0,
                "SHICHISHITO-BRANCH-IMPACT-REFERENCE",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
                    "Scene evidence: Source workbook row 05-035 anchors this scene to Late 4th century AD; "
                    "Scene: a repeated ordinary sword beside an idle crowd. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertNotIn("repeated ordinary sword beside an idle crowd", compiled.positive)

    def test_baekje_chiljido_ep05_noncombat_and_preservation_scenes_stay_literal(self):
        cases = (
            (
                "분명한 점은 칠지도가 전장에서 많이 사용할 목적으로 만든 물건이 아니라",
                "single",
                1,
                "pulls one simple fibre cord firmly around one long completely closed undecorated wooden diplomatic gift case",
            ),
            (
                "후세에 전하여 보이라는 뜻으로 칼을 오래 보존할 이유까지 남겼습니다",
                "object",
                0,
                "exactly one plain closed steel latch bridges one narrow seam",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
                    "Scene evidence: Source workbook row 05-043 anchors this Seven-branched Sword scene; "
                    "Scene: a repeated ordinary sword beside an idle crowd. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertNotIn("repeated ordinary sword beside an idle crowd", compiled.positive)

    def test_baekje_chiljido_ep05_date_and_diplomacy_finale_uses_literal_scenes(self):
        cases = (
            (
                "명문 첫머리에는 태라는 글자 뒤에 손상된 글자 하나와 사년이 보입니다",
                "single",
                1,
                "exactly one older silver-haired Korean woman",
            ),
            (
                "중국의 다른 태 계통 연호를 대입한 여러 제작 연대가 제시됐고",
                "pair",
                2,
                "Present-day extreme two-face close-up",
            ),
            (
                "제작 연대보다 더 뜨거운 문제는 누가 누구에게 어떤 자격으로 줬느냐입니다",
                "group",
                3,
                "three-person diplomatic triangle",
            ),
            (
                "이를 백제 왕이 왜왕에게 하사했다는 뜻으로 읽는 견해가 나옵니다",
                "pair",
                2,
                "two-person formal handover",
            ),
            (
                "동진의 물건을 백제가 중개했다는 주장까지 제기된 적이 있습니다",
                "group",
                3,
                "three-person mediation",
            ),
            (
                "칼을 건넨 순간보다 그 뒤 천육백 년의 보존이 관계의 무게를 증명합니다",
                "object",
                None,
                "exactly one completely closed long dark wooden artifact case",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
                    "Scene evidence: Source workbook row 05-076 anchors this scene; "
                    "Scene: a fake readable document beside a modern camera lens. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertNotIn("a fake readable document beside a modern camera lens", compiled.positive)

    def test_baekje_chiljido_ep05_late_diplomatic_scene_keeps_three_distinct_roles(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-053 anchors this scene; "
            "Scene: idle crowd beside pots and ordinary swords. || "
            "Narration context: 만든 쪽과 받는 쪽, 제작 이유가 한 물건 안에 함께 들어 있기 때문이죠"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 3)
        self.assertIn("one Baekje metalworker", compiled.positive)
        self.assertIn("one envoy", compiled.positive)
        self.assertIn("one Wa recipient", compiled.positive)
        self.assertIn("pot", compiled.negative)
        self.assertIn("static lineup", compiled.negative)
        self.assertNotIn("idle crowd beside pots", compiled.positive)

    def test_baekje_chiljido_ep05_wani_chronology_finale_uses_literal_scenes(self):
        cases = (
            (
                "칠지도처럼 정교한 금상감 철기는 백제 금속기술의 수준을 보여 주며",
                "single",
                1,
                "one thin gold wire into one shallow groove",
            ),
            (
                "받은 쪽은 칼을 신궁에 보관해 왕실과 신성한 권위에 연결했고",
                "pair",
                2,
                "two bareheaded adult male custodians",
            ),
            (
                "실전에서 쓰지 않았기에 독특한 형태와 명문도 비교적 오래 남았습니다",
                "object",
                0,
                "Seven-branch-sword-only strict top-down artifact plate",
            ),
            (
                "아직기가 먼저 건너간 뒤 더 뛰어난 학자로 왕인을 추천했다는 전승도 남죠",
                "group",
                3,
                "three-person Wa court introduction",
            ),
            (
                "기록 사이에는 왕인의 활동 시점만 삼사십 년 가까이 차이가 납니다",
                "pair",
                2,
                "thirty-to-forty-year discrepancy",
            ),
            (
                "오늘 알려진 천자문은 중국 양나라 무제 때 육세기에 만들어졌으므로",
                "single",
                1,
                "sixth-century Liang bookbinding workshop",
            ),
            (
                "사오세기 인물인 왕인이 그 책을 가져갔다는 전승과 맞지 않죠",
                "pair",
                2,
                "two-person contradiction review",
            ),
            (
                "왕인과 아직기를 지우는 것이 아니라 전승의 층을 나누는 일이며",
                "group",
                3,
                "three-person evidence-sorting scene",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
                    "Scene evidence: Source workbook row 05-096 anchors this scene; "
                    "Scene: a fake readable document beside an idle crowd and ordinary swords. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertIn("readable writing", compiled.negative)
                self.assertNotIn(
                    "a fake readable document beside an idle crowd and ordinary swords",
                    compiled.positive,
                )

    def test_baekje_chiljido_ep05_exchange_and_preview_finale_uses_literal_scenes(self):
        cases = (
            (
                "백제에서 왜로 건너간 사람들은 학자만이 아니었습니다",
                "group",
                None,
                "exactly six distinct Baekje migrants",
            ),
            (
                "박사 고흥이 서기를 편찬했다는 전승도 문자 행정의 성장을 보여 주지만",
                "single",
                1,
                "single-scribe action",
            ),
            (
                "책이 남아 있지 않아 구체적인 내용은 상상으로 채울 수 없습니다",
                "object",
                0,
                "conspicuously empty central cradle",
            ),
            (
                "칠지도 명문은 사라진 서기와 달리 당시 문자를 직접 눈앞에 남겼고",
                "object",
                0,
                "Exactly five tiny isolated straight gold-inlay stubs",
            ),
            (
                "칠지도는 그 교환 속에서 백제가 가졌던 자신감을 드러낸 물건입니다",
                "object",
                0,
                "Seven-branch-sword-only diagonal artifact plate",
            ),
            (
                "손상된 연호는 삼백육십구년설을 유력하게 하면서도 논쟁을 남깁니다",
                "object",
                0,
                "Broad untouched corrosion fully isolates each stub",
            ),
            (
                "이소노카미신궁에 남은 철검은 그 관계를 직접 증언합니다",
                "object",
                0,
                "Seven-branch-sword-only strict top-down shrine conservation plate",
            ),
            (
                "녹을 벗겨낸 금빛 글자는 찬란한 자랑만이 아니라 해석의 책임도 요구했고",
                "single",
                1,
                "single-conservator action",
            ),
            (
                "한 글자를 원하는 방향으로 읽으면 외교사는 곧 선전으로 변합니다",
                "pair",
                2,
                "two-person warning",
            ),
            (
                "삼백팔십사년 마라난타가 동진에서 도착하자 침류왕은 그를 궁중으로 맞고",
                "group",
                3,
                "Buddhist monk Marananta",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
                    "Scene evidence: Source workbook row 05-121 anchors this scene; "
                    "Scene: a fake readable document beside an idle crowd and ordinary swords. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertIn("readable writing", compiled.negative)
                if narration in {
                    "칠지도 명문은 사라진 서기와 달리 당시 문자를 직접 눈앞에 남겼고",
                    "손상된 연호는 삼백육십구년설을 유력하게 하면서도 논쟁을 남깁니다",
                }:
                    self.assertIn("kintsugi", compiled.negative)
                self.assertNotIn(
                    "a fake readable document beside an idle crowd and ordinary swords",
                    compiled.positive,
                )

    def test_baekje_chiljido_ep05_geunchogo_exchange_has_no_crown_or_armor(self):
        source = (
            "Year/period: Late 4th century AD; Culture scope: Baekje, Eastern Jin, and Wa; "
            "Scene evidence: Source workbook row 05-010 anchors this scene to Late 4th century AD; "
            "Scene: crowned king with armored guards. || "
            "Narration context: 근초고왕은 백제 제십삼대 왕으로 정복과 외교를 결합한 군주였으며"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("bareheaded adult Baekje ruler", compiled.positive)
        self.assertIn("undecorated dark-red hemp cross-collar robe", compiled.positive)
        self.assertNotIn("crowned king with armored guards", compiled.positive)

    def test_minoan_ep06_empty_akrotiri_stays_uninhabited(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete, Aegean Sea; "
            "Main subject: Ash-buried Akrotiri with intact rooms; "
            "Scene: Ash-buried Akrotiri with intact rooms, empty streets, abandoned vessels, "
            "and no human remains; Scene evidence: Source workbook scene: Ash-buried Akrotiri "
            "with intact rooms; || Narration context: An entire island city disappears under ash, "
            "yet archaeologists find no bodies in its streets"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")
        styled = _apply_longtube_dark_manhwa_style(
            compiled.positive,
            model_id="comfyui-z-image-turbo",
        )

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("panoramic landscape", compiled.positive)
        self.assertNotIn("one adult with one head", compiled.positive)
        self.assertIn("HISTORICAL MANHWA LANDSCAPE STYLE LOCK", styled)
        self.assertNotIn("Adult faces are weathered", styled)

    def test_minoan_ep06_earthquake_escape_stays_group_action(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Akrotiri, Thera; "
            "Main subject: families fleeing a collapsing street; "
            "Scene: families rush outside while dust hides neighbors only a few steps away; "
            "Scene evidence: Source workbook scene: Akrotiri earthquake evacuation; "
            "|| Narration context: Families rush outside while dust hides neighbors only a few steps away"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "group")
        self.assertIsNone(compiled.person_count)
        self.assertNotIn("one adult with one head", compiled.positive)

    def test_minoan_ep06_earthquake_warning_excludes_horizon_and_volcano(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Akrotiri, Thera; "
            "Main subject: first earthquake warning in a paved street; "
            "Scene: a distant volcano above the town; "
            "Scene evidence: Source workbook scene: Akrotiri earthquake warning; "
            "|| Narration context: The disaster did not arrive as one instant; the ground warned them first"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("near-vertical downward close-up", compiled.positive)
        self.assertIn("there is no horizon or sky", compiled.positive)
        self.assertNotIn("distant volcano above the town", compiled.positive)

    def test_minoan_ep06_zakros_burn_uses_bronze_age_coast_not_castle(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Zakros, Crete; "
            "Main subject: a medieval castle and tall galleons; "
            "Scene evidence: Source workbook scene: Zakros palace burns; "
            "|| Narration context: Zakros burns near the eastern coast, cutting a palace deeply tied to overseas exchange"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("low flat-roofed plaster-and-mudbrick palace", compiled.positive)
        self.assertNotIn("medieval castle and tall galleons", compiled.positive)

    def test_minoan_ep06_evacuation_keeps_all_three_distinct_actor_slots(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Knossos, Crete; "
            "Main subject: identical men standing in a line; "
            "Scene evidence: Source workbook scene: evacuation through a processional corridor; "
            "|| Narration context: People run through complexes designed for processions, not rapid defense or evacuation"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertIn("gaunt elder has long white hair", compiled.positive)
        self.assertIn("short stocky clean-shaven youth", compiled.positive)
        self.assertIn("tall lean bald beardless porter", compiled.positive)
        self.assertIn("Three unique faces, builds, garments, and poses", compiled.positive)
        self.assertNotIn("identical men standing in a line", compiled.positive)

    def test_minoan_ep06_modern_excavation_replaces_fake_map_and_excavator_machine(self):
        cases = (
            (
                "He hoped the eruption might explain Minoan decline and reveal an Aegean Pompeii",
                "pair",
                2,
                "small tray of pale volcanic ash",
            ),
            (
                "Instead, his team found a city whose warning phase had allowed residents to flee",
                "landscape",
                0,
                "completely empty ash-preserved Akrotiri street",
            ),
        )
        for narration, expected_kind, expected_count, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete, Aegean Sea; "
                    "Culture scope: Minoan civilization, Mycenaean Greece; "
                    "Scene evidence: Source workbook scene: fake Europe map and modern excavator machine; "
                    f"|| Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(expected_action, compiled.positive)
                self.assertNotIn("fake Europe map and modern excavator machine", compiled.positive)

    def test_minoan_ep06_ventris_announcement_uses_radio_not_fake_text_tablet(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete, Aegean Sea; "
            "Culture scope: Minoan civilization, Mycenaean Greece; "
            "Scene evidence: Source workbook scene: a giant stone tablet covered in readable fake Greek; "
            "|| Narration context: In 1952, he announced that Linear B encoded an early form of Greek"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("1952 CE tight two-person radio-studio action", compiled.positive)
        self.assertIn("period black broadcast microphone", compiled.positive)
        self.assertNotIn("giant stone tablet covered in readable fake Greek", compiled.positive)

    def test_minoan_ep06_finale_replaces_fake_text_and_map_scenes(self):
        cases = (
            (
                "Suddenly the takeover was audible in language, not merely visible in pottery and graves",
                "one palm-sized sealed clay tablet edge-on",
            ),
            (
                "Linear A remains unread, preserving the older Minoan voice behind a locked script",
                "exactly three small irregular Minoan clay fragments",
            ),
            (
                "That imbalance lets conquerors speak through records while the preceding administration stays mute",
                "Present-day tight two-person conservation comparison",
            ),
            (
                "It also prevents us from learning what Minoans called themselves, their rulers, or the crisis",
                "one tiny clay fragment kept fully below the frame",
            ),
            (
                "Around 1450 BCE, widespread destruction removed most major palace centers",
                "exactly three separate low plaster-and-mudbrick palace settlements",
            ),
            (
                "That inheritance made the next Bronze Age system richer, larger, and more interconnected",
                "exactly three distinct small low single-decked wooden cargo boats",
            ),
            (
                "It also made the coming collapse spread farther when every palace depended on distant partners",
                "exactly four distinct dockworkers",
            ),
            (
                "Crete's fall was not the end of the crisis; it was an early warning",
                "one ash-covered Cretan quay",
            ),
            (
                "Next, kingdoms from Greece to Anatolia and Syria collapse within a few violent decades",
                "exactly three separate low mudbrick-and-stone settlement clusters",
            ),
            (
                "Desperate letters beg for ships while unidentified raiders strike exposed coasts",
                "one palm-sized clay tablet whose marked face angles fully away",
            ),
            (
                "Egypt calls them Sea Peoples, but invasion is only one part of the disaster",
                "exactly four distinct adults",
            ),
        )
        for narration, expected_action in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete, Aegean Sea; "
                    "Culture scope: Minoan civilization and Mycenaean Greece; "
                    "Scene evidence: Source workbook scene: fake giant map and readable inscription; "
                    "Main subject: a giant Europe map covered in English words; "
                    "Scene: a giant Europe map covered in English words. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertIn(expected_action, compiled.positive)
                self.assertNotIn("a giant Europe map covered in English words", compiled.positive)

    def test_japanese_ep10_victory_keeps_four_distinct_actor_slots(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: a generic row of duplicated deities; "
            "Scene evidence: Source workbook scene: Susanoo wins the ukehi trial; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: その 結果、 優しい 女神 を 産み出した スサノオ が 勝利 しました。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertIn("Triangular victory action across four depths", compiled.positive)
        self.assertIn("foreground-left tall broad male Susanoo", compiled.positive)
        self.assertIn("center midground short bob-haired woman", compiled.positive)
        self.assertIn("far background medium tied-haired woman", compiled.positive)
        self.assertIn("right foreground tall long-haired woman", compiled.positive)
        self.assertIn("fifth person", compiled.negative.casefold())
        self.assertIn("duplicate susanoo", compiled.negative.casefold())
        self.assertNotIn("generic row of duplicated deities", compiled.positive)

    def test_japanese_ep10_defilement_keeps_visible_throw_action(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: Susanoo standing still; "
            "Scene evidence: Source workbook scene: defilement of the sacred hall; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: あろう こと か その 神殿 に、 自身 の 大便 を まき散らした の です。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertIn("one visible dark foul mud-like arc", compiled.positive)
        self.assertIn("airborne arc", compiled.positive)
        self.assertIn("standing portrait", compiled.negative.casefold())
        self.assertNotIn("Susanoo standing still", compiled.positive)

    def test_japanese_ep10_weaving_hall_keeps_four_distinct_workers(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: the same long-haired woman repeated across an empty landscape; "
            "Scene evidence: Source workbook scene: sacred weaving hall workers; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: 彼女 は 忌服屋 と 呼ばれる 神聖 な 建物 で、 神々 の 衣服 を 織らせて いました。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertIn("four adult women occupy four separate depths", compiled.positive)
        self.assertIn("short bob-haired woman", compiled.positive)
        self.assertIn("tall braided woman", compiled.positive)
        self.assertIn("older silver-streaked woman", compiled.positive)
        self.assertIn("long-haired woman", compiled.positive)
        self.assertIn("identical repeated woman", compiled.negative.casefold())
        self.assertNotIn("same long-haired woman repeated across an empty landscape", compiled.positive)

    def test_japanese_ep10_roof_impact_and_hide_evidence_exclude_people_and_live_horses(self):
        cases = (
            (
                "ところが その 平和 な 空間 に、 突然 凄まじい 轟音 が 響き渡り ます。",
                "solid blank clay walls",
                "outdoor landscape",
            ),
            (
                "そして その 穴 から、 想像 を 絶する 恐ろしい 物 を 投げ込み ました。",
                "one featureless closed mass",
                "animal silhouette",
            ),
            (
                "しかも ただ の 死骸 では なく、 生きた まま 皮 を 剥ぎ取られて いました。",
                "one large thin white-and-brown spotted hide sheet",
                "living animal",
            ),
            (
                "さらに 尻尾 の 方 から 逆剥き に する という、 最も 残酷 な 殺し 方 です。",
                "one narrow natural tail tuft",
                "living animal",
            ),
            (
                "天の斑馬 と 呼ばれる 尊い 動物 を、 残酷 に 殺して 投げ入れた の です。",
                "one featureless closed mass",
                "animal shape",
            ),
        )
        for narration, expected_positive, _excluded_shape in cases:
            with self.subTest(narration=narration):
                source = (
                    "Time range: Japanese mythic creation era; "
                    "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
                    "and Takamagahara only as named by each scene; "
                    "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
                    "Main subject: Susanoo and a live running horse beside a doorway figure; "
                    "Scene evidence: Source workbook scene: roof attack aftermath; "
                    "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, "object")
                self.assertIn(expected_positive, compiled.positive)
                self.assertNotIn("a live running horse beside a doorway figure", compiled.positive)

    def test_japanese_ep10_panic_keeps_exactly_four_upright_women_and_empty_floor(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: Susanoo beside two fallen women and four standing duplicates; "
            "Scene evidence: Source workbook scene: panic inside the weaving hall; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: 血だらけ の 死骸 が 降って きた こと で、 機屋 の 中 は パニック に なります。"
        )
        compiled = self.compile(source, model="comfyui-z-image-turbo")
        self.assertEqual(compiled.scene_kind, "group")
        self.assertEqual(compiled.person_count, 4)
        self.assertIn("Exactly four distinct standing women exist", compiled.positive)
        self.assertIn("clean plank floor behind and between them remains fully empty", compiled.positive)
        self.assertNotIn("two fallen women and four standing duplicates", compiled.positive)

    def test_japanese_ep10_weaver_fall_excludes_floating_crossed_weapons(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: one woman under two floating crossed swords; "
            "Scene evidence: Source workbook scene: weaver falls against loom; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: その 際 に 転倒 し、 機織り の 道具 に 身体 を 強く ぶつけて しまい ます。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("strikes her clothed hip against one fixed horizontal timber loom beam", compiled.positive)
        self.assertIn("crossed swords", compiled.negative.casefold())
        self.assertNotIn("woman under two floating crossed swords", compiled.positive)

    def test_japanese_ep10_fatal_aftermath_stays_non_graphic_and_two_person(self):
        source = (
            "Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: graphic exposed injury beside a loom; "
            "Scene evidence: Source workbook scene: fatal weaving accident aftermath; "
            "NARRATION VISUAL ALIGNMENT: match the spoken moment; "
            "Narration context: なんと その 衝撃 で 道具 が 陰部 に 突き刺さり、 命 を 落として しまった の です。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "pair")
        self.assertEqual(compiled.person_count, 2)
        self.assertIn("Non-graphic floor-level aftermath", compiled.positive)
        self.assertIn("one second adult woman kneels at her shoulder", compiled.positive)
        self.assertNotIn("graphic exposed injury beside a loom", compiled.positive)

    def test_minoan_ep06_linear_a_uses_unreadable_small_fragments(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Knossos, Crete; "
            "Main subject: a giant stone inscription with readable letters; "
            "Scene evidence: Source workbook scene: Linear A records; "
            "|| Narration context: Earlier Minoan administrators wrote Linear A, a script still undeciphered today"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("exactly three small irregular Minoan clay tablet fragments", compiled.positive)
        self.assertNotIn("giant stone inscription with readable letters", compiled.positive)

    def test_minoan_ep06_warrior_burial_uses_grave_goods_not_portrait(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete; "
            "Main subject: a living woman on a bed; "
            "Scene evidence: Source workbook scene: mainland-style warrior burial; "
            "|| Narration context: Mainland-style warrior burials and objects appear as the new order settles into Crete"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("top-down archaeological warrior burial", compiled.positive)
        self.assertNotIn("living woman on a bed", compiled.positive)

    def test_minoan_ep06_abandoned_roofs_stay_uninhabited(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Akrotiri, Thera; "
            "Main subject: Pumice and ash burying empty Akrotiri houses floor by floor; "
            "Scene: Pumice and ash burying empty Akrotiri houses floor by floor; "
            "|| Narration context: Hot debris falls across abandoned roofs and begins sealing every room"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("completely abandoned Bronze Age Akrotiri roofs", compiled.positive)
        self.assertIn("zero people", compiled.positive)

    def test_minoan_ep06_dating_gap_uses_unlabeled_stratigraphy(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete; "
            "Main subject: a labeled timeline; Scene: dates and arrows across a volcano; "
            "|| Narration context: That dating problem matters because Crete's palace destructions occur substantially later"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("archaeological stratigraphy close-up", compiled.positive)
        self.assertIn("thick undisturbed brown occupation-soil band", compiled.positive)
        self.assertNotIn("dates and arrows", compiled.positive)

    def test_minoan_ep06_lost_port_uses_quay_evidence_without_ship(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Akrotiri, Thera; "
            "Main subject: a giant Renaissance galleon; Scene: a tall ship in harbor; "
            "|| Narration context: Trade routes lose a major port and perhaps ships, crews, markets, and trusted partners"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIn("three snapped coarse mooring ropes", compiled.positive)
        self.assertIn("crop contains no water, horizon, shore, or boat", compiled.positive)
        self.assertNotIn("tall ship in harbor", compiled.positive)

    def test_minoan_ep06_1450_destruction_uses_crete_panorama_not_europe_map(self):
        source = (
            "Year/period: 1600 BCE to 1450 BCE; Exact place: Crete; "
            "Main subject: map of Europe; Scene: Britain, Italy, and Greece on fire; "
            "|| Narration context: Then, around 1450 BCE, fire and destruction sweep through much of Crete"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "landscape")
        self.assertEqual(compiled.person_count, 0)
        self.assertIn("three separate low plaster-and-mudbrick settlement centers", compiled.positive)
        self.assertNotIn("Britain, Italy, and Greece on fire", compiled.positive)

    def test_ch3_ep10_ritual_recap_replaces_symbolic_scale_with_exact_objects(self):
        source = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: Takamagahara; "
            "Scene: a glowing golden scale balancing a sword and sun emblem; "
            "Narration context: 前回 は、 天上 界 で 行われた 奇妙 な 裁判 の お 話 でした。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "object")
        self.assertIsNone(compiled.person_count)
        self.assertIn("exactly one plain aged-bronze blade", compiled.positive)
        self.assertIn("exactly one short cord of green comma-shaped magatama beads", compiled.positive)
        self.assertIn("no scale, emblem, writing, person, or extra object", compiled.positive)
        self.assertNotIn("glowing golden scale", compiled.positive)

    def test_ch3_ep11_first_batch_locks_remove_stale_amaterasu_and_symbols(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a generic neutral standing portrait with readable symbols; "
        )
        cases = (
            (
                "彼 は 全て の 神々 を 驚かせる、 奇想天外 な 作戦 を 提案 し ます。",
                "group",
                "Omoikane rises and speaks",
            ),
            (
                "太陽 の 女神 アマテラス が 洞窟 に 隠れ、 闇 に 包まれた 世界。",
                "landscape",
                "one real island coastline",
            ),
            (
                "八咫鏡 と 呼ばれる この 鏡 は、 日本 の 三種の神器 の 一つ と なります。",
                "object",
                "exactly one bright pale-gold polished aged-bronze Yata mirror face",
            ),
            (
                "次に 鍛冶屋 の 神様 に 命じて、 太陽 を 模した 巨大 な 鏡 を 作らせ ます。",
                "single",
                "swings one rough stone maul",
            ),
        )
        for narration, scene_kind, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("generic neutral standing portrait", compiled.positive)
                self.assertIn("readable writing", compiled.negative)
                self.assertIn("lightbulb", compiled.negative)

        susanoo = self.compile(
            prefix
            + "Narration context: 前回 は、 暴風 の 神 スサノオ の 凄惨 な 悪行 を お 話 しました。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("complete mature male face", susanoo.positive)
        self.assertIn("female person", susanoo.negative)

        broken_blade = self.compile(
            prefix
            + "Narration context: 暴力 や 武力 では、 閉ざされた 女神 の 心 を 開く こと は できない の です。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("two short dull-brown aged-bronze fragments", broken_blade.positive)
        self.assertIn("modern sword", broken_blade.negative)

        magatama = self.compile(
            prefix
            + "Narration context: 八尺瓊勾玉 と 呼ばれる これ も また、 天皇家 に 伝わる 宝物 です。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly nine separate comma-shaped green jade magatama", magatama.positive)
        self.assertIn("round bead", magatama.negative)

    def test_ch3_ep11_second_batch_locks_use_varied_safe_ritual_staging(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a floating exclamation mark above a generic portrait; "
        )
        cases = (
            (
                "その 木 の 枝 に、 完成 した 鏡 と 勾玉 を 綺麗 に 飾り付け ました。",
                "object",
                "one complete living sakaki branch",
            ),
            (
                "アメノウズメ という、 芸能 と 歓楽 を 司る 女神 が 進み出た の です。",
                "single",
                "Uzume advances with a confident half-smile",
            ),
            (
                "神聖 な 儀式 の ど 真ん中 で 行われた、 衝撃 的 な ストリップ ショー です。",
                "group",
                "non-explicit backlit dance silhouette",
            ),
        )
        for narration, scene_kind, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertEqual(compiled.scene_kind, scene_kind)
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("floating exclamation mark", compiled.positive)
                self.assertIn("exclamation mark", compiled.negative)

        coordinated = self.compile(
            prefix
            + "Narration context: 神々 は 一丸 と なって、 宇宙 の 闇 を 打ち破る 計画 を 進めた の です。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("six distinct adults on empty bare ground", coordinated.positive)
        self.assertIn("dining table", coordinated.negative)

        chanting = self.compile(
            prefix
            + "Narration context: 彼ら は 太陽 の 女神 を 褒め称える ため に、 壮大 な 祝詞 を 読み上げ ました。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("both ritual deities chant with visibly open empty mouths", chanting.positive)
        self.assertIn("hard lower crop ends at both jawlines", chanting.positive)
        self.assertIn("drinking", chanting.negative)
        self.assertIn("hand", chanting.negative)

        open_ground = self.compile(
            prefix
            + "Narration context: 神聖 な 儀式 の ど 真ん中 で 行われた、 衝撃 的 な ストリップ ショー です。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("low empty rocky horizon spanning the full frame", open_ground.positive)
        self.assertIn("timber frame", open_ground.negative)

        stamping = self.compile(
            prefix
            + "Narration context: そして その 桶 の 上 に 飛び乗る と、 激しく 足 を 踏み鳴らし 始め ます。",
            "comfyui-z-image-turbo",
        )
        self.assertIn("exactly two attached bare adult female feet", stamping.positive)
        self.assertIn("second pair of legs", stamping.negative)

    def test_ch3_ep11_third_batch_locks_stage_laughter_cave_and_mirror_sequence(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands and Takamagahara; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a generic standing portrait with floating musical notes and a question mark; "
        )
        cases = (
            (
                "暗闇 の 中 に いた 無数 の 神々 が、 一斉 に どっと 笑い 転げた の です。",
                "distinct adult deities collapse into laughter",
            ),
            (
                "この 凄まじい 歓声 と 笑い声 は、 固く 閉ざされた 洞窟 の 中 に も 届き ました。",
                "dust sifts from its upper seam",
            ),
            (
                "ところが 外 から 聞こえて くる の は、 楽し そう な 音楽 と 凄まじい 笑い声 です。",
                "softly focused celebratory crowd with raised laughing faces",
            ),
            (
                "一体 外 では 何 が 起き て いる の だろう と、 彼女 は 不思議 に 思い 始め ます。",
                "Extreme face-only curiosity close-up",
            ),
            (
                "アマテラス は 隙間 から 外 を 覗き込み、 ウズメ に 向かって 問いかけ ました。",
                "EXTREME COMPLETE-FACE CLOSE-UP BETWEEN TWO ROCK EDGES",
            ),
            (
                "それ を 聞いた アマテラス は、 激しい プライド を 刺激 され ました。",
                "fine feminine jaw",
            ),
            (
                "太陽 の 女神 である 自分 より も、 素晴らしい 神 が いる はず が ない。",
                "STRICT TWO-ELEMENT MACRO",
            ),
            (
                "その 瞬間、 外 で 待ち構えて いた 神々 が 素早く 動きました。",
                "exactly four distinct waiting helpers",
            ),
            (
                "鏡 に 映った の は、 光り輝く アマテラス 自身 の 美しい 顔 でした。",
                "one coherent reflected image of Amaterasu",
            ),
            (
                "その 瞬間、 隠れて いた 神々 が 八咫鏡 を アマテラス の 前 に 突き出し ました。",
                "two hidden attendants emerge from separate low rocks",
            ),
            (
                "彼女 は 隙間 から 外 を 覗き、 なぜ 皆 笑って いる の か と 尋ね ました。",
                "EXTREME FACE-ONLY SEAM CLOSE-UP WITH ZERO BODY",
            ),
            (
                "ウズメ は、 あなた 様 より も 美しい 神 が 現れた から だ と 嘘 を つき ます。",
                "complete face spans the frame from hairline to chin",
            ),
            (
                "プライド を 刺激 された 太陽 神 は、 その 姿 を 見よう と さらに 身 を 乗り出し ます。",
                "STRICT HAND-ACTION MACRO",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("generic standing portrait", compiled.positive)
                self.assertIn("musical note", compiled.negative)
                self.assertIn("question mark", compiled.negative)

    def test_ch3_ep11_fourth_batch_locks_stage_return_regalia_and_judgment(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands and Takamagahara; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: a modern shrine with readable text, a crown, a justice scale, and a map; "
        )
        cases = (
            (
                "アマテラス が 身 を 乗り出した 瞬間、 彼 は 女神 の 手 を ガシッ と 掴み ます。",
                "one large hand closes securely around Amaterasu's forearm",
            ),
            (
                "これ は 結界 の 役割 を 果たし、 もう 二度と 中 に は 戻れ ない という 印 です。",
                "one thick unpainted plant-fiber shimenawa",
            ),
            (
                "それ と 同時に、 地上 の 葦原中国 に も 暖か な 陽差し が 降り注ぎ ました。",
                "one unlabeled river plain",
            ),
            (
                "暗闇 を 徘徊 して いた 恐ろしい 悪霊 たち は、 光 に 焼かれて 消滅 しました。",
                "black smoke wisps breaking apart into ash",
            ),
            (
                "世界 を 滅亡 から 救った の は、 深刻 な 戦い で は なく 笑い と お 祭り でした。",
                "Uzume dances on the wooden tub",
            ),
            (
                "また、 この 時 使われた 八咫鏡 と 八尺瓊勾玉 は 非常に 重要 です。",
                "exactly nine separate thick green comma-shaped magatama",
            ),
            (
                "これら は 後 に、 天皇家 の 証 で ある 三種の神器 と して 受け継がれ ます。",
                "right presents one complete straight leaf-shaped bronze blade",
            ),
            (
                "さらに 結界 として 張られた 注連縄 は、 現在 の 神社 でも 見る ことが できます。",
                "spanning between two rough uncarved stones",
            ),
            (
                "神様 を 呼び寄せる ため に 踊る 神楽 も、 ウズメ の 踊り が ルーツ です。",
                "Wide archaic kagura origin scene",
            ),
            (
                "姉 の アマテラス を 絶望 させ、 機織り の 少女 を 死 に 追いやった スサノオ。",
                "one broken archaic loom and torn white weaving cloth",
            ),
            (
                "世界 の 秩序 を 取り戻した 神々 は、 ついに 彼 へ の 厳正 な 処罰 を 下し ます。",
                "restrained Susanoo kneels alone at center",
            ),
            (
                "これ は 単なる 兄弟 喧嘩 の 結末 では なく、 神話 の 舞台 を 移す 決定 的 な 裁判 と なります。",
                "empty descending mountain path toward the earthly coast",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("modern shrine with readable text", compiled.positive)
                self.assertIn("readable writing", compiled.negative)

    def test_ch3_ep11_fifth_batch_locks_stage_epilogue_exile_and_next_episode(self):
        prefix = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, Silla coast, and Korea Strait; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Main subject: exactly one adult female Amaterasu; "
            "Scene: readable social-media text with a thumbs-up icon, map labels, and a modern katana; "
        )
        cases = (
            (
                "暗闇 に 乗じて 騒いで いた 悪霊 たち は、 太陽 の 光 に 焼かれて 消滅 します。",
                "separate black smoke wisps dissolve into thousands of pale ash particles",
            ),
            (
                "この 時 に 使われた 鏡 や 勾玉 は、 後 の 天皇家 の 三種の神器 と なります。",
                "right presents one complete straight leaf-shaped bronze blade",
            ),
            (
                "注連縄 や 神楽 など、 現代 の 神社 に 繋がる ルーツ が 全て 詰まった 神話。",
                "braided boundary rope spans natural rocks",
            ),
            (
                "ヒゲ と 手足 の 爪 を 剥がれ、 天上 界 から 永遠 に 追放 される という 刑罰。",
                "fingernails are closely trimmed",
            ),
            (
                "皆さん は この アメノウズメ の 破格的 な 踊り について、 どう 感じ ました か。",
                "four distinct mature viewers",
            ),
            (
                "是非 コメント 欄 で、 皆さん の 自由 な ご 意見 を お 聞かせ ください。",
                "four distinct adults take turns speaking and listening",
            ),
            (
                "チーム 一同、 楽しく コメント を 読ま せ て 頂いて おります。",
                "four distinct adult storytellers",
            ),
            (
                "面白い と 感じて 頂け たら、 チャンネル 登録 と 高評価 を お願い します。",
                "polite request gesture",
            ),
            (
                "皆さん の 応援 が、 いつも 動画 制作 の 大きな 励み に なって います。",
                "blank image boards",
            ),
            (
                "ヒゲ と 爪 を 剥がされる という 屈辱 的 な 罰 を 受け、 地上 へ と 降り立ち ます。",
                "shortened uneven beard",
            ),
            (
                "彼 が 落ちて きた の は、 新羅 の 曾尸茂梨 と 呼ばれる 場所 でした。",
                "wild southeastern Korean shoreline",
            ),
            (
                "ここ で 日本 神話 に、 突然 韓半島 の 地名 が 登場 する の です。",
                "exactly one complete archaic wooden boat",
            ),
            (
                "古代 日本 と 韓半島 の 深い 繋がり を 示す、 非常に ミステリアス な 記録。",
                "one closed face-down blank plant-fiber record bundle",
            ),
            (
                "天上界 の 問題児 は、 地上 で 一体 どんな 活躍 を 見せる の でしょう か。",
                "Extreme emotional head-and-shoulders shore portrait",
            ),
            (
                "次回、 スサノオ が 新羅 を 経て ヤマタノオロチ と 激突 する 伝説 に 迫り ます！",
                "exactly eight complete giant serpent heads",
            ),
        )
        for narration, expected in cases:
            with self.subTest(narration=narration):
                compiled = self.compile(
                    prefix + f"Narration context: {narration}",
                    "comfyui-z-image-turbo",
                )
                self.assertIn(expected, compiled.positive)
                self.assertNotIn("readable social-media text", compiled.positive)
                self.assertIn("readable writing", compiled.negative)

    def test_ch3_ep10_rampage_uses_low_angle_field_action(self):
        source = (
            "Global visual world: Time range: Japanese mythic creation era; "
            "Place scope: primordial Japanese islands, the Yomi boundary, misogi riverbanks, "
            "and Takamagahara only as named by each scene; "
            "Culture scope: Kojiki and Nihon Shoki Japanese creation myth; "
            "Year/period: Japanese mythic creation era; Exact place: Takamagahara rice field; "
            "Scene: a generic standing portrait of Susanoo; "
            "Narration context: しかし スサノオ は、 その 田んぼ の 畦 を 荒々しく 壊して まわり ます。"
        )

        compiled = self.compile(source, model="comfyui-z-image-turbo")

        self.assertEqual(compiled.scene_kind, "single")
        self.assertEqual(compiled.person_count, 1)
        self.assertIn("Low-angle full-body action", compiled.positive)
        self.assertIn("drives one bare foot through a packed-earth paddy ridge", compiled.positive)
        self.assertNotIn("generic standing portrait", compiled.positive)

    def test_ch2_bronze_age_ep07_first_batch_repairs_remove_visible_text(self):
        cases = (
            (
                "Ugarit's last king sends a desperate warning: enemy ships have arrived, and his cities burn.",
                "single",
                1,
                "Extreme emotional head-and-shoulders portrait",
            ),
            (
                "For centuries, powerful kingdoms had exchanged gifts, brides, copper, grain, soldiers, and intelligence.",
                "group",
                None,
                "diplomatic foot procession",
            ),
            (
                "Modern scholars call this diplomatic circle the Club of Great Powers.",
                "group",
                None,
                "three culturally distinct mature rulers",
            ),
            (
                "Egyptian pharaohs addressed foreign rulers as brothers when status and advantage required it.",
                "pair",
                2,
                "one undecorated bronze drinking bowl",
            ),
            (
                "Mycenaean palace states ruled parts of mainland Greece through fortified administrative centers.",
                "group",
                None,
                "Wide human-centered Mycenaean citadel court",
            ),
            (
                "Bronze made weapons, tools, armor, vessels, statues, fittings, and elite prestige.",
                "object",
                0,
                "Object-only strict overhead arrangement",
            ),
            (
                "But copper and tin rarely came from the same place, making every palace dependent on trade.",
                "landscape",
                0,
                "Landscape-only wide vulnerable coastal palace and harbor",
            ),
            (
                "That concentration produced extraordinary power during stability and catastrophic paralysis during failure.",
                "landscape",
                0,
                "Landscape-only high oblique view of one rectangular Mycenaean citadel court",
            ),
            (
                "A failed harvest removed the rations needed by workers and soldiers.",
                "group",
                None,
                "irregular rubble-and-mottled-plaster",
            ),
            (
                "Without ships, metalworkers lost ore while armies waited for replacement weapons.",
                "group",
                3,
                "Exactly three adults in one empty harbor smithy",
            ),
            (
                "Once tribute stopped, kings could no longer reward officers whose loyalty protected the throne.",
                "pair",
                2,
                "Tight two-person confrontation in one empty treasury",
            ),
            (
                "Collapse at one major port gave distant partners shortages they never caused.",
                "landscape",
                0,
                "Landscape-only wide coastal depth view",
            ),
            (
                "The Bronze Age world resembled a chain of heavily loaded wagons joined wheel to wheel.",
                "landscape",
                0,
                "STRICT VERTICAL BIRD'S-EYE VIEW",
            ),
            (
                "One broken axle could be repaired; several simultaneous failures stopped the entire convoy.",
                "object",
                0,
                "BROKEN-PARTS-ONLY LOCK",
            ),
            (
                "By the late thirteenth century, those failures begin arriving faster than kingdoms can recover.",
                "landscape",
                0,
                "Landscape-only wide abandoned palace edge",
            ),
            (
                "That imbalance gives rebellion a practical reason beyond abstract resentment.",
                "group",
                None,
                "Dynamic low-angle granary breach",
            ),
            (
                "Letters from the era mention grain shortages and requests for emergency food shipments.",
                "single",
                1,
                "closed unmarked dark leather dispatch pouch",
            ),
        )
        for narration, expected_kind, expected_count, required in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1200 BCE; Exact place: Eastern Mediterranean; "
                    "Culture scope: Ugarit, Hittite Empire, Mycenaean Greece, and New Kingdom Egypt; "
                    "Scene evidence: Source workbook scene: giant readable tablet, inscribed wall, and map labels; "
                    "Main subject: giant readable tablet; Scene: giant readable tablet beside an inscribed wall. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("giant readable tablet", compiled.positive)
                self.assertNotIn("inscribed wall", compiled.positive)
                self.assertIn("readable cuneiform", compiled.negative)

    def test_ch2_bronze_age_ep07_second_batch_repairs_are_textless_scenes(self):
        cases = (
            ("Earthquakes also strike a tectonically violent region filled with heavy stone buildings.", "landscape", 0, "Landscape-only high oblique view"),
            ("Mycenae suffers collapsed structures and crushed bodies around the middle of the thirteenth century.", "group", None, "Wide rescue scene inside collapsed Mycenae"),
            ("Tiryns later endures another destructive earthquake, yet communities rebuild after both events.", "group", None, "Wide active Tiryns rebuilding scene"),
            ("Earthquake alone therefore cannot explain why administrative systems permanently disappear.", "landscape", 0, "Landscape-only deep view"),
            ("Plague, changing warfare, mercenary defection, and internal civil conflict add further pressure.", "group", None, "continuous tense city-gate scene"),
            ("Chariot elites are expensive, specialized, and dependent on horses, roads, armor, and trained crews.", "group", 4, "Wide human-centered chariot preparation"),
            ("Massed foot soldiers with long swords and javelins can exploit broken terrain and confusion.", "group", 6, "Low tracking action with exactly six"),
            ("Palaces built to manage predictable obligations struggle against enemies who refuse conventional campaigns.", "group", None, "High wide continuous view"),
            ("Raiders burn supplies, seize ships, and disappear before a royal army can assemble.", "group", None, "Dynamic wide harbor raid"),
            ("Refugees from one destroyed region then increase pressure on the next surviving coast.", "group", None, "Wide coastal migration"),
            ("Some migrants arrive seeking land; others arrive armed because unarmed families are easily robbed.", "group", None, "Tight human-centered migrant family"),
            ("The same group can be refugees, settlers, mercenaries, pirates, and invaders at different moments.", "group", None, "One continuous shoreline camp"),
            ("That complexity matters when Egyptian texts later label several enemies together.", "group", None, "Wide Egyptian court encounter"),
            ("They were not one nation calling itself the Sea Peoples.", "group", None, "Wide human-centered shoreline gathering"),
            ("The phrase is modern shorthand for names Egyptian records list in several conflicts.", "object", 0, "Object-only strict overhead arrangement"),
            ("Some names appear earlier as raiders, mercenaries, allies, or members of mixed armies.", "group", None, "Wide active mixed harbor force"),
            ("Egyptian pharaoh Ramesses II defeated Sherden raiders, then incorporated captured men into his own guard.", "single", 1, "Extreme regal waist-up portrait"),
            ("Merneptah fought Libyans supported by Ekwesh, Shekelesh, Lukka, Sherden, and Teresh.", "group", None, "Dynamic wide battlefield"),
            ("By Ramesses III's reign, larger movements combine armed columns, ships, carts, women, and children.", "group", None, "High oblique coastal migration"),
            ("Before Egypt faces them, the northern great powers are already coming apart.", "landscape", 0, "Landscape-only high wide view"),
            ("Ugarit receives reports that an enemy fleet of twenty ships has been sighted.", "single", 1, "High watchtower view"),
            ("The warning crosses the sea to Ammurapi, Ugarit's young final king.", "pair", 2, "Tight two-person arrival"),
            ("Ammurapi asks where those ships are now, because every hour changes the threat.", "single", 1, "Tight emotional three-quarter portrait"),
            ("His city has walls, wealth, scribes, workshops, and a palace archive filled with diplomacy.", "group", None, "Wide active Ugarit palace courtyard"),
            ("What it lacks at the decisive moment is the force needed to defend itself.", "single", 1, "Extreme emotional waist-up portrait"),
            ("Ugarit's troops and chariots are away in Hittite territory.", "landscape", 0, "Landscape-only high oblique view"),
            ("Its ships are operating near Lukka lands, leaving the home harbor exposed.", "landscape", 0, "Landscape-only deep coastal view"),
            ("Then hostile vessels reach the coast before those forces can return.", "group", None, "Low water-level landing scene"),
            ("Ammurapi writes that enemy ships arrived and cities were burned.", "single", 1, "Extreme emotional head-and-shoulders portrait"),
            ("He tells Alashiya that his country has been abandoned to itself.", "single", 1, "UGARIT KING IDENTITY LOCK"),
        )
        for narration, expected_kind, expected_count, required in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1200 BCE; Exact place: Eastern Mediterranean; "
                    "Culture scope: Ugarit, Hittite Empire, Mycenaean Greece, and New Kingdom Egypt; "
                    "Scene evidence: giant readable tablet, wall text, annotated map, and covered wagon; "
                    "Main subject: giant readable tablet; Scene: giant readable tablet beside a labeled map. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("giant readable tablet", compiled.positive)
                self.assertNotIn("labeled map", compiled.positive)
                self.assertIn("readable cuneiform", compiled.negative)
                self.assertIn("covered wagon", compiled.negative)
                self.assertIn("modern cargo ship", compiled.negative)

    def test_ch2_bronze_age_ep07_third_batch_repairs_are_textless_scenes(self):
        cases = (
            ("Another report says seven enemy ships inflicted severe damage, a frighteningly small number.", "landscape", 0, "Landscape-only high coastal view"),
            ("Seven crews can devastate exposed towns when the royal army and fleet are absent.", "group", None, "Wide active raid with exactly seven"),
            ("The attackers need not conquer every district; destroying stores and command centers is enough.", "group", 5, "Dynamic single-courtyard scene"),
            ("Ugarit's people retreat through streets built for commerce, not a final urban battle.", "group", None, "Low tracking view down one narrow Ugarit market street"),
            ("Fire moves from warehouses into houses while smoke blocks routes toward the inland road.", "landscape", 0, "Landscape-only low street view"),
            ("Ammurapi seeks help from Carchemish, the Hittite center that still has troops.", "pair", 2, "Tight two-person plea"),
            ("Carchemish sends assistance, but the soldiers arrive after Ugarit has already been sacked.", "group", 3, "Low arrival scene with exactly three"),
            ("The last diplomatic network functions perfectly enough to deliver news of its own failure.", "group", 3, "continuous relay-road scene"),
            ("Later tablets report threshing floors plundered and vineyards destroyed.", "landscape", 0, "Landscape-only wide agricultural devastation"),
            ("Without grain, vines, harbor, and palace, rebuilding becomes more than replacing walls.", "landscape", 0, "Landscape-only high wide view"),
            ("Ugarit never returns as the international port that wrote those final letters.", "landscape", 0, "Landscape-only very wide view"),
            ("The attackers' exact identity remains unknown despite the evidence of assault from the sea.", "object", 0, "Object-only strict overhead evidence scene"),
            ("Calling them Sea Peoples describes the wider crisis, not a solved criminal case.", "group", None, "Wide human-centered coastal crisis"),
            ("Northward, the Hittite Empire is already weakened by famine, plague, and civil war.", "group", None, "continuous Hittite capital street"),
            ("Its vassals strain, supply routes fail, and the capital's authority fragments.", "landscape", 0, "Landscape-only deep Anatolian route"),
            ("Suppiluliuma II, the last known Hittite king, fights naval actions near Cyprus.", "group", 5, "Dynamic five-person naval action"),
            ("Hittite power has reached the sea, but victory there cannot repair the empire behind him.", "single", 1, "Tight emotional three-quarter portrait"),
            ("Hattusa is eventually abandoned and burned during the wider period of breakdown.", "landscape", 0, "Landscape-only high oblique view"),
            ("The burning does not necessarily mark a victorious enemy storming occupied walls.", "landscape", 0, "Landscape-only wide view"),
            ("That distinction matters because later maps exaggerate some destructions and simplify others.", "pair", 2, "Present-day field archaeology pair"),
            ("What is certain is that the central Hittite state ceases functioning.", "landscape", 0, "Landscape-only deep view into Hattusa"),
            ("Smaller Syro-Hittite kingdoms survive pieces of its language, titles, and political tradition.", "group", 3, "Tight three-ruler meeting"),
            ("Across the Aegean, Mycenaean palaces face their own sequence of attack and collapse.", "group", None, "Wide dynamic Mycenaean citadel crisis"),
            ("Thebes suffers repeated sackings before fire ends its palace administration.", "group", None, "Wide Thebes palace court"),
            ("Pylos prepares coastal watchers and defensive deployments recorded on clay tablets.", "group", 4, "High coastal-defense view"),
            ("Those tablets reveal officials reacting to danger, though they never name the final attacker.", "group", 4, "Wide active Pylos command courtyard"),
            ("The palace burns so intensely that its temporary records bake into permanent testimony.", "landscape", 0, "Landscape-only ground-level interior"),
            ("Mycenae and Tiryns endure earthquakes, rebuilding, later destruction, and shrinking political reach.", "landscape", 0, "Landscape-only high oblique view"),
            ("No single synchronized invasion accounts cleanly for every mainland sequence.", "landscape", 0, "Landscape-only very wide natural coastal depth view"),
            ("Still, the palace system disappears, writing vanishes, and populations move or decline.", "group", None, "Wide final migration scene"),
        )
        for narration, expected_kind, expected_count, required in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1200 BCE; Exact place: Eastern Mediterranean; "
                    "Culture scope: Ugarit, Hittite Empire, Mycenaean Greece, and New Kingdom Egypt; "
                    "Scene evidence: giant readable tablet, wall text, annotated map, and covered wagon; "
                    "Main subject: giant readable tablet; Scene: giant readable tablet beside a labeled map. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("giant readable tablet", compiled.positive)
                self.assertNotIn("labeled map", compiled.positive)
                self.assertIn("readable cuneiform", compiled.negative)
                self.assertIn("covered wagon", compiled.negative)
                self.assertIn("modern cargo ship", compiled.negative)

    def test_ch2_bronze_age_ep07_fourth_batch_repairs_are_textless_scenes(self):
        cases = (
            ("The collapse destroys institutions more consistently than it destroys every settlement.", "landscape", 0, "Landscape-only high oblique view"),
            ("Some cities burn, others contract, and several famous destruction claims now look overstated.", "landscape", 0, "Landscape-only very wide continuous coastline"),
            ("Cyprus also changes violently, yet several sites show continuity instead of total annihilation.", "group", None, "Wide active Cypriot coastal town"),
            ("Maa-Palaeokastro shows clearer evidence of attack, but archaeologists cannot identify its attackers.", "pair", 2, "Present-day archaeology pair"),
            ("The evidence demands a mosaic of local disasters inside one regional transformation.", "landscape", 0, "Landscape-only very wide natural coastal depth view"),
            ("Now the moving groups enter Egyptian records under names still difficult to locate.", "group", None, "Wide Egyptian frontier encounter"),
            ("Peleset are commonly connected with later Philistines settled along the southern Levantine coast.", "group", 5, "Wide settlement scene"),
            ("Early ancestry and pottery suggest some newcomers arrived from an Aegean-related population.", "object", 0, "Object-only strict overhead arrangement"),
            ("They rapidly intermarried with local people, creating communities neither purely foreign nor unchanged.", "group", 5, "Tight domestic courtyard scene"),
            ("Sherden can serve as raiders, Egyptian soldiers, captured enemies, and later settlers.", "group", 4, "continuous harbor scene"),
            ("Their proposed connection with Sardinia remains debated rather than securely demonstrated.", "pair", 2, "Present-day archaeology pair"),
            ("Denyen are sometimes linked to Greek Danaans or Anatolian Danuna, without certainty.", "group", 5, "Wide ambiguous Denyen coastal camp"),
            ("Tjeker origins are equally uncertain, despite their later presence on the Levantine coast.", "group", 5, "Wide settled Levantine coast"),
            ("Weshesh appear so sparsely that even their visual identity remains unknown.", "landscape", 0, "Landscape-only quiet abandoned shoreline camp"),
            ("Lukka are better known as mobile raiders and rebels from southwestern Anatolia.", "group", 6, "Dynamic rocky-coast action"),
            ("These differences make a single ethnic portrait misleading from the beginning.", "group", None, "Wide human-centered shoreline gathering"),
            ("Medinet Habu even shows women and children traveling in ox carts with one column.", "group", None, "STRICT VERTICAL BIRD'S-EYE VIEW"),
            ("That image suggests settlement movement, although one scene cannot define every group.", "group", 5, "STRICT VERTICAL BIRD'S-EYE VIEW"),
            ("Some leaders may command pirate bands; others protect communities escaping failed homelands.", "group", 6, "continuous coastal scene"),
            ("By the time they approach Egypt, survival and conquest have become impossible to separate.", "group", None, "Wide advancing migrant column"),
            ("Ramesses III meets the landward column first near Djahy on Egypt's northeastern frontier.", "group", None, "High wide land battle near Djahy"),
            ("The precise battlefield remains debated, probably somewhere in the southern Levant or northwestern Sinai.", "pair", 2, "Present-day field pair"),
            ("Egyptian chariots maneuver against warriors accompanied by carts and household movement.", "landscape", 0, "TRACKS-ONLY STRICT OVERHEAD BATTLEFIELD"),
            ("Ramesses claims victory on land, stopping the column before it reaches the Nile heartland.", "single", 1, "Extreme regal waist-up portrait"),
            ("The fleet remains, and Egypt prepares a more carefully engineered naval trap.", "landscape", 0, "Landscape-only high oblique view"),
            ("Ramesses turns a Nile mouth into what his inscription calls a strong wall.", "landscape", 0, "Landscape-only very high view"),
            ("Ranks of archers take positions along both banks among reeds and prepared ground.", "group", 6, "Low bank-level view"),
            ("Egyptian ships wait within the channels, where local knowledge neutralizes open-sea maneuvering.", "landscape", 0, "Landscape-only deep channel view"),
            ("The enemy fleet enters the river mouth expecting access, landing, or direct engagement.", "landscape", 0, "Landscape-only high water view"),
            ("Once their vessels reach range, Ramesses signals the shore archers to fire.", "single", 1, "Extreme commanding waist-up portrait"),
        )
        for narration, expected_kind, expected_count, required in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1200 BCE; Exact place: Eastern Mediterranean; "
                    "Culture scope: Ugarit, Hittite Empire, Mycenaean Greece, and New Kingdom Egypt; "
                    "Scene evidence: giant readable tablet, wall text, annotated map, and covered wagon; "
                    "Main subject: giant readable tablet; Scene: giant readable tablet beside a labeled map. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("giant readable tablet", compiled.positive)
                self.assertNotIn("labeled map", compiled.positive)
                self.assertIn("readable cuneiform", compiled.negative)
                self.assertIn("covered wagon", compiled.negative)
                self.assertIn("modern cargo ship", compiled.negative)

    def test_ch2_bronze_age_ep07_fifth_batch_repairs_are_textless_scenes(self):
        cases = (
            ("Arrows strike crowded decks where shields cannot cover sailors, rowers, warriors, and rigging together.", "group", None, "Dynamic close naval battle"),
            ("Enemy ships recoil from the banks, only to find Egyptian vessels closing behind them.", "group", None, "High oblique river battle"),
            ("The river has become a corridor with missiles on both sides and warships at the exit.", "group", 6, "High oblique battle view"),
            ("Egyptian archers shoot from their own decks while marines grapple the nearest hulls.", "group", 6, "Low water-level close combat"),
            ("Rigging tangles, oars snap, and packed vessels collide before crews can regain formation.", "landscape", 0, "Landscape-only tight water-level view"),
            ("One enemy ship overturns, spilling armored men into water too crowded for swimming.", "group", 6, "Dynamic wide river disaster"),
            ("Others are dragged toward shore, where soldiers seize survivors emerging beneath arrow fire.", "group", 6, "Low muddy-bank capture scene"),
            ("The Medinet Habu relief shows the northern fleet breaking apart under combined pressure.", "landscape", 0, "Landscape-only very high actual-battle view"),
            ("Ramesses appears enormous above the action, the pharaoh visually controlling every arrow and ship.", "single", 1, "Extreme low-angle propaganda-style portrait"),
            ("That scale is royal propaganda, not a literal view of his position during combat.", "pair", 2, "Present-day archaeology pair"),
            ("The victorious monument remains our fullest source, so its boasts require caution.", "pair", 2, "Present-day archaeology pair"),
            ("Its enemy losses and Egyptian perfection cannot be accepted without independent confirmation.", "pair", 2, "Present-day field pair"),
            ("But the relief's ship details confirm a fierce naval encounter with archers and close combat.", "group", 6, "Tight six-person naval reconstruction"),
            ("Egypt wins, captures survivors, and prevents the migrating coalition from conquering the Nile state.", "group", 6, "Wide aftermath on the Nile bank"),
            ("Some captured groups are later settled or absorbed within Egyptian-controlled territories.", "group", 5, "Wide farming settlement"),
            ("Ramesses saves Egypt from immediate destruction, but he does not restore the old international world.", "single", 1, "Tight reflective waist-up portrait"),
            ("Trade contracts, tribute routes, and diplomatic brotherhoods cannot be rebuilt by battlefield victory.", "landscape", 0, "Landscape-only deep view"),
            ("Egypt survives weaker, poorer, and increasingly unable to control its former empire.", "group", 3, "Wide Egyptian garrison court"),
            ("Later in Ramesses's reign, unpaid tomb workers stage history's earliest recorded labor strike.", "group", 6, "Wide Deir el-Medina work stoppage"),
            ("Even the victorious kingdom cannot reliably feed specialized workers serving royal eternity.", "group", 4, "Tight ration crisis"),
            ("The Sea Peoples were therefore attackers, migrants, symptoms, and accelerants, not one sufficient cause.", "group", None, "continuous coastal crisis"),
            ("The collapse came from interacting failures that transformed every local crisis into regional danger.", "landscape", 0, "Landscape-only very wide continuous terrain"),
            ("Cities did not all burn, peoples did not vanish, and new societies formed from survivors.", "group", 6, "Wide hopeful rebuilding scene"),
            ("Iron Age Phoenicians, Philistines, Greeks, Arameans, and Syro-Hittite states inherit the wreckage.", "group", None, "Wide early Iron Age port market"),
            ("The Bronze Age ends not with silence, but with displaced people building unfamiliar futures.", "group", 6, "Wide sunrise settlement scene"),
            ("Next, later poets turn Bronze Age ruins into a ten-year war for one woman.", "single", 1, "Tight three-quarter portrait"),
            ("Achilles will choose glory over life, while Hector fights knowing his city may fall.", "pair", 2, "Tight emotional two-person portrait"),
            ("We will separate Homer's immortal combat from the archaeology beneath Hisarlik.", "pair", 2, "Present-day archaeology pair"),
            ("Subscribe before the Bronze Age collapse becomes the legend of the Trojan War.", "landscape", 0, "Landscape-only cinematic dawn"),
            ("And like this episode if the Delta battle finally made the collapse feel real.", "single", 1, "Tight reflective waist-up portrait"),
        )
        for narration, expected_kind, expected_count, required in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 1200 BCE; Exact place: Eastern Mediterranean; "
                    "Culture scope: Ugarit, Hittite Empire, Mycenaean Greece, and New Kingdom Egypt; "
                    "Scene evidence: giant readable tablet, wall text, annotated map, and covered wagon; "
                    "Main subject: giant readable tablet; Scene: giant readable tablet beside a labeled map. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("giant readable tablet", compiled.positive)
                self.assertNotIn("labeled map", compiled.positive)
                self.assertIn("readable cuneiform", compiled.negative)
                self.assertIn("covered wagon", compiled.negative)
                self.assertIn("modern cargo ship", compiled.negative)

    def test_baekje_ep07_domi_first_batch_uses_early_baekje_scene_locks(self):
        cases = (
            (
                "왕은 평민의 아내를 차지하려고 남편과 잔인한 내기를 벌였습니다.",
                "group",
                None,
                "Low canted hook shot",
            ),
            (
                "이 이야기는 삼국사기에 실린 백제 도미 부인 설화입니다.",
                "group",
                None,
                "oral-memory scene",
            ),
            (
                "도미는 자신의 아내가 죽음을 당해도 마음을 바꾸지 않을 것이라고 답합니다.",
                "single",
                1,
                "Emotion-first chest-up close-up",
            ),
            (
                "밤에 도미의 집으로 보내 왕이 찾아온 것처럼 꾸미게 합니다.",
                "group",
                None,
                "Low moonlit tracking shot",
            ),
            (
                "하지만 도미 부인은 그 명령을 그대로 받아들이지 않았습니다.",
                "pair",
                2,
                "Emotion-first over-the-shoulder confrontation",
            ),
            (
                "설화는 하늘이 억울한 사람을 도왔다는 방식으로 빈칸을 채웁니다.",
                "scene",
                1,
                "ordinary shaft of dawn light",
            ),
            (
                "산산의 정확한 위치와 이동 경로는 확정하기 어렵지만,",
                "scene",
                2,
                "three natural mountain channels",
            ),
            (
                "아무도 몰지 않는 배 한 척이 그녀 앞에 나타났다고 전합니다.",
                "object",
                0,
                "OBJECT-ONLY MIRACLE ARRIVAL",
            ),
        )
        for offset, (narration, expected_kind, expected_count, required) in enumerate(cases, 10):
            with self.subTest(narration=narration):
                source = (
                    "Year/period: Baekje period, date unspecified in the Domi legend recorded in the Samguk Sagi; "
                    "Exact place: the Han River basin and the traditional home region of Domi and his wife; "
                    "Culture scope: Baekje; Material culture: generic historical material; "
                    f"Scene evidence: Source workbook row 07-{offset:03d} anchors this scene to Baekje; "
                    "Scene: generic guarded courtyard with witnesses and a tiled palace. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-flux2-klein-9b")
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertIn("early Hanseong Baekje", compiled.positive)
                self.assertNotIn("generic guarded courtyard", compiled.positive)
                for forbidden in (
                    "katana",
                    "ornate tiled roof",
                    "signboard",
                    "speech bubble",
                    "readable writing",
                ):
                    self.assertIn(forbidden, compiled.negative)
                if narration.startswith("아무도 몰지 않는 배"):
                    self.assertIn("HARD UNINHABITED RIVER LOCK", compiled.positive)
                    self.assertIn("house", compiled.negative)
                    self.assertNotIn("every visible building", compiled.positive)

    def test_baekje_ep08_hanseong_fall_narrations_replace_generic_workbook_scenes(self):
        cases = (
            ("개로왕은 북위에 고구려를 함께 공격하자는 군사 지원 요청을 보냈습니다.", "pair", 2, "two-person dispatch action"),
            ("국서에는 고구려의 팽창이 북위에도 위협이 된다는 논리가 담겼고,", "pair", 2, "diplomatic reading reaction"),
            ("백제와 북위가 협공하면 승산이 있다는 설득도 이어졌습니다.", "group", 3, "three-person persuasion scene"),
            ("북위의 힘으로 고구려 병력을 북쪽에 묶고 한강의 압박을 줄이려는 전략이었죠.", "group", 4, "strategy council"),
            ("하지만 당시 북위는 남쪽의 송과 맞서며 큰 전선을 관리하고 있었고,", "group", None, "Northern Wei cavalry columns"),
            ("요동까지 장악한 고구려를 새 적으로 돌릴 이유가 크지 않았습니다.", "pair", 2, "two-person refusal scene"),
            ("북위는 백제의 요청에 실질적인 군사 행동으로 응답하지 않았고,", "group", 3, "closed Pingcheng cavalry yard"),
            ("개로왕의 가장 대담한 외교 승부수는 지원군 한 명 없이 끝납니다.", "single", 1, "solitary aftermath portrait"),
            ("국서가 장수왕의 침공 명분이 되었다고 단순하게 잇기도 하지만,", "object", 0, "archaeological caution still life"),
            ("고구려의 남진은 그 편지 이전부터 오랫동안 준비된 정책이었습니다.", "group", None, "Goguryeo mountain fort"),
            ("다만 백제가 북위와 손잡으려 한 사실은 장수왕에게 적대 의도를 분명히 보여 줬고,", "pair", 2, "intelligence report"),
            ("두 나라 사이에 타협할 공간은 더욱 줄어들었습니다.", "pair", 2, "walk away in opposite directions"),
            ("개로왕은 남쪽의 신라와 맺은 동맹도 유지하며 또 다른 구원로를 남겼지만,", "pair", 2, "alliance renewal"),
            ("전쟁이 시작되면 먼 동맹군이 수도보다 빨리 움직일 수 있을지는 알 수 없었습니다.", "group", None, "empty southeastern road"),
            ("고구려는 외교의 답을 기다리지 않고 군사 삼만 명을 남쪽으로 보냅니다.", "group", None, "mountain pass"),
            ("사백칠십오년 가을, 장수왕은 병력 삼만 명을 동원해 백제를 공격합니다.", "group", None, "King Jangsu"),
            ("평양에서 남하한 고구려군은 한강 북쪽의 방어 거점을 차례로 압박했고,", "group", None, "River-level siege approach"),
            ("한성의 토성과 목책은 대규모 공세를 버텨야 했습니다.", "group", None, "rammed-earth embankment"),
            ("개로왕은 왕자 여도를 신라로 보내 구원병을 요청했으며,", "pair", 2, "Prince Yeodo"),
            ("나제동맹에 따라 신라는 병력 만 명을 보내기로 합니다.", "group", None, "Silla packed-earth mustering yard"),
            ("하지만 왕자가 군사를 데리고 돌아오기 전에 수도의 시간이 먼저 끝나고 있었죠.", "group", None, "damaged rammed-earth wall"),
            ("고구려군이 불과 칠 일 만에 주요 방어선을 무너뜨렸다는 기록 뒤로,", "group", None, "broken sharpened palisade stakes"),
            ("북성과 남성으로 나뉜 한성의 왕도는 직접 공격을 받습니다.", "landscape", None, "two separated low Hanseong earthwork enclosures"),
            ("성안에서는 왕족 중심의 지휘와 밀려난 귀족 세력이 하나로 움직여야 했지만,", "group", 5, "five-person emergency council"),
            ("오랫동안 쌓인 불신은 위기에서 전투력만큼 치명적인 약점이 됐습니다.", "pair", 2, "two-person command failure"),
            ("도림의 공작이 있었다 해도 문을 연 것은 한 사람의 속임수만이 아니었고,", "group", 4, "Dorim stands small and secondary"),
            ("재정 소모와 내부 분열, 고구려의 우세한 병력이 동시에 성벽을 눌렀습니다.", "group", None, "empty supply baskets"),
            ("개로왕은 수도를 끝까지 지키기 어려워지자 탈출을 시도했고,", "group", 3, "escape attempt"),
            ("한강과 아차산 사이의 길에서 왕의 운명은 백제 출신 두 사람과 마주칩니다.", "group", 3, "Jaejeunggeollu, and Goimannyeon"),
            ("그들은 고구려군의 선봉에 선 재증걸루와 고이만년이었습니다.", "pair", 2, "two-person Goguryeo vanguard portrait"),
        )
        for offset, (narration, expected_kind, expected_count, required) in enumerate(cases, 70):
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 475 AD; Exact place: Hanseong, the Han River basin; "
                    "Culture scope: Baekje and Goguryeo; Material culture: generic Northeast Asian costume; "
                    f"Scene evidence: Source workbook row 08-{offset:03d} anchors this scene to 475 AD, "
                    "Baekje and Goguryeo, and Hanseong; Scene: generic Chinese imperial courtyard where "
                    "envoys exchange one sealed object while opposing formations lock into one clash. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-flux2-klein-9b")
                self.assertIn("narration_visual_alignment=on", compiled.diagnostics)
                self.assertEqual(compiled.scene_kind, expected_kind)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertIn(required, compiled.positive)
                self.assertNotIn("generic Chinese imperial courtyard", compiled.positive)
                self.assertNotIn("Opposing formations lock into one clash", compiled.positive)
                for forbidden in (
                    "Ming dynasty robe",
                    "Qing dynasty robe",
                    "Joseon samo",
                    "samurai",
                    "pseudo-writing",
                    "signboard",
                ):
                    self.assertIn(forbidden, compiled.negative)

    def test_baekje_ep08_polity_specific_clothing_and_architecture_are_frontloaded(self):
        cases = (
            (
                70,
                "개로왕은 북위에 고구려를 함께 공격하자는 군사 지원 요청을 보냈습니다.",
                ("broad-sleeved deep-purple robe", "black silk cap", "small gold flower"),
            ),
            (
                74,
                "하지만 당시 북위는 남쪽의 송과 맞서며 큰 전선을 관리하고 있었고,",
                ("Northern Wei Tuoba Xianbei cavalry", "Liu Song southern infantry", "visibly separated"),
            ),
            (
                82,
                "개로왕은 남쪽의 신라와 맺은 동맹도 유지하며 또 다른 구원로를 남겼지만,",
                ("fifth-century Silla material", "gilt-bronze wing or branch ornament", "birch-bark cowl cap"),
            ),
            (
                87,
                "한성의 토성과 목책은 대규모 공세를 버텨야 했습니다.",
                ("low rammed-earth walls", "sharpened timber palisades", "Goguryeo tomb-mural dress"),
            ),
            (
                98,
                "한강과 아차산 사이의 길에서 왕의 운명은 백제 출신 두 사람과 마주칩니다.",
                ("exactly three adult men total", "left-fastening jackets", "Acha Mountain"),
            ),
            (
                99,
                "그들은 고구려군의 선봉에 선 재증걸루와 고이만년이었습니다.",
                ("exactly two adult men total", "tomb-mural dress", "zero king"),
            ),
        )
        for row, narration, expected_terms in cases:
            with self.subTest(narration=narration):
                source = (
                    "Year/period: 475 AD; Exact place: Hanseong, the Han River basin; "
                    "Culture scope: Baekje and Goguryeo; Material culture: generic Northeast Asian costume; "
                    f"Scene evidence: Source workbook row 08-{row:03d} anchors this scene to 475 AD, "
                    "Baekje and Goguryeo, and Hanseong; Scene: generic tiled Chinese court. || "
                    f"Narration context: {narration}"
                )
                compiled = self.compile(source, model="comfyui-flux2-klein-9b")
                for expected in expected_terms:
                    self.assertIn(expected, compiled.positive)
                if row in {70, 87, 98, 99}:
                    self.assertIn("ceramic tiled palace roof", compiled.negative)
                self.assertIn("generic Chinese imperial court", compiled.negative)

    def test_z_image_uninhabited_environment_uses_empty_landscape_style(self):
        styled = _apply_longtube_dark_manhwa_style(
            "Visible action: Extreme wide environment-only establishing view across bare rock, "
            "gray water, and fog. Primary subject: the empty coastline itself; environment-only "
            "uninhabited natural landscape. Era/period: 346-375 AD. Exact place: Yellow Sea coast.",
            model_id="comfyui-z-image-turbo",
        )

        self.assertIn("HISTORICAL MANHWA LANDSCAPE STYLE LOCK", styled)
        self.assertIn("environment remains completely unoccupied", styled)
        self.assertNotIn("Adult faces are weathered", styled)

    def test_ch2_trojan_ep08_failed_scene_repairs_replace_ambiguous_workbook_actions(self):
        cases = (
            (
                "The Greek commander humiliates his greatest warrior, and Troy nearly wins because of it.",
                "exactly three adults exist",
                "Agamemnon at left grips only the edge of Briseis's plain dark-red wool cloak",
                3,
            ),
            (
                "Then Hector's elderly father enters the killer's tent alone and kisses his hands.",
                "exactly two adult men exist",
                "Elderly King Priam",
                2,
            ),
            (
                "Other Hittite texts mention Ahhiyawa, commonly connected with Mycenaean Greek power across the sea.",
                "one bareheaded Hittite scribe",
                "one palm-sized wet clay tablet",
                1,
            ),
            (
                "That evidence makes conflict plausible, but it does not confirm Homer's ten-year siege.",
                "Present-day archaeological uncertainty still life",
                "no battle reconstruction appears",
                0,
            ),
            (
                "Homer does not narrate the whole conflict or even the fall of Troy.",
                "Troy remains intact and quiet",
                "closed gates and an empty battlefield",
                1,
            ),
            (
                "Paris is a Trojan prince once raised as a shepherd because prophecy marked him dangerous.",
                "exactly one young adult man Paris",
                "among six sheep",
                1,
            ),
            (
                "Three goddesses choose him to judge which of them deserves a golden apple.",
                "exactly four adults and no others",
                "three visually distinct goddesses",
                4,
            ),
            (
                "Hera offers imperial power, and Athena promises wisdom with unmatched skill in battle.",
                "exactly three adults and no others",
                "Hera and Athena are separate adult women",
                3,
            ),
            (
                "Aphrodite offers Helen, the most beautiful woman alive, although Helen already has a husband.",
                "exactly four adults and no others",
                "Helen and Menelaus stand close together as husband and wife",
                4,
            ),
            (
                "Paris chooses Aphrodite, gaining desire while making enemies of power and war.",
                "exactly four adults and no others",
                "Hera is an adult woman at far right",
                4,
            ),
            (
                "Menelaus became Helen's husband and king of Sparta, protected by that dangerous promise.",
                "exactly four adults and no others",
                "crowned Menelaus and crowned Helen",
                4,
            ),
            (
                "Whether myth frames her choice as love, divine compulsion, elopement, or abduction varies.",
                "exactly one adult woman Helen",
                "Her uncertain posture carries all disputed interpretations",
                1,
            ),
            (
                "Achilles's mother hides him among women on Skyros to prevent his foretold death.",
                "exactly two adults and no others",
                "His entire body from neck to feet is covered",
                2,
            ),
            (
                "Odysseus lays out jewelry and weapons, then sounds an alarm among the court.",
                "exactly four adults and no others",
                "Disguised Achilles at center-right reaches directly for the spear",
                4,
            ),
            (
                "Versions differ over whether she dies, escapes, or is replaced by an animal.",
                "exactly two adults and exactly one living animal",
                "Exactly one living deer steps from mist at far left",
                2,
            ),
            (
                "Every version leaves Agamemnon willing to trade family for command and expedition.",
                "exactly two adults and no others",
                "turning his stern face and torso away from his daughter Iphigenia",
                2,
            ),
            (
                "Briseis, a captured woman from Lyrnessus, is awarded to Achilles as a prize.",
                "exactly two adults and no others",
                "Briseis stands at center-left",
                2,
            ),
            (
                "Chryseis is captured elsewhere and assigned to Agamemnon, reinforcing his superior rank.",
                "exactly three adults and no others",
                "Chryseis stands at center",
                3,
            ),
            (
                "These women possess names and grief, yet the army treats them as movable status.",
                "exactly four adults and no others",
                "Briseis and Chryseis stand together at center",
                4,
            ),
            (
                "That system finally turns the coalition's strongest men against each other.",
                "exactly four adults and no others",
                "furious eye contact and separate clenched fists",
                4,
            ),
            (
                "Apollo answers with plague, firing invisible arrows through animals and soldiers.",
                "exactly three adult soldiers and no others",
                "Three long black arrow-shaped shadows cross the dusty ground",
                3,
            ),
            (
                "He knows the city may fall, but shame will not let him abandon the front.",
                "exactly one adult man Hector and no others",
                "one plain uncarved rectangular stone lintel",
                1,
            ),
            (
                "Hector sets fire to Protesilaus's ship, the same warrior he killed at the landing.",
                "exactly one adult man Hector and no others",
                "presses one flaming wooden torch directly against black pitch cloth",
                1,
            ),
            (
                "Achilles still refuses, but allows Patroclus to wear his terrifying armor.",
                "exactly two adult men and no others",
                "fasten the shoulder strap of his distinctive bronze cuirass onto bareheaded Patroclus",
                2,
            ),
            (
                "News reaches Achilles, and his revenge collapses instantly into grief.",
                "exactly two adult men and no others",
                "Achilles has collapsed to both knees",
                2,
            ),
            (
                "He covers himself in ash and cries so violently that Thetis hears beneath the sea.",
                "exactly two adults and no others",
                "His mother Thetis is an adult woman at right",
                2,
            ),
            (
                "He reconciles with Agamemnon because killing Hector matters more than the original insult.",
                "exactly three adults and no others",
                "Briseis stands between them",
                3,
            ),
            (
                "Hephaestus forges new armor, including a shield displaying an entire human world.",
                "exactly one adult man Hephaestus and no others",
                "one glowing round bronze shield lying flat on a black stone anvil",
                1,
            ),
            (
                "Hector stays outside, trapped between duty, shame, and the man coming to kill him.",
                "exactly two adult men and no others",
                "Two massive solid door leaves touch at the center seam",
                2,
            ),
            (
                "Andromache hears the cries, reaches the battlement, and sees her future disappear.",
                "exactly one adult woman Andromache and no others",
                "Her tear-streaked shocked face looks downward beyond the frame",
                1,
            ),
            (
                "Then Priam leaves Troy at night carrying ransom for his son's remains.",
                "Deep moonlit night departure with exactly one adult man and no others",
                "sealed cloth bundles, plain bronze bowls, and one gold cup",
                1,
            ),
            (
                "Hermes guides the old king through Greek sentries and into Achilles's shelter.",
                "exactly two adult men and no others",
                "Young Hermes at left wears a plain travel cloak",
                2,
            ),
            (
                "He asks Achilles to remember his own aging father waiting far away.",
                "exactly two adult men and no others",
                "Elderly white-bearded Priam kneels at left",
                2,
            ),
            (
                "Achilles returns the corpse and grants time for Troy to conduct the funeral.",
                "exactly two living adult men and no others",
                "low two-wheeled bier",
                2,
            ),
            (
                "The arrow and vulnerable heel dominate later tradition more than Homer's own account.",
                "only his right lower calf, ankle, heel, and complete foot appear",
                "A single short bronze projectile",
                1,
            ),
            (
                "Odysseus eventually designs the wooden horse that transforms absence into infiltration.",
                "exactly three adult men and no others",
                "one enormous lifeless wooden horse sculpture",
                3,
            ),
            (
                "The Greeks burn their camp, sail away visibly, and hide chosen warriors inside the structure.",
                "Object-only dusk deception tableau with zero visible people",
                "recognizable traditional Trojan wooden horse sculpture",
                0,
            ),
            (
                "Trojans debate burning, breaking, or dedicating the object, then drag it through the gate.",
                "Exactly four adult Trojans and no others",
                "one enormous lifeless wooden horse sculpture",
                4,
            ),
            (
                "At night, the hidden Greeks emerge and signal the returning fleet.",
                "exactly one adult Greek man and no others",
                "One black rectangular hatch opens low in the belly",
                1,
            ),
            (
                "Hector's infant Astyanax is thrown from the walls to prevent future revenge.",
                "exactly two adults and one infant",
                "exactly one tiny swaddled infant horizontally across both forearms",
                3,
            ),
            (
                "Frank Calvert identified Hisarlik's promise before Heinrich Schliemann launched famous excavations there.",
                "exactly two adult European men and no others",
                "dark Victorian frock coat",
                2,
            ),
            (
                "He misidentified Troy II as Priam's city, although it predated any plausible war by centuries.",
                "exactly one adult European man Heinrich Schliemann and no others",
                "dark Victorian frock coat",
                1,
            ),
            (
                "A historical conflict may lie beneath the epic, but its heroes remain beyond proof.",
                "plain black velvet fills every edge",
                "unpainted raw matte-brown rectangular Hittite clay slab",
                0,
            ),
            (
                "We will follow cheating, bribery, naked combat, and city rivalry inside the games.",
                "exactly two adult men and no others",
                "plain dark leather hand wraps",
                2,
            ),
            (
                "And like this episode if Achilles and Hector finally felt painfully human.",
                "exactly two adult men and no others",
                "both have exhausted eyes, dirt, small cuts, grief, and fear",
                2,
            ),
        )
        for narration, required_a, required_b, expected_count in cases:
            with self.subTest(narration=narration):
                source = prepare_scene_contract_source(
                    (
                        "Year/period: 12th Century BCE Tradition; Exact place: Aegean Sea, Troy; "
                        "Culture scope: Mycenaean Greek kingdoms, Trojan polity; "
                        "Main subject: generic ambiguous workbook scene; "
                        "Scene: generic ambiguous workbook scene, Late Bronze Age Mycenaean and Homeric material culture"
                    ),
                    "mature vintage dark historical manhwa illustration",
                    narration_context=narration,
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertIn(required_a, compiled.positive)
                self.assertIn(required_b, compiled.positive)
                self.assertEqual(compiled.person_count, expected_count)
                self.assertNotIn("generic ambiguous workbook scene", compiled.positive)
                self.assertIn("readable writing", compiled.negative)

        setting_cases = (
            (
                "Frank Calvert identified Hisarlik's promise before Heinrich Schliemann launched famous excavations there.",
                "1860s-1870s AD archaeological fieldwork",
            ),
            (
                "A historical conflict may lie beneath the epic, but its heroes remain beyond proof.",
                "present-day archaeological artifact study",
            ),
            (
                "We will follow cheating, bribery, naked combat, and city rivalry inside the games.",
                "Archaic Greek Olympic games, 8th-6th century BCE",
            ),
        )
        for narration, expected_setting in setting_cases:
            with self.subTest(setting=narration):
                source = prepare_scene_contract_source(
                    (
                        "Year/period: 12th Century BCE Tradition; Exact place: Aegean Sea, Troy; "
                        "Culture scope: Mycenaean Greek kingdoms, Trojan polity; "
                        "Main subject: generic ambiguous workbook scene; "
                        "Scene: generic ambiguous workbook scene, Late Bronze Age Mycenaean and Homeric material culture"
                    ),
                    "mature vintage dark historical manhwa illustration",
                    narration_context=narration,
                )
                compiled = self.compile(source, model="comfyui-z-image-turbo")
                self.assertIn(expected_setting, compiled.positive)
                self.assertNotIn("12th Century BCE Tradition", compiled.positive)


if __name__ == "__main__":
    unittest.main()
