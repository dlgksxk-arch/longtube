"""v1.1.34 — '딸깍 제작' 서비스.

템플릿 프로젝트 1 개를 골라 topic 만 교체한 **새 프로젝트** 를 만들고,
대본 → 음성 → 이미지 → 영상 → 최종 렌더링까지 백그라운드로 직렬 실행한다.

설계 원칙
---------
1. **격리**: FastAPI 안의 `asyncio.create_task` 로 돈다. Celery 큐에 섞이지
   않아 사용자가 Studio 에서 다른 프로젝트를 손보는 동안 영향받지 않는다.
2. **상태는 in-memory + Redis**: 태스크 메타(제목/토픽/현재 단계/에러/시작시각)
   는 모듈 전역 `_TASKS` dict 에 둔다. 컷 단위 진행 카운터는 기존
   `pipeline:step_progress:{pid}:{step}` Redis 키를 그대로 쓴다.
3. **단계 함수 재사용**: `app.tasks.pipeline_tasks._step_*` 는 sync 함수.
   v1.1.51 부터 `_run_sync_pipeline` 에서 **단일 스레드** 순차 직접 호출한다.
   run_pipeline(Celery) 과 완전히 동일한 실행 환경. 이전 개별
   `asyncio.to_thread` 래핑은 이벤트 루프 불일치(TTS/FFmpeg 에러)의 근본
   원인이어서 제거. 최종 렌더 단계는 `routers/subtitle.py` 의
   `render_video_with_subtitles` (async) 를 직접 호출.
4. **업로드 제외**: 사용자는 "최종 렌더링까지" 라고 명시했다. YouTube 업로드는
   별도 스텝에서 수동으로 돌린다.
5. **서버 재시작 시 tasks 손실 허용**: oneclick 태스크는 단건 수명이 짧고, 복구
   로직을 넣으면 복잡도가 폭발한다. 재시작 시 in-flight 태스크는 "중단됨"
   으로 간주하고 사용자에게 다시 누르게 한다.

v1.1.38
-------
- 세밀한 진행률 노출: `current_step_completed` / `current_step_total` 을
  task dict 에 실시간 반영하여 UI 가 "N/M 컷" 을 표시할 수 있게 한다.

v1.1.42
-------
- 스케줄러(매일 HH:MM 자동 실행) 전면 삭제. 사용자 요구: "자동화 스케쥴
  삭제하고 그자리에 버튼 넣어". 딸깍은 이제 모달 팝업에서 주제/시간을
  즉시 입력해 순차 실행하는 "인스턴트" 경로만 남는다.
- `prepare_task` 가 `target_duration` 파라미터를 받아 모달의 "시간" 입력을
  새 프로젝트 config 에 반영한다.
- 클론된 딸깍 프로젝트는 `config["__oneclick__"] = True` 마커로 식별되며,
  projects.list 엔드포인트가 이 플래그가 켜진 행을 제외한다. 더이상 딸깍
  실행이 대시보드 프리셋 목록을 오염시키지 않는다.

v1.1.43
-------
- "딸깍제작 주제 입력 리스트 만들고 매일 몇시에 시작 할지 입력 할 수 있게해".
  스케줄을 다시 도입하되 **주제 큐(queue)** 형태로 재설계.
- 각 큐 항목은 `{id, topic, template_project_id, target_duration}` 를 가진다.
  주제마다 프리셋/길이 개별 지정 가능.
- 하루 1회, 사용자가 지정한 HH:MM 에 큐의 **맨 위 1건** 을 pop 해 실행.
  성공/실패 상관없이 pop on start (일회성 소비 시맨틱).
- 큐가 비면 조용히 대기 — 토글/알림 없음. 사용자가 채울 때까지 아무것도 안 함.
- 상태 영속화: `DATA_DIR / oneclick_queue.json`. 프로세스 재시작에도 복원.
- 중복 발화 방지: `last_run_date` (YYYY-MM-DD) 를 저장해 같은 날 두 번
  안 돌게 한다. 서버가 09:00 에 죽었다가 09:30 에 올라와도 오늘 아직 안
  돌았으면 catch-up 으로 즉시 발화.
- 즉시 실행 팝업(v1.1.42) 은 제거. 모달은 이제 큐 편집기 역할만 한다.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config import DATA_DIR
from app.models.database import SessionLocal
from app.models.project import Project
from app.services.estimation_service import estimate_project

# v1.1.52: pipeline_tasks 의 _redis_get 을 사용 — 인메모리 fallback 포함이라
# Redis 없어도 같은 프로세스 내에서 진행률을 정확히 읽는다.
from app.tasks.pipeline_tasks import _redis_get, _redis_delete


# --------------------------------------------------------------------------- #
# Task registry
# --------------------------------------------------------------------------- #

# task_id → dict[str, Any]
_TASKS: dict[str, dict[str, Any]] = {}

# v1.1.52: 태스크 상태 영속화 — 서버 재시작 후에도 실패/취소 태스크를 복원해서
# "이어서 하기" 가능하게 한다. running 중이던 태스크는 "interrupted" 로 표시.
_TASKS_FILE = Path(DATA_DIR) / "oneclick_tasks.json"


def _save_tasks_to_disk() -> None:
    """_TASKS 를 JSON 으로 영속화. running 태스크 중단 감지를 위해 상태 보존."""
    try:
        _TASKS_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 최근 50건만 보존 (오래된 completed 태스크는 버린다)
        recent = dict(list(_TASKS.items())[-50:])
        _TASKS_FILE.write_text(
            json.dumps(recent, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[oneclick] tasks save failed: {e}")


def _load_tasks_from_disk() -> None:
    """서버 시작 시 이전 태스크 복원. running 상태였던 건 interrupted 로 표시."""
    global _TASKS
    try:
        if not _TASKS_FILE.exists():
            _recover_orphaned_projects()
            return
        raw = json.loads(_TASKS_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            _recover_orphaned_projects()
            return
        for tid, task in raw.items():
            if not isinstance(task, dict):
                continue
            # running/queued 상태였으면 서버가 중간에 죽은 것 — failed 로 전환
            if task.get("status") in ("running", "queued"):
                task["status"] = "failed"
                task["error"] = "서버 재시작으로 중단됨"
                task["finished_at"] = task.get("finished_at") or _utcnow_iso()
                # 실제 파일 기반으로 완료된 스텝 재감지
                detected = _detect_completed_steps(task.get("project_id", ""))
                for sn, state in detected.items():
                    if state == "completed":
                        task.setdefault("step_states", {})[sn] = "completed"
            _TASKS[tid] = task
        print(f"[oneclick] {len(_TASKS)}개 태스크 복원 완료")
        # v1.1.56: 디스크에 있지만 _TASKS 에 없는 고아 프로젝트 자동 복구
        _recover_orphaned_projects()
    except Exception as e:
        print(f"[oneclick] tasks load failed: {e}")


def _recover_orphaned_projects() -> None:
    """v1.1.56: DB 에서 __oneclick__ 프로젝트 중 _TASKS 에 없는 것을 자동 복구.

    서버 재시작 시 자동 호출. 태스크 JSON 에서 유실된 딸깍 프로젝트를
    디스크 파일 기반으로 감지해서 태스크 목록에 다시 추가한다.
    """
    known_pids = {t.get("project_id") for t in _TASKS.values()}
    try:
        db = SessionLocal()
        try:
            # __oneclick__ 마커가 있는 프로젝트만 조회
            from sqlalchemy import text as sql_text
            candidates = (
                db.query(Project)
                .filter(Project.id.like("딸깍_%"))
                .order_by(Project.created_at.desc())
                .limit(100)
                .all()
            )
        finally:
            db.close()

        recovered = 0
        for proj in candidates:
            if proj.id in known_pids:
                continue
            # config 에 __oneclick__ 확인
            cfg = proj.config or {}
            if not cfg.get("__oneclick__"):
                continue

            # 생성물이 하나라도 있는 프로젝트만 복구 (빈 프로젝트는 무시)
            detected = _detect_completed_steps(proj.id)
            completed_count = sum(1 for v in detected.values() if v == "completed")
            if completed_count == 0:
                continue

            # 태스크 레코드 생성
            task_id = str(uuid.uuid4())[:8]
            estimate = estimate_project(cfg)
            task = _make_task_record(
                task_id,
                template_project_id=cfg.get("template_project_id"),
                project_id=proj.id,
                topic=proj.topic or "",
                title=proj.title or "",
                estimate=estimate,
                config=cfg,
            )
            task["step_states"] = detected

            # total_cuts 복원
            script_path = Path(DATA_DIR) / proj.id / "script.json"
            if script_path.exists():
                try:
                    script = json.loads(script_path.read_text(encoding="utf-8"))
                    task["total_cuts"] = len(script.get("cuts", []))
                except Exception:
                    pass

            # 첫 번째 미완료 스텝
            first_pending = None
            for _slug, step_num, _label in STEP_ORDER:
                if detected.get(str(step_num)) != "completed":
                    first_pending = step_num
                    break

            all_done = all(v == "completed" for v in detected.values())
            task["status"] = "completed" if all_done else "failed"
            task["error"] = None if all_done else "태스크 복구됨 — 이어서 하기를 눌러주세요"
            task["finished_at"] = _utcnow_iso() if all_done else None
            if first_pending:
                task["resume_from_step"] = first_pending

            _TASKS[task_id] = task
            recovered += 1
            completed_labels = [
                label for _slug, sn, label in STEP_ORDER
                if detected.get(str(sn)) == "completed"
            ]
            print(
                f"[oneclick] 고아 프로젝트 복구: {proj.id} "
                f"(완료: {', '.join(completed_labels)}, "
                f"다음: Step {first_pending or '모두완료'})"
            )

        if recovered > 0:
            _save_tasks_to_disk()
            print(f"[oneclick] 총 {recovered}개 고아 프로젝트 자동 복구 완료")
    except Exception as e:
        print(f"[oneclick] orphan recovery failed: {e}")
        import traceback
        traceback.print_exc()


# 동시성: 같은 프로세스에서 oneclick 여러 건이 동시에 돌면 GPU/FFmpeg 자원이
# 겹칠 수 있다. scheduler 와 동일한 보수적 정책 — 한 번에 하나만.
_RUN_LOCK = asyncio.Lock()

# v1.1.58: task_id → asyncio.Task 매핑. resume / start 가 중복으로 _run_oneclick_task
# 를 스케줄해서 _RUN_LOCK 에 영원히 갇히는 것을 막는다. 이전 인스턴스가 살아있으면
# 새로 스케줄하지 않는다(또는 끝날 때까지 짧게 기다린 뒤 새로 시작한다).
_ACTIVE_RUNS: dict[str, "asyncio.Task"] = {}

# Step 2~5 는 pipeline_tasks._step_* 가 담당, Step 6 은 subtitle.render 가 담당
STEP_ORDER = [
    ("script",  2, "대본 생성"),
    ("voice",   3, "음성 생성"),
    ("image",   4, "이미지 생성"),
    ("video",   5, "영상 생성"),
    ("render",  6, "최종 렌더링"),
    ("upload",  7, "유튜브 업로드"),
]

# UI 상 단계별 "총 진행률" 기여도 (합=100).
# render 는 컷 단위 카운터가 없어 고정 15% 를 부여하고 단계 시작/끝으로만 진행.
STEP_WEIGHTS = {
    2: 5,    # 대본 — 짧은 단일 호출
    3: 18,   # 음성 — 컷 수만큼 호출
    4: 32,   # 이미지 — 가장 무거움
    5: 23,   # 영상 — ffmpeg/AI 비디오
    6: 14,   # 렌더 — concat + 자막 + 페이드
    7: 8,    # 업로드 — 썸네일 생성 + YouTube 업로드
}


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _make_task_record(
    task_id: str,
    *,
    template_project_id: Optional[str],
    project_id: str,
    topic: str,
    title: str,
    estimate: dict,
    config: Optional[dict] = None,
) -> dict:
    # v1.1.52: 각 스텝에서 사용하는 AI 모델명을 task 에 포함 — UI 표시용
    cfg = config or {}
    models = {
        "script": cfg.get("script_model", ""),
        "tts": cfg.get("tts_model", ""),
        "tts_voice": cfg.get("tts_voice_id", ""),
        "image": cfg.get("image_model", ""),
        "video": cfg.get("video_model", ""),
        # v1.1.55: 썸네일 모델 — 프론트 드롭다운 기본값 용
        "thumbnail": cfg.get("thumbnail_model", ""),
    }
    return {
        "task_id": task_id,
        "template_project_id": template_project_id,
        "project_id": project_id,
        "topic": topic,
        "title": title,
        "status": "prepared",   # prepared | running | completed | failed | cancelled
        "current_step": None,
        "current_step_name": None,
        "step_states": {str(n): "pending" for _, n, _ in STEP_ORDER},
        "progress_pct": 0.0,
        "total_cuts": int(estimate.get("estimated_cuts") or 0),
        "completed_cuts_by_step": {str(n): 0 for _, n, _ in STEP_ORDER if n not in (6, 7)},
        # v1.1.38: 현재 실행 중 단계의 세부 컷 진행 상황 — UI 가 "N/M 컷" 표시.
        "current_step_completed": 0,
        "current_step_total": 0,
        "current_step_label": None,
        "estimate": estimate,
        "models": models,
        "error": None,
        "started_at": None,
        "finished_at": None,
        "created_at": _utcnow_iso(),
        "triggered_by": "manual",   # "manual" | "schedule"
    }


# --------------------------------------------------------------------------- #
# 공용 DB 헬퍼
# --------------------------------------------------------------------------- #

def _load_project(project_id: str) -> Optional[Project]:
    db = SessionLocal()
    try:
        return db.query(Project).filter(Project.id == project_id).first()
    finally:
        db.close()


def _detect_completed_steps(project_id: str) -> dict[str, str]:
    """v1.1.52: 프로젝트 디렉토리와 DB 를 스캔해서 실제 완료된 스텝을 감지한다.

    실패/중단된 프로젝트를 재사용할 때, 이미 만들어진 생성물이 있으면
    해당 스텝을 "completed" 로 표시해서 _run_sync_pipeline 이 건너뛸 수 있게 한다.

    반환: { "2": "completed", "3": "completed", "4": "pending", ... }
    """
    from app.models.cut import Cut

    project_dir = Path(DATA_DIR) / project_id
    states: dict[str, str] = {}

    # Step 2 (대본): script.json 존재 + cuts 배열 비어있지 않으면 완료
    script_path = project_dir / "script.json"
    script_ok = False
    total_cuts = 0
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            cuts = script.get("cuts", [])
            if cuts:
                script_ok = True
                total_cuts = len(cuts)
        except Exception:
            pass
    states["2"] = "completed" if script_ok else "pending"

    if not script_ok:
        # 대본도 없으면 나머지 다 pending
        for s in ("3", "4", "5", "6", "7"):
            states[s] = "pending"
        return states

    # Step 3 (음성): audio/ 폴더에 cut_NNN.mp3 파일이 total_cuts 만큼 있으면 완료
    audio_dir = project_dir / "audio"
    audio_count = sum(1 for f in audio_dir.glob("cut_*.mp3")) if audio_dir.exists() else 0
    states["3"] = "completed" if audio_count >= total_cuts else "pending"

    # Step 4 (이미지): images/ 폴더에 cut_NNN.png 파일이 total_cuts 만큼 있으면 완료
    image_dir = project_dir / "images"
    image_count = sum(1 for f in image_dir.glob("cut_*.png")) if image_dir.exists() else 0
    states["4"] = "completed" if image_count >= total_cuts else "pending"

    # Step 5 (영상): videos/ 폴더에 cut_NNN.mp4 파일이 total_cuts 만큼 있으면 완료
    # merged.mp4 는 렌더링(Step 6) 산출물이므로 Step 5 판정에서 제외
    video_dir = project_dir / "videos"
    video_count = sum(1 for f in video_dir.glob("cut_*.mp4")) if video_dir.exists() else 0
    states["5"] = "completed" if video_count >= total_cuts else "pending"

    # Step 6 (렌더): output/final_with_subtitles.mp4 또는 output/final.mp4 존재하면 완료
    final_sub = project_dir / "output" / "final_with_subtitles.mp4"
    final_old = project_dir / "output" / "final.mp4"
    states["6"] = "completed" if (final_sub.exists() or final_old.exists()) else "pending"

    # Step 7 (업로드): DB 의 youtube_url 있으면 완료
    db = SessionLocal()
    try:
        proj = db.query(Project).filter(Project.id == project_id).first()
        states["7"] = "completed" if (proj and proj.youtube_url) else "pending"
    finally:
        db.close()

    return states


def _find_reusable_project(
    template_project_id: Optional[str],
    topic: str,
) -> Optional[tuple[Project, dict[str, str]]]:
    """v1.1.52: 동일 주제로 이미 생성된 미완성 프로젝트가 있으면 반환한다.

    조건:
    1. topic 이 일치
    2. __oneclick__ 마커가 있음 (딸깍으로 만든 프로젝트)
    3. status 가 completed 가 아님 (이미 완성된 건 재사용 안 함)
    4. 스캔 결과 1개 이상의 스텝이 completed

    여러 개 있으면 가장 최근(id desc) 것을 사용한다.
    """
    db = SessionLocal()
    try:
        candidates = (
            db.query(Project)
            .filter(
                Project.topic == topic.strip(),
                Project.status != "completed",
            )
            .order_by(Project.created_at.desc())
            .limit(10)
            .all()
        )
        for proj in candidates:
            cfg = proj.config or {}
            if not cfg.get("__oneclick__"):
                continue
            # 생성물 스캔
            detected = _detect_completed_steps(proj.id)
            completed_count = sum(1 for v in detected.values() if v == "completed")
            if completed_count > 0:
                return (proj, detected)
        return None
    finally:
        db.close()


def _sanitize_for_filename(text: str, max_len: int = 30) -> str:
    """파일명에 안전한 문자만 남긴다. 한글/영문/숫자/하이픈/언더스코어 허용."""
    # 공백 → 언더스코어
    text = text.strip().replace(" ", "_")
    # 허용 문자만 남김 (한글, 영문, 숫자, 하이픈, 언더스코어)
    text = re.sub(r'[^\w가-힣-]', '', text, flags=re.UNICODE)
    return text[:max_len] or "Untitled"


def _generate_oneclick_project_id(topic: str, db) -> str:
    """v1.1.52: 딸깍_주제_YYMMDD-N 형식의 project_id 를 생성한다.

    같은 날짜에 이미 생성된 딸깍 프로젝트 수를 세서 순번(N)을 매긴다.
    예: 딸깍_AI로봇_260413-1, 딸깍_AI로봇_260413-2
    """
    safe_topic = _sanitize_for_filename(topic)
    date_str = datetime.now().strftime("%y%m%d")
    prefix = f"딸깍_{safe_topic}_{date_str}"

    # 같은 prefix 로 시작하는 기존 프로젝트 수 카운트
    existing = (
        db.query(Project.id)
        .filter(Project.id.like(f"{prefix}-%"))
        .all()
    )
    seq = len(existing) + 1
    project_id = f"{prefix}-{seq}"

    # 혹시 충돌하면 순번 올림
    while db.query(Project).filter(Project.id == project_id).first():
        seq += 1
        project_id = f"{prefix}-{seq}"

    return project_id


def _copy_template_assets(tmpl_dir: Path, dest_dir: Path, config: dict):
    """템플릿 프로젝트의 에셋 파일(레퍼런스/캐릭터/로고/간지)을 새 프로젝트 디렉토리에 복사.

    v1.1.52: config 에 상대 경로로 기록된 에셋 파일이 새 project_id
    디렉토리에도 물리적으로 존재해야 collect_reference_images /
    collect_character_images 가 제대로 동작한다.
    """
    import shutil

    # 1) config 에 기록된 상대 경로 기반 에셋 복사
    for key in ("reference_images", "character_images", "logo_images"):
        for rel in config.get(key, []) or []:
            src = tmpl_dir / rel
            dst = dest_dir / rel
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(str(src), str(dst))
                except Exception as e:
                    print(f"[oneclick] 에셋 복사 실패 {rel}: {e}")

    # 2) 간지(interlude) 디렉토리가 있으면 통째로 복사
    tmpl_interlude = tmpl_dir / "interlude"
    if tmpl_interlude.is_dir():
        dest_interlude = dest_dir / "interlude"
        try:
            shutil.copytree(str(tmpl_interlude), str(dest_interlude), dirs_exist_ok=True)
        except Exception as e:
            print(f"[oneclick] 간지 복사 실패: {e}")

    # 3) v1.1.55 hotfix: 프리셋에 연결된 YouTube 토큰을 클론으로 복사.
    # 프리셋(예: "무서운이야기")에 OAuth 인증한 youtube_token.json 이
    # tmpl_dir 에 있으면 클론에도 똑같이 깔아준다. 이게 빠지면 업로드 시
    # _step_youtube_upload 가 채널 기본값(CH1) 토큰으로 폴백해서
    # 전혀 다른 계정("제리스 아키오") 으로 올라가는 사고가 난다.
    src_token = tmpl_dir / "youtube_token.json"
    if src_token.exists():
        dst_token = dest_dir / "youtube_token.json"
        try:
            shutil.copy2(str(src_token), str(dst_token))
            print(f"[oneclick] 프리셋 YouTube 토큰 복사: {src_token.name}")
        except Exception as e:
            print(f"[oneclick] YouTube 토큰 복사 실패: {e}")


def _clone_project_from_template(
    template_project_id: Optional[str],
    topic: str,
    title: Optional[str],
    target_duration: Optional[int] = None,
) -> Project:
    """템플릿의 config 를 얕은 복사해 새 Project 를 만든다.

    template_project_id 가 None 이면 DEFAULT_CONFIG 사용.

    v1.1.42
    -------
    - `target_duration` (초) 이 지정되면 config 에 덮어쓴다. 딸깍 모달의
      "시간" 입력을 그대로 반영한다.
    - `config["__oneclick__"] = True` 마커를 심어 대시보드의 프리셋 목록에서
      자동 제외한다. 사용자 요구: "딸깍 셋팅하면 프리셋이 생성되네? 이럼
      안되지. 프리셋이 중요한거라고". 더 이상 딸깍 실행이 프리셋을 오염시키
      지 않는다. 실제 파이프라인 함수들은 Project 행이 DB 에 있어야 동작하
      므로 행 자체는 계속 만들되, UI 리스트에서만 숨긴다.
    """
    from app.routers.projects import DEFAULT_CONFIG

    db = SessionLocal()
    try:
        base_config: dict = dict(DEFAULT_CONFIG)
        if template_project_id:
            tmpl = (
                db.query(Project)
                .filter(Project.id == template_project_id)
                .first()
            )
            if tmpl and tmpl.config:
                base_config.update(tmpl.config)

        # oneclick 은 사용자 개입 없이 끝까지 달려야 한다.
        base_config["auto_pause_after_step"] = False

        # v1.1.42: 모달 "시간" 입력 반영
        if target_duration is not None:
            try:
                td = int(target_duration)
                if td > 0:
                    base_config["target_duration"] = td
            except (TypeError, ValueError):
                pass

        # v1.1.42: 프리셋 목록에서 숨길 마커
        base_config["__oneclick__"] = True

        clean_topic = (topic or "").strip() or "Untitled"
        clean_title = (title or "").strip() or clean_topic[:50]

        # v1.1.52: 딸깍_주제_YYMMDD-N 형식 project_id 생성
        project_id = _generate_oneclick_project_id(clean_topic, db)

        project = Project(
            id=project_id,
            title=clean_title,
            topic=clean_topic,
            config=base_config,
            status="draft",
        )
        db.add(project)
        db.commit()
        db.refresh(project)

        # 디렉토리 레이아웃 확보
        project_dir = Path(DATA_DIR) / project_id
        for sub in ["audio", "images", "videos", "subtitles", "output"]:
            (project_dir / sub).mkdir(parents=True, exist_ok=True)

        # v1.1.52: 템플릿의 에셋 파일을 새 프로젝트로 복사.
        # config 에 상대 경로로 기록된 레퍼런스/캐릭터/로고/간지(interlude)
        # 파일이 새 project_id 디렉토리에도 존재해야 collect_*_images 가
        # 파일을 찾을 수 있다.
        if template_project_id:
            tmpl_dir = Path(DATA_DIR) / template_project_id
            _copy_template_assets(tmpl_dir, project_dir, base_config)

        return project
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 진행률 계산
# --------------------------------------------------------------------------- #

def _compute_progress_pct(task: dict) -> float:
    """task 상태 + Redis 컷 카운터를 읽어 0~100 의 총 진행률을 계산.

    각 step_num 의 기여도(STEP_WEIGHTS) 는 완료 시 100% 더해지고, 실행 중인
    스텝은 (컷카운터 / 총 컷 수) 비율만큼 부분 가산된다. render(6) 만 컷 단위
    카운터가 없어 'running' 이면 0, 'completed' 면 풀 가산.

    v1.1.38: 부수효과로 task["current_step_completed/total/label"] 도 갱신하여
    UI 가 "N/M 컷" 표시를 바로 쓸 수 있게 한다.
    """
    project_id = task["project_id"]
    total_cuts = max(1, int(task.get("total_cuts") or 1))
    step_states = task.get("step_states") or {}
    # 현재 단계 세부 카운터 초기화 (running 인 스텝을 만나면 덮어씀)
    task["current_step_completed"] = 0
    task["current_step_total"] = 0
    task["current_step_label"] = None

    pct = 0.0
    running_labels = []  # v1.1.53: 병렬 실행 시 여러 라벨 수집
    for _name, step_num, label in STEP_ORDER:
        state = step_states.get(str(step_num), "pending")
        weight = STEP_WEIGHTS.get(step_num, 0)
        if state == "completed":
            pct += weight
            # 완료된 단계는 total 만큼 다 채워둔다 — UI 기록용
            task["completed_cuts_by_step"][str(step_num)] = (
                total_cuts if step_num != 6 else 0
            )
        elif state == "running":
            if step_num == 6:
                # 렌더링은 컷 단위 카운터가 없음 — 단계 라벨만 노출
                running_labels.append(label)
                task["current_step_completed"] = 0
                task["current_step_total"] = 0
                continue
            if step_num == 2:
                # v1.1.53: 대본은 단건 LLM 호출이라 컷 단위 진행이 없음
                # running 중이면 가중치의 50% 부여 (생성 중 표시)
                pct += weight * 0.5
                task["current_step_completed"] = 0
                task["current_step_total"] = 0
                running_labels.append(label)
                continue
            raw = _redis_get(f"pipeline:step_progress:{project_id}:{step_num}")
            try:
                completed = int(raw) if raw else 0
            except (TypeError, ValueError):
                completed = 0
            task["completed_cuts_by_step"][str(step_num)] = completed
            ratio = min(1.0, completed / total_cuts)
            pct += weight * ratio
            task["current_step_completed"] = completed
            task["current_step_total"] = int(task.get("total_cuts") or 0)
            running_labels.append(label)
    # v1.1.53: 병렬 실행 시 "음성 생성 + 이미지 생성" 으로 표시
    task["current_step_label"] = " + ".join(running_labels) if running_labels else None
    return round(min(100.0, pct), 1)


# --------------------------------------------------------------------------- #
# Step 7: 썸네일 생성 + 유튜브 업로드
# --------------------------------------------------------------------------- #

async def _step_youtube_upload(
    project_id: str,
    config: dict,
    channel: Optional[int] = None,
) -> None:
    """썸네일을 자동 생성하고 YouTube 에 업로드한다.

    channel (1~4) 가 지정되면 채널별 OAuth 토큰을 우선 사용한다.
    채널 토큰이 없으면 프로젝트 토큰 → 전역 토큰 순으로 폴백.
    """
    from app.services.thumbnail_service import generate_ai_thumbnail
    from app.services.youtube_service import YouTubeUploader, YouTubeAuthError, YouTubeUploadError
    from pathlib import Path

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise RuntimeError("project not found")

        # 1) 썸네일 자동 생성 (AI overlay 모드)
        # v1.1.55: script.json 에서 LLM 이 생성한 title 을 우선 사용
        script_path_t = Path(DATA_DIR) / project_id / "script.json"
        script_title = ""
        if script_path_t.exists():
            try:
                with open(script_path_t, "r", encoding="utf-8") as f:
                    _sd = json.load(f)
                script_title = (_sd.get("title") or "").strip()
            except Exception:
                pass
        title = script_title or (project.title or project.topic or "Untitled").strip()

        thumb_dir = Path(DATA_DIR) / project_id / "output"
        thumb_path = thumb_dir / "thumbnail.png"

        if not thumb_path.exists():
            try:
                image_model = config.get("thumbnail_model") or config.get("image_model") or "openai-image-1"
                # script.json 에서 thumbnail_prompt 를 가져온다
                thumb_prompt = "YouTube thumbnail: " + title
                if script_path_t.exists():
                    try:
                        with open(script_path_t, "r", encoding="utf-8") as f:
                            script_data = json.load(f)
                        tp = script_data.get("thumbnail_prompt") or ""
                        if tp.strip():
                            thumb_prompt = tp.strip()
                    except Exception:
                        pass

                result = await generate_ai_thumbnail(
                    project_id=project_id,
                    image_prompt=thumb_prompt,
                    image_model_id=image_model,
                    overlay_title_text=title,
                )
                print(f"[oneclick] thumbnail generated: {result.get('path')}")
            except Exception as e:
                import traceback
                # 썸네일 실패해도 업로드는 진행 (썸네일 없이)
                print(f"[oneclick] thumbnail generation FAILED (continuing without): {e}\n{traceback.format_exc()}")

        # 2) YouTube 업로드
        final_video = thumb_dir / "final_with_subtitles.mp4"
        if not final_video.exists():
            # merged.mp4 폴백
            final_video = thumb_dir / "merged.mp4"
        if not final_video.exists():
            raise RuntimeError("최종 영상 파일이 없습니다.")

        # v1.1.60 → v1.1.55 hotfix: 채널 결정 우선순위 재정렬.
        # **프리셋의 youtube_channel 이 항상 최우선** 이다. 큐 row 의 channel 은
        # 사용자가 UI 에서 명시 선택하지 않으면 _queue_normalize 가 1 로 기본값을
        # 박는데, 그 기본값 1 이 프리셋의 실제 채널을 덮어써서 "무서운이야기"
        # 프리셋이 CH1(=다른 계정) 으로 잘못 업로드되던 사고가 났다.
        # 이제는:
        #   1. config["youtube_channel"]  (프리셋 — 가장 신뢰도 높음)
        #   2. 호출 시 명시한 channel (큐 row)
        # 두 값이 충돌하면 프리셋 우선 + 경고 로그.
        ch_int: Optional[int] = None
        cfg_ch_raw = config.get("youtube_channel")
        cfg_ch_int: Optional[int] = None
        if cfg_ch_raw is not None and str(cfg_ch_raw).strip() != "":
            try:
                cfg_ch_int = int(cfg_ch_raw)
            except Exception:
                cfg_ch_int = None
        queue_ch_int: Optional[int] = None
        if channel is not None:
            try:
                queue_ch_int = int(channel)
            except Exception:
                queue_ch_int = None
        if cfg_ch_int is not None:
            ch_int = cfg_ch_int
            if queue_ch_int is not None and queue_ch_int != cfg_ch_int:
                print(
                    f"[oneclick] ⚠ 채널 충돌: 큐 row 는 CH{queue_ch_int}, "
                    f"프리셋 youtube_channel 은 CH{cfg_ch_int} → 프리셋 우선 적용. "
                    f"(과거에는 큐 row 가 이겨서 잘못된 계정으로 업로드되던 사고)"
                )
        else:
            ch_int = queue_ch_int

        # v1.1.55 hotfix: **프로젝트 토큰이 최우선**.
        # _copy_template_assets 가 프리셋의 youtube_token.json 을 클론으로
        # 복사해주므로, 프리셋에 직접 연결한 계정이 그대로 따라온다.
        # 이게 있으면 채널 기본값(CH1=다른 계정) 으로 잘못 폴백하던 사고를
        # 차단할 수 있다.
        # 우선순위: 프로젝트별 → 채널별 → 전역
        uploader = None
        project_uploader = YouTubeUploader(project_id=project_id)
        if project_uploader.is_authenticated():
            uploader = project_uploader
            print(f"[oneclick] using project-bound YouTube token ({project_id})")
        elif ch_int is not None:
            ch_uploader = YouTubeUploader(channel_id=ch_int)
            if ch_uploader.is_authenticated():
                uploader = ch_uploader
                print(f"[oneclick] using channel {ch_int} YouTube token")
            else:
                # v1.1.60: 프리셋이 채널을 명시했는데 그 채널이 인증 안 된 상태라면
                # 잘못된 계정으로 올라가는 사고를 막기 위해 즉시 실패시킨다.
                raise RuntimeError(
                    f"CH{ch_int} YouTube 인증이 안 되어 있습니다. "
                    f"딸깍 위젯 → 채널별 YouTube 계정 → CH{ch_int} '연결' 을 먼저 해 주세요. "
                    f"(다른 계정 토큰으로 잘못 업로드되는 것을 막기 위해 업로드를 중단합니다.)"
                )
        if uploader is None:
            uploader = YouTubeUploader()

        if not uploader.is_authenticated():
            raise RuntimeError(
                "YouTube 인증이 설정되지 않았습니다. "
                "먼저 해당 채널의 YouTube 인증을 완료해주세요."
            )

        # v1.1.55: script.json 에서 description/tags 를 가져와서 config 폴백보다 우선
        script_description = ""
        script_tags: list[str] = []
        script_path = Path(DATA_DIR) / project_id / "script.json"
        if script_path.exists():
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    script_data = json.load(f)
                script_description = (script_data.get("description") or "").strip()
                raw_tags = script_data.get("tags") or []
                if isinstance(raw_tags, list):
                    script_tags = [t.strip() for t in raw_tags if isinstance(t, str) and t.strip()]
            except Exception:
                pass

        # 우선순위: config(프리셋) > script.json(LLM생성) > project.topic(폴백)
        description = (
            (config.get("youtube_description") or "").strip()
            or script_description
            or (project.topic or "").strip()
        )
        config_tags = [t.strip() for t in (config.get("youtube_tags") or "").split(",") if t.strip()] if config.get("youtube_tags") else []
        tags = config_tags if config_tags else script_tags
        privacy = config.get("youtube_privacy") or "private"
        print(f"[oneclick] YouTube upload: privacy={privacy}, desc_len={len(description)}, tags={len(tags)}, thumb={thumb_path.exists()}")

        use_thumb = thumb_path.exists()
        result = await asyncio.to_thread(
            uploader.upload,
            str(final_video),
            title,
            description,
            tags,
            str(thumb_path) if use_thumb else None,
            privacy,
            config.get("language") or "ko",
            None,   # category_id
            False,  # made_for_kids
            None,   # progress_callback
        )

        video_url = result.get("url")
        if video_url:
            project.youtube_url = video_url
            # step_states 7 = completed
            ss = dict(project.step_states or {})
            ss["7"] = "completed"
            project.step_states = ss
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "step_states")
            db.commit()
            print(f"[oneclick] YouTube uploaded: {video_url}")
        else:
            raise RuntimeError(f"업로드 성공했으나 URL 이 비어있습니다: {result!r}")
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 실제 실행 코루틴
# --------------------------------------------------------------------------- #

def _run_sync_pipeline(task: dict, project_id: str, config: dict, resume_from) -> str:
    """Step 2~5 를 실행. v1.1.53: step 3(음성) + step 4(이미지)를 병렬 실행.

    대본(2) → 음성+이미지(3+4 병렬) → 영상(5)
    음성과 이미지는 서로 의존 관계가 없으므로 ThreadPoolExecutor 로 동시 실행한다.
    개별 step 내부는 여전히 단일 스레드 → 단일 이벤트 루프로 동작하여
    httpx transport, subprocess 핸들링 안정성은 유지된다.

    반환값: "ok" | "cancelled" | "failed:{에러메시지}"
    task dict 의 step_states/status 등은 이 함수 안에서 직접 갱신한다.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from app.tasks.pipeline_tasks import (
        _step_script,
        _step_voice,
        _step_image,
        _step_video,
        init_progress,
        PipelineCancelled,
    )

    all_steps = [
        (2, _step_script, "대본 생성"),
        (3, _step_voice,  "음성 생성"),
        (4, _step_image,  "이미지 생성"),
        (5, _step_video,  "영상 생성"),
    ]

    def _should_skip(step_num):
        """resume 모드에서 이미 완료된 단계 건너뛰기"""
        if resume_from is not None and step_num < resume_from:
            return task["step_states"].get(str(step_num)) == "completed"
        return False

    def _check_cancel():
        if task.get("status") == "cancelled":
            return True
        return False

    def _run_single_step(step_num, func, label):
        """단일 스텝 실행. 예외는 그대로 raise."""
        task["current_step"] = step_num
        task["current_step_name"] = label
        task["step_states"][str(step_num)] = "running"
        try:
            init_progress(project_id, step_num)
        except Exception:
            pass
        func(project_id, config)
        task["step_states"][str(step_num)] = "completed"
        _save_tasks_to_disk()

    def _cleanup_cancel_key():
        """v1.1.53: 파이프라인 종료 시 cancel 키 정리"""
        try:
            _redis_delete(f"pipeline:cancel:{project_id}")
        except Exception:
            pass

    def _handle_cancel(step_num, label, e=None):
        msg = e or "사용자 취소"
        print(f"[oneclick] step {label} CANCELLED: {msg}")
        task["step_states"][str(step_num)] = "cancelled"
        task["status"] = "cancelled"
        task["error"] = task.get("error") or "사용자 취소"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "cancelled")
        # v1.1.55: cancel 키를 여기서 삭제하지 않는다.
        # 병렬 실행 시 다른 스레드가 아직 돌고 있을 수 있으므로
        # cancel 키는 _run_sync_pipeline 의 최종 반환 직전에만 정리한다.
        return "cancelled"

    def _handle_fail(step_num, label, e):
        tb = traceback.format_exc()
        print(f"[oneclick] step {label} FAILED: {e}\n{tb}")
        task["step_states"][str(step_num)] = "failed"
        task["status"] = "failed"
        task["error"] = f"{label} 실패: {type(e).__name__}: {e}"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "failed")
        _save_tasks_to_disk()
        return f"failed:{task['error']}"

    # ── Step 2: 대본 (순차) ──
    step2 = all_steps[0]  # (2, _step_script, "대본 생성")
    if not _should_skip(2):
        if _check_cancel():
            _cleanup_cancel_key()
            return _handle_cancel(2, "대본 생성")
        try:
            _run_single_step(*step2)
        except PipelineCancelled as e:
            _cleanup_cancel_key()
            return _handle_cancel(2, "대본 생성", e)
        except Exception as e:
            return _handle_fail(2, "대본 생성", e)

    # step 2 끝나면 total_cuts 결정 — task 에 반영
    fresh = _load_project(project_id)
    if fresh and fresh.total_cuts:
        task["total_cuts"] = int(fresh.total_cuts)

    # ── Step 3+4: 음성 + 이미지 (병렬) ──
    skip_3 = _should_skip(3)
    skip_4 = _should_skip(4)
    parallel_targets = []
    if not skip_3:
        parallel_targets.append(all_steps[1])  # (3, _step_voice, "음성 생성")
    if not skip_4:
        parallel_targets.append(all_steps[2])  # (4, _step_image, "이미지 생성")

    if parallel_targets:
        if _check_cancel():
            return _handle_cancel(3, "음성+이미지")

        if len(parallel_targets) == 2:
            # ★ 병렬 실행
            print(f"[oneclick] ★ 음성(3) + 이미지(4) 병렬 실행 시작")
            # v1.1.58: parallel 진입 시 current_step / current_step_name 을 갱신.
            # 이전에는 step 2 의 마지막 값("대본 생성")이 그대로 박혀 있어 UI 가
            # "현재 단계: 대본 생성 100%" 로만 보이고 음성/이미지 진행이 시각적으로
            # 묻혔다. (사용자 신고: "초기화 후 이어서 하기 반응 없다")
            task["current_step"] = 3
            task["current_step_name"] = "음성+이미지 생성 (병렬)"
            errors = {}

            def _thread_run(step_num, func, label):
                try:
                    task["step_states"][str(step_num)] = "running"
                    try:
                        init_progress(project_id, step_num)
                    except Exception:
                        pass
                    func(project_id, config)
                    task["step_states"][str(step_num)] = "completed"
                    _save_tasks_to_disk()
                    print(f"[oneclick] ★ {label} 완료")
                except PipelineCancelled:
                    raise
                except Exception:
                    raise

            # v1.1.55: cancel 키를 삭제하지 않고 유지하므로, 병렬 스레드들이
            # 각자 check_pause_or_cancel 에서 cancel 을 감지하고 종료한다.
            # wait=True 로 모든 스레드가 실제 종료될 때까지 대기한 후 반환.
            pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="step")
            cancel_result = None
            try:
                futures = {
                    pool.submit(_thread_run, sn, fn, lb): (sn, lb)
                    for sn, fn, lb in parallel_targets
                }
                for fut in as_completed(futures):
                    sn, lb = futures[fut]
                    try:
                        fut.result()
                    except PipelineCancelled as e:
                        if not cancel_result:
                            cancel_result = _handle_cancel(sn, lb, e)
                        # break 하지 않고 나머지 future 도 수거한다.
                        # cancel 키가 살아있으므로 다른 스레드도 곧 종료된다.
                    except Exception as e:
                        if cancel_result:
                            pass  # cancel 중 발생한 부수 에러는 무시
                        else:
                            errors[sn] = (lb, e)
            finally:
                pool.shutdown(wait=True, cancel_futures=True)

            if cancel_result:
                _cleanup_cancel_key()
                return cancel_result

            if errors:
                first_sn = min(errors.keys())
                lb, e = errors[first_sn]
                return _handle_fail(first_sn, lb, e)
        else:
            # 하나만 실행 (resume 시 한쪽만 남은 경우)
            sn, fn, lb = parallel_targets[0]
            try:
                _run_single_step(sn, fn, lb)
            except PipelineCancelled as e:
                _cleanup_cancel_key()
                return _handle_cancel(sn, lb, e)
            except Exception as e:
                return _handle_fail(sn, lb, e)

    # ── Step 5: 영상 (순차) ──
    if not _should_skip(5):
        if _check_cancel():
            _cleanup_cancel_key()
            return _handle_cancel(5, "영상 생성")
        try:
            _run_single_step(*all_steps[3])  # (5, _step_video, "영상 생성")
        except PipelineCancelled as e:
            _cleanup_cancel_key()
            return _handle_cancel(5, "영상 생성", e)
        except Exception as e:
            return _handle_fail(5, "영상 생성", e)

    _cleanup_cancel_key()
    return "ok"


