import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import {
  api,
  getToken,
  setToken,
  type DevUserList,
} from "@/api";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatError } from "@/lib/utils";
import { LoginPageView } from "./view";

export { LoginPageView } from "./view";

export function LoginPage() {
  const navigate = useNavigate();
  useDocumentTitle("Sign in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [devInfo, setDevInfo] = useState<DevUserList | null>(null);
  const [devError, setDevError] = useState<string | null>(null);
  const [devBusy, setDevBusy] = useState(false);

  const loadDevUsers = useCallback(async () => {
    setDevError(null);
    try {
      const data = await api.devUsers();
      setDevInfo(data);
    } catch {
      setDevInfo(null);
    }
  }, []);

  useEffect(() => {
    void loadDevUsers();
  }, [loadDevUsers]);

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

  function fillLogin(userEmail: string, userPassword: string | null) {
    setEmail(userEmail);
    if (userPassword) setPassword(userPassword);
  }

  async function setPasswordFor(userEmail: string) {
    setDevBusy(true);
    setDevError(null);
    try {
      const res = await api.devSetPassword(userEmail, "password123");
      await loadDevUsers();
      fillLogin(res.email, res.password);
    } catch (err) {
      setDevError(formatError(err));
    } finally {
      setDevBusy(false);
    }
  }

  async function setAllPasswords() {
    setDevBusy(true);
    setDevError(null);
    try {
      await api.devSetAllPasswords("password123");
      await loadDevUsers();
    } catch (err) {
      setDevError(formatError(err));
    } finally {
      setDevBusy(false);
    }
  }

  return (
    <LoginPageView
      error={error}
      busy={busy}
      devInfo={devInfo}
      devError={devError}
      devBusy={devBusy}
      email={email}
      password={password}
      onEmailChange={setEmail}
      onPasswordChange={setPassword}
      onSubmit={submit}
      onFillLogin={fillLogin}
      onSetPassword={setPasswordFor}
      onSetAllPasswords={setAllPasswords}
      onLoadDevUsers={loadDevUsers}
    />
  );
}
