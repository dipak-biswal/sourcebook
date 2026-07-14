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

    const items =
      (b.items && b.items.length ? b.items : null) ||
      asStringList(anyB.points) ||
      asStringList(anyB.bullets) ||
      asStringList(anyB.key_points) ||
      asStringList(anyB.steps) ||
      undefined;

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
