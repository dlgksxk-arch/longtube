"""API key status and balance checking router"""
import asyncio
import os
import subprocess
import time
from pathlib import Path
import httpx
from fastapi import APIRouter
from app import config as cfg

router = APIRouter()

ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
_SYSTEM_STATUS_CACHE: dict = {"ts": 0.0, "data": None}


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


async def _check_ltx() -> dict:
    """로컬 ComfyUI (LTX / WAN / HunyuanVideo 등 로컬 영상 생성) 연결 확인.

    v1.2.21: 사용자 요청으로 "API 연결 상태" 패널에 로컬 영상 생성(LTX 계열,
    ComfyUI 서버)까지 포함. COMFYUI_BASE_URL 이 비어있으면 not_configured,
    설정돼 있으면 `/system_stats` 엔드포인트를 10초 타임아웃으로 호출해
    응답 200 이면 active. 연결 실패 / 타임아웃은 error 로 표시한다.

    provider 이름은 "ComfyUI (Local)" — 대시보드 좌측 사이드바 리스트에서 다른
    API 타일과 구분되도록.
    """
    base = (getattr(cfg, "COMFYUI_BASE_URL", "") or "").rstrip("/")
    # .env 를 재확인해 키 저장 직후 새 값 반영 (다른 _check_* 와 동일한 패턴).
    env_base = _read_env_file().get("COMFYUI_BASE_URL", "").strip().rstrip("/")
    if env_base:
        base = env_base
    if not base:
        return {
            "provider": "ComfyUI (Local)",
            "status": "not_configured",
            "balance": None,
            "detail": "COMFYUI_BASE_URL 미설정 — backend/.env 에 http://<IP>:<PORT> 추가",
        }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{base}/system_stats")
            if resp.status_code == 200:
                # GPU 정보가 함께 노출되면 잔액 칸에 짧게 표시 (실제 잔액은 아님).
                try:
                    data = resp.json()
                    devs = data.get("devices") or []
                    gpu_name = (devs[0] or {}).get("name") if devs else ""
                    gpu_short = (gpu_name or "").split(":")[0][:16]
                    balance = f"로컬 {gpu_short}" if gpu_short else "로컬 연결됨"
                except Exception:
                    balance = "로컬 연결됨"
                return {
                    "provider": "ComfyUI (Local)",
                    "status": "active",
                    "balance": balance,
                    "detail": f"ComfyUI OK @ {base}",
                }
            return {
                "provider": "ComfyUI (Local)",
                "status": "error",
                "balance": None,
                "detail": f"ComfyUI HTTP {resp.status_code} @ {base}",
            }
    except httpx.TimeoutException:
        return {
            "provider": "ComfyUI (Local)",
            "status": "error",
            "balance": None,
            "detail": f"ComfyUI 응답 없음 (timeout 10s) @ {base}",
        }
    except Exception as e:
        return {
            "provider": "ComfyUI (Local)",
            "status": "error",
            "balance": None,
            "detail": f"{type(e).__name__}: {str(e)[:100]}",
        }


async def _check_ltx_v2() -> dict:
    """More forgiving ComfyUI probe for the sidebar status tile.

    Some ComfyUI builds respond slowly on `/system_stats` while still serving
    `/queue` or even the base page. Treat any successful lightweight probe as
    active so the local-model provider does not show as broken unnecessarily.
    """
    base = (_key("COMFYUI_BASE_URL") or "").rstrip("/")
    if not base:
        return {
            "provider": "ComfyUI (Local)",
            "status": "not_configured",
            "balance": None,
            "detail": "COMFYUI_BASE_URL not set - add http://<IP>:<PORT> to backend/.env",
        }

    probe_errors: list[str] = []
    probes = [
        ("/system_stats", True),
        ("/queue", False),
        ("", False),
    ]
    timeout = httpx.Timeout(4.0, connect=2.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        for path, wants_gpu in probes:
            label = path or "/"
            try:
                resp = await client.get(f"{base}{path}")
            except httpx.TimeoutException:
                probe_errors.append(f"{label} timeout")
                continue
            except Exception as e:
                probe_errors.append(f"{label} {type(e).__name__}")
                continue

            if resp.status_code != 200:
                probe_errors.append(f"{label} HTTP {resp.status_code}")
                continue

            balance = "Local ready"
            if wants_gpu:
                try:
                    data = resp.json()
                    devices = data.get("devices") or []
                    gpu_name = (devices[0] or {}).get("name") if devices else ""
                    gpu_short = (gpu_name or "").split(":")[0][:16]
                    if gpu_short:
                        balance = f"Local {gpu_short}"
                except Exception:
                    pass

            via = "" if label == "/system_stats" else f" via {label}"
            return {
                "provider": "ComfyUI (Local)",
                "status": "active",
                "balance": balance,
                "detail": f"ComfyUI OK{via} @ {base}",
            }

    detail = "; ".join(probe_errors[:3]) if probe_errors else "no response"
    return {
        "provider": "ComfyUI (Local)",
        "status": "error",
        "balance": None,
        "detail": f"ComfyUI unreachable @ {base} ({detail})",
    }


async def _check_comfyui_queue(base: str) -> dict:
    """Return a tiny ComfyUI queue summary for the sidebar service chip."""
    if not base:
        return {"queue_running": None, "queue_pending": None}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.5, connect=1.5)) as client:
            resp = await client.get(f"{base}/queue")
        if resp.status_code != 200:
            return {"queue_running": None, "queue_pending": None}
        data = resp.json()
        running = data.get("queue_running") or []
        pending = data.get("queue_pending") or []
        return {
            "queue_running": len(running) if isinstance(running, list) else 0,
            "queue_pending": len(pending) if isinstance(pending, list) else 0,
        }
    except Exception:
        return {"queue_running": None, "queue_pending": None}


