import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  Blocks,
  ChartNoAxesCombined,
  ChevronDown,
  CircleDollarSign,
  Clapperboard,
  Home,
  Infinity,
  LogOut,
  Menu,
  MessageSquareText,
  Settings2,
  Shield,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";

const ownerLinks = [
  { label: "Visão geral", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Loops", to: "/feature/loops", icon: Infinity },
  { label: "Analytics", to: "/feature/analytics", icon: ChartNoAxesCombined },
  { label: "Financeiro", to: "/feature/finance", icon: CircleDollarSign },
  { label: "Ranking", to: "/feature/ranking", icon: Trophy },
  { label: "Feed", to: "/feature/feed", icon: Clapperboard },
  { label: "Automações", to: "/feature/automations", icon: MessageSquareText },
  { label: "Integrações", to: "/feature/integrations", icon: Blocks },
  { label: "Colaboradores", to: "/feature/collaborators", icon: Users },
  { label: "Notificações", to: "/feature/notifications", icon: Bell },
  { label: "Configurações", to: "/feature/settings", icon: Settings2 },
];

const adminLinks = [
  { label: "Visão geral", to: "/admin", icon: Home },
  { label: "Usuários", to: "/admin/users", icon: Users },
  { label: "Workspaces", to: "/admin/workspaces", icon: Blocks },
  { label: "Sistema", to: "/admin/system", icon: Settings2 },
];

const collaboratorLinks = [
  { label: "Meu painel", to: "/dashboard", icon: Home },
  { label: "Hub de contas", to: "/feature/accounts", icon: Users },
  { label: "Loops", to: "/feature/loops", icon: Infinity },
];

export function AppShell({ admin = false }: { admin?: boolean }) {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const logout = useMutation({
    mutationFn: () => apiRequest("/api/auth/logout", { method: "POST" }),
    onSuccess: () => {
      queryClient.clear();
      navigate("/login", { replace: true });
    },
    onError: (error) => {
      setLogoutError(
        error instanceof ApiError ? error.message : "Não foi possível encerrar a sessão.",
      );
    },
  });
  const links = admin ? adminLinks : ownerLinks;
  const visibleLinks = !admin && user?.role === "COLLABORATOR" ? collaboratorLinks : links;
  useEffect(() => {
    const showToast = (event: Event) => {
      const message = (event as CustomEvent<string>).detail;
      if (!message) return;
      setToast(message);
      window.setTimeout(() => setToast(null), 4500);
    };
    window.addEventListener("flashpost-toast", showToast);
    return () => window.removeEventListener("flashpost-toast", showToast);
  }, []);
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "America/Sao_Paulo",
    }).format(new Date()),
  );
  const greeting =
    hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
  const pageHeading = admin
    ? "Painel da plataforma"
    : `${greeting}, ${user?.nickname ?? "bem-vindo"}`;

  const sidebar = (
    <div className="flex h-full flex-col bg-[#0b0c0e]">
      <div className="flex h-[72px] items-center justify-between border-b border-[#202838] px-5 lg:px-3 lg:group-hover:px-5">
        <Link
          className="flex items-center gap-3 lg:gap-0 lg:group-hover:gap-3"
          to={admin ? "/admin" : "/dashboard"}
          onClick={() => setMobileOpen(false)}
        >
          <span className="grid size-9 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-sm font-bold text-[#9baaff]">
            F
          </span>
          <span className="max-w-[140px] overflow-hidden whitespace-nowrap text-base font-semibold tracking-[-0.03em] text-[#f5f7fb] opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[140px] lg:group-hover:opacity-100">
            FlashPost<span className="text-[#7186ff]">.</span>
          </span>
        </Link>
        <button
          className="grid size-9 place-items-center rounded-lg text-[#94a3b8] hover:bg-[#151922] lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-label="Fechar menu"
        >
          <X size={18} />
        </button>
      </div>

      {admin && (
        <div className="mx-4 mt-5 flex items-center gap-2 overflow-hidden rounded-lg border border-[#27334a] bg-[#10141b] px-3 py-2 text-xs font-medium text-[#aeb9ce] lg:group-hover:mx-3">
          <Shield className="shrink-0 text-[#8295ff]" size={14} />
          <span className="max-w-[180px] overflow-hidden whitespace-nowrap opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[180px] lg:group-hover:opacity-100">
            Administração da plataforma
          </span>
        </div>
      )}

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5">
        {visibleLinks.map(({ label, to, icon: Icon }) => (
          <NavLink
            end={to === "/admin" || to === "/dashboard"}
            key={to}
            to={to}
            title={label}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors ${
                isActive
                  ? "bg-[#151b2d] font-medium text-[#dfe4ff]"
                  : "text-[#94a3b8] hover:bg-[#12151b] hover:text-[#f5f7fb]"
              }`
            }
          >
            <Icon className="shrink-0" size={17} strokeWidth={1.8} />
            <span className="max-w-[170px] flex-1 overflow-hidden whitespace-nowrap opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[170px] lg:group-hover:opacity-100">
              {label}
            </span>
            {!admin &&
              user?.role !== "COLLABORATOR" &&
              to !== "/dashboard" &&
              to !== "/feature/accounts" &&
              to !== "/feature/loops" &&
              to !== "/feature/analytics" &&
              to !== "/feature/settings" && (
              <span className="ml-auto hidden rounded-md border border-[#202838] px-1.5 py-0.5 text-[9px] text-[#64748b] lg:group-hover:inline">
                EM BREVE
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-[#202838] p-3">
        <Link
          to="/profile"
          onClick={() => setMobileOpen(false)}
          className="flex items-center justify-center gap-3 rounded-lg px-3 py-3 hover:bg-[#12151b] lg:px-0 lg:group-hover:justify-start lg:group-hover:px-3"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt=""
              className="size-9 rounded-full border border-[#27334a] object-cover"
            />
          ) : (
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#171e31] text-sm font-semibold text-[#aab7ff]">
              {user?.full_name.slice(0, 1).toUpperCase() ?? "F"}
            </span>
          )}
          <span className="min-w-0 max-w-[145px] flex-1 overflow-hidden whitespace-nowrap opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[145px] lg:group-hover:opacity-100">
            <span className="block truncate text-sm font-medium text-[#e6eaf2]">
              {user?.full_name}
            </span>
            <span className="block truncate text-xs text-[#64748b]">
              {user?.role}
            </span>
          </span>
          <ChevronDown size={15} className="hidden shrink-0 text-[#64748b] lg:group-hover:block" />
        </Link>
        <button
          onClick={() => {
            setLogoutError(null);
            logout.mutate();
          }}
          disabled={logout.isPending}
          className="mt-1 flex min-h-10 w-full items-center justify-center gap-3 rounded-lg px-3 text-sm text-[#94a3b8] hover:bg-[#171317] hover:text-[#f1a3ad] disabled:opacity-50 lg:px-0 lg:group-hover:justify-start lg:group-hover:px-3"
        >
          <LogOut className="shrink-0" size={16} />
          <span className="max-w-[120px] overflow-hidden whitespace-nowrap opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[120px] lg:group-hover:opacity-100">
            Sair
          </span>
        </button>
        {logoutError && (
          <p role="alert" className="px-3 pt-2 text-xs text-[#f1a3ad]">
            {logoutError}
          </p>
        )}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#070809] text-[#f5f7fb]">
      <aside className="group fixed inset-y-0 left-0 z-30 hidden w-[68px] border-r border-[#202838] transition-[width] duration-200 hover:w-[252px] lg:block">
        {sidebar}
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileOpen(false)}
            aria-label="Fechar menu"
          />
          <aside className="group relative h-full w-[min(300px,85vw)] border-r border-[#202838]">
            {sidebar}
          </aside>
        </div>
      )}
      <div className="lg:pl-[68px]">
        <header className="sticky top-0 z-20 flex h-[72px] items-center justify-between border-b border-[#202838] bg-[#070809]/95 px-5 backdrop-blur-sm sm:px-8">
          <div className="flex items-center gap-3">
            <button
              className="grid size-9 place-items-center rounded-lg border border-[#202838] text-[#94a3b8] hover:bg-[#10141b] lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Abrir menu"
            >
              <Menu size={18} />
            </button>
            <div>
              <p className="text-xs text-[#64748b]">
                {admin ? "FlashPost / Administração" : "FlashPost / Workspace"}
              </p>
              <h1 className="mt-0.5 max-w-[calc(100vw-170px)] truncate text-sm font-medium text-[#e6eaf2]">
                {pageHeading}
              </h1>
            </div>
          </div>
          <div className="hidden items-center gap-2 rounded-full border border-[#202838] bg-[#0d1015] px-3 py-2 text-xs text-[#94a3b8] transition-colors duration-200 hover:border-[#536dfe]/40 sm:flex">
            <span className="size-1.5 rounded-full bg-[#2dd4a0]" />
            Sistema online
          </div>
        </header>
        <main className="mx-auto max-w-[1440px] px-5 py-7 sm:px-8 sm:py-9">
          <Outlet />
        </main>
      </div>
      {toast && (
        <div
          className="fixed right-5 top-20 z-[70] max-w-sm rounded-xl border border-[#315843] bg-[#10231a] px-4 py-3 text-sm text-[#a9e5c0] shadow-[0_12px_38px_rgba(0,0,0,.45)]"
          role="status"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