def _ensure_thumbnail_before_render(project_id: str, config: dict):
    """v1.1.57: 렌더링(Step 6) 전에 썸네일이 없으면 자동 생성.

    resume 등으로 Step 6 부터 시작할 때 썸네일이 누락된 경우를 방지한다.
    실패해도 렌더링은 계속 진행한다 (썸네일은 필수가 아님).
    """
    from app.tasks.pipeline_tasks import load_script, _generate_thumbnail_sync, _redis_set

    thumb_path = DATA_DIR / project_id / "output" / "thumbnail.png"
    if thumb_path.exists() and thumb_path.stat().st_size > 100:
        print(f"[oneclick] 썸네일 이미 존재 — 건너뜀: {thumb_path}")
        # v1.1.60: Redis 상태도 done 으로 동기화 — 안 그러면 UI 가 'waiting'
        # 으로 남아서 렌더 단계에서 미리보기가 안 뜬다 (resume 케이스).
        _redis_set(f"thumbnail:status:{project_id}", "done")
        return

    print(f"[oneclick] 썸네일 없음 — 렌더링 전에 자동 생성 시작: {project_id}")
    try:
        script = load_script(project_id)
        if script:
            _generate_thumbnail_sync(project_id, config, script)
            print(f"[oneclick] 썸네일 자동 생성 완료: {project_id}")
        else:
            print(f"[oneclick] script.json 없음 — 썸네일 생성 불가")
            _redis_set(f"thumbnail:status:{project_id}", "failed:script.json 없음")
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}"
        print(f"[oneclick] 썸네일 자동 생성 실패 (렌더링은 계속): {err_msg}")
        _redis_set(f"thumbnail:status:{project_id}", f"failed:{err_msg[:300]}")


