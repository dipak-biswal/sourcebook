import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  api,
} from "@/api";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import { useDocuments, useWorkspaces } from "@/hooks/queries";
import { useLastWorkspace } from "@/hooks/useLastWorkspace";
import { DocumentsPageView } from "./view";

const INGEST_STEPS = [
  "Starting ingest…",
  "Parsing document…",
  "Chunking text…",
  "Embedding chunks…",
  "Saving vectors…",
  "Almost done…",
];

export { DocumentsPageView } from "./view";

export function DocumentsPage() {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle("Documents");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [ingestingId, setIngestingId] = useState<string | null>(null);
  const [ingestProgress, setIngestProgress] = useState<string | null>(null);

  const { data: workspaces = [], isLoading: loading } = useWorkspaces();
  const { workspaceId, setWorkspaceId } = useLastWorkspace(workspaces);
  const { data: docs = [], refetch: refetchDocs } = useDocuments(workspaceId);

  async function onUpload(file: File) {
    if (!workspaceId) return;
    setUploading(true);
    setError(null);
    try {
      await api.upload(workspaceId, file);
      await queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
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
      !(await confirmAction(
        "Delete this document?",
        doc?.filename
          ? `${doc.filename} and its chunks will be removed.`
          : "This cannot be undone.",
      ))
    ) {
      return;
    }
    setError(null);
    try {
      await api.deleteDocument(id);
      await queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
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
    const invalidate = () => queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    try {
      await api.ingestDocument(id);
      await invalidate();
      let finalStatus = "processing";
      for (let i = 0; i < 40; i++) {
        setIngestProgress(INGEST_STEPS[Math.min(i, INGEST_STEPS.length - 1)]);
        await new Promise((r) => setTimeout(r, 1500));
        const list = await api.documents(workspaceId);
        queryClient.setQueryData(["documents", workspaceId], list);
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
      await invalidate();
    } finally {
      setIngestingId(null);
      setIngestProgress(null);
    }
  }

  return (
    <DocumentsPageView
      workspaces={workspaces}
      workspaceId={workspaceId}
      docs={docs}
      error={error}
      uploading={uploading}
      ingestingId={ingestingId}
      ingestProgress={ingestProgress}
      loading={loading}
      onChangeWorkspace={(id) => {
        setWorkspaceId(id);
        setError(null);
      }}
      onRefreshWorkspaces={() => {
        void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      }}
      onRetryError={() => {
        setError(null);
        void refetchDocs();
      }}
      onDismissError={() => setError(null)}
      onUpload={onUpload}
      onDelete={onDelete}
      onIngest={onIngest}
      onNavigateToChat={() => navigate("/chat")}
      onLogout={() => navigate("/login", { replace: true })}
    />
  );
}
