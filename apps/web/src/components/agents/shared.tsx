import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Loader2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  agentStatusVariant,
  isPresentationPending,
  isQuestionsPending,
  parseContextQuestions,
  prettyJson,
  toolDisplayName,
  type ContextAnswers,
  type PendingTool,
} from "./agent-utils";
import type { AgentStep } from "@/api";

export function AgentStatusBadge({ status }: { status: string }) {
  return <Badge variant={agentStatusVariant(status)}>{status}</Badge>;
}

export function AgentStepCard({ step }: { step: AgentStep }) {
  return (
    <div className="rounded-[6px] border border-hairline bg-canvas px-3 py-2.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-ink">#{step.step_index}</span>
        <Badge variant="outline">{step.type}</Badge>
        {step.tool_name && (
          <Badge variant="secondary">{toolDisplayName(step.tool_name)}</Badge>
        )}
      </div>
      {step.input != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">Input</div>
          <pre className="mt-0.5 max-h-32 overflow-auto whitespace-pre-wrap text-xs text-body">
            {prettyJson(step.input)}
          </pre>
        </div>
      )}
      {step.output != null && (
        <div className="mt-1">
          <div className="text-[11px] font-medium uppercase text-mute">
            Output
          </div>
          <pre className="mt-0.5 max-h-40 overflow-auto whitespace-pre-wrap text-xs text-body">
            {prettyJson(step.output)}
          </pre>
        </div>
      )}
    </div>
  );
}

