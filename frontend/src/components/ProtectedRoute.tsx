import { Navigate, Outlet, useLocation } from "react-router-dom";

import { homeFor, useAuth } from "../context/AuthContext";
import type { Role } from "../lib/api";
import { Spinner } from "./ui";

/**
 * A convenience guard only. Every endpoint behind it also checks the role on the server,
 * so hiding a route here is never the thing that keeps data safe.
 */
export default function ProtectedRoute({ allow }: { allow: Role[] }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) return <Spinner label="Checking your session" />;

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  if (!allow.includes(user.role)) {
    return <Navigate to={homeFor(user.role)} replace />;
  }

  return <Outlet />;
}
