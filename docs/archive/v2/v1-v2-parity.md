# LongTube v1 → v2 기능 패리티 대장

> 작성: v2.4.0 야간 작업 (2026-04-21)
> 목적: **"v1 에는 있고 v2 에는 없는" 기능이 남았는지** 를 한눈에 보기
> 위함. v2-plan §24 "기존 코드와의 대응표" 가 *파일 이동 맵* 에 가까운
> 반면, 이 문서는 *엔드포인트 / 사용자 기능 단위* 에서 한 건 한 건
> 대조한다.
>
> 원칙:
>
> - v1 의 "이미 삭제된 기능" 은 재이식하지 않는다 (사용자 원칙: 이미
>   빠진 건 그대로 둔다).
> - v1 의 기능은 **입력/설정 방법이 바뀌어도 무방**하지만 결과물이 v1
>   과 동등해야 한다. 예: 인터루드는 v1 의 초-단위 숫자 입력을 업로드
>   파일 3 슬롯으로 교체했다 — 결과(영상 앞/사이/뒤 붙이기)는 동일.
> - 이 문서는 **코드 실측** 기반. 2026-04-21 시점 `backend/app/routers/*`
>   모든 `@router.*` 데코레이터를 나열한 뒤, v2 대응 / 상태 / 마감 마일
>   스톤 을 기입한다.
>
> 범례: ✅ 완료 · 🚧 부분 · ❌ 미 · ⛔ 폐기 확정 (v1 에서 빠진 기능, 재이식 안 함)

---

## 1. 프로젝트 수명주기 — v1 `routers/projects.py`

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `GET /api/projects` | `GET /api/v2/presets` + `GET /api/v2/tasks` | ✅ (프리셋 목록 + 작업 목록 분리) |
| `POST /api/projects` | `POST /api/v2/presets` + `POST /api/v2/queue` | ✅ (프리셋 생성 + 큐 추가 분리) |
| `GET /api/projects/{id}` | `GET /api/v2/tasks/{id}` + `GET /api/v2/presets/{id}` | ✅ |
| `PUT /api/projects/{id}` | `PATCH /api/v2/presets/{id}` | ✅ |
| `DELETE /api/projects/{id}` | `DELETE /api/v2/queue/{id}` (대기중) · tasks 삭제는 v2.5.0 | 🚧 (실행중/완료 태스크 삭제 없음) |
| `GET /api/projects/_diagnose/by-title` | ❌ | ⛔ (디버그용, 필요 없음) |
| `GET /api/projects/{id}/estimate` | ❌ | ❌ (예산 추정은 `/v2/usage/summary` 실측으로 대체) |

## 2. 파이프라인 실행 제어 — v1 `routers/pipeline.py` + `tasks.py`

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `POST /pipeline/{id}/run-all` | 큐 실행은 딸깍폼 자동 — 수동 실행은 `/v2/live` 트리거 | 🚧 (단계별 수동 트리거 미구현) |
| `POST /pipeline/{id}/step/{step}` | ❌ | ❌ (단계별 트리거 — v2.5.0 검토) |
| `POST /pipeline/{id}/pause` · `resume` · `cancel` | `/v2/live` 비상정지 | 🚧 (프로젝트 단위 일시정지 없음, 전체 정지만) |
| `POST /pipeline/{id}/pause-step/{step}` · `resume-step` | ❌ | ❌ |
| `POST /pipeline/{id}/reset-step/{step}` | ❌ | ❌ (단계별 리셋은 v2.5.0) |
| `POST /pipeline/{id}/resume-from/{step}` | ❌ | ❌ |
| `GET /pipeline/{id}/status` | `GET /api/v2/tasks/{id}` | ✅ |
| `GET /tasks/{id}/{step}` · `POST .../cancel` | ❌ | ❌ (단계 취소는 v2.5.0) |

## 3. 대본·샷·보이스·영상·자막 파이프라인

| 영역 | v1 엔드포인트 수 | v2 대응 | 상태 |
|---|---|---|---|
| **script** (`routers/script.py`) | 8 (generate / generate-async / cuts CRUD / clear) | 파이프라인 내부에서 자동 호출 — 외부 노출 없음 | ✅ (자동 실행 스펙) |
| **image** (`routers/image.py`) | 13 (generate / async / per-cut / reference·character 업로드 등) | 파이프라인 자동 + `/v2/presets/[id]` 에서 레퍼런스 업로드 예정 | 🚧 (레퍼런스 업로드 UI 가 v2 에 아직 없음) |
| **voice** (`routers/voice.py`) | 6 | 자동 실행 | ✅ |
| **video** (`routers/video.py`) | 7 (ComfyUI 진단 포함) | 자동 실행 + `/v2/settings/api` 의 ping | ✅ |
| **subtitle** (`routers/subtitle.py`) | 3 | 자동 실행 (config 로 on/off) | ✅ |
| **downloads** (`routers/downloads.py`) | 3 | ❌ (다운로드는 v1 UI 전용) | 🚧 (v2 다운로드 링크 미노출 — v2.5.0) |

