import {
  BookOpen,
  HelpCircle,
  Lightbulb,
  ListOrdered,
  Sparkles,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type GenUIBlock = {
  type: string;
  title?: string | null;
  body?: string | null;
  items?: string[] | null;
  terms?: { term: string; definition: string }[] | null;
  faqs?: { question: string; answer: string }[] | null;
};

export type GenerativeUIPayload = {
  type: "generative_ui";
  title: string;
  plain_summary?: string;
  blocks?: GenUIBlock[];
  source_files?: string[];
};

export function isGenerativeUI(value: unknown): value is GenerativeUIPayload {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return v.type === "generative_ui" && typeof v.title === "string";
}

/** Find the latest generative_ui payload in agent step outputs. */
export function extractGenerativeUIFromSteps(
  steps: { type: string; tool_name?: string | null; output?: unknown }[],
): GenerativeUIPayload | null {
  for (let i = steps.length - 1; i >= 0; i--) {
    const s = steps[i];
    const out = s.output;
    if (isGenerativeUI(out)) return out;
    if (typeof out === "string") {
      try {
        const parsed = JSON.parse(out) as unknown;
        if (isGenerativeUI(parsed)) return parsed;
      } catch {
        /* ignore */
      }
    }
  }
  return null;
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

export function GenerativeUIView({
  payload,
  className,
}: {
  payload: GenerativeUIPayload;
  className?: string;
}) {
  const blocks = payload.blocks ?? [];

  return (
    <div
      className={cn(
        "w-full max-w-[min(100%,36rem)] space-y-3 rounded-vercel-md border border-hairline bg-canvas p-3 shadow-[var(--elevation-2)] sm:p-4",
        className,
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-ink" strokeWidth={1.5} />
            <h3 className="text-sm font-semibold tracking-tight text-ink">
              {payload.title}
            </h3>
          </div>
          <p className="mt-0.5 text-[11px] text-mute">
            Learning view · generated from your documents
          </p>
        </div>
        <Badge variant="secondary" className="text-[10px]">
          Generative UI
        </Badge>
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
        {blocks.map((b, i) => (
          <section
            key={`${b.type}-${i}`}
            className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5"
          >
            <div className="mb-1.5 flex items-center gap-1.5">
              <BlockIcon type={b.type} />
              <h4 className="text-xs font-semibold text-ink">
                {b.title || b.type.replace("_", " ")}
              </h4>
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
                    <dt className="text-xs font-semibold text-ink">{t.term}</dt>
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
          </section>
        ))}
      </div>
    </div>
  );
}
