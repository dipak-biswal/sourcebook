import { useId, useMemo, useState, type ReactNode } from "react";
import { ChevronLeft, ChevronRight, Workflow } from "lucide-react";
import { cn } from "@/lib/utils";
import { BLOCK_TYPE_ICONS } from "./generative-ui";
import type { GenUIBlock } from "./generative-ui";

function DiagramLabel({
  type,
  title,
}: {
  type: string;
  title?: string | null;
}) {
  const Icon = BLOCK_TYPE_ICONS[type] ?? Workflow;
  const label = title || type.replace(/_/g, " ");
  return (
    <div className="mb-2 flex items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
      <span className="text-[11px] font-bold uppercase tracking-wide text-mute">
        {label}
      </span>
    </div>
  );
}

function DiagramMarker({ id }: { id: string }) {
  return (
    <marker
      id={id}
      viewBox="0 0 10 10"
      refX="8"
      refY="5"
      markerWidth="7"
      markerHeight="7"
      orient="auto-start-reverse"
    >
      <path d="M 0 0 L 10 5 L 0 10 z" className="fill-mute" />
    </marker>
  );
}

/** Soft zone palette so runtime parts (stack vs queue vs APIs) read as distinct. */
const ZONE_STYLES = [
  "border-success-border bg-success-soft text-success-text",
  "border-warning-border bg-warning-soft text-warning-text",
  "border-hairline bg-canvas-soft-2 text-ink",
  "border-ink/20 bg-canvas-soft text-ink",
] as const;

const ZONE_BAND_FILLS = [
  "fill-success-soft",
  "fill-warning-soft",
  "fill-canvas-soft-2",
  "fill-canvas-soft",
] as const;

