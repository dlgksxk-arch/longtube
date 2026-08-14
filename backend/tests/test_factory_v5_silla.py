from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import apply_main_caption_delivery_policy
from app.routers.image import IMAGE_SINGLE_FRAME_LOCK, _build_image_prompt
from app.services import factory_v5_silla, oneclick_service
from app.services.factory_v5_silla import (
    SOURCE_SCHEMA,
    apply_actual_assets_to_cut_rows,
    import_silla_workbook,
    parse_silla_workbook,
)
from app.tasks.pipeline_tasks import _validate_prepared_script


SILLA_EP02 = Path(r"D:\#대본\채널1_신라사\황금의_나라_EP02.xlsx")
SILLA_EP03 = Path(r"D:\#대본\채널1_신라사\황금의_나라_EP03.xlsx")
SILLA_EP04 = Path(r"D:\#대본\채널1_신라사\황금의_나라_EP04.xlsx")


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


@pytest.mark.skipif(not SILLA_EP02.is_file(), reason="local Silla EP02 workbook is unavailable")
def test_silla_actual_asset_is_allowed_in_shorts(monkeypatch):
    sheet_name, source_cells, embedded_assets = factory_v5_silla._read_first_sheet(SILLA_EP02)
    cells = dict(source_cells)
    header_row = factory_v5_silla._find_cut_header(cells)
    actual_row = header_row + 136
    moved_short_row = next(
        row
        for (row, column), value in cells.items()
        if column == 2 and str(value).strip() == "S4-15"
    )
    cells[(actual_row, 2)] = "S4-15"
    cells[(moved_short_row, 2)] = ""
    cells[(moved_short_row, 15)] = ""
    monkeypatch.setattr(
        factory_v5_silla,
        "_read_first_sheet",
        lambda _path: (sheet_name, cells, embedded_assets),
    )

    parsed = parse_silla_workbook(SILLA_EP02)
    cut = parsed.payload["cuts"][135]

    assert cut["actual_asset"]
    assert cut["shorts_candidate"] is True
    assert cut["shorts_group"] == 4
    assert cut["shorts_order"] == 15
    assert cut["image_prompt"] == ""
    assert cut["video_tag"] == ""


def test_source_usage_contract_accepts_public_domain_and_rejects_missing_terms():
    assert factory_v5_silla._has_source_usage_contract(
        "Natural Earth public domain: https://www.naturalearthdata.com/"
    )
    assert factory_v5_silla._has_source_usage_contract(
        "국가유산청 공공누리 제1유형 https://www.heritage.go.kr/"
    )
    assert not factory_v5_silla._has_source_usage_contract(
        "출처만 있음: https://example.com/source"
    )
    assert not factory_v5_silla._has_source_usage_contract(
        "공공누리 제1유형이지만 URL 없음"
    )


def test_source_usage_contract_accepts_trusted_official_source_urls():
    assert factory_v5_silla._has_source_usage_contract(
        "단순 위치도. 나정: https://www.heritage.go.kr/heri/cul/detail"
    )
    assert factory_v5_silla._has_source_usage_contract(
        "위치 참고: https://contents.history.go.kr/mobile/kc/view.do?levelId=kc_n101790"
    )


def test_source_usage_contract_does_not_trust_lookalike_or_general_domains():
    assert not factory_v5_silla._has_source_usage_contract(
        "출처: https://heritage.go.kr.example.com/source"
    )
    assert not factory_v5_silla._has_source_usage_contract(
        "출처: https://example.com/source"
    )


def test_shared_source_contract_accepts_later_cut_using_same_landmarks():
    declared = [
        "국가유산포털 나정·오릉 대표점. 나정: "
        "https://www.heritage.go.kr/heri/cul/detail | 오릉: "
        "https://www.heritage.go.kr/heri/cul/detail2"
    ]

    assert factory_v5_silla._has_shared_source_usage_contract(
        "국가유산포털 대표점 기준 나정·오릉 상세 위치도",
        declared,
    )
    assert not factory_v5_silla._has_shared_source_usage_contract(
        "국사편찬위원회 삼국사기 목판본",
        declared,
    )


def test_silla_workbook_list_excludes_non_episode_reference_workbooks(tmp_path, monkeypatch):
    episode = tmp_path / "황금의_나라_EP01.xlsx"
    reference = tmp_path / "신라_확장_자료집.xlsx"
    episode.touch()
    reference.touch()
    monkeypatch.setattr(
        factory_v5_silla,
        "parse_silla_workbook",
        lambda path: SimpleNamespace(summary={"filename": path.name, "valid": True}),
    )

    result = factory_v5_silla.list_silla_workbooks(tmp_path)

    assert [item["filename"] for item in result["workbooks"]] == [episode.name]


@pytest.mark.skipif(
    not all(path.is_file() for path in (SILLA_EP03, SILLA_EP04)),
    reason="local Silla episode workbooks are unavailable",
)
@pytest.mark.parametrize("workbook", [SILLA_EP03, SILLA_EP04])
def test_current_silla_episode_workbooks_pass_registration_validation(workbook: Path):
    parsed = parse_silla_workbook(workbook)

    assert parsed.summary["valid"] is True
    assert parsed.summary["content_qa_declared"] is True


def test_factory_v5_uses_youtube_caption_track_without_burning_subtitles():
    config = apply_main_caption_delivery_policy(
        {
            "factory_version": 5,
            "language": "ko",
            "subtitle_delivery": "youtube_captions",
            "cut_level_subtitles": True,
        }
    )

    assert config["cut_level_subtitles"] is False
    assert config["subtitle_delivery"] == "youtube_caption"
    assert config["youtube_captions_enabled"] is True
    assert config["caption_languages"] == ["ko"]


def test_queue_item_template_overrides_channel_default(monkeypatch):
    monkeypatch.setattr(
        oneclick_service,
        "_QUEUE",
        {"channel_presets": {"1": "channel-default"}, "items": []},
    )

    item = {"channel": 1, "template_project_id": "item-explicit"}
    assert oneclick_service._resolve_item_preset(item) == "item-explicit"
    assert oneclick_service._channel_studio_project_id(1, "item-explicit") == "item-explicit"
    assert oneclick_service._resolve_item_preset({"channel": 1}) == "channel-default"
    assert oneclick_service._channel_studio_project_id(1) == "channel-default"


def test_channel_eight_resolves_its_own_queue_preset(monkeypatch):
    monkeypatch.setattr(
        oneclick_service,
        "_QUEUE",
        {"channel_presets": {"8": "channel-eight"}, "items": []},
    )

    assert oneclick_service._resolve_item_preset({"channel": 8}) == "channel-eight"
    assert oneclick_service._channel_studio_project_id(8) == "channel-eight"


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
