import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Coins,
  GitBranch,
  Loader2,
  Shield,
  Sparkles,
  Target,
  Wrench,
} from "lucide-react";
import type { AgentRun, AgentStep } from "@/api";
import {
  isPresentationPending,
  parseWebSearchOutput,
  prettyJson,
  toolDisplayName,
} from "@/components/agents/agent-utils";
import { isGenerativeUI } from "@/components/agents/generative-ui";
import { AgentApprovalCard } from "@/components/agents/shared";
import { WebSearchResults } from "@/components/agents/WebSearchResults";
import { MarkdownContent } from "@/components/chat/MarkdownContent";
import { Badge } from "@/components/ui/badge";
import {
  buildAgentTraceTree,
  findActiveTraceId,
  traceProgress,
} from "@/components/agents/trace-tree";
import type {
  ActiveToolCall,
  LiveTraceSpan,
  TraceAgentTurn,
  TraceTreeItem,
  TraceToolNode,
} from "@/components/agents/trace-types";
import { cn } from "@/lib/utils";

const MAIN_ICON_COL = 36;
const NESTED_ICON_COL = 28;
const BRANCH_STUB = 12;
const NESTED_BRANCH_STUB = 10;

function TraceIcon({
  icon: Icon,
  state,
  active,
  nested,
}: {
  icon: typeof Brain;
  state: "pending" | "running" | "done";
  active?: boolean;
  nested?: boolean;
}) {
  const size = nested ? "h-7 w-7" : "h-9 w-9";
  const iconSize = nested ? "h-3 w-3" : "h-4 w-4";
  return (
    <div
      className={cn(
        "relative z-10 flex shrink-0 items-center justify-center rounded-full border-2 bg-canvas transition-all",
        size,
        state === "running" && "border-warning-border shadow-[0_0_0_4px_rgba(234,179,8,0.14)]",
        state === "done" && "border-ink/30",
        state === "pending" && "border-hairline",
        active && state === "running" && "animate-trace-pulse",
      )}
    >
      {state === "running" ? (
        <Loader2 className={cn(iconSize, "animate-spin text-warning-text")} />
      ) : (
        <Icon className={cn(iconSize, "text-ink")} strokeWidth={2} />
      )}
    </div>
  );
}

