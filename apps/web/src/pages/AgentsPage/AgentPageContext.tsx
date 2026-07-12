import { createContext, useContext, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AgentStep } from "@/api";
import type { AgentRun } from "@/api";
import type { LiveTraceSpan, LlmTraceEvent } from "@/components/agents/AgentRunPanel";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import {
  makeAgentStreamHandlers,
  makeApprovalHandlers,
  upsertSteps,
  upsertTraceStep,
  makeLlmEndPatch,
} from "@/hooks/useAgentStream";
import { useAgentRuns, useNotes, useWorkspaces } from "@/hooks/queries";

type AgentPageContextValue = {
  workspaces: Workspace[];
  workspaceId: string;
  runs: AgentRun[];
  notes: NoteSummary[];
  selected: AgentRun | null;
  selectedId: string;
  goal: string;
  error: string | null;
  running: boolean;
  approving: boolean;
  sidebarOpen: boolean;
  savingNote: boolean;
  loading: boolean;
  liveGoal: string | null;
  liveSteps: AgentStep[];
  liveTokenUsage: number | null;
  liveLlmEvents: LlmTraceEvent[];
  liveTrace: LiveTraceSpan[];
  onChangeWorkspace: (id: string) => void;
  onSelectRun: (id: string) => void;
  onGoalChange: (v: string) => void;
  onRun: (e: FormEvent) => void;
  onApprove: (approve: boolean) => void;
  onDeleteNote: (id: string) => void;
  onSaveLearningNote: (title: string, body: string) => void;
  onRefresh: () => void;
  onToggleSidebar: () => void;
  onSidebarClose: () => void;
  onLogout: () => void;
};

type Workspace = { id: string; name: string };
type NoteSummary = { id: string; title: string; body: string | null; created_at: string };

const AgentPageContext = createContext<AgentPageContextValue | null>(null);

import { AGENT_EXAMPLE_GOALS } from "@/components/agents/shared";

