import asyncio
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import shorts_service  # noqa: E402
from app.services.tts.elevenlabs_service import ElevenLabsService  # noqa: E402
from app.services.tts.narration_fit import generate_tts_with_auto_narration_fit  # noqa: E402
from app.services.tts.japanese_preflight import (  # noqa: E402
    assert_japanese_tts_script_ready,
    inspect_japanese_tts_script,
)
from app.services.tts.narration_source import (  # noqa: E402
    build_tts_input_marker_payload,
    build_tts_request_context,
    prepare_script_tts_inputs,
    tts_input_marker_matches,
    write_tts_input_marker,
)
from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts  # noqa: E402


JA_CONFIG = {"language": "ja", "tts_model": "elevenlabs"}


class JapanesePronunciationRegressionTests(unittest.TestCase):
    def test_comment_reported_terms_use_verified_readings(self):
        spoken = prepare_spoken_narration_for_tts(
            "御家人、野見宿禰、人柱、埴輪、新羅、百済、高句麗、大火傷。",
            "ja",
        )

        for reading in (
            "ごけにん",
            "のみのすくね",
            "ひとばしら",
            "はにわ",
            "しらぎ",
            "くだら",
            "こうくり",
            "おおやけど",
        ):
            self.assertIn(reading, spoken)
        self.assertNotIn("おかじん", spoken)
        self.assertNotIn("だいやけど", spoken)

    def test_preflight_rejects_verified_wrong_kana(self):
        script = {
            "cuts": [
                {"cut_number": 1, "narration": "御家人の制度です。", "tts_narration": "おかじんのせいどです。"},
                {"cut_number": 2, "narration": "野見宿禰が登場します。", "tts_narration": "のみすくねがとうじょうします。"},
                {"cut_number": 3, "narration": "大火傷を負いました。", "tts_narration": "だいやけどをおいました。"},
                {"cut_number": 4, "narration": "一つの決断でした。", "tts_narration": "いちつのけつだんでした。"},
            ]
        }

        issues = inspect_japanese_tts_script(script, JA_CONFIG)

        self.assertEqual(sum(issue.code == "verified_reading_mismatch" for issue in issues), 4)
        with self.assertRaisesRegex(ValueError, "日本語 TTS|일본어 TTS"):
            assert_japanese_tts_script_ready(script, JA_CONFIG)

    def test_preflight_accepts_verified_kana(self):
        script = {
            "cuts": [
                {"cut_number": 1, "narration": "御家人の制度です。", "tts_narration": "ごけにんのせいどです。"},
                {"cut_number": 2, "narration": "野見宿禰が登場します。", "tts_narration": "のみのすくねがとうじょうします。"},
                {"cut_number": 3, "narration": "大火傷を負いました。", "tts_narration": "おおやけどをおいました。"},
                {"cut_number": 4, "narration": "一つの決断でした。", "tts_narration": "ひとつのけつだんでした。"},
            ]
        }

        assert_japanese_tts_script_ready(script, JA_CONFIG)

    def test_verified_source_context_corrects_known_explicit_kana_typo(self):
        script = {
            "cuts": [
                {
                    "cut_number": 134,
                    "narration": "神話最大の兄弟喧嘩の始まりでした。",
                    "tts_narration": "しんわさいだいのきょうだいげんかのはじまりでした。",
                }
            ]
        }

        prepared = prepare_script_tts_inputs(script, JA_CONFIG)[134]

        self.assertIn("きょうだいけんか", prepared.spoken_narration)
        self.assertNotIn("きょうだいげんか", prepared.spoken_narration)
        assert_japanese_tts_script_ready(script, JA_CONFIG)

    def test_verified_source_context_corrects_shitai_explicit_kana_typo(self):
        script = {
            "cuts": [
                {
                    "cut_number": 126,
                    "narration": "なんとその死体から、驚くべき奇跡が起こっていました。",
                    "tts_narration": "なんとそのいたいから、おどろくべききせきがおこっていました。",
                }
            ]
        }

        prepared = prepare_script_tts_inputs(script, JA_CONFIG)[126]

        self.assertIn("そのしたいから", prepared.spoken_narration)
        self.assertNotIn("そのいたいから", prepared.spoken_narration)

    def test_verified_source_context_corrects_mikusa_explicit_kana_typo(self):
        script = {
            "cuts": [
                {
                    "cut_number": 28,
                    "narration": "日本の三種の神器の一つとなります。",
                    "tts_narration": "にほんのみくさのかんどからのひとつとなります。",
                }
            ]
        }

        prepared = prepare_script_tts_inputs(script, JA_CONFIG)[28]

        self.assertIn("みくさのかむたから", prepared.spoken_narration)
        self.assertNotIn("みくさのかんどから", prepared.spoken_narration)
        assert_japanese_tts_script_ready(script, JA_CONFIG)
        assert_japanese_tts_script_ready(script, JA_CONFIG)

    def test_explicit_genka_is_not_changed_without_verified_source_context(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "減価について説明します。",
                    "tts_narration": "げんかについてせつめいします。",
                }
            ]
        }

        prepared = prepare_script_tts_inputs(script, JA_CONFIG)[1]

        self.assertIn("げんか", prepared.spoken_narration)

    def test_person_counter_guard_does_not_break_grammar_terms(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "一人称と二人称を比較します。",
                    "tts_narration": "いちにんしょうとににんしょうをひかくします。",
                }
            ]
        }

        assert_japanese_tts_script_ready(script, JA_CONFIG)
        spoken = prepare_spoken_narration_for_tts(script["cuts"][0]["narration"], "ja")
        self.assertIn("いちにんしょう", spoken)
        self.assertIn("ににんしょう", spoken)

    def test_preflight_rejects_unrelated_explicit_tts(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "古代日本では新しい政治制度が始まりました。",
                    "tts_narration": "まったくかんけいのないべつのぶんしょうです。",
                }
            ]
        }

        issues = inspect_japanese_tts_script(script, JA_CONFIG)

        self.assertIn("source_tts_alignment", {issue.code for issue in issues})