def _schedule_oneclick_run(task_id: str) -> None:
    """v1.1.58: _run_oneclick_task 를 안전하게 스케줄한다.

    같은 task_id 의 이전 인스턴스가 아직 살아있으면(예: 사용자가 중지를 눌렀지만
    내부 LLM/TTS 호출이 끝나지 않아 _RUN_LOCK 을 들고 있는 경우), 그것을 cancel
    하고 새 인스턴스를 띄운다. 이 가드가 없으면 새 _run_oneclick_task 가 _RUN_LOCK
    에서 영원히 대기해 UI 가 "queued" 로 멎는다.
    """
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        # 1) 백그라운드 스레드(_run_sync_pipeline) 가 다음 체크포인트에서 종료되도록
        #    Redis cancel 플래그를 세운다. asyncio Task 만 cancel 하면 thread 는
        #    살아남아 새 인스턴스와 동시에 같은 프로젝트를 건드릴 수 있다.
        task = _TASKS.get(task_id)
        pid = task.get("project_id") if task else None
        if pid:
            try:
                from app.tasks.pipeline_tasks import _redis_set
                _redis_set(f"pipeline:cancel:{pid}", "1")
            except Exception:
                pass
        # 2) 코루틴을 cancel — `async with _RUN_LOCK` 블록이 풀리며 락이 즉시 반환된다.
        try:
            prev.cancel()
            print(f"[oneclick] 이전 _run_oneclick_task({task_id}) 를 취소합니다 — 새 실행 스케줄")
        except Exception as e:
            print(f"[oneclick] 이전 task 취소 실패: {e}")
    loop = asyncio.get_running_loop()

    async def _delayed_start():
        # 3) 잠깐 대기 후 cancel 플래그를 비우고 본 작업 시작 — 잔존 스레드가
        #    새 작업의 cancel 플래그를 자기 것으로 오인하지 않게 한다.
        if prev is not None:
            try:
                await asyncio.sleep(1.0)
            except Exception:
                pass
            task = _TASKS.get(task_id)
            pid = task.get("project_id") if task else None
            if pid:
                try:
                    from app.tasks.pipeline_tasks import _redis_set
                    _redis_set(f"pipeline:cancel:{pid}", "")
                except Exception:
                    pass
        await _run_oneclick_task(task_id)

    new_task = loop.create_task(_delayed_start())
    _ACTIVE_RUNS[task_id] = new_task

    def _cleanup(t):
        if _ACTIVE_RUNS.get(task_id) is t:
            _ACTIVE_RUNS.pop(task_id, None)

    new_task.add_done_callback(_cleanup)


