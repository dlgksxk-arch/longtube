# AutoTube - 유튜브 롱폼 영상 자동 생성 파이프라인

## 설계 문서 v2.0

> v2.0 변경사항: 이미지 모델 6종 추가, 대본 AI 모델 선택 (Claude/GPT), 단계별 일시중지·편집·재시작, 전체 결과물 다운로드

---

## 1. 시스템 개요

### 목적
주제(또는 뉴스 URL)를 입력하면, 대본 작성부터 유튜브 업로드까지 **완전 자동화**되는 롱폼 영상 생성 도구. 각 단계에서 **일시중지 → 수동 편집 → 재시작**이 가능한 하이브리드 워크플로우.

### 실행 환경
- **OS**: Windows (로컬 PC)
- **접속**: `localhost:3000` (브라우저 UI) + `localhost:8000` (API 서버)
- **사용자**: 1인 (본인 전용)

### 핵심 원칙
- 모든 AI 기능은 외부 API 호출 (자체 모델 없음)
- 각 단계는 독립적으로 재실행 가능
- **각 단계 완료 후 일시중지 → 결과물 확인/편집 → 다음 단계 진행 가능**
- 모든 중간 결과물 + 최종 결과물 개별 다운로드 가능
- 크레딧/과금 시스템 없음 (본인 전용이므로 API 비용만 트래킹)

---

## 2. 지원 AI 모델 목록

### 2.1 대본 생성 모델 (Step 2)

| 모델 ID | 표시명 | API | 비고 |
|---------|--------|-----|------|
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | Anthropic API | **기본값** |
| `claude-opus-4-6` | Claude Opus 4.6 | Anthropic API | 최고 품질 |
| `claude-haiku-4-5` | Claude Haiku 4.5 | Anthropic API | 빠르고 저렴 |
| `gpt-4o` | GPT-4o | OpenAI API | |
| `gpt-4o-mini` | GPT-4o Mini | OpenAI API | 저비용 |
| `gpt-4.1` | GPT-4.1 | OpenAI API | |

**UI**: 드롭다운으로 모델 선택, 각 모델 옆에 예상 비용 표시

### 2.2 이미지 생성 모델 (Step 4)

| 모델 ID | 표시명 | API 엔드포인트 | 비율 지원 | 비고 |
|---------|--------|---------------|----------|------|
| `nano-banana-2` | Nano Banana 2 | bbanana API (자체) | 16:9, 9:16, 1:1, 3:4 | **기본값** |
| `nano-banana-pro` | Nano Banana Pro | bbanana API (자체) | 16:9, 9:16, 1:1, 3:4 | 고품질 |
| `nano-banana` | Nano Banana | bbanana API (자체) | 16:9, 9:16, 1:1, 3:4 | 레거시 |
| `seedream-v4.5` | Seedream V4.5 | fal.ai / Replicate | 16:9, 9:16, 1:1 | |
| `z-image-turbo` | Z-IMAGE Turbo | fal.ai / Replicate | 16:9, 9:16, 1:1 | 초고속 |
| `grok-imagine` | Grok Imagine Image | xAI API | 16:9, 1:1 | |
| `flux-dev` | Flux Dev | fal.ai | 모든 비율 | 범용 |
| `flux-schnell` | Flux Schnell | fal.ai | 모든 비율 | 초고속/저비용 |
| `midjourney` | Midjourney | 외부 API | 모든 비율 | 최고 품질 |

**UI**: 빠나나처럼 모델 드롭다운 + 비율 표시 + 컷당 비용 표시

### 2.3 영상 생성 모델 (Step 5)

| 모델 ID | 표시명 | API 엔드포인트 | 비고 |
|---------|--------|---------------|------|
| `ffmpeg-kenburns` | FFmpeg Ken Burns | 로컬 | **기본값**, 무료, 빠름 |
| `kling-v2` | Kling V2 | Kling API | 이미지→영상 변환 |
| `runway-gen3` | Runway Gen-3 | Runway API | 고품질 |
| `luma-dream` | Luma Dream Machine | Luma API | |
| `pika-v2` | Pika V2 | Pika API | |
| `seedance-lite` | Seedance 1.0 Lite | fal.ai | 빠나나 기본 모델 |
| `seedance-1.0` | Seedance 1.0 | fal.ai | 고품질 |
| `hailuo-minimax` | Hailuo (MiniMax) | MiniMax API | |

### 2.4 음성 모델 (Step 3)

| 모델 ID | 표시명 | API 엔드포인트 | 비고 |
|---------|--------|---------------|------|
| `elevenlabs` | ElevenLabs | ElevenLabs API | **기본값**, 다국어 |
| `openai-tts` | OpenAI TTS | OpenAI API | alloy, echo, fable 등 |

