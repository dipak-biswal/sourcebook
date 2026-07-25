import { useQuery } from "@tanstack/react-query";
import {
  api,
  type AgentConnectorsOverview,
  type AgentRun,
  type ChatMessage,
  type Conversation,
  type Document,
  type Note,
  type UsageSummary,
  type UserProfile,
  type VisualPipelineSummary,
  type Workspace,
} from "@/api";
import { useIsAuthenticated } from "@/hooks/useAuth";

export function useMe() {
  const authed = useIsAuthenticated();
  return useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    staleTime: 60_000,
    enabled: authed,
  });
}

export function useWorkspaces() {
  const authed = useIsAuthenticated();
  return useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: () => api.workspaces(),
    enabled: authed,
  });
}

const INGEST_POLL_STATUSES = new Set(["processing", "queued", "chunked"]);

function documentsNeedPolling(docs: Document[] | undefined): boolean {
  if (!docs?.length) return false;
  return docs.some((d) => INGEST_POLL_STATUSES.has(d.status.toLowerCase()));
}

export function useDocuments(workspaceId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<Document[]>({
    queryKey: ["documents", workspaceId],
    queryFn: () => api.documents(workspaceId!),
    enabled: authed && !!workspaceId,
    refetchInterval: (query) =>
      documentsNeedPolling(query.state.data) ? 3_000 : false,
  });
}

export function useConversations(workspaceId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<Conversation[]>({
    queryKey: ["conversations", workspaceId],
    queryFn: () => api.conversations(workspaceId!),
    enabled: authed && !!workspaceId,
  });
}

export function useMessages(conversationId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<ChatMessage[]>({
    queryKey: ["messages", conversationId],
    queryFn: () => api.messages(conversationId!),
    enabled: authed && !!conversationId,
  });
}

export function useAgentRuns(workspaceId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<AgentRun[]>({
    queryKey: ["agentRuns", workspaceId],
    queryFn: () => api.agentRuns(workspaceId!),
    enabled: authed && !!workspaceId,
  });
}

export function useAgentConnectors() {
  const authed = useIsAuthenticated();
  return useQuery<AgentConnectorsOverview>({
    queryKey: ["agentConnectors"],
    queryFn: () => api.agentConnectors(),
    enabled: authed,
    staleTime: 60_000,
  });
}

export function useAgentRun(runId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<AgentRun>({
    queryKey: ["agentRun", runId],
    queryFn: () => api.agentRun(runId!),
    enabled: authed && !!runId,
  });
}

export function useNotes(workspaceId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<Note[]>({
    queryKey: ["notes", workspaceId],
    queryFn: () => api.notes(workspaceId!),
    enabled: authed && !!workspaceId,
  });
}

export function useNote(noteId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<Note>({
    queryKey: ["note", noteId],
    queryFn: () => api.getNote(noteId!),
    enabled: authed && !!noteId,
  });
}

export function useChatSuggestions(workspaceId: string | undefined) {
  const authed = useIsAuthenticated();
  return useQuery<string[]>({
    queryKey: ["chatSuggestions", workspaceId],
    queryFn: () => api.suggestQuestions(workspaceId!).then((r) => r.questions),
    enabled: authed && !!workspaceId,
    staleTime: 300_000,
    retry: false,
  });
}

export function useUsageSummary() {
  const authed = useIsAuthenticated();
  return useQuery<UsageSummary>({
    queryKey: ["usageSummary"],
    queryFn: () => api.usageSummary(),
    enabled: authed,
  });
}

export function useVisualPipelineSummary(workspaceId?: string) {
  const authed = useIsAuthenticated();
  return useQuery<VisualPipelineSummary>({
    queryKey: ["visualPipelineSummary", workspaceId ?? "all"],
    queryFn: () => api.visualPipelineSummary(workspaceId),
    enabled: authed,
  });
}
