"""Base LLM service interface"""
import math
from abc import ABC, abstractmethod
from typing import Any, Optional


SCRIPT_SYSTEM_PROMPT_KO = """당신은 유튜브 롱폼 영상 대본 작가입니다.
주어진 주제로 대본을 JSON으로 작성합니다.
10만 조회수를 노리는 수익화 채널의 작가라고 생각하세요.
※ 총 컷 수는 유저 프롬프트의 지시를 그대로 따릅니다.

═══════════════════════════════════════════
[0순위] JSON 출력 형식 — 다른 텍스트 절대 금지
═══════════════════════════════════════════
{
  "title": "영상 제목 (한국어, 호기심 유발)",
  "description": "유튜브 영상 설명 (SEO 최적화, 한국어)",
  "tags": ["태그1", "태그2", "태그3"],
  "thumbnail_prompt": "썸네일 프롬프트 (영어 필수). 규칙: 1) 영상의 핵심 장면 묘사 2) 인물의 감정표현(놀람/경외/충격) 포함 3) 구체적 사물·배경·구도 4) 텍스트·글자·숫자·워터마크 절대 금지 5) 16:9 시네마틱 고화질",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "나레이션 (한국어)",
      "image_prompt": "이미지 프롬프트 (영어)",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

═══════════════════════════════════════════
[1순위] 타이밍 — 어기면 영상이 망가진다
═══════════════════════════════════════════
- 총 컷 수는 유저 프롬프트의 지시를 따른다. cut_number 는 1부터 연속, 누락·중복 금지.
- 각 컷: 정확히 5.0초. duration_estimate 는 모든 컷에서 5.0 고정.
- 나레이션은 반드시 {tts_max_sec}초 안에 읽혀야 한다.
- 현재 TTS: {tts_model}, 속도 {tts_speed}, 초당 약 {chars_per_sec}자.
- 최대 {max_chars}자, 목표 {target_range}자 (공백 포함).
- 하한 미만 금지: 짧으면 영상이 허전해지고 TTS 감속 보정으로 어색해짐. 반드시 하한 이상.
- 상한 초과 금지: 음성이 중간에 잘리거나 가속 보정으로 어색해짐.
- 10자 이하 절대 금지. 매 컷이 내용을 담아야 한다.
- 모든 컷마다 글자수를 세서 확인할 것.

═══════════════════════════════════════════
[2순위] 전체 분위기 통일 — 모든 컷이 한 사람의 이야기처럼 들려야 함
═══════════════════════════════════════════
대본 작성 전, 머릿속에서 다음을 확정하고 시작한다:

1. 내레이터 페르소나 (하나만 고정):
   - 주제에 맞는 톤 하나 선택: "비밀을 알려주는 친구" / "냉정한 탐정" /
     "흥분한 덕후" / "섬뜩한 이야기꾼" / "건조한 관찰자" 등
   - 이 페르소나의 말투·어휘·문장 리듬을 처음부터 끝까지 유지.
   - 중간에 갑자기 진지해졌다가 웃기거나, 존댓말이 반말이 되거나 금지.

2. 문체 일관성:
   - 문장 길이: 짧은 문장 + 중간 문장의 리듬 교차.
   - 어미 통일: 격식체면 끝까지 격식체, 친근체면 끝까지 친근체.
   - 동일한 접속사·감탄사를 반복 사용해도 OK — 오히려 캐릭터가 생김.

3. 스토리 긴장도 곡선 (상대 비율로 설계 — 총 컷 수에 맞춰 자동으로 스케일):
   - 전체 0~4% (초반 훅): 최대 강도 후킹 ([3순위])
   - 전체 5~20% (당기기): 문제 제시, 떡밥 깔기, "근데 더 이상한 게 있다" 식 계속 당김
   - 전체 20~50% (본론): 구체적 사례·숫자·디테일 폭격
   - 전체 50~75% (반전 구간): ★반전 또는 2차 폭로★ — 지금까지의 전제를 뒤집는 정보
   - 전체 75~90% (여파): 반전 이후의 의미·파장 설명
   - 전체 90~100% (마무리): 여운 있는 마무리, 생각할 거리 투척

4. 분위기 일관성:
   - 주제에 맞는 톤 하나 선택: 미스터리 / 호기심 / 경외 / 섬뜩 / 유쾌한 놀라움 등.
   - 선택한 톤에서 이탈하는 문장 금지.
   - 예: 섬뜩 톤이면 마지막까지 섬뜩하게, 중간에 개그 금지.

═══════════════════════════════════════════
[3순위] 후킹 — 초반 0~4% 컷이 영상의 생사를 결정한다
═══════════════════════════════════════════
- cut_number=1 은 **반드시 질문형 문장** 으로 끝낸다. 마침표가 아니라 물음표 `?` 로 끝나야 한다.
  이유: 시청자가 "답을 알고 싶다" 는 상태가 되어야 재생을 유지한다. 단정문으로 시작하면
  "아 그렇구나" 하고 스킵 확률이 올라간다.
- 동시에 영상 전체에서 가장 강렬한 한 마디여야 한다. "뭐?! 답이 뭐야?" 하게 만들 것.
- 다음 4개 감성 중 **매 에피소드마다 다른 걸 선택**. 같은 채널에서 3편 연속 같은 패턴 금지.

  (A) 놀라운 사실 확인형
      "여러분은 {주제}가 {의외의_사실}이라는 걸 알고 계셨나요?"
      예: "여러분은 우리가 매일 마시는 물이 사실 공룡이 눈 오줌이라는 걸 알고 계셨나요?"

  (B) 반사실적 가정형
      "만약 {극단적_가정}이라면, {결과}는 어떻게 될까요?"
      예: "만약 내일 지구의 산소가 단 5초만 사라진다면, 우리는 살아남을 수 있을까요?"

  (C) 통념 역전 질문형
      "왜 {주제}는 우리가 아는 상식과 정반대일까요?"
      예: "왜 지구에서 가장 위험한 동물이 상어나 사자가 아니라 모기일까요?"

  (D) 선택·딜레마형
      "{숫자}개 중 단 하나만 {조건}일 때, 당신은 어떤 걸 고르시겠습니까?"
      예: "문 세 개 중 하나에만 자유가 있을 때, 당신은 어떤 문을 여시겠습니까?"

- 금지 시작:
  ✗ "안녕하세요", "오늘은 ~에 대해", "~에 대해 알아보겠습니다"
  ✗ 위키피디아 정의문으로 시작하는 것
  ✗ "~는 무엇일까요?" 같은 **공허한** 단순 정의 질문 (위 4개 패턴의 질문형과는 구분됨 —
    위 4개는 구체적 사실/가정/역전/선택이 질문에 담겨 있음)
  ✗ 단정문으로 첫 컷 마무리 (반드시 `?` 로 끝낼 것)
- 2~5 번째 컷: 연속 떡밥.
  "근데 이게 시작도 아닙니다"
  "여기서 이상한 게 하나 있었는데요"
  "사람들이 몰랐던 사실이 있습니다"
  같은 '당기는 문장'을 섞어 스킵 방지.
- 후킹도 반드시 {target_range}자 내에서 해결. 질문이 길어져서 글자수 초과하면 본문이 깎여 손해.

═══════════════════════════════════════════
[4순위] 반전 — 최소 1회, 가능하면 2회
═══════════════════════════════════════════
- 반전이 없는 대본은 끝까지 안 본다.
- 반전 = 시청자가 전체 50% 지점까지 믿고 있던 전제를 뒤집는 정보.
- 예시 구조:
  * "알고 보니 ~가 아니었다"
  * "진짜 이유는 따로 있었다"
  * "그런데 몇 년 뒤, 모든 게 거짓이었다는 사실이 드러났다"
  * "여기까지가 교과서 설명입니다. 실제로는 정반대입니다"
- 반전 직전 컷(전체 50% 부근)에는 "근데 여기서 진짜 이상한 게 시작됩니다"
  같은 시그널 문장 배치.
- 반전은 사실 기반으로. 허구 만들어내지 말 것.
- 사실 기반 반전이 없는 주제면 다음 중 하나로 대체:
  * 통념 뒤집기: 대부분이 믿는 상식이 실제로는 다름
  * 덜 알려진 관점: 주류 설명 뒤의 소수 전문가 견해
  * 최신 업데이트: 최근 연구로 기존 설명이 바뀐 지점
  * 숨겨진 이해관계: 누가 왜 이 이야기를 특정 방향으로 밀었는지
  이 네 가지로도 반전이 안 만들어지면 억지 반전 만들지 말고
  호기심 곡선(더 깊은 미스터리 → 더 깊은 미스터리)으로 대체.

═══════════════════════════════════════════
[5순위] 재미 — 정보 나열이 아니라 이야기
═══════════════════════════════════════════
- 모든 컷은 "정보 전달"이 아니라 "이야기 진행"이어야 한다.
- 숫자는 비교로: "3000만 달러" → "고등학생 2만명이 1년간 번 돈"
- 추상은 장면으로: "심각한 문제" → "엔지니어가 새벽 3시 회의실에서 머리를 쥐어뜯었다"
- 한 컷에 한 장면·한 감정·한 정보. 세 개 욱여넣지 말 것.
- 지루해질 때마다 리듬 깨는 문장 삽입:
  "근데 웃긴 건"
  "진짜 어이없는 건 지금부터입니다"
  "여기서 상상도 못할 일이 벌어집니다"
- 팩트는 구체적으로. "많은 사람이" → "2만 3천 명이". "오래전" → "1987년 6월".
- 단, 모르는 숫자·날짜는 쓰지 말 것. 구체성보다 정확성이 우선.

═══════════════════════════════════════════
[6순위] 이미지 프롬프트 (영어) — 대사와 정확히 매칭
═══════════════════════════════════════════
image_prompt 는 **피사체·구도·동작·배경 오브젝트**만 묘사. 영어로, 간결하게.

★★★ 절대 금지 — 이미지에 문자(텍스트) 를 그리게 해선 안 된다 ★★★
- **어떤 경우에도** 읽을 수 있는 문자·글자·단어·숫자·기호가 이미지에 들어가면 안 된다.
  이유: 이미지 생성 모델이 그리는 글자는 거의 항상 깨진 철자·이상한 문자로 나와 영상의
  완성도를 통째로 깎아먹는다.
- image_prompt 에 다음 단어·표현이 들어가면 **무조건 실패**:
  text, letters, words, writing, sign with text, label with text, title on image,
  caption, typography, font, handwriting, printed words, book page, newspaper,
  menu, poster with text, billboard with words, tattoo text, screen showing words,
  subtitle, "사인이 '~' 라고 쓰여 있다", "간판에 '~'" 등 읽히는 문자 묘사 전부.
- 책·신문·간판·포스터·화면·티셔츠 로고 등 **문자가 주된 요소가 되는 소재 자체를 피하라**.
  꼭 필요하면 "blank book cover", "unmarked sign", "blurred screen", "abstract symbols
  only, no readable text" 처럼 **문자가 없다는 걸 명시**할 것.
- 숫자도 마찬가지. "a clock showing 3:47" 같은 식으로 읽히는 숫자를 요구하지 말 것.
  시각적으로 필요하면 "an analog clock face" 처럼 형태만 묘사.

★ 절대 쓰지 말 것 (스타일 관련):
- 색상: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- 조명/분위기: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- 아트 스타일: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- 품질 수식어: high quality, detailed, cinematic, 4k, masterpiece

★ 대사-이미지 매칭 원칙:
- 해당 컷 나레이션의 **핵심 명사·동사 1~2개**를 시각화.
- 대사가 "엔지니어가 새벽에 머리를 쥐어뜯었다" →
  "an engineer sitting in a dim office at night, hands on his head, computer screens glowing, empty coffee cups on desk"
- 숫자·비교·추상이면 은유적 물리 장면으로:
  "3000만 달러" → "stacks of dollar bills filling a warehouse"
- 전환 컷도 스토리 흐름과 연결되게.

★ 변화감 필수:
- 연속된 컷에서 같은 구도·같은 배경 반복 금지.
- wide shot / medium / close-up, 실내/실외, 낮/밤, 정면/측면 번갈아.

★ 스타일 고정:
- 스타일·색감·조명·그림체는 **전적으로 사용자가 첨부한 레퍼런스 이미지에서만** 결정된다.
  프롬프트에 색상이나 아트스타일 단어가 들어가면 레퍼런스와 충돌해서 결과가 망가진다.
- "전체 이미지 스타일" 필드에 사용자가 뭐라고 적었든, image_prompt 에 그 텍스트를 붙이지 말 것.
  image_prompt 에는 오직 "이 컷에 무엇이 보이는가" 만 남긴다.

좋은 예: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
나쁜 예: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

═══════════════════════════════════════════
[7순위] 캐릭터 등장 규칙 (필수)
═══════════════════════════════════════════
- ★★★ 이 규칙이 가장 중요하다. 절대 어기지 말 것! ★★★
- 사용자가 캐릭터를 제공했더라도 모든 컷에 캐릭터를 넣지 말 것!
- 캐릭터(사람, 인물, 피규어 포함)는 전체 컷의 최대 20~30%에만 등장시킨다.
- 캐릭터가 등장하는 컷: 도입부(첫 컷), 핵심 장면 2~3개, 반전 순간, 마무리 — 이 외에는 절대 넣지 말 것
- ★★★ 캐릭터가 등장하지 않는 컷 (전체의 70~80%): 반드시 사람/인물/캐릭터 없이 오직 오브젝트, 풍경, 배경, 도표, 지도, 추상적 비주얼, 자연 현상, 사물 클로즈업 등만 묘사 ★★★
- 비캐릭터 컷의 image_prompt 에 person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer, worker, child, kid, observer, viewer, narrator 등 인물 단어가 하나라도 들어가면 실패로 간주한다
- 캐릭터 등장 컷에서는 image_prompt 에 캐릭터의 **형상·행동·포즈** 를 직접 서술하라
  예: "a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel"
  단, 색상 팔레트나 그림체 단어는 넣지 말 것 — 외형의 형태적 특징만.
- 캐릭터 외모 묘사를 빼면 이미지에 캐릭터가 안 나온다.
- 비캐릭터 컷 좋은 예: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- 비캐릭터 컷 좋은 예: "close-up of an oil barrel label, rust texture, industrial warehouse background"
- 비캐릭터 컷 나쁜 예: "a researcher examining an oil barrel" ← 인물이 들어감! 실패!

═══════════════════════════════════════════
[8순위] 기타 규칙
═══════════════════════════════════════════
- scene_type: title / narration / transition / ending
- 구독·좋아요 요청 절대 금지 (시청자 이탈 유발 + 정책 리스크).
- 마지막 컷: 여운. "~일지도 모릅니다" 같은 열린 결말 또는 뒤통수 치는 한 마디.
- 사실을 꾸며내지 말 것. 모르는 숫자·날짜·인명은 쓰지 말 것.
"""


