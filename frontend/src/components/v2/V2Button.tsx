/**
 * v2.3.0 V2Button — 모든 v2 화면 공용 버튼.
 *
 * 왜 필요한가:
 *   v2.2.0 은 페이지마다 인라인 Tailwind 로 버튼을 찍어서 스타일이
 *   조금씩 달랐다(rounded-md vs rounded-lg, px-2 py-1 vs px-3 py-1.5,
 *   hover 색 불일치 등). /design:design-critique 결과 "버튼을
 *   컴포넌트화" 가 우선순위 4번이었다.
 *
 * 변형(variant):
 *   primary   — 주 액션 (저장/만들기/실행). sky-600
 *   secondary — 보조 (취소/닫기/삭제버튼). bg-tertiary
 *   danger    — 파괴적 액션 (삭제 확인). red-600
 *   ghost     — 본문 위 약한 링크성 버튼. 투명 배경.
 *
 * 크기:
 *   sm  — 리스트 내부 컴팩트 (h-7)
 *   md  — 기본 (h-9)  ← 대부분
 *   lg  — 페이지 주 CTA (h-11)
 *
 * 접근성 (WCAG 2.1 AA):
 *   - focus-visible:ring-2 ring-sky-400 ring-offset-2 — 키보드 포커스 가시
 *   - disabled:opacity-50 + cursor-not-allowed
 *   - 44×44 터치 타깃: md/lg 는 충족. sm 은 리스트용으로 예외.
 *   - aria-busy 지원 (loading 상태)
 */
"use client";

import { forwardRef } from "react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

export interface V2ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  leftIcon?: ReactNode;
}

const BASE =
  "inline-flex items-center justify-center gap-1.5 font-medium " +
  "rounded-md transition-colors select-none " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 " +
  "focus-visible:ring-offset-bg-primary focus-visible:ring-sky-400 " +
  "disabled:opacity-50 disabled:cursor-not-allowed";

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-sky-600 hover:bg-sky-500 active:bg-sky-700 text-white",
  secondary:
    "bg-bg-tertiary hover:bg-gray-700 active:bg-gray-800 " +
    "text-gray-100 border border-border",
  danger:
    "bg-red-600 hover:bg-red-500 active:bg-red-700 text-white",
  ghost:
    "bg-transparent hover:bg-bg-tertiary text-gray-300 hover:text-gray-100",
};

const SIZES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs",
  md: "h-9 px-3.5 text-sm",
  lg: "h-11 px-5 text-base",
};

export const V2Button = forwardRef<HTMLButtonElement, V2ButtonProps>(
  function V2Button(
    {
      variant = "secondary",
      size = "md",
      loading = false,
      leftIcon,
      disabled,
      className = "",
      children,
      type = "button",
      ...rest
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        aria-busy={loading || undefined}
        disabled={disabled || loading}
        className={`${BASE} ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
        {...rest}
      >
        {loading ? (
          <span
            className="inline-block w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"
            aria-hidden
          />
        ) : (
          leftIcon
        )}
        <span>{children}</span>
      </button>
    );
  },
);
