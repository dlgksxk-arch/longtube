from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from transformers import MarianMTModel, MarianTokenizer

from scripts import rewrite_remaining_text_risk_prompts as rewrite


MODELS = {
    "ja": "Helsinki-NLP/opus-mt-ja-en",
    "ko": "Helsinki-NLP/opus-mt-ko-en",
}


def _targets() -> dict[str, list[tuple[str, str]]]:
    grouped: dict[str, list[tuple[str, str]]] = {"ja": [], "ko": []}
    for row in rewrite._collect_remaining_scripts():
        language = "ja" if int(row["channel"]) == 3 else "ko"
        for cut in row["payload"].get("cuts") or []:
            if not isinstance(cut, dict):
                continue
            if not rewrite._risk_categories(rewrite._compact(cut.get("image_prompt"))):
                continue
            cut_number = int(cut.get("cut_number") or 0)
            key = rewrite._translation_key(
                channel=int(row["channel"]),
                episode_number=int(row["episode_number"]),
                cut_number=cut_number,
            )
            grouped[language].append((key, rewrite._compact(cut.get("narration"))))
    return grouped


def build(output: Path, *, batch_size: int) -> dict[str, object]:
    grouped = _targets()
    translations: dict[str, str] = {}
    if output.exists():
        existing = json.loads(output.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and isinstance(existing.get("translations"), dict):
            translations = {
                str(key): rewrite._compact(value)
                for key, value in existing["translations"].items()
                if rewrite._compact(value)
            }
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"DEVICE {device}", flush=True)
    for language in ("ja", "ko"):
        rows = [row for row in grouped[language] if row[0] not in translations]
        print(f"LOAD {language} model={MODELS[language]} targets={len(rows)}", flush=True)
        tokenizer = MarianTokenizer.from_pretrained(MODELS[language])
        model = MarianMTModel.from_pretrained(MODELS[language]).to(device)
        model.eval()
        for start in range(0, len(rows), batch_size):
            batch = rows[start:start + batch_size]
            encoded = tokenizer(
                [text for _, text in batch],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=256,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            with torch.inference_mode():
                generated = model.generate(**encoded, max_new_tokens=160)
            decoded = tokenizer.batch_decode(generated, skip_special_tokens=True)
            for (key, _), translated in zip(batch, decoded, strict=True):
                value = rewrite._compact(translated)
                if not value:
                    raise RuntimeError(f"empty translation: {key}")
                translations[key] = value
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    {
                        "version": "remaining-text-risk-translation-v1",
                        "status": "running",
                        "translated_count": len(translations),
                        "translations": translations,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            print(f"PROGRESS {language} {min(start + len(batch), len(rows))}/{len(rows)}", flush=True)
        del model
        del tokenizer
        if device == "cuda":
            torch.cuda.empty_cache()

    expected = sum(len(rows) for rows in grouped.values())
    if len(translations) != expected:
        raise RuntimeError(f"translation count mismatch: {len(translations)} != {expected}")
    payload = {
        "version": "remaining-text-risk-translation-v1",
        "target_count": expected,
        "status": "complete",
        "counts": {language: len(rows) for language, rows in grouped.items()},
        "translations": translations,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()
    result = build(args.output, batch_size=max(1, args.batch_size))
    print(json.dumps({key: result[key] for key in ("version", "target_count", "counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
