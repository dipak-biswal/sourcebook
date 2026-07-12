import { StickyNote } from "lucide-react";
import { useNotesPage } from "./NotesPageContext";

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function NotesSidebar() {
  const {
    workspaces,
    workspaceId,
    notes,
    selected,
    onChangeWorkspace,
    onSelect,
  } = useNotesPage();

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline p-4">
        <div className="flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-ink" strokeWidth={1.5} />
          <h2 className="text-body-sm font-semibold text-ink">Notes</h2>
        </div>

        {workspaces.length > 0 && (
          <label className="mt-3 block">
            <span className="mb-1 block text-xs text-mute">Workspace</span>
            <select
              value={workspaceId}
              onChange={(e) => onChangeWorkspace(e.target.value)}
              className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>{w.name}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        {notes.length === 0 ? (
          <p className="px-2 py-3 text-xs text-mute">
            No notes yet. Approve a create_note run to add one.
          </p>
        ) : (
          <ul className="space-y-1">
            {notes.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => { onSelect(n); }}
                  className={
                    "w-full rounded-[6px] border px-2 py-2 text-left transition-colors" +
                    (n.id === selected?.id
                      ? " border-hairline bg-canvas-soft-2"
                      : " border-transparent hover:bg-canvas-soft-2")
                  }
                >
                  <div className="truncate text-sm font-medium text-ink">
                    {n.title}
                  </div>
                  <div className="mt-0.5 line-clamp-2 text-xs text-mute">
                    {n.body || "—"}
                  </div>
                  <div className="mt-1 text-[11px] text-mute">
                    {formatWhen(n.created_at)}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
