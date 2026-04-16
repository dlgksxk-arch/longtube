"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Timer, Loader2, XCircle } from "lucide-react";
import { taskApi, type TaskStatus } from "@/lib/api";

interface Props {
  /** project ID */
  projectId: string;
  /** step name for task API: "voice" | "image" | "video" | "subtitle" */
  step: string;
  /** fallback: true while local generation is in progress (for non-async calls like script) */
  running?: boolean;
  /** fallback: total items for local timer */
  totalItems?: number;
  /** fallback: estimated seconds per item for local timer */
  secsPerItem?: number;
  /** label */
  label?: string;
  /** called when background task completes */
  onComplete?: () => void;
}

const fmtTime = (s: number) => {
  if (s <= 0) return "곧 완료";
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  if (m < 60) return `${m}분 ${sec}초`;
  const h = Math.floor(m / 60);
  return `${h}시간 ${m % 60}분`;
};

export default function GenerationTimer({ projectId, step, running, totalItems, secsPerItem, label, onComplete }: Props) {
  const [taskStatus, setTaskStatus] = useState<TaskStatus | null>(null);
  const [localElapsed, setLocalElapsed] = useState(0);
  const localStartRef = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const localRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  // Poll backend task status
  const pollTask = useCallback(async () => {
    try {
      const status = await taskApi.status(projectId, step);
      setTaskStatus(status);
      if (status.status === "completed" || status.status === "failed" || status.status === "cancelled") {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        if (status.status === "completed") {
          onCompleteRef.current?.();
        }
      }
    } catch {
      // ignore
    }
  }, [projectId, step]);

  // Start polling when component mounts or step changes
  useEffect(() => {
    pollTask(); // initial check
    pollRef.current = setInterval(pollTask, 1500);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [pollTask]);

  // Local timer fallback (for script generation which isn't async)
  useEffect(() => {
    if (running) {
      localStartRef.current = Date.now();
      setLocalElapsed(0);
      localRef.current = setInterval(() => {
        setLocalElapsed(Math.floor((Date.now() - localStartRef.current) / 1000));
      }, 1000);
    } else {
      if (localRef.current) clearInterval(localRef.current);
      localRef.current = null;
    }
    return () => {
      if (localRef.current) clearInterval(localRef.current);
    };
  }, [running]);

  // Determine what to show
  const isServerRunning = taskStatus?.status === "running";
  const isLocalRunning = running && !isServerRunning;

  if (!isServerRunning && !isLocalRunning) return null;

  let pct = 0;
  let elapsedStr = "";
  let totalStr = "";
  let remainStr = "";
  let displayLabel = label || "생성 중...";

  // Detect stuck task: running > 2 min with 0 completed AND no time-based estimate
  // v1.1.49: 단일 작업(total=1)은 progress_pct>0이면 시간 기반 추정이 작동 중이므로 stuck 아님
  const isStuck = isServerRunning && taskStatus &&
    taskStatus.elapsed > 120 && taskStatus.completed === 0 && taskStatus.progress_pct === 0;

  if (isServerRunning && taskStatus) {
    pct = taskStatus.progress_pct;
    elapsedStr = fmtTime(Math.round(taskStatus.elapsed));
    const eta = taskStatus.eta_seconds;
    // v1.1.49: eta_seconds > 0이면 시간 기반 추정 사용 (단일 작업 포함)
    const totalEst = eta > 0 ? Math.round(taskStatus.elapsed + eta) : 0;
    totalStr = totalEst > 0 ? fmtTime(totalEst) : "계산 중";
    remainStr = isStuck
      ? "응답 없음 — 취소 후 재시도하세요"
      : eta > 0
        ? `~${fmtTime(eta)}`
        : "계산 중";
    // v1.1.49: 단일 작업(total=1)은 (0/1) 대신 퍼센트만 표시
    const isSingleTask = taskStatus.total === 1;
    displayLabel = isStuck
      ? `⚠️ ${label || step} 생성 멈춤 — API 응답 없음`
      : isSingleTask
        ? `${label || step + " 생성 중..."}`
        : `${label || step + " 생성 중..."} (${taskStatus.completed}/${taskStatus.total})`;
  } else if (isLocalRunning && totalItems && secsPerItem) {
    const totalEst = Math.ceil(totalItems * secsPerItem);
    pct = totalEst > 0 ? Math.min(100, Math.round((localElapsed / totalEst) * 100)) : 0;
    elapsedStr = fmtTime(localElapsed);
    totalStr = fmtTime(totalEst);
    remainStr = fmtTime(Math.max(0, totalEst - localElapsed));
  }

  const cancelTask = async () => {
    try {
      await taskApi.cancel(projectId, step);
      pollTask();
    } catch {}
  };

  return (
    <div className="flex items-center gap-3 bg-accent-primary/10 border border-accent-primary/30 rounded-lg px-4 py-2.5">
      <Loader2 size={16} className="text-accent-primary animate-spin flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-accent-primary font-medium">{displayLabel}</span>
          <span className="text-xs text-gray-400">
            {elapsedStr} / ~{totalStr}
          </span>
        </div>
        <div className="w-full h-1.5 bg-gray-700/50 rounded-full overflow-hidden">
          <div
            className="h-full bg-accent-primary rounded-full transition-all duration-1000"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1">
          <span className="text-[10px] text-gray-500">{pct}%</span>
          <span className="text-[10px] text-gray-400 flex items-center gap-1">
            <Timer size={9} />
            남은 시간: {remainStr}
          </span>
        </div>
      </div>
      {isServerRunning && (
        <button
          onClick={cancelTask}
          className="p-1.5 rounded hover:bg-accent-danger/20 text-gray-500 hover:text-accent-danger transition-colors flex-shrink-0"
          title="취소"
        >
          <XCircle size={16} />
        </button>
      )}
    </div>
  );
}
