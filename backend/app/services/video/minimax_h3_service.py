"""Local MiniMax H3 first-frame image-to-video service.

This runtime is intentionally isolated from LongTube's main ComfyUI server.
It starts once on port 8190, keeps the process alive, and never calls `/free`
between tagged cuts or after the render.  Consecutive prompts therefore reuse
the already-loaded H3 weights and ComfyUI cache.
"""
from __future__ import annotations

import asyncio
import json
import random
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.config import (
    COMFYUI_WORKFLOWS_DIR,
    MINIMAX_H3_BASE_URL,
    MINIMAX_H3_COMFYUI_DIR,
    MINIMAX_H3_PYTHON,
    MINIMAX_H3_ROOT,
)
from app.services.cancel_ctx import raise_if_cancelled
from app.services.video.base import BaseVideoService


MODEL_ID = "local-minimax-h3"
DISPLAY_NAME = "로컬영상미니맥스"
_WORKFLOW_FILE = "minimax_h3_i2v.json"
_START_LOCK = threading.Lock()
_PROCESS: subprocess.Popen | None = None


def _dimensions(aspect_ratio: str) -> tuple[int, int]:
    """Return the tested low-resolution H3 canvas for local batch rendering."""
    if aspect_ratio == "9:16":
        return 352, 608
    if aspect_ratio == "1:1":
        return 448, 448
    if aspect_ratio == "3:4":
        return 416, 544
    return 608, 352


def build_minimax_h3_i2v_prompt(video_tag: str) -> str:
    """Compile a script video tag into the official H3 I2VA field contract."""
    raw_prompt = str(video_tag or "").strip()
    if not raw_prompt:
        raise ValueError("MiniMax H3 영상 태그 프롬프트가 비어 있습니다.")
    if all(
        field in raw_prompt
        for field in (
            "integrated_multimodal_description:",
            "overall_soundscape:",
            "non_diegetic_music:",
        )
    ):
        return raw_prompt
    prompt = " ".join(raw_prompt.split())
    return (
        "For the target video, at 0.00 seconds into the target video, "
        "<Picture 1> (from [Shot 1]) is fully referenced.\n\n"
        "integrated_multimodal_description: [Shot 1] "
        f"{prompt} Preserve the exact subject identity, clothing, object count, "
        "period details, lighting, camera angle, composition, and background established "
        "by <Picture 1>. Keep one continuous shot with no cut and no readable text.\n\n"
        "overall_soundscape: N/A\n\n"
        "non_diegetic_music: N/A"
    )


def video_tag_prompt(cut_data: dict | None) -> str:
    """Return the canonical per-cut H3 tag. Untagged cuts return an empty string."""
    if not isinstance(cut_data, dict):
        return ""
    value = cut_data.get("video_tag")
    if isinstance(value, str):
        return value.strip()
    return ""


def has_video_tag(cut_data: dict | None) -> bool:
    return bool(video_tag_prompt(cut_data))


