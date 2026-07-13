import { createContext, useContext } from "react";
import type { NotesPageContextValue } from "@/types/notes";

export const NotesPageContext = createContext<NotesPageContextValue | null>(null);

export function useNotesPage(): NotesPageContextValue {
  const ctx = useContext(NotesPageContext);
  if (!ctx) throw new Error("useNotesPage must be used within NotesPageProvider");
  return ctx;
}
