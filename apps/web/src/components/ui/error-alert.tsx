import { Link } from "react-router-dom";
import { RefreshCw, X } from "lucide-react";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { isSessionExpiredMessage } from "@/lib/api-errors";
import { cn } from "@/lib/utils";

type ErrorAlertProps = {
  message: string | null;
  onDismiss?: () => void;
  onRetry?: () => void;
  className?: string;
};

export function ErrorAlert({
  message,
  onDismiss,
  onRetry,
  className,
}: ErrorAlertProps) {
  if (!message) return null;

  const sessionExpired = isSessionExpiredMessage(message);

  return (
    <Alert variant="danger" className={cn("flex items-start gap-3", className)}>
      <div className="min-w-0 flex-1">
        <p className="leading-relaxed">{message}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {sessionExpired ? (
            <Button
              asChild
              type="button"
              variant="secondary"
              size="sm"
              className="h-7 px-2.5 text-xs"
            >
              <Link to="/login">Sign in again</Link>
            </Button>
          ) : (
            onRetry && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="h-7 gap-1 px-2.5 text-xs"
                onClick={onRetry}
              >
                <RefreshCw className="h-3 w-3" strokeWidth={1.5} />
                Retry
              </Button>
            )
          )}
          {onDismiss && (
            <button
              type="button"
              onClick={onDismiss}
              className="text-xs font-medium text-danger-text underline-offset-2 hover:underline"
            >
              Dismiss
            </button>
          )}
        </div>
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="shrink-0 rounded p-1 text-danger-text/70 hover:bg-danger-soft hover:text-danger-text"
          aria-label="Dismiss error"
        >
          <X className="h-3.5 w-3.5" strokeWidth={1.5} />
        </button>
      )}
    </Alert>
  );
}