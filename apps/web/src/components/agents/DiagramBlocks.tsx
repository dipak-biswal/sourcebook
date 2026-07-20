import { useId, useMemo, useState } from "react";
import { Workflow } from "lucide-react";
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

function ExpandPanel({
  eyebrow,
  text,
}: {
  eyebrow: string;
  text: string;
}) {
  return (
    <div className="mt-2 rounded-[8px] border border-hairline bg-canvas-soft px-3 py-2.5 text-xs leading-relaxed text-body">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
        {eyebrow}
      </div>
      {text}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Flow diagram: layered-DAG layout with deterministic back-edge arc routing.
// ---------------------------------------------------------------------------

type FlowNode = { id: string; label: string; detail?: string | null };
type FlowEdge = { source: string; target: string; label?: string | null };

const NODE_W = 176;
const NODE_H = 64;
const COL_GAP = 88;
const ROW_GAP = 20;
const LANE_GAP = 24;
const LANE_H = 28;

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
  for (const e of validEdges) {
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1);
    outDegree.set(e.source, (outDegree.get(e.source) ?? 0) + 1);
    adj.get(e.source)?.push(e.target);
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

  // Multi-source BFS: shortest-path layering, cycle-safe by construction
  // (a node is only ever assigned a column the first time it's reached).
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
      if (!column.has(next)) {
        column.set(next, col + 1);
        queue.push(next);
      }
    }
  }
  for (const n of nodes) {
    if (!column.has(n.id)) column.set(n.id, 0);
  }

  const byColumn = new Map<number, string[]>();
  for (const n of nodes) {
    const c = column.get(n.id) ?? 0;
    if (!byColumn.has(c)) byColumn.set(c, []);
    byColumn.get(c)?.push(n.id);
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
    return { ...n, column: col, row: r, x: col * (NODE_W + COL_GAP), y: r * (NODE_H + ROW_GAP) };
  });
  const posById = new Map(positioned.map((n) => [n.id, n]));

  const diagramHeight = maxRows * (NODE_H + ROW_GAP) - ROW_GAP;
  const diagramWidth = (maxCol + 1) * (NODE_W + COL_GAP) - COL_GAP;

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

  const height = diagramHeight + (laneKeys.length ? LANE_GAP + laneKeys.length * LANE_H : 0);
  return { nodes: positioned, forwardEdges, backEdges, width: diagramWidth, height };
}

