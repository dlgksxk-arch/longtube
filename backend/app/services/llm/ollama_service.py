"""Ollama-backed LLM service for local script-studio experiments."""
from __future__ import annotations

import json
import re
from typing import Any
from pathlib import Path

import httpx

from app.services.llm.base import BaseLLMService
from app.services.llm.script_quality import assert_script_quality, assert_story_plan


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
OLLAMA_NUM_CTX = 65536
OLLAMA_SCENE_BLOCK_NUM_CTX = 8192
OLLAMA_FULL_SCRIPT_NUM_CTX = 65536
SCENE_BLOCK_MAX_REGENERATIONS = 2
SCENE_BLOCK_GEMMA_REPAIR_ATTEMPTS = 3
SCENE_BLOCK_NUM_PREDICT_MIN = 1800
SCENE_BLOCK_NUM_PREDICT_PER_CUT = 520
SCENE_BLOCK_NUM_PREDICT_MAX = 3200
SCRIPT_BLOCK_FORBIDDEN_TERMS = (
    "충격",
    "소름",
    "대박",
    "미쳤다",
    "레전드",
    "알아보자",
    "역사 이야기",
    "진짜 이유",
)


class OllamaService(BaseLLMService):
    """Minimal local LLM adapter.

    This is intentionally used by Script Studio first. The existing production
    providers remain unchanged unless a caller explicitly selects a local model id.
    """

    def __init__(self, model_id: str = "qwen3:32b"):
        self.model_id = model_id
        self.model_name = model_id.split(":", 1)[1] if model_id.startswith("ollama:") else model_id
        self.display_name = self.model_name

    async def _chat_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        num_predict: int,
        num_ctx: int | None = None,
        result_dir: str | None = None,
        raw_label: str | None = None,
        allow_nested_json: bool = True,
        expected_cuts: int | None = None,
    ) -> dict:
        payload = {
            "model": self.model_name,
            "stream": False,
            "format": "json",
            "think": True,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        system
                        + "\n\nReturn JSON only. Do not include reasoning, markdown, or commentary."
                    ),
                },
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": int(num_ctx or OLLAMA_NUM_CTX),
                "num_predict": num_predict,
                "repeat_penalty": 1.18,
                "repeat_last_n": 2048,
                "top_p": 0.9,
            },
        }
        timeout = httpx.Timeout(None, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
        data = response.json()
        raw = str(((data.get("message") or {}).get("content")) or "").strip()
        self._save_raw_text(result_dir, raw_label, raw)
        if not raw:
            raise RuntimeError(f"Ollama response was empty: {self.model_name}")
        parsed = self._parse_json_with_local_repair(raw, allow_nested_json=allow_nested_json)
        if parsed is None:
            raise RuntimeError(f"Ollama response was not valid JSON: {self.model_name}")
        if expected_cuts is not None:
            cuts = self._scene_block_cuts_payload(parsed)
            actual = len(cuts) if isinstance(cuts, list) else 0
            if actual != expected_cuts:
                raise RuntimeError(
                    f"Ollama response returned {actual} cuts, expected {expected_cuts}: {self.model_name}"
                )
        return parsed

    async def _chat_text(
        self,
        *,
        system: str,
        user: str,
        temperature: float,
        num_predict: int,
        num_ctx: int | None = None,
        result_dir: str | None = None,
        raw_label: str | None = None,
        think: bool = False,
    ) -> str:
        payload = {
            "model": self.model_name,
            "stream": False,
            "think": bool(think),
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": temperature,
                "num_ctx": int(num_ctx or OLLAMA_NUM_CTX),
                "num_predict": num_predict,
                "repeat_penalty": 1.18,
                "repeat_last_n": 2048,
                "top_p": 0.9,
            },
        }
        timeout = httpx.Timeout(None, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
        data = response.json()
        raw = str(((data.get("message") or {}).get("content")) or "").strip()
        self._save_raw_text(result_dir, raw_label, raw)
        if not raw:
            raise RuntimeError(f"Ollama response was empty: {self.model_name}")
        return raw

    @staticmethod
    def _save_raw_text(result_dir: str | None, label: str | None, raw: str) -> None:
        if not result_dir or not label:
            return
        try:
            raw_dir = Path(result_dir) / "llm_raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in label).strip("_") or "ollama_raw"
            (raw_dir / f"{safe}.txt").write_text(raw or "", encoding="utf-8")
        except Exception:
            pass

    @classmethod
    def _parse_json_with_local_repair(cls, raw: str, *, allow_nested_json: bool = True) -> dict | None:
        raw = str(raw or "").strip()
        if not raw:
            return None
        candidates = cls._json_repair_candidates(raw, allow_nested_json=allow_nested_json)
        for candidate in candidates:
            parsed = cls._loads_jsonish(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"cuts": parsed}
        return None

    @classmethod
    def _json_repair_candidates(cls, raw: str, *, allow_nested_json: bool = True) -> list[str]:
        candidates: list[str] = []

        def add(value: str | None) -> None:
            text = str(value or "").strip()
            if text and text not in candidates:
                candidates.append(text)

        add(raw)
        for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE):
            add(match.group(1))
        decoder = json.JSONDecoder()
        if allow_nested_json:
            for idx, ch in enumerate(raw):
                if ch not in "{[":
                    continue
                try:
                    _, end = decoder.raw_decode(raw[idx:])
                    add(raw[idx:idx + end])
                except Exception:
                    pass
        else:
            first_json = min([idx for idx in (raw.find("{"), raw.find("[")) if idx >= 0], default=-1)
            if first_json >= 0:
                try:
                    _, end = decoder.raw_decode(raw[first_json:])
                    add(raw[first_json:first_json + end])
                except Exception:
                    pass
        first_obj = raw.find("{")
        last_obj = raw.rfind("}")
        if first_obj >= 0:
            add(raw[first_obj:last_obj + 1] if last_obj > first_obj else raw[first_obj:])
        first_arr = raw.find("[")
        last_arr = raw.rfind("]")
        if first_arr >= 0:
            add(raw[first_arr:last_arr + 1] if last_arr > first_arr else raw[first_arr:])
        cuts_key = re.search(r'"cuts"\s*:', raw)
        if cuts_key:
            add("{" + raw[cuts_key.start():].strip().strip(",") + "}")
        return candidates

    @classmethod
    def _loads_jsonish(cls, text: str) -> Any:
        text = cls._clean_jsonish_text(text)
        for candidate in (text, cls._balance_jsonish(text)):
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except Exception:
                pass
            try:
                import ast

                value = ast.literal_eval(candidate)
                if isinstance(value, (dict, list)):
                    return value
            except Exception:
                pass
        return None

    @staticmethod
    def _clean_jsonish_text(text: str) -> str:
        out = str(text or "").strip()
        out = out.replace("\ufeff", "")
        out = out.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
        out = re.sub(r"^\s*json\s*", "", out, flags=re.IGNORECASE)
        out = re.sub(r",\s*([}\]])", r"\1", out)
        return out.strip()

    @staticmethod
    def _balance_jsonish(text: str) -> str:
        stack: list[str] = []
        in_string = False
        quote = ""
        escaped = False
        for ch in text:
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    in_string = False
                continue
            if ch in {"'", '"'}:
                in_string = True
                quote = ch
            elif ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
        return text + "".join(reversed(stack))

    def _emit_script_progress(
        self,
        config: dict,
        *,
        completed: int,
        total: int,
        message: str,
        status: str = "running",
        block: dict | None = None,
    ) -> None:
        callback = (config or {}).get("script_progress_callback") or (config or {}).get("progress_callback")
        if not callable(callback):
            return
        try:
            event = {
                "stage": "script",
                "status": status,
                "completed": completed,
                "total": total,
                "progress_pct": round((completed / max(total, 1)) * 100, 1),
                "message": message,
                "model": self.model_id,
            }
            if isinstance(block, dict):
                event["block"] = block
            callback(event)
        except Exception:
            pass

    def _save_partial_script_progress(
        self,
        config: dict,
        story_plan: dict,
        cuts: list[dict[str, Any]],
        *,
        completed_blocks: int,
        total_blocks: int,
    ) -> None:
        result_dir = str((config or {}).get("result_dir") or "").strip()
        if not result_dir:
            return
        try:
            from pathlib import Path

            metadata = self._script_metadata_from_story_plan(
                str((config or {}).get("topic") or ""),
                config,
                story_plan,
            )
            partial = {
                "script_version": "3.1",
                **metadata,
                "partial": True,
                "completed_scene_blocks": completed_blocks,
                "total_scene_blocks": total_blocks,
                "visual_world": story_plan.get("visual_world") or {},
                "story_core": story_plan.get("story_core") or {},
                "fact_ledger": story_plan.get("fact_ledger") or {},
                "visual_plan": story_plan.get("visual_plan") or {},
                "scene_blocks": self._scene_block_ranges(story_plan)[:completed_blocks],
                "cuts": cuts,
            }
            Path(result_dir).mkdir(parents=True, exist_ok=True)
            (Path(result_dir) / "partial_script.json").write_text(
                json.dumps(partial, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _save_partial_text_blocks_progress(
        self,
        config: dict,
        story_plan: dict,
        text_blocks: list[dict[str, Any]],
        *,
        completed_blocks: int,
        total_blocks: int,
    ) -> None:
        result_dir = str((config or {}).get("result_dir") or "").strip()
        if not result_dir:
            return
        try:
            from pathlib import Path

            metadata = self._script_metadata_from_story_plan(
                str((config or {}).get("topic") or ""),
                config,
                story_plan,
            )
            partial = {
                "script_version": "3.1",
                **metadata,
                "partial": True,
                "text_only": True,
                "completed_scene_blocks": completed_blocks,
                "total_scene_blocks": total_blocks,
                "visual_world": story_plan.get("visual_world") or {},
                "story_core": story_plan.get("story_core") or {},
                "fact_ledger": story_plan.get("fact_ledger") or {},
                "visual_plan": story_plan.get("visual_plan") or {},
                "scene_blocks": self._scene_block_ranges(story_plan)[:completed_blocks],
                "script_text_blocks": text_blocks,
            }
            Path(result_dir).mkdir(parents=True, exist_ok=True)
            (Path(result_dir) / "partial_script.json").write_text(
                json.dumps(partial, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _raise_if_cancelled(self, config: dict) -> None:
        checker = (config or {}).get("script_cancel_checker")
        if callable(checker):
            checker()

    def _configured_forbidden_terms(self, config: dict) -> list[str]:
        raw = str((config or {}).get("content_forbidden") or (config or {}).get("content_constraints") or "")
        terms = [
            term.strip(" -•·\t")
            for term in re.split(r"[\n,/·]+", raw)
            if term.strip(" -•·\t")
        ]
        return [*SCRIPT_BLOCK_FORBIDDEN_TERMS, *terms]

    def _narration_words(self, text: str) -> set[str]:
        ignored = {
            "그리고",
            "하지만",
            "그런데",
            "그래서",
            "이제",
            "바로",
            "당시",
            "이후",
            "이번",
            "영상",
        }
        words = {
            word.lower()
            for word in re.findall(r"[A-Za-z0-9가-힣]{2,}", str(text or ""))
            if len(word.strip()) >= 2
        }
        return {word for word in words if word not in ignored}

    def _sentence_ending(self, text: str) -> str:
        value = re.sub(r"\s+", " ", str(text or "").strip())
        value = re.sub(r"[\"'“”‘’\]\)]*$", "", value)
        value = re.sub(r"[.!?。！？…]+$", "", value).strip()
        endings = (
            "었습니다",
            "했습니다",
            "였습니다",
            "입니다",
            "습니다",
            "는데요",
            "거든요",
            "였어요",
            "했어요",
            "어요",
            "였죠",
            "했죠",
            "이죠",
            "고요",
            "니다",
            "죠",
            "요",
            "다",
        )
        for ending in endings:
            if value.endswith(ending):
                return ending
        tail = value.split(" ")[-1] if value else ""
        return tail[-4:] if len(tail) > 4 else tail

    @staticmethod
    def _ending_group(ending: str) -> str:
        ending = str(ending or "")
        if ending in {"죠", "했죠", "였죠", "이죠"}:
            return "죠"
        if ending in {"요", "어요", "했어요", "였어요", "는데요", "거든요", "고요"}:
            return "요"
        if ending in {"습니다", "입니다", "했습니다", "였습니다", "었습니다", "니다"}:
            return "습니다"
        return ending

    @staticmethod
    def _scene_block_num_predict(expected_count: int) -> int:
        return min(
            SCENE_BLOCK_NUM_PREDICT_MAX,
            max(SCENE_BLOCK_NUM_PREDICT_MIN, int(expected_count or 5) * SCENE_BLOCK_NUM_PREDICT_PER_CUT),
        )

    @staticmethod
    def _scene_block_text_num_predict(expected_count: int) -> int:
        return min(6400, max(3200, int(expected_count or 10) * 520))

    @staticmethod
    def _full_script_text_num_predict(expected_count: int) -> int:
        return min(64000, max(16000, int(expected_count or 150) * 380))

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        value = str(text or "").strip()
        fenced = re.search(r"```(?:text|txt)?\s*([\s\S]*?)\s*```", value, flags=re.IGNORECASE)
        return fenced.group(1).strip() if fenced else value

    @staticmethod
    def _clean_generated_line(text: str) -> str:
        value = re.sub(r"\s+", " ", str(text or "").strip())
        value = value.strip(" -•\t")
        value = value.strip("\"'“”‘’")
        return value

    @staticmethod
    def _trim_words(text: str, max_words: int) -> str:
        words = re.findall(r"[A-Za-z0-9가-힣'’:-]+", str(text or ""))
        if len(words) <= max_words:
            return str(text or "").strip()
        return " ".join(words[:max_words])

    @staticmethod
    def _block_scope_summary(block: dict | None) -> dict[str, Any]:
        if not isinstance(block, dict):
            return {}
        try:
            block_id = int(block.get("block_id") or 0)
        except (TypeError, ValueError):
            block_id = 0
        hook_or_focus_key = "hook_question" if block_id == 1 else "focus"
        return {
            "block_id": block.get("block_id"),
            "cut_range": block.get("cut_range"),
            hook_or_focus_key: block.get("mini_question"),
            "new_information": block.get("new_information"),
            "tension": block.get("tension"),
            "turn": block.get("turn"),
            "must_include": block.get("must_include") or [],
            "must_avoid": block.get("must_avoid") or [],
            "block_goal": block.get("block_goal"),
            "key_facts": block.get("key_facts") or [],
            "character_focus": block.get("character_focus") or [],
            "character_introductions": block.get("character_introductions") or [],
            "continuity_from_previous": block.get("continuity_from_previous"),
            "required_script_moves": block.get("required_script_moves") or [],
            "turn_to_next": block.get("turn_to_next"),
        }

    @staticmethod
    def _cut_history_summary(previous_cuts: list[dict[str, Any]] | None, *, limit: int = 12) -> list[str]:
        history: list[str] = []
        for cut in (previous_cuts or [])[-limit:]:
            if not isinstance(cut, dict):
                continue
            narration = re.sub(r"\s+", " ", str(cut.get("narration") or "").strip())
            if narration:
                history.append(narration)
        return history

    @staticmethod
    def _text_similarity(left: str, right: str) -> float:
        left_words = set(re.findall(r"[A-Za-z가-힣0-9]{2,}", str(left or "").lower()))
        right_words = set(re.findall(r"[A-Za-z가-힣0-9]{2,}", str(right or "").lower()))
        if not left_words or not right_words:
            return 0.0
        return len(left_words & right_words) / max(min(len(left_words), len(right_words)), 1)

    def _scene_block_text_context(
        self,
        *,
        story_plan: dict,
        scene_block: dict,
        previous_cuts: list[dict[str, Any]] | None,
        next_block: dict | None,
        future_blocks: list[dict[str, Any]] | None = None,
        ) -> dict[str, Any]:
        compact = self._compact_story_plan_for_scene_block(story_plan, scene_block)
        plan = story_plan if isinstance(story_plan, dict) else {}
        fact_ledger = compact.get("fact_ledger") if isinstance(compact.get("fact_ledger"), dict) else {}
        future_scope = []
        for item in future_blocks or []:
            if isinstance(item, dict):
                future_scope.append(self._block_scope_summary(item))
        return {
            "fixed_story_design": {
                "story_core": plan.get("story_core") or {},
                "character_map": plan.get("character_map") or [],
                "causality_chain": plan.get("causality_chain") or [],
                "fact_ledger": plan.get("fact_ledger") or {},
                "visual_plan": plan.get("visual_plan") or {},
                "visual_world": plan.get("visual_world") or {},
            },
            "current_block_only": self._block_scope_summary(scene_block),
            "forbidden_claims": (fact_ledger.get("forbidden_claims") or [])[:8],
            "already_said_do_not_repeat": self._cut_history_summary(previous_cuts, limit=12),
            "next_block_preview_only": self._block_scope_summary(next_block),
            "future_blocks_do_not_explain_yet": future_scope,
        }

    def _build_scene_block_text_system_prompt(self, config: dict) -> str:
        cfg = config or {}
        language = self._language_name(str(cfg.get("language") or "ko"))
        limits = self._calc_narration_limits(cfg)
        target_range = str(limits.get("target_range") or "")
        return (
            "당신은 유튜브 대사와 이미지 프롬프트 블럭 작성기입니다.\n"
            "JSON, 설명, 마크다운, 주석은 금지입니다.\n"
            "반드시 요청된 줄 수만 번호 목록으로 반환하세요.\n"
            "형식은 `1. 한국어 대사 || English image prompt` 한 줄씩입니다.\n\n"
            f"내레이션 언어: {language}.\n"
            f"각 줄 목표 길이: {target_range} 공백 포함 글자.\n"
            "현재 블럭의 새 정보만 요청된 컷 수로 확장하세요. 전체 결론, 이후 블럭 사건, 이미 말한 문장은 반복하지 마세요.\n"
            "보고서 문체가 아니라 사람이 말하는 영상 대사여야 합니다.\n"
            "문장 끝은 한 블럭 안에서 자연스럽게 섞으세요: `습니다/입니다`, `요`, `죠` 계열을 섞고, 10컷 블럭에서 `죠`는 최대 3컷만 씁니다.\n"
            "금지 문서체: `균열을 드러냈다`, `화친을 건의했다`, `운명을 바꿨다`, `남하의 길을 택했다`, `점에서 시작된다`, `의미를 가진다`, `단서가 된다`.\n"
            "구분자 `||` 왼쪽은 한국어 대사, 오른쪽은 영어 이미지 프롬프트입니다.\n"
            "이미지 프롬프트는 45~70단어로 쓰고, 내레이션 원문을 번역/복사하지 마세요.\n"
            "이미지 프롬프트에는 시대에 맞는 인물, 장소, 소품, 행동, 촬영 구도를 구체적으로 넣으세요.\n"
            "이미지 프롬프트 금지어: fog, mist, haze, text, letters, numbers, logos, readable signs.\n"
            "stormy sky, sunset, silhouette, generic palace hall 같은 재탕 구도는 블럭이 직접 요구할 때만 쓰세요.\n"
            "새 사실, 실제 대사, 확정할 수 없는 날짜/동기/경로를 만들지 마세요."
        )

    def _build_scene_block_text_user_prompt(
        self,
        *,
        topic: str,
        config: dict,
        story_plan: dict,
        scene_block: dict,
        previous_cuts: list[dict[str, Any]] | None,
        next_block: dict | None,
        future_blocks: list[dict[str, Any]] | None = None,
        start: int,
        end: int,
    ) -> str:
        context = self._scene_block_text_context(
            story_plan=story_plan,
            scene_block=scene_block,
            previous_cuts=previous_cuts,
            next_block=next_block,
            future_blocks=future_blocks,
        )
        try:
            block_id = int(scene_block.get("block_id") or 0) if isinstance(scene_block, dict) else 0
        except (TypeError, ValueError):
            block_id = 0
        special_rules = ""
        if block_id == 1:
            special_rules = (
                "Block 1 전용 규칙:\n"
                f"- {start}번 컷 첫 문장은 반드시 질문으로 시작하세요. `왜`만 반복하지 말고 `어떻게`, `정말`, `무엇이`, `왜 하필`, `그 선택은 왜` 같은 다양한 질문 패턴 중 하나를 씁니다.\n"
                "- 1블럭 전체는 영상 전체를 아우르는 가장 충격적인 사건을 먼저 말합니다. 평범한 배경 설명, 시대 소개, 요약으로 시작하지 마세요.\n"
                "- 나머지 컷은 그 사건이 왜 충격적인지, 왜 그럴 수밖에 없었는지, 어떻게 그런 일이 가능했는지에 대한 압박과 의문을 키웁니다.\n"
                "- 결론을 완전히 말하지 말고, Block 2에서 해답을 찾도록 마지막 줄을 넘기세요.\n\n"
            )
        elif block_id == 2:
            special_rules = (
                "Block 2 전용 규칙:\n"
                "- Block 1의 충격적인 사건에 대한 해답을 찾아가는 도입으로 쓰세요.\n"
                "- 답을 은근히 흘리되 결론을 다 말하지 말고, 본편으로 호흡을 끌고 가세요.\n"
                "- `이제부터 그 이유를 따라가 보겠습니다`, `오늘은 그 이야기를 해보죠`, `함께 확인해볼까요` 같은 본편 진입 어투를 참고하되 그대로 복붙하지 말고 자연스럽게 변형하세요.\n"
                "- 새로운 큰 사건을 앞당기지 말고, Block 1의 질문을 받아 본론으로 연결하세요.\n\n"
            )
        return (
            f"주제: {topic}\n"
            f"컷 범위: {start}-{end}\n"
            f"정확히 {end - start + 1}줄만 작성하세요.\n\n"
            f"스토리 기준:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            f"{special_rules}"
            "규칙:\n"
            "- fixed_story_design은 매 블럭의 고정 기준입니다. 중심축, 중심 질문/답변, 인물 설계, 사건 인과, 팩트 장부를 벗어나지 마세요.\n"
            "- current_block_only의 훅 질문 또는 핵심 진행, 새 정보, 압박, 전환만 사용하세요.\n"
            "- 질문형 대사는 Block 1의 첫 문장에만 씁니다. Block 2부터는 질문으로 시작하지 마세요.\n"
            "- current_block_only.character_introductions가 있으면, 지정된 cut_number는 반드시 해당 블럭의 2번째 컷이며 그 줄은 해당 인물/집단의 첫 출현과 정체를 설명하세요.\n"
            "- character_introductions가 있는 블럭의 3번째, 4번째, 5번째 컷은 같은 인물/집단의 직책, 이해관계, 이번 사건에서의 기능을 이어서 설명하세요.\n"
            "- character_introductions가 없는 인물 설명은 새로 만들지 말고, 첫 등장 이후의 인물은 사건 행동으로만 진행하세요.\n"
            "- already_said_do_not_repeat의 대사와 같은 주장/문장 구조를 반복하지 마세요.\n"
            "- future_blocks_do_not_explain_yet 내용은 아직 설명하지 마세요. 필요하면 마지막 줄에서 짧게 예고만 하세요.\n"
            "- 각 줄은 서로 다른 기능이어야 합니다: 상황, 인물/집단, 압박, 구체 물증/행동, 선택, 반전, 비용, 다음 블럭 연결.\n"
            "- 이미지 프롬프트도 모든 줄에서 다른 피사체와 구도를 쓰세요.\n\n"
            "출력은 번호 목록만 허용합니다. 각 줄은 반드시 `대사 || English image prompt` 형식이어야 합니다. JSON은 쓰지 마세요."
        )

    def _build_all_scene_blocks_text_system_prompt(self, config: dict) -> str:
        cfg = config or {}
        language = self._language_name(str(cfg.get("language") or "ko"))
        limits = self._calc_narration_limits(cfg)
        target_range = str(limits.get("target_range") or "")
        return (
            "당신은 유튜브 15블럭 대본 작성기입니다.\n"
            "JSON, 설명, 마크다운, 주석은 금지입니다.\n"
            "반드시 BLOCK 헤더와 번호 목록만 반환하세요.\n"
            "출력 형식:\n"
            "BLOCK 1 | 1-10\n"
            "1. 한국어 대사 || English image prompt\n"
            "2. 한국어 대사 || English image prompt\n"
            "3. 한국어 대사 || English image prompt\n"
            "4. 한국어 대사 || English image prompt\n"
            "5. 한국어 대사 || English image prompt\n"
            "6. 한국어 대사 || English image prompt\n"
            "7. 한국어 대사 || English image prompt\n"
            "8. 한국어 대사 || English image prompt\n"
            "9. 한국어 대사 || English image prompt\n"
            "10. 한국어 대사 || English image prompt\n\n"
            f"내레이션 언어: {language}.\n"
            f"각 대사 목표 길이: {target_range} 공백 포함 글자.\n"
            "각 블럭은 정확히 10줄입니다. 전체 블럭 수와 전체 컷 수를 맞추세요.\n"
            "각 블럭의 new_information만 확장하고, 다른 블럭의 결론을 앞당기지 마세요.\n"
            "이전 블럭과 같은 주장, 같은 첫 문장 구조, 같은 이미지 피사체를 반복하지 마세요.\n"
            "문장 끝은 자연스럽게 섞으세요: `습니다/입니다`, `요`, `죠` 계열을 섞고, 한 블럭 안에서 `죠`는 최대 2컷만 씁니다.\n"
            "이미지 프롬프트는 45~70단어로 쓰고, 시대에 맞는 인물, 장소, 소품, 행동, 촬영 구도를 구체적으로 넣으세요.\n"
            "이미지 프롬프트 금지어: fog, mist, haze, text, letters, numbers, logos, readable signs.\n"
            "새 사실, 실제 대사, 확정할 수 없는 날짜/동기/경로를 만들지 마세요."
        )

    def _build_all_scene_blocks_text_user_prompt(
        self,
        *,
        topic: str,
        config: dict,
        story_plan: dict,
        blocks: list[dict],
        previous_cuts: list[dict[str, Any]] | None,
    ) -> str:
        block_payload = [self._block_scope_summary(block) for block in blocks if isinstance(block, dict)]
        context = {
            "topic": topic,
            "story_core": (story_plan.get("story_core") or {}) if isinstance(story_plan, dict) else {},
            "fact_ledger": (story_plan.get("fact_ledger") or {}) if isinstance(story_plan, dict) else {},
            "visual_world": (story_plan.get("visual_world") or {}) if isinstance(story_plan, dict) else {},
            "previous_completed_narration": self._cut_history_summary(previous_cuts, limit=20),
            "blocks_to_write": block_payload,
        }
        expected_cuts = 0
        for block in blocks:
            parsed = self._parse_range_text(block.get("cut_range") if isinstance(block, dict) else "")
            if parsed:
                expected_cuts += parsed[1] - parsed[0] + 1
        return (
            f"아래 {len(block_payload)}개 블럭 전체를 한 번에 작성하세요.\n"
            f"총 {expected_cuts}컷입니다. 각 블럭은 정확히 10컷입니다.\n\n"
            f"설계 JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            "규칙:\n"
            "- 출력은 BLOCK 헤더와 번호 목록만 허용합니다.\n"
            "- 각 줄은 반드시 `대사 || English image prompt` 형식입니다.\n"
            "- 블럭마다 서로 다른 새 정보와 시각 구도를 사용하세요.\n"
            "- BLOCK 1은 전체 내용을 아우르는 충격적 사건을 질문으로 시작하고, 왜 충격적인지/왜 그럴 수밖에 없었는지/어떻게 가능했는지 의문을 키우세요.\n"
            "- BLOCK 2는 BLOCK 1의 충격적인 사건에 대한 해답을 찾아가는 도입입니다. 질문으로 시작하지 말고, 답을 은근히 흘리되 결론을 다 말하지 말고 본편 진입 어투로 이어가세요.\n"
            "- scene_blocks 설계에 없는 결론, 목적지, 인물 설명을 앞당기지 마세요.\n"
            "- 구버전 구조 키는 쓰지 마세요."
        )

    def _parse_scene_block_text_response(
        self,
        raw: str,
        *,
        block: dict,
        story_plan: dict,
        start: int,
        end: int,
    ) -> list[dict[str, Any]]:
        text = self._strip_code_fences(raw)
        expected_count = end - start + 1
        numbered_lines = [
            line.strip()
            for line in re.split(r"[\r\n]+", text)
            if re.match(r"^\s*(?:\d+[\).\:-]|[-•])\s+", line.strip())
        ]
        if numbered_lines:
            cuts: list[dict[str, Any]] = []
            for idx, line in enumerate(numbered_lines):
                body = re.sub(r"^\s*(?:\d+[\).\:-]|[-•])\s+", "", line).strip()
                parts = re.split(r"\s*\|\|\s*|\s+--\s+|\s+//\s+", body, maxsplit=1)
                if len(parts) != 2:
                    continue
                narration = self._clean_generated_line(parts[0])
                image_prompt = self._clean_generated_line(parts[1])
                image_prompt = re.sub(r"^(?:IMAGE_PROMPT|IMAGE PROMPT|이미지\s*프롬프트|PROMPT)\s*:\s*", "", image_prompt, flags=re.IGNORECASE).strip()
                if narration and image_prompt:
                    cuts.append(
                        self._build_scene_block_cut_from_text(
                            cut_number=start + idx,
                            narration=narration,
                            image_prompt=image_prompt,
                            block=block,
                            story_plan=story_plan,
                        )
                    )
            if len(cuts) >= expected_count:
                return cuts[:expected_count]

        marker_re = re.compile(r"(?im)^\s*(?:CUT|컷)\s*[:#.-]?\s*(\d+)\s*$")
        markers = list(marker_re.finditer(text))
        segments: list[tuple[int, str]] = []
        for idx, marker in enumerate(markers):
            cut_number = int(marker.group(1))
            body_start = marker.end()
            body_end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
            segments.append((cut_number, text[body_start:body_end]))
        if not segments:
            pairs = re.findall(
                r"(?is)(?:NARRATION|나레이션|대사)\s*:\s*(.*?)\s*(?:IMAGE_PROMPT|IMAGE PROMPT|이미지\s*프롬프트|PROMPT)\s*:\s*(.*?)(?=\n\s*(?:NARRATION|나레이션|대사)\s*:|\Z)",
                text,
            )
            segments = [(start + idx, f"NARRATION: {n}\nIMAGE_PROMPT: {p}") for idx, (n, p) in enumerate(pairs)]
        cuts: list[dict[str, Any]] = []
        for fallback_idx, (cut_number, body) in enumerate(segments):
            if not (start <= cut_number <= end):
                cut_number = start + fallback_idx
            narration = self._extract_labeled_text(
                body,
                labels=("NARRATION", "나레이션", "대사"),
                stop_labels=("IMAGE_PROMPT", "IMAGE PROMPT", "이미지 프롬프트", "PROMPT", "VISUAL", "장면"),
            )
            image_prompt = self._extract_labeled_text(
                body,
                labels=("IMAGE_PROMPT", "IMAGE PROMPT", "이미지 프롬프트", "PROMPT", "VISUAL", "장면"),
                stop_labels=("NARRATION", "나레이션", "대사"),
            )
            narration = self._clean_generated_line(narration)
            image_prompt = self._clean_generated_line(image_prompt)
            if narration and image_prompt:
                cuts.append(
                    self._build_scene_block_cut_from_text(
                        cut_number=cut_number,
                        narration=narration,
                        image_prompt=image_prompt,
                        block=block,
                        story_plan=story_plan,
                    )
                )
        cuts.sort(key=lambda item: int(item.get("cut_number") or 0))
        if len(cuts) >= expected_count:
            return cuts[:expected_count]
        if len(cuts) != expected_count:
            raise ValueError(f"scene_block text response returned {len(cuts)} cuts, expected {expected_count}")
        return cuts

    def _parse_all_scene_blocks_text_response(
        self,
        raw: str,
        *,
        blocks: list[dict],
        story_plan: dict,
    ) -> dict[int, list[dict[str, Any]]]:
        text = self._strip_code_fences(raw)
        block_by_id: dict[int, dict] = {}
        for block in blocks:
            if not isinstance(block, dict):
                continue
            try:
                block_by_id[int(block.get("block_id") or 0)] = block
            except (TypeError, ValueError):
                continue

        parsed_by_block: dict[int, list[dict[str, Any]]] = {}
        header_re = re.compile(r"(?im)^\s*(?:BLOCK|Block|블럭)\s*#?\s*(\d+)\b[^\n]*$")
        headers = list(header_re.finditer(text))
        if headers:
            for idx, header in enumerate(headers):
                block_id = int(header.group(1))
                block = block_by_id.get(block_id)
                if not block:
                    continue
                parsed_range = self._parse_range_text(block.get("cut_range"))
                if parsed_range is None:
                    continue
                start, end = parsed_range
                body_start = header.end()
                body_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
                parsed_by_block[block_id] = self._parse_scene_block_text_response(
                    text[body_start:body_end],
                    block=block,
                    story_plan=story_plan,
                    start=start,
                    end=end,
                )
        else:
            numbered_lines = [
                line.strip()
                for line in re.split(r"[\r\n]+", text)
                if re.match(r"^\s*(?:\d+[\).\:-]|[-•])\s+", line.strip())
            ]
            line_index = 0
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                parsed_range = self._parse_range_text(block.get("cut_range"))
                if parsed_range is None:
                    continue
                start, end = parsed_range
                expected_count = end - start + 1
                chunk = numbered_lines[line_index : line_index + expected_count]
                line_index += expected_count
                if len(chunk) == expected_count:
                    block_id = int(block.get("block_id") or 0)
                    parsed_by_block[block_id] = self._parse_scene_block_text_response(
                        "\n".join(chunk),
                        block=block,
                        story_plan=story_plan,
                        start=start,
                        end=end,
                    )

        missing = []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            block_id = int(block.get("block_id") or 0)
            if block_id and block_id not in parsed_by_block:
                missing.append(str(block_id))
        if missing:
            raise ValueError("full script text response missing blocks: " + ", ".join(missing[:12]))
        return parsed_by_block

    @staticmethod
    def _extract_labeled_text(body: str, *, labels: tuple[str, ...], stop_labels: tuple[str, ...]) -> str:
        label_alt = "|".join(re.escape(label) for label in labels)
        stop_alt = "|".join(re.escape(label) for label in stop_labels)
        match = re.search(
            rf"(?is)(?:^|\n)\s*(?:{label_alt})\s*:\s*(.*?)(?=\n\s*(?:{stop_alt})\s*:|\Z)",
            str(body or ""),
        )
        return match.group(1).strip() if match else ""

    def _build_scene_block_cut_from_text(
        self,
        *,
        cut_number: int,
        narration: str,
        image_prompt: str,
        block: dict,
        story_plan: dict,
    ) -> dict[str, Any]:
        visual_world = story_plan.get("visual_world") if isinstance(story_plan, dict) else {}
        if not isinstance(visual_world, dict):
            visual_world = {}
        prompt = self._clean_generated_line(image_prompt)
        visual_scene = self._trim_words(prompt, 90)
        visual_subject = self._trim_words(re.split(r"[,.;]", visual_scene)[0], 12)
        if not visual_subject:
            visual_subject = self._trim_words("historical scene from current block", 12)
        return {
            "cut_number": cut_number,
            "scene_block_id": block.get("block_id"),
            "narration": narration,
            "image_prompt": "",
            "visual_year": str(visual_world.get("time_range") or "historical period").strip(),
            "visual_period": str(visual_world.get("culture_scope") or visual_world.get("time_range") or "historical period").strip(),
            "visual_location": str(visual_world.get("place_scope") or "story location").strip(),
            "visual_evidence": "Derived from the current scene block and narration.",
            "visual_subject": visual_subject,
            "visual_scene": visual_scene,
            "scene_type": "body",
            "shorts_candidate": False,
        }

    @staticmethod
    def _script_text_block_from_cuts(
        *,
        block: dict,
        start: int,
        end: int,
        cuts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        lines: list[dict[str, Any]] = []
        for offset, cut in enumerate(cuts):
            cut_number = start + offset
            if isinstance(cut, dict):
                try:
                    cut_number = int(cut.get("cut_number") or cut_number)
                except (TypeError, ValueError):
                    pass
                lines.append({
                    "cut_number": cut_number,
                    "scene_block_id": block.get("block_id"),
                    "narration": str(cut.get("narration") or "").strip(),
                    "visual_subject": str(cut.get("visual_subject") or "").strip(),
                    "visual_scene": str(cut.get("visual_scene") or "").strip(),
                    "visual_evidence": str(cut.get("visual_evidence") or "").strip(),
                    "visual_year": str(cut.get("visual_year") or "").strip(),
                    "visual_period": str(cut.get("visual_period") or "").strip(),
                    "visual_location": str(cut.get("visual_location") or "").strip(),
                })
        return {
            "block_id": block.get("block_id"),
            "cut_range": f"{start}-{end}",
            "lines": lines,
        }

    @staticmethod
    def _history_cuts_from_text_blocks(text_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for text_block in text_blocks:
            if not isinstance(text_block, dict):
                continue
            for line in text_block.get("lines") or []:
                if isinstance(line, dict):
                    history.append(line)
        return history

    @staticmethod
    def _degenerate_repetition_issue(text: str) -> str | None:
        value = str(text or "")
        if not value:
            return None
        words = re.findall(r"[A-Za-z가-힣]{3,}", value.lower())
        if len(words) < 4:
            return None
        consecutive = 1
        for idx in range(1, len(words)):
            if words[idx] == words[idx - 1]:
                consecutive += 1
                if consecutive >= 4:
                    return f"동일 토큰 연속 반복 `{words[idx]}`"
            else:
                consecutive = 1
        counts: dict[str, int] = {}
        for word in words:
            counts[word] = counts.get(word, 0) + 1
        repeated_word, repeated_count = max(counts.items(), key=lambda item: item[1])
        if repeated_count >= 8 and repeated_count / max(len(words), 1) >= 0.25:
            return f"토큰 과반복 `{repeated_word}` {repeated_count}회"
        return None

    def _normalize_and_validate_scene_block_cuts(
        self,
        *,
        block_cuts: Any,
        config: dict,
        block: dict,
        block_index: int,
        start: int,
        end: int,
        previous_cuts: list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        expected_count = end - start + 1
        if not isinstance(block_cuts, list):
            raise ValueError(f"scene_block {block_index} did not return cuts array")
        if len(block_cuts) != expected_count:
            raise ValueError(
                f"scene_block {block_index} returned {len(block_cuts)} cuts, expected {expected_count}"
            )

        hard_issues: list[str] = []
        warnings: list[str] = []
        normalized: list[dict[str, Any]] = []
        forbidden_terms = self._configured_forbidden_terms(config)
        history_narrations = self._cut_history_summary(previous_cuts, limit=20)
        scope_text = json.dumps(block, ensure_ascii=False)
        for offset, raw_cut in enumerate(block_cuts):
            expected_cut_number = start + offset
            if not isinstance(raw_cut, dict):
                hard_issues.append(f"cut {expected_cut_number}: 컷 항목이 객체가 아니라 JSON 조립에서 제외했습니다")
                continue
            cut = dict(raw_cut)
            cut["cut_number"] = expected_cut_number
            cut["scene_block_id"] = cut.get("scene_block_id") or block.get("block_id")
            cut["image_prompt"] = ""
            cut["shorts_candidate"] = False
            for key in ("shorts_group", "shorts_reason", "shorts_score", "shorts_title"):
                cut.pop(key, None)

            narration = str(cut.get("narration") or "").strip()
            if not narration:
                hard_issues.append(f"cut {expected_cut_number}: narration이 비어 있습니다")
            for field in ("visual_year", "visual_period", "visual_location", "visual_subject", "visual_scene"):
                if not str(cut.get(field) or "").strip():
                    hard_issues.append(f"cut {expected_cut_number}: {field}가 비어 있습니다")
            for field in ("visual_evidence", "visual_subject", "visual_scene"):
                value = str(cut.get(field) or "")
                repeat_issue = self._degenerate_repetition_issue(value)
                if repeat_issue:
                    hard_issues.append(f"cut {expected_cut_number}: {field} 반복 출력 붕괴 - {repeat_issue}")
            visual_subject_words = re.findall(r"[A-Za-z가-힣0-9]{2,}", str(cut.get("visual_subject") or ""))
            visual_scene_words = re.findall(r"[A-Za-z가-힣0-9]{2,}", str(cut.get("visual_scene") or ""))
            if len(visual_subject_words) > 40:
                hard_issues.append(f"cut {expected_cut_number}: visual_subject가 너무 깁니다")
            if len(visual_scene_words) > 95:
                hard_issues.append(f"cut {expected_cut_number}: visual_scene이 너무 깁니다")
            visual_text_lower = " ".join(
                str(cut.get(field) or "").lower()
                for field in ("visual_subject", "visual_scene")
            )
            for blocked_visual in ("fog", "mist", "haze"):
                if blocked_visual in visual_text_lower:
                    hard_issues.append(f"cut {expected_cut_number}: 이미지 프롬프트 금지어 사용 {blocked_visual}")
            if not str(cut.get("visual_evidence") or "").strip():
                warnings.append(f"cut {expected_cut_number}: visual_evidence가 비어 있습니다")
            for term in forbidden_terms:
                if term and term in narration:
                    hard_issues.append(f"cut {expected_cut_number}: 금지어 사용 {term}")
            for previous_narration in history_narrations:
                similarity = self._text_similarity(narration, previous_narration)
                if narration == previous_narration or similarity >= 0.82:
                    hard_issues.append(
                        f"cut {expected_cut_number}: 이전 컷과 대사 중복률이 높습니다 ({similarity:.2f})"
                    )
                    break
            guarded_terms = {
                "진국": ("진국",),
                "2천여 호": ("2천여 호", "이천여 호", "2천여 가구", "이천여 가구"),
            }
            for label, variants in guarded_terms.items():
                if any(variant in narration for variant in variants) and not any(
                    variant in scope_text for variant in variants
                ):
                    hard_issues.append(f"cut {expected_cut_number}: 현재 블럭 범위 밖 핵심어 사용 {label}")
            normalized.append(cut)

        try:
            timing_issues = self.validate_script_timing({"cuts": normalized}, config)
            for item in timing_issues[:5]:
                warnings.append(
                    f"cut {item.get('cut_number')}: 글자 수/TTS 범위 이탈 "
                    f"{item.get('amount')}{item.get('unit')} / 목표 {item.get('target_range')}"
                )
        except Exception as exc:
            warnings.append(f"TTS 길이 검사를 완료하지 못했습니다: {exc}")

        word_sets = [self._narration_words(cut.get("narration") or "") for cut in normalized]
        for idx in range(2, len(word_sets)):
            repeated = sorted(word_sets[idx - 2] & word_sets[idx - 1] & word_sets[idx])
            if repeated:
                warnings.append(
                    f"cut {normalized[idx].get('cut_number')}: 같은 단어 3컷 이상 반복 "
                    + ", ".join(repeated[:6])
                )

        endings = [self._sentence_ending(cut.get("narration") or "") for cut in normalized]
        ending_groups = [self._ending_group(ending) for ending in endings]
        group_counts = {group: ending_groups.count(group) for group in {"습니다", "요", "죠"}}
        if expected_count >= 10:
            if group_counts.get("죠", 0) >= 4:
                hard_issues.append(
                    f"scene_block {block_index}: `죠` 계열 종결이 {group_counts.get('죠', 0)}컷입니다. 10컷 안에서는 최대 3컷만 허용합니다"
                )
            if group_counts.get("습니다", 0) < 1:
                hard_issues.append(f"scene_block {block_index}: `습니다/입니다` 계열 종결이 최소 1컷 필요합니다")
            if group_counts.get("요", 0) < 1:
                warnings.append(f"scene_block {block_index}: `요` 계열 종결이 없어 말투가 단조롭습니다")
        for idx in range(2, len(endings)):
            if endings[idx] and endings[idx] == endings[idx - 1] == endings[idx - 2]:
                warnings.append(
                    f"cut {normalized[idx].get('cut_number')}: 같은 종결어 3컷 이상 반복 {endings[idx]}"
                )

        if len(normalized) != expected_count:
            raise ValueError(
                f"scene_block {block_index} JSON assembly failed: "
                f"assembled {len(normalized)} cuts, expected {expected_count}; "
                + "; ".join(hard_issues[:8])
            )
        for issue in hard_issues[:12]:
            warnings.append(f"python 조립 경고: {issue}")

        return normalized, warnings

    @staticmethod
    def _scene_block_cuts_payload(parsed: Any) -> Any:
        if isinstance(parsed, list):
            return parsed
        if not isinstance(parsed, dict):
            return None
        cuts = parsed.get("cuts")
        if isinstance(cuts, dict):
            ordered: list[Any] = []
            for key, value in sorted(cuts.items(), key=lambda item: str(item[0])):
                if isinstance(value, dict):
                    ordered.append(value)
            return ordered
        if isinstance(cuts, list):
            return cuts
        for key in ("scenes", "items", "data", "result"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict) and isinstance(value.get("cuts"), list):
                return value.get("cuts")
        if any(key in parsed for key in ("cut_number", "narration", "visual_scene")):
            return [parsed]
        return None

    async def _repair_scene_block_with_gemma(
        self,
        *,
        topic: str,
        config: dict,
        story_plan: dict,
        block: dict,
        previous_cuts: list[dict[str, Any]],
        next_block: dict | None,
        future_blocks: list[dict[str, Any]] | None = None,
        block_index: int,
        start: int,
        end: int,
        last_error: Exception | None,
    ) -> tuple[list[dict[str, Any]] | None, list[str], str]:
        configured_gemma_model = str(config.get("validation_gemma_model") or "").strip()
        current_model = str(self.model_name or self.model_id or "").strip()
        gemma_model = configured_gemma_model or (
            current_model if current_model.lower().startswith("gemma") else "gemma4:26b-a4b-it-q4_K_M"
        )
        if gemma_model.startswith("ollama:"):
            gemma_model = gemma_model.split(":", 1)[1]
        service = OllamaService(gemma_model)
        expected_count = end - start + 1
        warnings: list[str] = []
        last_error_text = str(last_error or "")
        for attempt in range(1, SCENE_BLOCK_GEMMA_REPAIR_ATTEMPTS + 1):
            self._raise_if_cancelled(config)
            self._emit_script_progress(
                config,
                completed=block_index - 1,
                total=len(self._scene_block_ranges(story_plan)) or 1,
                message=(
                    f"scene_block {block_index} Gemma 형식 재작성 "
                    f"{attempt}/{SCENE_BLOCK_GEMMA_REPAIR_ATTEMPTS} ({start}-{end}컷)"
                ),
                block={
                    "block_index": block_index,
                    "total_blocks": len(self._scene_block_ranges(story_plan)) or 1,
                    "cut_range": f"{start}-{end}",
                    "generation_status": "running",
                    "validation_status": "running",
                    "generation_model": gemma_model,
                    "validation_model": "python",
                    "message": last_error_text[:220],
                },
            )
            try:
                text_prompt = service._build_scene_block_text_user_prompt(
                    topic=topic,
                    config=config,
                    story_plan=story_plan,
                    scene_block=block,
                    previous_cuts=previous_cuts,
                    next_block=next_block,
                    future_blocks=future_blocks,
                    start=start,
                    end=end,
                )
                text_prompt += (
                    "\n\n이전 생성 실패 사유:\n"
                    f"{last_error_text[:1200]}\n"
                    "같은 실패를 반복하지 말고 지정된 텍스트 형식으로만 다시 작성하세요."
                )
                raw_text = await service._chat_text(
                    system=service._build_scene_block_text_system_prompt(config),
                    user=text_prompt,
                    temperature=0.2,
                    num_predict=self._scene_block_text_num_predict(expected_count),
                    num_ctx=OLLAMA_SCENE_BLOCK_NUM_CTX,
                    result_dir=str(config.get("result_dir") or ""),
                    raw_label=f"scene_block_{block_index}_gemma_repair_{attempt}_{gemma_model}_raw",
                )
                parsed_cuts = service._parse_scene_block_text_response(
                    raw_text,
                    block=block,
                    story_plan=story_plan,
                    start=start,
                    end=end,
                )
                normalized, block_warnings = self._normalize_and_validate_scene_block_cuts(
                    block_cuts=parsed_cuts,
                    config=config,
                    block=block,
                    block_index=block_index,
                    start=start,
                    end=end,
                    previous_cuts=previous_cuts,
                )
                warnings.extend(block_warnings)
                return normalized, warnings, gemma_model
            except Exception as exc:
                last_error_text = str(exc)
                warnings.append(f"Gemma 형식 재작성 {attempt}회 실패: {str(exc)[:180]}")
        return None, warnings, gemma_model

    async def _generate_script_from_scene_blocks(
        self,
        topic: str,
        config: dict,
        story_plan: dict,
        blocks: list[dict],
    ) -> dict:
        total_blocks = len(blocks)
        config = dict(config or {})
        config["topic"] = topic
        existing_script = config.get("script_existing_script") if isinstance(config.get("script_existing_script"), dict) else {}
        resume_partial = config.get("script_resume_partial") if isinstance(config.get("script_resume_partial"), dict) else {}
        regenerate_block_index = 0
        try:
            regenerate_block_index = int(config.get("script_regenerate_block_index") or 0)
        except (TypeError, ValueError):
            regenerate_block_index = 0
        existing_cuts = existing_script.get("cuts") if isinstance(existing_script.get("cuts"), list) else []
        resume_cuts = resume_partial.get("cuts") if isinstance(resume_partial.get("cuts"), list) else []
        existing_text_blocks = existing_script.get("script_text_blocks") if isinstance(existing_script.get("script_text_blocks"), list) else []
        resume_text_blocks = resume_partial.get("script_text_blocks") if isinstance(resume_partial.get("script_text_blocks"), list) else []
        text_blocks: list[dict[str, Any]] = []
        history_cuts: list[dict[str, Any]] = []
        resume_completed_blocks = 0
        if resume_text_blocks and not regenerate_block_index:
            try:
                declared_completed = int(resume_partial.get("completed_scene_blocks") or 0)
            except (TypeError, ValueError):
                declared_completed = 0
            resume_completed_blocks = max(0, min(total_blocks, declared_completed, len(resume_text_blocks)))
            text_blocks = [dict(item) for item in resume_text_blocks[:resume_completed_blocks] if isinstance(item, dict)]
            history_cuts = self._history_cuts_from_text_blocks(text_blocks)
        elif resume_cuts and not regenerate_block_index:
            try:
                declared_completed = int(resume_partial.get("completed_scene_blocks") or 0)
            except (TypeError, ValueError):
                declared_completed = 0
            completed_by_cut_count = len(resume_cuts) // 10
            resume_completed_blocks = max(0, min(total_blocks, declared_completed, completed_by_cut_count))
            resume_cut_limit = resume_completed_blocks * 10
            block_lines: dict[int, list[dict[str, Any]]] = {}
            for cut in resume_cuts:
                if not isinstance(cut, dict):
                    continue
                try:
                    cut_number = int(cut.get("cut_number") or 0)
                except (TypeError, ValueError):
                    continue
                if 1 <= cut_number <= resume_cut_limit:
                    block_id = math.ceil(cut_number / 10)
                    block_lines.setdefault(block_id, []).append(dict(cut))
            for block_id in sorted(block_lines):
                start, end = self._parse_range_text(blocks[block_id - 1].get("cut_range")) or ((block_id - 1) * 10 + 1, block_id * 10)
                text_blocks.append(self._script_text_block_from_cuts(block=blocks[block_id - 1], start=start, end=end, cuts=block_lines[block_id]))
            history_cuts = self._history_cuts_from_text_blocks(text_blocks)
        regenerate_prefix: list[dict[str, Any]] = []
        regenerate_suffix: list[dict[str, Any]] = []
        regenerate_completed_blocks = 0
        if regenerate_block_index:
            if regenerate_block_index < 1 or regenerate_block_index > total_blocks:
                raise ValueError(f"invalid regenerate block index: {regenerate_block_index}")
            target_range = self._parse_range_text(blocks[regenerate_block_index - 1].get("cut_range"))
            if target_range is None:
                raise ValueError(f"invalid scene_block cut_range: {blocks[regenerate_block_index - 1].get('cut_range')}")
            target_start, target_end = target_range
            source_text_blocks = existing_text_blocks
            if not source_text_blocks and existing_cuts:
                converted: list[dict[str, Any]] = []
                for block_id in range(1, total_blocks + 1):
                    parsed = self._parse_range_text(blocks[block_id - 1].get("cut_range"))
                    if not parsed:
                        continue
                    block_start, block_end = parsed
                    block_cuts = [
                        dict(cut) for cut in existing_cuts
                        if isinstance(cut, dict)
                        and block_start <= int(cut.get("cut_number") or 0) <= block_end
                    ]
                    if block_cuts:
                        converted.append(self._script_text_block_from_cuts(block=blocks[block_id - 1], start=block_start, end=block_end, cuts=block_cuts))
                source_text_blocks = converted
            text_blocks = [
                dict(item) for item in source_text_blocks
                if isinstance(item, dict) and int(item.get("block_id") or 0) != regenerate_block_index
            ]
            history_cuts = self._history_cuts_from_text_blocks([
                item for item in text_blocks if isinstance(item, dict) and int(item.get("block_id") or 0) < regenerate_block_index
            ])
            regenerate_completed_blocks = min(total_blocks, len(source_text_blocks))
        self._raise_if_cancelled(config)
        self._emit_script_progress(
            config,
            completed=regenerate_block_index - 1 if regenerate_block_index else resume_completed_blocks,
            total=total_blocks,
            message=(
                f"scene_block {regenerate_block_index}/{total_blocks} 재생성 준비 중"
                if regenerate_block_index
                else f"scene_blocks {resume_completed_blocks}/{total_blocks} 이어서 준비 중"
                if resume_completed_blocks
                else f"scene_blocks 0/{total_blocks} 준비 중"
            ),
            block={"reset": True, "total_blocks": total_blocks},
        )
        for index, block in enumerate(blocks, start=1):
            if regenerate_block_index and index != regenerate_block_index:
                continue
            if not regenerate_block_index and index <= resume_completed_blocks:
                continue
            self._raise_if_cancelled(config)
            parsed_range = self._parse_range_text(block.get("cut_range"))
            if parsed_range is None:
                raise ValueError(f"invalid scene_block cut_range: {block.get('cut_range')}")
            start, end = parsed_range
            expected_count = end - start + 1
            next_block = blocks[index] if index < total_blocks else None
            future_blocks = blocks[index : min(total_blocks, index + 4)]
            last_error: Exception | None = None
            block_text: dict[str, Any] | None = None
            generation_model_used = self.model_id
            max_attempts = 1 + SCENE_BLOCK_MAX_REGENERATIONS
            for attempt in range(1, max_attempts + 1):
                self._raise_if_cancelled(config)
                retry_text = "" if attempt == 1 else f" 재생성 {attempt - 1}/{SCENE_BLOCK_MAX_REGENERATIONS}"
                self._emit_script_progress(
                    config,
                    completed=index - 1,
                    total=total_blocks,
                    message=f"scene_block {index}/{total_blocks} 생성 중{retry_text} ({start}-{end}컷)",
                    block={
                        "block_index": index,
                        "total_blocks": total_blocks,
                        "cut_range": f"{start}-{end}",
                        "generation_status": "running",
                        "validation_status": "pending",
                        "generation_model": self.model_id,
                        "validation_model": "python",
                    },
                )
                failure_phase = "generation"
                try:
                    try:
                        raw_text = await self._chat_text(
                            system=self._build_scene_block_text_system_prompt(config),
                            user=self._build_scene_block_text_user_prompt(
                                topic=topic,
                                config=config,
                                story_plan=story_plan,
                                scene_block=block,
                                previous_cuts=history_cuts[-20:],
                                next_block=next_block,
                                future_blocks=future_blocks,
                                start=start,
                                end=end,
                            ),
                            temperature=0.35,
                            num_predict=self._scene_block_text_num_predict(expected_count),
                            num_ctx=OLLAMA_SCENE_BLOCK_NUM_CTX,
                            result_dir=str(config.get("result_dir") or ""),
                            raw_label=f"scene_block_{index}_attempt_{attempt}_{self.model_name}_raw",
                        )
                        parsed_cuts = self._parse_scene_block_text_response(
                            raw_text,
                            block=block,
                            story_plan=story_plan,
                            start=start,
                            end=end,
                        )
                    except Exception as exc:
                        self._emit_script_progress(
                            config,
                            completed=index - 1,
                            total=total_blocks,
                            message=f"scene_block {index}/{total_blocks} 생성 실패, 재시도 준비 중: {str(exc)[:180]}",
                            block={
                                "block_index": index,
                                "total_blocks": total_blocks,
                                "cut_range": f"{start}-{end}",
                                "generation_status": "failed",
                                "validation_status": "pending",
                                "generation_model": self.model_id,
                                "validation_model": "python",
                                "generation_failures": attempt,
                                "message": str(exc)[:220],
                            },
                        )
                        raise
                    self._raise_if_cancelled(config)
                    self._emit_script_progress(
                        config,
                        completed=index - 1,
                        total=total_blocks,
                        message=f"scene_block {index}/{total_blocks} 블럭 텍스트 분리 중 ({start}-{end}컷)",
                        block={
                            "block_index": index,
                            "total_blocks": total_blocks,
                            "cut_range": f"{start}-{end}",
                            "generation_status": "completed",
                            "validation_status": "pending",
                            "generation_model": self.model_id,
                            "validation_model": "",
                        },
                    )
                    block_text = self._script_text_block_from_cuts(
                        block=block,
                        start=start,
                        end=end,
                        cuts=parsed_cuts,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt >= max_attempts:
                        break
                    self._emit_script_progress(
                        config,
                        completed=index - 1,
                        total=total_blocks,
                        message=(
                            f"scene_block {index}/{total_blocks} 텍스트 분리 실패, "
                            f"재시도 준비 중: {str(exc)[:180]}"
                        ),
                        block={
                            "block_index": index,
                            "total_blocks": total_blocks,
                            "cut_range": f"{start}-{end}",
                            "generation_status": "completed",
                            "validation_status": "failed",
                            "generation_model": self.model_id,
                            "validation_model": "",
                            "validation_failures": attempt,
                            "message": str(exc)[:220],
                        },
                    )
            if block_text is None:
                raise RuntimeError(f"scene_block {index} text generation failed: {last_error}")
            text_blocks = [
                item for item in text_blocks
                if not (isinstance(item, dict) and int(item.get("block_id") or 0) == index)
            ]
            text_blocks.append(block_text)
            text_blocks.sort(key=lambda item: int(item.get("block_id") or 0) if isinstance(item, dict) else 0)
            history_cuts = self._history_cuts_from_text_blocks(text_blocks)
            if regenerate_block_index:
                text_blocks.sort(key=lambda item: int(item.get("block_id") or 0) if isinstance(item, dict) else 0)
            self._emit_script_progress(
                config,
                completed=max(index, regenerate_completed_blocks) if regenerate_block_index else index,
                total=total_blocks,
                message=f"scene_block {index}/{total_blocks} 블럭 텍스트 생성 완료 ({start}-{end}컷)",
                block={
                    "block_index": index,
                    "total_blocks": total_blocks,
                    "cut_range": f"{start}-{end}",
                    "generation_status": "completed",
                    "validation_status": "pending",
                    "generation_model": generation_model_used,
                    "validation_model": "",
                    "fallback_used": False,
                    "message": "텍스트 생성 완료",
                },
            )
            self._save_partial_text_blocks_progress(
                config,
                story_plan,
                text_blocks,
                completed_blocks=max(index, regenerate_completed_blocks) if regenerate_block_index else index,
                total_blocks=total_blocks,
            )
            if regenerate_block_index:
                break
        self._raise_if_cancelled(config)

        metadata = self._script_metadata_from_story_plan(topic, config, story_plan)
        script = {
            "script_version": "3.1",
            **metadata,
            "visual_world": story_plan.get("visual_world") or {},
            "story_core": story_plan.get("story_core") or {},
            "fact_ledger": story_plan.get("fact_ledger") or {},
            "visual_plan": story_plan.get("visual_plan") or {},
            "scene_blocks": blocks,
            "script_text_blocks": text_blocks,
            "text_only": True,
        }
        return script

    async def generate_story_plan(self, topic: str, config: dict) -> dict:
        cached = self._load_cached_story_plan(topic, config)
        if cached is not None:
            return cached
        target_cuts = self._expected_cut_count(config)
        raw = await self._chat_text(
            system=self._build_story_plan_text_system_prompt(config),
            user=self._build_story_plan_text_user_prompt(topic, config),
            temperature=0.35,
            num_predict=18000 if target_cuts >= 100 else 7000,
            result_dir=str(config.get("result_dir") or ""),
            raw_label=f"story_plan_{self.model_name}_raw",
            think=True,
        )
        parsed = self._parse_story_plan_text_response(raw, topic=topic, config=config)
        parsed = self._normalize_story_plan_structure(parsed)
        assert_story_plan(parsed, target_cuts, topic, config)
        self._save_story_plan(topic, config, parsed)
        return parsed

    async def generate_script(self, topic: str, config: dict) -> dict:
        estimated_cuts = self._expected_cut_count(config)
        story_plan = await self._ensure_story_plan_for_script(topic, config)
        script_config = dict(config or {})
        script_config["story_plan"] = story_plan
        blocks = self._scene_block_ranges(story_plan)
        if blocks:
            parsed = await self._generate_script_from_scene_blocks(topic, script_config, story_plan, blocks)
        else:
            self._emit_script_progress(
                script_config,
                completed=0,
                total=1,
                message="단일 호출 대본 생성 중",
            )
            parsed = await self._chat_json(
                system=self._get_system_prompt(script_config),
                user=self._build_user_prompt(topic, script_config),
                temperature=0.65,
                num_predict=min(64000, max(12000, estimated_cuts * 360 + 8192)),
                result_dir=str(script_config.get("result_dir") or ""),
                raw_label=f"script_single_{self.model_name}_raw",
            )
            self._emit_script_progress(
                script_config,
                completed=1,
                total=1,
                message="단일 호출 대본 생성 완료",
            )
        if isinstance(parsed.get("script_text_blocks"), list):
            self._emit_script_progress(
                script_config,
                completed=len(blocks) or 1,
                total=len(blocks) or 1,
                message="대본 블럭 텍스트 생성 완료, 검수 대기",
                status="completed",
            )
            return parsed
        cuts = parsed.get("cuts") or []
        is_partial_block_regeneration = bool(script_config.get("script_regenerate_block_index")) and len(cuts) < estimated_cuts
        if len(cuts) != estimated_cuts and not is_partial_block_regeneration:
            raise ValueError(f"script generation returned {len(cuts)} cuts, expected {estimated_cuts}")
        parsed = self.strengthen_visual_context(parsed, config)
        parsed = self.normalize_v31_story_contract(parsed, config, topic)
        if not is_partial_block_regeneration:
            try:
                assert_script_quality(parsed, topic)
            except Exception as exc:
                print(f"[script] quality warning only: {exc}")
        self.assert_script_timing(parsed, config)
        self._emit_script_progress(
            script_config,
            completed=len(blocks) or 1,
            total=len(blocks) or 1,
            message="대본 생성 검증 완료",
            status="completed",
        )
        return parsed
