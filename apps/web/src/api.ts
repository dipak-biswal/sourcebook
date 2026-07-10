const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000"

export function getToken(): string | null {
  return localStorage.getItem("sourcebook_token")
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem("sourcebook_token", token)
  else localStorage.removeItem("sourcebook_token")
}

async function request<T>(path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set("Authorization", `Bearer ${token}`)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json")
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers })

  if (!res.ok) {
    const text = await res.text()

    throw new Error(text || res.statusText)
  }

  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export type TokenResponse = { access_token: string, token_type: string };

export type Workspace = { id: string, name: string, role: string };

export type Document = {
  id: string
  workspace_id: string
  filename: string
  content_type: string | null
  status: string
  created_at: string
};

export const api = {
  login: (email: string, password: string) => request<TokenResponse>(
    "/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password })
  }
  ),
  register: (email: string, password: string) => request<TokenResponse>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password })
  }),

  workspaces: () => request<Workspace[]>("/workspaces"),
  documents: (workspaceId: string) => request<Document[]>(`/documents?workspace_id=${workspaceId}`),
  upload: (workspaceId: string, file: File) => {
    const form = new FormData()
    form.append("workspace_id", workspaceId)
    form.append("file", file)
    return request<Document>("/documents", {
      method: "POST",
      body: form
    })
  },
  deleteDocument: (id: string) =>
    request<void>(`/documents/${id}`, { method: "DELETE" }),
};
