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

  useEffect(() => {
    if (!running || !activeRef.current) return;
    activeRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [running, activeId, tree]);

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

  const rows = useMemo((): FlatRow[] => {
    const flat: FlatRow[] = [];
    let turnCount = 0;

    for (const item of tree) {
      if (item.kind === "goal") {
        flat.push({ id: item.id, kind: "goal", goal: item.goal, isLast: false });
        continue;
      }
      if (item.kind === "turn") {
        turnCount += 1;
        flat.push({
          id: item.id,
          kind: "turn",
          turnNumber: turnCount,
          turn: item.turn,
          isLast: false,
        });
        for (const tool of item.turn.tools) {
          flat.push({ id: tool.id, kind: "tool", tool, nested: true, isLast: false });
        }
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
  }, [tree]);

  return (
    <div className="flex flex-col">
      <div className="border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-ink" strokeWidth={1.5} />
            <span className="text-xs font-semibold text-ink">Execution trace</span>
            {running && (
              <Badge variant="warning" className="gap-1 text-[10px]">
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                running
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
              running
                ? "animate-trace-progress bg-gradient-to-r from-warning-border via-ink to-warning-border bg-[length:200%_100%]"
                : "bg-success-border",
            )}
            style={{ width: `${Math.max(running ? progress : 100, running ? 12 : 0)}%` }}
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
              const llmContent =
                turn.llm?.streamContent || stepText(turn.thoughtStep) || "";
              const status = turnStatusLabel(turn);

              return (
                <ExpandableTraceRow
                  key={row.id}
                  nodeId={row.id}
                  activeRef={turnActive ? activeRef : undefined}
                  active={turnActive}
                  defaultOpen={turnActive}
                  icon={Brain}
                  label={`Agent · turn ${row.turnNumber}`}
                  state={turn.state}
                  isLast={row.isLast}
                >
                  {status && (
                    <p className="mb-2 text-[11px] text-mute">{status}</p>
                  )}
                  <LlmStreamBody
                    content={llmContent}
                    running={turn.llm?.status === "running"}
                  />
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
                    defaultOpen={toolActive}
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
                  defaultOpen={hitlActive || hitl.pending}
                  icon={Shield}
                  label={
                    hitl.step?.tool_name === "generative_ui" || hitl.pending
                      ? "Human approval · View in UI?"
                      : "Human approval"
                  }
                  state={hitl.state}
                  isLast={row.isLast}
                >
                  {hitl.pending && run?.pending_tool && onApprove && onReject ? (
                    <AgentApprovalCard
                      pendingTool={run.pending_tool}
                      approving={approving}
                      onApprove={onApprove}
                      onReject={onReject}
                      className="border-warning-border/60 bg-warning-soft/40"
                    />
                  ) : hitl.building ? (
                    <div className="flex items-center gap-2 text-[11px] text-warning-text">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Building visual summary…
                    </div>
                  ) : hitl.step?.input ? (
                    <pre className="max-h-32 overflow-auto rounded border border-hairline bg-canvas p-2 font-mono text-[11px]">
                      {prettyJson(hitl.step.input)}
                    </pre>
                  ) : (
                    <p className="text-mute">Approved</p>
                  )}
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
                  defaultOpen={presActive}
                  icon={Sparkles}
                  label="Visual summary"
                  state={pres.state}
                  isLast={row.isLast}
                >
                  {pres.state === "running" ? (
                    <div className="flex items-center gap-2 text-[11px] text-warning-text">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Building UI blocks from answer + evidence…
                    </div>
                  ) : pres.step?.output ? (
                    <p>
                      Visual summary attached — open the{" "}
                      <strong className="text-ink">Visual summary</strong> tab.
                    </p>
                  ) : (
                    <p className="text-mute">Runs after you approve View in UI.</p>
                  )}
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