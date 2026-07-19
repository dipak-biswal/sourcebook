import { useNavigate } from "react-router-dom";
import { useDocumentTitle } from "@/hooks/useDocumentTitle";
import {
  useUsageSummary,
  useVisualPipelineSummary,
} from "@/hooks/queries";
import { formatError } from "@/lib/utils";
import { UsagePageView } from "./view";

export { UsagePageView } from "./view";
export { DailyTrendChart } from "./DailyTrendChart";

export function UsagePage() {
  const navigate = useNavigate();
  useDocumentTitle("Usage");
  const { data, error, isLoading, refetch } = useUsageSummary();
  const {
    data: visualPipeline,
    isLoading: visualLoading,
    refetch: refetchVisual,
  } = useVisualPipelineSummary();

  return (
    <UsagePageView
      data={data ?? null}
      visualPipeline={visualPipeline ?? null}
      error={error ? formatError(error) : null}
      loading={isLoading || visualLoading}
      onRefresh={() => {
        void refetch();
        void refetchVisual();
      }}
      onLogout={() => navigate("/login", { replace: true })}
    />
  );
}
