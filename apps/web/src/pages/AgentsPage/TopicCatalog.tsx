import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  Plus,
  RefreshCw,
  Sparkles,
  X,
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
  /** Accordion: which question ids are expanded. */
  const [openQuestions, setOpenQuestions] = useState<Set<string>>(new Set());

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
    setOpenQuestions(new Set());
  }, [load]);

  async function onSelectTopic(topic: CurriculumTopic) {
    if (disabled) return;
    // Selecting the same topic again is a no-op (card stays disabled/selected).
    if (selected?.id === topic.id) return;
    setSelected(topic);
    setIntakeLoading(true);
    setError(null);
    setIntake(null);
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
      // Open first question (and required ones with no answer yet) by default.
      const open = new Set<string>();
      const qs = form.questions || [];
      if (qs[0]?.id) open.add(qs[0].id);
      for (const q of qs) {
        if (q.required && !(saved[q.id]?.length)) open.add(q.id);
      }
      setOpenQuestions(open);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load questions");
      setSelected(null);
    } finally {
      setIntakeLoading(false);
    }
  }

  function clearSelection() {
    setSelected(null);
    setIntake(null);
    setAnswers({});
    setOpenQuestions(new Set());
  }

  function toggleAccordion(qid: string) {
    setOpenQuestions((prev) => {
      const next = new Set(prev);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
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

  function answerSummary(q: CurriculumIntakeQuestion): string {
    const ids = answers[q.id] || [];
    if (!ids.length) return "Not set";
    const labels = (q.options || [])
      .filter((o) => ids.includes(o.id))
      .map((o) => o.label);
    return labels.join(", ") || ids.join(", ");
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
      // Keep selection (disabled card) so context stays visible after start.
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
              ? `Pick a topic for ${domain}, then set options below.`
              : "Pick a topic, then set options in the accordion below."}
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

      {/* Topic cards always stay visible in one horizontal row. */}
      <div className="mt-3 -mx-1 overflow-x-auto px-1 pb-1 [scrollbar-width:thin]">
        <div className="flex w-max min-w-full gap-2">
          {topics.map((t) => {
            const isSelected = selected?.id === t.id;
            const cardDisabled = disabled || isSelected;
            return (
              <button
                key={t.id}
                type="button"
                disabled={cardDisabled}
                aria-pressed={isSelected}
                onClick={() => void onSelectTopic(t)}
                className={cn(
                  "w-[13.5rem] shrink-0 rounded-[10px] border px-3 py-2.5 text-left transition-colors",
                  isSelected
                    ? "cursor-not-allowed border-ink bg-ink/5 ring-1 ring-ink/15"
                    : "border-hairline bg-canvas-soft hover:border-ink/25 hover:bg-canvas-soft-2",
                  disabled && !isSelected && "opacity-60",
                  isSelected && disabled && "opacity-80",
                )}
              >
                <div className="flex items-center gap-1.5">
                  {isSelected ? (
                    <Check
                      className="h-3 w-3 shrink-0 text-ink"
                      strokeWidth={2}
                    />
                  ) : (
                    <Sparkles
                      className="h-3 w-3 shrink-0 text-mute"
                      strokeWidth={1.5}
                    />
                  )}
                  <span className="truncate text-xs font-semibold text-ink">
                    {t.title}
                  </span>
                  {isSelected && (
                    <span className="ml-auto shrink-0 rounded-full border border-ink/20 bg-canvas px-1.5 text-[9px] font-bold uppercase text-ink">
                      Selected
                    </span>
                  )}
                  {!isSelected && t.source === "custom" && (
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
            );
          })}
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

      {/* Intake accordion — stays open under the topic row. */}
      {selected && (
        <div className="mt-4 rounded-[10px] border border-hairline bg-canvas-soft">
          <div className="flex items-center justify-between gap-2 border-b border-hairline/70 px-3 py-2.5">
            <div className="min-w-0">
              <p className="truncate text-xs font-semibold text-ink">
                {intake?.title || `Set up: ${selected.title}`}
              </p>
              <p className="text-[11px] text-mute">
                {intake?.subtitle ||
                  "Expand each question, pick options, then start."}
              </p>
            </div>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              className="h-7 shrink-0 gap-1 text-[11px]"
              onClick={clearSelection}
              disabled={submitting}
            >
              <X className="h-3 w-3" strokeWidth={1.5} />
              Clear
            </Button>
          </div>

          {intakeLoading && (
            <div className="flex items-center gap-2 px-3 py-4 text-[11px] text-mute">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading questions…
            </div>
          )}

          {intake && (
            <div className="divide-y divide-hairline/70">
              {intake.questions.map((q) => {
                const open = openQuestions.has(q.id);
                const summary = answerSummary(q);
                return (
                  <div key={q.id}>
                    <button
                      type="button"
                      onClick={() => toggleAccordion(q.id)}
                      className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-canvas/60"
                      aria-expanded={open}
                    >
                      {open ? (
                        <ChevronDown className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
                      ) : (
                        <ChevronRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-mute" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="text-[11px] font-medium text-ink">
                          {q.prompt}
                          {q.required ? (
                            <span className="text-danger-text"> *</span>
                          ) : null}
                        </div>
                        {!open && (
                          <div className="mt-0.5 truncate text-[10px] text-mute">
                            {summary}
                          </div>
                        )}
                      </div>
                    </button>
                    {open && (
                      <div className="flex flex-wrap gap-1.5 px-3 pb-3 pl-9">
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
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {intake && (
            <div className="border-t border-hairline/70 px-3 py-3">
              <Button
                type="button"
                className="w-full sm:w-auto"
                disabled={disabled || submitting || intakeLoading}
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
      )}
    </div>
  );
}
