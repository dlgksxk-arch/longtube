# LongTube 새 세션 인수인계 - 2026-04-27 22:10 KST

## 사용자 최신 지시
- 새 세션으로 이동 예정.
- 현재까지의 진행상황을 최대한 세세하게 기록하라고 요청함.
- "이 PC 리소스는 모두 사용해도 되"라고 명시함.
- 기존 큰 목표는 `MYLORA` LoRA 학습 후 CH2 5편 + CH1 5편을 이미지 기반 정적 렌더로 만들고 YouTube 비공개 업로드하는 것.
- 영상 AI 생성은 하지 말 것. FF/움직임 효과도 쓰지 말라는 취지였음. 현재 템플릿은 `ffmpeg-static`으로 정적 이미지 렌더 설정.

## 현재 서버/네트워크 상태
- 이 PC IP: `192.168.0.221`
- 다른 PC로 보이는 클라이언트: `192.168.0.45`
- 현재 다른 PC `192.168.0.45`에서 이 PC의 3000/8000/8188 포트에 실제 Established 연결이 있음.
- 즉 "다른 PC에서 서버로 연결 안 됨"은 포트가 안 열린 문제라기보다, 페이지 내부 API 주소/브라우저 상태/프론트 런타임 문제일 가능성이 큼.
- 이 PC에서 직접 LAN 주소 테스트 결과 모두 200 응답:
  - `http://192.168.0.221:3000/`
  - `http://192.168.0.221:8000/api/health`
  - `http://192.168.0.221:8188/system_stats`
- 서버 바인딩:
  - 프론트: `0.0.0.0:3000`
  - 백엔드: `0.0.0.0:8000`
  - ComfyUI: `0.0.0.0:8188`
- Windows 네트워크 프로필은 `Public`으로 확인됨.
- 방화벽 규칙 추가를 시도했으나 관리자 권한이 없어 `Access is denied` 발생.
- 그런데 실제 외부 연결이 이미 Established이므로, 현 시점에서는 방화벽이 완전 차단 중인 상태는 아님.

## 현재 실행 중 프로세스
- ComfyUI:
  - PID `15928`, `python.exe`
  - 포트 `8188`
  - 실행 옵션에 `--listen 0.0.0.0 --port 8188`
- 백엔드:
  - PID `16380`, `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload ...`
  - 리로더/래퍼 cmd도 있음.
  - `/api/health` 응답: `{"status":"ok","version":"1.2.29","comfyui_base_url":"http://127.0.0.1:8188"}`
- 프론트:
  - PID `10080`, `node ... next dev --hostname 0.0.0.0 --port 3000`
- 자동 실행 도우미:
  - PID `14980`, `python C:\Users\Ai_M9\Desktop\mylora_training\overnight_run_ch1_ch2.py`
  - 이 도우미가 CH2/CH1 큐를 순차 실행 중임.
  - 새 세션에서 중복 실행하지 말 것. 필요하면 이 PID를 중단하고 직접 제어.

## MYLORA 학습 상태
- 최종 학습 완료됨.
- 최종 LoRA:
  - `C:\Users\Ai_M9\Desktop\mylora_training\output\MYLORA.safetensors`
  - `C:\models\loras\MYLORA.safetensors`
  - 파일 크기: `170,547,524 bytes`
  - 최종 수정: `2026-04-27 21:38:35`
- 중간 산출물:
  - `MYLORA-step00001000.safetensors`
  - `MYLORA-step00002000.safetensors`
  - `MYLORA-step00003000.safetensors`
  - 이어학습 중간 `MYLORA-step00000500.safetensors`
- 학습 경위:
  - 최초 4000 step 계획.
  - 밤사이 PC 절전/중단 영향으로 3149/4000 근처에서 멈춤.
  - 최종 파일이 없어서 `MYLORA-step00003000.safetensors`에서 1000 step 이어학습 진행.
  - 처음 이어학습 스크립트는 `triton not found` 경고가 PowerShell에서 치명 오류처럼 처리되어 멈췄음.
  - `run_mylora_continue_from_3000_direct.ps1`에서 `$ErrorActionPreference='Continue'`로 고쳐 정상 완료.
