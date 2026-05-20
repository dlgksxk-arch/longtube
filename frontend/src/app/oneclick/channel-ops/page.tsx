"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  MessageSquare,
  RefreshCw,
  Reply,
  Send,
} from "lucide-react";
import {
  channelOpsApi,
  type ChannelOpsComment,
  type ChannelOpsReplyRequest,
} from "@/lib/api";

const CHANNELS = [1, 2, 3, 4] as const;

type ChannelMessage = { type: "success" | "error" | "info"; text: string };
type ChannelError = { video_id?: string; video_title?: string; error: string };
type ChannelViewState = {
  comments: ChannelOpsComment[];
  errors: ChannelError[];
  loaded: boolean;
  message: ChannelMessage | null;
};

function emptyChannelState(): ChannelViewState {
  return { comments: [], errors: [], loaded: false, message: null };
}

function initialChannelStates(): Record<number, ChannelViewState> {
  return CHANNELS.reduce(
    (acc, ch) => {
      acc[ch] = emptyChannelState();
      return acc;
    },
    {} as Record<number, ChannelViewState>,
  );
}

function channelClass(channel: number) {
  if (channel === 1) return "border-emerald-400/35 bg-emerald-400/10 text-emerald-200";
  if (channel === 2) return "border-sky-400/35 bg-sky-400/10 text-sky-200";
  if (channel === 3) return "border-amber-400/35 bg-amber-400/10 text-amber-200";
  return "border-fuchsia-400/35 bg-fuchsia-400/10 text-fuchsia-200";
}

