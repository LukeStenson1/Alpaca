import React, { createContext, useContext, useState, useCallback } from "react";
import { CheckCircle2, AlertTriangle, XCircle, Info } from "lucide-react";

const ToastCtx = createContext(null);
export const useToast = () => useContext(ToastCtx);

const icons = {
  success: <CheckCircle2 size={16} className="text-profit" />,
  error: <XCircle size={16} className="text-loss" />,
  warning: <AlertTriangle size={16} className="text-warn" />,
  info: <Info size={16} className="text-klein" />,
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const toast = useCallback((message, type = "info") => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t, { id, message, type }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4000);
  }, []);

  return (
    <ToastCtx.Provider value={toast}>
      {children}
      <div className="fixed bottom-5 right-5 z-[100] flex flex-col gap-2" data-testid="toast-container">
        {toasts.map((t) => (
          <div
            key={t.id}
            data-testid="toast"
            className="flex items-center gap-2 border border-zinc-200 bg-white px-4 py-3 text-sm shadow-sm rounded-md min-w-[260px] max-w-sm"
          >
            {icons[t.type]}
            <span className="text-zinc-800">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}