async def _run_oneclick_task(task_id: str) -> None:
    """단일 oneclick task 를 끝까지 실행. 실패/성공 모두 task 상태를 갱신.

    v1.1.51: Step 2~5 를 _run_sync_pipeline() 에서 **단일 스레드** 순차 직접
    호출로 변경. 스튜디오의 run_pipeline(Celery) 과 완전히 동일한 실행 환경을
    보장한다. 이전 버전의 개별 asyncio.to_thread 래핑이 TTS, FFmpeg 등 모든
    에러의 근본 원인이었다.
    """
    from app.routers.subtitle import render_video_with_subtitles

    task = _TASKS.get(task_id)
    if not task:
        return

    project_id = task["project_id"]
    project = _load_project(project_id)
    if not project:
        task["status"] = "failed"
        task["error"] = "project not found (삭제되었거나 생성 실패)"
        task["finished_at"] = _utcnow_iso()
        return

    config = dict(project.config or {})
    config["auto_pause_after_step"] = False

    async with _RUN_LOCK:
        if task.get("status") == "cancelled":
            return

        task["status"] = "running"
        if not task.get("started_at"):
            task["started_at"] = _utcnow_iso()

        resume_from = task.pop("resume_from_step", None)

        if resume_from is not None and resume_from > 2:
            fresh = _load_project(project_id)
            if fresh and fresh.total_cuts:
                task["total_cuts"] = int(fresh.total_cuts)

        # --- Step 2~5: 단일 스레드에서 직접 호출 (run_pipeline 과 동일) ---
        result = await asyncio.to_thread(
            _run_sync_pipeline, task, project_id, config, resume_from
        )
        if result != "ok":
            return  # cancelled 또는 failed — _run_sync_pipeline 이 상태 갱신 완료

        # v1.1.48: 영상 단계 끝난 직후에도 cancel 확인 — 렌더링은 오래 걸리니
        # 중간 인터럽트는 불가능해도 진입 자체를 막을 수는 있다.
        if task.get("status") == "cancelled":
            task["step_states"]["6"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = task.get("finished_at") or _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return

        # --- Step 6: 최종 렌더링 (router handler 직접 호출) ---
        # v1.1.49: resume 모드에서 이미 완료된 6단계는 건너뛴다.
        if task["step_states"].get("6") == "completed":
            task["current_step"] = None
            task["current_step_name"] = None
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "completed")
            return

        # v1.1.57: 렌더링 전 썸네일 없으면 자동 생성
        # _generate_thumbnail_sync 내부에서 run_async() 를 쓰므로
        # 이벤트 루프 충돌을 피하기 위해 별도 스레드에서 실행한다.
        await asyncio.to_thread(_ensure_thumbnail_before_render, project_id, config)

        task["current_step"] = 6
        task["current_step_name"] = "최종 렌더링"
        task["step_states"]["6"] = "running"
        try:
            db = SessionLocal()
            try:
                await render_video_with_subtitles(project_id, db=db)
            finally:
                db.close()
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[oneclick] step 최종 렌더링 FAILED: {e}\n{tb}")
            task["step_states"]["6"] = "failed"
            task["status"] = "failed"
            task["error"] = f"최종 렌더링 실패: {type(e).__name__}: {e}"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "failed")
            return

        task["step_states"]["6"] = "completed"

        # --- Step 7: 썸네일 생성 + 유튜브 업로드 ---
        # v1.1.49: resume 모드에서 이미 완료된 7단계는 건너뛴다.
        if task.get("status") == "cancelled":
            task["step_states"]["7"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = task.get("finished_at") or _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return

        if task["step_states"].get("7") == "completed":
            task["current_step"] = None
            task["current_step_name"] = None
            task["status"] = "completed"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "completed")
            return

        task["current_step"] = 7
        task["current_step_name"] = "유튜브 업로드"
        task["step_states"]["7"] = "running"
        try:
            await _step_youtube_upload(project_id, config, channel=task.get("channel"))
        except PipelineCancelled as e:
            print(f"[oneclick] step 유튜브 업로드 CANCELLED by user: {e}")
            task["step_states"]["7"] = "cancelled"
            task["status"] = "cancelled"
            task["error"] = task.get("error") or "사용자 취소"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "cancelled")
            return
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[oneclick] step 유튜브 업로드 FAILED: {e}\n{tb}")
            task["step_states"]["7"] = "failed"
            task["status"] = "failed"
            task["error"] = f"유튜브 업로드 실패: {type(e).__name__}: {e}"
            task["finished_at"] = _utcnow_iso()
            _update_project_status(project_id, "failed")
            return

        task["step_states"]["7"] = "completed"
        task["current_step"] = None
        task["current_step_name"] = None
        task["status"] = "completed"
        task["finished_at"] = _utcnow_iso()
        _update_project_status(project_id, "completed")
        _save_tasks_to_disk()


