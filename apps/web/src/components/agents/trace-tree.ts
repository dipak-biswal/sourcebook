import type { AgentStep } from "@/api";
import { isPresentationPending } from "@/components/agents/agent-utils";
import { isGenerativeUI } from "@/components/agents/generative-ui";
import type {
  ActiveToolCall,
  LiveTraceSpan,
  LlmTraceEvent,
  TraceAgentTurn,
  TraceNodeState,
  TraceToolNode,
  TraceTreeItem,
} from "@/components/agents/trace-types";

function openTool(
  toolName: string,
  callStep?: AgentStep,
  runningNames?: Set<string>,
): TraceToolNode {
  const running = runningNames?.has(toolName) && !callStep;
  return {
    id: callStep?.id ?? `tool-${toolName}-${callStep?.step_index ?? "pending"}`,
    toolName,
    callStep,
    state: running ? "running" : callStep ? "running" : "pending",
  };
}

function attachToolResult(tools: TraceToolNode[], step: AgentStep): TraceToolNode[] {
  const name = step.tool_name ?? "";
  const next = [...tools];
  let idx = -1;
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].toolName === name && !next[i].resultStep) {
      idx = i;
      break;
    }
  }
  if (idx >= 0) {
    next[idx] = {
      ...next[idx],
      resultStep: step,
      state: "done",
    };
    return next;
  }
  next.push({
    id: step.id,
    toolName: name,
    resultStep: step,
    state: "done",
  });
  return next;
}

function finishTurn(
  turn: TraceAgentTurn,
  thoughtStep?: AgentStep,
  llmDone?: boolean,
): TraceAgentTurn {
  const tools = turn.tools.map((t) =>
    t.resultStep ? { ...t, state: "done" as TraceNodeState } : t,
  );
  return {
    ...turn,
    tools,
    thoughtStep: thoughtStep ?? turn.thoughtStep,
    state:
      llmDone && tools.every((t) => t.state === "done")
        ? "done"
        : turn.state === "running"
          ? turn.state
          : "done",
  };
}

const PRESENTATION_TOOL = "generative_ui";

function isPresentationApproval(step: AgentStep): boolean {
  return step.type === "approval" && step.tool_name === PRESENTATION_TOOL;
}

function approvalStatus(step: AgentStep): string | undefined {
  if (!step.output || typeof step.output !== "object") return undefined;
  return (step.output as { status?: string }).status;
}

function pushPresentationHitl(
  tail: TraceTreeItem[],
  approvalSteps: AgentStep[],
): void {
  if (!approvalSteps.length) return;

  const last = approvalSteps[approvalSteps.length - 1]!;
  const approved = approvalSteps.some((s) => approvalStatus(s) === "approved");
  const rejected = approvalSteps.some((s) => approvalStatus(s) === "rejected");
  const waiting = !approved && !rejected;

  const hitlItem: TraceTreeItem = {
    id: `hitl-${last.id}`,
    kind: "hitl",
    step: last,
    pending: waiting,
    building: false,
    state: waiting ? "running" : "done",
  };

  const presIdx = tail.findIndex((t) => t.kind === "presentation");
  if (presIdx >= 0) {
    tail.splice(presIdx, 0, hitlItem);
  } else {
    tail.push(hitlItem);
  }
}

