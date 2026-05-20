# LongTube 설정
# - 코드/DB: 로컬 (longtube/)
# - v1.x 에셋: NAS (사용자 지정). v2 에서는 `LEGACY_DATA_DIR` 로 읽기 전용 보존.
# - v2 새 에셋: 기본 상대 경로 `longtube/data/outputs/`. UI(/v2/settings/storage) 에서 변경 가능.
import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# 경로 설정
BASE_DIR = Path(__file__).resolve().parent.parent.parent          # longtube/

# v2.1.0: DATA_DIR 기본값을 상대 경로로 전환.
# 사용자가 .env 에 DATA_DIR 을 명시했으면 그 값을 계속 존중한다(기존 설치 호환).
# .env 에 없으면 `longtube/data/outputs/` 를 쓴다. 경로는 부팅 시 자동 생성.
_default_data_dir = BASE_DIR / "data" / "outputs"
_RAW_DATA_DIR = Path(os.getenv("DATA_DIR", str(_default_data_dir)))

# v2.1.0: 구버전 NAS 경로 보존. legacy/ 읽기 전용 마운트 루트로 사용한다.
# 환경변수 LEGACY_DATA_DIR 가 있으면 그 값, 없으면 과거 기본값 유지(있으면 읽고 없으면 무시).
LEGACY_DATA_DIR = Path(
    os.getenv(
        "LEGACY_DATA_DIR",
        r"C:\Users\Jevis\Desktop\longtube_net\projects",
    )
)

CHANNELS_ROOT = _RAW_DATA_DIR / "channels"
SYSTEM_DIR = _RAW_DATA_DIR / "_system"
SYSTEM_PROJECTS_ROOT = SYSTEM_DIR / "projects"
RESULT_ARCHIVE_DIR = Path(os.getenv("RESULT_ARCHIVE_DIR", r"D:\long_result"))

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


def _coerce_channel(value) -> int | None:
    try:
        ch = int(value)
    except (TypeError, ValueError):
        return None
    return ch if ch >= 1 else None


def parse_v3_oneclick_project_id(project_id: str) -> tuple[int, int, str] | None:
    """Return (channel, episode, unique_id) for V3 workbench run project ids."""
    pid = str(project_id or "").strip()
    m = re.fullmatch(r"V3_CH([1-9]\d*)_EP(\d+)_([A-Za-z0-9][A-Za-z0-9_-]*)", pid)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    # Read compatibility for an early discussed external shape.
    m = re.fullmatch(r"CH([1-9]\d*)_EP\.(\d+)\.([A-Za-z0-9][A-Za-z0-9_-]*)", pid)
    if m:
        return int(m.group(1)), int(m.group(2)), m.group(3)
    return None


def v3_oneclick_project_dir(project_id: str) -> Path | None:
    parsed = parse_v3_oneclick_project_id(project_id)
    if not parsed:
        return None
    channel, episode, unique_id = parsed
    return RESULT_ARCHIVE_DIR / f"CH{channel}" / f"EP.{episode}.{unique_id}"


def infer_project_channel(project_id: str, config: dict | None = None) -> int | None:
    """프로젝트의 채널 번호를 추론한다.

    우선순위:
    1. project_id 의 `딸깍_CH{n}_...` prefix
    2. config["channel"]
    3. config["youtube_channel"]
    """
    pid = str(project_id or "").strip()
    parsed_v3 = parse_v3_oneclick_project_id(pid)
    if parsed_v3:
        return parsed_v3[0]
    m = re.search(r"(?:^|[_-])CH([1-4])(?:[_-]|$)", pid, flags=re.IGNORECASE)
    if m:
        return int(m.group(1))

    cfg = config or {}
    return _coerce_channel(cfg.get("channel")) or _coerce_channel(cfg.get("youtube_channel"))


def get_channel_projects_root(channel: int) -> Path:
    return CHANNELS_ROOT / f"CH{int(channel)}" / "projects"


def get_system_projects_root() -> Path:
    return SYSTEM_PROJECTS_ROOT


_ROOT_RESERVED_NAMES = {
    "_system",
    "channels",
    "logs",
    "presets",
    "tasks",
    "api_balances.json",
    "api_spend_log.jsonl",
}


def _looks_like_project_key(value) -> bool:
    key = str(value or "").strip()
    if not key:
        return False
    if parse_v3_oneclick_project_id(key):
        return True
    if "\\" in key or "/" in key:
        return False
    if key in _ROOT_RESERVED_NAMES:
        return False
    # 루트 설정/로그 파일은 project_id 로 취급하지 않는다.
    if Path(key).suffix and not key.startswith("딸깍_"):
        return False
    return True


