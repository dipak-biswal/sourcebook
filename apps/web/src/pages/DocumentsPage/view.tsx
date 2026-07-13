import { FileText, Upload } from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import { DocumentsSidebar } from "@/components/layout/DocumentsSidebar";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

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

        <div className="flex min-h-0 min-w-0 flex-1 flex-col md:hidden">
          {error && (
            <div className="px-4 pt-3">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}
          <DocumentsSidebar {...libraryProps} compact />
        </div>

        <main id="main-content" tabIndex={-1} className="document-scroll hidden min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10 text-center outline-none sm:px-8 sm:py-12 md:flex">
          {error && (
            <Alert variant="danger" className="mb-6 max-w-md text-left">
              {error}
            </Alert>
          )}

          <div className="flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute">
            <Upload className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <h2 className="mt-4 text-display-sm font-semibold tracking-tight text-ink">
            Your document library
          </h2>
          <p className="mt-2 max-w-md text-body-sm text-mute">
            Upload <strong className="text-ink">PDF, DOCX, txt/md</strong>, CSV,
            HTML, JSON, and other text files, then{" "}
            <strong className="text-ink">Ingest for chat</strong>. Status goes{" "}
            <strong className="text-ink">processing → ready</strong>. Scanned
            image-only PDFs need OCR (not included yet).
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {[".pdf", ".docx", ".txt / .md", "CSV / HTML", "Ingest → ready"].map(
              (label) => (
                <span
                  key={label}
                  className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3 py-1 text-xs text-body"
                >
                  <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
                  {label}
                </span>
              ),
            )}
          </div>

          <ol className="mt-8 max-w-sm space-y-2 text-left text-body-sm text-body">
            <li className="flex gap-2">
              <span className="font-medium text-ink">1.</span>
              Upload from the sidebar
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">2.</span>
              Click <strong>Ingest for chat</strong>
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">3.</span>
              If <strong>failed</strong>, expand the error and retry
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">4.</span>
              Open <strong>Chat</strong> when status is <strong>ready</strong>
            </li>
          </ol>

          <Button
            type="button"
            variant="secondary"
            className="mt-8"
            onClick={onNavigateToChat}
          >
            Go to Chat →
          </Button>
        </main>
      </div>
    </div>
  );
}
