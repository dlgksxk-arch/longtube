import copy

from app.services.image.comfyui_service import _apply_longtube_render_style
from app.services.image.prompt_builder import (
    append_prompt_specific_negative_prompt,
    historical_negative_prompt,
    is_canonical_script_image_prompt,
)
from app.services.image.prompt_compiler import compile_image_prompt
from app.services.llm.visual_policy import apply_script_visual_policy


ORIGINAL_SCENE = (
    "13th century medieval inquisitor holding high a papal parchment scroll "
    "Vox in Rama under flickering torchlight"
)
RATS_SCENE = (
    "Dark misty medieval town square with swarms of black rats crawling over "
    "cobblestone streets"
)
CRYING_SCENE = (
    "Beautiful medieval noblewoman Lady Isobel clutching a soft black cat closely "
    "to her velvet dress weeping"
)


def _script(*, speaker: str = "해설자", emotion: str | None = None) -> dict:
    return {
        "script_version": "prepared-ch4-time-explorers-s1-v2",
        "source_schema": "ch4-time-explorers-season1-xlsx-v1",
        "visual_policy_mode": "source-locked",
        "visual_world": {
            "time_range": "1233년 (13세기 중세 가톨릭 유럽)",
            "place_scope": "유럽 전역 / 교황청 / 독일 및 프랑스 교구 마을",
            "culture_scope": "13세기 중세 가톨릭 유럽",
        },
        "cuts": [
            {
                "cut_number": 1,
                "speaker": speaker,
                "emotion": emotion
                or ("[angry] [shouts]" if speaker != "해설자" else "[dramatic] [slowly]"),
                "narration": "교황의 종교 칙령이 선포되었습니다.",
                "image_prompt": ORIGINAL_SCENE,
                "visual_year": "1233 AD",
                "visual_period": "1233년 (13세기 중세 가톨릭 유럽)",
                "visual_location": "유럽 전역 / 교황청 / 독일 및 프랑스 교구 마을",
            }
        ],
    }


def test_ch4_source_locked_policy_is_live_action_and_idempotent() -> None:
    once = apply_script_visual_policy(_script())
    twice = apply_script_visual_policy(copy.deepcopy(once))
    first_prompt = once["cuts"][0]["image_prompt"]
    second_prompt = twice["cuts"][0]["image_prompt"]

    assert second_prompt == first_prompt
    assert f"Scene: {ORIGINAL_SCENE}" in first_prompt
    assert first_prompt.startswith(
        "1233 AD Western Europe. Cinematic live-action historical drama, "
        "photorealistic feature-film frame,"
    )
    assert "cinematic live-action historical drama" in first_prompt.lower()
    assert "photorealistic feature-film frame" in first_prompt
    assert "mature vintage dark historical manhwa" not in first_prompt
    assert "Year/period:" not in first_prompt
    assert "Style:" not in first_prompt
    assert is_canonical_script_image_prompt(first_prompt)


def test_ch4_speaking_cut_keeps_emotion_and_visible_dialogue_direction() -> None:
    prompt = apply_script_visual_policy(_script(speaker="남성1 그레고리오 9세"))["cuts"][0][
        "image_prompt"
    ]
    assert "[angry]" not in prompt
    assert "Visual direction:" in prompt
    assert "deeply furrowed brows" in prompt
    assert "mouth clearly open mid-shout" in prompt
    assert "lips are visibly caught mid-word" in prompt
    assert f"Scene: {ORIGINAL_SCENE}" in prompt


