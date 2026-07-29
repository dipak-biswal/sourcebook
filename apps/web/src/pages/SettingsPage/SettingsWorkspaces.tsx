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
import {
  parseTagInput,
  SUGGESTED_WORKSPACE_TAGS,
  toggleTagInInput,
} from "./workspace-tags";
import { WorkspaceActivityPanel } from "./WorkspaceActivityPanel";
import { CreateWorkspaceModal } from "./CreateWorkspaceModal";

export function SettingsWorkspaces() {
  const queryClient = useQueryClient();
  const {
    workspaces,
    editingId,
    editName,
    editDescription,
    editTags,
    savingEdit,
    onStartEdit,
    onEditNameChange,
    onEditDescriptionChange,
    onEditTagsChange,
    onCancelEdit,
    onSaveEdit,
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

  const activeId =
    selectedId && workspaces.some((w) => w.id === selectedId)
      ? selectedId
      : (workspaces[0]?.id ?? null);
  const active = workspaces.find((w) => w.id === activeId) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Workspaces</h2>
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
        <div className="rounded-vercel-md border border-hairline bg-canvas p-2">
          {workspaces.length === 0 ? (
            <p className="px-2 py-4 text-xs text-mute">No workspaces yet.</p>
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
                        "flex w-full items-center gap-2 rounded-[8px] px-2.5 py-2 text-left transition-colors",
                        selected
                          ? "bg-ink text-[var(--canvas)]"
                          : "text-body hover:bg-canvas-soft",
                      )}
                    >
                      <LayoutGrid
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          selected ? "text-[var(--canvas)]/80" : "text-mute",
                        )}
                        strokeWidth={1.5}
                      />
                      <span className="min-w-0 flex-1 truncate text-xs font-semibold">
                        {ws.name}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="min-w-0 space-y-3">
          {!active ? (
            <div className="rounded-vercel-md border border-hairline bg-canvas p-6 text-center text-xs text-mute">
              Select a workspace
            </div>
          ) : (
            <>
              <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
                {editingId === active.id ? (
                  <div className="space-y-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        type="button"
                        variant="secondary"
                        size="icon"
                        className="h-7 w-7"
                        disabled={!editName.trim() || savingEdit}
                        onClick={() => handleEditSubmit(active.id)}
                        aria-label="Save"
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
                        aria-label="Cancel"
                      >
                        <X className="h-3 w-3" strokeWidth={1.5} />
                      </Button>
                    </div>
                    <Input
                      value={editName}
                      onChange={(e) => {
                        onEditNameChange(e.target.value);
                        setEditErrors({});
                      }}
                      className="h-8 text-sm"
                      autoFocus
                      aria-invalid={!!editErrors.name || undefined}
                      placeholder="Name"
                    />
                    <FieldError error={editErrors.name} />
                    <textarea
                      value={editDescription}
                      onChange={(e) => onEditDescriptionChange(e.target.value)}
                      className="min-h-[5rem] w-full rounded-[6px] border border-hairline bg-canvas px-2.5 py-2 text-xs text-body"
                      placeholder="Description (optional)"
                    />
                    <div>
                      <Input
                        value={editTags}
                        onChange={(e) => onEditTagsChange(e.target.value)}
                        className="h-8 text-xs"
                        placeholder="Tags (optional)"
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
                  </div>
                ) : (
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-ink">
                        {active.name}
                      </div>
                      {active.description ? (
                        <p className="mt-1 text-xs leading-relaxed text-mute">
                          {active.description}
                        </p>
                      ) : null}
                      {active.tags && active.tags.length > 0 ? (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {active.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full border border-hairline bg-canvas-soft px-2 py-0.5 text-[10px] text-mute"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : null}
                    </div>
                    {active.role === "owner" && (
                      <div className="flex shrink-0 gap-0.5">
                        <button
                          type="button"
                          className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                          title="Edit"
                          onClick={() => onStartEdit(active)}
                        >
                          <Pen className="h-3.5 w-3.5" strokeWidth={1.5} />
                        </button>
                        <button
                          type="button"
                          className="rounded p-1 text-mute hover:bg-danger-soft hover:text-danger-text"
                          title="Delete"
                          onClick={() => void onDeleteWorkspace(active.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
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
