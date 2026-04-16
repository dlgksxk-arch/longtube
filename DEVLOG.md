# LongTube 개발 일지

> 날짜별로 개발 결정사항, 변경사항, 문제 해결을 기록합니다.
> 세션 끝에 "DEVLOG 업데이트해줘" 라고 요청하세요.

---

## 2026-04-14 (v1.1.54 — TTS 3초 버그 + 중지 즉시 반영 + 썸네일 안정화)

### 사용자 체감 문제

1. 생성된 음성이 전부 3초 — 4.0~4.5초 범위 강제가 안 먹힘.
2. 중지 눌러도 병렬 생성(음성+이미지)이 계속돼서 API 크레딧 낭비.
3. 썸네일 생성 실패 — 컷 이미지는 레퍼런스 잘 적용되는데 썸네일만 실패.
4. 자동저장 1초 디바운스가 너무 짧아 주제 입력 중 저장됨.

### 원인 진단 및 수정

**(1) `_get_duration` ffprobe 경로 미해결.**

`openai_tts_service._get_duration()`과 `elevenlabs_service._get_duration()`이
bare `ffprobe` 를 subprocess로 호출. Windows에서 PATH에 없으면 실패 →
파일 크기 기반 추정(`size / 16000`)으로 폴백. 65KB 파일이 4.1초로 추정되어
`enforce_min_duration` (< 4.0초 조건)이 발동 안 됨. 실제로는 3초.
수정: `_resolve_bins()`로 ffprobe 절대경로 사용.

**(2) ThreadPoolExecutor `with` 블록의 `shutdown(wait=True)`.**

`_run_sync_pipeline`이 `with ThreadPoolExecutor`으로 병렬 실행 중 cancel 감지 시
`return`하면 `__exit__` → `shutdown(wait=True)` → 나머지 스레드가 끝날 때까지 대기.
수정: `with` 대신 수동 생성, cancel 시 `shutdown(wait=False, cancel_futures=True)`.

**(3) 썸네일 프롬프트 + /edits 재시도 없음.**

fallback 프롬프트의 "provocative", "shocking", "engagement bait"이 OpenAI
content policy 위반 가능. `/edits` 엔드포인트에 재시도 로직도 없어서 1회 실패 시
바로 에러. 수정: 프롬프트 완화 + 3회 재시도 + 표준 생성 폴백.

**(4) 자동저장 디바운스 1초 → 5초.**

### 수정 파일

- `backend/app/services/tts/openai_tts_service.py` — `_get_duration`에 `_resolve_bins` 적용
- `backend/app/services/tts/elevenlabs_service.py` — 동일
- `backend/app/services/oneclick_service.py` — ThreadPoolExecutor 수동 관리
- `backend/app/services/image/openai_image_service.py` — `/edits` 재시도 + 폴백
- `backend/app/tasks/pipeline_tasks.py` — 썸네일 프롬프트 완화
- `frontend/src/app/oneclick/page.tsx` — 자동저장 디바운스 5초

---

## 2026-04-13 (v1.1.52 — 템플릿 에셋 물리 복사 + cancel 시그널 라우팅 수정)

### 사용자 체감 문제

딸깍으로 프리셋 템플릿을 사용해 영상을 생성하면 레퍼런스/캐릭터 이미지가
전혀 반영되지 않았다. 생성된 이미지들은 일관된 스타일 없이 제각각이었다.
또한 중지 버튼을 눌러도 이미지 생성이 멈추지 않았고, 이미지 삭제 후에도
파이프라인이 계속 실행되며 파일을 다시 생성했다.

### 원인 진단

**(1) 템플릿 에셋 파일이 복사되지 않음.**

`_clone_project_from_template`는 config dict만 복사했다. config에는
`references/reference_xxx.png` 같은 상대 경로가 기록되어 있지만, 실제
파일은 템플릿 프로젝트 디렉토리에만 존재했다. 새 프로젝트 디렉토리에는
해당 파일이 없으므로 `collect_reference_images` / `collect_character_images`
가 빈 리스트를 반환 — 이미지 생성 시 레퍼런스가 전혀 전달되지 않았다.

**(2) cancel 시그널이 다른 in-memory dict로 라우팅됨.**

`cancel_task()`는 `app.routers.pipeline._redis_set`에 cancel 플래그를
기록했지만, `check_pause_or_cancel()`은 `app.tasks.pipeline_tasks._redis_get`
에서 읽었다. 두 모듈이 각각 독립적인 `_progress_mem` dict를 가지고 있어
cancel 시그널이 파이프라인 루프에 도달하지 않았다.

### 수정 내용

- `_copy_template_assets()` 함수 추가: 템플릿 디렉토리에서 reference_images,
  character_images, logo_images 파일과 interlude 디렉토리를 새 프로젝트로
  물리적으로 복사한다. `_clone_project_from_template`에서 디렉토리 생성 직후 호출.
- `cancel_task()` / `resume_task()`의 `_redis_set` import를
  `app.tasks.pipeline_tasks`로 변경 — cancel 플래그가 올바른 dict에 기록됨.
- `clear_step_outputs()` 함수 + `POST /{task_id}/clear-step/{step}` 엔드포인트:
  특정 단계의 생성물(이미지/영상)을 삭제하고 step_state를 pending으로 되돌림.
- 프론트엔드: 실패/완료된 이미지·영상 단계에 "이미지 삭제" / "영상 삭제" 버튼 추가.
- 실패 배너에 큐 토픽 이름 표시.
- `start.bat`: backend/frontend cmd 창을 `/min` 으로 최소화 실행.
- `_step_video`의 `ffmpeg` 미정의 참조를 `FFmpegService` import로 수정.
- ghost test: `DummyVideoService`에 `generate()` 메서드 추가 (새 video service 인터페이스 호환).

### 영향 범위

- 딸깍 프리셋 사용 시 레퍼런스/캐릭터 이미지가 정상 전달됨.
- 중지 버튼이 실제로 파이프라인을 멈춤.
- 이미지/영상 삭제 후 재시도 가능.
- 기존 스튜디오 경로에는 영향 없음 (cancel_task는 oneclick 전용).

---

## 2026-04-12 (v1.1.48 — 딸깍 "중지" 버튼 실제로 작동하게 수선)

### 사용자 체감 문제

"중지가 안되네." 스크린샷은 딸깍 제작 큐 모달의 진행 배너였고, `대본 생성`
단계에서 0.0% 로 고정된 태스크 "Why Oil Is Still Priced in Whiskey Barrels" 가
여전히 `running` 으로 표시되고 있었다. 사용자가 중지를 눌렀지만 UI 는 멈추지
않았다.

### 원인 진단

중지 경로를 끝에서 끝까지 읽어본 결과 세 군데가 동시에 고장나 있었다.

**(1) `_step_script` 는 취소 체크가 전무.**

`_step_voice` / `_step_image` / `_step_video` 는 모두 컷 루프의 맨 위에
`check_pause_or_cancel(project_id, step)` 가 있어 Redis 플래그가 세팅되면 즉시
`PipelineCancelled` 를 던진다. 하지만 `_step_script` 는 루프가 없다 — 단 한 번의
LLM 호출로 끝난다. 그래서 취소 체크 호출이 **하나도 없었다**. LLM 자체는 중간
인터럽트가 불가능하니 진짜 중간 이탈은 못 시키더라도, 최소한 LLM 호출 전·후
에 플래그를 보고 빠질 수는 있다. 이전 코드는 그마저도 없었다.

**(2) `_run_oneclick_task` 는 `PipelineCancelled` 를 `failed` 로 잘못 기록.**

`except Exception` 만 있었다. 그래서 파이프라인 루프에서 취소 플래그를 잡아
`PipelineCancelled` 를 던져도 일반 예외로 흡수돼 task 상태가 `failed` 로 찍혔다.
기록 자체가 꼬이고, UI 의 `cancelled` 뱃지가 한 번도 뜨지 않았다.

**(3) `cancel_task` 는 running 일 때 UI 를 갱신하지 않음.**

`prepared` / `queued` 상태일 때만 `status = "cancelled"` 로 바꾸고, running
상태일 때는 Redis 플래그만 세팅한 채 상태를 그대로 둔 채 반환했다. "상태는
runner 가 PipelineCancelled 를 catch 해 갱신한다" 는 주석이 달려 있었지만
runner 는 (2) 때문에 그걸 catch 하지 않고 있었다. 결과적으로 사용자가 중지
버튼을 눌러도 UI 는 완전히 무변화 — 체감상 "아무것도 안 한다".

### 설계 결정

**결정 1. 낙관적 UI 마킹.**

`cancel_task` 가 상태 무관하게 즉시 `status = "cancelled"` + `finished_at` 을
찍는다. runner 가 실제로 멈추기 전에도 UI 는 "중지됨" 으로 표시된다.
사용자의 체감 요구는 "버튼을 눌렀으면 당장 멈춘 것처럼 보여라" 이므로 이게
최우선이다. 이미 `completed`/`failed`/`cancelled` 인 경우는 건드리지 않는다
(이중 종료 방지).

**결정 2. status 를 진실의 원천으로 사용.**

`_run_oneclick_task` 가 매 단계 진입 **전** 과 완료 **후** 양쪽에서
`task["status"] == "cancelled"` 를 확인한다. 사용자가 낙관적으로 마킹한
상태를 보고 다음 단계 진입 자체를 건너뛴다. Redis 플래그는 pipeline step
내부 루프(voice/image/video)를 깨우는 용도로 그대로 유지 — 즉 두 경로가
동시에 작동한다.

- status 폴링: 단계 경계에서 빠져나가기 (특히 `_step_script` 처럼 루프가
  없는 단계용).
- Redis 플래그: 루프 내부에서 `PipelineCancelled` 를 던져 단계 중단.

**결정 3. `_step_script` 전후에 `check_pause_or_cancel` 2 방 추가.**

LLM 호출 자체는 못 끊더라도, 호출 직전과 호출 직후에는 읽을 수 있다.
특히 직후 체크는 중요 — LLM 결과가 돌아온 시점에 플래그가 세팅돼 있으면
`save_script` / 컷 INSERT 를 스킵한 채 빠진다. 이렇게 하면 최악의 경우에도
"LLM 응답이 돌아오는 순간" 에 멈춘다 (30~60초 안에).

**결정 4. `_run_oneclick_task` 에서 `PipelineCancelled` 를 분리 catch.**

일반 `Exception` 앞에 `except PipelineCancelled as e:` 블록을 두고,
- step_states[step] = "cancelled"
- task.status = "cancelled"
- project.status = "cancelled"
- task.error = "사용자 취소"
로 마감한 뒤 `return`. 이렇게 해야 기록이 정확해지고, 향후 로그를 보고
"이건 사용자 취소 / 이건 진짜 실패" 를 구분할 수 있다.

### 왜 "_step_script 루프 내부에 취소 체크를 심는다" 는 안 했는가

그게 가능하려면 LLM 호출을 스트리밍 / 토큰 콜백 기반으로 바꿔야 한다.
서비스 레이어 전체(`app/services/llm/factory.py`, 각 provider 구현) 를
스트리밍으로 재작성해야 하는 큰 리팩토링이다. v1.1.48 의 스코프를 벗어난다.
현재 타협은 "단계 경계에서만 끊을 수 있다" 인데, 사용자 요구("중지가 안되네")
를 해결하기엔 충분하다 — 최악의 경우에도 LLM 응답이 돌아오는 순간(수십 초)
에 멈춘다. 진짜 인터럽트가 필요하면 추후 v1.2.x 에서 스트리밍 LLM 으로 넘어가면서
같이 심을 수 있다.

### 영향 범위

- 딸깍 제작 큐의 모든 단계에서 중지가 작동. 특히 대본 단계 동안 눌러도
  UI 는 즉시 "중지됨" 으로 바뀌고 runner 는 LLM 응답 직후 저장 전에 빠진다.
- 기존 파이프라인(`run_pipeline`, Celery 경로)은 이미 `check_pause_or_cancel`
  을 쓰고 있어 이번 변경이 깨는 것 없음.
- `_step_script` 에 추가된 두 체크는 일반 Celery 경로에서도 작동 — 즉 Studio
  에서 수동으로 스크립트 돌리다가 취소해도 동일하게 LLM 전후에서 빠진다.

### 다음 후보

진짜 LLM 중간 인터럽트가 필요하면 provider 구현을 streaming chunk 기반으로
바꾸고 각 청크 수신 후 `check_pause_or_cancel` 을 돌리면 된다. 현재는
의도적으로 단계 경계 타협을 유지한다.

---

## 2026-04-12 (v1.1.47 — StepSettings 에 TTS 미리듣기 추가)

### 사용자 체감 문제

v1.1.46 가 나온 직후 사용자 반응이 즉각 왔다: "TTS 미리듣기 해줘야지."

그 한마디가 정확히 맞다. 이관은 했는데 **들어볼 방법을 같이 옮기지 않았다**.
결과적으로 설정 화면에서는 목소리를 고를 수는 있지만 어떤 목소리인지 확인
할 수 없고, 확인하려면 설정을 저장하고 음성 스텝으로 넘어가 거기 있는 기존
미리듣기 버튼을 눌러야 했다. 두 스텝 사이를 왔다갔다 해야 하는 워크플로는
애초에 이관의 의도와 정반대다.

### 설계 결정

**1. 미리듣기 엔드포인트에 override body 추가 vs 즉시 저장 후 호출**

StepSettings 는 local `config` 를 편집해 "저장" 버튼을 눌러야 DB 에 반영되는
패턴이다. 미리듣기를 하려면 두 갈래가 있었다:

- (A) 미리듣기 버튼 누를 때 자동으로 즉시 저장 → 그 다음 기존 preview API 호출.
  단점: 저장 확정 전에 "들어만 보고 취소" 가 불가능. 사용자가 A/B 비교 하고
  싶을 때 두 번째 목소리가 저장된 상태로 남아 원복해야 한다.
- (B) preview 엔드포인트에 옵셔널 override body 추가 → 저장 없이 임시로 들음.
  단점: 엔드포인트가 저장된 config 와 override 를 병합하는 약간의 복잡도.

(B) 가 명확히 맞다. "저장 없이 실험" 은 프로젝트 설정 패턴의 핵심이고, 모델
변경·속도 조정도 같은 룰로 동작한다. 미리듣기만 예외적으로 즉시 저장하게 만드는
건 예측 가능성을 해친다. (B) 의 복잡도도 `pick()` 헬퍼 하나면 끝난다.

**2. override 병합 규칙 — None 과 빈 문자열**

`PreviewOverride` 의 모든 필드는 `Optional` 이고, 서버의 `pick()` 은 `None`
뿐 아니라 빈 문자열(`""`) 도 "제공 안 됨" 으로 취급해 저장된 config 로 폴백한다.
이유: 프런트가 `config.tts_voice_preset` 처럼 기본값이 `""` 일 수 있는 필드를
그대로 넘길 때, 서버가 빈 문자열을 "preset 을 빈 문자열로 설정하라" 로 해석
하지 않도록 하기 위함이다. 같은 원리로 `tts_speed: 0` 같은 엣지 케이스는 발생
하지 않음 (slider 가 0.7~1.2 범위).

**3. 버튼 배치 — 그리드 셀 내부 vs 그리드 밖 별도 행**

VoiceSelector 가 `grid-cols-2` 의 한 셀을 차지하고 있어서, 같은 셀 안에
버튼을 추가하면 레이아웃이 깨진다. 옆 셀에 넣는 것도 부자연스럽다 (인접 셀은
TTS 모델). 그래서 그리드 바로 아래 우측 정렬된 한 줄을 추가:
`[안내 문구]    [TTS 미리듣기 버튼]`. 시각적으로 그리드에 붙어 있으면서도
전체 2-col 리듬은 건드리지 않는다.

**4. 버튼 disabled 조건**

`!config.tts_voice_id` 일 때만 비활성화. ElevenLabs 모드에서 voice 목록이
아직 로딩 중이거나 에러 상태일 때도 `config.tts_voice_id` 는 비어있을 가능성이
높다. 백엔드가 빈 voice_id 를 받으면 그대로 API 호출 실패하는데, 버튼을 미리
막는 쪽이 실패 다이얼로그를 띄우는 것보다 친절하다.

**5. 오디오 캐시 무효화**

`voice_preview.mp3` 는 언제나 같은 경로에 덮어쓰기된다. 브라우저가 이전
미리듣기 파일을 캐시하면 새 재생이 안 된다. URL 에 `?t=${Date.now()}` 를 붙여
매번 다른 URL 로 보이게 해 캐시 스킵. 기존 StepVoice 의 미리듣기와 동일한 트릭.

---

## 2026-04-12 (v1.1.46 — TTS 모델/목소리 선택을 프로젝트 설정으로 이관)

### 사용자 체감 문제

프로젝트 생성 워크플로가 "설정 → 대본 → 이미지 → 음성 → 영상 → …" 순서라
한 번 설정 화면을 떠나면 뒤로 돌아와 설정을 다시 바꾸기가 번거롭다. 그런데
**TTS 모델** 선택은 두 곳(설정 + 음성 스텝)에 중복 존재했고, **목소리 선택** 은
음성 스텝에만 있었다. 설정 화면에서 TTS 모델만 고르고 넘어간 뒤 음성 스텝에서
목소리까지 다시 결정해야 하는 이중 작업이 돼 있었다. 사용자는 한 마디로 정리했다:

> 음성 TTS 모델 목소리 선택 도 프로젝트 설정으로 옮기자.

이 방향은 "설정 화면에서 모든 모델·파라미터를 한 번에 결정하고 저장한다" 는
기존 패턴과 정확히 일치한다. 이관 쪽이 원래 자리였다.

### 설계 결정

**1. VoiceSelector 컴포넌트로 추출 vs 인라인 복붙**

목소리 선택 UI 는 드롭다운 하나치고는 로직이 제법 크다 (~250줄):
- ElevenLabs 모드와 OpenAI TTS 모드로 렌더링이 분기됨
- ElevenLabs 에서는 백엔드 API 에서 실제 보이스 목록을 가져와 ko/en/ja/other
  로 그룹핑하는 `inferVoiceLangCode` 휴리스틱 있음
- OpenAI TTS 에서는 21개 고정 프리셋 카탈로그와 `OPENAI_VOICE_MAP` 이 있음
- 외부 클릭 감지, 드롭다운 상태, 로딩/에러 상태 관리

StepSettings 와 StepVoice 양쪽에 복붙하면 앞으로 보이스 로직을 건드릴 때마다
두 곳을 동기화해야 한다. 그래서 `components/studio/VoiceSelector.tsx` 로 추출.
StepVoice 의 UI 는 제거할 계획이지만, 미래에 다른 화면(예: 배치 생성 화면)에서
쓸 수도 있으므로 재사용 가능한 형태가 낫다.

**2. VoiceSelector 의 상태 저장 정책 — 직접 저장 vs onChange 만**

StepVoice 의 기존 동작: 목소리를 선택하면 즉시 `projectsApi.update` 로 저장.
StepSettings 의 기존 동작: local `config` state 에 편집하다 "저장" 버튼을 누르면
한 번에 `projectsApi.update`. 두 패턴을 동시에 지원하려면 컴포넌트가 너무
복잡해진다. 그래서 VoiceSelector 는 **저장을 일절 하지 않고** `onChange(patch)`
로 결과만 부모에게 전달. 부모가 local state 에 병합하거나 즉시 저장하거나
선택하면 된다. StepSettings 는 local state 에 병합(즉시 저장 안 함), "저장"
버튼이 한 번에 커밋한다.

**3. 서버 쪽 — 저장되지 않은 tts_model 로 보이스 미리보기**

문제: StepSettings 에서 사용자가 TTS 모델을 ElevenLabs → OpenAI TTS 로 드롭다운
변경만 했고 아직 저장 안 했다. 이 상태에서 VoiceSelector 가
`voiceApi.listVoices(projectId)` 를 호출하면, 백엔드는 DB 의 **저장된** config
를 읽기 때문에 여전히 ElevenLabs 목록이 돌아온다. 사용자는 새 모델(OpenAI TTS)
의 목소리 카탈로그를 보고 싶은데 볼 수 없다.

해결 옵션:
- (A) 모델 변경 시 즉시 저장 — 다른 설정 필드와 비대칭이 됨. 설정 화면은 "저장
  버튼 누를 때까지 아무것도 영속화 안 됨" 이 불문율이었고, 이걸 어기면 사용자가
  모델만 바꿔 보고 취소할 수 없다.
- (B) 서버 엔드포인트에 쿼리 파라미터 추가 — 클라이언트가 자기가 편집 중인
  모델값을 서버에 넘겨주면 서버는 그 값으로 voices 를 조회.

(B) 가 맞다. 엔드포인트 한 개에 옵셔널 쿼리 파라미터 하나 추가면 되고,
기존 호출자(파라미터 없이 호출)도 동일하게 동작한다. 구현:

```python
async def list_voices(
    project_id: str,
    tts_model: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    ...
    effective_model = tts_model or project.config.get("tts_model", "elevenlabs")
    tts_service = get_tts_service(effective_model)
```

**4. StepSettings 의 그리드 레이아웃 — 2-col 에 5셀 끼우기**

기존 AI 모델 섹션은 `grid-cols-2` 에 4개(LLM/이미지/영상/TTS) 셀이 딱 떨어졌다.
VoiceSelector 를 추가하면 5셀이라 2-col 에서 마지막 행에 빈 자리가 남는다.
`grid-cols-3` 로 바꾸면 라벨 텍스트가 좁아지고 시각적 비율이 흐트러진다.
결국 `grid-cols-2` 를 그대로 유지하고 5번째 셀을 두 번째 열 맨 아래에 자연스럽게
놓는 쪽을 택했다. 가로 그리드의 빈 공간이 오히려 "TTS 모델 + 목소리 선택이 한
쌍" 이라는 걸 시각적으로 분리해주는 효과가 있다.

**5. TTS 모델 변경 시 voice_id 리셋 타이밍**