- 학습 데이터:
  - 원본 생성 폴더: `C:\Users\Ai_M9\Desktop\train`
  - 학습 데이터 폴더: `C:\Users\Ai_M9\Desktop\mylora_training\dataset\4_MYLORA`
  - 총 250 PNG + 250 TXT, 학습 쪽 캡션은 `MYLORA, ` 프리픽스 적용.

## MYLORA 앱/ComfyUI 연결 상태
- 신규 이미지 모델 ID:
  - `comfyui-dreamshaper-xl-mylora`
- 신규 워크플로:
  - `C:\Users\Ai_M9\Desktop\longtube\backend\workflows\comfyui\dreamshaper_xl_mylora_text2img.json`
- 워크플로는:
  - 체크포인트 `dreamshaperXL_sfwLightningDPMSDE.safetensors`
  - LoRA `MYLORA.safetensors`
  - SDXL 계열, 1344x768 강제 쪽 기존 LongTube 흐름과 유사
- 코드 연결:
  - `backend/app/services/image/comfyui_service.py`
    - 모델 ID -> 워크플로 매핑 추가
    - 표시명 추가
    - SDXL 패밀리 포함
    - MYLORA 트리거가 프롬프트에 없으면 `MYLORA, `를 앞에 붙이도록 추가
  - `backend/app/services/image/factory.py`
    - `"comfyui-dreamshaper-xl-mylora"` 레지스트리 추가
- 문법 체크:
  - `python -m py_compile` 통과.

## 템플릿/큐 설정 상태
- CH1 템플릿:
  - ID `f60d6b0b`
  - 제목 `딸깍폼-10분역공`
  - 현재 설정:
    - `image_model`: `comfyui-dreamshaper-xl-mylora`
    - `thumbnail_model`: `comfyui-dreamshaper-xl-mylora`
    - `video_model`: `ffmpeg-static`
    - `video_target_selection`: `all`
    - `youtube_privacy`: `private`
    - `youtube_channel`: `1`
    - `channel`: `1`
- CH2 템플릿:
  - ID `e6619f7e`
  - 제목 `딸깍폼-제리스아케오`
  - 현재 설정:
    - `image_model`: `comfyui-dreamshaper-xl-mylora`
    - `thumbnail_model`: `comfyui-dreamshaper-xl-mylora`
    - `video_model`: `ffmpeg-static`
    - `video_target_selection`: `all`
    - `youtube_privacy`: `private`
    - `youtube_channel`: `2`
    - `channel`: `2`
- 큐 파일:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.json`
- 큐 백업:
  - `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.before_ch1_ch2_5_mylora_static.json`
  - `C:\Users\Ai_M9\Desktop\longsult\_system\oneclick_queue.before_mylora_run.json`
- 현재 `last_run_dates`:
  - CH1: `2026-04-27`
  - CH2: `2026-04-27`
  - CH3: `2026-04-25`
  - CH4: `null`
- 현재 `channel_times`:
  - CH1 `01:00`
  - CH2 `03:00`
  - CH3 `06:00`
  - CH4 `null`
- 자동 스케줄러가 다시 물지 않도록 CH1/CH2 last_run_dates는 오늘 날짜로 잠겨 있음.

## 현재 큐 앞부분
- CH1 큐 count: 63
- CH1 앞 5개는 모두 `f60d6b0b` 템플릿 지정됨:
  - EP3 `단군은 사람이었을까, 칭호였을까`
  - EP4 `고조선 마지막 왕은 어디로 사라졌나`
  - EP5 `한반도가 정말 식민지였던 적이 있을까`
  - EP6 `부여에서 쫓겨난 한 청년, 그 이름은`
  - EP7 `주몽의 아들들은 왜 뿔뿔이 흩어졌을까`
- CH2 큐 count: 58
- CH2 현재 앞부분:
  - EP3 `Post-it Notes: The Glue That Failed and Changed Offices Forever`, template `e6619f7e`
  - EP4 `Velcro: Invented After a Dog Walk in the Alps`, template `e6619f7e`
  - EP5 `The Microwave: A Melted Chocolate Bar in a Scientist's Pocket`, template `e6619f7e`
  - EP6 이후는 template null인 항목이 있음. 앞 5편 목표만 보면 EP3~EP5까지는 템플릿 OK.
