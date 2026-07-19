export type GenUIMeasure = {
  label: string;
  value: string;
  unit?: string | null;
  numeric?: number | null;
};

export type GenUIBlock = {
  type: string;
  title?: string | null;
  body?: string | null;
  items?: string[] | null;
  terms?: { term: string; definition: string }[] | null;
  faqs?: { question: string; answer: string }[] | null;
  tags?: string[] | null;
  /** Structured rows for metrics/progress/chart, derived server-side from items. */
  measures?: GenUIMeasure[] | null;
  source_indices?: number[] | null;
  /** Layout hint honored by the grid. Backend may set it; otherwise defaulted per type. */
  width?: "full" | "half" | null;
};

export type GenUISource = {
  index: number;
  chunk_id?: string;
  document_id?: string;
  filename?: string | null;
  score?: number | null;
  snippet?: string;
};

export type GenerativeUIPayload = {
  type: "generative_ui";
  title: string;
  plain_summary?: string;
  presentation_profile?: string;
  version?: number;
  blocks?: GenUIBlock[];
  source_files?: string[];
  sources?: GenUISource[];
  document_id?: string | null;
  document_filename?: string | null;
};

export function isGenerativeUI(value: unknown): value is GenerativeUIPayload {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return v.type === "generative_ui" && typeof v.title === "string";
}

function looksLikeGenerativePayload(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return typeof v.title === "string" && Array.isArray(v.blocks);
}

function coerceGenerativeUIPayload(
  raw: Record<string, unknown>,
): GenerativeUIPayload {
  return normalizeGenerativeUI({
    type: "generative_ui",
    title: String(raw.title),
    plain_summary:
      typeof raw.plain_summary === "string"
        ? raw.plain_summary
        : typeof raw.summary === "string"
          ? raw.summary
          : undefined,
    presentation_profile:
      typeof raw.presentation_profile === "string"
        ? raw.presentation_profile
        : undefined,
    blocks: (raw.blocks ?? []) as GenUIBlock[],
    source_files: Array.isArray(raw.source_files)
      ? (raw.source_files as string[])
      : undefined,
    sources: Array.isArray(raw.sources)
      ? (raw.sources as GenerativeUIPayload["sources"])
      : undefined,
    document_id:
      typeof raw.document_id === "string" ? raw.document_id : undefined,
    document_filename:
      typeof raw.document_filename === "string"
        ? raw.document_filename
        : undefined,
  });
}

function stripJsonFences(raw: string): string {
  return raw
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function parseJsonGenerativeUI(raw: string): GenerativeUIPayload | null {
  const trimmed = stripJsonFences(raw);
  if (!trimmed.startsWith("{")) return null;
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    return extractFromValue(parsed);
  } catch {
    return null;
  }
}

function blockContentScore(block: GenUIBlock): number {
  const anyB = block as GenUIBlock & Record<string, unknown>;
  let score = 0;
  if (block.body?.trim()) score += 2;
  if (block.items?.length) score += block.items.length * 2;
  if (block.terms?.length) score += block.terms.length * 2;
  if (block.faqs?.length) score += block.faqs.length * 2;
  if (typeof anyB.data === "string" && anyB.data.trim()) score += 4;
  if (Array.isArray(anyB.data) && anyB.data.length) score += anyB.data.length * 2;
  if (block.type === "table" && coerceTableRows(block).length) score += 4;
  return score;
}

function payloadContentScore(payload: GenerativeUIPayload): number {
  return (payload.blocks ?? []).reduce(
    (sum, block) => sum + blockContentScore(block),
    payload.plain_summary?.trim() ? 1 : 0,
  );
}

function pickRicherGenerativeUI(
  primary: GenerativeUIPayload | null,
  secondary: GenerativeUIPayload | null,
): GenerativeUIPayload | null {
  if (!primary) return secondary;
  if (!secondary) return primary;
  return payloadContentScore(secondary) > payloadContentScore(primary)
    ? secondary
    : primary;
}

type RunStep = {
  type: string;
  tool_name?: string | null;
  input?: unknown;
  output?: unknown;
};

