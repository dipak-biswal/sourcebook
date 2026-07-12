import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bot,
  Loader2,
  MessageCircle,
  PanelLeft,
  Send,
  Trash2,
} from "lucide-react";
import {
  api,
  getToken,
  type AgentRun,
  type ChatMessage,
  type Conversation,
  type Workspace,
} from "@/api";
import {
  extractGenerativeUIFromSteps,
  GenerativeUIView,
} from "@/components/agents/GenerativeUI";
import {
  AGENT_EXAMPLE_GOALS,
  AgentApprovalCard,
  AgentStatusBadge,
  AgentStepList,
} from "@/components/agents/shared";
import { ChatSessionsPanel } from "@/components/chat/ChatSessionsPanel";
import {
  CitationList,
  isDenialMessage,
  shouldShowSources,
} from "@/components/chat/CitationList";
import { CopyButton } from "@/components/chat/CopyButton";
import { ModeTip } from "@/components/chat/ModeTip";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { cn, formatError } from "@/lib/utils";

const MODE_KEY = "sourcebook_chat_mode";

type ChatMode = "chat" | "agent";

/** Ephemeral agent turns in the chat thread (not persisted to conversation messages). */
type AgentThreadItem = {
  id: string;
  role: "user" | "assistant";
  content: string;
  run?: AgentRun | null;
  pending?: boolean;
};

type ThreadItem =
  | { kind: "chat"; message: ChatMessage }
  | { kind: "agent"; item: AgentThreadItem };

function formatSessionDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function readMode(): ChatMode {
  try {
    const v = localStorage.getItem(MODE_KEY);
    if (v === "agent" || v === "chat") return v;
  } catch {
    /* ignore */
  }
  return "chat";
}

