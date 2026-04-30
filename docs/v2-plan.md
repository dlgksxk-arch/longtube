# LongTube v2 기획 문서

- 작성일: 2026-04-21
- 대상 버전: v2.1.0 / v2.2.0 / v2.3.0 (병렬 경로 방식)
- 기준 버전: v2.0.74
- 원칙: 기존 코드·데이터·NAS 자산 건드리지 않음. `/v2/*` 경로와 새 테이블로 병렬 구축. 작동 확인 후 구 경로 제거.

---

## 0. 최상위 원칙 (절대 지킴)

1. **데이터 손실 금지**: 기존 테이블 `projects`, `cuts`, `scheduled_episodes`, `api_logs` 와 NAS 자산 경로는 v2.x 동안 절대 수정하지 않는다. 읽기 전용만 허용.
2. **마이그레이션 없음**: 스키마 변환/데이터 이동 없음. 새 테이블 5개 추가로만 처리.
3. **병렬 경로**: 프론트는 `/v2/*`, 백엔드 라우터는 `/api/v2/*`. 구 경로(`/oneclick`, `/youtube`, `/settings`)는 그대로 둔다.
4. **프리셋이 단일 진실원**: 스튜디오(테스트폼)과 딸깍폼은 동일한 프리셋 모델을 공유한다. 딸깍폼은 채널당 1개 고정, 테스트폼은 N개.
5. **존댓말 문서 원칙 유지**: 코드 주석/UI 문구에 반말·농담 금지.
6. **모바일·상용화는 v3.0으로 유예**: v2.x에서는 PC 기반으로만 구현한다. 보안은 v2.x에서도 최소한(암호화+검증)은 지킨다.

---

## 1. 용어 정의

| 용어 | 뜻 |
|---|---|
| 채널(CH1~CH4) | 유튜브 채널 4개 슬롯. 고정. |
| 딸깍폼 | 채널별 1개 고정 프리셋. 큐·스케줄·자동 업로드에 쓰인다. |
| 테스트폼 | 스튜디오에서 실험용으로 만드는 프리셋. N개 가능. 채널 재바인딩으로 딸깍폼으로 승격 가능. |
| 프리셋(Preset) | 한 편 만드는 모든 설정(주제 방향, 모델, 길이, 자막, 레퍼런스, 업로드 템플릿, 자동화, 음향)을 담는 단위. |
| 큐(Queue) | 딸깍폼 실행 대기열. 프리셋+주제로 구성된 줄들. |
| 태스크(Task) | 큐 한 줄이 실제 실행될 때 생기는 실행 기록. |
| EP.XX | 채널별 딸깍폼 제작분의 일련번호. |
| 명명 규칙 | `{채널}-{폼타입}-{이름}` 예: `CH1-딸깍폼-10분역공`, `CH2-테스트폼-스와핑테스트` |

---

## 2. 병렬 경로 구조

### 2.1 프론트 라우트

```
/v2/                        → v2 대시보드
/v2/presets                 → 프리셋 목록(통합 스튜디오+딸깍)
/v2/presets/[id]            → 프리셋 편집(9 섹션)
/v2/queue                   → 딸깍 큐
/v2/live                    → 실시간 현황
/v2/schedule                → 스케줄 (읽기 전용 달력)
/v2/youtube/channels        → 채널별 관리 허브
/v2/youtube/videos          → 내 영상 목록
/v2/youtube/playlists       → 재생목록
/v2/youtube/comments        → 댓글
/v2/settings                → 설정 허브
/v2/settings/api            → API 키/잔액
/v2/settings/storage        → 저장소 경로
```

구 경로(`/oneclick/*`, `/youtube/*`, `/settings`)는 그대로 유지. v2 동작 확인 후 삭제.

### 2.2 백엔드 라우터

```
/api/v2/presets
/api/v2/queue
/api/v2/tasks
/api/v2/events
/api/v2/storage
/api/v2/keys
```

구 라우터(`app/routers/*.py`)는 v2.x 중에는 남겨둔다.

### 2.3 구 경로 제거 시점

- v2.3.0 출시 + 1주일 운영 관찰 → v2.4.0에서 구 경로 frontend 제거 → v2.5.0에서 backend 라우터 제거.
- 각 단계마다 `backend/app/main.py`의 include_router 주석 처리만으로 롤백 가능하도록 한다.

---

## 3. 데이터베이스 스키마 (새 테이블만 추가)

### 3.1 `channel_presets`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| channel_id | INTEGER | 1~4 (딸깍폼은 채널에 고정 바인딩) |
| form_type | TEXT | '딸깍폼' / '테스트폼' |
| name | TEXT | 사용자 지정 이름 (예: `10분역공`) |
| full_name | TEXT | 자동 조합: `{CH}-{폼타입}-{name}` |
| config | JSON (MutableDict) | 9개 섹션 전체 설정 |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |
| is_modified | BOOLEAN | 편집 페이지 modified 뱃지 판정용 |