class JapaneseTTSRequestAndCacheTests(unittest.TestCase):
    def _prepared(self):
        script = {
            "cuts": [
                {"cut_number": 1, "narration": "最初の説明です。", "tts_narration": "さいしょのせつめいです。"},
                {"cut_number": 2, "narration": "御家人が登場します。", "tts_narration": "ごけにんがとうじょうします。"},
                {"cut_number": 3, "narration": "最後の説明でした。", "tts_narration": "さいごのせつめいでした。"},
            ]
        }
        return prepare_script_tts_inputs(script, JA_CONFIG)[2]

    def test_prepared_cut_carries_neighbor_context(self):
        prepared = self._prepared()

        self.assertEqual(prepared.previous_text, "さいしょのせつめいです。")
        self.assertEqual(prepared.next_text, "さいごのせつめいでした。")
        self.assertEqual(prepared.spoken_narration, "ごけにんがとうじょうします。")

    def test_elevenlabs_v3_payload_omits_unsupported_text_normalization(self):
        prepared = self._prepared()
        config = {
            **JA_CONFIG,
            "elevenlabs_pronunciation_dictionary_locators": [
                {"pronunciation_dictionary_id": "dict-1", "version_id": "version-1"}
            ],
        }
        context = build_tts_request_context(prepared, config)

        payload = ElevenLabsService._build_request_payload(
            prepared.spoken_narration,
            {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0},
            context,
        )

        self.assertEqual(payload["language_code"], "ja")
        self.assertNotIn("apply_language_text_normalization", payload)
        self.assertNotIn("previous_text", payload)
        self.assertNotIn("next_text", payload)
        self.assertEqual(
            payload["pronunciation_dictionary_locators"],
            [{"pronunciation_dictionary_id": "dict-1", "version_id": "version-1"}],
        )

    def test_elevenlabs_non_v3_payload_keeps_text_normalization(self):
        class MultilingualV2Service(ElevenLabsService):
            engine_model_id = "eleven_multilingual_v2"

        payload = MultilingualV2Service._build_request_payload(
            "ごけにんがとうじょうします。",
            {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0},
            {
                "language_code": "ja",
                "apply_language_text_normalization": True,
                "previous_text": "まえのぶんです。",
                "next_text": "つぎのぶんです。",
            },
        )

        self.assertIs(payload["apply_language_text_normalization"], True)
        self.assertEqual(payload["previous_text"], "まえのぶんです。")
        self.assertEqual(payload["next_text"], "つぎのぶんです。")

    def test_narration_fit_forwards_request_context(self):
        class CapturingService:
            def __init__(self):
                self.context = None

            async def generate(
                self,
                text,
                voice_id,
                output_path,
                speed=1.0,
                voice_settings=None,
                request_context=None,
            ):
                self.context = request_context
                Path(output_path).write_bytes(b"audio")
                return {"path": output_path, "duration": 0.0}

        service = CapturingService()
        context = {"language_code": "ja", "previous_text": "まえ。", "next_text": "つぎ。"}
        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(
                generate_tts_with_auto_narration_fit(
                    service,
                    "ほんぶん。",
                    "voice-a",
                    str(Path(tmp) / "cut.mp3"),
                    speed=1.0,
                    config={"tts_audio_timing_fit": False},
                    language="ja",
                    request_context=context,
                )
            )

        self.assertEqual(service.context, context)

    def test_versioned_marker_invalidates_voice_or_normalizer_changes(self):
        prepared = self._prepared()
        marker_payload = build_tts_input_marker_payload(
            prepared,
            JA_CONFIG,
            provider="elevenlabs",
            engine_model="eleven_v3",
            voice_id="voice-a",
            speed=1.0,
            voice_settings={"stability": 0.5},
        )
        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "cut_002.mp3"
            write_tts_input_marker(audio_path, marker_payload, enabled=True)

            self.assertTrue(tts_input_marker_matches(audio_path, marker_payload, enabled=True))
            changed_voice = {**marker_payload, "voice_id": "voice-b"}
            self.assertFalse(tts_input_marker_matches(audio_path, changed_voice, enabled=True))
            changed_normalizer = {**marker_payload, "normalizer_signature": "ja-v999"}
            self.assertFalse(tts_input_marker_matches(audio_path, changed_normalizer, enabled=True))


