export type AgentType = "general";

export const AGENT_EXAMPLE_GOALS = [
  "Explain my documents simply with key points and a short FAQ.",
  "Search documents for the main themes and summarize in bullets.",
  "Analyze my resume for a senior full-stack AI role — compare skills to current market expectations.",
  "List all ready documents and describe what each file covers.",
  "Compare themes across my uploads in a scannable table.",
  "Create a note titled Demo Approval with body hello from HITL agent.",
];

const TOOL_LABELS: Record<string, string> = {
  list_documents: "List documents",
  search_documents: "Search workspace",
  web_search: "Web search",
  create_note: "Create note",
  generative_ui: "Visual summary",
};

export function toolDisplayName(toolName: string | null | undefined): string {
  if (!toolName) return "Tool";
  return TOOL_LABELS[toolName] ?? toolName.replaceAll("_", " ");
}

export type WebSearchHit = {
  title: string;
  url?: string;
  snippet?: string;
};

export type WebSearchOutput = {
  query?: string;
  results?: WebSearchHit[];
  result_count?: number;
  error?: string;
};

export function parseWebSearchOutput(value: unknown): WebSearchOutput | null {
  if (!value || typeof value !== "object") return null;
  const raw = value as Record<string, unknown>;
  if (!("results" in raw) && !raw.error) return null;
  const results = Array.isArray(raw.results)
    ? raw.results
        .filter((r): r is Record<string, unknown> => !!r && typeof r === "object")
        .map((r) => ({
          title: String(r.title ?? r.url ?? "Untitled"),
          url: r.url ? String(r.url) : undefined,
          snippet: r.snippet ? String(r.snippet) : undefined,
        }))
    : [];
  return {
    query: raw.query ? String(raw.query) : undefined,
    results,
    result_count:
      typeof raw.result_count === "number" ? raw.result_count : results.length,
    error: raw.error ? String(raw.error) : undefined,
  };
}

export function agentStatusVariant(
  status: string,
): "success" | "warning" | "danger" | "secondary" | "outline" {
  switch (status) {
    case "completed":
      return "success";
    case "running":
    case "waiting_approval":
      return "warning";
    case "failed":
    case "cancelled":
      return "danger";
    default:
      return "secondary";
  }
}

export type PendingTool = {
  id?: string;
  name?: string;
  kind?: string;
  args?: Record<string, unknown>;
};

export function isPresentationPending(
  pending: PendingTool | null | undefined,
): boolean {
  if (!pending) return false;
  return pending.name === "generative_ui" || pending.kind === "presentation";
}

export function prettyJson(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}