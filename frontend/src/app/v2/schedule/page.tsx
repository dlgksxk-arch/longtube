/**
 * /v2/schedule — 읽기 전용 달력 (기획 §13, Option B).
 *
 * 데이터 소스 2 원천:
 *   1) 과거: GET /api/v2/tasks/ (최신 200건)
 *      - ended_at > started_at 순으로 pivot.
 *      - 둘 다 없으면 달력에 올리지 않음.
 *   2) 미래: GET /api/v2/queue/ 의 `scheduled_at` 이 있는 항목
 *      - v2.3.1 부터 QueueItemOut 에 노출됨.
 *      - 없으면(NULL) 달력에 올리지 않음 — 즉시 실행 큐는 "예정일"
 *        이 정해지지 않은 상태이므로 날짜 배치 금지.
 *
 * 과거·미래 구분:
 *   - 과거 기록(TaskOut): solid 도트 + "완료/실패/실행 중" 배지.
 *   - 미래 예약(QueueItemOut.scheduled_at): 점선 테두리 도트 + "예약" 배지.
 *
 * 거짓말 금지: 미래 예약 중 `scheduled_at=NULL` 은 그대로 숨김 처리한다.
 * 전체 큐를 대충 오늘 날짜에 몰아넣지 않는다.
 */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { v2Url } from "@/lib/v2Api";
import { channelColor, type ChannelId } from "@/lib/channelColor";
import { LoadingState, ErrorState, V2Button } from "@/components/v2";

interface TaskOut {
  id: number;
  channel_id: number;
  form_type: string;
  episode_no: number | null;
  status: string;
  step_states: Record<string, unknown>;
  started_at: string | null;
  ended_at: string | null;
  estimated_sec: number | null;
  actual_sec: number | null;
  output_dir: string | null;
}

interface QueueItemOut {
  id: number;
  preset_id: number;
  channel_id: number;
  episode_no: number | null;
  topic_raw: string;
  topic_polished: string | null;
  status: string;
  scheduled_at: string | null;
  created_at: string | null;
}

/** 달력 셀에 들어가는 통합 엔트리 (과거 실적 또는 미래 예약). */
type CellEntry =
  | {
      kind: "task";
      id: number;
      channel_id: number;
      form_type: string;
      episode_no: number | null;
      status: string;
      at: Date;
    }
  | {
      kind: "queue";
      id: number;
      channel_id: number;
      form_type: "딸깍폼" | "테스트폼" | string;
      episode_no: number | null;
      status: string;
      at: Date;
      topic_preview: string;
    };

