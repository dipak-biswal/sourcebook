import { AlertTriangle, ExternalLink, Globe } from "lucide-react";
import type { WebSearchOutput } from "@/components/agents/agent-utils";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function WebSearchResults({
  data,
  className,
  compact,
}: {
  data: WebSearchOutput;
  className?: string;
  compact?: boolean;
}) {
  const count = data.result_count ?? data.results?.length ?? 0;

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge variant="secondary" className="gap-1 text-[10px]">
          <Globe className="h-2.5 w-2.5" strokeWidth={2} />
          Web search
        </Badge>
        {data.query && (
          <span className="text-[11px] text-body">
            <span className="text-mute">Query:</span>{" "}
            <span className="font-medium text-ink">{data.query}</span>
            {data.original_query && data.original_query !== data.query && (
              <span className="text-mute">
                {" "}
                (adjusted from “{data.original_query}”)
              </span>
            )}
          </span>
        )}
        <span className="text-[10px] text-mute">
          {count} {count === 1 ? "result" : "results"}
        </span>
      </div>

      {data.error && (
        <div className="flex items-start gap-1.5 rounded-[6px] border border-warning-border bg-warning-soft/40 px-2.5 py-2 text-[11px] text-warning-text">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" strokeWidth={2} />
          <span>{data.error}</span>
        </div>
      )}

      {data.results && data.results.length > 0 ? (
        <ul className={cn("space-y-2", compact && "space-y-1.5")}>
          {data.results.map((hit, i) => (
            <li
              key={`${hit.url ?? hit.title}-${i}`}
              className="rounded-[6px] border border-hairline bg-canvas px-2.5 py-2"
            >
              {hit.url ? (
                <a
                  href={hit.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-start gap-1 text-xs font-semibold text-ink underline-offset-2 hover:underline"
                >
                  <span className="min-w-0">{hit.title}</span>
                  <ExternalLink className="mt-0.5 h-3 w-3 shrink-0 text-mute" />
                </a>
              ) : (
                <div className="text-xs font-semibold text-ink">{hit.title}</div>
              )}
              {hit.snippet && (
                <p
                  className={cn(
                    "mt-1 text-[11px] leading-relaxed text-body",
                    compact ? "line-clamp-2" : "line-clamp-3",
                  )}
                >
                  {hit.snippet}
                </p>
              )}
            </li>
          ))}
        </ul>
      ) : !data.error ? (
        <p className="text-[11px] text-mute">No web results returned.</p>
      ) : null}
    </div>
  );
}