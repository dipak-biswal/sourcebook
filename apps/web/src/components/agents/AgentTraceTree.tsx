import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Coins,
  GitBranch,
  Loader2,
  Shield,
  Sparkles,
  Target,
  Wrench,
} from "lucide-react";
import type { AgentRun } from "@/api";
import { parseWebSearchOutput, prettyJson } from "@/components/agents/agent-utils";
import { LlmModelBadge } from "@/components/agents/llm-model";
import type {
  ExecutionTrace,
  TraceAgentTurnPhase,
  TraceChild,
  TraceFinalAnswerChild,
  TraceHandoffChild,
  TraceHitlEmbedChild,
  TraceLlmChild,
  TraceLlmRole,
  TracePhase,
  TracePresentationPhase,
  TraceState,
  TraceSynthesisPhase,
  TraceToolChild,
  TraceVisualStageChild,
} from "@/components/agents/execution-trace-types";
import { isGenerativeUI } from "@/components/agents/generative-ui";
import { AgentApprovalCard } from "@/components/agents/shared";
import { WebSearchResults } from "@/components/agents/WebSearchResults";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const MAIN_ICON_COL = 36;
const NESTED_ICON_COL = 28;
const BRANCH_STUB = 12;
const NESTED_BRANCH_STUB = 10;
const VISUAL_SUMMARY_AGENT_LABEL = "Visual Summary Agent";

function traceChildContainsActive(child: TraceChild, activeChildId: string | null): boolean {
  if (!activeChildId) return false;
  if (child.id === activeChildId) return true;
  if (child.type === "visual_stage") {
    return child.children.some((nested) => traceChildContainsActive(nested, activeChildId));
  }
  if (child.type === "tool") {
    return (child.children ?? []).some((nested) => nested.id === activeChildId);
  }
  return false;
}

function OutputOnlyBody({ output, state }: { output?: string; state: TraceState }) {
  const text = output?.trim() ?? "";
  return (
    <div>
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Output</div>
      <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
        {text || (state === "running" ? "" : "—")}
      </pre>
      {state === "running" && !text && (
        <span className="mt-1 inline-block h-3 w-0.5 animate-pulse bg-ink" />
      )}
    </div>
  );
}

function TraceIcon({
  icon: Icon,
  state,
  active,
  nested,
}: {
  icon: typeof Brain;
  state: TraceState;
  active?: boolean;
  nested?: boolean;
}) {
  const size = nested ? "h-7 w-7" : "h-9 w-9";
  const iconSize = nested ? "h-3 w-3" : "h-4 w-4";
  return (
    <div
      className={cn(
        "relative z-10 flex shrink-0 items-center justify-center rounded-full border-2 bg-canvas transition-all",
        size,
        state === "running" && "border-warning-border shadow-[0_0_0_4px_rgba(234,179,8,0.14)]",
        state === "done" && "border-ink/30",
        state === "pending" && "border-hairline",
        active && state === "running" && "animate-trace-pulse",
      )}
    >
      {state === "running" ? (
        <Loader2 className={cn(iconSize, "animate-spin text-warning-text")} />
      ) : (
        <Icon className={cn(iconSize, "text-ink")} strokeWidth={2} />
      )}
    </div>
  );
}

