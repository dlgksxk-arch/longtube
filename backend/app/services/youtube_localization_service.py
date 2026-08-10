"""Build and validate localized YouTube titles and descriptions."""
from __future__ import annotations

import json
import re
from typing import Any

import anthropic
from openai import AsyncOpenAI

from app import config as app_config


LANGUAGE_NAMES = {
    "en": "English",
    "ja": "Japanese",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
}
_TRANSLATION_LANGUAGE_NAMES = {**LANGUAGE_NAMES, "ko": "Korean"}
_LANGUAGE_ALIASES = {
    "en-us": "en",
    "en_us": "en",
    "english": "en",
    "ja-jp": "ja",
    "ja_jp": "ja",
    "japanese": "ja",
    "fr-fr": "fr",
    "fr_fr": "fr",
    "french": "fr",
    "es-es": "es",
    "es_es": "es",
    "spanish": "es",
    "de-de": "de",
    "de_de": "de",
    "german": "de",
}
_SCRIPT_LOCALIZATION_KEYS = (
    "youtube_localizations",
    "metadata_localizations",
    "localizations",
)
_TRAILING_TITLE_HASHTAGS_RE = re.compile(r"(?:\s+#[^\s#]+)+\s*$")


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {
        "1", "true", "yes", "y", "on", "enabled",
    }