제약: (`channel_id`, `form_type='딸깍폼'`)는 UNIQUE. 테스트폼은 같은 채널에 N개 가능.

### 3.2 `preset_queue_items`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| preset_id | INTEGER FK channel_presets.id | |
| channel_id | INTEGER | 1~4 |
| episode_no | INTEGER | EP.XX 자동 할당 (딸깍폼만) |
| topic_raw | TEXT | 사용자 자유 입력 원문 (멀티라인) |
| topic_polished | TEXT | 의미 보존 다듬기 결과 (첫 줄만) |
| status | TEXT | 'pending' / 'scheduled' / 'running' / 'done' / 'failed' |
| scheduled_at | TIMESTAMP NULL | 스케줄 배정 시각 |
| created_at | TIMESTAMP | |

### 3.3 `preset_tasks`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| queue_item_id | INTEGER FK | |
| preset_id | INTEGER FK | |
| channel_id | INTEGER | |
| form_type | TEXT | EP.XX 카운트용. '딸깍폼'만 카운트. |
| episode_no | INTEGER NULL | 딸깍폼만 사용 |
| status | TEXT | 단계별 진행 상태 |
| step_states | JSON (MutableDict) | 대본/이미지/보이스/자막/영상/썸네일/업로드 각 단계 상태 |
| started_at | TIMESTAMP | |
| ended_at | TIMESTAMP NULL | |
| estimated_sec | INTEGER | 예산 시간 |
| actual_sec | INTEGER NULL | 완료 시간 |
| output_dir | TEXT | `{DATA_DIR}/tasks/{id}/` |

### 3.4 `preset_usage_records`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| preset_id | INTEGER FK | |
| task_id | INTEGER FK | |
| provider | TEXT | anthropic / openai / elevenlabs / fal / xai / gemini |
| cost_usd | REAL | |
| tokens_in | INTEGER NULL | |
| tokens_out | INTEGER NULL | |
| units | REAL NULL | 음성/이미지/음악 단가 환산치 |
| recorded_at | TIMESTAMP | |

프리셋 카드에 "총 비용 / 총 제작 건수 / 예정 제작 건수" 집계용.

### 3.5 `events`

| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | INTEGER PK | |
| scope | TEXT | 'task' / 'queue' / 'system' |
| scope_id | INTEGER NULL | |
| level | TEXT | 'info' / 'warn' / 'error' |
| code | TEXT | 이벤트 코드 (예: `TASK_STEP_STARTED`) |
| message | TEXT | |
| payload | JSON NULL | |
| created_at | TIMESTAMP | |

실시간 현황 페이지, 실패 분석용.

### 3.6 기존 테이블 처리

- `projects`, `cuts`, `scheduled_episodes`, `api_logs`, `api_balances`, `api_keys` : 건드리지 않음.
- `api_keys` 기존 저장분이 평문이면 v2 부팅 시 1회 한정 자동 암호화(값 보존). `api_keys_backup_<timestamp>.sqlite3` 로 선백업 후 변환.

---

## 4. 내부 폴더 구조 (파일 저장 위치)

### 4.1 기본 루트

- 기본값: `longtube/data/outputs/` (상대 경로)
- 사용자 변경 가능: `/v2/settings/storage`에서 지정
- 기존 하드코딩 경로 `C:\Users\Jevis\Desktop\longtube_net\projects` 는 `legacy/` 로만 읽어들이고 새 파일은 저장하지 않음.

### 4.2 하위 구조

```
{DATA_DIR}/
  legacy/          # 기존 프로젝트(읽기 전용)
  presets/
    {preset_id}/
      bgm_cache/   # BGM 시드 음원 캐시 (프리셋 단위)
      reference/   # 레퍼런스 이미지·자막 원본
  tasks/
    {task_id}/
      script/
      audio/
      images/
      subtitle/
      video/
      thumbnail/
      upload/
```

### 4.3 경로 검증 규칙

저장소 경로 변경 시:
1. 경로 유효성(존재/쓰기 권한) 검증.
2. 실패 시 저장 버튼 비활성.
3. 성공 시 백엔드 config에 반영 후 재시작 없이 적용.
4. 기존 `tasks/*` 파일은 이동하지 않음. 과거 경로 참조는 계속 유효.

### 4.4 저장소 UI 표시

- 현재 사용량 GB 단위 표시.
- 루트 경로 input + 찾아보기.
- 하위 디렉터리(`legacy`, `presets`, `tasks`) 각각 용량 표기.

---

## 5. 보안 (v2.x 범위)

### 5.1 API 키 암호화

