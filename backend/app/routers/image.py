"""Image generation router"""
import re
import datetime as _dt
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.database import get_db
from app.models.project import Project
from app.models.cut import Cut
from app.config import DATA_DIR, BASE_DIR as _BASE_DIR_FOR_LOG
from app.services.image.factory import get_image_service
from app.services.image.base import get_size

router = APIRouter()


# v1.1.61: 파일 로그. backend/logs/image_async.log 에 찍어서
# 디버깅 시 서버 콘솔 뒤적이지 않고 바로 볼 수 있게.
_IMG_LOG_PATH = Path(_BASE_DIR_FOR_LOG) / "backend" / "logs" / "image_async.log"

def _ilog(msg: str) -> None:
    try:
        _IMG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = _dt.datetime.now().strftime("%H:%M:%S")
        with open(_IMG_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


# v1.1.59: ComfyUI VRAM 수동 해제 엔드포인트.
# 배치 작업 후 모델이 VRAM 에 계속 남아있을 때 프론트에서 호출.
@router.post("/comfyui/free")
async def comfyui_free_memory():
    """ComfyUI 서버의 /free 를 호출해 로딩된 모델/캐시를 VRAM 에서 내린다."""
    from app.services import comfyui_client
    ok = await comfyui_client.free_memory()
    return {"ok": ok}


# v1.1.30: 레퍼런스 이미지가 첨부된 경우, cut.image_prompt 안에 이미 박혀있는
# 색상/조명/분위기/아트스타일 수식어가 레퍼런스 팔레트를 덮어쓰는 현상을 막기 위해
# 런타임에 해당 구문들을 제거한다. DB 원본은 건드리지 않는다.
#
# 전략:
# 1) LLM 이 주로 쓰는 포맷 "[style], [mood], [rendering]: [subject]" 를 감지해서
#    첫 번째 콜론 앞쪽이 "스타일 prefix" 로 보이면 통째로 잘라낸다.
#    (콜론 앞 텍스트 길이가 너무 길면 피사체 설명일 수 있으니 100자 이내만 자른다.)
# 2) 그 뒤에 키워드/구문 단위 스트립을 2차로 돌려서 남은 색상·톤·렌더링 수식어를
#    마저 제거한다.
# 3) 문장 앞뒤 잔여 구두점·공백 정리.

# 콜론 앞쪽이 "스타일 prefix" 인지 판단할 때 사용하는 힌트 단어 집합.
# 이 중 한 개라도 콜론 앞 구간에 들어있으면 그 구간은 스타일 선언으로 판정.
_STYLE_HINT_WORDS = [
    "style", "illustration", "cartoon", "anime", "manga", "cinematic",
    "photorealistic", "realistic", "watercolor", "painting", "sketch",
    "flat design", "line art", "ink", "pixel art", "3d render", "render",
    "tones", "tone", "palette", "colors", "color", "lighting", "lit",
    "golden", "amber", "sepia", "monochrome", "pastel", "muted", "vibrant",
    "retro", "vintage", "moody", "dramatic", "soft", "warm", "cool",
    "bold outlines", "outlines", "clean lines", "high quality", "4k",
    "detailed", "masterpiece", "atmosphere", "atmospheric", "mood",
]

_STYLE_STRIP_PATTERNS = [
    # 컬러 톤/무드
    r"\bwarm\s+golden(?:\s+\w+)?",
    r"\bgolden\s+hour\b",
    r"\bgolden\s+tones?\b",
    r"\bgolden\s+lighting\b",
    r"\bamber\s+tones?\b",
    r"\bmoody\s+lighting\b",
    r"\bdark\s+moody(?:\s+\w+)?",
    r"\bdramatic\s+lighting\b",
    r"\bdramatic\s+and\s+inviting\s+scene\b",
    # 주의: "dramatic scene of X" 같은 경우 scene of 가 피사체 지시문이므로
    # "dramatic" 만 스트립 (아래 standalone 패턴에서 처리) 하고 "scene" 은 남긴다.
    r"\bdramatic\b",
    r"\bcinematic\s+lighting\b",
    r"\bsoft\s+lighting\b",
    r"\bpastel\s+colors?\b",
    r"\bpastel\s+palette\b",
    r"\bmuted\s+colors?\b",
    r"\bmuted\s+palette\b",
    r"\bvibrant\s+colors?\b",
    r"\bneon\s+colors?\b",
    r"\bneon\s+lighting\b",
    r"\bsepia\s+tones?\b",
    r"\bsepia\s+colors?\b",
    r"\bsepia[-\s]toned?\b",
    r"\bhistorical\s+atmosphere\b",
    r"\bvintage\s+atmosphere\b",
    r"\bweathered\s+parchment\b",
    r"\bold\s+parchment\b",
    r"\baged\s+paper\b",
    r"\bgrungy\s+texture\b",
    r"\bgrimy\s+texture\b",
    r"\bdusty\s+atmosphere\b",
    r"\bnostalgic\s+atmosphere\b",
    r"\bnostalgic\s+mood\b",
    r"\bmoody\s+atmosphere\b",
    r"\bdark\s+atmosphere\b",
    r"\bwild\s+and\s+frantic\s+energy\b",
    r"\bchaotic\s+energy\b",
    r"\bfrantic\s+energy\b",
    r"\bwarm\s+and\s+\w+\s+atmosphere\b",
    r"\bmonochrome\b",
    r"\bblack[-\s]and[-\s]white\b",
    r"\bcool\s+blue(?:\s+\w+)?",
    r"\bwarm\s+orange(?:\s+\w+)?",
    r"\bearthy\s+tones?\b",
    r"\brust\s+tones?\b",
    r"\bbronze\s+tones?\b",
    r"\bretro\s+vibes?\b",
    r"\b80s\s+retro\b",
    r"\bvintage\s+palette\b",
    # 렌더링/라인 아트 수식어
    r"\bbold\s+outlines?\b",
    r"\bclean\s+lines?\b",
    r"\bline\s+art(?:\s+style)?\b",
    r"\bflat\s+colors?\b",
    r"\bcel[-\s]shading\b",
    r"\bcel[-\s]shaded\b",
    # 전체 아트스타일 선언
    r"\bstorytelling\s+illustration\s+style\b",
    r"\bcinematic\s+style\b",
    r"\bphotorealistic\b",
    r"\bphoto[-\s]?realistic\b",
    r"\brealistic\s+photo(?:graph)?\b",
    r"\bstudio\s+ghibli\s+style\b",
    r"\bpixar\s+style\b",
    r"\bdisney\s+style\b",
    r"\banime\s+style\b",
    r"\bcartoon\s+style\b",
    r"\bwatercolor\s+style\b",
    r"\boil\s+painting\s+style\b",
    r"\bpencil\s+sketch\s+style\b",
    r"\bdigital\s+painting\s+style\b",
    r"\bflat\s+design\s+style\b",
    r"\billustration\s+style\b",
    # 품질 수식어 (레퍼런스가 있으면 굳이 필요 없고 톤을 비틀 수 있음)
    r"\bhigh\s+quality\b",
    r"\bcinematic\b",
    r"\bdetailed\b",
    r"\bmasterpiece\b",
    r"\b4k\b",
    r"\b8k\b",
]

_STYLE_STRIP_REGEX = re.compile(
    "|".join(f"(?:{p})" for p in _STYLE_STRIP_PATTERNS),
    flags=re.IGNORECASE,
)


def _strip_style_cues(text: str) -> str:
    """레퍼런스 이미지가 붙은 상태에서 cut.image_prompt 에 섞여있는
    색상/조명/톤/아트스타일 수식어를 제거한 뒤 남은 텍스트를 정리해서 반환.

    1단계: 첫 번째 콜론 앞쪽이 100자 이내이고 style hint 단어를 포함하면
          해당 구간 + 콜론을 통째로 잘라낸다. (LLM 이 흔히 쓰는 prefix 포맷)
    2단계: 키워드/구문 패턴 스트립.
    3단계: 잔여 구두점/공백 정리.
    최종 결과가 완전히 비면 원본을 그대로 반환 (피사체까지 날려버리는 걸 방지).
    """
    if not text:
        return text

    cleaned = text

    # 1단계: 콜론 prefix 절단
    colon_idx = cleaned.find(":")
    if 0 < colon_idx <= 120:
        prefix = cleaned[:colon_idx].lower()
        if any(hint in prefix for hint in _STYLE_HINT_WORDS):
            cleaned = cleaned[colon_idx + 1:].lstrip()

    # 2단계: 키워드/구문 스트립
    cleaned = _STYLE_STRIP_REGEX.sub("", cleaned)

    # 3단계: 잔여 구두점 정리
    cleaned = re.sub(r"\s*[,:;]\s*(?=[,:;])", "", cleaned)
    cleaned = re.sub(r"^[\s,:;.\-]+", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    cleaned = re.sub(r"^[\s,:;.\-]+", "", cleaned).strip()
    # 꼬리 구두점 정리
    cleaned = re.sub(r"[\s,:;\-]+$", "", cleaned).strip()

    if not cleaned:
        return text
    return cleaned


def _build_image_prompt(
    image_prompt: str,
    global_style: str,
    *,
    has_reference: bool = False,
    has_character_slot: bool = False,
    character_description: str = "",
) -> str:
    """Build final prompt for image generation.

    v1.1.58: prompt_builder.build_image_prompt 으로 위임.
    라우터와 파이프라인이 동일한 로직을 사용하도록 통일.
    """
    from app.services.image.prompt_builder import build_image_prompt
    return build_image_prompt(
        image_prompt,
        global_style,
        has_reference=has_reference,
        has_character_slot=has_character_slot,
        character_description=character_description,
    )


def _to_relative(project_id: str, abs_path: str) -> str:
    """Convert absolute path to relative path from project dir for DB storage."""
    project_dir = str(DATA_DIR / project_id)
    p = str(abs_path).replace("\\", "/")
    pd = project_dir.replace("\\", "/")
    if p.startswith(pd):
        rel = p[len(pd):]
        return rel.lstrip("/")
    # Already relative or can't convert
    return abs_path


def _collect_reference_images(project_id: str, config: dict) -> list[str]:
    """Collect absolute paths of reference images (style only) for this project."""
    ref_imgs = config.get("reference_images", [])
    project_dir = DATA_DIR / project_id

    paths = []
    for rel in ref_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def _collect_character_images(project_id: str, config: dict) -> list[str]:
    """Collect absolute paths of character images for this project."""
    char_imgs = config.get("character_images", [])
    project_dir = DATA_DIR / project_id

    paths = []
    for rel in char_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def _collect_logo_images(project_id: str, config: dict) -> list[str]:
    """Collect absolute paths of logo images for this project."""
    logo_imgs = config.get("logo_images", [])
    project_dir = DATA_DIR / project_id

    paths = []
    for rel in logo_imgs:
        p = Path(rel)
        abs_path = p if p.is_absolute() else project_dir / rel
        if abs_path.exists():
            paths.append(str(abs_path))
    return paths


def cut_has_character(cut_number: int) -> bool:
    """1-based cut_number 기준, 3컷마다 1장씩 캐릭터 배치.

    즉 cut 1, 4, 7, 10, ... 가 캐릭터 컷.
    DB 마이그레이션 없이 결정적으로 계산 가능해 프론트/백엔드 모두 같은 규칙 적용 가능.
    """
    if cut_number is None or cut_number < 1:
        return False
    return (cut_number - 1) % 3 == 0


def _prompt_mentions_character(prompt: str, config: dict) -> bool:
    """Heuristic: check if an image prompt likely includes a character.

    Strategy:
    1. Extract character names/keywords from global_style and character image filenames
    2. Also check for generic character-related words in the prompt
    3. If we can't extract any keywords, use generic detection
    """
    import re
    global_style = config.get("image_global_prompt", "")
    char_imgs = config.get("character_images", [])

    if not char_imgs:
        return False

    char_keywords = []

    # Extract from global style
    if global_style:
        names = re.findall(r'named\s+(\w+)', global_style, re.IGNORECASE)
        names += re.findall(r'called\s+(\w+)', global_style, re.IGNORECASE)
        names += re.findall(r'이름은\s+(\w+)', global_style)
        names += re.findall(r'캐릭터\s+(\w+)', global_style)
        char_keywords.extend([n.lower() for n in names if len(n) > 1])

    # Generic character-related words to detect character presence in prompt
    generic_char_words = [
        "character", "캐릭터", "キャラクター",
        "person", "figure", "mascot", "protagonist",
        "standing", "holding", "wearing", "sitting",
        "boy", "girl", "man", "woman", "bear", "cat", "dog", "rabbit",
        "explaining", "pointing", "presenting", "looking",
    ]

    prompt_lower = prompt.lower()

    # Check specific character keywords first
    if char_keywords and any(kw in prompt_lower for kw in char_keywords):
        return True

    # Check generic character words (LLM was told to describe character in prompt)
    return any(word in prompt_lower for word in generic_char_words)


@router.post("/{project_id}/generate")
async def generate_all_images(project_id: str, db: Session = Depends(get_db)):
    """Generate all images"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cuts = db.query(Cut).filter(Cut.project_id == project_id).all()
    image_model = project.config.get("image_model", "nano-banana-2")
    aspect_ratio = project.config.get("aspect_ratio", "16:9")

    image_service = get_image_service(image_model)
    try:
        image_service.negative_prompt = (project.config.get("image_negative_prompt") or "").strip()
    except Exception:
        pass
    width, height = get_size(aspect_ratio)

    global_style = project.config.get("image_global_prompt", "")
    character_description = (project.config.get("character_description") or "").strip()
    ref_images = _collect_reference_images(project_id, project.config)
    char_images = _collect_character_images(project_id, project.config)

    results = []
    for cut in cuts:
        if not cut.image_prompt:
            results.append({
                "cut_number": cut.cut_number,
                "status": "skipped",
                "reason": "No image prompt"
            })
            continue

        try:
            image_dir = DATA_DIR / project_id / "images"
            image_dir.mkdir(parents=True, exist_ok=True)
            image_path = str(image_dir / f"cut_{cut.cut_number}.png")

            # v1.1.26: 3컷마다 1장 캐릭터 슬롯 (1, 4, 7, ...)
            is_character_cut = cut_has_character(cut.cut_number) and (bool(char_images) or bool(character_description))
            prompt = _build_image_prompt(
                cut.image_prompt,
                global_style,
                has_reference=bool(ref_images),
                has_character_slot=is_character_cut,
                character_description=character_description,
            )

            # Reference images always attached (for style).
            # Character images attached ONLY on character slots.
            all_refs = list(ref_images)
            if char_images and is_character_cut:
                all_refs.extend(char_images)

            result_path = await image_service.generate(
                prompt,
                width,
                height,
                image_path,
                reference_images=all_refs if all_refs else None,
            )

            cut.image_path = _to_relative(project_id, result_path)
            cut.image_model = image_model
            cut.status = "completed"
            db.commit()

            results.append({
                "cut_number": cut.cut_number,
                "status": "completed",
                "path": cut.image_path,
                "model": image_model,
                "has_character": is_character_cut,
            })
        except Exception as e:
            cut.status = "failed"
            db.commit()
            results.append({
                "cut_number": cut.cut_number,
                "status": "failed",
                "error": str(e)
            })

    # Mark step completed
    step_states = dict(project.step_states or {})
    step_states["4"] = "completed"
    project.step_states = step_states
    db.commit()

    return {
        "project_id": project_id,
        "image_model": image_model,
        "aspect_ratio": aspect_ratio,
        "results": results,
        "total": len(cuts),
        "completed": sum(1 for r in results if r["status"] == "completed")
    }


@router.post("/{project_id}/generate-async")
async def generate_all_images_async(project_id: str, db: Session = Depends(get_db)):
    """Start image generation in background"""
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, register_async_task, is_running

    _ilog(f">>> generate-async ENDPOINT HIT project={project_id}")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        _ilog(f"generate-async 404 project_not_found={project_id}")
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "image"):
        _ilog(f"generate-async already_running project={project_id}")
        return {"status": "already_running", "step": "image"}

    cut_count = db.query(Cut).filter(Cut.project_id == project_id).count()
    state = start_task(project_id, "image", cut_count)

    step_states = dict(project.step_states or {})
    step_states["4"] = "running"
    project.step_states = step_states
    db.commit()

    # v1.1.49: 동시 N장 병렬 생성 (기본 4장)
    # v1.1.56: ComfyUI 로컬 모델일 때는 1로 강제 (GPU 순차 큐).
    CONCURRENT_IMAGES = 4

    async def _run():
        nonlocal CONCURRENT_IMAGES
        from app.models.database import SessionLocal
        from app.services.image.factory import IMAGE_REGISTRY
        local_db = SessionLocal()
        try:
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            image_model = proj.config.get("image_model", "openai-image-1")
            aspect_ratio = proj.config.get("aspect_ratio", "16:9")
            global_style = proj.config.get("image_global_prompt", "")

            if IMAGE_REGISTRY.get(image_model, {}).get("provider") == "comfyui":
                CONCURRENT_IMAGES = 1

            image_service = get_image_service(image_model)
            try:
                image_service.negative_prompt = (proj.config.get("image_negative_prompt") or "").strip()
            except Exception:
                pass
            width, height = get_size(aspect_ratio)
            ref_images = _collect_reference_images(project_id, proj.config)
            char_images = _collect_character_images(project_id, proj.config)
            character_description = (proj.config.get("character_description") or "").strip()

            cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()

            # 프롬프트 없는 컷은 건너뛰기
            cut_specs = []
            for cut in cuts:
                if not cut.image_prompt:
                    continue
                cut_specs.append(cut)

            image_dir = DATA_DIR / project_id / "images"
            image_dir.mkdir(parents=True, exist_ok=True)

            semaphore = asyncio.Semaphore(CONCURRENT_IMAGES)
            done_count = 0

            _ilog(f"=== generate_all_images project={project_id} model={image_model} refs={len(ref_images)} chars={len(char_images)} cut_specs={len(cut_specs)} ===")

            async def _gen_one(cut):
                nonlocal done_count
                if state.status != "running":
                    _ilog(f"_gen_one cut={cut.cut_number} early_exit status={state.status}")
                    return
                async with semaphore:
                    if state.status != "running":
                        _ilog(f"_gen_one cut={cut.cut_number} exit_after_sem status={state.status}")
                        return
                    image_path = str(image_dir / f"cut_{cut.cut_number}.png")
                    is_character_cut = cut_has_character(cut.cut_number) and (bool(char_images) or bool(character_description))
                    prompt = _build_image_prompt(
                        cut.image_prompt,
                        global_style,
                        has_reference=bool(ref_images),
                        has_character_slot=is_character_cut,
                        character_description=character_description,
                    )
                    all_refs = list(ref_images)
                    if char_images and is_character_cut:
                        all_refs.extend(char_images)
                    _ilog(f"_gen_one cut={cut.cut_number} call generate() refs={len(all_refs)} svc={type(image_service).__name__}")
                    import time as _t
                    _s = _t.time()
                    try:
                        result_path = await image_service.generate(
                            prompt, width, height, image_path,
                            reference_images=all_refs if all_refs else None,
                        )
                        _ilog(f"_gen_one cut={cut.cut_number} SUCCESS in {_t.time()-_s:.1f}s → {result_path}")
                        cut.image_path = _to_relative(project_id, result_path)
                        cut.image_model = image_model
                        cut.status = "completed"
                        # v1.1.55-fix: 스튜디오 이미지 생성 비용 기록
                        try:
                            from app.services import spend_ledger
                            spend_ledger.record_image(
                                image_model, n_images=1,
                                project_id=project_id, note=f"studio cut_{cut.cut_number}",
                            )
                        except Exception as _le:
                            print(f"[spend_ledger] studio image record skipped: {_le}")
                    except Exception as e:
                        import traceback as _tb
                        print(f"[image] Cut {cut.cut_number} failed: {e}")
                        _ilog(f"_gen_one cut={cut.cut_number} FAILED after {_t.time()-_s:.1f}s: {type(e).__name__}: {e}\n{_tb.format_exc()[-800:]}")
                        cut.status = "failed"
                    local_db.commit()
                    done_count += 1
                    update_task(project_id, "image", done_count)

            tasks = [asyncio.create_task(_gen_one(c)) for c in cut_specs]
            await asyncio.gather(*tasks, return_exceptions=True)
            _ilog(f"=== all tasks gathered. done_count={done_count} ===")

            # 프롬프트 없는 컷도 카운트에 포함
            update_task(project_id, "image", len(cuts))

            # v1.1.55-fix: 실제 생성된 이미지 수 검증 — 0개면 failed 처리
            import os as _os
            _img_dir = DATA_DIR / project_id / "images"
            _generated = [
                f for f in _img_dir.glob("cut_*.png")
                if f.stat().st_size > 50
            ] if _img_dir.exists() else []
            _ilog(f"=== post-check: {len(_generated)}/{len(cut_specs)} images on disk ===")

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj.step_states or {})
            if _generated:
                ss["4"] = "completed"
                proj.step_states = ss
                local_db.commit()
                complete_task(project_id, "image")
            else:
                ss["4"] = "failed"
                proj.step_states = ss
                local_db.commit()
                fail_task(project_id, "image", f"이미지 0/{len(cut_specs)}개 생성됨 — API 키/잔액 확인 필요")

            # v1.1.59: 배치 종료 → ComfyUI VRAM 해제
            if IMAGE_REGISTRY.get(image_model, {}).get("provider") == "comfyui":
                try:
                    from app.services import comfyui_client
                    await comfyui_client.free_memory()
                except Exception as _e:
                    print(f"[image] VRAM 해제 스킵: {_e}")
        except Exception as e:
            fail_task(project_id, "image", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                ss = dict(proj.step_states or {})
                ss["4"] = "failed"
                proj.step_states = ss
                local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "image", task)
    return {"status": "started", "step": "image", "total": cut_count}


@router.post("/{project_id}/resume-async")
async def resume_images_async(project_id: str, db: Session = Depends(get_db)):
    """Resume image generation — only generate cuts that don't have images yet"""
    import asyncio
    from app.services.task_manager import start_task, update_task, complete_task, fail_task, register_async_task, is_running

    _ilog(f">>> resume-async ENDPOINT HIT project={project_id}")
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        _ilog(f"resume-async 404 project_not_found={project_id}")
        raise HTTPException(404, "Project not found")

    if is_running(project_id, "image"):
        _ilog(f"resume-async already_running project={project_id}")
        return {"status": "already_running", "step": "image"}

    cuts = db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
    pending_cuts = [c for c in cuts if not c.image_path and c.image_prompt]
    if not pending_cuts:
        _ilog(f"resume-async nothing_to_resume project={project_id} cuts={len(cuts)}")
        return {"status": "nothing_to_resume", "step": "image", "total": 0}
    _ilog(f"resume-async pending={len(pending_cuts)} of {len(cuts)} project={project_id}")

    state = start_task(project_id, "image", len(pending_cuts))

    step_states = dict(project.step_states or {})
    step_states["4"] = "running"
    project.step_states = step_states
    db.commit()

    # v1.1.49: 병렬 생성
    # v1.1.56: ComfyUI 로컬 모델일 때는 1로 강제 (GPU 순차 큐).
    CONCURRENT_IMAGES = 4

    async def _run():
        nonlocal CONCURRENT_IMAGES
        from app.models.database import SessionLocal
        from app.services.image.factory import IMAGE_REGISTRY
        local_db = SessionLocal()
        try:
            proj = local_db.query(Project).filter(Project.id == project_id).first()
            image_model = proj.config.get("image_model", "openai-image-1")
            aspect_ratio = proj.config.get("aspect_ratio", "16:9")
            global_style = proj.config.get("image_global_prompt", "")

            if IMAGE_REGISTRY.get(image_model, {}).get("provider") == "comfyui":
                CONCURRENT_IMAGES = 1

            image_service = get_image_service(image_model)
            _ilog(f"resume _run service={type(image_service).__name__} model={image_model} aspect={aspect_ratio}")
            try:
                image_service.negative_prompt = (proj.config.get("image_negative_prompt") or "").strip()
            except Exception:
                pass
            width, height = get_size(aspect_ratio)
            ref_images = _collect_reference_images(project_id, proj.config)
            char_images = _collect_character_images(project_id, proj.config)
            character_description = (proj.config.get("character_description") or "").strip()

            db_cuts = local_db.query(Cut).filter(Cut.project_id == project_id).order_by(Cut.cut_number).all()
            pending = [c for c in db_cuts if not c.image_path and c.image_prompt]
            _ilog(f"resume _run pending={len(pending)} refs={len(ref_images)} chars={len(char_images)}")

            image_dir = DATA_DIR / project_id / "images"
            image_dir.mkdir(parents=True, exist_ok=True)

            semaphore = asyncio.Semaphore(CONCURRENT_IMAGES)
            done_count = 0

            async def _gen_one(cut):
                nonlocal done_count
                if state.status != "running":
                    _ilog(f"resume _gen_one cut={cut.cut_number} early_exit status={state.status}")
                    return
                async with semaphore:
                    if state.status != "running":
                        _ilog(f"resume _gen_one cut={cut.cut_number} exit_after_sem status={state.status}")
                        return
                    image_path = str(image_dir / f"cut_{cut.cut_number}.png")
                    is_character_cut = cut_has_character(cut.cut_number) and (bool(char_images) or bool(character_description))
                    prompt = _build_image_prompt(
                        cut.image_prompt,
                        global_style,
                        has_reference=bool(ref_images),
                        has_character_slot=is_character_cut,
                        character_description=character_description,
                    )
                    all_refs = list(ref_images)
                    if char_images and is_character_cut:
                        all_refs.extend(char_images)
                    _ilog(f"resume _gen_one cut={cut.cut_number} call generate() refs={len(all_refs)}")
                    import time as _t
                    _s = _t.time()
                    try:
                        result_path = await image_service.generate(
                            prompt, width, height, image_path,
                            reference_images=all_refs if all_refs else None,
                        )
                        _ilog(f"resume _gen_one cut={cut.cut_number} SUCCESS in {_t.time()-_s:.1f}s → {result_path}")
                        cut.image_path = _to_relative(project_id, result_path)
                        cut.image_model = image_model
                        cut.status = "completed"
                    except Exception as e:
                        import traceback
                        print(f"[image-resume] Cut {cut.cut_number} failed: {e}\n{traceback.format_exc()}")
                        _ilog(f"resume _gen_one cut={cut.cut_number} FAILED after {_t.time()-_s:.1f}s: {type(e).__name__}: {e}\n{traceback.format_exc()[-600:]}")
                        cut.status = "failed"
                    local_db.commit()
                    done_count += 1
                    update_task(project_id, "image", done_count)

            tasks = [asyncio.create_task(_gen_one(c)) for c in pending]
            await asyncio.gather(*tasks, return_exceptions=True)

            proj = local_db.query(Project).filter(Project.id == project_id).first()
            ss = dict(proj.step_states or {})
            ss["4"] = "completed"
            proj.step_states = ss
            local_db.commit()
            complete_task(project_id, "image")

            # v1.1.59: 배치 종료 → ComfyUI VRAM 해제
            if IMAGE_REGISTRY.get(image_model, {}).get("provider") == "comfyui":
                try:
                    from app.services import comfyui_client
                    await comfyui_client.free_memory()
                except Exception as _e:
                    print(f"[image-resume] VRAM 해제 스킵: {_e}")
        except BaseException as e:
            import traceback
            print(f"[image-resume] Task failed: {e}\n{traceback.format_exc()}")
            fail_task(project_id, "image", str(e))
            try:
                proj = local_db.query(Project).filter(Project.id == project_id).first()
                if proj:
                    ss = dict(proj.step_states or {})
                    ss["4"] = "failed"
                    proj.step_states = ss
                    local_db.commit()
            except:
                pass
        finally:
            local_db.close()

    task = asyncio.create_task(_run())
    register_async_task(project_id, "image", task)
    return {"status": "started", "step": "image", "total": len(pending_cuts), "skipped": len(cuts) - len(pending_cuts)}


@router.post("/{project_id}/generate/{cut_number}")
async def generate_one_image(
    project_id: str,
    cut_number: int,
    db: Session = Depends(get_db)
):
    """Regenerate one cut's image"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cut = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == cut_number
    ).first()

    if not cut:
        raise HTTPException(404, f"Cut {cut_number} not found")

    if not cut.image_prompt:
        raise HTTPException(400, "Cut has no image prompt")

    image_model = project.config.get("image_model", "nano-banana-2")
    aspect_ratio = project.config.get("aspect_ratio", "16:9")

    image_service = get_image_service(image_model)
    try:
        image_service.negative_prompt = (project.config.get("image_negative_prompt") or "").strip()
    except Exception:
        pass
    width, height = get_size(aspect_ratio)
    global_style = project.config.get("image_global_prompt", "")
    character_description = (project.config.get("character_description") or "").strip()
    ref_images = _collect_reference_images(project_id, project.config)
    char_images = _collect_character_images(project_id, project.config)

    try:
        image_dir = DATA_DIR / project_id / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = str(image_dir / f"cut_{cut_number}.png")

        is_character_cut = cut_has_character(cut_number) and (bool(char_images) or bool(character_description))
        prompt = _build_image_prompt(
            cut.image_prompt,
            global_style,
            has_reference=bool(ref_images),
            has_character_slot=is_character_cut,
            character_description=character_description,
        )

        all_refs = list(ref_images)
        if char_images and is_character_cut:
            all_refs.extend(char_images)

        result_path = await image_service.generate(
            prompt,
            width,
            height,
            image_path,
            reference_images=all_refs if all_refs else None,
        )

        cut.image_path = _to_relative(project_id, result_path)
        cut.image_model = image_model
        cut.status = "completed"
        # v1.1.55-fix: 단건 이미지 생성 비용 기록
        try:
            from app.services import spend_ledger
            spend_ledger.record_image(
                image_model, n_images=1,
                project_id=project_id, note=f"studio single cut_{cut_number}",
            )
        except Exception as _le:
            print(f"[spend_ledger] studio single image record skipped: {_le}")
        db.commit()

        return {
            "cut_number": cut_number,
            "status": "completed",
            "path": cut.image_path,
            "model": image_model,
            "has_character": is_character_cut,
        }
    except Exception as e:
        cut.status = "failed"
        db.commit()
        raise HTTPException(500, f"Image generation failed: {str(e)}")


@router.post("/{project_id}/reference/upload")
async def upload_reference_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload reference/style image"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        ref_dir = DATA_DIR / project_id / "references"
        ref_dir.mkdir(parents=True, exist_ok=True)

        ref_path = ref_dir / f"reference_{file.filename}"
        content = await file.read()
        with open(ref_path, "wb") as f:
            f.write(content)

        # Save to project config
        # v1.1.29: SQLAlchemy 는 JSON 컬럼의 in-place mutation 을 감지 못 한다.
        # 새 dict 를 할당해도 plain JSON Column 은 dirty 마킹이 불안정하므로
        # flag_modified 로 명시적으로 dirty 를 찍어서 commit 에 반영시킨다.
        config = dict(project.config) if project.config else {}
        refs = list(config.get("reference_images", []) or [])
        rel_path = f"references/reference_{file.filename}"
        if rel_path not in refs:
            refs.append(rel_path)
        config["reference_images"] = refs
        project.config = config
        flag_modified(project, "config")
        db.commit()

        return {"status": "uploaded", "path": rel_path, "total_refs": len(refs)}
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.post("/{project_id}/character/upload")
async def upload_character_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload character consistency image"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        char_dir = DATA_DIR / project_id / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)

        char_path = char_dir / f"char_{file.filename}"
        content = await file.read()
        with open(char_path, "wb") as f:
            f.write(content)

        config = dict(project.config) if project.config else {}
        chars = list(config.get("character_images", []) or [])
        rel_path = f"characters/char_{file.filename}"
        if rel_path not in chars:
            chars.append(rel_path)
        config["character_images"] = chars
        project.config = config
        flag_modified(project, "config")
        db.commit()

        return {"status": "uploaded", "path": rel_path, "total_chars": len(chars)}
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.delete("/{project_id}/reference/{filename}")
async def delete_reference_image(project_id: str, filename: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    config = dict(project.config) if project.config else {}
    refs = list(config.get("reference_images", []) or [])
    target = f"references/{filename}"
    refs = [r for r in refs if r != target]
    config["reference_images"] = refs
    project.config = config
    flag_modified(project, "config")
    db.commit()
    # Delete file
    try:
        (DATA_DIR / project_id / target).unlink(missing_ok=True)
    except:
        pass
    return {"status": "deleted"}


@router.post("/{project_id}/logo/upload")
async def upload_logo_image(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload logo/watermark image (used in interlude + image generation branding)."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    try:
        logo_dir = DATA_DIR / project_id / "logos"
        logo_dir.mkdir(parents=True, exist_ok=True)

        logo_path = logo_dir / f"logo_{file.filename}"
        content = await file.read()
        with open(logo_path, "wb") as f:
            f.write(content)

        config = dict(project.config) if project.config else {}
        logos = list(config.get("logo_images", []) or [])
        rel_path = f"logos/logo_{file.filename}"
        if rel_path not in logos:
            logos.append(rel_path)
        config["logo_images"] = logos
        project.config = config
        flag_modified(project, "config")
        db.commit()

        return {"status": "uploaded", "path": rel_path, "total_logos": len(logos)}
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.delete("/{project_id}/logo/{filename}")
async def delete_logo_image(project_id: str, filename: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    config = dict(project.config) if project.config else {}
    logos = list(config.get("logo_images", []) or [])
    target = f"logos/{filename}"
    logos = [l for l in logos if l != target]
    config["logo_images"] = logos
    project.config = config
    flag_modified(project, "config")
    db.commit()
    try:
        (DATA_DIR / project_id / target).unlink(missing_ok=True)
    except:
        pass
    return {"status": "deleted"}


@router.get("/{project_id}/character-slots")
def list_character_slots(project_id: str, db: Session = Depends(get_db)):
    """각 컷의 has_character 플래그를 반환 — 3컷마다 1장 캐릭터 배치 규칙.

    프론트의 StepImage 가 '캐릭터 등장 컷' 배지 표시에 사용.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    cuts = (
        db.query(Cut)
        .filter(Cut.project_id == project_id)
        .order_by(Cut.cut_number.asc())
        .all()
    )
    return {
        "project_id": project_id,
        "slots": [
            {
                "cut_number": c.cut_number,
                "has_character": cut_has_character(c.cut_number),
            }
            for c in cuts
        ],
    }


@router.get("/{project_id}/assets")
def list_project_assets(project_id: str, db: Session = Depends(get_db)):
    """현재 프로젝트에 등록된 레퍼런스/캐릭터/로고 이미지 목록을 반환.

    프론트 `StepSettings` 의 레퍼런스 섹션이 사용.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    cfg = project.config or {}

    def _present(rel_list: list[str]) -> list[dict]:
        out = []
        for rel in rel_list or []:
            abs_p = DATA_DIR / project_id / rel
            out.append({
                "path": rel,
                "filename": Path(rel).name,
                "exists": abs_p.exists(),
            })
        return out

    return {
        "project_id": project_id,
        "reference_images": _present(cfg.get("reference_images", [])),
        "character_images": _present(cfg.get("character_images", [])),
        "logo_images": _present(cfg.get("logo_images", [])),
    }


@router.delete("/{project_id}/character/{filename}")
async def delete_character_image(project_id: str, filename: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    config = dict(project.config) if project.config else {}
    chars = list(config.get("character_images", []) or [])
    target = f"characters/{filename}"
    chars = [c for c in chars if c != target]
    config["character_images"] = chars
    project.config = config
    flag_modified(project, "config")
    db.commit()
    try:
        (DATA_DIR / project_id / target).unlink(missing_ok=True)
    except:
        pass
    return {"status": "deleted"}


@router.post("/{project_id}/{cut_number}/upload")
async def upload_custom_image(
    project_id: str,
    cut_number: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload custom image"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    cut = db.query(Cut).filter(
        Cut.project_id == project_id,
        Cut.cut_number == cut_number
    ).first()

    if not cut:
        raise HTTPException(404, f"Cut {cut_number} not found")

    try:
        image_dir = DATA_DIR / project_id / "images"
        image_dir.mkdir(parents=True, exist_ok=True)

        # Save uploaded file
        image_path = image_dir / f"cut_{cut_number}_custom.png"
        content = await file.read()
        with open(image_path, "wb") as f:
            f.write(content)

        cut.image_path = _to_relative(project_id, str(image_path))
        cut.is_custom_image = True
        cut.status = "completed"
        db.commit()

        return {
            "cut_number": cut_number,
            "status": "uploaded",
            "path": str(image_path),
            "is_custom": True
        }
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")
