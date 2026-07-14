import { useState } from "react";
import {
  LayoutGrid,
  Loader2,
  Pen,
  Plus,
  Save,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { validateWorkspaceName } from "@/lib/validation";
import { useSettingsPage } from "./settings-page-context";

export function SettingsWorkspaces() {
  const {
    workspaces, newWsName, creatingWs,
    editingId, editName, editDescription, editTags, savingEdit,
    onNewWsNameChange, onCreateWorkspace,
    onStartEdit, onEditNameChange, onEditDescriptionChange, onEditTagsChange,
    onCancelEdit, onSaveEdit,
    onDeleteWorkspace,
  } = useSettingsPage();
  const [wsError, setWsError] = useState<string | null>(null);
  const [editErrors, setEditErrors] = useState<{ name?: string }>({});

  function handleCreateWs() {
    const err = validateWorkspaceName(newWsName);
    setWsError(err);
    if (!err) void onCreateWorkspace();
  }

  function handleNewWsKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") {
      e.preventDefault();
      handleCreateWs();
    }
  }

  function handleEditSubmit(id: string) {
    const err = validateWorkspaceName(editName);
    setEditErrors({ name: err ?? undefined });
    if (!err) void onSaveEdit(id);
  }

  return (
    <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
      <h2 className="text-sm font-semibold text-ink">Workspaces</h2>
      <p className="mt-1 text-xs text-mute">
        Create, edit, or delete workspaces. Description and tags help the agent
        tailor structured presentations to your workspace.
      </p>

      <div className="mt-3">
        <div className="flex gap-1">
          <Input
            value={newWsName}
            onChange={(e) => { onNewWsNameChange(e.target.value); setWsError(null); }}
            placeholder="New workspace name…"
            className="h-8 text-xs"
            aria-invalid={!!wsError || undefined}
            onKeyDown={handleNewWsKeyDown}
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            className="h-8 shrink-0"
            disabled={!newWsName.trim() || creatingWs}
            onClick={handleCreateWs}
          >
            {creatingWs ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Create
          </Button>
        </div>
        <FieldError error={wsError} />
      </div>

      <div className="mt-3 space-y-1">
        {workspaces.length === 0 ? (
          <p className="text-xs text-mute">No workspaces.</p>
        ) : (
          workspaces.map((ws) => (
            <div
              key={ws.id}
              className="rounded-[6px] border border-hairline px-3 py-2"
            >
              {editingId === ws.id ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
                    <span className="text-[10px] uppercase text-mute">{ws.role}</span>
                    <div className="ml-auto flex gap-1">
                      <Button
                        type="button"
                        variant="secondary"
                        size="icon"
                        className="h-7 w-7"
                        disabled={!editName.trim() || savingEdit}
                        onClick={() => handleEditSubmit(ws.id)}
                      >
                        {savingEdit ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Save className="h-3 w-3" strokeWidth={1.5} />
                        )}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="icon"
                        className="h-7 w-7"
                        onClick={onCancelEdit}
                      >
                        <X className="h-3 w-3" strokeWidth={1.5} />
                      </Button>
                    </div>
                  </div>
                  <Input
                    value={editName}
                    onChange={(e) => { onEditNameChange(e.target.value); setEditErrors({}); }}
                    className="h-7 text-xs"
                    autoFocus
                    aria-invalid={!!editErrors.name || undefined}
                    placeholder="Workspace name"
                  />
                  <FieldError error={editErrors.name} />
                  <textarea
                    value={editDescription}
                    onChange={(e) => onEditDescriptionChange(e.target.value)}
                    className="min-h-[4rem] w-full rounded-[6px] border border-hairline bg-canvas px-2.5 py-2 text-xs text-body"
                    placeholder="What is this workspace for? (optional)"
                  />
                  <Input
                    value={editTags}
                    onChange={(e) => onEditTagsChange(e.target.value)}
                    className="h-7 text-xs"
                    placeholder="Tags, comma-separated (optional)"
                  />
                </div>
              ) : (
                <div className="flex items-start gap-2">
                  <LayoutGrid className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-ink">
                        {ws.name}
                      </span>
                      <span className="text-[10px] uppercase text-mute">{ws.role}</span>
                    </div>
                    {ws.description && (
                      <p className="mt-0.5 line-clamp-2 text-xs text-mute">
                        {ws.description}
                      </p>
                    )}
                    {ws.tags && ws.tags.length > 0 && (
                      <p className="mt-0.5 text-[10px] text-mute">
                        {ws.tags.join(" · ")}
                      </p>
                    )}
                  </div>
                  {ws.role === "owner" && (
                    <div className="flex shrink-0 gap-0.5">
                      <button
                        type="button"
                        className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                        title="Edit workspace"
                        onClick={() => onStartEdit(ws)}
                      >
                        <Pen className="h-3 w-3" strokeWidth={1.5} />
                      </button>
                      <button
                        type="button"
                        className="rounded p-1 text-mute hover:bg-danger-soft hover:text-danger-text"
                        title="Delete workspace"
                        onClick={() => void onDeleteWorkspace(ws.id)}
                      >
                        <Trash2 className="h-3 w-3" strokeWidth={1.5} />
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
}