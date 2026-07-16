export type TraceState = "pending" | "running" | "done" | "error";

/** LangSmith-style span timing, derived server-side from step timestamps. */
export type TraceTiming = {
  started_ms?: number | null;
  ended_ms?: number | null;
  duration_ms?: number | null;
  error?: string | null;
};

export type TraceLlmRole =
  | "orchestrator_decision"
  | "orchestrator_response"
  | "orchestrator"
  | "embedded_planner"
  | "embedded_render"
  | "embedded";

export type TraceToolChild = TraceTiming & {
  id: string;
  type: "tool";
  label: string;
  tool_name: string;
  state: TraceState;
  input?: unknown;
  output?: unknown;
  has_embedded_llm?: boolean;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  children?: TraceChild[];
};

export type TraceLlmMessage = {
  role: string;
  content: string;
  tool_calls?: unknown[];
  tool_call_id?: string;
  name?: string;
};

export type TraceTokenUsage = {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
};

export type TraceLlmChild = TraceTiming & {
  id: string;
  type: "llm_response";
  label: string;
  state: TraceState;
  model?: string | null;
  llm_role?: TraceLlmRole | string | null;
  prompt?: TraceLlmMessage[] | null;
  output: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
};

export type TraceHitlEmbedChild = TraceTiming & {
  id: string;
  type: "hitl_embed";
  label: string;
  state: TraceState;
  pending?: boolean;
  building?: boolean;
  input?: unknown;
  output?: unknown;
};

export type TraceHandoffChild = TraceTiming & {
  id: string;
  type: "handoff";
  label: string;
  state: TraceState;
  output?: string;
};

export type TraceFinalAnswerChild = TraceTiming & {
  id: string;
  type: "final_answer";
  label: string;
  state: TraceState;
  output?: string;
};

export type TraceVisualStageChild = TraceTiming & {
  id: string;
  type: "visual_stage";
  label: string;
  stage?: string;
  state: TraceState;
  children: TraceChild[];
};

export type TraceChild =
  | TraceToolChild
  | TraceLlmChild
  | TraceHitlEmbedChild
  | TraceHandoffChild
  | TraceFinalAnswerChild
  | TraceVisualStageChild;

export type TraceGoalPhase = TraceTiming & {
  id: string;
  type: "goal";
  label: string;
  state: TraceState;
  goal: string;
};

export type TraceAgentTurnPhase = TraceTiming & {
  id: string;
  type: "agent_turn";
  turn: number;
  label: string;
  agent_label?: string | null;
  state: TraceState;
  children: TraceChild[];
  llm_turn_id?: string;
};

export type TraceHitlPhase = TraceTiming & {
  id: string;
  type: "hitl";
  label: string;
  state: TraceState;
  pending?: boolean;
  building?: boolean;
  input?: unknown;
  output?: unknown;
};

export type TraceAgentEvidence = {
  document_hits?: Array<{
    filename: string;
    snippet: string;
    score?: number | null;
    chunk_id?: string | null;
  }>;
  web_hits?: Array<{
    title: string;
    snippet: string;
    url?: string;
  }>;
};

export type TracePresentationPhase = TraceTiming & {
  id: string;
  type: "presentation";
  label: string;
  state: TraceState;
  model?: string | null;
  output?: unknown;
  prompt?: TraceLlmMessage[] | string | null;
  llm_output?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
  children?: TraceChild[];
  agent_evidence?: TraceAgentEvidence | null;
  block_count?: number;
  presentation_profile?: string | null;
};

export type TraceSynthesisPhase = TraceTiming & {
  id: string;
  type: "synthesis";
  label: string;
  state: TraceState;
  model?: string | null;
  prompt?: TraceLlmMessage[] | null;
  output?: string;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
};

export type TracePhase =
  | TraceGoalPhase
  | TraceAgentTurnPhase
  | TraceHitlPhase
  | TracePresentationPhase
  | TraceSynthesisPhase;

export type TraceTokenSummary = {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  total_tokens?: number | null;
};

export type ExecutionTrace = {
  goal: string;
  workspace_name?: string | null;
  phases: TracePhase[];
  active_phase_id: string | null;
  is_complete: boolean;
  status?: string | null;
  token_usage?: TraceTokenSummary | null;
  run_started_ms?: number | null;
  run_ended_ms?: number | null;
  total_duration_ms?: number | null;
  error?: string | null;
};