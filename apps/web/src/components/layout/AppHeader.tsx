import { Link } from "react-router-dom";
import { LogOut } from "lucide-react";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { ThemeToggle } from "@/components/theme/ThemeToggle";
import { Button } from "@/components/ui/button";
import { getToken, setToken } from "@/api";

type AppHeaderProps = {
  showAuthActions?: boolean;
  onLogout?: () => void;
};

export function AppHeader({
  showAuthActions = true,
  onLogout,
}: AppHeaderProps) {
  const authed = !!getToken();

  function handleLogout() {
    setToken(null);
    onLogout?.();
  }

  return (
    <header className="flex w-full shrink-0 items-center justify-between border-b border-hairline bg-canvas px-6 py-4">
      <Link to={authed ? "/documents" : "/login"} className="flex items-center gap-2.5">
        <SourcebookIcon size="sm" />
        <span className="font-semibold text-ink">Sourcebook</span>
      </Link>

      <div className="flex items-center gap-1">
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