def _update_project_status(project_id: str, status: str) -> None:
    db = SessionLocal()
    try:
        p = db.query(Project).filter(Project.id == project_id).first()
        if p:
            p.status = status
            db.commit()
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# Public API (routers/oneclick.py 에서 호출)
# --------------------------------------------------------------------------- #

def prepare_task(
    *,
    template_project_id: Optional[str],
    topic: str,
    title: Optional[str] = None,
    target_duration: Optional[int] = None,
) -> dict:
    """프로젝트 준비 + task 레코드 생성. 아직 실행은 안 함.

    v1.1.52: **기존 미완성 프로젝트 자동 감지** — 동일 주제로 이미 생성된
    프로젝트가 있고, 1개 이상의 스텝이 완료됐으면 새로 만들지 않고 재사용한다.
    완료된 스텝은 step_states 에 "completed" 로 표시해서 _run_sync_pipeline 이
    자동으로 건너뛴다. 실패해도 만들어진 생성물은 보존된다.

    v1.1.42: `target_duration` (초) 을 받아 clone 시 config 에 반영.
    """
    # ── 기존 미완성 프로젝트 재사용 시도 ──
    reusable = _find_reusable_project(template_project_id, topic)
    if reusable:
        project, detected_states = reusable

        # v1.1.57: 재사용 시 현재 프리셋(template) 의 config 로 갱신한다.
        # 이전에는 생성 당시의 옛 config (예: language=ko) 가 그대로 박혀
        # 있어서, 사용자가 프리셋을 English 로 바꾸고 재실행해도 한국어로
        # 대본이 나오는 버그가 있었다. 단, 이미 완료된 스텝의 결과물(스크립트
        # 파일 등)은 그대로 두고, 앞으로 실행될 스텝에만 새 config 가 적용된다.
        try:
            from app.routers.projects import DEFAULT_CONFIG
            db_refresh = SessionLocal()
            try:
                base = dict(DEFAULT_CONFIG)
                if template_project_id:
                    tmpl = (
                        db_refresh.query(Project)
                        .filter(Project.id == template_project_id)
                        .first()
                    )
                    if tmpl and tmpl.config:
                        base.update(tmpl.config)
                # __oneclick__ 마커 유지 + 기존 target_duration 보존
                base["__oneclick__"] = True
                base["auto_pause_after_step"] = False
                old_cfg = dict(project.config or {})
                if target_duration is not None:
                    try:
                        td = int(target_duration)
                        if td > 0:
                            base["target_duration"] = td
                    except (TypeError, ValueError):
                        pass
                elif old_cfg.get("target_duration"):
                    base["target_duration"] = old_cfg["target_duration"]

                proj_in_db = (
                    db_refresh.query(Project)
                    .filter(Project.id == project.id)
                    .first()
                )
                if proj_in_db:
                    proj_in_db.config = base
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(proj_in_db, "config")
                    db_refresh.commit()
                    db_refresh.refresh(proj_in_db)
                    project = proj_in_db
            finally:
                db_refresh.close()
        except Exception as e:
            print(f"[oneclick] 재사용 프로젝트 config 갱신 실패: {e}")

        # 첫 번째 미완료 스텝 찾기
        first_pending = None
        for _slug, step_num, _label in STEP_ORDER:
            if detected_states.get(str(step_num)) != "completed":
                first_pending = step_num
                break

        task_id = str(uuid.uuid4())[:8]
        estimate = estimate_project(project.config or {})
        task = _make_task_record(
            task_id,
            template_project_id=template_project_id,
            project_id=project.id,
            topic=project.topic,
            title=project.title,
            estimate=estimate,
            config=project.config,
        )
        # 감지된 완료 상태 반영
        task["step_states"] = detected_states
        if first_pending:
            task["resume_from_step"] = first_pending

        # total_cuts 복원
        fresh = _load_project(project.id)
        if fresh and fresh.total_cuts:
            task["total_cuts"] = int(fresh.total_cuts)

        completed_labels = [
            label for _slug, sn, label in STEP_ORDER
            if detected_states.get(str(sn)) == "completed"
        ]
        print(
            f"[oneclick] 기존 프로젝트 재사용: {project.id} "
            f"(완료: {', '.join(completed_labels)}, "
            f"이어하기: Step {first_pending}부터)"
        )
        _TASKS[task_id] = task
        _save_tasks_to_disk()
        return task

    # ── 새 프로젝트 생성 ──
    project = _clone_project_from_template(
        template_project_id, topic, title, target_duration=target_duration
    )
    task_id = str(uuid.uuid4())[:8]
    estimate = estimate_project(project.config or {})
    task = _make_task_record(
        task_id,
        template_project_id=template_project_id,
        project_id=project.id,
        topic=project.topic,
        title=project.title,
        estimate=estimate,
        config=project.config,
    )
    _TASKS[task_id] = task
    _save_tasks_to_disk()
    return task


