"""Synchronize reviewed captions into the current pending prepared scripts.

The current prepared script is authoritative for production narration. Caption
text must match the reviewed checkpoint and its workbook cell exactly. Existing
narration differences are reported and narration is never modified.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts.ch4_time_explorers_workbook_to_prepared_scripts import (  # noqa: E402
    _load_xlsx_workbook,
    _row_value,
)


CAPTION_HEADER = "한국식 예능 자막 (전 컷 수록)"
CAPTION_MARKER_RE = re.compile(r"\*\*[^*]+\*\*")
LEADING_AUDIO_TAGS_RE = re.compile(
    r"^\s*(?:\[[a-z][a-z0-9_ -]{0,31}\]\s*)+",
    re.IGNORECASE,
)
EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "]+"
)

CH1_WORKBOOK = Path(
    r"Z:\HDD2\longtube\CH1 10분역공\2. 삼한시대\백제사\백제사_01-40화_6000컷_통합대본_최종검수완료.xlsx"
)
CH3_WORKBOOK = Path(
    r"Z:\HDD2\longtube\CH3 일본역사\제1장\제1장_대본_수정본_20260707.xlsx"
)
CH4_WORKBOOK_01_13 = Path(
    r"Z:\HDD2\longtube\CH4 시간탐구회\대본\#기괴와변칙의세계사_시즌1_1-13.xlsx"
)
CH4_WORKBOOK_20_31 = Path(
    r"Z:\HDD2\longtube\CH4 시간탐구회\대본\#기괴와변칙의세계사_시즌1_20-31.xlsx"
)

PREPARED_ROOTS = {
    "CH1": Path(
        r"C:\Users\Ai_M9\Desktop\longsult\_system\projects\f60d6b0b\prepared_scripts"
    ),
    "CH3": Path(
        r"C:\Users\Ai_M9\Desktop\longsult\channels\CH3\projects\7d8b63e5\prepared_scripts"
    ),
    "CH4": Path(
        r"C:\Users\Ai_M9\Desktop\longsult\channels\CH4\projects\83cca89d\prepared_scripts"
    ),
}

CHECKPOINT_PATH = (
    BACKEND_DIR.parent
    / ".codex_tmp"
    / "variety-captions-all"
    / "caption_checkpoint.json"
)

TARGET_EPISODES = {
    "CH1": tuple(range(16, 41)),
    "CH3": tuple(range(16, 41)),
    "CH4": (11, 12, 13, *range(20, 32)),
}

EPISODE_PREFIX = {
    "CH1": "백제사-EP",
    "CH3": "CH3_C1_EP",
    "CH4": "CH4-WH-S01-EP",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _visible_caption(value: str) -> str:
    return value.replace("**", "")


def _caption_errors(value: str, channel: str) -> list[str]:
    errors: list[str] = []
    visible = _visible_caption(value)
    if not 10 <= len(visible) <= 15:
        errors.append(f"visible_length={len(visible)}")
    if value.count("**") != 2 or CAPTION_MARKER_RE.search(value) is None:
        errors.append("keyword_marker")
    if EMOJI_RE.search(value):
        errors.append("emoji")
    if re.search(r"[`#_~<>]", value):
        errors.append("other_markdown")
    if channel in {"CH1", "CH4"}:
        if re.search(r"[가-힣]", visible) is None:
            errors.append("missing_korean")
        if re.search(r"[ぁ-んァ-ヶ]", visible):
            errors.append("mixed_japanese")
    if channel == "CH3":
        if re.search(r"[ぁ-んァ-ヶ一-龠々]", visible) is None:
            errors.append("missing_japanese")
        if re.search(r"[가-힣]", visible):
            errors.append("mixed_korean")
    return errors


def _normalize_narration(value: str, channel: str) -> str:
    text = _text(value)
    if channel == "CH4":
        text = LEADING_AUDIO_TAGS_RE.sub("", text).strip()
    if channel == "CH3":
        return re.sub(r"\s+", "", text)
    return re.sub(r"\s+", " ", text)


def _find_prepared_file(channel: str, episode: int) -> tuple[Path, dict[str, Any]]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for path in PREPARED_ROOTS[channel].glob("*.json"):
        if path.name.lower().endswith("manifest.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        code = _text(payload.get("episode_code") or payload.get("episode_id"))
        if (
            int(payload.get("episode_number") or -1) == episode
            and code.startswith(EPISODE_PREFIX[channel])
            and isinstance(payload.get("cuts"), list)
        ):
            matches.append((path, payload))
    if len(matches) != 1:
        raise ValueError(
            f"{channel} EP{episode}: prepared script count={len(matches)}, "
            f"files={[str(path) for path, _payload in matches]!r}"
        )
    return matches[0]


def _workbook_for(channel: str, episode: int) -> Path:
    if channel == "CH1":
        return CH1_WORKBOOK
    if channel == "CH3":
        return CH3_WORKBOOK
    return CH4_WORKBOOK_01_13 if episode <= 13 else CH4_WORKBOOK_20_31


def _sheet_name(channel: str, episode: int, prepared: dict[str, Any]) -> str:
    if channel == "CH1":
        return f"{episode:02d}화"
    return _text(prepared.get("source_sheet") or episode)


def _source_row(channel: str, cut_number: int, cut: dict[str, Any]) -> int:
    if channel == "CH1":
        return cut_number + 9
    if channel == "CH3":
        match = re.search(r"\brow\s+(\d+)\b", _text(cut.get("visual_evidence")), re.I)
        return int(match.group(1)) if match else cut_number + 7
    match = re.search(r"\brow=(\d+)\b", _text(cut.get("visual_evidence")), re.I)
    if match is None:
        raise ValueError(f"CH4 cut {cut_number}: source row missing from visual_evidence")
    return int(match.group(1))


def _header_row(channel: str) -> int:
    return 7 if channel == "CH3" else 9


def _narration_column(channel: str) -> int:
    if channel == "CH1":
        return 3
    if channel == "CH3":
        return 2
    return 4


def _load_workbooks() -> dict[Path, dict[str, dict[int, dict[int, str]]]]:
    paths = {CH1_WORKBOOK, CH3_WORKBOOK, CH4_WORKBOOK_01_13, CH4_WORKBOOK_20_31}
    loaded: dict[Path, dict[str, dict[int, dict[int, str]]]] = {}
    for workbook_path in paths:
        loaded[workbook_path] = {
            sheet_name: rows
            for sheet_name, rows in _load_xlsx_workbook(workbook_path)
        }
    return loaded


def build_updates() -> list[dict[str, Any]]:
    workbooks = _load_workbooks()
    checkpoint = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    updates: list[dict[str, Any]] = []
    total_cuts = 0
    for channel, episodes in TARGET_EPISODES.items():
        for episode in episodes:
            prepared_path, payload = _find_prepared_file(channel, episode)
            workbook_path = _workbook_for(channel, episode)
            sheet_name = _sheet_name(channel, episode, payload)
            try:
                rows = workbooks[workbook_path][sheet_name]
            except KeyError as exc:
                raise ValueError(
                    f"{channel} EP{episode}: source sheet missing {workbook_path}!{sheet_name}"
                ) from exc
            header = _row_value(rows, _header_row(channel), 5)
            if header != CAPTION_HEADER:
                raise ValueError(
                    f"{channel} EP{episode}: caption header mismatch {header!r}"
                )
            seen_rows: set[int] = set()
            existing_mismatch_count = 0
            narration_mismatch_count = 0
            key = f"{channel}-EP{episode}"
            checkpoint_episode = checkpoint["episodes"][key]
            checkpoint_source = Path(checkpoint_episode["source_path"]).resolve()
            if checkpoint_source != prepared_path.resolve():
                raise ValueError(
                    f"{key}: checkpoint source mismatch "
                    f"{checkpoint_source} != {prepared_path.resolve()}"
                )
            checkpoint_captions = checkpoint_episode["captions"]
            for cut in payload["cuts"]:
                cut_number = int(cut.get("cut_number") or 0)
                row = _source_row(channel, cut_number, cut)
                if row in seen_rows:
                    raise ValueError(f"{channel} EP{episode}: duplicate source row {row}")
                seen_rows.add(row)
                source_narration = _row_value(rows, row, _narration_column(channel))
                prepared_narration = _text(cut.get("narration"))
                if _normalize_narration(source_narration, channel) != _normalize_narration(
                    prepared_narration,
                    channel,
                ):
                    narration_mismatch_count += 1
                caption = _text(checkpoint_captions.get(str(cut_number)))
                workbook_caption = _row_value(rows, row, 5)
                if workbook_caption != caption:
                    raise ValueError(
                        f"{channel} EP{episode} cut {cut_number}: "
                        "workbook/checkpoint caption mismatch"
                    )
                errors = _caption_errors(caption, channel)
                if errors:
                    raise ValueError(
                        f"{channel} EP{episode} cut {cut_number}: invalid caption {errors}: {caption!r}"
                    )
                if _text(cut.get("highlight_caption")) != caption:
                    existing_mismatch_count += 1
                cut["highlight_caption"] = caption
                total_cuts += 1
            updates.append(
                {
                    "channel": channel,
                    "episode": episode,
                    "path": prepared_path,
                    "payload": payload,
                    "cut_count": len(payload["cuts"]),
                    "workbook": workbook_path,
                    "sheet": sheet_name,
                    "existing_mismatch_count": existing_mismatch_count,
                    "narration_mismatch_count": narration_mismatch_count,
                }
            )
    if len(updates) != 65 or total_cuts != 9661:
        raise ValueError(f"target mismatch: episodes={len(updates)}, cuts={total_cuts}")
    return updates


def write_updates(updates: list[dict[str, Any]], backup_dir: Path) -> dict[str, Any]:
    backup_dir.mkdir(parents=True, exist_ok=False)
    files: list[dict[str, Any]] = []
    for item in updates:
        source = item["path"]
        channel_dir = backup_dir / item["channel"]
        channel_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, channel_dir / source.name)
        temporary = source.with_suffix(source.suffix + ".caption.tmp")
        temporary.write_text(
            json.dumps(item["payload"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(source)
        files.append(
            {
                "channel": item["channel"],
                "episode": item["episode"],
                "path": str(source),
                "cut_count": item["cut_count"],
                "workbook": str(item["workbook"]),
                "sheet": item["sheet"],
            }
        )
    return {
        "episode_count": len(files),
        "cut_count": sum(item["cut_count"] for item in files),
        "existing_mismatch_count": sum(
            item["existing_mismatch_count"] for item in updates
        ),
        "narration_mismatch_count": sum(
            item["narration_mismatch_count"] for item in updates
        ),
        "files": files,
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--backup-dir")
    parser.add_argument("--report")
    args = parser.parse_args()

    updates = build_updates()
    result: dict[str, Any] = {
        "write": bool(args.write),
        "episode_count": len(updates),
        "cut_count": sum(item["cut_count"] for item in updates),
        "targets": [
            {
                "channel": item["channel"],
                "episode": item["episode"],
                "path": str(item["path"]),
                "cut_count": item["cut_count"],
                "existing_mismatch_count": item["existing_mismatch_count"],
                "narration_mismatch_count": item["narration_mismatch_count"],
            }
            for item in updates
        ],
    }
    result["existing_mismatch_count"] = sum(
        item["existing_mismatch_count"] for item in updates
    )
    result["narration_mismatch_count"] = sum(
        item["narration_mismatch_count"] for item in updates
    )
    if args.write:
        if not args.backup_dir:
            raise ValueError("--backup-dir is required with --write")
        result = write_updates(updates, Path(args.backup_dir))
        result["write"] = True
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        Path(args.report).write_text(content, encoding="utf-8")
    print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
