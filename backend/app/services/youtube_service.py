"""YouTube Data API v3 upload service.

OAuth: InstalledAppFlow 로컬 데스크탑 플로우. 최초 1회 브라우저 팝업 인증 후
token.json 에 refresh token 저장. 이후부터는 자동 갱신.

주의: `upload()` 는 네트워크 I/O 가 있지만 의도적으로 **sync** 로 구현되어 있습니다.
FastAPI 라우터에서 `asyncio.to_thread(uploader.upload, ...)` 로 감싸 호출하세요.
(googleapiclient 자체가 blocking resumable upload 를 쓰므로 async 로 포장해 봐야
실제 이득이 없고, 라우터/서비스 간 sync/async 불일치만 유발합니다.)
"""
from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Optional, Callable

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from app.config import YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, BASE_DIR, DATA_DIR

# 업로드 + 썸네일 세팅 권한
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

# 전역 fallback 경로 (project_id 없이 생성된 uploader 를 위한 legacy 호환)
TOKEN_PATH = BASE_DIR / "token.json"
CLIENT_SECRET_PATH = BASE_DIR / "client_secret.json"


def _project_token_path(project_id: str) -> Path:
    """프로젝트별 token.json 경로.

    각 프로젝트 디렉토리 아래에 저장하면 프로젝트별로 다른 YouTube 계정을 연결할
    수 있습니다. `DATA_DIR/{project_id}/youtube_token.json` 형태.
    """
    return Path(DATA_DIR) / project_id / "youtube_token.json"


def _channel_token_path(channel_id: int) -> Path:
    """채널별 token.json 경로.

    딸깍 큐의 CH1~CH4 가 실제로 서로 다른 YouTube 채널에 업로드되도록,
    채널마다 별도의 OAuth 토큰을 저장한다.
    `BASE_DIR/token_ch{N}.json` 형태.
    """
    return BASE_DIR / f"token_ch{int(channel_id)}.json"

# Privacy enum 값 (YouTube API 표준)
VALID_PRIVACY = {"private", "unlisted", "public"}

# YouTube 카테고리 ID (대표적인 것만; 22=People & Blogs 기본값)
DEFAULT_CATEGORY_ID = "22"


class YouTubeAuthError(RuntimeError):
    """OAuth 설정/플로우 실패 시."""


class YouTubeUploadError(RuntimeError):
    """업로드/썸네일 API 호출 실패 시."""


