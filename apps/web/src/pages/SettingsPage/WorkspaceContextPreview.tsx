import { useEffect, useState } from "react";
import { Loader2, Sparkles } from "lucide-react";
import { api, type WorkspaceContextPreview } from "@/api";
import { formatError } from "@/lib/utils";
import { cn } from "@/lib/utils";

const CONFIDENCE_STYLES: Record<string, string> = {
  low: "bg-amber-50 text-amber-800 border-amber-200",
  medium: "bg-blue-50 text-blue-800 border-blue-200",
  high: "bg-emerald-50 text-emerald-800 border-emerald-200",
};

function ChipList({ items }: { items: string[] }) {
  if (items.length === 0) return <span className="text-mute">(none)</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {items.map((item) => (
        <span
          key={item}
          className="rounded-full border border-hairline bg-canvas-soft px-2 py-0.5 text-[10px] text-body"
        >
          {item}
        </span>
      ))}
    </span>
  );
}

export function WorkspaceContextPreviewPanel({
  workspaceId,
  name,
  description,
  tags,
}: {
  workspaceId: string;
  name: string;
  description: string;
  tags: string[];
}) {
  const [preview, setPreview] = useState<WorkspaceContextPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    const timer = window.setTimeout(() => {
      setLoading(true);
      void api
        .previewWorkspaceContext(workspaceId, {
          name: name.trim() || undefined,
          description: description.trim() || null,
          tags: tags.length ? tags : null,
        })
        .then(setPreview)
        .catch((err) => {
          setPreview(null);
          setError(formatError(err));
        })
        .finally(() => setLoading(false));
    }, 400);
    return () => window.clearTimeout(timer);
  }, [workspaceId, name, description, tags.join("\0")]);

  return (
    <div className="rounded-[6px] border border-dashed border-hairline bg-canvas-soft/50 p-3">
      <div className="flex items-center gap-1.5 text-xs font-medium text-ink">
        <Sparkles className="h-3.5 w-3.5 text-violet-500" strokeWidth={1.5} />
        How agents will interpret this workspace
        {loading && <Loader2 className="ml-1 h-3 w-3 animate-spin text-mute" />}
      </div>
      <p className="mt-1 text-[10px] text-mute">
        Live preview from name, description, tags, and uploaded documents.
      </p>

      {error && (
        <p className="mt-2 text-xs text-danger-text">{error}</p>
      )}

      {preview && !error && (
        <div className="mt-3 space-y-2 text-xs text-body">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium capitalize",
                CONFIDENCE_STYLES[preview.confidence] ?? CONFIDENCE_STYLES.low,
              )}
            >
              {preview.confidence} confidence
            </span>
            <span className="text-mute">Tone: {preview.tone}</span>
          </div>

          <div>
            <span className="font-medium text-ink">Outcome: </span>
            {preview.outcome_phrase}
          </div>
          <div>
            <span className="font-medium text-ink">Success: </span>
            {preview.success_criteria}
          </div>
          <div>
            <span className="font-medium text-ink">Answer sections: </span>
            <ChipList items={preview.answer_sections} />
          </div>
          <div>
            <span className="font-medium text-ink">Visual affordances: </span>
            <ChipList items={preview.visual_affordances} />
          </div>
          <div className="text-mute">
            Tools: up to {preview.max_search_documents} doc search
            {preview.external_context_ok
              ? `, ${preview.max_web_search} web search`
              : ", web search off"}
            {" · "}
            {preview.documents_ready.length} doc
            {preview.documents_ready.length === 1 ? "" : "s"} ready
            {preview.documents_pending.length > 0 &&
              `, ${preview.documents_pending.length} pending`}
          </div>
        </div>
      )}
    </div>
  );
}