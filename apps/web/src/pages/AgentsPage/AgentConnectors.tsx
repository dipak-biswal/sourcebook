import {
  Calendar,
  FileText,
  Files,
  Globe,
  LayoutTemplate,
  Link2,
  Plug,
  Search,
  StickyNote,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import type { AgentConnector } from "@/api";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

const ICON_MAP: Record<string, LucideIcon> = {
  files: Files,
  search: Search,
  file: FileText,
  globe: Globe,
  link: Link2,
  note: StickyNote,
  calendar: Calendar,
  layout: LayoutTemplate,
  diagram: Workflow,
  tool: Plug,
};

const STATUS_LABEL: Record<AgentConnector["status"], string> = {
  available: "Available",
  configured: "Configured",
  coming_soon: "Coming soon",
  disabled: "Disabled",
};

const KIND_LABEL: Record<AgentConnector["kind"], string> = {
  builtin: "Built-in",
  mcp: "MCP",
  pipeline: "Pipeline",
};

const PHASE_LABEL: Record<AgentConnector["phase"], string> = {
  main: "Main agent",
  visual: "Visual summary",
  both: "Main + visual",
};

function statusClass(status: AgentConnector["status"]): string {
  switch (status) {
    case "available":
      return "bg-success-soft text-success-text border-success-border";
    case "configured":
      return "bg-canvas-soft-2 text-ink border-hairline";
    case "coming_soon":
      return "bg-warning-soft text-warning-text border-warning-border";
    case "disabled":
      return "bg-canvas-soft text-mute border-hairline";
  }
}

function ConnectorCard({ connector }: { connector: AgentConnector }) {
  const Icon = ICON_MAP[connector.icon] ?? Plug;
  const isMcpPending = connector.kind === "mcp" && connector.status === "coming_soon";

  return (
    <li
      className={cn(
        "rounded-[8px] border border-hairline bg-canvas p-3 transition-colors",
        isMcpPending && "border-dashed",
      )}
    >
      <div className="flex items-start gap-2.5">
        <span
          className={cn(
            "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] border border-hairline bg-canvas-soft",
            connector.status === "coming_soon" && "opacity-70",
          )}
        >
          <Icon className="h-3.5 w-3.5 text-ink" strokeWidth={1.5} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium text-ink">{connector.name}</span>
            <span
              className={cn(
                "rounded-full border px-1.5 py-0.5 text-[10px] font-medium",
                statusClass(connector.status),
              )}
            >
              {STATUS_LABEL[connector.status]}
            </span>
            <span className="rounded-full border border-hairline px-1.5 py-0.5 text-[10px] text-mute">
              {KIND_LABEL[connector.kind]}
            </span>
          </div>
          <p className="mt-1 text-[11px] leading-relaxed text-body">
            {connector.description}
          </p>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px] text-mute">
            <span>{PHASE_LABEL[connector.phase]}</span>
            {connector.requires_approval && (
              <span className="font-medium text-warning-text">Needs approval</span>
            )}
            {connector.install_hint && (
              <code className="rounded bg-canvas-soft-2 px-1 py-0.5 font-mono text-[10px] text-ink">
                {connector.install_hint}
              </code>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

export function AgentConnectors() {
  const { connectors, connectorsLoading } = useAgentPage();

  if (connectorsLoading && !connectors) {
    return (
      <section className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4">
        <h2 className="text-sm font-semibold text-ink">Connectors</h2>
        <p className="mt-2 text-xs text-mute">Loading available tools…</p>
      </section>
    );
  }

  if (!connectors?.connectors?.length) return null;

  const { connectors: items, counts, mcp_enabled } = connectors;
  const ready = counts.available + counts.configured;

  return (
    <section className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold text-ink">Connectors</h2>
          <p className="mt-1 text-xs text-mute">
            Tools the agent can use — built-in workspace tools, visual pipeline,
            and MCP servers (e.g. draw.io).
          </p>
        </div>
        <div className="text-right text-[11px] text-mute">
          <div>
            <span className="font-medium text-ink">{ready}</span> ready
            {counts.coming_soon > 0 && (
              <>
                {" · "}
                <span className="font-medium text-warning-text">
                  {counts.coming_soon}
                </span>{" "}
                coming soon
              </>
            )}
          </div>
          <div className="mt-0.5">
            MCP master: {mcp_enabled ? "on" : "off"}
          </div>
        </div>
      </div>

      <ul className="mt-3 grid gap-2 sm:grid-cols-2">
        {items.map((c) => (
          <ConnectorCard key={c.id} connector={c} />
        ))}
      </ul>
    </section>
  );
}
