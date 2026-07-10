import { Link, useLocation } from "react-router-dom";
import { Activity, Files, LogOut, MessageCircle } from "lucide-react";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { getToken, setToken } from "@/api";
import { cn } from "@/lib/utils";

type AppHeaderProps = {
  showAuthActions?: boolean;
  onLogout?: () => void;
};

export function AppHeader({
  showAuthActions = true,
  onLogout,
}: AppHeaderProps) {
  const authed = !!getToken();
  const location = useLocation();

  function handleLogout() {
    setToken(null);
    onLogout?.();
  }

  return (
    <header className="flex w-full shrink-0 items-center justify-between border-b border-hairline bg-canvas px-6 py-4">
      <Link
        to={authed ? "/documents" : "/login"}
        className="flex items-center gap-2.5"
      >
        <SourcebookIcon size="sm" />
        <span className="font-semibold text-ink">Sourcebook</span>
      </Link>

      <div className="flex items-center gap-1">
        {showAuthActions && authed && (
          <>
            <Link
              to="/documents"
              className={cn(
                "flex items-center gap-1.5 rounded-[6px] px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                location.pathname.startsWith("/documents")
                  ? "bg-canvas-soft-2 text-ink"
                  : "text-body hover:bg-canvas-soft-2 hover:text-ink",
              )}
            >
              <Files className="h-3.5 w-3.5" strokeWidth={1.5} />
              Documents
            </Link>
            <Link
              to="/chat"
              className={cn(
                "flex items-center gap-1.5 rounded-[6px] px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                location.pathname.startsWith("/chat")
                  ? "bg-canvas-soft-2 text-ink"
                  : "text-body hover:bg-canvas-soft-2 hover:text-ink",
              )}
            >
              <MessageCircle className="h-3.5 w-3.5" strokeWidth={1.5} />
              Chat
            </Link>
            <Link
              to="/usage"
              className={cn(
                "flex items-center gap-1.5 rounded-[6px] px-2.5 py-1.5 text-[13px] font-medium transition-colors",
                location.pathname.startsWith("/usage")
                  ? "bg-canvas-soft-2 text-ink"
                  : "text-body hover:bg-canvas-soft-2 hover:text-ink",
              )}
            >
              <Activity className="h-3.5 w-3.5" strokeWidth={1.5} />
              Usage
            </Link>
          </>
        )}
        <ThemeToggle />
        {showAuthActions && authed && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            className="gap-1 text-[13px]"
          >
            <LogOut className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span className="hidden sm:inline">Sign out</span>
          </Button>
        )}
      </div>
    </header>
  );
}
