import { useCallback, useEffect, useState } from "react";
import type { Workspace } from "@/api";
import { readLastWorkspaceId, writeLastWorkspaceId } from "@/lib/last-workspace";

export function useLastWorkspace(workspaces: Workspace[]) {
  const [workspaceId, setWorkspaceIdState] = useState("");

  useEffect(() => {
    if (!workspaces.length) {
      setWorkspaceIdState("");
      return;
    }
    setWorkspaceIdState((current) => {
      if (current && workspaces.some((w) => w.id === current)) return current;
      const saved = readLastWorkspaceId();
      const fromSaved = saved
        ? workspaces.find((w) => w.id === saved)
        : undefined;
      return fromSaved?.id ?? workspaces[0].id;
    });
  }, [workspaces]);

  const setWorkspaceId = useCallback((id: string) => {
    setWorkspaceIdState(id);
    if (id) writeLastWorkspaceId(id);
  }, []);

  const effectiveId =
    workspaceId && workspaces.some((w) => w.id === workspaceId)
      ? workspaceId
      : workspaces[0]?.id ?? "";

  return { workspaceId: effectiveId, setWorkspaceId };
}