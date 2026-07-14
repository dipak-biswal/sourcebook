import { useEffect, useMemo, useRef, type ReactNode } from "react";
import {
  Brain,
  CheckCircle2,
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
  toolDisplayName,
} from "@/components/agents/agent-utils";
import { AgentApprovalCard } from "@/components/agents/shared";
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

/** Text-only timeline row: icon on spine → branch → label. */
function TraceLabel({
  icon,
  label,
  detail,
  state,
  active,
  nodeId,
  activeRef,
  nested,
  isLast,
  trailing,
}: {
  icon: typeof Brain;
  label: string;
  detail?: string;
  state: "pending" | "running" | "done";
  active?: boolean;
  nodeId: string;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  nested?: boolean;
  isLast?: boolean;
  trailing?: ReactNode;
}) {
  const iconCol = nested ? NESTED_ICON_COL : MAIN_ICON_COL;
  const stubW = nested ? NESTED_BRANCH_STUB : BRANCH_STUB;
  const iconTop = nested ? 4 : 6;
  const iconSize = nested ? 28 : 36;
  const branchTop = iconTop + iconSize / 2;

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
            <div className="flex flex-wrap items-center gap-1.5">
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
            </div>
            {detail && (
              <p className="mt-0.5 line-clamp-2 text-[11px] text-mute">{detail}</p>
            )}
          </div>
        </div>
      </div>
      {trailing}
    </div>
  );
}

function ToolTraceLabel({
  tool,
  active,
  activeRef,
  isLast,
}: {
  tool: TraceToolNode;
  active?: boolean;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  isLast?: boolean;
}) {
  return (
    <TraceLabel
      nodeId={tool.id}
      activeRef={activeRef}
      active={active}
      nested
      isLast={isLast}
      icon={Wrench}
      label={toolDisplayName(tool.toolName)}
      detail={
        tool.state === "running"
          ? "Running…"
          : tool.resultStep
            ? "Complete"
            : undefined
      }
      state={tool.state}
    />
  );
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
                <TraceLabel
                  key={row.id}
                  nodeId={row.id}
                  icon={Target}
                  label="Input goal"
                  detail={row.goal}
                  state="done"
                  isLast={row.isLast}
                />
              );
            }

            if (row.kind === "turn" && row.turn) {
              const turnActive = activeId === row.id || row.turn.state === "running";
              return (
                <TraceLabel
                  key={row.id}
                  nodeId={row.id}
                  activeRef={turnActive ? activeRef : undefined}
                  active={turnActive}
                  icon={Brain}
                  label={`Agent · turn ${row.turnNumber}`}
                  detail={turnStatusLabel(row.turn)}
                  state={row.turn.state}
                  isLast={row.isLast}
                />
              );
            }

            if (row.kind === "tool" && row.tool) {
              return (
                <div key={row.id} className="pl-6">
                  <ToolTraceLabel
                    tool={row.tool}
                    active={activeId === row.id}
                    activeRef={activeId === row.id ? activeRef : undefined}
                    isLast={row.isLast}
                  />
                </div>
              );
            }

            if (row.kind === "hitl" && row.hitl) {
              const hitl = row.hitl;
              const hitlActive = hitl.state === "running" || activeId === hitl.id;
              return (
                <TraceLabel
                  key={row.id}
                  nodeId={row.id}
                  activeRef={hitlActive ? activeRef : undefined}
                  active={hitlActive}
                  icon={Shield}
                  label={
                    hitl.step?.tool_name === "generative_ui" || hitl.pending
                      ? "Human approval · View in UI?"
                      : "Human approval"
                  }
                  detail={
                    hitl.building
                      ? "Building visual summary…"
                      : hitl.pending
                        ? "Waiting for your decision"
                        : "Approved"
                  }
                  state={hitl.state}
                  isLast={row.isLast}
                  trailing={
                    hitl.pending && run?.pending_tool && onApprove && onReject ? (
                      <div className="ml-[calc(36px+12px)] mt-2 max-w-md">
                        <AgentApprovalCard
                          pendingTool={run.pending_tool}
                          approving={approving}
                          onApprove={onApprove}
                          onReject={onReject}
                          className="border-warning-border/60 bg-warning-soft/40"
                        />
                      </div>
                    ) : null
                  }
                />
              );
            }

            if (row.kind === "presentation" && row.presentation) {
              const pres = row.presentation;
              const presActive = pres.state === "running";
              return (
                <TraceLabel
                  key={row.id}
                  nodeId={row.id}
                  activeRef={presActive ? activeRef : undefined}
                  active={presActive}
                  icon={Sparkles}
                  label="Visual summary"
                  detail={
                    pres.state === "running"
                      ? "Generating…"
                      : pres.step
                        ? "Ready — see Visual summary tab"
                        : "Pending approval"
                  }
                  state={pres.state}
                  isLast={row.isLast}
                />
              );
            }

            if (row.kind === "synthesis" && row.synthesis) {
              return (
                <TraceLabel
                  key={row.id}
                  nodeId={row.id}
                  icon={CheckCircle2}
                  label="Answer synthesis"
                  detail="Final answer recovered"
                  state="done"
                  isLast={row.isLast}
                />
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