"""Kling video generation service — JWT auth, global endpoint, async"""
import asyncio
import base64
import hmac
import hashlib
import json
import time
import os
from typing import Optional

import httpx

from app.services.video.base import BaseVideoService
from app.services.video.subprocess_helper import run_subprocess, find_ffmpeg
from app import config as cfg

# Global endpoint (not Beijing)
KLING_BASE = "https://api.klingai.com"
KLING_IMAGE2VIDEO = "/v1/videos/image2video"


def _b64url(data: bytes) -> str:
    """Base64URL encoding without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _generate_jwt(access_key: str, secret_key: str, expire_seconds: int = 1800) -> str:
    """Generate JWT token (HS256) using only stdlib — no PyJWT needed."""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": access_key,
        "exp": now + expire_seconds,
        "nbf": now - 5,
    }
    header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header_b64}.{payload_b64}".encode()
    signature = hmac.new(secret_key.encode(), signing_input, hashlib.sha256).digest()
    sig_b64 = _b64url(signature)
    return f"{header_b64}.{payload_b64}.{sig_b64}"


class KlingService(BaseVideoService):
    def __init__(self):
        self.model_id = "kling-v2"
        self.display_name = "Kling V2"

    def _get_headers(self) -> dict:
        ak = os.environ.get("KLING_ACCESS_KEY", "") or getattr(cfg, "KLING_ACCESS_KEY", "")
        sk = os.environ.get("KLING_SECRET_KEY", "") or getattr(cfg, "KLING_SECRET_KEY", "")
        token = _generate_jwt(ak, sk)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        ak = os.environ.get("KLING_ACCESS_KEY", "") or getattr(cfg, "KLING_ACCESS_KEY", "")
        sk = os.environ.get("KLING_SECRET_KEY", "") or getattr(cfg, "KLING_SECRET_KEY", "")
        if not ak or not sk:
            raise ValueError("Kling API keys not configured (KLING_ACCESS_KEY / KLING_SECRET_KEY)")

        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # Map aspect ratio
        kling_ratio = "16:9"
        if aspect_ratio == "9:16":
            kling_ratio = "9:16"
        elif aspect_ratio == "1:1":
            kling_ratio = "1:1"

        async with httpx.AsyncClient(timeout=600) as client:
            # Submit task
            resp = await client.post(
                f"{KLING_BASE}{KLING_IMAGE2VIDEO}",
                headers=self._get_headers(),
                json={
                    "model_name": "kling-v2",
                    "image": image_b64,
                    "prompt": prompt or "smooth cinematic camera motion",
                    "duration": "5",
                    "mode": "std",
                    "aspect_ratio": kling_ratio,
                },
            )
            resp.raise_for_status()
            resp_data = resp.json()
            if resp_data.get("code") != 0:
                raise RuntimeError(f"Kling API error: {resp_data.get('message', resp_data)}")
            task_id = resp_data["data"]["task_id"]

            # Poll for completion (max ~10 min)
            for _ in range(120):
                await asyncio.sleep(5)
                status_resp = await client.get(
                    f"{KLING_BASE}{KLING_IMAGE2VIDEO}/{task_id}",
                    headers=self._get_headers(),
                )
                data = status_resp.json().get("data", {})
                task_status = data.get("task_status", "")

                if task_status == "succeed":
                    video_url = data["task_result"]["videos"][0]["url"]
                    vid_resp = await client.get(video_url)

                    # Mux with audio if available
                    if audio_path and os.path.exists(audio_path):
                        temp_path = output_path.replace(".mp4", "_kling_raw.mp4")
                        with open(temp_path, "wb") as f:
                            f.write(vid_resp.content)

                        try:
                            ffmpeg_bin = find_ffmpeg()
                        except RuntimeError as e:
                            print(f"[kling] ffmpeg mux skipped — {e}")
                            ffmpeg_bin = ""
                        if not ffmpeg_bin:
                            mux_rc, mux_err = -1, b"ffmpeg not found"
                        else:
                            # Non-blocking ffmpeg mux
                            cmd = [
                                ffmpeg_bin, "-y",
                                "-i", temp_path,
                                "-i", audio_path,
                                "-map", "0:v", "-map", "1:a",
                                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-shortest",
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
                            print(f"[kling] ffmpeg mux failed rc={mux_rc}: {(mux_err or b'')[:300]}")
                            # Fallback: use raw video without audio
                            os.rename(temp_path, output_path) if os.path.exists(temp_path) else None
                        else:
                            try:
                                os.remove(temp_path)
                            except:
                                pass
                    else:
                        with open(output_path, "wb") as f:
                            f.write(vid_resp.content)

                    return output_path

                elif task_status == "failed":
                    msg = data.get("task_status_msg", "unknown error")
                    raise RuntimeError(f"Kling generation failed: {msg}")

        raise TimeoutError("Kling video generation timed out (10 min)")
