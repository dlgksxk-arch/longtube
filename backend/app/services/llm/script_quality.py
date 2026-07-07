"""Script-level quality checks for documentary-style longform episodes."""
from __future__ import annotations

import re
import math
from collections import Counter
from typing import Any


SHORTS_TARGET_GROUPS = 4
SHORTS_MIN_GROUPS = 3
SHORTS_GROUP_CUTS = 15
SHORTS_TARGET_CUTS = SHORTS_TARGET_GROUPS * SHORTS_GROUP_CUTS
SHORTS_MIN_CUTS = SHORTS_MIN_GROUPS * SHORTS_GROUP_CUTS


FORBIDDEN_TEMPLATE_PHRASES: tuple[str, ...] = (
    "압력이 다가옵니다",
    "선택이 좁혀집니다",
    "사건의 온도가 높아집니다",
    "결말의 그림자가 드리웁니다",
    "기록의 빈칸이 말합니다",
    "다음 장면을 차갑게 만듭니다",
    "권위의 출처를 묻습니다",
    "흐름을 남깁니다",
    "그 의미가 작지 않습니다",
    "끝까지 봐야 합니다",
    "기록의 순간",
    "결정적 여파",
    "권력의 장면",
    "사람들은 이 조건 속에서 움직였습니다",
    "다음 결과는 이 움직임에서 나옵니다",
    "기록은 세부 장면보다 방향을 남깁니다",
    "과장 없이 보아도 전환점은 분명합니다",
    "이 단계에서 사건의 무게가 달라집니다",
    "이 지점에서 앞선 질문의 답이 보입니다",
    "후대 인식도 여기서 갈라집니다",
    "그래서 단정 대신 가능성으로 말해야 합니다",
    "정리하면 기록과 해석을 나눠야 보입니다",
    "확실한 내용부터 세우겠습니다",
    "첫 단서는 인물의 움직임을 보여 줍니다",
    "지리와 권위가 함께 작동했습니다",
    "주변 정세가 판단을 바꿨습니다",
    "이제 한계와 해석을 따져야 합니다",
    "이제 질문은 다음 인물과 사건으로 넘어갑니다",
    "이제 사건은 더 구체적인 선택으로 좁혀집니다",
    "이 질문들은 기록과 해석을 가릅니다",
    "이 조심스러운 태도가 결론을 단단하게 만듭니다",
    "이 조건은 사건의 무대를 만듭니다",
    "남은 쟁점은 인물과 제도의 관계입니다",
    "기록이 말한 것과 말하지 않은 것을 계속 나눠 보겠습니다",
    "이 질문은 오늘 주제의 출발점입니다",
    "기록과 해석을 분리해야 답이 보입니다",
    "이 다섯 단서는 오늘 주제를 한 방향으로 묶습니다",
    "이 질문의 세부 과정은 기록만으로 복원하기 어렵습니다",
    "그래서 오늘 주제는 사실과 해석을 나눠야 합니다",
    "배경을 봐야 다음 고리로 이어지는 길도 보입니다",
    "이제 오늘 주제를 정리하겠습니다",
    "이 한계 때문에 다음 주제를 이어서 봐야 합니다",
    "고조선 이야기는 다음 주제에서 더 복잡해집니다",
)

BAD_GRAMMAR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[가-힣A-Za-z0-9_]{2,20}는\s+(?:선택|전개|단서|사람들|압박|기록|사건)은"),
    re.compile(r"(?:에는|에서는)\s+기록은"),
    re.compile(r"(?:에는|에서는)\s+기록에는"),
    re.compile(r"([가-힣]{2,})\s+\1"),
    re.compile(r"그\s+그"),
    re.compile(r"이\s+이탈"),
    re.compile(r"(?:했나|였나|인가|누구였나|무엇인가|어디인가)는"),
    re.compile(r"(?:왜|어떻게|무엇|누구|어디|언제).*(?:나|까)는\s"),
    re.compile(r"[1-9]번째"),
    re.compile(r"[가-힣A-Za-z0-9]+와\s+압박가"),
    re.compile(r"[가-힣A-Za-z0-9]+는\s+[가-힣A-Za-z0-9]+가\s+압박가"),
    re.compile(r"(?:습니다|입니다|됩니다|했습니다|였습니다)(?:라는|을|를)"),
    re.compile(r"(?:습니다|입니다|됩니다|했습니다|였습니다)입니다\b"),
    re.compile(r"(?:습니다|입니다|됩니다|했습니다|였습니다)는\s"),
    re.compile(r"(?:습니다|입니다|됩니다|했습니다|였습니다)\s+때문"),
    re.compile(r"(?:입니다|합니다|됐습니다)이"),
    re.compile(r"(?:동진|수용|집권|결합|공백|대결|함락|선택|기억|상실|고인돌)는\b"),
    re.compile(r"(?:제국|왕국|정권|세력)와\b"),
)

