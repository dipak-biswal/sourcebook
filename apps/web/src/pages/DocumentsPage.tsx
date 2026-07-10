import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { FileText, Upload } from "lucide-react";
import {
  api,
  getToken,
  type Document,
  type Workspace,
} from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { DocumentsSidebar } from "@/components/layout/DocumentsSidebar";
import { Alert } from "@/components/ui/alert";
import { formatError } from "@/lib/utils";

export function DocumentsPage() {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [docs, setDocs] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const loadDocs = useCallback(async (ws: string) => {
    if (!ws) return;
    setDocs(await api.documents(ws));
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await api.workspaces();
        if (cancelled) return;
        setWorkspaces(list);
        const first = list[0]?.id ?? "";
        setWorkspaceId((prev) => prev || first);
      } catch (err) {
        if (!cancelled) setError(formatError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    loadDocs(workspaceId).catch((err) => setError(formatError(err)));
  }, [workspaceId, loadDocs]);

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  async function onUpload(file: File) {
    if (!workspaceId) return;
    setUploading(true);
    setError(null);
    try {
      await api.upload(workspaceId, file);
      await loadDocs(workspaceId);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(id: string) {
    setError(null);
    try {
      await api.deleteDocument(id);
      await loadDocs(workspaceId);
    } catch (err) {
      setError(formatError(err));
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas-soft">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        <DocumentsSidebar
          workspaces={workspaces}
          workspaceId={workspaceId}
          onWorkspaceChange={setWorkspaceId}
          documents={docs}
          loading={loading}
          uploading={uploading}
          onUpload={onUpload}
          onDelete={onDelete}
        />

        <main className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-y-auto px-8 py-12 text-center">
          {error && (
            <Alert variant="danger" className="mb-6 max-w-md text-left">
              {error}
            </Alert>
          )}

          <div className="flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute">
            <Upload className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <h2 className="mt-4 text-display-sm font-semibold text-ink">
            Your document library
          </h2>
          <p className="mt-2 max-w-md text-body-sm text-mute">
            Upload files from the sidebar. Later weeks add ingest, RAG chat with
            citations, and tool-using agents.
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {["Text", "Markdown", "PDF soon"].map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3 py-1 text-xs text-body"
              >
                <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
                {label}
              </span>
            ))}
          </div>

          <ol className="mt-8 max-w-sm space-y-2 text-left text-body-sm text-body">
            <li className="flex gap-2">
              <span className="font-medium text-ink">1.</span>
              Create an account and open your workspace
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">2.</span>
              Upload a source file from the sidebar
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">3.</span>
              Chat with grounded answers (coming next)
            </li>
          </ol>
        </main>
      </div>
    </div>
  );
}
