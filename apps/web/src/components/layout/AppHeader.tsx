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
  StickyNote,
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

const PRIMARY_NAV = [
  { to: "/chat", label: "Chat", icon: MessageCircle, match: "/chat" },
  { to: "/agents", label: "Agents", icon: Bot, match: "/agents" },
  { to: "/documents", label: "Documents", icon: Files, match: "/documents" },
  { to: "/notes", label: "Notes", icon: StickyNote, match: "/notes" },
] as const;

const MORE_NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, match: "/" },
  { to: "/usage", label: "Usage", icon: Activity, match: "/usage" },
  { to: "/settings", label: "Settings", icon: User, match: "/settings" },
] as const;

function initialsFromEmail(email: string): string {
  const local = email.split("@")[0] || "?";
  const parts = local.split(/[._\-\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

function UserAvatar({ email, size = "sm" }: { email: string; size?: "sm" | "md" }) {
  const initials = initialsFromEmail(email);
  return (
    <span
      className={cn(
        "flex shrink-0 items-center justify-center rounded-full bg-ink font-semibold text-[var(--canvas)]",
        size === "sm" ? "h-7 w-7 text-[11px]" : "h-9 w-9 text-xs",
      )}
    >
      {initials}
    </span>
  );
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

  return (
    <div className="relative hidden md:block" ref={rootRef}>
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
        <UserAvatar email={email} />
        <span className="flex min-w-0 max-w-[10rem] flex-col">
          <span className="truncate text-[12px] font-medium leading-tight text-ink">
            {email}
          </span>
          <span className="text-[10px] leading-tight text-mute">Account</span>
        </span>
        <ChevronDown
          className={cn("h-3.5 w-3.5 text-mute", open && "rotate-180")}
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
              <UserAvatar email={email} size="md" />
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-ink">
                  {email}
                </div>
                <div className="mt-0.5 flex items-center gap-1 text-[11px] text-mute">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-success-text" />
                  Signed in
                </div>
              </div>
            </div>
          </div>

          <div className="p-1.5">
            {MORE_NAV.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex w-full items-center gap-2 rounded-[6px] px-2.5 py-2 text-[13px] text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
              >
                <Icon className="h-3.5 w-3.5" strokeWidth={1.5} />
                {label}
              </Link>
            ))}
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

function MobileNavLink({
  to,
  label,
  icon: Icon,
  match,
  onNavigate,
}: {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
  match: string;
  onNavigate: () => void;
}) {
  const location = useLocation();
  const active =
    match === "/"
      ? location.pathname === "/"
      : location.pathname.startsWith(match);

  return (
    <Link
      to={to}
      onClick={onNavigate}
      className={cn(
        "flex w-full items-center gap-3 rounded-[8px] px-3 py-2.5 text-[14px] font-medium transition-colors",
        active
          ? "bg-canvas-soft-2 text-ink"
          : "text-body hover:bg-canvas-soft-2 hover:text-ink",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" strokeWidth={1.5} />
      {label}
    </Link>
  );
}

function MobileNavMenu({
  open,
  onClose,
  onLogout,
}: {
  open: boolean;
  onClose: () => void;
  onLogout?: () => void;
}) {
  const { data: user } = useMe();
  const email = user?.email || "Account";

  if (!open) return null;

  function handleLogout() {
    setToken(null);
    onClose();
    onLogout?.();
  }

  return (
    <div className="border-t border-hairline bg-canvas md:hidden">
      <div className="flex items-center gap-3 border-b border-hairline px-4 py-3">
        <UserAvatar email={email} size="md" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-semibold text-ink">{email}</div>
          <div className="text-xs text-mute">Signed in</div>
        </div>
      </div>

      <div className="document-scroll max-h-[min(70vh,28rem)] overflow-y-auto px-3 py-3">
        <p className="px-3 pb-1 text-[10px] font-medium uppercase tracking-wide text-mute">
          Main
        </p>
        <nav className="flex flex-col gap-0.5">
          {PRIMARY_NAV.map((item) => (
            <MobileNavLink key={item.to} {...item} onNavigate={onClose} />
          ))}
        </nav>

        <p className="mt-4 px-3 pb-1 text-[10px] font-medium uppercase tracking-wide text-mute">
          More
        </p>
        <nav className="flex flex-col gap-0.5">
          {MORE_NAV.map((item) => (
            <MobileNavLink key={item.to} {...item} onNavigate={onClose} />
          ))}
        </nav>

        <div className="mt-4 flex items-center justify-between rounded-[8px] border border-hairline px-3 py-2.5">
          <span className="text-sm font-medium text-ink">Theme</span>
          <ThemeToggle />
        </div>

        <button
          type="button"
          onClick={handleLogout}
          className="mt-3 flex w-full items-center gap-3 rounded-[8px] px-3 py-2.5 text-left text-[14px] font-medium text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink"
        >
          <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.5} />
          Sign out
        </button>
      </div>
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
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  function navClass(match: string) {
    const active =
      match === "/"
        ? location.pathname === "/"
        : location.pathname.startsWith(match);
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
            <nav className="mr-1 hidden items-center gap-0.5 md:flex" aria-label="Main">
              {PRIMARY_NAV.map(({ to, label, icon: Icon, match }) => (
                <Link
                  key={to}
                  to={to}
                  className={navClass(match)}
                  title={label}
                  aria-label={label}
                >
                  <Icon className="h-3.5 w-3.5 shrink-0" strokeWidth={1.5} />
                  <span className="hidden lg:inline">{label}</span>
                </Link>
              ))}
            </nav>
          )}

          <div className="hidden md:block">
            <ThemeToggle />
          </div>

          {showAuthActions && authed && (
            <>
              <UserProfileMenu onLogout={onLogout} />

              <button
                type="button"
                className="inline-flex h-9 w-9 items-center justify-center rounded-[8px] border border-hairline text-body transition-colors hover:bg-canvas-soft-2 hover:text-ink md:hidden"
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

      {showAuthActions && authed && (
        <MobileNavMenu
          open={menuOpen}
          onClose={() => setMenuOpen(false)}
          onLogout={onLogout}
        />
      )}
    </header>
  );
}