- 방식: AES-GCM.
- 키 소스: OS 환경 변수 `LONGTUBE_KEY_SECRET` (없으면 앱이 `data/.key` 생성하고 0600 권한).
- 부팅 1회: 기존 평문 `api_keys` 레코드를 자동 감지해서 암호화 저장. 원본 값은 보존됨(복호화 결과는 동일).
- 백업: `api_keys_backup_<UNIXTS>.sqlite3` 자동 생성 후 변환.

### 5.2 Pydantic 재검증

- 모든 `/api/v2/*` 라우터의 입력은 Pydantic 모델로 재검증.
- 프론트 신뢰 금지. 서버 쪽에서도 길이·형식·허용값을 다시 검사한다.

### 5.3 .env 보호

- `.env`, `data/.key`, `token.json`, `client_secret.json` 는 `.gitignore`에 명시(이미 있으면 점검만).
- v3.0 상용화 단계에서 인증/멀티테넌시/과금 보안 레이어를 추가한다.

### 5.4 v3.0으로 유예된 보안

- 사용자 인증(로그인/OAuth), RBAC, 조직 단위 격리, 로그 감사, 키 로테이션 UI, 모바일 보안.

---

## 6. 공통 디자인 시스템

### 6.1 전역 스타일 조정

- 폰트 크기: Tailwind 기준 한 단계 상향(base → +1 tier 전역 적용). 시안성 우선.
- 여백: 과도한 여백 축소.
  - `p-8` → `p-5`
  - `space-y-6` → `space-y-4`
  - `gap-5` → `gap-3`
- 좌측 사이드바: 240px 폭 유지.
- 모바일 대응: v3.0으로 유예. v2.x는 1280px 기준 PC만 안정적으로 보이면 됨.

### 6.2 공통 컴포넌트

다음을 `frontend/src/components/common/` 에 공통화:

| 컴포넌트 | 용도 |
|---|---|
| `StatusDot` | 연결/상태 점 표시 (녹색/노랑/빨강/회색). |
| `ConfirmDialog` | `confirm()` 대체. 확인/취소 모달. |
| `Toast` | `alert()` 대체. 4초 자동 사라짐. |
| `EmptyState` | 비었을 때 안내. |
| `LoadingState` | 로딩 스피너 + 안내문. |
| `ErrorState` | 에러 메시지 + 재시도 버튼. |

### 6.3 채널 색상 헬퍼

`frontend/src/lib/channelColor.ts`:
- CH1: blue-400
- CH2: green-400
- CH3: amber-400
- CH4: pink-400

인라인 삼항 연산자 금지. 반드시 헬퍼 사용.

---

## 7. 좌측 사이드바 통합 구조

딸깍/유튜브/설정이 별도 사이드바를 쓰던 구조를 하나로 통합.

### 7.1 4 섹션 아코디언

```
┌─ 프리셋
│   - 프리셋 목록
│   - (CH1~CH4 딸깍폼 바로가기)
├─ 딸깍
│   - 제작 큐
│   - 실시간 현황
│   - 스케줄
│   - 완성작 관리
├─ 유튜브
│   - 채널 허브
│   - 내 영상
│   - 재생목록
│   - 댓글
└─ 설정
    - API 키/잔액
    - 저장소
    - (이후 확장)
```

하단의 "자동 실행 상태" 위젯은 이 통합 사이드바 하단으로 이동.

### 7.2 기존 사이드바 처리

- `/v2/layout.tsx`에 통합 사이드바 신규 구현.
- 구 `/oneclick/layout.tsx`는 v2.x 동안 유지.

---

## 8. 대시보드 재설계 (`/v2`)

### 8.1 상단

- 채널 4개 카드: 딸깍폼 이름 / 마지막 완료 EP / 다음 예정 EP / 오늘 상태 점.
- 실행 중 태스크 요약(가로 스트립): `CH{n} EP.{xx} {단계} {경과/예산}`.

### 8.2 중단

- 예산 vs 소비(이번 달 USD).
- 7일 제작 건수 바 차트(채널별 색).

### 8.3 하단

- 최근 이벤트 10건(events 테이블).

---

## 9. 프리셋 목록 (`/v2/presets`)

### 9.1 항상 표시되는 4 CH 슬롯

- CH1~CH4 딸깍폼 카드는 **비어 있어도 항상 표시**.
- 비어있을 때: 카드 안에 "초기화" 버튼 노출.

### 9.2 초기화 버튼 모달 (3-way)

- 옵션 A: 빈 프리셋으로 생성.
- 옵션 B: 다른 CH 딸깍폼에서 복사.
- 옵션 C: 테스트폼에서 복사.
- 실행 직전 "진짜 실행할까요?" 확인(ConfirmDialog).

### 9.3 테스트폼 목록

