from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.image.comfyui_service import (  # noqa: E402
    _image_has_internal_text_like_marks,
    _internal_text_detector_policy_prompt,
    _is_baekje_ep01_foundation_generation_context,
    _is_baekje_ep01_modern_pungnap_generation_context,
    _should_check_baekje_ep01_internal_text,
    _should_check_internal_text_for_generation,
    _should_check_internal_text_after_generation,
    _should_skip_dense_internal_text_grid,
    _should_use_reduced_internal_text_detector,
)


class BaekjeEP01GenerationGuardTests(unittest.TestCase):
    _ANCIENT_WORLD = (
        "Global visual world: "
        "Time range: Late 1st century BC foundation tradition through the early reign of King Onjo; "
        "Culture scope: Goguryeo, Mahan, and Baekje; "
        "Year/period: Late 1st century BC foundation tradition through the early reign of King Onjo; "
    )

    @classmethod
    def _ancient_prompt(
        cls,
        *,
        exact_place: str,
        primary_subject: str,
        scene: str,
        visible_action: str,
        narration_context: str = "",
    ) -> str:
        prompt = (
            cls._ANCIENT_WORLD
            + f"Exact place: {exact_place}; "
            + f"Primary subject: {primary_subject}; "
            + f"Scene: {scene}; "
            + f"Visible action: {visible_action}"
        )
        if narration_context:
            prompt += f" || Narration context: {narration_context}"
        return prompt

    @classmethod
    def _cut33_court_prompt(cls) -> str:
        return cls._ancient_prompt(
            exact_place="the early Goguryeo royal court",
            primary_subject="young man Yuri and adult man Jumong",
            scene="Yuri stands before adult man Jumong as the court reorganizes around Yuri",
            visible_action="Jumong acknowledges Yuri before the assembled officials",
            narration_context="주몽은 오래 미루지 않은 채 그를 태자로 세웠죠.",
        )

    @classmethod
    def _cut31_or_32_court_prompt(cls, narration_context: str) -> str:
        return cls._ancient_prompt(
            exact_place="the early Goguryeo royal court",
            primary_subject="young man Yuri and adult man Jumong",
            scene="Yuri stands before adult man Jumong as the court reorganizes around Yuri",
            visible_action="Jumong acknowledges Yuri before the assembled officials",
            narration_context=narration_context,
        )

    @classmethod
    def _cut40_banner_prompt(cls) -> str:
        return cls._ancient_prompt(
            exact_place="the northern departure road from Jumong's realm",
            primary_subject="adult woman Soseono with Biryu and Onjo",
            scene="the three depart with packed baggage and blank unmarked woven cloth banners",
            visible_action="Soseono leads both sons southward",
        )

    @classmethod
    def _cut44_gate_prompt(cls) -> str:
        return cls._ancient_prompt(
            exact_place="a plain timber gate on the northern departure road",
            primary_subject="Ogan and Maryeo with retainers and families",
            scene="the households leave through the plain timber gate with household goods",
            visible_action="Ogan and Maryeo guide the departing families",
        )

    def test_ancient_cut33_cut40_and_cut44_enable_full_text_check(self):
        for cut_number, prompt in (
            (33, self._cut33_court_prompt()),
            (40, self._cut40_banner_prompt()),
            (44, self._cut44_gate_prompt()),
        ):
            with self.subTest(cut_number=cut_number):
                self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
                self.assertTrue(_should_check_baekje_ep01_internal_text(prompt))
                self.assertTrue(_should_check_internal_text_after_generation(prompt))
                self.assertFalse(_should_use_reduced_internal_text_detector(prompt))

    def test_ancient_cut13_without_text_risk_does_not_enable_text_check(self):
        prompt = self._ancient_prompt(
            exact_place="an early timber settlement courtyard",
            primary_subject="adult woman Soseono with her two sons",
            scene="Soseono directs household work while both sons remain beside her",
            visible_action="the family prepares for the next stage of their journey",
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut2_open_palisade_entrance_does_not_treat_wood_grain_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="outside Onjo's settlement",
            primary_subject="exactly one adult man Biryu",
            scene="Biryu stands alone outside one plain open timber-palisade entrance",
            visible_action=(
                "Biryu lowers his head on an empty road while uninterrupted bare wood "
                "fills the entrance"
            ),
            narration_context=(
                "도읍 하나를 잘못 고른 비류는 백성을 잃고, 동생의 성 앞에서 모든 선택이 무너졌죠"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut17_open_palisade_entrance_does_not_treat_thatch_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="one early Goguryeo settlement",
            primary_subject=(
                "Soseono and Jumong with secondary unarmed settlers"
            ),
            scene=(
                "Soseono and Jumong step together through one plain open "
                "timber-palisade entrance"
            ),
            visible_action=(
                "secondary settlers assemble behind them while uninterrupted bare wood "
                "forms the entrance"
            ),
            narration_context=(
                "전승 속 주몽은 그 힘을 발판으로 고구려를 세우며 소서노와 결합합니다"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut21_empty_palisade_entrance_does_not_treat_wood_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="Soseono's established royal household",
            primary_subject="Soseono, Biryu, and Onjo",
            scene=(
                "the distant plain open timber-palisade entrance and approach road "
                "remain empty"
            ),
            visible_action=(
                "Soseono stands between Biryu and Onjo while uninterrupted bare wood "
                "forms the entrance"
            ),
            narration_context=(
                "하지만 그 질서는 주몽의 친아들 유리가 돌아오기 전까지만 유지됐습니다"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut24_open_palisade_entrance_does_not_treat_thatch_or_wood_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="the edge of the early Goguryeo royal household",
            primary_subject=(
                "exactly four named people: one adult woman Soseono, exactly two adult "
                "men Biryu and Onjo, and one distant young adult man Yuri"
            ),
            scene=(
                "rough thatch roofs around one plain open timber-palisade entrance with "
                "uninterrupted bare wood"
            ),
            visible_action=(
                "Soseono stands with Biryu and Onjo while distant Yuri alone enters "
                "through the entrance"
            ),
            narration_context=(
                "소서노의 공로와 비류·온조의 자리도 혈통 앞에서 불안해졌습니다"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut26_open_palisade_entrance_does_not_enable_text_check(self):
        prompt = self._ancient_prompt(
            exact_place="Jolbon's open timber-palisade entrance",
            primary_subject="exactly two adult men: father Jumong and adult son Yuri",
            scene="uninterrupted bare timber and rough thatch surround the open entrance",
            visible_action=(
                "Jumong stands inside left and Yuri arrives outside right while both pairs "
                "of hands remain concealed in closed long sleeves"
            ),
            narration_context=(
                "유리가 졸본에 도착하면 주몽은 친아들의 귀환을 외면하기 어려웠고"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_cut29_closed_plain_gate_does_not_treat_bare_wood_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="outside Jolbon's closed gate",
            primary_subject="exactly one adult East Asian man named Yuri",
            scene=(
                "one closed plain timber gate with uninterrupted bare wood panels"
            ),
            visible_action=(
                "Direct centered rear head-and-shoulders view of Yuri immediately "
                "before the closed gate; his face is fully hidden; exactly zero "
                "visible hands or fingers"
            ),
            narration_context=(
                "그 평온을 깨뜨릴 청년이 마침내 졸본의 성문 앞에 섰고"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))
        self.assertFalse(
            _should_check_internal_text_for_generation(prompt, prompt, prompt)
        )

    def test_cut30_open_plain_gate_does_not_treat_bare_wood_as_text_risk(self):
        prompt = self._ancient_prompt(
            exact_place="inside Jolbon's open gate",
            primary_subject=(
                "exactly four named adults: Yuri, Soseono, Biryu, and Onjo"
            ),
            scene=(
                "one open plain timber gate with uninterrupted bare wood posts and panels"
            ),
            visible_action=(
                "Extreme facial close-up four-person reaction row as Soseono, Biryu, "
                "and Onjo turn their eyes toward Yuri; exactly zero visible hands"
            ),
            narration_context=(
                "문이 열리는 순간, 소서노 가족이 의지하던 권력의 균형도 함께 흔들렸죠"
            ),
        )

        self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))
        self.assertFalse(
            _should_check_internal_text_for_generation(prompt, prompt, prompt)
        )

    def test_cut31_and_cut32_court_wording_stays_off_without_cut33_narration(self):
        for cut_number, narration_context in (
            (31, "낯선 청년이 신하들 앞에 서자, 주몽은 그가 친아들 유리임을 확인합니다."),
            (32, "유리는 단순한 가족이 아니라 왕위를 이을 적통 후계자로 들어왔고,"),
        ):
            prompt = self._cut31_or_32_court_prompt(narration_context)
            with self.subTest(cut_number=cut_number):
                self.assertTrue(_is_baekje_ep01_foundation_generation_context(prompt))
                self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
                self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_runtime_policy_uses_ep01_final_scene_instead_of_global_source_scope(self):
        source_prompt = "direct source prompt without the structured EP01 world"
        cut33_generation_prompt = self._cut33_court_prompt()
        cut33_final_prompt = self._cut31_or_32_court_prompt("").strip()

        cut33_policy_prompt = _internal_text_detector_policy_prompt(
            source_prompt,
            cut33_final_prompt,
            cut33_generation_prompt,
        )

        self.assertNotEqual(cut33_policy_prompt, source_prompt)
        self.assertIn("Narration context:", cut33_policy_prompt)
        self.assertTrue(_should_check_baekje_ep01_internal_text(cut33_policy_prompt))
        self.assertFalse(_should_use_reduced_internal_text_detector(cut33_policy_prompt))
        self.assertTrue(_should_skip_dense_internal_text_grid(cut33_policy_prompt))

        cut31_generation_prompt = self._cut31_or_32_court_prompt(
            "낯선 청년이 신하들 앞에 서자, 주몽은 그가 친아들 유리임을 확인합니다."
        )
        cut31_policy_prompt = _internal_text_detector_policy_prompt(
            source_prompt,
            cut33_final_prompt,
            cut31_generation_prompt,
        )
        self.assertTrue(cut31_policy_prompt.startswith(cut33_final_prompt))
        self.assertIn("Narration context:", cut31_policy_prompt)
        self.assertFalse(
            _should_check_internal_text_for_generation(
                source_prompt,
                cut33_final_prompt,
                cut31_generation_prompt,
            )
        )

        global_scope_source = self._ancient_prompt(
            exact_place=(
                "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, "
                "and Ugok Fortress"
            ),
            primary_subject="the full episode world",
            scene="the full episode may later include maps, records, banners, and a fortress gate",
            visible_action="the source workbook supplies the complete episode scope",
        )
        cut5_final_prompt = self._ancient_prompt(
            exact_place="an open departure road",
            primary_subject="exactly two adults: Onjo and Biryu; one neighboring Mahan settlement",
            scene=(
                "Onjo moves screen-right while Biryu remains left-midground and the Mahan "
                "settlement stays far-left across a broad empty field gap"
            ),
            visible_action=(
                "the two men have no eye contact and no interaction in one continuous scene"
            ),
        )
        cut5_policy_prompt = _internal_text_detector_policy_prompt(
            global_scope_source,
            cut5_final_prompt,
            cut5_final_prompt,
        )
        self.assertEqual(cut5_policy_prompt, cut5_final_prompt)
        self.assertFalse(_should_check_internal_text_after_generation(cut5_policy_prompt))
        self.assertFalse(
            _should_check_internal_text_for_generation(
                global_scope_source,
                cut5_final_prompt,
                cut5_final_prompt,
            )
        )

    def test_modern_pungnap_archaeology_is_excluded_from_ep01_ancient_guard(self):
        prompt = (
            self._ANCIENT_WORLD
            + "Year/period: present-day archaeological examination; "
            + "Exact place: modern Seoul Pungnap earthen-wall excavation trench; "
            + "Primary subject: two archaeologists at an exposed soil cross section; "
            + "Scene: the archaeologists inspect rammed-earth layers with simple hand tools; "
            + "Visible action: both archaeologists compare the exposed soil layers"
        )

        self.assertFalse(_is_baekje_ep01_foundation_generation_context(prompt))
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertFalse(_should_check_internal_text_after_generation(prompt))

    def test_shortened_ep01_era_still_checks_final_blank_banner_from_actual_cut_scope(self):
        source_prompt = self._ancient_prompt(
            exact_place=(
                "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, "
                "and Ugok Fortress"
            ),
            primary_subject="the full episode world",
            scene="the source workbook supplies the full episode scope",
            visible_action="the source remains broad",
        )
        final_prompt = (
            "Visible action: Biryu leads families west with lowered blank unmarked woven banners. "
            "Primary subject: Biryu and secondary families. Era/period: Late 1st century BC. "
            "Culture scope: Goguryeo, Mahan, and Baekje."
        )

        policy_prompt = _internal_text_detector_policy_prompt(
            source_prompt,
            final_prompt,
            final_prompt,
        )
        self.assertTrue(_is_baekje_ep01_foundation_generation_context(policy_prompt))
        self.assertTrue(_should_check_baekje_ep01_internal_text(policy_prompt))
        self.assertTrue(
            _should_check_internal_text_for_generation(
                source_prompt,
                final_prompt,
                final_prompt,
            )
        )

    def test_modern_pungnap_blank_manuscript_surface_uses_generic_text_check(self):
        prompt = (
            "Visible action: Two closed blank unmarked manuscript covers remain separated in "
            "front of present-day excavated earth layers. Primary subject: exactly two closed "
            "blank unmarked manuscript covers. Era/period: Present-day archaeological examination."
        )
        self.assertFalse(_should_check_baekje_ep01_internal_text(prompt))
        self.assertTrue(_should_check_internal_text_after_generation(prompt))

    def test_modern_pungnap_runtime_uses_final_location_scene_not_source_manuscript(self):
        source_prompt = (
            "Global visual world: Culture scope: Goguryeo, Mahan, and Baekje; "
            "Era/period: Present-day archaeological examination; Exact place: Pungnap Toseong; "
            "Scene: ancient manuscripts fade into present-day Pungnap archaeological earth layers"
        )
        final_prompt = (
            "Visible action: Pungnap earthworks meet the Han River and broad open plain. "
            "Primary subject: present-day Pungnap Toseong earthworks. "
            "Era/period: Present-day archaeological examination. "
            "Culture scope: Goguryeo, Mahan, and Baekje."
        )

        self.assertTrue(_is_baekje_ep01_modern_pungnap_generation_context(source_prompt))
        self.assertTrue(_is_baekje_ep01_modern_pungnap_generation_context(final_prompt))
        self.assertEqual(
            _internal_text_detector_policy_prompt(
                source_prompt,
                final_prompt,
                final_prompt,
            ),
            final_prompt,
        )
        self.assertFalse(
            _should_check_internal_text_for_generation(
                source_prompt,
                final_prompt,
                final_prompt,
            )
        )

    def test_dense_grid_is_skipped_for_gate_and_court_but_not_banner_or_scroll(self):
        scroll_prompt = self._ancient_prompt(
            exact_place="an early Baekje record chamber",
            primary_subject="one blank genealogy scroll on a low timber surface",
            scene="an object-only blank genealogy scroll without writing",
            visible_action="the blank scroll lies fully unrolled",
        )

        for label, prompt in (
            ("court", self._cut33_court_prompt()),
            ("gate", self._cut44_gate_prompt()),
        ):
            with self.subTest(label=label):
                self.assertTrue(_should_check_baekje_ep01_internal_text(prompt))
                self.assertTrue(_should_skip_dense_internal_text_grid(prompt))

        for label, prompt in (
            ("banner", self._cut40_banner_prompt()),
            ("scroll", scroll_prompt),
        ):
            with self.subTest(label=label):
                self.assertTrue(_should_check_baekje_ep01_internal_text(prompt))
                self.assertFalse(_should_skip_dense_internal_text_grid(prompt))

    def test_actual_ep01_detector_routing_keeps_passed_gates_and_catches_rejected_text(self):
        episode_dir = Path(
            r"D:\long_result\CH1\백제사\EP.1.2607150045456ce0aa"
        )
        passed_dir = episode_dir / "images"
        rejected_dir = (
            episode_dir
            / "qa_rejected"
            / "ep01_role_period_content_fail_20260715_030009"
        )
        required_paths = [
            *(passed_dir / f"cut_{cut}.png" for cut in (28, 29, 30)),
            *(rejected_dir / f"cut_{cut}.png" for cut in (33, 40, 41, 42, 44, 45)),
        ]
        if not all(path.is_file() for path in required_paths):
            self.skipTest("actual Baekje EP01 detector fixtures are not present")

        gate_prompt = self._cut44_gate_prompt()
        banner_prompt = self._cut40_banner_prompt()
        court_prompt = self._cut33_court_prompt()

        for cut_number in (28, 29, 30):
            with self.subTest(cut_number=cut_number, expected="passed"):
                self.assertTrue(_should_check_baekje_ep01_internal_text(gate_prompt))
                self.assertTrue(_should_skip_dense_internal_text_grid(gate_prompt))
                self.assertFalse(
                    _image_has_internal_text_like_marks(
                        passed_dir / f"cut_{cut_number}.png",
                        include_dense_grid=False,
                    )
                )

        for cut_number, prompt in (
            (33, court_prompt),
            (40, banner_prompt),
            (41, banner_prompt),
            (42, banner_prompt),
            (44, gate_prompt),
            (45, gate_prompt),
        ):
            with self.subTest(cut_number=cut_number, expected="rejected"):
                self.assertTrue(_should_check_baekje_ep01_internal_text(prompt))
                self.assertTrue(
                    _image_has_internal_text_like_marks(
                        rejected_dir / f"cut_{cut_number}.png",
                        include_dense_grid=not _should_skip_dense_internal_text_grid(
                            prompt
                        ),
                    )
                )


if __name__ == "__main__":
    unittest.main()
