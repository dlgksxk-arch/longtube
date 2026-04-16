"""이미지 프롬프트 빌더 + 레퍼런스 수집 유틸.

v1.1.52: pipeline_tasks._step_image 와 routers/image.py 가 동일한 로직을
공유하기 위해 분리. 라우터를 직접 import 하면 FastAPI 의존성(python-multipart 등)이
끌려오므로, 순수 함수만 이 모듈에 배치한다.

v1.1.58: 레퍼런스 이미지가 있으면 스타일은 100% 레퍼런스에서 가져온다.
global_style, 스타일 큐 제거 등 복잡한 우회 로직 삭제 — 단순하고 명확하게.

v1.1.55: 모든 이미지 생성(컷, 썸네일, 재생성) 경로에서 동일한 REFERENCE_STYLE_PREFIX
를 사용한다. 문구가 3 곳에서 제각각이던 상태를 단일 상수로 통합해 스타일 일관성을
강제한다.
"""
import re
from pathlib import Path
from app.config import DATA_DIR


# ── 레퍼런스 스타일 락 (모든 이미지 생성 경로 공용) ──
#
# 이 프리픽스는 레퍼런스 이미지가 하나라도 첨부된 모든 프롬프트에 예외 없이
# 앞자리로 붙는다. 목적은 "이 프로젝트 안의 모든 이미지가 같은 그림체·같은
# 팔레트·같은 조명으로 나온다" 는 것을 모델 수준에서 강제하는 것이다.
#
# 사용처:
# - build_image_prompt (컷 이미지, has_reference=True 분기)
# - apply_reference_style_prefix (썸네일 자동/재생성, 그 외 외부 호출)
#
# 끝에 " || " 구분자를 두어 사용자 프롬프트가 바로 이어 붙을 수 있게 한다.
REFERENCE_STYLE_PREFIX = (
    "★ STYLE REFERENCE LOCK — the attached reference images are the absolute "
    "ground truth for art direction, color palette, lighting, texture, "
    "line/stroke character, and rendering technique. COPY that exact style "
    "pixel-for-pixel feel. Do NOT reinterpret, stylize, or drift. Keep every "
    "new image visually indistinguishable in style from the references. "
    "Change ONLY composition, subject, pose, and action as described below. || "
)


def apply_reference_style_prefix(prompt: str, has_reference: bool) -> str:
    """썸네일/재생성 등 외부 경로용 프리픽스 적용 헬퍼.

    이미 프리픽스가 붙어 있으면 중복 부착을 피한다. has_reference=False 이면
    원문을 그대로 반환한다 (레퍼런스가 없으면 스타일을 강제할 수 없으므로).
    """
    p = (prompt or "").strip()
    if not has_reference:
        return p
    if "STYLE REFERENCE LOCK" in p or p.startswith("STYLE:"):
        return p
    return REFERENCE_STYLE_PREFIX + p


# ── 캐릭터 슬롯 규칙 ──

def cut_has_character(cut_number: int) -> bool:
    """1-based cut_number 기준, 3컷마다 1장씩 캐릭터 배치.
    즉 cut 1, 4, 7, 10, ... 가 캐릭터 컷.
    """
    if cut_number is None or cut_number < 1:
        return False
    return (cut_number - 1) % 3 == 0


# ── 레퍼런스/캐릭터 이미지 수집 ──

def collect_reference_images(project_id: str, config: dict) -> list[str]:
    """config 의 reference_images 에서 절대 경로 목록을 반환."""
    ref_imgs = config.get("reference_images", [])
    project_dir = Path(DATA_DIR) / project_id
    paths = []
    for rel in ref_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def collect_character_images(project_id: str, config: dict) -> list[str]:
    """config 의 character_images 에서 절대 경로 목록을 반환."""
    char_imgs = config.get("character_images", [])
    project_dir = Path(DATA_DIR) / project_id
    paths = []
    for rel in char_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


# ── 프롬프트 빌더 ──

def build_image_prompt(
    image_prompt: str,
    global_style: str,
    *,
    has_reference: bool = False,
    has_character_slot: bool = False,
    character_description: str = "",
) -> str:
    """최종 이미지 프롬프트 조합.

    v1.1.58: 레퍼런스 이미지가 있으면 스타일은 전적으로 레퍼런스에 위임.
    프롬프트에는 피사체/구도/동작만 남기고, global_style 등 스타일 텍스트는 주입하지 않는다.
    레퍼런스가 없을 때만 global_style 을 폴백으로 사용.
    """
    base = (image_prompt or "").strip()

    if has_reference:
        # ── 레퍼런스 있음 ──
        # v1.1.61: global_style 도 항상 포함. 이유: 로컬 ComfyUI 모델 중 일부는
        # IPAdapter 가 안 깔려있어서 레퍼런스 픽셀이 모델에 안 들어갈 수 있다.
        # 그 경우 스타일 정보가 텍스트 프리픽스뿐인데 그게 "스타일 복사하라" 는
        # 메타 지시라 실제 스타일 단어(예: "cartoon illustration")가 전혀 없다.
        # 결과가 기본값(실사)로 돌아가는 원인. global_style 을 항상 끼워넣어 안전.
        parts: list[str] = [REFERENCE_STYLE_PREFIX]

        style_hint = (global_style or "").strip()
        if style_hint:
            parts.append(f"Style keywords: {style_hint}.")

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "From the character reference image, use ONLY shape, silhouette, and design. "
                    "Recolor and restyle the character to match the style reference images."
                )
            else:
                parts.append(
                    "This cut features the main character from the attached character "
                    "reference image. Use ONLY the character's shape and design. "
                    "Recolor and restyle the character to match the style reference images."
                )

        if base:
            parts.append(base)

        return " ".join(parts).strip()

    else:
        # ── 레퍼런스 없음: global_style 폴백 ──
        parts = []
        if global_style:
            parts.append(global_style.strip())
        if base:
            parts.append(base)

        if has_character_slot:
            char_desc = character_description.strip()
            if char_desc:
                parts.append(
                    f"This cut features the main character: {char_desc}. "
                    "Place the character clearly in frame, pose matching the scene."
                )

        return " ".join(parts).strip()