def test_ch4_crying_stammering_cut_uses_explicit_visible_performance() -> None:
    script = _script(speaker="여성1 이소벨", emotion="[crying] [stammers]")
    script["cuts"][0]["image_prompt"] = CRYING_SCENE
    once = apply_script_visual_policy(script)
    prompt = once["cuts"][0]["image_prompt"]
    twice = apply_script_visual_policy(copy.deepcopy(once))["cuts"][0]["image_prompt"]
    assert twice == prompt
    assert "The face is visibly soaked with tears" in prompt
    assert "clear droplets overflow both reddened eyes" in prompt
    assert "form two glossy wet tracks to the jaw" in prompt
    assert "Pinched brows and trembling wet lips are parted mid-word" in prompt
    assert f"Scene: {CRYING_SCENE}" in prompt
    assert prompt.index(f"Scene: {CRYING_SCENE}") < prompt.index(
        "Visual direction:"
    )
    assert len(prompt) < 900


def test_ch4_narrator_emotion_stays_atmospheric_and_preserves_nonhuman_scene() -> None:
    script = _script(emotion="[curious]")
    script["cuts"][0]["image_prompt"] = RATS_SCENE
    prompt = apply_script_visual_policy(script)["cuts"][0]["image_prompt"]

    assert f"Scene: {RATS_SCENE}" in prompt
    assert "Visual direction:" in prompt
    assert "[curious]" not in prompt
    assert "Character identity:" not in prompt
    assert "Visible performance:" not in prompt
    assert "Dialogue direction:" not in prompt
    assert "Character performance priority:" not in prompt
    assert "populated exclusively by black rats" in prompt.lower()
    assert "sole living subjects in frame are black rats" in prompt.lower()
    assert "black rats fill the foreground, middle ground, and background" in prompt.lower()
    assert len(prompt) < 700
    for forbidden in (
        "raised brow",
        "searching eyes",
        "parted lips",
        "speaking character",
        "adult cast",
        "expressive actor",
    ):
        assert forbidden not in prompt.lower()


def test_ch4_narrator_human_scene_is_not_rewritten_as_an_empty_environment() -> None:
    prompt = apply_script_visual_policy(_script())['cuts'][0]['image_prompt']

    assert f"Scene: {ORIGINAL_SCENE}" in prompt
    assert "Visual direction:" not in prompt


def test_ch4_visible_character_emotion_order_is_canonical() -> None:
    first = apply_script_visual_policy(
        _script(speaker="남성1 그레고리오 9세", emotion="[booming] [angry]")
    )["cuts"][0]["image_prompt"]
    second = apply_script_visual_policy(
        _script(speaker="남성1 그레고리오 9세", emotion="[angry] [booming]")
    )["cuts"][0]["image_prompt"]

    first_visible = first.split("Visual direction:", 1)[1]
    second_visible = second.split("Visual direction:", 1)[1]
    assert first_visible == second_visible
    assert first_visible.index("deeply furrowed brows") < first_visible.index(
        "commanding chest-open posture"
    )


def test_ch4_live_action_negative_path_does_not_ban_live_action() -> None:
    prompt = apply_script_visual_policy(_script())["cuts"][0]["image_prompt"]
    negative = historical_negative_prompt(prompt, enabled=True)
    negative = append_prompt_specific_negative_prompt(negative, prompt)
    compiled = compile_image_prompt(prompt, model_id="comfyui-krea2", base_negative=negative)

    for conflict in (
        "photorealistic",
        "photorealism",
        "photographic",
        "live-action still",
        "raw photo",
    ):
        assert conflict not in compiled.negative.lower()


def test_krea2_runtime_keeps_ch4_prompt_and_filters_conflicting_negatives() -> None:
    prompt = apply_script_visual_policy(_script())["cuts"][0]["image_prompt"]
    positive, negative = _apply_longtube_render_style(
        prompt,
        (
            "extra fingers, photorealistic photo, photographic still, live-action still, "
            "raw camera photo, manhwa, East Asian faces, generic Asian people, modern vehicle"
        ),
        model_id="comfyui-krea2",
        source_prompt=prompt,
    )

    assert positive == prompt
    assert f"Scene: {ORIGINAL_SCENE}" in positive
    assert "DEFAULT VISUAL STYLE LOCK" not in positive
    assert "mature vintage dark historical manhwa" not in positive
    assert negative == "extra fingers, modern vehicle"
