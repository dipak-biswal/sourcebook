import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Coins,
  Eye,
  EyeOff,
  Loader2,
  Shield,
  Wrench,
  XCircle,
} from "lucide-react";
import type { AgentRun, AgentStep } from "@/api";
import { isGenerativeUI } from "@/components/agents/GenerativeUI";
import {
  AgentApprovalCard,
  AgentStatusBadge,
  prettyJson,
} from "@/components/agents/shared";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const TOGGLE_KEY = "sourcebook_agent_show_run_view";

function readShowRun(): boolean {
  try {
    const v = localStorage.getItem(TOGGLE_KEY);
    if (v === "0") return false;
    if (v === "1") return true;
  } catch {
    /* ignore */
  }
  return true; // default: show behind-the-scenes
}

function stepLabel(step: AgentStep): string {
  switch (step.type) {
    case "tool_call":
      return `Decided to call tool`;
    case "tool_result":
      return `Tool returned output`;
    case "thought":
      return `Model reasoning`;
    case "final":
      return `Final decision / answer`;
    case "approval":
      return `Human approval gate`;
    default:
      return step.type;
  }
}

function StepIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5 shrink-0";
  switch (type) {
    case "tool_call":
      return <Wrench className={cn(cls, "text-ink")} strokeWidth={1.5} />;
    case "tool_result":
      return <Activity className={cn(cls, "text-mute")} strokeWidth={1.5} />;
    case "thought":
    case "final":
      return <Brain className={cn(cls, "text-ink")} strokeWidth={1.5} />;
    case "approval":
      return <Shield className={cn(cls, "text-warning-text")} strokeWidth={1.5} />;
    default:
      return <Activity className={cn(cls, "text-mute")} strokeWidth={1.5} />;
  }
}

function summarizeOutput(step: AgentStep): string {
  const out = step.output;
  if (out == null) return "";
  if (isGenerativeUI(out)) {
    return `Learning view: “${out.title}” (${out.blocks?.length ?? 0} sections) — shown above`;
  }
  if (typeof out === "object" && out !== null && "error" in out) {
    return `Error: ${String((out as { error: unknown }).error)}`;
  }
  if (step.type === "approval" && typeof out === "object" && out !== null) {
    const s = (out as { status?: string }).status;
    if (s === "waiting_approval") return "Paused — waiting for human approve/reject";
    if (s === "approved") return "Human approved write";
    if (s === "rejected") return "Human rejected write";
  }
  if (typeof out === "string") {
    return out.length > 140 ? `${out.slice(0, 140)}…` : out;
  }
  if (Array.isArray(out)) {
    return `List with ${out.length} item(s)`;
  }
  try {
    const s = JSON.stringify(out);
    return s.length > 140 ? `${s.slice(0, 140)}…` : s;
  } catch {
    return "—";
  }
}

