import { Suspense, useEffect, type ComponentType } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { getToken, isTokenExpired, setToken } from "@/api";
import { PageLoadingFallback } from "@/components/layout/PageLoadingFallback";

type RequireAuthProps = {
  page: ComponentType;
};

export function RequireAuth({ page: Page }: RequireAuthProps) {
  const location = useLocation();
  const token = getToken();
  const sessionValid = !!token && !isTokenExpired(token);

  useEffect(() => {
    if (token && isTokenExpired(token)) {
      setToken(null);
    }
  }, [token]);

  if (!sessionValid) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return (
    <Suspense key={location.key} fallback={<PageLoadingFallback />}>
      <Page />
    </Suspense>
  );
}
