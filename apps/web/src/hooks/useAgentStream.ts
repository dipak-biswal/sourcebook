import {
  api,
  type AgentRun,
  type AgentStep,
  type AgentStreamHandlers,
} from "@/api";
import type {
  LiveTraceSpan,
  LlmTraceEvent,
} from "@/components/agents/trace-types";

type AgentLiveCallbacks = {
  onLlmStart: (event: LlmTraceEvent) => void;
  onLlmDelta?: (p: { turn_id?: string; delta: string }) => void;
  onLlmEnd: (p: {
    duration_ms?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    token_usage_so_far?: number;
    has_tool_calls?: boolean;
  }) => void;
  onStep: (step: AgentStep) => void;
  onTokenUsage: (usage: number) => void;
  onToolStart?: (p: {
    tool_name: string;
    tool_args?: Record<string, unknown>;
    call_id?: string;
  }) => void;
  onLoopWarning?: (p: { message: string }) => void;
};

export function createAgentLlmEvent(
  payload?: Record<string, unknown>,
): LlmTraceEvent {
  const turnId = payload?.turn_id as string | undefined;
  return {
    id: turnId ?? `llm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    turnId,
    kind: "llm",
    status: "running",
    name: (payload?.name as string) || "ChatOpenAI",
    streamContent: "",
  };
}

export function appendLlmStream(
  event: LlmTraceEvent,
  delta: string,
  turnId?: string,
): LlmTraceEvent {
  if (turnId && event.turnId && event.turnId !== turnId) return event;
  return {
    ...event,
    streamContent: `${event.streamContent ?? ""}${delta}`,
  };
}

export function patchRunningLlmWithDelta(
  trace: LiveTraceSpan[],
  delta: string,
  turnId?: string,
): LiveTraceSpan[] {
  return trace.map((node) => {
    if (node.kind !== "llm" || node.event.status !== "running") return node;
    if (turnId && node.event.turnId && node.event.turnId !== turnId) return node;
    return {
      kind: "llm" as const,
      event: appendLlmStream(node.event, delta, turnId),
    };
  });
}

export function makeLlmEndPatch(p: {
  duration_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  has_tool_calls?: boolean;
}): Partial<LlmTraceEvent> {
  return {
    duration_ms: p.duration_ms,
    prompt_tokens: p.prompt_tokens,
    completion_tokens: p.completion_tokens,
    total_tokens: p.total_tokens,
    has_tool_calls: p.has_tool_calls,
  };
}

export function upsertSteps(steps: AgentStep[], step: AgentStep): AgentStep[] {
  const next = [...steps];
  const i = next.findIndex((s) => s.id === step.id);
  if (i >= 0) next[i] = step;
  else next.push(step);
  return next;
}

export function upsertTraceStep(
  trace: LiveTraceSpan[],
  step: AgentStep,
): LiveTraceSpan[] {
  const already = trace.some(
    (n) => n.kind === "step" && n.step.id === step.id,
  );
  if (already) {
    return trace.map((n) =>
      n.kind === "step" && n.step.id === step.id
        ? { kind: "step" as const, step }
        : n,
    );
  }
  return [...trace, { kind: "step" as const, step }];
}

export function makeAgentStreamHandlers(
  cb: AgentLiveCallbacks,
  onDoneExtra?: (run: AgentRun) => void,
  includeStatus = true,
): AgentStreamHandlers {
  const base: AgentStreamHandlers = {
    onLlmStart: (payload) => {
      cb.onLlmStart(createAgentLlmEvent(payload));
    },
    onLlmDelta: (p) => {
      cb.onLlmDelta?.(p);
    },
    onLlmEnd: (p) => {
      cb.onLlmEnd(p);
      if (p.token_usage_so_far != null) {
        cb.onTokenUsage(p.token_usage_so_far);
      }
    },
    onStep: (step) => {
      cb.onStep(step);
    },
    onToolStart: (p) => {
      cb.onToolStart?.(p);
    },
    onLoopWarning: (p) => {
      cb.onLoopWarning?.(p);
    },
    onDone: (final) => {
      onDoneExtra?.(final);
    },
    onError: () => {},
  };
  if (includeStatus) {
    base.onStatus = (p) => {
      if (p.token_usage != null) cb.onTokenUsage(p.token_usage);
    };
  }
  return base;
}

export { api };
export type { AgentLiveCallbacks };