def recover_project(project_id: str) -> dict:
    """v1.1.56: 프로젝트 ID 로 태스크를 복구한다.

    큐에서 사라졌거나, 서버 재시작으로 유실된 태스크를 디스크 파일 기반으로
    복구해서 이어서 하기 가능한 상태로 만든다.

    1. project_id 로 DB 에서 프로젝트를 찾는다.
    2. _detect_completed_steps 로 어디까지 완료됐는지 파악한다.
    3. 태스크 레코드를 _TASKS 에 등록한다 (status='failed' → 이어하기 가능).
    """
    # 이미 같은 project_id 의 태스크가 있으면 그대로 반환
    for t in _TASKS.values():
        if t.get("project_id") == project_id:
            return t

    project = _load_project(project_id)
    if not project:
        raise KeyError(f"프로젝트를 찾을 수 없습니다: {project_id}")

    detected = _detect_completed_steps(project_id)
    config = project.config or {}
    estimate = estimate_project(config)

    task_id = str(uuid.uuid4())[:8]
    task = _make_task_record(
        task_id,
        template_project_id=config.get("template_project_id"),
        project_id=project_id,
        topic=project.topic or "",
        title=project.title or "",
        estimate=estimate,
        config=config,
    )
    task["step_states"] = detected

    # total_cuts 복원 — script.json 에서
    script_path = Path(DATA_DIR) / project_id / "script.json"
    if script_path.exists():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            task["total_cuts"] = len(script.get("cuts", []))
        except Exception:
            pass

    # 첫 번째 미완료 스텝
    first_pending = None
    for _slug, step_num, _label in STEP_ORDER:
        if detected.get(str(step_num)) != "completed":
            first_pending = step_num
            break

    if first_pending:
        task["resume_from_step"] = first_pending

    # 모든 스텝이 완료면 completed, 아니면 failed (이어하기 가능)
    all_done = all(v == "completed" for v in detected.values())
    task["status"] = "completed" if all_done else "failed"
    task["error"] = None if all_done else "태스크 복구됨 — 이어하기를 눌러주세요"
    task["finished_at"] = _utcnow_iso() if all_done else None

    completed_labels = [
        label for _slug, sn, label in STEP_ORDER
        if detected.get(str(sn)) == "completed"
    ]
    print(
        f"[oneclick] 프로젝트 복구: {project_id} "
        f"(완료: {', '.join(completed_labels) or '없음'}, "
        f"이어하기: Step {first_pending or '모두완료'}부터)"
    )
    _TASKS[task_id] = task
    _save_tasks_to_disk()
    return task


def start_task(task_id: str) -> dict:
    """prepared 상태의 task 를 실제로 실행. 백그라운드 asyncio.Task 등록."""
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")
    if task["status"] not in ("prepared", "failed", "cancelled"):
        # 이미 running/completed 면 무시 (idempotent)
        return task
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    # v1.1.37 bugfix: get_event_loop() 는 worker thread 에서 에러. 반드시 async
    # 컨텍스트에서 호출되어야 하므로 get_running_loop() 로 의도를 명시. 라우터
    # oneclick.start 가 async def 로 선언되어 있어 여기서 running loop 가 보장됨.
    # v1.1.58: 중복 스케줄 방지 가드를 통한다.
    _schedule_oneclick_run(task_id)
    return task


def resume_task(task_id: str) -> dict:
    """실패/취소된 task 를 실패 지점부터 이어서 재실행.

    v1.1.49: 완료된 단계(step_states == "completed")는 건너뛰고,
    첫 번째 failed/pending/cancelled 단계부터 다시 실행한다.
    """
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")
    if task["status"] not in ("failed", "cancelled", "paused", "completed", "queued"):
        raise ValueError(f"resume 불가: 현재 상태가 '{task['status']}'")

    # 첫 번째 미완료 단계 찾기
    resume_step = None
    for _slug, step_num, _label in STEP_ORDER:
        state = task["step_states"].get(str(step_num), "pending")
        if state != "completed":
            resume_step = step_num
            break

    if resume_step is None:
        # 모든 단계가 completed — 사실상 완료 상태
        task["status"] = "completed"
        task["finished_at"] = _utcnow_iso()
        return task

    # 실패/취소된 단계와 이후 단계 상태를 pending 으로 리셋
    found = False
    for _slug, step_num, _label in STEP_ORDER:
        if step_num == resume_step:
            found = True
        if found:
            task["step_states"][str(step_num)] = "pending"

    # task 메타 리셋
    task["status"] = "queued"
    task["error"] = None
    task["finished_at"] = None
    task["resume_from_step"] = resume_step

    # Redis cancel 플래그 초기화
    try:
        from app.tasks.pipeline_tasks import _redis_set
        _redis_set(f"pipeline:cancel:{task['project_id']}", "")
    except Exception:
        pass

    # v1.1.58: 이전 인스턴스가 _RUN_LOCK 을 들고 있을 수 있으므로 가드로 정리 후 스케줄
    _schedule_oneclick_run(task_id)
    return task


def cancel_task(task_id: str) -> dict:
    """사용자 `중지` — 어떤 상태든 즉시 `cancelled` 로 표시한다.

    v1.1.48 이전에는 running 상태일 때 status 를 그대로 두고 Redis cancel 플래그
    에만 의존했다. 문제는:

    1. 사용자가 중지를 누른 직후에도 UI 가 여전히 `running` 으로 보여
       "중지가 안되네" 라고 느꼈다.
    2. 대본 생성(`_step_script`) 단계는 check_pause_or_cancel 호출이 전혀 없어
       LLM 이 끝날 때까지(30~60초) 플래그가 사실상 무시됐다.
    3. runner 가 PipelineCancelled 를 catch 하지 않아 취소가 `failed` 로 기록.

    v1.1.48 는 세 경로를 모두 수선한다:
    - 여기서 task status 를 즉시 `cancelled` + `finished_at` 로 마킹 → UI 즉시 반영.
    - `_run_oneclick_task` 가 매 단계 진입 전/후로 이 status 를 확인하고 빠진다.
    - `_step_script` 가 LLM 전후로 check_pause_or_cancel 을 돌아 중간 이탈 가능.
    - `_run_oneclick_task` 가 `PipelineCancelled` 를 별도로 잡아 cancelled 로 마감.

    즉 pipeline step 내부 루프(_step_voice/image/video)는 기존처럼 Redis 플래그로
    깨어나고, 대본 단계는 status 폴링 + 전후 체크로 빠지고, UI 는 즉시 업데이트된다.
    """
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    try:
        from app.tasks.pipeline_tasks import _redis_set
        _redis_set(f"pipeline:cancel:{task['project_id']}", "1")
    except Exception:
        pass

    # v1.1.48: 상태와 무관하게 즉시 cancelled 로 마킹(낙관적 UI).
    # 이미 completed/failed/cancelled 인 경우는 건드리지 않는다.
    if task["status"] not in ("completed", "failed", "cancelled"):
        task["status"] = "cancelled"
        task["error"] = task.get("error") or "사용자 취소"
        task["finished_at"] = task.get("finished_at") or _utcnow_iso()
    return task


def get_task(task_id: str) -> Optional[dict]:
    task = _TASKS.get(task_id)
    if not task:
        return None
    # 매 조회마다 진행률을 최신화
    task["progress_pct"] = _compute_progress_pct(task)
    # v1.1.53: 썸네일 생성 상태 (waiting / generating / done / failed)
    # v1.1.55: failed:사유 형태인 경우 status 와 error 를 분리하여 전달
    # v1.1.58: 완료/실패 태스크는 실제 파일 존재 여부로 최종 판정 — Redis 고착 방지
    pid = task.get("project_id")
    if pid:
        raw = _redis_get(f"thumbnail:status:{pid}") or "waiting"
        # 태스크가 이미 끝났으면 Redis 대신 파일 체크로 확정
        if task["status"] in ("completed", "failed", "cancelled"):
            thumb_path = DATA_DIR / pid / "output" / "thumbnail.png"
            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                task["thumbnail_status"] = "done"
                task["thumbnail_error"] = None
            elif raw.startswith("failed:"):
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = raw[len("failed:"):]
            else:
                # generating 이 고착됐거나 waiting 인데 태스크는 끝남 → 실패 처리
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = "썸네일 파일이 생성되지 않았습니다."
        else:
            # v1.1.60: 실행 중인 태스크라도 썸네일 파일이 실제로 있으면 done 으로
            # 본다. Redis 가 'waiting' 으로 고착된 resume 케이스 등에서 미리보기가
            # 안 뜨는 문제를 막는다.
            thumb_path = DATA_DIR / pid / "output" / "thumbnail.png"
            if thumb_path.exists() and thumb_path.stat().st_size > 100:
                task["thumbnail_status"] = "done"
                task["thumbnail_error"] = None
            elif raw.startswith("failed:"):
                task["thumbnail_status"] = "failed"
                task["thumbnail_error"] = raw[len("failed:"):]
            else:
                task["thumbnail_status"] = raw
                task["thumbnail_error"] = None
    else:
        task["thumbnail_status"] = "waiting"
        task["thumbnail_error"] = None
    return task


def get_running_task_info() -> Optional[dict]:
    """v1.1.58: 현재 실행 중(running/queued)인 태스크 정보 반환.

    없으면 None. 있으면 { task_id, topic, status, progress_pct,
    started_at, estimated_remaining_seconds } 를 반환.
    """
    for t in _TASKS.values():
        if t["status"] in ("running", "queued", "prepared"):
            pct = _compute_progress_pct(t)
            remaining = None
            est = t.get("estimate") or {}
            est_total = est.get("estimated_seconds")
            if est_total and pct > 0:
                elapsed_ratio = pct / 100.0
                if elapsed_ratio > 0.01:
                    remaining = int(est_total * (1.0 - elapsed_ratio) / elapsed_ratio)
            elif est_total:
                remaining = est_total
            return {
                "task_id": t["task_id"],
                "topic": t.get("topic") or t.get("title") or "",
                "status": t["status"],
                "progress_pct": pct,
                "started_at": t.get("started_at"),
                "estimated_remaining_seconds": remaining,
            }
    return None


def list_tasks() -> list[dict]:
    # 최신순. 진행률도 갱신.
    for tid in list(_TASKS.keys()):
        _TASKS[tid]["progress_pct"] = _compute_progress_pct(_TASKS[tid])
    return sorted(
        _TASKS.values(),
        key=lambda t: t.get("created_at") or "",
        reverse=True,
    )


def clear_step_outputs(task_id: str, step: int) -> dict:
    """v1.1.52: 특정 단계의 생성물을 디스크에서 삭제하고 step_state 를 pending 으로 되돌린다.

    지원 단계:
        3 — audio/*.mp3
        4 — images/*.png (커스텀 이미지 제외)
        5 — videos/*.mp4 + output/merged.mp4
    """
    import glob as _glob

    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task {task_id} not found")
    if task["status"] in ("running", "queued"):
        raise ValueError("실행 중인 태스크는 초기화할 수 없습니다")

    project_id = task["project_id"]
    project_dir = Path(DATA_DIR) / project_id

    STEP_MAP = {
        2: ("script", ["script.json", "output/thumbnail.png"]),
        3: ("audio", ["audio/*.mp3"]),
        4: ("images", ["images/*.png"]),
        5: ("videos", ["videos/*.mp4", "output/merged.mp4"]),
        6: ("render", ["output/final.mp4", "output/merged.mp4"]),
    }
    if step not in STEP_MAP:
        raise ValueError(f"초기화 가능한 단계: 2(대본), 3(음성), 4(이미지), 5(영상), 6(렌더)")

    label, patterns = STEP_MAP[step]
    deleted = 0
    for pattern in patterns:
        for fp in _glob.glob(str(project_dir / pattern)):
            try:
                os.remove(fp)
                deleted += 1
            except OSError:
                pass

    # DB step_state 도 되돌린다
    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            states = dict(project.step_states or {})
            states[str(step)] = "pending"
            # 이후 단계도 pending 으로 (예: 이미지 삭제 시 영상도 무효)
            for s in range(step + 1, 8):
                if str(s) in states:
                    states[str(s)] = "pending"
            project.step_states = states
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(project, "step_states")
            db.commit()
    finally:
        db.close()

    # 태스크 메모리에도 반영
    step_states = task.get("step_states", {})
    step_states[str(step)] = "pending"
    for s in range(step + 1, 8):
        if str(s) in step_states:
            step_states[str(s)] = "pending"
    task["step_states"] = step_states
    _save_tasks_to_disk()

    return {"ok": True, "step": step, "label": label, "deleted_files": deleted}


