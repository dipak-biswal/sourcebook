import { useState } from "react";
import { AppHeader } from "@/components/layout/AppHeader";
import { ErrorAlert } from "@/components/ui/error-alert";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  Activity,
  LayoutGrid,
  PanelLeft,
  Settings,
  User,
} from "lucide-react";
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
    description: "Topics and call audit per workspace",
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
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-hairline px-3 py-3">
        <div className="text-[10px] font-bold uppercase tracking-wide text-mute">
          Sections
        </div>
        <div className="truncate text-sm font-semibold text-ink">Settings</div>
        <p className="mt-1 text-[10px] text-mute">
          Account, workspaces, and admin tools
        </p>
      </div>
      <nav
        aria-label="Settings sections"
        className="min-h-0 flex-1 overflow-y-auto p-2"
      >
        <ul className="space-y-0.5">
          {TABS.map(({ id, label, description, icon: Icon }) => {
            const isActive = active === id;
            return (
              <li key={id}>
                <button
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onChange(id)}
                  className={cn(
                    "flex w-full items-start gap-2.5 rounded-[8px] px-2.5 py-2 text-left transition-colors",
                    isActive
                      ? "bg-ink font-semibold text-[var(--canvas)]"
                      : "text-body hover:bg-canvas-soft",
                  )}
                >
                  <Icon
                    className={cn(
                      "mt-0.5 h-3.5 w-3.5 shrink-0",
                      isActive ? "text-[var(--canvas)]" : "text-mute",
                    )}
                    strokeWidth={1.5}
                  />
                  <span className="min-w-0">
                    <span className="block text-xs font-semibold leading-snug">
                      {label}
                    </span>
                    <span
                      className={cn(
                        "mt-0.5 block text-[11px] leading-snug",
                        isActive
                          ? "text-[var(--canvas)]/75"
                          : "text-mute",
                      )}
                    >
                      {description}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}

function SettingsPageInner() {
  const { error, onDismissError, onRetryError, onLogout } = useSettingsPage();
  const [tab, setTab] = useState<SettingsTab>("profile");
  const [leftOpen, setLeftOpen] = useState(false);

  const activeTab = TABS.find((t) => t.id === tab) ?? TABS[0];

  function handleSelectTab(next: SettingsTab) {
    setTab(next);
    setLeftOpen(false);
  }

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <div className="flex shrink-0 items-center gap-2 border-b border-hairline bg-canvas px-3 py-2 sm:px-4">
        <Settings className="hidden h-4 w-4 text-mute sm:block" strokeWidth={1.5} />
        <span className="text-sm font-semibold text-ink">Settings</span>
      </div>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 flex-col border-r border-hairline bg-canvas lg:flex">
          <SettingsNav active={tab} onChange={handleSelectTab} />
        </aside>

        <Sheet
          open={leftOpen}
          onClose={() => setLeftOpen(false)}
          title="Settings"
          side="left"
          mobileOnly={false}
        >
          <SettingsNav active={tab} onChange={handleSelectTab} />
        </Sheet>

        <main
          id="main-content"
          tabIndex={-1}
          className="document-scroll flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto outline-none"
        >
          <div className="flex shrink-0 items-center gap-2 border-b border-hairline px-3 py-2 lg:hidden">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Open settings sections"
              onClick={() => setLeftOpen(true)}
            >
              <PanelLeft className="h-4 w-4" strokeWidth={1.5} />
            </Button>
            <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink">
              {activeTab.label}
            </span>
          </div>

          <div className="min-h-0 flex-1 px-4 py-6 sm:px-6 sm:py-8">
            <div
              className={cn(
                "mx-auto w-full",
                tab === "workspace" ? "max-w-5xl" : "max-w-3xl",
              )}
            >
              {error && (
                <ErrorAlert
                  message={error}
                  className="mb-4"
                  onDismiss={onDismissError}
                  onRetry={onRetryError}
                />
              )}

              <div role="tabpanel">
                {tab === "profile" && (
                  <div className="space-y-4">
                    <div className="mb-1">
                      <h2 className="text-sm font-semibold text-ink">
                        User profile
                      </h2>
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
                    <div className="mb-1">
                      <h2 className="text-sm font-semibold text-ink">
                        Workspace
                      </h2>
                      <p className="mt-0.5 text-xs text-mute">
                        Topics and call audit per workspace
                      </p>
                    </div>
                    <SettingsWorkspaces />
                  </div>
                )}

                {tab === "monitoring" && (
                  <div className="space-y-4">
                    <div className="mb-1">
                      <h2 className="text-sm font-semibold text-ink">
                        Monitoring
                      </h2>
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