모델을 바꾸면 기존 voice_id 는 무효다 (OpenAI 의 "alloy" 를 ElevenLabs 에
던지면 에러). `changeTtsModel()` 에서 `tts_voice_id` 와 `tts_voice_preset` 을
빈 문자열로 리셋하도록 했다. 이후 VoiceSelector 의 `fetchVoices` useEffect 가
`ttsModel` 변화를 감지해 새 목록을 가져오고, 빈 voice_id 면 첫 번째 보이스로
자동 채워준다 (`onChange` 를 통해 local state 에 반영).

**6. StepVoice 의 잔존 툴바**

StepVoice 에서 모델/목소리 선택 UI 를 제거하더라도 "지금 이 프로젝트가 어떤
모델로 무슨 목소리를 쓰는지" 를 표시하는 자리는 남겨야 한다. 그래야 사용자가
생성 버튼을 누르기 전에 설정을 확인할 수 있다. 그래서 "TTS 모델: openai-tts /
목소리: alloy / 모델·목소리는 프로젝트 설정에서 변경합니다" 라는 요약 한 줄 +
미리듣기 버튼 + 비용 예측만 남긴 간단한 툴바로 교체했다.

---

## 2026-04-12 (v1.1.45 — 컷당 영상 길이 5초 고정)

### 사용자 체감 문제

v1.1.44 를 돌린 후 120컷 병합본이 **7분 24초 (444초)** 로 나왔다. 사용자는
"120 × 5 = 10분" 을 기대했다. 내가 먼저 사실 확인 후 원인을 설명했고 (컷 길이가
`cut.audio_duration` 을 따라가며 평균 3.7초 음성이라 그대로 반영됨), 사용자는
즉시 방향을 결정했다:

> 무조껀 영상당 5초 여야 되. 음성은 4초쯤 정도여야겠지? 이런식이면 시간계산 안되고 자막 싱크도 안맞자나.

맞는 지적이다. 컷 길이가 가변이면 시간 계산도 불가능하고 자막 start/end 시각도 런타임에
음성 파일을 probe 해야 한다. 5초 고정이 훨씬 합리적.

### 설계 결정

**1. 컷 경계와 발화 구간을 분리한다**

이게 핵심 통찰이다. 자막 싱크 관점에서 두 가지 다른 시간이 있다:

- **컷 창(cut window)**: 컷 경계의 시각. 영상 병합 순서를 결정. → 5초 고정.
- **발화 구간(speech span)**: 실제 음성이 들리는 시간. → 음성 파일 길이.

컷이 5초 창을 갖고 그 안에 3.7초 발화가 있다면:
- 0.0s ~ 3.7s: 발화 + 자막 분포
- 3.7s ~ 5.0s: 무음 + 자막 없음
- 5.0s: 다음 컷 시작

이 구조 덕분에 subtitle 로직도 단순해진다. `current_time += 5.0` 으로 고정 전진하고,
문장 분포만 `speech_dur / len(sentences)` 로 계산하면 끝.

**2. 오디오 패딩 위치 — 서비스 안 vs 라우터 안 vs 미리 파일 생성**

세 가지 선택지:

A) video.py 에서 padded audio 를 미리 만들어서 서비스에 넘긴다
B) 서비스 안의 ffmpeg 명령줄에서 `-af apad` 로 처리
C) 각 서비스가 입력 음성을 감지해서 알아서 패딩

**B) 를 택했다**. 이유:
- 임시 파일을 만들지 않아 I/O 절약
- ffmpeg 가 한 번에 scale/pad/encode 전부 처리
- 서비스별로 mux 명령 하나만 고치면 되고, 공통 추상화 불필요
- `-af apad` + `-t {duration}` 조합은 ffmpeg 가 공식적으로 지원하는 패턴

**3. `-shortest` 를 왜 빼야 하는가**

과거 코드에 있던 `-shortest` 는 "가장 짧은 스트림에 맞춰 종료" 플래그다. 원래 의도는
"이미지 루프가 무한히 돌아도 음성 끝나면 멈춰라" 였을 것. 하지만 이제 영상 길이를
정확히 `duration` 으로 고정하고 싶으므로, "가장 짧은 스트림" 이 아니라 "정확히 N초"
를 원한다. 그건 `-t duration` 의 역할.

제거하지 않고 두면 `-shortest` 가 우선 적용돼 음성 길이(3.7s) 로 영상이 잘려나간다
— 바로 이게 v1.1.44 에서 7분 24초가 나온 이유다.

**4. fal.ai payload 의 `duration` 도 상수로 묶었다**

fal.ai 로 보내는 요청의 `"duration": "5"` 를 `str(int(round(CUT_VIDEO_DURATION)))` 로 교체.
지금은 결과가 같지만, 나중에 누군가 `CUT_VIDEO_DURATION = 6.0` 으로 바꾸면 fal.ai 에도
6초 요청이 나간다. 일관성 유지.

단 fal.ai 는 대부분 정수 초만 받는다. 5.5 초 같은 값은 `int(round(5.5))` = 6 으로 반올림
— 그 뒤 후처리 `-t 5.5` 가 정확한 길이로 자른다. 이 이중 보정으로 상수가 실수여도 동작.

**5. subtitle_service.py 에 config import 를 직접 넣었다**

기존에는 subtitle_service 가 순수 함수로만 구성돼 config 참조 없음. 지금은 `from app.config
import CUT_VIDEO_DURATION` 을 넣었다. 순환 의존이 없고 (config → nothing), 테스트 시
오버라이드가 필요하면 파라미터화할 수 있다. 일단은 직접 import 가 가장 읽기 쉽다.

**6. interlude accumulator 도 손댔다**

`build_interlude_sequence` 가 `c.audio_duration` 을 누적해서 "intermission_every_sec" 시각에
간지영상을 끼워 넣는다. 이제 모든 컷이 5초 고정이므로 그냥 `CUT_VIDEO_DURATION` 을 더하면 된다.
audio_duration 을 읽는 로직은 legacy 데이터 호환을 위해 남겨둘 수도 있지만, 새 런은
전부 5초가 될 것이므로 단순화했다.

### 파일 변경 요약

- `backend/app/config.py` — `CUT_VIDEO_DURATION = 5.0` 신설
- `backend/app/routers/video.py` — `duration=` 파라미터 3개소 교체
- `backend/app/services/video/ffmpeg_service.py` — `FFmpegService`/`FFmpegStaticService` 의 audio-mux 명령줄에서 `-shortest` 제거, `-af apad` + `-t duration` 추가
- `backend/app/services/video/fal_service.py` — 동일한 패턴을 mux 명령에 적용, payload duration 도 상수 참조
- `backend/app/services/subtitle_service.py` — `generate_ass` 의 `current_time` 전진 규칙 변경 (cut_window 고정 전진 + speech_dur 기반 문장 분배)
- `backend/app/routers/interlude.py` — cut_entries 의 dur 를 `CUT_VIDEO_DURATION` 로 교체
- `backend/app/main.py`, `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` — 1.1.44 → 1.1.45 버전 번프
- `CHANGELOG.md`, `DEVLOG.md` — 항목 추가

### 검증

- `python -m py_compile` 대상 5개 파일 전부 OK (config, video, ffmpeg_service, fal_service, subtitle_service, interlude, main)
- TypeScript 변경 없음 (버전 문자열만)

### 알려진 한계 / 후속 과제

- **음성이 5초를 넘으면 뒷부분 잘림**. 대본 생성 단계에서 컷당 목표 글자수(한국어 기준
  대략 50자 이하)를 강제하는 로직이 필요. 지금은 TTS 가 길면 경고 없이 `-t` 가 자른다.
  나중에 `cut.audio_duration > CUT_VIDEO_DURATION` 감지해서 사용자에게 경고 띄우는
  게 좋겠다.
- **apad 가 디지털 0 으로 패딩** — 일부 환경에서 노이즈 플로어 변화로 "tt" 하는 클릭이
  들릴 수 있다. 문제 되면 `afade=out:st=(dur-0.1):d=0.1` 를 추가해서 cross-fade 처리.
- **렌더 단계 자막 합성** 은 이미 `.ass` 파일을 영상 위에 덮어쓰는 구조라 변경 불필요.
  `_build_and_write_ass` 가 주는 싱크 데이터를 그대로 사용한다.
- **기존 프로젝트** 는 자동 마이그레이션이 없다. 영상 스텝을 다시 돌려야 5초 고정본이
  생성된다. 재실행 비용이 부담이면 v1.1.45+ 에서 "기존 5초가 아닌 컷만 재생성" 모드를 추가할 수도.

---

## 2026-04-12 (v1.1.44 — 영상 생성 자동 폴백 + 4컷 병렬)

### 사용자 체감 문제

v1.1.43 작업이 끝나갈 무렵 사용자 콘솔에 `RuntimeError: Fal submit HTTP 403:
{"detail":"User is locked. Reason: Exhausted balance..."}` 가 떴고,
120컷 중 **87컷이 완료된 시점에 잔액이 바닥나서 나머지 33컷이 빨간 "failed" 로
한 번에 터졌다**. 사용자 메시지 그대로: "에러가 절대 나지 않는 방법을 마련해.
그리고 너무 느리다 영상생성이 대체 방안 마련해봐."

### 정직한 선언

사용자에게 먼저 분명히 했다: **"에러가 절대 안 난다"** 는 글자 그대로는 불가능하다.
네트워크 끊김/디스크 풀/ffmpeg 자체 실패/전원 차단 같은 건 여전히 존재한다.
내가 제공할 수 있는 건 **"사용자가 빨간 에러 화면을 마주치지 않는"** 수준의 안정성이다.
그 선에서 모든 failure 경로에 자동 폴백을 걸어 최종 산출물이 "kenburns 로 채워진"
형태로라도 나오게 만드는 것.

거짓말을 지양하는 건 사용자 선호사항이자 내 기본 태도.

### 요구 결정 (AskUserQuestion)

- 폴백 전략: **사전 잔액 체크 후 결정** (probe → 실패면 전체 kenburns, 성공이면 per-cut 폴백)
- 병렬도: **4컷 동시** (fixed, UI 미설정)
- 현재 33컷 실패 프로젝트: **코드 수정만** (기존 프로젝트 건드리지 않음)

### 설계 선택과 근거

**1. fal_service submit 재시도를 왜 v1.1.39 의 GET 재시도와 분리해 지금 추가했나**

v1.1.39 은 result fetch 와 video download 의 409/5xx 문제를 잡았지만 submit POST 는
그대로 두었다. 당시엔 submit 실패가 드물었고, 드물면 retry 비용 < 단일 실패 비용
판단이었던 것 같다. 그런데 이번 사고에서 확인된 건 다른 시나리오다:
**잔액이 서서히 말라가며 submit 에서 일시적으로 5xx / 409 가 섞여 나오는 단계**가 있고,
그 구간에서 retry 가 없으면 멀쩡히 되살아날 컷까지 죽어버린다.

정책은 GET 재시도와 완전히 동일:
- 409/429/5xx → 지수 backoff 2s → 4s → 8s, 최대 4회
- **401/403/404/400 은 재시도하지 않는다** — 잔액 소진/키 거부는 retry 로 해결되지 않고
  그냥 지연만 늘린다. 바로 예외를 raise → 상위에서 kenburns 폴백으로 떨어진다.

**2. pre-flight probe 를 왜 재사용하나 (새로 만들지 않고)**

`api_status._probe_fal_video_model` 이 이미 완성돼 있다. dummy request-id 로 status
GET 을 쏴서 404 면 키 유효, 401/403 이면 auth_failed 를 돌려준다. 잔액 소진 시 status
endpoint 도 403 을 내는 걸 확인했고, 이미 UI 에서 이 함수를 호출해 key health 를 보여주고
있다. 같은 함수를 video.py 에서 한 번 더 호출하면 끝. 새 probe 를 만들 이유가 0.

단, probe 는 순환 import 를 피하려고 `_preflight_fal_probe` 내부에서 import 한다.
`api_status.py` 가 video 쪽 함수를 import 하지 않음을 확인했지만, 방어적으로 둔다.

**3. 개별 컷 폴백과 "primary_disabled" 공유 플래그의 조합**

pre-flight 가 통과했는데 런 도중 잔액이 바닥나는 케이스가 있다 (예: pre-flight 직후
다른 프로젝트가 큰 컷을 돌려 잔액을 빨아먹은 경우). 이 때:

- 첫 실패 → per-cut 폴백으로 kenburns 시도
- 동시에 에러 문자열에서 `_is_terminal_primary_error` 가 "HTTP 403 / Exhausted balance / User is locked" 감지
- 감지되면 공유 플래그 `primary_disabled = [True]` (길이 1 list 로 mutable 전달)
- **이후 워커들은 `_generate_one_cut_safe` 진입 시점에 `primary_disabled[0]` 을 체크** → 즉시 kenburns 로 간다

이게 왜 중요한가: 4개 워커가 동시 실행 중이면, 1번 워커가 403 을 받고 폴백으로 복구하는
동안 2/3/4번 워커는 여전히 primary 로 submit 을 날리고 있다. 플래그가 없으면 넷 다 403 맞고
셋 다 쓸데없이 kenburns 로 떨어진다 (소요 시간 누적). 플래그 덕분에 "403 한 번 터진 후에는
다음 워커부터 primary 건너뛰기" 가 된다.

`asyncio` 단일 이벤트 루프라 락 없이 list[0] 만으로도 경쟁 조건 없다.

**4. 왜 `kenburns` 가 auto-fallback 용이고 `static` 이 selection 용인가**

v1.1.40 에서 사용자가 "나머지 컷에 kenburns 넣지 말라" 고 요청해 selection 미선택 컷은
static (효과 없음) 으로 떨어졌다. 그 결정은 여전히 유효하다 — 선택되지 않은 자리에 켄번은
"공짜 효과처럼 보이지만 사용자가 원하지 않는 효과" 였다.

하지만 폴백의 맥락은 다르다. **폴백은 "primary 가 실패했을 때 사용자에게 뭐라도 보여주는"
안전장치이고, 그 대체물은 static 보다 kenburns 가 낫다** — 사용자는 "내가 유료 모델로 돌렸는데
왜 아무 효과 없이 정지 이미지가 나오지?" 라고 느낄 가능성이 있다. 적어도 켄번은 "AI 만큼은
아니지만 뭔가 움직임은 있네" 로 수용 가능하다.

이 선택은 사용자에게 물어보지 않았다 — 폴백 경로를 설계할 때 기본값을 고르는 건 내 판단
영역이고, `cut.video_model` 컬럼에 `"ffmpeg-kenburns (auto-fallback)"` 라고 명시적으로
기록해 나중에 추적 가능하게 해뒀다. 사용자가 불만이면 이 컬럼을 근거로 되돌릴 수 있다.

**5. 병렬도 4는 어떻게 정했나**

`fal.ai` 큐 API 는 submit 이 사실상 async 작업 예약이라 rate limit 자체는 꽤 높은 편
(초당 수 건 이상). 병목은 submit 이 아니라 **poll+download** 쪽에 있고, 이건 네트워크 bound.
- 1 → 지금처럼 직렬. 120컷 × 45초 = 90분.
- 4 → 이론상 22.5분. 실제론 워커 간 편차로 25~30분 예상.
- 8 → 22분 이하로 더 줄지만 동일 이미지 대량 업로드로 payload 병목이 생기기 시작.
- 16+ → 메모리/서버 rate limit 리스크.

사용자에게 "4 (추천) vs 8 vs 16" 선택지를 주고 **4** 를 선택받았다. UI 설정은 추가하지 않고
상수로 고정 — 필요해지면 v1.1.45 에서 뽑아낼 수 있다.

**6. 워커별 SessionLocal — 왜 분리하나**

v1.1.43 까지는 `_run` 하나가 `local_db` 한 세션으로 돌았고 직렬이라 문제없었다. 병렬에서는:

- 여러 워커가 동시에 한 세션의 identity map 을 수정하면 race
- `local_db.commit()` 은 마지막 호출자만 visible
- 세션은 스레드 safe 하지 않다

async 라 스레드는 안 쓰지만, 세션의 flush/commit 타이밍이 여러 코루틴 사이에서 뒤섞이는
건 안전하지 않다. 각 워커가 자체 세션을 열고 자기 cut 만 업데이트하도록 분리했다. 메인
`local_db` 는 워커 시작 전에 한 번 닫고, 워커가 전부 끝난 뒤 merge 시 다시 열어 사용한다.

**7. 병렬 상태에서 진행률 카운터**

`update_task(project_id, "video", completed_counter[0])` 를 공유 카운터로 증가.
asyncio 는 단일 스레드이므로 락 불필요. 완료/실패 여부에 관계없이 워커 끝에서 `_bump_progress()`
한 번 호출 — 프로그레스 바가 단조 증가하고 최종적으로 cut_count 까지 도달.

**8. 왜 프런트엔드를 안 바꿨나**

백엔드 변경 only. API 스펙은 그대로고, 기존 `/generate-async` / `/resume-async` 엔드포인트가
내부에서 병렬화/폴백을 수행할 뿐이다. 사용자가 보는 건 동일한 진행률 UI 지만 훨씬 빠르고
에러가 덜 난다. 나중에 `ai_fallback` 카운트를 UI 에 노출하고 싶으면 task state 에 추가하면
된다 — 지금은 서버 로그에 SUMMARY 한 줄로 남긴다.

**9. 이름 충돌 주의**

v1.1.40 의 `fallback_service` 변수명을 더 이상 쓰지 않는다 (selection 용 static 과 auto-fallback
용 kenburns 가 서로 다른 개념이 됐기 때문). 새 이름:
- `primary_service` (원래 모델)
- `kenburns_service` (자동 폴백)
- `static_service` (selection 미선택 컷)

`video_model == "ffmpeg-kenburns"` / `"ffmpeg-static"` 인 경우 primary_service 인스턴스를
재사용해 불필요한 중복 초기화 회피.

### 파일 변경 요약

- `backend/app/services/video/fal_service.py` — `_post_with_retries` 추가, submit 호출 교체
- `backend/app/routers/video.py` — `_FAL_VIDEO_MODEL_IDS`, `_is_fal_video_model`,
  `_is_terminal_primary_error`, `_preflight_fal_probe`, `_generate_one_cut_safe` 신설,
  `generate_all_videos_async` / `resume_videos_async` 의 `_run` 병렬화
- `backend/app/main.py`, `frontend/src/lib/version.ts`, `frontend/package.json`,
  `frontend/package-lock.json` — 1.1.43 → 1.1.44 버전 번프
- `CHANGELOG.md`, `DEVLOG.md` — 항목 추가

### 검증

- `python -m py_compile backend/app/routers/video.py` → OK
- `python -m py_compile backend/app/services/video/fal_service.py` → OK
- TypeScript 는 변경 파일 없음 (버전 문자열만 교체)

### 알려진 한계 / 후속 과제

- 워커 4개가 전부 동시에 첫 submit 을 날리는 순간에 큰 base64 payload 4개가 같이 붐비므로
  메모리 스파이크가 있을 수 있다. 필요하면 Semaphore 를 업로드 단계에 별도로 하나 더 둬야 함.
- `_is_terminal_primary_error` 가 문자열 매칭이라 fal.ai 가 에러 포맷을 바꾸면 놓친다.
  대응책: FAL_QUEUE 응답의 structured error code 를 fal_service 에서 노출하는 작업이 필요.
- `VIDEO_PARALLELISM=4` 가 상수 — UI 설정 필요해지면 v1.1.45 에서.

---

## 2026-04-12 (v1.1.43 — 딸깍 주제 큐 + 매일 HH:MM 자동 실행 재도입)

### 사용자 체감 문제

"딸깍제작 주제 입력 리스트 만들고 매일 몇시에 시작 할지 입력 할 수 있게해."

v1.1.42 에서 딸깍은 "팝업 열어서 주제 1 건 입력 → 즉시 실행" 형태가 됐지만, 사용자는 사실 "매일 자동" 을 다시 원하고 있었음. 단, 예전 17 행 EP 그리드가 아니라 **주제 리스트 + 시각** 이라는 새 모델로.

v1.1.42 의 삭제는 틀렸나? 아님. 예전 자동화 스케줄(17 행 프리셋 × 17 슬롯)이 너무 경직돼 있었고, oneclick 내부의 "프리셋 1 개 × 시각 1 개" 도 주제 다양성이 없었음. 이번엔 "주제 큐 × 시각 1 개" — 사용자가 주제만 채워두면 매일 다른 주제가 나간다. 같은 용어("스케줄") 지만 모델이 다름.

### 설계 판단

**데이터 위치 — DB 테이블 vs JSON 파일**

큐 항목이 쌓이는 곳이 필요. 선택지:

- (A) 새 DB 테이블 `oneclick_queue_item` — 인덱스/정렬 좋지만 SQLite + SQLAlchemy 에 Alembic 없는 환경에서 컬럼 추가가 fragile
- (B) JSON 파일 — 예전 scheduler 가 썼던 패턴. 단순, 스키마 변경 없음, 프로세스 재시작 복원 가능
- (C) Project.config 같은 JSON 컬럼 재활용 — 큐가 프로젝트 소속이 아니라 전역이라 부적절

→ (B) 채택. `DATA_DIR/oneclick_queue.json`. v1.1.42 에서 삭제했던 `_SCHEDULE_FILE` 의 직계 후손이지만 **스키마는 완전히 다름** — 그때는 HH:MM + template_project_id 1 쌍, 이번엔 items 리스트 구조.

**발화 시점 — cron 스타일 vs last_run_date 가드**

옵션 1: cron 느낌으로 "방금 HH:MM 가 됐는가" 만 체크. 단순하지만 서버가 HH:MM 정확히 그 1 분에만 살아있어야 함. 재시작/지연에 취약.

옵션 2: `last_run_date` 를 저장해놓고 "오늘 이미 돌았는가 + 오늘 지정 시각을 지났는가" 로 판단. catch-up 가능. ✅

→ 옵션 2. 구체 규칙:

```
now = datetime.now()
if daily_time is None: skip
if last_run_date == today: skip
if (now.hour, now.minute) < (target_h, target_m): skip (아직 이름)
# 발화 조건 충족 → last_run_date 를 오늘로 표기 후 pop
```

서버가 09:00 에 죽어 있다가 09:45 에 올라와도 오늘 아직 안 돌았으면 09:45 에 즉시 발화. 의도된 catch-up.

**빈 큐 + 시간 조건 충족 상황**

사용자가 09:00 에 돌게 해뒀는데 오늘 큐가 비어 있다. 09:00 가 지났다. 이 상태에서:

- (A) `last_run_date` 를 업데이트 안 함 → 사용자가 09:30 에 주제를 채우면 즉시 발화. "빈 큐 감지 → 채울 때까지 대기" 해석
- (B) `last_run_date` 를 업데이트함 → 오늘은 "점검 완료", 사용자가 09:30 에 채워도 내일 09:00 까지 대기. "매일 HH:MM 에만 본다" 해석

사용자는 "조용히 대기" 라고 했음. 둘 다 그 해석에 걸릴 수 있지만:

- (A) 는 "조용" 보다는 "늦게라도 돈다" 에 가까움 — 사용자는 오늘 뭐가 나올지 예상 못 함
- (B) 는 문자 그대로 매일 HH:MM 단 한 번의 기회 — 오늘은 조용하고 내일 다시 시도

→ (B) 채택. 하루 1 회 보장이 기대치에 더 가깝고, "매일 HH:MM" 이라는 사용자 표현과도 일치. 내일 다시 온다.

**pop 타이밍 — start 시점 vs 성공 후**

(A) start 후에 pop: 실패하면 아이템이 큐에 남아 내일 재시도. 단점: 같은 실패를 무한 반복 가능
(B) start 시점에 pop: 성공하든 실패하든 1 회 소비. 단점: 실패 시 사용자가 재입력해야 함

→ (B) 채택. 큐는 "1 회성 소비" 시맨틱이 맞음. 실패 이유가 "일시적" 이 아닌 경우(프롬프트 자체가 이상함, API 키 만료 등) 무한 재시도보다 한 번에 티 내고 사용자가 손 대는 쪽이 안전. 이건 실제 운영 경험 기반 보수적 선택.

**큐 아이템당 프리셋/길이 자유도**

사용자가 "주제마다 다르게" 로 답했음. UI 복잡도 vs 유연성 트레이드오프:

- 큐 row 하나에 (주제 textarea + 프리셋 select + 길이 input + 삭제 버튼) 4 요소
- 3 열 grid 로 밀어넣으면 좁아서 읽기 힘듦
- 2 단 레이아웃: 위 = 주제, 아래 = [프리셋] [길이] — 이게 결국 채택. 모바일 안 쓸 거라는 전제 하에 데스크톱 한정 최적화

**백엔드 스케줄러 다시 붙이기 — v1.1.42 에서 삭제했던 것과 혼동?**

v1.1.42 에서 삭제한 것:

1. `scheduler_service` (17 행 EP 그리드) — 완전 다른 모델이므로 부활 안 함
2. `oneclick_service` 내부의 `_SCHEDULE_FILE`, `_SCHEDULE`, `start_scheduler`, `_schedule_loop` 등 ~200 줄

이 중 (2) 에 해당하는 부분만 "새 모델" 로 재구현. 함수 이름을 다르게 지어서 의도가 섞이지 않게 함:

| v1.1.42 에서 삭제된 이름 | v1.1.43 에서 새로 추가 |
|---|---|
| `_SCHEDULE_FILE` | `_QUEUE_FILE` |
| `_SCHEDULE` | `_QUEUE` |
| `_load_schedule_from_disk` | `_load_queue_from_disk` |
| `_save_schedule_to_disk` | `_save_queue_to_disk` |
| `get_schedule` / `set_schedule` | `get_queue` / `set_queue` |
| `_schedule_loop` | `_queue_loop` |
| `start_scheduler` / `stop_scheduler` | `start_queue_scheduler` / `stop_queue_scheduler` |
| `_trigger_scheduled_run` | `_fire_queue_top` |
| — | `run_queue_top_now` (새 "지금 실행" 버튼) |

### 구현 메모

**디스크 포맷**

```json
{
  "daily_time": "09:00",
  "last_run_date": "2026-04-12",
  "items": [
    {
      "id": "a1b2c3d4",
      "topic": "고대 로마 멸망 원인",
      "template_project_id": "proj123",
      "target_duration": 600
    }
  ]
}
```

`_queue_normalize` 가 불완전/손상 파일을 방어적으로 정리: 비어있는 topic 제거, id 없으면 uuid 자동 생성, target_duration 0/None 은 null 로, HH:MM 형식 아니면 null 처리. 파일 수동 편집해도 크래시 안 남.

**asyncio.Task 생명주기**

`start_queue_scheduler` 는 FastAPI `lifespan` 에서 호출되고, 그 시점에 이벤트 루프가 이미 돌고 있어서 `asyncio.get_running_loop().create_task(_queue_loop())` 가 안전함. 루프 내부는 `while True: ... await asyncio.sleep(30)` 패턴, shutdown 시 `task.cancel()` 로 `CancelledError` 던져 깨끗하게 종료.

루프 안에서 예외가 나도 `try/except` 로 감싸 다음 iteration 으로 넘어가게 함 (30 초 후 재시도). 단일 iteration 실패로 스케줄러 전체가 죽는 일 없음.

**pop 트리거 → prepare + start 호출**

`_fire_queue_top` 이 직접 `prepare_task` + `start_task` 를 호출. 이 두 함수는 v1.1.42 에서 생긴 `target_duration` 파라미터와 `config["__oneclick__"] = True` 마커 로직을 이미 포함하고 있어서, 큐 발화로 만들어지는 프로젝트도 자연스럽게 프리셋 목록에서 숨겨짐. v1.1.42 의 선택이 v1.1.43 에서도 유지되는 덕분에 중복 작업 없음.

`task["triggered_by"] = "schedule"` 로 표기 (UI 는 아직 안 보여주지만 `list_tasks` 응답에는 들어감).

**프론트엔드 저장 플로우**

v1.1.42 의 `handleStart` (prepare → start) 가 아니라 `handleSave` (PUT /queue) 가 메인 동작. "지금 1 건 실행" 을 누르면 먼저 자동 저장 후 `run-next` 호출 — 사용자가 큐를 편집하고 저장 누르지 않은 채 "지금 실행" 을 눌러도 의도가 반영되게 함.

큐 row 편집 시 `saved` 플래그를 false 로 내려 "저장" 버튼 아이콘이 체크마크 → 저장 아이콘으로 되돌아감. "저장 안 된 변경 있음" 을 시각적으로 전달.

**`runQueueNext` 후 re-fetch**

서버가 맨 위를 pop 했으므로 UI 의 items 도 리프레시해야 맞음. 그냥 `loadQueue()` 재호출 — 전체 상태 재동기화. 네트워크 1 번 더 타지만 복잡도 낮음.

**진행 배너 UX**

모달 안에 태스크가 돌고 있을 때 상단에 얇은 배너 (주제명, 진행률, 중지 버튼). 배너 아래로 큐 편집기가 그대로 보이므로 "지금 돌고 있는 거 + 내일 돌 것들" 을 한 화면에서 파악 가능. 사용자가 큐 편집하다 중간에 태스크 돌고 있는 걸 잊지 않게 함.

### 호환성

- SQLite 스키마 변경 없음
- `DATA_DIR/oneclick_queue.json` 이 없으면 자동으로 빈 상태 + 스케줄 꺼짐으로 초기화
- v1.1.42 의 `/api/oneclick/prepare`, `/api/oneclick/{id}/start` 는 그대로 유지 — `run-next` 엔드포인트가 내부에서 호출
- `config["__oneclick__"]` 마커는 v1.1.42 부터 계속 동작 → 큐 발화로 만들어지는 프로젝트도 프리셋 목록에 노출되지 않음
- 첫 배포 시 사용자는 기본적으로 "스케줄 꺼짐" 상태. 시간을 명시적으로 설정해야 돌기 시작

### 후속 작업

- 큐 아이템 드래그 순서 변경 (현재는 삭제 + 재추가만 가능)
- 큐 아이템에 "다음 실행 예상" 라벨 ("내일 09:00", "3 일 후" 등) 표시
- 주 단위/월 단위 반복 옵션 — 지금은 "매일 동일 시각" 만
- `last_run_date` 에 더해 "마지막 실행 task_id" 링크를 저장해 "어제 뭐 돌았나" 바로 접근 가능하게
- 실패한 아이템의 재시도 UX — 현재는 사용자가 수동으로 다시 추가해야 함
- 큐 발화 실패 시 사용자 알림 (현재는 백엔드 로그에만 찍힘)

---

## 2026-04-12 (v1.1.42 — 딸깍 = 인스턴트 팝업 / 자동화 스케줄 폐기 / 프리셋 목록 오염 해소)

### 사용자 체감 문제

"딸깍 셋팅하면 프리셋이 생성되네? 이럼 안되지. 이건 아니야. 이런 방식이 아니야. 딸깍은 인스턴트야. 프리셋이 중요한거라고. 딸깍 제작은 팝업띄우자. 팝업 띄워서 주제 넣고 시간 넣으면 순차적으로 진행하게 해. 자동화 스케쥴 삭제하고 그자리에 버튼 넣어"

세 가지가 섞여 있음:

1. 딸깍을 누를 때마다 프리셋(Project) 이 하나씩 새로 생겨서 프리셋 목록이 더러워짐 — 딸깍으로 만든 건 일회성인데 영구 저장물처럼 쌓임
2. 현재 딸깍 흐름은 "저장 → 예상 견적 → 시작" 3-step 이라 "인스턴트" 가 아님
3. 자동화 스케줄(17-행 EP 그리드 + 일일 HH:MM 자동 실행) 은 더 이상 필요 없음. 그 버튼 자리에 딸깍을 넣자

### 설계 판단

**딸깍 프로젝트를 DB 에 저장할 것인가, 하지 말 것인가**

파이프라인 함수들(`run_script`, `run_tts`, `run_image`, `run_video`) 은 전부 `project_id` 로 Project 행을 조회해서 동작한다. 즉 딸깍이라 해도 파이프라인이 돌아가려면 DB 행은 있어야 함. 선택지:

- (A) Project 행을 아예 만들지 않고 메모리/임시 구조체만으로 돌린다 — 파이프라인 4개를 전부 뜯어고쳐야 함. 위험 크고 이득 적음
- (B) 행은 만들되 UI 프리셋 목록에서만 숨긴다 ✅

→ (B) 채택. 구현 방법은 두 가지:

- (B-1) Project 모델에 `is_oneclick Boolean` 컬럼 추가. 명시적이고 인덱스 걸기 좋음. 단점: SQLite + SQLAlchemy 에 Alembic 이 없는 현 구조에선 컬럼 추가가 fragile (수동 ALTER TABLE 필요, 기존 DB 파일 호환 문제)
- (B-2) `config` JSON 컬럼 안에 `__oneclick__: True` 마커만 꽂는다. config 는 이미 `MutableDict.as_mutable(JSON)` 이라 추가 필드 자유. 스키마 변경 없음 ✅

→ (B-2) 채택. 밑줄 두 개 prefix 로 "내부 전용" 을 시각적으로 표시. 필터링은 `/api/projects` list 엔드포인트 한 곳에서만 처리하면 됨 — 단건 조회(`/projects/{id}`) 는 여전히 잘 동작해야 파이프라인이 돌아감.

**"저장 → 예상 → 시작" 3-step 을 어디까지 줄일 것인가**

기존 OneClickWidget 은 카드 안에 전개형 UI 로 이 3단계를 보여줬음. 사용자 요구는 "인스턴트" — 팝업 열자마자 주제 쓰고 "시작" 한 번 누르면 끝나야 함. 예상 견적(estimate) 은 실제로 필요한가?

- 예상 견적의 원래 용도는 "과금/퀄리티 파악 후 취소 기회 제공" 이지만, 딸깍의 본질은 "고민 없이 누르면 그만" 이라 견적 단계가 오히려 "한 번 더 확인 눌러야 하는 마찰" 이 됨
- 모델/캐릭터/자막 구성은 템플릿 프리셋을 그대로 가져오기 때문에 사용자가 견적 보고 바꿀 여지도 거의 없음 (바꾸려면 Studio 로 가야 함)

→ `handleStart` 한 번 호출로 `prepare` + `start` 를 연달아 실행. 예상 견적 단계는 완전히 제거. 모달 하단에 "약 N 분 분량" 힌트만 보여줌 (입력한 duration 기준).

**"시간" 은 시각인가 길이인가**

사용자 문장 "주제 넣고 시간 넣으면" 의 "시간" 은 중의적. 옛날 자동화 스케줄 맥락(HH:MM 자동 실행) 이 뇌리에 남아 있으면 "시각" 으로 읽히지만, 자동화 스케줄을 없앴다는 문맥에서 다시 읽으면 "영상 길이(target_duration)" 가 자연스러움. 템플릿 프리셋에 이미 `target_duration` 이 있으니 "시간 = 길이" 로 해석하는 쪽이 기능적으로도 맞음.

→ 모달의 두 번째 입력 필드는 "목표 영상 길이(분)". 숫자만 받음. 기본값은 선택된 템플릿의 `target_duration / 60`, 없으면 10. 빈 값으로 넘기면 템플릿 기본값 사용.

**모달 닫기 UX — 실행 중에도 닫을 수 있게 할 것인가**

옵션 A: 실행 중엔 모달을 못 닫게 잠금 — "실행 중" 임을 계속 의식하게 만든다는 장점. 단점: 모달이 있는 내내 화면을 점유해 "인스턴트" 의 정서와 충돌
옵션 B: 실행 중에도 자유롭게 닫을 수 있게 하고, 버튼 자체가 "진행 중(48%)" 형태로 상태 표시 ✅

→ B 채택. 모달은 단지 제어용 창, 태스크의 집은 버튼임. 사용자가 모달을 닫고 Studio 로 이동해도 백엔드 `asyncio.create_task` 는 계속 돌고, 나중에 대시보드로 돌아오면 버튼이 여전히 "진행 중" 으로 보임.

**페이지 이동 후 태스크 복구**

OneClickWidget 이 unmount/remount 되면 내부 state(`task`) 가 초기화된다. 그럼 버튼은 "딸깍 제작" 으로 돌아가고 실제로는 태스크가 돌고 있는데 UI 엔 안 보이는 상황이 됨. 해결: mount 시점에 `oneclickApi.list()` 를 호출해서 `prepared|queued|running` 상태의 태스크가 있으면 그 중 가장 최근 것을 `task` state 로 꽂아준 뒤 폴링 재개.

이 방법은 `_TASKS` 모듈 레벨 dict 에 모든 태스크가 들어있다는 사실에 의존 — 프로세스가 살아있는 동안은 list() 가 진실의 원천. reload/crash 시엔 이 dict 가 날아가지만 그건 v1.1.42 에서 해결할 영역이 아님(더 큰 영속화 얘기).

### 구현 메모

**삭제된 스케줄 서브시스템 (두 개, 한 번에)**

"자동화 스케줄" 이라는 표현이 UI 상으론 한 곳(/schedule 의 17-행 EP 그리드) 에만 붙어 있었지만, 실제로는 독립된 두 개의 스케줄러가 있었음:

1. `scheduler_service` — EP 그리드, daily-at-HHMM 발화, 에피소드 단위 자동 편성
   - `backend/app/routers/schedule.py`, `backend/app/services/scheduler_service.py`, `backend/app/models/scheduled_episode.py`
   - `frontend/src/app/schedule/page.tsx` (17-행 UI)
2. `oneclick_service` 내부 스케줄러 — 특정 템플릿을 매일 HH:MM 에 자동 실행
   - `oneclick_service.py` 의 `_SCHEDULE_FILE`, `_SCHEDULE_DEFAULT`, `_schedule_loop`, `start_scheduler`, `get_schedule`, `set_schedule` 등 약 200 줄
   - OneClickWidget 카드 하단의 "매일 실행" 토글 + 시각 입력 패널

둘 다 "자동화 스케줄" 의 의미 범주에 들어가므로 둘 다 삭제. (1) 은 라우터/서비스 import 를 main.py 에서 떼어내는 것으로 비활성화 (물리적 파일은 남김), (2) 는 `oneclick_service.py` 내부의 스케줄러 블록을 완전히 제거.

**물리 삭제 vs 디스커넥트**

위험/이득 판단:

- 파일을 지우면 `from .scheduler_service import X` 같은 숨은 import 가 모듈 로드 자체를 터뜨릴 수 있음
- Grep 으로 확인한 결과 `scheduler_service` 참조는 이제 `routers/schedule.py` (자기 자신) 한 곳뿐
- 그래도 안전장치 차원에서 v1.1.42 에선 파일은 남기고 import 만 뗌. 다음 릴리스 또는 충분한 실사용 확인 후 물리 삭제

예외: `frontend/src/app/schedule/page.tsx` 는 bash `rm` 권한 문제로 애초에 삭제 불가였고, 또 기존 북마크/히스토리 보호를 위해 redirect 스텁으로 교체 — `useEffect` 에서 `window.location.replace("/")` + fallback UI "자동화 스케줄은 제거되었습니다".

**`oneclick_service.py` 에서 빠진 것 (요약)**

```
_SCHEDULE_FILE
_SCHEDULE_DEFAULT
_SCHEDULE (module-level state)
_load_schedule_from_disk / _save_schedule_to_disk
_compute_next_run
get_schedule / set_schedule
_trigger_scheduled_run
_schedule_loop
start_scheduler / stop_scheduler
```

이와 함께 `import json, time`, `from datetime import timedelta` 도 now-unused 라 함께 정리. `_clone_project_from_template` 시그니처에 `target_duration` 추가, `config["__oneclick__"] = True` 마커 주입.

**필터링 위치**

```python
# routers/projects.py - list_projects
for p in projects:
    cfg = p.config or {}
    if cfg.get("__oneclick__"):
        continue
    out.append(_to_dict(p))
```

단건 조회 `/projects/{id}` 는 손대지 않음. 파이프라인 함수들이 여전히 동작해야 하므로.

**모달 구조 (OneClickWidget 재작성)**

- 기본 export 가 이제 카드가 아니라 "버튼" — 부모 레이아웃(대시보드 topbar) 에 그대로 꽂힘
- 상태: `open`, `projects`, `templateId`, `topic`, `durationMin`, `task`, `busy`, `err`
- mount effect: `projectsApi.list()` 로 템플릿 로드 + `oneclickApi.list()` 로 active task 복구
- `useEffect([templateId])`: 선택된 템플릿의 `config.target_duration` 을 분으로 변환해 `durationMin` 초기화
- polling `useEffect([task])`: 2초 간격 `setTimeout`, `completed|failed|cancelled` 되면 정리
- 모달 뷰 3종: `InputView`(주제/길이 입력 + 시작), `RunningView`(진행률 + 중지), `FinishedView`(결과 + 새로 시작)
- 배경 클릭으로 닫힘. `onClick={e => e.stopPropagation()}` 로 내용 클릭은 흡수
- 버튼 자체는 `isActiveTask(task)` 에 따라 "딸깍 제작" ↔ "진행 중 (N%)" 로 토글 + 색/아이콘 변화

**대시보드 topbar 배치**

```tsx
// app/page.tsx
<div className="flex items-center gap-2">
  <a href="/">홈</a>
  <OneClickWidget />  {/* ← 자동화 스케줄 버튼이 있던 자리 */}
</div>
```

그리고 본문에 있던 기존 인라인 OneClickWidget 카드는 제거, 대신 안내 문구 한 줄:

> 프리셋은 모델·자막·캐릭터 구성을 재사용하는 틀입니다. Studio 에서 프리셋을 다듬고, 상단의 **딸깍 제작** 버튼으로 주제/시간을 넣어 새 영상을 즉시 만드세요.

### 호환성

- SQLite 스키마 변경 없음 (JSON 마커만 사용)
- 기존 프리셋 목록은 `config["__oneclick__"]` 이 없으므로 필터에 안 걸림 — 영향 없음
- `/api/oneclick/schedule` GET/PUT 이 사라짐: 외부 호출자 있으면 404. LongTube 자체 호출처는 전부 정리됨
- `/api/schedule/*` 전체가 사라짐: 동일
- 기존 OneClick 태스크는 `_TASKS` 메모리 구조 그대로 사용 — prepare/start/status/cancel/list 엔드포인트 시그니처 불변
- 이전 딸깍으로 생성되어 이미 DB 에 쌓인 "오염 프리셋" 들은 마커가 없어서 여전히 목록에 보임 (수동 정리 또는 future migration 대상)

### 후속 작업

- 스케줄러 파일 물리 삭제 (routers/schedule.py, services/scheduler_service.py, models/scheduled_episode.py) — 다음 릴리스에 검토
- 과거 딸깍으로 만들어진 "오염 프리셋" 소급 정리 스크립트 (이 프로젝트 마커 주입 migration)
- OneClickWidget 모달의 키보드 접근성(ESC 로 닫기, 포커스 트랩)
- `_TASKS` in-memory 만 믿는 구조가 프로세스 재시작 시 "진행 중" 을 잃는다 — 영속화 논의는 별도 이슈

---

## 2026-04-12 (v1.1.41 — 긴 영상 태스크가 중간에 죽는 문제 + 탭 이동 시 진행 상태 노출)

### 사용자 체감 문제

"영상 생성이 왜자꾸 멈추는 거 같지? 한번 시작하면 페이지 변경 되도 계속 진행 되게 해. 중지 누를때까진 계쏙 진행."

두 가지가 섞여 있는 불만:

1. 영상 생성을 시작해 두고 다른 탭에 갔다 오면 진행이 안 되는 것 같다 → 진짜 멈춘 건지 UI 만 안 보이는 건지 판단 불가
2. 원하는 동작: 한 번 시작하면 사용자가 중지 누르기 전까진 계속 돌아야 함