class MiniMaxH3VideoService(BaseVideoService):
    model_id = MODEL_ID
    display_name = DISPLAY_NAME

    def __init__(self, model_id: str = MODEL_ID):
        if model_id != MODEL_ID:
            raise ValueError(f"Unknown MiniMax H3 model: {model_id}")
        workflow_path = Path(COMFYUI_WORKFLOWS_DIR) / _WORKFLOW_FILE
        if not workflow_path.exists():
            raise FileNotFoundError(f"워크플로 JSON 누락: {workflow_path}")
        self._template = json.loads(workflow_path.read_text(encoding="utf-8"))
        self._batch_ready = False

    @staticmethod
    def _validate_runtime() -> None:
        required = (
            Path(MINIMAX_H3_PYTHON),
            Path(MINIMAX_H3_COMFYUI_DIR) / "main.py",
            Path(MINIMAX_H3_ROOT) / "models" / "diffusion_models"
            / "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
            Path(MINIMAX_H3_ROOT) / "models" / "text_encoders"
            / "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            Path(MINIMAX_H3_ROOT) / "models" / "vae"
            / "minimax_h3_video_vae_fp16.safetensors",
        )
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            raise FileNotFoundError("MiniMax H3 로컬 런타임 누락: " + ", ".join(missing))

    @staticmethod
    def _server_ready_sync() -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                queue_response = client.get(f"{MINIMAX_H3_BASE_URL}/queue")
                node_response = client.get(
                    f"{MINIMAX_H3_BASE_URL}/object_info/MiniMaxH3ImageToVideo"
                )
                return (
                    queue_response.status_code == 200
                    and node_response.status_code == 200
                    and "MiniMaxH3ImageToVideo" in node_response.json()
                )
        except Exception:
            return False

    @classmethod
    def _start_server_sync(cls) -> None:
        global _PROCESS
        with _START_LOCK:
            if cls._server_ready_sync():
                return
            cls._validate_runtime()
            logs_dir = Path(MINIMAX_H3_ROOT) / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = logs_dir / "longtube_h3.log"
            stderr_path = logs_dir / "longtube_h3.err.log"
            user_dir = Path(MINIMAX_H3_ROOT) / "user"
            user_dir.mkdir(parents=True, exist_ok=True)
            command = [
                str(MINIMAX_H3_PYTHON),
                "main.py",
                "--disable-auto-launch",
                "--listen", "127.0.0.1",
                "--port", "8190",
                "--base-directory", str(MINIMAX_H3_ROOT),
                "--user-directory", str(user_dir),
                "--database-url", f"sqlite:///{(user_dir / 'comfyui.db').as_posix()}",
                "--reserve-vram", "4",
            ]
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            stdout_handle = open(stdout_path, "ab", buffering=0)
            stderr_handle = open(stderr_path, "ab", buffering=0)
            try:
                _PROCESS = subprocess.Popen(
                    command,
                    cwd=str(MINIMAX_H3_COMFYUI_DIR),
                    stdin=subprocess.DEVNULL,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    creationflags=creation_flags,
                )
            finally:
                stdout_handle.close()
                stderr_handle.close()

            deadline = time.monotonic() + 180.0
            while time.monotonic() < deadline:
                if _PROCESS.poll() is not None:
                    raise RuntimeError(
                        f"MiniMax H3 서버가 시작 중 종료되었습니다 (exit={_PROCESS.returncode}). "
                        f"로그: {stderr_path}"
                    )
                if cls._server_ready_sync():
                    print(f"[minimax-h3] server ready pid={_PROCESS.pid} url={MINIMAX_H3_BASE_URL}")
                    return
                time.sleep(1.0)
            raise TimeoutError(f"MiniMax H3 서버 시작 시간 초과: {MINIMAX_H3_BASE_URL}")

    async def ensure_server(self) -> None:
        if await asyncio.to_thread(self._server_ready_sync):
            return
        await asyncio.to_thread(self._start_server_sync)

    async def prepare_batch(self) -> None:
        """Initialize the isolated server once for a consecutive render batch."""
        if self._batch_ready:
            return
        await self.ensure_server()
        self._batch_ready = True
        print("[minimax-h3] consecutive batch ready; weights will remain loaded")

    @staticmethod
    async def _upload_image(image_path: str) -> str:
        upload_name = f"longtube_{uuid.uuid4().hex[:10]}_{Path(image_path).name}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            with open(image_path, "rb") as handle:
                response = await client.post(
                    f"{MINIMAX_H3_BASE_URL}/upload/image",
                    files={"image": (upload_name, handle, "application/octet-stream")},
                    data={"overwrite": "true", "type": "input"},
                )
        if response.status_code != 200:
            raise RuntimeError(f"MiniMax H3 이미지 업로드 실패 {response.status_code}: {response.text[:400]}")
        payload = response.json()
        return payload.get("name") or upload_name

    @staticmethod
    async def _submit(graph: dict, client_id: str) -> str:
        raise_if_cancelled("minimax-h3-submit")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{MINIMAX_H3_BASE_URL}/prompt",
                json={"prompt": graph, "client_id": client_id},
            )
        if response.status_code != 200:
            raise RuntimeError(f"MiniMax H3 제출 실패 {response.status_code}: {response.text[:600]}")
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"MiniMax H3 prompt_id 누락: {response.text[:600]}")
        return str(prompt_id)

    @staticmethod
    async def _wait(prompt_id: str, timeout: float = 1800.0) -> dict:
        deadline = asyncio.get_running_loop().time() + timeout
        async with httpx.AsyncClient(timeout=30.0) as client:
            while asyncio.get_running_loop().time() < deadline:
                raise_if_cancelled("minimax-h3-wait")
                response = await client.get(f"{MINIMAX_H3_BASE_URL}/history/{prompt_id}")
                response.raise_for_status()
                entry = response.json().get(prompt_id)
                if entry:
                    status = entry.get("status") or {}
                    status_name = status.get("status_str")
                    if status_name == "error":
                        raise RuntimeError(
                            "MiniMax H3 생성 실패: "
                            + json.dumps(status.get("messages") or status, ensure_ascii=False)[-1200:]
                        )
                    if status.get("completed") or status_name == "success" or entry.get("outputs"):
                        return entry
                await asyncio.sleep(1.5)
        raise TimeoutError(f"MiniMax H3 생성 시간 초과: {prompt_id}")

    @staticmethod
    async def _download(entry: dict, output_path: str) -> None:
        outputs = entry.get("outputs") or {}
        target = None
        for node_outputs in outputs.values():
            if not isinstance(node_outputs, dict):
                continue
            for kind in ("videos", "gifs", "images"):
                assets = node_outputs.get(kind)
                if assets:
                    target = assets[0]
                    break
            if target:
                break
        if not target:
            raise RuntimeError("MiniMax H3 결과 영상이 없습니다.")
        query = urlencode(
            {
                "filename": target.get("filename", ""),
                "subfolder": target.get("subfolder", ""),
                "type": target.get("type", "output"),
            }
        )
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.get(f"{MINIMAX_H3_BASE_URL}/view?{query}")
        response.raise_for_status()
        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
        audio_start_offset: float = 0.0,
    ) -> str:
        if not output_path:
            raise ValueError("output_path required")
        if not Path(image_path).exists():
            raise FileNotFoundError(f"입력 이미지 없음: {image_path}")
        await self.prepare_batch()
        raise_if_cancelled("minimax-h3-upload")
        uploaded_name = await self._upload_image(image_path)
        width, height = _dimensions(aspect_ratio)
        prefix = f"LongTubeMiniMaxH3/{Path(output_path).stem}_{uuid.uuid4().hex[:8]}"
        substitutions = {
            "INPUT_IMAGE_NAME": uploaded_name,
            "PROMPT": build_minimax_h3_i2v_prompt(prompt),
            "WIDTH": width,
            "HEIGHT": height,
            "LENGTH": 124,
            "SEED": random.randint(0, 2**31 - 1),
            "STEPS": 20,
            "PREFIX": prefix,
        }
        from app.services.comfyui_client import render_workflow

        graph = render_workflow(self._template, substitutions)
        client_id = f"longtube-minimax-h3-{uuid.uuid4().hex[:12]}"
        prompt_id = await self._submit(graph, client_id)
        print(
            f"[minimax-h3] submitted prompt_id={prompt_id} {width}x{height} "
            f"frames=124 steps=20; weights kept loaded"
        )
        entry = await self._wait(prompt_id)
        await self._download(entry, output_path)
        print(f"[minimax-h3] saved -> {output_path}")
        return output_path
