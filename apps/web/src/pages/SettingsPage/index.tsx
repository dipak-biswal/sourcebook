import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorAlert } from "@/components/ui/error-alert";
import { cn } from "@/lib/utils";
import { Activity, LayoutGrid, Settings, User } from "lucide-react";
import { SettingsPageProvider } from "./SettingsPageContext";
import { useSettingsPage } from "./settings-page-context";
import { SettingsProfileForm } from "./SettingsProfileForm";
import { SettingsPasswordForm } from "./SettingsPasswordForm";
import { SettingsWorkspaces } from "./SettingsWorkspaces";
import { SettingsMonitoring } from "./SettingsMonitoring";

type SettingsTab = "profile" | "workspace" | "monitoring";

const TABS: {
  id: SettingsTab;
  label: string;
  description: string;
  icon: typeof User;
}[] = [
  {
    id: "profile",
    label: "User profile",
    description: "Email and password",
    icon: User,
  },
  {
    id: "workspace",
    label: "Workspace",
    description: "Create and manage workspaces",
    icon: LayoutGrid,
  },
  {
    id: "monitoring",
    label: "Monitoring",
    description: "Online users and activity",
    icon: Activity,
  },
];

function SettingsNav({
  active,
  onChange,
}: {
  active: SettingsTab;
  onChange: (tab: SettingsTab) => void;
}) {
  return (
    <nav
      aria-label="Settings sections"
      className="flex shrink-0 gap-1 overflow-x-auto sm:w-52 sm:flex-col sm:gap-0.5 sm:overflow-visible"
    >
      {TABS.map(({ id, label, description, icon: Icon }) => {
        const isActive = active === id;
        return (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(id)}
            className={cn(
              "flex min-w-[9.5rem] items-start gap-2.5 rounded-[8px] border px-3 py-2.5 text-left transition-colors sm:min-w-0 sm:w-full",
              isActive
                ? "border-hairline bg-canvas-soft text-ink shadow-sm"
                : "border-transparent text-body hover:bg-canvas-soft-2 hover:text-ink",
            )}
          >
            <Icon
              className={cn(
                "mt-0.5 h-4 w-4 shrink-0",
                isActive ? "text-ink" : "text-mute",
              )}
              strokeWidth={1.5}
            />
            <span className="min-w-0">
              <span className="block text-sm font-medium leading-tight">
                {label}
              </span>
              <span className="mt-0.5 hidden text-[11px] leading-snug text-mute sm:block">
                {description}
              </span>
            </span>
          </button>
        );
      })}
    </nav>
  );
}

function SettingsPageInner() {
  const { error, onDismissError, onRetryError, onLogout } = useSettingsPage();
  const [tab, setTab] = useState<SettingsTab>("profile");

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <main
        id="main-content"
        tabIndex={-1}
        className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-6 outline-none sm:px-6 sm:py-8"
      >
        <div className="mx-auto w-full max-w-3xl">
          <div className="mb-6 flex items-center gap-2">
            <Settings className="h-5 w-5 text-ink" strokeWidth={1.5} />
            <h1 className="text-display-sm font-semibold tracking-tight text-ink">
              Settings
            </h1>
          </div>

          {error && (
            <ErrorAlert
              message={error}
              className="mb-4"
              onDismiss={onDismissError}
              onRetry={onRetryError}
            />
          )}

          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-8">
            <SettingsNav active={tab} onChange={setTab} />

            <div className="min-w-0 flex-1" role="tabpanel">
              {tab === "profile" && (
                <div className="space-y-4">
                  <div className="mb-1 sm:hidden">
                    <h2 className="text-sm font-semibold text-ink">User profile</h2>
                    <p className="mt-0.5 text-xs text-mute">
                      Email and password
                    </p>
                  </div>
                  <SettingsProfileForm />
                  <SettingsPasswordForm />
                </div>
              )}

              {tab === "workspace" && (
                <div className="space-y-4">
                  <div className="mb-1 sm:hidden">
                    <h2 className="text-sm font-semibold text-ink">Workspace</h2>
                    <p className="mt-0.5 text-xs text-mute">
                      Create and manage workspaces
                    </p>
                  </div>
                  <SettingsWorkspaces />
                </div>
              )}

              {tab === "monitoring" && (
                <div className="space-y-4">
                  <div className="mb-1 sm:hidden">
                    <h2 className="text-sm font-semibold text-ink">Monitoring</h2>
                    <p className="mt-0.5 text-xs text-mute">
                      Online users and activity
                    </p>
                  </div>
                  <SettingsMonitoring />
                </div>
              )}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export function SettingsPage() {
  return (
    <SettingsPageProvider>
      <SettingsPageInner />
    </SettingsPageProvider>
  );
}
