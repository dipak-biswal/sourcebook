import { Bot, Loader2, MessageCircle, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useChatPage } from "./chat-page-context";

export function ChatInput() {
  const {
    mode,
    workspaceId,
    input,
    sending,
    onSetMode,
    onInputChange,
    onSend,
  } = useChatPage();

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSend(); }}
      className="shrink-0 border-t border-hairline bg-canvas px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-6 sm:py-4"
    >
      <div className="mx-auto max-w-2xl space-y-2">
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-[6px] border border-hairline p-0.5">
            <button
              type="button"
              onClick={() => onSetMode("chat")}
              className={cn(
                "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
                mode === "chat"
                  ? "bg-ink text-[var(--canvas)]"
                  : "text-body hover:bg-canvas-soft-2",
              )}
            >
              <MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
              Chat
            </button>
            <button
              type="button"
              onClick={() => onSetMode("agent")}
              className={cn(
                "flex items-center gap-1.5 rounded-[4px] px-2.5 py-1 text-xs font-medium transition-colors",
                mode === "agent"
                  ? "bg-ink text-[var(--canvas)]"
                  : "text-body hover:bg-canvas-soft-2",
              )}
            >
              <Bot className="h-3.5 w-3.5" strokeWidth={1.5} />
              Agent
            </button>
          </div>
          <span className="hidden text-[11px] text-mute sm:inline">
            {mode === "chat"
              ? "Grounded RAG + citations · ⌘/Ctrl+Enter"
              : "Tools + HITL · ⌘/Ctrl+Enter"}
          </span>
        </div>
        <div className="flex gap-2">
          <Input
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                onSend();
              }
            }}
            placeholder={
              !workspaceId
                ? "Select a workspace first…"
                : mode === "agent"
                  ? "List docs, search, or create a note…"
                  : "Ask a question about your documents…"
            }
            disabled={sending || !workspaceId}
            className="flex-1"
            autoFocus
          />
          <Button
            type="submit"
            disabled={sending || !input.trim() || !workspaceId}
            className="rounded-[6px] px-4"
            title={
              !workspaceId
                ? "Select a workspace first"
                : !input.trim()
                  ? "Type a message"
                  : "Send"
            }
          >
            {sending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" strokeWidth={1.5} />
            )}
            {sending
              ? mode === "agent"
                ? "Tracing…"
                : "Sending…"
              : "Send"}
          </Button>
        </div>
      </div>
    </form>
  );
}
