import { FileText, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

type DocumentsOnboardingProps = {
  onNavigateToChat?: () => void;
  compact?: boolean;
};

export function DocumentsOnboarding({
  onNavigateToChat,
  compact = false,
}: DocumentsOnboardingProps) {
  return (
    <section
      className={
        compact
          ? "border-b border-hairline bg-canvas-soft px-4 py-4"
          : "flex flex-col items-center justify-center px-4 py-10 text-center sm:px-8 sm:py-12"
      }
    >
      <div className={compact ? "mx-auto max-w-lg" : undefined}>
        <div
          className={
            compact
              ? "flex items-start gap-3 text-left"
              : "flex flex-col items-center"
          }
        >
          <div
            className={
              compact
                ? "flex h-9 w-9 shrink-0 items-center justify-center rounded-[6px] bg-canvas-soft-2 text-mute"
                : "flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute"
            }
          >
            <Upload
              className={compact ? "h-4 w-4" : "h-5 w-5"}
              strokeWidth={1.5}
            />
          </div>
          <div className={compact ? "min-w-0 flex-1" : "mt-4"}>
            <h2
              className={
                compact
                  ? "text-sm font-semibold text-ink"
                  : "text-display-sm font-semibold tracking-tight text-ink"
              }
            >
              Get documents ready for chat
            </h2>
            <p
              className={
                compact
                  ? "mt-1 text-xs leading-relaxed text-mute"
                  : "mt-2 max-w-md text-body-sm text-mute"
              }
            >
              Upload <strong className="text-ink">PDF, DOCX, txt/md</strong> or
              other text files below, then tap{" "}
              <strong className="text-ink">Ingest for chat</strong>. Wait for
              status <strong className="text-ink">ready</strong> before asking
              questions in Chat.
            </p>
          </div>
        </div>

        {!compact && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
            {[".pdf", ".docx", ".txt / .md", "Ingest → ready"].map((label) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-canvas px-3 py-1 text-xs text-body"
              >
                <FileText className="h-3.5 w-3.5" strokeWidth={1.5} />
                {label}
              </span>
            ))}
          </div>
        )}

        <ol
          className={
            compact
              ? "mt-3 space-y-1 text-left text-xs text-body"
              : "mt-8 max-w-sm space-y-2 text-left text-body-sm text-body"
          }
        >
          <li className="flex gap-2">
            <span className="font-medium text-ink">1.</span>
            Upload from the list below
          </li>
          <li className="flex gap-2">
            <span className="font-medium text-ink">2.</span>
            Tap <strong>Ingest for chat</strong>
          </li>
          <li className="flex gap-2">
            <span className="font-medium text-ink">3.</span>
            If <strong>failed</strong>, expand the error and retry
          </li>
          <li className="flex gap-2">
            <span className="font-medium text-ink">4.</span>
            Open <strong>Chat</strong> when status is <strong>ready</strong>
          </li>
        </ol>

        {onNavigateToChat && !compact && (
          <Button
            type="button"
            variant="secondary"
            className="mt-8"
            onClick={onNavigateToChat}
          >
            Go to Chat →
          </Button>
        )}
      </div>
    </section>
  );
}