import { cn } from "@/lib/utils";

export function TypingIndicator({ className }: { className?: string }) {
  return (
    <div
      className={cn("flex items-center gap-1 py-0.5", className)}
      role="status"
      aria-label="Assistant is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-pulse rounded-full bg-mute"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}