- 4 CH 카드 아래, 별도 섹션에 그리드.
- "테스트폼 새로 만들기" 버튼.
- 테스트폼 카드 우상단에 "딸깍폼으로 승격" 버튼 → 채널 선택 → 기존 딸깍폼을 테스트폼으로 강등하며 자리 교체(채널 **재바인딩만** 변경. 내용은 그대로).

### 9.4 카드 표시 정보

- 이름 (`{CH}-{폼타입}-{name}`)
- 영상 길이 대표값
- 총 비용(USD)
- 총 제작 건수
- 예정 제작 건수(큐 pending)
- 수정일
- modified 뱃지(편집 후 미저장)

### 9.5 정렬 드롭다운

- 수정일 / 이름 / 원본 순서.

---

## 10. 프리셋 편집 (`/v2/presets/[id]`)

### 10.1 레이아웃

- 좌측 탭: 9개 섹션.
- 우측: 선택된 섹션 폼.
- 상단 고정 바: 프리셋 풀네임, 채널 배지, 폼 타입 배지, modified 뱃지, 저장 버튼.

### 10.2 공통 규칙

1. **이름 자동 조합 강제**: `full_name = {채널}-{폼타입}-{name}`. `name`만 수정 가능.
2. **라벨 분기**: 
   - 딸깍폼 → 주제 영역은 "큐에서 주입" 설명 + 읽기 전용.
   - 테스트폼 → 주제 필드 편집 가능.
3. **modified 뱃지**: 편집 후 저장 전까지 상단에 표시.
4. **프롬프트 역할 분리**:
   - 시스템 프롬프트(기술·모델별) → 설정 > 시스템 프롬프트에서 관리(프리셋에 안 들어감).
   - 프리셋 프롬프트(내용·분위기) → 프리셋 안에 저장.

### 10.3 9개 섹션

#### 섹션 1 — 식별
- 이름(사용자 부분)
- 풀네임 자동 표시(read-only)
- 채널 배지(딸깍폼은 잠금)
- 폼 타입 배지
- 설명 메모

#### 섹션 2 — 내용 방향
- 주제 필드 (딸깍폼은 read-only 안내)
- 톤/분위기 드롭다운 + 자유 입력 혼용
- 스타일(역사/미스터리/인물/…) 드롭다운 + 자유 입력
- 시청자 타깃 메모
- 시그니처 문구 (인트로/아웃트로용)

#### 섹션 3 — AI 모델
- 대본 모델 (프로바이더 + 모델명)
- 이미지 모델 (fal.ai 계열)
- TTS 모델 (ElevenLabs)
- 썸네일 모델: **Nano Banana 고정** (Gemini 2.5 Flash Image)
- BGM 모델: **ElevenLabs Music 고정**
- 각 모델당 "고급 옵션 펼치기"(temperature, top_p, max_tokens 등).
- 시스템 프롬프트는 모델별로 **4개 따로** 관리(대본/이미지/TTS/썸네일). 시스템 프롬프트는 전역 설정에 저장, 프리셋에는 참조 키만.

#### 섹션 4 — 영상 구조
- 목표 길이(분)
- 인트로 구성 템플릿 드롭다운 + **사용자 정의**
- 본문 구성 템플릿 드롭다운 + **사용자 정의**
- 아웃트로 템플릿 드롭다운 + **사용자 정의**
- 중간 인터미션: "N분마다" 와 "총 N회" **둘 다 지원**(선택).

#### 섹션 5 — 자막
- 폰트, 크기, 색, 스트로크 색/두께, 그림자 on/off
- 위치, 여백
- **실시간 미리보기**(왼쪽 프리뷰, 오른쪽 조작).
- 줄 바꿈 규칙(글자수 기반 / 자연어 기반)

#### 섹션 6 — 레퍼런스
- 레퍼런스 이미지 URL 최대 **10장**, 업로드 최대 **20장**.
- 유튜브 URL 첨부 시 자막 자동 추출(caption) → 프리셋 reference 탭에 저장.
- **"다른 프리셋에서 가져오기"** 버튼(비어있을 때).

#### 섹션 7 — 업로드 템플릿
- 제목 템플릿: `{주제}`, `{요약}`, `{채널이름}`, `{길이}`, `{날짜}` placeholder 지원.
- 설명 템플릿: 동일 placeholder + 자유 입력.
- 태그: **대본 생성 단계에서 자동 추출**(`generate_script_with_meta`가 title/tags/summary 동시 산출).
- 재생목록: 드롭다운 + 신규 생성.
- 공개 설정: public / unlisted / private.
- 예약 업로드: on/off(스케줄 페이지 규칙을 따름).

