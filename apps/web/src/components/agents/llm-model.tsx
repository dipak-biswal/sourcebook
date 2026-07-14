import { Brain } from "lucide-react";
import { cn } from "@/lib/utils";

export type LlmProvider =
  | "openai"
  | "anthropic"
  | "google"
  | "xai"
  | "meta"
  | "unknown";

export function resolveLlmProvider(model: string): LlmProvider {
  const m = model.toLowerCase();
  if (
    m.includes("gpt")
    || m.includes("o1-")
    || m.includes("o3-")
    || m.includes("o4-")
    || m.startsWith("chatgpt")
  ) {
    return "openai";
  }
  if (m.includes("claude")) return "anthropic";
  if (m.includes("gemini")) return "google";
  if (m.includes("grok")) return "xai";
  if (m.includes("llama")) return "meta";
  return "unknown";
}

function OpenAiLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023-.141-.085-4.774-2.758a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365 2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"
      />
    </svg>
  );
}

function AnthropicLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M13.827 3.52h3.603L24 20.48h-4.395l-1.114-3.09h-5.52l-1.09 3.09H7.38L13.827 3.52zm.39 11.79 1.805-5.01-1.805-5.01h-.03l-1.8 5.01h3.63zM5.1 3.52h3.75L2.25 20.48H0L5.1 3.52z"
      />
    </svg>
  );
}

function GoogleLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
    </svg>
  );
}

function XaiLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M3 3h4.5l5.2 7.1L17.7 3H21l-7.8 10.5L21 21h-4.5l-5.5-7.5L6.3 21H3l8-10.7L3 3z"
      />
    </svg>
  );
}

function MetaLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path
        fill="currentColor"
        d="M12 2c-2.8 3.5-4.6 6.7-4.6 10.2 0 2.2 1.2 3.9 3 3.9 1.6 0 2.5-1.1 3.6-3.6.9 2.3 1.7 3.6 3.5 3.6 1.8 0 3-1.7 3-3.9C20.6 8.7 18.8 5.5 16 2c-1.2 1.5-2 3-2.4 4.2C13.2 5 12.4 3.5 12 2z"
      />
    </svg>
  );
}

export function LlmProviderLogo({
  provider,
  className,
}: {
  provider: LlmProvider;
  className?: string;
}) {
  const cls = cn("shrink-0", className);
  switch (provider) {
    case "openai":
      return <OpenAiLogo className={cls} />;
    case "anthropic":
      return <AnthropicLogo className={cls} />;
    case "google":
      return <GoogleLogo className={cls} />;
    case "xai":
      return <XaiLogo className={cls} />;
    case "meta":
      return <MetaLogo className={cls} />;
    default:
      return <Brain className={cn(cls, "text-mute")} strokeWidth={2} />;
  }
}

export function LlmModelBadge({
  model,
  className,
  compact,
}: {
  model?: string | null;
  className?: string;
  compact?: boolean;
}) {
  if (!model?.trim()) return null;
  const provider = resolveLlmProvider(model);
  return (
    <span
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-[4px] border border-hairline bg-canvas-soft/60 px-1.5 py-0.5",
        className,
      )}
      title={model}
    >
      <LlmProviderLogo provider={provider} className="h-3 w-3" />
      {!compact && (
        <span className="truncate font-mono text-[10px] text-mute">{model}</span>
      )}
    </span>
  );
}