import { useRef, useState } from "react";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  Play,
  Trash2,
  Upload,
} from "lucide-react";
import type { Document, Workspace } from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type DocumentsSidebarProps = {
  workspaces: Workspace[];
  workspaceId: string;
  onWorkspaceChange: (id: string) => void;
  documents: Document[];
  loading?: boolean;
  uploading?: boolean;
  ingestingId?: string | null;
  onUpload: (file: File) => void;
  onDelete: (id: string) => void;
  onIngest: (id: string) => void;
};

function statusVariant(
  status: string,
): "secondary" | "success" | "warning" | "danger" {
  const s = status.toLowerCase();
  if (s === "ready") return "success";
  if (s === "failed") return "danger";
  if (
    s === "processing" ||
    s === "queued" ||
    s === "chunked"
  ) {
    return "warning";
  }
  return "secondary";
}

function canIngest(doc: Document): boolean {
  const name = doc.filename.toLowerCase();
  const textLike =
    name.endsWith(".txt") ||
    name.endsWith(".md") ||
    name.endsWith(".markdown");
  const s = doc.status.toLowerCase();
  // Allow re-queue when failed/ready/uploaded; block while queued/processing
  return textLike && s !== "processing" && s !== "queued";
}

export function DocumentsSidebar({
  workspaces,
  workspaceId,
  onWorkspaceChange,
  documents,
  loading,
  uploading,
  ingestingId,
  onUpload,
  onDelete,
  onIngest,
}: DocumentsSidebarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [expandedErrors, setExpandedErrors] = useState<Record<string, boolean>>(
    {},
  );

  function toggleError(id: string) {
    setExpandedErrors((prev) => ({ ...prev, [id]: !prev[id] }));
  }

  return (
    <aside className="flex w-80 shrink-0 flex-col border-r border-hairline bg-canvas">
      <div className="shrink-0 border-b border-hairline p-4">
        <h2 className="text-body-sm font-semibold text-ink">Library</h2>
        <p className="mt-0.5 text-xs text-mute">
          Upload → Ingest → status <span className="text-ink">ready</span> → Chat
        </p>

        {workspaces.length > 0 && (
          <label className="mt-3 block">
            <span className="mb-1 block text-xs text-mute">Workspace</span>
            <select
              value={workspaceId}
              onChange={(e) => onWorkspaceChange(e.target.value)}
              className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
        )}

        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          accept=".txt,.md,.markdown"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) onUpload(file);
            e.target.value = "";
          }}
        />

        <Button
          type="button"
          className="mt-3 w-full rounded-[6px]"
          disabled={!workspaceId || uploading}
          onClick={() => fileInputRef.current?.click()}
        >
          <Upload className="h-4 w-4" strokeWidth={1.5} />
          {uploading ? "Uploading…" : "Upload .txt / .md"}
        </Button>
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
          Documents ({documents.length})
        </div>

        {loading ? (
          <p className="px-2 py-3 text-xs text-mute">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="px-2 py-3 text-xs text-mute">No documents yet.</p>
        ) : (
          <ul className="space-y-1">
            {documents.map((doc) => {
              const ingesting = ingestingId === doc.id;
              const status = doc.status.toLowerCase();
              const ready = status === "ready";
              const failed = status === "failed";
              const errOpen = !!expandedErrors[doc.id];
              const errText = (doc.error || "").trim();
              return (
                <li
                  key={doc.id}
                  className={cn(
                    "rounded-[6px] border bg-canvas px-2 py-2",
                    failed ? "border-red-200 bg-[#fffbeb]" : "border-hairline",
                  )}
                >
                  <div className="flex items-start gap-2">
                    <FileText
                      className="mt-0.5 h-4 w-4 shrink-0 text-mute"
                      strokeWidth={1.5}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-medium text-ink">
                        {doc.filename}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-1">
                        <Badge variant={statusVariant(doc.status)}>
                          {doc.status}
                        </Badge>
                        {(status === "queued" ||
                          status === "processing" ||
                          ingesting) && (
                          <Loader2 className="h-3 w-3 animate-spin text-mute" />
                        )}
                      </div>
                      {failed && !errText && (
                        <p className="mt-1.5 flex items-start gap-1 text-[11px] text-red-700">
                          <AlertCircle
                            className="mt-0.5 h-3 w-3 shrink-0"
                            strokeWidth={1.5}
                          />
                          Ingest failed. Try Re-ingest or re-upload the file.
                        </p>
                      )}
                      {errText && (
                        <div className="mt-1.5">
                          <button
                            type="button"
                            onClick={() => toggleError(doc.id)}
                            className="flex w-full items-start gap-1 text-left text-[11px] font-medium text-red-800"
                          >
                            <AlertCircle
                              className="mt-0.5 h-3 w-3 shrink-0"
                              strokeWidth={1.5}
                            />
                            <span className="min-w-0 flex-1">
                              {errOpen ? (
                                <span className="whitespace-pre-wrap break-words font-normal">
                                  {errText}
                                </span>
                              ) : (
                                <span className="line-clamp-2 font-normal">
                                  {errText}
                                </span>
                              )}
                            </span>
                            {errOpen ? (
                              <ChevronDown className="mt-0.5 h-3 w-3 shrink-0" />
                            ) : (
                              <ChevronRight className="mt-0.5 h-3 w-3 shrink-0" />
                            )}
                          </button>
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      title="Delete"
                      className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                      onClick={() => onDelete(doc.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                    </button>
                  </div>

                  {canIngest(doc) && (
                    <Button
                      type="button"
                      variant={ready ? "secondary" : "default"}
                      size="sm"
                      className="mt-2 w-full rounded-[6px]"
                      disabled={ingesting}
                      onClick={() => onIngest(doc.id)}
                    >
                      {ingesting ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Play className="h-3.5 w-3.5" strokeWidth={1.5} />
                      )}
                      {ingesting
                        ? "Working…"
                        : failed
                          ? "Retry ingest"
                          : ready
                            ? "Re-ingest"
                            : "Ingest for chat"}
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
