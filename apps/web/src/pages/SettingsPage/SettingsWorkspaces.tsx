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
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { validateWorkspaceName } from "@/lib/validation";
import { cn } from "@/lib/utils";
import { useSettingsPage } from "./settings-page-context";
import { WorkspaceContextPreviewPanel } from "./WorkspaceContextPreview";
import {
  parseTagInput,
  SUGGESTED_WORKSPACE_TAGS,
  toggleTagInInput,
  WORKSPACE_DESCRIPTION_TEMPLATE,
} from "./workspace-tags";
import { WorkspaceActivityPanel } from "./WorkspaceActivityPanel";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";

export function SettingsWorkspaces() {
  const queryClient = useQueryClient();
  const {
    workspaces,
    editingId, editName, editDescription, editTags, savingEdit,
    onStartEdit, onEditNameChange, onEditDescriptionChange, onEditTagsChange,
    onCancelEdit, onSaveEdit,
    onDeleteWorkspace,
  } = useSettingsPage();
  const [editErrors, setEditErrors] = useState<{ name?: string }>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  function handleEditSubmit(id: string) {
    const err = validateWorkspaceName(editName);
    setEditErrors({ name: err ?? undefined });
    if (!err) void onSaveEdit(id);
  }

  // Prefer explicit selection; fall back to first workspace.
  const activeId =
    selectedId && workspaces.some((w) => w.id === selectedId)
      ? selectedId
      : workspaces[0]?.id ?? null;
  const active = workspaces.find((w) => w.id === activeId) ?? null;

  return (
    <div className="space-y-4">
      <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-ink">Workspaces</h2>
            <p className="mt-1 text-xs text-mute">
              Select a workspace to inspect topics and every LLM, tool, and web
              search call (with prompts and outputs).
            </p>
          </div>
          <Button
            type="button"
            size="sm"
            className="h-8 shrink-0"
            onClick={() => setCreateOpen(true)}
          >
            <Plus className="mr-1 h-3.5 w-3.5" strokeWidth={1.5} />
            Add workspace
          </Button>
        </div>
      </div>

      <CreateWorkspaceModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(id) => {
          setSelectedId(id);
          void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
          void queryClient.invalidateQueries({ queryKey: ["learnTopics"] });
        }}
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,14rem)_minmax(0,1fr)]">
        {/* Workspace list */}
        <div className="rounded-vercel-md border border-hairline bg-canvas p-2">
          <div className="px-2 py-1.5 text-[10px] font-bold uppercase tracking-wide text-mute">
            All workspaces
          </div>
          {workspaces.length === 0 ? (
            <p className="px-2 py-4 text-xs text-mute">No workspaces.</p>
          ) : (
            <ul className="space-y-0.5">
              {workspaces.map((ws) => {
                const selected = ws.id === activeId;
                return (
                  <li key={ws.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(ws.id)}
                      className={cn(
                        "flex w-full items-start gap-2 rounded-[8px] px-2.5 py-2 text-left transition-colors",
                        selected
                          ? "bg-ink text-[var(--canvas)]"
                          : "hover:bg-canvas-soft text-body",
                      )}
                    >
                      <LayoutGrid
                        className={cn(
                          "mt-0.5 h-3.5 w-3.5 shrink-0",
                          selected ? "text-[var(--canvas)]/80" : "text-mute",
                        )}
                        strokeWidth={1.5}
                      />
                      <span className="min-w-0">
                        <span className="block truncate text-xs font-semibold">
                          {ws.name}
                        </span>
                        <span
                          className={cn(
                            "block text-[10px] uppercase",
                            selected ? "text-[var(--canvas)]/70" : "text-mute",
                          )}
                        >
                          {ws.role}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Selected workspace detail */}
        <div className="min-w-0 space-y-3">
          {!active ? (
            <div className="rounded-vercel-md border border-hairline bg-canvas p-6 text-center text-xs text-mute">
              Create or select a workspace to view topics and call history.
            </div>
          ) : (
            <>
              <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
                {editingId === active.id ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
                      <span className="text-[10px] uppercase text-mute">{active.role}</span>
                      <div className="ml-auto flex gap-1">
                        <Button
                          type="button"
                          variant="secondary"
                          size="icon"
                          className="h-7 w-7"
                          disabled={!editName.trim() || savingEdit}
                          onClick={() => handleEditSubmit(active.id)}
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
                      className="min-h-[6rem] w-full rounded-[6px] border border-hairline bg-canvas px-2.5 py-2 text-xs text-body"
                      placeholder={WORKSPACE_DESCRIPTION_TEMPLATE}
                    />
                    <div>
                      <Input
                        value={editTags}
                        onChange={(e) => onEditTagsChange(e.target.value)}
                        className="h-7 text-xs"
                        placeholder="Tags, comma-separated (optional)"
                      />
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {SUGGESTED_WORKSPACE_TAGS.map((tag) => {
                          const isOn = parseTagInput(editTags).includes(tag);
                          return (
                            <button
                              key={tag}
                              type="button"
                              onClick={() =>
                                onEditTagsChange(toggleTagInInput(editTags, tag))
                              }
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-[10px] transition-colors",
                                isOn
                                  ? "border-ink bg-ink text-[var(--canvas)]"
                                  : "border-hairline text-mute hover:border-ink/30 hover:text-ink",
                              )}
                            >
                              {tag}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                    <WorkspaceContextPreviewPanel
                      workspaceId={active.id}
                      name={editName}
                      description={editDescription}
                      tags={parseTagInput(editTags)}
                    />
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <LayoutGrid className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-ink">
                          {active.name}
                        </span>
                        <span className="text-[10px] uppercase text-mute">{active.role}</span>
                      </div>
                      {active.description && (
                        <p className="mt-0.5 text-xs text-mute">
                          {active.description}
                        </p>
                      )}
                      {active.tags && active.tags.length > 0 && (
                        <p className="mt-0.5 text-[10px] text-mute">
                          {active.tags.join(" · ")}
                        </p>
                      )}
                    </div>
                    {active.role === "owner" && (
                      <div className="flex shrink-0 gap-0.5">
                        <button
                          type="button"
                          className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                          title="Edit workspace"
                          onClick={() => onStartEdit(active)}
                        >
                          <Pen className="h-3 w-3" strokeWidth={1.5} />
                        </button>
                        <button
                          type="button"
                          className="rounded p-1 text-mute hover:bg-danger-soft hover:text-danger-text"
                          title="Delete workspace"
                          onClick={() => void onDeleteWorkspace(active.id)}
                        >
                          <Trash2 className="h-3 w-3" strokeWidth={1.5} />
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>

              <WorkspaceActivityPanel
                key={active.id}
                workspaceId={active.id}
                workspaceName={active.name}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
