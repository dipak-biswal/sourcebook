import { PanelLeft, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatPage } from "./chat-page-context";

export function ChatPageHeader() {
  const {
    title,
    subtitle,
    showDelete,
    showClear,
    active,
    onDeleteSession,
    onNewAgent,
    onToggleSessions,
  } = useChatPage();

  return (
    <div className="flex shrink-0 items-center justify-between gap-3 border-b border-hairline bg-canvas px-4 py-3 sm:px-6">
      <div className="flex min-w-0 items-start gap-2">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="mt-0.5 shrink-0 md:hidden"
          aria-label="Open sessions"
          onClick={onToggleSessions}
        >
          <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
        </Button>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-ink">
            {title}
          </div>
          <div className="text-xs text-mute">
            {subtitle}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {showDelete && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => active && onDeleteSession(active.id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Delete</span>
          </Button>
        )}
        {showClear && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onNewAgent}
          >
            Clear
          </Button>
        )}
      </div>
    </div>
  );
}
