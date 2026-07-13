import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "animate-pulse rounded-[6px] bg-canvas-soft-2",
        className,
      )}
      aria-hidden
    />
  );
}

/** Sidebar session / run list placeholders */
export function ListSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="space-y-2 p-2" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="rounded-[6px] border border-hairline bg-canvas px-2 py-2"
        >
          <Skeleton className="h-3.5 w-3/4 max-w-[12rem]" />
          <Skeleton className="mt-2 h-2.5 w-1/2 max-w-[8rem]" />
        </div>
      ))}
    </div>
  );
}

/** Chat thread placeholders while session history loads */
export function MessageListSkeleton() {
  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-4" aria-busy="true" aria-label="Loading messages">
      <div className="flex justify-end">
        <Skeleton className="h-10 w-[min(70%,16rem)] rounded-vercel-md" />
      </div>
      <div className="flex justify-start">
        <Skeleton className="h-16 w-[min(80%,20rem)] rounded-vercel-md" />
      </div>
      <div className="flex justify-end">
        <Skeleton className="h-10 w-[min(60%,14rem)] rounded-vercel-md" />
      </div>
      <div className="flex justify-start">
        <Skeleton className="h-20 w-[min(85%,22rem)] rounded-vercel-md" />
      </div>
    </div>
  );
}

export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-vercel-md border border-hairline bg-canvas p-4",
        className,
      )}
      aria-busy="true"
    >
      <Skeleton className="h-3 w-20" />
      <Skeleton className="mt-3 h-7 w-24" />
    </div>
  );
}
