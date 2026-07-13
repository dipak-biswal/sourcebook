import {
  ApiError,
  parseApiErrorBody,
  shouldRedirectToLogin,
} from "@/lib/api-errors";

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export { ApiError } from "@/lib/api-errors";

function failHttpResponse(status: number, text: string): never {
  if (status === 401) {
    setToken(null);
    if (shouldRedirectToLogin()) {
      window.location.replace("/login");
    }
  }
  throw new ApiError(parseApiErrorBody(text, status), status);
}

export function getToken(): string | null {
  return localStorage.getItem("sourcebook_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("sourcebook_token", token);
  else {
    localStorage.removeItem("sourcebook_token");
    localStorage.removeItem("sourcebook_user");
  }
}

export type UserProfile = {
  id: string;
  email: string;
};

export function getCachedUser(): UserProfile | null {
  try {
    const raw = localStorage.getItem("sourcebook_user");
    if (!raw) return null;
    return JSON.parse(raw) as UserProfile;
  } catch {
    return null;
  }
}

export function setCachedUser(user: UserProfile | null) {
  if (user) localStorage.setItem("sourcebook_user", JSON.stringify(user));
  else localStorage.removeItem("sourcebook_user");
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const text = await res.text();
    failHttpResponse(res.status, text || res.statusText);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export type TokenResponse = { access_token: string; token_type: string };

export type Workspace = { id: string; name: string; role: string };

export type Document = {
  id: string;
  workspace_id: string;
  filename: string;
  content_type: string | null;
  status: string;
  error?: string | null;
  created_at: string;
};

export type Conversation = {
  id: string;
  workspace_id: string;
  user_id: string;
  title: string;
  created_at: string;
};

export type Citation = {
  index?: number;
  chunk_id?: string;
  document_id?: string;
  filename?: string | null;
  score?: number;
  snippet?: string;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  citations?: Citation[];
  created_at: string;
};

export type ChatResponse = {
  conversation_id: string;
  message: string;
  citations?: Array<Record<string, unknown>>;
};

export type StreamChatHandlers = {
  onToken?: (text: string) => void;
  onCitations?: (citations: Array<Record<string, unknown>>) => void;
  onDone?: () => void;
  onError?: (detail: string) => void;
};

const SSE_TIMEOUT_MS = 30_000;

async function consumeSSE(url: string, body: Record<string, unknown>, onEvent: (payload: Record<string, unknown>) => void): Promise<void> {
  const token = getToken();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), SSE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${url}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const text = await res.text();
      failHttpResponse(res.status, text || res.statusText);
    }
    if (!res.body) throw new Error("No response body for stream");

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part
          .split("\n")
          .map((l) => l.trim())
          .find((l) => l.startsWith("data:"));
        if (!line) continue;
        const raw = line.replace(/^data:\s*/, "");
        if (!raw || raw === "[DONE]") continue;

        let payload: Record<string, unknown>;
        try {
          payload = JSON.parse(raw) as Record<string, unknown>;
        } catch {
          continue;
        }
        onEvent(payload);
      }
    }
  } finally {
    clearTimeout(timer);
  }
}

/** Consume POST /chat/stream (SSE). */
export async function streamChat(
  conversationId: string,
  message: string,
  handlers: StreamChatHandlers = {},
): Promise<void> {
  await consumeSSE("/chat/stream", { conversation_id: conversationId, message }, (payload) => {
    const type = String(payload.type || "");
    if (type === "token" && payload.content) {
      handlers.onToken?.(String(payload.content));
    } else if (type === "citations" && payload.citations) {
      handlers.onCitations?.(payload.citations as Array<Record<string, unknown>>);
    } else if (type === "done") {
      handlers.onDone?.();
    } else if (type === "error") {
      const detail = String(payload.detail || "Stream error");
      handlers.onError?.(detail);
      throw new Error(detail);
    }
  });
}

