import { useCallback, useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { getToken, type UsageSummary } from "@/api";
import { api } from "@/api";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { formatError } from "@/lib/utils";
import { UsagePageView } from "./view";

export { UsagePageView } from "./view";

export function UsagePage() {
  const navigate = useNavigate();
  useDocumentTitle("Usage");
  const [data, setData] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const summary = await api.usageSummary();
      setData(summary);
    } catch (err) {
      setError(formatError(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    void load();
  }, [load]);

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <UsagePageView
      data={data}
      error={error}
      loading={loading}
      onRefresh={load}
      onLogout={() => navigate("/login", { replace: true })}
    />
  );
}
