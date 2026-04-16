"use client";

import { useState, useEffect, useRef } from "react";
import { ChevronDown } from "lucide-react";
import type { ModelInfo } from "@/lib/api";

interface Props {
  label: string;
  models: ModelInfo[];
  value: string;
  onChange: (id: string) => void;
  disabled?: boolean;
}

export default function ModelSelector({ label, models, value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selected = models.find((m) => m.id === value);

  return (
    <div ref={ref} className="relative">
      <label className="block text-xs text-gray-400 mb-1">{label}</label>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(!open)}
        className="w-full bg-bg-primary border border-border rounded-lg px-3 py-2 text-sm text-left flex items-center justify-between hover:border-accent-primary/50 transition-colors disabled:opacity-50"
      >
        <div className="flex items-center gap-2 truncate">
          <span className="truncate">{selected?.name || value || "Select..."}</span>
          {selected && selected.available === false && (
            <span className="text-[10px] text-red-400 bg-red-500/20 px-1.5 py-0.5 rounded flex-shrink-0">
              API 미설정
            </span>
          )}
          {selected?.cost_per_unit && selected.available !== false && (
            <span className="text-[10px] text-emerald-400 bg-emerald-400/10 px-1.5 py-0.5 rounded flex-shrink-0">
              {selected.cost_per_unit}
            </span>
          )}
        </div>
        <ChevronDown size={14} className={`ml-2 transition-transform flex-shrink-0 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full bg-bg-secondary border border-border rounded-lg shadow-xl max-h-60 overflow-y-auto">
          {models.map((m) => {
            const isAvailable = m.available !== false;
            return (
              <button
                key={m.id}
                onClick={() => { if (isAvailable) { onChange(m.id); setOpen(false); } }}
                disabled={!isAvailable}
                className={`w-full text-left px-3 py-2.5 text-sm transition-colors ${
                  !isAvailable
                    ? "opacity-40 cursor-not-allowed"
                    : m.id === value
                    ? "bg-accent-primary/20 text-accent-primary"
                    : "text-gray-300 hover:bg-accent-primary/10"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{m.name}</span>
                  <div className="flex items-center gap-1.5 ml-2 flex-shrink-0">
                    {!isAvailable && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-400">
                        API 미설정
                      </span>
                    )}
                    {m.cost_per_unit && (
                      <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                        m.cost_per_unit.includes("Free")
                          ? "text-green-400 bg-green-400/10"
                          : "text-emerald-400 bg-emerald-400/10"
                      }`}>
                        {m.cost_per_unit}
                      </span>
                    )}
                  </div>
                </div>
                <div className="text-xs text-gray-500 mt-0.5">{m.provider}</div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
