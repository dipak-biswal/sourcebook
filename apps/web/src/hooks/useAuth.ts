import { useEffect, useState } from "react";
import {
  AUTH_CHANGED_EVENT,
  getToken,
  isTokenExpired,
  setToken,
} from "@/api";

function readAuthed(): boolean {
  const token = getToken();
  return !!token && !isTokenExpired(token);
}

/** Reactive auth flag — updates on login, logout, refresh, and storage events. */
export function useIsAuthenticated(): boolean {
  const [authed, setAuthed] = useState(() => readAuthed());

  useEffect(() => {
    // Drop expired tokens once after mount (side-effect-safe).
    const token = getToken();
    if (token && isTokenExpired(token)) {
      setToken(null);
      setAuthed(false);
    }

    const sync = () => {
      const t = getToken();
      if (t && isTokenExpired(t)) {
        setToken(null);
        setAuthed(false);
        return;
      }
      setAuthed(!!t);
    };
    window.addEventListener(AUTH_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(AUTH_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return authed;
}
