import type { AgentStep, AgentRun } from "@/api";
import type { LiveTraceSpan, LlmTraceEvent } from "@/components/agents/AgentRunPanel";

export type AgentPageContextValue = {
  workspaces: Workspace[];
  workspaceId: string;
  runs: AgentRun[];
  notes: NoteSummary[];
  selected: AgentRun | null;
  selectedId: string;
  goal: string;
  error: string | null;
  running: boolean;
  approving: boolean;
  sidebarOpen: boolean;
  savingNote: boolean;
  loading: boolean;
  liveGoal: string | null;
  liveSteps: AgentStep[];
  liveTokenUsage: number | null;
  liveLlmEvents: LlmTraceEvent[];
  liveTrace: LiveTraceSpan[];
  activeToolCalls: { tool_name: string; startTime: number }[];
  loopWarning: string | null;
  onChangeWorkspace: (id: string) => void;
  onSelectRun: (id: string) => void;
  onGoalChange: (v: string) => void;
  onRun: (e: React.SubmitEvent<HTMLFormElement>) => void;
  onApprove: (approve: boolean) => void;
  onDeleteNote: (id: string) => void;
  onSaveLearningNote: (title: string, body: string) => void;
  onRefresh: () => void;
  onToggleSidebar: () => void;
  onSidebarClose: () => void;
  onLogout: () => void;
};

type Workspace = { id: string; name: string };
export type NoteSummary = { id: string; title: string; body: string | null; created_at: string };
