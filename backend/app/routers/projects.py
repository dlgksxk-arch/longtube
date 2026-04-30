"""Project CRUD router"""
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel
from typing import Optional

from app.models.database import get_db
from app.models.project import Project
from app.services.estimation_service import estimate_project
from app.services.image.factory import DEFAULT_IMAGE_MODEL
from app.services.video.factory import DEFAULT_VIDEO_MODEL
from app.config import resolve_project_dir
import os

router = APIRouter()


class ProjectCreate(BaseModel):
    topic: str
    title: Optional[str] = None
    config: Optional[dict] = None


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    config: Optional[dict] = None


DEFAULT_CONFIG = {
    "aspect_ratio": "16:9",
    "target_duration": 600,
    "cut_transition": "slow",
    "style": "news_explainer",
    "script_model": "claude-sonnet-4-6",
    "image_model": DEFAULT_IMAGE_MODEL,
    "video_model": DEFAULT_VIDEO_MODEL,
    # v2.1.1: AI 영상 생성 활성화 여부. False 면 모든 컷이 Ken Burns 폴백 (비용 0, GPU 0)
    "enable_ai_video": True,
    # v1.1.36: 영상 제작 대상 — 선택되지 않은 컷은 ffmpeg-kenburns 폴백(비용 0)
    # "all" | "every_3" | "every_4" | "every_5" | "character_only"
    "video_target_selection": "all",
    # v1.1.55: 인트로 강제 AI 컷 수. 양수면 컷 1..N 은 video_target_selection
    # 과 무관하게 무조건 primary video_model 로 생성한다. 0 이면 비활성.
    "ai_video_first_n": 5,
    # v1.1.55: 컷별 영상 생성 직후 자기 대사 자막을 바로 번인 → 머지 후
    # 싱크 깨짐 차단. False 로 토글하면 옛 방식(머지 후 본편 ASS 번인) 사용.
    "cut_level_subtitles": True,
    "tts_model": "openai-tts",
    "tts_voice_id": "alloy",
    # 음성 속도: 1.0=기본, <1.0=느리게, >1.0=빠르게.
    # OpenAI TTS: 0.25~4.0, ElevenLabs: 0.7~1.2 에서 clamp.
    "tts_speed": 1.0,
    "language": "ko",
    "auto_pause_after_step": True,
    # v1.1.55: YouTube 공개 범위 — 프리셋 설정에서 관리
    "youtube_privacy": "private",
    # v2.1.3: 최종 렌더 BGM. bgm_path 는 DATA_DIR/{project_id} 기준 상대 경로.
    "bgm_enabled": False,
    "bgm_path": "",
    "bgm_style_prompt": "",
    "bgm_volume": 0.24,
    "subtitle_style": {
        "font": "Pretendard Bold",
        "size": 48,
        "color": "#FFFFFF",
        "outline_color": "#000000",
        "position": "bottom",
    },
}


@router.get("")
def list_projects(db: Session = Depends(get_db)):
    # v1.1.42: 딸깍(oneclick) 으로 만들어진 일회성 프로젝트는 프리셋 목록에서
    # 제외한다. 사용자 요구: "딸깍 셋팅하면 프리셋이 생성되네? 이럼 안되지.
    # 프리셋이 중요한거라고". 실제 파이프라인 함수들이 Project 행을 DB 에
    # 기대하기 때문에 행 자체는 남기되, UI 리스트에서만 숨긴다.
    projects = db.query(Project).order_by(Project.created_at.desc()).all()
    out = []
    for p in projects:
        cfg = p.config or {}
        if cfg.get("__oneclick__"):
            continue
        out.append(_to_dict(p))
    return out


@router.post("")
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    project_id = str(uuid.uuid4())[:8]
    config = {**DEFAULT_CONFIG, **(body.config or {})}

    project = Project(
        id=project_id,
        title=body.title or body.topic[:50],
        topic=body.topic,
        config=config,
        status="draft",
    )
    db.add(project)
    db.commit()

    # NAS에 프로젝트 디렉토리 생성
    project_dir = resolve_project_dir(project_id, config=config, create=True)
    for sub in ["audio", "images", "videos", "subtitles", "output"]:
        os.makedirs(project_dir / sub, exist_ok=True)

    return _to_dict(project)


