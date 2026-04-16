"use client";

import { Loader2 } from "lucide-react";

interface Props {
  onClick: () => void;
  loading?: boolean;
  disabled?: boolean;
  icon?: React.ReactNode;
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  className?: string;
}

const variants = {
  primary: "bg-accent-primary hover:bg-purple-600 text-white",
  secondary: "bg-accent-secondary hover:bg-yellow-600 text-black font-semibold",
  danger: "bg-accent-danger/20 hover:bg-accent-danger/30 text-accent-danger border border-accent-danger/30",
  ghost: "bg-bg-secondary hover:bg-bg-tertiary text-white border border-border",
};

export default function LoadingButton({ onClick, loading, disabled, icon, children, variant = "primary", className = "" }: Props) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      className={`px-4 py-2 rounded-lg flex items-center gap-2 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${variants[variant]} ${className}`}
    >
      {loading ? <Loader2 size={14} className="animate-spin" /> : icon}
      {children}
    </button>
  );
}
