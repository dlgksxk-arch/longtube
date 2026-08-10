import unittest

from scripts import rewrite_remaining_text_risk_prompts as rewrite


class RewriteRemainingTextRiskPromptsTests(unittest.TestCase):
    def test_detects_direct_and_object_based_text_risks(self):
        prompt = "A glowing title card above an old newspaper and military map"
        self.assertEqual(
            set(rewrite._risk_categories(prompt)),
            {"explicit", "paper", "layout"},
        )

    def test_ignores_explicit_no_text_directive(self):
        self.assertEqual(rewrite._risk_categories("plain wall with no readable text"), [])

    def test_rewrite_changes_only_image_fields_and_removes_risk(self):
        cut = {
            "cut_number": 5,
            "narration": "토끼들이 사냥터를 뒤덮었습니다.",
            "image_prompt": "Napoleon holding a folded military map beside a title card",
        }
        narration_before = cut["narration"]
        prompt = rewrite._rewrite_prompt(
            cut=cut,
            channel=4,
            episode_number=9,
            translated_narration="Domestic rabbits overwhelmed the hunting ground.",
        )
        self.assertEqual(cut["narration"], narration_before)
        self.assertEqual(rewrite._risk_categories(prompt), [])
        self.assertIn("domestic rabbits", prompt)

    def test_translation_key_is_stable(self):
        self.assertEqual(
            rewrite._translation_key(channel=3, episode_number=14, cut_number=7),
            "CH3-EP014-CUT007",
        )


if __name__ == "__main__":
    unittest.main()