def reset_task(task_id: str, from_step: int = 2) -> dict:
    """v1.1.55: 프로젝트 전체 초기화 — from_step 부터 모든 단계를 pending 으로 되돌린다.

    from_step=2 (기본값) → 대본부터 전부 초기화.
    from_step=3 → 음성부터 초기화 (대본은 유지).

    v1.1.55: 백그라운드 스레드가 아직 돌고 있을 수 있으므로 cancel 키를 설정해
    잔존 스레드가 다음 check_pause_or_cancel 에서 종료되도록 보장한다.
    """
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError(f"task {task_id} not found")
    if task["status"] in ("running", "queued"):
        raise ValueError("실행 중인 태스크는 초기화할 수 없습니다")

    # v1.1.55: 취소 후에도 백그라운드 스레드가 살아있을 수 있다.
    # cancel 키를 (재)설정하여 잔존 스레드가 확실히 멈추게 한다.
    pid = task.get("project_id")
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception:
            pass
        # 잔존 스레드가 종료될 시간을 약간 준다 (TTS 한 건 완료 대기)
        import time
        time.sleep(0.5)

    total_deleted = 0
    for step in range(from_step, 8):
        try:
            result = clear_step_outputs(task_id, step)
            total_deleted += result.get("deleted_files", 0)
        except (ValueError, KeyError):
            continue

    # cancel 키 정리 (다음 재실행 시 cancel 상태로 시작하지 않도록)
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_delete
            _redis_delete(f"pipeline:cancel:{pid}")
        except Exception:
            pass

    # 상태를 paused 로 되돌림 (재실행 가능)
    task["status"] = "paused"
    task["progress_pct"] = 0.0
    task["current_step"] = None
    task["current_step_name"] = None
    _save_tasks_to_disk()

    return {"ok": True, "from_step": from_step, "deleted_files": total_deleted}


def delete_task(task_id: str) -> bool:
    """태스크 하나를 삭제한다. 디스크 파일도 정리.

    v1.1.58 [돈줄 차단 HOTFIX]: 이전엔 status 가 running/queued 면 거부했고,
    설령 cancelled 상태에서 삭제가 통과돼도 백그라운드 스레드(특히 이미지
    배치 호출)가 계속 살아있어 OpenAI 비용이 새는 사고가 났다.
    이제는:
      1) Redis cancel 플래그를 즉시 세워 다음 컷 호출을 차단
      2) _ACTIVE_RUNS 의 asyncio.Task 를 cancel 해서 _RUN_LOCK 즉시 해제
      3) task 메타 + 디스크 파일 정리
    실행 중이어도 강제 삭제를 허용한다.
    """
    task = _TASKS.get(task_id)
    if not task:
        return False

    pid = task.get("project_id")

    # 1) 백그라운드 스레드가 다음 컷에서 즉시 빠지도록 cancel 플래그 세팅
    if pid:
        try:
            from app.tasks.pipeline_tasks import _redis_set
            _redis_set(f"pipeline:cancel:{pid}", "1")
        except Exception as e:
            print(f"[oneclick] delete: cancel 플래그 설정 실패: {e}")

    # 2) asyncio Task cancel
    prev = _ACTIVE_RUNS.get(task_id)
    if prev is not None and not prev.done():
        try:
            prev.cancel()
            print(f"[oneclick] delete: 실행 중인 _run_oneclick_task({task_id}) 강제 취소")
        except Exception as e:
            print(f"[oneclick] delete: asyncio task cancel 실패: {e}")
    _ACTIVE_RUNS.pop(task_id, None)

    # 3) 태스크 + 디스크 정리
    task["status"] = "cancelled"
    task["finished_at"] = task.get("finished_at") or _utcnow_iso()
    _cleanup_project_files(pid)
    _TASKS.pop(task_id, None)
    _save_tasks_to_disk()
    return True


def _cleanup_project_files(project_id: str | None) -> int:
    """프로젝트 디렉토리 삭제. 삭제한 바이트 수 반환."""
    if not project_id:
        return 0
    import shutil
    project_dir = DATA_DIR / project_id
    if not project_dir.exists():
        return 0
    try:
        size = _dir_size(project_dir)
        shutil.rmtree(project_dir, ignore_errors=True)
        return size
    except Exception as e:
        print(f"[oneclick] 디스크 정리 실패 ({project_id}): {e}")
        return 0


def _dir_size(path) -> int:
    """디렉토리 전체 크기 (바이트)."""
    from pathlib import Path
    total = 0
    try:
        for f in Path(path).rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except Exception:
        pass
    return total


def prune_tasks(keep: int = 20) -> None:
    """완료/실패 태스크가 너무 쌓이면 오래된 것부터 정리."""
    finished = [
        t for t in _TASKS.values()
        if t["status"] in ("completed", "failed", "cancelled")
    ]
    finished.sort(key=lambda t: t.get("finished_at") or t.get("created_at") or "")
    excess = len(finished) - keep
    if excess > 0:
        for t in finished[:excess]:
            _TASKS.pop(t["task_id"], None)


# --------------------------------------------------------------------------- #
# v1.1.54 — 완성작 관리 (라이브러리)
# --------------------------------------------------------------------------- #