---

## 3. 기술 스택

| 레이어 | 기술 | 이유 |
|--------|------|------|
| **프론트엔드** | Next.js 14 + TypeScript + Tailwind CSS | 빠나나 스타일 다크 UI |
| **백엔드** | Python FastAPI | AI API 연동, FFmpeg 제어, 비동기 작업 관리 |
| **작업 큐** | Celery + Redis | 긴 작업(영상 생성 등)을 백그라운드 처리 |
| **데이터베이스** | SQLite | 1인 사용, 프로젝트 메타데이터 저장 |
| **영상 처리** | FFmpeg | 이미지+오디오 합성, 자막 삽입, 최종 렌더링 |
| **패키지 관리** | pnpm (프론트) / pip venv (백엔드) | |

---

## 4. 프로젝트 파일 구조

```
autotube/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                  # 대시보드 (프로젝트 목록)
│   │   │   ├── studio/[projectId]/
│   │   │   │   └── page.tsx              # 자동화 스튜디오
│   │   │   └── layout.tsx
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── TopNav.tsx
│   │   │   │   └── StepProgress.tsx      # 6단계 + 상태(완료/진행/일시중지/대기)
│   │   │   ├── studio/
│   │   │   │   ├── Step1Settings.tsx
│   │   │   │   ├── Step2Script.tsx       # 대본 편집기 + AI 모델 선택 드롭다운
│   │   │   │   ├── Step3Voice.tsx
│   │   │   │   ├── Step4Image.tsx        # 이미지 모델 선택 드롭다운
│   │   │   │   ├── Step5Video.tsx        # 영상 모델 선택 드롭다운
│   │   │   │   ├── Step6Subtitle.tsx
│   │   │   │   ├── CutList.tsx
│   │   │   │   └── StepControls.tsx      # [▶ 시작] [⏸ 일시중지] [⏭ 다음단계] 컨트롤
│   │   │   ├── common/
│   │   │   │   ├── VideoPreview.tsx
│   │   │   │   ├── PromptEditor.tsx
│   │   │   │   ├── ModelSelector.tsx     # 재사용 모델 선택 컴포넌트
│   │   │   │   └── DownloadButton.tsx    # 다운로드 버튼 (개별/전체)
│   │   │   └── dashboard/
│   │   │       └── ProjectCard.tsx
│   │   ├── hooks/
│   │   │   ├── useProject.ts
│   │   │   ├── usePipeline.ts            # 일시중지/재시작 상태 관리 포함
│   │   │   └── useWebSocket.ts
│   │   ├── lib/
│   │   │   └── api.ts
│   │   └── styles/
│   │       └── globals.css
│   ├── package.json
│   └── tailwind.config.ts
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py                     # API 키 + 모델 레지스트리
│   │   ├── models/
│   │   │   ├── project.py
│   │   │   └── cut.py
│   │   ├── routers/
│   │   │   ├── projects.py
│   │   │   ├── pipeline.py               # 일시중지/재시작/취소 API 포함
│   │   │   ├── script.py
│   │   │   ├── voice.py
│   │   │   ├── image.py
│   │   │   ├── video.py
│   │   │   ├── subtitle.py
│   │   │   ├── youtube.py
│   │   │   └── downloads.py              # 다운로드 전용 API
│   │   ├── services/
│   │   │   ├── llm/                      # 대본 AI 모델 통합
│   │   │   │   ├── base.py               # 추상 인터페이스
│   │   │   │   ├── claude_service.py     # Anthropic Claude
│   │   │   │   ├── gpt_service.py        # OpenAI GPT
│   │   │   │   └── factory.py            # 모델 ID → 서비스 인스턴스
│   │   │   ├── image/                    # 이미지 생성 모델 통합
│   │   │   │   ├── base.py
│   │   │   │   ├── flux_service.py
│   │   │   │   ├── nano_banana_service.py
│   │   │   │   ├── seedream_service.py
│   │   │   │   ├── zimage_service.py
│   │   │   │   ├── grok_service.py
│   │   │   │   ├── midjourney_service.py
│   │   │   │   └── factory.py
│   │   │   ├── video/                    # 영상 생성 모델 통합
│   │   │   │   ├── base.py
│   │   │   │   ├── ffmpeg_service.py
│   │   │   │   ├── kling_service.py
│   │   │   │   ├── runway_service.py
│   │   │   │   ├── seedance_service.py
│   │   │   │   └── factory.py
│   │   │   ├── tts/                      # TTS 모델 통합
│   │   │   │   ├── base.py
│   │   │   │   ├── elevenlabs_service.py
│   │   │   │   ├── openai_tts_service.py
│   │   │   │   └── factory.py
│   │   │   ├── subtitle_service.py
│   │   │   ├── youtube_service.py
│   │   │   └── download_service.py       # ZIP 패키징 + 개별 파일 서빙
│   │   ├── tasks/
│   │   │   └── pipeline_tasks.py         # Celery 태스크 (일시중지 신호 수신)
│   │   └── utils/
│   │       ├── prompt_templates.py
│   │       └── file_manager.py
│   ├── requirements.txt
│   └── .env
│
├── data/
│   └── projects/
│       └── {project_id}/
│           ├── script.json
│           ├── audio/
│           │   └── cut_001.mp3 ...
│           ├── images/
│           │   └── cut_001.png ...
│           ├── videos/
│           │   └── cut_001.mp4 ...
│           ├── subtitles/
│           │   └── final.ass
│           └── output/
│               ├── final.mp4
│               └── all_assets.zip        # 전체 다운로드용
│
├── docker-compose.yml
├── start.bat
└── README.md
```

