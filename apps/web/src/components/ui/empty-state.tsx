import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

type EmptyStateProps = {
  icon: LucideIcon;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
  children?: React.ReactNode;
};

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className,
  children,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex h-full min-h-[12rem] flex-col items-center justify-center px-4 py-10 text-center",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-vercel-md bg-canvas-soft-2 text-mute">
        <Icon className="h-5 w-5" strokeWidth={1.5} />
      </div>
      <h2 className="mt-4 text-display-sm font-semibold tracking-tight text-ink">
        {title}
      </h2>
      <p className="mt-2 max-w-md text-body-sm text-mute">{description}</p>
      {children}
      {actionLabel && onAction && (
        <Button
          type="button"
          variant="secondary"
          className="mt-6"
          onClick={onAction}
        >
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
