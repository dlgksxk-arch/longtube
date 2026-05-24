"""YouTube Data API v3 upload service.

OAuth: InstalledAppFlow ë¡œì»¬ ë°ìŠ¤í¬íƒ‘ í”Œë¡œìš°. ìµœì´ˆ 1íšŒ ë¸Œë¼ìš°ì € íŒì—… ì¸ì¦ í›„
token.json ì— refresh token ì €ìž¥. ì´í›„ë¶€í„°ëŠ” ìžë™ ê°±ì‹ .

ì£¼ì˜: `upload()` ëŠ” ë„¤íŠ¸ì›Œí¬ I/O ê°€ ìžˆì§€ë§Œ ì˜ë„ì ìœ¼ë¡œ **sync** ë¡œ êµ¬í˜„ë˜ì–´ ìžˆìŠµë‹ˆë‹¤.
FastAPI ë¼ìš°í„°ì—ì„œ `asyncio.to_thread(uploader.upload, ...)` ë¡œ ê°ì‹¸ í˜¸ì¶œí•˜ì„¸ìš”.
(googleapiclient ìžì²´ê°€ blocking resumable upload ë¥¼ ì“°ë¯€ë¡œ async ë¡œ í¬ìž¥í•´ ë´ì•¼
ì‹¤ì œ ì´ë“ì´ ì—†ê³ , ë¼ìš°í„°/ì„œë¹„ìŠ¤ ê°„ sync/async ë¶ˆì¼ì¹˜ë§Œ ìœ ë°œí•©ë‹ˆë‹¤.)
"""
from __future__ import annotations

import os
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional, Callable

import httplib2
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, BASE_DIR, resolve_project_dir

# ì—…ë¡œë“œ + ì¸ë„¤ì¼ ì„¸íŒ… ê¶Œí•œ
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/youtube",
]

# ì „ì—­ fallback ê²½ë¡œ (project_id ì—†ì´ ìƒì„±ëœ uploader ë¥¼ ìœ„í•œ legacy í˜¸í™˜)
TOKEN_PATH = BASE_DIR / "token.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"


def _project_token_path(project_id: str) -> Path:
    """í”„ë¡œì íŠ¸ë³„ token.json ê²½ë¡œ.

    ê° í”„ë¡œì íŠ¸ ë””ë ‰í† ë¦¬ ì•„ëž˜ì— ì €ìž¥í•˜ë©´ í”„ë¡œì íŠ¸ë³„ë¡œ ë‹¤ë¥¸ YouTube ê³„ì •ì„ ì—°ê²°í• 
    ìˆ˜ ìžˆìŠµë‹ˆë‹¤. í”„ë¡œì íŠ¸ ë””ë ‰í† ë¦¬ì˜ `youtube_token.json` í˜•íƒœ.
    """
    return resolve_project_dir(project_id, create=True) / "youtube_token.json"


def _channel_token_path(channel_id: int) -> Path:
    """ì±„ë„ë³„ token.json ê²½ë¡œ.

    ë”¸ê¹ íì˜ CH1~CH4 ê°€ ì‹¤ì œë¡œ ì„œë¡œ ë‹¤ë¥¸ YouTube ì±„ë„ì— ì—…ë¡œë“œë˜ë„ë¡,
    ì±„ë„ë§ˆë‹¤ ë³„ë„ì˜ OAuth í† í°ì„ ì €ìž¥í•œë‹¤.
    `BASE_DIR/token_ch{N}.json` í˜•íƒœ.
    """
    return BASE_DIR / f"token_ch{int(channel_id)}.json"

# Privacy enum ê°’ (YouTube API í‘œì¤€)
VALID_PRIVACY = {"private", "unlisted", "public"}

# YouTube ì¹´í…Œê³ ë¦¬ ID (ëŒ€í‘œì ì¸ ê²ƒë§Œ; 22=People & Blogs ê¸°ë³¸ê°’)
DEFAULT_CATEGORY_ID = "22"
YOUTUBE_HTTP_TIMEOUT_SECONDS = 180
YOUTUBE_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
YOUTUBE_UPLOAD_TRANSIENT_RETRIES = 8
YOUTUBE_UPLOAD_FILE_READY_TIMEOUT_SECONDS = int(os.getenv("YOUTUBE_UPLOAD_FILE_READY_TIMEOUT_SECONDS", "300") or 300)
YOUTUBE_UPLOAD_FILE_STABLE_SECONDS = float(os.getenv("YOUTUBE_UPLOAD_FILE_STABLE_SECONDS", "5") or 5)
YOUTUBE_UPLOAD_FFMPEG_VALIDATE_TIMEOUT_SECONDS = int(os.getenv("YOUTUBE_UPLOAD_FFMPEG_VALIDATE_TIMEOUT_SECONDS", "600") or 600)


def _short_error(data: bytes, limit: int = 1200) -> str:
    text = (data or b"").decode("utf-8", errors="replace").strip()
    return text[-limit:] if len(text) > limit else text


