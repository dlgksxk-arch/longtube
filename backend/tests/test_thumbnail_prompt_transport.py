import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.services.thumbnail_service import (
    THUMBNAIL_MINIMAL_GENERATION_CONTRACT,
    build_standard_thumbnail_prompt,
    generate_ai_thumbnail,
)


def test_standard_thumbnail_prompt_keeps_script_scene_and_dedicated_style_only():
    raw = "King Seong overlooks the newly planned Sabi capital beside the Geum River."
    prompt = build_standard_thumbnail_prompt(
        {
            "title": "아마노이와토라는 단어가 있어도 교체하지 않는다",
            "thumbnail_prompt": raw,
            "visual_world_text": "This must not be injected.",
        },
        config={
            "thumbnail_style_prompt": "Dedicated CH1 thumbnail illustration style.",
            "image_global_prompt": "Main-image style must not leak.",
            "thumbnail_subject_direction": "Do not override the script subject.",
        },
    )

    assert prompt == (
        "Dedicated CH1 thumbnail illustration style.\n"
        f"{raw}\n"
        f"{THUMBNAIL_MINIMAL_GENERATION_CONTRACT}"
    )
    assert "Main-image style must not leak" not in prompt
    assert "This must not be injected" not in prompt
    assert "AMANO-IWATO RESCUE" not in prompt
    assert "THUMBNAIL FACE VISIBILITY LOCK" not in prompt


def test_standard_thumbnail_prompt_removes_only_explicit_writing_request():
    prompt = build_standard_thumbnail_prompt(
        {
            "thumbnail_prompt": (
                "King Seong overlooks Sabi while a banner symbolically evokes the name "
                "Nambuyeo with restrained written characters, sixth-century historical scene."
            )
        },
        config={"thumbnail_style_prompt": "CH1 style."},
    )

    assert "King Seong overlooks Sabi" in prompt
    assert "sixth-century historical scene" in prompt
    assert "written characters" not in prompt
    assert "a plain unmarked banner" in prompt


@pytest.mark.asyncio
async def test_generate_ai_thumbnail_sends_stable_composed_prompt_to_krea2():
    class FakeImageService:
        model_id = "comfyui-krea2"
        negative_prompt = ""

        def __init__(self):
            self.prompts = []

        async def generate(self, prompt, width, height, output_path, reference_images=None):
            self.prompts.append(prompt)
            Image.new("RGB", (width, height), (20, 20, 20)).save(output_path)
            return output_path

    raw = "One exact historical scene from the script."
    expected = (
        "Dedicated channel thumbnail style.\n"
        f"{raw}\n"
        f"{THUMBNAIL_MINIMAL_GENERATION_CONTRACT}"
    )
    fake = FakeImageService()
    with tempfile.TemporaryDirectory() as td, patch(
        "app.services.image.factory.get_image_service",
        return_value=fake,
    ):
        await generate_ai_thumbnail(
            project_id="thumbnail-transport-test",
            image_prompt=raw,
            image_model_id="comfyui-krea2",
            output_path=str(Path(td) / "thumbnail.png"),
            config={
                "thumbnail_style_prompt": "Dedicated channel thumbnail style.",
                "image_global_prompt": "Must remain unused.",
                "thumbnail_quality_check": False,
            },
        )

    assert fake.prompts == [expected]