def get_task_detail(task_id: str) -> dict:
    """완성작 상세 정보 — 프로젝트 메타 + 디스크 용량 + 컷 목록."""
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    project_id = task.get("project_id")
    project = _load_project(project_id) if project_id else None
    project_dir = DATA_DIR / project_id if project_id else None

    # 디스크 용량
    disk_bytes = _dir_size(project_dir) if project_dir and project_dir.exists() else 0

    # 파일 존재 여부
    has_final = False
    has_thumbnail = False
    final_path = ""
    thumbnail_path = ""
    cut_images = []
    if project_dir and project_dir.exists():
        output_dir = project_dir / "output"
        # 최종 영상
        for name in ("final_with_subtitles.mp4", "final.mp4", "merged.mp4"):
            f = output_dir / name
            if f.exists() and f.stat().st_size > 100:
                has_final = True
                final_path = f"output/{name}"
                break
        # 썸네일
        for ext in ("png", "jpg", "jpeg", "webp"):
            f = output_dir / f"thumbnail.{ext}"
            if f.exists():
                has_thumbnail = True
                thumbnail_path = f"output/thumbnail.{ext}"
                break
        # 컷 이미지 목록
        images_dir = project_dir / "images"
        if images_dir.exists():
            for img in sorted(images_dir.glob("cut_*.png")):
                cut_images.append(f"images/{img.name}")
            if not cut_images:
                for img in sorted(images_dir.glob("cut_*.jpg")):
                    cut_images.append(f"images/{img.name}")

    # 소요 시간
    elapsed_sec = None
    if task.get("started_at") and task.get("finished_at"):
        try:
            from datetime import datetime
            start = datetime.fromisoformat(task["started_at"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(task["finished_at"].replace("Z", "+00:00"))
            elapsed_sec = int((end - start).total_seconds())
        except Exception:
            pass

    return {
        "task_id": task_id,
        "project_id": project_id,
        "topic": task.get("topic"),
        "title": task.get("title"),
        "status": task.get("status"),
        "total_cuts": task.get("total_cuts", 0),
        "disk_bytes": disk_bytes,
        "disk_mb": round(disk_bytes / (1024 * 1024), 1),
        "has_final_video": has_final,
        "final_video_path": final_path,
        "has_thumbnail": has_thumbnail,
        "thumbnail_path": thumbnail_path,
        "cut_images": cut_images,
        "cut_image_count": len(cut_images),
        "models": task.get("models"),
        "estimate": task.get("estimate"),
        "elapsed_sec": elapsed_sec,
        "youtube_url": project.youtube_url if project else None,
        "started_at": task.get("started_at"),
        "finished_at": task.get("finished_at"),
        "created_at": task.get("created_at"),
        "error": task.get("error"),
    }


async def manual_youtube_upload(task_id: str) -> dict:
    """완성작을 수동으로 YouTube 에 업로드."""
    task = _TASKS.get(task_id)
    if not task:
        raise KeyError("task not found")

    project_id = task["project_id"]
    project = _load_project(project_id)
    if not project:
        raise RuntimeError("프로젝트를 찾을 수 없습니다")

    config = dict(project.config or {})
    await _step_youtube_upload(project_id, config, channel=task.get("channel"))

    # task 에도 반영
    task["step_states"]["7"] = "completed"
    _save_tasks_to_disk()

    # 업로드 후 URL 다시 읽기
    project = _load_project(project_id)
    return {
        "ok": True,
        "youtube_url": project.youtube_url if project else None,
    }


def bulk_delete_tasks(task_ids: list[str]) -> dict:
    """여러 태스크 일괄 삭제 + 디스크 정리."""
    deleted = 0
    freed_bytes = 0
    skipped = []
    for tid in task_ids:
        task = _TASKS.get(tid)
        if not task:
            continue
        if task["status"] in ("running", "queued", "prepared"):
            skipped.append(tid)
            continue
        freed_bytes += _cleanup_project_files(task.get("project_id"))
        _TASKS.pop(tid, None)
        deleted += 1
    _save_tasks_to_disk()
    return {
        "ok": True,
        "deleted": deleted,
        "freed_mb": round(freed_bytes / (1024 * 1024), 1),
        "skipped": skipped,
    }


def get_library_stats() -> dict:
    """라이브러리 통계."""
    all_tasks = list(_TASKS.values())
    completed = [t for t in all_tasks if t["status"] == "completed"]
    failed = [t for t in all_tasks if t["status"] == "failed"]

    # 업로드 여부는 DB 에서 youtube_url 확인
    uploaded_count = 0
    total_disk = 0
    for t in completed:
        pid = t.get("project_id")
        if pid:
            p = _load_project(pid)
            if p and p.youtube_url:
                uploaded_count += 1
            pdir = DATA_DIR / pid
            if pdir.exists():
                total_disk += _dir_size(pdir)

    return {
        "total_completed": len(completed),
        "total_failed": len(failed),
        "uploaded": uploaded_count,
        "not_uploaded": len(completed) - uploaded_count,
        "total_disk_bytes": total_disk,
        "total_disk_mb": round(total_disk / (1024 * 1024), 1),
    }


# --------------------------------------------------------------------------- #
# v1.1.43 — 주제 큐 + 매일 HH:MM 스케줄러
# --------------------------------------------------------------------------- #
#
# 설계 개요 (v1.1.57: 채널 4개 지원)
# --------
# `_QUEUE_FILE` 에 아래 구조의 JSON 을 저장한다:
#
#   {
#     "channel_times": {           # 채널별 HH:MM, null 이면 해당 채널 스케줄 꺼짐
#       "1": "07:00",
#       "2": "12:00",
#       "3": "18:00",
#       "4": null
#     },
#     "last_run_dates": {          # 채널별 마지막 발화 날짜 (중복 방지)
#       "1": "2026-04-14",
#       "2": "2026-04-14",
#       ...
#     },
#     "items": [
#       {
#         "id": "<uuid8>",
#         "topic": "...",
#         "template_project_id": "<project_id>" | null,
#         "target_duration": 600,  # 초 단위, null/0 이면 템플릿 기본값
#         "channel": 1             # 1~4 (없으면 1)
#       },
#       ...
#     ]
#   }
#
# 발화 규칙
# --------
# 1. 30 초 간격으로 `_queue_loop` 가 돈다.
# 2. 각 채널(1~4) 독립적으로 점검:
#    - channel_times[ch] 가 비어있으면 건너뜀
#    - 해당 채널의 items 가 없으면 건너뜀
#    - 오늘 HH:MM 시각을 지났고 last_run_dates[ch] 가 오늘이 아니면
#      해당 채널의 큐 맨 앞 1 건을 pop 해서 즉시 prepare + start.
# 3. 채널별로 last_run_dates[ch] 를 갱신해 같은 날 재발화 방지.

CHANNELS = [1, 2, 3, 4]

_QUEUE_FILE = Path(DATA_DIR) / "oneclick_queue.json"

_QUEUE_DEFAULT: dict[str, Any] = {
    "channel_times": {"1": None, "2": None, "3": None, "4": None},
    "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
    "items": [],
}

# 프로세스 내 캐시. 파일을 정답으로 두고, 이 dict 는 읽기 가속용.
_QUEUE: dict[str, Any] = dict(_QUEUE_DEFAULT)

# 스케줄러 asyncio.Task 핸들
_queue_task: Optional[asyncio.Task] = None

# 파일 I/O 직렬화용 락
_queue_io_lock = asyncio.Lock()


def _queue_normalize(raw: Any) -> dict[str, Any]:
    """디스크에서 읽은 값이 불완전해도 안전한 dict 로 강제.

    v1.1.57: 레거시 daily_time/last_run_date → channel_times/last_run_dates 마이그레이션.
    """
    if not isinstance(raw, dict):
        return {k: (dict(v) if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
                for k, v in _QUEUE_DEFAULT.items()}
    out: dict[str, Any] = {
        "channel_times": {"1": None, "2": None, "3": None, "4": None},
        "last_run_dates": {"1": None, "2": None, "3": None, "4": None},
        "items": [],
    }

    # --- channel_times ---
    ct = raw.get("channel_times")
    if isinstance(ct, dict):
        for ch in CHANNELS:
            v = ct.get(str(ch))
            if isinstance(v, str) and len(v) == 5 and v[2] == ":":
                out["channel_times"][str(ch)] = v
    # 레거시 마이그레이션: daily_time → channel_times["1"]
    legacy_dt = raw.get("daily_time")
    if isinstance(legacy_dt, str) and len(legacy_dt) == 5 and legacy_dt[2] == ":":
        if not out["channel_times"]["1"]:
            out["channel_times"]["1"] = legacy_dt

    # --- last_run_dates ---
    lrd = raw.get("last_run_dates")
    if isinstance(lrd, dict):
        for ch in CHANNELS:
            v = lrd.get(str(ch))
            if isinstance(v, str) and len(v) == 10:
                out["last_run_dates"][str(ch)] = v
    # 레거시 마이그레이션
    legacy_lrd = raw.get("last_run_date")
    if isinstance(legacy_lrd, str) and len(legacy_lrd) == 10:
        if not out["last_run_dates"]["1"]:
            out["last_run_dates"]["1"] = legacy_lrd

    # --- items ---
    items = raw.get("items")
    if isinstance(items, list):
        clean: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            topic = str(it.get("topic") or "").strip()
            if not topic:
                continue
            # channel: 1~4. 명시값 → 프리셋 youtube_channel → 1.
            # v1.1.55 hotfix: 사용자가 큐 UI 에서 채널을 안 골랐을 때
            # 무조건 1 로 박혀 프리셋의 채널을 무시하던 버그 수정.
            ch_raw = it.get("channel")
            ch: Optional[int] = None
            try:
                if ch_raw is not None and str(ch_raw).strip() != "":
                    ch = int(ch_raw)
            except (TypeError, ValueError):
                ch = None
            if ch is None:
                tpl_id = it.get("template_project_id")
                if tpl_id:
                    try:
                        tpl = _load_project(str(tpl_id))
                        cfg_ch = (tpl.config or {}).get("youtube_channel") if tpl else None
                        if cfg_ch is not None and str(cfg_ch).strip() != "":
                            ch = int(cfg_ch)
                    except Exception:
                        ch = None
            if ch is None:
                ch = 1
            if ch < 1 or ch > 4:
                ch = 1
            clean.append({
                "id": str(it.get("id") or uuid.uuid4().hex[:8]),
                "topic": topic,
                "template_project_id": (it.get("template_project_id") or None),
                "target_duration": (
                    int(it["target_duration"])
                    if isinstance(it.get("target_duration"), (int, float))
                    and it["target_duration"]
                    else None
                ),
                "channel": ch,
            })
        out["items"] = clean
    return out


def _load_queue_from_disk() -> None:
    global _QUEUE
    try:
        if _QUEUE_FILE.exists():
            raw = json.loads(_QUEUE_FILE.read_text(encoding="utf-8"))
            _QUEUE = _queue_normalize(raw)
            return
    except Exception as e:
        print(f"[oneclick.queue] load failed, falling back to default: {e}")
    _QUEUE = dict(_QUEUE_DEFAULT)


def _save_queue_to_disk() -> None:
    try:
        _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _QUEUE_FILE.write_text(
            json.dumps(_QUEUE, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"[oneclick.queue] save failed: {e}")


def get_queue() -> dict[str, Any]:
    """현재 큐 상태 반환 (UI 조회용). 복사본을 돌려준다."""
    return {
        "channel_times": dict(_QUEUE.get("channel_times") or {}),
        "last_run_dates": dict(_QUEUE.get("last_run_dates") or {}),
        "items": list(_QUEUE.get("items") or []),
    }


def set_queue(new_state: dict[str, Any]) -> dict[str, Any]:
    """큐 전체를 교체. 프론트의 "저장" 버튼이 이 한 건만 호출한다."""
    global _QUEUE
    normalized = _queue_normalize(new_state)
    # last_run_dates 는 사용자가 바꿀 값이 아니므로 기존 값 유지.
    normalized["last_run_dates"] = dict(_QUEUE.get("last_run_dates") or {})
    _QUEUE = normalized
    _save_queue_to_disk()
    return get_queue()


def _today_iso() -> str:
    return datetime.now().date().isoformat()


def _should_fire_channel(now: datetime, ch: int) -> bool:
    """채널 ch 의 스케줄이 발화해야 하는지 판단."""
    ch_key = str(ch)
    ct = (_QUEUE.get("channel_times") or {}).get(ch_key)
    if not ct:
        return False
    try:
        hh, mm = ct.split(":")
        target_h = int(hh)
        target_m = int(mm)
    except Exception:
        return False
    today = now.date().isoformat()
    lrd = (_QUEUE.get("last_run_dates") or {}).get(ch_key)
    if lrd == today:
        return False
    return (now.hour, now.minute) >= (target_h, target_m)


async def _fire_queue_for_channel(ch: int) -> None:
    """채널 ch 의 큐 맨 앞 1 건을 뽑아 즉시 실행.

    해당 채널에 items 가 없으면 아무것도 안 함.
    성공/실패 상관없이 pop-on-start.
    """
    ch_key = str(ch)
    items = list(_QUEUE.get("items") or [])
    # 해당 채널의 첫 번째 항목 찾기
    target_idx = None
    for i, it in enumerate(items):
        if (it.get("channel") or 1) == ch:
            target_idx = i
            break
    if target_idx is None:
        return

    head = items.pop(target_idx)
    _QUEUE["items"] = items
    _save_queue_to_disk()

    print(
        f"[oneclick.queue] firing ch{ch} item: topic={head.get('topic')!r} "
        f"template={head.get('template_project_id')} "
        f"duration={head.get('target_duration')}"
    )

    try:
        task = prepare_task(
            template_project_id=head.get("template_project_id"),
            topic=head["topic"],
            title=None,
            target_duration=head.get("target_duration"),
        )
        task["triggered_by"] = "schedule"
        task["channel"] = ch
        start_task(task["task_id"])
    except Exception as e:
        print(f"[oneclick.queue] fire ch{ch} failed: {e}")


async def _queue_loop() -> None:
    """30 초 간격으로 채널별 큐 스케줄을 점검."""
    print("[oneclick.queue] scheduler loop started (4-channel mode)")
    try:
        while True:
            try:
                now = datetime.now()
                today = _today_iso()
                for ch in CHANNELS:
                    if _should_fire_channel(now, ch):
                        # 오늘 점검 완료로 표시
                        if "last_run_dates" not in _QUEUE:
                            _QUEUE["last_run_dates"] = {}
                        _QUEUE["last_run_dates"][str(ch)] = today
                        _save_queue_to_disk()
                        # 해당 채널의 아이템이 있으면 실행
                        ch_items = [it for it in (_QUEUE.get("items") or [])
                                    if (it.get("channel") or 1) == ch]
                        if ch_items:
                            await _fire_queue_for_channel(ch)
            except Exception as e:
                print(f"[oneclick.queue] loop iter error: {e}")
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        print("[oneclick.queue] scheduler loop cancelled")
        raise


def start_queue_scheduler() -> None:
    """FastAPI startup 훅에서 호출. 프로세스당 한 번만 돈다."""
    global _queue_task
    _load_tasks_from_disk()   # v1.1.52: 이전 세션 태스크 복원
    _load_queue_from_disk()
    if _queue_task is not None and not _queue_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        print("[oneclick.queue] no running loop; scheduler not started")
        return
    _queue_task = loop.create_task(_queue_loop())


def stop_queue_scheduler() -> None:
    """FastAPI shutdown 훅에서 호출."""
    global _queue_task
    if _queue_task is not None:
        _queue_task.cancel()
        _queue_task = None


def run_queue_top_now(channel: Optional[int] = None) -> Optional[dict]:
    """사용자가 "지금 1건 실행" 버튼을 누를 때 호출.

    channel 이 지정되면 해당 채널의 맨 위 1건만 실행.
    None 이면 전체 큐에서 맨 위 1건 실행 (레거시 호환).
    """
    items = list(_QUEUE.get("items") or [])
    if not items:
        return None
    # 채널 지정 시 해당 채널의 첫 항목 찾기
    target_idx = None
    for i, it in enumerate(items):
        if channel is None or (it.get("channel") or 1) == channel:
            target_idx = i
            break
    if target_idx is None:
        return None
    head = items.pop(target_idx)
    _QUEUE["items"] = items
    _save_queue_to_disk()
    task = prepare_task(
        template_project_id=head.get("template_project_id"),
        topic=head["topic"],
        title=None,
        target_duration=head.get("target_duration"),
    )
    task["triggered_by"] = "manual"
    task["channel"] = head.get("channel") or 1
    start_task(task["task_id"])
    return task
