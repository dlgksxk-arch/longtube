"""Flux image generation via fal.ai"""
import asyncio
import json
import httpx
from app.services.image.base import BaseImageService
from app.config import FAL_KEY

FAL_BASE = "https://queue.fal.run"


def _safe_json(resp: httpx.Response, where: str) -> dict:
    """Decode JSON with a clear error message instead of raw JSONDecodeError.

    fal.ai 큐 엔드포인트는 인증 실패 / 잘못된 경로에서 3xx 리다이렉트 +
    빈 본문을 돌려주는 경우가 있어 resp.json() 이 곧바로 터진다. 사용자에게
    원인을 바로 알 수 있게 상태코드/본문 앞부분을 메시지에 담는다.
    """
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError):
        body_preview = (resp.text or "").strip()[:200]
        if not body_preview:
            body_preview = "<empty body>"
        raise RuntimeError(
            f"fal.ai 응답을 JSON 으로 해석할 수 없습니다 ({where}, "
            f"status={resp.status_code}): {body_preview}"
        )


class FluxService(BaseImageService):
    # Flux dev/schnell 의 기본 text-to-image 엔드포인트는 image refs 를 받지 않는다.
    supports_reference_images = False

    def __init__(self, model_id: str = "flux-dev"):
        self.model_id = model_id
        self.display_name = "Flux Dev" if model_id == "flux-dev" else "Flux Schnell"
        self._fal_model = "fal-ai/flux/dev" if model_id == "flux-dev" else "fal-ai/flux/schnell"

    async def generate(self, prompt: str, width: int, height: int, output_path: str, reference_images=None) -> str:
        if reference_images:
            # 조용히 드롭하지 않고 로그에 경고 — router 레벨 폴백이 실패했을 때를 대비한 마지막 방어선
            import logging
            logging.getLogger(__name__).warning(
                "FluxService (%s) 는 reference_images 를 사용하지 않습니다. "
                "레퍼런스 스타일을 유지하려면 nano-banana 또는 gpt-image-1 을 선택하세요. "
                "드롭된 레퍼런스 %d 장.",
                self.model_id, len(reference_images),
            )
        if not FAL_KEY:
            raise RuntimeError(
                "FAL_KEY 환경변수가 설정돼 있지 않습니다. .env 에 FAL_KEY 를 "
                "넣거나 이미지 모델을 OpenAI / Grok 등으로 바꿔주세요."
            )

        headers = {"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=180, follow_redirects=True) as client:
            # Submit
            resp = await client.post(
                f"{FAL_BASE}/{self._fal_model}",
                headers=headers,
                json={
                    "prompt": f"cinematic, high quality, detailed, {prompt}",
                    "image_size": {"width": width, "height": height},
                    "num_images": 1,
                    "guidance_scale": 7.5,
                },
            )
            resp.raise_for_status()
            data = _safe_json(resp, "submit")

            # fal.ai returns result directly or request_id for polling.
            # ★ 중요: status/response URL 은 submit 응답이 주는 그대로 써야 한다.
            # 경로를 직접 조립하면 (`fal-ai/flux/dev/requests/...`) fal.ai 가
            # 405 Method Not Allowed 를 뱉는다. 실제 status 경로는 서브경로
            # (`/dev`) 가 빠진 `fal-ai/flux/requests/.../status` 이기 때문.
            if "images" in data:
                image_url = data["images"][0]["url"]
            elif "request_id" in data:
                status_url = data.get("status_url")
                response_url = data.get("response_url")
                if not status_url or not response_url:
                    raise RuntimeError(
                        f"fal.ai 응답에 status_url/response_url 이 없습니다: "
                        f"{str(data)[:200]}"
                    )
                image_url = await self._poll_result(
                    client, headers, status_url, response_url
                )
            else:
                raise RuntimeError(
                    f"fal.ai 응답에 images/request_id 가 없습니다: "
                    f"{str(data)[:200]}"
                )

            # Download
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(img_resp.content)

        return output_path

    async def _poll_result(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        status_url: str,
        response_url: str,
    ) -> str:
        for _ in range(60):
            resp = await client.get(status_url, headers=headers)
            resp.raise_for_status()
            data = _safe_json(resp, "poll-status")
            if data.get("status") == "COMPLETED":
                result = await client.get(response_url, headers=headers)
                result.raise_for_status()
                rdata = _safe_json(result, "poll-result")
                return rdata["images"][0]["url"]
            await asyncio.sleep(3)
        raise TimeoutError("Flux image generation timed out")
