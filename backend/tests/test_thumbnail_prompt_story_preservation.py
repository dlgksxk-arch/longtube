from app.services.image.prompt_builder import apply_reference_style_prefix
from app.services.image.prompt_compiler import compile_image_prompt


def test_thumbnail_story_survives_historical_guard_and_scene_compilation():
    source = (
        "Global visual world: Time range: 475 AD; "
        "Place scope: Hanseong and the Han River basin; "
        "Culture scope: Baekje and Goguryeo; "
        "Material culture: historically grounded local materials; "
        "Continuity rule: follow the episode source. "
        "Thumbnail image prompt: King Gaero plays a tense board game with "
        "the disguised Goguryeo monk Dorim while construction drains Baekje. "
        "THUMBNAIL RENDERING STYLE: mature historical documentary illustration."
    )

    guarded = apply_reference_style_prefix(
        source,
        has_reference=False,
        enable_historical_guard=True,
    )
    compiled = compile_image_prompt(
        guarded,
        model_id="comfyui-z-image-turbo",
    )

    assert "King Gaero" in guarded
    assert "Goguryeo monk Dorim" in guarded
    assert "King Gaero" in compiled.positive
    assert "Goguryeo monk Dorim" in compiled.positive


def test_distinct_thumbnail_story_prompts_do_not_compile_to_same_scene():
    prefix = (
        "Global visual world: Time range: Baekje period; "
        "Place scope: Han River basin; Culture scope: Baekje; "
        "Material culture: historically grounded local materials; "
        "Continuity rule: follow the episode source. "
        "Thumbnail image prompt: "
    )
    prompts = (
        prefix + "King Chimnyu receives the foreign monk Marananta in court.",
        prefix + "Domi's wife escapes toward the river to find her blinded husband.",
    )

    compiled = [
        compile_image_prompt(
            apply_reference_style_prefix(
                prompt,
                has_reference=False,
                enable_historical_guard=True,
            ),
            model_id="comfyui-z-image-turbo",
        ).positive
        for prompt in prompts
    ]

    assert "King Chimnyu" in compiled[0]
    assert "Marananta" in compiled[0]
    assert "Domi's wife" in compiled[1]
    assert "blinded husband" in compiled[1]
    assert compiled[0] != compiled[1]
