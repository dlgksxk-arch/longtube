"use client";

/**
 * v1.1.49 — 딸깍 대시보드 레이아웃
 * 좌측 사이드바(네비게이션) + 우측 콘텐츠 영역
 */
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Zap,
  ListTodo,
  Activity,
  Film,
  Upload,
  MessageSquare,
  LayoutDashboard,
  Key,
} from "lucide-react";
import {
  oneclickApi,
  type OneClickTask,
  type OneClickQueueState,
} from "@/lib/api";
import LocalServiceStatus from "@/components/common/LocalServiceStatus";

const NAV = [
  { href: "/oneclick", label: "제작 큐", icon: ListTodo },
  { href: "/oneclick/upload-pending", label: "업로드 대기", icon: Upload },
  { href: "/oneclick/live", label: "작업대", icon: Activity },
  { href: "/oneclick/channel-ops", label: "채널운영", icon: MessageSquare },
  { href: "/oneclick/library", label: "완성작 관리", icon: Film },
] as const;

const TOP_NAV = [
  { href: "/", label: "대시보드", icon: LayoutDashboard },
  { href: "/oneclick", label: "딸깍 대시보드", icon: Zap },
  { href: "/settings", label: "API 설정", icon: Key },
] as const;

function episodePrefix(ep?: number | null) {
  return typeof ep === "number" && ep > 0 ? `EP.${String(ep).padStart(2, "0")}` : "";
}

function taskDisplayTitle(task: OneClickTask) {
  const text = String(task.topic || task.title || "").trim();
  const prefix = episodePrefix(task.episode_number);
  if (!prefix || /^EP\.\s*\d+/i.test(text)) return text;
  return `${prefix} ${text}`;
}

function activeStepLabel(step?: number | null) {
  if (step === 2) return "스크립트";
  if (step === 3) return "음성";
  if (step === 4) return "이미지";
  if (step === 5) return "영상";
  if (step === 6) return "렌더";
  if (step === 7) return "업로드";
  return "작업";
}

function activeModelNameForStep(task: OneClickTask, step: number) {
  const model = task.models || {};
  if (step === 2) {
    const script = String(model.script || "").trim();
    return script.replace(/^Claude\s+/i, "").replace(/^Anthropic\s*\|\s*/i, "") || "Sonnet 4.6";
  }
  if (step === 3) return model.tts_voice || "Harry Kim - Conversational";
  if (step === 4) {
    const image = String(model.image || "").trim();
    const names: Record<string, string> = {
      "comfyui-dreamshaper-xl": "SDXL Lightning",
      "comfyui-dreamshaper-xl-longtube": "SDXL 로컬모델 v1",
      "comfyui-dreamshaper-xl-longtube-v15": "SDXL 로컬모델 v1.5 실사",
      "openai-image-1": "GPT Image 1",
      "openai-image-2": "OpenAI Image 2",
      "nano-banana-3": "Nano Banana 3",
      "nano-banana-2": "Nano Banana 2",
      "nano-banana-pro": "Nano Banana Pro",
    };
    return names[image] || image.replace(/^DreamShaper XL/i, "SDXL") || "SDXL 로컬모델 v1";
  }
  if (step === 5) {
    const video = String(model.video || "").trim();
    const names: Record<string, string> = {
      "ffmpeg-static": "FFmpeg Static",
      "ffmpeg-safe-motion": "숏츠",
      "seedance-lite": "Seedance 1.0 Lite",
    };
    return names[video] || video || "FFmpeg Static";
  }
  return task.current_step_name || "처리 중";
}

function activeModelEntries(task: OneClickTask) {
  const states = task.step_states || {};
  const steps = [2, 3, 4, 5, 6, 7].filter((step) => states[String(step)] === "running");
  const activeSteps = steps.length ? steps : [Number(task.current_step || 0)].filter(Boolean);
  return activeSteps.map((step) => ({
    task,
    step,
    label: activeStepLabel(step),
    model: activeModelNameForStep(task, step),
  }));
}