---

## 5. 파이프라인 상세 설계

### 5.1 전체 흐름도 (일시중지 포인트 포함)

```
[주제 입력] 
    │
    ▼
[Step 1: 설정] ─── 비율, 스타일, 타겟 길이, 모델 선택
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[Step 2: 대본 생성] ─── Claude/GPT 선택 → 컷 단위 JSON
    │
    │  💡 대본 편집기: 컷별 나레이션/프롬프트 수정, 컷 추가/삭제/순서변경
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[Step 3: 음성 생성] ─── ElevenLabs/OpenAI TTS → 컷별 MP3
    │
    │  💡 컷별 음성 미리듣기, 마음에 안 드는 컷만 재생성
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[Step 4: 이미지 생성] ─── 6종 모델 중 선택 → 컷별 PNG
    │
    │  💡 컷별 이미지 미리보기, 프롬프트 수정 후 개별 재생성, 직접 이미지 업로드
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[Step 5: 영상 생성] ─── FFmpeg/Kling/Runway 등 선택 → 컷별 MP4
    │
    │  💡 컷별 영상 미리보기, 개별 재생성
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[Step 6: 자막 + 합성] ─── 자막 스타일 편집 → FFmpeg 최종 렌더링
    │
    │  💡 자막 타이밍/텍스트 수정, 스타일 조정 후 재렌더링
    │
    ▼ ──── ⏸ 일시중지 가능 ────
    │
[유튜브 업로드] ─── 제목/설명/태그 최종 확인 → 업로드
    │
    ▼
[📥 전체 다운로드] ─── 모든 결과물 ZIP 또는 개별 다운로드
```

### 5.2 파이프라인 상태 머신

```
각 Step의 상태:

  ┌─────────┐     시작      ┌───────────┐    완료     ┌───────────┐
  │ PENDING ├──────────────►│ RUNNING   ├───────────►│ COMPLETED │
  └─────────┘               └─────┬─────┘            └─────┬─────┘
                                  │                        │
                             일시중지                   재실행
                                  │                        │
                                  ▼                        ▼
                           ┌───────────┐            ┌───────────┐
                           │ PAUSED    ├───재시작──►│ RUNNING   │
                           └─────┬─────┘            └───────────┘
                                 │
                            편집 가능
                          (컷 수정, 프롬프트 변경,
                           파일 교체 등)
                                 │
                                 ▼
                           ┌───────────┐
                           │ EDITING   │ → 변경사항 저장 후 → PAUSED로 복귀
                           └───────────┘

  ※ FAILED 상태: 에러 발생 시 → 원인 표시 + 해당 컷만 재시도 가능
```

### 5.3 Step 1: 설정 (Global Config)

```json
{
  "aspect_ratio": "16:9",
  "target_duration": 600,
  "cut_transition": "slow",
  "style": "news_explainer",
  
  "script_model": "claude-sonnet-4-6",     // ★ 대본 AI 모델 선택
  "image_model": "nano-banana-2",           // ★ 이미지 모델 선택
  "video_model": "ffmpeg-kenburns",         // ★ 영상 모델 선택
  "tts_model": "elevenlabs",               // ★ TTS 모델 선택
  "tts_voice_id": "가탄",
  
  "language": "ko",
  "auto_pause_after_step": true,            // ★ 각 단계 완료 후 자동 일시중지
  
  "subtitle_style": {
    "font": "Pretendard Bold",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "position": "bottom"
  }
}
```

**`auto_pause_after_step` 옵션:**
- `true` (기본): 각 단계 완료 후 멈추고 결과물 확인 가능 → 수동으로 "다음 단계" 클릭
- `false`: 전체 자동 실행 (1→6 + 업로드까지 논스톱)

### 5.4 Step 2: 대본 생성 (멀티 모델)

