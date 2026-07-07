"""OpenAI GPT LLM service"""
import json
from openai import AsyncOpenAI
from app.services.llm.base import BaseLLMService
from app.services.llm.script_quality import assert_script_quality, assert_story_plan
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

    def _is_latest_gpt(self) -> bool:
        return str(self.model_id or "").startswith("gpt-5")

    def _latest_gpt_output_budget(self, requested: int) -> int:
        return min(128000, max(64000, int(requested or 0)))

    async def _create_json_chat_completion(
        self,
        client,
        *,
        messages: list[dict],
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout=None,
    ):
        kwargs = {
            "model": self.model_id,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "timeout": timeout,
        }
        if max_tokens is not None:
            if self._is_latest_gpt():
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
        if temperature is not None and not self._is_latest_gpt():
            kwargs["temperature"] = temperature
        return await client.chat.completions.create(**kwargs)

    @staticmethod
    def _response_to_jsonable(response) -> dict:
        try:
            return response.model_dump(mode="json")
        except Exception:
            try:
                return json.loads(response.model_dump_json())
            except Exception:
                return {"repr": repr(response)}

    def _save_raw_response(self, project_id: str | None, label: str, response) -> None:
        if not project_id:
            return
        try:
            project_dir = config.resolve_project_dir(str(project_id), create=True)
            raw_dir = project_dir / "llm_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in label).strip("_") or "response"
            (raw_dir / f"{safe}.json").write_text(
                json.dumps(self._response_to_jsonable(response), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _message_content_text(response) -> str:
        try:
            content = response.choices[0].message.content
        except Exception:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("content") or ""))
                else:
                    parts.append(str(getattr(item, "text", "") or getattr(item, "content", "") or ""))
            return "".join(parts)
        return str(content or "")

    @staticmethod
    def _finish_reason(response) -> str:
        try:
            return str(response.choices[0].finish_reason or "")
        except Exception:
            return ""

    @staticmethod
    def _usage_summary(response) -> str:
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return ""
            return json.dumps(
                usage.model_dump(mode="json") if hasattr(usage, "model_dump") else usage,
                ensure_ascii=False,
            )
        except Exception:
            return ""

    def _record_usage(self, response, note: str, project_id: str | None = None):
        try:
            from app.services import spend_ledger
            spend_ledger.record_llm_usage(
                self.model_id,
                getattr(response, "usage", None),
                project_id=project_id,
                note=note,
            )
        except Exception:
            pass

    async def generate_story_plan(self, topic: str, config: dict) -> dict:
        cached = self._load_cached_story_plan(topic, config)
        if cached is not None:
            return cached

        target_cuts = self._expected_cut_count(config)
        max_tokens = 18000 if target_cuts >= 100 else 7000
        if self._is_latest_gpt():
            max_tokens = self._latest_gpt_output_budget(max_tokens)
        raise_if_cancelled("gpt story_plan")
        async with self._client() as client:
            kwargs = {
                "model": self.model_id,
                "messages": [
                    {"role": "system", "content": self._build_story_plan_text_system_prompt(config)},
                    {"role": "user", "content": self._build_story_plan_text_user_prompt(topic, config)},
                ],
                "timeout": None,
            }
            if self._is_latest_gpt():
                kwargs["max_completion_tokens"] = max_tokens
            else:
                kwargs["max_tokens"] = max_tokens
                kwargs["temperature"] = 0.4
            response = await client.chat.completions.create(**kwargs)
        raise_if_cancelled("gpt story_plan")
        self._record_usage(response, "story_plan", config.get("__project_id"))
        project_id = config.get("__project_id")
        self._save_raw_response(project_id, "story_plan_response", response)
        raw = self._message_content_text(response).strip()
        if not raw:
            raise RuntimeError(
                "OpenAI story plan response was empty "
                f"(model={self.model_id}, finish_reason={self._finish_reason(response)}, "
                f"usage={self._usage_summary(response)})"
            )
        parsed = self._parse_story_plan_text_response(raw, topic=topic, config=config)
        parsed = self._normalize_story_plan_structure(parsed)
        assert_story_plan(parsed, target_cuts, topic, config)
        self._save_story_plan(topic, config, parsed)
        return parsed

    async def generate_script(self, topic: str, config: dict) -> dict:
        # v1.1.32: target_duration 기반 동적 max_tokens (롱폼 truncation 방지)
        estimated_cuts = self._expected_cut_count(config)
        dynamic_max = max(8192, estimated_cuts * 360 + 8192)
        dynamic_max = min(dynamic_max, 128000)
        if self._is_latest_gpt():
            dynamic_max = self._latest_gpt_output_budget(dynamic_max)
        story_plan = await self._ensure_story_plan_for_script(topic, config)
        script_config = dict(config or {})
        script_config["story_plan"] = story_plan
        project_id = config.get("__project_id")
        timing_issues: list[dict] = []
        max_attempts = int(script_config.get("script_timing_retry_attempts") or 3)
        max_attempts = max(1, min(5, max_attempts))
        for attempt in range(1, max_attempts + 1):
            attempt_config = dict(script_config)
            if timing_issues:
                attempt_config["__script_timing_retry_instruction"] = self._script_timing_retry_instruction(
                    script_config,
                    timing_issues,
                )
            raise_if_cancelled("gpt generate_script")
            async with self._client() as client:
                response = await self._create_json_chat_completion(
                    client,
                    messages=[
                        {"role": "system", "content": self._get_system_prompt(attempt_config)},
                        {"role": "user", "content": self._build_user_prompt(topic, attempt_config)},
                    ],
                    temperature=0.8 if attempt == 1 else 0.35,
                    max_tokens=dynamic_max,
                    timeout=None,
                )
            raise_if_cancelled("gpt generate_script")
            self._record_usage(response, "script", project_id)
            raw_label = "script_response" if attempt == 1 else f"script_timing_retry_{attempt}_response"
            self._save_raw_response(project_id, raw_label, response)
            raw = self._message_content_text(response).strip()
            if not raw:
                raise RuntimeError(
                    "OpenAI script response was empty "
                    f"(model={self.model_id}, finish_reason={self._finish_reason(response)}, "
                    f"usage={self._usage_summary(response)})"
                )
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "OpenAI script response was not valid JSON "
                    f"(model={self.model_id}, finish_reason={self._finish_reason(response)}, "
                    f"error={exc})"
                ) from exc
            cuts = parsed.get("cuts") or []
            if len(cuts) != estimated_cuts:
                raise ValueError(
                    f"script generation returned {len(cuts)} cuts, expected {estimated_cuts}"
                )
            parsed = self.strengthen_visual_context(parsed, config)
            parsed = self.normalize_v31_story_contract(parsed, config, topic)
            assert_script_quality(parsed, topic)
            timing_issues = self.validate_script_timing(parsed, config)
            if timing_issues and attempt < max_attempts:
                continue
            self.assert_script_timing(parsed, config)
            return parsed
        raise RuntimeError("OpenAI script generation did not return a valid script")

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
            response = await self._create_json_chat_completion(
                client,
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
                temperature=0.5,
            )
        raise_if_cancelled("gpt generate_tags")
        self._record_usage(response, "tags")
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
            response = await self._create_json_chat_completion(
                client,
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
                temperature=0.7,
            )
        raise_if_cancelled("gpt generate_metadata")
        self._record_usage(response, "metadata")
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
                response = await self._create_json_chat_completion(
                    client,
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
                    temperature=0.8,
                )
            raise_if_cancelled("gpt thumbnail_prompt")
            self._record_usage(response, "thumbnail_prompt")
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
            response = await self._create_json_chat_completion(
                client,
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
                temperature=0.2,
                max_tokens=300,
            )
        raise_if_cancelled("gpt timing_rewrite")
        self._record_usage(response, "timing_rewrite")
        raw = response.choices[0].message.content or ""
        return self._parse_narration_rewrite_response(raw)
