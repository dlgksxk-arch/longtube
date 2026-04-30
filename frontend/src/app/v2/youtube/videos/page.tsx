/**
 * /v2/youtube/videos — 내 영상.
 *
 * v2 전용 엔드포인트(/api/v2/youtube/...)는 아직 없고, v1 의
 * `/api/youtube/{project_id}/videos` 는 project_id 기반이라 CH1~CH4
 * 채널 모델과 1:1 매핑되지 않는다. v2.4.0 에서 channel_id 기반 엔드포인트로
 * 재설계 예정.
 *
 * 그 사이 사용자는 v1 UI 로 건너가 작업할 수 있다.
 */
"use client";

import Link from "next/link";
import { EmptyState } from "@/components/v2/EmptyState";
import { V2Button } from "@/components/v2/V2Button";

export default function V2YouTubeVideosPage() {
  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-gray-100">내 영상</h1>
        <p className="text-sm text-gray-500 mt-1">
          채널 드롭다운 + 영상 리스트 + 삭제/재업로드. v2.4.0 에서 전용
          엔드포인트가 붙으면 여기서 직접 관리할 수 있습니다.
        </p>
      </header>

      <EmptyState
        title="v2.4.0 에서 연결됩니다"
        description={
          "v1 엔드포인트(/api/youtube/{project_id}/videos)는 project_id\n" +
          "기반이라 CH1~CH4 채널 모델과 직접 매핑되지 않습니다.\n" +
          "그 사이 v1 UI 에서 프로젝트 단위로 영상을 관리할 수 있습니다."
        }
        action={
          <Link href="/youtube/videos">
            <V2Button size="sm" variant="primary">
              v1 영상 관리 화면 열기
            </V2Button>
          </Link>
        }
      />
    </div>
  );
}
