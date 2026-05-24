"""Channel operations: manual YouTube comment management."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from app import config
from app.services.youtube_service import YouTubeUploader, YouTubeAuthError, YouTubeUploadError

router = APIRouter()

COMMENT_REPLY_MODEL = "gpt-5.5"
COMMENT_TRANSLATION_MODEL = "gpt-4o-mini"
MAX_REPLY_ALL = 50
COMMENT_SCAN_PAGE_SIZE = 50
MAX_COMMENT_SCAN_VIDEOS = 200


class CommentReplyTarget(BaseModel):
    parent_comment_id: str
    comment_text: str
    author: Optional[str] = None
    video_title: Optional[str] = None
    video_id: Optional[str] = None
    can_reply: Optional[bool] = True
    has_channel_reply: Optional[bool] = False
    is_own_comment: Optional[bool] = False


class CommentReplyRequest(CommentReplyTarget):
    channel_id: int = Field(..., ge=1, le=4)


class CommentReplyAllRequest(BaseModel):
    channel_id: int = Field(..., ge=1, le=4)
    comments: list[CommentReplyTarget] = Field(default_factory=list)


def _clean_text(value: object, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "..."
    return text


def _clean_reply(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"^```(?:\w+)?\s*", "", text).strip()
    text = re.sub(r"\s*```$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text[:500].strip()


def _extract_json_object(text: str) -> dict:
    raw = str(text or "").strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("translation response was not JSON")


def _has_korean_text(text: object) -> bool:
    return bool(re.search(r"[가-힣]", str(text or "")))


def _has_translatable_text(text: object) -> bool:
    return bool(re.search(r"[A-Za-z\u3040-\u30ff\u3400-\u9fff\u0900-\u097f]", str(text or "")))


def _needs_korean_translation(text: object) -> bool:
    cleaned = _clean_text(text, 1200)
    return bool(cleaned and not _has_korean_text(cleaned) and _has_translatable_text(cleaned))


def _reply_profile(target: CommentReplyTarget) -> dict[str, str]:
    text = _clean_text(target.comment_text, 600)
    lowered = text.lower()
    normalized = re.sub(r"\s+", "", text)

    if any(mark in text for mark in ("?", "？")) or any(
        token in lowered
        for token in ("why", "how", "what", "when", "where", "is it", "인가", "나요", "습니까", "어떻게", "왜", "무엇", "どこ", "なぜ", "どう", "ですか", "क्या", "क्यों", "कैसे")
    ):
        comment_type = "viewer question"
    elif any(
        token in lowered
        for token in ("wrong", "incorrect", "not true", "mistake", "error", "틀", "아니", "오류", "잘못", "間違", "違う", "誤", "गलत")
    ):
        comment_type = "correction or disagreement"
    elif any(
        token in lowered
        for token in ("great", "good", "thanks", "thank you", "love", "훌륭", "좋", "감사", "고맙", "재밌", "面白", "ありがとう", "良い", "素晴", "अच्छ", "धन्यवाद")
    ):
        comment_type = "praise or support"
    elif len(normalized) >= 120 or "\n" in str(target.comment_text or ""):
        comment_type = "long feedback or suggestion"
    elif any(
        token in lowered
        for token in ("lol", "ㅋㅋ", "ㅎㅎ", "草", "笑", "ばか", "バカ", "웃", "농담")
    ):
        comment_type = "joke or sarcasm"
    else:
        comment_type = "short viewer reaction"

    seed = f"{target.parent_comment_id}|{target.video_id}|{text}".encode("utf-8", errors="ignore")
    index = int(hashlib.sha256(seed).hexdigest()[:8], 16) % 6
    styles = [
        "Start by directly acknowledging the specific point, then add one warm sentence.",
        "Start with a brief natural thanks, then respond to the core idea without sounding formal.",
        "Start from the viewer's quoted idea, then say how the channel will reflect it.",
        "Use a conversational tone with no generic apology unless the comment points out an error.",
        "Answer the question or correction first, then add a short appreciation.",
        "Keep it restrained and human; avoid sounding like customer support.",
    ]
    return {"comment_type": comment_type, "style": styles[index]}


def _safe_int(value: object) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_disabled_comment_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return (
        "disabled comments" in text
        or "comments disabled" in text
        or "has disabled comments" in text
        or "commentsdisabled" in text
        or "video identified by" in text and "videoid" in text and "disabled" in text
    )


def _comment_error_text(exc: Exception) -> str:
    if _is_disabled_comment_error(exc):
        return "댓글이 비활성화된 영상입니다."
    return _clean_text(str(exc), 500)


def _http_error(exc: Exception, prefix: str) -> HTTPException:
    if isinstance(exc, YouTubeAuthError):
        return HTTPException(status_code=401, detail=f"{prefix}: {exc}")
    if isinstance(exc, YouTubeUploadError):
        return HTTPException(status_code=502, detail=f"{prefix}: {exc}")
    return HTTPException(status_code=500, detail=f"{prefix}: {type(exc).__name__}: {exc}")


def _get_own_channel_id(uploader: YouTubeUploader) -> str:
    uploader._ensure()
    resp = uploader.youtube.channels().list(part="id", mine=True).execute()
    items = resp.get("items") or []
    return str((items[0] or {}).get("id") or "").strip() if items else ""


def _list_uploaded_videos_for_comment_scan(
    uploader: YouTubeUploader,
    max_videos: int,
) -> list[dict]:
    videos: list[dict] = []
    page_token: Optional[str] = None
    limit = max(1, min(int(max_videos or 50), MAX_COMMENT_SCAN_VIDEOS))

    while len(videos) < limit:
        batch_size = min(COMMENT_SCAN_PAGE_SIZE, limit - len(videos))
        data = uploader.list_my_videos(
            max_results=batch_size,
            page_token=page_token,
            include_details=True,
        )
        page_items = data.get("items") or []
        if not page_items:
            break
        videos.extend(page_items[:batch_size])
        page_token = data.get("next_page_token")
        if not page_token:
            break
    return videos


def _videos_with_comments(videos: list[dict]) -> tuple[list[dict], int]:
    known_comment_counts = [
        _safe_int(video.get("comment_count"))
        for video in videos
        if "comment_count" in video
    ]
    has_statistics = any(count is not None for count in known_comment_counts)
    if not has_statistics:
        return videos, 0

    selected = [
        video
        for video in videos
        if (_safe_int(video.get("comment_count")) or 0) > 0
    ]
    return selected, max(0, len(videos) - len(selected))


def _list_comments_sync(channel_id: int, max_videos: int, max_comments: int) -> dict:
    uploader = YouTubeUploader(channel_id=channel_id)
    own_channel_id = _get_own_channel_id(uploader)
    if hasattr(uploader, "list_channel_comment_threads") and own_channel_id:
        comments: list[dict] = []
        errors: list[dict] = []
        page_token: Optional[str] = None
        scanned_pages = 0
        while len(comments) < max_comments:
            try:
                thread_data = uploader.list_channel_comment_threads(
                    channel_youtube_id=own_channel_id,
                    max_results=min(100, max_comments - len(comments)),
                    page_token=page_token,
                    order="time",
                )
            except Exception as exc:
                if not _is_disabled_comment_error(exc):
                    errors.append({"error": _comment_error_text(exc)})
                break
            scanned_pages += 1
            threads = thread_data.get("items") or []
            if not threads:
                break
            video_ids = [
                str(thread.get("video_id") or "").strip()
                for thread in threads
                if str(thread.get("video_id") or "").strip()
            ]
            try:
                video_details = uploader.get_videos_details(video_ids)
            except Exception:
                video_details = {}
            for thread in threads:
                if len(comments) >= max_comments:
                    break
                video_id = str(thread.get("video_id") or "").strip()
                details = video_details.get(video_id) or {}
                replies = thread.get("replies") or []
                author_channel_id = str(thread.get("author_channel_id") or "").strip()
                has_channel_reply = any(
                    str(reply.get("author_channel_id") or "").strip() == own_channel_id
                    for reply in replies
                )
                is_own_comment = bool(own_channel_id and author_channel_id == own_channel_id)
                comments.append({
                    "channel_id": channel_id,
                    "own_channel_id": own_channel_id,
                    "video_id": video_id,
                    "video_title": details.get("title") or video_id,
                    "video_url": f"https://www.youtube.com/watch?v={video_id}" if video_id else "",
                    "video_thumbnail": details.get("thumbnail"),
                    "thread_id": thread.get("thread_id"),
                    "parent_comment_id": thread.get("top_comment_id"),
                    "author": thread.get("author") or "",
                    "author_channel_id": author_channel_id or None,
                    "text": thread.get("text") or "",
                    "like_count": thread.get("like_count"),
                    "published_at": thread.get("published_at"),
                    "updated_at": thread.get("updated_at"),
                    "total_reply_count": thread.get("total_reply_count") or 0,
                    "can_reply": thread.get("can_reply") is not False,
                    "has_channel_reply": has_channel_reply,
                    "is_own_comment": is_own_comment,
                    "replies": replies,
                })
            page_token = thread_data.get("next_page_token")
            if not page_token:
                break
        return {
            "ok": True,
            "channel_id": channel_id,
            "channel_youtube_id": own_channel_id,
            "max_videos": max_videos,
            "max_comments": max_comments,
            "videos_scanned": 0,
            "videos_with_comments": len({c.get("video_id") for c in comments if c.get("video_id")}),
            "videos_skipped_no_comments": 0,
            "comments": comments,
            "errors": errors,
            "scan_mode": "channel_comments",
            "comment_pages_scanned": scanned_pages,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    videos = _list_uploaded_videos_for_comment_scan(uploader, max_videos)
    comment_videos, skipped_no_comments = _videos_with_comments(videos)
    comments: list[dict] = []
    errors: list[dict] = []

    per_video = max(
        1,
        min(100, (max_comments + max(1, len(comment_videos)) - 1) // max(1, len(comment_videos))),
    )
    for video in comment_videos:
        if len(comments) >= max_comments:
            break
        video_id = str(video.get("video_id") or "").strip()
        if not video_id:
            continue
        remaining = max_comments - len(comments)
        try:
            thread_data = uploader.list_comment_threads(
                video_id=video_id,
                max_results=min(per_video, remaining),
                order="time",
            )
        except Exception as exc:
            if not _is_disabled_comment_error(exc):
                errors.append({
                    "video_id": video_id,
                    "video_title": video.get("title") or "",
                    "error": _comment_error_text(exc),
                })
            continue

        for thread in thread_data.get("items") or []:
            if len(comments) >= max_comments:
                break
            replies = thread.get("replies") or []
            author_channel_id = str(thread.get("author_channel_id") or "").strip()
            has_channel_reply = any(
                str(reply.get("author_channel_id") or "").strip() == own_channel_id
                for reply in replies
            )
            is_own_comment = bool(own_channel_id and author_channel_id == own_channel_id)
            comments.append({
                "channel_id": channel_id,
                "own_channel_id": own_channel_id,
                "video_id": video_id,
                "video_title": video.get("title") or "",
                "video_url": f"https://www.youtube.com/watch?v={video_id}",
                "video_thumbnail": video.get("thumbnail"),
                "thread_id": thread.get("thread_id"),
                "parent_comment_id": thread.get("top_comment_id"),
                "author": thread.get("author") or "",
                "author_channel_id": author_channel_id or None,
                "text": thread.get("text") or "",
                "like_count": thread.get("like_count"),
                "published_at": thread.get("published_at"),
                "updated_at": thread.get("updated_at"),
                "total_reply_count": thread.get("total_reply_count") or 0,
                "can_reply": thread.get("can_reply") is not False,
                "has_channel_reply": has_channel_reply,
                "is_own_comment": is_own_comment,
                "replies": replies,
            })

    return {
        "ok": True,
        "channel_id": channel_id,
        "channel_youtube_id": own_channel_id,
        "max_videos": max_videos,
        "max_comments": max_comments,
        "videos_scanned": len(videos),
        "videos_with_comments": len(comment_videos),
        "videos_skipped_no_comments": skipped_no_comments,
        "comments": comments,
        "errors": errors,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


async def _translate_loaded_comments(comments: list[dict]) -> None:
    for comment in comments:
        comment["translated_text"] = None
        comment["translation_error"] = None

    targets = [
        (index, _clean_text(comment.get("text"), 1200))
        for index, comment in enumerate(comments)
        if _needs_korean_translation(comment.get("text"))
    ]
    if not targets:
        return
    if not config.OPENAI_API_KEY:
        for index, _text in targets:
            comments[index]["translation_error"] = "OPENAI_API_KEY 가 설정되지 않았습니다."
        return

    try:
        async with AsyncOpenAI(api_key=config.OPENAI_API_KEY) as client:
            response = await client.chat.completions.create(
                model=COMMENT_TRANSLATION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Translate YouTube comments into Korean. Return only JSON. "
                            "Preserve names, numbers, slang, sarcasm, and the viewer's tone. "
                            "Do not add explanations or moderation notes."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "target_language": "Korean",
                                "rules": [
                                    "Return exactly one Korean string per input comment.",
                                    "Keep informal comments informal.",
                                    "Do not translate JSON keys.",
                                ],
                                "comments": [
                                    {"id": index, "text": text}
                                    for index, text in targets
                                ],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                timeout=90,
            )
        try:
            from app.services import spend_ledger

            spend_ledger.record_llm_usage(
                COMMENT_TRANSLATION_MODEL,
                getattr(response, "usage", None),
                note=f"channel_comment_translation {len(targets)} comments",
            )
        except Exception:
            pass

        data = _extract_json_object(response.choices[0].message.content or "")
        translated = data.get("translations") or data.get("comments") or data.get("texts") or []
        if isinstance(translated, dict):
            translated = [translated.get(str(index)) or translated.get(index) or "" for index, _text in targets]
        if len(translated) != len(targets):
            raise ValueError(f"translation count mismatch: got {len(translated)}, expected {len(targets)}")

        for (comment_index, original_text), item in zip(targets, translated):
            if isinstance(item, dict):
                value = item.get("translation") or item.get("translated_text") or item.get("text") or ""
            else:
                value = item
            text = _clean_text(value, 1200)
            if text and text != original_text:
                comments[comment_index]["translated_text"] = text
    except Exception as exc:
        error = _clean_text(str(exc), 300)
        for index, _text in targets:
            comments[index]["translation_error"] = error


async def _generate_reply(target: CommentReplyTarget) -> str:
    comment_text = _clean_text(target.comment_text)
    if not comment_text:
        raise HTTPException(status_code=400, detail="댓글 내용이 비어 있습니다.")
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=400, detail="OPENAI_API_KEY 가 설정되지 않았습니다.")
    profile = _reply_profile(target)

    messages = [
        {
            "role": "system",
            "content": (
                "You write YouTube replies as the channel owner. "
                "Reply in the same language as the viewer comment. "
                "Match the viewer's comment type and do not use a template. "
                "Naturally include one short quoted phrase, paraphrase, or clearly referenced idea from the comment. "
                "Be human, positive, kind, and specific to the comment. "
                "If the viewer corrects an error, acknowledge it plainly without arguing. "
                "If the viewer asks a question, answer the question directly when possible. "
                "If the viewer praises the video, respond warmly without overexplaining. "
                "Mention improvement only when it fits, and vary the wording; do not repeatedly say 'we will keep improving'. "
                "Avoid repeated openings such as 'Thank you', 'Thanks for watching', '소중한 의견 감사합니다', '좋은 지적 감사합니다'. "
                "Do not invent facts. Do not use markdown or hashtags. "
                "Use 1-2 sentences and stay under 450 characters. "
                "Return only the reply text."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Video title: {_clean_text(target.video_title, 300) or '(none)'}\n"
                f"Comment author: {_clean_text(target.author, 120) or '(unknown)'}\n"
                f"Viewer comment type: {profile['comment_type']}\n"
                f"Reply style for this comment: {profile['style']}\n"
                f"Viewer comment: {comment_text}"
            ),
        },
    ]

    async with AsyncOpenAI(api_key=config.OPENAI_API_KEY) as client:
        response = await client.chat.completions.create(
            model=COMMENT_REPLY_MODEL,
            messages=messages,
            max_completion_tokens=320,
            timeout=90,
        )
    try:
        from app.services import spend_ledger

        spend_ledger.record_llm_usage(
            COMMENT_REPLY_MODEL,
            getattr(response, "usage", None),
            note="channel_comment_reply",
        )
    except Exception:
        pass

    try:
        raw = response.choices[0].message.content or ""
    except Exception:
        raw = ""
    reply = _clean_reply(raw)
    if not reply:
        raise HTTPException(status_code=502, detail="GPT-5.5 댓글 답변 생성 결과가 비어 있습니다.")
    return reply


def _should_skip_reply(target: CommentReplyTarget) -> Optional[str]:
    if not str(target.parent_comment_id or "").strip():
        return "parent_comment_id 가 비어 있습니다."
    if target.can_reply is False:
        return "답변할 수 없는 댓글입니다."
    if target.is_own_comment:
        return "채널 본인 댓글입니다."
    if target.has_channel_reply:
        return "이미 채널 답변이 있는 댓글입니다."
    return None


@router.get("/comments")
async def list_comments(
    channel_id: int = Query(..., ge=1, le=4),
    max_videos: int = Query(50, ge=1, le=MAX_COMMENT_SCAN_VIDEOS),
    max_comments: int = Query(25, ge=1, le=100),
):
    try:
        data = await asyncio.to_thread(_list_comments_sync, channel_id, max_videos, max_comments)
        await _translate_loaded_comments(data.get("comments") or [])
        return data
    except Exception as exc:
        raise _http_error(exc, "댓글 조회 실패") from exc


@router.post("/comments/reply")
async def reply_comment(req: CommentReplyRequest):
    skip_reason = _should_skip_reply(req)
    if skip_reason:
        raise HTTPException(status_code=400, detail=skip_reason)
    try:
        reply_text = await _generate_reply(req)
        uploader = YouTubeUploader(channel_id=req.channel_id)
        posted = await asyncio.to_thread(
            uploader.reply_to_comment,
            str(req.parent_comment_id).strip(),
            reply_text,
        )
        return {
            "ok": True,
            "channel_id": req.channel_id,
            "parent_comment_id": req.parent_comment_id,
            "reply_text": reply_text,
            "posted": posted,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise _http_error(exc, "댓글 답변 실패") from exc


@router.post("/comments/reply-all")
async def reply_all_comments(req: CommentReplyAllRequest):
    targets = req.comments[:MAX_REPLY_ALL]
    uploader = YouTubeUploader(channel_id=req.channel_id)
    results: list[dict] = []
    seen_parent_ids: set[str] = set()

    for target in targets:
        parent_id = str(target.parent_comment_id or "").strip()
        if parent_id in seen_parent_ids:
            results.append({
                "ok": False,
                "parent_comment_id": parent_id,
                "skipped": True,
                "error": "중복 댓글입니다.",
            })
            continue
        seen_parent_ids.add(parent_id)

        skip_reason = _should_skip_reply(target)
        if skip_reason:
            results.append({
                "ok": False,
                "parent_comment_id": parent_id,
                "skipped": True,
                "error": skip_reason,
            })
            continue

        try:
            reply_text = await _generate_reply(target)
            posted = await asyncio.to_thread(uploader.reply_to_comment, parent_id, reply_text)
            results.append({
                "ok": True,
                "parent_comment_id": parent_id,
                "reply_text": reply_text,
                "posted": posted,
            })
        except Exception as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else f"{type(exc).__name__}: {exc}"
            results.append({
                "ok": False,
                "parent_comment_id": parent_id,
                "error": str(detail),
            })

    succeeded = sum(1 for item in results if item.get("ok"))
    failed = len(results) - succeeded
    return {
        "ok": failed == 0,
        "channel_id": req.channel_id,
        "total": len(results),
        "succeeded": succeeded,
        "failed": failed,
        "capped": len(req.comments) > MAX_REPLY_ALL,
        "results": results,
    }
