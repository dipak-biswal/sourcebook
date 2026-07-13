import {
  Activity,
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronRight,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CardSkeleton } from "@/components/ui/skeleton";
import { cn, formatDateTime } from "@/lib/utils";
import { DailyTrendChart } from "./DailyTrendChart";
import { UsageDetailPanel } from "./UsageDetailPanel";

import type { UsagePageViewProps } from "@/types/page-props";
import { confirmAction } from "@/lib/confirm";
import { useToast } from "@/components/ui/toast";

type SortDir = "asc" | "desc";
type SortCol = "created_at" | "kind" | "model" | "total_tokens";

export function UsagePageView({
  data,
  error,
  loading,
  onRefresh,
  onLogout,
}: UsagePageViewProps) {
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState<SortCol>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const { success, error: toastError } = useToast();

  const rows = useMemo(() => {
    let list = data?.recent ?? [];
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (r) =>
          r.kind.toLowerCase().includes(q) ||
          (r.model ?? "").toLowerCase().includes(q),
      );
    }
    list = [...list].sort((a, b) => {
      let cmp = 0;
      if (sortCol === "created_at") cmp = a.created_at.localeCompare(b.created_at);
      else if (sortCol === "kind") cmp = a.kind.localeCompare(b.kind);
      else if (sortCol === "model") cmp = (a.model ?? "").localeCompare(b.model ?? "");
      else if (sortCol === "total_tokens") cmp = (a.total_tokens ?? 0) - (b.total_tokens ?? 0);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return list;
  }, [data?.recent, search, sortCol, sortDir]);

  function toggleSort(col: SortCol) {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir(col === "created_at" ? "desc" : "asc");
    }
  }

  async function handleDeleteRow(id: string) {
    if (!(await confirmAction("Delete this event?", "This cannot be undone."))) return;
    try {
      await api.deleteUsageEvent(id);
      if (selectedEventId === id) setSelectedEventId(null);
      onRefresh();
      success("Event deleted");
    } catch (err) {
      toastError("Delete failed", String(err));
    }
  }

  async function handleDeleteAll() {
    if (!(await confirmAction("Delete all events?", "This cannot be undone. All usage history will be permanently removed."))) return;
    try {
      await api.deleteAllUsageEvents();
      setSelectedEventId(null);
      onRefresh();
      success("All events deleted");
    } catch (err) {
      toastError("Delete failed", String(err));
    }
  }

  function SortIcon({ col }: { col: SortCol }) {
    if (sortCol !== col) return <ArrowUpDown className="h-3 w-3" strokeWidth={1.5} />;
    return sortDir === "asc"
      ? <ArrowUp className="h-3 w-3" strokeWidth={1.5} />
      : <ArrowDown className="h-3 w-3" strokeWidth={1.5} />;
  }

  const content = (
    <>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-ink" strokeWidth={1.5} />
            <h1 className="text-display-sm font-semibold tracking-tight text-ink">
              Usage
            </h1>
          </div>
          <p className="mt-1 text-body-sm text-mute">
            Token usage logged for your account — chat, agents, suggestions,
            study guides, and embeddings.
            OpenAI dashboard is the source of truth for billing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data && data.event_count > 0 && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="text-red-500 hover:text-red-600"
              onClick={handleDeleteAll}
            >
              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
              Delete all
            </Button>
          )}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={loading}
            onClick={onRefresh}
          >
            {loading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="danger" className="mb-4">
          {error}
        </Alert>
      )}

      {loading && !data ? (
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <CardSkeleton />
          <CardSkeleton />
        </div>
      ) : (
        <>
          <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-mute">
                Events
              </div>
              <div className="mt-1 text-2xl font-semibold text-ink">
                {data?.event_count ?? 0}
              </div>
            </div>
            <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-mute">
                Total tokens (logged)
              </div>
              <div className="mt-1 text-2xl font-semibold text-ink">
                {(data?.total_tokens ?? 0).toLocaleString()}
              </div>
            </div>
          </div>

          {data?.daily_totals && data.daily_totals.length > 0 && (
            <div className="mb-6">
              <DailyTrendChart data={data.daily_totals} />
            </div>
          )}

          <div className="rounded-vercel-md border border-hairline bg-canvas">
            <div className="flex items-center justify-between border-b border-hairline px-4 py-3">
              <span className="text-sm font-semibold text-ink">
                Recent activity
              </span>
              {data?.recent && data.recent.length > 0 && (
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-mute" strokeWidth={1.5} />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Filter by kind or model…"
                    className="h-8 w-48 rounded-[6px] border border-hairline bg-canvas pl-7 pr-2 text-xs text-ink outline-none placeholder:text-mute focus:border-ink"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch("")}
                      className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-mute hover:text-ink"
                    >
                      <X className="h-3 w-3" strokeWidth={1.5} />
                    </button>
                  )}
                </div>
              )}
            </div>
            {rows.length === 0 ? (
              <p className="px-4 py-10 text-center text-sm text-mute">
                {search
                  ? "No events match your filter."
                  : "No usage yet. Send a chat message or run an agent, then refresh."}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-hairline text-xs text-mute">
                      <Th label="When" icon={<SortIcon col="created_at" />} onClick={() => toggleSort("created_at")} />
                      <Th label="Kind" icon={<SortIcon col="kind" />} onClick={() => toggleSort("kind")} />
                      <Th label="Model" icon={<SortIcon col="model" />} onClick={() => toggleSort("model")} />
                      <Th label="Tokens" icon={<SortIcon col="total_tokens" />} onClick={() => toggleSort("total_tokens")} />
                      <th className="px-4 py-2 font-medium">Notes</th>
                      <th className="w-8" />
                      <th className="w-8" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const estimated =
                        row.meta && typeof row.meta === "object" && "estimated" in row.meta && row.meta.estimated === true;
                      const denied =
                        row.meta && typeof row.meta === "object" && "denied" in row.meta && row.meta.denied === true;
                      const isOpen = selectedEventId === row.id;
                      return (
                        <tr
                          key={row.id}
                          className={cn(
                            "group border-b border-hairline transition-colors last:border-0",
                            "hover:bg-canvas-soft",
                            isOpen && "bg-canvas-soft-2",
                          )}
                        >
                          <td
                            className="cursor-pointer px-4 py-2.5 text-body whitespace-nowrap"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            {formatDateTime(row.created_at)}
                          </td>
                          <td
                            className="cursor-pointer px-4 py-2.5 text-ink"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            {row.kind}
                          </td>
                          <td
                            className="cursor-pointer px-4 py-2.5 text-body max-w-[160px] truncate"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            {row.model ?? "—"}
                          </td>
                          <td
                            className="cursor-pointer px-4 py-2.5 font-medium text-ink"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            {row.total_tokens != null ? row.total_tokens.toLocaleString() : "—"}
                            {row.prompt_tokens != null && row.completion_tokens != null && (
                              <span className="ml-1 text-xs font-normal text-mute">
                                ({row.prompt_tokens}+{row.completion_tokens})
                              </span>
                            )}
                          </td>
                          <td
                            className="cursor-pointer px-4 py-2.5"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            <div className="flex flex-wrap gap-1">
                              {estimated && <Badge variant="secondary">estimated</Badge>}
                              {denied && <Badge variant="warning">denied</Badge>}
                              {!estimated && !denied && <span className="text-mute">—</span>}
                            </div>
                          </td>
                          <td
                            className="cursor-pointer px-2 py-2.5"
                            onClick={() => setSelectedEventId(isOpen ? null : row.id)}
                          >
                            <ChevronRight
                              className={cn(
                                "h-3.5 w-3.5 text-mute transition-transform",
                                isOpen && "rotate-90",
                              )}
                              strokeWidth={1.5}
                            />
                          </td>
                          <td className="px-2 py-2.5">
                            <button
                              type="button"
                              title="Delete event"
                              className="rounded p-1 text-mute opacity-0 transition-opacity hover:bg-canvas-soft-2 hover:text-red-500 group-hover:opacity-100"
                              onClick={() => handleDeleteRow(row.id)}
                            >
                              <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </>
  );

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />
      <div className="flex min-h-0 flex-1">
        <main
          id="main-content"
          tabIndex={-1}
          className={cn(
            "document-scroll min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-6 outline-none sm:px-6 sm:py-8",
            selectedEventId && "border-r border-hairline",
          )}
        >
          <div className="mx-auto max-w-3xl">{content}</div>
        </main>
        {selectedEventId && (
          <aside className="document-scroll w-[480px] shrink-0 overflow-y-auto border-l border-hairline bg-canvas">
            <UsageDetailPanel
              eventId={selectedEventId}
              onClose={() => setSelectedEventId(null)}
            />
          </aside>
        )}
      </div>
    </div>
  );
}

function Th({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <th
      className="cursor-pointer px-4 py-2 font-medium select-none hover:text-ink"
      onClick={onClick}
    >
      <span className="inline-flex items-center gap-1">
        {label}
        {icon}
      </span>
    </th>
  );
}
