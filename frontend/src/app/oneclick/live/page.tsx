"use client";

/**
 * v1.1.49 — 딸깍 대시보드 > 실시간 현황
 * - 파이프라인 진행 + 터미널 로그 + 미리보기 + 단계 상세
 * - 예상 비용/시간 표시
 * - 에러/멈춤 이유 표시
 * - 창 닫아도 백엔드 작업은 계속 진행 (페이지 복귀 시 자동 복구)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Loader2,
  CheckCircle2,
  PlayCircle,
  Circle,
  ArrowRight,
  Square,
  Clock,
  DollarSign,
  Timer,
  AlertTriangle,
  RefreshCw,
  RotateCcw,
  X,
} from "lucide-react";
import { oneclickApi, modelsApi, assetUrl, type OneClickTask, type ModelInfo } from "@/lib/api";
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
  if (!task || !task.step_states) return "pending";
  const val = task.step_states[stepKey];
  if (val === "completed" || val === "done") return "done";
  if (val === "running" || val === "in_progress") return "active";
  if (val === "failed" || val === "cancelled") return "failed";
  return "pending";
}

interface LogEntry {
  time: string;
  msg: string;
  level: "info" | "success" | "warn" | "error" | "muted";
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
            <span className="text-xs text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
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
              <span className="text-xs text-red-300/70 text-center leading-relaxed max-h-20 overflow-y-auto">
                {task.thumbnail_error}
              </span>
            )}
            <button
              onClick={handleRegenerate}
              className="text-xs text-accent-primary hover:underline mt-1"
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
          className="flex-1 text-xs bg-bg-primary text-gray-300 border border-border rounded-lg px-3 py-2 outline-none"
        >
          {imageModels.map((m) => (
            <option key={m.id} value={m.id}>{m.name || m.id}</option>
          ))}
        </select>
        <button
          onClick={handleRegenerate}
          disabled={regenerating || !pid || thumbStatus === "generating"}
          className="flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-lg bg-accent-primary/15 text-accent-primary border border-accent-primary/30 hover:bg-accent-primary/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <RefreshCw size={13} className={regenerating ? "animate-spin" : ""} />
          {regenerating ? "생성 중..." : "재생성"}
        </button>
      </div>
    </div>
  );
}


/** 단계별 작업 활동 패널 — 각 단계가 살아있는지 / 얼마나 진행됐는지 / 멈춤인지 시각화 */
function ActivityPanel({ task }: { task: OneClickTask | null }) {
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

  if (!task) {
    return (
      <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
        <h3 className="text-base font-bold text-gray-100 mb-4">단계별 작업 활동</h3>
        <div className="text-xs text-gray-600 py-6 text-center">
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
          <div className="flex items-center gap-1.5 text-[11px] text-gray-500">
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
          const cuts = Number(completedByStep[s.key] || 0);
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

          return (
            <div
              key={s.key}
              className={`rounded-lg border px-3.5 py-3 transition-colors ${
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
              <div className="flex items-center gap-2.5">
                <StepIcon state={state} />
                <div className="text-sm font-semibold text-gray-200 flex-1 truncate">
                  {s.label}
                </div>
                <div className="text-xs text-gray-500 tabular-nums">
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
                    <div className="flex items-center justify-between mt-1.5 text-[11px] text-gray-500">
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
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [pollFails, setPollFails] = useState(0);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  // 멈춤 감지: 진행률이 일정 시간 변하지 않으면 경고
  const lastPctChangeRef = useRef<number>(Date.now());
  const lastPctValueRef = useRef<number>(0);
  const [stalled, setStalled] = useState(false);
  // v2.1.2: 서버 측 로그 동기화 카운터
  const serverLogCountRef = useRef<number>(0);

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

  // ─── 초기 로드: 페이지 열 때 (또는 다시 돌아올 때) 활성 태스크 자동 복구 ───
  useEffect(() => {
    let cancelled = false;
    oneclickApi
      .list()
      .then(({ tasks }) => {
        if (cancelled) return;
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
          lastPctValueRef.current = active.progress_pct;
          lastPctChangeRef.current = Date.now();
        } else {
          // 완료/실패 태스크가 있으면 마지막 것 표시
          const latest = (tasks || [])
            .filter((t) => ["completed", "failed", "cancelled"].includes(t.status))
            .sort(
              (a, b) =>
                new Date(b.finished_at || b.created_at).getTime() -
                new Date(a.finished_at || a.created_at).getTime(),
            )[0];
          if (latest) {
            setTask(latest);
            if (latest.status === "completed") {
              addLog(`[시스템] 마지막 완료 태스크: ${latest.topic}`, "success");
            } else if (latest.status === "failed") {
              addLog(`[시스템] 마지막 실패 태스크: ${latest.topic}`, "error");
              if (latest.error) {
                addLog(`[오류 원인] ${latest.error}`, "error");
              }
            }
          } else {
            addLog("[시스템] 현재 진행 중인 태스크가 없습니다.", "muted");
          }
        }
      })
      .catch(() => {
        addLog("[오류] 태스크 목록 로드 실패", "error");
      })
      .finally(() => setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [addLog]);

  // ─── 폴링 + 로그 자동 생성 + 멈춤/에러 감지 ─────────────────────
  const prevStepRef = useRef<string | null>(null);
  const prevPctRef = useRef<number>(0);

  useEffect(() => {
    if (!task) return;
    const done = ["completed", "failed", "cancelled"].includes(task.status);
    if (done) {
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
    pollRef.current = setTimeout(async () => {
      try {
        const fresh = await oneclickApi.get(task.task_id);
        setPollFails(0); // 성공하면 리셋

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

        // 멈춤 감지: 진행률이 90초 이상 변하지 않으면 경고
        if (fresh.progress_pct !== lastPctValueRef.current) {
          lastPctValueRef.current = fresh.progress_pct;
          lastPctChangeRef.current = Date.now();
          setStalled(false);
        } else if (Date.now() - lastPctChangeRef.current > 90000) {
          if (!stalled) {
            addLog(
              `[경고] 90초 이상 진행률 변화 없음 — 처리가 지연되고 있을 수 있습니다`,
              "warn",
            );
            setStalled(true);
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
  }, [task, addLog, stalled]);

  // 로그 자동 스크롤
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const handleCancel = async () => {
    if (!task) return;
    try {
      const t = await oneclickApi.cancel(task.task_id);
      setTask(t);
    } catch {}
  };

  // v1.1.70: 전체 비상 정지 — Python asyncio + Redis cancel + ComfyUI /interrupt + /queue clear
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
    try {
      const r = await oneclickApi.emergencyStop();
      addLog(
        `[비상 정지] 태스크 ${r.stopped_count}건 중단 · ComfyUI interrupt=${r.comfyui_interrupt} · queue clear=${r.comfyui_queue_cleared}`,
        "warn",
      );
      if (r.errors?.length) {
        for (const e of r.errors) addLog(`[비상 정지 경고] ${e}`, "error");
      }
      // 목록 재조회
      const { tasks } = await oneclickApi.list();
      const activeList = (tasks || [])
        .filter((t) => ["prepared", "queued", "running"].includes(t.status))
        .sort((a, b) => {
          const order: Record<string, number> = { running: 0, queued: 1, prepared: 2 };
          return (order[a.status] ?? 9) - (order[b.status] ?? 9);
        });
      setActiveTasks(activeList);
      if (task) {
        try {
          const fresh = await oneclickApi.get(task.task_id);
          setTask(fresh);
        } catch {}
      }
    } catch (e: any) {
      addLog(`[오류] 비상 정지 실패: ${e?.message || e}`, "error");
    }
    setEmergencyStopping(false);
  };

  // v1.1.52: 특정 단계 생성물 삭제
  const [clearing, setClearing] = useState<number | null>(null);
  const handleClearStep = async (step: number, label: string) => {
    if (!task) return;
    if (!confirm(`${label} 생성물을 모두 삭제합니다. 계속하시겠습니까?`)) return;
    setClearing(step);
    try {
      const result = await oneclickApi.clearStep(task.task_id, step);
      addLog(`[시스템] ${label} 초기화 완료 — ${result.deleted_files}개 파일 삭제`, "warn");
      // 태스크 새로고침
      const fresh = await oneclickApi.get(task.task_id);
      setTask(fresh);
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
      const t = await oneclickApi.resume(task.task_id);
      setTask(t);
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
      const result = await oneclickApi.resetTask(task.task_id, fromStep);
      addLog(`[시스템] 초기화 완료 (${stepLabel}) — ${result.deleted_files}개 파일 삭제`, "warn");
      const fresh = await oneclickApi.get(task.task_id);
      setTask(fresh);
    } catch (e: any) {
      addLog(`[오류] 초기화 실패: ${e?.message || e}`, "error");
    }
    setResetting(false);
  };

  // 새로고침 (활성 태스크 다시 찾기)
  const handleRefresh = async () => {
    setLoading(true);
    try {
      const { tasks } = await oneclickApi.list();
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

  // v1.1.65: 리스트 자동 새로고침 — 5초마다 activeTasks 만 갱신(상세 뷰엔 영향 X).
  // 기존 2초 단일-task 폴링은 그대로 유지되고, 이건 별도 주기로 전체 목록만 점검해
  // 새로 생긴 queued/prepared 를 스트립에 반영한다.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const { tasks } = await oneclickApi.list();
        if (cancelled) return;
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
  }, []);

  const isRunning =
    task && ["prepared", "queued", "running"].includes(task.status);
  const isFailed = task?.status === "failed" || task?.status === "cancelled" || task?.status === "paused";
  const isFinished = task && ["completed", "failed", "cancelled", "paused"].includes(task.status);

  // v1.1.55: 스텝별 재실행
  const [rerunning, setRerunning] = useState(false);
  const handleRerunFromStep = async (fromStep: number) => {
    if (!task || rerunning) return;
    const stepLabel = STEPS.find((s) => s.key === String(fromStep))?.label || `Step ${fromStep}`;
    if (!confirm(`"${stepLabel}" 단계부터 재실행합니다. 이후 단계 데이터가 초기화됩니다.`)) return;
    setRerunning(true);
    try {
      await oneclickApi.resetTask(task.task_id, fromStep);
      addLog(`[시스템] ${stepLabel} 부터 초기화 완료 — 재실행 시작`, "info");
      await oneclickApi.resume(task.task_id);
      addLog(`[시스템] 재실행 시작`, "success");
      handleRefresh();
    } catch (e: any) {
      addLog(`[오류] 재실행 실패: ${e?.message || e}`, "error");
    } finally {
      setRerunning(false);
    }
  };
  const isCompleted = task?.status === "completed";
  const pct = Math.round(task?.progress_pct || 0);

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
    <div className="p-6 h-full flex flex-col gap-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-white">실시간 현황</h1>
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
              className="flex items-center gap-1.5 text-xs text-red-400 hover:text-red-300 hover:bg-red-500/10 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50"
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
            className="flex items-center gap-1.5 text-xs font-semibold bg-red-600 text-white hover:bg-red-500 border border-red-500/60 px-3 py-1.5 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="서버 + ComfyUI 의 모든 작업을 강제 중단합니다. 생성 파일은 보존."
          >
            <AlertTriangle size={14} className={emergencyStopping ? "animate-pulse" : ""} />
            {emergencyStopping ? "중단 중..." : "모든 작업 중단"}
          </button>
        </div>
        {isRunning && task && (
          <div className="flex items-center gap-2.5 bg-amber-400/10 text-amber-400 text-sm font-semibold rounded-lg px-4 py-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400" />
            </span>
            제작 중: {task.topic}
          </div>
        )}
        {isFailed && task && (
          <div className="flex items-center gap-2.5 bg-accent-danger/10 text-accent-danger text-sm font-semibold rounded-lg px-4 py-2">
            <AlertTriangle size={14} />
            실패: {task.topic}
          </div>
        )}
        {isCompleted && task && (
          <div className="flex items-center gap-2.5 bg-accent-success/10 text-accent-success text-sm font-semibold rounded-lg px-4 py-2">
            <CheckCircle2 size={14} />
            완료: {task.topic}
          </div>
        )}
      </div>

      {/* v1.1.66: 대기열 스트립 — 항상 표시. 다음 5개까지. 비어있으면 플레이스홀더.
          백엔드 _RUN_LOCK 으로 실제 실행은 1건씩 직렬이므로 prepared/queued 는 사실상
          대기열. 칩 클릭 시 상세 뷰 전환. */}
      {(() => {
        const MAX_VISIBLE = 5;
        const running = activeTasks.filter((t) => t.status === "running");
        const waiting = activeTasks.filter(
          (t) => t.status === "queued" || t.status === "prepared",
        );
        const visible = activeTasks.slice(0, MAX_VISIBLE);
        const overflow = Math.max(0, activeTasks.length - MAX_VISIBLE);
        return (
          <div className="flex-shrink-0 bg-bg-secondary border border-border rounded-xl p-3">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <Activity size={14} className="text-gray-400" />
              <span className="text-xs font-semibold text-gray-300">대기열</span>
              <span className="text-[10px] text-gray-500">
                진행 {running.length} · 대기 {waiting.length}
                {activeTasks.length > 0
                  ? ` · 총 ${activeTasks.length}건 (최대 ${MAX_VISIBLE}개 표시)`
                  : ""}
              </span>
              <span className="text-[10px] text-gray-600">
                · 한 번에 1건만 실행 (백엔드 직렬화)
              </span>
            </div>
            {activeTasks.length === 0 ? (
              <div className="text-[11px] text-gray-500 px-1 py-1.5">비어있음</div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {visible.map((t) => {
                  const selected = task?.task_id === t.task_id;
                  const statusClass =
                    t.status === "running"
                      ? "border-amber-400/60 text-amber-300 bg-amber-400/10"
                      : t.status === "queued"
                        ? "border-gray-600 text-gray-300 bg-bg-tertiary"
                        : "border-sky-500/50 text-sky-300 bg-sky-500/10";
                  const statusLabel =
                    t.status === "running"
                      ? "진행"
                      : t.status === "queued"
                        ? "대기"
                        : "준비";
                  return (
                    <button
                      key={t.task_id}
                      onClick={() => {
                        setTask(t);
                        lastPctValueRef.current = t.progress_pct;
                        lastPctChangeRef.current = Date.now();
                        setStalled(false);
                      }}
                      className={`flex items-center gap-1.5 text-xs rounded-lg px-2.5 py-1 border transition-colors hover:opacity-80 ${statusClass} ${
                        selected ? "ring-2 ring-accent-primary" : ""
                      }`}
                      title={`${t.topic} — ${Math.round(t.progress_pct)}%${
                        t.current_step_name ? ` · ${t.current_step_name}` : ""
                      }`}
                    >
                      <span className="text-[9px] font-bold uppercase tracking-wide">
                        {statusLabel}
                      </span>
                      {t.channel ? (
                        <span className="text-[9px] text-gray-500">ch{t.channel}</span>
                      ) : null}
                      <span className="max-w-[240px] truncate">{t.topic}</span>
                      <span className="text-[10px] text-gray-400 tabular-nums">
                        {Math.round(t.progress_pct)}%
                      </span>
                    </button>
                  );
                })}
                {overflow > 0 && (
                  <span
                    className="flex items-center text-[10px] text-gray-500 px-2 py-1"
                    title={`화면엔 ${MAX_VISIBLE}개까지만 노출. 나머지 ${overflow}건은 가려져 있음`}
                  >
                    +{overflow} 건 더
                  </span>
                )}
              </div>
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
                  <span className="ml-2 text-gray-300 font-medium">{task.topic}</span>
                )}
              </div>
              <div className="text-sm text-gray-300 leading-relaxed">
                {task.error}
              </div>
              <div className="text-xs text-gray-500 mt-2">
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
                    className="flex items-center gap-1.5 bg-accent-danger/20 hover:bg-accent-danger/30 text-accent-danger text-xs font-semibold px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50"
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
                    className="flex items-center gap-1.5 bg-accent-danger/20 hover:bg-accent-danger/30 text-accent-danger text-xs font-semibold px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50"
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
            className="ml-auto text-xs bg-accent-danger/20 text-accent-danger rounded-lg px-3 py-1.5 hover:bg-accent-danger/30"
          >
            재연결
          </button>
        </div>
      )}

      {/* 파이프라인 */}
      <div className="bg-bg-secondary border border-border rounded-xl p-5 flex-shrink-0">
        <h3 className="text-base font-bold text-gray-100 mb-5">
          파이프라인 진행
        </h3>
        <div className="flex items-start gap-2">
          {STEPS.map((step, i) => {
            const state = getStepState(task, step.key);

            // 스텝별 진행률 (0~100)
            const totalCuts = task?.total_cuts || 0;
            const doneCuts = Number(
              task?.completed_cuts_by_step?.[step.key] || 0,
            );
            const pct =
              state === "done"
                ? 100
                : state === "active" && totalCuts > 0
                  ? Math.min(100, Math.round((doneCuts / totalCuts) * 100))
                  : 0;

            // v1.1.52: 모델명 표시
            const modelName = step.modelKey && task?.models
              ? (step.modelKey === "tts"
                  ? [task.models.tts, task.models.tts_voice].filter(Boolean).join(" / ")
                  : task.models[step.modelKey] || "")
              : "";

            return (
              <div key={step.key} className="contents">
                {/* 스텝 컬럼: 바 + 모델명 */}
                <div className="flex-1 flex flex-col items-center">
                  <div
                    className={`relative w-full h-11 rounded-full overflow-hidden border transition-colors ${
                      state === "done"
                        ? "border-accent-success/40"
                        : state === "active"
                          ? "border-amber-400/50"
                          : state === "failed"
                            ? "border-accent-danger/50"
                            : "border-border"
                    }`}
                    style={{ background: "#0d0d15" }}
                  >
                    {/* 진행률 필 바 */}
                    <div
                      className={`absolute inset-y-0 left-0 rounded-full transition-all duration-500 ease-out ${
                        state === "done"
                          ? "bg-accent-success/25"
                          : state === "active"
                            ? "bg-amber-400/20"
                            : state === "failed"
                              ? "bg-accent-danger/20"
                              : ""
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                    {/* 라벨 + 아이콘 */}
                    <div
                      className={`relative z-10 flex items-center justify-center gap-2 h-full text-sm font-semibold ${
                        state === "done"
                          ? "text-accent-success"
                          : state === "active"
                            ? "text-amber-400"
                            : state === "failed"
                              ? "text-accent-danger"
                              : "text-gray-600"
                      }`}
                    >
                      {state === "done" ? (
                        <CheckCircle2 size={16} />
                      ) : state === "active" ? (
                        <PlayCircle size={16} className="animate-pulse" />
                      ) : state === "failed" ? (
                        <X size={16} />
                      ) : (
                        <Circle size={16} />
                      )}
                      {step.label}
                      {state === "active" && pct > 0 && (
                        <span className="text-xs opacity-70">{pct}%</span>
                      )}
                    </div>
                  </div>
                  {/* v1.1.52: 모델명 */}
                  {modelName && (
                    <span className="mt-1.5 text-[11px] text-gray-500 truncate max-w-full text-center leading-tight">
                      {modelName}
                    </span>
                  )}
                  {/* v1.1.55: 스텝별 재실행 버튼 — 완료/실패/취소 상태에서만 표시 */}
                  {isFinished && !isRunning && !rerunning && Number(step.key) <= 6 && (
                    <button
                      onClick={() => handleRerunFromStep(Number(step.key))}
                      className="mt-1.5 flex items-center gap-1 text-[11px] text-gray-500 hover:text-accent-primary transition-colors"
                      title={`${step.label} 부터 재실행`}
                    >
                      <RotateCcw size={11} />
                      재실행
                    </button>
                  )}
                </div>
                {/* 화살표 커넥터 */}
                {i < STEPS.length - 1 && (
                  <ArrowRight
                    size={16}
                    className={`flex-shrink-0 mt-3.5 ${
                      state === "done" ? "text-accent-success/50" : "text-gray-700"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* 본체: 로그 + 우측 패널 */}
      <div className="flex-1 grid grid-cols-[1fr_400px] gap-5 min-h-0">
        {/* 로그 */}
        <div className="bg-[#08080e] border border-border rounded-xl flex flex-col overflow-hidden">
          <div className="flex items-center gap-2.5 px-5 py-3.5 border-b border-border flex-shrink-0">
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
            <span className="text-xs text-gray-600 ml-auto">
              {logs.length}줄
            </span>
          </div>
          <div className="flex-1 overflow-y-auto px-5 py-3.5 font-mono text-[13px] leading-relaxed space-y-1">
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
        <div className="flex flex-col gap-4 overflow-y-auto">
          {/* 단계별 작업 활동 — 살아있는지/얼마 남았는지/멈췄는지 시각화 */}
          <ActivityPanel task={task} />

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
                    <div className="text-xs text-gray-500 font-medium mb-1.5">
                      비용 상세
                    </div>
                    {Object.entries(task.estimate.cost_breakdown).map(
                      ([key, val]) =>
                        val > 0 && (
                          <div
                            key={key}
                            className="flex justify-between text-xs"
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
                    <div className="text-xs text-gray-500 font-medium mb-1.5">
                      시간 상세
                    </div>
                    {Object.entries(task.estimate.time_breakdown).map(
                      ([key, val]) =>
                        val > 0 && (
                          <div
                            key={key}
                            className="flex justify-between text-xs"
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

          {/* 중단 버튼 */}
          {isRunning && (
            <button
              onClick={handleCancel}
              className="flex items-center justify-center gap-2 w-full py-3 rounded-xl text-sm font-semibold bg-accent-danger/10 text-accent-danger border border-accent-danger/30 hover:bg-accent-danger/20 transition-colors flex-shrink-0"
            >
              <Square size={14} /> 제작 중단
            </button>
          )}

          {/* 안내 문구 */}
          <div className="text-xs text-gray-600 text-center px-2 flex-shrink-0">
            이 페이지를 닫아도 백엔드에서 작업은 계속 진행됩니다.
            <br />
            다시 열면 자동으로 진행 상태를 복구합니다.
          </div>
        </div>
      </div>
    </div>
  );
}
