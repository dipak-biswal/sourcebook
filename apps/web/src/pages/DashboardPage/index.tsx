import { AppHeader } from "@/components/layout/AppHeader";
import { OnboardingChecklist } from "@/components/onboarding/OnboardingChecklist";
import { WorkspaceSelect } from "@/components/workspace/WorkspaceSelect";
import { DashboardPageProvider } from "./DashboardPageContext";
import { useDashboardPage } from "./dashboard-page-context";
import { DashboardStats } from "./DashboardStats";
import { DashboardQuickActions } from "./DashboardQuickActions";
import { DashboardRecentActivity } from "./DashboardRecentActivity";

function DashboardPageInner() {
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
            {userEmail ? `Hi, ${userEmail.split("@")[0]}` : "Welcome"}
          </h1>
          <p className="mt-1.5 text-body-sm text-body">
            Overview of your workspace activity.
          </p>

          {workspaces.length > 0 && (
            <div className="mt-5 max-w-sm">
              <WorkspaceSelect
                workspaces={workspaces}
                workspaceId={workspaceId}
                onChange={onChangeWorkspace}
                onRefresh={onRefreshWorkspaces}
              />
            </div>
          )}

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
