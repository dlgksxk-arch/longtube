from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.routers.image import IMAGE_SINGLE_FRAME_LOCK, _build_image_prompt
from app.services import factory_v5_silla
from app.services.factory_v5_silla import (
    SOURCE_SCHEMA,
    apply_actual_assets_to_cut_rows,
    import_silla_workbook,
    parse_silla_workbook,
)
from app.tasks.pipeline_tasks import _validate_prepared_script


SILLA_EP02 = Path(r"D:\#대본\채널1_신라사\황금의_나라_EP02.xlsx")


def _base_cut(**updates):
    cut = {
        "cut_number": 1,
        "narration": "대사",
        "image_prompt": "one historical scene",
        "visual_year": "57 BCE",
        "visual_period": "late first century BCE",
        "visual_location": "Gyeongju basin",
        "visual_evidence": "source note",
    }
    cut.update(updates)
    return cut


def test_legacy_prepared_script_still_requires_image_prompt():
    payload = {"script_version": "prepared-1.0", "cuts": [_base_cut(image_prompt="")]}
    with pytest.raises(RuntimeError, match="image_prompt"):
        _validate_prepared_script(payload, "legacy.json", expected_cut_count=1)


def test_silla_actual_asset_can_replace_image_prompt():
    payload = {
        "script_version": "prepared-5.0",
        "source_schema": SOURCE_SCHEMA,
        "cuts": [
            _base_cut(
                image_prompt="",
                actual_asset={
                    "source_note": "공공누리 제1유형",
                    "source_sha256": "A" * 64,
                    "source_member": "xl/media/image1.png",
                },
            )
        ],
    }
    _validate_prepared_script(payload, "silla.json", expected_cut_count=1)


@pytest.mark.skipif(not SILLA_EP02.is_file(), reason="local Silla EP02 workbook is unavailable")
def test_real_silla_ep02_contract_and_import(tmp_path: Path):
    parsed = parse_silla_workbook(SILLA_EP02)
    assert parsed.summary["cut_count"] == 150
    assert parsed.summary["krea_prompt_count"] == 145
    assert parsed.summary["actual_asset_count"] == 5
    assert parsed.summary["h3_tag_count"] == 55
    assert parsed.summary["shorts_cut_count"] == 60
    assert parsed.summary["quote_count"] == 5
    assert parsed.summary["emotion_tag_missing_count"] == 0
    assert parsed.summary["caption_error_count"] == 0
    assert sorted(parsed.assets_by_cut) == [136, 137, 138, 139, 140]

    result = import_silla_workbook(parsed, tmp_path)
    prepared = Path(result["prepared_script"])
    payload = json.loads(prepared.read_text(encoding="utf-8"))
    _validate_prepared_script(payload, prepared, expected_cut_count=150)
    actual_cuts = [cut for cut in payload["cuts"] if cut.get("actual_asset")]
    assert len(actual_cuts) == 5
    assert all(Path(cut["actual_asset"]["path"]).is_file() for cut in actual_cuts)


@pytest.mark.skipif(not SILLA_EP02.is_file(), reason="local Silla EP02 workbook is unavailable")
def test_silla_title_length_is_not_rejected(monkeypatch):
    sheet_name, cells, embedded_assets = factory_v5_silla._read_first_sheet(SILLA_EP02)
    title_row = next(
        row
        for (row, column), value in cells.items()
        if column == 1 and str(value).strip() == "에피소드 제목"
    )
    cells[(title_row, 2)] = "글자 수 제한 없이 사용하는 신라사 에피소드 제목"
    monkeypatch.setattr(
        factory_v5_silla,
        "_read_first_sheet",
        lambda _path: (sheet_name, cells, embedded_assets),
    )

    parsed = parse_silla_workbook(SILLA_EP02)

    assert parsed.summary["title"] == "글자 수 제한 없이 사용하는 신라사 에피소드 제목"


def test_actual_asset_is_materialized_as_custom_canonical_image(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (64, 36), (120, 80, 40)).save(source)
    normalized_sha = hashlib.sha256(source.read_bytes()).hexdigest().upper()
    monkeypatch.setattr(factory_v5_silla, "resolve_project_dir", lambda *_args, **_kwargs: tmp_path / "run")
    row = SimpleNamespace(
        image_prompt="prompt",
        image_path=None,
        image_model=None,
        is_custom_image=False,
        status="pending",
    )
    script = {
        "cuts": [
            _base_cut(
                image_prompt="",
                actual_asset={
                    "path": str(source),
                    "source_note": "공공누리 제1유형",
                    "source_sha256": "B" * 64,
                    "normalized_sha256": normalized_sha,
                },
            )
        ]
    }
    assert apply_actual_assets_to_cut_rows("run-id", {}, script, {1: row}) == 1
    assert row.image_path == "images/cut_1.png"
    assert row.image_model == "source-asset"
    assert row.is_custom_image is True
    assert row.status == "completed"
    assert (tmp_path / "run" / "images" / "cut_1.png").is_file()


def test_silla_krea_prompt_adds_single_frame_lock_without_changing_legacy_projects():
    source = "16:9 historical frame of an early Saro council"
    silla_prompt = _build_image_prompt(
        source,
        "",
        image_model="comfyui-krea2",
        style_config={"factory_source_schema": SOURCE_SCHEMA},
    )
    legacy_prompt = _build_image_prompt(
        source,
        "",
        image_model="comfyui-krea2",
        style_config={},
    )
    assert silla_prompt.startswith(IMAGE_SINGLE_FRAME_LOCK)
    assert legacy_prompt == source