/** Timeline row with chevron expand/collapse for step details. */
function ExpandableTraceRow({
  icon,
  label,
  state,
  active,
  nodeId,
  activeRef,
  nested,
  isLast,
  defaultOpen = false,
  children,
}: {
  icon: typeof Brain;
  label: string;
  state: "pending" | "running" | "done";
  active?: boolean;
  nodeId: string;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  nested?: boolean;
  isLast?: boolean;
  defaultOpen?: boolean;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const iconCol = nested ? NESTED_ICON_COL : MAIN_ICON_COL;
  const stubW = nested ? NESTED_BRANCH_STUB : BRANCH_STUB;
  const iconTop = nested ? 4 : 6;
  const iconSize = nested ? 28 : 36;
  const branchTop = iconTop + iconSize / 2;
  const expandable = children != null;

  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);

  return (
    <div
      ref={active ? activeRef : undefined}
      data-trace-id={nodeId}
      className={cn(
        "relative min-w-0",
        nested ? "pb-1" : "pb-1.5",
        active && "scroll-mt-4",
      )}
    >
      <div className="relative flex min-w-0">
        <div
          className="relative z-10 flex shrink-0 justify-center"
          style={{ width: iconCol, paddingTop: iconTop }}
        >
          {!isLast && (
            <div
              className="pointer-events-none absolute left-1/2 w-0.5 -translate-x-1/2 bg-ink/25"
              style={{ top: branchTop, bottom: 0 }}
            />
          )}
          <TraceIcon icon={icon} state={state} active={active} nested={nested} />
        </div>

        <div className="flex min-w-0 flex-1">
          <div className="relative shrink-0" style={{ width: stubW }}>
            <div
              className="absolute left-0 right-0 h-0.5 bg-ink/25"
              style={{ top: branchTop }}
            />
          </div>

          <div
            className="min-w-0 flex-1"
            style={{ paddingTop: branchTop - (nested ? 7 : 8) }}
          >
            {expandable ? (
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                className="flex w-full items-start gap-1.5 rounded-[6px] px-1 py-0.5 text-left hover:bg-canvas-soft"
              >
                <span className="mt-0.5 shrink-0 text-mute">
                  {open ? (
                    <ChevronDown className="h-3.5 w-3.5" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-center gap-1.5">
                    <span
                      className={cn(
                        "font-medium text-ink",
                        nested ? "text-[11px]" : "text-xs",
                        active && state === "running" && "text-warning-text",
                      )}
                    >
                      {label}
                    </span>
                    {state === "running" && (
                      <Badge variant="warning" className="gap-1 text-[10px]">
                        <span className="relative flex h-1.5 w-1.5">
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
                          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-warning" />
                        </span>
                        live
                      </Badge>
                    )}
                    {state === "done" && !nested && (
                      <Badge variant="success" className="text-[10px]">
                        done
                      </Badge>
                    )}
                  </span>
                  {open && (
                    <div className="mt-2 text-xs leading-relaxed text-body">
                      {children}
                    </div>
                  )}
                </span>
              </button>
            ) : (
              <div className="flex flex-wrap items-center gap-1.5 px-1 py-0.5">
                <span
                  className={cn(
                    "font-medium text-ink",
                    nested ? "text-[11px]" : "text-xs",
                  )}
                >
                  {label}
                </span>
                {state === "done" && !nested && (
                  <Badge variant="success" className="text-[10px]">
                    done
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function LlmStreamBody({
  content,
  running,
}: {
  content: string;
  running?: boolean;
}) {
  if (!content && !running) {
    return (
      <p className="text-[11px] italic text-mute">
        Model chose tool calls without prose.
      </p>
    );
  }
  return (
    <div className="rounded-[6px] border border-hairline bg-canvas p-2.5">
      <div className="prose prose-sm max-w-none text-xs text-body">
        <MarkdownContent content={content || (running ? " " : "")} />
      </div>
      {running && (
        <span className="mt-1 inline-block h-3 w-0.5 animate-pulse bg-ink" />
      )}
    </div>
  );
}

function ToolTraceBody({ tool }: { tool: TraceToolNode }) {
  const web =
    tool.toolName === "web_search" && tool.resultStep
      ? parseWebSearchOutput(tool.resultStep.output)
      : null;

  return (
    <div className="space-y-2">
      {(tool.callStep?.input != null || tool.resultStep?.input != null) && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
            Input
          </div>
          <pre className="max-h-36 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
            {prettyJson(tool.callStep?.input ?? tool.resultStep?.input)}
          </pre>
        </div>
      )}
      {tool.resultStep?.output != null && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
            Output
          </div>
          {web ? (
            <WebSearchResults data={web} compact />
          ) : (
            <pre className="max-h-44 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
              {prettyJson(tool.resultStep.output)}
            </pre>
          )}
        </div>
      )}
      {tool.state === "running" && !tool.resultStep && (
        <div className="flex items-center gap-2 text-[11px] text-warning-text">
          <Loader2 className="h-3 w-3 animate-spin" />
          Executing…
        </div>
      )}
    </div>
  );
}

function stepText(step?: AgentStep): string {
  if (!step?.output) return "";
  if (typeof step.output === "string") return step.output;
  return "";
}

function turnStatusLabel(turn: TraceAgentTurn): string | undefined {
  if (turn.llm?.status === "running") return "Streaming…";
  if (turn.llm?.has_tool_calls) return "Calling tools";
  if (turn.thoughtStep?.type === "final") return "Final answer";
  return undefined;
}

/** LLM text for the response row — skips pre-tool planning when tools ran first. */
function turnResponseContent(turn: TraceAgentTurn): string {
  if (turn.thoughtStep?.type === "final") {
    return stepText(turn.thoughtStep);
  }
  if (turn.tools.length === 0) {
    return turn.llm?.streamContent || stepText(turn.thoughtStep) || "";
  }
  if (turn.thoughtStep?.type === "thought") {
    return turn.llm?.streamContent || "";
  }
  return turn.llm?.streamContent || stepText(turn.thoughtStep) || "";
}

type FlatRow =
  | { id: string; kind: "goal"; isLast: boolean; goal: string }
  | { id: string; kind: "turn"; isLast: boolean; turnNumber: number; turn: TraceAgentTurn }
  | { id: string; kind: "tool"; isLast: boolean; tool: TraceToolNode; nested: true }
  | { id: string; kind: "hitl"; isLast: boolean; hitl: Extract<TraceTreeItem, { kind: "hitl" }> }
  | {
      id: string;
      kind: "presentation";
      isLast: boolean;
      presentation: Extract<TraceTreeItem, { kind: "presentation" }>;
    }
  | { id: string; kind: "synthesis"; isLast: boolean; synthesis: Extract<TraceTreeItem, { kind: "synthesis" }> };

/** During a live run, reveal steps sequentially as each finishes. */
function filterRowsForLive(rows: FlatRow[]): FlatRow[] {
  const visible: FlatRow[] = [];

  for (const row of rows) {
    if (row.kind === "tool") {
      if (row.tool.state === "pending" && !row.tool.callStep) break;
      visible.push(row);
      if (row.tool.state !== "done") break;
      continue;
    }

    if (row.kind === "turn") {
      const tools = row.turn.tools;
      const toolsReady =
        tools.length === 0 || tools.every((t) => t.state === "done");
      if (!toolsReady) break;
      visible.push(row);
      if (row.turn.state !== "done") break;
      continue;
    }

    visible.push(row);

    if (row.kind === "hitl" && row.hitl.pending && !row.hitl.building) break;
    if (row.kind === "presentation" && row.presentation.state === "pending") break;
    if (row.kind === "presentation" && row.presentation.state !== "done") break;
  }

  if (!visible.length) return visible;
  return visible.map((row, i) => ({
    ...row,
    isLast: i === visible.length - 1,
  }));
}

function buildFlatRows(tree: TraceTreeItem[]): FlatRow[] {
  const flat: FlatRow[] = [];
  let turnCount = 0;

  for (const item of tree) {
    if (item.kind === "goal") {
      flat.push({ id: item.id, kind: "goal", goal: item.goal, isLast: false });
      continue;
    }
    if (item.kind === "turn") {
      turnCount += 1;
      for (const tool of item.turn.tools) {
        flat.push({ id: tool.id, kind: "tool", tool, nested: true, isLast: false });
      }
      flat.push({
        id: item.id,
        kind: "turn",
        turnNumber: turnCount,
        turn: item.turn,
        isLast: false,
      });
      continue;
    }
    if (item.kind === "hitl") {
      flat.push({ id: item.id, kind: "hitl", hitl: item, isLast: false });
      continue;
    }
    if (item.kind === "presentation") {
      flat.push({ id: item.id, kind: "presentation", presentation: item, isLast: false });
      continue;
    }
    if (item.kind === "synthesis") {
      flat.push({ id: item.id, kind: "synthesis", synthesis: item, isLast: false });
    }
  }

  if (flat.length > 0) {
    flat[flat.length - 1] = { ...flat[flat.length - 1]!, isLast: true };
  }
  return flat;
}

function approvalOutput(
  step?: AgentStep,
): { status?: string; kind?: string } | null {
  if (!step?.output || typeof step.output !== "object") return null;
  return step.output as { status?: string; kind?: string };
}

function presentationTitle(
  run: AgentRun | null | undefined,
  tree: TraceTreeItem[],
): string | undefined {
  const fromRun = run?.presentation_spec;
  if (isGenerativeUI(fromRun)) return fromRun.title;
  for (const item of tree) {
    if (item.kind === "presentation" && isGenerativeUI(item.step?.output)) {
      return item.step.output.title;
    }
  }
  return undefined;
}

function HitlTraceBody({
  hitl,
  run,
  presentationTitle: presTitle,
  approving,
  onApprove,
  onReject,
}: {
  hitl: Extract<TraceTreeItem, { kind: "hitl" }>;
  run: AgentRun | null | undefined;
  presentationTitle?: string;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const output = approvalOutput(hitl.step);

  if (hitl.pending && run?.pending_tool && onApprove && onReject) {
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

  if (hitl.building && output?.status !== "approved") {
    return (
      <div className="flex items-center gap-2 text-[11px] text-warning-text">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building visual summary…
      </div>
    );
  }

  if (output?.status === "approved") {
    return (
      <div className="space-y-1.5">
        <p className="font-medium text-ink">Approved — visual summary generated</p>
        {presTitle && (
          <p className="text-mute">
            Title: <span className="text-body">{presTitle}</span>
          </p>
        )}
        <p className="text-mute">Open the Visual summary tab to view the full layout.</p>
      </div>
    );
  }

  if (output?.status === "rejected") {
    return (
      <p className="text-body">
        Rejected — answer kept as text only (no visual summary).
      </p>
    );
  }

  if (output?.status === "waiting_approval") {
    return <p className="text-mute">Waiting for your decision…</p>;
  }

  if (hitl.step?.input) {
    return (
      <pre className="max-h-32 overflow-auto rounded border border-hairline bg-canvas p-2 font-mono text-[11px]">
        {prettyJson(hitl.step.input)}
      </pre>
    );
  }

  return <p className="text-mute">Completed</p>;
}

function PresentationTraceBody({
  pres,
  presTitle,
}: {
  pres: Extract<TraceTreeItem, { kind: "presentation" }>;
  presTitle?: string;
}) {
  if (pres.state === "running") {
    return (
      <div className="flex items-center gap-2 text-[11px] text-warning-text">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building UI blocks from answer + evidence…
      </div>
    );
  }

  if (pres.step?.output && isGenerativeUI(pres.step.output)) {
    const payload = pres.step.output;
    return (
      <div className="space-y-1.5">
        <p className="font-medium text-ink">{payload.title}</p>
        {payload.plain_summary && (
          <p className="line-clamp-4 text-mute">{payload.plain_summary}</p>
        )}
        {payload.blocks?.length != null && (
          <p className="text-mute">
            {payload.blocks.length} block{payload.blocks.length === 1 ? "" : "s"} ·{" "}
            {payload.presentation_profile?.replace(/_/g, " ") ?? "layout"}
          </p>
        )}
        <p className="text-mute">Open the Visual summary tab for the full view.</p>
      </div>
    );
  }

  if (presTitle) {
    return (
      <p>
        <span className="font-medium text-ink">{presTitle}</span>
        {" — "}
        open the <strong className="text-ink">Visual summary</strong> tab.
      </p>
    );
  }

  return <p className="text-mute">Runs after you approve View in UI.</p>;
}

export function AgentTraceTree({
  run,
  goal,
  liveSteps,
  liveTrace,
  liveTokenUsage,
  running,
  activeToolCalls,
  approving,
  onApprove,
  onReject,
}: {
  run: AgentRun | null | undefined;
  goal?: string | null;
  liveSteps?: AgentStep[];
  liveTrace?: LiveTraceSpan[];
  liveTokenUsage?: number | null;
  running?: boolean;
  activeToolCalls?: ActiveToolCall[];
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const activeRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const mergedSteps = useMemo(() => {
    const fromRun = run?.steps ?? [];
    const live = liveSteps ?? [];
    const map = new Map<string, AgentStep>();
    for (const s of fromRun) map.set(s.id, s);
    for (const s of live) map.set(s.id, s);
    return [...map.values()].sort((a, b) => a.step_index - b.step_index);
  }, [run?.steps, liveSteps]);

  const displayGoal = goal || run?.goal || "";
  const presentationPending =
    run?.status === "waiting_approval" &&
    isPresentationPending(run.pending_tool);

  const tree = useMemo(
    () =>
      buildAgentTraceTree({
        goal: displayGoal,
        steps: mergedSteps,
        liveTrace,
        running,
        runningToolNames: activeToolCalls,
        pendingTool: run?.pending_tool,
        approving,
        presentationPending,
      }),
    [
      displayGoal,
      mergedSteps,
      liveTrace,
      running,
      activeToolCalls,
      run?.pending_tool,
      approving,
      presentationPending,
    ],
  );

  const activeId = findActiveTraceId(tree);
  const progress = traceProgress(tree);
  const tokens = liveTokenUsage ?? run?.token_usage ?? null;
  const visualSummaryTitle = presentationTitle(run, tree);
  const runComplete =
    run?.status === "completed" ||
    run?.status === "cancelled" ||
    run?.status === "failed";
  const isLive =
    !runComplete &&
    (running || approving || run?.status === "waiting_approval");

  useEffect(() => {
    if (!running || !activeRef.current) return;
    activeRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [running, activeId, tree]);

  const rows = useMemo((): FlatRow[] => {
    const flat = buildFlatRows(tree);
    return isLive ? filterRowsForLive(flat) : flat;
  }, [tree, isLive]);

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
          </div>
          {tokens != null && (
            <span className="inline-flex items-center gap-1 font-mono text-[10px] text-mute">
              <Coins className="h-3 w-3" />
              {tokens.toLocaleString()} tok
            </span>
          )}
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              isLive
                ? "animate-trace-progress bg-gradient-to-r from-warning-border via-ink to-warning-border bg-[length:200%_100%]"
                : "bg-success-border",
            )}
            style={{ width: `${Math.max(isLive ? progress : 100, isLive ? 12 : 0)}%` }}
          />
        </div>
      </div>

      <div ref={scrollRef} className="max-h-[min(70vh,36rem)] overflow-x-auto overflow-y-auto p-4">
        <div className="relative min-w-0">
          {rows.map((row) => {
            if (row.kind === "goal") {
              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  icon={Target}
                  label="Input goal"
                  state="done"
                  isLast={row.isLast}
                  defaultOpen={runComplete}
                >
                  {row.goal ? (
                    <p className="text-body">{row.goal}</p>
                  ) : (
                    <p className="italic text-mute">No goal text</p>
                  )}
                </ExpandableTraceRow>
              );
            }

            if (row.kind === "turn" && row.turn) {
              const turn = row.turn;
              const turnActive = activeId === row.id || turn.state === "running";
              const hasTools = turn.tools.length > 0;
              const llmContent = turnResponseContent(turn);
              const status = turnStatusLabel(turn);
              const turnLabel = hasTools
                ? `Agent · turn ${row.turnNumber} · response`
                : `Agent · turn ${row.turnNumber}`;

              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  activeRef={turnActive ? activeRef : undefined}
                  active={turnActive}
                  defaultOpen={runComplete || turnActive}
                  icon={Brain}
                  label={turnLabel}
                  state={turn.state}
                  isLast={row.isLast}
                >
                  {status && (
                    <p className="mb-2 text-[11px] text-mute">{status}</p>
                  )}
                  <div>
                    {hasTools && (
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                        LLM response
                      </div>
                    )}
                    <LlmStreamBody
                      content={llmContent}
                      running={turn.llm?.status === "running"}
                    />
                  </div>
                </ExpandableTraceRow>
              );
            }

            if (row.kind === "tool" && row.tool) {
              const toolActive = activeId === row.id;
              return (
                <div key={row.id} className="pl-6">
                  <ExpandableTraceRow
                    nodeId={row.id}
                    activeRef={toolActive ? activeRef : undefined}
                    active={toolActive}
                    defaultOpen={runComplete || toolActive}
                    nested
                    icon={Wrench}
                    label={toolDisplayName(row.tool.toolName)}
                    state={row.tool.state}
                    isLast={row.isLast}
                  >
                    <ToolTraceBody tool={row.tool} />
                  </ExpandableTraceRow>
                </div>
              );
            }

            if (row.kind === "hitl" && row.hitl) {
              const hitl = row.hitl;
              const hitlActive = hitl.state === "running" || activeId === hitl.id;
              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  activeRef={hitlActive ? activeRef : undefined}
                  active={hitlActive}
                  defaultOpen={runComplete || hitlActive || hitl.pending}
                  icon={Shield}
                  label={
                    hitl.step?.tool_name === "generative_ui" || hitl.pending
                      ? "Human approval · View in UI?"
                      : "Human approval"
                  }
                  state={hitl.state}
                  isLast={row.isLast}
                >
                  <HitlTraceBody
                    hitl={hitl}
                    run={run}
                    presentationTitle={visualSummaryTitle}
                    approving={approving}
                    onApprove={onApprove}
                    onReject={onReject}
                  />
                </ExpandableTraceRow>
              );
            }

            if (row.kind === "presentation" && row.presentation) {
              const pres = row.presentation;
              const presActive = pres.state === "running";
              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  activeRef={presActive ? activeRef : undefined}
                  active={presActive}
                  defaultOpen={runComplete || presActive}
                  icon={Sparkles}
                  label="Visual summary"
                  state={pres.state}
                  isLast={row.isLast}
                >
                  <PresentationTraceBody
                    pres={pres}
                    presTitle={visualSummaryTitle}
                  />
                </ExpandableTraceRow>
              );
            }

            if (row.kind === "synthesis" && row.synthesis) {
              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  icon={CheckCircle2}
                  label="Answer synthesis"
                  state="done"
                  isLast={row.isLast}
                  defaultOpen={runComplete}
                >
                  <MarkdownContent content={stepText(row.synthesis.step)} />
                </ExpandableTraceRow>
              );
            }

            return null;
          })}
        </div>
      </div>

      <style>{`
        @keyframes trace-pulse {
          0%, 100% { box-shadow: 0 0 0 4px rgba(234, 179, 8, 0.1); }
          50% { box-shadow: 0 0 0 7px rgba(234, 179, 8, 0.18); }
        }
        @keyframes trace-progress {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        .animate-trace-pulse { animation: trace-pulse 1.8s ease-in-out infinite; }
        .animate-trace-progress { animation: trace-progress 2s linear infinite; }
      `}</style>
    </div>
  );
}