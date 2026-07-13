export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export const SESSION_EXPIRED_MESSAGE =
  "Session expired. Please sign in again.";

export function parseApiErrorBody(text: string, status: number): string {
  if (status === 401) return SESSION_EXPIRED_MESSAGE;
  const trimmed = text.trim();
  if (!trimmed) return `Request failed (${status})`;
  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown };
    if (typeof parsed.detail === "string") return parsed.detail;
    if (Array.isArray(parsed.detail)) {
      return parsed.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object" && "msg" in item) {
            return String((item as { msg: string }).msg);
          }
          return JSON.stringify(item);
        })
        .join(", ");
    }
  } catch {
    /* plain text */
  }
  return trimmed;
}

export function isSessionExpiredMessage(message: string): boolean {
  return message === SESSION_EXPIRED_MESSAGE;
}

export function shouldRedirectToLogin(): boolean {
  return !window.location.pathname.startsWith("/login");
}