function clamp(value: number, min: number, max: number) {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "-";
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function canReply(comment: ChannelOpsComment) {
  return Boolean(
    comment.parent_comment_id &&
      comment.can_reply &&
      !comment.has_channel_reply &&
      !comment.is_own_comment,
  );
}

function buildReplyPayload(channel: number, comment: ChannelOpsComment): ChannelOpsReplyRequest {
  return {
    channel_id: channel,
    parent_comment_id: comment.parent_comment_id,
    comment_text: comment.text,
    author: comment.author,
    video_title: comment.video_title,
    video_id: comment.video_id,
    can_reply: comment.can_reply,
    has_channel_reply: comment.has_channel_reply,
    is_own_comment: comment.is_own_comment,
  };
}

export default function ChannelOpsPage() {
  const [channel, setChannel] = useState<number>(1);
  const [maxVideos, setMaxVideos] = useState(50);
  const [maxComments, setMaxComments] = useState(25);
  const [channelStates, setChannelStates] = useState<Record<number, ChannelViewState>>(
    initialChannelStates,
  );
  const [loading, setLoading] = useState(false);
  const [replyingId, setReplyingId] = useState<string | null>(null);
  const [bulkReplying, setBulkReplying] = useState(false);
  const currentState = channelStates[channel] || emptyChannelState();
  const comments = currentState.comments;
  const errors = currentState.errors;
  const loaded = currentState.loaded;
  const message = currentState.message;

  const replyable = useMemo(() => comments.filter(canReply), [comments]);
  const answered = useMemo(() => comments.filter((comment) => comment.has_channel_reply).length, [comments]);
  const busy = loading || bulkReplying || Boolean(replyingId);

  const updateChannelState = (
    targetChannel: number,
    updater: (prev: ChannelViewState) => ChannelViewState,
  ) => {
    setChannelStates((prev) => {
      const current = prev[targetChannel] || emptyChannelState();
      return { ...prev, [targetChannel]: updater(current) };
    });
  };

  const patchComment = (
    targetChannel: number,
    parentId: string,
    patch: Partial<ChannelOpsComment>,
  ) => {
    updateChannelState(targetChannel, (prev) => ({
      ...prev,
      comments: prev.comments.map((comment) =>
        comment.parent_comment_id === parentId ? { ...comment, ...patch } : comment,
      ),
    }));
  };

  const changeChannel = (nextChannel: number) => {
    if (busy || nextChannel === channel) return;
    setChannel(nextChannel);
  };

  const loadComments = async () => {
    if (loading) return;
    const targetChannel = channel;
    setLoading(true);
    updateChannelState(targetChannel, (prev) => ({
      ...prev,
      loaded: true,
      message: { type: "info", text: `CH${targetChannel} 댓글 불러오는 중` },
    }));
    try {
      const result = await channelOpsApi.listComments(targetChannel, { maxVideos, maxComments });
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        comments: result.comments || [],
        errors: result.errors || [],
        loaded: true,
        message: {
          type: "success",
          text: `CH${targetChannel} 댓글 ${result.comments?.length || 0}개 로드 완료 (댓글 있는 영상 ${result.videos_with_comments ?? 0}개 / 스캔 ${result.videos_scanned ?? 0}개)`,
        },
      }));
    } catch (e: any) {
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        comments: [],
        errors: [],
        loaded: true,
        message: { type: "error", text: `댓글 로드 실패: ${e?.message || e}` },
      }));
    } finally {
      setLoading(false);
    }
  };

  const replyOne = async (comment: ChannelOpsComment) => {
    if (busy || !canReply(comment)) return;
    const targetChannel = channel;
    const parentId = comment.parent_comment_id;
    setReplyingId(parentId);
    patchComment(targetChannel, parentId, { reply_error: null });
    try {
      const result = await channelOpsApi.replyComment(buildReplyPayload(targetChannel, comment));
      patchComment(targetChannel, parentId, {
        has_channel_reply: true,
        reply_text: result.reply_text,
        reply_comment_id: result.posted?.comment_id || null,
      });
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        message: { type: "success", text: "댓글 답변 완료" },
      }));
    } catch (e: any) {
      const text = e?.message || String(e);
      patchComment(targetChannel, parentId, { reply_error: text });
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        message: { type: "error", text: `댓글 답변 실패: ${text}` },
      }));
    } finally {
      setReplyingId(null);
    }
  };

  const replyAll = async () => {
    if (busy || replyable.length === 0) return;
    if (!confirm(`GPT-5.5로 답변 가능 댓글 ${replyable.length}개에 답변합니다. 계속할까요?`)) return;
    const targetChannel = channel;
    const targets = replyable;
    setBulkReplying(true);
    updateChannelState(targetChannel, (prev) => ({
      ...prev,
      message: { type: "info", text: `전체 답변 처리 중: ${targets.length}개` },
    }));
    try {
      const result = await channelOpsApi.replyAll(
        targetChannel,
        targets.map((comment) => buildReplyPayload(targetChannel, comment)),
      );
      const byParentId = new Map(result.results.map((item) => [item.parent_comment_id, item]));
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        comments: prev.comments.map((comment) => {
          const row = byParentId.get(comment.parent_comment_id);
          if (!row) return comment;
          if (row.ok) {
            return {
              ...comment,
              has_channel_reply: true,
              reply_text: row.reply_text || null,
              reply_comment_id: row.posted?.comment_id || null,
              reply_error: null,
            };
          }
          return { ...comment, reply_error: row.error || "답변 실패" };
        }),
        message: {
          type: result.failed ? "error" : "success",
          text: `전체 답변 결과: 성공 ${result.succeeded}개, 실패 ${result.failed}개${result.capped ? " (최대 50개 처리)" : ""}`,
        },
      }));
    } catch (e: any) {
      updateChannelState(targetChannel, (prev) => ({
        ...prev,
        message: { type: "error", text: `전체 답변 실패: ${e?.message || e}` },
      }));
    } finally {
      setBulkReplying(false);
    }
  };

  const messageClass =
    message?.type === "success"
      ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-200"
      : message?.type === "error"
        ? "border-red-400/30 bg-red-400/10 text-red-200"
        : "border-blue-400/30 bg-blue-400/10 text-blue-200";

  return (
    <div className="min-h-full bg-bg-primary p-5 text-white lg:p-7">
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="mr-auto">
          <div className="flex items-center gap-2">
            <MessageSquare size={22} className="text-accent-primary" />
            <h1 className="text-2xl font-black">채널운영</h1>
          </div>
        </div>
        <button
          type="button"
          onClick={loadComments}
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm font-semibold text-gray-200 hover:bg-bg-tertiary disabled:opacity-50"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          댓글 불러오기
        </button>
        <button
          type="button"
          onClick={replyAll}
          disabled={busy || replyable.length === 0}
          className="inline-flex items-center gap-2 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
        >
          {bulkReplying ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
          전체 답변하기
        </button>
      </div>

      <div className="mb-4 rounded-lg border border-border bg-bg-secondary/70 p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <div className="mb-1 text-xs font-bold text-gray-500">채널</div>
            <div className="flex flex-wrap gap-2">
              {CHANNELS.map((ch) => (
                <button
                  key={ch}
                  type="button"
                  onClick={() => changeChannel(ch)}
                  disabled={busy}
                  className={`rounded-md border px-3 py-2 text-sm font-black transition ${
                    channel === ch
                      ? channelClass(ch)
                      : "border-border bg-bg-primary text-gray-300 hover:bg-bg-tertiary"
                  } disabled:opacity-50`}
                >
                  CH{ch}
                </button>
              ))}
            </div>
          </div>
          <label className="block">
            <span className="mb-1 block text-xs font-bold text-gray-500">스캔 영상 수</span>
            <input
              type="number"
              min={1}
              max={200}
              value={maxVideos}
              disabled={busy}
              onChange={(event) => setMaxVideos(clamp(Number(event.target.value), 1, 200))}
              className="w-24 rounded-md border border-border bg-bg-primary px-3 py-2 text-sm font-bold text-gray-100 outline-none focus:border-accent-primary disabled:opacity-50"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-bold text-gray-500">댓글 수</span>
            <input
              type="number"
              min={1}
              max={100}
              value={maxComments}
              disabled={busy}
              onChange={(event) => setMaxComments(clamp(Number(event.target.value), 1, 100))}
              className="w-24 rounded-md border border-border bg-bg-primary px-3 py-2 text-sm font-bold text-gray-100 outline-none focus:border-accent-primary disabled:opacity-50"
            />
          </label>
          <div className="ml-auto grid min-w-64 grid-cols-3 gap-2">
            <div className="rounded-md border border-border bg-bg-primary px-3 py-2">
              <div className="text-xs font-bold text-gray-500">로드</div>
              <div className="text-lg font-black text-white">{comments.length}</div>
            </div>
            <div className="rounded-md border border-border bg-bg-primary px-3 py-2">
              <div className="text-xs font-bold text-gray-500">답변가능</div>
              <div className="text-lg font-black text-emerald-200">{replyable.length}</div>
            </div>
            <div className="rounded-md border border-border bg-bg-primary px-3 py-2">
              <div className="text-xs font-bold text-gray-500">답변됨</div>
              <div className="text-lg font-black text-blue-200">{answered}</div>
            </div>
          </div>
        </div>
      </div>

      {message && (
        <div className={`mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${messageClass}`}>
          {message.text}
        </div>
      )}

      {errors.length > 0 && (
        <div className="mb-4 rounded-lg border border-amber-400/30 bg-amber-400/10 p-4 text-sm text-amber-100">
          <div className="mb-2 flex items-center gap-2 font-bold">
            <AlertTriangle size={16} />
            일부 영상 댓글 조회 실패
          </div>
          <div className="space-y-1">
            {errors.slice(0, 5).map((item, idx) => (
              <div key={`${item.video_id || idx}-${idx}`} className="truncate text-amber-100/90">
                {item.video_title || item.video_id || "영상"}: {item.error}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {!loaded && (
          <div className="rounded-lg border border-dashed border-border bg-bg-secondary/40 px-4 py-14 text-center text-sm font-semibold text-gray-500">
            댓글을 불러오지 않았습니다.
          </div>
        )}

        {loaded && loading && (
          <div className="rounded-lg border border-border bg-bg-secondary/60 px-4 py-14 text-center text-sm font-semibold text-gray-400">
            <Loader2 size={22} className="mx-auto mb-3 animate-spin text-accent-primary" />
            댓글 로드 중
          </div>
        )}

        {loaded && !loading && comments.length === 0 && (
          <div className="rounded-lg border border-dashed border-border bg-bg-secondary/40 px-4 py-14 text-center text-sm font-semibold text-gray-500">
            불러온 댓글이 없습니다.
          </div>
        )}

        {!loading &&
          comments.map((comment) => {
            const rowBusy = replyingId === comment.parent_comment_id;
            const disabledReason = comment.is_own_comment
              ? "본인 댓글"
              : comment.has_channel_reply
                ? "답변 완료"
                : comment.can_reply
                  ? ""
                  : "답변 불가";

            return (
              <article
                key={comment.parent_comment_id || comment.thread_id || `${comment.video_id}-${comment.published_at}`}
                className="rounded-lg border border-border bg-bg-secondary/70 p-4 shadow-sm shadow-black/20"
              >
                <div className="mb-3 flex flex-wrap items-start gap-3">
                  {comment.video_thumbnail && (
                    <img
                      src={comment.video_thumbnail}
                      alt=""
                      className="h-16 w-28 rounded-md border border-border object-cover"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <span className={`rounded border px-2 py-0.5 text-xs font-black ${channelClass(comment.channel_id || channel)}`}>
                        CH{comment.channel_id || channel}
                      </span>
                      <span className="text-xs font-semibold text-gray-500">{formatDate(comment.published_at)}</span>
                      {comment.has_channel_reply && (
                        <span className="inline-flex items-center gap-1 rounded border border-blue-400/30 bg-blue-400/10 px-2 py-0.5 text-xs font-bold text-blue-200">
                          <CheckCircle2 size={12} />
                          답변 완료
                        </span>
                      )}
                    </div>
                    <a
                      href={comment.video_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex max-w-full items-center gap-1 truncate text-sm font-bold text-gray-100 hover:text-accent-primary"
                    >
                      <span className="truncate">{comment.video_title || comment.video_id}</span>
                      <ExternalLink size={13} className="shrink-0" />
                    </a>
                  </div>
                  <button
                    type="button"
                    onClick={() => replyOne(comment)}
                    disabled={busy || !canReply(comment)}
                    title={disabledReason || "답하기"}
                    className="inline-flex items-center gap-2 rounded-md border border-accent-primary/30 bg-accent-primary/10 px-3 py-2 text-sm font-bold text-accent-primary hover:bg-accent-primary/15 disabled:border-border disabled:bg-bg-primary disabled:text-gray-500 disabled:opacity-70"
                  >
                    {rowBusy ? <Loader2 size={15} className="animate-spin" /> : <Reply size={15} />}
                    답하기
                  </button>
                </div>

                <div className="rounded-md border border-border bg-bg-primary/70 p-3">
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <span className="font-bold text-gray-100">{comment.author || "작성자"}</span>
                    <span className="text-xs font-semibold text-gray-500">
                      답글 {comment.total_reply_count || 0}개
                    </span>
                  </div>
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-gray-200">
                    {comment.text}
                  </p>
                  {comment.translated_text && (
                    <div className="mt-3 rounded-md border border-sky-400/20 bg-sky-400/10 p-3">
                      <div className="mb-1 text-xs font-black text-sky-200">번역</div>
                      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-sky-50">
                        {comment.translated_text}
                      </p>
                    </div>
                  )}
                  {comment.translation_error && (
                    <div className="mt-2 text-xs font-semibold text-amber-200">
                      번역 실패: {comment.translation_error}
                    </div>
                  )}
                </div>

                {(comment.reply_text || comment.reply_error) && (
                  <div
                    className={`mt-3 rounded-md border p-3 text-sm ${
                      comment.reply_error
                        ? "border-red-400/30 bg-red-400/10 text-red-100"
                        : "border-emerald-400/30 bg-emerald-400/10 text-emerald-100"
                    }`}
                  >
                    <div className="mb-1 font-bold">
                      {comment.reply_error ? "답변 실패" : "작성된 답변"}
                    </div>
                    <div className="whitespace-pre-wrap break-words leading-6">
                      {comment.reply_error || comment.reply_text}
                    </div>
                  </div>
                )}
              </article>
            );
          })}
      </div>
    </div>
  );
}