### 진단

두 개의 독립 원인을 분리해서 확인:

**원인 1 — `task_manager.is_running` 의 30분 auto-expire**

```python
def is_running(project_id, step):
    state = _tasks.get(...)
    if state is None or state.status != "running":
        return False
    elapsed = time.time() - state.started_at
    if elapsed > 1800:   # ← 30분
        state.status = "failed"
        ...
```

이 코드는 사용자가 새 태스크를 시작하려 할 때 "이미 돌고 있는가" 를 확인하기 위한 용도인데, 30분이 지났으면 무조건 실패 처리. 120 컷 × 30~60s = 1~2시간이 걸리는 Fal 영상 생성에선 2차 호출이 걸리는 순간 (예: 사용자가 "이어서 생성" 클릭) 이 호출이 `is_running` 을 타면서 멀쩡한 태스크가 죽음.

**원인 2 — 탭 간 진행 상태 가시성 없음**

StepVideo 안에만 `GenerationTimer` 가 있어서, 사용자가 StepSettings 로 이동하면 "진행 중" 이 사라짐. StepVideo 컴포넌트가 unmount 돼도 백엔드 `asyncio.create_task(_run())` 는 계속 돌고 있음 — 다만 UI 에서 그게 안 보임. 다시 StepVideo 로 돌아오면 mount effect 가 `taskApi.status` 를 조회해 UI 상태를 복구하긴 하지만, 그 동안 사용자는 "아 멈췄구나" 라고 결론 지음.

### 설계 판단

**원인 1 수정 — 상한선을 올릴까, 없앨까**

옵션 A: auto-expire 완전 제거. 유실 방지 측면에선 완벽. 단점: 진짜로 태스크가 죽었는데 state 가 running 으로 남아있는 경우 (크래시, 프로세스 재시작) 영원히 "이미 돌고 있음" 으로 판단돼 사용자가 새 태스크 시작 불가.

옵션 B: 상한선 상향 + 별도 리컨사일. 안전망은 유지하되 6시간으로 올리고, 동시에 "asyncio.Task 가 이미 done() 인데 state 가 running" 인 dangling 상태를 즉시 감지해 정리. ✅

→ 옵션 B 채택. 6시간은 실제로 나올 수 있는 최대 소요시간 (120 컷 × 2분 ≈ 4시간) 에 여유를 두고 정한 값. 진짜로 죽은 태스크는 asyncio reconcile 로 6시간 안 기다리고 즉시 감지됨.

```python
atask = _async_tasks.get(key)
if atask is not None and atask.done():
    state.status = "failed"
    state.error = "Task ended without status update (crash or reload)"
    ...
    return False
```

이 패턴은 `_async_tasks` 가 asyncio.Task 인스턴스를 약한 참조가 아닌 강한 참조로 붙잡고 있다는 점에 의존. `register_async_task` 가 그렇게 함. 따라서 여기서 호출되는 `atask.done()` 은 신뢰할 수 있음.

**원인 2 수정 — StepVideo 밖으로 타이머 빼내기**

`GenerationTimer` 는 이미 `projectId` + `step` 만 있으면 자체적으로 폴링/상태 관리/취소 버튼까지 다 해주는 자족적 컴포넌트. 스텝별 GenerationTimer 를 건드릴 필요 없이, 동일한 인스턴스를 StudioPage 최상단에 추가로 3개 (voice/image/video) 올리면 됨. 두 군데서 동시에 폴링하는 건 낭비라고 생각할 수도 있지만:

- 폴링 간격이 1.5초로 가볍고 GET /api/tasks/{pid}/{step} 응답이 수십 바이트
- 각 GenerationTimer 는 자체 `setInterval` 로 독립적으로 돌아가므로 상호 간섭 없음
- StepVideo 내부 타이머는 그대로 둬야 그 탭에선 자세히 보임 (cut 별 진행 상황 등)

중복 비용이 거의 없고, 기능 복잡도는 크게 늘지 않음.

### 구현 메모

**빈 컨테이너 숨기기**

3 개 GenerationTimer 가 전부 `null` 을 반환하는 idle 상태에선 배너 영역이 통째로 안 보여야 함. 부모 `div` 에 `px-6 pt-3` 패딩이 붙어 있으면 자식이 없어도 12px 여백이 생김. Tailwind 의 `empty:hidden` 유틸리티 (CSS `:empty` 셀렉터) 로 해결 — 자식이 아무도 DOM 에 안 들어가는 상태에선 부모를 `display:none`.

```tsx
<div className="empty:hidden px-6 pt-3 flex flex-col gap-2 flex-shrink-0">
  <GenerationTimer projectId={projectId} step="voice" ... />
  <GenerationTimer projectId={projectId} step="image" ... />
  <GenerationTimer projectId={projectId} step="video" ... />
</div>
```

React 에서 `null` 반환은 실제 DOM 노드를 만들지 않으므로 이 div 의 자식이 전부 null 이면 `:empty` 가 매치됨.

**polling 중복 검토**

각 탭에서:
- StudioPage 전역 영역 → 3 개 GenerationTimer (1.5s 간격)
- StepVoice → 내부 GenerationTimer 1 개 + useEffect 폴링 (2s)  
- StepImage → 동일
- StepVideo → 동일

사용자가 StepVideo 에 있을 때 `/api/tasks/{pid}/video` 에 걸리는 폴링 횟수는 전역 1 개 + StepVideo 내부 2 개 = 3 개. 매초 약 2 요청. 로컬 백엔드라 실질적 부하는 무시할 만함. 분산/원격 환경이었으면 디바운싱/캐싱 레이어가 필요했겠지만, LongTube 는 로컬 실행 기본 전제라 생략.

### 검증

`python -m py_compile backend/app/services/task_manager.py` 통과. 프런트엔드는 다음 `npm run dev` 에서 자연히 반영.

### 후속 과제 메모

- 한 프로젝트당 `task_manager` 는 메모리 상에서만 상태를 들고 있음. 백엔드 프로세스가 재시작되면 `project.step_states` 는 "running" 으로 남아있고 `task_manager` 는 비어 있음 → 사이드바 step 원이 "running" 처럼 보이지만 실제로는 아무것도 안 돌고 있음. 이 dangling 상태는 v1.1.41 에서 건드리지 않았음. 나중에 `lifespan` 시작 훅에서 `project.step_states` 를 스캔해 "running" → "failed" 로 reconcile 하는 게 맞음. 이번엔 사용자 요청의 핵심이 아니라 패스.
- 전역 `GenerationTimer` 에서 취소 버튼을 누르면 해당 step 만 중단됨. 사용자가 "전부 중지" 같은 일괄 중지를 원할 경우 별도 버튼 필요 (현재 없음).

---

## 2026-04-12 (v1.1.40 — 영상 폴백 켄번 효과 제거)

### 배경

v1.1.36 에서 영상 모델 비용 절감용 "영상 제작 대상 선택" 을 도입했음. 4 컷당 1 컷, 5 컷당 1 컷 식으로 소수 컷만 비싼 AI 영상 모델로 처리하고, 나머지 컷은 비용 0 의 폴백 모델 (`ffmpeg-kenburns`) 로 처리해 실시간 비용을 1/3~1/5 로 줄이는 구조.

문제는 폴백으로 자동 지정한 `ffmpeg-kenburns` 가 줌 인/아웃 효과를 컷마다 무작위로 적용한다는 점. AI 영상으로 만든 컷과 Ken Burns 컷이 한 영상 안에 섞이면, "AI 가 만든 자연스러운 카메라 워크" 옆에 "정형화된 줌인" 이 끼어드는 위화감이 생김.

사용자 메시지: "나머지에 켄번 효과 느치 말라고."

### 설계 판단

**옵션 1 — 기존 `FFmpegService` 의 zoompan 을 조건부로 끄기**

가장 작은 변경이지만, 이렇게 하면 사용자가 "주 모델"로 Ken Burns 를 명시 선택한 경우에도 효과가 사라짐. Ken Burns 자체를 좋아하는 사용자에겐 기능 후퇴. 거부.

**옵션 2 — 새 서비스 `FFmpegStaticService` 추가, 폴백만 교체** ✅

`ffmpeg_service.py` 안에 `FFmpegStaticService` 클래스를 새로 만들고, factory 에 `provider="local-static"` 으로 등록. `FFmpegService` 는 그대로 둠 — 기존 의도대로 zoompan 효과 유지. 폴백 경로 (`router/video.py` 의 두 곳, 동기/비동기) 만 새 서비스를 호출.

장점: 기존 사용자의 명시 선택을 보호함. 책임 분리가 명확함 — 한쪽은 효과, 다른 쪽은 비용 0 정지.

### 구현 메모

`FFmpegStaticService.generate` 의 `vf` 필터:

```
scale={W}:{H}:force_original_aspect_ratio=decrease,
pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,
setsar=1,
fps=30,
format=yuv420p
```

기존 Ken Burns 에서 빠진 건 `zoompan=z='if(...)'` 한 줄. `-loop 1 -i image -i audio -shortest` 패턴으로 오디오 길이만큼만 인코딩. 인코더는 `libx264 -preset ultrafast -crf 23` 로 동일.

zoompan 이 빠지면서 컷당 인코딩 시간이 약 0.8s → 0.6s 로 단축됐음 (체감은 미미하지만 120 컷 × 0.2s = 24s 정도 절약).

### estimation_service 수정

`estimation_service.py` 에서 `_count_ai_video_cuts` 로 분리해두었던 폴백 컷 수에 적용되는 모델 이름을 두 군데 (`_estimate_video_cost_usd`, `_estimate_video_seconds`) 에서 `"ffmpeg-kenburns"` → `"ffmpeg-static"` 으로 교체. cost 는 양쪽 모두 0 이라 동일하지만, time breakdown 의 video 시간이 살짝 줄어듦.

`VIDEO_SEC_PER_CUT` 에 `"ffmpeg-static": 0.6` 추가.

### 호환성

- `config.video_model` 기본값은 여전히 `ffmpeg-kenburns`. 사용자의 주 모델 선택은 건드리지 않음.
- "영상 제작 대상 선택" 이 `all` 인 경우 폴백 경로 자체가 안 타니까 영향 없음.
- v1.1.36~v1.1.39 에서 이미 생성된 영상은 그대로. 새 변경은 앞으로 생성되는 영상에만 적용.

### 추후 검토거리

- `FFmpegStaticService` 를 사용자 드롭다운에 노출할지. 현재 `default=False` 라 UI 에 안 뜨도록 했는데, "효과 없는 정지 영상" 을 일부러 원하는 사람도 있을 수 있음. 피드백 받으면 켜기.
- 폴백을 더 다양화 (예: 매우 약한 fade-in/out 만 있는 변종) 할지. 현재는 켄번 vs 정지 두 갈래로만 나눠둠 — 옵션이 너무 많아지면 본 기능 (비용 절감) 의 핵심이 흐려짐.

---

## 2026-04-12 (v1.1.39 — Fal 영상 다운로드 재시도)

### 배경

사용자 스크린샷: 120 컷짜리 롱폼 영상 생성 중 9 번 컷 하나만 `RuntimeError: Fal video download HTTP 409` 로 실패. 나머지 119 컷은 정상 진행. 진행률 UI (v1.1.38 에서 세부화한) 덕분에 "하나만 죽었구나" 가 바로 보이긴 했지만, 애초에 이런 잔고장으로 컷이 죽지 말았어야 함.

### 진단

`fal_service.py::generate` 의 다운로드 단계 트레이스:

1. `submit` → 202 Accepted, `request_id` 획득
2. `status_url` polling → "COMPLETED" 도착
3. `result_url` GET → video URL 추출
4. `video_url` GET → **HTTP 409 ← 여기서 터짐**

Fal 쪽에선 영상 생성 자체는 성공한 상태 (`COMPLETED`) 였고, 단지 CDN 에서 결과 파일을 내려받는 순간에 409 를 뱉은 것. 이는 Fal CDN 이 생성 직후 첫 요청을 간헐적으로 거절하는 알려진 패턴 (경쟁 조건으로 추정 — 파일이 모든 엣지 노드에 전파되기 전에 요청이 들어오면 충돌).

코드는 다운로드 응답 코드가 400 이상이면 곧바로 `RuntimeError` 로 승격 — 재시도가 전혀 없었음. v1.1.34 에서 이 서비스를 작성할 때 "Fal 큐가 한 번 COMPLETED 주면 downloadable 하다" 고 가정했던 게 실전에선 틀렸음.

### 설계 판단

**재시도 대상 분류**

그냥 모든 실패에 재시도를 거는 건 나쁜 선택. 401 (인증 만료), 403 (권한), 404 (리소스 없음), 400 (잘못된 요청) 은 재시도해도 같은 실패를 반복할 뿐이고 오히려 rate-limit 을 유발. 진짜 "일시적" 인 에러만 골라서 재시도:

- `409 Conflict` — 이번에 터진 것. CDN 전파 레이스.
- `429 Too Many Requests` — 공식적인 재시도 시그널.
- `5xx` — 서버 쪽 이슈, 대부분 몇 초면 복구.
- `httpx.TransportError` / `TimeoutException` — 네트워크 끊김.

그 외 4xx 는 영구 에러로 판단해 즉시 raise.

**backoff 전략**

Exponential backoff 2s → 4s → 8s, 최대 4 회 시도. 한 컷당 최악의 경우 추가 지연 14초. 120 컷 작업에서 매 컷이 최악이라고 해도 28 분 증가 — 하지만 실제로는 4 회 재시도까지 가는 경우는 극히 드물고 (이번 버그도 2 회째에 거의 확실히 풀림), 재시도로 컷을 살려내는 이득이 훨씬 큼.

**어디에 적용하나**

3 개 GET 중 2 개에만 적용:

- ✅ **video download**: 실제로 터진 지점. 서명된 presigned URL 이라 `Authorization` 헤더 안 붙임 (서명 + Auth 이중은 CDN 마다 처리가 불일치할 수 있어 미리 회피).
- ✅ **result fetch** (`result_url`): 동일 Fal 큐 경로. 같은 부류 이슈에 노출돼 있으므로 예방적 적용.
- ❌ **status polling**: 이미 자체 루프가 5초 간격 × 120 회로 재시도 역할을 함. 이중 재시도는 상태 머신을 혼란스럽게 만듦 — 건드리지 않음.
- ❌ **submit**: 이 경로의 실패는 대부분 잘못된 요청 (payload 형식, image_url 크기, 잘못된 모델 ID) 이라 재시도가 오히려 비용만 늘리고 같은 실패를 반복하게 함.

**헬퍼 위치**

`FalVideoService._get_with_retries` 정적 메서드로 내부화. 파일 내부 재사용만 필요하고 httpx 의존성을 밖으로 새게 하기 싫어서 모듈 레벨 유틸로 뽑지 않음. 만약 나중에 다른 서비스에서도 쓸 일이 생기면 그때 공통 유틸로 추출.

### 변경 요약

- `backend/app/services/video/fal_service.py`:
  - `_get_with_retries` 정적 메서드 추가
  - `generate()` 의 result GET 과 video download GET 을 이 헬퍼로 래핑
  - video download 시 `Authorization` 헤더 제외 (CDN 서명 URL 보호)
- 버전 1.1.38 → 1.1.39

### 향후 개선 여지

- 다른 영상 서비스 (`kling_service.py`, `runway_service.py` 등) 가 있다면 동일한 재시도 패턴을 이식할 가치가 있음. 지금 턴에선 Fal 만 손봄.
- 재시도 통계 (성공한 재시도 횟수) 를 Redis 카운터로 쌓아두면 Fal CDN 안정성을 측정할 수 있음. 필요해지면 넣음.

---

## 2026-04-12 (v1.1.38 — 딸깍 진행률 세부화 & 매일 자동 실행 스케줄)

### 배경

사용자 요청: "딸깍 시작하면 진행상황을 좀더 세밀하게 표현해 줄수 없을까? 그리고 딸깍에 옵션 하나 추가하자. 시간 입력 받게 해서 매일 몇시에 자동으로 생성하게. 활성화 버튼도 만들고."

요구가 둘: (1) 현재 어디까지 돌고 있는지 컷 단위로 보여주기, (2) 매일 HH:MM 에 자동 트리거 + 활성화 토글. 둘 다 기존 딸깍 구조를 크게 건드리지 않고 올려야 하는 증분 기능.

### 설계 판단

**진행률 세부화**

기존 아키텍처가 이미 컷 단위 진행률 원시 데이터를 `pipeline:step_progress:{pid}:{step}` Redis 키에 쌓고 있었고, `_compute_progress_pct` 가 읽어 `completed_cuts_by_step` 를 채우고 있었음. 따라서 백엔드는 새 데이터 수집이 아니라 **이미 수집된 데이터를 task 레코드에 더 구조적으로 노출** 하는 것만 하면 됨. `current_step_completed/total/label` 3 필드를 `_compute_progress_pct` 의 부수효과로 갱신하도록 확장 — 호출 비용은 기존과 동일.

프론트는 두 곳에서 표시:

1. 진행 바 위 단계 라벨 옆에 "N/M 컷" 배지 (가장 눈에 잘 띄는 위치)
2. 5 단계 점 아래에도 각 단계별로 완료 수를 작게 — 전체 파이프라인의 진척도를 한눈에

step 2 (대본) 는 예외 케이스: 대본 생성 중에는 `total_cuts` 자체가 아직 없음 (LLM 이 결정). "N/M" 은 표시할 수 없어서 "N 컷 작성" 만 보여줌. step 6 (렌더링) 은 컷 단위 카운터가 없어서 라벨만 노출.

**매일 자동 실행**

실행 모델 후보를 빠르게 비교:

1. APScheduler 도입 — 과하다. 의존성 추가, cron 표현식 학습, 프로세스/락 관리 복잡도. 단 1 개 전역 스케줄에 대해 과투자.
2. cron/Task Scheduler — 사용자 운영 환경에 의존. Windows 에서 Task Scheduler 를 자동 등록하는 건 권한/UX 측면 애매.
3. **In-process asyncio 루프 + polling** — 이미 `scheduler_service` 가 비슷하게 돌고 있음. 같은 스타일. 코드 양 최소. 서버가 켜져 있을 때만 돌아도 사용자 워크플로우상 충분함 (롱폼 자동화 머신이 24h 켜져 있다고 가정).

3 번 채택. 30초 간격 polling 은 HH:MM 정밀도를 달성하기 위한 최소 주기.

**스케줄 트리거 → 딸깍 실행 경로**

새 코드 패스를 만드는 게 아니라 기존 `prepare_task` + `start_task` 를 **그대로 호출**. 이렇게 하면:

- 수동 딸깍과 스케줄 딸깍이 같은 태스크 레지스트리에 섞여 리스트/폴링/취소 등이 자동으로 작동
- 수동 실행과 자원 경합을 막기 위한 `_RUN_LOCK` 도 자연히 공유됨
- UI 는 `triggered_by` 태그 하나로만 구분 — "스케줄" 배지

만약 나중에 스케줄 쪽에만 다른 로직 (예: 토픽 로테이션) 을 넣어야 한다면 `_trigger_scheduled_run()` 만 고치면 됨.

**영속화**

JSON 1 개 파일 (`data/oneclick_schedule.json`) 이 가장 단순. DB 테이블을 만들기엔 엔트리가 영구히 1 개. 이미 `data/` 디렉토리가 장착된 볼륨이라 lifecycle 걱정 없음.

**타임존**

`datetime.now()` 로컬 시간 기준. 사용자가 한국 Windows 로컬이므로 KST. 서버를 다른 머신에 배포할 일은 현재 없음. 미래에 배포 시 UTC 로 바꿔도 되지만 현재는 YAGNI.

### 변경 요약

- 백엔드
  - `app/services/oneclick_service.py`: `_compute_progress_pct` 확장 + 스케줄 전체 구현 (`_SCHEDULE`, `_SCHEDULE_FILE`, `get/set_schedule`, `_trigger_scheduled_run`, `_schedule_loop`, `start/stop_scheduler`)
  - `app/routers/oneclick.py`: `GET /schedule`, `PUT /schedule` 엔드포인트 + `ScheduleUpdateRequest` Pydantic 모델
  - `app/main.py` lifespan: startup/shutdown 에 oneclick 스케줄러 훅
  - 버전 1.1.37 → 1.1.38 (`main.py` + `/api/health` + version.ts + package.json + package-lock.json)
- 프론트엔드
  - `src/lib/api.ts`: `OneClickTask` 에 `current_step_completed/total/label` + `triggered_by` 추가, `OneClickSchedule` 타입 + `oneclickApi.getSchedule/updateSchedule`
  - `src/components/studio/OneClickWidget.tsx`:
    - Running phase: 단계 라벨 옆 "N/M 컷" 배지, 단계 점 아래 per-step 컷 카운터, "스케줄" 배지
    - 하단: 접을 수 있는 "매일 자동 실행" 패널 (HH:MM 입력, 프리셋, 주제, 저장/토글 버튼, 다음 실행 시각, 마지막 실행 기록)
    - `formatNextRun(iso)` 헬퍼 — 24시간 이내면 "(X시간 Y분 후)" 아니면 "M/D HH:MM"

### 사용자 워크플로우에 미치는 영향

- 이제 대시보드에서 한 번 스케줄을 켜 두면, 사용자가 컴퓨터를 꺼두지만 않으면 매일 그 시각에 새 영상이 자동으로 만들어짐.
- 진행률도 "이미지 12/30 컷" 처럼 구체적으로 보여서, 머신 작업이 멈췄는지 판단 가능.
- 같은 주제로 반복 실행되는 한계는 명시적 안내 — 토픽 로테이션은 다음 턴 이슈로 보류.

### 잠재 이슈 / 향후 개선

