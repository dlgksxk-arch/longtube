"""Script-level quality checks for documentary-style longform episodes."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any


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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _primary_topic_terms(script: dict[str, Any], topic: str = "") -> list[str]:
    source = " ".join(_text(v) for v in (topic, script.get("topic"), script.get("title")))
    if not source:
        return []
    source = re.sub(r"[_/|:()\[\]{}]", " ", source)
    candidates = re.findall(r"[가-힣]{2,8}", source)
    terms: list[str] = []
    for token in candidates:
        token = re.sub(r"(?:으로|에서|에게|까지|부터|처럼|보다|과|와|은|는|을|를|의|가|이)$", "", token)
        if token in COMMON_TOPIC_WORDS:
            continue
        if len(token) < 2:
            continue
        if token.endswith(("편", "이유", "진짜", "의미", "사건", "역사")):
            continue
        if token not in terms:
            terms.append(token)
    return terms[:3]


def _extract_prompt_field(prompt: str, label: str) -> str:
    match = re.search(rf"{re.escape(label)}\s*:\s*([^;]+)", prompt, re.IGNORECASE)
    if not match:
        return ""
    return match.group(1).strip().lower()


def inspect_script_quality(script: dict[str, Any], topic: str = "") -> list[str]:
    """Return concrete quality issues that should block a generated script."""
    issues: list[str] = []
    if not isinstance(script, dict):
        return ["script is not a JSON object"]
    cuts = script.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        return ["script has no cuts"]

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

    if len(cuts) == 150:
        shorts = [
            cut
            for cut in cuts
            if isinstance(cut, dict) and cut.get("shorts_candidate") is True
        ]
        if len(shorts) != 60:
            issues.append(f"invalid shorts candidate count: {len(shorts)}")
        group_counts = Counter(cut.get("shorts_group") for cut in shorts)
        for group in (1, 2, 3, 4):
            if group_counts[group] != 15:
                issues.append(f"invalid shorts group {group} count: {group_counts[group]}")

    for term in _primary_topic_terms(script, topic):
        count = full_text.count(term)
        if count > 15:
            issues.append(f"topic term repeated too often: {term}={count}")

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
