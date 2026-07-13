export type AgentType = "general" | "study_guide";

export const AGENT_EXAMPLE_GOALS = [
  "Search documents for the main themes and summarize in bullets.",
  "List all ready documents and describe what each file covers.",
  "Create a note titled Demo Approval with body hello from HITL agent.",
];

export const STUDY_GUIDE_EXAMPLE_GOALS = [
  "Explain my documents simply with key points and a short FAQ for beginners.",
  "List documents, then explain the first ready file simply with citations.",
  "Make a study guide with glossary and key terms from my uploads.",
  "Summarize the onboarding PDF with steps and a short FAQ.",
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

export function prettyJson(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}


