/**
 * v2.1.0 ConfirmDialog — window.confirm 대체.
 *
 * 사용법:
 *   const [open, setOpen] = useState(false);
 *   <ConfirmDialog
 *     open={open}
 *     title="정말 삭제할까요?"
 *     description="복구할 수 없습니다."
 *     confirmLabel="삭제"
 *     cancelLabel="취소"
 *     danger
 *     onConfirm={() => { doDelete(); setOpen(false); }}
 *     onCancel={() => setOpen(false)}
 *   />
 *
 * 기획 §6.2 공통 컴포넌트.
 */
"use client";

import { useEffect } from "react";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "확인",
  cancelLabel = "취소",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  // ESC 로 취소, Enter 로 확인.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      else if (e.key === "Enter") onConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  const confirmBtn = danger
    ? "bg-red-600 hover:bg-red-500 text-white"
    : "bg-sky-600 hover:bg-sky-500 text-white";

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-[200] flex items-center justify-center"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onCancel}
        aria-hidden
      />
      <div className="relative bg-bg-secondary border border-border rounded-xl shadow-xl px-5 py-4 w-[380px]">
        <h3 className="text-base font-semibold text-gray-100">{title}</h3>
        {description && (
          <p className="mt-2 text-sm text-gray-400 whitespace-pre-wrap">
            {description}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md text-sm bg-bg-tertiary hover:bg-gray-700 text-gray-200"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`px-3 py-1.5 rounded-md text-sm ${confirmBtn}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