#### 섹션 8 — 자동화
- 외부 알림: **v2.x에서는 없음**. (v3.0 검토)
- 실패 시 재시도 횟수(기본 1회).
- 딸깍 일시 정지: **강제 on** (토글 없음). 스튜디오(테스트폼) 실행 중에는 딸깍 태스크가 반드시 멈춘다.
- 품질 경고 기본 설정(길이/음량/해상도 임계치).

#### 섹션 9 — 음향
- BGM on/off (기본 on)
- BGM 스타일 프롬프트(한 줄, 한국어·영어 혼용 가능) — 예: "calm historical documentary, orchestral, no vocals"
- BGM 볼륨 dB 단위(-30 ~ -6, 기본 -18)
- 사이드체인 덕킹 강도(낮음/보통/강함, 기본 보통)
- 페이드 인/아웃 초(기본 각 2초)
- SFX 팩: **기본 팩 없음**. 프리셋 단위로 파일 업로드 가능(선택).
- 단위는 전부 dB.

---

## 11. 딸깍 큐 (`/v2/queue`)

### 11.1 입력 방식 (확정: Option A)

- **별도 모달**을 띄워 한 건씩 추가.
- 모달 필드:
  - 채널 드롭다운 (CH1~CH4).
  - EP.XX (자동 할당, **read-only**).
  - 주제(멀티라인 textarea, 자유 입력).
- 멀티라인 자유 입력 예시:
  ```
  Ep.01 주제 - 단군, 진짜 있었을까 — 한반도 첫 나라의 수수께끼
  첫대사 - 우리가 반만년 역사라고 말할 때, 그 절반은 이 한 사람에게 달려있습니다
  핵심소재 - 단군신화 3층위 / 환웅 하강 / 웅녀 / 청동기 부족국가 / 삼국유사 기록
  단군은 개인이 아니라 왕의 칭호였을 가능성
  ```
- 검증: **없음**. AI를 신뢰한다.
- 첫 줄(제목 부분)은 "의미 보존 다듬기"만 허용(과도한 요약/재해석 금지).

### 11.2 EP.XX 자동 번호 규칙

- **채널별 독립 카운터**. CH1 EP.07과 CH2 EP.01이 공존한다.
- 계산식:
  ```sql
  episode_no = (
    SELECT COUNT(*) FROM preset_tasks
    WHERE channel_id = :channel AND form_type = '딸깍폼'
  ) + 1
  ```
- **딸깍폼만 카운트**. 테스트폼은 EP 없음.
- 큐 추가 시점에 값이 확정되고 이후 변하지 않음(큐 순서 바뀌어도 번호는 그대로).
- 수동 덮어쓰기 불가.

### 11.3 큐 목록 화면

- 채널 탭 4개 + 전체.
- 각 행: `EP.XX · 주제 한 줄 · 생성일 · 상태 배지 · 편집/삭제`.
- 드래그 정렬 가능(순서만 바꿈, EP.XX는 고정).

### 11.4 실행 트리거

- 기본: 스케줄 규칙에 따라 자동 실행.
- 수동: 행 우측 "지금 실행".

---

## 12. 실시간 현황 (`/v2/live`)

### 12.1 중복 방지

- 채널 × EP 기준으로 중복 카드 렌더링 제거.
- 같은 태스크의 서로 다른 단계는 카드 내부에서 순차 표시.

### 12.2 로그 카드

- 완료 시간 + 예산 시간을 **항상** 표기. 비용은 **표시 제외**.
- 지연 임계치 기본 **120초**(기존 90초에서 상향). 초과 시 경고 배지.
- 지연 판정 규칙: API 연결 테스트 OK 상태에서는 "API 연결 이상 없음"을 함께 표기(헷갈리지 않게).

### 12.3 이벤트 피드

- `events` 테이블을 꼬리 따라가는 SSE 스트림.
- 레벨(info/warn/error)별 색 필터.

---

## 13. 스케줄 (`/v2/schedule`) — Option B 확정

### 13.1 원칙

- **읽기 전용 달력**. 편집은 큐 쪽에서만.
- 기존에 상단에 있던 `channel_times` 편집기는 **제거**(프리셋 섹션 4로 이전).

### 13.2 표시 규칙

- 월간 그리드 + 다가오는 목록 병행.
- 각 셀: `CH{n} EP.{xx}` + 업로드 예정 시간.
- 채널 색상은 `channelColor` 헬퍼로 통일.
- 과거 달도 **조회 가능**.
- 셀 내부는 **단순 표시**(아이콘/배경 최소화).

### 13.3 스케줄 규칙 안내

- 페이지 상단에 한 줄 설명: "채널별 독립, 하루 1개 소비. 큐가 비면 건너뜀."
- 배분 로직은 기존 로직 계승:
  ```
  items_by_channel[ch] = pending queue of that channel
  each day: consume one per channel if schedule active
  ```

---

## 14. 유튜브 관리 (`/v2/youtube/*`)

