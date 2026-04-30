/**
 * v2.3.0 Modal — 임의 컨텐츠를 담는 범용 모달 셸.
 *
 * ConfirmDialog 는 "정말 실행할까요" 2-choice 전용이라 입력 폼을 담기에는
 * 좁다. 이 모달은 header/body/footer 슬롯을 열어 두고 배경 클릭/ESC 로
 * 닫히는 기본 동작만 제공한다.
 *
 * 사용법:
 *   <Modal open={open} onClose={() => setOpen(false)} title="초기화">
 *     {form body}
 *   </Modal>
 *
 * 기획 §6.2 공통 컴포넌트 — 모달/토스트만 사용.
 *
 * v2.3.0 접근성 개선 (design:accessibility-review R1/O2):
 *   - aria-labelledby → 헤더 h3 의 id 를 연결해 스크린리더가 제목을 읽음.
 *   - 최초 포커스 → 본문 최초 focusable 에 자동 이동 (없으면 닫기 버튼).
 *   - Tab 루프 포커스 트랩 → 모달 밖으로 포커스 이탈 방지.
 *   - 모달 닫힐 때 호출자 버튼으로 포커스 복귀.
 *   - body scroll lock — 뒤 페이지 스크롤 잠금.
 */
"use client";

import { useEffect, useId, useRef } from "react";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  /** 기본 w-[480px]. 값이 주어지면 해당 tailwind width class 를 사용한다. */
  widthClass?: string;
  /** footer 슬롯 (버튼 영역). 주어지지 않으면 본문만 렌더. */
  footer?: React.ReactNode;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), ' +
  'input:not([disabled]):not([type="hidden"]), select:not([disabled]), ' +
  '[tabindex]:not([tabindex="-1"])';

export function Modal({
  open,
  title,
  onClose,
  children,
  widthClass = "w-[480px]",
  footer,
}: ModalProps) {
  const titleId = useId();
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  // ESC 닫기 + Tab 포커스 트랩.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !dialogRef.current) return;

      const focusables = Array.from(
        dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((el) => !el.hasAttribute("data-focus-skip"));
      if (focusables.length === 0) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const activeEl = document.activeElement as HTMLElement | null;

      if (e.shiftKey && activeEl === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && activeEl === last) {
        e.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // 열릴 때: 기존 포커스 기억 → 첫 포커스 이동 → body scroll lock.
  // 닫힐 때: 복귀 + 해제.
  useEffect(() => {
    if (!open) return;
    previouslyFocused.current =
      (document.activeElement as HTMLElement | null) ?? null;

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // 한 틱 뒤에 첫 포커스 이동 (마운트 완료 보장).
    const raf = requestAnimationFrame(() => {
      if (!dialogRef.current) return;
      const first = dialogRef.current.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? dialogRef.current).focus();
    });

    return () => {
      cancelAnimationFrame(raf);
      document.body.style.overflow = prevOverflow;
      previouslyFocused.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-[180] flex items-center justify-center"
    >
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />
      <div
        ref={dialogRef}
        tabIndex={-1}
        className={`relative bg-bg-secondary border border-border rounded-xl shadow-xl ${widthClass} max-h-[85vh] flex flex-col focus:outline-none`}
      >
        <header className="px-5 py-3 border-b border-border flex items-center justify-between">
          <h3
            id={titleId}
            className="text-base font-semibold text-gray-100"
          >
            {title}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-100 text-xl leading-none w-8 h-8 flex items-center justify-center rounded-md hover:bg-bg-tertiary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
            aria-label="닫기"
          >
            ×
          </button>
        </header>
        <div className="px-5 py-4 overflow-y-auto flex-1">{children}</div>
        {footer && (
          <footer className="px-5 py-3 border-t border-border flex justify-end gap-2">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
