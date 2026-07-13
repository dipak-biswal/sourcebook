export type DashboardPageContextValue = {
  workspaces: Workspace[];
  workspaceId: string;
  documentsCount: number;
  readyDocumentsCount: number;
  conversationsCount: number;
  agentRunsCount: number;
  notesCount: number;
  loading: boolean;
  userEmail: string;
  recent: RecentItem[];
  onLogout: () => void;
};

type Workspace = { id: string; name: string; role: string };

type RecentItem = {
  id: string;
  type: "document" | "conversation" | "agent_run" | "note";
  label: string;
  subtitle: string;
  href: string;
  created_at: string;
};
