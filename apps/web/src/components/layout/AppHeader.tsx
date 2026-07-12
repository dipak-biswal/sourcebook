import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  Files,
  LogOut,
  Menu,
  MessageCircle,
  X,
} from "lucide-react";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { getToken, setToken } from "@/api";
import { cn } from "@/lib/utils";

type AppHeaderProps = {
  showAuthActions?: boolean;
  onLogout?: () => void;
};

const NAV = [
  { to: "/documents", label: "Documents", icon: Files, match: "/documents" },
  { to: "/chat", label: "Chat", icon: MessageCircle, match: "/chat" },
  { to: "/agents", label: "Agents", icon: Bot, match: "/agents" },
  { to: "/usage", label: "Usage", icon: Activity, match: "/usage" },
] as const;

export function AppHeader({
  showAuthActions = true,
  onLogout,
}: AppHeaderProps) {
  const authed = !!getToken();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  function handleLogout() {
    setToken(null);
    setMenuOpen(false);
    onLogout?.();
  }

  function navClass(match: string) {
    const active = location.pathname.startsWith(match);
    return cn(
      "flex items-center gap-1.5 rounded-[6px] px-2.5 py-1.5 text-[13px] font-medium transition-colors",
      active
        ? "bg-canvas-soft-2 text-ink"
        : "text-body hover:bg-canvas-soft-2 hover:text-ink",
    );
  }

  return (
    <header className="sticky top-0 z-40 w-full shrink-0 border-b border-hairline bg-canvas/95 backdrop-blur-sm">
      <div className="flex w-full items-center justify-between gap-3 px-4 py-3 sm:px-6 sm:py-3.5">
        <Link
          to={authed ? "/documents" : "/login"}
          className="flex min-w-0 items-center gap-2.5"
        >
          <SourcebookIcon size="sm" />
          <span className="truncate font-semibold tracking-tight text-ink">
            Sourcebook
          </span>
        </Link>

        <div className="flex items-center gap-0.5 sm:gap-1">
          {/* Desktop nav */}
          {showAuthActions && authed && (
            <nav className="mr-1 hidden items-center gap-0.5 md:flex">
              {NAV.map(({ to, label, icon: Icon, match }) => (
                <Link key={to} to={to} className={navClass(match)}>
                  <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                  {label}
                </Link>
              ))}
            </nav>
          )}

          <ThemeToggle />

          {showAuthActions && authed && (
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleLogout}
                className="hidden gap-1 text-[13px] sm:inline-flex"
              >
                <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
                <span className="hidden lg:inline">Sign out</span>
              </Button>

              {/* Mobile menu toggle */}
              <button
                type="button"
                className="inline-flex items-center justify-center rounded-[6px] p-1.5 text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink md:hidden"
                aria-label={menuOpen ? "Close menu" : "Open menu"}
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((v) => !v)}
              >
                {menuOpen ? (
                  <X className="h-5 w-5" strokeWidth={1.5} />
                ) : (
                  <Menu className="h-5 w-5" strokeWidth={1.5} />
                )}
              </button>
            </>
          )}
        </div>
      </div>

      {/* Mobile drawer */}
      {showAuthActions && authed && menuOpen && (
        <div className="border-t border-hairline bg-canvas px-3 py-2 md:hidden">
          <nav className="flex flex-col gap-0.5">
            {NAV.map(({ to, label, icon: Icon, match }) => (
              <Link
                key={to}
                to={to}
                className={cn(navClass(match), "w-full py-2.5")}
              >
                <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                {label}
              </Link>
            ))}
            <button
              type="button"
              onClick={handleLogout}
              className="mt-1 flex w-full items-center gap-1.5 rounded-[6px] px-2.5 py-2.5 text-left text-[13px] font-medium text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
            >
              <LogOut className="h-4 w-4" strokeWidth={1.5} />
              Sign out
            </button>
          </nav>
        </div>
      )}
    </header>
  );
}
