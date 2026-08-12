from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


BACKEND_DIR = Path(__file__).resolve().parents[1]
import sys

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import oneclick_service as svc  # noqa: E402
from app.services.oneclick_queue_normalizer import normalize_queue_state  # noqa: E402
from scripts.ch4_register_time_explorers_queue import _registration_state, validate_prepared_scripts  # noqa: E402
from scripts.ch4_time_explorers_workbook_to_prepared_scripts import (  # noqa: E402
    _load_xlsx_workbook,
    build_prepared_scripts,
    write_prepared_scripts,
)


def _inline_cell(reference: str, value: str) -> str:
    return (
        f'<c r="{reference}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
    )


def _worksheet_xml(
    episode: int,
    cut_count: int,
    *,
    include_variety_caption: bool = False,
    include_numberless_caption_row: bool = False,
) -> str:
    topic = ("시체 재판", "중세 동물 재판", "세일럼 마녀 재판", "교황 요안나 출산 소동")[episode - 1]
    labels = (
        "항목",
        "에피소드 제목",
        "시대 (연도)",
        "배경 (장소/국가/문화권)",
        "등장인물 (최대 4인)" if episode == 1 else "등장인물 (총 4명)",
        "단일 썸네일 문구",
        "KREA AI 썸네일 프롬프트",
    )
    values = (
        "내용",
        f"Ep.{episode:02d} {topic} (Test title)",
        f"{800 + episode}년",
        "Test location",
        "해설자",
        "Test thumbnail text",
        "A period-accurate test thumbnail prompt",
    )
    rows = []
    for row_number, (label, value) in enumerate(zip(labels, values), start=1):
        rows.append(
            f'<row r="{row_number}">{_inline_cell(f"A{row_number}", label)}{_inline_cell(f"B{row_number}", value)}</row>'
        )
    headers = (
        "컷번호",
        "숏츠번호",
        "인물" if episode == 1 else "인물 (태그명)",
        "대사 (ElevenLabs V3 순수 텍스트)",
        "감성상태 (V3 연출)" if episode == 1 else "감성상태 (ElevenLabs V3 Audio Tag)",
        "이미지 프롬프트 (KREA Local AI)",
    )
    if include_variety_caption:
        headers += ("한국식 예능 자막 (주요 장면용)",)
    rows.append(
        "<row r=\"9\">"
        + "".join(_inline_cell(f"{column}9", value) for column, value in zip("ABCDEFG", headers))
        + "</row>"
    )
    for cut_number in range(1, cut_count + 1):
        row_number = cut_number + 9
        values = (
            str(cut_number),
            "S1-1" if cut_number == 1 else "-",
            "해설자",
            f"테스트 내레이션 {cut_number}",
            "차분한 해설",
            f"Period accurate historical test scene {episode}-{cut_number}",
        )
        if include_variety_caption:
            values += ("명시된 주요 장면" if cut_number == 1 else "-",)
        rows.append(
            f'<row r="{row_number}">'
            + "".join(_inline_cell(f"{column}{row_number}", value) for column, value in zip("ABCDEFG", values))
            + "</row>"
        )
    if include_numberless_caption_row:
        row_number = cut_count + 10
        rows.append(
            f'<row r="{row_number}">{_inline_cell(f"G{row_number}", "번호 없는 자막")}</row>'
        )
    return (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def _write_workbook(
    path: Path,
    *,
    include_variety_caption: bool = False,
    include_numberless_caption_row: bool = False,
    absolute_relationship_targets: bool = False,
) -> None:
    names = ("Ep01_시체 재판", "Ep02_중세 동물 재판", "Ep03_세일럼 마녀 재판", "Ep04_교황 요안나 출산 소동")
    counts = (150, 150, 135, 149)
    workbook_xml = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, name in enumerate(names, start=1)
        )
        + "</sheets></workbook>"
    )
    rels_xml = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{("/xl/" if absolute_relationship_targets else "")}worksheets/sheet{index}.xml"/>'
            for index in range(1, 5)
        )
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        for episode, count in enumerate(counts, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{episode}.xml",
                _worksheet_xml(
                    episode,
                    count,
                    include_variety_caption=include_variety_caption,
                    include_numberless_caption_row=include_numberless_caption_row,
                ),
            )


