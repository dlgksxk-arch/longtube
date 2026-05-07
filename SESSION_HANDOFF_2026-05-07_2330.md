# SESSION HANDOFF 2026-05-07 23:30 KST

## 사용자 지시

- 추론하지 않는다. 실제를 바탕으로 답변한다.
- 추측성으로 변경하지 않는다. 정확히 해야 할 것만 한다.
- 좆나 설명하지 않는다.
- 말투는 자비스 말투를 쓴다.
- 반말하지 않는다.
- 생성 결과물에 문제가 발견되었을 때 결과물 직접 수정은 절대 금한다.
- 결과물 문제는 로직을 수정해서 다음 생성물에 적용되게 한다.
- 지시가 애매하면 반드시 다시 질문한다.
- 사용자가 명시적으로 요구한 핵심:
  - 작업대에서 진행되는 생성은 스튜디오에서 쓰던 생성 프롬프트와 파이프라인을 그대로 써야 한다.
  - 비슷하게 만들지 말고, 기존 스튜디오 설정 파일/프롬프트/로직에 연결해서 써야 한다.
  - 기존에 잘 만들어져 있는 스튜디오 프롬프트나 로직 자체를 변경하지 말아야 한다.
  - 현재 생성 결과물에 대한 직접 수정은 하지 말아야 한다.

## 현재 저장 시점

- 작업 디렉터리: `C:\Users\Ai_M9\Desktop\longtube`
- 저장 시각: 2026-05-07 23:30 KST
- 백엔드 실행 확인:
  - 프로세스: `python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - 확인 URL: `http://127.0.0.1:8000/docs`
  - 응답: `200`

## 현재 git 변경 파일

다음 파일들이 수정 상태다.

```text
 M backend/app/routers/oneclick.py
 M backend/app/services/llm/claude_service.py
 M backend/app/services/oneclick_service.py
 M backend/app/services/oneclick_stability_helpers.py
 M backend/app/services/thumbnail_service.py
 M backend/app/tasks/pipeline_tasks.py
 M frontend/src/app/oneclick/layout.tsx
 M frontend/src/app/oneclick/live/page.tsx
 M frontend/src/app/oneclick/live/queueHelpers.ts
 M frontend/src/app/oneclick/upload-pending/page.tsx
 M frontend/src/app/page.tsx
 M frontend/src/app/v2/layout.tsx
 M frontend/src/app/v2/live/page.tsx
 M frontend/src/lib/api.ts
```

## 이번 저장 직전 실제로 마친 작업

### 1. 작업대 대본 생성 경로를 스튜디오 대본 생성 순서에 맞춤

수정 파일:

- `backend/app/tasks/pipeline_tasks.py`

스튜디오 기준 파일:

- `backend/app/routers/script.py`

스튜디오 라우터의 실제 순서:

```text
generate_script
apply_script_visual_policy
annotate_script_shorts
assert_script_timing
script_title_for_language
_strip_script_motion_prompts
save/db cuts
```

작업대 `_step_script`를 위 순서와 맞췄다.

변경 내용:

- `annotate_script_shorts` import 추가.
- `_step_script`에서 `apply_script_visual_policy(script)` 직후 `annotate_script_shorts(script)` 실행.
- `script_title_for_language(...)` 호출에서 작업대 전용 `first_narration` 전달 제거.
- 스튜디오 라우터의 `_strip_script_motion_prompts`를 import해서 사용.
- `save_script(...)` 내부도 `_strip_script_motion_prompts`를 사용하도록 변경.

중요:

- `backend/app/routers/script.py`는 수정하지 않았다.
- 스튜디오 대본 생성 프롬프트 파일은 수정하지 않았다.
- 새 대본 프롬프트를 만들지 않았다.

### 2. 작업대 이미지 프롬프트 생성 경로를 스튜디오 이미지 함수에 연결

수정 파일:

- `backend/app/tasks/pipeline_tasks.py`

스튜디오 기준 파일:

- `backend/app/routers/image.py`

작업대 `_step_image`에서 직접 쓰던 prompt_builder 함수 일부를 스튜디오 라우터 함수로 교체했다.

변경 내용:

- 제거:
  - `build_image_prompt`
  - `historical_negative_prompt`
  - `map_negative_prompt`
  - `symbol_negative_prompt`
  - `text_negative_prompt`
