/**
 * v2.1.0 EmptyState — 데이터 없음 안내.
 *
 * 예: 프리셋이 없는 CH 카드, 큐가 빈 탭, 댓글이 없는 영상.
 * 기획 §6.2.
 */
"use client";

import { ReactNode } from "react";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;     // 예: "새로 만들기" 버튼
  className?: string;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center text-center px-5 py-10 rounded-lg border border-dashed border-border bg-bg-secondary/30 ${className}`}
    >
      {icon && <div className="mb-3 text-gray-500">{icon}</div>}
      <p className="text-sm font-medium text-gray-200">{title}</p>
      {description && (
        <p className="mt-1 text-xs text-gray-500 max-w-xs whitespace-pre-wrap">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
