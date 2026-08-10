from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.tasks.pipeline_tasks import _validate_prepared_script  # noqa: E402
from scripts.ch1_baekje_workbook_to_prepared_scripts import (  # noqa: E402
    CJK_RE,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_WORKBOOK,
    TEMPLATE_PROJECT_ID,
    build_prepared_scripts,
)


CHANNEL = 1
SERIES_NAME = "백제사"
EXPECTED_EPISODES = 40
EXPECTED_CUTS_PER_EPISODE = 150
EXPECTED_TOTAL_CUTS = EXPECTED_EPISODES * EXPECTED_CUTS_PER_EPISODE
EXPECTED_CLEANED_PROMPTS = 0
EXPECTED_SHORTS_CUTS = 2293
EXPECTED_SOURCE_SHA256 = "B99193FE2645311E0CD6DF39309E029467D42BE4645830B5797C6DB7710EA137"
QUEUE_ID_RE = re.compile(r"^ch1-baekje-ep(\d{3})$")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _canonical_script(payload: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(payload)
    source = result.get("source")
    if isinstance(source, dict):
        source["created_at"] = "<generated-at>"
    return result


def _queue_item(
    *,
    episode_number: int,
    episode_code: str,
    title: str,
    source_sheet: str,
    queued_at: str,
) -> dict[str, Any]:
    return {
        "id": f"ch1-baekje-ep{episode_number:03d}",
        "topic": title,
        "template_project_id": TEMPLATE_PROJECT_ID,
        "target_duration": 600,
        "target_cuts": EXPECTED_CUTS_PER_EPISODE,
        "channel": CHANNEL,
        "openings": [],
        "endings": [],
        "core_content": (
            f"[Prepared Script] {episode_code}_script.json\n"
            f"[Source Workbook Sheet] {source_sheet}\n"
            f"[Cuts] {EXPECTED_CUTS_PER_EPISODE}\n"
            "[Series] 백제사"
        ),
        "episode_number": episode_number,
        "series": SERIES_NAME,
        "episode_code": episode_code,
        "episode_id": episode_code,
        "next_episode_preview": "",
        "queued_source": "import",
        "queued_at": queued_at,
        "queued_note": "백제사 통합대본 / 준비 대본 검증 완료",
        "requeued_from_task_id": "",
        "restored_from_project_id": "",
        "status": "pending",
    }


def build_queue_items(
    workbook_path: Path,
    prepared_dir: Path,
    *,
    queued_at: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    workbook_path = workbook_path.resolve()
    prepared_dir = prepared_dir.resolve()
    canonical_scripts, canonical_manifest = build_prepared_scripts(workbook_path)
    if canonical_manifest["source_sha256"] != EXPECTED_SOURCE_SHA256:
        raise ValueError(
            "원본 통합대본 SHA-256 불일치: "
            f"{canonical_manifest['source_sha256']} != {EXPECTED_SOURCE_SHA256}"
        )
    expected_manifest_values = {
        "episode_count": EXPECTED_EPISODES,
        "cut_count": EXPECTED_TOTAL_CUTS,
        "unique_image_prompt_count": EXPECTED_TOTAL_CUTS,
        "pipeline_unique_image_prompt_count": EXPECTED_TOTAL_CUTS,
        "cleaned_prompt_count": EXPECTED_CLEANED_PROMPTS,
        "shorts_cut_count": EXPECTED_SHORTS_CUTS,
    }
    for key, expected in expected_manifest_values.items():
        actual = canonical_manifest.get(key)
        if actual != expected:
            raise ValueError(f"변환 결과 {key} 불일치: {actual!r} != {expected!r}")

    manifest_path = prepared_dir / "백제사_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"준비 대본 manifest 누락: {manifest_path}")
    written_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in (
        "source_workbook",
        "source_sha256",
        "source_size",
        "source_contract",
        "episode_count",
        "cut_count",
        "unique_image_prompt_count",
        "pipeline_unique_image_prompt_count",
        "cleaned_prompt_count",
        "shorts_cut_count",
    ):
        if written_manifest.get(key) != canonical_manifest.get(key):
            raise ValueError(
                f"준비 대본 manifest {key} 불일치: "
                f"{written_manifest.get(key)!r} != {canonical_manifest.get(key)!r}"
            )

    manifest_files = {
        Path(str(entry.get("path") or "")).name: str(entry.get("sha256") or "")
        for entry in written_manifest.get("files") or []
        if isinstance(entry, dict)
    }
    if len(manifest_files) != EXPECTED_EPISODES:
        raise ValueError(
            f"준비 대본 manifest 파일 수 불일치: {len(manifest_files)} != {EXPECTED_EPISODES}"
        )

    queued_at = queued_at or _utc_timestamp()
    items: list[dict[str, Any]] = []
    file_hashes: dict[str, str] = {}
    total_cuts = 0
    total_shorts = 0
    for episode_number, expected_script in enumerate(canonical_scripts, start=1):
        episode_code = f"백제사-EP{episode_number:02d}"
        filename = f"{episode_code}_script.json"
        script_path = prepared_dir / filename
        if not script_path.is_file():
            raise FileNotFoundError(f"준비 대본 누락: {script_path}")
        actual_hash = _sha256(script_path)
        if manifest_files.get(filename) != actual_hash:
            raise ValueError(
                f"준비 대본 SHA-256 불일치: {filename} "
                f"{actual_hash} != {manifest_files.get(filename)!r}"
            )
        actual_script = json.loads(script_path.read_text(encoding="utf-8"))
        if _canonical_script(actual_script) != _canonical_script(expected_script):
            raise ValueError(f"준비 대본이 현재 변환 로직 결과와 다릅니다: {filename}")
        _validate_prepared_script(
            actual_script,
            script_path,
            expected_cut_count=EXPECTED_CUTS_PER_EPISODE,
        )
        cuts = actual_script.get("cuts") or []
        for cut in cuts:
            prompt = str(cut.get("image_prompt") or "")
            narration = str(cut.get("narration") or "")
            if CJK_RE.search(prompt):
                raise ValueError(
                    f"이미지 프롬프트 CJK 잔존: {episode_code} cut {cut.get('cut_number')}"
                )
            if narration and narration in prompt:
                raise ValueError(
                    f"이미지 프롬프트 대사 복제: {episode_code} cut {cut.get('cut_number')}"
                )
        total_cuts += len(cuts)
        total_shorts += sum(bool(cut.get("shorts_candidate")) for cut in cuts)
        file_hashes[filename] = actual_hash
        items.append(
            _queue_item(
                episode_number=episode_number,
                episode_code=episode_code,
                title=str(actual_script["topic"]),
                source_sheet=f"{episode_number:02d}화",
                queued_at=queued_at,
            )
        )

    if total_cuts != EXPECTED_TOTAL_CUTS:
        raise ValueError(f"준비 대본 전체 컷 수 불일치: {total_cuts}")
    if total_shorts != EXPECTED_SHORTS_CUTS:
        raise ValueError(f"준비 대본 숏츠 컷 수 불일치: {total_shorts}")
    expected_ids = {f"ch1-baekje-ep{number:03d}" for number in range(1, 41)}
    actual_ids = {str(item["id"]) for item in items}
    if actual_ids != expected_ids or len(items) != EXPECTED_EPISODES:
        raise ValueError("백제사 큐 항목 ID 구성 불일치")
    actual_numbers = [int(item["episode_number"]) for item in items]
    actual_codes = [str(item["episode_code"]) for item in items]
    actual_episode_ids = [str(item["episode_id"]) for item in items]
    expected_numbers = list(range(1, EXPECTED_EPISODES + 1))
    expected_codes = [f"백제사-EP{number:02d}" for number in expected_numbers]
    if actual_numbers != expected_numbers:
        raise ValueError(f"백제사 큐 회차 순서 불일치: {actual_numbers!r}")
    if actual_codes != expected_codes or actual_episode_ids != expected_codes:
        raise ValueError("백제사 큐 episode_code/episode_id 순서 불일치")
    for item in items:
        match = QUEUE_ID_RE.fullmatch(str(item["id"]))
        if not match or int(match.group(1)) != int(item["episode_number"]):
            raise ValueError(f"큐 ID/회차 불일치: {item!r}")

    report = {
        "workbook": str(workbook_path),
        "workbook_sha256": canonical_manifest["source_sha256"],
        "prepared_dir": str(prepared_dir),
        "episode_count": len(items),
        "cut_count": total_cuts,
        "cleaned_prompt_count": canonical_manifest["cleaned_prompt_count"],
        "pipeline_unique_image_prompt_count": canonical_manifest[
            "pipeline_unique_image_prompt_count"
        ],
        "shorts_cut_count": total_shorts,
        "queued_at": queued_at,
        "first_item": items[0],
        "last_item": items[-1],
        "prepared_file_sha256": file_hashes,
    }
    return items, report


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(DEFAULT_WORKBOOK))
    parser.add_argument("--prepared-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output")
    args = parser.parse_args()

    items, report = build_queue_items(
        Path(args.input),
        Path(args.prepared_dir),
    )
    result = dict(report)
    result["items"] = items
    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output_path)
        result["output"] = str(output_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
