import { ChevronDown, ChevronRight, Loader2, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type UsageEventDetail } from "@/api";
import { Button } from "@/components/ui/button";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { cn } from "@/lib/utils";

export function UsageDetailPanel({
  eventId,
  onClose,
}: {
  eventId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<UsageEventDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  const loadDetail = useCallback(async () => {
    setLoading(true);
    setLoadError(false);
    try {
      setDetail(await api.usageEventDetail(eventId));
    } catch {
      setDetail(null);
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    void loadDetail();
  }, [loadDetail]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
        <span className="text-sm font-semibold text-ink">Trace</span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-5 w-5 animate-spin text-mute" />
          </div>
        ) : loadError || !detail ? (
          <div className="flex flex-col items-center gap-3 py-10 text-center text-sm text-mute">
            <p>Failed to load event details.</p>
            <Button type="button" variant="secondary" size="sm" onClick={() => void loadDetail()}>
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
              Retry
            </Button>
          </div>
        ) : detail.kind === "agent_run" ? (
          <AgentRunTrace detail={detail} />
        ) : detail.kind === "chat" ||
          detail.kind === "chat_stream" ||
          detail.kind === "stream" ? (
          <ChatTrace detail={detail} />
        ) : detail.meta ? (
          <MetaTrace kind={detail.kind} meta={detail.meta} />
        ) : (
          <div className="py-10 text-center text-sm text-mute">
            No details available for this event type ({detail.kind}).
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Tree node primitives ─── */

function TreeNode({
  icon,
  label,
  meta,
  defaultOpen = true,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  meta?: React.ReactNode;
  defaultOpen?: boolean;
  children?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const hasChildren = !!children;

  return (
    <div>
      <div
        className={cn(
          "flex cursor-pointer items-center gap-1.5 rounded-[4px] px-2 py-1.5 text-[13px] transition-colors hover:bg-canvas-soft-2",
        )}
        onClick={() => hasChildren && setOpen((v) => !v)}
      >
        {hasChildren ? (
          open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
          )
        ) : (
          <span className="w-3.5" />
        )}
        <span className="shrink-0">{icon}</span>
        <span className="min-w-0 truncate font-medium text-ink">{label}</span>
        {meta && <span className="ml-auto shrink-0 text-[11px] text-mute">{meta}</span>}
      </div>
      {hasChildren && open && (
        <div className="ml-4 border-l border-hairline pl-2">{children}</div>
      )}
    </div>
  );
}

function LeafNode({
  icon,
  label,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  detail?: string;
}) {
  return (
    <div className="flex items-start gap-1.5 rounded-[4px] px-2 py-1.5 text-[13px]">
      <span className="mt-0.5 shrink-0">{icon}</span>
      <div className="min-w-0 flex-1">
        <span className="font-medium text-ink">{label}</span>
        {detail && (
          <pre className="mt-1 overflow-x-auto whitespace-pre-wrap text-[11px] text-mute">
            {detail.length > 300 ? detail.slice(0, 300) + "…" : detail}
          </pre>
        )}
      </div>
    </div>
  );
}

/* ─── Agent run trace ─── */

function AgentRunTrace({ detail }: { detail: UsageEventDetail }) {
  return (
    <div className="space-y-0.5">
      <TreeNode
        icon={<span className="text-[11px] font-bold text-indigo-500">A</span>}
        label="Agent run"
        meta={
          detail.token_usage != null
            ? `${detail.token_usage.toLocaleString()} tok`
            : undefined
        }
        defaultOpen
      >
        <TreeNode
          icon={<span className="text-[11px]">💬</span>}
          label="Goal"
          defaultOpen={false}
        >
          <LeafNode
            icon={<span />}
            label=""
            detail={detail.goal ?? "—"}
          />
        </TreeNode>

        {detail.steps.map((s, i) => {
          if (s.type === "thought") {
            return (
              <TreeNode
                key={i}
                icon={<span className="text-[11px]">💭</span>}
                label="Thought"
                defaultOpen={false}
              >
                <LeafNode
                  icon={<span />}
                  label=""
                  detail={
                    typeof s.output === "string" ? s.output : JSON.stringify(s.output, null, 1)
                  }
                />
              </TreeNode>
            );
          }
          if (s.type === "tool_call") {
            return (
              <TreeNode
                key={i}
                icon={<span className="text-[11px]">🔧</span>}
                label={s.tool_name ?? "Tool call"}
                defaultOpen={false}
              >
                <LeafNode
                  icon={<span className="text-[11px] text-mute">📥</span>}
                  label="Input"
                  detail={
                    s.input ? JSON.stringify(s.input, null, 1) : "—"
                  }
                />
              </TreeNode>
            );
          }
          if (s.type === "tool_result") {
            return (
              <TreeNode
                key={i}
                icon={<span className="text-[11px]">📄</span>}
                label={s.tool_name ? `${s.tool_name} result` : "Tool result"}
                defaultOpen={false}
              >
                <LeafNode
                  icon={<span className="text-[11px] text-mute">📤</span>}
                  label="Output"
                  detail={
                    s.output
                      ? typeof s.output === "string"
                        ? s.output
                        : JSON.stringify(s.output, null, 1)
                      : "—"
                  }
                />
              </TreeNode>
            );
          }
          return null;
        })}

        {detail.final_answer && (
          <TreeNode
            icon={<span className="text-[11px]">✅</span>}
            label="Final answer"
            defaultOpen
          >
            <div className="rounded-[4px] bg-canvas-soft p-2 text-[12px] text-body">
              <MarkdownContent content={detail.final_answer} />
            </div>
          </TreeNode>
        )}
      </TreeNode>
    </div>
  );
}

/* ─── Chat trace ─── */

function ChatTrace({ detail }: { detail: UsageEventDetail }) {
  return (
    <div className="space-y-0.5">
      <TreeNode
        icon={<span className="text-[11px] font-bold text-sky-500">C</span>}
        label="Chat"
        defaultOpen
      >
        {detail.user_message && (
          <TreeNode
            icon={<span className="text-[11px]">💬</span>}
            label="User"
            defaultOpen={false}
          >
            <LeafNode icon={<span />} label="" detail={detail.user_message} />
          </TreeNode>
        )}

        {detail.assistant_message && (
          <TreeNode
            icon={<span className="text-[11px]">🤖</span>}
            label="Assistant"
            defaultOpen
          >
            <div className="rounded-[4px] bg-canvas-soft p-2 text-[12px] text-body">
              <MarkdownContent content={detail.assistant_message} />
            </div>
          </TreeNode>
        )}

        {detail.citations.length > 0 && (
          <TreeNode
            icon={<span className="text-[11px]">📎</span>}
            label={`Citations (${detail.citations.length})`}
            defaultOpen={false}
          >
            {detail.citations.map((c, i) => (
              <LeafNode key={i} icon={<span />} label="" detail={c} />
            ))}
          </TreeNode>
        )}
      </TreeNode>
    </div>
  );
}

/* ─── Generic meta trace (suggestions, study guide, embeddings) ─── */

function MetaTrace({
  kind,
  meta,
}: {
  kind: string;
  meta: Record<string, unknown>;
}) {
  const entries = Object.entries(meta).filter(([, v]) => v != null && v !== "");

  return (
    <div className="space-y-0.5">
      <TreeNode
        icon={<span className="text-[11px] font-bold text-violet-500">U</span>}
        label={kind.replace(/_/g, " ")}
        defaultOpen
      >
        {entries.length === 0 ? (
          <div className="px-2 py-3 text-[12px] text-mute">No metadata recorded.</div>
        ) : (
          entries.map(([key, value]) => (
            <LeafNode
              key={key}
              icon={<span />}
              label={key.replace(/_/g, " ")}
              detail={
                typeof value === "object"
                  ? JSON.stringify(value, null, 2)
                  : String(value)
              }
            />
          ))
        )}
      </TreeNode>
    </div>
  );
}
