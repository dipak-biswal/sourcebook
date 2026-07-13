import type { Note } from "@/api";

export type NotesPageContextValue = {
  workspaces: Workspace[];
  workspaceId: string;
  notes: Note[];
  selected: Note | null;
  error: string | null;
  saving: boolean;
  onChangeWorkspace: (id: string) => void;
  onSelect: (note: Note) => void;
  onSave: (title: string, body: string) => void;
  onDelete: (id: string) => void;
  onLogout: () => void;
};

type Workspace = { id: string; name: string };
