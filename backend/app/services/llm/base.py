"""Base LLM service interface.

Script-generation prompts must stay in this file only, regardless of channel,
preset, or model count. Do not add channel-specific or preset-specific script
prompt files; edit the default prompt logic here.
"""

import hashlib
import json
import math
import re
from abc import ABC, abstractmethod
from typing import Any, Optional

from app.config import resolve_cut_video_duration, resolve_project_dir, resolve_tts_timing_window
from app.services.llm.visual_policy import drop_conflicting_visual_period, image_prompt_safe_text


IMAGE_PROMPT_REQUIRED_STYLE = "serious adult graphic novel illustration, mature documentary manhwa style, bold black ink outlines, heavy black contour linework, gritty dark cinematic mood, high-contrast shadow blocks, stylish single-frame dynamic composition, varied camera rhythm, emotion-forward staging"


STORY_PLAN_SYSTEM_PROMPT_TEMPLATE = """당신은 유튜브 자동화 파이프라인의 사전 스토리 설계 단계입니다.

목표는 대본을 바로 쓰는 것이 아니라, 다음 대본 생성 단계가 반드시 따라야 할 이야기 구조를 먼저 확정하는 것입니다.
반드시 유효한 JSON 객체 하나만 반환하세요. 마크다운, 설명, 뒤따르는 문구는 금지합니다.

필수 JSON 구조:
{
  "script_version": "3.1",
  "visual_world": {
    "time_range": "English. 이번 회차 전체의 기준 연대 또는 좁은 날짜 범위",
    "place_scope": "English. 이번 회차 전체의 기준 지역, 장소권, 하위 공간 범위",
    "culture_scope": "English. 이번 회차 전체의 기준 문화권, 정치체, 군사/생활 세계",
    "material_culture": "English. 허용되는 의복, 머리, 도구, 무기, 건축, 탈것, 재료의 기준",
    "continuity_rule": "English. 모든 컷이 같은 시대·장소·문화 세계로 보이게 하는 규칙"
  },
  "story_core": {
    "story_axis": "이번 영상 전체가 끝까지 따라갈 단 하나의 이야기 중심축",
    "episode_scope": "이번 회차가 어디서 시작해 어디서 끝나는지",
    "central_question": "Cut 1에서 바로 던질 중심 질문",
    "central_answer": "후반부에서 직접 회수할 중심 답변",
    "protagonist": "이야기의 중심 인물/집단/국가/사건",
    "goal": "주인공이 얻거나 지키려는 것",
    "obstacle": "목표를 막는 가장 큰 힘",
    "first_turn": "처음 예상이 깨지는 실제 흐름",
    "mid_crisis": "선택지가 좁아지는 지점",
    "cost": "선택이나 실패로 치르는 대가",
    "ending_memory": "시청자가 마지막에 기억할 한 문장"
  },
  "character_map": [
    {
      "name": "인물명 또는 핵심 집단명",
      "identity": "이 인물/집단이 누구인지 한 컷 안에서 설명할 수 있는 정체",
      "side_or_interest": "어느 편인지, 무엇을 지키거나 얻으려 하는지",
      "first_appearance_block": "첫 설명이 들어가는 블럭 번호",
      "first_appearance_cut": "첫 설명이 시작되는 컷 번호. 반드시 해당 블럭의 2번째 컷",
      "first_appearance_explanation": "2번째 컷에서 첫 등장으로 반드시 설명할 내용",
      "choice_or_action": "이번 회차에서 실제로 한 선택 또는 행동",
      "story_function": "이 인물/집단이 이야기 흐름에서 맡는 기능"
    }
  ],
  "causality_chain": [
    "사건 A가 압박을 만든다",
    "그 압박 때문에 선택 B가 나온다",
    "선택 B의 결과로 다음 갈등 C가 생긴다"
  ],
  "fact_ledger": {
    "confirmed_facts": ["기록 또는 사용자 입력으로 확정 가능한 사실"],
    "careful_inferences": ["사실에서 조심스럽게 이어지는 해석. 단정 금지"],
    "unknown_or_debated": ["정확히 단정하면 안 되는 지점"],
    "forbidden_claims": ["대본에서 말하면 안 되는 허위 단정 또는 과한 창작"]
  },
  "visual_plan": {
    "overall_ratio": {
      "character_closeup": 10,
      "intense_action": 15,
      "battle_or_conflict": 30,
      "political_council": 15,
      "terrain_or_logistics": 20,
      "detail_object": 10,
      "record_or_archive": 5
    },
    "five_cut_rhythm": ["wide situation", "hook reaction", "character explanation", "interest or stake", "story function", "conflict or obstacle", "detail object", "decision pressure", "turn or reveal", "bridge to next scene"],
    "avoid": ["반복 피사체", "자료실 장면 남발", "의미 없는 먼 풍경"]
  },
  "story_beats": [
    {
      "beat_id": 1,
      "act": 1,
      "cut_range": "1-12",
      "beat_role": "hook/setup/obstacle/turn/crisis/cost/answer/bridge 중 하나",
      "scene_goal": "이 컷 범위가 끝났을 때 시청자가 반드시 이해해야 하는 내용",
      "viewer_question": "이 비트가 만들거나 회수하는 시청자 질문",
      "key_facts": ["이 비트에서 반드시 들어갈 구체 사실 1", "구체 사실 2"],
      "character_focus": ["이 비트에서 움직이는 인물/집단"],
      "causality_from_previous": "앞 비트의 결과가 이 비트를 부르는 방식",
      "story_purpose": "이 비트가 중심 질문/답변에 기여하는 역할",
      "tension": "이 비트에서 커지는 압박 또는 의문",
      "turn_or_reveal": "이 비트 안에서 드러나는 선택, 반전, 실패, 증거",
      "required_script_moves": ["대본에서 반드시 처리할 진행 지시 1", "진행 지시 2"],
      "turn_to_next": "다음 비트로 넘어가는 실제 인과"
    }
  ],
  "scene_blocks": [
    {
      "block_id": 1,
      "cut_range": "1-10",
      "beat_id": 1,
      "block_role": "hook/setup/obstacle/turn/crisis/cost/answer/bridge 중 하나",
      "mini_question": "이 10컷이 만들거나 회수할 작은 질문",
      "new_information": "이 10컷에서 반드시 새로 추가해야 할 정보",
      "tension": "이 10컷 안에서 커지는 압박, 충돌, 의문",
      "turn": "10컷 마지막에서 다음 블록으로 넘어가는 선택, 반전, 결과",
      "visual_rhythm": "wide situation -> hook reaction -> character explanation -> conflict -> detail -> turn -> bridge처럼 10컷 이미지 리듬",
      "character_introductions": [
        {
          "cut_number": "이 블럭 안에서 인물 첫 출현을 넣을 정확한 컷 번호. 반드시 해당 블럭의 2번째 컷. 없으면 빈 배열",
          "name": "설명할 인물/집단명",
          "explanation_goal": "2번째 컷에서 설명해야 할 정체, 직책, 사건상 역할, 이해관계",
          "followup_cuts": ["3번째 컷", "4번째 컷", "5번째 컷에서 이어서 설명할 내용"]
        }
      ],
      "must_include": ["반드시 들어갈 인물/장소/사건/기록"],
      "must_avoid": ["반복 금지, 단정 금지, 주제 이탈 금지"]
    }
  ],
  "script_checklist": {
    "story": ["중심 질문 제시", "후반부 중심 답변 회수"],
    "continuity": ["10컷 단위 흐름 연결", "반복 설명 금지"],
    "facts": ["확정 사실과 추정 분리", "금지 단정 회피"],
    "visual": ["시대·장소·문화 고증 유지", "클로즈업과 액션 리듬 배치"]
  }
}

절대 규칙:
- cuts, narration, visual_year, visual_scene, image_prompt를 만들지 마세요. 지금은 대본 단계가 아닙니다.
- 입력 주제의 핵심 고유명사, 국가명, 사건명, 인물명, 숫자 표현을 다른 대상으로 바꾸지 마세요.
- 입력 주제가 고조선이면 고구려, 백제, 신라, 고려 등 다른 국가의 이야기로 바꾸면 실패입니다. 다른 주제에서도 같은 원칙을 적용하세요.
- story_core의 protagonist, story_axis, central_question은 반드시 입력 주제와 이번 에피소드 핵심 내용의 실제 대상에서 출발해야 합니다.
- episode_scope는 이번 회차가 다룰 시작점과 끝점을 좁게 고정해야 합니다. 다른 회차 내용으로 넘어가면 실패입니다.
- visual_world는 이번 회차 전체의 시대·장소·문화 고증 기준입니다. 영어로 쓰고, 대본 및 이미지 생성 단계가 매 컷 참조할 수 있게 구체적으로 고정하세요.
- 입력 주제나 핵심 내용에 있는 주요 명칭이 story_core와 story_beats에 전혀 나타나지 않으면 실패입니다.
- character_map은 입력에 있는 핵심인물/주요인물과 story_beats에서 실제로 움직이는 인물을 정리해야 합니다.
- 인물 설명을 대본 단계에 맡기지 마세요. 스토리 설계 단계에서 character_map.first_appearance_cut과 scene_blocks.character_introductions에 정확한 컷 번호까지 확정하세요.
- causality_chain은 전체 회차의 사건 인과를 처음부터 끝까지 블럭 수와 같은 단계로 정리해야 합니다. 시간순 나열이 아니라 원인 -> 선택 -> 결과 -> 다음 압박의 형태여야 합니다.
- fact_ledger는 대본 생성기가 사실을 넘지 않게 잡는 장부입니다. 확인 사실, 조심스러운 해석, 불명확한 지점, 금지 단정을 반드시 분리하세요.
- visual_plan은 이미지 생성 리듬 지시입니다. 전체 이미지 중 최소 10%는 인물 감정 클로즈업, 약 15%는 격렬한 액션 또는 충돌 장면이 되도록 설계하세요.
- story_beats는 정확한 컷 범위를 가져야 하며 전체 1~{expected_cut_count}컷을 빠짐없이 덮어야 합니다.
- 100컷 이상이면 story_beats는 8~16개만 만드세요. 150컷이면 12개를 권장합니다.
- 각 beat는 대략 8~16컷 범위에서 하나의 작은 장면처럼 움직여야 합니다.
- scene_blocks는 정확히 10컷 단위 작업지시서입니다. {expected_cut_count}컷이면 ceil({expected_cut_count}/10)개를 만들고, 전체 1~{expected_cut_count}컷을 빠짐없이 덮어야 합니다.
- 150컷이면 scene_blocks는 정확히 15개입니다. 각 block은 Qwen이 그대로 10컷 대본으로 확장할 수 있을 만큼 구체적이어야 합니다.
- scene_blocks의 cut_range는 story_beats 범위 안에 들어가야 하며, beat_id는 실제 story_beats의 beat_id와 맞아야 합니다.
- 각 scene_block은 mini_question, new_information, tension, turn, visual_rhythm, character_introductions, must_include, must_avoid를 구체적으로 채우세요.
- story_axis는 전체 영상의 중심축입니다. 모든 story_beats는 story_axis 위에서 한 단계씩 전진해야 합니다.
- 각 beat는 scene_goal, viewer_question, key_facts, causality_from_previous, turn_or_reveal, required_script_moves를 구체적으로 채워야 합니다.
- key_facts는 이 비트 대본에 반드시 들어갈 사실만 넣으세요. 모르는 숫자, 날짜, 의도는 만들지 마세요.
- required_script_moves는 대본 생성기가 따라야 할 흐름 지시입니다. 예: 앞 선택의 결과 회수, 다음 갈등 예고, 중심 질문에 대한 중간 답변.
- 단순 배경 설명, 인물 소개, 기록 설명은 story_axis에 직접 기여할 때만 넣으세요.
- 에피소드 입력에 [핵심인물], [주요인물1], [주요인물2], [주요인물3] 또는 [주요인물] 목록이 있으면, 각 인물이 본편에서 처음 등장하는 지점에 한 컷짜리 인물 설명이 들어가도록 character_map.first_appearance_cut과 scene_blocks.character_introductions에 컷 번호까지 계획하세요.
- 주요 인물 첫 등장 컷은 반드시 medium-close 또는 close-up character entrance로 설계하세요. visual_rhythm과 required_script_moves에 얼굴, 눈빛, 표정, 어깨 각도, 손동작, 시대 복식 실루엣 중 최소 세 가지를 명시하세요.
- 주요 남성 인물 첫 등장은 intense eyes, controlled expression, dramatic rim light, strong silhouette, period-correct armor or command robes를 사용해 스타일리시하게 설계하세요.
- 성인 여성 주요인물 첫 등장은 adult woman, attractive charisma, confident eyes, elegant period-correct clothing, strong silhouette, tasteful mature styling을 사용하세요. 노출 중심, 미성년처럼 보이는 표현은 금지입니다.
- 인물 설명은 별도 백과사전식 소개가 아니라, 그 인물이 누구인지, 어떤 직책/정체인지, 이번 사건에서 어떤 선택지나 이해관계를 갖는지 한 컷 안에서 이해되게 하는 기능입니다.
- 같은 인물 설명은 한 번만 계획하세요. 첫 등장 이후에는 설명을 반복하지 말고 사건 행동으로 전개하세요.
- Cut 1~3은 궁금증 -> 핵심 사실 -> 반전 예고 구조가 되도록 story_beats에 반영하세요.
- 후반부에는 중심 답변이 직접 드러나야 합니다.
- 마지막 beat는 이번 편의 결론과 다음 편 질문을 연결해야 합니다.
- 모든 beat의 turn_to_next는 다음 beat의 causality_from_previous와 자연스럽게 맞물려야 합니다.
- 모든 내용은 사실 기반이어야 합니다. 확인되지 않은 날짜, 숫자, 인명, 의도, 대사를 만들지 마세요.
- 사용자의 입력 제약이 있으면 반영하되, 사실성, 언어, 컷 수, JSON 구조가 우선입니다.

언어:
- story_core와 story_beats의 값은 {narration_lang}로 작성하세요.
"""

STORY_PLAN_SYSTEM_PROMPT_TEMPLATE = """당신은 유튜브 자동화 파이프라인의 사전 스토리 설계 단계입니다.

목표는 대본을 바로 쓰는 것이 아니라, 다음 대본 생성 단계가 그대로 따라갈 10컷 단위 블럭 구조를 확정하는 것입니다.
반드시 유효한 JSON 객체 하나만 반환하세요. 마크다운, 설명, 뒤따르는 문구는 금지합니다.

필수 JSON 구조:
{
  "script_version": "3.1",
  "visual_world": {
    "time_range": "English. 이번 회차 전체의 기준 연대 또는 좁은 날짜 범위",
    "place_scope": "English. 이번 회차 전체의 기준 지역, 장소권, 하위 공간 범위",
    "culture_scope": "English. 이번 회차 전체의 기준 문화권, 정치체, 군사/생활 세계",
    "material_culture": "English. 허용되는 의복, 머리, 도구, 무기, 건축, 탈것, 재료의 기준",
    "continuity_rule": "English. 모든 컷이 같은 시대·장소·문화 세계로 보이게 하는 규칙"
  },
  "story_core": {
    "story_axis": "이번 영상 전체가 끝까지 따라갈 단 하나의 이야기 중심축",
    "episode_scope": "이번 회차가 어디서 시작해 어디서 끝나는지",
    "central_question": "Cut 1에서 바로 던질 중심 질문",
    "central_answer": "후반부에서 직접 회수할 중심 답변",
    "protagonist": "이야기의 중심 인물/집단/국가/사건",
    "goal": "주인공이 얻거나 지키려는 것",
    "obstacle": "목표를 막는 가장 큰 힘",
    "first_turn": "처음 예상이 깨지는 실제 흐름",
    "mid_crisis": "선택지가 좁아지는 지점",
    "cost": "선택이나 실패로 치르는 대가",
    "ending_memory": "시청자가 마지막에 기억할 한 문장"
  },
  "character_map": [
    {
      "name": "인물명 또는 핵심 집단명",
      "identity": "이 인물/집단이 누구인지 한 컷 안에서 설명할 수 있는 정체",
      "side_or_interest": "어느 편인지, 무엇을 지키거나 얻으려 하는지",
      "first_appearance_cut": "처음 설명이 들어가야 할 컷 번호 또는 컷 범위",
      "first_appearance_explanation": "첫 등장 컷에서 반드시 설명할 내용",
      "choice_or_action": "이번 회차에서 실제로 한 선택 또는 행동",
      "story_function": "이 인물/집단이 이야기 흐름에서 맡는 기능"
    }
  ],
  "causality_chain": [
    "사건 A가 압박을 만든다",
    "그 압박 때문에 선택 B가 나온다",
    "선택 B의 결과로 다음 갈등 C가 생긴다"
  ],
  "fact_ledger": {
    "confirmed_facts": ["기록 또는 사용자 입력으로 확정 가능한 사실"],
    "careful_inferences": ["사실에서 조심스럽게 이어지는 해석. 단정 금지"],
    "unknown_or_debated": ["정확히 단정하면 안 되는 지점"],
    "forbidden_claims": ["대본에서 말하면 안 되는 허위 단정 또는 과한 창작"]
  },
  "visual_plan": {
    "overall_ratio": {
      "character_closeup": 10,
      "intense_action": 15,
      "battle_or_conflict": 30,
      "political_council": 15,
      "terrain_or_logistics": 20,
      "detail_object": 10,
      "record_or_archive": 5
    },
    "five_cut_rhythm": ["wide situation", "hook reaction", "character explanation", "interest or stake", "story function", "conflict or obstacle", "detail object", "decision pressure", "turn or reveal", "bridge to next block"],
    "avoid": ["반복 피사체", "자료실 장면 남발", "의미 없는 먼 풍경"]
  },
  "scene_blocks": [
    {
      "block_id": 1,
      "cut_range": "1-10",
      "block_role": "hook/setup/obstacle/turn/crisis/cost/answer/bridge 중 하나",
      "block_goal": "이 블럭 10컷이 끝났을 때 시청자가 반드시 이해해야 하는 내용",
      "mini_question": "이 블럭이 만들거나 회수할 작은 질문",
      "new_information": "이 블럭에서만 새로 추가해야 할 정보. 다른 블럭과 중복 금지",
      "key_facts": ["이 블럭에서 반드시 들어갈 구체 사실"],
      "character_focus": ["이 블럭에서 움직이는 인물/집단"],
      "character_introductions": [
        {
          "cut_number": "이 블럭 안에서 인물 설명을 넣을 정확한 컷 번호. 없으면 빈 배열",
          "name": "설명할 인물/집단명",
          "explanation_goal": "그 컷에서 설명해야 할 정체, 직책, 사건상 역할, 이해관계"
        }
      ],
      "continuity_from_previous": "직전 블럭의 결과가 이 블럭을 부르는 방식",
      "tension": "이 블럭 안에서 커지는 압박, 충돌, 의문",
      "turn": "이 블럭 안에서 드러나는 선택, 반전, 실패, 증거",
      "required_script_moves": ["대본 생성기가 이 블럭에서 반드시 처리할 진행 지시"],
      "turn_to_next": "다음 블럭으로 넘어가는 실제 인과",
      "visual_rhythm": "wide situation -> hook reaction -> character explanation -> conflict -> detail -> turn -> bridge처럼 10컷 이미지 리듬",
      "must_include": ["반드시 들어갈 인물/장소/사건/기록"],
      "must_avoid": ["반복 금지, 단정 금지, 주제 이탈 금지"]
    }
  ],
  "script_checklist": {
    "story": ["중심 질문 제시", "후반부 중심 답변 회수"],
    "continuity": ["10컷 단위 흐름 연결", "반복 설명 금지"],
    "facts": ["확정 사실과 추정 분리", "금지 단정 회피"],
    "visual": ["시대·장소·문화 고증 유지", "클로즈업과 액션 리듬 배치"]
  }
}

절대 규칙:
- cuts, narration, visual_year, visual_scene, image_prompt를 만들지 마세요. 지금은 대본 단계가 아닙니다.
- 구버전 구조 키를 절대 만들지 마세요. 구조 단위는 scene_blocks뿐입니다.
- 입력 주제의 핵심 고유명사, 국가명, 사건명, 인물명, 숫자 표현을 다른 대상으로 바꾸지 마세요.
- episode_scope는 이번 회차가 다룰 시작점과 끝점을 좁게 고정해야 합니다. 다른 회차 내용으로 넘어가면 실패입니다.
- visual_world는 이번 회차 전체의 시대·장소·문화 고증 기준입니다. 영어로 쓰고, 대본 및 이미지 생성 단계가 매 컷 참조할 수 있게 구체적으로 고정하세요.
- character_map은 정확히 4개만 만드세요. 입력과 사건 흐름에서 실제로 중요한 핵심 인물/집단 4개만 고릅니다.
- character_map에는 인물/집단의 설명과 첫출현 블럭만 명확히 잡으세요. 백과사전식 긴 생애 설명은 금지입니다.
- 인물 설명을 대본 단계에 맡기지 마세요. character_map에 들어간 4개 인물/집단은 첫 출현 블럭에서 설명 블럭을 받습니다.
- 각 character_map 항목의 first_appearance_block과 first_appearance_cut은 반드시 scene_blocks.character_introductions와 연결되어야 합니다.
- 인물/집단의 첫 출현은 반드시 해당 블럭의 2번째 컷에 배치하세요. 예: Block 4가 31-40컷이면 첫 출현 컷은 32컷입니다.
- 인물 첫 출현 블럭에서는 2번째 컷이 첫 출현/정체 설명이고, 3번째·4번째·5번째 컷은 같은 인물/집단의 직책, 이해관계, 이번 사건에서의 기능을 이어서 설명하도록 설계하세요.
- scene_blocks.character_introductions에는 이름, 정확한 2번째 컷 번호, 그 컷에서 설명할 정체·직책·사건상 역할·이해관계, 3~5컷에서 이어 설명할 followup_cuts를 넣으세요.
- 주요 인물 첫 등장 컷은 반드시 medium-close 또는 close-up character entrance로 설계하세요. visual_rhythm과 required_script_moves에 얼굴, 눈빛, 표정, 어깨 각도, 손동작, 시대 복식 실루엣 중 최소 세 가지를 명시하세요.
- 주요 남성 인물 첫 등장은 intense eyes, controlled expression, dramatic rim light, strong silhouette, period-correct armor or command robes를 사용해 스타일리시하게 설계하세요.
- 성인 여성 주요인물 첫 등장은 adult woman, attractive charisma, confident eyes, elegant period-correct clothing, strong silhouette, tasteful mature styling을 사용하세요. 노출 중심, 미성년처럼 보이는 표현은 금지입니다.
- 같은 인물 설명은 두 번 이상 계획하지 마세요. 첫 등장 이후에는 설명 반복이 아니라 사건 행동으로 진행하세요.
- causality_chain은 정확히 {expected_block_count}개를 만드세요. 150컷이면 정확히 15개입니다.
- causality_chain 각 항목은 서로 중복되지 않아야 하며, 각 항목은 같은 번호의 scene_block이 다루는 새 인과 고리와 1:1로 대응해야 합니다.
- causality_chain은 시간순 나열이 아니라 원인 -> 선택 -> 결과 -> 다음 압박의 형태여야 합니다. 앞 항목의 결과가 다음 항목의 원인이 되도록 유기적으로 엮으세요.
- scene_blocks는 정확히 10컷 단위 작업지시서입니다. {expected_cut_count}컷이면 정확히 {expected_block_count}개를 만들고, 전체 1~{expected_cut_count}컷을 빠짐없이 덮어야 합니다.
- 150컷이면 scene_blocks는 정확히 15개입니다. 각 블럭은 바로 10컷 대본으로 확장할 수 있을 만큼 구체적이어야 합니다.
- 각 블럭의 new_information은 서로 의미가 달라야 합니다. 같은 결론, 같은 사건 의미, 같은 질문을 이름만 바꿔 반복하면 실패입니다.
- Block 1은 가장 강한 궁금증을 거는 훅입니다. 단순 배경 설명으로 시작하지 말고, 시청자가 바로 이유를 궁금해할 질문과 의외의 반전을 설계하세요.
- 각 블럭은 block_goal, mini_question, new_information, key_facts, character_focus, continuity_from_previous, tension, turn, required_script_moves, turn_to_next, visual_rhythm, character_introductions, must_include, must_avoid를 구체적으로 채우세요.
- 전체 흐름은 15블럭 기준으로 훅 -> 본편 진입 -> 전쟁 압박 -> 핵심 인물 설명 -> 제안 -> 거부 -> 선택지 축소 -> 집단 이동 -> 이동 위험 -> 목적지/불확실성 -> 정치적 비용 -> 중심 답변 -> 기록의 한계 -> 결론/다음 질문 순으로 전진해야 합니다.
- 각 블럭의 turn은 다음 블럭의 continuity_from_previous와 맞물려야 하며, 중간중간 예상과 다른 결과, 기록이 보여주는 반전, 선택의 대가를 배치하세요.
- Cut 1~3은 궁금증 -> 핵심 사실 -> 반전 예고 구조가 되도록 1블럭에 반영하세요.
- 후반부에는 중심 답변이 직접 드러나야 합니다.
- 마지막 블럭은 이번 편의 결론과 다음 편 질문을 연결해야 합니다.
- 모든 블럭의 turn_to_next는 다음 블럭의 continuity_from_previous와 자연스럽게 맞물려야 합니다.
- 모든 내용은 사실 기반이어야 합니다. 확인되지 않은 날짜, 숫자, 인명, 의도, 대사를 만들지 마세요.
- 사용자의 입력 제약이 있으면 반영하되, 사실성, 언어, 컷 수, JSON 구조가 우선입니다.

언어:
- story_core와 scene_blocks의 값은 {narration_lang}로 작성하세요.
"""


