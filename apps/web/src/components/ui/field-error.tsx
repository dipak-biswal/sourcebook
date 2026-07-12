import { cn } from "@/lib/utils";

export function FieldError({ error, className }: { error?: string | null; className?: string }) {
  if (!error) return null;
  return (
    <p className={cn("mt-1 text-xs text-danger-text", className)} role="alert">
      {error}
    </p>
  );
}
