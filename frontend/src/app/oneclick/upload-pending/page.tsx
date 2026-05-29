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
const UPLOAD_PENDING_CACHE_KEY = "longtube:upload-pending:last-loaded-tasks";

function isUploadPending(task: OneClickTask) {
  const states = task.step_states || {};
  return states["6"] === "completed" && states["7"] !== "completed";
}

function uploadAttemptUsed(task: OneClickTask) {
  const states = task.step_states || {};
  return (
    Number(task.youtube_upload_attempt_count || 0) > 0 ||
    task.status === "upload_failed" ||
    states["7"] === "failed"
  );
}

function canUploadOnce(task: OneClickTask) {
  const states = task.step_states || {};
  return isUploadPending(task) && states["7"] === "pending" && !uploadAttemptUsed(task);
}

function uploadFailureReason(task: OneClickTask) {
  const withUploadError = task as OneClickTask & { upload_error?: string | null };
  return String(task.youtube_upload_error || withUploadError.upload_error || task.error || "").trim();
}

function uploadStatusReason(task: OneClickTask, isUploading: boolean, attempted: boolean) {
  const reason = uploadFailureReason(task);
  if (reason) return `실패 사유: ${reason}`;
  if (isUploading) return "사유: 업로드 진행 중";
  if (attempted) return "실패 사유: 서버에 상세 사유 없음";
  return "사유: 아직 업로드를 시도하지 않았습니다.";
}

function episodeLabel(task: OneClickTask) {
  return typeof task.episode_number === "number" && task.episode_number > 0
    ? `EP.${String(task.episode_number).padStart(2, "0")}`
    : "EP.--";
}

