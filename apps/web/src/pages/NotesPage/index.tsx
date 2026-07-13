import { useState } from "react";
import { PanelLeft } from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { NotesPageProvider } from "./NotesPageContext";
import { useNotesPage } from "./notes-page-context";
import { NotesSidebar } from "./NotesSidebar";
import { NoteEditor } from "./NoteEditor";

function NotesPageInner() {
  const { error, selected, onDismissError, onRetryError, onLogout } = useNotesPage();
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 flex-col border-r border-hairline bg-canvas md:flex">
          <NotesSidebar />
        </aside>

        <Sheet
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          title="Notes"
          description="Notes in this workspace"
          side="left"
        >
          <NotesSidebar onAfterNavigate={() => setSidebarOpen(false)} />
        </Sheet>

        <main
          id="main-content"
          tabIndex={-1}
          className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto outline-none"
        >
          <div className="flex shrink-0 items-center gap-2 border-b border-hairline px-4 py-3 md:hidden">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Open notes list"
              onClick={() => setSidebarOpen(true)}
            >
              <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
            </Button>
            <span className="truncate text-sm font-semibold text-ink">
              {selected?.title || "Notes"}
            </span>
          </div>

          <div className="min-h-0 flex-1 px-4 py-5 sm:px-6 sm:py-6">
            <div className="mx-auto max-w-2xl">
              {error && (
                <ErrorAlert
                  message={error}
                  className="mb-4"
                  onDismiss={onDismissError}
                  onRetry={onRetryError}
                />
              )}
              <NoteEditor key={selected?.id} />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

export function NotesPage() {
  return (
    <NotesPageProvider>
      <NotesPageInner />
    </NotesPageProvider>
  );
}