function zoneIndex(seed: string): number {
  let h = 0;
  for (let i = 0; i < seed.length; i++) {
    h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return h % ZONE_STYLES.length;
}

function ExpandPanel({
  eyebrow,
  text,
  stepLabel,
}: {
  eyebrow: string;
  text: string;
  stepLabel?: string;
}) {
  return (
    <div className="mt-3 rounded-[10px] border border-hairline bg-canvas-soft px-3 py-2.5 text-xs leading-relaxed text-body">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        {stepLabel && (
          <span className="rounded-full border border-hairline bg-canvas px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-mute">
            {stepLabel}
          </span>
        )}
        <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
          {eyebrow}
        </div>
      </div>
      <TeachingText text={text} />
    </div>
  );
}

/** Light code-aware detail: backticks become mono chips; rest stays plain. */
function TeachingText({ text }: { text: string }) {
  const parts = text.split(/(`[^`]+`)/g);
  return (
    <p className="text-xs leading-relaxed text-body">
      {parts.map((part, i) => {
        if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
          return (
            <code
              key={i}
              className="mx-0.5 rounded border border-hairline bg-canvas px-1 py-0.5 font-mono text-[11px] text-ink"
            >
              {part.slice(1, -1)}
            </code>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </p>
  );
}

function WalkthroughControls({
  index,
  total,
  onPrev,
  onNext,
  label,
}: {
  index: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  label?: string;
}) {
  if (total < 1) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <div className="inline-flex items-center gap-1 rounded-[8px] border border-hairline bg-canvas p-0.5">
        <button
          type="button"
          onClick={onPrev}
          disabled={index <= 0}
          className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-body transition-colors hover:bg-canvas-soft disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Previous step"
        >
          <ChevronLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
        <span className="min-w-[4.5rem] text-center text-[11px] font-medium tabular-nums text-mute">
          Step {index + 1} / {total}
        </span>
        <button
          type="button"
          onClick={onNext}
          disabled={index >= total - 1}
          className="inline-flex h-7 w-7 items-center justify-center rounded-[6px] text-body transition-colors hover:bg-canvas-soft disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Next step"
        >
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      </div>
      {label && (
        <span className="line-clamp-1 text-[11px] text-mute">{label}</span>
      )}
    </div>
  );
}

function FigureChrome({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[12px] border border-hairline bg-canvas-soft/40 p-3 sm:p-4">
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flow diagram: layered-DAG layout with deterministic back-edge arc routing.
// ---------------------------------------------------------------------------

type FlowNode = { id: string; label: string; detail?: string | null };
type FlowEdge = { source: string; target: string; label?: string | null };

const NODE_W = 168;
const NODE_H = 76;
const COL_GAP = 56;
const ROW_GAP = 28;
const LANE_GAP = 32;
const LANE_H = 32;
const COL_PAD_Y = 32;
const PAD_X = 12;

type PositionedNode = FlowNode & {
  column: number;
  row: number;
  x: number;
  y: number;
};

type LaidOutEdge = FlowEdge & { path: string; labelX: number; labelY: number };

type FlowLayout = {
  nodes: PositionedNode[];
  forwardEdges: LaidOutEdge[];
  backEdges: LaidOutEdge[];
  columns: { index: number; x: number; label: string }[];
  width: number;
  height: number;
};

function layoutFlowDiagram(nodes: FlowNode[], edges: FlowEdge[]): FlowLayout | null {
  if (nodes.length < 2) return null;
  const idSet = new Set(nodes.map((n) => n.id));
  const validEdges = edges.filter(
    (e) => idSet.has(e.source) && idSet.has(e.target) && e.source !== e.target,
  );
  if (!validEdges.length) return null;

  const inDegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const outDegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const adj = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  const rev = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of validEdges) {
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
    outDegree.set(e.source, (outDegree.get(e.source) ?? 0) + 1);
    adj.get(e.source)?.push(e.target);
    rev.get(e.target)?.push(e.source);
  }

  let roots = nodes.filter((n) => (inDegree.get(n.id) ?? 0) === 0).map((n) => n.id);
  if (!roots.length) {
    let best = nodes[0].id;
    let bestOut = -1;
    for (const n of nodes) {
      const od = outDegree.get(n.id) ?? 0;
      if (od > bestOut) {
        bestOut = od;
        best = n.id;
      }
    }
    roots = [best];
  }

  // Longest-path layering: more stable columns for teaching pipelines.
  const column = new Map<string, number>();
  const queue: string[] = [];
  for (const r of roots) {
    column.set(r, 0);
    queue.push(r);
  }
  while (queue.length) {
    const id = queue.shift();
    if (id === undefined) break;
    const col = column.get(id) ?? 0;
    for (const next of adj.get(id) ?? []) {
      const nextCol = col + 1;
      const prev = column.get(next);
      if (prev === undefined || nextCol > prev) {
        column.set(next, nextCol);
        queue.push(next);
      }
    }
  }
  for (const n of nodes) {
    if (!column.has(n.id)) column.set(n.id, 0);
  }

  // Teaching preference: ≤5 components → one node per column (readable chain).
  // Use topological order from original node list when columns would stack.
  let byColumn = new Map<number, string[]>();
  for (const n of nodes) {
    const c = column.get(n.id) ?? 0;
    if (!byColumn.has(c)) byColumn.set(c, []);
    byColumn.get(c)?.push(n.id);
  }
  const maxStacked = Math.max(
    ...Array.from(byColumn.values()).map((v) => v.length),
    1,
  );
  if (nodes.length <= 5 && maxStacked > 1) {
    // Re-assign sequential columns in longest-path order, preserving stack root first.
    const ordered = [...nodes].sort(
      (a, b) => (column.get(a.id) ?? 0) - (column.get(b.id) ?? 0),
    );
    ordered.forEach((n, i) => column.set(n.id, i));
    byColumn = new Map();
    for (const n of ordered) {
      const c = column.get(n.id) ?? 0;
      if (!byColumn.has(c)) byColumn.set(c, []);
      byColumn.get(c)?.push(n.id);
    }
  }

  const row = new Map<string, number>();
  for (const ids of byColumn.values()) {
    ids.forEach((id, i) => row.set(id, i));
  }

  const maxCol = Math.max(...Array.from(column.values()), 0);
  const maxRows = Math.max(...Array.from(byColumn.values()).map((v) => v.length), 1);

  const positioned: PositionedNode[] = nodes.map((n) => {
    const col = column.get(n.id) ?? 0;
    const r = row.get(n.id) ?? 0;
    return {
      ...n,
      column: col,
      row: r,
      x: PAD_X + col * (NODE_W + COL_GAP),
      y: COL_PAD_Y + r * (NODE_H + ROW_GAP),
    };
  });
  const posById = new Map(positioned.map((n) => [n.id, n]));

  const columns = Array.from({ length: maxCol + 1 }, (_, index) => {
    const ids = byColumn.get(index) ?? [];
    const label =
      ids
        .map((id) => posById.get(id)?.label)
        .filter(Boolean)
        .slice(0, 1)[0] ?? `Zone ${index + 1}`;
    return {
      index,
      x: PAD_X + index * (NODE_W + COL_GAP),
      label,
    };
  });

  const diagramHeight =
    COL_PAD_Y + maxRows * (NODE_H + ROW_GAP) - ROW_GAP + 8;
  const diagramWidth =
    PAD_X * 2 + (maxCol + 1) * (NODE_W + COL_GAP) - COL_GAP;

  const forwardEdges: LaidOutEdge[] = [];
  const backEdgesRaw: FlowEdge[] = [];
  for (const e of validEdges) {
    const s = posById.get(e.source);
    const t = posById.get(e.target);
    if (!s || !t) continue;
    if (t.column > s.column) {
      const x1 = s.x + NODE_W;
      const y1 = s.y + NODE_H / 2;
      const x2 = t.x;
      const y2 = t.y + NODE_H / 2;
      const midX = (x1 + x2) / 2;
      forwardEdges.push({
        ...e,
        path: `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`,
        labelX: midX,
        labelY: (y1 + y2) / 2 - 6,
      });
    } else {
      backEdgesRaw.push(e);
    }
  }

  const laneKeys: string[] = [];
  for (const e of backEdgesRaw) {
    const s = posById.get(e.source);
    const t = posById.get(e.target);
    const key = `${s?.column ?? 0}-${t?.column ?? 0}`;
    if (!laneKeys.includes(key)) laneKeys.push(key);
  }
  const backEdges: LaidOutEdge[] = backEdgesRaw.map((e) => {
    const s = posById.get(e.source);
    const t = posById.get(e.target);
    const key = `${s?.column ?? 0}-${t?.column ?? 0}`;
    const lane = laneKeys.indexOf(key);
    const laneY = diagramHeight + LANE_GAP + lane * LANE_H + LANE_H / 2;
    const x1 = (s?.x ?? 0) + NODE_W / 2;
    const y1 = (s?.y ?? 0) + NODE_H;
    const x2 = (t?.x ?? 0) + NODE_W / 2;
    const y2 = (t?.y ?? 0) + NODE_H;
    return {
      ...e,
      path: `M ${x1} ${y1} L ${x1} ${laneY} L ${x2} ${laneY} L ${x2} ${y2}`,
      labelX: (x1 + x2) / 2,
      labelY: laneY - 6,
    };
  });

  const height =
    diagramHeight + (laneKeys.length ? LANE_GAP + laneKeys.length * LANE_H : 0);
  return {
    nodes: positioned,
    forwardEdges,
    backEdges,
    columns,
    width: diagramWidth,
    height,
  };
}

export function FlowDiagramBlock({
  block,
  onCardExpand,
}: {
  block: GenUIBlock;
  onCardExpand?: (affordance: string, label: string) => void;
}) {
  const markerId = useId();
  const [step, setStep] = useState(0);
  const layout = useMemo(
    () => layoutFlowDiagram(block.nodes ?? [], block.edges ?? []),
    [block.nodes, block.edges],
  );
  // Walk left→right by column so teaching steps follow the pipeline.
  const walkNodes = useMemo(() => {
    if (!layout) return [];
    return [...layout.nodes].sort(
      (a, b) => a.column - b.column || a.row - b.row,
    );
  }, [layout]);
  if (!layout) return null;

  const arrowId = `flow-arrow-${markerId}`;
  const active = walkNodes[Math.min(step, Math.max(walkNodes.length - 1, 0))];
  const activeId = active?.id ?? null;

  return (
    <div>
      <DiagramLabel type="flow_diagram" title={block.title} />
      <FigureChrome>
        <p className="mb-2 text-[11px] text-mute">
          Click a component or use steps to walk the mechanism.
        </p>
        <div className="overflow-x-auto pb-1">
          <div
            className="relative mx-auto"
            style={{ width: layout.width, height: layout.height, minWidth: layout.width }}
          >
            <svg
              className="pointer-events-none absolute inset-0 overflow-visible"
              width={layout.width}
              height={layout.height}
              viewBox={`0 0 ${layout.width} ${layout.height}`}
            >
              <defs>
                <DiagramMarker id={arrowId} />
              </defs>
              {layout.columns.map((col) => (
                <rect
                  key={col.index}
                  x={col.x - 8}
                  y={0}
                  width={NODE_W + 16}
                  height={layout.height}
                  rx={12}
                  className={cn(
                    ZONE_BAND_FILLS[col.index % ZONE_BAND_FILLS.length],
                    "opacity-40",
                  )}
                />
              ))}
              {[...layout.forwardEdges, ...layout.backEdges].map((e, i) => {
                const isBack = i >= layout.forwardEdges.length;
                const touchesActive =
                  e.source === activeId || e.target === activeId;
                const labelW = Math.min(
                  120,
                  Math.max(48, (e.label?.length ?? 0) * 5.5 + 12),
                );
                return (
                  <g key={`${isBack ? "b" : "f"}-${i}`}>
                    <path
                      d={e.path}
                      fill="none"
                      className={
                        touchesActive
                          ? "stroke-ink"
                          : isBack
                            ? "stroke-mute"
                            : "stroke-hairline"
                      }
                      strokeOpacity={touchesActive ? 1 : isBack ? 0.55 : 0.9}
                      strokeWidth={touchesActive ? 2.25 : 1.5}
                      strokeDasharray={isBack ? "4 3" : undefined}
                      markerEnd={`url(#${arrowId})`}
                    />
                    {e.label && (
                      <g>
                        <rect
                          x={e.labelX - labelW / 2}
                          y={e.labelY - 10}
                          width={labelW}
                          height={16}
                          rx={4}
                          className="fill-canvas stroke-hairline"
                          strokeWidth={1}
                          opacity={0.95}
                        />
                        <text
                          x={e.labelX}
                          y={e.labelY + 2}
                          textAnchor="middle"
                          className="fill-mute text-[9px]"
                        >
                          {e.label.length > 22
                            ? `${e.label.slice(0, 20)}…`
                            : e.label}
                        </text>
                      </g>
                    )}
                  </g>
                );
              })}
            </svg>
            {layout.nodes.map((n) => {
              const zi = zoneIndex(n.label || n.id);
              const isActive = n.id === activeId;
              return (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => {
                    const idx = walkNodes.findIndex((w) => w.id === n.id);
                    if (idx >= 0) setStep(idx);
                    onCardExpand?.("mechanism_explainer", n.label);
                  }}
                  className={cn(
                    "absolute flex flex-col items-center justify-center rounded-[12px] border px-3 py-2 text-center shadow-sm transition-all",
                    ZONE_STYLES[zi],
                    isActive && "ring-2 ring-ink/25 ring-offset-1 ring-offset-canvas",
                  )}
                  style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H }}
                >
                  <span className="line-clamp-2 text-sm font-semibold leading-snug">
                    {n.label}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
        <WalkthroughControls
          index={step}
          total={walkNodes.length}
          onPrev={() => setStep((s) => Math.max(0, s - 1))}
          onNext={() => setStep((s) => Math.min(walkNodes.length - 1, s + 1))}
          label={active?.label}
        />
        {active?.detail && (
          <ExpandPanel
            eyebrow={active.label}
            text={active.detail}
            stepLabel={`Component ${step + 1}`}
          />
        )}
      </FigureChrome>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sequence diagram: actor lifelines + ordered messages, UML-style.
// ---------------------------------------------------------------------------

type SeqMessage = {
  source: string;
  target: string;
  label: string;
  order: number;
  note?: string | null;
};

const COL_W = 172;
const HEADER_H = 48;
const MSG_ROW_H = 56;
const LIFELINE_PAD = 20;
const SELF_LOOP_BULGE = 48;

type SeqRow = {
  message: SeqMessage;
  y: number;
  x1: number;
  x2: number;
  path: string;
  labelX: number;
};

type SeqLayout = {
  actors: { name: string; x: number }[];
  rows: SeqRow[];
  width: number;
  height: number;
};

function layoutSequenceDiagram(actors: string[], messages: SeqMessage[]): SeqLayout | null {
  if (actors.length < 2 || !messages.length) return null;
  const positionedActors = actors.map((name, i) => ({
    name,
    x: i * COL_W + COL_W / 2,
  }));
  const xByActor = new Map(positionedActors.map((a) => [a.name, a.x]));
  const sorted = [...messages].sort((a, b) => a.order - b.order);

  const rows: SeqRow[] = sorted.map((m, i) => {
    const y = HEADER_H + LIFELINE_PAD + (i + 1) * MSG_ROW_H;
    const x1 = xByActor.get(m.source) ?? 0;
    const x2 = xByActor.get(m.target) ?? 0;
    const selfLoop = m.source === m.target;
    const path = selfLoop
      ? `M ${x1} ${y - 10} C ${x1 + SELF_LOOP_BULGE} ${y - 10}, ${x1 + SELF_LOOP_BULGE} ${y + 10}, ${x1} ${y + 10}`
      : `M ${x1} ${y} L ${x2} ${y}`;
    return {
      message: m,
      y,
      x1,
      x2,
      path,
      labelX: selfLoop ? x1 + SELF_LOOP_BULGE + 8 : (x1 + x2) / 2,
    };
  });

  const width = Math.max(actors.length * COL_W, COL_W);
  const height = HEADER_H + LIFELINE_PAD + (sorted.length + 1) * MSG_ROW_H;
  return { actors: positionedActors, rows, width, height };
}

export function SequenceDiagramBlock({
  block,
  onCardExpand,
}: {
  block: GenUIBlock;
  onCardExpand?: (affordance: string, label: string) => void;
}) {
  const markerId = useId();
  const [step, setStep] = useState(0);
  const layout = useMemo(
    () => layoutSequenceDiagram(block.actors ?? [], block.messages ?? []),
    [block.actors, block.messages],
  );
  if (!layout) return null;

  const arrowId = `seq-arrow-${markerId}`;
  const activeIdx = Math.min(step, layout.rows.length - 1);
  const active = layout.rows[activeIdx];
  const headerW = COL_W - 16;

  return (
    <div>
      <DiagramLabel type="sequence_diagram" title={block.title} />
      <FigureChrome>
        <div className="overflow-x-auto pb-1">
          <div
            className="relative"
            style={{ width: layout.width, height: layout.height }}
          >
            <svg
              className="pointer-events-none absolute inset-0 overflow-visible"
              width={layout.width}
              height={layout.height}
              viewBox={`0 0 ${layout.width} ${layout.height}`}
            >
              <defs>
                <DiagramMarker id={arrowId} />
              </defs>
              {layout.actors.map((a, i) => (
                <line
                  key={a.name}
                  x1={a.x}
                  y1={HEADER_H}
                  x2={a.x}
                  y2={layout.height}
                  className={
                    active &&
                    (a.name === active.message.source ||
                      a.name === active.message.target)
                      ? "stroke-ink"
                      : "stroke-hairline"
                  }
                  strokeWidth={
                    active &&
                    (a.name === active.message.source ||
                      a.name === active.message.target)
                      ? 1.5
                      : 1
                  }
                  strokeDasharray="3 4"
                  opacity={i >= 0 ? 1 : 1}
                />
              ))}
              {layout.rows.map((r, i) => (
                <path
                  key={i}
                  d={r.path}
                  fill="none"
                  className={i === activeIdx ? "stroke-ink" : "stroke-mute"}
                  strokeWidth={i === activeIdx ? 2.25 : 1.5}
                  strokeOpacity={i === activeIdx ? 1 : 0.45}
                  markerEnd={`url(#${arrowId})`}
                />
              ))}
            </svg>
            {layout.actors.map((a) => {
              const zi = zoneIndex(a.name);
              const isActive =
                active &&
                (a.name === active.message.source ||
                  a.name === active.message.target);
              return (
                <div
                  key={a.name}
                  className={cn(
                    "absolute flex items-center justify-center rounded-[10px] border px-2 text-center shadow-sm",
                    ZONE_STYLES[zi],
                    isActive && "ring-2 ring-ink/20 ring-offset-1 ring-offset-canvas",
                  )}
                  style={{
                    left: a.x - headerW / 2,
                    top: 0,
                    width: headerW,
                    height: HEADER_H,
                  }}
                >
                  <span className="line-clamp-2 text-xs font-semibold">
                    {a.name}
                  </span>
                </div>
              );
            })}
            {layout.rows.map((r, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setStep(i);
                  onCardExpand?.(
                    "interaction_walkthrough",
                    r.message.label,
                  );
                }}
                className={cn(
                  "absolute -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                  i === activeIdx
                    ? "border-ink bg-ink text-[var(--canvas)]"
                    : "border-hairline bg-canvas text-body hover:bg-canvas-soft",
                )}
                style={{ left: r.labelX, top: r.y - 4 }}
              >
                <span className="mr-1 opacity-70">{i + 1}.</span>
                {r.message.label}
              </button>
            ))}
          </div>
        </div>
        <WalkthroughControls
          index={activeIdx}
          total={layout.rows.length}
          onPrev={() => setStep((s) => Math.max(0, s - 1))}
          onNext={() =>
            setStep((s) => Math.min(layout.rows.length - 1, s + 1))
          }
          label={active?.message.label}
        />
        {active?.message.note && (
          <ExpandPanel
            eyebrow={active.message.label}
            text={active.message.note}
            stepLabel={`Step ${activeIdx + 1}`}
          />
        )}
      </FigureChrome>
    </div>
  );
}