export const api = {
  login: (email: string, password: string) =>
    request<TokenResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    request<TokenResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  /** Current authenticated user (email for profile menu). */
  me: async () => {
    const user = await request<UserProfile>("/me");
    setCachedUser(user);
    return user;
  },

  workspaces: () => request<Workspace[]>("/workspaces"),

  documents: (workspaceId: string) =>
    request<Document[]>(`/documents?workspace_id=${workspaceId}`),

  upload: (workspaceId: string, file: File) => {
    const form = new FormData();
    form.append("workspace_id", workspaceId);
    form.append("file", file);
    return request<Document>("/documents", {
      method: "POST",
      body: form,
    });
  },

  deleteDocument: (id: string) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }),

  ingestDocument: (id: string) =>
    request<Document>(`/documents/${id}/ingest`, { method: "POST" }),

  createConversation: (workspaceId: string, title = "New chat") =>
    request<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId, title }),
    }),

  conversations: (workspaceId: string) =>
    request<Conversation[]>(`/conversations?workspace_id=${workspaceId}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),

  messages: (conversationId: string) =>
    request<ChatMessage[]>(`/conversations/${conversationId}/messages`),

  chat: (conversationId: string, message: string) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: conversationId,
        message,
      }),
    }),

  suggestQuestions: (workspaceId: string) =>
    request<{ questions: string[] }>("/chat/suggestions", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId }),
    }),

  /** Streaming chat (preferred for UI). */
  chatStream: streamChat,

  usageSummary: () => request<UsageSummary>("/usage/summary"),

  usageEvents: (limit = 50) =>
    request<UsageEventRow[]>(`/usage/events?limit=${limit}`),

  usageEventDetail: (eventId: string) =>
    request<UsageEventDetail>(`/usage/events/${eventId}`),

  deleteUsageEvent: (eventId: string) =>
    request<void>(`/usage/events/${eventId}`, { method: "DELETE" }),

  deleteAllUsageEvents: () =>
    request<void>("/usage/events", { method: "DELETE" }),

  startAgentRun: (
    workspaceId: string,
    goal: string,
    options: { maxSteps?: number; agentType?: "general" | "study_guide" } = {},
  ) =>
    request<AgentRun>("/agents/runs", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: workspaceId,
        goal,
        max_steps: options.maxSteps,
        agent_type: options.agentType ?? "general",
      }),
    }),

  /** LangSmith-style live agent trace (SSE). */
  startAgentRunStream: (
    workspaceId: string,
    goal: string,
    handlers: AgentStreamHandlers = {},
    options: { maxSteps?: number; agentType?: "general" | "study_guide" } = {},
  ) =>
    streamAgentRun(
      "/agents/runs/stream",
      {
        workspace_id: workspaceId,
        goal,
        max_steps: options.maxSteps,
        agent_type: options.agentType ?? "general",
      },
      handlers,
    ),

  agentRuns: (
    workspaceId: string,
    agentType?: "general" | "study_guide",
  ) => {
    const params = new URLSearchParams({ workspace_id: workspaceId });
    if (agentType) params.set("agent_type", agentType);
    return request<AgentRun[]>(`/agents/runs?${params.toString()}`);
  },

  agentRun: (runId: string) => request<AgentRun>(`/agents/runs/${runId}`),

  deleteAgentRun: (runId: string) =>
    request<void>(`/agents/runs/${runId}`, { method: "DELETE" }),

  approveAgentRun: (runId: string, approve: boolean) =>
    request<AgentRun>(`/agents/runs/${runId}/approve`, {
      method: "POST",
      body: JSON.stringify({ approve }),
    }),

  approveAgentRunStream: (
    runId: string,
    approve: boolean,
    handlers: AgentStreamHandlers = {},
  ) =>
    streamAgentRun(
      `/agents/runs/${runId}/approve/stream`,
      { approve },
      handlers,
    ),

  notes: (workspaceId: string) =>
    request<Note[]>(`/notes?workspace_id=${workspaceId}`),

  deleteNote: (noteId: string) =>
    request<void>(`/notes/${noteId}`, { method: "DELETE" }),

  updateProfile: (email: string) =>
    request<UserProfile>("/me", {
      method: "PUT",
      body: JSON.stringify({ email }),
    }),

  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>("/me/password", {
      method: "PUT",
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  createWorkspace: (name: string) =>
    request<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),

  updateWorkspace: (id: string, name: string) =>
    request<Workspace>(`/workspaces/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),

  deleteWorkspace: (id: string) =>
    request<void>(`/workspaces/${id}`, { method: "DELETE" }),

  getNote: (noteId: string) =>
    request<Note>(`/notes/${noteId}`),

  updateNote: (noteId: string, title: string, body: string) =>
    request<Note>(`/notes/${noteId}`, {
      method: "PUT",
      body: JSON.stringify({ title, body }),
    }),

  /** Dev-only testing helpers (require DEV_MODE on API). */
  devUsers: () => request<DevUserList>("/dev/users"),

  devSetPassword: (email: string, password = "password123") =>
    request<{ email: string; password: string; message: string }>(
      "/dev/users/set-password",
      {
        method: "POST",
        body: JSON.stringify({ email, password }),
      },
    ),

  devSetAllPasswords: (password = "password123") =>
    request<{ password: string; updated: string[]; message: string }>(
      `/dev/users/set-all-passwords?password=${encodeURIComponent(password)}`,
      { method: "POST" },
    ),
};

export type DevUserRow = {
  id: string;
  email: string;
  created_at: string | null;
  test_password: string | null;
  password_note: string;
};

export type DevUserList = {
  dev_mode: boolean;
  warning: string;
  default_test_password: string;
  users: DevUserRow[];
};