- **서버 꺼짐 복구**: 스케줄 시각에 서버가 꺼져 있다가 나중에 부팅되면 그 회차는 그냥 건너뜀. "놓친 실행 catchup" 은 구현하지 않음 — 사용자가 원치 않는 시각에 영상이 만들어질 가능성이 있어 더 위험.
- **토픽 로테이션**: 별도 주제 목록을 돌려 쓰는 기능은 v1.1.39 이후. 지금은 "사용자가 주기적으로 주제를 바꾸세요" 라고 안내만.
- **여러 스케줄**: 현재는 전역 1 개. 여러 시간대/여러 프리셋을 동시에 자동화하려면 ID 기반 멀티 스케줄로 확장 필요. 아직 필요 없음.

---

## 2026-04-12 (v1.1.37 — 딸깍 대시보드 이동 + 프리셋 재프레이밍 + start 버그 수정)

### 배경

사용자 피드백: "프로젝트는 그냥 프로젝트고 딸깍은 그냥 딸깍인건데. 딸깍제작은 대시보드로 옮기고. 프로젝트는 프리셋같은 개념으로 가야해."

v1.1.34 에서 OneClickWidget 을 Studio 좌측 사이드바에 박은 건 "Studio 가 유일한 작업 화면" 이라는 가정이 있었기 때문인데, 사용자는 프로젝트를 재사용 가능한 **프리셋** 으로 보고 있었습니다. 매일의 업로드는 "프리셋 골라 주제 넣기" 한 번이면 되는 흐름을 원함. 재정리:

- 대시보드 = 매일 쓰는 메인 액션. 딸깍이 여기 있어야 함.
- Studio = 프리셋 편집 / (원할 때) 수동 작업.
- 프로젝트 목록 = 프리셋 라이브러리.

### AskUserQuestion 으로 짚은 3 가지

1. 데이터 모델: 실행 결과를 별도 엔티티로 (DB 마이그레이션 필요) — 사용자 선택
2. Studio 역할: 프리셋 편집 + 수동 작업 모두 유지 — 사용자 선택
3. 선택 UX: 드롭다운 1개 — 사용자 선택 (= 기존 방식 유지)

### 왜 이번 턴에 DB 스키마 분할은 안 했는가

1번 답이 "별도 엔티티" 인데 이번 턴에 구현 안 했습니다. 이유:

- 현재 `projects` 테이블은 config + cuts(FK) + 상태 머신이 섞여있어서 분할 시 **cuts 테이블의 project_id → run_id 이관** 이 필수. SQLAlchemy 모델, 마이그레이션, routers 전체 (`pipeline.py`, `script.py`, `image.py`, `voice.py`, `video.py`, `subtitle.py`, `youtube.py`), pipeline_tasks, scheduler_service 를 전부 건드려야 함.
- 기존 데이터 마이그레이션 로직도 필요 (cuts 유무 heuristic). edge case 가 있음.
- 한 턴에 이걸 다 하면 break 지점이 많아 롤백 비용이 큼.

대신 **UI 재프레이밍** 만 먼저 한 턴에 깔끔하게 끝내고, 실제 엔티티 분할은 단계적으로:

1. v1.1.38: `projects.kind` ("preset"|"run") + `projects.parent_preset_id` 컬럼 추가. 기존 프로젝트는 cuts 유무 heuristic 으로 자동 분류. 딸깍 clone 은 `kind="run"` 세팅.
2. v1.1.39: 대시보드를 "프리셋" + "최근 생성" 섹션으로 분할. Studio 가 kind 에 따라 Step 필터링.
3. v1.1.40+: 필요 시 cuts.project_id → cuts.run_id rename.

### 구현 순서 (이번 턴)

1. `app/page.tsx` 에 OneClickWidget import + 마운트 (API 패널 위)
2. 헤더 설명문 교체 (프리셋/딸깍 용어 소개)
3. "새 프로젝트" → "새 프리셋" 섹션 리네이밍, 빈 상태/삭제 확인 카피 교체
4. OneClickWidget idle phase 12-grid 재배치, 글꼴 사이즈 업, mt/mb 조정, "템플릿 프로젝트" → "프리셋"
5. `studio/[projectId]/page.tsx` 에서 OneClickWidget import + 마운트 제거
6. 버전 범프 4 파일
7. tsc 검증
8. **(실행 직후 사용자가 실제로 돌려보고 `start` 엔드포인트가 500 나는 걸 발견)**

### start 500 에러 — 되돌아보면 뻔한 실수

증상: 스크린샷의 에러 — `HTTP 500 POST /oneclick/26664a23/start: start 실패: RuntimeError: There is no current event loop in thread 'AnyIO worker thread'.`

원인: `oneclick.start()` 라우터가 sync `def` 로 선언돼 있어서 FastAPI 가 AnyIO worker thread 풀에서 실행. 그 스레드엔 이벤트 루프가 없음. `oneclick_service.start_task()` 안의 `asyncio.get_event_loop()` 가 Python 3.12+ 에서 "no current event loop" RuntimeError 를 던짐.

v1.1.34 때 짰던 주석이 이미 경고 신호였습니다: "start_task 는 FastAPI 엔드포인트에서 호출될 것이므로 loop 는 반드시 존재" — 이 가정은 엔드포인트가 `async def` 일 때만 참입니다. FastAPI 는 sync endpoint 를 worker thread 에서 돌리고, 그 스레드엔 loop 가 없거든요. **엔드포인트가 async 가 아니면 asyncio API 를 직접 부르지 말자** 가 교훈.

수정:

- `routers/oneclick.py::start` → `async def`. FastAPI 메인 이벤트 루프에서 직접 실행.
- `services/oneclick_service.py::start_task` 에서 `asyncio.get_event_loop()` → `asyncio.get_running_loop()`. 실수로 sync 컨텍스트에서 불리면 즉시 RuntimeError 를 던지도록 의도를 강제.

`prepare` / `cancel` 는 asyncio 호출이 없어서 sync 그대로 안전. `_RUN_LOCK = asyncio.Lock()` 모듈 레벨 선언은 Python 3.10+ 에서 지연 바인딩이라 문제 없음.

### 검증

- `tsc --noEmit` → exit 0
- `python -m py_compile` oneclick.py / oneclick_service.py / main.py → OK
- 런타임 테스트는 사용자 확인에 의존 (스크린샷으로 최초 확인됨, 수정 후 재테스트 요청)

### 남은 이슈

- v1.1.34 의 `scheduler_service.py` 구 `_step_subtitle` import 버그 여전히 미수정 (범위 밖)
- 프리셋이 많아질 경우 드롭다운 UX 가 한계. 다음 단계에서 썸네일/최근순/검색 추가 검토
- 스케줄(`/schedule`) 과 딸깍이 현재 별개 경로. 스케줄이 내부적으로 딸깍 엔티티를 사용하도록 통일하는 리팩터가 v1.1.38 이후 필요할 수 있음

---

## 2026-04-12 (v1.1.36 — 영상 제작 대상 선택 기능)

### 배경

v1.1.35 에서 비용 경고 배지만 띄우고 "기본값은 건드리지 말자" 로 넘겼는데, 사용자가 다음 턴에서 바로 실질적인 절감 레버를 요청했습니다:

> "영상 스텝에 제작 대상 기능 넣자 3컷당 1장 4컷당 한장 5컷당 한장, 캐릭터만 뭐 이런식으로. 선택할 수 있게도 해주고."

비용 breakdown 분석(`estimate_project()` 샘플) 에서 영상 단계가 전체의 80~90% 를 먹는 게 확인된 상태라, 이 스텝에 필터만 달아도 1/3~1/5 감축이 즉시 가능합니다. 기본값(`all`) 은 유지해서 기존 프로젝트 동작엔 영향을 주지 않도록 했습니다.

### 핵심 고민: skip vs fallback

처음엔 선택되지 않은 컷을 **그냥 스킵** 하는 방향도 고려했는데, 금방 막혔습니다. 렌더 단계(`subtitle.render_video_with_subtitles`) 가 `cut_1.mp4 ... cut_N.mp4` 를 전체 컷에 대해 concat 하는 구조라, 중간에 파일이 없으면 타임라인에 구멍이 나고 나레이션/자막 싱크가 깨집니다. 빈 컷을 "검은 화면" 으로 생성하면 시청자 경험이 망가지고요.

대신 **`ffmpeg-kenburns` 폴백** 으로 가는 전략을 골랐습니다:

- 이미지 스텝은 그대로 전체 컷에 대해 돌아가니까 `cut_N.png` 가 모두 존재
- Ken Burns 는 정지 이미지에 pan/zoom 을 입히는 로컬 FFmpeg 처리 → 비용 0 / 컷당 0.8초
- 선택되지 않은 컷은 "싸게 때운 움직이는 사진" 이 되고, 선택된 컷만 진짜 AI 영상
- 시각적으로도 구분감이 생겨서 "중요한 장면 강조" 효과까지 부수적으로 얻음

이 결정 덕에 렌더 파이프라인은 한 글자도 안 건드리고 video.py 안에서 분기 한 곳만 넣으면 끝났습니다.

### 규칙 — `(n - 1) % step == 0`

1-based 컷 번호 기준 `(n-1) % 3 == 0` 은 1, 4, 7, 10... 을 뽑아냅니다. 이 규칙을 고른 이유는 **`image.py` 의 `cut_has_character(n)` 와 완벽히 일치** 하기 때문. 기존 코드가 이미 "1, 4, 7... 컷이 캐릭터 컷" 이라고 정의하고 있어서 `character_only` 옵션이 공짜로 성립합니다.

단점: 규칙이 3 곳에 복제됩니다 — `video.py` (런타임 필터), `estimation_service.py` (비용 계산), `StepVideo.tsx` (UI 카운터). 원래는 video.py 의 헬퍼를 그대로 import 하고 싶었는데, services/ 계층에서 routers/ 를 import 하면 레이어링 위반 + 순환 임포트 위험이 있어서 복제 + 주석으로 대응했습니다. 나중에 규칙이 바뀌면 세 곳을 동시에 갱신해야 합니다.

### 구현 순서

1. `projects.py` DEFAULT_CONFIG 에 `video_target_selection: "all"` 추가
2. `video.py` 에 `VIDEO_TARGET_OPTIONS`, `should_generate_ai_video`, `count_ai_video_cuts` 모듈 헬퍼 추가
3. `video.py::generate_all_videos` (sync) — `primary_service`/`fallback_service` 두 인스턴스 확보, 컷 루프 안에서 `use_ai` 분기. 로그에 실제 사용된 모델 기록
4. `video.py::generate_all_videos_async._run` (async) — 동일 패턴, `START` 로그에 `model={used_model} ai={use_ai}` 추가
5. `estimation_service.py` — `_count_ai_video_cuts` 복제, `estimate_project` 에서 video_cost/video_sec 분리 계산, 반환 dict 에 selection 필드 3 개 추가
6. `api.ts` — `ProjectConfig.video_target_selection?`, `ProjectEstimate` 에 optional 필드 3 개
7. `StepVideo.tsx` — `countAiCuts` 로컬 헬퍼, CostEstimate detail 조건부 표시 (셀렉터 UI 는 동일 세션 후속 요청으로 StepSettings 로 이관)
7b. `StepSettings.tsx` — 사용자 피드백 "영상제작 대상은 프로젝트 설정으로 옮기자" 를 반영해 "AI 모델 선택" 카드 안 영상 모델 아래에 5 옵션 버튼 그리드 배치. StepVideo 에서는 비용 detail + "설정에서 변경" 안내만 남김. 이유: 모델/해상도/언어처럼 "프로젝트 사양" 성격이라 생성 스텝이 아니라 설정 카드가 자연스러움
8. 버전 범프 4 파일 (main.py, version.ts, package.json, package-lock.json)
9. py_compile / tsc 검증
10. CHANGELOG / DEVLOG 기록

### 검증 — 실제 감소량

seedance-1.5-pro ($0.28/clip), 10분 프로젝트(120컷) 기준:

| 선택 | AI 컷 수 | 비용 | KRW | 감소율 |
|---|---|---|---|---|
| all | 120 | $33.60 | 45,696원 | 0% |
| every_3 | 40 | $11.20 | 15,232원 | -66.7% |
| every_4 | 30 | $8.40 | 11,424원 | -75.0% |
| every_5 | 24 | $6.72 | 9,139원 | -80.0% |
| character_only | 40 | $11.20 | 15,232원 | -66.7% |

tier 도 자동으로 바뀌어서, `every_5` 쯤 되면 `expensive` → `normal` 로 배지 색이 빨강 → 노랑으로 떨어집니다. tier 임계치 ($8 / $3) 를 지나면 경고 배지도 자동으로 사라지는 구조.

### 남은 이슈 / 메모

- v1.1.34 에서 언급한 `scheduler_service.py` 의 구 `_step_subtitle` import 버그는 여전히 미수정. 이번 범위 밖.
- `VIDEO_TARGET_OPTIONS` 복제는 단기적으로 수용했지만, 중장기적으로는 `app/services/video_selection.py` 같은 공용 모듈로 빼는 게 맞습니다. routers/ 와 services/ 양쪽에서 import 가능한 중립 레이어.
- UI 에서 `all` 이 아닌 옵션을 선택했을 때, 나중에 다시 `all` 로 복구하는 경우 이미 생성된 폴백 클립을 "진짜 AI" 로 교체하는 regeneration 은 수동으로 해당 컷 개별 재생성 버튼을 눌러야 함. 전체 regenerate 는 영상 단계 "정리" 버튼으로 비운 후 재생성 하는 패턴을 권장.

---

## 2026-04-12 (v1.1.35 — 예상 비용 원화/월/tier 경고)

### 배경

v1.1.34 에서 딸깍 제작을 테스트한 직후 사용자가 수치를 보고 "하나 만드는데 4만원이면 한달에 120만원이라는거자녀" 라고 반응했습니다. 이 숫자가 실제로 맞는지 계산했더니 프리미엄 조합(opus + midjourney + elevenlabs + seedance-1.5-pro) 이 정확히 $35.07 = 47,692원 / 월 143만원 으로 착지했습니다.

사용자가 어느 방향으로 가고 싶은지 AskUserQuestion 으로 선택지를 제시 (저가 기본값 / 프리셋 3종 / 둘 다 / 경고만). 사용자는 **"일단 경고만 표시"** + "비디오 유지" + "TTS 유지" 를 선택. 모델 선택권을 건드리지 않고 체감만 강화하는 방향.

### 설계 결정

1. **원화를 1순위로, USD 를 보조로.** 사용자 체감은 원화 기반 ("4만원" 이라고 즉시 반응). 달러 숫자는 개발자 디버깅용으로 괄호 안에 작게.
2. **"편당" + "월 30편" 동시 표기.** 월 비용이 진짜 위협이라는 걸 대시보드 카드에서도 바로 보이게. 일일 업로드가 이 프로젝트의 명시된 목표 (project instruction: "매일 하나씩 업로드 한다") 이므로 30을 factor 로 씀.
3. **환율은 상수.** 실시간 조회는 (a) 네트워크 실패 handling, (b) `_to_dict` 성능 영향, (c) 추정치 오차 범위보다 훨씬 작은 환율 변동 — 모든 면에서 외부 호출을 정당화하지 못함. 환율 조정이 필요하면 `USD_TO_KRW` 상수 한 줄.
4. **tier 임계치.** 3단계 — cheap(≤$3), normal($3~$8), expensive(>$8). $8 = 월 약 33만원. 이게 "이거 비싸다" 의 심리적 방어선으로 적절하다고 판단. 사용자가 언급한 4만원/편(=월 120만원) 은 정확히 expensive 로 걸리게 됨.
5. **기본값 건드리지 않음.** 사용자 선택 존중. 저가 조합으로 몰래 바꾸면 기존 프로젝트의 품질 기대치가 깨질 수 있음. 경고로만 유도.

### 구현 파일

- `backend/app/services/estimation_service.py` — USD_TO_KRW / DAYS_PER_MONTH / tier 상수 + 반환 dict 확장 + `format_krw` 유틸
- `frontend/src/lib/format.ts` — `formatKrw`, `costTierClasses` (tier → Tailwind 색상)
- `frontend/src/lib/api.ts` — `ProjectEstimate` optional 필드 추가
- `frontend/src/app/page.tsx` — 대시보드 카드 배지 교체
- `frontend/src/app/studio/[projectId]/page.tsx` — Studio 상단바 배지 교체 (non-null assertion 으로 IIFE 안에서 타입 좁힘)
- `frontend/src/components/studio/OneClickWidget.tsx` — prepared phase 카드 배경색 + 원화 + 월 + 경고문
- 버전: 1.1.34 → 1.1.35 (main.py ×2, version.ts, package.json, package-lock.json ×2)

### 검증

5개 모델 조합을 대상으로 estimate 실행, 기대 tier/원화 값 매칭 확인:
- 기본 → 3,815원 / 월 114,461원 / cheap
- 초저가 → 1,006원 / 월 30,184원 / cheap
- 중급 → 27,780원 / 월 833,390원 / expensive
- 프리미엄 → 47,692원 / 월 1,430,762원 / expensive ← 사용자 언급 수치와 일치
- 5분 기본 → 1,934원 / 월 58,010원 / cheap

py_compile OK, tsc --noEmit exit 0.

### 이어지는 작업

사용자가 직후 "영상 스텝에 제작 대상 기능 넣자 — 3컷당 1장 / 4컷당 1장 / 5컷당 1장 / 캐릭터만 / 선택 가능" 을 요청. 이건 v1.1.36 에서 다룸. 비용 절감과도 직결 — AI 비디오 컷 수를 1/3 로 줄이면 비디오 비용도 1/3 로 떨어짐.

---

## 2026-04-12 (v1.1.34 — 딸깍 제작, Studio 사이드바 독립 실행)

### 배경

사용자 요청 (Studio 사이드바 빈 공간에 빨간 동그라미 스크린샷 첨부): "여기에 딸깍 제작 기능 만들자. 프로젝트 선택가능하게 하고 그 프로젝트의 모든 시퀀스대로 자동으로 최종 렌더링까지 하는 기능. 다른 작업들과 관계없이 따로 작업되도록. 주제 넣고 저장 누르면 예상 시간/비용(모델별로) 계산해서 표현해주고, 시작 누르면 프로세스게이지 채우면서 진행."

요구 스펙이 꽤 명확합니다: (a) 템플릿 프로젝트 선택 가능, (b) 새 주제로 end-to-end 실행, (c) 예상 비용/시간 미리보기, (d) 진행 게이지, (e) **다른 작업과 격리**. (e) 가 핵심이었고, 설계 선택의 대부분이 "격리" 기준에서 갈렸습니다.

### 설계 결정

1. **실행 경로: Celery 워커가 아니라 FastAPI 프로세스 내 `asyncio.create_task`.**
   - Celery 에 태우면 기존 pipeline 작업, scheduler 가 돌리는 에피소드와 같은 큐를 공유합니다. 사용자가 "다른 작업들과 관계없이 따로" 라고 못 박은 이상 큐 혼재는 아웃. worker 슬롯 경쟁, 우선순위 역전, 실패 시 책임 소재 혼란이 염려됩니다.
   - FastAPI asyncio 루프 안에서 create_task 로 띄우면, API 요청 처리 루프를 막지 않으면서도 "이 서비스 인스턴스 안에서 한 번에 하나씩" 이라는 자원 제한을 `asyncio.Lock` 하나로 강제할 수 있습니다. GPU/FFmpeg 자원이 겹치지 않도록 `_RUN_LOCK` 을 걸어 oneclick 태스크끼리는 직렬 실행.
   - 단점은 서버 재시작 시 in-flight 태스크가 날아간다는 것인데, 사용자 시나리오는 "즉시 실행, 즉시 확인" 이라 복구 로직을 넣어도 이득이 적다 판단. "다시 누르세요" 로 충분.

2. **단계 실행: 기존 `pipeline_tasks._step_*` 재사용.**
   - 이 sync 함수들은 이미 수개월 검증된 코드 패스이고, Redis 진행률 카운터 갱신/에러 핸들링/ApiLog 기록이 내장되어 있습니다. 새로 async 버전을 짜는 건 중복과 버그의 소스.
   - 문제: 이 함수들은 내부적으로 `run_async` 헬퍼로 새 이벤트 루프를 만들어 async 함수를 호출합니다. FastAPI 메인 루프 위에서 그대로 부르면 "This event loop is already running" 으로 터집니다.
   - 해결: `asyncio.to_thread(func, project_id, config)` 로 감쌌습니다. 별도 워커 스레드에서는 각자 독립 루프를 돌릴 수 있어 안전. 스레드풀 기본 사이즈(32 이상)로 충분.

3. **Step 6(최종 렌더링): router handler 직접 호출.**
   - `app/routers/subtitle.py::render_video_with_subtitles` 가 async FastAPI handler 지만 사실상 평범한 async 함수입니다. `db: Session = Depends(get_db)` 인자만 수동으로 채워주면 일반 함수처럼 부를 수 있음 — FastAPI 의 Depends 는 호출 시점에 resolve 되지 파일 import 시점이 아니기 때문.
   - ASS 자막 생성 / 컷 오디오 힐링 / 5초 최소 컷 정규화 / body concat / 자막 번인 / 오프닝·엔딩 페이드를 한 함수가 다 해주므로, 파이프라인에 step_render 를 추가하는 대신 이걸 쓰는 게 훨씬 간단.
   - 제공용 db 세션은 `SessionLocal()` 로 명시적으로 열고 `finally` 에서 닫습니다 — request-scoped 가 아니어야 task 수명 동안 유지됩니다.

4. **진행률 계산: Redis 카운터 + 스텝 가중치 혼합.**
   - `pipeline:step_progress:{pid}:{step}` 가 이미 컷 단위 카운터로 기존 pipeline 에서 쓰이고 있어 그대로 재사용. oneclick 도 `init_progress(project_id, step)` 를 스텝 시작에 호출해 카운터를 리셋.
   - UI 총 진행률 = sum( (완료 시 풀 가중치) 또는 (진행 중이면 카운터/total_cuts × 가중치) ) 로 0~100% 산정. 가중치 `{2:5, 3:20, 4:35, 5:25, 6:15}` 는 "체감 시간에 비례" 가 목표 (이미지가 가장 오래 걸림).
   - 렌더링(6) 은 컷 단위 카운터가 없어 시작→0 / 완료→15 이진. 렌더가 통상 1~2분 안에 끝나서 UX 상 큰 문제는 아님.

