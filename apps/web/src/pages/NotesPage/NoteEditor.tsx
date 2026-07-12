import { useState, type FormEvent } from "react";
import { Loader2, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useNotesPage } from "./NotesPageContext";

export function NoteEditor() {
  const {
    selected,
    saving,
    onSave,
    onDelete,
  } = useNotesPage();
  const [title, setTitle] = useState(selected?.title ?? "");
  const [body, setBody] = useState(selected?.body ?? "");

  if (!selected) {
    return (
      <div className="py-12 text-center text-sm text-mute">
        Select a note from the sidebar to view or edit it.
      </div>
    );
  }

  function handleSave(e: FormEvent) {
    e.preventDefault();
    onSave(title, body);
  }

  return (
    <form onSubmit={handleSave} className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          <Button
            type="submit"
            size="sm"
            className="rounded-[6px]"
            disabled={saving}
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Save className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Save
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => onDelete(selected.id)}
          >
            <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
          </Button>
        </div>
      </div>

      <Input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Note title"
        className="text-lg font-semibold"
      />

      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Note body…"
        rows={15}
        className="w-full resize-y rounded-[6px] border border-hairline bg-canvas px-3 py-2 text-sm text-body placeholder:text-mute focus:outline-none focus:ring-2 focus:ring-ink/25"
      />
    </form>
  );
}
