export type AgentType = "general";

export const AGENT_EXAMPLE_GOALS = [
  "Explain my documents simply with key points and a short FAQ.",
  "Search documents for the main themes and summarize in bullets.",
  "List all ready documents and describe what each file covers.",
  "Compare themes across my uploads in a scannable table.",
  "Create a note titled Demo Approval with body hello from HITL agent.",
];

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