```python
# services/llm/base.py
from abc import ABC, abstractmethod

class BaseLLMService(ABC):
    @abstractmethod
    async def generate_script(self, topic: str, config: dict) -> dict:
        """대본 생성 - 공통 인터페이스"""
        pass


# services/llm/claude_service.py
import anthropic

class ClaudeService(BaseLLMService):
    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.AsyncAnthropic()
        self.model = model
    
    async def generate_script(self, topic: str, config: dict) -> dict:
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=SCRIPT_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"주제: {topic}\n목표 길이: {config['target_duration']}초\n스타일: {config['style']}"
            }]
        )
        return json.loads(response.content[0].text)


# services/llm/gpt_service.py
from openai import AsyncOpenAI

class GPTService(BaseLLMService):
    def __init__(self, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
    
    async def generate_script(self, topic: str, config: dict) -> dict:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SCRIPT_SYSTEM_PROMPT},
                {"role": "user", "content": f"주제: {topic}\n목표 길이: {config['target_duration']}초"}
            ],
            response_format={"type": "json_object"},
            temperature=0.8
        )
        return json.loads(response.choices[0].message.content)


# services/llm/factory.py
def get_llm_service(model_id: str) -> BaseLLMService:
    """모델 ID → 서비스 인스턴스 매핑"""
    REGISTRY = {
        "claude-sonnet-4-6": lambda: ClaudeService("claude-sonnet-4-6"),
        "claude-opus-4-6":   lambda: ClaudeService("claude-opus-4-6"),
        "claude-haiku-4-5":  lambda: ClaudeService("claude-haiku-4-5-20251001"),
        "gpt-4o":            lambda: GPTService("gpt-4o"),
        "gpt-4o-mini":       lambda: GPTService("gpt-4o-mini"),
        "gpt-4.1":           lambda: GPTService("gpt-4.1"),
    }
    return REGISTRY[model_id]()
```

**대본 JSON 출력 형식 (Claude/GPT 공통):**
```json
{
  "title": "호르무즈 해협: 전 세계를 흔드는 좁은 바닷길의 비밀",
  "description": "유튜브 영상 설명...",
  "tags": ["호르무즈", "이란", "석유", "해협"],
  "thumbnail_prompt": "Dramatic aerial view of Strait of Hormuz with oil tankers...",
  "cuts": [
    {
      "cut_number": 1,
      "narration": "만약 하나의 좁은 바닷길이 세계 경제 전체를 뒤흔들 수 있다면 어떨까요?",
      "image_prompt": "Wide shot of a narrow ocean strait with jagged cliffs on both sides, surrounded by deep blue water and abstract geometric shapes representing global tension",
      "duration_estimate": 6.0,
      "scene_type": "title"
    }
  ]
}
```

### 5.5 Step 4: 이미지 생성 (멀티 모델)

```python
# services/image/base.py
class BaseImageService(ABC):
    @abstractmethod
    async def generate(self, prompt: str, width: int, height: int, output_path: str) -> str:
        pass


# services/image/nano_banana_service.py
class NanoBananaService(BaseImageService):
    """빠나나 자체 모델 (API 엔드포인트 필요)"""
    
    MODELS = {
        "nano-banana-2": "Nano Banana 2",
        "nano-banana-pro": "Nano Banana Pro", 
        "nano-banana": "Nano Banana",
    }
    
    async def generate(self, prompt, width, height, output_path):
        # bbanana.ai API 또는 호환 API 호출
        result = await self.client.post("/generate", json={
            "model": self.model_id,
            "prompt": prompt,
            "width": width,
            "height": height
        })
        download_file(result["image_url"], output_path)
        return output_path


# services/image/seedream_service.py
class SeedreamService(BaseImageService):
    """Seedream V4.5"""
    async def generate(self, prompt, width, height, output_path):
        result = await fal_client.run("fal-ai/seedream-v4.5", arguments={
            "prompt": prompt,
            "image_size": {"width": width, "height": height}
        })
        download_file(result["images"][0]["url"], output_path)
        return output_path


# services/image/zimage_service.py
class ZImageService(BaseImageService):
    """Z-IMAGE Turbo"""
    async def generate(self, prompt, width, height, output_path):
        result = await fal_client.run("fal-ai/z-image-turbo", arguments={
            "prompt": prompt,
            "image_size": {"width": width, "height": height}
        })
        download_file(result["images"][0]["url"], output_path)
        return output_path


# services/image/grok_service.py
class GrokImageService(BaseImageService):
    """Grok Imagine Image (xAI)"""
    async def generate(self, prompt, width, height, output_path):
        response = await xai_client.images.generate(
            model="grok-2-image",
            prompt=prompt,
            size=f"{width}x{height}"
        )
        download_file(response.data[0].url, output_path)
        return output_path


# services/image/factory.py
def get_image_service(model_id: str) -> BaseImageService:
    REGISTRY = {
        "nano-banana-2":   lambda: NanoBananaService("nano-banana-2"),
        "nano-banana-pro": lambda: NanoBananaService("nano-banana-pro"),
        "nano-banana":     lambda: NanoBananaService("nano-banana"),
        "seedream-v4.5":   lambda: SeedreamService(),
        "z-image-turbo":   lambda: ZImageService(),
        "grok-imagine":    lambda: GrokImageService(),
        "flux-dev":        lambda: FluxService("fal-ai/flux/dev"),
        "flux-schnell":    lambda: FluxService("fal-ai/flux/schnell"),
        "midjourney":      lambda: MidjourneyService(),
    }
    return REGISTRY[model_id]()
```

