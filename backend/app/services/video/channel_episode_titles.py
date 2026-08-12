"""Reviewed display titles for channel-specific long-form overlays."""
from __future__ import annotations

import re


CH3_EPISODE_TITLES_JA = {
    15: "八つの酒樽とクシナダヒメ",
    16: "怪物の尾から現れた神剣",
    17: "ヤマタノオロチの正体",
    18: "オオクニヌシと毛をむしられたウサギ",
    19: "奪われた国と出雲大社の四拍手",
    20: "高天原の武力示威とタケミカヅチ",
    21: "天孫降臨、高千穂に降りた神の孫",
    22: "三本足のカラス、ヤタガラス",
    23: "熊野の大熊と呪術の剣",
    24: "初代天皇、神武の即位",
    25: "殉死に代えて埴輪を埋めよ",
    26: "鍵穴形の巨大古墳、前方後円墳",
    27: "天皇の権力は水から生まれた？",
    28: "勝者の記録、『古事記』の真の目的",
    29: "列島に現れた新羅の王子",
    30: "「学問の神」菅原道真の血脈",
    31: "加耶の鉄と土器が日本を変えた",
    32: "品部、日本経済を築いた技術集団",
    33: "大規模インフラの始まり、百済の敷葉工法",
    34: "「くだらない」、百済のものが最高だ",
    35: "文字を伝えた阿直岐と王仁博士",
    36: "仏教を巡る古代豪族の血戦",
    37: "黒幕の実力者、百済系貴族・藤原鎌足",
    38: "怨霊信仰のルーツは韓国の巫俗？",
    39: "渡来人の移住禁止と忘れられた祖先の国",
    40: "総決算――神話と史実の狭間にある韓半島",
}


_HANGUL_RE = re.compile(r"[\uac00-\ud7a3]")
_JAPANESE_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff々]")


def resolve_channel_episode_title(
    channel_id: int | None,
    episode_number: int | None,
) -> str:
    try:
        channel = int(channel_id or 0)
        episode = int(episode_number or 0)
    except (TypeError, ValueError):
        return ""
    if channel == 3:
        return CH3_EPISODE_TITLES_JA.get(episode, "")
    return ""


def validate_channel_title_language(title: str, channel_id: int | None) -> str:
    clean = re.sub(r"\s+", " ", str(title or "")).strip()
    if int(channel_id or 0) == 3:
        if _HANGUL_RE.search(clean):
            raise ValueError(f"CH3 long-form title contains Hangul: {clean!r}")
        if not _JAPANESE_RE.search(clean):
            raise ValueError(f"CH3 long-form title is not Japanese: {clean!r}")
    return clean