def _worksheet_xml_5_7(episode: int, cut_count: int) -> str:
    topics = {
        5: "교황 그레고리오 9세의 고양이 처형령",
        6: "1904 세인트루이스 올림픽 마라톤",
        7: "1922 뉴욕 밀짚모자 폭동",
    }
    compact_metadata = episode == 7
    labels = (
        "항목",
        "에피소드 제목",
        "시대" if compact_metadata else "시대 (연도)",
        "배경" if compact_metadata else "배경 (장소/국가/문화권)",
        "등장인물" if compact_metadata else "등장인물 (총 4명)",
        "썸네일 문구" if compact_metadata else "단일 썸네일 문구",
        "썸네일 프롬프트" if compact_metadata else "KREA AI 썸네일 프롬프트",
    )
    values = (
        "내용",
        f"Ep.{episode:02d} {topics[episode]} (Test title)",
        f"{1200 + episode}년",
        "Test location",
        "해설자(남성 메인), 남성1 인물, 여성1 인물, 남성2 인물",
        "Test thumbnail text",
        "A period-accurate test thumbnail prompt",
    )
    rows = []
    for row_number, (label, value) in enumerate(zip(labels, values), start=1):
        rows.append(
            f'<row r="{row_number}">{_inline_cell(f"A{row_number}", label)}{_inline_cell(f"B{row_number}", value)}</row>'
        )
    caption_headers = {
        5: "한국식 예능 자막 (핵심 포인트)",
        6: "한국식 예능 자막 (주요 장면용)",
        7: "한국식 예능 자막 (선택적 하이라이트)",
    }
    headers = (
        "컷번호",
        "숏츠번호",
        "인물 (태그명)",
        "대사 (ElevenLabs V3 감성 태그 포함)",
        caption_headers[episode],
        "이미지 프롬프트 (KREA Local AI)",
    )
    rows.append(
        '<row r="9">'
        + "".join(_inline_cell(f"{column}9", value) for column, value in zip("ABCDEF", headers))
        + "</row>"
    )
    for cut_number in range(1, cut_count + 1):
        row_number = cut_number + 9
        narration = (
            f"태그 없는 테스트 내레이션 {cut_number}"
            if episode == 6 and cut_number == cut_count
            else f"[dramatic] [slowly] 테스트 내레이션 {cut_number}"
        )
        row_values = (
            str(cut_number),
            "S1-1" if cut_number == 1 else "-",
            "남성1 인물" if cut_number == 1 else "해설자",
            narration,
            f"명시 자막 {episode}-{cut_number} 💥",
            f"Period accurate historical test scene {episode}-{cut_number}",
        )
        rows.append(
            f'<row r="{row_number}">'
            + "".join(_inline_cell(f"{column}{row_number}", value) for column, value in zip("ABCDEF", row_values))
            + "</row>"
        )
    return (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(rows)}</sheetData></worksheet>"
    )


def _write_workbook_5_7(path: Path) -> None:
    names = (
        "Ep05_교황 그레고리오 9세의 고양이 처형령",
        "Ep06_1904 세인트루이스 올림픽 마라톤",
        "Ep07_밀짚모자 폭동",
    )
    counts = (3, 2, 3)
    workbook_xml = (
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, name in enumerate(names, start=1)
        )
        + "</sheets></workbook>"
    )
    rels_xml = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, 4)
        )
        + "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        for episode, count in zip(range(5, 8), counts):
            archive.writestr(
                f"xl/worksheets/sheet{episode - 4}.xml",
                _worksheet_xml_5_7(episode, count),
            )