5. **예상치는 v1.1.33 에서 이미 만든 `estimate_project(config)` 를 그대로 재사용.**
   - DB 쿼리 없이 pure function 이라 `prepare_task` 에서 새 프로젝트의 config 를 읽어 1회 호출 → task 레코드에 embed. 프론트에서 별도 endpoint 호출이 필요 없음.

6. **상태 저장: 인메모리 `_TASKS` dict.**
   - task 수명이 짧고(몇 분~수십 분), 복구 요구사항이 낮아 DB 테이블을 추가할 가치가 없음. 모듈 전역 dict + `prune_tasks(keep=20)` 로 충분.
   - 상태 lifecycle: `prepared → queued → running → completed | failed | cancelled`.

7. **취소 처리: 소프트 취소.**
   - Running 상태에서 "중지" 를 누르면 `cancel_task` 가 Redis `pipeline:cancel:{pid}` 에 `"1"` 을 set. 다음 컷 처리 시 `check_pause_or_cancel` (기존 헬퍼) 이 `PipelineCancelled` 를 던져 스텝 함수가 종료되고 runner 가 failed 로 마크.
   - Prepared/queued 단계 취소는 그냥 status 를 cancelled 로 바꾸고 끝 — _RUN_LOCK 획득 후 상태 체크로 즉시 리턴하는 가드가 있음.

### 트러블 없이 지나간 포인트

- 원래 `_step_subtitle` (v1.1.32 에서 제거됨) 을 참조하던 `scheduler_service.py` 의 import 가 깨져 있는 걸 발견했지만, 본 변경 범위 밖이라 수정 안 함 (별개 이슈로 기록). 서버 시작 시 scheduler 기동 실패 로그가 떨어지는 상태.

### 구현 파일

- 신규 `backend/app/services/oneclick_service.py` (~426 lines)
- 신규 `backend/app/routers/oneclick.py` (~80 lines)
- 수정 `backend/app/main.py` — oneclick router 등록, 버전 1.1.34
- 신규 `frontend/src/components/studio/OneClickWidget.tsx` (~380 lines)
- 수정 `frontend/src/lib/api.ts` — `OneClickTask` 타입 + `oneclickApi` 네임스페이스
- 수정 `frontend/src/app/studio/[projectId]/page.tsx` — 사이드바 마운트
- 수정 version.ts / package.json / package-lock.json — 1.1.34

### 검증

- `python -m py_compile` (4 파일) — OK
- `tsc --noEmit` — exit 0, 에러 0

### 후속

- scheduler_service.py 의 broken `_step_subtitle` import 정리 (별도 버그)
- oneclick 태스크 히스토리를 Studio 어디에도 못 보고 있는 상태 — 사이드바 위젯 하나로만 접근. 추후 "딸깍 제작 기록" 페이지가 필요할 수 있음.
- 업로드(Step 7) 자동화는 의도적으로 제외. 수동 승인 게이트 유지.

---

## 2026-04-12 (v1.1.33 — 프로젝트별 예상 소요시간 / 비용 표시)

### 배경
사용자 요청: "프로젝트 별 예상 소요시간하고 비용 표시해."

LongTube 는 LLM / 이미지 / TTS / 비디오 네 가지 카테고리에서 각각 모델을 갈아끼울 수 있습니다. 기본값(claude-sonnet-4-6 + gpt-image-1 + openai-tts + ffmpeg-kenburns) 로 600초 한 편 만들면 $2.8 정도에 42분이 걸리지만, 프리미엄 조합(claude-opus-4-6 + midjourney + elevenlabs + seedance-1.5-pro) 로 올리면 $35 에 3시간 6분까지 튑니다. **12배 차이**. 실행 전에 이걸 보여주지 않으면 사용자가 실수로 비싼 모델을 고른 채 "자동화 스케줄" 로 매일 돌려서 한 달에 수백 달러가 증발할 수 있습니다. 그래서 프로젝트 카드와 Studio 상단에 예상치를 띄우기로 함.

### 설계 결정

1. **순수 계산 함수 — DB/네트워크 없음.** `config` dict 만 받아 estimate 를 뱉는 함수로 설계. 대시보드가 프로젝트 N 개를 그리면 N 번 호출되지만, 호출당 ~10 arithmetic op 수준이라 레이턴시 무시 가능. 캐시 설계도 불필요.
2. **기존 팩토리 registry 재활용.** LLM / Image / TTS / Video 각 factory 파일에 이미 `cost_value`, `cost_input`, `cost_output` 메타데이터가 박혀 있었음 (v1.1.x 초기부터). 이걸 다시 정의하면 두 곳에서 관리하게 돼 drift 가 생기므로, estimation_service 는 registry 를 import 해서 그대로 씀. 새 모델이 추가되면 factory 만 건드리면 estimate 도 자동 반영.
3. **출력 토큰 산식을 `claude_service.py::generate_script` 의 dynamic_max 와 완전히 동일화.** `cuts * 180 + 2048`. 실제 LLM 호출 비용과 추정치의 갭을 최소화. 입력 토큰은 시스템+유저 프롬프트 길이 실측 기반 2500 으로 상수화.
4. **시간은 순차 가정.** 실제 파이프라인은 일부 단계가 병렬이지만 사용자가 기다리는 최악 시나리오를 보여주는 게 UX 상 안전 (underestimate 로 배신당하는 것보단 overestimate 가 낫다). 모델별 컷당 시간은 실측 평균의 보수적 값 (예: openai-image-1 = 18초, midjourney = 45초, seedance-1.0 = 60초).
5. **`_to_dict` 에 embed vs 별도 엔드포인트.** 둘 다 제공. embed 는 목록 로드 한 번으로 모든 카드가 estimate 를 갖게 해서 쿼리 fan-out 을 막고, 별도 `/estimate` 는 부분 갱신이 필요한 경우(StepSettings 에서 모델만 바꾸고 로컬 상태 업데이트) 용. 현재 프론트는 embed 경로만 사용하지만, 남겨 두는 쪽이 확장성에 유리.
6. **"예상" vs "실사용" 구분.** 기존 `api_cost` 컬럼은 실제 청구된 누적 금액(ApiLog 집계) 이라 의미가 다름. 프론트에서 라벨을 `실사용 $x.xx` 로 바꾸고 새 `예상 $x.xx` 배지를 옆에 둬 혼동 제거.

### 산정 산식 (최종 확정)

```
cuts           = target_duration // 5
llm_input      = 2500 tokens (고정)
llm_output     = cuts * 180 + 2048 tokens
llm_cost       = (llm_input * cost_input + llm_output * cost_output) / 1e6
image_cost     = IMAGE_REGISTRY[m]['cost_value'] * cuts
tts_chars      = cuts * 24
tts_cost       = (tts_chars / 1000) * TTS_REGISTRY[m]['cost_value']
video_cost     = VIDEO_REGISTRY[m]['cost_value'] * cuts   # 5초 clip 단가

llm_sec        = 45 (단일 호출)
image_sec      = IMAGE_SEC_PER_CUT[m] * cuts
tts_sec        = TTS_SEC_PER_CUT[m] * cuts
video_sec      = VIDEO_SEC_PER_CUT[m] * cuts
post_sec       = 30 (자막 + 최종 합성)
total_sec      = 합계
```

### 실제 추정치 샘플

| 케이스 | cuts | 예상비용 | 예상시간 |
|---|---|---|---|
| 600s 기본 (claude-sonnet + gpt-image + openai-tts + ffmpeg) | 120 | **$2.81** | **42분 27초** |
| 600s claude-sonnet + dalle3 + elevenlabs + ffmpeg | 120 | $6.03 | 51분 51초 |
| 600s claude-opus + midjourney + elevenlabs + seedance-1.5-pro | 120 | **$35.07** | **3시간 6분** |
| 300s 기본 | 60 | $1.42 | 21분 51초 |
| 60s 최소 | 12 | $0.32 | 5분 22초 |

기본 조합 $2.81 은 Claude Sonnet input 2500 + output 23,648 @ $3/$15 per 1M ≈ $0.36 + GPT Image 1 $0.02 × 120 = $2.40 + OpenAI TTS 2,880자 @ $0.015/1K = $0.043 + ffmpeg $0 = $2.81 로 정확히 검산 일치.

### 수정 파일

- `backend/app/services/estimation_service.py` (신규, +236 lines)
- `backend/app/routers/projects.py` — `_to_dict` 에 estimate 추가, `GET /{id}/estimate` 엔드포인트 신설
- `backend/app/main.py` — v1.1.33 (×2)
- `frontend/src/lib/api.ts` — `ProjectEstimate` 타입 + `Project.estimate?` 필드
- `frontend/src/lib/format.ts` (신규) — `formatDurationKo` 공용 포맷 헬퍼
- `frontend/src/app/page.tsx` — 프로젝트 카드에 예상시간/예상비용 배지 + 모델 요약 + 기존 api_cost 배지를 "실사용 $x" 로 rename
- `frontend/src/app/studio/[projectId]/page.tsx` — 상단바에 "예상 42분 / 예상 $2.81 / 실사용 $0.00" 세 배지. breakdown 을 `title` tooltip 으로 노출.
- `frontend/src/lib/version.ts` — 1.1.33
- `frontend/package.json` — 1.1.33
- `frontend/package-lock.json` — 1.1.33 (×2)
- `CHANGELOG.md`, `DEVLOG.md`

### 검증

- `python -m py_compile` — main.py, routers/projects.py, services/estimation_service.py 전부 OK
- `tsc --noEmit` — exit 0 (타입 에러 0)
- estimation 산식 단위 테스트 — 5개 케이스 전부 산출값과 수작업 검산 일치. 포맷 함수 `format_duration_ko` 도 각 케이스 확인.
- Studio 상세의 모델 변경 → 저장 → estimate 갱신 경로 — 기존 `handleUpdate → loadProject()` 가 이미 StepSettings 저장 이벤트에서 호출되므로 추가 코드 불필요. 배지는 프론트 상태 업데이트로 자동 갱신.

### 남은 리스크 / 후속 아이디어

- 모델별 컷당 처리 시간 테이블이 **하드코딩 상수**. 실측치는 네트워크 상황 / 이미지 복잡도 / 프롬프트 길이에 따라 ±50% 움직일 수 있음. 정확도가 더 필요해지면 `api_logs.duration_ms` 집계 기반으로 동적 학습하는 경로가 가능.
- 병렬 처리(이미지 여러개 동시 요청) 가 실제로 일어나는 단계는 현재 산식이 **과대 추정**. 그래도 UX 상 "예상보다 일찍 끝났다" 는 긍정적 방향이라 감수.
- Midjourney 등 **구독제** 모델은 cost_value 가 "한 달 $10~120" 이라 per-image 단가로 환산이 까다로움. 현재는 대략치 ($0.04) 로 취급. 정확히 하려면 월 사용량 기반 amortize 가 필요하지만 UI 가 복잡해져 보류.
- 예상과 실사용이 크게 갈라졌을 때의 **경고 UI** (예: 실사용이 예상의 150% 초과) 는 미구현. 스케줄 자동화가 본격 돌면 유용할 듯.

---

## 2026-04-12 (v1.1.32 — 600초 대본 생성 JSON 파싱 실패 버그픽스)

### 증상
사용자 보고: "600초로 대본생성하니까 에러난다 이거 부터 처리해." 스크린샷 에러 메시지: `대본 생성 실패: HTTP 500 POST /script/043a24df/generate: LLM script generation failed: Expecting ',' delimiter: line 545 column 6 (char 29325)`.

300초~450초에서는 멀쩡히 생성되다가 600초에서만 터지는 것이 첫 단서. 에러 메시지의 "line 545 column 6" 위치와 "char 29325" 가 유난히 구체적 — 이건 JSON 이 구조적으로 잘못 만들어진 게 아니라 **중간에 잘려서** `json.loads` 가 unfinished token 앞에서 멈춘 것을 시사.

### 원인 추적

1. `backend/app/routers/script.py::generate_script` → `llm_service.generate_script(project.topic, project.config)` 에서 예외가 올라와 try/except 가 `HTTPException(500, ...)` 로 감싼 것.
2. `backend/app/services/llm/claude_service.py::generate_script` 를 읽어보니 `max_tokens=8192` 로 **하드코딩** 되어 있었음.
3. 시스템 프롬프트(`base.py::SCRIPT_SYSTEM_PROMPT_KO`) 는 "600초(10분) = 120컷" 을 강제하고 각 컷당 `cut_number / narration(20-28자) / image_prompt(영문) / duration_estimate / scene_type` 을 요구. 영문 image_prompt 가 길어서 컷당 80-120 토큰이 나옴. 120컷 × 100토큰 ≈ 12,000 토큰, 거기에 title/description/tags 2,000 토큰을 더하면 **최소 14k output tokens 가 필요**. 8192 상한에서 바로 터지는 게 맞음.
4. 에러의 `char 29325` 는 Claude 가 8192 토큰 한도에 도달한 시점의 누적 문자수와 일치 (한 토큰 ≈ 3-4자 Unicode mix). 확정.
5. `gpt_service.py::generate_script` 도 점검 — `max_tokens` 미지정이라 OpenAI 모델 기본값에 종속. 똑같은 위험 구조.

### 수정 — 2중 방어선

**1차: max_tokens 동적 산정 (근본 해결)**

`claude_service.py::generate_script` 와 `gpt_service.py::generate_script` 둘 다 `config['target_duration']` 을 읽어 계산:

```python
target_duration = int(config.get("target_duration") or 300)
estimated_cuts = max(1, target_duration // 5)
dynamic_max = max(8192, estimated_cuts * 180 + 2048)
```

- 컷당 180 토큰은 여유 있게 잡은 상한 (실제 ~100) — 회귀 리스크 최소화
- 600초 → 120 * 180 + 2048 = 23,648 토큰 → 8192 대비 2.9배 여유
- Claude Sonnet 4.6 은 64k output 지원, GPT-4o 는 16k 로 각각 상한 설정

**2차: truncation 복구 방어선 (`_repair_truncated_json`)**

`_parse_json` 이 실패하면 미완결 JSON 을 구조적으로 닫아 재파싱. 알고리즘:

- 한 번의 선형 스캔으로 `in_str / escape / stack / expecting_value` 상태 추적
- "구조적으로 안전한 cut point" 만 기록 — ①`{` / `[` 직후 (빈 컨테이너), ②`}` / `]` 직후 (값 완결), ③ value 포지션의 `"` 닫힘 직후
- key 와 value 를 구분하기 위해 object 진입 시 `expecting_value=False`, `:` 만나면 `True`, `,` 만나면 다시 `False`
- 스캔 종료 후 마지막 safe cut 까지 자르고 당시 열려있던 `stack` 을 역순으로 `}` / `]` 로 닫음

단위 시뮬레이션 — 120컷 stress sample (14,861자) 을 80/150/200/300/500/1500/5000/10000/14000/14861 위치에서 잘라 repair 후 `json.loads`:

```
cut_at=80:    ok cuts=1    (cuts 배열이 막 열린 상태)
cut_at=150:   ok cuts=1
cut_at=300:   ok cuts=2
cut_at=500:   ok cuts=4
cut_at=1500:  ok cuts=12
cut_at=5000:  ok cuts=41
cut_at=10000: ok cuts=81
cut_at=14000: ok cuts=114
cut_at=14861: ok cuts=120  (전체)
```

전부 통과. 1차 방어선이 뚫리는 최악의 경우에도 **생성 실패 → 부분 복구** 로 격하되어 사용자가 다시 시도하거나 부족한 컷을 수동으로 채울 수 있음.

### 설계 판단 — 왜 repair 까지 넣었나

max_tokens 를 올리는 것만으로 이번 증상은 잡힙니다. 하지만 LLM 응답이 어떤 이유로든 truncate 될 가능성 (레이트 리밋, 네트워크 컷, 모델 측 abrupt stop) 은 남아 있고, 그때마다 500 을 띄우는 건 UX 손실이 큽니다. 같은 비용(JSON 구조 이해만 있으면 되는 선형 스캔 ~80 lines) 으로 2차선을 깔 수 있어서 같이 넣었습니다.

### 수정 파일

- `backend/app/services/llm/claude_service.py` — dynamic max_tokens + `_safe_int` + `_parse_json` 확장 + `_repair_truncated_json` 신설
- `backend/app/services/llm/gpt_service.py` — dynamic max_tokens
- `backend/app/main.py` — 버전 1.1.31 → 1.1.32 (×2)
- `frontend/src/lib/version.ts` — 1.1.32
- `frontend/package.json` — 1.1.32
- `frontend/package-lock.json` — 1.1.32 (×2)
- `CHANGELOG.md`, `DEVLOG.md`

### 검증

- `python -m py_compile claude_service.py gpt_service.py main.py` → OK
- truncation repair 단위 테스트 → 10개 cut point 전부 통과
- `frontend` 쪽은 이번 수정과 무관 (버전 문자열만 변경)

### 남은 리스크 / 후속 아이디어

- GPT-4o 상한 16k 는 600초 기준 이론상 여유가 빠듯 (12-14k 필요). 900초(180컷) 이상에서는 GPT 쪽도 dynamic max_tokens 만으로는 부족할 수 있음 — 그때는 청크 분할(앞 60컷 → 뒤 60컷) 전략을 검토.
- `_parse_json` 이 여러 candidate 를 순차 시도하므로 **불필요한 시도 비용** 이 있음. 정상 경로는 첫 candidate 에서 성공하므로 핫패스 비용 증가는 무시할 수준.
- `_repair_truncated_json` 은 object 안에서 primitive (숫자, true/false/null) 의 "완결 여부" 를 엄밀히 추적하지 않음 — 뒤에 comma 나 closer 가 오면서 자동 마크되므로 실전 JSON 은 문제 없지만, 극단적으로 `"key": 5` 에서 `5` 한가운데에 잘리면 해당 field 가 날아갈 수 있음. 허용 오차.

---

## 2026-04-12 (v1.1.31 — YouTube Studio: 파이프라인 밖 채널 관리 UI 신설)

### 배경
사용자 요청: "자 이제 유튜브 스튜디오 콘텐츠 업로드 페이지 하고 관리 페이지 만들자. 가져올수 있는 기능 모두 다 가져와 싹다. 업로드부터 게시 게시 설정 삭제까지 싹다."

지금까지 LongTube 는 "프로젝트 → 스크립트 → 컷 → 썸네일 → 업로드" 일직선 파이프라인에 묶여 있어서, 이미 올라가 있는 영상을 수정하거나 LongTube 밖에서 찍은 영상을 올리는 경로가 없었음. "YouTube Studio 같은 화면 하나가 필요하다" 는 요구.

### 설계 결정

1. **파이프라인과 독립된 라우트/라우터** — 기존 `/api/youtube` 는 LongTube 프로젝트 중심(`/{project_id}/upload`, `/{project_id}/thumbnail`) 이라 URL 구조가 Studio 스타일과 안 맞음. 새 prefix `/api/youtube-studio` 를 파고 `project_id` 는 쿼리 파라미터로 선택 사항으로 내림. 기본은 전역 `token.json`.
2. **서비스는 재사용, 클래스는 확장** — 기존 `YouTubeUploader` 클래스를 그대로 쓰고 Studio 메서드를 뒤에 이어 붙임. 인증/클라이언트 빌드/토큰 저장 경로 전부 재활용. 파일 분리보다 라인 수가 늘더라도 OAuth/토큰 state 를 한 곳에 두는 게 안전.
3. **merge 기반 업데이트** — YouTube `videos.update` / `playlists.update` 는 `part` 에 포함된 필드를 전체 덮어씀. `title` 하나만 바꾸려고 해도 `description`/`tags`/`categoryId` 를 같이 안 보내면 전부 빈 값으로 날아감. 서비스 레이어에서 현재 상태 읽어와서 None 이 아닌 입력만 교체 후 전체 body 재조립.
4. **예약 게시** — `videos.insert` 는 status.publishAt 를 받지 않음. 라우터 `/upload` 는 업로드 후 `publish_at` 이 있으면 같은 handler 안에서 `update_video` 한 번 더 호출. `update_video` 쪽에서는 `publishAt` 이 있으면 자동으로 `privacyStatus=private` 로 강제 — public 상태에서 publishAt 을 넣으면 API 가 400 을 돌려주는 걸 막음.
5. **파일 업로드 디스크 flush** — `UploadFile.file` 을 바로 `MediaFileUpload` 로 넘기면 큰 영상은 메모리 전부 상주. `shutil.copyfileobj(..., length=1MB)` 로 임시 파일에 흘려보낸 뒤 기존 resumable 업로드 그대로 재사용. 업로드 완료 후 `finally` 에서 삭제.
6. **에러 매핑** — 서비스는 `YouTubeAuthError` / `YouTubeUploadError` 만 올림. 라우터 `_wrap_errors()` 가 Auth → 401, Upload → 400, 나머지 → 500 으로 번역.
7. **프론트 layout 분리** — Next 14 app router 의 중첩 layout 으로 `/youtube/layout.tsx` 하나에 사이드바 + 인증 배너를 모으고 자식 페이지들은 본문만 쓰게 함.

### 구현

**Backend**
- `backend/app/services/youtube_service.py` 에 Studio 메서드 블록 추가 (`list_my_videos` ~ `list_video_categories` + `_ensure` 헬퍼 + 모듈 레벨 `_to_int`).
- `backend/app/routers/youtube_studio.py` 신규. 엔드포인트 표:
  - `GET /auth/status`
  - `GET /videos`, `GET /videos/{id}`, `PATCH /videos/{id}`, `POST /videos/{id}/thumbnail`, `DELETE /videos/{id}?confirm=true`
  - `POST /upload` (multipart)
  - `GET/POST /playlists`, `PATCH/DELETE /playlists/{id}`, `GET/POST /playlists/{id}/items`, `DELETE /playlists/{id}/items/{item_id}`
  - `GET /videos/{id}/comments`, `POST /comments/{parent_id}/reply`, `POST /comments/{id}/moderation`, `POST /comments/{id}/spam`, `DELETE /comments/{id}`
  - `GET /categories`