export function AgentPageProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle("Agents");

  const [workspaceId, setWorkspaceId] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [goal, setGoal] = useState(AGENT_EXAMPLE_GOALS[0]);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [approving, setApproving] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [liveGoal, setLiveGoal] = useState<string | null>(null);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [liveTokenUsage, setLiveTokenUsage] = useState<number | null>(null);
  const [liveLlmEvents, setLiveLlmEvents] = useState<LlmTraceEvent[]>([]);
  const [liveTrace, setLiveTrace] = useState<LiveTraceSpan[]>([]);
  const [selected, setSelected] = useState<AgentRun | null>(null);

  const { data: workspaces = [], isLoading: loading } = useWorkspaces();
  const effectiveWorkspaceId = workspaceId || workspaces[0]?.id || "";
  const { data: runs = [] } = useAgentRuns(effectiveWorkspaceId);
  const { data: notes = [] } = useNotes(effectiveWorkspaceId);
  const effectiveSelectedId = selectedId || runs[0]?.id || "";

  async function onSelect(id: string) {
    setSelectedId(id);
    setError(null);
    setLiveSteps([]);
    setLiveTrace([]);
    setLiveLlmEvents([]);
    setLiveTokenUsage(null);
    setLiveGoal(null);
    try {
      setSelected(await api.agentRun(id));
    } catch (err) {
      setError(formatError(err));
    }
  }

  function resetLiveTrace(goalText: string) {
    setLiveGoal(goalText);
    setLiveSteps([]);
    setLiveTokenUsage(null);
    setLiveLlmEvents([]);
    setLiveTrace([]);
  }

  async function onRun(e: FormEvent) {
    e.preventDefault();
    if (!effectiveWorkspaceId || !goal.trim() || running) return;
    const goalText = goal.trim();
    resetLiveTrace(goalText);
    setRunning(true);
    setError(null);
    setSelected(null);
    setSelectedId("");
    try {
      const run = await api.startAgentRunStream(
        effectiveWorkspaceId,
        goalText,
        makeAgentStreamHandlers(
          {
            onLlmStart: (event) => {
              setLiveLlmEvents((prev) => [
                ...prev.filter((e) => e.status === "done"),
                event,
              ]);
              setLiveTrace((prev) => [...prev, { kind: "llm", event }]);
            },
            onLlmEnd: (p) => {
              const patch = makeLlmEndPatch(p);
              setLiveLlmEvents((prev) =>
                prev.map((e) =>
                  e.status === "running"
                    ? { ...e, ...patch, status: "done" as const }
                    : e,
                ),
              );
              setLiveTrace((prev) =>
                prev.map((node) =>
                  node.kind === "llm" && node.event.status === "running"
                    ? {
                        kind: "llm" as const,
                        event: { ...node.event, ...patch, status: "done" as const },
                      }
                    : node,
                ),
              );
            },
            onStep: (step) => {
              setLiveSteps((prev) => upsertSteps(prev, step));
              setLiveTrace((prev) => upsertTraceStep(prev, step));
            },
            onTokenUsage: (usage) => setLiveTokenUsage(usage),
          },
          (final) => {
            setSelected(final);
            setSelectedId(final.id);
          },
        ),
        5,
      );
      if (run) {
        setSelected(run);
        setSelectedId(run.id);
        await queryClient.invalidateQueries({ queryKey: ["agentRuns", effectiveWorkspaceId] });
        if (run.status === "waiting_approval") {
          success("Approval needed", "Review the write action below.");
        } else if (run.status === "completed") {
          success("Agent finished");
        }
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Agent failed", msg);
    } finally {
      setRunning(false);
      setLiveGoal(null);
    }
  }

  async function onApprove(approve: boolean) {
    if (!selected || approving) return;
    setApproving(true);
    setError(null);
    setRunning(true);
    setLiveGoal(selected.goal);
    try {
      if (!approve) {
        const run = await api.approveAgentRun(selected.id, false);
        await queryClient.invalidateQueries({ queryKey: ["agentRuns", effectiveWorkspaceId] });
        setSelected(run);
        success("Action rejected");
        return;
      }
      const seedSteps = selected.steps ?? [];
      setLiveSteps(seedSteps);
      setLiveTrace(
        seedSteps.map((step) => ({
          kind: "step" as const,
          step,
        })),
      );
      setLiveTokenUsage(selected.token_usage);
      const run = await api.approveAgentRunStream(
        selected.id,
        true,
        makeApprovalHandlers(
          {
            onLlmStart: (event) => {
              setLiveLlmEvents((prev) => [
                ...prev.filter((e) => e.status === "done"),
                event,
              ]);
              setLiveTrace((prev) => [...prev, { kind: "llm", event }]);
            },
            onLlmEnd: (p) => {
              const patch = makeLlmEndPatch(p);
              setLiveLlmEvents((prev) =>
                prev.map((e) =>
                  e.status === "running"
                    ? { ...e, ...patch, status: "done" as const }
                    : e,
                ),
              );
              setLiveTrace((prev) =>
                prev.map((node) =>
                  node.kind === "llm" && node.event.status === "running"
                    ? {
                        kind: "llm" as const,
                        event: { ...node.event, ...patch, status: "done" as const },
                      }
                    : node,
                ),
              );
            },
            onStep: (step) => {
              setLiveSteps((prev) => upsertSteps(prev, step));
              setLiveTrace((prev) => upsertTraceStep(prev, step));
            },
            onTokenUsage: (usage) => setLiveTokenUsage(usage),
          },
          (final) => {
            setSelected(final);
          },
        ),
      );
      if (run) {
        setSelected(run);
        await queryClient.invalidateQueries({ queryKey: ["agentRuns", effectiveWorkspaceId] });
        await queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
        success("Action approved — agent continued");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Approval failed", msg);
    } finally {
      setApproving(false);
      setRunning(false);
      setLiveGoal(null);
    }
  }

  async function onSaveLearningNote(title: string, body: string) {
    if (!effectiveWorkspaceId || savingNote) return;
    setSavingNote(true);
    setError(null);
    const goalText =
      `Create a note titled ${JSON.stringify(title)} with body:\n${body}`;
    try {
      const run = await api.startAgentRun(effectiveWorkspaceId, goalText, 5);
      await queryClient.invalidateQueries({ queryKey: ["agentRuns", effectiveWorkspaceId] });
      setSelected(run);
      if (run.status === "waiting_approval") {
        success("Approve the note", "Review create_note, then Approve.");
      } else {
        success("Note flow finished");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Could not start save-as-note", msg);
    } finally {
      setSavingNote(false);
    }
  }

  async function onDeleteNote(id: string) {
    if (!(await confirmAction("Delete this note?", "This cannot be undone."))) return;
    setError(null);
    try {
      await api.deleteNote(id);
      await queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
      success("Note deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  const value: AgentPageContextValue = {
    workspaces,
    workspaceId: effectiveWorkspaceId,
    runs,
    notes,
    selected,
    selectedId: effectiveSelectedId,
    goal,
    error,
    running,
    approving,
    sidebarOpen,
    savingNote,
    loading,
    liveGoal,
    liveSteps,
    liveTokenUsage,
    liveLlmEvents,
    liveTrace,
    onChangeWorkspace: setWorkspaceId,
    onSelectRun: onSelect,
    onGoalChange: setGoal,
    onRun,
    onApprove,
    onDeleteNote,
    onSaveLearningNote,
    onRefresh: () => {
      queryClient.invalidateQueries({ queryKey: ["agentRuns", effectiveWorkspaceId] });
      queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
    },
    onToggleSidebar: () => setSidebarOpen(true),
    onSidebarClose: () => setSidebarOpen(false),
    onLogout: () => navigate("/login", { replace: true }),
  };

  return (
    <AgentPageContext.Provider value={value}>
      {children}
    </AgentPageContext.Provider>
  );
}

export function useAgentPage(): AgentPageContextValue {
  const ctx = useContext(AgentPageContext);
  if (!ctx) throw new Error("useAgentPage must be used within AgentPageProvider");
  return ctx;
}
