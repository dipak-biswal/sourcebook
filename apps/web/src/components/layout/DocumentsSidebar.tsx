import { useRef } from "react";
import { FileText, Trash2, Upload } from "lucide-react";
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
  onUpload: (file: File) => void;
  onDelete: (id: string) => void;
};

function statusVariant(
  status: string,
): "secondary" | "success" | "warning" | "danger" {
  switch (status) {
    case "ready":
      return "success";
    case "failed":
      return "danger";
    case "processing":
      return "warning";
    default:
      return "secondary";
  }
}

export function DocumentsSidebar({
  workspaces,
  workspaceId,
  onWorkspaceChange,
  documents,
  loading,
  uploading,
  onUpload,
  onDelete,
}: DocumentsSidebarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-hairline bg-canvas">
      <div className="border-b border-hairline p-4">
        <h2 className="text-body-sm font-semibold text-ink">Library</h2>
        <p className="mt-0.5 text-xs text-mute">
          Upload notes and source files
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
          accept=".txt,.md,.markdown,.pdf,.docx"
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
          {uploading ? "Uploading…" : "Upload file"}
        </Button>
      </div>

      <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <p className="px-2 py-3 text-xs text-mute">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="px-2 py-3 text-xs text-mute">No documents yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {documents.map((doc) => (
              <li
                key={doc.id}
                className={cn(
                  "group flex items-start gap-2 rounded-[6px] px-2 py-2 hover:bg-canvas-soft-2",
                )}
              >
                <FileText
                  className="mt-0.5 h-4 w-4 shrink-0 text-mute"
                  strokeWidth={1.5}
                />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-ink">
                    {doc.filename}
                  </div>
                  <div className="mt-1">
                    <Badge variant={statusVariant(doc.status)}>
                      {doc.status}
                    </Badge>
                  </div>
                </div>
                <button
                  type="button"
                  title="Delete"
                  className="rounded p-1 text-mute opacity-0 transition-opacity hover:bg-canvas hover:text-ink group-hover:opacity-100"
                  onClick={() => onDelete(doc.id)}
                >
                  <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