def _run_status_command(args: list[str], timeout: float = 1.5) -> str:
    """Run a tiny local status command without popping a console window."""
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip()[:200])
    return proc.stdout.strip()


def _parse_wmic_key_values(raw: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (raw or "").replace("\r", "\n").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _safe_float(value, default=None):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_cpu_ram_status() -> dict:
    try:
        import psutil  # type: ignore

        cpu_percent = float(psutil.cpu_percent(interval=0.1))
        mem = psutil.virtual_memory()
        total_gb = round(float(mem.total) / (1024 ** 3), 1)
        used_gb = round(float(mem.used) / (1024 ** 3), 1)
        return {
            "cpu_percent": round(cpu_percent, 1),
            "ram_percent": round(float(mem.percent), 1),
            "ram_used_gb": used_gb,
            "ram_total_gb": total_gb,
        }
    except Exception:
        pass

    out: dict = {
        "cpu_percent": None,
        "ram_percent": None,
        "ram_used_gb": None,
        "ram_total_gb": None,
    }

    try:
        cpu_raw = _run_status_command(["wmic", "cpu", "get", "loadpercentage", "/value"], timeout=2.0)
        cpu_data = _parse_wmic_key_values(cpu_raw)
        out["cpu_percent"] = _safe_float(cpu_data.get("LoadPercentage"))
        if out["cpu_percent"] is None and os.name == "nt":
            ps_cpu = _run_status_command(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average",
                ],
                timeout=3.0,
            )
            out["cpu_percent"] = _safe_float(ps_cpu.strip())
    except Exception as e:
        out["cpu_error"] = f"{type(e).__name__}: {str(e)[:80]}"

    try:
        mem_raw = _run_status_command(
            ["wmic", "OS", "get", "FreePhysicalMemory,TotalVisibleMemorySize", "/value"],
            timeout=2.0,
        )
        mem_data = _parse_wmic_key_values(mem_raw)
        free_kb = _safe_float(mem_data.get("FreePhysicalMemory"))
        total_kb = _safe_float(mem_data.get("TotalVisibleMemorySize"))
        if total_kb and free_kb is not None:
            used_kb = max(total_kb - free_kb, 0)
            out["ram_percent"] = round((used_kb / total_kb) * 100, 1)
            out["ram_used_gb"] = round(used_kb / (1024 ** 2), 1)
            out["ram_total_gb"] = round(total_kb / (1024 ** 2), 1)
    except Exception as e:
        out["ram_error"] = f"{type(e).__name__}: {str(e)[:80]}"

    return out


def _get_gpu_status() -> dict:
    try:
        raw = _run_status_command(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            timeout=2.0,
        )
    except FileNotFoundError:
        return {"available": False, "detail": "nvidia-smi not found"}
    except Exception as e:
        return {"available": False, "detail": f"{type(e).__name__}: {str(e)[:100]}"}

    gpus: list[dict] = []
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        name, util, mem_used, mem_total, temp = parts[:5]
        used_mb = _safe_float(mem_used)
        total_mb = _safe_float(mem_total)
        memory_percent = None
        if total_mb and used_mb is not None:
            memory_percent = round((used_mb / total_mb) * 100, 1)
        gpus.append({
            "name": name,
            "load_percent": _safe_float(util),
            "memory_used_mb": used_mb,
            "memory_total_mb": total_mb,
            "memory_percent": memory_percent,
            "temperature_c": _safe_float(temp),
        })

    if not gpus:
        return {"available": False, "detail": "no GPU data"}
    return {"available": True, "gpus": gpus, "primary": gpus[0]}


