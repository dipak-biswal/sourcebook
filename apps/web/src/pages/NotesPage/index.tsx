import { Navigate } from "react-router-dom";
import { getToken } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { NotesPageProvider, useNotesPage } from "./NotesPageContext";
import { NotesSidebar } from "./NotesSidebar";
import { NoteEditor } from "./NoteEditor";

function NotesPageInner() {
  const { error, selected, onLogout } = useNotesPage();

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 flex-col border-r border-hairline bg-canvas md:flex">
          <NotesSidebar />
        </aside>

        <main id="main-content" tabIndex={-1} className="document-scroll min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5 outline-none sm:px-6 sm:py-6">
          <div className="mx-auto max-w-2xl">
            {error && (
              <Alert variant="danger" className="mb-4">{error}</Alert>
            )}
            <NoteEditor key={selected?.id} />
          </div>
        </main>
      </div>
    </div>
  );
}

export function NotesPage() {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <NotesPageProvider>
      <NotesPageInner />
    </NotesPageProvider>
  );
}