class Ch4TimeExplorersRegistrationTests(unittest.TestCase):
    def test_loader_accepts_absolute_package_sheet_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "absolute-targets.xlsx"
            _write_workbook(workbook, absolute_relationship_targets=True)

            sheets = _load_xlsx_workbook(workbook)

        self.assertEqual([name for name, _ in sheets], [
            "Ep01_시체 재판",
            "Ep02_중세 동물 재판",
            "Ep03_세일럼 마녀 재판",
            "Ep04_교황 요안나 출산 소동",
        ])

    def test_current_prepared_queue_contract_overrides_stale_task_cut_count(self):
        task = {
            "config": {
                "target_cuts": 150,
                "target_duration": 600,
                "oneclick_target_cuts_override": 150,
                "episode_code": "CH4-WH-S01-EP01",
            },
            "total_cuts": 150,
        }
        item = {
            "target_cuts": 146,
            "target_duration": 584,
            "episode_number": 1,
            "episode_code": "CH4-WH-S01-EP01",
            "episode_id": "CH4-WH-S01-EP01",
            "series": "기괴와 변칙의 세계사 시즌1",
            "core_content": "[Prepared Script] CH4-WH-S01-EP01.json\n[Cuts] 146",
        }

        changed = svc._sync_prepared_queue_contract_to_task(task, item)

        self.assertTrue(changed)
        self.assertEqual(task["total_cuts"], 146)
        self.assertEqual(task["config"]["target_cuts"], 146)
        self.assertEqual(task["config"]["oneclick_target_cuts_override"], 146)
        self.assertTrue(task["config"]["prepared_script_required"])
    def test_converter_preserves_variable_source_cut_counts_and_pipeline_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers.xlsx"
            prepared_dir = Path(temp) / "prepared_scripts"
            _write_workbook(workbook)

            manifest = write_prepared_scripts(workbook, prepared_dir)
            scripts, validated_manifest = validate_prepared_scripts(workbook, prepared_dir)

        self.assertEqual(manifest["cut_count"], 584)
        self.assertEqual([len(script["cuts"]) for script in scripts], [150, 150, 135, 149])
        self.assertEqual([script["episode_code"] for script in scripts], [
            "CH4-WH-S01-EP01",
            "CH4-WH-S01-EP02",
            "CH4-WH-S01-EP03",
            "CH4-WH-S01-EP04",
        ])
        self.assertEqual(len(validated_manifest["files"]), 4)
        self.assertEqual(scripts[0]["cuts"][0]["tts_tags"], [])

    def test_converter_maps_only_explicit_variety_caption_cells(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers-with-captions.xlsx"
            _write_workbook(workbook, include_variety_caption=True)
            scripts, _manifest = build_prepared_scripts(workbook)

        first_script = scripts[0][1]
        self.assertEqual(
            first_script["cuts"][0]["highlight_caption"],
            "명시된 주요 장면",
        )
        self.assertNotIn("highlight_caption", first_script["cuts"][1])

    def test_converter_rejects_caption_without_cut_number(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers-invalid-caption-row.xlsx"
            _write_workbook(
                workbook,
                include_variety_caption=True,
                include_numberless_caption_row=True,
            )

            with self.assertRaisesRegex(ValueError, "cut data without cut number"):
                build_prepared_scripts(workbook)

    def test_converter_maps_all_explicit_ep05_07_variety_caption_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers-ep05-07.xlsx"
            _write_workbook_5_7(workbook)
            canonical, manifest = build_prepared_scripts(workbook)

        scripts = [script for _filename, script in canonical]
        self.assertEqual([script["episode_number"] for script in scripts], [5, 6, 7])
        self.assertEqual([len(script["cuts"]) for script in scripts], [3, 2, 3])
        self.assertEqual(manifest["manifest_file"], "manifest_ep05-07.json")
        self.assertEqual(scripts[0]["cuts"][0]["narration"], "테스트 내레이션 1")
        self.assertEqual(scripts[0]["cuts"][0]["emotion"], "[dramatic] [slowly]")
        self.assertEqual(scripts[0]["cuts"][0]["tts_tags"], ["dramatic", "slowly"])
        self.assertEqual(scripts[0]["cuts"][0]["highlight_caption"], "명시 자막 5-1")
        self.assertEqual(scripts[0]["cuts"][0]["speaker"], "인물")
        self.assertEqual(scripts[0]["cuts"][0]["voice_role"], "male_1")
        self.assertEqual(scripts[1]["cuts"][0]["highlight_caption"], "명시 자막 6-1")
        self.assertEqual(scripts[1]["cuts"][1]["tts_tags"], [])
        self.assertEqual(scripts[1]["cuts"][1]["narration"], "태그 없는 테스트 내레이션 2")
        self.assertEqual(scripts[2]["cuts"][0]["highlight_caption"], "명시 자막 7-1")

    def test_prepared_script_merge_preserves_existing_ep01_04_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workbook_1_4 = root / "time-explorers-ep01-04.xlsx"
            workbook_5_7 = root / "time-explorers-ep05-07.xlsx"
            prepared_dir = root / "prepared_scripts"
            _write_workbook(workbook_1_4)
            _write_workbook_5_7(workbook_5_7)
            write_prepared_scripts(workbook_1_4, prepared_dir)
            preserved = {
                path.name: path.read_bytes()
                for path in prepared_dir.iterdir()
                if path.is_file()
            }

            write_prepared_scripts(
                workbook_5_7,
                prepared_dir,
                preserve_existing=True,
            )
            scripts, manifest = validate_prepared_scripts(workbook_5_7, prepared_dir)

            self.assertEqual([script["episode_number"] for script in scripts], [5, 6, 7])
            self.assertEqual(manifest["manifest_file"], "manifest_ep05-07.json")
            for filename, payload in preserved.items():
                self.assertEqual((prepared_dir / filename).read_bytes(), payload)

    def test_queue_normalizer_keeps_prepared_script_cut_count(self):
        normalized = normalize_queue_state(
            {
                "items": [
                    {"topic": "EP03", "channel": 4, "target_cuts": 135, "target_duration": 600},
                    {"topic": "EP04", "channel": 4, "target_duration": 596},
                ]
            },
            channels=[1, 2, 3, 4],
            main_target_duration=600,
            main_cut_count=150,
        )

        self.assertEqual(
            [(item["target_cuts"], item["target_duration"]) for item in normalized["items"]],
            [(135, 540), (149, 596)],
        )

    def test_v3_override_survives_for_non_150_cut_count(self):
        with tempfile.TemporaryDirectory() as temp:
            config = svc._apply_v3_episode_overrides(
                {},
                source_project_id="83cca89d",
                project_id="V3_CH4_EP3_123456789abc",
                result_dir=Path(temp),
                topic="세일럼 마녀 재판",
                channel=4,
                episode_number=3,
                episode_code="CH4-WH-S01-EP03",
                target_cuts=135,
            )

        self.assertEqual(config["oneclick_target_cuts_override"], 135)
        self.assertEqual(config["target_cuts"], 135)
        self.assertEqual(config["target_duration"], 540)

    def test_registration_replaces_only_existing_first_four_ch4_items(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers.xlsx"
            _write_workbook(workbook)
            canonical_scripts, _manifest = build_prepared_scripts(workbook)
        scripts = [script for _filename, script in canonical_scripts]
        current = {
            "channel_presets": {"4": "83cca89d"},
            "items": [
                {
                    "id": f"keep-{episode}",
                    "topic": f"old {episode}",
                    "channel": 4,
                    "episode_code": f"CH4-WH-S01-EP{episode:02d}",
                    "status": "pending",
                }
                for episode in range(1, 5)
            ]
            + [
                {"id": "keep-5", "topic": "unchanged", "channel": 4, "episode_code": "CH4-WH-S01-EP05", "status": "pending"},
                {"id": "ch1", "topic": "other channel", "channel": 1, "status": "pending"},
            ],
        }

        state, errors = _registration_state(current, scripts, queued_at="2026-08-05T00:00:00Z")

        self.assertEqual(errors, [])
        self.assertEqual(state["items"][4], current["items"][4])
        self.assertEqual(state["items"][5], current["items"][5])
        self.assertEqual(
            [(item["id"], item["target_cuts"], item["target_duration"]) for item in state["items"][:4]],
            [("keep-1", 150, 600), ("keep-2", 150, 600), ("keep-3", 135, 540), ("keep-4", 149, 596)],
        )

    def test_registration_replaces_only_ep05_07_queue_items(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers-ep05-07.xlsx"
            _write_workbook_5_7(workbook)
            canonical, _manifest = build_prepared_scripts(workbook)
        scripts = [script for _filename, script in canonical]
        current = {
            "channel_presets": {"4": "83cca89d"},
            "items": [
                {
                    "id": f"keep-{episode}",
                    "topic": f"old {episode}",
                    "channel": 4,
                    "episode_code": f"CH4-WH-S01-EP{episode:02d}",
                    "status": "pending",
                }
                for episode in range(5, 8)
            ]
            + [
                {
                    "id": "keep-8",
                    "topic": "unchanged",
                    "channel": 4,
                    "episode_code": "CH4-WH-S01-EP08",
                    "status": "pending",
                }
            ],
        }

        state, errors = _registration_state(
            current,
            scripts,
            queued_at="2026-08-05T00:00:00Z",
        )

        self.assertEqual(errors, [])
        self.assertEqual(state["items"][3], current["items"][3])
        self.assertEqual(
            [(item["id"], item["target_cuts"], item["target_duration"]) for item in state["items"][:3]],
            [("keep-5", 3, 12), ("keep-6", 2, 8), ("keep-7", 3, 12)],
        )

    def test_registration_adds_a_missing_episode_before_later_ch4_episode(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers-ep05-07.xlsx"
            _write_workbook_5_7(workbook)
            canonical, _manifest = build_prepared_scripts(workbook)
        scripts = [script for _filename, script in canonical]
        current = {
            "channel_presets": {"4": "83cca89d"},
            "items": [
                {"id": "keep-6", "topic": "old 6", "channel": 4, "episode_number": 6, "episode_code": "CH4-WH-S01-EP06", "status": "pending"},
                {"id": "keep-7", "topic": "old 7", "channel": 4, "episode_number": 7, "episode_code": "CH4-WH-S01-EP07", "status": "pending"},
            ],
        }

        state, errors = _registration_state(
            current,
            scripts,
            queued_at="2026-08-05T00:00:00Z",
            add_missing=True,
        )

        self.assertEqual(errors, [])
        self.assertEqual([item["episode_number"] for item in state["items"]], [5, 6, 7])
        self.assertTrue(state["items"][0]["id"].startswith("ch4-"))

    def test_registration_removes_only_stale_items_in_the_same_ch4_series(self):
        with tempfile.TemporaryDirectory() as temp:
            workbook = Path(temp) / "time-explorers.xlsx"
            _write_workbook(workbook)
            canonical, _manifest = build_prepared_scripts(workbook)
        scripts = [script for _filename, script in canonical]
        current = {
            "channel_presets": {"4": "83cca89d"},
            "items": [
                {"id": f"keep-{episode}", "topic": "old", "channel": 4, "episode_code": f"CH4-WH-S01-EP{episode:02d}", "status": "pending"}
                for episode in range(1, 5)
            ] + [
                {"id": "stale", "topic": "stale", "channel": 4, "episode_code": "CH4-WH-S01-EP05", "status": "pending"},
                {"id": "other", "topic": "other", "channel": 4, "episode_code": "CH4-OTHER-EP01", "status": "pending"},
            ],
        }

        state, errors = _registration_state(
            current,
            scripts,
            queued_at="2026-08-05T00:00:00Z",
            remove_stale=True,
        )

        self.assertEqual(errors, [])
        self.assertEqual([item["episode_code"] for item in state["items"]], [
            "CH4-WH-S01-EP01",
            "CH4-WH-S01-EP02",
            "CH4-WH-S01-EP03",
            "CH4-WH-S01-EP04",
            "CH4-OTHER-EP01",
        ])


if __name__ == "__main__":
    unittest.main()