- 추가:
  - `from app.routers.image import _apply_historical_negative_prompt, _build_image_prompt`
- 네거티브 프롬프트 조립을 직접 하지 않고 `_apply_historical_negative_prompt(...)` 호출.
- 컷 이미지 프롬프트 최종 조립을 `build_image_prompt(...)` 대신 `_build_image_prompt(...)` 호출로 변경.

중요:

- `backend/app/routers/image.py`는 수정하지 않았다.
- 스튜디오 이미지 프롬프트 로직 자체는 수정하지 않았다.
- 새 이미지 프롬프트를 만들지 않았다.
- `collect_reference_images`, `collect_character_images`는 작업대 기존 경로를 유지했다.
  - 이유: 작업대 프로젝트는 채널 폴더 경로를 쓰므로, 스튜디오 라우터의 DATA_DIR 기준 수집 함수를 그대로 쓰면 경로가 달라질 수 있다.
  - 이 부분은 새 프롬프트가 아니라 파일 경로 수집이다.

## 이번 저장 직전 검증

실행한 명령:

```powershell
python -m py_compile backend\app\tasks\pipeline_tasks.py
```

결과:

```text
통과
```

실행한 import 확인:

```powershell
$env:PYTHONIOENCODING='utf-8'; @'
import sys
sys.path.insert(0, 'backend')
from app.tasks.pipeline_tasks import _step_script, _step_image
from app.routers.script import _strip_script_motion_prompts
from app.routers.image import _build_image_prompt, _apply_historical_negative_prompt
print('ok')
'@ | python -
```

결과:

```text
ok
```

백엔드 재시작 후 확인:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8000/docs -UseBasicParsing -TimeoutSec 10
```

결과:

```text
docs_status=200
```

## `backend/app/tasks/pipeline_tasks.py` 현재 diff

```diff
diff --git a/backend/app/tasks/pipeline_tasks.py b/backend/app/tasks/pipeline_tasks.py
index 7e41b0c..5f3521d 100644
--- a/backend/app/tasks/pipeline_tasks.py
+++ b/backend/app/tasks/pipeline_tasks.py
@@ -12,6 +12,7 @@ from app.models.project import Project
 from app.models.cut import Cut
 from app.services.title_utils import script_title_for_language, with_episode_prefix, without_episode_prefix
 from app.services.llm.visual_policy import apply_script_visual_policy, normalize_cut_image_prompt, normalize_image_prompt
+from app.services.shorts_service import annotate_script_shorts
 from app.services.youtube_metadata import expand_tags, format_description
 from app.services.multilingual_caption_service import should_upload_youtube_captions, upload_multilingual_captions
 
@@ -178,14 +179,13 @@ def _ensure_project_layout(project_id: str):
 
 def save_script(project_id: str, script: dict, language: str = "ko"):
     try:
-        from app.services.shorts_service import annotate_script_shorts
-        script = annotate_script_shorts(script)
+        from app.routers.script import _strip_script_motion_prompts
+        script = _strip_script_motion_prompts(script)
     except Exception:
-        pass
-    for cut_data in script.get("cuts", []) or []:
-        if isinstance(cut_data, dict):
-            cut_data.pop("motion_prompt", None)
-            cut_data.pop("video_motion_prompt", None)
+        for cut_data in script.get("cuts", []) or []:
+            if isinstance(cut_data, dict):
+                cut_data.pop("motion_prompt", None)
+                cut_data.pop("video_motion_prompt", None)
     project_dir = _ensure_project_layout(project_id)
     path = project_dir / "script.json"
     with open(path, "w", encoding="utf-8") as f:
@@ -480,6 +480,7 @@ def _step_script(project_id: str, config: dict):
     if script is None:
         raise RuntimeError("Script generation failed")
     script = apply_script_visual_policy(script)
+    script = annotate_script_shorts(script)
     service.assert_script_timing(script, script_config)
 
     # v1.1.48: LLM 완료 후에도 취소 여부 확인
@@ -491,8 +492,15 @@ def _step_script(project_id: str, config: dict):
         topic=project.topic,
         episode_number=config.get("episode_number"),
         language=config.get("language", "ko"),
