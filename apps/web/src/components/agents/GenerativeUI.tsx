import { useState } from "react";
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Lightbulb,
  ListOrdered,
  Loader2,
  Sparkles,
  StickyNote,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type GenUIBlock = {
  type: string;
  title?: string | null;
  body?: string | null;
  items?: string[] | null;
  terms?: { term: string; definition: string }[] | null;
  faqs?: { question: string; answer: string }[] | null;
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

/** Normalize LLM shape quirks so cards always show body/lists when present. */
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

    return {
      ...b,
      body: body || b.body,
      items: items && items.length ? items : b.items,
      terms: terms && terms.length ? terms : b.terms,
      faqs: faqs && faqs.length ? faqs : b.faqs,
    };
  });

  // Drop truly empty blocks (title-only cards)
  const filled = blocks.filter(
    (b) =>
      !!(
        (b.body && b.body.trim()) ||
        (b.items && b.items.length) ||
        (b.terms && b.terms.length) ||
        (b.faqs && b.faqs.length)
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

/** Find the latest generative_ui payload in agent step outputs. */
export function extractGenerativeUIFromSteps(
  steps: { type: string; tool_name?: string | null; output?: unknown }[],
): GenerativeUIPayload | null {
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    const out = s.output;
    if (isGenerativeUI(out)) return normalizeGenerativeUI(out);
    if (typeof out === "string") {
      try {
        const parsed = JSON.parse(out) as unknown;
        if (isGenerativeUI(parsed)) return normalizeGenerativeUI(parsed);
      } catch {
        /* ignore */
      }
    }
  }
  return null;
}

/** Markdown body for create_note HITL. */
export function generativeUIToNoteBody(payload: GenerativeUIPayload): string {
  const lines: string[] = [`# ${payload.title}`];
  if (payload.document_filename) {
    lines.push(`_Source: ${payload.document_filename}_`);
  }
  if (payload.plain_summary) {
    lines.push("", payload.plain_summary);
  }
  for (const b of payload.blocks ?? []) {
    const t = b.title || b.type.replace(/_/g, " ");
    lines.push("", `## ${t}`);
    if (b.body) lines.push(b.body);
    for (const item of b.items ?? []) lines.push(`- ${item}`);
    for (const term of b.terms ?? []) {
      lines.push(`- **${term.term}**: ${term.definition}`);
    }
    for (const f of b.faqs ?? []) {
      lines.push(`**Q: ${f.question}**`, `A: ${f.answer}`);
    }
    const idxs = b.source_indices ?? [];
    if (idxs.length) {
      lines.push(`_Sources: ${idxs.map((i) => `[${i}]`).join(", ")}_`);
    }
  }
  if (payload.source_files?.length) {
    lines.push("", `_Files: ${payload.source_files.join(", ")}_`);
  }
  return lines.join("\n").trim();
}

function BlockIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5 shrink-0 text-mute";
  switch (type) {
    case "key_points":
      return <Lightbulb className={cls} strokeWidth={1.5} />;
    case "key_terms":
      return <BookOpen className={cls} strokeWidth={1.5} />;
    case "faq":
      return <HelpCircle className={cls} strokeWidth={1.5} />;
    case "steps":
      return <ListOrdered className={cls} strokeWidth={1.5} />;
    default:
      return <Sparkles className={cls} strokeWidth={1.5} />;
  }
}

function sourcesForBlock(
  block: GenUIBlock,
  sources: GenUISource[],
): GenUISource[] {
  const idxs = block.source_indices ?? [];
  if (!idxs.length || !sources.length) return [];
  const byIndex = new Map(sources.map((s) => [s.index, s]));
  return idxs
    .map((i) => byIndex.get(i))
    .filter((s): s is GenUISource => !!s);
}

