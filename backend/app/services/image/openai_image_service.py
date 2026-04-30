"""OpenAI DALL-E / GPT Image generation service
v1.1.52: 재시도 로직 추가.
"""
import asyncio
import httpx
import base64
from pathlib import Path
from typing import Optional
from app.services.image.base import BaseImageService
from app.services.cancel_ctx import raise_if_cancelled  # v1.2.25 cancel 방어
from app import config


class OpenAIImageService(BaseImageService):
    """OpenAI 이미지 생성 (gpt-image-1, dall-e-3)"""

    def __init__(self, model_id: str):
        self.model_id = model_id
        self.display_name = model_id

        # Map our model ID to OpenAI model name
        self._model_map = {
            "openai-image-1": "gpt-image-1",
            "openai-dalle3": "dall-e-3",
        }
        # gpt-image-1 만 /edits 엔드포인트로 레퍼런스 이미지 받음
        self.supports_reference_images = (model_id == "openai-image-1")

    async def generate(
        self,
        prompt: str,
        width: int,
        height: int,
        output_path: str,
        reference_images: Optional[list[str]] = None,
    ) -> str:
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 매 호출마다 config 에서 읽음.
        if not config.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY not set")

        openai_model = self._model_map.get(self.model_id, "gpt-image-1")
        size = self._resolve_size(width, height, openai_model)

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # If reference images exist and model supports it, use /edits endpoint
        if reference_images and openai_model == "gpt-image-1":
            return await self._generate_with_references(
                prompt, size, output_path, reference_images
            )

        # Standard generation without reference images
        return await self._generate_standard(prompt, size, output_path, openai_model)

    async def _generate_standard(
        self, prompt: str, size: str, output_path: str, openai_model: str
    ) -> str:
        """Standard text-to-image generation."""
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }

        if openai_model == "gpt-image-1":
            payload = {
                "model": openai_model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "quality": "medium",
            }
        else:
            payload = {
                "model": openai_model,
                "prompt": prompt,
                "n": 1,
                "size": size,
                "quality": "standard",
                "response_format": "b64_json",
            }

        MAX_RETRIES = 3
        for attempt in range(1, MAX_RETRIES + 1):
            # v1.2.25: 재시도 루프 진입 시마다 cancel 체크.
            raise_if_cancelled(f"openai-generate:{openai_model}")
            try:
                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/images/generations",
                        headers=headers,
                        json=payload,
                    )
                    if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                        wait = attempt * 5
                        print(f"[Image] OpenAI HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue
                    if resp.status_code >= 400:
                        err_body = resp.text[:500] if resp.text else ""
                        print(f"[Image] OpenAI /generations HTTP {resp.status_code}: {err_body}")
                        raise RuntimeError(f"OpenAI /generations HTTP {resp.status_code}: {err_body}")
                    resp.raise_for_status()
                    data = resp.json()
                break
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                if attempt < MAX_RETRIES:
                    wait = attempt * 5
                    print(f"[Image] OpenAI 연결 오류, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
                raise

        self._save_result(data["data"][0], output_path)
        return output_path

    async def _generate_with_references(
        self,
        prompt: str,
        size: str,
        output_path: str,
        reference_images: list[str],
    ) -> str:
        """Generate image with reference images using /v1/images/edits endpoint.
        gpt-image-1 supports up to 10 reference images.

        v1.1.54: 재시도 로직 추가 + /edits 3회 실패 시 표준 생성 폴백.
        """
        headers = {
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        }

        # Build multipart form data
        # Limit to 4 reference images to keep cost/latency reasonable
        ref_paths = reference_images[:4]

        def _mime_for(p: Path) -> str:
            ext = p.suffix.lower().lstrip(".")
            if ext in ("jpg", "jpeg"):
                return "image/jpeg"
            if ext == "webp":
                return "image/webp"
            # gpt-image-1 /edits only officially accepts png/jpeg/webp. Default to png.
            return "image/png"

        MAX_RETRIES = 3
        last_err = None

        for attempt in range(1, MAX_RETRIES + 1):
            # v1.2.25: /edits 재시도 루프에서도 cancel 체크.
            raise_if_cancelled("openai-edits")
            opened_files = []
            files = []
            try:
                for ref_path in ref_paths:
                    try:
                        p = Path(ref_path)
                        if p.exists() and p.stat().st_size > 0:
                            f = open(p, "rb")
                            opened_files.append(f)
                            files.append(("image[]", (p.name, f, _mime_for(p))))
                    except (OSError, PermissionError):
                        continue

                # If no reference files could be opened, fall back to standard generation
                if not files:
                    return await self._generate_standard(
                        prompt, size, output_path, "gpt-image-1"
                    )

                form_data = {
                    "model": "gpt-image-1",
                    "prompt": prompt,
                    "n": "1",
                    "size": size,
                    "quality": "medium",
                }

                async with httpx.AsyncClient(timeout=180) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/images/edits",
                        headers=headers,
                        data=form_data,
                        files=files,
                    )

                if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                    wait = attempt * 5
                    print(f"[Image] /edits HTTP {resp.status_code}, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code >= 400:
                    err_detail = resp.text[:300] if resp.text else f"HTTP {resp.status_code}"
                    print(f"[Image] /edits 실패 (HTTP {resp.status_code}): {err_detail}")
                    last_err = RuntimeError(f"/edits HTTP {resp.status_code}: {err_detail}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(attempt * 3)
                        continue
                    break  # 모든 재시도 실패 → 명시적 RuntimeError

                data = resp.json()
                self._save_result(data["data"][0], output_path)
                return output_path

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_err = e
                if attempt < MAX_RETRIES:
                    wait = attempt * 5
                    print(f"[Image] /edits 연결 오류, {wait}초 후 재시도 ({attempt}/{MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue
            finally:
                for f in opened_files:
                    f.close()

        # v1.2.20: 폴백 제거. 표준 생성으로 갈아엎지 않고 명시적 RuntimeError.
        # 사용자 요구: "API 이용할 때 설정된 모델의 API 연결 안되있을때 알림창
        # 띄우고 풀백으로 처리하지마." — 레퍼런스가 무시된 채 다른 결과를 내는
        # 것을 막는다. task.error 로 전파되어 UI 알림으로 노출.
        raise RuntimeError(
            f"[OpenAI Image] /edits 엔드포인트 {MAX_RETRIES}회 모두 실패 — "
            f"폴백 비활성화. 원인: {last_err}. OPENAI_API_KEY/잔액/네트워크를 "
            f"확인하세요."
        )

    def _save_result(self, result: dict, output_path: str):
        """Save image result (b64_json or url) to file."""
        # Ensure parent dir exists (safety net)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if "b64_json" in result:
            img_bytes = base64.b64decode(result["b64_json"])
            with open(output_path, "wb") as f:
                f.write(img_bytes)
        elif "url" in result:
            import urllib.request
            urllib.request.urlretrieve(result["url"], output_path)
        else:
            raise ValueError(f"Unexpected API response: no b64_json or url in result. Keys: {list(result.keys())}")

    def _resolve_size(self, width: int, height: int, model: str) -> str:
        """OpenAI는 정해진 사이즈만 지원"""
   