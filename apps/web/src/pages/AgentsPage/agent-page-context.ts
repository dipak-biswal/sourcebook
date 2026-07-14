import { createContext, useContext } from "react";
import type { AgentPageContextValue } from "@/types/agents";

export const AgentPageContext = createContext<AgentPageContextValue | null>(null);

export function useAgentPage(): AgentPageContextValue {
  const ctx = useContext(AgentPageContext);
  if (!ctx) throw new Error("useAgentPage must be used within AgentPageProvider");
  return ctx;
}
