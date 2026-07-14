import { useEffect, useMemo, useRef, useState } from "react";
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
  TraceToolNode,
} from "@/components/agents/trace-types";
import { cn } from "@/lib/utils";

function Connector({ active, done }: { active?: boolean; done?: boolean }) {
  return (
    <div
      className={cn(
        "absolute left-[15px] top-8 bottom-0 w-0.5 origin-top",
        active
          ? "animate-trace-flow bg-gradient-to-b from-warning-border via-ink/40 to-hairline"
          : done
            ? "bg-ink/25"
            : "bg-hairline",
      )}
    />
  );
}

function NodeShell({
  icon: Icon,
  title,
  subtitle,
  state,
  active,
  open,
  onToggle,
  children,
  nodeId,
  activeRef,
}: {
  icon: typeof Brain;
  title: string;
  subtitle?: string;
  state: "pending" | "running" | "done";
  active?: boolean;
  open: boolean;
  onToggle: () => void;
  children?: React.ReactNode;
  nodeId: string;
  activeRef?: React.RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      ref={active ? activeRef : undefined}
      data-trace-id={nodeId}
      className={cn(
        "relative pl-9",
        active && "scroll-mt-4",
      )}
    >
      <Connector active={active && state === "running"} done={state === "done"} />
      <div
        className={cn(
          "absolute left-0 top-1 flex h-8 w-8 items-center justify-center rounded-full border-2 bg-canvas transition-all",
          state === "running" && "border-warning-border shadow-[0_0_0_4px_rgba(234,179,8,0.12)]",
          state === "done" && "border-success-border",
          state === "pending" && "border-hairline",
          active && state === "running" && "animate-trace-pulse",
        )}
      >
        {state === "running" ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin text-warning-text" />
        ) : state === "done" ? (
          <Icon className="h-3.5 w-3.5 text-ink" strokeWidth={2} />
        ) : (
          <Icon className="h-3.5 w-3.5 text-mute" strokeWidth={2} />
        )}
      </div>

      <div
        className={cn(
          "mb-3 overflow-hidden rounded-[8px] border bg-canvas transition-shadow",
          active && state === "running"
            ? "border-warning-border/80 ring-1 ring-warning-border/30"
            : "border-hairline",
        )}
      >
        <button
          type="button"
          onClick={onToggle}
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
              <span className="text-xs font-semibold text-ink">{title}</span>
              {state === "running" && (
                <Badge variant="warning" className="gap-1 text-[10px]">
                  <span className="relative flex h-1.5 w-1.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-warning" />
                  </span>
                  live
                </Badge>
              )}
              {state === "done" && (
                <Badge variant="success" className="text-[10px]">
                  done
                </Badge>
              )}
            </div>
            {subtitle && (
              <p className="mt-0.5 line-clamp-2 text-[11px] text-mute">{subtitle}</p>
            )}
          </div>
        </button>
        {open && children && (
          <div className="border-t border-hairline bg-canvas-soft/60 px-3 py-2.5">
            {children}
          </div>
        )}
      </div>
    </div>
  );
}

