import { Link } from "react-router-dom";
import { Bot, MessageCircle, Plus, Trash2 } from "lucide-react";
import type { AgentRun, Conversation, Workspace } from "@/api";
import { AgentStatusBadge } from "@/components/agents/shared";
import { Button } from "@/components/ui/button";
import { ListSkeleton } from "@/components/ui/skeleton";
import { WorkspaceSelect } from "@/components/workspace/WorkspaceSelect";
import { cn, formatDate } from "@/lib/utils";

function truncateGoal(goal: string, max = 56): string {
  const t = goal.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export type ChatSessionsPanelProps = {
  mode: "chat" | "agent";
  workspaces: Workspace[];
  workspaceId: string;
  onChangeWorkspace: (id: string) => void;
  onRefreshWorkspaces: () => void;
  /** Chat mode */
  conversations: Conversation[];
  conversationId: string;
  onNewChat?: () => void;
  /** Agent mode */
  agentRuns?: AgentRun[];
  agentRunId?: string;
  onNewAgent?: () => void;
  loading: boolean;
  onSelectSession: (id: string) => void;
  onDeleteSession?: (id: string) => void;
  onSelectAgentRun?: (id: string) => void;
  /** Close mobile sheet after navigation */
  onAfterNavigate?: () => void;
};

export function ChatSessionsPanel({
  mode,
  workspaces,
  workspaceId,
  onChangeWorkspace,
  onRefreshWorkspaces,
  conversations,
  conversationId,
  onNewChat,
  agentRuns = [],
  agentRunId = "",
  onNewAgent,
  loading,
  onSelectSession,
  onDeleteSession,
  onSelectAgentRun,
  onAfterNavigate,
}: ChatSessionsPanelProps) {
  const isAgent = mode === "agent";
  const count = isAgent ? agentRuns.length : conversations.length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 space-y-3 border-b border-hairline p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            {isAgent ? (
              <Bot className="h-4 w-4 shrink-0 text-ink" strokeWidth={1.5} />
            ) : (
              <MessageCircle className="h-4 w-4 shrink-0 text-ink" strokeWidth={1.5} />
            )}
            <h2 className="truncate text-body-sm font-semibold text-ink">
              {isAgent ? "Agent sessions" : "Chat sessions"}
            </h2>
          </div>
          {isAgent ? (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="h-7 shrink-0 px-2 text-xs"
              disabled={!workspaceId}
              onClick={() => {
                onNewAgent?.();
                onAfterNavigate?.();
              }}
            >
              <Plus className="h-3 w-3" strokeWidth={1.5} />
              New run
            </Button>
          ) : (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="h-7 shrink-0 px-2 text-xs"
              disabled={!workspaceId || !conversationId}
              title={
                !conversationId
                  ? "Already on a new session — send a message to save it"
                  : undefined
              }
              onClick={() => {
                onNewChat?.();
                onAfterNavigate?.();
              }}
            >
              <Plus className="h-3 w-3" strokeWidth={1.5} />
              New session
            </Button>
          )}
        </div>
        {workspaces.length > 0 && (
          <WorkspaceSelect
            workspaces={workspaces}
            workspaceId={workspaceId}
            onChange={onChangeWorkspace}
            onRefresh={onRefreshWorkspaces}
          />
        )}
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          {isAgent ? "Runs" : "Sessions"} ({count})
        </div>

        {loading ? (
          <ListSkeleton rows={5} />
        ) : isAgent ? (
          agentRuns.length === 0 ? (
            <div className="rounded-[6px] border border-dashed border-hairline px-3 py-4 text-center">
              <p className="text-xs text-mute">No runs in this workspace yet.</p>
              <p className="mt-1 text-xs text-mute">
                Send a goal below — or browse all runs on the{" "}
                <Link
                  to="/agents"
                  onClick={() => onAfterNavigate?.()}
                  className="font-medium text-ink underline-offset-2 hover:underline"
                >
                  Agents page
                </Link>
                .
              </p>
            </div>
          ) : (
            <ul className="space-y-1">
              {agentRuns.map((run) => {
                const selected = run.id === agentRunId;
                return (
                  <li key={run.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelectAgentRun?.(run.id);
                        onAfterNavigate?.();
                      }}
                      className={cn(
                        "group flex w-full flex-col gap-1 rounded-[6px] border px-2 py-2 text-left transition-colors",
                        selected
                          ? "border-hairline bg-canvas-soft-2"
                          : "border-transparent hover:bg-canvas-soft-2",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div
                          className={cn(
                            "min-w-0 flex-1 text-sm leading-snug",
                            selected
                              ? "font-semibold text-ink"
                              : "font-medium text-ink",
                          )}
                        >
                          {truncateGoal(run.goal)}
                        </div>
                        <AgentStatusBadge status={run.status} />
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-mute">
                        <span>{formatDate(run.created_at)}</span>
                        {run.token_usage != null && (
                          <span className="font-mono">
                            {run.token_usage.toLocaleString()} tok
                          </span>
                        )}
                        {run.steps?.length ? (
                          <span>{run.steps.length} spans</span>
                        ) : null}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )
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
                        {formatDate(c.created_at)}
                      </div>
                    </button>
                    {onDeleteSession && (
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
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="shrink-0 border-t border-hairline p-3">
        <p className="text-[11px] leading-snug text-mute">
          {isAgent
            ? "Switch to Chat mode for RAG Q&A sessions with citations."
            : (
              <>
                Docs must show status <span className="text-ink">ready</span>{" "}
                before Chat mode can cite them.
              </>
            )}
        </p>
      </div>
    </div>
  );
}
