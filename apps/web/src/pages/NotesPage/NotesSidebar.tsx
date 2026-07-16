import { Loader2, Plus, StickyNote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { WorkspaceSelect } from "@/components/workspace/WorkspaceSelect";
import { formatDate } from "@/lib/utils";
import { useNotesPage } from "./notes-page-context";

export function NotesSidebar({
  onAfterNavigate,
}: {
  onAfterNavigate?: () => void;
} = {}) {
  const {
    workspaces,
    workspaceId,
    notes,
    selected,
    onChangeWorkspace,
    onRefreshWorkspaces,
    onSelect,
    onCreate,
    creating,
  } = useNotesPage();

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline p-4">
        <div className="flex items-center gap-2">
          <StickyNote className="h-4 w-4 text-ink" strokeWidth={1.5} />
          <h2 className="text-body-sm font-semibold text-ink">Notes</h2>
        </div>

        {workspaces.length > 0 && (
          <div className="mt-3 space-y-2">
            <WorkspaceSelect
              workspaces={workspaces}
              workspaceId={workspaceId}
              onChange={onChangeWorkspace}
              onRefresh={onRefreshWorkspaces}
            />
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="h-8 w-full"
              disabled={!workspaceId || creating}
              onClick={() => void onCreate()}
            >
              {creating ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
              New note
            </Button>
          </div>
        )}
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        {notes.length === 0 ? (
          <p className="px-2 py-3 text-xs text-mute">
            No notes yet. Click New note or approve a create_note agent run.
          </p>
        ) : (
          <ul className="space-y-1">
            {notes.map((n) => (
              <li key={n.id}>
                <button
                  type="button"
                  onClick={() => {
                    onSelect(n);
                    onAfterNavigate?.();
                  }}
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
                    {formatDate(n.created_at)}
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
