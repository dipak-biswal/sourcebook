export type TraceState = "pending" | "running" | "done";

export type TraceToolChild = {
  id: string;
  type: "tool";
  label: string;
  tool_name: string;
  state: TraceState;
  input?: unknown;
  output?: unknown;
};

export type TraceLlmMessage = {
  role: string;
  content: string;
  tool_calls?: unknown[];
  tool_call_id?: string;
  name?: string;
};

export type TraceLlmChild = {
  id: string;
  type: "llm_response";
  label: string;
  state: TraceState;
  prompt?: TraceLlmMessage[] | null;
  output: string;
};

export type TraceChild = TraceToolChild | TraceLlmChild;

export type TraceGoalPhase = {
  id: string;
  type: "goal";
  label: string;
  state: TraceState;
  goal: string;
};

export type TraceAgentTurnPhase = {
  id: string;
  type: "agent_turn";
  turn: number;
  label: string;
  state: TraceState;
  children: TraceChild[];
  llm_turn_id?: string;
};

export type TraceHitlPhase = {
  id: string;
  type: "hitl";
  label: string;
  state: TraceState;
  pending?: boolean;
  building?: boolean;
  input?: unknown;
  output?: unknown;
};

export type TracePresentationPhase = {
  id: string;
  type: "presentation";
  label: string;
  state: TraceState;
  output?: unknown;
};

export type TraceSynthesisPhase = {
  id: string;
  type: "synthesis";
  label: string;
  state: TraceState;
  content?: string;
};

export type TracePhase =
  | TraceGoalPhase
  | TraceAgentTurnPhase
  | TraceHitlPhase
  | TracePresentationPhase
  | TraceSynthesisPhase;

export type ExecutionTrace = {
  goal: string;
  phases: TracePhase[];
  active_phase_id: string | null;
  is_complete: boolean;
};