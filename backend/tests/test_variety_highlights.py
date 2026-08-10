import asyncio
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.subtitle_service import (
    VARIETY_HIGHLIGHT_ALIGNMENT,
    VARIETY_HIGHLIGHT_FONT_SCALE,
    VARIETY_HIGHLIGHT_PANELS,
    VARIETY_HIGHLIGHT_X_RATIO,
    VARIETY_HIGHLIGHT_Y_RATIO,
    VARIETY_HERO_BASE_FONT_SIZE,
    VARIETY_HERO_FONT,
    VARIETY_HERO_OUTLINE,
    VARIETY_HERO_OUTER_OUTLINE,
    VARIETY_HERO_SHADOW,
    VARIETY_HERO_TAG_COLORS,
    VARIETY_TAG_TO_PANEL,
    burn_cut_variety_highlight_file,
    generate_variety_highlight_ass,
    resolve_variety_highlight_panel,
)


EXPECTED_PANEL_TAGS = {
    "neutral": {"slowly", "flatly", "thoughtful", "softly"},
    "epic": {"dramatic", "booming"},
    "anger": {"angry", "annoyed", "upset"},
    "shout": {"shouts"},
    "whisper": {"quietly", "whispers"},
    "tension": {"worried", "rushed", "nervously", "stammers"},
    "sad": {"sorrowful", "crying", "sighs"},
    "shock": {"surprised", "gasps", "curious", "questioning"},
    "sly": {"mischievously", "sarcastic"},
    "joy": {"happily", "excited", "laughs", "giggle"},
}


