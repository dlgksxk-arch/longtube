/**
 * v2 대시보드 (기획 §8) — v2.3.0 실제 콘텐츠.
 *
 * 디자인 크리틱 우선순위 3: "대시보드가 비어 있다" 를 해소한다.
 * 서버 API 가 이미 돌고 있는 것만 사용:
 *   GET /api/v2/presets/           — 채널별 딸깍폼 유무
 *   GET /api/v2/queue/             — 대기 중인 주제 수
 *   GET /api/v2/tasks/             — 최근 태스크 (실행중/오늘 완료)
 *   GET /api/v2/events/?limit=8    — 최근 이벤트
 *
 * 아직 없는 집계(월 예산 소비 등)는 "카드 헤더 + 준비중" 으로 솔직히
 * 라벨링한다. 거짓 숫자 채우지 않는다.
 *
 * 폴링: 30초마다 리프레시. SSE 는 기획 §12.3 v2.4.0.
 */
"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { channelColor } from "@/lib/channelColor";
import { v2Url } from "@/lib/v2Api";
import { StatusDot, V2Button } from "@/components/v2";

const CHANNELS = [1, 2, 3, 4] as const;

interface Preset {
  id: number;
  channel_id: number;
  form_type: "딸깍폼" | "테스트폼";
  name: string;
  full_name: string;
  is_modified: boolean;
  updated_at?: string;
}

interface QueueItem {
  id: number;
  channel_id: number;
  episode_no: number | null;
  status: string;
  topic_raw: string;
}

interface TaskRow {
  id: number;
  channel_id: number;
  form_type: string;
  episode_no: number | null;
  status: string; // 'pending' | 'running' | 'done' | 'failed' ...
  started_at: string | null;
  ended_at: string | null;
}

interface EventRow {
  id: number;
  scope: string;
  level: string;  // 'info' | 'warn' | 'error' | 'ok' 등 백엔드 정의 따름
  code: string;
  message: string;
  created_at: string;
}

interface UsageChannel {
  channel_id: number;
  total_cost_usd: number;
  month_cost_usd: number;
  record_count: number;
}
interface UsageSummary {
  generated_at: string;
  window_days: number;
  total_cost_usd: number;
  month_cost_usd: number;
  record_count: number;
  by_channel: UsageChannel[];
}

function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function levelToStatus(level: string): "ok" | "warn" | "fail" | "idle" {
  const l = level.toLowerCase();
  if (l.startsWith("err") || l === "fail" || l === "critical") return "fail";
  if (l.startsWith("warn")) return "warn";
  if (l === "ok" || l === "success" || l === "done") return "ok";
  return "idle";
}

