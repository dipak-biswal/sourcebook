import { useEffect, useRef, useState } from "react";
import { ChevronDown, Plug, Workflow } from "lucide-react";
import type { AgentConnector } from "@/api";
import { cn } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

const MCP_ICONS: Record<string, typeof Plug> = {
  diagram: Workflow,
};

function McpToggleRow({
  connector,
  enabled,
  onToggle,
  disabled,
}: {
  connector: AgentConnector;
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
}) {
  const Icon = MCP_ICONS[connector.icon] ?? Plug;

  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2.5 rounded-[8px] px-2.5 py-2 transition-colors",
        disabled ? "opacity-50" : "hover:bg-canvas-soft-2",
      )}
    >
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] border border-hairline bg-canvas-soft">
        <Icon className="h-3.5 w-3.5 text-ink" strokeWidth={1.5} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-1.5">
          <span className="text-[13px] font-medium text-ink">{connector.name}</span>
          <span className="rounded-full border border-hairline px-1.5 py-0.5 text-[10px] text-mute">
            MCP
          </span>
        </span>
        <span className="mt-0.5 block text-[11px] leading-snug text-mute">
          {connector.description}
        </span>
        {connector.install_hint && (
          <code className="mt-1 inline-block rounded bg-canvas-soft-2 px-1 py-0.5 font-mono text-[10px] text-ink">
            {connector.install_hint}
          </code>
        )}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`${enabled ? "Disable" : "Enable"} ${connector.name}`}
        disabled={disabled}
        onClick={(e) => {
          e.preventDefault();
          onToggle();
        }}
        className={cn(
          "relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition-colors",
          enabled ? "bg-ink" : "bg-canvas-soft-2 ring-1 ring-hairline",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-[var(--canvas)] shadow transition-transform",
            enabled ? "left-4" : "left-0.5",
          )}
        />
      </button>
    </label>
  );
}

/** Dropdown of MCP connectors with on/off toggles — sits beside Run agent. */
export function AgentMcpMenu({ disabled }: { disabled?: boolean }) {
  const {
    connectors,
    connectorsLoading,
    enabledMcpIds,
    onToggleMcp,
  } = useAgentPage();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const mcpList =
    connectors?.mcp_connectors ??
    connectors?.connectors?.filter((c) => c.kind === "mcp") ??
    [];
  const enabledCount = mcpList.filter((c) => enabledMcpIds.has(c.id)).length;

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        disabled={disabled || connectorsLoading}
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex h-9 items-center gap-1.5 rounded-[6px] border border-hairline bg-canvas px-3 text-[13px] font-medium transition-colors",
          open
            ? "border-ink bg-canvas-soft-2 text-ink"
            : "text-body hover:bg-canvas-soft-2 hover:text-ink",
          (disabled || connectorsLoading) && "cursor-not-allowed opacity-50",
        )}
      >
        <Plug className="h-3.5 w-3.5" strokeWidth={1.5} />
        MCP
        {enabledCount > 0 && (
          <span className="rounded-full bg-ink px-1.5 py-0.5 text-[10px] font-semibold text-[var(--canvas)]">
            {enabledCount}
          </span>
        )}
        <ChevronDown
          className={cn("h-3.5 w-3.5 text-mute transition-transform", open && "rotate-180")}
          strokeWidth={1.5}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute left-0 z-50 mt-1.5 w-[min(100vw-2rem,20rem)] overflow-hidden rounded-[10px] border border-hairline bg-canvas shadow-[var(--elevation-card)] sm:left-auto sm:right-0"
        >
          <div className="border-b border-hairline bg-canvas-soft px-3 py-2">
            <p className="text-[12px] font-semibold text-ink">MCP connectors</p>
            <p className="mt-0.5 text-[11px] text-mute">
              Toggle external tools for this agent. Built-in document tools stay on.
            </p>
          </div>

          {mcpList.length === 0 ? (
            <p className="px-3 py-4 text-center text-xs text-mute">
              {connectorsLoading ? "Loading…" : "No MCP connectors configured."}
            </p>
          ) : (
            <ul className="max-h-72 overflow-y-auto p-1.5">
              {mcpList.map((c) => (
                <li key={c.id}>
                  <McpToggleRow
                    connector={c}
                    enabled={enabledMcpIds.has(c.id)}
                    onToggle={() => onToggleMcp(c.id)}
                    disabled={disabled}
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
