import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Bell,
  Blocks,
  ChartNoAxesCombined,
  ChevronDown,
  CircleDollarSign,
  Clapperboard,
  Folder,
  Home,
  Infinity,
  LogOut,
  Menu,
  MessageSquareText,
  Settings2,
  Share,
  Shield,
  Trophy,
  Users,
  X,
} from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "@/features/auth/AuthProvider";
import { setCsrfToken, apiRequest } from "@/services/api";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";

const ownerLinks = [
  { label: "Visão geral", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Pastas de perfis", to: "/feature/profile-folders", icon: Folder },
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

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

const INSTALL_PROMPT_DISMISSED_UNTIL_KEY = "flashpost-install-prompt-dismissed-until";
const INSTALL_PROMPT_SNOOZE_MS = 30 * 24 * 60 * 60 * 1000;

function isInstallPromptSnoozed() {
  try {
    return (
      Number(window.localStorage.getItem(INSTALL_PROMPT_DISMISSED_UNTIL_KEY)) >
      Date.now()
    );
  } catch (error) {
    console.warn("FlashPost could not read the install-prompt preference.", error);
    return false;
  }
}

function snoozeInstallPrompt() {
  try {
    window.localStorage.setItem(
      INSTALL_PROMPT_DISMISSED_UNTIL_KEY,
      String(Date.now() + INSTALL_PROMPT_SNOOZE_MS),
    );
  } catch (error) {
    console.warn("FlashPost could not save the install-prompt preference.", error);
  }
}

export function AppShell() {
  const { user } = useAuth();
  const location = useLocation();
  const isAdminRoute = location.pathname.startsWith("/admin");
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const workspaceRole =
    isSuperAdmin ? user.workspace_role : user?.role;
  const hasWorkspaceOwnerAccess = workspaceRole === "OWNER";
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(() => new Date());
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [installGuideOpen, setInstallGuideOpen] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [isMobileDevice, setIsMobileDevice] = useState(false);
  const [isIosDevice, setIsIosDevice] = useState(false);
  const [installPrompt, setInstallPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const analyticsNotifications = useQuery({
    queryKey: ["analytics", "summary", "fast", "7d", null, null],
    queryFn: () =>
      apiRequest<InstagramAnalyticsSummary>(
        "/api/analytics/summary?period=7d",
      ),
    enabled: hasWorkspaceOwnerAccess,
    retry: false,
    staleTime: 60_000,
    refetchInterval: 300_000,
  });
  const notificationItems = [
    ...(analyticsNotifications.error
      ? [
          {
            title: "Analytics indisponível",
            message: "Não foi possível atualizar as métricas. Tente novamente mais tarde.",
          },
        ]
      : []),
    ...(analyticsNotifications.data?.missing_permissions.map((permission) => ({
      title: "Permissão Meta não autorizada para esta conta",
      message: `O token da conta não confirmou a permissão ${permission}. Reconecte a conta Instagram para atualizar as permissões concedidas.`,
    })) ?? []),
    ...(analyticsNotifications.data?.profile_metrics_unavailable
      ? [
          {
            title: "Dados do perfil Instagram indisponíveis",
            message:
              "A Meta não atualizou seguidores e mídias de uma ou mais contas. Os últimos valores salvos serão mantidos.",
          },
        ]
      : []),
    ...(analyticsNotifications.data?.insights_unavailable &&
    !analyticsNotifications.data.missing_permissions.length
      ? [
          {
            title: "Insights da Meta indisponíveis",
            message:
              "A Meta não retornou as visualizações. O erro não identifica uma permissão específica.",
          },
        ]
      : []),
  ];
  const logout = useMutation({
    mutationFn: () => apiRequest("/api/auth/logout", { method: "POST" }),
    onSettled: () => {
      setCsrfToken(undefined);
      queryClient.clear();
      queryClient.setQueryData(["auth", "me"], null);
      navigate("/login", { replace: true });
    },
  });
  const workspaceLinks =
    workspaceRole === "COLLABORATOR" ? collaboratorLinks : ownerLinks;
  const mobileLinks = isAdminRoute
    ? adminLinks
    : workspaceRole === "COLLABORATOR"
      ? collaboratorLinks
      : ownerLinks.filter(({ to }) =>
          ["/dashboard", "/feature/accounts", "/feature/loops", "/feature/collaborators"].includes(to),
        );
  const visibleLinkGroups = [
    ...(hasWorkspaceOwnerAccess || workspaceRole === "COLLABORATOR"
      ? [{ title: "Workspace", links: workspaceLinks }]
      : []),
    ...(isSuperAdmin ? [{ title: "Administração", links: adminLinks }] : []),
  ];
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
  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const navigatorWithStandalone = navigator as Navigator & { standalone?: boolean };
    const installed =
      window.matchMedia("(display-mode: standalone)").matches ||
      navigatorWithStandalone.standalone === true;
    const isIos =
      /iPhone|iPad|iPod/i.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const isMobile =
      isIos || /Android/i.test(navigator.userAgent);

    setIsStandalone(installed);
    setIsMobileDevice(isMobile);
    setIsIosDevice(isIos);
    if (!isMobile || installed || isInstallPromptSnoozed()) return;

    const timer = window.setTimeout(() => setInstallGuideOpen(true), 2500);
    const onBeforeInstallPrompt = (event: Event) => {
      event.preventDefault();
      setInstallPrompt(event as BeforeInstallPromptEvent);
    };
    const onAppInstalled = () => {
      setIsStandalone(true);
      setInstallPrompt(null);
      setInstallGuideOpen(false);
      snoozeInstallPrompt();
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt);
    window.addEventListener("appinstalled", onAppInstalled);

    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt);
      window.removeEventListener("appinstalled", onAppInstalled);
    };
  }, []);

  const dismissInstallGuide = () => {
    setInstallGuideOpen(false);
    snoozeInstallPrompt();
  };

  const installApp = async () => {
    if (!installPrompt) {
      dismissInstallGuide();
      return;
    }
    await installPrompt.prompt();
    const choice = await installPrompt.userChoice;
    setInstallPrompt(null);
    if (choice.outcome === "accepted") {
      setIsStandalone(true);
      setInstallGuideOpen(false);
      snoozeInstallPrompt();
      return;
    }
    dismissInstallGuide();
  };
  const hour = Number(
    new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hourCycle: "h23",
      timeZone: "America/Sao_Paulo",
    }).format(new Date()),
  );
  const greeting =
    hour < 12 ? "Bom dia" : hour < 18 ? "Boa tarde" : "Boa noite";
  const pageHeading = isAdminRoute
    ? "Painel da plataforma"
    : `${greeting}, ${user?.nickname ?? "bem-vindo"} · ${new Intl.DateTimeFormat(
        "pt-BR",
        {
          weekday: "long",
          day: "2-digit",
          month: "long",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          timeZone: "America/Sao_Paulo",
        },
      ).format(currentTime)}`;

  const sidebar = (
    <div className="flex h-full flex-col bg-[#0b0c0e]">
      <div className="flex h-[72px] items-center justify-between border-b border-[#202838] px-5 lg:px-3 lg:group-hover:px-5">
        <Link
          className="flex items-center gap-3 lg:gap-0 lg:group-hover:gap-3"
          to={
            hasWorkspaceOwnerAccess
              ? "/dashboard"
              : workspaceRole === "COLLABORATOR"
                ? "/feature/accounts"
                : isSuperAdmin
                  ? "/admin"
                  : "/dashboard"
          }
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

      {isAdminRoute && (
        <div className="mx-4 mt-5 flex items-center gap-2 overflow-hidden rounded-lg border border-[#27334a] bg-[#10141b] px-3 py-2 text-xs font-medium text-[#aeb9ce] lg:group-hover:mx-3">
          <Shield className="shrink-0 text-[#8295ff]" size={14} />
          <span className="max-w-[180px] overflow-hidden whitespace-nowrap opacity-100 transition-all duration-200 lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[180px] lg:group-hover:opacity-100">
            Administração da plataforma
          </span>
        </div>
      )}

      <nav className="app-sidebar-nav flex-1 space-y-1 overflow-y-auto px-3 py-5">
        {visibleLinkGroups.map((group, groupIndex) => (
          <section
            className={groupIndex ? "mt-4 border-t border-[#202838] pt-3" : ""}
            key={group.title}
          >
            {visibleLinkGroups.length > 1 && (
              <h2 className="mb-2 overflow-hidden px-3 text-[10px] font-medium uppercase tracking-[0.12em] text-[#64748b] opacity-100 transition-all lg:max-w-0 lg:opacity-0 lg:group-hover:max-w-[170px] lg:group-hover:opacity-100">
                {group.title}
              </h2>
            )}
            <div className="space-y-1">
              {group.links.map(({ label, to, icon: Icon }) => (
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
                </NavLink>
              ))}
            </div>
          </section>
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
              {(user?.full_name || user?.nickname || "F").slice(0, 1).toUpperCase()}
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
        <header className="app-shell-header sticky top-0 z-20 flex items-center justify-between border-b border-[#202838] bg-[#070809]/95 px-4 backdrop-blur-sm sm:px-8">
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
                {isAdminRoute ? "FlashPost / Administração" : "FlashPost / Workspace"}
              </p>
              <h1 className="mt-0.5 max-w-[calc(100vw-170px)] truncate text-sm font-medium text-[#e6eaf2]">
                {pageHeading}
              </h1>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <button
                aria-label={
                  notificationItems.length
                    ? `Notificações, ${notificationItems.length} avisos`
                    : "Notificações"
                }
                aria-expanded={notificationsOpen}
                aria-haspopup="dialog"
                className="relative grid size-9 place-items-center rounded-full border border-[#202838] bg-[#0d1015] text-[#94a3b8] transition-colors hover:border-[#536dfe]/40 hover:text-white"
                onClick={() => setNotificationsOpen((open) => !open)}
                type="button"
              >
                <Bell size={16} />
                {notificationItems.length > 0 && (
                  <span className="absolute -right-1 -top-1 grid min-h-4 min-w-4 place-items-center rounded-full bg-[#f16f82] px-1 text-[9px] font-semibold text-[#17090c]">
                    {notificationItems.length > 9 ? "9+" : notificationItems.length}
                  </span>
                )}
              </button>
              {notificationsOpen && (
                <section
                  aria-label="Notificações"
                  className="absolute right-0 top-11 z-50 w-[min(360px,calc(100vw-32px))] rounded-xl border border-[#27334a] bg-[#0d1015] p-3 shadow-[0_16px_48px_rgba(0,0,0,.55)]"
                  role="dialog"
                >
                  <div className="flex items-center justify-between border-b border-[#202838] pb-2">
                    <h2 className="text-sm font-semibold text-[#e6eaf2]">Notificações</h2>
                    <button
                      className="text-xs text-[#94a3b8] hover:text-white"
                      onClick={() => setNotificationsOpen(false)}
                      type="button"
                    >
                      Fechar
                    </button>
                  </div>
                  {notificationItems.length ? (
                    <ul className="max-h-[min(60vh,420px)] divide-y divide-[#202838] overflow-y-auto">
                      {notificationItems.map((item, index) => (
                        <li className="flex gap-2.5 py-3" key={`${item.title}-${index}`}>
                          <AlertTriangle
                            aria-hidden="true"
                            className="mt-0.5 shrink-0 text-[#f2d48a]"
                            size={15}
                          />
                          <div>
                            <h3 className="text-xs font-medium text-[#f2d48a]">{item.title}</h3>
                            <p className="mt-1 text-xs leading-5 text-[#aeb9ce]">
                              {item.message}
                            </p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="py-4 text-xs text-[#94a3b8]">
                      Nenhum aviso no momento.
                    </p>
                  )}
                </section>
              )}
            </div>
            <div className="flex items-center gap-2 rounded-full border border-[#202838] bg-[#0d1015] px-3 py-2 text-xs text-[#94a3b8]">
              <span className="size-1.5 rounded-full bg-[#2dd4a0]" />
              <span className="hidden sm:inline">Sistema online</span>
              <span className="sm:hidden">Online</span>
            </div>
          </div>
        </header>
        <main className="app-shell-content min-h-[calc(100dvh-72px)] w-full px-4 py-6 sm:px-8 sm:py-9">
          <Outlet />
        </main>
      </div>
      <nav
        aria-label="Navegação principal"
        className="app-mobile-nav fixed inset-x-0 bottom-0 z-30 flex border-t border-[#202838] bg-[#0b0c0e]/95 px-2 pt-2 backdrop-blur-xl lg:hidden"
      >
        {mobileLinks.map(({ label, to, icon: Icon }) => (
          <NavLink
            end={to === "/dashboard" || to === "/admin"}
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `flex min-w-0 flex-1 flex-col items-center justify-center gap-1 rounded-lg px-1 py-1.5 text-[10px] transition ${
                isActive ? "text-[#aab7ff]" : "text-[#78839b]"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
                <span className="max-w-full truncate">{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
      {installGuideOpen && isMobileDevice && !isStandalone && (
        <div
          className="fixed inset-0 z-[80] grid items-end bg-black/70 p-3 sm:items-center sm:justify-items-center"
          onClick={dismissInstallGuide}
        >
          <section
            aria-labelledby="install-guide-title"
            aria-modal="true"
            className="dashboard-card w-full max-w-md rounded-2xl p-5 sm:p-6"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-[#8295ff]">
                  App FlashPost
                </p>
                <h2 id="install-guide-title" className="mt-2 text-lg font-semibold text-[#f5f7fb]">
                  Adicione à tela de início
                </h2>
              </div>
              <button
                aria-label="Fechar instruções"
                className="grid size-9 shrink-0 place-items-center rounded-lg text-[#94a3b8] hover:bg-[#151922]"
                onClick={dismissInstallGuide}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            {isIosDevice ? (
              <ol className="mt-4 space-y-3 text-sm leading-6 text-[#cbd5e1]">
                <li className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#171e31] text-xs text-[#aab7ff]">1</span>
                  No Safari, toque em <Share className="mt-1 inline shrink-0 text-[#aab7ff]" size={15} />{" "}
                  Compartilhar.
                </li>
                <li className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[#171e31] text-xs text-[#aab7ff]">2</span>
                  Escolha “Adicionar à Tela de Início” e confirme em “Adicionar”.
                </li>
              </ol>
            ) : (
              <p className="mt-4 text-sm leading-6 text-[#cbd5e1]">
                {installPrompt
                  ? "Adicione o FlashPost à tela inicial para abrir em modo de aplicativo."
                  : "Abra o menu do navegador e escolha “Instalar app” ou “Adicionar à tela inicial”."}
              </p>
            )}
            <p className="mt-4 rounded-lg border border-[#27334a] bg-[#0d1015] p-3 text-xs leading-5 text-[#94a3b8]">
              {isIosDevice
                ? "Depois de adicionar, abra o ícone FlashPost pela tela de início. O app abrirá sem a barra de endereço."
                : "A instalação mantém sua sessão e abre o FlashPost numa janela própria."}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="min-h-10 rounded-lg px-3 text-sm text-[#94a3b8] hover:bg-[#151922]"
                onClick={dismissInstallGuide}
                type="button"
              >
                Agora não
              </button>
              {!isIosDevice && installPrompt && (
                <button
                  className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[#586eff] px-4 text-sm font-semibold text-white hover:bg-[#7187ff]"
                  onClick={() => void installApp()}
                  type="button"
                >
                  Instalar
                </button>
              )}
              {!isIosDevice && !installPrompt && (
                <button
                  className="min-h-10 rounded-lg bg-[#586eff] px-4 text-sm font-semibold text-white hover:bg-[#7187ff]"
                  onClick={dismissInstallGuide}
                  type="button"
                >
                  Entendi
                </button>
              )}
            </div>
          </section>
        </div>
      )}
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
