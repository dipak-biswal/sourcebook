import { Link } from "react-router-dom";
import { Plus, Trash2 } from "lucide-react";
import type { Conversation, Workspace } from "@/api";
import { ListSkeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

function formatSessionDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

type ChatSessionsPanelProps = {
  workspaces: Workspace[];
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
  conversations: Conversation[];
  conversationId: string;
  loading: boolean;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  /** Close mobile sheet after navigation */
  onAfterNavigate?: () => void;
};

export function ChatSessionsPanel({
  workspaces,
  workspaceId,
  onWorkspaceChange,
  conversations,
  conversationId,
  loading,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onAfterNavigate,
}: ChatSessionsPanelProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline p-4">
        <h2 className="text-body-sm font-semibold text-ink">Sessions</h2>
        <p className="mt-0.5 text-xs text-mute">
          RAG chat history (Agent turns stay in the thread for now)
        </p>

        {workspaces.length > 0 && (
          <label className="mt-3 block">
            <span className="mb-1 block text-xs text-mute">Workspace</span>
            <select
              value={workspaceId}
              onChange={(e) => onWorkspaceChange(e.target.value)}
              className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <Button
          type="button"
          className="mt-3 w-full rounded-[6px]"
          disabled={!workspaceId || loading}
          onClick={() => {
            onNewChat();
            onAfterNavigate?.();
          }}
        >
          <Plus className="h-4 w-4" strokeWidth={1.5} />
          New session
        </Button>
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          Session list ({conversations.length})
        </div>

        {loading ? (
          <ListSkeleton rows={5} />
        ) : conversations.length === 0 ? (
          <div className="rounded-[6px] border border-dashed border-hairline px-3 py-4 text-center">
            <p className="text-xs text-mute">No sessions yet.</p>
            <p className="mt-1 text-xs text-mute">
              Click <span className="font-medium text-ink">New session</span> or
              send a message in Chat mode.
            </p>
          </div>
        ) : (
          <ul className="space-y-1">
            {conversations.map((c) => {
              const selected = c.id === conversationId;
              return (
                <li key={c.id}>
                  <div
                    className={cn(
                      "group flex items-start gap-1 rounded-[6px] border px-2 py-2 transition-colors",
                      selected
                        ? "border-hairline bg-canvas-soft-2"
                        : "border-transparent hover:bg-canvas-soft-2",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        onSelectSession(c.id);
                        onAfterNavigate?.();
                      }}
                      className="min-w-0 flex-1 text-left"
                    >
                      <div
                        className={cn(
                          "truncate text-sm",
                          selected
                            ? "font-semibold text-ink"
                            : "font-medium text-ink",
                        )}
                      >
                        {c.title || "Untitled session"}
                      </div>
                      <div className="mt-0.5 text-[11px] text-mute">
                        {formatSessionDate(c.created_at)}
                      </div>
                    </button>
                    <button
                      type="button"
                      title="Delete session"
                      className="rounded p-1 text-mute opacity-100 transition-opacity hover:bg-canvas hover:text-ink sm:opacity-0 sm:group-hover:opacity-100"
                      onClick={(e) => {
                        e.stopPropagation();
                        void onDeleteSession(c.id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="shrink-0 space-y-2 border-t border-hairline p-3">
        <Link
          to="/documents"
          onClick={() => onAfterNavigate?.()}
          className="block text-xs font-medium text-ink underline-offset-2 hover:underline"
        >
          → Manage documents & ingest
        </Link>
        <Link
          to="/agents"
          onClick={() => onAfterNavigate?.()}
          className="block text-xs font-medium text-ink underline-offset-2 hover:underline"
        >
          → Agent run history & notes
        </Link>
        <p className="text-[11px] leading-snug text-mute">
          Docs must show status <span className="text-ink">ready</span> before
          Chat mode can cite them.
        </p>
      </div>
    </div>
  );
}