class JapaneseShortsClosureTests(unittest.TestCase):
    @staticmethod
    def _script() -> dict:
        cuts = []
        groups = ((20, 34), (45, 59), (70, 84), (100, 114))
        for number in range(1, 151):
            group = next((index for index, bounds in enumerate(groups, start=1) if bounds[0] <= number <= bounds[1]), 0)
            narration = f"これは第{number}の説明でした。"
            if number == 34:
                narration = "しかし、生まれたのは骨のないスライムのような子。"
            elif number == 35:
                narration = "その子は葦の船に乗せられ、海へ流されました。"
            cuts.append({
                "cut_number": number,
                "narration": narration,
                "shorts_candidate": group > 0,
                "shorts_group": group,
                "shorts_score": 8 if group else 0,
            })
        return {"language": "ja", "title": "日本神話", "cuts": cuts}

    def test_dangling_japanese_short_moves_to_next_closed_sentence(self):
        annotated = shorts_service.annotate_script_shorts(self._script())
        group_one = [
            cut["cut_number"]
            for cut in annotated["cuts"]
            if cut.get("shorts_candidate") is True and cut.get("shorts_group") == 1
        ]

        self.assertEqual(group_one, list(range(21, 36)))
        self.assertTrue(
            shorts_service._japanese_shorts_end_is_closed(
                annotated["cuts"][34]["narration"]
            )
        )

    def test_transition_sentence_with_explicit_resolution_is_closed(self):
        self.assertTrue(
            shorts_service._japanese_shorts_end_is_closed(
                "しかし、神々の協力によって問題は解決しました。"
            )
        )
        self.assertFalse(
            shorts_service._japanese_shorts_end_is_closed(
                "しかし、生まれたのは骨のないスライムのような子。"
            )
        )

    def test_punctuationless_finite_japanese_sentence_is_closed(self):
        self.assertTrue(
            shorts_service._japanese_shorts_end_is_closed(
                "ウケモチの死は、食と衣の起源として残りました"
            )
        )
        self.assertTrue(
            shorts_service._japanese_shorts_end_is_closed(
                "しかし、神々の協力によって問題は解決しました"
            )
        )
        self.assertFalse(
            shorts_service._japanese_shorts_end_is_closed(
                "しかし、生まれたのは骨のないスライムのような子"
            )
        )

    def test_punctuationless_japanese_episode_still_selects_four_shorts(self):
        script = {
            "language": "ja",
            "cuts": [
                {
                    "cut_number": number,
                    "narration": f"これは第{number}の説明でした",
                    "shorts_score": number % 10,
                }
                for number in range(1, 151)
            ],
        }

        segments = shorts_service.select_shorts_segments(script)

        self.assertEqual(len(segments), shorts_service.SHORTS_SEGMENT_COUNT)
        spans = [
            set(range(int(segment["start_cut"]), int(segment["end_cut"]) + 1))
            for segment in segments
        ]
        self.assertTrue(all(len(span) == shorts_service.SHORTS_CUT_COUNT for span in spans))
        self.assertEqual(
            [set(segment.get("cut_numbers") or []) for segment in segments],
            spans,
        )
        self.assertTrue(
            all(not left.intersection(right) for index, left in enumerate(spans) for right in spans[index + 1:])
        )

    def test_episode_07_shorts_headlines_are_strong_and_unique(self):
        segment_texts = [
            (
                "月の神ツクヨミが遣わされます 神の食卓は、ここで殺しの場に変わりました "
                "鋭い石の刃が命を断ち、ウケモチは倒れました"
            ),
            (
                "桑の葉の上で白い蚕が静かにうごきます 死の場なのに命の気配がふえ、"
                "芽吹く穀物が見えてきます"
            ),
            (
                "稲は米として人の腹を満たします 蚕は絹へつながり、"
                "からだから衣のもとまで出ました"
            ),
            (
                "散らばる種を集め、編み皿に拾います 種は田へ向かい、"
                "若い稲の列で農のはじまりを語ります"
            ),
        ]
        expected = [
            ("神の食卓で殺害", "女神に何が起きた"),
            ("死体から米と蚕", "神話最大の異変"),
            ("女神の体が田畑に", "食と衣の起源"),
            ("死体の種を拾った", "人類初の農業へ"),
        ]

        actual = [
            shorts_service._japanese_action_headline(text, text)
            for text in segment_texts
        ]

        self.assertEqual(actual, expected)
        self.assertEqual(len(set(actual)), 4)


if __name__ == "__main__":
    unittest.main()
