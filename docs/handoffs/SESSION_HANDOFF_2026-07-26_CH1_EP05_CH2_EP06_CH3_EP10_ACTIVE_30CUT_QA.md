# 2026-07-26 CH1 EP05 · CH2 EP06 · CH3 EP10 제작/30컷 QA 인수인계

저장 시각: 2026-07-26 18:28 KST

## 새 세션 시작 순서

1. `AGENTS.md`
2. `docs/SESSION_PROTOCOL.md`
3. `SESSION_HANDOFF.md`
4. 이 문서 전체
5. `docs/handoffs/SESSION_QA_V3_2026-05-08.md` 전체
6. `CONTEXT.md`
7. 아래 작업 ID/API/프로세스/이미지 파일을 실제로 재확인

추측으로 승인하거나 재개하지 않는다.

## 사용자 지시

- 채널 1·2·3의 다음 에피소드를 시작하고 이미지 검수부터 렌더·업로드·공개 확인까지 계속 추적한다.
- 세피아 강도는 기존 대비 절반으로 낮춘다.
- 인물이 멀뚱히 서 있는 장면을 반복하지 않는다. 대사에 맞게 배경·액션·클로즈업·유물/증거 컷을 섞는다.
- 각 에피소드는 3~4시간 안에 끝낼 수 있도록 계획적으로 진행한다.
- 생성 결과물을 직접 수정하지 않는다. 문제를 만든 로직을 수정하고 재생성한다.
- GPT 이미지 생성/비전 QA 크레딧과 이미지 모델 변경은 허가 없이 사용하지 않는다.
- 30컷마다 직접 검수·승인한 뒤 다음 30컷으로 진행한다.

## 런타임

- Backend PID: `201348`
- Backend command: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
- 18:25 KST 기준 ComfyUI: running 1 / pending 0
- 당시 running prompt는 별도 해저 케이블 작업이다. 중단하지 않는다.
- 이 문서 저장 시 LongTube 직접 재생성 프로세스는 모두 완료됐다.

작업 조회:

```powershell
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/1411187c
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/2799640b
python .codex_tmp\oneclick_auth_call.py GET /api/oneclick/tasks/6c35cd5d
Invoke-RestMethod http://127.0.0.1:8188/queue
```

승인 후 재개는 반드시 해당 작업 ID의 resume만 사용한다.

```powershell
python .codex_tmp\oneclick_auth_call.py POST /api/oneclick/<TASK_ID>/approve-image-qa
python .codex_tmp\oneclick_auth_call.py POST /api/oneclick/<TASK_ID>/resume
```

`/api/oneclick/queue/run-next`를 기존 작업 재개에 사용하지 않는다.

## CH1 EP05

- Task: `1411187c`
- Project: `V3_CH1_EP5_260726151249b253b0`
- Result: `D:\long_result\CH1\백제사\EP.5.260726151249b253b0`
- 제목: `고대 한류, 칠지도와 해상 무역 EP.05`
- 상태: `paused`
- 생성: 30/150
- 승인 커서: 0
- 절대 승인하지 않은 상태다.

최종 접촉판:

`C:\Users\Ai_M9\Desktop\longtube\.codex_tmp\ch1_ep5_001_030_contact_final.jpg`

확인된 상태:

- 통과 후보: 1–5, 7–12, 16–17, 19–20, 22, 24, 26–28, 30.
- 6: 선체/화물 근접 레퍼런스가 평면 도식으로 남았다. 불합격.
- 13: 신궁 경첩 근접 레퍼런스가 평면 도식으로 남았다. 불합격.
- 14·15·18·21·23·25·29: 철기 표면 레퍼런스는 질감이 개선됐지만 같은 금선 지그재그 구도가 반복된다. 최종 승인 전에 개별 확대 재검수한다.
- 첫 30컷 전체는 아직 승인 금지다.

관련 로그:

```text
.codex_tmp\ch1_ep5_regen_remaining.out.log
.codex_tmp\ch1_ep5_regen_reference_fixes.out.log
.codex_tmp\ch1_ep5_regen_final_macro_fixes.out.log
.codex_tmp\ch1_ep5_regen_final_reference_render.out.log
```

중요 로직 상태:

- 칠지도 단독 형상 및 가지 충돌용 로컬 레퍼런스 경로가 추가됐다.
- 선체 화물/경첩 레퍼런스 denoise를 `0.62`까지 올렸지만 6·13은 여전히 도식적이다.
- 이 둘을 결과물에서 직접 손보지 않는다. 레퍼런스 품질/워크플로를 다시 수정한 뒤 재생성한다.

## CH2 EP06

- Task: `2799640b`
- Project: `V3_CH2_EP6_2607261531487be407`
- Result: `D:\long_result\CH2\Scartography\EP.6.2607261531487be407`
- 제목: `Minoan Collapse and the Late Bronze Age Crisis EP.06`
- 상태: `paused`
- 생성: 90/150
- 승인 커서: 60

완료:

- 1–30 검수·수정·승인 완료.
- 31–60 검수·수정·승인 완료.
- 61–90에서 63, 67, 78–83, 86, 87을 로직 보정 후 재생성했다.
- 63, 78–83, 86, 87 보정본은 확인상 통과.

남은 실패:

- 67은 달리는 동작은 맞지만 다섯 인물이 복제된 얼굴/체형으로 생성됐다.
- 이후 로직은 서로 다른 나이·머리·체형·행동을 가진 정확히 세 명으로 수정했지만, 수정 후 재생성은 아직 하지 않았다.
- 67을 아래 명령으로 재생성하고 직접 확인한 뒤에만 90까지 승인한다.

