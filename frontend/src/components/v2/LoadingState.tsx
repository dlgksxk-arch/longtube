/**
 * v2.1.0 LoadingState — 로딩 스피너 + 안내문.
 * 기획 §6.2.
 */
"use client";

import { Loader2 } from "lucide-react";

interface LoadingStateProps {
  message?: string;
  className?: string;
  size?: "sm" | "md";
}

export function LoadingState({
  message = "불러오는 중입니다...",
  className = "",
  size = "md",
}: LoadingStateProps) {
  const iconSize = size === "sm" ? 14 : 18;
  return (
    <div
      className={`flex items-center gap-2 text-sm text-gray-400 ${className}`}
      role="status"
      aria-live="polite"
    >
      <Loader2 size={iconSize} className="animate-spin text-sky-400" />
      <span>{message}</span>
    </div>
  );
}
