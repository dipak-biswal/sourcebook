import { useEffect, useRef, useState, type ReactNode, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useChatSessions } from "./hooks/useChatSessions";
import { useChatMessages } from "./hooks/useChatMessages";
import { useAgentThread } from "./hooks/useAgentThread";
import type { ChatMode, ChatPageContextValue } from "@/types/chat";
import { formatDate } from "@/lib/utils";
import { ChatPageContext } from "./chat-page-context";

const MODE_KEY = "sourcebook_chat_mode";

function readMode(): ChatMode {
  try {
    const v = localStorage.getItem(MODE_KEY);
    if (v === "agent" || v === "chat") return v;
  } catch {
    /* ignore */
  }
  return "chat";
}

export function ChatPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);
  useDocumentTitle("Chat");

  const [mode, setMode] = useState<ChatMode>(readMode);
  const [input, setInput] = useState("");
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [sending, setSending] = useState(false);

  const setModePersist = (m: ChatMode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* ignore */
    }
  };

  const sessions = useChatSessions();
  const chatMessages = useChatMessages(
    sessions.workspaceId,
    sessions.conversationId,
    sessions.setConversationId,
    sessions.setError,
    sessions.setMessages,
    setInput,
  );
  const agent = useAgentThread(
    sessions.workspaceId,
    sessions.setAgentRunId,
    sessions.setError,
    setInput,
    bottomRef,
    setModePersist,
  );

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sessions.messages, agent.agentThread, sending]);

  async function onSend(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending || !sessions.workspaceId) return;

    sessions.setError(null);
    setInput("");

    if (mode === "agent") {
      setSending(true);
      try {
        await agent.onSendAgent(text);
      } finally {
        setSending(false);
      }
      return;
    }

    setSending(true);
    try {
      await chatMessages.onSendChat(text);
    } finally {
      setSending(false);
    }
  }

  async function onSelectAgentRun(id: string) {
    sessions.setAgentRunId(id);
    sessions.setError(null);
    try {
      const run = sessions.agentRuns.find((r) => r.id === id);
      const detail = (run?.steps?.length ? run : await api.agentRun(id)) ?? run;
      if (detail) {
        agent.setAgentThread(agent.threadFromRun(detail));
      }
    } catch (err) {
      sessions.setError(err instanceof Error ? err.message : "Failed to load run");
    }
  }

  function onNewAgent() {
    sessions.onNewAgent();
    agent.setAgentThread([]);
  }

  function onDeleteSession(id: string) {
    void sessions.onDeleteSession(id);
  }

  const active = sessions.conversations.find((c) => c.id === sessions.conversationId);
  const activeAgentRun =
    sessions.agentRuns.find((r) => r.id === sessions.agentRunId) ??
    agent.agentThread.find((t) => t.run)?.run ??
    null;

  const empty = (mode === "chat" ? sessions.messages : agent.agentThread).length === 0 && !sending;

  const title =
    mode === "agent"
      ? activeAgentRun
        ? activeAgentRun.goal.length > 48
          ? `${activeAgentRun.goal.slice(0, 48)}…`
          : activeAgentRun.goal
        : agent.agentThread.length > 0
          ? "Current agent run"
          : "New agent run"
      : active?.title || "New session";

  const subtitle =
    mode === "agent"
      ? activeAgentRun
        ? `Run · ${formatDate(activeAgentRun.created_at)}`
        : "Tools: list / search docs, create_note (HITL)"
      : active
        ? `Session · ${formatDate(active.created_at)}`
        : "Send a message to start a session";

  const loading =
    sessions.loadingWs ||
    (mode === "chat" ? sessions.loadingSessions : sessions.loadingAgentRuns);

  const value: ChatPageContextValue = {
    mode,
    input,
    sessionsOpen,
    sending,
    error: sessions.error,
    workspaces: sessions.workspaces,
    workspaceId: sessions.workspaceId,
    conversations: sessions.conversations,
    conversationId: sessions.conversationId,
    agentRuns: sessions.agentRuns,
    agentRunId: sessions.agentRunId,
    messages: sessions.messages,
    agentThread: agent.agentThread,
    approving: agent.approving,
    savingNote: agent.savingNote,
    loadingWs: sessions.loadingWs,
    loadingSessions: sessions.loadingSessions,
    loadingAgentRuns: sessions.loadingAgentRuns,
    active,
    activeAgentRun,
    empty,
    title,
    subtitle,
    showDelete: mode === "chat" && !!active,
    showClear: mode === "agent" && agent.agentThread.length > 0,
    loading,
    sessionPanelProps: {
      mode,
      workspaces: sessions.workspaces,
      workspaceId: sessions.workspaceId,
      onWorkspaceChange: sessions.setWorkspaceId,
      conversations: sessions.conversations,
      conversationId: sessions.conversationId,
      agentRuns: sessions.agentRuns,
      agentRunId: sessions.agentRunId,
      loading: loading,
      onNewChat: () => { void sessions.onNewChat(); },
      onSelectSession: (id) => sessions.onSelectSession(id),
      onDeleteSession,
      onSelectAgentRun,
      onNewAgent,
      onAfterNavigate: () => setSessionsOpen(false),
    },
    onSetMode: setModePersist,
    onChangeWorkspace: sessions.setWorkspaceId,
    onSelectSession: (id) => sessions.onSelectSession(id),
    onNewChat: () => { void sessions.onNewChat(); },
    onDeleteSession,
    onSelectAgentRun,
    onNewAgent,
    onSend,
    onApproveAgent: (asstId, runId, approve) => { void agent.onApproveAgent(asstId, runId, approve); },
    onSaveLearningNote: (title, body) => { void agent.onSaveLearningNote(title, body); },
    onInputChange: setInput,
    onToggleSessions: () => setSessionsOpen(true),
    onCloseSessions: () => setSessionsOpen(false),
    onLogout: () => navigate("/login", { replace: true }),
  };

  return (
    <ChatPageContext.Provider value={value}>
      {children}
    </ChatPageContext.Provider>
  );
}
