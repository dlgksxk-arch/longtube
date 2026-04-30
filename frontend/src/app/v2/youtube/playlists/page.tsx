/**
 * /v2/youtube/playlists — 재생목록.
 *
 * v1 의 `/api/youtube/{project_id}/playlists` 는 project_id 기반. v2.4.0 에서
 * channel_id 기반으로 재설계 예정. 그 사이 v1 UI 로 이동 가능.
 */
"use client";

import Link from "next/link";
import { EmptyState } from "@/components/v2/EmptyState";
import { V2Button } from "@/components/v2/V2Button";

export default function V2YouTubePlaylistsPage() {
  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-gray-100">재생목록</h1>
        <p className="text-sm text-gray-500 mt-1">
          채널별 재생목록 + 항목 관리. v2.4.0 에서 연결됩니다.
        </p>
      </header>

      <EmptyState
        title="v2.4.0 에서 연결됩니다"
        description={
          "v1 엔드포인트(/api/youtube/{project_id}/playlists)는 project_id\n" +
          "기반이라 CH1~CH4 채널 모델과 직접 매핑되지 않습니다.\n" +
          "그 사이 v1 UI 에서 재생목록을 관리할 수 있습니다."
        }
        action={
          <Link href="/youtube/playlists">
            <V2Button size="sm" variant="primary">
              v1 재생목록 화면 열기
            </V2Button>
          </Link>
        }
      />
    </div>
  );
}