### 14.1 채널 허브 (`/v2/youtube/channels`)

- CH1~CH4 카드 + "채널 추가"(v3.0 전까지는 4개 고정).
- 각 카드에서 최근 업로드 5개, 댓글 미응답 수, 재생목록 수 요약.

### 14.2 내 영상 (`/v2/youtube/videos`)

- 채널 드롭다운 선택 → 해당 채널 영상만 표시.
- confirm/alert 대신 `ConfirmDialog` / `Toast`.

### 14.3 재생목록 (`/v2/youtube/playlists`)

- grid-cols-2 카드 유지.
- 생성/삭제 confirm은 `ConfirmDialog`로 교체.
- 알림은 `Toast`로 교체.

### 14.4 댓글 (`/v2/youtube/comments`)

- 레이아웃 유지(좌측 260px 영상 목록, 우측 댓글 스레드).
- 채널 필터 추가(허브에서 진입 시 자동 적용).

### 14.5 직접 업로드 페이지 제거

- 기존 `/youtube/upload`는 v2에서 **없앰**. 업로드는 파이프라인 마지막 단계에서만 발생.

---

## 15. 설정 (`/v2/settings/*`)

### 15.1 API 설정 (`/v2/settings/api`) — 3영역 카드

프로바이더별로 카드 하나. 카드 내부 3영역:

1. **상태 영역** (상단)
   - StatusDot (연결/만료/실패)
   - 테스트 핑 버튼
   - 마지막 확인 시각

2. **키 영역** (중단)
   - 키 입력(마스킹 표시 + 편집 시 전체 공개)
   - 저장 버튼 → AES-GCM 암호화 저장
   - 메모 필드: **제거**(요청)

3. **잔액 영역** (하단)
   - 현재 잔액 USD 표시(자동 조회 + 수동 기록값 중 최신)
   - **"충전했어요" 모달**을 통해서만 잔액 수기 입력. 평상시에는 read-only.
   - 통화 단위: USD 고정.

### 15.2 공통 헤더

- "프로바이더 사용처 범례": 각 프로바이더가 어느 단계에 쓰이는지 한 줄 설명.
- Anthropic=대본, OpenAI=보조, ElevenLabs=TTS+BGM, fal.ai=이미지, xAI=보조, Gemini=썸네일.

### 15.3 저장소 (`/v2/settings/storage`)

- 루트 경로 input + 찾아보기.
- 현재 사용량 GB 단위.
- 하위 디렉터리 각각 용량 표시.
- 경로 유효성 검증 필수. 실패 시 저장 불가.
- 기존 파일 이동 **없음**.

---

## 16. BGM 파이프라인

### 16.1 목표

- ElevenLabs Music로 30초 시드 생성 → ffmpeg로 반복·덕킹·페이드 처리해 영상 전체에 깔기.

### 16.2 시드 생성 규칙

- API: ElevenLabs Music.
- 길이: **30초** 고정.
- 가사: **없음**. 프롬프트 말미에 "seamlessly loopable, no vocals" 자동 부착.
- 시드 프롬프트: 프리셋 섹션 9 "BGM 스타일 프롬프트" 값을 그대로 사용.
- **프리셋 단위 캐시**: `{DATA_DIR}/presets/{preset_id}/bgm_cache/{hash}.mp3`. 프롬프트 해시가 같으면 재사용.

### 16.3 ffmpeg 체인 (고정)

순서:
1. `trim` — 시드 앞뒤 정리(무음 제거).
2. `acrossfade` — 앞꼬리/뒤머리 자연 교차(2초).
3. `stream_loop` — 영상 길이에 맞게 반복.
4. `afade` — 시작/끝 페이드(기본 각 2초, 프리셋에서 조정 가능).
5. `sidechaincompress` — 내레이션 들어올 때 덕킹(프리셋 강도 설정).
6. `limiter` — 피크 컷.

### 16.4 볼륨

- 기본 -18 dB. 프리셋 섹션 9에서 -30 ~ -6 범위 조정.
- 단위: dB.

---

## 17. 썸네일 파이프라인

### 17.1 단계 1 — 배경 생성 (Nano Banana)

- 모델: Gemini 2.5 Flash Image.
- 입력: 레퍼런스 이미지 + 프리셋 톤 + 대본 제목/요약.
- 목표: 예쁘고 강렬하고 훅 빡 오는 한 장.
- 해상도: 1280x720.

### 17.2 단계 2 — EP 오버레이 (Pillow 후처리)

- **AI에 지시하지 않는다**(100% 신뢰 못함). Pillow로 직접 얹는다.
- 위치: **좌측 상단**.
- 여백: 48px (기본값, 조정 가능).
- 폰트: **Noto Sans KR Bold**.
- 크기: 이미지 높이의 약 **8%**.
- 색: 흰색 `#FFFFFF` + 검정 스트로크 `#000000` 두께 **4px**.
- 포맷 드롭다운(프리셋 섹션 7에서 선택):
  - `Ep.07`
  - `EP.07`
  - `#07`
  - `01화`
  - `제1화`

