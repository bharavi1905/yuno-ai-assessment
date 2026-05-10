import { createContext, useContext, useState, useCallback, ReactNode } from "react";

interface Toast {
  id: number;
  type: "success" | "error" | "info";
  message: string;
}

interface ToastContextValue {
  success: (msg: string) => void;
  error: (msg: string) => void;
  info: (msg: string) => void;
}

const ToastContext = createContext<ToastContextValue>({
  success: () => {},
  error:   () => {},
  info:    () => {},
});

let _id = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const add = useCallback((type: Toast["type"], message: string) => {
    const id = ++_id;
    setToasts((prev) => [...prev, { id, type, message }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const value: ToastContextValue = {
    success: (msg) => add("success", msg),
    error:   (msg) => add("error", msg),
    info:    (msg) => add("info", msg),
  };

  const colors = {
    success: "border-[#22c55e] bg-[#052e16] text-[#22c55e]",
    error:   "border-[#ef4444] bg-[#2d0a0a] text-[#ef4444]",
    info:    "border-[#3b82f6] bg-[#0a1628] text-[#3b82f6]",
  };

  const icons = {
    success: "✓",
    error:   "✕",
    info:    "ℹ",
  };

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 min-w-[280px] max-w-[400px]">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`flex items-start gap-3 px-4 py-3 rounded-lg border text-sm font-medium shadow-xl
              animate-[fadeIn_0.2s_ease] ${colors[t.type]}`}
          >
            <span className="mt-0.5 text-base leading-none">{icons[t.type]}</span>
            <span className="text-primary">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  return useContext(ToastContext);
}
