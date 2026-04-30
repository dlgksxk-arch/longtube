"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  MessageSquare,
  Reply,
  Trash2,
  ShieldAlert,
  ShieldCheck,
  Ban,
  RefreshCw,
  Film,
} from "lucide-react";
import {
  youtubeStudioApi,
  type StudioCommentThread,
  type StudioVideoListItem,
} from "@/lib/api";

function studioHref(path: string, projectId?: string | null): string {
  const pid = (projectId || "").trim();
  return pid ? `${path}?project=${encodeURIComponent(pid)}` : path;
}

export default function CommentsPage() {
  const searchParams = useSearchParams();
  const projectId = (searchParams.get("project") || "").trim();

  const [videos, setVideos] = useState<StudioVideoListItem[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);
  const [threads, setThreads] = useState<StudioCommentThread[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(false);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [order, setOrder] = useState<"time" | "relevance">("time");
  const [replyBoxes, setReplyBoxes] = useState<Record<string, string>>({});

  const loadVideos = useCallback(async () => {
    if (!projectId) return;
    setLoadingVideos(true);
    try {
      const res = await youtubeStudioApi.listVideos({ maxResults: 25, projectId });
      setVideos(res.items || []);
      setSelectedVideo((prev) => prev || res.items?.[0]?.video_id || null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoadingVideos(false);
    }
  }, [projectId]);

  const loadThreads = useCallback(
    async (videoId: string, sortOrder: "time" | "relevance") => {
      if (!projectId) return;
      setLoadingThreads(true);
      setErr(null);
      try {
        const res = await youtubeStudioApi.listComments(videoId, {
          order: sortOrder,
          maxResults: 50,
          projectId,
        });
        setThreads(res.items || []);
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoadingThreads(false);
      }
    },
    [projectId],
  );

  useEffect(() => {
    setSelectedVideo(null);
    setVideos([]);
    setThreads([]);
  }, [projectId]);

  useEffect(() => {
    loadVideos();
  }, [loadVideos]);

  useEffect(() => {
    if (selectedVideo) loadThreads(selectedVideo, order);
  }, [selectedVideo, order, loadThreads]);

  const doReply = async (threadId: string, parentCommentId: string) => {
    const text = (replyBoxes[threadId] || "").trim();
    if (!text || !projectId) return;
    try {
      await youtubeStudioApi.replyComment(parentCommentId, text, projectId);
      setReplyBoxes((prev) => ({ ...prev, [threadId]: "" }));
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`답글 실패: ${(e as Error).message}`);
    }
  };

  const doModerate = async (
    commentId: string,
    status: "heldForReview" | "published" | "rejected",
    banAuthor = false,
  ) => {
    if (!projectId) return;
    try {
      await youtubeStudioApi.moderateComment(commentId, status, banAuthor, projectId);
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`모더레이션 실패: ${(e as Error).message}`);
    }
  };

  const doSpam = async (commentId: string) => {
    if (!projectId || !confirm("이 댓글을 스팸으로 신고하시겠습니까?")) return;
    try {
      await youtubeStudioApi.markCommentSpam(commentId, projectId);
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`스팸 신고 실패: ${(e as Error).message}`);
    }
  };

  const doDelete = async (commentId: string) => {
    if (!projectId || !confirm("이 댓글을 삭제하시겠습니까? 복구할 수 없습니다.")) return;
    try {
      await youtubeStudioApi.deleteComment(commentId, projectId);
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`삭제 실패: ${(e as Error).message}`);
    }
  };

  return (
    <div className="p-8 max-w-6xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold">댓글</h2>
          <p className="text-gray-400 text-sm mt-1">선택된 프리셋의 댓글만 관리합니다.</p>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">
          {err}
        </div>
      )}

      {!projectId ? (
        <div className="bg-bg-secondary border border-border rounded-lg p-8 text-sm text-gray-500">
          좌측에서 프리셋을 선택하십시오.
        </div>
      ) : (
        <div className="grid grid-cols-[260px_1fr] gap-4">
          <div className="bg-bg-secondary border border-border rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-xs font-semibold text-gray-300 flex items-center gap-1">
                <Film size={12} /> 영상
              </h3>
              <button
                onClick={loadVideos}
                disabled={loadingVideos}
                className="text-[10px] text-gray-500 hover:text-white"
              >
                <RefreshCw size={10} className={loadingVideos ? "animate-spin" : ""} />
              </button>
            </div>
            <div className="space-y-1 max-h-[560px] overflow-y-auto">
              {videos.map((video) => (
                <button
                  key={video.video_id}
                  onClick={() => setSelectedVideo(video.video_id)}
                  className={`w-full text-left px-2 py-2 rounded text-xs transition-colors ${
                    selectedVideo === video.video_id
                      ? "bg-accent-primary/20 text-accent-primary"
                      : "text-gray-400 hover:bg-bg-tertiary"
                  }`}
                  title={video.title}
                >
                  <div className="truncate font-semibold">{video.title}</div>
                  <div className="text-[10px] text-gray-500">{video.comment_count ?? 0} 댓글</div>
                </button>
              ))}
              {videos.length === 0 && !loadingVideos && (
                <div className="text-xs text-gray-500 text-center py-4">영상이 없습니다.</div>
              )}
            </div>
          </div>

          <div className="bg-bg-secondary border border-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold flex items-center gap-2">
                <MessageSquare size={14} /> 댓글
              </h3>
              <div className="flex items-center gap-2">
                <select
                  value={order}
                  onChange={(e) => setOrder(e.target.value as "time" | "relevance")}
                  className="bg-bg-primary border border-border rounded px-2 py-1 text-xs"
                >
                  <option value="time">최신순</option>
                  <option value="relevance">관련순</option>
                </select>
                <Link
                  href={selectedVideo ? studioHref(`/youtube/videos/${selectedVideo}`, projectId) : "#"}
                  className="text-[11px] text-accent-primary hover:underline"
                >
                  영상 편집
                </Link>
              </div>
            </div>

            {loadingThreads ? (
              <div className="text-gray-500 text-sm p-6 text-center">불러오는 중...</div>
            ) : !selectedVideo ? (
              <div className="text-gray-500 text-sm p-6 text-center">왼쪽에서 영상을 선택해 주십시오.</div>
            ) : threads.length === 0 ? (
              <div className="text-gray-500 text-sm p-6 text-center">댓글이 없습니다.</div>
            ) : (
              <div className="space-y-4">
                {threads.map((thread) => (
                  <div key={thread.thread_id} className="border-b border-border pb-4 last:border-b-0">
                    <div className="flex items-start gap-3">
                      <div className="w-8 h-8 rounded-full bg-gray-700 flex-shrink-0 flex items-center justify-center text-xs font-bold">
                        {(thread.author || "?").slice(0, 1)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs text-gray-400 mb-0.5">
                          <span className="font-semibold text-gray-200">{thread.author}</span>{" "}
                          <span>
                            · {thread.published_at ? new Date(thread.published_at).toLocaleString("ko-KR") : ""}
                          </span>
                          <span> · 좋아요 {thread.like_count ?? 0}</span>
                        </div>
                        <div className="text-sm text-gray-100 whitespace-pre-wrap break-words">{thread.text}</div>

                        <div className="flex items-center gap-1 mt-2 text-[11px]">
                          <button
                            onClick={() =>
                              setReplyBoxes((prev) => ({
                                ...prev,
                                [thread.thread_id]: prev[thread.thread_id] ?? "",
                              }))
                            }
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            <Reply size={11} /> 답글
                          </button>
                          <button
                            onClick={() => doModerate(thread.top_comment_id, "heldForReview")}
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            <ShieldAlert size={11} /> 보류
                          </button>
                          <button
                            onClick={() => doModerate(thread.top_comment_id, "published")}
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            <ShieldCheck size={11} /> 승인
                          </button>
                          <button
                            onClick={() => doModerate(thread.top_comment_id, "rejected", true)}
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            <Ban size={11} /> 차단
                          </button>
                          <button
                            onClick={() => doSpam(thread.top_comment_id)}
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            스팸
                          </button>
                          <button
                            onClick={() => doDelete(thread.top_comment_id)}
                            className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          >
                            <Trash2 size={11} /> 삭제
                          </button>
                        </div>

                        {replyBoxes[thread.thread_id] !== undefined && (
                          <div className="mt-2 flex gap-2">
                            <input
                              type="text"
                              value={replyBoxes[thread.thread_id] || ""}
                              onChange={(e) =>
                                setReplyBoxes((prev) => ({
                                  ...prev,
                                  [thread.thread_id]: e.target.value,
                                }))
                              }
                              className="flex-1 bg-bg-primary border border-border rounded px-3 py-2 text-sm focus:outline-none focus:border-accent-primary"
                              placeholder="답글 입력"
                            />
                            <button
                              onClick={() => doReply(thread.thread_id, thread.top_comment_id)}
                              className="bg-accent-primary hover:bg-purple-600 text-white rounded px-3 py-2 text-sm"
                            >
                              등록
                            </button>
                          </div>
                        )}

                        {thread.replies?.length > 0 && (
                          <div className="mt-3 pl-4 border-l border-border space-y-3">
                            {thread.replies.map((reply) => (
                              <div key={reply.comment_id}>
                                <div className="text-xs text-gray-400 mb-0.5">
                                  <span className="font-semibold text-gray-200">{reply.author}</span>{" "}
                                  <span>
                                    · {reply.published_at ? new Date(reply.published_at).toLocaleString("ko-KR") : ""}
                                  </span>
                                </div>
                                <div className="text-sm text-gray-200 whitespace-pre-wrap break-words">{reply.text}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
