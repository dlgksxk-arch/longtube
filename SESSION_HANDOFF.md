# LongTube Current Session Handoff

새 세션은 아래 문서를 순서대로 읽고 실제 파일·DB·API·큐·프로세스를 다시 확인한다.

1. `AGENTS.md`
2. `docs/SESSION_PROTOCOL.md`
3. `SESSION_HANDOFF.md`
4. `docs/handoffs/SESSION_HANDOFF_2026-07-27_OPENAI_FULL_STOP_CH3_EP07_AUDIT.md`
5. `docs/handoffs/SESSION_QA_V3_2026-05-08.md` 전체
6. `CONTEXT.md`

## 현재 원장

`docs/handoffs/SESSION_HANDOFF_2026-07-27_OPENAI_FULL_STOP_CH3_EP07_AUDIT.md`

## 저장 시점 핵심 상태

- LongTube OpenAI API 사용은 사용자 지시로 전면 중지됐다.
- `OPENAI_API_DISABLED=True`; API 상태는 `not_configured`.
- 썸네일은 전부 ComfyUI 로컬 생성으로 강제한다.
- CH1 EP05 task `1411187c`: completed, 본편 `qXIQkPx54r8`.
- CH2 EP06 task `2799640b`: completed, 본편 `DtQ7V3IsKm8`.
- CH3 신규 EP07 task `394cb599`: completed, 본편 `2VxKK2vano8`, Shorts 4건 public/processed/HD/CH3 검증 저장.
- CH3 기존 EP07 task `10883b35`: completed, 본편 `e82J2CUe58E`; 중복 공개 처리는 사용자 지시 없이 변경하지 않는다.
- CH3 EP10 task `6c35cd5d`: cancelled, 60/150 보존, 자동 재개 금지.
- 실행 중/대기/준비 OneClick 작업: 0건.
- Backend PID `279228`.

## 절대 Guard

- 기존 대본이 있으면 재사용한다. 사용자의 명시적 허가 없이 Step 2를 reset하거나 대본을 재생성하지 않는다.
- 다른 LLM으로 임의 전환하지 않는다.
- OpenAI를 자동 또는 묵시적으로 다시 활성화하지 않는다.
- 작업 트리는 기존부터 대규모 dirty 상태다. reset, checkout, clean, 광범위 stage/commit을 금한다.
- 생성물을 직접 수정하지 말고 로직 수정 후 재생성한다.
