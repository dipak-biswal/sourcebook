import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { FileUp, X } from "lucide-react";
import { useDocuments } from "@/hooks/queries";
import { useChatPage } from "@/pages/ChatPage/chat-page-context";

const dismissKey = (workspaceId: string) =>
  `sourcebook_no_docs_banner_${workspaceId}`;

export function ChatNoDocsBanner() {
  const { mode, workspaceId } = useChatPage();
  const { data: docs = [], isLoading } = useDocuments(
    mode === "chat" ? workspaceId : undefined,
  );
  const [dismissed, setDismissed] = useState(false);

  const readyCount = docs.filter((d) => d.status === "ready").length;
  const totalCount = docs.length;

  useEffect(() => {
    if (!workspaceId) {
      setDismissed(false);
      return;
    }
    try {
      setDismissed(localStorage.getItem(dismissKey(workspaceId)) === "1");
    } catch {
      setDismissed(false);
    }
  }, [workspaceId]);

  if (mode !== "chat" || !workspaceId || isLoading || readyCount > 0 || dismissed) {
    return null;
  }

  function onDismiss() {
    setDismissed(true);
    try {
      localStorage.setItem(dismissKey(workspaceId), "1");
    } catch {
      /* ignore */
    }
  }

  const message =
    totalCount === 0
      ? "No documents in this workspace yet. Upload a file and ingest it before Chat can answer from your sources."
      : "Documents are uploaded but none are ready yet. Finish ingest (status ready) before asking grounded questions.";

  return (
    <div className="shrink-0 border-b border-warning-border bg-warning-soft px-4 py-3 sm:px-6">
      <div className="mx-auto flex max-w-2xl items-start gap-3">
        <FileUp className="mt-0.5 h-4 w-4 shrink-0 text-warning-text" strokeWidth={1.5} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-warning-text">
            Documents not ready for chat
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-warning-text/90">
            {message}
          </p>
          <Link
            to="/documents"
            className="mt-2 inline-block text-xs font-medium text-ink underline-offset-2 hover:underline"
          >
            Go to Documents →
          </Link>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded p-1 text-warning-text/80 hover:bg-warning-soft hover:text-warning-text"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}