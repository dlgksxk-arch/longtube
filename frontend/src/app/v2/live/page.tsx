/**
 * /v2/live — 실시간 현황 (기획 §12).
 *
 * 진행 중 태스크 카드 + 대기 태스크 + 최근 이벤트 피드.
 * 5초 폴링. 비용 표시 없음.
 * 지연 임계치: 실제 경과 > 예산 + 120 초 → 경고 배지.
 *
 * v2 파이프라인(`services/v2/task_runner.py`) 은 추후 연결. 현재는
 * 백엔드 `/api/v2/tasks`/`events` 가 비어 있어도 폴링만 돌고 EmptyState 를 보여준다.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { channelColor } from "@/lib/channelColor";
import { v2Url } from "@/lib/v2Api";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusDot,
} from "@/components/v2";

interface TaskOut {
  id: number;
  channel_id: number;
  form_type: string;
  episode_no: number | null;
  status: string;
  step_states: Record<string, string>;
  started_at: string | null;
  ended_at: string | null;
  estimated_sec: number | null;
  actual_sec: number | null;
  output_dir: string | null;
}

interface EventOut {
  id: number;
  scope: string;
  scope_id: number | null;
  level: string;
  code: string;
  message: string;
  payload: Record<string, unknown> | null;
  created_at: string;
}

const POLL_MS = 5_000;
const DELAY_OVERRUN_SEC = 120; // 기획 §12.2 — 예산 +120초 초과 시 경고

function elapsedSec(startedAt: string | null): number | null {
  if (!startedAt) return null;
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return null;
  return Math.max(0, Math.floor((Date.now() - started) / 1000));
}

function fmtSec(s: number | null): string {
  if (s === null || s === undefined) return "—";
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m === 0) return `${r}초`;
  return `${m}분 ${r.toString().padStart(2, "0")}초`;
}

function fmtRelTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return iso;
  const diff = Math.floor((Date.now() - t) / 1000);
  if (diff < 0) return "방금";
  if (diff < 60) return `${diff}초 전`;
  if (diff < 3600) return `${Math.floor(diff / 60)}분 전`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

function statusTone(s: string): {
  dot: "ok" | "idle" | "warn" | "fail";
  label: string;
} {
  switch (s) {
    case "running":
      return { dot: "warn", label: "진행 중" };
    case "completed":
      return { dot: "ok", label: "완료" };
    case "failed":
      return { dot: "fail", label: "실패" };
    case "cancelled":
      return { dot: "fail", label: "취소" };
    case "paused":
      return { dot: "idle", label: "일시정지" };
    default:
      return { dot: "idle", label: s || "대기" };
  }
}

function eventLevelColor(level: string): string {
  switch (level) {
    case "error":
      return "text-red-300";
    case "warn":
    case "warning":
      return "text-amber-300";
    case "success":
      return "text-emerald-300";
    default:
      return "text-sky-300";
  }
}

/* -------------------------------------------------------------------------- */