### 5.6 일시중지/재시작 메커니즘

```python
# tasks/pipeline_tasks.py

import redis
from celery import shared_task

redis_client = redis.Redis()

PAUSE_KEY = "pipeline:pause:{project_id}"
CANCEL_KEY = "pipeline:cancel:{project_id}"


def check_pause_or_cancel(project_id: str, step: int):
    """각 컷 처리 전 호출 - 일시중지/취소 신호 확인"""
    
    # 취소 확인
    if redis_client.get(CANCEL_KEY.format(project_id=project_id)):
        redis_client.delete(CANCEL_KEY.format(project_id=project_id))
        raise PipelineCancelled(f"Step {step} 취소됨")
    
    # 일시중지 확인 (블로킹 대기)
    while redis_client.get(PAUSE_KEY.format(project_id=project_id)):
        time.sleep(1)  # 재시작 신호 올 때까지 대기
        # 대기 중에도 취소 확인
        if redis_client.get(CANCEL_KEY.format(project_id=project_id)):
            raise PipelineCancelled(f"Step {step} 취소됨")


@shared_task
def run_pipeline(project_id: str, start_step: int = 1, end_step: int = 7):
    """파이프라인 실행 (특정 단계 범위 지정 가능)"""
    
    project = load_project(project_id)
    config = project["config"]
    auto_pause = config.get("auto_pause_after_step", True)
    
    steps = {
        2: ("대본 생성", run_script_generation),
        3: ("음성 생성", run_voice_generation),
        4: ("이미지 생성", run_image_generation),
        5: ("영상 생성", run_video_generation),
        6: ("자막 + 합성", run_subtitle_and_merge),
        7: ("유튜브 업로드", run_youtube_upload),
    }
    
    for step_num in range(start_step, end_step + 1):
        if step_num not in steps:
            continue
        
        step_name, step_func = steps[step_num]
        update_status(project_id, step_num, "RUNNING")
        send_ws(project_id, {"step": step_num, "status": "running", "message": f"{step_name} 시작..."})
        
        try:
            step_func(project_id, config, check_pause_callback=lambda: check_pause_or_cancel(project_id, step_num))
            update_status(project_id, step_num, "COMPLETED")
            send_ws(project_id, {"step": step_num, "status": "completed"})
            
            # 자동 일시중지 모드: 각 단계 완료 후 멈춤
            if auto_pause and step_num < end_step:
                update_status(project_id, step_num + 1, "PAUSED")
                send_ws(project_id, {
                    "step": step_num,
                    "status": "paused_after_complete",
                    "message": f"{step_name} 완료. 결과물을 확인하고 '다음 단계'를 눌러주세요."
                })
                # 재시작 신호 대기
                redis_client.set(PAUSE_KEY.format(project_id=project_id), "1")
                while redis_client.get(PAUSE_KEY.format(project_id=project_id)):
                    time.sleep(1)
                    if redis_client.get(CANCEL_KEY.format(project_id=project_id)):
                        raise PipelineCancelled("파이프라인 취소됨")
        
        except PipelineCancelled:
            update_status(project_id, step_num, "CANCELLED")
            break
        except Exception as e:
            update_status(project_id, step_num, "FAILED", error=str(e))
            send_ws(project_id, {"step": step_num, "status": "failed", "error": str(e)})
            break
```

### 5.7 일시중지 중 편집 API

