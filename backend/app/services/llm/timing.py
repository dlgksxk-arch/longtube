"""Script-level narration timing repair.

The voice step must keep narration as-is. This module repairs narration length
immediately after script generation, before the script is saved or TTS is run.
"""
from __future__ import annotations

import re
from typing import Any, Callable

from app import config as app_config
from app.services.cancel_ctx import OperationCancelled, raise_if_cancelled
from app.services.llm.base import BaseLLMService


def _compact(text: str) -> str:
    return " ".join((text or "").split()).strip()


def _amount(text: str, lang: str) -> int:
    if lang in ("ko", "ja"):
        return len(text)

    return len(re.findall(r"\b[\w']+\b", text))


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
            current_amount = _amount(current, lang)
            fallback = _fallback_repair(current, lang, low, high, cut_number, topic)
            if fallback != current and _is_in_range(fallback, lang, low, high):
                cut["narration"] = fallback
                if log:
                    log(
                        f"[script] timing repaired locally cut {cut_number}: "
                        f"{current_amount}->{_amount(fallback, lang)}"
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

        for issue in issues:
            raise_if_cancelled("script timing repair")
            cut_number = int(issue.get("cut_number") or 0)
            item = by_num.get(cut_number)
            if not item:
                continue
            idx, cut = item
            current = _compact(cut.get("narration") or "")
            current_amount = _amount(current, lang)
            direction = "short" if current_amount < low else "long"

            try:
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
                    target_min=app_config.TTS_MIN_DURATION,
                    target_max=app_config.TTS_MAX_DURATION,
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
                continue

            rewrite = _compact(rewrite)
            if rewrite and _is_in_range(rewrite, lang, low, high):
                cut["narration"] = rewrite
                if log:
                    log(
                        f"[script] timing repaired by LLM cut {cut_number}: "
                        f"{current_amount}->{_amount(rewrite, lang)}"
                    )

    return script