export default function V2Dashboard() {
  const [presets, setPresets] = useState<Preset[] | null>(null);
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [tasks, setTasks] = useState<TaskRow[] | null>(null);
  const [events, setEvents] = useState<EventRow[] | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    // 모든 호출은 실패해도 타일 단위로만 degrade 되도록 병렬 + try/catch.
    const fetchJson = async <T,>(path: string): Promise<T | null> => {
      try {
        const res = await fetch(v2Url(path));
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return (await res.json()) as T;
      } catch {
        return null;
      }
    };

    const [p, q, t, e, u] = await Promise.all([
      fetchJson<Preset[]>("/v2/presets/"),
      fetchJson<QueueItem[]>("/v2/queue/"),
      fetchJson<TaskRow[]>("/v2/tasks/"),
      fetchJson<EventRow[]>("/v2/events/?limit=8"),
      fetchJson<UsageSummary>("/v2/usage/summary"),
    ]);

    // 전부 null 이면 백엔드 자체가 죽은 것으로 보고 경고.
    if (p == null && q == null && t == null && e == null && u == null) {
      setErr("백엔드 연결 실패 — 포트 8000 확인");
    } else {
      setErr(null);
    }
    setPresets(p ?? []);
    setQueue(q ?? []);
    setTasks(t ?? []);
    setEvents(e ?? []);
    setUsage(u);
  }, []);

  useEffect(() => {
    loadAll();
    const t = setInterval(loadAll, 30_000);
    return () => clearInterval(t);
  }, [loadAll]);

  const running = useMemo(
    () => (tasks ?? []).filter((x) => x.status === "running"),
    [tasks],
  );
  const doneToday = useMemo(
    () =>
      (tasks ?? []).filter(
        (x) => x.status === "done" && isToday(x.ended_at),
      ),
    [tasks],
  );
  const queueByCh = useMemo(() => {
    const m: Record<number, QueueItem[]> = { 1: [], 2: [], 3: [], 4: [] };
    (queue ?? []).forEach((q) => {
      if (m[q.channel_id]) m[q.channel_id].push(q);
    });
    return m;
  }, [queue]);
  const ddalkkakByCh = useMemo(() => {
    const m: Record<number, Preset | null> = { 1: null, 2: null, 3: null, 4: null };
    (presets ?? []).forEach((p) => {
      if (p.form_type === "딸깍폼" && m[p.channel_id] == null) {
        m[p.channel_id] = p;
      }
    });
    return m;
  }, [presets]);

  return (
    <div className="p-6 space-y-6">
      <header className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-gray-100">LongTube v2</h1>
          <p className="text-sm text-gray-500 mt-1">
            프리셋 단일 진실원 기반 자동화 파이프라인
          </p>
        </div>
        <div className="flex gap-2">
          <Link href="/v2/presets" tabIndex={-1}>
            <V2Button variant="secondary" size="md">
              프리셋
            </V2Button>
          </Link>
          <Link href="/v2/queue" tabIndex={-1}>
            <V2Button variant="primary" size="md">
              큐에 주제 추가
            </V2Button>
          </Link>
        </div>
      </header>

      {err && (
        <div
          role="alert"
          className="rounded-md border border-red-500/40 bg-red-500/10 text-sm text-red-300 px-4 py-2"
        >
          {err}
        </div>
      )}

      {/* KPI 4종 ------------------------------------------------------- */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KpiTile
          label="실행 중"
          value={running.length}
          hint={running.length > 0 ? `${running[0].form_type}` : "대기"}
          tone={running.length > 0 ? "busy" : "idle"}
        />
        <KpiTile
          label="오늘 완료"
          value={doneToday.length}
          hint="done 상태"
          tone={doneToday.length > 0 ? "ok" : "idle"}
        />
        <KpiTile
          label="대기 큐"
          value={queue?.length ?? 0}
          hint={`CH별 ${Object.values(queueByCh)
            .map((arr) => arr.length)
            .join("/")}`}
          tone={(queue?.length ?? 0) > 0 ? "warn" : "idle"}
        />
        <KpiTile
          label="딸깍폼 준비"
          value={Object.values(ddalkkakByCh).filter(Boolean).length}
          hint="4 채널 기준"
          tone={
            Object.values(ddalkkakByCh).every(Boolean) ? "ok" : "warn"
          }
        />
      </section>

      {/* 채널별 카드 --------------------------------------------------- */}
      <section>
        <h2 className="text-gray-200 mb-3">채널 현황</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {CHANNELS.map((ch) => {
            const c = channelColor(ch);
            const preset = ddalkkakByCh[ch];
            const chRunning = running.filter((r) => r.channel_id === ch);
            const chQueue = queueByCh[ch] ?? [];
            const chDoneToday = doneToday.filter((r) => r.channel_id === ch);
            return (
              <article
                key={ch}
                className={`rounded-xl border ${c.border} ${c.bgSoft} p-5 flex flex-col gap-3`}
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
                  >
                    CH{ch}
                  </span>
                  {preset ? (
                    <span className="text-sm text-gray-100 truncate">
                      {preset.name}
                    </span>
                  ) : (
                    <span className="text-sm text-gray-500">딸깍폼 미설정</span>
                  )}
                  <span className="ml-auto">
                    <StatusDot
                      status={
                        chRunning.length > 0
                          ? "busy"
                          : preset
                          ? "ok"
                          : "idle"
                      }
                    />
                  </span>
                </div>

                <dl className="grid grid-cols-3 gap-3 text-sm">
                  <KvBlock label="실행" value={chRunning.length} />
                  <KvBlock label="대기" value={chQueue.length} />
                  <KvBlock label="오늘" value={chDoneToday.length} />
                </dl>

                <div className="mt-auto pt-2 flex items-center justify-between border-t border-border">
                  <span className="text-xs text-gray-500 truncate">
                    {preset ? preset.full_name : "프리셋 없음"}
                  </span>
                  <Link
                    href={preset ? `/v2/presets/${preset.id}` : "/v2/presets"}
                    tabIndex={-1}
                  >
                    <V2Button variant="ghost" size="sm">
                      {preset ? "편집" : "만들기"}
                    </V2Button>
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      {/* 하단 2-열 : 실행 스트립 + 최근 이벤트 -------------------------- */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 실행 중 태스크 스트립 */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-gray-200">실행 중인 태스크</h2>
            <Link
              href="/v2/queue"
              className="text-xs text-sky-400 hover:text-sky-300 underline-offset-2 hover:underline"
            >
              전체 보기
            </Link>
          </div>
          {running.length === 0 ? (
            <p className="text-sm text-gray-500">
              현재 실행 중인 태스크가 없습니다.
            </p>
          ) : (
            <ul className="space-y-2">
              {running.slice(0, 6).map((t) => {
                const c = channelColor(t.channel_id);
                return (
                  <li
                    key={t.id}
                    className="flex items-center gap-3 rounded-md border border-border bg-bg-tertiary/60 px-3 py-2"
                  >
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border}`}
                    >
                      CH{t.channel_id}
                    </span>
                    <span className="text-sm text-gray-100">
                      {t.episode_no != null
                        ? `EP.${t.episode_no}`
                        : t.form_type}
                    </span>
                    <StatusDot status="busy" showLabel={false} />
                    <span className="ml-auto text-xs text-gray-500">
                      시작 {t.started_at ? fmtTime(t.started_at) : "—"}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* 최근 이벤트 */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-gray-200">최근 이벤트</h2>
            <span className="text-xs text-gray-500">
              {events == null ? "로딩..." : `${events.length}건`}
            </span>
          </div>
          {(events ?? []).length === 0 ? (
            <p className="text-sm text-gray-500">이벤트가 없습니다.</p>
          ) : (
            <ul className="space-y-2">
              {(events ?? []).slice(0, 8).map((e) => (
                <li
                  key={e.id}
                  className="flex items-center gap-2 text-sm"
                >
                  <StatusDot
                    status={levelToStatus(e.level)}
                    showLabel={false}
                  />
                  <span className="text-xs text-gray-500 font-mono">
                    {fmtTime(e.created_at)}
                  </span>
                  <span className="text-gray-300 truncate" title={e.message}>
                    {e.message}
                  </span>
                  <span className="ml-auto text-xs text-gray-500">
                    {e.scope}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      <UsageSection usage={usage} />
    </div>
  );
}

function UsageSection({ usage }: { usage: UsageSummary | null }) {
  const hasAny = usage && usage.record_count > 0;
  const max = usage
    ? Math.max(
        0.000001,
        ...usage.by_channel.map((c) => c.month_cost_usd),
      )
    : 0;

  return (
    <section className="rounded-xl border border-border bg-bg-secondary p-5">
      <div className="flex items-baseline gap-3">
        <h2 className="text-gray-300 text-base">이번 달 채널별 비용</h2>
        <span className="text-xs text-gray-500">
          최근 {usage?.window_days ?? 30}일 윈도우 · {usage?.record_count ?? 0}개
          레코드
        </span>
        <span className="ml-auto text-sm text-gray-100 tabular-nums">
          ${usage?.month_cost_usd?.toFixed(2) ?? "0.00"} (월 합)
        </span>
      </div>
      {!hasAny ? (
        <p className="mt-3 text-sm text-gray-500">
          아직 preset_usage_records 행이 없습니다. v2.4.0 task_runner 가
          붙으면 실행 중 자동으로 적재되고, 여기에 채널별 막대가 채워집니다.
          지금은 거짓 숫자 대신 빈 상태로 둡니다.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {usage!.by_channel.map((row) => {
            const c = channelColor(row.channel_id);
            const pct = (row.month_cost_usd / max) * 100;
            return (
              <li key={row.channel_id} className="flex items-center gap-3">
                <span
                  className={`px-2 py-0.5 rounded-md text-xs font-semibold ${c.bgSoft} ${c.text} border ${c.border} shrink-0 w-10 text-center`}
                >
                  CH{row.channel_id}
                </span>
                <div className="flex-1 h-5 rounded-sm bg-bg-tertiary relative overflow-hidden">
                  <div
                    className={`h-full ${c.dot}`}
                    style={{ width: `${pct}%`, minWidth: row.month_cost_usd > 0 ? "3px" : 0 }}
                  />
                </div>
                <span className="text-xs tabular-nums text-gray-200 w-20 text-right">
                  ${row.month_cost_usd.toFixed(2)}
                </span>
                <span className="text-[11px] tabular-nums text-gray-500 w-14 text-right">
                  {row.record_count}건
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/* ========================================================================= */

function KpiTile({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: number;
  hint: string;
  tone: "ok" | "warn" | "busy" | "idle";
}) {
  const color =
    tone === "ok"
      ? "text-emerald-300"
      : tone === "warn"
      ? "text-amber-300"
      : tone === "busy"
      ? "text-sky-300"
      : "text-gray-300";
  return (
    <div className="rounded-xl border border-border bg-bg-secondary p-5">
      <div className="flex items-center justify-between">
        <span className="text-xs text-gray-500 uppercase tracking-wide">
          {label}
        </span>
        <StatusDot status={tone} showLabel={false} />
      </div>
      <p className={`mt-2 text-3xl font-semibold ${color}`}>{value}</p>
      <p className="mt-1 text-xs text-gray-500 truncate" title={hint}>
        {hint}
      </p>
    </div>
  );
}

function KvBlock({ label, value }: { label: string; value: number }) {
  return (
    <div>
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className="text-lg font-semibold text-gray-100">{value}</dd>
    </div>
  );
}
