export type GenUIBlock = {
  type: string;
  title?: string | null;
  body?: string | null;
  items?: string[] | null;
  terms?: { term: string; definition: string }[] | null;
  faqs?: { question: string; answer: string }[] | null;
  tags?: string[] | null;
  source_indices?: number[] | null;
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
    if (/^[\s\-:|]+$/.test(trimmed)) continue;
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
    const rows = lines
      .filter((l) => !/^[\s\-:|]+$/.test(l))
      .map(splitDelimitedRow)
      .filter((r) => r.length);
    if (rows.length) return padTableRows(rows);
  }
  return items.map(splitDelimitedRow).filter((r) => r.length);
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
  if (!trimmed) {
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
    if (multiCol.length >= 2) return padTableRows(matrix);
    if (multiCol.length === 1 && matrix.length >= 2) return padTableRows(matrix);
  }

  if (Array.isArray(anyB.headers) && anyB.headers.length) {
    const header = (anyB.headers as unknown[]).map((h) => String(h).trim());
    const bodyRaw = anyB.rows ?? anyB.data ?? block.items ?? [];
    if (Array.isArray(bodyRaw) && bodyRaw.length) {
      const body = bodyRaw
        .map(rowToCells)
        .filter((r) => r.length);
      if (body.length) return padTableRows([header, ...body]);
    }
  }

  const rowsRaw = anyB.rows ?? anyB.data ?? anyB.table;
  if (
    Array.isArray(rowsRaw) &&
    rowsRaw.length &&
    rowsRaw.every((r) => r && typeof r === "object" && !Array.isArray(r))
  ) {
    const table = objectRowsToTable(rowsRaw as Record<string, unknown>[]);
    if (table.length) return table;
  }

  const fromItems = (block.items ?? []).map(rowToCells).filter((r) => r.length);
  const rawItems = block.items as unknown;
  if (
    Array.isArray(rawItems) &&
    rawItems.length &&
    rawItems.every((x) => x && typeof x === "object" && !Array.isArray(x))
  ) {
    const table = objectRowsToTable(rawItems as Record<string, unknown>[]);
    if (table.length) return table;
  }
  if (fromItems.some((r) => r.length > 1)) {
    return padTableRows(fromItems);
  }

  if (Array.isArray(rowsRaw) && rowsRaw.length) {
    const parsed = rowsRaw.map(rowToCells).filter((r) => r.length);
    if (parsed.some((r) => r.length > 1)) {
      return padTableRows(parsed);
    }
  }

  if (block.body?.includes("|")) {
    const md = parseMarkdownTableBody(block.body);
    if (md.length) return padTableRows(md);
  }

  if (fromItems.length) return padTableRows(fromItems);
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

export function normalizeGenerativeUI(raw: GenerativeUIPayload): GenerativeUIPayload {
  const blocks = (raw.blocks ?? []).map((b) => {
    const anyB = b as GenUIBlock & Record<string, unknown>;
    const body =
      b.body ||
      (typeof anyB.content === "string" ? anyB.content : null) ||
      (typeof anyB.text === "string" ? anyB.text : null) ||
      (typeof anyB.description === "string" ? anyB.description : null);

    let items =
      (b.items && b.items.length ? b.items : null) ||
      asStringList(anyB.points) ||
      asStringList(anyB.bullets) ||
      asStringList(anyB.key_points) ||
      asStringList(anyB.steps) ||
      undefined;

    if (b.type === "table") {
      const coerced = coerceTableRows({ ...b, items: items ?? b.items });
      if (coerced.length) {
        items = coerced.map((row) => row.join(" | "));
      }
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

    return {
      ...b,
      body: body || b.body,
      items: items && items.length ? items : b.items,
      terms: terms && terms.length ? terms : b.terms,
      faqs: faqs && faqs.length ? faqs : b.faqs,
      tags: tags && tags.length ? tags : b.tags,
    };
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

  return {
    ...raw,
    plain_summary:
      raw.plain_summary ||
      (typeof (raw as { summary?: string }).summary === "string"
        ? (raw as { summary?: string }).summary
        : undefined),
    blocks: filled.length ? filled : blocks,
  };
}

function extractFromValue(value: unknown): GenerativeUIPayload | null {
  if (isGenerativeUI(value)) return normalizeGenerativeUI(value);
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (isGenerativeUI(parsed)) return normalizeGenerativeUI(parsed);
    } catch {
      /* ignore */
    }
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (record.spec) {
      return extractFromValue(record.spec);
    }
  }
  return null;
}

export function extractGenerativeUIFromRun(
  run: {
    presentation_spec?: unknown;
    steps?: { type: string; tool_name?: string | null; output?: unknown }[];
  } | null | undefined,
): GenerativeUIPayload | null {
  if (!run) return null;
  const fromSpec = extractFromValue(run.presentation_spec);
  if (fromSpec) return fromSpec;
  return extractGenerativeUIFromSteps(run.steps ?? []);
}

export function extractGenerativeUIFromSteps(
  steps: { type: string; tool_name?: string | null; output?: unknown }[],
): GenerativeUIPayload | null {
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    const out = s.output;
    const gen = extractFromValue(out);
    if (gen) return gen;
  }
  return null;
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
