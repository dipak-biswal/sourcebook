import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, ChevronRight, Circle, X } from "lucide-react";
import { useOnboardingProgress } from "@/hooks/useOnboardingProgress";
import {
  dismissChecklist,
  isChecklistDismissed,
  type OnboardingStep,
  type OnboardingStepId,
} from "@/lib/onboarding";
import { cn } from "@/lib/utils";

type OnboardingChecklistProps = {
  workspaceId: string;
  variant?: "full" | "compact";
  /** Only show when this step is the active incomplete step */
  whenCurrentStep?: OnboardingStepId;
  /** Only show when the active step is one of these */
  whenCurrentSteps?: OnboardingStepId[];
};

function StepRow({
  step,
  isCurrent,
  compact,
}: {
  step: OnboardingStep;
  isCurrent: boolean;
  compact?: boolean;
}) {
  const Icon = step.done ? Check : Circle;

  return (
    <li
      className={cn(
        "flex items-start gap-2.5",
        compact ? "text-xs" : "text-sm",
        step.done && "text-mute",
        isCurrent && !step.done && "text-ink",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 h-3.5 w-3.5 shrink-0",
          step.done
            ? "text-emerald-600 dark:text-emerald-400"
            : isCurrent
              ? "text-ink"
              : "text-mute/60",
        )}
        strokeWidth={step.done ? 2.5 : 1.5}
        fill={step.done ? "currentColor" : "none"}
      />
      <div className="min-w-0 flex-1">
        <span className={cn(step.done && "line-through decoration-mute/50")}>
          {step.label}
        </span>
        {!compact && (
          <p className="mt-0.5 text-xs text-mute">{step.description}</p>
        )}
      </div>
      {isCurrent && !step.done && (
        <Link
          to={step.href}
          className="inline-flex shrink-0 items-center gap-0.5 text-xs font-medium text-ink underline-offset-2 hover:underline"
        >
          Go
          <ChevronRight className="h-3 w-3" strokeWidth={2} />
        </Link>
      )}
    </li>
  );
}

export function OnboardingChecklist({
  workspaceId,
  variant = "full",
  whenCurrentStep,
  whenCurrentSteps,
}: OnboardingChecklistProps) {
  const { steps, completedCount, totalSteps, isComplete, loading, currentStep } =
    useOnboardingProgress(workspaceId);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    if (!workspaceId) {
      setDismissed(false);
      return;
    }
    setDismissed(isChecklistDismissed(workspaceId));
  }, [workspaceId]);

  const stepAllowed =
    !whenCurrentStep && !whenCurrentSteps
      ? true
      : whenCurrentStep
        ? currentStep?.id === whenCurrentStep
        : whenCurrentSteps
          ? !!currentStep && whenCurrentSteps.includes(currentStep.id)
          : true;

  if (!workspaceId || isComplete || dismissed || !stepAllowed) {
    return null;
  }

  function onDismiss() {
    dismissChecklist(workspaceId);
    setDismissed(true);
  }

  const progressPct = Math.round((completedCount / totalSteps) * 100);
  const compact = variant === "compact";

  if (compact) {
    return (
      <div className="border-b border-hairline bg-canvas-soft px-4 py-3 sm:px-6">
        <div className="mx-auto flex max-w-3xl items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-xs font-semibold text-ink">Getting started</p>
              <span className="text-[11px] text-mute">
                {loading ? "…" : `${completedCount}/${totalSteps}`}
              </span>
            </div>
            {currentStep && (
              <p className="mt-1 text-xs text-body">
                Next:{" "}
                <Link
                  to={currentStep.href}
                  className="font-medium text-ink underline-offset-2 hover:underline"
                >
                  {currentStep.label.toLowerCase()}
                </Link>
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onDismiss}
            className="shrink-0 rounded p-1 text-mute hover:bg-canvas hover:text-ink"
            aria-label="Dismiss checklist"
          >
            <X className="h-3.5 w-3.5" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <section className="rounded-vercel-md border border-hairline bg-canvas p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink">Getting started</h2>
          <p className="mt-1 text-xs text-mute">
            Upload documents, ingest them, then ask grounded questions in Chat.
          </p>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
          aria-label="Dismiss checklist"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>

      <div className="mt-4">
        <div className="mb-1.5 flex items-center justify-between text-[11px] text-mute">
          <span>Progress</span>
          <span>
            {loading ? "Checking…" : `${completedCount} of ${totalSteps} complete`}
          </span>
        </div>
        <div
          className="h-1.5 overflow-hidden rounded-full bg-canvas-soft-2"
          role="progressbar"
          aria-valuenow={completedCount}
          aria-valuemin={0}
          aria-valuemax={totalSteps}
          aria-label="Onboarding progress"
        >
          <div
            className="h-full rounded-full bg-ink transition-all duration-300"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      <ol className="mt-4 space-y-3">
        {steps.map((step) => (
          <StepRow
            key={step.id}
            step={step}
            isCurrent={currentStep?.id === step.id}
          />
        ))}
      </ol>

      {currentStep && (
        <Link
          to={currentStep.href}
          className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-ink underline-offset-2 hover:underline"
        >
          Continue: {currentStep.label}
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
        </Link>
      )}
    </section>
  );
}