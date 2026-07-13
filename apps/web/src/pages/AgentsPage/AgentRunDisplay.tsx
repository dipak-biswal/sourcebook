import { AgentRunPanel } from "@/components/agents/AgentRunPanel";
import { GenerativeUIView } from "@/components/agents/GenerativeUI";
import { extractGenerativeUIFromSteps } from "@/components/agents/generative-ui";
import { formatDate } from "@/lib/utils";
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

  const steps = selected?.steps ?? [];

  if (!selected && !running) {
    return (
      <div className="py-12 text-center text-sm text-mute">
        Select a run or start a new one.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {(() => {
        const gen = extractGenerativeUIFromSteps(
          liveSteps.length ? liveSteps : steps,
        );
        return gen ? (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-ink">
              Learning view
            </h2>
            <p className="mb-2 text-xs text-mute">
              Product surface for easy understanding
            </p>
            <GenerativeUIView
              payload={gen}
              onSaveAsNote={(t, b) => onSaveLearningNote(t, b)}
              savingNote={savingNote}
            />
          </div>
        ) : null;
      })()}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-ink">
          Trace
        </h2>
        <p className="mb-2 text-xs text-mute">
          LangSmith-style run tree — LLM spans, tools, inputs/outputs,
          tokens. Opens the moment you click Run.
        </p>
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

      {selected && !running && (
        <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
          <div className="text-xs text-mute">
            {formatDate(selected.created_at)}
          </div>
          <div className="mt-1 text-sm font-medium text-ink">
            {selected.goal}
          </div>
          {selected.final_answer && (
            <div className="mt-3">
              <div className="text-[11px] font-semibold uppercase text-mute">
                {selected.status === "waiting_approval"
                  ? "Status message"
                  : "Final answer"}
              </div>
              <div className="mt-1 whitespace-pre-wrap text-body-sm text-body">
                {selected.final_answer}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
