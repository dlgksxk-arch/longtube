from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.routers.video import (
    _cut_video_needs_regeneration,
    _restore_cut_media_paths_from_disk,
)


class VideoStaleDetectionTests(unittest.TestCase):
    def test_missing_db_media_paths_are_restored_from_committed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative in (
                "images/cut_1.png",
                "audio/cut_001.mp3",
                "videos/cut_1.mp4",
            ):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"data")

            cut = SimpleNamespace(
                cut_number=1,
                image_path=None,
                audio_path=None,
                video_path=None,
            )

            self.assertEqual(_restore_cut_media_paths_from_disk(root, [cut]), 3)
            self.assertEqual(cut.image_path, "images/cut_1.png")
            self.assertEqual(cut.audio_path, "audio/cut_001.mp3")
            self.assertEqual(cut.video_path, "videos/cut_1.mp4")

    def test_clip_regenerates_only_when_missing_or_older_than_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "images" / "cut_1.png"
            audio = root / "audio" / "cut_1.mp3"
            video = root / "videos" / "cut_1.mp4"
            for path in (image, audio, video):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"data")

            cut = SimpleNamespace(
                image_path="images/cut_1.png",
                audio_path="audio/cut_1.mp3",
                video_path="videos/cut_1.mp4",
            )
            os.utime(image, ns=(1_000_000_000, 1_000_000_000))
            os.utime(audio, ns=(1_000_000_000, 1_000_000_000))
            os.utime(video, ns=(2_000_000_000, 2_000_000_000))
            self.assertFalse(_cut_video_needs_regeneration(root, cut))

            os.utime(image, ns=(3_000_000_000, 3_000_000_000))
            self.assertTrue(_cut_video_needs_regeneration(root, cut))

            os.utime(image, ns=(1_000_000_000, 1_000_000_000))
            os.utime(audio, ns=(3_000_000_000, 3_000_000_000))
            self.assertTrue(_cut_video_needs_regeneration(root, cut))

            video.unlink()
            self.assertTrue(_cut_video_needs_regeneration(root, cut))

    def test_factory_v5_caption_mode_regenerates_previously_burned_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "images" / "cut_1.png"
            audio = root / "audio" / "cut_1.mp3"
            video = root / "videos" / "cut_1.mp4"
            marker = video.with_suffix(".subtitle.json")
            for path in (image, audio, video, marker):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"data")

            cut = SimpleNamespace(
                image_path="images/cut_1.png",
                audio_path="audio/cut_1.mp3",
                video_path="videos/cut_1.mp4",
            )
            config = {
                "factory_version": 5,
                "subtitle_delivery": "youtube_caption",
            }

            self.assertTrue(_cut_video_needs_regeneration(root, cut, config))
            marker.unlink()
            self.assertFalse(_cut_video_needs_regeneration(root, cut, config))
