import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatError(err: unknown): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message) as { detail?: string };
      if (typeof parsed.detail === "string") return parsed.detail;
    } catch {
      /* plain message */
    }
    return err.message;
  }
  return String(err);
}
