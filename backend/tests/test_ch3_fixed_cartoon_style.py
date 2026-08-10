from app.routers.image import _build_image_prompt
from app.services.image.channel_style_policy import (
    CH3_FIXED_CARTOON_STYLE,
    apply_fixed_channel_image_style,
    fixed_channel_image_style,
    is_channel3_context,
)
from app.services.thumbnail_service import build_standard_thumbnail_prompt


def test_channel3_detection_uses_explicit_config_or_project_id():
    assert is_channel3_context({"channel": 3})
    assert is_channel3_context({"result_channel_dir": "CH3"})
    assert is_channel3_context({}, "V3_CH3_EP11_2607282329539f30d9")
    assert not is_channel3_context({"channel": 4}, "V3_CH4_EP11")


def test_channel3_canonical_cut_style_replaces_source_style_only():
    source = (
        "Global visual world: Japanese myth; Year/period: mythic era; "
        "Exact place: Amano-Iwato cave; Style: photorealistic live action; "
        "Scene: sacred roosters crow outside the sealed cave"
    )
    result = apply_fixed_channel_image_style(source, {"channel": 3})

    assert CH3_FIXED_CARTOON_STYLE in result
    assert "photorealistic live action" not in result
    assert "Scene: sacred roosters crow outside the sealed cave" in result


def test_non_channel3_prompt_and_style_remain_unchanged():
    prompt = "Photorealistic 1897 West Virginia bedroom scene."
    assert apply_fixed_channel_image_style(prompt, {"channel": 4}) == prompt
    assert fixed_channel_image_style(
        {"channel": 4}, configured_style="live-action"
    ) == "live-action"


def test_channel3_krea2_path_receives_the_fixed_style_after_verbatim_branch():
    result = _build_image_prompt(
        "Sacred roosters crow outside the cave.",
        "ignored",
        image_model="comfyui-krea2",
        style_config={"channel": 3},
        project_id="V3_CH3_EP11",
    )

    assert result.startswith("Sacred roosters crow outside the cave.")
    assert CH3_FIXED_CARTOON_STYLE in result


def test_channel3_thumbnail_uses_same_fixed_style_and_ignores_override():
    result = build_standard_thumbnail_prompt(
        {
            "title": "Amano-Iwato",
            "thumbnail_prompt": "Ame-no-Uzume dances before the dark cave.",
        },
        config={
            "channel": 3,
            "thumbnail_style_prompt": "photorealistic live action",
        },
    )

    assert result.startswith(CH3_FIXED_CARTOON_STYLE)
    assert "photorealistic live action" not in result
    assert "Ame-no-Uzume dances before the dark cave." in result
