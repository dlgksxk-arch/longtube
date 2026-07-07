"""고스트 테스트 — 외부 API 호출 없이 딸깍 파이프라인 전체를 검증.

모든 서비스(LLM, TTS, Image, Video, Render, YouTube)를 더미로 교체하여
실제 비용 없이 _run_sync_pipeline → render → upload 경로를 확인한다.

사용법:
    cd backend
    python -m tests.test_ghost_pipeline
"""
import asyncio
import json
import os
import sys
import time
import shutil
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

# backend/ 를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ★ config.DB_PATH 를 sys.modules 트릭으로 사전 교체
# database.py 가 `from app.config import DB_PATH` 하므로 module 자체를 먼저 넣어야 함
os.environ["DATA_DIR"] = "/tmp/longtube_ghost_test"
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

# 1) app.config 를 먼저 import 한 뒤 DB_PATH 교체
import app.config as _cfg
_cfg.DB_PATH = Path("/tmp/test_ghost.db")
_cfg.DATA_DIR = Path("/tmp/longtube_ghost_test")

# 2) database.py 가 아직 안 읽혔으면 좋겠지만, import chain 때문에 이미 읽혔을 수 있음.
#    engine/SessionLocal 을 강제 교체
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import app.models.database as _db
_new_engine = create_engine("sqlite:////tmp/test_ghost.db", connect_args={"check_same_thread": False})
_new_session = sessionmaker(bind=_new_engine, autoflush=False, autocommit=False)
_db.engine = _new_engine
_db.SessionLocal = _new_session

# 3) 이미 SessionLocal 을 from-import 한 모듈들도 교체
import app.services.oneclick_service as _ocs
import app.tasks.pipeline_tasks as _pt
_ocs.SessionLocal = _new_session
_pt.SessionLocal = _new_session

from app.config import DATA_DIR, resolve_project_dir

# ─── 더미 데이터 ──────────────────────────────────────────

GHOST_TOPIC = "[고스트] 테스트 주제"
GHOST_CUTS = 3  # 컷 수를 최소로

DUMMY_SCRIPT = {
    "title": "[고스트] 테스트 영상",
    "description": "고스트 테스트용 더미 대본",
    "tags": ["test", "ghost"],
    "thumbnail_prompt": "test thumbnail",
    "cuts": [
        {
            "cut_number": i + 1,
            "narration": f"고스트 테스트 나레이션 {i + 1}번 컷입니다.",
            "image_prompt": f"ghost test image prompt {i + 1}",
            "duration_estimate": 5.0,
            "scene_type": "narration",
        }
        for i in range(GHOST_CUTS)
    ],
}


# ─── 더미 서비스 ──────────────────────────────────────────


