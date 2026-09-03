import { useEffect, useState } from "react";

interface Toast { id: number; message: string; type: "success" | "error" | "info" }

export function ToastViewport() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<Omit<Toast, "id">>).detail;
      const id = Date.now() + Math.random();
      setToasts((items) => [...items.slice(-3), { id, ...detail }]);
      window.setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 5000);
    };
    window.addEventListener("app:toast", handler);
    return () => window.removeEventListener("app:toast", handler);
  }, []);
  return (
    <div className="toast-viewport">
      {toasts.map((toast) => <div key={toast.id} className={`toast toast-${toast.type}`}>{toast.message}</div>)}
    </div>
  );
}
