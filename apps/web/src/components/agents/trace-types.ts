import type { AgentStep } from "@/api";

/** Live LLM span while the model is thinking. */
export type LlmTraceEvent = {
  id: string;
  turnId?: string;
  kind: "llm";
  status: "running" | "done";
  streamContent?: string;
  duration_ms?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  has_tool_calls?: boolean;
  name?: string;
};

export type LiveTraceSpan =
  | { kind: "llm"; event: LlmTraceEvent }
  | { kind: "step"; step: AgentStep };

export type TraceNodeState = "pending" | "running" | "done";

export type TraceToolNode = {
  id: string;
  toolName: string;
  callStep?: AgentStep;
  resultStep?: AgentStep;
  state: TraceNodeState;
};

export type TraceAgentTurn = {
  id: string;
  turnId?: string;
  llm?: LlmTraceEvent;
  tools: TraceToolNode[];
  thoughtStep?: AgentStep;
  state: TraceNodeState;
};

export type TraceTreeItem =
  | { id: string; kind: "goal"; goal: string; state: TraceNodeState }
  | { id: string; kind: "turn"; turn: TraceAgentTurn }
  | { id: string; kind: "hitl"; step?: AgentStep; pending: boolean; building?: boolean; state: TraceNodeState }
  | { id: string; kind: "presentation"; step?: AgentStep; state: TraceNodeState }
  | { id: string; kind: "synthesis"; step: AgentStep; state: TraceNodeState };

export type ActiveToolCall = {
  tool_name: string;
  call_id?: string;
  startTime: number;
};