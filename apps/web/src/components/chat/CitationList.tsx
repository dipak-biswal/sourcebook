import { useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type Citation = {
  index?: number;
  chunk_id?: string;
  document_id?: string;
  filename?: string | null;
  score?: number;
  snippet?: string;
};

function asCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) return [];
  return value as Citation[];
}

function scoreLabel(score?: number): string {
  if (typeof score !== "number") return "";
  if (score >= 0.45) return "strong";
  if (score >= 0.25) return "medium";
  return "weak";
}

function scoreVariant(
  score?: number,
): "success" | "warning" | "secondary" {
  if (typeof score !== "number") return "secondary";
  if (score >= 0.45) return "success";
  if (score >= 0.25) return "warning";
  return "secondary";
}

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

/** Only show sources when retrieval returned real citations and answer isn't a denial. */
export function shouldShowSources(
  content: string,
  citations: unknown,
): boolean {
  if (isDenialMessage(content || "")) return false;
  const items = asCitations(citations);
  if (items.length === 0) return false;
  // Hide if every score is very weak (legacy messages / loose retrieval)
  const scores = items
    .map((c) => c.score)
    .filter((s): s is number => typeof s === "number");
  if (scores.length > 0 && scores.every((s) => s < 0.18)) return false;
  return true;
}

type CitationListProps = {
  citations: unknown;
  className?: string;
  /** When true, expand snippet cards by default (default: collapsed). */
  defaultExpanded?: boolean;
};

/**
 * Compact chips by default; expand for full snippets + scores.
 * Reduces noise while keeping grounded-source transparency.
 */
export function CitationList({
  citations,
  className,
  defaultExpanded = false,
}: CitationListProps) {
  const items = asCitations(citations);
  const [expanded, setExpanded] = useState(defaultExpanded);
  if (items.length === 0) return null;

  return (
    <div className={cn("mt-2 max-w-[90%] space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-mute">
          Sources ({items.length})
        </span>
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-0.5 text-[11px] font-medium text-ink underline-offset-2 hover:underline"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
          )}
          {expanded ? "Hide details" : "Show details"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {items.map((c, i) => {
          const n = c.index ?? i + 1;
          return (
            <Badge
              key={c.chunk_id ?? i}
              variant="outline"
              className="cursor-default gap-1 font-normal"
              title={c.snippet}
            >
              <FileText className="h-3 w-3" strokeWidth={1.5} />
              [{n}] {c.filename ? truncate(c.filename, 28) : "chunk"}
              {typeof c.score === "number" && (
                <span className="text-mute">· {c.score.toFixed(2)}</span>
              )}
            </Badge>
          );
        })}
      </div>

      {expanded && (
        <ul className="space-y-1.5">
          {items.map((c, i) => {
            const n = c.index ?? i + 1;
            return (
              <li
                key={`detail-${c.chunk_id ?? i}`}
                className="rounded-[6px] border border-hairline bg-canvas px-2.5 py-2 text-xs text-body"
              >
                <div className="mb-1 flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold text-ink">[{n}]</span>
                  {c.filename && (
                    <span className="font-medium text-ink">{c.filename}</span>
                  )}
                  {typeof c.score === "number" && (
                    <Badge
                      variant={scoreVariant(c.score)}
                      className="text-[10px]"
                    >
                      {scoreLabel(c.score)} {c.score.toFixed(3)}
                    </Badge>
                  )}
                </div>
                <p className="text-mute leading-relaxed">
                  {c.snippet ?? "…"}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function truncate(s: string, n: number): string {
  return s.length <= n ? s : `${s.slice(0, n - 1)}…`;
}
