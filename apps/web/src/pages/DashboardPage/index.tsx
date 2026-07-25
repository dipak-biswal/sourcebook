import { Link } from "react-router-dom";
import { AppHeader } from "@/components/layout/AppHeader";
import { OnboardingChecklist } from "@/components/onboarding/OnboardingChecklist";
import { WorkspaceSelect } from "@/components/workspace/WorkspaceSelect";
import { useIsAuthenticated } from "@/hooks/useAuth";
import { DashboardPageProvider } from "./DashboardPageContext";
import { useDashboardPage } from "./dashboard-page-context";
import { DashboardStats } from "./DashboardStats";
import { DashboardQuickActions } from "./DashboardQuickActions";
import { DashboardRecentActivity } from "./DashboardRecentActivity";

function GuestWelcome() {
  return (
    <div className="mt-8 rounded-vercel-md border border-hairline bg-canvas-soft p-6 sm:p-8">
      <h2 className="text-base font-semibold text-ink">
        Your grounded workspace for documents, chat, and agents
      </h2>
      <p className="mt-2 max-w-xl text-sm text-body">
        Sign in to upload sources, ask questions with citations, run agents,
        and keep notes — all in one place.
      </p>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Link
          to="/login"
          className="inline-flex items-center justify-center rounded-[8px] bg-ink px-4 py-2 text-sm font-medium text-[var(--canvas)] transition-opacity hover:opacity-90"
        >
          Sign in
        </Link>
        <span className="text-xs text-mute">
          New here? Create an account from the sign-in page.
        </span>
      </div>
    </div>
  );
}

function DashboardPageInner() {
  const authed = useIsAuthenticated();
  const {
    userEmail,
    workspaces,
    workspaceId,
    onChangeWorkspace,
    onRefreshWorkspaces,
    onLogout,
  } = useDashboardPage();

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <main id="main-content" tabIndex={-1} className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-8 outline-none sm:px-6 sm:py-10">
        <div className="mx-auto max-w-3xl">
          <h1 className="text-display-sm font-semibold tracking-tight text-ink">
            {authed && userEmail
              ? `Hi, ${userEmail.split("@")[0]}`
              : "Welcome to Sourcebook"}
          </h1>
          <p className="mt-1.5 text-body-sm text-body">
            {authed
              ? "Overview of your workspace activity."
              : "Browse the dashboard. Sign in to open your workspaces."}
          </p>

          {!authed && <GuestWelcome />}

          {authed && workspaces.length > 0 && (
            <div className="mt-5 max-w-sm">
              <WorkspaceSelect
                workspaces={workspaces}
                workspaceId={workspaceId}
                onChange={onChangeWorkspace}
                onRefresh={onRefreshWorkspaces}
              />
            </div>
          )}

          {authed && (
            <div className="mt-8 space-y-8">
              {workspaceId && <OnboardingChecklist workspaceId={workspaceId} />}

              <section>
                <h2 className="mb-3 text-sm font-semibold text-ink">At a glance</h2>
                <DashboardStats />
              </section>

              <section>
                <h2 className="mb-3 text-sm font-semibold text-ink">Quick actions</h2>
                <DashboardQuickActions />
              </section>

              <section>
                <h2 className="mb-3 text-sm font-semibold text-ink">Recent activity</h2>
                <DashboardRecentActivity />
              </section>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export function DashboardPage() {
  return (
    <DashboardPageProvider>
      <DashboardPageInner />
    </DashboardPageProvider>
  );
}
