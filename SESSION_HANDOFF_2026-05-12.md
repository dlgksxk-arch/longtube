# 새 세션 인계 메모 - 2026-05-12 12:52 KST

최신 인계 원본은 `SESSION_HANDOFF.md`에 저장했다.

핵심:
- CH3 EP.15 완료: `https://www.youtube.com/watch?v=WM49E5sBMU0`
- 현재 실행 중 oneclick 작업 없음.
- OpenAI 공식 비용 동기화 기능 추가 및 재시작 완료.
- 남은 핵심 이슈는 이미지 얼굴 뭉개짐.
- 원인: 역사 다큐 사람 컷에 `faceless rounded-head` 리라이트가 적용됨.
- 다음 작업: `backend/app/services/image/prompt_builder.py`에서 역사 다큐 컷의 faceless 리라이트를 제한하고, 실제 사람 인물은 readable face로 유도.
