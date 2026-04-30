/**
 * v2.1.0 ErrorState — 오류 메시지 + 재시도 버튼.
 * 기획 §6.2.
 */
"use client";

import { AlertTriangle, RefreshCcw } from "lucide-react";

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}

export function ErrorState({
  title = "문제가 발생했습니다",
  message,
  onRetry,
  retryLabel = "다시 시도",
  className = "",
}: ErrorStateProps) {
  return (
    <div
      className={`rounded-lg border border-red-500/40 bg-red-500/5 px-4 py-3 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 text-red-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-red-200">{title}</p>
          <p className="mt-1 text-xs text-red-300/80 whitespace-pre-wrap">
            {message}
          </p>
        </div>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs bg-red-500/20 hover:bg-red-500/30 text-red-100"
          >
            <RefreshCcw size={12} />
            {retryLabel}
          </button>
        )}
      </div>
    </div>
  );
}