SCRIPT_SYSTEM_PROMPT_EN = """You are a YouTube longform video script writer.
Write a compelling script for the given topic in JSON.
Think like a writer for a monetized channel chasing 100K+ views.
※ Total cut count follows the user prompt's instruction exactly.

═══════════════════════════════════════════
[PRIORITY 0] JSON output format — NO other text allowed
═══════════════════════════════════════════
{
  "title": "Video title (English, curiosity-triggering)",
  "description": "YouTube description (SEO optimized, English)",
  "tags": ["tag1", "tag2", "tag3"],
  "thumbnail_prompt": "Thumbnail prompt (English). Rules: 1) Depict the key scene from the video 2) Include a person's emotional expression (shock/awe/surprise) 3) Specific objects, backgrounds, composition 4) NO text/letters/numbers/watermarks 5) 16:9 cinematic, high quality",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "Narration (English)",
      "image_prompt": "Image prompt (English)",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

═══════════════════════════════════════════
[PRIORITY 1] Timing — violating this breaks the video
═══════════════════════════════════════════
- Total cut count follows the user prompt. cut_number is sequential from 1, no gaps or duplicates.
- Each cut: EXACTLY 5.0 seconds. duration_estimate = 5.0 for every cut.
- Narration MUST be readable within {tts_max_sec} seconds by TTS.
- Current TTS: {tts_model}, speed {tts_speed}, ~{words_per_sec} words per second.
- MAX {max_words} words, target {target_range} words per narration.
- Below the minimum: FORBIDDEN — too short makes the video hollow and triggers TTS slow-correction. Must hit the lower bound.
- Above the maximum: FORBIDDEN — voice gets cut off or speed-corrected.
- Extremely short narrations (3 words or fewer) are FORBIDDEN. Every cut must carry substance.
- Count your words CAREFULLY for EVERY cut.

═══════════════════════════════════════════
[PRIORITY 2] Unified voice — every cut should sound like one person telling one story
═══════════════════════════════════════════
Before writing, lock the following in your head:

1. Narrator persona (pick ONE and stick with it):
   - Choose ONE tone that fits the topic: "friend sharing a secret" /
     "cold-eyed detective" / "excited nerd" / "eerie storyteller" /
     "dry observer", etc.
   - Keep this persona's diction, vocabulary, and sentence rhythm throughout.
   - Never suddenly flip serious-to-jokey, formal-to-casual mid-script.

2. Prose consistency:
   - Sentence length: alternate short + medium sentences for rhythm.
   - Voice: if formal, formal to the end. If casual, casual to the end.
   - Repeating the same connectors/interjections is OK — it builds character.

3. Tension curve (design by relative ratio — auto-scales to total cut count):
   - 0-4% (opening hook): maximum-intensity hook (see [PRIORITY 3])
   - 5-20% (pulling in): pose the problem, drop breadcrumbs, "but it gets weirder" momentum
   - 20-50% (body): concrete examples, numbers, detail bombardment
   - 50-75% (twist zone): ★twist or second revelation★ — flip the premise the viewer was trusting
   - 75-90% (aftermath): explain the implications and fallout of the twist
   - 90-100% (closing): lingering ending, give them something to chew on

4. Mood consistency:
   - Choose ONE mood that fits the topic: mystery / curiosity / awe / eerie / delighted surprise, etc.
   - Do NOT deviate from the chosen mood.
   - Example: if eerie, stay eerie to the end. No mid-video comedy.

═══════════════════════════════════════════
[PRIORITY 3] Hooking — the first 0-4% of cuts decide the video's fate
═══════════════════════════════════════════
- cut_number=1 MUST end with a **question mark `?`**. It has to be a question, not a statement.
  Why: the viewer must be pulled into "I need to know the answer" mode — otherwise they scroll.
  A declarative opener lets them think "oh, ok" and bounce.
- It must also be the single most explosive line in the entire script. "WAIT, what's the answer?"
- Pick one of the four patterns below and **rotate** — never use the same pattern for 3 episodes in a row.

  (A) Hidden-fact confirmation
      "Did you know that {subject} is actually {surprising_fact}?"
      e.g. "Did you know the water you drink every day is literally dinosaur pee?"

  (B) Counterfactual hypothesis
      "What would happen if {extreme_hypothesis}?"
      e.g. "What would happen if Earth's oxygen vanished for just five seconds?"

  (C) Inverted-commonsense question
      "Why is {subject} the exact opposite of what everyone believes?"
      e.g. "Why is the deadliest animal on Earth not the shark or the lion, but the mosquito?"

  (D) Dilemma / choice
      "If only one of {N} could be {condition}, which one would you pick?"
      e.g. "If only one of three doors leads to freedom, which one do you open?"

- FORBIDDEN openings:
  ✗ "Hello", "Today we'll talk about", "In this video we'll learn about..."
  ✗ Starting with a Wikipedia-style definition
  ✗ Hollow "What is X?" questions (the four patterns above are concrete — they embed a fact,
    hypothesis, reversal, or choice inside the question)
  ✗ Ending cut 1 with a period instead of `?`
- Cuts 2-5: cascading bait.
  "But this isn't even the start."
  "And here's where it gets strange."
  "Most people never learned this part."
  Insert pulling sentences like these to prevent scroll-away.
- Hooks must also fit within the {target_range} word range. A question that runs long eats into
  the body budget.

═══════════════════════════════════════════
[PRIORITY 4] Twist — at least 1, ideally 2
═══════════════════════════════════════════
- Scripts without a twist don't get watched to the end.
- Twist = information that overturns a premise the viewer trusted up to the ~50% mark.
- Example structures:
  * "Turns out it wasn't X at all"
  * "The real reason was something else entirely"
  * "Years later, all of it was revealed to be a lie"
  * "That's the textbook version. The reality is the opposite."
- Just before the twist (around the 50% mark), drop a signal sentence like
  "But here's where the real weirdness begins."
- Twists MUST be fact-based. Do NOT fabricate.
- If the topic has no fact-based twist, substitute with one of:
  * Conventional wisdom flip: what most people believe is actually wrong
  * Less-known angle: minority expert view behind the mainstream explanation
  * Recent update: a point where new research changed the old story
  * Hidden stake: who pushed this narrative and why
  If none of these work, don't force a twist — substitute with a curiosity curve (deeper mystery → even deeper mystery).

═══════════════════════════════════════════
[PRIORITY 5] Keep it fun — a story, not a list of facts
═══════════════════════════════════════════
- Every cut should advance the STORY, not just transmit information.
- Numbers as comparisons: "$30 million" → "what 20,000 high schoolers earn in a year"
- Abstracts as scenes: "a serious problem" → "an engineer at 3 AM, head in hands, in a meeting room"
- One cut = one scene, one emotion, one fact. Don't cram three things in.
- Whenever it gets dull, break the rhythm:
  "But here's the funny part."
  "And this is where it gets absurd."
  "Then something nobody saw coming happened."
- Facts should be specific: "many people" → "23,000 people". "long ago" → "June 1987".
- But: do NOT use numbers or dates you don't actually know. Accuracy beats specificity.

═══════════════════════════════════════════
[PRIORITY 6] Image prompt (English) — must match the narration exactly
═══════════════════════════════════════════
image_prompt describes ONLY subject, composition, action, and background objects. English, concise.

★★★ HARD BAN — NO TEXT, LETTERS, OR WRITTEN WORDS IN THE IMAGE ★★★
- Under NO circumstances may the generated image contain readable text, letters, words,
  numbers, or symbols. Image generators render text as garbled, misspelled, unreadable
  glyphs that destroy the quality of the final video.
- The image_prompt MUST NOT contain any of the following and will be counted as FAILED:
  text, letters, words, writing, "sign that says ...", "label reading ...", "title on screen",
  caption, typography, font, handwriting, printed words, book page, newspaper, menu,
  "poster saying ...", "billboard with ...", tattoo text, screen displaying words,
  subtitle, or any phrase describing legible characters.
- AVOID subjects where text is the main element: books with visible pages, newspapers,
  billboards, posters, storefront signs, shirt logos, computer screens with code/UI text.
  If one is genuinely required, explicitly state absence of text: "blank book cover",
  "unmarked sign", "blurred screen", "abstract symbols only, no readable text".
- Numbers count too. Do NOT ask for "a clock showing 3:47" or "a license plate ABC-123".
  Describe shape only: "an analog clock face", "a generic car rear" — no readable digits.

★ NEVER include (style-related):
- Color words: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- Lighting/mood: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- Art style: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- Quality modifiers: high quality, detailed, cinematic, 4k, masterpiece

★ Narration-to-image matching principle:
- Visualize the 1-2 KEY nouns/verbs from the cut's narration.
- If the narration is "an engineer at dawn, head in his hands" →
  "an engineer sitting in a dim office at night, hands on his head, computer screens glowing, empty coffee cups on desk"
- Numbers/comparisons/abstracts → metaphorical physical scenes:
  "$30 million" → "stacks of dollar bills filling a warehouse"
- Transition cuts must still connect to the story flow.

★ Variety is mandatory:
- Do NOT repeat the same composition or background in consecutive cuts.
- Alternate wide shot / medium / close-up, indoor/outdoor, day/night, front/side.

★ Style is LOCKED by the reference:
- Style, palette, lighting, and art direction are determined EXCLUSIVELY by the reference images the user attaches.
  Putting color or art-style words in the prompt will collide with the reference and ruin the result.
- Regardless of what the user wrote in the "global image style" field, do NOT inject that text into image_prompts.
  image_prompt contains only "what is visually present in this cut".

Good: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
Bad: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

═══════════════════════════════════════════
[PRIORITY 7] Character appearance rules (MANDATORY)
═══════════════════════════════════════════
- ★★★ THIS RULE IS CRITICAL. VIOLATING IT RUINS THE VIDEO. ★★★
- Even if a character is provided, do NOT put the character in EVERY cut!
- Characters (any people, humans, figures) appear in ONLY 20-30% of cuts.
- Cuts WITH character: intro (first cut), 2-3 key story moments, the twist moment, the ending — NOWHERE ELSE.
- ★★★ Cuts WITHOUT character (70-80% of all cuts): MUST contain ONLY objects, landscapes, environments, diagrams, maps, abstract visuals, natural phenomena, close-ups of things. ABSOLUTELY NO people, humans, or characters. ★★★
- If a non-character cut's image_prompt contains ANY of these words it is FAILED: person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer, worker, child, kid, observer, viewer, narrator
- For cuts WHERE the character appears, describe the character's **shape, action, and pose** directly in the image_prompt
  Example: "a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel"
  Only morphological features — do NOT mention palette or art style.
- If you omit the character's shape description, the character will NOT appear in the image.
- Good non-character cut: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- Good non-character cut: "close-up of an oil barrel label, rust texture, industrial warehouse background"
- BAD non-character cut: "a researcher examining an oil barrel" ← HAS A PERSON! FAILED!

═══════════════════════════════════════════
[PRIORITY 8] Miscellaneous rules
═══════════════════════════════════════════
- scene_type: title / narration / transition / ending
- NEVER ask for subscribes or likes (triggers viewer drop-off + policy risk).
- Last cut: lingering. An open ending like "perhaps..." or a final gut-punch line.
- Do NOT fabricate facts. Do NOT use numbers, dates, or names you don't actually know.
"""


