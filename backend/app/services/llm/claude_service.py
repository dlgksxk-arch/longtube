"""Claude (Anthropic) LLM service"""
from datetime import datetime, timedelta, timezone
import json
import math
import re
import anthropic
from app.config import resolve_cut_video_duration
from app.services.llm.base import BaseLLMService
from app.services.llm.script_quality import assert_script_quality
from app.services.cancel_ctx import OperationCancelled, raise_if_cancelled
from app import config


class ClaudeService(BaseLLMService):
    def __init__(self, model_id: str = "claude-sonnet-4-6"):
        self.model_id = model_id
        self.display_name = f"Claude ({model_id})"
        # v1.1.63: UI 에서 바꾼 키가 즉시 반영되도록 config 모듈 속성을 참조.
        # (모듈 레벨에서 값을 import 하면 복사본이라 갱신이 안 보임)
        self._client_factory = anthropic.AsyncAnthropic

        # model_id → Anthropic API model string
        self._model_map = {
            "claude-sonnet-4-6": "claude-sonnet-4-6",
            "claude-opus-4-7": "claude-opus-4-7",
            "claude-opus-4-6": "claude-opus-4-6",
            "claude-haiku-4-5": "claude-haiku-4-5-20251001",
        }

    def _client(self):
        """Create a client in the active event loop."""
        return self._client_factory(api_key=config.ANTHROPIC_API_KEY)

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

    def _enforce_daily_budget(self):
        limit = float(getattr(config, "ANTHROPIC_DAILY_LIMIT_USD", 0.0) or 0.0)
        if limit <= 0:
            return
        try:
            from app.services import spend_ledger
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
            spent = spend_ledger.spend_since("Anthropic", since)
        except Exception:
            return
        if spent >= limit:
            raise RuntimeError(
                "Anthropic daily budget exceeded: "
                f"${spent:.2f} used in the last 24h, limit ${limit:.2f}. "
                "Claude API call was blocked before sending. "
                "Set ANTHROPIC_DAILY_LIMIT_USD=0 only if you intentionally want to disable this guard."
            )

    async def generate_script(self, topic: str, config: dict) -> dict:
        model = self._model_map.get(self.model_id, self.model_id)

        # v1.1.32: target_duration 기반 동적 max_tokens.
        # 컷당 ~180 토큰 (나레이션+image_prompt+메타) + title/description/tags 여유
        # 고정 8192 는 600초 롱폼 대본에서 mid-JSON truncation → 파싱 실패 유발
        target_cuts = self._safe_int(config.get("target_cuts"), 0)
        if target_cuts > 0:
            estimated_cuts = target_cuts
        else:
            target_duration = self._safe_int(config.get("target_duration"), 300)
            estimated_cuts = max(1, math.ceil(target_duration / resolve_cut_video_duration(config)))
        dynamic_max = max(8192, estimated_cuts * 220 + 2048)
        # Claude Sonnet 4.6 상한 안전치
        dynamic_max = min(dynamic_max, 64000)
        raise_if_cancelled("claude generate_script")
        self._enforce_daily_budget()
        async with self._client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=dynamic_max,
                system=self._get_system_prompt(config),
                messages=[{
                    "role": "user",
                    "content": self._build_user_prompt(topic, config),
                }],
                timeout=None,
            )

        raise_if_cancelled("claude generate_script")
        self._record_usage(response, "script", config.get("__project_id"))
        raw = response.content[0].text
        parsed = self._parse_json(raw)
        cuts = parsed.get("cuts") or []
        if len(cuts) != estimated_cuts:
            raise ValueError(
                f"script generation returned {len(cuts)} cuts, expected {estimated_cuts}"
            )
        parsed = self.strengthen_visual_context(parsed, config)
        assert_script_quality(parsed, topic)
        self.assert_script_timing(parsed, config)
        return parsed

    @staticmethod
    def _safe_int(value, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    async def generate_tags(
        self,
        title: str,
        topic: str,
        narration: str = "",
        max_tags: int = 15,
        language: str = "ko",
    ) -> list[str]:
        """Claude 로 YouTube 태그 후보 JSON 생성. 가벼운 단일 호출."""
        model = self._model_map.get(self.model_id, self.model_id)
        prompt = self._build_tag_prompt(title, topic, narration, max_tags, language)
        raise_if_cancelled("claude generate_tags")
        async with self._client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=1024,
                system=(
                    "You are a YouTube SEO assistant. Respond with a single JSON "
                    "object containing a tags array. No prose. Match the language "
                    "requested in the user prompt EXACTLY."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
        raise_if_cancelled("claude generate_tags")
        self._record_usage(response, "tags")
        raw = response.content[0].text if response.content else ""
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
        """Claude 로 title_hook / description / tags 를 한 번에 생성."""
        model = self._model_map.get(self.model_id, self.model_id)
        prompt = self._build_metadata_prompt(
            title, topic, narration, language, max_tags, episode_number
        )
        raise_if_cancelled("claude generate_metadata")
        async with self._client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=2048,
                system=(
                    "You are a YouTube metadata writer. Respond with a single JSON "
                    "object containing title_hook, description, and tags. No prose. "
                    "Match the language requested in the user prompt EXACTLY — "
                    "do not mix languages."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
        raise_if_cancelled("claude generate_metadata")
        self._record_usage(response, "metadata")
        raw = response.content[0].text if response.content else ""
        return self._parse_metadata_response(raw)

    async def generate_thumbnail_image_prompt(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        character_description: str = "",
    ) -> str:
        """Claude 로 YouTube 썸네일용 image generation 프롬프트 한 줄 생성."""
        model = self._model_map.get(self.model_id, self.model_id)
        prompt = self._build_thumbnail_prompt_request(
            title, topic, narration, language, character_description
        )
        try:
            raise_if_cancelled("claude thumbnail_prompt")
            async with self._client() as client:
                response = await client.messages.create(
                    model=model,
                    max_tokens=768,
                    system=(
                        "You are a cinematic image-prompt engineer. Respond with a single "
                        'JSON object of the form {"prompt": "..."} containing one '
                        "English image-generation prompt. No prose outside the JSON."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                )
            raise_if_cancelled("claude thumbnail_prompt")
            self._record_usage(response, "thumbnail_prompt")
        except OperationCancelled:
            raise
        except Exception:
            return self._fallback_thumbnail_prompt(title, topic, language, character_description)
        raw = response.content[0].text if response.content else ""
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
        model = self._model_map.get(self.model_id, self.model_id)
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
        raise_if_cancelled("claude timing_rewrite")
        async with self._client() as client:
            response = await client.messages.create(
                model=model,
                max_tokens=300,
                system=(
                    "You are a precise TTS narration timing editor. "
                    "Return a single JSON object only."
                ),
                messages=[{"role": "user", "content": prompt}],
            )
        raise_if_cancelled("claude timing_rewrite")
        self._record_usage(response, "timing_rewrite")
        raw = response.content[0].text if response.content else ""
        return self._parse_narration_rewrite_response(raw)

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Claude는 JSON 모드가 없으므로 텍스트에서 JSON 추출.

        v1.1.32: mid-stream truncation (max_tokens 초과) 대비해 실패 시
        truncation 복구 (미완결 string/array/object 강제 닫기) 후 재시도.
        """
        candidates: list[str] = []

        # 1) ```json ... ``` 블록
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if m:
            candidates.append(m.group(1))

        # 2) 첫 { 부터 마지막 } 까지
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            candidates.append(m.group(0))

        # 3) 첫 { 부터 끝까지 (truncation 된 경우 닫는 } 가 없을 수 있음)
        idx = text.find("{")
        if idx >= 0:
            candidates.append(text[idx:])

        # 4) 원문 그대로
        candidates.append(text)

        last_err: Exception | None = None
        for cand in candidates:
            try:
                return json.loads(cand)
            except Exception as e:
                last_err = e
            # truncation 복구 시도
            repaired = ClaudeService._repair_truncated_json(cand)
            if repaired is not None:
                try:
                    return json.loads(repaired)
                except Exception as e:
                    last_err = e

        raise last_err if last_err else ValueError("Failed to parse Claude JSON response")

    @staticmethod
    def _repair_truncated_json(text: str) -> str | None:
        """미완결 JSON 을 best-effort 로 닫아본다.

        전략: 구조적으로 안전한 cut point 위치들을 기록하면서 한 번 스캔.
        안전한 cut point 는 다음과 같다 (문자열 바깥):
          - ``{`` 또는 ``[`` 직후 (빈 컨테이너)
          - ``}`` 또는 ``]`` 직후 (해당 컨테이너의 값이 완결됨)
          - 문자열 ``"`` 닫힘 직후 — 단 이 경우 그 문자열이 key 가 아닌 value 여야 함.
            (직전의 구조적 문맥이 ``: `` 뒤, 또는 ``[`` / ``,`` 뒤 배열 요소)

        마지막 안전 지점까지 자른 뒤 열린 괄호들을 역순으로 닫는다.
        """
        if not text:
            return None
        s = text.strip()
        start = s.find("{")
        if start < 0:
            return None
        s = s[start:]

        in_str = False
        escape = False
        stack: list[str] = []  # "{" / "["
        # object 컨텍스트에서 "다음 문자열 닫힘은 key" vs "value" 추적
        # object 안에서: 처음/','뒤 → key, ':' 뒤 → value
        expecting_value: list[bool] = []  # stack 와 평행; True 면 value
        # 루트는 object 라 가정하고 초기 상태 설정은 '{' 만남 시 push 됨

        safe_cut = 0  # exclusive — 여기까지 잘라서 닫으면 valid
        safe_stack_depth = 0
        safe_stack: list[str] = []

        def mark_safe(pos: int):
            nonlocal safe_cut, safe_stack
            safe_cut = pos
            safe_stack = list(stack)

        last_struct = None  # 'open' | 'close' | 'colon' | 'comma' | 'str' | None

        for i, ch in enumerate(s):
            if in_str:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_str = False
                    # 방금 닫힌 문자열이 value 였는지 판단
                    if stack and stack[-1] == "[":
                        # 배열 요소 = value
                        mark_safe(i + 1)
                    elif stack and stack[-1] == "{":
                        # object: expecting_value[-1] 가 True 면 value
                        if expecting_value and expecting_value[-1]:
                            mark_safe(i + 1)
                        # key 인 경우 safe 아님 (다음에 ':value' 필요)
                    last_struct = "str"
                continue
            if ch == '"':
                in_str = True
                continue
            if ch in "{[":
                stack.append(ch)
                expecting_value.append(False)  # object 안 시작은 key 기대
                mark_safe(i + 1)
                last_struct = "open"
                continue
            if ch in "}]":
                if stack:
                    stack.pop()
                    if expecting_value:
                        expecting_value.pop()
                mark_safe(i + 1)
                last_struct = "close"
                continue
            if ch == ":":
                # object 에서 key 다음 → 이제 value 기대
                if expecting_value:
                    expecting_value[-1] = True
                last_struct = "colon"
                continue
            if ch == ",":
                # object: 다음은 다시 key 기대 / array: 다음 요소
                if expecting_value:
                    expecting_value[-1] = False
                last_struct = "comma"
                continue
            if ch in " \t\r\n":
                continue
            # 숫자/true/false/null primitive 시작 — 완결 시점을 알 수 없어 여기서는 safe 마킹 안 함
            # 하지만 primitive 뒤에 오는 구조 문자 (}, ], ,) 가 이미 mark_safe 를 호출하므로 OK
            last_struct = "primitive"
            continue

        if safe_cut <= 0:
            return None

        cut = s[:safe_cut]

        # trailing comma/colon 제거 (안전 컷이 정확하면 없어야 하지만 방어)
        cut = cut.rstrip()
        while cut and cut[-1] in ",:":
            cut = cut[:-1].rstrip()

        # safe_stack 역순으로 닫기
        close_map = {"{": "}", "[": "]"}
        for opener in reversed(safe_stack):
            cut += close_map[opener]

        return cut
