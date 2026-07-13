import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Citation } from "@/api";
import { asCitations } from "./citations";

type FileGroup = {
  key: string;
  filename: string;
  bestScore?: number;
  chunks: Citation[];
};

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

function groupByFile(items: Citation[]): FileGroup[] {
  const map = new Map<string, FileGroup>();
  for (const c of items) {
    const key =
      c.document_id || c.filename || c.chunk_id || `chunk-${c.index ?? "?"}`;
    const filename = c.filename || "Unknown file";
    const existing = map.get(key);
    if (!existing) {
      map.set(key, {
        key,
        filename,
        bestScore: c.score,
        chunks: [c],
      });
    } else {
      existing.chunks.push(c);
      if (
        typeof c.score === "number" &&
        (existing.bestScore == null || c.score > existing.bestScore)
      ) {
        existing.bestScore = c.score;
      }
    }
  }
  return [...map.values()].sort(
    (a, b) => (b.bestScore ?? 0) - (a.bestScore ?? 0),
  );
}

type CitationListProps = {
  citations: unknown;
  className?: string;
  defaultExpanded?: boolean;
};

/**
 * Grouped by file (chips). Expand for per-chunk snippets + scores.
 */
export function CitationList({
  citations,
  className,
  defaultExpanded = false,
}: CitationListProps) {
  const items = asCitations(citations);
  const groups = useMemo(() => groupByFile(items), [items]);
  const [expanded, setExpanded] = useState(defaultExpanded);
  if (items.length === 0) return null;

  return (
    <div className={cn("mt-2 max-w-[min(90%,36rem)] space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[11px] font-medium uppercase tracking-wide text-mute">
          Sources · {groups.length} file{groups.length === 1 ? "" : "s"} ·{" "}
          {items.length} chunk{items.length === 1 ? "" : "s"}
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
          {expanded ? "Hide chunks" : "Show chunks"}
        </button>
      </div>

      <div className="flex flex-wrap gap-1.5">
        {groups.map((g) => (
          <Badge
            key={g.key}
            variant="outline"
            className="cursor-default gap-1 font-normal"
            title={`${g.chunks.length} chunk(s)`}
          >
            <FileText className="h-3 w-3" strokeWidth={1.5} />
            {truncate(g.filename, 28)}
            <span className="text-mute">
              · {g.chunks.length}x
              {typeof g.bestScore === "number" &&
                ` · ${g.bestScore.toFixed(2)}`}
            </span>
          </Badge>
        ))}
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