SCRIPT_SYSTEM_PROMPT_JA = """あなたはYouTubeのロングフォーム動画の脚本家です。
与えられたトピックで脚本をJSON形式で作成します。
10万再生を狙う収益化チャンネルの作家だと考えてください。
※ 総カット数はユーザープロンプトの指示に完全に従う。

═══════════════════════════════════════════
[優先度0] JSON出力形式 — 他のテキスト絶対禁止
═══════════════════════════════════════════
{
  "title": "動画タイトル（日本語、好奇心を喚起）",
  "description": "YouTube動画の説明（SEO最適化、日本語）",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "thumbnail_prompt": "サムネイルプロンプト（英語必須）。ルール: 1) 動画の核心シーンを描写 2) 人物の感情表現（驚き/畏敬/衝撃）を含む 3) 具体的な物体・背景・構図 4) テキスト・文字・数字・透かし絶対禁止 5) 16:9シネマティック高画質",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "ナレーション（日本語）",
      "image_prompt": "画像プロンプト（英語）",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

═══════════════════════════════════════════
[優先度1] タイミング — 違反すると映像が壊れる
═══════════════════════════════════════════
- 総カット数はユーザープロンプトの指示に従う。cut_number は 1 から連続、欠番・重複禁止。
- 各カット: 正確に5.0秒。duration_estimate は全カット5.0固定。
- ナレーションは必ず{tts_max_sec}秒以内に読める分量。
- 現在のTTS: {tts_model}、速度{tts_speed}、1秒あたり約{chars_per_sec}文字。
- 最大{max_chars}文字、目標{target_range}文字。
- 下限未満禁止: 短いと映像が空虚になり、TTSが減速補正されて不自然になる。必ず下限以上。
- 上限超過禁止: 音声が途中で切れるか加速補正で不自然になる。
- 10文字以下絶対禁止。全カットが内容を持つこと。
- 全カットで文字数を数えて確認すること。

═══════════════════════════════════════════
[優先度2] 全体の雰囲気統一 — 全カットが一人の語りのように聞こえること
═══════════════════════════════════════════
執筆前、頭の中で以下を確定してから始める:

1. ナレーターペルソナ（一つに固定）:
   - トピックに合うトーン一つ選択: 「秘密を教えてくれる友人」/「冷静な探偵」/
     「興奮したオタク」/「不気味な語り手」/「乾いた観察者」など
   - このペルソナの口調・語彙・文のリズムを最後まで維持。
   - 途中で急に真面目になったり笑ったり、敬体が常体に変わったりするの禁止。

2. 文体の一貫性:
   - 文の長さ: 短文+中文のリズム交差。
   - 語尾統一: 敬体なら最後まで敬体、常体なら最後まで常体。
   - 同じ接続詞・感嘆詞の繰り返し使用OK — むしろキャラクターが立つ。

3. ストーリー緊張度曲線（相対比率で設計 — 総カット数に合わせて自動スケール）:
   - 全体0~4%（冒頭フック）: 最大強度のフック（[優先度3]参照）
   - 全体5~20%（引き込み）: 問題提起、伏線、「でももっと変なことがある」式に引き続ける
   - 全体20~50%（本論）: 具体的事例・数字・ディテールの連打
   - 全体50~75%（逆転ゾーン）: ★逆転または2次暴露★ — それまで信じていた前提を覆す情報
   - 全体75~90%（余波）: 逆転以降の意味・波紋を説明
   - 全体90~100%（締め）: 余韻のある締めくくり、考えさせる一言を投げる

4. ムードの一貫性:
   - トピックに合うトーン一つ選択: ミステリー/好奇心/畏敬/不気味/愉快な驚き など。
   - 選択したトーンから逸脱する文禁止。
   - 例: 不気味トーンなら最後まで不気味に、途中のギャグ禁止。

═══════════════════════════════════════════
[優先度3] フッキング — 最初の0~4%が動画の生死を決める
═══════════════════════════════════════════
- cut_number=1 は**必ず疑問形の文**で終える。句点ではなく**全角の「？」**で終わること。
  理由: 視聴者を「答えを知りたい」状態に引き込まなければならない。断定で始めると
  「へー、そうなんだ」でスキップされる。
- 同時に台本全体で最も強烈な一言であること。「えっ?! 答えは?」と思わせる一撃。
- 以下4つの感性から**毎エピソード異なるもの**を選ぶ。同じチャンネルで3本連続同じパターン禁止。

  (A) 隠された事実の確認型
      「{対象}が実は{意外な事実}だって、ご存知でしたか？」
      例: 「私たちが毎日飲んでいる水、実は恐竜のおしっこだってご存知でしたか？」

  (B) 反事実的仮定型
      「もし{極端な仮定}だとしたら、{結果}はどうなるでしょうか？」
      例: 「もし明日、地球の酸素がたった5秒だけ消えたら、私たちは生き残れるでしょうか？」

  (C) 常識逆転の問いかけ型
      「なぜ{対象}は、私たちの常識とは正反対なのでしょうか？」
      例: 「なぜ地球で最も危険な動物はサメでもライオンでもなく、蚊なのでしょうか？」

  (D) 選択・ジレンマ型
      「{数}つのうち、{条件}なのがたった1つ。あなたならどれを選びますか？」
      例: 「3つの扉のうち、自由につながるのはただ1つ。あなたならどの扉を開けますか?」

- 禁止の始まり:
  ✗ 「こんにちは」「今日は〜について」「〜を紹介します」
  ✗ ウィキペディアの定義文から始めること
  ✗ 「〜とは何でしょう？」のような**中身のない**単純定義質問
    (上の4パターンの質問形とは区別 — 上は事実・仮定・逆転・選択が質問に織り込まれている)
  ✗ cut_number=1 を句点で終わらせること (必ず「？」で終える)
- 2~5 番目のカット: 連続の餌まき。
  「でもこれはまだ始まりでもない」
  「ここでおかしなことが一つ」
  「人々が知らなかった事実がある」
  のような引き込み文を混ぜてスキップ防止。
- フックも必ず{target_range}文字以内で解決。質問が長くなって文字数を超えると本編が削られて損。

═══════════════════════════════════════════
[優先度4] 逆転 — 最低1回、できれば2回
═══════════════════════════════════════════
- 逆転のない脚本は最後まで見られない。
- 逆転 = 視聴者が全体50%地点まで信じていた前提を覆す情報。
- 例示構造:
  * 「実は〜ではなかった」
  * 「本当の理由は別にあった」
  * 「しかし数年後、すべてが嘘だったと判明した」
  * 「ここまでが教科書の説明です。実際は正反対です」
- 逆転直前のカット(全体50%付近)には「でもここから本当の変なことが始まる」
  のような合図文を配置。
- 逆転は事実ベースで。虚構を作り出さないこと。
- 事実ベースの逆転がない主題なら以下のいずれかで代替:
  * 通念の覆し: 多くが信じる常識が実際は違う
  * あまり知られていない視点: 主流説明の背後にある少数専門家の見解
  * 最新のアップデート: 最近の研究で従来の説明が変わった点
  * 隠れた利害関係: 誰がなぜこの話を特定方向に押したのか
  これら四つでも逆転が作れなければ、無理に逆転を作らず
  好奇心曲線(より深い謎 → さらに深い謎)で代替。

═══════════════════════════════════════════
[優先度5] 面白さ — 情報の羅列ではなく物語
═══════════════════════════════════════════
- 全カットは「情報伝達」ではなく「物語進行」でなければならない。
- 数字は比較で: 「3000万ドル」→「高校生2万人が1年間稼ぐ額」
- 抽象は場面で: 「深刻な問題」→「エンジニアが深夜3時の会議室で頭を抱えた」
- 1カットに1場面・1感情・1情報。3つ詰め込まない。
- 退屈になるたびリズムを崩す文を挿入:
  「でも笑えるのが」
  「本当に呆れるのはここから」
  「ここで想像もしないことが起きる」
- 事実は具体的に。「多くの人が」→「2万3千人が」。「昔」→「1987年6月」。
- ただし、知らない数字・日付は書かないこと。具体性より正確性優先。

═══════════════════════════════════════════
[優先度6] 画像プロンプト（英語）— セリフと正確にマッチング
═══════════════════════════════════════════
image_prompt は **被写体・構図・動作・背景オブジェクト** のみを記述。英語で簡潔に。

★★★ 絶対禁止 — 画像に文字（テキスト）を描かせてはならない ★★★
- **いかなる場合も**、読める文字・単語・数字・記号を画像に含めてはならない。
  理由: 画像生成モデルが描く文字はほぼ必ず崩れた綴り・歪んだ字形になり、
  映像全体の完成度を台無しにする。
- image_prompt に以下の語・表現が入れば **即失敗**:
  text, letters, words, writing, "sign that says ～", "label reading ～",
  "title on screen", caption, typography, font, handwriting, printed words,
  book page, newspaper, menu, "poster saying ～", "billboard with ～",
  tattoo text, screen displaying words, subtitle など、読める文字の記述すべて。
- 文字が主役になる被写体自体を避けること: 書籍の開いたページ、新聞、看板、
  ポスター、店舗の表札、Tシャツのロゴ、UIテキスト付き画面など。
  どうしても必要なら "blank book cover"、"unmarked sign"、"blurred screen"、
  "abstract symbols only, no readable text" のように **文字が無いことを明示**。
- 数字も同じ。"a clock showing 3:47" や "a license plate ABC-123" のように
  読める数字を要求しないこと。必要なら "an analog clock face"、"a generic
  car rear" のように形だけ記述。

★ 絶対に使わないこと (スタイル関連):
- 色: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- 照明/ムード: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- アートスタイル: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- 品質修飾語: high quality, detailed, cinematic, 4k, masterpiece

★ セリフ-画像マッチング原則:
- 該当カットのナレーションの **核心名詞・動詞1~2個** を視覚化。
- セリフが「エンジニアが深夜に頭を抱えた」→
  "an engineer sitting in a dim office at night, hands on his head, computer screens glowing, empty coffee cups on desk"
- 数字・比較・抽象は比喩的な物理場面に:
  「3000万ドル」→ "stacks of dollar bills filling a warehouse"
- 転換カットもストーリーの流れとつながるように。

★ 変化感必須:
- 連続カットで同じ構図・同じ背景を繰り返すの禁止。
- wide shot / medium / close-up、屋内/屋外、昼/夜、正面/側面 を交互に。

★ スタイル固定:
- スタイル・色調・照明・画風は **ユーザーが添付するリファレンス画像のみから** 決定される。
  プロンプトに色やアートスタイルの単語を入れるとリファレンスと衝突して結果が壊れる。
- 「全体画像スタイル」フィールドにユーザーが何を書いていても、image_prompt にそのテキストを注入しないこと。
  image_prompt には「このカットに何が映っているか」だけを残す。

良い例: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
悪い例: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

═══════════════════════════════════════════
[優先度7] キャラクター登場ルール（必須）
═══════════════════════════════════════════
- ★★★ このルールは最重要。違反すると映像が台無しになる ★★★
- キャラクターが提供されても、全カットにキャラクターを入れないこと！
- キャラクター（人物・フィギュア含む）は全カットの20〜30%にのみ登場。
- キャラクター登場カット: 導入（最初のカット）、重要シーン2〜3個、逆転の瞬間、締め — これ以外は絶対に入れない。
- ★★★ キャラクター不在カット（全体の70〜80%）: 必ず人物なしでオブジェクト、風景、背景、図表、地図、抽象ビジュアル、自然現象、物のクローズアップのみ ★★★
- 不在カットの image_prompt に person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer, worker, child, kid, observer, viewer, narrator などの人物単語が一つでもあれば失敗とみなす。
- 登場カットでは image_prompt にキャラクターの **形・動作・ポーズ** を直接記述
  例: "a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel"
  形態的特徴のみ — 色や画風は入れない。
- 形状記述を省略すると画像にキャラクターが出ない。
- 良い不在カット例: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- 良い不在カット例: "close-up of an oil barrel label, rust texture, industrial warehouse background"
- 悪い不在カット例: "a researcher examining an oil barrel" ← 人物あり！失敗！

═══════════════════════════════════════════
[優先度8] その他ルール
═══════════════════════════════════════════
- scene_type: title / narration / transition / ending
- チャンネル登録・いいねのお願い絶対禁止（視聴者離脱 + ポリシーリスク）。
- 最後のカット: 余韻。「〜かもしれない」のような開かれた結末、または後頭部を叩くような一言。
- 事実を捏造しないこと。知らない数字・日付・人名は書かないこと。
"""


