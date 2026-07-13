import { AppHeader } from "@/components/layout/AppHeader";
import { Button } from "@/components/ui/button";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Sheet } from "@/components/ui/sheet";
import { PanelLeft } from "lucide-react";
import {
  AgentPageProvider,
  STUDY_GUIDE_CONFIG,
} from "@/pages/AgentsPage/AgentPageContext";
import { useAgentPage } from "@/pages/AgentsPage/agent-page-context";
import { AgentSidebar } from "@/pages/AgentsPage/AgentSidebar";
import { AgentRunForm } from "@/pages/AgentsPage/AgentRunForm";
import { AgentRunDisplay } from "@/pages/AgentsPage/AgentRunDisplay";

function StudyGuidePageInner() {
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
          title="Study guides"
          description="Learning UI runs in this workspace"
          side="left"
        >
          <AgentSidebar />
        </Sheet>

        <main
          id="main-content"
          tabIndex={-1}
          className="document-scroll min-h-0 min-w-0 flex-1 overflow-y-auto px-4 py-5 outline-none sm:px-6 sm:py-6"
        >
          <div className="mx-auto max-w-2xl">
            <div className="mb-4 md:hidden">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={onToggleSidebar}
              >
                <PanelLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
                Study guides ({runs.length})
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

export function StudyGuidePage() {
  return (
    <AgentPageProvider config={STUDY_GUIDE_CONFIG}>
      <StudyGuidePageInner />
    </AgentPageProvider>
  );
}