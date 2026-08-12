from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.sync_variety_captions_to_prepared import (  # noqa: E402
    _caption_errors,
    _normalize_narration,
)


def test_korean_caption_contract_accepts_10_to_15_visible_characters():
    assert _caption_errors("76년 만의 **한강** 수복", "CH1") == []
    assert "visible_length=7" in _caption_errors("**한강** 되찾는다", "CH1")


def test_japanese_caption_contract_rejects_korean_mixing():
    assert _caption_errors("酒に酔った**大蛇**の最期", "CH3") == []
    assert "mixed_korean" in _caption_errors("酒に酔った**대사**の最期", "CH3")


def test_ch4_narration_comparison_ignores_only_leading_audio_tags():
    assert _normalize_narration("[whispers] [slowly] 진실이 드러났다.", "CH4") == "진실이 드러났다."
    assert _normalize_narration("진실이 [whispers] 드러났다.", "CH4") == "진실이 [whispers] 드러났다."


def test_ch3_narration_comparison_ignores_japanese_token_spacing():
    assert _normalize_narration("巨大 な 八つ の 尻尾", "CH3") == _normalize_narration(
        "巨大 な 八 つ の 尻尾",
        "CH3",
    )
