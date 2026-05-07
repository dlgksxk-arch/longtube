"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  Loader2,
  RefreshCw,
  RotateCcw,
  Upload,
} from "lucide-react";
import { oneclickApi, type OneClickTask } from "@/lib/api";

const CHANNELS = [1, 2, 3, 4] as const;
type RowUploadState = "uploading" | "pending" | "success" | "error";

function isUploadPending(task: OneClickTask) {
  const states = task.step_states || {};
  return states["6"] === "completed" && states["7"] !== "completed";
}

function episodeLabel(task: OneClickTask) {
  return typeof task.episode_number === "number" && task.episode_number > 0
    ? `EP.${String(task.episode_number).padStart(2, "0")}`
    : "EP.--";
}

function taskTitle(task: OneClickTask) {
  const title = String(task.title || task.topic || "").trim();
  const ep = episodeLabel(task);
  return /^EP\.\s*\d+/i.test(title) ? title : `${ep} ${title}`;
}

function timeValue(value?: string | null) {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
}

function channelClass(channel?: number) {
  if (channel === 1) return "border-emerald-400/35 bg-emerald-400/10 text-emerald-200";
  if (channel === 2) return "border-sky-400/35 bg-sky-400/10 text-sky-200";
  if (channel === 3) return "border-amber-400/35 bg-amber-400/10 text-amber-200";
  return "border-fuchsia-400/35 bg-fuchsia-400/10 text-fuchsia-200";
}

function waitForPaint() {
  return new Promise<void>((resolve) => {
    requestAnimationFrame(() => resolve());
  });
}

