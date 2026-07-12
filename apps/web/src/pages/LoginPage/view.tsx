import { type FormEvent } from "react";
import type { DevUserList } from "@/api";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export type LoginPageViewProps = {
  error: string | null;
  busy: boolean;
  devInfo: DevUserList | null;
  devError: string | null;
  devBusy: boolean;
  email: string;
  password: string;
  onEmailChange: (v: string) => void;
  onPasswordChange: (v: string) => void;
  onSubmit: (e: FormEvent, mode: "login" | "register") => void;
  onFillLogin: (email: string, password: string | null) => void;
  onSetPassword: (email: string) => void;
  onSetAllPasswords: () => void;
  onLoadDevUsers: () => void;
};

export function LoginPageView({
  error,
  busy,
  devInfo,
  devError,
  devBusy,
  email,
  password,
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onFillLogin,
  onSetPassword,
  onSetAllPasswords,
  onLoadDevUsers,
}: LoginPageViewProps) {
  return (
    <div className="flex min-h-full flex-col bg-canvas-soft">
      <AppHeader showAuthActions={false} />

      <main id="main-content" tabIndex={-1} className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center px-4 py-10 outline-none sm:px-6 sm:py-14">
        <div className="mb-6 flex flex-col items-center text-center">
          <SourcebookIcon size="lg" />
          <h1 className="mt-5 text-display-sm font-semibold tracking-tight text-ink">
            Sign in to Sourcebook
          </h1>
          <p className="mt-2 max-w-sm text-body-sm text-body">
            Multi-tenant document workspace. Upload sources, then chat with
            grounded answers.
          </p>
        </div>

        <div className="auth-card">
          {error && (
            <Alert variant="danger" className="mb-4">
              {error}
            </Alert>
          )}

          <form
            className="flex flex-col gap-3"
            onSubmit={(e) => onSubmit(e, "login")}
          >
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-body">
                Email
              </span>
              <Input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => onEmailChange(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-body">
                Password
              </span>
              <Input
                type="password"
                autoComplete="current-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => onPasswordChange(e.target.value)}
              />
            </label>

            <Button
              type="submit"
              className="mt-2 w-full"
              disabled={busy}
            >
              {busy ? "Please wait…" : "Continue"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              disabled={busy}
              onClick={(e) => onSubmit(e as unknown as FormEvent, "register")}
            >
              Create account
            </Button>
          </form>

          <p className="mt-5 text-center text-xs leading-relaxed text-mute">
            By continuing you agree to use Sourcebook for your own documents.
          </p>
        </div>

        {devInfo && (
          <section className="mt-8 w-full max-w-3xl rounded-vercel-md border border-warning-border bg-warning-soft p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <Badge variant="warning">DEV ONLY</Badge>
                  <h2 className="text-sm font-semibold text-ink">
                    Test users
                  </h2>
                </div>
                <p className="mt-1 text-xs text-body">{devInfo.warning}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={devBusy}
                  onClick={onLoadDevUsers}
                >
                  Refresh
                </Button>
                <Button
                  type="button"
                  size="sm"
                  className="rounded-[6px]"
                  disabled={devBusy || devInfo.users.length === 0}
                  onClick={onSetAllPasswords}
                >
                  Set all → password123
                </Button>
              </div>
            </div>

            {devError && (
              <Alert variant="danger" className="mt-3">
                {devError}
              </Alert>
            )}

            {devInfo.users.length === 0 ? (
              <p className="mt-4 text-sm text-mute">
                No users yet. Create an account above, then refresh.
              </p>
            ) : (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-hairline text-xs text-mute">
                      <th className="py-2 pr-3 font-medium">Email</th>
                      <th className="py-2 pr-3 font-medium">Test password</th>
                      <th className="py-2 pr-3 font-medium">Note</th>
                      <th className="py-2 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {devInfo.users.map((u) => (
                      <tr
                        key={u.id}
                        className="border-b border-hairline last:border-0"
                      >
                        <td className="py-2.5 pr-3 font-medium text-ink">
                          {u.email}
                        </td>
                        <td className="py-2.5 pr-3 font-mono text-body">
                          {u.test_password ?? "—"}
                        </td>
                        <td className="max-w-[200px] py-2.5 pr-3 text-xs text-mute">
                          {u.password_note}
                        </td>
                        <td className="py-2.5">
                          <div className="flex flex-wrap gap-1.5">
                            <Button
                              type="button"
                              variant="secondary"
                              size="sm"
                              disabled={devBusy}
                              onClick={() =>
                                onFillLogin(u.email, u.test_password)
                              }
                            >
                              Fill
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              className="rounded-[6px]"
                              disabled={devBusy}
                              onClick={() => void onSetPassword(u.email)}
                            >
                              Set password123
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}