```powershell
python .codex_tmp\regenerate_one_image_direct.py V3_CH2_EP6_2607261531487be407 67
```

접촉판/로그:

```text
.codex_tmp\ch2_ep6_061_090_contact.jpg
.codex_tmp\ch2_ep6_regen_061_090_fixes.out.log
```

## CH3 EP10

- Task: `6c35cd5d`
- Project: `V3_CH3_EP10_260726161148299480`
- Result: `D:\long_result\CH3\제1장 신들의 시대와 한반도의 그림자\EP.10.260726161148299480`
- 주제: `하늘을 피로 물들인 난동`
- 상태: `paused`
- 생성: 30/150
- 승인 커서: 0

완료:

- 2–30을 새 내레이션 장면 잠금으로 전부 재생성했다.
- 배경·액션·클로즈업·증거 컷 비율은 이전 정적 인물 위주보다 개선됐다.

최종 접촉판:

`C:\Users\Ai_M9\Desktop\longtube\.codex_tmp\ch3_ep10_001_030_contact_final.jpg`

확정 실패/재검수:

- 5: Susanoo가 두 명으로 복제돼 총 5명이 나왔다. 요구는 Susanoo 1명 + 여신 3명이다. 불합격.
- 12: 파괴 장면의 인물들이 줄지어 보인다. 확대 재검수 후 필요 시 액션 구도를 강화한다.
- 15: 대사는 벼의 성장 증거인데 인물 실루엣이 들어갔다. 불합격.
- 25: 분노한 신들이 정적 4인 줄세우기로 보인다. 액션 반응 구도로 재생성 대상.
- 26: 신성 모독으로 확대되는 장면인데 문 위 가짜 문자가 보인다. 불합격.
- 28: 오물 투척 행동 대신 인물이 건물 앞에 서 있다. 불합격.
- 30: 분노한 신들이 정적 줄세우기로 보인다. 불합격.
- 이 실패들을 로직 수정·재생성·개별 확인하기 전에는 승인하지 않는다.

로그:

`C:\Users\Ai_M9\Desktop\longtube\.codex_tmp\ch3_ep10_regen_002_030.out.log`

## 세피아 50% 로직

`backend/app/services/image/comfyui_service.py`의 `HALF_SEPIA_COLOR_BALANCE_PROMPT`를 세피아/담배색 계열 스타일에 적용했다.

현재 생성본은 기존보다 자연색·청색·녹색을 더 유지하지만, 최종 판단은 각 접촉판과 개별 원본으로 한다.

## 주요 변경 파일

```text
backend/app/services/image/comfyui_service.py
backend/app/services/image/prompt_compiler.py
backend/tests/test_image_prompt_compiler.py
backend/tests/test_comfyui_z_image_hand_refine_workflow.py
backend/scripts/generate_shichishito_branch_impact_reference.py
backend/scripts/generate_baekje_boat_cargo_close_reference.py
backend/scripts/generate_baekje_flat_iron_macro_reference.py
backend/scripts/generate_baekje_hinge_close_reference.py
backend/assets/references/shichishito_branch_impact_layout_16x9.png
backend/assets/references/baekje_boat_cargo_close_layout_16x9.png
backend/assets/references/baekje_flat_iron_macro_layout_16x9.png
backend/assets/references/baekje_hinge_close_layout_16x9.png
.codex_tmp/build_contact_sheet.py
```

`prompt_compiler.py`와 테스트 파일들은 이 dirty worktree에서 Git 미추적 상태로 보이므로 정리/삭제/checkout하지 않는다.

## 검증

마지막 확인:

- 관련 targeted unittest 6건 통과.
- `comfyui_service.py`, `prompt_compiler.py`, 신규 레퍼런스 생성 스크립트 `py_compile` 통과.
- 전체 테스트 스위트의 기존 dirty-tree 실패는 이 작업 범위에서 수정하지 않았다.

## 잘못 실행했던 API와 정정

CH2 60컷 승인 후 기존 작업 재개에 `/api/oneclick/queue/run-next?channel=2`를 잘못 호출해 EP07 task `94c807c3`가 생성됐다.

즉시 cancel 후 delete했다.

- 해당 task GET: 404 확인
- EP07 결과 폴더 없음 확인
- 기존 큐 항목 손상 없음 확인

앞으로 기존 작업 재개는 반드시 `/api/oneclick/{task_id}/resume`만 사용한다.

## 다음 세션 실행 순서

1. 세 작업 상태와 ComfyUI 큐를 다시 조회한다.
2. CH1 6·13의 평면 레퍼런스 문제를 로직에서 해결하고 재생성한다.
3. CH1 반복 철기 매크로 컷을 개별 확대 검수하고 첫 30컷 승인 여부를 결정한다.
4. CH2 67을 최신 3인 액션 로직으로 재생성·확인하고 90까지 승인한 뒤 `2799640b`를 resume한다.
5. CH3 확정 실패 5·15·25·26·28·30과 재검수 12를 로직 수정·재생성한다.
6. CH1/CH3 첫 30컷이 전부 통과한 뒤에만 승인·resume한다.
7. 이후 각 채널을 30컷 단위로 150까지 검수한다.
8. 렌더·본편/숏츠 업로드 후 artifact JSON/DB와 실제 YouTube API 또는 oEmbed로 공개·처리·채널 일치를 확인한다.

## Git/보안 경계

- 기존부터 대규모 dirty worktree다.
- `git reset --hard`, `git checkout --`, `git clean`, 광범위 stage/commit 금지.
- 토큰/OAuth/DB/로그/생성물은 커밋하지 않는다.
- 사용자 파일과 무관한 변경을 정리하지 않는다.
