"use client";

/**
 * v1.1.49 — 딸깍 대시보드 > 실시간 현황
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
  Clock,
  DollarSign,
  Timer,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  ListChecks,
  X,
  Trash2,
} from "lucide-react";
import { oneclickApi, modelsApi, voiceApi, assetUrl, type OneClickTask, type OneClickQueueItem, type ModelInfo, type OrphanProject } from "@/lib/api";
import { formatDurationKo, formatKrw } from "@/lib/format";

const STEPS = [
  { key: "2", label: "스크립트", modelKey: "script" as const },
  { key: "3", label: "음성", modelKey: "tts" as const },
  { key: "4", label: "이미지", modelKey: "image" as const },
  { key: "5", label: "영상", modelKey: "video" as const },
  { key: "6", label: "렌더", modelKey: null },
  { key: "7", label: "업로드", modelKey: null },
] as const;

function getStepState(
  task: OneClickTask | null,
  stepKey: string,
): "done" | "active" | "pending" | "failed" {
  if (!task) return "pending";

  const stepStates = task.step_states || {};
  const val = stepStates[stepKey];
  if (val === "completed" || val === "done") return "done";
  if (val === "running" || val === "in_progress") return "active";
  if (val === "failed" || val === "cancelled") return "failed";

  const stepOrder = ["2", "3", "4", "5", "6", "7"];
  const highestCompletedIndex = stepOrder.reduce((acc, key, index) => {
    const state = stepStates[key];
    return state === "completed" || state === "done" ? index : acc;
  }, -1);

  if (
    highestCompletedIndex >= 0 &&
    stepOrder.indexOf(stepKey) <= highestCompletedIndex
  ) {
    return "done";
  }

  return "pending";
}

interface LogEntry {
  time: string;
  msg: string;
  level: "info" | "success" | "warn" | "error" | "muted";
}

type ServerLogEntry = NonNullable<OneClickTask["logs"]>[number];

const timeValue = (value?: string | null) => {
  if (!value) return 0;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : 0;
};

function serverLogToEntry(log: ServerLogEntry): LogEntry {
  return {
    time: log.ts || "",
    msg: log.msg,
    level:
      log.level === "error"
        ? "error"
        : log.level === "warn"
          ? "warn"
          : "info",
  };
}

function taskLogsToEntries(task: OneClickTask | null): LogEntry[] {
  return (task?.logs || []).map(serverLogToEntry);
}

function formatQueueWaitingMeta(
  item: OneClickQueueItem,
  channelTimes: Record<string, string | null | undefined>,
) {
  const source = String(item.queued_source || "manual").toLowerCase();
  const sourceLabel =
    source === "import"
      ? "엑셀 등록"
      : source === "requeue"
        ? "실패 복구"
        : source === "orphan"
          ? "고아 복구"
          : source === "schedule" || source === "system"
            ? "자동 등록"
            : "수동 등록";
  const sourceClass =
    source === "requeue" || source === "orphan"
      ? "border-amber-400/30 bg-amber-400/10 text-amber-200"
      : source === "import"
        ? "border-sky-400/30 bg-sky-400/10 text-sky-200"
        : "border-gray-500/30 bg-gray-500/10 text-gray-300";
  const ch = String(item.channel || 1);
  const scheduledTime = channelTimes[ch] || null;
  const scheduleLabel = scheduledTime
    ? `자동 실행 · 매일 ${scheduledTime}`
    : "수동 실행 대기";
  const queuedAt = item.queued_at
    ? new Date(item.queued_at).toLocaleString("ko-KR", {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "등록 시각 미상";
  return {
    sourceLabel,
    sourceClass,
    scheduleLabel,
    queuedAt,
    note: item.queued_note || "",
  };
}

function formatEpisodeBadge(item: OneClickQueueItem) {
  const ep = item.episode_number;
  return typeof ep === "number" && ep > 0 ? `EP.${String(ep).padStart(2, "0")}` : "EP.--";
}

function episodePrefix(ep?: number | null) {
  return typeof ep === "number" && ep > 0 ? `EP.${String(ep).padStart(2, "0")}` : "";
}

function withEpisodeTitle(title: string | null | undefined, ep?: number | null) {
  const text = String(title || "").trim();
  const prefix = episodePrefix(ep);
  if (!prefix) return text;
  if (/^EP\.\s*\d+/i.test(text)) return text;
  return `${prefix} ${text}`;
}

function queueTitle(item: OneClickQueueItem) {
  return withEpisodeTitle(item.topic, item.episode_number);
}

function isLiveNextQueueItem(item: OneClickQueueItem) {
  return (
    String(item.queued_source || "").toLowerCase() === "manual" &&
    String(item.queued_note || "").includes("실시간 현황")
  );
}

function taskTitle(item: OneClickTask) {
  return withEpisodeTitle(item.topic || item.title, item.episode_number);
}

function queueItemKey(item: OneClickQueueItem, index: number) {
  return item.id || `${index}:${item.channel || 1}:${item.topic}`;
}

/** v1.1.53: 썸네일 패널 — 실시간 3단계 표시
 *  waiting     → "대본 생성 완료 후 자동 생성됩니다"
 *  generating  → 스피너 + "썸네일 생성 중..."
 *  done        → 이미지 즉시 표시
 *  failed      → 실패 메시지 + 재생성 버튼
 */