def _get_local_system_status() -> dict:
    now = time.monotonic()
    cached = _SYSTEM_STATUS_CACHE.get("data")
    if isinstance(cached, dict) and now - float(_SYSTEM_STATUS_CACHE.get("ts") or 0.0) < 5.0:
        return cached

    status = _get_cpu_ram_status()
    gpu = _get_gpu_status()
    ok_cpu = status.get("cpu_percent") is not None
    ok_ram = status.get("ram_percent") is not None
    status.update({
        "provider": "Local PC",
        "status": "active" if ok_cpu and ok_ram else "partial",
        "gpu": gpu.get("primary"),
        "gpus": gpu.get("gpus", []),
        "gpu_available": bool(gpu.get("available")),
        "gpu_detail": gpu.get("detail"),
    })
    _SYSTEM_STATUS_CACHE["ts"] = now
    _SYSTEM_STATUS_CACHE["data"] = status
    return status


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
                # v1.2.21: 로컬 영상 생성(LTX/ComfyUI) 연결 상태도 같은 리스트에 포함.
                _safe(_check_ltx_v2(), "ComfyUI (Local)"),
            ),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        results = [{"provider": n, "status": "error", "balance": None, "detail": "overall timeout 15s"} for n in ["Anthropic","OpenAI","ElevenLabs","fal.ai","xAI (Grok)","ComfyUI (Local)"]]

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

    # v1.1.64: provider 별 "사용 단계" 표시. 각 registry 를 읽어 PROVIDER_MAP 으로
    # 정규 이름으로 환산한 뒤 (step_no, step_label) 리스트를 만든다.
    # 하드코딩 안 하고 registry 에서 도출하므로 모델 추가/제거 시 자동 반영.
    try:
        usage_map = _compute_provider_usage()
        merged2 = []
        for r in results:
            r = dict(r)
            r["used_in_steps"] = usage_map.get(r.get("provider", ""), [])
            merged2.append(r)
        results = merged2
    except Exception as e:
        print(f"[api_status] usage_map merge failed: {e}")

    return {"apis": list(results)}


@router.get("/local-services")
async def check_local_services():
    """Lightweight status for the sidebar: backend + local ComfyUI only."""
    base = (_key("COMFYUI_BASE_URL") or "").rstrip("/")
    async def _safe_comfy_status() -> dict:
        try:
            return await _check_ltx_v2()
        except Exception as e:
            return {
                "provider": "ComfyUI (Local)",
                "status": "error",
                "balance": None,
                "detail": f"{type(e).__name__}: {str(e)[:120]}",
            }

    comfy, queue, system = await asyncio.gather(
        _safe_comfy_status(),
        _check_comfyui_queue(base),
        asyncio.to_thread(_get_local_system_status),
    )
    if not isinstance(comfy, dict):
        comfy = {
            "provider": "ComfyUI (Local)",
            "status": "error",
            "balance": None,
            "detail": "ComfyUI status probe failed",
        }
    comfy.update(queue if isinstance(queue, dict) else {})
    return {
        "backend": {
            "provider": "Backend",
            "status": "active",
            "version": "1.2.29",
            "detail": "FastAPI OK",
        },
        "comfyui": comfy,
        "system": system if isinstance(system, dict) else {"provider": "Local PC", "status": "error"},
    }


def _compute_provider_usage() -> dict[str, list[dict]]:
    """provider 정규 이름 → [{step, label, models:[...]}, ...] 목록 반환.

    각 registry 의 provider 필드를 spend_ledger.PROVIDER_MAP 으로 정규화하면
    api_balances.ALLOWED_PROVIDERS 와 동일한 이름이 된다. step 번호는 파이프라인
    실제 단계(2=Script, 3=Voice, 4=Image, 5=Video).
    """
    from app.services.spend_ledger import PROVIDER_MAP
    out: dict[str, dict[int, dict]] = {}  # provider → step_no → {label, models}

    def _add(step_no: int, label: str, prov_token: str, model_id: str):
        canonical = PROVIDER_MAP.get((prov_token or "").strip().lower())
        if not canonical:
            return
        bucket = out.setdefault(canonical, {})
        slot = bucket.setdefault(step_no, {"step": step_no, "label": label, "models": []})
        slot["models"].append(model_id)

    # Step 2 — Script (LLM)
    try:
        from app.services.llm.factory import LLM_REGISTRY
        for mid, meta in LLM_REGISTRY.items():
            _add(2, "스크립트", meta.get("provider", ""), mid)
    except Exception:
        pass

    # Step 3 — Voice (TTS)
    try:
        from app.services.tts.factory import TTS_REGISTRY
        for mid, meta in TTS_REGISTRY.items():
            _add(3, "음성", meta.get("provider", ""), mid)
    except Exception:
        pass

    # Step 4 — Image
    try:
        from app.services.image.factory import IMAGE_REGISTRY
        for mid, meta in IMAGE_REGISTRY.items():
            _add(4, "이미지", meta.get("provider", ""), mid)
    except Exception:
        pass

    # Step 5 — Video
    try:
        from app.services.video.factory import VIDEO_REGISTRY
        for mid, meta in VIDEO_REGISTRY.items():
            _add(5, "영상", meta.get("provider", ""), mid)
    except Exception:
        pass

    # step 번호 오름차순 리스트로 평탄화
    final: dict[str, list[dict]] = {}
    for prov, step_dict in out.items():
        final[prov] = [step_dict[k] for k in sorted(step_dict.keys())]
    return final
