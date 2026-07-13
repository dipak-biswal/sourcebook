import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { agentStatusVariant, prettyJson } from "./agent-utils";
import type { AgentStep } from "@/api";

export function AgentStatusBadge({ status }: { status: string }) {
  return <Badge variant={agentStatusVariant(status)}>{status}</Badge>;
}

export function AgentStepCard({ step }: { step: AgentStep }) {
  return (
    <div className="rounded-[6px] border border-hairline bg-canvas px-3 py-2.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-ink">#{step.step_index}</span>
        <Badge variant="outline">{step.type}</Badge>
        {step.tool_name && <Badge variant="secondary">{step.tool_name}</Badge>}
      </div>
      {step.input != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">Input</div>
          <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-body">
            {prettyJson(step.input)}
          </pre>
        </div>
      )}
      {step.output != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">
            Output
          </div>
          <pre className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-body">
            {prettyJson(step.output)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function AgentStepList({
  steps,
  compact = false,
}: {
  steps: AgentStep[];
  compact?: boolean;
}) {
  const sorted = [...steps].sort((a, b) => a.step_index - b.step_index);
  const [expanded, setExpanded] = useState(false);

  if (sorted.length === 0) {
    return <p className="text-xs text-mute">No steps recorded.</p>;
  }

  if (compact) {
    return (
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-ink underline-offset-2 hover:underline"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
          )}
          {expanded ? "Hide step details" : `Show ${sorted.length} step details`}
        </button>
        <ul className="space-y-1">
          {sorted.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center gap-1.5 text-xs text-body"
            >
              <span className="font-medium text-ink">#{s.step_index}</span>
              <Badge variant="outline" className="text-[10px]">
                {s.type}
              </Badge>
              {s.tool_name && (
                <Badge variant="secondary" className="text-[10px]">
                  {s.tool_name}
                </Badge>
              )}
            </li>
          ))}
        </ul>
        {expanded && (
          <div className="space-y-2 pt-1">
            {sorted.map((s) => (
              <AgentStepCard key={`full-${s.id}`} step={s} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {sorted.map((s) => (
        <AgentStepCard key={s.id} step={s} />
      ))}
    </div>
  );
}

type PendingTool = {
  id?: string;
  name?: string;
  args?: Record<string, unknown>;
};

export function AgentApprovalCard({
  pendingTool,
  approving,
  onApprove,
  onReject,
  className,
}: {
  pendingTool: PendingTool;
  approving?: boolean;
  onApprove: () => void;
  onReject: () => void;
  className?: string;
}) {
  return (
    <div
      className={
        className ??
        "rounded-[6px] border border-warning-border bg-warning-soft p-3"
      }
    >
      <div className="text-sm font-semibold text-ink">Approval required</div>
      <p className="mt-1 text-xs text-body">
        Write tool{" "}
        <code className="rounded bg-canvas px-1">
          {pendingTool.name ?? "unknown"}
        </code>
        . Review args, then approve or reject.{" "}
        <span className="font-medium text-ink">
          After approve, the agent continues
        </span>{" "}
        (confirm + next steps)—it does not stop at the write.
      </p>
      <pre className="mt-2 max-h-40 overflow-auto rounded border border-hairline bg-canvas p-2 text-xs text-body">
        {prettyJson(pendingTool.args ?? {})}
      </pre>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          className="rounded-[6px]"
          disabled={approving}
          onClick={onApprove}
        >
          {approving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
          Approve
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={approving}
          onClick={onReject}
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          Reject
        </Button>
      </div>
    </div>
  );
}
