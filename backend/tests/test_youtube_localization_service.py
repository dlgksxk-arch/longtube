import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.youtube_localization_service import (  # noqa: E402
    build_youtube_metadata_localizations,
    ensure_primary_youtube_metadata_language,
    normalize_youtube_localizations,
    youtube_localization_languages,
)


class YouTubeLocalizationTests(unittest.IsolatedAsyncioTestCase):
    def test_language_and_localization_normalization(self):
        config = {
            "language": "en",
            "caption_languages": ["en", "fr-FR", "es_ES", "de"],
        }
        self.assertEqual(
            youtube_localization_languages(config),
            ["fr", "es", "de"],
        )
        normalized = normalize_youtube_localizations({
            "fr_FR": {"title": "  Titre  ", "description": "Texte\r\n\r\n\r\nSuite"},
            "en": {"title": "English", "description": "Default"},
        })
        self.assertEqual(normalized["fr"]["title"], "Titre")
        self.assertEqual(normalized["fr"]["description"], "Texte\n\nSuite")

    def test_japanese_source_language_is_not_requested_as_a_localization(self):
        self.assertEqual(
            youtube_localization_languages({
                "language": "ja",
                "caption_languages": ["ja", "fr", "es"],
            }),
            ["fr", "es"],
        )

    def test_overlong_localized_title_is_fitted_and_preserves_shorts_hashtags(self):
        long_title = (
            "Pourquoi les migrations de la steppe ont bouleverse les anciennes societes "
            "europeennes et transforme durablement leurs institutions #Shorts #Histoire"
        )
        normalized = normalize_youtube_localizations({
            "fr": {"title": long_title, "description": "Description francaise"},
        })
        title = normalized["fr"]["title"]
        self.assertLessEqual(len(title), 100)
        self.assertTrue(title.endswith("#Shorts #Histoire"))
        self.assertFalse(title.endswith(" "))

    async def test_complete_script_localizations_skip_model_generation(self):
        localizations = {
            "fr": {"title": "Titre", "description": "Description francaise"},
            "es": {"title": "Titulo", "description": "Descripcion espanola"},
            "de": {"title": "Titel", "description": "Deutsche Beschreibung"},
        }
        result = await build_youtube_metadata_localizations(
            title="English title",
            description="English description",
            script={"youtube_localizations": localizations},
            config={
                "language": "en",
                "youtube_localization_languages": ["fr", "es", "de"],
                "youtube_metadata_localizations_enabled": True,
            },
        )
        self.assertEqual(result, localizations)

    async def test_disabled_generation_returns_only_supplied_localizations(self):
        result = await build_youtube_metadata_localizations(
            title="English title",
            description="English description",
            script={
                "youtube_localizations": {
                    "fr": {"title": "Titre", "description": "Description francaise"},
                }
            },
            config={
                "language": "en",
                "youtube_localization_languages": ["fr", "es", "de"],
                "youtube_metadata_localizations_enabled": False,
            },
        )
        self.assertEqual(sorted(result), ["fr"])

    async def test_openai_hard_stop_skips_optional_localization_generation(self):
        with patch(
            "app.services.youtube_localization_service._translate_openai",
            new=AsyncMock(),
        ) as mocked:
            result = await build_youtube_metadata_localizations(
                title="English title",
                description="English description",
                script={
                    "youtube_localizations": {
                        "fr": {
                            "title": "Titre",
                            "description": "Description francaise",
                        },
                    }
                },
                config={
                    "language": "en",
                    "youtube_localization_languages": ["fr", "es", "de"],
                    "youtube_metadata_localizations_enabled": True,
                    "youtube_metadata_translation_model": "gpt-5.4-mini",
                },
            )

        self.assertEqual(sorted(result), ["fr"])
        mocked.assert_not_awaited()

    async def test_amanoiwato_overlay_uses_reviewed_local_japanese_without_model(self):
        with patch(
            "app.services.youtube_localization_service._translate_openai",
            new=AsyncMock(),
        ) as mocked:
            title, description = await ensure_primary_youtube_metadata_language(
                title="여신의 파격적인 스트립쇼가 세상을 구했다?!",
                description="여신의 파격적인 스트립쇼가 세상을 구했다?!",
                config={"language": "ja"},
            )

        self.assertEqual(title, "女神の型破りな踊りが世界を救った！？")
        self.assertEqual(description, title)
        mocked.assert_not_awaited()

    async def test_amanoiwato_upload_metadata_uses_reviewed_local_japanese_without_model(self):
        with patch(
            "app.services.youtube_localization_service._translate_openai",
            new=AsyncMock(),
        ) as mocked:
            title, description = await ensure_primary_youtube_metadata_language(
                title="일본사 시크릿 암흑으로 변한 세상, 아마노이와토 EP.11",
                description="아마테라스가 동굴로 숨어 세계가 어둠에 잠긴 이야기입니다.",
                config={"language": "ja"},
            )

        self.assertEqual(title, "闇に包まれた世界、天岩戸 EP.11")
        self.assertNotRegex(f"{title}\n{description}", r"[가-힣]")
        self.assertIn("アメノウズメ", description)
        self.assertIn("スサノオ", description)
        mocked.assert_not_awaited()

    async def test_hangul_primary_metadata_is_translated_before_japanese_upload(self):
        translated = {
            "ja": {
                "title": "亡き女神の身体から芽吹いた命 EP.07",
                "description": "食物の女神ウケモチの死から穀物と蚕が生まれる神話をたどります。",
            }
        }
        with patch(
            "app.services.youtube_localization_service._translate_openai",
            new=AsyncMock(return_value=translated),
        ) as mocked:
            title, description = await ensure_primary_youtube_metadata_language(
                title="죽은 여신의 시신에서 피어난 생명 EP.07",
                description="우케모치의 죽음에서 곡식과 누에가 태어나는 신화입니다.",
                config={"language": "ja", "youtube_metadata_translation_model": "gpt-test"},
            )

        self.assertEqual(title, translated["ja"]["title"])
        self.assertEqual(description, translated["ja"]["description"])
        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.kwargs["source_language"], "ko")
        self.assertEqual(mocked.await_args.kwargs["target_languages"], ["ja"])
        self.assertTrue(mocked.await_args.kwargs["strict_no_hangul"])

    async def test_hangul_residue_in_japanese_metadata_is_repaired_once(self):
        first_pass = {
            "ja": {
                "title": "亡き 여신 の身体から芽吹いた命 EP.07",
                "description": "食物の女神 우케모치 の死から穀物が生まれる神話です。",
            }
        }
        repaired = {
            "ja": {
                "title": "亡き女神の身体から芽吹いた命 EP.07",
                "description": "食物の女神ウケモチの死から穀物が生まれる神話です。",
            }
        }
        with patch(
            "app.services.youtube_localization_service._translate_openai",
            new=AsyncMock(side_effect=[first_pass, repaired]),
        ) as mocked:
            title, description = await ensure_primary_youtube_metadata_language(
                title="죽은 여신의 시신에서 피어난 생명 EP.07",
                description="우케모치의 죽음에서 곡식이 태어나는 신화입니다.",
                config={"language": "ja", "youtube_metadata_translation_model": "gpt-test"},
            )

        self.assertEqual(title, repaired["ja"]["title"])
        self.assertEqual(description, repaired["ja"]["description"])
        self.assertEqual(mocked.await_count, 2)
        repair_call = mocked.await_args_list[1]
        self.assertEqual(repair_call.kwargs["source_language"], "ja")
        self.assertEqual(repair_call.kwargs["title"], first_pass["ja"]["title"])
        self.assertTrue(repair_call.kwargs["strict_no_hangul"])


if __name__ == "__main__":
    unittest.main()
