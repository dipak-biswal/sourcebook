import { useState } from "react";
import { Activity, Sparkles } from "lucide-react";
import { AgentRunPanel } from "@/components/agents/AgentRunPanel";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromSteps } from "@/components/agents/generative-ui";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { formatDate } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

type TabKey = "learning" | "trace";

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
    liveSteps,
    liveTokenUsage,
    liveLlmEvents,
    liveTrace,
    approving,
    onApprove,
    onSaveLearningNote,
    savingNote,
  } = useAgentPage();

  const steps = selected?.steps ?? [];
  const gen = extractGenerativeUIFromSteps(
    liveSteps.length ? liveSteps : steps,
  );
  const [activeTab, setActiveTab] = useState<TabKey>(gen ? "learning" : "trace");

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

        {running && !selected?.final_answer && (
          <div className="px-4 py-3 text-sm text-mute">
            Processing…
          </div>
        )}

        <div className="flex items-center gap-1 border-t border-hairline bg-canvas-soft/50 px-4 py-2">
          {gen && (
            <TabButton
              active={activeTab === "learning"}
              icon={Sparkles}
              label="Learning view"
              onClick={() => setActiveTab("learning")}
            />
          )}
          <TabButton
            active={activeTab === "trace"}
            icon={Activity}
            label={gen ? "Trace" : "Trace & details"}
            onClick={() => setActiveTab("trace")}
          />
        </div>

        {activeTab === "learning" && gen && (
          <div className="p-4">
            <GenerativeUIView
              payload={gen}
              onSaveAsNote={(t, b) => onSaveLearningNote(t, b)}
              savingNote={savingNote}
            />
          </div>
        )}

        {activeTab === "trace" && (
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
            embedded
            onApprove={() => onApprove(true)}
            onReject={() => onApprove(false)}
          />
        )}
      </div>
    </div>
  );
}
