import asyncio
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.title_utils import series_episode_main_upload_title, shorts_upload_title, strong_main_upload_title  # noqa: E402
from app.services.shorts_service import derive_shorts_segment_title, resolve_shorts_source_title  # noqa: E402
from app.services.youtube_metadata import (  # noqa: E402
    expand_tags,
    format_description,
    recommended_shorts_title_hashtags,
    validate_metadata_for_profile,
)
from app.services.oneclick_service import _append_youtube_channel_description  # noqa: E402
from app.services.youtube_localization_service import ensure_primary_youtube_metadata_language  # noqa: E402


class YouTubeMetadataTests(unittest.TestCase):
    def test_japanese_shorts_title_keeps_both_sides_of_punctuation(self):
        script = {
            "title": "八つの頭を持つ怪物、ヤマタノオロチ EP.14",
            "language": "ja",
        }
        labels = {
            "default_title_1": "",
            "default_title_2": "",
        }

        title = __import__(
            "app.services.shorts_service",
            fromlist=["_short_title"],
        )._short_title(
            script,
            {},
            labels,
            "八つの頭を持つ怪物、ヤマタノオロチ",
        )

        self.assertEqual(title, "八つの頭を持つ怪物\nヤマタノオロチ")

    def test_japanese_shorts_source_title_translates_yamata_no_orochi_title(self):
        title = asyncio.run(
            resolve_shorts_source_title(
                {
                    "title": "일본사 시크릿 8개의 머리를 가진 괴물, 야마타노오로치 EP.14",
                    "topic": "8개의 머리를 가진 괴물, 야마타노오로치",
                    "description": "스사노오가 이즈모에서 야마타노오로치를 만나는 이야기",
                    "language": "ja",
                }
            )
        )

        self.assertEqual(title, "八つの頭を持つ怪物、ヤマタノオロチ")
        self.assertNotRegex(title, r"[가-힣]")

    def test_yamata_no_orochi_primary_metadata_does_not_use_amano_iwato_title(self):
        title, description = asyncio.run(
            ensure_primary_youtube_metadata_language(
                title="8개의 머리를 가진 괴물, 야마타노오로치 EP.14",
                description="스사노오가 이즈모에서 야마타노오로치를 만나는 이야기",
                config={"language": "ja"},
            )
        )

        self.assertEqual(title, "八つの頭を持つ怪物、ヤマタノオロチ EP.14")
        self.assertIn("ヤマタノオロチ", description)
        self.assertNotIn("天岩戸", title)

    def test_yamata_no_orochi_shorts_segment_does_not_claim_sun_disappeared(self):
        script = {
            "title": "八つの頭を持つ怪物、ヤマタノオロチ EP.14",
            "language": "ja",
            "cuts": [
                {
                    "cut_number": 69,
                    "narration": "彼は老夫婦に向かって、ある驚くべき提案を持ちかけます。",
                },
                {
                    "cut_number": 74,
                    "narration": "私は太陽の女神アマテラスオオミカミの弟、スサノオである。",
                },
            ],
        }

        title = derive_shorts_segment_title(
            script,
            {"start_cut": 69, "end_cut": 83},
        )

        self.assertNotIn("太陽神が消えた", title)
        self.assertNotIn("世界が暗闇へ", title)

    def test_channel_description_is_appended_without_replacing_episode_description(self):
        description = _append_youtube_channel_description(
            "이번 편에서는 기묘한 왕실 재판의 전말을 추적합니다.",
            {"youtube_channel_description": "사건탐구회는 기록을 바탕으로 역사 속 사건을 풀어냅니다."},
        )

        self.assertTrue(description.startswith("이번 편에서는"))
        self.assertIn("사건탐구회는 기록을", description)

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

    def test_japanese_shorts_title_removes_tts_token_spacing(self):
        title = shorts_upload_title(
            "たった 一つ の 動作 から も、 無数 の 命",
            recommended_hashtags=["#日本神話", "#古事記"],
        )

        self.assertEqual(
            title,
            "たった一つの動作からも、無数の命 #Shorts #日本神話 #古事記",
        )
        self.assertEqual(
            shorts_upload_title("天照大御神 は 高天原 を 暖かく 照らし、"),
            "天照大御神は高天原を暖かく照らし #Shorts",
        )

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

    def test_english_shorts_upload_title_preserves_specific_segment_heroes(self):
        context_title = "Minoan Collapse and the Late Bronze Age Crisis EP.06"
        cases = [
            "They Escaped the City Before Ash Buried It",
            "The Invaders Kept The Minoan Machine",
            "One Decoding Exposed Crete's New Rulers",
        ]

        for index, hero in enumerate(cases, start=1):
            with self.subTest(hero=hero):
                title = shorts_upload_title(
                    hero,
                    index=index,
                    total=4,
                    context_title=context_title,
                )
                self.assertEqual(title, f"{hero} #Shorts")
                self.assertNotIn("fatal turn", title.casefold())
                self.assertNotIn("how it collapsed", title.casefold())
                self.assertNotIn("cost of", title.casefold())

    def test_english_main_upload_title_is_stronger_before_episode_label(self):
        title = strong_main_upload_title(
            "Edmund Ironside and the Peace That Handed England to Cnut",
            16,
        )

        self.assertEqual(title, "The Peace That Lost England EP.16")

    def test_minoan_main_upload_title_uses_specific_crisis_hook(self):
        title = strong_main_upload_title(
            "Minoan Collapse and the Late Bronze Age Crisis",
            6,
        )

        self.assertEqual(
            title,
            "Crete Burned in 1450 BCE—Who Ended the Minoan World? EP.06",
        )

    def test_japanese_dead_goddess_main_title_uses_specific_crisis_hook(self):
        title = strong_main_upload_title(
            "ころされた女神から、稲と蚕が生まれた",
            7,
        )

        self.assertEqual(
            title,
            "殺された女神の死体から米と蚕が生まれた EP.07",
        )

    def test_japanese_shorts_upload_title_preserves_hero_line_boundary(self):
        script = {
            "title": "ころされた女神から、稲と蚕が生まれた EP.07",
            "language": "ja",
            "cuts": [
                {
                    "cut_number": 6,
                    "narration": "月の神ツクヨミが遣わされます。",
                },
                {
                    "cut_number": 7,
                    "narration": "神の食卓は殺しの場に変わり、ウケモチは倒れました。",
                },
            ],
        }

        base = derive_shorts_segment_title(
            script,
            {"start_cut": 6, "end_cut": 7},
        )
        title = shorts_upload_title(base, recommended_hashtags=["#日本神話"])

        self.assertEqual(base, "神の食卓で殺害｜女神に何が起きた")
        self.assertEqual(title, "神の食卓で殺害｜女神に何が起きた #Shorts #日本神話")

    def test_shorts_hero_copy_uses_segment_event_instead_of_generic_template(self):
        script = {
            "title": "Minoan Collapse and the Late Bronze Age Crisis EP.06",
            "language": "en",
            "cuts": [
                {
                    "cut_number": 26,
                    "narration": "A major earthquake throws upper floors down into the streets.",
                },
                {
                    "cut_number": 27,
                    "narration": "Families clear rubble during a brief pause before the final blast.",
                },
            ],
        }
        title = derive_shorts_segment_title(
            script,
            {"start_cut": 26, "end_cut": 27},
        )

        self.assertEqual(title, "The Quake Was Only The Final Warning")
        self.assertNotIn("fatal turn", title.casefold())

    def test_baekje_wani_shorts_hero_uses_chronology_conflict(self):
        script = {
            "title": "고대 한류, 칠지도와 해상 무역 EP.05",
            "language": "ko",
            "cuts": [
                {
                    "cut_number": 106,
                    "narration": "왕인은 왜에 논어와 천자문을 전한 백제 학자로 널리 알려져 있습니다.",
                },
                {
                    "cut_number": 110,
                    "narration": "기록 사이에는 왕인의 활동 시점만 삼사십 년 가까이 차이가 납니다.",
                },
                {
                    "cut_number": 115,
                    "narration": "사오세기 인물인 왕인이 그 책을 가져갔다는 전승과 맞지 않죠.",
                },
                {
                    "cut_number": 117,
                    "narration": "구체적인 책 이름과 연대에는 후대 윤색이 섞였다고 봐야 합니다.",
                },
            ],
        }
        title = derive_shorts_segment_title(
            script,
            {"start_cut": 106, "end_cut": 120},
        )

        self.assertEqual(title, "왕인 전설의 연대 계산이 안 맞는다")
        self.assertNotIn("일본 형성에 남은 일본에 남은 백제", title)

    def test_series_episode_main_upload_title_uses_requested_prefix(self):
        title = series_episode_main_upload_title(
            "왕위에서 밀려난 온조, 형의 몰락 위에 세운 백제",
            1,
            "백제",
        )

        self.assertEqual(
            title,
            "백제-EP.01 왕위에서 밀려난 온조, 형의 몰락 위에 세운 백제",
        )

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

    def test_japanese_shorts_title_hashtags_drop_connective_fragments(self):
        tags = recommended_shorts_title_hashtags(
            title="死体の種を拾った｜人類の農業が始まる",
            topic="殺された女神の死体から米と蚕が生まれた",
            narration="けれど、本編はここから農業の始まりを追います。",
            language="ja",
        )

        self.assertNotIn("#けれど", tags)
        self.assertNotIn("#本編は", tags)

    def test_japanese_tags_are_not_dropped_by_word_filter(self):
        tags = expand_tags(
            ["日本神話", "古事記", "天照大御神"],
            title="三貴子の誕生",
            topic="禊から誕生した三貴子",
            narration="伊邪那岐命の禊から天照大御神、月読命、須佐之男命が誕生しました。",
            language="ja",
        )

        self.assertIn("日本神話", tags)
        self.assertIn("古事記", tags)
        self.assertIn("天照大御神", tags)
        self.assertIn("日本史", tags)
        self.assertNotIn("戦争史", tags)
        self.assertNotIn("しかし", tags)
        self.assertNotIn("いました", tags)

    def test_european_history_profile_excludes_unrelated_horror_metadata(self):
        title = "Proto-Indo-European Creation Myth: Manu and Yemo"
        narration = (
            "Manu and Yemo stand at the center of a reconstructed Indo-European myth. "
            "The story survives through related traditions recorded across Europe and Asia."
        )
        description = format_description(
            "",
            title=title,
            topic=title,
            narration=narration,
            language="en",
            profile="european_history",
        )
        tags = expand_tags(
            ["horror story", "locked room"],
            title=title,
            topic=title,
            narration=narration,
            language="en",
            profile="european_history",
        )

        self.assertIn("Scartography", description)
        self.assertIn("Subtitles available in English, French, Spanish, and German", description)
        self.assertIn("Proto-Indo-European", tags)
        self.assertIn("European history", tags)
        self.assertNotIn("horror story", tags)
        self.assertNotIn("locked room", tags)
        self.assertLessEqual(len(tags), 12)
        validate_metadata_for_profile(
            title=title,
            description=description,
            tags=tags,
            profile="european_history",
        )

    def test_european_history_profile_rejects_legacy_generic_metadata(self):
        with self.assertRaisesRegex(ValueError, "unrelated generic terms"):
            validate_metadata_for_profile(
                title="A European Story",
                description="If you enjoy mystery, suspense, strange incidents, watch this.",
                tags=["history", "nightmare story"],
                profile="european_history",
            )


if __name__ == "__main__":
    unittest.main()