COMMON_TOPIC_WORDS = {
    "고조선",
    "왕검성",
    "사기",
    "한서",
    "위략",
    "기록",
    "사람들",
    "이야기",
    "문제",
    "전쟁",
    "건국",
    "이후",
    "마지막",
    "내부",
    "제국",
    "사신",
}

GENERIC_IMAGE_SUBJECTS = {
    "opening historical question",
    "source evidence",
    "historical background",
    "main event",
    "historical consequence",
    "cautious interpretation",
    "next episode bridge",
}

V31_STORY_CORE_FIELDS = (
    "story_axis",
    "episode_scope",
    "central_question",
    "central_answer",
    "protagonist",
    "goal",
    "obstacle",
    "first_turn",
    "mid_crisis",
    "cost",
    "ending_memory",
)

V31_SCENE_BLOCK_FIELDS = (
    "block_id",
    "cut_range",
    "block_role",
    "block_goal",
    "mini_question",
    "new_information",
    "key_facts",
    "continuity_from_previous",
    "tension",
    "turn",
    "required_script_moves",
    "turn_to_next",
    "visual_rhythm",
    "must_include",
    "must_avoid",
)

V31_FACT_LEDGER_FIELDS = (
    "confirmed_facts",
    "careful_inferences",
    "unknown_or_debated",
    "forbidden_claims",
)

_CUT_RANGE_RE = re.compile(r"^\s*(\d+)\s*[-~–—]\s*(\d+)\s*$")


def _text(value: Any) -> str:
    return str(value or "").strip()


