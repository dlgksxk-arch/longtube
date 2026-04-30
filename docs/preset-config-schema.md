# Preset `config` JSON 스키마 (v2.3.1 기준, v2.4.0 대비)

> `channel_presets.config` 는 JSON 컬럼이며, **프런트 /v2/presets/[id] 편집
> 화면이 쓰는 필드 전체** 를 아래에 정리한다. 이 문서는 v2.4.0
> task_runner 가 읽기/쓰기 할 때 참조할 **authoritative source** 이다.
>
> 원칙
> - 미설정 값은 `null` 로 저장한다 (키 삭제가 아니라). 파이프라인 코드는
>   `null`/`""`/`0` 을 동등한 "기본값 사용" 으로 해석할 수 있다.
> - 스키마에 없는 키는 **버리지 않는다** — /v2/presets/[id] 의 PATCH 는
>   `{ ...기존, ...변경 }` 부분 병합이라, v2.4.0 에서 필드가 추가되어도
>   기존 값이 보존된다.
> - 배열은 빈 배열 `[]` 로 저장한다 (미설정 해시 `null` 사용 금지).
> - 채널/폼타입/이름은 `config` 가 아니라 `channel_presets` 테이블 컬럼이
>   담당한다. `config` 는 **콘텐츠/모델/구조/자막/레퍼런스/업로드** 에
>   한정한다.

---

## 최상위 구조

```jsonc
{
  "content":    { /* §1 */ },
  "models":     { /* §2 */ },
  "structure":  { /* §3 */ },
  "subtitles":  { /* §4 */ },
  "references": { /* §5 */ },
  "upload":     { /* §6 */ },
  "automation": { /* §7 — v2.3.2 실구현 */ },
  "audio":      { /* §8 — v2.3.2 실구현 */ },

  // v1 호환. 과거 StepYouTube 버그로 topic 컬럼이 오염됐던 잔재를
  // 여기로 이관한 필드. 새로 쓰지 않음 (파이프라인 읽기만).
  "youtube_description": "string (legacy, v1.1.29 마이그레이션)"
}
```

최상위에 임의 키가 추가되어도 **무시되며 보존된다**. 예: 사용자가 손으로
`notes`, `draft_memo` 같은 키를 넣어도 프런트가 지우지 않는다.

---

## §1 `content` — 콘텐츠 방향 (섹션 2)

```jsonc
{
  "topic": "string",             // 딸깍폼이면 큐에서 주입 — 편집 화면에서는 read-only
  "tone": "string",              // 자유 입력. 예: "차분한 다큐멘터리"
  "style": "string",             // 자유 입력. 예: "역사 / 미스터리"
  "target_audience": "string",   // 자유 입력. 예: "40대 남성, 역사 관심"
  "signature_phrase": "string"   // 인트로/아웃트로 고정 문구
}
```

- 전부 `string`. 빈 문자열 `""` 는 "미설정" 과 동치.
- 파이프라인은 `tone` + `style` 을 시스템 프롬프트에 합류시킨다
  (현재 v1 `pipeline_tasks` 는 v1 전용 필드를 쓰지만, v2 task_runner 는
  이 경로를 써야 한다).

---

## §2 `models` — AI 모델 (섹션 3)

```jsonc
{
  "script":    { "model_id": "string" },                     // 대본 LLM
  "image":     { "model_id": "string" },                     // 이미지 모델 (본 컷용)
  "tts":       { "model_id": "string", "voice_id": "string" }, // ElevenLabs 등
  "thumbnail": { "model_id": "nano-banana" },                // 고정 — 변경 UI 없음
  "bgm":       { "model_id": "elevenlabs-music" }            // 고정 — 변경 UI 없음
}
```

- 각 하위 객체 안에 `model_id` 는 `backend/app/services/{image,tts,llm}/factory.py`
  에 등록된 id 문자열이어야 한다. 알 수 없는 id 는 서비스 레벨에서
  폴백(`openai-image-1` 등) — 이 스키마에서 검증 안 함.
- `thumbnail` / `bgm` 은 현재 UI 편집 불가(§10.3 명시). task_runner 는
  이 값이 비어있으면 위 고정값으로 해석.
- `script.temperature`, `script.top_p`, `script.max_tokens` 등 고급 옵션은
  **v2.4.0 에서 확장 예정** (§10.3 에 "고급 옵션 펼치기"). 현재는 저장 안 함.

---

## §3 `structure` — 영상 구조 (섹션 4)

