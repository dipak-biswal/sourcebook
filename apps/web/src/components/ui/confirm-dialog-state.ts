export type ConfirmDialogOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "danger" | "default";
};

type ConfirmFn = (opts: ConfirmDialogOptions) => Promise<boolean>;

let confirmResolve: ((value: boolean) => void) | null = null;
let confirmState: ConfirmDialogOptions | null = null;
let confirmListeners: Array<() => void> = [];

function notifyListeners() {
  confirmListeners.forEach((fn) => fn());
}

export function showConfirm(opts: ConfirmDialogOptions): Promise<boolean> {
  confirmState = opts;
  notifyListeners();
  return new Promise<boolean>((resolve) => {
    confirmResolve = resolve;
  });
}

export const confirm: ConfirmFn = showConfirm;

export function subscribeToConfirm(listener: () => void) {
  confirmListeners.push(listener);
  return () => {
    confirmListeners = confirmListeners.filter((l) => l !== listener);
  };
}

export function getConfirmState(): ConfirmDialogOptions | null {
  return confirmState;
}

export function resolveConfirm(value: boolean) {
  confirmResolve?.(value);
  confirmResolve = null;
  confirmState = null;
}
