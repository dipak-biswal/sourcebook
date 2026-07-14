import { useCallback, useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type ChatMessage } from "@/api";
import { useToast } from "@/components/ui/toast";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { useAgentRuns, useConversations, useMessages, useWorkspaces } from "@/hooks/queries";
import { readLastWorkspaceId, writeLastWorkspaceId } from "@/lib/last-workspace";

function sortMessages(raw: ChatMessage[]): ChatMessage[] {
  if (!raw.length) return [];
  return [...raw].sort((a, b) => {
    const ta = new Date(a.created_at).getTime();
    const tb = new Date(b.created_at).getTime();
    if (ta !== tb) return ta - tb;
    if (a.role === "user" && b.role === "assistant") return -1;
    if (a.role === "assistant" && b.role === "user") return 1;
    return a.id.localeCompare(b.id);
  });
}

export function useChatSessions() {
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();

  const [overrideWorkspaceId, setOverrideWorkspaceId] = useState<string | null>(null);
  const [overrideConversationId, setOverrideConversationId] = useState<string | null>(null);
  const [overrideAgentRunId, setOverrideAgentRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const { data: workspaces = [], isLoading: loadingWs } = useWorkspaces();
  const workspaceId = useMemo(() => {
    if (
      overrideWorkspaceId &&
      workspaces.some((w) => w.id === overrideWorkspaceId)
    ) {
      return overrideWorkspaceId;
    }
    const saved = readLastWorkspaceId();
    if (saved && workspaces.some((w) => w.id === saved)) return saved;
    return workspaces[0]?.id ?? "";
  }, [overrideWorkspaceId, workspaces]);
  const { data: conversations = [], isLoading: loadingSessions } = useConversations(workspaceId);
  const conversationId = overrideConversationId ?? conversations[0]?.id ?? "";
  const {
    data: fetchedMessages = [],
    isFetching: loadingMessages,
  } = useMessages(conversationId || undefined);
  const { data: agentRuns = [], isLoading: loadingAgentRuns } =
    useAgentRuns(workspaceId);
  const agentRunId = overrideAgentRunId ?? "";

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      return;
    }
    const cached = queryClient.getQueryData<ChatMessage[]>(["messages", conversationId]);
    const source =
      fetchedMessages.length > 0
        ? fetchedMessages
        : cached && cached.length > 0
          ? cached
          : null;
    if (source) {
      setMessages(sortMessages(source));
    } else if (!loadingMessages) {
      setMessages([]);
    }
  }, [conversationId, fetchedMessages, loadingMessages, queryClient]);

  const setWorkspaceId = useCallback((id: string) => {
    setOverrideWorkspaceId(id || null);
    if (id) writeLastWorkspaceId(id);
    setOverrideConversationId(null);
    setMessages([]);
  }, []);

  const setConversationId = useCallback((id: string) => {
    setOverrideConversationId(id || null);
    const cached = id
      ? queryClient.getQueryData<ChatMessage[]>(["messages", id])
      : undefined;
    if (cached?.length) {
      setMessages(sortMessages(cached));
    }
  }, [queryClient]);

  const setAgentRunId = useCallback((id: string) => {
    setOverrideAgentRunId(id || null);
  }, []);

  async function onNewChat() {
    if (!workspaceId) return;
    setError(null);
    try {
      const conv = await api.createConversation(workspaceId, "New chat");
      setConversationId(conv.id);
      await queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      setMessages([]);
    } catch (err) {
      setError(formatError(err));
    }
  }

  function onNewAgent() {
    setAgentRunId("");
    setError(null);
  }

  async function onSelectSession(id: string) {
    setConversationId(id);
    setError(null);
  }

  async function onSelectAgentRun(id: string) {
    setError(null);
    setAgentRunId(id);
  }

  async function onDeleteSession(id: string) {
    if (
      !(await confirmAction(
        "Delete this chat session?",
        "Messages in this session will be removed.",
      ))
    ) {
      return;
    }
    setError(null);
    try {
      await api.deleteConversation(id);
      const nextPrefer =
        conversationId === id
          ? conversations.find((c) => c.id !== id)?.id
          : conversationId;
      if (nextPrefer) setConversationId(nextPrefer);
      else setMessages([]);
      await queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      success("Session deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  const loadingMessageHistory =
    !!conversationId && loadingMessages && messages.length === 0;

  return {
    workspaces,
    workspaceId,
    setWorkspaceId,
    conversations,
    conversationId,
    setConversationId,
    agentRuns,
    agentRunId,
    setAgentRunId,
    messages,
    setMessages,
    error,
    setError,
    loadingWs,
    loadingSessions,
    loadingAgentRuns,
    loadingMessageHistory,
    onNewChat,
    onNewAgent,
    onSelectSession,
    onSelectAgentRun,
    onDeleteSession,
  };
}