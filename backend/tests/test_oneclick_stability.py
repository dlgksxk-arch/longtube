"""OneClick stability characterization tests.

These tests lock down small pure helpers before splitting the large
oneclick_service module further. They do not call external APIs or start jobs.
"""
import asyncio
import copy
import inspect
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import oneclick_service as svc  # noqa: E402
from app.services import thumbnail_service as thumb_svc  # noqa: E402
from app.services.tts import narration_fit  # noqa: E402
from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts  # noqa: E402
from app.services import shorts_service  # noqa: E402
from app.services import subtitle_service  # noqa: E402
from app.services import youtube_service  # noqa: E402
from app import config as app_config  # noqa: E402
from app.services.title_utils import shorts_upload_title  # noqa: E402
from app.services.image import prompt_builder  # noqa: E402
from app.services.thumbnail_service import (  # noqa: E402
    _basic_thumbnail_file_check,
    _thumbnail_error_allows_first_cut_fallback,
    _thumbnail_closeup_soft_quality_failure,
    _thumbnail_person_presence_misread,
    _thumbnail_overlay_quality_system_prompt,
    _thumbnail_fallback_face_safe_boxes,
    _thumbnail_overlay_local_geometry_pass,
    _thumbnail_prompt_expects_face_closeup,
    _thumbnail_prompt_expects_person,
    _thumbnail_quality_system_prompt,
    _thumbnail_retry_prompt,
    _thumbnail_text_layout_score,
    _wrap_text,
    build_clickbait_thumbnail_overlay,
    build_standard_thumbnail_prompt,
    extract_thumbnail_text_parts,
    ThumbnailError,
)
from app.services.image.comfyui_service import (  # noqa: E402
    apply_longtube_local_v1_master_prompt,
    build_longtube_local_v1_negative_prompt,
    _compact_flux2_klein_4b_prompt,
    _enrich_local_v1_positive_prompt,
    _flux2_klein_ep13_scene_prompt,
    _flux2_klein_is_japanese_frayed_storage_context,
    _flux2_klein_is_japanese_bookshop_theater_context,
    _flux2_klein_is_historical_japanese_context,
    _flux2_klein_is_japanese_courier_context,
    _flux2_klein_is_japanese_rice_storehouse_context,
    _flux2_klein_japanese_frayed_storage_retry_sentence,
    _flux2_klein_japanese_bookshop_theater_retry_sentence,
    _flux2_klein_japanese_courier_retry_sentence,
    _flux2_klein_japanese_rice_storehouse_retry_sentence,
    _flux2_klein_japanese_textless_retry_sentence,
    _flux2_klein_md_negative_contract,
    _flux2_klein_md_positive_contract,
    _image_has_corner_artist_mark,
    _image_has_internal_text_like_marks,
    _image_has_split_panel_divider,
    _image_has_solid_light_outer_margin,
    _image_has_top_caption_like_text,
    _should_check_internal_text_after_generation,
    _should_use_japanese_document_table_retry,
    _strip_local_v1_positive_only_prompt,
    PREMODERN_INTERIOR_PROP_COMFYUI_EXTRA_NEGATIVE,
    PREMODERN_INTERIOR_PROP_COMFYUI_FRONT_PROMPT,
)
from app.services.llm.base import BaseLLMService, get_system_prompt  # noqa: E402
from app.services.llm.visual_policy import apply_script_visual_policy, normalize_cut_image_prompt  # noqa: E402
from app.services.llm.script_quality import (  # noqa: E402
    _inspect_story_plan_topic_alignment,
    inspect_script_quality,
)
from app.routers import interlude as interlude_router  # noqa: E402
from app.routers import script as script_router  # noqa: E402
from app.routers import channel_ops as channel_ops_router  # noqa: E402
from app.routers.projects import DEFAULT_CONFIG  # noqa: E402
from app.routers import subtitle as subtitle_router  # noqa: E402
from app.services.interlude_service import DEFAULT_INTERMISSION_EVERY  # noqa: E402
from app.tasks import pipeline_tasks  # noqa: E402


class StoryPlanProbeLLM(BaseLLMService):
    model_id = "story-plan-probe"
    display_name = "Story Plan Probe"

    def __init__(self):
        self.story_plan_calls = 0

    async def generate_story_plan(self, topic: str, config: dict) -> dict:
        self.story_plan_calls += 1
        raise AssertionError("story plan generation should not run")

    async def generate_script(self, topic: str, config: dict) -> dict:
        return {"cuts": []}


