"""v1.1.55 — ComfyUI 이미지 생성 서비스 (Flux.2 Dev + Turbo LoRA)

로컬/네트워크 ComfyUI 인스턴스에 Flux.2 Dev 기반 text-to-image 워크플로를
제출한다. 비용 0 (로컬 GPU 사용). 레퍼런스 이미지는 아직 미지원
(`supports_reference_images=False`) — 추후 Flux Kontext 또는 IPAdapter 로
확장 가능.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Optional

from app.config import COMFYUI_WORKFLOWS_DIR
from app.services.image.base import BaseImageService
from app.services import comfyui_client


def _safe_console(value) -> str:
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _pad_image_to_canvas(path: str, width: int, height: int) -> None:
    from PIL import Image

    image_path = Path(path)
    with Image.open(image_path) as src:
        img = src.convert("RGBA")
        canvas = Image.new("RGBA", (int(width), int(height)), (248, 246, 239, 255))
        img.thumbnail((int(width), int(height)), Image.Resampling.LANCZOS)
        x = (int(width) - img.width) // 2
        y = (int(height) - img.height) // 2
        canvas.alpha_composite(img, (x, y))
        canvas.convert("RGB").save(image_path)


_MYLORA_TRIGGER_PREFIX = "MYLORA, lt_roundhead_style"

# v2.0.75: 이전에는 trigger 외에 "warm beige cartoon icon, thick dark brown outline,
# simple flat editorial illustration, clean shape language" 4개를 강제로 prepend
# 했는데, 이 토큰들이 LoRA 학습 분포와 정확히 일치하지 않아 텍스트 가이드와
# LoRA 가 충돌해 결과가 흐물거리는 원인이었다. 트리거만 남기고 모두 제거.
_MYLORA_STYLE_PREFIX = _MYLORA_TRIGGER_PREFIX

# v2.0.75: 매체 자체 키워드(사진/세피아/흑백)만 차단. 카메라·조명·구도 용어
# (close up / macro / dramatic lighting / depth of field 등) 는 살려서 대본 LLM
# 이 만든 영화적 묘사가 화면에 반영되도록 한다.
_MYLORA_NEGATIVE_PROMPT = (
    "detailed background, scenery, room, city, corridor, landscape, furniture, "
    "rooftop, library, workbench, skyline, realistic, photorealistic, realistic photo, "
    "photograph, photographic, cinematic lighting, complex lighting, depth of field, "
    "sepia, black and white, monochrome, grayscale, vintage photo, historical photo, "
    "eyes, mouth, nose, eyebrows, facial features, face details, expression, "
    "second character, duplicate character, multiple characters, crowd, "
    "sign, placard, speech bubble, caption box, floating panel, "
    "colored background, gradient background, cast shadow, heavy shadow, "
    "tiny readable letters, keyboard letters, keycap symbols, screen text, "
    "logo, watermark, text, words, letters, numbers"
)

_MYLORA_REALISM_TOKENS = (
    "photorealistic",
    "photo-realistic",
    "realistic photo",
    "photograph",
    "photographic",
    "vintage photo",
    "historical photo",
    "black and white",
    "black-and-white",
    "monochrome",
    "grayscale",
    "sepia",
)

def _shape_mylora_prompt(prompt: str) -> str:
    scene = (prompt or "").strip()
    scene = re.sub(r"\bMYLORA\b\s*,?", "", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\blt_roundhead_style\b\s*,?", "", scene, flags=re.IGNORECASE)
    for token in _MYLORA_REALISM_TOKENS:
        scene = re.sub(re.escape(token), "", scene, flags=re.IGNORECASE)
    scene = re.sub(
        r"\b(scene|scenery|background|room|city|corridor|landscape|furniture|"
        r"rooftop|library|workbench|skyline|atmospheric|cinematic|dramatic|"
        r"detailed|complex|realistic|no readable text|white background)\b",
        "",
        scene,
        flags=re.IGNORECASE,
    )
    scene = re.sub(r"\s*,\s*,+", ",", scene)
    scene = re.sub(r"\s{2,}", " ", scene).strip(" ,.;")
    lowered = scene.lower()
    if re.search(r"\b(character|person|figure|mascot|round[- ]?head|faceless|writing_character)\b", lowered):
        if "writing" in lowered:
            subject = "character_pose, writing_character, single faceless round-head character, blank face"
            style = "warm honey-beige cartoon"
        else:
            subject = "front standing single faceless round-head character, blank face, arms at sides"
            style = "warm beige cartoon icon"
    elif "globe" in lowered:
        subject = "globe"
        style = "warm beige cartoon icon"
    else:
        subject = re.sub(r"\b(a|an|the|of|with|on|in|at|beside|above|under)\b", " ", scene, flags=re.IGNORECASE)
        subject = re.sub(r"\s{2,}", " ", subject).strip(" ,.;")
        if not subject:
            subject = "simple object icon"
        subject = f"daily_object, {subject}"
        style = "warm honey-beige cartoon object"
    return (
        f"{_MYLORA_TRIGGER_PREFIX}, {subject}, {style}, thick dark brown outline, white background"
    )
    # 사용자 프롬프트에 트리거가 이미 있다면 중복 방지 위해 한 번만 남게 제거
    scene = re.sub(r"\bMYLORA\b\s*,?", "", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\blt_roundhead_style\b\s*,?", "", scene, flags=re.IGNORECASE)
    for token in _MYLORA_REALISM_TOKENS:
        scene = re.sub(re.escape(token), "", scene, flags=re.IGNORECASE)
    scene = re.sub(r"\s*,\s*,+", ",", scene)
    scene = re.sub(r"\s{2,}", " ", scene).strip(" ,.;")
    if not scene:
        return _MYLORA_TRIGGER_PREFIX
    # v2.0.75: 이전의 "simplified icon scene of {scene}, white background,
    # no readable text" 강제 wrap 제거. 사용자/대본 LLM 이 적은 묘사를 그대로
    # 통과시키고 트리거만 앞에 붙인다.
    return f"{_MYLORA_TRIGGER_PREFIX}, {scene}"


def _apply_mylora_profile(graph: dict, shaped_prompt: str) -> None:
    text = (shaped_prompt or "").lower()
    if "writing_character" in text:
        lora_name = "MYLORA-step00002000.safetensors"
        strength = 0.65
    elif "front standing" in text and "round-head character" in text:
        lora_name = "MYLORA.safetensors"
        strength = 0.75
    else:
        lora_name = "MYLORA.safetensors"
        strength = 0.85

    for node in (graph or {}).values():
        if not isinstance(node, dict) or node.get("class_type") != "LoraLoader":
            continue
        inputs = node.setdefault("inputs", {})
        inputs["lora_name"] = lora_name
        inputs["strength_model"] = strength
        inputs["strength_clip"] = strength


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
    "comfyui-dreamshaper-xl-mylora": "dreamshaper_xl_mylora_text2img.json",
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
    "comfyui-dreamshaper-xl-mylora": "ComfyUI DreamShaper XL + MYLORA (local)",
    "comfyui-dreamshaper-xl-longtube": "ComfyUI DreamShaper XL + longtube_style_v1.safetensors (final, local)",
    "comfyui-dreamshaper-xl-longtube-2k": "ComfyUI DreamShaper XL + longtube_style_v1-step00002000.safetensors (2K, local)",
    "comfyui-dreamshaper-xl-longtube-3k": "ComfyUI DreamShaper XL + longtube_style_v1-step00003000.safetensors (3K, local)",
    "comfyui-qwen-image-edit-2509": "ComfyUI Qwen-Image-Edit 2509 fp8 (local, ref 필수)",
}

# SDXL 계열 (1024 훈련) — 해상도 강제 매핑 대상
_SDXL_FAMILY = {"comfyui-dreamshaper-xl", "comfyui-dreamshaper-xl-vector", "comfyui-dreamshaper-xl-mylora", "comfyui-dreamshaper-xl-longtube", "comfyui-dreamshaper-xl-longtube-2k", "comfyui-dreamshaper-xl-longtube-3k"}

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

    def _context_label(self) -> str:
        ctx = getattr(self, "progress_context", {}) or {}
        cut_number = ctx.get("cut_number")
        total_cuts = ctx.get("total_cuts")
        if cut_number and total_cuts:
            return f"컷 {cut_number}/{total_cuts}"
        if cut_number:
            return f"컷 {cut_number}"
        return "ComfyUI"

    def _emit_log(self, msg: str, level: str = "info") -> None:
        cb = getattr(self, "progress_log", None)
        if not cb:
            return
        try:
            cb(msg, level)
        except Exception:
            pass

    def _emit_status(self, text: str | None) -> None:
        cb = getattr(self, "progress_status", None)
        if not cb:
            return
        try:
            cb(text)
        except Exception:
            pass

    @staticmethod
    def _workflow_summary(graph: dict) -> dict:
        summary: dict = {"loras": []}
        for node in (graph or {}).values():
            if not isinstance(node, dict):
                continue
            cls = node.get("class_type")
            inputs = node.get("inputs") or {}
            if cls == "CheckpointLoaderSimple":
                summary["checkpoint"] = inputs.get("ckpt_name")
            elif cls == "LoraLoader":
                lora_name = inputs.get("lora_name")
                if lora_name:
                    summary.setdefault("loras", []).append(lora_name)
            elif cls == "KSampler":
                for key in ("steps", "cfg", "sampler_name", "scheduler", "denoise"):
                    summary[key] = inputs.get(key)
        return summary

    async def _emit_gpu_status(self, label: str) -> None:
        try:
            stats = await comfyui_client.system_stats()
            vram = comfyui_client.first_device_vram_text(stats)
            if vram:
                self._emit_log(f"{label} GPU 상태: {vram}")
        except Exception:
            pass

    def _progress_callback(self, label: str):
        reported_progress: set[tuple[str, int, int]] = set()
        reported_nodes: set[str] = set()

        def _cb(event: dict) -> None:
            event_type = event.get("type")
            if event_type == "progress":
                try:
                    value = int(event.get("value") or 0)
                    max_value = int(event.get("max") or 0)
                except (TypeError, ValueError):
                    return
                if max_value <= 0:
                    return
                node_class = event.get("node_class") or "node"
                pct = int((value / max_value) * 100)
                should_report = value == max_value or value == 1 or value % 5 == 0
                key = (str(node_class), value, max_value)
                if should_report and key not in reported_progress:
                    reported_progress.add(key)
                    self._emit_log(
                        f"{label} ComfyUI 진행: {node_class} {value}/{max_value} ({pct}%)"
                    )
                self._emit_status(
                    f"{label} ComfyUI {node_class} {value}/{max_value} ({pct}%)"
                )
            elif event_type == "executing":
                node_class = str(event.get("node_class") or "")
                if node_class and node_class not in reported_nodes:
                    reported_nodes.add(node_class)
                    self._emit_log(f"{label} ComfyUI 노드 실행: {node_class}")
            elif event_type == "execution_cached":
                nodes = ((event.get("data") or {}).get("nodes") or [])
                if nodes:
                    self._emit_log(f"{label} ComfyUI 캐시 노드: {len(nodes)}개")
            elif event_type in {"watch_error", "watch_unavailable"}:
                err = event.get("error") or "unknown"
                self._emit_log(f"{label} ComfyUI 진행 이벤트 수신 불가: {err}", "warn")

        return _cb

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
        pad_canvas: tuple[int, int] | None = None
        if self.model_id == "comfyui-dreamshaper-xl-mylora" and w != h:
            pad_canvas = (w, h)
            w, h = _SDXL_DIMS.get("1:1", (1024, 1024))

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
            label = self._context_label()
            summary = self._workflow_summary(graph)
            self._emit_log(
                f"{label} ComfyUI 준비: {self.display_name}, {w}x{h}, "
                f"steps={summary.get('steps')}, seed={seed}"
            )
            await self._emit_gpu_status(label)
            client_id = comfyui_client.new_client_id()
            prompt_id = await comfyui_client.submit(graph, client_id=client_id)
            print(f"[comfyui-image] submitted {self.model_id} prompt_id={prompt_id} {w}x{h}")
            self._emit_log(f"{label} ComfyUI 제출: prompt_id={prompt_id}")
            entry = await comfyui_client.wait_for(
                prompt_id,
                total_timeout=600.0,
                client_id=client_id,
                prompt_graph=graph,
                on_progress=self._progress_callback(label),
            )
            seconds = comfyui_client.execution_seconds(entry)
            cached = comfyui_client.cached_node_count(entry)
            if seconds is not None:
                self._emit_log(
                    f"{label} ComfyUI 실행 완료: {seconds:.2f}s, 캐시 노드 {cached}개"
                )
            await comfyui_client.download_first_output(
                entry, output_path, kinds=("images",)
            )
            self._emit_log(f"{label} 이미지 저장: {Path(output_path).name}")
            self._emit_status(None)
            print(f"[comfyui-image] saved -> {_safe_console(output_path)}")
            return output_path

        # v1.1.61: 그 외 로컬 ComfyUI 는 레퍼런스 이미지 픽셀을 모델로 주입하지 않는다
        # (IPAdapter/Redux 설치 난이도 높음). 레퍼런스 들어와도 기본 워크플로로 실행.
        # 스타일은 global_style/프롬프트 텍스트로 유도.
        final_prompt_text = (prompt or "").strip() or "an image"

        # LoRA 트리거 워드 자동 삽입
        if self.model_id == "comfyui-dreamshaper-xl-vector":
            if "vector" not in final_prompt_text.lower():
                final_prompt_text = f"vector, {final_prompt_text}"
        elif self.model_id == "comfyui-dreamshaper-xl-mylora":
            final_prompt_text = _shape_mylora_prompt(final_prompt_text)
            neg = f"{_MYLORA_NEGATIVE_PROMPT}, {neg}"
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
        if self.model_id == "comfyui-dreamshaper-xl-mylora":
            _apply_mylora_profile(graph, final_prompt_text)
        label = self._context_label()
        summary = self._workflow_summary(graph)
        loras = ", ".join(summary.get("loras") or []) or "none"
        self._emit_log(
            f"{label} ComfyUI 준비: {self.display_name}, {w}x{h}, "
            f"steps={summary.get('steps')}, sampler={summary.get('sampler_name')}, "
            f"scheduler={summary.get('scheduler')}, seed={seed}"
        )
        if summary.get("checkpoint"):
            self._emit_log(
                f"{label} 모델 로딩 대상: {summary.get('checkpoint')} / LoRA: {loras}"
            )
        await self._emit_gpu_status(label)
        client_id = comfyui_client.new_client_id()
        prompt_id = await comfyui_client.submit(graph, client_id=client_id)
        print(f"[comfyui-image] submitted {self.model_id} prompt_id={prompt_id} {w}x{h}")
        self._emit_log(f"{label} ComfyUI 제출: prompt_id={prompt_id}")
        entry = await comfyui_client.wait_for(
            prompt_id,
            total_timeout=300.0,
            client_id=client_id,
            prompt_graph=graph,
            on_progress=self._progress_callback(label),
        )
        seconds = comfyui_client.execution_seconds(entry)
        cached = comfyui_client.cached_node_count(entry)
        if seconds is not None:
            self._emit_log(
                f"{label} ComfyUI 실행 완료: {seconds:.2f}s, 캐시 노드 {cached}개"
            )
        await comfyui_client.download_first_output(
            entry, output_path, kinds=("images",)
        )
        self._emit_log(f"{label} 이미지 저장: {Path(output_path).name}")
        if pad_canvas:
            _pad_image_to_canvas(output_path, pad_canvas[0], pad_canvas[1])
        self._emit_status(None)
        print(f"[comfyui-image] saved -> {_safe_console(output_path)}")
        return output_path
