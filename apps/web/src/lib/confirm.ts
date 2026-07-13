import { showConfirm } from "@/components/ui/confirm-dialog-state";

/** Show a styled confirmation dialog. Returns true if the user confirmed. */
export async function confirmAction(
  title: string,
  message: string,
  confirmLabel = "Delete",
): Promise<boolean> {
  return showConfirm({ title, message, confirmLabel, variant: "danger" });
}
