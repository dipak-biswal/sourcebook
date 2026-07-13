import type {
  AgentRun,
  AgentStep,
  ChatMessage,
  Conversation,
  Workspace,
} from "@/api";
import type {
  LiveTraceSpan,
  LlmTraceEvent,
} from "@/components/agents/AgentRunPanel";
import type { ChatSessionsPanelProps } from "@/components/chat/ChatSessionsPanel";

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

export type ChatPageContextValue = {
  mode: ChatMode;
  input: string;
  sessionsOpen: boolean;
  sending: boolean;
  error: string | null;
  workspaces: Workspace[];
  workspaceId: string;
  conversations: Conversation[];
  conversationId: string;
  agentRuns: AgentRun[];
  agentRunId: string;
  messages: ChatMessage[];
  agentThread: AgentThreadItem[];
  approving: boolean;
  savingNote: boolean;
  loadingWs: boolean;
  loadingSessions: boolean;
  loadingAgentRuns: boolean;
  active: Conversation | undefined;
  activeAgentRun: AgentRun | null;
  empty: boolean;
  title: string;
  subtitle: string;
  showDelete: boolean;
  showClear: boolean;
  loading: boolean;
  sessionPanelProps: Omit<ChatSessionsPanelProps, "onAfterNavigate"> & { onAfterNavigate: () => void };
  onInputChange: (v: string) => void;
  onSend: (e: React.FormEvent) => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
  onClearSession: () => void;
  onToggleSessions: () => void;
  onSessionsClose: () => void;
  onSwitchMode: (mode: ChatMode) => void;
  onApprove: (approve: boolean) => void;
  onSaveLearningNote: (title: string, body: string) => void;
  onLogout: () => void;
};
