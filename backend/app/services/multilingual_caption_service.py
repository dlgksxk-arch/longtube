from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

import anthropic
from openai import AsyncOpenAI

from app import config as app_config


DEFAULT_CAPTION_LANGUAGES = ("ko",)
LANGUAGE_NAMES = {
    "en": "English",
    "ko": "Korean",
    "hi": "Hindi",
    "ja": "Japanese",
    "zh-CN": "Chinese (China)",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
}
_LANGUAGE_ALIASES = {
    "cn": "zh-CN",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "zh_cn": "zh-CN",
    "zh_hans": "zh-CN",
    "eng": "en",
    "english": "en",
    "kor": "ko",
    "kr": "ko",
    "korean": "ko",
    "jp": "ja",
    "jpn": "ja",
    "japanese": "ja",
    "spa": "es",
    "spanish": "es",
    "fra": "fr",
    "fre": "fr",
    "french": "fr",
    "ger": "de",
    "deu": "de",
    "german": "de",
}
_SCRIPT_CAPTION_TRACK_KEYS = (
    "caption_tracks",
    "captions",
    "subtitle_tracks",
    "youtube_caption_tracks",
)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "y", "on", "enabled"}


def _normalize_caption_language(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    key = raw.replace("_", "-").lower()
    if key in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[key]
    if key in LANGUAGE_NAMES:
        return key
    base = key.split("-", 1)[0]
    if base in LANGUAGE_NAMES:
        return base
    return None


def should_upload_youtube_captions(config: dict[str, Any] | None) -> bool:
    return app_config.resolve_main_subtitle_delivery(config) == "youtube_caption"


def caption_languages_for_config(config: dict[str, Any] | None) -> list[str]:
    cfg = config or {}
    raw = (
        cfg.get("caption_languages")
        or cfg.get("youtube_caption_languages")
        or cfg.get("subtitle_languages")
        or cfg.get("captions_languages")
    )
    values: list[Any]
    if raw is None:
        values = list(DEFAULT_CAPTION_LANGUAGES)
    elif isinstance(raw, str):
        values = re.split(r"[,;/\s]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = list(raw)
    else:
        values = [raw]

    out: list[str] = []
    for value in values:
        lang = _normalize_caption_language(value)
        if lang and lang not in out:
            out.append(lang)
    return out or list(DEFAULT_CAPTION_LANGUAGES)


def _source_language(config: dict[str, Any] | None) -> str:
    return _normalize_caption_language((config or {}).get("language")) or "ko"


def _parse_srt(srt_text: str) -> list[dict[str, str]]:
    blocks = re.split(r"\n\s*\n", srt_text.replace("\r\n", "\n").replace("\r", "\n").strip())
    entries: list[dict[str, str]] = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines()]
        if len(lines) < 3:
            continue
        index = lines[0].strip()
        timing = lines[1].strip()
        text = " ".join(line.strip() for line in lines[2:] if line.strip())
        if not index or "-->" not in timing or not text:
            continue
        entries.append({"index": index, "timing": timing, "text": text})
    return entries


def _render_srt(entries: list[dict[str, str]], translations: list[str]) -> str:
    blocks: list[str] = []
    for entry, text in zip(entries, translations):
        clean = re.sub(r"\s+", " ", str(text or "").replace("\r", " ").replace("\n", " ")).strip()
        blocks.append(f"{entry['index']}\n{entry['timing']}\n{clean}\n")
    return "\n".join(blocks)


def _caption_mode_requires_script_tracks(config: dict[str, Any] | None) -> bool:
    cfg = config or {}
    mode = str(
        cfg.get("caption_source")
        or cfg.get("caption_track_source")
        or cfg.get("youtube_caption_source")
        or ""
    ).strip().lower()
    return mode in {
        "script",
        "script_tracks",
        "prepared",
        "prepared_script",
        "workbook",
        "xlsx",
    }


def _script_caption_path(source_path: Path) -> Path:
    return source_path.parent.parent / "script.json"


def _caption_text_from_cut(cut: dict[str, Any], lang: str) -> str:
    aliases = {lang}
    if lang == "zh-CN":
        aliases.update({"zh", "zh-cn", "zh_CN", "zh_Hans"})
    for container_key in _SCRIPT_CAPTION_TRACK_KEYS:
        container = cut.get(container_key)
        if not isinstance(container, dict):
            continue
        for key in aliases:
            value = container.get(key)
            if value is not None and str(value).strip():
                return re.sub(r"\s+", " ", str(value).replace("\r", " ").replace("\n", " ")).strip()
    for key in (
        f"caption_{lang}",
        f"{lang}_caption",
        f"subtitle_{lang}",
        f"{lang}_subtitle",
        f"narration_{lang}",
        f"{lang}_narration",
    ):
        value = cut.get(key)
        if value is not None and str(value).strip():
            return re.sub(r"\s+", " ", str(value).replace("\r", " ").replace("\n", " ")).strip()
    return ""


def _load_script_caption_tracks(
    source_path: Path,
    entries: list[dict[str, str]],
    target_languages: list[str],
) -> dict[str, str]:
    script_path = _script_caption_path(source_path)
    if not script_path.exists():
        return {}
    try:
        script = json.loads(script_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cuts = script.get("cuts") if isinstance(script, dict) else None
    if not isinstance(cuts, list) or len(cuts) != len(entries):
        return {}

    rendered: dict[str, str] = {}
    for lang in target_languages:
        texts = [
            _caption_text_from_cut(cut, lang) if isinstance(cut, dict) else ""
            for cut in cuts
        ]
        if texts and all(texts):
            rendered[lang] = _render_srt(entries, texts)
    return rendered


def _extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("translation response was not JSON")


async def _translate_batch_openai(texts: list[str], target_lang: str, model: str) -> list[str]:
    app_config.require_openai_api_enabled()
    async with AsyncOpenAI(api_key=app_config.OPENAI_API_KEY) as client:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You translate YouTube subtitle lines. Return only JSON. "
                        "Preserve meaning, names, numbers, and tone. Do not add commentary."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_language": LANGUAGE_NAMES[target_lang],
                            "rules": [
                                "Return exactly the same number of strings.",
                                "Keep each translated string concise enough for subtitles.",
                                "Do not translate timing, indices, or JSON keys.",
                            ],
                            "texts": texts,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
    data = _extract_json_object(response.choices[0].message.content or "")
    try:
        from app.services import spend_ledger
        spend_ledger.record_llm_usage(
            model,
            getattr(response, "usage", None),
            note=f"caption_translation {target_lang} {len(texts)} lines",
        )
    except Exception:
        pass
    translated = data.get("translations") or data.get("texts") or []
    if len(translated) != len(texts):
        raise ValueError(f"translation count mismatch: got {len(translated)}, expected {len(texts)}")
    return [str(x or "").strip() for x in translated]


async def _translate_batch_claude(texts: list[str], target_lang: str, model: str) -> list[str]:
    async with anthropic.AsyncAnthropic(api_key=app_config.ANTHROPIC_API_KEY) as client:
        response = await client.messages.create(
            model=model,
            max_tokens=max(2048, len(texts) * 90),
            system=(
                "You translate YouTube subtitle lines. Return only one JSON object "
                'with key "translations". Preserve meaning, names, numbers, and tone.'
            ),
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "target_language": LANGUAGE_NAMES[target_lang],
                            "rules": [
                                "Return exactly the same number of strings.",
                                "Keep each translated string concise enough for subtitles.",
                                "Do not add commentary.",
                            ],
                            "texts": texts,
                        },
                        ensure_ascii=False,
                    ),
                }
            ],
        )
    data = _extract_json_object(response.content[0].text if response.content else "")
    try:
        from app.services import spend_ledger
        spend_ledger.record_llm_usage(
            model,
            getattr(response, "usage", None),
            note=f"caption_translation {target_lang} {len(texts)} lines",
        )
    except Exception:
        pass
    translated = data.get("translations") or []
    if len(translated) != len(texts):
        raise ValueError(f"translation count mismatch: got {len(translated)}, expected {len(texts)}")
    return [str(x or "").strip() for x in translated]


