import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Clock,
  Coins,
  GitBranch,
  Loader2,
  Shield,
  Sparkles,
  Target,
  Wrench,
} from "lucide-react";
import type { AgentRun } from "@/api";
import { parseWebSearchOutput, prettyJson } from "@/components/agents/agent-utils";
import { LlmModelBadge } from "@/components/agents/llm-model";
import type {
  ExecutionTrace,
  TraceChild,
  TraceHitlEmbedChild,
  TraceLlmChild,
  TraceLlmRole,
  TracePhase,
  TracePresentationPhase,
  TraceState,
} from "@/components/agents/execution-trace-types";
import { isGenerativeUI } from "@/components/agents/generative-ui";
import { AgentApprovalCard } from "@/components/agents/shared";
import { WebSearchResults } from "@/components/agents/WebSearchResults";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** Any node in the flattened span tree — a phase or a nested child. */
type TraceNode = TracePhase | TraceChild;

type Row = {
  node: TraceNode;
  depth: number;
  hasChildren: boolean;
};

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtDuration(ms: number | null | undefined): string | null {
  if (ms == null || Number.isNaN(ms)) return null;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const s = ms / 1000;
  return `${s.toFixed(s < 10 ? 2 : 1)}s`;
}

function nodeChildren(node: TraceNode): TraceChild[] {
  const kids = (node as { children?: TraceChild[] }).children;
  return Array.isArray(kids) ? kids : [];
}

function nodeIcon(node: TraceNode): typeof Brain {
  switch (node.type) {
    case "goal":
      return Target;
    case "agent_turn":
    case "llm_response":
      return Brain;
    case "tool":
      return node.tool_name === "generative_ui" ? Sparkles : Wrench;
    case "visual_stage":
      return Wrench;
    case "hitl":
    case "hitl_embed":
      return Shield;
    case "handoff":
      return Target;
    case "final_answer":
    case "synthesis":
      return CheckCircle2;
    case "presentation":
      return Sparkles;
    default:
      return Brain;
  }
}

function DynIcon({ icon: Icon, className }: { icon: typeof Brain; className?: string }) {
  return <Icon className={className} strokeWidth={1.75} />;
}

function nodeModel(node: TraceNode): string | null | undefined {
  return (node as { model?: string | null }).model;
}

function nodeTokens(node: TraceNode): {
  prompt?: number | null;
  completion?: number | null;
  total?: number | null;
} {
  const n = node as {
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
    total_tokens?: number | null;
  };
  return { prompt: n.prompt_tokens, completion: n.completion_tokens, total: n.total_tokens };
}

function llmRoleBadge(role: TraceLlmRole | string | null | undefined): string | null {
  switch (role) {
    case "orchestrator_decision":
    case "orchestrator_response":
    case "orchestrator":
      return "Orchestrator";
    case "embedded_planner":
      return "Planner LLM";
    case "embedded_render":
      return "Render LLM";
    case "embedded":
      return "Tool LLM";
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Small presentational atoms
// ---------------------------------------------------------------------------

function StateDot({ state }: { state: TraceState }) {
  if (state === "running") {
    return <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-warning-text" />;
  }
  if (state === "error") {
    return <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-red-500" strokeWidth={2} />;
  }
  return (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        state === "done" ? "bg-success-border" : "bg-hairline",
      )}
    />
  );
}

