"""OpenAI GPT LLM service"""
import asyncio
import json
from openai import AsyncOpenAI
from app.services.llm.base import BaseLLMService
from app.services.cancel_ctx import OperationCancelled, raise_if_cancelled
from app import config


class GPTService(BaseLLMService):
    def __init__(self, model_id: str = "gpt-4o"):
        self.model_id = model_id
        self.display_name = f"GPT ({model_id})"
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
        self._client_factory = AsyncOpenAI

    def _client(self):
        """Create a client in the active event loop."""
        return self._client_factory(api_key=config.OPENAI_API_KEY)

    async def generate_script(self, topic: str, config: dict) -> dict:
        # v1.1.32: target_duration 기반 동적 max_tokens (600초=120컷 truncation 방지)
        try:
            estimated_cuts = int(config.get("target_cuts") or 0)
        except (TypeError, ValueError):
            estimated_cuts = 0
        if estimated_cuts <= 0:
            try:
                target_duration = int(config.get("target_duration") or 300)
            except (TypeError, ValueError):
                target_duration = 300
            estimated_cuts = max(1, target_duration // 5)
        dynamic_max = max(8192, estimated_cuts * 220 + 2048)
        dynamic_max = min(dynamic_max, 16000)  # GPT-4o 실용 상한
        default_timeout = 300.0 if estimated_cuts >= 100 else 180.0
        try:
            request_timeout = float(config.get("script_generation_timeout_sec", default_timeout) or default_timeout)
        except (TypeError, ValueError):
            request_timeout = default_timeout
        request_timeout = max(30.0, min(300.0, request_timeout))

        raise_if_cancelled("gpt generate_script")
        async with self._client() as client:
            try:
                response = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=self.model_id,
                        messages=[
                            {"role": "system", "content": self._get_system_prompt(config)},
                            {"role": "user", "content": self._build_user_prompt(topic, config)},
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.8,
                        max_tokens=dynamic_max,
                    ),
                    timeout=request_timeout,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"script generation timed out after {request_timeout:.0f}s"
                ) from exc
        raise_if_cancelled("gpt generate_script")
        return json.loads(response.choices[0].message.content)

    async def generate_tags(
        self,
        title: str,
        topic: str,
        narration: str = "",
        max_tags: int = 15,
        language: str = "ko",
    ) -> list[str]:
        """GPT 로 YouTube 태그 후보 JSON 생성. json_object 응답 포맷 사용."""
        prompt = self._build_tag_prompt(title, topic, narration, max_tags, language)
        raise_if_cancelled("gpt generate_tags")
        async with self._client() as client:
            response = await client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a YouTube SEO assistant. Respond with a single "
                            'JSON object of the form {"tags": [...]}. No prose. '
                            "Match the language requested in the user prompt EXACTLY."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
        raise_if_cancelled("gpt generate_tags")
        raw = response.choices[0].message.content or ""
        return self._parse_tag_response(raw)

    async def generate_metadata(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        max_tags: int = 15,
        episode_number: int | None = None,
    ) -> dict:
        """GPT 로 title_hook / description / tags 를 한 번에 생성."""
        prompt = self._build_metadata_prompt(
            title, topic, narration, language, max_tags, episode_number
        )
        raise_if_cancelled("gpt generate_metadata")
        async with self._client() as client:
            response = await client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a YouTube metadata writer. Respond with a single "
                            'JSON object with keys "title_hook", "description", "tags". '
                            "No prose. Match the language requested in the user "
                            "prompt EXACTLY — do not mix languages."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
        raise_if_cancelled("gpt generate_metadata")
        raw = response.choices[0].message.content or ""
        return self._parse_metadata_response(raw)

    async def generate_thumbnail_image_prompt(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        character_description: str = "",
    ) -> str:
        """GPT 로 YouTube 썸네일용 image generation 프롬프트 한 줄 생성."""
        prompt = self._build_thumbnail_prompt_request(
            title, topic, narration, language, character_description
        )
        try:
            raise_if_cancelled("gpt thumbnail_prompt")
            async with self._client() as client:
                response = await client.chat.completions.create(
                    model=self.model_id,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a cinematic image-prompt engineer. Respond with a "
                                'single JSON object {"prompt": "..."} containing one '
                                "English image-generation prompt. No prose outside the JSON."
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.8,
                )
            raise_if_cancelled("gpt thumbnail_prompt")
        except OperationCancelled:
            raise
        except Exception:
            return self._fallback_thumbnail_prompt(title, topic, language, character_description)
        raw = response.choices[0].message.content or ""
        parsed = self._parse_thumbnail_prompt_response(raw)
        return parsed or self._fallback_thumbnail_prompt(title, topic, language, character_description)

    async def rewrite_narration_for_timing(
        self,
        *,
        topic: str,
        narration: str,
        language: str,
        cut_number: int,
        total_cuts: int,
        measured_duration: float,
        target_min: float,
        target_max: float,
        direction: str,
        target_chars: int,
        image_prompt: str = "",
        scene_type: str = "",
        previous_narration: str = "",
        next_narration: str = "",
    ) -> str:
        prompt = self._build_narration_timing_prompt(
            topic=topic,
            narration=narration,
            language=language,
            cut_number=cut_number,
            total_cuts=total_cuts,
            measured_duration=measured_duration,
            target_min=target_min,
            target_max=target_max,
            direction=direction,
            target_chars=target_chars,
            image_prompt=image_prompt,
            scene_type=scene_type,
            previous_narration=previous_narration,
            next_narration=next_narration,
        )
        raise_if_cancelled("gpt timing_rewrite")
        async with self._client() as client:
            response = await client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a precise TTS narration timing editor. "
                            "Return JSON only."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=300,
            )
        raise_if_cancelled("gpt timing_rewrite")
        raw = response.choices[0].message.content or ""
        return self._parse_narration_rewrite_response(raw)