-        first_narration=(script.get("cuts") or [{}])[0].get("narration") if script.get("cuts") else None,
     )
+    try:
+        from app.routers.script import _strip_script_motion_prompts
+        script = _strip_script_motion_prompts(script)
+    except Exception:
+        for cut_data in script.get("cuts", []) or []:
+            if isinstance(cut_data, dict):
+                cut_data.pop("motion_prompt", None)
+                cut_data.pop("video_motion_prompt", None)
     save_script(project_id, script, config.get("language", "ko"))
 
     db.query(Cut).filter(Cut.project_id == project_id).delete()
@@ -920,15 +928,14 @@ def _step_image(project_id: str, config: dict):
     from app.services.image.base import get_size
     from app.services.image.prompt_builder import (
         append_prompt_specific_negative_prompt,
-        build_image_prompt,
         collect_reference_images,
         collect_character_images,
         cut_has_character,
         should_enable_historical_guard_for_context,
-        historical_negative_prompt,
-        map_negative_prompt,
-        symbol_negative_prompt,
-        text_negative_prompt,
+    )
+    from app.routers.image import (
+        _apply_historical_negative_prompt,
+        _build_image_prompt,
     )
     from app.services.image.asset_guard import (
         canonical_cut_image_path,
@@ -996,33 +1003,14 @@ def _step_image(project_id: str, config: dict):
             pass
     # v1.1.59: 사용자 네거티브 프롬프트 주입 (ComfyUI 만 반영; 그 외 서비스는 무시)
     try:
-        negative_prompt = (config.get("image_negative_prompt") or "").strip()
-        text_negative = text_negative_prompt()
-        if text_negative and text_negative not in negative_prompt:
-            negative_prompt = f"{text_negative}, {negative_prompt}".strip(" ,")
-        map_negative = map_negative_prompt()
-        if map_negative and map_negative not in negative_prompt:
-            negative_prompt = f"{map_negative}, {negative_prompt}".strip(" ,")
-        symbol_negative = symbol_negative_prompt()
-        if symbol_negative and symbol_negative not in negative_prompt:
-            negative_prompt = f"{symbol_negative}, {negative_prompt}".strip(" ,")
-        guard_negative = historical_negative_prompt(
-            " ".join(
-                str(x or "")
-                for x in (
-                    project_id,
-                    config.get("title"),
-                    config.get("topic"),
-                    config.get("image_global_prompt"),
-                    script.get("title"),
-                    script.get("topic"),
-                )
-            ),
-            enable_historical_negative_guard,
+        service.negative_prompt = (config.get("image_negative_prompt") or "").strip()
+        _apply_historical_negative_prompt(
+            service,
+            config,
+            project_id,
+            config.get("title"),
+            config.get("topic"),
         )
-        if guard_negative and guard_negative not in negative_prompt:
-            negative_prompt = f"{guard_negative}, {negative_prompt}".strip(" ,")
-        service.negative_prompt = negative_prompt
     except Exception:
         pass
     base_negative_prompt = (getattr(service, "negative_prompt", "") or "").strip()
@@ -1072,7 +1060,7 @@ def _step_image(project_id: str, config: dict):
         is_char_cut = cut_has_character(num) and has_character_anchor
         prompt_source = (cut.image_prompt if cut and cut.image_prompt else cut_data.get("image_prompt", "")) or ""
         prompt_narration = (cut.narration if cut and cut.narration else cut_data.get("narration", "")) or ""
-        prompt = build_image_prompt(
+        prompt = _build_image_prompt(
             normalize_cut_image_prompt(
                 prompt_source,
                 prompt_narration,
```

## 이전 대화에서 확인된 현재 CH3 EP6 상태

실제 확인된 값:

- project_id: `딸깍_CH3_EP6_260506-1`
- script path: `C:\Users\Ai_M9\Desktop\longsult\channels\CH3\projects\딸깍_CH3_EP6_260506-1\script.json`
- 컷 수: 120
- `_partial`: 없음
- 누락 컷 번호: 없음
- 중복 컷 번호: 없음

대본 품질 확인에서 발견된 값:

- 모든 컷에 다음 필드가 없었다.
  - `visual_year`
  - `visual_period`
  - `visual_location`
  - `visual_evidence`
  - `duration_estimate`
- final `image_prompt`에 required style 문구가 빠져 있었다.
- 일본어 narration 39개가 45자 초과였다.
- 이미지 프롬프트가 일반적이었다.

중요:

- 위 생성 결과물 자체는 직접 수정하지 않았다.
- 사용자는 결과물 직접 수정 금지, 로직 수정만 허용했다.

## CH3 템플릿 관련 실제 확인 값

- CH3 template id: `7d8b63e5`
- `image_global_prompt`: 빈 문자열
- `image_negative_prompt`: 빈 문자열
- `visual_mode`: `simple_cartoon`
- `image_model`: `comfyui-dreamshaper-xl-longtube`
- `language`: `ja`
- `script_model`: `claude-sonnet-4-6`
- `content_required` / `content_forbidden`: CH3 규칙 존재
- queue `channel_presets`: `"3": "7d8b63e5"`

## 이전에 적용되어 있는 주요 수정 상태

아래 내용은 현재 git status에 보이는 다른 파일들과 관련된 기존 진행 상태다.

### 작업대/큐 UI

관련 파일:

- `frontend/src/app/oneclick/live/page.tsx`
- `frontend/src/app/oneclick/live/queueHelpers.ts`
- `frontend/src/app/oneclick/layout.tsx`
- `frontend/src/app/v2/live/page.tsx`
- `frontend/src/app/v2/layout.tsx`
- `frontend/src/app/page.tsx`

반영된 방향:

- `실시간 현황` 명칭을 `작업대`로 변경.
- 스케줄 메뉴 삭제.
- 전체 작업 큐에서 `실행`을 눌렀을 때 즉시 자동생성 시작하지 않고 순번 1번으로 올리는 방향.
- 작업대에서 `시작`을 눌러야 자동생성 시작.
- 이후는 정해진 큐/시간에 따라 다음 작업이 이어지는 방향.
- 큐 표시를 1, 2, 3 순번 형태로 표현.

### 큐/복귀/작업 유실 방지

관련 파일:

- `backend/app/routers/oneclick.py`
- `backend/app/services/oneclick_service.py`
- `backend/app/services/oneclick_stability_helpers.py`
- `frontend/src/lib/api.ts`

반영된 방향:

- 작업대에 에피소드가 올라올 때 기존 진행 자료가 있으면 불러오는 방향.
- 진행 자료가 있으면 실제 진행 프로세스에 표시하고 `이어하기`로 표현하는 방향.
- 기존 작업이 없을 때 시작 순간 새 task를 만들 수 있도록 하는 방향.
- `_partial` script는 완료 대본으로 보지 않는 방향.
- script가 없거나 partial이면 script 단계부터 재개하는 방향.
- task estimate refresh 관련 처리 추가.

### 대본 생성

관련 파일:

- `backend/app/services/llm/claude_service.py`

현재 방향:

- 40컷 청크 방식 유지.
- max token 제한 관련 수정이 들어간 상태.
- 컷당 5초 조건을 요청문에 강하게 넣은 상태.
- 청크 성공분을 `script.partial.json`과 `_partial` `script.json`에 저장하는 방향.
- 청크 중간 실패 시 성공한 청크를 보존하는 방향.

중요:

- 사용자는 120컷 1회 요청으로 비용이 증가하는 것을 거부했고, 원래 방식으로 돌리라고 지시했다.
- 사용자는 실패해도 성공 청크는 저장해야 한다고 지시했다.

### 썸네일

관련 파일:

- `backend/app/services/thumbnail_service.py`

반영된 방향:

- 썸네일 제목이 길어도 잘라내지 않고 줄맞춤으로 붙이는 방향.

## 다음 작업자가 반드시 지켜야 할 것

- 스튜디오 프롬프트/로직 파일을 직접 수정하지 않는다.
- 작업대 쪽에서 새 프롬프트를 만들지 않는다.
- 작업대는 스튜디오의 기존 함수/설정/프롬프트를 호출하게만 연결한다.
- 생성 결과물 파일을 직접 고치지 않는다.
- CH3 EP6의 기존 생성물 문제는 로직 수정으로 다음 생성부터 반영한다.
- 사용자에게 추측성 설명을 하지 않는다.
- 애매한 지시는 질문한다.

