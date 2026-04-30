/**
 * v2.1.0 공통 컴포넌트 배럴.
 * 기획 §6.2.
 *
 * Toast 는 기존 `components/common/Toast.tsx` 를 그대로 재사용한다.
 * v2 화면에서도 `useToast` 훅과 `ToastProvider` 를 그대로 import 하면 된다.
 */
export { StatusDot } from "./StatusDot";
export type { StatusKind } from "./StatusDot";
export { ConfirmDialog } from "./ConfirmDialog";
export { Modal } from "./Modal";
export { EmptyState } from "./EmptyState";
export { LoadingState } from "./LoadingState";
export { ErrorState } from "./ErrorState";
export { V2Button } from "./V2Button";
export type { V2ButtonProps } from "./V2Button";

// 기존 Toast 재사용 편의 re-export.
export { ToastProvider, useToast } from "@/components/common/Toast";
