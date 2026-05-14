"""OneClick stability characterization tests.

These tests lock down small pure helpers before splitting the large
oneclick_service module further. They do not call external APIs or start jobs.
"""
import copy
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import oneclick_service as svc  # noqa: E402
from app.services.tts import narration_fit  # noqa: E402
from app.services import shorts_service  # noqa: E402
from app.services import subtitle_service  # noqa: E402
from app.services.image import prompt_builder  # noqa: E402
from app.services.image.comfyui_service import (  # noqa: E402
    apply_longtube_local_v1_master_prompt,
    build_longtube_local_v1_negative_prompt,
    _enrich_local_v1_positive_prompt,
    _strip_local_v1_positive_only_prompt,
)
from app.services.llm.base import BaseLLMService  # noqa: E402
from app.services.llm.visual_policy import apply_script_visual_policy  # noqa: E402
from app.routers import interlude as interlude_router  # noqa: E402
from app.routers import subtitle as subtitle_router  # noqa: E402
from app.services.interlude_service import DEFAULT_INTERMISSION_EVERY  # noqa: E402


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
        self.assertEqual(cfg["script_tts_target_sec"], 4.4)
        self.assertEqual(cfg["script_tts_tolerance_sec"], 0.2)

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
            self.assertEqual([item["id"] for item in svc._QUEUE["items"]], ["active", "normal"])
            self.assertEqual(svc._QUEUE["items"][0]["status"], "running")
            self.assertEqual(svc._QUEUE["items"][0]["queued_note"], "실행 중")
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

    def test_uploading_task_keeps_queue_row_active_without_live_runner(self):
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
            self.assertTrue(svc._has_inflight_task())
            self.assertEqual(svc._QUEUE["items"][0]["status"], "running")
            self.assertEqual(svc._QUEUE["items"][0]["queued_note"], "실행 중")
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


class InterludeStabilityTests(unittest.TestCase):
    def test_default_interval_is_250_cuts_and_first_three_cut_insert_is_kept(self):
        self.assertEqual(DEFAULT_INTERMISSION_EVERY, 250)

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
        self.assertIn("수익창출이 최우선 목표인 유튜브 자동화 파이프라인용 대본 생성기", prompt_source)
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
        self.assertIn("정확히 4편의 쇼츠", prompt_source)
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
        self.assertIn("Year/period: c. 1590-1591; Exact place: a specific visible place", prompt_source)

    def test_four_second_video_keeps_script_tts_window_at_4_2_to_4_6(self):
        limits = BaseLLMService._calc_narration_limits({
            "language": "ko",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(limits["target_min_sec"], 4.2)
        self.assertEqual(limits["target_sec"], 4.4)
        self.assertEqual(limits["target_max_sec"], 4.6)
        self.assertEqual(limits["target_range"], "42~46")

        ja_limits = BaseLLMService._calc_narration_limits({
            "language": "ja",
            "tts_model": "elevenlabs",
            "tts_speed": 1.0,
            "cut_video_duration": 4.0,
        })

        self.assertEqual(ja_limits["target_min_sec"], 4.2)
        self.assertEqual(ja_limits["target_sec"], 4.4)
        self.assertEqual(ja_limits["target_max_sec"], 4.6)
        self.assertEqual(ja_limits["target_range"], "40~43")

    def test_tts_duration_status_treats_over_slot_audio_as_long(self):
        cfg = {"cut_video_duration": 4.0}

        self.assertEqual(narration_fit._duration_status(4.0, cfg), "slot_fit")
        self.assertEqual(narration_fit._duration_status(4.2, cfg), "long")
        self.assertEqual(narration_fit._duration_status(4.6, cfg), "long")
        self.assertEqual(narration_fit._duration_status(4.61, cfg), "too_long")


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

    def test_annotate_script_shorts_keeps_four_twelve_cut_groups(self):
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
        self.assertIn("image_prompt에 보이는 시대 증거를 적어야 합니다", prompt_source)
        self.assertIn("시대에 맞을 법한 평범한 사물", prompt_source)
        self.assertIn("가짜 문자, 가짜 한자, 가짜 서예", prompt_source)
        self.assertIn("visual_year는 정확한 보이는 연도", prompt_source)
        self.assertIn("visual_location은 일반 배경이 아니라 구체적인 공간", prompt_source)

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


if __name__ == "__main__":
    unittest.main()