function buildTurnsFromSteps(
  steps: AgentStep[],
  runningToolNames?: Set<string>,
): { turns: TraceAgentTurn[]; tail: TraceTreeItem[] } {
  const turns: TraceAgentTurn[] = [];
  const tail: TraceTreeItem[] = [];
  const presentationApprovals: AgentStep[] = [];
  let current: TraceAgentTurn | null = null;
  let turnIndex = 0;

  function startTurn() {
    turnIndex += 1;
    current = {
      id: `turn-${turnIndex}`,
      tools: [],
      state: "done",
    };
  }

  for (const step of steps) {
    if (step.type === "tool_call") {
      if (!current) startTurn();
      current!.tools.push(
        openTool(step.tool_name ?? "tool", step, runningToolNames),
      );
      continue;
    }
    if (step.type === "tool_result") {
      if (!current) startTurn();
      current!.tools = attachToolResult(current!.tools, step);
      continue;
    }
    if (step.type === "thought") {
      if (!current) startTurn();
      const awaitingToolResults = current!.tools.some((t) => !t.resultStep);
      if (awaitingToolResults) {
        current = { ...current!, thoughtStep: step };
        continue;
      }
      current = finishTurn(current!, step, true);
      turns.push(current);
      current = null;
      continue;
    }
    if (step.type === "final") {
      if (!current) startTurn();
      current = finishTurn(current!, step, true);
      turns.push(current);
      current = null;
      continue;
    }
    if (step.type === "approval") {
      if (current) {
        turns.push(finishTurn(current, undefined, true));
        current = null;
      }
      if (isPresentationApproval(step)) {
        presentationApprovals.push(step);
      } else {
        const waiting = approvalStatus(step) === "waiting_approval";
        tail.push({
          id: step.id,
          kind: "hitl",
          step,
          pending: waiting,
          state: waiting ? "running" : "done",
          building: false,
        });
      }
      continue;
    }
    if (step.type === "presentation" || isGenerativeUI(step.output)) {
      const idx = tail.findIndex(
        (t) => t.kind === "presentation" && t.state !== "done",
      );
      const item: TraceTreeItem = {
        id: step.id,
        kind: "presentation",
        step,
        state: "done",
      };
      if (idx >= 0) tail[idx] = item;
      else tail.push(item);
      continue;
    }
    if (step.type === "synthesis") {
      tail.push({ id: step.id, kind: "synthesis", step, state: "done" });
    }
  }

  if (current) {
    turns.push(
      finishTurn(
        current,
        undefined,
        !runningToolNames || runningToolNames.size === 0,
      ),
    );
  }

  pushPresentationHitl(tail, presentationApprovals);

  return { turns, tail };
}

function turnFromLlmAndSteps(
  llm: LlmTraceEvent,
  steps: AgentStep[],
  runningToolNames?: Set<string>,
): TraceAgentTurn {
  const { turns: parsed } = buildTurnsFromSteps(steps, runningToolNames);
  const base = parsed[0];
  if (base) {
    return {
      ...base,
      id: llm.id,
      turnId: llm.turnId,
      llm,
      state:
        llm.status === "running" || base.state === "running"
          ? "running"
          : "done",
    };
  }
  return {
    id: llm.id,
    turnId: llm.turnId,
    llm,
    tools: [],
    state: llm.status === "running" ? "running" : "done",
  };
}

function mergeLiveLlmIntoTurns(
  liveTrace: LiveTraceSpan[],
  runningToolNames?: Set<string>,
): TraceAgentTurn[] {
  const turns: TraceAgentTurn[] = [];
  let currentLlm: LlmTraceEvent | null = null;
  let stepBuf: AgentStep[] = [];

  function flushTurn() {
    if (!currentLlm) return;
    turns.push(turnFromLlmAndSteps(currentLlm, stepBuf, runningToolNames));
    stepBuf = [];
    currentLlm = null;
  }

  for (const node of liveTrace) {
    if (node.kind === "llm") {
      flushTurn();
      currentLlm = node.event;
    } else {
      stepBuf.push(node.step);
    }
  }
  flushTurn();
  return turns;
}

