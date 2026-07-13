import {
  api,
  type AgentRun,
  type AgentStep,
  type AgentStreamHandlers,
} from "@/api";
import {
  type LiveTraceSpan,
  type LlmTraceEvent,
} from "@/components/agents/AgentRunPanel";

type AgentLiveCallbacks = {
  onLlmStart: (event: LlmTraceEvent) => void;
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

export function createAgentLlmEvent(): LlmTraceEvent {
  return {
    id: `llm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    kind: "llm",
    status: "running",
    name: "ChatOpenAI",
  };
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
    onLlmStart: () => {
      cb.onLlmStart(createAgentLlmEvent());
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