export default function V2LivePage() {
  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [events, setEvents] = useState<EventOut[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // 경과 시간 라이브 업데이트를 위한 tick.
  const [tick, setTick] = useState(0);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [tRes, eRes] = await Promise.all([
        fetch(v2Url("/v2/tasks/")),
        fetch(v2Url("/v2/events/?limit=50")),
      ]);
      if (!tRes.ok) throw new Error(`tasks HTTP ${tRes.status}`);
      if (!eRes.ok) throw new Error(`events HTTP ${eRes.status}`);
      setTasks(await tRes.json());
      setEvents(await eRes.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
  }, [load]);

  // 1초마다 경과 시간 갱신 (폴링과 분리).
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const running = useMemo(
    () => (tasks ?? []).filter((t) => t.status === "running"),
    [tasks],
  );
  const queued = useMemo(
    () => (tasks ?? []).filter((t) => t.status === "queued" || t.status === "paused"),
    [tasks],
  );
  const todayDone = useMemo(() => {
    if (!tasks) return 0;
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return tasks.filter(
      (t) =>
        t.status === "completed" &&
        t.ended_at !== null &&
        new Date(t.ended_at).getTime() >= today.getTime(),
    ).length;
  }, [tasks]);
  const delayCount = useMemo(() => {
    let n = 0;
    for (const t of running) {
      const el = elapsedSec(t.started_at);
      const budget = t.estimated_sec;
      if (el !== null && budget !== null && el > budget + DELAY_OVERRUN_SEC) {
        n += 1;
      }
    }
    return n;
  }, [running, tick]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="p-6 space-y-5">
      <header>
        <h1 className="text-gray-100">실시간 현황</h1>
        <p className="text-sm text-gray-500 mt-1">
          진행 중 태스크와 최근 이벤트. 5초마다 자동 새로고침. 예산 +120초
          초과 시 지연 경고.
        </p>
      </header>

      {/* 요약 스트립 ------------------------------------------------------ */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <SummaryTile label="진행 중" value={running.length} tone="warn" />
        <SummaryTile label="대기" value={queued.length} tone="idle" />
        <SummaryTile label="오늘 완료" value={todayDone} tone="ok" />
        <SummaryTile label="지연 경고" value={delayCount} tone={delayCount > 0 ? "fail" : "idle"} />
      </section>

      {err && <ErrorState message={err} onRetry={load} />}
      {!err && tasks === null && <LoadingState />}

      {!err && tasks !== null && (
        <>
          {/* 진행 중 --------------------------------------------------- */}
          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-gray-300">진행 중</h2>
            {running.length === 0 ? (
              <EmptyState
                title="진행 중인 태스크가 없습니다"
                description="큐에서 다음 항목이 시작되면 여기에 표시됩니다."
              />
            ) : (
              <ul className="space-y-3">
                {running.map((t) => (
                  <RunningCard key={t.id} task={t} />
                ))}
              </ul>
            )}
          </section>

          {/* 대기 중 --------------------------------------------------- */}
          {queued.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold text-gray-300">대기</h2>
              <ul className="space-y-1.5">
                {queued.map((t) => (
                  <QueuedRow key={t.id} task={t} />
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {/* 최근 이벤트 --------------------------------------------------- */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-300">최근 이벤트</h2>
        {events === null && !err && <LoadingState />}
        {events !== null && events.length === 0 && (
          <EmptyState
            title="이벤트가 없습니다"
            description="파이프라인이 돌기 시작하면 실시간으로 채워집니다."
          />
        )}
        {events !== null && events.length > 0 && (
          <ul className="space-y-1 rounded-lg border border-border bg-bg-secondary divide-y divide-border">
            {events.map((e) => (
              <EventRow key={e.id} ev={e} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Sub-components                                                             */
/* -------------------------------------------------------------------------- */

function SummaryTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "ok" | "idle" | "warn" | "fail";
}) {
  const toneText =
    tone === "fail"
      ? "text-red-300"
      : tone === "warn"
        ? "text-amber-200"
        : tone === "ok"
          ? "text-emerald-300"
          : "text-gray-100";
  return (
    <div className="rounded-lg border border-border bg-bg-secondary p-4 flex items-center justify-between">
      <div className="text-xs text-gray-400">{label}</div>
      <div className={`text-2xl font-semibold tabular-nums ${toneText}`}>{value}</div>
    </div>
  );
}

function RunningCard({ task }: { task: TaskOut }) {
  const c = channelColor(task.channel_id);
  const tone = statusTone(task.status);
  const elapsed = elapsedSec(task.started_at);
  const budget = task.estimated_sec;
  const overrun = elapsed !== null && budget !== null ? elapsed - budget : null;
  const isDelayed = overrun !== null && overrun > DELAY_OVERRUN_SEC;

  const progressRatio =
    elapsed !== null && budget !== null && budget > 0
      ? Math.min(1, elapsed / budget)
      : null;

  const steps = Object.entries(task.step_states ?? {});

  return (
    <li
      className={`rounded-lg border p-4 ${
        isDelayed
          ? "border-red-500/60 bg-red-500/5"
          : `${c.border} ${c.bgSoft}`
      }`}
    >
      <header className="flex items-center gap-2 flex-wrap">
        <span
          className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
        >
          CH{task.channel_id}
        </span>
        <span className="px-2 py-0.5 rounded-md text-xs font-semibold bg-bg-tertiary text-gray-100 border border-border">
          {task.episode_no !== null
            ? `EP.${String(task.episode_no).padStart(2, "0")}`
            : task.form_type}
        </span>
        <span className="text-xs text-gray-400">#{task.id}</span>
        <span className="ml-auto">
          <StatusDot status={tone.dot} label={tone.label} />
        </span>
        {isDelayed && (
          <span className="text-xs font-semibold text-red-300 border border-red-500/50 rounded px-1.5 py-0.5">
            지연 경고 (+{fmtSec(overrun!)})
          </span>
        )}
      </header>

      {/* 경과 vs 예산 바 */}
      <div className="mt-3">
        <div className="flex justify-between text-xs text-gray-400 mb-1">
          <span>
            경과 <span className="text-gray-100 tabular-nums">{fmtSec(elapsed)}</span>
          </span>
          <span>
            예산 <span className="text-gray-100 tabular-nums">{fmtSec(budget)}</span>
          </span>
        </div>
        <div className="h-1.5 rounded bg-bg-tertiary overflow-hidden">
          {progressRatio !== null && (
            <div
              className={`h-full ${
                isDelayed ? "bg-red-400" : progressRatio >= 1 ? "bg-amber-400" : "bg-sky-400"
              }`}
              style={{ width: `${Math.max(4, progressRatio * 100)}%` }}
            />
          )}
        </div>
      </div>

      {/* 단계 상태 */}
      {steps.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {steps.map(([name, state]) => (
            <StepChip key={name} name={name} state={state} />
          ))}
        </div>
      )}
    </li>
  );
}

function StepChip({ name, state }: { name: string; state: string }) {
  const tone =
    state === "completed"
      ? "bg-emerald-500/10 text-emerald-200 border-emerald-500/40"
      : state === "running"
        ? "bg-sky-500/15 text-sky-200 border-sky-500/50"
        : state === "failed"
          ? "bg-red-500/15 text-red-200 border-red-500/50"
          : "bg-bg-tertiary text-gray-400 border-border";
  return (
    <span
      className={`px-1.5 py-0.5 rounded text-[11px] font-medium border ${tone}`}
      title={`${name}: ${state}`}
    >
      {name}
    </span>
  );
}

function QueuedRow({ task }: { task: TaskOut }) {
  const c = channelColor(task.channel_id);
  const tone = statusTone(task.status);
  return (
    <li className="flex items-center gap-2 rounded border border-border bg-bg-secondary px-3 py-2">
      <span
        className={`px-1.5 py-0.5 rounded text-[11px] font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
      >
        CH{task.channel_id}
      </span>
      <span className="px-1.5 py-0.5 rounded text-[11px] font-semibold bg-bg-tertiary text-gray-100 border border-border">
        {task.episode_no !== null
          ? `EP.${String(task.episode_no).padStart(2, "0")}`
          : task.form_type}
      </span>
      <span className="text-xs text-gray-500">#{task.id}</span>
      <span className="ml-auto">
        <StatusDot status={tone.dot} label={tone.label} />
      </span>
    </li>
  );
}

function EventRow({ ev }: { ev: EventOut }) {
  return (
    <li className="flex items-start gap-3 px-3 py-2 text-sm">
      <span
        className={`text-[11px] font-semibold uppercase tracking-wide shrink-0 ${eventLevelColor(
          ev.level,
        )}`}
        style={{ minWidth: 48 }}
      >
        {ev.level}
      </span>
      <span className="text-xs text-gray-500 shrink-0" style={{ minWidth: 72 }}>
        {ev.scope}
        {ev.scope_id !== null ? ` #${ev.scope_id}` : ""}
      </span>
      <span className="flex-1 text-gray-100 break-words">{ev.message}</span>
      <span className="text-xs text-gray-500 shrink-0 tabular-nums">
        {fmtRelTime(ev.created_at)}
      </span>
    </li>
  );
}