```python
# routers/pipeline.py

@router.post("/{project_id}/pause")
async def pause_pipeline(project_id: str):
    """실행 중인 파이프라인 일시중지"""
    redis_client.set(f"pipeline:pause:{project_id}", "1")
    return {"status": "pausing", "message": "현재 컷 처리 완료 후 일시중지됩니다"}

@router.post("/{project_id}/resume")
async def resume_pipeline(project_id: str):
    """일시중지된 파이프라인 재시작"""
    redis_client.delete(f"pipeline:pause:{project_id}")
    return {"status": "resumed"}

@router.post("/{project_id}/resume-from/{step}")
async def resume_from_step(project_id: str, step: int):
    """특정 단계부터 재시작 (이전 단계 편집 후)"""
    redis_client.delete(f"pipeline:pause:{project_id}")
    # 해당 단계부터 새로 실행
    run_pipeline.delay(project_id, start_step=step)
    return {"status": "restarted", "from_step": step}

@router.post("/{project_id}/cancel")
async def cancel_pipeline(project_id: str):
    """파이프라인 취소"""
    redis_client.set(f"pipeline:cancel:{project_id}", "1")
    return {"status": "cancelling"}


# 일시중지 중 개별 컷 수정
@router.put("/{project_id}/cuts/{cut_number}/narration")
async def edit_cut_narration(project_id: str, cut_number: int, body: EditNarrationRequest):
    """컷 나레이션 텍스트 수정 (일시중지 중)"""
    script = load_script(project_id)
    script["cuts"][cut_number - 1]["narration"] = body.narration
    save_script(project_id, script)
    return {"status": "updated"}

@router.put("/{project_id}/cuts/{cut_number}/image-prompt")
async def edit_cut_image_prompt(project_id: str, cut_number: int, body: EditPromptRequest):
    """컷 이미지 프롬프트 수정 (일시중지 중)"""
    script = load_script(project_id)
    script["cuts"][cut_number - 1]["image_prompt"] = body.prompt
    save_script(project_id, script)
    return {"status": "updated"}

@router.post("/{project_id}/cuts/{cut_number}/regenerate/{asset_type}")
async def regenerate_cut_asset(project_id: str, cut_number: int, asset_type: str):
    """특정 컷의 특정 에셋만 재생성 (voice, image, video)"""
    # asset_type: "voice" | "image" | "video"
    # 해당 컷의 해당 에셋만 다시 생성
    ...

@router.post("/{project_id}/cuts/{cut_number}/upload-image")
async def upload_custom_image(project_id: str, cut_number: int, file: UploadFile):
    """AI 생성 대신 직접 이미지 업로드"""
    save_path = f"data/projects/{project_id}/images/cut_{cut_number:03d}.png"
    with open(save_path, "wb") as f:
        f.write(await file.read())
    return {"status": "uploaded", "path": save_path}
```

---

## 6. 다운로드 시스템

### 6.1 다운로드 API

```python
# routers/downloads.py

from fastapi.responses import FileResponse, StreamingResponse
import zipfile, io

@router.get("/{project_id}/download/{asset_type}")
async def download_asset(project_id: str, asset_type: str, cut_number: int = None):
    """개별 에셋 다운로드"""
    
    paths = {
        "script":    f"data/projects/{project_id}/script.json",
        "audio":     f"data/projects/{project_id}/audio/cut_{cut_number:03d}.mp3",
        "image":     f"data/projects/{project_id}/images/cut_{cut_number:03d}.png",
        "video":     f"data/projects/{project_id}/videos/cut_{cut_number:03d}.mp4",
        "subtitle":  f"data/projects/{project_id}/subtitles/final.ass",
        "final":     f"data/projects/{project_id}/output/final.mp4",
    }
    
    file_path = paths.get(asset_type)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(404, "파일이 존재하지 않습니다")
    
    return FileResponse(file_path, filename=os.path.basename(file_path))


@router.get("/{project_id}/download-all")
async def download_all(project_id: str):
    """전체 프로젝트 ZIP 다운로드"""
    
    project_dir = f"data/projects/{project_id}"
    zip_buffer = io.BytesIO()
    
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(project_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, project_dir)
                zf.write(file_path, arcname)
    
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=autotube_{project_id}.zip"}
    )


@router.get("/{project_id}/download-step/{step}")
async def download_step_assets(project_id: str, step: int):
    """특정 단계 결과물 ZIP 다운로드"""
    
    step_dirs = {
        2: "script.json",           # 대본
        3: "audio/",                # 음성 파일들
        4: "images/",               # 이미지 파일들
        5: "videos/",               # 영상 클립들
        6: "output/final.mp4",      # 최종 영상
    }
    # ... ZIP 생성 로직
```

### 6.2 UI 다운로드 버튼 배치

