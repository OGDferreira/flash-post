import { Suspense, lazy } from "react";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { LoadingState } from "@/components/PageState";
import { AuthProvider, useAuth } from "@/features/auth/AuthProvider";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { AppShell } from "@/layouts/AppShell";
import { FeaturePlaceholderPage } from "@/pages/FeaturePlaceholderPage";
import { InstagramAccountsPage } from "@/pages/InstagramAccountsPage";
import { LoopsPage } from "@/pages/LoopsPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { AdminOverviewPage } from "@/pages/admin/AdminOverviewPage";
import { AdminSystemPage } from "@/pages/admin/AdminSystemPage";
import { AdminUsersPage } from "@/pages/admin/AdminUsersPage";
import { AdminWorkspacesPage } from "@/pages/admin/AdminWorkspacesPage";

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route element={<RequireAuth />}>
            <Route element={<AppShell />}>
              <Route
                path="/dashboard"
                element={
                  <Suspense fallback={<LoadingState label="Carregando painel" />}>
                    <DashboardPage />
                  </Suspense>
                }
              />
              <Route path="/profile" element={<ProfilePage />} />
              <Route path="/feature/accounts" element={<InstagramAccountsPage />} />
              <Route path="/feature/loops" element={<LoopsPage />} />
              <Route path="/feature/:slug" element={<FeaturePlaceholderPage />} />
            </Route>
            <Route element={<RequireSuperAdmin />}>
              <Route element={<AppShell admin />}>
                <Route path="/admin" element={<AdminOverviewPage />} />
                <Route path="/admin/users" element={<AdminUsersPage />} />
                <Route path="/admin/workspaces" element={<AdminWorkspacesPage />} />
                <Route path="/admin/system" element={<AdminSystemPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

function RequireAuth() {
  const { user, isLoading } = useAuth();
  const location = useLocation();
  if (isLoading) return <LoadingState label="Verificando sessão" />;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

function RequireSuperAdmin() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState label="Verificando permissões" />;
  if (user?.role !== "SUPER_ADMIN") {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}

function HomeRedirect() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState label="Verificando sessão" />;
  if (!user) return <Navigate to="/login" replace />;
  return (
    <Navigate
      to={user.role === "SUPER_ADMIN" ? "/admin" : "/dashboard"}
      replace
    />
  );
}

function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-[#070809] px-5 text-center text-[#94a3b8]">
      <div>
        <p className="text-sm font-medium text-[#7186ff]">404</p>
        <h1 className="mt-2 text-2xl font-semibold text-[#f5f7fb]">
          Página não encontrada
        </h1>
        <a
          className="mt-5 inline-block text-sm text-[#aab7ff] hover:text-white"
          href="/"
        >
          Voltar ao início
        </a>
      </div>
    </main>
  );
}