_TOPIC_PARTICLE_RE = re.compile(
    r"(?:했을까|었을까|였을까|을까|했나|할까|일까|인가|인가요|나요|으로|에서|에게|까지|부터|처럼|보다|과|와|은|는|을|를|의|가|에)$"
)
_TOPIC_VERB_STEM_RE = re.compile(r".*(?:했|었|았|였|렸|졌|냈|켰|됐|살았|무너뜨렸)$")
_TOPIC_GENERIC_SUFFIXES = ("편", "이유", "진짜", "의미", "사건", "역사")
_TOPIC_ALIGNMENT_STOPWORDS = {
    "오늘은",
    "이번",
    "에피소드",
    "주제",
    "이야기",
    "내부",
    "과정",
    "시작",
    "결과",
    "기록",
    "세력",
    "왕국",
    "국가",
    "사람들",
    "문제",
    "이유",
    "의미",
    "역사",
    "전쟁",
    "후반부",
    "중심",
    "질문",
    "답변",
    "연도",
    "배경",
    "핵심인물",
    "주요인물",
    "사건의출발",
    "주요사건",
    "갈림길",
    "반전",
    "핵심내용",
    "내용",
    "목표",
    "제목",
    "자연스러운",
    "작성하세요",
    "일본어",
    "내레이션",
    "문장",
    "한자",
    "중심축",
    "주인공",
    "장애물",
    "번이나",
    "무엇",
    "어떻게",
    "어째서",
    "원래",
    "무너뜨렸을까",
    "무너뜨렸",
    "살았을까",
    "살았",
}
_TOPIC_ALIGNMENT_ALLOWED_LABELS = {
    "핵심인물",
    "주요인물1",
    "주요인물2",
    "주요인물3",
    "주요인물",
    "주요사건",
    "사건의출발",
    "갈림길/반전",
    "핵심내용",
}
_TOPIC_ANCHOR_ALIASES = {
    "몽골": ("몽골", "モンゴル", "元", "원"),
    "일본": ("일본", "日本", "にほん", "ニホン"),
    "쿠빌라이": ("쿠빌라이", "フビライ", "クビライ", "忽必烈", "쿠빌라이 칸"),
    "호조": ("호조", "北条", "ほうじょう", "ホウジョウ"),
    "도키무네": ("도키무네", "時宗", "ときむね", "トキムネ"),
    "고려": ("고려", "高麗", "こうらい", "コウライ"),
    "가마쿠라": ("가마쿠라", "鎌倉", "かまくら", "カマクラ"),
    "막부": ("막부", "幕府", "ばくふ", "バクフ"),
    "겐코": ("겐코", "元弘", "元弘の乱", "げんこう", "ゲンコウ"),
    "고다이고": ("고다이고", "後醍醐", "後醍醐天皇", "ごだいご", "ゴダイゴ"),
    "천황": ("천황", "天皇", "てんのう", "テンノウ"),
    "아시카": ("아시카", "足利", "足利尊氏", "あしかが", "アシカガ"),
    "아시카가": ("아시카가", "足利", "足利尊氏", "あしかが", "アシカガ"),
    "다카우지": ("다카우지", "尊氏", "足利尊氏", "たかうじ", "タカウジ"),
    "닛타": ("닛타", "新田", "新田義貞", "にった", "ニッタ"),
    "요시사다": ("요시사다", "義貞", "新田義貞", "よしさだ", "ヨシサダ"),
    "무사": ("무사", "武士", "侍", "ぶし", "ブシ", "さむらい", "サムライ"),
    "고케닌": ("고케닌", "御家人", "ごけにん", "ゴケニン"),
    "미나모토노": ("미나모토노", "源", "源頼朝", "みなもとの", "ミナモトノ"),
    "미나모토": ("미나모토", "源", "源頼朝", "みなもと", "ミナモト"),
    "하카타": ("하카타", "博多", "はかた", "ハカタ"),
    "분에이": ("분에이", "文永", "ぶんえい", "ブンエイ"),
    "고안": ("고안", "弘安", "こうあん", "コウアン"),
    "오닌": ("오닌", "応仁", "応仁の乱", "Onin", "Ōnin"),
    "교토": ("교토", "京都", "Kyoto"),
    "무로마치": ("무로마치", "室町", "Muromachi"),
    "전국시대": ("전국시대", "戦国時代", "戦国", "せんごく", "センゴク", "Sengoku"),
    "센고쿠": ("센고쿠", "戦国時代", "戦国", "せんごく", "センゴク", "Sengoku"),
    "슈고": ("슈고", "守護", "守護大名", "しゅご", "シュゴ", "Shugo"),
    "다이묘": ("다이묘", "大名", "守護大名", "戦国大名", "だいみょう", "ダイミョウ", "Daimyo"),
    "고쿠진": ("고쿠진", "国人", "国人領主", "こくじん", "コクジン", "Kokujin"),
    "쇼군": ("쇼군", "将軍", "shogun", "Shogun"),
    "호소카": ("호소카", "호소카와", "細川", "細川勝元", "Hosokawa"),
    "호소카와": ("호소카와", "細川", "細川勝元", "Hosokawa"),
    "가쓰모토": ("가쓰모토", "勝元", "細川勝元", "Katsumoto"),
    "야마나": ("야마나", "山名", "山名宗全", "Yamana"),
    "소젠": ("소젠", "宗全", "山名宗全", "Sozen", "Sōzen"),
    "요시마사": ("요시마사", "義政", "足利義政", "Yoshimasa"),
    "무사도": ("무사도", "武士道", "ぶしどう", "ブシドウ", "Bushido"),
    "야마가": ("야마가", "山鹿", "山鹿素行", "やまが", "Yamaga"),
    "야마": ("야마", "山鹿", "山鹿素行", "やまが", "Yamaga"),
    "소코": ("소코", "素行", "山鹿素行", "そこう", "Soko", "Sokō"),
    "니토베": ("니토베", "新渡戸", "新渡戸稲造", "にとべ", "Nitobe"),
    "이나조": ("이나조", "稲造", "新渡戸稲造", "いなぞう", "Inazo", "Inazō"),
    "오다": ("오다", "織田", "おだ", "オダ", "Oda"),
    "노부나가": ("노부나가", "信長", "織田信長", "のぶなが", "ノブナガ", "Nobunaga"),
    "노부나": ("노부나", "信長", "織田信長", "のぶなが", "ノブナガ", "Nobunaga"),
    "불교": ("불교", "仏教", "佛教", "ぶっきょう", "ブッキョウ", "Buddhist", "Buddhism"),
    "이시야마": ("이시야마", "石山", "石山本願寺", "いしやま", "イシヤマ", "Ishiyama"),
    "혼간지": ("혼간지", "本願寺", "石山本願寺", "ほんがんじ", "ホンガンジ", "Honganji"),
    "엔랴쿠지": ("엔랴쿠지", "延暦寺", "えんりゃくじ", "エンリャクジ", "Enryakuji"),
    "잇코잇키": ("잇코잇키", "一向一揆", "いっこういっき", "イッコウイッキ", "Ikko Ikki", "Ikkō-ikki"),
    "검지": ("검지", "検地", "けんち", "ケンチ", "land survey"),
    "도검몰수": ("도검몰수", "刀狩り", "かたながり", "カタナガリ", "sword hunt", "weapon collection"),
    "태합검지": ("태합검지", "太閤検地", "たいこうけんち", "タイコウケンチ", "Taiko kenchi"),
    "도요토미": ("도요토미", "豊臣", "豊臣秀吉", "とよとみ", "トヨトミ", "Toyotomi"),
    "히데요시": ("히데요시", "秀吉", "豊臣秀吉", "ひでよし", "ヒデヨシ", "Hideyoshi"),
    "농민": ("농민", "百姓", "農民", "ひゃくしょう", "のうみん", "farmer", "farmers"),
}


