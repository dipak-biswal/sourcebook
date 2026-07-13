import { useMemo, useState } from "react";
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
  Sparkles,
  Timer,
  Wrench,
  XCircle,
} from "lucide-react";
import type { AgentRun, AgentStep } from "@/api";
import { isGenerativeUI } from "@/components/agents/generative-ui";
import { AgentApprovalCard, AgentStatusBadge } from "@/components/agents/shared";
import { prettyJson } from "@/components/agents/agent-utils";
import { Badge } from "@/components/ui/badge";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
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
  return true;
}

/** Live LLM span while the model is thinking (LangSmith-style). */
export type LlmTraceEvent = {
  id: string;
  kind: "llm";
  status: "running" | "done";
  duration_ms?: number;
  /** Full request size: system + tools + messages (not user text alone) */
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  has_tool_calls?: boolean;
  name?: string;
};

/** Chronological trace row for live streaming (preferred over separate arrays). */
export type LiveTraceSpan =
  | { kind: "llm"; event: LlmTraceEvent }
  | { kind: "step"; step: AgentStep };

function stepKindLabel(step: AgentStep): string {
  switch (step.type) {
    case "tool_call":
      return "Tool call";
    case "tool_result":
      return "Tool output";
    case "thought":
      return "Chain · reasoning";
    case "final":
      return "Chain · final";
    case "approval":
      return "Human approval";
    default:
      return step.type;
  }
}

