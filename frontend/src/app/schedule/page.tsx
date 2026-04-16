"use client";

// v1.1.42: 자동화 스케줄 기능이 제거됨. 사용자 요구: "자동화 스케쥴 삭제
// 하고 그자리에 버튼 넣어". 이 페이지는 더 이상 스케줄 UI 를 제공하지 않고,
// 진입 즉시 대시보드로 리다이렉트한다. 대시보드 상단의 "딸깍 제작" 버튼이
// 이 스케줄 자리를 대체한다.
//
// 파일 자체를 지우면 인덱스/히스토리/북마크가 깨지므로 남겨두지만, 백엔드
// /api/schedule 라우터도 함께 비활성화되어 있어 실사용 경로는 모두 제거됨.
import { useEffect } from "react";

export default function SchedulePageRemoved() {
  useEffect(() => {
    if (typeof window !== "undefined") {
      window.location.replace("/");
    }
  }, []);
  return (
    <div className="min-h-screen bg-bg-primary flex items-center justify-center p-8">
      <div className="max-w-md text-center">
        <h1 className="text-xl font-semibold mb-2">자동화 스케줄은 제거되었습니다</h1>
        <p className="text-sm text-gray-400 mb-6">
          v1.1.42 부터 "딸깍 제작" 팝업으로 대체되었습니다. 대시보드에서 상단의
          <strong> 딸깍 제작</strong> 버튼을 눌러 주제와 시간을 입력하면 즉시 영상 제작이
          시작됩니다.
        </p>
        <a
          href="/"
          className="inline-block bg-accent-primary hover:bg-purple-600 text-white font-semibold px-4 py-2 rounded-lg text-sm"
        >
          대시보드로 이동
        </a>
      </div>
    </div>
  );
}
