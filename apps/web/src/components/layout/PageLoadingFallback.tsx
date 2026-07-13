import { Loader2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

/** Shown while lazy route chunks load — matches app-shell layout. */
export function PageLoadingFallback() {
  return (
    <div className="app-shell" aria-busy="true" aria-label="Loading page">
      <div className="flex h-[53px] shrink-0 items-center justify-between border-b border-hairline px-4 sm:px-6">
        <div className="flex items-center gap-2.5">
          <Skeleton className="h-7 w-7 rounded-[6px]" />
          <Skeleton className="h-4 w-24" />
        </div>
        <Skeleton className="h-8 w-20" />
      </div>
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-8">
        <Loader2 className="h-6 w-6 animate-spin text-mute" strokeWidth={1.5} />
        <p className="text-sm text-mute">Loading…</p>
      </div>
    </div>
  );
}