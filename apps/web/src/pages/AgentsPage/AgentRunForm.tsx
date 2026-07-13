import { Link } from "react-router-dom";
import { Loader2, Play } from "lucide-react";
import { AGENT_EXAMPLE_GOALS } from "@/components/agents/agent-utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAgentPage } from "./agent-page-context";

export function AgentRunForm() {
  const {
    goal,
    running,
    workspaceId,
    onGoalChange,
    onRun,
  } = useAgentPage();

  return (
    <form
      onSubmit={onRun}
      className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4"
    >
      <h1 className="text-sm font-semibold text-ink">Agents workspace</h1>
      <p className="mt-1 text-xs text-mute">
        Full run history, trace tabs, and notes live here. Read tools run
        immediately; <strong className="text-ink">create_note</strong> waits for
        Approve / Reject. For a quick in-thread run, use{" "}
        <Link
          to="/chat"
          className="font-medium text-ink underline-offset-2 hover:underline"
        >
          Chat → Agent
        </Link>
        .
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {AGENT_EXAMPLE_GOALS.map((g) => (
          <button
            key={g}
            type="button"
            disabled={running}
            onClick={() => onGoalChange(g)}
            className={
              "rounded-full border px-2.5 py-1 text-left text-[11px] transition-colors" +
              (goal === g
                ? " border-ink bg-ink text-[var(--canvas)]"
                : " border-hairline bg-canvas text-body hover:bg-canvas-soft-2")
            }
          >
            {g.length > 48 ? `${g.slice(0, 48)}…` : g}
          </button>
        ))}
      </div>

      <label className="mt-3 block">
        <span className="mb-1 block text-xs text-mute">Goal</span>
        <Input
          value={goal}
          onChange={(e) => onGoalChange(e.target.value)}
          disabled={running || !workspaceId}
          placeholder="What should the agent do?"
        />
      </label>
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
        {running
          ? "Streaming trace…"
          : "Run agent"}
      </Button>
    </form>
  );
}
