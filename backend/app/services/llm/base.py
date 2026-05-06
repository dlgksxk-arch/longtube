"""Base LLM service interface"""
import math
import re
"""Single source of truth for script-generation prompts.

Script-generation prompts must stay in this file only, regardless of channel,
preset, or model count. Do not add channel-specific or preset-specific script
prompt files; edit the default prompt logic here.
"""

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
  "thumbnail_prompt": "썸네일 프롬프트 (영어 필수). 규칙: 1) 주요 인물·사건·사물의 클로즈업 2) 인물의 감정표현(놀람/경외/충격) 포함 3) 구체적 사물·배경·구도 4) 텍스트·글자·숫자·워터마크 절대 금지 5) 16:9 시네마틱 고화질",
  "thumbnail_hook": "썸네일 큰 글자 2줄. 영상 제목 복사 금지. 예: 아무도 몰랐던\\n진짜 이유",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "나레이션 (한국어)",
      "image_prompt": "이미지 프롬프트 (영어)",
      "duration_estimate": 5.0,
      "scene_type": "title",
      "shorts_candidate": false,
      "shorts_group": 0,
      "shorts_reason": "",
      "shorts_score": 0,
      "shorts_title": ""
    }
  ]
}

═══════════════════════════════════════════
[1순위] 타이밍 — 어기면 영상이 망가진다
═══════════════════════════════════════════
- 총 컷 수는 유저 프롬프트의 지시를 따른다. cut_number 는 1부터 연속, 누락·중복 금지.
- 각 컷: 정확히 5.0초. duration_estimate 는 모든 컷에서 5.0 고정.
- 나레이션은 반드시 {tts_min_sec}~{tts_max_sec}초 분량이어야 한다.
- 현재 TTS: {tts_model}, 속도 {tts_speed}, 초당 약 {chars_per_sec}자.
- 최대 {max_chars}자, 목표 {target_range}자 (공백 포함).
- 모든 컷의 narration 을 출력 직전에 직접 세어라. 공백 포함 글자 수가 {target_range}자를 벗어나면 JSON을 내보내기 전에 내부적으로 고쳐라.
- 음성 생성 단계는 narration을 절대 고쳐주지 않는다. 여기서 틀리면 결과 시간이 그대로 짧거나 길게 남는다.
- 속도 조절/잘라내기 후처리는 사용하지 않는다. 길이는 오직 대본 분량으로만 맞춘다.
- 분량을 맞추려고 "이 지점입니다", "이게 시작입니다", "여기서 갈립니다", "그게 핵심입니다", "정말로요", "맞죠" 같은 일반 꼬리말을 붙이지 마라.
- 짧은 컷은 해당 주제의 구체 정보/사건/원인/결과를 한 조각 더 넣어 자연스럽게 늘려라.
- 하한 미만 금지: 짧으면 최종 영상 싱크가 깨진다. 반드시 하한 이상.
- 상한 초과 금지: 길면 최종 영상 싱크가 깨진다. 반드시 상한 이하.
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
   - 한국어 나레이션은 존댓말 기반의 자연스러운 구어체다. 뉴스 리포트처럼 `-습니다`, `-입니다`, `-했습니다`로 딱딱하게 끊지 마라.
   - `-습니다`, `-입니다`, `-했습니다`, `-됩니다`는 전체 컷의 20% 이하로만 사용하고, 2컷 연속으로 쓰지 않는다.
   - 기본 리듬은 연결형이다: `-했는데요`, `-인데요`, `-하다 보니`, `-그러다`, `-그런데`, `-이었거든요`, `-였죠`, `-였고요`, `-보면요`.
   - 한 컷 안에서도 단정문 하나로 끝내지 말고, 사건에서 원인으로, 원인에서 결과로 자연스럽게 이어 말한다.
     좋은 예: "수나라는 압도적인 병력을 모았는데요, 문제는 고구려가 그 숫자 싸움에 말려들지 않았다는 겁니다."
     나쁜 예: "수나라는 고구려를 공격했습니다. 고구려는 방어했습니다."
   - 같은 종결 어미가 3컷 이상 연속 반복되지 않게 한다. 특히 모든 컷을 `-다.` 로만 끝내지 말 것.
   - 반말로 갑자기 떨어지거나, 지나치게 구어체로 무너지지 않게 톤은 유지한다.
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
- cut_number=1 은 주제와 정확히 맞는 호기심 질문으로 시작한다. 공허한 질문 금지.
- cut_number=2 는 답을 다 말하지 말고 은근한 힌트나 반쯤 열린 답변을 준다.
- cut_number=3 은 "같이 알아보시죠" 류의 본편 진입 멘트로 끝낸다. 단, 상투적인 인사말처럼 쓰지 말고 주제의 긴장을 유지한다.
- 본론 설명은 cut_number=5 부터 시작한다.
- cut_number=1, 2, 3 은 모두 강한 후킹 멘트여야 한다. 정의, 배경 설명, 본론 요약으로 쓰지 말고
  질문·은근한 답변·본편 진입 유도만으로 시작 15초를 고정한다.
- 특히 1~3컷은 짧고 강한 타격형 대사로 쓴다. 느슨하게 설명하지 말고, 한 컷마다
  "뭐지?", "왜?", "다음 말이 뭔데?"가 바로 떠오르게 팍팍 치는 리듬으로 작성한다.
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

★★★ 쉬운 말만 사용 ★★★
- narration 은 중학생도 바로 이해하는 쉬운 한국어로 쓴다.
- 한자어·전문용어·학술어·문어체를 피한다. 꼭 필요한 고유명사만 허용한다.
- 어려운 말이 필요하면 쉬운 말로 풀어쓴다.
  예: "권력 투쟁" → "힘을 잡으려는 싸움", "외교적 갈등" → "나라 사이의 다툼".
- 한 문장에 어려운 개념을 두 개 이상 넣지 말 것.
- image_prompt 도 쉬운 영어 단어만 쓴다. academic, ornate, poetic, esoteric, metaphorical 같은 어려운 표현 금지.

═══════════════════════════════════════════
[6순위] 이미지 프롬프트 (영어) — 대사와 정확히 매칭
═══════════════════════════════════════════
image_prompt 는 **피사체·구도·동작·배경 오브젝트**만 묘사. 영어로, 간결하게.

★★★ 쉬운 영어 단어만 사용 ★★★
- image_prompt 는 초등~중등 수준의 쉬운 영어 명사·동사만 쓴다.
- 어려운 미술 용어, 학술 용어, 시적인 단어, 추상 단어를 쓰지 말 것.
- concrete, visible objects only: person, room, road, boat, table, door, wall, field, river 처럼 눈에 보이는 단어를 우선한다.
- "socio-political", "ritualistic", "ornamental", "symbolic", "mythic", "ethereal", "opulent", "intricate" 같은 단어 금지.

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

★★★ 현대 국기 연상 구도 금지 ★★★
- image_prompt 에 현대 국가의 국기·국장·국가 상징을 연상시키는 시각 요소를 넣지 말 것.
- flag, national flag, country flag, state flag, flagpole, tricolor, stars and stripes,
  canton stars, emblem, national symbol 같은 단어를 쓰지 말 것.
- 특히 일장기/욱일기 연상 구도 금지: red circle on white background, centered red disc,
  red sun disc, rising sun rays, red radial rays, hinomaru 를 쓰지 말 것.
- 깃발이 필요한 장면도 문양 없는 천, 낡은 천 조각, plain cloth banner 정도로만 묘사.

★★★ 손/손가락 클로즈업 금지 — 로컬 SDXL 모델 취약점 ★★★
- image_prompt 의 주 피사체로 hand, hands, fingers, fingertips, palm, knuckles 를 쓰지 말 것.
- "two hands touching", "human hand and robotic hand", "glow between fingertips",
  "holding", "pointing", "reaching hand" 같은 손가락 중심 구도 금지.
- 접촉/협력/발견/선택은 손 대신 실루엣, 오브젝트, 도구, 빛나는 구체, 문양 없는 장치로 표현.
- 인물 동작이 필요하면 손은 작게/부분 가림/단순한 형태로만. 손가락이 화면 전면에 오면 실패.

★★★ 해부학/사지 오류 방지 — 잘린 손, 붙은 다리, 여섯 손가락, 다섯 다리 차단 ★★★
- 사람/캐릭터/동물은 반드시 **완전한 하나의 몸**으로 묘사. 팔다리가 배경이나 다른 몸에 붙으면 실패.
- 사람/캐릭터: one head, one torso, two arms, two legs. 손은 작고 단순하게. 팔/손/다리 클로즈업 금지.
- 개/고양이/말/소/사슴/늑대 등 네발 동물: one head, one torso, exactly four legs/paws/hooves, one tail if visible.
- 동물은 side-view 또는 three-quarter standing/walking pose 를 우선 사용. running/jumping/galloping 은 여분 다리 오류가 잦으니 피하라.
- crowd, overlapping bodies, tangled limbs, pile of animals, close-up paws/feet, cropped body, partial body, out of frame 금지.
- 여러 인물/동물은 서로 떨어진 실루엣으로 배치하고, 몸통·머리·팔다리가 겹치지 않게 하라.

★ 절대 쓰지 말 것 (스타일 관련):
- 색상: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- 조명/분위기: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- 아트 스타일: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- 품질 수식어: high quality, detailed, cinematic, 4k, masterpiece

★ 대사-이미지 매칭 원칙:
- 해당 컷 나레이션의 **핵심 명사·동사 1~2개**를 시각화.
- 대사가 "엔지니어가 새벽에 멘붕했다" →
  "an exhausted engineer slumped beside a computer desk at night, face partly hidden, empty coffee cups on desk"
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