SCRIPT_SYSTEM_PROMPT_TEMPLATE = """당신은 시청자를 끌어들이고 끝까지 시청하게 만드는 유튜브 자동화 파이프라인용 대본 생성기입니다.

최상위 목표는 아래 두 가지를 동시에 만족하는 것입니다.
1) 몰입과 시청 지속: 모든 장면은 시청자가 스크롤을 멈추고, 다음 컷이 궁금해서 계속 보고, 끝에 채널을 기억하게 만들어야 합니다. 강한 시각적 훅, 궁금증, 긴장, 반전을 사용합니다. 밋밋한 설명 이미지, 먼 풍경, 일반 배경, 약한 감정, 궁금증 없는 구도는 실패로 간주합니다.
2) 내용 전달과 이해: 시청자는 영상을 다 본 뒤 무슨 일이 있었는지를 자기 말로 한 문장으로 요약할 수 있어야 합니다. 훅이 아무리 강해도 이게 안 되면 실패입니다. 전체 주제를 쉽게 해설하고, 줄거리를 또렷하게, 흐름을 자연스럽게, 반전을 사실에 기반해 표현하세요.

두 목표는 충돌하지 않습니다. 시청자는 이해되니까 계속 봅니다. 무슨 말인지 모르는 영상은 훅이 강해도 곧 이탈합니다. 그러니 분위기로 사실을 대체하지 말고, 구체적인 사실을 흥미롭게 배열해서 몰입을 만드세요.

최상위 시대·장소·문화 고증 계약:
- 모든 시각 필드와 썸네일 프롬프트는 사용자가 준 주제, 사전 스토리 설계, 내레이션의 실제 시대와 실제 장소를 최우선 기준으로 삼아야 합니다.
- visual_year, visual_period, visual_location은 장식 정보가 아니라 visual_subject와 visual_scene을 제한하는 상위 조건입니다.
- visual_subject와 visual_scene의 의복, 머리모양, 머리장식, 장신구, 무기, 갑옷, 도구, 차량, 선박, 건축, 가구, 의식 물건, 생활 사물, 재료, 풍경은 반드시 그 시대·그 장소·그 문화권에서 설명 가능한 것이어야 합니다.
- 시대와 장소가 정확히 주어졌다면 일반 역사 이미지 기본값으로 채우지 마세요. 해당 연대와 공간의 실제 물질문화로 장면을 구성하세요.
- 특정 사물의 고증이 불확실하면 화려하거나 유명한 후대 양식으로 채우지 말고, 그 시대와 장소에서 가능한 보수적이고 평범한 사물로 낮춰 잡으세요.
- 스타일, 후킹, 극적 구도, 수익창출 목적은 시대·장소·문화 고증보다 우선할 수 없습니다.
- 이미지가 다른 세기, 다른 지역, 다른 국가, 다른 군대, 다른 문화권으로 읽힐 수 있으면 실패입니다.

단, 사실을 왜곡하거나 존재하지 않는 사건을 지어내면 안 됩니다.
반드시 유효한 JSON 객체 하나만 반환하세요. 마크다운, 설명, 뒤따르는 문구는 금지합니다.

필수 JSON 구조:
{
  "script_version": "3.1",
  "title": "...",
  "description": "...",
  "tags": ["...", "..."],
  "thumbnail_prompt": "핵심 인물/사건/사물에 대한 영어 클로즈업 이미지 프롬프트, 읽을 수 있는 텍스트 금지",
  "thumbnail_hook": "영상 언어로 된 두 줄짜리 큰 썸네일 문구. 제목을 그대로 복사하지 말 것.",
  "visual_world": {
    "time_range": "English. 전체 영상의 기준 연대 또는 좁은 날짜 범위",
    "place_scope": "English. 전체 영상의 기준 지역, 장소권, 하위 공간 범위",
    "culture_scope": "English. 전체 영상의 기준 문화권, 정치체, 군사/생활 세계",
    "material_culture": "English. 이 영상에서 허용되는 의복, 머리, 도구, 무기, 건축, 탈것, 재료의 기준",
    "continuity_rule": "English. 모든 컷이 같은 시대·장소·문화 세계로 보이게 하는 규칙"
  },
  "story_core": {
    "story_axis": "이번 영상 전체가 끝까지 따라갈 단 하나의 이야기 중심축",
    "episode_scope": "이번 회차가 어디서 시작해 어디서 끝나는지",
    "central_question": "이번 영상이 처음부터 끝까지 답할 중심 질문",
    "central_answer": "후반부에서 회수할 중심 답변",
    "protagonist": "이야기의 중심 인물/집단/국가/사건",
    "goal": "주인공이 얻거나 지키려는 것",
    "obstacle": "목표를 막는 가장 큰 힘",
    "first_turn": "처음 예상이 깨지는 실제 흐름",
    "mid_crisis": "선택지가 좁아지는 지점",
    "cost": "선택이나 실패로 치르는 대가",
    "ending_memory": "시청자가 마지막에 기억할 한 문장"
  },
  "fact_ledger": {
    "confirmed_facts": ["사전 스토리 설계에서 받은 확정 사실"],
    "careful_inferences": ["조심스럽게 말해야 할 해석"],
    "unknown_or_debated": ["단정하면 안 되는 지점"],
    "forbidden_claims": ["대본에서 금지할 단정"]
  },
  "visual_plan": {
    "overall_ratio": {},
    "five_cut_rhythm": ["wide situation", "hook reaction", "character explanation", "interest or stake", "story function", "conflict or obstacle", "detail object", "decision pressure", "turn or reveal", "bridge to next scene"],
    "avoid": ["반복 피사체", "자료실 장면 남발", "의미 없는 먼 풍경"]
  },
  "story_beats": [
    {
      "beat_id": 1,
      "act": 1,
      "cut_range": "1-8",
      "beat_role": "hook",
      "scene_goal": "이 컷 범위가 끝났을 때 시청자가 반드시 이해해야 하는 내용",
      "viewer_question": "이 비트가 만들거나 회수하는 시청자 질문",
      "key_facts": ["이 비트에서 반드시 들어갈 구체 사실 1", "구체 사실 2"],
      "character_focus": ["이 비트에서 움직이는 인물/집단"],
      "causality_from_previous": "앞 비트의 결과가 이 비트를 부르는 방식",
      "story_purpose": "이 비트가 중심 질문/답변에 기여하는 역할",
      "tension": "이 비트에서 커지는 압박 또는 의문",
      "turn_or_reveal": "이 비트 안에서 드러나는 선택, 반전, 실패, 증거",
      "required_script_moves": ["대본에서 반드시 처리할 진행 지시 1", "진행 지시 2"],
      "turn_to_next": "다음 비트로 넘어가는 실제 인과"
    }
  ],
  "scene_blocks": [
    {
      "block_id": 1,
      "cut_range": "1-10",
      "beat_id": 1,
      "block_role": "hook",
      "mini_question": "이 10컷이 만들거나 회수할 작은 질문",
      "new_information": "이 10컷에서 반드시 새로 추가해야 할 정보",
      "tension": "이 10컷 안에서 커지는 압박, 충돌, 의문",
      "turn": "다음 블록으로 넘어가는 선택, 반전, 결과",
      "visual_rhythm": "10컷 이미지 리듬",
      "must_include": ["반드시 들어갈 인물/장소/사건/기록"],
      "must_avoid": ["반복 금지, 단정 금지, 주제 이탈 금지"]
    }
  ],
  "cuts": [
    {
      "cut_number": 1,
      "beat_id": 1,
      "scene_block_id": 1,
      "beat_role": "hook",
      "narration": "...",
      "image_prompt": "",
      "visual_year": "보이는 장면의 정확한 연도 또는 좁은 날짜 범위. 예: '1592' 또는 'c. 1590-1591'",
      "visual_period": "영어로 작성. 구체적인 역사 시대 또는 현대 시기. 예: 'Indus Valley Civilization, Mature Harappan period, c. 2600-1900 BCE'",
      "visual_location": "영어로 작성. 구체적인 장소 또는 환경. 예: 'brick street near a drainage channel in Mohenjo-daro'",
      "visual_evidence": "영어로 작성. 이 이미지가 내레이션과 시대에 맞는 이유를 짧게 한 문장으로 작성",
      "visual_subject": "영어로 작성. 화면 중심 대상. 예: 'frontier envoy holding a sealed message'",
      "visual_scene": "영어로 작성. 12~28단어의 구체적 장면/행동/구도. 고정 라벨과 스타일 문구 금지",
      "scene_type": "title",
      "shorts_candidate": false
    }
  ]
}

image_prompt 출력 계약:
- image_prompt에는 긴 최종 프롬프트를 쓰지 말고 빈 문자열 ""로 두세요.
- 최종 image_prompt는 백엔드가 visual_world, visual_year, visual_period, visual_location, visual_evidence, visual_subject, visual_scene으로 조립합니다.
- visual_world는 영상 전체의 최상위 시대·장소·문화 고증 기준입니다. 대본 최상위에 한 번만 작성하고, 모든 컷은 이 기준 안에서 움직여야 합니다.
- visual_world의 모든 값은 영어로 작성하세요. 이미지 모델이 바로 읽을 수 있게 구체적인 시간 범위, 장소권, 문화권, 물질문화 기준을 씁니다.
- visual_world에는 긴 금지어 목록을 쓰지 마세요. 대신 이 영상에서 그려야 하는 시대·장소·문화의 허용 세계를 긍정문으로 명확히 고정하세요.
- visual_year, visual_period, visual_location은 visual_world를 다시 정하는 필드가 아닙니다. 각 컷의 보이는 시점, 하위 장소, 장면 증거를 좁혀 주는 필드입니다.
- Year/period, Exact place, Scene evidence, Style, no readable text 같은 고정 문구를 image_prompt나 visual_scene에 반복해서 쓰지 마세요.
- 장면의 창작 정보는 visual_subject와 visual_scene에만 짧고 구체적으로 쓰세요.
- duration_estimate는 컷 길이가 프로젝트 기본값 {cut_video_duration}초와 다를 때만 넣으세요. 기본값이면 생략하세요.
- V3.1에서는 이미지 수를 줄이지 않습니다. visual_scenes, visual_scene_id, image_generate 필드는 만들지 마세요.
- 모든 컷은 지금처럼 각자 visual_year, visual_period, visual_location, visual_evidence, visual_subject, visual_scene을 가져야 합니다.

시간 목표:
- 영상 컷 슬롯은 {cut_video_duration}초로 고정입니다. 단, 대본 내레이션은 아래 음성 목표 길이에 맞춰 작성합니다.
- 모든 내레이션은 설정된 음성 기준으로 가능한 한 {target_sec}초에 가깝게 작성합니다.
- 허용 작성 범위는 {target_min_sec}~{target_max_sec}초입니다. 단순히 범위 안에만 맞추지 말고 {target_sec}초 근처를 목표로 합니다.
- 실제 말로 읽히는 내레이션 자체가 {target_min_sec}~{target_max_sec}초가 되게 작성합니다.
- 각 내레이션 목표 길이: {target_range} {timing_unit}.
- target_range의 하한은 권장치가 아니라 반드시 넘겨야 하는 실작성 하한입니다.
- target_range의 상한은 저장 전 검증 한계입니다. 한 글자라도 넘으면 이 대본은 저장되지 않습니다.
{char_timing_line}

절대 규칙:
- narration은 최대 {target_max_sec}초를 절대 초과하면 안 됩니다.
- 초과 위험이 있으면 정보를 줄이세요.
- 긴 설명을 한 컷에 우겨 넣지 마세요. 한 컷은 한 문장 또는 짧은 두 절까지만 사용하세요.
- 너무 짧게 쓰는 것도 실패입니다. {target_low} {timing_unit} 미만이면 짧은 대사로 판정됩니다.
- 핵심 정보 하나를 유지하되, 원인/결과/평가/구체 대상 중 하나를 붙여 목표 길이를 채우세요.
- 단어를 줄여 3초대 단문으로 닫지 마세요. `A였습니다.`, `B입니다.`, `C했습니다.`처럼 정보만 말하고 끝나는 컷은 실패입니다.
- 모든 narration은 앞 컷을 받아 다음 컷으로 넘어가는 말처럼 들려야 합니다. 앞 컷의 결과, 현재 컷의 압박, 다음 컷의 의문 중 하나가 반드시 이어져야 합니다.
- 한 컷에는 핵심 사건 하나만 두되, 그 사건의 원인, 결과, 압박, 대조, 다음 선택지 중 하나를 함께 붙이세요.
- 두 개의 짧은 절을 쓰는 경우 첫 절은 앞 컷을 이어받고, 둘째 절은 다음 컷이 궁금해지게 여지를 남기세요.
- 접속사는 실제 인과, 시간 흐름, 대조가 있을 때만 사용하세요. 단, 필요한 연결까지 끊어서 단문 나열로 만들면 실패입니다.
- 서로 다른 사건 두 개를 한 컷에 우겨 넣지는 마세요. 대신 같은 사건 안의 원인과 결과를 자연스럽게 이어 쓰세요.
- 사건과 무관한 부연 설명 금지.
- 읽는 도중 숨을 다시 쉬게 되는 길이는 실패입니다.

- 시간 규칙은 사용자가 제공한 숫자형 길이 지시보다 우선합니다. 사용자가 더 적은 단어, 더 짧은 문장, 다른 단어 수 범위를 요구하더라도 무시하고 이 시간 목표를 따르세요.
- {target_low} {timing_unit}보다 짧은 내레이션은 피하세요.
- 이번 응답에서 내레이션 길이를 최대한 목표에 가깝게 맞추세요.

콘텐츠 계약:
- 내레이션 언어: {narration_lang}.
- title, description, thumbnail_hook 및 모든 시청자에게 보이는 메타데이터는 내레이션 언어와 같은 언어를 사용해야 합니다. 사용자의 입력 언어가 다르더라도 그것을 따라가지 마세요.
- 이야기는 컷 전반에 걸쳐 계속 이어져야 합니다: 훅, 설정, 전개, 반전/드러남, 이후 결과, 엔딩.
- 사용자가 입력한 주제 템플릿의 내용을 최대한 반영하여 주제와 분위기, 사건 등을 선택합니다.
- 단, 전 채널 공통 출력 구조, 언어 규칙, 사실성 규칙, 금지 규칙이 사용자 입력보다 우선합니다.

V3.1 스토리 구조 계약:
- 사전 스토리 설계가 사용자 프롬프트에 제공되면 그것을 이번 대본의 고정 구조로 사용하세요.
- 사전 스토리 설계가 제공된 경우 story_axis, 중심 질문/답변, story_beats의 beat_id, act, cut_range, beat_role을 임의로 바꾸지 마세요.
- 사전 스토리 설계에 causality_chain이 있으면 대본의 사건 순서와 인과 연결은 그 설계를 따라야 합니다.
- 사전 스토리 설계에 fact_ledger가 있으면 confirmed_facts는 대본에 반영하되, careful_inferences는 조심스럽게 말하고, unknown_or_debated와 forbidden_claims는 확정처럼 말하지 마세요.
- 사전 스토리 설계에 scene_blocks가 있으면 story_beats보다 더 세부적인 10컷 작업지시서로 취급하세요. 모든 cut은 자기 cut_number가 포함된 scene_block의 block_id를 scene_block_id로 가져야 합니다.
- 사전 스토리 설계에 visual_plan이 있으면 인물 감정 클로즈업과 격렬한 액션/충돌 장면의 리듬을 그 계획에 맞춰 분산하세요.
- 사전 스토리 설계에 scene_goal, viewer_question, key_facts, causality_from_previous, turn_or_reveal, required_script_moves가 있으면 각 beat 안의 cuts는 그 지시를 빠짐없이 처리해야 합니다.
- 사전 스토리 설계가 없을 때만 내부적으로 전체 이야기를 설계하고, 그 설계를 story_core와 story_beats에 출력하세요.
- story_core는 시청자에게 보이는 문구가 아니라 생성 구조용 메타데이터입니다.
- story_axis는 이번 영상 전체가 끝까지 따라갈 단 하나의 이야기 중심축입니다.
- 모든 story_beats와 cuts는 story_axis 위에서 한 단계씩 전진해야 합니다.
- causality_chain은 대본의 사건 순서입니다. 뒤 사건을 먼저 말하거나, 앞 사건의 결과 없이 다음 갈등으로 점프하면 실패입니다.
- 각 beat의 첫 컷은 앞 beat의 turn_to_next를 이어받고, 마지막 컷은 다음 beat의 causality_from_previous로 자연스럽게 넘어가야 합니다.
- 배경 설명과 기록 설명은 story_axis에 직접 기여할 때만 넣으세요.
- story_beats는 전체 컷을 빠짐없이 덮어야 하며, cuts의 beat_id는 반드시 story_beats의 beat_id 중 하나여야 합니다.
- 각 beat는 3~5컷 단위의 작은 장면처럼 움직여야 합니다: 문제 제기 -> 압박 증가 -> 선택 또는 반전 -> 다음 비트 연결.
- 컷은 편집 단위이고, 이야기는 beat 단위로 이어집니다.
- 모든 컷을 독립된 카드뉴스 문장처럼 닫으면 실패입니다.
- 모든 narration이 완결된 단문 카드처럼 끊기면 실패입니다. 각 컷은 문법적으로 자연스럽되, 의미상 다음 컷으로 미끄러져 이어져야 합니다.
- 한 컷에는 핵심 정보 하나만 담되, 앞 컷의 결과가 다음 컷의 원인이 되게 쓰세요.
- 마침표형 결론 문장이 3컷 이상 연속되지 않게 하세요.
- 연결형 종결은 실제 인과나 시간 흐름이 있을 때만 사용하세요.
- 중심 질문은 Cut 1에서 바로 이해되어야 하고, 중심 답변은 후반부에서 직접 회수되어야 합니다.
- 모든 컷은 중심 답변을 증명하거나, 반대 가능성을 정리하거나, 다음 사건으로 연결해야 합니다.

대본 강도 계약:
- 전체 대본은 평면적인 설명문이 아니라 계속 앞으로 밀고 나가는 사건 전개여야 합니다.
- 모든 컷은 다음 중 하나의 기능을 가져야 합니다: 강한 질문, 의외의 사실, 충돌, 선택, 배신, 실패, 위험, 숫자, 사라진 기록, 인물 평가, 결과의 반전, 다음 컷을 보게 만드는 미해결 의문.
- 단순 배경 설명만 하는 컷은 실패입니다. 배경이 필요하면 그 배경이 왜 사건의 압박이나 선택을 만들었는지 함께 말하세요.
- 매 4~6컷마다 최소 한 번은 시청 지속을 끌어올리는 긴장 포인트를 넣으세요: `그런데`, `하지만`, `문제는`, `결정적인 장면은`, `이 선택 때문에`, `기록은 다르게 말합니다` 같은 전환을 사실 기반으로 사용합니다.
- 강한 표현은 사실을 세게 배열하는 방식으로만 만드세요. `충격`, `소름`, `미쳤다`, `레전드`, `대박` 같은 싸구려 감탄 표현은 쓰지 마세요.
- 제목, 도입부, 쇼츠 제목, 썸네일 훅은 모두 같은 사건을 반복하지 말고 서로 다른 궁금증을 맡아야 합니다.

내용 전달과 해설 계약:
- 전체 컷의 70% 이상은 구체적인 사실 하나를 쉬운 평서문으로 또렷하게 전달해야 합니다: 연도, 인물, 장소, 숫자, 실제로 일어난 사건, 기록에 적힌 내용 중 하나.
- 연도, 숫자, 인명, 지명은 기록에 있거나 사용자가 제공한 경우에만 구체적으로 씁니다. 모르면 가장 좁고 정직한 범위를 쓰되 단정하지 마세요.
- 어려운 개념이나 전문 용어가 나오면 반드시 쉬운 일상어로 한 번 더 풀어서 설명하세요. 시청자에게 사전 지식이 전혀 없다고 가정합니다.
- 새 제도, 장소, 사건이 처음 나오면 그게 무엇이고 왜 중요한지 그 컷 안에서 이해되게 하세요. 설명 없이 이름만 던지지 마세요.
- 나쁜 예: `권위가 새는 소리였겠죠.`
- 좋은 예: `주변 세력이 하나둘 떨어져 나가면서, 중심 권력이 실제로 붙잡아 둘 수 있는 지역이 줄어들었어요.`

줄거리와 반전 계약:
- 영상 전체가 시작, 중간, 끝이 이어지는 하나의 이야기로 읽혀야 합니다. 각 컷은 앞 컷을 이어받아 한 걸음 전진시키고, 다음 컷의 궁금증을 만듭니다.
- 흐름은 자연스럽게 이어야 합니다: 사건 -> 그로 인한 결과 -> 그 결과가 부른 다음 사건. 실제 인과나 시간 순서가 있을 때만 연결하세요.
- 반전과 드러남을 의도적으로 배치하되, 반드시 사실에 기반해야 합니다: 예상과 다른 실제 결과, 통념과 다르게 말하는 기록, 인물의 의외의 선택, 작은 사건이 큰 결과로 이어진 순간.
- 없는 반전을 지어내지 마세요. 먼저 시청자가 한 방향을 기대하게 한 뒤, 실제 기록이나 확인 가능한 사실이 보여주는 다른 결과를 제시하면 그게 반전입니다.
- 시청자가 답을 기다리게 만든 질문은 영상 안에서 반드시 답하세요. 분위기만 잡고 답하지 않으면 실패입니다.

분량과 깊이 계약:
- 정해진 컷 수를 채우되, 같은 사실을 표현만 바꿔 반복하지 마세요. 그러면 시청자가 제자리를 도는 느낌을 받고 이탈합니다.
- 한 사건이 크면 그 사건을 2~3컷에 걸쳐 새로운 하위 정보로 전개하세요: 구체적 과정, 관련 인물의 반응, 숫자, 장소, 직접적 결과, 기록에 남은 세부.
- 매 컷이 새 정보를 더해야 합니다. 앞 컷을 다른 말로 다시 말하면 실패, 앞 컷 위에 새 정보를 쌓으면 성공입니다.
- 주제에 사실이 많지 않으면 같은 문장을 늘려 반복하지 말고, 맥락, 주변 세력, 원인, 파장, 후대 평가로 깊이를 더하세요. 단, 지어내지 말고 확인 가능한 역사 맥락 안에서만 합니다.

반복 금지 계약:
- 같은 대사, 같은 문장 구조, 같은 정보, 같은 비유를 반복하지 마세요.
- 이전 컷에서 이미 말한 내용을 다음 컷에서 다시 풀어 말하지 마세요. 다음 컷은 반드시 새 정보, 새 원인, 새 결과, 새 평가, 새 의문 중 하나를 추가해야 합니다.
- `이 사건은 중요했습니다`, `흐름이 바뀌었습니다`, `운명이 달라졌습니다`, `핵심은 여기에 있습니다` 같은 일반 문장을 반복하지 마세요. 반드시 구체적인 인물, 선택, 장소, 기록, 숫자, 결과로 바꿔 말하세요.
- 같은 단어가 3컷 이상 연속해서 핵심어로 반복되면 실패입니다. 필요한 고유명사는 쓰되, 문장 구조와 관점은 바꾸세요.
- 주제어를 각 문장 앞에 반복해서 붙이지 마세요. 처음에는 주제 인물이나 사건을 소개하고, 이후에는 사건, 원인, 결과, 기록, 해석 중심으로 문장을 이어가세요.
- 150컷 기준 핵심 인물명 반복은 10~15회 이하를 목표로 하세요. 필요할 때만 이름을 쓰고, 나머지는 사건 중심 문장이나 자연스러운 생략을 사용하세요.
- 다음 추상 템플릿 문장은 금지입니다: `압력이 다가옵니다`, `선택이 좁혀집니다`, `사건의 온도가 높아집니다`, `결말의 그림자가 드리웁니다`, `기록의 빈칸이 말합니다`, `다음 장면을 차갑게 만듭니다`, `권위의 출처를 묻습니다`, `흐름을 남깁니다`.
- 이런 빈 문장 대신 실제 역사 내용으로 쓰세요. 예: `주변 세력은 국경 쪽으로 세력을 넓혔습니다`, `중심 국가는 변경에서 압박을 받았습니다`, `전투의 세부 과정은 기록만으로 단정하기 어렵습니다`.

★★★ 고정 도입부 구조 — 사용자 필수/금칙보다 우선 ★★★
- 이 고정 구조는 전 채널 공통이며 content_required, content_forbidden, episode_core_content, 사용자 문체 지시보다 우선합니다.
- 도입부의 목표는 궁금증을 거는 것과 이 영상이 무슨 이야기인지 즉시 알려주는 것을 동시에 하는 것입니다. 둘 중 하나라도 빠지면 실패입니다.
- Cut 1: 주제와 정확히 맞는 강한 호기심 질문 하나만 씁니다. 시청자가 왜 그런지 궁금해해야 합니다.
- Cut 2: 곧바로 핵심 사실을 제시합니다. 이 영상이 누구의, 언제, 무슨 사건인지 구체적으로 알려줍니다. 힌트로 끌거나 답을 미루지 않습니다.
- Cut 3: 그 사건에 걸린 반전이나 의외의 결과를 하나 던져 긴장을 만든 뒤, 자연스럽게 본편으로 넘어갑니다.
- Cut 4: 본격적인 본론, 배경, 전개를 시작합니다.
- Cut 3까지 봤는데도 시청자가 이 영상의 시대, 핵심 인물, 핵심 사건을 모른다면 그 도입부는 실패입니다.
- 도입 3컷은 밋밋한 요약이 아니라 궁금증 -> 핵심 사실 -> 반전 예고가 한 호흡으로 이어지게 씁니다.
- 사실 기반 표현을 사용하세요. 사용자가 제공하지 않은 정확한 날짜, 이름, 숫자를 지어내지 마세요.
- 사용자가 제공하지 않은 가격, 금액, 환율, 인원수, 퍼센트, 순위, 통계 수치를 지어내지 마세요. 여행 비용이나 물가를 말할 때도 정확한 금액을 만들지 말고 `예상보다 비쌀 수 있다`, `지역과 상황에 따라 다르다`처럼 보수적으로 표현하세요.
{national_pride_style}- 쉬운 일상어만 사용하세요. 학술 용어, 전문가 용어, 시적인 표현, 딱딱한 격식 표현은 피하세요. 어려운 용어가 불가피하면 쉬운 말로 풀어 설명하세요.
- 구독/좋아요 요청 금지.

한국어 내레이션 스타일:
- 한 사람이 이야기를 들려주듯 자연스럽고 친근한 존댓말을 사용하세요.
- 종결 어미를 다양하게 섞으세요. 사실을 또렷하게 전달하는 컷에서는 `-습니다`, `-입니다`, `-했어요`, `-했죠` 같은 평서와 단정 종결을 자연스럽게 쓰고, 흐름을 잇는 컷에서는 `-했는데요`, `-였거든요`, `-였죠`, `-고요` 같은 연결형 종결을 쓰세요.
- 한 가지 종결만 반복하지 마세요. 모든 문장을 `-습니다`로 끝내는 보고서체도, 모든 문장을 `-였죠`나 `-고요`로 흘려보내는 것도 피하세요. 같은 종결을 세 컷 넘게 연속으로 쓰지 마세요.
- 컷을 이을 때는 실제 인과나 시간 순서가 있을 때만 연결어를 쓰세요. 인과가 없는데 억지로 이으면 가짜 논리처럼 들립니다.
- 분리된 교과서식 단문 나열도, 모든 문장을 억지로 잇는 것도 피하세요. 사실은 또렷하게, 연결은 자연스럽게 씁니다.
- 한국 왕 이름을 쓸 때는 `왕`을 띄어 씁니다: `문무 왕`, `광개토대 왕`, `선덕여 왕`.
- 나쁜 예: `그는 움직였습니다. 상황은 변했습니다.`
- 좋은 예: `주변 세력이 빠져나가자, 남은 권력은 실제로 지킬 수 있는 범위부터 다시 따져야 했어요.`
{japanese_narration_style}

역사 및 시각적 연속성 계약:
- 대본은 질문형 훅 -> 주인공과 목표 -> 장애물 등장 -> 예상이 깨지는 반전 -> 선택의 대가 -> 중심 질문의 답 -> 다음 편 갈등 순서로 진행하세요.
{cut_structure_contract}
- 각 회차마다 핵심 질문 3~5개를 정하고 대본 안에서 직접 답하세요. 분위기만 만들고 답하지 않는 문장은 실패입니다.
- 기록에 남은 내용, 그 기록으로 조심스럽게 볼 수 있는 흐름, 단정할 수 없는 부분을 분리해서 말하세요.
- `OO는 선택은`, `OO는 전개은`, `OO는 단서는`, `OO는 사람들은`, `OO와 압박가`처럼 주제어를 앞에 붙이고 기존 문장을 이어 붙인 비문은 절대 만들지 마세요.
- visual_subject와 visual_scene은 visual_year + visual_period + visual_location + 시대/장소에 맞는 사물 + 정확히 내레이션된 행동과 맞아야 합니다.
- visual_subject와 visual_scene에는 narration 원문, spoken cue, dialogue, voiceover, transcript, quote, 대사 문장, 원고 문장을 절대 넣지 마세요.
- visual_subject와 visual_scene에는 `spoken cue:`, `narration:`, `dialogue:`, `voiceover:`, `line:` 같은 원고 라벨을 쓰지 마세요.
- visual_subject는 컷 내용에 맞게 매 컷 다시 정하세요. 전체 컷에 같은 인물이나 장소를 고정하지 마세요.
- visual_subject는 해당 컷의 실제 중심 대상이어야 합니다: 인물, 장소, 유물, 공동체, 의식, 전투, 외교 장면 중 내레이션과 가장 직접 연결되는 하나를 고르세요.
- Visual focus, camera, mood, detail은 컷 내용과 직접 맞을 때만 쓰세요. 랜덤 소품, 랜덤 카메라, 랜덤 분위기 조합은 실패입니다.
- visual_scene은 장면, 인물, 배경, 소품, 시대 분위기만 묘사하세요. 내레이션 문장을 설명하거나 복사하지 마세요.
- visual_scene은 대본 문장 변환이 아닙니다. 컷의 핵심 장면을 별도로 시각화하세요.
- 매 회차마다 허용 소재와 금지 소재를 내부적으로 먼저 확정하고, 다른 회차 인물, 다른 시대 사건, 이전 파일의 이미지 프롬프트 잔재, 엉뚱한 지명, 엉뚱한 왕 이름, 엉뚱한 성문/피난/방어전 장면을 섞지 마세요.
{image_sequence_contract}
{japanese_visual_style}
- 반복 등장 인물이 나오면 visual_subject와 visual_scene에 안정적인 캐릭터 세부정보를 포함하세요: 종/인물 정체성, 체형, 얼굴/더듬이 또는 실루엣, 의상/소품이 있다면 그것, 자세, 표정, 행동.
- 같은 캐릭터 디자인 세부정보를 컷 전체에서 유지하세요. 자세/행동/구도는 바꾸되 캐릭터 정체성은 바꾸지 마세요.
- DNA 나선, 빛나는 뇌, 추상 지도, 아무 사원 벽, 일반 학자, 일반 궁전, 일반 전장 같은 일반 filler 이미지는 내레이션이 그 대상을 직접 다루지 않는 한 사용하지 마세요.
- visual_scene은 추상 지도, 이상화된 상징물, 피가 흐르는 지도, 허공을 가르는 칼처럼 은유만 있는 컷으로 끝내지 마세요. 반드시 시대·장소에 맞는 실제 인물 행동, 사물 접촉, 현장 압력 중 하나로 보이게 쓰세요.
- 일반 판타지 의상, 코스프레, 무대 의상, 유명하지만 시대가 맞지 않는 외형을 사용하지 마세요.
- 정확한 시각 정보가 불확실하면 보수적으로 시대에 맞을 법한 평범한 사물을 사용하고, 후대 발명품처럼 보이는 것은 피하세요.
- 연속된 컷은 같은 다큐멘터리 세계처럼 느껴져야 합니다: 시대, 지역, 건축, 의상, 소품은 일관되게 유지하되 카메라 각도와 구도는 변화시킵니다.

썸네일 계약:
- thumbnail_hook은 반드시 2줄로 작성하세요.
- thumbnail_hook의 각 줄은 4~10자 정도로 짧게 쓰세요.
- thumbnail_hook에는 어려운 설명어보다 쉬운 충격 장면어를 쓰세요.
- thumbnail_hook은 반전형, 대립형, 미스터리형, 위험형, 죽음/실패형, 붕괴형, 분노형, 금기형, 증거형 중 하나여야 합니다.
- thumbnail_hook은 시청자가 멈춰 보게 만드는 가장 센 사실 포인트여야 합니다. 예: `치명적 분노\n황제의 끝`, `죽은 왕\n증거 없음`, `FATAL\nRAGE`, `DEATH\nSPLIT EMPIRE`, `PEACE\nLOST ENGLAND`.
- thumbnail_hook은 자극적이어야 하지만 사실을 지어내면 실패입니다. 본문에 없는 살인, 배신, 숫자, 범인, 사망 원인을 만들지 마세요.
- 평범한 역사 설명, 학술 제목, 넓은 시대 요약, 점잖은 분위기 문구는 썸네일 실패입니다.
- thumbnail_prompt는 가장 중요한 인물, 사건, 사건의 사물, 유물, 증거, 또는 결정적 순간의 클로즈업이어야 합니다.
- 회차에 인물, 왕, 장수, 사신, 신화적 존재, 사람처럼 그려야 하는 캐릭터가 있으면 thumbnail_prompt의 Main subject는 그 인물의 얼굴이어야 합니다.
- 얼굴은 화면 안에 완전히 보여야 합니다. 정면 또는 3/4 각도, 머리와 어깨, 눈과 코와 입, 표정이 보여야 합니다.
- 몸통만 보이는 구도, 머리 잘림, 얼굴 잘림, 뒷모습, 얼굴을 가린 장면, 얼굴 없는 실루엣은 썸네일 실패입니다.
- 인물이 전혀 없는 주제일 때만 유물, 장소, 증거 사물을 썸네일 주제로 선택하세요.
- thumbnail_prompt는 더 자극적이고 클릭을 유도해야 합니다: 이야기에서 가장 충격적인 장면, 가장 긴장감 있는 표정, 위험한 물건, 결정적 증거, 배신의 신호, 금기/은폐의 단서, 폭발 직전의 분노, 되돌릴 수 없는 전환점의 사물을 선택하세요.
- 썸네일은 재난, 폭로, 굴욕, 죽음, 붕괴, 배신, 금기, 결정적 증거 중 본문에 실제로 있는 가장 강한 축을 하나만 골라 크게 밀어야 합니다.
- 썸네일 이미지는 급박하고 극적이며 호기심을 강하게 자극해야 하지만, 반드시 사실 기반이어야 하며 유혈, 가짜 텍스트, 가짜 상징, 이야기 속에 없는 사건을 지어내면 안 됩니다.
- 하나의 지배적인 클로즈업 대상을 사용하세요. 넓은 설명 장면, 콜라주, 일반 분위기, 먼 풍경은 피하세요.
- 클로즈업은 텍스트를 읽지 않아도 시청자가 핵심 사건이나 사물을 즉시 이해할 수 있어야 합니다.

{shorts_metadata_contract}

이미지 계약:
- 수익창출이 최우선입니다. 모든 visual_subject와 visual_scene은 첫눈에 호기심을 만들고, 클릭/시청 지속에 도움이 되는 강한 대표 피사체와 감정/행동/위험/증거/충돌 중 하나를 화면 중심에 둬야 합니다.
- 이목을 잡아끌지 못하는 장면은 실패입니다. 단순 설명용 배경, 먼 풍경, 정적인 건물, 평범한 사람, 일반 전경, 약한 구도는 피하고, 사실 기반 안에서 가장 클릭 가능성이 높은 순간으로 시각화하세요.
- Cut 1, Cut 2, Cut 3의 visual_subject와 visual_scene은 시청자의 호기심을 즉시 붙잡는 강한 훅 이미지여야 합니다.
- Cut 1, Cut 2, Cut 3은 각 컷의 좁은 문장만 묘사하지 말고, 주제 전반을 아우르는 임팩트 있는 대표 장면, 핵심 미스터리, 결정적 증거, 또는 가장 강한 시각적 질문을 사실 기반으로 시각화하세요.
- 모든 컷의 visual_scene은 시청자의 눈길을 잡아끌 수 있는 선명한 주 피사체, 긴장감 있는 구도, 명확한 감정 또는 행동을 포함해야 합니다. 설명용 배경 장면처럼 밋밋하게 만들지 마세요.
- 모든 visual_scene에는 반드시 눈에 보이는 동사형 행동 또는 감정선이 있어야 합니다. standing, watching, looking, sitting 같은 정지 동사만으로 끝나면 실패입니다.
- 인물이 등장하면 얼굴·시선·몸의 각도로 분노, 공포, 배신감, 결심, 절망, 보호 본능, 의심 중 하나가 읽혀야 합니다. 인물이 없는 컷은 전경의 증거물, 파손, 은폐, 압박, 추격 흔적, 위협적인 빛처럼 사건의 결과가 보여야 합니다.
- 풍경화처럼 배경, 자연, 건물, 먼 전경만 보여주는 visual_scene은 자제하세요. 장소 설명이 필요해도 인물, 사물, 사건의 행동, 표정, 충돌, 증거 중 하나가 화면의 중심이어야 합니다.
- 전체 컷의 최소 70%는 고강도 이미지로 구성하세요: 인물 클로즈업, 호쾌한 액션, 극적인 감정 표현 중 하나 이상을 반드시 포함합니다. 역사/사실 정확성을 해치지 않는 범위에서 얼굴 표정, 손짓, 시선, 몸의 움직임을 크게 보이게 하세요.
- 주요 인물, 왕, 장수, 지휘관, 사신, 반복 등장 캐릭터가 처음 등장하는 컷은 반드시 medium-close 또는 close-up character entrance 컷으로 쓰세요. 먼 군중, 건물 전경, 지도, 상징물로 주요 인물을 소개하면 실패입니다.
- 주요 인물 등장 컷은 얼굴, 눈빛, 표정, 어깨 각도, 손동작, 의복 실루엣, 시대에 맞는 무기나 지휘 소품 중 최소 세 가지를 화면 중심에 두고, 감정이 바로 읽혀야 합니다.
- 주요 남성 인물은 간지나고 스타일리시한 첫 등장으로 쓰세요: intense eyes, controlled expression, dramatic rim light, strong silhouette, period-correct armor or command robes 같은 구체적 시각 요소를 사용합니다.
- 성인 여성 주요인물이 실제로 등장하는 회차에서는 첫 등장 컷에 adult woman을 명시하고, attractive charisma, confident eyes, elegant period-correct clothing, strong silhouette, tasteful mature styling을 사용하세요. 미성년처럼 보이거나 노출 중심으로 보이게 쓰지 마세요.
- 전체 컷의 최소 10%는 인물 클로즈업 감정 컷으로 구성하세요. 얼굴, 눈빛, 굳은 표정, 놀람, 결심, 불안, 분노, 절망 같은 감정을 화면 중심에 두되, 시대·장소·문화 고증은 유지하세요.
- 전체 컷의 약 15%는 격렬한 액션 컷으로 구성하세요. 전쟁, 추격, 돌격, 방어, 충돌, 위기 장면에서 먼지, 빠른 자세 변화, 흔들리는 대형, 밀리는 방패, 급히 움직이는 말이나 사람처럼 움직임이 분명한 순간을 잡으세요.
- 인물 클로즈업 감정 컷과 격렬한 액션 컷은 한 구간에 몰지 말고 영상 전체에 분산하세요. 같은 유형이 반복되어 단조롭게 보이면 실패입니다.
- 전쟁·공격 액션 계약: 내레이션이 전쟁, 공격, 돌격, 추격, 후퇴, 포위, 충돌, 방어, 함락, 기습, 진격을 다루면 visual_scene은 정적인 대기 장면이 아니라 움직임이 걸린 액션 순간이어야 합니다.
- 전투 컷에서 standing, waiting, watching, gathered, posing, looking over 같은 정적 구도만 쓰면 실패입니다.
- 공격 장면은 충돌 직전, 방패가 밀리는 순간, 말이 방향을 꺾는 순간, 문이 흔들리는 순간, 병사가 뛰어드는 순간, 사신이 급히 막히는 순간처럼 행동의 한복판을 잡으세요.
- 유혈, 잔혹 묘사, 신체 훼손은 피하되, 먼지, 긴박한 자세, 무기 충돌, 방패 압박, 말의 움직임, 뒤엉킨 행렬, 무너지는 대형으로 강도를 만드세요.
- 고증은 유지합니다. 액션을 강하게 만들기 위해 시대에 맞지 않는 무기, 갑옷, 군복, 탈것을 넣으면 실패입니다.
- visual_period, visual_location, visual_evidence, visual_subject, visual_scene은 영어만 사용하세요.
- visual_world의 모든 값도 영어만 사용하세요.
- visual_* 필드와 image_prompt에는 일본어, 한국어, 힌디어, 중국어, 한자, 가나, 한글 등 비영어 문자를 넣지 마세요.
- 최종 image_prompt의 필수 이미지 스타일 필드 `Style: {image_prompt_required_style}`는 백엔드가 정확히 한 번 추가합니다. 직접 쓰지 마세요.
- visual_scene에는 `photorealistic`, `hyperrealistic`, `photo-real`, `real photo`, `realistic photograph` 같은 실사 지시어를 쓰지 마세요.
- 읽을 수 있는 텍스트, 글자, 숫자, 로고, 워터마크, 자막, UI 라벨, 글자가 있는 포스터, 글자가 있는 화면, 가짜 문자, 가짜 한자, 가짜 서예, 문장, 엠블럼, 장식용 상징 표식을 절대 요청하지 마세요.
- 보이는 표지판, 벽걸이, 깃발, 갑옷 판, 배의 돛, 책 표지, 상자, 라벨은 이야기가 실제 특정 표시를 다루는 경우가 아니라면 모두 비어 있고 아무 표시가 없어야 합니다.
- 컷을 쓰기 전에 내부적으로 주제의 정확한 시간대, 필요할 경우 계절/시간대, 지역, 장소 유형, 물질문화, 의복, 머리모양, 머리 장식, 장신구, 건축, 도구, 무기, 갑옷, 차량, 선박, 가구, 의식, 일상 사물, 풍경, 재료, 반복 캐릭터 디자인을 확정하세요.
- 모든 컷에는 visual_year, visual_period, visual_location, visual_evidence, visual_subject, visual_scene이 있어야 합니다.
- visual_year는 정확한 보이는 연도, 또는 정확한 연도를 알 수 없을 경우 가장 좁고 정직한 날짜 범위를 적어야 합니다.
- visual_period는 구체적이어야 하며 일반적이면 안 됩니다. 영어로 작성하고, 역사에서는 가능하면 시대, 통치자/왕조/문화, 날짜 범위를 적으세요.
- visual_location은 일반 배경이 아니라 구체적인 공간이어야 합니다. 영어로 작성하세요.
- visual_evidence는 내레이션과 이미지의 연결 이유를 짧게 설명해야 합니다. 영어로 작성하세요.
- 최종 image_prompt는 백엔드가 보이는 연도/날짜 범위, 정확한 공간, 스타일로 시작하게 만듭니다.
- visual_scene 필드 값 안에는 따옴표를 넣지 마세요.
- 역사 컷에서는 visual_scene에 보이는 시대 증거를 적어야 합니다: 시대에 맞는 의복, 머리모양 또는 머리장식, 도구, 무기, 갑옷, 장신구, 가구, 건물, 차량, 선박, 의식 물건, 일상 사물, 재료 등.
- 신화와 전승 컷에서는 확정 고증처럼 보이는 성벽, 병사, 궁전, 철기, 수레, 깃발을 자동으로 넣지 마세요. 내레이션이 직접 요구하지 않으면 신단수, 동굴, 제의 공간, 소박한 청동기풍 의례 소품처럼 보수적인 장면을 쓰세요.
- 시대, 공간, 장소에 맞지 않는 깃발 이미지는 사용하지 마세요.
- 시대, 공간, 장소에 맞는 의복, 차량, 사물, 무기, 갑옷, 생활양식, 건물만 사용하세요.
- 시대나 문화를 섞지 마세요.
- 시대착오 금지: 현대 의복, 현대 머리모양, 현대 장신구, 현대 건물, 총, 자동차, 화면, 네온, 국기, 인쇄된 책, 종이 노트, 읽을 수 있는 글자는 내레이션이 실제로 그 시대를 다루는 경우가 아니라면 금지합니다.
- 내레이션이 추상적 주장에 관한 것이라면, 은유 이미지가 아니라 그 컷에 가장 가까운 구체적 역사 증거나 행동을 시각화하세요.

최종 출력:
- 반드시 JSON 객체 하나만 반환합니다.
- script_version은 반드시 "3.1"로 반환합니다.
- visual_world는 반드시 최상위에 포함합니다.
- JSON 밖에 어떤 설명도 붙이지 않습니다.
- 모든 컷 번호는 1부터 순서대로 빠짐없이 이어져야 합니다.
- cuts의 개수는 사용자 프롬프트의 정확한 컷 수와 일치해야 합니다.
- story_beats는 cuts 전체를 빠짐없이 설명해야 합니다.
- 모든 cut에는 beat_id와 beat_role이 있어야 합니다.
"""


