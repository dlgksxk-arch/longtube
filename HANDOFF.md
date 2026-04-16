# LongTube 세션 인계 (v1.1.61 기준)

## 프로젝트
- FastAPI(backend) + Next.js(frontend) YouTube 영상 파이프라인
- 경로: `C:\Users\Jevis\Desktop\longtube\` (mount: `/sessions/nice-eager-johnson/mnt/longtube/`)
- 서버: uvicorn `--reload` (파일 변경 자동 감지)

## 사용자 선호
- 한국어 존댓말
- 거짓말/추측으로 사실 왜곡 금지
- 내 탓하지 말 것, 로그는 내가 직접 볼 것, 내가 할 수 있는 걸 사용자에게 시키지 말 것
- 쓸데없는 농담 금지

## 이미지 생성 (백엔드 현재 상태)

### 레지스트리 (`backend/app/services/image/factory.py`)
- 로컬 ComfyUI 모델: **`comfyui-dreamshaper-xl` 1개만** (provider=comfyui)
- 클라우드: openai-image-1(default), openai-dalle3, nano-banana-(3/2/pro/base), seedream-v4.5, z-image-turbo, grok-imagine, flux-dev, flux-schnell, midjourney
- Unknown model_id → openai-image-1 폴백

### ComfyUI 서비스 (`backend/app/services/image/comfyui_service.py`)
- `supports_reference_images = False` → 레퍼런스 첨부 시 썸네일은 nano-banana-3 로 자동 폴백
- generate() 단순화: 레퍼런스/IPAdapter/Redux 분기 전부 제거, base 워크플로만 제출
- SDXL 해상도 강제 매핑: 16:9=1344x768, 9:16=768x1344, 1:1=1024x1024, 3:4=896x1152, 4:3=1152x896
- 워크플로 파일: `backend/workflows/comfyui/dreamshaper_xl_lightning_text2img.json`
- `_WORKFLOW_FILES_REF` 매핑과 `*_ref.json` 파일들은 고아 상태로 남아있음 (권한 문제로 rm 실패, 참조 안 됨)

### 프롬프트 빌더 (`backend/app/services/image/prompt_builder.py`)
- `REFERENCE_STYLE_PREFIX`: 텍스트 기반 스타일 락 프리픽스 (메타 지시, 픽셀 전이 아님)
- has_reference=True 여도 `global_style` 항상 주입 (로컬 모델은 레퍼런스 픽셀을 못 받기 때문)

## 비디오 생성
### 레지스트리 (`backend/app/services/video/factory.py`)
- 로컬 ComfyUI 비디오 모델 **전부 제거**
- 유지: ffmpeg-kenburns(default), ffmpeg-static(폴백), ltx2-fast/pro, seedance-(lite/1.5-pro/1.0), kling-v2/2.5-turbo/2.6-pro
- Unknown → ffmpeg-kenburns 폴백

### LTXV 움직임 이슈 (해결됨)
- `workflows/comfyui/ltxv_13b_distilled_i2v.json`: `image_noise_scale` 0.15 → **0.3**
- `routers/video.py::_build_video_motion_prompt`: 명시적 모션 동사 주입 (카메라 팬, 바람, 파티클 등)

## 로깅
- `backend/logs/image_async.log` : `routers/image.py::_ilog()` 가 기록
- `backend/logs/video_async.log` : `routers/video.py::_vlog()` 가 기록
- 경로 mount 로 접근 가능. 사용자한테 로그 붙여달라 하지 말고 직접 읽을 것.

## 알려진 이슈 / 진행중

### Qwen-Image-Edit 통합 (보류)
- 사용자가 설치 중이었음. 레퍼런스 이미지 픽셀 기반 스타일 전이 목적.
- 다운로드 파일명 확정되면 워크플로 JSON 작성 필요. 사용자 확인 대기.

### IPAdapter 시도 이력 (폐기)
- `ComfyUI_IPAdapter_plus` 설치했는데도 계속 `IPAdapterModelLoader not found` 400.
- 사용자 짜증 극에 달해서 IPAdapter 경로 완전 제거. 다시 건드리지 말 것.

### 로컬 레퍼런스 스타일 전이
- 현재 DreamShaper XL 로는 **텍스트 프리픽스로만** 스타일 유도. 픽셀 전이 X.
- 픽셀 단위 필요 시: Qwen-Image-Edit or FLUX Kontext-dev 쪽으로. Kontext 는 비상업 라이선스 주의.

## 마지막 상태 (이 세션 직전)
- `comfyui-dreamshaper-xl` 을 factory.py 에 재추가 완료
- 사용자가 "전체 생성" 눌렀는데 IPAdapter 에러 발생 → 로그 확인 결과 그 실행은 04:05:34, 파일 수정은 04:13:49 로 **수정 반영 전 실행분**이었음
- 사용자에게 재시도 요청한 상태에서 세션 종료

## 새 세션 시작 시 체크
1. 사용자가 재시도 결과를 말하면 `backend/logs/image_async.log` tail 해서 최신 타임스탬프 확인
2. 여전히 IPAdapter 에러면 uvicorn 실제 reload 됐는지(수동 재시작 필요 여부) 확인
3. 다른 에러면 해당 라인 추적
