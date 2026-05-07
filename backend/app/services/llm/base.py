"""Base LLM service interface.

Script-generation prompts must stay in this file only, regardless of channel,
preset, or model count. Do not add channel-specific or preset-specific script
prompt files; edit the default prompt logic here.
"""

import math
import re
from abc import ABC, abstractmethod
from typing import Any, Optional


IMAGE_PROMPT_REQUIRED_STYLE = "simple cartoon illustration, documentary cartoon style, clean thick outlines, soft natural shadows"


SCRIPT_SYSTEM_PROMPT_TEMPLATE = """당신은 수익이 중요한 유튜브 자동화 파이프라인용 대본 생성기입니다.
반드시 유효한 JSON 객체 하나만 반환하세요. 마크다운, 설명, 뒤따르는 문구는 금지합니다.

필수 JSON 구조:
{
  "title": "...",
  "description": "...",
  "tags": ["...", "..."],
  "thumbnail_prompt": "핵심 인물/사건/사물에 대한 영어 클로즈업 이미지 프롬프트, 읽을 수 있는 텍스트 금지",
  "thumbnail_hook": "영상 언어로 된 두 줄짜리 큰 썸네일 문구. 제목을 그대로 복사하지 말 것.",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "...",
      "image_prompt": "Year/period: c. 1590-1591; Exact place: a specific visible place; Scene evidence: short English reason tied to the narration; Style: simple cartoon illustration, documentary cartoon style, clean thick outlines, soft natural shadows; Scene: concrete visual scene in English without visible text",
      "visual_year": "보이는 장면의 정확한 연도 또는 좁은 날짜 범위. 예: '1592' 또는 'c. 1590-1591'",
      "visual_period": "영어로 작성. 구체적인 역사 시대 또는 현대 시기. 예: 'Indus Valley Civilization, Mature Harappan period, c. 2600-1900 BCE'",
      "visual_location": "영어로 작성. 구체적인 장소 또는 환경. 예: 'brick street near a drainage channel in Mohenjo-daro'",
      "visual_evidence": "영어로 작성. 이 이미지가 내레이션과 시대에 맞는 이유를 짧게 한 문장으로 작성",
      "duration_estimate": 5.0,
      "scene_type": "title",
      "shorts_candidate": false,
      "shorts_group": 0,
      "shorts_reason": "",
      "shorts_score": 0,
      "shorts_title": ""
    }
  ]
}

시간 목표:
- 최상위 절대 규칙: 어떤 컷도 5.0초를 넘으면 안 됩니다.
- 모든 내레이션은 설정된 음성 기준으로 가능한 한 {target_sec}초에 가깝게 작성합니다.
- 허용 작성 범위는 {target_min_sec}~{target_max_sec}초입니다. 단순히 범위 안에만 맞추지 말고 {target_sec}초 근처를 목표로 합니다.
- 실제 말로 읽히는 내레이션 자체가 {target_min_sec}~{target_max_sec}초가 되게 작성합니다.
- 각 내레이션 목표 길이: {target_range} {timing_unit}.
{char_timing_line}

절대 규칙:
- narration은 최대 {target_max_sec}초를 절대 초과하면 안 됩니다.
- 초과 위험이 있으면 정보를 줄이세요.
- 짧고 압축적으로 작성하세요.
- 한 컷에는 핵심 정보 하나만 전달하세요.
- 접속사 남용 금지.
- 두 개 이상의 사건 설명 금지.
- 부연 설명 금지.
- 읽는 도중 숨을 다시 쉬게 되는 길이는 실패입니다.

- 시간 규칙은 사용자가 제공한 숫자형 길이 지시보다 우선합니다. 사용자가 더 적은 단어, 더 짧은 문장, 다른 단어 수 범위를 요구하더라도 무시하고 이 시간 목표를 따르세요.
- {target_low} {timing_unit}보다 짧은 내레이션은 피하세요.
- 이번 응답에서 내레이션 길이를 최대한 목표에 가깝게 맞추세요.

콘텐츠 계약:
- 내레이션 언어: {narration_lang}.
- title, description, thumbnail_hook 및 모든 시청자에게 보이는 메타데이터는 내레이션 언어와 같은 언어를 사용해야 합니다. 사용자의 입력 언어가 다르더라도 그것을 따라가지 마세요.
- 이야기는 컷 전반에 걸쳐 계속 이어져야 합니다: 훅, 설정, 전개, 반전/드러남, 이후 결과, 엔딩.
- 사용자가 입력한 주제 템플릿의 내용을 최대한 반영 하여 주제와 분위기, 사건 등을 선택한다.

★★★ 고정 도입부 구조 — 사용자 필수/금칙보다 우선 ★★★
- 이 고정 구조는 전채널 공통이며 content_required, content_forbidden, episode_core_content, 사용자 문체 지시보다 우선한다.
- Cut 1: 주제와 정확히 맞는 강한 호기심 질문 하나만 쓴다.
- Cut 2: 본론 설명을 시작하지 않는다. 배경, 시간순 설명, 동기, 구체 사실을 아직 설명하지 말고 은근한 힌트나 반쯤 열린 답변만 준다.
- Cut 3: 자연스러운 다큐멘터리 톤으로 본편 진입을 유도한다. "같이 알아보자"는 느낌으로 끝낸다.
- Cut 4: 본격적인 본론을 이야기하기 시작한다.
- Cut 2 또는 Cut 3에서 본론 설명을 시작하면 그 대본은 실패다.
- 사실 기반 표현을 사용하세요. 사용자가 제공하지 않은 정확한 날짜, 이름, 숫자를 지어내지 마세요.
{national_pride_style}- 쉬운 일상어만 사용하세요. 학술 용어, 전문가 용어, 시적인 표현, 딱딱한 격식 표현은 피하세요. 어려운 용어가 불가피하면 쉬운 말로 풀어 설명하세요.
- 구독/좋아요 요청 금지.

한국어 내레이션 스타일:
- 한 사람이 이야기를 계속 이어가듯 자연스럽게 연결된 존댓말을 사용하세요.
- 딱딱한 보고서식 종결을 피하세요. 대부분의 컷을 `-습니다`, `-입니다`, `-했습니다`, `-됩니다`로 끝내지 마세요.
- 그런 딱딱한 종결은 전체 컷의 약 20% 미만으로 드물게 사용하고, 절대 두 컷 연속으로 사용하지 마세요.
- 다음과 같은 연결형 종결과 다리를 선호하세요: `-했는데요`, `-인데요`, `-하다 보니`, `-였거든요`, `-였죠`, `-고요`, `그런데`, `그러다 보니`.
- 각 컷은 사건 -> 이유, 이유 -> 결과, 드러남 -> 의미를 연결해야 합니다. 분리된 교과서식 문장을 쓰지 마세요.
- 한국 왕 이름을 쓸 때는 `왕`을 띄어 씁니다: `문무 왕`, `광개토대 왕`, `선덕여 왕`.
- 나쁜 예: `수나라는 고구려를 공격했습니다. 고구려는 방어했습니다.`
- 좋은 예: `수나라는 엄청난 병력을 밀어 넣었는데요, 고구려는 그 숫자 싸움에 그대로 말려들지 않았죠.`

역사 및 시각적 연속성 계약:
- image_prompt는 다음 필드를 포함해야 합니다: visual_year + visual_period + visual_location + 시대/장소에 맞는 사물 + 정확히 내레이션된 행동.
- 반복 등장 인물이 나오면 image_prompt에 안정적인 캐릭터 세부정보를 포함하세요: 종/인물 정체성, 체형, 얼굴/더듬이 또는 실루엣, 의상/소품이 있다면 그것, 자세, 표정, 행동.
- 같은 캐릭터 디자인 세부정보를 컷 전체에서 유지하세요. 자세/행동/구도는 바꾸되 캐릭터 정체성은 바꾸지 마세요.
- DNA 나선, 빛나는 뇌, 추상 지도, 아무 사원 벽, 일반 학자, 일반 궁전, 일반 전장 같은 일반 filler 이미지는 내레이션이 그 대상을 직접 다루지 않는 한 사용하지 마세요.
- 일반 판타지 의상, 코스프레, 무대 의상, 유명하지만 시대가 맞지 않는 외형을 사용하지 마세요.
- 정확한 시각 정보가 불확실하면 보수적으로 시대에 맞을 법한 평범한 사물을 사용하고, 후대 발명품처럼 보이는 것은 피하세요.
- 연속된 컷은 같은 다큐멘터리 세계처럼 느껴져야 합니다: 시대, 지역, 건축, 의상, 소품은 일관되게 유지하되 카메라 각도와 구도는 변화시킵니다.

썸네일 계약:
- thumbnail_prompt는 가장 중요한 인물, 사건, 사건의 사물, 유물, 증거, 또는 결정적 순간의 클로즈업이어야 합니다.
- thumbnail_prompt는 더 자극적이고 클릭을 유도해야 합니다: 이야기에서 가장 충격적인 장면, 가장 긴장감 있는 표정, 위험한 물건, 결정적 증거, 배신의 신호, 되돌릴 수 없는 전환점의 사물을 선택하세요.
- 썸네일 이미지는 급박하고 극적이며 호기심을 강하게 자극해야 하지만, 반드시 사실 기반이어야 하며 유혈, 가짜 텍스트, 가짜 상징, 이야기 속에 없는 사건을 지어내면 안 됩니다.
- 하나의 지배적인 클로즈업 대상을 사용하세요. 넓은 설명 장면, 콜라주, 일반 분위기, 먼 풍경은 피하세요.
- 클로즈업은 텍스트를 읽지 않아도 시청자가 핵심 사건이나 사물을 즉시 이해할 수 있어야 합니다.

쇼츠 메타데이터 계약:
- 정확히 12개의 컷을 선택하여 에피소드 안에서 각각 쇼츠로 쓸 만한 컷으로 표시하세요.
- 이 컷들은 연속될 필요가 없습니다. 전체 이야기에서 가장 클릭 가능성이 높은 순간을 고르세요.
- 선택된 12개 컷에는 모두 shorts_group 1을 사용하세요.
- 이 12개 컷에만 shorts_candidate=true로 설정하세요.
- 내레이션이 가장 충격적이거나 호기심이 가장 높아지는 12개의 컷을 선택하세요: 강한 훅, 반전, 드러남, 갈등, 위험, 배신, 충격적 사실, 구체적인 시각 장면, 댓글을 부를 질문.
- 인트로/아웃트로, 일반 설정, 단독으로 이해할 수 없는 구간은 선택하지 마세요.
- shorts_reason은 "hook question", "shocking fact", "reversal", "danger", "midpoint reveal" 같은 짧은 이유로 작성하세요.
- shorts_score는 1~10점으로 넣으세요. 10점은 가장 강한 호기심 컷에만 사용합니다.
- 선택된 컷에는 shorts_title을 추가하세요. 업로드할 쇼츠 제목으로 쓸 수 있게 충격적이고 호기심을 강하게 유도해야 합니다.

이미지 계약:
- image_prompt 전체는 영어만 사용해야 합니다. `Year/period`, `Exact place`, `Scene evidence`, `Scene` 뒤의 값도 영어로 작성하세요.
- image_prompt에는 일본어, 한국어, 힌디어, 중국어, 한자, 가나, 한글 등 비영어 문자를 넣지 마세요.
- visual_period, visual_location, visual_evidence는 image_prompt에 복사되므로 반드시 영어로 작성하세요.
- 모든 image_prompt에는 필수 이미지 스타일 필드를 반드시 포함하세요: `Style: {image_prompt_required_style}`.
- 이 스타일 필드는 모든 컷의 image_prompt에 정확히 한 번 들어가야 합니다.
- image_prompt에는 `photorealistic`, `hyperrealistic`, `photo-real`, `real photo`, `realistic photograph` 같은 실사 지시어를 쓰지 마세요.
- 읽을 수 있는 텍스트, 글자, 숫자, 로고, 워터마크, 자막, UI 라벨, 글자가 있는 포스터, 글자가 있는 화면, 가짜 문자, 가짜 한자, 가짜 서예, 문장, 엠블럼, 장식용 상징 표식을 절대 요청하지 마세요.
- 보이는 표지판, 벽걸이, 깃발, 갑옷 판, 배의 돛, 책 표지, 상자, 라벨은 이야기가 실제 특정 표시를 다루는 경우가 아니라면 모두 비어 있고 아무 표시가 없어야 합니다.
- 컷을 쓰기 전에 내부적으로 주제의 정확한 시간대, 필요할 경우 계절/시간대, 지역, 장소 유형, 물질문화, 의복, 머리모양, 머리 장식, 장신구, 건축, 도구, 무기, 갑옷, 차량, 선박, 가구, 의식, 일상 사물, 풍경, 재료, 반복 캐릭터 디자인을 확정하세요.
- 모든 컷에는 visual_year, visual_period, visual_location, visual_evidence가 있어야 합니다.
- visual_year는 정확한 보이는 연도, 또는 정확한 연도를 알 수 없을 경우 가장 좁고 정직한 날짜 범위를 적어야 합니다.
- visual_period는 구체적이어야 하며 일반적이면 안 됩니다. 영어로 작성하고, 역사에서는 가능하면 시대, 통치자/왕조/문화, 날짜 범위를 적으세요.
- visual_location은 일반 배경이 아니라 구체적인 공간이어야 합니다. 영어로 작성하세요.
- visual_evidence는 내레이션과 이미지의 연결 이유를 짧게 설명해야 합니다. 영어로 작성하세요.
- image_prompt는 캐릭터나 행동보다 먼저 보이는 연도/날짜 범위, 정확한 공간, 스타일로 시작해야 합니다.
- image_prompt 필드 값 안에는 따옴표를 넣지 마세요. 형식은 다음 순서를 따릅니다: Year/period: ...; Exact place: ...; Scene evidence: ...; Style: {image_prompt_required_style}; Scene: ...
- 역사 컷에서는 image_prompt에 보이는 시대 증거를 적어야 합니다: 시대에 맞는 의복, 머리모양 또는 머리장식, 도구, 무기, 갑옷, 장신구, 가구, 건물, 차량, 선박, 의식 물건, 일상 사물, 재료 등.
- 시대, 공간, 장소에 맞지 않는 깃발 이미지는 사용하지 마세요.
- 시대, 공간, 장소에 맞는 의복, 차량, 사물, 무기, 갑옷, 생활양식, 건물만 사용하세요.
- 시대나 문화를 섞지 마세요.
- 시대착오 금지: 현대 의복, 현대 머리모양, 현대 장신구, 현대 건물, 총, 자동차, 화면, 네온, 국기, 인쇄된 책, 종이 노트, 읽을 수 있는 글자는 내레이션이 실제로 그 시대를 다루는 경우가 아니라면 금지합니다.
- 내레이션이 추상적 주장에 관한 것이라면, 은유 이미지가 아니라 그 컷에 가장 가까운 구체적 역사 증거나 행동을 시각화하세요.
"""