class YouTubeUploader:
    def __init__(
        self,
        project_id: Optional[str] = None,
        channel_id: Optional[int] = None,
    ):
        """YouTube 업로더.

        토큰 우선순위:
          1. channel_id 지정 시 → `BASE_DIR/token_ch{N}.json`
          2. project_id 지정 시 → `DATA_DIR/{project_id}/youtube_token.json`
          3. 둘 다 None → 전역 `BASE_DIR/token.json` (legacy)

        Args:
            project_id: 프로젝트 ID.
            channel_id: 딸깍 채널 번호 (1~4). 지정하면 채널별 토큰을 사용한다.
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

    # ---------- OAuth ----------

    def authenticate(self) -> None:
        """OAuth 2.0 인증. 최초 1회 브라우저 인증 후 token.json 저장.

        이미 token.json 이 있으면 재사용. 만료됐으면 refresh_token 으로 자동 갱신.
        client_secret.json 이 없으면 env 의 YOUTUBE_CLIENT_ID/SECRET 로 즉석 생성.
        """
        creds = None

        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                raise YouTubeAuthError(f"token.json 로드 실패: {e}") from e

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    raise YouTubeAuthError(f"토큰 갱신 실패: {e}") from e
            else:
                if not CLIENT_SECRET_PATH.exists():
                    if not YOUTUBE_CLIENT_ID or not YOUTUBE_CLIENT_SECRET:
                        raise YouTubeAuthError(
                            "YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET 환경변수가 설정되지 "
                            "않았거나 client_secret.json 파일이 없습니다."
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
                        raise YouTubeAuthError(f"client_secret.json 생성 실패: {e}") from e

                try:
                    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_PATH), SCOPES)
                    creds = flow.run_local_server(port=8090)
                except Exception as e:
                    raise YouTubeAuthError(f"OAuth 로컬 서버 플로우 실패: {e}") from e

            try:
                self.token_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                raise YouTubeAuthError(f"token.json 저장 실패: {e}") from e

        try:
            self.youtube = build("youtube", "v3", credentials=creds)
        except Exception as e:
            raise YouTubeAuthError(f"youtube 클라이언트 빌드 실패: {e}") from e

    def is_authenticated(self) -> bool:
        """token.json 이 있고 유효한 scope 로 로드 가능한지 non-destructive 체크."""
        if not self.token_path.exists():
            return False
        try:
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        except Exception:
            return False
        return creds is not None and (creds.valid or bool(creds.refresh_token))

    def get_channel_info(self) -> dict:
        """현재 인증된 계정의 YouTube 채널 정보 조회.

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
            YouTubeAuthError: 인증 안 됐거나 API 호출 실패.
        """
        if self.youtube is None:
            self.authenticate()
        try:
            resp = self.youtube.channels().list(
                part="id,snippet,statistics",
                mine=True,
            ).execute()
        except Exception as e:
            raise YouTubeAuthError(f"채널 정보 조회 실패: {e}") from e

        items = resp.get("items") or []
        if not items:
            raise YouTubeAuthError(
                "인증된 계정에 연결된 YouTube 채널이 없습니다."
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
        """저장된 token.json 을 삭제해 다음 호출에서 재인증을 강제.

        프로젝트별 토큰이 설정돼 있으면 그 토큰만, 아니면 전역 토큰을 삭제합니다.

        Returns:
            실제로 파일을 지웠는지 여부.
        """
        if self.token_path.exists():
            try:
                self.token_path.unlink()
                return True
            except Exception as e:
                raise YouTubeAuthError(f"token.json 삭제 실패: {e}") from e
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
        """영상 업로드 + (선택) 썸네일 설정.

        Returns:
            {"video_id": str, "url": str}

        Raises:
            YouTubeUploadError: API 호출 실패 시.
        """
        if privacy not in VALID_PRIVACY:
            raise YouTubeUploadError(
                f"유효하지 않은 privacy 값: {privacy!r} (허용: {sorted(VALID_PRIVACY)})"
            )
        if not os.path.exists(video_path):
            raise YouTubeUploadError(f"영상 파일이 존재하지 않음: {video_path}")

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
                chunksize=10 * 1024 * 1024,
            )
            request = self.youtube.videos().insert(
                part="snippet,status",
                body=body,
                media_body=media,
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status and progress_callback:
                    try:
                        progress_callback(int(status.progress() * 100))
                    except Exception:
                        pass  # 콜백 실패는 업로드를 막으면 안 됨
        except Exception as e:
            raise YouTubeUploadError(f"영상 업로드 실패: {e}") from e

        video_id = response.get("id")
        if not video_id:
            raise YouTubeUploadError(f"업로드 응답에 video id 가 없음: {response!r}")

        # 썸네일 설정 (선택)
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
                ).execute()
            except Exception as e:
                # 썸네일 실패해도 영상 자체는 업로드 성공이므로 dict 에 에러만 기록
                return {
                    "video_id": video_id,
                    "url": f"https://youtube.com/watch?v={video_id}",
                    "thumbnail_error": str(e),
                }

        return {
            "video_id": video_id,
            "url": f"https://youtube.com/watch?v={video_id}",
        }

    # ---------- Delete ----------

    def delete_video(self, video_id: str) -> None:
        """업로드된 영상을 YouTube 에서 삭제.

        YouTube API 의 videos.delete 를 호출합니다. **복구 불가능** 한 작업이므로
        호출 전에 사용자에게 반드시 확인을 받아야 합니다. 라우터 레이어에서
        `confirm=True` 같은 명시적 플래그를 강제해 이중 안전장치를 두세요.

        Args:
            video_id: 삭제할 유튜브 video id (예: "dQw4w9WgXcQ").

        Raises:
            YouTubeUploadError: video_id 가 비었거나 API 호출이 실패한 경우.
            YouTubeAuthError: 인증 실패.
        """
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id 가 비어있어 삭제할 수 없습니다.")
        if self.youtube is None:
            self.authenticate()
        try:
            # videos.delete 는 성공 시 204 No Content — execute() 는 빈 dict 반환
            self.youtube.videos().delete(id=str(video_id).strip()).execute()
        except Exception as e:
            raise YouTubeUploadError(f"영상 삭제 실패: {e}") from e

    # ---------- Studio: 영상 조회/편집 (v1.1.31) ----------
    #
    # 이 아래 메서드들은 LongTube 파이프라인 밖에서 이미 업로드되어 있는 영상도
    # 관리하기 위한 일반 Studio 기능입니다. 모두 `youtube.force-ssl` + `youtube`
    # scope 로 동작 — 추가 scope 없이 videos/playlists/commentThreads 전체 편집
    # 가능. YouTube Analytics (조회수 그래프 등) 는 별도 scope 라 미구현.

    def _ensure(self) -> None:
        if self.youtube is None:
            self.authenticate()

    def list_my_videos(
        self,
        max_results: int = 50,
        page_token: Optional[str] = None,
        query: Optional[str] = None,
    ) -> dict:
        """내 채널에 업로드된 영상 목록.

        구현 노트: `search.list(forMine=True, type=video)` 는 **업로드 쿼터
        100 units** 를 쓰고 결과에 title/description/thumbnails/publishedAt 만
        내려줌. 상세(조회수, 길이, privacyStatus, categoryId) 가 필요하면
        이후 `videos.list(id=..,part=snippet,status,statistics,contentDetails)`
        로 보강 호출이 필요하지만, 여기서는 UI 가 목록만 빨리 받아야 하므로
        1차 응답을 그대로 반환하고 상세는 get_video 에서 따로 제공.

        Args:
            max_results: 1~50. YouTube 제한.
            page_token: 다음 페이지 토큰.
            query: 제목 검색어 (있으면 forMine + q).

        Returns:
            {"items": [...], "next_page_token": str|None, "total_results": int}
        """
        self._ensure()
        try:
            req_params: dict = {
                "part": "snippet",
                "forMine": True,
                "type": "video",
                "maxResults": max(1, min(int(max_results or 50), 50)),
                "order": "date",
            }
            if page_token:
                req_params["pageToken"] = page_token
            if query and query.strip():
                req_params["q"] = query.strip()
            resp = self.youtube.search().list(**req_params).execute()
        except Exception as e:
            raise YouTubeUploadError(f"영상 목록 조회 실패: {e}") from e

        items = []
        video_ids: list[str] = []
        for it in resp.get("items") or []:
            vid = ((it.get("id") or {}).get("videoId") or "").strip()
            if not vid:
                continue
            sn = it.get("snippet") or {}
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

        # 보강: videos.list 로 status + statistics + contentDetails 붙이기
        if video_ids:
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
                # 보강 실패해도 목록은 반환
                print(f"[youtube studio] videos.list 보강 실패 (non-fatal): {e}")

        return {
            "items": items,
            "next_page_token": resp.get("nextPageToken"),
            "prev_page_token": resp.get("prevPageToken"),
            "total_results": (resp.get("pageInfo") or {}).get("totalResults"),
        }

    def get_video(self, video_id: str) -> dict:
        """영상 1 건 상세.

        snippet + status + statistics + contentDetails 를 모두 포함.
        """
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id 가 비어있습니다.")
        try:
            resp = self.youtube.videos().list(
                part="snippet,status,statistics,contentDetails",
                id=str(video_id).strip(),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"영상 상세 조회 실패: {e}") from e
        items = resp.get("items") or []
        if not items:
            raise YouTubeUploadError(f"영상을 찾을 수 없습니다: {video_id}")
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
        """영상 메타데이터 업데이트.

        YouTube 의 videos.update 는 `part` 에 포함된 리소스 필드를 **통째로**
        덮어쓰므로 먼저 현재 값을 읽어와서 None 이 아닌 필드만 교체한 전체
        snippet/status 를 다시 보내는 merge 방식으로 구현합니다.

        예약 게시: `privacy_status="private"` + `publish_at=<RFC3339>` 를
        함께 넘기면 YouTube 가 해당 시각에 public 으로 자동 전환합니다. 이미
        public 인 영상에 publish_at 을 넣으면 API 가 400 을 돌려줍니다.

        Raises:
            YouTubeUploadError: API 실패.
        """
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id 가 비어있습니다.")
        if privacy_status is not None and privacy_status not in VALID_PRIVACY:
            raise YouTubeUploadError(
                f"privacy_status 값이 유효하지 않습니다: {privacy_status!r}"
            )

        # 현재 영상 상태 읽어오기 (merge 기반)
        try:
            cur_resp = self.youtube.videos().list(
                part="snippet,status",
                id=str(video_id).strip(),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"영상 현재 상태 조회 실패: {e}") from e
        cur_items = cur_resp.get("items") or []
        if not cur_items:
            raise YouTubeUploadError(f"영상을 찾을 수 없습니다: {video_id}")
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
        # publish_at 예약은 privacyStatus 가 private 일 때만 유효
        if new_status.get("publishAt") and new_status.get("privacyStatus") != "private":
            # 예약 넣는데 public 이면 YouTube 가 거부 — 명시적으로 private 로 내림
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
            raise YouTubeUploadError(f"영상 업데이트 실패: {e}") from e
        return {
            "video_id": resp.get("id") or video_id,
            "snippet": resp.get("snippet") or {},
            "status": resp.get("status") or {},
        }

    def set_thumbnail(self, video_id: str, thumbnail_path: str) -> dict:
        """기존 영상의 썸네일 교체."""
        self._ensure()
        if not video_id or not str(video_id).strip():
            raise YouTubeUploadError("video_id 가 비어있습니다.")
        if not os.path.exists(thumbnail_path):
            raise YouTubeUploadError(f"썸네일 파일이 없습니다: {thumbnail_path}")
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
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"썸네일 교체 실패: {e}") from e
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
            raise YouTubeUploadError(f"재생목록 조회 실패: {e}") from e
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
                f"privacy_status 값이 유효하지 않습니다: {privacy_status!r}"
            )
        if not title or not title.strip():
            raise YouTubeUploadError("재생목록 title 이 비어있습니다.")
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
            raise YouTubeUploadError(f"재생목록 생성 실패: {e}") from e
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
            raise YouTubeUploadError("playlist_id 가 비어있습니다.")
        try:
            cur = self.youtube.playlists().list(
                part="snippet,status",
                id=playlist_id,
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"재생목록 조회 실패: {e}") from e
        items = cur.get("items") or []
        if not items:
            raise YouTubeUploadError(f"재생목록을 찾을 수 없습니다: {playlist_id}")
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
                    f"privacy_status 값이 유효하지 않습니다: {privacy_status!r}"
                )
            new_st["privacyStatus"] = privacy_status
        try:
            resp = self.youtube.playlists().update(
                part="snippet,status",
                body={"id": playlist_id, "snippet": new_sn, "status": new_st},
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"재생목록 업데이트 실패: {e}") from e
        return {"playlist_id": resp.get("id"), "snippet": resp.get("snippet") or {}}

    def delete_playlist(self, playlist_id: str) -> None:
        self._ensure()
        if not playlist_id:
            raise YouTubeUploadError("playlist_id 가 비어있습니다.")
        try:
            self.youtube.playlists().delete(id=playlist_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"재생목록 삭제 실패: {e}") from e

    def list_playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
    ) -> dict:
        self._ensure()
        if not playlist_id:
            raise YouTubeUploadError("playlist_id 가 비어있습니다.")
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
            raise YouTubeUploadError(f"재생목록 항목 조회 실패: {e}") from e
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
            raise YouTubeUploadError("playlist_id 또는 video_id 가 비어있습니다.")
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
            raise YouTubeUploadError(f"재생목록 항목 추가 실패: {e}") from e
        return {"item_id": resp.get("id"), "playlist_id": playlist_id, "video_id": video_id}

    def remove_from_playlist(self, item_id: str) -> None:
        self._ensure()
        if not item_id:
            raise YouTubeUploadError("item_id 가 비어있습니다.")
        try:
            self.youtube.playlistItems().delete(id=item_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"재생목록 항목 제거 실패: {e}") from e

    # ---------- Comments ----------

    def list_comment_threads(
        self,
        video_id: str,
        max_results: int = 50,
        page_token: Optional[str] = None,
        order: str = "time",
    ) -> dict:
        """영상의 최상위 댓글 스레드. `order` 는 "time" 또는 "relevance"."""
        self._ensure()
        if not video_id:
            raise YouTubeUploadError("video_id 가 비어있습니다.")
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
            raise YouTubeUploadError(f"댓글 조회 실패: {e}") from e
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

    def reply_to_comment(self, parent_comment_id: str, text: str) -> dict:
        """기존 댓글 스레드에 답글 작성."""
        self._ensure()
        if not parent_comment_id or not text or not text.strip():
            raise YouTubeUploadError("parent_comment_id 또는 text 가 비어있습니다.")
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
            raise YouTubeUploadError(f"답글 작성 실패: {e}") from e
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
        """댓글 모더레이션 상태 변경.

        status: "heldForReview" | "published" | "rejected"
        """
        self._ensure()
        if status not in ("heldForReview", "published", "rejected"):
            raise YouTubeUploadError(
                f"moderation status 값이 유효하지 않습니다: {status!r}"
            )
        try:
            self.youtube.comments().setModerationStatus(
                id=comment_id,
                moderationStatus=status,
                banAuthor=bool(ban_author),
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"댓글 모더레이션 실패: {e}") from e

    def delete_comment(self, comment_id: str) -> None:
        """댓글 삭제 (본인 영상의 댓글만)."""
        self._ensure()
        if not comment_id:
            raise YouTubeUploadError("comment_id 가 비어있습니다.")
        try:
            self.youtube.comments().delete(id=comment_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"댓글 삭제 실패: {e}") from e

    def mark_comment_as_spam(self, comment_id: str) -> None:
        """댓글을 스팸으로 신고."""
        self._ensure()
        if not comment_id:
            raise YouTubeUploadError("comment_id 가 비어있습니다.")
        try:
            self.youtube.comments().markAsSpam(id=comment_id).execute()
        except Exception as e:
            raise YouTubeUploadError(f"댓글 스팸 처리 실패: {e}") from e

    # ---------- Categories ----------

    def list_video_categories(self, region_code: str = "KR") -> list[dict]:
        """카테고리 드롭다운 데이터."""
        self._ensure()
        try:
            resp = self.youtube.videoCategories().list(
                part="snippet",
                regionCode=region_code or "KR",
            ).execute()
        except Exception as e:
            raise YouTubeUploadError(f"카테고리 조회 실패: {e}") from e
        out = []
        for it in resp.get("items") or []:
            sn = it.get("snippet") or {}
            # assignable=False 인 카테고리는 업로드 시 쓸 수 없음
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