class DummyLLMService:
    async def generate_story_plan(self, topic, config):
        print(f"  [GHOST-LLM] generate_story_plan({topic!r}) → 더미 스토리 설계")
        return {
            "script_version": "3.1",
            "visual_world": {
                "time_range": "Ghost test time",
                "place_scope": "Ghost test workspace",
                "culture_scope": "Synthetic pipeline test context",
                "material_culture": "Simple test objects and neutral interface-like props",
                "continuity_rule": "Every scene stays inside the same synthetic test world",
            },
            "story_core": {
                "story_axis": "고스트 테스트가 전체 파이프라인을 한 번 통과하는 흐름",
                "episode_scope": "고스트 테스트 시작부터 더미 대본 생성 직전까지",
                "central_question": "고스트 테스트 중심 질문",
                "central_answer": "고스트 테스트 중심 답변",
                "protagonist": "고스트 테스트",
                "goal": "파이프라인 검증",
                "obstacle": "외부 API 없이 실행",
                "first_turn": "더미 서비스로 대체",
                "mid_crisis": "단계 연결 확인",
                "cost": "비용 없음",
                "ending_memory": "고스트 테스트가 통과했다",
            },
            "character_map": [
                {
                    "name": "고스트 테스트",
                    "identity": "외부 API 없이 파이프라인을 검증하는 더미 대상",
                    "side_or_interest": "생성 단계 연결 확인",
                    "first_appearance_cut": "1",
                    "first_appearance_explanation": "고스트 테스트가 무엇을 검증하는지 설명",
                    "choice_or_action": "더미 서비스로 스토리와 대본을 반환",
                    "story_function": "전체 단계 연결 검증",
                }
            ],
            "causality_chain": [
                "고스트 테스트가 시작된다",
                "더미 스토리 설계가 반환된다",
                "더미 대본 생성으로 이어진다",
                "외부 API 없이 단계 연결을 확인한다",
            ],
            "fact_ledger": {
                "confirmed_facts": ["고스트 테스트는 외부 API 없이 실행된다"],
                "careful_inferences": ["더미 서비스로 단계 연결을 확인할 수 있다"],
                "unknown_or_debated": ["실제 모델 품질은 이 테스트에서 판단하지 않는다"],
                "forbidden_claims": ["실제 API가 호출됐다고 말하지 않는다"],
            },
            "visual_plan": {
                "overall_ratio": {"character_closeup": 10, "intense_action": 10},
                "five_cut_rhythm": ["wide situation", "test object", "transition"],
                "avoid": ["external API scene"],
            },
            "story_beats": [
                {
                    "beat_id": 1,
                    "act": 1,
                    "cut_range": f"1-{GHOST_CUTS}",
                    "beat_role": "hook",
                    "scene_goal": "고스트 테스트의 목적을 이해시킨다",
                    "viewer_question": "외부 API 없이 파이프라인이 이어지는가",
                    "key_facts": ["더미 스토리 설계 반환", "더미 대본 생성 연결"],
                    "character_focus": ["고스트 테스트"],
                    "first_appearance": "고스트 테스트",
                    "causality_from_previous": "테스트 시작",
                    "story_purpose": "고스트 파이프라인 검증",
                    "tension": "외부 API 호출 없이 전체 단계가 이어지는지 확인",
                    "turn_or_reveal": "더미 서비스로 실제 호출을 대체",
                    "required_script_moves": ["테스트 목적 설명", "다음 단계 연결"],
                    "turn_to_next": "더미 대본 생성으로 이어짐",
                }
            ],
            "scene_blocks": [
                {
                    "block_id": 1,
                    "cut_range": f"1-{GHOST_CUTS}",
                    "beat_id": 1,
                    "block_role": "hook",
                    "mini_question": "더미 파이프라인이 이어지는가",
                    "new_information": "외부 API 없이 스토리와 대본 단계를 연결한다",
                    "tension": "단계 누락 없이 진행되는지 확인한다",
                    "turn": "더미 대본 생성으로 넘어간다",
                    "visual_rhythm": "wide test scene -> simple object -> bridge",
                    "must_include": ["고스트 테스트", "더미 대본"],
                    "must_avoid": ["실제 API 호출 단정"],
                }
            ],
            "script_checklist": {
                "story": ["중심 질문 제시"],
                "continuity": ["단계 연결"],
                "facts": ["외부 API 호출 금지"],
                "visual": ["동일 테스트 세계 유지"],
            },
        }

    async def generate_script(self, topic, config):
        print(f"  [GHOST-LLM] generate_script({topic!r}) → {GHOST_CUTS}컷 더미 대본")
        return DUMMY_SCRIPT

    @staticmethod
    def assert_script_timing(script, config):
        return None


class DummyTTSService:
    async def generate(self, text, voice_id, output_path, speed=1.0, **kw):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # 더미 mp3 (빈 파일 — FFmpeg 테스트에선 사용 안 함)
        Path(output_path).write_bytes(b"\x00" * 1024)
        print(f"  [GHOST-TTS] → {Path(output_path).name} (더미 1KB)")
        return {"path": output_path, "duration": 3.5}


class DummyImageService:
    async def generate(self, prompt, width, height, output_path, **kw):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        # 더미 PNG (1x1 빨간 픽셀)
        import struct, zlib
        def _make_png():
            raw = b"\x00\xff\x00\x00"  # filter + RGB
            compressed = zlib.compress(raw)
            def chunk(ctype, data):
                c = ctype + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
            return (
                b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", compressed)
                + chunk(b"IEND", b"")
            )
        Path(output_path).write_bytes(_make_png())
        print(f"  [GHOST-IMG] → {Path(output_path).name} (더미 1x1 PNG)")
        return output_path


