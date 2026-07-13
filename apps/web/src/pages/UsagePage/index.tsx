import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import { useUsageSummary } from "@/hooks/queries";
import { formatError } from "@/lib/utils";
import { UsagePageView } from "./view";

export { UsagePageView } from "./view";

export function UsagePage() {
  const navigate = useNavigate();
  useDocumentTitle("Usage");
  const { data, error, isLoading, refetch } = useUsageSummary();

  return (
    <UsagePageView
      data={data ?? null}
      error={error ? formatError(error) : null}
      loading={isLoading}
      onRefresh={() => refetch()}
      onLogout={() => navigate("/login", { replace: true })}
    />
  );
}
