# LongTube Session Handoff - 2026-05-04

> 보관 문서입니다. 새 세션 시작 기준은 `docs/SESSION_PROTOCOL.md` 와 `SESSION_HANDOFF.md` 입니다.

## 사용자 지시
- 말투: 자비스 톤. 존댓말 유지.
- 원칙: 추론하지 말고 실제 확인한 내용만 답변.
- 과설명 금지.
- 기존 사용자 변경사항은 되돌리지 말 것.

## 이번 세션 핵심 작업
- `http://localhost:3000/oneclick/live` 실시간 현황 화면 UI/UX 개편 진행.
- 작업 대기열을 상단으로 이동하고 5개만 표시.
- 현재 작업 카드에 썸네일, 시작/작업 중/이어서 하기 버튼, 진행률, 결과 미리보기 영역 추가.
- 이미지/영상 결과가 있으면 우측 미리보기 영역에 표시. 영상은 `video controls`로 재생 가능.
- 단계별 실제 진행 영역을 좌측 하단으로 압축하고 제작 로그를 우측으로 배치.
- 제작 로그는 새 로그 발생 시 아래로 자동 스크롤.
- 서버 상태 카드 UI 정리:
  - 프론트/백엔드/Comfy 상태는 OK 텍스트 대신 색상 박스.
  - CPU/RAM/GPU/YT는 2x2 그리드.
  - 세부 버전/용량 텍스트 제거.
- 사이드바 하단의 자동 실행 시간표와 대시보드 링크 제거.
- 호출 중 모델 표시 영역은 현재 호출 중인 모델만 표시하도록 구성.

## 최근 버그 수정
- 증상:
  - 실제 백엔드는 작업이 진행 중인데 화면에는 `대기`, `실패`, `queue is empty`처럼 보임.
- 확인한 원인:
  - 실시간 화면이 `/api/oneclick/tasks` 전체 목록 API에 의존.
  - 해당 호출이 브라우저에서 끊기면 화면 상태가 낡은 값으로 남음.
- 수정:
  - `frontend/src/app/oneclick/live/page.tsx`
  - 초기 로드/새로고침/5초 자동 갱신을 `/api/oneclick/running` + `/api/oneclick/queue` 기준으로 변경.
  - 시작 버튼 클릭 시 먼저 실제 실행 중 작업을 확인하고, 실행 중이면 새 시작 요청을 보내지 않고 해당 작업에 연결.
- 검증:
  - `frontend`에서 `npx tsc --noEmit --pretty false` 통과.

## 모델 리스트/표시 정리
- 이미지 모델 registry 정리:
  - `backend/app/services/image/factory.py`
  - 남긴 항목:
    - `SDXL Lightning`
    - `SDXL 로컬모델 v1`
    - `GPT Image 1 (gpt-image-1)`
    - `Nano Banana 3 (Reference style lock)`
    - `Nano Banana 2`
    - `Nano Banana Pro`
- 영상 모델 registry 정리:
  - `backend/app/services/video/factory.py`
  - 남긴 항목:
    - `FFmpeg Static (no motion)`
    - `FFmpeg Safe Static (source locked)`
    - `Seedance 1.0 Lite`
- TTS 모델:
  - `backend/app/services/tts/factory.py`
  - OpenAI TTS 제거, ElevenLabs만 남김.
- 단계별 실제 진행 표시:
  - 회사명 제거.
  - 예: `Sonnet 4.6`, `Harry Kim - Conversational`, `SDXL 로컬모델 v1`, `FFmpeg Static (no motion)`.

## 저장 폴더명 수정
- `backend/app/services/oneclick_service.py`
- 새 프로젝트 ID 생성 시:
  - 깨진 문자 방지용 NFC 정규화 및 Windows 금지 문자 제거.
  - 채널 뒤에 EP 번호가 붙도록 변경.
  - 예: `딸깍_CH1_EP30_제목_260504-1`
- 기존 생성 폴더는 자동 rename 하지 않음.

## 실패/고아/큐 UI
- 실패/고아 가져오기 팝업:
  - 테두리 흰색으로 변경.
  - `큐 상단으로`는 현재 팝업을 닫거나 전체 큐 창으로 이동하지 않고 기능만 수행.
- 전체 작업 큐 모달:
  - 닫기 버튼 우측 상단 고정.
  - 상단 대기열 CH 버튼 클릭 시 채널 편집 모달 열리도록 구성.

## 검증 완료
- 프론트 타입 검사:
  - `cd frontend`
  - `npx tsc --noEmit --pretty false`
  - 통과.
- 백엔드 문법 일부 확인:
  - `backend/app/services/oneclick_service.py`
  - `backend/app/services/image/factory.py`
  - `backend/app/services/video/factory.py`
  - `backend/app/services/tts/factory.py`
  - `py_compile` 통과한 상태.

## 마지막 실제 상태 확인
- 인증 쿠키 없이 API는 401 반환.
- 로컬 세션 쿠키 생성 후 확인:
  - `/api/oneclick/running`: 실행 중 작업 없음.
  - `/api/oneclick/queue`: 433개.
  - 큐 첫 작업: `한반도 최초 여왕이 미리 알았다는 세 가지`.

## 주의 사항
- 현재 워크트리는 매우 dirty 상태.
- 이번 세션에서 만진 핵심 파일:
  - `frontend/src/app/oneclick/live/page.tsx`
  - `frontend/src/app/oneclick/layout.tsx`
  - `frontend/src/components/common/LocalServiceStatus.tsx`
  - `backend/app/services/oneclick_service.py`
  - `backend/app/services/image/factory.py`
  - `backend/app/services/video/factory.py`
  - `backend/app/services/tts/factory.py`
- 그 외 `git status`에 보이는 많은 파일은 이전 작업/사용자 변경이 섞여 있음.
- 전체 `git reset --hard` 금지.
- 로컬 모델 파일 삭제 요청은 있었지만 실제 삭제는 하지 않음. 삭제는 파괴 작업이므로 명시 확인 필요.
- `rg`는 현재 정상 동작 확인됨.

## 다음 세션 바로 할 일
1. 브라우저에서 `http://localhost:3000/oneclick/live` 새로고침 후 현재 작업 카드가 `/running` 상태와 맞는지 확인.
2. 시작 버튼 클릭 시 `queue is empty`가 다시 뜨는지 확인.
3. 백엔드 코드 변경 반영이 필요한 경우 서버 재시작 여부 확인.
4. 모델 리스트 정리 후 설정/프리셋 화면에서도 표시명이 같은지 확인.
5. 저장 폴더명은 새 작업부터 확인. 기존 폴더명은 그대로 둠.