function taskTitle(task: OneClickTask) {
  const title = String(task.title || task.topic || "").trim();
  const ep = episodeLabel(task);
  if (ep === "EP.--") return title;
  const clean = title
    .replace(/^\s*EP\.?\s*\d+\s*[-:.)]?\s*/i, "")
    .replace(/\s*(?:[|/\\\-–—:·]\s*)?EP\.?\s*\d+\s*$/i, "")
    .trim();
  return `${clean || title} ${ep}`.trim();
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
  const [loading, setLoading] = useState(false);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [rowStates, setRowStates] = useState<Record<string, RowUploadState>>({});
  const [bulkUploading, setBulkUploading] = useState(false);
  const [channelFilter, setChannelFilter] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);

  const rememberTasks = (nextTasks: OneClickTask[]) => {
    setTasks(nextTasks);
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(UPLOAD_PENDING_CACHE_KEY, JSON.stringify(nextTasks));
    }
  };

  const patchRememberedTask = (taskId: string, patcher: (task: OneClickTask) => OneClickTask) => {
    setTasks((prev) => {
      const nextTasks = prev.map((task) => (task.task_id === taskId ? patcher(task) : task));
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(UPLOAD_PENDING_CACHE_KEY, JSON.stringify(nextTasks));
      }
      return nextTasks;
    });
  };

  const markUploadSuccess = (task: OneClickTask, youtubeUrl?: string | null) => {
    patchRememberedTask(task.task_id, (current) => ({
      ...current,
      status: "completed",
      youtube_url: youtubeUrl ?? current.youtube_url ?? null,
      step_states: { ...(current.step_states || {}), "6": "completed", "7": "completed" },
      youtube_upload_attempt_count: Number(current.youtube_upload_attempt_count || 0) + 1,
      youtube_upload_error: null,
    }));
  };

  const markUploadFailure = (task: OneClickTask, error: string) => {
    patchRememberedTask(task.task_id, (current) => ({
      ...current,
      status: "upload_failed",
      step_states: { ...(current.step_states || {}), "6": "completed", "7": "failed" },
      youtube_upload_attempt_count: Number(current.youtube_upload_attempt_count || 0) + 1,
      youtube_upload_error: error,
      error,
    }));
  };

  const load = async () => {
    setLoading(true);
    try {
      const { tasks } = await oneclickApi.list();
      const nextTasks = tasks || [];
      rememberTasks(nextTasks);
      setLoadedOnce(true);
      setMessage(null);
    } catch (e: any) {
      setMessage({ type: "error", text: `업로드 대기 목록 로드 실패: ${e?.message || e}` });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    const cached = window.sessionStorage.getItem(UPLOAD_PENDING_CACHE_KEY);
    if (!cached) return;
    try {
      const parsed = JSON.parse(cached);
      if (Array.isArray(parsed)) {
        rememberTasks(parsed);
        setLoadedOnce(true);
      }
    } catch {
      window.sessionStorage.removeItem(UPLOAD_PENDING_CACHE_KEY);
    }
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

  const uploadableCount = useMemo(() => pending.filter(canUploadOnce).length, [pending]);

  const uploadOne = async (task: OneClickTask, retry = false) => {
    if (uploadingId || bulkUploading) return;
    if (!retry && !canUploadOnce(task)) {
      setMessage({ type: "error", text: `${taskTitle(task)} 업로드는 이미 1회 시도되어 재시도하지 않습니다.` });
      return;
    }
    setUploadingId(task.task_id);
    setRowStates((prev) => ({ ...prev, [task.task_id]: "uploading" }));
    setMessage({ type: "info", text: `${taskTitle(task)} ${retry ? "재업로드" : "1회 업로드"} 중...` });
    try {
      await waitForPaint();
      const result = retry
        ? await oneclickApi.manualReupload(task.task_id)
        : await oneclickApi.manualUpload(task.task_id);
      if (!result.ok) {
        setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
        markUploadFailure(task, result.message || "실패 처리됨");
        setMessage({
          type: "error",
          text: `${taskTitle(task)} 업로드 실패: ${result.message || "실패 처리됨"}`,
        });
        return;
      }
      setRowStates((prev) => ({ ...prev, [task.task_id]: "success" }));
      markUploadSuccess(task, result.youtube_url);
      setMessage({
        type: "success",
        text: `${taskTitle(task)} 업로드 완료${result.youtube_url ? `: ${result.youtube_url}` : ""}`,
      });
    } catch (e: any) {
      const errorText = String(e?.message || e);
      setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
      markUploadFailure(task, errorText);
      setMessage({ type: "error", text: `${taskTitle(task)} 업로드 실패: ${errorText}` });
    } finally {
      setUploadingId(null);
    }
  };


  const reuploadAll = async () => {
    const uploadable = pending.filter(canUploadOnce);
    if (bulkUploading || uploadingId || uploadable.length === 0) return;
    if (!confirm(`미시도 업로드 ${uploadable.length}건을 순서대로 1회 업로드합니다. 계속할까요?`)) return;
    setBulkUploading(true);
    try {
      let ok = 0;
      let failed = 0;
      for (const task of uploadable) {
        setUploadingId(task.task_id);
        setRowStates((prev) => ({ ...prev, [task.task_id]: "uploading" }));
        setMessage({ type: "info", text: `(${ok + failed + 1}/${uploadable.length}) ${taskTitle(task)} 업로드 중...` });
        try {
          await waitForPaint();
          const result = await oneclickApi.manualUpload(task.task_id);
          if (result.ok) {
            setRowStates((prev) => ({ ...prev, [task.task_id]: "success" }));
            markUploadSuccess(task, result.youtube_url);
            ok += 1;
          } else {
            setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
            markUploadFailure(task, result.message || "실패 처리됨");
            failed += 1;
          }
        } catch (e: any) {
          const errorText = String(e?.message || e);
          setRowStates((prev) => ({ ...prev, [task.task_id]: "error" }));
          markUploadFailure(task, errorText);
          setMessage({ type: "error", text: `${taskTitle(task)} 업로드 실패: ${errorText}` });
          failed += 1;
        }
      }
      if (failed === 0) {
        setMessage({ type: "success", text: `업로드 대기 ${ok}건 처리 완료` });
      } else {
        setMessage({ type: "error", text: `업로드 완료 ${ok}건, 실패 ${failed}건` });
      }
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
          불러오기
        </button>
        <button
          type="button"
          onClick={reuploadAll}
          disabled={uploadableCount === 0 || loading || bulkUploading || Boolean(uploadingId)}
          className="inline-flex items-center gap-2 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
        >
          {bulkUploading ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} />}
          미시도 전체 업로드
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

      {!loadedOnce && !loading ? (
        <div className="rounded-lg border border-dashed border-border bg-bg-secondary/60 p-8 text-center text-gray-500">
          불러오기 버튼을 눌러 업로드 대기 목록을 조회합니다.
        </div>
      ) : loading ? (
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
          <div className="grid grid-cols-[90px_90px_minmax(260px,1fr)_minmax(320px,420px)_230px] gap-3 border-b border-border bg-bg-tertiary px-4 py-3 text-xs font-bold uppercase tracking-wide text-gray-500">
            <div>채널</div>
            <div>EP</div>
            <div>제목</div>
            <div>상태</div>
            <div className="text-right">작업</div>
          </div>
          {pending.map((task) => {
            const rowState = rowStates[task.task_id];
            const isUploading = rowState === "uploading" || task.status === "uploading";
            const attempted = uploadAttemptUsed(task);
            const uploadable = canUploadOnce(task);
            const failureReason = uploadFailureReason(task);
            const failedUpload = rowState === "error" || task.status === "upload_failed" || (attempted && task.step_states?.["7"] === "failed");
            const hasFailureReason = failureReason.length > 0;
            const statusReason = uploadStatusReason(task, isUploading, attempted);
            const reasonClass =
              failedUpload || hasFailureReason
                ? "border-red-400/20 bg-red-400/10 text-red-200"
                : isUploading
                  ? "border-emerald-400/20 bg-emerald-400/10 text-emerald-200"
                  : "border-amber-400/20 bg-amber-400/10 text-amber-200";
            return (
            <div
              key={task.task_id}
              className={`grid grid-cols-[90px_90px_minmax(260px,1fr)_minmax(320px,420px)_230px] items-center gap-3 border-b border-border/70 px-4 py-3 last:border-b-0 ${
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
              <div className="min-w-0">
                {isUploading ? (
                  <span className="inline-flex items-center gap-1 rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 text-xs font-bold text-emerald-200">
                    <Loader2 size={12} className="animate-spin" />
                    업로드 중
                  </span>
                ) : failedUpload || hasFailureReason ? (
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
                <div className={`mt-1 line-clamp-3 rounded border px-2 py-1 text-xs font-semibold ${reasonClass}`} title={statusReason}>
                  {statusReason}
                </div>
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
                  onClick={() => uploadOne(task, attempted)}
                  disabled={Boolean(uploadingId) || bulkUploading || !uploadable}
                  className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
                >
                  {isUploading ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <CheckCircle2 size={13} />
                  )}
                  {isUploading ? "업로드 중" : attempted ? "시도 완료" : "1회 업로드"}
                </button>
                {attempted && (
                  <button
                    type="button"
                    onClick={() => uploadOne(task, true)}
                    disabled={Boolean(uploadingId) || bulkUploading}
                    className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/35 bg-amber-400/10 px-3 py-1.5 text-xs font-bold text-amber-200 hover:bg-amber-400/15 disabled:opacity-40"
                  >
                    {isUploading ? <Loader2 size={13} className="animate-spin" /> : <RotateCcw size={13} />}
                    재업로드
                  </button>
                )}
              </div>
            </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