def _style_rows(ass: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in ass.splitlines():
        if not line.startswith("Style: Variety_"):
            continue
        fields = line.removeprefix("Style: ").split(",")
        rows[fields[0].removeprefix("Variety_")] = fields
    return rows


def _fixed_panel_ass(panel_id: str) -> str:
    return generate_variety_highlight_ass(
        [{
            "cut_number": 1,
            "narration": "사건의 핵심 단서가 드러났습니다.",
            "highlight_caption": "사건의 핵심 단서",
            "cut_video_duration": 2,
            "tts_tags": ["angry"],
        }],
        panel_mode="fixed",
        fixed_panel=panel_id,
    )


def _fixed_panel_event(panel_id: str) -> tuple[str, str]:
    ass = _fixed_panel_ass(panel_id)
    events = [line for line in ass.splitlines() if line.startswith("Dialogue:")]
    event = next(line for line in events if f",Variety_{panel_id}," in line)
    overrides = [
        match.group(1)
        for line in events
        for match in re.finditer(r"\{([^}]*)\}", line)
    ]
    return event, "|".join(overrides)


class VarietyHighlightTests(unittest.TestCase):
    def test_cut_burn_skips_plain_dialogue_without_explicit_variety_caption(self):
        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "cut_001.mp4"
            video.write_bytes(b"video")
            with patch(
                "app.services.video.ffmpeg_service.FFmpegService.burn_subtitles",
                new_callable=AsyncMock,
            ) as burn:
                result = asyncio.run(burn_cut_variety_highlight_file(
                    str(video),
                    {"narration": "기본 대사만 있습니다."},
                    duration=4.0,
                ))

            self.assertFalse(result)
            burn.assert_not_awaited()

    def test_cut_burn_uses_only_explicit_korean_variety_caption(self):
        captured_ass = ""

        async def fake_burn(input_path: str, ass_path: str, output_path: str):
            nonlocal captured_ass
            captured_ass = Path(ass_path).read_text(encoding="utf-8")
            shutil.copyfile(input_path, output_path)

        with tempfile.TemporaryDirectory() as td:
            video = Path(td) / "cut_001.mp4"
            video.write_bytes(b"video")
            with (
                patch(
                    "app.services.video.ffmpeg_service.FFmpegService.probe_duration",
                    new=AsyncMock(return_value=4.0),
                ),
                patch(
                    "app.services.video.ffmpeg_service.FFmpegService.burn_subtitles",
                    new=fake_burn,
                ),
            ):
                result = asyncio.run(burn_cut_variety_highlight_file(
                    str(video),
                    {
                        "narration": "기본 대사는 화면에 나오면 안 됩니다.",
                        "highlight_caption": "한국 예능 핵심 자막",
                        "tts_tags": ["surprised"],
                    },
                    duration=4.0,
                ))

            self.assertTrue(result)
            self.assertIn("한국 예능 핵심 자막", captured_ass)
            self.assertNotIn("기본 대사는 화면에 나오면 안 됩니다.", captured_ass)
            self.assertIn(",Variety_shock,", captured_ass)

    def test_ten_panels_cover_every_registered_ch4_tag(self):
        self.assertEqual(len(VARIETY_HIGHLIGHT_PANELS), 10)
        self.assertEqual(set(VARIETY_HIGHLIGHT_PANELS), set(EXPECTED_PANEL_TAGS))

        registered_tags = [
            tag
            for panel in VARIETY_HIGHLIGHT_PANELS.values()
            for tag in panel["tags"]
        ]
        expected_tags = set().union(*EXPECTED_PANEL_TAGS.values())
        self.assertEqual(len(registered_tags), 29)
        self.assertEqual(len(registered_tags), len(set(registered_tags)))
        self.assertEqual(set(VARIETY_TAG_TO_PANEL), expected_tags)

        for panel_id, tags in EXPECTED_PANEL_TAGS.items():
            with self.subTest(panel=panel_id):
                self.assertEqual(set(VARIETY_HIGHLIGHT_PANELS[panel_id]["tags"]), tags)
                for tag in tags:
                    self.assertEqual(VARIETY_TAG_TO_PANEL[tag], panel_id)
                    self.assertEqual(resolve_variety_highlight_panel([tag]), panel_id)

    def test_first_registered_tag_wins_and_fixed_mode_overrides(self):
        self.assertEqual(resolve_variety_highlight_panel(["angry", "shouts"]), "anger")
        self.assertEqual(resolve_variety_highlight_panel([" shouts ", "ANGRY"]), "shout")
        self.assertEqual(resolve_variety_highlight_panel(["unknown"]), "neutral")
        self.assertEqual(resolve_variety_highlight_panel([]), "neutral")
        self.assertEqual(
            resolve_variety_highlight_panel(["angry"], panel_mode="fixed", fixed_panel="joy"),
            "joy",
        )
        self.assertEqual(
            resolve_variety_highlight_panel(["angry"], panel_mode="fixed", fixed_panel="missing"),
            "neutral",
        )

    def test_ass_declares_ten_panels_and_uses_emotion_style(self):
        ass = generate_variety_highlight_ass([
            {
                "cut_number": 2,
                "narration": "대체 무슨 일이 벌어진 걸까요?",
                "highlight_caption": "대체 무슨 일?",
                "cut_video_duration": 2,
                "tts_tags": ["surprised", "gasps"],
            },
        ])
        self.assertEqual(ass.count("Style: Variety_"), 10)
        self.assertIn("Dialogue: 5,0:00:00.50,0:00:01.50,Variety_shock", ass)

    def test_variety_panel_uses_source_cut_window_with_half_second_padding(self):
        ass = generate_variety_highlight_ass([
            {
                "cut_number": 1,
                "highlight_caption": "컷 전체 유지",
                "cut_video_duration": 6,
            },
        ])
        self.assertIn("Dialogue: 5,0:00:00.50,0:00:05.50,Variety_neutral", ass)

    def test_fixed_mode_can_render_every_panel_without_emotion_remapping(self):
        for panel_id in VARIETY_HIGHLIGHT_PANELS:
            with self.subTest(panel=panel_id):
                event, _override = _fixed_panel_event(panel_id)
                self.assertIn(f",Variety_{panel_id},", event)

    def test_all_panels_render_bottom_center_at_one_point_five_font_size(self):
        styles = _style_rows(generate_variety_highlight_ass([]))
        expected_x = round(1920 * VARIETY_HIGHLIGHT_X_RATIO)
        expected_y = round(1080 * VARIETY_HIGHLIGHT_Y_RATIO)

        expected_size = int(VARIETY_HERO_BASE_FONT_SIZE * VARIETY_HIGHLIGHT_FONT_SCALE + 0.5)
        for panel_id in VARIETY_HIGHLIGHT_PANELS:
            with self.subTest(panel=panel_id):
                fields = styles[panel_id]
                self.assertEqual(int(fields[2]), expected_size)
                self.assertEqual(fields[1], VARIETY_HERO_FONT)
                self.assertEqual(int(fields[16]), VARIETY_HERO_OUTLINE)
                self.assertEqual(int(fields[17]), VARIETY_HERO_SHADOW)
                self.assertEqual(int(fields[18]), VARIETY_HIGHLIGHT_ALIGNMENT)
                self.assertEqual(fields[19:22], ["50", "50", "92"])

                event, _override = _fixed_panel_event(panel_id)
                motion = re.search(r"\{([^}]*)\}", event)
                self.assertIsNotNone(motion)
                tags = motion.group(1) if motion else ""
                self.assertIn(rf"\an{VARIETY_HIGHLIGHT_ALIGNMENT}", tags)
                position = re.search(r"\\pos\((-?\d+),(-?\d+)\)", tags)
                self.assertIsNotNone(position, tags)
                final_x, final_y = int(position.group(1)), int(position.group(2))
                self.assertEqual((final_x, final_y), (expected_x, expected_y))

    def test_auto_and_fixed_modes_share_the_same_panel_emitter(self):
        cut = [{
            "cut_number": 1,
            "narration": "마침내 숨겨진 반전이 드러났습니다.",
            "highlight_caption": "숨겨진 반전",
            "cut_video_duration": 2,
            "tts_tags": ["mischievously"],
        }]
        auto_ass = generate_variety_highlight_ass(cut, panel_mode="emotion_auto")
        fixed_ass = generate_variety_highlight_ass(
            cut,
            panel_mode="fixed",
            fixed_panel="sly",
        )

        self.assertEqual(auto_ass, fixed_ass)

    def test_marked_keyword_is_cleaned_and_gets_panel_emphasis(self):
        ass = generate_variety_highlight_ass(
            [{
                "cut_number": 1,
                "narration": "교황이 모두를 놀라게 했습니다.",
                "highlight_caption": "교황의 **충격 선언**",
                "cut_video_duration": 2,
                "tts_tags": ["surprised"],
            }],
            panel_mode="fixed",
            fixed_panel="shock",
        )
        event = next(
            line for line in ass.splitlines()
            if line.startswith("Dialogue:") and ",Variety_shock," in line
        )

        self.assertNotIn("**", ass)
        self.assertIn("교황의 ", event)
        self.assertIn("충격 선언", event)
        keyword_override = re.search(r"\{([^}]*)\}충격 선언", event)
        self.assertIsNotNone(keyword_override)
        override = keyword_override.group(1) if keyword_override else ""
        self.assertRegex(override, r"\\(?:1?c)&H[0-9A-Fa-f]{6,8}&")
        self.assertNotRegex(override, r"\\fsc[xy]\d+")

    def test_explicit_unmarked_caption_is_preserved_without_keyword_inference(self):
        ass = generate_variety_highlight_ass(
            [{
                "cut_number": 1,
                "narration": "교황청에서 예상하지 못한 결정이 내려졌습니다.",
                "highlight_caption": "교황청에서 예상하지 못한 결정이 내려졌습니다.",
                "cut_video_duration": 2,
                "tts_tags": ["dramatic"],
            }],
        )
        event = next(
            line for line in ass.splitlines()
            if line.startswith("Dialogue:") and ",Variety_epic," in line
        )

        visible_text = re.sub(r"\{[^}]*\}", "", event.rsplit(",,", 1)[-1])
        self.assertEqual(
            visible_text,
            "교황청에서 예상하지 못한 결정이 내려졌습니다.",
        )
        self.assertNotRegex(event, r"\}못한 결정이\{")

    def test_panels_do_not_emit_legacy_graphic_decorations(self):
        for panel_id in VARIETY_HIGHLIGHT_PANELS:
            ass = _fixed_panel_ass(panel_id)
            decorations = [
                line for line in ass.splitlines()
                if line.startswith("Dialogue:") and ",VarietyDecor," in line
            ]
            self.assertFalse(decorations, panel_id)

    def test_ten_panels_share_one_non_color_shorts_hero_contract(self):
        base_ass = generate_variety_highlight_ass([])
        styles = _style_rows(base_ass)
        self.assertEqual(set(styles), set(VARIETY_HIGHLIGHT_PANELS))

        typography_signatures: set[tuple[str, ...]] = set()
        position_signatures: set[tuple[str, ...]] = set()
        decoration_signatures: set[tuple[str, ...]] = set()
        motion_signatures: set[tuple[str, ...]] = set()
        combined_signatures: set[tuple[tuple[str, ...], ...]] = set()

        for panel_id, fields in styles.items():
            self.assertEqual(len(fields), 23, panel_id)
            event, override = _fixed_panel_event(panel_id)

            typography = tuple(fields[index] for index in (1, 2, 7, 8, 11, 12, 13, 14))
            inline_position = tuple(re.findall(
                r"\\(?:an\d+|pos\([^)]*\)|move\([^)]*\)|org\([^)]*\))",
                override,
            ))
            position = tuple(fields[index] for index in (18, 19, 20, 21)) + inline_position
            inline_decoration = tuple(re.findall(
                r"\\(?:bord|shad|blur|be|clip|iclip)[^\\}]*",
                override,
            ))
            decoration = tuple(fields[index] for index in (15, 16, 17)) + inline_decoration
            motion = tuple(re.findall(
                r"\\(?:fad|fade|t|move)\([^)]*\)|"
                r"\\(?:fscx|fscy|frx|fry|frz|fax|fay|alpha|[1-4]a)[^\\}]*",
                override,
            ))

            typography_signatures.add(typography)
            position_signatures.add(position)
            decoration_signatures.add(decoration)
            motion_signatures.add(motion)
            combined_signatures.add((typography, position, decoration, motion))

        self.assertEqual(len(typography_signatures), 1)
        self.assertEqual(len(position_signatures), 1)
        self.assertEqual(len(decoration_signatures), 1)
        self.assertEqual(len(motion_signatures), 1)
        self.assertEqual(len(combined_signatures), 1)
        self.assertEqual(len(VARIETY_HERO_TAG_COLORS), 10)

    def test_generates_sparse_overlay_with_intermission_offset(self):
        ass = generate_variety_highlight_ass(
            [
                {"cut_number": 1, "narration": "첫 번째 핵심입니다.", "cut_video_duration": 2},
                {"cut_number": 2, "narration": "두 번째 내용입니다.", "highlight_caption": "두 번째 핵심", "cut_video_duration": 2},
            ],
            first_intermission_after_cuts=1,
            intermission_every_cuts=4,
            intermission_duration=3,
        )
        self.assertEqual(
            sum(1 for line in ass.splitlines() if line.startswith("Dialogue:") and ",Variety_" in line),
            1,
        )
        self.assertIn("0:00:05.50", ass)
        self.assertIn(r"\pos(960,983)", ass)

    def test_does_not_select_cuts_from_emotion_speaker_or_interval(self):
        ass = generate_variety_highlight_ass(
            [
                {
                    "cut_number": 1,
                    "narration": "감정 태그만 있습니다.",
                    "speaker": "남성1",
                    "tts_tags": ["angry"],
                    "cut_video_duration": 2,
                },
                {
                    "cut_number": 2,
                    "narration": "간격 조건에 걸릴 수 있는 컷입니다.",
                    "cut_video_duration": 2,
                },
            ],
        )

        self.assertFalse(any(
            line.startswith("Dialogue:") and ",Variety_" in line
            for line in ass.splitlines()
        ))

    def test_exact_korean_source_field_is_supported(self):
        ass = generate_variety_highlight_ass([
            {
                "cut_number": 1,
                "narration": "원문 대사입니다.",
                "한국식 예능 자막 (주요 장면용)": "대본에 직접 쓴 자막",
                "cut_video_duration": 2,
                "tts_tags": ["surprised"],
            }
        ])

        self.assertIn("대본에 직접 쓴 자막", ass)
        self.assertIn(",Variety_shock,", ass)


if __name__ == "__main__":
    unittest.main()
