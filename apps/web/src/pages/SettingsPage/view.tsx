import { type FormEvent } from "react";
import {
  KeyRound,
  LayoutGrid,
  Loader2,
  Mail,
  Pen,
  Plus,
  Save,
  Trash2,
  User,
} from "lucide-react";
import type { Workspace } from "@/api";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type SettingsPageViewProps = {
  email: string;
  error: string | null;
  savingProfile: boolean;
  savingPassword: boolean;
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
  workspaces: Workspace[];
  newWsName: string;
  creatingWs: boolean;
  renamingId: string | null;
  renameValue: string;
  savingRename: boolean;
  onEmailChange: (v: string) => void;
  onUpdateProfile: (e: FormEvent) => void;
  onCurrentPasswordChange: (v: string) => void;
  onNewPasswordChange: (v: string) => void;
  onConfirmPasswordChange: (v: string) => void;
  onChangePassword: (e: FormEvent) => void;
  onNewWsNameChange: (v: string) => void;
  onCreateWorkspace: () => void;
  onStartRename: (id: string, name: string) => void;
  onRenameValueChange: (v: string) => void;
  onCancelRename: () => void;
  onSaveRename: (id: string) => void;
  onDeleteWorkspace: (id: string) => void;
  onLogout: () => void;
};

export function SettingsPageView({
  email,
  error,
  savingProfile,
  savingPassword,
  currentPassword,
  newPassword,
  confirmPassword,
  workspaces,
  newWsName,
  creatingWs,
  renamingId,
  renameValue,
  savingRename,
  onEmailChange,
  onUpdateProfile,
  onCurrentPasswordChange,
  onNewPasswordChange,
  onConfirmPasswordChange,
  onChangePassword,
  onNewWsNameChange,
  onCreateWorkspace,
  onStartRename,
  onRenameValueChange,
  onCancelRename,
  onSaveRename,
  onDeleteWorkspace,
  onLogout,
}: SettingsPageViewProps) {
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
            <form
              onSubmit={onUpdateProfile}
              className="rounded-vercel-md border border-hairline bg-canvas p-4"
            >
              <h2 className="text-sm font-semibold text-ink">Profile</h2>
              <p className="mt-1 text-xs text-mute">
                Update your email address.
              </p>

              <label className="mt-3 block">
                <span className="mb-1 flex items-center gap-1 text-xs text-mute">
                  <Mail className="h-3 w-3" strokeWidth={1.5} />
                  Email
                </span>
                <Input
                  value={email}
                  onChange={(e) => onEmailChange(e.target.value)}
                  type="email"
                  placeholder="you@example.com"
                />
              </label>

              <Button
                type="submit"
                className="mt-3 rounded-[6px]"
                disabled={savingProfile || !email.trim()}
              >
                {savingProfile ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Save className="h-4 w-4" strokeWidth={1.5} />
                )}
                Save
              </Button>
            </form>

            <form
              onSubmit={onChangePassword}
              className="rounded-vercel-md border border-hairline bg-canvas p-4"
            >
              <h2 className="text-sm font-semibold text-ink">Change password</h2>
              <p className="mt-1 text-xs text-mute">
                Enter your current password and a new one.
              </p>

              <label className="mt-3 block">
                <span className="mb-1 flex items-center gap-1 text-xs text-mute">
                  <KeyRound className="h-3 w-3" strokeWidth={1.5} />
                  Current password
                </span>
                <Input
                  value={currentPassword}
                  onChange={(e) => onCurrentPasswordChange(e.target.value)}
                  type="password"
                  placeholder="Current password"
                />
              </label>

              <label className="mt-3 block">
                <span className="mb-1 text-xs text-mute">New password</span>
                <Input
                  value={newPassword}
                  onChange={(e) => onNewPasswordChange(e.target.value)}
                  type="password"
                  placeholder="New password (min 8 chars)"
                />
              </label>

              <label className="mt-3 block">
                <span className="mb-1 text-xs text-mute">Confirm new password</span>
                <Input
                  value={confirmPassword}
                  onChange={(e) => onConfirmPasswordChange(e.target.value)}
                  type="password"
                  placeholder="Confirm new password"
                />
              </label>

              <Button
                type="submit"
                className="mt-3 rounded-[6px]"
                disabled={savingPassword || !currentPassword || !newPassword || !confirmPassword}
              >
                {savingPassword ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <KeyRound className="h-4 w-4" strokeWidth={1.5} />
                )}
                Change password
              </Button>
            </form>

            <div className="rounded-vercel-md border border-hairline bg-canvas p-4">
              <h2 className="text-sm font-semibold text-ink">Workspaces</h2>
              <p className="mt-1 text-xs text-mute">
                Create, rename, or delete workspaces. Deleting removes all associated data.
              </p>

              <div className="mt-3 flex gap-1">
                <Input
                  value={newWsName}
                  onChange={(e) => onNewWsNameChange(e.target.value)}
                  placeholder="New workspace name…"
                  className="h-8 text-xs"
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); onCreateWorkspace(); }
                  }}
                />
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="h-8 shrink-0"
                  disabled={!newWsName.trim() || creatingWs}
                  onClick={onCreateWorkspace}
                >
                  {creatingWs ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Plus className="h-3.5 w-3.5" strokeWidth={1.5} />
                  )}
                  Create
                </Button>
              </div>

              <div className="mt-3 space-y-1">
                {workspaces.length === 0 ? (
                  <p className="text-xs text-mute">No workspaces.</p>
                ) : (
                  workspaces.map((ws) => (
                    <div
                      key={ws.id}
                      className="flex items-center gap-2 rounded-[6px] border border-hairline px-3 py-2"
                    >
                      <LayoutGrid className="h-3.5 w-3.5 shrink-0 text-mute" strokeWidth={1.5} />
                      {renamingId === ws.id ? (
                        <div className="flex flex-1 items-center gap-1">
                          <Input
                            value={renameValue}
                            onChange={(e) => onRenameValueChange(e.target.value)}
                            className="h-7 flex-1 text-xs"
                            autoFocus
                            onKeyDown={(e) => {
                              if (e.key === "Enter") { e.preventDefault(); onSaveRename(ws.id); }
                              if (e.key === "Escape") { onCancelRename(); }
                            }}
                          />
                          <Button
                            type="button"
                            variant="secondary"
                            size="icon"
                            className="h-7 w-7"
                            disabled={!renameValue.trim() || savingRename}
                            onClick={() => onSaveRename(ws.id)}
                          >
                            {savingRename ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Save className="h-3 w-3" strokeWidth={1.5} />
                            )}
                          </Button>
                        </div>
                      ) : (
                        <>
                          <span className="min-w-0 flex-1 truncate text-sm text-ink">
                            {ws.name}
                          </span>
                          <span className="text-[10px] uppercase text-mute">{ws.role}</span>
                          {ws.role === "owner" && (
                            <>
                              <button
                                type="button"
                                className="rounded p-1 text-mute hover:bg-canvas-soft-2 hover:text-ink"
                                title="Rename"
                                onClick={() => onStartRename(ws.id, ws.name)}
                              >
                                <Pen className="h-3 w-3" strokeWidth={1.5} />
                              </button>
                              <button
                                type="button"
                                className="rounded p-1 text-mute hover:bg-danger-soft hover:text-danger-text"
                                title="Delete workspace"
                                onClick={() => onDeleteWorkspace(ws.id)}
                              >
                                <Trash2 className="h-3 w-3" strokeWidth={1.5} />
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