### 17.3 산출물

- `{DATA_DIR}/tasks/{task_id}/thumbnail/final.jpg`.
- 대본 단계에서 함께 생성된 title/tags/summary가 업로드 메타와 결합된다.

---

## 18. 실행 파이프라인 (태스크 진행 순서)

1. 대본 생성 (`generate_script_with_meta`): 본문 + title + tags + summary 한 번에.
2. 보이스 합성 (ElevenLabs TTS).
3. 이미지 생성 (fal.ai 기반).
4. 자막 렌더.
5. 영상 합성 + BGM 믹스(16장 체인).
6. 썸네일 생성 + EP 오버레이.
7. 메타 조립(템플릿 placeholder 치환).
8. 업로드(`youtube_service`) — 예약/즉시 분기.
9. `preset_usage_records` 에 각 API 비용 적재.
10. `events` 스트림에 단계별 기록.

모든 중간 산출물은 `{DATA_DIR}/tasks/{task_id}/` 하위에 저장.

---

## 19. 시스템 프롬프트 관리

- 시스템 프롬프트는 **모델별 4개**(대본/이미지/TTS/썸네일).
- 저장 위치: 전역 설정(별도 테이블 없이 `config.py` + DB `system_prompts` 신설 없음, 대신 `settings` 신규 JSON 테이블 권장).
- 프리셋은 시스템 프롬프트 **키**만 참조. 내용은 프리셋 편집 화면에 표시되지 않음.
- 프리셋 자체 프롬프트(섹션 2 톤/분위기, 섹션 9 BGM 스타일)는 프리셋 안에 저장.

---

## 20. 릴리즈 청크

### 20.1 v2.1.0 — 기반 (선작업)

- 5개 신규 DB 테이블 추가(`channel_presets`, `preset_queue_items`, `preset_tasks`, `preset_usage_records`, `events`).
- API 키 AES-GCM 암호화 전환(백업 + 자동 변환).
- `/v2/*` 레이아웃·라우팅 스캐폴딩.
- 통합 좌측 사이드바(4 섹션 아코디언) 구현.
- 공통 컴포넌트 세트(`StatusDot`, `ConfirmDialog`, `Toast`, `EmptyState`, `LoadingState`, `ErrorState`).
- `channelColor` 헬퍼.
- 폰트/여백 전역 재조정.

### 20.2 v2.2.0 — 핵심 흐름

- 프리셋 목록(4 CH 슬롯 + 테스트폼 목록 + 정렬 드롭다운 + 초기화 3-way 모달).
- 프리셋 편집 9 섹션(좌측 탭 + modified 뱃지 + 이름 자동 조합 + 프롬프트 역할 분리).
- 큐 별도 모달(Option A 자유 입력 + EP.XX 자동 할당).
- 스케줄 읽기 전용 달력(Option B).
- 대본 단계 확장(`generate_script_with_meta` — title/tags/summary 동시 산출).
- 자동 업로드 플로우(유튜브 예약/즉시 분기).

### 20.3 v2.3.0 — 품질 마감

- BGM 파이프라인(ElevenLabs Music 30초 + ffmpeg 체인).
- 썸네일 파이프라인(Nano Banana + Pillow EP 오버레이).
- 새 실시간 현황 페이지(120초 임계치, 비용 숨김, 완료/예산 시간, 중복 제거).
- 새 유튜브 관리 섹션(채널 허브/영상/재생목록/댓글 — confirm·alert 대체).
- API 3영역 카드 + 테스트 핑 + "충전했어요" 모달.
- 저장소 설정 UI + 경로 검증.
- `events` 테이블 기반 이벤트 스트림(SSE).
- legacy 임포트(읽기 전용 관찰 카드).

### 20.4 v2.4.0 — 구 프론트 정리

- `/oneclick/*`, `/youtube/*`, `/settings` 프론트 라우트 제거.

### 20.5 v2.5.0 — 구 백엔드 정리

- 구 라우터 `app/routers/*` 중 v2로 대체된 것 제거.
- 구 테이블에 대한 마이그레이션 없음(그냥 읽지 않음).

### 20.6 v3.0 (유예)

- 모바일 라우트(`/m/live`, `/m/schedule`, `/m/add`).
- 모바일에서는 현황/스케줄/딸깍 주제 추가 3개만 제공.
- 상용화: 사용자 인증, 멀티테넌시, 과금, 키 로테이션, 감사 로그, 모바일 보안.

---

## 21. 구현 가드레일