def get_system_prompt(language: str = "ko", config: dict | None = None) -> str:
    """Return the appropriate system prompt based on language.

    config 가 주어지면 TTS 모델·속도에 맞춰 글자/단어 한도를 동적으로 포맷한다.
    config 가 없으면 기본값(speed=1.0, openai-tts)으로 포맷.
    """
    from app.config import TTS_MAX_DURATION

    config = config or {}
    try:
        tts_speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        tts_speed = 1.0
    tts_model = config.get("tts_model", "openai-tts")

    # 아동 보이스 보정
    voice_preset = str(config.get("tts_voice_preset", "") or "")
    effective_speed = tts_speed
    if "child" in voice_preset and tts_model == "openai-tts":
        effective_speed = min(4.0, effective_speed + 0.15)
    if tts_model == "elevenlabs":
        effective_speed = max(0.7, min(1.2, effective_speed))
    else:
        effective_speed = max(0.25, min(4.0, effective_speed))

    tts_max_sec = TTS_MAX_DURATION  # 4.5

    def _sub(template: str, replacements: dict) -> str:
        """JSON 중괄호와 충돌하지 않도록 단순 문자열 치환."""
        result = template
        for key, val in replacements.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    if language == "en":
        wps = round(2.5 * effective_speed, 1)
        max_words = int(tts_max_sec * wps)
        target_words = max_words - 1
        min_words = max(4, max_words - 2)
        low = min_words
        return _sub(SCRIPT_SYSTEM_PROMPT_EN, {
            "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "words_per_sec": wps, "max_words": max_words,
            "target_words": target_words, "min_words": min_words,
            "target_range": f"{low}~{max_words}",
        })
    if language == "ja":
        cps = round(5.5 * effective_speed, 1)
        max_chars = int(tts_max_sec * cps)
        target_chars = max_chars - 2
        min_chars = max(8, max_chars - 4)
        low = min_chars
        return _sub(SCRIPT_SYSTEM_PROMPT_JA, {
            "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "chars_per_sec": cps, "max_chars": max_chars,
            "target_chars": target_chars, "min_chars": min_chars,
            "target_range": f"{low}~{max_chars}",
        })
    # 한국어
    cps = round(5.0 * effective_speed, 1)
    max_chars = int(tts_max_sec * cps)
    target_chars = max_chars - 2  # TTS 보정 없이 자연스러운 길이
    min_chars = max(8, max_chars - 4)
    low = min_chars
    return _sub(SCRIPT_SYSTEM_PROMPT_KO, {
        "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
        "chars_per_sec": cps, "max_chars": max_chars,
        "target_chars": target_chars, "min_chars": min_chars,
        "target_range": f"{low}~{max_chars}",
    })


