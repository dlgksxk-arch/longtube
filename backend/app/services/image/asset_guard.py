"""Guards that keep generated image files tied to the current cut prompt."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.services.image.prompt_compiler import (
    compile_image_prompt,
    prompt_contract_revision,
    supports_scene_contract_v2_model,
    uses_scene_contract_v2,
)
from app.services.image.prompt_builder import is_canonical_script_image_prompt


_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "beside", "by", "for", "from",
    "in", "into", "is", "it", "its", "of", "on", "or", "the", "their", "them",
    "this", "to", "with", "without", "world", "style", "cartoon", "simple",
    "flat", "clean", "clear", "wide", "composition", "frame", "scene",
    "background", "tone", "only", "prompt", "subject", "action", "setting",
    "period", "props", "visible", "drawn", "illustration",
}

_EQUIV_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("child", ("child", "children", "boy", "girl")),
    ("grasshopper", ("grasshopper", "grasshoppers")),
    ("ant", ("ant", "ants", "anthill")),
    ("seed", ("seed", "seeds", "grain", "grains")),
    ("anthill", ("anthill", "ant hill")),
    ("violin", ("violin", "fiddle")),
    ("guitar", ("guitar",)),
    ("flower", ("flower", "petal")),
    ("snow", ("snow", "snowy", "winter")),
    ("door", ("door", "entrance")),
    ("desk", ("desk", "office")),
    ("folder", ("folder", "folders")),
    ("jar", ("jar", "jars")),
)

_NEGATIVE_PROMPT_STARTS = (
    "anime, manga",
    "blurry, low quality",
    "bad anatomy",
    "photorealistic, hyperrealistic",
)

_PROMPT_POLICY_VERSION = "storybook_guard_v10_scene_contract_3"


def canonical_cut_image_path(project_dir: Path, cut_number: int) -> Path:
    return project_dir / "images" / f"cut_{int(cut_number)}.png"


def cut_image_candidates(project_dir: Path, cut_number: int) -> list[Path]:
    n = int(cut_number)
    return [
        project_dir / "images" / f"cut_{n}.png",
        project_dir / "images" / f"cut_{n:03d}.png",
    ]


def find_existing_cut_image(project_dir: Path, cut_number: int) -> Path | None:
    for path in cut_image_candidates(project_dir, cut_number):
        if path.exists() and path.is_file() and path.stat().st_size > 50:
            return path
    return None


def sidecar_path(image_path: str | Path) -> Path:
    p = Path(image_path)
    return p.with_name(p.name + ".prompt.json")


def _core_prompt(text: str) -> str:
    core = re.split(r"\s*\|\|\s*", text or "", maxsplit=1)[0]
    core = re.split(r"\bStyle/tone only\b", core, maxsplit=1, flags=re.IGNORECASE)[0]
    core = re.sub(r"\b(ColoringBookAF|Coloring Book)\b", " ", core, flags=re.IGNORECASE)
    return core.strip()


def _tokens(text: str) -> set[str]:
    out: set[str] = set()
    for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", _core_prompt(text).lower()):
        token = token.replace("-", " ")
        for part in token.split():
            if len(part) >= 3 and part not in _STOPWORDS:
                out.add(part)
    return out


def prompt_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text or "").strip()
    normalized = f"{_PROMPT_POLICY_VERSION}|{normalized}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def expected_comfyui_positive_prompt(
    final_prompt: str,
    *,
    image_model: str,
    prompt_profile: str,
) -> str:
    if is_canonical_script_image_prompt(final_prompt):
        return str(final_prompt).strip()
    if not final_prompt or not uses_scene_contract_v2(prompt_profile):
        return ""
    if not supports_scene_contract_v2_model(image_model):
        return ""
    positive = compile_image_prompt(final_prompt, model_id=image_model).positive
    # ComfyUI applies the LongTube rendering lock after compiling the scene
    # contract.  Resume validation must reproduce that exact final positive
    # prompt; comparing against the pre-style compiler output marks every valid
    # Z-Image sidecar stale and needlessly overwrites manually approved cuts.
    from app.services.image.comfyui_service import (
        _LONGTUBE_DARK_MANHWA_STYLE_MODELS,
        _apply_longtube_dark_manhwa_style,
        _flux2_baekje_ep06_visual_direction,
        _promote_comfyui_lock_to_front,
    )

    if image_model in _LONGTUBE_DARK_MANHWA_STYLE_MODELS:
        positive = _apply_longtube_dark_manhwa_style(
            positive,
            model_id=image_model,
        )
    if image_model == "comfyui-flux2-klein-9b":
        baekje_ep06_visual_direction = _flux2_baekje_ep06_visual_direction(
            final_prompt
        )
        if baekje_ep06_visual_direction:
            positive = _promote_comfyui_lock_to_front(
                positive,
                baekje_ep06_visual_direction,
            )
    return positive


def _retry_corrected_positive_matches_current_compiler(
    meta: dict[str, Any],
    *,
    final_prompt: str,
    image_model: str,
) -> bool:
    """Accept a saved detector-retry prompt only when the current compiler reproduces it exactly."""
    actual = str(meta.get("comfyui_positive_prompt") or "")
    match = re.search(
        r"\bRetry\s+correction:\s*(.*?)(?:\s+Style:|$)",
        actual,
        re.IGNORECASE | re.DOTALL,
    )
    if not match or not final_prompt or not image_model:
        return False
    quality_hint = match.group(1).strip().rstrip(" .")
    if not quality_hint:
        return False
    rebuilt = compile_image_prompt(
        final_prompt,
        model_id=image_model,
        quality_hint=quality_hint,
    ).positive
    return bool(rebuilt) and meta.get("comfyui_positive_prompt_hash") == prompt_hash(rebuilt)


def write_prompt_sidecar(
    image_path: str | Path,
    *,
    cut_number: int,
    image_model: str,
    source_prompt: str,
    final_prompt: str,
    narration: str = "",
    comfyui_positive_prompt: str = "",
    comfyui_negative_prompt: str = "",
    effective_image_model: str = "",
) -> None:
    path = sidecar_path(image_path)
    payload = {
        "cut_number": int(cut_number),
        "image_model": image_model,
        "prompt_policy_version": _PROMPT_POLICY_VERSION,
        "source_prompt_hash": prompt_hash(source_prompt or ""),
        "final_prompt_hash": prompt_hash(final_prompt or ""),
        "source_prompt": source_prompt or "",
        "final_prompt": final_prompt or "",
        "narration": narration or "",
    }
    contract_revision = prompt_contract_revision(final_prompt or source_prompt)
    if contract_revision:
        payload["prompt_contract_revision"] = contract_revision
    if comfyui_positive_prompt:
        payload["comfyui_positive_prompt_hash"] = prompt_hash(comfyui_positive_prompt)
        payload["comfyui_positive_prompt"] = comfyui_positive_prompt
    if comfyui_negative_prompt:
        payload["comfyui_negative_prompt"] = comfyui_negative_prompt
    if effective_image_model and effective_image_model != image_model:
        payload["effective_image_model"] = effective_image_model
    # The sidecar is the commit marker for a generated cut.  Write it
    # atomically so a restart cannot leave a half-written file that is counted
    # as completed.
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def image_has_prompt_sidecar_commit(
    image_path: str | Path,
    *,
    cut_number: int | None = None,
    verify_image: bool = False,
) -> bool:
    """Return True only when both the image and its valid commit marker exist."""
    image = Path(image_path)
    if not image.exists() or not image.is_file() or image.stat().st_size <= 50:
        return False
    if verify_image:
        try:
            from PIL import Image

            with Image.open(image) as opened:
                opened.verify()
        except Exception:
            return False
    meta = _read_prompt_sidecar(image)
    if not isinstance(meta, dict):
        return False
    if cut_number is not None:
        try:
            if int(meta.get("cut_number")) != int(cut_number):
                return False
        except (TypeError, ValueError):
            return False
    return bool(
        str(meta.get("image_model") or "").strip()
        and str(meta.get("source_prompt_hash") or "").strip()
        and str(meta.get("final_prompt_hash") or "").strip()
    )


def _read_prompt_sidecar(image_path: str | Path) -> dict[str, Any] | None:
    path = sidecar_path(image_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _positive_png_prompts(image_path: str | Path) -> list[str]:
    try:
        from PIL import Image

        raw = Image.open(image_path).info.get("prompt")
        if not raw:
            return []
        graph = json.loads(raw)
    except Exception:
        return []

    texts: list[str] = []
    for node in (graph or {}).values():
        if not isinstance(node, dict) or node.get("class_type") != "CLIPTextEncode":
            continue
        text = str((node.get("inputs") or {}).get("text") or "")
        lower = text.strip().lower()
        if any(lower.startswith(marker) for marker in _NEGATIVE_PROMPT_STARTS):
            continue
        if text.strip():
            texts.append(text)
    return texts


def _critical_group_failures(expected: str, actual: str) -> list[str]:
    exp_l = _core_prompt(expected).lower()
    act_l = _core_prompt(actual).lower()
    failures: list[str] = []
    for label, terms in _EQUIV_GROUPS:
        if any(re.search(rf"\b{re.escape(term)}s?\b", exp_l) for term in terms):
            if not any(re.search(rf"\b{re.escape(term)}s?\b", act_l) for term in terms):
                failures.append(label)
    return failures


def image_matches_prompt(
    image_path: str | Path,
    *,
    source_prompt: str,
    final_prompt: str = "",
    image_model: str = "",
    comfyui_positive_prompt: str = "",
    effective_image_model: str = "",
) -> tuple[bool, str]:
    p = Path(image_path)
    if not p.exists() or not p.is_file() or p.stat().st_size <= 50:
        return False, "missing_or_too_small"

    meta = _read_prompt_sidecar(p)
    if meta:
        if image_model and meta.get("image_model") and meta.get("image_model") != image_model:
            return False, "sidecar_model_mismatch"
        if effective_image_model:
            actual_effective_model = str(
                meta.get("effective_image_model") or meta.get("image_model") or ""
            ).strip()
            if actual_effective_model and actual_effective_model != effective_image_model:
                return False, "sidecar_effective_model_mismatch"
        expected_contract_revision = prompt_contract_revision(final_prompt or source_prompt)
        if expected_contract_revision and meta.get("prompt_contract_revision") != expected_contract_revision:
            return False, "sidecar_prompt_contract_mismatch"
        if comfyui_positive_prompt and meta.get("comfyui_positive_prompt_hash") != prompt_hash(
            comfyui_positive_prompt
        ):
            final_hash_matches = bool(
                final_prompt and meta.get("final_prompt_hash") == prompt_hash(final_prompt)
            )
            source_hash_matches = bool(
                not source_prompt or meta.get("source_prompt_hash") == prompt_hash(source_prompt)
            )
            if not (
                final_hash_matches
                and source_hash_matches
                and _retry_corrected_positive_matches_current_compiler(
                    meta,
                    final_prompt=final_prompt,
                    image_model=image_model,
                )
            ):
                return False, "sidecar_comfyui_positive_prompt_mismatch"
        if final_prompt:
            if meta.get("final_prompt_hash") == prompt_hash(final_prompt):
                return True, "sidecar_final_prompt_match"
            return False, "sidecar_final_prompt_mismatch"
        if source_prompt and meta.get("source_prompt_hash") == prompt_hash(source_prompt):
            return True, "sidecar_source_prompt_match"
        return False, "sidecar_prompt_mismatch"
    if final_prompt:
        return False, "missing_prompt_sidecar"

    expected = source_prompt or final_prompt
    if not expected:
        return True, "no_expected_prompt"

    positives = _positive_png_prompts(p)
    if not positives:
        return False, "no_positive_prompt_metadata"

    expected_tokens = _tokens(expected)
    if not expected_tokens:
        return True, "no_expected_tokens"

    best_score = 0.0
    best_reason = "prompt_token_mismatch"
    for actual in positives:
        failures = _critical_group_failures(expected, actual)
        if failures:
            best_reason = "missing_critical_terms:" + ",".join(failures)
            continue
        actual_tokens = _tokens(actual)
        score = len(expected_tokens & actual_tokens) / max(1, len(expected_tokens))
        if score > best_score:
            best_score = score
        if score >= 0.52:
            return True, f"png_prompt_token_match:{score:.2f}"
    return False, f"{best_reason}:{best_score:.2f}"