export function AgentStepList({
  steps,
  compact = false,
}: {
  steps: AgentStep[];
  compact?: boolean;
}) {
  const sorted = [...steps].sort((a, b) => a.step_index - b.step_index);
  const [expanded, setExpanded] = useState(false);

  if (sorted.length === 0) {
    return <p className="text-xs text-mute">No steps recorded.</p>;
  }

  if (compact) {
    return (
      <div className="space-y-1.5">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="inline-flex items-center gap-1 text-[11px] font-medium text-ink underline-offset-2 hover:underline"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" strokeWidth={1.5} />
          ) : (
            <ChevronRight className="h-3 w-3" strokeWidth={1.5} />
          )}
          {expanded ? "Hide step details" : `Show ${sorted.length} step details`}
        </button>
        <ul className="space-y-1">
          {sorted.map((s) => (
            <li
              key={s.id}
              className="flex flex-wrap items-center gap-1.5 text-xs text-body"
            >
              <span className="font-medium text-ink">#{s.step_index}</span>
              <Badge variant="outline" className="text-[10px]">
                {s.type}
              </Badge>
              {s.tool_name && (
                <Badge variant="secondary" className="text-[10px]">
                  {toolDisplayName(s.tool_name)}
                </Badge>
              )}
            </li>
          ))}
        </ul>
        {expanded && (
          <div className="space-y-2 pt-1">
            {sorted.map((s) => (
              <AgentStepCard key={`full-${s.id}`} step={s} />
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {sorted.map((s) => (
        <AgentStepCard key={s.id} step={s} />
      ))}
    </div>
  );
}

export type ApproveOptions = {
  answers?: ContextAnswers;
  enabledMcpIds?: string[];
};

function availableMcpFromPending(
  pendingTool: PendingTool,
): { id: string; name: string }[] {
  const args = pendingTool.args ?? {};
  const raw = args.available_mcp;
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((x): x is Record<string, unknown> => !!x && typeof x === "object")
    .map((x) => ({
      id: String(x.id ?? ""),
      name: String(x.name ?? x.id ?? "MCP"),
    }))
    .filter((x) => x.id);
}

function preselectedMcpFromPending(pendingTool: PendingTool): string[] {
  const args = pendingTool.args ?? {};
  const raw = args.preselected_mcp_ids;
  if (!Array.isArray(raw)) return [];
  return raw.map((x) => String(x)).filter(Boolean);
}

export function AgentApprovalCard({
  pendingTool,
  approving,
  onApprove,
  onReject,
  className,
}: {
  pendingTool: PendingTool;
  approving?: boolean;
  onApprove: (options?: ApproveOptions) => void;
  onReject: () => void;
  className?: string;
}) {
  const presentation = isPresentationPending(pendingTool);
  const contextForm = parseContextQuestions(pendingTool);
  const questions = isQuestionsPending(pendingTool) && contextForm;
  const availableMcp = availableMcpFromPending(pendingTool);

  const [textAnswers, setTextAnswers] = useState<Record<string, string>>({});
  const [checkboxAnswers, setCheckboxAnswers] = useState<
    Record<string, string[]>
  >({});
  const [formError, setFormError] = useState<string | null>(null);
  const [mcpEnabled, setMcpEnabled] = useState<Record<string, boolean>>(() => {
    const pre = new Set(preselectedMcpFromPending(pendingTool));
    const init: Record<string, boolean> = {};
    for (const m of availableMcpFromPending(pendingTool)) {
      init[m.id] = pre.has(m.id);
    }
    return init;
  });

  function toggleOption(qid: string, oid: string, allowMultiple: boolean) {
    setCheckboxAnswers((prev) => {
      const cur = prev[qid] ?? [];
      if (allowMultiple) {
        const next = cur.includes(oid)
          ? cur.filter((x) => x !== oid)
          : [...cur, oid];
        return { ...prev, [qid]: next };
      }
      // single-select: toggle off if same, else replace
      if (cur.length === 1 && cur[0] === oid) {
        return { ...prev, [qid]: [] };
      }
      return { ...prev, [qid]: [oid] };
    });
  }

  function buildAnswers(): ContextAnswers {
    const out: ContextAnswers = {};
    if (!contextForm) return out;
    for (const q of contextForm.questions) {
      if (q.input === "checkbox") {
        const selected = checkboxAnswers[q.id] ?? [];
        if (selected.length) {
          out[q.id] = q.allow_multiple ? selected : selected[0] ?? "";
        }
      } else {
        const t = (textAnswers[q.id] ?? "").trim();
        if (t) out[q.id] = t;
      }
    }
    return out;
  }

  function validateRequired(): string | null {
    if (!contextForm) return null;
    for (const q of contextForm.questions) {
      if (!q.required) continue;
      if (q.input === "checkbox") {
        if (!(checkboxAnswers[q.id]?.length)) {
          return `Please answer: ${q.prompt}`;
        }
      } else if (!(textAnswers[q.id] ?? "").trim()) {
        return `Please answer: ${q.prompt}`;
      }
    }
    return null;
  }

  function handleContinue(skip: boolean) {
    if (!skip) {
      const err = validateRequired();
      if (err) {
        setFormError(err);
        return;
      }
    }
    setFormError(null);
    onApprove({ answers: skip ? {} : buildAnswers() });
  }

  if (questions && contextForm) {
    return (
      <div
        className={
          className ??
          "rounded-[6px] border border-warning-border bg-warning-soft p-3"
        }
      >
        <div className="text-sm font-semibold text-ink">{contextForm.title}</div>
        {contextForm.subtitle && (
          <p className="mt-1 text-xs text-body">{contextForm.subtitle}</p>
        )}
        <div className="mt-3 space-y-3">
          {contextForm.questions.map((q) => (
            <div key={q.id} className="space-y-1.5">
              <label className="block text-xs font-medium text-ink">
                {q.prompt}
                {q.required ? (
                  <span className="ml-1 text-danger">*</span>
                ) : (
                  <span className="ml-1 font-normal text-mute">(optional)</span>
                )}
              </label>
              {q.input === "checkbox" && q.options ? (
                <div className="flex flex-wrap gap-1.5">
                  {q.options.map((opt) => {
                    const selected = (checkboxAnswers[q.id] ?? []).includes(
                      opt.id,
                    );
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        disabled={approving}
                        onClick={() =>
                          toggleOption(q.id, opt.id, Boolean(q.allow_multiple))
                        }
                        className={
                          selected
                            ? "rounded-full border border-accent bg-accent/10 px-2.5 py-1 text-xs font-medium text-accent"
                            : "rounded-full border border-hairline bg-canvas px-2.5 py-1 text-xs text-body hover:border-accent/40"
                        }
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              ) : (
                <textarea
                  className="w-full resize-y rounded-[6px] border border-hairline bg-canvas px-2.5 py-1.5 text-xs text-ink placeholder:text-mute focus:border-accent focus:outline-none"
                  rows={2}
                  disabled={approving}
                  placeholder={q.placeholder}
                  value={textAnswers[q.id] ?? ""}
                  onChange={(e) =>
                    setTextAnswers((prev) => ({
                      ...prev,
                      [q.id]: e.target.value,
                    }))
                  }
                />
              )}
            </div>
          ))}
        </div>
        {formError && (
          <p className="mt-2 text-xs text-danger">{formError}</p>
        )}
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            className="rounded-[6px]"
            disabled={approving}
            onClick={() => handleContinue(false)}
          >
            {approving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Check className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Continue
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={approving}
            onClick={() => handleContinue(true)}
          >
            Skip
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={approving}
            onClick={onReject}
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
            Cancel
          </Button>
        </div>
      </div>
    );
  }

  function selectedMcpIds(): string[] {
    return Object.entries(mcpEnabled)
      .filter(([, on]) => on)
      .map(([id]) => id);
  }

  function handlePresentationApprove() {
    onApprove({ enabledMcpIds: selectedMcpIds() });
  }

  return (
    <div
      className={
        className ??
        "rounded-[6px] border border-warning-border bg-warning-soft p-3"
      }
    >
      <div className="text-sm font-semibold text-ink">
        {presentation ? "View in UI?" : "Approval required"}
      </div>
      {presentation ? (
        <>
          <p className="mt-1 text-xs text-body">
            Generate a visual summary, or keep the text-only answer.
          </p>
          {availableMcp.length > 0 && (
            <div className="mt-3 rounded-[6px] border border-hairline bg-canvas px-2.5 py-2">
              <p className="text-[11px] font-medium text-ink">
                Available connectors
              </p>
              <ul className="mt-1.5 space-y-1">
                {availableMcp.map((m) => (
                  <li key={m.id}>
                    <label className="flex cursor-pointer items-center gap-2 py-0.5 text-[12px] text-ink">
                      <input
                        type="checkbox"
                        className="h-3.5 w-3.5 rounded border-hairline"
                        checked={!!mcpEnabled[m.id]}
                        disabled={approving}
                        onChange={() =>
                          setMcpEnabled((prev) => ({
                            ...prev,
                            [m.id]: !prev[m.id],
                          }))
                        }
                      />
                      <span>
                        Use <span className="font-medium">{m.name}</span>
                      </span>
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <>
          <p className="mt-1 text-xs text-body">
            Write tool{" "}
            <code className="rounded bg-canvas px-1">
              {pendingTool.name ?? "unknown"}
            </code>
            . Review args, then approve or reject.{" "}
            <span className="font-medium text-ink">
              After approve, the agent continues
            </span>{" "}
            (confirm + next steps)—it does not stop at the write.
          </p>
          <pre className="mt-2 max-h-40 overflow-auto rounded border border-hairline bg-canvas p-2 text-xs text-body">
            {prettyJson(pendingTool.args ?? {})}
          </pre>
        </>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          className="rounded-[6px]"
          disabled={approving}
          onClick={() =>
            presentation ? handlePresentationApprove() : onApprove()
          }
        >
          {approving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Check className="h-3.5 w-3.5" strokeWidth={1.5} />
          )}
          {presentation ? "View in UI" : "Approve"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={approving}
          onClick={onReject}
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          {presentation ? "Text only" : "Reject"}
        </Button>
      </div>
    </div>
  );
}
