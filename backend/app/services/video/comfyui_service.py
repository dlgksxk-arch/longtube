"""v1.1.55 — ComfyUI 영상 생성 서비스 (WAN 2.2 I2V 14B + lightx2v 4-step LoRA)

이미지→영상 (image-to-video) 전용. 컷 이미지를 ComfyUI 에 업로드하고,
high-noise / low-noise 2단 샘플링을 4스텝으로 끝내는 경량 설정으로
5초 @ 16fps mp4 를 생성한다. fal.ai Kling/LTX 대비 비용 0 + 퀄리티 준수.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from app.config import COMFYUI_WORKFLOWS_DIR
from app.services.video.base import BaseVideoService
from app.services import comfyui_client


_WORKFLOW_FILES = {
    "comfyui-wan22-i2v-fast": "wan22_i2v_fast.json",
    "comfyui-wan22-5b": "wan22_ti2v_5b.json",
    "comfyui-ltxv-2b": "ltxv_2b_distilled_i2v.json",
    "comfyui-ltxv-13b": "ltxv_13b_distilled_i2v.json",
}

_DISPLAY_NAMES = {
    "comfyui-wan22-i2v-fast": "ComfyUI WAN 2.2 I2V 14B (local)",
    "comfyui-wan22-5b": "ComfyUI WAN 2.2 TI2V 5B (local)",
    "comfyui-ltxv-2b": "ComfyUI LTX Video 2B distilled (local, ultra-fast)",
    "comfyui-ltxv-13b": "ComfyUI LTX Video 13B distilled fp8 (local, quality)",
}

# 모델별 기본 FPS. 14B I2V = 16fps, 5B TI2V = 24fps, LTXV = 24fps.
_FPS_BY_MODEL = {
    "comfyui-wan22-i2v-fast": 16,
    "comfyui-wan22-5b": 24,
    "comfyui-ltxv-2b": 24,
    "comfyui-ltxv-13b": 24,
}

# 해상도 배수 요구사항 (width/height 가 이 값의 배수여야 함).
_DIM_MULTIPLE = {
    "comfyui-wan22-i2v-fast": 16,
    "comfyui-wan22-5b": 16,
    "comfyui-ltxv-2b": 32,
    "comfyui-ltxv-13b": 32,
}

# LTXV 는 프레임 수도 8n+1 형태 (WAN 은 4n+1).
_FRAME_QUANTIZE = {
    "comfyui-wan22-i2v-fast": 4,
    "comfyui-wan22-5b": 4,
    "comfyui-ltxv-2b": 8,
    "comfyui-ltxv-13b": 8,
}


def _wan_dims(aspect_ratio: str, multiple: int = 16) -> tuple[int, int]:
    """권장 해상도. 12GB VRAM + 속도 우선 → 640x384 계열 (v1.1.56).
    LTXV 는 32 배수 요구라 640x384 → 그대로 OK (둘 다 32로 나눠짐)."""
    if aspect_ratio == "9:16":
        w, h = 384, 640
    elif aspect_ratio == "1:1":
        w, h = 512, 512
    elif aspect_ratio == "3:4":
        w, h = 448, 576  # 432 는 32 배수 아니라 448 로 올림
    else:  # 16:9
        w, h = 640, 384
    # 배수 보정
    w = (w // multiple) * multiple
    h = (h // multiple) * multiple
    return w, h


def _length_for(duration: float, fps: int, quantize: int = 4) -> int:
    """duration(초) → 프레임 수(quantize·n+1). 최소 quantize+1 프레임."""
    frames = int(round(max(1.0, float(duration)) * fps))
    rem = (frames - 1) % quantize
    if rem:
        frames += (quantize - rem)
    return max(quantize + 1, frames)


class ComfyUIVideoService(BaseVideoService):
    """WAN 2.2 I2V (local GPU, 4-step lightx2v)."""

    def __init__(self, model_id: str = "comfyui-wan22-i2v-fast"):
        self.model_id = model_id
        self.display_name = _DISPLAY_NAMES.get(model_id, "ComfyUI (local)")
        self.fps = _FPS_BY_MODEL.get(model_id, 16)
        self.dim_multiple = _DIM_MULTIPLE.get(model_id, 16)
        self.frame_quantize = _FRAME_QUANTIZE.get(model_id, 4)
        wf_name = _WORKFLOW_FILES.get(model_id)
        if not wf_name:
            raise ValueError(f"Unknown comfyui video model: {model_id}")
        wf_path = Path(COMFYUI_WORKFLOWS_DIR) / wf_name
        if not wf_path.exists():
            raise FileNotFoundError(f"워크플로 JSON 누락: {wf_path}")
        with open(wf_path, "r", encoding="utf-8") as fh:
            self._template = json.load(fh)

    async def generate(
        self,
        image_path: str,
        audio_path: Optional[str] = None,
        duration: float = 5.0,
        output_path: str = "",
        aspect_ratio: str = "16:9",
        prompt: str = "",
    ) -> str:
        if not output_path:
            raise ValueError("output_path required")
        if not Path(image_path).exists():
            raise FileNotFoundError(f"입력 이미지 없음: {image_path}")

        # 1) 소스 이미지를 ComfyUI 서버에 업로드 → filename 획득
        uploaded_name = await comfyui_client.upload_image(image_path)

        w, h = _wan_dims(aspect_ratio, self.dim_multiple)
        length = _length_for(duration, self.fps, self.frame_quantize)
        seed = random.randint(0, 2**31 - 1)
        prefix = f"longtube/{Path(output_path).stem}"

        graph = comfyui_client.render_workflow(
            self._template,
            {
                "INPUT_IMAGE_NAME": uploaded_name,
                "PROMPT": (prompt or "").strip() or "a cinematic shot",
                "WIDTH": w,
                "HEIGHT": h,
                "LENGTH": length,
                "SEED": seed,
                "PREFIX": prefix,
            },
        )

        prompt_id = await comfyui_client.submit(graph)
        print(
            f"[comfyui-video] submitted {self.model_id} prompt_id={prompt_id} "
            f"{w}x{h} length={length} ({duration:.1f}s @ {self.fps}fps)"
        )
        # 14B I2V 는 느림. 충분한 타임아웃 (15분).
        entry = await comfyui_client.wait_for(prompt_id, total_timeout=900.0)
        await comfyui_client.download_first_output(
            entry, output_path, kinds=("videos", "gifs", "images"),
        )
        print(f"[comfyui-video] saved → {output_path}")
        return output_path