```jsonc
{
  "target_duration_min_sec": 600,    // number | null — 전체 목표 길이 하한 (초)
  "target_duration_max_sec": 1200,   // number | null — 전체 목표 길이 상한 (초)
  "opening_sec": 30,                 // number | null — 오프닝 구간
  "closing_sec": 20,                 // number | null — 클로징 구간
  "segment_count_min": 6,            // number | null — 세그먼트 최소 개수
  "segment_count_max": 10            // number | null — 세그먼트 최대 개수
}
```

- 전부 `number | null`. **빈 입력 → `null`**.
- 프런트는 내부 state 에서 문자열("")로 들고 있다가 저장 시 `inputToNum()`
  으로 변환한다.
- 파이프라인 권고: `null` 일 때 하드코딩된 기본값(현 v1 pipeline 의
  기본 15 분) 을 쓴다.
- `target_duration_min_sec <= target_duration_max_sec` 검증은 서버/프런트
  **아직 없음**. 잘못된 조합은 파이프라인에서 클램프한다고 가정.

---

## §4 `subtitles` — 자막 (섹션 5)

```jsonc
{
  "enabled": true,                   // 자막 생성/출력 자체 on/off
  "burn_in": false,                  // true → 영상에 구워넣기, false → .srt 파일만
  "language": "ko",                  // "ko" | "en" | "ja"
  "position": "bottom",              // "top" | "middle" | "bottom"
  "max_chars_per_line": 28           // number | null
}
```

- `enabled=false` 면 나머지 필드 의미 없음. 프런트 UI 는 dim 처리한다.
- `language` 는 화면 고정 3종. `"ja"` 지원은 아직 파이프라인 실측 없음(스키마만).
- `burn_in=true` 일 때만 `max_chars_per_line` 이 실제 레이아웃에 영향.
- §10.3 에 명시된 **폰트/크기/색/스트로크/미리보기** 는 v2.4.0 에서 확장.

---

## §5 `references` — 레퍼런스 (섹션 6)

```jsonc
{
  "mode": "style",                   // "off" | "style" | "composition"
  "strength": 0.65,                  // number | null, 0.0 ~ 1.0 권장
  "image_urls": [                    // string[] — 프런트는 textarea 한 줄 1 URL
    "https://example.com/ref1.jpg",
    "https://example.com/ref2.jpg"
  ]
}
```

- `mode="off"` 이면 `strength`, `image_urls` 는 의미 없음 — 파이프라인은
  레퍼런스 로직 자체를 타지 않는다.
- `strength` 범위 검증은 UI 에서 **안 함** (자유 입력). 0~1 밖 값은
  이미지 서비스에서 클램프한다고 가정.
- `image_urls` 는 **빈 배열 `[]` 로 저장** — `null` 로 저장 금지.
- §10.3 은 "이미지 URL 10장, 업로드 20장, 유튜브 캡션 자동 추출" 을
  명시하지만 현재 UI 는 URL 리스트만 지원. 업로드/캡션 추출은 v2.4.0.

---

## §6 `upload` — 업로드 템플릿 (섹션 7)

```jsonc
{
  "title_template": "{채널이름} · {주제} ({길이})",
  "description_template": "{요약}\n\n#{채널이름}",
  "playlist_id": "PL...",            // 빈 문자열이면 재생목록에 추가 안 함
  "visibility": "public",            // "public" | "unlisted" | "private"
  "scheduled": false                 // 예약 업로드 — 실 구현은 /v2/queue.scheduled_at
}
```

- 치환 토큰: `{주제}`, `{요약}`, `{채널이름}`, `{길이}`, `{날짜}`.
  v1 `youtube/studio` 의 템플릿 엔진과 **호환** 유지.
- `visibility` 가 위 3값이 아니면 프런트가 `"public"` 으로 강제.
- `scheduled=true` 라도 실제 예약 시각은 `preset_queue_items.scheduled_at`
  이 소유한다 (이 필드는 단순 "예약 업로드 기능을 쓸지" 플래그).

---

## §7 `automation` — 자동화 (섹션 8, v2.3.2 실구현)

§10.3 정의에 맞춰 UI 구현 완료.

```jsonc
{
  "retry_on_fail": 1,                // number | null — 실패 재시도 횟수
  "pause_during_studio": true,       // 항상 true — 프런트 save() 에서 강제
  "quality_gates": {
    "min_duration_sec": 300,         // number | null
    "max_duration_sec": 1800,        // number | null
    "min_loudness_lufs": -20,        // number | null (음수 LUFS)
    "max_loudness_lufs": -10,        // number | null (음수 LUFS)
    "min_resolution": "1080p"        // "720p" | "1080p" | "1440p" | "2160p"
  }
}
```

- `pause_during_studio` 는 **토글 노출 금지** — 프런트 UI 는 읽기만
  보여주고, save() 는 무조건 `true` 로 덮어쓴다. 서버 측 Pydantic 모델이
  붙을 때에도 동일 규칙.
