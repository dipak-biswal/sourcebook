import { AppHeader } from "@/components/layout/AppHeader";
import { DocumentsSidebar } from "@/components/layout/DocumentsSidebar";
import { DocumentsOnboarding } from "@/components/documents/DocumentsOnboarding";
import { Alert } from "@/components/ui/alert";

import type { DocumentsPageViewProps } from "@/types/page-props";

export function DocumentsPageView({
  workspaces,
  workspaceId,
  docs,
  error,
  uploading,
  ingestingId,
  ingestProgress,
  loading,
  onChangeWorkspace,
  onUpload,
  onDelete,
  onIngest,
  onNavigateToChat,
  onLogout,
}: DocumentsPageViewProps) {
  const libraryProps = {
    workspaces,
    workspaceId,
    onWorkspaceChange: onChangeWorkspace,
    documents: docs,
    loading,
    uploading,
    ingestingId,
    ingestProgress,
    onUpload,
    onDelete,
    onIngest,
  };

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex min-h-0 flex-1">
        <div className="hidden h-full shrink-0 md:flex md:w-80">
          <DocumentsSidebar {...libraryProps} />
        </div>

        <div className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto md:hidden">
          <DocumentsOnboarding compact />
          {error && (
            <div className="px-4 pt-3">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}
          <DocumentsSidebar {...libraryProps} compact />
        </div>

        <main
          id="main-content"
          tabIndex={-1}
          className="document-scroll hidden min-h-0 min-w-0 flex-1 flex-col overflow-y-auto outline-none md:flex"
        >
          {error && (
            <div className="px-8 pt-6">
              <Alert variant="danger" className="max-w-md text-left">
                {error}
              </Alert>
            </div>
          )}
          <DocumentsOnboarding onNavigateToChat={onNavigateToChat} />
        </main>
      </div>
    </div>
  );
}