function ExpandableTraceRow({
  icon,
  label,
  state,
  active,
  nodeId,
  activeRef,
  nested,
  isLast,
  defaultOpen = false,
  model,
  llmRole,
  children,
}: {
  icon: typeof Brain;
  label: string;
  state: TraceState;
  active?: boolean;
  nodeId: string;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  nested?: boolean;
  isLast?: boolean;
  defaultOpen?: boolean;
  model?: string | null;
  llmRole?: TraceLlmRole | string | null;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const iconCol = nested ? NESTED_ICON_COL : MAIN_ICON_COL;
  const stubW = nested ? NESTED_BRANCH_STUB : BRANCH_STUB;
  const iconTop = nested ? 4 : 6;
  const iconSize = nested ? 28 : 36;
  const branchTop = iconTop + iconSize / 2;
  const expandable = children != null;

  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);

  return (
    <div
      ref={active ? activeRef : undefined}
      data-trace-id={nodeId}
      className={cn("relative min-w-0", nested ? "pb-1" : "pb-1.5", active && "scroll-mt-4")}
    >
      <div className="relative flex min-w-0">
        <div
          className="relative z-10 flex shrink-0 justify-center"
          style={{ width: iconCol, paddingTop: iconTop }}
        >
          {!isLast && (
            <div
              className="pointer-events-none absolute left-1/2 w-0.5 -translate-x-1/2 bg-ink/25"
              style={{ top: branchTop, bottom: 0 }}
            />
          )}
          <TraceIcon icon={icon} state={state} active={active} nested={nested} />
        </div>

        <div className="flex min-w-0 flex-1">
          <div className="relative shrink-0" style={{ width: stubW }}>
            <div
              className="absolute left-0 right-0 h-0.5 bg-ink/25"
              style={{ top: branchTop }}
            />
          </div>

          <div
            className="min-w-0 flex-1"
            style={{ paddingTop: branchTop - (nested ? 7 : 8) }}
          >
            {expandable ? (
              <div>
                <button
                  type="button"
                  onClick={() => setOpen((v) => !v)}
                  className="flex w-full items-start gap-1.5 rounded-[6px] px-1 py-0.5 text-left hover:bg-canvas-soft"
                >
                  <span className="mt-0.5 shrink-0 text-mute">
                    {open ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <PhaseLabel
                      label={label}
                      state={state}
                      active={active}
                      nested={nested}
                      model={model}
                      llmRole={llmRole}
                    />
                  </span>
                </button>
                {open && (
                  <div className="mt-2 pl-5 text-xs leading-relaxed text-body">
                    {children}
                  </div>
                )}
              </div>
            ) : (
              <div className="px-1 py-0.5">
                <PhaseLabel
                  label={label}
                  state={state}
                  nested={nested}
                  model={model}
                  llmRole={llmRole}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function llmRoleBadge(role: TraceLlmRole | string | null | undefined): string | null {
  switch (role) {
    case "orchestrator_decision":
      return "Orchestrator";
    case "orchestrator_response":
      return "Orchestrator";
    case "embedded_planner":
      return "Planner LLM";
    case "embedded_render":
      return "Render LLM";
    case "embedded":
      return "Tool LLM";
    default:
      return null;
  }
}

function PhaseLabel({
  label,
  state,
  active,
  nested,
  model,
  llmRole,
}: {
  label: string;
  state: TraceState;
  active?: boolean;
  nested?: boolean;
  model?: string | null;
  llmRole?: TraceLlmRole | string | null;
}) {
  const roleBadge = llmRoleBadge(llmRole);
  return (
    <span className="flex flex-wrap items-center gap-1.5">
      <span
        className={cn(
          "font-medium text-ink",
          nested ? "text-[11px]" : "text-xs",
          active && state === "running" && "text-warning-text",
        )}
      >
        {label}
      </span>
      {roleBadge && (
        <Badge variant="outline" className="text-[10px] font-normal">
          {roleBadge}
        </Badge>
      )}
      <LlmModelBadge model={model} />
      {state === "running" && (
        <Badge variant="warning" className="gap-1 text-[10px]">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-warning opacity-60" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-warning" />
          </span>
          live
        </Badge>
      )}
      {state === "done" && !nested && (
        <Badge variant="success" className="text-[10px]">
          done
        </Badge>
      )}
    </span>
  );
}

function formatTracePrompt(
  prompt: TraceLlmChild["prompt"] | TracePresentationPhase["prompt"],
): string {
  if (prompt == null) return "";
  if (typeof prompt === "string") return prompt;
  if (!Array.isArray(prompt) || prompt.length === 0) return "";
  return prompt
    .map((message) => {
      const role = message.role || "message";
      const content = message.content ?? "";
      return `[${role}]\n${content}`;
    })
    .join("\n\n");
}

function TokenUsageLine({
  promptTokens,
  completionTokens,
  totalTokens,
}: {
  promptTokens?: number | null;
  completionTokens?: number | null;
  totalTokens?: number | null;
}) {
  if (
    promptTokens == null &&
    completionTokens == null &&
    totalTokens == null
  ) {
    return null;
  }
  return (
    <div className="flex flex-wrap items-center gap-2 text-[10px] text-mute">
      <Coins className="h-3 w-3" strokeWidth={1.5} />
      {promptTokens != null && promptTokens > 0 && (
        <span>Input: {promptTokens.toLocaleString()} tok</span>
      )}
      {completionTokens != null && completionTokens > 0 && (
        <span>Output: {completionTokens.toLocaleString()} tok</span>
      )}
      {totalTokens != null && totalTokens > 0 && (
        <span>Total: {totalTokens.toLocaleString()} tok</span>
      )}
    </div>
  );
}

function LlmTraceSections({
  prompt,
  output,
  state,
  promptTokens,
  completionTokens,
  totalTokens,
}: {
  prompt?: TraceLlmChild["prompt"] | TracePresentationPhase["prompt"];
  output?: string;
  state: TraceState;
  promptTokens?: number | null;
  completionTokens?: number | null;
  totalTokens?: number | null;
}) {
  const promptText = formatTracePrompt(prompt);
  const outputText = output ?? "";

  return (
    <div className="space-y-2">
      <TokenUsageLine
        promptTokens={promptTokens}
        completionTokens={completionTokens}
        totalTokens={totalTokens}
      />
      {promptText ? (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Prompt</div>
          <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
            {promptText}
          </pre>
        </div>
      ) : null}
      <div>
        <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Output</div>
        <pre className="max-h-44 overflow-auto whitespace-pre-wrap rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
          {outputText || (state === "running" ? "" : "—")}
        </pre>
        {state === "running" && (
          <span className="mt-1 inline-block h-3 w-0.5 animate-pulse bg-ink" />
        )}
      </div>
    </div>
  );
}

function LlmChildBody({ child }: { child: Extract<TraceChild, { type: "llm_response" }> }) {
  return (
    <LlmTraceSections
      prompt={child.prompt}
      output={child.output}
      state={child.state}
      promptTokens={child.prompt_tokens}
      completionTokens={child.completion_tokens}
      totalTokens={child.total_tokens}
    />
  );
}

function HitlEmbedBody({ child }: { child: TraceHitlEmbedChild }) {
  const output =
    child.output && typeof child.output === "object"
      ? (child.output as { status?: string })
      : null;

  if (child.building && output?.status !== "approved") {
    return (
      <div className="flex items-center gap-2 text-[11px] text-warning-text">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building visual summary…
      </div>
    );
  }

  if (output?.status === "approved") {
    return <p className="text-body">Approved — visual summary generated</p>;
  }

  if (output?.status === "rejected") {
    return <p className="text-body">Rejected — answer kept as text only.</p>;
  }

  if (child.input) {
    return (
      <pre className="max-h-32 overflow-auto rounded border border-hairline bg-canvas p-2 font-mono text-[11px]">
        {prettyJson(child.input)}
      </pre>
    );
  }

  return <p className="text-mute">Completed</p>;
}

function PresentationTraceBody({ phase }: { phase: TracePresentationPhase }) {
  const output = isGenerativeUI(phase.output) ? phase.output : null;

  if (!output) {
    return <p className="text-[11px] text-mute">Waiting for generated UI…</p>;
  }

  return (
    <div className="space-y-1.5 rounded-[6px] border border-hairline bg-canvas-soft/40 p-2">
      <p className="font-medium text-ink">{output.title}</p>
      {output.plain_summary && (
        <p className="text-[11px] text-mute">{output.plain_summary}</p>
      )}
      <div className="flex flex-wrap gap-2 text-[10px] text-mute">
        {phase.presentation_profile && (
          <span>Profile: {phase.presentation_profile.replace(/_/g, " ")}</span>
        )}
        {phase.block_count != null && <span>{phase.block_count} blocks</span>}
      </div>
    </div>
  );
}

function ToolChildBody({
  child,
  activeChildId,
  activeRef,
  defaultOpen,
}: {
  child: TraceToolChild;
  activeChildId?: string | null;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  defaultOpen?: boolean;
}) {
  const web =
    child.tool_name === "web_search" && child.output
      ? parseWebSearchOutput(child.output)
      : null;
  const llmChildren = (child.children ?? []).filter(
    (c): c is TraceLlmChild => c.type === "llm_response",
  );
  const showToolIo = !child.has_embedded_llm || child.tool_name === "web_search";

  return (
    <div className="space-y-2">
      {child.has_embedded_llm && llmChildren.length > 0 && (
        <p className="text-[11px] text-mute">
          Tool invocation — LLM prompt and output are on the embedded node
          {llmChildren.length > 1 ? "s" : ""} below.
        </p>
      )}
      {showToolIo && child.input != null && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Input</div>
          <pre className="max-h-36 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
            {prettyJson(child.input)}
          </pre>
        </div>
      )}
      {showToolIo && child.output != null && (
        <div>
          <div className="mb-1 text-[10px] font-bold uppercase tracking-wide text-mute">Output</div>
          {web ? (
            <WebSearchResults data={web} compact />
          ) : (
            <pre className="max-h-44 overflow-auto rounded-[6px] border border-hairline bg-canvas p-2 font-mono text-[11px] text-body">
              {prettyJson(child.output)}
            </pre>
          )}
        </div>
      )}
      {llmChildren.map((llmChild, i) => {
        const active = llmChild.id === activeChildId;
        return (
          <ExpandableTraceRow
            key={llmChild.id}
            nodeId={llmChild.id}
            activeRef={active ? activeRef : undefined}
            active={active}
            nested
            isLast={i === llmChildren.length - 1}
            defaultOpen={(defaultOpen ?? false) || active}
            icon={Brain}
            label={llmChild.label}
            state={llmChild.state}
            model={llmChild.model}
            llmRole={llmChild.llm_role}
          >
            <LlmChildBody child={llmChild} />
          </ExpandableTraceRow>
        );
      })}
      {child.state === "running" && child.output == null && (
        <div className="flex items-center gap-2 text-[11px] text-warning-text">
          <Loader2 className="h-3 w-3 animate-spin" />
          Executing…
        </div>
      )}
    </div>
  );
}

function TurnChildrenTimeline({
  children,
  activeChildId,
  activeRef,
  defaultOpen,
  isLive,
}: {
  children: TraceChild[];
  activeChildId?: string | null;
  activeRef?: React.RefObject<HTMLDivElement | null>;
  defaultOpen: boolean;
  isLive?: boolean;
}) {
  return (
    <div className="rounded-[6px] border border-hairline/80 bg-canvas-soft/40 p-2">
      {children.map((child, i) => {
        const isLast = i === children.length - 1;
        const active = traceChildContainsActive(child, activeChildId ?? null);
        if (child.type === "handoff") {
          return (
            <ExpandableTraceRow
              key={child.id}
              nodeId={child.id}
              activeRef={active ? activeRef : undefined}
              active={active}
              nested
              isLast={isLast}
              defaultOpen={active}
              icon={Target}
              label={child.label}
              state={child.state}
            >
              <OutputOnlyBody output={child.output} state={child.state} />
            </ExpandableTraceRow>
          );
        }
        if (child.type === "final_answer") {
          const finalChild = child as TraceFinalAnswerChild;
          return (
            <ExpandableTraceRow
              key={child.id}
              nodeId={child.id}
              activeRef={active ? activeRef : undefined}
              active={active}
              nested
              isLast={isLast}
              defaultOpen={active}
              icon={CheckCircle2}
              label={finalChild.label}
              state={finalChild.state}
            >
              <OutputOnlyBody output={finalChild.output} state={finalChild.state} />
            </ExpandableTraceRow>
          );
        }
        if (child.type === "visual_stage") {
          const stage = child as TraceVisualStageChild;
          const stageOpen =
            active || (isLive && stage.state === "running");
          return (
            <ExpandableTraceRow
              key={child.id}
              nodeId={child.id}
              activeRef={active ? activeRef : undefined}
              active={active}
              nested
              isLast={isLast}
              defaultOpen={stageOpen}
              icon={Wrench}
              label={stage.label}
              state={stage.state}
            >
              <TurnChildrenTimeline
                children={stage.children}
                activeChildId={activeChildId}
                activeRef={activeRef}
                defaultOpen={false}
                isLive={isLive}
              />
            </ExpandableTraceRow>
          );
        }
        if (child.type === "tool") {
          return (
            <ExpandableTraceRow
              key={child.id}
              nodeId={child.id}
              activeRef={active ? activeRef : undefined}
              active={active}
              nested
              isLast={isLast}
              defaultOpen={defaultOpen || active}
              icon={child.tool_name === "generative_ui" ? Sparkles : Wrench}
              label={child.label}
              state={child.state}
            >
              <ToolChildBody
                child={child}
                activeChildId={activeChildId}
                activeRef={activeRef}
                defaultOpen={defaultOpen || active}
              />
            </ExpandableTraceRow>
          );
        }
        if (child.type === "hitl_embed") {
          return (
            <ExpandableTraceRow
              key={child.id}
              nodeId={child.id}
              activeRef={active ? activeRef : undefined}
              active={active}
              nested
              isLast={isLast}
              defaultOpen={defaultOpen || active}
              icon={Shield}
              label={child.label}
              state={child.state}
            >
              <HitlEmbedBody child={child} />
            </ExpandableTraceRow>
          );
        }
        return (
          <ExpandableTraceRow
            key={child.id}
            nodeId={child.id}
            activeRef={active ? activeRef : undefined}
            active={active}
            nested
            isLast={isLast}
            defaultOpen={defaultOpen || active}
            icon={Brain}
            label={child.label}
            state={child.state}
            model={child.model}
            llmRole={child.llm_role}
          >
            <LlmChildBody child={child} />
          </ExpandableTraceRow>
        );
      })}
    </div>
  );
}

function HitlBody({
  phase,
  run,
  approving,
  onApprove,
  onReject,
  presTitle,
}: {
  phase: Extract<TracePhase, { type: "hitl" }>;
  run: AgentRun | null | undefined;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
  presTitle?: string;
}) {
  const output =
    phase.output && typeof phase.output === "object"
      ? (phase.output as { status?: string })
      : null;

  if (phase.pending && run?.pending_tool && onApprove && onReject) {
    return (
      <AgentApprovalCard
        pendingTool={run.pending_tool}
        approving={approving}
        onApprove={onApprove}
        onReject={onReject}
        className="border-warning-border/60 bg-warning-soft/40"
      />
    );
  }

  if (phase.building && output?.status !== "approved") {
    return (
      <div className="flex items-center gap-2 text-[11px] text-warning-text">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building visual summary…
      </div>
    );
  }

  if (output?.status === "approved") {
    return (
      <div className="space-y-1.5">
        <p className="font-medium text-ink">Approved — visual summary generated</p>
        {presTitle && (
          <p className="text-mute">
            Title: <span className="text-body">{presTitle}</span>
          </p>
        )}
      </div>
    );
  }

  if (output?.status === "rejected") {
    return <p className="text-body">Rejected — answer kept as text only.</p>;
  }

  if (phase.input) {
    return (
      <pre className="max-h-32 overflow-auto rounded border border-hairline bg-canvas p-2 font-mono text-[11px]">
        {prettyJson(phase.input)}
      </pre>
    );
  }

  return <p className="text-mute">Completed</p>;
}

function traceProgress(phases: TracePhase[]): number {
  const nodes = phases.filter((p) => p.type !== "goal");
  if (!nodes.length) return 8;
  const done = nodes.filter((p) => p.state === "done").length;
  const running = nodes.some((p) => p.state === "running");
  const base = Math.round((done / nodes.length) * 100);
  return running ? Math.min(base + 6, 99) : base;
}

function presentationTitle(trace: ExecutionTrace, run: AgentRun | null | undefined): string | undefined {
  if (run?.presentation_spec && isGenerativeUI(run.presentation_spec)) {
    return run.presentation_spec.title;
  }
  for (const phase of trace.phases) {
    if (phase.type === "presentation" && isGenerativeUI(phase.output)) {
      return phase.output.title;
    }
  }
  return undefined;
}

export function AgentTraceTree({
  run,
  executionTrace,
  running,
  approving,
  onApprove,
  onReject,
}: {
  run: AgentRun | null | undefined;
  executionTrace?: ExecutionTrace | null;
  running?: boolean;
  approving?: boolean;
  onApprove?: () => void;
  onReject?: () => void;
}) {
  const activeRef = useRef<HTMLDivElement | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const trace = executionTrace ?? run?.execution_trace ?? null;
  // Presentation "Visual summary" duplicates the Visual summary tab; keep the agent turn.
  const phases = useMemo(
    () => (trace?.phases ?? []).filter((p) => p.type !== "presentation"),
    [trace?.phases],
  );
  const isLive = running || approving || (trace != null && !trace.is_complete);
  const progress = trace ? traceProgress(phases) : 0;
  const tokenSummary = trace?.token_usage;
  const totalTokens =
    tokenSummary?.total_tokens ??
    (tokenSummary?.prompt_tokens != null && tokenSummary?.completion_tokens != null
      ? tokenSummary.prompt_tokens + tokenSummary.completion_tokens
      : null) ??
    run?.token_usage ??
    null;
  const presTitle = trace ? presentationTitle(trace, run) : undefined;
  const activeId = trace?.active_phase_id ?? null;

  const activeChildId = useMemo(() => {
    if (!activeId || !trace) return null;
    const findInChildren = (children: TraceChild[]): string | null => {
      for (const child of children) {
        if (child.id === activeId) return child.id;
        if (child.type === "visual_stage" && traceChildContainsActive(child, activeId)) {
          for (const nested of child.children) {
            const hit = findInChildren([nested]);
            if (hit) return hit;
          }
        }
        if (child.type === "tool") {
          for (const nested of child.children ?? []) {
            if (nested.id === activeId) return nested.id;
          }
        }
      }
      return null;
    };
    for (const phase of phases) {
      if (phase.type !== "agent_turn") continue;
      const hit = findInChildren(phase.children);
      if (hit) return hit;
    }
    return null;
  }, [activeId, phases, trace]);

  useEffect(() => {
    if (!isLive || !activeRef.current) return;
    activeRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [isLive, activeId, trace]);

  const defaultOpen = trace?.is_complete ?? false;

  function renderPhase(phase: TracePhase, isLast: boolean) {
    const active = phase.id === activeId || phase.state === "running";

    if (phase.type === "goal") {
      return (
        <ExpandableTraceRow
          key={phase.id}
          nodeId={phase.id}
          icon={Target}
          label={phase.label}
          state={phase.state}
          isLast={isLast}
          defaultOpen={defaultOpen}
        >
          <p className="text-body">{phase.goal}</p>
        </ExpandableTraceRow>
      );
    }

    if (phase.type === "agent_turn") {
      const turn = phase as TraceAgentTurnPhase;
      return (
        <ExpandableTraceRow
          key={phase.id}
          nodeId={phase.id}
          activeRef={active && !activeChildId ? activeRef : undefined}
          active={active && !activeChildId}
          icon={Brain}
          label={phase.label}
          state={phase.state}
          isLast={isLast}
          defaultOpen={defaultOpen || active}
        >
          <TurnChildrenTimeline
            children={turn.children}
            activeChildId={activeChildId}
            activeRef={activeRef}
            defaultOpen={false}
            isLive={isLive}
          />
        </ExpandableTraceRow>
      );
    }

    if (phase.type === "hitl") {
      return (
        <ExpandableTraceRow
          key={phase.id}
          nodeId={phase.id}
          activeRef={active ? activeRef : undefined}
          active={active}
          icon={Shield}
          label={phase.label}
          state={phase.state}
          isLast={isLast}
          defaultOpen={defaultOpen || active || !!phase.pending}
        >
          <HitlBody
            phase={phase}
            run={run}
            approving={approving}
            onApprove={onApprove}
            onReject={onReject}
            presTitle={presTitle}
          />
        </ExpandableTraceRow>
      );
    }

    if (phase.type === "presentation") {
      const presentation = phase as TracePresentationPhase;
      return (
        <ExpandableTraceRow
          key={phase.id}
          nodeId={phase.id}
          activeRef={active ? activeRef : undefined}
          active={active}
          icon={Sparkles}
          label={phase.label}
          state={phase.state}
          isLast={isLast}
          defaultOpen={defaultOpen || active}
          model={presentation.model}
        >
          <PresentationTraceBody phase={presentation} />
        </ExpandableTraceRow>
      );
    }

    if (phase.type === "synthesis") {
      const synthesis = phase as TraceSynthesisPhase;
      return (
        <ExpandableTraceRow
          key={phase.id}
          nodeId={phase.id}
          icon={CheckCircle2}
          label={phase.label}
          state={phase.state}
          isLast={isLast}
          defaultOpen={defaultOpen}
          model={synthesis.model}
        >
          <LlmTraceSections
            prompt={synthesis.prompt}
            output={synthesis.output}
            state={synthesis.state}
            promptTokens={synthesis.prompt_tokens}
            completionTokens={synthesis.completion_tokens}
            totalTokens={synthesis.total_tokens}
          />
        </ExpandableTraceRow>
      );
    }

    return null;
  }

  return (
    <div className="flex flex-col">
      <div className="border-b border-hairline bg-canvas-soft px-4 py-2.5">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4 text-ink" strokeWidth={1.5} />
            <span className="text-xs font-semibold text-ink">Execution trace</span>
            {isLive && (
              <Badge variant="warning" className="gap-1 text-[10px]">
                <Loader2 className="h-2.5 w-2.5 animate-spin" />
                {run?.status === "waiting_approval" ? "awaiting you" : "running"}
              </Badge>
            )}
          </div>
          {totalTokens != null && totalTokens > 0 && (
            <span
              className="inline-flex items-center gap-1 font-mono text-[10px] text-mute"
              title={
                tokenSummary?.prompt_tokens != null && tokenSummary?.completion_tokens != null
                  ? `Input ${tokenSummary.prompt_tokens.toLocaleString()} · Output ${tokenSummary.completion_tokens.toLocaleString()}`
                  : undefined
              }
            >
              <Coins className="h-3 w-3" />
              {totalTokens.toLocaleString()} tok
            </span>
          )}
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-hairline">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-500 ease-out",
              isLive
                ? "animate-trace-progress bg-gradient-to-r from-warning-border via-ink to-warning-border bg-[length:200%_100%]"
                : "bg-success-border",
            )}
            style={{ width: `${Math.max(isLive ? progress : 100, isLive ? 12 : 0)}%` }}
          />
        </div>
      </div>

      <div ref={scrollRef} className="max-h-[min(70vh,36rem)] overflow-x-auto overflow-y-auto p-4">
        <div className="relative min-w-0">
          {phases.length === 0 ? (
            <p className="text-xs text-mute">Waiting for execution trace…</p>
          ) : (
            phases.map((phase, i) => renderPhase(phase, i === phases.length - 1))
          )}
        </div>
      </div>

      <style>{`
        @keyframes trace-pulse {
          0%, 100% { box-shadow: 0 0 0 4px rgba(234, 179, 8, 0.1); }
          50% { box-shadow: 0 0 0 7px rgba(234, 179, 8, 0.18); }
        }
        @keyframes trace-progress {
          0% { background-position: 100% 0; }
          100% { background-position: -100% 0; }
        }
        .animate-trace-pulse { animation: trace-pulse 1.8s ease-in-out infinite; }
        .animate-trace-progress { animation: trace-progress 2s linear infinite; }
      `}</style>
    </div>
  );
}