@router.get("/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    # v1.1.49: step_states 마이그레이션 — 영상 스텝이 6→5 로 변경됨.
    # 기존 DB 에 step_states["6"] 이 영상 데이터로 남아있으면 "5" 로 이동하고 "6" 삭제.
    ss = dict(project.step_states or {})
    if "6" in ss and "5" not in ss:
        # "6" 에 저장된 값이 영상 상태 (이전 버전)
        ss["5"] = ss.pop("6")
        project.step_states = ss
        flag_modified(project, "step_states")
        db.commit()
    elif "6" in ss and ss["6"] in ("running", "failed") and ss.get("5") in (None, "pending", ""):
        # 둘 다 있는데 "6" 이 이전 영상 데이터인 경우
        ss["5"] = ss.pop("6")
        project.step_states = ss
        flag_modified(project, "step_states")
        db.commit()

    return _to_dict(project)


@router.put("/{project_id}")
def update_project(project_id: str, body: ProjectUpdate, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if body.title is not None:
        project.title = body.title
    if body.topic is not None:
        project.topic = body.topic
    if body.config is not None:
        # v1.1.29: SQLAlchemy JSON 컬럼의 in-place mutation 감지 실패 이슈 대응 —
        # 새 dict 를 할당하는 것만으론 dirty 마킹이 불안정하므로 flag_modified 로 강제.
        project.config = {**(project.config or {}), **body.config}
        flag_modified(project, "config")

    db.commit()

    # v1.2.28: 실행 중인 딸깍 태스크에 설정 변경 즉시 전파.
    # 사용자 요구: "설정 변경하면 실시간으로 반영해!!!"
    # _TASKS 의 해당 project_id task 에 대해 task["models"] 를 새 config 기준으로
    # 덮어쓰고 로그도 남긴다. 실제 스텝 함수가 다음 컷/다음 스텝에서 config 를
    # 다시 읽도록 _run_single_step 도 v1.2.28 에서 DB 재로드로 바뀌었으니
    # 여기선 UI 표시/로그 즉시성만 챙기면 된다.
    if body.config is not None:
        try:
            from app.services.oneclick_service import refresh_tasks_for_project_update
            refresh_tasks_for_project_update(project.id, dict(project.config or {}))
            from app.services import oneclick_service as _oc
            _fresh_cfg = dict(project.config or {})
            for _t in list(_oc._TASKS.values()):
                if _t.get("project_id") != project.id:
                    continue
                if _t.get("status") not in ("running", "prepared", "queued", "paused"):
                    continue
                _old_models = dict(_t.get("models") or {})
                _oc._sync_task_models_from_config(_t, _fresh_cfg)
                _new_models = _t.get("models") or {}
                _changes = [
                    f"{k}: {_old_models.get(k, '') or '(없음)'} → {_new_models.get(k, '') or '(없음)'}"
                    for k in ("script", "tts", "tts_voice", "image", "video", "thumbnail")
                    if _old_models.get(k, "") != _new_models.get(k, "")
                ]
                if _changes:
                    _oc._add_log(_t, "ℹ 설정 실시간 반영: " + "; ".join(_changes))
        except Exception:
            # 프로젝트 업데이트 자체는 이미 커밋됐으니, 태스크 동기화 실패는 삼킨다.
            pass

    return _to_dict(project)


@router.delete("/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()
    return {"status": "deleted"}


def _to_dict(p: Project) -> dict:
    return {
        "id": p.id, "title": p.title, "topic": p.topic, "config": p.config,
        "status": p.status, "current_step": p.current_step, "step_states": p.step_states,
        "total_cuts": p.total_cuts, "youtube_url": p.youtube_url, "api_cost": p.api_cost,
        "created_at": str(p.created_at), "updated_at": str(p.updated_at),
        # v1.1.33: 선택된 모델 조합 기반 예상 소요시간/비용 (순수 계산, DB 호출 없음)
        "estimate": estimate_project(p.config or {}),
    }


@router.get("/_diagnose/by-title")
def diagnose_by_title(title: str, db: Session = Depends(get_db)):
    """v1.1.55: 프리셋 이름으로 디스크 실태 진단.

    project_id 를 모르는 상황에서 "딸깍폼-제리스아케오" 같은 제목 일부만으로
    어떤 프로젝트가 매칭되는지, 각 프로젝트의 config 에 적힌 자산 파일이
    실제 디스크에 있는지, 그리고 누락된 파일이 DATA_DIR 의 다른 폴더에
    살아남아 있는지(고아 자산)까지 한 번에 보고한다.
    """
    from pathlib import Path as _P

    q = (title or "").strip()
    if not q:
        raise HTTPException(400, "title 쿼리 파라미터가 비어있습니다.")

    # 1) 제목에 q 포함되는 프로젝트 모두 (대소문자 구분 X, like %q%)
    rows = (
        db.query(Project)
        .filter(Project.title.ilike(f"%{q}%"))
        .order_by(Project.created_at.desc())
        .all()
    )

    # 2) DATA_DIR 전체에서 파일명 → 절대경로 인덱스 (고아 자산 탐색용)
    name_index: dict[str, list[str]] = {}
    try:
        for f in _P(DATA_DIR).rglob("*"):
            if f.is_file():
                name_index.setdefault(f.name, []).append(str(f))
    except Exception as e:
        print(f"[diagnose] DATA_DIR scan 실패: {e}")

    def _check(rel_list, pid):
        out = []
        for rel in rel_list or []:
            abs_p = _P(DATA_DIR) / pid / rel
            entry = {
                "rel": rel,
                "abs": str(abs_p),
                "exists": abs_p.exists(),
            }
            if not abs_p.exists():
                fname = _P(rel).name
                hits = name_index.get(fname, [])
                # 자기 폴더 외에서 발견된 고아 후보
                entry["orphans"] = [h for h in hits if str(_P(DATA_DIR) / pid) not in h]
            out.append(entry)
        return out

    results = []
    for p in rows:
        cfg = p.config or {}
        pid = p.id
        proj_dir = _P(DATA_DIR) / pid
        inter_cfg = (cfg.get("interlude") or {})
        inter_report = {}
        for kind in ("opening", "intermission", "ending"):
            entry = inter_cfg.get(kind) or {}
            vp = entry.get("video_path")
            if vp:
                abs_p = proj_dir / vp
                inter_report[kind] = {
                    "rel": vp,
                    "abs": str(abs_p),
                    "exists": abs_p.exists(),
                    "filename": entry.get("filename"),
                }
            else:
                inter_report[kind] = None

        results.append({
            "project_id": pid,
            "title": p.title,
            "topic": p.topic,
            "is_oneclick_marker": bool(cfg.get("__oneclick__")),
            "project_dir": str(proj_dir),
            "project_dir_exists": proj_dir.exists(),
            "reference_images": _check(cfg.get("reference_images", []), pid),
            "character_images": _check(cfg.get("character_images", []), pid),
            "logo_images": _check(cfg.get("logo_images", []), pid),
            "interlude": inter_report,
        })

    return {
        "data_dir": str(DATA_DIR),
        "query": q,
        "match_count": len(results),
        "projects": results,
    }


@router.get("/{project_id}/estimate")
def get_project_estimate(project_id: str, db: Session = Depends(get_db)):
    """v1.1.33: 프로젝트의 현재 config 로 예상 소요시간/비용을 재계산해 반환.

    UI 에서 모델을 바꾸자마자 최신 추정치를 보여주고 싶을 때 호출. 전체
    _to_dict 직렬화에 이미 포함되지만 별도 엔드포인트가 있으면 부분 갱신이 쉬움.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    return estimate_project(project.config or {})
