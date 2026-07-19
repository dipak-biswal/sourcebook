import { useCallback, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  FileText,
  HelpCircle,
  Lightbulb,
  ListOrdered,
  Loader2,
  MessageSquareQuote,
  Sparkles,
  StickyNote,
  Table2,
  Tags,
  Timer,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/api";
import { Button } from "@/components/ui/button";
import { citationViewerPath } from "@/lib/document-links";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { GenUIBlock, GenerativeUIPayload } from "./generative-ui";
import { BLOCK_CONTRACT, KNOWN_BLOCK_TYPES } from "./block-contract";
import {
  coerceTableRows,
  generativeUIExportFilename,
  generativeUIToNoteBody,
  parseProgressValue,
} from "./generative-ui";

/** Best-effort: never block the UI on ranking telemetry. */
function reportVisualInteraction(opts: {
  workspaceId?: string | null;
  runId?: string | null;
  action: string;
  affordance?: string;
  label?: string;
}) {
  if (!opts.workspaceId) return;
  void api.logVisualInteraction({
    workspace_id: opts.workspaceId,
    action: opts.action,
    affordance: opts.affordance,
    label: opts.label,
    run_id: opts.runId ?? undefined,
  });
}

function isDashOnlyRow(text: string): boolean {
  const s = text.trim();
  if (!s) return true;
  return /^[\s\-:|]+$/.test(s);
}

function parsePipeRow(row: string): string[] {
  return row.split("|").map((c) => c.trim());
}

// Must mirror the backend chip slug (non-alphanumeric → dash) so block tags
// and chip tags land on the same value.
function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeProse(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

/** True when the standalone summary paragraph just repeats a summary block. */
function plainSummaryIsRedundant(
  plain: string,
  blocks: GenUIBlock[],
): boolean {
  const p = normalizeProse(plain);
  if (!p) return true;
  for (const block of blocks) {
    if (block.type !== "summary" || !block.body) continue;
    const b = normalizeProse(block.body);
    if (b.startsWith(p.slice(0, 120)) || p.startsWith(b.slice(0, 120))) {
      return true;
    }
  }
  return false;
}

// Wide blocks carry more data and read better full-width; compact blocks pair up.
const FULL_WIDTH_TYPES = new Set([
  "summary",
  "table",
  "comparison",
  "chart",
  "timeline",
  "steps",
  "chips",
]);

function isFullWidth(block: GenUIBlock): boolean {
  if (block.width === "full") return true;
  if (block.width === "half") return false;
  return FULL_WIDTH_TYPES.has(block.type);
}

function parseChip(item: string): { label: string; tag: string } {
  const parts = parsePipeRow(item);
  const label = parts[0] || item;
  const tag = slugify(parts[1] || parts[0] || item);
  return { label, tag };
}

function blockMatchesTag(block: GenUIBlock, tag: string | null): boolean {
  if (!tag) return true;
  // Always keep filters + overview visible while filtering.
  if (block.type === "chips" || block.type === "summary") return true;

  const tags = (block.tags ?? []).map((t) => slugify(t)).filter(Boolean);
  // Most assembled blocks are untagged today. Hiding them on chip click
  // emptied the visual summary for job-search / multi-theme layouts.
  if (!tags.length) {
    const hay = [
      block.title ?? "",
      block.body ?? "",
      ...(block.items ?? []),
      ...(block.terms ?? []).flatMap((t) => [t.term, t.definition]),
      ...(block.faqs ?? []).flatMap((f) => [f.question, f.answer]),
    ]
      .join(" ")
      .toLowerCase();
    return hay.includes(tag.replace(/-/g, " ")) || hay.includes(tag);
  }
  if (tags.includes(tag)) return true;
  const titleSlug = slugify(block.title ?? "");
  return titleSlug.includes(tag) || tag.includes(titleSlug);
}

function BlockLabel({
  type,
  title,
  className,
}: {
  type: string;
  title?: string | null;
  className?: string;
}) {
  const label = title || type.replace(/_/g, " ");
  const icons: Record<string, typeof Sparkles> = {
    key_points: Lightbulb,
    key_terms: BookOpen,
    faq: HelpCircle,
    steps: ListOrdered,
    timeline: Timer,
    chips: Tags,
    table: Table2,
    metrics: Sparkles,
    callout: AlertTriangle,
    quote: MessageSquareQuote,
    comparison: Table2,
    progress: BarChart3,
    chart: BarChart3,
  };
  const Icon = icons[type] ?? Sparkles;
  return (
    <div className={cn("mb-2 flex items-center gap-1.5", className)}>
      <Icon className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
      <span className="text-[11px] font-bold uppercase tracking-wide text-mute">
        {label}
      </span>
    </div>
  );
}

function SummaryBlock({ block }: { block: GenUIBlock }) {
  return (
    <div className="rounded-[10px] bg-canvas-soft px-4 py-3">
      {block.title && (
        <h4 className="text-sm font-semibold text-ink">{block.title}</h4>
      )}
      {block.body && (
        <p
          className={cn(
            "text-sm leading-relaxed text-body",
            block.title && "mt-1.5",
          )}
        >
          {block.body}
        </p>
      )}
    </div>
  );
}

function CalloutBlock({ block }: { block: GenUIBlock }) {
  return (
    <div className="flex gap-3 rounded-[8px] border border-warning-border bg-warning-soft px-3 py-2.5">
      <AlertTriangle
        className="mt-0.5 h-4 w-4 shrink-0 text-warning-text"
        strokeWidth={1.5}
      />
      <div className="min-w-0">
        {block.title && (
          <div className="text-xs font-semibold text-ink">{block.title}</div>
        )}
        {block.body && (
          <p className="mt-0.5 text-xs leading-relaxed text-body">{block.body}</p>
        )}
      </div>
    </div>
  );
}

function QuoteBlock({ block }: { block: GenUIBlock }) {
  return (
    <blockquote className="border-l-2 border-ink/20 pl-4">
      {block.body && (
        <p className="text-sm italic leading-relaxed text-body">
          &ldquo;{block.body}&rdquo;
        </p>
      )}
      {block.title && (
        <footer className="mt-1.5 text-[11px] font-medium text-mute">
          — {block.title}
        </footer>
      )}
    </blockquote>
  );
}

function ChipsBlock({
  block,
  activeTag,
  onSelect,
}: {
  block: GenUIBlock;
  activeTag: string | null;
  onSelect: (tag: string | null) => void;
}) {
  const items = block.items ?? [];
  if (!items.length) return null;
  const chips = items.map(parseChip);

  return (
    <div>
      <BlockLabel type="chips" title={block.title ?? "Filter by theme"} />
      <div className="flex flex-wrap items-center gap-1.5">
        <button
          type="button"
          onClick={() => onSelect(null)}
          className={cn(
            "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
            activeTag === null
              ? "border-ink bg-ink text-[var(--canvas)]"
              : "border-hairline bg-canvas text-ink hover:bg-canvas-soft-2",
          )}
        >
          All
        </button>
        {chips.map((chip, j) => (
          <button
            key={j}
            type="button"
            onClick={() => onSelect(activeTag === chip.tag ? null : chip.tag)}
            className={cn(
              "inline-flex rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
              activeTag === chip.tag
                ? "border-ink bg-ink text-[var(--canvas)]"
                : "border-hairline bg-canvas text-ink hover:bg-canvas-soft-2",
            )}
          >
            {chip.label}
          </button>
        ))}
      </div>
      {activeTag && (
        <p className="mt-1.5 text-[10px] text-mute">
          Showing sections tagged &ldquo;{activeTag}&rdquo; — click All to reset
        </p>
      )}
    </div>
  );
}

function MetricsBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  // Server-derived measures keep label/value intact even when the label
  // itself contains a pipe; fall back to parsing the raw pipe rows.
  const rows: Array<[string, string]> = block.measures?.length
    ? block.measures.map((m) => [m.label, m.value])
    : items.map((item) => {
        const [label, value] = parsePipeRow(item);
        return [label || item, value ?? ""];
      });
  if (!rows.length) return null;
  return (
    <div>
      <BlockLabel type="metrics" title={block.title} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {rows.map(([label, value], j) => {
          return (
            <div
              key={j}
              className="rounded-[8px] border border-hairline bg-canvas px-3 py-2.5"
            >
              <div className="text-[10px] font-medium uppercase tracking-wide text-mute">
                {label}
              </div>
              {value && (
                <div className="mt-0.5 text-base font-semibold tabular-nums text-ink">
                  {value}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ProgressBlock({ block }: { block: GenUIBlock }) {
  const items = (block.items ?? []).filter((item) => !isDashOnlyRow(item));
  if (!items.length) return null;
  return (
    <div>
      <BlockLabel type="progress" title={block.title} />
      <div className="space-y-2.5">
        {items
          .filter((item) => {
            const [label, raw] = parsePipeRow(item);
            return !(isDashOnlyRow(label) && isDashOnlyRow(raw || ""));
          })
          .map((item, j) => {
          const [label, raw] = parsePipeRow(item);
          const { pct, display } = parseProgressValue(raw || "");
          return (
            <div key={j}>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-ink">{label || item}</span>
                <span
                  className={cn(
                    "text-mute",
                    display.endsWith("%") && "tabular-nums",
                  )}
                >
                  {display}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-canvas-soft">
                <div
                  className="h-full rounded-full bg-ink transition-all duration-300"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ChartBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  const measures = block.measures ?? [];
  // When every row has a server-verified numeric, scale bars by the real
  // values ("200 ms" vs "450 ms") instead of the qualitative 50% fallback.
  const numericScale =
    measures.length > 0 && measures.every((m) => typeof m.numeric === "number");
  const rows = numericScale
    ? measures.map((m) => ({
        label: m.label,
        pct: Math.abs(m.numeric as number),
        display: m.value,
      }))
    : items.map((item) => {
        const [label, raw] = parsePipeRow(item);
        const parsed = parseProgressValue(raw || "");
        return { label: label || item, ...parsed };
      });
  if (!rows.length) return null;
  const max = Math.max(...rows.map((r) => r.pct), 1);

  return (
    <div>
      <BlockLabel type="chart" title={block.title} />
      <div className="space-y-2">
        {rows.map((row, j) => (
          <div key={j} className="flex items-center gap-2">
            <span className="w-24 shrink-0 truncate text-[11px] font-medium text-ink">
              {row.label}
            </span>
            <div className="relative h-6 min-w-0 flex-1 overflow-hidden rounded-[4px] bg-canvas-soft">
              <div
                className="absolute inset-y-0 left-0 rounded-[4px] bg-ink/80 transition-all duration-300"
                style={{ width: `${(row.pct / max) * 100}%` }}
              />
              <span
                className={cn(
                  "relative z-10 flex h-full items-center px-2 text-[10px] font-semibold text-ink",
                  row.display.endsWith("%") && "tabular-nums",
                )}
              >
                {row.display}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KeyPointsBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  if (!items.length && !block.body) return null;
  return (
    <div>
      <BlockLabel type="key_points" title={block.title} />
      {block.body && (
        <p className="mb-2 text-xs leading-relaxed text-body">{block.body}</p>
      )}
      <ul className="space-y-1.5">
        {items.map((item, j) => (
          <li key={j} className="flex gap-2 text-xs leading-relaxed text-body">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-ink" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function StepsBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  if (!items.length) return null;
  return (
    <div>
      <BlockLabel type="steps" title={block.title} />
      <ol className="space-y-0">
        {items.map((item, j) => (
          <li key={j} className="flex gap-3">
            <div className="flex flex-col items-center">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-bold text-[var(--canvas)]">
                {j + 1}
              </span>
              {j < items.length - 1 && (
                <span className="my-0.5 w-px flex-1 bg-hairline" />
              )}
            </div>
            <p className="pb-3 pt-0.5 text-xs leading-relaxed text-body">
              {item}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

function TimelineBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  if (!items.length) return null;
  return (
    <div>
      <BlockLabel type="timeline" title={block.title} />
      <div className="relative space-y-0 pl-1">
        <div className="absolute bottom-2 left-[7px] top-2 w-px bg-hairline" />
        {items.map((item, j) => {
          const cells = parsePipeRow(item);
          const [period, title, detail] = cells;
          return (
            <div key={j} className="relative flex gap-3 pb-4 last:pb-0">
              <span className="relative z-10 mt-1.5 h-3.5 w-3.5 shrink-0 rounded-full border-2 border-ink bg-canvas" />
              <div className="min-w-0 flex-1">
                {period && (
                  <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
                    {period}
                  </div>
                )}
                <div className="text-xs font-semibold text-ink">
                  {title || (cells.length === 1 ? item : "")}
                </div>
                {detail && (
                  <p className="mt-0.5 text-xs leading-relaxed text-body">
                    {detail}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function normalizeTableMatrix(rows: string[][]): string[][] {
  if (!rows.length) return rows;
  // Prefer the dominant column count so 2-col skill rows don't warp a 3-col matrix.
  const counts = new Map<number, number>();
  for (const r of rows) {
    if (r.length >= 2) counts.set(r.length, (counts.get(r.length) ?? 0) + 1);
  }
  let dominant = 0;
  let best = 0;
  for (const [cols, n] of counts) {
    if (n > best || (n === best && cols > dominant)) {
      best = n;
      dominant = cols;
    }
  }
  const filtered =
    dominant >= 2
      ? rows.filter((r) => r.length === dominant || r.length === 0)
      : rows;
  const usable = filtered.filter((r) => r.length >= 2);
  if (!usable.length) return rows.filter((r) => r.length >= 1);
  const colCount = Math.max(...usable.map((r) => r.length), 1);
  return usable.map((r) => {
    const padded = [...r];
    while (padded.length < colCount) padded.push("");
    return padded.slice(0, colCount);
  });
}

function TableBlock({ block }: { block: GenUIBlock }) {
  const rows = normalizeTableMatrix(coerceTableRows(block));
  if (!rows.length) {
    if (block.body?.trim()) {
      return (
        <div>
          <BlockLabel type="table" title={block.title} />
          <p className="text-xs leading-relaxed text-body">{block.body}</p>
        </div>
      );
    }
    return null;
  }

  const colCount = Math.max(...rows.map((r) => r.length), 1);
  const headerLooksLikeLabels =
    rows.length > 1 &&
    rows[0].every((cell) => cell.length > 0 && cell.length < 40) &&
    rows[0].some((cell) => /[a-zA-Z]/.test(cell)) &&
    !/strong|growing|gap|weak|foundational/i.test(rows[0].join(" "));
  const useHeader = rows.length > 1 && headerLooksLikeLabels;
  const header = useHeader ? rows[0] : null;
  const bodyRows = useHeader ? rows.slice(1) : rows;

  return (
    <div className="min-w-0">
      <BlockLabel type="table" title={block.title} />
      <div className="max-w-full overflow-x-auto rounded-[8px] border border-hairline">
        <Table>
          {header && (
            <TableHeader>
              <TableRow className="hover:bg-canvas-soft">
                {Array.from({ length: colCount }).map((_, k) => (
                  <TableHead key={k} className="whitespace-nowrap">
                    {header[k] ?? ""}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
          )}
          <TableBody>
            {bodyRows.map((cells, j) => (
              <TableRow key={j} className="even:bg-canvas-soft/40">
                {Array.from({ length: colCount }).map((_, k) => (
                  <TableCell
                    key={k}
                    className="max-w-[14rem] whitespace-normal break-words align-top text-xs"
                  >
                    {cells[k] ?? ""}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function ComparisonBlock({ block }: { block: GenUIBlock }) {
  const items = block.items ?? [];
  if (!items.length) return null;
  const rows = normalizeTableMatrix(items.map(parsePipeRow));
  const headers = rows[0] ?? [];
  const dataRows = rows.slice(1);
  return (
    <div className="min-w-0">
      <BlockLabel type="comparison" title={block.title} />
      {headers.length >= 2 ? (
        <div className="grid gap-2 sm:grid-cols-2">
          {headers.slice(1).map((header, colIdx) => (
            <div
              key={colIdx}
              className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5"
            >
              <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
                {header}
              </div>
              <ul className="mt-2 space-y-1.5">
                {dataRows.map((row, j) => (
                  <li key={j}>
                    <div className="text-[10px] font-medium text-mute">
                      {row[0]}
                    </div>
                    <div className="text-xs text-body">{row[colIdx + 1] ?? "—"}</div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      ) : (
        <TableBlock block={block} />
      )}
    </div>
  );
}

function TermsBlock({ block }: { block: GenUIBlock }) {
  const terms = block.terms ?? [];
  if (!terms.length) return null;
  return (
    <div>
      <BlockLabel type="key_terms" title={block.title} />
      <div className="grid gap-2 sm:grid-cols-2">
        {terms.map((t, j) => (
          <div
            key={j}
            className="rounded-[8px] border border-hairline bg-canvas px-3 py-2"
          >
            <dt className="text-xs font-semibold text-ink">{t.term}</dt>
            <dd className="mt-0.5 text-xs leading-relaxed text-body">
              {t.definition}
            </dd>
          </div>
        ))}
      </div>
    </div>
  );
}

function FaqBlock({
  block,
  onExpand,
}: {
  block: GenUIBlock;
  onExpand?: (question: string) => void;
}) {
  const [openIdx, setOpenIdx] = useState<number | null>(0);
  const faqs = block.faqs ?? [];
  if (!faqs.length) return null;

  return (
    <div>
      <BlockLabel type="faq" title={block.title} />
      <div className="divide-y divide-hairline rounded-[8px] border border-hairline">
        {faqs.map((f, j) => {
          const open = openIdx === j;
          return (
            <div key={j}>
              <button
                type="button"
                onClick={() => {
                  const next = open ? null : j;
                  setOpenIdx(next);
                  if (next !== null) onExpand?.(f.question);
                }}
                className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-canvas-soft"
              >
                {open ? (
                  <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
                ) : (
                  <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
                )}
                <span className="text-xs font-semibold text-ink">
                  {f.question}
                </span>
              </button>
              {open && (
                <div className="border-t border-hairline bg-canvas-soft px-3 py-2.5 pl-9 text-xs leading-relaxed text-body">
                  {f.answer}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GenerativeUIBlock({
  block,
  chipProps,
  onFaqExpand,
}: {
  block: GenUIBlock;
  chipProps?: {
    activeTag: string | null;
    onSelect: (tag: string | null) => void;
  };
  onFaqExpand?: (question: string) => void;
}) {
  switch (block.type) {
    case "summary":
      return <SummaryBlock block={block} />;
    case "callout":
      return <CalloutBlock block={block} />;
    case "quote":
      return <QuoteBlock block={block} />;
    case "chips":
      return chipProps ? (
        <ChipsBlock
          block={block}
          activeTag={chipProps.activeTag}
          onSelect={chipProps.onSelect}
        />
      ) : null;
    case "metrics":
      return <MetricsBlock block={block} />;
    case "progress":
      return <ProgressBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "key_points":
      return <KeyPointsBlock block={block} />;
    case "steps":
      return <StepsBlock block={block} />;
    case "timeline":
      return <TimelineBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "comparison":
      return <ComparisonBlock block={block} />;
    case "key_terms":
      return <TermsBlock block={block} />;
    case "faq":
      return <FaqBlock block={block} onExpand={onFaqExpand} />;
    default:
      // A type in the contract but missing a case above means this renderer
      // is behind the backend registry — surface it in dev builds.
      if (import.meta.env.DEV && KNOWN_BLOCK_TYPES.has(block.type)) {
        console.warn(
          `GenerativeUI: block type "${block.type}" is in the block contract but has no renderer case`,
        );
      }
      return (
        <div className="rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5">
          <BlockLabel type={block.type} title={block.title} />
          {block.body && (
            <p className="text-xs leading-relaxed text-body">{block.body}</p>
          )}
          {block.items && block.items.length > 0 && (
            <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-body">
              {block.items.map((item, j) => (
                <li key={j}>{item}</li>
              ))}
            </ul>
          )}
        </div>
      );
  }
}

export function GenerativeUISkeleton({
  skeleton,
  className,
}: {
  skeleton: import("@/api").PresentationSkeleton;
  className?: string;
}) {
  const widths = BLOCK_CONTRACT.widths as Record<string, string>;
  const outline = skeleton.outline ?? [];
  if (!outline.length) return null;
  return (
    <div
      className={cn(
        "w-full max-w-[min(100%,60rem)] space-y-4 rounded-vercel-md border border-hairline bg-canvas p-3 shadow-[var(--elevation-2)] sm:p-4",
        className,
      )}
    >
      <div className="flex items-center gap-1.5">
        <Loader2 className="h-4 w-4 shrink-0 animate-spin text-mute" />
        <h3 className="text-sm font-semibold tracking-tight text-ink">
          Building visual summary…
        </h3>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {outline.map((entry, i) => {
          const full =
            entry.width === "full" ||
            (!entry.width && widths[entry.type] === "full");
          return (
            <div
              key={`${entry.type}-${i}`}
              className={cn(
                "min-w-0 animate-pulse rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5",
                full && "md:col-span-2",
              )}
            >
              <div className="text-[11px] font-bold uppercase tracking-wide text-mute">
                {entry.title || entry.type.replace(/_/g, " ")}
              </div>
              <div className="mt-2 h-2 w-3/4 rounded bg-canvas-soft-2" />
              <div className="mt-1.5 h-2 w-1/2 rounded bg-canvas-soft-2" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function GenerativeUIView({
  payload,
  className,
  onSaveAsNote,
  savingNote,
  workspaceId,
  runId,
}: {
  payload: GenerativeUIPayload;
  className?: string;
  onSaveAsNote?: (title: string, body: string) => void;
  savingNote?: boolean;
  /** When set, chip/FAQ interactions are logged for affordance ranking. */
  workspaceId?: string | null;
  runId?: string | null;
}) {
  const blocks = payload.blocks ?? [];
  const sourceFiles = [
    ...new Set(
      (payload.source_files ?? [])
        .map((f) => (f ?? "").trim())
        .filter(Boolean),
    ),
  ];
  const [activeTag, setActiveTag] = useState<string | null>(null);
  const onChipSelect = useCallback(
    (tag: string | null) => {
      setActiveTag(tag);
      if (tag) {
        reportVisualInteraction({
          workspaceId,
          runId,
          action: "chip_select",
          affordance: "topic_filter",
          label: tag,
        });
      }
    },
    [workspaceId, runId],
  );
  const onFaqExpand = useCallback(
    (question: string) => {
      reportVisualInteraction({
        workspaceId,
        runId,
        action: "faq_expand",
        affordance: "self_check",
        label: question,
      });
    },
    [workspaceId, runId],
  );
  const chipProps = { activeTag, onSelect: onChipSelect };
  const [copied, setCopied] = useState(false);
  const markdown = generativeUIToNoteBody(payload);

  const handleCopyMarkdown = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Fallback for older browsers / denied clipboard
      const ta = document.createElement("textarea");
      ta.value = markdown;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    }
  }, [markdown]);

  const handleDownloadMarkdown = useCallback(() => {
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = generativeUIExportFilename(payload);
    a.click();
    URL.revokeObjectURL(url);
  }, [markdown, payload]);

  return (
    <div
      className={cn(
        "w-full max-w-[min(100%,60rem)] space-y-4 rounded-vercel-md border border-hairline bg-canvas p-3 shadow-[var(--elevation-2)] sm:p-4",
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
              ? `${payload.presentation_profile.replace(/_/g, " ")} · `
              : ""}
            Visual summary from your workspace
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 gap-1 text-[11px]"
            onClick={() => void handleCopyMarkdown()}
          >
            {copied ? (
              <Check className="h-3 w-3" strokeWidth={1.5} />
            ) : (
              <Copy className="h-3 w-3" strokeWidth={1.5} />
            )}
            {copied ? "Copied" : "Copy MD"}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-7 gap-1 text-[11px]"
            onClick={handleDownloadMarkdown}
          >
            <Download className="h-3 w-3" strokeWidth={1.5} />
            Download
          </Button>
          {onSaveAsNote && (
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 gap-1 text-[11px]"
              disabled={savingNote}
              onClick={() =>
                onSaveAsNote(
                  payload.title.slice(0, 120) || "Visual summary",
                  markdown,
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

      {payload.plain_summary &&
        !plainSummaryIsRedundant(payload.plain_summary, blocks) && (
          <p className="text-body-sm leading-relaxed text-body">
            {payload.plain_summary}
          </p>
        )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {blocks.map((b, i) => {
          if (!blockMatchesTag(b, activeTag)) return null;
          const highlighted =
            activeTag &&
            b.type !== "chips" &&
            b.type !== "summary" &&
            (b.tags ?? []).map(slugify).includes(activeTag);
          return (
            <div
              key={`${b.type}-${i}`}
              className={cn(
                "min-w-0 self-start transition-opacity duration-200",
                isFullWidth(b) && "md:col-span-2",
                highlighted && "rounded-[10px] ring-1 ring-ink/15",
              )}
            >
              <GenerativeUIBlock
                block={b}
                chipProps={b.type === "chips" ? chipProps : undefined}
                onFaqExpand={b.type === "faq" ? onFaqExpand : undefined}
              />
            </div>
          );
        })}
      </div>

      {blocks.length === 0 && (
        <p className="text-xs text-mute">Presentation has no sections yet.</p>
      )}

      {(payload.sources?.length || sourceFiles.length > 0) && (
        <div className="flex flex-wrap items-center gap-1.5 border-t border-hairline pt-3">
          <span className="text-[10px] font-bold uppercase tracking-wide text-mute">
            Sources
          </span>
          {payload.sources && payload.sources.length > 0
            ? payload.sources.map((s) => {
                const path = citationViewerPath({
                  document_id: s.document_id,
                  chunk_id: s.chunk_id,
                  snippet: s.snippet,
                });
                const label = s.filename || `Source ${s.index}`;
                const chip = (
                  <>
                    <FileText
                      className="h-3 w-3 shrink-0 text-mute"
                      strokeWidth={1.5}
                    />
                    <span className="font-semibold text-ink">[{s.index}]</span>
                    {label}
                  </>
                );
                return path ? (
                  <Link
                    key={`${s.index}-${s.chunk_id || s.document_id || label}`}
                    to={path}
                    title={s.snippet || label}
                    className="inline-flex max-w-full items-center gap-1 truncate rounded-full border border-hairline bg-canvas-soft px-2 py-0.5 text-[10px] font-medium text-body transition-colors hover:border-ink/30 hover:bg-canvas"
                  >
                    {chip}
                  </Link>
                ) : (
                  <span
                    key={`${s.index}-${label}`}
                    className="inline-flex max-w-full items-center gap-1 truncate rounded-full border border-hairline bg-canvas-soft px-2 py-0.5 text-[10px] font-medium text-body"
                    title={s.snippet || label}
                  >
                    {chip}
                  </span>
                );
              })
            : sourceFiles.map((file, j) => (
                <span
                  key={j}
                  className="inline-flex items-center gap-1 rounded-full border border-hairline bg-canvas-soft px-2 py-0.5 text-[10px] font-medium text-body"
                >
                  <FileText
                    className="h-3 w-3 shrink-0 text-mute"
                    strokeWidth={1.5}
                  />
                  {file}
                </span>
              ))}
        </div>
      )}
    </div>
  );
}