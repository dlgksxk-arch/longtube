"""API key status and balance checking router"""
import os
from pathlib import Path
import httpx
from fastapi import APIRouter
from app import config as cfg

router = APIRouter()

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


def _read_env_file() -> dict:
    """Parse backend/.env and return key→value map. Always fresh from disk."""
    result = {}
    try:
        if not ENV_PATH.exists():
            return result
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return result


def _key(name: str) -> str:
    """Always read freshest key value: .env file on disk → os.environ → cfg module."""
    # 1) Source of truth: .env file on disk (read every call, no caching)
    env = _read_env_file()
    if env.get(name):
        return env[name]
    # 2) os.environ (updated on save)
    v = os.environ.get(name, "")
    if v:
        return v
    # 3) config module fallback
    return getattr(cfg, name, "") or ""


async def _check_anthropic() -> dict:
    """Check Anthropic API key validity"""
    key = _key("ANTHROPIC_API_KEY")
    if not key:
        return {"provider": "Anthropic", "status": "not_configured", "balance": None, "detail": "API key not set", "balance_url": "https://console.anthropic.com/settings/billing"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                }
            )
            if resp.status_code == 200:
                return {"provider": "Anthropic", "status": "active", "balance": None, "detail": "키 유효", "balance_url": "https://console.anthropic.com/settings/billing"}
            elif resp.status_code == 401:
                return {"provider": "Anthropic", "status": "invalid", "balance": None, "detail": "키 무효", "balance_url": "https://console.anthropic.com/settings/billing"}
            else:
                return {"provider": "Anthropic", "status": "active", "balance": None, "detail": f"키 설정됨 (HTTP {resp.status_code})", "balance_url": "https://console.anthropic.com/settings/billing"}
    except Exception as e:
        return {"provider": "Anthropic", "status": "error", "balance": None, "detail": str(e)[:100], "balance_url": "https://console.anthropic.com/settings/billing"}


async def _check_openai() -> dict:
    """Check OpenAI API key and try to get billing info"""
    key = _key("OPENAI_API_KEY")
    if not key:
        return {"provider": "OpenAI", "status": "not_configured", "balance": None, "detail": "API key not set", "balance_url": "https://platform.openai.com/settings/organization/billing/overview"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"}
            )
            if resp.status_code == 200:
                return {"provider": "OpenAI", "status": "active", "balance": None, "detail": "키 유효", "balance_url": "https://platform.openai.com/settings/organization/billing/overview"}
            elif resp.status_code == 401:
                return {"provider": "OpenAI", "status": "invalid", "balance": None, "detail": "키 무효", "balance_url": "https://platform.openai.com/settings/organization/billing/overview"}
            else:
                return {"provider": "OpenAI", "status": "active", "balance": None, "detail": f"키 설정됨 (HTTP {resp.status_code})", "balance_url": "https://platform.openai.com/settings/organization/billing/overview"}
    except Exception as e:
        return {"provider": "OpenAI", "status": "error", "balance": None, "detail": str(e)[:100], "balance_url": "https://platform.openai.com/settings/organization/billing/overview"}


async def _check_elevenlabs() -> dict:
    """Check ElevenLabs API key and get subscription/usage info"""
    key = _key("ELEVENLABS_API_KEY")
    if not key:
        return {"provider": "ElevenLabs", "status": "not_configured", "balance": None, "detail": "API key not set"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.elevenlabs.io/v1/user/subscription",
                headers={"xi-api-key": key}
            )
            if resp.status_code == 200:
                data = resp.json()
                char_limit = data.get("character_limit", 0)
                char_used = data.get("character_count", 0)
                char_remaining = char_limit - char_used
                tier = data.get("tier", "unknown")
                return {
                    "provider": "ElevenLabs",
                    "status": "active",
                    "balance": f"{char_remaining:,} chars left",
                    "detail": f"{tier} plan: {char_used:,}/{char_limit:,} chars used",
                    "usage_pct": round(char_used / char_limit * 100, 1) if char_limit > 0 else 0,
                }
            elif resp.status_code == 401:
                return {"provider": "ElevenLabs", "status": "invalid", "balance": None, "detail": "Invalid API key"}
            else:
                return {"provider": "ElevenLabs", "status": "active", "balance": None, "detail": f"Key configured (HTTP {resp.status_code})"}
    except Exception as e:
        return {"provider": "ElevenLabs", "status": "error", "balance": None, "detail": str(e)[:100]}


async def _check_replicate() -> dict:
    """Check Replicate API token"""
    token = _key("REPLICATE_API_TOKEN")
    if not token:
        return {"provider": "Replicate", "status": "not_configured", "balance": None, "detail": "API token not set"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.replicate.com/v1/account",
                headers={"Authorization": f"Bearer {token}"}
            )
            if resp.status_code == 200:
                data = resp.json()
                return {"provider": "Replicate", "status": "active", "balance": None, "detail": f"Account: {data.get('username', 'ok')}"}
            elif resp.status_code == 401:
                return {"provider": "Replicate", "status": "invalid", "balance": None, "detail": "Invalid token"}
            else:
                return {"provider": "Replicate", "status": "active", "balance": None, "detail": f"Token configured (HTTP {resp.status_code})"}
    except Exception as e:
        return {"provider": "Replicate", "status": "error", "balance": None, "detail": str(e)[:100]}


