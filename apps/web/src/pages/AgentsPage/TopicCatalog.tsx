import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
} from "lucide-react";
import {
  api,
  ApiError,
  type CurriculumIntakeForm,
  type CurriculumIntakeQuestion,
  type CurriculumTopic,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Props = {
  workspaceId: string;
  disabled?: boolean;
  onStartTopic: (topicId: string, composedGoal: string) => void;
};

export function TopicCatalog({ workspaceId, disabled, onStartTopic }: Props) {
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [domain, setDomain] = useState("");
  const [topics, setTopics] = useState<CurriculumTopic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [customTitle, setCustomTitle] = useState("");
  const [adding, setAdding] = useState(false);
  const [customError, setCustomError] = useState<string | null>(null);

  const [selected, setSelected] = useState<CurriculumTopic | null>(null);
  const [intake, setIntake] = useState<CurriculumIntakeForm | null>(null);
  const [answers, setAnswers] = useState<Record<string, string[]>>({});
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const load = useCallback(
    async (refresh = false) => {
      if (!workspaceId) return;
      setError(null);
      if (refresh) setRefreshing(true);
      else setLoading(true);
      try {
        const data = refresh
          ? await api.refreshCurriculum(workspaceId)
          : await api.getCurriculum(workspaceId);
        setEnabled(data.enabled);
        setDomain(data.domain || "");
        setTopics(data.topics || []);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load topics");
        setEnabled(false);
        setTopics([]);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [workspaceId],
  );

  useEffect(() => {
    void load(false);
    setSelected(null);
    setIntake(null);
    setAnswers({});
    setCustomError(null);
  }, [load]);

  async function onSelectTopic(topic: CurriculumTopic) {
    if (disabled) return;
    setSelected(topic);
    setIntakeLoading(true);
    setError(null);
    try {
      const form = await api.getTopicIntake(workspaceId, topic.id);
      setIntake(form);
      const saved = form.saved_answers || topic.preferences || {};
      setAnswers(
        Object.fromEntries(
          Object.entries(saved).map(([k, v]) => [
            k,
            Array.isArray(v) ? v : [String(v)],
          ]),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load questions");
      setSelected(null);
    } finally {
      setIntakeLoading(false);
    }
  }

  function toggleOption(q: CurriculumIntakeQuestion, optionId: string) {
    setAnswers((prev) => {
      const cur = prev[q.id] || [];
      if (q.allow_multiple) {
        const next = cur.includes(optionId)
          ? cur.filter((x) => x !== optionId)
          : [...cur, optionId];
        return { ...prev, [q.id]: next };
      }
      return { ...prev, [q.id]: [optionId] };
    });
  }

  async function onSubmitIntake() {
    if (!selected || !intake) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: Record<string, string | string[]> = {};
      for (const [k, v] of Object.entries(answers)) {
        payload[k] = v;
      }
      const result = await api.submitTopicIntake(
        workspaceId,
        selected.id,
        payload,
      );
      onStartTopic(selected.id, result.composed_goal);
      setSelected(null);
      setIntake(null);
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Could not start from topic",
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function onAddCustom() {
    const title = customTitle.trim();
    if (!title) return;
    setAdding(true);
    setCustomError(null);
    try {
      const topic = await api.addCurriculumTopic(workspaceId, title);
      setCustomTitle("");
      setTopics((prev) => {
        if (prev.some((t) => t.id === topic.id)) {
          return prev.map((t) => (t.id === topic.id ? topic : t));
        }
        return [topic, ...prev];
      });
      await onSelectTopic(topic);
    } catch (e) {
      setCustomError(
        e instanceof ApiError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Could not add topic",
      );
    } finally {
      setAdding(false);
    }
  }

  if (loading) {
    return (
      <div className="mb-6 flex items-center gap-2 rounded-vercel-md border border-hairline bg-canvas px-4 py-6 text-xs text-mute">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading topics…
      </div>
    );
  }

  if (!enabled) return null;

  return (
    <div className="mb-6 rounded-vercel-md border border-hairline bg-canvas p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <BookOpen className="h-4 w-4 text-ink" strokeWidth={1.5} />
            <h2 className="text-sm font-semibold text-ink">Topics to learn</h2>
          </div>
          <p className="mt-0.5 text-[11px] text-mute">
            {domain
              ? `Pick a topic for ${domain}, answer a few checkboxes, then run.`
              : "Pick a topic, answer a few checkboxes, then run the agent."}
          </p>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-7 gap-1 text-[11px]"
          disabled={disabled || refreshing}
          onClick={() => void load(true)}
        >
          {refreshing ? (
            <Loader2 className="h-3 w-3 animate-spin" />
          ) : (
            <RefreshCw className="h-3 w-3" strokeWidth={1.5} />
          )}
          Refresh
        </Button>
      </div>

      {error && (
        <p className="mt-2 rounded-[6px] border border-danger-border bg-danger-soft px-2 py-1.5 text-[11px] text-danger-text">
          {error}
        </p>
      )}

      {!selected && (
        <>
          {/* Single horizontal row — scroll when topics overflow. */}
          <div className="mt-3 -mx-1 overflow-x-auto px-1 pb-1 [scrollbar-width:thin]">
            <div className="flex w-max min-w-full gap-2">
              {topics.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  disabled={disabled}
                  onClick={() => void onSelectTopic(t)}
                  className={cn(
                    "w-[13.5rem] shrink-0 rounded-[10px] border border-hairline bg-canvas-soft px-3 py-2.5 text-left transition-colors",
                    "hover:border-ink/25 hover:bg-canvas-soft-2",
                    disabled && "opacity-60",
                  )}
                >
                  <div className="flex items-center gap-1.5">
                    <Sparkles
                      className="h-3 w-3 shrink-0 text-mute"
                      strokeWidth={1.5}
                    />
                    <span className="truncate text-xs font-semibold text-ink">
                      {t.title}
                    </span>
                    {t.source === "custom" && (
                      <span className="rounded-full border border-hairline px-1.5 text-[9px] uppercase text-mute">
                        custom
                      </span>
                    )}
                  </div>
                  {t.summary && (
                    <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-mute">
                      {t.summary}
                    </p>
                  )}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-3 flex max-w-xl gap-1.5">
            <Input
              value={customTitle}
              onChange={(e) => {
                setCustomTitle(e.target.value);
                setCustomError(null);
              }}
              disabled={disabled || adding}
              placeholder="Custom topic…"
              className="h-8 text-xs"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void onAddCustom();
                }
              }}
            />
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-8 shrink-0 gap-1"
              disabled={disabled || adding || !customTitle.trim()}
              onClick={() => void onAddCustom()}
            >
              {adding ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
              )}
              Add
            </Button>
          </div>
          {customError && (
            <p className="mt-1.5 text-[11px] text-warning-text">{customError}</p>
          )}
        </>
      )}

      {selected && (
        <div className="mt-3 space-y-3 rounded-[10px] border border-hairline bg-canvas-soft p-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-xs font-semibold text-ink">
                {intake?.title || selected.title}
              </p>
              <p className="text-[11px] text-mute">
                {intake?.subtitle || "Select options below"}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 text-[11px]"
              onClick={() => {
                setSelected(null);
                setIntake(null);
              }}
            >
              Back
            </Button>
          </div>

          {intakeLoading && (
            <div className="flex items-center gap-2 text-[11px] text-mute">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading questions…
            </div>
          )}

          {intake &&
            intake.questions.map((q) => (
              <fieldset key={q.id} className="space-y-1.5">
                <legend className="text-[11px] font-medium text-ink">
                  {q.prompt}
                  {q.required ? (
                    <span className="text-danger-text"> *</span>
                  ) : null}
                </legend>
                <div className="flex flex-wrap gap-1.5">
                  {(q.options || []).map((opt) => {
                    const active = (answers[q.id] || []).includes(opt.id);
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={disabled || submitting}
                        onClick={() => toggleOption(q, opt.id)}
                        className={cn(
                          "rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors",
                          active
                            ? "border-ink bg-ink text-[var(--canvas)]"
                            : "border-hairline bg-canvas text-body hover:bg-canvas-soft-2",
                        )}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </fieldset>
            ))}

          <Button
            type="button"
            className="w-full sm:w-auto"
            disabled={disabled || submitting || intakeLoading || !intake}
            onClick={() => void onSubmitIntake()}
          >
            {submitting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Sparkles className="h-4 w-4" strokeWidth={1.5} />
            )}
            {submitting ? "Starting…" : "Start study run"}
          </Button>
        </div>
      )}
    </div>
  );
}
