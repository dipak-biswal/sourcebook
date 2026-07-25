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
    <div
      className={cn(
        "flex items-center gap-2.5 rounded-[6px] px-2 py-1.5",
        !disabled && "hover:bg-canvas-soft-2",
        disabled && "opacity-50",
      )}
    >
      <Icon className="h-4 w-4 shrink-0 text-body" strokeWidth={1.5} />
      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ink">
        {connector.name}
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        aria-label={`${enabled ? "Disable" : "Enable"} ${connector.name}`}
        disabled={disabled}
        onClick={onToggle}
        className={cn(
          "relative h-5 w-9 shrink-0 rounded-full transition-colors",
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
    </div>
  );
}

/** Compact MCP toggles beside Run agent — icon, name, switch only. */
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
        aria-label="MCP connectors"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex h-9 items-center gap-1.5 rounded-[6px] border border-hairline bg-canvas px-2.5 text-[13px] font-medium transition-colors",
          open
            ? "border-ink bg-canvas-soft-2 text-ink"
            : "text-body hover:bg-canvas-soft-2 hover:text-ink",
          (disabled || connectorsLoading) && "cursor-not-allowed opacity-50",
        )}
      >
        <Plug className="h-3.5 w-3.5" strokeWidth={1.5} />
        <span>MCP</span>
        {enabledCount > 0 && (
          <span className="tabular-nums text-mute">{enabledCount}</span>
        )}
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-mute transition-transform",
            open && "rotate-180",
          )}
          strokeWidth={1.5}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1.5 w-52 overflow-hidden rounded-[8px] border border-hairline bg-canvas py-1 shadow-[var(--elevation-card)]"
        >
          {mcpList.length === 0 ? (
            <p className="px-3 py-2 text-xs text-mute">
              {connectorsLoading ? "Loading…" : "None"}
            </p>
          ) : (
            <ul>
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
