import { createContext, useContext } from "react";
import type { SettingsPageContextValue } from "@/types/settings";

export const SettingsPageContext = createContext<SettingsPageContextValue | null>(null);

export function useSettingsPage(): SettingsPageContextValue {
  const ctx = useContext(SettingsPageContext);
  if (!ctx) throw new Error("useSettingsPage must be used within SettingsPageProvider");
  return ctx;
}
