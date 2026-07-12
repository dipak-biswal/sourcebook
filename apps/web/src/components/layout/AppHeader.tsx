import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Activity,
  Bot,
  ChevronDown,
  Files,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageCircle,
  User,
  X,
} from "lucide-react";
import { getToken, setToken } from "@/api";
import { useMe } from "@/hooks/queries";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { cn } from "@/lib/utils";

type AppHeaderProps = {
  showAuthActions?: boolean;
  onLogout?: () => void;
};

const NAV = [
  { to: "/", label: "Home", icon: LayoutDashboard, match: "/" },
  { to: "/documents", label: "Documents", icon: Files, match: "/documents" },
  { to: "/chat", label: "Chat", icon: MessageCircle, match: "/chat" },
  { to: "/agents", label: "Agents", icon: Bot, match: "/agents" },
  { to: "/usage", label: "Usage", icon: Activity, match: "/usage" },
] as const;

function initialsFromEmail(email: string): string {
  const local = email.split("@")[0] || "?";
  const parts = local.split(/[._\-\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

function UserProfileMenu({ onLogout }: { onLogout?: () => void }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const { data: user } = useMe();

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function handleLogout() {
    setToken(null);
    setOpen(false);
    onLogout?.();
  }

  const email = user?.email || "Account";
  const initials = user?.email ? initialsFromEmail(user.email) : "?";

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="menu"
        className={cn(
          "inline-flex items-center gap-1.5 rounded-[8px] border border-hairline bg-canvas px-1.5 py-1 text-left transition-colors",
          "hover:bg-canvas-soft-2",
          open && "bg-canvas-soft-2 ring-1 ring-hairline",
        )}
      >
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink text-[11px] font-semibold text-[var(--canvas)]">
          {initials}
        </span>
        <span className="hidden min-w-0 max-w-[10rem] flex-col sm:flex">
          <span className="truncate text-[12px] font-medium leading-tight text-ink">
            {email}
          </span>
          <span className="text-[10px] leading-tight text-mute">Session</span>
        </span>
        <ChevronDown
          className={cn(
            "hidden h-3.5 w-3.5 text-mute sm:block",
            open && "rotate-180",
          )}
          strokeWidth={1.5}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-1.5 w-64 overflow-hidden rounded-[10px] border border-hairline bg-canvas shadow-[var(--elevation-card)]"
        >
          <div className="border-b border-hairline bg-canvas-soft px-3 py-3">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink text-xs font-semibold text-[var(--canvas)]">
                {initials}
              </span>
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">
                  {email}
                </div>
                <div className="mt-0.5 flex items-center gap-1 text-[11px] text-mute">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-success-text" />
                  Signed in · active session
                </div>
              </div>
            </div>
          </div>

          <div className="p-1.5">
            <Link
              to="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2 rounded-[6px] px-2.5 py-2 text-[13px] text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
            >
              <User className="h-3.5 w-3.5" strokeWidth={1.5} />
              Settings
            </Link>
            <Link
              to="/usage"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex w-full items-center gap-2 rounded-[6px] px-2.5 py-2 text-[13px] text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
            >
              <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
              Usage
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={handleLogout}
              className="flex w-full items-center gap-2 rounded-[6px] px-2.5 py-2 text-left text-[13px] text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
            >
              <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

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

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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
          to={authed ? "/" : "/login"}
          className="flex min-w-0 items-center gap-2.5"
        >
          <SourcebookIcon size="sm" />
          <span className="truncate font-semibold tracking-tight text-ink">
            Sourcebook
          </span>
        </Link>

        <div className="flex items-center gap-1 sm:gap-1.5">
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
              <UserProfileMenu onLogout={onLogout} />

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
