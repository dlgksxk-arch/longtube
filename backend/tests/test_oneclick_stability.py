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
from app.services.tts import narration_fit  # noqa: E402
from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts  # noqa: E402
from app.services import shorts_service  # noqa: E402
from app.services import subtitle_service  # noqa: E402
from app.services import youtube_service  # noqa: E402
from app import config as app_config  # noqa: E402
from app.services.title_utils import shorts_upload_title  # noqa: E402
from app.services.image import prompt_builder  # noqa: E402
from app.services.thumbnail_service import (  # noqa: E402
    build_standard_thumbnail_prompt,
    extract_thumbnail_text_parts,
)
from app.services.image.comfyui_service import (  # noqa: E402
    apply_longtube_local_v1_master_prompt,
    build_longtube_local_v1_negative_prompt,
    _enrich_local_v1_positive_prompt,
    _strip_local_v1_positive_only_prompt,
)
from app.services.llm.base import BaseLLMService, get_system_prompt  # noqa: E402
from app.services.llm.visual_policy import apply_script_visual_policy, normalize_cut_image_prompt  # noqa: E402
from app.services.llm.script_quality import inspect_script_quality  # noqa: E402
from app.routers import interlude as interlude_router  # noqa: E402
from app.routers import script as script_router  # noqa: E402
from app.routers import channel_ops as channel_ops_router  # noqa: E402
from app.routers.projects import DEFAULT_CONFIG  # noqa: E402
from app.routers import subtitle as subtitle_router  # noqa: E402
from app.services.interlude_service import DEFAULT_INTERMISSION_EVERY  # noqa: E402
from app.tasks import pipeline_tasks  # noqa: E402


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
        self.assertEqual(cfg["script_tts_target_sec"], 4.0)
        self.assertEqual(cfg["script_tts_tolerance_sec"], 0.2)

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
        self.assertIn("중요 인물 계약", prompt_source)
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
        self.assertIn("정확히 4편의 쇼츠", prompt_source)
        self.assertIn("각 쇼츠 그룹은 정확히 15개 컷", prompt_source)
        self.assertIn("총 60개 컷", prompt_source)
        self.assertIn("shorts_group 1: 논쟁 질문", prompt_source)
        self.assertIn("shorts_group 2: 충격 사실", prompt_source)
        self.assertIn("shorts_group 3: 롱폼으로 넘기는 미스터리", prompt_source)
        self.assertIn("shorts_group 4: 주요 인물 부각", prompt_source)
        self.assertIn("일반 설명 컷, 배경만 말하는 컷", prompt_source)
        self.assertIn("본편 흐름을 깨는 별도 쇼츠용 대사는 만들지 마세요", prompt_source)
        self.assertIn("첫 8~14글자", prompt_source)
        self.assertIn("구독 유도형 여운", prompt_source)
        self.assertIn("정보형 명사구 금지", prompt_source)
        self.assertIn("shorts_title", prompt_source)
        self.assertIn("visual_year", prompt_source)
        self.assertIn("image_prompt에는 긴 최종 프롬프트를 쓰지 말고", prompt_source)
        self.assertIn("최종 image_prompt는 백엔드가", prompt_source)

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
        self.assertIn("torso-only framing", fallback)
        self.assertIn("full visible face", request)
        self.assertIn("torso-only", request)
        self.assertIn("faceless silhouette", request)

    def test_four_second_video_uses_four_second_script_tts_window(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "ko",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(limits["target_min_sec"], 3.8)
        self.assertEqual(limits["target_sec"], 4.0)
        self.assertEqual(limits["target_max_sec"], 4.2)
        self.assertEqual(limits["target_range"], "38~42")

        ja_limits = BaseLLMService._calc_narration_limits({
            "language": "ja",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(ja_limits["target_min_sec"], 3.8)
        self.assertEqual(ja_limits["target_sec"], 4.0)
        self.assertEqual(ja_limits["target_max_sec"], 4.2)
        self.assertEqual(ja_limits["target_range"], "36~39")

    def test_eight_second_video_uses_eight_second_script_tts_window(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "en",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 8.0,
        })

        self.assertEqual(limits["target_min_sec"], 7.8)
        self.assertEqual(limits["target_sec"], 8.0)
        self.assertEqual(limits["target_max_sec"], 8.2)

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
        self.assertIn("clothing, hairstyle, headwear, armor, jewelry and accessories", guard)
        self.assertIn("tools, weapons", guard)
        self.assertIn("ritual objects, everyday objects", guard)
        self.assertIn("generic historical costume, fantasy costume, cosplay", guard)

    def test_historical_negative_prompt_blocks_wrong_era_costume_and_props(self):
        negative = prompt_builder.GENERAL_HISTORY_NEGATIVE_PROMPT

        self.assertIn("wrong-era hairstyle", negative)
        self.assertIn("wrong-era headwear", negative)
        self.assertIn("wrong-era tool", negative)
        self.assertIn("wrong-era jewelry", negative)
        self.assertIn("fantasy costume", negative)
        self.assertIn("cosplay", negative)

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
        self.assertIn("Style: simple cartoon illustration", prompt)
        self.assertIn("Main subject: Toyotomi envoy holding a sealed order", prompt)
        self.assertIn("Scene: tense officials lean over a blank campaign map", prompt)
        self.assertEqual(prompt.count("Style:"), 1)

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
        self.assertIn("Scene: Toyotomi Hideyoshi standing near a dark sea", prompt)

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