좋은 예: "a researcher standing beside an unmarked oil barrel on a sandy beach, pipes and boat in the background, magnifying glass on a nearby crate"
나쁜 예: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

═══════════════════════════════════════════
[7순위] 캐릭터 등장 규칙 (필수)
═══════════════════════════════════════════
- ★★★ 이 규칙이 가장 중요하다. 절대 어기지 말 것! ★★★
- 사용자가 캐릭터를 제공한 경우, 필요한 컷에서는 캐릭터를 자유롭게 등장시켜도 된다.
- 캐릭터 등장 비율에 대한 전역 제한은 두지 않는다.
- 캐릭터를 넣을지 여부는 각 컷의 전달력과 장면 구성에 맞춰 판단한다.
- 캐릭터 등장 컷에서는 image_prompt 에 캐릭터의 **형상·행동·포즈** 를 직접 서술하라
  예: "a small character wearing a yellow hat standing beside a large magnifying glass on a tripod, looking at an oil barrel"
  단, 색상 팔레트나 그림체 단어는 넣지 말 것 — 외형의 형태적 특징만.
- 캐릭터 외모 묘사를 빼면 이미지에 캐릭터가 안 나온다.
- 캐릭터가 꼭 필요 없는 컷은 오브젝트·풍경 중심으로 구성해도 된다.

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
  "thumbnail_prompt": "Thumbnail prompt (English). Rules: 1) Close-up of the key person, event, or object 2) Include a person's emotional expression (shock/awe/surprise) 3) Specific objects, backgrounds, composition 4) NO text/letters/numbers/watermarks 5) 16:9 cinematic, high quality",
  "thumbnail_hook": "Two-line large thumbnail text in the video language. Do not copy the title.",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "Narration (English)",
      "image_prompt": "Image prompt (English)",
      "duration_estimate": 5.0,
      "scene_type": "title",
      "shorts_candidate": false,
      "shorts_group": 0,
      "shorts_reason": "",
      "shorts_score": 0,
      "shorts_title": ""
    }
  ]
}

═══════════════════════════════════════════
[PRIORITY 1] Timing — violating this breaks the video
═══════════════════════════════════════════
- Total cut count follows the user prompt. cut_number is sequential from 1, no gaps or duplicates.
- Each cut: EXACTLY 5.0 seconds. duration_estimate = 5.0 for every cut.
- Narration MUST naturally read within {tts_min_sec}~{tts_max_sec} seconds.
- Current TTS: {tts_model}, speed {tts_speed}, ~{words_per_sec} words per second.
- MAX {max_words} words, target {target_range} words per narration.
- Before returning JSON, count every narration. If any cut is outside {target_range} words, fix it internally before output.
- If the user/content prompt gives a different per-cut word range, ignore that conflicting range; this TTS voice timing range wins.
- The voice generation step will NOT rewrite narration. If timing is wrong here, the generated audio remains too short or too long.
- Do NOT rely on speed-up, slowdown, or audio cutting. Solve timing only by narration length.
- Below the minimum: FORBIDDEN — the final sync breaks. Must hit the lower bound.
- Above the maximum: FORBIDDEN — the final sync breaks. Stay at or below the upper bound.
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
- cut_number=1 MUST start with a topic-specific curiosity question. Empty generic questions are forbidden.
- cut_number=2 gives only a subtle partial answer or hint, never the full explanation.
- cut_number=3 ends in a "let's find out" rhythm while keeping tension.
- Start the real body explanation from cut 5.
- cut_number=1, 2, and 3 MUST all be strong hook lines. Do not use them for definitions,
  background setup, or a neutral summary. Lock the first 15 seconds with a question,
  subtle answer, and body-entry invitation.
- Cuts 1-3 must hit hard and fast. Do not explain lazily. Each line should create
  an immediate "what?", "why?", or "what comes next?" reaction.
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

★★★ USE SIMPLE WORDS ONLY ★★★
- narration must use plain everyday words that a middle-school viewer can understand.
- Avoid academic words, expert jargon, literary phrasing, and stiff formal wording.
- If a hard term is necessary, explain it with simple words.
  Example: "political factionalism" → "groups fighting for power".
- Do not put two hard ideas in one sentence.
- image_prompt must also use simple English only. No academic, ornate, poetic, esoteric, or metaphorical wording.

═══════════════════════════════════════════
[PRIORITY 6] Image prompt (English) — must match the narration exactly
═══════════════════════════════════════════
image_prompt describes ONLY subject, composition, action, and background objects. English, concise.

★★★ SIMPLE ENGLISH ONLY ★★★
- image_prompt must use easy elementary-to-middle-school English nouns and verbs.
- Avoid art jargon, academic terms, poetic words, and abstract words.
- Prefer concrete visible objects: person, room, road, boat, table, door, wall, field, river.
- Forbidden hard words include: socio-political, ritualistic, ornamental, symbolic, mythic, ethereal, opulent, intricate.

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

★★★ HARD BAN — NO MODERN NATIONAL FLAG-LIKE MOTIFS ★★★
- image_prompt MUST NOT include visuals resembling modern national flags, state flags,
  national emblems, or country symbols.
- Do NOT use: flag, national flag, country flag, state flag, flagpole, tricolor,
  stars and stripes, canton stars, emblem, national symbol.
- Especially avoid Japanese flag / rising sun motifs: red circle on white background,
  centered red disc, red sun disc, rising sun rays, red radial rays, hinomaru.
- If a scene needs a banner, describe only a plain unmarked cloth banner or torn cloth,
  with no emblem, no stripes, no national colors, and no flag-like composition.

★★★ HARD BAN — NO CLOSE-UP HANDS OR FINGERS ★★★
- Do NOT make hand, hands, fingers, fingertips, palm, or knuckles the main subject of image_prompt.
- Avoid hand-centered compositions such as "two hands touching", "human hand and robotic hand",
  "glow between fingertips", "holding", "pointing", or "reaching hand".
- Show contact, cooperation, discovery, or choice with silhouettes, objects, tools, glowing orbs,
  or unmarked devices instead of fingers.
- If a person needs a gesture, keep hands small, partially hidden, and simplified. Foreground
  finger anatomy is a failure.

★★★ ANATOMY / LIMB ERROR PREVENTION — detached hands, six fingers, five-legged dogs ★★★
- Every person, character, or animal must be one complete coherent body. Detached limbs, limbs
  pasted onto the background, or limbs fused to another body are failures.
- Humans/characters: one head, one torso, two arms, two legs. Keep hands small and simple. Avoid
  arm/hand/leg close-ups.
- Quadrupeds such as dogs, cats, horses, cows, deer, wolves, and foxes: one head, one torso,
  exactly four legs/paws/hooves, one tail if visible.
- Prefer side-view or three-quarter standing/walking poses for animals. Avoid running, jumping,
  galloping, tangled legs, close-up paws, cropped bodies, partial bodies, and out-of-frame limbs.
- For multiple people/animals, keep subjects separated with clear silhouettes. No overlapping
  bodies, fused bodies, limb piles, or crowd tangles.

★ NEVER include (style-related):
- Color words: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- Lighting/mood: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- Art style: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- Quality modifiers: high quality, detailed, cinematic, 4k, masterpiece

★ Narration-to-image matching principle:
- Visualize the 1-2 KEY nouns/verbs from the cut's narration.
- If the narration is "an engineer breaking down at dawn" →
  "an exhausted engineer slumped beside a computer desk at night, face partly hidden, empty coffee cups on desk"
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

Good: "a researcher standing beside an unmarked oil barrel on a sandy beach, pipes and boat in the background, magnifying glass on a nearby crate"
Bad: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

═══════════════════════════════════════════
[PRIORITY 7] Character appearance rules (MANDATORY)
═══════════════════════════════════════════
- ★★★ THIS RULE IS CRITICAL. VIOLATING IT RUINS THE VIDEO. ★★★
- If a character is provided, you may place that character in any cut where it helps the scene.
- There is NO global percentage cap for character appearances.
- Decide character presence per cut based on visual clarity and storytelling value.
- For cuts WHERE the character appears, describe the character's **shape, action, and pose** directly in the image_prompt
  Example: "a small character wearing a yellow hat standing beside a large magnifying glass on a tripod, looking at an oil barrel"
  Only morphological features — do NOT mention palette or art style.
- If you omit the character's shape description, the character will NOT appear in the image.
- If a cut works better without the character, object-only or environment-only composition is still allowed.

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
  "thumbnail_prompt": "サムネイルプロンプト（英語必須）。ルール: 1) 主要人物・事件・物体のクローズアップ 2) 人物の感情表現（驚き/畏敬/衝撃）を含む 3) 具体的な物体・背景・構図 4) テキスト・文字・数字・透かし絶対禁止 5) 16:9シネマティック高画質",
  "thumbnail_hook": "サムネイルの大きな文字2行。タイトルをそのままコピーしない。",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "ナレーション（日本語）",
      "image_prompt": "画像プロンプト（英語）",
      "duration_estimate": 5.0,
      "scene_type": "title",
      "shorts_candidate": false,
      "shorts_group": 0,
      "shorts_reason": "",
      "shorts_score": 0,
      "shorts_title": ""
    }
  ]
}

