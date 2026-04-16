"use client";

import { DollarSign } from "lucide-react";

interface Props {
  label: string;
  amount: number;
  detail?: string;
}

export default function CostEstimate({ label, amount, detail }: Props) {
  const isFree = amount === 0;
  return (
    <div className="flex items-center gap-2 bg-bg-secondary border border-border rounded-lg px-3 py-2">
      <DollarSign size={14} className={isFree ? "text-green-400" : "text-amber-400"} />
      <div className="flex items-center gap-2 text-sm">
        <span className="text-gray-400">{label}</span>
        <span className={`font-semibold ${isFree ? "text-green-400" : "text-amber-400"}`}>
          {isFree ? "Free" : `~$${amount.toFixed(2)}`}
        </span>
        {detail && <span className="text-xs text-gray-500">({detail})</span>}
      </div>
    </div>
  );
}