function BlockCitations({ sources }: { sources: GenUISource[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-2 border-t border-hairline pt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-0.5 text-[10px] font-medium text-mute hover:text-ink"
      >
        {open ? (
          <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
        ) : (
          <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
        )}
        Sources ({sources.map((s) => `[${s.index}]`).join(" ")})
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1.5">
          {sources.map((s) => (
            <li
              key={`${s.index}-${s.chunk_id ?? s.snippet}`}
              className="rounded-[6px] border border-hairline bg-canvas px-2 py-1.5 text-[10px] leading-relaxed text-body"
            >
              <span className="font-semibold text-ink">[{s.index}]</span>{" "}
              {s.filename && (
                <span className="font-medium text-ink">{s.filename}</span>
              )}
              {typeof s.score === "number" && (
                <span className="text-mute"> · {s.score.toFixed(2)}</span>
              )}
              <p className="mt-0.5 text-mute">{s.snippet || "…"}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function GenerativeUIView({
  payload,
  className,
  onSaveAsNote,
  savingNote,
}: {
  payload: GenerativeUIPayload;
  className?: string;
  /** Starts HITL create_note with learning content */
  onSaveAsNote?: (title: string, body: string) => void;
  savingNote?: boolean;
}) {
  const blocks = payload.blocks ?? [];
  const sources = payload.sources ?? [];

  return (
    <div
      className={cn(
        "w-full max-w-[min(100%,36rem)] space-y-3 rounded-vercel-md border border-hairline bg-canvas p-3 shadow-[var(--elevation-2)] sm:p-4",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 shrink-0 text-ink" strokeWidth={1.5} />
            <h3 className="text-sm font-semibold tracking-tight text-ink">
              {payload.title}
            </h3>
          </div>
          <p className="mt-0.5 text-[11px] text-mute">
            Learning view · generated from your documents
            {payload.document_filename
              ? ` · ${payload.document_filename}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge variant="secondary" className="text-[10px]">
            Generative UI
          </Badge>
          {onSaveAsNote && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1 text-[11px]"
              disabled={savingNote}
              onClick={() =>
                onSaveAsNote(
                  payload.title.slice(0, 120) || "Learning notes",
                  generativeUIToNoteBody(payload),
                )
              }
            >
              {savingNote ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <StickyNote className="h-3 w-3" strokeWidth={1.5} />
              )}
              Save as note
            </Button>
          )}
        </div>
      </div>

      {payload.source_files && payload.source_files.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {payload.source_files.map((f) => (
            <Badge key={f} variant="outline" className="text-[10px] font-normal">
              {f}
            </Badge>
          ))}
        </div>
      )}

      {payload.plain_summary && (
        <p className="text-body-sm leading-relaxed text-body">
          {payload.plain_summary}
        </p>
      )}

      <div className="space-y-2.5">
        {blocks.map((b, i) => {
          const cited = sourcesForBlock(b, sources);
          return (
            <section
              key={`${b.type}-${i}`}
              className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5"
            >
              <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
                <BlockIcon type={b.type} />
                <h4 className="text-xs font-semibold text-ink">
                  {b.title || b.type.replace("_", " ")}
                </h4>
                {cited.length > 0 && (
                  <span className="text-[10px] text-mute">
                    {cited.map((s) => `[${s.index}]`).join(" ")}
                  </span>
                )}
              </div>

              {b.body && (
                <p className="text-xs leading-relaxed text-body">{b.body}</p>
              )}

              {b.items && b.items.length > 0 && (
                <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-body">
                  {b.items.map((item, j) => (
                    <li key={j} className="leading-relaxed">
                      {item}
                    </li>
                  ))}
                </ul>
              )}

              {b.terms && b.terms.length > 0 && (
                <dl className="mt-1 space-y-2">
                  {b.terms.map((t, j) => (
                    <div key={j}>
                      <dt className="text-xs font-semibold text-ink">
                        {t.term}
                      </dt>
                      <dd className="text-xs leading-relaxed text-body">
                        {t.definition}
                      </dd>
                    </div>
                  ))}
                </dl>
              )}

              {b.faqs && b.faqs.length > 0 && (
                <div className="mt-1 space-y-2">
                  {b.faqs.map((f, j) => (
                    <div key={j}>
                      <div className="text-xs font-semibold text-ink">
                        {f.question}
                      </div>
                      <div className="mt-0.5 text-xs leading-relaxed text-body">
                        {f.answer}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {!b.body &&
                !(b.items && b.items.length) &&
                !(b.terms && b.terms.length) &&
                !(b.faqs && b.faqs.length) && (
                  <p className="text-xs text-mute">
                    No details in this section. Try regenerating the learning
                    view or re-ingest the document.
                  </p>
                )}

              <BlockCitations sources={cited} />
            </section>
          );
        })}
      </div>

      {blocks.length === 0 && (
        <p className="text-xs text-mute">
          Learning view has no sections yet. Re-run the agent with “explain
          simply” after documents are ready.
        </p>
      )}
    </div>
  );
}
