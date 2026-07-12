import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { FileText, PanelLeft, Upload } from "lucide-react";
import {
  api,
  getToken,
  type Document,
  type Workspace,
} from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { DocumentsSidebar } from "@/components/layout/DocumentsSidebar";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { useToast } from "@/components/ui/toast";
import { formatError } from "@/lib/utils";

export function DocumentsPage() {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [docs, setDocs] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [ingestingId, setIngestingId] = useState<string | null>(null);
  const [libraryOpen, setLibraryOpen] = useState(false);

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
      success("Uploaded", file.name);
      setLibraryOpen(false);
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Upload failed", msg);
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(id: string) {
    setError(null);
    try {
      await api.deleteDocument(id);
      await loadDocs(workspaceId);
      success("Document deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  async function onIngest(id: string) {
    setError(null);
    setIngestingId(id);
    try {
      await api.ingestDocument(id);
      await loadDocs(workspaceId);
      // Poll while queued/processing
      let finalStatus = "processing";
      for (let i = 0; i < 40; i++) {
        await new Promise((r) => setTimeout(r, 1500));
        const list = await api.documents(workspaceId);
        setDocs(list);
        const doc = list.find((d) => d.id === id);
        const s = doc?.status?.toLowerCase() ?? "";
        if (!doc || s === "ready" || s === "failed" || s === "uploaded") {
          finalStatus = s || "unknown";
          if (s === "ready") success("Ingest complete", "Document is ready for chat.");
          if (s === "failed")
            toastError(
              "Ingest failed",
              doc?.error || "Check the error on the document card.",
            );
          break;
        }
      }
      if (finalStatus === "processing" || finalStatus === "queued") {
        success("Ingest still running", "Refresh the list if status stays processing.");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Ingest failed", msg);
      await loadDocs(workspaceId);
    } finally {
      setIngestingId(null);
    }
  }

  const library = (
    <DocumentsSidebar
      workspaces={workspaces}
      workspaceId={workspaceId}
      onWorkspaceChange={setWorkspaceId}
      documents={docs}
      loading={loading}
      uploading={uploading}
      ingestingId={ingestingId}
      onUpload={onUpload}
      onDelete={onDelete}
      onIngest={onIngest}
    />
  );

  return (
    <div className="app-shell">
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        <div className="hidden h-full shrink-0 md:flex md:w-80">{library}</div>

        <Sheet
          open={libraryOpen}
          onClose={() => setLibraryOpen(false)}
          title="Library"
          description="Upload and ingest documents"
          side="left"
        >
          {library}
        </Sheet>

        <main className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10 text-center sm:px-8 sm:py-12">
          <div className="mb-6 w-full max-w-md md:hidden">
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              onClick={() => setLibraryOpen(true)}
            >
              <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
              Open library ({docs.length})
            </Button>
          </div>

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
            Upload a .txt or .md, then click{" "}
            <strong className="text-ink">Ingest for chat</strong>. Status goes{" "}
            <strong className="text-ink">processing → ready</strong> (or{" "}
            <strong className="text-ink">failed</strong> with an error in the
            sidebar). After ready, open Chat.
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {[".txt", ".md", "Ingest → ready"].map((label) => (
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
              Upload from the sidebar
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">2.</span>
              Click <strong>Ingest for chat</strong> (needs a valid OpenAI /
              embedding API key)
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">3.</span>
              If status is <strong>failed</strong>, expand the error, fix, then{" "}
              <strong>Retry ingest</strong>
            </li>
            <li className="flex gap-2">
              <span className="font-medium text-ink">4.</span>
              Open <strong>Chat</strong> when status is <strong>ready</strong>
            </li>
          </ol>

          <button
            type="button"
            className="mt-8 text-sm font-medium text-ink underline-offset-2 hover:underline"
            onClick={() => navigate("/chat")}
          >
            Go to Chat →
          </button>
        </main>
      </div>
    </div>
  );
}