function ThumbnailPanel({ task }: { task: OneClickTask }) {
  const pid = task.project_id;
  const [imageModels, setImageModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [regenerating, setRegenerating] = useState(false);
  const [thumbKey, setThumbKey] = useState(0); // 캐시 무효화용

  const thumbStatus = task.thumbnail_status || "waiting";
  const thumbUrl = pid ? `${assetUrl(pid, "output/thumbnail.png")}?v=${thumbKey}` : "";

  // done 상태가 되면 자동으로 thumbKey 증가 → 이미지 리로드
  const prevStatusRef = useRef(thumbStatus);
  useEffect(() => {
    if (prevStatusRef.current !== "done" && thumbStatus === "done") {
      setThumbKey((k) => k + 1);
    }
    prevStatusRef.current = thumbStatus;
  }, [thumbStatus]);

  useEffect(() => {
    modelsApi.listImage().then((r) => setImageModels(r.models || []));
  }, []);

  // v1.1.55: 썸네일 모델 우선, 없으면 이미지 모델 폴백
  useEffect(() => {
    setSelectedModel(task.models?.thumbnail || task.models?.image || "");
  }, [task.models?.thumbnail, task.models?.image]);

  const [regenError, setRegenError] = useState<string | null>(null);

  const handleRegenerate = async () => {
    setRegenerating(true);
    setRegenError(null);
    try {
      await oneclickApi.regenerateThumbnail(task.task_id, selectedModel || undefined);
      setThumbKey((k) => k + 1);
    } catch (e: any) {
      const detail = e?.message || String(e) || "알 수 없는 오류";
      console.error("썸네일 재생성 실패:", detail);
      setRegenError(detail);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
      <h3 className="text-base font-bold text-gray-100 mb-4">썸네일</h3>

      {/* 썸네일 영역: 상태에 따라 표시 — regenerating 이면 무조건 스피너 */}
      <div className="relative w-full aspect-video bg-black/30 rounded-lg overflow-hidden mb-4">
        {regenerating ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 size={28} className="animate-spin text-accent-primary" />
            <span className="text-sm text-gray-400">썸네일 재생성 중...</span>
          </div>
        ) : regenError ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
            <span className="text-sm text-red-400 font-semibold">썸네일 재생성 실패</span>
            <span className="text-sm text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
              {regenError}
            </span>
          </div>
        ) : thumbStatus === "done" || prevStatusRef.current === "done" ? (
          <img
            key={thumbKey}
            src={thumbUrl}
            alt="thumbnail"
            className="w-full h-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
          />
        ) : thumbStatus === "generating" ? (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Loader2 size={28} className="animate-spin text-accent-primary" />
            <span className="text-sm text-gray-400">썸네일 생성 중...</span>
          </div>
        ) : thumbStatus === "failed" ? (
          <div className="flex flex-col items-center justify-center h-full gap-2 px-4">
            <span className="text-sm text-red-400 font-semibold">썸네일 생성 실패</span>
            {task.thumbnail_error && (
              <span className="text-sm text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
                {task.thumbnail_error}
              </span>
            )}
            <button
              onClick={handleRegenerate}
              className="text-sm text-accent-primary hover:underline mt-1"
            >
              다시 시도
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3">
            <Clock size={20} className="text-gray-600" />
            <span className="text-sm text-gray-600">대본 생성 완료 후 자동 생성</span>
          </div>
        )}
      </div>

      {/* 모델 선택 + 재생성 버튼 */}
      <div className="flex items-center gap-2">
        <select
          value={selectedModel}
          onChange={(e) => setSelectedModel(e.target.value)}
          className="flex-1 text-sm bg-bg-primary text-gray-300 border border-border rounded-lg px-3 py-2 outline-none"
        >
          {imageModels.map((m) => (
            <option key={m.id} value={m.id}>{m.name || m.id}</option>
          ))}
        </select>
        <button
          onClick={handleRegenerate}
          disabled={regenerating || !pid || thumbStatus === "generating"}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-accent-primary/15 text-accent-primary border border-accent-primary/30 hover:bg-accent-primary/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={regenerating ? "animate-spin" : ""} />
          {regenerating ? "생성 중..." : "재생성"}
        </button>
      </div>
    </div>
  );
}


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
  const lastTickRef = useRef<{ step: string; cuts: number; ts: number }>({
    step: "",
    cuts: -1,
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

  const stepStates = task.step_states || {};
  const completedByStep = task.completed_cuts_by_step || {};
  const totalCuts = Math.max(1, Number(task.total_cuts || 0));
  const timeBreakdown = task.estimate?.time_breakdown || {};

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
    const cutsNow = Number(completedByStep[primaryActive.key] || 0);
    const tick = lastTickRef.current;
    if (tick.step !== primaryActive.key || tick.cuts !== cutsNow) {
      lastTickRef.current = { step: primaryActive.key, cuts: cutsNow, ts: now };
    } else {
      staleSec = Math.floor((now - tick.ts) / 1000);
    }
  } else {
    lastTickRef.current = { step: "", cuts: -1, ts: now };
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
          const state = getStepState(task, s.key);
          const stepNum = Number(s.key);
          const cuts = Number(completedByStep[s.key] || 0);
          const modelName =
            s.modelKey && task?.models
              ? s.modelKey === "tts"
                ? [
                    task.models.tts
                      ? modelNameMap[task.models.tts] || task.models.tts
                      : "",
                    task.models.tts_voice
                      ? voiceNameMap[task.models.tts_voice] || task.models.tts_voice
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" / ")
                : task.models[s.modelKey]
                  ? modelNameMap[task.models[s.modelKey] as string] || task.models[s.modelKey] || ""
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
              etaText = `남은 ~${formatDurationKo(remainSec)}`;
            } else if (est > 0) {
              etaText = `예상 ~${formatDurationKo(est)}`;
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
  // v1.1.65: 동시/대기 중 task 전체 목록. 화면에 "진행 중 N건" 스트립으로 노출.
  // 백엔드는 _RUN_LOCK 으로 한 번에 1건만 실행하지만 사용자가 여러 건을 시작하거나
  // 큐 스케줄러(_queue_loop)가 여러 채널을 동시에 fire 하면 prepared/queued/running
  // 이 여러 개 쌓일 수 있다. 기존 .find() 1건 표시로는 가려지던 상태.
  const [activeTasks, setActiveTasks] = useState<OneClickTask[]>([]);
  const [pendingQueueItems, setPendingQueueItems] = useState<OneClickQueueItem[]>([]);
  const [queueChannelTimes, setQueueChannelTimes] = useState<Record<string, string | null>>({
    "1": null,
    "2": null,
    "3": null,
    "4": null,
  });
  const [recoveryOpen, setRecoveryOpen] = useState(false);
  const [recoveryLoading, setRecoveryLoading] = useState(false);
  const [recoveryChannel, setRecoveryChannel] = useState<number | null>(null);
  const [failedTasks, setFailedTasks] = useState<OneClickTask[]>([]);
  const [orphanProjects, setOrphanProjects] = useState<OrphanProject[]>([]);
  const [recoveringId, setRecoveringId] = useState<string | null>(null);
  const [movingQueueId, setMovingQueueId] = useState<string | null>(null);
  const [queuePanelOpen, setQueuePanelOpen] = useState(false);
  const [selectedQueueIds, setSelectedQueueIds] = useState<Set<string>>(new Set());
  const [queueBatchRunning, setQueueBatchRunning] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [pollFails, setPollFails] = useState(0);
  const [lastServerSyncAt, setLastServerSyncAt] = useState<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  // 멈춤 감지: 진행률이 일정 시간 변하지 않으면 경고
  const lastPctChangeRef = useRef<number>(Date.now());
  const lastPctValueRef = useRef<number>(0);
  const [stalled, setStalled] = useState(false);
  // v1.2.27: 3분 stall 시 ComfyUI 큐 자동 리셋을 이번 stall 라운드에 이미 쐈는지.
  // 진행률이 다시 변하면 false 로 되돌려 다음 stall 라운드에 다시 쏠 수 있게 한다.
  const autoResetFiredRef = useRef<boolean>(false);
  // v2.1.2: 서버 측 로그 동기화 카운터
  const serverLogCountRef = useRef<number>(0);
  const selectedTaskIdRef = useRef<string | null>(null);

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
        .map(serverLogToEntry);
      serverLogCountRef.current = serverLogs.length;
      setLogs((prev) => [...prev, ...newEntries].slice(-200));
    },
    [replaceLogsFromTask],
  );

  const markServerSync = useCallback(() => {
    setLastServerSyncAt(Date.now());
  }, []);

  useEffect(() => {
    setSelectedQueueIds((prev) => {
      if (prev.size === 0) return prev;
      const visible = new Set(pendingQueueItems.map((item, index) => queueItemKey(item, index)));
      const next = new Set(Array.from(prev).filter((id) => visible.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [pendingQueueItems]);

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

  // ─── 초기 로드: 페이지 열 때 (또는 다시 돌아올 때) 활성 태스크 자동 복구 ───
  useEffect(() => {
    let cancelled = false;
    oneclickApi
      .getQueue()
      .then((queueState) => {
        if (!cancelled) {
          setPendingQueueItems(queueState.items || []);
          setQueueChannelTimes(queueState.channel_times || {});
        }
      })
      .catch(() => {
        if (!cancelled) setPendingQueueItems([]);
      });
    oneclickApi
      .list()
      .then(({ tasks }) => {
        if (cancelled) return;
        markServerSync();
        // v1.1.65: running 을 맨 앞으로 정렬 — "진행 중" 을 우선 선택/표시
        const activeList = (tasks || [])
          .filter((t) => ["prepared", "queued", "running"].includes(t.status))
          .sort((a, b) => {
            const order: Record<string, number> = { running: 0, queued: 1, prepared: 2 };
            return (order[a.status] ?? 9) - (order[b.status] ?? 9);
          });
        setActiveTasks(activeList);
        const active = activeList[0];
        if (active) {
          setTask(active);
          addLog(`[시스템] 활성 태스크 감지: ${active.topic}`, "info");
          if (activeList.length > 1) {
            addLog(
              `[시스템] 동시 진행/대기 중 ${activeList.length}건 — 상단 스트립에서 전환 가능`,
              "warn",
            );
          }
          if (active.current_step_name) {
            addLog(
              `[${active.current_step_name}] 진행 중 (${Math.round(active.progress_pct)}%)`,
              "warn",
            );
          }
          // estimate 정보 로그
          if (active.estimate) {
            const est = active.estimate;
            if (est.estimated_cost_krw) {
              addLog(
                `[정보] 예상 비용: ${formatKrw(est.estimated_cost_krw)} (${est.cost_tier || ""})`,
                "info",
              );
            }
            if (est.estimated_seconds) {
              addLog(
                `[정보] 예상 소요: ${formatDurationKo(est.estimated_seconds)}`,
                "info",
              );
            }
          }
          replaceLogsFromTask(active, [
            {
              time: timeStr(),
              msg: `[시스템] 활성 태스크 감지: ${active.topic}`,
              level: "info",
            },
          ]);
          lastPctValueRef.current = active.progress_pct;
          lastPctChangeRef.current = Date.now();
        } else {
          // 실시간 현황은 "현재 진행 중" 화면이다. 진행 중 태스크가 없을 때
          // 마지막 실패/고아 태스크를 자동으로 띄우면 페이지 진입만으로 복구된
          // 것처럼 보이고 실패 alert 까지 뜬다. 과거 실패/고아는 제작 큐의
          // 실패 표시를 눌러 명시적으로 확인한다.
          setTask(null);
          selectedTaskIdRef.current = null;
          serverLogCountRef.current = 0;
          setLogs([
            {
              time: timeStr(),
              msg: "[시스템] 현재 진행 중인 태스크가 없습니다.",
              level: "muted",
            },
          ]);
        }
      })
      .catch(() => {
        setTask(null);
        selectedTaskIdRef.current = null;
        serverLogCountRef.current = 0;
        addLog("[오류] 태스크 목록 로드 실패", "error");
      })
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [addLog, markServerSync, replaceLogsFromTask]);

  // ─── 폴링 + 로그 자동 생성 + 멈춤/에러 감지 ─────────────────────
  const prevStepRef = useRef<string | null>(null);
  const prevPctRef = useRef<number>(0);
  // v1.2.20: 실패 알림창은 task 별 1회만. ref 로 중복 방지.
  const alertedTaskIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!task) return;
    const done = ["completed", "failed", "cancelled"].includes(task.status);
    if (done) {
      syncLogsFromTask(task);
      if ((task.logs?.length || 0) > 0) {
        if (
          task.status === "failed" &&
          task.error &&
          alertedTaskIdRef.current !== task.task_id
        ) {
          alertedTaskIdRef.current = task.task_id;
          try {
            if (typeof window !== "undefined") {
              window.alert(
                `[제작 실패] ${task.topic || ""}\n\n` +
                  `단계: ${task.current_step_name || "알 수 없음"}\n` +
                  `원인: ${task.error}`,
              );
            }
          } catch {
            // alert 차단 환경에서는 로그 패널만 표시한다.
          }
        }
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
          // v1.2.20: 모델 API 연결 실패 / 폴백 비활성화로 멈춘 경우 즉시 알림창.
          // 사용자 요구 — "API 이용할 때 설정된 모델의 API 연결 안되있을때 알림창
          // 띄우고 풀백으로 처리하지마". 같은 task 에 대해 1회만 띄운다 (ref 가드).
          if (alertedTaskIdRef.current !== task.task_id) {
            alertedTaskIdRef.current = task.task_id;
            try {
              if (typeof window !== "undefined") {
                window.alert(
                  `[제작 실패] ${task.topic || ""}\n\n` +
                    `단계: ${task.current_step_name || "알 수 없음"}\n` +
                    `원인: ${task.error}`,
                );
              }
            } catch {
              // alert 차단 환경에서는 배너만 표시 (조용히)
            }
          }
        }
      } else {
        addLog(`[취소됨] 사용자에 의해 제작 중단`, "warn");
      }
      return;
    }
    pollRef.current = setTimeout(async () => {
      try {
        const fresh = await resolveLiveTask(task);
        markServerSync();
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
        if (fresh.progress_pct !== lastPctValueRef.current) {
          lastPctValueRef.current = fresh.progress_pct;
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
      }
    }, 2000);
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [task, addLog, stalled, markServerSync, syncLogsFromTask, resolveLiveTask]);

  // 로그 자동 스크롤
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleCancel = async () => {
    if (!task) return;
    try {
      const liveTask = await resolveLiveTask(task);
      const t = await oneclickApi.cancel(liveTask.task_id);
      markServerSync();
      setTask(t);
      syncLogsFromTask(t);
    } catch {}
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
      // 목록 재조회
      try {
        const [{ tasks }, queueState] = await Promise.all([
          oneclickApi.list(),
          oneclickApi.getQueue(),
        ]);
        markServerSync();
        setPendingQueueItems(queueState.items || []);
        setQueueChannelTimes(queueState.channel_times || {});
        const activeList = (tasks || [])
          .filter((t) => ["prepared", "queued", "running"].includes(t.status))
          .sort((a, b) => {
            const order: Record<string, number> = { running: 0, queued: 1, prepared: 2 };
            return (order[a.status] ?? 9) - (order[b.status] ?? 9);
          });
        setActiveTasks(activeList);
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
      const [{ tasks }, queueState] = await Promise.all([
        oneclickApi.list(),
        oneclickApi.getQueue(),
      ]);
      markServerSync();
      setPendingQueueItems(queueState.items || []);
      setQueueChannelTimes(queueState.channel_times || {});
      // v1.1.65: running 우선 정렬로 activeTasks 갱신
      const activeList = (tasks || [])
        .filter((t) => ["prepared", "queued", "running"].includes(t.status))
        .sort((a, b) => {
          const order: Record<string, number> = { running: 0, queued: 1, prepared: 2 };
          return (order[a.status] ?? 9) - (order[b.status] ?? 9);
        });
      setActiveTasks(activeList);
      const active = activeList[0];
      if (active) {
        setTask(active);
        addLog(`[시스템] 태스크 재연결: ${active.topic} (${Math.round(active.progress_pct)}%)`, "info");
        if (activeList.length > 1) {
          addLog(`[시스템] 동시 진행/대기 중인 작업 ${activeList.length}건 감지`, "warn");
        }
        replaceLogsFromTask(active, [
          {
            time: timeStr(),
            msg: `[시스템] 태스크 재연결: ${active.topic} (${Math.round(active.progress_pct)}%)`,
            level: "info",
          },
        ]);
        lastPctValueRef.current = active.progress_pct;
        lastPctChangeRef.current = Date.now();
        setPollFails(0);
        setStalled(false);
      } else {
        addLog("[시스템] 활성 태스크 없음", "muted");
      }
    } catch {
      addLog("[오류] 재연결 실패", "error");
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
      let targetIndex = index;
      if (direction === "up") targetIndex = Math.max(0, index - 1);
      if (direction === "down") targetIndex = Math.min(items.length - 1, index + 1);
      if (direction === "top") targetIndex = 0;
      if (targetIndex === index) return;

      const [moved] = items.splice(index, 1);
      items.splice(targetIndex, 0, moved);
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items,
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(updated.channel_times || {});
      markServerSync();
    } catch (e: any) {
      addLog(`[오류] 대기열 순서 변경 실패: ${e?.message || e}`, "error");
    } finally {
      setMovingQueueId(null);
    }
  };

  const deleteQueueItem = async (itemId: string | undefined, rowKey: string, title: string) => {
    if (!itemId || movingQueueId || queueBatchRunning) return;
    if (!confirm(`대기열에서 삭제할까요?\n\n${title}`)) return;
    setMovingQueueId(itemId);
    try {
      const queueState = await oneclickApi.getQueue();
      const items = (queueState.items || []).filter((item) => item.id !== itemId);
      const updated = await oneclickApi.setQueue({
        channel_times: queueState.channel_times,
        channel_presets: queueState.channel_presets,
        items,
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(updated.channel_times || {});
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

  const runQueueItemsNow = async (orderedKeys: string[]) => {
    const keys = Array.from(new Set(orderedKeys.filter(Boolean)));
    if (keys.length === 0 || queueBatchRunning) return;
    setQueueBatchRunning(true);
    try {
      const [{ tasks }, queueState] = await Promise.all([
        oneclickApi.list(),
        oneclickApi.getQueue(),
      ]);
      markServerSync();
      const currentItems = queueState.items || [];
      const keyToOrder = new Map(keys.map((key, index) => [key, index]));
      const selected: OneClickQueueItem[] = [];
      const remaining: OneClickQueueItem[] = [];
      currentItems.forEach((item, index) => {
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
          items: [...stillLiveNext, cancelled, ...normalRemaining],
        });
        setPendingQueueItems(updated.items || []);
        setQueueChannelTimes(updated.channel_times || {});
        setSelectedQueueIds(new Set());
        markServerSync();
        addLog(`[시스템] 다음 실행 예약 취소: ${cancelled.topic}`, "warn");
        await handleRefresh();
        return;
      }

      const promoted = selected.map((item) => ({
        ...item,
        queued_source: "manual",
        queued_at: now,
        queued_note: selected.length > 1
          ? `실시간 현황에서 선택 ${selected.length}건 즉시 순차 실행`
          : "실시간 현황에서 바로 실행",
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
        items: [...existingLiveNext, ...promoted, ...normalRemaining],
      });
      setPendingQueueItems(updated.items || []);
      setQueueChannelTimes(updated.channel_times || {});
      setSelectedQueueIds(new Set());

      const activeList = (tasks || []).filter((t) => ["prepared", "queued", "running"].includes(t.status));
      const hasActiveWork =
        activeList.length > 0 ||
        Boolean(task && ["prepared", "queued", "running"].includes(task.status));
      if (!hasActiveWork) {
        await oneclickApi.runQueueNext(promoted[0].channel || 1);
        addLog(`[시스템] 선택 ${promoted.length}건 즉시 실행 시작: ${promoted[0].topic}`, "success");
      } else {
        addLog(`[시스템] 선택 ${promoted.length}건을 다음 실행 목록 뒤에 추가했습니다. 현재 작업 완료 후 예약한 순서대로 실행합니다.`, "success");
      }
      await handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 선택 작업 즉시 실행 실패: ${e?.message || e}`, "error");
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
        .filter((t) => ["failed", "cancelled", "paused"].includes(t.status))
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
      setOrphanProjects(orphans);
      addLog(
        `[시스템] 복구 대상 로드: 실패 ${failed.length}건 / 고아 ${orphanRes.count || 0}건`,
        failed.length || orphanRes.count ? "warn" : "muted",
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
    lastPctValueRef.current = failed.progress_pct;
    lastPctChangeRef.current = Date.now();
    setStalled(false);
  };

  const handleRecoverOrphan = async (projectId: string) => {
    setRecoveringId(projectId);
    try {
      const recovered = await oneclickApi.recoverProject(projectId);
      markServerSync();
      setTask(recovered);
      replaceLogsFromTask(recovered, [
        {
          time: timeStr(),
          msg: `[시스템] 고아 프로젝트 불러옴: ${recovered.topic}`,
          level: "warn",
        },
      ]);
      setStalled(false);
      await loadRecoveryContent(recoveryChannel);
    } catch (e: any) {
      addLog(`[오류] 고아 프로젝트 불러오기 실패: ${e?.message || e}`, "error");
    } finally {
      setRecoveringId(null);
    }
  };

  // v1.1.65: 리스트 자동 새로고침 — 5초마다 activeTasks 만 갱신(상세 뷰엔 영향 X).
  // 기존 2초 단일-task 폴링은 그대로 유지되고, 이건 별도 주기로 전체 목록만 점검해
  // 새로 생긴 queued/prepared 를 스트립에 반영한다.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const [{ tasks }, queueState] = await Promise.all([
          oneclickApi.list(),
          oneclickApi.getQueue(),
        ]);
        if (cancelled) return;
        markServerSync();
        setPendingQueueItems(queueState.items || []);
        setQueueChannelTimes(queueState.channel_times || {});
        const activeList = (tasks || [])
          .filter((t) => ["prepared", "queued", "running"].includes(t.status))
          .sort((a, b) => {
            const order: Record<string, number> = { running: 0, queued: 1, prepared: 2 };
            return (order[a.status] ?? 9) - (order[b.status] ?? 9);
          });
        setActiveTasks(activeList);
      } catch {
        // 네트워크 실패는 단일-task 폴링 쪽에서 이미 감지/로그. 여기선 조용히 무시.
      }
    };
    const id = setInterval(tick, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [markServerSync]);

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
  const isCompleted = task?.status === "completed";
  const pct = isCompleted ? 100 : Math.round(task?.progress_pct || 0);
  // 경과 시간 (실시간 카운트)
  const [elapsedStr, setElapsedStr] = useState("--:--");
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

  const runningTasks = activeTasks.filter((t) => t.status === "running");
  const waitingTasks = activeTasks.filter(
    (t) => t.status === "queued" || t.status === "prepared",
  );
  const activeDisplayTasks =
    task && ["prepared", "queued", "running"].includes(task.status)
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
    <div className="p-3 sm:p-4 lg:p-5 xl:p-6 h-full flex flex-col gap-3.5 lg:gap-5">
      {/* 헤더 */}
      <div className="flex flex-col gap-3 xl:gap-4 flex-shrink-0">
        <div className="flex flex-wrap items-center gap-2 lg:gap-3">
          <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold leading-none text-white">실시간 현황</h1>
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
            className="flex items-center gap-1.5 text-[11px] sm:text-xs lg:text-sm font-semibold bg-red-600 text-white hover:bg-red-500 border border-red-500/60 px-2 sm:px-2.5 lg:px-3 py-1.5 sm:py-2 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="서버 + ComfyUI 의 모든 작업을 강제 중단합니다. 생성 파일은 보존."
          >
            <AlertTriangle size={14} className={emergencyStopping ? "animate-pulse" : ""} />
            {emergencyStopping ? "중단 중..." : "모든 작업 중단"}
          </button>
        </div>
      </div>

      {/* v1.1.67: 상단은 요약만 남기고 전체 큐/순서 변경은 팝업으로 분리한다. */}
      {(() => {
        const queueEntries = [
          ...activeDisplayTasks.map((item) => ({ kind: "task" as const, item })),
          ...pendingQueueItems.map((item, index) => ({ kind: "queue" as const, item, index })),
        ];
        const activeCount = activeDisplayTasks.length;
        const persistedCount = pendingQueueItems.length;
        const runningTask = activeDisplayTasks.find((item) => item.status === "running") || activeDisplayTasks[0] || null;
        const channelCounts = queueEntries.reduce<Record<number, number>>((acc, entry) => {
          const ch = entry.kind === "queue" ? entry.item.channel || 1 : entry.item.channel || 1;
          acc[ch] = (acc[ch] || 0) + 1;
          return acc;
        }, {});
        const timeToMinutes = (value: string | null | undefined) => {
          if (!value) return Number.POSITIVE_INFINITY;
          const [hh, mm] = value.split(":").map((part) => Number(part));
          if (!Number.isFinite(hh) || !Number.isFinite(mm)) return Number.POSITIVE_INFINITY;
          return hh * 60 + mm;
        };
        const channelsByTime = [1, 2, 3, 4].sort((a, b) => {
          const diff = timeToMinutes(queueChannelTimes[String(a)]) - timeToMinutes(queueChannelTimes[String(b)]);
          return diff || a - b;
        });
        const liveNextEntries: { item: OneClickQueueItem; index: number; cycle: number }[] = [];
        const timedItems: { item: OneClickQueueItem; index: number }[] = [];
        pendingQueueItems.forEach((item, index) => {
          if (index === liveNextEntries.length && isLiveNextQueueItem(item)) {
            liveNextEntries.push({ item, index, cycle: -1 });
          } else {
            timedItems.push({ item, index });
          }
        });
        const queueEntriesByTime: { item: OneClickQueueItem; index: number; cycle: number }[] = [];
        const byChannel = new Map<number, { item: OneClickQueueItem; index: number }[]>();
        timedItems.forEach(({ item, index }) => {
          const ch = item.channel || 1;
          const rows = byChannel.get(ch) || [];
          rows.push({ item, index });
          byChannel.set(ch, rows);
        });
        const maxCycle = Math.max(0, ...Array.from(byChannel.values()).map((rows) => rows.length));
        for (let cycle = 0; cycle < maxCycle; cycle += 1) {
          for (const ch of channelsByTime) {
            const row = byChannel.get(ch)?.[cycle];
            if (row) queueEntriesByTime.push({ ...row, cycle });
          }
        }
        const visibleQueueEntries = [...liveNextEntries, ...queueEntriesByTime];
        const nextQueueItems = visibleQueueEntries.slice(0, 2).map(({ item }) => item);
        const visibleQueueKeys = visibleQueueEntries.map(({ item, index }) => queueItemKey(item, index));
        const selectedVisibleCount = visibleQueueKeys.filter((key) => selectedQueueIds.has(key)).length;
        const allVisibleSelected = visibleQueueKeys.length > 0 && selectedVisibleCount === visibleQueueKeys.length;
        const renderQueueRow = (item: OneClickQueueItem, index: number) => {
          const isMoving = movingQueueId === item.id;
          const meta = formatQueueWaitingMeta(item, queueChannelTimes);
          const rowKey = queueItemKey(item, index);
          const checked = selectedQueueIds.has(rowKey);
          const displayTitle = queueTitle(item);
          const liveNextRank =
            isLiveNextQueueItem(item) &&
            pendingQueueItems.slice(0, index).every((prev) => isLiveNextQueueItem(prev))
              ? index + 1
              : 0;
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
              className={`flex min-h-11 items-center gap-2 border-b border-border/70 px-3 py-1.5 text-sm last:border-b-0 hover:bg-blue-400/5 ${
                checked ? "bg-accent-primary/10" : ""
              }`}
              title={`${item.topic} — ${meta.sourceLabel} — ${meta.scheduleLabel}`}
            >
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  setSelectedQueueIds((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(rowKey);
                    else next.delete(rowKey);
                    return next;
                  });
                }}
                className="h-4 w-4 shrink-0 accent-accent-primary"
                title="즉시 순차 실행 선택"
              />
              <span className="w-12 shrink-0 rounded bg-blue-400/15 px-1.5 py-0.5 text-center text-[10px] font-bold text-blue-200">
                #{index + 1}
              </span>
              <span className="w-9 shrink-0 rounded bg-bg-secondary px-1.5 py-0.5 text-center text-[10px] font-semibold text-gray-300">
                CH{item.channel || 1}
              </span>
              <span className="w-14 shrink-0 rounded border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-center text-[10px] font-bold text-violet-200">
                {formatEpisodeBadge(item)}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold text-blue-100">{displayTitle}</div>
                <div className="mt-1 flex min-w-0 flex-wrap items-center gap-1.5 text-[11px]">
                  <span className={`rounded border px-1.5 py-0.5 font-semibold ${meta.sourceClass}`}>
                    {meta.sourceLabel}
                  </span>
                  <span className="rounded border border-emerald-400/25 bg-emerald-400/10 px-1.5 py-0.5 font-semibold text-emerald-200">
                    {meta.scheduleLabel}
                  </span>
                  <span className="text-gray-500">{meta.queuedAt}</span>
                  {isPromotedNext && (
                    <span className="rounded border border-amber-300/40 bg-amber-300/15 px-1.5 py-0.5 font-bold text-amber-200">
                      다음 실행 #{liveNextRank}{nextStartLabel ? ` · 예상 ${nextStartLabel}` : ""}
                    </span>
                  )}
                  {meta.note && <span className="min-w-0 truncate text-gray-500">· {meta.note}</span>}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  onClick={() => void runQueueItemsNow([rowKey])}
                  disabled={queueBatchRunning}
                  className={`inline-flex min-w-14 items-center justify-center gap-1 rounded border px-2 py-0.5 text-[10px] font-bold disabled:opacity-40 ${
                    isPromotedNext
                      ? "border-amber-300/50 bg-amber-300/15 text-amber-200 hover:bg-amber-300/25"
                      : "border-accent-success/40 bg-accent-success/10 text-accent-success hover:bg-accent-success/20"
                  }`}
                  title={isPromotedNext ? "다음 실행 예약 취소" : "자동 실행 시간을 무시하고 이 작업을 다음 순서로 실행"}
                >
                  <PlayCircle size={11} />
                  {isPromotedNext ? "취소" : "실행"}
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "top")}
                  disabled={isMoving || index === 0}
                  className="rounded border border-border bg-bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-gray-400 hover:text-gray-100 disabled:opacity-30"
                  title="맨 위로"
                >
                  맨위
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "up")}
                  disabled={isMoving || index === 0}
                  className="rounded border border-border bg-bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-gray-400 hover:text-gray-100 disabled:opacity-30"
                  title="한 칸 위"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => void moveQueueItem(item.id, "down")}
                  disabled={isMoving || index >= pendingQueueItems.length - 1}
                  className="rounded border border-border bg-bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-gray-400 hover:text-gray-100 disabled:opacity-30"
                  title="한 칸 아래"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => void deleteQueueItem(item.id, rowKey, displayTitle)}
                  disabled={isMoving || queueBatchRunning}
                  className="inline-flex items-center justify-center rounded border border-red-400/30 bg-red-400/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-300 hover:bg-red-400/20 disabled:opacity-30"
                  title="대기열에서 삭제"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          );
        };
        return (
          <div className="flex-shrink-0 rounded-xl border border-border bg-bg-secondary px-3 py-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <Activity size={14} className="text-accent-secondary" />
                <span className="text-sm font-bold text-gray-100">작업 대기열</span>
              </div>
              <span className="rounded border border-amber-400/25 bg-amber-400/10 px-2 py-0.5 text-[11px] font-semibold text-amber-300">
                진행 {activeCount}
              </span>
              <span className="rounded border border-blue-400/25 bg-blue-400/10 px-2 py-0.5 text-[11px] font-semibold text-blue-200">
                대기 {persistedCount}
              </span>
              {[1, 2, 3, 4].map((ch) => (
                <span
                  key={`queue-count-${ch}`}
                  className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${
                    channelCounts[ch]
                      ? "border-border bg-bg-primary text-gray-300"
                      : "border-border/60 bg-bg-primary/40 text-gray-600"
                  }`}
                >
                  CH{ch} {channelCounts[ch] || 0}
                </span>
              ))}
              <div className="ml-auto flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setQueuePanelOpen(true)}
                  className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-blue-400/30 bg-blue-400/10 px-3 py-1.5 text-xs font-semibold text-blue-200 hover:bg-blue-400/15"
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
                  className="inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/15"
                >
                  <AlertTriangle size={13} />
                  실패/고아 가져오기
                </button>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-1 gap-1.5 xl:grid-cols-3">
              {runningTask ? (
                <button
                  type="button"
                  onClick={() => {
                    setTask(runningTask);
                    replaceLogsFromTask(runningTask, [
                      {
                        time: timeStr(),
                        msg: `[시스템] 선택한 태스크 표시: ${runningTask.topic}`,
                        level: "info",
                      },
                    ]);
                    lastPctValueRef.current = runningTask.progress_pct;
                    lastPctChangeRef.current = Date.now();
                    setStalled(false);
                  }}
                  className="flex min-w-0 items-center gap-2 rounded-md border border-amber-400/35 bg-amber-400/10 px-2.5 py-1.5 text-left text-xs"
                  title={taskTitle(runningTask)}
                >
                  <span className="shrink-0 rounded bg-amber-300 px-1.5 py-0.5 text-[10px] font-bold text-black">
                    진행
                  </span>
                  <span className="min-w-0 flex-1 truncate font-semibold text-gray-100">
                    {taskTitle(runningTask)}
                  </span>
                  <span className="shrink-0 tabular-nums text-gray-200">{Math.round(runningTask.progress_pct)}%</span>
                </button>
              ) : (
                <div className="rounded-md border border-dashed border-border bg-bg-primary/35 px-2.5 py-1.5 text-xs text-gray-500">
                  진행 중인 작업 없음
                </div>
              )}
              {nextQueueItems.map((item, index) => {
                const meta = formatQueueWaitingMeta(item, queueChannelTimes);
                const displayTitle = queueTitle(item);
                return (
                  <div
                    key={`next-queue-${item.id || index}`}
                    className="flex min-w-0 items-center gap-2 rounded-md border border-border bg-bg-primary/55 px-2.5 py-1.5 text-xs"
                    title={`${item.topic} · ${meta.sourceLabel} · ${meta.scheduleLabel}`}
                  >
                    <span className="shrink-0 rounded bg-blue-400/15 px-1.5 py-0.5 text-[10px] font-bold text-blue-200">
                      다음 {index + 1}
                    </span>
                    <span className="shrink-0 rounded bg-bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-gray-300">
                      CH{item.channel || 1}
                    </span>
                    <span className="shrink-0 rounded border border-violet-400/30 bg-violet-400/10 px-1.5 py-0.5 text-[10px] font-bold text-violet-200">
                      {formatEpisodeBadge(item)}
                    </span>
                    <span className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold ${meta.sourceClass}`}>
                      {meta.sourceLabel}
                    </span>
                    <span className="hidden shrink-0 text-[11px] text-emerald-300 lg:inline">
                      {meta.scheduleLabel}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-semibold text-blue-100">{displayTitle}</span>
                  </div>
                );
              })}
              {nextQueueItems.length === 0 && !runningTask && (
                <div className="rounded-md border border-dashed border-border bg-bg-primary/35 px-2.5 py-1.5 text-xs text-gray-500 xl:col-span-2">
                  대기 중인 작업이 없습니다.
                </div>
              )}
            </div>

            {queuePanelOpen && (
              <>
                <button
                  type="button"
                  aria-label="대기열 팝업 닫기"
                  onClick={() => setQueuePanelOpen(false)}
                  className="fixed inset-0 z-40 cursor-default bg-black/35"
                />
                <div className="fixed bottom-6 left-4 right-4 top-24 z-50 flex flex-col overflow-hidden rounded-xl border border-blue-400/25 bg-[#10101a] shadow-2xl shadow-black/50 lg:left-[18rem] lg:right-8">
                  <div className="flex flex-wrap items-center gap-2 border-b border-border/70 px-4 py-3">
                    <ListChecks size={15} className="text-blue-200" />
                    <div className="mr-auto">
                      <div className="text-sm font-bold text-gray-100">전체 작업 큐</div>
                      <div className="text-[11px] text-gray-500">
                        다음 실행 예약을 먼저, 나머지는 채널 작업 시간순으로 고정 정렬합니다. 현재 대기 {persistedCount}건.
                      </div>
                    </div>
                    <span className="rounded-md border border-blue-400/30 bg-blue-400/10 px-2.5 py-1 text-[11px] font-bold text-blue-200">
                      작업 시간순 고정
                    </span>
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
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-primary px-2.5 py-1 text-[11px] font-semibold text-gray-300 hover:bg-bg-tertiary disabled:opacity-40"
                    >
                      {allVisibleSelected ? "전체 해제" : "전체 선택"}
                    </button>
                    <button
                      type="button"
                      onClick={() => void runQueueItemsNow(visibleQueueKeys.filter((key) => selectedQueueIds.has(key)))}
                      disabled={selectedVisibleCount === 0 || queueBatchRunning}
                      className="inline-flex items-center gap-1.5 rounded-md border border-accent-success/40 bg-accent-success/15 px-3 py-1 text-[11px] font-bold text-accent-success hover:bg-accent-success/25 disabled:opacity-40"
                      title="체크한 작업을 큐 맨 앞으로 올리고 자동 실행 시간을 무시해서 순차 실행"
                    >
                      {queueBatchRunning ? <Loader2 size={12} className="animate-spin" /> : <PlayCircle size={12} />}
                      선택 {selectedVisibleCount}건 실행
                    </button>
                    <button
                      type="button"
                      onClick={handleRefresh}
                      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-primary px-2.5 py-1 text-[11px] font-semibold text-gray-300 hover:bg-bg-tertiary"
                    >
                      <RefreshCw size={12} />
                      새로고침
                    </button>
                    <button
                      type="button"
                      onClick={() => setQueuePanelOpen(false)}
                      className="inline-flex h-7 w-7 items-center justify-center rounded-md border border-border bg-bg-primary text-gray-400 hover:text-gray-100"
                      title="닫기"
                    >
                      <X size={13} />
                    </button>
                  </div>
                  <div className="min-h-0 flex-1 overflow-y-auto p-3">
                    {pendingQueueItems.length === 0 ? (
                      <div className="rounded-lg border border-dashed border-border bg-bg-primary/35 px-4 py-8 text-center text-sm text-gray-500">
                        대기 중인 작업이 없습니다.
                      </div>
                    ) : (
                      <div className="overflow-hidden rounded-lg border border-border bg-bg-primary/40">
                        <div className="flex flex-wrap items-center gap-2 border-b border-border/70 bg-bg-secondary/70 px-3 py-2 text-[11px] text-gray-400">
                          <span className="font-bold text-gray-200">작업 시간순</span>
                          {liveNextEntries.length > 0 && (
                            <span className="rounded border border-amber-300/40 bg-amber-300/15 px-2 py-0.5 font-bold text-amber-200">
                              다음 실행 {liveNextEntries.length}건
                            </span>
                          )}
                          {channelsByTime.map((ch) => (
                            <span key={`time-order-${ch}`} className="rounded border border-border bg-bg-primary px-2 py-0.5 font-semibold">
                              CH{ch} {queueChannelTimes[String(ch)] || "수동"}
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
              <div className="fixed left-4 right-4 top-36 z-50 max-h-[420px] overflow-y-auto rounded-xl border border-amber-500/25 bg-[#10101a] p-3 shadow-2xl shadow-black/50 lg:left-72 lg:right-8">
                <div className="mb-3 flex flex-wrap items-center gap-2 border-b border-border/70 pb-3">
                  <div className="mr-auto flex min-w-[160px] items-center gap-2">
                    <AlertTriangle size={14} className="text-amber-300" />
                    <div>
                      <div className="text-sm font-bold text-gray-100">실패/고아 가져오기</div>
                      <div className="text-[11px] text-gray-500">
                        실패 {failedTasks.length}건 · 고아 {orphanProjects.length}건
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
                    disabled={recoveryLoading}
                    className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-primary px-2.5 py-1 text-[11px] font-semibold text-gray-300 hover:bg-bg-tertiary disabled:opacity-50"
                  >
                    <RefreshCw size={12} className={recoveryLoading ? "animate-spin" : ""} />
                    새로고침
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
                ) : failedTasks.length === 0 && orphanProjects.length === 0 ? (
                  <div className="text-sm text-gray-500">불러올 실패/고아 컨텐츠가 없습니다.</div>
                ) : (
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
                    <div>
                      <div className="mb-2 text-xs font-bold text-red-300">실패/중단 태스크 {failedTasks.length}건</div>
                      <div className="space-y-2 max-h-44 overflow-y-auto pr-1">
                        {failedTasks.map((item) => (
                          <div key={item.task_id} className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/5 px-3 py-2">
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-semibold text-gray-200">{taskTitle(item)}</div>
                              <div className="text-xs text-gray-500">
                                {item.channel ? `CH${item.channel} · ` : ""}{item.current_step_name || "단계 미상"} · {Math.round(item.progress_pct || 0)}%
                              </div>
                            </div>
                            <button
                              onClick={() => {
                                handleSelectFailedTask(item);
                                setRecoveryOpen(false);
                              }}
                              className="shrink-0 rounded-md border border-red-400/30 bg-red-400/10 px-2.5 py-1 text-xs font-semibold text-red-200 hover:bg-red-400/15"
                            >
                              불러오기
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
                              onClick={() => {
                                void handleRecoverOrphan(item.project_id);
                                setRecoveryOpen(false);
                              }}
                              disabled={recoveringId === item.project_id}
                              className="shrink-0 rounded-md border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-xs font-semibold text-amber-200 hover:bg-amber-400/15 disabled:opacity-50"
                            >
                              {recoveringId === item.project_id ? "불러오는 중..." : "불러오기"}
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

      {/* 에러/멈춤 경고 배너 */}
      {isFailed && task?.error && (
        <div className="bg-accent-danger/10 border border-accent-danger/30 rounded-xl p-5 flex-shrink-0">
          <div className="flex items-start gap-3">
            <AlertTriangle
              size={18}
              className="text-accent-danger flex-shrink-0 mt-0.5"
            />
            <div className="flex-1">
              <div className="text-base font-bold text-accent-danger mb-1.5">
                제작 실패
                {task.topic && (
                  <span className="ml-2 text-gray-300 font-medium">{taskTitle(task)}</span>
                )}
              </div>
              <div className="text-sm text-gray-300 leading-relaxed">
                {task.error}
              </div>
              <div className="text-sm text-gray-500 mt-2">
                단계: {task.current_step_name || "알 수 없음"} · 진행률:{" "}
                {pct}% · 시각:{" "}
                {task.finished_at
                  ? new Date(task.finished_at).toLocaleString("ko-KR")
                  : "-"}
              </div>
              <div className="mt-4 flex items-center gap-2.5 flex-wrap">
                <button
                  onClick={handleResume}
                  disabled={resuming}
                  className="flex items-center gap-2 bg-accent-primary hover:bg-purple-600 text-white text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  {resuming ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RefreshCw size={14} />
                  )}
                  이어서 하기
                </button>
                {/* v1.1.53: 전체 초기화 버튼 */}
                <button
                  onClick={() => handleReset(2)}
                  disabled={resetting}
                  className="flex items-center gap-1.5 bg-red-700/40 hover:bg-red-700/60 text-red-300 text-sm font-semibold px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50"
                >
                  {resetting ? (
                    <Loader2 size={14} className="animate-spin" />
                  ) : (
                    <RotateCcw size={14} />
                  )}
                  전체 초기화
                </button>
                {/* v1.1.52: 단계별 생성물 삭제 버튼 */}
                {(task.step_states?.["4"] === "completed" ||
                  task.step_states?.["4"] === "failed" ||
                  task.step_states?.["4"] === "running") && (
                  <button
                    onClick={() => handleClearStep(4, "이미지")}
                    disabled={clearing !== null}
                    className="flex items-center gap-1.5 bg-accent-danger/20 hover:bg-accent-danger/30 text-accent-danger text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {clearing === 4 ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <X size={13} />
                    )}
                    이미지 삭제
                  </button>
                )}
                {(task.step_states?.["5"] === "completed" ||
                  task.step_states?.["5"] === "failed" ||
                  task.step_states?.["5"] === "running") && (
                  <button
                    onClick={() => handleClearStep(5, "영상")}
                    disabled={clearing !== null}
                    className="flex items-center gap-1.5 bg-accent-danger/20 hover:bg-accent-danger/30 text-accent-danger text-sm font-semibold px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50"
                  >
                    {clearing === 5 ? (
                      <Loader2 size={13} className="animate-spin" />
                    ) : (
                      <X size={13} />
                    )}
                    영상 삭제
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      {stalled && isRunning && (
        <div className="bg-amber-400/10 border border-amber-400/30 rounded-xl px-5 py-3.5 flex items-center gap-3 flex-shrink-0">
          <AlertTriangle size={16} className="text-amber-400 flex-shrink-0" />
          <span className="text-sm text-amber-300">
            90초 이상 진행률 변화 없음 — API 응답 지연 또는 대용량 처리 중일 수
            있습니다. 백엔드에서 작업은 계속 진행됩니다.
          </span>
        </div>
      )}
      {pollFails >= 3 && isRunning && (
        <div className="bg-accent-danger/10 border border-accent-danger/30 rounded-xl px-5 py-3.5 flex items-center gap-3 flex-shrink-0">
          <AlertTriangle
            size={16}
            className="text-accent-danger flex-shrink-0"
          />
          <span className="text-sm text-red-300">
            서버 응답 없음 ({pollFails}회 연속 실패) — 백엔드 서버가 실행 중인지
            확인해 주세요. 서버 측 작업은 독립적으로 계속 진행됩니다.
          </span>
          <button
            onClick={handleRefresh}
            className="ml-auto text-sm bg-accent-danger/20 text-accent-danger rounded-lg px-3 py-1.5 hover:bg-accent-danger/30"
          >
            재연결
          </button>
        </div>
      )}
      {isRunning && (
        <div
          className={`rounded-xl px-5 py-3 flex items-center gap-3 flex-shrink-0 border ${
            pollFails >= 1 || serverSyncStale
              ? "bg-amber-400/10 border-amber-400/30"
              : "bg-bg-secondary border-border"
          }`}
        >
          <Clock
            size={16}
            className={pollFails >= 1 || serverSyncStale ? "text-amber-300" : "text-gray-500"}
          />
          <span
            className={`text-sm ${
              pollFails >= 1 || serverSyncStale ? "text-amber-200" : "text-gray-400"
            }`}
          >
            {serverSyncLabel}
            {pollFails >= 1 || serverSyncStale ? " · 화면 숫자가 잠시 늦을 수 있습니다" : ""}
          </span>
        </div>
      )}

      {/* 파이프라인
          v1.2.13: 반응형으로 재작성.
          - xl 이상: 기존처럼 한 줄 6 스텝 + 화살표 커넥터.
          - xl 미만: flex-wrap 로 자동 줄바꿈, 스텝은 min-width 로 찌그러짐 방지,
            화살표는 줄바꿈과 충돌하므로 xl 미만에서 숨김. */}
      {/* 본체: 로그 + 우측 패널
          v1.2.13: xl 미만에서는 세로 1열로 붕괴 (우측 패널이 아래로). */}
      <div className="flex-1 grid grid-cols-1 xl:grid-cols-[1fr_360px] gap-3.5 lg:gap-5 min-h-0">
        {/* 로그 */}
        <div className="bg-[#08080e] border border-border rounded-xl flex flex-col overflow-hidden">
          <div className="flex items-center gap-2.5 px-3.5 sm:px-4 lg:px-5 py-3 border-b border-border flex-shrink-0">
            <span className="relative flex h-2.5 w-2.5">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isRunning ? "bg-accent-success" : "bg-gray-600"} opacity-75`}
              />
              <span
                className={`relative inline-flex rounded-full h-2.5 w-2.5 ${isRunning ? "bg-accent-success" : "bg-gray-600"}`}
              />
            </span>
            <span className="text-sm font-bold text-gray-200">
              제작 로그
            </span>
            <span className="text-sm text-gray-600 ml-auto">
              {logs.length}줄
            </span>
          </div>
          <div className="flex-1 overflow-y-auto px-3.5 sm:px-4 lg:px-5 py-3 font-mono text-sm leading-7 space-y-1.5">
            {logs.map((log, i) => (
              <div key={i} className="flex gap-3">
                <span className="text-gray-600 flex-shrink-0 select-none">
                  {log.time}
                </span>
                <span className={logColor(log.level)}>{log.msg}</span>
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>

        {/* 우측 패널 */}
        <div className="flex flex-col gap-3 lg:gap-4 overflow-y-auto">
          {/* 단계별 작업 활동 — 살아있는지/얼마 남았는지/멈췄는지 시각화 */}
          <ActivityPanel
            task={task}
            isRunningTask={Boolean(isRunning)}
            clearingStep={clearing}
            rerunningStep={rerunningStep}
            uploadingStep={uploadingStep}
            onClearStep={handleClearStep}
            onRerunStep={handleRerunFromStep}
            onReupload={handleReupload}
          />

          {/* 단계 상세 */}
          <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
            <h3
              className={`text-base font-bold mb-4 ${
                isFailed
                  ? "text-accent-danger"
                  : isCompleted
                    ? "text-accent-success"
                    : "text-amber-400"
              }`}
            >
              {isRunning
                ? `현재 단계: ${task?.current_step_name || "준비 중"}`
                : isCompleted
                  ? "제작 완료"
                  : isFailed
                    ? "제작 실패"
                    : "대기 중"}
            </h3>
            <div className="space-y-3 text-sm">
              {task?.current_step_completed !== undefined &&
                task?.current_step_total && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">처리 컷</span>
                    <span className="text-gray-200 font-medium">
                      {task.current_step_completed} / {task.current_step_total}
                    </span>
                  </div>
                )}
              <div className="flex justify-between">
                <span className="text-gray-500">
                  <Clock size={13} className="inline mr-1.5" />
                  경과 시간
                </span>
                <span className="text-gray-200 font-mono">{elapsedStr}</span>
              </div>
              {estimatedRemaining !== null && isRunning && (
                <div className="flex justify-between">
                  <span className="text-gray-500">
                    <Timer size={13} className="inline mr-1.5" />
                    예상 잔여
                  </span>
                  <span className="text-gray-200 font-mono">
                    ~{formatDurationKo(estimatedRemaining)}
                  </span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-500">전체 진행률</span>
                <span
                  className={`font-bold ${
                    isFailed
                      ? "text-accent-danger"
                      : isCompleted
                        ? "text-accent-success"
                        : "text-amber-400"
                  }`}
                >
                  {pct}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">총 컷 수</span>
                <span className="text-gray-200">{task?.total_cuts || "-"}</span>
              </div>
            </div>
          </div>

          {/* v1.1.52: 썸네일 */}
          {task && <ThumbnailPanel task={task} />}

          {/* 예상 비용/시간 */}
          {task?.estimate && (
            <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
              <h3 className="text-base font-bold text-gray-100 mb-4">
                <DollarSign size={15} className="inline mr-1.5" />
                예상 비용 · 시간
              </h3>
              <div className="space-y-3 text-sm">
                {task.estimate.estimated_cost_krw != null && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">예상 비용</span>
                    <span className="text-gray-200 font-medium">
                      {formatKrw(task.estimate.estimated_cost_krw)}
                      {task.estimate.estimated_cost_usd != null && (
                        <span className="text-gray-500 ml-1.5">
                          (${task.estimate.estimated_cost_usd.toFixed(2)})
                        </span>
                      )}
                    </span>
                  </div>
                )}
                {task.estimate.estimated_seconds != null && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">예상 소요</span>
                    <span className="text-gray-200 font-medium">
                      {formatDurationKo(task.estimate.estimated_seconds)}
                    </span>
                  </div>
                )}
                {task.estimate.cost_tier && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">비용 등급</span>
                    <span
                      className={`font-semibold ${
                        task.estimate.cost_tier === "cheap"
                          ? "text-accent-success"
                          : task.estimate.cost_tier === "normal"
                            ? "text-amber-400"
                            : "text-accent-danger"
                      }`}
                    >
                      {task.estimate.cost_tier === "cheap"
                        ? "저렴"
                        : task.estimate.cost_tier === "normal"
                          ? "보통"
                          : "비쌈"}
                    </span>
                  </div>
                )}
                {/* 비용 상세 (있으면) */}
                {task.estimate.cost_breakdown && (
                  <div className="mt-3 pt-3 border-t border-border space-y-2">
                    <div className="text-sm text-gray-500 font-medium mb-1.5">
                      비용 상세
                    </div>
                    {Object.entries(task.estimate.cost_breakdown).map(
                      ([key, val]) =>
                        val > 0 && (
                          <div
                            key={key}
                            className="flex justify-between text-sm"
                          >
                            <span className="text-gray-500">{key}</span>
                            <span className="text-gray-400">
                              ${(val as number).toFixed(3)}
                            </span>
                          </div>
                        ),
                    )}
                  </div>
                )}
                {/* 시간 상세 (있으면) */}
                {task.estimate.time_breakdown && (
                  <div className="mt-3 pt-3 border-t border-border space-y-2">
                    <div className="text-sm text-gray-500 font-medium mb-1.5">
                      시간 상세
                    </div>
                    {Object.entries(task.estimate.time_breakdown).map(
                      ([key, val]) =>
                        val > 0 && (
                          <div
                            key={key}
                            className="flex justify-between text-sm"
                          >
                            <span className="text-gray-500">{key}</span>
                            <span className="text-gray-400">
                              {formatDurationKo(val as number)}
                            </span>
                          </div>
                        ),
                    )}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
