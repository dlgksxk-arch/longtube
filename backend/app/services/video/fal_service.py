"""Fal.ai video generation service (Seedance etc.) — async REST API"""
import asyncio
import base64
import io
import os
from typing import Optional

import httpx

from app.services.video.base import BaseVideoService
from app.services.video.subprocess_helper import run_subprocess, find_ffmpeg
from app.services.cancel_ctx import raise_if_cancelled  # v1.2.25 cancel 방어
from app import config as cfg
from app.config import CUT_VIDEO_DURATION


def _get_fal_key() -> str:
    return os.environ.get("FAL_KEY", "") or getattr(cfg, "FAL_KEY", "")

# Model ID mapping — internal LongTube id → fal.ai queue path
FAL_MODEL_MAP = {
    # Seedance (ByteDance)
    "seedance-lite":    "fal-ai/bytedance/seedance/v1/lite/image-to-video",
    "seedance-1.0":     "fal-ai/bytedance/seedance/v1/pro/image-to-video",
    "seedance-1.5-pro": "fal-ai/bytedance/seedance/v1.5/pro/image-to-video",
    # LTX Video 2.0 (Lightricks, fast & pro variants)
    "ltx2-fast":        "fal-ai/ltx-2/image-to-video/fast",
    "ltx2-pro":         "fal-ai/ltx-2/image-to-video",
    # Kling (via fal.ai — newer versions only; legacy kling-v2 uses native Kling API)
    "kling-2.5-turbo":  "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
    "kling-2.6-pro":    "fal-ai/kling-video/v2.6/pro/image-to-video",
}

FAL_QUEUE_URL = "https://queue.fal.run"

# Max long-side after downscale. 1280 is a safe sweet spot for Seedance input
# (model generates 720p-ish output anyway) and keeps base64 payload < 1 MB.
MAX_INPUT_LONG_SIDE = 1280
JPEG_QUALITY = 85


def _downscale_image_to_jpeg_bytes(image_path: str) -> tuple[bytes, str]:
    """Downscale image with Pillow if available, return (bytes, mime).

    Falls back to reading raw bytes if Pillow is not installed, so this
    function must not crash the caller on ImportError.
    """
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        with open(image_path, "rb") as f:
            data = f.read()
        ext = os.path.splitext(image_path)[1].lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        print(f"[fal] Pillow not installed — sending raw {mime} ({len(data)} bytes). Install 'Pillow' in backend for auto-downscale.")
        return data, mime

    img = Image.open(image_path)
    # Drop alpha for JPEG
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    long_side = max(w, h)
    if long_side > MAX_INPUT_LONG_SIDE:
        scale = MAX_INPUT_LONG_SIDE / long_side
        new_size = (int(w * scale), int(h * scale))
        img = img.resize(new_size, Image.LANCZOS)
        print(f"[fal] downscaled {w}x{h} → {new_size[0]}x{new_size[1]}")
    else:
        print(f"[fal] image {w}x{h} already <= {MAX_INPUT_LONG_SIDE}, no downscale")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    data = buf.getvalue()
    return data, "image/jpeg"


