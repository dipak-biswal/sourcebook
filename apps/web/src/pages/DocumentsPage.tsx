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
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";

const INGEST_STEPS = [
  "Starting ingest…",
  "Parsing document…",
  "Chunking text…",
  "Embedding chunks…",
  "Saving vectors…",
  "Almost done…",
];

export function DocumentsPage() {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  useDocumentTitle("Documents");
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [docs, setDocs] = useState<Document[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [ingestingId, setIngestingId] = useState<string | null>(null);
  const [ingestProgress, setIngestProgress] = useState<string | null>(null);

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
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Upload failed", msg);
    } finally {
      setUploading(false);
    }
  }

  async function onDelete(id: string) {
    const doc = docs.find((d) => d.id === id);
    if (
      !confirmAction(
        "Delete this document?",
        doc?.filename
          ? `${doc.filename} and its chunks will be removed.`
          : "This cannot be undone.",
      )
    ) {
      return;
    }
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
    setIngestProgress(INGEST_STEPS[0]);
    try {
      await api.ingestDocument(id);
      await loadDocs(workspaceId);
      let finalStatus = "processing";
      for (let i = 0; i < 40; i++) {
        setIngestProgress(INGEST_STEPS[Math.min(i, INGEST_STEPS.length - 1)]);
        await new Promise((r) => setTimeout(r, 1500));
        const list = await api.documents(workspaceId);
        setDocs(list);
        const doc = list.find((d) => d.id === id);
        const s = doc?.status?.toLowerCase() ?? "";
        if (!doc || s === "ready" || s === "failed" || s === "uploaded") {
          finalStatus = s || "unknown";
          if (s === "ready")
            success("Ingest complete", "Document is ready for chat.");
          if (s === "failed")
            toastError(
              "Ingest failed",
              doc?.error || "Check the error on the document card.",
            );
          break;
        }
      }
      if (finalStatus === "processing" || finalStatus === "queued") {
        success(
          "Ingest still running",
          "Refresh the list if status stays processing.",
        );
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Ingest failed", msg);
      await loadDocs(workspaceId);
    } finally {
      setIngestingId(null);
      setIngestProgress(null);
    }
  }

  const libraryProps = {
    workspaces,
    workspaceId,
    onWorkspaceChange: setWorkspaceId,
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
      <AppHeader
        onLogout={() => {
          navigate("/login", { replace: true });
        }}
      />

      <div className="flex min-h-0 flex-1">
        {/* Desktop sidebar */}
        <div className="hidden h-full shrink-0 md:flex md:w-80">
          <DocumentsSidebar {...libraryProps} />
        </div>

        {/* Mobile: list-first library */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col md:hidden">
          {error && (
            <div className="px-4 pt-3">
              <Alert variant="danger">{error}</Alert>
            </div>
          )}
          <DocumentsSidebar {...libraryProps} compact />
        </div>

        {/* Desktop guide panel */}
        <main className="document-scroll hidden min-h-0 min-w-0 flex-1 flex-col items-center justify-center overflow-y-auto px-4 py-10 text-center sm:px-8 sm:py-12 md:flex">
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
            Upload a .txt or .md from the sidebar, then{" "}
            <strong className="text-ink">Ingest for chat</strong>. Watch status:{" "}
            <strong className="text-ink">processing → ready</strong>. Progress
            text shows while embedding.
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
            onClick={() => navigate("/chat")}
          >
            Go to Chat →
          </Button>
        </main>
      </div>
    </div>
  );
}
