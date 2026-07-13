import { useState } from "react";
import { ChevronsUpDown, Loader2, Plus, Settings } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type Workspace } from "@/api";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { validateWorkspaceName } from "@/lib/validation";
import { formatError } from "@/lib/utils";

type WorkspaceSelectProps = {
  workspaces: Workspace[];
  workspaceId: string;
  onChange: (id: string) => void;
  onRefresh: () => void;
};

export function WorkspaceSelect({
  workspaces,
  workspaceId,
  onChange,
  onRefresh,
}: WorkspaceSelectProps) {
  const { success, error: toastError } = useToast();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const active = workspaces.find((w) => w.id === workspaceId);

  async function onCreate() {
    const err = validateWorkspaceName(newName);
    setError(err);
    if (err) return;
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const ws = await api.createWorkspace(name);
      success(`Workspace "${ws.name}" created`);
      setNewName("");
      setError(null);
      onRefresh();
      onChange(ws.id);
      setOpen(false);
    } catch (err) {
      toastError("Create failed", formatError(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <span className="mb-1.5 block text-xs text-mute">Workspace</span>

      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            aria-label="Select workspace"
            className="h-9 w-full justify-between rounded-[6px] px-2.5 font-normal"
          >
            <span className="truncate text-sm text-ink">
              {active?.name ?? "Select workspace"}
            </span>
            <ChevronsUpDown
              className="ml-2 h-3.5 w-3.5 shrink-0 text-mute"
              strokeWidth={1.5}
            />
          </Button>
        </DropdownMenuTrigger>

        <DropdownMenuContent align="start" className="w-[var(--radix-dropdown-menu-trigger-width)]">
          <DropdownMenuLabel>Workspaces</DropdownMenuLabel>
          <DropdownMenuRadioGroup
            value={workspaceId}
            onValueChange={onChange}
          >
            {workspaces.map((w) => (
              <DropdownMenuRadioItem
                key={w.id}
                value={w.id}
                className="cursor-pointer"
              >
                <span className="truncate">{w.name}</span>
              </DropdownMenuRadioItem>
            ))}
          </DropdownMenuRadioGroup>

          <DropdownMenuSeparator />

          <div
            className="space-y-1.5 p-2"
            onPointerDown={(e) => e.stopPropagation()}
            onKeyDown={(e) => e.stopPropagation()}
          >
            <p className="text-[11px] font-medium text-mute">New workspace</p>
            <div className="flex gap-1">
              <Input
                value={newName}
                onChange={(e) => {
                  setNewName(e.target.value);
                  setError(null);
                }}
                placeholder="Name…"
                className="h-8 text-xs"
                aria-invalid={!!error || undefined}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void onCreate();
                  }
                }}
              />
              <Button
                type="button"
                variant="secondary"
                size="icon"
                className="h-8 w-8 shrink-0"
                disabled={!newName.trim() || creating}
                onClick={() => void onCreate()}
                title="Create workspace"
              >
                {creating ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
                )}
              </Button>
            </div>
            <FieldError error={error} />
          </div>

          <DropdownMenuSeparator />

          <DropdownMenuItem asChild className="cursor-pointer">
            <Link to="/settings" onClick={() => setOpen(false)}>
              <Settings className="h-3.5 w-3.5 text-mute" strokeWidth={1.5} />
              Manage workspaces
            </Link>
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  );
}