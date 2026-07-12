/** Browser confirm helper with a consistent default message. */
export function confirmAction(
  message: string,
  detail?: string,
): boolean {
  const full = detail ? `${message}\n\n${detail}` : message;
  return window.confirm(full);
}
