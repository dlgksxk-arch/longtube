"""영상 모션 프롬프트 빌더 + AI 비디오 타겟 선택 유틸.

v1.1.52: pipeline_tasks._step_video 와 routers/video.py 가 동일한 로직을
공유하기 위해 분리. 라우터를 직접 import 하면 FastAPI 의존성이 끌려오므로
순수 함수만 이 모듈에 배치한다.
"""
from app.services.image.prompt_builder import cut_has_character

VIDEO_TARGET_OPTIONS = {"all", "every_3", "every_4", "every_5", "character_only"}


def should_generate_ai_video(cut_number: int, selection: str, ai_first_n: int = 5) -> bool:
    """주어진 cut 이 primary video_model 로 처리돼야 하는지 판단.

    v1.1.55: `ai_first_n` 이 양수이면 컷 1..N 은 selection 과 무관하게 무조건
    AI. 인트로 5컷의 임팩트가 영상 후킹의 핵심이라 사용자가 매번 강제했다.
    DEFAULT_CONFIG 의 `ai_video_first_n` (기본 5) 가 여기로 흘러들어온다.
    """
    if cut_number is None or cut_number < 1:
        return False
    # ★ 앞 N 컷 강제 AI — 모든 selection 위에 군림하는 규칙
    try:
        n = int(ai_first_n)
    except (TypeError, ValueError):
        n = 0
    if n > 0 and cut_number <= n:
        return True
    if selection not in VIDEO_TARGET_OPTIONS:
        return True
    if selection == "all":
        return True
    if selection == "every_3":
        return (cut_number - 1) % 3 == 0
    if selection == "every_4":
        return (cut_number - 1) % 4 == 0
    if selection == "every_5":
        return (cut_number - 1) % 5 == 0
    if selection == "character_only":
        return (cut_number - 1) % 5 == 0
    return True


def build_video_motion_prompt(
    cut_number: int,
    total_cuts: int,
    config: dict,
) -> str:
    """컷별 영상 모션 프롬프트 생성. routers/video.py 의 _build_video_motion_prompt 와 동일."""
    character_description = (
        (config.get("character_description") or "").strip()
        or (config.get("image_global_prompt") or "").strip()
    )

    is_first = cut_number == 1
    is_last = total_cuts > 0 and cut_number == total_cuts
    is_character_cut = cut_has_character(cut_number)

    parts: list[str] = []

    # v1.1.62: 심플 일러스트/카툰 스타일에 맞게 모션 프롬프트 단순화.
    # 과도한 실사 묘사(먼지 파티클, 빛 깜빡임 등)를 제거하고
    # 부드럽고 단순한 애니메이션 지시로 통일.
    if is_first:
        parts.append(
            "Gentle slow zoom in. Subtle movement in the scene, "
            "soft animation, smooth opening."
        )
    elif is_last:
        parts.append(
            "Gentle slow zoom out. Soft fading motion, "
            "calm and peaceful ending."
        )
    else:
        parts.append(
            "Gentle slow pan. Subtle natural movement, "
            "smooth continuous motion, soft animation."
        )

    if is_character_cut and character_description:
        parts.append(
            f"The character ({character_description}) moves slightly — "
            f"small gesture, gentle sway. Keep appearance consistent."
        )
    elif is_character_cut:
        parts.append(
            "The character moves slightly — small gesture, gentle sway."
        )
    else:
        parts.append("Keep motion smooth and gentle, no sudden changes.")

    return " ".join(parts)
