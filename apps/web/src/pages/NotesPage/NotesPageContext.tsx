import { useCallback, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, type Note } from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { useNote, useNotes, useWorkspaces } from "@/hooks/queries";
import { useLastWorkspace } from "@/hooks/useLastWorkspace";
import type { NotesPageContextValue } from "@/types/notes";
import { NotesPageContext } from "./notes-page-context";

export function NotesPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { noteId } = useParams();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle(noteId ? "Edit note" : "Notes");

  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);

  const { data: workspaces = [] } = useWorkspaces();
  const { workspaceId: effectiveWorkspaceId, setWorkspaceId: persistWorkspace } =
    useLastWorkspace(workspaces);

  const { data: notes = [], refetch: refetchNotes } = useNotes(effectiveWorkspaceId);
  const { data: selected, refetch: refetchSelected } = useNote(noteId);

  const onChangeWorkspace = useCallback(
    (id: string) => {
      persistWorkspace(id);
      setError(null);
      if (selected && selected.workspace_id !== id) {
        navigate("/notes", { replace: true });
      }
    },
    [selected, navigate, persistWorkspace],
  );

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

  async function onCreate() {
    if (!effectiveWorkspaceId || creating) return;
    setCreating(true);
    setError(null);
    try {
      const note = await api.createNote(effectiveWorkspaceId, "Untitled note");
      await queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
      navigate(`/notes/${note.id}`);
      success("Note created");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Create failed", msg);
    } finally {
      setCreating(false);
    }
  }

  const value: NotesPageContextValue = {
    workspaces,
    workspaceId: effectiveWorkspaceId,
    notes,
    selected: selected ?? null,
    error,
    saving,
    onChangeWorkspace,
    onRefreshWorkspaces: () => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
    onDismissError: () => setError(null),
    onRetryError: () => {
      setError(null);
      void refetchNotes();
      if (noteId) void refetchSelected();
    },
    onSelect,
    onCreate,
    creating,
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
