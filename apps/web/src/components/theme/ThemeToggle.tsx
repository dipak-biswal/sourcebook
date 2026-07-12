import { Moon, Sun } from "lucide-react";
import { useTheme } from "./ThemeProvider";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  return (
    <button
      type="button"
      onClick={toggle}
      className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-[6px] text-mute transition-colors duration-200 hover:bg-canvas-soft-2 hover:text-ink"
      aria-label={
        theme === "light" ? "Switch to dark mode" : "Switch to light mode"
      }
    >
      {/* Fixed-size icon slot so swap never jumps layout */}
      <span className="relative block h-4 w-4">
        <Sun
          className={
            "absolute inset-0 h-4 w-4 transition-all duration-200 ease-out " +
            (theme === "dark"
              ? "scale-100 rotate-0 opacity-100"
              : "scale-75 -rotate-90 opacity-0")
          }
          strokeWidth={1.5}
          aria-hidden
        />
        <Moon
          className={
            "absolute inset-0 h-4 w-4 transition-all duration-200 ease-out " +
            (theme === "light"
              ? "scale-100 rotate-0 opacity-100"
              : "scale-75 rotate-90 opacity-0")
          }
          strokeWidth={1.5}
          aria-hidden
        />
      </span>
    </button>
  );
}
