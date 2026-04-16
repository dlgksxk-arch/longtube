"""Base LLM service interface"""
import math
from abc import ABC, abstractmethod
from typing import Any, Optional


SCRIPT_SYSTEM_PROMPT_KO = """당신은 유튜브 롱폼 영상 대본 작가입니다.
주어진 주제로 시청자를 끌어들이는 대본을 작성하세요.

반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요:
{
  "title": "영상 제목 (한국어, 호기심 유발)",
  "description": "유튜브 영상 설명 (SEO 최적화, 한국어)",
  "tags": ["태그1", "태그2", "태그3"],
  "thumbnail_prompt": "썸네일용 이미지 생성 프롬프트 (영어 필수). 규칙: 1) 반드시 영상 주제/내용의 핵심 장면을 묘사할 것 — 주제와 무관한 자극적 이미지 금지. 2) 시청자가 '이게 뭐지?' 하고 궁금해할 한 장면. 3) 인물의 감정 표현(놀람/흥분/경외)을 포함하면 클릭률 상승. 4) 구체적 사물/배경/색감을 묘사. 5) 텍스트/글자/숫자/워터마크 절대 금지. 6) 16:9 비율, 시네마틱 조명, 고화질.",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "나레이션 텍스트 (한국어)",
      "image_prompt": "이미지 생성 프롬프트 (영어, 구체적 시각 묘사)",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

핵심 규칙 - 타이밍 (이 규칙이 1순위 — 어기면 영상이 망가진다!!):
- 각 영상 클립은 정확히 5.0초. 한 치도 더 길 수 없다.
- 각 컷의 나레이션은 반드시 {tts_max_sec}초 안에 읽힐 분량이어야 한다.
- 현재 TTS 모델: {tts_model}, 속도: {tts_speed}
- 이 설정에서 한국어 TTS는 초당 약 {chars_per_sec}글자 속도로 읽는다.
- 따라서: 최대 {max_chars}자 (공백 포함). {target_range}자를 목표로 쓸 것.
- ★★★ 절대 제한: {max_chars}자를 넘기면 음성이 중간에 잘린다.
- ★★★ 최소 제한: {target_range}자 범위의 하한 미만이면 영상이 허전해진다. 반드시 하한 이상으로 쓸 것!
- 너무 짧은 나레이션(10자 이하)은 절대 금지. 매 컷이 내용을 담아야 한다.
- 모든 컷마다 반드시 글자 수를 세고 확인할 것.
- 좋은 예: "석유를 재는 단위가 왜 하필 배럴일까요?" (19자) ✓ 꽉 찬 느낌
- 좋은 예: "펜실베이니아의 작은 마을에서 모든 게 바뀌었죠." (22자) ✓ 꽉 찬 느낌
- 나쁜 예: "배럴이 뭘까요?" (7자) ✗ 너무 짧아서 허전함
- 나쁜 예: "전 세계가 석유를 거래할 때 쓰는 단위 배럴이라고 하는데 이게 뭔지 아세요?" (37자) ✗ 넘침
- duration_estimate는 모든 컷에서 5.0으로 고정 — 절대 바꾸지 말 것
- 목표 길이에 맞게 컷 수 계산: 컷 수 = 목표길이(초) / 5
  예) 300초(5분) = 60컷, 600초(10분) = 120컷, 900초(15분) = 180컷

후킹 규칙 (가장 중요 — 첫 대사가 영상의 생사를 결정한다!!):
- ★★★ 첫 번째 컷(cut_number=1)은 영상 전체에서 가장 강렬하고 자극적인 한 마디로 시작!
- 시청자가 스크롤을 멈추고 "뭐?! 이거 봐야돼" 하게 만드는 한 방이 필요하다
- 좋은 첫 대사 패턴:
  * 충격 사실: "여러분이 매일 마시는 물, 사실 공룡 오줌입니다"
  * 도발 질문: "만약 내일 지구의 산소가 5초만 사라진다면?"
  * 반전 선언: "지금 당신 주머니 속 스마트폰, 아폴로 11호보다 10만 배 강력합니다"
  * 긴급성: "이 영상을 끝까지 보지 않으면, 평생 모르고 살 겁니다"
  * 스토리 훅: "1977년, NASA가 우주로 보낸 금색 레코드판. 거기 담긴 한국어가 있습니다"
- 절대 피할 것: "안녕하세요", "오늘은 ~에 대해", "~에 대해서 알아보겠습니다" 같은 밋밋한 시작
- 첫 대사는 주제의 가장 놀라운 사실, 가장 충격적인 숫자, 가장 의외의 반전을 꺼내라
- 첫 3~5컷은 시청자가 "나도 이거 궁금했는데!" 하며 빠져들게 만드는 떡밥 투척 구간
- 질문형, 반전형, 충격형 도입부를 적극 활용
- 절대 평범하게 시작하지 말 것. 훅 들어와서 관심 쭉 빨아야 함
- 단, 후킹도 반드시 {target_range}자 내에서 해결할 것!

콘텐츠 규칙:
- 각 컷 나레이션은 자연스러운 한국어 구어체, 반드시 {target_range}자 이내
- image_prompt는 반드시 영어로 작성
- scene_type: title(제목), narration(본문), transition(전환), ending(마무리)
- 구독/좋아요 요청은 절대 하지 않는다
- 마지막 컷은 여운이 남는 마무리 멘트로 깔끔하게 끝낸다 (예: 의미심장한 한 마디, 생각할 거리를 던지는 문장)

이미지 프롬프트 작성 규칙 (가장 중요!!!):
- image_prompt 는 **피사체·구도·동작·배경 오브젝트**만 묘사한다. 영어로, 간결하게.
- 절대 쓰지 말 것:
  * 색상 수식어: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome 등
  * 조명/분위기 수식어: cinematic lighting, moody, dramatic lighting, soft light, dark atmosphere, golden hour 등
  * 아트 스타일 선언: illustration style, cartoon style, anime style, photorealistic, watercolor, oil painting, Ghibli style, Pixar style 등
  * 품질 수식어: high quality, detailed, cinematic, 4k, masterpiece 등
- 스타일·색감·조명·그림체는 **전적으로 사용자가 첨부한 레퍼런스 이미지에서만** 결정된다.
  프롬프트에 색상이나 아트스타일 단어가 들어가면 레퍼런스와 충돌해서 결과가 망가진다.
- "전체 이미지 스타일" 필드에 사용자가 뭐라고 적었든, image_prompt 에 그 텍스트를 붙이지 말 것.
  image_prompt 에는 오직 "이 컷에 무엇이 보이는가" 만 남긴다.
- 좋은 예: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
- 나쁜 예: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

이미지 프롬프트 캐릭터 등장 규칙 (필수!!):
- ★★★ 이 규칙이 가장 중요하다. 절대 어기지 말 것! ★★★
- 사용자가 캐릭터를 제공했더라도 모든 컷에 캐릭터를 넣지 말 것!
- 캐릭터(사람, 인물, 피규어 포함)는 전체 컷의 최대 20~30%에만 등장시킨다 (예: 12컷이면 3~4컷, 60컷이면 12~18컷)
- 캐릭터가 등장하는 컷: 도입부(첫 컷), 핵심 장면 2~3개, 마무리 — 이 외에는 절대 넣지 말 것
- ★★★ 캐릭터가 등장하지 않는 컷 (전체의 70~80%): 반드시 사람/인물/캐릭터 없이 오직 오브젝트, 풍경, 배경, 도표, 지도, 추상적 비주얼, 자연 현상, 사물 클로즈업 등만 묘사 ★★★
- 비캐릭터 컷의 image_prompt 에 person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer 등 인물 단어가 하나라도 들어가면 실패로 간주한다
- 캐릭터 등장 컷에서는 image_prompt 에 캐릭터의 **형상·행동·포즈** 를 직접 서술하라
  예: "a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel"
  단, 색상 팔레트나 그림체 단어는 넣지 말 것 — 외형의 형태적 특징만.
- 캐릭터 외모 묘사를 빼면 이미지에 캐릭터가 안 나온다.
- 비캐릭터 컷 좋은 예: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- 비캐릭터 컷 좋은 예: "close-up of an oil barrel label, rust texture, industrial warehouse background"
- 비캐릭터 컷 나쁜 예: "a researcher examining an oil barrel" ← 인물이 들어감! 실패!
"""