```
┌─────────────────────────────────────────────────┐
│  Step 3: 음성 생성 ✅ 완료                        │
│                                                  │
│  Cut 1  ▶ 미리듣기  📥 MP3   ✏️ 수정  🔄 재생성   │
│  Cut 2  ▶ 미리듣기  📥 MP3   ✏️ 수정  🔄 재생성   │
│  Cut 3  ▶ 미리듣기  📥 MP3   ✏️ 수정  🔄 재생성   │
│  ...                                             │
│                                                  │
│  [📥 이 단계 전체 다운로드]  [⏭ 다음 단계로]        │
└──────────────────────────────────────────────────┘

최종:
┌──────────────────────────────────────────────────┐
│  📥 다운로드 옵션                                  │
│                                                   │
│  [📥 최종 영상 (MP4)]                              │
│  [📥 대본 (JSON)]                                  │
│  [📥 모든 음성 (ZIP)]                              │
│  [📥 모든 이미지 (ZIP)]                            │
│  [📥 모든 영상클립 (ZIP)]                          │
│  [📥 자막 파일 (ASS)]                              │
│  [📥 전체 프로젝트 (ZIP)]                          │
│                                                   │
│  [📤 유튜브 업로드]                                │
└──────────────────────────────────────────────────┘
```

---

## 7. API 엔드포인트 명세 (전체)

### 프로젝트 관리

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/projects` | 프로젝트 목록 |
| POST | `/api/projects` | 새 프로젝트 생성 |
| GET | `/api/projects/{id}` | 프로젝트 상세 |
| DELETE | `/api/projects/{id}` | 프로젝트 삭제 |
| PUT | `/api/projects/{id}/config` | 설정 저장 (모델 선택 포함) |

### 파이프라인 제어

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/pipeline/{id}/run-all` | 전체 자동 실행 |
| POST | `/api/pipeline/{id}/step/{n}` | 특정 단계만 실행 |
| POST | `/api/pipeline/{id}/pause` | ⏸ 일시중지 |
| POST | `/api/pipeline/{id}/resume` | ▶ 재시작 |
| POST | `/api/pipeline/{id}/resume-from/{step}` | 특정 단계부터 재시작 |
| POST | `/api/pipeline/{id}/cancel` | ⏹ 취소 |
| GET | `/api/pipeline/{id}/status` | 현재 상태 |

### 컷 편집 (일시중지 중)

| Method | Endpoint | 설명 |
|--------|----------|------|
| PUT | `/api/{id}/cuts/{n}/narration` | 나레이션 텍스트 수정 |
| PUT | `/api/{id}/cuts/{n}/image-prompt` | 이미지 프롬프트 수정 |
| POST | `/api/{id}/cuts/{n}/regenerate/{type}` | 특정 에셋 재생성 |
| POST | `/api/{id}/cuts/{n}/upload-image` | 커스텀 이미지 업로드 |
| POST | `/api/{id}/cuts/add` | 컷 추가 |
| DELETE | `/api/{id}/cuts/{n}` | 컷 삭제 |
| PUT | `/api/{id}/cuts/reorder` | 컷 순서 변경 |

### 다운로드

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/{id}/download/{type}?cut=N` | 개별 에셋 다운로드 |
| GET | `/api/{id}/download-step/{step}` | 특정 단계 ZIP |
| GET | `/api/{id}/download-all` | 전체 프로젝트 ZIP |

### 모델 정보

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/models/llm` | 사용 가능한 대본 모델 목록 |
| GET | `/api/models/image` | 사용 가능한 이미지 모델 목록 |
| GET | `/api/models/video` | 사용 가능한 영상 모델 목록 |
| GET | `/api/models/tts` | 사용 가능한 TTS 모델 목록 |

---

## 8. 데이터베이스 스키마

### projects

```sql
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    config          JSON NOT NULL,            -- 모델 선택 포함
    status          TEXT DEFAULT 'draft',     -- draft, processing, paused, completed, failed
    current_step    INTEGER DEFAULT 0,
    step_states     JSON DEFAULT '{}',        -- {"2":"completed","3":"paused","4":"pending"...}
    total_cuts      INTEGER DEFAULT 0,
    youtube_url     TEXT,
    api_cost        REAL DEFAULT 0.0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### cuts

```sql
CREATE TABLE cuts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id),
    cut_number      INTEGER NOT NULL,
    narration       TEXT,
    image_prompt    TEXT,
    scene_type      TEXT,
    audio_path      TEXT,
    audio_duration  REAL,
    image_path      TEXT,
    image_model     TEXT,                     -- 사용된 이미지 모델
    video_path      TEXT,
    video_model     TEXT,                     -- 사용된 영상 모델
    status          TEXT DEFAULT 'pending',
    is_custom_image BOOLEAN DEFAULT FALSE,    -- 직접 업로드 여부
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### api_logs

