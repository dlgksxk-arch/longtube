"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
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
  type StudioVideoListItem,
  type StudioCommentThread,
} from "@/lib/api";

// v1.1.31: 댓글 관리. 영상을 선택 → 해당 영상의 댓글 스레드를 가져와 답글/모더/삭제.

export default function CommentsPage() {
  const [videos, setVideos] = useState<StudioVideoListItem[]>([]);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(null);
  const [threads, setThreads] = useState<StudioCommentThread[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(false);
  const [loadingThreads, setLoadingThreads] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [order, setOrder] = useState<"time" | "relevance">("time");
  const [replyBoxes, setReplyBoxes] = useState<Record<string, string>>({});

  const loadVideos = useCallback(async () => {
    setLoadingVideos(true);
    try {
      const res = await youtubeStudioApi.listVideos({ maxResults: 25 });
      setVideos(res.items || []);
      if (res.items && res.items.length > 0 && !selectedVideo) {
        setSelectedVideo(res.items[0].video_id);
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoadingVideos(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadThreads = useCallback(
    async (videoId: string, o: "time" | "relevance") => {
      setLoadingThreads(true);
      setErr(null);
      try {
        const res = await youtubeStudioApi.listComments(videoId, { order: o, maxResults: 50 });
        setThreads(res.items || []);
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoadingThreads(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadVideos();
  }, [loadVideos]);

  useEffect(() => {
    if (selectedVideo) loadThreads(selectedVideo, order);
  }, [selectedVideo, order, loadThreads]);

  const doReply = async (threadId: string, parentCommentId: string) => {
    const text = (replyBoxes[threadId] || "").trim();
    if (!text) return;
    try {
      await youtubeStudioApi.replyComment(parentCommentId, text);
      setReplyBoxes((b) => ({ ...b, [threadId]: "" }));
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
    try {
      await youtubeStudioApi.moderateComment(commentId, status, banAuthor);
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`모더레이션 실패: ${(e as Error).message}`);
    }
  };

  const doSpam = async (commentId: string) => {
    if (!confirm("이 댓글을 스팸으로 신고합니다. 계속하시겠습니까?")) return;
    try {
      await youtubeStudioApi.markCommentSpam(commentId);
      if (selectedVideo) loadThreads(selectedVideo, order);
    } catch (e) {
      alert(`스팸 신고 실패: ${(e as Error).message}`);
    }
  };

  const doDelete = async (commentId: string) => {
    if (!confirm("이 댓글을 삭제합니다. 복구할 수 없습니다. 계속하시겠습니까?")) return;
    try {
      await youtubeStudioApi.deleteComment(commentId);
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
          <p className="text-gray-400 text-sm mt-1">영상을 골라 댓글에 답글을 달고, 신고/숨김/삭제합니다.</p>
        </div>
      </div>

      {err && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-sm rounded p-3 mb-4">{err}</div>
      )}

      <div className="grid grid-cols-[260px_1fr] gap-4">
        {/* Video picker */}
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
            {videos.map((v) => (
              <button
                key={v.video_id}
                onClick={() => setSelectedVideo(v.video_id)}
                className={`w-full text-left px-2 py-2 rounded text-xs transition-colors ${
                  selectedVideo === v.video_id
                    ? "bg-accent-primary/20 text-accent-primary"
                    : "text-gray-400 hover:bg-bg-tertiary"
                }`}
                title={v.title}
              >
                <div className="truncate font-semibold">{v.title}</div>
                <div className="text-[10px] text-gray-500">{v.comment_count ?? 0} 댓글</div>
              </button>
            ))}
            {videos.length === 0 && !loadingVideos && (
              <div className="text-xs text-gray-500 text-center py-4">영상 없음</div>
            )}
          </div>
        </div>

        {/* Threads */}
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
                href={selectedVideo ? `/youtube/videos/${selectedVideo}` : "#"}
                className="text-[11px] text-accent-primary hover:underline"
              >
                영상 편집 →
              </Link>
            </div>
          </div>

          {loadingThreads ? (
            <div className="text-gray-500 text-sm p-6 text-center">불러오는 중...</div>
          ) : !selectedVideo ? (
            <div className="text-gray-500 text-sm p-6 text-center">왼쪽에서 영상을 선택하세요.</div>
          ) : threads.length === 0 ? (
            <div className="text-gray-500 text-sm p-6 text-center">댓글이 없습니다.</div>
          ) : (
            <div className="space-y-4">
              {threads.map((t) => (
                <div key={t.thread_id} className="border-b border-border pb-4 last:border-b-0">
                  <div className="flex items-start gap-3">
                    <div className="w-8 h-8 rounded-full bg-gray-700 flex-shrink-0 flex items-center justify-center text-xs font-bold">
                      {(t.author || "?").slice(0, 1)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs text-gray-400 mb-0.5">
                        <span className="font-semibold text-gray-200">{t.author}</span>{" "}
                        <span>· {t.published_at ? new Date(t.published_at).toLocaleString("ko-KR") : ""}</span>
                        <span> · 👍 {t.like_count ?? 0}</span>
                      </div>
                      <div className="text-sm text-gray-100 whitespace-pre-wrap break-words">{t.text}</div>

                      <div className="flex items-center gap-1 mt-2 text-[11px]">
                        <button
                          onClick={() =>
                            setReplyBoxes((b) => ({
                              ...b,
                              [t.thread_id]: b[t.thread_id] ?? "",
                            }))
                          }
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                        >
                          <Reply size={11} /> 답글
                        </button>
                        <button
                          onClick={() => doModerate(t.top_comment_id, "heldForReview")}
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          title="검토 대기로 보류"
                        >
                          <ShieldAlert size={11} /> 보류
                        </button>
                        <button
                          onClick={() => doModerate(t.top_comment_id, "published")}
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          title="공개로 승인"
                        >
                          <ShieldCheck size={11} /> 승인
                        </button>
                        <button
                          onClick={() => doModerate(t.top_comment_id, "rejected", true)}
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                          title="거부 + 작성자 차단"
                        >
                          <Ban size={11} /> 차단
                        </button>
                        <button
                          onClick={() => doSpam(t.top_comment_id)}
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-bg-tertiary text-gray-400"
                        >
                          스팸
                        </button>
                        <button
                          onClick={() => doDelete(t.top_comment_id)}
                          className="flex items-center gap-1 px-2 py-1 rounded hover:bg-red-500/20 text-red-400"
                        >
                          <Trash2 size={11} /> 삭제
                        </button>
                      </div>

                      {/* Reply box */}
                      {replyBoxes[t.thread_id] !== undefined && (
                        <div className="mt-2 flex gap-2">
                          <input
                            type="text"
                            value={replyBoxes[t.thread_id]}
                            onChange={(e) =>
                              setReplyBoxes((b) => ({ ...b, [t.thread_id]: e.target.value }))
                            }
                            onKeyDown={(e) =>
                              e.key === "Enter" && doReply(t.thread_id, t.top_comment_id)
                            }
                            placeholder="답글 작성..."
                            className="flex-1 bg-bg-primary border border-border rounded px-2 py-1 text-xs focus:outline-none focus:border-accent-primary"
                          />
                          <button
                            onClick={() => doReply(t.thread_id, t.top_comment_id)}
                            className="bg-accent-primary hover:bg-purple-600 text-white px-3 rounded text-xs"
                          >
                            전송
                          </button>
                        </div>
                      )}

                      {/* Replies */}
                      {t.replies && t.replies.length > 0 && (
                        <div className="mt-3 pl-4 border-l border-border space-y-2">
                          {t.replies.map((r) => (
                            <div key={r.comment_id} className="flex items-start gap-2">
                              <div className="w-6 h-6 rounded-full bg-gray-700 flex-shrink-0 flex items-center justify-center text-[10px]">
                                {(r.author || "?").slice(0, 1)}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="text-[11px] text-gray-400">
                                  <span className="font-semibold text-gray-200">{r.author}</span>{" "}
                                  <span>
                                    ·{" "}
                                    {r.published_at ? new Date(r.published_at).toLocaleString("ko-KR") : ""}
                                  </span>
                                </div>
                                <div className="text-xs text-gray-100 whitespace-pre-wrap break-words">
                                  {r.text}
                                </div>
                                <div className="flex items-center gap-1 mt-1">
                                  <button
                                    onClick={() => doDelete(r.comment_id)}
                                    className="text-[10px] text-gray-500 hover:text-red-400"
                                  >
                                    삭제
                                  </button>
                                </div>
                              </div>
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
    </div>
  );
}
