import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "@/api";
import { SourcebookIcon } from "@/components/branding/SourcebookIcon";
import { AppHeader } from "@/components/layout/AppHeader";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { formatError } from "@/lib/utils";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (getToken()) {
    return <Navigate to="/documents" replace />;
  }

  async function submit(e: FormEvent, mode: "login" | "register") {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res =
        mode === "login"
          ? await api.login(email, password)
          : await api.register(email, password);
      setToken(res.access_token);
      navigate("/documents", { replace: true });
    } catch (err) {
      setError(formatError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col bg-canvas-soft">
      <AppHeader showAuthActions={false} />

      <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center px-6 py-12">
        <SourcebookIcon size="lg" />
        <h1 className="mt-6 text-display-sm font-semibold text-ink">
          Sign in to Sourcebook
        </h1>
        <p className="mt-2 text-center text-body-sm text-body">
          Multi-tenant document workspace. Upload sources, then chat with
          grounded answers.
        </p>

        {error && (
          <Alert variant="danger" className="mt-4 w-full">
            {error}
          </Alert>
        )}

        <form
          className="mt-8 flex w-full flex-col gap-3"
          onSubmit={(e) => submit(e, "login")}
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
              onChange={(e) => setEmail(e.target.value)}
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
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>

          <Button type="submit" className="mt-2 w-full rounded-[6px]" disabled={busy}>
            {busy ? "Please wait…" : "Continue"}
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            disabled={busy}
            onClick={(e) => submit(e, "register")}
          >
            Create account
          </Button>
        </form>

        <p className="mt-6 text-center text-xs text-mute">
          By continuing you agree to use Sourcebook for your own documents.
        </p>
      </main>
    </div>
  );
}
