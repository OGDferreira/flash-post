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
import { NotificationsPage } from "@/pages/NotificationsPage";
import { RankingPage } from "@/pages/RankingPage";
import { InstagramAccountsPage } from "@/pages/InstagramAccountsPage";
import { LoopsPage } from "@/pages/LoopsPage";
import { EmailsPage } from "@/pages/EmailsPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { ProfileFoldersPage } from "@/pages/ProfileFoldersPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { CollaboratorsPage } from "@/pages/CollaboratorsPage";
import { FeedPage } from "@/pages/FeedPage";
import { AdminOverviewPage } from "@/pages/admin/AdminOverviewPage";
import { AdminSystemPage } from "@/pages/admin/AdminSystemPage";
import { AdminUsersPage } from "@/pages/admin/AdminUsersPage";
import { AdminWorkspacesPage } from "@/pages/admin/AdminWorkspacesPage";

const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((module) => ({
    default: module.DashboardPage,
  })),
);
const AnalyticsPage = lazy(() =>
  import("@/pages/AnalyticsPage").then((module) => ({
    default: module.AnalyticsPage,
  })),
);
const CollaboratorDashboardPage = lazy(() =>
  import("@/pages/CollaboratorDashboardPage").then((module) => ({
    default: module.CollaboratorDashboardPage,
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
            <Route element={<RequireWorkspaceUser />}>
              <Route element={<RequireCollaboratorAccess />}>
                <Route element={<AppShell />}>
                  <Route path="/dashboard" element={<WorkspaceDashboard />} />
                  <Route path="/profile" element={<ProfilePage />} />
                  <Route path="/feature/accounts" element={<InstagramAccountsPage />} />
                  <Route path="/feature/loops" element={<LoopsPage />} />
                  <Route path="/feature/emails" element={<EmailsPage />} />
                  <Route element={<RequireWorkspaceOwner />}>
                    <Route path="/feature/profile-folders" element={<ProfileFoldersPage />} />
                    <Route
                      path="/feature/analytics"
                      element={
                        <Suspense fallback={<LoadingState label="Carregando Analytics" />}>
                          <AnalyticsPage />
                        </Suspense>
                      }
                    />
                    <Route path="/feature/feed" element={<FeedPage />} />
                    <Route path="/feature/collaborators" element={<CollaboratorsPage />} />
                    <Route path="/feature/notifications" element={<NotificationsPage />} />
                    <Route path="/feature/ranking" element={<RankingPage />} />
                    <Route path="/feature/settings" element={<SettingsPage />} />
                    <Route path="/feature/:slug" element={<FeaturePlaceholderPage />} />
                  </Route>
                </Route>
            </Route>
            </Route>
            <Route element={<RequireSuperAdmin />}>
              <Route element={<AppShell />}>
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

function WorkspaceDashboard() {
  const { user } = useAuth();
  const workspaceRole =
    user?.role === "SUPER_ADMIN" ? user.workspace_role : user?.role;
  if (workspaceRole === "COLLABORATOR") {
    return (
      <Suspense fallback={<LoadingState label="Carregando seu painel" />}>
        <CollaboratorDashboardPage />
      </Suspense>
    );
  }
  return (
    <Suspense fallback={<LoadingState label="Carregando painel" />}>
      <DashboardPage />
    </Suspense>
  );
}

function RequireWorkspaceUser() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState label="Verificando permissões" />;
  const workspaceRole =
    user?.role === "SUPER_ADMIN" ? user.workspace_role : user?.role;
  if (workspaceRole !== "OWNER" && workspaceRole !== "COLLABORATOR") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function RequireWorkspaceOwner() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState label="Verificando permissões" />;
  const isWorkspaceOwner =
    user?.role === "OWNER" ||
    (user?.role === "SUPER_ADMIN" && user.workspace_role === "OWNER");
  if (!isWorkspaceOwner) return <Navigate to="/dashboard" replace />;
  return <Outlet />;
}

function RequireCollaboratorAccess() {
  const { user } = useAuth();
  const location = useLocation();
  const workspaceRole =
    user?.role === "SUPER_ADMIN" ? user.workspace_role : user?.role;
  const collaboratorRoutes = [
    "/dashboard",
    "/feature/accounts",
    "/feature/loops",
    "/feature/emails",
  ];
  if (
    workspaceRole === "COLLABORATOR" &&
    !collaboratorRoutes.includes(location.pathname)
  ) {
    return <Navigate to="/feature/accounts" replace />;
  }
  return <Outlet />;
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
      to={
        user.role === "SUPER_ADMIN"
          ? user.workspace_role === "OWNER"
            ? "/dashboard"
            : user.workspace_role === "COLLABORATOR"
              ? "/feature/accounts"
              : "/admin"
          : user.role === "COLLABORATOR"
            ? "/feature/accounts"
            : "/dashboard"
      }
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
