import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.title_utils import shorts_upload_title, strong_main_upload_title  # noqa: E402
from app.services.youtube_metadata import (  # noqa: E402
    format_description,
    recommended_shorts_title_hashtags,
)


class YouTubeMetadataTests(unittest.TestCase):
    def test_format_description_adds_rich_hashtag_block(self):
        narration = "\n".join([
            "고구려 성문 앞에 병사들이 모이고, 낡은 칼 한 자루가 사건의 단서로 남습니다.",
            "주인공은 칼의 주인을 찾으며 사라진 사람들의 행적을 따라갑니다.",
            "왕실과 변경 마을의 긴장이 커지고, 작은 증언 하나가 흐름을 바꿉니다.",
            "마지막에는 칼이 단순한 무기가 아니라 숨겨진 약속의 증거였다는 사실이 드러납니다.",
        ])

        text = format_description(
            "부러진 칼의 주인을 찾아가는 이야기입니다.",
            title="부러진 칼의 주인을 찾아라 EP.03",
            topic="고구려 부러진 칼",
            narration=narration,
            language="ko",
        )

        self.assertIn("핵심 포인트:", text)
        self.assertIn("추천 해시태그:", text)
        self.assertGreaterEqual(text.count("#"), 8)

    def test_shorts_upload_title_can_append_recommended_hashtags(self):
        title = shorts_upload_title(
            "숨겨진 진실 #1 #Shorts",
            index=1,
            total=4,
            recommended_hashtags=["#고구려", "#역사쇼츠"],
        )

        self.assertEqual(title, "숨겨진 진실 #Shorts #고구려 #역사쇼츠")
        self.assertNotRegex(title, r"#\d+\b")

    def test_english_shorts_upload_title_does_not_truncate_before_hashtags(self):
        title = shorts_upload_title(
            "William I’s Fatal Raid: The Death That Split an Empire",
            index=1,
            total=4,
            context_title="William I’s Fatal Raid: The Death That Split an Empire",
            recommended_hashtags=["#William", "#Fatal", "#Raid"],
        )

        self.assertLessEqual(len(title), 100)
        self.assertIn("William I", title)
        self.assertNotIn("Death Th:", title)
        self.assertNotRegex(title, r"\b(?:a|an|and|for|of|that|the|to|with)\s+#Shorts\b")

    def test_english_shorts_upload_title_replaces_generic_template_with_context(self):
        title = shorts_upload_title(
            "One deal. Total humiliation.",
            index=4,
            total=4,
            context_title="Edmund Ironside and the Peace That Handed England to Cnut",
            recommended_hashtags=["#Edmund", "#Ironside", "#Peace"],
        )

        self.assertLessEqual(len(title), 100)
        self.assertIn("Edmund Ironside", title)
        self.assertNotIn("One deal", title)
        self.assertNotIn("Total humiliation", title)

    def test_english_main_upload_title_is_stronger_before_episode_label(self):
        title = strong_main_upload_title(
            "Edmund Ironside and the Peace That Handed England to Cnut",
            16,
        )

        self.assertEqual(title, "The Peace That Lost England EP.16")

    def test_recommended_shorts_title_hashtags_are_title_safe(self):
        tags = recommended_shorts_title_hashtags(
            title="고구려 비밀 작전",
            topic="고구려 전쟁사",
            narration="고구려 왕과 병사들이 변경의 성문 앞에서 작전을 준비합니다.",
            language="ko",
        )

        self.assertGreaterEqual(len(tags), 1)
        self.assertLessEqual(len(tags), 3)
        self.assertNotIn("#Shorts", tags)
        self.assertTrue(all(tag.startswith("#") and len(tag) <= 17 for tag in tags))


if __name__ == "__main__":
    unittest.main()
