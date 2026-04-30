"""ComfyUI local image-to-video service.

The Studio API exposes production-ready local ComfyUI video workflows. Older
removed local IDs are remapped in the factory so saved presets do not
accidentally launch missing workflows.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from app.config import COMFYUI_WORKFLOWS_DIR
from app.services.video.base import BaseVideoService
from app.services.video.prompt_builder import VIDEO_NEGATIVE_PROMPT
from app.services.video.wan_control import build_wan_track_coords
from app.services import comfyui_client


_WORKFLOW_FILES = {
    "comfyui-hunyuan15-480p": "hunyuan15_480p_i2v.json",
    "comfyui-wan22-ti2v-5b": "wan22_ti2v_5b_track_control.json",
}

_DISPLAY_NAMES = {
    "comfyui-hunyuan15-480p": "ComfyUI HunyuanVideo 1.5 480p (local)",
    "comfyui-wan22-ti2v-5b": "ComfyUI Wan2.2 TI2V-5B (local)",
}

# 모델별 기본 FPS. Wan 5B는 24fps 네이티브보다 16fps가 RTX 3090에서
# 훨씬 현실적이라, 먼저 안정적인 5초/81프레임 운용으로 붙인다.
_FPS_BY_MODEL = {
    "comfyui-hunyuan15-480p": 16,
    "comfyui-wan22-ti2v-5b": 16,
}

# 해상도 배수 요구사항 (width/height 가 이 값의 배수여야 함).
_DIM_MULTIPLE = {
    "comfyui-hunyuan15-480p": 16,
    "comfyui-wan22-ti2v-5b": 32,
}

# WAN/Hunyuan 계열은 프레임 수가 4n+1 형태.
_FRAME_QUANTIZE = {
    "comfyui-hunyuan15-480p": 4,
    "comfyui-wan22-ti2v-5b": 4,
}


def _wan_dims(aspect_ratio: str, multiple: int = 16) -> tuple[int, int]:
    """권장 해상도.

    640x384는 빠르지만 너무 흐리고 움직임도 약해 보인다. RTX 3090 24GB
    기준으로 16:9는 768x432 계열을 기본값으로 사용한다.
    """
    if aspect_ratio == "9:16":
        w, h = 384, 640
    elif aspect_ratio == "1:1":
        w, h = 512, 512
    elif aspect_ratio == "3:4":
        w, h = 448, 576
    else:  # 16:9
        w, h = 640, 384
    # 배수 보정
    w = (w // multiple) * multiple
    h = (h // multiple) * multiple
    return w, h


def _wan22_ti2v_dims(aspect_ratio: str, multiple: int = 32) -> tuple[int, int]:
    """Wan2.2 TI2V-5B quality-oriented 480p dimensions for RTX 3090."""
    if aspect_ratio == "9:16":
        w, h = 480, 864
    elif aspect_ratio == "1:1":
        w, h = 512, 512
    elif aspect_ratio == "3:4":
        w, h = 480, 640
    else:  # 16:9
        w, h = 864, 480
    w = (w // multiple) * multiple
    h = (h // multiple) * multiple
    return w, h


def _negative_for_model(model_id: str) -> str:
    if model_id == "comfyui-hunyuan15-480p":
        return (
            VIDEO_NEGATIVE_PROMPT
            + ", temporal ghost, temporal smear, frame echo, echo frame, onion skin, "
            + "transparent body copy, faded duplicate, semi-transparent duplicate, "
            + "overlapping duplicate, duplicate outline, duplicated contour, residual silhouette, "
            + "motion smear, character smear, face smear, body smear, edge echo, "
            + "low temporal consistency, inconsistent frame-to-frame identity"
        )
    if model_id == "comfyui-wan22-ti2v-5b":
        return (
            VIDEO_NEGATIVE_PROMPT
            + ", walking, running, foot lifting, leg crossing, kicking, stepping forward, "
            + "distorted gait, broken legs, duplicated limbs, melted legs, large arm swing"
        )
    return VIDEO_NEGATIVE_PROMPT


def _length_for(duration: float, fps: int, quantize: int = 4) -> int:
    """duration(초) → 프레임 수(quantize·n+1). 최소 quantize+1 프레임."""
    frames = int(round(max(1.0, float(duration)) * fps))
    rem = (frames - 1) % quantize
    if rem:
        frames += (quantize - rem)
    return max(quantize + 1, frames)


def _target_720_resolution(aspect_ratio: str) -> tuple[int, int]:
    if aspect_ratio == "9:16":
        return 720, 1280
    if aspect_ratio == "1:1":
        return 720, 720
    if aspect_ratio == "3:4":
        return 720, 960
    return 1280, 720


class ComfyUIVideoService(BaseVideoService):
    """Local ComfyUI I2V video generation."""

    def __init__(self, model_id: str = "comfyui-hunyuan15-480p"):
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

        # 0) 이전 모델(DreamShaper XL 등)이 VRAM 에 남아있으면 OOM 위험 → 해제
        await comfyui_client.free_memory(unload_models=True, free_memory=True)

        # 1) 소스 이미지를 ComfyUI 서버에 업로드 → filename 획득
        uploaded_name = await comfyui_client.upload_image(image_path)

        if self.model_id == "comfyui-wan22-ti2v-5b":
            w, h = _wan22_ti2v_dims(aspect_ratio, self.dim_multiple)
        else:
            w, h = _wan_dims(aspect_ratio, self.dim_multiple)
        length = _length_for(duration, self.fps, self.frame_quantize)
        seed = random.randint(0, 2**31 - 1)
        prefix = f"longtube/{Path(output_path).stem}"
        track_coords = "[]"
        track_strength = 1.0
        if self.model_id == "comfyui-wan22-ti2v-5b":
            track_coords = build_wan_track_coords(
                image_path=image_path,
                width=w,
                height=h,
                length=length,
                prompt=prompt,
            )
            track_strength = 1.2

        graph = comfyui_client.render_workflow(
            self._template,
            {
                "INPUT_IMAGE_NAME": uploaded_name,
                "PROMPT": (prompt or "").strip() or "a cinematic shot",
                "NEGATIVE": _negative_for_model(self.model_id),
                "WIDTH": w,
                "HEIGHT": h,
                "LENGTH": length,
                "FPS": self.fps,
                "SEED": seed,
                "PREFIX": prefix,
                "TRACK_COORDS": track_coords,
                "TRACK_STRENGTH": track_strength,
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

        # v2.1.1: AI 모델이 요청보다 짧은 영상을 생성하는 경우 → 정확히 duration 에 맞게 슬로모션
        await self._enforce_duration(output_path, duration)

        if self.model_id == "comfyui-hunyuan15-480p":
            await self._upscale_to_720(output_path, aspect_ratio)

        print(f"[comfyui-video] saved → {output_path}")
        return output_path

    @staticmethod
    async def _upscale_to_720(video_path: str, aspect_ratio: str) -> None:
        """Scale local Hunyuan output to 720-class delivery resolution."""
        import os
        from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess

        if not os.path.exists(video_path):
            return
        try:
            ffmpeg_bin = find_ffmpeg()
        except RuntimeError:
            print("[comfyui-video] 720 upscale skipped: ffmpeg not found")
            return

        w, h = _target_720_resolution(aspect_ratio)
        tmp_path = video_path + ".720p.mp4"
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
        )
        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart",
            tmp_path,
        ]
        try:
            rc, _, stderr = await run_subprocess(
                cmd,
                timeout=600.0,
                capture_stdout=False,
                capture_stderr=True,
            )
            if rc == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                os.replace(tmp_path, video_path)
                print(f"[comfyui-video] upscaled to {w}x{h} -> {video_path}")
            else:
                err = (stderr or b"").decode(errors="replace")[-300:]
                print(f"[comfyui-video] 720 upscale failed rc={rc}: {err}")
        except Exception as e:
            print(f"[comfyui-video] 720 upscale exception: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    @staticmethod
    async def _enforce_duration(video_path: str, target_duration: float) -> None:
        """생성된 영상이 target_duration보다 짧으면 setpts/atempo로 정확히 맞춤."""
        import os
        from app.services.video.subprocess_helper import find_ffmpeg, run_subprocess

        try:
            ffmpeg_bin = find_ffmpeg()
            ffprobe = ffmpeg_bin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
        except RuntimeError:
            return

        # 현재 영상 길이 측정
        try:
            rc, stdout, _ = await run_subprocess(
                [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "csv=p=0", video_path],
                timeout=30.0, capture_stdout=True, capture_stderr=False,
            )
            if rc != 0 or not stdout:
                return
            actual_dur = float((stdout or b"").decode().strip())
        except Exception:
            return

        if actual_dur <= 0 or actual_dur >= target_duration - 0.1:
            return  # 이미 충분히 길면 패스

        # 슬로모션 비율: 3.3초 → 5초 = setpts=1.515*PTS, atempo=0.66
        ratio = target_duration / actual_dur
        if ratio > 2.5:
            # 너무 짧으면 슬로모션도 부자연스러움 — 패스 (ensure_min_duration에서 루프 처리)
            print(f"[comfyui-video] too short ({actual_dur:.1f}s), ratio {ratio:.2f}x — skipping slowmo")
            return

        setpts = round(ratio, 4)
        atempo = round(1.0 / ratio, 4)
        # atempo 범위: 0.5~2.0. 범위 밖이면 체인 필요하지만 여기선 0.4~1.0 범위
        atempo = max(0.5, atempo)

        tmp_path = video_path + ".slowmo.mp4"
        cmd = [
            ffmpeg_bin, "-y", "-i", video_path,
            "-filter:v", f"setpts={setpts}*PTS",
            "-filter:a", f"atempo={atempo}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(target_duration),
            "-pix_fmt", "yuv420p",
            tmp_path,
        ]
        try:
            rc, _, stderr = await run_subprocess(cmd, timeout=120.0, capture_stdout=False, capture_stderr=True)
            if rc == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 100:
                os.replace(tmp_path, video_path)
                print(f"[comfyui-video] slowmo applied: {actual_dur:.1f}s → {target_duration:.1f}s (x{setpts})")
            else:
                err = (stderr or b"").decode(errors="replace")[-200:]
                print(f"[comfyui-video] slowmo failed rc={rc}: {err}")
        except Exception as e:
            print(f"[comfyui-video] slowmo exception: {e}")
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
