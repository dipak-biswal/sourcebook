export type AgentType = "general";

export const AGENT_EXAMPLE_GOALS = [
  "Explain my documents simply with key points and a short FAQ.",
  "Search documents for the main themes and summarize in bullets.",
  "Analyze my resume for a senior full-stack AI role — compare skills to current market expectations.",
  "List all ready documents and describe what each file covers.",
  "Compare themes across my uploads in a scannable table.",
  "Create a note titled Demo Approval with body hello from HITL agent.",
];

export type AgentFormExample = { label: string; goal: string };

type WorkspaceLike = {
  name: string;
  description?: string | null;
  tags?: string[] | null;
};

type DocumentLike = { filename: string; status: string };

function shortFilename(filename: string): string {
  const base = filename.replace(/\.[^.]+$/, "");
  return base.length > 24 ? `${base.slice(0, 24)}…` : base;
}

function isResumeLike(filename: string): boolean {
  return /resume|cv|curriculum/i.test(filename);
}

function truncateLabel(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

/** Build agent goal examples from the selected workspace and its documents. */
export function buildWorkspaceAgentExamples(
  workspace: WorkspaceLike | null | undefined,
  documents: DocumentLike[],
): AgentFormExample[] {
  if (!workspace?.name?.trim()) return [];

  const name = workspace.name.trim();
  const description = workspace.description?.trim();
  const tags = (workspace.tags ?? []).map((t) => t.trim()).filter(Boolean);
  const readyDocs = documents.filter((d) => d.status === "ready");
  const examples: AgentFormExample[] = [];

  examples.push({
    label: "Explain documents",
    goal: description
      ? `Explain the documents in the "${name}" workspace (${description}) with key points and a short FAQ.`
      : `Explain the documents in the "${name}" workspace with key points and a short FAQ.`,
  });

  const resumeDoc = readyDocs.find((d) => isResumeLike(d.filename));
  if (resumeDoc) {
    examples.push({
      label: "Analyze resume",
      goal: `Analyze "${resumeDoc.filename}" in "${name}" for a senior full-stack role — compare skills to current market expectations.`,
    });
  } else if (readyDocs.length >= 2) {
    const sample = readyDocs
      .slice(0, 3)
      .map((d) => d.filename)
      .join(", ");
    examples.push({
      label: "Compare files",
      goal: `Compare themes across documents in "${name}" (${sample}) in a scannable summary.`,
    });
  } else if (readyDocs.length === 1) {
    examples.push({
      label: `Summarize ${shortFilename(readyDocs[0].filename)}`,
      goal: `Summarize "${readyDocs[0].filename}" in "${name}" with the main themes and key takeaways.`,
    });
  } else if (tags.length > 0) {
    examples.push({
      label: truncateLabel(tags[0]),
      goal: `Search documents in "${name}" for topics related to ${tags.join(", ")} and summarize findings.`,
    });
  } else {
    examples.push({
      label: "Search themes",
      goal: `Search documents in "${name}" for the main themes and summarize in bullets.`,
    });
  }

  if (readyDocs.length > 0 || documents.length > 0) {
    examples.push({
      label: "List documents",
      goal:
        readyDocs.length > 0
          ? `List all ready documents in "${name}" and describe what each file covers.`
          : `List all documents in "${name}" and describe what each file covers once ingest is complete.`,
    });
  }

  const seen = new Set<string>();
  const unique: AgentFormExample[] = [];
  for (const example of examples) {
    if (seen.has(example.goal)) continue;
    seen.add(example.goal);
    unique.push(example);
    if (unique.length >= 3) break;
  }
  return unique;
}

const TOOL_LABELS: Record<string, string> = {
  list_documents: "List documents",
  search_documents: "Search workspace",
  read_document: "Read document",
  web_search: "Web search",
  fetch_url: "Fetch web page",
  create_note: "Create note",
  generative_ui: "Visual summary",
  get_current_date: "Current date",
  plan_layout: "Plan layout",
  render_ui: "Render UI",
  ask_user: "Collect context",
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
  original_query?: string;
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
    original_query: raw.original_query ? String(raw.original_query) : undefined,
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

/** Workspace Context Agent HITL form (checkbox + text questions). */
export function isQuestionsPending(
  pending: PendingTool | null | undefined,
): boolean {
  if (!pending) return false;
  return pending.name === "ask_user" || pending.kind === "questions";
}

export type ContextQuestionOption = {
  id: string;
  label: string;
};

export type ContextQuestion = {
  id: string;
  prompt: string;
  input: "text" | "checkbox";
  required?: boolean;
  placeholder?: string;
  allow_multiple?: boolean;
  options?: ContextQuestionOption[];
};

export function parseContextQuestions(
  pending: PendingTool | null | undefined,
): {
  title: string;
  subtitle: string;
  questions: ContextQuestion[];
} | null {
  if (!isQuestionsPending(pending)) return null;
  const args = pending?.args ?? {};
  const raw = Array.isArray(args.questions) ? args.questions : [];
  const questions: ContextQuestion[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const q = item as Record<string, unknown>;
    const id = String(q.id ?? "").trim();
    const prompt = String(q.prompt ?? "").trim();
    if (!id || !prompt) continue;
    const input = q.input === "checkbox" ? "checkbox" : "text";
    const options: ContextQuestionOption[] = [];
    if (Array.isArray(q.options)) {
      for (const opt of q.options) {
        if (!opt || typeof opt !== "object") continue;
        const o = opt as Record<string, unknown>;
        const oid = String(o.id ?? "").trim();
        const label = String(o.label ?? oid).trim();
        if (oid && label) options.push({ id: oid, label });
      }
    }
    questions.push({
      id,
      prompt,
      input,
      required: Boolean(q.required),
      placeholder: q.placeholder ? String(q.placeholder) : undefined,
      allow_multiple: Boolean(q.allow_multiple),
      options: options.length ? options : undefined,
    });
  }
  if (!questions.length) return null;
  return {
    title: String(args.title ?? "A bit more context will improve the answer"),
    subtitle: String(
      args.subtitle ?? "Answer what you can — skip optional fields if unsure.",
    ),
    questions,
  };
}

export type ContextAnswers = Record<string, string | string[]>;

export function prettyJson(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}