def _strip_topic_particle(token: str) -> str:
    value = _TOPIC_PARTICLE_RE.sub("", token.strip())
    if value.endswith("이") and len(value) > 3 and not value.endswith(("라이", "타이")):
        value = value[:-1]
    return value


def _topic_tokens(text: str) -> list[str]:
    if not text:
        return []
    normalized = re.sub(r"[_/|:()\[\]{}.,!?;·\-]", " ", text)
    tokens: list[str] = []
    for token in re.findall(r"[가-힣]{2,12}", normalized):
        token = _strip_topic_particle(token)
        if len(token) < 2:
            continue
        if token.endswith(_TOPIC_GENERIC_SUFFIXES):
            continue
        tokens.append(token)
    return tokens


def _topic_alignment_tokens(topic: str, config: dict[str, Any] | None = None) -> list[str]:
    sources = [topic]
    cfg = config or {}
    core = _text(cfg.get("episode_core_content"))
    if core:
        for line in core.splitlines():
            match = re.match(r"\s*\[([^\]]+)\]\s*(.+?)\s*$", line)
            if match:
                label = match.group(1).strip()
                value = match.group(2).strip()
                if label in _TOPIC_ALIGNMENT_ALLOWED_LABELS and value:
                    sources.append(value)
            elif line.strip():
                sources.append(line.strip())
    tokens: list[str] = []
    for source in sources:
        normalized = re.sub(r"[_/|:()\[\]{}.,!?;·\-]", " ", _text(source))
        for token in re.findall(r"[가-힣A-Za-z][가-힣A-Za-z0-9]{1,24}", normalized):
            token = _strip_topic_particle(token)
            if len(token) < 2:
                continue
            if re.fullmatch(r"\d+", token):
                continue
            if token in _TOPIC_ALIGNMENT_STOPWORDS:
                continue
            if _TOPIC_VERB_STEM_RE.fullmatch(token):
                continue
            if token.endswith(_TOPIC_GENERIC_SUFFIXES):
                continue
            if token not in tokens:
                tokens.append(token)
    return tokens[:12]