═══════════════════════════════════════════
[優先度1] タイミング — 違反すると映像が壊れる
═══════════════════════════════════════════
- 総カット数はユーザープロンプトの指示に従う。cut_number は 1 から連続、欠番・重複禁止。
- 各カット: 正確に5.0秒。duration_estimate は全カット5.0固定。
- ナレーションは必ず{tts_min_sec}~{tts_max_sec}秒で自然に読める分量。
- 現在のTTS: {tts_model}、速度{tts_speed}、1秒あたり約{chars_per_sec}文字。
- 最大{max_chars}文字、目標{target_range}文字。
- JSONを返す直前に全カットの narration 文字数を数えること。{target_range}文字から外れたカットは出力前に内部で修正すること。
- 音声生成段階は narration を絶対に修正しない。ここで長さを外すと生成音声がそのまま短すぎる/長すぎる状態で残る。
- 速度変更・減速・音声カットで合わせてはいけない。長さは台本の分量だけで調整する。
- 下限未満禁止: 短い場合、最終映像の同期が崩れる。必ず下限以上。
- 上限超過禁止: 長い場合、最終映像の同期が崩れる。必ず上限以下。
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
- cut_number=1 は主題に正確に合う好奇心の質問で始める。中身のない汎用質問は禁止。
- cut_number=2 は答えを言い切らず、控えめなヒントか半分だけ開いた答えにする。
- cut_number=3 は「一緒に見ていきましょう」系の本編導入リズムで終える。ただし緊張感は保つ。
- cut_number=3 の後にインターミッション映像が入る。本論説明は cut_number=5 から始める。
- cut_number=1、2、3 はすべて強いフック台詞にすること。定義、背景説明、中立的な要約に使わず、
  質問、控えめな答え、本編導入だけで最初の15秒を固定する。
- 1〜3カットは短く強い打撃型の台詞にする。ゆるく説明せず、各カットごとに
  「何？」「なぜ？」「次は？」という反応がすぐ出るリズムで書く。
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

★★★ 手・指のクローズアップ禁止 — ローカルSDXLモデルの弱点 ★★★
- image_prompt の主被写体として hand, hands, fingers, fingertips, palm, knuckles を使わない。
- "two hands touching", "human hand and robotic hand", "glow between fingertips",
  "holding", "pointing", "reaching hand" のような指中心の構図は禁止。
- 接触・協力・発見・選択は、手ではなくシルエット、物体、道具、光る球体、
  文字のない装置で表現する。
- 人物のジェスチャーが必要なら、手は小さく、部分的に隠し、単純化する。前景の指の解剖描写は失敗。

★★★ 解剖・四肢エラー防止 — 切れた手、6本指、5本脚の犬を避ける ★★★
- 人物・キャラクター・動物は必ず **一つの完全な体** として描写する。四肢が背景や別の体に付くのは失敗。
- 人物/キャラクター: one head, one torso, two arms, two legs。手は小さく単純に。腕・手・脚のクローズアップは禁止。
- 犬/猫/馬/牛/鹿/狼/狐など四足動物: one head, one torso, exactly four legs/paws/hooves, one tail if visible。
- 動物は side-view または three-quarter standing/walking pose を優先。running/jumping/galloping は余分な脚が出やすいので避ける。
- crowd, overlapping bodies, tangled limbs, pile of animals, close-up paws/feet, cropped body, partial body, out of frameは禁止。
- 複数の人物/動物は離して配置し、胴体・頭・四肢が重ならないようにする。

★ 絶対に使わないこと (スタイル関連):
- 色: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome
- 照明/ムード: cinematic lighting, moody, dramatic lighting, soft light, golden hour
- アートスタイル: illustration style, cartoon, anime, photorealistic, watercolor, Ghibli, Pixar
- 品質修飾語: high quality, detailed, cinematic, 4k, masterpiece

★ セリフ-画像マッチング原則:
- 該当カットのナレーションの **核心名詞・動詞1~2個** を視覚化。
- セリフが「エンジニアが深夜に途方に暮れた」→
  "an exhausted engineer slumped beside a computer desk at night, face partly hidden, empty coffee cups on desk"
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

良い例: "a researcher standing beside an unmarked oil barrel on a sandy beach, pipes and boat in the background, magnifying glass on a nearby crate"
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
  例: "a small character wearing a yellow hat standing beside a large magnifying glass on a tripod, looking at an oil barrel"
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


SCRIPT_VISUAL_POLICY_APPENDIX = ""