async def _translate_texts(texts: list[str], target_lang: str, config: dict[str, Any] | None) -> list[str]:
    cfg = config or {}
    batch_size = int(cfg.get("caption_translation_batch_size") or 40)
    batch_size = max(10, min(80, batch_size))
    model = str(cfg.get("caption_translation_model") or "gpt-4o-mini")
    out: list[str] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        if model.startswith("claude"):
            translated = await _translate_batch_claude(batch, target_lang, model)
        else:
            translated = await _translate_batch_openai(batch, target_lang, model)
        out.extend(translated)
        await asyncio.sleep(0)
    return out


async def ensure_multilingual_caption_files(
    source_srt_path: str | Path,
    config: dict[str, Any] | None = None,
) -> dict[str, str]:
    source_path = Path(source_srt_path)
    if not source_path.exists():
        raise FileNotFoundError(f"caption file does not exist: {source_path}")
    entries = _parse_srt(source_path.read_text(encoding="utf-8"))
    if not entries:
        raise ValueError(f"caption file has no SRT entries: {source_path}")

    source_lang = _source_language(config)
    target_languages = caption_languages_for_config(config)
    captions_dir = source_path.parent
    results: dict[str, str] = {}
    script_tracks = _load_script_caption_tracks(source_path, entries, target_languages)
    source_target = captions_dir / f"subtitles.{source_lang}.srt"
    if source_target.resolve() != source_path.resolve():
        shutil.copy2(source_path, source_target)
    results[source_lang] = str(source_target)

    source_texts = [entry["text"] for entry in entries]
    for lang in target_languages:
        target = captions_dir / f"subtitles.{lang}.srt"
        if lang == source_lang:
            results[lang] = str(source_target)
            continue
        if lang in script_tracks:
            target.write_text(script_tracks[lang], encoding="utf-8")
            results[lang] = str(target)
            continue
        if target.exists() and target.stat().st_size > 0:
            results[lang] = str(target)
            continue
        if _caption_mode_requires_script_tracks(config):
            raise ValueError(
                f"caption track {lang} is required from script.json but was not found"
            )
        translated = await _translate_texts(source_texts, lang, config)
        target.write_text(_render_srt(entries, translated), encoding="utf-8")
        results[lang] = str(target)

    return {lang: results[lang] for lang in target_languages if lang in results}