SCRIPT_SYSTEM_PROMPT_EN = """You are a YouTube longform video script writer.
Write a compelling script on the given topic that hooks viewers and keeps them engaged.

You MUST respond ONLY with JSON in the exact format below. No other text:
{
  "title": "Video title (English, curiosity-inducing)",
  "description": "YouTube video description (SEO optimized, English)",
  "tags": ["tag1", "tag2", "tag3"],
  "thumbnail_prompt": "Thumbnail image generation prompt (English ONLY). Rules: 1) MUST depict the KEY SCENE from the actual video topic — no random shocking imagery unrelated to the subject. 2) Show a scene that makes viewers think 'What is this? I need to watch.' 3) Include a person's emotional expression (surprise/excitement/awe) to boost CTR. 4) Describe specific objects, backgrounds, and colors. 5) NO text, letters, numbers, or watermarks. 6) 16:9 ratio, cinematic lighting, high quality.",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "Narration text (English)",
      "image_prompt": "Image generation prompt (English, detailed visual description)",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

Key rules - Timing (THIS IS THE #1 RULE — VIOLATING IT BREAKS THE VIDEO!!):
- Each video clip is EXACTLY 5.0 seconds. No more, no less.
- Each cut's narration MUST fit within {tts_max_sec} seconds when spoken by TTS.
- Current TTS model: {tts_model}, speed: {tts_speed}
- At this setting, English TTS speaks at ~{words_per_sec} words per second.
- Therefore: MAXIMUM {max_words} words per narration. Aim for {target_range} words.
- ★★★ HARD LIMIT: If a narration exceeds {max_words} words, the audio will be CUT OFF mid-sentence.
- ★★★ MINIMUM: Narrations below the lower bound of {target_range} words make the video feel empty. ALWAYS write at least that many words!
- Extremely short narrations (3 words or fewer) are FORBIDDEN. Every cut must carry substance.
- Count your words CAREFULLY for EVERY SINGLE cut before writing it.
- Good: "Oil is measured in something called a barrel — but why?" (10 words) ✓ fills the time
- Good: "A small town in Pennsylvania changed everything forever." (8 words) ✓ fills the time
- BAD: "Barrels. Why?" (2 words) ✗ WAY too short, video feels empty
- BAD: "The entire world trades oil using a unit called a barrel but do you know what it is?" (18 words) ✗ EXCEEDS limit
- duration_estimate is fixed at 5.0 for all cuts — NEVER change this value
- Calculate cut count from target duration: cuts = target_duration(sec) / 5
  e.g.) 300sec(5min) = 60 cuts, 600sec(10min) = 120 cuts, 900sec(15min) = 180 cuts

Hooking rules (MOST IMPORTANT — the first line decides whether viewers stay or leave!!):
- ★★★ Cut #1 MUST be the most provocative, jaw-dropping single line in the ENTIRE script!
- The viewer must stop scrolling and think "WHAT?! I have to watch this"
- Great first-line patterns:
  * Shock fact: "The water you drink every day is literally dinosaur pee"
  * Provocative question: "What if Earth's oxygen disappeared for just 5 seconds?"
  * Reversal: "Your smartphone is 100,000 times more powerful than the Apollo 11 computer"
  * Urgency: "If you don't watch this to the end, you'll never know"
  * Story hook: "In 1977, NASA sent a golden record into space — and it had a Korean message on it"
- NEVER start with: "Hello", "Today we'll talk about", "In this video" — these are scroll-past material
- The first line should reveal the topic's most shocking fact, most surprising number, or most unexpected twist
- The first 3-5 cuts are the bait zone — drop shocking facts, counterintuitive claims, unanswered questions
- Use question hooks, reversal hooks, shock hooks aggressively
- NEVER start bland or generic. Hook hard and pull attention immediately
- Hooks MUST also stay within the {max_words} word limit!

Content rules:
- Each narration is natural conversational English, {target_range} words max
- image_prompt MUST be in English
- scene_type: title, narration, transition, ending
- NEVER ask for subscribes or likes
- The last cut ends with a lingering, thought-provoking closer (a memorable line that leaves the viewer thinking)

Image prompt writing rules (MOST IMPORTANT!!!):
- image_prompt describes ONLY subject, composition, action, and background objects. English, concise.
- NEVER include:
  * Color words: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome, etc.
  * Lighting/mood words: cinematic lighting, moody, dramatic lighting, soft light, dark atmosphere, golden hour, etc.
  * Art style declarations: illustration style, cartoon style, anime style, photorealistic, watercolor, oil painting, Ghibli style, Pixar style, etc.
  * Quality modifiers: high quality, detailed, cinematic, 4k, masterpiece, etc.
- Style, palette, lighting, and art direction are determined EXCLUSIVELY by the reference images the user attaches.
  Putting color or art-style words in the prompt will collide with the reference and ruin the result.
- Regardless of what the user wrote in the "global image style" field, do NOT inject that text into image_prompts.
  image_prompt contains only "what is visually present in this cut".
- Good: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
- Bad: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

Image prompt character appearance rules (MANDATORY — THIS IS THE MOST IMPORTANT RULE!!):
- ★★★ THIS RULE IS CRITICAL. VIOLATING IT RUINS THE VIDEO. ★★★
- Even if a character is provided, do NOT put the character in EVERY cut!
- Characters (including any people, humans, figures) should appear in ONLY 20-30% of cuts (e.g., 3-4 cuts out of 12, 12-18 cuts out of 60)
- Cuts WITH character: intro (first cut), 2-3 key story moments, ending — NOWHERE ELSE
- ★★★ Cuts WITHOUT character (70-80% of all cuts): MUST contain ONLY objects, landscapes, environments, diagrams, maps, abstract visuals, natural phenomena, close-ups of things. ABSOLUTELY NO people, humans, or characters. ★★★
- If a non-character cut's image_prompt contains ANY of these words it is FAILED: person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer, worker, child, kid, observer, viewer, narrator
- For cuts WHERE the character appears, describe the character's **shape, action, and pose** directly in the image_prompt
  Example: "a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel"
  Only morphological features — do NOT mention palette or art style.
- If you omit the character's shape description, the character will NOT appear in the image.
- Good non-character cut: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- Good non-character cut: "close-up of an oil barrel label, rust texture, industrial warehouse background"
- BAD non-character cut: "a researcher examining an oil barrel" ← HAS A PERSON! FAILED!
"""


