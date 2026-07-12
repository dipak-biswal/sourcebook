import { useState } from "react";
import { Loader2, Plus, Settings } from "lucide-react";
import { api, type Workspace } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { formatError } from "@/lib/utils";
import { Link } from "react-router-dom";

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
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  async function onCreate() {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const ws = await api.createWorkspace(name);
      success(`Workspace "${ws.name}" created`);
      setNewName("");
      onRefresh();
      onChange(ws.id);
    } catch (err) {
      toastError("Create failed", formatError(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <span className="text-xs text-mute">Workspace</span>
        <Link
          to="/settings"
          className="text-[11px] text-mute hover:text-ink"
        >
          <Settings className="inline-block h-3 w-3" strokeWidth={1.5} />
        </Link>
      </div>
      <select
        value={workspaceId}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
      >
        {workspaces.map((w) => (
          <option key={w.id} value={w.id}>
            {w.name}
          </option>
        ))}
      </select>
      <div className="mt-1.5 flex gap-1">
        <Input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New workspace name…"
          className="h-7 text-xs"
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); void onCreate(); }
          }}
        />
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="h-7 w-7 shrink-0"
          disabled={!newName.trim() || creating}
          onClick={() => void onCreate()}
          title="Create workspace"
        >
          {creating ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <Plus className="h-3 w-3" strokeWidth={1.5} />
          )}
        </Button>
      </div>
    </div>
  );
}