const ONECLICK_SUBNAV = [
  { href: "/oneclick", label: "제작 큐", icon: ListTodo },
  { href: "/oneclick/upload-pending", label: "업로드 대기", icon: Upload },
  { href: "/oneclick/live", label: "작업대", icon: Activity },
  { href: "/oneclick/channel-ops", label: "채널운영", icon: MessageSquare },
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
  const [activeTasks, setActiveTasks] = useState<OneClickTask[]>([]);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 큐 + 활성 태스크 로드
  const load = useCallback(async () => {
    try {
      const [q, runningResult] = await Promise.all([
        oneclickApi.getQueue(),
        oneclickApi.getRunning(),
      ]);
      setQueue(q);
      const running = runningResult?.running;
      if (!running?.task_id) {
        setTask(null);
        setActiveTasks([]);
        return;
      }
      const active = await oneclickApi.get(running.task_id);
      setTask(active || null);
      setActiveTasks(
        active?.status === "running" && (active.current_step != null || active.sub_status)
          ? [active]
          : [],
      );
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // 사이드바 상태/호출 모델 실시간 폴링
  useEffect(() => {
    pollRef.current = setInterval(() => {
      if (typeof document !== "undefined" && document.hidden) return;
      void load();
    }, pathname === "/oneclick/live" ? 15000 : 10000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load, pathname]);

  const isRunning =
    task &&
    ["prepared", "queued", "running"].includes(task.status);
  const pct = Math.max(0, Math.min(100, task?.progress_pct || 0));

  const activeCallItems = activeTasks.flatMap(activeModelEntries).slice(0, 4);
  const flatSidebarNav = [
    TOP_NAV[0],
    ...ONECLICK_SUBNAV,
    ...TOP_NAV.filter(({ href }) => href !== "/" && href !== "/oneclick"),
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── 사이드바 ── */}
      <aside className="w-48 min-[1100px]:w-52 xl:w-60 2xl:w-72 flex-shrink-0 bg-bg-secondary border-r border-border flex flex-col">
        {/* 로고 */}
        <Link
          href="/"
          className="flex items-center gap-3 px-3 lg:px-4 xl:px-5 h-14 lg:h-16 xl:h-20 hover:opacity-80 transition-opacity"
        >
          <div className="w-9 h-9 lg:w-10 lg:h-10 xl:w-11 xl:h-11 rounded-xl bg-accent-primary flex items-center justify-center">
            <LayoutDashboard size={18} className="text-white" />
          </div>
          <span className="text-lg lg:text-xl xl:text-2xl font-bold text-white truncate">
            LongTube
          </span>
        </Link>

        <div className="h-px bg-border" />

        <LocalServiceStatus />

        {/* 네비게이션 */}
        <nav className="p-2.5 lg:p-3 xl:p-4 space-y-1.5">
          {flatSidebarNav.map(({ href, label, icon: Icon }) => {
            const displayLabel = href === "/oneclick/library" ? "작업기록" : label;
            const active =
              href === "/"
                ? pathname === "/"
                : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 lg:gap-3 px-3 lg:px-3.5 xl:px-4 py-2.5 lg:py-3 rounded-lg text-sm xl:text-base font-medium transition-colors ${
                  active
                    ? "bg-accent-primary/15 text-accent-primary font-semibold"
                    : "text-gray-300 hover:text-white hover:bg-white/[0.04]"
                }`}
              >
                <Icon size={20} />
                <span className="truncate">{displayLabel}</span>
              </Link>
            );
          })}
        </nav>

        <div className="px-2.5 lg:px-3 xl:px-4">
          <div className="rounded-lg border border-border bg-bg-primary/65 p-2.5 shadow-sm shadow-black/20">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${activeCallItems.length ? "bg-accent-success" : "bg-gray-600"}`} />
                <span className="truncate text-xs font-bold text-gray-100">호출 중 모델</span>
              </div>
              {activeCallItems.length > 0 && (
                <span className="rounded border border-emerald-400/25 bg-emerald-400/10 px-1.5 py-0.5 text-[10px] font-bold text-emerald-200">
                  {activeCallItems.length}
                </span>
              )}
            </div>
            {activeCallItems.length ? (
              <div className="space-y-1.5">
                {activeCallItems.map(({ task: item, step, label, model }) => (
                  <div
                    key={`${item.task_id}-${step}`}
                    className="rounded-md border border-border/80 bg-bg-secondary/80 px-2 py-1.5"
                    title={`${taskDisplayTitle(item)} · ${model}`}
                  >
                    <div className="flex items-center gap-1.5">
                      <span className="shrink-0 rounded border border-accent-primary/30 bg-accent-primary/10 px-1.5 py-0.5 text-[10px] font-black text-accent-primary">
                        {label}
                      </span>
                      <span className="min-w-0 truncate text-xs font-bold text-white">{model}</span>
                    </div>
                    <div className="mt-1 truncate text-[10px] text-gray-500">
                      CH{item.channel || "-"} {episodePrefix(item.episode_number) || ""} · {Math.round(item.progress_pct || 0)}%
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-md border border-dashed border-border bg-bg-secondary/45 px-2 py-2 text-xs text-gray-500">
                호출 중 없음
              </div>
            )}
          </div>
        </div>

        <div className="flex-1" />
      </aside>

      {/* ── 메인 콘텐츠 ── */}
      <main className="min-w-0 flex-1 flex flex-col overflow-hidden">
        <div className="min-w-0 flex-1 overflow-y-auto overflow-x-hidden">{children}</div>
      </main>
    </div>
  );
}
