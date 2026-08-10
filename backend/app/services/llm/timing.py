"""Script-level narration timing repair.

The voice step must keep narration as-is. This module repairs narration length
immediately after script generation, before the script is saved or TTS is run.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable

from app import config as app_config
from app.services.cancel_ctx import OperationCancelled, raise_if_cancelled
from app.services.llm.base import BaseLLMService


def _script_checkpoint_fingerprint(topic: str, config: dict, model_id: str) -> str:
    payload = {
        "topic": str(topic or ""),
        "model_id": str(model_id or ""),
        "target_cuts": config.get("target_cuts"),
        "target_duration": config.get("target_duration"),
        "language": config.get("language"),
        "style": config.get("style"),
        "content_required": config.get("content_required"),
        "content_forbidden": config.get("content_forbidden"),
        "episode_number": config.get("episode_number"),
        "episode_core_content": config.get("episode_core_content"),
        "next_episode_preview": config.get("next_episode_preview"),
        "episode_openings": config.get("episode_openings"),
        "episode_endings": config.get("episode_endings"),
        "story_plan": config.get("story_plan"),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _script_checkpoint_path(config: dict, *, create: bool) -> Path | None:
    project_id = str(config.get("__project_id") or "").strip()
    if not project_id:
        return None
    try:
        project_dir = app_config.resolve_project_dir(project_id, config, create=create)
        raw_dir = project_dir / "llm_raw"
        if create:
            raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir / "script_timing_checkpoint.json"
    except Exception:
        return None


def load_script_timing_checkpoint(topic: str, config: dict, model_id: str) -> dict | None:
    path = _script_checkpoint_path(config, create=False)
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("fingerprint") != _script_checkpoint_fingerprint(topic, config, model_id):
            return None
        script = payload.get("script")
        if not isinstance(script, dict):
            return None
        cuts = script.get("cuts")
        if not isinstance(cuts, list) or len(cuts) != BaseLLMService._expected_cut_count(config):
            return None
        return script
    except Exception:
        return None


def save_script_timing_checkpoint(script: dict, topic: str, config: dict, model_id: str) -> None:
    if not isinstance(script, dict):
        return
    path = _script_checkpoint_path(config, create=True)
    if path is None:
        return
    payload = {
        "fingerprint": _script_checkpoint_fingerprint(topic, config, model_id),
        "script": script,
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temp_path.replace(path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def clear_script_timing_checkpoint(config: dict) -> None:
    path = _script_checkpoint_path(config, create=False)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _amount(text: str, lang: str) -> int:
    if lang in ("ko", "ja"):
        return len(text)

    return len(re.findall(r"\b[\w']+\b", text))


def _spoken_amount(text: str, lang: str, cut: dict | None, config: dict) -> int:
    """Measure Japanese narration exactly as the final timing validator does."""
    if lang != "ja":
        return _amount(text, lang)
    try:
        from app.services.tts.narration_source import get_cut_tts_narration
        from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts

        candidate_cut = dict(cut or {})
        candidate_cut["narration"] = text
        spoken = get_cut_tts_narration(candidate_cut, config, text) or text
        spoken = prepare_spoken_narration_for_tts(spoken, lang) or spoken
        return len(spoken)
    except Exception:
        return _amount(text, lang)


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"\b[\w']+\b", text or "")


def _parse_range(target_range: str) -> tuple[int, int] | None:
    try:
        low_s, high_s = str(target_range).split("~", 1)
        return int(low_s), int(high_s)
    except Exception:
        return None


def _is_in_range(text: str, lang: str, low: int, high: int) -> bool:
    value = _amount(text, lang)
    return low <= value <= high


def _is_spoken_in_range(
    text: str,
    lang: str,
    low: int,
    high: int,
    cut: dict | None,
    config: dict,
) -> bool:
    value = _spoken_amount(text, lang, cut, config)
    return low <= value <= high


def _short_ko_fallback(text: str, low: int, high: int, cut_number: int) -> str:
    """Do not pad short Korean lines locally.

    Generic suffixes visibly damage the script. If the generated line is too
    short, fail validation before saving so the script is regenerated through
    the LLM prompt path, not by mutating generated content with filler.
    """
    return text


def _long_ko_fallback(text: str, low: int, high: int) -> str:
    text = _compact(text)
    removals = [
        "사실 ",
        "정말 ",
        "진짜 ",
        "바로 ",
        "생각보다 ",
        "어쩌면 ",
        "여러분은 ",
    ]
    candidate = text
    for token in removals:
        if token in candidate:
            candidate = _compact(candidate.replace(token, "", 1))
            if _is_in_range(candidate, "ko", low, high):
                return candidate
    return text


def _fit_words_locally(text: str, low: int, high: int, topic: str) -> str:
    words = _word_tokens(text)
    if len(words) > high:
        fitted = " ".join(words[:high])
        suffix = "?" if text.strip().endswith("?") else "."
        return _compact(fitted + suffix)
    return _compact(text)


def _fit_chars_locally(text: str, low: int, high: int, topic: str, lang: str) -> str:
    # Conservative fallback: never pad with topic words or hard-cut CJK text.
    # Bad timing is better than visible garbage such as trailing ". ai".
    return _compact(text)


def _fallback_repair(text: str, lang: str, low: int, high: int, cut_number: int, topic: str = "") -> str:
    text = _compact(text)
    value = _amount(text, lang)
    if low <= value <= high:
        return text
    if lang == "en":
        return _fit_words_locally(text, low, high, topic)
    if lang == "ja":
        return text
    if lang == "ko":
        if value < low:
            repaired = _short_ko_fallback(text, low, high, cut_number)
            if _is_in_range(repaired, lang, low, high):
                return repaired
            return text
        repaired = _long_ko_fallback(text, low, high)
        if _is_in_range(repaired, lang, low, high):
            return repaired
        return text
    return text


async def repair_script_narration_timing(
    script: dict,
    config: dict,
    *,
    topic: str,
    llm_service: Any,
    max_rounds: int = 2,
    log: Callable[[str], None] | None = print,
) -> dict:
    """Repair narration lengths before TTS.

    Free deterministic repair runs first but stays conservative: it must never
    pad with topic words or cut CJK text blindly. Paid one-line LLM rewrite only
    runs when explicitly enabled by config.
    """
    if not isinstance(script, dict):
        return script

    limits = BaseLLMService._calc_narration_limits(config)
    lang = limits.get("lang") or config.get("language", "ko")
    parsed = _parse_range(str(limits.get("target_range") or ""))
    if not parsed:
        return script
    low, high = parsed
    target_units = max(low, min(high, round((low + high) / 2)))
    repair_cap = config.get("script_timing_max_llm_repairs")
    if repair_cap is None:
        repair_cap = 3
    try:
        max_llm_repairs = int(repair_cap)
    except (TypeError, ValueError):
        max_llm_repairs = 3
    max_llm_repairs = max(0, max_llm_repairs)
    try:
        repair_concurrency = int(config.get("script_timing_repair_concurrency") or 4)
    except (TypeError, ValueError):
        repair_concurrency = 4
    repair_concurrency = max(1, min(12, repair_concurrency))

    for round_idx in range(1, max_rounds + 1):
        raise_if_cancelled("script timing repair")
        issues = BaseLLMService.validate_script_timing(script, config)
        if not issues:
            return script
        cuts = script.get("cuts", []) or []
        by_num = {}
        for idx, cut in enumerate(cuts):
            try:
                by_num[int(cut.get("cut_number"))] = (idx, cut)
            except Exception:
                continue

        for issue in issues:
            raise_if_cancelled("script timing local repair")
            cut_number = int(issue.get("cut_number") or 0)
            item = by_num.get(cut_number)
            if not item:
                continue
            _idx, cut = item
            current = _compact(cut.get("narration") or "")
            current_amount = _spoken_amount(current, lang, cut, config)
            fallback = _fallback_repair(current, lang, low, high, cut_number, topic)
            if (
                fallback != current
                and _is_spoken_in_range(fallback, lang, low, high, cut, config)
            ):
                cut["narration"] = fallback
                if log:
                    log(
                        f"[script] timing repaired locally cut {cut_number}: "
                        f"{current_amount}->{_spoken_amount(fallback, lang, cut, config)}"
                    )

        issues = BaseLLMService.validate_script_timing(script, config)
        if not issues:
            return script
        if len(issues) > max_llm_repairs:
            if log:
                log(
                    f"[script] timing LLM repairs disabled/refused: {len(issues)} cuts remain, "
                    f"cap is {max_llm_repairs}"
                )
            return script

        semaphore = asyncio.Semaphore(repair_concurrency)

        async def _rewrite_issue(issue: dict) -> tuple[int, int, str] | None:
            raise_if_cancelled("script timing repair")
            cut_number = int(issue.get("cut_number") or 0)
            item = by_num.get(cut_number)
            if not item:
                return None
            idx, cut = item
            current = _compact(cut.get("narration") or "")
            current_amount = _spoken_amount(current, lang, cut, config)
            direction = "short" if current_amount < low else "long"

            try:
                async with semaphore:
                    raise_if_cancelled("script timing LLM rewrite")
                    if lang == "en":
                        units_per_sec = float(limits.get("words_per_sec") or 2.5)
                    else:
                        units_per_sec = float(limits.get("chars_per_sec") or 8.8)
                    measured_estimate = current_amount / max(0.1, units_per_sec)
                    rewrite = await llm_service.rewrite_narration_for_timing(
                        topic=topic,
                        narration=current,
                        language=lang,
                        cut_number=cut_number,
                        total_cuts=len(cuts),
                        measured_duration=measured_estimate,
                        target_min=float(limits.get("target_min_sec") or app_config.TTS_MIN_DURATION),
                        target_max=float(limits.get("target_max_sec") or app_config.TTS_MAX_DURATION),
                        direction=direction,
                        target_chars=target_units,
                        image_prompt=cut.get("image_prompt") or "",
                        scene_type=cut.get("scene_type") or "",
                        previous_narration=(cuts[idx - 1].get("narration") if idx > 0 else "") or "",
                        next_narration=(cuts[idx + 1].get("narration") if idx + 1 < len(cuts) else "") or "",
                    )
                    raise_if_cancelled("script timing LLM rewrite")
            except OperationCancelled:
                raise
            except Exception as exc:
                if log:
                    log(f"[script] timing LLM repair skipped cut {cut_number}: {exc}")
                return None
            return cut_number, current_amount, _compact(rewrite)

        tasks = [asyncio.create_task(_rewrite_issue(issue)) for issue in issues]
        try:
            rewrites = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

        for result in rewrites:
            if not result:
                continue
            cut_number, current_amount, rewrite = result
            item = by_num.get(cut_number)
            if not item:
                continue
            _idx, cut = item
            rewritten_amount = (
                _spoken_amount(rewrite, lang, cut, config) if rewrite else 0
            )
            if rewrite and low <= rewritten_amount <= high:
                cut["narration"] = rewrite
                if log:
                    log(
                        f"[script] timing repaired by LLM cut {cut_number}: "
                        f"{current_amount}->{rewritten_amount}"
                    )
            elif log:
                log(
                    f"[script] timing LLM repair rejected cut {cut_number}: "
                    f"{current_amount}->{rewritten_amount}, target {low}~{high}"
                )

    return script