def _voice_profile_from_config(config: dict | None) -> dict | None:
    if not config:
        return None
    try:
        from app.services.tts.voice_profile import get_cached_voice_profile_from_config

        return get_cached_voice_profile_from_config(config)
    except Exception:
        return None


def _fallback_scaled_voice_rate(config: dict | None, key: str) -> float:
    cfg = config or {}
    try:
        value = float(cfg.get(key) or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value > 0:
        return value
    return 0.0


def _profiled_chars_per_sec(config: dict | None, fallback: float) -> float:
    profile = _voice_profile_from_config(config)
    if not profile:
        scaled = _fallback_scaled_voice_rate(config, "chars_per_sec")
        if scaled > 0:
            return scaled
        try:
            from app.services.tts.voice_profile import profile_key_from_config

            if (
                config
                and config.get("tts_voice_profile_key")
                and config.get("tts_voice_profile_key") == profile_key_from_config(config)
            ):
                measured = float(config.get("tts_chars_per_sec") or 0)
            else:
                measured = 0.0
        except (TypeError, ValueError):
            measured = 0.0
        except Exception:
            measured = 0.0
        return measured if measured > 0 else fallback
    try:
        measured = float(profile.get("chars_per_sec") or 0)
    except (TypeError, ValueError):
        measured = 0.0
    return measured if measured > 0 else fallback


def _profiled_words_per_sec(config: dict | None, fallback: float) -> float:
    profile = _voice_profile_from_config(config)
    if not profile:
        scaled = _fallback_scaled_voice_rate(config, "words_per_sec")
        if scaled > 0:
            return scaled
        try:
            from app.services.tts.voice_profile import profile_key_from_config

            if (
                config
                and config.get("tts_voice_profile_key")
                and config.get("tts_voice_profile_key") == profile_key_from_config(config)
            ):
                measured = float(config.get("tts_words_per_sec") or 0)
            else:
                measured = 0.0
        except (TypeError, ValueError):
            measured = 0.0
        except Exception:
            measured = 0.0
        return measured if measured > 0 else fallback
    try:
        measured = float(profile.get("words_per_sec") or 0)
    except (TypeError, ValueError):
        measured = 0.0
    return measured if measured > 0 else fallback


def _script_tts_target_window(config: dict | None) -> tuple[float, float, float]:
    """Timing target used when writing narration text."""
    return resolve_tts_timing_window(config)


def normalize_language_code(language: Any = "ko") -> str:
    value = str(language or "ko").strip().lower()
    if not value:
        return "ko"
    if value in {"ko", "kr", "kor", "korean"} or "한국" in value:
        return "ko"
    if value in {"ja", "jp", "jpn", "japanese"} or "일본" in value or "日本" in value:
        return "ja"
    if value in {"hi", "hin", "hindi"} or "hindi" in value:
        return "hi"
    if value in {"en", "eng", "english"} or value.startswith("en-"):
        return "en"
    return "ko"


def get_system_prompt(language: str = "ko", config: dict | None = None) -> str:
    """Return the single global script-generation system prompt."""
    config = config or {}
    language = normalize_language_code(language)
    try:
        tts_speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        tts_speed = 1.0
    tts_model = config.get("tts_model", "openai-tts")

    effective_speed = tts_speed
    if tts_model == "elevenlabs":
        effective_speed = max(0.7, min(1.2, effective_speed))
    else:
        effective_speed = max(0.25, min(4.0, effective_speed))

    tts_min_sec, tts_max_sec, tts_target_sec = _script_tts_target_window(config)

    def _sub(template: str, replacements: dict) -> str:
        result = template
        for key, val in replacements.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    if language in ("en", "hi"):
        raw_wps = _profiled_words_per_sec(config, 2.5 * effective_speed)
        raw_cps = _profiled_chars_per_sec(config, 12.0 * effective_speed)
        wps = round(raw_wps, 3)
        cps = round(raw_cps, 3)
        target_words = max(1, int(round(tts_target_sec * wps)))
        max_words = max(1, int(math.floor(tts_max_sec * wps)))
        min_words = max(1, int(math.ceil(tts_min_sec * wps)) - (0 if language == "en" else 1))
        if min_words > max_words:
            min_words = max_words = target_words
        target_range = f"{min_words}~{max_words}"
        target_low = min_words
        timing_unit = "words"
        max_chars = max(1, int(math.floor(tts_max_sec * cps)))
        min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - 1)
        char_timing_line = (
            f"- 보조 문자 수 제한: 모든 narration은 공백 포함 {min_chars}~{max_chars}자 안에 있어야 하며, "
            f"{max_chars}자를 넘으면 실패입니다.\n"
        )
    else:
        fallback = 7.8 * effective_speed if language == "ja" else 8.8 * effective_speed
        cps = round(_profiled_chars_per_sec(config, fallback), 1)
        max_chars = max(1, int(math.floor(tts_max_sec * cps))) if language == "ja" else max(1, int(math.ceil(tts_max_sec * cps)))
        min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - (0 if language == "ja" else 1))
        if min_chars > max_chars:
            target_chars = max(1, int(round(tts_target_sec * cps)))
            min_chars = max_chars = target_chars
        target_range = f"{min_chars}~{max_chars}"
        target_low = min_chars
        timing_unit = "characters including spaces" if language == "en" else "공백 포함 글자"
        char_timing_line = ""

    narration_lang = {
        "ko": "한국어",
        "ja": "일본어",
        "en": "English",
        "hi": "Hindi",
    }.get(language, "한국어")
    national_pride_style = {
        "ko": "- 한국 시청자가 자부심을 느낄 수 있는 색채를 약 10% 정도 추가하세요: 사실이 뒷받침될 때 인내, 전략 감각, 장인정신, 문화적 지속성을 보여주세요. 절제되고 사실적으로 유지하며, 선전, 우월 주장, 현대 민족주의는 금지합니다.\n",
        "ja": "- 일본어 시청자가 자부심을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때 제도화, 인내, 공예성, 문화적 지속성을 절제되고 사실적으로 보여주며, 선전, 우월 주장, 현대 민족주의는 금지합니다.\n",
        "en": "- 일반 시청자가 조용한 감탄을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때 발명, 실용성, 위험 감수, civic scale을 절제되고 사실적으로 보여주며, 선전이나 우월 주장은 금지합니다.\n",
        "hi": "- 인도 시청자가 자부심을 느낄 수 있는 색채를 약 40% 정도 추가하세요. 사실이 뒷받침될 때 문명적 깊이, 정치적 감각, 지적 전통, 사회적 규모를 절제되고 사실적으로 보여주며, 선전이나 우월 주장은 금지합니다.\n",
    }.get(language, "- 현지 시청자가 조용한 감탄을 느낄 수 있는 색채를 약 10% 정도 추가하세요. 사실이 뒷받침될 때만 절제되고 사실적으로 사용합니다.\n")

    japanese_narration_style = ""
    if language == "ja":
        japanese_narration_style = """

日本語ナレーション品質契約:
- 日本語の視聴者が自然に聞ける、短く明確な話し言葉で書いてください。韓国語や中国語を直訳したような語順は禁止です。
- 歴史用語、人名、地名、史料名は日本語で一般的な読みを前提にしてください。読みが複数ある語は、その時代・文脈で最も自然な読みを選びます。
- 古代日本・ヤマト王権の文脈で「大王」を扱う場合は、おおきみとして扱ってください。外国の「大王」はこの規則に含めません。
- 漢字は最大限ひかえてください。narration、title、description、shorts の見出しは、できるだけひらがな・カタカナ中心で書きます。
- 漢字を使うのは、人名・地名・史料名・時代名など、意味が崩れる固有名詞や一般的に読める歴史用語だけにしてください。
- 難しい漢字熟語、四字熟語、漢語の連続は禁止です。漢字が続く場合は、ひらがなを増やす、言い換える、文を分けるなどして読みやすくしてください。
- 助詞、ひらがな、自然な言い換えを多く使い、TTSが詰まらず読める文にしてください。
- 一文の中で固有名詞を詰め込みすぎないでください。固有名詞は一文に原則1つ、多くても2つまでに抑えてください。
- 「読み方が不自然」「中国語のように聞こえる」と言われやすい表現を避け、日本語の歴史解説として普通に聞こえる文にしてください。
"""
    japanese_visual_style = ""
    if language == "ja":
        japanese_visual_style = """- 일본사 시각화에서는 현대 연구자, 현대 자료실, 현대 도서관, 현대 박물관 장면을 반복하지 마세요.
- 고대/중세/근세 일본사 주제에서 후대 해석이나 연구를 말할 때도, 실제 현대 연구 방법을 직접 다루는 컷만 현대 장면을 사용하세요.
- 150컷 기준 현대 자료실/도서관/연구자 장면은 최대 5컷입니다. 나머지는 원시대 장면, 사본 전승 시기, 주석이 이루어진 역사 시대의 장면으로 시각화하세요.
- visual_year에 2020-2024, visual_period에 Contemporary Japan, visual_subject에 modern researcher를 반복하면 실패입니다.
"""

    cut_duration = resolve_cut_video_duration(config)
    try:
        expected_cut_count = int(config.get("target_cuts") or 0)
    except (TypeError, ValueError):
        expected_cut_count = 0
    if expected_cut_count <= 0:
        try:
            target_duration = float(config.get("target_duration") or 600)
        except (TypeError, ValueError):
            target_duration = 600
        expected_cut_count = max(1, math.ceil(target_duration / cut_duration))

    if expected_cut_count >= 150:
        cut_structure_contract = (
            "- 150컷 구성은 15개 scene_blocks로만 진행하세요. 구버전 구조 키는 만들지 마세요.\n"
            "- scene_blocks는 정확히 15개입니다. 각 블럭은 10컷이고 전체 1~150컷을 빠짐없이 덮어야 합니다.\n"
            "- 권장 블럭 범위: 1=1-10, 2=11-20, 3=21-30 ... 15=141-150.\n"
            "- 1막 1~30컷: 중심 질문, 주인공, 목표, 위험을 제시합니다. 시청자는 누가 무엇을 하려는지 바로 알아야 합니다.\n"
            "- 2막 31~60컷: 첫 장애물이 등장합니다. 기록, 지형, 적, 내부 갈등, 보급, 외교 문제 중 하나가 계획을 막아야 합니다.\n"
            "- 3막 61~90컷: 예상과 다른 반전이 드러납니다. 강해 보인 쪽의 약점, 약해 보인 쪽의 버팀, 작은 사건의 큰 결과를 보여줍니다.\n"
            "- 4막 91~120컷: 압박이 가장 커집니다. 선택의 대가, 내부 갈등, 실패 가능성, 돌이킬 수 없는 변화가 이어져야 합니다.\n"
            "- 5막 121~140컷: 중심 질문에 직접 답합니다. 시청자가 이 영상을 한 문장으로 기억할 결론을 줍니다.\n"
            "- 141~150컷: 이번 편의 결론과 다음 편의 갈등을 연결합니다. 새 사건을 길게 설명하지 말고, 다음 질문만 강하게 남깁니다."
        )
        image_sequence_contract = (
            "- 이미지는 계속 컷 단위입니다. visual_scene_id를 만들거나 이미지 수를 줄이지 마세요.\n"
            "- 다만 이미지 흐름은 scene_blocks와 함께 변해야 합니다. 1막은 주인공과 위험, 2막은 장애물과 압박, 3막은 반전과 전황 변화, "
            "4막은 선택의 대가와 위기, 5막은 결론과 다음 갈등을 각 컷별로 시각화하세요."
        )
    else:
        cut_structure_contract = (
            f"- 이번 영상은 정확히 {expected_cut_count}컷 구성입니다. "
            "150컷 장기 구성 규칙을 적용하지 말고, 주어진 컷 수 안에서 주인공, 목표, 장애물, 반전, 대가, 결론을 압축하세요."
        )
        image_sequence_contract = (
            f"- 이미지도 정확히 {expected_cut_count}컷에 맞춰 달라야 합니다. "
            "짧은 테스트 영상에서도 이미지 수를 줄이지 말고, 각 컷마다 컷 내용에 맞는 visual_* 필드를 작성하세요."
        )

    shorts_metadata_contract = """쇼츠 메타데이터 계약:
- 대본 생성 단계에서는 쇼츠 후보를 선정하지 않습니다.
- 모든 컷은 shorts_candidate=false만 넣고 shorts_group, shorts_reason, shorts_score, shorts_title은 생략하세요.
- 쇼츠 후보 선정은 대본 생성 뒤 1차 검사 단계에서 수행합니다.
- 본편 narration은 쇼츠로 잘릴 수 있는 독립 문장이 아니라 전체 흐름을 우선합니다."""

    return _sub(SCRIPT_SYSTEM_PROMPT_TEMPLATE, {
        "target_sec": tts_target_sec,
        "target_min_sec": tts_min_sec,
        "target_max_sec": tts_max_sec,
        "target_range": target_range,
        "timing_unit": timing_unit,
        "char_timing_line": char_timing_line,
        "target_low": target_low,
        "narration_lang": narration_lang,
        "national_pride_style": national_pride_style,
        "japanese_narration_style": japanese_narration_style,
        "japanese_visual_style": japanese_visual_style,
        "cut_structure_contract": cut_structure_contract,
        "image_sequence_contract": image_sequence_contract,
        "shorts_metadata_contract": shorts_metadata_contract,
        "image_prompt_required_style": IMAGE_PROMPT_REQUIRED_STYLE,
        "cut_video_duration": cut_duration,
    })