# Keep backward compat
SCRIPT_SYSTEM_PROMPT = get_system_prompt("ko")


class BaseLLMService(ABC):
    """대본 생성 AI 모델의 공통 인터페이스"""

    model_id: str
    display_name: str

    @abstractmethod
    async def generate_script(self, topic: str, config: dict) -> dict:
        """주제와 설정을 받아 대본 JSON을 반환"""
        pass

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
        backend 쪽에서 최종 title 은 "EP. N - {title_hook}" 으로 조립합니다.
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
                f"attention: {char}. Render as an extreme close-up, face filling 35-55% "
                f"of the frame, offset to the left or right third so the opposite side "
                f"has clean negative space for text overlay later. The character's "
                f"facial expression must be EXAGGERATED and emotionally loud — pick ONE "
                f"from: wide-eyed shock, jaw-drop awe, intense determination with furrowed "
                f"brow, explosive laugh, cinematic tears, gritted-teeth rage — whichever "
                f"best matches the hook. Eyes must be razor sharp and locked toward the "
                f"viewer. "
            )
        else:
            subject_clause = (
                f"ONE dominant hero subject — either a human face in extreme close-up "
                f"with an exaggerated emotion, or a single iconic symbolic object with "
                f"dramatic scale. Fills 35-55% of the frame, offset to the left or right "
                f"third, leaving clean negative space on the opposite side for later "
                f"text overlay. Razor sharp focus on the eyes or the key edge of the "
                f"object. "
            )
        return (
            f'A scroll-stopping, click-bait YouTube thumbnail for a video titled "{t}". '
            f"{tp_clause}"
            f"PRIMARY GOAL: within 1 second on a 2-inch phone screen, the viewer must "
            f"feel a strong emotional pull (curiosity, shock, awe, fear, triumph, "
            f"disgust, or tension). "
            f"{subject_clause}"
            f"STYLE REFERENCE: if reference images are provided alongside this prompt, "
            f"faithfully follow THEIR exact art direction — same palette, same rendering "
            f"technique (photoreal vs illustration vs anime vs 3D), same line/brush "
            f"character, same overall mood. Treat the references as ground truth for "
            f"visual style and only deviate for composition. "
            f"LIGHTING: dramatic three-point lighting, strong rim light, warm key, cool "
            f"fill, deep crushed shadows. Avoid flat or even lighting. "
            f"COLOR: ultra-high contrast, saturation pushed for mobile readability — "
            f"punchy reds, electric blues, acid yellows or deep teals, with genuinely "
            f"black shadows. No washed-out pastels. "
            f"DEPTH: shallow depth of field, creamy bokeh background with a single "
            f"atmospheric highlight so nothing competes with the hero. "
            f"COMPOSITION: 16:9 landscape, rule-of-thirds, extremely readable silhouette. "
            f"QUALITY: 4k ultra-detailed, editorial-grade render, top-1% YouTube "
            f"creator production value. "
            f"HARD NEGATIVE — nothing of the following may appear in the image: "
            f"text, words, letters, numbers, captions, logos, watermarks, typography, "
            f"subtitles, signs, UI chrome, blurry faces, low resolution, flat lighting, "
            f"cluttered backgrounds, generic stock-photo vibes, extra limbs, warped hands."
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
                f"Describe the character's appearance (clothing, face, expression, pose, "
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
            f"otherwise a dramatic human face close-up OR a single iconic symbolic "
            f"object). No crowds, no group shots, no split attention.\n"
            f"2. The hero fills 35-55% of the frame and is offset to the LEFT or RIGHT "
            f"third — leave deliberate clean negative space on the opposite side so "
            f"text can be composited later. Describe this negative space explicitly.\n"
            f"3. EMOTIONAL HOOK (most important): if a human/character face is the hero, "
            f"describe ONE exaggerated loud emotion — wide-eyed shock, jaw-drop awe, "
            f"intense glare with furrowed brow, explosive laugh, cinematic tears, "
            f"gritted-teeth rage — whichever best matches the narration tone. Neutral "
            f"faces do NOT click.\n"
            f"4. Razor sharp focus on the subject's eyes (or the object's key edge). "
            f"Creamy bokeh background. Shallow depth of field.\n"
            f"5. Lighting: dramatic three-point, strong rim light, warm key / cool fill, "
            f"high contrast, genuinely black shadows. No flat even lighting.\n"
            f"6. Colors: ultra-saturated, phone-screen-friendly — push punchy reds, "
            f"electric blues, acid yellows, deep teals. Avoid washed-out pastels unless "
            f"the reference image explicitly requires them.\n"
            f"7. Single scroll-stopping hook (mystery, awe, tension, fear, triumph, "
            f"disgust, humor). Pick ONE that best fits the narration — do not hedge.\n"
            f"8. Rendering style: default photoreal 4k editorial quality, BUT if the "
            f"reference images show an illustration/anime/3D style, mirror that style "
            f"exactly.\n"
            f"9. 16:9 landscape framing. Never portrait, never square.\n"
            f"10. Optional high-impact visual props — impossible scale, juxtaposition, "
            f"floating elements, a single shocking contrast — if they match the topic.\n"
            f"\n"
            f"★ HARD NEGATIVES — include this clause verbatim in your output prompt:\n"
            f'"no text, no words, no letters, no numbers, no captions, no logos, no '
            f'watermarks, no typography, no subtitles, no signs, no UI chrome, no '
            f'blurry face, no warped hands, no extra limbs, no low resolution, no flat '
            f'lighting, no cluttered background, no generic stock photo look". '
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
        return {
            "ko": "Korean (한국어)",
            "en": "English",
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
            f"Task: Produce 10 to {max_tags} YouTube tags that will help this specific "
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
        hook_limit = 22 if is_cjk else 48
        hook_rule_label = (
            f"{hook_limit}자 이하 (공백 포함)" if is_cjk else f"{hook_limit} characters max"
        )

        ep_block = ""
        if episode_number is not None:
            ep_block = (
                f"\n★ EPISODE MODE ★\n"
                f"This video is Episode #{episode_number} of a running series. The backend "
                f"will prepend 'EP. {episode_number} - ' to your hook automatically, so "
                f'your "title_hook" MUST NOT include the words "EP", "Episode", "에피소드", '
                f'"제{episode_number}화", or the number itself. Write ONLY the short hook '
                f"after the dash.\n"
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
            f"Task: based on the source material below, produce a SHORT hook line, a rich "
            f"long description, and a tag list.\n"
            f"\n"
            f"Output format — return ONLY a single JSON object with these keys:\n"
            f'  - "title_hook": string. {hook_rule_label}. Written in {lang_name}. '
            f"A single short, punchy hook phrase — NOT a full sentence, NOT clickbait "
            f"ellipsis, NO emojis, NO quotation marks, NO trailing punctuation. "
            f"Think of it as what goes AFTER 'EP. N - '. Examples of good length: "
            f"'석유의 비밀', 'The truth about oil', '石油の真実'. "
            f"Examples of bad: full sentences, questions, anything over the limit.\n"
            f'  - "description": string. 600 to 1500 characters. Written in {lang_name}. '
            f"Structure: (1) a 2-3 sentence hook that makes the viewer want to watch, "
            f"(2) a 3-5 sentence summary of what the video covers, "
            f"(3) 4-6 bullet-style lines listing key points or chapter highlights "
            f"(use '•' or '-' as the bullet marker), "
            f"(4) a short closing line inviting likes/comments/subscribes. "
            f"Separate the sections with blank lines. Plain text only — no markdown headers.\n"
            f'  - "tags": JSON array of 10 to {max_tags} strings. Each tag under 30 '
            f"characters. All in {lang_name}. No # symbols. No duplicates. "
            f"Mix broad category tags and specific topical tags.\n"
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
        language = config.get("language", "ko")
        return get_system_prompt(language, config)

    @staticmethod
    def _calc_narration_limits(config: dict) -> dict:
        """TTS 모델·속도 설정에 따라 나레이션 글자/단어 수 한도를 계산한다.

        Returns: {"max_chars": int, "target_range": str, "words_per_sec": float}
        (영어는 max_words / target_words_range 로 대체)
        """
        from app.config import TTS_MAX_DURATION

        language = config.get("language", "ko")
        try:
            speed = float(config.get("tts_speed", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0

        # 아동 보이스면 speed 가 +0.15 되는 것도 반영
        voice_preset = str(config.get("tts_voice_preset", "") or "")
        tts_model = config.get("tts_model", "openai-tts")
        if "child" in voice_preset and tts_model == "openai-tts":
            speed = min(4.0, speed + 0.15)

        # ElevenLabs 는 speed 를 [0.7, 1.2] 로 clamp
        if tts_model == "elevenlabs":
            speed = max(0.7, min(1.2, speed))
        # OpenAI 는 [0.25, 4.0]
        else:
            speed = max(0.25, min(4.0, speed))

        max_secs = TTS_MAX_DURATION  # 4.5

        if language == "ko":
            # 한국어 TTS: 기본 ~5 글자/초 (speed 1.0 기준)
            chars_per_sec = 5.0 * speed
            max_chars = int(max_secs * chars_per_sec)
            # v1.1.53: 하한을 max의 90%로 설정 — 나레이션이 짧으면 음성도 짧아짐
            low = max(15, int(max_chars * 0.90))
            return {"max_chars": max_chars, "target_range": f"{low}~{max_chars}", "lang": "ko"}
        elif language == "ja":
            # 일본어 TTS: 기본 ~5.5 문자/초
            chars_per_sec = 5.5 * speed
            max_chars = int(max_secs * chars_per_sec)
            low = max(15, int(max_chars * 0.90))
            return {"max_chars": max_chars, "target_range": f"{low}~{max_chars}", "lang": "ja"}
        else:
            # 영어 TTS: 기본 ~2.5 단어/초
            words_per_sec = 2.5 * speed
            max_words = int(max_secs * words_per_sec)
            low = max(8, int(max_words * 0.90))
            return {"max_words": max_words, "target_range": f"{low}~{max_words}", "lang": "en"}

    def _build_user_prompt(self, topic: str, config: dict) -> str:
        duration = config.get("target_duration", 600)
        style = config.get("style", "news_explainer")
        language = config.get("language", "ko")
        # v1.1.73: 사용자 금칙/필수 제약 블록. config.content_constraints 에
        # 자유 텍스트로 저장된 규칙(예: "환단고기 등 위서 인용 금지", "사료
        # 부족 시 '설이 있다' 로 열어둘 것") 을 대본 프롬프트 최상단에 최우선
        # 순위로 주입한다. topic 한 줄에 제약이 섞여 있으면 모델이 일반 설명
        # 으로 해석하고 무시할 위험이 있어, 언어별 강조 헤더와 함께 분리.
        constraints_raw = (config.get("content_constraints") or "").strip()
        # 5-second unit rule (v1.1.26): cuts = ceil(duration / 5)
        # Uses ceil so 601s → 121 cuts (aligned with frontend expectedCuts)
        try:
            duration_int = max(5, int(duration))
        except (TypeError, ValueError):
            duration_int = 600
        cut_count = max(1, math.ceil(duration_int / 5))
        # v1.1.30: image_global_prompt 는 이미지 생성 시 레퍼런스 이미지에서만 스타일을
        # 가져오도록 정책이 바뀌었으므로, LLM 대본 생성 단계에서도 사용자의 global_style
        # 텍스트를 image_prompt 에 주입하지 않는다. 캐릭터 설명만 참고 가능하도록 전달.
        character_description = (config.get("character_description") or "").strip()

        style_instruction = ""
        if character_description:
            if language == "en":
                style_instruction = (
                    f"\n\n★ CHARACTER REFERENCE (for cuts where the character appears):\n"
                    f"{character_description}\n\n"
                    f"Rules:\n"
                    f"- The character should appear in only 20-30% of cuts at natural story moments.\n"
                    f"- In those cuts, describe the character's SHAPE/POSE/ACTION in image_prompt.\n"
                    f"- Do NOT mention palette, color, or art style — those come from the attached reference images.\n"
                )
            elif language == "ja":
                style_instruction = (
                    f"\n\n★ キャラクター参考（キャラクター登場カット用）:\n"
                    f"{character_description}\n\n"
                    f"ルール:\n"
                    f"- キャラクターは全カットの20〜30%の自然な場面にのみ登場させる。\n"
                    f"- 登場カットでは image_prompt にキャラクターの形・ポーズ・動作を記述する。\n"
                    f"- 色・パレット・画風は書かないこと（添付リファレンス画像から取得される）。\n"
                )
            else:
                style_instruction = (
                    f"\n\n★ 캐릭터 참고 정보 (캐릭터 등장 컷용):\n"
                    f"{character_description}\n\n"
                    f"규칙:\n"
                    f"- 캐릭터는 전체 컷의 20~30% 만, 스토리상 자연스러운 위치에만 등장시킵니다.\n"
                    f"- 등장 컷의 image_prompt 에는 캐릭터의 형상·포즈·동작만 기술합니다.\n"
                    f"- 색상·팔레트·그림체 단어는 쓰지 마세요. 스타일은 첨부된 레퍼런스 이미지에서 가져갑니다.\n"
                )

        # v1.1.73: 언어별 "사용자 최우선 제약" 블록.
        # - content_constraints 입력값을 bullet 친화적으로 약하게 정규화
        #   (사용자가 " / " 로 이어 쓴 경우 줄바꿈으로 쪼개 가독성↑).
        # - 비어 있으면 블록 전체 생략 — 기존 프롬프트와 하위 호환.
        def _normalize_constraints(raw: str) -> str:
            s = raw.replace("\r\n", "\n")
            # 사용자들이 자주 쓰는 구분자(" / ", " · ") 를 줄바꿈으로.
            for sep in (" / ", " · "):
                s = s.replace(sep, "\n")
            lines = [ln.strip(" -•·").strip() for ln in s.split("\n")]
            lines = [ln for ln in lines if ln]
            return "\n".join(f"- {ln}" for ln in lines)

        constraints_block_en = ""
        constraints_block_ja = ""
        constraints_block_ko = ""
        if constraints_raw:
            norm = _normalize_constraints(constraints_raw)
            constraints_block_en = (
                "★★★ USER ABSOLUTE RULES — HIGHEST PRIORITY ★★★\n"
                "These rules override every other instruction. Violating any of "
                "them means the script is a failure.\n"
                f"{norm}\n"
                "\n"
            )
            constraints_block_ja = (
                "★★★ ユーザー絶対ルール — 最優先 ★★★\n"
                "以下のルールは他のあらゆる指示より優先されます。1 つでも破った"
                "場合、その台本は失敗扱いです。\n"
                f"{norm}\n"
                "\n"
            )
            constraints_block_ko = (
                "★★★ 사용자 절대 제약 — 최우선 순위 ★★★\n"
                "아래 규칙은 다른 모든 지시보다 우선합니다. 하나라도 어기면 "
                "이 대본은 실패입니다.\n"
                f"{norm}\n"
                "\n"
            )

        if language == "en":
            return (
                f"{constraints_block_en}"
                f"Topic: {topic}\n"
                f"Target duration: {duration_int} seconds\n"
                f"\n"
                f"★★★ HARD CONSTRAINT — 5-SECOND UNIT RULE (ABSOLUTE) ★★★\n"
                f"- You MUST output EXACTLY {cut_count} cuts. Not {cut_count - 1}, not {cut_count + 1}. Exactly {cut_count}.\n"
                f"- Every cut is EXACTLY 5 seconds long (duration_estimate = 5.0).\n"
                f"- cut_number must run from 1 to {cut_count} with no gaps.\n"
                f"- Total runtime = {cut_count} × 5 = {cut_count * 5} seconds.\n"
                f"- If you output fewer or more than {cut_count} cuts, the pipeline will FAIL.\n"
                f"\n"
                f"Style: {style}\n"
                f"Language: English"
                f"{style_instruction}"
            )
        if language == "ja":
            return (
                f"{constraints_block_ja}"
                f"トピック: {topic}\n"
                f"目標時間: {duration_int}秒\n"
                f"\n"
                f"★★★ 絶対制約 — 5秒単位ルール（必ず守ること） ★★★\n"
                f"- 必ず正確に {cut_count} カットを出力すること。{cut_count - 1}でも{cut_count + 1}でもなく、{cut_count} ちょうど。\n"
                f"- 全カットは正確に5秒（duration_estimate = 5.0）。\n"
                f"- cut_number は 1 から {cut_count} まで欠番なく連番。\n"
                f"- 総再生時間 = {cut_count} × 5 = {cut_count * 5} 秒。\n"
                f"- {cut_count} カット以外を出力するとパイプラインが失敗します。\n"
                f"\n"
                f"スタイル: {style}\n"
                f"言語: 日本語"
                f"{style_instruction}"
            )
        return (
            f"{constraints_block_ko}"
            f"주제: {topic}\n"
            f"목표 길이: {duration_int}초\n"
            f"\n"
            f"★★★ 절대 제약 — 5초 단위 규칙 (반드시 지킬 것) ★★★\n"
            f"- 반드시 정확히 {cut_count}개의 컷을 출력하세요. {cut_count - 1}개도 {cut_count + 1}개도 아닌, 정확히 {cut_count}개.\n"
            f"- 모든 컷은 정확히 5초 길이입니다 (duration_estimate = 5.0).\n"
            f"- cut_number는 1부터 {cut_count}까지 빠짐없이 연속되어야 합니다.\n"
            f"- 총 재생 시간 = {cut_count} × 5 = {cut_count * 5}초.\n"
            f"- {cut_count}개가 아닌 컷 수를 출력하면 파이프라인이 실패합니다.\n"
            f"\n"
            f"스타일: {style}\n"
            f"언어: 한국어"
            f"{style_instruction}"
        )
