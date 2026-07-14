import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Loader2, MessageCircle, Sparkles } from "lucide-react";
import { AgentTraceTree } from "@/components/agents/AgentTraceTree";
import { AgentApprovalCard } from "@/components/agents/shared";
import {
  isPresentationPending,
  toolDisplayName,
} from "@/components/agents/agent-utils";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromRun } from "@/components/agents/generative-ui";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

type TabKey = "answer" | "visual" | "trace";

function TabButton({
  active,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  icon: typeof Sparkles;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[6px] px-2.5 py-1 text-[11px] font-medium transition-colors",
        active
          ? "bg-ink text-[var(--canvas)]"
          : "text-body hover:bg-canvas-soft-2 hover:text-ink",
      )}
    >
      <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
      {label}
    </button>
  );
}

export function AgentRunDisplay() {
  const {
    selected,
    running,
    liveGoal,
    liveExecutionTrace,
    liveSteps,
    activeToolCalls,
    loopWarning,
    approving,
    onApprove,
    onSaveLearningNote,
    savingNote,
  } = useAgentPage();

  const steps = selected?.steps ?? [];
  const gen = useMemo(
    () =>
      extractGenerativeUIFromRun(
        selected
          ? {
              presentation_spec: selected.presentation_spec,
              steps: liveSteps.length ? liveSteps : steps,
            }
          : null,
      ),
    [selected?.id, selected?.presentation_spec, liveSteps, steps],
  );
  const hasVisualSummary = gen != null;
  const presentationPending =
    selected?.status === "waiting_approval" &&
    isPresentationPending(selected.pending_tool);
  const [activeTab, setActiveTab] = useState<TabKey>(running ? "trace" : "answer");

  useEffect(() => {
    if (running) setActiveTab("trace");
  }, [running]);

  // Auto-open visual tab once when a summary becomes available (not on every render).
  useEffect(() => {
    if (hasVisualSummary && !running && !approving) {
      setActiveTab("visual");
    }
  }, [hasVisualSummary, running, approving, selected?.id]);

  if (!selected && !running) {
    return (
      <div className="rounded-vercel-md border border-dashed border-hairline bg-canvas px-6 py-14 text-center">
        <div className="text-sm font-medium text-ink">No run selected</div>
        <p className="mt-1 text-xs text-mute">
          Choose a run from the sidebar or type a goal above and click Run
          agent.
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div
        className={cn(
          "rounded-vercel-md border bg-canvas",
          running
            ? "border-warning-border ring-1 ring-warning-border/40"
            : "border-hairline",
        )}
      >
        <div className="border-b border-hairline bg-canvas-soft px-4 py-3">
          <div className="min-w-0">
            <div className="text-xs text-mute">
              {selected ? formatDate(selected.created_at) : ""}
            </div>
            <div className="mt-0.5 truncate text-sm font-medium text-ink">
              {selected?.goal || liveGoal || "Agent run in progress…"}
            </div>
          </div>
        </div>

        {running && (
          <div className="flex flex-wrap items-center gap-2 border-t border-hairline px-4 py-2">
            {activeToolCalls.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                {activeToolCalls.map((t, i) => (
                  <span
                    key={`${t.tool_name}-${i}`}
                    className="inline-flex items-center gap-1 rounded-[4px] bg-warning-bg/20 px-1.5 py-0.5 text-[10px] font-medium text-warning"
                  >
                    <Loader2 className="h-2.5 w-2.5 animate-spin" />
                    {toolDisplayName(t.tool_name)}
                  </span>
                ))}
              </div>
            )}
            {loopWarning && (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-red-500">
                <AlertTriangle className="h-3 w-3" strokeWidth={1.5} />
                {loopWarning}
              </span>
            )}
          </div>
        )}

        <div className="flex items-center gap-1 border-t border-hairline bg-canvas-soft/50 px-4 py-2">
          <TabButton
            active={activeTab === "answer"}
            icon={MessageCircle}
            label={
              selected?.status === "waiting_approval" && !presentationPending
                ? "Status"
                : "Answer"
            }
            onClick={() => setActiveTab("answer")}
          />
          {gen && (
            <TabButton
              active={activeTab === "visual"}
              icon={Sparkles}
              label="Visual summary"
              onClick={() => setActiveTab("visual")}
            />
          )}
          <TabButton
            active={activeTab === "trace"}
            icon={Activity}
            label={gen ? "Trace" : "Trace & details"}
            onClick={() => setActiveTab("trace")}
          />
        </div>

        {activeTab === "answer" && (
          <div className="px-4 py-3">
            {running && !selected?.final_answer ? (
              <div className="text-sm text-mute">Processing…</div>
            ) : selected?.final_answer ? (
              <div className="space-y-3 text-body-sm text-body">
                <MarkdownContent content={selected.final_answer} />
                {presentationPending && (
                  <AgentApprovalCard
                    pendingTool={selected.pending_tool!}
                    approving={approving}
                    onApprove={() => onApprove(true)}
                    onReject={() => onApprove(false)}
                  />
                )}
              </div>
            ) : null}
          </div>
        )}

        {activeTab === "visual" && gen && (
          <div className="p-4">
            <GenerativeUIView
              payload={gen}
              onSaveAsNote={(t, b) => onSaveLearningNote(t, b)}
              savingNote={savingNote}
            />
          </div>
        )}

        {activeTab === "trace" && (
          <AgentTraceTree
            run={selected}
            executionTrace={liveExecutionTrace ?? selected?.execution_trace}
            running={running || approving}
            approving={approving}
            onApprove={() => onApprove(true)}
            onReject={() => onApprove(false)}
          />
        )}
      </div>
    </div>
  );
}
