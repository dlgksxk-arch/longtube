"use client";

/**
 * v1.1.49 — 딸깍 대시보드 > 작업대
 * - 파이프라인 진행 + 터미널 로그 + 미리보기 + 단계 상세
 * - 예상 비용/시간 표시
 * - 에러/멈춤 이유 표시
 * - 창 닫아도 백엔드 작업은 계속 진행 (페이지 복귀 시 진행 중 태스크만 연결)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Loader2,
  CheckCircle2,
  PlayCircle,
  Circle,
  Square,
  DollarSign,
  Timer,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  ListChecks,
  X,
  Trash2,
  Film,
  Power,
  Pencil,
} from "lucide-react";
import {
  oneclickApi,
  modelsApi,
  voiceApi,
  projectsApi,
  assetUrl,
  type OneClickTask,
  type OneClickQueueItem,
  type OrphanProject,
  type ProjectConfig,
} from "@/lib/api";
import { formatKrw } from "@/lib/format";
import { APP_VERSION } from "@/lib/version";
import {
  compactSeconds,
  isConsoleProgressLog,
  isUploadRecoverableTask,
  type LogEntry,
  serverLogToEntry,
  stepApiName,
  stepModelName,
  stepTargetText,
  taskLogsToEntries,
  taskProgressHeartbeat,
  taskTitle,
  timeValue,
} from "./displayHelpers";
import {
  channelBadgeClass,
  collectQueueChannels,
  DEFAULT_QUEUE_CHANNEL_TIMES,
  episodePrefix,
  formatEpisodeBadge,
  formatQueueWaitingMeta,
  isLiveNextQueueItem,
  normalizeQueueChannelTimes,
  queueChannelTimeLabel,
  queueItemKey,
  queueTitle,
  scheduledDelayMinutes,
  withEpisodeTitle,
} from "./queueHelpers";
import {
  getEffectiveStepStates,
  getEffectiveTask,
  getStepState,
  getTaskFailureStepName,
  inferLiveStepKey,
  STEP_ORDER,
  STEPS,
} from "./taskHelpers";
import { ThumbnailPanel } from "./ThumbnailPanel";


/** 단계별 작업 활동 패널 — 각 단계가 살아있는지 / 얼마나 진행됐는지 / 멈춤인지 시각화 */
function ActivityPanel({
  task,
  isRunningTask,
  clearingStep,
  rerunningStep,
  uploadingStep,
  onClearStep,
  onRerunStep,
  onReupload,
}: {
  task: OneClickTask | null;
  isRunningTask: boolean;
  clearingStep: number | null;
  rerunningStep: number | null;
  uploadingStep: boolean;
  onClearStep: (step: number, label: string) => void;
  onRerunStep: (step: number) => void;
  onReupload: () => void;
}) {
  const [modelNameMap, setModelNameMap] = useState<Record<string, string>>({});
  const [voiceNameMap, setVoiceNameMap] = useState<Record<string, string>>({});
  // 활성 단계의 마지막 진행 변화를 추적해서 stale(멈춤) 여부 판단
  const lastTickRef = useRef<{ step: string; heartbeat: string; ts: number }>({
    step: "",
    heartbeat: "",
    ts: Date.now(),
  });
  const [now, setNow] = useState(Date.now());

  // 1초 틱으로 경과/ETA/멈춤 표시 갱신
  useEffect(() => {
    const iv = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const [llmRes, ttsRes, imageRes, videoRes] = await Promise.all([
          modelsApi.listLLM(),
          modelsApi.listTTS(),
          modelsApi.listImage(),
          modelsApi.listVideo(),
        ]);

        if (cancelled) return;

        const nextMap: Record<string, string> = {};
        for (const model of [
          ...(llmRes.models || []),
          ...(ttsRes.models || []),
          ...(imageRes.models || []),
          ...(videoRes.models || []),
        ]) {
          if (!model?.id) continue;
          nextMap[model.id] = model.name || model.id;
        }
        setModelNameMap(nextMap);
      } catch {
        if (!cancelled) setModelNameMap({});
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const projectId = task?.project_id;
    const ttsModel = task?.models?.tts;

    if (!projectId || !ttsModel) {
      setVoiceNameMap({});
      return;
    }

    voiceApi
      .listVoices(projectId, ttsModel)
      .then((res) => {
        if (cancelled) return;
        const voices = Array.isArray(res?.voices) ? res.voices : [];
        const nextMap: Record<string, string> = {};
        for (const voice of voices) {
          if (!voice?.id) continue;
          nextMap[voice.id] = voice.name || voice.id;
        }
        setVoiceNameMap(nextMap);
      })
      .catch(() => {
        if (!cancelled) setVoiceNameMap({});
      });

    return () => {
      cancelled = true;
    };
  }, [task?.project_id, task?.models?.tts]);

  if (!task) {
    return (
      <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
        <h3 className="text-base font-bold text-gray-100 mb-4">단계별 작업 활동</h3>
        <div className="text-sm text-gray-600 py-6 text-center">
          진행 중인 작업이 없습니다.
        </div>
      </div>
    );
  }

  const liveTask = getEffectiveTask(task) || task;
  const stepStates = liveTask.step_states || {};
  const completedByStep = liveTask.completed_cuts_by_step || {};
  const totalCuts = Math.max(1, Number(liveTask.total_cuts || 0));
  const timeBreakdown = liveTask.estimate?.time_breakdown || {};

  // step → 예상 소요 (초) 매핑
  const stepEstSec: Record<string, number> = {
    "2": Number(timeBreakdown.llm_script || 0),
    "3": Number(timeBreakdown.tts || 0),
    "4": Number(timeBreakdown.image_generation || 0),
    "5": Number(timeBreakdown.video || 0),
    "6": Number(timeBreakdown.post_process || 0),
    "7": 30,
  };

  // 활성 단계 계산 (병렬일 수 있음 — 음성+이미지)
  const activeSteps = STEPS.filter((s) => stepStates[s.key] === "running");

  // 멈춤(stale) 감지 — 활성 단계 컷 수가 변하지 않은 채 60초 이상 경과
  const primaryActive = activeSteps[0];
  let staleSec = 0;
  if (primaryActive) {
    const activeHeartbeat = [
      Number(completedByStep[primaryActive.key] || 0),
      liveTask.current_step_completed ?? "",
      liveTask.current_step_cut_progress_pct ?? "",
      liveTask.progress_pct ?? "",
      liveTask.sub_status || "",
      liveTask.logs?.length || 0,
    ].join("|");
    const tick = lastTickRef.current;
    if (tick.step !== primaryActive.key || tick.heartbeat !== activeHeartbeat) {
      lastTickRef.current = { step: primaryActive.key, heartbeat: activeHeartbeat, ts: now };
    } else {
      staleSec = Math.floor((now - tick.ts) / 1000);
    }
  } else {
    lastTickRef.current = { step: "", heartbeat: "", ts: now };
  }

  return (
    <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-bold text-gray-100">단계별 작업 활동</h3>
        {activeSteps.length > 0 && (
          <div className="flex items-center gap-1.5 text-sm text-gray-500">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-400" />
            </span>
            실시간 폴링 중
          </div>
        )}
      </div>

      <div className="space-y-2.5">
        {STEPS.map((s) => {
          const state = getStepState(liveTask, s.key);
          const stepNum = Number(s.key);
          const cuts = Number(completedByStep[s.key] || 0);
          const estimatedModels = liveTask?.estimate?.models_used || {};
          const rawStepModel =
            s.modelKey && s.modelKey !== "tts"
              ? (liveTask.models?.[s.modelKey] ||
                  estimatedModels[s.modelKey as keyof typeof estimatedModels] ||
                  "")
              : "";
          const rawTtsModel = liveTask.models?.tts || estimatedModels.tts || "";
          const modelName =
            s.modelKey
              ? s.modelKey === "tts"
                ? [
                    rawTtsModel
                      ? modelNameMap[rawTtsModel] || rawTtsModel
                      : "",
                    liveTask.models?.tts_voice
                      ? voiceNameMap[liveTask.models.tts_voice] || liveTask.models.tts_voice
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" / ")
                : rawStepModel
                  ? modelNameMap[rawStepModel] || rawStepModel
                  : ""
              : "";
          // 컷 단위 진행이 의미 있는 단계
          const hasCutProgress = ["3", "4", "5"].includes(s.key);
          const target = hasCutProgress ? totalCuts : 1;
          const ratio = state === "done"
            ? 1
            : hasCutProgress
              ? Math.min(1, cuts / Math.max(1, totalCuts))
              : state === "active" ? 0.5 : 0;
          const pct = Math.round(ratio * 100);

          // ETA — 활성 단계만
          let etaText = "";
          if (state === "active") {
            const est = stepEstSec[s.key] || 0;
            if (hasCutProgress && cuts > 0 && est > 0) {
              const perCut = est / totalCuts;
              const remainSec = Math.max(0, Math.round(perCut * (totalCuts - cuts)));
              etaText = `남은 ~${compactSeconds(remainSec)}`;
            } else if (est > 0) {
              etaText = `예상 ~${compactSeconds(est)}`;
            }
          }

          const isStaleHere = state === "active" && primaryActive?.key === s.key && staleSec >= 60;
          const canClear = stepNum >= 2 && stepNum <= 6;
          const canRerun = stepNum >= 2 && stepNum <= 6;
          const canReupload = stepNum === 7;
          const isPendingLike = state === "pending";
          const isBusy =
            isRunningTask ||
            clearingStep === stepNum ||
            rerunningStep === stepNum ||
            (canReupload && uploadingStep);

          return (
            <div
              key={s.key}
              className={`rounded-lg border px-3 py-2.5 sm:px-3.5 sm:py-3 transition-colors ${
                state === "active"
                  ? isStaleHere
                    ? "border-amber-400/60 bg-amber-400/[0.04]"
                    : "border-accent-primary/50 bg-accent-primary/[0.05]"
                  : state === "done"
                    ? "border-emerald-400/25 bg-emerald-400/[0.03]"
                    : state === "failed"
                      ? "border-accent-danger/40 bg-accent-danger/[0.04]"
                      : "border-border/60 bg-transparent"
              }`}
            >
              <div className="flex items-start gap-2 sm:gap-2.5">
                <StepIcon state={state} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-gray-200 truncate">
                    {s.label}
                  </div>
                  {modelName && (
                    <div className="mt-1 flex max-w-full items-start gap-1.5 rounded-md border border-border/80 bg-bg-primary/70 px-2 py-1">
                      <span className="flex-shrink-0 text-[11px] font-semibold text-gray-400">
                        모델
                      </span>
                      <span className="min-w-0 text-xs leading-snug text-gray-200 break-all">
                        {modelName}
                      </span>
                    </div>
                  )}
                </div>
                <div className="text-sm text-gray-500 tabular-nums">
                  {state === "done" && hasCutProgress
                    ? `${totalCuts} / ${totalCuts}`
                    : state === "done"
                      ? "완료"
                      : state === "active" && hasCutProgress
                        ? `${cuts} / ${totalCuts}`
                        : state === "active"
                          ? "진행 중"
                          : state === "failed"
                            ? "실패"
                            : "대기"}
                </div>
              </div>

              {/* 진행 바 — 활성/완료 단계만 */}
              {(state === "active" || state === "done") && (
                <div className="mt-2.5">
                  <div className="h-1.5 rounded-full bg-bg-primary/80 overflow-hidden relative">
                    <div
                      className={`h-full rounded-full transition-[width] duration-500 ease-out ${
                        state === "done"
                          ? "bg-emerald-400/80"
                          : isStaleHere
                            ? "bg-amber-400/80"
                            : "bg-accent-primary"
                      }`}
                      style={{ width: `${Math.max(state === "active" ? 4 : 0, pct)}%` }}
                    />
                    {/* 활성이면서 컷 단위 진행이 없는 단계는 살아있음을 보여주는 흐름 라인 */}
                    {state === "active" && !hasCutProgress && !isStaleHere && (
                      <div className="absolute inset-0 overflow-hidden">
                        <div className="h-full w-1/3 bg-accent-primary/60 animate-[slide_1.6s_linear_infinite]" />
                      </div>
                    )}
                  </div>

                  {state === "active" && (
                    <div className="flex items-center justify-between mt-1.5 text-sm text-gray-500">
                      <span className="flex items-center gap-1">
                        {isStaleHere ? (
                          <>
                            <AlertTriangle size={11} className="text-amber-400" />
                            <span className="text-amber-400">
                              {staleSec}s 동안 변화 없음
                            </span>
                          </>
                        ) : (
                          <>
                            <Loader2 size={11} className="animate-spin text-accent-primary" />
                            <span>처리 중…</span>
                          </>
                        )}
                      </span>
                      <span className="tabular-nums">{etaText}</span>
                    </div>
                  )}
                </div>
              )}

              {(canClear || canReupload) && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {canClear && (
                    <button
                      onClick={() => onClearStep(stepNum, s.label)}
                      disabled={isBusy || isPendingLike}
                      className="inline-flex items-center gap-1.5 rounded-md border border-red-500/30 bg-red-500/10 px-2.5 py-1.5 text-xs font-semibold text-red-300 transition-colors hover:bg-red-500/15 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <X size={12} />
                      {clearingStep === stepNum ? "삭제 중..." : "삭제"}
                    </button>
                  )}

                  {canRerun && (
                    <button
                      onClick={() => onRerunStep(stepNum)}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-accent-primary/30 bg-accent-primary/10 px-2.5 py-1.5 text-xs font-semibold text-accent-primary transition-colors hover:bg-accent-primary/15 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <RotateCcw size={12} className={rerunningStep === stepNum ? "animate-spin" : ""} />
                      {rerunningStep === stepNum ? "재실행 중..." : "삭제 후 다시"}
                    </button>
                  )}

                  {canReupload && (
                    <button
                      onClick={onReupload}
                      disabled={isBusy}
                      className="inline-flex items-center gap-1.5 rounded-md border border-accent-primary/30 bg-accent-primary/10 px-2.5 py-1.5 text-xs font-semibold text-accent-primary transition-colors hover:bg-accent-primary/15 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <RotateCcw size={12} className={uploadingStep ? "animate-spin" : ""} />
                      {uploadingStep ? "업로드 중..." : "다시 업로드"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* CSS 키프레임 — 무한 흐름 라인 */}
      <style jsx>{`
        @keyframes slide {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </div>
  );
}

function StepIcon({ state }: { state: "done" | "active" | "pending" | "failed" }) {
  if (state === "done") return <CheckCircle2 size={16} className="text-emerald-400" />;
  if (state === "active") return <Loader2 size={16} className="text-accent-primary animate-spin" />;
  if (state === "failed") return <AlertTriangle size={16} className="text-accent-danger" />;
  return <Circle size={16} className="text-gray-600" />;
}

export default function LivePage() {
  const [task, setTask] = useState<OneClickTask | null>(null);
  const taskRef = useRef<OneClickTask | null>(null);
  // v1.1.65: 동시/대기 중 task 전체 목록. 화면에 "진행 중 N건" 스트립으로 노출.
  // 백엔드는 _RUN_LOCK 으로 한 번에 1건만 실행하지만 사용자가 여러 건을 시작하거나
  // 큐 스케줄러(_queue_loop)가 여러 채널을 동시에 fire 하면 prepared/queued/running
  // 이 여러 개 쌓일 수 있다. 기존 .find() 1건 표시로는 가려지던 상태.
  const [activeTasks, setActiveTasks] = useState<OneClickTask[]>([]);
  const [pendingQueueItems, setPendingQueueItems] = useState<OneClickQueueItem[]>([]);
  const [previewModelConfig, setPreviewModelConfig] = useState<Partial<ProjectConfig> | null>(null);
  const [queueChannelTimes, setQueueChannelTimes] = useState<Record<string, string | null>>(
    DEFAULT_QUEUE_CHANNEL_TIMES,
  );
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [recoveryChannel, setRecoveryChannel] = useState<number | null>(null);
  const [failedTasks, setFailedTasks] = useState<OneClickTask[]>([]);
  const [completedTasks, setCompletedTasks] = useState<OneClickTask[]>([]);
  const [orphanProjects, setOrphanProjects] = useState<OrphanProject[]>([]);
  const [recoveringId, setRecoveringId] = useState<string | null>(null);
  const [recoveryUploadingId, setRecoveryUploadingId] = useState<string | null>(null);
  const [recoveryBulkUploading, setRecoveryBulkUploading] = useState(false);
  const [recoveryBulkQueuing, setRecoveryBulkQueuing] = useState(false);
  const [movingQueueId, setMovingQueueId] = useState<string | null>(null);
  const [queuePanelOpen, setQueuePanelOpen] = useState(false);
  const [queueEditChannel, setQueueEditChannel] = useState<number | null>(null);
  const [queueChannelFilter, setQueueChannelFilter] = useState<number | null>(null);
  const [selectedQueueIds, setSelectedQueueIds] = useState<Set<string>>(new Set());
  const [queueBatchRunning, setQueueBatchRunning] = useState(false);
  const [autoProductionEnabled, setAutoProductionEnabled] = useState(true);
  const [autoProductionRemaining, setAutoProductionRemaining] = useState(0);
  const [autoProductionSaving, setAutoProductionSaving] = useState(false);
  const [safetyStatus, setSafetyStatus] = useState<"ok" | "alert" | string>("ok");
  const [safetyMessage, setSafetyMessage] = useState<string>("감시 정상");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [pollFails, setPollFails] = useState(0);
  const [lastServerSyncAt, setLastServerSyncAt] = useState<number | null>(null);
  const [thumbnailPromptOpen, setThumbnailPromptOpen] = useState(false);
  const [thumbnailPrompt, setThumbnailPrompt] = useState("");
  const [thumbnailPromptLoading, setThumbnailPromptLoading] = useState(false);
  const [thumbnailPromptSaving, setThumbnailPromptSaving] = useState(false);
  const [thumbnailRegenerating, setThumbnailRegenerating] = useState(false);
  const [thumbnailRefreshKey, setThumbnailRefreshKey] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logScrollRef = useRef<HTMLDivElement | null>(null);
  // 멈춤 감지: 진행률이 일정 시간 변하지 않으면 경고
  const lastPctChangeRef = useRef<number>(Date.now());
  const lastPctValueRef = useRef<string>("");
  const [stalled, setStalled] = useState(false);
  // v1.2.27: 3분 stall 시 ComfyUI 큐 자동 리셋을 이번 stall 라운드에 이미 쐈는지.
  // 진행률이 다시 변하면 false 로 되돌려 다음 stall 라운드에 다시 쏠 수 있게 한다.
  const autoResetFiredRef = useRef<boolean>(false);
  // v2.1.2: 서버 측 로그 동기화 카운터
  const serverLogCountRef = useRef<number>(0);
  const selectedTaskIdRef = useRef<string | null>(null);
  const uploadVerifiedReloadRef = useRef<boolean>(false);

  useEffect(() => {
    taskRef.current = task;
  }, [task]);

  useEffect(() => {
    if (!recoveryOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setRecoveryOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [recoveryOpen]);

  const timeStr = () =>
    new Date().toLocaleTimeString("ko-KR", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });

  const formatAutoProductionCountdown = (seconds: number) => {
    return compactSeconds(Math.max(0, Math.floor(seconds || 0)));
  };

  const syncAutoProductionState = useCallback(async () => {
    const state = await oneclickApi.getAutoProduction();
    setAutoProductionEnabled(Boolean(state.enabled));
    setAutoProductionRemaining(Math.max(0, Number(state.remaining_seconds || 0)));
  }, []);

  const syncSafetyState = useCallback(async () => {
    const state = await oneclickApi.getSafety();
    setSafetyStatus(state.status || "ok");
    const last = state.last_event;
    if (last?.message) {
      setSafetyMessage(last.message);
    } else {
      const running = state.running?.[0];
      const stale = Number((running?.safety as any)?.stale_seconds || 0);
      setSafetyMessage(stale > 0 ? `감시 중 · 정체 ${compactSeconds(stale)}` : "감시 정상");
    }
  }, []);

  useEffect(() => {
    void syncAutoProductionState().catch(() => {});
    void syncSafetyState().catch(() => {});
  }, [syncAutoProductionState, syncSafetyState]);

  useEffect(() => {
    const id = setInterval(() => {
      setAutoProductionRemaining((prev) => {
        const next = Math.max(0, prev - 1);
        if (next === 0) setAutoProductionEnabled(true);
        return next;
      });
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const handleToggleAutoProduction = async () => {
    if (autoProductionSaving) return;
    setAutoProductionSaving(true);
    try {
      const state = await oneclickApi.setAutoProduction(!autoProductionEnabled);
      setAutoProductionEnabled(Boolean(state.enabled));
      setAutoProductionRemaining(Math.max(0, Number(state.remaining_seconds || 0)));
      addLog(
        state.enabled
          ? "[시스템] 자동제작 켜기"
          : "[시스템] 자동제작 끄기 — 30분 후 자동으로 켜집니다",
        state.enabled ? "success" : "warn",
      );
    } catch (e: any) {
      addLog(`[오류] 자동제작 설정 실패: ${e?.message || e}`, "error");
    } finally {
      setAutoProductionSaving(false);
    }
  };

  const addLog = useCallback(
    (msg: string, level: LogEntry["level"] = "info") => {
      setLogs((prev) => [...prev.slice(-200), { time: timeStr(), msg, level }]);
    },
    [],
  );

  const replaceLogsFromTask = useCallback(
    (nextTask: OneClickTask | null, fallback: LogEntry[] = []) => {
      const restored = taskLogsToEntries(nextTask);
      selectedTaskIdRef.current = nextTask?.task_id || null;
      serverLogCountRef.current = nextTask?.logs?.length || 0;
      setLogs(restored.length > 0 ? restored : fallback);
    },
    [],
  );

  const syncLogsFromTask = useCallback(
    (nextTask: OneClickTask | null) => {
      if (!nextTask) {
        selectedTaskIdRef.current = null;
        serverLogCountRef.current = 0;
        return;
      }

      const serverLogs = nextTask.logs || [];
      if (
        selectedTaskIdRef.current !== nextTask.task_id ||
        serverLogs.length < serverLogCountRef.current
      ) {
        replaceLogsFromTask(nextTask);
        return;
      }

      if (serverLogs.length === serverLogCountRef.current) return;

      const newEntries = serverLogs
        .slice(serverLogCountRef.current)
        .filter((log) => !isConsoleProgressLog(log))
        .map(serverLogToEntry);
      serverLogCountRef.current = serverLogs.length;
      setLogs((prev) => [...prev, ...newEntries].slice(-200));
    },
    [replaceLogsFromTask],
  );

  const markServerSync = useCallback(() => {
    setLastServerSyncAt(Date.now());
  }, []);

  const maybeReloadAfterVerifiedUpload = useCallback((nextTask: OneClickTask | null) => {
    if (!nextTask || uploadVerifiedReloadRef.current) return;
    if (nextTask.status !== "completed") return;
    const step7Done = (nextTask.step_states || {})["7"] === "completed";

    const youtubeUrl = String((nextTask as any).youtube_url || "").trim();
    const uploadVerified = Boolean(youtubeUrl) || (nextTask.logs || []).some((log) =>
      /유튜브 업로드 완료|유튜브 수동 업로드 완료|YouTube verified|YouTube Shorts uploaded|YouTube Shorts uploaded count|업로드 확인 완료/i.test(
        String(log?.msg || ""),
      ),
    );
    if (!step7Done && !uploadVerified) return;

    const reloadKey = `oneclick-upload-verified-reload:${nextTask.task_id}:${nextTask.finished_at || nextTask.project_id}`;
    if (typeof window !== "undefined" && window.sessionStorage.getItem(reloadKey)) return;
    uploadVerifiedReloadRef.current = true;
    if (typeof window !== "undefined") {
      window.sessionStorage.setItem(reloadKey, "1");
      window.setTimeout(() => window.location.reload(), 1200);
    }
  }, []);

  const maybeReloadOnAutoTaskSwitch = useCallback(
    (runningTaskId: string | undefined | null) => {
      const currentTask = taskRef.current;
      const currentTaskId = currentTask?.task_id;
      if (!currentTask || !currentTaskId || !runningTaskId || runningTaskId === currentTaskId) return false;
      const states = currentTask.step_states || {};
      const episodeDone =
        currentTask.status === "completed" ||
        ["2", "3", "4", "5", "6", "7"].every((key) => states[key] === "completed");
      if (!episodeDone) return false;
      if (typeof window === "undefined") return false;

      const reloadKey = `oneclick-auto-task-switch:${currentTaskId}->${runningTaskId}`;
      if (window.sessionStorage.getItem(reloadKey)) return true;
      window.sessionStorage.setItem(reloadKey, "1");
      window.setTimeout(() => window.location.reload(), 250);
      return true;
    },
    [],
  );

  const activeQueueTaskId = useCallback(() => {
    const currentTask = taskRef.current;
    if (!currentTask || !["prepared", "queued", "running"].includes(currentTask.status)) return null;
    return currentTask.task_id;
  }, []);

  const isQueueItemLocked = useCallback(
    (item: OneClickQueueItem) => {
      const activeTaskId = activeQueueTaskId();
      return (
        String(item.status || "").toLowerCase() === "running" ||
        Boolean(activeTaskId && item.task_id === activeTaskId)
      );
    },
    [activeQueueTaskId],
  );

  useEffect(() => {
    setSelectedQueueIds((prev) => {
      if (prev.size === 0) return prev;
      const visible = new Set(
        pendingQueueItems.flatMap((item, index) =>
          isQueueItemLocked(item) ? [] : [queueItemKey(item, index)],
        ),
      );
      const next = new Set(Array.from(prev).filter((id) => visible.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [isQueueItemLocked, pendingQueueItems]);

  useEffect(() => {
    let cancelled = false;
    const topItem = pendingQueueItems[0] || null;
    const sourceProjectId =
      topItem?.template_project_id ||
      topItem?.source_project_id ||
      topItem?.project_id ||
      null;

    if (!sourceProjectId) {
      setPreviewModelConfig(null);
      return;
    }

    projectsApi
      .get(sourceProjectId)
      .then((project) => {
        if (!cancelled) setPreviewModelConfig(project.config || null);
      })
      .catch(() => {
        if (!cancelled) setPreviewModelConfig(null);
      });

    return () => {
      cancelled = true;
    };
  }, [
    pendingQueueItems[0]?.template_project_id,
    pendingQueueItems[0]?.source_project_id,
    pendingQueueItems[0]?.project_id,
  ]);

  const resolveLiveTask = useCallback(
    async (candidate: OneClickTask): Promise<OneClickTask> => {
      try {
        const fresh = await oneclickApi.get(candidate.task_id);
        markServerSync();
        if (fresh.task_id !== task?.task_id) {
          setTask(fresh);
          syncLogsFromTask(fresh);
        }
        return fresh;
      } catch (err: any) {
        const msg = String(err?.message || err || "").toLowerCase();
        const isMissing = msg.includes("task not found") || msg.includes("404");
        if (!isMissing || !candidate.project_id) throw err;
      }

      const { tasks } = await oneclickApi.list();
      markServerSync();
      const replacement = (tasks || []).find(
        (t) => t.project_id === candidate.project_id,
      );
      if (!replacement) {
        throw new Error("task not found and no recovered task for this project");
      }
      setTask(replacement);
      syncLogsFromTask(replacement);
      if (replacement.task_id !== candidate.task_id) {
        addLog(
          `[시스템] 서버 재시작 후 작업 ID 재연결: ${candidate.task_id} -> ${replacement.task_id}`,
          "warn",
        );
      }
      return replacement;
    },
    [addLog, markServerSync, syncLogsFromTask, task?.task_id],
  );

  const refreshLiveSnapshot = useCallback(
    async (mode: "initial" | "manual" | "silent" = "silent"): Promise<OneClickTask | null> => {
      const [queueState, runningState] = await Promise.all([
        oneclickApi.getQueue(),
        oneclickApi.getRunning(),
      ]);
      void syncSafetyState().catch(() => {});
      markServerSync();
      const queueItems = queueState.items || [];
      setPendingQueueItems(queueItems);
      setQueueChannelTimes(normalizeQueueChannelTimes(queueState.channel_times));

      const running = runningState.running;
      if (!running?.task_id) {
        setActiveTasks([]);
        const selectedTask = taskRef.current;
        if (selectedTask && ["failed", "cancelled", "paused", "prepared", "queued"].includes(selectedTask.status)) {
          return selectedTask;
        }
        const topQueueItem = queueItems[0] || null;
        if (topQueueItem?.id) {
          try {
            const recovered = await oneclickApi.recoverExistingQueueItem(topQueueItem.id);
            markServerSync();
            if (recovered.queue) {
              setPendingQueueItems(recovered.queue.items || []);
              setQueueChannelTimes(normalizeQueueChannelTimes(recovered.queue.channel_times));
            }
            if (recovered.task) {
              setTask(recovered.task);
              replaceLogsFromTask(recovered.task, [
                {
                  time: timeStr(),
                  msg: `[시스템] 기존 진행 자료 불러오기: ${recovered.task.topic}`,
                  level: "info",
                },
              ]);
              setPollFails(0);
              setStalled(false);
              return recovered.task;
            }
          } catch (e: any) {
            const message = String(e?.message || e || "");
            const routeMissing =
              message.toLowerCase().includes("not found") ||
              message.includes("404");
            if (mode === "manual" && !routeMissing) {
              addLog(`[오류] 기존 자료 불러오기 실패: ${e?.message || e}`, "error");
            }
          }
        }
        setTask(null);
        selectedTaskIdRef.current = null;
        serverLogCountRef.current = 0;
        if (mode === "initial") {
          setLogs([
            {
              time: timeStr(),
              msg: "[시스템] 현재 진행 중인 태스크가 없습니다.",
              level: "muted",
            },
          ]);
        } else if (mode === "manual") {
          addLog("[시스템] 활성 태스크 없음", "muted");
        }
        return null;
      }

      const active = await oneclickApi.get(running.task_id);
      markServerSync();
      if (maybeReloadOnAutoTaskSwitch(active.task_id)) {
        return active;
      }
      setActiveTasks([active]);
      setTask(active);
      replaceLogsFromTask(active, [
        {
          time: timeStr(),
          msg:
            mode === "manual"
              ? `[시스템] 태스크 재연결: ${active.topic} (${Math.round(active.progress_pct)}%)`
              : `[시스템] 활성 태스크 감지: ${active.topic}`,
          level: "info",
        },
      ]);
      lastPctValueRef.current = taskProgressHeartbeat(active);
      lastPctChangeRef.current = Date.now();
      setPollFails(0);
      setStalled(false);
      return active;
    },
    [activeQueueTaskId, addLog, markServerSync, maybeReloadOnAutoTaskSwitch, replaceLogsFromTask, syncSafetyState],
  );

  // ─── 초기 로드: 페이지 열 때 (또는 다시 돌아올 때) 실행 중 태스크 자동 복구 ───
  useEffect(() => {
    let cancelled = false;
    refreshLiveSnapshot("initial")
      .catch((e: any) => {
        if (cancelled) return;
        setTask(null);
        selectedTaskIdRef.current = null;
        serverLogCountRef.current = 0;
        addLog(`[오류] 실행 상태 로드 실패: ${e?.message || e}`, "error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [addLog, refreshLiveSnapshot]);

  useEffect(() => {
    const current = task;
    if (!current) return;
    const states = current.step_states || {};
    const episodeDone =
      current.status === "completed" ||
      ["2", "3", "4", "5", "6", "7"].every((key) => states[key] === "completed");
    if (!episodeDone) return;

    let cancelled = false;
    const watchNextTask = async () => {
      try {
        const runningState = await oneclickApi.getRunning();
        if (cancelled) return;
        if (runningState.running?.task_id && runningState.running.task_id !== current.task_id) {
          maybeReloadOnAutoTaskSwitch(runningState.running.task_id);
        }
      } catch {
        // 단일 태스크 폴링에서 네트워크 상태를 이미 표시한다.
      }
    };
    void watchNextTask();
    const id = setInterval(watchNextTask, 2000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [
    task?.task_id,
    task?.status,
    task?.finished_at,
    task?.step_states,
    maybeReloadOnAutoTaskSwitch,
  ]);

  // ─── 폴링 + 로그 자동 생성 + 멈춤/에러 감지 ─────────────────────
  const prevStepRef = useRef<string | null>(null);
  const prevPctRef = useRef<number>(0);
  useEffect(() => {
    if (!task) return;
    const done = ["completed", "failed", "cancelled"].includes(task.status);
    if (done) {
      syncLogsFromTask(task);
      maybeReloadAfterVerifiedUpload(task);
      if ((task.logs?.length || 0) > 0) {
        return;
      }
      if (task.status === "completed") {
        addLog(`[완료] ${task.topic} — 제작 완료!`, "success");
        if (task.estimate?.estimated_cost_krw) {
          addLog(
            `[비용] 실제 예상 비용: ${formatKrw(task.estimate.estimated_cost_krw)}`,
            "info",
          );
        }
      } else if (task.status === "failed") {
        addLog(`[실패] ${task.topic}`, "error");
        if (task.error) {
          addLog(`[오류 원인] ${task.error}`, "error");
        }
      } else {
        addLog(`[취소됨] 사용자에 의해 제작 중단`, "warn");
      }
      return;
    }
    let inFlight = false;
    pollRef.current = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const fresh = await resolveLiveTask(task);
        markServerSync();
        void syncSafetyState().catch(() => {});
        setPollFails(0); // 성공하면 리셋

        syncLogsFromTask(fresh);
        const hasServerLogs = (fresh.logs?.length || 0) > 0;

        if (!hasServerLogs) {
        // 단계 변경 감지
        if (
          fresh.current_step_name &&
          fresh.current_step_name !== prevStepRef.current
        ) {
          if (prevStepRef.current) {
            addLog(`[${prevStepRef.current}] 완료`, "success");
          }
          addLog(`[${fresh.current_step_name}] 시작...`, "info");
          prevStepRef.current = fresh.current_step_name;
        }

        // 진행률 10% 단위 로그
        const newPct = Math.round(fresh.progress_pct);
        if (newPct - prevPctRef.current >= 10) {
          addLog(
            `[진행] ${fresh.current_step_name || "처리"} — ${newPct}%`,
            "warn",
          );
          prevPctRef.current = newPct;
        }

        // 컷 진행 로그
        if (
          fresh.current_step_completed !== undefined &&
          fresh.current_step_total
        ) {
          const label =
            fresh.current_step_label || fresh.current_step_name || "";
          if (
            fresh.current_step_completed > 0 &&
            fresh.current_step_completed !== (task.current_step_completed ?? 0)
          ) {
            addLog(
              `[${label}] ${fresh.current_step_completed}/${fresh.current_step_total} 컷`,
              "info",
            );
          }
        }
        }

        // v2.1.2: 서버 측 제작 로그 (task.logs) 를 프론트 로그에 합류
        if (fresh.logs && fresh.logs.length > 0) {
          const serverLogs = fresh.logs;
          const lastSynced = serverLogCountRef.current;
          if (serverLogs.length > lastSynced) {
            const newEntries = serverLogs.slice(lastSynced);
            for (const sl of newEntries) {
              if (isConsoleProgressLog(sl)) continue;
              const lvl: LogEntry["level"] =
                sl.level === "error" ? "error" :
                sl.level === "warn" ? "warn" : "info";
              addLog(`[서버] ${sl.msg}`, lvl);
            }
            serverLogCountRef.current = serverLogs.length;
          }
        }

        // 멈춤 감지: 진행률이 90초 이상 변하지 않으면 경고,
        // 180초 이상이면 ComfyUI 큐 자동 리셋 (한 stall 라운드에 1회).
        const heartbeat = taskProgressHeartbeat(fresh);
        if (heartbeat !== lastPctValueRef.current) {
          lastPctValueRef.current = heartbeat;
          lastPctChangeRef.current = Date.now();
          setStalled(false);
          autoResetFiredRef.current = false;
        } else {
          const elapsed = Date.now() - lastPctChangeRef.current;
          if (elapsed > 90000 && !stalled) {
            addLog(
              `[경고] 90초 이상 진행률 변화 없음 — 처리가 지연되고 있을 수 있습니다`,
              "warn",
            );
            setStalled(true);
          }
          // v1.2.27: 3분 이상 변화 없음 → ComfyUI 큐 리셋 자동 호출 (한 번만).
          // ComfyUI 서버가 응답 못 주는 상황에서 현재 prompt interrupt + queue clear
          // 를 시도해 wait_for 폴링 루프가 에러로 빠져 다음 컷으로 넘어가게 한다.
          // 외부 API 만 쓰는 경우 COMFYUI_BASE_URL 미설정이라 no-op 로 조용히 지나감.
          const canResetComfyui =
            fresh.current_step === 4 ||
            fresh.current_step === 5 ||
            fresh.current_step_name?.includes("이미지") ||
            fresh.current_step_name?.includes("영상");
          if (elapsed > 180000 && !autoResetFiredRef.current && canResetComfyui) {
            autoResetFiredRef.current = true;
            addLog(
              `[자동복구] 3분 이상 진행 없음 — ComfyUI 큐 리셋 시도`,
              "warn",
            );
            (async () => {
              try {
                const rr = await oneclickApi.comfyuiReset();
                addLog(
                  `[자동복구] 결과: interrupt=${rr.comfyui_interrupt} clear=${rr.comfyui_queue_cleared}`,
                  "info",
                );
                if (rr.errors?.length) {
                  for (const e of rr.errors)
                    addLog(`[자동복구 경고] ${e}`, "warn");
                }
              } catch (e: any) {
                addLog(`[자동복구 실패] ${e?.message || e}`, "error");
              }
            })();
          }
        }

        setTask(fresh);
        setActiveTasks((prev) => {
          if (!["prepared", "queued", "running"].includes(fresh.status)) {
            return prev.filter((item) => item.task_id !== fresh.task_id);
          }
          if (!prev.some((item) => item.task_id === fresh.task_id)) {
            return [fresh];
          }
          return prev.map((item) => (item.task_id === fresh.task_id ? fresh : item));
        });
        maybeReloadAfterVerifiedUpload(fresh);
      } catch {
        setPollFails((prev) => {
          const next = prev + 1;
          if (next === 3) {
            addLog(
              "[경고] 서버 응답 없음 — 백엔드 연결 확인 필요 (작업은 서버에서 계속 진행 중)",
              "error",
            );
          }
          return next;
        });
      } finally {
        inFlight = false;
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [task, addLog, stalled, markServerSync, syncLogsFromTask, resolveLiveTask, maybeReloadAfterVerifiedUpload, syncSafetyState]);

  // 로그 자동 스크롤
  useEffect(() => {
    const el = logScrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs, task?.sub_status, task?.current_step_completed, task?.progress_pct]);

  const handleCancel = async () => {
    if (!task) return;
    const target = task;
    const optimistic: OneClickTask = {
      ...target,
      status: "cancelled",
      error: target.error || "사용자 취소",
      finished_at: target.finished_at || new Date().toISOString(),
    };
    setTask(optimistic);
    setActiveTasks((prev) => prev.filter((item) => item.task_id !== target.task_id));
    syncLogsFromTask(optimistic);
    addLog("[중단] 사용자 중단 요청 전송", "warn");
    try {
      const liveTask = await resolveLiveTask(target).catch(() => target);
      const t = await oneclickApi.cancel(liveTask.task_id);
      markServerSync();
      setTask(t);
      setActiveTasks((prev) => prev.filter((item) => item.task_id !== t.task_id));
      syncLogsFromTask(t);
    } catch (e: any) {
      addLog(`[오류] 중단 요청 실패: ${e?.message || e}`, "error");
    }
  };

  // v1.1.70: 전체 비상 정지 — Python asyncio + Redis cancel + ComfyUI /interrupt + /queue clear
  // v1.2.27: try/finally + 8초 페일세이프 — 백엔드가 응답 지연하더라도 버튼이
  // "중단 중..." 으로 고착되지 않도록. 서버 응답이 돌아오면 즉시 풀리고,
  // 최악의 경우에도 8초 후엔 버튼이 다시 활성화된다.
  const [emergencyStopping, setEmergencyStopping] = useState(false);
  const handleEmergencyStop = async () => {
    if (
      !confirm(
        "서버에서 실행/대기 중인 모든 작업을 강제 중단합니다.\n" +
          "ComfyUI 에 남아있는 현재 prompt + 대기 큐도 함께 비웁니다.\n" +
          "생성된 파일은 삭제되지 않습니다. 계속하시겠습니까?",
      )
    )
      return;
    setEmergencyStopping(true);
    // 페일세이프: 어떤 이유로 await 가 풀리지 않아도 8초 후엔 버튼 원상복귀.
    const safety = setTimeout(() => setEmergencyStopping(false), 8000);
    try {
      const r = await oneclickApi.emergencyStop();
      markServerSync();
      addLog(
        `[비상 정지] 태스크 ${r.stopped_count}건 중단 · ComfyUI interrupt=${r.comfyui_interrupt} · queue clear=${r.comfyui_queue_cleared}`,
        "warn",
      );
      if (r.errors?.length) {
        for (const e of r.errors) addLog(`[비상 정지 경고] ${e}`, "error");
      }
      try {
        await refreshLiveSnapshot("silent");
      } catch {}
      if (task) {
        try {
          const fresh = await resolveLiveTask(task);
          markServerSync();
          setTask(fresh);
          syncLogsFromTask(fresh);
        } catch {}
      }
    } catch (e: any) {
      addLog(`[오류] 비상 정지 실패: ${e?.message || e}`, "error");
    } finally {
      clearTimeout(safety);
      setEmergencyStopping(false);
    }
  };

  // v1.1.52: 특정 단계 생성물 삭제
  const [clearing, setClearing] = useState<number | null>(null);
  const handleClearStep = async (step: number, label: string) => {
    if (!task) return;
    if (!confirm(`${label} 생성물을 모두 삭제합니다. 계속하시겠습니까?`)) return;
    setClearing(step);
    try {
      const liveTask = await resolveLiveTask(task);
      const result = await oneclickApi.clearStep(liveTask.task_id, step);
      markServerSync();
      addLog(`[시스템] ${label} 초기화 완료 — ${result.deleted_files}개 파일 삭제`, "warn");
      // 태스크 새로고침
      const fresh = await oneclickApi.get(liveTask.task_id);
      markServerSync();
      setTask(fresh);
      syncLogsFromTask(fresh);
    } catch (e: any) {
      addLog(`[오류] ${label} 초기화 실패: ${e?.message || e}`, "error");
    }
    setClearing(null);
  };

  // v1.1.49: 실패/취소된 태스크를 실패 지점부터 이어서 하기
  const [resuming, setResuming] = useState(false);
  const [startingCurrent, setStartingCurrent] = useState(false);
  const handleResume = async () => {
    if (!task) return;
    setResuming(true);
    try {
      const liveTask = await resolveLiveTask(task);
      const t = await oneclickApi.resume(liveTask.task_id);
      markServerSync();
      setTask(t);
      syncLogsFromTask(t);
      addLog(`[시스템] 이어서 하기 시작: ${task.topic}`, "info");
      setPollFails(0);
      setStalled(false);
    } catch (e: any) {
      addLog(`[오류] 이어서 하기 실패: ${e?.message || e}`, "error");
    }
    setResuming(false);
  };

  // v1.1.53: 전체 초기화
  const [resetting, setResetting] = useState(false);
  const handleReset = async (fromStep: number = 2) => {
    if (!task) return;
    const stepLabel = fromStep === 2 ? "전체 (대본부터)" : fromStep === 3 ? "음성부터" : `Step ${fromStep}부터`;
    if (!confirm(`${stepLabel} 초기화합니다. 모든 생성물이 삭제됩니다. 계속하시겠습니까?`)) return;
    setResetting(true);
    try {
      const liveTask = await resolveLiveTask(task);
      const result = await oneclickApi.resetTask(liveTask.task_id, fromStep);
      markServerSync();
      addLog(`[시스템] 초기화 완료 (${stepLabel}) — ${result.deleted_files}개 파일 삭제`, "warn");
      const fresh = await oneclickApi.get(liveTask.task_id);
      markServerSync();
      setTask(fresh);
      syncLogsFromTask(fresh);
    } catch (e: any) {
      addLog(`[오류] 초기화 실패: ${e?.message || e}`, "error");
    }
    setResetting(false);
  };

  // 새로고침 (활성 태스크 다시 찾기)
  const handleRefresh = async () => {
    setLoading(true);
    try {
      await refreshLiveSnapshot("manual");
    } catch (e: any) {
      addLog(`[오류] 재연결 실패: ${e?.message || e}`, "error");
    }
    setLoading(false);
  };

  const moveQueueItem = async (itemId: string | undefined, direction: "up" | "down" | "top") => {
    if (!itemId || movingQueueId) return;
    setMovingQueueId(itemId);
    try {
      const queueState = await oneclickApi.getQueue();
      const items = [...(queueState.items || [])];
      const index = items.findIndex((item) => item.id === itemId);
      if (index < 0) return;
      if (isQueueItemLocked(items[index])) {
        addLog("[시스템] 진행 중인 작업은 순서를 변경할 수 없습니다.", "warn");
        return;
      }
      const lockedCount = items.filter((item) => isQueueItemLocked(item)).length;
      let targetIndex = index;
      if (direction === "up") targetIndex = Math.max(lockedCount, index - 1);
      if (direction === "down") targetIndex = Math.min(items.length - 1, index + 1);
      if (direction === "top") targetIndex = lockedCount;
      if (targetIndex === index) return;

      const [moved] = items.splice(index, 1);
      items.splice(targetIndex, 0, moved);
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items,
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
      markServerSync();
    } catch (e: any) {
      addLog(`[오류] 대기열 순서 변경 실패: ${e?.message || e}`, "error");
    } finally {
      setMovingQueueId(null);
    }
  };

  const sortQueueItems = async (direction: "asc" | "desc") => {
    if (movingQueueId || queueBatchRunning) return;
    setQueueBatchRunning(true);
    try {
      const queueState = await oneclickApi.getQueue();
      const items = queueState.items || [];
      const now = new Date();
      const nowMinutes = now.getHours() * 60 + now.getMinutes();
      const channelSeen = new Map<number, number>();
      const lockedItems = items.filter((item) => isQueueItemLocked(item));
      const sorted = items
        .filter((item) => !isQueueItemLocked(item))
        .map((item, index) => {
          const channel = Number(item.channel || 1);
          const channelOrder = channelSeen.get(channel) || 0;
          channelSeen.set(channel, channelOrder + 1);
          return { item, index, channelOrder };
        })
        .sort((a, b) => {
          const aDelay = scheduledDelayMinutes(queueState.channel_times?.[String(a.item.channel || 1)], nowMinutes);
          const bDelay = scheduledDelayMinutes(queueState.channel_times?.[String(b.item.channel || 1)], nowMinutes);
          const timeDiff = direction === "asc" ? aDelay - bDelay : bDelay - aDelay;
          return a.channelOrder - b.channelOrder || timeDiff || a.index - b.index;
        })
        .map(({ item }) => item);
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items: [...lockedItems, ...sorted],
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
      setSelectedQueueIds(new Set());
      markServerSync();
      addLog(`[시스템] 전체 작업큐 순차 정렬: ${direction === "asc" ? "오름차순" : "내림차순"}`, "success");
    } catch (e: any) {
      addLog(`[오류] 대기열 순차 정렬 실패: ${e?.message || e}`, "error");
    } finally {
      setQueueBatchRunning(false);
    }
  };

  const deleteQueueItem = async (itemId: string | undefined, rowKey: string, title: string) => {
    if (movingQueueId || queueBatchRunning) return;
    if (!confirm(`대기열에서 삭제할까요?\n\n${title}`)) return;
    setMovingQueueId(itemId || rowKey);
    try {
      const queueState = await oneclickApi.getQueue();
      let removed = false;
      const items = (queueState.items || []).filter((item, index) => {
        if (isQueueItemLocked(item)) return true;
        const remove = Boolean((itemId && item.id === itemId) || queueItemKey(item, index) === rowKey);
        if (remove) removed = true;
        return !remove;
      });
      if (!removed) {
        addLog("[시스템] 진행 중인 작업은 삭제할 수 없습니다.", "warn");
        return;
      }
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items,
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
      setSelectedQueueIds((prev) => {
        const next = new Set(prev);
        next.delete(rowKey);
        return next;
      });
      markServerSync();
      addLog(`[시스템] 대기열 삭제: ${title}`, "warn");
    } catch (e: any) {
      addLog(`[오류] 대기열 삭제 실패: ${e?.message || e}`, "error");
    } finally {
      setMovingQueueId(null);
    }
  };

  const deleteQueueItems = async (orderedKeys: string[]) => {
    const keys = Array.from(new Set(orderedKeys.filter(Boolean)));
    if (keys.length === 0 || movingQueueId || queueBatchRunning) return;
    if (!confirm(`선택한 대기 작업 ${keys.length}건을 삭제할까요?`)) return;
    setQueueBatchRunning(true);
    try {
      const queueState = await oneclickApi.getQueue();
      const keySet = new Set(keys);
      const currentItems = queueState.items || [];
      const removedTitles: string[] = [];
      const items = currentItems.filter((item, index) => {
        if (isQueueItemLocked(item)) return true;
        const key = queueItemKey(item, index);
        const remove = keySet.has(key);
        if (remove) removedTitles.push(queueTitle(item));
        return !remove;
      });
      if (removedTitles.length === 0) {
        addLog("[오류] 선택한 대기 작업을 서버 큐에서 찾지 못했습니다.", "error");
        return;
      }
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items,
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
      setSelectedQueueIds((prev) => {
        const next = new Set(prev);
        keys.forEach((key) => next.delete(key));
        return next;
      });
      markServerSync();
      addLog(`[시스템] 대기열 선택 삭제: ${removedTitles.length}건`, "warn");
    } catch (e: any) {
      addLog(`[오류] 대기열 선택 삭제 실패: ${e?.message || e}`, "error");
    } finally {
      setQueueBatchRunning(false);
    }
  };

  const promoteQueueItemsToNext = async (orderedKeys: string[]) => {
    const keys = Array.from(new Set(orderedKeys.filter(Boolean)));
    if (keys.length === 0 || queueBatchRunning) return;
    setQueueBatchRunning(true);
    try {
      const queueState = await oneclickApi.getQueue();
      markServerSync();
      const currentItems = queueState.items || [];
      const keyToOrder = new Map(keys.map((key, index) => [key, index]));
      const lockedItems = currentItems.filter((item) => isQueueItemLocked(item));
      const selected: OneClickQueueItem[] = [];
      const remaining: OneClickQueueItem[] = [];
      currentItems.forEach((item, index) => {
        if (isQueueItemLocked(item)) return;
        const key = queueItemKey(item, index);
        if (keyToOrder.has(key)) selected.push(item);
        else remaining.push(item);
      });
      selected.sort((a, b) => {
        const ai = currentItems.indexOf(a);
        const bi = currentItems.indexOf(b);
        return (keyToOrder.get(queueItemKey(a, ai)) ?? 999999) - (keyToOrder.get(queueItemKey(b, bi)) ?? 999999);
      });
      if (selected.length === 0) {
        addLog("[오류] 선택한 대기 작업을 서버 큐에서 찾지 못했습니다.", "error");
        return;
      }

      const now = new Date().toISOString();
      const isSingleLiveNextCancel = selected.length === 1 && isLiveNextQueueItem(selected[0]);
      if (isSingleLiveNextCancel) {
        const cancelled = {
          ...selected[0],
          queued_source: "manual",
          queued_at: now,
          queued_note: "수동 대기",
        };
        const stillLiveNext: OneClickQueueItem[] = [];
        const normalRemaining: OneClickQueueItem[] = [];
        remaining.forEach((item, index) => {
          if (index === stillLiveNext.length && isLiveNextQueueItem(item)) {
            stillLiveNext.push(item);
          } else {
            normalRemaining.push(item);
          }
        });
        const updated = await oneclickApi.setQueue({
          channel_times: queueState.channel_times,
          channel_presets: queueState.channel_presets,
          items: [...lockedItems, ...stillLiveNext, cancelled, ...normalRemaining],
        });
        setPendingQueueItems(updated.items || []);
        setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
        setSelectedQueueIds(new Set());
        markServerSync();
        addLog(`[시스템] 실행순 지정 취소: ${cancelled.topic}`, "warn");
        await handleRefresh();
        return;
      }

      const promoted = selected.map((item) => ({
        ...item,
        queued_source: "manual",
        queued_at: now,
        queued_note: selected.length > 1
          ? `작업대에서 선택 ${selected.length}건 실행순 지정`
          : "작업대에서 실행순 1번 지정",
      }));
      const existingLiveNext: OneClickQueueItem[] = [];
      const normalRemaining: OneClickQueueItem[] = [];
      remaining.forEach((item, index) => {
        if (index === existingLiveNext.length && isLiveNextQueueItem(item)) {
          existingLiveNext.push(item);
        } else {
          normalRemaining.push(item);
        }
      });
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items: [...lockedItems, ...promoted, ...existingLiveNext, ...normalRemaining],
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(normalizeQueueChannelTimes(updated.channel_times));
      setSelectedQueueIds(new Set());
      addLog(`[시스템] 선택 ${promoted.length}건 실행순 지정: 1번 ${promoted[0].topic}`, "success");
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 선택 작업 실행순 지정 실패: ${e?.message || e}`, "error");
    } finally {
      setQueueBatchRunning(false);
    }
  };

  const loadRecoveryContent = async (channel: number | null = recoveryChannel) => {
    setRecoveryLoading(true);
    try {
      const [{ tasks }, orphanRes] = await Promise.all([
        oneclickApi.list(),
        oneclickApi.listOrphanProjects(channel ?? undefined),
      ]);
      markServerSync();
      const failed = (tasks || [])
        .filter((t) => ["failed", "cancelled", "paused"].includes(t.status) || isUploadRecoverableTask(t))
        .filter((t) => channel == null || Number(t.channel || 0) === channel)
        .sort(
          (a, b) => {
            const uploadDiff = Number(isUploadRecoverableTask(b)) - Number(isUploadRecoverableTask(a));
            if (uploadDiff !== 0) return uploadDiff;
            return (
              timeValue(b.finished_at || b.created_at) -
              timeValue(a.finished_at || a.created_at)
            );
          },
        );
      const completed = (tasks || [])
        .filter((t) => t.status === "completed")
        .filter((t) => channel == null || Number(t.channel || 0) === channel)
        .sort(
          (a, b) =>
            timeValue(b.finished_at || b.created_at) -
            timeValue(a.finished_at || a.created_at),
        );
      const orphans = [...(orphanRes.items || [])].sort(
        (a, b) => timeValue(b.created_at) - timeValue(a.created_at),
      );
      setFailedTasks(failed);
      setCompletedTasks(completed);
      setOrphanProjects(orphans);
      addLog(
        `[시스템] 작업기록 로드: 완료 ${completed.length}건 / 실패 ${failed.length}건 / 고아 ${orphanRes.count || 0}건`,
        completed.length || failed.length || orphanRes.count ? "warn" : "muted",
      );
    } catch (e: any) {
      addLog(`[오류] 복구 대상 로드 실패: ${e?.message || e}`, "error");
    } finally {
      setRecoveryLoading(false);
    }
  };

  const handleSelectFailedTask = (failed: OneClickTask) => {
    setTask(failed);
    replaceLogsFromTask(failed, [
      {
        time: timeStr(),
        msg: `[시스템] 실패 태스크 불러옴: ${failed.topic}`,
        level: "warn",
      },
    ]);
    lastPctValueRef.current = taskProgressHeartbeat(failed);
    lastPctChangeRef.current = Date.now();
    setStalled(false);
  };

  const handleQueueFailedTask = async (failed: OneClickTask) => {
    setRecoveringId(failed.task_id);
    try {
      const result = await oneclickApi.requeueTask(failed.task_id);
      markServerSync();
      addLog(`[시스템] 제작 큐 상단에 배치: ${taskTitle(failed)} (CH${result.channel})`, "success");
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 제작 큐 배치 실패: ${taskTitle(failed)} - ${e?.message || e}`, "error");
    } finally {
      setRecoveringId(null);
    }
  };

  const handleQueueCompletedTask = async (completed: OneClickTask) => {
    if (!confirm(`완료된 작업을 백업 후 제작 큐 상단으로 복귀합니다.\n${taskTitle(completed)}\n계속할까요?`)) return;
    setRecoveringId(completed.task_id);
    try {
      const result = await oneclickApi.requeueTask(completed.task_id);
      markServerSync();
      addLog(
        `[시스템] 완료 작업 큐 복귀: ${taskTitle(completed)} (CH${result.channel})${result.archived_path ? ` · 백업: ${result.archived_path}` : ""}`,
        "success",
      );
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 완료 작업 큐 복귀 실패: ${taskTitle(completed)} - ${e?.message || e}`, "error");
    } finally {
      setRecoveringId(null);
    }
  };

  const handleRecoverOrphan = async (projectId: string) => {
    setRecoveringId(projectId);
    try {
      const result = await oneclickApi.requeueOrphanProjects([projectId], recoveryChannel);
      markServerSync();
      const queued = result.items?.[0]?.queue_item;
      addLog(`[시스템] 고아 프로젝트를 제작 큐 상단에 배치: ${queued?.topic || projectId}`, "success");
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 고아 프로젝트 큐 배치 실패: ${e?.message || e}`, "error");
    } finally {
      setRecoveringId(null);
    }
  };

  const handleRecoveryQueueAll = async () => {
    if (recoveryBulkQueuing || recoveryBulkUploading || recoveringId) return;
    const taskTargets = [...failedTasks];
    const orphanIds = orphanProjects.map((item) => item.project_id).filter(Boolean);
    const total = taskTargets.length + orphanIds.length;
    if (total === 0) return;
    if (!confirm(`복구 대상 ${total}건을 제작 큐 상단에 순서대로 배치합니다. 계속할까요?`)) return;

    setRecoveryBulkQueuing(true);
    let ok = 0;
    let fail = 0;
    try {
      if (orphanIds.length > 0) {
        setRecoveringId("__orphans__");
        const result = await oneclickApi.requeueOrphanProjects(orphanIds, recoveryChannel);
        ok += result.requeued_count || 0;
        fail += result.errors?.length || 0;
        for (const error of result.errors || []) {
          addLog(`[오류] 고아 프로젝트 전체 복구 실패: ${error.project_id} - ${error.error}`, "error");
        }
      }

      for (const item of taskTargets.reverse()) {
        setRecoveringId(item.task_id);
        try {
          await oneclickApi.requeueTask(item.task_id);
          ok += 1;
        } catch (e: any) {
          fail += 1;
          addLog(`[오류] 태스크 전체 복구 실패: ${taskTitle(item)} - ${e?.message || e}`, "error");
        }
      }

      markServerSync();
      addLog(`[시스템] 전체 복구 완료: 성공 ${ok}건 / 실패 ${fail}건`, fail ? "warn" : "success");
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } finally {
      setRecoveringId(null);
      setRecoveryBulkQueuing(false);
    }
  };

  const handleRecoveryReupload = async (failed: OneClickTask) => {
    if (recoveryUploadingId || recoveryBulkUploading) return;
    setRecoveryUploadingId(failed.task_id);
    try {
      const result = await oneclickApi.manualUpload(failed.task_id);
      markServerSync();
      addLog(
        `[시스템] 업로드 실패 항목 재시도 완료: ${taskTitle(failed)}${result.youtube_url ? ` — ${result.youtube_url}` : ""}`,
        "success",
      );
      const fresh = await oneclickApi.get(failed.task_id);
      markServerSync();
      setTask(fresh);
      syncLogsFromTask(fresh);
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 업로드 재시도 실패: ${taskTitle(failed)} — ${e?.message || e}`, "error");
      await loadRecoveryContent(recoveryChannel);
    } finally {
      setRecoveryUploadingId(null);
    }
  };

  const handleRecoveryBulkReupload = async () => {
    if (recoveryBulkUploading || recoveryUploadingId) return;
    const targets = failedTasks.filter(isUploadRecoverableTask);
    if (targets.length === 0) return;
    if (!confirm(`업로드 실패 ${targets.length}건을 순서대로 다시 업로드합니다. 계속할까요?`)) return;
    setRecoveryBulkUploading(true);
    try {
      let ok = 0;
      for (const item of targets) {
        setRecoveryUploadingId(item.task_id);
        try {
          const result = await oneclickApi.manualUpload(item.task_id);
          ok += 1;
          addLog(
            `[시스템] 업로드 재시도 완료 (${ok}/${targets.length}): ${taskTitle(item)}${result.youtube_url ? ` — ${result.youtube_url}` : ""}`,
            "success",
          );
        } catch (e: any) {
          addLog(`[오류] 업로드 재시도 실패: ${taskTitle(item)} — ${e?.message || e}`, "error");
          break;
        }
      }
      markServerSync();
      await loadRecoveryContent(recoveryChannel);
      await handleRefresh();
    } finally {
      setRecoveryUploadingId(null);
      setRecoveryBulkUploading(false);
    }
  };

  // v1.1.65: 자동 새로고침 — 실행 중 태스크와 대기열만 가볍게 갱신한다.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      if (typeof document !== "undefined" && document.hidden) return;
      try {
        const [queueState, runningState] = await Promise.all([
          oneclickApi.getQueue(),
          oneclickApi.getRunning(),
        ]);
        if (cancelled) return;
        markServerSync();
        setPendingQueueItems(queueState.items || []);
        setQueueChannelTimes(normalizeQueueChannelTimes(queueState.channel_times));
        if (runningState.running?.task_id) {
          const activeRunningTaskId = runningState.running.task_id;
          if (task?.task_id !== activeRunningTaskId) {
            if (maybeReloadOnAutoTaskSwitch(activeRunningTaskId)) return;
            const active = await oneclickApi.get(activeRunningTaskId);
            if (cancelled) return;
            setTask(active);
            setActiveTasks([active]);
            syncLogsFromTask(active);
            lastPctValueRef.current = taskProgressHeartbeat(active);
            lastPctChangeRef.current = Date.now();
            setStalled(false);
            autoResetFiredRef.current = false;
          } else {
            setActiveTasks([task]);
          }
        } else {
          setActiveTasks([]);
        }
      } catch {
        // 네트워크 실패는 단일-task 폴링 쪽에서 이미 감지/로그. 여기선 조용히 무시.
      }
    };
    const id = setInterval(tick, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeQueueTaskId, markServerSync, syncLogsFromTask, task, maybeReloadOnAutoTaskSwitch]);

  const isRunning =
    task && ["prepared", "queued", "running"].includes(task.status);
  const isFailed = task?.status === "failed" || task?.status === "cancelled" || task?.status === "paused";
  const isFinished = task && ["completed", "failed", "cancelled", "paused"].includes(task.status);

  // v1.1.55: 스텝별 재실행
  const [rerunningStep, setRerunningStep] = useState<number | null>(null);
  const handleRerunFromStep = async (fromStep: number) => {
    if (!task || rerunningStep !== null) return;
    const stepLabel = STEPS.find((s) => s.key === String(fromStep))?.label || `Step ${fromStep}`;
    if (!confirm(`"${stepLabel}" 단계부터 재실행합니다. 이후 단계 데이터가 초기화됩니다.`)) return;
    setRerunningStep(fromStep);
    try {
      const liveTask = await resolveLiveTask(task);
      await oneclickApi.resetTask(liveTask.task_id, fromStep);
      markServerSync();
      addLog(`[시스템] ${stepLabel} 부터 초기화 완료 — 재실행 시작`, "info");
      const resumed = await oneclickApi.resume(liveTask.task_id);
      markServerSync();
      setTask(resumed);
      syncLogsFromTask(resumed);
      addLog(`[시스템] 재실행 시작`, "success");
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 재실행 실패: ${e?.message || e}`, "error");
    } finally {
      setRerunningStep(null);
    }
  };
  const [uploadingStep, setUploadingStep] = useState(false);
  const handleReupload = async () => {
    if (!task || uploadingStep) return;
    if (!confirm("현재 최종 영상으로 YouTube 업로드를 다시 실행합니다. 계속하시겠습니까?")) return;
    setUploadingStep(true);
    try {
      const liveTask = await resolveLiveTask(task);
      const result = await oneclickApi.manualUpload(liveTask.task_id);
      markServerSync();
      addLog(
        `[시스템] 유튜브 업로드 완료${result.youtube_url ? ` — ${result.youtube_url}` : ""}`,
        "success",
      );
      const fresh = await oneclickApi.get(liveTask.task_id);
      markServerSync();
      setTask(fresh);
      syncLogsFromTask(fresh);
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 재업로드 실패: ${e?.message || e}`, "error");
    } finally {
      setUploadingStep(false);
    }
  };
  const runningDisplayTask = activeTasks.find((item) => item.status === "running") || null;
  const displaySourceTask =
    task && runningDisplayTask?.task_id === task.task_id
      ? task
      : runningDisplayTask || task;
  const displayTask = getEffectiveTask(displaySourceTask);
  const isCompleted = displayTask?.status === "completed";
  const pct = isCompleted ? 100 : Math.round(displayTask?.progress_pct || 0);
  const activeStepKey = displayTask?.current_step ? String(displayTask.current_step) : inferLiveStepKey(displayTask);
  const activeStepLabel =
    (activeStepKey && STEPS.find((step) => step.key === activeStepKey)?.label) ||
    displayTask?.current_step_name ||
    "대기";
  const activeStartedSec =
    displayTask?.started_at && displayTask?.status === "running"
      ? Math.max(0, Math.floor((Date.now() - new Date(displayTask.started_at).getTime()) / 1000))
      : 0;
  const activeApiName = activeStepKey ? stepApiName(activeStepKey, displayTask) : "-";
  const activeModelName = activeStepKey ? stepModelName(activeStepKey, displayTask) : "-";
  const activeTargetText = activeStepKey ? stepTargetText(activeStepKey, displayTask) : "0 / 0";
  const failureLogEntry =
    isFailed && task?.error
      ? {
          time: task.finished_at
            ? new Date(task.finished_at).toLocaleTimeString("ko-KR", {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
              })
            : timeStr(),
          msg: `[제작 실패] ${getTaskFailureStepName(task)}: ${task.error}`,
          level: "error" as const,
        }
      : null;
  const compactLogRows = (
    failureLogEntry && !logs.some((log) => log.msg.includes(String(task?.error || "")))
      ? [...logs, failureLogEntry]
      : logs
  ).filter((log) => !isConsoleProgressLog(log));
  const previewQueueItem = pendingQueueItems[0] || null;
  const previewStageModels = {
    script: previewModelConfig?.script_model || "",
    tts: previewModelConfig?.tts_model || "",
    tts_voice: previewModelConfig?.tts_voice_id || "",
    image: previewModelConfig?.image_model || "",
    video: previewModelConfig?.video_model || "",
    thumbnail: previewModelConfig?.thumbnail_model || "",
  };
  const mergedStageModels = {
    script: displayTask?.models?.script || previewStageModels.script,
    tts: displayTask?.models?.tts || previewStageModels.tts,
    tts_voice: displayTask?.models?.tts_voice || previewStageModels.tts_voice,
    image: displayTask?.models?.image || previewStageModels.image,
    video: displayTask?.models?.video || previewStageModels.video,
    thumbnail: displayTask?.models?.thumbnail || previewStageModels.thumbnail,
  };
  const stageModelTask = (displayTask
    ? {
        ...displayTask,
        models: mergedStageModels,
        estimate: {
          ...displayTask.estimate,
          models_used: {
            ...(displayTask.estimate?.models_used || {}),
            script: displayTask.estimate?.models_used?.script || mergedStageModels.script,
            tts: displayTask.estimate?.models_used?.tts || mergedStageModels.tts,
            image: displayTask.estimate?.models_used?.image || mergedStageModels.image,
            video: displayTask.estimate?.models_used?.video || mergedStageModels.video,
            thumbnail: displayTask.estimate?.models_used?.thumbnail || mergedStageModels.thumbnail,
          },
        },
      }
    : previewQueueItem
      ? ({
          models: mergedStageModels,
          estimate: { models_used: mergedStageModels },
        } as unknown as OneClickTask)
      : null) as OneClickTask | null;
  const compactStageRows = STEPS.filter((step) => ["2", "3", "4", "5", "6", "7"].includes(step.key)).map((step) => {
    const state = getStepState(displayTask, step.key);
    const isActive = activeStepKey === step.key && displayTask?.status === "running";
    const total = Math.max(1, Number(displayTask?.total_cuts || displayTask?.current_step_total || 150));
    const done = Number(displayTask?.completed_cuts_by_step?.[step.key] || 0);
    const activeCutPct =
      isActive && ["3", "4", "5"].includes(step.key)
        ? Math.max(0, Math.min(100, Number(displayTask?.current_step_cut_progress_pct || 0)))
        : 0;
    const activeCutContribution =
      isActive && activeCutPct > 0
        ? activeCutPct / Math.max(1, total)
        : 0;
    const progress =
      state === "done"
        ? 100
        : ["3", "4", "5"].includes(step.key)
          ? Math.min(100, Math.round(((done / total) * 100) + activeCutContribution))
          : isActive
            ? 34
            : 0;
    const liveText =
      isActive
        ? String(displayTask?.current_step_progress_text || displayTask?.sub_status || "").trim()
        : "";
    return {
      ...step,
      state,
      isActive,
      api: stepApiName(step.key, stageModelTask),
      model: stepModelName(step.key, stageModelTask),
      target: stepTargetText(step.key, displayTask),
      seconds: isActive ? compactSeconds(activeStartedSec) : "00:00:00",
      progress,
      liveText,
    };
  });
  const hasCurrentPanelItem = Boolean(displayTask || previewQueueItem);
  const currentPanelChannel = displayTask?.channel || previewQueueItem?.channel || 1;
  const currentPanelEpisode = displayTask?.episode_number || previewQueueItem?.episode_number || null;
  const currentPanelTitleBase = displayTask
    ? taskTitle(displayTask)
    : previewQueueItem
      ? queueTitle(previewQueueItem)
      : "";
  const currentPanelTitle = currentPanelTitleBase
    ? `CH${currentPanelChannel} ${currentPanelTitleBase}`
    : "";
  const currentPanelIsRunning = displayTask?.status === "running";
  const currentPanelCanResume =
    displayTask != null && ["failed", "cancelled", "paused"].includes(displayTask.status);
  const currentPanelCanStart =
    !currentPanelIsRunning &&
    !currentPanelCanResume &&
    Boolean(previewQueueItem || (displayTask && ["prepared", "queued"].includes(displayTask.status)));
  const currentPanelPrimaryLabel = currentPanelIsRunning
    ? "작업 중"
    : currentPanelCanResume
      ? resuming
        ? "이어서 하는 중..."
        : "이어서 하기"
      : startingCurrent
        ? "시작 중..."
        : "시작";
  const currentPanelPrimaryDisabled =
    currentPanelIsRunning ||
    resuming ||
    startingCurrent ||
    (!currentPanelCanResume && !currentPanelCanStart);
  const handleCurrentPanelPrimaryAction = async () => {
    if (currentPanelPrimaryDisabled) return;
    if (currentPanelCanResume) {
      await handleResume();
      return;
    }
    setStartingCurrent(true);
    try {
      const live = await refreshLiveSnapshot("silent");
      if (live?.status === "running") {
        addLog(`[시스템] 이미 진행 중인 작업에 연결: ${live.topic}`, "info");
        return;
      }

      let started: OneClickTask | null = null;
      if (displayTask?.task_id && ["prepared", "queued"].includes(displayTask.status)) {
        started = await oneclickApi.start(displayTask.task_id);
      } else if (previewQueueItem) {
        started = await oneclickApi.runQueueNext(currentPanelChannel);
      }
      if (started && ["prepared", "queued", "running"].includes(started.status)) {
        markServerSync();
        setTask(started);
        syncLogsFromTask(started);
        addLog(`[시스템] 시작: ${started.topic || started.title || previewQueueItem?.topic || ""}`, "success");
      }
      await new Promise((resolve) => setTimeout(resolve, 800));
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 시작 실패: ${e?.message || e}`, "error");
    } finally {
      setStartingCurrent(false);
    }
  };
  const currentPanelStatus =
    displayTask?.status === "running"
      ? "진행 중"
      : currentPanelCanResume
        ? "이어하기"
      : displayTask?.status === "failed"
        ? "실패"
        : displayTask?.status === "cancelled"
          ? "중단"
          : displayTask?.status === "paused"
            ? "정지"
            : previewQueueItem
              ? "대기"
              : "대기";
  const currentThumbnailSrc =
    displayTask?.thumbnail_status === "done" && displayTask.project_id
      ? `${assetUrl(displayTask.project_id, "output/thumbnail.png")}?v=${displayTask.finished_at || displayTask.started_at || displayTask.task_id}-${thumbnailRefreshKey}`
      : null;
  const handleOpenThumbnailPrompt = async () => {
    if (!displayTask?.task_id || thumbnailPromptLoading) return;
    setThumbnailPromptOpen(true);
    setThumbnailPromptLoading(true);
    try {
      const liveTask = await resolveLiveTask(displayTask);
      const result = await oneclickApi.getThumbnailPrompt(liveTask.task_id);
      setThumbnailPrompt(result.prompt || "");
    } catch (e: any) {
      addLog(`[오류] 썸네일 프롬프트 로드 실패: ${e?.message || e}`, "error");
    } finally {
      setThumbnailPromptLoading(false);
    }
  };
  const handleSaveThumbnailPrompt = async () => {
    if (!displayTask?.task_id || thumbnailPromptSaving) return;
    const nextPrompt = thumbnailPrompt.trim();
    if (!nextPrompt) {
      addLog("[오류] 썸네일 프롬프트가 비어 있습니다", "error");
      return;
    }
    setThumbnailPromptSaving(true);
    try {
      const liveTask = await resolveLiveTask(displayTask);
      await oneclickApi.updateThumbnailPrompt(liveTask.task_id, nextPrompt);
      addLog("[시스템] 썸네일 프롬프트 저장 완료", "success");
    } catch (e: any) {
      addLog(`[오류] 썸네일 프롬프트 저장 실패: ${e?.message || e}`, "error");
    } finally {
      setThumbnailPromptSaving(false);
    }
  };
  const handleRegenerateThumbnail = async () => {
    if (!displayTask?.task_id || thumbnailRegenerating) return;
    setThumbnailRegenerating(true);
    try {
      const liveTask = await resolveLiveTask(displayTask);
      await oneclickApi.regenerateThumbnail(liveTask.task_id);
      markServerSync();
      setThumbnailRefreshKey((key) => key + 1);
      addLog("[시스템] 썸네일 재생성 완료", "success");
      const fresh = await oneclickApi.get(liveTask.task_id);
      markServerSync();
      setTask(fresh);
      syncLogsFromTask(fresh);
    } catch (e: any) {
      addLog(`[오류] 썸네일 재생성 실패: ${e?.message || e}`, "error");
    } finally {
      setThumbnailRegenerating(false);
    }
  };
  const parsedImageCut = (() => {
    const text = `${displayTask?.current_step_progress_text || ""} ${displayTask?.sub_status || ""}`;
    const match = text.match(/컷\s+(\d+)\s*\/\s*(\d+)/);
    if (!match) return 0;
    return Math.max(0, Number(match[1]) - 1);
  })();
  const latestImageCut = Math.max(
    0,
    Number(displayTask?.completed_cuts_by_step?.["4"] || 0),
    activeStepKey === "4" ? Number(displayTask?.current_step_completed || 0) : 0,
    activeStepKey === "4" ? parsedImageCut : 0,
  );
  const latestVideoCut = Math.max(
    0,
    Number(displayTask?.completed_cuts_by_step?.["5"] || 0),
    activeStepKey === "5" ? Number(displayTask?.current_step_completed || 0) : 0,
  );
  const latestGeneratedAsset =
    displayTask?.project_id && latestVideoCut > 0
      ? {
          kind: "video" as const,
          label: `영상 cut ${String(latestVideoCut).padStart(3, "0")}`,
          src: `${assetUrl(displayTask.project_id, `videos/cut_${String(latestVideoCut).padStart(3, "0")}.mp4`)}?v=${latestVideoCut}-${displayTask.current_step_completed || 0}-${displayTask.progress_pct}`,
        }
      : displayTask?.project_id && latestImageCut > 0
        ? {
            kind: "image" as const,
            label: `이미지 cut ${latestImageCut}`,
            src: `${assetUrl(displayTask.project_id, `images/cut_${latestImageCut}.png`)}?v=${latestImageCut}-${displayTask.current_step_completed || 0}-${displayTask.progress_pct}`,
          }
        : null;
  const comfyProgress = (() => {
    if (!displayTask || activeStepKey !== "4") return null;
    const parse = (text: string) => {
      const match = text.match(/KSampler\s+(\d+)\s*\/\s*(\d+)\s*\((\d+(?:\.\d+)?)%\)/i);
      if (!match) return null;
      const current = Number(match[1]);
      const total = Number(match[2]);
      const pct = Math.max(0, Math.min(100, Number(match[3])));
      if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) return null;
      const cutMatch = text.match(/컷\s+(\d+)\s*\/\s*(\d+)/);
      return {
        current,
        total,
        pct,
        cut: cutMatch ? Number(cutMatch[1]) : null,
        cutTotal: cutMatch ? Number(cutMatch[2]) : null,
      };
    };
    const liveText = `${displayTask?.current_step_progress_text || ""} ${displayTask?.sub_status || ""}`;
    const live = parse(liveText);
    if (live) return live;
    for (const log of [...(displayTask?.logs || [])].reverse()) {
      const parsed = parse(String(log?.msg || ""));
      if (parsed) return parsed;
    }
    return null;
  })();
  const comfyAverage = (() => {
    const samples = (displayTask?.logs || [])
      .map((log) => String(log?.msg || "").match(/ComfyUI\s+실행\s+완료:\s*(\d+(?:\.\d+)?)s/i))
      .filter((match): match is RegExpMatchArray => Boolean(match))
      .map((match) => Number(match[1]))
      .filter((value) => Number.isFinite(value) && value > 0)
      .slice(-20);
    if (!samples.length) return null;
    const seconds = samples.reduce((sum, value) => sum + value, 0) / samples.length;
    return { seconds, count: samples.length };
  })();
  // 경과 시간 (실시간 카운트)
  const [elapsedStr, setElapsedStr] = useState("--:--");
  const [headerNow, setHeaderNow] = useState(timeStr());
  useEffect(() => {
    const id = setInterval(() => setHeaderNow(timeStr()), 1000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    if (!task?.started_at) {
      setElapsedStr("--:--");
      return;
    }
    const tick = () => {
      const base = task.finished_at
        ? new Date(task.finished_at).getTime()
        : Date.now();
      const diff = base - new Date(task.started_at!).getTime();
      const m = Math.floor(diff / 60000);
      const s = Math.floor((diff % 60000) / 1000);
      setElapsedStr(
        `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`,
      );
    };
    tick();
    if (task.finished_at) return; // 종료된 태스크는 고정
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [task?.started_at, task?.finished_at]);

  // 예상 잔여 시간
  const estimatedRemaining = (() => {
    if (!task?.estimate?.estimated_seconds || !task?.started_at || pct <= 0)
      return null;
    const totalEst = task.estimate.estimated_seconds;
    const elapsedMs = Date.now() - new Date(task.started_at).getTime();
    const elapsedSec = elapsedMs / 1000;
    // 진행률 기반 추정
    const estimatedTotal = pct > 0 ? elapsedSec / (pct / 100) : totalEst;
    const remaining = Math.max(0, estimatedTotal - elapsedSec);
    return Math.round(remaining);
  })();
  const serverSyncLabel = lastServerSyncAt
    ? `서버 마지막 반영 ${new Date(lastServerSyncAt).toLocaleTimeString("ko-KR", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })}`
    : "서버 동기화 대기 중";
  const serverSyncStale =
    lastServerSyncAt !== null && Date.now() - lastServerSyncAt > 10000;
  const costEstimateTask = task?.estimate ? task : activeTasks.find((item) => item.estimate) || null;
  const costEstimate = costEstimateTask?.estimate || null;
  const costBreakdown = costEstimate?.cost_breakdown;
  const costEstimateUsd = costEstimate
    ? Number(
        (
          Number(costBreakdown?.llm_script || 0) +
          Number(costBreakdown?.image_generation || 0) +
          Number(costBreakdown?.thumbnail || 0) +
          (
            costBreakdown?.tts_billable !== undefined
              ? Number(costBreakdown.tts_billable || 0)
              : costEstimateTask?.models?.tts === "elevenlabs"
                ? 0
                : Number(costBreakdown?.tts || 0)
          ) +
          Number(costBreakdown?.video || 0)
        ).toFixed(4),
      )
    : null;
  const costEstimateKrw = costEstimateUsd !== null
    ? Math.round(costEstimateUsd * Number(costEstimate?.usd_to_krw || 1360))
    : null;
  const costEstimateTitle = costEstimate
    ? [
        `편당 예상: $${Number(costEstimateUsd || 0).toFixed(2)} / ${formatKrw(costEstimateKrw ?? Number(costEstimateUsd || 0) * 1360)}`,
        `대본 $${Number(costBreakdown?.llm_script || 0).toFixed(2)}`,
        `이미지 $${Number(costBreakdown?.image_generation || 0).toFixed(2)}`,
        `썸네일 $${Number(costBreakdown?.thumbnail || 0).toFixed(2)}`,
        `음성 $${Number(costBreakdown?.tts || 0).toFixed(2)} (구독 제외)`,
        `영상 $${Number(costBreakdown?.video || 0).toFixed(2)}`,
      ].join("\n")
    : "편당 예상비 대기";

  const runningTasks = activeTasks.filter((t) => t.status === "running");
  const waitingTasks = activeTasks.filter(
    (t) => t.status === "queued" || t.status === "prepared",
  );
  const activeDisplayTasks =
    runningDisplayTask
      ? [runningDisplayTask]
      : task && ["prepared", "queued", "running"].includes(task.status)
      ? activeTasks.some((item) => item.task_id === task.task_id)
        ? activeTasks
        : [task, ...activeTasks]
      : activeTasks;

  const logColor = (level: LogEntry["level"]) => {
    switch (level) {
      case "success":
        return "text-accent-success";
      case "warn":
        return "text-amber-400";
      case "error":
        return "text-accent-danger";
      case "muted":
        return "text-gray-600";
      default:
        return "text-gray-400";
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="animate-spin text-gray-500" />
      </div>
    );
  }

  return (
    <div className="h-full w-full min-w-0 overflow-hidden p-3 sm:p-4 lg:p-5 xl:p-6 flex flex-col gap-3 lg:gap-4">
      {/* 헤더 */}
      <div className="flex flex-col gap-3 xl:gap-4 flex-shrink-0">
        <div className="grid grid-cols-1 items-center gap-2 lg:grid-cols-[minmax(300px,1fr)_auto_auto_auto_minmax(220px,260px)] lg:gap-3">
          <div className="flex flex-wrap items-center gap-2 lg:gap-3">
            <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold leading-none text-white">작업대</h1>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-lg hover:bg-bg-secondary text-gray-500 hover:text-gray-300 transition-colors"
              title="태스크 새로고침"
            >
              <RefreshCw size={16} />
            </button>
            {/* v1.1.53: 전체 초기화 — 실행 중이 아닐 때만 표시 */}
            {task && !isRunning && (
              <button
                onClick={() => handleReset(2)}
                disabled={resetting}
                className="flex items-center gap-1.5 text-[11px] sm:text-xs lg:text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 px-2 sm:px-2.5 lg:px-3 py-1.5 sm:py-2 rounded-lg transition-colors disabled:opacity-50"
                title="전체 초기화 (대본부터)"
              >
                <RotateCcw size={14} className={resetting ? "animate-spin" : ""} />
                초기화
              </button>
            )}
            {/* v1.1.70: 비상 정지 — 서버 + ComfyUI 전체 중단. 항상 표시. */}
            <button
              onClick={handleEmergencyStop}
              disabled={emergencyStopping}
              className="inline-flex h-9 min-w-[132px] items-center justify-center gap-1.5 rounded-lg border border-red-500/60 bg-red-600 px-3 text-xs font-black text-white transition-colors hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
              title="서버 + ComfyUI 의 모든 작업을 강제 중단합니다. 생성 파일은 보존."
            >
              <AlertTriangle size={14} className={emergencyStopping ? "animate-pulse" : ""} />
              {emergencyStopping ? "중단 중..." : "모든 작업 중단"}
            </button>
          </div>
          <div className="inline-flex h-9 min-w-[154px] items-center justify-center gap-2 rounded-lg border border-border bg-bg-secondary/70 px-3 text-xs font-black text-gray-200 shadow-sm">
            <span className="rounded border border-accent-primary/30 bg-accent-primary/10 px-2 py-0.5 text-accent-primary">
              v{APP_VERSION}
            </span>
            <span className="font-mono text-gray-100">{headerNow}</span>
          </div>
          <div
            className="inline-flex h-9 min-w-[178px] items-center justify-center gap-2 rounded-lg border border-sky-400/30 bg-sky-500/10 px-3 text-xs font-black text-sky-100 shadow-sm"
            title={costEstimateTitle}
          >
            <span className="text-sky-300">예상비</span>
            <span className="font-mono text-white">
              {costEstimate
                ? formatKrw(costEstimateKrw ?? Number(costEstimateUsd || 0) * 1360)
              : "-원"}
            </span>
          </div>
          <div
            className={`inline-flex h-9 min-w-[168px] max-w-[240px] items-center justify-center gap-2 rounded-lg border px-3 text-xs font-black shadow-sm ${
              safetyStatus === "alert"
                ? "border-red-400/50 bg-red-500/15 text-red-100"
                : "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
            }`}
            title={safetyMessage}
          >
            <span className={`h-2 w-2 rounded-full ${safetyStatus === "alert" ? "bg-red-400" : "bg-emerald-400"}`} />
            <span className="truncate">{safetyStatus === "alert" ? "감시 경고" : "감시 정상"}</span>
          </div>
          <div className="ml-auto flex max-w-full items-center justify-end">
            <div
              className={`inline-flex h-9 w-[260px] max-w-full items-center justify-center gap-2 rounded-lg border px-3 text-xs font-black shadow-sm ${
                autoProductionEnabled
                  ? "border-emerald-400/35 bg-emerald-500/10 text-emerald-100"
                  : "border-amber-400/45 bg-amber-500/10 text-amber-100"
              }`}
              title={autoProductionEnabled ? "자동제작 켜짐" : "자동제작 꺼짐"}
            >
              <span className={`h-2 w-2 rounded-full ${autoProductionEnabled ? "bg-emerald-400" : "bg-amber-400"}`} />
              <span>{autoProductionEnabled ? "자동제작 켜짐" : "자동제작 꺼짐"}</span>
              {!autoProductionEnabled && (
                <span className="font-mono text-xs text-amber-200">
                  {formatAutoProductionCountdown(autoProductionRemaining)}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* v1.1.67: 상단은 요약만 남기고 전체 큐/순서 변경은 팝업으로 분리한다. */}
      {(() => {
        const queueEntries = pendingQueueItems.map((item, index) => ({ kind: "queue" as const, item, index }));
        const persistedCount = pendingQueueItems.length;
        const queueChannels = collectQueueChannels(queueChannelTimes, pendingQueueItems, []);
        const channelCounts = queueEntries.reduce<Record<number, number>>((acc, entry) => {
          const ch = entry.item.channel || 1;
          acc[ch] = (acc[ch] || 0) + 1;
          return acc;
        }, {});
        const nowForQueueSort = new Date();
        const nowMinutes = nowForQueueSort.getHours() * 60 + nowForQueueSort.getMinutes();
        const channelsByNextRun = [...queueChannels].sort((a, b) => {
          const diff =
            scheduledDelayMinutes(queueChannelTimes[String(a)], nowMinutes) -
            scheduledDelayMinutes(queueChannelTimes[String(b)], nowMinutes);
          return diff || a - b;
        });
        const channelSummary = queueChannels.map((ch) => ({
          ch,
          count: channelCounts[ch] || 0,
          time: queueChannelTimeLabel(queueChannelTimes[String(ch)]),
        }));
        const allQueueEntries = pendingQueueItems.map((item, index) => ({
          item,
          index,
          cycle: index,
          dueMinutes: scheduledDelayMinutes(queueChannelTimes[String(item.channel || 1)], nowMinutes),
        }));
        const liveNextCount = pendingQueueItems.reduce((count, item) => {
          if (isQueueItemLocked(item)) return count;
          return count >= 0 && isLiveNextQueueItem(item) ? count + 1 : -1;
        }, 0);
        const visibleQueueEntries =
          queueChannelFilter == null
            ? allQueueEntries
            : allQueueEntries.filter(({ item }) => Number(item.channel || 1) === queueChannelFilter);
        const nextQueueItems = visibleQueueEntries.slice(0, 5).map(({ item }) => item);
        const editChannelEntries =
          queueEditChannel == null
            ? []
            : allQueueEntries.filter(({ item }) => Number(item.channel || 1) === queueEditChannel);
        const visibleQueueKeys = visibleQueueEntries
          .filter(({ item }) => !isQueueItemLocked(item))
          .map(({ item, index }) => queueItemKey(item, index));
        const selectedVisibleCount = visibleQueueKeys.filter((key) => selectedQueueIds.has(key)).length;
        const allVisibleSelected = visibleQueueKeys.length > 0 && selectedVisibleCount === visibleQueueKeys.length;
        const renderQueueRow = (item: OneClickQueueItem, index: number) => {
          const isMoving = movingQueueId === item.id;
          const meta = formatQueueWaitingMeta(item, queueChannelTimes);
          const rowKey = queueItemKey(item, index);
          const checked = selectedQueueIds.has(rowKey);
          const displayTitle = queueTitle(item);
          const isRunningQueueItem = isQueueItemLocked(item);
          const isWorkbenchQueueItem = !isRunningQueueItem && Boolean(item.task_id);
          const actionDisabled = queueBatchRunning || isRunningQueueItem;
          const liveNextRank = (() => {
            if (!isLiveNextQueueItem(item)) return 0;
            let rank = 0;
            for (let i = 0; i < pendingQueueItems.length; i += 1) {
              const prev = pendingQueueItems[i];
              if (isQueueItemLocked(prev)) continue;
              if (!isLiveNextQueueItem(prev)) return 0;
              rank += 1;
              if (i === index) return rank;
            }
            return 0;
          })();
          const isPromotedNext = liveNextRank > 0;
          const nextStartLabel =
            isPromotedNext && task && ["prepared", "queued", "running"].includes(task.status)
              ? liveNextRank > 1
                ? "앞 예약 완료 후"
                : estimatedRemaining
                ? new Date(Date.now() + estimatedRemaining * 1000).toLocaleTimeString("ko-KR", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "현재 작업 완료 직후"
              : "";
          return (
            <div
              key={`queue-panel-${item.id || index}`}
              className={`flex min-h-14 items-center gap-3 border-b border-border/70 px-4 py-2.5 text-base last:border-b-0 hover:bg-blue-400/5 ${
                checked ? "bg-accent-primary/10" : ""
              }`}
              title={`${item.topic} — ${meta.sourceLabel} — ${meta.scheduleLabel}`}
            >
              <input
                type="checkbox"
                checked={checked}
                disabled={isRunningQueueItem}
                onChange={(e) => {
                  if (isRunningQueueItem) return;
                  setSelectedQueueIds((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(rowKey);
                    else next.delete(rowKey);
                    return next;
                  });
                }}
                className="h-5 w-5 shrink-0 accent-accent-primary disabled:cursor-not-allowed disabled:opacity-30"
                title={isRunningQueueItem ? "진행 중인 작업은 선택할 수 없습니다" : "실행순 지정 선택"}
              />
              <span className="w-14 shrink-0 rounded bg-blue-400/15 px-2 py-1 text-center text-sm font-bold text-blue-200">
                #{index + 1}
              </span>
              <span className={`w-16 shrink-0 rounded-md border px-2.5 py-1.5 text-center text-base font-black ${channelBadgeClass(item.channel)}`}>
                CH{item.channel || 1}
              </span>
              <span className="w-16 shrink-0 rounded border border-violet-400/30 bg-violet-400/10 px-2 py-1 text-center text-sm font-bold text-violet-200">
                {formatEpisodeBadge(item)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate text-base font-bold text-blue-50">{displayTitle}</div>
                <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2 text-sm">
                  <span className={`rounded border px-2 py-1 font-semibold ${meta.sourceClass}`}>
                    {meta.sourceLabel}
                  </span>
                  <span className="rounded border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 font-semibold text-emerald-200">
                    {meta.scheduleLabel}
                  </span>
                  {isRunningQueueItem && (
                    <span className="rounded border border-red-300/40 bg-red-300/15 px-2 py-1 font-bold text-red-100">
                      진행중
                    </span>
                  )}
                  {isWorkbenchQueueItem && (
                    <span className="rounded border border-blue-300/40 bg-blue-300/15 px-2 py-1 font-bold text-blue-100">
                      작업대
                    </span>
                  )}
                  <span className="text-gray-500">{meta.queuedAt}</span>
                  {isPromotedNext && (
                    <span className="rounded border border-amber-300/40 bg-amber-300/15 px-2 py-1 font-bold text-amber-200">
                      실행순 #{liveNextRank}{nextStartLabel ? ` · 예상 ${nextStartLabel}` : ""}
                    </span>
                  )}
                  {meta.note && <span className="min-w-0 truncate text-gray-500">· {meta.note}</span>}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => {
                    if (!isRunningQueueItem) void promoteQueueItemsToNext([rowKey]);
                  }}
                  disabled={actionDisabled}
                  className={`inline-flex min-w-16 items-center justify-center gap-1.5 rounded border px-3 py-1.5 text-sm font-bold disabled:opacity-40 ${
                    isRunningQueueItem
                      ? "cursor-not-allowed border-red-300/40 bg-red-300/15 text-red-100"
                      : isPromotedNext
                      ? "border-amber-300/50 bg-amber-300/15 text-amber-200 hover:bg-amber-300/25"
                      : "border-accent-success/40 bg-accent-success/10 text-accent-success hover:bg-accent-success/20"
                  }`}
                  title={
                    isRunningQueueItem
                      ? "진행 중인 작업은 순서를 변경할 수 없습니다"
                      : isPromotedNext
                        ? "실행순 지정 취소"
                        : "이 작업을 실행순 1번으로 지정"
                  }
                >
                  {isRunningQueueItem ? <Loader2 size={14} className="animate-spin" /> : <PlayCircle size={14} />}
                  {isRunningQueueItem ? "진행중" : isPromotedNext ? "취소" : "1번 지정"}
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "top")}
                  disabled={isRunningQueueItem || isMoving || index === 0}
                  className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-sm font-semibold text-gray-300 hover:text-gray-100 disabled:opacity-30"
                  title="맨 위로"
                >
                  맨위
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "up")}
                  disabled={isRunningQueueItem || isMoving || index === 0}
                  className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-sm font-semibold text-gray-300 hover:text-gray-100 disabled:opacity-30"
                  title="한 칸 위"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "down")}
                  disabled={isRunningQueueItem || isMoving || index >= pendingQueueItems.length - 1}
                  className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-sm font-semibold text-gray-300 hover:text-gray-100 disabled:opacity-30"
                  title="한 칸 아래"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => void deleteQueueItem(item.id, rowKey, displayTitle)}
                  disabled={isRunningQueueItem || isMoving || queueBatchRunning}
                  className="inline-flex items-center justify-center rounded border border-red-400/30 bg-red-400/10 px-2.5 py-1.5 text-sm font-semibold text-red-300 hover:bg-red-400/20 disabled:opacity-30"
                  title="대기열에서 삭제"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          );
        };
        return (
          <div className="order-1 flex-shrink-0 rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-sm shadow-black/20">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Activity size={14} className="text-accent-secondary" />
                <span className="text-sm font-bold text-gray-100">작업 대기열</span>
              </div>
              <span className="rounded-md border border-border bg-bg-primary px-2.5 py-1 text-[11px] font-bold text-gray-200">
                {persistedCount}건 대기
              </span>
              {liveNextCount > 0 && (
                <span className="rounded border border-amber-300/35 bg-amber-300/10 px-2 py-0.5 text-[11px] font-bold text-amber-200">
                  실행순 지정 {liveNextCount}
                </span>
              )}
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setQueuePanelOpen(true)}
                  className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-blue-400/40 bg-blue-400/15 px-3 text-xs font-bold text-blue-100 hover:bg-blue-400/25"
                >
                  <ListChecks size={13} />
                  전체 큐/순서
                </button>
                <button
                  onClick={() => {
                    const next = !recoveryOpen;
                    setRecoveryOpen(next);
                    if (next) void loadRecoveryContent(recoveryChannel);
                  }}
                  className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/15 px-3 text-xs font-bold text-amber-200 hover:bg-amber-500/25"
                >
                  <AlertTriangle size={13} />
                  작업기록 복귀
                </button>
              </div>
            </div>
            <div className="mt-1.5 flex min-w-0 flex-wrap items-center gap-2">
              {nextQueueItems.slice(0, 5).map((item, index) => {
                const meta = formatQueueWaitingMeta(item, queueChannelTimes);
                const isRunningQueueItem =
                  String(item.status || "pending").toLowerCase() === "running" ||
                  Boolean(item.task_id && task?.task_id === item.task_id && task.status === "running");
                const isWorkbenchQueueItem = !isRunningQueueItem && Boolean(item.task_id);
                return (
                  <div
                    key={`next-queue-${item.id || index}`}
                    className="flex h-10 min-w-0 items-center gap-1.5 rounded-md border border-border bg-bg-primary/70 px-2 text-xs shadow-sm shadow-black/20"
                    title={`${item.topic} · ${meta.sourceLabel} · ${meta.scheduleLabel}`}
                  >
                    <span className="shrink-0 rounded bg-blue-400/15 px-1.5 py-0.5 text-[10px] font-black text-blue-100">
                      {isRunningQueueItem ? "진행중" : isWorkbenchQueueItem ? "작업대" : `다음 ${index + 1}`}
                    </span>
                    <button
                      type="button"
                      onClick={() => setQueueEditChannel(Number(item.channel || 1))}
                      className={`shrink-0 rounded-md border px-2.5 py-1 text-sm font-black transition-transform hover:scale-[1.03] ${channelBadgeClass(item.channel)}`}
                      title={`CH${item.channel || 1} 대기열 편집`}
                    >
                      CH{item.channel || 1}
                    </button>
                    <span className="shrink-0 rounded border border-violet-400/40 bg-violet-400/15 px-1.5 py-0.5 text-[10px] font-black text-violet-100">
                      {formatEpisodeBadge(item)}
                    </span>
                  </div>
                );
              })}
              {nextQueueItems.length === 0 && (
                <div className="flex-1 rounded-md border border-dashed border-border bg-bg-primary/35 px-2.5 py-1.5 text-xs text-gray-500">
                  대기 중인 작업이 없습니다.
                </div>
              )}
            </div>

            {queueEditChannel != null && (
              <>
                <button
                  type="button"
                  aria-label="채널 편집 닫기"
                  onClick={() => setQueueEditChannel(null)}
                  className="fixed inset-0 z-40 cursor-default bg-black/40"
                />
                <div className="fixed bottom-8 left-4 right-4 top-28 z-50 flex flex-col overflow-hidden rounded-xl border border-accent-primary/30 bg-[#10101a] shadow-2xl shadow-black/60 lg:left-[18rem] lg:right-10">
                  <div className="flex flex-wrap items-center gap-3 border-b border-border/70 bg-bg-secondary/80 px-5 py-4">
                    <span className={`rounded-md border px-3 py-1.5 text-base font-black ${channelBadgeClass(queueEditChannel, true)}`}>
                      CH{queueEditChannel}
                    </span>
                    <div className="mr-auto min-w-0">
                      <div className="text-lg font-bold text-gray-100">채널 대기열 편집</div>
                      <div className="text-sm text-gray-400">
                        {queueChannelTimeLabel(queueChannelTimes[String(queueEditChannel)])} · {editChannelEntries.length}건
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const editKeys = editChannelEntries.map(({ item, index }) => queueItemKey(item, index));
                        const selectedCount = editKeys.filter((key) => selectedQueueIds.has(key)).length;
                        setSelectedQueueIds((prev) => {
                          const next = new Set(prev);
                          if (editKeys.length > 0 && selectedCount === editKeys.length) {
                            editKeys.forEach((key) => next.delete(key));
                          } else {
                            editKeys.forEach((key) => next.add(key));
                          }
                          return next;
                        });
                      }}
                      disabled={editChannelEntries.length === 0 || queueBatchRunning}
                      className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-border bg-bg-primary px-3 text-sm font-bold text-gray-200 hover:bg-bg-tertiary disabled:opacity-40"
                    >
                      {editChannelEntries.length > 0 &&
                      editChannelEntries.every(({ item, index }) => selectedQueueIds.has(queueItemKey(item, index)))
                        ? "전체 해제"
                        : "전체 선택"}
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        void deleteQueueItems(
                          editChannelEntries
                            .map(({ item, index }) => queueItemKey(item, index))
                            .filter((key) => selectedQueueIds.has(key)),
                        )
                      }
                      disabled={
                        queueBatchRunning ||
                        editChannelEntries.every(({ item, index }) => !selectedQueueIds.has(queueItemKey(item, index)))
                      }
                      className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-red-400/35 bg-red-400/10 px-3 text-sm font-bold text-red-300 hover:bg-red-400/20 disabled:opacity-40"
                    >
                      <Trash2 size={14} />
                      선택 삭제
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setQueueChannelFilter(queueEditChannel);
                        setQueuePanelOpen(true);
                        setQueueEditChannel(null);
                      }}
                      className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-blue-400/40 bg-blue-400/15 px-3 text-sm font-bold text-blue-100 hover:bg-blue-400/25"
                    >
                      <ListChecks size={14} />
                      전체 편집
                    </button>
                    <button
                      type="button"
                      onClick={() => setQueueEditChannel(null)}
                      className="inline-flex h-9 items-center justify-center rounded-md border border-border bg-bg-primary px-3 text-sm font-bold text-gray-200 hover:bg-bg-tertiary"
                    >
                      닫기
                    </button>
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto">
                    {editChannelEntries.length ? (
                      editChannelEntries.map(({ item, index }) => renderQueueRow(item, index))
                    ) : (
                      <div className="flex h-full items-center justify-center text-sm text-gray-500">
                        CH{queueEditChannel} 대기열이 비어 있습니다.
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}

            {queuePanelOpen && (
              <>
                <button
                  type="button"
                  aria-label="대기열 팝업 닫기"
                  onClick={() => setQueuePanelOpen(false)}
                  className="fixed inset-0 z-40 cursor-default bg-black/35"
                />
                <div className="fixed bottom-6 left-4 right-4 top-24 z-50 flex flex-col overflow-hidden rounded-xl border border-blue-400/25 bg-[#10101a] shadow-2xl shadow-black/50 lg:left-[18rem] lg:right-8">
                  <button
                    type="button"
                    onClick={() => setQueuePanelOpen(false)}
                    className="absolute right-4 top-4 z-10 inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-bg-primary text-gray-300 shadow-lg shadow-black/30 hover:text-gray-100"
                    title="닫기"
                  >
                    <X size={17} />
                  </button>
                  <div className="flex flex-wrap items-center gap-3 border-b border-border/70 px-5 py-4 pr-16">
                    <ListChecks size={20} className="text-blue-200" />
                    <div className="mr-auto">
                      <div className="text-lg font-bold text-gray-100">전체 작업 큐</div>
                      <div className="text-sm text-gray-400">
                        현재 시각 기준 다음 실행이 빠른 순서로 정렬합니다. 채널 내부는 EP 오름차순입니다. 현재 대기 {persistedCount}건.
                      </div>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setQueueChannelFilter(null)}
                        className={`rounded-md border px-3 py-1.5 text-sm font-bold transition-colors ${
                          queueChannelFilter == null
                            ? "border-accent-primary bg-accent-primary/20 text-accent-primary"
                            : "border-border bg-bg-primary text-gray-400 hover:text-gray-200"
                        }`}
                      >
                        All
                      </button>
                      {queueChannels.map((ch) => (
                        <button
                          key={`queue-filter-${ch}`}
                          type="button"
                          onClick={() => setQueueChannelFilter(ch)}
                          className={`rounded-md border px-3 py-1.5 text-sm font-black transition-colors ${
                            queueChannelFilter === ch
                              ? channelBadgeClass(ch, true)
                              : "border-border bg-bg-primary text-gray-400 hover:text-gray-200"
                          }`}
                          title={`CH${ch} ${channelCounts[ch] || 0}`}
                        >
                          CH{ch} {channelCounts[ch] || 0}
                        </button>
                      ))}
                    </div>
                    <span className="rounded-md border border-blue-400/30 bg-blue-400/10 px-3 py-1.5 text-sm font-bold text-blue-200">
                      현재 기준 실행순
                    </span>
                    <button
                      type="button"
                      onClick={() => void sortQueueItems("asc")}
                      disabled={pendingQueueItems.length < 2 || queueBatchRunning}
                      className="inline-flex items-center gap-2 rounded-md border border-emerald-400/35 bg-emerald-400/10 px-3 py-2 text-sm font-bold text-emerald-200 hover:bg-emerald-400/20 disabled:opacity-40"
                      title="전체 큐를 CH 오름차순, EP 오름차순으로 저장"
                    >
                      오름차순
                    </button>
                    <button
                      type="button"
                      onClick={() => void sortQueueItems("desc")}
                      disabled={pendingQueueItems.length < 2 || queueBatchRunning}
                      className="inline-flex items-center gap-2 rounded-md border border-amber-400/35 bg-amber-400/10 px-3 py-2 text-sm font-bold text-amber-200 hover:bg-amber-400/20 disabled:opacity-40"
                      title="전체 큐를 CH 내림차순, EP 내림차순으로 저장"
                    >
                      내림차순
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedQueueIds((prev) => {
                          const next = new Set(prev);
                          if (allVisibleSelected) {
                            visibleQueueKeys.forEach((key) => next.delete(key));
                          } else {
                            visibleQueueKeys.forEach((key) => next.add(key));
                          }
                          return next;
                        });
                      }}
                      disabled={visibleQueueKeys.length === 0}
                      className="inline-flex items-center gap-2 rounded-md border border-border bg-bg-primary px-3 py-2 text-sm font-semibold text-gray-300 hover:bg-bg-tertiary disabled:opacity-40"
                    >
                      {allVisibleSelected ? "전체 해제" : "전체 선택"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void promoteQueueItemsToNext(visibleQueueKeys.filter((key) => selectedQueueIds.has(key)))}
                      disabled={selectedVisibleCount === 0 || queueBatchRunning}
                      className="inline-flex items-center gap-2 rounded-md border border-accent-success/40 bg-accent-success/15 px-4 py-2 text-sm font-bold text-accent-success hover:bg-accent-success/25 disabled:opacity-40"
                      title="체크한 작업을 큐 맨 앞으로 올리고 1번부터 실행순을 지정"
                    >
                      {queueBatchRunning ? <Loader2 size={15} className="animate-spin" /> : <PlayCircle size={15} />}
                      선택 {selectedVisibleCount}건 순번 지정
                    </button>
                    <button
                      type="button"
                      onClick={() => void deleteQueueItems(visibleQueueKeys.filter((key) => selectedQueueIds.has(key)))}
                      disabled={selectedVisibleCount === 0 || queueBatchRunning}
                      className="inline-flex items-center gap-2 rounded-md border border-red-400/35 bg-red-400/10 px-4 py-2 text-sm font-bold text-red-300 hover:bg-red-400/20 disabled:opacity-40"
                      title="체크한 대기 작업을 큐에서 삭제"
                    >
                      {queueBatchRunning ? <Loader2 size={15} className="animate-spin" /> : <Trash2 size={15} />}
                      선택 {selectedVisibleCount}건 삭제
                    </button>
                    <button
                      type="button"
                      onClick={handleRefresh}
                      className="inline-flex items-center gap-2 rounded-md border border-border bg-bg-primary px-3 py-2 text-sm font-semibold text-gray-300 hover:bg-bg-tertiary"
                    >
                      <RefreshCw size={15} />
                      새로고침
                    </button>
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto p-3">
                    {pendingQueueItems.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border bg-bg-primary/35 px-4 py-8 text-center text-sm text-gray-500">
                        대기 중인 작업이 없습니다.
                      </div>
                    ) : visibleQueueEntries.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border bg-bg-primary/35 px-4 py-8 text-center text-sm text-gray-500">
                        CH{queueChannelFilter} queue is empty.
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-border bg-bg-primary/40">
                        <div className="flex flex-wrap items-center gap-2.5 border-b border-border/70 bg-bg-secondary/70 px-4 py-3 text-sm text-gray-300">
                          <span className="font-bold text-gray-200">현재 큐 순서</span>
                          {queueChannelFilter != null && (
                            <span className={`rounded-md border px-3 py-1.5 text-sm font-black ${channelBadgeClass(queueChannelFilter, true)}`}>
                              CH{queueChannelFilter} filter · {visibleQueueEntries.length}
                            </span>
                          )}
                          {liveNextCount > 0 && (
                            <span className="rounded border border-amber-300/40 bg-amber-300/15 px-2.5 py-1 font-bold text-amber-200">
                              실행순 지정 {liveNextCount}건
                            </span>
                          )}
                          {channelsByNextRun.map((ch) => (
                            <span key={`time-order-${ch}`} className={`rounded-md border px-3 py-1.5 text-sm font-black ${channelBadgeClass(ch, (channelCounts[ch] || 0) > 0)}`}>
                              CH{ch} {queueChannelTimeLabel(queueChannelTimes[String(ch)])} · {channelCounts[ch] || 0}건
                            </span>
                          ))}
                        </div>
                        {visibleQueueEntries.map(({ item, index }) => renderQueueRow(item, index))}
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
            {recoveryOpen && (
              <>
              <button
                type="button"
                aria-label="복구 팝업 닫기"
                onClick={() => setRecoveryOpen(false)}
                className="fixed inset-0 z-40 cursor-default bg-black/20"
              />
              <div className="fixed left-4 right-4 top-36 z-50 max-h-[420px] overflow-y-auto rounded-xl border border-white/70 bg-[#10101a] p-3 shadow-2xl shadow-black/50 lg:left-72 lg:right-8">
                <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-white/25 pb-3">
                  <div className="mr-auto flex min-w-[160px] items-center gap-2">
                    <AlertTriangle size={14} className="text-amber-300" />
                    <div>
                      <div className="text-sm font-bold text-gray-100">작업기록 큐 복귀</div>
                      <div className="text-[11px] text-gray-500">
                        완료 {completedTasks.length}건 · 실패 {failedTasks.length}건 · 고아 {orphanProjects.length}건
                      </div>
                    </div>
                  </div>
                  {[null, 1, 2, 3, 4].map((ch) => (
                    <button
                      key={ch ?? "all"}
                      type="button"
                      onClick={() => {
                        setRecoveryChannel(ch);
                        void loadRecoveryContent(ch);
                      }}
                      className={`rounded-md border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                        recoveryChannel === ch
                          ? "border-accent-primary bg-accent-primary/20 text-accent-primary"
                          : "border-border bg-bg-primary text-gray-400 hover:text-gray-200"
                      }`}
                    >
                      {ch == null ? "전체" : `CH${ch}`}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => loadRecoveryContent(recoveryChannel)}
                    disabled={recoveryLoading || recoveryBulkQueuing}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-primary px-2.5 py-1 text-[11px] font-semibold text-gray-300 hover:bg-bg-tertiary disabled:opacity-50"
                  >
                    <RefreshCw size={12} className={recoveryLoading ? "animate-spin" : ""} />
                    새로고침
                  </button>
                  <button
                    type="button"
                    onClick={handleRecoveryBulkReupload}
                    disabled={recoveryBulkUploading || recoveryBulkQueuing || failedTasks.filter(isUploadRecoverableTask).length === 0}
                    className="inline-flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
                  >
                    <RotateCcw size={12} className={recoveryBulkUploading ? "animate-spin" : ""} />
                    업로드 실패 {failedTasks.filter(isUploadRecoverableTask).length}건 재시도
                  </button>
                  <button
                    type="button"
                    onClick={handleRecoveryQueueAll}
                    disabled={recoveryBulkQueuing || recoveryBulkUploading || recoveryLoading || failedTasks.length + orphanProjects.length === 0}
                    className="inline-flex items-center gap-1.5 rounded-md border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 text-[11px] font-semibold text-amber-100 hover:bg-amber-400/15 disabled:opacity-40"
                  >
                    <RotateCcw size={12} className={recoveryBulkQueuing ? "animate-spin" : ""} />
                    전체 복구 {failedTasks.length + orphanProjects.length}건
                  </button>
                  <button
                    type="button"
                    onClick={() => setRecoveryOpen(false)}
                    className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-bg-primary text-gray-400 hover:text-gray-100"
                    title="닫기"
                  >
                    <X size={13} />
                  </button>
                </div>
                {recoveryLoading ? (
                  <div className="flex items-center gap-2 text-sm text-gray-400">
                    <Loader2 size={14} className="animate-spin" />
                    복구 대상 불러오는 중...
                  </div>
                ) : completedTasks.length === 0 && failedTasks.length === 0 && orphanProjects.length === 0 ? (
                  <div className="text-sm text-gray-500">불러올 작업기록이 없습니다.</div>
                ) : (
                  <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
                    <div>
                      <div className="mb-2 text-xs font-bold text-emerald-300">완료 태스크 {completedTasks.length}건</div>
                      <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
                        {completedTasks.map((item) => (
                          <div key={item.task_id} className="flex items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-3 py-2">
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-gray-200">{taskTitle(item)}</div>
                              <div className="text-xs text-gray-500">
                                {item.channel ? `CH${item.channel} · ` : ""}{getTaskFailureStepName(item)} · {Math.round(item.progress_pct || 0)}%
                              </div>
                            </div>
                            <button
                              onClick={() => void handleQueueCompletedTask(item)}
                              disabled={recoveryBulkQueuing || recoveringId === item.task_id}
                              className="shrink-0 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-xs font-semibold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-50"
                            >
                              {recoveringId === item.task_id ? "처리 중..." : "큐 복귀"}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold text-red-300">실패/중단 태스크 {failedTasks.length}건</div>
                      <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
                        {failedTasks.map((item) => (
                          <div key={item.task_id} className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                            <div className="min-w-0 flex-1">
                              <div className="flex min-w-0 items-center gap-2">
                                <div className="truncate text-sm font-semibold text-gray-200">{taskTitle(item)}</div>
                                {isUploadRecoverableTask(item) && (
                                  <span className="shrink-0 rounded border border-emerald-400/30 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-200">
                                    업로드만 남음
                                  </span>
                                )}
                              </div>
                              <div className="text-xs text-gray-500">
                                {item.channel ? `CH${item.channel} · ` : ""}{getTaskFailureStepName(item)} · {Math.round(item.progress_pct || 0)}%
                              </div>
                            </div>
                            {isUploadRecoverableTask(item) && (
                              <button
                                onClick={() => void handleRecoveryReupload(item)}
                                disabled={Boolean(recoveryUploadingId) || recoveryBulkUploading || recoveryBulkQueuing}
                                className="shrink-0 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-xs font-semibold text-emerald-200 hover:bg-emerald-400/15 disabled:opacity-40"
                              >
                                {recoveryUploadingId === item.task_id ? "업로드 중..." : "업로드 재시도"}
                              </button>
                            )}
                            <button
                              onClick={() => void handleQueueFailedTask(item)}
                              disabled={recoveryBulkQueuing || recoveringId === item.task_id}
                              className="shrink-0 rounded-md border border-red-400/30 bg-red-400/10 px-2.5 py-1 text-xs font-semibold text-red-200 hover:bg-red-400/15 disabled:opacity-50"
                            >
                              {recoveringId === item.task_id ? "처리 중..." : "큐 상단으로"}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div className="mb-2 text-xs font-bold text-amber-300">고아 프로젝트 {orphanProjects.length}건</div>
                      <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
                        {orphanProjects.map((item) => (
                          <div key={item.project_id} className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 px-3 py-2">
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-gray-200">{withEpisodeTitle(item.topic || item.title || item.project_id, item.episode_number)}</div>
                              <div className="text-xs text-gray-500">
                                CH{item.channel || "-"} · {item.progress?.progress_pct ?? 0}% · {item.progress?.total_cuts ?? 0}컷
                                {item.unattributed ? " · 채널 미지정" : ""}
                              </div>
                            </div>
                            <button
                              onClick={() => void handleRecoverOrphan(item.project_id)}
                              disabled={recoveryBulkQueuing || recoveringId === item.project_id}
                              className="shrink-0 rounded-md border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-xs font-semibold text-amber-200 hover:bg-amber-400/15 disabled:opacity-50"
                            >
                              {recoveringId === item.project_id ? "처리 중..." : "큐 상단으로"}
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
              </>
            )}
          </div>
        );
      })()}

      <div className="order-2 flex-1 min-h-0 overflow-y-auto pr-1">
        <div className="flex min-h-full flex-col gap-3 2xl:gap-4">
          <section className="rounded-lg border border-border bg-bg-secondary p-3">
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Activity size={15} className="text-accent-secondary" />
                <h2 className="text-base font-bold text-gray-100">현재 작업</h2>
                {hasCurrentPanelItem && (
                  <span
                    className={`rounded border px-2 py-0.5 text-xs font-bold ${
                      displayTask?.status === "running"
                        ? "border-emerald-400/35 bg-emerald-400/10 text-emerald-200"
                        : displayTask?.status === "failed" || displayTask?.status === "cancelled" || displayTask?.status === "paused"
                          ? "border-red-400/35 bg-red-400/10 text-red-200"
                          : "border-amber-400/35 bg-amber-400/10 text-amber-200"
                    }`}
                  >
                    {currentPanelStatus}
                  </span>
                )}
              </div>
            </div>

            {hasCurrentPanelItem ? (
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-[minmax(220px,30%)_minmax(240px,1fr)_minmax(220px,30%)]">
                <div className="flex min-w-0 flex-col gap-2">
                  <div className="group relative aspect-video overflow-hidden rounded-lg border border-border bg-black/35">
                    {currentThumbnailSrc ? (
                      <img
                        src={currentThumbnailSrc}
                        alt="thumbnail"
                        className="h-full w-full object-cover"
                        onError={(e) => {
                          (e.target as HTMLImageElement).style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="flex h-full flex-col items-center justify-center gap-2 bg-gradient-to-br from-slate-900 via-slate-800 to-zinc-950">
                        <Film size={30} className="text-gray-600" />
                        <span className="text-sm font-semibold text-gray-500">썸네일 대기</span>
                      </div>
                    )}
                    {displayTask?.task_id && (
                      <div className="absolute inset-x-0 bottom-0 flex items-center justify-end gap-2 bg-gradient-to-t from-black/80 via-black/45 to-transparent p-2 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                        <button
                          type="button"
                          onClick={handleOpenThumbnailPrompt}
                          disabled={thumbnailPromptLoading}
                          className="inline-flex items-center gap-1.5 rounded-md border border-white/15 bg-black/65 px-2.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-black/80 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {thumbnailPromptLoading ? <Loader2 size={13} className="animate-spin" /> : <Pencil size={13} />}
                          프롬프트 변경
                        </button>
                        <button
                          type="button"
                          onClick={handleRegenerateThumbnail}
                          disabled={thumbnailRegenerating || displayTask.thumbnail_status === "generating"}
                          className="inline-flex items-center gap-1.5 rounded-md border border-accent-primary/40 bg-accent-primary/80 px-2.5 py-1.5 text-xs font-black text-white shadow-sm hover:bg-accent-primary disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <RefreshCw size={13} className={thumbnailRegenerating ? "animate-spin" : ""} />
                          {thumbnailRegenerating ? "생성 중" : "재생성"}
                        </button>
                      </div>
                    )}
                    <div className="absolute left-2 top-2 flex gap-1.5">
                      <span className={`rounded border px-2 py-1 text-xs font-black ${channelBadgeClass(currentPanelChannel)}`}>
                        CH{currentPanelChannel}
                      </span>
                      <span className="rounded border border-violet-400/35 bg-violet-400/15 px-2 py-1 text-xs font-bold text-violet-100">
                        {episodePrefix(currentPanelEpisode) || "EP.--"}
                      </span>
                    </div>
                  </div>
                  <button
                    onClick={handleCurrentPanelPrimaryAction}
                    disabled={currentPanelPrimaryDisabled}
                    className={`inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border px-4 text-sm font-black shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-55 ${
                      currentPanelIsRunning
                        ? "border-border bg-bg-primary text-gray-500"
                        : currentPanelCanResume
                          ? "border-accent-primary/50 bg-accent-primary text-white shadow-purple-950/30 hover:bg-purple-600"
                          : "border-emerald-400/45 bg-emerald-500/20 text-emerald-100 shadow-emerald-950/20 hover:bg-emerald-500/30"
                    }`}
                  >
                    {resuming || startingCurrent ? (
                      <Loader2 size={15} className="animate-spin" />
                    ) : currentPanelCanResume ? (
                      <RefreshCw size={15} />
                    ) : (
                      <PlayCircle size={15} />
                    )}
                    {currentPanelPrimaryLabel}
                  </button>
                </div>

                <div className="flex min-w-0 flex-col gap-3">
                  <div className="min-w-0">
                    <h3 className="line-clamp-2 text-lg font-black leading-tight text-white lg:text-xl">
                      {currentPanelTitle}
                    </h3>
                  </div>

                  <div>
                    <div className="mb-1.5 flex items-end justify-between gap-3">
                      <span className="text-3xl font-black tabular-nums text-white lg:text-4xl">{(displayTask?.progress_pct || 0).toFixed(1)}%</span>
                      <span className="font-mono text-base font-bold text-amber-200 lg:text-lg">{displayTask ? compactSeconds(activeStartedSec) : "대기"}</span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-bg-primary">
                      <div
                        className="h-full rounded-full bg-accent-primary transition-[width] duration-500"
                        style={{ width: `${Math.max(0, Math.min(100, displayTask?.progress_pct || 0))}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex min-h-[116px] flex-1 flex-col justify-center rounded-lg border border-border/70 bg-bg-primary/35 px-4 py-3">
                    {comfyProgress ? (
                      <div className="space-y-2.5">
                        <div className="flex items-center justify-between gap-3 text-xs font-black">
                          <span className="truncate text-purple-100">
                            {comfyProgress.cut
                              ? `COMFYUI cut ${comfyProgress.cut}/${comfyProgress.cutTotal || displayTask?.total_cuts || "-"}`
                              : "COMFYUI KSampler"}
                          </span>
                          <span className="shrink-0 font-mono text-purple-200">
                            {comfyProgress.current}/{comfyProgress.total} ({Math.round(comfyProgress.pct)}%)
                          </span>
                        </div>
                        <div className="h-3 overflow-hidden rounded-full bg-purple-950/80">
                          <div
                            className="h-full rounded-full bg-purple-400 transition-[width] duration-300"
                            style={{ width: `${comfyProgress.pct}%` }}
                          />
                        </div>
                        {comfyAverage && (
                          <div className="flex items-center justify-between gap-3 text-[11px] font-bold text-purple-100/85">
                            <span>평균 {compactSeconds(comfyAverage.seconds)}/건</span>
                            <span className="text-purple-200/70">최근 {comfyAverage.count}건</span>
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-3 text-xs font-bold text-gray-500">
                        <span>COMFYUI 진행 수신 대기</span>
                        <span className="font-mono">0/0 (0%)</span>
                      </div>
                    )}
                  </div>

                  <div className="mt-auto">
                    <button
                      onClick={handleToggleAutoProduction}
                      disabled={autoProductionSaving}
                      className={`inline-flex h-10 w-full min-w-0 items-center justify-center gap-2 rounded-lg border px-4 text-sm font-black shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
                        autoProductionEnabled
                          ? "border-emerald-400/45 bg-emerald-500/15 text-emerald-100 hover:bg-emerald-500/25"
                          : "border-amber-400/45 bg-amber-500/15 text-amber-100 hover:bg-amber-500/25"
                      }`}
                    >
                      {autoProductionSaving ? (
                        <Loader2 size={15} className="animate-spin" />
                      ) : (
                        <Power size={15} />
                      )}
                      <span className="truncate">
                        {autoProductionEnabled ? "자동제작 끄기" : "자동제작 켜기"}
                      </span>
                    </button>
                  </div>
                </div>

                <div className="flex min-w-0 flex-col gap-2">
                  <div className="relative aspect-video overflow-hidden rounded-lg border border-border bg-black/35">
                    <div className="absolute left-2 top-2 z-10 rounded border border-border/80 bg-black/55 px-2 py-1 text-xs font-bold text-gray-200">
                      {latestGeneratedAsset?.label || "생성 결과 대기"}
                    </div>
                    {latestGeneratedAsset?.kind === "video" ? (
                      <video
                        key={latestGeneratedAsset.src}
                        src={latestGeneratedAsset.src}
                        className="h-full w-full object-contain"
                        controls
                        preload="metadata"
                      />
                    ) : latestGeneratedAsset?.kind === "image" ? (
                      <img
                        key={latestGeneratedAsset.src}
                        src={latestGeneratedAsset.src}
                        alt="generated preview"
                        className="h-full w-full object-contain"
                        onError={(event) => {
                          event.currentTarget.style.display = "none";
                        }}
                      />
                    ) : (
                      <div className="flex h-full flex-col items-center justify-center gap-2 text-gray-600">
                        <Film size={30} />
                        <span className="text-sm font-semibold">이미지/영상 대기</span>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={handleCancel}
                    disabled={!displayTask || displayTask.status !== "running"}
                    className="inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-red-400/40 bg-red-500/10 px-4 text-sm font-black text-red-200 shadow-sm transition-colors hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <Square size={15} />
                    중단
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed border-border bg-bg-primary/40 text-sm text-gray-600">
                진행 중인 작업이 없습니다.
              </div>
            )}
          </section>

          <div className="grid h-[430px] grid-cols-1 items-stretch gap-3 md:grid-cols-[minmax(360px,50%)_minmax(360px,1fr)] 2xl:grid-cols-[minmax(420px,50%)_minmax(420px,1fr)]">
            <section className="h-full overflow-hidden rounded-lg border border-border bg-bg-secondary p-2.5">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h2 className="text-base font-bold text-gray-100">단계별 실제 진행</h2>
                <span className="text-xs text-gray-500">실시간</span>
              </div>
              <div className="space-y-2">
                {compactStageRows.map((row) => (
                  <div
                    key={row.key}
                    className={`min-w-0 rounded-lg border px-2 py-2 ${
                      row.isActive
                        ? "border-accent-primary/50 bg-accent-primary/[0.05]"
                        : row.state === "done"
                          ? "border-emerald-400/25 bg-emerald-400/[0.03]"
                          : row.state === "failed"
                            ? "border-red-400/35 bg-red-400/[0.04]"
                            : "border-border/70 bg-bg-primary/35"
                    }`}
                  >
                    <div className="grid grid-cols-[58px_44px_minmax(0,1fr)_72px_48px_48px] items-center gap-2">
                      <div className="truncate text-sm font-black text-gray-100" title={row.label}>{row.label}</div>
                      <div className={`truncate text-xs font-bold ${row.isActive ? "text-accent-primary" : "text-gray-500"}`}>
                          {row.isActive ? "진행" : row.state === "done" ? "완료" : row.state === "failed" ? "실패" : "대기"}
                      </div>
                      <div className="truncate text-sm font-semibold text-gray-200" title={row.model || ""}>
                        {row.model || "-"}
                      </div>
                      <div className="font-mono text-xs font-bold text-amber-200" title={row.seconds}>{row.seconds}</div>
                      <button
                        type="button"
                        onClick={() => handleRerunFromStep(Number(row.key))}
                        className="justify-self-end rounded border border-accent-primary/25 bg-accent-primary/10 px-1.5 py-1 text-[10px] font-bold text-accent-primary"
                        title="이 단계부터 재개"
                      >
                        재개
                      </button>
                      <button
                        type="button"
                        onClick={() => handleClearStep(Number(row.key), row.label)}
                        disabled={
                          Number(row.key) > 6 ||
                          row.state === "pending" ||
                          clearing === Number(row.key) ||
                          ["running", "queued", "prepared"].includes(displayTask?.status || "")
                        }
                        className="justify-self-end rounded border border-red-400/30 bg-red-400/10 px-1.5 py-1 text-[10px] font-bold text-red-300 hover:bg-red-400/20 disabled:cursor-not-allowed disabled:opacity-35"
                        title={
                          ["running", "queued", "prepared"].includes(displayTask?.status || "")
                            ? "작업 중에는 결과물을 삭제할 수 없습니다. 먼저 중단하세요."
                            : Number(row.key) > 6
                              ? "업로드 단계는 삭제 대상 결과물이 없습니다."
                              : "이 단계 결과물 삭제"
                        }
                      >
                        {clearing === Number(row.key) ? "삭제중" : "삭제"}
                      </button>
                    </div>
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-primary">
                      <div
                        className={`h-full rounded-full transition-[width] duration-500 ${row.isActive ? "bg-accent-primary" : row.state === "done" ? "bg-emerald-400" : "bg-gray-700"}`}
                        style={{ width: `${row.progress}%` }}
                      />
                    </div>
                    {row.isActive && row.liveText && (
                      <div className="mt-1.5 truncate text-[11px] font-semibold text-accent-primary" title={row.liveText}>
                        {row.liveText}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <aside className="grid h-full min-h-0 grid-cols-1 gap-3.5">
              <section className="flex h-full min-h-0 flex-col overflow-hidden rounded-lg border border-border bg-[#08080e] p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <h2 className="text-base font-bold text-gray-100">제작 로그</h2>
                  <span className="text-xs text-gray-600">{compactLogRows.length}줄</span>
                </div>
                <div ref={logScrollRef} className="min-h-0 flex-1 overflow-y-auto pr-1 font-mono text-xs leading-5">
                  {compactLogRows.length ? (
                    <>
                      {compactLogRows.map((log, i) => (
                        <div key={`${log.time}-${i}`} className="grid grid-cols-[58px_minmax(0,1fr)] gap-2 border-b border-white/[0.03] py-1 last:border-b-0">
                          <span className="text-gray-600">{log.time}</span>
                          <span className={`min-w-0 truncate ${logColor(log.level)}`} title={log.msg}>{log.msg}</span>
                        </div>
                      ))}
                    </>
                  ) : (
                    <div className="py-8 text-center text-sm text-gray-600">로그 없음</div>
                  )}
                </div>
              </section>
            </aside>
          </div>
        </div>
      </div>

      {thumbnailPromptOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4">
          <div className="w-full max-w-3xl rounded-xl border border-border bg-bg-secondary shadow-2xl">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <div>
                <h2 className="text-base font-bold text-gray-100">썸네일 프롬프트 변경</h2>
                <p className="mt-1 text-xs text-gray-500">저장된 프롬프트는 다음 썸네일 재생성에 적용됩니다.</p>
              </div>
              <button
                type="button"
                onClick={() => setThumbnailPromptOpen(false)}
                className="rounded-md border border-border bg-bg-primary p-2 text-gray-400 hover:text-white"
              >
                <X size={16} />
              </button>
            </div>
            <div className="p-5">
              {thumbnailPromptLoading ? (
                <div className="flex h-52 items-center justify-center gap-3 text-sm text-gray-400">
                  <Loader2 size={18} className="animate-spin text-accent-primary" />
                  프롬프트 불러오는 중...
                </div>
              ) : (
                <textarea
                  value={thumbnailPrompt}
                  onChange={(event) => setThumbnailPrompt(event.target.value)}
                  className="h-64 w-full resize-none rounded-lg border border-border bg-bg-primary px-3 py-3 font-mono text-sm leading-6 text-gray-200 outline-none focus:border-accent-primary"
                  placeholder="썸네일 이미지 프롬프트"
                />
              )}
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
              <button
                type="button"
                onClick={() => setThumbnailPromptOpen(false)}
                className="rounded-lg border border-border bg-bg-primary px-4 py-2 text-sm font-semibold text-gray-300 hover:text-white"
              >
                닫기
              </button>
              <button
                type="button"
                onClick={handleSaveThumbnailPrompt}
                disabled={thumbnailPromptLoading || thumbnailPromptSaving}
                className="inline-flex items-center gap-2 rounded-lg border border-accent-primary/40 bg-accent-primary px-4 py-2 text-sm font-black text-white hover:bg-purple-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {thumbnailPromptSaving && <Loader2 size={14} className="animate-spin" />}
                저장
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 실패/지연 메시지는 제작 로그 패널에만 표시한다. */}
      {/* 파이프라인
          v1.2.13: 반응형으로 재작성.
          - xl 이상: 기존처럼 한 줄 6 스텝 + 화살표 커넥터.
          - xl 미만: flex-wrap 로 자동 줄바꿈, 스텝은 min-width 로 찌그러짐 방지,
            화살표는 줄바꿈과 충돌하므로 xl 미만에서 숨김. */}
    </div>
  );
}

