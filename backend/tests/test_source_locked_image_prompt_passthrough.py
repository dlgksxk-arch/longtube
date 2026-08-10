import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.routers.image import _build_image_prompt
from app.services.image.asset_guard import expected_comfyui_positive_prompt
from app.services.image.comfyui_service import ComfyUIImageService
from app.services.image.prompt_builder import is_canonical_script_image_prompt


SOURCE_PROMPT = (
    "Global visual world: Time range: 501 AD; Place scope: Ungjin and Garimseong Fortress; "
    "Culture scope: Baekje; Material culture: documented Baekje material culture; "
    "Continuity rule: follow the source workbook; Year/period: 501 AD; "
    "Exact place: Ungjin and Garimseong Fortress; Scene evidence: source workbook row 11-011; "
    "Style: mature vintage dark historical manhwa illustration; "
    "Scene: King Muryeong stands inside a guarded Baekje audience hall, cinematic 16:9."
)


def test_canonical_script_prompt_is_detected() -> None:
    assert is_canonical_script_image_prompt(SOURCE_PROMPT)


def test_router_does_not_add_global_style_or_locks() -> None:
    actual = _build_image_prompt(
        SOURCE_PROMPT,
        "UNRELATED GLOBAL STYLE THAT MUST NOT BE ADDED",
        enable_historical_guard=True,
        image_model="comfyui-krea2",
        prompt_profile="scene-contract-v2",
        narration_context="unrelated narration",
    )
    assert actual == SOURCE_PROMPT


def test_router_keeps_arbitrary_krea2_prompt_verbatim() -> None:
    source = "Channel-owned style. Scene: one exact moment; preserve punctuation || no text"
    actual = _build_image_prompt(
        source,
        "UNRELATED STYLE",
        image_model="comfyui-krea2",
        prompt_profile="scene-contract-v2",
        narration_context="unrelated narration",
    )
    assert actual == source


def test_krea2_channel_order_does_not_change_prompts() -> None:
    channel_1 = "CH1 cartoon ink style. Scene: Baekje council."
    channel_4 = "CH4 photorealistic live-action style. Scene: 1922 New York street."

    ch4_first = _build_image_prompt(channel_4, "", image_model="comfyui-krea2")
    ch1_after_ch4 = _build_image_prompt(channel_1, "", image_model="comfyui-krea2")
    ch1_first = _build_image_prompt(channel_1, "", image_model="comfyui-krea2")
    ch4_after_ch1 = _build_image_prompt(channel_4, "", image_model="comfyui-krea2")

    assert ch1_after_ch4 == ch1_first == channel_1
    assert ch4_after_ch1 == ch4_first == channel_4


def test_resume_expected_positive_is_the_same_source_prompt() -> None:
    actual = expected_comfyui_positive_prompt(
        SOURCE_PROMPT,
        image_model="comfyui-krea2",
        prompt_profile="scene-contract-v2",
    )
    assert actual == SOURCE_PROMPT


def test_krea2_workflow_has_only_prompt_placeholder() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1]
        / "workflows"
        / "comfyui"
        / "krea2_text2img.json"
    )
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    encoded_texts = [
        node.get("inputs", {}).get("text")
        for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]
    assert encoded_texts == ["${PROMPT}"]


def test_krea2_runtime_submits_positive_prompt_verbatim() -> None:
    async def write_output(_entry, output_path, **_kwargs):
        from PIL import Image

        Image.new("RGB", (64, 36), (120, 120, 120)).save(output_path)

    source = (
        "CH4 photorealistic live-action style; Scene: exact requested action. "
        "Do not append or rewrite this prompt."
    )
    service = ComfyUIImageService("comfyui-krea2")
    submit = AsyncMock(return_value="prompt-id")
    with tempfile.TemporaryDirectory() as tmp:
        output = str(Path(tmp) / "cut.png")
        with (
            patch(
                "app.services.image.comfyui_service.comfyui_client.system_stats",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.submit",
                new=submit,
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.wait_for",
                new=AsyncMock(return_value={"outputs": {}}),
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.download_first_output",
                new=AsyncMock(side_effect=write_output),
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.execution_seconds",
                return_value=None,
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.cached_node_count",
                return_value=0,
            ),
            patch(
                "app.services.image.comfyui_service.comfyui_client.new_client_id",
                return_value="client-id",
            ),
        ):
            asyncio.run(service.generate(source, 1280, 720, output))

    assert service.last_positive_prompt == source
    graph = submit.await_args.args[0]
    assert graph["3"]["inputs"]["text"] == source
