import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.youtube_service import (  # noqa: E402
    YouTubeUploader,
    build_upload_top_comment,
    prepare_youtube_thumbnail_upload_path,
)


class _Request:
    def __init__(self, response):
        self.response = response

    def execute(self):
        return self.response


class _Videos:
    def __init__(self):
        self.update_body = None
        self.update_part = None

    def list(self, **kwargs):
        return _Request({
            "items": [{
                "id": "video-1",
                "snippet": {
                    "title": "English title",
                    "description": "English description",
                    "tags": ["European history"],
                    "categoryId": "27",
                    "defaultLanguage": "en",
                    "defaultAudioLanguage": "en",
                },
                "localizations": {
                    "fr": {"title": "Ancien", "description": "Ancienne description"},
                },
            }]
        })

    def update(self, *, part, body):
        self.update_part = part
        self.update_body = body
        return _Request({"id": body["id"], "localizations": body["localizations"]})


class _YouTube:
    def __init__(self):
        self.videos_api = _Videos()

    def videos(self):
        return self.videos_api


class _Channels:
    def list(self, **kwargs):
        return _Request({
            "items": [{
                "id": "channel-1",
                "snippet": {"title": "Channel", "thumbnails": {}},
                "statistics": {},
            }]
        })


class _CommentThreads:
    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.insert_body = None

    def list(self, **kwargs):
        return _Request({"items": self.existing})

    def insert(self, *, part, body):
        self.insert_body = body
        text = body["snippet"]["topLevelComment"]["snippet"]["textOriginal"]
        return _Request({
            "id": "thread-1",
            "snippet": {
                "topLevelComment": {
                    "id": "comment-1",
                    "snippet": {"textDisplay": text},
                }
            },
        })


class _YouTubeComments:
    def __init__(self, existing=None):
        self.channels_api = _Channels()
        self.comment_threads_api = _CommentThreads(existing)

    def channels(self):
        return self.channels_api

    def commentThreads(self):
        return self.comment_threads_api


class YouTubeServiceLocalizationTests(unittest.TestCase):
    def test_upload_comment_templates_follow_channel_language(self):
        korean = build_upload_top_comment("백제의 건국", "ko")
        english = build_upload_top_comment("The Fall of Rome", "en-US")
        japanese = build_upload_top_comment("ヤマタノオロチ", "ja")

        self.assertTrue(korean.startswith("이번 편은 백제의 건국을 주제로"))
        self.assertIn("구독과 좋아요, 알림설정", korean)
        self.assertTrue(english.startswith("This episode explores The Fall of Rome."))
        self.assertIn("subscribing, liking, and turning on notifications", english)
        self.assertTrue(japanese.startswith("今回は「ヤマタノオロチ」をテーマにした物語です。"))
        self.assertIn("チャンネル登録、高評価、通知設定", japanese)

    def test_ensure_top_level_comment_inserts_channel_owned_comment(self):
        uploader = YouTubeUploader(channel_id=1)
        uploader.youtube = _YouTubeComments()

        result = uploader.ensure_top_level_comment("video-1", "백제의 건국", "ko")

        body = uploader.youtube.comment_threads_api.insert_body
        self.assertEqual(body["snippet"]["channelId"], "channel-1")
        self.assertEqual(body["snippet"]["videoId"], "video-1")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["comment_id"], "comment-1")
        self.assertFalse(result["already_present"])

    def test_ensure_top_level_comment_does_not_duplicate_existing_channel_comment(self):
        text = build_upload_top_comment("백제의 건국", "ko")
        existing = [{
            "id": "thread-existing",
            "snippet": {
                "topLevelComment": {
                    "id": "comment-existing",
                    "snippet": {
                        "authorChannelId": {"value": "channel-1"},
                        "authorDisplayName": "Channel",
                        "textDisplay": text,
                    },
                },
                "totalReplyCount": 0,
            },
        }]
        uploader = YouTubeUploader(channel_id=1)
        uploader.youtube = _YouTubeComments(existing)

        result = uploader.ensure_top_level_comment("video-1", "백제의 건국", "ko")

        self.assertTrue(result["already_present"])
        self.assertEqual(result["comment_id"], "comment-existing")
        self.assertIsNone(uploader.youtube.comment_threads_api.insert_body)

    def test_private_upload_records_comment_as_pending(self):
        uploader = YouTubeUploader(channel_id=1)

        result = uploader.ensure_upload_top_comment(
            video_id="video-1",
            topic="백제의 건국",
            language="ko",
            privacy="private",
            made_for_kids=False,
        )

        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["reason"], "private_video_comments_unavailable")

    def test_large_thumbnail_gets_youtube_safe_derivative_without_touching_source(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "thumbnail.png"
            image = Image.effect_noise((2560, 1440), 100).convert("RGB")
            image.save(source, "PNG")
            source_bytes = source.read_bytes()
            self.assertGreater(source.stat().st_size, 2_097_152)

            upload_path = prepare_youtube_thumbnail_upload_path(source)

            self.assertEqual(source.read_bytes(), source_bytes)
            self.assertEqual(upload_path.name, "thumbnail_youtube.jpg")
            self.assertLessEqual(upload_path.stat().st_size, 2_097_152)

    def test_set_video_localizations_merges_and_preserves_snippet(self):
        uploader = YouTubeUploader(channel_id=2)
        uploader.youtube = _YouTube()

        result = uploader.set_video_localizations(
            "video-1",
            {
                "es": {"title": "Titulo", "description": "Descripcion"},
                "de": {"title": "Titel", "description": "Beschreibung"},
            },
            default_language="en",
            default_audio_language="en",
        )

        body = uploader.youtube.videos_api.update_body
        self.assertEqual(uploader.youtube.videos_api.update_part, "snippet,localizations")
        self.assertEqual(body["snippet"]["title"], "English title")
        self.assertEqual(body["snippet"]["categoryId"], "27")
        self.assertEqual(body["snippet"]["defaultAudioLanguage"], "en")
        self.assertEqual(sorted(body["localizations"]), ["de", "es", "fr"])
        self.assertEqual(result["languages"], ["de", "es", "fr"])


if __name__ == "__main__":
    unittest.main()