async def _check_fal() -> dict:
    """Check fal.ai API key"""
    key = _key("FAL_KEY")
    if not key:
        return {"provider": "fal.ai", "status": "not_configured", "balance": None, "detail": "API key not set"}
    # fal doesn't expose a simple validation endpoint; accept well-formed keys
    return {"provider": "fal.ai", "status": "active", "balance": None, "detail": "API key configured"}


async def _check_xai() -> dict:
    """Check xAI (Grok) API key by hitting /v1/models — real validation."""
    key = _key("XAI_API_KEY")
    if not key:
        # Detailed diagnostic so we can see WHY it's not finding the key
        env_exists = ENV_PATH.exists()
        env_keys = list(_read_env_file().keys()) if env_exists else []
        os_env_has = "XAI_API_KEY" in os.environ
        cfg_has = bool(getattr(cfg, "XAI_API_KEY", ""))
        detail = f"v2: env_file={env_exists}, keys_in_env={len(env_keys)}, os={os_env_has}, cfg={cfg_has}, path={ENV_PATH.name}"
        print(f"[api_status] xAI check: {detail} | full_keys={env_keys}")
        return {"provider": "xAI (Grok)", "status": "not_configured", "balance": None, "detail": detail, "balance_url": "https://console.x.ai/"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.x.ai/v1/models",
                headers={"Authorization": f"Bearer {key}"}
            )
            if resp.status_code == 200:
                return {"provider": "xAI (Grok)", "status": "active", "balance": None, "detail": "키 유효", "balance_url": "https://console.x.ai/"}
            elif resp.status_code == 401:
                return {"provider": "xAI (Grok)", "status": "invalid", "balance": None, "detail": "키 무효 (401)", "balance_url": "https://console.x.ai/"}
            else:
                return {"provider": "xAI (Grok)", "status": "active", "balance": None, "detail": f"키 설정됨 (HTTP {resp.status_code})", "balance_url": "https://console.x.ai/"}
    except Exception as e:
        return {"provider": "xAI (Grok)", "status": "error", "balance": None, "detail": str(e)[:100], "balance_url": "https://console.x.ai/"}


async def _check_kling() -> dict:
    """Check Kling keys — presence + basic JWT signing test."""
    ak = _key("KLING_ACCESS_KEY")
    sk = _key("KLING_SECRET_KEY")
    if not ak or not sk:
        missing = []
        if not ak: missing.append("ACCESS_KEY")
        if not sk: missing.append("SECRET_KEY")
        return {"provider": "Kling", "status": "not_configured", "balance": None, "detail": f"Missing: {', '.join(missing)}"}
    return {"provider": "Kling", "status": "active", "balance": None, "detail": "AK/SK 설정됨"}


def _check_simple(provider: str, key: str, label: str = "API key") -> dict:
    """Simple key presence check for providers without validation endpoints"""
    if not key:
        return {"provider": provider, "status": "not_configured", "balance": None, "detail": f"{label} not set"}
    masked = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    return {"provider": provider, "status": "active", "balance": None, "detail": f"키 설정됨 ({masked})"}


