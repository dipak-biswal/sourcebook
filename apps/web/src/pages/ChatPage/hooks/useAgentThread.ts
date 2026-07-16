import { useState, type RefObject } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AgentRun, type ExecutionTrace } from "@/api";
import type {
  LiveTraceSpan,
  LlmTraceEvent,
} from "@/components/agents/trace-types";
import { useToast } from "@/components/ui/toast";
import { formatError } from "@/lib/utils";
import {
  makeAgentStreamHandlers,
  upsertSteps,
  upsertTraceStep,
  makeLlmEndPatch,
} from "@/hooks/useAgentStream";
import { isPresentationPending } from "@/components/agents/agent-utils";
import type { AgentThreadItem } from "@/types/chat";

export function useAgentThread(
  workspaceId: string,
  setAgentRunId: (id: string) => void,
  setError: (err: string | null) => void,
  setInput: (v: string) => void,
  bottomRef: RefObject<HTMLDivElement | null>,
  setModePersist: (mode: "chat" | "agent") => void,
) {
  const { success, error: toastError } = useToast();
  const queryClient = useQueryClient();

  const [agentThread, setAgentThread] = useState<AgentThreadItem[]>([]);
  const [approving, setApproving] = useState(false);
  const [savingNote, setSavingNote] = useState(false);

  function threadFromRun(run: AgentRun): AgentThreadItem[] {
    const content =
      run.final_answer ||
      (run.status === "waiting_approval"
        ? "Waiting for your approval on a write action…"
        : run.error
          ? `Agent failed: ${run.error}`
          : run.status === "completed"
            ? "(empty answer)"
            : `Status: ${run.status}`);
    return [
      {
        id: `agent-user-${run.id}`,
        role: "user",
        content: run.goal,
      },
      {
        id: `agent-asst-${run.id}`,
        role: "assistant",
        content,
        run,
        pending: false,
        goal: run.goal,
        liveSteps: run.steps,
        liveTokenUsage: run.token_usage,
        liveTrace: (run.steps ?? []).map((step) => ({
          kind: "step" as const,
          step,
        })),
        liveExecutionTrace: run.execution_trace ?? null,
      },
    ];
  }

  function applyRunToThread(asstId: string, run: AgentRun) {
    const content =
      run.final_answer ||
      (run.status === "waiting_approval"
        ? "Waiting for your approval on a write action…"
        : run.error
          ? `Agent failed: ${run.error}`
          : run.status === "completed"
            ? "(empty answer)"
            : `Status: ${run.status}`);
    setAgentThread((prev) =>
      prev.map((item) =>
        item.id === asstId
          ? {
              ...item,
              content,
              run,
              pending: false,
              liveSteps: run.steps,
              liveTokenUsage: run.token_usage,
              liveTrace:
                item.liveTrace && item.liveTrace.length > 0
                  ? item.liveTrace
                  : run.steps.map((step) => ({ kind: "step" as const, step })),
              liveLlmEvents: [],
              liveExecutionTrace:
                run.execution_trace ?? item.liveExecutionTrace ?? null,
            }
          : item,
      ),
    );
  }

  function patchExecutionTrace(asstId: string, trace: ExecutionTrace) {
    patchLive(asstId, { liveExecutionTrace: trace });
  }

  function appendTrace(asstId: string, span: LiveTraceSpan) {
    setAgentThread((prev) =>
      prev.map((item) => {
        if (item.id !== asstId) return item;
        return { ...item, liveTrace: [...(item.liveTrace ?? []), span] };
      }),
    );
  }

  function patchLlmInTrace(
    asstId: string,
    patch: Partial<LlmTraceEvent> & { status?: "running" | "done" },
  ) {
    setAgentThread((prev) =>
      prev.map((item) => {
        if (item.id !== asstId) return item;
        const liveTrace = (item.liveTrace ?? []).map((node) => {
          if (node.kind !== "llm" || node.event.status !== "running") return node;
          return {
            kind: "llm" as const,
            event: { ...node.event, ...patch, status: "done" as const },
          };
        });
        return { ...item, liveTrace };
      }),
    );
  }

  function patchLive(
    asstId: string,
    patch: Partial<AgentThreadItem>,
  ) {
    setAgentThread((prev) =>
      prev.map((item) => (item.id === asstId ? { ...item, ...patch } : item)),
    );
  }

  async function onSendAgent(text: string) {
    const userId = `agent-user-${Date.now()}`;
    const asstId = `agent-asst-${Date.now()}`;

    setAgentThread((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      {
        id: asstId,
        role: "assistant",
        content: "Trace live — LLM and tool spans appear as they run…",
        pending: true,
        run: null,
        goal: text,
      },
    ]);
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });

    try {
      const run = await api.startAgentRunStream(
        workspaceId,
        text,
        makeAgentStreamHandlers(
          {
            onTrace: (trace) => {
              patchExecutionTrace(asstId, trace);
            },
            onLlmStart: (event) => {
              appendTrace(asstId, { kind: "llm", event });
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  return {
                    ...item,
                    liveLlmEvents: [
                      ...(item.liveLlmEvents ?? []).filter((e) => e.status === "done"),
                      event,
                    ],
                  };
                }),
              );
            },
            onLlmEnd: (p) => {
              const patch = makeLlmEndPatch(p);
              patchLlmInTrace(asstId, patch);
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  const events = (item.liveLlmEvents ?? []).map((e) =>
                    e.status === "running"
                      ? { ...e, ...patch, status: "done" as const }
                      : e,
                  );
                  return {
                    ...item,
                    liveLlmEvents: events,
                    liveTokenUsage:
                      p.token_usage_so_far ?? item.liveTokenUsage ?? null,
                  };
                }),
              );
            },
            onStep: (step) => {
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  return {
                    ...item,
                    liveSteps: upsertSteps(item.liveSteps ?? [], step),
                    liveTrace: upsertTraceStep(item.liveTrace ?? [], step),
                  };
                }),
              );
              requestAnimationFrame(() => {
                bottomRef.current?.scrollIntoView({ behavior: "smooth" });
              });
            },
            onTokenUsage: (usage) => {
              patchLive(asstId, { liveTokenUsage: usage });
            },
          },
          (final) => {
            applyRunToThread(asstId, final);
            setAgentRunId(final.id);
            void queryClient.invalidateQueries({
              queryKey: ["agentRuns", workspaceId],
            });
            if (final.status === "waiting_approval") {
              if (isPresentationPending(final.pending_tool)) {
                success("Answer ready", "Choose whether to view it in the UI.");
              } else {
                success("Approval needed", "Review the write action below.");
              }
            } else if (final.status === "completed") {
              success("Agent finished");
            }
          },
        ),
        { maxSteps: 5 },
      );
      if (run) {
        applyRunToThread(asstId, run);
        setAgentRunId(run.id);
        void queryClient.invalidateQueries({
          queryKey: ["agentRuns", workspaceId],
        });
      }
      requestAnimationFrame(() => {
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      });
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Agent failed", msg);
      setAgentThread((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== asstId),
      );
      setInput(text);
    }
  }

  async function onApproveAgent(asstId: string, runId: string, approve: boolean) {
    if (approving) return;
    const threadItem = agentThread.find((item) => item.id === asstId);
    const presentationPending = isPresentationPending(threadItem?.run?.pending_tool);
    setApproving(true);
    setError(null);
    if (!presentationPending) {
      setAgentThread((prev) =>
        prev.map((item) =>
          item.id === asstId
            ? {
                ...item,
                pending: true,
                content: approve
                  ? "Approved — agent is continuing…"
                  : "Rejecting…",
              }
            : item,
        ),
      );
    }
    try {
      if (presentationPending) {
        if (!approve) {
          const run = await api.approveAgentRun(runId, false);
          applyRunToThread(asstId, run);
          void queryClient.invalidateQueries({ queryKey: ["agentRuns", workspaceId] });
          success("Keeping text answer");
          return;
        }
        const seedSteps = threadItem?.run?.steps ?? [];
        setAgentThread((prev) =>
          prev.map((item) =>
            item.id === asstId
              ? {
                  ...item,
                  pending: true,
                  content: "Building visual summary…",
                  liveSteps: seedSteps,
                  liveTrace: seedSteps.map((step) => ({
                    kind: "step" as const,
                    step,
                  })),
                }
              : item,
          ),
        );
        const run = await api.approveAgentRunStream(
          runId,
          true,
          makeAgentStreamHandlers(
            {
              onTrace: (trace) => {
                patchExecutionTrace(asstId, trace);
              },
              onLlmStart: (event) => {
                appendTrace(asstId, { kind: "llm", event });
                setAgentThread((prev) =>
                  prev.map((item) => {
                    if (item.id !== asstId) return item;
                    return {
                      ...item,
                      liveLlmEvents: [
                        ...(item.liveLlmEvents ?? []).filter((e) => e.status === "done"),
                        event,
                      ],
                    };
                  }),
                );
              },
              onLlmEnd: (p) => {
                const patch = makeLlmEndPatch(p);
                patchLlmInTrace(asstId, patch);
                setAgentThread((prev) =>
                  prev.map((item) => {
                    if (item.id !== asstId) return item;
                    return {
                      ...item,
                      liveTokenUsage:
                        p.token_usage_so_far ?? item.liveTokenUsage ?? null,
                      liveLlmEvents: (item.liveLlmEvents ?? []).map((e) =>
                        e.status === "running"
                          ? { ...e, ...patch, status: "done" as const }
                          : e,
                      ),
                    };
                  }),
                );
              },
              onStep: (step) => {
                setAgentThread((prev) =>
                  prev.map((item) => {
                    if (item.id !== asstId) return item;
                    return {
                      ...item,
                      liveSteps: upsertSteps(item.liveSteps ?? [], step),
                      liveTrace: upsertTraceStep(item.liveTrace ?? [], step),
                    };
                  }),
                );
              },
              onTokenUsage: (usage) => {
                patchLive(asstId, { liveTokenUsage: usage });
              },
              onStatus: (p) => {
                if (p.presentation_spec) {
                  setAgentThread((prev) =>
                    prev.map((item) => {
                      if (item.id !== asstId || !item.run) return item;
                      return {
                        ...item,
                        run: {
                          ...item.run,
                          presentation_spec: p.presentation_spec ?? null,
                        },
                      };
                    }),
                  );
                }
              },
            },
            (final) => {
              applyRunToThread(asstId, final);
              setAgentRunId(final.id);
              void queryClient.invalidateQueries({
                queryKey: ["agentRuns", workspaceId],
              });
              success("Visual summary ready", "Scroll down to view it.");
            },
            false,
          ),
        );
        if (run) {
          applyRunToThread(asstId, run);
          setAgentRunId(run.id);
          void queryClient.invalidateQueries({ queryKey: ["agentRuns", workspaceId] });
        }
        return;
      }
      if (!approve) {
        const run = await api.approveAgentRun(runId, false);
        applyRunToThread(asstId, run);
        success("Action rejected");
        return;
      }
      const run = await api.approveAgentRunStream(
        runId,
        true,
        makeAgentStreamHandlers(
          {
            onTrace: (trace) => {
              patchExecutionTrace(asstId, trace);
            },
            onLlmStart: (event) => {
              appendTrace(asstId, { kind: "llm", event });
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  return {
                    ...item,
                    liveLlmEvents: [
                      ...(item.liveLlmEvents ?? []).filter((e) => e.status === "done"),
                      event,
                    ],
                  };
                }),
              );
            },
            onLlmEnd: (p) => {
              const patch = makeLlmEndPatch(p);
              patchLlmInTrace(asstId, patch);
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  return {
                    ...item,
                    liveTokenUsage:
                      p.token_usage_so_far ?? item.liveTokenUsage ?? null,
                    liveLlmEvents: (item.liveLlmEvents ?? []).map((e) =>
                      e.status === "running"
                        ? { ...e, ...patch, status: "done" as const }
                        : e,
                    ),
                  };
                }),
              );
            },
            onStep: (step) => {
              setAgentThread((prev) =>
                prev.map((item) => {
                  if (item.id !== asstId) return item;
                  return {
                    ...item,
                    liveSteps: upsertSteps(item.liveSteps ?? item.run?.steps ?? [], step),
                    liveTrace: upsertTraceStep(item.liveTrace ?? [], step),
                  };
                }),
              );
            },
            onTokenUsage: (usage) => {
              patchLive(asstId, { liveTokenUsage: usage });
            },
          },
          (final) => {
            applyRunToThread(asstId, final);
            setAgentRunId(final.id);
            void queryClient.invalidateQueries({ queryKey: ["agentRuns", workspaceId] });
            success("Action approved — agent continued");
          },
          false,
        ),
      );
      if (run) {
        applyRunToThread(asstId, run);
        setAgentRunId(run.id);
        void queryClient.invalidateQueries({ queryKey: ["agentRuns", workspaceId] });
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Approval failed", msg);
      setAgentThread((prev) =>
        prev.map((item) =>
          item.id === asstId ? { ...item, pending: false } : item,
        ),
      );
    } finally {
      setApproving(false);
    }
  }

  async function onSaveLearningNote(title: string, body: string) {
    if (!workspaceId || savingNote) return;
    setSavingNote(true);
    setError(null);
    const userId = `agent-user-note-${Date.now()}`;
    const asstId = `agent-asst-note-${Date.now()}`;
    const goalText =
      `Create a note titled ${JSON.stringify(title)} with body:\n${body}`;
    setModePersist("agent");
    setAgentThread((prev) => [
      ...prev,
      { id: userId, role: "user", content: `Save visual summary as note: ${title}` },
      {
        id: asstId,
        role: "assistant",
        content: "Preparing note (approval required)…",
        pending: true,
        run: null,
        goal: goalText,
      },
    ]);
    requestAnimationFrame(() => {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    });
    try {
      const run = await api.startAgentRun(workspaceId, goalText, { maxSteps: 5 });
      applyRunToThread(asstId, run);
      setAgentRunId(run.id);
      void queryClient.invalidateQueries({ queryKey: ["agentRuns", workspaceId] });
      if (run.status === "waiting_approval") {
        success("Approve the note", "Review create_note below, then Approve.");
      } else if (run.status === "completed") {
        success("Note flow finished");
      }
    } catch (err) {
      const msg = formatError(err);
      setError(msg);
      toastError("Could not start save-as-note", msg);
      setAgentThread((prev) =>
        prev.filter((m) => m.id !== userId && m.id !== asstId),
      );
    } finally {
      setSavingNote(false);
    }
  }

  return {
    agentThread,
    setAgentThread,
    approving,
    savingNote,
    onSendAgent,
    onApproveAgent,
    onSaveLearningNote,
    threadFromRun,
  };
}
