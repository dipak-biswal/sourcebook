import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  Loader2,
  MessageCircle,
  Plus,
  Send,
  Trash2,
} from "lucide-react";
import {
  api,
  getToken,
  type ChatMessage,
  type Conversation,
  type Workspace,
} from "@/api";
import {
  CitationList,
  isDenialMessage,
  shouldShowSources,
} from "@/components/chat/CitationList";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatError } from "@/lib/utils";

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

export function ChatPage() {
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [sending, setSending] = useState(false);

  const loadMessages = useCallback(async (convId: string) => {
    if (!convId) {
      setMessages([]);
      return;
    }
    const list = await api.messages(convId);
    // Oldest → newest (user then assistant). Guard against API/clock quirks.
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
    // only when workspace changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workspaceId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

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

  async function onSend(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending || !workspaceId) return;

    setSending(true);
    setError(null);
    setInput("");

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

      // Sync with DB (ids, ordering) after stream completes
      await loadMessages(convId);
      await loadConversations(workspaceId, convId);
    } catch (err) {
      setError(formatError(err));
      setMessages((prev) =>
        prev.filter((m) => m.id !== userTempId && m.id !== asstTempId),
      );
      setInput(text);
    } finally {
      setSending(false);
    }
  }

  const active = conversations.find((c) => c.id === conversationId);

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas-soft">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        {/* Sessions sidebar */}
        <aside className="flex w-80 shrink-0 flex-col border-r border-hairline bg-canvas">
          <div className="shrink-0 border-b border-hairline p-4">
            <div className="flex items-center justify-between gap-2">
              <div>
                <h2 className="text-body-sm font-semibold text-ink">Sessions</h2>
                <p className="mt-0.5 text-xs text-mute">
                  Your chat history in this workspace
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
                  or send a message.
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
            <p className="text-[11px] leading-snug text-mute">
              Docs must show status <span className="text-ink">ready</span>{" "}
              before chat can cite them.
            </p>
          </div>
        </aside>

        {/* Main chat */}
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">
          <div className="flex shrink-0 items-center justify-between border-b border-hairline bg-canvas px-6 py-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-ink">
                {active?.title || "New session"}
              </div>
              <div className="text-xs text-mute">
                {active
                  ? `Session · ${formatSessionDate(active.created_at)}`
                  : "Send a message to start a session"}
              </div>
            </div>
            {active && (
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
          </div>

          {error && (
            <div className="px-6 pt-4">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}

          <div className="document-scroll min-h-0 flex-1 overflow-y-auto px-6 py-6">
            {messages.length === 0 && !sending ? (
              <div className="flex h-full flex-col items-center justify-center text-center">
                <div className="flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute">
                  <MessageCircle className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <h2 className="mt-4 text-display-sm font-semibold text-ink">
                  Ask about your documents
                </h2>
                <p className="mt-2 max-w-md text-body-sm text-mute">
                  1) Upload .txt/.md on Documents · 2) Click{" "}
                  <strong className="text-ink">Ingest</strong> until status is{" "}
                  <strong className="text-ink">ready</strong> · 3) Ask here.
                </p>
                <Button
                  type="button"
                  variant="secondary"
                  className="mt-6"
                  onClick={() => navigate("/documents")}
                >
                  Open documents
                </Button>
              </div>
            ) : (
              <div className="mx-auto flex max-w-2xl flex-col gap-4">
                {messages.map((m) => {
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
                          <div className="whitespace-pre-wrap">{m.content}</div>
                        </div>
                      )}
                      {!isUser &&
                        shouldShowSources(m.content, m.citations) && (
                          <CitationList citations={m.citations} />
                        )}
                    </div>
                  );
                })}
                {sending &&
                  !(
                    messages.length > 0 &&
                    messages[messages.length - 1]?.role === "assistant" &&
                    messages[messages.length - 1]?.content
                  ) && (
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
            <div className="mx-auto flex max-w-2xl gap-2">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question about your documents…"
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
          </form>
        </main>
      </div>
    </div>
  );
}
