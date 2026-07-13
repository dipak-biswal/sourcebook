import { createContext, useContext } from "react";
import type { DashboardPageContextValue } from "@/types/dashboard";

export const DashboardPageContext = createContext<DashboardPageContextValue | null>(null);

export function useDashboardPage(): DashboardPageContextValue {
  const ctx = useContext(DashboardPageContext);
  if (!ctx) throw new Error("useDashboardPage must be used within DashboardPageProvider");
  return ctx;
}