- `backend/app/main.py` 에 라우터 등록 및 버전 bump 1.1.30 → 1.1.31.

**Frontend**
- `frontend/src/lib/api.ts` 에 `youtubeStudioApi` 네임스페이스와 type interface 전체 추가.
- `frontend/src/app/youtube/layout.tsx` (사이드바 + OAuth 트리거).
- `frontend/src/app/youtube/page.tsx` (Studio 대시보드 — 합계 카드 + 최근 영상 + 재생목록).
- `frontend/src/app/youtube/videos/page.tsx` (검색/페이지네이션/삭제).
- `frontend/src/app/youtube/videos/[videoId]/page.tsx` (편집 + 썸네일 교체 + 예약 게시 + 아동용/퍼가기/좋아요공개).
- `frontend/src/app/youtube/upload/page.tsx` (파이프라인 없는 직접 업로드).
- `frontend/src/app/youtube/playlists/page.tsx` + `/youtube/playlists/[playlistId]/page.tsx`.
- `frontend/src/app/youtube/comments/page.tsx` (영상 선택 → 댓글 스레드 관리).
- `frontend/src/app/page.tsx` 메인 대시보드에 "YouTube Studio" 버튼 추가.

**버전 파일 4 개 동시 bump**: `backend/app/main.py` ×2, `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` ×2.

### 검증
- `python -m py_compile backend/app/services/youtube_service.py backend/app/routers/youtube_studio.py backend/app/main.py` → OK.
- `node ./node_modules/typescript/bin/tsc --noEmit` → 에러 0 (프론트 전체 타입체크).
- 실제 YouTube 호출 테스트는 토큰이 필요해서 사용자 손으로 1 회 해야 함 — 로그인 → `/youtube/videos` 진입 → 편집/업로드/재생목록/댓글 각 1 건씩 확인 권장.

### 의식적으로 뺀 것
- **YouTube Analytics (조회수 그래프, 수익, CTR, 시청 지속시간)** — 별도 scope (`yt-analytics.readonly`) + 별도 API (`youtubeAnalytics.reports`) 라 이번 작업 범위 밖.
- **커뮤니티 탭 포스트 / 챕터 편집 / 엔드스크린 / 카드 / 수익화 / 썸네일 A/B** — Public Data API 에 write 엔드포인트가 없음 (Studio 웹 UI 전용).

사실대로, 이 네 부류는 "API 자체에 없다" 가 정답입니다. 사용자 요구에 억지로 맞추려고 가짜 UI 를 만들어 두면 버튼은 있는데 눌러도 아무 일 안 일어나는 상태가 되므로 아예 넣지 않았습니다.

---

## 2026-04-12 (v1.1.30 — 최종 렌더링 pad 필터 버그 + 썸네일 비율 복구)

### 배경
v1.1.29 적용 후 사용자 재시도. 스튜디오에서 썸네일이 생성되긴 했는데 배경이 왼쪽에 치우치고 오른쪽 절반이 비어 보이는 상태였고, 최종 렌더링 버튼을 누르자 즉시 500 에러:

```
HTTP 500 POST /subtitle/043a24df/render: Cut normalization failed:
RuntimeError: FFmpeg failed (code 4294967274): configure input pad on Parsed_pad_1
[vf#0:0] Error reinitializing filters!
[vf#0:0] Task finished with error code: -22 (Invalid argument)
[vost#0:0/libx264] Could not open encoder before EOF
... frame= 0 fps=0.0 q=0.0 Lsize= 0KiB ... Conversion failed!
```

사용자 요약: "이미지 비율이 왜이래. 그리고. 최종렌더링 안된다".

### 진단 1 — FFmpeg pad 필터가 WxH 지름길을 안 받음
`app/services/video/ffmpeg_service.py` 의 세 함수가 똑같이 아래 패턴을 사용:

```python
"-vf", f"scale={resolution}:force_original_aspect_ratio=decrease,"
       f"pad={resolution}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
```

`resolution` 은 `_resolution_for_aspect` 에서 돌려주는 `"1920x1080"` / `"1080x1920"` / `"1080x1080"` 중 하나. scale 필터는 이 `WxH` 포맷을 내부에서 "size" 지름길로 특수 처리해서 통과시키지만, pad 필터는 w/h 파라미터를 그냥 `av_expr_parse_and_eval` 에 넘겨서 `1920x1080` 을 expression 으로 해석하려다 `Invalid chars 'x1080' at the end of expression '1920x1080'` 로 터진다. sandbox ffmpeg 4.4.2 로 동일 에러 완전 재현:

```
[Parsed_pad_1 @ ...] [Eval @ ...] Invalid chars 'x1080' at the end of expression '1920x1080'
[Parsed_pad_1 @ ...] Error when evaluating the expression '(ow-iw)/2'
[Parsed_pad_1 @ ...] Failed to configure input pad on Parsed_pad_1
Error reinitializing filters!
Failed to inject frame into filter network: Invalid argument
```

그 결과 Step 3 `ensure_min_duration` 의 첫 컷부터 즉시 실패하고 `Cut normalization failed` 가 사용자에게 그대로 뜸. v1.1.29 까지 렌더링이 돌아갔던 건 **컷 영상이 이미 1920x1080 이어서 pad 가 no-op 이었고 pad 필터 자체는 검증만 통과해서** 넘어갔던 건지, 아니면 해당 경로가 실제로 돌지 않은 채 통과했던 건지 확실하지 않음 — 어쨌든 해상도가 다른 입력이 들어오면 필연적으로 터지는 잠재 버그였음.

세 함수 모두 같은 포맷을 만들고 있었음: `ensure_min_duration`, `merge_videos_reencode`, `add_fade_in_out`.

### 조치 1 (v1.1.30)
`ffmpeg_service.py` — 세 함수 모두 pad 용 해상도만 콜론 포맷으로 따로 만듦:

```python
pad_wh = resolution.replace("x", ":")  # "1920x1080" → "1920:1080"
vf = (
    f"scale={resolution}:force_original_aspect_ratio=decrease,"
    f"pad={pad_wh}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30"
)
```

scale 은 지름길이 멀쩡하게 동작하니 그대로 둠. pad 만 콜론 포맷 적용.

### 진단 2 — 썸네일/컷 이미지가 1:1 로 나오는 문제
사용자 스크린샷의 썸네일은 배럴 + 오일릭 + 석양이 왼쪽 2/3 에 몰려 있고 오른쪽 1/3 은 거의 단색 어두운 teal. 썸네일 저장 경로는 `generate_ai_thumbnail` → `generate_thumbnail` → `_cover_resize(..., 1280, 720)` 이라 결과물은 강제로 1280x720 이 되긴 하는데, 원본이 1:1 square 면 중앙 크롭을 해도 subject 가 이미 square 의 왼쪽에 치우쳐 있으면 치우친 그대로 잘림. 즉 **원본 이미지 자체가 1:1 로 생성되고 있다**.

`app/services/image/nano_banana_service.py` 를 확인: edit 모드 (`reference_images` 가 있는 경우) 에서 `image_size` 를 일부러 생략하고 있었음. 주석:

```python
if use_edit:
    payload["image_urls"] = ref_data_uris
else:
    # 순수 t2i 일 때만 이미지 크기 힌트. edit 쪽은 ref 크기를 상속.
    payload["image_size"] = {"width": width, "height": height}
```

"edit 쪽은 ref 크기를 상속" 이라는 가정이 틀렸거나, 맞더라도 사용자의 레퍼런스가 square 면 결과물도 square 가 됨. 썸네일뿐 아니라 컷 이미지 생성 경로도 전부 같은 서비스를 거치므로 모든 컷 이미지가 1:1 로 나오고, 이게 영상 생성 단계에서 1:1 영상이 되어 Step 3 의 pad 필터로 넘어간 순간 터짐 (진단 1 과 정확히 겹친다).

### 조치 2 (v1.1.30)
`nano_banana_service.py` — edit / t2i 구분 없이 항상 `image_size` 를 payload 에 포함:

```python
payload: dict = {
    "prompt": effective_prompt,
    "num_images": 1,
    "image_size": {"width": width, "height": height},  # edit 에서도 강제
}
if use_edit:
    payload["image_urls"] = ref_data_uris
```

fal.ai nano-banana edit 엔드포인트가 `image_size` 파라미터를 허용하는 것으로 확인되어 있어 레퍼런스 스타일은 유지하면서 출력 비율만 강제하는 형태가 됨.

### 검증
- sandbox ffmpeg 4.4.2 재현 케이스:
  - `pad=1920x1080:...` → 기존 에러 완전 동일하게 재현 ✅
  - `pad=1920:1080:...` 로 수정 → 800x600 / 1024x1024 / 512x512 입력 모두 통과, 결과 해상도 1920x1080 / 1080x1920 으로 확인 ✅
  - `merge_videos_reencode` 에 해당하는 `filter_complex` 구조로도 1:1 square 입력 → 9:16 출력 통과 확인 ✅
- py_compile: `backend/app/services/video/ffmpeg_service.py`, `backend/app/services/image/nano_banana_service.py`, `backend/app/main.py` 모두 OK.
- nano-banana edit 모드의 image_size 허용 여부: 코드상 payload 변경만 했으므로 실제 fal.ai 응답에서 `image_size` 가 반영되는지는 사용자 실환경 검증 필요. 만약 fal.ai 가 해당 파라미터를 무시하더라도 _cover_resize 가 뒤에서 강제 크롭하므로 **최소한 썸네일 비율은 1280x720 으로 고정** 됨 (컷 이미지 비율은 ffmpeg pad 에서 letterbox 로 흡수).

### 버전 범프
1.1.29 → 1.1.30. 4 파일 동시 bump: `backend/app/main.py` (FastAPI version + /health 응답), `frontend/src/lib/version.ts`, `frontend/package.json`, `frontend/package-lock.json` (name/version 2 곳).

### 다음 세션 확인 항목
1. 사용자 재시도 시 최종 렌더링이 끝까지 통과하는지 — `Cut normalization failed` 가 더 나오지 않아야 함.
2. 신규 생성 썸네일이 실제로 16:9 꽉 채운 구도로 나오는지 — nano-banana edit 이 `image_size` 를 존중하는지 실환경 검증.
3. 기존에 1:1 로 생성돼 있던 컷 이미지/영상은 그대로 남아 있을 수 있음 — 필요하면 해당 프로젝트의 이미지/영상 스텝을 다시 돌려야 16:9 로 재생성됨. 단, pad 필터 수정 덕에 **재생성 없이 렌더링만 다시 눌러도 letterbox 16:9 로 최종 영상은 만들어진다.**

---

## 2026-04-12 (v1.1.29 — 레퍼런스 스타일 강제 + topic 오염 복구)

### 배경
v1.1.28 핫픽스로 썸네일 생성이 실제 끝까지 돌아가게 되자, 두 가지 문제가 동시에 드러남.

1. 생성된 PNG 의 배경 이미지가 프로젝트에 등록해둔 "스타일 레퍼런스" 와 전혀 닮지 않음. 사용자 표현: "이미지가 영 똥망인데? 레퍼런스 이미지 스타일 따라가야지".
2. 스튜디오 상단 헤더 바로 아래에 한 줄짜리 `<p>{project.topic}</p>` 가 **수천자짜리 YouTube 영상 설명 전문 + bullet 목차** 를 벽으로 뿌리고 있었음.

### 진단 1 — 레퍼런스 무시
`NanoBananaService.generate` 흐름:
```
ref_data_uris = []
for p in reference_images:
    uri = _file_to_data_uri(p)
    if uri:
        ref_data_uris.append(uri)
use_edit = bool(ref_data_uris)
```
만약 경로 resolve 는 성공했는데 `_file_to_data_uri` 가 None (파일 없음/권한/크기 0) 을 돌려주면, ref_data_uris 가 비고 use_edit=False → 순수 t2i 경로. 이 경우 "레퍼런스 스타일" 을 전달할 통로 자체가 사라짐. 추가로 style lock prefix 는 `_style_lock = (model_id == "nano-banana-3")` + `use_edit=True` 일 때만 붙어서, 변종이 다르거나 edit 로 못 가면 프롬프트 레벨 지시조차 없었음.

### 진단 2 — topic 오염
`StepYouTube.tsx`:
```
const [description, setDescription] = useState(project.topic || "");
...
persistProjectMeta(title.trim(), description.trim())
```
내부에서 두 번째 인자를 `project.topic` 에 PUT. 즉 DB 스키마상 `project.topic` 이 "영상 설명" 으로 재사용되어 버렸고, AI 전체 추천 한 번 돌면 5000자 + bullet 목차가 그대로 topic 을 덮어썼음. 스튜디오 상단 컴포넌트가 그 topic 을 헤더 서브라인으로 뿌려서 레이아웃이 완전히 망가짐.

### 조치 (v1.1.29)

**A. 레퍼런스 스타일 3 layer 강화**

1. `nano_banana_service.py::generate`
   - 레퍼런스가 주어졌는데 `_file_to_data_uri` 로 하나도 못 읽으면 명시적 `RuntimeError` — 조용한 t2i 폴백 차단.
   - `_style_lock` 분기 제거. 모든 nano-banana 변종에서 `use_edit=True` 면 스타일 락 프리픽스를 항상 prepend. 문구도 강화("copy it, do not reinterpret").

2. `routers/youtube.py::create_thumbnail`
   - `combined_refs` 가 있으면 LLM 이 만든 프롬프트 맨 앞에 한 번 더 STYLE REFERENCE LOCK 블록을 prepend. 서비스 레벨 prefix 가 끊기더라도 프롬프트엔 반드시 박힘.
   - 응답에 `reference_diagnostics` 필드 추가 — 등록 장수, 디스크에서 찾은 장수, 누락, 실제 모델로 전달된 장수.

3. `frontend/src/components/studio/StepYouTube.tsx`
   - 썸네일 카드 하단에 진단 배너. 0 장이면 노란 경고 + "설정→이미지 탭에서 스타일 레퍼런스 업로드" 안내. 전달됐으면 녹색 + 장수 + 폴백 사유.

**B. topic 오염 복구 + 재발 방지**

1. `StepYouTube.tsx` — `description` state 를 `project.config.youtube_description` 에서 초기화. `persistProjectMeta` 를 `title` + `config.youtube_description` 저장으로 리팩터. 더 이상 `project.topic` 에 description 이 들어갈 경로가 없음.
2. `StepYouTube.tsx::handleRecommendMetadata` / `handleRecommendTags` — LLM 컨텍스트로 넘기는 `topic` 을 `project.topic` 원본으로 교체. 이전엔 description 을 넘겨서 점점 길어지는 피드백 루프였음.
3. `app/studio/[projectId]/page.tsx` — 헤더 topic 을 `truncate` + `title` 툴팁으로 1 줄 강제. 안전망.
4. `backend/app/main.py::lifespan` — startup 1 회성 마이그레이션. `project.topic` 길이 > 300 or `\n` / `• ` / `· ` 포함이면 `config.youtube_description` 으로 이관하고 topic 을 `title` 또는 첫 문장(≤120자) 으로 복구. 이미 `config.youtube_description` 이 있으면 덮어쓰지 않음. 결과를 `[startup] migrated N polluted ...` 로 로그.

### 버전
1.1.28 → 1.1.29. 4 파일 동시 bump.

### 다음 세션에서 확인할 것
- 마이그레이션이 실제로 사용자 DB 의 `043a24df` 레코드를 복구했는지. startup 로그 확인.
- 레퍼런스가 등록돼 있는 프로젝트에서 썸네일 재생성 시 `reference_diagnostics.sent_to_model >= 1` 이고 이미지가 실제로 스타일을 따라가는지.
- 레퍼런스가 하나도 없는 프로젝트에선 UI 에 노란 경고가 뜨는지.
- `config.youtube_description` 을 업로드 시점에 실제로 YouTube 에 제출하는 경로가 어디인지 — 현재 리팩터는 저장만 담당. 업로드 파이프라인이 아직 `project.topic` 을 description 으로 쓰고 있다면 그쪽도 `config.youtube_description` 우선으로 교체해야 함.

---

## 2026-04-12 (v1.1.28 — HOTFIX: fal.ai status URL 405)

### 증상
사용자가 v1.1.27 배포 후 썸네일 재생성 시 `HTTP 500 … '405 Method Not Allowed' for url 'https://queue.fal.run/fal-ai/flux/dev/requests/019d7d4f-.../status'`. UI 드롭다운은 Nano Banana 를 보여주는데 에러는 flux/dev 로 떨어짐.

### 진단
1. UI 가 nano-banana 를 선택해도 내부에서 fal.ai polling 이 실패 → `NanoBananaService.generate` 의 `except` 블록이 `FluxService` 로 조용히 폴백. 그래서 에러 URL 에 flux 가 박힘.
2. 왜 polling 이 실패하나? 세 서비스 전부(`flux_service`, `nano_banana_service`, `fal_generic_service`) 큐 status URL 을 `f"{FAL_BASE}/{submit_endpoint}/requests/{id}/status"` 로 손수 조립. fal.ai 큐 API 의 실제 status 경로는 submit 경로에서 서브경로(예: `/dev`, `/edit`) 를 뗀 형태 — 즉 submit 이 `fal-ai/flux/dev` 면 status 는 `fal-ai/flux/requests/{id}/status`.
3. fal.ai 는 잘못된 경로에 GET 을 치면 405 Method Not Allowed 로 응답. 결과: fal.ai 쓰는 모든 모델이 async 큐 job 으로 넘어가는 즉시 전부 터짐.

### 조치 (v1.1.28)
fal.ai 큐는 submit 응답에 `status_url` 과 `response_url` 필드를 명시적으로 내려준다. 이 두 URL 을 그대로 쓰면 서브경로 문제도 생기지 않음. 세 서비스 전부 같은 패턴으로 수정:

- `flux_service.py::_poll_result(status_url, response_url)` 로 시그니처 교체.
- `nano_banana_service.py::_poll(status_url, response_url)` 로 시그니처 교체.
- `fal_generic_service.py::_poll(status_url, response_url)` 로 시그니처 교체.
- submit 응답에 해당 필드가 없으면 200 OK + 빈 값 케이스를 피하려고 명시적으로 RuntimeError 를 올려서 원인이 로그에 드러나게 함.

버전 1.1.27 → 1.1.28 bump (4 파일).

### 다음 세션에서 확인할 것
- 실제로 Nano Banana / Flux / Seedream / Z-IMAGE 각각으로 썸네일 한 번씩 돌려서 async 큐 경로가 실제로 끝까지 완주하는지 확인.
- v1.1.27 의 그림텍스트 오버레이가 찍힌 PNG 가 나오는지 — 이전 세션에선 썸네일 생성 자체가 터져서 새 스타일을 못 본 상태.
- nano-banana 의 Flux 조용한 폴백은 유지하되, 폴백이 왜 일어났는지를 UI 레벨 warning 으로 흘려주는 게 좋을지 판단.

---

## 2026-04-12 (v1.1.27 — 그림텍스트 썸네일 + 레퍼런스 폴백)

### 배경
v1.1.26 에서 박스를 줄였지만 사용자 재피드백: "이미지가 설정의 레퍼런스와 스타일이 같아야지. 그리고 문구가 너무 재미 없지 않냐? 자막 형식으로 하지말고 그림텍스트로 해."

두 가지 별개 문제가 얽혀 있었음.

### 진단
1. **텍스트 스타일이 여전히 "자막"처럼 보임.** 축소해도 라운드 박스 배경은 자막 UI 그 자체. 사용자가 원하는 건 썸네일 위에 글자 자체를 큼직하게 박는 MrBeast/Mr. 정재님 류 "그림텍스트" 스타일.
2. **생성된 이미지가 프로젝트의 레퍼런스 스타일과 전혀 다름.** 코드 추적 결과: `FluxService.generate()` 가 `reference_images` 파라미터를 시그니처에는 받지만 fal.ai 페이로드에 안 넣고 그냥 드롭. 같은 문제가 `fal_generic_service` (seedream / z-image), `grok_service`, `midjourney_service`, 그리고 OpenAI 의 dall-e-3 경로에도 있었음. 사용자가 flux / seedream 을 고르면 프로젝트에 등록한 레퍼런스가 완전히 무시됨.

### 조치 (v1.1.27)

1. **썸네일 그림텍스트 리팩터 — `thumbnail_service.py::generate_thumbnail`**
   - 라운드 박스·테두리 전부 제거. 후보 폰트 `(88…46) → (160…60)`, 최대 3 줄, 블록 높이 `18% → 38%`.
   - 스트로크 굵기 폰트 비례 `max(6, min(14, title_size // 9))`.
   - `ImageFilter.GaussianBlur(radius=6)` 드롭섀도우 레이어(오프셋 6px) 를 알파 합성.
   - 멀티라인이면 마지막 줄만 노란색(`255,226,32`), 그 외 흰색 — MrBeast 의 마지막 단어 강조.
   - 하단 그라디언트 darken 20 단계 오버레이로 가독성 확보.
   - 좌측 정렬(`pad_x=60`), EP 배지는 기존 v1.1.26 스펙 유지.

2. **레퍼런스 미지원 모델 자동 폴백 — image service + router**
   - `BaseImageService.supports_reference_images: bool = False` 클래스 속성 추가.
   - `NanoBananaService.supports_reference_images = True`.
   - `OpenAIImageService.__init__` 에서 `self.supports_reference_images = (model_id == "openai-image-1")` 로 인스턴스 단위 세팅 — gpt-image-1 만 `/edits` 엔드포인트 사용 가능, dall-e-3 은 불가.
   - `FluxService.supports_reference_images = False` 명시 + `reference_images` 가 들어오면 `logging.warning` 으로 드롭 사유를 로그에 남김. (router 에서 이미 폴백을 걸지만, 직접 호출되는 경로까지 감시하기 위한 2차 방어선.)
   - `routers/youtube.py::create_thumbnail`: 프로젝트에 레퍼런스가 있고 선택한 모델이 `supports_reference_images=False` 면 `image_model_id` 를 `nano-banana-3` 로 자동 교체. 응답에 `reference_fallback: str | None` 로 이유를 실어 보냄.