- CH2 EP1, EP2는 이미 큐에서 빠짐:
  - EP1은 실패.
  - EP2는 현재 실행 중.

## 현재 oneclick 작업 상태
- 현재 실행 중:
  - task_id `29478658`
  - CH2 EP2
  - topic/title: `QWERTY: The Keyboard Designed to Slow You Down`
  - project_id: `딸깍_CH2_QWERTY_The_Keyboard_Designed_t_260427-1`
  - status: `running`
  - progress: `2.5%`
  - current_step_label: `대본 생성`
  - youtube_url: null
- 직전 실패:
  - task_id `a8752d47`
  - CH2 EP1
  - topic: `The Spork: 90 Years Forgotten, Until the Army Saved It`
  - project_id: `딸깍_CH2_The_Spork_90_Years_Forgotten_U_260427-1`
  - status: `failed`
  - progress: `5.0%`
  - error:
    - `음성 생성 실패: RuntimeError: TTS duration 5.50s exceeds hard limit 4.8s after narration rewrites. Refusing to accept over-limit audio.`
  - 이전 도우미 로그에는 5.70s 초과도 한 번 있었음.
  - 한 번 resume 시도했고 컷 1~2 음성/이미지 진행 후 다시 TTS hard limit으로 실패.
- 업로드 완료된 신규 작업은 아직 없음.
- 기존 과거 완료 예시:
  - CH1 EP1 `딸깍_CH1_4000년_전_한반도에_정말_나라가_있었을까_260424-1`
  - YouTube URL `https://youtube.com/watch?v=biDQRaxlwVY`
  - 이건 이번 MYLORA/비공개 목표와 별개 과거 작업.

## 가장 큰 현재 문제
- 업로드가 안 된 직접 원인:
  - MYLORA 학습이 밤사이 끝까지 못 끝나서 자동 업로드로 못 넘어갔음.
  - 이후 학습은 완료했지만, CH2 EP1이 TTS 길이 hard limit 초과로 실패해서 렌더/업로드까지 못 감.
- 현재 새로 발생한 핵심 장애:
  - TTS duration hard limit 4.8s.
  - 사용자가 이전에 강하게 지시한 조건:
    - 음성은 속도로 억지 조절하지 말 것.
    - 대본 분량으로 맞출 것.
    - 음성 생성은 있는 그대로 생성할 것.
    - 4.8초 넘는 컷이 실패한다고 작업 전체가 막히면 안 된다고 불만.
  - 현재 시스템은 narration rewrite 후에도 4.8s 초과하면 실패로 거부함.
  - 그래서 자동 대량 생성이 계속 막힐 수 있음.
- 다음 세션에서 최우선 수정 권장:
  - `backend/app/services/tts/narration_fit.py`
  - `backend/app/tasks/pipeline_tasks.py`
  - `backend/app/services/llm/base.py`
  - `backend/app/services/llm/timing.py`
  - 위 파일들에서 "대본 분량으로 길이를 맞추는 시스템"과 "실패하지 않고 재작성/재TTS 하는 정책"을 정리해야 함.
  - 단, 사용자 지시상 TTS 속도 조절은 금지.

## 자동 실행 도우미 상태/주의
- 도우미 파일:
  - `C:\Users\Ai_M9\Desktop\mylora_training\overnight_run_ch1_ch2.py`
- 로그:
  - `C:\Users\Ai_M9\Desktop\mylora_training\overnight_run_ch1_ch2.log`
- 결과 JSON:
  - `C:\Users\Ai_M9\Desktop\mylora_training\overnight_run_ch1_ch2_result.json`
- 현재 도우미 PID:
  - `14980`
- 도우미 동작:
  - 원래 CH2 5편 + CH1 5편 순차 실행.
  - EP1이 이미 running인 상태에서 시작되어 `CH2x4 + CH1x5`로 조정.
  - EP1 실패 후 resume 한 번 시도.
  - 두 번째 실패 후 다음 CH2 항목 실행.
