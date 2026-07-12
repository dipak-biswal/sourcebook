import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Bot,
  Loader2,
  MessageCircle,
  Plus,
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
  AGENT_EXAMPLE_GOALS,
  AgentApprovalCard,
  AgentStatusBadge,
  AgentStepList,
} from "@/components/agents/shared";
import {
  CitationList,
  isDenialMessage,
  shouldShowSources,
} from "@/components/chat/CitationList";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
    setError(null);
    try {
      await api.deleteConversation(id);
      const nextPrefer =
        conversationId === id
          ? conversations.find((c) => c.id !== id)?.id
          : conversationId;
      await loadConversations(workspaceId, nextPrefer);
    } catch (err) {
      setError(formatError(err));
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
    } catch (err) {
      setError(formatError(err));
      setAgentThread((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== asstId),
      );
      setInput(text);
    }
  }

  async function onSend(e: FormEvent) {
    e.preventDefault();
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
    } catch (err) {
      setError(formatError(err));
    } finally {
      setApproving(false);
    }
  }

  const active = conversations.find((c) => c.id === conversationId);

  const thread: ThreadItem[] =
    mode === "chat"
      ? messages.map((m) => ({ kind: "chat" as const, message: m }))
      : agentThread.map((item) => ({ kind: "agent" as const, item }));

  const empty = thread.length === 0 && !sending;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas-soft">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-80 shrink-0 flex-col border-r border-hairline bg-canvas">
          <div className="shrink-0 border-b border-hairline p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-body-sm font-semibold text-ink">Sessions</h2>
                <p className="mt-0.5 text-xs text-mute">
                  RAG chat history (Agent turns stay in this tab for now)
                </p>
              </div>
            </div>

            {workspaces.length > 0 && (
              <label className="mt-3 block">
                <span className="mb-1 block text-xs text-mute">Workspace</span>
                <select
                  value={workspaceId}
                  onChange={(e) => setWorkspaceId(e.target.value)}
                  className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <Button
              type="button"
              className="mt-3 w-full rounded-[6px]"
              disabled={!workspaceId || loadingWs}
              onClick={onNewChat}
            >
              <Plus className="h-4 w-4" strokeWidth={1.5} />
              New session
            </Button>
          </div>

          <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
            <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
              Session list ({conversations.length})
            </div>

            {loadingWs || loadingSessions ? (
              <p className="flex items-center gap-2 px-2 py-3 text-xs text-mute">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Loading sessions…
              </p>
            ) : conversations.length === 0 ? (
              <div className="rounded-[6px] border border-dashed border-hairline px-3 py-4 text-center">
                <p className="text-xs text-mute">No sessions yet.</p>
                <p className="mt-1 text-xs text-mute">
                  Click <span className="font-medium text-ink">New session</span>{" "}
                  or send a message in Chat mode.
                </p>
              </div>
            ) : (
              <ul className="space-y-1">
                {conversations.map((c) => {
                  const selected = c.id === conversationId;
                  return (
                    <li key={c.id}>
                      <div
                        className={cn(
                          "group flex items-start gap-1 rounded-[6px] border px-2 py-2 transition-colors",
                          selected
                            ? "border-hairline bg-canvas-soft-2"
                            : "border-transparent hover:bg-canvas-soft-2",
                        )}
                      >
                        <button
                          type="button"
                          onClick={() => onSelectSession(c.id)}
                          className="min-w-0 flex-1 text-left"
                        >
                          <div
                            className={cn(
                              "truncate text-sm",
                              selected
                                ? "font-semibold text-ink"
                                : "font-medium text-ink",
                            )}
                          >
                            {c.title || "Untitled session"}
                          </div>
                          <div className="mt-0.5 text-[11px] text-mute">
                            {formatSessionDate(c.created_at)}
                          </div>
                        </button>
                        <button
                          type="button"
                          title="Delete session"
                          className="rounded p-1 text-mute opacity-100 transition-opacity hover:bg-canvas hover:text-ink sm:opacity-0 sm:group-hover:opacity-100"
                          onClick={(e) => {
                            e.stopPropagation();
                            void onDeleteSession(c.id);
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="shrink-0 space-y-2 border-t border-hairline p-3">
            <Link
              to="/documents"
              className="block text-xs font-medium text-ink underline-offset-2 hover:underline"
            >
              → Manage documents & ingest
            </Link>
            <Link
              to="/agents"
              className="block text-xs font-medium text-ink underline-offset-2 hover:underline"
            >
              → Agent run history & notes
            </Link>
            <p className="text-[11px] leading-snug text-mute">
              Docs must show status <span className="text-ink">ready</span>{" "}
              before Chat mode can cite them.
            </p>
          </div>
        </aside>

        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-canvas px-6 py-3">
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
            {mode === "chat" && active && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void onDeleteSession(active.id)}
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            )}
            {mode === "agent" && agentThread.length > 0 && (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setAgentThread([])}
              >
                Clear agent thread
              </Button>
            )}
          </div>

          {error && (
            <div className="px-6 pt-4">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}

          <div className="document-scroll min-h-0 flex-1 overflow-y-auto px-6 py-6">
            {empty ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute">
                  {mode === "agent" ? (
                    <Bot className="h-5 w-5" strokeWidth={1.5} />
                  ) : (
                    <MessageCircle className="h-5 w-5" strokeWidth={1.5} />
                  )}
                </div>
                <h2 className="mt-4 text-display-sm font-semibold text-ink">
                  {mode === "agent"
                    ? "Run tools from chat"
                    : "Ask about your documents"}
                </h2>
                <p className="mt-2 max-w-md text-body-sm text-mute">
                  {mode === "agent" ? (
                    <>
                      List or search documents, or create a note (writes need
                      your approval). Full history also lives on the{" "}
                      <Link to="/agents" className="font-medium text-ink underline">
                        Agents
                      </Link>{" "}
                      page.
                    </>
                  ) : (
                    <>
                      1) Upload .txt/.md on Documents · 2) Click{" "}
                      <strong className="text-ink">Ingest</strong> until status
                      is <strong className="text-ink">ready</strong> · 3) Ask
                      here.
                    </>
                  )}
                </p>
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
                {mode === "chat" && (
                  <Button
                    type="button"
                    variant="secondary"
                    className="mt-6"
                    onClick={() => navigate("/documents")}
                  >
                    Open documents
                  </Button>
                )}
              </div>
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
                          <div className="max-w-[90%] rounded-vercel-md border border-amber-200 bg-[#fffbeb] px-3.5 py-3 text-body-sm text-[#92400e]">
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
                              "max-w-[90%] rounded-vercel-md border px-3.5 py-2.5 text-body-sm leading-relaxed",
                              isUser
                                ? "border-ink bg-ink text-[var(--canvas)]"
                                : "border-hairline bg-canvas text-body shadow-[var(--elevation-2)]",
                            )}
                          >
                            <div className="whitespace-pre-wrap">
                              {m.content}
                            </div>
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
                          "max-w-[90%] rounded-vercel-md border px-3.5 py-2.5 text-body-sm leading-relaxed",
                          isUser
                            ? "border-ink bg-ink text-[var(--canvas)]"
                            : "border-hairline bg-canvas text-body shadow-[var(--elevation-2)]",
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
                            {item.pending && (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-mute" />
                            )}
                          </div>
                        )}
                        <div className="whitespace-pre-wrap">{item.content}</div>
                      </div>

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
            className="shrink-0 border-t border-hairline bg-canvas px-6 py-4"
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
                <span className="text-[11px] text-mute">
                  {mode === "chat"
                    ? "Grounded RAG + citations"
                    : "Tools + human approval for writes"}
                </span>
              </div>
              <div className="flex gap-2">
                <Input
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder={
                    mode === "agent"
                      ? "List docs, search, or create a note…"
                      : "Ask a question about your documents…"
                  }
                  disabled={sending || !workspaceId}
                  className="flex-1"
                />
                <Button
                  type="submit"
                  disabled={sending || !input.trim() || !workspaceId}
                  className="rounded-[6px] px-4"
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