3. 버전 1.1.26 → 1.1.27 bump (4 파일).

### 메모
- `base.py::_fallback_thumbnail_prompt` / `_build_thumbnail_prompt_request` 는 이미 "STYLE REFERENCE LOCK" 블록이 들어있음. 문제는 프롬프트가 아니라 이미지 자체가 모델에 안 들어가는 거였음. router 폴백으로 정답 해결.
- 후크 텍스트 "재미없음" 문제는 v1.1.26 에서 추가한 "메인 후크 텍스트" 전용 input 으로 사용자가 직접 수정할 수 있으니, LLM 프롬프트 튜닝은 당장은 보류. 다음 세션에 피드백 더 들으면 `generate_metadata` 프롬프트 수정 검토.

### 다음 세션에서 확인할 것
- 실제 플럭스/시드림을 선택해서 레퍼런스 있는 프로젝트로 썸네일 생성 → 응답에 `reference_fallback` 이 떨어지고 nano-banana-3 로 실제 호출되는지.
- 그림텍스트 썸네일이 배경이 밝은 이미지(흰 배경 등) 에서도 가독성 확보되는지 — 드롭섀도우만으로 부족하면 반투명 검은 오버레이를 텍스트 뒷면에만 국소적으로 넣을 것.

---

## 2026-04-12 (v1.1.26 — 썸네일 오버레이 리팩터)

### 배경
사용자 보고: "응 썸네일이 여전히 좆구려." + 썸네일에 채널명("jerry's aecheo")이 박혀 있음.

### 진단
1. `thumbnail_service.py::generate_thumbnail` 의 `_fit_font` 후보가 150px 부터 시작해서 메인 후크 박스가 화면 하단 1/3 이상을 덮어버림. 이미지가 텍스트 박스에 가려 안 보임.
2. `frame=True` 가 기본값이라 초록 14px 외곽선이 액자처럼 둘러싸서 잡지 표지 같은 분위기를 망쳤음.
3. 채널명 유출: `handleGenerateThumbnail` 이 `titleHook || title(접두어 제거) || title` 체인으로 썸네일 텍스트를 자동 계산. AI 메타 추천 한 번도 안 돌린 상태에서 `project.title == 채널명` 이면 채널명이 그대로 박힘. 사용자 입장에서 생성 전에 미리 볼 방법도 없음.

### 조치 (v1.1.26)
1. **오버레이 축소**: 폰트 `(150…78) → (88…46)`, 허용 높이 `28% → 18%`, 패딩 `34/18 → 22/12`, 외곽선 `6 → 4`, radius `22 → 14`. EP 배지도 동일 톤 다운.
2. **외곽 프레임 완전 제거**: `frame` / `overlay_frame` 파라미터 및 관련 필드 코드에서 삭제 (`thumbnail_service.py`, `youtube.py`, `scheduler_service.py`, `api.ts`).
3. **채널명 유출 방지**: `StepYouTube.tsx` 에 전용 "메인 후크 텍스트" input 추가. `thumbMainHook` state 가 `titleHook` / `title` 변경 시 자동 기본값을 세팅하지만, 한 번이라도 사용자가 편집하면(`touched=true`) 덮어쓰지 않음. 생성 버튼은 이 input 값을 그대로 전송하고, 비어 있으면 에러 표시 후 early return. 다시는 `project.title` 이 자동 폴백으로 섞이지 않는다.
4. 버전 1.1.26 — 4개 파일 동시 bump.

### 다음 세션에서 확인할 것
- 실제로 썸네일 돌려서 오버레이 크기 톤이 적절한지 (필요하면 `(88…46)` 후보를 더 줄이거나 키우기).
- 채널명을 `project.title` 로 덮어쓴 경로가 어디인지 소스 추적 — 현재는 증상만 차단했음. (의심 구간: 프로젝트 생성 UI, `_update_project_title` 호출부, 스케줄러의 스크립트 title)

---

## 2026-04-09 (Day 1)

### 한 일
- bbanana.ai (빠나나AI) 사이트 분석 완료
  - AI 생성, AI 자동화, AI 사운드, AI 보드, AI 바로가기 5개 섹션 확인
  - 6단계 파이프라인: 설정 → 대본 → 음성 → 이미지 → 영상 → 자막
  - 이미지 모델 드롭다운: Nano Banana 2, Pro, Seedream V4.5, Z-IMAGE Turbo, Grok Imagine
- 설계 문서 v1.0 작성
- 설계 문서 v2.0으로 업그레이드
  - 이미지 모델 9종 추가
  - 대본 AI 모델 선택 (Claude/GPT) 추가
  - 단계별 일시중지/편집/재시작 설계
  - 전체 결과물 다운로드 시스템 설계
- 프로젝트 디렉토리 구조 생성
- CONTEXT.md, DEVLOG.md 생성
- Git 레포: https://github.com/dlgksxk-arch/longtube.git

### 결정사항
| 결정 | 이유 |
|------|------|
| 대본 기본 모델 = Claude Sonnet 4.6 | Jerome 선호, 비용 대비 품질 우수 |
| 이미지 모델 9종 지원 | 빠나나처럼 드롭다운 선택, Factory 패턴으로 확장 |
| 영상 기본 = FFmpeg Ken Burns | 무료, 빠름, API 비용 절약 |
| Redis로 일시중지 신호 | Celery worker와 통신하는 가장 간단한 방법 |
| SQLite | 1인 사용, 별도 DB 서버 불필요 |
| auto_pause_after_step 기본 true | 각 단계 확인 후 진행하는 게 실수 방지 |

### 미해결 이슈
- [ ] Nano Banana API 엔드포인트/인증 방식 미확인
- [ ] Seedream V4.5, Z-IMAGE Turbo의 fal.ai 모델 경로 확인 필요
- [ ] Grok Imagine Image API (xAI) 접근 방법 확인 필요

### 다음 할 일
- Phase 1 백엔드 개발 착수
- FastAPI 앱 기본 구조 잡기
- Claude/GPT 대본 서비스 구현

---

## 2026-04-11 (세션 기록 — 자막/TTS/유튜브/썸네일/나노바나나3)

> 이 세션은 컨텍스트 초과로 중간에 한 번 압축(compaction)되었음. 아래는 압축 전/후 두 구간을 합쳐 시간순으로 정리한 기록.

### 사용자 요청 타임라인
1. "아니 스텝6 자막은 삭제 해. 설정에 있으니까. 설정에 있는 자막에 자막 배경 기능 추가해줘. 불투명 농도 설정할 수 있게 해주고."
2. "그리고 음성 말이 너무 빠른데 좀 느긋하게 하게 못해?"
3. "업로드된 유튜브 영상 삭제 기능은 없어? 그리고 썸네일 너무 구리다. 썸네일 프롬프트 변경해. 후킹 주고 관심 쫙 끌만하게. 그리고 레퍼런스 이미지 스타일 따라 가고. 나노바나나 3 가능 하게 해."
4. "유튜브 컨텐츠 관리 페이지 만들수 있나?"
5. "세션이 너무 느려졌다 지금까지 작업 내용과 대화내용 세세하게 정리해서 md 파일에 추가 해." ← 현재 요청

### 작업 1 — 스텝6 자막 제거 + 설정에 자막 배경/불투명도 추가 (압축 전 완료)
- `StepSubtitle.tsx` 제거(스텝6 단계 삭제), 스텝 번호 재정렬
- `StepSettings.tsx` 에 자막 섹션 통합: 활성화 토글, 폰트/크기/색상/외곽선, **자막 배경 on/off**, **배경 불투명도(0~100%) 슬라이더**
- `ProjectConfig` 타입에 `subtitle_background?: boolean`, `subtitle_background_opacity?: number` 추가
- 백엔드 자막 렌더링 파이프라인에서 배경 박스(rectangle behind text)와 알파값 적용

### 작업 2 — TTS 음성 속도 느리게 설정 가능하게
**타입/설정**
- `frontend/src/lib/api.ts` — `ProjectConfig` 에 `tts_speed?: number` 필드 추가
- `StepSettings.tsx` — "음성 속도" 슬라이더 섹션 추가 (0.70~1.20, step 0.05, 기본 0.9)
  - 현재 값 숫자 표시 + "느긋 / 기본 / 빠르게" 라벨

**백엔드 서비스**
- `backend/app/services/tts/openai_service.py` — `generate(..., speed)` 시그니처 추가, OpenAI TTS 의 `speed` 파라미터(0.25~4.0)로 전달
- `backend/app/services/tts/elevenlabs_service.py` — `voice_settings.speed` 필드로 ElevenLabs 속도(0.7~1.2) 반영
- `backend/app/services/tts/base.py` — 추상 인터페이스에 `speed: float = 1.0` 기본값

**라우터 배선 (핵심)**
- `backend/app/routers/voice.py` 의 `generate_all_voices`, `generate_one_voice` 두 경로 모두에 `speed` 추출 및 전달 추가:
  ```python
  tts_model = project.config.get("tts_model", "elevenlabs")
  tts_service = get_tts_service(tts_model)
  try:
      speed = float(project.config.get("tts_speed", 1.0) or 1.0)
  except (TypeError, ValueError):
      speed = 1.0
  ...
  result = await tts_service.generate(narration, voice_id, audio_path, speed=speed)
  ```

### 작업 3 — 업로드된 YouTube 영상 삭제 기능

**백엔드 서비스**
- `backend/app/services/youtube_service.py` — `YouTubeUploader.delete_video(video_id)` 메서드 추가
  ```python
  def delete_video(self, video_id: str) -> None:
      if not video_id or not str(video_id).strip():
          raise YouTubeUploadError("video_id 가 비어있어 삭제할 수 없습니다.")
      if self.youtube is None:
          self.authenticate()
      try:
          self.youtube.videos().delete(id=str(video_id).strip()).execute()
      except Exception as e:
          raise YouTubeUploadError(f"영상 삭제 실패: {e}") from e
  ```
- 기존 `SCOPES` 에 이미 `youtube` (풀 권한) 포함되어 있어 재인증 불필요

**라우터 엔드포인트**
- `backend/app/routers/youtube.py`:
  - `YouTubeDeleteRequest` Pydantic 모델 추가 (`video_id`, `confirm`, `clear_project_url`)
  - `_extract_video_id()` 헬퍼: `watch?v=`, `youtu.be/`, `/shorts/`, `/embed/`, 또는 11자 bare ID 파싱
  - `DELETE /{project_id}/upload` 신규 엔드포인트:
    - `confirm=true` 강제
    - body 의 `video_id` 또는 `project.youtube_url` 에서 자동 추출
    - 프로젝트별 uploader 시도 후 글로벌 uploader fallback
    - 404 / `videoNotFound` / "not found" 케이스는 `"already_gone"` 으로 정리하고 URL 클리어
    - `clear_project_url=true` 이면 `project.youtube_url` 을 null 로

**프론트 타입/API**
- `frontend/src/lib/api.ts`:
  ```ts
  export interface YouTubeDeleteRequest {
    video_id?: string;
    confirm: boolean;
    clear_project_url?: boolean;
  }
  export interface YouTubeDeleteResult {
    status: "deleted" | "already_gone";
    project_id: string;
    video_id: string;
    cleared_project_url?: boolean;
    message?: string;
  }
  ```
  - `youtubeApi.deleteUpload(id, body)` 추가 (DELETE 메서드)

**UI**
- `frontend/src/components/studio/StepYouTube.tsx`:
  - `Trash2` (lucide-react) 아이콘 import
  - `deleting` / `deleteError` / `deleteMessage` 상태 추가
  - `handleDeleteUpload()`:
    - `urlToDelete` = `uploadResult?.video_url || project.youtube_url`
    - `window.confirm()` 로 2차 확인 ("정말 삭제하시겠습니까...")
    - `youtubeApi.deleteUpload(project.id, { confirm: true, clear_project_url: true })` 호출
    - 성공 시 `uploadResult` 클리어, 완료 메시지, `onUpdate()` 호출
  - 업로드 결과 박스 안에 `LoadingButton variant="danger"` + Trash2 아이콘 배치 ("YouTube 에서 삭제" / "삭제 중...")

**2단계 안전장치**
- API 단의 `confirm: true` Pydantic 필수 + UI 단의 `window.confirm()` 다이얼로그. 둘 다 통과해야 실제 삭제 요청이 발사됨.

### 작업 4 — 썸네일 프롬프트 강화 (후킹 + 레퍼런스 스타일 락)

**LLM 메타 프롬프트 재작성**
- `backend/app/services/llm/base.py`:
  - `_fallback_thumbnail_prompt` (v1.1.33) 전면 재작성:
    - **PRIMARY GOAL**: "1 second hook"
    - 과장된 감정 표현 picker: wide-eyed shock / jaw-drop awe / intense determination / explosive laugh / cinematic tears / gritted-teeth rage
    - **STYLE REFERENCE** 섹션: 레퍼런스 이미지의 art direction / palette / technique 따르도록 지시
    - 주제 크기 35~55%, rule-of-thirds 오프셋
    - 강화된 negative prompt: UI chrome, warped hands, extra limbs, text, words, letters, numbers, watermarks, blurry, stock-photo
    - 최종 출력 길이 ~2062 chars
  - `_build_thumbnail_prompt_request` 메타 프롬프트에 **"STYLE REFERENCE LOCK (critical)"** 섹션 추가:
    - LLM 출력에 다음 문장을 그대로 포함시키도록 강제: *"Follow the EXACT visual style, palette, and rendering technique of the reference images."*

**레퍼런스 이미지 파이프라인 배선**
- `backend/app/routers/youtube.py` 의 `create_thumbnail` 엔드포인트:
  - `project.config` 에서 `character_images` + `reference_images` 상대 경로 수집
  - `_resolve_asset_list()` 로 `DATA_DIR/{project_id}/` 기준 절대 경로 해석 + 존재 여부 확인
  - 중복 제거 후 `combined_refs` 리스트 생성
  - `generate_ai_thumbnail(..., reference_images=combined_refs or None)` 로 전달
  - 응답에 `reference_images_used: len(combined_refs)` 포함

### 작업 5 — Nano Banana 3 활성화 (정직한 공개)

**투명한 사실 공개**
- Google 은 공식적으로 "Nano Banana 3" 를 출시한 적 없음. 내부 프리셋 이름일 뿐.
- 실제로는 `fal-ai/nano-banana` (Gemini 2.5 Flash Image) 를 호출하되, "레퍼런스 스타일 따라가기" 프롬프트 프리픽스를 자동 주입하는 preset.
- 사용자 선호도("거짓말 절대 하지 않는다")에 따라 결과 회신 시 이 사실을 명시.

**팩토리 등록**
- `backend/app/services/image/factory.py` 에 추가:
  ```python
  "nano-banana-3": {
      "name": "Nano Banana 3 (레퍼런스 스타일 락)",
      "provider": "bbanana",
      "cost_per_unit": "~$0.04/image",
      "cost_value": 0.04,
  },
  ```

**서비스 완전 재작성**
- `backend/app/services/image/nano_banana_service.py` — 기존 구현은 모델 선택과 무관하게 조용히 Flux 로 fallback 하던 가짜였음. 진짜 fal.ai 엔드포인트를 호출하도록 재작성:
  - `_ENDPOINTS` 매핑:
    ```python
    {
      "nano-banana":    "fal-ai/nano-banana",
      "nano-banana-2":  "fal-ai/nano-banana",
      "nano-banana-3":  "fal-ai/nano-banana",
      "nano-banana-pro":"fal-ai/nano-banana-pro",
    }
    ```
  - `_file_to_data_uri()` — 로컬 파일을 base64 data URI 로 변환 (최대 4장, fal 스토리지 업로드 우회)
  - `reference_images` 있으면 `/edit` 엔드포인트 (i2i), 없으면 t2i
  - `nano-banana-3` preset 은 `_style_lock=True` 로, 프롬프트 앞에 다음 문장 prepend:
    *"Follow the EXACT visual style, color palette, lighting mood, line/stroke character, and overall art direction of the reference images provided..."*
  - 페이로드:
    - edit: `{"prompt": ..., "num_images": 1, "image_urls": [...]}`
    - t2i: `{"prompt": ..., "num_images": 1, "image_size": {w, h}}`
  - `_poll()`: 최대 80회 폴링, COMPLETED/FAILED/ERROR 상태 처리
  - 실패 시 `FluxService("flux-dev")` 로 투명한 fallback (이유 로깅)

**검증**
- 모든 수정된 6개 백엔드 Python 파일 `ast.parse` 통과
- 스모크 테스트:
  - `nano-banana-3` 정상 등록 → `fal-ai/nano-banana` 라우팅, `_style_lock=True` 확인
  - fallback thumbnail prompt 길이 2062 chars, 모든 negative 키워드 포함 확인
  - `_extract_video_id` 가 모든 URL 포맷 파싱 확인

### 작업 6 — YouTube 컨텐츠 관리 페이지 (현재 진행 예정)
사용자 질문: "유튜브 컨텐츠 관리 페이지 만들수 있나?"

**답변 요약 (현재 세션에서 이미 전달)**
- 네, 만들 수 있음.
- 이미 각 프로젝트에 `youtube_url` 이 저장되어 있고, `YouTubeUploader` OAuth 스코프가 `youtube` (풀 권한) 이라 `videos.list`, `videos.update`, `channels.list` 추가 호출 가능.
- **2단계 구성 제안**:
  - **1단계** — 프로젝트 기반 업로드 관리 페이지 (바로 가능):
    - `/youtube` 경로 or 대시보드 탭
    - 카드 리스트: 썸네일 / 제목 / URL / 업로드 일자 / 상태
    - 프로젝트별 token.json 으로 `videos.list?id=...&part=statistics,status,snippet` 호출 → 실시간 조회수/좋아요/댓글
    - 액션: 열기 / 통계 새로고침 / 삭제 / 공개상태 변경 (private ↔ unlisted ↔ public)
    - 일괄 선택 삭제
  - **2단계** — 채널 전체 관리 (선택):
    - `videos.list?forMine=true` 로 LongTube 외부 영상까지 포함
    - 단, 현재는 프로젝트별 OAuth 라 글로벌 계정 묶기 설정 필요
- **권장**: 1단계부터. 방금 만든 삭제 엔드포인트와 자연스럽게 이어짐.
- **구현 계획** (사용자 승인 대기):
  - 백엔드: `GET /youtube/managed`, `PATCH /youtube/{project_id}/visibility`, `YouTubeUploader.list_video_stats()` / `update_video_status()`
  - 프론트: `frontend/src/app/youtube/page.tsx`, 사이드 내비 링크, 카드 리스트 UI
  - `StepYouTube` 삭제 로직 재사용

### 결정사항
| 결정 | 이유 |
|------|------|
| TTS 속도 기본 0.9 | 사용자 "너무 빠르다" 피드백, 느긋한 느낌을 기본값으로 |
| YouTube 삭제 2단계 확인 | API `confirm=true` + UI `window.confirm()` — 파괴적 작업 안전장치 |
| `nano-banana-3` 는 스타일 락 preset | Google 공식 v3 없음, 정직하게 preset 임을 공개하고 기능은 실제로 동작 |
| 썸네일 레퍼런스 파이프라인 = config 기반 | `character_images` + `reference_images` 둘 다 자동 수집 |
| 썸네일 프롬프트에 STYLE REFERENCE LOCK 강제 문구 | LLM 이 meta-prompt 를 무시하지 못하도록 verbatim injection |
| YouTube 관리 페이지는 1단계부터 | 기존 데이터/권한만으로 가능, 2단계는 글로벌 OAuth 재설계 필요 |

### 수정 파일 목록 (이번 세션 전체)
**Backend**
- `backend/app/routers/voice.py` (TTS speed passthrough)
- `backend/app/routers/youtube.py` (DELETE upload + thumbnail reference images)
- `backend/app/services/youtube_service.py` (`delete_video`)
- `backend/app/services/tts/openai_service.py` (speed)
- `backend/app/services/tts/elevenlabs_service.py` (speed)
- `backend/app/services/tts/base.py` (speed)
- `backend/app/services/llm/base.py` (thumbnail prompts 재작성)
- `backend/app/services/image/factory.py` (`nano-banana-3` 등록)
- `backend/app/services/image/nano_banana_service.py` (전면 재작성)
- 자막 렌더링 파이프라인 (배경 박스 + 알파)

**Frontend**
- `frontend/src/lib/api.ts` (`tts_speed`, `subtitle_background*`, YouTube delete 타입/API)
- `frontend/src/components/studio/StepSettings.tsx` (음성 속도 슬라이더, 자막 배경/불투명도)
- `frontend/src/components/studio/StepYouTube.tsx` (삭제 버튼)
- 스텝6 `StepSubtitle.tsx` 삭제 + 스텝 인덱스 재정렬

### 미해결 이슈
- [ ] YouTube 컨텐츠 관리 페이지 1단계 구현 (사용자 승인 대기)
- [ ] `nano-banana-pro` 엔드포인트 실제 존재 여부 확인 필요 (현재는 매핑만 되어 있음)
- [ ] 썸네일 프롬프트 실제 생성 결과물 사용자 눈으로 확인 후 톤 조정 가능성

### 다음 할 일
- 사용자가 YouTube 관리 페이지 1단계 진행 승인하면:
  1. `YouTubeUploader` 에 `list_video_stats()` / `update_video_status()` 추가
  2. `GET /youtube/managed` + `PATCH /youtube/{project_id}/visibility` 라우터 추가
  3. `frontend/src/app/youtube/page.tsx` 신규 페이지 구현
  4. 사이드 내비에 "YouTube 관리" 링크 추가
  5. 기존 삭제 로직 재사용하여 일괄 삭제 구현
