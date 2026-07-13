import type { Citation } from "@/api";

export function isDenialMessage(content: string): boolean {
  const t = content.trim().toLowerCase();
  return (
    t.includes("no relevant indexed chunks") ||
    t.includes("no indexed document chunks") ||
    t.includes("no grounded match") ||
    (t.includes("i don't know") &&
      (t.includes("ingest") || t.includes("document") || t.includes("chunk")))
  );
}

export function shouldShowSources(
  content: string,
  citations: unknown,
): boolean {
  if (isDenialMessage(content || "")) return false;
  const items = asCitations(citations);
  if (items.length === 0) return false;
  const scores = items
    .map((c) => c.score)
    .filter((s): s is number => typeof s === "number");
  if (scores.length > 0 && scores.every((s) => s < 0.18)) return false;
  return true;
}

export function asCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) return [];
  return value as Citation[];
}