/** 달력에 쓰일 "실제 일어난 시각". ended_at > started_at. */
function pivotDate(t: TaskOut): Date | null {
  const raw = t.ended_at ?? t.started_at;
  if (!raw) return null;
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** YYYY-MM-DD (local). */
function dayKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const da = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${da}`;
}

/** `month` 의 달력 그리드 시작일 (해당 월 1일이 속한 주의 일요일). */
function gridStart(month: Date): Date {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const wd = first.getDay(); // 0 = Sun
  const start = new Date(first);
  start.setDate(first.getDate() - wd);
  start.setHours(0, 0, 0, 0);
  return start;
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d);
  r.setDate(d.getDate() + n);
  return r;
}

function sameMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function firstLine(s: string): string {
  const nl = s.indexOf("\n");
  return (nl >= 0 ? s.slice(0, nl) : s).trim();
}

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"] as const;

const STATUS_LABEL: Record<string, string> = {
  // tasks
  queued: "대기",
  running: "실행 중",
  paused: "일시정지",
  completed: "완료",
  failed: "실패",
  cancelled: "취소됨",
  // queue
  pending: "대기",
  scheduled: "예약",
  done: "완료",
};

export default function V2SchedulePage() {
  const [today] = useState(() => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return t;
  });
  const [month, setMonth] = useState(() => {
    const t = new Date();
    return new Date(t.getFullYear(), t.getMonth(), 1);
  });
  const [selected, setSelected] = useState<Date>(() => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return t;
  });
  const [tasks, setTasks] = useState<TaskOut[] | null>(null);
  const [queue, setQueue] = useState<QueueItemOut[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const [rt, rq] = await Promise.all([
        fetch(v2Url("/v2/tasks/")),
        fetch(v2Url("/v2/queue/")),
      ]);
      if (!rt.ok) throw new Error(`tasks HTTP ${rt.status}`);
      if (!rq.ok) throw new Error(`queue HTTP ${rq.status}`);
      setTasks((await rt.json()) as TaskOut[]);
      setQueue((await rq.json()) as QueueItemOut[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // dayKey → CellEntry[] (과거 + 미래 통합).
  const byDay = useMemo(() => {
    const map = new Map<string, CellEntry[]>();
    if (tasks) {
      for (const t of tasks) {
        const d = pivotDate(t);
        if (!d) continue;
        const k = dayKey(d);
        const arr = map.get(k) ?? [];
        arr.push({
          kind: "task",
          id: t.id,
          channel_id: t.channel_id,
          form_type: t.form_type,
          episode_no: t.episode_no,
          status: t.status,
          at: d,
        });
        map.set(k, arr);
      }
    }
    if (queue) {
      for (const q of queue) {
        if (!q.scheduled_at) continue;
        const d = new Date(q.scheduled_at);
        if (Number.isNaN(d.getTime())) continue;
        const k = dayKey(d);
        const arr = map.get(k) ?? [];
        arr.push({
          kind: "queue",
          id: q.id,
          channel_id: q.channel_id,
          form_type: q.topic_polished ? "딸깍폼" : "딸깍폼",
          episode_no: q.episode_no,
          status: q.status,
          at: d,
          topic_preview: firstLine(q.topic_polished ?? q.topic_raw ?? ""),
        });
        map.set(k, arr);
      }
    }
    return map;
  }, [tasks, queue]);

  const grid = useMemo(() => {
    const start = gridStart(month);
    const cells: Date[] = [];
    for (let i = 0; i < 42; i++) cells.push(addDays(start, i));
    return cells;
  }, [month]);

  const selectedEntries = useMemo(() => {
    const arr = byDay.get(dayKey(selected)) ?? [];
    // 시각 내림차순 (최근 먼저). 미래 예약도 섞여 있으면 시각 기준 그대로.
    return [...arr].sort((a, b) => b.at.getTime() - a.at.getTime());
  }, [byDay, selected]);

  const prevMonth = () =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1));
  const nextMonth = () =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1));
  const jumpToday = () => {
    setMonth(new Date(today.getFullYear(), today.getMonth(), 1));
    setSelected(today);
  };

  if (err && !tasks && !queue) {
    return (
      <div className="p-6">
        <ErrorState message={err} onRetry={load} />
      </div>
    );
  }
  if (!tasks || !queue) {
    return (
      <div className="p-6">
        <LoadingState />
      </div>
    );
  }

  const monthLabel = `${month.getFullYear()}년 ${month.getMonth() + 1}월`;

  // 미래 예약이 하나도 없으면 헤더에 정보 제공.
  const totalScheduled = queue.filter((q) => q.scheduled_at).length;

  return (
    <div className="p-6 space-y-4">
      <header className="flex items-start gap-3">
        <div className="flex-1">
          <h1 className="text-gray-100">스케줄</h1>
          <p className="text-sm text-gray-500 mt-1">
            채널별 완료·실행 태스크(과거)와 큐에 등록된 미래 예약을 한 달력에
            모아 보는 읽기 전용 페이지입니다. 예약 시각이 비어 있는 큐
            항목(즉시 실행 대기)은 달력에 표시하지 않습니다.
            {totalScheduled === 0 && " 현재는 미래 예약이 0건입니다."}
          </p>
        </div>
        <V2Button size="sm" variant="secondary" onClick={load}>
          새로고침
        </V2Button>
      </header>

      {/* 달력 조작 ----------------------------------------------------- */}
      <div className="flex items-center gap-2">
        <V2Button size="sm" variant="ghost" onClick={prevMonth} aria-label="이전 달">
          ←
        </V2Button>
        <span className="text-sm font-semibold text-gray-100 tabular-nums w-28 text-center">
          {monthLabel}
        </span>
        <V2Button size="sm" variant="ghost" onClick={nextMonth} aria-label="다음 달">
          →
        </V2Button>
        <V2Button size="sm" variant="secondary" onClick={jumpToday}>
          오늘
        </V2Button>
        <span className="ml-auto flex items-center gap-3 text-xs text-gray-500">
          {([1, 2, 3, 4] as const).map((ch) => {
            const c = channelColor(ch);
            return (
              <span key={ch} className="inline-flex items-center gap-1">
                <span className={`inline-block w-2 h-2 rounded-full ${c.dot}`} />
                CH{ch}
              </span>
            );
          })}
          <span className="inline-flex items-center gap-1 pl-2 border-l border-border">
            <span className="inline-block w-2 h-2 rounded-full border border-dashed border-gray-400" />
            예약
          </span>
        </span>
      </div>

      {/* 그리드 + 상세 -------------------------------------------------- */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] gap-4">
        {/* 그리드 ----------------------------------------------------- */}
        <section className="rounded-xl border border-border bg-bg-secondary overflow-hidden">
          <div className="grid grid-cols-7 text-xs text-gray-500 border-b border-border bg-bg-tertiary/50">
            {WEEKDAYS.map((w, i) => (
              <div
                key={w}
                className={`px-2 py-1.5 ${
                  i === 0 ? "text-red-300" : i === 6 ? "text-sky-300" : ""
                }`}
              >
                {w}
              </div>
            ))}
          </div>
          <div className="grid grid-cols-7">
            {grid.map((d, i) => {
              const key = dayKey(d);
              const dayEntries = byDay.get(key) ?? [];
              const isCurMonth = sameMonth(d, month);
              const isToday = sameDay(d, today);
              const isSel = sameDay(d, selected);
              const wd = d.getDay();
              const bucket = bucketByChannel(dayEntries);

              return (
                <button
                  key={i}
                  type="button"
                  onClick={() => setSelected(d)}
                  className={`relative text-left min-h-[84px] p-1.5 border-b border-r border-border/60 transition-colors ${
                    isCurMonth ? "bg-bg-secondary" : "bg-bg-tertiary/30"
                  } ${isSel ? "ring-1 ring-inset ring-sky-400" : "hover:bg-bg-tertiary/60"}`}
                  aria-current={isToday ? "date" : undefined}
                  aria-label={`${d.getMonth() + 1}월 ${d.getDate()}일, ${dayEntries.length}건`}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={`text-xs tabular-nums ${
                        !isCurMonth
                          ? "text-gray-600"
                          : wd === 0
                            ? "text-red-300"
                            : wd === 6
                              ? "text-sky-300"
                              : "text-gray-300"
                      } ${isToday ? "font-bold" : ""}`}
                    >
                      {d.getDate()}
                    </span>
                    {isToday && (
                      <span className="text-[10px] px-1 rounded bg-sky-500/20 text-sky-200">
                        오늘
                      </span>
                    )}
                  </div>
                  {dayEntries.length > 0 && (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {([1, 2, 3, 4] as const).map((ch) => {
                        const row = bucket[ch];
                        if (!row.total) return null;
                        const c = channelColor(ch);
                        const parts: string[] = [];
                        if (row.past) parts.push(`과거 ${row.past}`);
                        if (row.future) parts.push(`예약 ${row.future}`);
                        return (
                          <span
                            key={ch}
                            className={`inline-flex items-center gap-0.5 px-1 rounded text-[10px] ${c.bgSoft} ${c.text}`}
                            title={`CH${ch} ${parts.join(" · ")}`}
                          >
                            <span
                              className={`w-1.5 h-1.5 rounded-full ${
                                row.past ? c.dot : ""
                              } ${
                                row.future && !row.past
                                  ? "border border-dashed border-current bg-transparent"
                                  : ""
                              }`}
                            />
                            {row.total}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        </section>

        {/* 상세 ------------------------------------------------------- */}
        <aside className="rounded-xl border border-border bg-bg-secondary p-4 min-h-[320px]">
          <h2 className="text-sm font-semibold text-gray-100">
            {selected.getFullYear()}년 {selected.getMonth() + 1}월 {selected.getDate()}일
            <span className="ml-2 text-xs text-gray-500">
              ({WEEKDAYS[selected.getDay()]})
            </span>
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {selectedEntries.length > 0
              ? `항목 ${selectedEntries.length}건`
              : "이 날짜에 집계된 태스크·예약이 없습니다."}
          </p>

          {selectedEntries.length > 0 && (
            <ul className="mt-3 space-y-2">
              {selectedEntries.map((e) => {
                const c = channelColor(e.channel_id as ChannelId);
                const hm = `${String(e.at.getHours()).padStart(2, "0")}:${String(e.at.getMinutes()).padStart(2, "0")}`;
                const statusText = STATUS_LABEL[e.status] ?? e.status;
                return (
                  <li
                    key={`${e.kind}-${e.id}`}
                    className={`rounded-md border ${c.border} ${c.bgSoft} px-2.5 py-2 ${
                      e.kind === "queue" ? "border-dashed" : ""
                    }`}
                  >
                    <div className="flex items-center gap-2 text-xs">
                      <span className={`font-semibold ${c.text}`}>
                        CH{e.channel_id}
                      </span>
                      {e.episode_no != null && (
                        <span className="text-gray-400 tabular-nums">
                          EP.{String(e.episode_no).padStart(2, "0")}
                        </span>
                      )}
                      {e.kind === "queue" && (
                        <span className="text-[10px] px-1 rounded bg-amber-500/20 text-amber-200">
                          예약
                        </span>
                      )}
                      <span className="ml-auto tabular-nums text-gray-500">
                        {hm}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-gray-300">
                      <span>{e.form_type}</span>
                      <span className="text-gray-600">·</span>
                      <span
                        className={
                          e.status === "failed"
                            ? "text-red-300"
                            : e.status === "completed" || e.status === "done"
                              ? "text-emerald-300"
                              : e.status === "running"
                                ? "text-sky-300"
                                : e.kind === "queue"
                                  ? "text-amber-200"
                                  : "text-gray-400"
                        }
                      >
                        {statusText}
                      </span>
                    </div>
                    {e.kind === "queue" && e.topic_preview && (
                      <div className="mt-1 text-[11px] text-gray-400 line-clamp-2">
                        {e.topic_preview}
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}

/** 채널별 과거·미래 건수. */
function bucketByChannel(
  entries: CellEntry[],
): Record<1 | 2 | 3 | 4, { past: number; future: number; total: number }> {
  const out = {
    1: { past: 0, future: 0, total: 0 },
    2: { past: 0, future: 0, total: 0 },
    3: { past: 0, future: 0, total: 0 },
    4: { past: 0, future: 0, total: 0 },
  } as Record<1 | 2 | 3 | 4, { past: number; future: number; total: number }>;
  for (const e of entries) {
    const c = e.channel_id;
    if (c === 1 || c === 2 || c === 3 || c === 4) {
      if (e.kind === "task") out[c].past += 1;
      else out[c].future += 1;
      out[c].total += 1;
    }
  }
  return out;
}
