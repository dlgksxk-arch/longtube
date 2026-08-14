import asyncio
from pathlib import Path

import pytest

from app.services import movie_review_service as service


def test_youtube_url_guard_accepts_youtube_and_rejects_other_hosts():
    assert service.validate_youtube_url("https://www.youtube.com/watch?v=abc123")
    assert service.validate_youtube_url("https://youtu.be/abc123")
    with pytest.raises(ValueError, match="YouTube"):
        service.validate_youtube_url("https://example.com/watch?v=abc123")


def test_subtitle_language_normalization_rejects_invalid_values():
    assert service.normalize_subtitle_languages(["ko", "ko", "en"]) == ["ko", "en"]
    with pytest.raises(ValueError, match="자막 언어"):
        service.normalize_subtitle_languages(["../../secret"])


@pytest.mark.asyncio
async def test_start_job_persists_work_unit_without_running_a_real_download(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._ACTIVE_TASKS.clear()
    service._JOB_DIR_CACHE.clear()
    monkeypatch.setattr(
        service,
        "_probe_source_metadata",
        lambda _url: {
            "id": "abc123",
            "title": "Test: Movie / Episode",
            "channel": "Test channel",
            "duration": 120,
        },
    )

    async def fake_run_job(job_id: str) -> None:
        service._update_manifest(
            job_id,
            status="ready",
            progress=100,
            message="test complete",
        )

    monkeypatch.setattr(service, "_run_job", fake_run_job)
    job = await service.start_job(
        source_url="https://www.youtube.com/watch?v=abc123",
        max_height=1080,
        subtitle_languages=["ko", "en"],
        rights_confirmed=True,
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    stored = service.get_job(job["job_id"])
    assert stored["status"] == "ready"
    assert stored["progress"] == 100
    assert Path(stored["output_dir"]).parent == tmp_path
    assert Path(stored["output_dir"]).name == "1. Test Movie Episode"
    assert stored["sequence_number"] == 1
    assert stored["shorts_layout"] == service.movie_shorts_layout_defaults()
    assert (Path(stored["output_dir"]) / "job.json").is_file()


def test_movie_shorts_layout_is_validated_and_persisted(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._JOB_DIR_CACHE.clear()
    job_id = "MR_20260812_120000_deadbeef"
    job_dir = tmp_path / "1. Test"
    job_dir.mkdir()
    service._JOB_DIR_CACHE[job_id] = job_dir
    service._write_manifest(
        {
            "job_id": job_id,
            "status": "ready",
            "created_at": "2026-08-12T12:00:00+00:00",
        }
    )

    layout = service.movie_shorts_layout_defaults()
    layout["title_center_x"] = 500
    layout["caption_font_size"] = 84
    layout["caption_outline_width"] = 10
    layout["movie_title_center_x"] = 520
    layout["channel_center_x"] = 560
    updated = service.update_shorts_layout(job_id, layout)

    assert updated["shorts_layout"]["layout_version"] == 2
    assert updated["shorts_layout"]["title_center_x"] == 500
    assert updated["shorts_layout"]["caption_font_size"] == 84
    assert updated["shorts_layout"]["caption_outline_width"] == 10
    assert updated["shorts_layout"]["movie_title_center_x"] == 520
    assert updated["shorts_layout"]["channel_center_x"] == 560
    assert service.get_job(job_id)["shorts_layout"]["caption_font_size"] == 84
    with pytest.raises(ValueError, match="영상 표현 구간 아래"):
        service.update_shorts_layout(job_id, {"caption_top": 1000})


def test_legacy_movie_shorts_layout_is_upgraded_to_four_text_layers():
    legacy = service.movie_shorts_layout_defaults()
    for key in (
        "layout_version",
        "title_center_x",
        "movie_title_top",
        "movie_title_center_x",
        "movie_title_font_size",
        "movie_title_color",
        "movie_title_outline_color",
        "movie_title_outline_width",
        "channel_center_x",
        "channel_color",
        "intertitle_text_top",
        "intertitle_text_center_x",
        "intertitle_outline_color",
        "intertitle_outline_width",
    ):
        legacy.pop(key)
    legacy["channel_top"] = 1502

    upgraded = service.normalize_movie_shorts_layout(legacy)

    assert upgraded["layout_version"] == 2
    assert upgraded["title_center_x"] == 540
    assert upgraded["movie_title_top"] == 1480
    assert upgraded["movie_title_center_x"] == 540
    assert upgraded["channel_top"] == 1605
    assert upgraded["channel_center_x"] == 540
    assert upgraded["intertitle_text_center_x"] == 540
    assert upgraded["intertitle_text_top"] == 840


@pytest.mark.asyncio
async def test_thumbnail_frame_is_extracted_and_registered(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._JOB_DIR_CACHE.clear()
    job_id = "MR_20260812_120000_deadbeef"
    job_dir = tmp_path / "1. Test"
    job_dir.mkdir()
    video_path = job_dir / "source.mp4"
    video_path.write_bytes(b"video")
    service._JOB_DIR_CACHE[job_id] = job_dir
    service._write_manifest(
        {
            "job_id": job_id,
            "status": "ready",
            "created_at": "2026-08-12T12:00:00+00:00",
            "video_path": str(video_path),
            "duration_seconds": 10,
        }
    )
    monkeypatch.setattr(service, "find_ffmpeg", lambda: "ffmpeg")

    async def fake_run_subprocess(cmd, **_kwargs):
        Path(cmd[-1]).write_bytes(b"jpeg")
        return 0, b"", b""

    monkeypatch.setattr(service, "run_subprocess", fake_run_subprocess)
    updated = await service.select_thumbnail_frame(job_id, 4.25)

    assert updated["thumbnail_source"] == "video_frame"
    assert updated["thumbnail_time_seconds"] == 4.25
    assert Path(updated["thumbnail_path"]).read_bytes() == b"jpeg"
    with pytest.raises(ValueError, match="영상 길이 범위"):
        await service.select_thumbnail_frame(job_id, 10)


@pytest.mark.asyncio
async def test_start_job_requires_rights_confirmation(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    with pytest.raises(ValueError, match="사용 허가"):
        await service.start_job(
            source_url="https://youtu.be/abc123",
            rights_confirmed=False,
        )


def test_artifact_resolution_cannot_escape_job_directory(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._JOB_DIR_CACHE.clear()
    job_id = "MR_20260812_120000_deadbeef"
    job_dir = tmp_path / "1. Test"
    job_dir.mkdir()
    service._JOB_DIR_CACHE[job_id] = job_dir
    outside = tmp_path.parent / "outside.mp4"
    outside.write_bytes(b"video")
    service._write_manifest(
        {
            "job_id": job_id,
            "status": "ready",
            "created_at": "2026-08-12T12:00:00+00:00",
            "video_path": str(outside),
        }
    )
    with pytest.raises(ValueError, match="작업 폴더 밖"):
        service.resolve_artifact(job_id, "video")


def test_meta_tags_are_written_as_json_and_plain_text(tmp_path: Path):
    result = service._write_meta_tag_files(
        tmp_path,
        {
            "id": "video123",
            "title": "Test title",
            "channel": "Test channel",
            "tags": ["history", "mystery"],
            "categories": ["Education"],
            "description": "Test description",
            "duration": 123,
            "language": "ko",
        },
    )
    payload = __import__("json").loads(Path(result["meta_tags_path"]).read_text(encoding="utf-8"))
    assert payload["tags"] == ["history", "mystery"]
    assert payload["tag_count"] == 2
    assert Path(result["meta_tags_text_path"]).read_text(encoding="utf-8") == "history\nmystery\n"


def test_video_output_scan_ignores_incomplete_part_files(tmp_path: Path):
    (tmp_path / "blocked.f137.mp4.part").write_bytes(b"incomplete")
    completed = tmp_path / "fallback.mp4"
    completed.write_bytes(b"complete")
    result = service._find_output_files(tmp_path)
    assert result["video_path"] == str(completed.resolve())


def test_srt_timestamp_uses_standard_millisecond_format():
    assert service._srt_timestamp(0) == "00:00:00,000"
    assert service._srt_timestamp(3661.234) == "01:01:01,234"


def test_research_response_collects_json_sources_and_queries():
    raw_text, sources, queries = service._responses_research_output(
        {
            "output": [
                {
                    "type": "web_search_call",
                    "action": {
                        "type": "search",
                        "queries": ["테스트 영화 공식 개봉일"],
                        "sources": [
                            {"title": "공식 작품 페이지", "url": "https://example.com/official"}
                        ],
                    },
                },
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"canonical_title_ko":"테스트 영화"}',
                            "annotations": [
                                {
                                    "type": "url_citation",
                                    "url": "https://example.com/official",
                                    "title": "공식 작품 페이지",
                                }
                            ],
                        }
                    ],
                },
            ]
        }
    )
    assert raw_text == '{"canonical_title_ko":"테스트 영화"}'
    assert queries == ["테스트 영화 공식 개봉일"]
    assert sources == [{"title": "공식 작품 페이지", "url": "https://example.com/official"}]


def test_research_metadata_requires_cited_web_source():
    with pytest.raises(RuntimeError, match="웹 출처"):
        service._normalize_movie_research(
            {"canonical_title_ko": "테스트 영화"},
            seed_metadata={"title": "테스트 영화"},
            sources=[],
            queries=[],
        )


def test_preview_plan_numbers_three_cut_groups_and_appends_separate_final_cta(tmp_path: Path):
    subtitle = tmp_path / "source.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n첫 문장\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\n둘째 문장\n\n"
        "3\n00:00:02,000 --> 00:00:03,000\n셋째 문장\n\n"
        "4\n00:00:03,000 --> 00:00:04,000\n넷째 문장\n",
        encoding="utf-8",
    )
    cues = service._read_subtitle_cues(subtitle)
    source = {
        "metadata": {
            "title": "테스트 영화",
            "description": "테스트 줄거리",
            "duration_seconds": 4,
            "tags": ["테스트"],
            "webpage_url": "https://youtu.be/test",
            "channel": "테스트 채널",
        },
        "cues": cues,
        "groups": [
            {"group": 1, "cut_start": 1, "cut_end": 3, "source_start": 0, "source_end": 3, "dialogue": ["첫 문장", "둘째 문장", "셋째 문장"]},
            {"group": 2, "cut_start": 4, "cut_end": 4, "source_start": 3, "source_end": 4, "dialogue": ["넷째 문장"]},
        ],
        "research": {
            "canonical_title_ko": "테스트 영화",
            "release": {
                "date": "2026-08-28",
                "platform_or_theatrical": "넷플릭스",
            },
        },
    }
    plan = service._validate_preview_plan(
        {
            "hero_copy": {
                "lines": ["내 이름이 사라졌다", "모든 것을 훔친 자", "정체는 바로 들쥐"],
                "accent_words": ["사라졌다", "훔친 자", "들쥐"],
            },
            "cards": [
                {
                    "typing_text": "모든 이름이 사라진다\n범인은 가장 가까이 있다",
                    "narration": "오늘은 테스트 영화 예고편을 가져왔어요.",
                },
                {
                    "typing_text": "공개 일정",
                    "narration": "이 테스트 영화는 테스트 극장에서 곧 공개될 예정이에요.",
                },
            ],
            "upload_metadata": {
                "short_summary": "내 모든 인생을 훔친 범인",
                "description": "테스트 영화의 예고 영상입니다. {PROFILE_LINK}",
                "tags": ["테스트", "영화예고"],
            },
        },
        source,
    )
    assert len(cues) == 4
    assert plan["cards"][0]["after_cut"] == 3
    assert plan["cards"][1]["after_cut"] == 4
    assert plan["cards"][0]["order"] == 1
    assert plan["cards"][1]["order"] == 2
    assert plan["cards"][2]["order"] == 3
    assert plan["cards"][2]["kind"] == "final_cta"
    assert plan["cards"][2]["after_cut"] == 4
    assert plan["cards"][2]["typing_text"] == "더 많은 정보는\n하단 프로필 링크 클릭!"
    assert plan["cards"][0]["typing_text"] == "모든 이름이 사라진다\n범인은 가장 가까이 있다"
    assert plan["cards"][0]["duration_mode"] == "tts_audio"
    assert "duration_seconds" not in plan["cards"][0]
    assert plan["cards"][2]["duration_mode"] == "tts_audio"
    assert "duration_seconds" not in plan["cards"][2]
    assert plan["commentary_count"] == 2
    assert plan["generation_model"] == "gpt-5.4-mini"
    assert plan["upload_metadata"]["privacy_status"] == "private"
    assert plan["hero_copy"]["lines"] == ["내 이름이 사라졌다", "모든 것을 훔친 자", "정체는 바로 들쥐"]
    assert plan["hero_copy"]["accent_ranges"][2] == [[7, 9]]
    assert plan["upload_metadata"]["title"] == "내 모든 인생을 훔친 범인 | 테스트 영화 | 2026.08.28 | 넷플릭스"
    assert plan["upload_metadata"]["title_parts"]["release_media"] == "넷플릭스"
    assert "TTS 음성 길이에 자동 맞춤" in service._preview_markdown(plan)


def test_cast_narration_is_strengthened_without_uncertain_wording():
    assert service._strengthen_cast_narration("확인된 출연 배우는 류준열과 설경구예요.") == "출연진은 류준열과 설경구예요."
    assert service._strengthen_cast_narration("자료에 따르면 류준열이 주연을 맡아요.") == "류준열이 주연을 맡아요."


@pytest.mark.asyncio
async def test_run_job_uses_whisper_only_when_youtube_has_no_subtitles(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._JOB_DIR_CACHE.clear()
    job_id = "MR_20260812_120000_deadbeef"
    job_dir = tmp_path / "1. Test movie"
    job_dir.mkdir()
    service._JOB_DIR_CACHE[job_id] = job_dir
    video_path = job_dir / "movie.mp4"
    video_path.write_bytes(b"video")
    audio_path = job_dir / "audio_16k_mono.wav"
    audio_path.write_bytes(b"audio")
    service._write_manifest(
        {
            "job_id": job_id,
            "source_url": "https://youtu.be/abc123",
            "status": "queued",
            "created_at": "2026-08-12T12:00:00+00:00",
            "video_path": "",
            "audio_path": "",
            "subtitle_paths": [],
        }
    )
    monkeypatch.setattr(
        service,
        "_download_with_yt_dlp",
        lambda _job_id: {"video_path": str(video_path), "subtitle_paths": []},
    )

    async def fake_extract_audio(_job_id: str, _video_path: str) -> str:
        return str(audio_path)

    monkeypatch.setattr(service, "_extract_audio", fake_extract_audio)
    monkeypatch.setattr(
        service,
        "_transcribe_audio_with_whisper",
        lambda _job_id, _audio_path: {
            "subtitle_path": str(job_dir / "movie.whisper.en.srt"),
            "transcription_provider": "faster-whisper",
            "transcription_model": "large-v3",
            "transcription_language": "en",
            "transcription_device": "cuda:float16",
        },
    )

    await service._run_job(job_id)

    stored = service.get_job(job_id)
    assert stored["status"] == "ready"
    assert stored["subtitle_paths"] == [str(job_dir / "movie.whisper.en.srt")]
    assert stored["transcription_provider"] == "faster-whisper"
    assert stored["transcription_device"] == "cuda:float16"


def test_delete_job_removes_only_the_selected_job_folder(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(service, "MOVIE_REVIEW_ROOT", tmp_path)
    service._JOB_DIR_CACHE.clear()
    job_id = "MR_20260812_120000_deadbeef"
    job_dir = tmp_path / "3. Selected movie"
    job_dir.mkdir()
    (job_dir / "video.mp4").write_bytes(b"video")
    service._JOB_DIR_CACHE[job_id] = job_dir
    service._write_manifest(
        {
            "job_id": job_id,
            "status": "ready",
            "created_at": "2026-08-12T12:00:00+00:00",
        }
    )
    untouched = tmp_path / "4. Other movie"
    untouched.mkdir()
    (untouched / "keep.txt").write_text("keep", encoding="utf-8")

    result = service.delete_job(job_id)

    assert result["deleted"] is True
    assert not job_dir.exists()
    assert (untouched / "keep.txt").is_file()
