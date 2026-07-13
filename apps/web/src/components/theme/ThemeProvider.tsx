import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ThemeContext, type Theme } from "./theme-context";

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

const THEME_TRANSITION_MS = 280;

function applyTheme(theme: Theme) {
  const root = document.documentElement;

  const paint = () => {
    root.setAttribute("data-theme", theme);
    root.style.colorScheme = theme;
  };

  // Smooth cross-fade where supported (Chrome/Edge/Safari recent)
  const doc = document as Document & {
    startViewTransition?: (cb: () => void) => { finished: Promise<void> };
  };

  if (typeof doc.startViewTransition === "function") {
    try {
      doc.startViewTransition(paint);
      return;
    } catch {
      /* fall through */
    }
  }

  // Fallback: brief CSS transitions on color properties only while switching
  root.classList.add("theme-changing");
  paint();
  window.setTimeout(() => {
    root.classList.remove("theme-changing");
  }, THEME_TRANSITION_MS);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    if (typeof window === "undefined") return "light";
    const stored = localStorage.getItem("theme");
    if (stored === "dark" || stored === "light") return stored;
    return systemTheme();
  });
  const [followsSystem, setFollowsSystem] = useState(() => {
    if (typeof window === "undefined") return true;
    const stored = localStorage.getItem("theme");
    return stored !== "dark" && stored !== "light";
  });

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  // Follow OS when user has not chosen manually
  useEffect(() => {
    if (!followsSystem) return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      const next = mq.matches ? "dark" : "light";
      setThemeState(next);
      applyTheme(next);
    };

    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [followsSystem]);

  const setTheme = useCallback((next: Theme | "system") => {
    if (next === "system") {
      localStorage.removeItem("theme");
      setFollowsSystem(true);
      const resolved = systemTheme();
      setThemeState(resolved);
      applyTheme(resolved);
      return;
    }
    localStorage.setItem("theme", next);
    setFollowsSystem(false);
    setThemeState(next);
    applyTheme(next);
  }, []);

  const toggle = useCallback(() => {
    setTheme(theme === "light" ? "dark" : "light");
  }, [setTheme, theme]);

  const value = useMemo(
    () => ({ theme, followsSystem, toggle, setTheme }),
    [theme, followsSystem, toggle, setTheme],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}
