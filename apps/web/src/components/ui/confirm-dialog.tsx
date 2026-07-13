import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { ConfirmDialogOptions } from "./confirm-dialog-state";
import {
  subscribeToConfirm,
  getConfirmState,
  resolveConfirm,
} from "./confirm-dialog-state";

type ConfirmDialogProps = ConfirmDialogOptions & {
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  variant = "danger",
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
    };
    document.addEventListener("keydown", handler);
    confirmRef.current?.focus();
    return () => document.removeEventListener("keydown", handler);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-[1px]">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="mx-4 w-full max-w-sm rounded-[12px] border border-hairline bg-canvas p-5 shadow-[var(--elevation-card)]"
      >
        <div className="flex items-start gap-3">
          <div
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
              variant === "danger"
                ? "bg-danger-soft text-danger-text"
                : "bg-canvas-soft-2 text-mute"
            }`}
          >
            <AlertTriangle className="h-4 w-4" strokeWidth={1.5} />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-ink">{title}</h3>
            <p className="mt-1 text-sm text-mute">{message}</p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            ref={confirmRef}
            type="button"
            variant={variant === "danger" ? "default" : "secondary"}
            size="sm"
            onClick={onConfirm}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<ConfirmDialogOptions | null>(null);

  useEffect(() => {
    const unsub = subscribeToConfirm(() => {
      const state = getConfirmState();
      if (state) setDialog({ ...state });
    });
    return unsub;
  }, []);

  function handleConfirm() {
    resolveConfirm(true);
    setDialog(null);
  }

  function handleCancel() {
    resolveConfirm(false);
    setDialog(null);
  }

  return (
    <>
      {children}
      {dialog && (
        <ConfirmDialog
          {...dialog}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </>
  );
}
