import asyncio

import pytest
from PIL import Image

from app.services.image.comfyui_service import (
    _z_image_uses_compact_thumbnail_prompt,
)
from app.services.image.prompt_compiler import SCENE_CONTRACT_V2
from app.services.thumbnail_service import (
    build_clickbait_thumbnail_overlay,
    generate_ai_thumbnail,
)


@pytest.mark.parametrize(
    ("configured_profile", "expected_profile"),
    (
        (SCENE_CONTRACT_V2, SCENE_CONTRACT_V2),
        ("legacy", ""),
    ),
)
def test_generate_ai_thumbnail_applies_configured_prompt_profile(
    monkeypatch,
    tmp_path,
    configured_profile,
    expected_profile,
):
    calls: list[dict] = []

    class FakeImageService:
        model_id = "comfyui-z-image-turbo"
        prompt_profile = ""
        negative_prompt = ""
        compact_thumbnail_prompt = False

        async def generate(
            self,
            prompt,
            width,
            height,
            output_path,
            reference_images=None,
        ):
            calls.append(
                {
                    "prompt": prompt,
                    "prompt_profile": self.prompt_profile,
                    "width": width,
                    "height": height,
                }
            )
            Image.new("RGB", (width, height), "#203040").save(output_path)
            return output_path

    service = FakeImageService()
    monkeypatch.setattr(
        "app.services.image.factory.get_image_service",
        lambda _model_id: service,
    )

    output_path = tmp_path / "thumbnail.png"
    result = asyncio.run(
        generate_ai_thumbnail(
            project_id="V3_CH1_EP8_TEST",
            image_prompt=(
                "King Gaero plays a tense board game with the disguised "
                "Goguryeo monk Dorim while construction drains Baekje."
            ),
            image_model_id="comfyui-z-image-turbo",
            output_path=str(output_path),
            config={
                "image_prompt_profile": configured_profile,
                "thumbnail_quality_check": False,
            },
        )
    )

    assert calls
    assert calls[0]["prompt_profile"] == expected_profile
    assert "King Gaero" in calls[0]["prompt"]
    assert "Goguryeo monk Dorim" in calls[0]["prompt"]
    assert calls[0]["width"] == 1280
    assert calls[0]["height"] == 720
    assert result["model"] == "comfyui-z-image-turbo"
    assert output_path.exists()


def test_script_thumbnail_literal_prompt_stays_at_prompt_head(
    monkeypatch,
    tmp_path,
):
    calls: list[str] = []

    class FakeImageService:
        model_id = "comfyui-z-image-turbo"
        prompt_profile = ""
        negative_prompt = ""

        async def generate(
            self,
            prompt,
            width,
            height,
            output_path,
            reference_images=None,
        ):
            calls.append(prompt)
            Image.new("RGB", (width, height), "#203040").save(output_path)
            return output_path

    service = FakeImageService()
    monkeypatch.setattr(
        "app.services.image.factory.get_image_service",
        lambda _model_id: service,
    )
    literal_prompt = (
        "SCRIPT THUMBNAIL LITERAL LOCK: King Chimnyu formally receives "
        "the foreign monk Marananta inside a Baekje timber hall."
    )

    asyncio.run(
        generate_ai_thumbnail(
            project_id="V3_CH1_EP6_TEST",
            image_prompt=literal_prompt,
            image_model_id="comfyui-z-image-turbo",
            output_path=str(tmp_path / "thumbnail.png"),
            enable_historical_guard=True,
            config={
                "image_prompt_profile": "legacy",
                "thumbnail_quality_check": False,
            },
        )
    )

    assert calls
    assert calls[0].startswith("King Chimnyu")
    assert "SCRIPT THUMBNAIL LITERAL LOCK" not in calls[0]
    assert "THUMBNAIL FACE VISIBILITY LOCK" not in calls[0]
    assert "King Chimnyu" in calls[0]
    assert "Marananta" in calls[0]
    assert service.compact_thumbnail_prompt is True


def test_script_thumbnail_literal_prompt_uses_raw_z_image_path():
    prompt = (
        "SCRIPT THUMBNAIL LITERAL LOCK: King Chimnyu receives "
        "the foreign monk Marananta."
    )

    assert _z_image_uses_compact_thumbnail_prompt(
        prompt,
        "comfyui-z-image-turbo",
    )
    assert not _z_image_uses_compact_thumbnail_prompt(
        prompt,
        "comfyui-flux2-klein-4b",
    )


def test_korean_thumbnail_hook_does_not_cut_a_word_in_half():
    overlay = build_clickbait_thumbnail_overlay(
        {
            "thumbnail_hook": "왕을 속이고 남편을 구한 평민 여성",
            "title": "도미 부인 설화",
            "language": "ko",
        },
        "도미 부인 설화",
        {"language": "ko"},
    )

    assert overlay == "왕을 속이고 남편을\n구한 평민 여성"


def test_japanese_yamata_no_orochi_thumbnail_gets_japanese_overlay():
    overlay = build_clickbait_thumbnail_overlay(
        {
            "title": "일본사 시크릿 8개의 머리를 가진 괴물, 야마타노오로치 EP.14",
            "topic": "8개의 머리를 가진 괴물, 야마타노오로치",
            "language": "ja",
        },
        "8개의 머리를 가진 괴물, 야마타노오로치 EP.14",
        {"language": "ja"},
    )

    assert overlay == "八つの頭の怪物\nヤマタノオロチ"


def test_japanese_thumbnail_reuses_stored_main_upload_title():
    overlay = build_clickbait_thumbnail_overlay(
        {
            "title": "日本史 시크릿 괴물의 꼬리에서 발견된 신검 EP.16",
            "topic": "괴물의 꼬리에서 발견된 신검",
            "thumbnail_hook": "괴물의 뱃속에서 나온 왕권의 보물?! 신검의 정체!",
        },
        "日本史 시크릿 괴물의 꼬리에서 발견된 신검 EP.16",
        {
            "language": "ja",
            "youtube_upload_result": {
                "videos": [
                    {
                        "kind": "main",
                        "title": "八つの頭を持つ怪物、ヤマタノオロチ EP.16",
                    }
                ]
            },
        },
    )

    assert overlay == "八つの頭の怪物\nヤマタノオロチ"