async def upload_multilingual_captions(
    uploader,
    video_id: str,
    source_srt_path: str | Path,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    effective_config = app_config.apply_main_caption_delivery_policy(config)
    files = await ensure_multilingual_caption_files(source_srt_path, effective_config)
    uploaded: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for lang, path in files.items():
        try:
            uploaded[lang] = await asyncio.to_thread(
                uploader.upload_caption,
                video_id,
                str(path),
                lang,
                LANGUAGE_NAMES.get(lang, lang),
            )
        except Exception as exc:
            errors[lang] = str(exc)
    if errors:
        raise RuntimeError(f"YouTube 자막 업로드 실패: {errors}")
    for lang in files:
        track = uploaded.get(lang) or {}
        caption_id = str(track.get("caption_id") or "").strip()
        actual_language = _normalize_caption_language(track.get("language"))
        if not caption_id:
            raise RuntimeError(
                f"YouTube 자막 업로드 검증 실패: language={lang}, caption_id가 없습니다."
            )
        if actual_language != lang:
            raise RuntimeError(
                "YouTube 자막 업로드 검증 실패: "
                f"expected_language={lang}, "
                f"actual_language={actual_language or '(없음)'}"
            )
    return {
        "languages": list(files.keys()),
        "uploaded": uploaded,
        "errors": errors,
        "files": files,
    }
