import { Navigate } from "react-router-dom";
import { getToken } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { DashboardPageProvider, useDashboardPage } from "./DashboardPageContext";
import { DashboardStats } from "./DashboardStats";
import { DashboardQuickActions } from "./DashboardQuickActions";
import { DashboardRecentActivity } from "./DashboardRecentActivity";

function DashboardPageInner() {
  const { userEmail, onLogout } = useDashboardPage();

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

          <div className="mt-8 space-y-8">
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
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <DashboardPageProvider>
      <DashboardPageInner />
    </DashboardPageProvider>
  );
}
