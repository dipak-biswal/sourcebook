export const SUGGESTED_WORKSPACE_TAGS = [
  "learning",
  "hiring",
  "product",
  "research",
  "personal",
  "reference",
  "writing",
] as const;

export const WORKSPACE_DESCRIPTION_TEMPLATE =
  "This workspace is for [purpose].\nI want Sourcebook to help me [outcome].\nAudience: [me | my team | client].\nSuccess looks like: [what I can do after a run].";

export function parseTagInput(value: string): string[] {
  return value
    .split(",")
    .map((t) => t.trim())
    .filter(Boolean);
}

export function toggleTagInInput(current: string, tag: string): string {
  const tags = parseTagInput(current);
  const next = tags.includes(tag)
    ? tags.filter((t) => t !== tag)
    : [...tags, tag];
  return next.join(", ");
}