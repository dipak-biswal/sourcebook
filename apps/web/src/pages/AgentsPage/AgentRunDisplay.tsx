import { useState } from "react";
import { ChevronRight, Eye, EyeOff } from "lucide-react";
import { AgentRunPanel } from "@/components/agents/AgentRunPanel";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromSteps } from "@/components/agents/generative-ui";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

export function AgentRunDisplay() {
  const {
    selected,
    running,
    liveGoal,
    liveSteps,
    liveTokenUsage,
    liveLlmEvents,
    liveTrace,
    approving,
    onApprove,
    onSaveLearningNote,
    savingNote,
  } = useAgentPage();

  const [showTrace, setShowTrace] = useState(false);

  const steps = selected?.steps ?? [];

  if (!selected && !running) {
    return (
      <div className="py-12 text-center text-sm text-mute">
        Select a run or start a new one.
      </div>
    );
  }

  const gen = (() => {
    const g = extractGenerativeUIFromSteps(
      liveSteps.length ? liveSteps : steps,
    );
    return g || null;
  })();

  return (
    <div className="space-y-4">
      {gen && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-ink">
            Learning view
          </h2>
          <GenerativeUIView
            payload={gen}
            onSaveAsNote={(t, b) => onSaveLearningNote(t, b)}
            savingNote={savingNote}
          />
        </div>
      )}

      {/* AI message block with attached trace toggle */}
      <div
        className={cn(
          "rounded-vercel-md border bg-canvas",
          running
            ? "border-warning-border ring-1 ring-warning-border/40"
            : "border-hairline",
        )}
      >
        {/* Message header */}
        <div className="border-b border-hairline bg-canvas-soft px-4 py-3">
          {selected && (
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs text-mute">
                  {formatDate(selected.created_at)}
                </div>
                <div className="mt-0.5 truncate text-sm font-medium text-ink">
                  {selected.goal}
                </div>
              </div>
              {(selected.final_answer || running) && (
                <button
                  type="button"
                  onClick={() => setShowTrace((v) => !v)}
                  className={cn(
                    "inline-flex shrink-0 items-center gap-1.5 rounded-[6px] border px-2 py-1 text-[11px] font-medium transition-colors",
                    showTrace
                      ? "border-ink bg-ink text-[var(--canvas)]"
                      : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
                  )}
                >
                  {showTrace ? (
                    <EyeOff className="h-3 w-3" strokeWidth={1.5} />
                  ) : (
                    <Eye className="h-3 w-3" strokeWidth={1.5} />
                  )}
                  {showTrace ? "Hide trace" : "Show trace"}
                </button>
              )}
            </div>
          )}
          {!selected && running && (
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium text-ink">
                {liveGoal || "Agent run in progress…"}
              </span>
              <button
                type="button"
                onClick={() => setShowTrace((v) => !v)}
                className={cn(
                  "inline-flex shrink-0 items-center gap-1.5 rounded-[6px] border px-2 py-1 text-[11px] font-medium transition-colors",
                  showTrace
                    ? "border-ink bg-ink text-[var(--canvas)]"
                    : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
                )}
              >
                {showTrace ? (
                  <EyeOff className="h-3 w-3" strokeWidth={1.5} />
                ) : (
                  <Eye className="h-3 w-3" strokeWidth={1.5} />
                )}
                {showTrace ? "Hide trace" : "Show trace"}
              </button>
            </div>
          )}
        </div>

        {/* Message body (final answer) */}
        {selected?.final_answer && (
          <div className="px-4 py-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-mute">
              {selected.status === "waiting_approval"
                ? "Status message"
                : "Final answer"}
            </div>
            <div className="mt-1 text-body-sm text-body">
              <MarkdownContent content={selected.final_answer} />
            </div>
          </div>
        )}

        {/* Running indicator when no answer yet */}
        {running && !selected?.final_answer && (
          <div className="flex items-center gap-2 px-4 py-3 text-sm text-mute">
            <span className="text-xs">Processing…</span>
          </div>
        )}

        {/* Trace panel (toggleable) */}
        {showTrace && (
          <div className="border-t border-hairline p-3">
            <AgentRunPanel
              run={selected}
              pending={running}
              goal={liveGoal || selected?.goal}
              liveSteps={liveSteps}
              liveTokenUsage={liveTokenUsage}
              liveLlmEvents={liveLlmEvents}
              liveTrace={liveTrace}
              approving={approving}
              forceOpenWhilePending
              onApprove={() => onApprove(true)}
              onReject={() => onApprove(false)}
            />
          </div>
        )}

        {/* Toggle button at bottom when trace is hidden */}
        {!showTrace && (selected?.final_answer || running) && (
          <div className="border-t border-hairline px-4 py-2">
            <button
              type="button"
              onClick={() => setShowTrace(true)}
              className="inline-flex items-center gap-1 text-[11px] font-medium text-mute hover:text-ink"
            >
              <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
              Show trace details
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