def _compact_script_system_prompt(language: str, limits: dict, config: dict) -> str:
    """Short, production-focused script prompt.

    The previous script prompt was very large. For 100+ cuts it made the paid
    model spend too much time reconciling style rules before returning JSON.
    Keep only constraints that affect pipeline correctness and revenue safety.
    """
    lang = normalize_language_code(language)
    min_sec = limits.get("target_min_sec", 4.3)
    max_sec = limits.get("target_max_sec", 4.8)
    target_sec = limits.get("target_sec", 4.5)
    target_range = limits.get("target_range", "")
    target_low = str(target_range).split("~", 1)[0] if "~" in str(target_range) else target_range
    char_target_range = limits.get("char_target_range", "")
    max_chars = limits.get("max_chars", "")
    tts_model = config.get("tts_model", "openai-tts")
    tts_speed = config.get("tts_speed", 1.0)

    if lang == "en":
        unit = "words"
        unit_rate = limits.get("words_per_sec", "")
        unit_rate_label = "words/sec"
        narration_lang = "English"
    elif lang == "ja":
        unit = "characters"
        unit_rate = limits.get("chars_per_sec", "")
        unit_rate_label = "chars/sec"
        narration_lang = "Japanese"
    elif lang == "hi":
        unit = "words"
        unit_rate = limits.get("words_per_sec", "")
        unit_rate_label = "words/sec"
        narration_lang = "Hindi"
    else:
        unit = "characters including spaces"
        unit_rate = limits.get("chars_per_sec", "")
        unit_rate_label = "chars/sec"
        narration_lang = "Korean"
    national_pride_style = {
        "ko": "- Add a Korean-audience pride tint, about 10%: show endurance, strategic sense, craft, or cultural continuity when the facts support it. Keep it restrained and factual; no propaganda, no superiority claims, no modern nationalism.\n",
        "en": "- Add an audience-pride tint, about 10%: when the facts support it, frame invention, practical ingenuity, risk-taking, or civic scale as quietly impressive. Keep it restrained and factual; no propaganda, no superiority claims.\n",
        "ja": "- 事実に基づく範囲で、日本語視聴者向けの誇りを10%ほど入れること。粘り強さ、制度化、工夫、文化的連続性を静かに感じさせる程度にし、宣伝・優越表現・現代ナショナリズムは禁止。\n",
        "hi": "- Add an Indian-audience pride tint, about 10%: when the facts support it, let civilizational depth, political skill, intellectual tradition, or social scale feel quietly weighty. Keep it restrained and factual; no propaganda, no superiority claims.\n",
    }.get(lang, "- Add a local-audience pride tint, about 10%, only when facts support it. Keep it restrained and factual; no propaganda or superiority claims.\n")

    korean_spoken_style = ""
    if lang == "ko":
        korean_spoken_style = """
Korean narration style:
- Use natural connected 존댓말, like one person continuing a story.
- Avoid stiff report endings. Do not end most cuts with `-습니다`, `-입니다`, `-했습니다`, or `-됩니다`.
- Use those stiff endings sparingly, under about 20% of cuts, and never in 2 consecutive cuts.
- Prefer connected endings and bridges: `-했는데요`, `-인데요`, `-하다 보니`, `-였거든요`, `-였죠`, `-고요`, `그런데`, `그러다 보니`.
- Each cut should connect event -> reason, reason -> result, or reveal -> meaning. Do not write detached textbook sentences.
- When writing Korean king names, separate `왕` with a space: `문무 왕`, `광개토대 왕`, `선덕여 왕`.
- Bad: `수나라는 고구려를 공격했습니다. 고구려는 방어했습니다.`
- Good: `수나라는 엄청난 병력을 밀어 넣었는데요, 고구려는 그 숫자 싸움에 그대로 말려들지 않았죠.`
"""

    spoken_style = ""
    if lang == "en":
        spoken_style = """
English narration style:
- Prefer conversational connectors: `but`, `so`, `then`, `still`, `because`, `by then`, `that meant`.
- Use varied sentence shapes. Mix one sentence and two short connected sentences across cuts.
- Avoid stiff textbook phrasing: `lived peacefully`, `arrived in the household`, `was punished`, `finally prevailed`, `throughout history`.
- Avoid flat passive voice when a person or object can do the action.
- Each cut should contain a tiny emotional turn: curiosity, doubt, pressure, unfairness, irony, or consequence.
- Bad: `The father believed her. The sisters had no voice left.`
- Good: `Their father believed the lie, and the sisters had nowhere left to speak.`
"""
    elif lang == "hi":
        spoken_style = """
Hindi narration style:
- Write natural spoken Hindi for an Indian documentary audience, not textbook Hindi.
- Prefer flowing connectors and light conversational rhythm, while staying factual.
- Avoid stiff, overly formal phrasing and repeated sentence endings.
- Each cut should carry one emotional turn: curiosity, pressure, injustice, surprise, irony, or consequence.
- Keep the line speakable in one breath, but not like a headline.
"""

    character_timing_rule = ""
    if lang in ("en", "hi") and char_target_range and max_chars:
        character_timing_rule = (
            f"- PRIMARY HARD CAP: every narration must be {char_target_range} total characters, "
            f"including spaces and punctuation. Never exceed {max_chars} characters.\n"
            f"- Character count overrides word count. A line with valid words but more than {max_chars} characters is FAILED.\n"
            f"- After writing each narration, count the characters. If it is over {max_chars}, delete a clause, adjective, or prepositional phrase before returning JSON.\n"
            f"- Bad over-cap style: two joined clauses with 'and', 'until', 'while', or a trailing location phrase.\n"
            f"- Good timing style: one concrete action, no extra tail."
        )
    elif lang == "ja" and max_chars:
        character_timing_rule = (
            f"- PRIMARY HARD CAP: every narration must be {target_range} Japanese characters, including punctuation.\n"
            f"- Never exceed {max_chars} characters. A line over {max_chars} characters is FAILED even if it sounds natural.\n"
            f"- Use one short spoken sentence only."
        )

    if lang == "en":
        floor_rule = (
            f"- HARD FLOOR: any narration shorter than {target_low} {unit} is invalid because it creates too much silence in the 5.0-second cut.\n"
            f"- Before returning JSON, count every narration yourself. If any line is below {target_low} {unit}, add one concrete cause, object, action, or consequence from that cut.\n"
            "- The backend validates this after generation; do not rely on later audio padding to fix a short spoken line."
        )
    else:
        floor_rule = f"- Avoid narrations shorter than {target_low} {unit}."

    return f"""You are the script generator for a revenue-sensitive YouTube automation pipeline.
Return ONE valid JSON object only. No markdown, no explanation, no trailing text.

Required JSON shape:
{{
  "title": "...",
  "description": "...",
  "tags": ["...", "..."],
  "thumbnail_prompt": "English close-up image prompt for the key person/event/object, no readable text",
  "thumbnail_hook": "Two-line large thumbnail text in the video language. Do not copy the title.",
  "cuts": [
    {{
      "cut_number": 1,
      "narration": "...",
      "image_prompt": "English visual scene only, no readable text",
      "visual_year": "exact year or tight date range for the visible scene, e.g. '1592' or 'c. 1590-1591'",
      "visual_period": "specific historical era or modern period, e.g. 'Indus Valley civilization, Mature Harappan period, c. 2600-1900 BCE'",
      "visual_location": "specific place or environment, e.g. 'brick street near a drainage channel in Mohenjo-daro'",
      "visual_evidence": "one short reason why this image matches the narration and period",
      "duration_estimate": 5.0,
      "scene_type": "title",
      "shorts_candidate": false,
      "shorts_group": 0,
      "shorts_reason": "",
      "shorts_score": 0,
      "shorts_title": ""
    }}
  ]
}}

Timing target:
- ABSOLUTE TOP RULE: no cut may exceed 5.0 seconds.
- Write every narration to land as close as possible to {target_sec} seconds with the configured voice.
- Acceptable script-writing window: {min_sec}~{max_sec} seconds. Do not merely aim anywhere inside the window; aim near {target_sec}s.
- Write the spoken narration itself for {min_sec}~{max_sec}s.
- Current voice timing: model={tts_model}, speed={tts_speed}, approx {unit_rate} {unit_rate_label}.
- Each narration target: {target_range} {unit}.
{character_timing_rule}
- Timing rules override user-provided numeric length instructions. If user constraints say fewer words, shorter sentences, or another word range, ignore those numeric limits and follow this timing target.
{floor_rule}
- Do not write slogan-length lines. Each narration needs one complete spoken thought with a concrete detail.
- For Korean cuts, use two connected clauses: concrete event/object first, concrete consequence or meaning second.
- For Japanese cuts, keep one compact sentence under the hard character cap. Do not add a second explanatory clause.
- A valid cut should feel speakable for nearly the whole 5-second slot, not like a title card.
- Do not output tiny filler like "ai", "yes", "right", or generic tails just to pad length.
- Get the narration length as close as possible in this response.

Content contract:
- Narration language: {narration_lang}.
- title, description, thumbnail_hook, and all viewer-facing metadata must use the same language as Narration language. Do not use the user's input language if it differs from Narration language.
- Keep the story continuous across cuts: hook, setup, development, reversal/reveal, aftermath, ending.
- Use factual wording. Do not invent exact dates, names, or numbers unless supplied by the user.
{national_pride_style}
- Use simple everyday words only. Avoid academic terms, expert jargon, poetic wording, and stiff formal phrases. If a hard term is unavoidable, explain it with simpler words.
- No subscribe/like requests.
{spoken_style}
{korean_spoken_style}

Historical and visual continuity contract:
- image_prompt must include those fields: visual_year + visual_period + visual_location + period/place-correct objects + exact narrated action.
- If a recurring character appears, image_prompt must include stable character detail: species/person identity, body shape, face/antennae or silhouette, clothing/props if any, pose, expression, and action.
- Keep the same character design details across cuts; vary pose/action/composition, not the character identity.
- Do not use generic filler visuals such as DNA helix, glowing brain, abstract map, random temple wall, generic scholar, generic palace, generic battlefield, unless the narration explicitly discusses that object.
- Do not use generic fantasy costume, cosplay, stage costume, or famous wrong-era looks.
- If exact visual details are uncertain, use plain conservative period-plausible objects and avoid recognizable later inventions.
- Consecutive cuts should feel like the same documentary world: consistent era, region, architecture, costume, and props, while varying camera angle and composition.

Thumbnail contract:
- thumbnail_prompt must be a close-up of the most important person, case, event object, artifact, evidence, or decisive moment.
- Make thumbnail_prompt more provocative and click-driving: choose the most shocking visible moment, highest-tension facial expression, dangerous object, decisive evidence, betrayal signal, or irreversible turning-point object from the story.
- The thumbnail image should feel urgent, dramatic, and curiosity-heavy, but it must remain fact-based and must not invent gore, fake text, fake symbols, or events not in the story.
- Use one dominant close-up subject. Avoid wide explanatory scenes, collages, generic atmosphere, or distant landscapes.
- The close-up must make the viewer understand the main incident or object instantly without reading text.

Shorts metadata contract:
- Pick exactly 12 cuts and mark them as individual shorts-worthy cuts across the episode.
- These cuts do not need to be consecutive. Pick the most clickable moments from the full story.
- Use shorts_group 1 for all 12 selected cuts.
- Set shorts_candidate=true only on these 12 cuts.
- Pick the 12 cuts where the narration is most shocking or curiosity reaches its highest point: strong hook, reversal, reveal, conflict, danger, betrayal, shocking fact, concrete visual, or comment-worthy question.
- Do not pick intro/outro, generic setup, or a section that cannot be understood alone.
- shorts_reason must be a short reason such as "hook question", "shocking fact", "reversal", "danger", or "midpoint reveal".
- Add shorts_score from 1 to 10. Use 10 only for the strongest curiosity cut.
- Add shorts_title to selected cuts. It must be shocking, curiosity-heavy, and usable as the uploaded Shorts title.

Image contract:
- image_prompt must be English.
- image_prompt describes only visible scene, object, composition, or character pose.
- Never request readable text, letters, numbers, logos, watermarks, subtitles, UI labels, posters with words, screens with words, fake glyphs, fake kanji, pseudo calligraphy, crests, emblems, or decorative symbol marks.
- Any visible sign, wall hanging, banner, armor plate, ship sail, book cover, box, or label must be blank and unmarked unless the story is actually about a specific visible mark.
- Before writing cuts, internally lock the topic's exact time period, season/time-of-day when relevant, region, place type, material culture, clothing, hairstyle, headwear, jewelry/accessories, architecture, tools, weapons, armor, vehicles, vessels, furniture, rituals, everyday objects, landscape, materials, and recurring character designs.
- Every cut must include visual_year, visual_period, visual_location, and visual_evidence.
- visual_year must name the exact visible year, or the tightest honest date range if the exact year is not known.
- visual_period must be specific, not generic. For history, name the era, ruler/dynasty/culture, and date range when possible.
- visual_location must name a concrete space, not a generic background.
- visual_evidence must explain the link between narration and image in one short phrase.
- image_prompt must begin with the visible year/date range and exact space before any character or action. Required shape: "Year/period: ...; Exact place: ...; Scene: ..."
- In historical cuts, image_prompt must name visible period evidence: period-correct clothing, hairstyle or headwear, tools, weapons, armor, jewelry/accessories, furniture, buildings, vehicles, vessels, ritual objects, everyday objects, and materials when any of them are visible.
- For historically disputed subjects or disputed wording, add wording that it is disputed or controversial.
- Do not use FLAG visuals that do not match the era, space, or place.
- Use only clothing, vehicles, objects, weapons, armor, lifestyle, and buildings that match the era, space, and place.
- Do not mix eras or cultures.
- No anachronisms: modern clothes, modern hairstyles, modern jewelry, modern buildings, guns, cars, screens, neon, national flags, printed books, paper notebooks, or readable writing unless the narration explicitly takes place in that period.
- If the narration is about an abstract claim, visualize the closest concrete historical evidence or action from that cut, not a metaphor.
"""


def _strip_added_visual_prompt_rules(prompt: str) -> str:
    """Remove recent hard visual guardrails; keep image_prompt as scene description."""
    out = prompt or ""
    patterns = [
        r"\n?★★★[^\n]*(?:손/손가락|NO CLOSE-UP HANDS OR FINGERS|手・指)[\s\S]*?(?=\n\n★|\n\n════════|$)",
        r"\n?★★★[^\n]*(?:해부학|ANATOMY / LIMB|解剖)[\s\S]*?(?=\n\n★|\n\n════════|$)",
    ]
    for pattern in patterns:
        out = re.sub(pattern, "\n", out, flags=re.IGNORECASE)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip() + "\n"


