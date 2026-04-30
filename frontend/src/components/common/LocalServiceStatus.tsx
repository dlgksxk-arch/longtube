"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  localServicesApi,
  type LocalServiceInfo,
  type LocalSystemStatus,
  type LocalServicesStatus,
} from "@/lib/api";
import { APP_VERSION } from "@/lib/version";

type ServiceTone = "ok" | "warn" | "fail" | "idle";

interface FrontendHealth {
  status: string;
  version?: string;
}

interface ServiceRow {
  name: string;
  label: string;
  detail: string;
  tone: ServiceTone;
}

interface ResourceRow {
  name: string;
  value: string;
  detail: string;
  percent: number | null;
  tone: ServiceTone;
}

interface Props {
  variant?: "sidebar" | "floating";
  className?: string;
}

const TONE_DOT: Record<ServiceTone, string> = {
  ok: "bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.55)]",
  warn: "bg-amber-400 shadow-[0_0_10px_rgba(251,191,36,0.45)]",
  fail: "bg-red-400 shadow-[0_0_10px_rgba(248,113,113,0.45)]",
  idle: "bg-gray-500",
};

const TONE_TEXT: Record<ServiceTone, string> = {
  ok: "text-emerald-300",
  warn: "text-amber-300",
  fail: "text-red-300",
  idle: "text-gray-400",
};

const TONE_BAR: Record<ServiceTone, string> = {
  ok: "bg-emerald-400",
  warn: "bg-amber-400",
  fail: "bg-red-400",
  idle: "bg-gray-600",
};

function toneFromStatus(status?: string): ServiceTone {
  if (!status) return "idle";
  if (["active", "configured", "ok", "key_valid"].includes(status)) return "ok";
  if (["not_configured", "unknown", "unknown_ok"].includes(status)) return "warn";
  if (["error", "invalid", "auth_failed", "timeout"].includes(status)) return "fail";
  return "warn";
}

function labelFromStatus(status?: string): string {
  if (["active", "configured", "ok", "key_valid"].includes(status || "")) return "OK";
  if (status === "not_configured") return "미설정";
  if (["error", "invalid", "auth_failed", "timeout"].includes(status || "")) return "OFF";
  return "확인";
}

function compactLabel(row: ServiceRow): string {
  if (row.tone === "ok") return "OK";
  if (row.tone === "fail") return "OFF";
  if (row.tone === "warn") return "CHECK";
  return "WAIT";
}

function clampPercent(value?: number | null): number | null {
  if (typeof value !== "number" || Number.isNaN(value)) return null;
  return Math.max(0, Math.min(100, value));
}

function formatPercent(value?: number | null): string {
  const pct = clampPercent(value);
  return pct == null ? "--" : `${Math.round(pct)}%`;
}

function toneFromPercent(value?: number | null): ServiceTone {
  const pct = clampPercent(value);
  if (pct == null) return "idle";
  if (pct >= 90) return "fail";
  if (pct >= 75) return "warn";
  return "ok";
}

function formatGb(used?: number | null, total?: number | null): string {
  if (typeof used !== "number" || typeof total !== "number") return "측정 대기";
  return `${used.toFixed(1)} / ${total.toFixed(1)}GB`;
}

function shortGpuName(name?: string): string {
  if (!name) return "GPU 정보 없음";
  return name.replace(/^NVIDIA GeForce\s+/i, "").replace(/^NVIDIA\s+/i, "");
}