function extractLlmOutputGenerativeUI(steps: RunStep[]): GenerativeUIPayload | null {
  let best: GenerativeUIPayload | null = null;

  for (let i = steps.length - 1; i >= 0; i--) {
    const step = steps[i];
    const candidates: string[] = [];

    if (step.type === "tool_result" && step.tool_name === "render_ui") {
      const out = step.output as Record<string, unknown> | undefined;
      if (typeof out?.llm_output === "string") candidates.push(out.llm_output);
    }

    if (step.type === "presentation") {
      const input = step.input as Record<string, unknown> | undefined;
      if (typeof input?.llm_output === "string") candidates.push(input.llm_output);
    }

    for (const raw of candidates) {
      const parsed = parseJsonGenerativeUI(raw);
      best = pickRicherGenerativeUI(best, parsed);
    }
  }

  return best;
}

function cleanCellText(text: string): string {
  let s = text.trim();
  s = s.replace(/^\d+[.)]\s+/, "");
  s = s.replace(/^[-•*]\s+/, "");
  s = s.replace(/\*\*([^*]+)\*\*/g, "$1");
  s = s.replace(/__([^_]+)__/g, "$1");
  s = s.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, "$1");
  s = s.replace(/`([^`]+)`/g, "$1");
  s = s.replace(/\*\*/g, "");
  return s.trim();
}

/** Strip markdown/list markers from render-engine strings for card UI. */
export function cleanDisplayText(text: string): string {
  if (text.includes("\n")) {
    return text
      .split("\n")
      .map((line) => cleanDisplayText(line))
      .join("\n");
  }
  if (text.includes("|")) {
    return text
      .split("|")
      .map((part) => cleanCellText(part))
      .join(" | ");
  }
  return cleanCellText(text);
}

function isSeparatorText(text: string): boolean {
  const s = text.trim();
  if (!s) return false;
  if (/^[\s\-:|]+$/.test(s)) return true;
  if (s.includes("|")) {
    const parts = s.split("|").map((p) => p.trim()).filter(Boolean);
    if (parts.length > 0 && parts.every((p) => /^[\s\-:]+$/.test(p))) {
      return true;
    }
  }
  return false;
}

function isSeparatorCells(cells: string[]): boolean {
  const nonEmpty = cells.map((c) => c.trim()).filter(Boolean);
  if (!nonEmpty.length) return false;
  return nonEmpty.every((c) => /^[\s\-:]+$/.test(c));
}

function filterTableRows(rows: string[][]): string[][] {
  return rows.filter((cells) => !isSeparatorCells(cells));
}

function splitDelimitedRow(text: string): string[] {
  const s = text.trim();
  if (!s) return [];
  if (s.includes("|")) return s.split("|").map((c) => c.trim());
  if (s.includes("\t")) return s.split("\t").map((c) => c.trim());
  if (s.includes(" · ")) return s.split(" · ").map((c) => c.trim());
  if (s.includes(" — ")) return s.split(" — ").map((c) => c.trim());
  const commas = s.split(",").map((c) => c.trim()).filter(Boolean);
  if (commas.length >= 2 && commas.length <= 8) return commas;
  return [s];
}

function rowToCells(row: unknown): string[] {
  if (typeof row === "string") {
    return splitDelimitedRow(row);
  }
  if (Array.isArray(row)) {
    return row.map((c) => String(c ?? "").trim()).filter(Boolean);
  }
  if (row && typeof row === "object") {
    const o = row as Record<string, unknown>;
    if (Array.isArray(o.cells)) {
      return o.cells.map((c) => String(c ?? "").trim());
    }
    const skip = new Set(["source_indices", "tags", "type", "id"]);
    return Object.entries(o)
      .filter(([k]) => !skip.has(k))
      .map(([, v]) => String(v ?? "").trim());
  }
  return [];
}

function parseMarkdownTableBody(body: string): string[][] {
  const rows: string[][] = [];
  for (const line of body.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.includes("|")) continue;
    if (isSeparatorText(trimmed)) continue;
    let parts = trimmed.split("|").map((c) => c.trim());
    if (parts[0] === "") parts = parts.slice(1);
    if (parts[parts.length - 1] === "") parts = parts.slice(0, -1);
    if (parts.length) rows.push(parts);
  }
  return rows;
}

function padTableRows(rows: string[][]): string[][] {
  const cols = Math.max(...rows.map((r) => r.length), 1);
  return rows.map((r) => {
    const out = [...r];
    while (out.length < cols) out.push("");
    return out.slice(0, cols);
  });
}

function finalizeTableRows(rows: string[][]): string[][] {
  return filterTableRows(padTableRows(rows));
}

function objectRowsToTable(rows: Record<string, unknown>[]): string[][] {
  if (!rows.length) return [];
  const skip = new Set(["source_indices", "tags", "type", "id"]);
  const keys = Object.keys(rows[0]).filter((k) => !skip.has(k));
  if (!keys.length) return [];
  const header = keys.map((k) => k.replace(/_/g, " "));
  const body = rows.map((row) =>
    keys.map((k) => String(row[k] ?? "").trim()),
  );
  return padTableRows([header, ...body]);
}

function itemsToRowMatrix(items: string[]): string[][] {
  if (items.length === 1 && items[0].includes("\n")) {
    const lines = items[0]
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    const rows = filterTableRows(
      lines
        .filter((l) => !isSeparatorText(l))
        .map(splitDelimitedRow)
        .filter((r) => r.length),
    );
    if (rows.length) return finalizeTableRows(rows);
  }
  return filterTableRows(
    items
      .filter((item) => !isSeparatorText(item))
      .map(splitDelimitedRow)
      .filter((r) => r.length),
  );
}

/** Normalize table blocks from pipes, markdown body, or row objects. */
const QUALITATIVE_LEVELS: Record<string, { pct: number; label: string }> = {
  expert: { pct: 92, label: "Expert" },
  strong: { pct: 82, label: "Strong" },
  advanced: { pct: 78, label: "Advanced" },
  proficient: { pct: 72, label: "Proficient" },
  solid: { pct: 68, label: "Solid" },
  diverse: { pct: 65, label: "Diverse" },
  moderate: { pct: 55, label: "Moderate" },
  growing: { pct: 52, label: "Growing" },
  developing: { pct: 48, label: "Developing" },
  foundational: { pct: 42, label: "Foundational" },
  basic: { pct: 38, label: "Basic" },
  gap: { pct: 28, label: "Gap" },
  weak: { pct: 22, label: "Weak" },
  lacking: { pct: 18, label: "Lacking" },
};

export type ProgressDisplay = {
  pct: number;
  display: string;
  qualitative: boolean;
};

/** Map progress/chart values to bar width; prefer qualitative labels over fake %. */
export function parseProgressValue(raw: string): ProgressDisplay {
  const trimmed = (raw || "").trim();
  if (!trimmed || isSeparatorText(trimmed)) {
    return { pct: 0, display: "—", qualitative: true };
  }

  const lower = trimmed.toLowerCase();
  for (const [key, meta] of Object.entries(QUALITATIVE_LEVELS)) {
    if (lower === key || lower.includes(key)) {
      return { pct: meta.pct, display: meta.label, qualitative: true };
    }
  }

  const hasExplicitPercent = /%/.test(trimmed);
  const isBareNumber = /^\d{1,3}$/.test(trimmed);
  if (hasExplicitPercent || isBareNumber) {
    const pct = parseInt(trimmed.replace("%", ""), 10);
    const safe = Math.min(100, Math.max(0, pct));
    return { pct: safe, display: `${safe}%`, qualitative: false };
  }

  return { pct: 50, display: trimmed, qualitative: true };
}

export function coerceTableRows(block: GenUIBlock): string[][] {
  const anyB = block as GenUIBlock & Record<string, unknown>;

  if (block.items?.length) {
    const matrix = itemsToRowMatrix(block.items);
    const multiCol = matrix.filter((r) => r.length > 1);
    if (multiCol.length >= 2) return finalizeTableRows(matrix);
    if (multiCol.length === 1 && matrix.length >= 2) return finalizeTableRows(matrix);
  }

  if (Array.isArray(anyB.headers) && anyB.headers.length) {
    const header = (anyB.headers as unknown[]).map((h) => String(h).trim());
    const bodyRaw = anyB.rows ?? anyB.data ?? block.items ?? [];
    if (Array.isArray(bodyRaw) && bodyRaw.length) {
      const body = bodyRaw
        .map(rowToCells)
        .filter((r) => r.length);
      if (body.length) return finalizeTableRows([header, ...body]);
    }
  }

  const dataField = anyB.data;
  if (typeof dataField === "string" && dataField.includes("|")) {
    const md = parseMarkdownTableBody(dataField);
    if (md.length) return finalizeTableRows(md);
  }
  const rowsRaw =
    anyB.rows ??
    (typeof dataField === "string" ? undefined : dataField) ??
    anyB.table;
  if (
    Array.isArray(rowsRaw) &&
    rowsRaw.length &&
    rowsRaw.every((r) => r && typeof r === "object" && !Array.isArray(r))
  ) {
    const table = objectRowsToTable(rowsRaw as Record<string, unknown>[]);
    if (table.length) return filterTableRows(table);
  }

  const fromItems = (block.items ?? [])
    .filter((item) => !isSeparatorText(String(item)))
    .map(rowToCells)
    .filter((r) => r.length);
  const rawItems = block.items as unknown;
  if (
    Array.isArray(rawItems) &&
    rawItems.length &&
    rawItems.every((x) => x && typeof x === "object" && !Array.isArray(x))
  ) {
    const table = objectRowsToTable(rawItems as Record<string, unknown>[]);
    if (table.length) return filterTableRows(table);
  }
  if (fromItems.some((r) => r.length > 1)) {
    return finalizeTableRows(fromItems);
  }

  if (Array.isArray(rowsRaw) && rowsRaw.length) {
    const parsed = rowsRaw.map(rowToCells).filter((r) => r.length);
    if (parsed.some((r) => r.length > 1)) {
      return finalizeTableRows(parsed);
    }
  }

  if (block.body?.includes("|")) {
    const md = parseMarkdownTableBody(block.body);
    if (md.length) return finalizeTableRows(md);
  }

  if (fromItems.length) return finalizeTableRows(fromItems);
  return [];
}

function asStringList(value: unknown): string[] {
  if (!value) return [];
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const x of value) {
    if (typeof x === "string" && x.trim()) out.push(x.trim());
    else if (x && typeof x === "object") {
      const o = x as Record<string, unknown>;
      for (const k of ["text", "point", "item", "content", "value"]) {
        if (typeof o[k] === "string" && (o[k] as string).trim()) {
          out.push((o[k] as string).trim());
          break;
        }
      }
    }
  }
  return out;
}

function firstStringList(...values: unknown[]): string[] | undefined {
  for (const value of values) {
    const list = asStringList(value);
    if (list.length) return list.map(cleanDisplayText);
  }
  return undefined;
}

function cleanBlockFields(block: GenUIBlock): GenUIBlock {
  const items = block.items
    ?.filter((item) => !isSeparatorText(item))
    .map(cleanDisplayText);
  return {
    ...block,
    title: block.title ? cleanDisplayText(block.title) : block.title,
    body: block.body ? cleanDisplayText(block.body) : block.body,
    items,
    terms: block.terms?.map((t) => ({
      term: cleanDisplayText(t.term),
      definition: cleanDisplayText(t.definition),
    })),
    faqs: block.faqs?.map((f) => ({
      question: cleanDisplayText(f.question),
      answer: cleanDisplayText(f.answer),
    })),
  };
}

export function normalizeGenerativeUI(raw: GenerativeUIPayload): GenerativeUIPayload {
  const blocks = (raw.blocks ?? []).map((b) => {
    const anyB = b as GenUIBlock & Record<string, unknown>;
    const body =
      b.body ||
      (typeof anyB.content === "string" ? anyB.content : null) ||
      (typeof anyB.text === "string" ? anyB.text : null) ||
      (typeof anyB.description === "string" ? anyB.description : null);

    let items = firstStringList(
      b.items,
      anyB.points,
      anyB.bullets,
      anyB.key_points,
      anyB.steps,
      anyB.data,
    );

    const dataStr =
      typeof anyB.data === "string" && anyB.data.trim() ? anyB.data.trim() : null;

    if (b.type === "table") {
      const coerced = coerceTableRows({
        ...b,
        items: items ?? b.items,
        body: body || b.body || dataStr || undefined,
      });
      if (coerced.length) {
        items = coerced.map((row) =>
          row.map(cleanCellText).join(" | "),
        );
      }
    }

    if (
      (b.type === "progress" || b.type === "chart" || b.type === "metrics") &&
      (!items || !items.length) &&
      dataStr
    ) {
      items = dataStr.split("\n").map((l) => l.trim()).filter(Boolean);
    }

    let terms = b.terms;
    if ((!terms || !terms.length) && Array.isArray(anyB.glossary)) {
      terms = (anyB.glossary as Record<string, unknown>[])
        .map((t) => ({
          term: String(t.term ?? t.name ?? t.word ?? ""),
          definition: String(
            t.definition ?? t.meaning ?? t.description ?? "",
          ),
        }))
        .filter((t) => t.term && t.definition);
    }

    let faqs = b.faqs;
    if ((!faqs || !faqs.length) && Array.isArray(anyB.questions)) {
      faqs = (anyB.questions as Record<string, unknown>[])
        .map((f) => ({
          question: String(f.question ?? f.q ?? ""),
          answer: String(f.answer ?? f.a ?? ""),
        }))
        .filter((f) => f.question && f.answer);
    }

    let tags = b.tags;
    if ((!tags || !tags.length) && Array.isArray(anyB.filter_tags)) {
      tags = (anyB.filter_tags as unknown[])
        .map((t) =>
          String(t)
            .trim()
            .toLowerCase()
            .replace(/\s+/g, "-"),
        )
        .filter(Boolean);
    }
    if ((!tags || !tags.length) && Array.isArray(anyB.themes)) {
      tags = (anyB.themes as unknown[])
        .map((t) =>
          String(t)
            .trim()
            .toLowerCase()
            .replace(/\s+/g, "-"),
        )
        .filter(Boolean);
    }

    return cleanBlockFields({
      type: b.type,
      title: b.title,
      body: body || b.body,
      items: items && items.length ? items : b.items,
      terms: terms && terms.length ? terms : b.terms,
      faqs: faqs && faqs.length ? faqs : b.faqs,
      tags: tags && tags.length ? tags : b.tags,
      source_indices: b.source_indices,
      width: b.width,
    });
  });

  const filled = blocks.filter(
    (b) =>
      !!(
        (b.body && b.body.trim()) ||
        (b.items && b.items.length) ||
        (b.terms && b.terms.length) ||
        (b.faqs && b.faqs.length) ||
        b.type === "chips" ||
        b.type === "table" ||
        b.type === "metrics" ||
        b.type === "timeline" ||
        b.type === "comparison" ||
        b.type === "progress" ||
        b.type === "chart"
      ),
  );

  const plain =
    raw.plain_summary ||
    (typeof (raw as { summary?: string }).summary === "string"
      ? (raw as { summary?: string }).summary
      : undefined);

  return {
    ...raw,
    title: cleanDisplayText(raw.title),
    plain_summary: plain ? cleanDisplayText(plain) : undefined,
    blocks: filled.length ? filled : blocks,
  };
}

function extractFromValue(value: unknown): GenerativeUIPayload | null {
  if (isGenerativeUI(value)) return normalizeGenerativeUI(value);
  if (typeof value === "string") {
    const parsed = parseJsonGenerativeUI(value);
    if (parsed) return parsed;
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (record.spec) {
      return extractFromValue(record.spec);
    }
    if (looksLikeGenerativePayload(record)) {
      return coerceGenerativeUIPayload(record);
    }
  }
  return null;
}

export function extractGenerativeUIFromRun(
  run: {
    presentation_spec?: unknown;
    final_answer?: string | null;
    steps?: RunStep[];
  } | null | undefined,
): GenerativeUIPayload | null {
  if (!run) return null;
  const steps = run.steps ?? [];
  const fromSpec = extractFromValue(run.presentation_spec);
  const fromLlmOutput = extractLlmOutputGenerativeUI(steps);
  const fromFinalAnswer =
    typeof run.final_answer === "string"
      ? parseJsonGenerativeUI(run.final_answer)
      : null;
  const fromSteps = extractGenerativeUIFromSteps(steps);

  return [fromSpec, fromLlmOutput, fromFinalAnswer, fromSteps].reduce(
    (best, candidate) => pickRicherGenerativeUI(best, candidate),
    null as GenerativeUIPayload | null,
  );
}

export function extractGenerativeUIFromSteps(
  steps: RunStep[],
): GenerativeUIPayload | null {
  let best: GenerativeUIPayload | null = null;
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    const gen = extractFromValue(s.output);
    best = pickRicherGenerativeUI(best, gen);
  }
  return best;
}

export function generativeUIToNoteBody(payload: GenerativeUIPayload): string {
  const lines: string[] = [`# ${payload.title}`];
  if (payload.plain_summary) {
    lines.push("", payload.plain_summary);
  }
  for (const b of payload.blocks ?? []) {
    const t = b.title || b.type.replace(/_/g, " ");
    lines.push("", `## ${t}`);
    if (b.body) lines.push(b.body);
    for (const item of b.items ?? []) {
      if (b.type === "table" && item.includes("|")) {
        lines.push(`| ${item.split("|").map((c) => c.trim()).join(" | ")} |`);
      } else {
        lines.push(`- ${item}`);
      }
    }
    for (const term of b.terms ?? []) {
      lines.push(`- **${term.term}**: ${term.definition}`);
    }
    for (const f of b.faqs ?? []) {
      lines.push(`**Q: ${f.question}**`, `A: ${f.answer}`);
    }
    if (b.type === "quote" && b.body) {
      lines.push(`> ${b.body}`);
    }
  }
  return lines.join("\n").trim();
}
