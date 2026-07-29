import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Bot,
  ChevronDown,
  ChevronRight,
  Globe,
  Link2,
  Loader2,
  RefreshCw,
  Sparkles,
  Wrench,
} from "lucide-react";
import {
  api,
  type WorkspaceActivity,
  type WorkspaceActivityCall,
  type WorkspaceActivityTopic,
} from "@/api";
import { Button } from "@/components/ui/button";
import { cn, formatError } from "@/lib/utils";

type DetailTab = "topics" | "activity";
type CallFilter = "all" | "llm" | "tool" | "web_search" | "fetch_url";

function callTypeIcon(t: string) {
  if (t === "web_search") return Globe;
  if (t === "fetch_url") return Link2;
  if (t === "tool") return Wrench;
  if (t === "llm") return Sparkles;
  return Bot;
}

function formatWhen(iso?: string | null) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function prettyJson(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function CallCard({ call }: { call: WorkspaceActivityCall }) {
  const [open, setOpen] = useState(false);
  const Icon = callTypeIcon(call.call_type);
  const title = call.tool_name || call.kind || call.call_type || "call";
  const hasBody =
    !!call.prompt ||
    !!call.completion ||
    call.tool_input != null ||
    call.tool_output != null;

  return (
    <div className="rounded-[8px] border border-hairline bg-canvas">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left"
      >
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-ink">{title}</span>
            <span className="rounded-full bg-canvas-soft px-1.5 py-px text-[10px] uppercase tracking-wide text-mute">
              {call.call_type}
            </span>
            {call.model ? (
              <span className="font-mono text-[10px] text-mute">{call.model}</span>
            ) : null}
          </div>
          <div className="mt-0.5 text-[10px] text-mute">
            {formatWhen(call.created_at)}
            {call.total_tokens
              ? ` · ${call.total_tokens} tokens`
              : call.prompt_tokens || call.completion_tokens
                ? ` · ${call.prompt_tokens ?? 0}p / ${call.completion_tokens ?? 0}c`
                : ""}
          </div>
        </div>
        {hasBody ? (
          open ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0 text-mute" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-mute" />
          )
        ) : null}
      </button>
      {open && hasBody ? (
        <div className="space-y-2 border-t border-hairline px-3 py-2.5">
          {call.prompt ? (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Input
              </div>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-[6px] bg-canvas-soft p-2 font-mono text-[10px] leading-relaxed text-body">
                {call.prompt}
              </pre>
            </div>
          ) : null}
          {call.completion ? (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Output
              </div>
              <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded-[6px] bg-canvas-soft p-2 font-mono text-[10px] leading-relaxed text-body">
                {call.completion}
              </pre>
            </div>
          ) : null}
          {call.tool_input != null ? (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Tool input
              </div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-[6px] bg-canvas-soft p-2 font-mono text-[10px] leading-relaxed text-body">
                {prettyJson(call.tool_input)}
              </pre>
            </div>
          ) : null}
          {call.tool_output != null ? (
            <div>
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                Tool output
              </div>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-[6px] bg-canvas-soft p-2 font-mono text-[10px] leading-relaxed text-body">
                {prettyJson(call.tool_output)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function TopicsTree({ topics }: { topics: WorkspaceActivityTopic[] }) {
  const idSet = useMemo(() => new Set(topics.map((t) => t.id)), [topics]);
  const roots = useMemo(
    () => topics.filter((t) => !t.parent_id || !idSet.has(t.parent_id)),
    [topics, idSet],
  );
  const childrenOf = useMemo(() => {
    const m = new Map<string, WorkspaceActivityTopic[]>();
    for (const t of topics) {
      if (!t.parent_id || !idSet.has(t.parent_id)) continue;
      const list = m.get(t.parent_id) ?? [];
      list.push(t);
      m.set(t.parent_id, list);
    }
    return m;
  }, [topics, idSet]);

  if (!topics.length) {
    return <p className="text-xs text-mute">No topics yet.</p>;
  }

  const renderTopic = (t: WorkspaceActivityTopic, depth = 0): ReactNode => {
    const kids = childrenOf.get(t.id) ?? [];
    return (
      <li key={t.id} className={cn(depth > 0 && "ml-3 border-l border-hairline pl-2")}>
        <div className="rounded-[6px] px-2 py-1.5 hover:bg-canvas-soft">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs font-semibold text-ink">{t.title}</span>
            {t.status === "archived" ? (
              <span className="text-[10px] text-amber-700">archived</span>
            ) : null}
            {t.has_lesson ? (
              <span className="text-[10px] text-emerald-700">lesson</span>
            ) : null}
          </div>
        </div>
        {kids.length > 0 ? (
          <ul className="mt-0.5 space-y-0.5">
            {kids.map((c) => renderTopic(c, depth + 1))}
          </ul>
        ) : null}
      </li>
    );
  };

  return <ul className="space-y-0.5">{roots.map((t) => renderTopic(t))}</ul>;
}

export function WorkspaceActivityPanel({
  workspaceId,
}: {
  workspaceId: string;
  workspaceName: string;
}) {
  const [tab, setTab] = useState<DetailTab>("topics");
  const [filter, setFilter] = useState<CallFilter>("all");
  const [data, setData] = useState<WorkspaceActivity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.workspaceActivity(workspaceId, 100);
      setData(res);
    } catch (e) {
      setData(null);
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void load();
  }, [load]);

  const filteredCalls = useMemo(() => {
    const calls = data?.calls ?? [];
    if (filter === "all") return calls;
    return calls.filter((c) => c.call_type === filter);
  }, [data?.calls, filter]);

  const summary = data?.summary ?? {};

  return (
    <div className="rounded-[10px] border border-hairline bg-canvas">
      <div className="flex items-center gap-2 border-b border-hairline px-2 py-1.5">
        <div className="flex min-w-0 flex-1 gap-1">
          {(
            [
              ["topics", "Topics"],
              ["activity", "Activity"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cn(
                "rounded-[6px] px-2.5 py-1 text-xs font-medium",
                tab === id
                  ? "bg-ink text-[var(--canvas)]"
                  : "text-mute hover:bg-canvas-soft hover:text-ink",
              )}
            >
              {label}
              {id === "topics" && summary.topics != null
                ? ` (${summary.topics})`
                : null}
              {id === "activity" && summary.calls != null
                ? ` (${summary.calls})`
                : null}
            </button>
          ))}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={() => void load()}
          disabled={loading}
          aria-label="Refresh"
        >
          <RefreshCw
            className={cn("h-3.5 w-3.5", loading && "animate-spin")}
            strokeWidth={1.5}
          />
        </Button>
      </div>

      <div className="max-h-[28rem] overflow-y-auto p-3">
        {loading && !data ? (
          <div className="flex items-center gap-2 text-xs text-mute">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Loading…
          </div>
        ) : null}
        {error ? <p className="text-xs text-red-600">{error}</p> : null}

        {tab === "topics" && data ? <TopicsTree topics={data.topics} /> : null}

        {tab === "activity" && data ? (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  ["all", "All"],
                  ["llm", "LLM"],
                  ["tool", "Tools"],
                  ["web_search", "Web"],
                  ["fetch_url", "Fetch"],
                ] as const
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setFilter(id)}
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[10px]",
                    filter === id
                      ? "border-ink bg-ink text-[var(--canvas)]"
                      : "border-hairline text-mute hover:text-ink",
                  )}
                >
                  {label}
                  {id !== "all" && summary[id] != null ? ` ${summary[id]}` : ""}
                </button>
              ))}
            </div>

            {data.agent_runs.length > 0 ? (
              <div>
                <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">
                  Runs
                </div>
                <ul className="mb-3 space-y-1">
                  {data.agent_runs.slice(0, 8).map((r) => (
                    <li
                      key={r.id}
                      className="rounded-[6px] border border-hairline bg-canvas-soft/40 px-2 py-1.5 text-[11px]"
                    >
                      <div className="font-medium text-ink line-clamp-1">
                        {r.goal}
                      </div>
                      <div className="text-[10px] text-mute">
                        {r.status} · {r.step_count} steps
                        {r.token_usage ? ` · ${r.token_usage} tok` : ""} ·{" "}
                        {formatWhen(r.created_at)}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <div className="space-y-1.5">
              {filteredCalls.map((c) => (
                <CallCard key={`${c.source}-${c.id}`} call={c} />
              ))}
              {!filteredCalls.length ? (
                <p className="text-xs text-mute">No activity yet.</p>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