- 도우미 버그/주의:
  - `run-next` API가 404를 반환해도 백엔드 내부에서 실제로는 task를 fire하는 레이스가 있었음.
  - 도우미는 이를 견디도록 수정됨.
  - 하지만 EP1 실패 후 `request run-next CH2` 응답이 실패 task를 반환했고, 실제로는 EP2 task가 running이 됨. 계속 감시 필요.
  - 새 세션에서 같은 도우미를 중복 실행하지 말 것.

## 코드/파일 변경 요약
- 이 세션에서 확실히 추가/수정한 것:
  - `backend/workflows/comfyui/dreamshaper_xl_mylora_text2img.json`
  - `backend/app/services/image/comfyui_service.py`
  - `backend/app/services/image/factory.py`
  - `backend/app/routers/oneclick.py`
  - `backend/app/services/oneclick_service.py`
  - `C:\Users\Ai_M9\Desktop\mylora_training\overnight_run_ch1_ch2.py`
  - `C:\Users\Ai_M9\Desktop\mylora_training\run_mylora_continue_from_3000.ps1`
  - `C:\Users\Ai_M9\Desktop\mylora_training\run_mylora_continue_from_3000_direct.ps1`
- 저장소는 원래부터 매우 dirty 상태였음.
- `git status --short`에 많은 수정/신규 파일이 있음. 절대 무작정 revert/reset 금지.
- 특히 `backend/app/routers/oneclick.py`, `backend/app/services/oneclick_service.py`에는 기존 작업분도 많아 보임. 내가 만든 작은 수정만 구분해서 다루기 어려움.

## 새 세션 시작 시 추천 순서
1. 현재 작업 상태 확인:
   ```powershell
   $env:PYTHONIOENCODING='utf-8'
   python - <<'PY'
   import json, urllib.request
   for path in ['/api/oneclick/running','/api/oneclick/tasks','/api/oneclick/queue']:
       print(path)
       print(urllib.request.urlopen('http://127.0.0.1:8000'+path, timeout=10).read().decode('utf-8')[:3000])
   PY
   ```
2. 자동 도우미가 아직 떠 있는지 확인:
   ```powershell
   Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'overnight_run_ch1_ch2' } | Select-Object ProcessId,Name,CommandLine | Format-List
   ```
3. CH2 EP2도 TTS hard limit으로 실패하면, 더 진행시키기 전에 TTS/대본 길이 로직을 고쳐야 함.
4. 필요하면 도우미 중지:
   ```powershell
   Stop-Process -Id 14980 -Force
   ```
5. TTS 문제 고친 뒤 실패한 CH2 EP1은 재큐/재시작 필요:
   - 현재 EP1은 큐에서 빠져 있고 task failed 상태.
   - `POST /api/oneclick/tasks/a8752d47/requeue` 또는 큐에 직접 재삽입 가능.
6. 업로드 확인은 프로젝트 DB의 `youtube_url` 또는 `/api/oneclick/tasks`에서 확인.

## 자주 쓰는 상태 확인 명령
```powershell
$env:PYTHONIOENCODING='utf-8'
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8000/api/oneclick/running
Invoke-RestMethod http://127.0.0.1:8000/api/oneclick/tasks
Invoke-RestMethod http://127.0.0.1:8000/api/oneclick/queue
Invoke-RestMethod http://127.0.0.1:8188/system_stats
Get-NetTCPConnection -LocalPort 3000,8000,8188
```

## 서버 접속 주소
- 이 PC에서:
  - `http://localhost:3000`
  - `http://localhost:8000/api/health`
  - `http://localhost:8188`
- 같은 LAN의 다른 PC에서:
  - `http://192.168.0.221:3000`
  - `http://192.168.0.221:8000/api/health`
  - `http://192.168.0.221:8188`

## 마지막 확인 기준 시각
- 기준 시각: `2026-04-27 22:10:28 +09:00`
- 백엔드 health OK.
- 다른 PC `192.168.0.45`에서 API polling 로그 다수 확인.
- 신규 업로드 완료분 없음.
- 현재 진행 중인 신규 작업은 CH2 EP2 `QWERTY`.