```sql
CREATE TABLE api_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT REFERENCES projects(id),
    service         TEXT NOT NULL,
    model           TEXT,                     -- 사용된 모델 ID
    endpoint        TEXT,
    cost_usd        REAL DEFAULT 0.0,
    tokens_used     INTEGER,
    duration_ms     INTEGER,
    status          TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 9. UI/UX 설계

### 색상 시스템

```css
:root {
  --bg-primary: #0D0D0D;
  --bg-secondary: #1A1A2E;
  --bg-tertiary: #16213E;
  --accent-primary: #7C3AED;      /* 보라 - 진행률, 활성 */
  --accent-secondary: #F59E0B;    /* 골드 - CTA 버튼 */
  --accent-success: #10B981;      /* 녹색 - 완료 */
  --accent-warning: #EAB308;      /* 노랑 - 일시중지 */
  --accent-danger: #EF4444;       /* 빨강 - 에러/취소 */
  --text-primary: #FFFFFF;
  --text-secondary: #9CA3AF;
  --border: #2D2D44;
}
```

### StepProgress 상태별 아이콘

```
✅ COMPLETED (보라 체크)    → 클릭하면 해당 단계 결과물 보기
🔄 RUNNING (보라 스피너)    → 진행률 % 표시
⏸ PAUSED (노랑 일시중지)   → "편집 가능" 표시
❌ FAILED (빨강 X)          → 에러 메시지 + 재시도 버튼
○  PENDING (회색 원)        → 대기 중
```

### 단계별 편집 컨트롤 바

```
┌──────────────────────────────────────────────────────────────────┐
│  [◀ 이전 단계] [⏸ 일시중지] [▶ 재시작] [⏭ 다음 단계] [⏹ 취소]     │
│                                                                   │
│  모델: [Claude Sonnet 4.6 ▼]    진행: ████████░░ 75% (20/27컷)   │
│                                                                   │
│  [📥 이 단계 다운로드]  [📥 전체 프로젝트 다운로드]                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 10. .env 설정

```env
# Anthropic (대본 - Claude)
ANTHROPIC_API_KEY=sk-ant-...

# OpenAI (대본 - GPT / TTS)
OPENAI_API_KEY=sk-...

# ElevenLabs (TTS)
ELEVENLABS_API_KEY=...

# fal.ai (Flux, Seedream, Z-IMAGE, Seedance)
FAL_KEY=...

# xAI (Grok Imagine)
XAI_API_KEY=...

# Kling
KLING_ACCESS_KEY=...
KLING_SECRET_KEY=...

# Runway (선택)
RUNWAY_API_KEY=...

# Midjourney (선택, 프록시 서비스 경유)
MIDJOURNEY_API_KEY=...

# YouTube OAuth
YOUTUBE_CLIENT_ID=...
YOUTUBE_CLIENT_SECRET=...
YOUTUBE_REDIRECT_URI=http://localhost:8000/auth/youtube/callback
```

---

## 11. 예상 API 비용 (10분 영상, ~27컷 기준)

| 단계 | 모델 | 비용 |
|------|------|------|
| 대본 | Claude Sonnet 4.6 | ~$0.03 |
| 대본 | GPT-4o | ~$0.05 |
| 음성 | ElevenLabs | ~$0.50 |
| 이미지 | Flux Dev | ~$0.27 |
| 이미지 | Nano Banana 2 | ~$0.30 (추정) |
| 이미지 | Z-IMAGE Turbo | ~$0.15 |
| 영상 | FFmpeg (로컬) | $0.00 |
| 영상 | Kling V2 | ~$2.70 |
| 영상 | Seedance Lite | ~$0.81 |
| 업로드 | YouTube API | $0.00 |
| **합계 (최저: Claude + Z-IMAGE + FFmpeg)** | | **~$0.68** |
| **합계 (최고: GPT + Midjourney + Kling)** | | **~$5.00+** |

---

## 12. 개발 로드맵

### Phase 1: 핵심 파이프라인 (1~2주)
- Python 백엔드 기본 구조 + Factory 패턴 서비스
- Claude/GPT 대본 생성
- ElevenLabs 음성
- Flux + Nano Banana + Z-IMAGE + Seedream + Grok 이미지
- FFmpeg 합성
- CLI 테스트

### Phase 2: UI + 제어 (1~2주)
- Next.js 다크 테마 대시보드
- 6단계 스텝 워크플로우 UI + 모델 선택 드롭다운
- **일시중지 / 재시작 / 편집 / 재생성 UI**
- WebSocket 실시간 진행률
- **개별 + 전체 다운로드 버튼**

### Phase 3: 유튜브 + 고도화 (1주)
- YouTube Data API 연동
- 영상 모델 추가 (Kling, Runway, Seedance 등)
- 에러 핸들링 + 자동 재시도

### Phase 4: 편의 기능 (지속적)
- 프로젝트 복제/템플릿
- 배치 생성 (여러 영상 연속)
- API 비용 대시보드
- 모델 성능 비교 (같은 프롬프트, 다른 모델 결과 비교)
