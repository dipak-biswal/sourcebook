import { createContext, useContext } from "react";
import type { ChatPageContextValue } from "@/types/chat";

export const ChatPageContext = createContext<ChatPageContextValue | null>(null);

export function useChatPage(): ChatPageContextValue {
  const ctx = useContext(ChatPageContext);
  if (!ctx) throw new Error("useChatPage must be used within ChatPageProvider");
  return ctx;
}