class FalVideoService(BaseVideoService):
    def __init__(self, model_id: str = "seedance-lite"):
        self.model_id = model_id
        self.display_name = FAL_MODEL_MAP.get(model_id, model_id)
        self._fal_model = FAL_MODEL_MAP.get(model_id, model_id)

    def _app_id(self) -> str:
        """Extract fal.ai app id for queue status/result URLs.

        Full model path like 'fal-ai/bytedance/seedance/v1/pro/image-to-video'
        maps to app id 'fal-ai/bytedance' in the queue API. status/result are
        addressed by app id, not full model path (that's a POST-only path).
        """
        parts = self._fal_model.split("/")
        if len(parts) >= 2:
            return "/".join(parts[:2])
        return self._fal_model

    def _headers(self) -> dict:
        return {
            "Authorization": f"Key {_get_fal_key()}",
            "Content-Type": "application/json",
        }

    async def _upload_image(self, client: httpx.AsyncClient, image_path: str) -> str:
        """Return data-URL for the image, downscaled to cap base64 size."""
        data, mime = _downscale_image_to_jpeg_bytes(image_path)
        b64 = base64.b64encode(data).decode()
        data_url = f"data:{mime};base64,{b64}"
        kb = len(data_url) / 1024
        print(f"[fal] payload image data-url: {kb:.1f} KB ({mime})")
        if kb > 4096:
            print(f"[fal] WARNING: payload > 4 MB — fal.ai queue may reject. Consider lowering MAX_INPUT_LONG_SIDE.")
        return data_url

    @staticmethod
    def _safe_json(resp: httpx.Response, where: str) -> dict:
        """Parse response as JSON. On failure raise with HTTP code + raw body prefix."""
        code = resp.status_code
        raw = resp.text or ""
        if not raw.strip():
            raise RuntimeError(f"Fal {where} HTTP {code} returned EMPTY body (len=0). Headers={dict(resp.headers)}")
        try:
            return resp.json()
        except Exception as e:
            raise RuntimeError(
                f"Fal {where} HTTP {code} non-JSON body (len={len(raw)}): {raw[:400]!r}"
            ) from e

    @staticmethod
    async def _post_with_retries(
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: dict,
        json_body: dict,
        label: str = "submit",
        max_attempts: int = 4,
        base_delay: float = 2.0,
    ) -> httpx.Response:
        """POST with retry on transient failures.

        v1.1.44: submit POST 도 재시도 대상에 추가. 과거엔 submit 한 번이 409/429/5xx
        로 터지면 그 컷이 즉시 죽었고, 120컷 중 수십 개가 연쇄적으로 실패하는 사고로
        이어졌다. 재시도 정책은 `_get_with_retries` 와 동일하다:

        - HTTP 409/429/5xx → 지수 backoff 2s → 4s → 8s
        - 401/403/404/400 → 영구 에러, 즉시 반환 (호출자가 raise)
        - TransportError / TimeoutException → 네트워크 에러, 재시도
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.post(url, headers=headers, json=json_body)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Fal {label} network error after {attempt} attempts: {type(e).__name__}: {e}"
                    ) from e
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[fal] {label} transport err '{e}' (attempt {attempt}/{max_attempts}), retry in {delay:.1f}s")
                await asyncio.sleep(delay)
                continue

            code = resp.status_code
            transient = code == 409 or code == 429 or code >= 500
            if code < 400:
                if attempt > 1:
                    print(f"[fal] {label} succeeded on attempt {attempt}")
                return resp
            if not transient or attempt >= max_attempts:
                return resp  # 호출자가 에러 메시지 포맷해서 raise 하도록
            delay = base_delay * (2 ** (attempt - 1))
            body_prefix = (resp.text or "")[:200]
            print(
                f"[fal] {label} HTTP {code} transient "
                f"(attempt {attempt}/{max_attempts}), retry in {delay:.1f}s. body={body_prefix!r}"
            )
            await asyncio.sleep(delay)
        if last_exc:
            raise RuntimeError(f"Fal {label} exhausted retries: {last_exc}") from last_exc
        raise RuntimeError(f"Fal {label} exhausted retries")

    @staticmethod
    async def _get_with_retries(
        client: httpx.AsyncClient,
        url: str,
        *,
        headers: Optional[dict] = None,
        label: str = "fal",
        max_attempts: int = 4,
        base_delay: float = 2.0,
    ) -> httpx.Response:
        """GET with retry on transient failures.

        v1.1.39: 'Fal video download HTTP 409' 같은 일시적인 CDN/큐 에러로 컷이
        한 번에 죽는 걸 막는다. 재시도 대상:

        - HTTP 409 (Conflict)    — Fal CDN 이 생성 직후 같은 URL 을 거절하는 케이스
        - HTTP 429 (Rate Limit)  — 쿼터 제한
        - HTTP 5xx               — 서버 이슈
        - httpx.TransportError / TimeoutException — 네트워크 끊김

        다른 4xx (401, 403, 404, 400 등) 는 영구 에러로 판단해 즉시 raise.
        exponential backoff: 2s → 4s → 8s.
        """
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.get(url, headers=headers)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                last_exc = e
                if attempt >= max_attempts:
                    raise RuntimeError(
                        f"Fal {label} network error after {attempt} attempts: {type(e).__name__}: {e}"
                    ) from e
                delay = base_delay * (2 ** (attempt - 1))
                print(f"[fal] {label} transport err '{e}' (attempt {attempt}/{max_attempts}), retry in {delay:.1f}s")
                await asyncio.sleep(delay)
                continue

            code = resp.status_code
            transient = code == 409 or code == 429 or code >= 500
            if code < 400:
                if attempt > 1:
                    print(f"[fal] {label} succeeded on attempt {attempt}")
                return resp
            if not transient or attempt >= max_attempts:
                return resp  # 호출자가 에러 메시지 포맷해서 raise 하도록
            delay = base_delay * (2 ** (attempt - 1))
            body_prefix = (resp.text or "")[:200]
            print(
                f"[fal] {label} HTTP {code} transient "
                f"(attempt {attempt}/{max_attempts}), retry in {delay:.1f}s. body={body_prefix!r}"
            )
            await asyncio.sleep(delay)
        # unreachable — loop either returns or raises
        if last_exc:
            raise RuntimeError(f"Fal {label} exhausted retries: {last_exc}") from last_exc
        raise RuntimeError(f"Fal {label} exhausted retries")

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        if not _get_fal_key():
            raise ValueError("FAL_KEY not configured")

        # v1.2.25: cancel 확인 — 영상 제출 금지.
        raise_if_cancelled(f"fal-video-submit:{self.model_id}")

        async with httpx.AsyncClient(timeout=600) as client:
            image_url = await self._upload_image(client, image_path)

            # Submit to queue
            submit_url = f"{FAL_QUEUE_URL}/{self._fal_model}"
            # v1.1.45: CUT_VIDEO_DURATION 와 sync. fal.ai 는 정수 초만 받는 모델이
            # 대부분이라 str(int(...)) 로 내려보낸다. 후처리 mux 단계에서 정확한
            # 길이로 한 번 더 trim 되기 때문에 여기서는 정수 근사로 충분하다.
            fal_duration = str(int(round(CUT_VIDEO_DURATION)))
            payload = {
                "image_url": image_url,
                "prompt": prompt or "smooth cinematic camera motion",
                "duration": fal_duration,
                "aspect_ratio": aspect_ratio,
            }
            print(f"[fal] POST {submit_url} (image_url len={len(image_url)})")
            submit_resp = await self._post_with_retries(
                client,
                submit_url,
                headers=self._headers(),
                json_body=payload,
                label="submit",
            )
            scode = submit_resp.status_code
            sbody = (submit_resp.text or "")[:500]
            print(f"[fal] submit ← HTTP {scode}, body[:500]={sbody!r}")

            if scode >= 400:
                raise RuntimeError(f"Fal submit HTTP {scode}: {sbody}")

            submit_data = self._safe_json(submit_resp, "submit")
            request_id = submit_data.get("request_id")

            if not request_id:
                raise RuntimeError(f"Fal submit HTTP {scode} has no request_id. body={submit_data}")

            print(f"[fal] submit accepted, request_id={request_id}")

            # Prefer fal-provided URLs (authoritative), else fall back to app-id form.
            # IMPORTANT: status/result are under the APP ID (e.g. 'fal-ai/bytedance'),
            # NOT the full model path. The full path is submit-only.
            app_id = self._app_id()
            status_url = submit_data.get("status_url") or f"{FAL_QUEUE_URL}/{app_id}/requests/{request_id}/status"
            result_url = submit_data.get("response_url") or f"{FAL_QUEUE_URL}/{app_id}/requests/{request_id}"
            print(f"[fal] status_url={status_url}")
            print(f"[fal] result_url={result_url}")

            for poll_i in range(120):
                # v1.2.25: polling 매 반복마다 cancel 체크 — 5초 sleep 낭비 없이 이탈.
                raise_if_cancelled(f"fal-video-poll:{self.model_id}")
                await asyncio.sleep(5)
                try:
                    status_resp = await asyncio.wait_for(
                        client.get(status_url, headers=self._headers()),
                        timeout=30,
                    )
                except asyncio.TimeoutError:
                    print(f"[fal] poll {poll_i}: status GET timed out (30s), retrying...")
                    continue
                except Exception as poll_err:
                    print(f"[fal] poll {poll_i}: status GET error: {poll_err}, retrying...")
                    continue
                pcode = status_resp.status_code
                if pcode >= 400:
                    pbody = (status_resp.text or "")[:400]
                    raise RuntimeError(f"Fal status HTTP {pcode}: {pbody}")
                status_data = self._safe_json(status_resp, "status")
                status = status_data.get("status", "")

                if poll_i % 6 == 0:  # log every ~30s
                    print(f"[fal] poll {poll_i}: status={status!r}")

                if status == "COMPLETED":
                    # Fetch result — v1.1.39: 일시적 5xx/409 는 재시도
                    result_resp = await self._get_with_retries(
                        client,
                        result_url,
                        headers=self._headers(),
                        label="result",
                    )
                    rcode = result_resp.status_code
                    if rcode >= 400:
                        rbody = (result_resp.text or "")[:400]
                        raise RuntimeError(f"Fal result HTTP {rcode}: {rbody}")
                    result_data = self._safe_json(result_resp, "result")

                    # Extract video URL
                    video_info = result_data.get("video", {})
                    video_url = video_info.get("url", "")
                    if not video_url:
                        raise RuntimeError(f"Fal result has no video URL: {result_data}")

                    # v1.1.39: 영상 다운로드 409/5xx 재시도. 과거엔 한 번 터지면
                    # 그 컷 전체가 죽어서 재생성 비용이 다시 드는 고통이 있었음.
                    print(f"[fal] completed, downloading {video_url}")
                    vid_resp = await self._get_with_retries(
                        client,
                        video_url,
                        headers=None,  # CDN URL 은 서명 포함 — 인증 헤더 넣지 않음
                        label="video download",
                    )
                    if vid_resp.status_code >= 400:
                        raise RuntimeError(
                            f"Fal video download HTTP {vid_resp.status_code} (재시도 소진)"
                        )

                    # Mux with audio if available
                    if audio_path and os.path.exists(audio_path):
                        temp_path = output_path.replace(".mp4", "_fal_raw.mp4")
                        with open(temp_path, "wb") as f:
                            f.write(vid_resp.content)

                        try:
                            ffmpeg_bin = find_ffmpeg()
                        except RuntimeError as e:
                            print(f"[fal] ffmpeg mux skipped — {e}")
                            ffmpeg_bin = ""
                        if not ffmpeg_bin:
                            mux_rc, mux_err = -1, b"ffmpeg not found"
                        else:
                            # v1.1.45: fal.ai 는 5초 클립을 반환한다. 음성이 더 짧아도
                            # `-shortest` 로 영상을 줄이지 않고, 음성을 `apad` 로 무음 패딩
                            # 한 뒤 `-t CUT_VIDEO_DURATION` 으로 고정 길이로 잘라낸다.
                            cmd = [
                                ffmpeg_bin, "-y",
                                "-i", temp_path,
                                "-i", audio_path,
                                "-map", "0:v", "-map", "1:a",
                                "-af", "apad",
                                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-t", str(CUT_VIDEO_DURATION),
                                output_path,
                            ]
                            try:
                                mux_rc, _, mux_err = await run_subprocess(
                                    cmd, timeout=300.0, capture_stdout=False, capture_stderr=True
                                )
                            except FileNotFoundError:
                                mux_rc, mux_err = -1, b"ffmpeg not found"
                            except asyncio.TimeoutError:
                                mux_rc, mux_err = -1, b"ffmpeg mux timed out"
                        if mux_rc != 0:
                            print(f"[fal] ffmpeg mux failed rc={mux_rc}: {(mux_err or b'')[:300]}")
                            if os.path.exists(temp_path):
                                os.rename(temp_path, output_path)
                        else:
                            try:
                                os.remove(temp_path)
                            except Exception:
                                pass
                    else:
                        with open(output_path, "wb") as f:
                            f.write(vid_resp.content)

                    return output_path

                elif status == "FAILED":
                    error = status_data.get("error", "unknown")
                    raise RuntimeError(f"Fal generation failed: {error}")

            raise TimeoutError("Fal video generation timed out (10 min)")
