import { Navigate } from "react-router-dom";
import { getToken } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { User } from "lucide-react";
import { SettingsPageProvider, useSettingsPage } from "./SettingsPageContext";
import { SettingsProfileForm } from "./SettingsProfileForm";
import { SettingsPasswordForm } from "./SettingsPasswordForm";
import { SettingsWorkspaces } from "./SettingsWorkspaces";

function SettingsPageInner() {
  const { error, onLogout } = useSettingsPage();

  return (
    <div className="app-shell">
      <AppHeader onLogout={onLogout} />

      <main id="main-content" tabIndex={-1} className="document-scroll min-h-0 flex-1 overflow-y-auto px-4 py-6 outline-none sm:px-6 sm:py-8">
        <div className="mx-auto max-w-lg">
          <div className="mb-6 flex items-center gap-2">
            <User className="h-5 w-5 text-ink" strokeWidth={1.5} />
            <h1 className="text-display-sm font-semibold tracking-tight text-ink">
              Settings
            </h1>
          </div>

          {error && (
            <Alert variant="danger" className="mb-4">
              {error}
            </Alert>
          )}

          <div className="space-y-6">
            <SettingsProfileForm />
            <SettingsPasswordForm />
            <SettingsWorkspaces />
          </div>
        </div>
      </main>
    </div>
  );
}

export function SettingsPage() {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <SettingsPageProvider>
      <SettingsPageInner />
    </SettingsPageProvider>
  );
}
