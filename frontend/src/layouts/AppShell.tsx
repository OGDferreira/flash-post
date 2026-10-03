import { useState } from "react";
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

export function AppShell({ admin = false }: { admin?: boolean }) {
  const { user } = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);
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

  const sidebar = (
    <div className="flex h-full flex-col bg-[#0b0c0e]">
      <div className="flex h-[72px] items-center justify-between border-b border-[#202838] px-5">
        <Link
          className="flex items-center gap-3"
          to={admin ? "/admin" : "/dashboard"}
          onClick={() => setMobileOpen(false)}
        >
          <span className="grid size-9 place-items-center rounded-xl border border-[#33447c] bg-[#11182d] text-sm font-bold text-[#9baaff]">
            F
          </span>
          <span className="text-base font-semibold tracking-[-0.03em] text-[#f5f7fb]">
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
        <div className="mx-4 mt-5 flex items-center gap-2 rounded-lg border border-[#27334a] bg-[#10141b] px-3 py-2 text-xs font-medium text-[#aeb9ce]">
          <Shield size={14} className="text-[#8295ff]" />
          Administração da plataforma
        </div>
      )}

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-5">
        {links.map(({ label, to, icon: Icon }) => (
          <NavLink
            end={to === "/admin" || to === "/dashboard"}
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex min-h-10 items-center gap-3 rounded-lg px-3 text-sm transition-colors ${
                isActive
                  ? "bg-[#151b2d] font-medium text-[#dfe4ff]"
                  : "text-[#94a3b8] hover:bg-[#12151b] hover:text-[#f5f7fb]"
              }`
            }
          >
            <Icon size={17} strokeWidth={1.8} />
            {label}
            {!admin &&
              to !== "/dashboard" &&
              to !== "/feature/accounts" &&
              to !== "/feature/loops" && (
              <span className="ml-auto rounded-md border border-[#202838] px-1.5 py-0.5 text-[9px] text-[#64748b]">
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
          className="flex items-center gap-3 rounded-lg px-3 py-3 hover:bg-[#12151b]"
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
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-[#e6eaf2]">
              {user?.full_name}
            </span>
            <span className="block truncate text-xs text-[#64748b]">
              {user?.role}
            </span>
          </span>
          <ChevronDown size={15} className="text-[#64748b]" />
        </Link>
        <button
          onClick={() => {
            setLogoutError(null);
            logout.mutate();
          }}
          disabled={logout.isPending}
          className="mt-1 flex min-h-10 w-full items-center gap-3 rounded-lg px-3 text-sm text-[#94a3b8] hover:bg-[#171317] hover:text-[#f1a3ad] disabled:opacity-50"
        >
          <LogOut size={16} />
          Sair
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
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[252px] border-r border-[#202838] lg:block">
        {sidebar}
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileOpen(false)}
            aria-label="Fechar menu"
          />
          <aside className="relative h-full w-[min(300px,85vw)] border-r border-[#202838]">
            {sidebar}
          </aside>
        </div>
      )}
      <div className="lg:pl-[252px]">
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
              <h1 className="mt-0.5 text-sm font-medium text-[#e6eaf2]">
                {admin ? "Painel da plataforma" : "Seu espaço de trabalho"}
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
    </div>
  );
}
