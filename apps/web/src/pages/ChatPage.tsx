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
  type AgentStep,
  type ChatMessage,
  type Conversation,
  type Workspace,
} from "@/api";
import {
  AgentRunPanel,
  type LiveTraceSpan,
  type LlmTraceEvent,
} from "@/components/agents/AgentRunPanel";
import {
  extractGenerativeUIFromSteps,
  GenerativeUIView,
} from "@/components/agents/GenerativeUI";
import { AGENT_EXAMPLE_GOALS } from "@/components/agents/shared";
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
  /** User goal — used to show run view immediately before API returns */
  goal?: string;
  liveSteps?: AgentStep[];
  liveTokenUsage?: number | null;
  liveLlmEvents?: LlmTraceEvent[];
  /** Chronological LangSmith-style spans as SSE events arrive */
  liveTrace?: LiveTraceSpan[];
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
  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentRunId, setAgentRunId] = useState("");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loadingWs, setLoadingWs] = useState(true);
  const [loadingSessions, setLoadingSessions] = useState(false);
  const [loadingAgentRuns, setLoadingAgentRuns] = useState(false);
  const [sending, setSending] = useState(false);
  const [approving, setApproving] = useState(false);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  const [savingNote, setSavingNote] = useState(false);

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

  const loadAgentRuns = useCallback(
    async (ws: string, preferId?: string) => {
      if (!ws) return;
      setLoadingAgentRuns(true);
      try {
        const list = await api.agentRuns(ws);
        setAgentRuns(list);
        if (preferId && list.some((r) => r.id === preferId)) {
          setAgentRunId(preferId);
        }
      } finally {
        setLoadingAgentRuns(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (!workspaceId) return;
    loadConversations(workspaceId).catch((err) => setError(formatError(err)));
    loadAgentRuns(workspaceId).catch((err) => setError(formatError(err)));
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
    } catch (err) {
      setError(formatError(err));
    }
  }

  function onNewAgent() {
    setAgentThread([]);
    setAgentRunId("");
    setError(null);
  }

  function threadFromRun(run: AgentRun): AgentThreadItem[] {
    const content =
      run.final_answer ||
      (run.status === "waiting_approval"
        ? "Waiting for your approval on a write action…"
        : run.error
          ? `Agent failed: ${run.error}`
          : run.status === "completed"
            ? "(empty answer)"
            : `Status: ${run.status}`);
    return [
      {
        id: `agent-user-${run.id}`,
        role: "user",
        content: run.goal,
      },
      {
        id: `agent-asst-${run.id}`,
        role: "assistant",
        content,
        run,
        pending: false,
        goal: run.goal,
        liveSteps: run.steps,
        liveTokenUsage: run.token_usage,
        liveTrace: (run.steps ?? []).map((step) => ({
          kind: "step" as const,
          step,
        })),
      },
    ];
  }

  async function onSelectAgentRun(id: string) {
    setError(null);
    setAgentRunId(id);
    try {
      const detail =
        agentRuns.find((r) => r.id === id) ?? (await api.agentRun(id));
      // Prefer full detail with steps
      const run =
        detail.steps?.length || !agentRuns.find((r) => r.id === id)
          ? detail
          : await api.agentRun(id);
      setAgentThread(threadFromRun(run));
      setAgentRuns((prev) => {
        const i = prev.findIndex((r) => r.id === run.id);
        if (i < 0) return [run, ...prev];
        const next = [...prev];
        next[i] = run;
        return next;
      });
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
          ? {
              ...item,
              content,
              run,
              pending: false,
              liveSteps: run.steps,
              liveTokenUsage: run.token_usage,
              // Keep chronological trace if we streamed it; else map steps
              liveTrace:
                item.liveTrace && item.liveTrace.length > 0
                  ? item.liveTrace
                  : run.steps.map((step) => ({ kind: "step" as const, step })),
              liveLlmEvents: [],
            }
          : item,
      ),
    );
  }

  function appendTrace(asstId: string, span: LiveTraceSpan) {
    setAgentThread((prev) =>
      prev.map((item) => {
        if (item.id !== asstId) return item;
        return { ...item, liveTrace: [...(item.liveTrace ?? []), span] };
      }),
    );
  }

  function patchLlmInTrace(
    asstId: string,
    patch: Partial<LlmTraceEvent> & { status?: "running" | "done" },
  ) {
    setAgentThread((prev) =>
      prev.map((item) => {
        if (item.id !== asstId) return item;
        const liveTrace = (item.liveTrace ?? []).map((node) => {
          if (node.kind !== "llm" || node.event.status !== "running") return node;
          return {
            kind: "llm" as const,
            event: { ...node.event, ...patch, status: "done" as const },
          };
        });
        return { ...item, liveTrace };
      }),
    );
  }

  function patchLive(
    asstId: string,
    patch: Partial<AgentThreadItem>,
  ) {
    setAgentThread((prev) =>
      prev.map((item) => (item.id === asstId ? { ...item, ...patch } : item)),
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

    // Optimistic UI first — run panel mounts before the network call
    setAgentThread((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      {
        id: asstId,
        role: "assistant",
        content: "Agent is working — run view is open below…",
        pending: true,
        run: null,
        goal: text,
      },
    ]);
    // Scroll after paint so the live run panel is visible immediately
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });

    try {
      const run = await api.startAgentRunStream(
        workspaceId,
        text,
        {
          onRunStart: () => {
            patchLive(asstId, {
              content: "Trace live — LLM and tool spans appear as they run…",
            });
          },
          onLlmStart: () => {
            const id = `llm-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
            const event: LlmTraceEvent = {
              id,
              kind: "llm",
              status: "running",
              name: "ChatOpenAI",
            };
            appendTrace(asstId, { kind: "llm", event });
            setAgentThread((prev) =>
              prev.map((item) => {
                if (item.id !== asstId) return item;
                return {
                  ...item,
                  liveLlmEvents: [
                    ...(item.liveLlmEvents ?? []).filter((e) => e.status === "done"),
                    event,
                  ],
                };
              }),
            );
          },
          onLlmEnd: (p) => {
            patchLlmInTrace(asstId, {
              duration_ms: p.duration_ms,
              prompt_tokens: p.prompt_tokens,
              completion_tokens: p.completion_tokens,
              total_tokens: p.total_tokens,
              has_tool_calls: p.has_tool_calls,
            });
            setAgentThread((prev) =>
              prev.map((item) => {
                if (item.id !== asstId) return item;
                const events = (item.liveLlmEvents ?? []).map((e) =>
                  e.status === "running"
                    ? {
                        ...e,
                        status: "done" as const,
                        duration_ms: p.duration_ms,
                        prompt_tokens: p.prompt_tokens,
                        completion_tokens: p.completion_tokens,
                        total_tokens: p.total_tokens,
                        has_tool_calls: p.has_tool_calls,
                      }
                    : e,
                );
                return {
                  ...item,
                  liveLlmEvents: events,
                  liveTokenUsage:
                    p.token_usage_so_far ?? item.liveTokenUsage ?? null,
                };
              }),
            );
          },
          onStep: (step) => {
            setAgentThread((prev) =>
              prev.map((item) => {
                if (item.id !== asstId) return item;
                const steps = [...(item.liveSteps ?? [])];
                const i = steps.findIndex((s) => s.id === step.id);
                if (i >= 0) steps[i] = step;
                else steps.push(step);
                // Append to chronological tree only once
                const already = (item.liveTrace ?? []).some(
                  (n) => n.kind === "step" && n.step.id === step.id,
                );
                const liveTrace = already
                  ? (item.liveTrace ?? []).map((n) =>
                      n.kind === "step" && n.step.id === step.id
                        ? { kind: "step" as const, step }
                        : n,
                    )
                  : [...(item.liveTrace ?? []), { kind: "step" as const, step }];
                return { ...item, liveSteps: steps, liveTrace };
              }),
            );
            requestAnimationFrame(() => {
              bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            });
          },
          onStatus: (p) => {
            if (p.final_answer) {
              patchLive(asstId, { content: p.final_answer });
            }
            if (p.token_usage != null) {
              patchLive(asstId, { liveTokenUsage: p.token_usage });
            }
          },
          onDone: (final) => {
            applyRunToThread(asstId, final);
            setAgentRunId(final.id);
            void loadAgentRuns(workspaceId, final.id);
            if (final.status === "waiting_approval") {
              success("Approval needed", "Review the write action below.");
            } else if (final.status === "completed") {
              success("Agent finished");
            }
          },
        },
        5,
      );
      if (run) {
        applyRunToThread(asstId, run);
        setAgentRunId(run.id);
        void loadAgentRuns(workspaceId, run.id);
      }
      requestAnimationFrame(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      });
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

    setError(null);
    setInput("");

    if (mode === "agent") {
      // Do not wait to flip UI — show run panel in the same tick as click
      setSending(true);
      try {
        await onSendAgent(text);
      } finally {
        setSending(false);
      }
      return;
    }

    setSending(true);
    try {
      await onSendChat(text);
    } finally {
      setSending(false);
    }
  }

  async function onApproveAgent(asstId: string, runId: string, approve: boolean) {
    if (approving) return;
    setApproving(true);
    setError(null);
    // Keep run view live while resume-after-approve is in flight
    setAgentThread((prev) =>
      prev.map((item) =>
        item.id === asstId
          ? {
              ...item,
              pending: true,
              content: approve
                ? "Approved — agent is continuing…"
                : "Rejecting…",
            }
          : item,
      ),
    );
    try {
      if (!approve) {
        const run = await api.approveAgentRun(runId, false);
        applyRunToThread(asstId, run);
        success("Action rejected");
        return;
      }
      const run = await api.approveAgentRunStream(runId, true, {
        onStep: (step) => {
          setAgentThread((prev) =>
            prev.map((item) => {
              if (item.id !== asstId) return item;
              const steps = [...(item.liveSteps ?? item.run?.steps ?? [])];
              const i = steps.findIndex((s) => s.id === step.id);
              if (i >= 0) steps[i] = step;
              else steps.push(step);
              const already = (item.liveTrace ?? []).some(
                (n) => n.kind === "step" && n.step.id === step.id,
              );
              const liveTrace = already
                ? (item.liveTrace ?? []).map((n) =>
                    n.kind === "step" && n.step.id === step.id
                      ? { kind: "step" as const, step }
                      : n,
                  )
                : [...(item.liveTrace ?? []), { kind: "step" as const, step }];
              return { ...item, liveSteps: steps, liveTrace };
            }),
          );
        },
        onLlmStart: () => {
          const id = `llm-resume-${Date.now()}`;
          const event: LlmTraceEvent = {
            id,
            kind: "llm",
            status: "running",
            name: "ChatOpenAI",
          };
          appendTrace(asstId, { kind: "llm", event });
          setAgentThread((prev) =>
            prev.map((item) => {
              if (item.id !== asstId) return item;
              return {
                ...item,
                liveLlmEvents: [
                  ...(item.liveLlmEvents ?? []).filter((e) => e.status === "done"),
                  event,
                ],
              };
            }),
          );
        },
        onLlmEnd: (p) => {
          patchLlmInTrace(asstId, {
            duration_ms: p.duration_ms,
            prompt_tokens: p.prompt_tokens,
            completion_tokens: p.completion_tokens,
            total_tokens: p.total_tokens,
            has_tool_calls: p.has_tool_calls,
          });
          setAgentThread((prev) =>
            prev.map((item) => {
              if (item.id !== asstId) return item;
              return {
                ...item,
                liveTokenUsage:
                  p.token_usage_so_far ?? item.liveTokenUsage ?? null,
                liveLlmEvents: (item.liveLlmEvents ?? []).map((e) =>
                  e.status === "running"
                    ? {
                        ...e,
                        status: "done" as const,
                        duration_ms: p.duration_ms,
                        prompt_tokens: p.prompt_tokens,
                        completion_tokens: p.completion_tokens,
                        total_tokens: p.total_tokens,
                        has_tool_calls: p.has_tool_calls,
                      }
                    : e,
                ),
              };
            }),
          );
        },
        onDone: (final) => {
          applyRunToThread(asstId, final);
          setAgentRunId(final.id);
          void loadAgentRuns(workspaceId, final.id);
          success("Action approved — agent continued");
        },
      });
      if (run) {
        applyRunToThread(asstId, run);
        setAgentRunId(run.id);
        void loadAgentRuns(workspaceId, run.id);
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Approval failed", msg);
      setAgentThread((prev) =>
        prev.map((item) =>
          item.id === asstId ? { ...item, pending: false } : item,
        ),
      );
    } finally {
      setApproving(false);
    }
  }

  /** HITL path: start agent run that proposes create_note with learning content. */
  async function onSaveLearningNote(title: string, body: string) {
    if (!workspaceId || savingNote) return;
    setSavingNote(true);
    setError(null);
    const userId = `agent-user-note-${Date.now()}`;
    const asstId = `agent-asst-note-${Date.now()}`;
    const goal =
      `Create a note titled ${JSON.stringify(title)} with body:\n${body}`;
    setModePersist("agent");
    setAgentThread((prev) => [
      ...prev,
      { id: userId, role: "user", content: `Save learning view as note: ${title}` },
      {
        id: asstId,
        role: "assistant",
        content: "Preparing note (approval required)…",
        pending: true,
        run: null,
        goal,
      },
    ]);
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });
    try {
      const run = await api.startAgentRun(workspaceId, goal, 5);
      applyRunToThread(asstId, run);
      setAgentRunId(run.id);
      void loadAgentRuns(workspaceId, run.id);
      if (run.status === "waiting_approval") {
        success("Approve the note", "Review create_note below, then Approve.");
      } else if (run.status === "completed") {
        success("Note flow finished");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Could not start save-as-note", msg);
      setAgentThread((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== asstId),
      );
    } finally {
      setSavingNote(false);
    }
  }

  const sessionsPanel = (
    <ChatSessionsPanel
      mode={mode}
      workspaces={workspaces}
      workspaceId={workspaceId}
      onWorkspaceChange={setWorkspaceId}
      conversations={conversations}
      conversationId={conversationId}
      agentRuns={agentRuns}
      agentRunId={agentRunId}
      loading={
        loadingWs ||
        (mode === "chat" ? loadingSessions : loadingAgentRuns)
      }
      onNewChat={() => void onNewChat()}
      onSelectSession={(id) => void onSelectSession(id)}
      onDeleteSession={(id) => void onDeleteSession(id)}
      onSelectAgentRun={(id) => void onSelectAgentRun(id)}
      onNewAgent={onNewAgent}
      onAfterNavigate={() => setSessionsOpen(false)}
    />
  );

  const active = conversations.find((c) => c.id === conversationId);
  const activeAgentRun =
    agentRuns.find((r) => r.id === agentRunId) ??
    agentThread.find((t) => t.run)?.run ??
    null;

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
          title={mode === "agent" ? "Agent sessions" : "Chat sessions"}
          description={
            mode === "agent"
              ? "Agent runs in this workspace"
              : "Chat history in this workspace"
          }
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
                    ? activeAgentRun
                      ? activeAgentRun.goal.length > 48
                        ? `${activeAgentRun.goal.slice(0, 48)}…`
                        : activeAgentRun.goal
                      : agentThread.length > 0
                        ? "Current agent run"
                        : "New agent run"
                    : active?.title || "New session"}
                </div>
                <div className="text-xs text-mute">
                  {mode === "agent"
                    ? activeAgentRun
                      ? `Run · ${formatSessionDate(activeAgentRun.created_at)}`
                      : "Tools: list / search docs, create_note (HITL)"
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
                    : "Upload PDF, DOCX, or text files, ingest until ready, then ask grounded questions here."
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

                      {/* Showcase: generative learning UI (product surface) */}
                      {!isUser &&
                        (() => {
                          const gen = extractGenerativeUIFromSteps(
                            item.liveSteps ?? item.run?.steps ?? [],
                          );
                          return gen ? (
                            <div className="mt-2 w-full max-w-[min(100%,36rem)]">
                              <GenerativeUIView
                                payload={gen}
                                onSaveAsNote={(t, b) =>
                                  void onSaveLearningNote(t, b)
                                }
                                savingNote={savingNote}
                              />
                            </div>
                          ) : null;
                        })()}

                      {/* LangSmith-style trace: mounts on Send, streams live */}
                      {!isUser && (item.run || item.pending) && (
                        <div className="mt-2 w-full max-w-[min(100%,40rem)]">
                          <AgentRunPanel
                            run={item.run}
                            pending={!!item.pending}
                            goal={item.goal || item.run?.goal}
                            liveSteps={item.liveSteps}
                            liveTokenUsage={item.liveTokenUsage}
                            liveLlmEvents={item.liveLlmEvents}
                            liveTrace={item.liveTrace}
                            approving={approving}
                            forceOpenWhilePending
                            onApprove={
                              item.run
                                ? () =>
                                    void onApproveAgent(
                                      item.id,
                                      item.run!.id,
                                      true,
                                    )
                                : undefined
                            }
                            onReject={
                              item.run
                                ? () =>
                                    void onApproveAgent(
                                      item.id,
                                      item.run!.id,
                                      false,
                                    )
                                : undefined
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
                  {sending
                    ? mode === "agent"
                      ? "Tracing…"
                      : "Sending…"
                    : "Send"}
                </Button>
              </div>
            </div>
          </form>
        </main>
      </div>
    </div>
  );
}