def normalize_language(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = raw.replace("_", "-").lower()
    if key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[key]
    base = key.split("-", 1)[0]
    return base if base in LANGUAGE_NAMES else ""


def youtube_localization_languages(config: dict[str, Any] | None) -> list[str]:
    cfg = config or {}
    raw = cfg.get("youtube_localization_languages")
    if raw is None:
        raw = cfg.get("caption_languages") or []
    if isinstance(raw, str):
        values = re.split(r"[,;/\s]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [raw]
    source = normalize_language(cfg.get("language")) or "en"
    out: list[str] = []
    for value in values:
        lang = normalize_language(value)
        if lang and lang != source and lang not in out:
            out.append(lang)
    return out


def _fit_youtube_title(value: Any, *, max_length: int = 100) -> str:
    """Fit a localized title to YouTube's limit without dropping trailing hashtags."""
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    limit = max(1, int(max_length or 100))
    if len(text) <= limit:
        return text

    suffix = ""
    suffix_match = _TRAILING_TITLE_HASHTAGS_RE.search(text)
    if suffix_match:
        candidate = suffix_match.group(0).strip()
        if len(candidate) < limit - 20:
            suffix = candidate
            text = text[:suffix_match.start()].rstrip()

    base_limit = limit - (len(suffix) + 1 if suffix else 0)
    if base_limit <= 0:
        return suffix[:limit].rstrip()
    if len(text) > base_limit:
        window = text[: base_limit + 1]
        cut_at = window.rfind(" ")
        if cut_at < max(20, int(base_limit * 0.55)):
            cut_at = base_limit
        text = text[:cut_at].rstrip(" |/\\-–—:·,.;!?")
    fitted = f"{text} {suffix}".strip() if suffix else text
    return fitted[:limit].rstrip()


def normalize_youtube_localizations(
    value: Any,
    *,
    allowed_languages: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    raw = value
    if isinstance(raw, dict) and isinstance(raw.get("localizations"), dict):
        raw = raw["localizations"]
    if not isinstance(raw, dict):
        return {}
    allowed = set(allowed_languages or [])
    out: dict[str, dict[str, str]] = {}
    for raw_lang, raw_item in raw.items():
        lang = normalize_language(raw_lang)
        if not lang or (allowed and lang not in allowed) or not isinstance(raw_item, dict):
            continue
        title = _fit_youtube_title(raw_item.get("title"), max_length=100)
        description = str(raw_item.get("description") or "").strip()
        description = re.sub(r"\r\n?", "\n", description)
        description = re.sub(r"\n{3,}", "\n\n", description)
        if not title or not description:
            continue
        if len(description) > 5000:
            raise ValueError(f"YouTube localized description exceeds 5000 characters: {lang}")
        out[lang] = {"title": title, "description": description}
    return out


def script_youtube_localizations(
    script: dict[str, Any] | None,
    *,
    allowed_languages: list[str] | None = None,
) -> dict[str, dict[str, str]]:
    data = script or {}
    for key in _SCRIPT_LOCALIZATION_KEYS:
        normalized = normalize_youtube_localizations(
            data.get(key),
            allowed_languages=allowed_languages,
        )
        if normalized:
            return normalized
    return {}


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        parsed = json.loads(raw[start:end + 1])
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("YouTube metadata translation response was not a JSON object")


def _translation_request(
    *,
    title: str,
    description: str,
    source_language: str,
    target_languages: list[str],
    strict_no_hangul: bool = False,
) -> str:
    rules = [
        "Translate faithfully without adding or removing historical claims.",
        "Preserve dates, paragraph breaks, and the brand name Scartography.",
        "Use natural native phrasing, not word-for-word machine phrasing.",
        "Each title must be 100 characters or fewer.",
        "Return every requested language exactly once.",
    ]
    if strict_no_hangul:
        rules.extend([
            "The Japanese title and description must contain zero Hangul characters.",
            "Render every Korean proper name in standard Japanese script; do not copy Korean spellings.",
            "Translate or transliterate Korean hashtag text into Japanese while preserving each hashtag marker and meaning.",
        ])
    else:
        rules.extend([
            "Preserve proper names.",
            "Preserve every hashtag exactly as written in the source description.",
        ])
    return json.dumps(
        {
            "source_language": _TRANSLATION_LANGUAGE_NAMES.get(source_language, source_language),
            "target_languages": {
                lang: _TRANSLATION_LANGUAGE_NAMES.get(lang, lang) for lang in target_languages
            },
            "title": title,
            "description": description,
            "rules": rules,
            "response_schema": {
                "localizations": {
                    "language_code": {"title": "...", "description": "..."}
                }
            },
        },
        ensure_ascii=False,
    )


def _record_usage(model: str, response: Any, languages: list[str]) -> None:
    try:
        from app.services import spend_ledger

        spend_ledger.record_llm_usage(
            model,
            getattr(response, "usage", None),
            note=f"youtube_metadata_translation {','.join(languages)}",
        )
    except Exception:
        pass


async def _translate_openai(
    *,
    title: str,
    description: str,
    source_language: str,
    target_languages: list[str],
    model: str,
    strict_no_hangul: bool = False,
) -> dict[str, dict[str, str]]:
    app_config.require_openai_api_enabled()
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You translate YouTube titles and descriptions for a European-history "
                    "documentary channel. Return one JSON object only."
                ),
            },
            {
                "role": "user",
                "content": _translation_request(
                    title=title,
                    description=description,
                    source_language=source_language,
                    target_languages=target_languages,
                    strict_no_hangul=strict_no_hangul,
                ),
            },
        ],
        "response_format": {"type": "json_object"},
        "timeout": 180,
    }
    if model.startswith("gpt-5"):
        kwargs["max_completion_tokens"] = 12000
    else:
        kwargs["max_tokens"] = 12000
        kwargs["temperature"] = 0.2
    async with AsyncOpenAI(api_key=app_config.OPENAI_API_KEY) as client:
        response = await client.chat.completions.create(**kwargs)
    _record_usage(model, response, target_languages)
    data = _extract_json_object(response.choices[0].message.content or "")
    return normalize_youtube_localizations(
        data,
        allowed_languages=target_languages,
    )