def _voice_profile_from_config(config: dict | None) -> dict | None:
    if not config:
        return None
    try:
        from app.services.tts.voice_profile import get_cached_voice_profile_from_config

        return get_cached_voice_profile_from_config(config)
    except Exception:
        return None


def _fallback_scaled_voice_rate(config: dict | None, metric: str) -> float:
    """Reuse the same ElevenLabs voice profile at another speed when available."""
    if not config or config.get("tts_model") != "elevenlabs":
        return 0.0
    voice_id = str(config.get("tts_voice_id") or "").strip()
    language = normalize_language_code(config.get("language") or config.get("tts_voice_lang") or "ko")
    if not voice_id:
        return 0.0
    try:
        requested_speed = float(config.get("tts_speed", 1.0) or 1.0)
    except (TypeError, ValueError):
        requested_speed = 1.0
    try:
        from app.services.tts.voice_profile import _load_cache

        cache = _load_cache()
    except Exception:
        return 0.0
    best: dict | None = None
    for item in cache.values():
        if not isinstance(item, dict):
            continue
        if item.get("voice_id") != voice_id or normalize_language_code(item.get("language")) != language:
            continue
        value = float(item.get(metric) or 0)
        if value <= 0:
            continue
        best = item
        try:
            if abs(float(item.get("speed") or 1.0) - 1.0) < 0.001:
                break
        except (TypeError, ValueError):
            pass
    if not best:
        return 0.0
    try:
        cached_speed = float(best.get("speed") or 1.0)
        cached_value = float(best.get(metric) or 0)
    except (TypeError, ValueError):
        return 0.0
    if cached_speed <= 0 or cached_value <= 0:
        return 0.0
    return cached_value * (requested_speed / cached_speed)


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
    """Timing target used when writing narration text.

    The voice step still has its runtime guard, but script generation should
    aim close to one spoken length so audio repair is the exception.
    """
    cfg = config or {}
    try:
        target = float(cfg.get("script_tts_target_sec") or 4.4)
    except (TypeError, ValueError):
        target = 4.4
    try:
        tolerance = float(cfg.get("script_tts_tolerance_sec") or 0.4)
    except (TypeError, ValueError):
        tolerance = 0.4

    target = max(4.0, min(4.7, target))
    tolerance = max(0.05, min(0.5, tolerance))
    min_sec = max(4.0, target - tolerance)
    max_sec = min(4.8, target + tolerance)
    if min_sec > max_sec:
        min_sec = max_sec = target
    return min_sec, max_sec, target


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
    """Return the appropriate system prompt based on language.

    config 가 주어지면 TTS 모델·속도에 맞춰 글자/단어 한도를 동적으로 포맷한다.
    config 가 없으면 기본값(speed=1.0, openai-tts)으로 포맷.
    """
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
        """JSON 중괄호와 충돌하지 않도록 단순 문자열 치환."""
        result = template
        for key, val in replacements.items():
            result = result.replace(f"{{{key}}}", str(val))
        return result

    def _limits_for_compact(lang: str) -> dict:
        if lang in ("en", "hi"):
            raw_wps = _profiled_words_per_sec(config, 2.5 * effective_speed)
            raw_cps = _profiled_chars_per_sec(config, 12.0 * effective_speed)
            wps = round(raw_wps, 3)
            cps = round(raw_cps, 3)
            extra_words = 0
            extra_chars = max(0, int(round(extra_words * (cps / max(wps, 0.1)))))
            target_words = max(1, int(round(tts_target_sec * wps)))
            max_words = max(1, int(math.floor(tts_max_sec * wps)))
            min_words = max(1, int(math.ceil(tts_min_sec * wps)) - (0 if lang == "en" else 1))
            if min_words > max_words:
                min_words = max_words = target_words
            min_words += extra_words
            max_words += extra_words
            target_words += extra_words
            target_chars = max(1, int(round(tts_target_sec * cps)))
            max_chars = max(1, int(math.floor(tts_max_sec * cps)))
            min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - 1)
            target_chars += extra_chars
            max_chars += extra_chars
            min_chars += extra_chars
            return {
                "target_range": f"{min_words}~{max_words}",
                "char_target_range": f"{min_chars}~{max_chars}",
                "target_chars": target_chars,
                "max_chars": max_chars,
                "words_per_sec": wps,
                "chars_per_sec": cps,
                "target_min_sec": tts_min_sec,
                "target_max_sec": tts_max_sec,
                "target_sec": tts_target_sec,
            }
        fallback = 7.8 * effective_speed if lang == "ja" else 8.8 * effective_speed
        cps = round(_profiled_chars_per_sec(config, fallback), 1)
        target_chars = max(1, int(round(tts_target_sec * cps)))
        if lang == "ko":
            max_chars = max(1, int(math.ceil(tts_max_sec * cps)))
            min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - 1)
        else:
            max_chars = max(1, int(math.floor(tts_max_sec * cps)))
            min_chars = max(1, int(math.ceil(tts_min_sec * cps)))
        if min_chars > max_chars:
            min_chars = max_chars = target_chars
        result = {
            "target_range": f"{min_chars}~{max_chars}",
            "chars_per_sec": cps,
            "max_chars": max_chars,
            "target_min_sec": tts_min_sec,
            "target_max_sec": tts_max_sec,
            "target_sec": tts_target_sec,
        }
        if lang == "ko":
            result["validation_range"] = f"{max(1, min_chars - 1)}~{max_chars}"
        return result

    if config.get("script_prompt_mode", "compact") == "compact":
        return _compact_script_system_prompt(language, _limits_for_compact(language), config)

    if language in ("en", "hi"):
        wps = round(_profiled_words_per_sec(config, 2.5 * effective_speed), 1)
        target_words = max(1, int(round(tts_target_sec * wps)))
        max_words = max(1, int(math.floor(tts_max_sec * wps)))
        min_words = max(1, int(math.ceil(tts_min_sec * wps)))
        if min_words > max_words:
            min_words = max_words = target_words
        target_words = max(min_words, min(max_words, target_words))
        low = min_words
        prompt = _sub(SCRIPT_SYSTEM_PROMPT_EN, {
            "tts_min_sec": tts_min_sec, "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "words_per_sec": wps, "max_words": max_words,
            "target_words": target_words, "min_words": min_words,
            "target_range": f"{low}~{max_words}",
        })
        if language == "hi":
            prompt = prompt.replace(
                "You are a YouTube longform video script writer.",
                "You are a YouTube longform video script writer for a Hindi-speaking Indian audience. Write all title, description, tags, and narration in natural Hindi. Keep image prompts in English.",
                1,
            )
        return _strip_added_visual_prompt_rules(prompt)
    if language == "ja":
        cps = round(_profiled_chars_per_sec(config, 7.8 * effective_speed), 1)
        target_chars = max(1, int(round(tts_target_sec * cps)))
        max_chars = max(1, int(math.floor(tts_max_sec * cps)))
        min_chars = max(1, int(math.ceil(tts_min_sec * cps)))
        if min_chars > max_chars:
            min_chars = max_chars = target_chars
        target_chars = max(min_chars, min(max_chars, target_chars))
        low = min_chars
        return _strip_added_visual_prompt_rules(_sub(SCRIPT_SYSTEM_PROMPT_JA, {
            "tts_min_sec": tts_min_sec, "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "chars_per_sec": cps, "max_chars": max_chars,
            "target_chars": target_chars, "min_chars": min_chars,
            "target_range": f"{low}~{max_chars}",
        }))
    # 한국어
    # 실측 보정: ElevenLabs/OpenAI 한국어 TTS는 짧은 문장을 생각보다 빠르게 읽는다.
    # 27~28자는 3초대로 떨어지므로 5초 컷에는 38~42자 안팎이 더 안전하다.
    cps = round(_profiled_chars_per_sec(config, 8.8 * effective_speed), 1)
    target_chars = max(1, int(round(tts_target_sec * cps)))
    max_chars = max(1, int(math.floor(tts_max_sec * cps)))
    min_chars = max(1, int(math.ceil(tts_min_sec * cps)) - 1)
    if min_chars > max_chars:
        min_chars = max_chars = target_chars
    target_chars = max(min_chars, min(max_chars, target_chars))
    low = min_chars
    return _strip_added_visual_prompt_rules(_sub(SCRIPT_SYSTEM_PROMPT_KO, {
        "tts_min_sec": tts_min_sec, "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
        "chars_per_sec": cps, "max_chars": max_chars,
        "target_chars": target_chars, "min_chars": min_chars,
        "target_range": f"{low}~{max_chars}",
    }))


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

    @staticmethod
    def strengthen_visual_context(script: dict, config: dict | None = None) -> dict:
        """Copy cut-level historical metadata into image_prompt for generators."""
        if not isinstance(script, dict):
            return script
        if BaseLLMService._simple_cartoon_visuals(config or {}):
            return script
        cuts = script.get("cuts")
        if not isinstance(cuts, list):
            return script
        for cut in cuts:
            if not isinstance(cut, dict):
                continue
            image_prompt = str(cut.get("image_prompt") or "").strip()
            year = str(cut.get("visual_year") or "").strip()
            period = str(cut.get("visual_period") or "").strip()
            location = str(cut.get("visual_location") or "").strip()
            evidence = str(cut.get("visual_evidence") or "").strip()
            prefix_parts: list[str] = []
            year_period = "; ".join(part for part in (year, period) if part)
            if year_period:
                prefix_parts.append(f"Year/period: {year_period}")
            if period:
                prefix_parts.append(f"Historically accurate period details: {period}")
            if location:
                prefix_parts.append(f"Exact place: {location}")
            if evidence:
                prefix_parts.append(f"Scene evidence: {evidence}")
            if not prefix_parts:
                continue
            prefix = "; ".join(prefix_parts)
            if image_prompt:
                if prefix.lower() not in image_prompt.lower():
                    cut["image_prompt"] = f"{prefix}; Scene: {image_prompt}"
            else:
                cut["image_prompt"] = prefix
        return script

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
                from app.services.tts.pronunciation_normalizer import prepare_spoken_narration_for_tts
                spoken = prepare_spoken_narration_for_tts(narration, lang) or narration
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
        print(
            f"[script] narration timing warning only ({target}): {preview}. "
            "Script is kept; voice stage will use existing audio or local FFmpeg duration fit."
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
                f"ONE dominant hero subject — the most important person, incident, "
                f"event object, artifact, evidence, or decisive moment from the story. "
                f"Render it as an extreme close-up, either a human face with an "
                f"exaggerated emotion or one single story-critical object with dramatic "
                f"scale. Fills 35-55% of the frame, offset to the left or right third, "
                f"leaving clean negative space on the opposite side for later text "
                f"overlay. Razor sharp focus on the eyes or the key edge of the object. "
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
            f"otherwise the key person, incident, event object, artifact, evidence, or "
            f"decisive moment). It must be a close-up. No crowds, no group shots, no "
            f"wide scene, no distant subject, no split attention.\n"
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
        return get_system_prompt(language, config)

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
            # 떨어졌다. 5초 컷용으로 38~42자 안팎을 목표로 잡는다.
            chars_per_sec = _profiled_chars_per_sec(config, 8.8 * speed)
            target_chars = max(1, int(round(target_secs * chars_per_sec)))
            max_chars = max(1, int(math.ceil(max_secs * chars_per_sec)))
            low = max(1, int(math.ceil(min_secs * chars_per_sec)) - 1)
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
            # 쉬웠다. 5초 컷용으로 33~37자 안팎을 목표로 잡는다.
            chars_per_sec = _profiled_chars_per_sec(config, 7.8 * speed)
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
            words_per_sec = _profiled_words_per_sec(config, 2.5 * speed)
            chars_per_sec = _profiled_chars_per_sec(config, 12.0 * speed)
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
        duration = config.get("target_duration", 600)
        style = config.get("style", "news_explainer")
        language = normalize_language_code(config.get("language", "ko"))
        # v1.1.73: 사용자 금칙/필수 제약 블록. 대본 프롬프트 최상단에 최우선 순위로
        # 주입한다. topic 한 줄에 제약이 섞여 있으면 모델이 일반 설명으로 해석하고
        # 무시할 위험이 있어, 언어별 강조 헤더와 함께 분리.
        # v1.1.75: content_forbidden (금지) / content_required (필수) 로 필드 분리.
        # 기존 프로젝트의 content_constraints 는 두 신규 필드가 비어 있을 때만
        # legacy 블록으로 그대로 주입 (하위 호환).
        forbidden_raw = (config.get("content_forbidden") or "").strip()
        required_raw = (config.get("content_required") or "").strip()
        legacy_raw = (config.get("content_constraints") or "").strip()
        use_legacy = bool(legacy_raw) and not forbidden_raw and not required_raw
        # 5-second unit rule (v1.1.26): cuts = ceil(duration / 5)
        # Uses ceil so 601s → 121 cuts (aligned with frontend expectedCuts)
        try:
            cut_count = int(config.get("target_cuts") or 0)
        except (TypeError, ValueError):
            cut_count = 0
        if cut_count <= 0:
            try:
                duration_int = max(5, int(duration))
            except (TypeError, ValueError):
                duration_int = 600
            cut_count = max(1, math.ceil(duration_int / 5))
        duration_int = cut_count * 5
        narration_limits = self._calc_narration_limits(config)
        target_range = str(narration_limits.get("target_range") or "")
        target_sec = narration_limits.get("target_sec", 4.5)
        target_min_sec = narration_limits.get("target_min_sec", 4.0)
        target_max_sec = narration_limits.get("target_max_sec", 4.8)
        try:
            target_low = int(target_range.split("~", 1)[0])
        except Exception:
            target_low = 1
        timing_unit = "words" if language in ("en", "hi") else "characters including spaces"
        char_timing_line = ""
        char_target_range = narration_limits.get("char_target_range")
        max_chars = narration_limits.get("max_chars")
        if language in ("en", "hi") and char_target_range and max_chars:
            char_timing_line = (
                f"- Also keep every narration within {char_target_range} total characters; "
                f"never exceed {max_chars} total characters. This character cap wins over word count.\n"
            )
        timing_block_en = (
            f"★★★ NARRATION LENGTH TARGET ★★★\n"
            f"- ABSOLUTE TOP RULE: no cut may exceed 5.0 seconds.\n"
            f"- Each narration must aim near {target_sec}s of speech for the configured voice.\n"
            f"- Use {target_range} {timing_unit}; this is a tight script-writing range, not a loose suggestion.\n"
            f"{char_timing_line}"
            f"- This timing block overrides any user-provided word-count or short-sentence instruction.\n"
            f"- HARD FLOOR: anything below {target_low} {timing_unit} is invalid and creates too much silence.\n"
            f"- Count every narration before output; if it is short, add one concrete cause, object, action, or consequence.\n"
            f"- Do not write short slogan lines. Write one full spoken thought per cut.\n\n"
        )
        timing_block_ja = (
            f"★★★ ナレーション長の目標 ★★★\n"
            f"- 最上位絶対ルール: 1カットは5秒を超えてはいけません。\n"
            f"- 各 narration は設定音声に合わせて {target_range} 文字（空白含む）にすること。\n"
            f"- 絶対上限: {max_chars}文字。{max_chars}文字を1文字でも超えた narration は失敗。\n"
            f"- 目標秒数は {target_sec} 秒、許容範囲は {target_min_sec}~{target_max_sec} 秒。\n"
            f"- {target_low} 文字未満は無効。5秒カット内の無音が長くなりすぎる。\n"
            f"- 一つの短い話し言葉だけを書くこと。\n\n"
        )
        timing_block_ko = (
            f"★★★ 나레이션 길이 목표 ★★★\n"
            f"- 최상위 절대 규칙: 절대 컷당 5초를 넘지 않습니다.\n"
            f"- 각 narration 은 설정된 음성 기준 {target_range}자(공백 포함)여야 합니다.\n"
            f"- 하한선 {target_low}자 미만은 실패입니다. 5초 컷 안에서 무음이 너무 길어집니다.\n"
            f"- 출력 직전에 모든 narration 글자 수를 직접 세고, 짧으면 그 컷의 구체 원인·대상·행동·결과 중 하나를 더 넣으세요.\n"
            f"- 제목처럼 짧게 쓰지 마세요. 5초 대부분을 채우는 한 호흡 문장이어야 합니다.\n"
            f"- 각 narration 은 반드시 두 부분으로 구성하세요: 구체 사건/대상 + 구체 결과/의미.\n"
            f"- 왕의 이름을 명명할 때 `왕`은 띄어쓰기 후에 생성합니다. 예: 문무 왕, 광개토대 왕, 선덕여 왕.\n"
            f"- 부족한 글자 수는 해당 컷의 구체 원인, 사건, 대상, 결과를 한 조각 더 넣어 해결하세요.\n\n"
        )
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
                    f"- There is no global cap on how often the character may appear.\n"
                    f"- In those cuts, describe the character's SHAPE/POSE/ACTION in image_prompt.\n"
                    f"- Do NOT mention palette, color, or art style — those come from the attached reference images.\n"
                )
            elif language == "ja":
                style_instruction = (
                    f"\n\n★ キャラクター参考（キャラクター登場カット用）:\n"
                    f"{character_description}\n\n"
                    f"ルール:\n"
                    f"- キャラクター登場回数に全体割合の上限は設けない。\n"
                    f"- 登場カットでは image_prompt にキャラクターの形・ポーズ・動作を記述する。\n"
                    f"- 色・パレット・画風は書かないこと（添付リファレンス画像から取得される）。\n"
                )
            else:
                style_instruction = (
                    f"\n\n★ 캐릭터 참고 정보 (캐릭터 등장 컷용):\n"
                    f"{character_description}\n\n"
                    f"규칙:\n"
                    f"- 캐릭터 등장 비율에 대한 전체 제한은 두지 않습니다.\n"
                    f"- 등장 컷의 image_prompt 에는 캐릭터의 형상·포즈·동작만 기술합니다.\n"
                    f"- 색상·팔레트·그림체 단어는 쓰지 마세요. 스타일은 첨부된 레퍼런스 이미지에서 가져갑니다.\n"
                )
            style_instruction = f"\n\nCharacter reference context:\n{character_description}\n"

        visual_contract = """

*** IMAGE PROMPT RULES - REQUIRED FOR EVERY CUT ***
- Add these keys to every cut: visual_year, visual_period, visual_location, visual_evidence.
- visual_year must name the exact visible year, or the tightest honest date range if exact year is not known.
- visual_period must name the exact era/century/dynasty/culture when possible.
- visual_location must name the concrete space shown: exact country/region + city/province/site when known + place type + interior/exterior.
- visual_evidence must state why this scene belongs to this cut's narration.
- image_prompt must visually match the narration, visual_period, and visual_location.
- image_prompt must begin with the visible year/date range and exact space. Required shape: "Year/period: ...; Exact place: ...; Scene: ..."
- image_prompt must include time/space context and any visible character's stable details: identity, clothing or body design, pose, expression, props, and action.
- Use period-correct material culture: clothing, hairstyle, headwear, jewelry/accessories, architecture, tools, weapons, armor, vehicles, vessels, furniture, ritual objects, everyday objects, landscape, and materials.
- For historically disputed subjects or disputed wording, add wording that it is disputed or controversial.
- Do not use FLAG visuals that do not match the era, space, or place.
- Use only clothing, vehicles, objects, weapons, armor, lifestyle, and buildings that match the era, space, and place.
- Visible costume, hair, armor, tools, and props must prove the exact period; do not use generic fantasy costume, cosplay, stage costume, or famous wrong-era looks.
- If exact visual details are uncertain, use plain conservative period-plausible objects and avoid recognizable later inventions.
- No generic metaphor images, no random palaces/temples/scholars, no abstract DNA/brain/glowing symbols unless the narration explicitly says so.
- No anachronisms: modern clothes, modern hairstyles, modern jewelry, modern buildings, cars, guns, screens, neon, printed books, national flags, or readable text unless the story is actually modern.
- Keep consecutive cuts in the same documentary world; vary camera angle, not the historical setting.
"""
        if self._simple_cartoon_visuals(config):
            visual_contract = """

*** SIMPLE CARTOON VISUAL CONTRACT - REQUIRED FOR EVERY CUT ***
- Add image_prompt for every cut, but keep it short and concrete.
- Add these keys to every cut: visual_period, visual_location, visual_evidence.
- visual_period must name the exact story time context, such as "classic fable world, warm summer day", "classic fable world, cold winter evening", or "modern office, late evening".
- visual_location must name the concrete place shown, such as "meadow beside an anthill", "underground food storage room", "open-plan office desk row", or "small meeting room".
- visual_evidence must state why this scene belongs to this narration.
- Use a clean office-fable visual system, but keep source-story cuts in the original fable world and analogy cuts in the modern office world.
- image_prompt must describe the unique scene only: subject, action, key props, exact setting, framing, and emotional beat.
- image_prompt must include time/space context and recurring character details: species identity, soft mascot body shape, antennae or silhouette, clothing/props if any, pose, expression, and action.
- Keep ant and grasshopper character design details stable across cuts; do not let them become robots, aliens, realistic insects, generic humans, or unrelated creatures.
- Do NOT repeat global style words in image_prompt: no "2D cartoon scene", "flat colors", "thick outlines", "pale blue background", or "minimal scene".
- Backgrounds must be specific but simple: name the exact place/object visible in this cut, not a repeated generic backdrop.
- Do not use historical eras, old period clothing, wooden antique rooms, museums, palaces, temples, or documentary realism.
- Do not use warm yellow, golden hour, sepia, dusk, dawn, candlelight, cinematic lighting, or painterly texture.
- Keep consecutive cuts visually consistent through the world and character identity, but vary pose, prop, setting detail, and composition.
"""

        # Script generation does not request or store video motion prompts.

        # v1.1.73: 언어별 "사용자 최우선 제약" 블록.
        # - 입력값을 bullet 친화적으로 약하게 정규화
        #   (사용자가 " / " 로 이어 쓴 경우 줄바꿈으로 쪼개 가독성↑).
        # - 모두 비어 있으면 블록 전체 생략 — 기존 프롬프트와 하위 호환.
        # v1.1.75: 금지 / 필수 를 별도 서브블록으로 렌더. legacy(content_constraints)
        # 는 두 필드가 모두 비었을 때만 단일 "legacy rules" 블록으로 주입.
        def _normalize_constraints(raw: str) -> str:
            s = raw.replace("\r\n", "\n")
            # 사용자들이 자주 쓰는 구분자(" / ", " · ") 를 줄바꿈으로.
            for sep in (" / ", " · "):
                s = s.replace(sep, "\n")
            lines = [ln.strip(" -•·").strip() for ln in s.split("\n")]
            lines = [ln for ln in lines if ln]
            lines = [ln for ln in lines if not _is_conflicting_timing_constraint(ln)]
            return "\n".join(f"- {ln}" for ln in lines)

        def _is_conflicting_timing_constraint(line: str) -> bool:
            value = (line or "").strip().lower()
            if not value:
                return False
            has_number = bool(re.search(r"\d", value))
            timing_words = (
                "word", "words", "sec", "second", "seconds", "duration",
                "chars", "characters", "글자", "단어", "초", "秒", "文字",
            )
            if has_number and any(token in value for token in timing_words):
                return True
            if "per cut" in value and any(
                token in value for token in ("aim", "exceed", "more than", "less than")
            ):
                return True
            return False

        # 언어별 서브블록 라벨
        _labels = {
            "en": {
                "header": "★★★ USER ABSOLUTE RULES — HIGHEST PRIORITY ★★★",
                "intro": (
                    "These rules override every other instruction. Violating any of "
                    "them means the script is a failure."
                ),
                "forbidden": "[FORBIDDEN — Never include any of the following]",
                "required": "[REQUIRED — Must follow all of the following]",
                "legacy": "[USER RULES]",
            },
            "ja": {
                "header": "★★★ ユーザー絶対ルール — 最優先 ★★★",
                "intro": (
                    "以下のルールは他のあらゆる指示より優先されます。"
                    "1 つでも破った場合、その台本は失敗扱いです。"
                ),
                "forbidden": "[禁止事項 — 以下を絶対に含めないこと]",
                "required": "[必須事項 — 以下をすべて守ること]",
                "legacy": "[ユーザールール]",
            },
            "ko": {
                "header": "★★★ 사용자 절대 제약 — 최우선 순위 ★★★",
                "intro": (
                    "아래 규칙은 다른 모든 지시보다 우선합니다. "
                    "하나라도 어기면 이 대본은 실패입니다."
                ),
                "forbidden": "[금지 사항 — 아래 내용을 절대 포함하지 말 것]",
                "required": "[필수 사항 — 아래 내용을 반드시 지킬 것]",
                "legacy": "[사용자 규칙]",
            },
        }

        def _build_constraints_block(lang: str) -> str:
            lbl = _labels.get(lang, _labels["ko"])
            parts: list[str] = []
            if use_legacy:
                parts.append(lbl["legacy"])
                parts.append(_normalize_constraints(legacy_raw))
            else:
                # v1.1.75: 필수 먼저, 금칙 나중. UI 표시 순서와 일치.
                if required_raw:
                    parts.append(lbl["required"])
                    parts.append(_normalize_constraints(required_raw))
                if forbidden_raw:
                    if parts:
                        parts.append("")  # 서브블록 사이 빈 줄
                    parts.append(lbl["forbidden"])
                    parts.append(_normalize_constraints(forbidden_raw))
            if not parts:
                return ""
            body = "\n".join(parts)
            return f"{lbl['header']}\n{lbl['intro']}\n{body}\n\n"

        constraints_block_en = _build_constraints_block("en")
        constraints_block_ja = _build_constraints_block("ja")
        constraints_block_ko = _build_constraints_block("ko")

        # v1.2.9: 에피소드 상세 (주제 팝업에서 입력) — 오프닝/엔딩 대사,
        # 핵심 내용을 스크립트에 그대로 반영하도록 강제 지시 블록.
        # v1.2.10: episode_number / next_episode_preview 추가.
        episode_openings_raw = config.get("episode_openings")
        episode_endings_raw = config.get("episode_endings")
        core_content_raw = (config.get("episode_core_content") or "").strip()

        def _clean_lines(xs):
            if not isinstance(xs, list):
                return []
            return [str(x or "").strip() for x in xs if str(x or "").strip()]

        ep_openings = _clean_lines(episode_openings_raw)
        ep_endings = _clean_lines(episode_endings_raw)

        # v1.2.10: 시리즈 연속성 값.
        ep_num_cfg = config.get("episode_number")
        try:
            ep_num_val = int(ep_num_cfg) if ep_num_cfg is not None else None
            if ep_num_val is not None and ep_num_val <= 0:
                ep_num_val = None
        except (TypeError, ValueError):
            ep_num_val = None
        next_ep_preview = (config.get("next_episode_preview") or "").strip()

        def _build_episode_block(lang: str) -> str:
            if not (ep_openings or ep_endings or core_content_raw
                    or ep_num_val is not None or next_ep_preview):
                return ""
            if lang == "en":
                header = "★★★ EPISODE-SPECIFIC CONTENT — MUST BE REFLECTED ★★★"
                intro = (
                    "The following lines and core content were chosen by the user "
                    "for THIS episode. They override generic style and must appear "
                    "verbatim (or near-verbatim) at the marked positions."
                )
                ep_num_label = "[EPISODE NUMBER - mention this episode number naturally in the opening]"
                core_label = "[EPISODE CORE CONTENT - drive the narrative around this]"
                openings_label = "[OPENING LINES - use as the FIRST cuts, in order]"
                endings_label = "[ENDING LINES - use as the LAST cuts, in order]"
                next_label = (
                    "[NEXT EPISODE PREVIEW - weave this teaser into the LAST 1-2 cuts "
                    "so viewers anticipate the next episode. Do NOT reveal specifics "
                    "beyond what is written here.]"
                )
            elif lang == "ja":
                header = "★★★ エピソード固有コンテンツ — 必ず反映 ★★★"
                intro = (
                    "以下の台詞と核心内容は今回のエピソード専用にユーザーが指定したものです。"
                    "汎用スタイルより優先し、指定の位置でそのまま使うこと。"
                )
                ep_num_label = "[エピソード番号 - オープニングで自然に言及する]"
                core_label = "[エピソード核心内容 - これを軸にストーリーを構成]"
                openings_label = "[オープニング台詞 - 順番通り、最初のカットで使用]"
                endings_label = "[エンディング台詞 - 順番通り、最後のカットで使用]"
                next_label = (
                    "[次回予告 - 最後の1~2カットに予告として自然に織り込むこと。"
                    "ここに書かれた以上の具体情報は漏らさない。]"
                )
            else:
                header = "★★★ 이번 에피소드 전용 내용 — 반드시 반영 ★★★"
                intro = (
                    "아래 대사와 핵심 내용은 이번 에피소드를 위해 사용자가 직접 지정한 것입니다. "
                    "일반 스타일보다 우선이며, 지정된 위치에 원문 그대로(또는 거의 그대로) 등장해야 합니다."
                )
                ep_num_label = "[에피소드 번호 - 오프닝에서 자연스럽게 언급]"
                core_label = "[이번 에피소드 핵심 내용 - 이 내용을 축으로 스토리 전개]"
                openings_label = "[오프닝 대사 - 아래 순서대로 대본의 첫 컷부터 차례로 사용]"
                endings_label = "[엔딩 대사 - 아래 순서대로 대본의 마지막 컷에 차례로 사용]"
                next_label = (
                    "[다음 에피소드 예고 - 대본 마지막 1~2 컷에 '다음 편 예고'로 "
                    "자연스럽게 녹여 시청자가 다음 편을 기대하게 만들 것. "
                    "여기 적힌 이상의 구체 정보는 누설하지 말 것.]"
                )

            parts: list[str] = []
            if ep_num_val is not None:
                parts.append(ep_num_label)
                parts.append(f"Episode {ep_num_val}")
            if core_content_raw:
                if parts:
                    parts.append("")
                parts.append(core_label)
                parts.append(core_content_raw)
            if ep_openings:
                if parts:
                    parts.append("")
                parts.append(openings_label)
                for i, line in enumerate(ep_openings, 1):
                    parts.append(f"{i}. {line}")
            if ep_endings:
                if parts:
                    parts.append("")
                parts.append(endings_label)
                for i, line in enumerate(ep_endings, 1):
                    parts.append(f"{i}. {line}")
            if next_ep_preview:
                if parts:
                    parts.append("")
                parts.append(next_label)
                parts.append(next_ep_preview)
            body = "\n".join(parts)
            return f"{header}\n{intro}\n{body}\n\n"

        episode_block_en = _build_episode_block("en")
        episode_block_ja = _build_episode_block("ja")
        episode_block_ko = _build_episode_block("ko")

        if language == "en":
            return (
                f"{constraints_block_en}"
                f"{episode_block_en}"
                f"{timing_block_en}"
                f"Topic: {topic}\n"
                f"Target duration: {duration_int} seconds\n"
                f"\n"
                f"\u2605\u2605\u2605 HARD CONSTRAINT \u2014 5-SECOND UNIT RULE (ABSOLUTE) \u2605\u2605\u2605\n"
                f"- ABSOLUTE TOP RULE: no cut may exceed 5.0 seconds.\n"
                f"- You MUST output EXACTLY {cut_count} cuts. Not {cut_count - 1}, not {cut_count + 1}. Exactly {cut_count}.\n"
                f"- Set duration_estimate = 5.0 for every cut.\n"
                f"- cut_number must run from 1 to {cut_count} with no gaps.\n"
                f"- Total runtime = {cut_count} \u00d7 5 = {cut_count * 5} seconds.\n"
                f"- If you output fewer or more than {cut_count} cuts, the pipeline will FAIL.\n"
                f"\n"
                f"Style: {style}\n"
                f"Language: English"
                f"{visual_contract}"
                f"{style_instruction}"
            )
        if language == "hi":
            return (
                f"{constraints_block_en}"
                f"{episode_block_en}"
                f"{timing_block_en}"
                f"Topic: {topic}\n"
                f"Target duration: {duration_int} seconds\n"
                f"\n"
                f"*** HARD CONSTRAINT - 5-SECOND UNIT RULE (ABSOLUTE) ***\n"
                f"- ABSOLUTE TOP RULE: no cut may exceed 5.0 seconds.\n"
                f"- You MUST output EXACTLY {cut_count} cuts. Not {cut_count - 1}, not {cut_count + 1}. Exactly {cut_count}.\n"
                f"- Set duration_estimate = 5.0 for every cut.\n"
                f"- cut_number must run from 1 to {cut_count} with no gaps.\n"
                f"- Total runtime = {cut_count} x 5 = {cut_count * 5} seconds.\n"
                f"- If you output fewer or more than {cut_count} cuts, the pipeline will FAIL.\n"
                f"\n"
                f"Style: {style}\n"
                f"Language: Hindi\n"
                f"Write all title, description, tags, and narration in natural Hindi for an Indian audience.\n"
                f"Keep image_prompt and thumbnail_prompt in English only."
                f"{visual_contract}"
                f"{style_instruction}"
            )
        if language == "ja":
            return (
                f"{constraints_block_ja}"
                f"{episode_block_ja}"
                f"{timing_block_ja}"
                f"\u30c8\u30d4\u30c3\u30af: {topic}\n"
                f"\u76ee\u6a19\u6642\u9593: {duration_int}\u79d2\n"
                f"\n"
                f"\u2605\u2605\u2605 \u7d76\u5bfe\u5236\u7d04 \u2014 5\u79d2\u5358\u4f4d\u30eb\u30fc\u30eb\uff08\u5fc5\u305a\u5b88\u308b\u3053\u3068\uff09 \u2605\u2605\u2605\n"
                f"- \u6700\u4e0a\u4f4d\u7d76\u5bfe\u30eb\u30fc\u30eb: 1\u30ab\u30c3\u30c8\u306f5.0\u79d2\u3092\u8d85\u3048\u3066\u306f\u3044\u3051\u307e\u305b\u3093\u3002\n"
                f"- \u5fc5\u305a\u6b63\u78ba\u306b {cut_count} \u30ab\u30c3\u30c8\u3092\u51fa\u529b\u3059\u308b\u3053\u3068\u3002{cut_count - 1}\u3067\u3082{cut_count + 1}\u3067\u3082\u306a\u304f\u3001{cut_count} \u3061\u3087\u3046\u3069\u3002\n"
                f"- \u5168\u30ab\u30c3\u30c8\u306e duration_estimate \u306f 5.0 \u306b\u3059\u308b\u3053\u3068\u3002\n"
                f"- cut_number \u306f 1 \u304b\u3089 {cut_count} \u307e\u3067\u6b20\u756a\u306a\u304f\u9023\u756a\u3002\n"
                f"- \u7dcf\u518d\u751f\u6642\u9593 = {cut_count} \u00d7 5 = {cut_count * 5} \u79d2\u3002\n"
                f"- {cut_count} \u30ab\u30c3\u30c8\u4ee5\u5916\u3092\u51fa\u529b\u3059\u308b\u3068\u30d1\u30a4\u30d7\u30e9\u30a4\u30f3\u304c\u5931\u6557\u3057\u307e\u3059\u3002\n"
                f"\n"
                f"\u30b9\u30bf\u30a4\u30eb: {style}\n"
                f"\u8a00\u8a9e: \u65e5\u672c\u8a9e"
                f"{visual_contract}"
                f"{style_instruction}"
            )
        return (
            f"{constraints_block_ko}"
            f"{episode_block_ko}"
            f"{timing_block_ko}"
            f"\uc8fc\uc81c: {topic}\n"
            f"\ubaa9\ud45c \uae38\uc774: {duration_int}\ucd08\n"
            f"\n"
            f"\u2605\u2605\u2605 \uc808\ub300 \uc81c\uc57d \u2014 5\ucd08 \ub2e8\uc704 \uaddc\uce59 (\ubc18\ub4dc\uc2dc \uc9c0\ud0ac \uac83) \u2605\u2605\u2605\n"
            f"- \ucd5c\uc0c1\uc704 \uc808\ub300 \uaddc\uce59: \uc808\ub300 \ucef7\ub2f9 5\ucd08\ub97c \ub118\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.\n"
            f"- \ubc18\ub4dc\uc2dc \uc815\ud655\ud788 {cut_count}\uac1c\uc758 \ucef7\uc744 \ucd9c\ub825\ud558\uc138\uc694. {cut_count - 1}\uac1c\ub3c4 {cut_count + 1}\uac1c\ub3c4 \uc544\ub2cc, \uc815\ud655\ud788 {cut_count}\uac1c.\n"
            f"- \ubaa8\ub4e0 \ucef7\uc758 duration_estimate \ub294 5.0\uc73c\ub85c \uc124\uc815\ud569\ub2c8\ub2e4.\n"
            f"- cut_number\ub294 1\ubd80\ud130 {cut_count}\uae4c\uc9c0 \ube60\uc9d0\uc5c6\uc774 \uc5f0\uc18d\ub418\uc5b4\uc57c \ud569\ub2c8\ub2e4.\n"
            f"- \ucd1d \uc7ac\uc0dd \uc2dc\uac04 = {cut_count} \u00d7 5 = {cut_count * 5}\ucd08.\n"
            f"- {cut_count}\uac1c\uac00 \uc544\ub2cc \ucef7 \uc218\ub97c \ucd9c\ub825\ud558\uba74 \ud30c\uc774\ud504\ub77c\uc778\uc774 \uc2e4\ud328\ud569\ub2c8\ub2e4.\n"
            f"\n"
            f"\uc2a4\ud0c0\uc77c: {style}\n"
            f"\uc5b8\uc5b4: \ud55c\uad6d\uc5b4"
            f"{visual_contract}"
            f"{style_instruction}"
        )
