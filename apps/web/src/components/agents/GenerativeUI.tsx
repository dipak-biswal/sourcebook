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
  Table2,
  Tags,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { GenUIBlock, GenUISource, GenerativeUIPayload } from "./generative-ui";
import { generativeUIToNoteBody } from "./generative-ui";

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
    case "chips":
      return <Tags className={cls} strokeWidth={1.5} />;
    case "table":
      return <Table2 className={cls} strokeWidth={1.5} />;
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
            {payload.presentation_profile
              ? `${payload.presentation_profile} · `
              : ""}
            Generated from your workspace
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
                  payload.title.slice(0, 120) || "Structured summary",
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

              {b.type === "chips" && b.items && b.items.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  {b.items.map((item, j) => (
                    <Badge key={j} variant="outline" className="text-[10px] font-normal">
                      {item}
                    </Badge>
                  ))}
                </div>
              )}

              {b.type === "table" && b.items && b.items.length > 0 && (
                <div className="mt-1 overflow-x-auto">
                  <table className="w-full min-w-[12rem] border-collapse text-left text-xs text-body">
                    <tbody>
                      {b.items.map((row, j) => {
                        const cells = row.split("|").map((c) => c.trim());
                        const CellTag = j === 0 ? "th" : "td";
                        return (
                          <tr key={j} className="border-b border-hairline last:border-0">
                            {cells.map((cell, k) => (
                              <CellTag
                                key={k}
                                className={cn(
                                  "px-2 py-1.5 align-top",
                                  j === 0 && "font-semibold text-ink",
                                )}
                              >
                                {cell}
                              </CellTag>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {b.type !== "chips" &&
                b.type !== "table" &&
                b.items &&
                b.items.length > 0 && (
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
                    No details in this section.
                  </p>
                )}

              <BlockCitations sources={cited} />
            </section>
          );
        })}
      </div>

      {blocks.length === 0 && (
        <p className="text-xs text-mute">
          Presentation has no sections yet.
        </p>
      )}
    </div>
  );
}