def _validate_upload_media_file(path: Path) -> Optional[str]:
    try:
        from app.services.video.subprocess_helper import find_ffmpeg

        ffmpeg = find_ffmpeg()
        result = subprocess.run(
            [
                ffmpeg,
                "-v",
                "error",
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=YOUTUBE_UPLOAD_FFMPEG_VALIDATE_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            return _short_error(result.stderr) or f"ffmpeg returncode={result.returncode}"
        return None
    except subprocess.TimeoutExpired:
        return f"ffmpeg validation timeout after {YOUTUBE_UPLOAD_FFMPEG_VALIDATE_TIMEOUT_SECONDS}s"
    except Exception as exc:
        return str(exc)


def _wait_for_upload_media_ready(video_path: str) -> None:
    path = Path(video_path)
    deadline = time.monotonic() + max(1, YOUTUBE_UPLOAD_FILE_READY_TIMEOUT_SECONDS)
    stable_required = max(1.0, YOUTUBE_UPLOAD_FILE_STABLE_SECONDS)
    last_signature: tuple[int, int] | None = None
    stable_since: float | None = None
    last_error = ""

    while time.monotonic() < deadline:
        try:
            stat = path.stat()
            signature = (int(stat.st_size), int(stat.st_mtime_ns))
            if signature[0] <= 0:
                last_error = "file size is zero"
                last_signature = None
                stable_since = None
            elif signature == last_signature:
                if stable_since is None:
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= stable_required:
                    validation_error = _validate_upload_media_file(path)
                    if validation_error is None:
                        return
                    last_error = validation_error
                    last_signature = None
                    stable_since = None
            else:
                last_signature = signature
                stable_since = None
        except FileNotFoundError:
            last_error = "file does not exist yet"
            last_signature = None
            stable_since = None
        time.sleep(1)

    raise YouTubeUploadError(
        "YouTube 업로드 전 영상 파일 준비 확인 실패: "
        f"{video_path} ({last_error or 'file did not become stable'})"
    )


def _has_required_scopes(creds: Optional[Credentials]) -> bool:
    if not creds:
        return False
    granted = set(getattr(creds, "scopes", None) or getattr(creds, "granted_scopes", None) or [])
    if not granted:
        return False
    return set(SCOPES).issubset(granted)


def _token_file_has_required_scopes(path: Path) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    raw = data.get("scopes") or data.get("scope") or []
    if isinstance(raw, str):
        granted = set(raw.split())
    else:
        granted = {str(item) for item in raw}
    return set(SCOPES).issubset(granted)


def _load_credentials_from_token_file(path: Path) -> Credentials:
    """Load credentials while preserving broad-scope legacy YouTube tokens."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return Credentials.from_authorized_user_info(data, SCOPES)


def _friendly_youtube_error(prefix: str, e: Exception) -> str:
    msg = str(e)
    lowered = msg.lower()
    if "youtube.thumbnail" in lowered and "doesn't have permissions" in lowered:
        return (
            f"{prefix}: 이 YouTube 채널은 현재 커스텀 썸네일 업로드 권한이 없습니다. "
            "YouTube 채널 기능 자격요건에서 전화 인증/고급 기능을 활성화한 뒤 "
            "썸네일만 다시 업로드하세요. (reason: customThumbnailPermissionDenied)"
        )
    if "uploadlimitexceeded" in lowered or "exceeded the number of videos" in lowered:
        return (
            f"{prefix}: YouTube 업로드 제한입니다. "
            "이 계정은 현재 추가 영상을 업로드할 수 없습니다. "
            "일일/계정 업로드 한도가 풀린 뒤 업로드만 다시 시도하세요. "
            "(reason: uploadLimitExceeded)"
        )
    if (
        "quotaexceeded" in lowered
        or "dailylimitexceeded" in lowered
        or "you have exceeded your quota" in lowered
    ):
        return (
            f"{prefix}: YouTube API 할당량이 초과되었습니다. "
            "잠시 후 다시 시도하거나 Google Cloud Console에서 YouTube Data API 할당량을 확인하세요. "
            "(reason: quotaExceeded)"
        )
    if "insufficient authentication scopes" in lowered or "insufficientpermissions" in lowered:
        return (
            f"{prefix}: YouTube OAuth 권한이 부족합니다. "
            "이 채널 토큰을 다시 인증해야 합니다. 필요한 권한은 "
            "youtube.upload, youtube.force-ssl, youtube 입니다. "
            "(reason: insufficientAuthenticationScopes)"
        )
    if (
        "disabled comments" in lowered
        or "comments disabled" in lowered
        or "has disabled comments" in lowered
        or "commentsdisabled" in lowered
    ):
        return f"{prefix}: 댓글이 비활성화된 영상입니다. (reason: commentsDisabled)"
    return f"{prefix}: {e}"


def _is_transient_upload_error(e: Exception) -> bool:
    text = str(e).lower()
    transient_needles = (
        "timed out",
        "timeout",
        "read operation timed out",
        "connection reset",
        "connection aborted",
        "connectionabortederror",
        "winerror 10053",
        "winerror 10054",
        "winerror 10060",
        "현재 연결은",
        "호스트 시스템",
        "중단되었습니다",
        "forcibly closed",
        "forcibly aborted",
        "temporarily unavailable",
        "internal error",
        "backend error",
        "ssl",
        "broken pipe",
        "socket",
    )
    if any(needle in text for needle in transient_needles):
        return True
    status = getattr(getattr(e, "resp", None), "status", None)
    try:
        return int(status) in {500, 502, 503, 504}
    except Exception:
        return False


class YouTubeAuthError(RuntimeError):
    """OAuth ì„¤ì •/í”Œë¡œìš° ì‹¤íŒ¨ ì‹œ."""


class YouTubeUploadError(RuntimeError):
    """ì—…ë¡œë“œ/ì¸ë„¤ì¼ API í˜¸ì¶œ ì‹¤íŒ¨ ì‹œ."""


def normalize_upload_title_for_match(title: str) -> str:
    text = str(title or "").lower()
    text = re.sub(r"#\s*shorts\b", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" -_[]()")


class YouTubeUploader:
    def __init__(
        self,
        project_id: Optional[str] = None,
        channel_id: Optional[int] = None,
    ):
        """YouTube ì—…ë¡œë”.

        í† í° ìš°ì„ ìˆœìœ„:
          1. channel_id ì§€ì • ì‹œ â†’ `BASE_DIR/token_ch{N}.json`
          2. project_id ì§€ì • ì‹œ â†’ í”„ë¡œì íŠ¸ ë””ë ‰í† ë¦¬ì˜ `youtube_token.json`
          3. ë‘˜ ë‹¤ None â†’ ì „ì—­ `BASE_DIR/token.json` (legacy)

        Args:
            project_id: í”„ë¡œì íŠ¸ ID.
            channel_id: ë”¸ê¹ ì±„ë„ ë²ˆí˜¸ (1~4). ì§€ì •í•˜ë©´ ì±„ë„ë³„ í† í°ì„ ì‚¬ìš©í•œë‹¤.
        """
        self.youtube = None
        self.project_id = project_id
        self.channel_id = channel_id
        if channel_id is not None:
            self.token_path: Path = _channel_token_path(channel_id)
        elif project_id:
            self.token_path = _project_token_path(project_id)
        else:
            self.token_path = TOKEN_PATH
        self._uploads_playlist_id: Optional[str] = None

    # ---------- OAuth ----------

    def authenticate(self) -> None:
        """OAuth 2.0 ì¸ì¦. ìµœì´ˆ 1íšŒ ë¸Œë¼ìš°ì € ì¸ì¦ í›„ token.json ì €ìž¥.

        ì´ë¯¸ token.json ì´ ìžˆìœ¼ë©´ ìž¬ì‚¬ìš©. ë§Œë£Œëìœ¼ë©´ refresh_token ìœ¼ë¡œ ìžë™ ê°±ì‹ .
        client_secret.json ì´ ì—†ìœ¼ë©´ env ì˜ YOUTUBE_CLIENT_ID/SECRET ë¡œ ì¦‰ì„ ìƒì„±.
        """
        creds = None

        if self.token_path.exists():
            try:
                creds = _load_credentials_from_token_file(self.token_path)
            except Exception as e:
                raise YouTubeAuthError(f"token.json ë¡œë“œ ì‹¤íŒ¨: {e}") from e
            if not _token_file_has_required_scopes(self.token_path):
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    raise YouTubeAuthError(f"í† í° ê°±ì‹  ì‹¤íŒ¨: {e}") from e
            else:
                if not CLIENT_SECRET_PATH.exists():
                    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
                        raise YouTubeAuthError(
                            "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET í™˜ê²½ë³€ìˆ˜ê°€ ì„¤ì •ë˜ì§€ "
                            "ì•Šì•˜ê±°ë‚˜ client_secret.json íŒŒì¼ì´ ì—†ìŠµë‹ˆë‹¤."
                        )
                    secret = {
                        "installed": {
                            "client_id": YOUTUBE_CLIENT_ID,
                            "client_secret": YOUTUBE_CLIENT_SECRET,
                            "redirect_uris": ["http://localhost"],
                            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                            "token_uri": "https://oauth2.googleapis.com/token",
                        }
                    }
                    try:
                        with open(CLIENT_SECRET_PATH, "w", encoding="utf-8") as f:
                            json.dump(secret, f)
                    except Exception as e:
                        raise YouTubeAuthError(f"client_secret.json ìƒì„± ì‹¤íŒ¨: {e}") from e

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
                    creds = flow.run_local_server(
                        port=0,
                        prompt="select_account consent",
                        include_granted_scopes="true",
                    )
                except Exception as e:
                    raise YouTubeAuthError(f"OAuth ë¡œì»¬ ì„œë²„ í”Œë¡œìš° ì‹¤íŒ¨: {e}") from e

            try:
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                raise YouTubeAuthError(f"token.json ì €ìž¥ ì‹¤íŒ¨: {e}") from e

        try:
            http_client = httplib2.Http(timeout=YOUTUBE_HTTP_TIMEOUT_SECONDS)
            # YouTube resumable uploads use HTTP 308 "Resume Incomplete" as a
            # normal progress response. httplib2 treats 308 as a redirect by
            # default and can raise RedirectMissingLocation when no Location
            # header is present, aborting otherwise healthy uploads.
            try:
                http_client.redirect_codes = frozenset(
                    code for code in http_client.redirect_codes if code != 308
                )
            except Exception:
                pass
            http = AuthorizedHttp(
                creds,
                http=http_client,
            )
            self.youtube = build(
                "youtube",
                "v3",
                http=http,
                cache_discovery=False,
            )
        except Exception as e:
            raise YouTubeAuthError(f"youtube í´ë¼ì´ì–¸íŠ¸ ë¹Œë“œ ì‹¤íŒ¨: {e}") from e

    def is_authenticated(self) -> bool:
        """token.json ì´ ìžˆê³  ìœ íš¨í•œ scope ë¡œ ë¡œë“œ ê°€ëŠ¥í•œì§€ non-destructive ì²´í¬."""
        if not self.token_path.exists():
            return False
        try:
            creds = _load_credentials_from_token_file(self.token_path)
        except Exception:
            return False
        return (
            creds is not None
            and _token_file_has_required_scopes(self.token_path)
            and (creds.valid or bool(creds.refresh_token))
        )

    def get_channel_info(self) -> dict:
        """í˜„ìž¬ ì¸ì¦ëœ ê³„ì •ì˜ YouTube ì±„ë„ ì •ë³´ ì¡°íšŒ.

        Returns:
            {
                "channel_id": str,
                "title": str,
                "custom_url": Optional[str],
                "thumbnail": Optional[str],
                "subscriber_count": Optional[int],
                "video_count": Optional[int],
            }

        Raises:
            YouTubeAuthError: ì¸ì¦ ì•ˆ ëê±°ë‚˜ API í˜¸ì¶œ ì‹¤íŒ¨.
        """
        if self.youtube is None:
            self.authenticate()
        try:
            resp = self.youtube.channels().list(
                part="id,snippet,statistics",
                mine=True,
            ).execute()
        except Exception as e:
            raise YouTubeAuthError(f"ì±„ë„ ì •ë³´ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e

        items = resp.get("items") or []
        if not items:
            raise YouTubeAuthError(
                "ì¸ì¦ëœ ê³„ì •ì— ì—°ê²°ëœ YouTube ì±„ë„ì´ ì—†ìŠµë‹ˆë‹¤."
            )
        item = items[0]
        snippet = item.get("snippet") or {}
        stats = item.get("statistics") or {}
        thumbs = snippet.get("thumbnails") or {}
        thumb_url = None
        for key in ("default", "medium", "high"):
            t = thumbs.get(key)
            if t and t.get("url"):
                thumb_url = t["url"]
                break

        def _to_int(v):
            try:
                return int(v) if v is not None else None
            except Exception:
                return None

        return {
            "channel_id": item.get("id") or "",
            "title": snippet.get("title") or "",
            "custom_url": snippet.get("customUrl"),
            "thumbnail": thumb_url,
            "subscriber_count": _to_int(stats.get("subscriberCount")),
            "video_count": _to_int(stats.get("videoCount")),
        }

    def logout(self) -> bool:
        """ì €ìž¥ëœ token.json ì„ ì‚­ì œí•´ ë‹¤ìŒ í˜¸ì¶œì—ì„œ ìž¬ì¸ì¦ì„ ê°•ì œ.

        í”„ë¡œì íŠ¸ë³„ í† í°ì´ ì„¤ì •ë¼ ìžˆìœ¼ë©´ ê·¸ í† í°ë§Œ, ì•„ë‹ˆë©´ ì „ì—­ í† í°ì„ ì‚­ì œí•©ë‹ˆë‹¤.

        Returns:
            ì‹¤ì œë¡œ íŒŒì¼ì„ ì§€ì› ëŠ”ì§€ ì—¬ë¶€.
        """
        if self.token_path.exists():
            try:
                self.token_path.unlink()
                return True
            except Exception as e:
                raise YouTubeAuthError(f"token.json ì‚­ì œ ì‹¤íŒ¨: {e}") from e
        return False

    # ---------- Upload ----------

    def upload(
        self,
        video_path: str,
        title: str,
        description: str,
        tags: Optional[list[str]] = None,
        thumbnail_path: Optional[str] = None,
        privacy: str = "private",
        language: Optional[str] = None,
        category_id: Optional[str] = None,
        made_for_kids: bool = False,
        progress_callback: Optional[Callable[[int], None]] = None,
    ) -> dict:
        """ì˜ìƒ ì—…ë¡œë“œ + (ì„ íƒ) ì¸ë„¤ì¼ ì„¤ì •.

        Returns:
            {"video_id": str, "url": str}

        Raises:
            YouTubeUploadError: API í˜¸ì¶œ ì‹¤íŒ¨ ì‹œ.
        """
        if privacy not in VALID_PRIVACY:
            raise YouTubeUploadError(
                f"ìœ íš¨í•˜ì§€ ì•Šì€ privacy ê°’: {privacy!r} (í—ˆìš©: {sorted(VALID_PRIVACY)})"
            )
        if not os.path.exists(video_path):
            raise YouTubeUploadError(f"ì˜ìƒ íŒŒì¼ì´ ì¡´ìž¬í•˜ì§€ ì•ŠìŒ: {video_path}")
        _wait_for_upload_media_ready(video_path)

        if self.youtube is None:
            self.authenticate()

        snippet: dict = {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id or DEFAULT_CATEGORY_ID,
        }
        if language:
            snippet["defaultLanguage"] = language
            snippet["defaultAudioLanguage"] = language

        body = {
            "snippet": snippet,
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": bool(made_for_kids),
            },
        }

        try:
            media = MediaFileUpload(
                video_path,
                mimetype="video/mp4",
                resumable=True,
                chunksize=YOUTUBE_UPLOAD_CHUNK_SIZE,
            )
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            transient_errors = 0
            while response is None:
                try:
                    status, response = request.next_chunk(num_retries=5)
                    transient_errors = 0
                except Exception as e:
                    if not _is_transient_upload_error(e):
                        raise
                    transient_errors += 1
                    if transient_errors > YOUTUBE_UPLOAD_TRANSIENT_RETRIES:
                        existing = self.find_existing_upload_by_title(title, max_results=25)
                        if existing:
                            video_id = (existing.get("video_id") or "").strip()
                            if video_id:
                                return {
                                    "video_id": video_id,
                                    "url": existing.get("url") or f"https://youtube.com/watch?v={video_id}",
                                    "title": existing.get("title") or title,
                                    "already_uploaded": True,
                                    "recovered_after_upload_timeout": True,
                                }
                        raise
                    time.sleep(min(60, 5 * transient_errors))
                    continue
                if status and progress_callback:
                    try:
                        progress_callback(int(status.progress() * 100))
                    except Exception:
                        pass  # ì½œë°± ì‹¤íŒ¨ëŠ” ì—…ë¡œë“œë¥¼ ë§‰ìœ¼ë©´ ì•ˆ ë¨
        except Exception as e:
            if _is_transient_upload_error(e):
                existing = self.find_existing_upload_by_title(title, max_results=25)
                if existing:
                    video_id = (existing.get("video_id") or "").strip()
                    if video_id:
                        return {
                            "video_id": video_id,
                            "url": existing.get("url") or f"https://youtube.com/watch?v={video_id}",
                            "title": existing.get("title") or title,
                            "already_uploaded": True,
                            "recovered_after_upload_timeout": True,
                        }
            err_text = str(e)
            if "uploadLimitExceeded" in err_text or "exceeded the number of videos" in err_text:
                raise YouTubeUploadError(
                    "YouTube 업로드 제한: 이 계정은 현재 추가 영상을 업로드할 수 없습니다. "
                    "일일/계정 업로드 한도가 풀린 뒤 업로드만 다시 시도하세요. "
                    "(reason: uploadLimitExceeded)"
                ) from e
            raise YouTubeUploadError(_friendly_youtube_error("영상 업로드 실패", e)) from e

        video_id = response.get("id")
        if not video_id:
            raise YouTubeUploadError(f"ì—…ë¡œë“œ ì‘ë‹µì— video id ê°€ ì—†ìŒ: {response!r}")

        # ì¸ë„¤ì¼ ì„¤ì • (ì„ íƒ)
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                mime = "image/png"
                lower = thumbnail_path.lower()
                if lower.endswith(".jpg") or lower.endswith(".jpeg"):
                    mime = "image/jpeg"
                elif lower.endswith(".webp"):
                    mime = "image/webp"
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype=mime),
                ).execute(num_retries=3)
            except Exception as e:
                # ì¸ë„¤ì¼ ì‹¤íŒ¨í•´ë„ ì˜ìƒ ìžì²´ëŠ” ì—…ë¡œë“œ ì„±ê³µì´ë¯€ë¡œ dict ì— ì—ëŸ¬ë§Œ ê¸°ë¡
                return {
                    "video_id": video_id,
                    "url": f"https://youtube.com/watch?v={video_id}",
                    "thumbnail_error": str(e),
                }

        return {
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
        }

    def upload_caption(
        self,
        video_id: str,
        caption_path: str,
        language: str = "ko",
        name: Optional[str] = None,
        is_draft: bool = False,
    ) -> dict:
        """Upload a timed caption track to an existing YouTube video."""
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("caption upload failed: video_id is empty")
        if not os.path.exists(caption_path):
            raise YouTubeUploadError(f"caption file does not exist: {caption_path}")

        if self.youtube is None:
            self.authenticate()

        lang = (language or "ko").strip() or "ko"
        body = {
            "snippet": {
                "videoId": str(video_id).strip(),
                "language": lang,
                "name": (name or lang).strip(),
                "isDraft": bool(is_draft),
            }
        }
        try:
            media = MediaFileUpload(
                caption_path,
                mimetype="application/octet-stream",
                resumable=False,
            )
            response = self.youtube.captions().insert(
                part="snippet",
                body=body,
                media_body=media,
            ).execute(num_retries=3)
        except Exception as e:
            raise YouTubeUploadError(f"caption upload failed: {e}") from e

        return {
            "caption_id": response.get("id"),
            "language": lang,
            "name": body["snippet"]["name"],
        }

    # ---------- Delete ----------

    def delete_video(self, video_id: str) -> None:
        """ì—…ë¡œë“œëœ ì˜ìƒì„ YouTube ì—ì„œ ì‚­ì œ.

        YouTube API ì˜ videos.delete ë¥¼ í˜¸ì¶œí•©ë‹ˆë‹¤. **ë³µêµ¬ ë¶ˆê°€ëŠ¥** í•œ ìž‘ì—…ì´ë¯€ë¡œ
        í˜¸ì¶œ ì „ì— ì‚¬ìš©ìžì—ê²Œ ë°˜ë“œì‹œ í™•ì¸ì„ ë°›ì•„ì•¼ í•©ë‹ˆë‹¤. ë¼ìš°í„° ë ˆì´ì–´ì—ì„œ
        `confirm=True` ê°™ì€ ëª…ì‹œì  í”Œëž˜ê·¸ë¥¼ ê°•ì œí•´ ì´ì¤‘ ì•ˆì „ìž¥ì¹˜ë¥¼ ë‘ì„¸ìš”.

        Args:
            video_id: ì‚­ì œí•  ìœ íŠœë¸Œ video id (ì˜ˆ: "dQw4w9WgXcQ").

        Raises:
            YouTubeUploadError: video_id ê°€ ë¹„ì—ˆê±°ë‚˜ API í˜¸ì¶œì´ ì‹¤íŒ¨í•œ ê²½ìš°.
            YouTubeAuthError: ì¸ì¦ ì‹¤íŒ¨.
        """
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id ê°€ ë¹„ì–´ìžˆì–´ ì‚­ì œí•  ìˆ˜ ì—†ìŠµë‹ˆë‹¤.")
        if self.youtube is None:
            self.authenticate()
        try:
            # videos.delete ëŠ” ì„±ê³µ ì‹œ 204 No Content â€” execute() ëŠ” ë¹ˆ dict ë°˜í™˜
            self.youtube.videos().delete(id=str(video_id).strip()).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ì˜ìƒ ì‚­ì œ ì‹¤íŒ¨: {e}") from e

    # ---------- Studio: ì˜ìƒ ì¡°íšŒ/íŽ¸ì§‘ (v1.1.31) ----------
    #
    # ì´ ì•„ëž˜ ë©”ì„œë“œë“¤ì€ LongTube íŒŒì´í”„ë¼ì¸ ë°–ì—ì„œ ì´ë¯¸ ì—…ë¡œë“œë˜ì–´ ìžˆëŠ” ì˜ìƒë„
    # ê´€ë¦¬í•˜ê¸° ìœ„í•œ ì¼ë°˜ Studio ê¸°ëŠ¥ìž…ë‹ˆë‹¤. ëª¨ë‘ `youtube.force-ssl` + `youtube`
    # scope ë¡œ ë™ìž‘ â€” ì¶”ê°€ scope ì—†ì´ videos/playlists/commentThreads ì „ì²´ íŽ¸ì§‘
    # ê°€ëŠ¥. YouTube Analytics (ì¡°íšŒìˆ˜ ê·¸ëž˜í”„ ë“±) ëŠ” ë³„ë„ scope ë¼ ë¯¸êµ¬í˜„.

    def _ensure(self) -> None:
        if self.youtube is None:
            self.authenticate()

    def _get_uploads_playlist_id(self) -> str:
        """Return and cache this channel's uploads playlist id.

        `channels.list(mine=True, part=contentDetails)` is cheap, but this
        service may call it repeatedly during upload verification. Caching it
        per uploader instance keeps the hot path lean.
        """
        self._ensure()
        if self._uploads_playlist_id:
            return self._uploads_playlist_id
        resp = self.youtube.channels().list(
            part="contentDetails",
            mine=True,
        ).execute()
        items = resp.get("items") or []
        if not items:
            return ""
        uploads_playlist_id = (
            ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
            or ""
        ).strip()
        self._uploads_playlist_id = uploads_playlist_id
        return uploads_playlist_id

    def list_my_videos(
        self,
        max_results: int = 50,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
        include_details: bool = True,
    ) -> dict:
        """ë‚´ ì±„ë„ì— ì—…ë¡œë“œëœ ì˜ìƒ ëª©ë¡.

        Quota note: this intentionally avoids `search.list(forMine=True, q=...)`.
        YouTube charges that endpoint much more heavily than uploads playlist
        reads, so text search is implemented as a small local scan over the
        channel uploads playlist.

        Args:
            max_results: 1~50. YouTube ì œí•œ.
            page_token: ë‹¤ìŒ íŽ˜ì´ì§€ í† í°.
            query: title/description search text. Uses cheap local filtering.
            include_details: add videos.list status/statistics/duration fields.

        Returns:
            {"items": [...], "next_page_token": str|None, "total_results": int}
        """
        self._ensure()
        requested_max = max(1, min(int(max_results or 50), 50))
        search_query = (query or "").strip()

        try:
            uploads_playlist_id = self._get_uploads_playlist_id()
            if not uploads_playlist_id:
                return {
                    "items": [],
                    "next_page_token": None,
                    "prev_page_token": None,
                    "total_results": 0,
                }

            raw_items = []
            next_page_token = None
            prev_page_token = None
            total_results = 0
            token = page_token
            query_norm = normalize_upload_title_for_match(search_query)
            max_pages = 4 if query_norm else 1

            for _ in range(max_pages):
                req: dict = {
                    "part": "snippet,contentDetails",
                    "playlistId": uploads_playlist_id,
                    "maxResults": 50 if query_norm else requested_max,
                }
                if token:
                    req["pageToken"] = token
                resp = self.youtube.playlistItems().list(**req).execute()
                page_items = resp.get("items") or []
                next_page_token = resp.get("nextPageToken")
                prev_page_token = resp.get("prevPageToken")
                total_results = (resp.get("pageInfo") or {}).get("totalResults")

                if query_norm:
                    for it in page_items:
                        sn = it.get("snippet") or {}
                        haystack = normalize_upload_title_for_match(
                            f"{sn.get('title') or ''} {sn.get('description') or ''}"
                        )
                        if query_norm in haystack:
                            raw_items.append(it)
                            if len(raw_items) >= requested_max:
                                break
                    if len(raw_items) >= requested_max or not next_page_token:
                        break
                    token = next_page_token
                    continue

                raw_items = page_items
                break

            if query_norm:
                next_page_token = None
                prev_page_token = None
                total_results = len(raw_items)
        except Exception as e:
            raise YouTubeUploadError(_friendly_youtube_error("ì˜ìƒ ëª©ë¡ ì¡°íšŒ ì‹¤íŒ¨", e)) from e

        items = []
        video_ids: list[str] = []
        for it in raw_items:
            raw_id = it.get("id")
            id_block = raw_id if isinstance(raw_id, dict) else {}
            content_details = it.get("contentDetails") or {}
            snippet = it.get("snippet") or {}
            resource_id = snippet.get("resourceId") or {}
            vid = (
                (id_block.get("videoId"))
                or (content_details.get("videoId"))
                or (resource_id.get("videoId"))
                or ""
            ).strip()
            if not vid:
                continue
            sn = snippet
            thumbs = sn.get("thumbnails") or {}
            thumb = None
            for key in ("medium", "high", "default"):
                t = thumbs.get(key)
                if t and t.get("url"):
                    thumb = t["url"]
                    break
            items.append({
                "video_id": vid,
                "title": sn.get("title") or "",
                "description": sn.get("description") or "",
                "published_at": sn.get("publishedAt"),
                "thumbnail": thumb,
                "channel_title": sn.get("channelTitle") or "",
            })
            video_ids.append(vid)

        # ë³´ê°•: videos.list ë¡œ status + statistics + contentDetails ë¶™ì´ê¸°
        if include_details and video_ids:
            try:
                det_resp = self.youtube.videos().list(
                    part="status,statistics,contentDetails",
                    id=",".join(video_ids),
                    maxResults=50,
                ).execute()
                det_map = {d["id"]: d for d in (det_resp.get("items") or [])}
                for item in items:
                    d = det_map.get(item["video_id"])
                    if not d:
                        continue
                    status = d.get("status") or {}
                    stats = d.get("statistics") or {}
                    cd = d.get("contentDetails") or {}
                    item["privacy_status"] = status.get("privacyStatus")
                    item["publish_at"] = status.get("publishAt")
                    item["made_for_kids"] = status.get("madeForKids")
                    item["view_count"] = _to_int(stats.get("viewCount"))
                    item["like_count"] = _to_int(stats.get("likeCount"))
                    item["comment_count"] = _to_int(stats.get("commentCount"))
                    item["duration"] = cd.get("duration")  # ISO 8601
            except Exception as e:
                # ë³´ê°• ì‹¤íŒ¨í•´ë„ ëª©ë¡ì€ ë°˜í™˜
                print(f"[youtube studio] videos.list ë³´ê°• ì‹¤íŒ¨ (non-fatal): {e}")

        return {
            "items": items,
            "next_page_token": next_page_token,
            "prev_page_token": prev_page_token,
            "total_results": total_results,
        }

    def find_existing_upload_by_title(self, title: str, max_results: int = 10) -> Optional[dict]:
        """Return an already-uploaded video with the same normalized title.

        This uses the uploads playlist, not `search.list(q=...)`. The search
        endpoint is expensive enough to exhaust quota when every upload checks
        for duplicates first.
        """
        wanted = normalize_upload_title_for_match(title)
        if not wanted:
            return None
        token = None
        pages = 0
        while pages < 6:
            data = self.list_my_videos(
                max_results=max_results,
                page_token=token,
                include_details=False,
            )
            for item in data.get("items") or []:
                if normalize_upload_title_for_match(item.get("title") or "") == wanted:
                    video_id = (item.get("video_id") or "").strip()
                    if video_id and not item.get("url"):
                        item = {**item, "url": f"https://www.youtube.com/watch?v={video_id}"}
                    return item
            token = data.get("next_page_token")
            if not token:
                break
            pages += 1
        return None

    def find_upload_playlist_item_by_id(self, video_id: str, max_pages: int = 4) -> Optional[dict]:
        """Return an uploads-playlist item by video id, including deleted placeholders."""
        self._ensure()
        vid = str(video_id or "").strip()
        if not vid:
            return None
        token = None
        pages = 0
        while pages < max(1, int(max_pages or 4)):
            data = self.list_my_videos(
                max_results=50,
                page_token=token,
                include_details=False,
            )
            for item in data.get("items") or []:
                if str(item.get("video_id") or "").strip() == vid:
                    video_id_found = str(item.get("video_id") or "").strip()
                    if video_id_found and not item.get("url"):
                        item = {**item, "url": f"https://www.youtube.com/watch?v={video_id_found}"}
                    return item
            token = data.get("next_page_token")
            if not token:
                break
            pages += 1
        return None

    def confirm_upload_visible_in_studio(
        self,
        *,
        video_id: Optional[str] = None,
        title: Optional[str] = None,
        timeout_seconds: int = 120,
        interval_seconds: int = 10,
    ) -> dict:
        """Wait until an uploaded video is visible in the channel's Studio list.

        `videos.insert` returning a video id only means YouTube accepted the
        resumable upload. For queue completion we want the stricter condition:
        the authenticated channel's own uploads list can see the video. This
        uses the uploads playlist path from `list_my_videos()` instead of
        `search.list(q=...)` so upload-time verification does not burn the
        expensive search quota.
        """
        vid = (video_id or "").strip()
        wanted_title = normalize_upload_title_for_match(title or "")
        deadline = time.monotonic() + max(1, int(timeout_seconds or 120))
        interval = max(1, int(interval_seconds or 10))
        last_seen_count = 0

        while True:
            data = self.list_my_videos(max_results=25)
            items = data.get("items") or []
            last_seen_count = len(items)
            for item in items:
                item_video_id = (item.get("video_id") or "").strip()
                item_title = normalize_upload_title_for_match(item.get("title") or "")
                id_matches = bool(vid and item_video_id == vid)
                title_matches = bool(wanted_title and item_title == wanted_title)
                if id_matches or (not vid and title_matches):
                    if item_title == "deleted video":
                        raise YouTubeUploadError(
                            "YouTube 업로드 확인 실패: Studio 업로드 목록에서 "
                            f"삭제된 영상 placeholder 로 확인되었습니다. (video_id={item_video_id or vid})"
                        )
                    return {
                        **item,
                        "url": item.get("url") or (
                            f"https://www.youtube.com/watch?v={item_video_id}"
                            if item_video_id
                            else None
                        ),
                        "studio_verified": True,
                        "verification_method": "uploads_playlist",
                    }

            if time.monotonic() >= deadline:
                raise YouTubeUploadError(
                    "YouTube 업로드 확인 실패: 업로드 API는 성공했지만 "
                    "Studio 업로드 목록에서 영상을 확인하지 못했습니다. "
                    f"(video_id={vid or '-'}, title={title or '-'}, last_seen={last_seen_count})"
            )
            time.sleep(interval)

    def get_video_processing_state(self, video_id: str) -> dict:
        """Return upload/processing state for one video."""
        self._ensure()
        vid = str(video_id or "").strip()
        if not vid:
            raise YouTubeUploadError("video_id is empty.")
        try:
            resp = self.youtube.videos().list(
                part="snippet,status,processingDetails",
                id=vid,
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"video processing lookup failed: {e}") from e
        items = resp.get("items") or []
        if not items:
            playlist_item = self.find_upload_playlist_item_by_id(vid)
            if playlist_item:
                title = str(playlist_item.get("title") or "")
                if normalize_upload_title_for_match(title) == "deleted video":
                    return {
                        "video_id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "upload_status": "deleted",
                        "processing_status": None,
                        "processed": False,
                        "terminal_failure": True,
                        "failed_reason": "deleted_video",
                        "playlist_visible": True,
                    }
                return {
                    "video_id": vid,
                    "title": title,
                    "url": playlist_item.get("url") or f"https://www.youtube.com/watch?v={vid}",
                    "upload_status": "uploaded",
                    "processing_status": "processing",
                    "processed": False,
                    "terminal_failure": False,
                    "failed_reason": None,
                    "playlist_visible": True,
                }
            raise YouTubeUploadError(f"video not found: {vid}")
        item = items[0]
        snippet = item.get("snippet") or {}
        status = item.get("status") or {}
        processing = item.get("processingDetails") or {}
        upload_status = status.get("uploadStatus")
        processing_status = processing.get("processingStatus")
        failed_reason = (
            status.get("failureReason")
            or status.get("rejectionReason")
            or processing.get("processingFailureReason")
        )
        processed = upload_status == "processed" or processing_status == "succeeded"
        terminal_failure = upload_status in ("failed", "rejected", "deleted") or processing_status in (
            "failed",
            "terminated",
        )
        return {
            "video_id": vid,
            "title": snippet.get("title") or "",
            "url": f"https://www.youtube.com/watch?v={vid}",
            "upload_status": upload_status,
            "processing_status": processing_status,
            "processed": bool(processed and not terminal_failure),
            "terminal_failure": bool(terminal_failure),
            "failed_reason": failed_reason,
        }

    def confirm_upload_processed_in_studio(
        self,
        *,
        video_id: Optional[str] = None,
        title: Optional[str] = None,
        timeout_seconds: int = 900,
        interval_seconds: int = 20,
    ) -> dict:
        """Wait until Studio sees the upload and YouTube processing is done.

        The upload API can return a video id while Studio still shows
        "processing queued". Queue completion must wait for the processing
        state, otherwise completed tasks can still be unusable in Studio.
        """
        visible = self.confirm_upload_visible_in_studio(
            video_id=video_id,
            title=title,
            timeout_seconds=min(max(1, int(timeout_seconds or 900)), 120),
            interval_seconds=interval_seconds,
        )
        vid = (video_id or visible.get("video_id") or "").strip()
        if not vid:
            raise YouTubeUploadError("YouTube processing check failed: video_id is empty.")

        deadline = time.monotonic() + max(1, int(timeout_seconds or 900))
        interval = max(1, int(interval_seconds or 20))
        last_state: dict = {}
        while True:
            last_state = self.get_video_processing_state(vid)
            if last_state.get("terminal_failure"):
                raise YouTubeUploadError(
                    "YouTube processing failed: "
                    f"video_id={vid}, uploadStatus={last_state.get('upload_status')}, "
                    f"processingStatus={last_state.get('processing_status')}, "
                    f"reason={last_state.get('failed_reason') or '-'}"
                )
            if last_state.get("processed"):
                return {
                    **visible,
                    **last_state,
                    "studio_verified": True,
                    "processing_verified": True,
                    "verification_method": "uploads_playlist+videos.list",
                }
            if time.monotonic() >= deadline:
                raise YouTubeUploadError(
                    "YouTube upload is visible but still processing. "
                    f"video_id={vid}, uploadStatus={last_state.get('upload_status') or '-'}, "
                    f"processingStatus={last_state.get('processing_status') or '-'}"
                )
            time.sleep(interval)

    def get_video(self, video_id: str) -> dict:
        """ì˜ìƒ 1 ê±´ ìƒì„¸.

        snippet + status + statistics + contentDetails ë¥¼ ëª¨ë‘ í¬í•¨.
        """
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            resp = self.youtube.videos().list(
                part="snippet,status,statistics,contentDetails",
                id=str(video_id).strip(),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ì˜ìƒ ìƒì„¸ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        items = resp.get("items") or []
        if not items:
            raise YouTubeUploadError(f"ì˜ìƒì„ ì°¾ì„ ìˆ˜ ì—†ìŠµë‹ˆë‹¤: {video_id}")
        v = items[0]
        sn = v.get("snippet") or {}
        st = v.get("status") or {}
        stats = v.get("statistics") or {}
        cd = v.get("contentDetails") or {}
        thumbs = sn.get("thumbnails") or {}
        thumb = None
        for key in ("maxres", "high", "medium", "default"):
            t = thumbs.get(key)
            if t and t.get("url"):
                thumb = t["url"]
                break
        return {
            "video_id": v.get("id"),
            "title": sn.get("title") or "",
            "description": sn.get("description") or "",
            "tags": sn.get("tags") or [],
            "category_id": sn.get("categoryId"),
            "default_language": sn.get("defaultLanguage"),
            "default_audio_language": sn.get("defaultAudioLanguage"),
            "channel_id": sn.get("channelId"),
            "channel_title": sn.get("channelTitle") or "",
            "published_at": sn.get("publishedAt"),
            "thumbnail": thumb,
            "privacy_status": st.get("privacyStatus"),
            "publish_at": st.get("publishAt"),
            "made_for_kids": st.get("madeForKids"),
            "self_declared_made_for_kids": st.get("selfDeclaredMadeForKids"),
            "embeddable": st.get("embeddable"),
            "license": st.get("license"),
            "public_stats_viewable": st.get("publicStatsViewable"),
            "view_count": _to_int(stats.get("viewCount")),
            "like_count": _to_int(stats.get("likeCount")),
            "comment_count": _to_int(stats.get("commentCount")),
            "duration": cd.get("duration"),
            "definition": cd.get("definition"),
        }

    def get_videos_details(self, video_ids: list[str]) -> dict[str, dict]:
        """Return current metadata/status/statistics keyed by video id."""
        self._ensure()
        ids: list[str] = []
        seen: set[str] = set()
        for raw in video_ids or []:
            vid = str(raw or "").strip()
            if vid and vid not in seen:
                seen.add(vid)
                ids.append(vid)
        if not ids:
            return {}
        out: dict[str, dict] = {}
        for start in range(0, len(ids), 50):
            chunk = ids[start:start + 50]
            try:
                resp = self.youtube.videos().list(
                    part="snippet,status,statistics,contentDetails",
                    id=",".join(chunk),
                    maxResults=50,
                ).execute()
            except Exception as e:
                raise YouTubeUploadError(f"영상 상세 조회 실패: {e}") from e
            for v in resp.get("items") or []:
                sn = v.get("snippet") or {}
                st = v.get("status") or {}
                stats = v.get("statistics") or {}
                cd = v.get("contentDetails") or {}
                thumbs = sn.get("thumbnails") or {}
                thumb = None
                for key in ("maxres", "high", "medium", "default"):
                    t = thumbs.get(key)
                    if t and t.get("url"):
                        thumb = t["url"]
                        break
                out[str(v.get("id") or "")] = {
                    "video_id": v.get("id"),
                    "title": sn.get("title") or "",
                    "description": sn.get("description") or "",
                    "thumbnail": thumb,
                    "published_at": sn.get("publishedAt"),
                    "privacy_status": st.get("privacyStatus"),
                    "comment_count": _to_int(stats.get("commentCount")),
                    "duration": cd.get("duration"),
                }
        return out

    def update_video(
        self,
        video_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
        category_id: Optional[str] = None,
        default_language: Optional[str] = None,
        privacy_status: Optional[str] = None,
        publish_at: Optional[str] = None,   # RFC3339, e.g. "2026-04-13T15:00:00Z"
        made_for_kids: Optional[bool] = None,
        embeddable: Optional[bool] = None,
        public_stats_viewable: Optional[bool] = None,
    ) -> dict:
        """ì˜ìƒ ë©”íƒ€ë°ì´í„° ì—…ë°ì´íŠ¸.

        YouTube ì˜ videos.update ëŠ” `part` ì— í¬í•¨ëœ ë¦¬ì†ŒìŠ¤ í•„ë“œë¥¼ **í†µì§¸ë¡œ**
        ë®ì–´ì“°ë¯€ë¡œ ë¨¼ì € í˜„ìž¬ ê°’ì„ ì½ì–´ì™€ì„œ None ì´ ì•„ë‹Œ í•„ë“œë§Œ êµì²´í•œ ì „ì²´
        snippet/status ë¥¼ ë‹¤ì‹œ ë³´ë‚´ëŠ” merge ë°©ì‹ìœ¼ë¡œ êµ¬í˜„í•©ë‹ˆë‹¤.

        ì˜ˆì•½ ê²Œì‹œ: `privacy_status="private"` + `publish_at=<RFC3339>` ë¥¼
        í•¨ê»˜ ë„˜ê¸°ë©´ YouTube ê°€ í•´ë‹¹ ì‹œê°ì— public ìœ¼ë¡œ ìžë™ ì „í™˜í•©ë‹ˆë‹¤. ì´ë¯¸
        public ì¸ ì˜ìƒì— publish_at ì„ ë„£ìœ¼ë©´ API ê°€ 400 ì„ ëŒë ¤ì¤ë‹ˆë‹¤.

        Raises:
            YouTubeUploadError: API ì‹¤íŒ¨.
        """
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        if privacy_status is not None and privacy_status not in VALID_PRIVACY:
            raise YouTubeUploadError(
                f"privacy_status ê°’ì´ ìœ íš¨í•˜ì§€ ì•ŠìŠµë‹ˆë‹¤: {privacy_status!r}"
            )

        # í˜„ìž¬ ì˜ìƒ ìƒíƒœ ì½ì–´ì˜¤ê¸° (merge ê¸°ë°˜)
        try:
            cur_resp = self.youtube.videos().list(
                part="snippet,status",
                id=str(video_id).strip(),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ì˜ìƒ í˜„ìž¬ ìƒíƒœ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        cur_items = cur_resp.get("items") or []
        if not cur_items:
            raise YouTubeUploadError(f"ì˜ìƒì„ ì°¾ì„ ìˆ˜ ì—†ìŠµë‹ˆë‹¤: {video_id}")
        cur = cur_items[0]
        cur_snippet = cur.get("snippet") or {}
        cur_status = cur.get("status") or {}

        new_snippet = {
            "title": title if title is not None else (cur_snippet.get("title") or ""),
            "description": (
                description if description is not None
                else (cur_snippet.get("description") or "")
            ),
            "tags": tags if tags is not None else (cur_snippet.get("tags") or []),
            "categoryId": (
                category_id if category_id is not None
                else (cur_snippet.get("categoryId") or DEFAULT_CATEGORY_ID)
            ),
        }
        if default_language is not None:
            new_snippet["defaultLanguage"] = default_language
        elif cur_snippet.get("defaultLanguage"):
            new_snippet["defaultLanguage"] = cur_snippet["defaultLanguage"]

        new_status = dict(cur_status)
        if privacy_status is not None:
            new_status["privacyStatus"] = privacy_status
        if publish_at is not None:
            if publish_at:
                new_status["publishAt"] = publish_at
            else:
                new_status.pop("publishAt", None)
        if made_for_kids is not None:
            new_status["selfDeclaredMadeForKids"] = bool(made_for_kids)
        if embeddable is not None:
            new_status["embeddable"] = bool(embeddable)
        if public_stats_viewable is not None:
            new_status["publicStatsViewable"] = bool(public_stats_viewable)
        # publish_at ì˜ˆì•½ì€ privacyStatus ê°€ private ì¼ ë•Œë§Œ ìœ íš¨
        if new_status.get("publishAt") and new_status.get("privacyStatus") != "private":
            # ì˜ˆì•½ ë„£ëŠ”ë° public ì´ë©´ YouTube ê°€ ê±°ë¶€ â€” ëª…ì‹œì ìœ¼ë¡œ private ë¡œ ë‚´ë¦¼
            new_status["privacyStatus"] = "private"

        body = {
            "id": str(video_id).strip(),
            "snippet": new_snippet,
            "status": new_status,
        }
        try:
            resp = self.youtube.videos().update(
                part="snippet,status",
                body=body,
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ì˜ìƒ ì—…ë°ì´íŠ¸ ì‹¤íŒ¨: {e}") from e
        return {
            "video_id": resp.get("id") or video_id,
            "snippet": resp.get("snippet") or {},
            "status": resp.get("status") or {},
        }

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> dict:
        """ê¸°ì¡´ ì˜ìƒì˜ ì¸ë„¤ì¼ êµì²´."""
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        if not os.path.exists(thumbnail_path):
            raise YouTubeUploadError(f"ì¸ë„¤ì¼ íŒŒì¼ì´ ì—†ìŠµë‹ˆë‹¤: {thumbnail_path}")
        mime = "image/png"
        lower = thumbnail_path.lower()
        if lower.endswith(".jpg") or lower.endswith(".jpeg"):
            mime = "image/jpeg"
        elif lower.endswith(".webp"):
            mime = "image/webp"
        try:
            self.youtube.thumbnails().set(
                videoId=str(video_id).strip(),
                media_body=MediaFileUpload(thumbnail_path, mimetype=mime),
            ).execute(num_retries=3)
        except Exception as e:
            raise YouTubeUploadError(_friendly_youtube_error("썸네일 교체 실패", e)) from e
        return {"video_id": video_id, "thumbnail_path": thumbnail_path}

    # ---------- Playlists ----------

    def list_playlists(self, max_results: int = 50) -> list[dict]:
        self._ensure()
        try:
            resp = self.youtube.playlists().list(
                part="snippet,status,contentDetails",
                mine=True,
                maxResults=max(1, min(int(max_results or 50), 50)),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        out = []
        for it in resp.get("items") or []:
            sn = it.get("snippet") or {}
            cd = it.get("contentDetails") or {}
            st = it.get("status") or {}
            thumbs = sn.get("thumbnails") or {}
            thumb = None
            for key in ("medium", "high", "default"):
                t = thumbs.get(key)
                if t and t.get("url"):
                    thumb = t["url"]
                    break
            out.append({
                "playlist_id": it.get("id"),
                "title": sn.get("title") or "",
                "description": sn.get("description") or "",
                "thumbnail": thumb,
                "item_count": cd.get("itemCount"),
                "privacy_status": st.get("privacyStatus"),
                "published_at": sn.get("publishedAt"),
            })
        return out

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "private",
    ) -> dict:
        self._ensure()
        if privacy_status not in VALID_PRIVACY:
            raise YouTubeUploadError(
                f"privacy_status ê°’ì´ ìœ íš¨í•˜ì§€ ì•ŠìŠµë‹ˆë‹¤: {privacy_status!r}"
            )
        if not title or not title.strip():
            raise YouTubeUploadError("ìž¬ìƒëª©ë¡ title ì´ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            resp = self.youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": title.strip(),
                        "description": description or "",
                    },
                    "status": {"privacyStatus": privacy_status},
                },
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ ìƒì„± ì‹¤íŒ¨: {e}") from e
        return {"playlist_id": resp.get("id"), "title": title.strip()}

    def update_playlist(
        self,
        playlist_id: str,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        privacy_status: Optional[str] = None,
    ) -> dict:
        self._ensure()
        if not playlist_id:
            raise YouTubeUploadError("playlist_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            cur = self.youtube.playlists().list(
                part="snippet,status",
                id=playlist_id,
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        items = cur.get("items") or []
        if not items:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ì„ ì°¾ì„ ìˆ˜ ì—†ìŠµë‹ˆë‹¤: {playlist_id}")
        cur_sn = items[0].get("snippet") or {}
        cur_st = items[0].get("status") or {}
        new_sn = {
            "title": title if title is not None else (cur_sn.get("title") or ""),
            "description": (
                description if description is not None
                else (cur_sn.get("description") or "")
            ),
        }
        new_st = dict(cur_st)
        if privacy_status is not None:
            if privacy_status not in VALID_PRIVACY:
                raise YouTubeUploadError(
                    f"privacy_status ê°’ì´ ìœ íš¨í•˜ì§€ ì•ŠìŠµë‹ˆë‹¤: {privacy_status!r}"
                )
            new_st["privacyStatus"] = privacy_status
        try:
            resp = self.youtube.playlists().update(
                part="snippet,status",
                body={"id": playlist_id, "snippet": new_sn, "status": new_st},
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ ì—…ë°ì´íŠ¸ ì‹¤íŒ¨: {e}") from e
        return {"playlist_id": resp.get("id"), "snippet": resp.get("snippet") or {}}

    def delete_playlist(self, playlist_id: str) -> None:
        self._ensure()
        if not playlist_id:
            raise YouTubeUploadError("playlist_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            self.youtube.playlists().delete(id=playlist_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ ì‚­ì œ ì‹¤íŒ¨: {e}") from e

    def list_playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
    ) -> dict:
        self._ensure()
        if not playlist_id:
            raise YouTubeUploadError("playlist_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            req: dict = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": max(1, min(int(max_results or 50), 50)),
            }
            if page_token:
                req["pageToken"] = page_token
            resp = self.youtube.playlistItems().list(**req).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ í•­ëª© ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        out = []
        for it in resp.get("items") or []:
            sn = it.get("snippet") or {}
            cd = it.get("contentDetails") or {}
            thumbs = sn.get("thumbnails") or {}
            thumb = None
            for key in ("medium", "high", "default"):
                t = thumbs.get(key)
                if t and t.get("url"):
                    thumb = t["url"]
                    break
            out.append({
                "item_id": it.get("id"),
                "video_id": cd.get("videoId") or (sn.get("resourceId") or {}).get("videoId"),
                "position": sn.get("position"),
                "title": sn.get("title") or "",
                "thumbnail": thumb,
                "published_at": sn.get("publishedAt"),
            })
        return {
            "items": out,
            "next_page_token": resp.get("nextPageToken"),
            "total_results": (resp.get("pageInfo") or {}).get("totalResults"),
        }

    def add_to_playlist(self, playlist_id: str, video_id: str) -> dict:
        self._ensure()
        if not playlist_id or not video_id:
            raise YouTubeUploadError("playlist_id ë˜ëŠ” video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            resp = self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ í•­ëª© ì¶”ê°€ ì‹¤íŒ¨: {e}") from e
        return {"item_id": resp.get("id"), "playlist_id": playlist_id, "video_id": video_id}

    def add_to_playlist_if_missing(self, playlist_id: str, video_id: str) -> dict:
        """Add a video to a playlist only when it is not already present."""
        self._ensure()
        if not playlist_id or not video_id:
            raise YouTubeUploadError("playlist_id ë˜ëŠ” video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        token = None
        while True:
            data = self.list_playlist_items(
                playlist_id,
                max_results=50,
                page_token=token,
            )
            for item in data.get("items") or []:
                if str(item.get("video_id") or "").strip() == str(video_id).strip():
                    return {
                        "item_id": item.get("item_id"),
                        "playlist_id": playlist_id,
                        "video_id": video_id,
                        "already_present": True,
                    }
            token = data.get("next_page_token")
            if not token:
                break
        result = self.add_to_playlist(playlist_id, video_id)
        return {**result, "already_present": False}

    def remove_from_playlist(self, item_id: str) -> None:
        self._ensure()
        if not item_id:
            raise YouTubeUploadError("item_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            self.youtube.playlistItems().delete(id=item_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ìž¬ìƒëª©ë¡ í•­ëª© ì œê±° ì‹¤íŒ¨: {e}") from e

    # ---------- Comments ----------

    def list_comment_threads(
        self,
        video_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
        order: str = "time",
    ) -> dict:
        """ì˜ìƒì˜ ìµœìƒìœ„ ëŒ“ê¸€ ìŠ¤ë ˆë“œ. `order` ëŠ” "time" ë˜ëŠ” "relevance"."""
        self._ensure()
        if not video_id:
            raise YouTubeUploadError("video_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            req: dict = {
                "part": "snippet,replies",
                "videoId": str(video_id).strip(),
                "maxResults": max(1, min(int(max_results or 50), 100)),
                "order": order if order in ("time", "relevance") else "time",
                "textFormat": "plainText",
            }
            if page_token:
                req["pageToken"] = page_token
            resp = self.youtube.commentThreads().list(**req).execute()
        except Exception as e:
            raise YouTubeUploadError(_friendly_youtube_error("댓글 조회 실패", e)) from e
        out = []
        for it in resp.get("items") or []:
            sn = (it.get("snippet") or {})
            top = ((sn.get("topLevelComment") or {}).get("snippet") or {})
            replies_block = (it.get("replies") or {}).get("comments") or []
            replies = []
            for r in replies_block:
                rs = r.get("snippet") or {}
                replies.append({
                    "comment_id": r.get("id"),
                    "author": rs.get("authorDisplayName") or "",
                    "author_channel_id": (rs.get("authorChannelId") or {}).get("value"),
                    "text": rs.get("textDisplay") or "",
                    "like_count": rs.get("likeCount"),
                    "published_at": rs.get("publishedAt"),
                    "updated_at": rs.get("updatedAt"),
                })
            out.append({
                "thread_id": it.get("id"),
                "top_comment_id": (sn.get("topLevelComment") or {}).get("id"),
                "author": top.get("authorDisplayName") or "",
                "author_channel_id": (top.get("authorChannelId") or {}).get("value"),
                "text": top.get("textDisplay") or "",
                "like_count": top.get("likeCount"),
                "published_at": top.get("publishedAt"),
                "updated_at": top.get("updatedAt"),
                "total_reply_count": sn.get("totalReplyCount") or 0,
                "can_reply": sn.get("canReply"),
                "replies": replies,
            })
        return {
            "items": out,
            "next_page_token": resp.get("nextPageToken"),
            "total_results": (resp.get("pageInfo") or {}).get("totalResults"),
        }

    def list_channel_comment_threads(
        self,
        channel_youtube_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
        order: str = "time",
    ) -> dict:
        """Top-level comment threads across this channel, matching Studio comments."""
        self._ensure()
        channel_youtube_id = str(channel_youtube_id or "").strip()
        if not channel_youtube_id:
            raise YouTubeUploadError("channel_youtube_id 가 비어 있습니다.")
        try:
            req: dict = {
                "part": "snippet,replies",
                "allThreadsRelatedToChannelId": channel_youtube_id,
                "maxResults": max(1, min(int(max_results or 50), 100)),
                "order": order if order in ("time", "relevance") else "time",
                "textFormat": "plainText",
            }
            if page_token:
                req["pageToken"] = page_token
            resp = self.youtube.commentThreads().list(**req).execute()
        except Exception as e:
            raise YouTubeUploadError(_friendly_youtube_error("댓글 조회 실패", e)) from e
        out = []
        for it in resp.get("items") or []:
            sn = (it.get("snippet") or {})
            top = ((sn.get("topLevelComment") or {}).get("snippet") or {})
            replies_block = (it.get("replies") or {}).get("comments") or []
            replies = []
            for r in replies_block:
                rs = r.get("snippet") or {}
                replies.append({
                    "comment_id": r.get("id"),
                    "author": rs.get("authorDisplayName") or "",
                    "author_channel_id": (rs.get("authorChannelId") or {}).get("value"),
                    "text": rs.get("textDisplay") or "",
                    "like_count": rs.get("likeCount"),
                    "published_at": rs.get("publishedAt"),
                    "updated_at": rs.get("updatedAt"),
                })
            out.append({
                "thread_id": it.get("id"),
                "video_id": sn.get("videoId"),
                "top_comment_id": (sn.get("topLevelComment") or {}).get("id"),
                "author": top.get("authorDisplayName") or "",
                "author_channel_id": (top.get("authorChannelId") or {}).get("value"),
                "text": top.get("textDisplay") or "",
                "like_count": top.get("likeCount"),
                "published_at": top.get("publishedAt"),
                "updated_at": top.get("updatedAt"),
                "total_reply_count": sn.get("totalReplyCount") or 0,
                "can_reply": sn.get("canReply"),
                "replies": replies,
            })
        return {
            "items": out,
            "next_page_token": resp.get("nextPageToken"),
            "total_results": (resp.get("pageInfo") or {}).get("totalResults"),
        }

    def reply_to_comment(self, parent_comment_id: str, text: str) -> dict:
        """ê¸°ì¡´ ëŒ“ê¸€ ìŠ¤ë ˆë“œì— ë‹µê¸€ ìž‘ì„±."""
        self._ensure()
        if not parent_comment_id or not text or not text.strip():
            raise YouTubeUploadError("parent_comment_id ë˜ëŠ” text ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            resp = self.youtube.comments().insert(
                part="snippet",
                body={
                    "snippet": {
                        "parentId": parent_comment_id,
                        "textOriginal": text.strip(),
                    }
                },
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(_friendly_youtube_error("댓글 답변 실패", e)) from e
        sn = resp.get("snippet") or {}
        return {
            "comment_id": resp.get("id"),
            "text": sn.get("textDisplay") or text.strip(),
            "author": sn.get("authorDisplayName") or "",
            "published_at": sn.get("publishedAt"),
        }

    def set_comment_moderation(
        self,
        comment_id: str,
        status: str,
        ban_author: bool = False,
    ) -> None:
        """ëŒ“ê¸€ ëª¨ë”ë ˆì´ì…˜ ìƒíƒœ ë³€ê²½.

        status: "heldForReview" | "published" | "rejected"
        """
        self._ensure()
        if status not in ("heldForReview", "published", "rejected"):
            raise YouTubeUploadError(
                f"moderation status ê°’ì´ ìœ íš¨í•˜ì§€ ì•ŠìŠµë‹ˆë‹¤: {status!r}"
            )
        try:
            self.youtube.comments().setModerationStatus(
                id=comment_id,
                moderationStatus=status,
                banAuthor=bool(ban_author),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ëŒ“ê¸€ ëª¨ë”ë ˆì´ì…˜ ì‹¤íŒ¨: {e}") from e

    def delete_comment(self, comment_id: str) -> None:
        """ëŒ“ê¸€ ì‚­ì œ (ë³¸ì¸ ì˜ìƒì˜ ëŒ“ê¸€ë§Œ)."""
        self._ensure()
        if not comment_id:
            raise YouTubeUploadError("comment_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            self.youtube.comments().delete(id=comment_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ëŒ“ê¸€ ì‚­ì œ ì‹¤íŒ¨: {e}") from e

    def mark_comment_as_spam(self, comment_id: str) -> None:
        """ëŒ“ê¸€ì„ ìŠ¤íŒ¸ìœ¼ë¡œ ì‹ ê³ ."""
        self._ensure()
        if not comment_id:
            raise YouTubeUploadError("comment_id ê°€ ë¹„ì–´ìžˆìŠµë‹ˆë‹¤.")
        try:
            self.youtube.comments().markAsSpam(id=comment_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ëŒ“ê¸€ ìŠ¤íŒ¸ ì²˜ë¦¬ ì‹¤íŒ¨: {e}") from e

    # ---------- Categories ----------

    def list_video_categories(self, region_code: str = "KR") -> list[dict]:
        """ì¹´í…Œê³ ë¦¬ ë“œë¡­ë‹¤ìš´ ë°ì´í„°."""
        self._ensure()
        try:
            resp = self.youtube.videoCategories().list(
                part="snippet",
                regionCode=region_code or "KR",
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"ì¹´í…Œê³ ë¦¬ ì¡°íšŒ ì‹¤íŒ¨: {e}") from e
        out = []
        for it in resp.get("items") or []:
            sn = it.get("snippet") or {}
            # assignable=False ì¸ ì¹´í…Œê³ ë¦¬ëŠ” ì—…ë¡œë“œ ì‹œ ì“¸ ìˆ˜ ì—†ìŒ
            if not sn.get("assignable", True):
                continue
            out.append({
                "category_id": it.get("id"),
                "title": sn.get("title") or "",
            })
        return out


def _to_int(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except Exception:
        return None
