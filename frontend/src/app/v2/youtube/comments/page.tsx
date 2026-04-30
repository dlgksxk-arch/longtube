/**
 * /v2/youtube/comments — 댓글.
 *
 * 기획 §14.4: 좌측 260px 영상 목록 + 우측 댓글 스레드 + 답글/삭제/고정.
 * v1 의 `/api/youtube/{project_id}/videos/{video_id}/comments` 는
 * project_id 기반. v2.4.0 에서 channel_id 기반 전용 엔드포인트로 이관 예정.
 */
"use client";

import Link from "next/link";
import { EmptyState } from "@/components/v2/EmptyState";
import { V2Button } from "@/components/v2/V2Button";

export default function V2YouTubeCommentsPage() {
  return (
    <div className="p-6 space-y-4">
      <header>
        <h1 className="text-gray-100">댓글</h1>
        <p className="text-sm text-gray-500 mt-1">
          좌측 영상 목록 · 우측 댓글 스레드 · 답글/삭제/고정. v2.4.0 에서
          연결됩니다.
        </p>
      </header>

      <EmptyState
        title="v2.4.0 에서 연결됩니다"
        description={
          "v1 엔드포인트(/api/youtube/{project_id}/videos/{video_id}/comments)는\n" +
          "project_id 기반이라 CH1~CH4 채널 모델과 직접 매핑되지 않습니다.\n" +
          "그 사이 v1 UI 에서 댓글을 관리할 수 있습니다."
        }
        action={
          <Link href="/youtube/comments">
            <V2Button size="sm" variant="primary">
              v1 댓글 화면 열기
            </V2Button>
          </Link>
        }
      />
    </div>
  );
}