- `retry_on_fail` 은 각 스텝(대본/이미지/영상/TTS) 단위로 적용한다.
  `null` 또는 `0` 이면 재시도 없음.
- 품질 게이트 값을 벗어나도 **업로드는 막지 않는다** — 경고 배지만 띄운다.
- `min_resolution` 화이트리스트 밖 값은 프런트 load() 에서 `"1080p"` 로
  강제.

---

## §8 `audio` — 음향/BGM (섹션 9, v2.3.2 실구현)

```jsonc
{
  "bgm_enabled": true,               // boolean — 기본 true (§10.3)
  "bgm_style_prompt": "calm historical documentary, orchestral, no vocals",
  "bgm_volume_db": -18,              // number | null, 권장 -30 ~ -6
  "ducking_strength": "normal",      // "low" | "normal" | "strong"
  "fade_in_sec": 2,                  // number | null
  "fade_out_sec": 2                  // number | null
}
```

- 단위는 **dB** (모든 볼륨), **초** (모든 페이드). 다른 단위 금지.
- `bgm_enabled=false` 면 나머지 필드는 저장은 되지만 파이프라인이 무시.
- `ducking_strength` 화이트리스트 밖 값은 프런트 load() 에서 `"normal"`
  로 강제.
- **§10.3 의 `sfx_pack_urls` 는 v2.3.2 UI 에서 아직 제공 안 함** —
  파일 업로드 UX 가 필요해 v2.4.0 로 미룸. 이 키를 저장하는 코드는
  아직 없다(문서에만 존재).

---

## 레거시 / 이관 필드

### `youtube_description`

- **v1.1.29 마이그레이션 결과물**. 과거 `project.topic` 컬럼이 오염되어
  (수천자 + bullet) 이를 자동 복구하면서 실제 설명문을 이 키로 이관했다.
  `backend/app/main.py` startup 코드가 1회성으로 처리.
- v2 에서 **새로 쓰지 않는다**. `upload.description_template` 이 정식.
- 읽기 시에만 v2.4.0 task_runner 에서 참고할 수 있다(기존 프리셋 호환).

---

## 검증 규칙 (UI 기준)

| 필드 | 검증 | 검증 주체 |
|---|---|---|
| 모든 `number` 필드 | 공백 → `null`, 비숫자 → `null` | `inputToNum()` (프런트) |
| `upload.visibility` | 화이트리스트 밖 → `"public"` | 프런트 load() / 섹션 컴포넌트 |
| `subtitles.language` | `ko|en|ja` 밖 → `"ko"` | 프런트 load() |
| `subtitles.position` | `top|middle|bottom` 밖 → `"bottom"` | 프런트 load() |
| `references.mode` | `off|style|composition` 밖 → `"off"` | 프런트 load() |
| `references.image_urls` | 공백/빈줄 제거 후 저장 | save() |
| `automation.pause_during_studio` | 항상 `true` 강제 | save() |
| `automation.quality_gates.min_resolution` | `720p|1080p|1440p|2160p` 밖 → `"1080p"` | 프런트 load() |
| `audio.ducking_strength` | `low|normal|strong` 밖 → `"normal"` | 프런트 load() |
| 채널당 딸깍폼 중복 | partial unique index | DB (alembic `channel_presets` 스키마) |

서버측에는 현재 JSON Schema 검증 **없음**. PATCH 본문이 오면 그대로
덮어쓴다. v2.4.0 에서 Pydantic 모델로 이 문서를 구체화할 것을 권장.

---

## 변경 이력

- **v2.3.2 (2026-04-21)** — 섹션 8 (자동화) + 섹션 9 (음향) 실구현
  반영. `automation.pause_during_studio`, `quality_gates.*`,
  `audio.bgm_*`, `audio.ducking_strength`, `audio.fade_*` 필드 정식화.
  `sfx_pack_urls` 는 여전히 v2.4.0 대기.
- **v2.3.1 (2026-04-21)** — 최초 작성. 섹션 1~7 (식별 제외한 content/
  models/structure/subtitles/references/upload) 실제 구현 필드 반영.
  섹션 8/9 는 §10.3 정의만 명시, 실 구현 대기.
- (**식별** 섹션은 `config` 가 아니라 `channel_presets` 테이블 컬럼이
  담당하므로 이 문서에는 포함하지 않는다.)

---

## 참고

- 편집 화면 실구현: `frontend/src/app/v2/presets/[id]/page.tsx`
- 저장 엔드포인트: `PATCH /api/v2/presets/{id}` (body: `{ name?, config? }`)
- 응답 모델: `backend/app/routers/v2/presets.py::PresetDetailOut`
- 기획서: `docs/v2-plan.md` §10.3
