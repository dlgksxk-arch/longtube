import re
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ch2_europe_workbook_to_prepared_scripts import (  # noqa: E402
    _DIRECT_CAPTION_TEMPLATES,
    _clean_flux_prompt,
    _clean_integrated_prompt,
    _direct_caption_translation,
    _ENGLISH_CONTINUITY_TRANSITION_OVERRIDES,
    _english_continuity_prompt_cycle,
    _integrated_shorts_tag,
    _localized_era,
    _rebuild_english_continuity_prompt,
    _rebuild_english_continuity_thumbnail_prompt,
    _set_prompt_period,
    ENGLISH_CONTINUITY_END_LOCK,
    ENGLISH_CONTINUITY_MATERIAL_LOCK,
)
from scripts.ch2_europe_titles_en import (  # noqa: E402
    EPISODE_TITLES_EN,
    english_episode_title,
)


class Ch2EuropeWorkbookConverterTests(unittest.TestCase):
    def test_direct_english_title_catalog_covers_all_episodes(self):
        self.assertEqual(set(EPISODE_TITLES_EN), set(range(1, 180)))
        self.assertEqual(english_episode_title(176), "The Eurozone Debt Crisis")
        self.assertEqual(english_episode_title(177), "Brexit")
        self.assertEqual(
            english_episode_title(178),
            "Russia's Invasion of Ukraine and the Remaking of European Security",
        )

    def test_direct_translations_cover_every_known_contaminated_cut(self):
        expected_cuts = {
            1,
            2,
            3,
            4,
            13,
            16,
            19,
            23,
            32,
            42,
            47,
            61,
            73,
            76,
            88,
            92,
            107,
            124,
            136,
        }
        self.assertEqual(set(_DIRECT_CAPTION_TEMPLATES), expected_cuts)
        for cut_number in expected_cuts:
            tracks = _direct_caption_translation(cut_number, "기원전 490~479년")
            self.assertEqual(set(tracks), {"en", "fr", "es", "de"})
            self.assertTrue(all(tracks.values()))
            self.assertFalse(any(re.search(r"[가-힣]", text) for text in tracks.values()))

    def test_rewrites_the_full_sentence_instead_of_replacing_tokens(self):
        tracks = _direct_caption_translation(1, "기원전 3500~2000년경")
        self.assertEqual(
            tracks["en"],
            "Before this became history, someone had to live through it.",
        )
        self.assertIn("l'histoire", tracks["fr"])
        self.assertIn("Geschichte", tracks["de"])

    def test_localizes_years_centuries_ranges_and_traditions(self):
        self.assertEqual(_localized_era("1054년", "en"), "in 1054")
        self.assertEqual(_localized_era("1054년", "de"), "im Jahr 1054")
        self.assertEqual(
            _localized_era("기원전 490~479년", "fr"),
            "entre 490 et 479 av. J.-C.",
        )
        self.assertEqual(
            _localized_era("기원전 12세기 전승", "es"),
            "en una tradición del siglo XII a. C.",
        )
        self.assertEqual(
            _localized_era("14세기 후반", "de"),
            "im späten 14. Jahrhundert",
        )
        self.assertEqual(
            _localized_era("2022년~현재", "fr"),
            "de 2022 à aujourd'hui",
        )

    def test_flux_cleanup_removes_contaminated_narration_and_context(self):
        cleaned = _clean_flux_prompt(
            'FLUX2 4B optimized prompt: Roman forum; narration beat: “한글 문장”; '
            "context: 로마 제국; cinematic light"
        )
        self.assertEqual(cleaned, "Roman forum; cinematic light")

    def test_integrated_prompt_cleanup_removes_narration_and_expands_period_guard(self):
        cleaned = _clean_integrated_prompt(
            "A Roman forum where a ritual horse is led toward the next episode, set around 44 BCE. "
            "Narrative beat: Caesar enters. "
            "telephoto compression across a crowded historical scene; cold daylight. "
            "no modern objects, no anachronisms"
        )
        cleaned = _set_prompt_period(cleaned, "the late Roman Republic, 44 BCE")
        self.assertNotIn("Narrative beat", cleaned)
        self.assertNotIn("Caesar enters", cleaned)
        self.assertNotIn("next episode", cleaned)
        self.assertNotIn("set around", cleaned)
        self.assertIn("ritual horse is led forward", cleaned)
        self.assertNotIn("no modern objects", cleaned)
        self.assertIn("set during the late Roman Republic, 44 BCE", cleaned)
        self.assertIn(
            "no objects, clothing, architecture, vehicles, or weapons outside the depicted period",
            cleaned,
        )

    def test_integrated_shorts_tags_are_strict(self):
        self.assertEqual(_integrated_shorts_tag("#4-12"), (4, 12))
        self.assertIsNone(_integrated_shorts_tag(""))
        with self.assertRaises(ValueError):
            _integrated_shorts_tag("#5-1")

    def test_english_continuity_prompt_cycle_matches_reviewed_workbook_pattern(self):
        self.assertEqual(
            _english_continuity_prompt_cycle(1),
            (
                "wide establishing shot",
                "35mm documentary lens",
                "cold dawn light",
            ),
        )
        self.assertEqual(
            _english_continuity_prompt_cycle(8),
            (
                "wide establishing shot",
                "35mm documentary lens",
                "soft overcast daylight",
            ),
        )

    def test_english_continuity_prompt_rebuild_restores_only_fixed_tail(self):
        source_body = (
            "Yamnaya chief and farmer elder facing each other, "
            "character continuity: Yamnaya chief with ochre wool cloak and copper dagger"
        )
        source = f"{source_body},, {ENGLISH_CONTINUITY_END_LOCK}"
        rebuilt = _rebuild_english_continuity_prompt(source, 5)
        self.assertTrue(rebuilt.startswith(source_body + ", "))
        self.assertIn(ENGLISH_CONTINUITY_MATERIAL_LOCK, rebuilt)
        self.assertIn("low-angle action shot, 35mm lens, moonlit blue-black night", rebuilt)
        self.assertNotIn(",,", rebuilt)
        self.assertTrue(rebuilt.endswith(ENGLISH_CONTINUITY_END_LOCK))

    def test_english_continuity_prompt_rebuild_replaces_partial_fixed_tail(self):
        source_body = "Roman senators confront a general in the forum"
        source = (
            f"{source_body}, period-accurate clothing, architecture, tools, and, "
            f"{ENGLISH_CONTINUITY_END_LOCK}"
        )
        rebuilt = _rebuild_english_continuity_prompt(source, 2)
        self.assertTrue(rebuilt.startswith(source_body + ", "))
        self.assertEqual(rebuilt.count(ENGLISH_CONTINUITY_MATERIAL_LOCK), 1)
        self.assertIn(
            "eye-level medium shot, 50mm documentary lens, soft overcast daylight",
            rebuilt,
        )

    def test_english_continuity_prompt_rebuild_fails_when_end_lock_changed(self):
        with self.assertRaisesRegex(ValueError, "end lock"):
            _rebuild_english_continuity_prompt("A historical scene, no watermark", 1)

    def test_english_continuity_thumbnail_prompt_rebuild_restores_locks(self):
        source_body = (
            "Lucretia stands before Roman nobles, character continuity: Lucretia in a "
            "white wool stola, composed expression turning to"
        )
        source = (
            f"{source_body}, period-accurate clothing, architecture, tools, and, "
            f"{ENGLISH_CONTINUITY_END_LOCK}"
        )
        rebuilt = _rebuild_english_continuity_thumbnail_prompt(source)
        self.assertNotIn("turning to", rebuilt)
        self.assertNotIn(",,", rebuilt)
        self.assertEqual(rebuilt.count(ENGLISH_CONTINUITY_MATERIAL_LOCK), 1)
        self.assertTrue(rebuilt.endswith(ENGLISH_CONTINUITY_END_LOCK))

    def test_ep12_transition_override_targets_immediate_ep13(self):
        self.assertEqual(
            set(_ENGLISH_CONTINUITY_TRANSITION_OVERRIDES),
            {(12, cut_number) for cut_number in range(145, 151)},
        )
        self.assertIn(
            "Rome",
            _ENGLISH_CONTINUITY_TRANSITION_OVERRIDES[(12, 145)]["narration"],
        )
        self.assertIn(
            "Roman Republic",
            _ENGLISH_CONTINUITY_TRANSITION_OVERRIDES[(12, 150)]["prompt_body"],
        )


if __name__ == "__main__":
    unittest.main()