function buildResourceRows(system?: LocalSystemStatus | null, backendFailed = false): ResourceRow[] {
  if (backendFailed) {
    return [
      { name: "CPU", value: "--", detail: "백엔드 연결 필요", percent: null, tone: "idle" },
      { name: "RAM", value: "--", detail: "백엔드 연결 필요", percent: null, tone: "idle" },
      { name: "GPU", value: "--", detail: "백엔드 연결 필요", percent: null, tone: "idle" },
    ];
  }

  const gpu = system?.gpu || null;
  const gpuDetailParts = [
    shortGpuName(gpu?.name),
    typeof gpu?.memory_percent === "number" ? `VRAM ${formatPercent(gpu.memory_percent)}` : null,
    typeof gpu?.temperature_c === "number" ? `${Math.round(gpu.temperature_c)}C` : null,
  ].filter(Boolean);

  return [
    {
      name: "CPU",
      value: formatPercent(system?.cpu_percent),
      detail: "프로세서 로드",
      percent: clampPercent(system?.cpu_percent),
      tone: toneFromPercent(system?.cpu_percent),
    },
    {
      name: "RAM",
      value: formatPercent(system?.ram_percent),
      detail: formatGb(system?.ram_used_gb, system?.ram_total_gb),
      percent: clampPercent(system?.ram_percent),
      tone: toneFromPercent(system?.ram_percent),
    },
    {
      name: "GPU",
      value: formatPercent(gpu?.load_percent),
      detail: gpuDetailParts.join(" · ") || system?.gpu_detail || "GPU 정보 없음",
      percent: clampPercent(gpu?.load_percent),
      tone: toneFromPercent(gpu?.load_percent),
    },
  ];
}

function comfyDetail(info?: LocalServiceInfo): string {
  if (!info) return "확인 전";
  if (info.status === "not_configured") return "URL 없음";
  if (info.status !== "active") return info.detail || "응답 없음";

  const running = info.queue_running;
  const pending = info.queue_pending;
  if (typeof running === "number" || typeof pending === "number") {
    return `큐 ${running ?? "-"} / ${pending ?? "-"}`;
  }
  return info.balance || "연결됨";
}

function buildRows(
  frontend: FrontendHealth | null,
  frontendFailed: boolean,
  data: LocalServicesStatus | null,
  backendFailed: boolean,
): ServiceRow[] {
  return [
    {
      name: "프론트",
      label: frontendFailed ? "OFF" : labelFromStatus(frontend?.status || "active"),
      detail: frontendFailed ? "응답 없음" : `v${frontend?.version || APP_VERSION}`,
      tone: frontendFailed ? "fail" : toneFromStatus(frontend?.status || "active"),
    },
    {
      name: "백엔드",
      label: backendFailed ? "OFF" : labelFromStatus(data?.backend?.status),
      detail: backendFailed
        ? "응답 없음"
        : data?.backend?.version
          ? `v${data.backend.version}`
          : "FastAPI",
      tone: backendFailed ? "fail" : toneFromStatus(data?.backend?.status),
    },
    {
      name: "Comfy",
      label: backendFailed ? "확인불가" : labelFromStatus(data?.comfyui?.status),
      detail: backendFailed ? "백엔드 연결 필요" : comfyDetail(data?.comfyui),
      tone: backendFailed ? "idle" : toneFromStatus(data?.comfyui?.status),
    },
  ];
}

function overallTone(rows: ServiceRow[]): ServiceTone {
  if (rows.some((row) => row.tone === "fail")) return "fail";
  if (rows.some((row) => row.tone === "warn")) return "warn";
  if (rows.every((row) => row.tone === "ok")) return "ok";
  return "idle";
}

