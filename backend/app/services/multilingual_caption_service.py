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


DEFAULT_CAPTION_LANGUAGES = ("en", "ko", "hi")
LANGUAGE_NAMES = {
    "en": "English",
    "ko": "Korean",
    "hi": "Hindi",
}


def caption_languages_for_config(config: dict[str, Any] | None) -> list[str]:
    cfg = config or {}
    raw = cfg.get("caption_languages") or cfg.get("youtube_caption_languages")
    if isinstance(raw, str):
        parts = [p.strip().lower() for p in re.split(r"[,;\s]+", raw) if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p or "").strip().lower() for p in raw if str(p or "").strip()]
    else:
        parts = list(DEFAULT_CAPTION_LANGUAGES)

    out: list[str] = []
    for lang in parts:
        lang = lang.split("-")[0]
        if lang in LANGUAGE_NAMES and lang not in out:
            out.append(lang)
    return out or list(DEFAULT_CAPTION_LANGUAGES)


def _source_language(config: dict[str, Any] | None) -> str:
    lang = str((config or {}).get("language") or "ko").strip().lower().split("-")[0]
    return lang if lang in LANGUAGE_NAMES else "ko"


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
        if target.exists() and target.stat().st_size > 0:
            results[lang] = str(target)
            continue
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
    files = await ensure_multilingual_caption_files(source_srt_path, config)
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
    return {
        "languages": list(files.keys()),
        "uploaded": uploaded,
        "errors": errors,
        "files": files,
    }