async def _probe_fal_video_model(fal_model: str) -> dict:
    """Actively probe a fal.ai video model queue endpoint with a dummy request-id
    status GET to distinguish auth failure (401/403) vs valid key (404/not_found).

    Returns raw HTTP code and (truncated) response body so the frontend can show
    the actual fal.ai message without guessing.
    """
    key = _key("FAL_KEY")
    if not key:
        return {
            "ok": False,
            "model": fal_model,
            "http_code": 0,
            "status": "not_configured",
            "detail": "FAL_KEY가 backend/.env에 설정되지 않았습니다",
            "body": "",
        }
    dummy_id = "00000000-0000-0000-0000-000000000000"
    # status endpoint is under app id (e.g. 'fal-ai/bytedance'), not full model path
    parts = fal_model.split("/")
    app_id = "/".join(parts[:2]) if len(parts) >= 2 else fal_model
    url = f"https://queue.fal.run/{app_id}/requests/{dummy_id}/status"
    headers = {"Authorization": f"Key {key}"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
        code = resp.status_code
        body = (resp.text or "")[:800]
        if code in (401, 403):
            return {
                "ok": False,
                "model": fal_model,
                "http_code": code,
                "status": "auth_failed",
                "detail": f"fal.ai가 키를 거부했습니다 (HTTP {code}). 키 재발급 또는 모델 접근 권한/결제 상태를 확인하세요.",
                "body": body,
            }
        if code == 404:
            # fal.ai가 dummy request-id를 찾지 못한 것 = 인증은 통과
            return {
                "ok": True,
                "model": fal_model,
                "http_code": 404,
                "status": "key_valid",
                "detail": "키 유효 (dummy request 조회 → 404 Not Found, 이는 인증 통과를 의미합니다)",
                "body": body,
            }
        # 기타 코드는 그대로 노출 — 해석은 사용자에게 맡김
        return {
            "ok": True,
            "model": fal_model,
            "http_code": code,
            "status": "unknown_ok",
            "detail": f"예상 밖 응답 (HTTP {code}). 본문을 확인하세요.",
            "body": body,
        }
    except httpx.TimeoutException:
        return {
            "ok": False,
            "model": fal_model,
            "http_code": 0,
            "status": "timeout",
            "detail": "fal.ai 응답 시간 초과 (15s)",
            "body": "",
        }
    except Exception as e:
        return {
            "ok": False,
            "model": fal_model,
            "http_code": 0,
            "status": "error",
            "detail": f"{type(e).__name__}: {str(e)[:300]}",
            "body": "",
        }


@router.get("/ffmpeg")
async def ffmpeg_status_probe():
    """Diagnostic: report whether ffmpeg is reachable and from which source.

    Returns `{ok, path, source}` on success, `{ok: false, error}` on failure.
    `source` is a short label: path, $FFMPEG_BIN, imageio-ffmpeg, scoop, winget, etc.
    """
    from app.services.video.subprocess_helper import ffmpeg_status, run_subprocess

    status = ffmpeg_status()
    if not status.get("ok"):
        return status

    # If ffmpeg is resolved, also probe `-version` so user sees actual version string
    try:
        rc, out, err = await run_subprocess(
            [status["path"], "-version"],
            timeout=10.0,
            capture_stdout=True,
            capture_stderr=True,
        )
        ver_line = (out or err or b"").splitlines()[0:1]
        status["version"] = ver_line[0].decode(errors="replace") if ver_line else ""
        status["exec_rc"] = rc
    except Exception as e:
        status["version"] = ""
        status["exec_error"] = f"{type(e).__name__}: {str(e)[:300]}"
    return status


@router.get("/fal/video-probe")
async def fal_video_probe(model: str = "seedance-lite"):
    """Diagnostic: probe fal.ai video model queue to distinguish key/account problems.

    Query ?model= accepts either internal id (seedance-lite / seedance-1.0)
    or a raw fal-ai/... path.
    """
    # Map internal id → fal model path
    mapping = {
        "seedance-lite": "fal-ai/bytedance/seedance/v1/lite/image-to-video",
        "seedance-1.0": "fal-ai/bytedance/seedance/v1/pro/image-to-video",
    }
    fal_model = mapping.get(model, model)
    result = await _probe_fal_video_model(fal_model)
    result["input_model"] = model
    return result


@router.get("/status")
async def check_all_api_status():
    """Check status and balance of all configured API keys.

    v1.1.55: Runway / Midjourney / Kling 타일 삭제 (사용자 요청).
    v1.1.55: 5 개 체크를 병렬(asyncio.gather)로 수행. 직렬이면 각 10초×5=최악 50초 걸려
    무한로딩처럼 보이던 문제 해결. 전체에도 15 초 하드 타임아웃을 건다.
    """
    import asyncio

    async def _safe(coro, label: str, balance_url: str | None = None):
        try:
            return await coro
        except Exception as e:
            out = {"provider": label, "status": "error", "balance": None, "detail": f"{type(e).__name__}: {str(e)[:120]}"}
            if balance_url:
                out["balance_url"] = balance_url
            return out

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                _safe(_check_anthropic(), "Anthropic", "https://console.anthropic.com/settings/billing"),
                _safe(_check_openai(), "OpenAI", "https://platform.openai.com/settings/organization/billing/overview"),
                _safe(_check_elevenlabs(), "ElevenLabs"),
                _safe(_check_fal(), "fal.ai"),
                _safe(_check_xai(), "xAI (Grok)", "https://console.x.ai/"),
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        results = [{"provider": n, "status": "error", "balance": None, "detail": "overall timeout 15s"} for n in ["Anthropic","OpenAI","ElevenLabs","fal.ai","xAI (Grok)"]]

    # v1.1.55: 수동 입력 잔액을 머지. 자동 조회 값(ElevenLabs balance) 은 건드리지 않고,
    # balance 가 비어 있는 타일에만 수동 입력값을 채운다.
    try:
        from app.routers.api_balances import get_manual_balance
        merged = []
        for r in results:
            r = dict(r)
            manual = get_manual_balance(r.get("provider", ""))
            if manual:
                r["manual_balance"] = manual
                if not r.get("balance"):
                    r["balance"] = manual["display"]
                    r["manual"] = True
            merged.append(r)
        results = merged
    except Exception as e:
        print(f"[api_status] manual balance merge failed: {e}")

    return {"apis": list(results)}
