# LongTube 설정
# - 코드/DB: 로컬 (C:/Users/Jevis/Desktop/longtube)
# - 에셋(영상/이미지/음성): NAS (C:/Users/Jevis/Desktop/longtube_net)
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent.parent          # longtube/
DATA_DIR = Path(os.getenv("DATA_DIR", r"C:\Users\Jevis\Desktop\longtube_net\projects"))  # NAS
DB_PATH = BASE_DIR / "data" / "longtube.db"                       # 로컬 DB

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
FAL_KEY = os.getenv("FAL_KEY", "")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY", "")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")
RUNWAY_API_KEY = os.getenv("RUNWAY_API_KEY", "")
MIDJOURNEY_API_KEY = os.getenv("MIDJOURNEY_API_KEY", "")

# YouTube OAuth
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# v1.1.55: 로컬/네트워크 ComfyUI 서버 — 이미지/영상 생성을 자체 호스팅된
# ComfyUI 로 위임. 값 예: http://192.168.0.45:8188 (같은 네트워크의 다른 PC).
# 비어있으면 comfyui-* 프로바이더가 비활성화되고 기존 fal/kling/openai 로만 동작.
COMFYUI_BASE_URL = os.getenv("COMFYUI_BASE_URL", "").rstrip("/")
# ComfyUI 워크플로 JSON 프리셋 디렉토리
COMFYUI_WORKFLOWS_DIR = BASE_DIR / "backend" / "workflows" / "comfyui"

# Debug
DEBUG = os.getenv("DEBUG", "true").lower() == "true"

# --------------------------------------------------------------------------- #
# v1.1.45 — 컷당 고정 영상 길이
# --------------------------------------------------------------------------- #
# 모든 컷은 정확히 이 길이(초)로 렌더링된다. 시간 계산과 자막 싱크가 단순해지고,
# fal.ai 처럼 "5초 클립만 뽑아오는" 모델의 출력과 1:1 로 맞춰진다.
# 음성이 이 길이보다 짧으면 끝에 무음으로 패딩되고, 길면 잘린다(경고 로그).
# 값을 바꾸면 영상/자막/병합 전 파이프라인이 일괄로 따라간다.
CUT_VIDEO_DURATION = 5.0

# TTS 음성 최대 허용 길이. CUT_VIDEO_DURATION 보다 짧아야 영상 안에 여유가 생긴다.
# enforce_max_duration() 에서 이 값을 초과하면 atempo/자르기를 적용한다.
TTS_MAX_DURATION = 4.5

# v1.1.53: TTS 음성 최소 허용 길이. 이보다 짧으면 atempo 감속으로 늘린다.
# 4.0~4.5초 범위를 목표로 한다.
TTS_MIN_DURATION = 4.0