## 4. 인터루드 (오프닝/간지/엔딩) — **v2.4.0 에서 통합**

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `GET /api/interlude/{project_id}` | `GET /api/v2/presets/{preset_id}/interlude` | ✅ |
| `PUT /api/interlude/{project_id}/config` | `PUT /api/v2/presets/{preset_id}/interlude/config` | ✅ |
| `POST /api/interlude/{project_id}/upload/{kind}` | `POST /api/v2/presets/{preset_id}/interlude/upload/{kind}` | ✅ |
| `DELETE /api/interlude/{project_id}/{kind}` | `DELETE /api/v2/presets/{preset_id}/interlude/{kind}` | ✅ |
| `POST /api/interlude/{project_id}/compose` (cut 기반 재조립) | ❌ | 🚧 (파이프라인이 대본 cuts 를 건드리지 않는 구조라 필요 없음. v2 에서는 `build_interlude_sequence` 를 렌더 단계에서 직접 호출) |

서비스 중복 제거: `backend/app/services/interlude_service.py` 로 추출.
v1/v2 라우터가 모두 이 모듈을 호출한다. 저장 경로만 다르다 —
v1 = `DATA_DIR/{project_id}/interlude/`, v2 = `DATA_DIR/presets/{preset_id}/interlude/`.

## 5. 원클릭 (딸깍) — v1 `routers/oneclick.py`

v1 "딸깍" 은 *한 영상 단위 실행 트리거* 였지만 v2 "딸깍" 은 *프리셋 +
주제 큐 = 자동 반복* 으로 의미가 확장됐다. 따라서 엔드포인트 매핑이
1:1 이 아니다.

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `POST /oneclick/prepare` | `POST /api/v2/queue` | ✅ (큐 추가 = v2 의 prepare) |
| `POST /oneclick/{id}/start` · `resume` · `cancel` | `/v2/live` 트리거 + tasks | 🚧 (개별 태스크 resume 수동 트리거 없음) |
| `POST /oneclick/emergency-stop` | `/v2/live` 비상정지 | ✅ |
| `GET /oneclick/running` | `GET /api/v2/tasks?status=running` | ✅ |
| `GET /oneclick/tasks` · `GET /tasks/{id}` | `GET /api/v2/tasks` · `/{id}` | ✅ |
| `DELETE /oneclick/tasks/{id}` | ❌ | ❌ (태스크 삭제 — v2.5.0) |
| `POST /oneclick/{id}/clear-step/{step}` · `reset` · `regenerate-thumbnail` | ❌ | 🚧 (후처리 재생성 UI 미노출) |
| `GET /oneclick/library/stats` | `/v2` 대시보드 KPI | ✅ |
| `GET·PUT /oneclick/queue` · `run-next` | `/api/v2/queue` CRUD | ✅ |
| `POST /oneclick/recover` · `prune` | ❌ | ⛔ (v2 는 태스크 레코드가 고아가 되지 않는 설계) |
| `POST /oneclick/tasks/bulk-delete` | ❌ | ❌ (벌크 삭제 — v2.5.0) |

## 6. 스케줄 — v1 `routers/schedule.py`

v1 스케줄은 *쓰기* 가능했지만 v2 는 *읽기 전용 캘린더* 로 확정됨 (v2-plan §13 Option B).

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `GET /schedule` · `status` · `{id}` | `/v2/schedule` 페이지 (tasks + queue.scheduled_at 읽어 달력 렌더) | ✅ |
| `POST /schedule` · `PUT /schedule/{id}` · `DELETE` · `bulk` | `PATCH /api/v2/queue/{id}/schedule` (예약 설정/해제) | ✅ (입력 형태만 다름 — 큐 항목에 scheduled_at 을 패치) |
| `POST /schedule/{id}/run` · `reset` | ❌ | ⛔ (스케줄 수동 실행/리셋은 제거 확정) |

## 7. 유튜브 — v1 `routers/youtube.py` + `youtube_studio.py`

v2 는 `/v2/youtube/*` 4 페이지 스켈레톤 + v1 딥링크로 구성돼 있고,
실제 백엔드 엔드포인트는 아직 v1 을 경유한다 (v2-plan §14 는 v2.4.0~
로 잡혀있었으나 실제 구현은 v2.5.0 로 연기).

