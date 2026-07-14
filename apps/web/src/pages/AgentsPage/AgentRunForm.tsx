import { Loader2, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

export function AgentRunForm() {
  const {
    exampleGoals,
    goal,
    running,
    workspaceId,
    onGoalChange,
    onRun,
  } = useAgentPage();

  return (
    <form
      onSubmit={onRun}
      className={cn(
        "mb-6 rounded-vercel-md border border-hairline bg-canvas p-4",
        running && "opacity-80",
      )}
    >
      <h1 className="text-sm font-semibold text-ink">Run an agent</h1>
      <p className="mt-1 text-xs text-mute">
        Search and analyze documents in your workspace.
      </p>

      <label className="mt-4 block">
        <span className="mb-1 block text-xs text-mute">Goal</span>
        <Input
          value={goal}
          onChange={(e) => onGoalChange(e.target.value)}
          disabled={running || !workspaceId}
          placeholder="What should the agent do?"
        />
      </label>

      {!workspaceId && (
        <p className="mt-2 text-xs text-mute">
          Select a workspace in the sidebar to run an agent.
        </p>
      )}

      <Button
        type="submit"
        className="mt-3 rounded-[6px]"
        disabled={running || !workspaceId || !goal.trim()}
      >
        {running ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Play className="h-4 w-4" strokeWidth={1.5} />
        )}
        {running ? "Running agent…" : "Run agent"}
      </Button>

      {!running && exampleGoals.length > 0 && (
        <div className="mt-4 border-t border-hairline pt-3">
          <p className="mb-2 text-[11px] font-medium text-mute">Try an example</p>
          <div className="flex flex-wrap gap-1.5">
            {exampleGoals.map((example) => (
              <button
                key={example.goal}
                type="button"
                disabled={!workspaceId}
                onClick={() => onGoalChange(example.goal)}
                className={cn(
                  "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                  goal === example.goal
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
    </form>
  );
}