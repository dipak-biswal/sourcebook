import { Navigate, Outlet } from "react-router-dom";
import { getToken } from "@/api";

export function ProtectedRoute() {
  if (!getToken()) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
