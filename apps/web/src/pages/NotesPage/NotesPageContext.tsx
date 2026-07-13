import { useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, type Note } from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { useNote, useNotes, useWorkspaces } from "@/hooks/queries";
import { NotesPageContext } from "./notes-page-context";

export function NotesPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { noteId } = useParams();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle(noteId ? "Edit note" : "Notes");

  const [workspaceId, setWorkspaceId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const { data: workspaces = [] } = useWorkspaces();
  const effectiveWorkspaceId = workspaceId || workspaces[0]?.id || "";
  const { data: notes = [] } = useNotes(effectiveWorkspaceId);
  const { data: selected } = useNote(noteId);

  async function onSave(title: string, body: string) {
    if (!selected || saving) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateNote(selected.id, title, body);
      await queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
      await queryClient.invalidateQueries({ queryKey: ["note", selected.id] });
      success("Note updated");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Save failed", msg);
    } finally {
      setSaving(false);
    }
  }

  async function onDelete(id: string) {
    if (!(await confirmAction("Delete this note?", "This cannot be undone."))) return;
    setError(null);
    try {
      await api.deleteNote(id);
      await queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
      await queryClient.invalidateQueries({ queryKey: ["note", id] });
      navigate("/notes", { replace: true });
      success("Note deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  function onSelect(n: Note) {
    navigate(`/notes/${n.id}`);
  }

  const value: NotesPageContextValue = {
    workspaces,
    workspaceId: effectiveWorkspaceId,
    notes,
    selected: selected ?? null,
    error,
    saving,
    onChangeWorkspace: setWorkspaceId,
    onSelect,
    onSave,
    onDelete,
    onLogout: () => navigate("/login", { replace: true }),
  };

  return (
    <NotesPageContext.Provider value={value}>
      {children}
    </NotesPageContext.Provider>
  );
}
