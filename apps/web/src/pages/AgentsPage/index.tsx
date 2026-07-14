import { AppHeader } from "@/components/layout/AppHeader";
import { Button } from "@/components/ui/button";
import { PanelLeft } from "lucide-react";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Sheet } from "@/components/ui/sheet";
import { AgentPageProvider } from "./AgentPageContext";
import { useAgentPage } from "./agent-page-context";
import { AgentSidebar } from "./AgentSidebar";
import { AgentRunForm } from "./AgentRunForm";
import { AgentRunDisplay } from "./AgentRunDisplay";

function AgentsPageInner() {
  const {
    runs,
    error,
    sidebarOpen,
    onToggleSidebar,
    onSidebarClose,
    onDismissError,
    onRetryError,
    onLogout,
  } = useAgentPage();

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 flex-col border-r border-hairline bg-canvas md:flex">
          <AgentSidebar />
        </aside>

        <Sheet
          open={sidebarOpen}
          onClose={onSidebarClose}
          title="Runs"
          description="Agent history in this workspace"
          side="left"
        >
          <AgentSidebar />
        </Sheet>

        <main id="main-content" tabIndex={-1} className="document-scroll min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5 outline-none sm:px-6 sm:py-6">
          <div className="mx-auto max-w-2xl">
            <div className="mb-4 md:hidden">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onToggleSidebar}
              >
                <PanelLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
                Runs ({runs.length})
              </Button>
            </div>

            {error && (
              <ErrorAlert
                message={error}
                className="mb-4"
                onDismiss={onDismissError}
                onRetry={onRetryError}
              />
            )}

            <AgentRunForm />
            <AgentRunDisplay />
          </div>
        </main>
      </div>
    </div>
  );
}

export function AgentsPage() {
  return (
    <AgentPageProvider>
      <AgentsPageInner />
    </AgentPageProvider>
  );
}