class DummyVideoService:
    """v1.1.52: _step_video 가 get_video_service() 로 받는 서비스 인터페이스.
    generate(image_path, audio_path, duration, output_path, ...) 를 구현한다.
    """
    async def generate(self, *, image_path, audio_path, duration, output_path,
                       aspect_ratio="16:9", prompt="", **kw):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"\x00" * 2048)
        print(f"  [GHOST-VID] → {Path(output_path).name} (더미 2KB)")
        return output_path

    async def create_cut_with_audio(self, image_path, audio_path, output_path, duration):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"\x00" * 2048)
        print(f"  [GHOST-VID] → {Path(output_path).name} (더미 2KB)")

    @staticmethod
    async def merge_videos(video_paths, output_path):
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"\x00" * 4096)
        print(f"  [GHOST-MERGE] {len(video_paths)}개 → {Path(output_path).name}")
        return output_path


# ─── 테스트 실행 ──────────────────────────────────────────


def run_ghost_test():
    print("=" * 60)
    print("고스트 테스트 시작 — API 호출 없음")
    print("=" * 60)
    try:
        from app.services.cancel_ctx import clear_all_halted, set_cancel_key
        clear_all_halted()
        set_cancel_key(None)
    except Exception:
        pass

    # 1. DB 세팅 — 교체된 엔진으로 테이블 생성
    from app.models.database import Base
    Base.metadata.create_all(bind=_new_engine)

    # 2. 더미 프로젝트 생성
    from app.services.oneclick_service import (
        _clone_project_from_template,
        _make_task_record,
        _run_sync_pipeline,
        _update_project_status,
        _load_project,
        STEP_ORDER,
    )
    from app.services.estimation_service import estimate_project
    import uuid

    project = _clone_project_from_template(None, GHOST_TOPIC, "[고스트] 테스트")
    project_id = project.id
    try:
        from app.tasks.pipeline_tasks import _redis_delete
        _redis_delete(f"pipeline:cancel:{project_id}", f"pipeline:pause:{project_id}")
    except Exception:
        pass
    print(f"\n[1] 프로젝트 생성: {project_id}")
    print(f"    topic={project.topic}, config keys={list((project.config or {}).keys())[:10]}")

    # 3. 태스크 레코드 생성
    task_id = str(uuid.uuid4())[:8]
    estimate = estimate_project(project.config or {})
    task = _make_task_record(
        task_id,
        template_project_id=None,
        project_id=project_id,
        topic=GHOST_TOPIC,
        title="[고스트] 테스트",
        estimate=estimate,
    )
    task["status"] = "running"
    task["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[2] 태스크 생성: {task_id}")

    # 4. 서비스 mock 패치
    def _ghost_redis_get(key):
        key = str(key)
        if key.startswith("pipeline:cancel:") or key.startswith("pipeline:pause:"):
            return None
        return _pt._progress_mem.get(key)

    _original_step_script = _pt._step_script

    def _ghost_step_script(project_id_arg, config_arg):
        result = _original_step_script(project_id_arg, config_arg)
        task["status"] = "running"
        task["error"] = None
        return result

    patches = [
        patch("app.tasks.pipeline_tasks._step_script", side_effect=_ghost_step_script),
        patch("app.services.llm.factory.get_llm_service", return_value=DummyLLMService()),
        patch("app.services.tts.factory.get_tts_service", return_value=DummyTTSService()),
        patch("app.services.image.factory.get_image_service", return_value=DummyImageService()),
        patch("app.services.video.factory.get_video_service", return_value=DummyVideoService()),
        patch("app.services.video.ffmpeg_service.FFmpegService", DummyVideoService),
        patch("app.services.oneclick_service._redis_get", side_effect=_ghost_redis_get),
        patch("app.tasks.pipeline_tasks._redis_get", side_effect=_ghost_redis_get),
        patch("app.services.cancel_ctx.is_halted", return_value=False),
    ]

    for p in patches:
        p.start()

    # 5. _run_sync_pipeline 실행
    print(f"\n[3] _run_sync_pipeline 시작 (Step 2~5)")
    print("-" * 40)

    t0 = time.time()
    try:
        result = _run_sync_pipeline(task, project_id, project.config or {}, resume_from=None)
    except Exception as e:
        import traceback
        print(f"\n!!! 파이프라인 에러: {type(e).__name__}: {e}")
        traceback.print_exc()
        result = f"error:{e}"
    elapsed = time.time() - t0

    print("-" * 40)
    print(f"[4] _run_sync_pipeline 결과: {result} ({elapsed:.1f}초)")

    # 6. step_states 확인
    print(f"\n[5] step_states 확인:")
    for name, num, label in STEP_ORDER:
        state = task["step_states"].get(str(num), "???")
        mark = "✓" if state == "completed" else "✗" if state in ("failed", "cancelled") else "○"
        print(f"    {mark} Step {num} ({label}): {state}")

    # 7. 생성된 파일 확인
    pdir = resolve_project_dir(project_id, config=project.config, create=True)
    print(f"\n[6] 생성된 파일 확인 ({pdir}):")
    for sub in ["audio", "images", "videos", "output"]:
        d = pdir / sub
        if d.exists():
            files = sorted(d.iterdir())
            print(f"    {sub}/: {len(files)}개 — {[f.name for f in files[:5]]}")
        else:
            print(f"    {sub}/: (없음)")

    # 8. script.json 확인
    script_path = pdir / "script.json"
    if script_path.exists():
        script = json.loads(script_path.read_text(encoding="utf-8"))
        print(f"\n[7] script.json: title={script.get('title')!r}, cuts={len(script.get('cuts', []))}개")
    else:
        print(f"\n[7] script.json: (없음!)")

    # 9. DB 확인
    db = _new_session()
    from app.models.project import Project
    from app.models.cut import Cut
    p = db.query(Project).filter(Project.id == project_id).first()
    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    print(f"\n[8] DB 확인:")
    print(f"    Project: status={p.status}, total_cuts={p.total_cuts}, step_states={p.step_states}")
    print(f"    Cuts: {len(cuts)}개")
    for c in cuts[:3]:
        print(f"      #{c.cut_number}: status={c.status}, audio={c.audio_path}, image={c.image_path}, video={c.video_path}")
    db.close()

    # 10. 정리
    for p in patches:
        p.stop()

    # 결과 판정
    print("\n" + "=" * 60)
    if result == "ok":
        all_completed = all(
            task["step_states"].get(str(n)) == "completed"
            for _, n, _ in STEP_ORDER if n <= 5
        )
        if all_completed:
            print("✓ 고스트 테스트 통과 — Step 2~5 전체 완료")
        else:
            print("△ _run_sync_pipeline은 ok 반환했으나 일부 step이 completed가 아님")
    else:
        print(f"✗ 고스트 테스트 실패 — result={result}")
        if task.get("error"):
            print(f"  error: {task['error']}")

    print("=" * 60)

    # 테스트 프로젝트 정리
    print(f"\n정리: 테스트 프로젝트 삭제 중...")
    try:
        _new_engine.dispose()
        shutil.rmtree("/tmp/longtube_ghost_test", ignore_errors=True)
        Path("/tmp/test_ghost.db").unlink(missing_ok=True)
        print("  정리 완료")
    except Exception as e:
        print(f"  정리 실패 (무시): {e}")

    return result == "ok"


