"""v1.1.55 — ComfyUI 이미지 생성 서비스 (Flux.2 Dev + Turbo LoRA)

로컬/네트워크 ComfyUI 인스턴스에 Flux.2 Dev 기반 text-to-image 워크플로를
제출한다. 비용 0 (로컬 GPU 사용). 레퍼런스 이미지는 아직 미지원
(`supports_reference_images=False`) — 추후 Flux Kontext 또는 IPAdapter 로
확장 가능.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from app.config import COMFYUI_WORKFLOWS_DIR
from app.services.image.base import BaseImageService
from app.services import comfyui_client


# 워크플로 JSON 파일 매핑 (레퍼런스 이미지 없을 때)
_WORKFLOW_FILES = {
    "comfyui-flux2-turbo": "flux2_turbo_text2img.json",
    "comfyui-z-image-turbo": "z_image_turbo_text2img.json",
    "comfyui-sd15": "sd15_text2img.json",
    "comfyui-toonyou": "toonyou_beta6_text2img.json",
    "comfyui-revanimated": "revanimated_v2_text2img.json",
    "comfyui-meinamix": "meinamix_v12_text2img.json",
    "comfyui-dreamshaper-xl": "dreamshaper_xl_lightning_text2img.json",
    "comfyui-dreamshaper-xl-vector": "dreamshaper_xl_vector_text2img.json",
    "comfyui-dreamshaper-xl-longtube": "dreamshaper_xl_longtube_text2img.json",
    "comfyui-dreamshaper-xl-longtube-2k": "dreamshaper_xl_longtube_2k_text2img.json",
    "comfyui-dreamshaper-xl-longtube-3k": "dreamshaper_xl_longtube_3k_text2img.json",
    # Qwen-Image-Edit 는 t2i 전용 워크플로가 없음 (레퍼런스 필수). ref 워크플로만 등록.
}

# v1.1.61: 레퍼런스 이미지가 있을 때 사용할 전용 워크플로.
# SD1.5/SDXL → IPAdapter Plus, Flux.2 → Redux, Z-Image → img2img 폴백.
_WORKFLOW_FILES_REF = {
    "comfyui-flux2-turbo": "flux2_turbo_text2img_ref.json",
    "comfyui-z-image-turbo": "z_image_turbo_text2img_ref.json",
    "comfyui-sd15": "sd15_text2img_ref.json",
    "comfyui-toonyou": "toonyou_beta6_text2img_ref.json",
    "comfyui-revanimated": "revanimated_v2_text2img_ref.json",
    "comfyui-meinamix": "meinamix_v12_text2img_ref.json",
    "comfyui-dreamshaper-xl": "dreamshaper_xl_lightning_text2img_ref.json",
    "comfyui-qwen-image-edit-2509": "qwen_image_edit_2509_text2img_ref.json",
}

# 모델별 표시명
_DISPLAY_NAMES = {
    "comfyui-flux2-turbo": "ComfyUI Flux.2 Turbo (local)",
    "comfyui-z-image-turbo": "ComfyUI Z-Image Turbo (local, fast)",
    "comfyui-sd15": "ComfyUI SD 1.5 (local, ultra-fast)",
    "comfyui-toonyou": "ComfyUI ToonYou Beta 6 (local, cartoon)",
    "comfyui-revanimated": "ComfyUI ReV Animated v2 Rebirth (local, 2.5D)",
    "comfyui-meinamix": "ComfyUI MeinaMix v12 (local, anime)",
    "comfyui-dreamshaper-xl": "ComfyUI DreamShaper XL Lightning (local, SDXL)",
    "comfyui-dreamshaper-xl-vector": "ComfyUI DreamShaper XL + Vector Art (카툰/벡터, local)",
    "comfyui-dreamshaper-xl-longtube": "ComfyUI DreamShaper XL + LongTube Style 4K (커스텀, local)",
    "comfyui-dreamshaper-xl-longtube-2k": "ComfyUI DreamShaper XL + LongTube Style 2K (커스텀, local)",
    "comfyui-dreamshaper-xl-longtube-3k": "ComfyUI DreamShaper XL + LongTube Style 3K (커스텀, local)",
    "comfyui-qwen-image-edit-2509": "ComfyUI Qwen-Image-Edit 2509 fp8 (local, ref 필수)",
}

# SDXL 계열 (1024 훈련) — 해상도 강제 매핑 대상
_SDXL_FAMILY = {"comfyui-dreamshaper-xl", "comfyui-dreamshaper-xl-vector", "comfyui-dreamshaper-xl-longtube", "comfyui-dreamshaper-xl-longtube-2k", "comfyui-dreamshaper-xl-longtube-3k"}

_SDXL_DIMS = {
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "1:1":  (1024, 1024),
    "3:4":  (832, 1088),
    "4:3":  (1088, 832),
}

# Qwen-Image 계열 (1328 native, 64 배수 권장). 레퍼런스 필수.
_QWEN_FAMILY = {"comfyui-qwen-image-edit-2509"}

_QWEN_DIMS = {
    "16:9": (1344, 768),
    "9:16": (768, 1344),
    "1:1":  (1024, 1024),
    "3:4":  (896, 1152),
    "4:3":  (1152, 896),
}

# 사용자 `image_negative_prompt` 가 비어 있을 때의 기본값.
DEFAULT_NEGATIVE_PROMPT = (
    "blurry, low quality, watermark, text, letters, words, numbers, subtitles, "
    "captions, typography, logo, sign, writing, font, label, alphabet, "
    "handwriting, printed text, any text, title, caption, inscription, "
    "distorted, ugly, deformed, bad anatomy, extra fingers, extra limbs, "
    "extra legs, five legs, extra arms, mutated hands, fused limbs, "
    "malformed limbs, too many legs, too many arms, jpeg artifacts"
)

# SD 1.5 계열 (512 훈련) — 해상도 강제 매핑 대상
_SD15_FAMILY = {"comfyui-sd15", "comfyui-toonyou", "comfyui-revanimated", "comfyui-meinamix"}

# SD 1.5 는 512 기준 훈련 → 큰 해상도는 품질 저하. aspect_ratio 별로 강제 클램프.
_SD15_DIMS = {
    "16:9": (768, 448),
    "9:16": (448, 768),
    "1:1":  (512, 512),
    "3:4":  (512, 640),
    "4:3":  (640, 512),
}


class ComfyUIImageService(BaseImageService):
    """Flux.2 Dev + Turbo LoRA (8 steps, cfg 1.0) 로컬 추론."""

    # v1.1.61: 로컬 ComfyUI 는 레퍼런스 이미지 픽셀을 모델에 안 넣는다 (IPAdapter/Redux
    # 필요, 설치 난이도 높음). 레퍼런스 첨부 시 자동으로 nano-banana-3 로 폴백되게
    # False 유지. 스타일은 global_style 텍스트로 유도한다.
    supports_reference_images: bool = False

    # 호출부에서 세팅 가능: `service.negative_prompt = config.get("image_negative_prompt", "")`
    # 비어있으면 DEFAULT_NEGATIVE_PROMPT 사용.
    negative_prompt: str = ""

    def __init__(self, model_id: str = "comfyui-flux2-turbo"):
        self.model_id = model_id
        self.display_name = _DISPLAY_NAMES.get(model_id, "ComfyUI (local)")

        is_qwen = model_id in _QWEN_FAMILY

        # Qwen-Image-Edit 는 t2i 전용 워크플로가 존재하지 않음 (레퍼런스 필수).
        # 그 외 모델은 기본(t2i) 워크플로 로드.
        self._template = None
        wf_name = _WORKFLOW_FILES.get(model_id)
        if wf_name:
            wf_path = Path(COMFYUI_WORKFLOWS_DIR) / wf_name
            if not wf_path.exists():
                raise FileNotFoundError(f"워크플로 JSON 누락: {wf_path}")
            with open(wf_path, "r", encoding="utf-8") as fh:
                self._template = json.load(fh)
        elif not is_qwen:
            raise ValueError(f"Unknown comfyui image model: {model_id}")

        # 레퍼런스 워크플로 (있으면 로드, 없으면 None → 레퍼런스 들어와도 기본 워크플로로 폴백)
        ref_wf_name = _WORKFLOW_FILES_REF.get(model_id)
        self._template_ref = None
        if ref_wf_name:
            ref_path = Path(COMFYUI_WORKFLOWS_DIR) / ref_wf_name
            if ref_path.exists():
                with open(ref_path, "r", encoding="utf-8") as fh:
                    self._template_ref = json.load(fh)

        # Qwen 은 레퍼런스 필수 → 인스턴스 레벨에서 플래그 뒤집고 ref 워크플로 존재 보장.
        if is_qwen:
            if self._template_ref is None:
                raise FileNotFoundError(
                    f"Qwen-Image-Edit 레퍼런스 워크플로 JSON 누락: {ref_wf_name}"
                )
            # 인스턴스 속성으로 덮어써서 클래스 기본값(False) 와 분리.
            self.supports_reference_images = True

    @staticmethod
    def _guess_aspect(w: int, h: int) -> str:
        """입력 w/h 에서 가장 가까운 aspect_ratio 키 추정."""
        if w == h:
            return "1:1"
        r = w / h
        if r >= 1.6:
            return "16:9"
        if r >= 1.2:
            return "4:3"
        if r <= 0.625:
            return "9:16"
        if r <= 0.85:
            return "3:4"
        return "1:1"

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
        reference_images: Optional[list[str]] = None,
    ) -> str:
        # SD 1.5 는 512 기준 훈련 → input 해상도 무시하고 aspect 로 강제 매핑.
        # 그 외 (Flux.2 / Z-Image) 는 width/height 16 배수만 맞춰 그대로 사용.
        if self.model_id in _SD15_FAMILY:
            aspect = self._guess_aspect(width, height)
            w, h = _SD15_DIMS.get(aspect, (512, 512))
        elif self.model_id in _SDXL_FAMILY:
            aspect = self._guess_aspect(width, height)
            w, h = _SDXL_DIMS.get(aspect, (1024, 1024))
        elif self.model_id in _QWEN_FAMILY:
            aspect = self._guess_aspect(width, height)
            w, h = _QWEN_DIMS.get(aspect, (1024, 1024))
        else:
            w = max(16, (int(width) // 16) * 16)
            h = max(16, (int(height) // 16) * 16)
        seed = random.randint(0, 2**31 - 1)
        prefix = f"longtube/{Path(output_path).stem}"

        neg = (self.negative_prompt or "").strip() or DEFAULT_NEGATIVE_PROMPT

        # Qwen-Image-Edit: 레퍼런스 필수. 첫 번째 ref 를 ComfyUI 서버에 업로드하고
        # LoadImage 노드에 파일명을 꽂는다. 없으면 즉시 실패 (조용한 폴백 금지).
        if self.model_id in _QWEN_FAMILY:
            if not reference_images:
                raise RuntimeError(
                    "Qwen-Image-Edit 2509 은 레퍼런스 이미지가 필수입니다. "
                    "프로젝트에 스타일/캐릭터 레퍼런스를 등록하거나 다른 모델을 선택하세요."
                )
            ref_path = reference_images[0]
            uploaded_name = await comfyui_client.upload_image(ref_path)
            final_prompt_text = (prompt or "").strip() or "an image"
            subs = {
                "PROMPT": final_prompt_text,
                "NEGATIVE": neg,
                "WIDTH": w,
                "HEIGHT": h,
                "SEED": seed,
                "PREFIX": prefix,
                "REF_IMAGE": uploaded_name,
            }
            print(
                f"[comfyui-image] qwen-image-edit-2509 {w}x{h} "
                f"ref={uploaded_name} "
                f"prompt_head={final_prompt_text[:180]!r}"
            )
            template = self._template_ref
            graph = comfyui_client.render_workflow(template, subs)
            prompt_id = await comfyui_client.submit(graph)
            print(f"[comfyui-image] submitted {self.model_id} prompt_id={prompt_id} {w}x{h}")
            entry = await comfyui_client.wait_for(prompt_id, total_timeout=600.0)
            await comfyui_client.download_first_output(
                entry, output_path, kinds=("images",)
            )
            print(f"[comfyui-image] saved → {output_path}")
            return output_path

        # v1.1.61: 그 외 로컬 ComfyUI 는 레퍼런스 이미지 픽셀을 모델로 주입하지 않는다
        # (IPAdapter/Redux 설치 난이도 높음). 레퍼런스 들어와도 기본 워크플로로 실행.
        # 스타일은 global_style/프롬프트 텍스트로 유도.
        final_prompt_text = (prompt or "").strip() or "an image"

        # LoRA 트리거 워드 자동 삽입
        if self.model_id == "comfyui-dreamshaper-xl-vector":
            if "vector" not in final_prompt_text.lower():
                final_prompt_text = f"vector, {final_prompt_text}"
        elif self.model_id.startswith("comfyui-dreamshaper-xl-longtube"):
            if "longtubestyle" not in final_prompt_text.lower():
                final_prompt_text = f"longtubestyle, simple cartoon illustration, round head, thick outlines, {final_prompt_text}"
        subs = {
            "PROMPT": final_prompt_text,
            "NEGATIVE": neg,
            "WIDTH": w,
            "HEIGHT": h,
            "SEED": seed,
            "PREFIX": prefix,
        }
        print(
            f"[comfyui-image] {self.model_id} {w}x{h} "
            f"prompt_head={final_prompt_text[:180]!r}"
        )

        graph = comfyui_client.render_workflow(self._template, subs)
        prompt_id = await comfyui_client.submit(graph)
        print(f"[comfyui-image] submitted {self.model_id} prompt_id={prompt_id} {w}x{h}")
        entry = await comfyui_client.wait_for(prompt_id, total_timeout=300.0)
        await comfyui_client.download_first_output(
            entry, output_path, kinds=("images",)
        )
        print(f"[comfyui-image] saved → {output_path}")
        return output_path
