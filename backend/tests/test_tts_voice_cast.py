import unittest

from app.services.tts.voice_cast import apply_emotion_to_tts_text, resolve_tts_voice


CONFIG = {
    "tts_voice_id": "narrator",
    "tts_voice_male_1_id": "male-1",
    "tts_voice_male_2_id": "male-2",
    "tts_voice_female_1_id": "female-1",
    "tts_voice_female_2_id": "female-2",
}


class TTSVoiceCastTests(unittest.TestCase):
    def test_role_tag_selects_its_configured_voice(self):
        cases = (("남성1 샤세네", "male_1", "male-1"), ("남자2", "male_2", "male-2"), ("여성1 요안나", "female_1", "female-1"), ("여자2", "female_2", "female-2"))
        for speaker, role, voice_id in cases:
            with self.subTest(speaker=speaker):
                resolved = resolve_tts_voice({"speaker": speaker}, CONFIG)
                self.assertEqual((resolved.role, resolved.voice_id), (role, voice_id))

    def test_explicit_voice_role_selects_voice_for_clean_character_name(self):
        resolved = resolve_tts_voice({"speaker": "샤세네", "voice_role": "male_1"}, CONFIG)
        self.assertEqual((resolved.role, resolved.voice_id), ("male_1", "male-1"))

    def test_untagged_character_and_narrator_use_narrator_voice(self):
        for speaker in ("", "해설자", "스테파노 6세"):
            with self.subTest(speaker=speaker):
                resolved = resolve_tts_voice({"speaker": speaker}, CONFIG)
                self.assertEqual((resolved.role, resolved.voice_id), ("narrator", "narrator"))

    def test_explicit_character_mapping_selects_configured_voice(self):
        config = {
            **CONFIG,
            "tts_character_voice_map": {
                "스테파노 6세": "male_1",
                "아겔트루다": "female_1",
                "변호 부제": "male_2",
            },
        }
        cases = (("스테파노 6세", "male_1", "male-1"), ("아겔트루다", "female_1", "female-1"), ("변호 부제", "male_2", "male-2"))
        for speaker, role, voice_id in cases:
            with self.subTest(speaker=speaker):
                resolved = resolve_tts_voice({"speaker": speaker}, config)
                self.assertEqual((resolved.role, resolved.voice_id), (role, voice_id))

    def test_direct_character_voice_id_map_has_priority(self):
        config = {
            **CONFIG,
            "tts_character_voice_ids": {"소벌공": "sobeol-voice"},
        }
        resolved = resolve_tts_voice(
            {
                "speaker": "소벌공",
                "voice_generation_mode": "DIALOGUE",
            },
            config,
        )
        self.assertEqual((resolved.role, resolved.voice_id), ("character", "sobeol-voice"))

    def test_dialogue_without_dedicated_voice_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "전용 voice_id"):
            resolve_tts_voice(
                {
                    "speaker": "소벌공",
                    "voice_generation_mode": "DIALOGUE",
                },
                CONFIG,
            )

    def test_elevenlabs_gets_existing_and_korean_emotion_tags(self):
        resolved = resolve_tts_voice({"speaker": "남성1", "emotion": "분출하는 분노, 핏발 선 서늘한 고함"}, CONFIG)
        self.assertEqual(resolved.emotion_tags, ("angry", "shouts"))
        self.assertEqual(apply_emotion_to_tts_text("물러나라.", resolved, "elevenlabs"), "[angry] [shouts] 물러나라.")
        explicit = resolve_tts_voice({"speaker": "여성1", "emotion": "[sarcastic] [whispers]"}, CONFIG)
        self.assertEqual(apply_emotion_to_tts_text("아닙니다.", explicit, "elevenlabs"), "[sarcastic] [whispers] 아닙니다.")

    def test_registered_tts_tags_override_legacy_emotion_parsing(self):
        resolved = resolve_tts_voice({
            "speaker": "해설자",
            "emotion": "분출하는 분노, 핏발 선 서늘한 고함",
            "tts_tags": ["angry", "shouts"],
        }, CONFIG)
        self.assertEqual(resolved.emotion_tags, ("angry", "shouts"))
        neutral = resolve_tts_voice({"speaker": "해설자", "emotion": "분노", "tts_tags": []}, CONFIG)
        self.assertEqual(neutral.emotion_tags, ())

    def test_other_provider_keeps_clean_narration(self):
        resolved = resolve_tts_voice({"speaker": "남성1", "emotion": "[angry]"}, CONFIG)
        self.assertEqual(apply_emotion_to_tts_text("테스트", resolved, "local"), "테스트")