async def _translate_anthropic(
    *,
    title: str,
    description: str,
    source_language: str,
    target_languages: list[str],
    model: str,
    strict_no_hangul: bool = False,
) -> dict[str, dict[str, str]]:
    async with anthropic.AsyncAnthropic(api_key=app_config.ANTHROPIC_API_KEY) as client:
        response = await client.messages.create(
            model=model,
            max_tokens=12000,
            temperature=0.2,
            system=(
                "You translate YouTube titles and descriptions for a European-history "
                "documentary channel. Return one JSON object only."
            ),
            messages=[
                {
                    "role": "user",
                    "content": _translation_request(
                        title=title,
                        description=description,
                        source_language=source_language,
                        target_languages=target_languages,
                        strict_no_hangul=strict_no_hangul,
                    ),
                }
            ],
        )
    _record_usage(model, response, target_languages)
    raw = response.content[0].text if response.content else ""
    data = _extract_json_object(raw)
    return normalize_youtube_localizations(
        data,
        allowed_languages=target_languages,
    )


async def ensure_primary_youtube_metadata_language(
    *,
    title: str,
    description: str,
    config: dict[str, Any] | None,
) -> tuple[str, str]:
    """Translate a mismatched primary title/description before upload validation."""
    cfg = config or {}
    target_language = normalize_language(cfg.get("language"))
    if target_language != "ja":
        return title, description
    if not re.search(r"[\uac00-\ud7a3]", f"{title}\n{description}"):
        return title, description

    local_fallback = _local_japanese_primary_metadata(title, description)
    if local_fallback is not None:
        return local_fallback

    model = str(
        cfg.get("youtube_metadata_translation_model")
        or cfg.get("caption_translation_model")
        or "gpt-5.4-mini"
    ).strip()
    kwargs = {
        "title": title,
        "description": description,
        "source_language": "ko",
        "target_languages": [target_language],
        "model": model,
        "strict_no_hangul": True,
    }
    if model.startswith("claude"):
        generated = await _translate_anthropic(**kwargs)
    else:
        generated = await _translate_openai(**kwargs)
    localized = generated.get(target_language) or {}
    translated_title = str(localized.get("title") or "").strip()
    translated_description = str(localized.get("description") or "").strip()
    if not translated_title or not translated_description:
        raise ValueError("Primary YouTube metadata translation is missing Japanese text")
    if re.search(r"[\uac00-\ud7a3]", f"{translated_title}\n{translated_description}"):
        repair_kwargs = {
            "title": translated_title,
            "description": translated_description,
            "source_language": target_language,
            "target_languages": [target_language],
            "model": model,
            "strict_no_hangul": True,
        }
        if model.startswith("claude"):
            repaired = await _translate_anthropic(**repair_kwargs)
        else:
            repaired = await _translate_openai(**repair_kwargs)
        repaired_localized = repaired.get(target_language) or {}
        translated_title = str(repaired_localized.get("title") or "").strip()
        translated_description = str(repaired_localized.get("description") or "").strip()
        if not translated_title or not translated_description:
            raise ValueError("Primary YouTube metadata repair is missing Japanese text")
        if re.search(r"[\uac00-\ud7a3]", f"{translated_title}\n{translated_description}"):
            raise ValueError("Primary YouTube metadata translation still contains Hangul after repair")
    return translated_title, translated_description


