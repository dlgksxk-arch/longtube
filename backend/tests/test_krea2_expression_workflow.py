import json
from pathlib import Path

from app.services.image.comfyui_service import ComfyUIImageService
from app.services.image.factory import IMAGE_REGISTRY
from app.services.image.prompt_compiler import supports_scene_contract_v2_model


def _workflow(name: str) -> dict:
    path = Path(__file__).resolve().parents[1] / "workflows" / "comfyui" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_existing_krea2_workflow_is_unchanged_turbo_path() -> None:
    workflow = _workflow("krea2_text2img.json")
    assert workflow["1"]["inputs"]["unet_name"] == "krea2_turbo_fp8_scaled.safetensors"
    assert workflow["6"]["class_type"] == "KSampler"
    assert workflow["6"]["inputs"]["steps"] == 8
    assert workflow["7"]["inputs"]["vae_name"] == "qwen_image_vae.safetensors"


def test_expression_workflow_is_separately_registered() -> None:
    model_id = "comfyui-krea2-expression"
    assert model_id in IMAGE_REGISTRY
    assert supports_scene_contract_v2_model(model_id)
    service = ComfyUIImageService(model_id)
    assert service.display_name == "로컬krea2 표정개선"


def test_expression_workflow_has_exact_expression_stack() -> None:
    workflow = _workflow("krea2_expression_text2img.json")
    assert workflow["1"]["inputs"]["unet_name"] == "krea2_raw_int8_convrot.safetensors"
    assert workflow["2"]["inputs"] == {
        "lora_name": "krea2_turbo_lora_rank_64_bf16.safetensors",
        "strength_model": 0.6,
        "model": ["1", 0],
    }
    assert workflow["3"]["inputs"] == {
        "lora_name": "krea2filterbypass.safetensors",
        "strength_model": 1.0,
        "model": ["2", 0],
    }
    assert workflow["4"]["inputs"]["clip_name"] == "qwen3vl_4b_bf16.safetensors"
    assert workflow["8"]["inputs"]["sampler_name"] == "exponential/res_2s"
    assert workflow["8"]["inputs"]["scheduler"] == "beta"
    assert workflow["8"]["inputs"]["steps"] == 6
    assert workflow["9"]["inputs"]["sampler_name"] == "multistep/deis_3m"
    assert workflow["9"]["inputs"]["scheduler"] == "bong_tangent"
    assert workflow["9"]["inputs"]["steps"] == 2
    assert workflow["9"]["inputs"]["denoise"] == 0.2
    assert workflow["10"]["inputs"]["vae_name"] == "Wan2_1_VAE_fp32.safetensors"


def test_expression_workflow_contains_no_embedded_positive_prompt() -> None:
    workflow = _workflow("krea2_expression_text2img.json")
    encoded_texts = [
        node.get("inputs", {}).get("text")
        for node in workflow.values()
        if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncode"
    ]
    assert encoded_texts == ["${PROMPT}"]
