import { Navigate } from "react-router-dom";
import { getToken } from "@/api";
import { ChatSessionsPanel } from "@/components/chat/ChatSessionsPanel";
import { ModeTip } from "@/components/chat/ModeTip";
import { AppHeader } from "@/components/layout/AppHeader";
import { Sheet } from "@/components/ui/sheet";
import { ChatPageProvider, useChatPage } from "./ChatPageContext";
import { ChatPageHeader } from "./ChatPageHeader";
import { ChatMessageList } from "./ChatMessageList";
import { ChatInput } from "./ChatInput";

function ChatPageInner() {
  const {
    mode,
    sessionsOpen,
    sessionPanelProps,
    onCloseSessions,
    onLogout,
  } = useChatPage();

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-80 shrink-0 flex-col border-r border-hairline bg-canvas md:flex">
          <ChatSessionsPanel {...sessionPanelProps} />
        </aside>

        <Sheet
          open={sessionsOpen}
          onClose={onCloseSessions}
          title={mode === "agent" ? "Agent sessions" : "Chat sessions"}
          description={
            mode === "agent"
              ? "Agent runs in this workspace"
              : "Chat history in this workspace"
          }
          side="left"
        >
          <ChatSessionsPanel {...sessionPanelProps} />
        </Sheet>

        <main id="main-content" tabIndex={-1} className="flex min-h-0 min-w-0 flex-1 flex-col outline-none">
          <ChatPageHeader />
          <ModeTip />
          <ChatMessageList />
          <ChatInput />
        </main>
      </div>
    </div>
  );
}

export function ChatPage() {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <ChatPageProvider>
      <ChatPageInner />
    </ChatPageProvider>
  );
}
