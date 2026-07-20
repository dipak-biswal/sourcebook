import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Loader2,
  MessageCircle,
  Sparkles,
  XCircle,
} from "lucide-react";
import { AgentTraceTree } from "@/components/agents/AgentTraceTree";
import { AgentApprovalCard } from "@/components/agents/shared";
import {
  isPresentationPending,
  toolDisplayName,
} from "@/components/agents/agent-utils";
import {
  GenerativeUISkeleton,
  GenerativeUIView,
} from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromRun } from "@/components/agents/generative-ui";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { Button } from "@/components/ui/button";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

type TabKey = "answer" | "visual" | "trace";

function TabButton({
  active,
  disabled = false,
  icon: Icon,
  label,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  icon: typeof Sparkles;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[6px] px-2.5 py-1 text-[11px] font-medium transition-colors",
        disabled && "cursor-not-allowed opacity-40",
        active && !disabled
          ? "bg-ink text-[var(--canvas)]"
          : !disabled && "text-body hover:bg-canvas-soft-2 hover:text-ink",
        disabled && !active && "text-mute",
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
    liveSkeleton,
    approving,
    cancelling,
    onApprove,
    onCancelRun,
    onSaveLearningNote,
    savingNote,
    workspaceId,
  } = useAgentPage();

  const steps = selected?.steps ?? [];
  const gen = useMemo(
    () =>
      extractGenerativeUIFromRun(
        selected
          ? {
              presentation_spec: selected.presentation_spec,
              final_answer: selected.final_answer,
              steps: liveSteps.length ? liveSteps : steps,
            }
          : null,
      ),
    [selected?.id, selected?.presentation_spec, selected?.final_answer, liveSteps, steps],
  );
  const waitingApproval = selected?.status === "waiting_approval";
  const presentationPending =
    waitingApproval && isPresentationPending(selected.pending_tool);
  const writePending =
    waitingApproval && !!selected.pending_tool && !presentationPending;
  // Visual phase in flight: plan outline arrived, spec not yet rendered.
  const buildingVisual = (running || approving) && !!liveSkeleton;
  const [activeTab, setActiveTab] = useState<TabKey>(running ? "trace" : "answer");

  useEffect(() => {
    if (running || approving) setActiveTab("trace");
  }, [running, approving]);

  // When the run pauses for HITL, keep the user on Trace (where they already
  // are) but the sticky approval banner is always visible above the tabs.

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

        {/* Sticky HITL banner — always visible when waiting, any tab.
            Approval used to live only in the trace detail pane, so a soft
            tool error (e.g. fetch_url 403) could steal focus and leave
            "awaiting you" with no obvious Approve / Cancel. */}
        {waitingApproval && selected.pending_tool && (
          <div className="border-t border-warning-border/50 bg-warning-soft/30 px-4 py-3">
            <AgentApprovalCard
              pendingTool={selected.pending_tool}
              approving={approving}
              onApprove={() => onApprove(true)}
              onReject={() => onApprove(false)}
              className="border-warning-border bg-warning-soft"
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 gap-1 text-[11px] text-danger-text hover:text-danger-text"
                disabled={cancelling || approving}
                onClick={() => onCancelRun()}
              >
                {cancelling ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <XCircle className="h-3 w-3" strokeWidth={1.5} />
                )}
                Cancel run
              </Button>
              <span className="text-[10px] text-mute">
                {writePending
                  ? "Reject skips the write and continues; Cancel ends the run."
                  : "Text only keeps the answer without a visual summary; Cancel ends the run."}
              </span>
            </div>
          </div>
        )}

        {(running || waitingApproval) &&
          selected &&
          selected.status !== "waiting_approval" && (
            <div className="flex justify-end border-t border-hairline px-4 py-1.5">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 gap-1 text-[11px] text-mute hover:text-danger-text"
                disabled={cancelling}
                onClick={() => onCancelRun()}
              >
                {cancelling ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <XCircle className="h-3 w-3" strokeWidth={1.5} />
                )}
                Cancel run
              </Button>
            </div>
          )}

        <div className="flex items-center gap-1 border-t border-hairline bg-canvas-soft/50 px-4 py-2">
          <TabButton
            active={activeTab === "answer"}
            disabled={running}
            icon={MessageCircle}
            label={
              selected?.status === "waiting_approval" && !presentationPending
                ? "Status"
                : "Answer"
            }
            onClick={() => setActiveTab("answer")}
          />
          {(gen || buildingVisual) && (
            <TabButton
              active={activeTab === "visual"}
              disabled={running && !buildingVisual && !gen}
              icon={Sparkles}
              label={buildingVisual && !gen ? "Visual summary…" : "Visual summary"}
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

        {activeTab === "answer" && !running && (
          <div className="px-4 py-3">
            {selected?.final_answer ? (
              <div className="space-y-3 text-body-sm text-body">
                <MarkdownContent content={selected.final_answer} />
                {/* Approval is in the sticky banner above — avoid duplicating it here. */}
              </div>
            ) : waitingApproval ? (
              <p className="text-sm text-mute">
                Waiting for your decision above (approve, keep text only, or cancel).
              </p>
            ) : null}
          </div>
        )}

        {activeTab === "visual" && gen && (
          <div className="p-4">
            <GenerativeUIView
              payload={gen}
              onSaveAsNote={(t, b) => onSaveLearningNote(t, b)}
              savingNote={savingNote}
              workspaceId={workspaceId}
              runId={selected?.id}
            />
          </div>
        )}

        {activeTab === "visual" && !gen && buildingVisual && liveSkeleton && (
          <div className="p-4">
            <GenerativeUISkeleton skeleton={liveSkeleton} />
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