function TraceStep({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(
    step.type === "approval" || step.type === "final",
  );
  const gen = isGenerativeUI(step.output);

  return (
    <div className="rounded-[8px] border border-hairline bg-canvas px-3 py-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 text-left"
      >
        <span className="mt-0.5">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5 text-mute" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 text-mute" />
          )}
        </span>
        <StepIcon type={step.type} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-semibold text-mute">
              #{step.step_index}
            </span>
            <Badge variant="outline" className="text-[10px]">
              {step.type}
            </Badge>
            {step.tool_name && (
              <Badge variant="secondary" className="font-mono text-[10px]">
                {step.tool_name}
              </Badge>
            )}
            {gen && (
              <Badge variant="success" className="text-[10px]">
                generative UI
              </Badge>
            )}
          </div>
          <p className="mt-0.5 text-xs font-medium text-ink">{stepLabel(step)}</p>
          {!open && (
            <p className="mt-0.5 line-clamp-2 text-[11px] text-mute">
              {step.type === "tool_call"
                ? prettyJson(step.input).slice(0, 120)
                : summarizeOutput(step)}
            </p>
          )}
        </div>
      </button>

      {open && (
        <div className="mt-2 space-y-2 border-t border-hairline pt-2 pl-6">
          {step.type === "tool_call" && step.input != null && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-mute">
                Tool input / decision args
              </div>
              <pre className="mt-1 max-h-36 overflow-auto rounded-[6px] border border-hairline bg-canvas-soft p-2 text-[11px] leading-relaxed text-body">
                {prettyJson(step.input)}
              </pre>
            </div>
          )}
          {step.output != null && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-mute">
                {step.type === "thought" || step.type === "final"
                  ? "Model text"
                  : "Output / observation"}
              </div>
              {gen ? (
                <p className="mt-1 text-xs text-body">
                  Structured learning UI generated — rendered in the panel above
                  (not dumped as raw JSON here).
                </p>
              ) : (
                <pre className="mt-1 max-h-48 overflow-auto rounded-[6px] border border-hairline bg-canvas-soft p-2 text-[11px] leading-relaxed text-body">
                  {prettyJson(step.output)}
                </pre>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function AgentRunPanel({
  run,
  pending,
  approving,
  onApprove,
  onReject,
  className,
  /** When true, force run view open (e.g. while agent working) */
  forceOpenWhilePending,
}: {
  run: AgentRun | null | undefined;
  pending?: boolean;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  className?: string;
  forceOpenWhilePending?: boolean;
}) {
  const [showRun, setShowRun] = useState(readShowRun);

  useEffect(() => {
    if (forceOpenWhilePending && pending) setShowRun(true);
  }, [forceOpenWhilePending, pending]);

  function toggle() {
    setShowRun((v) => {
      const next = !v;
      try {
        localStorage.setItem(TOGGLE_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }

  const steps = useMemo(
    () => [...(run?.steps ?? [])].sort((a, b) => a.step_index - b.step_index),
    [run?.steps],
  );

  const stats = useMemo(() => {
    const toolCalls = steps.filter((s) => s.type === "tool_call");
    const tools = [
      ...new Set(
        toolCalls.map((s) => s.tool_name).filter((n): n is string => !!n),
      ),
    ];
    const approvals = steps.filter((s) => s.type === "approval").length;
    const thoughts = steps.filter(
      (s) => s.type === "thought" || s.type === "final",
    ).length;
    return {
      total: steps.length,
      toolCalls: toolCalls.length,
      tools,
      approvals,
      thoughts,
    };
  }, [steps]);

  if (!run && !pending) return null;

  return (
    <div
      className={cn(
        "w-full max-w-[min(100%,36rem)] rounded-vercel-md border border-hairline bg-canvas shadow-[var(--elevation-2)]",
        className,
      )}
    >
      {/* Header + toggle */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-3 py-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Activity className="h-4 w-4 shrink-0 text-ink" strokeWidth={1.5} />
          <span className="text-xs font-semibold text-ink">Agent run</span>
          {run ? (
            <AgentStatusBadge status={run.status} />
          ) : (
            <Badge variant="warning">running</Badge>
          )}
          {pending && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-mute" />
          )}
        </div>
        <button
          type="button"
          onClick={toggle}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[6px] border px-2 py-1 text-[11px] font-medium transition-colors",
            showRun
              ? "border-ink bg-ink text-[var(--canvas)]"
              : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
          )}
          title="Show or hide behind-the-scenes tool trace"
        >
          {showRun ? (
            <Eye className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <EyeOff className="h-3 w-3" strokeWidth={1.5} />
          )}
          {showRun ? "Hide run view" : "Show run view"}
        </button>
      </div>

      {/* Cost + stats strip — always visible */}
      <div className="flex flex-wrap gap-3 border-b border-hairline bg-canvas-soft px-3 py-2 text-[11px] text-body">
        <span className="inline-flex items-center gap-1 font-medium text-ink">
          <Coins className="h-3.5 w-3.5 text-mute" strokeWidth={1.5} />
          {run?.token_usage != null
            ? `~${run.token_usage.toLocaleString()} tokens (LLM)`
            : pending
              ? "Tokens: metering…"
              : "Tokens: —"}
        </span>
        <span className="text-mute">
          Steps: <span className="font-medium text-ink">{stats.total}</span>
        </span>
        <span className="text-mute">
          Tool calls:{" "}
          <span className="font-medium text-ink">{stats.toolCalls}</span>
        </span>
        {stats.tools.length > 0 && (
          <span className="text-mute">
            Tools:{" "}
            <span className="font-mono font-medium text-ink">
              {stats.tools.join(", ")}
            </span>
          </span>
        )}
        {run?.status === "completed" && (
          <span className="inline-flex items-center gap-1 text-success-text">
            <CheckCircle2 className="h-3 w-3" strokeWidth={1.5} />
            Done
          </span>
        )}
        {run?.status === "failed" && (
          <span className="inline-flex items-center gap-1 text-danger-text">
            <XCircle className="h-3 w-3" strokeWidth={1.5} />
            Failed
          </span>
        )}
        {run?.status === "waiting_approval" && (
          <span className="font-medium text-warning-text">Needs approval</span>
        )}
      </div>

      {run?.error && (
        <div className="border-b border-danger-border bg-danger-soft px-3 py-2 text-xs text-danger-text">
          {run.error}
        </div>
      )}

      {/* HITL always visible when pending approval */}
      {run?.status === "waiting_approval" &&
        run.pending_tool &&
        onApprove &&
        onReject && (
          <div className="border-b border-hairline p-3">
            <AgentApprovalCard
              pendingTool={run.pending_tool}
              approving={approving}
              onApprove={onApprove}
              onReject={onReject}
            />
          </div>
        )}

      {/* Behind-the-scenes timeline */}
      {showRun && (
        <div className="space-y-2 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-mute">
              Behind the scenes
            </p>
            <p className="text-[10px] text-mute">
              Tool choice · I/O · model decisions
            </p>
          </div>

          {pending && steps.length === 0 && (
            <div className="flex items-center gap-2 rounded-[8px] border border-dashed border-hairline px-3 py-4 text-xs text-mute">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Agent is planning and calling tools…
            </div>
          )}

          {steps.length === 0 && !pending && (
            <p className="text-xs text-mute">No steps recorded for this run.</p>
          )}

          <div className="space-y-2">
            {steps.map((s) => (
              <TraceStep key={s.id} step={s} />
            ))}
          </div>

          {run?.goal && (
            <div className="rounded-[6px] border border-hairline bg-canvas-soft px-2.5 py-2">
              <div className="text-[10px] font-semibold uppercase text-mute">
                Original goal
              </div>
              <p className="mt-0.5 text-xs text-body">{run.goal}</p>
            </div>
          )}
        </div>
      )}

      {!showRun && !run?.pending_tool && (
        <p className="px-3 py-2 text-[11px] text-mute">
          Run view hidden — turn it on to inspect tools, outputs, and LLM token
          use. Learning view (if any) stays above.
        </p>
      )}
    </div>
  );
}
