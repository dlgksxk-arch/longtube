"""API key management router — save/update keys in .env"""
import os
import re
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

router = APIRouter()

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

# Provider → env var name mapping
PROVIDER_KEY_MAP = {
    "Anthropic": "ANTHROPIC_API_KEY",
    "OpenAI": "OPENAI_API_KEY",
    "ElevenLabs": "ELEVENLABS_API_KEY",
    "fal.ai": "FAL_KEY",
    "xAI (Grok)": "XAI_API_KEY",
    "Kling": "KLING_ACCESS_KEY",
    "Replicate": "REPLICATE_API_TOKEN",
    "Replicate (fal/NanoBanana)": "REPLICATE_API_TOKEN",
    "Runway": "RUNWAY_API_KEY",
    "Midjourney": "MIDJOURNEY_API_KEY",
}

# Provider → API key creation page URL
PROVIDER_URLS = {
    "Anthropic": "https://console.anthropic.com/settings/keys",
    "OpenAI": "https://platform.openai.com/api-keys",
    "ElevenLabs": "https://elevenlabs.io/app/settings/api-keys",
    "fal.ai": "https://fal.ai/dashboard/keys",
    "xAI (Grok)": "https://console.x.ai/",
    "Kling": "https://klingai.com/",
    "Replicate": "https://replicate.com/account/api-tokens",
    "Replicate (fal/NanoBanana)": "https://replicate.com/account/api-tokens",
    "Runway": "https://app.runwayml.com/settings/api-keys",
    "Midjourney": "https://www.midjourney.com/account",
}


class ApiKeyUpdate(BaseModel):
    provider: str
    api_key: str


class ApiKeyDelete(BaseModel):
    provider: str


def _read_env() -> str:
    """Read .env file contents"""
    if ENV_PATH.exists():
        return ENV_PATH.read_text(encoding="utf-8")
    return ""


def _write_env(content: str):
    """Write .env file"""
    ENV_PATH.write_text(content, encoding="utf-8")


def _update_env_var(env_content: str, var_name: str, value: str) -> str:
    """Update or add an env var in the content string"""
    pattern = re.compile(rf'^{re.escape(var_name)}\s*=.*$', re.MULTILINE)
    new_line = f'{var_name}={value}'

    if pattern.search(env_content):
        return pattern.sub(new_line, env_content)
    else:
        # Add at end
        if env_content and not env_content.endswith('\n'):
            env_content += '\n'
        return env_content + new_line + '\n'


def _reload_config_var(var_name: str, value: str):
    """Update the in-memory config variable and os.environ"""
    os.environ[var_name] = value
    # Also update the config module's global
    import app.config as cfg
    if hasattr(cfg, var_name):
        setattr(cfg, var_name, value)


@router.post("/save")
async def save_api_key(body: ApiKeyUpdate):
    """Save an API key to .env and reload in memory"""
    var_name = PROVIDER_KEY_MAP.get(body.provider)
    if not var_name:
        raise HTTPException(400, f"Unknown provider: {body.provider}")

    env_content = _read_env()
    env_content = _update_env_var(env_content, var_name, body.api_key)
    _write_env(env_content)

    # Reload in memory
    _reload_config_var(var_name, body.api_key)

    return {"status": "saved", "provider": body.provider, "env_var": var_name}


@router.delete("/delete")
async def delete_api_key(body: ApiKeyDelete):
    """Remove an API key from .env"""
    var_name = PROVIDER_KEY_MAP.get(body.provider)
    if not var_name:
        raise HTTPException(400, f"Unknown provider: {body.provider}")

    env_content = _read_env()
    pattern = re.compile(rf'^{re.escape(var_name)}\s*=.*\n?', re.MULTILINE)
    env_content = pattern.sub('', env_content)
    _write_env(env_content)

    _reload_config_var(var_name, "")

    return {"status": "deleted", "provider": body.provider}


@router.get("/providers")
async def list_providers():
    """List all providers with their env var names and key creation URLs"""
    providers = []
    for provider, var_name in PROVIDER_KEY_MAP.items():
        # Skip duplicates
        if provider == "Replicate (fal/NanoBanana)":
            continue
        current_key = os.environ.get(var_name, "")
        masked = ""
        if current_key:
            if len(current_key) > 12:
                masked = current_key[:6] + "..." + current_key[-4:]
            else:
                masked = "***"
        providers.append({
            "provider": provider,
            "env_var": var_name,
            "has_key": bool(current_key),
            "masked_key": masked,
            "url": PROVIDER_URLS.get(provider, ""),
        })
    return {"providers": providers}