1. v2 작업 중에는 구 라우터·구 라우트·구 테이블에 **write**하지 않는다. 읽기만 허용.
2. 저장소 변경은 새 `tasks/*`에만 반영. 과거 파일은 이동 금지.
3. 모든 `/api/v2/*`는 Pydantic 검증 필수.
4. UI에서 confirm/alert 직접 호출 금지. 공통 모달·토스트만 사용.
5. 프리셋 명명은 `{CH}-{폼타입}-{name}` 강제. 직접 입력 금지.
6. EP.XX는 큐 추가 시점에 확정되고 이후 변경 금지. 수동 덮어쓰기 불가.
7. 딸깍폼만 EP 카운트. 테스트폼은 EP 없음.
8. 테스트폼 실행 중에는 딸깍 실행 강제 정지. 토글 없음.
9. 채널 색상은 `channelColor` 헬퍼만 사용.
10. BGM 시드 캐시는 프리셋 단위, 프롬프트 해시 키로 재사용.
11. 썸네일 EP 번호는 Pillow 후처리로만 올린다. AI 지시 금지.

---

## 22. 유예·미결정 항목

- 외부 알림(슬랙/디스코드/이메일): v2.x에서는 **없음**, v3.0 재검토.
- SFX 기본 팩: **없음**, 프리셋별 업로드만 허용.
- 테스트폼 → 딸깍폼 승격 시 과거 EP 카운트 보정: 현행 규칙은 "과거 태스크 기준 COUNT+1"이므로 자연 반영됨. 별도 보정 불필요.
- 다국어: v2.x는 한국어 UI 유지.

---

## 23. 검증 계획 (릴리즈별)

### v2.1.0
- 5개 테이블 생성 확인.
- 기존 `api_keys` 자동 암호화 후 복호화 결과가 원본과 동일한지 확인.
- `/v2/` 진입 시 통합 사이드바 렌더 확인.
- 공통 컴포넌트 시각 확인.

### v2.2.0
- 프리셋 목록 4 CH 슬롯 항상 표시 확인.
- 테스트폼 → 딸깍폼 승격 시 채널 바인딩만 바뀌는지 확인(내용 그대로).
- 큐 추가 시 채널별 EP.XX가 독립 카운터로 할당되는지 확인.
- 스케줄 과거 달 조회 확인.

### v2.3.0
- BGM 캐시 재사용 확인(동일 프롬프트 → 동일 파일).
- 썸네일 EP 오버레이 위치/폰트/색 확인(5가지 포맷).
- API 테스트 핑 버튼 동작 확인.
- 저장소 경로 변경 후 기존 파일 접근 유지 확인.

---

## 24. 참고 — 기존 코드와의 대응표

| v1 경로 | v2 대응 | 비고 |
|---|---|---|
| `/oneclick/layout.tsx` | `/v2/layout.tsx` | 통합 사이드바 |
| `/oneclick/schedule/page.tsx` | `/v2/schedule/page.tsx` | Option B 읽기 전용 |
| `/settings/page.tsx` | `/v2/settings/api/page.tsx` | 3영역 카드 |
| `/youtube/playlists/page.tsx` | `/v2/youtube/playlists/page.tsx` | 모달·토스트 교체 |
| `/youtube/comments/page.tsx` | `/v2/youtube/comments/page.tsx` | 레이아웃 유지 |
| `/youtube/upload/page.tsx` | **제거** | 업로드는 파이프라인 전담 |
| `routers/oneclick.py` | `routers/v2/queue.py` + `v2/tasks.py` | |
| `routers/youtube*.py` | `routers/v2/youtube.py` | |
| `routers/api_keys.py` | `routers/v2/keys.py` | 암호화 포함 |
| `services/oneclick_service.py` | `services/v2/task_runner.py` | 파이프라인 재구성 |
| `services/thumbnail_service.py` | `services/v2/thumbnail_service.py` | Pillow 오버레이 추가 |
| (신규) | `services/v2/bgm_service.py` | ElevenLabs Music + ffmpeg 체인 |

---

## 25. 최종 체크리스트 (착수 전)

- [ ] 본 문서 검토 및 확정.
- [ ] `api_keys` 백업 경로 확인.
- [ ] `.env`, `data/.key` `.gitignore` 포함 여부 점검.
- [ ] `DATA_DIR` 기본값을 상대 경로로 교체할 준비(`config.py`).
- [ ] `/v2` 레이아웃 스캐폴드 PR 분리 기준 합의.
- [ ] legacy 임포트가 기존 파일을 **읽기만** 하는지 코드 리뷰 규칙 공유.

---

이 문서는 디스커션 원본이다. 구현 과정에서 변경 발생 시 본 파일을 최우선으로 갱신하고, `HANDOFF.md` / `CHANGELOG.md` / `ARCHITECTURE.md` 에 반영한다.