export function ChatPage() {
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);
  const { success, error: toastError } = useToast();
  useDocumentTitle("Chat");

  const [mode, setMode] = useState<ChatMode>(readMode);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentThread, setAgentThread] = useState<AgentThreadItem[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sending, setSending] = useState(false);
  const [approving, setApproving] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);

  const setModePersist = (m: ChatMode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* ignore */
    }
  };

  const loadMessages = useCallback(async (convId: string) => {
    if (!convId) {
      setMessages([]);
      return;
    }
    const list = await api.messages(convId);
    const sorted = [...list].sort((a, b) => {
      const ta = new Date(a.created_at).getTime();
      const tb = new Date(b.created_at).getTime();
      if (ta !== tb) return ta - tb;
      if (a.role === "user" && b.role === "assistant") return -1;
      if (a.role === "assistant" && b.role === "user") return 1;
      return a.id.localeCompare(b.id);
    });
    setMessages(sorted);
  }, []);

  const loadConversations = useCallback(
    async (ws: string, preferId?: string) => {
      if (!ws) return;
      setLoadingSessions(true);
      try {
        const list = await api.conversations(ws);
        setConversations(list);

        const stillThere =
          preferId && list.some((c) => c.id === preferId) ? preferId : null;
        const currentStillThere =
          conversationId && list.some((c) => c.id === conversationId)
            ? conversationId
            : null;
        const nextId = stillThere || currentStillThere || list[0]?.id || "";

        setConversationId(nextId);
        if (nextId) await loadMessages(nextId);
        else setMessages([]);
      } finally {
        setLoadingSessions(false);
      }
    },
    [conversationId, loadMessages],
  );

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    (async () => {
      setLoadingWs(true);
      setError(null);
      try {
        const list = await api.workspaces();
        if (cancelled) return;
        setWorkspaces(list);
        const first = list[0]?.id ?? "";
        setWorkspaceId((prev) => prev || first);
      } catch (err) {
        if (!cancelled) setError(formatError(err));
      } finally {
        if (!cancelled) setLoadingWs(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    loadConversations(workspaceId).catch((err) => setError(formatError(err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, agentThread, sending]);

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  async function onNewChat() {
    if (!workspaceId) return;
    setError(null);
    try {
      const conv = await api.createConversation(workspaceId, "New chat");
      await loadConversations(workspaceId, conv.id);
      setMessages([]);
      setAgentThread([]);
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function onDeleteSession(id: string) {
    if (
      !confirmAction(
        "Delete this chat session?",
        "Messages in this session will be removed.",
      )
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
      await loadConversations(workspaceId, nextPrefer);
      success("Session deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  async function onSelectSession(id: string) {
    setConversationId(id);
    setError(null);
    try {
      await loadMessages(id);
    } catch (err) {
      setError(formatError(err));
    }
  }

  function applyRunToThread(asstId: string, run: AgentRun) {
    const content =
      run.final_answer ||
      (run.status === "waiting_approval"
        ? "Waiting for your approval on a write action…"
        : run.error
          ? `Agent failed: ${run.error}`
          : run.status === "completed"
            ? "(empty answer)"
            : `Status: ${run.status}`);
    setAgentThread((prev) =>
      prev.map((item) =>
        item.id === asstId
          ? { ...item, content, run, pending: false }
          : item,
      ),
    );
  }

  async function onSendChat(text: string) {
    const userTempId = `temp-user-${Date.now()}`;
    const asstTempId = `temp-asst-${Date.now()}`;

    setMessages((prev) => [
      ...prev,
      {
        id: userTempId,
        conversation_id: conversationId || "pending",
        role: "user",
        content: text,
        created_at: new Date().toISOString(),
      },
      {
        id: asstTempId,
        conversation_id: conversationId || "pending",
        role: "assistant",
        content: "",
        citations: [],
        created_at: new Date().toISOString(),
      },
    ]);

    try {
      let convId = conversationId;
      if (!convId) {
        const conv = await api.createConversation(workspaceId, "New chat");
        convId = conv.id;
        setConversationId(convId);
      }

      await api.chatStream(convId, text, {
        onToken: (chunk) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstTempId
                ? { ...m, content: m.content + chunk }
                : m,
            ),
          );
        },
        onCitations: (citations) => {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === asstTempId ? { ...m, citations } : m,
            ),
          );
        },
      });

      await loadMessages(convId);
      await loadConversations(workspaceId, convId);
    } catch (err) {
      setError(formatError(err));
      setMessages((prev) =>
        prev.filter((m) => m.id !== userTempId && m.id !== asstTempId),
      );
      setInput(text);
    }
  }

  async function onSendAgent(text: string) {
    const userId = `agent-user-${Date.now()}`;
    const asstId = `agent-asst-${Date.now()}`;

    setAgentThread((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      {
        id: asstId,
        role: "assistant",
        content: "Agent is working (tools may take ~30s)…",
        pending: true,
        run: null,
      },
    ]);

    try {
      const run = await api.startAgentRun(workspaceId, text, 5);
      applyRunToThread(asstId, run);
      if (run.status === "waiting_approval") {
        success("Approval needed", "Review the write action below.");
      } else if (run.status === "completed") {
        success("Agent finished");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Agent failed", msg);
      setAgentThread((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== asstId),
      );
      setInput(text);
    }
  }

  async function onSend(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || sending || !workspaceId) return;

    setSending(true);
    setError(null);
    setInput("");

    try {
      if (mode === "chat") await onSendChat(text);
      else await onSendAgent(text);
    } finally {
      setSending(false);
    }
  }

  async function onApproveAgent(asstId: string, runId: string, approve: boolean) {
    if (approving) return;
    setApproving(true);
    setError(null);
    try {
      const run = await api.approveAgentRun(runId, approve);
      applyRunToThread(asstId, run);
      success(approve ? "Action approved" : "Action rejected");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Approval failed", msg);
    } finally {
      setApproving(false);
    }
  }

  const sessionsPanel = (
    <ChatSessionsPanel
      workspaces={workspaces}
      workspaceId={workspaceId}
      onWorkspaceChange={setWorkspaceId}
      conversations={conversations}
      conversationId={conversationId}
      loading={loadingWs || loadingSessions}
      onNewChat={() => void onNewChat()}
      onSelectSession={(id) => void onSelectSession(id)}
      onDeleteSession={(id) => void onDeleteSession(id)}
      onAfterNavigate={() => setSessionsOpen(false)}
    />
  );

  const active = conversations.find((c) => c.id === conversationId);

  const thread: ThreadItem[] =
    mode === "chat"
      ? messages.map((m) => ({ kind: "chat" as const, message: m }))
      : agentThread.map((item) => ({ kind: "agent" as const, item }));

  const empty = thread.length === 0 && !sending;

  return (
    <div className="app-shell">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 flex-col border-r border-hairline bg-canvas md:flex">
          {sessionsPanel}
        </aside>

        <Sheet
          open={sessionsOpen}
          onClose={() => setSessionsOpen(false)}
          title="Sessions"
          description="Chat history in this workspace"
          side="left"
        >
          {sessionsPanel}
        </Sheet>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-hairline bg-canvas px-4 py-3 sm:px-6">
            <div className="flex min-w-0 items-start gap-2">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="mt-0.5 shrink-0 md:hidden"
                aria-label="Open sessions"
                onClick={() => setSessionsOpen(true)}
              >
                <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
              </Button>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">
                  {mode === "agent"
                    ? "Agent mode"
                    : active?.title || "New session"}
                </div>
                <div className="text-xs text-mute">
                  {mode === "agent"
                    ? "Tools: list / search documents, create_note (HITL)"
                    : active
                      ? `Session · ${formatSessionDate(active.created_at)}`
                      : "Send a message to start a session"}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              {mode === "chat" && active && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => void onDeleteSession(active.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span className="hidden sm:inline">Delete</span>
                </Button>
              )}
              {mode === "agent" && agentThread.length > 0 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setAgentThread([])}
                >
                  Clear
                </Button>
              )}
            </div>
          </div>

          <ModeTip />

          {error && (
            <div className="px-4 pt-3 sm:px-6">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}

          <div className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6 sm:py-6">
            {empty ? (
              <EmptyState
                icon={mode === "agent" ? Bot : MessageCircle}
                title={
                  mode === "agent"
                    ? "Run tools from chat"
                    : "Ask about your documents"
                }
                description={
                  mode === "agent"
                    ? "List/search docs, generate an easy learning view from your uploads, or create a note (writes need approval)."
                    : "Upload .txt/.md, ingest until ready, then ask grounded questions here."
                }
                actionLabel={mode === "chat" ? "Open documents" : undefined}
                onAction={
                  mode === "chat" ? () => navigate("/documents") : undefined
                }
              >
                {mode === "agent" && (
                  <div className="mt-6 flex max-w-lg flex-wrap justify-center gap-1.5">
                    {AGENT_EXAMPLE_GOALS.map((g) => (
                      <button
                        key={g}
                        type="button"
                        disabled={sending || !workspaceId}
                        onClick={() => setInput(g)}
                        className="rounded-full border border-hairline bg-canvas px-2.5 py-1 text-left text-[11px] text-body hover:bg-canvas-soft-2"
                      >
                        {g.length > 52 ? `${g.slice(0, 52)}…` : g}
                      </button>
                    ))}
                  </div>
                )}
              </EmptyState>
            ) : (
              <div className="mx-auto flex max-w-2xl flex-col gap-4">
                {thread.map((entry) => {
                  if (entry.kind === "chat") {
                    const m = entry.message;
                    const isUser = m.role === "user";
                    const denial =
                      !isUser && m.content && isDenialMessage(m.content);
                    return (
                      <div
                        key={m.id}
                        className={cn(
                          "flex flex-col",
                          isUser ? "items-end" : "items-start",
                        )}
                      >
                        {denial ? (
                          <div className="max-w-[90%] rounded-vercel-md border border-warning-border bg-warning-soft px-3.5 py-3 text-body-sm text-warning-text">
                            <div className="mb-1.5 flex items-center gap-1.5 font-medium">
                              <AlertCircle
                                className="h-4 w-4 shrink-0"
                                strokeWidth={1.5}
                              />
                              No grounded match
                            </div>
                            <div className="whitespace-pre-wrap leading-relaxed">
                              {m.content}
                            </div>
                            <button
                              type="button"
                              className="mt-3 text-xs font-medium text-ink underline-offset-2 hover:underline"
                              onClick={() => navigate("/documents")}
                            >
                              Go to Documents → ingest
                            </button>
                          </div>
                        ) : (
                          <div
                            className={cn(
                              "max-w-[min(90%,36rem)] rounded-vercel-md border px-3.5 py-2.5 text-body-sm leading-relaxed",
                              isUser
                                ? "rounded-br-sm border-ink bg-ink text-[var(--canvas)]"
                                : "rounded-bl-sm border-hairline bg-canvas text-body shadow-[var(--elevation-2)]",
                            )}
                          >
                            <div className="whitespace-pre-wrap">
                              {m.content}
                            </div>
                          </div>
                        )}
                        {!isUser && m.content && !denial && (
                          <div className="mt-1">
                            <CopyButton text={m.content} />
                          </div>
                        )}
                        {!isUser &&
                          shouldShowSources(m.content, m.citations) && (
                            <CitationList citations={m.citations} />
                          )}
                      </div>
                    );
                  }

                  const item = entry.item;
                  const isUser = item.role === "user";
                  return (
                    <div
                      key={item.id}
                      className={cn(
                        "flex flex-col",
                        isUser ? "items-end" : "items-start",
                      )}
                    >
                      <div
                        className={cn(
                          "max-w-[min(90%,36rem)] rounded-vercel-md border px-3.5 py-2.5 text-body-sm leading-relaxed",
                          isUser
                            ? "rounded-br-sm border-ink bg-ink text-[var(--canvas)]"
                            : "rounded-bl-sm border-hairline bg-canvas text-body shadow-[var(--elevation-2)]",
                        )}
                      >
                        {!isUser && (
                          <div className="mb-2 flex flex-wrap items-center gap-1.5">
                            <Bot className="h-3.5 w-3.5 text-mute" strokeWidth={1.5} />
                            <Badge variant="secondary" className="text-[10px]">
                              Agent
                            </Badge>
                            {item.run && (
                              <AgentStatusBadge status={item.run.status} />
                            )}
                            {item.run?.token_usage != null && (
                              <span className="text-[11px] text-mute">
                                ~{item.run.token_usage.toLocaleString()} tokens
                              </span>
                            )}
                            {item.pending && (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-mute" />
                            )}
                          </div>
                        )}
                        <div className="whitespace-pre-wrap">{item.content}</div>
                      </div>

                      {!isUser && item.content && !item.pending && (
                        <div className="mt-1">
                          <CopyButton text={item.content} />
                        </div>
                      )}

                      {!isUser &&
                        item.run &&
                        (() => {
                          const gen = extractGenerativeUIFromSteps(
                            item.run.steps ?? [],
                          );
                          return gen ? (
                            <div className="mt-2 w-full max-w-[min(100%,36rem)]">
                              <GenerativeUIView payload={gen} />
                            </div>
                          ) : null;
                        })()}

                      {!isUser && item.run && item.run.steps?.length > 0 && (
                        <div className="mt-2 max-w-[90%] rounded-[6px] border border-hairline bg-canvas px-3 py-2">
                          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-mute">
                            Steps ({item.run.steps.length})
                          </div>
                          <AgentStepList steps={item.run.steps} compact />
                        </div>
                      )}

                      {!isUser &&
                        item.run?.status === "waiting_approval" &&
                        item.run.pending_tool && (
                          <div className="mt-2 max-w-[90%]">
                            <AgentApprovalCard
                              pendingTool={item.run.pending_tool}
                              approving={approving}
                              onApprove={() =>
                                void onApproveAgent(
                                  item.id,
                                  item.run!.id,
                                  true,
                                )
                              }
                              onReject={() =>
                                void onApproveAgent(
                                  item.id,
                                  item.run!.id,
                                  false,
                                )
                              }
                            />
                          </div>
                        )}
                    </div>
                  );
                })}
                {sending && mode === "chat" && (
                  <div className="flex items-center gap-2 text-sm text-mute">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Retrieving & generating…
                  </div>
                )}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          <form
            onSubmit={onSend}
            className="shrink-0 border-t border-hairline bg-canvas px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6 sm:py-4"
          >
            <div className="mx-auto max-w-2xl space-y-2">
              <div className="flex items-center gap-2">
                <div className="inline-flex rounded-[6px] border border-hairline p-0.5">
                  <button
                    type="button"
                    onClick={() => setModePersist("chat")}
                    className={cn(
                      "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
                      mode === "chat"
                        ? "bg-ink text-[var(--canvas)]"
                        : "text-body hover:bg-canvas-soft-2",
                    )}
                  >
                    <MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
                    Chat
                  </button>
                  <button
                    type="button"
                    onClick={() => setModePersist("agent")}
                    className={cn(
                      "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
                      mode === "agent"
                        ? "bg-ink text-[var(--canvas)]"
                        : "text-body hover:bg-canvas-soft-2",
                    )}
                  >
                    <Bot className="h-3.5 w-3.5" strokeWidth={1.5} />
                    Agent
                  </button>
                </div>
                <span className="hidden text-[11px] text-mute sm:inline">
                  {mode === "chat"
                    ? "Grounded RAG + citations · ⌘/Ctrl+Enter"
                    : "Tools + HITL · ⌘/Ctrl+Enter"}
                </span>
              </div>
              <div className="flex gap-2">
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      void onSend();
                    }
                  }}
                  placeholder={
                    !workspaceId
                      ? "Select a workspace first…"
                      : mode === "agent"
                        ? "List docs, search, or create a note…"
                        : "Ask a question about your documents…"
                  }
                  disabled={sending || !workspaceId}
                  className="flex-1"
                  autoFocus
                />
                <Button
                  type="submit"
                  disabled={sending || !input.trim() || !workspaceId}
                  className="rounded-[6px] px-4"
                  title={
                    !workspaceId
                      ? "Select a workspace first"
                      : !input.trim()
                        ? "Type a message"
                        : "Send"
                  }
                >
                  {sending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Send className="h-4 w-4" strokeWidth={1.5} />
                  )}
                  Send
                </Button>
              </div>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