function formatMs(ms?: number | null): string | null {
  if (ms == null || Number.isNaN(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
}

function TraceNode({
  step,
  defaultOpen,
  isLast,
}: {
  step: AgentStep;
  defaultOpen?: boolean;
  isLast?: boolean;
}) {
  const [open, setOpen] = useState(!!defaultOpen);
  const gen = isGenerativeUI(step.output);
  const isTool = step.type === "tool_call" || step.type === "tool_result";
  const isLlm = step.type === "thought" || step.type === "final";
  const isApproval = step.type === "approval";

  return (
    <div className="relative pl-7">
      {!isLast && (
        <div className="absolute bottom-0 left-[11px] top-5 w-px bg-hairline" />
      )}
      <div
        className={cn(
          "absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 bg-canvas",
          isApproval && "border-warning-border",
          isTool && "border-ink",
          isLlm && "border-mute",
          gen && "border-success-border",
        )}
      >
        {isTool ? (
          <Wrench className="h-2.5 w-2.5 text-ink" strokeWidth={2} />
        ) : isApproval ? (
          <Shield className="h-2.5 w-2.5 text-warning-text" strokeWidth={2} />
        ) : (
          <Brain className="h-2.5 w-2.5 text-mute" strokeWidth={2} />
        )}
      </div>

      <div
        className={cn(
          "mb-1.5 overflow-hidden rounded-[8px] border bg-canvas transition-shadow",
          "border-hairline hover:shadow-[var(--elevation-1)]",
          gen && "border-success-border/60",
          isApproval && "border-warning-border/60",
        )}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-canvas-soft"
        >
          <span className="mt-0.5 shrink-0 text-mute">
            {open ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="font-mono text-[10px] tabular-nums text-mute">
                #{step.step_index}
              </span>
              <span className="text-xs font-semibold text-ink">
                {step.tool_name || stepKindLabel(step)}
              </span>
              <Badge
                variant={
                  isTool ? "secondary" : isApproval ? "warning" : "outline"
                }
                className="text-[10px]"
              >
                {step.type === "tool_call"
                  ? "tool"
                  : step.type === "tool_result"
                    ? "tool"
                    : step.type === "thought" || step.type === "final"
                      ? "chain"
                      : step.type}
              </Badge>
              {gen && (
                <Badge variant="success" className="gap-0.5 text-[10px]">
                  <Sparkles className="h-2.5 w-2.5" />
                  generative UI
                </Badge>
              )}
              {formatMs(step.duration_ms) && (
                <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-mute">
                  <Timer className="h-2.5 w-2.5" />
                  {formatMs(step.duration_ms)}
                </span>
              )}
            </div>
            {!open && (
              <p className="mt-0.5 line-clamp-1 font-mono text-[10px] text-mute">
                {step.type === "tool_call"
                  ? prettyJson(step.input).slice(0, 120)
                  : gen
                    ? `Learning view · ${(step.output as { title?: string }).title ?? "ready"}`
                    : prettyJson(step.output).slice(0, 120)}
              </p>
            )}
          </div>
        </button>

        {open && (
          <div className="space-y-2.5 border-t border-hairline bg-canvas-soft px-3 py-2.5">
            {step.input != null && step.type !== "final" && (
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                  Inputs
                </div>
                <pre className="max-h-44 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2.5 font-mono text-[11px] leading-relaxed text-body">
                  {prettyJson(step.input)}
                </pre>
              </div>
            )}
            {step.output != null && (
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                  Outputs
                </div>
                {gen ? (
                  <p className="text-xs leading-relaxed text-body">
                    Structured learning UI produced — rendered in the{" "}
                    <strong className="text-ink">Learning view</strong> (product
                    surface), not as raw JSON here.
                  </p>
                ) : (
                  <pre className="max-h-56 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2.5 font-mono text-[11px] leading-relaxed text-body">
                    {prettyJson(step.output)}
                  </pre>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function LlmLiveNode({
  event,
  isLast,
}: {
  event: LlmTraceEvent;
  isLast?: boolean;
}) {
  const running = event.status === "running";
  return (
    <div className="relative mb-1.5 pl-7">
      {!isLast && (
        <div className="absolute bottom-0 left-[11px] top-5 w-px bg-hairline" />
      )}
      <div
        className={cn(
          "absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 bg-canvas",
          running ? "border-warning-border" : "border-ink",
        )}
      >
        {running ? (
          <Loader2 className="h-2.5 w-2.5 animate-spin text-warning-text" />
        ) : (
          <Brain className="h-2.5 w-2.5 text-ink" strokeWidth={2} />
        )}
      </div>
      <div
        className={cn(
          "rounded-[8px] border px-3 py-2.5",
          running
            ? "border-warning-border/70 bg-warning-soft/30"
            : "border-hairline bg-canvas",
        )}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-ink">
            {event.name || "ChatOpenAI"}
          </span>
          <Badge variant="outline" className="text-[10px]">
            llm
          </Badge>
          {running ? (
            <Badge variant="warning" className="gap-1 text-[10px]">
              <Loader2 className="h-2.5 w-2.5 animate-spin" />
              running
            </Badge>
          ) : (
            <Badge variant="success" className="text-[10px]">
              success
            </Badge>
          )}
          {formatMs(event.duration_ms) && (
            <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-mute">
              <Timer className="h-2.5 w-2.5" />
              {formatMs(event.duration_ms)}
            </span>
          )}
          {event.total_tokens != null && event.total_tokens > 0 && (
            <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-mute">
              <Coins className="h-2.5 w-2.5" />
              {event.total_tokens.toLocaleString()} tok
            </span>
          )}
        </div>
        {!running &&
          (event.prompt_tokens != null || event.completion_tokens != null) && (
            <p className="mt-1 font-mono text-[10px] text-mute">
              in {(event.prompt_tokens ?? 0).toLocaleString()}
              {" · "}
              out {(event.completion_tokens ?? 0).toLocaleString()}
              <span className="text-mute/80">
                {" "}
                (in = system + tool schemas + messages)
              </span>
            </p>
          )}
        <p className="mt-1 text-[11px] text-mute">
          {running
            ? "Model deciding next tool or final answer…"
            : event.has_tool_calls
              ? "Requested tool call(s) — see tool spans below"
              : "Produced final message"}
        </p>
      </div>
    </div>
  );
}

function StepRow({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(false);
  const gen = isGenerativeUI(step.output);

  return (
    <div className="border-b border-hairline/60 last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-canvas-soft-2"
      >
        <span className="shrink-0 text-mute">
          {open ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-mute">
          #{step.step_index}
        </span>
        <span className="text-xs font-medium text-ink">
          {step.tool_name || stepKindLabel(step)}
        </span>
        <Badge variant="outline" className="text-[10px]">
          {step.type === "tool_call"
            ? "tool"
            : step.type === "tool_result"
              ? "result"
              : step.type === "thought"
                ? "think"
                : step.type === "final"
                  ? "final"
                  : step.type}
        </Badge>
        {formatMs(step.duration_ms) && (
          <span className="ml-auto inline-flex items-center gap-0.5 font-mono text-[10px] text-mute">
            <Timer className="h-2.5 w-2.5" />
            {formatMs(step.duration_ms)}
          </span>
        )}
        {gen && (
          <Badge variant="success" className="gap-0.5 text-[10px]">
            <Sparkles className="h-2.5 w-2.5" />
            gen UI
          </Badge>
        )}
      </button>

      {open && (
        <div className="space-y-2 px-3 pb-2.5">
          {step.input != null && step.type !== "final" && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Inputs
              </div>
              <pre className="max-h-44 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] leading-relaxed text-body">
                {prettyJson(step.input)}
              </pre>
            </div>
          )}
          {step.output != null && (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Outputs
              </div>
              <pre className="max-h-56 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] leading-relaxed text-body">
                {prettyJson(step.output)}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StepGroup({ steps, isLast }: { steps: AgentStep[]; isLast?: boolean }) {
  const [open, setOpen] = useState(true);
  const firstTool = steps.find((s) => s.type === "tool_call");
  const toolName = firstTool?.tool_name || stepKindLabel(steps[0]);
  const totalDuration = steps.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0) || null;
  const hasTool = steps.some((s) => s.type === "tool_call" || s.type === "tool_result");

  return (
    <div className="relative mb-1.5 pl-7">
      {!isLast && (
        <div className="absolute bottom-0 left-[11px] top-5 w-px bg-hairline" />
      )}
      <div
        className={cn(
          "absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 bg-canvas",
          hasTool ? "border-ink" : "border-mute",
        )}
      >
        {hasTool ? (
          <Wrench className="h-2.5 w-2.5 text-ink" strokeWidth={2} />
        ) : (
          <Brain className="h-2.5 w-2.5 text-mute" strokeWidth={2} />
        )}
      </div>

      <div className="overflow-hidden rounded-[8px] border border-hairline bg-canvas transition-shadow hover:shadow-[var(--elevation-1)]">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-canvas-soft"
        >
          <span className="mt-0.5 shrink-0 text-mute">
            {open ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold text-ink">{toolName}</span>
              <Badge variant="secondary" className="text-[10px]">
                {steps.length} {steps.length === 1 ? "step" : "steps"}
              </Badge>
              {formatMs(totalDuration) && (
                <span className="inline-flex items-center gap-0.5 font-mono text-[10px] text-mute">
                  <Timer className="h-2.5 w-2.5" />
                  {formatMs(totalDuration)}
                </span>
              )}
            </div>
            {!open && (
              <p className="mt-0.5 line-clamp-1 font-mono text-[10px] text-mute">
                {steps.map((s) => stepKindLabel(s)).join(" → ")}
              </p>
            )}
          </div>
        </button>

        {open && <div className="border-t border-hairline bg-canvas-soft">{steps.map((s) => <StepRow key={s.id} step={s} />)}</div>}
      </div>
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
  forceOpenWhilePending = true,
  goal,
  /** Render flush inside a parent card (no outer border/shadow) */
  embedded,
  /** Live steps streamed in before the final run object exists */
  liveSteps,
  liveTokenUsage,
  liveLlmEvents,
  /** Preferred: chronological spans (LLM + tool) as they arrive */
  liveTrace,
}: {
  run: AgentRun | null | undefined;
  pending?: boolean;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  className?: string;
  forceOpenWhilePending?: boolean;
  goal?: string | null;
  embedded?: boolean;
  liveSteps?: AgentStep[];
  liveTokenUsage?: number | null;
  liveLlmEvents?: LlmTraceEvent[];
  liveTrace?: LiveTraceSpan[];
}) {
  const [showRun, setShowRun] = useState(readShowRun);

  const mergedSteps = useMemo(() => {
    const fromRun = run?.steps ?? [];
    const live = liveSteps ?? [];
    if (!live.length) {
      return [...fromRun].sort((a, b) => a.step_index - b.step_index);
    }
    const map = new Map<string, AgentStep>();
    for (const s of fromRun) map.set(s.id, s);
    for (const s of live) map.set(s.id, s);
    return [...map.values()].sort((a, b) => a.step_index - b.step_index);
  }, [run?.steps, liveSteps]);

  /** Build LangSmith-style chronological tree */
  const tree = useMemo(() => {
    if (liveTrace && liveTrace.length > 0) {
      // Merge completed run steps not yet in liveTrace (after done)
      const stepIds = new Set(
        liveTrace
          .filter((n): n is Extract<LiveTraceSpan, { kind: "step" }> => n.kind === "step")
          .map((n) => n.step.id),
      );
      const extra = mergedSteps
        .filter((s) => !stepIds.has(s.id))
        .map((step): LiveTraceSpan => ({ kind: "step", step }));
      return [...liveTrace, ...extra];
    }
    // Fallback: LLM events then steps (legacy), or steps only after complete
    const nodes: LiveTraceSpan[] = [];
    for (const ev of liveLlmEvents ?? []) {
      nodes.push({ kind: "llm", event: ev });
    }
    for (const step of mergedSteps) {
      nodes.push({ kind: "step", step });
    }
    return nodes;
  }, [liveTrace, liveLlmEvents, mergedSteps]);

  const isLive = !!pending;
  const open = isLive && forceOpenWhilePending ? true : showRun;

  function toggle() {
    if (isLive) return;
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

  const stats = useMemo(() => {
    const toolCalls = mergedSteps.filter((s) => s.type === "tool_call");
    const tools = [
      ...new Set(
        toolCalls.map((s) => s.tool_name).filter((n): n is string => !!n),
      ),
    ];
    const llmCount =
      (liveTrace?.filter((n) => n.kind === "llm").length ?? 0) ||
      (liveLlmEvents?.length ?? 0) ||
      mergedSteps.filter((s) => s.type === "thought" || s.type === "final")
        .length;
    return {
      total: tree.length || mergedSteps.length,
      toolCalls: toolCalls.length,
      tools,
      llmCount,
    };
  }, [mergedSteps, liveTrace, liveLlmEvents, tree.length]);

  /** Group consecutive tool steps into collapsible groups for scannability */
  type GroupedItem =
    | { kind: "llm"; event: LlmTraceEvent }
    | { kind: "steps"; steps: AgentStep[] };

  const grouped = useMemo(() => {
    const items: GroupedItem[] = [];
    let buf: AgentStep[] = [];
    const BREAK = new Set(["final", "approval"]);

    function flush() {
      if (buf.length) items.push({ kind: "steps", steps: buf });
      buf = [];
    }

    for (const node of tree) {
      if (node.kind === "llm") {
        flush();
        items.push({ kind: "llm", event: node.event });
      } else {
        if (BREAK.has(node.step.type) && buf.length) flush();
        buf.push(node.step);
      }
    }
    flush();
    return items;
  }, [tree]);

  const displayGoal = goal || run?.goal || null;
  const tokens = liveTokenUsage ?? run?.token_usage ?? null;
  const status = pending
    ? run?.status === "waiting_approval"
      ? "waiting_approval"
      : "running"
    : run?.status;

  if (!run && !pending && !(liveSteps && liveSteps.length) && !(liveTrace?.length)) {
    return null;
  }

  return (
    <div
      className={cn(
        embedded
          ? "w-full"
          : "w-full max-w-[min(100%,42rem)] overflow-hidden rounded-vercel-md border border-hairline bg-canvas shadow-[var(--elevation-2)]",
        isLive && !embedded && "border-warning-border ring-1 ring-warning-border/40",
        isLive && embedded && "border-t border-warning-border/40",
        className,
      )}
    >
      {/* LangSmith-like run header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline bg-canvas-soft px-3 py-2.5">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <Activity className="h-4 w-4 shrink-0 text-ink" strokeWidth={1.5} />
          <span className="text-xs font-semibold tracking-tight text-ink">
            Trace
          </span>
          {status ? (
            <AgentStatusBadge status={status} />
          ) : (
            <Badge variant="warning">running</Badge>
          )}
          {isLive && (
            <span className="inline-flex items-center gap-1 text-[10px] font-medium text-warning-text">
              <Loader2 className="h-3 w-3 animate-spin" />
              live
            </span>
          )}
          {run?.id && (
            <span
              className="hidden font-mono text-[10px] text-mute sm:inline"
              title={run.id}
            >
              {run.id.slice(0, 8)}…
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={toggle}
          disabled={isLive}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[6px] border px-2 py-1 text-[11px] font-medium transition-colors",
            open
              ? "border-ink bg-ink text-[var(--canvas)]"
              : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
            isLive && "cursor-not-allowed opacity-90",
          )}
        >
          {open ? (
            <Eye className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <EyeOff className="h-3 w-3" strokeWidth={1.5} />
          )}
          {open ? "Hide details" : "Show details"}
        </button>
      </div>

      {/* Metrics strip — tokens, span counts (LangSmith-style) */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-hairline px-3 py-2 text-[11px]">
        <span className="inline-flex items-center gap-1 font-medium text-ink">
          <Coins className="h-3.5 w-3.5 text-mute" strokeWidth={1.5} />
          {tokens != null
            ? `${tokens.toLocaleString()} tokens`
            : isLive
              ? "tokens…"
              : "—"}
        </span>
        <span className="text-mute">
          spans{" "}
          <span className="font-semibold tabular-nums text-ink">
            {stats.total}
          </span>
        </span>
        <span className="text-mute">
          llm{" "}
          <span className="font-semibold tabular-nums text-ink">
            {stats.llmCount}
          </span>
        </span>
        <span className="text-mute">
          tools{" "}
          <span className="font-semibold tabular-nums text-ink">
            {stats.toolCalls}
          </span>
        </span>
        {stats.tools.length > 0 && (
          <span className="max-w-full truncate font-mono text-[10px] text-ink">
            {stats.tools.join(" · ")}
          </span>
        )}
        {status === "completed" && !isLive && (
          <span className="inline-flex items-center gap-1 text-success-text">
            <CheckCircle2 className="h-3 w-3" />
            success
          </span>
        )}
        {status === "failed" && (
          <span className="inline-flex items-center gap-1 text-danger-text">
            <XCircle className="h-3 w-3" />
            error
          </span>
        )}
      </div>

      {displayGoal && (
        <div className="border-b border-hairline px-3 py-2">
          <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
            Inputs · goal
          </div>
          <p className="mt-0.5 text-xs leading-relaxed text-body">{displayGoal}</p>
        </div>
      )}

      {run?.error && (
        <div className="border-b border-danger-border bg-danger-soft px-3 py-2 text-xs text-danger-text">
          {run.error}
        </div>
      )}

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

      {open && (
        <div className="max-h-[min(65vh,32rem)] overflow-y-auto p-3">
          {/* Root chain node (LangSmith root run) */}
          <div className="relative mb-2 pl-7">
            <div className="absolute bottom-0 left-[11px] top-5 w-px bg-hairline" />
            <div
              className={cn(
                "absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 bg-canvas",
                isLive ? "border-warning-border" : "border-success-border",
              )}
            >
              {isLive ? (
                <Loader2 className="h-2.5 w-2.5 animate-spin text-warning-text" />
              ) : (
                <Activity className="h-2.5 w-2.5 text-success-text" strokeWidth={2} />
              )}
            </div>
            <div className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs font-semibold text-ink">Agent</span>
                <Badge variant="outline" className="text-[10px]">
                  chain
                </Badge>
                {isLive ? (
                  <Badge variant="warning" className="text-[10px]">
                    running
                  </Badge>
                ) : (
                  <Badge
                    variant={
                      status === "failed"
                        ? "danger"
                        : status === "waiting_approval"
                          ? "warning"
                          : "success"
                    }
                    className="text-[10px]"
                  >
                    {status === "waiting_approval"
                      ? "paused"
                      : status === "failed"
                        ? "error"
                        : "success"}
                  </Badge>
                )}
              </div>
              <p className="mt-0.5 text-[11px] text-mute">
                Root run · LLM ↔ tools loop
                {isLive ? " · spans appear as they execute" : ""}
              </p>
            </div>
          </div>

          <div className="mb-2 ml-1 flex items-center gap-2 text-[10px] font-bold uppercase tracking-wide text-mute">
            <Activity className="h-3 w-3" />
            Run tree
          </div>

          {isLive && tree.length === 0 && (
            <div className="relative mb-1.5 pl-7">
              <div className="absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 border-warning-border bg-canvas">
                <Loader2 className="h-2.5 w-2.5 animate-spin text-warning-text" />
              </div>
              <div className="rounded-[8px] border border-dashed border-warning-border bg-warning-soft/40 px-3 py-3 text-xs text-ink">
                Trace started — waiting for first span (LLM / tool)…
              </div>
            </div>
          )}

          {grouped.map((item, idx) => {
            const isLast = idx === grouped.length - 1 && !run?.final_answer;
            if (item.kind === "llm") {
              return <LlmLiveNode key={item.event.id} event={item.event} isLast={isLast} />;
            }
            if (item.steps.length <= 1) {
              const step = item.steps[0];
              return (
                <TraceNode
                  key={step.id}
                  step={step}
                  isLast={isLast}
                  defaultOpen={
                    idx === grouped.length - 1 ||
                    step.type === "approval" ||
                    step.type === "final" ||
                    isGenerativeUI(step.output)
                  }
                />
              );
            }
            return <StepGroup key={item.steps[0].id + "-group"} steps={item.steps} isLast={isLast} />;
          })}

          {run?.final_answer && !isLive && (
            <div className="relative mt-1 pl-7">
              <div className="absolute left-0 top-2.5 flex h-[22px] w-[22px] items-center justify-center rounded-full border-2 border-success-border bg-canvas">
                <CheckCircle2 className="h-2.5 w-2.5 text-success-text" />
              </div>
              <div className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5">
                <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
                  Outputs · final answer
                </div>
                <div className="mt-1 text-xs leading-relaxed text-body">
                  <MarkdownContent content={run.final_answer} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {!open && !run?.pending_tool && (
        <p className="px-3 py-2 text-[11px] text-mute">
          Details hidden. Learning view (if any) stays above — toggle to inspect
          the full LangSmith-style trace.
        </p>
      )}
    </div>
  );
}
