"use client";

import { useEffect, useState, createContext, useContext, useCallback } from "react";
import { CheckCircle, AlertCircle, X, Info } from "lucide-react";

type ToastType = "success" | "error" | "info";
interface ToastItem { id: number; type: ToastType; message: string; }

const ToastContext = createContext<{
  toast: (type: ToastType, message: string) => void;
}>({ toast: () => {} });

export const useToast = () => useContext(ToastContext);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  let nextId = 0;

  const toast = useCallback((type: ToastType, message: string) => {
    const id = Date.now() + Math.random();
    setItems((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const remove = (id: number) => setItems((prev) => prev.filter((t) => t.id !== id));

  const icon = (type: ToastType) => {
    switch (type) {
      case "success": return <CheckCircle size={16} className="text-accent-success" />;
      case "error": return <AlertCircle size={16} className="text-accent-danger" />;
      default: return <Info size={16} className="text-accent-primary" />;
    }
  };

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} className="flex items-center gap-2 bg-bg-secondary border border-border rounded-lg px-4 py-3 shadow-lg min-w-[280px] animate-slide-in">
            {icon(t.type)}
            <span className="text-sm flex-1">{t.message}</span>
            <button onClick={() => remove(t.id)} className="text-gray-500 hover:text-white">
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
