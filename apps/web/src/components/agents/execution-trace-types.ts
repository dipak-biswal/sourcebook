export type TraceState = "pending" | "running" | "done";

export type TraceLlmRole =
  | "orchestrator_decision"
  | "orchestrator_response"
  | "orchestrator"
  | "embedded_planner"
  | "embedded_render"
  | "embedded";

export type TraceToolChild = {
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

export type TraceLlmChild = {
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

export type TraceHitlEmbedChild = {
  id: string;
  type: "hitl_embed";
  label: string;
  state: TraceState;
  pending?: boolean;
  building?: boolean;
  input?: unknown;
  output?: unknown;
};

export type TraceHandoffStructured = {
  summary?: string;
  key_points_count?: number;
  key_points_preview?: string[];
  faq_count?: number;
  faq_preview?: Array<{ question?: string; answer?: string }>;
  sections_count?: number;
  themes?: string[];
};

export type TraceHandoffInput = {
  goal?: string;
  structured_content?: TraceHandoffStructured;
  planner_notes?: string;
};

export type TraceHandoffChild = {
  id: string;
  type: "handoff";
  label: string;
  state: TraceState;
  input?: TraceHandoffInput;
};

export type TraceChild =
  | TraceToolChild
  | TraceLlmChild
  | TraceHitlEmbedChild
  | TraceHandoffChild;

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
  agent_label?: string | null;
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

export type TracePresentationPhase = {
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

export type TraceSynthesisPhase = {
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
  token_usage?: TraceTokenSummary | null;
};