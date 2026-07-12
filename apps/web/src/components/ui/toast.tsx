import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

export type ToastVariant = "default" | "success" | "danger";

export type ToastInput = {
  title: string;
  description?: string;
  variant?: ToastVariant;
  durationMs?: number;
};

type ToastItem = ToastInput & { id: string };

type ToastContextValue = {
  toast: (input: ToastInput) => void;
  success: (title: string, description?: string) => void;
  error: (title: string, description?: string) => void;
};

const ToastContext = createContext<ToastContextValue>({
  toast: () => {},
  success: () => {},
  error: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (input: ToastInput) => {
      const id = `t-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
      const item: ToastItem = {
        id,
        title: input.title,
        description: input.description,
        variant: input.variant ?? "default",
        durationMs: input.durationMs ?? 3200,
      };
      setItems((prev) => [...prev.slice(-4), item]);
      window.setTimeout(() => dismiss(id), item.durationMs);
    },
    [dismiss],
  );

  const success = useCallback(
    (title: string, description?: string) =>
      toast({ title, description, variant: "success" }),
    [toast],
  );

  const error = useCallback(
    (title: string, description?: string) =>
      toast({ title, description, variant: "danger", durationMs: 4500 }),
    [toast],
  );

  const value = useMemo(
    () => ({ toast, success, error }),
    [toast, success, error],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-[min(100%-2rem,22rem)] flex-col gap-2 sm:bottom-6 sm:right-6"
        aria-live="polite"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex gap-2.5 rounded-vercel-md border bg-canvas p-3 shadow-[var(--elevation-card)] animate-in",
              t.variant === "success" && "border-hairline",
              t.variant === "danger" &&
                "border-danger-border bg-danger-soft",
              t.variant === "default" && "border-hairline",
            )}
            role="status"
          >
            <span className="mt-0.5 shrink-0">
              {t.variant === "success" ? (
                <CheckCircle2
                  className="h-4 w-4 text-ink"
                  strokeWidth={1.5}
                />
              ) : t.variant === "danger" ? (
                <XCircle
                  className="h-4 w-4 text-danger-text"
                  strokeWidth={1.5}
                />
              ) : (
                <Info className="h-4 w-4 text-mute" strokeWidth={1.5} />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <div
                className={cn(
                  "text-sm font-medium",
                  t.variant === "danger" ? "text-danger-text" : "text-ink",
                )}
              >
                {t.title}
              </div>
              {t.description && (
                <div
                  className={cn(
                    "mt-0.5 text-xs leading-relaxed",
                    t.variant === "danger" ? "text-danger-text/90" : "text-mute",
                  )}
                >
                  {t.description}
                </div>
              )}
            </div>
            <button
              type="button"
              className="shrink-0 rounded p-0.5 text-mute hover:bg-canvas-soft-2 hover:text-ink"
              aria-label="Dismiss"
              onClick={() => dismiss(t.id)}
            >
              <X className="h-3.5 w-3.5" strokeWidth={1.5} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