def _story_plan_text(plan: dict[str, Any]) -> str:
    parts: list[str] = []
    visual_world = plan.get("visual_world")
    if isinstance(visual_world, dict):
        parts.extend(_text(value) for value in visual_world.values())
    core = plan.get("story_core")
    if isinstance(core, dict):
        parts.extend(_text(value) for value in core.values())
    character_map = plan.get("character_map")
    if isinstance(character_map, list):
        for item in character_map:
            if isinstance(item, dict):
                parts.extend(_text(value) for value in item.values())
            else:
                parts.append(_text(item))
    causality_chain = plan.get("causality_chain")
    if isinstance(causality_chain, list):
        parts.extend(_text(item) for item in causality_chain)
    fact_ledger = plan.get("fact_ledger")
    if isinstance(fact_ledger, dict):
        for value in fact_ledger.values():
            if isinstance(value, list):
                parts.extend(_text(item) for item in value)
            else:
                parts.append(_text(value))
    visual_plan = plan.get("visual_plan")
    if isinstance(visual_plan, dict):
        parts.extend(_text(value) for value in visual_plan.values())
    blocks = plan.get("scene_blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict):
                parts.extend(_text(value) for value in block.values())
    return "\n".join(part for part in parts if part)


def _inspect_story_plan_topic_alignment(
    plan: dict[str, Any],
    topic: str = "",
    config: dict[str, Any] | None = None,
) -> list[str]:
    anchors = _topic_alignment_tokens(topic, config)
    if not anchors:
        return []
    text = _story_plan_text(plan)
    present = []
    for token in anchors:
        aliases = _TOPIC_ANCHOR_ALIASES.get(token, (token,))
        if any(alias and alias in text for alias in aliases):
            present.append(token)
    required = 1 if len(anchors) <= 2 else 2
    if len(present) < required:
        return [
            "story plan topic alignment failed: "
            f"missing source topic anchors ({', '.join(anchors[:6])})"
        ]
    return []


def _primary_topic_phrases(script: dict[str, Any], topic: str = "") -> list[str]:
    phrases: list[str] = []
    sources = (topic, script.get("topic"), script.get("title"))
    for source in sources:
        tokens = _topic_tokens(_text(source))
        for width in (4, 3, 2):
            if len(tokens) < width:
                continue
            for idx in range(0, len(tokens) - width + 1):
                window = tokens[idx:idx + width]
                if all(token in COMMON_TOPIC_WORDS for token in window):
                    continue
                phrase = " ".join(window)
                if phrase not in phrases:
                    phrases.append(phrase)
    return phrases[:12]


def _topic_phrase_counts(narrations: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for line in narrations:
        tokens = _topic_tokens(line)
        for width in (4, 3, 2):
            if len(tokens) < width:
                continue
            for idx in range(0, len(tokens) - width + 1):
                counts[" ".join(tokens[idx:idx + width])] += 1
    return counts


def _extract_prompt_field(prompt: str, label: str) -> str:
    match = re.search(
        rf"(?:^|[;\n])\s*{re.escape(label)}\s*:\s*([^;]+)",
        prompt,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return match.group(1).strip().lower()


def _is_v31_script(script: dict[str, Any]) -> bool:
    return str(script.get("script_version") or "").strip() == "3.1"


def _inspect_v31_story_contract(script: dict[str, Any], cuts: list[Any]) -> list[str]:
    issues: list[str] = []
    core = script.get("story_core")
    if not isinstance(core, dict):
        issues.append("V3.1 story_core missing")
    else:
        missing = [field for field in V31_STORY_CORE_FIELDS if not _text(core.get(field))]
        if missing:
            issues.append(f"V3.1 story_core missing fields: {','.join(missing)}")

    blocks = script.get("scene_blocks")
    block_ids: set[int] = set()
    block_ranges: dict[int, tuple[int, int]] = {}
    if not isinstance(blocks, list) or not blocks:
        issues.append("V3.1 scene_blocks missing")
    else:
        expected_blocks = math.ceil(len(cuts) / 10) if cuts else 0
        if expected_blocks and len(blocks) != expected_blocks:
            issues.append(f"V3.1 scene_blocks count mismatch: {len(blocks)} expected {expected_blocks}")
        for idx, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                issues.append(f"V3.1 scene_block {idx} is not an object")
                continue
            try:
                block_id = int(block.get("block_id"))
                block_ids.add(block_id)
            except (TypeError, ValueError):
                issues.append(f"V3.1 scene_block {idx} invalid block_id")
                continue
            parsed_range = _parse_cut_range(block.get("cut_range"))
            if parsed_range is None:
                issues.append(f"V3.1 scene_block {idx} invalid cut_range")
            else:
                block_ranges[block_id] = parsed_range
        if block_ranges:
            ordered = sorted((start, end, block_id) for block_id, (start, end) in block_ranges.items())
            expected_start = 1
            for start, end, block_id in ordered:
                if start != expected_start:
                    issues.append(
                        f"V3.1 scene_blocks cut_range gap/overlap before block {block_id}: expected {expected_start}, got {start}"
                    )
                    break
                expected_start = end + 1
            if expected_start != len(cuts) + 1:
                issues.append(f"V3.1 scene_blocks cut_range does not end at {len(cuts)}")

    for idx, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            continue
        try:
            block_id = int(cut.get("scene_block_id"))
        except (TypeError, ValueError):
            issues.append(f"V3.1 cut {idx} missing scene_block_id")
            continue
        if block_ids and block_id not in block_ids:
            issues.append(f"V3.1 cut {idx} scene_block_id not in scene_blocks: {block_id}")
        if block_id in block_ranges:
            start, end = block_ranges[block_id]
            try:
                cut_number = int(cut.get("cut_number") or idx)
            except (TypeError, ValueError):
                cut_number = idx
            if cut_number < start or cut_number > end:
                issues.append(f"V3.1 cut {idx} outside scene_block {block_id} range {start}-{end}")
    return issues


def _parse_cut_range(value: Any) -> tuple[int, int] | None:
    match = _CUT_RANGE_RE.match(_text(value))
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end < start:
        return None
    return start, end


def inspect_story_plan(
    plan: dict[str, Any],
    target_cuts: int = 0,
    topic: str = "",
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Return structural issues for the pre-script V3.1 story plan."""
    issues: list[str] = []
    if not isinstance(plan, dict):
        return ["story plan is not a JSON object"]
    if _text(plan.get("script_version")) != "3.1":
        issues.append("story plan script_version must be 3.1")

    visual_world = plan.get("visual_world")
    if not isinstance(visual_world, dict) or not all(_text(visual_world.get(field)) for field in (
        "time_range",
        "place_scope",
        "culture_scope",
        "material_culture",
        "continuity_rule",
    )):
        issues.append("story plan visual_world missing or incomplete")

    core = plan.get("story_core")
    if not isinstance(core, dict):
        issues.append("story plan story_core missing")
    else:
        missing = [field for field in V31_STORY_CORE_FIELDS if not _text(core.get(field))]
        if missing:
            issues.append(f"story plan story_core missing fields: {','.join(missing)}")

    expected_blocks = math.ceil(target_cuts / 10) if target_cuts > 0 else 0

    character_map = plan.get("character_map")
    if not isinstance(character_map, list) or not character_map:
        issues.append("story plan character_map missing")
    elif len(character_map) != 4:
        issues.append(f"story plan character_map must contain exactly 4 items, got {len(character_map)}")

    causality_chain = plan.get("causality_chain")
    valid_causality = [item for item in causality_chain if _text(item)] if isinstance(causality_chain, list) else []
    if not isinstance(causality_chain, list) or len(valid_causality) < 4:
        issues.append("story plan causality_chain missing or too short")
    elif expected_blocks and len(valid_causality) != expected_blocks:
        issues.append(f"story plan causality_chain count mismatch: {len(valid_causality)} expected {expected_blocks}")
    elif len({_text(item) for item in valid_causality}) != len(valid_causality):
        issues.append("story plan causality_chain contains duplicated items")

    fact_ledger = plan.get("fact_ledger")
    if not isinstance(fact_ledger, dict):
        issues.append("story plan fact_ledger missing")
    else:
        for field in V31_FACT_LEDGER_FIELDS:
            if not isinstance(fact_ledger.get(field), list):
                issues.append(f"story plan fact_ledger.{field} must be a list")
        if not fact_ledger.get("confirmed_facts"):
            issues.append("story plan fact_ledger.confirmed_facts missing")

    visual_plan = plan.get("visual_plan")
    if not isinstance(visual_plan, dict):
        issues.append("story plan visual_plan missing")
    else:
        if not isinstance(visual_plan.get("overall_ratio"), dict):
            issues.append("story plan visual_plan.overall_ratio missing")
        if not isinstance(visual_plan.get("five_cut_rhythm"), list):
            issues.append("story plan visual_plan.five_cut_rhythm missing")

    script_checklist = plan.get("script_checklist")
    if not isinstance(script_checklist, dict):
        issues.append("story plan script_checklist missing")

    if "story_beats" in plan:
        issues.append("story plan must not include story_beats; use scene_blocks only")

    blocks = plan.get("scene_blocks")
    if not isinstance(blocks, list) or not blocks:
        issues.append("story plan scene_blocks missing")
    else:
        if expected_blocks and len(blocks) != expected_blocks:
            issues.append(f"story plan scene_blocks count mismatch: {len(blocks)} expected {expected_blocks}")
        block_ranges: list[tuple[int, int, int]] = []
        seen_block_ids: set[int] = set()
        for idx, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                issues.append(f"story plan scene_block {idx} is not an object")
                continue
            missing = [field for field in V31_SCENE_BLOCK_FIELDS if not _text(block.get(field))]
            if missing:
                issues.append(f"story plan scene_block {idx} missing fields: {','.join(missing)}")
            try:
                block_id = int(block.get("block_id"))
            except (TypeError, ValueError):
                issues.append(f"story plan scene_block {idx} invalid block_id")
                continue
            if block_id in seen_block_ids:
                issues.append(f"story plan duplicate scene_block_id: {block_id}")
            seen_block_ids.add(block_id)
            parsed_range = _parse_cut_range(block.get("cut_range"))
            if parsed_range is None:
                issues.append(f"story plan scene_block {idx} invalid cut_range")
                continue
            start, end = parsed_range
            if end - start + 1 > 10:
                issues.append(f"story plan scene_block {idx} exceeds 10 cuts")
            block_ranges.append((start, end, block_id))
        if target_cuts > 0 and block_ranges:
            ordered = sorted(block_ranges)
            expected_start = 1
            for start, end, block_id in ordered:
                if start != expected_start:
                    issues.append(
                        f"story plan scene_block cut_range gap/overlap before block {block_id}: expected {expected_start}, got {start}"
                    )
                    break
                expected_start = end + 1
            if expected_start != target_cuts + 1:
                issues.append(f"story plan scene_block cut_range does not end at {target_cuts}")
        introductions_by_name: dict[str, list[int]] = {}
        block_range_by_id = {block_id: (start, end) for start, end, block_id in block_ranges}
        for block in blocks:
            if not isinstance(block, dict):
                continue
            try:
                block_id = int(block.get("block_id") or 0)
            except (TypeError, ValueError):
                block_id = 0
            block_start, block_end = block_range_by_id.get(block_id, (0, 0))
            intros = block.get("character_introductions")
            if intros in (None, ""):
                intros = []
            if not isinstance(intros, list):
                issues.append(f"story plan scene_block {block_id or '?'} character_introductions must be a list")
                continue
            for intro in intros:
                if not isinstance(intro, dict):
                    issues.append(f"story plan scene_block {block_id or '?'} character introduction is not an object")
                    continue
                name = _text(intro.get("name"))
                try:
                    cut_number = int(str(intro.get("cut_number") or "").strip())
                except (TypeError, ValueError):
                    cut_number = 0
                if not name or not _text(intro.get("explanation_goal")) or cut_number <= 0:
                    issues.append(f"story plan scene_block {block_id or '?'} character introduction incomplete")
                    continue
                if block_start and not (block_start <= cut_number <= block_end):
                    issues.append(
                        f"story plan character introduction {name} cut {cut_number} outside block {block_id} range {block_start}-{block_end}"
                    )
                if block_start and cut_number != block_start + 1:
                    issues.append(
                        f"story plan character introduction {name} must be on the second cut of block {block_id}: expected {block_start + 1}, got {cut_number}"
                    )
                introductions_by_name.setdefault(name, []).append(cut_number)
        if isinstance(character_map, list):
            for character in character_map:
                if not isinstance(character, dict):
                    continue
                name = _text(character.get("name"))
                if not name:
                    continue
                matches = introductions_by_name.get(name, [])
                if not matches:
                    issues.append(f"story plan character first appearance missing one-cut explanation: {name}")
                elif len(matches) > 1:
                    issues.append(f"story plan character explanation duplicated: {name}")
                first_appearance = _text(character.get("first_appearance_cut"))
                if matches and first_appearance:
                    first_range = _parse_cut_range(first_appearance)
                    if first_range is None:
                        try:
                            first_cut = int(first_appearance)
                            first_range = (first_cut, first_cut)
                        except (TypeError, ValueError):
                            first_range = None
                    if first_range and not any(first_range[0] <= cut <= first_range[1] for cut in matches):
                        issues.append(
                            f"story plan character explanation not placed at first appearance: {name}"
                        )
                first_block_raw = _text(character.get("first_appearance_block"))
                if matches and first_block_raw:
                    try:
                        first_block = int(first_block_raw)
                    except (TypeError, ValueError):
                        first_block = 0
                    actual_block = math.ceil(matches[0] / 10)
                    if first_block != actual_block:
                        issues.append(
                            f"story plan character first_appearance_block mismatch: {name} expected {actual_block}, got {first_block_raw}"
                        )
    issues.extend(_inspect_story_plan_topic_alignment(plan, topic, config))
    return issues


def assert_story_plan(
    plan: dict[str, Any],
    target_cuts: int = 0,
    topic: str = "",
    config: dict[str, Any] | None = None,
) -> None:
    issues = inspect_story_plan(plan, target_cuts, topic, config)
    if issues:
        preview = "; ".join(issues[:5])
        raise ValueError(f"story plan validation failed: {preview}")


def inspect_script_quality(script: dict[str, Any], topic: str = "") -> list[str]:
    """Return concrete quality issues that should block a generated script."""
    issues: list[str] = []
    if not isinstance(script, dict):
        return ["script is not a JSON object"]
    cuts = script.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        return ["script has no cuts"]

    if _is_v31_script(script):
        issues.extend(_inspect_v31_story_contract(script, cuts))

    narrations = [_text(cut.get("narration")) for cut in cuts if isinstance(cut, dict)]
    full_text = "\n".join(narrations)
    for phrase in FORBIDDEN_TEMPLATE_PHRASES:
        if phrase in full_text:
            issues.append(f"forbidden template phrase: {phrase}")

    for idx, line in enumerate(narrations, start=1):
        for pattern in BAD_GRAMMAR_PATTERNS:
            if pattern.search(line):
                issues.append(f"bad grammar pattern at cut {idx}: {line}")
                break

    line_counts = Counter(line for line in narrations if line)
    repeated = [line for line, count in line_counts.items() if count > 1]
    if repeated:
        issues.append(f"repeated narration line: {repeated[0]}")

    topic_phrase_counts = _topic_phrase_counts(narrations)
    for phrase in _primary_topic_phrases(script, topic):
        count = topic_phrase_counts.get(phrase, 0)
        if count > 15:
            issues.append(f"topic phrase repeated too often: {phrase}={count}")

    image_prompts: list[str] = []
    main_subjects: list[str] = []
    scene_focuses: list[str] = []
    for idx, cut in enumerate(cuts, start=1):
        if not isinstance(cut, dict):
            issues.append(f"cut {idx} is not an object")
            continue
        narration = _text(cut.get("narration"))
        image_prompt = _text(cut.get("image_prompt"))
        image_prompts.append(image_prompt)
        if re.search(
            r"spoken\s+cue|narration\s+cue|dialogue\s*:|voiceover\s*:|transcript\s*:|quote\s*:",
            image_prompt,
            re.IGNORECASE,
        ):
            issues.append(f"narration label leaked into image_prompt at cut {idx}")
        if narration and narration in image_prompt:
            issues.append(f"narration copied into image_prompt at cut {idx}")
        if re.search(r"[가-힣一-龥ぁ-んァ-ン]", image_prompt):
            issues.append(f"non-English text in image_prompt at cut {idx}")
        main_subject = _extract_prompt_field(image_prompt, "Main subject")
        scene_focus = _extract_prompt_field(image_prompt, "Scene")
        if main_subject:
            main_subjects.append(main_subject)
            if main_subject in GENERIC_IMAGE_SUBJECTS:
                issues.append(f"generic Main subject at cut {idx}: {main_subject}")
        if scene_focus:
            scene_focuses.append(scene_focus)

    prompt_counts = Counter(prompt for prompt in image_prompts if prompt)
    repeated_prompt = [prompt for prompt, count in prompt_counts.items() if count > 1]
    if repeated_prompt:
        issues.append("repeated image_prompt")

    if len(cuts) >= 50:
        subject_counts = Counter(main_subjects)
        if subject_counts:
            subject, count = subject_counts.most_common(1)[0]
            if count > max(30, int(len(cuts) * 0.2)):
                issues.append(f"Main subject repeated too often: {subject}={count}")
        scene_counts = Counter(scene_focuses)
        if scene_counts:
            scene, count = scene_counts.most_common(1)[0]
            if count > max(20, int(len(cuts) * 0.14)):
                issues.append(f"image scene repeated too often: {scene}={count}")

    return issues


def assert_script_quality(script: dict[str, Any], topic: str = "") -> None:
    issues = inspect_script_quality(script, topic)
    if issues:
        preview = "; ".join(issues[:5])
        raise ValueError(f"script quality validation failed: {preview}")