class OneClickQueueStabilityTests(unittest.TestCase):
    def test_oneclick_main_length_is_150_four_second_cuts(self):
        cfg = {}
        svc._force_oneclick_main_length(cfg)

        self.assertEqual(svc.ONECLICK_MAIN_CUT_COUNT, 150)
        self.assertEqual(svc.ONECLICK_SECONDS_PER_CUT, 4.0)
        self.assertEqual(svc.ONECLICK_MAIN_TARGET_DURATION, 600)
        self.assertEqual(cfg["cut_video_duration"], 4.0)
        self.assertEqual(cfg["target_cuts"], 150)
        self.assertEqual(cfg["target_duration"], 600)
        self.assertEqual(cfg["script_tts_min_sec"], 4.0)
        self.assertEqual(cfg["script_tts_target_sec"], 5.0)
        self.assertEqual(cfg["script_tts_max_sec"], 6.0)

    def test_oneclick_main_length_uses_requested_duration(self):
        cfg = {}
        svc._force_oneclick_main_length(cfg, 20)

        self.assertEqual(cfg["cut_video_duration"], 4.0)
        self.assertEqual(cfg["target_duration"], 20)
        self.assertEqual(cfg["target_cuts"], 5)

    def test_oneclick_task_logs_prune_only_entries_older_than_36_hours(self):
        now = datetime.utcnow()
        old_iso = (now - timedelta(hours=37)).isoformat(timespec="seconds") + "Z"
        recent_iso = (now - timedelta(hours=35)).isoformat(timespec="seconds") + "Z"
        task = {
            "status": "failed",
            "created_at": recent_iso,
            "logs": [
                {"ts": "01:00:00", "ts_iso": old_iso, "level": "info", "msg": "old"},
                {"ts": "02:00:00", "ts_iso": recent_iso, "level": "warn", "msg": "recent"},
                {"ts": "03:00:00", "level": "error", "msg": "legacy"},
            ],
        }

        self.assertTrue(svc._prune_task_logs_for_retention(task))
        self.assertEqual([row["msg"] for row in task["logs"]], ["recent", "legacy"])
        self.assertTrue(svc._task_within_log_retention(task))

    def test_oneclick_log_retention_keeps_active_tasks(self):
        old_iso = (datetime.utcnow() - timedelta(hours=37)).isoformat(timespec="seconds") + "Z"
        task = {
            "status": "running",
            "created_at": old_iso,
            "logs": [{"ts": "01:00:00", "ts_iso": old_iso, "level": "info", "msg": "old"}],
        }

        self.assertTrue(svc._task_within_log_retention(task))

    def test_failed_output_scan_does_not_delete_existing_script_or_assets(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            (project_dir / "script.json").write_text("{broken", encoding="utf-8")
            for sub, name in (
                ("audio", "cut_1.mp3"),
                ("images", "cut_1.png"),
                ("videos", "cut_1.mp4"),
            ):
                folder = project_dir / sub
                folder.mkdir()
                (folder / name).write_bytes(b"broken")
            output_dir = project_dir / "output"
            output_dir.mkdir()
            (output_dir / "merged.mp4").write_bytes(b"broken")

            states, counts, total, removed = svc._cleanup_and_detect_completed_steps(
                "preserve-test",
                {"result_dir": str(project_dir)},
            )

            self.assertEqual(states["2"], "pending")
            self.assertEqual(total, 0)
            self.assertEqual(removed, [])
            self.assertEqual(counts["3"], 0)
            self.assertTrue((project_dir / "script.json").exists())
            self.assertTrue((project_dir / "audio" / "cut_1.mp3").exists())
            self.assertTrue((project_dir / "images" / "cut_1.png").exists())
            self.assertTrue((project_dir / "videos" / "cut_1.mp4").exists())
            self.assertTrue((project_dir / "output" / "merged.mp4").exists())

    def test_reconcile_after_failure_preserves_broken_audio_file(self):
        with tempfile.TemporaryDirectory() as td:
            project_dir = Path(td)
            script = {"cuts": [{"cut_number": 1, "narration": "test"}]}
            (project_dir / "script.json").write_text(json.dumps(script), encoding="utf-8")
            audio_dir = project_dir / "audio"
            audio_dir.mkdir()
            broken_audio = audio_dir / "cut_1.mp3"
            broken_audio.write_bytes(b"broken")
            task = {
                "task_id": "preserve-audio",
                "project_id": "preserve-audio",
                "config": {"result_dir": str(project_dir)},
                "status": "failed",
                "step_states": {"2": "completed", "3": "failed", "4": "pending", "5": "pending", "6": "pending", "7": "pending"},
                "completed_cuts_by_step": {"2": 1, "3": 0, "4": 0, "5": 0},
                "logs": [],
            }

            svc._reconcile_task_outputs(task)

            self.assertTrue(broken_audio.exists())
            self.assertEqual(task["step_states"]["2"], "completed")
            self.assertEqual(task["step_states"]["3"], "pending")

    def test_default_script_generation_uses_150_four_second_cuts(self):
        self.assertEqual(app_config.CUT_VIDEO_DURATION, 4.0)
        self.assertEqual(DEFAULT_CONFIG["cut_video_duration"], 4.0)
        self.assertEqual(DEFAULT_CONFIG["target_duration"], 600)

        prompt = get_system_prompt("ko", DEFAULT_CONFIG)
        self.assertIn('"image_prompt": ""', prompt)
        self.assertIn("visual_subject", prompt)
        self.assertIn("visual_scene", prompt)
        self.assertIn("duration_estimate는 컷 길이가 프로젝트 기본값", prompt)
        self.assertIn("영상 컷 슬롯은 4.0초로 고정", prompt)

    def test_sort_queue_keeps_running_first_and_removes_terminal_rows(self):
        state = {
            "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
            "last_run_dates": {},
        }
        items = [
            {"id": "manual", "topic": "Manual next", "channel": 2, "episode_number": 2, "queued_source": "manual", "queued_note": "작업대에서 실행순 1번 지정"},
            {"id": "normal", "topic": "Normal", "channel": 1, "episode_number": 1},
            {"id": "running", "topic": "Running", "channel": 4, "episode_number": 19, "status": "running", "task_id": "task-running"},
            {"id": "failed", "topic": "Failed", "channel": 3, "episode_number": 9, "status": "failed"},
        ]

        sorted_items = svc._sort_queue_items_for_execution(
            items,
            state,
            now=datetime(2026, 5, 5, 8, 0),
        )

        self.assertEqual([item["id"] for item in sorted_items], ["running", "manual", "normal"])

    def test_sort_queue_keeps_immediate_items_pinned_then_schedules_by_channel_and_episode(self):
        state = {
            "channel_times": {
                "1": "18:00",
                "2": "09:00",
                "3": None,
                "4": "12:00",
            },
            "last_run_dates": {},
        }
        items = [
            {"id": "ch1-ep30", "topic": "CH1 late", "channel": 1, "episode_number": 30},
            {"id": "ch2-ep13", "topic": "CH2 later ep", "channel": 2, "episode_number": 13},
            {"id": "manual", "topic": "Manual now", "channel": 4, "episode_number": 99, "queued_source": "manual", "queued_note": "수동 실행"},
            {"id": "ch4-ep8", "topic": "CH4 noon", "channel": 4, "episode_number": 8},
            {"id": "ch2-ep12", "topic": "CH2 first ep", "channel": 2, "episode_number": 12},
        ]

        sorted_items = svc._sort_queue_items_for_execution(
            items,
            state,
            now=datetime(2026, 5, 5, 8, 0),
        )

        self.assertEqual(
            [item["id"] for item in sorted_items],
            ["manual", "ch2-ep12", "ch4-ep8", "ch1-ep30", "ch2-ep13"],
        )

    def test_sort_queue_moves_already_fired_channel_to_next_day(self):
        state = {
            "channel_times": {"1": "08:00", "2": "09:00", "3": None, "4": None},
            "last_run_dates": {"1": "2026-05-05"},
        }
        items = [
            {"id": "ch1", "topic": "Already fired today", "channel": 1, "episode_number": 1},
            {"id": "ch2", "topic": "Next today", "channel": 2, "episode_number": 1},
        ]

        sorted_items = svc._sort_queue_items_for_execution(
            items,
            state,
            now=datetime(2026, 5, 5, 7, 0),
        )

        self.assertEqual([item["id"] for item in sorted_items], ["ch2", "ch1"])

    def test_scheduler_finds_due_channel_behind_not_due_head(self):
        old_queue = copy.deepcopy(svc._QUEUE)
        try:
            svc._QUEUE.clear()
            svc._QUEUE.update({
                "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                "last_run_dates": {"1": "2026-05-31", "3": "2026-06-01"},
                "channel_presets": {},
                "items": [
                    {"id": "ch3", "topic": "CH3 later", "channel": 3, "episode_number": 49, "status": "pending"},
                    {"id": "ch1", "topic": "CH1 due", "channel": 1, "episode_number": 18, "status": "pending"},
                ],
            })

            due_ch = svc._scheduled_queue_channel_to_fire(datetime(2026, 6, 2, 2, 0))

            self.assertEqual(due_ch, 1)
        finally:
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)

    def test_scheduler_due_channel_order_uses_schedule_time_before_queue_index(self):
        old_queue = copy.deepcopy(svc._QUEUE)
        try:
            svc._QUEUE.clear()
            svc._QUEUE.update({
                "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                "last_run_dates": {},
                "channel_presets": {},
                "items": [
                    {"id": "ch4", "topic": "CH4 first in file", "channel": 4, "episode_number": 1, "status": "pending"},
                    {"id": "ch1", "topic": "CH1 earlier schedule", "channel": 1, "episode_number": 1, "status": "pending"},
                ],
            })

            due_ch = svc._scheduled_queue_channel_to_fire(datetime(2026, 6, 2, 10, 0))

            self.assertEqual(due_ch, 1)
        finally:
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)

    def test_queue_normalize_preserves_schema_and_rejects_bad_items(self):
        normalized = svc._queue_normalize(
            {
                "daily_time": "07:30",
                "last_run_date": "2026-05-04",
                "channel_presets": {"2": "preset-ch2"},
                "items": [
                    {"topic": "Keep", "channel": "2", "episode_number": 7, "queued_source": "import"},
                    {"topic": "", "channel": 1},
                    {"topic": "Bad channel fallback", "channel": 99, "queued_source": "bad"},
                ],
            }
        )

        self.assertEqual(normalized["channel_times"]["1"], "07:30")
        self.assertEqual(normalized["last_run_dates"]["1"], "2026-05-04")
        self.assertEqual(normalized["channel_presets"]["2"], "preset-ch2")
        self.assertEqual(len(normalized["items"]), 2)
        by_topic = {item["topic"]: item for item in normalized["items"]}
        self.assertEqual(by_topic["Keep"]["channel"], 2)
        self.assertEqual(by_topic["Keep"]["episode_number"], 7)
        self.assertEqual(by_topic["Keep"]["queued_source"], "import")
        self.assertEqual(by_topic["Bad channel fallback"]["channel"], 1)
        self.assertEqual(by_topic["Bad channel fallback"]["queued_source"], "manual")
        self.assertEqual(by_topic["Keep"]["target_cuts"], svc.ONECLICK_MAIN_CUT_COUNT)
        self.assertEqual(by_topic["Keep"]["target_duration"], svc.ONECLICK_MAIN_TARGET_DURATION)

    def test_queue_normalize_uses_template_channel_when_item_channel_is_missing(self):
        normalized = svc._queue_normalize(
            {
                "items": [
                    {"topic": "From template", "template_project_id": "tpl-ch4"},
                ],
            }
        )

        self.assertEqual(normalized["items"][0]["channel"], 1)

        def fake_load_project(project_id: str):
            if project_id == "tpl-ch4":
                return SimpleNamespace(config={"youtube_channel": 4})
            return None

        from app.services.oneclick_queue_normalizer import normalize_queue_state

        direct = normalize_queue_state(
            {
                "items": [
                    {"topic": "From template", "template_project_id": "tpl-ch4"},
                ],
            },
            channels=svc.CHANNELS,
            main_target_duration=svc.ONECLICK_MAIN_TARGET_DURATION,
            main_cut_count=svc.ONECLICK_MAIN_CUT_COUNT,
            load_project=fake_load_project,
        )

        self.assertEqual(direct["items"][0]["channel"], 4)

    def test_orphan_v3_result_lookup_skips_empty_retry_folders(self):
        original_root = svc.RESULT_ARCHIVE_DIR
        try:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                svc.RESULT_ARCHIVE_DIR = root
                ch_dir = root / "CH1"
                ch_dir.mkdir(parents=True)
                empty_retry = ch_dir / "EP.2.2605191735323cc127"
                empty_retry.mkdir()
                (empty_retry / "audio").mkdir()
                existing = ch_dir / "EP.2.26051815093946c7fd"
                existing.mkdir()
                (existing / "script.json").write_text(
                    json.dumps({"cuts": [{"cut_number": 1}]}),
                    encoding="utf-8",
                )
                os.utime(empty_retry, (2000, 2000))
                os.utime(existing, (1000, 1000))

                found = svc._find_orphan_v3_result_project_for_queue_item(
                    {"channel": 1, "episode_number": 2, "topic": "단군왕검"}
                )
        finally:
            svc.RESULT_ARCHIVE_DIR = original_root

        self.assertIsNotNone(found)
        self.assertEqual(found[0], "V3_CH1_EP2_26051815093946c7fd")
        self.assertEqual(found[2]["total_cuts"], 1)

    def test_fire_queue_recovers_existing_project_before_preparing_new_v3_run(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_queue = copy.deepcopy(svc._QUEUE)
        old_loaded = svc._STATE_LOADED
        originals = {
            "_save_queue_to_disk": svc._save_queue_to_disk,
            "_save_tasks_to_disk": svc._save_tasks_to_disk,
            "_normalize_queue_runtime_state": svc._normalize_queue_runtime_state,
            "_queue_running_task_for_channel": svc._queue_running_task_for_channel,
            "_has_inflight_task": svc._has_inflight_task,
            "_find_existing_task_for_queue_item": svc._find_existing_task_for_queue_item,
            "_find_existing_project_for_queue_item": svc._find_existing_project_for_queue_item,
            "recover_project": svc.recover_project,
            "_reconcile_task_outputs": svc._reconcile_task_outputs,
            "_compute_progress_pct": svc._compute_progress_pct,
            "start_task": svc.start_task,
            "prepare_task": svc.prepare_task,
        }
        started = []
        result = None
        queue_project_id = None

        def fake_recover(project_id):
            task = {
                "task_id": "recovered-task",
                "project_id": project_id,
                "status": "failed",
                "step_states": {"2": "completed", "3": "pending"},
                "completed_cuts_by_step": {},
                "total_cuts": 150,
                "config": {},
            }
            svc._TASKS[task["task_id"]] = task
            return task

        def fail_prepare(**_kwargs):
            raise AssertionError("prepare_task should not be called")

        try:
            svc._STATE_LOADED = True
            svc._TASKS.clear()
            svc._QUEUE.clear()
            svc._QUEUE.update(
                {
                    "channel_times": {"1": None, "2": None, "3": None, "4": None},
                    "last_run_dates": {},
                    "channel_presets": {"1": "studio-ch1"},
                    "items": [
                        {
                            "id": "queue-ep2",
                            "topic": "단군왕검은 왕이었나",
                            "channel": 1,
                            "episode_number": 2,
                            "status": "pending",
                        }
                    ],
                }
            )
            svc._save_queue_to_disk = lambda: None
            svc._save_tasks_to_disk = lambda: None
            svc._normalize_queue_runtime_state = lambda save=True: None
            svc._queue_running_task_for_channel = lambda _ch: None
            svc._has_inflight_task = lambda: False
            svc._find_existing_task_for_queue_item = lambda _item, _preset: None
            svc._find_existing_project_for_queue_item = lambda _item: "V3_CH1_EP2_existing"
            svc.recover_project = fake_recover
            svc._reconcile_task_outputs = lambda _task, clear_terminal_cursor=False: False
            svc._compute_progress_pct = lambda _task: 10.0
            svc.start_task = lambda task_id: started.append(task_id) or svc._TASKS[task_id]
            svc.prepare_task = fail_prepare

            result = asyncio.run(svc._fire_queue_for_channel(1, triggered_by="manual"))
            queue_project_id = svc._QUEUE["items"][0].get("project_id")
        finally:
            for name, value in originals.items():
                setattr(svc, name, value)
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)
            svc._STATE_LOADED = old_loaded

        self.assertEqual(result["project_id"], "V3_CH1_EP2_existing")
        self.assertEqual(started, ["recovered-task"])
        self.assertEqual(queue_project_id, "V3_CH1_EP2_existing")

    def test_empty_v3_retry_task_redirects_to_existing_episode_outputs(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        originals = {
            "_save_tasks_to_disk": svc._save_tasks_to_disk,
            "_inspect_project_progress": svc._inspect_project_progress,
            "_find_existing_project_for_queue_item": svc._find_existing_project_for_queue_item,
            "recover_project": svc.recover_project,
        }

        def fake_recover(project_id):
            recovered = {
                "task_id": "fresh-recovered-task",
                "project_id": project_id,
                "status": "failed",
                "step_states": {"2": "completed", "3": "pending"},
                "completed_cuts_by_step": {},
                "total_cuts": 150,
                "config": {},
                "logs": [],
            }
            svc._TASKS[recovered["task_id"]] = recovered
            return recovered

        try:
            svc._TASKS.clear()
            task = {
                "task_id": "empty-retry",
                "project_id": "V3_CH1_EP2_2605191735323cc127",
                "status": "cancelled",
                "topic": "단군왕검은 왕이었나",
                "template_project_id": "studio-ch1",
                "config": {},
                "logs": [],
            }
            svc._TASKS["empty-retry"] = task
            svc._save_tasks_to_disk = lambda: None
            svc._inspect_project_progress = lambda *_args, **_kwargs: {
                "has_script": False,
                "audio_count": 0,
                "image_count": 0,
                "video_count": 0,
                "has_merged": False,
                "has_thumbnail": False,
            }
            svc._find_existing_project_for_queue_item = lambda _item: "V3_CH1_EP2_26051815093946c7fd"
            svc.recover_project = fake_recover

            redirected = svc._redirect_empty_v3_task_to_existing_episode("empty-retry", task)
            recovered_present_after_redirect = "fresh-recovered-task" in svc._TASKS
        finally:
            for name, value in originals.items():
                setattr(svc, name, value)
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)

        self.assertEqual(redirected["task_id"], "empty-retry")
        self.assertEqual(redirected["project_id"], "V3_CH1_EP2_26051815093946c7fd")
        self.assertFalse(recovered_present_after_redirect)

    def test_queue_task_sync_prunes_terminal_rows_and_marks_active_as_running(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_queue = copy.deepcopy(svc._QUEUE)
        old_saver = svc._save_queue_to_disk
        old_loaded = svc._STATE_LOADED
        try:
            svc._save_queue_to_disk = lambda: None
            svc._STATE_LOADED = True
            svc._TASKS.clear()
            svc._TASKS.update(
                {
                    "active": {
                        "task_id": "active",
                        "project_id": "project-active",
                        "status": "queued",
                        "topic": "Active episode",
                        "title": "Active episode",
                        "channel": 1,
                        "episode_number": 42,
                        "started_at": "2026-05-09T12:00:00Z",
                    },
                    "failed": {
                        "task_id": "failed",
                        "project_id": "project-failed",
                        "status": "failed",
                        "topic": "Failed episode",
                    },
                }
            )
            svc._QUEUE.clear()
            svc._QUEUE.update(
                {
                    "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                    "last_run_dates": {},
                    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
                    "items": [
                        {"id": "active", "topic": "Active episode", "channel": 1, "episode_number": 42, "status": "pending", "task_id": "active"},
                        {"id": "failed", "topic": "Failed episode", "channel": 2, "episode_number": 1, "status": "running", "task_id": "failed"},
                        {"id": "cancelled", "topic": "Cancelled episode", "channel": 3, "episode_number": 1, "status": "cancelled"},
                        {"id": "normal", "topic": "Normal episode", "channel": 4, "episode_number": 1, "status": "pending"},
                    ],
                }
            )

            changed = svc._sync_queue_items_from_tasks_for_save()
            svc._normalize_queue_runtime_state(save=False)

            self.assertTrue(changed)
            self.assertEqual([item["id"] for item in svc._QUEUE["items"]], ["active", "failed", "normal"])
            self.assertEqual(svc._QUEUE["items"][0]["status"], "running")
            self.assertEqual(svc._QUEUE["items"][0]["queued_note"], "실행 중")
            self.assertEqual(svc._QUEUE["items"][1]["status"], "pending")
            self.assertEqual(svc._QUEUE["items"][1]["queued_note"], "대기")
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)
            svc._save_queue_to_disk = old_saver
            svc._STATE_LOADED = old_loaded

    def test_queue_task_sync_keeps_active_task_visible_when_queue_row_is_missing(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_queue = copy.deepcopy(svc._QUEUE)
        old_saver = svc._save_queue_to_disk
        old_loaded = svc._STATE_LOADED
        old_active_runs = dict(svc._ACTIVE_RUNS)

        class _LiveRunner:
            def done(self):
                return False

        try:
            svc._save_queue_to_disk = lambda: None
            svc._STATE_LOADED = True
            svc._TASKS.clear()
            svc._TASKS.update(
                {
                    "active": {
                        "task_id": "active",
                        "project_id": "project-active",
                        "status": "running",
                        "topic": "Active episode",
                        "title": "Active episode",
                        "channel": 2,
                        "episode_number": 21,
                        "started_at": "2026-05-09T12:00:00Z",
                    },
                }
            )
            svc._ACTIVE_RUNS.clear()
            svc._ACTIVE_RUNS["active"] = _LiveRunner()
            svc._QUEUE.clear()
            svc._QUEUE.update(
                {
                    "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                    "last_run_dates": {},
                    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
                    "items": [],
                }
            )

            changed = svc._sync_queue_items_from_tasks_for_save()

            self.assertTrue(changed)
            self.assertEqual(len(svc._QUEUE["items"]), 1)
            self.assertEqual(svc._QUEUE["items"][0]["status"], "running")
            self.assertEqual(svc._QUEUE["items"][0]["task_id"], "active")
            self.assertEqual(svc._QUEUE["items"][0]["episode_number"], 21)
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)
            svc._save_queue_to_disk = old_saver
            svc._STATE_LOADED = old_loaded
            svc._ACTIVE_RUNS.clear()
            svc._ACTIVE_RUNS.update(old_active_runs)

    def test_queue_task_sync_does_not_overwrite_unrelated_queue_row(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_queue = copy.deepcopy(svc._QUEUE)
        old_saver = svc._save_queue_to_disk
        old_loaded = svc._STATE_LOADED
        try:
            svc._save_queue_to_disk = lambda: None
            svc._STATE_LOADED = True
            svc._TASKS.clear()
            svc._TASKS.update(
                {
                    "running": {
                        "task_id": "running",
                        "project_id": "project-running",
                        "status": "running",
                        "topic": "겐페이 전쟁은 왜 벌어졌을까",
                        "title": "겐페이 전쟁은 왜 벌어졌을까 EP.43",
                        "channel": 3,
                        "episode_number": 43,
                        "started_at": "2026-05-29T03:26:47Z",
                    },
                }
            )
            svc._QUEUE.clear()
            svc._QUEUE.update(
                {
                    "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                    "last_run_dates": {},
                    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
                    "items": [
                        {
                            "id": "dfa24fb0",
                            "topic": "The Qing Court Misreads the Opium War",
                            "channel": 4,
                            "episode_number": None,
                            "status": "running",
                            "task_id": "running",
                            "project_id": "project-running",
                            "queued_note": "실행 중",
                        },
                    ],
                }
            )

            changed = svc._sync_queue_items_from_tasks_for_save()

            self.assertTrue(changed)
            self.assertEqual(svc._QUEUE["items"][0]["id"], "dfa24fb0")
            self.assertEqual(svc._QUEUE["items"][0]["status"], "pending")
            self.assertNotIn("task_id", svc._QUEUE["items"][0])
            self.assertEqual(svc._QUEUE["items"][1]["id"], "task-running")
            self.assertEqual(svc._QUEUE["items"][1]["channel"], 3)
            self.assertEqual(svc._QUEUE["items"][1]["episode_number"], 43)
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)
            svc._save_queue_to_disk = old_saver
            svc._STATE_LOADED = old_loaded

    def test_uploading_task_does_not_block_production_queue(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_queue = copy.deepcopy(svc._QUEUE)
        old_saver = svc._save_queue_to_disk
        old_loaded = svc._STATE_LOADED
        try:
            svc._save_queue_to_disk = lambda: None
            svc._STATE_LOADED = True
            svc._TASKS.clear()
            svc._TASKS.update(
                {
                    "uploading": {
                        "task_id": "uploading",
                        "project_id": "project-uploading",
                        "status": "uploading",
                        "topic": "Uploading episode",
                        "title": "Uploading episode",
                        "channel": 1,
                        "episode_number": 48,
                        "started_at": "2026-05-11T17:56:09Z",
                    },
                }
            )
            svc._QUEUE.clear()
            svc._QUEUE.update(
                {
                    "channel_times": {"1": "01:00", "2": "03:00", "3": "06:00", "4": "09:00"},
                    "last_run_dates": {},
                    "channel_presets": {"1": None, "2": None, "3": None, "4": None},
                    "items": [
                        {
                            "id": "uploading",
                            "topic": "Uploading episode",
                            "channel": 1,
                            "episode_number": 48,
                            "status": "pending",
                            "task_id": "uploading",
                        },
                    ],
                }
            )

            changed = svc._sync_queue_items_from_tasks_for_save()

            self.assertTrue(changed)
            self.assertFalse(svc._has_inflight_task())
            self.assertEqual(svc._QUEUE["items"], [])
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._QUEUE.clear()
            svc._QUEUE.update(old_queue)
            svc._save_queue_to_disk = old_saver
            svc._STATE_LOADED = old_loaded

class OneClickSafetyStabilityTests(unittest.TestCase):
    def test_uploading_task_does_not_replace_running_workbench_task(self):
        old_tasks = copy.deepcopy(svc._TASKS)
        old_loaded = svc._STATE_LOADED
        old_saver = svc._save_tasks_to_disk
        try:
            svc._STATE_LOADED = True
            svc._save_tasks_to_disk = lambda: None
            svc._TASKS.clear()
            svc._TASKS.update(
                {
                    "uploading": {
                        "task_id": "uploading",
                        "project_id": "project-uploading",
                        "status": "uploading",
                        "topic": "Manual upload retry",
                        "progress_pct": 99.0,
                        "started_at": "2026-05-12T01:00:00Z",
                    },
                    "running": {
                        "task_id": "running",
                        "project_id": "project-running",
                        "status": "running",
                        "topic": "Workbench job",
                        "progress_pct": 31.0,
                        "started_at": "2026-05-12T02:00:00Z",
                    },
                }
            )

            current = svc.get_running_task_info()

            self.assertIsNotNone(current)
            self.assertEqual(current["task_id"], "running")
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._STATE_LOADED = old_loaded
            svc._save_tasks_to_disk = old_saver

    def test_progress_signature_is_stable_and_changes_on_real_progress(self):
        task = {
            "status": "running",
            "current_step": 4,
            "progress_pct": 25.12345,
            "current_step_completed": 2,
            "current_step_active_cut": 3,
            "current_step_cut_progress_pct": 50,
            "sub_status": "이미지 생성 중",
            "completed_cuts_by_step": {"3": 10, "4": 2},
        }

        sig1 = svc._task_progress_signature(task)
        sig2 = svc._task_progress_signature(dict(task))
        self.assertEqual(sig1, sig2)

        changed = dict(task)
        changed["current_step_completed"] = 3
        self.assertNotEqual(sig1, svc._task_progress_signature(changed))

    def test_task_rank_prefers_inflight_over_terminal_status(self):
        completed = {"status": "completed", "updated_at": "2026-05-05T09:00:00"}
        failed = {"status": "failed", "updated_at": "2026-05-05T08:00:00"}
        queued = {"status": "queued", "updated_at": "2026-05-05T07:00:00"}
        running = {"status": "running", "updated_at": "2026-05-05T06:00:00"}

        self.assertGreater(svc._task_rank_for_project_dedupe(failed), svc._task_rank_for_project_dedupe(completed))
        self.assertGreater(svc._task_rank_for_project_dedupe(queued), svc._task_rank_for_project_dedupe(failed))
        self.assertGreater(svc._task_rank_for_project_dedupe(running), svc._task_rank_for_project_dedupe(queued))

    def test_dedupe_tasks_by_project_id_keeps_best_record(self):
        old_tasks = dict(svc._TASKS)
        old_runs = dict(svc._ACTIVE_RUNS)
        try:
            svc._TASKS.clear()
            svc._ACTIVE_RUNS.clear()
            svc._TASKS.update(
                {
                    "completed": {
                        "task_id": "completed",
                        "project_id": "same-project",
                        "status": "completed",
                        "updated_at": "2026-05-05T10:00:00",
                    },
                    "queued": {
                        "task_id": "queued",
                        "project_id": "same-project",
                        "status": "queued",
                        "updated_at": "2026-05-05T09:00:00",
                    },
                    "other": {
                        "task_id": "other",
                        "project_id": "other-project",
                        "status": "failed",
                    },
                }
            )

            changed = svc._dedupe_tasks_by_project_id()

            self.assertTrue(changed)
            self.assertEqual(set(svc._TASKS.keys()), {"queued", "other"})
        finally:
            svc._TASKS.clear()
            svc._TASKS.update(old_tasks)
            svc._ACTIVE_RUNS.clear()
            svc._ACTIVE_RUNS.update(old_runs)

    def test_scheduled_task_does_not_auto_chain_next_generation(self):
        self.assertFalse(svc._should_auto_dispatch_after_task({"triggered_by": "schedule"}))
        self.assertFalse(svc._should_auto_dispatch_after_task({"triggered_by": ""}))
        self.assertTrue(svc._should_auto_dispatch_after_task({"triggered_by": "manual"}))
        self.assertTrue(svc._should_auto_dispatch_after_task({
            "status": "upload_pending",
            "triggered_by": "schedule",
            "step_states": {"6": "completed", "7": "pending"},
        }))


class InterludeStabilityTests(unittest.TestCase):
    def test_default_interval_is_45_cuts_and_first_three_cut_insert_is_kept(self):
        self.assertEqual(DEFAULT_INTERMISSION_EVERY, 45)

        cuts = [f"cut{i}.mp4" for i in range(1, 6)]
        sequence, count = subtitle_router._insert_intermissions_after_cuts(
            cuts,
            "intermission.mp4",
            DEFAULT_INTERMISSION_EVERY,
        )

        self.assertEqual(count, 1)
        self.assertEqual(
            sequence,
            ["cut1.mp4", "cut2.mp4", "cut3.mp4", "intermission.mp4", "cut4.mp4", "cut5.mp4"],
        )

    def test_manual_compose_sequence_matches_render_sequence(self):
        cut_entries = [(f"cut{i}.mp4", 5.0) for i in range(1, 6)]
        sequence, count = interlude_router._build_body_sequence_with_intermission(
            cut_entries,
            "intermission.mp4",
            DEFAULT_INTERMISSION_EVERY,
        )

        self.assertEqual(count, 1)
        self.assertEqual(
            sequence,
            ["cut1.mp4", "cut2.mp4", "cut3.mp4", "intermission.mp4", "cut4.mp4", "cut5.mp4"],
        )

    def test_script_prompt_uses_single_global_base_file(self):
        prompt_source = (Path(__file__).resolve().parent.parent / "app" / "services" / "llm" / "base.py").read_text(
            encoding="utf-8-sig",
        )

        self.assertIn("def get_system_prompt", prompt_source)
        self.assertIn("def _build_user_prompt", prompt_source)
        self.assertIn("SCRIPT_SYSTEM_PROMPT_TEMPLATE", prompt_source)
        self.assertIn("시청자를 끌어들이고 끝까지 시청하게 만드는 유튜브 자동화 파이프라인용 대본 생성기", prompt_source)
        self.assertIn("고정 도입부 구조", prompt_source)
        self.assertIn("대본 강도 계약", prompt_source)
        self.assertIn("반복 금지 계약", prompt_source)
        self.assertIn("주요 인물 첫 등장 컷은", prompt_source)
        self.assertIn("너무 짧게 쓰는 것도 실패", prompt_source)
        self.assertNotIn("SOURCE STORY / ANALOGY CONTEXT", prompt_source)
        self.assertNotIn("anthropomorphic grasshopper character", prompt_source)
        self.assertNotIn("SCRIPT_SYSTEM_PROMPT_KO", prompt_source)
        self.assertNotIn("SCRIPT_SYSTEM_PROMPT_EN", prompt_source)
        self.assertNotIn("SCRIPT_SYSTEM_PROMPT_JA", prompt_source)
        self.assertIn("thumbnail_prompt는 가장 중요한 인물", prompt_source)
        self.assertIn("얼굴은 화면 안에 완전히 보여야 합니다", prompt_source)
        self.assertIn("몸통만 보이는 구도", prompt_source)
        self.assertIn("인물이 전혀 없는 주제일 때만 유물", prompt_source)
        self.assertIn("대본 생성 단계에서는 쇼츠 후보를 선정하지 않습니다", prompt_source)
        self.assertIn("shorts_candidate=false", prompt_source)
        self.assertIn("쇼츠 후보 선정은 대본 생성 뒤 1차 검사 단계에서 수행합니다", prompt_source)
        self.assertIn("본편 narration은 쇼츠로 잘릴 수 있는 독립 문장이 아니라 전체 흐름을 우선합니다", prompt_source)
        self.assertIn("shorts_title", prompt_source)
        self.assertIn("visual_year", prompt_source)
        self.assertIn("image_prompt에는 긴 최종 프롬프트를 쓰지 말고", prompt_source)
        self.assertIn("최종 image_prompt는 백엔드가", prompt_source)
        self.assertIn("최소 10%는 인물 감정 클로즈업", prompt_source)
        self.assertIn("주요 인물 첫 등장 컷은 반드시 medium-close 또는 close-up character entrance", prompt_source)
        self.assertIn("성인 여성 주요인물 첫 등장은 adult woman", prompt_source)

    def test_prepared_script_loader_ignores_non_matching_invalid_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_dir = root / "대본"
            script_dir.mkdir()
            (script_dir / "EP_001_bad.json").write_text(
                json.dumps({
                    "episode_number": 1,
                    "topic": "Other topic",
                    "cuts": [],
                }),
                encoding="utf-8",
            )
            valid_cut = {
                "cut_number": 1,
                "narration": "The target event begins.",
                "image_prompt": (
                    "Year/period: test period; Exact place: test place; "
                    "Scene evidence: clay cup; Style: simple; Scene: visible person face; "
                    "Main subject: visible person face"
                ),
                "visual_year": "test period",
                "visual_period": "test period",
                "visual_location": "test place",
                "visual_evidence": "clay cup",
            }
            (script_dir / "EP_002_good.json").write_text(
                json.dumps({
                    "episode_number": 2,
                    "topic": "Target topic",
                    "title": "Target title",
                    "cuts": [valid_cut],
                }),
                encoding="utf-8",
            )

            original_resolver = pipeline_tasks.resolve_project_dir
            pipeline_tasks.resolve_project_dir = lambda *args, **kwargs: root
            try:
                selected, source_path = pipeline_tasks._load_prepared_script(
                    "unit-project",
                    {"episode_number": 2},
                    "Target topic",
                )
            finally:
                pipeline_tasks.resolve_project_dir = original_resolver

        self.assertEqual(selected["episode_number"], 2)
        self.assertTrue(source_path.endswith("EP_002_good.json"))

    def test_prepared_script_validation_accepts_source_without_blocks(self):
        script = {
            "script_version": "3.1",
            "episode_number": 1,
            "topic": "Prepared source topic",
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "The source line repeats.",
                    "image_prompt": (
                        "Year/period: test period; Exact place: test place; "
                        "Scene evidence: clay cup; Style: simple; Scene: first visible person face; "
                        "Main subject: first visible person face"
                    ),
                    "visual_year": "test period",
                    "visual_period": "test period",
                    "visual_location": "test place",
                    "visual_evidence": "clay cup",
                },
                {
                    "cut_number": 2,
                    "narration": "The source line repeats.",
                    "image_prompt": (
                        "Year/period: test period; Exact place: test place; "
                        "Scene evidence: clay cup; Style: simple; Scene: second visible person face; "
                        "Main subject: second visible person face"
                    ),
                    "visual_year": "test period",
                    "visual_period": "test period",
                    "visual_location": "test place",
                    "visual_evidence": "clay cup",
                },
            ],
        }

        pipeline_tasks._validate_prepared_script(script, "prepared_source.json")

    def test_prepared_script_validation_rejects_early_next_episode_preview(self):
        cuts = []
        for idx in range(1, 151):
            narration = "The prepared episode continues."
            scene = "period laboratory evidence on a wooden bench"
            if idx == 125:
                narration = "In our next episode, we travel to Imperial Russia."
                scene = "mechanical gears dissolving into a Russian blizzard"
            cuts.append({
                "cut_number": idx,
                "narration": narration,
                "image_prompt": (
                    "Year/period: 1944 AD; Exact place: Worthington, Ohio; "
                    f"Scene evidence: test cut {idx}; Style: simple; "
                    f"Main subject: {scene}; Scene: {scene}"
                ),
                "visual_year": "1944 AD",
                "visual_period": "1944 AD",
                "visual_location": "Worthington, Ohio",
                "visual_evidence": "prepared source test",
            })
        script = {
            "script_version": "3.1",
            "episode_number": 14,
            "topic": "The Inventor Strangled by His Own Genius: Thomas Midgley Jr.",
            "cuts": cuts,
        }

        with self.assertRaisesRegex(ValueError, "다음 회차 예고"):
            pipeline_tasks._validate_prepared_script(script, "prepared_source.json")

    def test_prepared_script_loader_skips_matching_invalid_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_dir = root / "대본"
            script_dir.mkdir()
            cuts = []
            for idx in range(1, 151):
                narration = "The prepared episode continues."
                scene = "period laboratory evidence on a wooden bench"
                if idx == 125:
                    narration = "In our next episode, we travel to Imperial Russia."
                    scene = "mechanical gears dissolving into a Russian blizzard"
                cuts.append({
                    "cut_number": idx,
                    "narration": narration,
                    "image_prompt": (
                        "Year/period: 1944 AD; Exact place: Worthington, Ohio; "
                        f"Scene evidence: test cut {idx}; Style: simple; "
                        f"Main subject: {scene}; Scene: {scene}"
                    ),
                    "visual_year": "1944 AD",
                    "visual_period": "1944 AD",
                    "visual_location": "Worthington, Ohio",
                    "visual_evidence": "prepared source test",
                })
            (script_dir / "EP_014_empire_errors_prepared.json").write_text(
                json.dumps({
                    "script_version": "3.1",
                    "episode_number": 14,
                    "topic": "The Inventor Strangled by His Own Genius: Thomas Midgley Jr.",
                    "cuts": cuts,
                }),
                encoding="utf-8",
            )

            original_resolver = pipeline_tasks.resolve_project_dir
            pipeline_tasks.resolve_project_dir = lambda *args, **kwargs: root
            try:
                selected = pipeline_tasks._load_prepared_script(
                    "unit-project",
                    {"episode_number": 14},
                    "The Inventor Strangled by His Own Genius: Thomas Midgley Jr.",
                )
            finally:
                pipeline_tasks.resolve_project_dir = original_resolver

        self.assertIsNone(selected)

    def test_script_router_checks_prepared_script_before_llm_path(self):
        self.assertIn(
            "_load_prepared_script_for_router",
            inspect.getsource(script_router.generate_script_async),
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            script_dir = root / "대본"
            script_dir.mkdir()
            valid_cut = {
                "cut_number": 1,
                "narration": "The target event begins.",
                "image_prompt": (
                    "Year/period: test period; Exact place: test place; "
                    "Scene evidence: clay cup; Style: simple; Scene: visible person face; "
                    "Main subject: visible person face"
                ),
                "visual_year": "test period",
                "visual_period": "test period",
                "visual_location": "test place",
                "visual_evidence": "clay cup",
            }
            (script_dir / "EP_002_good.json").write_text(
                json.dumps({
                    "episode_number": 2,
                    "topic": "Target topic",
                    "title": "Target title",
                    "cuts": [valid_cut],
                }),
                encoding="utf-8",
            )

            original_resolver = pipeline_tasks.resolve_project_dir
            pipeline_tasks.resolve_project_dir = lambda *args, **kwargs: root
            try:
                selected = script_router._load_prepared_script_for_router(
                    "unit-project",
                    {"episode_number": 2},
                    "Target topic",
                )
            finally:
                pipeline_tasks.resolve_project_dir = original_resolver

        self.assertEqual(selected["title"], "Target title")

    def test_dashboard_script_generation_skips_story_plan_stage(self):
        sync_source = inspect.getsource(script_router.generate_script)
        async_source = inspect.getsource(script_router.generate_script_async)
        pipeline_source = inspect.getsource(pipeline_tasks._step_script)

        self.assertIn("skip_story_plan_generation", sync_source)
        self.assertIn("skip_story_plan_generation", async_source)
        self.assertIn("skip_story_plan_generation", pipeline_source)
        self.assertNotIn("generate_story_plan_for_project", sync_source)
        self.assertNotIn("generate_story_plan_for_project", async_source)
        self.assertNotIn("generate_story_plan_for_project", pipeline_source)

        service = StoryPlanProbeLLM()
        plan = asyncio.run(service._ensure_story_plan_for_script(
            "Target topic",
            {"skip_story_plan_generation": True, "target_cuts": 10},
        ))

        self.assertIsNone(plan)
        self.assertEqual(service.story_plan_calls, 0)

    def test_v31_scene_blocks_are_normalized_to_actual_cut_count(self):
        script = {
            "script_version": "3.1",
            "story_core": {"story_axis": "보이지 않는 선"},
            "scene_blocks": [
                {"block_id": i, "cut_range": f"{(i - 1) * 10 + 1}-{i * 10}"}
                for i in range(1, 6)
            ],
            "cuts": [
                {
                    "cut_number": i,
                    "scene_block_id": min(5, ((i - 1) // 3) + 1),
                    "narration": f"보이지 않는 선의 흐름을 설명하는 {i}번째 대사입니다.",
                    "image_prompt": (
                        "Year/period: contemporary Korea; Exact place: Seoul; "
                        f"Scene evidence: transit line {i}; Style: simple; "
                        f"Scene: visible commuters moving through station {i}; "
                        f"Main subject: commuter group {i}"
                    ),
                }
                for i in range(1, 16)
            ],
        }

        normalized = BaseLLMService.normalize_v31_story_contract(
            script,
            {"skip_story_plan_generation": True},
            "보이지 않는 선",
        )
        issues = inspect_script_quality(normalized, "보이지 않는 선")

        self.assertEqual(len(normalized["scene_blocks"]), 2)
        self.assertEqual(normalized["scene_blocks"][0]["cut_range"], "1-10")
        self.assertEqual(normalized["scene_blocks"][1]["cut_range"], "11-15")
        self.assertEqual(normalized["cuts"][0]["scene_block_id"], 1)
        self.assertEqual(normalized["cuts"][-1]["scene_block_id"], 2)
        self.assertFalse(any("scene_blocks count mismatch" in issue for issue in issues))

    def test_thumbnail_prompt_forces_visible_character_face(self):
        prompt = build_standard_thumbnail_prompt({
            "topic": "곰이 사람이 됐다는 말, 사실은 왕권 이야기였다",
            "thumbnail_prompt": (
                "Year/period: Mythic Gojoseon foundation tradition; "
                "Scene: sacred mountain under a pale sky, sacred tree in the foreground; "
                "Main subject: sacred mountain and tree"
            ),
        })

        self.assertIn("THUMBNAIL FACE VISIBILITY LOCK", prompt)
        self.assertIn("show the full face clearly in frame", prompt)
        self.assertIn("torso-only framing", prompt)
        self.assertIn("cropped head", prompt)
        self.assertIn("back view", prompt)
        self.assertIn("This face rule overrides any earlier scenery", prompt)

    def test_thumbnail_closeup_prompt_blocks_rider_and_gate_composition(self):
        prompt = build_standard_thumbnail_prompt({
            "thumbnail_prompt": "Close-up of Toyotomi Hideyoshi's face, tense eyes, dark sea behind him",
        })

        self.assertTrue(_thumbnail_prompt_expects_face_closeup(prompt))
        self.assertIn("late sixteenth century Japanese male warlord", prompt)
        self.assertIn("THUMBNAIL CLOSE-UP FACE FRAME LOCK", prompt)
        self.assertIn("Do not use a horse, mounted rider", prompt)
        self.assertIn("large gate", prompt)
        self.assertIn("face fills 50-65 percent of image height", prompt)
        self.assertIn("army, crowd, gate, road, mountain, or battlefield detail stays blurred", prompt)
        self.assertIn("army crowd composition", prompt)

    def test_thumbnail_retry_prompt_suppresses_competing_army_background(self):
        prompt = _thumbnail_retry_prompt(
            "Close-up portrait of Eulji Mundeok's face, tense eyes",
            "the image featured a distant army in the background",
        )

        self.assertIn("occupying 50-65 percent of image height", prompt)
        self.assertIn("Use one face only", prompt)
        self.assertIn("Background armies, crowds, gates, rooftops, mountains", prompt)
        self.assertIn("must not compete with the face", prompt)
        self.assertIn("wide battlefield composition", prompt)
        self.assertIn("LOWER-LEFT TEXT-SAFE ZONE LOCK", prompt)
        self.assertIn("No face, eyes, nose, mouth, chin, hands, body", prompt)

    def test_thumbnail_named_eulji_prompt_forces_closeup_over_army_scene(self):
        prompt = build_standard_thumbnail_prompt({
            "thumbnail_prompt": (
                "Year/period: 612year 6~7; "
                "Scene: Eulji Mundeok standing on a foggy hill, looking down at "
                "a massive starving army with a cold smirk"
            ),
        })

        self.assertIn("Head-and-shoulders close-up portrait of early seventh-century Goguryeo", prompt)
        self.assertIn("commander Eulji Mundeok", prompt)
        self.assertIn("THUMBNAIL CLOSE-UP FACE FRAME LOCK", prompt)
        self.assertIn("piercing eyes sharp and looking toward the viewer", prompt)
        self.assertIn("featureless dark rainstorm background", prompt)
        self.assertIn("no hand prop, no scroll, no poem object", prompt)
        self.assertNotIn("rolled blank five-character poem message", prompt)
        self.assertNotIn("standing on a foggy hill", prompt)

    def test_thumbnail_goguryeo_king_prompt_forces_face_over_monument_scene(self):
        prompt = build_standard_thumbnail_prompt({
            "thumbnail_prompt": (
                "Year/period: 618~640around year; "
                "Scene: A ruined victory monument of skulls being smashed by foreign soldiers, "
                "a Goguryeo king watching passively in the shadows"
            ),
        })

        self.assertIn("Head-and-shoulders close-up portrait of the early seventh-century Goguryeo king", prompt)
        self.assertIn("smashed Goguryeo victory monument and skull-trophy war mound only blurred", prompt)
        self.assertIn("LOWER-LEFT TEXT-SAFE ZONE LOCK", prompt)
        self.assertIn("No face, eyes, nose, mouth, chin, hands, body", prompt)
        self.assertNotIn("watching passively in the shadows", prompt)

    def test_thumbnail_named_tokugawa_prompt_removes_hand_prop_scroll(self):
        prompt = build_standard_thumbnail_prompt({
            "thumbnail_prompt": (
                "Close-up of Tokugawa Ieyasu, older Japanese daimyo with controlled "
                "intense eyes, wearing late Sengoku lamellar armor and kabuto helmet, "
                "tense war camp shadows, sealed blank letters piled near his shoulder"
            ),
        })

        self.assertIn("Head-and-shoulders close-up portrait of Tokugawa Ieyasu", prompt)
        self.assertIn("calculated betrayed stare", prompt)
        self.assertIn("featureless dark war-camp smoke background", prompt)
        self.assertIn("no hand prop, no scroll, no document, no paper roll", prompt)
        self.assertNotIn("sealed blank letters piled near his shoulder", prompt)

    def test_thumbnail_named_sunanda_prompt_uses_drowning_danger_not_command_pose(self):
        prompt = build_standard_thumbnail_prompt({
            "thumbnail_prompt": (
                "Close-up of Queen Sunanda Kumariratana, an adult Siamese queen "
                "consort in late nineteenth-century court silk and gold ornaments, "
                "terrified yet dignified, wet royal parasol shadow behind her, "
                "dark Chao Phraya water rising"
            ),
        })

        self.assertIn("Queen Sunanda Kumariratana", prompt)
        self.assertIn("dark Chao Phraya river water rising", prompt)
        self.assertIn("THUMBNAIL DROWNING DANGER LOCK", prompt)
        self.assertIn("caught in the fatal water moment", prompt)
        self.assertNotIn("standing in command pose", prompt)

    def test_korean_thumbnail_hook_compacts_army_psychological_warfare(self):
        overlay = build_clickbait_thumbnail_overlay({
            "thumbnail_hook": "30만 대군을 굶겨 죽인 심리전! 거대 제국을 붕괴시킨 천재 명장",
        })

        self.assertEqual(overlay, "30만대군\n굶긴 심리전")

    def test_thumbnail_basic_quality_rejects_flat_background(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "thumbnail_bg.png"
            Image.new("RGB", (1280, 720), (24, 24, 24)).save(path)

            ok, reason = _basic_thumbnail_file_check(str(path))

        self.assertFalse(ok)
        self.assertIn(reason, {"nearly_flat_image", "low_visual_variance"})

    def test_comfyui_corner_artist_mark_detects_upper_left_red_stamp(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cut.png"
            image = Image.new("RGB", (1280, 720), (42, 42, 42))
            draw = ImageDraw.Draw(image)
            draw.rectangle((28, 18, 76, 72), fill=(150, 24, 20))
            draw.line((38, 26, 66, 64), fill=(235, 235, 225), width=4)
            image.save(path)

            self.assertTrue(_image_has_corner_artist_mark(path))

    def test_comfyui_top_caption_detects_upper_left_dark_title(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_top_caption_like_text

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "upper_left_title.png"
            image = Image.new("RGB", (1280, 720), (232, 230, 216))
            draw = ImageDraw.Draw(image)
            for x in (48, 78, 108, 138, 172):
                draw.line((x, 38, x + 10, 92), fill=(18, 18, 16), width=5)
                draw.line((x - 8, 60, x + 22, 56), fill=(18, 18, 16), width=4)
            for x in (52, 88, 126, 166):
                draw.line((x, 118, x + 28, 118), fill=(24, 24, 20), width=3)
            image.save(path)

            self.assertTrue(_image_has_top_caption_like_text(path))

    def test_comfyui_top_caption_ignores_cloud_outline_texture(self):
        from PIL import Image, ImageDraw
        from app.services.image.comfyui_service import _image_has_top_caption_like_text

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cloud_outline.png"
            wide_path = Path(td) / "wide_smoke_outline.png"
            image = Image.new("RGB", (1280, 720), (226, 224, 210))
            draw = ImageDraw.Draw(image)
            for cx, cy, rx, ry in (
                (120, 48, 100, 34),
                (270, 38, 130, 48),
                (430, 52, 115, 44),
                (116, 96, 58, 36),
                (318, 96, 74, 42),
            ):
                draw.arc((cx - rx, cy - ry, cx + rx, cy + ry), 180, 350, fill=(48, 48, 44), width=3)
            for x in range(70, 470, 55):
                draw.arc((x, 74, x + 46, 116), 190, 345, fill=(58, 58, 52), width=2)
            image.save(path)

            wide = Image.new("RGB", (1280, 720), (238, 236, 224))
            wide_draw = ImageDraw.Draw(wide)
            for x in range(170, 1120, 42):
                y = 28 + (x * 11) % 80
                wide_draw.arc((x - 60, y - 35, x + 70, y + 48), 185, 350, fill=(42, 42, 38), width=3)
                wide_draw.arc((x - 20, y + 10, x + 110, y + 74), 190, 350, fill=(62, 62, 56), width=2)
            wide.save(wide_path)

            self.assertFalse(_image_has_top_caption_like_text(path))
            self.assertFalse(_image_has_top_caption_like_text(wide_path))

    def test_comfyui_corner_artist_mark_detects_lower_corner_signatures(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as td:
            left_path = Path(td) / "left.png"
            left_image = Image.new("RGB", (1280, 720), (24, 24, 24))
            left_draw = ImageDraw.Draw(left_image)
            for x in (28, 58, 88, 118):
                left_draw.rectangle((x, 632, x + 5, 690), fill=(235, 235, 235))
            left_draw.rectangle((28, 660, 140, 664), fill=(235, 235, 235))
            left_image.save(left_path)

            right_path = Path(td) / "right.png"
            right_image = Image.new("RGB", (1280, 720), (26, 26, 26))
            right_draw = ImageDraw.Draw(right_image)
            right_draw.rectangle((1212, 660, 1216, 704), fill=(235, 235, 235))
            right_draw.rectangle((1232, 660, 1236, 704), fill=(235, 235, 235))
            right_draw.rectangle((1212, 682, 1236, 686), fill=(235, 235, 235))
            right_image.save(right_path)

            self.assertTrue(_image_has_corner_artist_mark(left_path))
            self.assertTrue(_image_has_corner_artist_mark(right_path))

    def test_comfyui_light_margin_detects_soft_white_illustration_frame(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "framed.png"
            image = Image.new("RGB", (1280, 720), (32, 32, 32))
            draw = ImageDraw.Draw(image)
            frame = (210, 210, 205)
            draw.rectangle((0, 0, 1279, 7), fill=frame)
            draw.rectangle((0, 0, 7, 719), fill=frame)
            draw.rectangle((1272, 0, 1279, 719), fill=frame)
            image.save(path)

            self.assertTrue(_image_has_solid_light_outer_margin(path))

    def test_thumbnail_vision_qa_allows_prompt_matched_people(self):
        prompt = _thumbnail_quality_system_prompt()

        self.assertIn("pre-overlay thumbnail image", prompt)
        self.assertIn("Do not fail solely because a recognizable human face", prompt)
        self.assertIn("when that matches the prompt", prompt)
        self.assertIn("background-only, object-only", prompt)

    def test_thumbnail_vision_qa_detects_person_presence_misread(self):
        self.assertTrue(_thumbnail_prompt_expects_person("Close-up of Toyotomi Hideyoshi's face"))
        self.assertTrue(_thumbnail_person_presence_misread(
            "The image includes a visible human face, which does not match the prompt "
            "for an object-only scene."
        ))
        self.assertFalse(_thumbnail_person_presence_misread(
            "The image includes a mounted rider and horse, which does not match the prompt "
            "for an object-only scene.",
            "Close-up of Toyotomi Hideyoshi's face",
        ))
        self.assertFalse(_thumbnail_person_presence_misread(
            "The image includes a recognizable human face, which does not match the prompt's "
            "requirement for an object-only focus.; The main subject is not clear due to "
            "the presence of a person and horse.",
            "Close-up of the Goguryeo king's face",
        ))
        self.assertFalse(_thumbnail_person_presence_misread(
            "The image includes a visible human face and fake text on signage."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The image features a close-up face, but the background includes "
            "additional figures and elements that detract from the focus on the face."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The face does not fill 50-65 percent of the image height; "
            "the background competes with the main subject; forehead and chin are cropped."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The main subject is a close-up face, but the image includes additional elements "
            "that detract from the focus on a single face.; The face does not fill 50-65% "
            "of the image height as required for a close-up portrait.; Background elements "
            "are not blurred or low-detail, competing with the face."
        ))
        self.assertFalse(_thumbnail_closeup_soft_quality_failure(
            "The close-up face has a UI watermark in the corner."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The image features a mounted rider, which does not match the prompt for "
            "a close-up face or portrait.; The main subject is not a head-and-shoulders "
            "close-up portrait as required.; The background includes additional figures "
            "and structures that detract from the focus on a single readable face."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The image features a mounted rider, but the prompt specifically requests "
            "a close-up face or portrait.; The main subject is not a head-and-shoulders "
            "portrait; it includes a full-body rider and horse.; The background contains "
            "additional figures and structures that detract from the focus on the face."
        ))
        self.assertFalse(_thumbnail_closeup_soft_quality_failure(
            "The image features a full-body rider with visible horse body, horse legs, and saddle."
        ))
        self.assertFalse(_thumbnail_closeup_soft_quality_failure(
            "The main subject is not clear due to the presence of a person and horse."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The image features a mounted rider, but the prompt requires a clear focus "
            "on an unmarked surface or object-only evidence.; The presence of the rider "
            "and horse does not align with the specified requirements for an object-only "
            "scene.; The background includes flags and a structure."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The image features a mounted rider, which does not match the prompt for "
            "an object-only evidence cut.; The presence of a horse and rider does not "
            "align with the requirement for unmarked surfaces and object-only evidence."
        ))
        self.assertTrue(_thumbnail_closeup_soft_quality_failure(
            "The main subject is not clear and clickable as it does not focus on a single dominant "
            "character or action.; The composition does not effectively reserve space for text "
            "overlay, as the main subject is not positioned to allow for a clean text-safe zone."
        ))

    def test_shorts_validation_allows_recoverable_ffmpeg_stderr_when_exit_ok(self):
        async def fake_run_subprocess(*_args, **_kwargs):
            return (
                0,
                b"",
                b"[h264] Invalid NAL unit size (0 > 23344)\n"
                b"[h264] Error splitting the input into NAL units\n",
            )

        original = shorts_service.run_subprocess
        shorts_service.run_subprocess = fake_run_subprocess
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "short_1.mp4"
                path.write_bytes(b"not a real mp4 but subprocess is stubbed")
                asyncio.run(shorts_service._validate_rendered_video("ffmpeg", path, "short_1"))
        finally:
            shorts_service.run_subprocess = original

    def test_shorts_validation_fails_when_ffmpeg_exit_is_nonzero(self):
        async def fake_run_subprocess(*_args, **_kwargs):
            return (1, b"", b"Invalid data found when processing input")

        original = shorts_service.run_subprocess
        shorts_service.run_subprocess = fake_run_subprocess
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "short_1.mp4"
                path.write_bytes(b"not a real mp4 but subprocess is stubbed")
                with self.assertRaises(RuntimeError):
                    asyncio.run(shorts_service._validate_rendered_video("ffmpeg", path, "short_1"))
        finally:
            shorts_service.run_subprocess = original

    def test_english_thumbnail_overlay_uses_strong_factual_hook(self):
        overlay = build_clickbait_thumbnail_overlay(
            {"title": "William I's Fatal Raid: The Death That Split an Empire", "language": "en"},
            "William I's Fatal Raid: The Death That Split an Empire",
            {"language": "en"},
        )

        self.assertEqual(overlay, "DEATH\nSPLIT EMPIRE")

    def test_english_thumbnail_overlay_uses_fatal_rage_hook(self):
        overlay = build_clickbait_thumbnail_overlay(
            {"thumbnail_hook": "Killed by Blood Pressure!", "language": "en"},
            "The Fatal Rage: The Apocalyptic Anger of Valentinian I",
            {"language": "en"},
        )

        self.assertEqual(overlay, "FATAL\nRAGE")

    def test_english_thumbnail_overlay_uses_crushing_throne_hook(self):
        overlay = build_clickbait_thumbnail_overlay(
            {"title": "The Throne That Crushed King Béla I EP.19", "language": "en"},
            "The Throne That Crushed King Béla I EP.19",
            {"language": "en"},
        )

        self.assertEqual(overlay, "THRONE\nCRUSHED HIM")

    def test_english_thumbnail_overlay_uses_sunanda_drowning_hook(self):
        overlay = build_clickbait_thumbnail_overlay(
            {
                "title": "The Untouchable Queen: The Tragic Drowning of Sunanda Kumariratana",
                "language": "en",
            },
            "The Untouchable Queen: The Tragic Drowning of Sunanda Kumariratana",
            {"language": "en"},
        )

        self.assertEqual(overlay, "POWER\nDROWNED HER")

        overlay_from_hook = build_clickbait_thumbnail_overlay(
            {
                "title": "The Queen No One Was Supposed to Touch EP.20",
                "thumbnail_hook": "UNTOUCH\nPOWER",
                "language": "en",
            },
            "The Queen No One Was Supposed to Touch EP.20",
            {"language": "en"},
        )

        self.assertEqual(overlay_from_hook, "POWER\nDROWNED HER")

    def test_thumbnail_prompt_forces_crushing_throne_mechanism(self):
        prompt = build_standard_thumbnail_prompt({
            "language": "en",
            "title": "The Throne That Crushed King Béla I EP.19",
            "thumbnail_prompt": (
                "Close-up of King Béla I of Hungary, stern middle-aged 11th-century "
                "Central European ruler with dark beard, wool cloak, simple crown slipping, "
                "broken wooden royal seat behind his shoulders, stunned nobles in shadow"
            ),
        })

        self.assertIn("Extreme close-up of King Bela I", prompt)
        self.assertIn("heavy wooden royal throne collapses toward him", prompt)
        self.assertIn("THUMBNAIL FATAL MECHANISM LOCK", prompt)
        self.assertIn("Do not make a calm ruler portrait", prompt)
        self.assertIn("fatal mechanism as a huge foreground threat", prompt)
        self.assertNotIn("stern middle-aged", prompt)

    def test_thumbnail_overlay_wrap_preserves_explicit_newlines(self):
        from PIL import Image, ImageDraw, ImageFont

        image = Image.new("RGB", (1280, 720))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()

        self.assertEqual(
            _wrap_text("THRONE\nCRUSHED HIM", font, 1200, draw),
            ["THRONE", "CRUSHED HIM"],
        )

    def test_thumbnail_qa_rejects_calm_portrait_without_fatal_mechanism(self):
        prompt = _thumbnail_quality_system_prompt()

        self.assertIn("fail calm portraits", prompt)
        self.assertIn("crushing throne", prompt)
        self.assertIn("collapsing chair", prompt)

    def test_standard_thumbnail_prompt_adds_fact_locked_provocation(self):
        prompt = build_standard_thumbnail_prompt({
            "topic": "The Fatal Rage: The Apocalyptic Anger of Valentinian I",
            "language": "en",
        })

        self.assertIn("fact-locked", prompt)
        self.assertIn("explosive rage", prompt)
        self.assertIn("exact second before disaster", prompt)
        self.assertIn("Do not fabricate gore", prompt)
        self.assertIn("lower-left text-safe zone", prompt)
        self.assertIn("No face, eyes, mouth, or important hand", prompt)

    def test_thumbnail_quality_prompts_reject_face_covered_by_overlay(self):
        background_prompt = _thumbnail_quality_system_prompt()
        overlay_prompt = _thumbnail_overlay_quality_system_prompt()

        self.assertIn("lower-left text-safe zone", background_prompt)
        self.assertIn("face, eyes, nose, mouth, chin", background_prompt)
        self.assertIn("Use pass=false", overlay_prompt)
        self.assertIn("overlay text", overlay_prompt)
        self.assertIn("eyes, nose", overlay_prompt)

    def test_thumbnail_overlay_layout_penalizes_face_overlap(self):
        face_boxes = [(40, 450, 430, 700)]
        lower_left_text = [(55, 470, 510, 680)]
        lower_right_text = [(730, 470, 1215, 680)]

        self.assertGreater(
            _thumbnail_text_layout_score(lower_left_text, face_boxes, 0),
            _thumbnail_text_layout_score(lower_right_text, face_boxes, 1),
        )

    def test_thumbnail_overlay_fallback_face_zone_avoids_lower_face_band(self):
        face_boxes = _thumbnail_fallback_face_safe_boxes("Close-up of Kim Chunchu's face, tense eyes")
        lower_left_text = [(55, 470, 510, 680)]
        upper_left_text = [(55, 54, 510, 240)]

        self.assertTrue(face_boxes)
        self.assertEqual(_thumbnail_fallback_face_safe_boxes("empty battlefield"), [])
        self.assertGreater(
            _thumbnail_text_layout_score(lower_left_text, face_boxes, 0),
            _thumbnail_text_layout_score(upper_left_text, face_boxes, 2),
        )

    def test_thumbnail_overlay_local_geometry_rejects_text_inside_face_core_only(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as td:
            safe_path = Path(td) / "safe.png"
            unsafe_path = Path(td) / "unsafe.png"
            prompt = "Close-up of Kim Chunchu's face, tense eyes"

            safe = Image.new("RGB", (1280, 720), (24, 24, 24))
            safe_draw = ImageDraw.Draw(safe)
            safe_draw.rectangle((60, 60, 280, 170), fill=(255, 255, 255))
            safe_draw.rectangle((60, 180, 250, 260), fill=(255, 226, 32))
            safe.save(safe_path)

            unsafe = Image.new("RGB", (1280, 720), (24, 24, 24))
            unsafe_draw = ImageDraw.Draw(unsafe)
            unsafe_draw.rectangle((610, 170, 860, 320), fill=(255, 255, 255))
            unsafe_draw.rectangle((610, 340, 820, 460), fill=(255, 226, 32))
            unsafe.save(unsafe_path)

            self.assertTrue(_thumbnail_overlay_local_geometry_pass(str(safe_path), prompt))
            self.assertFalse(_thumbnail_overlay_local_geometry_pass(str(unsafe_path), prompt))
            self.assertFalse(_thumbnail_overlay_local_geometry_pass(str(safe_path), "empty battlefield"))

    def test_thumbnail_overlay_uses_absolute_font_sizes_and_no_ep_badge(self):
        title, episode_label = extract_thumbnail_text_parts("EP.14 Target title", "EP.14")
        source = (Path(__file__).resolve().parent.parent / "app" / "services" / "thumbnail_service.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(title, "Target title")
        self.assertIsNone(episode_label)
        self.assertIn("candidates = (98, 87, 76, 67", source)
        self.assertNotIn("THUMBNAIL_TEXT_OVERLAY_SCALE", source)
        self.assertNotIn("class=\"top\"", source)
        self.assertNotIn("좌상단 EP 배지", source)

    def test_thumbnail_fallback_and_request_reject_body_only_faces(self):
        fallback = BaseLLMService._fallback_thumbnail_prompt(
            title="왕권 이야기",
            topic="단군신화",
            language="ko",
            character_description="Ungnyeo in simple ancient clothing",
        )
        request = BaseLLMService._build_thumbnail_prompt_request(
            title="왕권 이야기",
            topic="단군신화",
            narration="웅녀와 단군왕검을 설명한다.",
            language="ko",
            character_description="Ungnyeo in simple ancient clothing",
        )

        self.assertIn("full face clearly visible", fallback)
        self.assertIn("strongest factual stake", fallback)
        self.assertIn("Never invent gore", fallback)
        self.assertIn("torso-only framing", fallback)
        self.assertIn("FACT-LOCKED PROVOCATION", request)
        self.assertIn("explosive rage", request)
        self.assertIn("full visible face", request)
        self.assertIn("torso-only", request)
        self.assertIn("faceless silhouette", request)

    def test_thumbnail_quality_failure_does_not_fallback_to_first_cut(self):
        quality_error = ThumbnailError("AI 썸네일 품질검증 실패: mounted rider")
        overlay_error = ThumbnailError("AI 썸네일 최종 오버레이 품질검증 실패: overlay text covers eyes")
        technical_error = ThumbnailError("AI 썸네일 배경 생성 실패: timeout")

        self.assertFalse(_thumbnail_error_allows_first_cut_fallback(quality_error))
        self.assertFalse(_thumbnail_error_allows_first_cut_fallback(overlay_error))
        self.assertTrue(_thumbnail_error_allows_first_cut_fallback(technical_error))

    def test_thumbnail_fallback_overlay_guard_runs_final_qa(self):
        calls = []
        old_generate = thumb_svc.generate_thumbnail
        old_validate = thumb_svc._validate_thumbnail_final_overlay

        def fake_generate_thumbnail(**kwargs):
            return kwargs["output_path"]

        async def fake_validate_thumbnail_final_overlay(**kwargs):
            calls.append(kwargs)
            return False, "overlay text covers eyes"

        try:
            thumb_svc.generate_thumbnail = fake_generate_thumbnail
            thumb_svc._validate_thumbnail_final_overlay = fake_validate_thumbnail_final_overlay
            rendered_path, accepted, reason = asyncio.run(
                thumb_svc._generate_thumbnail_with_overlay_guard(
                    project_id="proj",
                    title="FATAL\nRAGE",
                    base_image_path="base.png",
                    output_path="thumb.png",
                    image_prompt="close-up face thumbnail",
                    config={"thumbnail_quality_check": True},
                )
            )
        finally:
            thumb_svc.generate_thumbnail = old_generate
            thumb_svc._validate_thumbnail_final_overlay = old_validate

        self.assertEqual(rendered_path, "thumb.png")
        self.assertFalse(accepted)
        self.assertEqual(reason, "overlay text covers eyes")
        self.assertEqual(calls[0]["overlay_text"], "FATAL\nRAGE")

    def test_script_uses_four_to_six_second_tts_window(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "ko",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(limits["target_min_sec"], 4.0)
        self.assertEqual(limits["target_sec"], 5.0)
        self.assertEqual(limits["target_max_sec"], 6.0)
        self.assertEqual(limits["target_range"], "40~60")

        ja_limits = BaseLLMService._calc_narration_limits({
            "language": "ja",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(ja_limits["target_min_sec"], 4.0)
        self.assertEqual(ja_limits["target_sec"], 5.0)
        self.assertEqual(ja_limits["target_max_sec"], 6.0)
        self.assertEqual(ja_limits["target_range"], "38~56")

    def test_cut_video_duration_does_not_expand_script_tts_window(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "en",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 8.0,
        })

        self.assertEqual(limits["target_min_sec"], 4.0)
        self.assertEqual(limits["target_sec"], 5.0)
        self.assertEqual(limits["target_max_sec"], 6.0)

    def test_legacy_script_tts_tolerance_cannot_shrink_four_to_six_window(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "ko",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "script_tts_target_sec": 3.6,
            "script_tts_tolerance_sec": 0.4,
        })

        self.assertEqual(limits["target_min_sec"], 4.0)
        self.assertEqual(limits["target_sec"], 5.0)
        self.assertEqual(limits["target_max_sec"], 6.0)
        self.assertEqual(limits["target_range"], "40~60")

    def test_timing_retry_instruction_is_added_to_script_prompt(self):
        svc_probe = StoryPlanProbeLLM()
        config = {
            "language": "ko",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "__script_timing_retry_instruction": BaseLLMService._script_timing_retry_instruction(
                {
                    "language": "ko",
                    "tts_model": "elevenlabs",
                    "tts_speed": 1.0,
                },
                [{"cut_number": 1, "amount": 58, "unit": "chars", "target_range": "40~60"}],
            ),
        }

        prompt = svc_probe._get_system_prompt(config)

        self.assertIn("내레이션 길이 재생성 지시", prompt)
        self.assertIn("cut 1=58chars", prompt)
        self.assertIn("전체 JSON을 처음부터 다시 작성", prompt)

    def test_script_timing_violation_blocks_save(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": (
                        "대한민국 어디선가 지금 이 순간에도 전력망은 20기가와트에서 30기가와트를 공급하고 있고, "
                        "통신 기지국은 하루 수십억 신호를 처리하고 있습니다."
                    ),
                    "image_prompt": "Scene: infrastructure control room; Main subject: operator",
                }
            ]
        }

        with self.assertRaisesRegex(ValueError, "script narration timing failed"):
            BaseLLMService.assert_script_timing(script, {
                "language": "ko",
                "tts_model": "elevenlabs",
                "tts_speed": 1.0,
                "cut_video_duration": 4.0,
            })

    def test_tts_duration_status_treats_over_slot_audio_as_long(self):
        cfg = {"cut_video_duration": 4.0}

        self.assertEqual(narration_fit._duration_status(3.7, cfg), "short")
        self.assertEqual(narration_fit._duration_status(4.0, cfg), "target_fit")
        self.assertEqual(narration_fit._duration_status(4.2, cfg), "window_fit")
        self.assertEqual(narration_fit._duration_status(4.21, cfg), "too_long")


class ShortsStabilityTests(unittest.TestCase):
    def test_shorts_keeps_marked_cut_clip_speed(self):
        self.assertEqual(shorts_service.SHORTS_PLAYBACK_SPEED, 1.0)

    def test_shorts_channel_name_position_matches_ten_minute_history_layout(self):
        self.assertEqual(shorts_service.SHORTS_CHANNEL_Y, 1450)
        self.assertEqual(shorts_service.SHORTS_CHANNEL_AVATAR_Y, 1438)
        self.assertEqual(shorts_service.SHORTS_CHANNEL_AVATAR_X, 318)
        self.assertEqual(shorts_service.SHORTS_CHANNEL_TEXT_X, 426)

    def test_japanese_shorts_do_not_fallback_to_english_text(self):
        script = {
            "title": "EP.02 スサノオはなぜ英雄であり問題児として残ったのか",
            "cuts": [{"cut_number": 1, "narration": "その答えは、嵐の神が持つ二つの顔にあります。"}],
        }

        language = shorts_service._detect_language(script)
        labels = shorts_service._shorts_labels(language)
        title = shorts_service._short_title(script, {"title": "Watch what happens"}, labels)

        self.assertEqual(language, "ja")
        self.assertNotIn("Watch what happens", title)

    def test_english_shorts_fallback_uses_current_ch4_brand(self):
        labels = shorts_service._shorts_labels("en")

        self.assertEqual(labels["fallback_channel"], "Empire Errors")
        self.assertIn(
            "8mFhhpKQW1HpFEPyq0qziMmY26fDaaNTsUayMxnKWf65WuPzR_NQKB_pIb1ULR4lOqwbh_0",
            shorts_service._default_channel_avatar_url("Empire Errors", "en") or "",
        )

    def test_hindi_shorts_fallback_is_not_bound_to_ch4(self):
        self.assertNotEqual(shorts_service._shorts_labels("hi")["fallback_channel"], "CH4")

    def test_japanese_shorts_split_long_text_without_generic_filler(self):
        line1, line2 = shorts_service._split_headline(
            "父イザナギはその姿に耐えられずスサノオを追放しました",
            width=20,
            fallback_1="この瞬間",
            fallback_2="",
        )

        self.assertTrue(line1)
        self.assertTrue(line2)
        self.assertNotIn("Watch what happens", line2)

    def test_shorts_title_allows_three_render_lines(self):
        title = shorts_service._short_title(
            {"title": "테스트"},
            {"title": "이 결정적 선택은 왜 왕국의 운명을 완전히 바꿨나"},
            shorts_service._shorts_labels("ko"),
        )

        lines = title.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(lines))

    def test_annotate_script_shorts_keeps_four_fifteen_cut_groups(self):
        script = {
            "cuts": [
                {
                    "cut_number": i,
                    "narration": f"Cut {i}",
                    "shorts_candidate": True,
                    "shorts_group": ((i - 1) // shorts_service.SHORTS_CUT_COUNT) + 1,
                    "shorts_score": i % 10,
                }
                for i in range(1, shorts_service.SHORTS_TOTAL_CANDIDATE_CUT_COUNT + 8)
            ]
        }

        annotated = shorts_service.annotate_script_shorts(script)
        marked = [c for c in annotated["cuts"] if c.get("shorts_candidate") is True]

        self.assertEqual(len(marked), shorts_service.SHORTS_TOTAL_CANDIDATE_CUT_COUNT)
        for group in range(1, shorts_service.SHORTS_SEGMENT_COUNT + 1):
            self.assertEqual(
                sum(1 for c in marked if c.get("shorts_group") == group),
                shorts_service.SHORTS_CUT_COUNT,
            )

    def test_annotate_script_shorts_accepts_three_fifteen_cut_groups(self):
        script = {
            "cuts": [
                {
                    "cut_number": i,
                    "narration": f"Cut {i}",
                    "shorts_candidate": i <= shorts_service.SHORTS_MIN_CANDIDATE_CUT_COUNT,
                    "shorts_group": ((i - 1) // shorts_service.SHORTS_CUT_COUNT) + 1
                    if i <= shorts_service.SHORTS_MIN_CANDIDATE_CUT_COUNT else 0,
                    "shorts_score": i % 10,
                }
                for i in range(1, 151)
            ]
        }

        annotated = shorts_service.annotate_script_shorts(script)
        marked = [c for c in annotated["cuts"] if c.get("shorts_candidate") is True]

        self.assertEqual(len(marked), shorts_service.SHORTS_MIN_CANDIDATE_CUT_COUNT)
        for group in range(1, shorts_service.SHORTS_MIN_SEGMENT_COUNT + 1):
            self.assertEqual(
                sum(1 for c in marked if c.get("shorts_group") == group),
                shorts_service.SHORTS_CUT_COUNT,
            )
        self.assertEqual(sum(1 for c in marked if c.get("shorts_group") == 4), 0)

    def test_annotate_script_shorts_preserves_explicit_four_ten_cut_groups(self):
        script = {
            "cuts": [
                {
                    "cut_number": i,
                    "narration": f"Cut {i}",
                    "shorts_candidate": i <= 40,
                    "shorts_group": ((i - 1) // 10) + 1 if i <= 40 else 0,
                }
                for i in range(1, 151)
            ]
        }

        annotated = shorts_service.annotate_script_shorts(script)
        marked = [c for c in annotated["cuts"] if c.get("shorts_candidate") is True]
        segments = shorts_service.select_shorts_segments(annotated)

        self.assertEqual(len(marked), 40)
        self.assertEqual([len(seg.get("cut_numbers") or []) for seg in segments], [10, 10, 10, 10])
        for group in range(1, shorts_service.SHORTS_SEGMENT_COUNT + 1):
            self.assertEqual(
                sum(1 for c in marked if c.get("shorts_group") == group),
                10,
            )

    def test_shorts_renderer_does_not_slice_segments_to_one(self):
        source = (Path(__file__).resolve().parent.parent / "app" / "services" / "shorts_service.py").read_text(
            encoding="utf-8-sig",
        )

        self.assertNotIn("segments[:1]", source)
        self.assertIn("segments[:SHORTS_SEGMENT_COUNT]", source)


class YouTubeScopeStabilityTests(unittest.TestCase):
    def test_youtube_token_scope_check_requires_force_ssl(self):
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "token.json"
            token_path.write_text(
                json.dumps({
                    "token": "x",
                    "refresh_token": "y",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "client_id": "cid",
                    "client_secret": "sec",
                    "scopes": [
                        "https://www.googleapis.com/auth/youtube.upload",
                        "https://www.googleapis.com/auth/youtube",
                    ],
                }),
                encoding="utf-8",
            )

            self.assertFalse(youtube_service._token_file_has_required_scopes(token_path))

    def test_youtube_insufficient_scope_error_is_actionable(self):
        text = youtube_service._friendly_youtube_error(
            "댓글 조회 실패",
            Exception("Request had insufficient authentication scopes."),
        )

        self.assertIn("OAuth 권한이 부족", text)
        self.assertIn("youtube.force-ssl", text)
        self.assertIn("insufficientAuthenticationScopes", text)

    def test_youtube_disabled_comments_error_is_readable(self):
        text = youtube_service._friendly_youtube_error(
            "댓글 조회 실패",
            Exception("The video identified by the videoId parameter has disabled comments."),
        )

        self.assertIn("댓글이 비활성화", text)
        self.assertIn("commentsDisabled", text)

    def test_youtube_upload_insert_retry_default_does_not_hide_429_retries(self):
        self.assertEqual(youtube_service.YOUTUBE_UPLOAD_INSERT_RETRIES, 0)


class UploadAndAudioMixStabilityTests(unittest.TestCase):
    def test_shorts_upload_title_has_no_numeric_hashtag(self):
        title = shorts_upload_title("숨겨진 진실 #1 #Shorts", index=1, total=4)

        self.assertEqual(title, "숨겨진 진실 #Shorts")
        self.assertNotRegex(title, r"#\d+\b")
        self.assertNotRegex(title, r"\bPart\s+\d+\b")

    def test_project_upload_completion_merges_completed_task_steps(self):
        states = svc._completed_project_step_states(
            {"story": "completed", "3": "running", "4": "completed", "7": "running"},
            {"2": "completed", "3": "completed", "5": "completed", "6": "completed", "7": "completed"},
        )

        self.assertEqual(states["story"], "completed")
        for key in ("2", "3", "4", "5", "6", "7"):
            self.assertEqual(states[key], "completed")

    def test_global_render_audio_mix_defaults(self):
        self.assertAlmostEqual(app_config.NARRATION_VOLUME_GAIN, 1.8)
        self.assertAlmostEqual(app_config.BGM_VOLUME_MULTIPLIER, 0.7)
        self.assertAlmostEqual(subtitle_router._effective_bgm_volume(0.21), 0.147)

    def test_youtube_upload_quota_classifier_is_precise(self):
        self.assertTrue(svc._is_youtube_upload_quota_error(Exception(
            "Quota exceeded for quota metric 'Video Uploads' and limit 'Video Uploads per day'"
        )))
        self.assertTrue(svc._is_youtube_upload_quota_error(Exception("reason: uploadLimitExceeded")))
        self.assertFalse(svc._is_youtube_upload_quota_error(Exception("reason: rateLimitExceeded")))
        self.assertFalse(svc._is_youtube_upload_quota_error(Exception("reason: quotaExceeded")))

    def test_existing_main_upload_keeps_step7_pending_when_required_shorts_missing(self):
        original_load_project = svc._load_project
        original_shorts_completion = svc._shorts_upload_completion
        try:
            svc._load_project = lambda project_id: SimpleNamespace(
                id=project_id,
                youtube_url="https://youtube.com/watch?v=abc123def",
                config={"shorts_enabled": True},
            )
            svc._shorts_upload_completion = lambda project_id, config=None: {
                "enabled": True,
                "required": 4,
                "file_count": 4,
                "uploaded_count": 0,
                "complete": False,
            }
            task = {
                "task_id": "t1",
                "status": "uploading",
                "step_states": {"6": "completed", "7": "pending"},
                "logs": [],
            }

            completed = svc._complete_task_from_existing_upload(
                task,
                "project1",
                {"shorts_enabled": True},
            )
        finally:
            svc._load_project = original_load_project
            svc._shorts_upload_completion = original_shorts_completion

        self.assertFalse(completed)
        self.assertEqual(task["youtube_url"], "https://youtube.com/watch?v=abc123def")
        self.assertEqual(task["step_states"]["7"], "pending")
        self.assertEqual(task["status"], "uploading")
        self.assertTrue(any("쇼츠 업로드 미완료" in log["msg"] for log in task["logs"]))

class ChannelOpsCommentLoadingTests(unittest.TestCase):
    def test_comment_translation_targets_non_korean_text(self):
        self.assertFalse(channel_ops_router._needs_korean_translation("좋은 영상입니다."))
        self.assertFalse(channel_ops_router._needs_korean_translation("123 !!! 😊"))
        self.assertTrue(channel_ops_router._needs_korean_translation("Great video, thank you."))
        self.assertTrue(channel_ops_router._needs_korean_translation("日本語の使い方が意味わかんねぇ"))
        self.assertTrue(channel_ops_router._needs_korean_translation("यह बहुत अच्छा है"))

    def test_comment_translation_assigns_korean_text(self):
        captured = {}

        class FakeCompletions:
            async def create(self, **kwargs):
                payload = json.loads(kwargs["messages"][1]["content"])
                captured["texts"] = [item["text"] for item in payload["comments"]]
                return SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=json.dumps({"translations": ["일본어 사용법이 이해가 잘 안 되네요."]}, ensure_ascii=False)
                            )
                        )
                    ],
                    usage=None,
                )

        class FakeChat:
            def __init__(self):
                self.completions = FakeCompletions()

        class FakeOpenAI:
            def __init__(self, api_key=None):
                self.chat = FakeChat()

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        comments = [
            {"text": "日本語の使い方が意味わかんねぇ"},
            {"text": "한국어 댓글입니다."},
        ]
        original_openai = channel_ops_router.AsyncOpenAI
        original_key = app_config.OPENAI_API_KEY
        try:
            channel_ops_router.AsyncOpenAI = FakeOpenAI
            app_config.OPENAI_API_KEY = "test-key"
            asyncio.run(channel_ops_router._translate_loaded_comments(comments))
        finally:
            channel_ops_router.AsyncOpenAI = original_openai
            app_config.OPENAI_API_KEY = original_key

        self.assertEqual(captured["texts"], ["日本語の使い方が意味わかんねぇ"])
        self.assertEqual(comments[0]["translated_text"], "일본어 사용법이 이해가 잘 안 되네요.")
        self.assertIsNone(comments[0]["translation_error"])
        self.assertIsNone(comments[1]["translated_text"])
        self.assertIsNone(comments[1]["translation_error"])

    def test_comment_reply_profile_is_stable_and_varied(self):
        first = channel_ops_router.CommentReplyTarget(
            parent_comment_id="comment-a",
            video_id="video-a",
            comment_text="집현전이란 기관을 연구해봤어?",
        )
        second = channel_ops_router.CommentReplyTarget(
            parent_comment_id="comment-b",
            video_id="video-b",
            comment_text="훌륭한 사람입니다 세종대왕 님 감사합니다",
        )

        self.assertEqual(
            channel_ops_router._reply_profile(first),
            channel_ops_router._reply_profile(first),
        )
        self.assertNotEqual(
            channel_ops_router._reply_profile(first)["comment_type"],
            channel_ops_router._reply_profile(second)["comment_type"],
        )

    def test_comment_loader_filters_videos_without_comments(self):
        calls = []

        class FakeUploader:
            def __init__(self, channel_id=None):
                self.channel_id = channel_id

            def list_my_videos(self, max_results=50, page_token=None, include_details=True):
                return {
                    "items": [
                        {"video_id": "no-comment", "title": "No comment", "comment_count": 0},
                        {"video_id": "has-comment-1", "title": "Has comment 1", "comment_count": 2},
                        {"video_id": "has-comment-2", "title": "Has comment 2", "comment_count": 1},
                    ],
                    "next_page_token": None,
                }

            def list_comment_threads(self, video_id, max_results=50, page_token=None, order="time"):
                calls.append(video_id)
                return {
                    "items": [
                        {
                            "thread_id": f"thread-{video_id}",
                            "top_comment_id": f"comment-{video_id}",
                            "author": "viewer",
                            "author_channel_id": "viewer-channel",
                            "text": f"text {video_id}",
                            "like_count": 0,
                            "published_at": "2026-05-19T00:00:00Z",
                            "updated_at": "2026-05-19T00:00:00Z",
                            "total_reply_count": 0,
                            "can_reply": True,
                            "replies": [],
                        }
                    ],
                    "next_page_token": None,
                    "total_results": 1,
                }

        original_uploader = channel_ops_router.YouTubeUploader
        original_own_channel = channel_ops_router._get_own_channel_id
        try:
            channel_ops_router.YouTubeUploader = FakeUploader
            channel_ops_router._get_own_channel_id = lambda uploader: "owner-channel"

            result = channel_ops_router._list_comments_sync(1, 10, 10)
        finally:
            channel_ops_router.YouTubeUploader = original_uploader
            channel_ops_router._get_own_channel_id = original_own_channel

        self.assertEqual(calls, ["has-comment-1", "has-comment-2"])
        self.assertEqual(result["videos_scanned"], 3)
        self.assertEqual(result["videos_with_comments"], 2)
        self.assertEqual(result["videos_skipped_no_comments"], 1)
        self.assertEqual(len(result["comments"]), 2)

    def test_comment_loader_suppresses_disabled_comment_warnings(self):
        class FakeUploader:
            def __init__(self, channel_id=None):
                self.channel_id = channel_id

            def list_my_videos(self, max_results=50, page_token=None, include_details=True):
                return {
                    "items": [
                        {"video_id": "disabled", "title": "Disabled", "comment_count": 1},
                    ],
                    "next_page_token": None,
                }

            def list_comment_threads(self, video_id, max_results=50, page_token=None, order="time"):
                raise youtube_service.YouTubeUploadError(
                    "댓글 조회 실패: The video identified by the videoId parameter has disabled comments."
                )

        original_uploader = channel_ops_router.YouTubeUploader
        original_own_channel = channel_ops_router._get_own_channel_id
        try:
            channel_ops_router.YouTubeUploader = FakeUploader
            channel_ops_router._get_own_channel_id = lambda uploader: "owner-channel"

            result = channel_ops_router._list_comments_sync(1, 10, 10)
        finally:
            channel_ops_router.YouTubeUploader = original_uploader
            channel_ops_router._get_own_channel_id = original_own_channel

        self.assertEqual(result["comments"], [])
        self.assertEqual(result["errors"], [])

    def test_comment_loader_uses_channel_comment_threads_when_available(self):
        class FakeUploader:
            def __init__(self, channel_id=None):
                self.channel_id = channel_id

            def list_channel_comment_threads(
                self,
                channel_youtube_id,
                max_results=50,
                page_token=None,
                order="time",
            ):
                return {
                    "items": [
                        {
                            "thread_id": "thread-a",
                            "video_id": "video-a",
                            "top_comment_id": "comment-a",
                            "author": "viewer",
                            "author_channel_id": "viewer-channel",
                            "text": "Studio comment",
                            "like_count": 1,
                            "published_at": "2026-05-21T00:00:00Z",
                            "updated_at": "2026-05-21T00:00:00Z",
                            "total_reply_count": 0,
                            "can_reply": True,
                            "replies": [],
                        }
                    ],
                    "next_page_token": None,
                    "total_results": 1,
                }

            def get_videos_details(self, video_ids):
                return {
                    "video-a": {
                        "title": "Video title",
                        "thumbnail": "https://example.test/thumb.jpg",
                    }
                }

        original_uploader = channel_ops_router.YouTubeUploader
        original_own_channel = channel_ops_router._get_own_channel_id
        try:
            channel_ops_router.YouTubeUploader = FakeUploader
            channel_ops_router._get_own_channel_id = lambda uploader: "owner-channel"

            result = channel_ops_router._list_comments_sync(3, 10, 10)
        finally:
            channel_ops_router.YouTubeUploader = original_uploader
            channel_ops_router._get_own_channel_id = original_own_channel

        self.assertEqual(result["scan_mode"], "channel_comments")
        self.assertEqual(result["videos_scanned"], 0)
        self.assertEqual(result["videos_with_comments"], 1)
        self.assertEqual(result["comments"][0]["text"], "Studio comment")
        self.assertEqual(result["comments"][0]["video_title"], "Video title")


class TTSPronunciationStabilityTests(unittest.TestCase):
    def test_japanese_tts_uses_reading_only_for_spoken_input(self):
        original = "古事記と日本書紀では、卑弥呼と倭国、藤原不比等の扱いが変わります。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertEqual(original, "古事記と日本書紀では、卑弥呼と倭国、藤原不比等の扱いが変わります。")
        self.assertIn("こじき", spoken)
        self.assertIn("にほんしょき", spoken)
        self.assertIn("ひみこ", spoken)
        self.assertIn("わこく", spoken)
        self.assertIn("ふじわらのふひと", spoken)
        self.assertNotIn("古事記", spoken)
        self.assertNotIn("日本書紀", spoken)
        self.assertNotRegex(spoken, r"[\u3400-\u9fff]")

    def test_japanese_tts_expanded_history_readings(self):
        original = "聖徳太子、大化の改新、壬申の乱、関ヶ原の戦い、明治維新を扱います。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("しょうとくたいし", spoken)
        self.assertIn("たいかのかいしん", spoken)
        self.assertIn("じんしんのらん", spoken)
        self.assertIn("せきがはらのたたかい", spoken)
        self.assertIn("めいじいしん", spoken)

    def test_japanese_tts_uses_okimi_in_yamato_context(self):
        original = "ヤマト王権では、大王の権威が豪族との関係で強まりました。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("おおきみ", spoken)
        self.assertNotIn("大王", spoken)

    def test_japanese_tts_keeps_foreign_daio_context(self):
        original = "アレクサンドロス大王の遠征とは別の話です。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("だいおう", spoken)
        self.assertNotIn("おおきみ", spoken)
        self.assertNotIn("大王", spoken)

    def test_japanese_tts_comment_reported_ancient_terms(self):
        original = "山背大兄王、蘇我入鹿、白村江の戦い、纒向遺跡を扱います。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("やましろのおおえのおう", spoken)
        self.assertIn("そがのいるか", spoken)
        self.assertIn("はくすきのえのたたかい", spoken)
        self.assertIn("まきむくいせき", spoken)

    def test_japanese_tts_manyoshu_reported_terms(self):
        original = "東歌、防人歌、万葉仮名、古今和歌集を扱います。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("あずまうた", spoken)
        self.assertIn("さきもりうた", spoken)
        self.assertIn("まんようがな", spoken)
        self.assertIn("こきんわかしゅう", spoken)

    def test_japanese_tts_converts_leaked_korean_history_terms(self):
        original = "신라와 백제はヤマト王権と関係します。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("しらぎとくだらは", spoken)
        self.assertIn("やまとおうけん", spoken)
        self.assertNotRegex(spoken, r"[\uac00-\ud7a3]")

    def test_japanese_tts_uses_kana_safety_net_for_remaining_kanji(self):
        original = "万葉集は、八世紀後半に形を整えた歌集です。歌は四千五百首前後です。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("まんようしゅう", spoken)
        self.assertIn("はっせいきこうはん", spoken)
        self.assertIn("よんせんごひゃくしゅぜんご", spoken)
        self.assertNotRegex(spoken, r"[\u3400-\u9fff]")

    def test_japanese_tts_handles_manyoshu_volume_counter(self):
        original = "万葉集は、全二十巻の大きなまとまりです。"

        spoken = prepare_spoken_narration_for_tts(original, "ja")

        self.assertIn("ぜんにじゅっかん", spoken)
        self.assertNotIn("じじゅう", spoken)
        self.assertNotRegex(spoken, r"[\u3400-\u9fff]")

    def test_japanese_reading_does_not_apply_to_korean_tts(self):
        text = "古事記와 日本書紀"

        spoken = prepare_spoken_narration_for_tts(text, "ko")

        self.assertIn("古事記", spoken)
        self.assertIn("日本書紀", spoken)
        self.assertNotIn("こじき", spoken)


class SubtitleStyleStabilityTests(unittest.TestCase):
    def test_default_subtitle_size_is_ten_points_larger(self):
        self.assertEqual(subtitle_service.DEFAULT_SUBTITLE_STYLE["size"], 68)
        self.assertEqual(subtitle_service.CUT_SUBTITLE_MARKER_VERSION, 4)

    def test_saved_subtitle_size_is_bumped_by_ten_on_render(self):
        normalized = subtitle_service.normalize_subtitle_style({"preset": "current", "size": 58})

        self.assertEqual(normalized["size"], 68)

    def test_non_legacy_saved_subtitle_size_is_not_bumped_again(self):
        normalized = subtitle_service.normalize_subtitle_style({"preset": "current", "size": 68})

        self.assertEqual(normalized["size"], 68)

    def test_subtitle_wrap_width_is_tighter_for_larger_font(self):
        wrapped = subtitle_service._wrap_two_lines(
            "이 문장은 커진 자막 크기에 맞춰 적절하게 두 줄로 나뉘어야 합니다.",
            "16:9",
        )

        self.assertIn("\\N", wrapped)

    def test_subtitle_render_uses_body_only_source_for_shorts(self):
        router_source = (Path(__file__).resolve().parent.parent / "app" / "routers" / "subtitle.py").read_text(
            encoding="utf-8-sig",
        )

        self.assertIn("shorts_body_no_interludes.mp4", router_source)
        self.assertIn("without opening/intermission/ending", router_source)


class HistoricalImagePromptStabilityTests(unittest.TestCase):
    def test_longtube_local_v1_applies_master_prompt(self):
        cut_prompt = "Year/period: 1592; Exact place: fortress gate; Scene: guards run"
        wrapped = apply_longtube_local_v1_master_prompt(
            cut_prompt
        )

        self.assertTrue(wrapped.startswith("CUT IMAGE PROMPT — SOURCE OF TRUTH\n" + cut_prompt))
        self.assertIn("[MASTER PROMPT — DOCUMENTARY ILLUSTRATION STYLE]", wrapped)
        self.assertIn("longtubestyle", wrapped)
        self.assertIn("CUT PROMPT LOCK — ABSOLUTE PRIORITY", wrapped)
        self.assertNotIn("{CUT_IMAGE_PROMPT}", wrapped)
        for forbidden_positive in (
            "Do not",
            "ABSOLUTELY NO",
            "temple",
            "castle",
            "ocean",
            "fire",
            "armor",
            "battle",
            "lightning",
            "no exterior",
        ):
            self.assertNotIn(forbidden_positive, wrapped)

    def test_longtube_local_v1_does_not_add_scene_words_to_negative_prompt(self):
        cut_prompt = (
            "Year/period: 2020s; Exact place: Japanese home kitchen; "
            "Scene: white ceramic bowl of miso soup on a breakfast table"
        )
        negative = build_longtube_local_v1_negative_prompt("blurry", cut_prompt)

        self.assertIn("blurry", negative)
        for scene_word in ("temple", "castle", "ocean", "fire", "boat", "mountain", "lightning", "storm"):
            self.assertNotIn(scene_word, negative)

    def test_longtube_local_v1_keeps_scene_terms_out_of_negative_prompt(self):
        cut_prompt = "Year/period: c. 1300; Exact place: temple kitchen; Scene: pot over open fire"
        negative = build_longtube_local_v1_negative_prompt("", cut_prompt)

        self.assertNotIn("temple", negative)
        self.assertNotIn("fire", negative)
        self.assertNotIn("castle", negative)
        self.assertNotIn("ocean", negative)

    def test_longtube_local_v1_strips_common_positive_negative_directives(self):
        raw = (
            "Year/period: 2020s; Exact place: home kitchen; Scene: miso soup, no text "
            "|| HARD HISTORICAL MATERIAL CULTURE LOCK - match the exact time period, season "
            "|| ★ HARD CONSTRAINT — ABSOLUTELY NO MAPS"
        )
        cleaned = _strip_local_v1_positive_only_prompt(raw)

        self.assertIn("miso soup", cleaned)
        self.assertNotIn("HARD HISTORICAL", cleaned)
        self.assertNotIn("ABSOLUTELY NO", cleaned)
        self.assertNotIn("no text", cleaned.lower())
        self.assertNotIn("no exterior", cleaned.lower())
        negative = build_longtube_local_v1_negative_prompt("", cleaned)
        self.assertNotIn("ocean", negative)

    def test_premodern_interior_guard_blocks_modern_desk_lamps(self):
        guard_text = (
            PREMODERN_INTERIOR_PROP_COMFYUI_FRONT_PROMPT
            + " "
            + PREMODERN_INTERIOR_PROP_COMFYUI_EXTRA_NEGATIVE
        )

        self.assertIn("desk lamp", guard_text)
        self.assertIn("task lamp", guard_text)
        self.assertIn("anglepoise lamp", guard_text)
        self.assertIn("electric table lamp", guard_text)
        self.assertIn("power cord", guard_text)

    def test_internal_text_mark_detector_targets_document_prompts(self):
        self.assertTrue(_should_check_internal_text_after_generation(
            "Scene: Officials stack blank land papers beside rice tallies."
        ))
        self.assertFalse(_should_check_internal_text_after_generation(
            "Scene: armored commander stands before a crowded castle courtyard."
        ))

    def test_internal_text_mark_detector_targets_japanese_architecture_prompts(self):
        self.assertTrue(_should_check_internal_text_after_generation(
            "Year/period: 1598; Exact place: Hizen Nagoya Castle command room; "
            "Culture scope: Late Sengoku Japanese administration; "
            "Scene: Toyotomi retainers sit beneath a blank wall plaque and folding screen."
        ))
        self.assertFalse(_should_check_internal_text_after_generation(
            "Year/period: 2020s; Exact place: modern Japanese home kitchen; "
            "Scene: a ceramic bowl of miso soup on a breakfast table."
        ))

    def test_internal_text_mark_detector_finds_dense_glyph_rows(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            text_path = Path(tmp) / "internal_text.png"
            blank_path = Path(tmp) / "blank_panel.png"
            landscape_path = Path(tmp) / "landscape_texture.png"
            road_splash_path = Path(tmp) / "edge_clipped_road_splash.png"
            im = Image.new("RGB", (1280, 720), (82, 82, 76))
            draw = ImageDraw.Draw(im)
            draw.rectangle((250, 150, 1030, 570), fill=(222, 210, 178))
            for row in range(12):
                y = 190 + row * 26
                for col in range(24):
                    x = 305 + col * 27
                    draw.line((x, y, x + 8, y + 12), fill=(28, 24, 20), width=2)
                    draw.line((x + 9, y + 2, x + 15, y + 2), fill=(28, 24, 20), width=2)
            im.save(text_path)

            blank = Image.new("RGB", (1280, 720), (82, 82, 76))
            blank_draw = ImageDraw.Draw(blank)
            blank_draw.rectangle((250, 150, 1030, 570), fill=(222, 210, 178))
            for row in range(12):
                y = 190 + row * 28
                blank_draw.line((280, y, 1000, y + 4), fill=(170, 154, 120), width=2)
            blank.save(blank_path)

            bamboo_path = Path(tmp) / "bamboo_hatching.png"
            bamboo = Image.new("RGB", (1280, 720), (138, 110, 72))
            bamboo_draw = ImageDraw.Draw(bamboo)
            bamboo_draw.rectangle((130, 145, 560, 490), fill=(196, 150, 86))
            bamboo_draw.rectangle((720, 145, 1150, 490), fill=(196, 150, 86))
            for x in range(150, 550, 18):
                bamboo_draw.line((x, 170, x - 90, 475), fill=(72, 54, 38), width=2)
            for x in range(740, 1140, 18):
                bamboo_draw.line((x, 170, x - 90, 475), fill=(72, 54, 38), width=2)
            for x in range(0, 1280, 24):
                y = 70 + (x * 17) % 570
                bamboo_draw.ellipse((x, y, x + 5, y + 4), fill=(40, 32, 25))
            bamboo.save(bamboo_path)

            landscape = Image.new("RGB", (1280, 720), (218, 215, 188))
            landscape_draw = ImageDraw.Draw(landscape)
            landscape_draw.rectangle((0, 230, 1280, 460), fill=(214, 210, 176))
            landscape_draw.line((0, 245, 1280, 245), fill=(64, 58, 50), width=2)
            for x in range(430, 820, 18):
                y = 250 + (x * 7) % 48
                landscape_draw.line((x, y, x + 12, y), fill=(44, 40, 34), width=2)
                landscape_draw.line((x + 4, y - 16, x + 6, y - 4), fill=(58, 54, 46), width=1)
            for x in range(400, 850, 35):
                y = 300 + (x * 5) % 40
                landscape_draw.ellipse((x, y, x + 10, y + 5), fill=(62, 57, 50))
            landscape.save(landscape_path)

            post_station_texture_path = Path(tmp) / "post_station_line_texture.png"
            post_station_texture = Image.new("RGB", (1280, 720), (226, 224, 206))
            post_station_draw = ImageDraw.Draw(post_station_texture)
            mark_count = 0
            for row in range(6):
                for col in range(5):
                    x = 980 + col * 36 + (row % 2) * 4
                    y = 190 + row * 18
                    if mark_count < 19:
                        post_station_draw.line((x, y, x + 18, y + 2), fill=(45, 42, 36), width=3)
                    else:
                        post_station_draw.line((x, y, x + 7, y + 9), fill=(45, 42, 36), width=3)
                    mark_count += 1
            post_station_texture.save(post_station_texture_path)

            road_splash = Image.new("RGB", (640, 360), (214, 213, 198))
            road_splash_draw = ImageDraw.Draw(road_splash)
            road_splash_draw.rectangle((350, 170, 470, 250), fill=(226, 225, 211))
            for x in (374, 382, 390, 406, 438):
                road_splash_draw.line((x, 180, x + 8, 181), fill=(45, 42, 36), width=2)
            for idx, x in enumerate(range(378, 454, 9)):
                y = 190 + (idx * 7) % 46
                road_splash_draw.ellipse((x, y, x + 3, y + 2), fill=(42, 39, 34))
                road_splash_draw.line((x + 5, y + 4, x + 12, y + 5), fill=(48, 44, 38), width=2)
            road_splash_draw.line((374, 235, 452, 247), fill=(92, 88, 78), width=2)
            road_splash.save(road_splash_path)

            self.assertTrue(_image_has_internal_text_like_marks(text_path))
            self.assertFalse(_image_has_internal_text_like_marks(blank_path))
            self.assertFalse(_image_has_internal_text_like_marks(bamboo_path))
            self.assertFalse(_image_has_internal_text_like_marks(landscape_path))
            self.assertFalse(_image_has_internal_text_like_marks(post_station_texture_path))
            self.assertFalse(_image_has_internal_text_like_marks(road_splash_path))

    def test_split_panel_detector_catches_top_inset_panel(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            bad_path = Path(tmp) / "split_panel.png"
            good_path = Path(tmp) / "tabletop.png"
            plank_path = Path(tmp) / "tabletop_dark_plank.png"

            bad = Image.new("RGB", (1280, 720), (220, 216, 190))
            bad_draw = ImageDraw.Draw(bad)
            bad_draw.rectangle((0, 0, 640, 250), fill=(190, 176, 138))
            bad_draw.line((0, 250, 640, 250), fill=(10, 10, 10), width=5)
            bad_draw.line((640, 0, 640, 250), fill=(10, 10, 10), width=5)
            bad_draw.rectangle((0, 252, 1279, 719), fill=(150, 150, 136))
            bad.save(bad_path)

            good = Image.new("RGB", (1280, 720), (196, 174, 132))
            good_draw = ImageDraw.Draw(good)
            for y in range(80, 700, 110):
                good_draw.line((0, y, 1279, y), fill=(86, 70, 48), width=2)
            for x in range(120, 1260, 180):
                good_draw.line((x, 0, x, 719), fill=(110, 92, 64), width=1)
            good.save(good_path)

            plank = Image.new("RGB", (1280, 720), (156, 126, 86))
            plank_draw = ImageDraw.Draw(plank)
            plank_draw.line((0, 250, 1279, 250), fill=(10, 10, 10), width=5)
            plank_draw.line((640, 20, 640, 250), fill=(10, 10, 10), width=5)
            for y in range(40, 700, 95):
                plank_draw.line((0, y, 1279, y), fill=(60, 45, 30), width=1)
            plank.save(plank_path)

            self.assertTrue(_image_has_split_panel_divider(bad_path))
            self.assertFalse(_image_has_split_panel_divider(good_path))
            self.assertFalse(_image_has_split_panel_divider(plank_path))

    def test_japanese_document_retry_uses_tabletop_only(self):
        document_source = (
            "Year/period: 17th century; Exact place: Edo Castle night office; "
            "Culture scope: Edo period Japan; Main subject: exhausted bakufu clerks; "
            "Scene: Clerks bend over blank papers late at night beside stacked wooden boxes."
        )
        gate_source = (
            "Year/period: 17th century; Exact place: Edo Castle main gate; "
            "Culture scope: Edo period Japan; Main subject: guarded gate; "
            "Scene: Officials stand under a blank wall plaque near the gate."
        )
        retry = _flux2_klein_japanese_textless_retry_sentence()

        self.assertTrue(_should_use_japanese_document_table_retry(document_source))
        self.assertFalse(_should_use_japanese_document_table_retry(gate_source))
        self.assertIn("Japanese object-only edge-to-edge tabletop macro retry composition", retry)
        self.assertNotIn("open air", retry)
        self.assertNotIn("plain posts", retry)
        self.assertNotIn("smoke", retry)

    def test_flux2_klein_japanese_contract_crops_out_sign_zones(self):
        source = (
            "Year/period: 1605; Exact place: Edo Castle formal chamber; "
            "Culture scope: Early Edo Japanese administration; "
            "Main subject: daimyo audience; "
            "Scene: retainers kneel in a tense audience hall."
        )
        positive = _flux2_klein_md_positive_contract(
            "Scene subject: daimyo audience. Visible action: retainers kneel in a tense audience hall.",
            source,
        )
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese open-veranda plain composition", positive)
        self.assertIn("open-sided veranda", positive)
        self.assertIn("continuous natural background material", positive)
        self.assertIn("shopfront sign", negative)
        self.assertIn("overdoor character board", negative)

    def test_flux2_klein_japanese_contract_replaces_open_documents(self):
        source = (
            "Year/period: 1603; Exact place: Edo administrative office; "
            "Culture scope: Early Edo Japanese administration; "
            "Main subject: forming shogunate office; "
            "Scene: Officials sort blank land papers and open documents on a low desk."
        )
        positive = _flux2_klein_md_positive_contract(
            "Visible action: Officials sort blank land papers and open documents on a low desk.",
            source,
        )

        self.assertIn("sealed cloth-wrapped packet bundles", positive)
        self.assertNotIn("blank land papers", positive)
        self.assertNotIn("open documents", positive)
        self.assertNotIn("open landscape", positive)
        self.assertNotIn("rice fields", positive)

    def test_flux2_klein_japanese_checkpoint_cart_uses_open_road_contract(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Year/period: 17th century; Edo period, mature bakuhan order; "
            "Exact place: domain storehouse and official checkpoint; "
            "Scene evidence: Storehouse and checkpoint show stable but monitored local rule.; "
            "Main subject: checkpoint officer stopping a domain cart; "
            "Scene: An officer blocks a loaded cart with his staff while clerks inspect cargo ropes."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese open-checkpoint road composition", positive)
        self.assertIn("loaded wooden handcart", positive)
        self.assertIn("plain kimono and hakama", positive)
        self.assertIn("waraji or zori sandals", positive)
        self.assertIn("short fence posts", positive)
        self.assertIn("rope-tied rice bales", positive)
        self.assertIn("low roof edges", positive)
        self.assertNotIn("Japanese plain-wall composition", positive)
        self.assertNotIn("wall plaque", positive)
        self.assertNotIn("storehouse wall", positive)
        self.assertIn("checkpoint wall text", negative)
        self.assertIn("storehouse wall writing", negative)
        self.assertIn("cargo label", negative)
        self.assertIn("telephone pole", negative)
        self.assertIn("peaked cap", negative)

    def test_flux2_klein_japanese_post_station_uses_exterior_yard_contract(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Year/period: 17th century; Edo period, post station town; "
            "Exact place: busy post station on a daimyo route; "
            "Scene evidence: Post station labor supports daimyo travel.; "
            "Main subject: post station workers preparing rooms; "
            "Scene: Inn workers throw open doors and carry mats as mounted samurai shout directions."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese post-station exterior work-yard composition", positive)
        self.assertIn("roadside inn yard", positive)
        self.assertIn("plain timber door panels", positive)
        self.assertIn("uninterrupted unmarked door wood grain", positive)
        self.assertIn("plain inn facade planks", positive)
        self.assertIn("open road", positive)
        self.assertNotIn("Japanese plain-wall composition", positive)
        self.assertNotIn("wall writing", positive)
        self.assertIn("inn wall writing", negative)
        self.assertIn("door paper label", negative)
        self.assertIn("room placard", negative)
        self.assertIn("paper sheet on inn wall", negative)
        self.assertIn("white paper sheet on inn facade", negative)
        self.assertIn("eave placard", negative)

    def test_flux2_klein_japanese_finance_council_uses_coin_tray_contract(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: 17th century; Edo period, domain survival politics; "
            "Exact place: domain council room in Edo residence; "
            "Scene evidence: A council over finances shows practical survival taking priority.; "
            "Main subject: domain council under financial pressure; "
            "Scene: Retainers huddle over empty money trays, arguing with sharp hands under dim light."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese finance-council coin-tray composition", positive)
        self.assertIn("round dull loose metal coins", positive)
        self.assertIn("unmarked cloth", positive)
        self.assertIn("closed blank packet bundles", positive)
        self.assertIn("no rectangular cards", positive)
        self.assertIn("cropped tray rims", positive)
        self.assertNotIn("empty money trays", positive)
        self.assertNotIn("domain council room", positive)
        self.assertNotIn("low desks", positive)
        self.assertNotIn("document, sign, wall", positive)
        self.assertIn("paper money", negative)
        self.assertIn("accounting sheet", negative)
        self.assertIn("rectangular accounting tile", negative)
        self.assertIn("official desk paper", negative)
        self.assertIn("vertical name strip", negative)
        self.assertIn("council room wall strip", negative)

    def test_flux2_klein_japanese_outer_waiting_retinue_avoids_desk_contract(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, ritualized political order; "
            "Year/period: 17th century; Edo period, bakufu use of daimyo prestige; "
            "Exact place: Edo Castle outer waiting area; "
            "Scene evidence: Ranked display and officials show prestige used as control.; "
            "Main subject: official observing daimyo display; "
            "Scene: A bakufu official watches a lavish retinue pass, eyes narrowed with measured calculation."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("open outer-waiting retinue yard frame", positive)
        self.assertIn("passing retinue", positive)
        self.assertIn("packed earth", positive)
        self.assertNotIn("low desks", positive)
        self.assertIn("desk paper", negative)
        self.assertIn("map on desk", negative)

    def test_flux2_klein_japanese_domestic_brush_scene_avoids_wall_marks(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, peaceful daily life; "
            "Year/period: 17th century; Edo period, peaceful daily life; "
            "Exact place: townhouse room with writing tools; "
            "Scene evidence: Writing tools and domestic life show energy moving from war to daily culture.; "
            "Main subject: child reaching for a writing brush; "
            "Scene: A child reaches for a brush while a sheathed sword rests unused in the corner."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese domestic practice-rod-and-scabbard veranda composition", positive)
        self.assertIn("plain wooden practice rod", positive)
        self.assertIn("small lidded wooden tub", positive)
        self.assertIn("fully enclosed black lacquer scabbard", positive)
        self.assertIn("unbroken black scabbard lacquer", positive)
        self.assertIn("plain unmarked tied-packet cloth", positive)
        self.assertNotIn("townhouse room with writing tools", positive)
        self.assertNotIn("writing brush", positive)
        self.assertNotIn("inkstone", positive)
        self.assertIn("townhouse wall writing", negative)
        self.assertIn("sliding door calligraphy", negative)
        self.assertIn("vertical poem strip", negative)
        self.assertIn("open practice book", negative)
        self.assertIn("open notebook", negative)
        self.assertIn("brush writing sheet", negative)
        self.assertIn("writing on packet cloth", negative)
        self.assertIn("packet cloth glyphs", negative)
        self.assertIn("bare sword blade", negative)
        self.assertIn("unsheathed katana", negative)

    def test_flux2_klein_japanese_bridge_traffic_avoids_tabletop_order_false_positive(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, ritualized political order; "
            "Year/period: 18th century; Edo period, regulated urban society; "
            "Exact place: Edo bridge with officials and merchants; "
            "Scene evidence: Bridge traffic under officials shows urban life resting on order.; "
            "Main subject: officials controlling bridge traffic; "
            "Scene: Officials direct merchants across a bridge as boats unload goods below in tight rhythm."
        )
        positive = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("Japanese open-bridge traffic composition", positive)
        self.assertIn("boats unload rope-tied goods", positive)
        self.assertIn("bridge planks", positive)
        self.assertNotIn("sealed-bundle tabletop", positive)
        self.assertNotIn("stone route markers", positive)
        self.assertNotIn("document, sign, wall", positive)

    def test_flux2_klein_japanese_coastal_watch_avoids_order_paper_and_modern_uniform(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, coastal vigilance; "
            "Year/period: 19th century; Late Edo period, nineteenth century pressures; "
            "Exact place: coastal watch post and nearby domain office; "
            "Scene evidence: Coastal and domestic watchfulness show combined pressures.; "
            "Main subject: coastal guards and anxious officials; "
            "Scene: Coastal guards point toward the sea while officials clutch orders at a wooden post."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese coastal-watch lookout composition", positive)
        self.assertIn("sealed cord-tied packets", positive)
        self.assertIn("hakama and plain robes", positive)
        self.assertNotIn("sealed-bundle tabletop", positive)
        self.assertNotIn("clutch orders", positive)
        self.assertNotIn("document, sign, wall", positive)
        self.assertIn("order paper in hand", negative)
        self.assertIn("peaked cap", negative)
        self.assertIn("modern military uniform", negative)

    def test_flux2_klein_japanese_courier_packet_stays_on_highway_not_tabletop(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, urgent communications; "
            "Year/period: 19th century; Late Edo period, urgent communications; "
            "Exact place: highway outside Edo; "
            "Scene evidence: A courier running shows urgent communication during crisis.; "
            "Main subject: urgent courier on the highway; "
            "Scene: A courier sprints through mud with a sealed blank packet tied to his chest."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_courier_retry_sentence()

        self.assertTrue(_flux2_klein_is_japanese_courier_context(source))
        self.assertIn("Japanese urgent-courier highway composition", positive)
        self.assertIn("sealed blank cloth packet tied flat to his chest", positive)
        self.assertIn("muddy highway", positive)
        self.assertNotIn("sealed-bundle tabletop", positive)
        self.assertFalse(_should_use_japanese_document_table_retry(source))
        self.assertIn("Japanese urgent-courier highway retry composition", retry)
        self.assertIn("same outdoor highway", retry)
        self.assertNotIn("tabletop", retry)
        self.assertIn("object-only tabletop", negative)

    def test_flux2_klein_japanese_domain_paper_council_avoids_road_child_scene(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Material culture: kimono, hakama, kamishimo, swords, palanquins, horses, wooden castles, tatami rooms, official documents, domain gates, processions, townhouses, rice bales, road stations; "
            "Year/period: early 17th century; "
            "Exact place: tatami council room inside Edo Castle; "
            "Culture scope: Early Edo Japanese political consolidation; "
            "Main subject: officials surrounding blank domain papers; "
            "Scene: Officials lean over blank folded documents, their hands tense near swords that remain untouched."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertIn("object-only Japanese sealed domain packet council evidence at a low table", positive)
        self.assertIn("closed sword scabbards", positive)
        self.assertIn("edge-to-edge tabletop macro crop", positive)
        self.assertIn("packets cropped by the image edges", positive)
        self.assertNotIn("castle-town society", positive)
        self.assertNotIn("sleeve-covered adult hands", positive)
        self.assertNotIn("rice-field road", positive)
        self.assertNotIn("workers", positive)
        self.assertNotIn("travelers", positive)
        self.assertNotIn("child", positive)
        self.assertNotIn("open landscape", positive)
        self.assertIn("child", negative)
        self.assertIn("rice-field road", negative)
        self.assertIn("open document", negative)

    def test_flux2_klein_japanese_two_group_document_table_uses_single_surface(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Year/period: early 17th century; Early Edo period, bakuhan system; "
            "Exact place: administrative room connecting Edo and domain offices; "
            "Scene evidence: Separate officials show bakufu and domains sharing rule.; "
            "Main subject: bakufu and domain officials at one table; "
            "Scene: Two groups of samurai push blank documents toward each other across a tatami table."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertIn("one continuous low table surface spans left to right", positive)
        self.assertIn("plain undyed unmarked packet cloth", positive)
        self.assertIn("plain undyed unmarked tied packet cloth", positive)
        self.assertIn("packets cropped by the image edges", positive)
        self.assertIn("one camera viewpoint", positive)
        self.assertNotIn("plain side posts", positive)
        self.assertNotIn("tense faces", positive)
        self.assertNotIn("sleeve-covered adult hands", positive)
        self.assertIn("split panel", negative)
        self.assertIn("center divider", negative)
        self.assertIn("rectangular frame border", negative)
        self.assertIn("kanji", negative)
        self.assertIn("wall scroll", negative)
        self.assertIn("kanji wall panel", negative)
        self.assertIn("red stains on packet cloth", negative)
        self.assertIn("seal-like packet marks", negative)

    def test_flux2_klein_japanese_rewritten_document_bundles_stay_textless(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: early 17th century; Early Edo period, bakuhan system; "
            "Exact place: administrative room connecting Edo and domain offices; "
            "Scene evidence: Separate officials show bakufu and domains sharing rule.; "
            "Main subject: bakufu and domain officials at one table; "
            "Scene: Two groups of samurai push blank cord-tied closed cream bundles held edge-on toward each other across a tatami table."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertIn("object-only Japanese sealed domain packet council evidence", positive)
        self.assertIn("plain undyed unmarked packet cloth", positive)
        self.assertNotIn("dried blood", positive)
        self.assertNotIn("Scene subject: bakufu and domain officials", positive)
        self.assertIn("right wall writing", negative)
        self.assertIn("wooden box label", negative)

    def test_flux2_klein_japanese_castle_gate_avoids_rice_road_child_scene(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Material culture: kimono, hakama, kamishimo, swords, palanquins, horses, wooden castles, tatami rooms, official documents, domain gates, processions, townhouses, rice bales, road stations; "
            "Year/period: 1603; Early Edo period, Tokugawa bakufu foundation; "
            "Exact place: outer gate of Edo Castle; "
            "Scene evidence: Edo Castle represents the new Tokugawa political center beginning in 1603.; "
            "Main subject: Edo bakufu officials at a castle gate; "
            "Scene: Samurai officials in kamishimo hurry through a heavy wooden gate, faces controlled and alert."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese castle-gate lower composition", positive)
        self.assertIn("heavy plain timber castle gate", positive)
        self.assertIn("adult samurai officials", positive)
        self.assertIn("stone threshold", positive)
        self.assertNotIn("rice fields", positive)
        self.assertNotIn("rice-field road", positive)
        self.assertNotIn("workers", positive)
        self.assertNotIn("child", positive)
        self.assertNotIn("castle-town society", positive)
        self.assertIn("child", negative)
        self.assertIn("rice-field road", negative)
        self.assertIn("overdoor character board", negative)

    def test_flux2_klein_japanese_mansion_gate_uses_gate_contract(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Place scope: Edo, daimyo domains, castle towns, roads between domains and Edo, rural villages, coastal towns; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society, domain administration, ritualized political order; "
            "Year/period: early 17th century; Early Edo period, daimyo power under Tokugawa rule; "
            "Exact place: domain mansion gate in Edo; "
            "Scene evidence: A guarded daimyo mansion visualizes powerful allies inside the system.; "
            "Main subject: daimyo retainers at a mansion gate; "
            "Scene: Armed retainers open a tall wooden gate, their guarded faces showing pride and restraint."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese castle-gate lower composition", positive)
        self.assertIn("heavy plain timber castle gate", positive)
        self.assertIn("adult samurai officials", positive)
        self.assertNotIn("rice fields", positive)
        self.assertNotIn("child", positive)
        self.assertNotIn("castle-town society", positive)
        self.assertIn("gate signboard", negative)
        self.assertIn("overdoor character board", negative)

    def test_flux2_klein_japanese_sword_order_contract_uses_ground_evidence(self):
        source = (
            "Year/period: c. 1600-1603; "
            "Exact place: charred field near a former battlefield outside a castle town; "
            "Culture scope: Early Edo Japanese administration; "
            "Main subject: sheathed sword beside an official document; "
            "Scene: A tense samurai hand pushes a sheathed sword away from a blank folded order on scorched earth."
        )
        positive = _flux2_klein_md_positive_contract(
            "Visible action: a samurai hand pushes a sheathed sword away from a blank folded order on scorched earth.",
            source,
        )
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese sword-and-packet ground composition", positive)
        self.assertIn("object-only Japanese sword-and-sealed-packet evidence", positive)
        self.assertIn("one closed black lacquer scabbard", positive)
        self.assertIn("one attached wrapped handle", positive)
        self.assertIn("one sealed cord-tied cloth packet", positive)
        self.assertIn("scorched packed earth", positive)
        self.assertNotIn("exposed blade", positive)
        self.assertNotIn("drawn blade", positive)
        self.assertNotIn("rice-field road", positive)
        self.assertNotIn("workers", positive)
        self.assertNotIn("travelers", positive)
        self.assertNotIn("child", positive)
        self.assertNotIn("utility", positive)
        self.assertNotIn("shopfront", positive)
        self.assertNotIn("signboard", positive)
        self.assertIn("telephone pole", negative)
        self.assertIn("overhead wire", negative)
        self.assertIn("official document sheet", negative)
        self.assertIn("exposed blade", negative)
        self.assertIn("drawn sword", negative)

    def test_flux2_klein_japanese_street_contract_removes_building_sign_triggers(self):
        source = (
            "Year/period: 1605; Exact place: Edo merchant quarter street; "
            "Culture scope: Early Edo Japanese town community; "
            "Main subject: anxious child in a settlement; "
            "Scene: workers and travelers move through a merchant street with a shop nearby."
        )
        positive = _flux2_klein_md_positive_contract(
            "Visible action: workers and travelers move through a merchant street.",
            source,
        )
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese rice-field road composition", positive)
        self.assertNotIn("buildings absent", positive)
        self.assertNotIn("merchant quarters", positive)
        self.assertNotIn("stalls", positive)
        self.assertNotIn("shop", positive)
        self.assertNotIn("wood grain", positive)
        self.assertNotIn("doorway", positive)
        self.assertIn("wooden shop", negative)
        self.assertIn("paper notice", negative)
        self.assertIn("white notice sheet", negative)
        self.assertIn("field stake with writing", negative)
        self.assertIn("modern child clothing", negative)

    def test_flux2_klein_japanese_street_contract_does_not_add_unrequested_child(self):
        source = (
            "Year/period: c. 1600-1605; Exact place: damaged castle-town street in eastern Japan; "
            "Culture scope: Early Edo Japanese town community; "
            "Main subject: townspeople near damaged wooden houses; "
            "Scene: Villagers carry bundles past broken wooden fences while samurai patrol with guarded expressions."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese rice-field road composition", positive)
        self.assertNotIn("child", positive)
        self.assertNotIn("small period kosode layers", positive)
        self.assertIn("child", negative)
        self.assertIn("small child body", negative)

    def test_flux2_klein_japanese_bookshop_theater_stays_urban_not_rice_field(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, castle-town society; "
            "Year/period: 18th century; Edo period, urban culture remembered; "
            "Exact place: Edo bookshop and theater street; "
            "Scene evidence: Books and theater recall culture fostered by long peace.; "
            "Main subject: townspeople around books and theater curtains; "
            "Scene: Townspeople reach for blank-covered books as theater attendants pull curtains in the background."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_bookshop_theater_retry_sentence()

        self.assertTrue(_flux2_klein_is_japanese_bookshop_theater_context(source))
        self.assertFalse(_should_use_japanese_document_table_retry(source))
        self.assertIn("Japanese Edo theater-street low-stall composition", positive)
        self.assertIn("closed cord-tied blank-covered books", positive)
        self.assertIn("plain dark cloth curtains", positive)
        self.assertNotIn("Japanese rice-field road composition", positive)
        self.assertNotIn("open book", positive)
        self.assertNotIn("book text", positive)
        self.assertIn("Japanese Edo bookshop-theater street retry composition", retry)
        self.assertIn("same outdoor street", retry)
        self.assertNotIn("tabletop", retry)
        self.assertIn("object-only tabletop", negative)
        self.assertIn("open book", negative)
        self.assertIn("shopfront sign", negative)

    def test_flux2_klein_japanese_outer_moat_sword_avoids_packet_ground(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance; "
            "Year/period: 1867; Late Edo period, end of Tokugawa order; "
            "Exact place: quiet outer moat of Edo Castle at morning mist; "
            "Scene evidence: The quiet castle and sheathed sword conclude that daily rules restrained violence.; "
            "Main subject: quiet castle moat and lowered sheathed sword; "
            "Scene: A calm adult samurai keeps a sheathed sword lowered beside the quiet outer moat."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese quiet outer-moat sheathed-sword composition", positive)
        self.assertIn("still moat water", positive)
        self.assertIn("closed black lacquer scabbard", positive)
        self.assertNotIn("Japanese sword-and-packet ground composition", positive)
        self.assertNotIn("sealed cord-tied cloth packet", positive)
        self.assertNotIn("scorched packed earth", positive)
        self.assertIn("exposed blade", negative)
        self.assertIn("door-header character panel", negative)

    def test_flux2_klein_japanese_outer_moat_documents_use_object_evidence(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance; "
            "Year/period: 1867; Late Edo period, end of Tokugawa order; "
            "Exact place: quiet outer moat of Edo Castle at morning mist; "
            "Scene evidence: The quiet castle and sheathed sword conclude that daily rules restrained violence.; "
            "Main subject: sheathed sword beside closed documents; "
            "Scene: A sheathed sword rests beside closed blank documents as mist softens the empty castle gate."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese quiet outer-moat sheathed-sword object composition", positive)
        self.assertIn("closed cord-tied cream packet bundles", positive)
        self.assertIn("low close outer-moat object evidence frame", positive)
        self.assertNotIn("calm adult walkers", positive)
        self.assertNotIn("black portfolio", positive)
        self.assertIn("black briefcase", negative)
        self.assertIn("document portfolio", negative)

    def test_flux2_klein_japanese_generic_veranda_removes_low_desks(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance; "
            "Year/period: 1867; Late Edo period, end of Tokugawa order; "
            "Exact place: Edo Castle council chamber; "
            "Scene evidence: Envoys wait under pressure.; "
            "Main subject: officials awaiting bakufu decision; "
            "Scene: Envoys stare toward senior officials across the chamber, their faces tense and divided."
        )
        positive = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("Japanese open-veranda plain composition", positive)
        self.assertIn("bare low trays", positive)
        self.assertIn("period kimono", positive)
        self.assertNotIn("low desks", positive)

    def test_flux2_klein_japanese_negative_blocks_packet_stains_optics_and_metal_trays(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance; "
            "Year/period: 19th century; Late Edo period; "
            "Exact place: coastal watch station in Japan; "
            "Scene evidence: Coastal watchfulness shows pressure.; "
            "Main subject: coastal watchmen scanning the sea; "
            "Scene: Watchmen grip simple spyglasses and shields as waves crash below the wooden lookout."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese coastal-watch lookout composition", positive)
        self.assertNotIn("binoculars", positive)
        self.assertIn("binoculars", negative)
        self.assertIn("black stains on packet cloth", negative)
        self.assertIn("gray metal cash tray", negative)
        self.assertIn("buttoned shirt", negative)
        self.assertIn("duffel bag", negative)

    def test_flux2_klein_japanese_document_table_blocks_people_diorama_and_dirty_packets(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: 1867; Late Edo period; "
            "Exact place: Edo Castle administrative chamber; "
            "Main subject: officials receiving final crisis orders; "
            "Scene: Officials recoil as a messenger drops a sealed blank packet onto the tatami."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_textless_retry_sentence()

        self.assertIn("strict human-free", positive)
        self.assertIn("zero people", positive)
        self.assertIn("zero miniature buildings", positive)
        self.assertIn("pristine stain-free clean plain undyed unmarked packet cloth", positive)
        self.assertIn("zero rolled scrolls", retry)
        self.assertNotIn("dust, and tabletop shadows", positive)
        self.assertIn("miniature castle", negative)
        self.assertIn("open drawer", negative)
        self.assertIn("rolled scroll", negative)
        self.assertIn("dirty packet cloth", negative)
        self.assertIn("soot speckles on packet cloth", negative)

    def test_flux2_klein_japanese_old_record_drawer_uses_period_storage_scene(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: late 18th century; Late Edo period; "
            "Exact place: domain office with old wooden shelves; "
            "Main subject: official struggling with old records; "
            "Scene: An official pulls at a stuck wooden drawer, frustration tightening his face."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertFalse(_should_use_japanese_document_table_retry(source))
        self.assertIn("Japanese old-record drawer storage composition", positive)
        self.assertIn("closed unmarked wooden drawer", positive)
        self.assertIn("no western suit", positive)
        self.assertIn("book spine text", negative)
        self.assertNotIn("zero drawers", positive)
        self.assertNotIn("object-only Japanese sealed domain packet council evidence", positive)

    def test_flux2_klein_japanese_bookshop_and_theater_facades_stay_unmarked(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, castle-town society; "
            "Year/period: 18th century; Edo period; "
            "Exact place: Edo theater entrance; "
            "Main subject: crowd entering a theater; "
            "Scene: A lively crowd presses toward a theater entrance as attendants pull blank curtains aside."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_bookshop_theater_retry_sentence()

        self.assertTrue(_flux2_klein_is_japanese_bookshop_theater_context(source))
        self.assertIn("Japanese Edo theater-street low-stall composition", positive)
        self.assertIn("continuous blank timber", positive)
        self.assertIn("cuts off all roof-sign and upper-floor sign zones", positive)
        self.assertIn("unmarked curtain cloth", retry)
        self.assertIn("cuts off all roof-sign and upper-floor sign zones", retry)
        self.assertIn("hanging shop sign", negative)
        self.assertIn("theater placard", negative)

    def test_flux2_klein_japanese_outdoor_work_scenes_block_poles_and_modern_caps(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, domain administration; "
            "Year/period: 17th century; Edo period; "
            "Exact place: domain storehouse and official checkpoint; "
            "Main subject: rice tax being measured; "
            "Scene: Officials measure rice bales as farmers wait anxiously with straw hats in their hands."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("soft smoke plumes without supporting poles", positive)
        self.assertIn("close yard crop keeps distant village buildings outside the canvas", positive)
        self.assertIn("broad unbroken hills", positive)
        self.assertNotIn("low roofs, tree lines", positive)
        self.assertIn("plain cloth headwraps", positive)
        self.assertIn("wire-strung pole", negative)
        self.assertIn("utility pole row", negative)
        self.assertIn("cross-shaped field stake", negative)
        self.assertIn("flat cap", negative)
        self.assertIn("steel helmet", negative)

    def test_flux2_klein_japanese_warped_floor_avoids_deep_crack(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance; "
            "Year/period: 19th century; Late Edo period; "
            "Exact place: old Edo Castle corridor; "
            "Main subject: official noticing warped floorboards; "
            "Scene: An official pauses as warped floorboards creak underfoot, worry crossing his face."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese intact old-floor veranda composition", positive)
        self.assertIn("old but unbroken floorboards", positive)
        self.assertIn("small seam shadows", positive)
        self.assertIn("deep floor crack", negative)
        self.assertIn("chasm in floor", negative)

    def test_flux2_klein_japanese_gate_and_notice_board_keep_period_clothing(self):
        gate_source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: early 19th century; "
            "Exact place: old gate of a domain office; "
            "Main subject: officials struggling with heavy gate; "
            "Scene: Officials push a warped wooden gate that groans and resists their full weight."
        )
        notice_source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: early 19th century; "
            "Exact place: domain office notice area with blank boards; "
            "Main subject: official replacing blank notice boards; "
            "Scene: An official fixes blank boards to a wooden frame as townspeople watch uneasily."
        )
        gate_positive = _flux2_klein_md_positive_contract(gate_source, gate_source)
        notice_positive = _flux2_klein_md_positive_contract(notice_source, notice_source)
        negative = _flux2_klein_md_negative_contract(notice_source, notice_positive)

        self.assertIn("Japanese heavy-domain-gate burden composition", gate_positive)
        self.assertIn("waraji or zori sandals", gate_positive)
        self.assertIn("no modern caps", gate_positive)
        self.assertIn("Japanese blank-notice-board regulation composition", notice_positive)
        self.assertIn("uninterrupted wood grain", notice_positive)
        self.assertIn("modern boots", negative)

    def test_flux2_klein_japanese_marker_council_is_full_bleed_textless(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, domain administration; "
            "Year/period: early 17th century; "
            "Exact place: Edo Castle council chamber; "
            "Main subject: council dividing domain responsibilities; "
            "Scene: Officials place plain wooden markers in separate groups as a senior samurai watches sharply."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("Japanese textless marker-council veranda composition", positive)
        self.assertIn("full-bleed", positive)
        self.assertIn("no paper margin", positive)
        self.assertIn("smooth blank wooden rods", positive)
        self.assertIn("labeled marker", negative)
        self.assertIn("floor block with writing", negative)

    def test_flux2_klein_japanese_rice_storehouse_avoids_document_tabletop(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Material culture: official documents, domain gates, rice bales, road stations; "
            "Year/period: early 17th century; Early Edo period, domain administration; "
            "Exact place: rice storehouse beside a domain office; "
            "Scene evidence: Rice storehouses show domains handling local resources.; "
            "Main subject: workers at rice-bundle yards; "
            "Scene: Workers stack rope-tied rice bales under plain roof eaves beside a loaded wooden cart."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_rice_storehouse_retry_sentence()

        self.assertTrue(_flux2_klein_is_japanese_rice_storehouse_context(source))
        self.assertFalse(_should_use_japanese_document_table_retry(source))
        self.assertIn("Japanese rice-storehouse exterior yard composition", positive)
        self.assertIn("rope-tied rice bales", positive)
        self.assertNotIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertNotIn("top-down edge-to-edge tabletop", positive)
        self.assertIn("Japanese rice-storehouse exterior yard retry composition", retry)
        self.assertNotIn("tabletop", retry)
        self.assertIn("bottom title plaque", negative)
        self.assertIn("warehouse sign", negative)

    def test_flux2_klein_japanese_frayed_storage_avoids_checkpoint_road(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Material culture: official documents, domain gates, rice bales, road stations; "
            "Year/period: early 19th century; Late Edo period, limits of reform; "
            "Exact place: storage room with frayed rope binding boxes; "
            "Scene evidence: Frayed bindings symbolize reforms holding but not resolving the system.; "
            "Main subject: frayed rope around old document boxes; "
            "Scene: A clerk pulls frayed rope tight around boxes, but the knot begins to slip."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)
        retry = _flux2_klein_japanese_frayed_storage_retry_sentence()

        self.assertTrue(_flux2_klein_is_japanese_frayed_storage_context(source))
        self.assertFalse(_should_use_japanese_document_table_retry(source))
        self.assertIn("Japanese frayed-storage-box room composition", positive)
        self.assertIn("frayed rope", positive)
        self.assertIn("kimono, hakama, wide sleeves", positive)
        self.assertNotIn("checkpoint control", positive)
        self.assertNotIn("open road", positive)
        self.assertNotIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertIn("Japanese frayed-storage-box room retry composition", retry)
        self.assertNotIn("checkpoint", retry)
        self.assertIn("checkpoint road", negative)
        self.assertIn("modern uniform", negative)
        self.assertIn("buttoned shirt", negative)
        self.assertIn("western trousers", negative)

    def test_flux2_klein_japanese_inner_gate_avoids_document_tabletop(self):
        source = (
            "Global visual world: Time range: 1603-1867, Edo period Japan; "
            "Culture scope: Tokugawa Japan, samurai governance, domain administration; "
            "Year/period: 1867; Late Edo period, Tokugawa bakufu end; "
            "Exact place: Edo Castle inner gate; "
            "Scene evidence: The inner gate marks the end of the Tokugawa bakufu in 1867.; "
            "Main subject: officials leaving Edo Castle; "
            "Scene: Officials carry blank document boxes through the inner gate, faces lowered in silence."
        )
        positive = _flux2_klein_md_positive_contract(source, source)

        self.assertIn("Japanese castle-gate lower composition", positive)
        self.assertIn("heavy plain timber castle gate", positive)
        self.assertNotIn("Japanese object-only sealed-bundle tabletop composition", positive)
        self.assertNotIn("top-down object-only tabletop", positive)

    def test_red_corner_detector_catches_red_stamp(self):
        from PIL import Image, ImageDraw

        with tempfile.TemporaryDirectory() as tmp:
            red_stamp = Path(tmp) / "red_stamp.png"

            stamped = Image.new("RGB", (1280, 720), (210, 205, 185))
            stamp_draw = ImageDraw.Draw(stamped)
            stamp_draw.rectangle((5, 7, 46, 96), fill=(160, 72, 68))
            for row in range(5):
                y = 18 + row * 14
                stamp_draw.line((17, y, 28, y + 8), fill=(22, 18, 16), width=2)
                stamp_draw.line((31, y, 37, y), fill=(22, 18, 16), width=2)
            stamped.save(red_stamp)

            self.assertTrue(_image_has_corner_artist_mark(red_stamp))

    def test_flux2_klein_japanese_negative_blocks_sleeve_patches(self):
        source = (
            "Year/period: 1599; Exact place: Edo Castle inner room; "
            "Culture scope: Late Sengoku Japanese administration; "
            "Main subject: Ieyasu reading in Edo; "
            "Scene: Ieyasu calmly reads a blank document while retainers lean forward."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("sealed cloth-wrapped packet bundles", positive)
        self.assertIn("sleeve patch", negative)
        self.assertIn("colored arm patch", negative)
        self.assertIn("red-and-white badge", negative)

    def test_flux2_klein_japanese_osaka_defense_board_uses_raised_markers(self):
        source = (
            "Year/period: 1614; Exact place: Tokugawa council camp near Osaka; "
            "Culture scope: Early Edo Japanese military council; "
            "Main subject: Tokugawa council over Osaka; "
            "Scene: Tokugawa commanders lean over a blank board of Osaka's defenses, faces hard under lamplight."
        )
        positive = _flux2_klein_md_positive_contract(source, source)
        negative = _flux2_klein_md_negative_contract(source, positive)

        self.assertIn("raised cord-and-stone Osaka defense markers", positive)
        self.assertIn("raised rope cords", positive)
        self.assertIn("plain clay blocks", positive)
        self.assertNotIn("blank board of Osaka", positive)
        self.assertIn("paper map", negative)
        self.assertIn("map lines", negative)
        self.assertIn("drawn borders", negative)

    def test_longtube_local_v1_enriches_modern_japanese_kitchen_prompt(self):
        raw = "Year/period: 2020s; 現代日本、令和時代; Exact place: 日本の一般家庭の台所・食卓; Scene: miso soup"
        enriched = _enrich_local_v1_positive_prompt(raw)

        self.assertIn("Present-day modern setting", enriched)
        self.assertIn("Ordinary modern Japanese home kitchen", enriched)
        self.assertIn("main subject is a bowl of miso soup", enriched)
        self.assertNotIn("no exterior", enriched.lower())

    def test_default_historical_image_guard_locks_period_material_culture(self):
        guard = prompt_builder.GENERAL_HISTORY_ACCURACY_DIRECTIVE

        self.assertIn("HARD HISTORICAL MATERIAL CULTURE LOCK", guard)
        self.assertIn("Year/period and Exact place", guard)
        self.assertIn("binding source of truth", guard)
        self.assertIn("clothing cuts, hairstyles, headwear", guard)
        self.assertIn("tools, weapons only when the narration requires them", guard)
        self.assertIn("ritual objects, everyday objects", guard)
        self.assertIn("Style words may change rendering only", guard)

    def test_hou_bowl_positive_directive_is_english_only(self):
        directive = prompt_builder.HOU_BOWL_OBJECT_DIRECTIVE
        blocked = [
            ch for ch in directive
            if ("\uac00" <= ch <= "\ud7a3")
            or ("\u4e00" <= ch <= "\u9fff")
            or ("\u3040" <= ch <= "\u30ff")
        ]

        self.assertEqual([], blocked)
        self.assertIn("Houmyeong vessel", directive)

    def test_flux2_klein_goguryeo_final_prompt_not_misread_as_japanese(self):
        prompt = (
            "Global visual world: Time range: 402-410 AD; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 402-410 AD; "
            "Scene: A sharp iron sword slicing through a heavy blizzard || HARD LOCK: "
            "no Japanese gate, no samurai armor, no katana."
        )

        positive, _negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertFalse(_flux2_klein_is_historical_japanese_context(prompt))
        self.assertIn("Goguryeo northern frontier snowstorm", positive)
        self.assertNotIn("historical Japanese forms", positive)
        self.assertNotIn("katana", positive.lower())
        self.assertNotIn("samurai", positive.lower())

    def test_flux2_klein_goguryeo_map_scene_becomes_command_table_action(self):
        prompt = (
            "Global visual world: Time range: 402-410 AD; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 402-410 AD; "
            "Scene: The golden map dripping with thick, dark red blood"
        )

        positive = _flux2_klein_ep13_scene_prompt(prompt)

        self.assertIn("Goguryeo frontier command-table action scene", positive)
        self.assertIn("Goguryeo officers", positive)
        self.assertIn("route cord", positive)
        self.assertNotIn("historical Japanese forms", positive)
        self.assertNotIn("katana", positive.lower())

    def test_flux2_klein_blade_draw_uses_scene_named_subject(self):
        prompt = (
            "Global visual world: Time range: 402-410 AD; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 402-410 AD; "
            "Main subject: Murong Sheng; Scene: A fierce warlord, Murong Sheng, drawing his sword with a cruel glare"
        )

        positive, _negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertIn("Show one Murong Sheng", positive)
        self.assertNotIn("Show one King Gwanggaeto", positive)

    def test_flux2_klein_gwanggaeto_guard_does_not_override_ruined_fortress_cut(self):
        guard = "GOGURYEO-SILLA 415 MATERIAL CULTURE LOCK - King Gwanggaeto continuity guard"
        prompt = (
            f"{guard}; Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: ruined Silla fortress covered in thick black smoke; "
            "Scene: A ruined Silla fortress covered in thick black smoke"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)

        self.assertIn("ruined Silla fortress", positive)
        self.assertNotIn("King Gwanggaeto", positive)
        self.assertNotIn("entrance portrait", positive)

    def test_flux2_klein_642_scale_crown_becomes_object_only_power_balance(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: scale, broken sword, crown; "
            "Scene: A bronze scale weighs a broken sword against a crown"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("diplomatic power balance scale", positive)
        self.assertIn("flat gold authority band", positive)
        self.assertNotIn("head-worn", positive)
        self.assertNotIn("human head", positive)
        self.assertIn("severed head", negative)

    def test_flux2_klein_642_chess_metaphor_becomes_period_alliance_markers(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: Two different colored chess pieces; "
            "Scene: Two different colored chess pieces standing side by side"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("cord-and-stone alliance marker tabletop", positive)
        self.assertNotIn("chess", positive.lower())
        self.assertNotIn("standing people", positive.lower())
        self.assertIn("modern board game", negative)
        self.assertIn("colored plastic shoes", negative)

    def test_flux2_klein_642_wolf_metaphor_becomes_human_diplomatic_standoff(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: two wolves; "
            "Scene: two wolves staring down each other during diplomatic talks"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("two-ruler diplomatic standoff", positive)
        self.assertNotIn("wolf", positive.lower())
        self.assertNotIn("wolves", positive.lower())
        self.assertIn("anthropomorphic wolf", negative)

    def test_flux2_klein_642_shield_tear_stays_small_surface_droplet(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: teardrop on shield; "
            "Scene: one teardrop rests on a shield"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("tiny wet tear droplet", positive)
        self.assertIn("shield surface", positive)
        self.assertNotIn("floating", positive.lower())
        self.assertIn("teardrop icon", negative)

    def test_flux2_klein_642_tiger_prey_metaphor_becomes_aftermath_evidence(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: tiger tearing into its prey without mercy in the snow; "
            "Scene: A tiger tearing into its prey without mercy in the snow"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("victory-and-defeat aftermath evidence", positive)
        self.assertIn("broken Silla shield", positive)
        self.assertNotIn("tiger", positive.lower())
        self.assertNotIn("prey", positive.lower())
        self.assertIn("tiger", negative)
        self.assertIn("animal eating prey", negative)

    def test_flux2_klein_642_hidden_dagger_rags_becomes_object_only_cut(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: small; "
            "Scene: A small, sharp dagger hidden beneath a beggar's rags"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("object-only hidden dagger", positive)
        self.assertIn("torn plain hemp rags", positive)
        self.assertNotIn("beggar", positive.lower())
        self.assertIn("upright wooden post", negative)
        self.assertIn("readable marks on wood", negative)

    def test_flux2_klein_642_fable_animals_become_empty_trap_evidence(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: ancient illustration of a turtle carrying a rabbit underwater; "
            "Scene: An ancient illustration of a turtle carrying a rabbit underwater"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("empty escape-trap evidence", positive)
        self.assertIn("sprung rope snare", positive)
        self.assertNotIn("rabbit", positive.lower())
        self.assertNotIn("turtle", positive.lower())
        self.assertIn("armored rabbit", negative)
        self.assertIn("animal silhouette", negative)

    def test_flux2_klein_642_writing_and_map_symbols_become_edge_on_rods_and_stones(self):
        writing_prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Scene: A close-up of ink characters forming on the bamboo paper"
        )
        map_prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: cross-shaped marking on a map being surrounded; "
            "Scene: A cross-shaped marking on a map being surrounded by red arrows"
        )

        writing_positive = _flux2_klein_md_positive_contract(writing_prompt, writing_prompt)
        map_positive = _flux2_klein_md_positive_contract(map_prompt, map_prompt)
        negative = _flux2_klein_md_negative_contract(map_prompt, map_positive)

        self.assertIn("edge-on tied bamboo rods", writing_positive)
        self.assertIn("edge-on cord-tied bundle of narrow tan bamboo rods", writing_positive)
        self.assertIn("unused brush", writing_positive)
        self.assertNotIn("ink characters", writing_positive.lower())
        self.assertNotIn("bamboo paper", writing_positive.lower())
        self.assertNotIn("closed bamboo message packet", writing_positive)
        self.assertIn("cord-and-stone territorial pressure layout", map_positive)
        self.assertNotIn("red arrows", map_positive.lower())
        self.assertNotIn("cross-shaped", map_positive.lower())
        self.assertNotIn("map", map_positive.lower())
        self.assertIn("red arrow", negative)
        self.assertIn("characters on bamboo", negative)
        self.assertIn("black glyphs on bamboo rods", negative)

    def test_flux2_klein_642_skull_dragon_multi_sword_and_block_are_period_evidence(self):
        cases = [
            (
                "A mountain of crushed skulls beneath an imposing throne",
                "low wooden command dais above broken armor evidence",
                ("skull", "skulls", "bone"),
            ),
            (
                "A massive Chinese dragon shadow looming ominously over the horizon",
                "ominous roof-beam shadow over a fortress horizon",
                ("dragon", "Chinese dragon", "monster"),
            ),
            (
                "A chilling silhouette of a dictator holding multiple bloody swords",
                "silhouetted ruler holding one blood-stained straight iron sword",
                ("multiple bloody swords", "multiple swords", "dictator"),
            ),
            (
                "A dark executioner's block waiting patiently in a gloomy courtyard",
                "plain wooden execution block on packed-earth courtyard ground",
                ("wall switch", "switch plate", "modern door"),
            ),
        ]
        for scene, expected, forbidden_terms in cases:
            with self.subTest(scene=scene):
                prompt = (
                    "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
                    "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
                    "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
                    f"Exact place: Pyongyang Fortress; Main subject: {scene}; Scene: {scene}"
                )

                positive = _flux2_klein_md_positive_contract(prompt, prompt)
                negative = _flux2_klein_md_negative_contract(prompt, positive)

                self.assertIn(expected, positive)
                for term in forbidden_terms:
                    self.assertNotIn(term.lower(), positive.lower())
                self.assertIn("modern wall switch", negative)
                self.assertIn("Chinese dragon", negative)
                self.assertIn("skull", negative)

    def test_flux2_klein_642_eye_glint_uses_human_face_without_glow_or_lens(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: eye staring directly and intensely into the camera lens; "
            "Scene: An eye staring directly and intensely into the camera lens"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("stern human face close-up", positive)
        self.assertIn("ordinary wet eye highlights", positive)
        self.assertNotIn("camera lens", positive.lower())
        self.assertNotIn("glowing", positive.lower())
        self.assertIn("glowing orb", negative)
        self.assertIn("camera lens", negative)

    def test_flux2_klein_642_blue_silk_avoids_modern_cuffs_and_hands(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: fine blue silk being handed over; "
            "Scene: fine blue silk being handed over as tribute"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("fine blue silk tribute bundles", positive)
        self.assertIn("cropped rough hemp sleeve ends", positive)
        self.assertNotIn("handed", positive.lower())
        self.assertNotIn("shirt cuff", positive.lower())
        self.assertIn("black suit sleeve", negative)
        self.assertIn("white shirt cuff", negative)

    def test_flux2_klein_642_sunlight_avoids_finger_beam(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Scene: a finger pointing upward at a ray of sunlight"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("natural daylight strip crossing dust", positive)
        self.assertIn("lowered rough hemp sleeve edge", positive)
        self.assertNotIn("finger", positive.lower())
        self.assertNotIn("pointing", positive.lower())
        self.assertIn("laser beam", negative)
        self.assertIn("glowing fingertip", negative)

    def test_flux2_klein_642_claw_handshake_avoids_tablets_and_fake_chars(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: shadowy claw hand shaking across diplomacy table; "
            "Scene: a shadowy claw hand shaking across diplomacy table"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("failed diplomatic contact across a low table", positive)
        self.assertIn("cropped wide hemp sleeve ends", positive)
        self.assertIn("flat rounded unmarked clay weights", positive)
        self.assertIn("edge-to-edge tight low-table", positive)
        self.assertIn("riverbank reeds", positive)
        self.assertNotIn("claw", positive.lower())
        self.assertNotIn("tablet", positive.lower())
        self.assertNotIn("stone marker", positive.lower())
        self.assertIn("upright tablet", negative)
        self.assertIn("stone tablet with writing", negative)
        self.assertIn("stone marker with glyph", negative)
        self.assertIn("glyph on marker", negative)
        self.assertIn("painted black border", negative)
        self.assertIn("vignette border", negative)

    def test_flux2_klein_642_capstan_avoids_marked_foreground_stones(self):
        prompt = (
            "Global visual world: Time range: 642 AD; Place scope: Pyongyang Fortress; "
            "Culture scope: Goguryeo and Silla diplomatic world; Material culture: iron weapons, "
            "lamellar armor, hemp garments; Continuity rule: period materials only; Year/period: 642 AD; "
            "Exact place: Pyongyang Fortress; Main subject: a meat grinder crushing soldiers; "
            "Scene: a meat grinder crushing soldiers into a brutal war machine"
        )

        positive = _flux2_klein_md_positive_contract(prompt, prompt)
        negative = _flux2_klein_md_negative_contract(prompt, positive)

        self.assertIn("preindustrial wooden capstan and stone crushing wheel", positive)
        self.assertIn("plain dust", positive)
        self.assertNotIn("loose stones", positive.lower())
        self.assertIn("glyphs on stone", negative)
        self.assertIn("foreground stone with letters", negative)

    def test_visual_policy_rewrites_bad_sui_river_prompt_for_jungnyeong_demand(self):
        prompt = (
            "Global visual world: Time range: 612 AD; Place scope: Goguryeo-Sui open river battlefield, "
            "muddy river crossing; Culture scope: Goguryeo and Sui military world; Material culture: "
            "spear shafts, shattered shields, torn lamellar armor, exhausted Sui soldiers; Continuity rule: "
            "outdoor river battlefield; Year/period: 612 CE; Goguryeo-Sui war, 612 AD; Exact place: "
            "612 Goguryeo-Sui open river battlefield, muddy river crossing; Scene evidence: exhausted "
            "Sui soldiers, Goguryeo pressure from the bank; Style: longtubestyle; Main subject: Sui soldiers; "
            "Scene: Exhausted Sui soldiers struggle across a cold open river crossing while also showing "
            "a finger pointing aggressively at the Han River on a map"
        )

        normalized = normalize_cut_image_prompt(
            prompt,
            "과거 신라가 빼앗은 죽령 이북 땅을 모두 내놓아라.",
            "외교의 달인 김춘추와 토끼의 간",
        )

        self.assertIn("territorial demand", normalized)
        self.assertIn("cord-and-stone territorial layout", normalized)
        self.assertIn("Pyongyang Fortress audience hall", normalized)
        self.assertIn("Kim Chunchu", normalized)
        self.assertIn("Yeon Gaesomun", normalized)
        self.assertNotIn("board", normalized.lower())
        self.assertNotIn("Sui soldiers", normalized)
        self.assertNotIn("open river battlefield", normalized)
        self.assertNotIn("river crossing", normalized)
        self.assertNotIn("612 AD", normalized)

    def test_flux2_klein_goguryeo_eye_scene_does_not_use_midgley_prompt(self):
        prompt = (
            "Global visual world: Time range: 402-410 AD; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Year/period: 402-410 AD; "
            "Main subject: King Gwanggaeto; Scene: King Gwanggaeto watches a burning frontier fortress "
            "from a dark timber command room"
        )

        positive, _negative = _compact_flux2_klein_4b_prompt(prompt, "")

        self.assertNotIn("1940s Worthington", positive)
        self.assertNotIn("turning gear", positive)
        self.assertIn("Goguryeo", positive)

    def test_historical_negative_prompt_avoids_object_name_lists(self):
        negative = prompt_builder.historical_negative_prompt(
            "Year/period: c. 109-108 BCE; Exact place: Pae River crossing",
            True,
        )

        self.assertIn("text", negative)
        self.assertIn("map", negative)
        self.assertNotIn("rifle", negative.lower())
        self.assertNotIn("uniform", negative.lower())
        self.assertNotIn("samurai", negative.lower())
        self.assertNotIn("wrong-era", negative.lower())

    def test_default_image_guard_blocks_fake_glyphs_and_crests(self):
        positive_guard = prompt_builder.NO_TEXT_DIRECTIVE
        negative = prompt_builder.NO_TEXT_NEGATIVE_PROMPT

        self.assertIn("NO FAKE GLYPHS", positive_guard)
        self.assertIn("NO FAKE KANJI", positive_guard)
        self.assertIn("NO CRESTS", positive_guard)
        self.assertIn("wall hangings, banners, flags, armor plates", positive_guard)
        self.assertIn("completely BLANK and unmarked", positive_guard)
        self.assertIn("pseudo calligraphy", negative)
        self.assertIn("mon crest", negative)
        self.assertIn("banner symbol", negative)

    def test_script_visual_contract_requires_period_evidence_in_image_prompt(self):
        prompt_source = (Path(__file__).resolve().parent.parent / "app" / "services" / "llm" / "base.py").read_text(
            encoding="utf-8-sig",
        )

        self.assertIn("의복, 머리모양, 머리 장식, 장신구", prompt_source)
        self.assertIn("visual_scene에 보이는 시대 증거를 적어야 합니다", prompt_source)
        self.assertIn("시대에 맞을 법한 평범한 사물", prompt_source)
        self.assertIn("가짜 문자, 가짜 한자, 가짜 서예", prompt_source)
        self.assertIn("visual_year는 정확한 보이는 연도", prompt_source)
        self.assertIn("visual_location은 일반 배경이 아니라 구체적인 공간", prompt_source)
        self.assertIn("spoken cue", prompt_source)
        self.assertIn("visual_subject는 컷 내용에 맞게", prompt_source)

    def test_cut_image_prompt_strips_spoken_cue_and_narration_text(self):
        narration = "곰이 사람이 됐다는 이야기는 이상하게 들립니다."
        prompt = (
            "Year/period: mythic tradition; Scene: cave entrance with bear and tiger; "
            "spoken cue: 곰이 사람이 됐다는 이야기는 이상하게 들립니다.; "
            "Main subject: Hwanung"
        )

        normalized = normalize_cut_image_prompt(prompt, narration)

        self.assertNotIn("spoken cue", normalized.lower())
        self.assertNotIn(narration, normalized)
        self.assertIn("cave entrance with bear and tiger", normalized)

    def test_script_quality_flags_template_phrases_and_prompt_leaks(self):
        script = {
            "title": "진개",
            "cuts": [
                {
                    "narration": "압력이 다가옵니다.",
                    "image_prompt": "Scene: border; spoken cue: 압력이 다가옵니다.",
                },
                {
                    "narration": "연나라는 왜 동쪽으로 움직였나는 두 번째 단서와 연결됩니다.",
                    "image_prompt": "Scene: border envoy near a frontier road; Main subject: frontier envoy",
                },
                {
                    "narration": "사기 조선열전에는 기록에는 항복을 말한 대신들이 등장합니다.",
                    "image_prompt": "Scene: officials in a fortress council; Main subject: divided officials",
                }
            ],
        }

        issues = inspect_script_quality(script, "진개")

        self.assertTrue(any("forbidden template phrase" in issue for issue in issues))
        self.assertTrue(any("narration label leaked" in issue for issue in issues))
        self.assertTrue(any("bad grammar pattern" in issue for issue in issues))

    def test_story_plan_topic_alignment_accepts_japanese_aliases(self):
        plan = {
            "visual_world": {
                "time_range": "1582-1591",
                "place_scope": "Japan",
                "culture_scope": "Toyotomi unification administration",
            },
            "character_map": [
                {"name": "豊臣秀吉", "role": "central authority"},
                {"name": "百姓", "role": "village farmers"},
            ],
            "causality_chain": [
                "検地と刀狩りは、地方社会を政権が読める形にする政策だった",
                "太閤検地は土地の生産力をこくだかで整理した",
            ],
            "fact_ledger": {
                "confirmed_facts": [
                    "1588年に刀狩り令が出され、百姓の武器を集める方針がしめされた"
                ],
            },
            "scene_blocks": [
                {"focus": "検地と刀狩りが税、軍役、身分整理につながる"},
            ],
        }
        cfg = {
            "episode_core_content": (
                "[핵심인물] 태합검지와 도검몰수\n"
                "[주요인물1] 도요토미 히데요시\n"
                "[주요인물2] 농민"
            )
        }

        issues = _inspect_story_plan_topic_alignment(
            plan,
            "검지와 도검몰수는 무엇을 노렸을까",
            cfg,
        )

        self.assertEqual([], issues)

    def test_script_quality_allows_repeated_single_topic_word(self):
        cuts = [
            {
                "narration": f"부왕은 국면 {i}에서 다른 판단을 남겼습니다.",
                "image_prompt": f"Scene: council chamber moment {i}; Main subject: envoy {i}",
            }
            for i in range(20)
        ]

        issues = inspect_script_quality(
            {"title": "부왕의 굴복 외교", "cuts": cuts},
            "부왕의 굴복 외교",
        )

        self.assertFalse(any("topic phrase repeated too often" in issue for issue in issues))
        self.assertFalse(any("topic term repeated too often" in issue for issue in issues))

    def test_script_quality_flags_repeated_topic_phrase(self):
        cuts = [
            {
                "narration": f"부왕의 굴복 외교는 국면 {i}에서 다시 드러났습니다.",
                "image_prompt": f"Scene: frontier negotiation moment {i}; Main subject: royal envoy {i}",
            }
            for i in range(16)
        ]

        issues = inspect_script_quality(
            {"title": "부왕의 굴복 외교", "cuts": cuts},
            "부왕의 굴복 외교",
        )

        self.assertTrue(
            any("topic phrase repeated too often: 부왕 굴복 외교=16" in issue for issue in issues)
        )

    def test_script_quality_does_not_treat_scene_evidence_as_scene(self):
        cuts = []
        for i in range(150):
            cuts.append({
                "cut_number": i + 1,
                "narration": f"테스트 문장 {i + 1}입니다.",
                "image_prompt": (
                    "Year/period: c. 1280s; "
                    "Exact place: Gojoseon ritual settlement; "
                    "Scene evidence: shared dating clue; "
                    "Style: simple cartoon illustration, documentary cartoon style, clean thick outlines, soft natural shadows; "
                    f"Main subject: subject {i + 1}; "
                    f"Scene: unique action {i + 1} near a blank ritual table"
                ),
                "shorts_candidate": i < 60,
                "shorts_group": (i // 15) + 1 if i < 60 else 0,
            })

        issues = inspect_script_quality({"title": "단군왕검", "cuts": cuts}, "단군왕검")

        self.assertFalse(any("image scene repeated too often" in issue for issue in issues))

    def test_script_quality_accepts_three_complete_shorts_groups(self):
        cuts = []
        for i in range(150):
            cuts.append({
                "cut_number": i + 1,
                "narration": f"테스트 전개 {i + 1}은 다음 정보로 이어집니다.",
                "image_prompt": (
                    "Year/period: c. 1280s; "
                    "Exact place: frontier camp; "
                    "Scene evidence: shared dating clue; "
                    "Style: simple cartoon illustration, documentary cartoon style, clean thick outlines, soft natural shadows; "
                    f"Main subject: subject {i + 1}; "
                    f"Scene: unique action {i + 1} beside period-correct tools"
                ),
                "shorts_candidate": i < 45,
                "shorts_group": (i // 15) + 1 if i < 45 else 0,
            })

        issues = inspect_script_quality({"title": "테스트", "cuts": cuts}, "테스트")

        self.assertFalse(any("invalid shorts" in issue for issue in issues))

    def test_visual_context_injects_year_and_exact_place_into_image_prompt(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "image_prompt": "armored lords in a tense council room",
                    "visual_year": "1591",
                    "visual_period": "Late Sengoku period, Toyotomi rule, Japan",
                    "visual_location": "Hizen Nagoya castle council room, northern Kyushu, interior",
                    "visual_evidence": "Hideyoshi's invasion planning pressure",
                }
            ]
        }

        strengthened = BaseLLMService.strengthen_visual_context(script, {})
        prompt = strengthened["cuts"][0]["image_prompt"]

        self.assertTrue(prompt.startswith("Year/period: 1591; Late Sengoku period"))
        self.assertIn("Exact place: Hizen Nagoya castle council room, northern Kyushu, interior", prompt)
        self.assertIn("Scene: armored lords in a tense council room", prompt)

    def test_visual_context_builds_prompt_from_compact_visual_fields(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "image_prompt": "",
                    "visual_year": "1591",
                    "visual_period": "Late Sengoku period, Toyotomi rule, Japan",
                    "visual_location": "Hizen Nagoya castle council room",
                    "visual_evidence": "invasion planning pressure",
                    "visual_subject": "Toyotomi envoy holding a sealed order",
                    "visual_scene": "tense officials lean over a blank campaign map under dim lamplight",
                }
            ]
        }

        strengthened = BaseLLMService.strengthen_visual_context(script, {})
        prompt = strengthened["cuts"][0]["image_prompt"]

        self.assertIn("Year/period: 1591; Late Sengoku period", prompt)
        self.assertIn("Exact place: Hizen Nagoya castle council room", prompt)
        self.assertIn("Style: serious adult graphic novel illustration", prompt)
        self.assertIn("Main subject: Toyotomi envoy holding a sealed order", prompt)
        self.assertIn("Scene: tense officials lean over a blank campaign map", prompt)
        self.assertEqual(prompt.count("Style:"), 1)

    def test_visual_context_drops_non_english_metadata_before_image_prompt(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
                "material_culture": "iron weapons, bows, leather armor, lamellar armor, wooden halls",
                "continuity_rule": "Every scene stays in ancient Northeast Asia with no modern objects.",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_period": "402~410년 고구려사 흐름",
                    "visual_location": "요하, 북방",
                    "visual_evidence": "큐시트 연도=402~410년; 배경=요하, 북방",
                    "visual_subject": "광개토대왕",
                    "visual_scene": "A Goguryeo cavalry commander watches a tense river crossing at dusk",
                }
            ],
        }

        strengthened = BaseLLMService.strengthen_visual_context(script, {})
        prompt = strengthened["cuts"][0]["image_prompt"]

        self.assertNotRegex(prompt, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertIn("Time range: 402-410 AD", prompt)
        self.assertIn("Year/period: 402-410 AD", prompt)
        self.assertIn("Exact place: Liao River, northern frontier", prompt)
        self.assertIn("Main subject: King Gwanggaeto", prompt)
        self.assertIn("Scene: A Goguryeo cavalry commander watches", prompt)

    def test_visual_policy_concretizes_goguryeo_metaphor_scene(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
                "material_culture": "iron weapons, bows, leather armor, lamellar armor, wooden halls",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "지도 위 붉은 선은 핏자국입니다.",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_period": "402~410년 고구려사 흐름",
                    "visual_location": "요하, 북방",
                    "visual_evidence": "큐시트 연도=402~410년; 배경=요하, 북방",
                    "visual_subject": "광개토대왕",
                    "visual_scene": "The golden map dripping with thick, dark red blood",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]
        prompt = cut["image_prompt"]

        self.assertNotRegex(prompt, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertIn("Main subject: Goguryeo officers", prompt)
        self.assertIn("Scene: Two to four Goguryeo officers lean over a low wooden campaign table", prompt)
        self.assertNotIn("golden map dripping", prompt)
        self.assertEqual(cut["visual_subject"], "Goguryeo officers")
        self.assertIn("Goguryeo officers", cut["visual_scene"])

    def test_visual_policy_converts_goguryeo_mechanical_metaphor_to_period_scene(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
            },
            "cuts": [
                {
                    "cut_number": 122,
                    "narration": "전쟁을 멈추면 무너지는 제국.",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_subject": "massive iron gear grinding heavily against another",
                    "visual_scene": "A massive iron gear grinding heavily against another, sparks flying in the dark",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertEqual(cut["visual_subject"], "Goguryeo soldiers")
        self.assertIn("heavy wooden siege cart", cut["visual_scene"])
        self.assertNotIn("iron gear", cut["image_prompt"])
        self.assertNotIn("mechanical", cut["image_prompt"])

    def test_visual_policy_converts_goguryeo_generic_chinese_and_meta_scenes(self):
        cases = [
            (
                "A dark, imposing Chinese fortress looming heavily in the dense fog",
                "Later Yan frontier fortress",
                "Sukgunseong",
            ),
            (
                "A Chinese governor running away in absolute terror, dropping his weapon",
                "Murong Gui",
                "Later Yan governor Murong Gui flees",
            ),
            (
                "A massive, endless wave of Yan soldiers marching towards a fortress",
                "Later Yan soldiers",
                "dense ranks toward a low Goguryeo",
            ),
            (
                "A massive, imposing stone fortress standing firmly against a dark storm",
                "Goguryeo frontier fortress",
                "single-level timber watch posts",
            ),
            (
                "A dark, quiet royal bedchamber, the curtains drawn tight",
                "Goguryeo royal bedchamber",
                "low wooden sleeping platform",
            ),
            (
                "An old, fairy-tale history book being thrown into a blazing fire",
                "Goguryeo scribe",
                "blank wooden tale tablet",
            ),
            (
                "A massive, heavy stone wheel rolling over a pile of broken shields",
                "heavy wooden supply cart wheel",
                "broken shields",
            ),
            (
                "A young prince holds a heavy crown in a dark hall",
                "young Goguryeo prince",
                "succession tablet box",
            ),
            (
                "A king sitting alone on a massive iron throne, surrounded by conquered banners",
                "King Gwanggaeto",
                "low wooden ruler seat",
            ),
            (
                "A severed head of a king rolling onto a muddy battlefield",
                "fallen Baekje royal helmet",
                "broken plain war banner",
            ),
            (
                "Sparks flying violently in the pitch dark from the clash of heavy iron weapons",
                "Goguryeo armored soldiers",
                "torchlit packed-earth courtyard",
            ),
            (
                "A faint glint of a freshly sharpened blade shining weakly in the pitch black",
                "King Jangsu",
                "stone whetstone",
            ),
            (
                "A thick, tight rope snapping violently in extreme slow motion",
                "blank sealed treaty bundle",
                "Goguryeo and Later Yan envoys",
            ),
            (
                "A dark cloud of arrows descending violently upon the retreating army",
                "Goguryeo archers",
                "retreating Later Yan soldiers",
            ),
            (
                "An ancient scroll unrolling, revealing perfectly neat, golden calligraphy",
                "blank wooden record tablet bundle",
                "plain bronze weights",
            ),
            (
                "A beautiful vase shattering violently into countless dangerous pieces",
                "shattered plain clay storage jar",
                "packed earth",
            ),
        ]
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
            },
            "cuts": [
                {
                    "cut_number": idx,
                    "narration": "test",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_subject": scene.split(",", 1)[0].removeprefix("A ").removeprefix("An "),
                    "visual_scene": scene,
                }
                for idx, (scene, _subject, _expected) in enumerate(cases, 1)
            ],
        }

        applied = apply_script_visual_policy(script)

        for idx, (_scene, subject, expected) in enumerate(cases, 1):
            with self.subTest(idx=idx):
                cut = applied["cuts"][idx - 1]
                self.assertEqual(cut["visual_subject"], subject)
                self.assertIn(expected, cut["visual_scene"])
                self.assertNotRegex(cut["image_prompt"], r"\bChinese\b|fairy[- ]tale|stone wheel|tiered castle keep|massive,|iron throne|heavy crown|crown case|severed head|pitch black|golden calligraphy|rope snapping|beautiful vase")

    def test_visual_policy_uses_scene_subject_for_goguryeo_named_rival(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
            },
            "cuts": [
                {
                    "cut_number": 11,
                    "narration": "후연의 새로운 지배자 모용성이 이빨을 드러냅니다.",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_period": "402~410년 고구려사 흐름",
                    "visual_location": "요하, 북방",
                    "visual_subject": "광개토대왕",
                    "visual_scene": "A fierce warlord, Murong Sheng, drawing his sword with a cruel glare",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]
        prompt = cut["image_prompt"]

        self.assertEqual(cut["visual_subject"], "Murong Sheng")
        self.assertIn("Main subject: Murong Sheng", prompt)
        self.assertNotIn("Main subject: King Gwanggaeto", prompt)

    def test_visual_policy_does_not_collapse_all_eulji_cuts_to_river_command_mat(self):
        script = {
            "visual_world": {
                "time_range": "612year 6~7",
                "place_scope": "ancient Northeast Asia, Goguryeo-related court and frontier settings",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian political and military world",
                "material_culture": "iron weapons, bows, lamellar armor, river crossings, low hills",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "권력자의 탐욕이 부른 전쟁입니다.",
                    "image_prompt": "Scene: A dark, blood-stained map of East Asia, gritty and cinematic",
                    "visual_year": "612년 6~7월",
                    "visual_period": "612년 6~7월 고구려사 흐름",
                    "visual_location": "평양성 밖",
                    "visual_evidence": "핵심인물=을지문덕",
                    "visual_subject": "을지문덕",
                    "visual_scene": "A dark, blood-stained map of East Asia, gritty and cinematic",
                },
                {
                    "cut_number": 2,
                    "narration": "별동대가 내륙으로 들어갑니다.",
                    "image_prompt": "Scene: The Sui army marching deeper into a dark, foreboding valley",
                    "visual_year": "612년 6~7월",
                    "visual_period": "612년 6~7월 고구려사 흐름",
                    "visual_location": "평양성 밖",
                    "visual_evidence": "핵심인물=을지문덕",
                    "visual_subject": "을지문덕",
                    "visual_scene": "The Sui army marching deeper into a dark, foreboding valley",
                },
                {
                    "cut_number": 3,
                    "narration": "살수의 결과가 남습니다.",
                    "image_prompt": "Scene: The word 'Salsu' carved deeply into a bloody, wet stone monument",
                    "visual_year": "612년 6~7월",
                    "visual_period": "612년 6~7월 고구려사 흐름",
                    "visual_location": "평양성 밖",
                    "visual_evidence": "핵심인물=을지문덕",
                    "visual_subject": "을지문덕",
                    "visual_scene": "The word 'Salsu' carved deeply into a bloody, wet stone monument",
                },
            ],
        }

        applied = apply_script_visual_policy(script)
        scenes = [cut["visual_scene"] for cut in applied["cuts"]]
        subjects = [cut["visual_subject"] for cut in applied["cuts"]]

        self.assertEqual(len(set(scenes)), 3)
        self.assertEqual(len({cut["image_prompt"] for cut in applied["cuts"]}), 3)
        self.assertEqual(inspect_script_quality(applied, "적의 심장부를 농락한 5언시, 을지문덕"), [])
        self.assertNotIn("Eulji Mundeok stands at an outdoor riverbank command mat", scenes[0])
        self.assertNotIn("Eulji Mundeok stands at an outdoor riverbank command mat", scenes[1])
        self.assertIn("Unmarked blood-stained river stone", scenes[2])
        self.assertEqual(subjects[0], "Eulji Mundeok")
        self.assertIn("Sui army", subjects[1])

    def test_visual_policy_converts_goguryeo_eye_metaphor_to_period_scene(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
            },
            "cuts": [
                {
                    "cut_number": 120,
                    "narration": "광개토대왕은 권력의 섭리를 이해했습니다.",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_subject": "광개토대왕",
                    "visual_scene": "A close-up of Gwanggaeto's sharp, calculating eyes reflecting a burning fortress",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertEqual(cut["visual_subject"], "King Gwanggaeto")
        self.assertIn("watching a burning frontier fortress", cut["visual_scene"])
        self.assertNotIn("eyes reflecting", cut["image_prompt"])

    def test_visual_policy_moves_goguryeo_bowing_ruler_scene_outside(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian military world",
            },
            "cuts": [
                {
                    "cut_number": 119,
                    "narration": "공포와 전시 상황이 독재를 정당화했습니다.",
                    "image_prompt": "",
                    "visual_year": "402~410년",
                    "visual_subject": "king standing proudly in full armor",
                    "visual_scene": "A king standing proudly in full armor, while his starving people bow in fear",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertIn("open packed-earth courtyard", cut["visual_scene"])
        self.assertIn("blank palisade stakes", cut["visual_scene"])
        self.assertNotIn("full armor, while his starving people", cut["image_prompt"])

    def test_visual_policy_preserves_year_and_place_prefix_before_storage(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "test",
                    "image_prompt": "Toyotomi Hideyoshi standing near a dark sea",
                    "visual_year": "c. 1590-1592",
                    "visual_period": "Late Sengoku period, Toyotomi Hideyoshi rule",
                    "visual_location": "Hizen Nagoya Castle area, northern Kyushu coast, exterior",
                    "visual_evidence": "pre-invasion pressure",
                }
            ]
        }

        applied = apply_script_visual_policy(script)
        prompt = applied["cuts"][0]["image_prompt"]

        self.assertIn("Year/period: c. 1590-1592; Late Sengoku period", prompt)
        self.assertIn("Exact place: Hizen Nagoya Castle area, northern Kyushu coast, exterior", prompt)
        self.assertIn("Scene: stylish medium-close entrance of Toyotomi Hideyoshi", prompt)

    def test_visual_policy_forces_character_introduction_cut_to_stylish_closeup(self):
        script = {
            "visual_world": {
                "time_range": "1592",
                "place_scope": "Toyotomi command world before the Joseon invasion",
                "culture_scope": "Late Sengoku and early Toyotomi administration",
            },
            "scene_blocks": [
                {
                    "block_id": 2,
                    "cut_range": "11-20",
                    "character_introductions": [
                        {
                            "cut_number": "12",
                            "name": "도요토미 히데요시",
                            "explanation_goal": "조선 침략 결정을 밀어붙이는 권력자",
                        }
                    ],
                }
            ],
            "cuts": [
                {
                    "cut_number": 12,
                    "narration": "히데요시는 다음 전쟁의 방향을 자기 권력과 연결했습니다.",
                    "image_prompt": "",
                    "visual_year": "1592",
                    "visual_period": "Late Sengoku period, Toyotomi rule",
                    "visual_location": "Hizen Nagoya Castle command area",
                    "visual_evidence": "Hideyoshi's invasion planning pressure",
                    "visual_subject": "distant command building",
                    "visual_scene": "a wide command building stands beyond a dark courtyard",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertEqual(cut["visual_subject"], "Toyotomi Hideyoshi")
        self.assertIn("stylish medium-close entrance of Toyotomi Hideyoshi", cut["visual_scene"])
        self.assertIn("intense eyes", cut["visual_scene"])
        self.assertIn("dramatic rim light", cut["visual_scene"])
        self.assertIn("face, eyes, readable emotion", cut["visual_evidence"])
        self.assertIn("Main subject: Toyotomi Hideyoshi", cut["image_prompt"])

    def test_visual_policy_forces_adult_female_introduction_cut_to_charismatic_closeup(self):
        script = {
            "scene_blocks": [
                {
                    "block_id": 4,
                    "cut_range": "31-40",
                    "character_introductions": [
                        {
                            "cut_number": "32",
                            "name": "Queen Seondeok",
                            "explanation_goal": "adult woman ruler facing a dangerous council choice",
                        }
                    ],
                }
            ],
            "cuts": [
                {
                    "cut_number": 32,
                    "narration": "선덕 여왕의 판단은 궁정 안의 압박 속에서 드러났습니다.",
                    "image_prompt": "",
                    "visual_year": "seventh century",
                    "visual_period": "Silla royal court",
                    "visual_location": "royal council chamber",
                    "visual_evidence": "court decision pressure",
                    "visual_subject": "empty council chamber",
                    "visual_scene": "wooden pillars frame a quiet empty chamber under lamplight",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertEqual(cut["visual_subject"], "Queen Seondeok")
        self.assertIn("adult woman with attractive charisma", cut["visual_scene"])
        self.assertIn("confident eyes", cut["visual_scene"])
        self.assertIn("tasteful mature styling", cut["visual_evidence"])
        self.assertNotRegex(cut["image_prompt"].lower(), r"\b(?:nude|naked|cleavage|underage|childlike)\b")

    def test_visual_policy_forces_joseon_seonjo_introduction_cut_to_closeup(self):
        script = {
            "scene_blocks": [
                {
                    "block_id": 2,
                    "cut_range": "11-20",
                    "character_introductions": [
                        {
                            "cut_number": "12",
                            "name": "宣祖",
                            "explanation_goal": "Joseon king leaving the capital under invasion pressure",
                        }
                    ],
                }
            ],
            "cuts": [
                {
                    "cut_number": 12,
                    "narration": "宣祖は都を離れる判断を迫られました。",
                    "image_prompt": "",
                    "visual_year": "1592",
                    "visual_period": "Joseon during the Imjin War",
                    "visual_location": "Hanseong royal court",
                    "visual_evidence": "court evacuation pressure",
                    "visual_subject": "empty palace corridor",
                    "visual_scene": "a quiet palace corridor stretches behind closed wooden doors",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]

        self.assertEqual(cut["visual_subject"], "King Seonjo of Joseon")
        self.assertIn("stylish medium-close entrance of King Seonjo of Joseon", cut["visual_scene"])
        self.assertIn("Main subject: King Seonjo of Joseon", cut["image_prompt"])

    def test_visual_policy_does_not_duplicate_compiled_visual_context(self):
        script = {
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "test",
                    "image_prompt": "",
                    "visual_year": "1591",
                    "visual_period": "Late Sengoku period",
                    "visual_location": "Hizen Nagoya Castle",
                    "visual_evidence": "planning pressure",
                    "visual_subject": "Toyotomi envoy",
                    "visual_scene": "officials point at a blank coastal map",
                }
            ]
        }

        strengthened = BaseLLMService.strengthen_visual_context(script, {})
        applied = apply_script_visual_policy(strengthened)
        prompt = applied["cuts"][0]["image_prompt"]

        self.assertEqual(prompt.count("Year/period:"), 1)
        self.assertEqual(prompt.count("Exact place:"), 1)
        self.assertEqual(prompt.count("Scene evidence:"), 1)
        self.assertEqual(prompt.count("Style:"), 1)
        self.assertEqual(prompt.count("Main subject:"), 1)

    def test_visual_policy_does_not_reintroduce_non_english_metadata(self):
        script = {
            "visual_world": {
                "time_range": "402~410년",
                "place_scope": "ancient Northeast Asia, Goguryeo frontier",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "test",
                    "image_prompt": "Scene: A Goguryeo cavalry commander watches a river crossing",
                    "visual_year": "402~410년",
                    "visual_period": "402~410년 고구려사 흐름",
                    "visual_location": "요하, 북방",
                    "visual_evidence": "큐시트 연도=402~410년; 배경=요하, 북방",
                    "visual_subject": "광개토대왕",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        prompt = applied["cuts"][0]["image_prompt"]

        self.assertNotRegex(prompt, r"[가-힣一-龥ぁ-んァ-ン]")
        self.assertIn("Year/period: 402-410 AD", prompt)
        self.assertIn("Scene: A Goguryeo cavalry commander watches", prompt)

    def test_visual_policy_drops_conflicting_612_period_from_645_liaodong_prompt(self):
        prompt = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, bows, leather armor, lamellar armor, hemp garments, wooden halls, "
            "fortress walls, river crossings, horses; Continuity rule: period materials only; "
            "Year/period: 645 AD; Sui-Goguryeo war, 612 AD; Exact place: Liaodong Fortress; "
            "Main subject: Tang siege troops; Scene: Tang siege towers approach the Liaodong Fortress wall"
        )

        normalized = normalize_cut_image_prompt(
            prompt,
            "Tang Taizong attacks Liaodong Fortress.",
            "Tang Taizong's 645 Liaodong campaign",
        )

        self.assertIn("Year/period: 645 AD", normalized)
        self.assertIn("Liaodong Fortress", normalized)
        self.assertIn("Tang siege towers", normalized)
        self.assertNotIn("612 AD", normalized)
        self.assertNotIn("Sui-Goguryeo", normalized)
        self.assertNotIn("open river battlefield", normalized)

    def test_visual_context_drops_conflicting_visual_period_year(self):
        script = {
            "visual_world": {
                "time_range": "645year",
                "place_scope": "Liaodong Fortress, Liaodong",
                "culture_scope": "Goguryeo and Tang military world",
                "material_culture": "iron weapons, bows, lamellar armor, hemp garments, wooden halls, fortress walls",
            },
            "cuts": [
                {
                    "cut_number": 1,
                    "narration": "Tang pressure reaches Liaodong Fortress.",
                    "image_prompt": "",
                    "visual_year": "645 AD",
                    "visual_period": "Sui-Goguryeo war, 612 AD",
                    "visual_location": "Liaodong Fortress",
                    "visual_evidence": "Tang siege pressure against Goguryeo walls",
                    "visual_subject": "Tang siege troops",
                    "visual_scene": "Tang siege towers approach the Liaodong Fortress wall",
                }
            ],
        }

        strengthened = BaseLLMService.strengthen_visual_context(copy.deepcopy(script), {})
        applied = apply_script_visual_policy(strengthened)
        cut = applied["cuts"][0]
        prompt = cut["image_prompt"]

        self.assertEqual(cut["visual_period"], "")
        self.assertIn("Year/period: 645 AD", prompt)
        self.assertIn("Liaodong Fortress", prompt)
        self.assertNotIn("612 AD", prompt)
        self.assertNotIn("Sui-Goguryeo", prompt)
        self.assertNotIn("open river battlefield", prompt)

    def test_visual_policy_repairs_existing_612_river_drift_in_645_liaodong_prompt(self):
        prompt = (
            "Global visual world: Time range: 645year; "
            "Place scope: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, riverbank mud, cold water; "
            "Continuity rule: outdoor river battlefield; Year/period: 645 AD; Sui-Goguryeo war, 612 AD; "
            "Exact place: 612 Goguryeo-Sui open river battlefield, muddy river crossing; "
            "Scene evidence: open river water, muddy banks, exhausted Sui soldiers; "
            "Main subject: Sui soldiers; Scene: Exhausted Sui soldiers struggle across a cold open river crossing"
        )

        normalized = normalize_cut_image_prompt(
            prompt,
            "Tang army begins crossing the Liao River toward Liaodong Fortress.",
            "Tang Taizong's 645 Liaodong campaign",
        )

        self.assertIn("Year/period: 645 AD", normalized)
        self.assertIn("Tang-Goguryeo Liaodong campaign", normalized)
        self.assertIn("Liao River crossing toward Liaodong Fortress", normalized)
        self.assertIn("Tang soldiers cross the wide muddy Liao River", normalized)
        self.assertNotIn("612 AD", normalized)
        self.assertNotIn("Sui soldiers", normalized)
        self.assertNotIn("Goguryeo-Sui", normalized)
        self.assertNotIn("Sui-Goguryeo", normalized)
        self.assertNotIn("open river battlefield", normalized)

    def test_visual_policy_repairs_645_tang_prompt_with_stale_emperor_yang_subject(self):
        prompt = (
            "Global visual world: Time range: 645year; Place scope: Liaodong Fortress, Liaodong; "
            "Culture scope: Goguryeo and neighboring ancient Northeast Asian political and military world; "
            "Material culture: iron weapons, bows, lamellar armor, hemp garments, wooden halls; "
            "Year/period: 645 AD; Sui-Goguryeo war, 612 AD; Exact place: Liaodong Fortress; "
            "Main subject: Emperor Yang of Sui; "
            "Scene: stylish medium-close entrance of Emperor Yang of Sui, intense eyes"
        )

        normalized = normalize_cut_image_prompt(
            prompt,
            "This gruesome regicide provoked Tang.",
            "Tang Taizong's 645 Liaodong campaign",
        )

        self.assertIn("Year/period: 645 AD", normalized)
        self.assertIn("Tang Taizong and court officials", normalized)
        self.assertIn("sealed border report", normalized)
        self.assertNotIn("612 AD", normalized)
        self.assertNotIn("Sui-Goguryeo", normalized)
        self.assertNotIn("Goguryeo-Sui", normalized)
        self.assertNotIn("Emperor Yang of Sui", normalized)

    def test_visual_policy_removes_readable_text_scene_requests(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress; "
            "Continuity rule: no readable text; Scene: The word 'Salsu' carved deeply "
            "into a bloody stone monument"
        )

        normalized = normalize_cut_image_prompt(prompt, "살수대첩입니다.")

        self.assertNotIn("word", normalized.lower())
        self.assertNotIn("Liaodong Fortress", normalized)
        self.assertIn("open river battlefield", normalized)
        self.assertIn("unmarked blood-stained river stone", normalized.lower())
        self.assertIn("muddy open riverbank", normalized)

    def test_visual_policy_converts_poem_to_blank_period_object(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress; "
            "Continuity rule: no readable text; Scene: The famous five-word poem "
            "unrolled on a wooden table"
        )

        normalized = normalize_cut_image_prompt(prompt, "역사적인 오언시가 꽂힌 겁니다.")

        self.assertNotIn("five-word poem", normalized)
        self.assertNotIn("Liaodong Fortress", normalized)
        self.assertIn("outdoor riverbank command mat", normalized)
        self.assertIn("blank bamboo slips", normalized)

    def test_visual_policy_keeps_eulji_command_scene_despite_episode_word_context(self):
        prompt = (
            "Global visual world: Time range: 612year 6~7; Place scope: ancient Northeast Asia, "
            "Goguryeo-related court and frontier settings; Culture scope: Goguryeo and neighboring "
            "ancient Northeast Asian political and military world; Material culture: iron weapons, bows, "
            "lamellar armor, hemp garments, riverbank mud, cold water, broken spear shafts; "
            "Year/period: 612 AD; Sui-Goguryeo war, 612 AD; Exact place: 612 Goguryeo-Sui open river battlefield, "
            "muddy river crossing; Scene evidence: open river water, muddy banks, broken spear shafts, "
            "torn lamellar armor, exhausted Sui soldiers, Goguryeo pressure from the bank, open sky, low hills; "
            "Main subject: Eulji Mundeok; Scene: Eulji Mundeok stands at an outdoor riverbank command mat "
            "with closed cord-tied bamboo slip packets, blank bamboo slips, brush resting aside, "
            "Goguryeo officers, cold river water behind them, muddy bank, low hills, and dusk wind"
        )

        normalized = normalize_cut_image_prompt(
            prompt,
            "고구려군은 적과 마주칠 때마다 무기력하게 패배하며 계속 달아났죠.",
            "적의 심장부를 농락한 5언시, 을지문덕",
        )

        self.assertIn("Eulji Mundeok stands at an outdoor riverbank command mat", normalized)
        self.assertIn("blank bamboo slips", normalized)
        self.assertNotIn("blood-stained river stone", normalized)
        self.assertNotIn("stone monument", normalized)

    def test_visual_policy_prevents_modern_vehicle_carriage_drift(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress; "
            "Scene: The Chinese emperor's carriage stuck in deep, freezing mud"
        )

        normalized = normalize_cut_image_prompt(prompt, "진흙탕 속에 갇혀 도망칩니다.")

        self.assertNotIn("carriage", normalized.lower())
        self.assertNotIn("Liaodong Fortress", normalized)
        self.assertIn("animal-drawn open wooden command cart", normalized)
        self.assertIn("deep muddy open ground near a riverbank", normalized)

    def test_visual_policy_concretizes_sky_strategy_metaphor(self):
        prompt = (
            "Global visual world: Time range: 612year; Place scope: Liaodong Fortress; "
            "Scene: A glowing, sarcastic illustration of a tactical genius in the sky"
        )

        normalized = normalize_cut_image_prompt(prompt, "하늘의 이치를 꿰뚫었습니다.")

        self.assertNotIn("in the sky", normalized)
        self.assertNotIn("Liaodong Fortress", normalized)
        self.assertIn("outdoor riverbank command mat", normalized)
        self.assertIn("blank bamboo slips", normalized)

    def test_visual_policy_routes_salsu_cut_away_from_liaodong_fortress(self):
        script = {
            "visual_world": {
                "time_range": "612year",
                "place_scope": "Liaodong Fortress, Liaodong",
                "culture_scope": "Goguryeo and neighboring ancient Northeast Asian political and military world",
                "material_culture": "Iron weapons, bows, leather armor, lamellar armor, hemp garments, wooden halls, fortress walls, river crossings, horses",
                "continuity_rule": "Every scene stays in an ancient Northeast Asian setting. No readable text.",
            },
            "cuts": [
                {
                    "cut_number": 145,
                    "narration": "제국의 오만을 강물에 묻어버린 고구려 최강의 전략, 살수대첩입니다.",
                    "image_prompt": "Scene: The word 'Salsu' carved deeply into a bloody stone monument",
                    "visual_year": "612년",
                    "visual_period": "612년 고구려사 흐름",
                    "visual_location": "요동성",
                    "visual_evidence": "큐시트 연도=612년; 배경=요동성",
                    "visual_subject": "수 양제",
                    "visual_scene": "The word 'Salsu' carved deeply into a bloody stone monument",
                }
            ],
        }

        applied = apply_script_visual_policy(script)
        cut = applied["cuts"][0]
        prompt = cut["image_prompt"]

        self.assertIn("open river battlefield", prompt)
        self.assertIn("muddy river crossing", prompt)
        self.assertNotIn("Liaodong Fortress", prompt)
        self.assertNotIn("wooden halls", prompt)
        self.assertNotIn("fortress walls", prompt)
        self.assertNotIn("word 'Salsu'", prompt)

    def test_visual_policy_caps_modern_archive_scenes_for_classical_japan(self):
        script = {
            "title": "万葉集はなぜ古代の声なのか",
            "description": "奈良時代と古代日本の和歌を扱います。",
            "cuts": [
                {
                    "cut_number": idx,
                    "narration": "記録と伝承を分けて見ることが大切です",
                    "image_prompt": "",
                    "visual_year": "c. 2020-2024",
                    "visual_period": "Contemporary Japan, manuscript research",
                    "visual_location": "modern archive reading room in Japan",
                    "visual_evidence": "modern researcher comparison",
                    "visual_subject": "modern researcher handling a manuscript reproduction",
                    "visual_scene": "A researcher compares facsimile copies at a modern archive table",
                }
                for idx in range(1, 7)
            ],
        }

        applied = apply_script_visual_policy(script)
        prompts = [cut["image_prompt"] for cut in applied["cuts"]]
        modern_count = sum(
            1
            for prompt in prompts
            if "2020" in prompt
            or "Contemporary Japan" in prompt
            or "modern researcher" in prompt
        )

        self.assertLessEqual(modern_count, 1)
        self.assertIn("Nara period manuscript compilation", prompts[-1])


if __name__ == "__main__":
    unittest.main()
