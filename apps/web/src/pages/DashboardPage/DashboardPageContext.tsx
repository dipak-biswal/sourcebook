import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useDocuments, useConversations, useAgentRuns, useNotes, useWorkspaces, useMe } from "@/hooks/queries";
import type { DashboardPageContextValue } from "@/types/dashboard";
import { DashboardPageContext } from "./dashboard-page-context";

type RecentItem = {
  id: string;
  type: "document" | "conversation" | "agent_run" | "note";
  label: string;
  subtitle: string;
  href: string;
  created_at: string;
};

export function DashboardPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [workspaceId, setWorkspaceId] = useState("");
  const { data: workspaces = [] } = useWorkspaces();
  const effectiveWorkspaceId = workspaceId || workspaces[0]?.id || "";

  useEffect(() => {
    if (!workspaces.length || workspaceId) return;
    setWorkspaceId(workspaces[0].id);
  }, [workspaces, workspaceId]);
  const { data: user } = useMe();
  const { data: documents = [], isLoading: docsLoading } = useDocuments(effectiveWorkspaceId);
  const { data: conversations = [], isLoading: convsLoading } = useConversations(effectiveWorkspaceId);
  const { data: agentRuns = [], isLoading: runsLoading } = useAgentRuns(effectiveWorkspaceId);
  const { data: notes = [], isLoading: notesLoading } = useNotes(effectiveWorkspaceId);

  const loading = docsLoading || convsLoading || runsLoading || notesLoading;

  const recent: RecentItem[] = [
    ...documents.slice(0, 3).map((d) => ({
      id: d.id,
      type: "document" as const,
      label: d.filename,
      subtitle: d.status,
      href: "/documents",
      created_at: d.created_at,
    })),
    ...conversations.slice(0, 3).map((c) => ({
      id: c.id,
      type: "conversation" as const,
      label: c.title,
      subtitle: "Chat session",
      href: "/chat",
      created_at: c.created_at,
    })),
    ...agentRuns.slice(0, 3).map((r) => ({
      id: r.id,
      type: "agent_run" as const,
      label: r.goal,
      subtitle: r.status,
      href: "/agents",
      created_at: r.created_at,
    })),
    ...notes.slice(0, 3).map((n) => ({
      id: n.id,
      type: "note" as const,
      label: n.title,
      subtitle: "Note",
      href: `/notes/${n.id}`,
      created_at: n.created_at,
    })),
  ].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 8);

  const value: DashboardPageContextValue = {
    workspaces,
    workspaceId: effectiveWorkspaceId,
    documentsCount: documents.length,
    readyDocumentsCount: documents.filter((d) => d.status === "ready").length,
    conversationsCount: conversations.length,
    agentRunsCount: agentRuns.length,
    notesCount: notes.length,
    loading,
    userEmail: user?.email || "",
    recent,
    onChangeWorkspace: setWorkspaceId,
    onRefreshWorkspaces: () => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    },
    onLogout: () => navigate("/login", { replace: true }),
  };

  return (
    <DashboardPageContext.Provider value={value}>
      {children}
    </DashboardPageContext.Provider>
  );
}
