import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  Bot,
  Check,
  Loader2,
  Play,
  RefreshCw,
  StickyNote,
  Trash2,
  X,
} from "lucide-react";
import {
  api,
  getToken,
  type AgentRun,
  type AgentStep,
  type Note,
  type Workspace,
} from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn, formatError } from "@/lib/utils";

const EXAMPLE_GOALS = [
  "List my documents and say which ones are ready for chat.",
  "Search documents for mesh gradient colors and summarize.",
  "Create a note titled Demo Approval with body hello from HITL agent.",
];

function statusVariant(
  status: string,
): "success" | "warning" | "danger" | "secondary" | "outline" {
  switch (status) {
    case "completed":
      return "success";
    case "running":
    case "waiting_approval":
      return "warning";
    case "failed":
    case "cancelled":
      return "danger";
    default:
      return "secondary";
  }
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function pretty(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function StepCard({ step }: { step: AgentStep }) {
  return (
    <div className="rounded-[6px] border border-hairline bg-canvas px-3 py-2.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-ink">#{step.step_index}</span>
        <Badge variant="outline">{step.type}</Badge>
        {step.tool_name && <Badge variant="secondary">{step.tool_name}</Badge>}
      </div>
      {step.input != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">Input</div>
          <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-body">
            {pretty(step.input)}
          </pre>
        </div>
      )}
      {step.output != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">
            Output
          </div>
          <pre className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-body">
            {pretty(step.output)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function AgentsPage() {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [selected, setSelected] = useState<AgentRun | null>(null);
  const [goal, setGoal] = useState(EXAMPLE_GOALS[0]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [approving, setApproving] = useState(false);

  const loadNotes = useCallback(async (ws: string) => {
    if (!ws) return;
    setNotes(await api.notes(ws));
  }, []);

  const loadRuns = useCallback(async (ws: string, preferId?: string) => {
    if (!ws) return;
    const list = await api.agentRuns(ws);
    setRuns(list);
    const next =
      preferId && list.some((r) => r.id === preferId)
        ? preferId
        : list[0]?.id || "";
    setSelectedId(next);
    if (next) {
      const detail =
        list.find((r) => r.id === next) ?? (await api.agentRun(next));
      setSelected(detail);
    } else {
      setSelected(null);
    }
  }, []);

  const refreshWorkspace = useCallback(
    async (ws: string, preferRunId?: string) => {
      await Promise.all([loadRuns(ws, preferRunId), loadNotes(ws)]);
    },
    [loadNotes, loadRuns],
  );

  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const list = await api.workspaces();
        if (cancelled) return;
        setWorkspaces(list);
        const first = list[0]?.id ?? "";
        setWorkspaceId((prev) => prev || first);
      } catch (err) {
        if (!cancelled) setError(formatError(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!workspaceId) return;
    refreshWorkspace(workspaceId).catch((err) => setError(formatError(err)));
  }, [workspaceId, refreshWorkspace]);

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  async function onSelect(id: string) {
    setSelectedId(id);
    setError(null);
    try {
      setSelected(await api.agentRun(id));
    } catch (err) {
      setError(formatError(err));
    }
  }

  async function onRun(e: FormEvent) {
    e.preventDefault();
    if (!workspaceId || !goal.trim() || running) return;
    setRunning(true);
    setError(null);
    try {
      const run = await api.startAgentRun(workspaceId, goal.trim(), 5);
      await refreshWorkspace(workspaceId, run.id);
      setSelected(run);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setRunning(false);
    }
  }

  async function onApprove(approve: boolean) {
    if (!selected || approving) return;
    setApproving(true);
    setError(null);
    try {
      const run = await api.approveAgentRun(selected.id, approve);
      await refreshWorkspace(workspaceId, run.id);
      setSelected(run);
    } catch (err) {
      setError(formatError(err));
    } finally {
      setApproving(false);
    }
  }

  async function onDeleteNote(id: string) {
    setError(null);
    try {
      await api.deleteNote(id);
      await loadNotes(workspaceId);
    } catch (err) {
      setError(formatError(err));
    }
  }

  const steps = [...(selected?.steps ?? [])].sort(
    (a, b) => a.step_index - b.step_index,
  );

  return (
    <div className="flex h-full flex-col overflow-hidden bg-canvas-soft">
      <AppHeader onLogout={() => navigate("/login", { replace: true })} />

      <div className="flex min-h-0 flex-1">
        <aside className="flex w-80 shrink-0 flex-col border-r border-hairline bg-canvas">
          <div className="shrink-0 border-b border-hairline p-4">
            <div className="flex items-center gap-2">
              <Bot className="h-4 w-4 text-ink" strokeWidth={1.5} />
              <h2 className="text-body-sm font-semibold text-ink">Agents</h2>
            </div>
            <p className="mt-0.5 text-xs text-mute">
              Tools + HITL for write actions
            </p>

            {workspaces.length > 0 && (
              <label className="mt-3 block">
                <span className="mb-1 block text-xs text-mute">Workspace</span>
                <select
                  value={workspaceId}
                  onChange={(e) => setWorkspaceId(e.target.value)}
                  className="h-9 w-full rounded-[6px] border border-hairline bg-canvas px-2 text-sm text-ink"
                >
                  {workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="mt-3 w-full"
              disabled={loading || !workspaceId}
              onClick={() =>
                refreshWorkspace(workspaceId, selectedId).catch((err) =>
                  setError(formatError(err)),
                )
              }
            >
              <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
              Refresh
            </Button>
          </div>

          <div className="document-scroll min-h-0 flex-1 overflow-y-auto p-2">
            <div className="mb-1 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
              Runs ({runs.length})
            </div>
            {loading ? (
              <p className="px-2 py-3 text-xs text-mute">Loading…</p>
            ) : runs.length === 0 ? (
              <p className="px-2 py-3 text-xs text-mute">
                No runs yet. Start one on the right.
              </p>
            ) : (
              <ul className="space-y-1">
                {runs.map((r) => (
                  <li key={r.id}>
                    <button
                      type="button"
                      onClick={() => void onSelect(r.id)}
                      className={cn(
                        "w-full rounded-[6px] border px-2 py-2 text-left transition-colors",
                        r.id === selectedId
                          ? "border-hairline bg-canvas-soft-2"
                          : "border-transparent hover:bg-canvas-soft-2",
                      )}
                    >
                      <div className="line-clamp-2 text-sm font-medium text-ink">
                        {r.goal}
                      </div>
                      <div className="mt-1 flex items-center gap-2">
                        <Badge variant={statusVariant(r.status)}>
                          {r.status}
                        </Badge>
                        <span className="text-[11px] text-mute">
                          {formatWhen(r.created_at)}
                        </span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <div className="mb-1 mt-4 px-2 py-1 text-[11px] font-medium uppercase tracking-wide text-mute">
              Notes ({notes.length})
            </div>
            {notes.length === 0 ? (
              <p className="px-2 py-2 text-xs text-mute">
                No notes yet. Approve a create_note run to add one.
              </p>
            ) : (
              <ul className="space-y-1">
                {notes.map((n) => (
                  <li
                    key={n.id}
                    className="group rounded-[6px] border border-hairline bg-canvas px-2 py-2"
                  >
                    <div className="flex items-start gap-2">
                      <StickyNote
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute"
                        strokeWidth={1.5}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium text-ink">
                          {n.title}
                        </div>
                        <div className="mt-0.5 line-clamp-2 text-xs text-mute">
                          {n.body || "—"}
                        </div>
                        <div className="mt-1 text-[11px] text-mute">
                          {formatWhen(n.created_at)}
                        </div>
                      </div>
                      <button
                        type="button"
                        title="Delete note"
                        className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                        onClick={() => void onDeleteNote(n.id)}
                      >
                        <Trash2 className="h-3.5 w-3.5" strokeWidth={1.5} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </aside>

        <main className="document-scroll min-h-0 min-w-0 flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-2xl">
            {error && (
              <Alert variant="danger" className="mb-4">
                {error}
              </Alert>
            )}

            <form
              onSubmit={onRun}
              className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4"
            >
              <h1 className="text-sm font-semibold text-ink">Start agent run</h1>
              <p className="mt-1 text-xs text-mute">
                Read tools run immediately.{" "}
                <strong className="text-ink">create_note</strong> waits for
                Approve / Reject.
              </p>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {EXAMPLE_GOALS.map((g) => (
                  <button
                    key={g}
                    type="button"
                    disabled={running}
                    onClick={() => setGoal(g)}
                    className={cn(
                      "rounded-full border px-2.5 py-1 text-left text-[11px] transition-colors",
                      goal === g
                        ? "border-ink bg-ink text-[var(--canvas)]"
                        : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
                    )}
                  >
                    {g.length > 48 ? `${g.slice(0, 48)}…` : g}
                  </button>
                ))}
              </div>

              <label className="mt-3 block">
                <span className="mb-1 block text-xs text-mute">Goal</span>
                <Input
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  disabled={running || !workspaceId}
                  placeholder="What should the agent do?"
                />
              </label>
              <Button
                type="submit"
                className="mt-3 rounded-[6px]"
                disabled={running || !workspaceId || !goal.trim()}
              >
                {running ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Play className="h-4 w-4" strokeWidth={1.5} />
                )}
                {running ? "Running (may take ~30s)…" : "Run agent"}
              </Button>
            </form>

            {!selected ? (
              <div className="py-12 text-center text-sm text-mute">
                Select a run or start a new one.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={statusVariant(selected.status)}>
                      {selected.status}
                    </Badge>
                    <span className="text-xs text-mute">
                      {formatWhen(selected.created_at)}
                    </span>
                    {selected.token_usage != null && (
                      <span className="text-xs text-mute">
                        ~{selected.token_usage} tokens (approx)
                      </span>
                    )}
                  </div>
                  <div className="mt-2 text-sm font-medium text-ink">
                    {selected.goal}
                  </div>
                  {selected.error && (
                    <Alert variant="danger" className="mt-3">
                      {selected.error}
                    </Alert>
                  )}

                  {selected.status === "waiting_approval" &&
                    selected.pending_tool && (
                      <div className="mt-4 rounded-[6px] border border-amber-200 bg-[#fffbeb] p-3">
                        <div className="text-sm font-semibold text-ink">
                          Approval required
                        </div>
                        <p className="mt-1 text-xs text-body">
                          Write tool{" "}
                          <code className="rounded bg-canvas px-1">
                            {selected.pending_tool.name}
                          </code>
                          . Review args, then approve or reject.
                        </p>
                        <pre className="mt-2 max-h-40 overflow-auto rounded border border-hairline bg-canvas p-2 text-xs text-body">
                          {pretty(selected.pending_tool.args ?? {})}
                        </pre>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <Button
                            type="button"
                            size="sm"
                            className="rounded-[6px]"
                            disabled={approving}
                            onClick={() => void onApprove(true)}
                          >
                            {approving ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            ) : (
                              <Check className="h-3.5 w-3.5" strokeWidth={1.5} />
                            )}
                            Approve
                          </Button>
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            disabled={approving}
                            onClick={() => void onApprove(false)}
                          >
                            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
                            Reject
                          </Button>
                        </div>
                      </div>
                    )}

                  {selected.final_answer && (
                    <div className="mt-3">
                      <div className="text-[11px] font-medium uppercase text-mute">
                        {selected.status === "waiting_approval"
                          ? "Status message"
                          : "Final answer"}
                      </div>
                      <div className="mt-1 whitespace-pre-wrap text-body-sm text-body">
                        {selected.final_answer}
                      </div>
                    </div>
                  )}
                </div>

                <div>
                  <h2 className="mb-2 text-sm font-semibold text-ink">
                    Step timeline ({steps.length})
                  </h2>
                  {steps.length === 0 ? (
                    <p className="text-sm text-mute">No steps recorded.</p>
                  ) : (
                    <div className="space-y-2">
                      {steps.map((s) => (
                        <StepCard key={s.id} step={s} />
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
