import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type ChatMessage } from "@/api";
import { useToast } from "@/components/ui/toast";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { useAgentRuns, useConversations, useMessages, useWorkspaces } from "@/hooks/queries";

export function useChatSessions() {
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();

  const [workspaceId, setWorkspaceId] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [agentRunId, setAgentRunId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const { data: workspaces = [], isLoading: loadingWs } = useWorkspaces();
  const { data: conversations = [], isLoading: loadingSessions } = useConversations(workspaceId);
  const { data: rawMessages = [] } = useMessages(conversationId);
  const { data: agentRuns = [], isLoading: loadingAgentRuns } = useAgentRuns(workspaceId);

  useEffect(() => {
    if (!workspaces.length || workspaceId) return;
    setWorkspaceId(workspaces[0].id);
  }, [workspaces, workspaceId]);

  useEffect(() => {
    if (!workspaceId) return;
    if (conversations.length && !conversationId) {
      setConversationId(conversations[0].id);
    }
    if (agentRuns.length && !agentRunId) {
      setAgentRunId(agentRuns[0].id);
    }
  }, [workspaceId, conversations, agentRuns, conversationId, agentRunId]);

  useEffect(() => {
    if (!rawMessages.length) {
      setMessages([]);
      return;
    }
    const sorted = [...rawMessages].sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      if (ta !== tb) return ta - tb;
      if (a.role === "user" && b.role === "assistant") return -1;
      if (a.role === "assistant" && b.role === "user") return 1;
      return a.id.localeCompare(b.id);
    });
    setMessages(sorted);
  }, [rawMessages]);

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
      await queryClient.invalidateQueries({ queryKey: ["conversations", workspaceId] });
      success("Session deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

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
    onNewChat,
    onNewAgent,
    onSelectSession,
    onSelectAgentRun,
    onDeleteSession,
  };
}