export function FlowDiagramBlock({
  block,
  onCardExpand,
}: {
  block: GenUIBlock;
  onCardExpand?: (affordance: string, label: string) => void;
}) {
  const markerId = useId();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const layout = useMemo(
    () => layoutFlowDiagram(block.nodes ?? [], block.edges ?? []),
    [block.nodes, block.edges],
  );
  if (!layout) return null;

  const arrowId = `flow-arrow-${markerId}`;
  const expandedNode = layout.nodes.find((n) => n.id === expandedId);

  return (
    <div>
      <DiagramLabel type="flow_diagram" title={block.title} />
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
            {layout.forwardEdges.map((e, i) => (
              <g key={`fwd-${i}`}>
                <path
                  d={e.path}
                  fill="none"
                  className="stroke-hairline"
                  strokeWidth={1.5}
                  markerEnd={`url(#${arrowId})`}
                />
                {e.label && (
                  <text
                    x={e.labelX}
                    y={e.labelY}
                    textAnchor="middle"
                    className="fill-mute text-[10px]"
                  >
                    {e.label}
                  </text>
                )}
              </g>
            ))}
            {layout.backEdges.map((e, i) => (
              <g key={`back-${i}`}>
                <path
                  d={e.path}
                  fill="none"
                  className="stroke-mute"
                  strokeOpacity={0.55}
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                  markerEnd={`url(#${arrowId})`}
                />
                {e.label && (
                  <text
                    x={e.labelX}
                    y={e.labelY}
                    textAnchor="middle"
                    className="fill-mute text-[10px]"
                  >
                    {e.label}
                  </text>
                )}
              </g>
            ))}
          </svg>
          {layout.nodes.map((n) => (
            <button
              key={n.id}
              type="button"
              onClick={() => {
                const next = expandedId === n.id ? null : n.id;
                setExpandedId(next);
                if (next) onCardExpand?.("mechanism_explainer", n.label);
              }}
              className={cn(
                "absolute flex flex-col items-center justify-center rounded-[10px] border px-3 py-2 text-center transition-colors",
                expandedId === n.id
                  ? "border-ink bg-canvas-soft-2"
                  : "border-hairline bg-canvas hover:bg-canvas-soft",
              )}
              style={{ left: n.x, top: n.y, width: NODE_W, height: NODE_H }}
            >
              <span className="line-clamp-2 text-xs font-medium text-ink">{n.label}</span>
            </button>
          ))}
        </div>
      </div>
      {expandedNode?.detail && (
        <ExpandPanel eyebrow={expandedNode.label} text={expandedNode.detail} />
      )}
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

const COL_W = 160;
const HEADER_H = 44;
const MSG_ROW_H = 52;
const LIFELINE_PAD = 20;
const SELF_LOOP_BULGE = 44;

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
  const positionedActors = actors.map((name, i) => ({ name, x: i * COL_W + COL_W / 2 }));
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
    return { message: m, y, x1, x2, path, labelX: selfLoop ? x1 + SELF_LOOP_BULGE + 8 : (x1 + x2) / 2 };
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
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const layout = useMemo(
    () => layoutSequenceDiagram(block.actors ?? [], block.messages ?? []),
    [block.actors, block.messages],
  );
  if (!layout) return null;

  const arrowId = `seq-arrow-${markerId}`;
  const expanded = expandedIdx !== null ? layout.rows[expandedIdx] : undefined;
  const headerW = COL_W - 16;

  return (
    <div>
      <DiagramLabel type="sequence_diagram" title={block.title} />
      <div className="overflow-x-auto pb-1">
        <div className="relative" style={{ width: layout.width, height: layout.height }}>
          <svg
            className="pointer-events-none absolute inset-0 overflow-visible"
            width={layout.width}
            height={layout.height}
            viewBox={`0 0 ${layout.width} ${layout.height}`}
          >
            <defs>
              <DiagramMarker id={arrowId} />
            </defs>
            {layout.actors.map((a) => (
              <line
                key={a.name}
                x1={a.x}
                y1={HEADER_H}
                x2={a.x}
                y2={layout.height}
                className="stroke-hairline"
                strokeWidth={1}
                strokeDasharray="3 4"
              />
            ))}
            {layout.rows.map((r, i) => (
              <path
                key={i}
                d={r.path}
                fill="none"
                className={i === expandedIdx ? "stroke-ink" : "stroke-mute"}
                strokeWidth={1.5}
                markerEnd={`url(#${arrowId})`}
              />
            ))}
          </svg>
          {layout.actors.map((a) => (
            <div
              key={a.name}
              className="absolute flex items-center justify-center rounded-[8px] border border-hairline bg-canvas px-2 text-center"
              style={{ left: a.x - headerW / 2, top: 0, width: headerW, height: HEADER_H }}
            >
              <span className="line-clamp-2 text-xs font-semibold text-ink">{a.name}</span>
            </div>
          ))}
          {layout.rows.map((r, i) => (
            <button
              key={i}
              type="button"
              onClick={() => {
                const next = expandedIdx === i ? null : i;
                setExpandedIdx(next);
                if (next !== null) onCardExpand?.("interaction_walkthrough", r.message.label);
              }}
              className={cn(
                "absolute -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors",
                i === expandedIdx
                  ? "border-ink bg-canvas-soft-2 text-ink"
                  : "border-hairline bg-canvas text-body hover:bg-canvas-soft",
              )}
              style={{ left: r.labelX, top: r.y - 4 }}
            >
              {r.message.label}
            </button>
          ))}
        </div>
      </div>
      {expanded?.message.note && (
        <ExpandPanel eyebrow={expanded.message.label} text={expanded.message.note} />
      )}
    </div>
  );
}