export function buildAgentTraceTree(params: {
  goal: string;
  steps: AgentStep[];
  liveTrace?: LiveTraceSpan[];
  running?: boolean;
  runningToolNames?: ActiveToolCall[];
  pendingTool?: { name?: string; kind?: string } | null;
  approving?: boolean;
  presentationPending?: boolean;
}): TraceTreeItem[] {
  const {
    goal,
    steps,
    liveTrace,
    running,
    runningToolNames = [],
    pendingTool,
    approving,
    presentationPending,
  } = params;

  const activeTools = new Set(
    runningToolNames.map((t) => t.tool_name).filter(Boolean),
  );

  const sorted = [...steps].sort((a, b) => a.step_index - b.step_index);
  const items: TraceTreeItem[] = [
    {
      id: "goal",
      kind: "goal",
      goal,
      state: running ? "done" : "done",
    },
  ];

  let turns: TraceAgentTurn[] = [];
  let tail: TraceTreeItem[] = [];

  if (liveTrace?.length) {
    turns = mergeLiveLlmIntoTurns(liveTrace, activeTools);
    const stepIdsInTrace = new Set(
      liveTrace
        .filter((n): n is Extract<LiveTraceSpan, { kind: "step" }> => n.kind === "step")
        .map((n) => n.step.id),
    );
    const orphanSteps = sorted.filter((s) => !stepIdsInTrace.has(s.id));
    const extra = buildTurnsFromSteps(orphanSteps, activeTools);
    turns.push(...extra.turns);
    tail = extra.tail;
  } else {
    const built = buildTurnsFromSteps(sorted, activeTools);
    turns = built.turns;
    tail = built.tail;
    if (running && turns.length) {
      turns[turns.length - 1]!.state = "running";
    }
  }

  for (const turn of turns) {
    items.push({ id: turn.id, kind: "turn", turn });
  }

  const hasPendingHitl = tail.some((t) => t.kind === "hitl" && t.pending);
  if (
    presentationPending &&
    pendingTool &&
    isPresentationPending(pendingTool) &&
    !hasPendingHitl
  ) {
    tail.push({
      id: "hitl-pending",
      kind: "hitl",
      pending: true,
      building: approving,
      state: "running",
    });
  } else if (presentationPending && pendingTool && !hasPendingHitl) {
    tail.push({
      id: "hitl-pending",
      kind: "hitl",
      pending: true,
      state: "running",
    });
  }

  if (
    approving &&
    presentationPending &&
    !tail.some((t) => t.kind === "presentation")
  ) {
    tail.push({
      id: "presentation-pending",
      kind: "presentation",
      state: "running",
    });
  }

  for (const t of tail) {
    if (t.kind === "hitl" && approving && presentationPending && t.pending) {
      items.push({ ...t, building: true, state: "running" });
    } else if (
      t.kind === "presentation" &&
      approving &&
      presentationPending &&
      t.state !== "done"
    ) {
      items.push({ ...t, state: "running" });
    } else {
      items.push(t);
    }
  }

  if (running && turns.length === 0 && !tail.length) {
    items.push({
      id: "turn-boot",
      kind: "turn",
      turn: {
        id: "turn-boot",
        tools: [],
        state: "running",
        llm: {
          id: "llm-boot",
          kind: "llm",
          status: "running",
          name: "ChatOpenAI",
          streamContent: "",
        },
      },
    });
  }

  return items;
}

export function isTraceItemDone(item: TraceTreeItem): boolean {
  if (item.kind === "goal") return true;
  if (item.kind === "turn") {
    return (
      item.turn.state === "done" &&
      item.turn.tools.every((t) => t.state === "done")
    );
  }
  if (item.kind === "hitl") return item.state === "done" && !item.pending;
  if (item.kind === "presentation") return item.state === "done";
  if (item.kind === "synthesis") return true;
  return true;
}

export function findActiveTraceId(items: TraceTreeItem[]): string | null {
  for (let i = items.length - 1; i >= 0; i -= 1) {
    const item = items[i]!;
    if (item.kind === "turn" && item.turn.state === "running") return item.id;
    if (item.kind === "hitl" && item.state === "running") return item.id;
    if (item.kind === "presentation" && item.state === "running") return item.id;
    if (item.kind === "turn") {
      const runningTool = item.turn.tools.find((t) => t.state === "running");
      if (runningTool) return runningTool.id;
      if (item.turn.llm?.status === "running") return item.id;
    }
  }
  if (items.some((i) => i.kind === "turn")) return items[items.length - 1]!.id;
  return items[0]?.id ?? null;
}

export function traceProgress(items: TraceTreeItem[]): number {
  const nodes = items.filter((i) => i.kind !== "goal");
  if (!nodes.length) return items.length ? 8 : 0;
  const done = nodes.filter((i) => {
    if (i.kind === "turn") return i.turn.state === "done";
    return i.state === "done";
  }).length;
  const running = nodes.some((i) => {
    if (i.kind === "turn") return i.turn.state === "running";
    return i.state === "running";
  });
  const base = Math.round((done / nodes.length) * 100);
  return running ? Math.min(base + 6, 99) : base;
}