import { useQuery } from "@tanstack/react-query";
import {
  api,
  type AgentRun,
  type ChatMessage,
  type Conversation,
  type Document,
  type Note,
  type UsageSummary,
  type UserProfile,
  type Workspace,
} from "@/api";

export function useMe() {
  return useQuery<UserProfile>({
    queryKey: ["me"],
    queryFn: () => api.me(),
    staleTime: 60_000,
  });
}

export function useWorkspaces() {
  return useQuery<Workspace[]>({
    queryKey: ["workspaces"],
    queryFn: () => api.workspaces(),
  });
}

const INGEST_POLL_STATUSES = new Set(["processing", "queued", "chunked"]);

function documentsNeedPolling(docs: Document[] | undefined): boolean {
  if (!docs?.length) return false;
  return docs.some((d) => INGEST_POLL_STATUSES.has(d.status.toLowerCase()));
}

export function useDocuments(workspaceId: string | undefined) {
  return useQuery<Document[]>({
    queryKey: ["documents", workspaceId],
    queryFn: () => api.documents(workspaceId!),
    enabled: !!workspaceId,
    refetchInterval: (query) =>
      documentsNeedPolling(query.state.data) ? 3_000 : false,
  });
}

export function useConversations(workspaceId: string | undefined) {
  return useQuery<Conversation[]>({
    queryKey: ["conversations", workspaceId],
    queryFn: () => api.conversations(workspaceId!),
    enabled: !!workspaceId,
  });
}

export function useMessages(conversationId: string | undefined) {
  return useQuery<ChatMessage[]>({
    queryKey: ["messages", conversationId],
    queryFn: () => api.messages(conversationId!),
    enabled: !!conversationId,
  });
}

export function useAgentRuns(
  workspaceId: string | undefined,
  agentType?: "general" | "study_guide",
) {
  return useQuery<AgentRun[]>({
    queryKey: ["agentRuns", workspaceId, agentType ?? "all"],
    queryFn: () => api.agentRuns(workspaceId!, agentType),
    enabled: !!workspaceId,
  });
}

export function useAgentRun(runId: string | undefined) {
  return useQuery<AgentRun>({
    queryKey: ["agentRun", runId],
    queryFn: () => api.agentRun(runId!),
    enabled: !!runId,
  });
}

export function useNotes(workspaceId: string | undefined) {
  return useQuery<Note[]>({
    queryKey: ["notes", workspaceId],
    queryFn: () => api.notes(workspaceId!),
    enabled: !!workspaceId,
  });
}

export function useNote(noteId: string | undefined) {
  return useQuery<Note>({
    queryKey: ["note", noteId],
    queryFn: () => api.getNote(noteId!),
    enabled: !!noteId,
  });
}

export function useChatSuggestions(workspaceId: string | undefined) {
  return useQuery<string[]>({
    queryKey: ["chatSuggestions", workspaceId],
    queryFn: () => api.suggestQuestions(workspaceId!).then((r) => r.questions),
    enabled: !!workspaceId,
    staleTime: 300_000,
    retry: false,
  });
}

export function useUsageSummary() {
  return useQuery<UsageSummary>({
    queryKey: ["usageSummary"],
    queryFn: () => api.usageSummary(),
  });
}
