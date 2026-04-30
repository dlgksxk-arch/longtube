/**
 * v2.1.0 StatusDot — 연결/상태 표시용 원형 닷.
 *
 * 용도: API 키 카드 상단, 채널 카드 "오늘 상태", 이벤트 레벨 배지 등.
 * 기획 §15.1 상태 영역.
 */
"use client";

import { memo } from "react";

export type StatusKind = "ok" | "warn" | "fail" | "idle" | "busy";

const COLOR: Record<StatusKind, { dot: string; label: string }> = {
  ok: { dot: "bg-emerald-400", label: "정상" },
  warn: { dot: "bg-amber-400", label: "주의" },
  fail: { dot: "bg-red-500", label: "실패" },
  idle: { dot: "bg-slate-500", label: "대기" },
  busy: { dot: "bg-sky-400 animate-pulse", label: "동작 중" },
};

interface StatusDotProps {
  status: StatusKind;
  label?: string;   // 커스텀 라벨. 없으면 기본 한국어 라벨.
  size?: "sm" | "md";
  showLabel?: boolean;
  className?: string;
}

function StatusDotInner({
  status,
  label,
  size = "sm",
  showLabel = true,
  className = "",
}: StatusDotProps) {
  const c = COLOR[status];
  const sizeCls = size === "md" ? "w-2.5 h-2.5" : "w-2 h-2";
  return (
    <span className={`inline-flex items-center gap-1.5 ${className}`}>
      <span
        aria-hidden
        className={`inline-block rounded-full ${sizeCls} ${c.dot}`}
      />
      {showLabel && (
        <span className="text-xs text-gray-300">
          {label ?? c.label}
        </span>
      )}
    </span>
  );
}

export const StatusDot = memo(StatusDotInner);
