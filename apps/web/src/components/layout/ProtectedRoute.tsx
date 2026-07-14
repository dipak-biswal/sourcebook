import { Suspense } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { getToken } from "@/api";
import { PageLoadingFallback } from "@/components/layout/PageLoadingFallback";

export function ProtectedRoute() {
  const location = useLocation();

  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }

  // key={location.key} remounts Suspense on navigation so React 19 shows the
  // fallback instead of keeping the previous lazy route visible while loading.
  return (
    <Suspense key={location.key} fallback={<PageLoadingFallback />}>
      <Outlet />
    </Suspense>
  );
}