def resolve_project_dir(project_id: str, config: dict | None = None, create: bool = False) -> Path:
    """프로젝트 디렉토리를 반환한다.

    저장 규칙:
    - 채널이 추론되면 `channels/CHn/projects/{project_id}`
    - 채널이 없으면 `_system/projects/{project_id}`
    - 구버전 루트 경로가 이미 있으면 읽기 호환용으로만 그대로 사용
    """
    pid = str(project_id or "").strip()
    if config and config.get("result_dir"):
        result_path = Path(str(config.get("result_dir")))
        if create or result_path.exists():
            if create:
                result_path.mkdir(parents=True, exist_ok=True)
            return result_path

    v3_path = v3_oneclick_project_dir(pid)
    if v3_path is not None:
        if create:
            v3_path.mkdir(parents=True, exist_ok=True)
        return v3_path

    ch = infer_project_channel(pid, config)
    if ch is not None:
        actual_path = get_channel_projects_root(ch) / pid
        if create or actual_path.exists():
            if create:
                actual_path.mkdir(parents=True, exist_ok=True)
            return actual_path

    channel_candidates: set[int] = set(range(1, 5))
    try:
        for child in CHANNELS_ROOT.iterdir():
            m = re.fullmatch(r"CH([1-9]\d*)", child.name, flags=re.IGNORECASE)
            if m:
                channel_candidates.add(int(m.group(1)))
    except Exception:
        pass
    for known_ch in sorted(channel_candidates):
        actual_path = get_channel_projects_root(known_ch) / pid
        if actual_path.exists():
            return actual_path

    system_path = get_system_projects_root() / pid
    if create or system_path.exists():
        if create:
            system_path.mkdir(parents=True, exist_ok=True)
        return system_path

    archive_path = RESULT_ARCHIVE_DIR / pid
    if archive_path.exists():
        return archive_path

    legacy_path = LEGACY_DATA_DIR / pid
    if legacy_path.exists():
        return legacy_path

    legacy_root_path = _RAW_DATA_DIR / pid
    if legacy_root_path.exists():
        return legacy_root_path

    if create:
        system_path.mkdir(parents=True, exist_ok=True)
        return system_path
    return system_path


class _DataDirProxy:
    """루트 경로와 project_id 해석을 동시에 제공하는 얇은 pathlike wrapper."""

    def __init__(self, root: Path):
        self._root = root

    def __fspath__(self) -> str:
        return os.fspath(self._root)

    def __str__(self) -> str:
        return str(self._root)

    def __repr__(self) -> str:
        return repr(self._root)

    def __truediv__(self, other):
        if _looks_like_project_key(other):
            return resolve_project_dir(str(other))
        return self._root / other

    def __getattr__(self, item):
        return getattr(self._root, item)


for _ch in range(1, 5):
    get_channel_projects_root(_ch).mkdir(parents=True, exist_ok=True)
SYSTEM_DIR.mkdir(parents=True, exist_ok=True)
SYSTEM_PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
DATA_DIR = _DataDirProxy(_RAW_DATA_DIR)

# --------------------------------------------------------------------------- #
# v1.1.45 — 컷당 고정 영상 길이
# --------------------------------------------------------------------------- #
# 모든 컷은 정확히 이 길이(초)로 렌더링된다. 시간 계산과 자막 싱크가 단순해지고,
# 150컷 × 4초 = 600초 롱폼 구성을 기본으로 맞춘다.
# 음성이 이 길이보다 짧으면 끝에 무음으로 패딩되고, 길면 잘린다(경고 로그).
# 값을 바꾸면 영상/자막/병합 전 파이프라인이 일괄로 따라간다.
CUT_VIDEO_DURATION = 4.0


def resolve_cut_video_duration(config: dict | None = None, default: float | None = None) -> float:
    """Return per-project cut duration, falling back to the 4s default."""
    fallback = float(default if default is not None else CUT_VIDEO_DURATION)
    raw = None
    if isinstance(config, dict):
        raw = config.get("cut_video_duration")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return fallback
    if value <= 0:
        return fallback
    return max(1.0, min(30.0, value))

# TTS 음성 목표 길이. 대본 생성은 4.4초 중심으로 쓰되,
# 음성 단계에서는 4초 컷 슬롯보다 긴 음성을 "압축 대상"으로 본다.
TTS_TARGET_DURATION = 4.4
TTS_MIN_DURATION = 4.2
TTS_MAX_DURATION = 4.6

# Anthropic safety brake.  The automation can start multiple 600s scripts in a
# row, so block new Claude calls after the rolling 24h spend crosses this cap.
# Set ANTHROPIC_DAILY_LIMIT_USD=0 to disable deliberately.
ANTHROPIC_DAILY_LIMIT_USD = float(os.getenv("ANTHROPIC_DAILY_LIMIT_USD", "1.00"))

# Absolute safety ceiling: target is 4.2~4.6s, and audio longer than this
# must not be accepted into the pipeline.
TTS_HARD_MAX_DURATION = 4.6
FIRST_CUT_FADE_IN_SECONDS = 0.5

# Final render narration gain. This is applied at render/mix time so script text,
# subtitles, and existing TTS files remain unchanged.
#
# 2026-05-06: 2.6 drove already-normal cut audio into the final limiter and
# produced audible hard limiting in long renders. Keep the gain conservative;
# final loudness is handled by the render filters.
NARRATION_VOLUME_GAIN = float(os.getenv("NARRATION_VOLUME_GAIN", "1.3"))

# Final render BGM gain multiplier. Stored project BGM volume remains unchanged;
# this is applied only at render/mix time for both long-form and shorts outputs.
BGM_VOLUME_MULTIPLIER = float(os.getenv("BGM_VOLUME_MULTIPLIER", "0.7"))