def _voice_profile_from_config(config: dict | None) -> dict | None:
    if not config:
        return None
    try:
        from app.services.tts.voice_profile import get_cached_voice_profile_from_config

        return get_cached_voice_profile_from_config(config)
    except Exception:
        return None


def _fallback_scaled_voice_rate(config: dict | None, key: str) -> float:
    cfg = config or {}
    try:
        value = float(cfg.get(key) or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value
    return 0.0


def _profiled_chars_per_sec(config: dict | None, fallback: float) -> float:
    profile = _voice_profile_from_config(config)
    if not profile:
        scaled = _fallback_scaled_voice_rate(config, "chars_per_sec")
        if scaled > 0:
            return scaled
        try:
            from app.services.tts.voice_profile import profile_key_from_config

            if (
                config
                and config.get("tts_voice_profile_key")
                and config.get("tts_voice_profile_key") == profile_key_from_config(config)
            ):
                measured = float(config.get("tts_chars_per_sec") or 0)
            else:
                measured = 0.0
        except (TypeError, ValueError):
            measured = 0.0
        except Exception:
            measured = 0.0
        return measured if measured > 0 else fallback
    try:
        measured = float(profile.get("chars_per_sec") or 0)
    except (TypeError, ValueError):
        measured = 0.0
    return measured if measured > 0 else fallback


def _profiled_words_per_sec(config: dict | None, fallback: float) -> float:
    profile = _voice_profile_from_config(config)
    if not profile:
        scaled = _fallback_scaled_voice_rate(config, "words_per_sec")
        if scaled > 0:
            return scaled
        try:
            from app.services.tts.voice_profile import profile_key_from_config

            if (
                config
                and config.get("tts_voice_profile_key")
                and config.get("tts_voice_profile_key") == profile_key_from_config(config)
            ):
                measured = float(config.get("tts_words_per_sec") or 0)
            else:
                measured = 0.0
        except (TypeError, ValueError):
            measured = 0.0
        except Exception:
            measured = 0.0
        return measured if measured > 0 else fallback
    try:
        measured = float(profile.get("words_per_sec") or 0)
    except (TypeError, ValueError):
        measured = 0.0
    return measured if measured > 0 else fallback


def _script_tts_target_window(config: dict | None) -> tuple[float, float, float]:
    """Timing target used when writing narration text.

    The voice step still has its runtime guard, but script generation should
    aim close to one spoken length so audio repair is the exception.
    """
    cfg = config or {}
    try:
        target = float(cfg.get("script_tts_target_sec") or 4.4)
    except (TypeError, ValueError):
        target = 4.4
    try:
        tolerance = float(cfg.get("script_tts_tolerance_sec") or 0.4)
    except (TypeError, ValueError):
        tolerance = 0.4

    target = max(4.0, min(4.7, target))
    tolerance = max(0.05, min(0.5, tolerance))
    min_sec = max(4.0, target - tolerance)
    max_sec = min(4.8, target + tolerance)
    if min_sec > max_sec:
        min_sec = max_sec = target
    return min_sec, max_sec, target


def normalize_language_code(language: Any = "ko") -> str:
    value = str(language or "ko").strip().lower()
    if not value:
        return "ko"
    if value in {"ko", "kr", "kor", "korean"} or "한국" in value:
        return "ko"
    if value in {"ja", "jp", "jpn", "japanese"} or "일본" in value or "日本" in value:
        return "ja"
    if value in {"hi", "hin", "hindi"} or "hindi" in value:
        return "hi"
    if value in {"en", "eng", "english"} or value.startswith("en-"):
        return "en"
    return "ko"


def get_system_prompt(language: str = "ko", config: dict | None = None) -> str:
    """Return the single global script-generation system prompt."""
    config = config or {}
    language = normalize_language_code(language)
    try:
        tts_speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        tts_speed = 1.0
    tts_model = config.get("tts_model", "openai-tts")

    effective_speed = tts_speed
    if tts_model == "elevenlabs":
        effective_speed = max(0.7, min(1.2, effective_speed))
    else:
        effective_speed = max(0.25, min(4.0, effective_speed))

    tts_min_sec, tts_max_sec, tts_target_sec = _script_tts_target_window(config)

    def _sub(template: str, replacements: dict) -> str:
        result = template
        for key, val in replacements.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    if language in ("en", "hi"):
        raw_wps = _profiled_words_per_sec(config, 2.5 * effective_speed)
        raw_cps = _profiled_chars_per_sec(config, 12.0 * effective_speed)
        wps = round(raw_wps, 3)
        cps = round(raw_cps, 3)
        target_words = max(1, int(round(tts_target_sec * wps)))
        max_words = max(1, int(math.floor(tts_max_sec * wps)))
        min_words = max(1, int(math.ceil(tts_min_sec * wps)) - (0 if language == "en" else 1))
        if min_words > max_words:
            min_words = max_words = target_words
        target_range = f"{min_words}~{max_words}"
        target_low = min_words
        timing_unit = "words"
        max_chars = max(1, int(math.floor(tts_max_sec * cps)))
        min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - 1)
        char_timing_line = (
            f"- 보조 문자 수 제한: 모든 narration은 공백 포함 {min_chars}~{max_chars}자 안에 있어야 하며, "
            f"{max_chars}자를 넘으면 실패입니다.\n"
        )
    else:
        fallback = 7.8 * effective_speed if language == "ja" else 8.8 * effective_speed
        cps = round(_profiled_chars_per_sec(config, fallback), 1)
        max_chars = max(1, int(math.floor(tts_max_sec * cps))) if language == "ja" else max(1, int(math.ceil(tts_max_sec * cps)))
        min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - (0 if language == "ja" else 1))
        if min_chars > max_chars:
            target_chars = max(1, int(round(tts_target_sec * cps)))
            min_chars = max_chars = target_chars
        target_range = f"{min_chars}~{max_chars}"
        target_low = min_chars
        timing_unit = "characters including spaces" if language == "en" else "공백 포함 글자"
        char_timing_line = ""

    narration_lang = {
        "ko": "한국어",
        "ja": "일본어",
        "en": "English",
        "hi": "Hindi",
    }.get(language, "한국어")
    national_pride_style = {
        "ko": "- 한국 시청자가 자부심을 느낄 수 있는 색채를 약 10% 정도 추가하세요: 사실이 뒷받침될 때 인내, 전략 감각, 장인정신, 문화적 지속성을 보여주세요. 절제되고 사실적으로 유지하며, 선전, 우월 주장, 현대 민족주의는 금지합니다.\n",
        "ja": "- 일본어 시청자가 자부심을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때 제도화, 인내, 공예성, 문화적 지속성을 절제되고 사실적으로 보여주며, 선전, 우월 주장, 현대 민족주의는 금지합니다.\n",
        "en": "- 일반 시청자가 조용한 감탄을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때 발명, 실용성, 위험 감수, civic scale을 절제되고 사실적으로 보여주며, 선전이나 우월 주장은 금지합니다.\n",
        "hi": "- 인도 시청자가 자부심을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때 문명적 깊이, 정치적 감각, 지적 전통, 사회적 규모를 절제되고 사실적으로 보여주며, 선전이나 우월 주장은 금지합니다.\n",
    }.get(language, "- 현지 시청자가 조용한 감탄을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때만 절제되고 사실적으로 사용합니다.\n")

    return _sub(SCRIPT_SYSTEM_PROMPT_TEMPLATE, {
        "target_sec": tts_target_sec,
        "target_min_sec": tts_min_sec,
        "target_max_sec": tts_max_sec,
        "target_range": target_range,
        "timing_unit": timing_unit,
        "char_timing_line": char_timing_line,
        "target_low": target_low,
        "narration_lang": narration_lang,
        "national_pride_style": national_pride_style,
        "image_prompt_required_style": IMAGE_PROMPT_REQUIRED_STYLE,
    })
