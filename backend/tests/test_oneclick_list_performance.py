"""Regression tests for the lightweight OneClick task-list hot path."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import oneclick_service as svc  # noqa: E402


class OneClickListPerformanceTests(unittest.TestCase):
    def test_cached_progress_does_not_touch_image_files(self):
        task = {
            "project_id": "completed-project",
            "status": "completed",
            "total_cuts": 10,
            "step_states": {"2": "completed", "3": "completed", "4": "completed"},
            "completed_cuts_by_step": {"2": 10, "3": 10, "4": 10},
        }

        with mock.patch.object(svc, "_count_committed_cut_images") as count_images:
            progress = svc._compute_progress_pct(task, verify_outputs=False)

        self.assertGreater(progress, 0)
        count_images.assert_not_called()

    def test_startup_does_not_rescan_terminal_outputs(self):
        payload = {
            "completed-task": {
                "task_id": "completed-task",
                "project_id": "completed-project",
                "status": "completed",
                "config": {},
            },
            "failed-task": {
                "task_id": "failed-task",
                "project_id": "failed-project",
                "status": "failed",
                "config": {},
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            task_file = Path(temp_dir) / "oneclick_tasks.json"
            task_file.write_text(json.dumps(payload), encoding="utf-8")
            with (
                mock.patch.dict(svc._TASKS, {}, clear=True),
                mock.patch.object(svc, "_TASKS_FILE", task_file),
                mock.patch.object(svc, "_project_storage_exists", return_value=True),
                mock.patch.object(svc, "_reconcile_task_outputs") as reconcile_outputs,
                mock.patch.object(svc, "_restore_executed_models_from_logs", return_value=False),
                mock.patch.object(svc, "_dedupe_tasks", return_value=False),
                mock.patch.object(svc, "_tasks_file_mtime_ns", return_value=1),
                mock.patch.object(svc, "_save_tasks_to_disk"),
            ):
                svc._load_tasks_from_disk()

        reconcile_outputs.assert_not_called()

    def test_list_tasks_does_not_rescan_terminal_outputs(self):
        task = {
            "task_id": "completed-task",
            "project_id": "completed-project",
            "status": "completed",
            "created_at": "2026-08-04T00:00:00Z",
            "step_states": {"2": "completed", "3": "completed"},
            "progress_pct": 100.0,
        }

        with (
            mock.patch.dict(svc._TASKS, {task["task_id"]: task}, clear=True),
            mock.patch.object(svc, "_ensure_state_loaded"),
            mock.patch.object(svc, "_refresh_tasks_from_disk_if_newer"),
            mock.patch.object(svc, "_dedupe_tasks", return_value=False),
            mock.patch.object(svc, "_drop_tasks_without_project_rows", return_value=False),
            mock.patch.object(svc, "_sync_completed_projects_into_tasks", return_value=False) as sync_completed,
            mock.patch.object(svc, "_mark_stale_inflight_tasks", return_value=False),
            mock.patch.object(svc, "_reconcile_task_outputs") as reconcile_outputs,
            mock.patch.object(svc, "_restore_executed_models_from_logs", return_value=False),
            mock.patch.object(svc, "_compute_progress_pct", return_value=100.0),
            mock.patch.object(svc, "_is_externally_managed_task", return_value=True),
            mock.patch.object(svc, "_save_tasks_to_disk"),
        ):
            result = svc.list_tasks()

        self.assertEqual([row["task_id"] for row in result], ["completed-task"])
        sync_completed.assert_called_once_with(verify_outputs=False)
        reconcile_outputs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