SCRIPT_SYSTEM_PROMPT_JA = """あなたはYouTubeのロングフォーム動画の脚本家です。
与えられたトピックで視聴者を引き込む脚本を作成してください。

必ず以下のJSON形式のみで回答してください。JSON以外のテキストは一切出力しないでください:
{
  "title": "動画タイトル（日本語、好奇心を刺激する）",
  "description": "YouTube動画の説明（SEO最適化、日本語）",
  "tags": ["タグ1", "タグ2", "タグ3"],
  "thumbnail_prompt": "サムネイル画像生成プロンプト（英語必須）。ルール: 1) 必ず動画の主題/内容の核心シーンを描写 — 主題と無関係な刺激的画像は禁止。2) 視聴者が「これ何？見なきゃ」と思う一場面。3) 人物の感情表現（驚き/興奮/畏怖）を含めるとCTR向上。4) 具体的な物体/背景/色彩を描写。5) テキスト/文字/数字/透かし絶対禁止。6) 16:9比率、シネマティック照明、高画質。",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "ナレーションテキスト（日本語）",
      "image_prompt": "画像生成プロンプト（英語、具体的な視覚描写）",
      "duration_estimate": 5.0,
      "scene_type": "title"
    }
  ]
}

核心ルール - タイミング（最優先ルール — 違反すると映像が壊れる!!）:
- 各映像クリップは正確に5.0秒。それ以上は不可。
- 各カットのナレーションは{tts_max_sec}秒以内に収まる分量でなければならない。
- 現在のTTSモデル: {tts_model}、速度: {tts_speed}
- この設定で日本語TTSは1秒あたり約{chars_per_sec}文字で読む。
- したがって: 最大{max_chars}文字（スペース含む）。{target_range}文字を目標に。
- 絶対制限: {max_chars}文字を超えると音声が途中で切れる。
- 全カットで文字数を数えて確認すること。
- 良い例: 「石油の単位、バレル。知ってます？」（15文字）✓
- 良い例: 「ペンシルベニアで全てが変わった。」（15文字）✓
- 悪い例: 「全世界が石油を取引する単位バレルと呼ばれていますが何か知っていますか？」（35文字）✗ 却下
- duration_estimateは全カット5.0固定 — 絶対に変更しないこと
- 目標時間からカット数を計算: カット数 = 目標時間(秒) / 5
  例）300秒(5分) = 60カット、600秒(10分) = 120カット

フッキングルール（最重要 — 最初の一言が動画の生死を決める!!）:
- ★★★ 最初のカット(cut_number=1)は動画全体で最も強烈で刺激的な一言で始めること！
- 視聴者がスクロールを止めて「え?! これ見なきゃ」と思う一撃が必要
- 良い最初のセリフパターン:
  * 衝撃事実: 「毎日飲んでいる水、実は恐竜のおしっこです」
  * 挑発質問: 「もし明日、地球の酸素が5秒だけ消えたら？」
  * 逆転宣言: 「あなたのスマホ、アポロ11号の10万倍強力です」
  * 緊急性: 「この動画を最後まで見ないと一生知らないままです」
- 絶対NG: 「こんにちは」「今日は〜について」「〜を紹介します」のような平凡な出だし
- 最初のセリフはトピックの最も驚くべき事実、最も衝撃的な数字、最も意外な逆転を出せ
- 最初の3〜5カットは視聴者が引き込まれる餌を撒く区間
- 質問型、逆転型、衝撃型の導入を積極活用
- 絶対に平凡に始めないこと
- フックも必ず{target_range}文字以内で！

コンテンツルール:
- 各カットのナレーションは自然な日本語口語体、必ず{target_range}文字以内
- image_promptは必ず英語で記述
- scene_type: title、narration、transition、ending
- チャンネル登録やいいねのお願いは絶対にしない
- 最後のカットは余韻の残る締めくくり

画像プロンプト作成ルール（最重要!!!）:
- image_prompt は **被写体・構図・動作・背景オブジェクト** のみを記述する。英語で簡潔に。
- 絶対に使わないこと:
  * 色の修飾語: warm golden, cool blue, pastel, vibrant, muted, sepia, monochrome など
  * 照明・ムード: cinematic lighting, moody, dramatic lighting, soft light, dark atmosphere, golden hour など
  * アートスタイル宣言: illustration style, cartoon style, anime style, photorealistic, watercolor, oil painting, Ghibli style, Pixar style など
  * 品質修飾語: high quality, detailed, cinematic, 4k, masterpiece など
- スタイル・色・照明・画風は **ユーザーが添付するリファレンス画像のみから** 決定される。
  プロンプトに色やアートスタイルの単語を入れるとリファレンスと衝突して結果が壊れる。
- 「全体画像スタイル」フィールドにユーザーが何を書いていても、image_prompt にそのテキストを注入しないこと。
  image_prompt には「このカットに何が映っているか」だけを残す。
- 良い例: "a researcher examining an oil barrel on a sandy beach, pipes and boat in the background, pointing at a label"
- 悪い例: "Storytelling illustration style, warm golden tones, cinematic lighting, a researcher examining an oil barrel..."

画像プロンプトのキャラクター登場ルール（必須!! — 最も重要なルール!!）:
- ★★★ このルールは最重要。違反すると映像が台無しになる ★★★
- キャラクターが提供されても、全カットにキャラクターを入れないこと！
- キャラクター（人物・フィギュア含む）は全カットの20〜30%にのみ登場（例：12カットなら3〜4カット、60カットなら12〜18カット）
- キャラクター登場カット：導入（最初のカット）、重要シーン2〜3個、まとめ — これ以外は絶対に入れない
- ★★★ キャラクター不在カット（全体の70〜80%）：必ず人物なしでオブジェクト、風景、背景、図表、地図、抽象ビジュアル、自然現象、物のクローズアップのみ ★★★
- 不在カットの image_prompt に person, man, woman, boy, girl, character, figure, someone, people, human, researcher, scientist, explorer 等の人物単語が一つでもあれば失敗
- 登場カットでは image_prompt にキャラクターの **形・動作・ポーズ** を直接記述
  例：「a small character wearing a yellow hat holding a magnifying glass, pointing at an oil barrel」
  形態的特徴のみ — 色や画風は入れない。
- 形状記述を省略すると画像にキャラクターが出ない。
- 良い不在カット例: "a spinning globe with trade routes highlighted, cargo ships crossing the ocean"
- 悪い不在カット例: "a researcher examining an oil barrel" ← 人物あり！失敗！
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
        low = max(4, max_words - 2)
        return _sub(SCRIPT_SYSTEM_PROMPT_EN, {
            "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "words_per_sec": wps, "max_words": max_words,
            "target_range": f"{low}~{max_words}",
        })
    if language == "ja":
        cps = round(5.5 * effective_speed, 1)
        max_chars = int(tts_max_sec * cps)
        low = max(8, max_chars - 4)
        return _sub(SCRIPT_SYSTEM_PROMPT_JA, {
            "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
            "chars_per_sec": cps, "max_chars": max_chars,
            "target_range": f"{low}~{max_chars}",
        })
    # 한국어
    cps = round(5.0 * effective_speed, 1)
    max_chars = int(tts_max_sec * cps)
    low = max(8, max_chars - 5)
    return _sub(SCRIPT_SYSTEM_PROMPT_KO, {
        "tts_max_sec": tts_max_sec, "tts_model": tts_model, "tts_speed": tts_speed,
        "chars_per_sec": cps, "max_chars": max_chars,
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

        if language == "en":
            return (
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