function ResourceStrip({ rows, compact = false }: { rows: ResourceRow[]; compact?: boolean }) {
  return (
    <div className={compact ? "grid grid-cols-3 gap-1.5 px-2 pb-2" : "mt-2 space-y-1.5 border-t border-border/70 pt-2"}>
      {rows.map((row) => {
        const pct = row.percent ?? 0;
        return (
          <div
            key={row.name}
            className={compact ? "min-w-0 rounded-lg border border-border/60 bg-bg-primary/60 px-2 py-1.5" : "min-w-0"}
            title={`${row.name}: ${row.value} - ${row.detail}`}
          >
            <div className="mb-1 flex items-center gap-2 text-[10px] leading-none">
              <span className="w-7 flex-shrink-0 font-bold text-gray-300">{row.name}</span>
              <span className={`w-9 flex-shrink-0 font-mono font-black ${TONE_TEXT[row.tone]}`}>
                {row.value}
              </span>
              {!compact && <span className="min-w-0 truncate text-gray-500">{row.detail}</span>}
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
              <div
                className={`h-full rounded-full transition-[width] duration-300 ${TONE_BAR[row.tone]}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            {compact && <div className="mt-1 truncate text-[9px] text-gray-500">{row.detail}</div>}
          </div>
        );
      })}
    </div>
  );
}

export default function LocalServiceStatus({ variant = "sidebar", className = "" }: Props) {
  const [frontend, setFrontend] = useState<FrontendHealth | null>(null);
  const [frontendFailed, setFrontendFailed] = useState(false);
  const [data, setData] = useState<LocalServicesStatus | null>(null);
  const [backendFailed, setBackendFailed] = useState(false);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const [frontendResult, localResult] = await Promise.allSettled([
      fetch("/api/frontend-health", { cache: "no-store" }).then((res) => {
        if (!res.ok) throw new Error(`frontend HTTP ${res.status}`);
        return res.json() as Promise<FrontendHealth>;
      }),
      localServicesApi.status(),
    ]);

    if (frontendResult.status === "fulfilled") {
      setFrontend(frontendResult.value);
      setFrontendFailed(false);
    } else {
      setFrontendFailed(true);
    }

    if (localResult.status === "fulfilled") {
      setData(localResult.value);
      setBackendFailed(false);
    } else {
      setBackendFailed(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 10_000);
    return () => window.clearInterval(timer);
  }, [load]);

  const rows = buildRows(frontend, frontendFailed, data, backendFailed);
  const resourceRows = buildResourceRows(data?.system, backendFailed);

  if (variant === "floating") {
    const tone = overallTone(rows);
    return (
      <div
        className={`fixed bottom-3 right-3 z-[9999] w-[min(92vw,430px)] rounded-2xl border border-border bg-bg-secondary/95 shadow-2xl shadow-black/30 backdrop-blur ${className}`}
      >
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
          <div className="flex items-center gap-2">
            <span className={`h-2.5 w-2.5 rounded-full ${TONE_DOT[tone]}`} />
            <span className="text-[11px] font-bold tracking-wide text-gray-200">
              서버 상태
            </span>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="rounded p-1 text-gray-500 transition-colors hover:bg-white/5 hover:text-gray-200 disabled:opacity-60"
            title="서버 상태 새로고침"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        <div className="grid grid-cols-3 gap-1.5 p-2">
          {rows.map((row) => (
            <div
              key={row.name}
              className="min-w-0 rounded-xl border border-border/70 bg-bg-primary/70 px-2 py-2"
              title={`${row.name}: ${row.label} - ${row.detail}`}
            >
              <div className="mb-1 flex items-center gap-1.5">
                <span className={`h-2 w-2 flex-shrink-0 rounded-full ${TONE_DOT[row.tone]}`} />
                <span className="truncate text-[10px] font-semibold text-gray-400">{row.name}</span>
              </div>
              <div className={`text-xs font-black ${TONE_TEXT[row.tone]}`}>{compactLabel(row)}</div>
              <div className="mt-0.5 truncate text-[10px] text-gray-500">{row.detail}</div>
            </div>
          ))}
        </div>
        <ResourceStrip rows={resourceRows} compact />
      </div>
    );
  }

  return (
    <div className="px-3 lg:px-4 xl:px-5 py-2.5 border-b border-border">
      <div className="rounded-xl border border-border bg-bg-primary/55 p-2.5">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold tracking-wide text-gray-300">
            서버 상태
          </span>
          <button
            onClick={load}
            disabled={loading}
            className="rounded p-1 text-gray-500 transition-colors hover:bg-white/5 hover:text-gray-200 disabled:opacity-60"
            title="서버 상태 새로고침"
          >
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>
        <div className="space-y-1.5">
          {rows.map((row) => (
            <div key={row.name} className="flex items-center gap-2 text-[11px] leading-none">
              <span className={`h-2 w-2 flex-shrink-0 rounded-full ${TONE_DOT[row.tone]}`} />
              <span className="w-11 flex-shrink-0 font-semibold text-gray-300">{row.name}</span>
              <span className={`w-12 flex-shrink-0 font-mono font-bold ${TONE_TEXT[row.tone]}`}>
                {row.label}
              </span>
              <span className="min-w-0 truncate text-gray-500" title={row.detail}>
                {row.detail}
              </span>
            </div>
          ))}
        </div>
        <ResourceStrip rows={resourceRows} />
      </div>
    </div>
  );
}