| v1 엔드포인트 | v2 대응 | 상태 |
|---|---|---|
| `GET /youtube/auth/channel/{ch}/status·info` · `reset` | `/v2/youtube/channels` 에서 실 OAuth 상태 노출 | ✅ (읽기는 v2, 인증 액션 자체는 v1 엔드포인트 호출) |
| `POST /youtube/auth/channel/{ch}` | v1 엔드포인트 그대로 사용 (재이식 안 함) | 🚧 |
| `GET /youtube/videos·playlists·comments` (`youtube_studio.py`) | `/v2/youtube/videos·playlists·comments` 는 현재 v1 UI 딥링크 | 🚧 (v2.5.0 에서 v2 백엔드로 교체 예정) |
| `POST /youtube/{project_id}/thumbnail` · `/upload` · `/tags/recommend` · `/metadata/recommend` | 파이프라인 자동 실행 | ✅ |
| 전 `youtube_studio.py` (비디오 · 재생목록 · 댓글 CRUD) | ❌ | 🚧 (v2.5.0 — v1 라우터를 그대로 사용) |

## 8. API 키 · 잔액 · 상태 · 모델

| v1 | v2 | 상태 |
|---|---|---|
| `routers/api_keys.py` | `routers/v2/keys.py` | ✅ (AES-GCM 암호화 전환 포함) |
| `routers/api_balances.py` | `routers/v2/keys.py` (`/balance`) | ✅ |
| `routers/api_status.py` (ffmpeg/fal/status) | `routers/v2/keys.py` (`/ping/{provider}`) | ✅ |
| `routers/models.py` (llm/image/video/tts 모델 카탈로그) | v2 프리셋 편집 §3 AI 모델 드롭다운이 직접 참조 | ✅ |

## 9. 저장소

| v1 | v2 | 상태 |
|---|---|---|
| (없음 — v1 에는 저장소 뷰가 없었음) | `GET /api/v2/storage/info` + `/v2/settings/storage` | ✅ (v2 신규) |

## 10. 이벤트 스트림

| v1 | v2 | 상태 |
|---|---|---|
| (v1 에는 이벤트 테이블 없음) | `GET /api/v2/events` + `/v2` 대시보드 피드 | ✅ (v2 신규) |

## 11. 사용량 · 예산

| v1 | v2 | 상태 |
|---|---|---|
| (v1 은 잔액 표시만) | `GET /api/v2/usage/summary` · `/by-preset` + `/v2` 대시보드 예산 타일 | ✅ (v2 신규) |

---

## 남은 v2 갭 (v2.5.0 큰 덩어리)

순위 없이 나열 (사용자 원칙: 우선순위 없이 앞에서부터 하나씩):

1. **v1 프런트 제거** (v2-plan §20.4 에서 v2.4.0 범위로 잡혔지만 실제로는
   v1 백엔드 엔드포인트가 아직 유튜브·다운로드·단계별 트리거에서 쓰이고
   있어 제거 불가 — v2.5.0 과 한 덩어리로 처리).
2. **단계별 실행 트리거 / 일시정지 / 리셋** — v1 의 `pipeline.py` 세분화
   제어를 `/v2/live` 에 녹여야 함. 현재 v2 는 전체 비상정지만 있음.
3. **태스크 삭제 / 벌크 삭제** — v1 `oneclick` 에 있던 정리 액션.
4. **레퍼런스·캐릭터·로고 업로드 UI** — 백엔드는 v1 엔드포인트 존재,
   v2 `/v2/presets/[id]` 섹션 6 (레퍼런스) 는 아직 플레이스홀더.
5. **썸네일 재생성 트리거** — v1 `regenerate-thumbnail` 대응 UI 없음.
6. **유튜브 스튜디오 (비디오·재생목록·댓글 CRUD)** — `/v2/youtube/*` 는
   현재 v1 딥링크. 백엔드 직접 호출로 교체.
7. **다운로드** — `/v2` 에 zip/단일 에셋 다운로드 경로 노출.
8. **SFX 팩 업로드** (v2-plan §22 유예 항목, v2.4.0 대기 표시됐으나 실제
   로는 v3.0 으로 넘어갈 가능성 — 사용자 결정 필요).

---

## 공식 폐기 확정 (재이식 안 함)

- `schedule/{id}/run` · `reset` (스케줄에서 직접 실행 / 리셋)
- `oneclick/recover` · `prune` (고아 레코드 복구 — v2 설계로 필요 없음)
- `projects/_diagnose/*` (디버그용)
- `projects/{id}/estimate` (사전 추정 — v2 는 실측 `usage` 테이블 기반)

---

작성 근거: 2026-04-21 `grep -rn "^@router\." backend/app/routers/` 실행
결과 172 개 엔드포인트 전수 분류. 갱신 필요 시 이 명령으로 다시 집계
하면 된다.