def _local_japanese_primary_metadata(
    title: str,
    description: str,
) -> tuple[str, str] | None:
    """Return reviewed local Japanese metadata for known prepared episodes.

    This path is deterministic and performs no external model call.
    """
    combined = f"{title}\n{description}"
    if re.search(
        r"ヤマタノオロチ|야마타노오로치|八つの頭|8개의\s*머리",
        combined,
        re.IGNORECASE,
    ):
        episode_match = re.search(r"\bEP\.?\s*(\d{1,3})\b", title, re.IGNORECASE)
        episode_suffix = (
            f" EP.{int(episode_match.group(1)):02d}"
            if episode_match
            else ""
        )
        return (
            f"八つの頭を持つ怪物、ヤマタノオロチ{episode_suffix}",
            "スサノオが出雲で老夫婦とクシナダヒメに出会い、八つの頭と八つの尾を持つ怪物ヤマタノオロチの恐怖に立ち向かう日本神話をたどります。\n\n"
            "洪水と川、砂鉄と古代出雲の製鉄文化が巨大な蛇の伝承にどう重なったのかを、物語の流れに沿って解説します。\n\n"
            "#日本神話 #ヤマタノオロチ #スサノオ #出雲",
        )
    if re.search(r"天岩戸|アマテラス|血まみれ", combined, re.IGNORECASE):
        episode_match = re.search(r"\bEP\.?\s*(\d{1,3})\b", title, re.IGNORECASE)
        episode_suffix = (
            f" EP.{int(episode_match.group(1)):02d}"
            if episode_match
            else ""
        )
        localized_title = title if not re.search(r"[\uac00-\ud7a3]", title) else f"天岩戸隠れ{episode_suffix}"
        localized_description = (
            "スサノオの暴走によって機織りの場に悲劇が起こり、太陽神アマテラスが天岩戸に隠れた日本神話をたどります。\n\n"
            "血に染まった布、閉ざされた岩戸、太陽を失った大地、そして神々が光を取り戻すために集まるまでを、物語の流れに沿って解説します。\n\n"
            "#日本神話 #天岩戸 #アマテラス #スサノオ"
        )
        return localized_title, localized_description
    if "여신의 파격적인 스트립쇼가 세상을 구했다" in combined:
        overlay = "女神の型破りな踊りが世界を救った！？"
        return overlay, overlay
    if "암흑으로 변한 세상" not in combined and "아마노이와토" not in combined:
        return None

    episode_match = re.search(r"\bEP\.?\s*(\d{1,3})\b", title, re.IGNORECASE)
    episode_suffix = (
        f" EP.{int(episode_match.group(1)):02d}"
        if episode_match
        else ""
    )
    localized_title = f"闇に包まれた世界、天岩戸{episode_suffix}"
    localized_description = (
        "太陽神アマテラスが天岩戸に隠れ、世界が闇に包まれた日本神話をたどります。\n\n"
        "神々の知恵、アメノウズメの型破りな踊り、八咫鏡と勾玉、光の復活、"
        "そしてスサノオの追放までを、物語の流れに沿って解説します。\n\n"
        "古代の祭り、神楽、注連縄へつながる要素と、日本神話に現れる韓半島との"
        "つながりにも触れます。\n\n"
        "#日本神話 #天岩戸 #アマテラス #スサノオ"
    )
    return localized_title, localized_description


async def build_youtube_metadata_localizations(
    *,
    title: str,
    description: str,
    script: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> dict[str, dict[str, str]]:
    cfg = config or {}
    targets = youtube_localization_languages(cfg)
    if not targets:
        return {}
    existing = script_youtube_localizations(
        script,
        allowed_languages=targets,
    )
    missing = [lang for lang in targets if lang not in existing]
    if not missing:
        return {lang: existing[lang] for lang in targets}
    if not _truthy(cfg.get("youtube_metadata_localizations_enabled")):
        return existing

    source_language = normalize_language(cfg.get("language")) or "en"
    model = str(
        cfg.get("youtube_metadata_translation_model")
        or cfg.get("caption_translation_model")
        or "gpt-5.4-mini"
    ).strip()
    if not model.startswith("claude") and app_config.OPENAI_API_DISABLED:
        return existing
    if model.startswith("claude"):
        generated = await _translate_anthropic(
            title=title,
            description=description,
            source_language=source_language,
            target_languages=missing,
            model=model,
        )
    else:
        generated = await _translate_openai(
            title=title,
            description=description,
            source_language=source_language,
            target_languages=missing,
            model=model,
        )
    merged = {**existing, **generated}
    unresolved = [lang for lang in targets if lang not in merged]
    if unresolved:
        raise ValueError(
            "YouTube metadata translations are missing: " + ", ".join(unresolved)
        )
    return {lang: merged[lang] for lang in targets}
