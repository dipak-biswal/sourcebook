const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export function getToken(): string | null {
  return localStorage.getItem("sourcebook_token");
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("sourcebook_token", token);
  else localStorage.removeItem("sourcebook_token");
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
    throw new Error(text || res.statusText);
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
  created_at: string;
};

export type Conversation = {
  id: string;
  workspace_id: string;
  user_id: string;
  title: string;
  created_at: string;
};

export type ChatMessage = {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  citations?: unknown;
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

/** Consume POST /chat/stream (SSE). */
export async function streamChat(
  conversationId: string,
  message: string,
  handlers: StreamChatHandlers = {},
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (!res.body) {
    throw new Error("No response body for stream");
  }

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

      let payload: {
        type?: string;
        content?: string;
        citations?: Array<Record<string, unknown>>;
        detail?: string;
      };
      try {
        payload = JSON.parse(raw) as typeof payload;
      } catch {
        continue;
      }

      if (payload.type === "token" && payload.content) {
        handlers.onToken?.(payload.content);
      } else if (payload.type === "citations" && payload.citations) {
        handlers.onCitations?.(payload.citations);
      } else if (payload.type === "done") {
        handlers.onDone?.();
      } else if (payload.type === "error") {
        handlers.onError?.(payload.detail || "Stream error");
        throw new Error(payload.detail || "Stream error");
      }
    }
  }
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

  /** Streaming chat (preferred for UI). */
  chatStream: streamChat,

  usageSummary: () => request<UsageSummary>("/usage/summary"),

  usageEvents: (limit = 50) =>
    request<UsageEventRow[]>(`/usage/events?limit=${limit}`),

  startAgentRun: (workspaceId: string, goal: string, maxSteps = 5) =>
    request<AgentRun>("/agents/runs", {
      method: "POST",
      body: JSON.stringify({
        workspace_id: workspaceId,
        goal,
        max_steps: maxSteps,
      }),
    }),

  agentRuns: (workspaceId: string) =>
    request<AgentRun[]>(`/agents/runs?workspace_id=${workspaceId}`),

  agentRun: (runId: string) => request<AgentRun>(`/agents/runs/${runId}`),
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
};

export type AgentStep = {
  id: string;
  step_index: number;
  type: string;
  tool_name: string | null;
  input?: unknown;
  output?: unknown;
  created_at: string;
};

export type AgentRun = {
  id: string;
  workspace_id: string;
  user_id: string;
  goal: string;
  status: string;
  final_answer: string | null;
  error: string | null;
  token_usage: number | null;
  created_at: string;
  steps: AgentStep[];
};
