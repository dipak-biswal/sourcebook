import { Bot, StickyNote, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { agentStatusVariant } from "@/components/agents/agent-utils";
import { Badge } from "@/components/ui/badge";
import { ListSkeleton } from "@/components/ui/skeleton";
import { formatDate } from "@/lib/utils";
import { useAgentPage } from "./agent-page-context";

export function AgentSidebar() {
  const {
    runs,
    notes,
    loading,
    onSelectRun,
    onSidebarClose,
    onDeleteNote,
    onDeleteRun,
  } = useAgentPage();

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline p-4">
        <div className="flex items-center gap-2">
          <Bot className="h-4 w-4 text-ink" strokeWidth={1.5} />
          <h2 className="text-body-sm font-semibold text-ink">Runs</h2>
        </div>
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          Runs ({runs.length})
        </div>
        {loading ? (
          <ListSkeleton rows={4} />
        ) : runs.length === 0 ? (
          <p className="px-2 py-3 text-xs text-mute">
            No runs yet. Start one on the right.
          </p>
        ) : (
          <ul className="space-y-1">
            {runs.map((r) => (
              <li key={r.id} className="group rounded-[6px] border border-transparent hover:border-hairline hover:bg-canvas-soft-2">
                <div className="flex items-start gap-1 px-2 py-2">
                  <div className="min-w-0 flex-1">
                    <button
                      type="button"
                      onClick={() => {
                        onSelectRun(r.id);
                        onSidebarClose();
                      }}
                      className="w-full text-left"
                    >
                      <div className="line-clamp-2 text-sm font-medium text-ink">
                        {r.goal}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant={agentStatusVariant(r.status)}>
                          {r.status}
                        </Badge>
                        <span className="text-[11px] text-mute">
                          {formatDate(r.created_at)}
                        </span>
                      </div>
                    </button>
                  </div>
                  <button
                    type="button"
                    title="Delete run"
                    className="mt-0.5 shrink-0 rounded p-1 opacity-0 text-mute transition-opacity hover:bg-canvas-soft-2 hover:text-ink group-hover:opacity-100"
                    onClick={() => onDeleteRun(r.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}

        <div className="mb-1 mt-4 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          Notes ({notes.length})
        </div>
        {notes.length === 0 ? (
          <p className="px-2 py-2 text-xs text-mute">
            No notes yet. Approve a create_note run to add one.
          </p>
        ) : (
          <ul className="space-y-1">
            {notes.map((n) => (
              <li
                key={n.id}
                className="group rounded-[6px] border border-hairline bg-canvas px-2 py-2"
              >
                <div className="flex items-start gap-2">
                  <StickyNote
                    className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute"
                    strokeWidth={1.5}
                  />
                  <div className="min-w-0 flex-1">
                    <Link
                      to={`/notes/${n.id}`}
                      className="truncate text-sm font-medium text-ink hover:underline"
                    >
                      {n.title}
                    </Link>
                    <div className="mt-0.5 line-clamp-2 text-xs text-mute">
                      {n.body || "—"}
                    </div>
                    <div className="mt-1 text-[11px] text-mute">
                      {formatDate(n.created_at)}
                    </div>
                  </div>
                  <button
                    type="button"
                    title="Delete note"
                    className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                    onClick={() => onDeleteNote(n.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
