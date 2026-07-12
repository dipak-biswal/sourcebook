import type {
  AgentRun,
  AgentStep,
  ChatMessage,
} from "@/api";
import type {
  LiveTraceSpan,
  LlmTraceEvent,
} from "@/components/agents/AgentRunPanel";

export type ChatMode = "chat" | "agent";

export type AgentThreadItem = {
  id: string;
  role: "user" | "assistant";
  content: string;
  run?: AgentRun | null;
  pending?: boolean;
  goal?: string;
  liveSteps?: AgentStep[];
  liveTokenUsage?: number | null;
  liveLlmEvents?: LlmTraceEvent[];
  liveTrace?: LiveTraceSpan[];
};

export type ThreadItem =
  | { kind: "chat"; message: ChatMessage }
  | { kind: "agent"; item: AgentThreadItem };
