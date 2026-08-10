from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tasks.pipeline_tasks import (
    _filter_prepared_script_quality_issues,
    _is_prepared_script_payload,
)
from app.routers.image import _build_image_prompt
from app.services.image.prompt_compiler import SCENE_CONTRACT_V2, compile_image_prompt
from app.services.llm.visual_policy import apply_script_visual_policy, normalize_cut_image_prompt
from scripts.ch1_baekje_workbook_to_prepared_scripts import (
    _EP01_PUNGNAP_ARCHAEOLOGY_SOURCES,
    _EP03_DIALOGUE_QA_SOURCES,
    _EP03_FULL_FRAME_QA_SOURCES,
    _EP03_GEUNCHOGO_PREVIEW_SOURCES,
    _ep03_full_frame_qa_location,
    _ep03_full_frame_qa_scene,
    _resolve_cut_visual_context,
    _shorts_fields,
    clean_image_prompt,
)


class BaekjePreparedScriptConverterTest(unittest.TestCase):
    def test_clean_image_prompt_removes_generated_korean_context(self):
        narration = "왕이 성문을 열었습니다."
        raw = (
            "A Baekje king stands before a timber gate. "
            "Setting: 475년; 백제·고구려; 한성. "
            "Narration beat for visual context only: 왕이 성문을 열었습니다. "
            "Korean historical-documentary image, period-accurate material culture, "
            "cinematic 16:9 composition, no readable text."
        )

        cleaned, was_cleaned = clean_image_prompt(raw, narration)

        self.assertTrue(was_cleaned)
        self.assertEqual(
            cleaned,
            "A Baekje king stands before a timber gate. Korean historical-documentary "
            "image, period-accurate material culture, cinematic 16:9 composition, "
            "no readable text.",
        )
        self.assertNotIn(narration, cleaned)

    def test_clean_image_prompt_rejects_unstructured_cjk(self):
        with self.assertRaisesRegex(ValueError, "정리 마커"):
            clean_image_prompt("Ancient gate with 백제 soldiers.", "대사")

    def test_shorts_marker_preserves_group_and_order(self):
        self.assertEqual(_shorts_fields("#4-12"), (True, 4, 12, "#4-12"))
        self.assertEqual(_shorts_fields(""), (False, 0, 0, ""))
        with self.assertRaisesRegex(ValueError, "숏츠 태그 형식 오류"):
            _shorts_fields("#4")

    def test_prepared_script_filter_keeps_source_text_and_drops_generator_heuristics(self):
        issues = [
            "bad grammar pattern at cut 91: 자살했다는 기록은 없습니다.",
            "topic phrase repeated too often: 도미 부인=18",
            "non-English text in image_prompt at cut 1",
            "narration copied into image_prompt at cut 2",
        ]

        filtered = _filter_prepared_script_quality_issues(issues)

        self.assertEqual(
            filtered,
            [
                "non-English text in image_prompt at cut 1",
                "narration copied into image_prompt at cut 2",
            ],
        )
        self.assertTrue(_is_prepared_script_payload({"prepared_source": True}))
        self.assertTrue(_is_prepared_script_payload({"script_version": "prepared-1.0"}))
        self.assertFalse(_is_prepared_script_payload({"script_version": "3.1"}))

    def test_source_locked_visual_policy_blocks_unrelated_goguryeo_repair(self):
        narration = "백강이라는 지명의 정확한 비정에는 설명이 필요하지만,"
        raw_scene = (
            "Baek Ga being escorted under guard toward the Baek River as royal officials "
            "witness the end of the rebellion."
        )
        script = {
            "visual_policy_mode": "source-locked",
            "visual_world": {
                "time_range": "501 CE",
                "place_scope": "Ungjin and Garimseong Fortress",
                "culture_scope": "Baekje",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": narration,
                    "image_prompt": raw_scene,
                    "visual_year": "501 CE",
                    "visual_period": "Baekje historical context",
                    "visual_location": "Ungjin and Garimseong Fortress",
                    "visual_evidence": "Source workbook row 11-088 anchors this scene.",
                }
            ],
        }

        processed = apply_script_visual_policy(copy.deepcopy(script))
        prompt = processed["cuts"][0]["image_prompt"]

        self.assertIn(raw_scene, prompt)
        self.assertIn("Time range: 501 CE", prompt)
        self.assertIn("Exact place: Ungjin and Garimseong Fortress", prompt)
        self.assertIn("Scene evidence: Source workbook row 11-088", prompt)
        self.assertNotIn("Sui", prompt)
        self.assertNotIn("612", prompt)
        self.assertEqual(
            apply_script_visual_policy(copy.deepcopy(processed))["cuts"][0]["image_prompt"],
            prompt,
        )
        final_normalized = normalize_cut_image_prompt(
            prompt,
            narration,
            "백제사 11화",
            enable_series_repairs=False,
        )
        self.assertNotIn("Sui", final_normalized)
        self.assertNotIn("612", final_normalized)

    def test_default_cut_context_preserves_episode_metadata(self):
        context = _resolve_cut_visual_context(
            episode_number=1,
            cut_number=1,
            row=10,
            narration="왕위에서 밀려난 왕자가 남쪽으로 내려왔습니다.",
            image_prompt="Onjo leaves Jolbon and travels south.",
            period_en="Late 1st century BC foundation tradition",
            countries_en="Goguryeo, Mahan, and Baekje",
            region_en="Jolbon, the Han River basin, Wirye, Michuhol, Mahan, and Ugok",
        )

        self.assertEqual(
            context["visual_year"],
            "Late 1st century BC foundation tradition",
        )
        self.assertEqual(
            context["visual_period"],
            "Goguryeo, Mahan, and Baekje historical context",
        )
        self.assertEqual(
            context["visual_location"],
            "Jolbon, the Han River basin, Wirye, Michuhol, Mahan, and Ugok",
        )
        self.assertEqual(context["image_prompt"], "Onjo leaves Jolbon and travels south.")

    def test_ep03_preview_rows_override_episode_range_and_match_narration(self):
        for cut_number, source in sorted(_EP03_GEUNCHOGO_PREVIEW_SOURCES.items()):
            with self.subTest(cut_number=cut_number):
                context = _resolve_cut_visual_context(
                    episode_number=3,
                    cut_number=cut_number,
                    row=cut_number + 9,
                    narration=source["narration"],
                    image_prompt={
                        145: "Side-lit court view inside a contested earthwork battlefield, visualizing this decisive historical beat: The person who wielded that tool most aggressively was King Geunchogo. Opposing formations lock into one clash as terrain, shields, and a running messenger reveal cause and consequence. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                        146: "Documentary long-lens view at a historically grounded Baekje settlement, visualizing this decisive historical beat: King Geunchogo expands his southern sphere of influence and advances north. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                        147: "Over-the-shoulder composition within a fortified Goguryeo frontier camp, visualizing this decisive historical beat: As the Baekje army ascended to Pyeongyangseong Fortress, King Gogukwon of Goguryeo also confronted him directly. Envoys exchange one sealed object across measured distance while attendants watch the political reaction. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                        148: "Closing wide composition across a guarded courtyard at the immediate aftermath, visualizing this decisive historical beat: When the king dies in the middle of the battle, the resentment between the two countries hardens into blood. Witnesses hold tense positions around the consequence, making the human cost visible through restrained body language. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                        149: "Reaction-focused medium shot at a historically grounded Baekje settlement, visualizing this decisive historical beat: The 371 years in which Baekje rose to become the most powerful nation on the Korean Peninsula. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                        150: "Closing wide composition across a historically grounded Baekje settlement, visualizing this decisive historical beat: The 371 years in which Baekje rose to become the most powerful nation on the Korean Peninsula, while the immediate aftermath settles into a final held frame. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
                    }[cut_number],
                    period_en="234-286 AD",
                    countries_en="Baekje, Mahan, Lelang Commandery, and Daifang Commandery",
                    region_en="the Han River basin and the central-western Korean Peninsula",
                )

                self.assertTrue(context["source_context_override"])
                self.assertEqual(context["visual_year"], "371 AD")
                self.assertIn("supersedes the episode-wide 234-286 AD", context["visual_evidence"])
                if cut_number == 147:
                    self.assertNotIn("Envoys exchange", context["image_prompt"])
                if cut_number == 148:
                    self.assertNotIn("guarded courtyard", context["image_prompt"])

                processed = apply_script_visual_policy(
                    {
                        "visual_policy_mode": "source-locked",
                        "visual_world": {
                            "time_range": "234-286 AD",
                            "place_scope": "the Han River basin",
                            "culture_scope": "Baekje under King Goi",
                        },
                        "cuts": [{"cut_number": cut_number, "narration": source["narration"], **context}],
                    }
                )
                prompt = processed["cuts"][0]["image_prompt"]
                self.assertIn("Global visual world: Time range: 371 AD", prompt)
                self.assertNotIn("Time range: 234-286 AD", prompt)

    def test_ep03_preview_source_guard_rejects_changed_workbook_row(self):
        with self.assertRaisesRegex(ValueError, "원본 변경 감지"):
            _resolve_cut_visual_context(
                episode_number=3,
                cut_number=147,
                row=156,
                narration="변경된 대사",
                image_prompt="changed scene",
                period_en="234-286 AD",
                countries_en="Baekje",
                region_en="the Korean Peninsula",
            )

    def test_ep03_dialogue_qa_rows_are_guarded_and_remove_failed_visuals(self):
        source_prompts = {
            1: "Low tracking view through a guarded Baekje audience hall, visualizing this decisive historical beat: The young king was pushed out because he found it difficult to hold the throne. A royal seal, guarded doorway, and shifting court posture make the change of power immediately legible. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            18: "Dynamic diagonal frame across a quiet archive table beside a weathered chronicle, visualizing this decisive historical beat: King Goi, who succeeded him, is recorded as King Chogo's younger brother. One physical record anchors the frame while two observers compare its details with restrained gestures. King Goi keeps a square mature face, trimmed beard, black court cap, and deep red robe. Historical-documentary realism, tactile paper and wood, controlled side light, 50mm lens, cinematic 16:9.",
            34: "Tight profile composition in a historically grounded Baekje settlement, visualizing this decisive historical beat: Ma Han has a track record of defeating the highest official of China's military and county. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            51: "Restrained backlit silhouette at a historically grounded Baekje settlement, visualizing this decisive historical beat: Incorporating neighboring powers into the kingdom does not end with just taking over land. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            67: "Close material-detail composition in a guarded Baekje audience hall, visualizing this decisive historical beat: Jwapyeong was in charge of government affairs under the king and represented the noble council. A royal seal, guarded doorway, and shifting court posture make the change of power immediately legible. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            84: "Wide establishing view across a historically grounded Baekje settlement, visualizing this decisive historical beat: The detailed order, including Dalsol, Eunsol, and Deoksol, is written below the left side. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            100: "Side-lit court view inside a historically grounded Baekje settlement, visualizing this decisive historical beat: The king's law can only be established if those who break the rules can be punished, zero matter how high their status. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            117: "Over-the-shoulder composition within a historically grounded Baekje settlement, visualizing this decisive historical beat: A nation is not a machine that can be completed with a single command from a king. Focused gestures, one decisive object, and surrounding reactions make the immediate historical stakes readable. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
            133: "Closing wide composition across a working Baekje craft yard, visualizing this decisive historical beat: King Goi's real weapon was not a sword but a chain of command. Craftspeople handle one period object as tools, surfaces, and nearby reactions reveal its practical value. King Goi keeps a square mature face, trimmed beard, black court cap, and deep red robe. Early Korean state-formation realism, grounded materials, natural directional light, 35mm lens, cinematic 16:9.",
        }
        forbidden_lexemes = {
            1: ("grappl", "map", "manuscript", "seal", "label", "readable text", "artifact"),
            18: ("archive", "chronicle", "genealogy", "map", "label", "readable text", "artifact"),
            34: ("trophy", "map", "document", "label", "readable text", "artifact"),
            51: ("silhouette", "map", "deed", "label", "readable text", "artifact"),
            67: ("royal seal", "map", "document", "label", "readable text", "artifact"),
            84: ("aerial", "chart", "roster", "label", "readable text", "artifact"),
            100: ("tablet", "document", "label", "readable text", "artifact"),
            117: ("machine", "map", "document", "label", "readable text", "artifact"),
            133: ("chain", "sword", "weapon", "craft", "map", "document", "label", "readable text", "artifact"),
        }

        for cut_number, source in sorted(_EP03_DIALOGUE_QA_SOURCES.items()):
            with self.subTest(cut_number=cut_number):
                context = _resolve_cut_visual_context(
                    episode_number=3,
                    cut_number=cut_number,
                    row=cut_number + 9,
                    narration=source["narration"],
                    image_prompt=source_prompts[cut_number],
                    period_en="234-286 AD",
                    countries_en="Baekje, Mahan, Lelang Commandery, and Daifang Commandery",
                    region_en="the Han River basin and the central-western Korean Peninsula",
                )

                self.assertTrue(context["source_context_override"])
                self.assertEqual(context["visual_year"], "234-286 AD")
                lowered_prompt = context["image_prompt"].lower()
                for lexeme in forbidden_lexemes[cut_number]:
                    self.assertNotIn(lexeme, lowered_prompt)
                if cut_number == 1:
                    self.assertIn("walks away alone", lowered_prompt)
                    self.assertIn("isolated young ruler being pushed out", lowered_prompt)
                if cut_number == 34:
                    self.assertIn("governor in a fine pale official robe kneels", lowered_prompt)
                    self.assertIn("standing empty-handed", lowered_prompt)

    def test_ep03_dialogue_qa_source_guard_rejects_changed_workbook_row(self):
        with self.assertRaisesRegex(ValueError, "원본 변경 감지"):
            _resolve_cut_visual_context(
                episode_number=3,
                cut_number=133,
                row=142,
                narration=_EP03_DIALOGUE_QA_SOURCES[133]["narration"],
                image_prompt="changed scene",
                period_en="234-286 AD",
                countries_en="Baekje",
                region_en="the Korean Peninsula",
            )

    def test_ep03_full_frame_qa_rows_are_source_locked_human_actions(self):
        forbidden = (
            "object-only",
            "one decisive object",
            "weathered chronicle",
            "royal seal",
            "artifact display",
            "readable text",
            "lantern",
        )
        self.assertEqual(len(_EP03_FULL_FRAME_QA_SOURCES), 56)
        for cut_number, source in sorted(_EP03_FULL_FRAME_QA_SOURCES.items()):
            with self.subTest(cut_number=cut_number):
                self.assertEqual(len(source["prompt_sha256"]), 64)
                scene = _ep03_full_frame_qa_scene(source["action"]).lower()
                self.assertIn("living adult actors fill the frame", scene)
                self.assertIn("natural attached arms", scene)
                self.assertIn("low featureless earthen", scene)
                location = _ep03_full_frame_qa_location(cut_number).lower()
                self.assertNotIn("courtyard", location)
                self.assertNotIn("hall", location)
                for lexeme in forbidden:
                    self.assertNotIn(lexeme, scene)
                if cut_number == 39:
                    self.assertNotIn("take over one gate", scene)
                    self.assertNotIn("nearby entrance", scene)
                    self.assertIn("only people and bare earth", scene)
                    self.assertIn("no distant background", source["action"].lower())
                    self.assertNotIn("settlement", location)
                    self.assertIn("horizon fully hidden", location)
                    self.assertIn("completely hide the horizon", scene)
                if cut_number in {70, 71}:
                    self.assertIn("no", source["action"].lower())
                    self.assertIn("written mark", scene)
                    self.assertNotIn("guarded doorway", scene)
                if cut_number == 86:
                    self.assertNotIn("jwapyeong", scene)
                    self.assertNotIn("sol-rank", scene)
                    self.assertIn("older court adviser", scene)
                    self.assertIn("open empty hands", scene)
                    self.assertIn("every person is unarmed", scene)
                if cut_number == 88:
                    self.assertIn("functioning human hierarchy", scene)
                    self.assertIn("no pot, jar, vessel, artifact", scene)
                if cut_number == 93:
                    self.assertIn("exactly three separate adult laborers", scene)
                    self.assertIn("exactly three sacks", scene)
                if cut_number == 94:
                    self.assertIn("one pale-robed disgraced former official", scene)
                    self.assertIn("three serving officials keep their backs turned", scene)
                    self.assertIn("nobody marches toward the camera", scene)
                if cut_number == 97:
                    self.assertIn("two escorts lead one pale-robed corrupt collector away", scene)
                    self.assertIn("three honest civilian officials keep receiving grain sacks", scene)
                if cut_number == 111:
                    self.assertIn("one listens to a speaking farmer delegation", scene)
                    self.assertIn("every hand is empty", scene)
                    self.assertIn("no paper, tablet, scroll, book, sign", scene)
                if cut_number == 125:
                    self.assertIn("two groups stop one arm's length apart", scene)
                    self.assertIn("nobody marches toward the camera", scene)
                if cut_number == 138:
                    self.assertIn("two civilian guards restrain the wrists", scene)
                    self.assertIn("an ordered soldier line begins moving away", scene)
                    self.assertIn("no split panel", scene)
                if cut_number == 143:
                    self.assertNotIn("continuous royal chain", scene)
                    self.assertIn("coordinated people and simultaneous duties", scene)
                    self.assertIn("no literal chain, rope, shackle", scene)

    def test_ep03_full_frame_qa_source_guard_rejects_changed_workbook_row(self):
        source = _EP03_FULL_FRAME_QA_SOURCES[77]
        with self.assertRaisesRegex(ValueError, "원본 변경 감지"):
            _resolve_cut_visual_context(
                episode_number=3,
                cut_number=77,
                row=86,
                narration=source["narration"],
                image_prompt="changed scene",
                period_en="234-286 AD",
                countries_en="Baekje",
                region_en="the Korean Peninsula",
            )

    def test_ep01_pungnap_archaeology_rows_remove_ancient_scene_contract(self):
        cases = (
            (
                106,
                115,
                "문헌이 서로 엇갈릴 때, 땅속에서 나온 흔적은 또 다른 시간표를 보여주죠.",
                "ancient manuscripts fade into an archaeological view of Pungnap earthen "
                "fortress beside the Han River in modern Seoul.",
                "Present-day archaeological examination",
            ),
            (
                109,
                118,
                "성벽은 흙을 여러 층으로 다져 쌓았고, 한 번에 만든 작은 마을 울타리가 아니었습니다.",
                "massive rammed-earth walls of Pungnap fortress rise above the river plain, "
                "showing organized labor and defense.",
                "evidence-based visualization",
            ),
            (
                112,
                121,
                "이 흔적은 도시가 어느 날 갑자기 완성되지 않고 오랜 기간 커졌음을 보여줍니다.",
                "archaeologists uncover layered dwellings, pits, kilns, and defensive "
                "features inside Pungnap fortress.",
                "Present-day archaeological examination",
            ),
        )
        ancient_suffix = (
            " Ancient Korean historical drama, cautious early Baekje and Goguryeo "
            "material culture, plain woven garments, timber and packed-earth architecture "
            "where relevant, realistic people, restrained tension, clear staging, wide "
            "establishing shot, directional natural light, 35mm lens, cinematic realism, "
            "no modern objects, no readable text, cinematic 16:9 composition."
        )

        for cut_number, row, narration, scene, expected_period in cases:
            with self.subTest(cut_number=cut_number):
                context = _resolve_cut_visual_context(
                    episode_number=1,
                    cut_number=cut_number,
                    row=row,
                    narration=narration,
                    image_prompt=scene + ancient_suffix,
                    period_en=(
                        "Late 1st century BC foundation tradition through the early reign "
                        "of King Onjo"
                    ),
                    countries_en="Goguryeo, Mahan, and Baekje",
                    region_en=(
                        "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state "
                        "centers, and Ugok Fortress"
                    ),
                )

                self.assertTrue(context["source_context_override"])
                self.assertIn(expected_period, context["visual_year"])
                self.assertIn("Pungnap Toseong", context["visual_location"])
                self.assertIn("present-day Seoul", context["visual_location"])
                self.assertIn(
                    "Present-day South Korean archaeological documentary",
                    context["image_prompt"],
                )
                self.assertNotIn("Ancient Korean historical drama", context["image_prompt"])
                self.assertNotIn("plain woven garments", context["image_prompt"])
                self.assertNotIn("no modern objects", context["image_prompt"])

    def test_ep01_pungnap_source_guard_rejects_changed_workbook_row(self):
        with self.assertRaisesRegex(ValueError, "원본 변경 감지"):
            _resolve_cut_visual_context(
                episode_number=1,
                cut_number=106,
                row=115,
                narration="변경된 대사",
                image_prompt="changed scene",
                period_en="Late 1st century BC foundation tradition",
                countries_en="Goguryeo, Mahan, and Baekje",
                region_en=(
                    "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, "
                    "and Ugok Fortress"
                ),
            )

    def test_ep01_pungnap_final_review_row_uses_archaeology_contract(self):
        context = _resolve_cut_visual_context(
            episode_number=1,
            cut_number=114,
            row=123,
            narration=(
                "풍납토성을 온조가 세운 바로 그 위례성이라고 단정할 증거도 아직 부족합니다."
            ),
            image_prompt=(
                "Eye-level medium shot inside the timber gate of the Wirye settlement, "
                "visualizing this decisive historical beat: There is still insufficient "
                "evidence to conclude that Pungnaptoseong is the very Wiryeseong Fortress "
                "built by Onjo. One physical record anchors the frame while two observers "
                "compare its details with restrained gestures. Onjo keeps a lean young face, "
                "straight brows, tied dark hair, and a crimson-edged plain robe. "
                "Historical-documentary realism, tactile paper and wood, controlled side "
                "light, 50mm lens, cinematic 16:9."
            ),
            period_en="Late 1st century BC foundation tradition",
            countries_en="Goguryeo, Mahan, and Baekje",
            region_en=(
                "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state centers, "
                "and Ugok Fortress"
            ),
        )

        self.assertTrue(context["source_context_override"])
        self.assertIn("archaeologists uncover layered dwellings", context["image_prompt"])
        self.assertIn("Present-day South Korean archaeological", context["image_prompt"])
        self.assertNotIn("Onjo keeps", context["image_prompt"])
        self.assertNotIn("timber gate of the Wirye settlement", context["image_prompt"])

    def test_ep01_pungnap_runtime_compiler_uses_scene_sentence_for_people(self):
        ancient_suffix = (
            " Ancient Korean historical drama, cautious early Baekje and Goguryeo "
            "material culture, plain woven garments, timber and packed-earth architecture "
            "where relevant, realistic people, restrained tension, clear staging, wide "
            "establishing shot, directional natural light, 35mm lens, cinematic realism, "
            "no modern objects, no readable text, cinematic 16:9 composition."
        )
        model_id = "comfyui-flux2-klein-4b"

        for cut_number, (narration, scene, _mode) in sorted(
            _EP01_PUNGNAP_ARCHAEOLOGY_SOURCES.items()
        ):
            with self.subTest(cut_number=cut_number):
                context = _resolve_cut_visual_context(
                    episode_number=1,
                    cut_number=cut_number,
                    row=cut_number + 9,
                    narration=narration,
                    image_prompt=scene + ancient_suffix,
                    period_en=(
                        "Late 1st century BC foundation tradition through the early reign "
                        "of King Onjo"
                    ),
                    countries_en="Goguryeo, Mahan, and Baekje",
                    region_en=(
                        "Jolbon, the Han River basin, Wirye, Michuhol, Mahan state "
                        "centers, and Ugok Fortress"
                    ),
                )
                policy_script = apply_script_visual_policy(
                    {
                        "visual_policy_mode": "source-locked",
                        "visual_world": {
                            "time_range": "Late 1st century BC",
                            "place_scope": "the Han River basin",
                            "culture_scope": "Baekje",
                        },
                        "cuts": [
                            {
                                "cut_number": cut_number,
                                "narration": narration,
                                **context,
                            }
                        ],
                    }
                )
                policy_cut = policy_script["cuts"][0]
                normalized = normalize_cut_image_prompt(
                    policy_cut["image_prompt"],
                    narration,
                    "백제사 EP01",
                    enable_series_repairs=False,
                )
                runtime_source = _build_image_prompt(
                    normalized,
                    "",
                    image_model=model_id,
                    prompt_profile=SCENE_CONTRACT_V2,
                    narration_context=narration,
                )
                compiled = compile_image_prompt(runtime_source, model_id=model_id)

                expected_kind = "group" if cut_number >= 112 else "landscape"
                self.assertEqual(compiled.scene_kind, expected_kind)


if __name__ == "__main__":
    unittest.main()
