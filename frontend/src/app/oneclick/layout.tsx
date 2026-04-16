"use client";

/**
 * v1.1.49 — 딸깍 대시보드 레이아웃
 * 좌측 사이드바(네비게이션 + 자동 실행 상태) + 우측 콘텐츠 영역
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Zap,
  ListTodo,
  Activity,
  CalendarDays,
  Film,
  Home,
  Power,
} from "lucide-react";
import {
  oneclickApi,
  type OneClickTask,
  type OneClickQueueState,
} from "@/lib/api";

const NAV = [
  { href: "/oneclick", label: "제작 큐", icon: ListTodo },
  { href: "/oneclick/live", label: "실시간 현황", icon: Activity },
  { href: "/oneclick/schedule", label: "스케줄", icon: CalendarDays },
  { href: "/oneclick/library", label: "완성작 관리", icon: Film },
] as const;

export default function OneClickLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [queue, setQueue] = useState<OneClickQueueState | null>(null);
  const [task, setTask] = useState<OneClickTask | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 큐 + 활성 태스크 로드
  const load = useCallback(async () => {
    try {
      const [q, { tasks }] = await Promise.all([
        oneclickApi.getQueue(),
        oneclickApi.list(),
      ]);
      setQueue(q);
      const active = (tasks || []).find((t) =>
        ["prepared", "queued", "running"].includes(t.status),
      );
      setTask(active || null);
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 활성 태스크 폴링
  useEffect(() => {
    if (!task) return;
    const done = ["completed", "failed", "cancelled"].includes(task.status);
    if (done) return;
    pollRef.current = setTimeout(async () => {
      try {
        const fresh = await oneclickApi.get(task.task_id);
        setTask(fresh);
        if (["completed", "failed", "cancelled"].includes(fresh.status)) {
          void load(); // 큐 갱신
        }
      } catch {}
    }, 2000);
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [task, load]);

  const isRunning =
    task &&
    ["prepared", "queued", "running"].includes(task.status);
  const pct = Math.max(0, Math.min(100, task?.progress_pct || 0));

  // v1.1.57: 활성 채널 수 계산
  const activeChannels = Object.entries(queue?.channel_times || {}).filter(([, v]) => !!v);
  const hasAnySchedule = activeChannels.length > 0;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── 사이드바 ── */}
      <aside className="w-60 flex-shrink-0 bg-bg-secondary border-r border-border flex flex-col">
        {/* 로고 */}
        <Link
          href="/"
          className="flex items-center gap-2.5 px-5 h-16 hover:opacity-80 transition-opacity"
        >
          <div className="w-8 h-8 rounded-lg bg-accent-primary flex items-center justify-center">
            <Zap size={16} className="text-white" />
          </div>
          <span className="text-lg font-bold text-white">LongTube</span>
        </Link>

        <div className="h-px bg-border" />

        {/* 네비게이션 */}
        <nav className="p-3 space-y-0.5">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active =
              href === "/oneclick"
                ? pathname === "/oneclick"
                : pathname.startsWith(href);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  active
                    ? "bg-accent-primary/15 text-accent-primary font-semibold"
                    : "text-gray-400 hover:text-gray-200 hover:bg-white/[0.03]"
                }`}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        {/* 자동 실행 상태 위젯 */}
        <div className="mx-3 mb-3 p-3.5 bg-bg-primary/60 border border-border rounded-xl">
          <div className="flex items-center gap-2 mb-2.5">
            {hasAnySchedule ? (
              <>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-success opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-success" />
                </span>
                <span className="text-xs font-semibold text-accent-success">
                  자동 실행 활성
                </span>
              </>
            ) : (
              <>
                <Power size={10} className="text-gray-500" />
                <span className="text-xs font-semibold text-gray-500">
                  자동 실행 꺼짐
                </span>
              </>
            )}
          </div>
          {hasAnySchedule && (
            <div className="space-y-0.5">
              {activeChannels.map(([ch, time]) => (
                <div key={ch} className="text-[10px] text-gray-400">
                  <span className={`font-bold ${
                    ch === "1" ? "text-blue-400" : ch === "2" ? "text-green-400" :
                    ch === "3" ? "text-amber-400" : "text-purple-400"
                  }`}>CH{ch}</span>{" "}
                  매일 {time}
                </div>
              ))}
            </div>
          )}
          <div className="text-[10px] text-gray-500 mt-1.5">
            대기 중 {queue?.items?.length ?? 0}개 주제
          </div>
        </div>

        {/* 대시보드 복귀 */}
        <div className="px-3 pb-3">
          <Link
            href="/"
            className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] transition-colors"
          >
            <Home size={14} />
            대시보드로 돌아가기
          </Link>
        </div>
      </aside>

      {/* ── 메인 콘텐츠 ── */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* 진행 배너 */}
        {isRunning && task && (
          <div className="flex-shrink-0 bg-accent-primary/10 border-b border-accent-primary/30 px-6 py-2.5 flex items-center gap-4">
            <div className="relative flex h-2 w-2 flex-shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent-primary opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-accent-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-xs text-gray-300">
                제작 중:{" "}
                <span className="text-white font-medium">{task.topic}</span>
              </span>
            </div>
            <div className="w-32 h-1.5 rounded-full bg-bg-tertiary overflow-hidden flex-shrink-0">
              <div
                className="h-full bg-accent-primary transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className="text-xs text-accent-primary font-mono flex-shrink-0">
              {Math.round(pct)}%
            </span>
          </div>
        )}
        <div className="flex-1 overflow-y-auto">{children}</div>
      </main>
    </div>
  );
}
