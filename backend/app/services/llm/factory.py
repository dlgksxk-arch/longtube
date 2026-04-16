"""LLM service factory"""
from app.services.llm.base import BaseLLMService
from app.services.llm.claude_service import ClaudeService
from app.services.llm.gpt_service import GPTService

LLM_REGISTRY: dict[str, dict] = {
    "claude-sonnet-4-6": {"name": "Claude Sonnet 4.6", "provider": "anthropic", "default": True,
                          "cost_per_unit": "$3 / $15 per 1M tokens", "cost_input": 3.0, "cost_output": 15.0},
    "claude-opus-4-6":   {"name": "Claude Opus 4.6",   "provider": "anthropic",
                          "cost_per_unit": "$5 / $25 per 1M tokens", "cost_input": 5.0, "cost_output": 25.0},
    "claude-haiku-4-5":  {"name": "Claude Haiku 4.5",  "provider": "anthropic",
                          "cost_per_unit": "$0.80 / $4 per 1M tokens", "cost_input": 0.8, "cost_output": 4.0},
    "gpt-4o":            {"name": "GPT-4o",             "provider": "openai",
                          "cost_per_unit": "$2.50 / $10 per 1M tokens", "cost_input": 2.5, "cost_output": 10.0},
    "gpt-4o-mini":       {"name": "GPT-4o Mini",        "provider": "openai",
                          "cost_per_unit": "$0.15 / $0.60 per 1M tokens", "cost_input": 0.15, "cost_output": 0.6},
    "gpt-4.1":           {"name": "GPT-4.1",            "provider": "openai",
                          "cost_per_unit": "$2 / $8 per 1M tokens", "cost_input": 2.0, "cost_output": 8.0},
}


def get_llm_service(model_id: str) -> BaseLLMService:
    if model_id not in LLM_REGISTRY:
        raise ValueError(f"Unknown LLM model: {model_id}")

    provider = LLM_REGISTRY[model_id]["provider"]
    if provider == "anthropic":
        return ClaudeService(model_id)
    elif provider == "openai":
        return GPTService(model_id)
    raise ValueError(f"Unknown provider: {provider}")


def list_llm_models() -> list[dict]:
    return [{"id": k, **v} for k, v in LLM_REGISTRY.items()]
