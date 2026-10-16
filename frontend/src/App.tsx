import { ContactsPage } from "@/pages/ContactsPage";
import { CollaboratorInvitePage } from "@/features/auth/CollaboratorInvitePage";
import { Suspense, lazy, type ComponentType } from "react";
import {
  BrowserRouter,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";

import { LoadingState } from "@/components/PageState";
import { ConfirmHost } from "@/lib/confirm";
import { AuthProvider, useAuth } from "@/features/auth/AuthProvider";
import { LoginPage } from "@/features/auth/LoginPage";
import { RegisterPage } from "@/features/auth/RegisterPage";
import { AppShell } from "@/layouts/AppShell";
import { FeaturePlaceholderPage } from "@/pages/FeaturePlaceholderPage";

const lazyPage = <K extends string>(
  load: () => Promise<Record<K, ComponentType>>,
  name: K,
) => lazy(() => load().then((module) => ({ default: module[name] })));

const NotificationsPage = lazyPage(() => import("@/pages/NotificationsPage"), "NotificationsPage");
const RankingPage = lazyPage(() => import("@/pages/RankingPage"), "RankingPage");
const InstagramAccountsPage = lazyPage(() => import("@/pages/InstagramAccountsPage"), "InstagramAccountsPage");
const LoopsPage = lazyPage(() => import("@/pages/LoopsPage"), "LoopsPage");
const ErrorLogsPage = lazyPage(() => import("@/pages/ErrorLogsPage"), "ErrorLogsPage");
const EmailsPage = lazyPage(() => import("@/pages/EmailsPage"), "EmailsPage");
const IntegrationsPage = lazyPage(() => import("@/pages/IntegrationsPage"), "IntegrationsPage");
const ProfilePage = lazyPage(() => import("@/pages/ProfilePage"), "ProfilePage");
const ProfileFoldersPage = lazyPage(() => import("@/pages/ProfileFoldersPage"), "ProfileFoldersPage");
const MetaAppsPage = lazyPage(() => import("@/pages/MetaAppsPage"), "MetaAppsPage");
const CollaboratorsPage = lazyPage(() => import("@/pages/CollaboratorsPage"), "CollaboratorsPage");
const AffiliatesPage = lazyPage(() => import("@/pages/AffiliatesPage"), "AffiliatesPage");
const ExtensionsPage = lazyPage(() => import("@/pages/ExtensionsPage"), "ExtensionsPage");
const SupportPage = lazyPage(() => import("@/pages/SupportPage"), "SupportPage");
const FeedPage = lazyPage(() => import("@/pages/FeedPage"), "FeedPage");
const BotsPage = lazyPage(() => import("@/pages/BotsPage"), "BotsPage");
const AdminOverviewPage = lazyPage(() => import("@/pages/admin/AdminOverviewPage"), "AdminOverviewPage");
const AdminNotificationsPage = lazyPage(() => import("@/pages/admin/AdminNotificationsPage"), "AdminNotificationsPage");
const AdminSystemPage = lazyPage(() => import("@/pages/admin/AdminSystemPage"), "AdminSystemPage");
const AdminUsersPage = lazyPage(() => import("@/pages/admin/AdminUsersPage"), "AdminUsersPage");
const AdminWorkspacesPage = lazyPage(() => import("@/pages/admin/AdminWorkspacesPage"), "AdminWorkspacesPage");

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
const FinancePage = lazy(() =>
  import("@/pages/FinancePage").then((module) => ({
    default: module.FinancePage,
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
        <ConfirmHost />
        <Suspense fallback={<LoadingState fullscreen label="Carregando página" />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/convite/:token" element={<CollaboratorInvitePage />} />
          <Route element={<RequireAuth />}>
            <Route element={<RequireWorkspaceUser />}>
              <Route element={<RequireCollaboratorAccess />}>
                <Route element={<AppShell />}>
                  <Route path="/dashboard" element={<WorkspaceDashboard />} />
                  <Route path="/profile" element={<ProfilePage />} />
                  <Route path="/feature/accounts" element={<InstagramAccountsPage />} />
                  <Route path="/feature/loops" element={<LoopsPage />} />
                  <Route path="/feature/error-logs" element={<ErrorLogsPage />} />
                  <Route path="/feature/emails" element={<EmailsPage />} />
                  <Route path="/feature/extensions" element={<ExtensionsPage />} />
                  <Route path="/feature/support" element={<SupportPage />} />
                  <Route path="/feature/contacts" element={<ContactsPage />} />
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
                    <Route path="/feature/affiliates" element={<AffiliatesPage />} />
                    <Route path="/feature/feed" element={<FeedPage />} />
                    <Route path="/feature/bots" element={<BotsPage />} />
                    <Route path="/feature/collaborators" element={<CollaboratorsPage />} />
                    <Route path="/feature/notifications" element={<NotificationsPage />} />
                    <Route path="/feature/ranking" element={<RankingPage />} />
                    <Route path="/feature/meta-apps" element={<MetaAppsPage />} />
                    <Route path="/feature/settings" element={<Navigate replace to="/feature/meta-apps" />} />
                    <Route path="/feature/integrations" element={<IntegrationsPage />} />
                    <Route
                      path="/feature/finance"
                      element={
                        <Suspense fallback={<LoadingState label="Carregando Financeiro" />}>
                          <FinancePage />
                        </Suspense>
                      }
                    />
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
                <Route path="/admin/notifications" element={<AdminNotificationsPage />} />
              </Route>
            </Route>
          </Route>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
        </Suspense>
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
      <Suspense fallback={<LoadingState fullscreen label="Carregando seu painel" />}>
        <CollaboratorDashboardPage />
      </Suspense>
    );
  }
  return (
    <Suspense fallback={<LoadingState fullscreen label="Carregando painel" />}>
      <DashboardPage />
    </Suspense>
  );
}

function RequireWorkspaceUser() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState fullscreen label="Verificando permissões" />;
  const workspaceRole =
    user?.role === "SUPER_ADMIN" ? user.workspace_role : user?.role;
  if (workspaceRole !== "OWNER" && workspaceRole !== "COLLABORATOR") {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

function RequireWorkspaceOwner() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState fullscreen label="Verificando permissões" />;
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
    "/feature/extensions",
    "/feature/support",
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
  if (isLoading) return <LoadingState fullscreen label="Verificando sessão" />;
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}

function RequireSuperAdmin() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState fullscreen label="Verificando permissões" />;
  if (user?.role !== "SUPER_ADMIN") {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}

function HomeRedirect() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingState fullscreen label="Verificando sessão" />;
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
    <main className="grid min-h-screen place-items-center bg-transparent px-4 text-center text-muted">
      <div>
        <p className="text-sm font-medium text-accent">404</p>
        <h1 className="mt-2 text-2xl font-semibold text-fg">
          Página não encontrada
        </h1>
        <a
          className="mt-5 inline-block text-sm text-accent hover:text-white"
          href="/"
        >
          Voltar ao início
        </a>
      </div>
    </main>
  );
}
