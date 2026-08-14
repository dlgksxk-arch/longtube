from __future__ import annotations

import sys
import inspect
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import youtube_service  # noqa: E402
from app.services.youtube_publish_schedule import (  # noqa: E402
    next_main_publish_at,
    next_production_publish_schedule,
)


def test_production_schedule_uses_same_kst_day_before_first_slot():
    schedule = next_production_publish_schedule(datetime(2026, 8, 12, 8, 0))

    assert schedule["publish_date"] == "2026-08-12"
    assert schedule["main"] == "2026-08-12T09:00:00Z"
    assert schedule["shorts"] == [
        "2026-08-12T00:00:00Z",
        "2026-08-12T03:00:00Z",
        "2026-08-12T06:00:00Z",
        "2026-08-12T07:00:00Z",
    ]


def test_production_schedule_moves_complete_batch_to_next_day_after_0900():
    schedule = next_production_publish_schedule(datetime(2026, 8, 12, 9, 0))

    assert schedule["publish_date"] == "2026-08-13"
    assert schedule["main"] == "2026-08-13T09:00:00Z"
    assert schedule["shorts"][0] == "2026-08-13T00:00:00Z"


def test_standalone_main_upload_uses_next_1800_kst_slot():
    assert next_main_publish_at(datetime(2026, 8, 12, 17, 0)) == "2026-08-12T09:00:00Z"
    assert next_main_publish_at(datetime(2026, 8, 12, 17, 55)) == "2026-08-13T09:00:00Z"


def test_upload_sends_private_publish_at_in_insert(monkeypatch, tmp_path):
    captured = {}

    class FakeRequest:
        def next_chunk(self, num_retries=0):
            return None, {"id": "scheduled-video"}

    class FakeVideos:
        def insert(self, *, part, body, media_body):
            captured["part"] = part
            captured["body"] = body
            return FakeRequest()

    class FakeYouTube:
        def videos(self):
            return FakeVideos()

    video = tmp_path / "video.mp4"
    video.write_bytes(b"test")
    monkeypatch.setattr(youtube_service, "_wait_for_upload_media_ready", lambda _path: None)
    monkeypatch.setattr(youtube_service, "MediaFileUpload", lambda *args, **kwargs: object())

    uploader = youtube_service.YouTubeUploader()
    uploader.youtube = FakeYouTube()
    uploader.ensure_upload_top_comment = lambda **kwargs: {"status": "skipped"}
    result = uploader.upload(
        str(video),
        "Scheduled title",
        "Description",
        privacy="public",
        publish_at="2026-08-13T09:00:00Z",
    )

    assert captured["part"] == "snippet,status"
    assert captured["body"]["status"]["privacyStatus"] == "private"
    assert captured["body"]["status"]["publishAt"] == "2026-08-13T09:00:00Z"
    assert result["privacy_status"] == "private"
    assert result["publish_at"] == "2026-08-13T09:00:00Z"


def test_every_current_application_upload_entry_passes_publish_at():
    from app.routers import youtube as youtube_router
    from app.services import oneclick_service, scheduler_service
    from app.tasks import pipeline_tasks

    assert inspect.getsource(oneclick_service._step_youtube_upload).count("publish_at=") == 2
    assert inspect.getsource(pipeline_tasks._step_upload).count("publish_at=") == 2
    assert inspect.getsource(scheduler_service._run_episode).count("publish_at=") == 1
    assert inspect.getsource(youtube_router.upload_to_youtube).count("publish_at=") == 1