export default function UploadPendingPage() {
  const [tasks, setTasks] = useState<OneClickTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [rowStates, setRowStates] = useState<Record<string, RowUploadState>>({});
  const [bulkUploading, setBulkUploading] = useState(false);
  const [channelFilter, setChannelFilter] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { tasks } = await oneclickApi.list();
      setTasks(tasks || []);
      setMessage(null);
    } catch (e: any) {
      setMessage({ type: "error", text: `업로드 대기 목록 로드 실패: ${e?.message || e}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const pending = useMemo(
    () =>
      tasks
        .filter(isUploadPending)
        .filter((task) => channelFilter == null || Number(task.channel || 0) === channelFilter)
        .sort((a, b) => {
          const channelDiff = Number(a.channel || 99) - Number(b.channel || 99);
          if (channelDiff !== 0) return channelDiff;
          const epDiff = Number(a.episode_number || 99999) - Number(b.episode_number || 99999);
          if (epDiff !== 0) return epDiff;
          return timeValue(b.created_at) - timeValue(a.created_at);
        }),
    [tasks, channelFilter],
  );

  const counts = useMemo(() => {
    const out: Record<number, number> = { 1: 0, 2: 0, 3: 0, 4: 0 };
    for (const task of tasks.filter(isUploadPending)) {
      const ch = Number(task.channel || 0);
      if (ch >= 1 && ch <= 4) out[ch] += 1;
    }
    return out;
  }, [tasks]);

  const reupload = async (task: OneClickTask) => {
    if (uploadingId || bulkUploading) return;
    setUploadingId(task.task_id);
    setRowStates((prev) => ({ ...prev, [task.task_id]: "uploading" }));
    setMessage({ type: "info", text: `${taskTitle(task)} 업로드 재시도 중...` });
    try {
      await waitForPaint();
      const result = await oneclickApi.manualUpload(task.task_id);
      if (result.pending) {
        setRowStates((prev) => ({ ...prev, [task.task_id]: "pending" }));
        setMessage({
          type: "info",
          text: `${taskTitle(task)} YouTube Studio 처리 대기 중${result.youtube_url ? `: ${result.youtube_url}` : ""}`,
        });
        await load();
        return;
      }
      setRowStates((prev) => ({ ...prev, [task.task_id]: "success" }));
      setMessage({
        type: "success",
        text: `${taskTitle(task)} 업로드 완료${result.youtube_url ? `: ${result.youtube_url}` : ""}`,
      });
      await load();
    } catch (e: any) {
      setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
      setMessage({ type: "error", text: `${taskTitle(task)} 업로드 실패: ${e?.message || e}` });
      await load();
    } finally {
      setUploadingId(null);
    }
  };


  const reuploadAll = async () => {
    if (bulkUploading || uploadingId || pending.length === 0) return;
    if (!confirm(`업로드 대기 ${pending.length}건을 순서대로 다시 업로드합니다. 계속할까요?`)) return;
    setBulkUploading(true);
    try {
      let ok = 0;
      for (const task of pending) {
        setUploadingId(task.task_id);
        setRowStates((prev) => ({ ...prev, [task.task_id]: "uploading" }));
        setMessage({ type: "info", text: `(${ok + 1}/${pending.length}) ${taskTitle(task)} 업로드 중...` });
        try {
          await waitForPaint();
          const result = await oneclickApi.manualUpload(task.task_id);
          if (result.pending) {
            setRowStates((prev) => ({ ...prev, [task.task_id]: "pending" }));
            setMessage({
              type: "info",
              text: `${taskTitle(task)} YouTube Studio 처리 대기 중이라 목록에 남겨둡니다.`,
            });
            continue;
          }
          setRowStates((prev) => ({ ...prev, [task.task_id]: "success" }));
          ok += 1;
        } catch (e: any) {
          setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
          setMessage({ type: "error", text: `${taskTitle(task)} 업로드 실패: ${e?.message || e}` });
          break;
        }
      }
      if (ok === pending.length) {
        setMessage({ type: "success", text: `업로드 대기 ${ok}건 처리 완료` });
      }
      await load();
    } finally {
      setUploadingId(null);
      setBulkUploading(false);
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
            <Upload size={22} className="text-accent-primary" />
            <h1 className="text-2xl font-black">업로드 대기</h1>
          </div>
          <p className="mt-1 text-sm text-gray-500">
            최종 렌더링은 끝났지만 YouTube 업로드 완료 판정이 없는 항목만 모았습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading || bulkUploading}
          className="inline-flex items-center gap-2 rounded-md border border-border bg-bg-secondary px-3 py-2 text-sm font-semibold text-gray-200 hover:bg-bg-tertiary disabled:opacity-50"
        >
          <RefreshCw size={15} className={loading ? "animate-spin" : ""} />
          새로고침
        </button>
        <button
          type="button"
          onClick={reuploadAll}
          disabled={pending.length === 0 || loading || bulkUploading || Boolean(uploadingId)}
          className="inline-flex items-center gap-2 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
        >
          {bulkUploading ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
          전체 재업로드
        </button>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setChannelFilter(null)}
          className={`rounded-md border px-3 py-1.5 text-sm font-bold ${
            channelFilter == null
              ? "border-accent-primary bg-accent-primary/20 text-accent-primary"
              : "border-border bg-bg-secondary text-gray-400 hover:text-gray-200"
          }`}
        >
          전체 {Object.values(counts).reduce((a, b) => a + b, 0)}
        </button>
        {CHANNELS.map((ch) => (
          <button
            key={ch}
            type="button"
            onClick={() => setChannelFilter(ch)}
            className={`rounded-md border px-3 py-1.5 text-sm font-black ${
              channelFilter === ch
                ? channelClass(ch)
                : "border-border bg-bg-secondary text-gray-400 hover:text-gray-200"
            }`}
          >
            CH{ch} {counts[ch]}
          </button>
        ))}
      </div>

      {message && (
        <div className={`mb-4 rounded-lg border px-4 py-3 text-sm font-semibold ${messageClass}`}>
          {message.text}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-bg-secondary p-5 text-gray-400">
          <Loader2 size={16} className="animate-spin" />
          업로드 대기 목록을 불러오는 중...
        </div>
      ) : pending.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-bg-secondary/60 p-8 text-center text-gray-500">
          업로드만 남은 항목이 없습니다.
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-bg-secondary">
          <div className="grid grid-cols-[90px_90px_minmax(260px,1fr)_140px_170px] gap-3 border-b border-border bg-bg-tertiary px-4 py-3 text-xs font-bold uppercase tracking-wide text-gray-500">
            <div>채널</div>
            <div>EP</div>
            <div>제목</div>
            <div>상태</div>
            <div className="text-right">작업</div>
          </div>
          {pending.map((task) => {
            const rowState = rowStates[task.task_id];
            const isUploading = rowState === "uploading";
            return (
            <div
              key={task.task_id}
              className={`grid grid-cols-[90px_90px_minmax(260px,1fr)_140px_170px] items-center gap-3 border-b border-border/70 px-4 py-3 last:border-b-0 ${
                isUploading ? "bg-emerald-400/5" : ""
              }`}
            >
              <div>
                <span className={`inline-flex rounded-md border px-2.5 py-1 text-sm font-black ${channelClass(task.channel)}`}>
                  CH{task.channel || "-"}
                </span>
              </div>
              <div className="font-mono text-sm font-bold text-violet-200">{episodeLabel(task)}</div>
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-gray-100">{taskTitle(task)}</div>
                <div className="truncate text-xs text-gray-500">{task.project_id}</div>
              </div>
              <div>
                {isUploading ? (
                  <span className="inline-flex items-center gap-1 rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-xs font-bold text-emerald-200">
                    <Loader2 size={12} className="animate-spin" />
                    업로드 중
                  </span>
                ) : rowState === "error" ? (
                  <span className="inline-flex items-center gap-1 rounded border border-red-400/30 bg-red-400/10 px-2 py-1 text-xs font-bold text-red-200">
                    <AlertTriangle size={12} />
                    업로드 실패
                  </span>
                ) : rowState === "pending" ? (
                  <span className="inline-flex items-center gap-1 rounded border border-blue-400/30 bg-blue-400/10 px-2 py-1 text-xs font-bold text-blue-200">
                    <Loader2 size={12} className="animate-spin" />
                    처리 대기
                  </span>
                ) : rowState === "success" ? (
                  <span className="inline-flex items-center gap-1 rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-xs font-bold text-emerald-200">
                    <CheckCircle2 size={12} />
                    완료
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-200">
                    <AlertTriangle size={12} />
                    업로드 미완료
                  </span>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Link
                  href="/oneclick/live"
                  className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-border bg-bg-primary text-gray-400 hover:text-gray-100"
                  title="작업대"
                >
                  <ExternalLink size={14} />
                </Link>
                <button
                  type="button"
                  onClick={() => reupload(task)}
                  disabled={Boolean(uploadingId) || bulkUploading}
                  className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
                >
                  {isUploading ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={13} />
                  )}
                  {isUploading ? "업로드 중" : rowState === "error" ? "다시 시도" : "재업로드"}
                </button>
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
