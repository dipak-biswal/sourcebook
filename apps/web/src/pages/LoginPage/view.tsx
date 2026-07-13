import { useState, type FormEvent } from "react";
import type { DevUserList } from "@/api";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FieldError } from "@/components/ui/field-error";
import { Input } from "@/components/ui/input";
import { validateEmail, validatePassword } from "@/lib/validation";

import type { LoginPageViewProps } from "@/types/page-props";

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
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [touched, setTouched] = useState<{ email: boolean; password: boolean }>({ email: false, password: false });

  function setField(field: "email" | "password", value: string, setter: (v: string) => void) {
    setter(value);
    if (touched[field]) {
      const error = field === "email" ? validateEmail(value) : validatePassword(value);
      setFieldErrors((prev) => ({ ...prev, [field]: error ?? undefined }));
    }
  }

  function handleBlur(field: "email" | "password") {
    setTouched((prev) => ({ ...prev, [field]: true }));
    const value = field === "email" ? email : password;
    const error = field === "email" ? validateEmail(value) : validatePassword(value);
    setFieldErrors((prev) => ({ ...prev, [field]: error ?? undefined }));
  }

  function handleSubmit(e: FormEvent, mode: "login" | "register") {
    setTouched({ email: true, password: true });
    const emailError = validateEmail(email);
    const passwordError = validatePassword(password);
    setFieldErrors({ email: emailError ?? undefined, password: passwordError ?? undefined });
    if (emailError || passwordError) {
      e.preventDefault();
      return;
    }
    onSubmit(e, mode);
  }

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
            onSubmit={(e) => handleSubmit(e, "login")}
            noValidate
          >
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-body">
                Email <span className="text-danger-text">*</span>
              </span>
              <Input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setField("email", e.target.value, onEmailChange)}
                onBlur={() => handleBlur("email")}
                aria-invalid={!!fieldErrors.email || undefined}
              />
              <FieldError error={fieldErrors.email} />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-body">
                Password <span className="text-danger-text">*</span>
              </span>
              <Input
                type="password"
                autoComplete="current-password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setField("password", e.target.value, onPasswordChange)}
                onBlur={() => handleBlur("password")}
                aria-invalid={!!fieldErrors.password || undefined}
              />
              <FieldError error={fieldErrors.password} />
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
              onClick={() => handleSubmit({ preventDefault() {} } as FormEvent, "register")}
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
