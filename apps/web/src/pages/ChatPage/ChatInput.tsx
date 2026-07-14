import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Bot, Loader2, MessageCircle, Play, Send } from "lucide-react";
import { buildWorkspaceAgentExamples } from "@/components/agents/agent-utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useChatSuggestions, useDocuments } from "@/hooks/queries";
import { cn } from "@/lib/utils";
import { useChatPage } from "./chat-page-context";

function ModeToggle({
  mode,
  onSetMode,
  disabled,
}: {
  mode: "chat" | "agent";
  onSetMode: (mode: "chat" | "agent") => void;
  disabled?: boolean;
}) {
  return (
    <div className="inline-flex rounded-[6px] border border-hairline p-0.5">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSetMode("chat")}
        className={cn(
          "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
          mode === "chat"
            ? "bg-ink text-[var(--canvas)]"
            : "text-body hover:bg-canvas-soft-2",
        )}
      >
        <MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
        Chat
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSetMode("agent")}
        className={cn(
          "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
          mode === "agent"
            ? "bg-ink text-[var(--canvas)]"
            : "text-body hover:bg-canvas-soft-2",
        )}
      >
        <Bot className="h-3.5 w-3.5" strokeWidth={1.5} />
        Agent
      </button>
    </div>
  );
}

export function ChatInput() {
  const {
    mode,
    workspaceId,
    workspaces,
    input,
    sending,
    empty,
    onSetMode,
    onInputChange,
    onSend,
    onSendMessage,
  } = useChatPage();

  const { data: documents = [] } = useDocuments(workspaceId);
  const workspace = workspaces.find((w) => w.id === workspaceId);
  const workspaceName = workspace?.name;
  const exampleGoals = useMemo(
    () => buildWorkspaceAgentExamples(workspace, documents),
    [workspace, documents],
  );
  const { data: suggestions, isLoading: loadingSuggestions } = useChatSuggestions(
    mode === "chat" && empty ? workspaceId : undefined,
  );

  const inputLabel = mode === "agent" ? "Goal" : "Message";
  const inputPlaceholder =
    !workspaceId
      ? "Select a workspace in the sidebar first…"
      : mode === "agent"
        ? "What should the agent do?"
        : "Ask a question about your documents…";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSend();
      }}
      className={cn(
        "mx-auto max-w-2xl rounded-vercel-md border border-hairline bg-canvas p-4",
        sending && "opacity-80",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-ink">
            {mode === "agent" ? "Run an agent" : "Ask about documents"}
          </h1>
          <p className="mt-1 text-xs text-mute">
            {mode === "agent" ? (
              <>
                Quick run in this thread. Full history, traces, and visual
                summaries on{" "}
                <Link
                  to="/agents"
                  className="font-medium text-ink underline-offset-2 hover:underline"
                >
                  Agents
                </Link>
                .
              </>
            ) : (
              "Grounded answers from your workspace documents with citations."
            )}
          </p>
        </div>
        <ModeToggle mode={mode} onSetMode={onSetMode} disabled={sending} />
      </div>

      <label className="mt-4 block">
        <span className="mb-1 block text-xs text-mute">{inputLabel}</span>
        <Input
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={inputPlaceholder}
          disabled={sending || !workspaceId}
        />
      </label>

      {!workspaceId && (
        <p className="mt-2 text-xs text-mute">
          Select a workspace in the sidebar to continue.
        </p>
      )}

      <Button
        type="submit"
        className="mt-3 rounded-[6px]"
        disabled={sending || !input.trim() || !workspaceId}
      >
        {sending ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : mode === "agent" ? (
          <Play className="h-4 w-4" strokeWidth={1.5} />
        ) : (
          <Send className="h-4 w-4" strokeWidth={1.5} />
        )}
        {sending
          ? mode === "agent"
            ? "Running agent…"
            : "Sending…"
          : mode === "agent"
            ? "Run agent"
            : "Send"}
      </Button>

      {!sending && mode === "agent" && empty && exampleGoals.length > 0 && (
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="mb-2 text-[11px] font-medium text-mute">
            {workspaceName
              ? `Try an example for ${workspaceName}`
              : "Try an example"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {exampleGoals.map((example) => (
              <button
                key={example.goal}
                type="button"
                disabled={!workspaceId}
                onClick={() => onInputChange(example.goal)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                  input === example.goal
                    ? "border-ink bg-ink text-[var(--canvas)]"
                    : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
                )}
              >
                {example.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {!sending && mode === "chat" && empty && (
        <div className="mt-4 border-t border-hairline pt-3">
          {loadingSuggestions ? (
            <div className="flex items-center gap-2 text-xs text-mute">
              <Loader2 className="h-3 w-3 animate-spin" />
              Generating suggestions…
            </div>
          ) : suggestions && suggestions.length > 0 ? (
            <>
              <p className="mb-2 text-[11px] font-medium text-mute">
                {workspaceName
                  ? `Suggested questions for ${workspaceName}`
                  : "Suggested questions"}
              </p>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    disabled={!workspaceId}
                    onClick={() => onSendMessage(question)}
                    className="rounded-full border border-hairline bg-canvas px-2.5 py-1 text-left text-[11px] text-body transition-colors hover:bg-canvas-soft-2"
                  >
                    {question.length > 56 ? `${question.slice(0, 56)}…` : question}
                  </button>
                ))}
              </div>
            </>
          ) : null}
        </div>
      )}

      <p className="mt-3 text-[11px] text-mute">Press ⌘/Ctrl+Enter to send</p>
    </form>
  );
}