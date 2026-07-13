import { createContext, useContext } from "react";

export type Theme = "light" | "dark";

export type ThemeContextValue = {
  theme: Theme;
  /** true when following OS preference (no manual override stored) */
  followsSystem: boolean;
  toggle: () => void;
  setTheme: (theme: Theme | "system") => void;
};

export const ThemeContext = createContext<ThemeContextValue>({
  theme: "light",
  followsSystem: true,
  toggle: () => {},
  setTheme: () => {},
});

export function useTheme() {
  return useContext(ThemeContext);
}