export type UsageEventRow = {
  id: string;
  kind: string;
  model: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  meta?: Record<string, unknown> | null;
  created_at: string;
};

export type UsageSummary = {
  event_count: number;
  total_tokens: number;
  by_kind: Record<string, number>;
  recent: UsageEventRow[];
  daily_totals: DailyTotal[];
};

export type UsageEventDetail = {
  kind: string;
  goal: string | null;
  steps: { type: string; tool_name?: string | null; input?: Record<string, unknown> | string | null; output?: Record<string, unknown> | string | null }[];
  final_answer: string | null;
  token_usage: number | null;
  user_message: string | null;
  assistant_message: string | null;
  citations: string[];
  meta: Record<string, unknown> | null;
};

export type DailyTotal = {
  date: string;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  event_count: number;
};

export type AgentStep = {
  id: string;
  step_index: number;
  type: string;
  tool_name: string | null;
  input?: unknown;
  output?: unknown;
  created_at: string;
  duration_ms?: number | null;
};

export type AgentRun = {
  id: string;
  workspace_id: string;
  user_id: string | null;
  goal: string;
  agent_type?: "general" | "study_guide";
  status: string;
  final_answer: string | null;
  error: string | null;
  token_usage: number | null;
  pending_tool?: {
    id?: string;
    name?: string;
    args?: Record<string, unknown>;
  } | null;
  created_at: string;
  steps: AgentStep[];
};

export type AgentStreamHandlers = {
  onRunStart?: (payload: {
    run_id?: string;
    goal?: string;
    status?: string;
  }) => void;
  onLlmStart?: (payload: Record<string, unknown>) => void;
  onLlmEnd?: (payload: {
    duration_ms?: number;
    prompt_tokens?: number;
    completion_tokens?: number;
    total_tokens?: number;
    token_usage_so_far?: number;
    has_tool_calls?: boolean;
  }) => void;
  onStep?: (step: AgentStep) => void;
  onStatus?: (payload: {
    status?: string;
    token_usage?: number | null;
    final_answer?: string | null;
    pending_tool?: AgentRun["pending_tool"];
  }) => void;
  onDone?: (run: AgentRun) => void;
  onError?: (detail: string) => void;
  onToolStart?: (payload: {
    tool_name: string;
    tool_args?: Record<string, unknown>;
    call_id?: string;
  }) => void;
  onLoopWarning?: (payload: { message: string }) => void;
};

async function streamAgentRun(
  path: string,
  body: Record<string, unknown>,
  handlers: AgentStreamHandlers,
): Promise<AgentRun | null> {
  let finalRun: AgentRun | null = null;
  await consumeSSE(path, body, (payload) => {
    const type = String(payload.type || "");
    if (type === "run_start") {
      handlers.onRunStart?.({
        run_id: payload.run_id as string | undefined,
        goal: payload.goal as string | undefined,
        status: payload.status as string | undefined,
      });
    } else if (type === "llm_start") {
      handlers.onLlmStart?.(payload);
    } else if (type === "llm_end") {
      handlers.onLlmEnd?.({
        duration_ms: payload.duration_ms as number | undefined,
        prompt_tokens: payload.prompt_tokens as number | undefined,
        completion_tokens: payload.completion_tokens as number | undefined,
        total_tokens: payload.total_tokens as number | undefined,
        token_usage_so_far: payload.token_usage_so_far as number | undefined,
        has_tool_calls: payload.has_tool_calls as boolean | undefined,
      });
    } else if (type === "step" && payload.step) {
      handlers.onStep?.(payload.step as AgentStep);
    } else if (type === "tool_start") {
      handlers.onToolStart?.({
        tool_name: payload.tool_name as string,
        tool_args: payload.tool_args as Record<string, unknown> | undefined,
        call_id: payload.call_id as string | undefined,
      });
    } else if (type === "loop_warning") {
      handlers.onLoopWarning?.({ message: payload.message as string });
    } else if (type === "status") {
      handlers.onStatus?.({
        status: payload.status as string | undefined,
        token_usage: (payload.token_usage as number | null | undefined) ?? null,
        final_answer: (payload.final_answer as string | null | undefined) ?? null,
        pending_tool: payload.pending_tool as AgentRun["pending_tool"],
      });
    } else if (type === "done" && payload.run) {
      finalRun = payload.run as AgentRun;
      handlers.onDone?.(finalRun);
    } else if (type === "error") {
      const detail = String(payload.detail || "Agent stream error");
      handlers.onError?.(detail);
      throw new Error(detail);
    }
  });
  return finalRun;
}

export type Note = {
  id: string;
  workspace_id: string;
  user_id: string | null;
  title: string;
  body: string;
  created_at: string;
};
