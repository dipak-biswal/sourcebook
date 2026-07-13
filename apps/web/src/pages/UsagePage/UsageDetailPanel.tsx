import { Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type UsageEventDetail } from "@/api";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { Badge } from "@/components/ui/badge";

export function UsageDetailPanel({
  eventId,
  onClose,
}: {
  eventId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<UsageEventDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .usageEventDetail(eventId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [eventId]);

  return (
    <div className="rounded-vercel-md border border-hairline bg-canvas">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
        <span className="text-sm font-semibold text-ink">Event details</span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>

      <div className="divide-y divide-hairline">
        {loading ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 className="h-5 w-5 animate-spin text-mute" />
          </div>
        ) : detail?.kind === "agent_run" ? (
          <AgentRunDetail detail={detail} />
        ) : detail?.kind === "chat" || detail?.kind === "chat_stream" || detail?.kind === "stream" ? (
          <ChatDetail detail={detail} />
        ) : (
          <div className="px-4 py-6 text-center text-sm text-mute">
            No details available for this event.
          </div>
        )}
      </div>
    </div>
  );
}

function AgentRunDetail({ detail }: { detail: UsageEventDetail }) {
  return (
    <div className="space-y-4 px-4 py-4">
      <div>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          Goal
        </div>
        <div className="text-sm text-body">{detail.goal || "—"}</div>
      </div>

      {detail.final_answer && (
        <div>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
            Final answer
          </div>
          <div className="rounded-[6px] border border-hairline bg-canvas-soft p-3 text-body-sm text-body">
            <MarkdownContent content={detail.final_answer} />
          </div>
        </div>
      )}

      {detail.token_usage != null && (
        <div>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
            Token usage
          </div>
          <div className="text-sm font-medium text-ink">
            {detail.token_usage.toLocaleString()} total
          </div>
        </div>
      )}

      {detail.steps.length > 0 && (
        <div>
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-mute">
            Steps ({detail.steps.length})
          </div>
          <div className="space-y-1.5">
            {detail.steps.map((s, i) => (
              <div
                key={i}
                className="rounded-[6px] border border-hairline bg-canvas-soft px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  <Badge variant="secondary" className="text-[10px]">
                    {s.type}
                  </Badge>
                  {s.tool_name && (
                    <span className="text-xs font-medium text-ink">
                      {s.tool_name}
                    </span>
                  )}
                </div>
                {s.type === "tool_call" && s.input && (
                  <pre className="mt-1 overflow-x-auto text-[10px] text-mute">
                    {(JSON.stringify(s.input as Record<string, unknown>, null, 1) ?? "")}
                  </pre>
                )}
                {s.type === "tool_result" && s.output && (
                  <pre className="mt-1 overflow-x-auto text-[10px] text-mute">
                    {typeof s.output === "string"
                      ? (s.output as string).slice(0, 500)
                      : (JSON.stringify(s.output, null, 1) ?? "").slice(0, 500)}
                    {(JSON.stringify(s.output) ?? "").length > 500 ? "…" : ""}
                  </pre>
                )}
                {s.type === "thought" && typeof s.output === "string" && (
                  <div className="mt-1 text-[11px] text-body">
                    {(s.output as string).slice(0, 300)}
                    {(s.output as string).length > 300 ? "…" : ""}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ChatDetail({ detail }: { detail: UsageEventDetail }) {
  return (
    <div className="space-y-4 px-4 py-4">
      {detail.user_message && (
        <div>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
            User message
          </div>
          <div className="rounded-[6px] border border-hairline bg-canvas-soft p-3 text-body-sm text-body">
            {detail.user_message}
          </div>
        </div>
      )}

      {detail.assistant_message && (
        <div>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
            Assistant response
          </div>
          <div className="rounded-[6px] border border-hairline bg-canvas-soft p-3 text-body-sm text-body">
            <MarkdownContent content={detail.assistant_message} />
          </div>
        </div>
      )}

      {detail.citations.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-mute">
            Citations
          </div>
          <div className="flex flex-wrap gap-1">
            {detail.citations.map((c, i) => (
              <Badge key={i} variant="outline" className="text-[10px]">
                {c}
              </Badge>
            ))}
          </div>
        </div>
      )}

      {!detail.user_message && !detail.assistant_message && (
        <div className="py-4 text-center text-sm text-mute">
          No messages found for this conversation.
        </div>
      )}
    </div>
  );
}
