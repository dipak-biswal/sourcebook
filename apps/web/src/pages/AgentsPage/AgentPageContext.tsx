import { useCallback, useEffect, useMemo, useState, type ReactNode, type SubmitEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AgentStep, type AgentRun } from "@/api";
import type { LiveTraceSpan, LlmTraceEvent } from "@/components/agents/trace-types";
import { useToast } from "@/components/ui/toast";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { confirmAction } from "@/lib/confirm";
import { formatError } from "@/lib/utils";
import {
  makeAgentStreamHandlers,
  upsertSteps,
  upsertTraceStep,
  makeLlmEndPatch,
  appendLlmStream,
  patchRunningLlmWithDelta,
} from "@/hooks/useAgentStream";
import { useAgentRuns, useDocuments, useWorkspaces } from "@/hooks/queries";
import { useLastWorkspace } from "@/hooks/useLastWorkspace";
import type { AgentPageContextValue } from "@/types/agents";
import { AgentPageContext } from "./agent-page-context";
import {
  buildWorkspaceAgentExamples,
  isPresentationPending,
} from "@/components/agents/agent-utils";

const DEFAULT_MAX_STEPS = 5;

export function AgentPageProvider({
  children,
}: {
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();
  useDocumentTitle("Agents");

  const [selectedId, setSelectedId] = useState("");
  const [goal, setGoal] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [approving, setApproving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [savingNote, setSavingNote] = useState(false);
  const [liveGoal, setLiveGoal] = useState<string | null>(null);
  const [liveExecutionTrace, setLiveExecutionTrace] =
    useState<import("@/api").ExecutionTrace | null>(null);
  const [liveSteps, setLiveSteps] = useState<AgentStep[]>([]);
  const [liveTokenUsage, setLiveTokenUsage] = useState<number | null>(null);
  const [liveLlmEvents, setLiveLlmEvents] = useState<LlmTraceEvent[]>([]);
  const [liveTrace, setLiveTrace] = useState<LiveTraceSpan[]>([]);
  const [selected, setSelected] = useState<AgentRun | null>(null);
  const [activeToolCalls, setActiveToolCalls] = useState<{ tool_name: string; startTime: number }[]>([]);
  const [loopWarning, setLoopWarning] = useState<string | null>(null);
  const [liveSkeleton, setLiveSkeleton] =
    useState<import("@/api").PresentationSkeleton | null>(null);

  const { data: workspaces = [], isLoading: loading } = useWorkspaces();
  const { workspaceId: effectiveWorkspaceId, setWorkspaceId: persistWorkspace } =
    useLastWorkspace(workspaces);
  const { data: runs = [] } = useAgentRuns(effectiveWorkspaceId);
  const { data: documents = [] } = useDocuments(effectiveWorkspaceId);
  const effectiveSelectedId = selectedId;
  const selectedWorkspace = useMemo(
    () => workspaces.find((w) => w.id === effectiveWorkspaceId),
    [workspaces, effectiveWorkspaceId],
  );
  const exampleGoals = useMemo(
    () => buildWorkspaceAgentExamples(selectedWorkspace, documents),
    [selectedWorkspace, documents],
  );

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
    setLiveExecutionTrace(null);
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
    setLiveExecutionTrace(null);
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
    setLiveExecutionTrace(null);
    setLiveSteps([]);
    setLiveTokenUsage(null);
    setLiveLlmEvents([]);
    setLiveTrace([]);
    setActiveToolCalls([]);
    setLoopWarning(null);
    setLiveSkeleton(null);
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
            onTrace: setLiveExecutionTrace,
            onLlmStart: (event) => {
              setLiveLlmEvents((prev) => [
                ...prev.filter((e) => e.status === "done"),
                event,
              ]);
              setLiveTrace((prev) => [...prev, { kind: "llm", event }]);
            },
            onLlmDelta: (p) => {
              setLiveLlmEvents((prev) =>
                prev.map((e) =>
                  e.status === "running"
                    ? appendLlmStream(e, p.delta, p.turn_id)
                    : e,
                ),
              );
              setLiveTrace((prev) =>
                patchRunningLlmWithDelta(prev, p.delta, p.turn_id),
              );
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
            setLiveExecutionTrace(final.execution_trace ?? null);
          },
        ),
        { maxSteps: DEFAULT_MAX_STEPS },
      );
      if (run) {
        setSelected(run);
        setSelectedId(run.id);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId],
        });
        if (run.status === "waiting_approval") {
          if (isPresentationPending(run.pending_tool)) {
            success("Answer ready", "Choose whether to view it in the UI.");
          } else {
            success("Approval needed", "Review the write action below.");
          }
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
      setActiveToolCalls([]);
    }
  }

  async function onApprove(approve: boolean) {
    if (!selected || approving) return;
    const presentationPending = isPresentationPending(selected.pending_tool);
    setApproving(true);
    setError(null);
    if (!presentationPending || approve) {
      setRunning(true);
      setLiveGoal(selected.goal);
    }
    try {
      if (presentationPending && !approve) {
        const run = await api.approveAgentRun(selected.id, false);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId],
        });
        setSelected(run);
        setLiveExecutionTrace(run.execution_trace ?? null);
        success("Keeping text answer");
        return;
      }
      if (presentationPending && approve) {
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
              onTrace: setLiveExecutionTrace,
              onLlmStart: (event) => {
                setLiveLlmEvents((prev) => [
                  ...prev.filter((e) => e.status === "done"),
                  event,
                ]);
                setLiveTrace((prev) => [...prev, { kind: "llm", event }]);
              },
              onLlmDelta: (p) => {
                setLiveLlmEvents((prev) =>
                  prev.map((e) =>
                    e.status === "running"
                      ? appendLlmStream(e, p.delta, p.turn_id)
                      : e,
                  ),
                );
                setLiveTrace((prev) =>
                  patchRunningLlmWithDelta(prev, p.delta, p.turn_id),
                );
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
              onPresentationSkeleton: (p) => {
                setLiveSkeleton(p);
              },
              onStatus: (p) => {
                if (p.presentation_spec) {
                  setLiveSkeleton(null);
                  setSelected((prev) =>
                    prev
                      ? { ...prev, presentation_spec: p.presentation_spec ?? null }
                      : prev,
                  );
                }
                if (p.token_usage != null) setLiveTokenUsage(p.token_usage);
              },
            },
            (final) => {
              setSelected(final);
              setLiveSkeleton(null);
              setLiveExecutionTrace(final.execution_trace ?? null);
            },
            false,
          ),
        );
        if (run) {
          setSelected(run);
          await queryClient.invalidateQueries({
            queryKey: ["agentRuns", effectiveWorkspaceId],
          });
          success("Visual summary ready", "Still on Trace — open Visual summary when you want.");
        }
        return;
      }
      if (!approve) {
        const run = await api.approveAgentRun(selected.id, false);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId],
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
            onTrace: setLiveExecutionTrace,
            onLlmStart: (event) => {
              setLiveLlmEvents((prev) => [
                ...prev.filter((e) => e.status === "done"),
                event,
              ]);
              setLiveTrace((prev) => [...prev, { kind: "llm", event }]);
            },
            onLlmDelta: (p) => {
              setLiveLlmEvents((prev) =>
                prev.map((e) =>
                  e.status === "running"
                    ? appendLlmStream(e, p.delta, p.turn_id)
                    : e,
                ),
              );
              setLiveTrace((prev) =>
                patchRunningLlmWithDelta(prev, p.delta, p.turn_id),
              );
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
            setLiveExecutionTrace(final.execution_trace ?? null);
          },
          false,
        ),
      );
      if (run) {
        setSelected(run);
        await queryClient.invalidateQueries({
          queryKey: ["agentRuns", effectiveWorkspaceId],
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
      setActiveToolCalls([]);
    }
  }

  async function onSaveLearningNote(title: string, body: string) {
    if (!effectiveWorkspaceId || savingNote) return;
    setSavingNote(true);
    setError(null);
    try {
      await api.createNote(effectiveWorkspaceId, title, body);
      await queryClient.invalidateQueries({
        queryKey: ["notes", effectiveWorkspaceId],
      });
      success("Saved as note", "Open Notes to edit or continue studying.");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Could not save note", msg);
    } finally {
      setSavingNote(false);
    }
  }

  async function onCancelRun() {
    if (!selected || cancelling) return;
    if (
      !(await confirmAction(
        "Cancel this run?",
        "Stops waiting for approval and marks the run cancelled. You can still read the answer so far.",
      ))
    ) {
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      const run = await api.cancelAgentRun(selected.id);
      setSelected(run);
      setLiveExecutionTrace(run.execution_trace ?? null);
      setLiveSkeleton(null);
      setActiveToolCalls([]);
      setRunning(false);
      await queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId],
      });
      success("Run cancelled");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Cancel failed", msg);
    } finally {
      setCancelling(false);
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
        queryKey: ["agentRuns", effectiveWorkspaceId],
      });
      success("Run deleted");
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Delete failed", msg);
    }
  }

  const value: AgentPageContextValue = {
    agentType: "general" as const,
    exampleGoals,
    workspaces,
    workspaceId: effectiveWorkspaceId,
    runs,
    selected,
    selectedId: effectiveSelectedId,
    goal,
    error,
    running,
    approving,
    cancelling,
    sidebarOpen,
    savingNote,
    loading,
    liveGoal,
    liveExecutionTrace,
    liveSteps,
    liveTokenUsage,
    liveLlmEvents,
    liveTrace,
    activeToolCalls,
    loopWarning,
    liveSkeleton,
    onChangeWorkspace,
    onSelectRun: onSelect,
    onGoalChange: setGoal,
    onRun,
    onApprove,
    onCancelRun,
    onDeleteRun,
    onSaveLearningNote,
    onRefresh: () => {
      void queryClient.invalidateQueries({ queryKey: ["workspaces"] });
      void queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId],
      });
      void queryClient.invalidateQueries({ queryKey: ["notes", effectiveWorkspaceId] });
    },
    onDismissError: () => setError(null),
    onRetryError: () => {
      setError(null);
      void queryClient.invalidateQueries({
        queryKey: ["agentRuns", effectiveWorkspaceId],
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