# Keep backward compat
SCRIPT_SYSTEM_PROMPT = get_system_prompt("ko")


class BaseLLMService(ABC):
    """대본 생성 AI 모델의 공통 인터페이스"""

    model_id: str
    display_name: str

    @abstractmethod
    async def generate_story_plan(self, topic: str, config: dict) -> dict:
        """대본 생성 전에 사용할 V3.1 story plan JSON을 반환"""
        pass

    @abstractmethod
    async def generate_script(self, topic: str, config: dict) -> dict:
        """주제와 설정을 받아 대본 JSON을 반환"""
        pass

    @staticmethod
    def _expected_cut_count(config: dict | None) -> int:
        cfg = config or {}
        try:
            target_cuts = int(cfg.get("target_cuts") or 0)
        except (TypeError, ValueError):
            target_cuts = 0
        if target_cuts > 0:
            return target_cuts
        try:
            target_duration = float(cfg.get("target_duration") or 600)
        except (TypeError, ValueError):
            target_duration = 600
        return max(1, math.ceil(target_duration / resolve_cut_video_duration(cfg)))

    @staticmethod
    def _story_plan_cache_payload(topic: str, config: dict | None) -> dict:
        cfg = config or {}
        return {
            "story_plan_schema": "v3.2-block-only-30",
            "topic": str(topic or "").strip(),
            "language": normalize_language_code(cfg.get("language", "ko")),
            "target_cuts": BaseLLMService._expected_cut_count(cfg),
            "target_duration": cfg.get("target_duration"),
            "style": cfg.get("style"),
            "script_model": cfg.get("script_model"),
            "story_model": cfg.get("story_model"),
            "content_required": cfg.get("content_required"),
            "content_forbidden": cfg.get("content_forbidden"),
            "content_constraints": cfg.get("content_constraints"),
            "episode_number": cfg.get("episode_number"),
            "episode_core_content": cfg.get("episode_core_content"),
            "next_episode_preview": cfg.get("next_episode_preview"),
            "episode_openings": cfg.get("episode_openings"),
            "episode_endings": cfg.get("episode_endings"),
        }

    @staticmethod
    def _story_plan_fingerprint(topic: str, config: dict | None) -> str:
        raw = json.dumps(
            BaseLLMService._story_plan_cache_payload(topic, config),
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _story_plan_path(self, config: dict | None, *, create: bool = False) -> Optional[Any]:
        project_id = str((config or {}).get("__project_id") or "").strip()
        if not project_id:
            return None
        try:
            return resolve_project_dir(project_id, config or {}, create=create) / "story_plan.json"
        except Exception:
            return None

    def _load_cached_story_plan(self, topic: str, config: dict | None) -> Optional[dict]:
        path = self._story_plan_path(config, create=False)
        if path is None or not path.exists():
            return None
        try:
            plan = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(plan, dict):
            return None
        if plan.get("source_fingerprint") != self._story_plan_fingerprint(topic, config):
            return None
        try:
            from app.services.llm.script_quality import assert_story_plan

            assert_story_plan(plan, self._expected_cut_count(config), topic, config)
        except Exception:
            return None
        return plan

    def _save_story_plan(self, topic: str, config: dict | None, story_plan: dict) -> None:
        path = self._story_plan_path(config, create=True)
        if path is None or not isinstance(story_plan, dict):
            return
        payload = dict(story_plan)
        payload["source_fingerprint"] = self._story_plan_fingerprint(topic, config)
        payload["story_model"] = self.model_id
        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    @staticmethod
    def _normalize_story_plan_structure(story_plan: dict) -> dict:
        if not isinstance(story_plan, dict):
            return story_plan
        normalized = dict(story_plan)
        normalized.pop("story_beats", None)
        blocks = normalized.get("scene_blocks")
        if isinstance(blocks, list):
            cleaned_blocks: list[Any] = []
            for block in blocks:
                if not isinstance(block, dict):
                    cleaned_blocks.append(block)
                    continue
                item = dict(block)
                item.pop("beat_id", None)
                if item.get("character_introductions") is None:
                    item["character_introductions"] = []
                cleaned_blocks.append(item)
            normalized["scene_blocks"] = cleaned_blocks
        return normalized

    def _story_plan_for_script(self, topic: str, config: dict) -> dict | None:
        existing = config.get("story_plan")
        if isinstance(existing, dict):
            try:
                from app.services.llm.script_quality import assert_story_plan

                assert_story_plan(existing, self._expected_cut_count(config), topic, config)
                return existing
            except Exception:
                return None
        return self._load_cached_story_plan(topic, config)

    async def _ensure_story_plan_for_script(self, topic: str, config: dict) -> dict | None:
        existing = self._story_plan_for_script(topic, config)
        if isinstance(existing, dict):
            return existing
        if (config or {}).get("skip_story_plan_generation"):
            return None
        story_model = str(
            (config or {}).get("story_model")
            or (config or {}).get("script_model")
            or self.model_id
        )
        if story_model and story_model != self.model_id:
            from app.services.llm.factory import get_llm_service

            return await get_llm_service(story_model).generate_story_plan(topic, config)
        return await self.generate_story_plan(topic, config)

    @staticmethod
    def _strip_story_plan_runtime_fields(story_plan: dict) -> dict:
        if not isinstance(story_plan, dict):
            return {}
        cleaned = {
            "script_version": story_plan.get("script_version"),
            "visual_world": story_plan.get("visual_world"),
            "story_core": story_plan.get("story_core"),
            "character_map": story_plan.get("character_map"),
            "causality_chain": story_plan.get("causality_chain"),
            "fact_ledger": story_plan.get("fact_ledger"),
            "visual_plan": story_plan.get("visual_plan"),
            "scene_blocks": story_plan.get("scene_blocks"),
            "script_checklist": story_plan.get("script_checklist"),
        }
        return {k: v for k, v in cleaned.items() if v is not None}

    @staticmethod
    def _compiled_visual_world(script: dict) -> str:
        world = script.get("visual_world") if isinstance(script, dict) else None
        if not isinstance(world, dict):
            return ""
        labels = (
            ("time_range", "Time range"),
            ("place_scope", "Place scope"),
            ("culture_scope", "Culture scope"),
            ("material_culture", "Material culture"),
            ("continuity_rule", "Continuity rule"),
        )
        parts: list[str] = []
        for key, label in labels:
            value = image_prompt_safe_text(
                world.get(key),
                allow_year_normalization=(key == "time_range"),
            )
            if value:
                parts.append(f"{label}: {value}")
        if not parts:
            return ""
        return "Global visual world: " + "; ".join(parts)

    def _build_story_plan_system_prompt(self, config: dict) -> str:
        language = normalize_language_code((config or {}).get("language", "ko"))
        narration_lang = {
            "ko": "한국어",
            "ja": "일본어",
            "en": "English",
            "hi": "Hindi",
        }.get(language, "한국어")

        def _sub(template: str, replacements: dict) -> str:
            result = template
            for key, val in replacements.items():
                result = result.replace(f"{{{key}}}", str(val))
            return result

        return _sub(
            STORY_PLAN_SYSTEM_PROMPT_TEMPLATE,
            {
                "expected_cut_count": self._expected_cut_count(config),
                "expected_block_count": math.ceil(self._expected_cut_count(config) / 10),
                "narration_lang": narration_lang,
            },
        )

    def _build_story_plan_user_prompt(self, topic: str, config: dict) -> str:
        cfg = config or {}
        language = normalize_language_code(cfg.get("language", "ko"))
        labels = {
            "ko": ("주제", "정확한 컷 수", "스타일", "언어", "한국어"),
            "ja": ("トピック", "正確なカット数", "スタイル", "言語", "日本語"),
            "en": ("Topic", "Exact cut count", "Style", "Language", "English"),
            "hi": ("Topic", "Exact cut count", "Style", "Language", "Hindi"),
        }
        topic_label, cuts_label, style_label, language_label, language_name = labels.get(language, labels["ko"])

        def _normalize_constraints(raw: str) -> str:
            s = str(raw or "").replace("\r\n", "\n")
            for sep in (" / ", " · "):
                s = s.replace(sep, "\n")
            lines = [ln.strip(" -•·").strip() for ln in s.split("\n")]
            lines = [ln for ln in lines if ln]
            return "\n".join(f"- {ln}" for ln in lines)

        required_raw = str(cfg.get("content_required") or "").strip()
        forbidden_raw = str(cfg.get("content_forbidden") or "").strip()
        legacy_raw = str(cfg.get("content_constraints") or "").strip()
        parts: list[str] = []
        if required_raw or forbidden_raw or legacy_raw:
            parts.append("사용자 입력 제약")
            if required_raw:
                parts.extend(["[필수 사항]", _normalize_constraints(required_raw)])
            if forbidden_raw:
                parts.extend(["[금지 사항]", _normalize_constraints(forbidden_raw)])
            if legacy_raw and not (required_raw or forbidden_raw):
                parts.extend(["[사용자 규칙]", _normalize_constraints(legacy_raw)])
            parts.append("")

        core_content = str(cfg.get("episode_core_content") or "").strip()
        next_preview = str(cfg.get("next_episode_preview") or "").strip()
        episode_openings = [str(x or "").strip() for x in (cfg.get("episode_openings") or []) if str(x or "").strip()] if isinstance(cfg.get("episode_openings"), list) else []
        episode_endings = [str(x or "").strip() for x in (cfg.get("episode_endings") or []) if str(x or "").strip()] if isinstance(cfg.get("episode_endings"), list) else []
        if core_content or next_preview or cfg.get("episode_number") or episode_openings or episode_endings:
            parts.append("이번 에피소드 입력")
            if cfg.get("episode_number"):
                parts.extend(["[에피소드 번호]", f"Episode {cfg.get('episode_number')}"])
            if core_content:
                parts.extend(["[핵심 내용]", core_content])
            if episode_openings:
                parts.append("[오프닝 대사]")
                parts.extend(f"{i}. {line}" for i, line in enumerate(episode_openings, 1))
            if episode_endings:
                parts.append("[엔딩 대사]")
                parts.extend(f"{i}. {line}" for i, line in enumerate(episode_endings, 1))
            if next_preview:
                parts.extend(["[다음 에피소드 예고]", next_preview])
            parts.append("")

        parts.extend([
            f"{topic_label}: {topic}",
            f"{cuts_label}: {self._expected_cut_count(cfg)}",
            f"{style_label}: {cfg.get('style', 'news_explainer')}",
            f"{language_label}: {language_name}",
        ])
        return "\n".join(parts).strip()

    def _build_story_plan_text_system_prompt(self, config: dict) -> str:
        expected_cuts = self._expected_cut_count(config)
        expected_blocks = math.ceil(expected_cuts / 10)
        language = normalize_language_code((config or {}).get("language", "ko"))
        narration_lang = {
            "ko": "한국어",
            "ja": "일본어",
            "en": "English",
            "hi": "Hindi",
        }.get(language, "한국어")
        return (
            "당신은 유튜브 스토리 설계 내용 작성기입니다.\n"
            "JSON을 쓰지 마세요. 마크다운 표도 쓰지 마세요. 아래 섹션명과 라인 형식만 사용하세요.\n"
            "Python이 이 텍스트를 읽어 story_plan JSON으로 조립합니다. 그래서 라벨과 구분자 `|`를 지켜야 합니다.\n\n"
            "VISUAL_WORLD\n"
            "time_range: English 기준 연대\n"
            "place_scope: English 기준 장소권\n"
            "culture_scope: English 기준 문화권\n"
            "material_culture: English 의복, 도구, 무기, 건축, 탈것 기준\n"
            "continuity_rule: English 전체 컷 연속성 규칙\n\n"
            "CHARACTERS\n"
            "1. 이름 | 한 컷 안에서 설명 가능한 정체와 사건상 역할 | 첫출현 블럭 번호\n"
            "2. 이름 | 한 컷 안에서 설명 가능한 정체와 사건상 역할 | 첫출현 블럭 번호\n"
            "3. 이름 | 한 컷 안에서 설명 가능한 정체와 사건상 역할 | 첫출현 블럭 번호\n"
            "4. 이름 | 한 컷 안에서 설명 가능한 정체와 사건상 역할 | 첫출현 블럭 번호\n\n"
            "FACT_LEDGER\n"
            "confirmed: 확정 사실 / 확정 사실\n"
            "inferences: 조심스러운 해석 / 조심스러운 해석\n"
            "unknown: 단정 금지 지점 / 단정 금지 지점\n"
            "forbidden: 금지 주장 / 금지 주장\n\n"
            f"CAUSALITY\n"
            f"1부터 {expected_blocks}까지 정확히 {expected_blocks}줄을 쓰세요. 각 줄은 같은 번호의 BLOCK과 1:1로 대응합니다.\n"
            "각 줄은 원인 -> 선택/충돌 -> 결과 -> 다음 압박 구조여야 하며, 서로 중복되면 실패입니다.\n\n"
            "BLOCKS\n"
            f"BLOCK 1부터 BLOCK {expected_blocks}까지 정확히 {expected_blocks}개를 쓰세요.\n"
            "각 블럭 형식:\n"
            "BLOCK 번호 | 컷범위 | 역할\n"
            "focus: 이 블럭이 밀고 갈 핵심 진행. BLOCK 1만 질문형 문장 허용, BLOCK 2부터는 질문형 금지\n"
            "new_info: 이 블럭에서만 새로 추가할 정보\n"
            "facts: 반드시 들어갈 구체 사실을 / 로 구분\n"
            "characters: 이 블럭에서 움직이는 인물/집단을 / 로 구분\n"
            "intro: 없으면 none. 있으면 이름 | 두번째컷번호 | 2번째 컷 정체 설명 | 3번째컷 설명 / 4번째컷 설명 / 5번째컷 설명\n"
            "from_prev: 직전 블럭 결과가 이 블럭을 부르는 방식\n"
            "tension: 이 블럭에서 커지는 압박\n"
            "turn: 이 블럭의 선택, 반전, 실패, 증거\n"
            "moves: 대본 생성기가 지켜야 할 진행 지시를 / 로 구분\n"
            "to_next: 다음 블럭으로 넘어가는 실제 인과\n"
            "visual: 10컷 이미지 리듬\n"
            "include: 반드시 포함할 요소를 / 로 구분\n"
            "avoid: 금지할 요소를 / 로 구분\n\n"
            f"규칙:\n"
            f"- 이번 영상은 정확히 {expected_cuts}컷, {expected_blocks}블럭입니다.\n"
            "- 중심축, 중심질문 같은 story_core 섹션은 출력하지 마세요. Python이 블럭과 인과에서 조립합니다.\n"
            "- CHARACTERS는 정확히 4개만 씁니다. 실제 핵심 인물/집단만 고르고, 설명과 첫출현 블럭만 줍니다.\n"
            "- 각 인물의 첫출현은 해당 블럭의 두번째 컷입니다. 예: BLOCK 4가 31-40이면 intro 컷은 32입니다.\n"
            "- 인물 intro가 있는 블럭은 2번째 컷이 첫 출현, 3~5번째 컷이 같은 인물/집단 설명이 되도록 moves에 반영하세요.\n"
            "- BLOCK 1은 전체 내용을 아우르는 가장 충격적인 사건을 먼저 던지는 훅입니다. 배경 설명이나 평범한 시대 소개로 시작하면 실패입니다.\n"
            "- BLOCK 1의 첫 컷은 반드시 질문으로 시작하게 설계하세요. 매번 같은 `왜 ...일까?`만 쓰지 말고, `어떻게 이런 일이 가능했을까`, `그 선택은 왜 피할 수 없었을까`, `정말 무너진 것은 성벽이었을까`, `왜 하필 그 순간이었을까`처럼 질문 패턴이 다양해야 합니다.\n"
            "- BLOCK 1의 나머지 컷은 그 사건이 왜 충격적인지, 왜 그런 선택이 나올 수밖에 없었는지, 어떻게 그런 일이 가능했는지에 대한 압박과 의문을 키워야 합니다. 답을 완전히 풀지 말고 Block 2로 넘기세요.\n"
            "- BLOCK 2는 Block 1의 충격적인 사건에 대한 해답을 찾아가는 도입입니다. focus는 질문형으로 쓰지 말고, 은근히 답을 흘리되 결론을 말하지 않는 본편 진입 흐름으로 쓰세요.\n"
            "- BLOCK 2부터 BLOCK 마지막까지 focus, new_info, tension, turn은 질문형 문장으로 쓰지 마세요. 질문은 Block 1의 첫 컷에만 둡니다.\n"
            "- 블럭끼리는 앞 결과가 다음 원인이 되도록 유기적으로 이어야 합니다.\n"
            "- 중간중간 예상과 다른 결과, 기록이 보여주는 반전, 선택의 대가를 넣으세요.\n"
            "- 확인되지 않은 날짜, 숫자, 동기, 실제 대사는 만들지 마세요.\n"
            f"- 모든 한국어 내용은 {narration_lang} 기준으로 작성하세요. visual_world만 English로 작성하세요."
        )

    def _build_story_plan_text_user_prompt(self, topic: str, config: dict) -> str:
        return self._build_story_plan_user_prompt(topic, config)

    @staticmethod
    def _story_text_sections(raw: str) -> dict[str, list[str]]:
        section_names = {"VISUAL_WORLD", "CHARACTERS", "FACT_LEDGER", "CAUSALITY", "BLOCKS"}
        sections: dict[str, list[str]] = {}
        current = ""
        for raw_line in str(raw or "").splitlines():
            line = raw_line.strip()
            marker = line.strip("[]# ").upper().rstrip(":")
            if marker in section_names:
                current = marker
                sections.setdefault(current, [])
                continue
            if current and line:
                sections.setdefault(current, []).append(line)
        return sections

    @staticmethod
    def _story_text_field(lines: list[str], aliases: tuple[str, ...]) -> str:
        for line in lines:
            for alias in aliases:
                match = re.match(rf"^\s*{re.escape(alias)}\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        return ""

    @staticmethod
    def _story_text_list(value: str) -> list[str]:
        parts = re.split(r"\s*(?:/|;|,|·)\s*", str(value or ""))
        return [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]

    @staticmethod
    def _story_text_number(value: str) -> int:
        match = re.search(r"\d+", str(value or ""))
        return int(match.group(0)) if match else 0

    @classmethod
    def _parse_story_text_characters(cls, lines: list[str]) -> list[dict[str, Any]]:
        characters: list[dict[str, Any]] = []
        for line in lines:
            cleaned = re.sub(r"^\s*\d+[\).\:-]\s*", "", line).strip()
            parts = [part.strip() for part in cleaned.split("|")]
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            identity = parts[1].strip()
            block_id = cls._story_text_number(parts[2])
            if not name or not identity or block_id <= 0:
                continue
            cut_number = (block_id - 1) * 10 + 2
            characters.append({
                "name": name,
                "identity": identity,
                "side_or_interest": identity,
                "first_appearance_block": block_id,
                "first_appearance_cut": str(cut_number),
                "first_appearance_explanation": identity,
                "choice_or_action": identity,
                "story_function": identity,
            })
        return characters[:4]

    @classmethod
    def _parse_story_plan_text_response(cls, raw: str, *, topic: str, config: dict) -> dict:
        expected_cuts = cls._expected_cut_count(config)
        expected_blocks = math.ceil(expected_cuts / 10)
        sections = cls._story_text_sections(raw)

        visual_lines = sections.get("VISUAL_WORLD") or []
        visual_world = {
            "time_range": cls._story_text_field(visual_lines, ("time_range",)),
            "place_scope": cls._story_text_field(visual_lines, ("place_scope",)),
            "culture_scope": cls._story_text_field(visual_lines, ("culture_scope",)),
            "material_culture": cls._story_text_field(visual_lines, ("material_culture",)),
            "continuity_rule": cls._story_text_field(visual_lines, ("continuity_rule",)),
        }
        character_map = cls._parse_story_text_characters(sections.get("CHARACTERS") or [])

        facts_lines = sections.get("FACT_LEDGER") or []
        fact_ledger = {
            "confirmed_facts": cls._story_text_list(cls._story_text_field(facts_lines, ("confirmed", "confirmed_facts"))),
            "careful_inferences": cls._story_text_list(cls._story_text_field(facts_lines, ("inferences", "careful_inferences"))),
            "unknown_or_debated": cls._story_text_list(cls._story_text_field(facts_lines, ("unknown", "unknown_or_debated"))),
            "forbidden_claims": cls._story_text_list(cls._story_text_field(facts_lines, ("forbidden", "forbidden_claims"))),
        }

        causality_chain: list[str] = []
        for line in sections.get("CAUSALITY") or []:
            if re.match(r"^\s*\d+\s*(?:부터|to)\s+\d+", line, flags=re.IGNORECASE):
                continue
            cleaned = re.sub(r"^\s*\d+[\).\:-]\s*", "", line).strip()
            if cleaned:
                causality_chain.append(cleaned)
        if expected_blocks and len(causality_chain) > expected_blocks:
            causality_chain = causality_chain[:expected_blocks]

        characters_by_block: dict[int, list[dict[str, Any]]] = {}
        for character in character_map:
            block_id = cls._story_text_number(str(character.get("first_appearance_block") or ""))
            if block_id > 0:
                characters_by_block.setdefault(block_id, []).append(character)

        blocks_text = "\n".join(sections.get("BLOCKS") or [])
        header_re = re.compile(r"(?im)^\s*BLOCK\s+(\d+)\s*(?:\|\s*([^\n|]+))?(?:\|\s*([^\n|]+))?\s*$")
        headers = list(header_re.finditer(blocks_text))
        scene_blocks: list[dict[str, Any]] = []
        for idx, header in enumerate(headers):
            block_id = int(header.group(1))
            if expected_blocks and not (1 <= block_id <= expected_blocks):
                continue
            start = (block_id - 1) * 10 + 1
            end = min(start + 9, expected_cuts or start + 9)
            body_start = header.end()
            body_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(blocks_text)
            body_lines = [line.strip() for line in blocks_text[body_start:body_end].splitlines() if line.strip()]
            role = str(header.group(3) or "").strip() or "setup"
            if block_id == 1:
                role = "hook"
            elif expected_blocks and block_id == expected_blocks:
                role = "bridge"
            focus_line = cls._story_text_field(body_lines, ("focus", "핵심", "진행"))
            question = cls._story_text_field(body_lines, ("question", "mini_question", "질문"))
            if block_id == 1:
                focus = question or focus_line
            else:
                focus = focus_line or question
            new_info = cls._story_text_field(body_lines, ("new_info", "new_information", "새 정보"))
            facts = cls._story_text_list(cls._story_text_field(body_lines, ("facts", "key_facts", "사실")))
            character_focus = cls._story_text_list(cls._story_text_field(body_lines, ("characters", "character_focus", "인물")))
            intro_raw = cls._story_text_field(body_lines, ("intro", "character_introduction", "첫출현"))
            introductions: list[dict[str, Any]] = []
            block_characters = characters_by_block.get(block_id) or []
            if block_characters:
                for character in block_characters:
                    name = str(character.get("name") or "").strip()
                    identity = str(character.get("identity") or "").strip()
                    introductions.append({
                        "cut_number": str(start + 1),
                        "name": name,
                        "explanation_goal": identity,
                        "followup_cuts": [
                            f"Cut {start + 2}: {name}의 직책과 권력 안 위치를 설명",
                            f"Cut {start + 3}: {name}의 이해관계와 선택지를 설명",
                            f"Cut {start + 4}: {name}이 이번 사건에서 맡는 기능을 설명",
                        ],
                    })
                    if name and name not in character_focus:
                        character_focus.append(name)
            elif intro_raw and intro_raw.lower() not in {"none", "없음", "no"}:
                intro_parts = [part.strip() for part in intro_raw.split("|")]
                name = intro_parts[0] if intro_parts else ""
                goal = intro_parts[2] if len(intro_parts) >= 3 else (intro_parts[1] if len(intro_parts) >= 2 else "")
                followups = cls._story_text_list(intro_parts[3]) if len(intro_parts) >= 4 else []
                if name and goal:
                    introductions.append({
                        "cut_number": str(start + 1),
                        "name": name,
                        "explanation_goal": goal,
                        "followup_cuts": followups,
                    })
            moves = cls._story_text_list(cls._story_text_field(body_lines, ("moves", "required_script_moves", "대본 지시")))
            if introductions:
                intro_name = introductions[0].get("name") or "해당 인물"
                moves.extend([
                    f"Cut {start + 1}은 {intro_name}의 첫 출현과 정체를 설명한다.",
                    f"Cut {start + 2}-{start + 4}는 {intro_name}의 직책, 이해관계, 사건상 기능을 이어서 설명한다.",
                ])
            causality = causality_chain[block_id - 1] if 0 <= block_id - 1 < len(causality_chain) else ""
            scene_blocks.append({
                "block_id": block_id,
                "cut_range": f"{start}-{end}",
                "block_role": role,
                "block_goal": cls._story_text_field(body_lines, ("goal", "block_goal", "목표")) or focus or causality,
                "mini_question": focus,
                "new_information": new_info or causality,
                "key_facts": facts,
                "character_focus": character_focus,
                "character_introductions": introductions,
                "continuity_from_previous": cls._story_text_field(body_lines, ("from_prev", "continuity_from_previous", "인과")) or causality,
                "tension": cls._story_text_field(body_lines, ("tension", "압박")),
                "turn": cls._story_text_field(body_lines, ("turn", "전환", "반전")),
                "required_script_moves": moves,
                "turn_to_next": cls._story_text_field(body_lines, ("to_next", "turn_to_next", "다음")),
                "visual_rhythm": cls._story_text_field(body_lines, ("visual", "visual_rhythm", "비주얼")),
                "must_include": cls._story_text_list(cls._story_text_field(body_lines, ("include", "must_include", "포함"))),
                "must_avoid": cls._story_text_list(cls._story_text_field(body_lines, ("avoid", "must_avoid", "회피"))),
            })
        scene_blocks.sort(key=lambda item: int(item.get("block_id") or 0))
        for block in scene_blocks:
            block_id = int(block.get("block_id") or 0)
            parsed_range = cls._story_text_number(str(block.get("cut_range") or ""))
            start_cut = parsed_range or ((block_id - 1) * 10 + 1)
            moves = block.get("required_script_moves")
            if not isinstance(moves, list):
                moves = []
            if block_id == 1:
                block["block_role"] = "hook"
                if not block.get("mini_question"):
                    block["mini_question"] = f"{topic}에서 가장 충격적인 선택은 왜 가능했을까?"
                moves.extend([
                    f"Cut {start_cut}은 전체 사건을 아우르는 강한 질문으로 시작한다. 질문 패턴은 매번 다르게 잡는다.",
                    f"Cut {start_cut + 1}-{start_cut + 9}는 그 사건이 왜 충격적인지, 왜 피하기 어려웠는지, 어떻게 가능했는지 압박과 의문을 키운다.",
                    "Block 1은 답을 끝까지 풀지 않고 Block 2에서 해답을 찾도록 넘긴다.",
                ])
                block["required_script_moves"] = moves
            elif block_id == 2:
                block["block_role"] = block.get("block_role") or "setup"
                if not block.get("mini_question"):
                    block["mini_question"] = "첫 블럭의 충격적인 사건에 대한 해답을 찾아가는 본편 진입"
                moves.extend([
                    f"Cut {start_cut}은 Block 1의 충격적인 사건을 받아 해답을 찾아가겠다는 흐름으로 시작한다.",
                    "Block 2는 답을 은근히 흘리되 결론을 다 말하지 않고 본편으로 호흡을 끌고 간다.",
                    "`이제부터 그 이유를 따라가 보겠습니다`, `오늘은 그 이야기를 해보죠`, `함께 확인해볼까요` 같은 자연스러운 본편 진입 어투를 참고하되 그대로 반복하지 않는다.",
                ])
                block["required_script_moves"] = moves

        first_block = scene_blocks[0] if scene_blocks else {}
        last_block = scene_blocks[-1] if scene_blocks else {}
        protagonist = str((character_map[0] or {}).get("name") or topic) if character_map else topic
        story_core = {
            "story_axis": causality_chain[0] if causality_chain else str(topic),
            "episode_scope": f"{first_block.get('new_information') or topic}부터 {last_block.get('new_information') or topic}까지",
            "central_question": str(first_block.get("mini_question") or topic),
            "central_answer": causality_chain[-2] if len(causality_chain) >= 2 else str(last_block.get("new_information") or topic),
            "protagonist": protagonist,
            "goal": str((character_map[0] or {}).get("side_or_interest") or first_block.get("new_information") or topic) if character_map else str(topic),
            "obstacle": str(first_block.get("tension") or (scene_blocks[1].get("tension") if len(scene_blocks) > 1 else "") or topic),
            "first_turn": str(first_block.get("turn") or first_block.get("new_information") or topic),
            "mid_crisis": str(scene_blocks[len(scene_blocks) // 2].get("turn") if scene_blocks else topic),
            "cost": str(scene_blocks[max(0, int(len(scene_blocks) * 0.7) - 1)].get("turn") if scene_blocks else topic),
            "ending_memory": str(last_block.get("turn") or (causality_chain[-1] if causality_chain else topic)),
        }
        return {
            "script_version": "3.1",
            "visual_world": visual_world,
            "story_core": story_core,
            "character_map": character_map,
            "causality_chain": causality_chain,
            "fact_ledger": fact_ledger,
            "visual_plan": {
                "overall_ratio": {
                    "character_closeup": 10,
                    "intense_action": 15,
                    "battle_or_conflict": 30,
                    "political_council": 15,
                    "terrain_or_logistics": 20,
                    "detail_object": 10,
                    "record_or_archive": 5,
                },
                "five_cut_rhythm": [
                    "wide situation",
                    "hook reaction",
                    "character explanation",
                    "interest or stake",
                    "story function",
                    "conflict or obstacle",
                    "detail object",
                    "decision pressure",
                    "turn or reveal",
                    "bridge to next block",
                ],
                "avoid": ["반복 피사체", "자료실 장면 남발", "의미 없는 먼 풍경"],
            },
            "scene_blocks": scene_blocks,
            "script_checklist": {
                "story": ["강한 첫 블럭 질문", "후반부 중심 답변 회수"],
                "continuity": [f"{expected_blocks}개 인과와 {expected_blocks}개 블럭 1:1 연결", "반복 설명 금지"],
                "facts": ["확정 사실과 추정 분리", "금지 단정 회피"],
                "visual": ["시대·장소·문화 고증 유지", "블럭별 다른 이미지 리듬"],
            },
        }

    @staticmethod
    def strengthen_visual_context(script: dict, config: dict | None = None) -> dict:
        """Copy cut-level historical metadata into image_prompt for generators."""
        if not isinstance(script, dict):
            return script
        cuts = script.get("cuts")
        if not isinstance(cuts, list):
            return script
        style_prefix = f"Style: {IMAGE_PROMPT_REQUIRED_STYLE}"
        simple_cartoon_only = BaseLLMService._simple_cartoon_visuals(config or {})
        visual_world = BaseLLMService._compiled_visual_world(script)
        for cut in cuts:
            if not isinstance(cut, dict):
                continue
            original_prompt = image_prompt_safe_text(cut.get("image_prompt") or "")
            year = image_prompt_safe_text(cut.get("visual_year"), allow_year_normalization=True)
            period = image_prompt_safe_text(cut.get("visual_period"))
            original_period = period
            period = drop_conflicting_visual_period(year, period)
            if original_period and not period:
                cut["visual_period"] = ""
            location = image_prompt_safe_text(cut.get("visual_location"))
            evidence = image_prompt_safe_text(cut.get("visual_evidence"))
            subject = image_prompt_safe_text(cut.get("visual_subject") or cut.get("main_subject") or "")
            explicit_scene = image_prompt_safe_text(cut.get("visual_scene"))
            if not (year or period or location or evidence or subject or explicit_scene):
                if original_prompt:
                    if IMAGE_PROMPT_REQUIRED_STYLE.lower() not in original_prompt.lower():
                        cut["image_prompt"] = f"{style_prefix}; {original_prompt}"
                    continue
                cut["image_prompt"] = style_prefix
                continue
            scene = explicit_scene or original_prompt
            scene = BaseLLMService._strip_compiled_image_prompt(scene, style_prefix)

            scene_parts: list[str] = []
            if subject:
                scene_parts.append(f"Main subject: {subject}")
            if scene:
                scene_parts.append(f"Scene: {scene}")
            scene_text = "; ".join(scene_parts)

            if simple_cartoon_only:
                cut["image_prompt"] = "; ".join(part for part in (visual_world, style_prefix, scene_text) if part)
                continue

            prefix_parts: list[str] = []
            year_period = "; ".join(part for part in (year, period) if part)
            if year_period:
                prefix_parts.append(f"Year/period: {year_period}")
            if location:
                prefix_parts.append(f"Exact place: {location}")
            if evidence:
                prefix_parts.append(f"Scene evidence: {evidence}")
            if not (prefix_parts or scene_text):
                continue
            prompt_parts = ([visual_world] if visual_world else []) + prefix_parts + [style_prefix]
            if scene_text:
                prompt_parts.append(scene_text)
            cut["image_prompt"] = "; ".join(part for part in prompt_parts if part)
        return script

    @staticmethod
    def normalize_v31_story_contract(script: dict, config: dict | None = None, topic: str = "") -> dict:
        """Repair inline V3.1 story metadata so script validation follows actual cuts."""
        if not isinstance(script, dict):
            return script
        if str(script.get("script_version") or "").strip() != "3.1":
            return script
        cuts = script.get("cuts")
        if not isinstance(cuts, list) or not cuts:
            return script

        total_cuts = len(cuts)
        expected_blocks = max(1, math.ceil(total_cuts / 10))
        topic_text = str(topic or script.get("title") or "episode").strip() or "episode"

        core = script.get("story_core")
        if not isinstance(core, dict):
            core = {}
        core_defaults = {
            "story_axis": topic_text,
            "episode_scope": topic_text,
            "central_question": topic_text,
            "central_answer": topic_text,
            "protagonist": topic_text,
            "goal": topic_text,
            "obstacle": topic_text,
            "first_turn": topic_text,
            "mid_crisis": topic_text,
            "cost": topic_text,
            "ending_memory": topic_text,
        }
        for key, fallback in core_defaults.items():
            if not str(core.get(key) or "").strip():
                core[key] = fallback
        script["story_core"] = core

        raw_blocks = script.get("scene_blocks")
        source_blocks = raw_blocks if isinstance(raw_blocks, list) else []

        def _source_block(block_id: int) -> dict:
            for block in source_blocks:
                if not isinstance(block, dict):
                    continue
                try:
                    if int(block.get("block_id") or 0) == block_id:
                        return block
                except (TypeError, ValueError):
                    continue
            if 0 <= block_id - 1 < len(source_blocks) and isinstance(source_blocks[block_id - 1], dict):
                return source_blocks[block_id - 1]
            return {}

        def _text_value(block: dict, key: str, fallback: str) -> str:
            value = block.get(key)
            if isinstance(value, list):
                value = ", ".join(str(item).strip() for item in value if str(item).strip())
            value = str(value or "").strip()
            return value or fallback

        normalized_blocks: list[dict] = []
        for block_id in range(1, expected_blocks + 1):
            start = (block_id - 1) * 10 + 1
            end = min(block_id * 10, total_cuts)
            block = _source_block(block_id)
            block_label = f"cuts {start}-{end}"
            normalized_blocks.append({
                "block_id": block_id,
                "cut_range": f"{start}-{end}",
                "block_role": _text_value(block, "block_role", "script segment"),
                "block_goal": _text_value(block, "block_goal", block_label),
                "mini_question": _text_value(block, "mini_question", topic_text),
                "new_information": _text_value(block, "new_information", block_label),
                "key_facts": block.get("key_facts") if isinstance(block.get("key_facts"), list) and block.get("key_facts") else [topic_text],
                "continuity_from_previous": _text_value(block, "continuity_from_previous", "continues previous cut flow" if block_id > 1 else "opening block"),
                "tension": _text_value(block, "tension", topic_text),
                "turn": _text_value(block, "turn", block_label),
                "required_script_moves": block.get("required_script_moves") if isinstance(block.get("required_script_moves"), list) and block.get("required_script_moves") else [block_label],
                "turn_to_next": _text_value(block, "turn_to_next", "next block" if block_id < expected_blocks else "ending"),
                "visual_rhythm": block.get("visual_rhythm") if isinstance(block.get("visual_rhythm"), list) and block.get("visual_rhythm") else ["wide", "medium", "detail"],
                "character_introductions": block.get("character_introductions") if isinstance(block.get("character_introductions"), list) else [],
                "must_include": block.get("must_include") if isinstance(block.get("must_include"), list) and block.get("must_include") else [topic_text],
                "must_avoid": block.get("must_avoid") if isinstance(block.get("must_avoid"), list) and block.get("must_avoid") else ["unverified claims"],
            })
        script["scene_blocks"] = normalized_blocks

        for idx, cut in enumerate(cuts, start=1):
            if not isinstance(cut, dict):
                continue
            try:
                cut_number = int(cut.get("cut_number") or idx)
            except (TypeError, ValueError):
                cut_number = idx
                cut["cut_number"] = idx
            block_id = min(expected_blocks, max(1, math.ceil(cut_number / 10)))
            cut["scene_block_id"] = block_id
        return script

    @staticmethod
    def _strip_compiled_image_prompt(prompt: str, style_prefix: str) -> str:
        """Keep only the creative scene body from old expanded image_prompt values."""
        out = str(prompt or "").strip()
        if not out:
            return ""
        out = re.sub(
            r"^\s*Global visual world:\s*.*?(?=(?:Year/period|Exact place|Scene evidence|Style|Main subject|Scene):)",
            "",
            out,
            flags=re.IGNORECASE | re.DOTALL,
        )
        out = re.sub(
            r"^\s*Year/period:\s*[^;]+(?:;\s*[^;]+)?;\s*"
            r"(?:Historically accurate period details:\s*[^;]+;\s*)?"
            r"(?:Exact place:\s*[^;]+;\s*)?"
            r"(?:Scene evidence:\s*[^;]+;\s*)?",
            "",
            out,
            flags=re.IGNORECASE,
        )
        out = re.sub(r"(?:^|;\s*)Style:\s*[^;]*;?", "; ", out, flags=re.IGNORECASE)
        out = re.sub(rf"\b{re.escape(IMAGE_PROMPT_REQUIRED_STYLE)}\b\s*;?", "", out, flags=re.IGNORECASE)
        out = re.sub(r"\s*;\s*", "; ", out).strip(" ;")
        out = re.sub(r"^\s*Scene:\s*", "", out, flags=re.IGNORECASE).strip(" ;")
        return out

    @staticmethod
    def _simple_cartoon_visuals(config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        mode = str(config.get("visual_mode") or config.get("image_visual_mode") or "").strip().lower()
        if mode in {"simple_cartoon", "webtoon", "office_parable"}:
            return True
        global_prompt = str(config.get("image_global_prompt") or "").lower()
        required = str(config.get("content_required") or "").lower()
        return (
            "the office parable" in required
            or "korean youtube explainer cartoon" in global_prompt
            or "clean 2d webtoon" in global_prompt
        )

    @staticmethod
    def validate_script_timing(script: dict, config: dict) -> list[dict]:
        """Return timing issues for generated narrations without mutating script."""
        limits = BaseLLMService._calc_narration_limits(config)
        lang = limits.get("lang") or config.get("language", "ko")
        target_range = str(limits.get("validation_range") or limits.get("target_range") or "")
        char_target_range = str(limits.get("char_target_range") or "")
        try:
            low_s, high_s = target_range.split("~", 1)
            low = int(low_s)
            high = int(high_s)
        except Exception:
            return []
        char_low = char_high = None
        if char_target_range:
            try:
                char_low_s, char_high_s = char_target_range.split("~", 1)
                char_low = int(char_low_s)
                char_high = int(char_high_s)
            except Exception:
                char_low = char_high = None

        exempt_texts = {
            "아름다운 우리 역사, 10분 역공입니다.",
            "역사는 현재의 거울이라고 합니다.",
            "사실을 바로 알고, 옳고 그름을 스스로 판단하는 것.",
            "그게 우리가 역사를 공부하는 진짜 이유 아닐까요.",
            "구독과 좋아요, 알림 설정 잊지 마세요.",
        }

        issues: list[dict] = []
        for cut in (script or {}).get("cuts", []) or []:
            narration = (cut.get("narration") or "").strip()
            if not narration:
                continue
            if narration in exempt_texts:
                continue
            spoken = narration
            try:
                if lang == "ja":
                    from app.services.tts.narration_source import get_cut_tts_narration

                    spoken = get_cut_tts_narration(cut, config, narration) or narration
                from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts
                spoken = prepare_spoken_narration_for_tts(spoken, lang) or spoken
            except Exception:
                spoken = narration
            if lang in ("ko", "ja"):
                amount = len(spoken)
                unit = "chars"
                if amount < low or amount > high:
                    issues.append({
                        "cut_number": cut.get("cut_number"),
                        "amount": amount,
                        "unit": unit,
                        "target_range": target_range,
                        "narration": narration,
                    })
            else:
                word_amount = len(re.findall(r"\b[\w'-]+\b", spoken))
                if word_amount < low or word_amount > high:
                    issues.append({
                        "cut_number": cut.get("cut_number"),
                        "amount": word_amount,
                        "unit": "words",
                        "target_range": target_range,
                        "narration": narration,
                    })
                if char_low is not None and char_high is not None:
                    char_amount = len(spoken)
                    if char_amount < char_low or char_amount > char_high:
                        issues.append({
                            "cut_number": cut.get("cut_number"),
                            "amount": char_amount,
                            "unit": "chars",
                            "target_range": char_target_range,
                            "narration": narration,
                        })
        return issues

    @staticmethod
    def assert_script_timing(script: dict, config: dict):
        issues = BaseLLMService.validate_script_timing(script, config)
        if not issues:
            return
        preview = ", ".join(
            f"cut {i.get('cut_number')}={i.get('amount')}{i.get('unit')}"
            for i in issues[:12]
        )
        if len(issues) > 12:
            preview += f", ... (+{len(issues) - 12})"
        target = issues[0].get("target_range")
        limits = BaseLLMService._calc_narration_limits(config)
        raise ValueError(
            f"script narration timing failed: target {limits.get('target_min_sec')}~"
            f"{limits.get('target_max_sec')}s ({target}), {preview}"
        )

    @staticmethod
    def _script_timing_retry_instruction(config: dict, issues: list[dict]) -> str:
        limits = BaseLLMService._calc_narration_limits(config)
        target_range = str(limits.get("target_range") or "")
        validation_range = str(limits.get("validation_range") or target_range)
        lang = limits.get("lang") or normalize_language_code((config or {}).get("language", "ko"))
        unit = "chars" if lang in ("ko", "ja") else "words"
        preview = ", ".join(
            f"cut {issue.get('cut_number')}={issue.get('amount')}{issue.get('unit')}"
            for issue in (issues or [])[:15]
        )
        if len(issues or []) > 15:
            preview += f", ... (+{len(issues) - 15})"
        return (
            "이전 응답은 내레이션 길이 검증에 실패했습니다.\n"
            f"- 모든 narration은 실제 TTS 기준 {limits.get('target_min_sec')}~{limits.get('target_max_sec')}초 안에 들어와야 합니다.\n"
            f"- 작성 목표 범위: {target_range} {unit}.\n"
            f"- 저장 검증 범위: {validation_range} {unit}. 이 상한을 넘는 컷이 하나라도 있으면 실패입니다.\n"
            f"- 실패 컷: {preview}.\n"
            "- 이번 응답은 전체 JSON을 처음부터 다시 작성하세요. 실패한 narration을 길게 유지하지 마세요.\n"
            "- 각 컷은 핵심 정보 하나만 말하고, 원인/결과/압박 중 하나만 짧게 붙이세요.\n"
            "- 쉼표가 두 번 이상 필요한 문장은 실패입니다. 한 문장 또는 짧은 두 절로 끝내세요.\n"
            "- 이미지 필드와 V3.1 구조는 유지하되 narration만 반드시 더 짧게 설계하세요."
        )

    async def generate_tags(
        self,
        title: str,
        topic: str,
        narration: str = "",
        max_tags: int = 15,
        language: str = "ko",
    ) -> list[str]:
        """YouTube 업로드용 태그 추천.

        기본 구현은 빈 리스트를 반환합니다. 구체 서비스(ClaudeService,
        GPTService 등)에서 오버라이드 하세요. 호출자(youtube 라우터)는
        실패 시 휴리스틱 폴백을 사용하므로, 예외 대신 빈 리스트 반환으로
        "구현 안 됨" 을 표현하는 편이 안전합니다.
        """
        return []

    async def generate_metadata(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        max_tags: int = 15,
        episode_number: Optional[int] = None,
    ) -> dict:
        """title_hook / description / tags 를 한 번에 생성.

        반환 형태: {"title_hook": str, "description": str, "tags": [str, ...]}
        `episode_number` 가 주어지면 LLM 에게 짧은 hook 만 쓰라고 지시합니다.
        backend 쪽에서 최종 title 은 "{title_hook} EP.N" 형식으로 조립합니다.
        기본 구현은 빈 dict. 구체 LLM 서비스에서 오버라이드.
        """
        return {}

    async def generate_thumbnail_image_prompt(
        self,
        title: str,
        topic: str,
        narration: str = "",
        language: str = "ko",
        character_description: str = "",
    ) -> str:
        """YouTube 썸네일용 image generation 프롬프트를 한 줄로 생성.

        기본 구현은 LLM 호출 없이 템플릿 폴백을 반환합니다. Claude / GPT 서비스는
        오버라이드해서 영화적 프롬프트를 뽑아냅니다. 반환 문자열은 이미지 모델
        (DALL-E / Nano Banana / Flux 등) 에 그대로 전달됩니다.

        `character_description` 이 주어지면 썸네일 이미지에 반드시 그 캐릭터가
        포함되도록 프롬프트를 구성합니다.
        """
        return self._fallback_thumbnail_prompt(title, topic, language, character_description)

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
        """Rewrite one cut narration so TTS duration lands inside the target window."""
        raise NotImplementedError("This LLM service does not support narration timing rewrite")

    @staticmethod
    def _build_narration_timing_prompt(
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
        lang_name = BaseLLMService._language_name(language)
        current = (narration or "").strip()
        current_amount = len(current)
        nonspace = len("".join(current.split()))
        unit = "total characters"
        tolerance = "+/- 2 characters"
        current_length = f"{current_amount} total characters, {nonspace} non-space characters"
        issue = "too short" if direction == "short" else "too long"
        action = (
            "add one concrete detail while preserving the meaning"
            if direction == "short"
            else "compress wording while preserving the meaning"
        )
        return (
            "Rewrite exactly ONE narration line for TTS timing.\n"
            "Return a single JSON object only: {\"narration\":\"...\"}\n\n"
            f"Language: {lang_name} ({language}). The rewritten narration MUST be in this language only.\n"
            f"Video topic: {topic or '(none)'}\n"
            f"Cut: {cut_number}/{total_cuts}, scene_type: {scene_type or '(none)'}\n"
            f"Image prompt context: {image_prompt or '(none)'}\n"
            f"Previous narration: {previous_narration or '(none)'}\n"
            f"Next narration: {next_narration or '(none)'}\n\n"
            f"Current narration: {current}\n"
            f"Current measured TTS duration: {measured_duration:.2f}s, which is {issue}.\n"
            f"Required duration window: {target_min:.1f}~{target_max:.1f}s.\n"
            f"Current length: {current_length}.\n"
            f"Target length: around {target_chars} {unit}, tolerance {tolerance}.\n"
            f"Hard upper limit: never exceed {target_chars + 2} total characters unless a proper noun makes it impossible.\n\n"
            "Hard rules:\n"
            f"- {action}; do NOT change the factual meaning or emotional beat.\n"
            "- Preserve the original speech level and sentence ending style exactly. "
            "If the original is polite/formal Korean, the rewrite must stay polite/formal Korean.\n"
            "- Never use casual Korean endings like '알아?', '아?', '냐?', '니?', '야?', '거야?', "
            "or cheap hook phrasing like '~거란 걸 알아?'.\n"
            "- Preserve every number, year, named entity, and factual claim. Do not introduce new numbers.\n"
            "- Do NOT solve timing by mentioning speech speed, pauses, audio editing, or stage directions.\n"
            "- Do NOT add filler/tag-on phrases such as '정말로요.', '맞죠.', '그렇죠.', "
            "'이 지점입니다.', '이게 시작입니다.', '여기서 갈립니다.', '여기서부터죠.', "
            "'이제 시작이죠.', or '그게 핵심입니다.'. They create extra TTS pauses and damage script quality.\n"
            "- If the line is too long, remove clauses or pause-heavy wording; do not add a new sentence.\n"
            "- If the line is too short, add one concrete meaningful detail, not a generic filler ending.\n"
            f"- The only acceptable timing target is the configured voice's {target_min:.1f}~{target_max:.1f}s window.\n"
            "- Do NOT add brackets, labels, quotes, SSML, markdown, or multiple alternatives.\n"
            "- Keep it natural spoken narration, one line, no newline.\n"
            "- Prefer one sentence unless the original clearly needs two.\n"
            "- Output JSON only."
        )

    @staticmethod
    def _parse_narration_rewrite_response(raw: str) -> str:
        import json
        import re

        text = (raw or "").strip()
        candidates: list[str] = []
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            candidates.append(match.group(1).strip())
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            candidates.append(match.group(0).strip())
        candidates.append(text)

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            value = parsed.get("narration") if isinstance(parsed, dict) else None
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())

        return " ".join(text.strip('"').split())

    @staticmethod
    def _fallback_thumbnail_prompt(
        title: str,
        topic: str,
        language: str,
        character_description: str = "",
    ) -> str:
        """LLM 호출 없이 쓰는 최소 폴백. 영어로 고정 — 대부분의 이미지 모델이 영어
        프롬프트에 가장 잘 반응하기 때문. 영상 자체의 언어(`language`)와는 별개.

        v1.1.33: "후킹 최대화" 폴백. 한 장짜리 Mrbeast/Nas-Daily/Veritasium 스타일
        썸네일을 노리고 설계됨. 특징:

        1. 정서적 후크를 맨 앞에 박아 이미지 모델이 감정을 먼저 읽도록 유도
        2. 레퍼런스 이미지가 같이 넘어올 때를 가정해 "레퍼런스 스타일 그대로"
           라는 지시를 명시. (실제로 reference_images 를 넘길지 여부는 호출부에서
           결정하고, 넘기지 않았다면 이 문장은 순수 지시문으로만 남음.)
        3. 한 개의 압도적 피사체 + 빈 네거티브 스페이스 규칙 강제
        4. 휴대폰 화면에서 1~2초 안에 스캔되는 대비/채도 강제
        5. 썸네일 안에 글자를 그리지 말라는 하드 네거티브
        """
        t = (title or "").strip() or "untitled video"
        tp = (topic or "").strip()
        tp_clause = f"Topic: {tp}. " if tp else ""
        char = (character_description or "").strip()
        if char:
            subject_clause = (
                f"THE hero subject MUST be this character, unmistakable and center of "
                f"attention: {char}. Render as an extreme close-up, full face clearly "
                f"visible, front-facing or three-quarter view, head and shoulders in "
                f"frame, eyes nose and mouth visible, face filling 40-55% "
                f"of the frame, offset to the left or right third so 35-45% of the "
                f"opposite side remains clean negative space for text overlay later. The character's "
                f"facial expression must be EXAGGERATED and emotionally loud — pick ONE "
                f"from: wide-eyed shock, jaw-drop awe, intense determination with furrowed "
                f"brow, explosive laugh, cinematic tears, gritted-teeth rage — whichever "
                f"best matches the hook. Eyes must be razor sharp and locked toward the "
                f"viewer. "
            )
        else:
            subject_clause = (
                f"ONE dominant hero subject — choose the most clickable story-critical person or "
                f"human-like character from the story when one exists. Render that "
                f"subject as an extreme face close-up with full face clearly visible, "
                f"front-facing or three-quarter view, head and shoulders in frame, eyes "
                f"nose and mouth visible, and exaggerated emotion. Use one single "
                f"story-critical object only when the topic has no usable person. "
                f"Fills 40-55% of the frame, offset to the left or right third, leaving "
                f"35-45% clean negative space on the opposite side for later text overlay. "
                f"Razor sharp focus on the eyes or the key edge of the object. "
            )
        return (
            f'A scroll-stopping, tabloid-intense but fact-locked YouTube thumbnail for a video titled "{t}". '
            f"{tp_clause}"
            f"PRIMARY GOAL: within 1 second on a 2-inch phone screen, the viewer must "
            f"feel the strongest factual stake from the story (fatal consequence, forbidden "
            f"secret, betrayal, explosive rage, public humiliation, collapse evidence, "
            f"or last warning before disaster). "
            f"{subject_clause}"
            f"PROVOCATION RULE: amplify only what is already in the title/topic/narration. "
            f"Make the image feel like the exact second before disaster, revelation, or "
            f"irreversible collapse. Never invent gore, crimes, symbols, accusations, "
            f"numbers, killers, or causes of death not present in the story. "
            f"STYLE REFERENCE: if reference images are provided alongside this prompt, "
            f"faithfully follow THEIR exact art direction — same palette, same rendering "
            f"technique (photoreal vs illustration vs anime vs 3D), same line/brush "
            f"character, same overall mood. Treat the references as ground truth for "
            f"visual style and only deviate for composition. "
            f"LIGHTING: dramatic three-point lighting, strong rim light, warm key, cool "
            f"fill, deep crushed shadows. Avoid flat or even lighting. "
            f"COLOR: ultra-high contrast, saturation pushed for mobile readability — "
            f"use one accent color that matches the story's emotion, with genuinely "
            f"black shadows. No washed-out pastels and no fixed repeated palette. "
            f"DEPTH: shallow depth of field, creamy bokeh background with a single "
            f"atmospheric highlight so nothing competes with the hero. "
            f"COMPOSITION: 16:9 landscape, rule-of-thirds, extremely readable silhouette. "
            f"QUALITY: high-resolution documentary cartoon thumbnail, clean bold shapes, "
            f"editorial-grade YouTube creator production value. "
            f"HARD NEGATIVE — nothing of the following may appear in the image: "
            f"text, words, letters, numbers, captions, logos, watermarks, typography, "
            f"subtitles, signs, UI chrome, blurry faces, low resolution, flat lighting, "
            f"cluttered backgrounds, generic stock-photo vibes, extra limbs, warped hands, "
            f"torso-only framing, body-only framing, cropped head, cropped face, back view, "
            f"hidden face, faceless silhouette, blank face, featureless face."
        )

    @classmethod
    def _build_thumbnail_prompt_request(
        cls,
        title: str,
        topic: str,
        narration: str,
        language: str,
        character_description: str = "",
    ) -> str:
        """LLM 에게 '이미지 생성 프롬프트'를 써달라고 시키는 메타-프롬프트.

        `character_description` 이 주어지면 썸네일에 반드시 그 캐릭터가 중심
        피사체로 등장하도록 강제합니다.
        """
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 1500)
        char = (character_description or "").strip()
        char_block = ""
        if char:
            char_block = (
                f"\n★★★ MANDATORY CHARACTER — the thumbnail MUST contain this character "
                f"as the primary focal subject:\n{char}\n"
                f"The character must be clearly visible, centered, and unmistakable. "
                f"The full face must be visible in frame: front-facing or three-quarter "
                f"view, head and shoulders visible, eyes nose and mouth visible, sharp "
                f"eyes, readable expression. Describe the character's appearance "
                f"(clothing, face, expression, pose, "
                f"colors) directly inside the image prompt you write. Without an explicit "
                f"character description in the prompt, the image model will NOT render "
                f"the character. Keep the art style consistent with the rest of the video.\n"
            )
        return (
            f"You are a senior YouTube thumbnail image-prompt engineer. Your prompts are "
            f"used by top creators (MrBeast, Veritasium, Kurzgesagt, Yes Theory style "
            f"studios) to win the 1-second click-through battle on a phone screen.\n"
            f"\n"
            f"Write ONE single-paragraph image generation prompt that another AI "
            f"(Nano Banana / Gemini Flash Image / DALL-E 3 / Flux / SDXL / similar) "
            f"will use to produce a 1280x720 (16:9) YouTube thumbnail image.\n"
            f"{char_block}"
            f"\n"
            f"★ STYLE REFERENCE LOCK (critical) — assume the user will feed reference/"
            f"character images into the same image model alongside your prompt. Your "
            f"prompt MUST explicitly instruct the model to:\n"
            f" • Treat the reference images as ground truth for art direction.\n"
            f" • Match the reference's exact rendering technique (photoreal vs "
            f"illustration vs anime vs 3D vs painterly), color palette, lighting mood, "
            f"line/brush character, and texture feel.\n"
            f" • Preserve recognizable character identity exactly as depicted in the "
            f"references (face shape, hair, costume, props).\n"
            f" • Only deviate from references for composition (camera angle, framing, "
            f"expression intensity) — never for style.\n"
            f"Include a sentence like: 'Follow the EXACT visual style, palette, and "
            f"rendering technique of the reference images.'\n"
            f"\n"
            f"★ CORE COMPOSITION RULES the generated image MUST satisfy:\n"
            f"1. ONE unmistakable hero subject (the mandatory character above if given, "
            f"otherwise the most clickable story-critical person or human-like character if the story has one; "
            f"use an event object, artifact, evidence, or decisive moment only when "
            f"there is no usable person). It must be a close-up. No crowds, no group shots, no "
            f"wide scene, no distant subject, no split attention.\n"
            f"2. The hero fills 40-55% of the frame and is offset to the LEFT or RIGHT "
            f"third — leave 35-45% deliberate clean negative space on the opposite side "
            f"so text can be composited later. Describe this negative space explicitly.\n"
            f"3. FACE VISIBILITY: if the story contains a person or human-like character, "
            f"the thumbnail hero must be that character's full visible face, front-facing "
            f"or three-quarter view, head and shoulders in frame, eyes nose and mouth "
            f"visible. Never use torso-only, body-only, cropped head, cropped face, back "
            f"view, hidden face, faceless silhouette, blank face, or featureless face.\n"
            f"4. FACT-LOCKED PROVOCATION (most important): choose ONE strongest factual "
            f"trigger from the title/topic/narration — fatal consequence, forbidden "
            f"secret, betrayal signal, explosive rage, public humiliation, collapse "
            f"evidence, or a last-warning object right before disaster. The thumbnail "
            f"must feel sharper than a calm history illustration, but never invent gore, "
            f"crimes, symbols, accusations, numbers, killers, or causes of death not "
            f"present in the story.\n"
            f"5. EMOTIONAL HOOK: if a human/character face is the hero, "
            f"describe ONE exaggerated loud emotion — wide-eyed shock, jaw-drop awe, "
            f"intense glare with furrowed brow, explosive laugh, cinematic tears, "
            f"gritted-teeth rage — whichever best matches the narration tone. Neutral "
            f"faces do NOT click.\n"
            f"6. Razor sharp focus on the subject's eyes (or the object's key edge). "
            f"Creamy bokeh background. Shallow depth of field.\n"
            f"7. Lighting: dramatic three-point, strong rim light, warm key / cool fill, "
            f"high contrast, genuinely black shadows. No flat even lighting.\n"
            f"8. Colors: phone-screen-friendly contrast with ONE story-matched accent color "
            f"(danger/betrayal can use red, power can use gold, mystery/records can use cyan, "
            f"war/night can use deep blue, collapse can use gray-red). Avoid a fixed repeated palette.\n"
            f"9. Single scroll-stopping hook (mystery, awe, tension, fear, triumph, "
            f"disgust, humor). Pick ONE that best fits the narration — do not hedge.\n"
            f"10. Rendering style: default high-resolution documentary cartoon thumbnail with "
            f"clean bold shapes, BUT if the reference images show another style, mirror that style exactly.\n"
            f"11. 16:9 landscape framing. Never portrait, never square.\n"
            f"12. Optional high-impact visual props — impossible scale, juxtaposition, "
            f"floating elements, a single shocking contrast — only if they are supported by the topic.\n"
            f"\n"
            f"★ HARD NEGATIVES — include this clause verbatim in your output prompt:\n"
            f'"no text, no words, no letters, no numbers, no captions, no logos, no '
            f'watermarks, no typography, no subtitles, no signs, no UI chrome, no '
            f'blurry face, no warped hands, no extra limbs, no low resolution, no flat '
            f'lighting, no cluttered background, no generic stock photo look, no '
            f'torso-only framing, no body-only framing, no cropped head, no cropped face, '
            f'no back view, no hidden face, no faceless silhouette, no blank face, no '
            f'featureless face". '
            f"Text will be composited later by Pillow — the image itself must be "
            f"completely text-free.\n"
            f"\n"
            f"★ LANGUAGE RULE — write the image prompt itself in ENGLISH (image models "
            f"respond best to English), even though the narration below is in {lang_name}. "
            f"Keep proper nouns (people, places, landmarks, historical figures) in their "
            f"original form so the model can recognize them.\n"
            f"\n"
            f"★ LENGTH — the prompt should be one dense paragraph, roughly 80-140 words. "
            f"Do not stop at 30 words; image models benefit from specific detail.\n"
            f"\n"
            f'Return ONLY a JSON object of the form {{"prompt": "..."}} — a single string '
            f"value, no extra keys, no commentary, no markdown fences.\n"
            f"\n"
            f"Video title: {title or '(none)'}\n"
            f"Video topic: {topic or '(none)'}\n"
            f"Narration excerpt:\n{snippet}\n"
        )

    @classmethod
    def _parse_thumbnail_prompt_response(cls, text: str) -> Optional[str]:
        data = cls._extract_json_object(text)
        if not data:
            return None
        p = data.get("prompt")
        if isinstance(p, str):
            cleaned = p.strip()
            if cleaned:
                return cleaned
        return None

    # ─── 프롬프트 빌더 ───

    @staticmethod
    def _language_name(code: str) -> str:
        """LLM 프롬프트에 넣을 언어 표시 이름."""
        code = normalize_language_code(code)
        return {
            "ko": "Korean (한국어)",
            "en": "English",
            "hi": "Hindi",
            "ja": "Japanese (日本語)",
            "zh": "Chinese (中文)",
            "es": "Spanish (Español)",
            "fr": "French (Français)",
            "de": "German (Deutsch)",
        }.get((code or "ko").lower(), code or "Korean")

    @staticmethod
    def _clip_snippet(text: str, limit: int = 1500) -> str:
        t = (text or "").strip()
        if len(t) <= limit:
            return t or "(none)"
        return t[:limit] + "..."

    @classmethod
    def _build_tag_prompt(
        cls,
        title: str,
        topic: str,
        narration: str,
        max_tags: int,
        language: str = "ko",
    ) -> str:
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 1200)
        return (
            f"You are a YouTube SEO assistant.\n"
            f"\n"
            f"★ CRITICAL LANGUAGE RULE ★\n"
            f"All tags you produce MUST be written in {lang_name}. "
            f"Do NOT mix other languages. If the source is in {lang_name}, every single tag "
            f"is in {lang_name}. No translations, no transliterations of English into "
            f"{lang_name}, no mixing.\n"
            f"\n"
            f"Task: Produce as many useful YouTube tags as possible, ideally {max_tags}, "
            f"while staying under YouTube tag limits. The tags must help this specific "
            f"long-form video be discovered. Mix broad category tags AND specific topical "
            f"tags drawn from the title / topic / script excerpt. Each tag under 30 "
            f"characters. No # symbols. No duplicates.\n"
            f"\n"
            f'Return ONLY a JSON object of the form {{"tags": ["tag1", "tag2", ...]}} '
            f"with no extra commentary.\n"
            f"\n"
            f"Title: {title or '(none)'}\n"
            f"Topic: {topic or '(none)'}\n"
            f"Script excerpt: {snippet}\n"
        )

    @classmethod
    def _build_metadata_prompt(
        cls,
        title: str,
        topic: str,
        narration: str,
        language: str = "ko",
        max_tags: int = 15,
        episode_number: Optional[int] = None,
    ) -> str:
        lang_name = cls._language_name(language)
        snippet = cls._clip_snippet(narration, 2500)

        # CJK 언어는 글자 수가 기준, 서구권은 문자 수가 기준.
        is_cjk = (language or "ko").lower() in {"ko", "ja", "zh", "zh-cn", "zh-tw"}
        hook_limit = 24 if is_cjk else 62
        hook_rule_label = (
            f"{hook_limit}자 이하 (공백 포함)" if is_cjk else f"{hook_limit} characters max"
        )

        ep_block = ""
        if episode_number is not None:
            ep_block = (
                f"\n★ EPISODE MODE ★\n"
                f"This video is Episode #{episode_number} of a running series. The backend "
                f"will append 'EP.{episode_number:02d}' to your hook automatically, so "
                f'your "title_hook" MUST NOT include the words "EP", "Episode", "에피소드", '
                f'"제{episode_number}화", or the number itself. Write ONLY the short hook '
                f"before the episode label.\n"
            )

        return (
            f"You are writing YouTube metadata for a long-form video.\n"
            f"\n"
            f"★ CRITICAL LANGUAGE RULE ★\n"
            f"EVERY field you output — title_hook, description, and every tag — MUST be "
            f"written in {lang_name} only. Do NOT mix languages. The video's narration is "
            f"in {lang_name} so the metadata must match exactly. No translations, no "
            f"transliterations, no romanizations, no foreign-language subtitles in the "
            f"description.\n"
            f"{ep_block}"
            f"\n"
            f"Task: based on the source material below, produce a SHORT but aggressive hook line, a rich "
            f"long description, and a tag list.\n"
            f"\n"
            f"Output format — return ONLY a single JSON object with these keys:\n"
            f'  - "title_hook": string. {hook_rule_label}. Written in {lang_name}. '
            f"A single short, high-tension, provocative hook phrase — NOT a full sentence, NOT fake clickbait "
            f"ellipsis, NO emojis, NO quotation marks, NO trailing punctuation. "
            f"Use hard story words when the source supports them: fatal, death, lost, poison, collapse, betrayal, "
            f"no proof, mistake, secret, truth, burned, drowned, assassination. Do not invent any event, victim, "
            f"number, motive, or outcome that is not supported by the source. "
            f"Think of it as what goes BEFORE the trailing episode label. Examples of good style: "
            f"'죽음이 갈랐다', 'The Death That Split an Empire', 'Peace That Lost England', '燃えた王の真実'. "
            f"Examples of bad: full sentences, questions, anything over the limit.\n"
            f'  - "description": string. 900 to 1800 characters. Written in {lang_name}. '
            f"Structure: (1) a 2-3 sentence hook that makes the viewer want to watch, "
            f"(2) a 3-5 sentence summary of what the video covers, "
            f"(3) 4-6 bullet-style lines listing key points or chapter highlights "
            f"(use '•' or '-' as the bullet marker), "
            f"(4) a short closing line inviting likes/comments/subscribes. "
            f"Separate the sections with blank lines and natural line breaks. Plain text only — no markdown headers.\n"
            f'  - "tags": JSON array with as many useful tags as possible, ideally {max_tags} strings. Each tag under 30 '
            f"characters. All in {lang_name}. No # symbols. No duplicates. "
            f"Mix broad category tags, niche topical tags, people/place/event tags, and search-intent tags.\n"
            f"\n"
            f"Do not output anything outside the JSON object.\n"
            f"\n"
            f"Source title hint: {title or '(none)'}\n"
            f"Source topic: {topic or '(none)'}\n"
            f"Narration excerpt:\n{snippet}\n"
        )

    # ─── 응답 파서 ───

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        """LLM 응답에서 첫 JSON 객체를 뽑아 dict 반환. 실패 시 None."""
        import json as _json
        import re as _re

        if not text:
            return None
        m = _re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
        candidate = m.group(1) if m else None
        if candidate is None:
            m = _re.search(r"\{[\s\S]*\}", text)
            candidate = m.group(0) if m else None
        if candidate is None:
            return None
        try:
            data = _json.loads(candidate)
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _parse_tag_response(cls, text: str) -> list[str]:
        """LLM 응답에서 tags 배열 추출. 실패 시 빈 리스트."""
        data = cls._extract_json_object(text)
        if not data:
            return []
        tags = data.get("tags")
        if not isinstance(tags, list):
            return []
        result: list[str] = []
        for t in tags:
            if isinstance(t, str):
                cleaned = t.strip().lstrip("#").strip()
                if cleaned:
                    result.append(cleaned)
        return result

    @classmethod
    def _parse_metadata_response(cls, text: str) -> dict:
        """LLM 응답에서 {title_hook, description, tags} 추출. 누락 필드는 빈 값.

        구버전 호환: 응답에 `title` 키만 있고 `title_hook` 이 없으면 `title` 을
        `title_hook` 으로도 매핑합니다.
        """
        data = cls._extract_json_object(text)
        if not data:
            return {}
        out: dict = {}
        hook = data.get("title_hook")
        if isinstance(hook, str) and hook.strip():
            out["title_hook"] = hook.strip()
        # 구버전 호환: title 키도 흡수
        legacy_title = data.get("title")
        if isinstance(legacy_title, str) and legacy_title.strip():
            out.setdefault("title_hook", legacy_title.strip())
            out["title"] = legacy_title.strip()
        if isinstance(data.get("description"), str):
            out["description"] = data["description"].strip()
        raw_tags = data.get("tags")
        if isinstance(raw_tags, list):
            tags: list[str] = []
            for t in raw_tags:
                if isinstance(t, str):
                    c = t.strip().lstrip("#").strip()
                    if c:
                        tags.append(c)
            out["tags"] = tags
        return out

    def _get_system_prompt(self, config: dict) -> str:
        language = normalize_language_code(config.get("language", "ko"))
        prompt = get_system_prompt(language, config)
        retry_instruction = str((config or {}).get("__script_timing_retry_instruction") or "").strip()
        if retry_instruction:
            prompt += "\n\n내레이션 길이 재생성 지시:\n" + retry_instruction
        return prompt

    @staticmethod
    def _calc_narration_limits(config: dict) -> dict:
        """TTS 모델·속도 설정에 따라 나레이션 글자/단어 수 한도를 계산한다.

        Returns: {"max_chars": int, "target_range": str, "words_per_sec": float}
        (영어는 max_words / target_words_range 로 대체)
        """
        language = normalize_language_code(config.get("language", "ko"))
        try:
            speed = float(config.get("tts_speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        tts_model = config.get("tts_model", "openai-tts")

        # ElevenLabs 는 speed 를 [0.7, 1.2] 로 clamp
        if tts_model == "elevenlabs":
            speed = max(0.7, min(1.2, speed))
        # OpenAI 는 [0.25, 4.0]
        else:
            speed = max(0.25, min(4.0, speed))

        min_secs, max_secs, target_secs = _script_tts_target_window(config)

        if language == "ko":
            # 한국어 TTS: 27~28자 기준은 실제 ElevenLabs/OpenAI에서 3초대로
            # 떨어졌다. 컷 길이에 맞춰 목표 글자 수를 계산한다.
            chars_per_sec = _profiled_chars_per_sec(config, 10.0 * speed)
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.ceil(max_secs * chars_per_sec)))
            low = max(1, int(math.ceil(min_secs * chars_per_sec)))
            if low > max_chars:
                low = max_chars = target_chars
            validation_low = max(1, low - 1)
            validation_max_chars = max_chars
            return {
                "max_chars": max_chars,
                "target_range": f"{low}~{max_chars}",
                "validation_range": f"{validation_low}~{validation_max_chars}",
                "lang": "ko",
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }
        elif language == "ja":
            # 일본어 TTS: 24~26자는 실제 출력에서 교과서식 단문으로 고정되기
            # 쉬웠다. 컷 길이에 맞춰 목표 글자 수를 계산한다.
            chars_per_sec = _profiled_chars_per_sec(config, 9.4 * speed)
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.floor(max_secs * chars_per_sec)))
            low = max(1, int(math.ceil(min_secs * chars_per_sec)))
            if low > max_chars:
                low = max_chars = target_chars
            return {
                "max_chars": max_chars,
                "target_range": f"{low}~{max_chars}",
                "lang": "ja",
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }
        else:
            # 영어 TTS: 기본 ~2.5 단어/초
            words_per_sec = _profiled_words_per_sec(config, 2.7 * speed)
            chars_per_sec = _profiled_chars_per_sec(config, 13.0 * speed)
            extra_words = 0
            extra_chars = max(0, int(round(extra_words * (chars_per_sec / max(words_per_sec, 0.1)))))
            target_words = max(1, int(round(target_secs * words_per_sec)))
            max_words = max(1, int(math.floor(max_secs * words_per_sec)))
            low = max(1, int(math.ceil(min_secs * words_per_sec)) - (0 if language == "en" else 1))
            if low > max_words:
                low = max_words = target_words
            low += extra_words
            max_words += extra_words
            target_words += extra_words
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.floor(max_secs * chars_per_sec)))
            min_chars = max(1, int(math.ceil(min_secs * chars_per_sec)))
            target_chars += extra_chars
            max_chars += extra_chars
            min_chars += extra_chars
            return {
                "max_words": max_words,
                "target_range": f"{low}~{max_words}",
                "max_chars": max_chars,
                "char_target_range": f"{min_chars}~{max_chars}",
                "target_chars": target_chars,
                "lang": language,
                "words_per_sec": words_per_sec,
                "chars_per_sec": chars_per_sec,
                "target_min_sec": min_secs,
                "target_max_sec": max_secs,
                "target_sec": target_secs,
            }

    def _build_user_prompt(self, topic: str, config: dict) -> str:
        """Build only runtime input; all default script rules live in system prompt."""
        duration = config.get("target_duration", 600)
        style = config.get("style", "news_explainer")
        language = normalize_language_code(config.get("language", "ko"))
        forbidden_raw = (config.get("content_forbidden") or "").strip()
        required_raw = (config.get("content_required") or "").strip()
        legacy_raw = (config.get("content_constraints") or "").strip()
        use_legacy = bool(legacy_raw) and not forbidden_raw and not required_raw

        try:
            cut_count = int(config.get("target_cuts") or 0)
        except (TypeError, ValueError):
            cut_count = 0
        if cut_count <= 0:
            try:
                duration_int = max(5, int(duration))
            except (TypeError, ValueError):
                duration_int = 600
            cut_duration = resolve_cut_video_duration(config)
            cut_count = max(1, math.ceil(duration_int / cut_duration))
        cut_duration = resolve_cut_video_duration(config)
        duration_seconds = cut_count * cut_duration
        duration_int = int(round(duration_seconds)) if abs(duration_seconds - round(duration_seconds)) < 0.001 else duration_seconds

        character_description = (config.get("character_description") or "").strip()

        def _normalize_constraints(raw: str) -> str:
            s = raw.replace("\r\n", "\n")
            for sep in (" / ", " · "):
                s = s.replace(sep, "\n")
            lines = [ln.strip(" -•·").strip() for ln in s.split("\n")]
            lines = [ln for ln in lines if ln]
            return "\n".join(f"- {ln}" for ln in lines)

        def _build_constraints_block(lang: str) -> str:
            if not (use_legacy or required_raw or forbidden_raw):
                return ""
            if lang == "ja":
                header = "ユーザー入力制約"
                required = "[必須事項]"
                forbidden = "[禁止事項]"
                legacy = "[ユーザールール]"
            elif lang in ("en", "hi"):
                header = "USER INPUT CONSTRAINTS"
                required = "[REQUIRED]"
                forbidden = "[FORBIDDEN]"
                legacy = "[USER RULES]"
            else:
                header = "사용자 입력 제약"
                required = "[필수 사항]"
                forbidden = "[금지 사항]"
                legacy = "[사용자 규칙]"
            parts: list[str] = [header]
            if use_legacy:
                parts.extend([legacy, _normalize_constraints(legacy_raw)])
            else:
                if required_raw:
                    parts.extend([required, _normalize_constraints(required_raw)])
                if forbidden_raw:
                    if len(parts) > 1:
                        parts.append("")
                    parts.extend([forbidden, _normalize_constraints(forbidden_raw)])
            return "\n".join(parts).strip() + "\n\n"

        episode_openings_raw = config.get("episode_openings")
        episode_endings_raw = config.get("episode_endings")
        core_content_raw = (config.get("episode_core_content") or "").strip()
        ep_num_cfg = config.get("episode_number")
        try:
            ep_num_val = int(ep_num_cfg) if ep_num_cfg is not None else None
            if ep_num_val is not None and ep_num_val <= 0:
                ep_num_val = None
        except (TypeError, ValueError):
            ep_num_val = None
        next_ep_preview = (config.get("next_episode_preview") or "").strip()

        def _clean_lines(xs):
            if not isinstance(xs, list):
                return []
            return [str(x or "").strip() for x in xs if str(x or "").strip()]

        def _build_episode_block(lang: str) -> str:
            ep_openings = _clean_lines(episode_openings_raw)
            ep_endings = _clean_lines(episode_endings_raw)
            if not (ep_openings or ep_endings or core_content_raw or ep_num_val is not None or next_ep_preview):
                return ""
            if lang == "ja":
                header = "今回のエピソード入力"
                ep_num_label = "[エピソード番号]"
                core_label = "[核心内容]"
                openings_label = "[オープニング台詞]"
                endings_label = "[エンディング台詞]"
                next_label = "[次回予告]"
            elif lang in ("en", "hi"):
                header = "EPISODE INPUT"
                ep_num_label = "[EPISODE NUMBER]"
                core_label = "[CORE CONTENT]"
                openings_label = "[OPENING LINES]"
                endings_label = "[ENDING LINES]"
                next_label = "[NEXT EPISODE PREVIEW]"
            else:
                header = "이번 에피소드 입력"
                ep_num_label = "[에피소드 번호]"
                core_label = "[핵심 내용]"
                openings_label = "[오프닝 대사]"
                endings_label = "[엔딩 대사]"
                next_label = "[다음 에피소드 예고]"
            parts: list[str] = [header]
            if ep_num_val is not None:
                parts.extend([ep_num_label, f"Episode {ep_num_val}"])
            if core_content_raw:
                parts.extend([core_label, core_content_raw])
            if ep_openings:
                parts.append(openings_label)
                parts.extend(f"{i}. {line}" for i, line in enumerate(ep_openings, 1))
            if ep_endings:
                parts.append(endings_label)
                parts.extend(f"{i}. {line}" for i, line in enumerate(ep_endings, 1))
            if next_ep_preview:
                parts.extend([next_label, next_ep_preview])
            return "\n".join(parts).strip() + "\n\n"

        labels = {
            "ko": ("주제", "목표 길이", "정확한 컷 수", "스타일", "언어", "한국어"),
            "ja": ("トピック", "目標時間", "正確なカット数", "スタイル", "言語", "日本語"),
            "en": ("Topic", "Target duration", "Exact cut count", "Style", "Language", "English"),
            "hi": ("Topic", "Target duration", "Exact cut count", "Style", "Language", "Hindi"),
        }
        topic_label, duration_label, cuts_label, style_label, language_label, language_name = labels.get(language, labels["ko"])
        story_plan = self._story_plan_for_script(topic, config)
        story_plan_block = ""
        if isinstance(story_plan, dict):
            if language == "ja":
                plan_header = "事前ストーリー設計"
                plan_rule = (
                    "下の story_core と scene_blocks を今回の大本として使います。"
                    "causality_chain、fact_ledger、visual_plan も固定設計として使います。"
                    "出力 JSON の story_core/scene_blocks はこれと同じ構造・同じ block_id/cut_range を保ち、"
                    "story_axis もそのまま保ち、cuts は必ず該当 scene_block に従って書いてください。"
                )
            elif language in ("en", "hi"):
                plan_header = "PRE-GENERATED STORY PLAN"
                plan_rule = (
                    "Use this story_core and scene_blocks as the binding structure for this script. "
                    "Use causality_chain, fact_ledger, and visual_plan as fixed generation instructions. "
                    "Preserve story_axis, keep the same block_id and cut_range values in the output, and write every cut under its scene_block."
                )
            else:
                plan_header = "사전 스토리 설계"
                plan_rule = (
                    "아래 story_core와 scene_blocks는 이번 대본의 고정 구조입니다. "
                    "causality_chain, fact_ledger, visual_plan은 사건 순서, 사실 경계, 이미지 리듬의 고정 설계입니다. "
                    "출력 JSON의 story_core/scene_blocks는 story_axis와 block_id/cut_range를 그대로 유지하고, "
                    "모든 cuts는 자기 cut_number가 속한 scene_block에 맞춰 작성하세요."
                )
            story_plan_block = (
                f"{plan_header}\n"
                f"{plan_rule}\n"
                f"{json.dumps(self._strip_story_plan_runtime_fields(story_plan), ensure_ascii=False, indent=2)}\n\n"
            )
        user_parts = [
            _build_constraints_block(language),
            _build_episode_block(language),
            story_plan_block,
            f"{topic_label}: {topic}\n",
            f"{duration_label}: {duration_int} seconds\n",
            f"{cuts_label}: {cut_count}\n",
            f"{style_label}: {style}\n",
            f"{language_label}: {language_name}\n",
        ]
        if character_description:
            user_parts.append(f"\nCharacter reference context:\n{character_description}\n")
        return "".join(user_parts)

    @staticmethod
    def _scene_block_ranges(story_plan: dict) -> list[dict]:
        blocks = story_plan.get("scene_blocks") if isinstance(story_plan, dict) else None
        return [block for block in blocks if isinstance(block, dict)] if isinstance(blocks, list) else []

    @staticmethod
    def _parse_range_text(value: Any) -> tuple[int, int] | None:
        match = re.match(r"^\s*(\d+)\s*[-~–—]\s*(\d+)\s*$", str(value or "").strip())
        if not match:
            return None
        start = int(match.group(1))
        end = int(match.group(2))
        if start <= 0 or end < start:
            return None
        return start, end

    @staticmethod
    def _script_metadata_from_story_plan(topic: str, config: dict, story_plan: dict) -> dict:
        core = story_plan.get("story_core") if isinstance(story_plan, dict) else {}
        if not isinstance(core, dict):
            core = {}
        title = str(config.get("title") or config.get("project_title") or topic or "").strip()
        if not title:
            title = str(core.get("ending_memory") or core.get("central_question") or "LongTube").strip()
        central_question = str(core.get("central_question") or "").strip()
        central_answer = str(core.get("central_answer") or "").strip()
        ending_memory = str(core.get("ending_memory") or "").strip()
        protagonist = str(core.get("protagonist") or "").strip()
        obstacle = str(core.get("obstacle") or "").strip()
        description_parts = [part for part in (central_question, central_answer, ending_memory) if part]
        description = "\n".join(description_parts) if description_parts else str(topic or title)
        raw_tags = re.findall(r"[가-힣A-Za-z0-9]{2,24}", f"{topic} {protagonist} {obstacle}")
        tags: list[str] = []
        for tag in raw_tags:
            if tag not in tags:
                tags.append(tag)
            if len(tags) >= 12:
                break
        hook_source = str(core.get("first_turn") or central_question or title).strip()
        hook_words = re.findall(r"[가-힣A-Za-z0-9]+", hook_source)
        if len(hook_words) >= 2:
            thumbnail_hook = f"{hook_words[0][:10]}\n{hook_words[1][:10]}"
        else:
            thumbnail_hook = f"{(hook_source or title)[:8]}\n왜 그랬나"
        thumbnail_subject = protagonist or title
        thumbnail_prompt = (
            "high-resolution documentary cartoon thumbnail, clean bold shapes, "
            "tabloid-intense but fact-locked, "
            f"the most clickable story-critical subject: {thumbnail_subject}, "
            "choose the strongest factual trigger: fatal consequence, forbidden secret, "
            "betrayal signal, explosive rage, public humiliation, collapse evidence, or last-warning object, "
            "one story-matched accent color, clear negative space for later text, no readable text, no logos"
        )
        return {
            "title": title,
            "description": description,
            "tags": tags,
            "thumbnail_prompt": thumbnail_prompt,
            "thumbnail_hook": thumbnail_hook,
        }

    def _build_scene_block_script_system_prompt(self, config: dict) -> str:
        cfg = config or {}
        language = normalize_language_code(cfg.get("language", "ko"))
        lang_name = self._language_name(language)
        limits = self._calc_narration_limits(cfg)
        target_range = str(limits.get("target_range") or "")
        timing_unit = "words" if language in ("en", "hi") else "공백 포함 글자"
        return (
            "당신은 LongTube V3.1 대본의 scene_block 확장기입니다.\n"
            "새 줄거리나 새 사실을 만들지 말고, 제공된 story_plan의 현재 scene_block만 해당 컷 범위 대본으로 확장합니다.\n"
            "반드시 JSON 객체 하나만 반환하세요. 마크다운, 설명, 주석은 금지합니다.\n\n"
            "출력 형식:\n"
            "{\"cuts\":[{\"cut_number\":1,\"scene_block_id\":1,\"narration\":\"...\",\"image_prompt\":\"\",\"visual_year\":\"...\",\"visual_period\":\"...\",\"visual_location\":\"...\",\"visual_evidence\":\"...\",\"visual_subject\":\"...\",\"visual_scene\":\"...\",\"scene_type\":\"body\",\"shorts_candidate\":false}]}\n\n"
            f"내레이션 언어: {lang_name}.\n"
            f"각 narration 목표 길이: {target_range} {timing_unit}. 너무 짧은 단문으로 닫지 마세요.\n"
            "narration은 보고서 요약문이 아니라 실제 영상에서 사람이 말하는 한국어 내레이션이어야 합니다.\n"
            "문서체 금지: `균열을 드러냈다`, `화친을 건의했다`, `운명을 바꿨다`, `남하의 길을 택했다`, `점에서 시작된다`, `의미를 가진다`, `단서가 된다`처럼 보고서 결론문으로 닫으면 실패입니다.\n"
            "시청자에게 말하듯 쓰세요. 예: `그런데 진짜 문제는 성 밖이 아니었습니다. 성 안에서 먼저 갈라지고 있었죠.`\n"
            "사실 전달은 유지하되, 문장 끝은 자연스럽게 섞으세요: `-습니다`, `-입니다`, `-했어요`, `-했죠`, `-였는데요`, `-였거든요`, `-고요`를 상황에 맞게 사용합니다.\n"
            "한 10컷 블럭 안에서 `죠` 계열 종결(`죠`, `했죠`, `였죠`, `이죠`)은 최대 3컷만 쓰세요. 4컷 이상 쓰면 실패입니다.\n"
            "한 10컷 블럭 안에는 `습니다/입니다` 계열, `요` 계열, `죠` 계열이 자연스럽게 섞여야 합니다.\n"
            "모든 컷을 질문형이나 `죠`로 끝내지 마세요. 사실을 고정하는 컷은 `-습니다/-입니다`, 연결 컷은 `-는데요/-고요/-거든요`처럼 역할에 맞게 나눕니다.\n"
            "권장 리듬 예: 질문 또는 압박 -> 사실 고정 -> 인물 설명 -> 이해관계 -> 충돌 -> 물증/행동 -> 선택지 -> 반전 -> 비용 -> 다음 블럭 연결.\n"
            "한 컷 안에 논문식 명사구를 겹치지 마세요. `내부의 선택이 먼저 드러냈다는 점에서 시작된다` 같은 문장은 금지입니다.\n"
            "첫 블럭 안에서 결론을 모두 말하지 마세요. 첫 블럭은 질문, 압박, 첫 선택, 다음 궁금증을 남기는 역할입니다.\n"
            "각 컷은 앞 컷을 받아 다음 컷으로 이어지는 자연스러운 대사여야 합니다.\n"
            "마침표형 단정 문장이 3컷 이상 연속되면 실패입니다.\n"
            "한 컷은 핵심 정보 하나를 담되, 원인/결과/압박/다음 의문 중 하나를 함께 붙이세요.\n"
            "scene_block의 mini_question, new_information, tension, turn, must_include를 빠짐없이 반영하세요.\n"
            "fact_ledger.confirmed_facts 밖의 내용을 확정처럼 말하지 마세요.\n"
            "fact_ledger.unknown_or_debated와 forbidden_claims는 단정하거나 장면으로 꾸미지 마세요.\n"
            "visual_world는 모든 visual_* 필드의 최상위 시대·장소·문화 기준입니다.\n"
            "visual_period, visual_location, visual_evidence, visual_subject, visual_scene은 영어로만 작성하세요.\n"
            "visual_subject는 4~12단어, visual_scene은 12~28단어로 짧고 구체적으로 작성하세요.\n"
            "visual_scene에는 반드시 보이는 행동 또는 감정선이 있어야 합니다. standing, watching, looking, sitting 같은 정지 동사만으로 끝내지 마세요.\n"
            "인물이 나오면 face, eyes, posture, body angle 중 하나로 anger, fear, resolve, grief, suspicion, betrayal, protection 같은 감정이 보이게 쓰세요.\n"
            "현재 scene_block.character_introductions에 현재 cut_number가 있으면 visual_subject는 해당 인물명으로 쓰고, visual_scene은 medium-close 또는 close-up character entrance로 쓰세요.\n"
            "주요 인물 첫 등장 컷은 얼굴, 눈빛, 표정, 어깨 각도, 손동작, 시대 복식 실루엣 중 최소 세 가지가 보이게 쓰세요. 먼 군중, 건물 전경, 지도, 상징물로 대체하면 실패입니다.\n"
            "주요 남성 인물 첫 등장은 stylish medium-close entrance, intense eyes, controlled expression, dramatic rim light, strong silhouette, period-correct armor or command robes를 포함하세요.\n"
            "성인 여성 주요인물 첫 등장은 adult woman, attractive charisma, confident eyes, elegant period-correct clothing, strong silhouette, tasteful mature styling을 포함하세요. 노출 중심, 미성년처럼 보이는 표현은 금지입니다.\n"
            "인물이 없는 컷은 foreground evidence, damage, concealment, pursuit trace, dangerous light, physical consequence 중 하나가 보이게 쓰세요.\n"
            "visual_evidence, visual_subject, visual_scene에서 같은 단어를 4회 이상 반복하거나 문구를 늘어뜨리면 실패입니다.\n"
            "출력 키 이름을 바꾸지 마세요. imageport_prompt, visual_or_visual_subject 같은 변형 키는 실패입니다.\n"
            "image_prompt는 항상 빈 문자열로 두세요.\n"
            "쇼츠 후보는 이 단계에서 선정하지 않습니다. shorts_candidate는 항상 false로 두고 shorts_group, shorts_reason, shorts_score, shorts_title은 쓰지 마세요.\n"
            "읽을 수 있는 텍스트, 숫자, 로고, 표식은 visual_scene에 요청하지 마세요.\n"
            "요청된 cut_range 밖의 cut_number를 만들지 마세요."
        )

    def _build_scene_block_script_user_prompt(
        self,
        *,
        topic: str,
        config: dict,
        story_plan: dict,
        scene_block: dict,
        previous_cuts: list[dict] | None = None,
        next_block: dict | None = None,
    ) -> str:
        previous_preview = [
            {
                "cut_number": cut.get("cut_number"),
                "narration": cut.get("narration"),
            }
            for cut in (previous_cuts or [])[-2:]
            if isinstance(cut, dict)
        ]
        compact_plan = self._compact_story_plan_for_scene_block(story_plan, scene_block)
        return (
            "아래 story_plan은 고정 설계입니다. 현재 scene_block만 대본으로 확장하세요.\n"
            f"주제: {topic}\n"
            f"정확한 현재 scene_block:\n{json.dumps(scene_block, ensure_ascii=False, indent=2)}\n\n"
            f"이전 컷 연결 참고:\n{json.dumps(previous_preview, ensure_ascii=False, indent=2)}\n\n"
            f"다음 block 연결 참고:\n{json.dumps(next_block or {}, ensure_ascii=False, indent=2)}\n\n"
            f"현재 블록용 story_plan 요약:\n{json.dumps(compact_plan, ensure_ascii=False, indent=2)}\n\n"
            "현재 scene_block의 cut_range에 해당하는 컷만 반환하세요."
        )

    def _compact_story_plan_for_scene_block(self, story_plan: dict, scene_block: dict) -> dict:
        plan = self._strip_story_plan_runtime_fields(story_plan if isinstance(story_plan, dict) else {})
        try:
            block_id = int((scene_block or {}).get("block_id") or 0)
        except (TypeError, ValueError):
            block_id = 0
        blocks: list[dict] = []
        for block in plan.get("scene_blocks") or []:
            if not isinstance(block, dict):
                continue
            try:
                current_id = int(block.get("block_id") or 0)
            except (TypeError, ValueError):
                current_id = 0
            if current_id in {block_id - 1, block_id, block_id + 1}:
                blocks.append(block)
        return {
            "visual_world": plan.get("visual_world") or {},
            "story_core": plan.get("story_core") or {},
            "fact_ledger": plan.get("fact_ledger") or {},
            "visual_plan": plan.get("visual_plan") or {},
            "current_scene_block": scene_block if isinstance(scene_block, dict) else {},
            "neighbor_scene_blocks": blocks,
            "script_checklist": plan.get("script_checklist") or {},
        }