function ToolTraceNode({
  tool,
  active,
  activeRef,
  defaultOpen,
}: {
  tool: TraceToolNode;
  active?: boolean;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  defaultOpen: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const web =
    tool.toolName === "web_search" && tool.resultStep
      ? parseWebSearchOutput(tool.resultStep.output)
      : null;

  return (
    <NodeShell
      nodeId={tool.id}
      activeRef={activeRef}
      active={active}
      open={open}
      onToggle={() => setOpen((v) => !v)}
      icon={Wrench}
      title={toolDisplayName(tool.toolName)}
      subtitle={
        tool.state === "running"
          ? "Running tool…"
          : tool.resultStep
            ? "Input → output"
            : "Waiting for result"
      }
      state={tool.state}
    >
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
    </NodeShell>
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

function stepText(step?: AgentStep): string {
  if (!step?.output) return "";
  if (typeof step.output === "string") return step.output;
  return "";
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
  const [goalOpen, setGoalOpen] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

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
    if (!activeId) return;
    setExpanded((prev) => ({ ...prev, [activeId]: true, goal: true }));
    for (const item of tree) {
      if (item.kind === "turn" && item.id === activeId) {
        setExpanded((prev) => ({ ...prev, [item.id]: true }));
      }
      if (item.kind === "turn") {
        for (const t of item.turn.tools) {
          if (t.id === activeId) {
            setExpanded((prev) => ({
              ...prev,
              [item.id]: true,
              [t.id]: true,
            }));
          }
        }
      }
    }
  }, [activeId, tree]);

  useEffect(() => {
    if (!running || !activeRef.current) return;
    activeRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [running, activeId, tree]);

  function isOpen(id: string, defaultOpen = false): boolean {
    if (expanded[id] !== undefined) return expanded[id]!;
    return defaultOpen;
  }

  function toggle(id: string) {
    setExpanded((prev) => ({ ...prev, [id]: !isOpen(id, true) }));
  }

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
        <p className="mt-1.5 text-[10px] text-mute">
          {running
            ? "Following the agent turn-by-turn — active step highlighted below."
            : "Full run history: goal → agent turns → tools → approvals → visual summary."}
        </p>
      </div>

      <div ref={scrollRef} className="max-h-[min(70vh,36rem)] overflow-y-auto p-4">
        {tree.map((item, index, arr) => {
          const isLast = index === arr.length - 1;
          const turnNumber =
            item.kind === "turn"
              ? arr.slice(0, index + 1).filter((n) => n.kind === "turn").length
              : 0;

          if (item.kind === "goal") {
            return (
              <NodeShell
                key={item.id}
                nodeId={item.id}
                icon={Target}
                title="Input goal"
                subtitle={item.goal}
                state="done"
                open={goalOpen}
                onToggle={() => setGoalOpen((v) => !v)}
              >
                <p className="text-xs leading-relaxed text-body">{item.goal}</p>
              </NodeShell>
            );
          }

          if (item.kind === "turn") {
            const turn = item.turn;
            const turnActive = activeId === item.id || turn.state === "running";
            const llmContent =
              turn.llm?.streamContent ||
              stepText(turn.thoughtStep) ||
              "";
            const turnOpen = isOpen(item.id, turnActive || isLast);

            return (
              <div key={item.id}>
                <NodeShell
                  nodeId={item.id}
                  activeRef={turnActive ? activeRef : undefined}
                  active={turnActive}
                  icon={Brain}
                  title={`Agent · turn ${turnNumber}`}
                  subtitle={
                    turn.llm?.status === "running"
                      ? "Streaming response…"
                      : turn.llm?.has_tool_calls
                        ? "Planning tool calls"
                        : turn.thoughtStep?.type === "final"
                          ? "Final answer"
                          : "Reasoning"
                  }
                  state={turn.state}
                  open={turnOpen}
                  onToggle={() => toggle(item.id)}
                >
                  <div className="space-y-3">
                    <div>
                      <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                        LLM output
                      </div>
                      <LlmStreamBody
                        content={llmContent}
                        running={turn.llm?.status === "running"}
                      />
                    </div>
                    {turn.tools.length > 0 && (
                      <div className="space-y-0">
                        <div className="mb-2 text-[10px] font-bold uppercase tracking-wide text-mute">
                          Tool calls
                        </div>
                        {turn.tools.map((tool) => (
                          <ToolTraceNode
                            key={tool.id}
                            tool={tool}
                            active={activeId === tool.id}
                            activeRef={activeId === tool.id ? activeRef : undefined}
                            defaultOpen={
                              tool.state === "running" ||
                              activeId === tool.id ||
                              isLast
                            }
                          />
                        ))}
                      </div>
                    )}
                  </div>
                </NodeShell>
              </div>
            );
          }

          if (item.kind === "hitl") {
            const hitlActive = item.state === "running" || activeId === item.id;
            return (
              <NodeShell
                key={item.id}
                nodeId={item.id}
                activeRef={hitlActive ? activeRef : undefined}
                active={hitlActive}
                icon={Shield}
                title={
                  item.step?.tool_name === "generative_ui" || item.pending
                    ? "Human approval · View in UI?"
                    : "Human approval · write tool"
                }
                subtitle={
                  item.building
                    ? "Building visual summary…"
                    : item.pending
                      ? "Waiting for your decision"
                      : "Approved"
                }
                state={item.state}
                open={isOpen(item.id, hitlActive || item.pending || isLast)}
                onToggle={() => toggle(item.id)}
              >
                {item.pending && run?.pending_tool && onApprove && onReject ? (
                  <AgentApprovalCard
                    pendingTool={run.pending_tool}
                    approving={approving}
                    onApprove={onApprove}
                    onReject={onReject}
                    className="border-warning-border/60 bg-warning-soft/40"
                  />
                ) : item.step?.input ? (
                  <pre className="max-h-32 overflow-auto rounded border border-hairline bg-canvas p-2 text-[11px]">
                    {prettyJson(item.step.input)}
                  </pre>
                ) : null}
              </NodeShell>
            );
          }

          if (item.kind === "presentation") {
            const presActive = item.state === "running";
            return (
              <NodeShell
                key={item.id}
                nodeId={item.id}
                activeRef={presActive ? activeRef : undefined}
                active={presActive}
                icon={Sparkles}
                title="Visual summary"
                subtitle={
                  item.state === "running"
                    ? "Layout engine generating blocks…"
                    : item.step
                      ? "Generative UI ready"
                      : "Pending approval"
                }
                state={item.state}
                open={isOpen(item.id, presActive || !!item.step)}
                onToggle={() => toggle(item.id)}
              >
                {item.step?.output ? (
                  <p className="text-xs text-body">
                    Visual summary attached — open the{" "}
                    <strong className="text-ink">Visual summary</strong> tab.
                  </p>
                ) : presActive ? (
                  <div className="flex items-center gap-2 text-[11px] text-warning-text">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Building UI blocks from answer + evidence…
                  </div>
                ) : (
                  <p className="text-[11px] text-mute">Runs after you approve View in UI.</p>
                )}
              </NodeShell>
            );
          }

          if (item.kind === "synthesis") {
            return (
              <NodeShell
                key={item.id}
                nodeId={item.id}
                icon={CheckCircle2}
                title="Answer synthesis"
                subtitle="Recovered final answer from tool evidence"
                state="done"
                open={isOpen(item.id, false)}
                onToggle={() => toggle(item.id)}
              >
                <MarkdownContent content={stepText(item.step)} />
              </NodeShell>
            );
          }

          return null;
        })}
      </div>

      <style>{`
        @keyframes trace-flow {
          0% { opacity: 0.45; transform: scaleY(0.98); }
          50% { opacity: 1; transform: scaleY(1); }
          100% { opacity: 0.45; transform: scaleY(0.98); }
        }
        @keyframes trace-pulse {
          0%, 100% { box-shadow: 0 0 0 4px rgba(234, 179, 8, 0.1); }
          50% { box-shadow: 0 0 0 7px rgba(234, 179, 8, 0.18); }
        }
        @keyframes trace-progress {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        .animate-trace-flow { animation: trace-flow 1.6s ease-in-out infinite; }
        .animate-trace-pulse { animation: trace-pulse 1.8s ease-in-out infinite; }
        .animate-trace-progress { animation: trace-progress 2s linear infinite; }
      `}</style>
    </div>
  );
}