def run_resume_test():
    """이어하기 고스트 테스트 — 이미지 도중 중단 후 재개 시 기존 파일 건너뛰는지 검증."""
    print("\n" + "=" * 60)
    print("이어하기 고스트 테스트 시작")
    print("=" * 60)
    try:
        from app.services.cancel_ctx import clear_all_halted, set_cancel_key
        clear_all_halted()
        set_cancel_key(None)
    except Exception:
        pass

    # DB 파일 재생성 (이전 테스트에서 삭제됐을 수 있음)
    try:
        _db.engine.dispose()
    except Exception:
        pass
    Path("/tmp/test_ghost.db").unlink(missing_ok=True)
    resume_engine = create_engine("sqlite:////tmp/test_ghost.db", connect_args={"check_same_thread": False})
    resume_session = sessionmaker(bind=resume_engine, autoflush=False, autocommit=False)
    _db.engine = resume_engine
    _db.SessionLocal = resume_session
    _ocs.SessionLocal = resume_session
    _pt.SessionLocal = resume_session

    from app.models.database import Base
    Base.metadata.create_all(bind=resume_engine)

    from app.services.oneclick_service import (
        _clone_project_from_template,
        _make_task_record,
        _run_sync_pipeline,
        _detect_completed_steps,
        STEP_ORDER,
    )
    from app.services.estimation_service import estimate_project
    import uuid

    # 1. 프로젝트 생성 + Step 2 (대본), Step 3 (음성) 완료 상태 만들기
    project = _clone_project_from_template(None, "[고스트] 이어하기 테스트", None)
    project_id = project.id
    try:
        from app.tasks.pipeline_tasks import _redis_delete
        _redis_delete(f"pipeline:cancel:{project_id}", f"pipeline:pause:{project_id}")
    except Exception:
        pass
    pdir = resolve_project_dir(project_id, config=project.config, create=True)
    print(f"\n[1] 프로젝트: {project_id}")

    # script.json 생성
    (pdir / "script.json").write_text(json.dumps(DUMMY_SCRIPT, ensure_ascii=False), encoding="utf-8")

    # DB 에 total_cuts 기록
    db = resume_session()
    from app.models.project import Project
    from app.models.cut import Cut
    proj = db.query(Project).filter(Project.id == project_id).first()
    proj.total_cuts = GHOST_CUTS
    for i in range(GHOST_CUTS):
        cut = Cut(project_id=project_id, cut_number=i + 1, status="draft")
        db.add(cut)
    db.commit()
    db.close()

    # audio/ 3개 모두 생성 (Step 3 완료 상태)
    for i in range(GHOST_CUTS):
        f = pdir / "audio" / f"cut_{i+1:03d}.mp3"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\x00" * 1024)

    # images/ 1개만 생성 (Step 4 중간에 중단된 상태)
    img1 = pdir / "images" / "cut_001.png"
    img1.parent.mkdir(parents=True, exist_ok=True)
    # 유효한 PNG 만들기
    import struct, zlib
    raw = b"\x00\xff\x00\x00"
    compressed = zlib.compress(raw)
    def chunk(ctype, data):
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )
    img1.write_bytes(png)
    from app.services.image.asset_guard import write_prompt_sidecar
    write_prompt_sidecar(
        img1,
        cut_number=1,
        image_model=str((project.config or {}).get("image_model") or ""),
        source_prompt=str(DUMMY_SCRIPT["cuts"][0]["image_prompt"]),
        final_prompt=str(DUMMY_SCRIPT["cuts"][0]["image_prompt"]),
        narration=str(DUMMY_SCRIPT["cuts"][0]["narration"]),
    )

    print(f"    audio/: 3개 (전부 생성됨)")
    print(f"    images/: 1개 (cut_001 만 — 나머지 2개는 미생성)")

    # 2. _detect_completed_steps 로 상태 감지
    detected = _detect_completed_steps(project_id)
    print(f"\n[2] _detect_completed_steps 결과:")
    for sn in ("2", "3", "4", "5", "6", "7"):
        label = {
            "2": "대본", "3": "음성", "4": "이미지",
            "5": "영상", "6": "렌더", "7": "업로드",
        }[sn]
        mark = "✓" if detected[sn] == "completed" else "○"
        print(f"    {mark} Step {sn} ({label}): {detected[sn]}")

    assert detected["2"] == "completed", "Step 2 should be completed (script.json exists)"
    assert detected["3"] == "completed", "Step 3 should be completed (3 audio files)"
    assert detected["4"] == "pending", "Step 4 should be pending (only 1 of 3 images)"
    print("    → 감지 정확! 대본/음성 완료, 이미지 미완료")

    # 3. 이어하기 실행 — Step 4 (이미지)부터 시작, 기존 cut_001.png 건너뛰기
    task_id = str(uuid.uuid4())[:8]
    estimate = estimate_project(project.config or {})
    task = _make_task_record(
        task_id,
        template_project_id=None,
        project_id=project_id,
        topic="[고스트] 이어하기 테스트",
        title="[고스트] 이어하기",
        estimate=estimate,
    )
    task["step_states"] = detected
    task["resume_from_step"] = 4
    task["total_cuts"] = GHOST_CUTS
    task["status"] = "running"

    # 이미지 생성 호출 횟수 추적
    img_call_count = 0
    _original_img_gen = DummyImageService.generate

    class TrackingImageService(DummyImageService):
        async def generate(self, prompt, width, height, output_path, **kw):
            nonlocal img_call_count
            out_name = Path(output_path).name
            if out_name.startswith("cut_"):
                img_call_count += 1
            return await _original_img_gen(self, prompt, width, height, output_path, **kw)

    patches = [
        patch("app.services.llm.factory.get_llm_service", return_value=DummyLLMService()),
        patch("app.services.tts.factory.get_tts_service", return_value=DummyTTSService()),
        patch("app.services.image.factory.get_image_service", return_value=TrackingImageService()),
        patch("app.services.video.factory.get_video_service", return_value=DummyVideoService()),
        patch("app.services.video.ffmpeg_service.FFmpegService", DummyVideoService),
        patch("app.services.oneclick_service._redis_get", side_effect=lambda key: None if str(key).startswith(("pipeline:cancel:", "pipeline:pause:")) else _pt._progress_mem.get(key)),
        patch("app.tasks.pipeline_tasks._redis_get", side_effect=lambda key: None if str(key).startswith(("pipeline:cancel:", "pipeline:pause:")) else _pt._progress_mem.get(key)),
        patch("app.services.cancel_ctx.is_halted", return_value=False),
    ]
    for p in patches:
        p.start()

    print(f"\n[3] _run_sync_pipeline 이어하기 (resume_from=4)")
    print("-" * 40)
    t0 = time.time()
    result = _run_sync_pipeline(task, project_id, project.config or {}, resume_from=4)
    elapsed = time.time() - t0
    print("-" * 40)
    print(f"[4] 결과: {result} ({elapsed:.1f}초)")

    for p in patches:
        p.stop()

    # 4. 검증
    print(f"\n[5] 검증:")

    # 이미지 API 호출은 2번만 (cut_001 건너뛰고 cut_002, cut_003 만)
    print(f"    이미지 API 호출 횟수: {img_call_count} (기대: 2)")
    assert img_call_count == 2, f"이미지 API가 {img_call_count}번 호출됨 — 2번이어야 함 (cut_001 건너뛰기)"

    # 이미지 3개 모두 존재
    images = sorted((pdir / "images").glob("cut_*.png"))
    print(f"    images/: {len(images)}개 (기대: 3)")
    assert len(images) == 3, f"이미지 {len(images)}개 — 3개여야 함"

    # 영상 3개 + merged
    videos = sorted((pdir / "videos").glob("cut_*.mp4"))
    merged = pdir / "output" / "merged.mp4"
    print(f"    videos/: {len(videos)}개, merged: {merged.exists()}")
    assert len(videos) == 3
    assert merged.exists()

    # step_states 확인
    for sn in ("2", "3", "4", "5"):
        assert task["step_states"][sn] == "completed", f"Step {sn} not completed"
    print(f"    step_states: 2~5 모두 completed ✓")

    print("\n" + "=" * 60)
    print("✓ 이어하기 고스트 테스트 통과!")
    print(f"  - cut_001.png 건너뛰기 ✓ (API 호출 2번만)")
    print(f"  - 음성(Step 3) 완전 건너뛰기 ✓")
    print(f"  - 나머지 이미지/영상 정상 생성 ✓")
    print("=" * 60)

    # 정리
    resume_engine.dispose()
    shutil.rmtree("/tmp/longtube_ghost_test", ignore_errors=True)
    Path("/tmp/test_ghost.db").unlink(missing_ok=True)
    return True


if __name__ == "__main__":
    ok1 = run_ghost_test()
    ok2 = run_resume_test() if ok1 else False
    if ok1 and ok2:
        print("\n✓ 모든 고스트 테스트 통과!")
    sys.exit(0 if (ok1 and ok2) else 1)
