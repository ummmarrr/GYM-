import { Route, Routes } from "react-router-dom";

import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import { ButtonLink } from "./components/ui";
import AdminDashboard from "./pages/AdminDashboard";
import AdminInsights from "./pages/AdminInsights";
import Join from "./pages/Join";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import MemberDashboard from "./pages/MemberDashboard";
import Packages from "./pages/Packages";
import TrainerDashboard from "./pages/TrainerDashboard";

function NotFound() {
  return (
    <div className="mx-auto max-w-md px-4 py-32 text-center">
      <p className="text-6xl font-extrabold text-volt-400">404</p>
      <h1 className="mt-4 text-2xl font-bold text-white">This page skipped leg day</h1>
      <p className="mt-2 text-slate-400">
        The page you were looking for does not exist. Let's get you back to training.
      </p>
      <ButtonLink to="/" className="mt-7">
        Back to home
      </ButtonLink>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Landing />} />
        <Route path="/packages" element={<Packages />} />
        <Route path="/login" element={<Login />} />
        <Route path="/join" element={<Join />} />

        <Route element={<ProtectedRoute allow={["member", "trainer", "admin"]} />}>
          <Route path="/dashboard" element={<MemberDashboard />} />
        </Route>

        <Route element={<ProtectedRoute allow={["trainer", "admin"]} />}>
          <Route path="/trainer" element={<TrainerDashboard />} />
        </Route>

        <Route element={<ProtectedRoute allow={["admin"]} />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/insights" element={<AdminInsights />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
