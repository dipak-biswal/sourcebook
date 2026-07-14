import { Suspense, type ComponentType } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getToken } from "@/api";
import { PageLoadingFallback } from "@/components/layout/PageLoadingFallback";

type RequireAuthProps = {
  page: ComponentType;
};

export function RequireAuth({ page: Page }: RequireAuthProps) {
  const location = useLocation();

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  return (
    <Suspense key={location.key} fallback={<PageLoadingFallback />}>
      <Page />
    </Suspense>
  );
}