function StatusBadge({ state }: { state: TraceState }) {
  if (state === "running") {
    return (
      <Badge variant="warning" className="gap-1 text-[10px]">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-warning" />
        </span>
        running
      </Badge>
    );
  }
  if (state === "error") {
    return (
      <Badge variant="danger" className="gap-1 text-[10px]">
        <AlertTriangle className="h-2.5 w-2.5" />
        error
      </Badge>
    );
  }
  if (state === "done") {
    return (
      <Badge variant="success" className="text-[10px]">
        success
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="text-[10px]">
      pending
    </Badge>
  );
}

/** Waterfall bar positioned by start offset, scaled by duration. */
function WaterfallBar({
  node,
  runStart,
  total,
}: {
  node: TraceNode;
  runStart: number | null | undefined;
  total: number | null | undefined;
}) {
  const started = (node as { started_ms?: number | null }).started_ms;
  const duration = (node as { duration_ms?: number | null }).duration_ms;

  if (runStart == null || !total || total <= 0 || started == null) {
    return <div className="h-1.5 w-full rounded-full bg-transparent" />;
  }
  const leftPct = Math.min(Math.max(((started - runStart) / total) * 100, 0), 100);
  const widthPct = Math.min(Math.max(((duration ?? 0) / total) * 100, 0), 100 - leftPct);

  return (
    <div className="relative h-1.5 w-full overflow-hidden rounded-full bg-canvas-soft-2/60">
      <div
        className={cn(
          "absolute top-0 h-full rounded-full",
          node.state === "running" && "bg-warning-border",
          node.state === "error" && "bg-red-500",
          node.state === "done" && "bg-ink/55",
          node.state === "pending" && "bg-hairline",
        )}
        style={{ left: `${leftPct}%`, width: `${widthPct}%`, minWidth: 2 }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Left pane — span tree with waterfall
// ---------------------------------------------------------------------------

function SpanRow({
  row,
  selected,
  collapsed,
  onSelect,
  onToggle,
  runStart,
  total,
  rowRef,
}: {
  row: Row;
  selected: boolean;
  collapsed: boolean;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  runStart: number | null | undefined;
  total: number | null | undefined;
  rowRef?: React.RefObject<HTMLButtonElement | null>;
}) {
  const { node, depth, hasChildren } = row;
  const duration = fmtDuration((node as { duration_ms?: number | null }).duration_ms);
  const roleBadge =
    node.type === "llm_response"
      ? llmRoleBadge((node as TraceLlmChild).llm_role)
      : null;

  return (
    <button
      ref={rowRef}
      type="button"
      data-trace-id={node.id}
      onClick={() => onSelect(node.id)}
      className={cn(
        "group flex w-full items-center gap-2 rounded-[6px] py-1 pr-2 text-left transition-colors",
        selected ? "bg-ink/[0.06] ring-1 ring-ink/15" : "hover:bg-canvas-soft",
      )}
      style={{ paddingLeft: 6 + depth * 14 }}
    >
      <span
        className="flex h-4 w-4 shrink-0 items-center justify-center text-mute"
        onClick={(e) => {
          if (!hasChildren) return;
          e.stopPropagation();
          onToggle(node.id);
        }}
        role={hasChildren ? "button" : undefined}
        aria-label={hasChildren ? (collapsed ? "Expand" : "Collapse") : undefined}
      >
        {hasChildren ? (
          collapsed ? (
            <ChevronRight className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )
        ) : null}
      </span>

      <StateDot state={node.state} />
      <DynIcon icon={nodeIcon(node)} className="h-3.5 w-3.5 shrink-0 text-ink" />

      <span className="flex min-w-0 flex-1 items-center gap-1.5">
        <span
          className={cn(
            "truncate text-[11px] font-medium",
            node.state === "error" ? "text-red-500" : "text-ink",
          )}
        >
          {node.label}
        </span>
        {roleBadge && (
          <Badge variant="outline" className="shrink-0 text-[9px] font-normal">
            {roleBadge}
          </Badge>
        )}
      </span>

      <span className="hidden w-24 shrink-0 sm:block">
        <WaterfallBar node={node} runStart={runStart} total={total} />
      </span>
      <span className="w-12 shrink-0 text-right font-mono text-[10px] tabular-nums text-mute">
        {duration ?? ""}
      </span>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Right pane — span detail
// ---------------------------------------------------------------------------

function StatCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <div className="text-[9px] font-bold uppercase tracking-wide text-mute">{label}</div>
      <div className="mt-0.5 truncate text-[12px] text-body">{children}</div>
    </div>
  );
}

function CodeBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">{title}</div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] leading-relaxed text-body">
        {children}
      </pre>
    </div>
  );
}

function formatPrompt(prompt: TraceLlmChild["prompt"]): string {
  if (prompt == null) return "";
  if (typeof prompt === "string") return prompt;
  if (!Array.isArray(prompt) || prompt.length === 0) return "";
  return prompt
    .map((m) => `[${m.role || "message"}]\n${m.content ?? ""}`)
    .join("\n\n");
}

function LlmDetail({ node }: { node: TraceLlmChild }) {
  const promptText = formatPrompt(node.prompt);
  return (
    <div className="space-y-3">
      {promptText && <CodeBlock title="Prompt">{promptText}</CodeBlock>}
      <CodeBlock title="Output">
        {node.output || (node.state === "running" ? "…" : "—")}
      </CodeBlock>
    </div>
  );
}

function ToolDetail({ node }: { node: Extract<TraceChild, { type: "tool" }> }) {
  const web =
    node.tool_name === "web_search" && node.output
      ? parseWebSearchOutput(node.output)
      : null;
  return (
    <div className="space-y-3">
      {node.input != null && <CodeBlock title="Input">{prettyJson(node.input)}</CodeBlock>}
      {node.output != null && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Output</div>
          {web ? (
            <WebSearchResults data={web} compact />
          ) : (
            <pre className="max-h-56 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
              {prettyJson(node.output)}
            </pre>
          )}
        </div>
      )}
      {node.has_embedded_llm && (
        <p className="text-[11px] text-mute">
          The embedded LLM call is shown as a child span in the tree.
        </p>
      )}
      {node.output == null && node.state === "running" && (
        <div className="flex items-center gap-2 text-[11px] text-warning-text">
          <Loader2 className="h-3 w-3 animate-spin" />
          Executing…
        </div>
      )}
    </div>
  );
}

function HitlDetail({
  node,
  run,
  approving,
  onApprove,
  onReject,
}: {
  node: Extract<TracePhase, { type: "hitl" }> | TraceHitlEmbedChild;
  run: AgentRun | null | undefined;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const output =
    node.output && typeof node.output === "object"
      ? (node.output as { status?: string })
      : null;

  if (node.pending && run?.pending_tool && onApprove && onReject) {
    return (
      <AgentApprovalCard
        pendingTool={run.pending_tool}
        approving={approving}
        onApprove={onApprove}
        onReject={onReject}
        className="border-warning-border/60 bg-warning-soft/40"
      />
    );
  }
  if (node.building && output?.status !== "approved") {
    return (
      <div className="flex items-center gap-2 text-[11px] text-warning-text">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building visual summary…
      </div>
    );
  }
  if (output?.status === "approved") {
    return <p className="text-body">Approved — visual summary generated.</p>;
  }
  if (output?.status === "rejected") {
    return <p className="text-body">Rejected — answer kept as text only.</p>;
  }
  if (node.input != null) {
    return <CodeBlock title="Input">{prettyJson(node.input)}</CodeBlock>;
  }
  return <p className="text-mute">Completed</p>;
}

function PresentationDetail({ node }: { node: TracePresentationPhase }) {
  const output = isGenerativeUI(node.output) ? node.output : null;
  if (!output) return <p className="text-[11px] text-mute">Waiting for generated UI…</p>;
  return (
    <div className="space-y-1.5 rounded-[6px] border border-hairline bg-canvas-soft/40 p-2.5">
      <p className="font-medium text-ink">{output.title}</p>
      {output.plain_summary && <p className="text-[11px] text-mute">{output.plain_summary}</p>}
      <div className="flex flex-wrap gap-2 text-[10px] text-mute">
        {node.presentation_profile && (
          <span>Profile: {node.presentation_profile.replace(/_/g, " ")}</span>
        )}
        {node.block_count != null && <span>{node.block_count} blocks</span>}
      </div>
    </div>
  );
}

function TraceDetailBody(props: {
  node: TraceNode;
  run: AgentRun | null | undefined;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const { node } = props;
  switch (node.type) {
    case "goal":
      return <p className="text-body">{node.goal}</p>;
    case "llm_response":
    case "synthesis":
      return <LlmDetail node={node as TraceLlmChild} />;
    case "tool":
      return <ToolDetail node={node} />;
    case "hitl":
    case "hitl_embed":
      return (
        <HitlDetail
          node={node}
          run={props.run}
          approving={props.approving}
          onApprove={props.onApprove}
          onReject={props.onReject}
        />
      );
    case "presentation":
      return <PresentationDetail node={node as TracePresentationPhase} />;
    case "handoff":
    case "final_answer":
      return (
        <CodeBlock title="Output">
          {(node as { output?: string }).output || "—"}
        </CodeBlock>
      );
    case "agent_turn":
      return (
        <p className="text-[11px] text-mute">
          Agent turn with {nodeChildren(node).length} step
          {nodeChildren(node).length === 1 ? "" : "s"}. Select a child span for details.
        </p>
      );
    case "visual_stage":
      return (
        <p className="text-[11px] text-mute">
          Visual pipeline stage. Select a child span for details.
        </p>
      );
    default:
      return <p className="text-mute">—</p>;
  }
}

function TraceDetailPanel({
  node,
  runStart,
  run,
  approving,
  onApprove,
  onReject,
}: {
  node: TraceNode | null;
  runStart: number | null | undefined;
  run: AgentRun | null | undefined;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  if (!node) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-xs text-mute">
        Select a span to inspect its input, output, latency, and tokens.
      </div>
    );
  }
  const duration = fmtDuration((node as { duration_ms?: number | null }).duration_ms);
  const started = (node as { started_ms?: number | null }).started_ms;
  const offset =
    started != null && runStart != null ? fmtDuration(started - runStart) : null;
  const tokens = nodeTokens(node);
  const model = nodeModel(node);
  const errorMsg = (node as { error?: string | null }).error;

  return (
    <div className="p-3.5">
      <div className="flex items-center gap-2">
        <DynIcon icon={nodeIcon(node)} className="h-4 w-4 shrink-0 text-ink" />
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
          {node.label}
        </span>
        <StatusBadge state={node.state} />
      </div>

      {errorMsg && (
        <div className="mt-2 flex items-start gap-1.5 rounded-[6px] border border-red-500/30 bg-red-500/[0.06] p-2 text-[11px] text-red-500">
          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
          <span className="min-w-0 break-words">{errorMsg}</span>
        </div>
      )}

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2.5 rounded-[6px] border border-hairline bg-canvas-soft/40 p-2.5 sm:grid-cols-3">
        <StatCell label="Latency">
          <span className="inline-flex items-center gap-1 font-mono tabular-nums">
            <Clock className="h-3 w-3 text-mute" />
            {duration ?? "—"}
          </span>
        </StatCell>
        <StatCell label="Start">
          <span className="font-mono tabular-nums text-mute">{offset ? `+${offset}` : "—"}</span>
        </StatCell>
        {model ? (
          <StatCell label="Model">
            <LlmModelBadge model={model} />
          </StatCell>
        ) : (
          <StatCell label="Type">{node.type.replace(/_/g, " ")}</StatCell>
        )}
        {(tokens.total ?? 0) > 0 && (
          <StatCell label="Tokens">
            <span className="font-mono tabular-nums">
              {(tokens.total ?? 0).toLocaleString()}
            </span>
          </StatCell>
        )}
        {(tokens.prompt ?? 0) > 0 && (
          <StatCell label="Input tok">
            <span className="font-mono tabular-nums">
              {(tokens.prompt ?? 0).toLocaleString()}
            </span>
          </StatCell>
        )}
        {(tokens.completion ?? 0) > 0 && (
          <StatCell label="Output tok">
            <span className="font-mono tabular-nums">
              {(tokens.completion ?? 0).toLocaleString()}
            </span>
          </StatCell>
        )}
      </div>

      <div className="mt-3 text-xs leading-relaxed text-body">
        <TraceDetailBody
          node={node}
          run={run}
          approving={approving}
          onApprove={onApprove}
          onReject={onReject}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tree flattening + container discovery
// ---------------------------------------------------------------------------

function flattenRows(nodes: TraceNode[], depth: number, collapsed: Set<string>, out: Row[]) {
  for (const node of nodes) {
    const kids = nodeChildren(node);
    out.push({ node, depth, hasChildren: kids.length > 0 });
    if (kids.length > 0 && !collapsed.has(node.id)) {
      flattenRows(kids, depth + 1, collapsed, out);
    }
  }
}

function collectContainerIds(nodes: TraceNode[], out: Set<string>) {
  for (const node of nodes) {
    const kids = nodeChildren(node);
    if (kids.length > 0) {
      out.add(node.id);
      collectContainerIds(kids, out);
    }
  }
}

function findNode(nodes: TraceNode[], id: string): TraceNode | null {
  for (const node of nodes) {
    if (node.id === id) return node;
    const hit = findNode(nodeChildren(node), id);
    if (hit) return hit;
  }
  return null;
}

function traceProgress(phases: TracePhase[]): number {
  const nodes = phases.filter((p) => p.type !== "goal");
  if (!nodes.length) return 8;
  const done = nodes.filter((p) => p.state === "done").length;
  const running = nodes.some((p) => p.state === "running");
  const base = Math.round((done / nodes.length) * 100);
  return running ? Math.min(base + 6, 99) : base;
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function AgentTraceTree({
  run,
  executionTrace,
  running,
  approving,
  onApprove,
  onReject,
}: {
  run: AgentRun | null | undefined;
  executionTrace?: ExecutionTrace | null;
  running?: boolean;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const activeRowRef = useRef<HTMLButtonElement | null>(null);

  const trace = executionTrace ?? run?.execution_trace ?? null;
  // Presentation "Visual summary" duplicates the Visual summary tab; keep the agent turn.
  const phases = useMemo(
    () => (trace?.phases ?? []).filter((p) => p.type !== "presentation"),
    [trace?.phases],
  );
  const isLive = running || approving || (trace != null && !trace.is_complete);
  const activeId = trace?.active_phase_id ?? null;

  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set());
  // Null until the user clicks a span. A stale pin (from a previous run) simply
  // fails the findNode lookup and falls back to the active span.
  const [pinnedId, setPinnedId] = useState<string | null>(null);

  const rows = useMemo(() => {
    const out: Row[] = [];
    flattenRows(phases as TraceNode[], 0, collapsed, out);
    return out;
  }, [phases, collapsed]);

  const runStart = trace?.run_started_ms ?? null;
  const total =
    trace?.total_duration_ms ??
    (trace?.run_started_ms != null && trace?.run_ended_ms != null
      ? trace.run_ended_ms - trace.run_started_ms
      : null);

  const lastPhaseId = phases.length ? phases[phases.length - 1].id : null;
  const pinnedNode = useMemo(
    () => (pinnedId ? findNode(phases as TraceNode[], pinnedId) : null),
    [phases, pinnedId],
  );
  // Effective selection: the user's pinned span, else follow the active span.
  const selectedNode = useMemo(() => {
    if (pinnedNode) return pinnedNode;
    const fallback = activeId ?? lastPhaseId;
    return fallback ? findNode(phases as TraceNode[], fallback) : null;
  }, [pinnedNode, activeId, lastPhaseId, phases]);
  const selectedId = selectedNode?.id ?? null;

  // DOM-only side effect (no setState): keep the active span in view while live.
  useEffect(() => {
    if (!isLive || pinnedNode || !activeRowRef.current) return;
    activeRowRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [isLive, pinnedNode, activeId, rows]);

  const tokenSummary = trace?.token_usage;
  const totalTokens =
    tokenSummary?.total_tokens ??
    (tokenSummary?.prompt_tokens != null && tokenSummary?.completion_tokens != null
      ? tokenSummary.prompt_tokens + tokenSummary.completion_tokens
      : null) ??
    run?.token_usage ??
    null;
  const progress = trace ? traceProgress(phases) : 0;
  const totalDuration = fmtDuration(total);

  function handleSelect(id: string) {
    setPinnedId(id);
  }

  function handleToggle(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function collapseAll() {
    const ids = new Set<string>();
    collectContainerIds(phases as TraceNode[], ids);
    setCollapsed(ids);
  }

  function expandAll() {
    setCollapsed(new Set());
  }

  const allCollapsed = rows.every((r) => !r.hasChildren || collapsed.has(r.node.id));

  return (
    <div className="flex flex-col">
      <div className="border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-ink" strokeWidth={1.5} />
            <span className="text-xs font-semibold text-ink">Execution trace</span>
            {isLive && (
              <Badge variant="warning" className="gap-1 text-[10px]">
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                {run?.status === "waiting_approval" ? "awaiting you" : "running"}
              </Badge>
            )}
            {trace?.status === "failed" ? (
              <Badge variant="danger" className="gap-1 text-[10px]">
                <AlertTriangle className="h-2.5 w-2.5" />
                failed
              </Badge>
            ) : (
              trace?.error && (
                <Badge variant="danger" className="gap-1 text-[10px]">
                  <AlertTriangle className="h-2.5 w-2.5" />
                  step error
                </Badge>
              )
            )}
          </div>
          <div className="flex items-center gap-3">
            {totalDuration && (
              <span className="inline-flex items-center gap-1 font-mono text-[10px] text-mute">
                <Clock className="h-3 w-3" />
                {totalDuration}
              </span>
            )}
            {totalTokens != null && totalTokens > 0 && (
              <span
                className="inline-flex items-center gap-1 font-mono text-[10px] text-mute"
                title={
                  tokenSummary?.prompt_tokens != null && tokenSummary?.completion_tokens != null
                    ? `Input ${tokenSummary.prompt_tokens.toLocaleString()} · Output ${tokenSummary.completion_tokens.toLocaleString()}`
                    : undefined
                }
              >
                <Coins className="h-3 w-3" />
                {totalTokens.toLocaleString()} tok
              </span>
            )}
            <button
              type="button"
              onClick={allCollapsed ? expandAll : collapseAll}
              className="inline-flex items-center gap-1 rounded-[5px] px-1.5 py-0.5 text-[10px] font-medium text-mute transition-colors hover:bg-canvas-soft-2 hover:text-ink"
            >
              {allCollapsed ? (
                <>
                  <ChevronsUpDown className="h-3 w-3" /> Expand all
                </>
              ) : (
                <>
                  <ChevronsDownUp className="h-3 w-3" /> Collapse all
                </>
              )}
            </button>
          </div>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              trace?.status === "failed"
                ? "bg-red-500"
                : isLive
                  ? "animate-trace-progress bg-gradient-to-r from-warning-border via-ink to-warning-border bg-[length:200%_100%]"
                  : "bg-success-border",
            )}
            style={{ width: `${Math.max(isLive ? progress : 100, isLive ? 12 : 0)}%` }}
          />
        </div>
      </div>

      {trace?.error && (
        <div className="flex items-start gap-2 border-b border-danger-border/40 bg-danger-soft/50 px-4 py-2 text-[11px] text-danger-text">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0 break-words">{trace.error}</span>
        </div>
      )}

      {phases.length === 0 ? (
        <p className="p-4 text-xs text-mute">Waiting for execution trace…</p>
      ) : (
        <div className="flex flex-col lg:flex-row">
          <div className="max-h-[min(70vh,36rem)] overflow-y-auto p-2 lg:w-[52%] lg:border-r lg:border-hairline">
            {rows.map((row) => (
              <SpanRow
                key={row.node.id}
                row={row}
                selected={row.node.id === selectedId}
                collapsed={collapsed.has(row.node.id)}
                onSelect={handleSelect}
                onToggle={handleToggle}
                runStart={runStart}
                total={total}
                rowRef={row.node.id === activeId ? activeRowRef : undefined}
              />
            ))}
          </div>
          <div className="max-h-[min(70vh,36rem)] flex-1 overflow-y-auto border-t border-hairline lg:border-t-0">
            <TraceDetailPanel
              node={selectedNode}
              runStart={runStart}
              run={run}
              approving={approving}
              onApprove={onApprove}
              onReject={onReject}
            />
          </div>
        </div>
      )}

      <style>{`
        @keyframes trace-progress {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        .animate-trace-progress { animation: trace-progress 2s linear infinite; }
      `}</style>
    </div>
  );
}
