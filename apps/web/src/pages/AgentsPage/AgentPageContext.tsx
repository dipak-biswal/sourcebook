import { useCallback, useEffect, useState, type ReactNode, type SubmitEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AgentStep, type AgentRun } from "@/api";
import type { LiveTraceSpan, LlmTraceEvent } from "@/components/agents/AgentRunPanel";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import {
  makeAgentStreamHandlers,
  upsertSteps,
  upsertTraceStep,
  makeLlmEndPatch,
} from "@/hooks/useAgentStream";
import { useAgentRuns, useNotes, useWorkspaces } from "@/hooks/queries";
import { useLastWorkspace } from "@/hooks/useLastWorkspace";
import type { AgentPageContextValue } from "@/types/agents";
import { AgentPageContext } from "./agent-page-context";
import {
  AGENT_EXAMPLE_GOALS,
  STUDY_GUIDE_EXAMPLE_GOALS,
  type AgentType,
} from "@/components/agents/agent-utils";

export type AgentWorkspaceConfig = {
  agentType: AgentType;
  documentTitle: string;
  defaultGoal: string;
  exampleGoals: string[];
  maxSteps?: number;
};

const GENERAL_CONFIG: AgentWorkspaceConfig = {
  agentType: "general",
  documentTitle: "Agents",
  defaultGoal: AGENT_EXAMPLE_GOALS[0],
  exampleGoals: AGENT_EXAMPLE_GOALS,
  maxSteps: 5,
};

export const STUDY_GUIDE_CONFIG: AgentWorkspaceConfig = {
  agentType: "study_guide",
  documentTitle: "Study Guide",
  defaultGoal: STUDY_GUIDE_EXAMPLE_GOALS[0],
  exampleGoals: STUDY_GUIDE_EXAMPLE_GOALS,
  maxSteps: 4,
};

export function AgentPageProvider({
  children,
  config = GENERAL_CONFIG,
}: {
  children: ReactNode;
  config?: AgentWorkspaceConfig;
}) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle(config.documentTitle);

  const [selectedId, setSelectedId] = useState("");
  const [goal, setGoal] = useState(config.defaultGoal);
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
  const [activeToolCalls, setActiveToolCalls] = useState<{ tool_name: string; startTime: number }[]>([]);
  const [loopWarning, setLoopWarning] = useState<string | null>(null);

  const { data: workspaces = [], isLoading: loading } = useWorkspaces();
  const { workspaceId: effectiveWorkspaceId, setWorkspaceId: persistWorkspace } =
    useLastWorkspace(workspaces);
  const { data: runs = [] } = useAgentRuns(
    effectiveWorkspaceId,
    config.agentType,
  );
  const { data: notes = [] } = useNotes(effectiveWorkspaceId);
  const effectiveSelectedId = selectedId;

  const onChangeWorkspace = useCallback((id: string) => {
    persistWorkspace(id);
    setSelectedId("");
    setSelected(null);
    setError(null);
    setLiveSteps([]);
    setLiveTrace([]);
    setLiveLlmEvents([]);
    setLiveTokenUsage(null);
    setLiveGoal(null);
    setActiveToolCalls([]);
    setLoopWarning(null);
  }, [persistWorkspace]);

  const onSelect = useCallback(async (id: string) => {
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
  }, []);

  useEffect(() => {
    const runId = searchParams.get("run");
    if (!runId) return;
    setSearchParams({}, { replace: true });
    if (runId === selectedId) return;
    void (async () => {
      try {
        const run = await api.agentRun(runId);
        if (run.workspace_id && run.workspace_id !== effectiveWorkspaceId) {
          persistWorkspace(run.workspace_id);
        }
        await onSelect(runId);
      } catch (err) {
        setError(formatError(err));
      }
    })();
  }, [searchParams, selectedId, onSelect, setSearchParams, effectiveWorkspaceId, persistWorkspace]);

  function resetLiveTrace(goalText: string) {
    setLiveGoal(goalText);
    setLiveSteps([]);
    setLiveTokenUsage(null);
    setLiveLlmEvents([]);
    setLiveTrace([]);
    setActiveToolCalls([]);
    setLoopWarning(null);
  }

  async function onRun(e: SubmitEvent<HTMLFormElement>) {
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
              if (step.type === "tool_result") {
                setActiveToolCalls((prev) =>
                  prev.filter((t) => t.tool_name !== step.tool_name),
                );
              }
            },
            onTokenUsage: (usage) => setLiveTokenUsage(usage),
            onToolStart: (p) => {
              setActiveToolCalls((prev) => [
                ...prev,
                { tool_name: p.tool_name, startTime: Date.now() },
              ]);
            },
            onLoopWarning: (p) => {
              setLoopWarning(p.message);
            },
          },
          (final) => {
            setSelected(final);
            setSelectedId(final.id);
          },
        ),
        {
          maxSteps: config.maxSteps,
          agentType: config.agentType,
        },
      );
      if (run) {
        setSelected(run);
        setSelectedId(run.id);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
        });
        if (run.status === "waiting_approval") {
          success("Approval needed", "Review the write action below.");
        } else if (run.status === "completed") {
          success(
            config.agentType === "study_guide"
              ? "Study guide ready"
              : "Agent finished",
          );
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
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
        });
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
              if (step.type === "tool_result") {
                setActiveToolCalls((prev) =>
                  prev.filter((t) => t.tool_name !== step.tool_name),
                );
              }
            },
            onTokenUsage: (usage) => setLiveTokenUsage(usage),
            onToolStart: (p) => {
              setActiveToolCalls((prev) => [
                ...prev,
                { tool_name: p.tool_name, startTime: Date.now() },
              ]);
            },
            onLoopWarning: (p) => {
              setLoopWarning(p.message);
            },
          },
          (final) => {
            setSelected(final);
          },
          false,
        ),
      );
      if (run) {
        setSelected(run);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
        });
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
      const run = await api.startAgentRun(effectiveWorkspaceId, goalText, {
        maxSteps: config.maxSteps,
        agentType: config.agentType,
      });
      await queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
      });
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

  async function onDeleteRun(id: string) {
    if (!(await confirmAction("Delete this run?", "This cannot be undone."))) return;
    setError(null);
    setSelected(null);
    setSelectedId("");
    try {
      await api.deleteAgentRun(id);
      await queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
      });
      success("Run deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  const value: AgentPageContextValue = {
    agentType: config.agentType,
    exampleGoals: config.exampleGoals,
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
    activeToolCalls,
    loopWarning,
    onChangeWorkspace,
    onSelectRun: onSelect,
    onGoalChange: setGoal,
    onRun,
    onApprove,
    onDeleteNote,
    onDeleteRun,
    onSaveLearningNote,
    onRefresh: () => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
      });
      void queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
    },
    onDismissError: () => setError(null),
    onRetryError: () => {
      setError(null);
      void queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId, config.agentType],
      });
      void queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
      if (selectedId) void onSelect(selectedId);
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