# Keep backward compat
SCRIPT_SYSTEM_PROMPT = get_system_prompt("ko")


class BaseLLMService(ABC):
    """대본 생성 AI 모델의 공통 인터페이스"""

    model_id: str
    display_name: str

    @abstractmethod
    async def generate_script(self, topic: str, config: dict) -> dict:
        """주제와 설정을 받아 대본 JSON을 반환"""
        pass

    @staticmethod
    def strengthen_visual_context(script: dict, config: dict | None = None) -> dict:
        """Copy cut-level historical metadata into image_prompt for generators."""
        if not isinstance(script, dict):
            return script
        cuts = script.get("cuts")
        if not isinstance(cuts, list):
            return script
        style_prefix = f"Style: {IMAGE_PROMPT_REQUIRED_STYLE}"
        simple_cartoon_only = BaseLLMService._simple_cartoon_visuals(config or {})
        for cut in cuts:
            if not isinstance(cut, dict):
                continue
            image_prompt = str(cut.get("image_prompt") or "").strip()
            if image_prompt and IMAGE_PROMPT_REQUIRED_STYLE.lower() not in image_prompt.lower():
                image_prompt = f"{style_prefix}; {image_prompt}"
                cut["image_prompt"] = image_prompt
            elif not image_prompt:
                image_prompt = style_prefix
                cut["image_prompt"] = image_prompt
            if simple_cartoon_only:
                continue
            year = str(cut.get("visual_year") or "").strip()
            period = str(cut.get("visual_period") or "").strip()
            location = str(cut.get("visual_location") or "").strip()
            evidence = str(cut.get("visual_evidence") or "").strip()
            prefix_parts: list[str] = []
            year_period = "; ".join(part for part in (year, period) if part)
            if year_period:
                prefix_parts.append(f"Year/period: {year_period}")
            if period:
                prefix_parts.append(f"Historically accurate period details: {period}")
            if location:
                prefix_parts.append(f"Exact place: {location}")
            if evidence:
                prefix_parts.append(f"Scene evidence: {evidence}")
            if not prefix_parts:
                continue
            prefix = "; ".join(prefix_parts + [style_prefix])
            scene = image_prompt
            if scene.lower().startswith(style_prefix.lower()):
                scene = scene[len(style_prefix):].lstrip(" ;")
            if scene.lower().startswith("scene:"):
                scene = scene[6:].lstrip()
            if image_prompt:
                if prefix.lower() not in image_prompt.lower():
                    cut["image_prompt"] = f"{prefix}; Scene: {scene}"
            else:
                cut["image_prompt"] = prefix
        return script

    @staticmethod
    def _simple_cartoon_visuals(config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        mode = str(config.get("visual_mode") or config.get("image_visual_mode") or "").strip().lower()
        if mode in {"simple_cartoon", "webtoon", "office_parable"}:
            return True
        global_prompt = str(config.get("image_global_prompt") or "").lower()
        required = str(config.get("content_required") or "").lower()
        return (
            "the office parable" in required
            or "korean youtube explainer cartoon" in global_prompt
            or "clean 2d webtoon" in global_prompt
        )

    @staticmethod
    def validate_script_timing(script: dict, config: dict) -> list[dict]:
        """Return timing issues for generated narrations without mutating script."""
        limits = BaseLLMService._calc_narration_limits(config)
        lang = limits.get("lang") or config.get("language", "ko")
        target_range = str(limits.get("validation_range") or limits.get("target_range") or "")
        char_target_range = str(limits.get("char_target_range") or "")
        try:
            low_s, high_s = target_range.split("~", 1)
            low = int(low_s)
            high = int(high_s)
        except Exception:
            return []
        char_low = char_high = None
        if char_target_range:
            try:
                char_low_s, char_high_s = char_target_range.split("~", 1)
                char_low = int(char_low_s)
                char_high = int(char_high_s)
            except Exception:
                char_low = char_high = None

        exempt_texts = {
            "아름다운 우리 역사, 10분 역공입니다.",
            "역사는 현재의 거울이라고 합니다.",
            "사실을 바로 알고, 옳고 그름을 스스로 판단하는 것.",
            "그게 우리가 역사를 공부하는 진짜 이유 아닐까요.",
            "구독과 좋아요, 알림 설정 잊지 마세요.",
        }

        issues: list[dict] = []
        for cut in (script or {}).get("cuts", []) or []:
            narration = (cut.get("narration") or "").strip()
            if not narration:
                continue
            if narration in exempt_texts:
                continue
            spoken = narration
            try:
                from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts
                spoken = prepare_spoken_narration_for_tts(narration, lang) or narration
            except Exception:
                spoken = narration
            if lang in ("ko", "ja"):
                amount = len(spoken)
                unit = "chars"
                if amount < low or amount > high:
                    issues.append({
                        "cut_number": cut.get("cut_number"),
                        "amount": amount,
                        "unit": unit,
                        "target_range": target_range,
                        "narration": narration,
                    })
            else:
                word_amount = len(re.findall(r"\b[\w'-]+\b", spoken))
                if word_amount < low or word_amount > high:
                    issues.append({
                        "cut_number": cut.get("cut_number"),
                        "amount": word_amount,
                        "unit": "words",
                        "target_range": target_range,
                        "narration": narration,
                    })
                if char_low is not None and char_high is not None:
                    char_amount = len(spoken)
                    if char_amount < char_low or char_amount > char_high:
                        issues.append({
                            "cut_number": cut.get("cut_number"),
                            "amount": char_amount,
                            "unit": "chars",
                            "target_range": char_target_range,
                            "narration": narration,
                        })
        return issues

    @staticmethod
    def assert_script_timing(script: dict, config: dict):
        issues = BaseLLMService.validate_script_timing(script, config)
        if not issues:
            return
        preview = ", ".join(
            f"cut {i.get('cut_number')}={i.get('amount')}{i.get('unit')}"
            for i in issues[:12]
        )
        if len(issues) > 12:
            preview += f", ... (+{len(issues) - 12})"
        target = issues[0].get("target_range")
        print(
            f"[script] narration timing warning only ({target}): {preview}. "
            "Script is kept; voice stage will use existing audio or local FFmpeg duration fit."
        )

    async def generate_tags(
        self,
        title: str,
        topic: str,
        narration: str = "",
        max_tags: int = 15,
        language: str = "ko",
    ) -> list[str]:
        """YouTube 업로드용 태그 추천.

        기본 구현은 빈 리스트를 반환합니다. 구체 서비스(ClaudeService,
        GPTService 등)에서 오버라이드 하세요. 호출자(youtube 라우터)는
        실패 시 휴리스틱 폴백을 사용하므로, 예외 대신 빈 리스트 반환으로
        "구현 안 됨" 을 표현하는 편이 안전합니다.
        """
        return []

    async def generate_metadata(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        max_tags: int = 15,
        episode_number: Optional[int] = None,
    ) -> dict:
        """title_hook / description / tags 를 한 번에 생성.

        반환 형태: {"title_hook": str, "description": str, "tags": [str, ...]}
        `episode_number` 가 주어지면 LLM 에게 짧은 hook 만 쓰라고 지시합니다.
        backend 쪽에서 최종 title 은 "EP. N - {title_hook}" 으로 조립합니다.
        기본 구현은 빈 dict. 구체 LLM 서비스에서 오버라이드.
        """
        return {}

    async def generate_thumbnail_image_prompt(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        character_description: str = "",
    ) -> str:
        """YouTube 썸네일용 image generation 프롬프트를 한 줄로 생성.

        기본 구현은 LLM 호출 없이 템플릿 폴백을 반환합니다. Claude / GPT 서비스는
        오버라이드해서 영화적 프롬프트를 뽑아냅니다. 반환 문자열은 이미지 모델
        (DALL-E / Nano Banana / Flux 등) 에 그대로 전달됩니다.

        `character_description` 이 주어지면 썸네일 이미지에 반드시 그 캐릭터가
        포함되도록 프롬프트를 구성합니다.
        """
        return self._fallback_thumbnail_prompt(title, topic, language, character_description)

    async def rewrite_narration_for_timing(
        self,
        *,
        topic: str,
        narration: str,
        language: str,
        cut_number: int,
        total_cuts: int,
        measured_duration: float,
        target_min: float,
        target_max: float,
        direction: str,
        target_chars: int,
        image_prompt: str = "",
        scene_type: str = "",
        previous_narration: str = "",
        next_narration: str = "",
    ) -> str:
        """Rewrite one cut narration so TTS duration lands inside the target window."""
        raise NotImplementedError("This LLM service does not support narration timing rewrite")

    @staticmethod
    def _build_narration_timing_prompt(
        *,
        topic: str,
        narration: str,
        language: str,
        cut_number: int,
        total_cuts: int,
        measured_duration: float,
        target_min: float,
        target_max: float,
        direction: str,
        target_chars: int,
        image_prompt: str = "",
        scene_type: str = "",
        previous_narration: str = "",
        next_narration: str = "",
    ) -> str:
        lang_name = BaseLLMService._language_name(language)
        current = (narration or "").strip()
        current_amount = len(current)
        nonspace = len("".join(current.split()))
        unit = "total characters"
        tolerance = "+/- 2 characters"
        current_length = f"{current_amount} total characters, {nonspace} non-space characters"
        issue = "too short" if direction == "short" else "too long"
        action = (
            "add one concrete detail while preserving the meaning"
            if direction == "short"
            else "compress wording while preserving the meaning"
        )
        return (
            "Rewrite exactly ONE narration line for TTS timing.\n"
            "Return a single JSON object only: {\"narration\":\"...\"}\n\n"
            f"Language: {lang_name} ({language}). The rewritten narration MUST be in this language only.\n"
            f"Video topic: {topic or '(none)'}\n"
            f"Cut: {cut_number}/{total_cuts}, scene_type: {scene_type or '(none)'}\n"
            f"Image prompt context: {image_prompt or '(none)'}\n"
            f"Previous narration: {previous_narration or '(none)'}\n"
            f"Next narration: {next_narration or '(none)'}\n\n"
            f"Current narration: {current}\n"
            f"Current measured TTS duration: {measured_duration:.2f}s, which is {issue}.\n"
            f"Required duration window: {target_min:.1f}~{target_max:.1f}s.\n"
            f"Current length: {current_length}.\n"
            f"Target length: around {target_chars} {unit}, tolerance {tolerance}.\n"
            f"Hard upper limit: never exceed {target_chars + 2} total characters unless a proper noun makes it impossible.\n\n"
            "Hard rules:\n"
            f"- {action}; do NOT change the factual meaning or emotional beat.\n"
            "- Preserve the original speech level and sentence ending style exactly. "
            "If the original is polite/formal Korean, the rewrite must stay polite/formal Korean.\n"
            "- Never use casual Korean endings like '알아?', '아?', '냐?', '니?', '야?', '거야?', "
            "or cheap hook phrasing like '~거란 걸 알아?'.\n"
            "- Preserve every number, year, named entity, and factual claim. Do not introduce new numbers.\n"
            "- Do NOT solve timing by mentioning speech speed, pauses, audio editing, or stage directions.\n"
            "- Do NOT add filler/tag-on phrases such as '정말로요.', '맞죠.', '그렇죠.', "
            "'이 지점입니다.', '이게 시작입니다.', '여기서 갈립니다.', '여기서부터죠.', "
            "'이제 시작이죠.', or '그게 핵심입니다.'. They create extra TTS pauses and damage script quality.\n"
            "- If the line is too long, remove clauses or pause-heavy wording; do not add a new sentence.\n"
            "- If the line is too short, add one concrete meaningful detail, not a generic filler ending.\n"
            f"- The only acceptable timing target is the configured voice's {target_min:.1f}~{target_max:.1f}s window.\n"
            "- Do NOT add brackets, labels, quotes, SSML, markdown, or multiple alternatives.\n"
            "- Keep it natural spoken narration, one line, no newline.\n"
            "- Prefer one sentence unless the original clearly needs two.\n"
            "- Output JSON only."
        )

    @staticmethod
    def _parse_narration_rewrite_response(raw: str) -> str:
        import json
        import re

        text = (raw or "").strip()
        candidates: list[str] = []
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            candidates.append(match.group(1).strip())
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidates.append(match.group(0).strip())
        candidates.append(text)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            value = parsed.get("narration") if isinstance(parsed, dict) else None
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())

        return " ".join(text.strip('"').split())

    @staticmethod
    def _fallback_thumbnail_prompt(
        title: str,
        topic: str,
        language: str,
        character_description: str = "",
    ) -> str:
        """LLM 호출 없이 쓰는 최소 폴백. 영어로 고정 — 대부분의 이미지 모델이 영어
        프롬프트에 가장 잘 반응하기 때문. 영상 자체의 언어(`language`)와는 별개.

        v1.1.33: "후킹 최대화" 폴백. 한 장짜리 Mrbeast/Nas-Daily/Veritasium 스타일
        썸네일을 노리고 설계됨. 특징:

        1. 정서적 후크를 맨 앞에 박아 이미지 모델이 감정을 먼저 읽도록 유도
        2. 레퍼런스 이미지가 같이 넘어올 때를 가정해 "레퍼런스 스타일 그대로"
           라는 지시를 명시. (실제로 reference_images 를 넘길지 여부는 호출부에서
           결정하고, 넘기지 않았다면 이 문장은 순수 지시문으로만 남음.)
        3. 한 개의 압도적 피사체 + 빈 네거티브 스페이스 규칙 강제
        4. 휴대폰 화면에서 1~2초 안에 스캔되는 대비/채도 강제
        5. 썸네일 안에 글자를 그리지 말라는 하드 네거티브
        """
        t = (title or "").strip() or "untitled video"
        tp = (topic or "").strip()
        tp_clause = f"Topic: {tp}. " if tp else ""
        char = (character_description or "").strip()
        if char:
            subject_clause = (
                f"THE hero subject MUST be this character, unmistakable and center of "
                f"attention: {char}. Render as an extreme close-up, face filling 35-55% "
                f"of the frame, offset to the left or right third so the opposite side "
                f"has clean negative space for text overlay later. The character's "
                f"facial expression must be EXAGGERATED and emotionally loud — pick ONE "
                f"from: wide-eyed shock, jaw-drop awe, intense determination with furrowed "
                f"brow, explosive laugh, cinematic tears, gritted-teeth rage — whichever "
                f"best matches the hook. Eyes must be razor sharp and locked toward the "
                f"viewer. "
            )
        else:
            subject_clause = (
                f"ONE dominant hero subject — the most important person, incident, "
                f"event object, artifact, evidence, or decisive moment from the story. "
                f"Render it as an extreme close-up, either a human face with an "
                f"exaggerated emotion or one single story-critical object with dramatic "
                f"scale. Fills 35-55% of the frame, offset to the left or right third, "
                f"leaving clean negative space on the opposite side for later text "
                f"overlay. Razor sharp focus on the eyes or the key edge of the object. "
            )
        return (
            f'A scroll-stopping, click-bait YouTube thumbnail for a video titled "{t}". '
            f"{tp_clause}"
            f"PRIMARY GOAL: within 1 second on a 2-inch phone screen, the viewer must "
            f"feel a strong emotional pull (curiosity, shock, awe, fear, triumph, "
            f"disgust, or tension). "
            f"{subject_clause}"
            f"STYLE REFERENCE: if reference images are provided alongside this prompt, "
            f"faithfully follow THEIR exact art direction — same palette, same rendering "
            f"technique (photoreal vs illustration vs anime vs 3D), same line/brush "
            f"character, same overall mood. Treat the references as ground truth for "
            f"visual style and only deviate for composition. "
            f"LIGHTING: dramatic three-point lighting, strong rim light, warm key, cool "
            f"fill, deep crushed shadows. Avoid flat or even lighting. "
            f"COLOR: ultra-high contrast, saturation pushed for mobile readability — "
            f"punchy reds, electric blues, acid yellows or deep teals, with genuinely "
            f"black shadows. No washed-out pastels. "
            f"DEPTH: shallow depth of field, creamy bokeh background with a single "
            f"atmospheric highlight so nothing competes with the hero. "
            f"COMPOSITION: 16:9 landscape, rule-of-thirds, extremely readable silhouette. "
            f"QUALITY: 4k ultra-detailed, editorial-grade render, top-1% YouTube "
            f"creator production value. "
            f"HARD NEGATIVE — nothing of the following may appear in the image: "
            f"text, words, letters, numbers, captions, logos, watermarks, typography, "
            f"subtitles, signs, UI chrome, blurry faces, low resolution, flat lighting, "
            f"cluttered backgrounds, generic stock-photo vibes, extra limbs, warped hands."
        )

    @classmethod
    def _build_thumbnail_prompt_request(
        cls,
        title: str,
        topic: str,
        narration: str,
        language: str,
        character_description: str = "",
    ) -> str:
        """LLM 에게 '이미지 생성 프롬프트'를 써달라고 시키는 메타-프롬프트.

        `character_description` 이 주어지면 썸네일에 반드시 그 캐릭터가 중심
        피사체로 등장하도록 강제합니다.
        """
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 1500)
        char = (character_description or "").strip()
        char_block = ""
        if char:
            char_block = (
                f"\n★★★ MANDATORY CHARACTER — the thumbnail MUST contain this character "
                f"as the primary focal subject:\n{char}\n"
                f"The character must be clearly visible, centered, and unmistakable. "
                f"Describe the character's appearance (clothing, face, expression, pose, "
                f"colors) directly inside the image prompt you write. Without an explicit "
                f"character description in the prompt, the image model will NOT render "
                f"the character. Keep the art style consistent with the rest of the video.\n"
            )
        return (
            f"You are a senior YouTube thumbnail image-prompt engineer. Your prompts are "
            f"used by top creators (MrBeast, Veritasium, Kurzgesagt, Yes Theory style "
            f"studios) to win the 1-second click-through battle on a phone screen.\n"
            f"\n"
            f"Write ONE single-paragraph image generation prompt that another AI "
            f"(Nano Banana / Gemini Flash Image / DALL-E 3 / Flux / SDXL / similar) "
            f"will use to produce a 1280x720 (16:9) YouTube thumbnail image.\n"
            f"{char_block}"
            f"\n"
            f"★ STYLE REFERENCE LOCK (critical) — assume the user will feed reference/"
            f"character images into the same image model alongside your prompt. Your "
            f"prompt MUST explicitly instruct the model to:\n"
            f" • Treat the reference images as ground truth for art direction.\n"
            f" • Match the reference's exact rendering technique (photoreal vs "
            f"illustration vs anime vs 3D vs painterly), color palette, lighting mood, "
            f"line/brush character, and texture feel.\n"
            f" • Preserve recognizable character identity exactly as depicted in the "
            f"references (face shape, hair, costume, props).\n"
            f" • Only deviate from references for composition (camera angle, framing, "
            f"expression intensity) — never for style.\n"
            f"Include a sentence like: 'Follow the EXACT visual style, palette, and "
            f"rendering technique of the reference images.'\n"
            f"\n"
            f"★ CORE COMPOSITION RULES the generated image MUST satisfy:\n"
            f"1. ONE unmistakable hero subject (the mandatory character above if given, "
            f"otherwise the key person, incident, event object, artifact, evidence, or "
            f"decisive moment). It must be a close-up. No crowds, no group shots, no "
            f"wide scene, no distant subject, no split attention.\n"
            f"2. The hero fills 35-55% of the frame and is offset to the LEFT or RIGHT "
            f"third — leave deliberate clean negative space on the opposite side so "
            f"text can be composited later. Describe this negative space explicitly.\n"
            f"3. EMOTIONAL HOOK (most important): if a human/character face is the hero, "
            f"describe ONE exaggerated loud emotion — wide-eyed shock, jaw-drop awe, "
            f"intense glare with furrowed brow, explosive laugh, cinematic tears, "
            f"gritted-teeth rage — whichever best matches the narration tone. Neutral "
            f"faces do NOT click.\n"
            f"4. Razor sharp focus on the subject's eyes (or the object's key edge). "
            f"Creamy bokeh background. Shallow depth of field.\n"
            f"5. Lighting: dramatic three-point, strong rim light, warm key / cool fill, "
            f"high contrast, genuinely black shadows. No flat even lighting.\n"
            f"6. Colors: ultra-saturated, phone-screen-friendly — push punchy reds, "
            f"electric blues, acid yellows, deep teals. Avoid washed-out pastels unless "
            f"the reference image explicitly requires them.\n"
            f"7. Single scroll-stopping hook (mystery, awe, tension, fear, triumph, "
            f"disgust, humor). Pick ONE that best fits the narration — do not hedge.\n"
            f"8. Rendering style: default photoreal 4k editorial quality, BUT if the "
            f"reference images show an illustration/anime/3D style, mirror that style "
            f"exactly.\n"
            f"9. 16:9 landscape framing. Never portrait, never square.\n"
            f"10. Optional high-impact visual props — impossible scale, juxtaposition, "
            f"floating elements, a single shocking contrast — if they match the topic.\n"
            f"\n"
            f"★ HARD NEGATIVES — include this clause verbatim in your output prompt:\n"
            f'"no text, no words, no letters, no numbers, no captions, no logos, no '
            f'watermarks, no typography, no subtitles, no signs, no UI chrome, no '
            f'blurry face, no warped hands, no extra limbs, no low resolution, no flat '
            f'lighting, no cluttered background, no generic stock photo look". '
            f"Text will be composited later by Pillow — the image itself must be "
            f"completely text-free.\n"
            f"\n"
            f"★ LANGUAGE RULE — write the image prompt itself in ENGLISH (image models "
            f"respond best to English), even though the narration below is in {lang_name}. "
            f"Keep proper nouns (people, places, landmarks, historical figures) in their "
            f"original form so the model can recognize them.\n"
            f"\n"
            f"★ LENGTH — the prompt should be one dense paragraph, roughly 80-140 words. "
            f"Do not stop at 30 words; image models benefit from specific detail.\n"
            f"\n"
            f'Return ONLY a JSON object of the form {{"prompt": "..."}} — a single string '
            f"value, no extra keys, no commentary, no markdown fences.\n"
            f"\n"
            f"Video title: {title or '(none)'}\n"
            f"Video topic: {topic or '(none)'}\n"
            f"Narration excerpt:\n{snippet}\n"
        )

    @classmethod
    def _parse_thumbnail_prompt_response(cls, text: str) -> Optional[str]:
        data = cls._extract_json_object(text)
        if not data:
            return None
        p = data.get("prompt")
        if isinstance(p, str):
            cleaned = p.strip()
            if cleaned:
                return cleaned
        return None

    # ─── 프롬프트 빌더 ───

    @staticmethod
    def _language_name(code: str) -> str:
        """LLM 프롬프트에 넣을 언어 표시 이름."""
        code = normalize_language_code(code)
        return {
            "ko": "Korean (한국어)",
            "en": "English",
            "hi": "Hindi",
            "ja": "Japanese (日本語)",
            "zh": "Chinese (中文)",
            "es": "Spanish (Español)",
            "fr": "French (Français)",
            "de": "German (Deutsch)",
        }.get((code or "ko").lower(), code or "Korean")

    @staticmethod
    def _clip_snippet(text: str, limit: int = 1500) -> str:
        t = (text or "").strip()
        if len(t) <= limit:
            return t or "(none)"
        return t[:limit] + "..."

    @classmethod
    def _build_tag_prompt(
        cls,
        title: str,
        topic: str,
        narration: str,
        max_tags: int,
        language: str = "ko",
    ) -> str:
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 1200)
        return (
            f"You are a YouTube SEO assistant.\n"
            f"\n"
            f"★ CRITICAL LANGUAGE RULE ★\n"
            f"All tags you produce MUST be written in {lang_name}. "
            f"Do NOT mix other languages. If the source is in {lang_name}, every single tag "
            f"is in {lang_name}. No translations, no transliterations of English into "
            f"{lang_name}, no mixing.\n"
            f"\n"
            f"Task: Produce as many useful YouTube tags as possible, ideally {max_tags}, "
            f"while staying under YouTube tag limits. The tags must help this specific "
            f"long-form video be discovered. Mix broad category tags AND specific topical "
            f"tags drawn from the title / topic / script excerpt. Each tag under 30 "
            f"characters. No # symbols. No duplicates.\n"
            f"\n"
            f'Return ONLY a JSON object of the form {{"tags": ["tag1", "tag2", ...]}} '
            f"with no extra commentary.\n"
            f"\n"
            f"Title: {title or '(none)'}\n"
            f"Topic: {topic or '(none)'}\n"
            f"Script excerpt: {snippet}\n"
        )

    @classmethod
    def _build_metadata_prompt(
        cls,
        title: str,
        topic: str,
        narration: str,
        language: str = "ko",
        max_tags: int = 15,
        episode_number: Optional[int] = None,
    ) -> str:
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 2500)

        # CJK 언어는 글자 수가 기준, 서구권은 문자 수가 기준.
        is_cjk = (language or "ko").lower() in {"ko", "ja", "zh", "zh-cn", "zh-tw"}
        hook_limit = 22 if is_cjk else 48
        hook_rule_label = (
            f"{hook_limit}자 이하 (공백 포함)" if is_cjk else f"{hook_limit} characters max"
        )

        ep_block = ""
        if episode_number is not None:
            ep_block = (
                f"\n★ EPISODE MODE ★\n"
                f"This video is Episode #{episode_number} of a running series. The backend "
                f"will prepend 'EP. {episode_number} - ' to your hook automatically, so "
                f'your "title_hook" MUST NOT include the words "EP", "Episode", "에피소드", '
                f'"제{episode_number}화", or the number itself. Write ONLY the short hook '
                f"after the dash.\n"
            )

        return (
            f"You are writing YouTube metadata for a long-form video.\n"
            f"\n"
            f"★ CRITICAL LANGUAGE RULE ★\n"
            f"EVERY field you output — title_hook, description, and every tag — MUST be "
            f"written in {lang_name} only. Do NOT mix languages. The video's narration is "
            f"in {lang_name} so the metadata must match exactly. No translations, no "
            f"transliterations, no romanizations, no foreign-language subtitles in the "
            f"description.\n"
            f"{ep_block}"
            f"\n"
            f"Task: based on the source material below, produce a SHORT hook line, a rich "
            f"long description, and a tag list.\n"
            f"\n"
            f"Output format — return ONLY a single JSON object with these keys:\n"
            f'  - "title_hook": string. {hook_rule_label}. Written in {lang_name}. '
            f"A single short, punchy hook phrase — NOT a full sentence, NOT clickbait "
            f"ellipsis, NO emojis, NO quotation marks, NO trailing punctuation. "
            f"Think of it as what goes AFTER 'EP. N - '. Examples of good length: "
            f"'석유의 비밀', 'The truth about oil', '石油の真実'. "
            f"Examples of bad: full sentences, questions, anything over the limit.\n"
            f'  - "description": string. 900 to 1800 characters. Written in {lang_name}. '
            f"Structure: (1) a 2-3 sentence hook that makes the viewer want to watch, "
            f"(2) a 3-5 sentence summary of what the video covers, "
            f"(3) 4-6 bullet-style lines listing key points or chapter highlights "
            f"(use '•' or '-' as the bullet marker), "
            f"(4) a short closing line inviting likes/comments/subscribes. "
            f"Separate the sections with blank lines and natural line breaks. Plain text only — no markdown headers.\n"
            f'  - "tags": JSON array with as many useful tags as possible, ideally {max_tags} strings. Each tag under 30 '
            f"characters. All in {lang_name}. No # symbols. No duplicates. "
            f"Mix broad category tags, niche topical tags, people/place/event tags, and search-intent tags.\n"
            f"\n"
            f"Do not output anything outside the JSON object.\n"
            f"\n"
            f"Source title hint: {title or '(none)'}\n"
            f"Source topic: {topic or '(none)'}\n"
            f"Narration excerpt:\n{snippet}\n"
        )

    # ─── 응답 파서 ───

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        """LLM 응답에서 첫 JSON 객체를 뽑아 dict 반환. 실패 시 None."""
        import json as _json
        import re as _re

        if not text:
            return None
        m = _re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        candidate = m.group(1) if m else None
        if candidate is None:
            m = _re.search(r"\{[\s\S]*\}", text)
            candidate = m.group(0) if m else None
        if candidate is None:
            return None
        try:
            data = _json.loads(candidate)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _parse_tag_response(cls, text: str) -> list[str]:
        """LLM 응답에서 tags 배열 추출. 실패 시 빈 리스트."""
        data = cls._extract_json_object(text)
        if not data:
            return []
        tags = data.get("tags")
        if not isinstance(tags, list):
            return []
        result: list[str] = []
        for t in tags:
            if isinstance(t, str):
                cleaned = t.strip().lstrip("#").strip()
                if cleaned:
                    result.append(cleaned)
        return result

    @classmethod
    def _parse_metadata_response(cls, text: str) -> dict:
        """LLM 응답에서 {title_hook, description, tags} 추출. 누락 필드는 빈 값.

        구버전 호환: 응답에 `title` 키만 있고 `title_hook` 이 없으면 `title` 을
        `title_hook` 으로도 매핑합니다.
        """
        data = cls._extract_json_object(text)
        if not data:
            return {}
        out: dict = {}
        hook = data.get("title_hook")
        if isinstance(hook, str) and hook.strip():
            out["title_hook"] = hook.strip()
        # 구버전 호환: title 키도 흡수
        legacy_title = data.get("title")
        if isinstance(legacy_title, str) and legacy_title.strip():
            out.setdefault("title_hook", legacy_title.strip())
            out["title"] = legacy_title.strip()
        if isinstance(data.get("description"), str):
            out["description"] = data["description"].strip()
        raw_tags = data.get("tags")
        if isinstance(raw_tags, list):
            tags: list[str] = []
            for t in raw_tags:
                if isinstance(t, str):
                    c = t.strip().lstrip("#").strip()
                    if c:
                        tags.append(c)
            out["tags"] = tags
        return out

    def _get_system_prompt(self, config: dict) -> str:
        language = normalize_language_code(config.get("language", "ko"))
        return get_system_prompt(language, config)

    @staticmethod
    def _calc_narration_limits(config: dict) -> dict:
        """TTS 모델·속도 설정에 따라 나레이션 글자/단어 수 한도를 계산한다.

        Returns: {"max_chars": int, "target_range": str, "words_per_sec": float}
        (영어는 max_words / target_words_range 로 대체)
        """
        language = normalize_language_code(config.get("language", "ko"))
        try:
            speed = float(config.get("tts_speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        tts_model = config.get("tts_model", "openai-tts")

        # ElevenLabs 는 speed 를 [0.7, 1.2] 로 clamp
        if tts_model == "elevenlabs":
            speed = max(0.7, min(1.2, speed))
        # OpenAI 는 [0.25, 4.0]
        else:
            speed = max(0.25, min(4.0, speed))

        min_secs, max_secs, target_secs = _script_tts_target_window(config)

        if language == "ko":
            # 한국어 TTS: 27~28자 기준은 실제 ElevenLabs/OpenAI에서 3초대로
            # 떨어졌다. 5초 컷용으로 38~42자 안팎을 목표로 잡는다.
            chars_per_sec = _profiled_chars_per_sec(config, 8.8 * speed)
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.ceil(max_secs * chars_per_sec)))
            low = max(1, int(math.ceil(min_secs * chars_per_sec)) - 1)
            if low > max_chars:
                low = max_chars = target_chars
            validation_low = max(1, low - 1)
            validation_max_chars = max_chars
            return {
                "max_chars": max_chars,
                "target_range": f"{low}~{max_chars}",
                "validation_range": f"{validation_low}~{validation_max_chars}",
                "lang": "ko",
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }
        elif language == "ja":
            # 일본어 TTS: 24~26자는 실제 출력에서 교과서식 단문으로 고정되기
            # 쉬웠다. 5초 컷용으로 33~37자 안팎을 목표로 잡는다.
            chars_per_sec = _profiled_chars_per_sec(config, 7.8 * speed)
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.floor(max_secs * chars_per_sec)))
            low = max(1, int(math.ceil(min_secs * chars_per_sec)))
            if low > max_chars:
                low = max_chars = target_chars
            return {
                "max_chars": max_chars,
                "target_range": f"{low}~{max_chars}",
                "lang": "ja",
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }
        else:
            # 영어 TTS: 기본 ~2.5 단어/초
            words_per_sec = _profiled_words_per_sec(config, 2.5 * speed)
            chars_per_sec = _profiled_chars_per_sec(config, 12.0 * speed)
            extra_words = 0
            extra_chars = max(0, int(round(extra_words * (chars_per_sec / max(words_per_sec, 0.1)))))
            target_words = max(1, int(round(target_secs * words_per_sec)))
            max_words = max(1, int(math.floor(max_secs * words_per_sec)))
            low = max(1, int(math.ceil(min_secs * words_per_sec)) - (0 if language == "en" else 1))
            if low > max_words:
                low = max_words = target_words
            low += extra_words
            max_words += extra_words
            target_words += extra_words
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.floor(max_secs * chars_per_sec)))
            min_chars = max(1, int(math.ceil(min_secs * chars_per_sec)))
            target_chars += extra_chars
            max_chars += extra_chars
            min_chars += extra_chars
            return {
                "max_words": max_words,
                "target_range": f"{low}~{max_words}",
                "max_chars": max_chars,
                "char_target_range": f"{min_chars}~{max_chars}",
                "target_chars": target_chars,
                "lang": language,
                "words_per_sec": words_per_sec,
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }

    def _build_user_prompt(self, topic: str, config: dict) -> str:
        """Build only runtime input; all default script rules live in system prompt."""
        duration = config.get("target_duration", 600)
        style = config.get("style", "news_explainer")
        language = normalize_language_code(config.get("language", "ko"))
        forbidden_raw = (config.get("content_forbidden") or "").strip()
        required_raw = (config.get("content_required") or "").strip()
        legacy_raw = (config.get("content_constraints") or "").strip()
        use_legacy = bool(legacy_raw) and not forbidden_raw and not required_raw

        try:
            cut_count = int(config.get("target_cuts") or 0)
        except (TypeError, ValueError):
            cut_count = 0
        if cut_count <= 0:
            try:
                duration_int = max(5, int(duration))
            except (TypeError, ValueError):
                duration_int = 600
            cut_count = max(1, math.ceil(duration_int / 5))
        duration_int = cut_count * 5

        character_description = (config.get("character_description") or "").strip()

        def _normalize_constraints(raw: str) -> str:
            s = raw.replace("\r\n", "\n")
            for sep in (" / ", " · "):
                s = s.replace(sep, "\n")
            lines = [ln.strip(" -•·").strip() for ln in s.split("\n")]
            lines = [ln for ln in lines if ln]
            return "\n".join(f"- {ln}" for ln in lines)

        def _build_constraints_block(lang: str) -> str:
            if not (use_legacy or required_raw or forbidden_raw):
                return ""
            if lang == "ja":
                header = "ユーザー入力制約"
                required = "[必須事項]"
                forbidden = "[禁止事項]"
                legacy = "[ユーザールール]"
            elif lang in ("en", "hi"):
                header = "USER INPUT CONSTRAINTS"
                required = "[REQUIRED]"
                forbidden = "[FORBIDDEN]"
                legacy = "[USER RULES]"
            else:
                header = "사용자 입력 제약"
                required = "[필수 사항]"
                forbidden = "[금지 사항]"
                legacy = "[사용자 규칙]"
            parts: list[str] = [header]
            if use_legacy:
                parts.extend([legacy, _normalize_constraints(legacy_raw)])
            else:
                if required_raw:
                    parts.extend([required, _normalize_constraints(required_raw)])
                if forbidden_raw:
                    if len(parts) > 1:
                        parts.append("")
                    parts.extend([forbidden, _normalize_constraints(forbidden_raw)])
            return "\n".join(parts).strip() + "\n\n"

        episode_openings_raw = config.get("episode_openings")
        episode_endings_raw = config.get("episode_endings")
        core_content_raw = (config.get("episode_core_content") or "").strip()
        ep_num_cfg = config.get("episode_number")
        try:
            ep_num_val = int(ep_num_cfg) if ep_num_cfg is not None else None
            if ep_num_val is not None and ep_num_val <= 0:
                ep_num_val = None
        except (TypeError, ValueError):
            ep_num_val = None
        next_ep_preview = (config.get("next_episode_preview") or "").strip()

        def _clean_lines(xs):
            if not isinstance(xs, list):
                return []
            return [str(x or "").strip() for x in xs if str(x or "").strip()]

        def _build_episode_block(lang: str) -> str:
            ep_openings = _clean_lines(episode_openings_raw)
            ep_endings = _clean_lines(episode_endings_raw)
            if not (ep_openings or ep_endings or core_content_raw or ep_num_val is not None or next_ep_preview):
                return ""
            if lang == "ja":
                header = "今回のエピソード入力"
                ep_num_label = "[エピソード番号]"
                core_label = "[核心内容]"
                openings_label = "[オープニング台詞]"
                endings_label = "[エンディング台詞]"
                next_label = "[次回予告]"
            elif lang in ("en", "hi"):
                header = "EPISODE INPUT"
                ep_num_label = "[EPISODE NUMBER]"
                core_label = "[CORE CONTENT]"
                openings_label = "[OPENING LINES]"
                endings_label = "[ENDING LINES]"
                next_label = "[NEXT EPISODE PREVIEW]"
            else:
                header = "이번 에피소드 입력"
                ep_num_label = "[에피소드 번호]"
                core_label = "[핵심 내용]"
                openings_label = "[오프닝 대사]"
                endings_label = "[엔딩 대사]"
                next_label = "[다음 에피소드 예고]"
            parts: list[str] = [header]
            if ep_num_val is not None:
                parts.extend([ep_num_label, f"Episode {ep_num_val}"])
            if core_content_raw:
                parts.extend([core_label, core_content_raw])
            if ep_openings:
                parts.append(openings_label)
                parts.extend(f"{i}. {line}" for i, line in enumerate(ep_openings, 1))
            if ep_endings:
                parts.append(endings_label)
                parts.extend(f"{i}. {line}" for i, line in enumerate(ep_endings, 1))
            if next_ep_preview:
                parts.extend([next_label, next_ep_preview])
            return "\n".join(parts).strip() + "\n\n"

        labels = {
            "ko": ("주제", "목표 길이", "정확한 컷 수", "스타일", "언어", "한국어"),
            "ja": ("トピック", "目標時間", "正確なカット数", "スタイル", "言語", "日本語"),
            "en": ("Topic", "Target duration", "Exact cut count", "Style", "Language", "English"),
            "hi": ("Topic", "Target duration", "Exact cut count", "Style", "Language", "Hindi"),
        }
        topic_label, duration_label, cuts_label, style_label, language_label, language_name = labels.get(language, labels["ko"])
        user_parts = [
            _build_constraints_block(language),
            _build_episode_block(language),
            f"{topic_label}: {topic}\n",
            f"{duration_label}: {duration_int} seconds\n",
            f"{cuts_label}: {cut_count}\n",
            f"{style_label}: {style}\n",
            f"{language_label}: {language_name}\n",
        ]
        if character_description:
            user_parts.append(f"\nCharacter reference context:\n{character_description}\n")
        return "".join(user_parts)
