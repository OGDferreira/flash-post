import { useEffect, useRef, useState } from "react";
import { useNotices, usePartnerMe } from "@/features/partners/api";
import { playCashSound, unlockCashSound } from "@/lib/cashSound";
import { RevenueBadge } from "@/features/wallet/RevenueBadge";
import { PushPrompt } from "@/components/PushPrompt";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  ChevronDown,
  Plus,
  LogOut,
  Pin,
  PinOff,
  Share,
  Shield,
  X,
} from "lucide-react";
import { buildNavigation } from "./navigation";
import { RefreshFab } from "@/components/RefreshFab";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { BrandLogo, BrandLockup } from "@/components/BrandLogo";
import { APPS, appForPath, lastPath, otherApp, rememberPath, type AppId } from "@/lib/brand";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import type { ShellContext } from "./shellContext";
import { useAuth } from "@/features/auth/AuthProvider";
import { setCsrfToken, apiRequest, reportClientError } from "@/services/api";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";

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
    console.warn("Falcon Post could not read the install-prompt preference.", error);
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
    console.warn("Falcon Post could not save the install-prompt preference.", error);
  }
}

export function AppShell() {
  const { user } = useAuth();
  const location = useLocation();
  const [pinned, setPinned] = useState(() => {
    try {
      return localStorage.getItem("flashpost-sidebar-pinned") === "1";
    } catch {
      return false;
    }
  });
  const [hovered, setHovered] = useState(false);
  const hoverTimer = useRef<number | undefined>(undefined);
  const sidebarOpen = pinned || hovered;
  const openSoon = (next: boolean) => {
    window.clearTimeout(hoverTimer.current);
    // Small intent delay so sweeping the mouse past the rail doesn't flicker it open.
    hoverTimer.current = window.setTimeout(() => setHovered(next), next ? 60 : 220);
  };
  useEffect(() => {
    document.body.dataset.sidebarPinned = pinned ? "1" : "0";
  }, [pinned]);
  const togglePin = () => {
    setPinned((value) => {
      try {
        localStorage.setItem("flashpost-sidebar-pinned", value ? "0" : "1");
      } catch {
        /* storage unavailable */
      }
      return !value;
    });
  };
  const isAdminRoute = location.pathname.startsWith("/admin");
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const workspaceRole =
    isSuperAdmin ? user.workspace_role : user?.role;
  const hasWorkspaceOwnerAccess = workspaceRole === "OWNER";
  // Falcon Post and Falcon Bot share this shell (one session): the path decides the tool,
  // its menu, its palette and its logo. Collaborators only use Falcon Post.
  const app = isAdminRoute || !hasWorkspaceOwnerAccess ? "post" : appForPath(location.pathname);
  const other = otherApp(app);
  // Tool switch inside the menu: the other tool, or both tools from the admin panel.
  const switchApps: AppId[] = !hasWorkspaceOwnerAccess
    ? isAdminRoute ? ["post"] : []
    : isAdminRoute ? ["post", "bot"] : [other];
  const partnerMe = usePartnerMe({ period: "today" }, hasWorkspaceOwnerAccess && !isAdminRoute);
  const isPartner = partnerMe.data?.role === "partner";
  useEffect(() => {
    document.documentElement.dataset.app = app;
    rememberPath(app, location.pathname + location.search);
  }, [app, location.pathname, location.search]);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
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
  const droppedKindTitle: Record<string, string> = {
    suspended: "Conta suspensa pelo Instagram",
    restricted: "Conta com restrição",
    expired: "Conta desconectada",
    manual: "Conta desconectada manualmente",
  };
  const notices = useNotices(Boolean(user) && !isAdminRoute);
  // Cash sound when a new sale/commission notice arrives while the panel is open.
  const lastNotice = useRef<string | null | undefined>(undefined);
  useEffect(() => unlockCashSound(), []);
  useEffect(() => {
    const items = notices.data?.items;
    if (!items) return;
    const newest = items[0]?.id ?? null;
    const seen = lastNotice.current;
    lastNotice.current = newest;
    if (seen === undefined || newest === seen) return; // first load or nothing new
    const fresh = items.slice(0, Math.max(0, items.findIndex((item) => item.id === seen)) || items.length);
    if (fresh.some((item) => !item.read && (item.kind === "sale" || item.kind === "commission"))) {
      playCashSound();
      refreshMoney();
    }
  }, [notices.data]);
  // Revenue and balances refresh the moment a sale arrives: on the push itself (the service
  // worker tells this window) and whenever the app comes back to the foreground.
  const refreshMoney = () => {
    for (const key of [["wallet"], ["finance"], ["analytics"], ["partners", "me"], ["bots"]]) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
  };
  useEffect(() => {
    if (!user) return;
    const onPush = (event: MessageEvent) => {
      if (event.data?.type !== "flashpost-push") return;
      void notices.refetch();
      refreshMoney();
    };
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      void notices.refetch();
      void queryClient.invalidateQueries({ queryKey: ["wallet"] });
    };
    navigator.serviceWorker?.addEventListener("message", onPush);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      navigator.serviceWorker?.removeEventListener("message", onPush);
      document.removeEventListener("visibilitychange", onVisible);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);
  const notificationItems = [
    ...(notices.data?.items ?? []).filter((item) => !item.read).slice(0, 10).map((item) => ({
      title: item.title,
      message: item.body,
    })),
    ...(analyticsNotifications.data?.disconnected_today_accounts ?? []).slice(0, 10).map((item) => ({
      title: droppedKindTitle[item.kind] ?? "Conta desconectada",
      message:
        item.kind === "manual"
          ? `@${item.username} foi desconectada hoje.`
          : `@${item.username} caiu hoje. Reconecte a conta para voltar a publicar.`,
    })),
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
      // Keep the auth query itself (its observer stays attached) and empty it; drop every other
      // cached query. Clearing everything left the screen holding the old user.
      void queryClient.cancelQueries();
      queryClient.setQueryData(["auth", "me"], null);
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
      setMobileOpen(false);
      navigate("/login", { replace: true });
    },
  });
  const navigation = buildNavigation({ isAdminRoute, isSuperAdmin, workspaceRole, pathname: location.pathname, isPartner });
  // The phone bar holds a few shortcuts; everything else lives in "Mais", grouped.
  const sidebarDirect = navigation.groups.length === 0 ? navigation.direct : [];
  const mobileLinks = navigation.direct.slice(0, isAdminRoute ? 4 : 6);
  const mobileOverflow = navigation.direct.slice(mobileLinks.length);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});
  const activeGroupId = navigation.groups.find((group) =>
    group.items.some(({ to }) => location.pathname === to || location.pathname.startsWith(`${to}/`)),
  )?.id;
  useEffect(() => {
    if (activeGroupId) setOpenGroups((current) => (current[activeGroupId] ? current : { ...current, [activeGroupId]: true }));
  }, [activeGroupId]);
  useEffect(() => setMobileOpen(false), [location.pathname]);
  const toggleGroup = (id: string) => setOpenGroups((current) => ({ ...current, [id]: !current[id] }));
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
    const originalConsoleError = console.error.bind(console);
    const formatError = (value: unknown) => {
      if (value instanceof Error) {
        return { message: `${value.name}: ${value.message}`, stack: value.stack };
      }
      if (typeof value === "string") return { message: value };
      try {
        return { message: JSON.stringify(value) ?? String(value) };
      } catch {
        return { message: String(value) };
      }
    };
    const onWindowError = (event: ErrorEvent) => {
      const details = formatError(event.error ?? event.message);
      void reportClientError("browser", details.message, details.stack);
    };
    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const details = formatError(event.reason);
      void reportClientError(
        "browser",
        `Unhandled promise rejection: ${details.message}`,
        details.stack,
      );
    };
    console.error = (...args) => {
      originalConsoleError(...args);
      const details = args.map(formatError);
      const message = details.map(({ message }) => message).join(" ");
      const stack = details
        .map(({ stack }) => stack)
        .filter((value): value is string => Boolean(value))
        .join("\n");
      void reportClientError("browser", `console.error: ${message}`, stack);
    };
    window.addEventListener("error", onWindowError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      console.error = originalConsoleError;
      window.removeEventListener("error", onWindowError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
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
  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex h-[72px] items-center justify-between border-b border-line-soft px-4 lg:px-3 lg:group-data-[open=true]:px-5">
        <Link
          className="flex items-center gap-3 lg:gap-0 lg:group-data-[open=true]:gap-3"
          to={
            hasWorkspaceOwnerAccess
              ? APPS[app].home
              : workspaceRole === "COLLABORATOR"
                ? "/feature/accounts"
                : isSuperAdmin
                  ? "/admin"
                  : "/dashboard"
          }
          onClick={() => setMobileOpen(false)}
        >
          <BrandLogo app={app} className="size-9 shrink-0" />
          <span className="max-w-[160px] overflow-hidden whitespace-nowrap opacity-100 transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:max-w-0 lg:opacity-0 lg:group-data-[open=true]:max-w-[160px] lg:group-data-[open=true]:opacity-100">
            <span className="block font-display text-base font-semibold leading-tight text-fg">{APPS[app].name}</span>
            <span className="block text-[10px] text-muted">{APPS[app].tagline}</span>
          </span>
        </Link>
        <button
          className="grid size-9 place-items-center rounded-lg text-muted hover:bg-well lg:hidden"
          onClick={() => setMobileOpen(false)}
          aria-label="Fechar menu"
        >
          <X size={18} />
        </button>
        <button
          aria-label={pinned ? "Desafixar menu" : "Fixar menu aberto"}
          aria-pressed={pinned}
          className={`hidden size-8 shrink-0 place-items-center rounded-lg transition-opacity duration-200 hover:bg-well lg:group-data-[open=true]:grid ${pinned ? "text-accent" : "text-muted"}`}
          onClick={togglePin}
          title={pinned ? "Desafixar menu" : "Fixar menu aberto"}
          type="button"
        >
          {pinned ? <PinOff size={15} /> : <Pin size={15} />}
        </button>
      </div>

      {isAdminRoute && (
        <div className="mx-4 mt-5 flex items-center gap-2 overflow-hidden rounded-lg border border-line bg-surface-raised px-3 py-2 text-xs font-medium text-fg-2 lg:group-data-[open=true]:mx-3">
          <Shield className="shrink-0 text-accent" size={14} />
          <span className="max-w-[180px] overflow-hidden whitespace-nowrap opacity-100 transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:max-w-0 lg:opacity-0 lg:group-data-[open=true]:max-w-[180px] lg:group-data-[open=true]:opacity-100">
            Administração da plataforma
          </span>
        </div>
      )}

      <nav className="app-sidebar-nav flex-1 space-y-1 overflow-y-auto px-3 py-5">
        {/* Administração (Super Admin) comes last, after the product's own sections. */}
        {[sidebarDirect, navigation.flat].filter((links) => links.length > 0).map((links, index) => (
        <div className={index ? "mt-4 space-y-1 border-t border-line-soft pt-3" : "space-y-1"} key={index}>
          {links.map(({ label, to, icon: Icon }) => (
            <NavLink
              end={to === "/admin" || to === "/dashboard"}
              key={to}
              to={to}
              title={label}
              className={({ isActive }) =>
                `flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition-[color,box-shadow] ${
                  isActive ? "nm-active font-medium" : "nm-hover text-muted"
                }`
              }
            >
              <Icon className="shrink-0" size={17} strokeWidth={1.8} />
              <span className="max-w-[170px] flex-1 overflow-hidden whitespace-nowrap lg:max-w-0 lg:opacity-0 lg:transition-[max-width,opacity] lg:duration-300 lg:group-data-[open=true]:max-w-[170px] lg:group-data-[open=true]:opacity-100">
                {label}
              </span>
            </NavLink>
          ))}
        </div>
        ))}
        {navigation.groups.map((group, index) => (
          <section
            className={index ? "mt-4 space-y-1 border-t border-line-soft pt-3" : "space-y-1"}
            key={group.id}
          >
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted lg:opacity-0 lg:group-data-[open=true]:opacity-100">
              {group.title}
            </p>
            {group.items.map(({ label, to, icon: Icon }) => (
              <NavLink
                end={to === "/dashboard"}
                key={to}
                to={to}
                title={label}
                className={({ isActive }) =>
                  `flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition-[color,box-shadow] ${
                    isActive ? "nm-active font-medium" : "nm-hover text-muted"
                  }`
                }
              >
                <Icon className="shrink-0" size={17} strokeWidth={1.8} />
                <span className="max-w-[170px] flex-1 overflow-hidden whitespace-nowrap lg:max-w-0 lg:opacity-0 lg:transition-[max-width,opacity] lg:duration-300 lg:group-data-[open=true]:max-w-[170px] lg:group-data-[open=true]:opacity-100">
                  {label}
                </span>
              </NavLink>
            ))}
          </section>
        ))}
        {navigation.admin.length > 0 && (
          <div className="mt-4 space-y-1 border-t border-line-soft pt-3">
            <p className="px-3 pb-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted lg:opacity-0 lg:group-data-[open=true]:opacity-100">
              Administração
            </p>
            {navigation.admin.map(({ label, to, icon: Icon }) => (
              <NavLink
                end={to === "/admin"}
                key={to}
                to={to}
                title={label}
                className={({ isActive }) =>
                  `flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm transition-[color,box-shadow] ${
                    isActive ? "nm-active font-medium" : "nm-hover text-muted"
                  }`
                }
              >
                <Icon className="shrink-0" size={17} strokeWidth={1.8} />
                <span className="max-w-[170px] flex-1 overflow-hidden whitespace-nowrap lg:max-w-0 lg:opacity-0 lg:transition-[max-width,opacity] lg:duration-300 lg:group-data-[open=true]:max-w-[170px] lg:group-data-[open=true]:opacity-100">
                  {label}
                </span>
              </NavLink>
            ))}
          </div>
        )}
      </nav>

      <div className="border-t border-line-soft p-3">
        {switchApps.length > 0 && (
          <div className="mb-2 space-y-1 border-b border-line-soft pb-2">
            {switchApps.map((target) => (
              <Link
                aria-label={`Ir para o ${APPS[target].name}`}
                className="app-switch-row flex min-h-11 items-center justify-center gap-3 rounded-xl px-3 text-sm font-medium text-fg-2 lg:px-0 lg:group-data-[open=true]:justify-start lg:group-data-[open=true]:px-3"
                data-target={target}
                key={target}
                onClick={() => setMobileOpen(false)}
                title={`Ir para o ${APPS[target].name} (mesma sessão)`}
                to={lastPath(target)}
              >
                <BrandLogo app={target} className="size-8 shrink-0" />
                <span className="max-w-[150px] flex-1 overflow-hidden whitespace-nowrap opacity-100 transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:max-w-0 lg:opacity-0 lg:group-data-[open=true]:max-w-[150px] lg:group-data-[open=true]:opacity-100">
                  {APPS[target].name}
                </span>
                <ArrowLeftRight className="hidden shrink-0 text-muted lg:group-data-[open=true]:block" size={14} />
              </Link>
            ))}
          </div>
        )}
        <Link
          to="/profile"
          onClick={() => setMobileOpen(false)}
          className="flex items-center justify-center gap-3 rounded-lg px-3 py-3 hover:bg-well lg:px-0 lg:group-data-[open=true]:justify-start lg:group-data-[open=true]:px-3"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt=""
              className="size-9 rounded-full border border-line object-cover"
            />
          ) : (
            <span className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-soft text-sm font-semibold text-accent">
              {(user?.full_name || user?.nickname || "F").slice(0, 1).toUpperCase()}
            </span>
          )}
          <span className="min-w-0 max-w-[145px] flex-1 overflow-hidden whitespace-nowrap opacity-100 transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:max-w-0 lg:opacity-0 lg:group-data-[open=true]:max-w-[145px] lg:group-data-[open=true]:opacity-100">
            <span className="block truncate text-sm font-medium text-fg">
              {user?.full_name}
            </span>
            <span className="block truncate text-xs text-muted">
              {user?.role}
            </span>
          </span>
          <ChevronDown size={15} className="hidden shrink-0 text-muted lg:group-data-[open=true]:block" />
        </Link>
        <button
          onClick={() => {
            logout.mutate();
          }}
          disabled={logout.isPending}
          className="mt-1 flex min-h-10 w-full items-center justify-center gap-3 rounded-lg px-3 text-sm text-muted hover:bg-danger-soft hover:text-danger disabled:opacity-50 lg:px-0 lg:group-data-[open=true]:justify-start lg:group-data-[open=true]:px-3"
        >
          <LogOut className="shrink-0" size={16} />
          <span className="max-w-[120px] overflow-hidden whitespace-nowrap opacity-100 transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] lg:max-w-0 lg:opacity-0 lg:group-data-[open=true]:max-w-[120px] lg:group-data-[open=true]:opacity-100">
            Sair
          </span>
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-transparent text-fg">
      <aside className="glass-bar group fixed inset-y-0 left-0 z-30 hidden w-[68px] !border-y-0 !border-l-0 transition-[width] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] data-[open=true]:w-[252px] lg:block"
        data-open={sidebarOpen}
        onMouseEnter={() => openSoon(true)}
        onMouseLeave={() => openSoon(false)}
      >
        {sidebar}
      </aside>
      <div className={`transition-[padding] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${pinned ? "lg:pl-[252px]" : "lg:pl-[68px]"}`}>
        <header className="app-shell-header glass-bar sticky top-0 z-20 flex items-center justify-between !border-x-0 !border-t-0 px-4 sm:px-6">
          {/* Like SharkBot: the logo and the name, and the revenue pill. Theme lives in
              Configurações and the notices in their own tab (Avisos). */}
          <Link aria-label={APPS[app].name} className="flex min-w-0 flex-1 items-center gap-3" to={isAdminRoute ? "/admin" : APPS[app].home}>
            {isAdminRoute ? (
              <>
                <BrandLogo app={app} className="size-8 shrink-0 lg:hidden" />
                <span className="truncate font-display text-base font-semibold text-fg sm:text-lg">Falcon · Administração</span>
              </>
            ) : (
              <>
                <BrandLockup app={app} className="h-8 lg:hidden" kind="lockup" />
                <BrandLockup app={app} className="hidden h-[18px] lg:block" kind="wordmark" />
              </>
            )}
          </Link>
          <div className="app-header-actions flex shrink-0 items-center gap-1 pl-2">
            <RevenueBadge enabled={hasWorkspaceOwnerAccess && !isAdminRoute} />
          </div>
        </header>
        <main className="app-shell-content min-h-[calc(100dvh-72px)] w-full px-4 py-4 sm:px-6 sm:py-6">
          <PushPrompt />
          <div className="page-enter" key={location.pathname}>
            <ErrorBoundary resetKey={location.pathname}>
              <Outlet context={{ notificationItems } satisfies ShellContext} />
            </ErrorBoundary>
          </div>
        </main>
      </div>
      <RefreshFab />
      {hasWorkspaceOwnerAccess && !isAdminRoute && (
        // Phones: the other tool is one tap away in the bottom-right corner (refresh sits on the left).
        <Link
          aria-label={`Ir para o ${APPS[other].name}`}
          className="glass-bar fixed bottom-[calc(env(safe-area-inset-bottom)+92px)] right-4 z-30 grid size-12 place-items-center rounded-full shadow-lg transition-transform active:scale-95 lg:hidden [body[data-bottom-tabs]_&]:hidden [body[data-flow-editor]_&]:hidden"
          title={`Ir para o ${APPS[other].name}`}
          to={lastPath(other)}
        >
          <BrandLogo app={other} className="size-8" />
        </Link>
      )}
      <nav
        aria-label="Navegação principal"
        className="app-mobile-nav glass-bar fixed z-30 flex gap-0.5 lg:hidden"
      >
        {mobileLinks.map(({ label, short, to, icon: Icon }) => (
          <NavLink
            end={to === "/dashboard" || to === "/admin"}
            key={to}
            to={to}
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) =>
              `group/nav flex min-h-[52px] min-w-0 flex-auto flex-col items-center justify-center gap-1 rounded-[20px] px-0 text-[9px] tracking-[-0.02em] min-[360px]:px-1 min-[360px]:tracking-[-0.01em] min-[360px]:text-[10px] font-medium transition-colors ${
                isActive
                  ? "nm-active"
                  : "text-muted active:text-fg-2"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={`grid h-7 w-10 place-items-center rounded-full transition-[max-width,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] ${
                    isActive ? "text-accent" : ""
                  }`}
                >
                  <Icon size={18} strokeWidth={isActive ? 2.2 : 1.8} />
                </span>
                <span className="max-w-full truncate whitespace-nowrap">{short ?? label}</span>
              </>
            )}
          </NavLink>
        ))}
        <button
          aria-expanded={mobileOpen}
          aria-haspopup="dialog"
          aria-label="Todas as funções"
          className="group/nav flex min-h-[52px] min-w-0 flex-auto flex-col items-center justify-center gap-1 rounded-[20px] px-0 text-[9px] font-medium text-muted active:text-fg-2 min-[360px]:px-1 min-[360px]:text-[10px]"
          onClick={() => setMobileOpen(true)}
          type="button"
        >
          <span className="grid h-7 w-10 place-items-center rounded-full bg-brand text-white">
            <Plus size={18} strokeWidth={2.2} />
          </span>
          <span>Mais</span>
        </button>
      </nav>
      {mobileOpen && (
        <div className="fixed inset-0 z-[60] lg:hidden">
          <button aria-label="Fechar" className="glass-overlay absolute inset-0" onClick={() => setMobileOpen(false)} type="button" />
          <section
            aria-label="Todas as funções"
            aria-modal="true"
            className="glass-modal modal-enter absolute inset-x-0 bottom-0 max-h-[82dvh] overflow-y-auto !rounded-b-none px-4 pb-[calc(env(safe-area-inset-bottom)+16px)] pt-3"
            role="dialog"
          >
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line" />
            {switchApps.length > 0 && (
              <div className={`mb-3 grid gap-2 ${switchApps.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}>
                {switchApps.map((target) => (
                  <Link
                    className="app-switch-row flex min-h-14 items-center gap-3 rounded-xl px-3 text-sm font-medium text-fg"
                    data-target={target}
                    key={target}
                    onClick={() => setMobileOpen(false)}
                    to={lastPath(target)}
                  >
                    <BrandLogo app={target} className="size-9 shrink-0" />
                    <span className="flex-1 truncate">{APPS[target].name}</span>
                    {switchApps.length === 1 && <ArrowLeftRight className="shrink-0 text-muted" size={14} />}
                  </Link>
                ))}
              </div>
            )}
            {(
              [
                [isAdminRoute ? "Administração" : "Funções", [...mobileOverflow, ...navigation.flat]],
              ] as const
            )
              .filter(([, items]) => items.length > 0)
              .map(([title, items], index) => (
                <div className={index ? "mt-3 border-t border-line-soft pt-3" : ""} key={title}>
                  <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{title}</p>
                  <div className="grid grid-cols-2 gap-1">
                    {items.map(({ label, to, icon: Icon }) => (
                      <NavLink
                        className={({ isActive }) =>
                          `flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm ${isActive ? "nm-active font-medium" : "text-fg-2"}`
                        }
                        key={to}
                        to={to}
                      >
                        <Icon className="shrink-0 text-accent" size={16} />
                        <span className="truncate">{label}</span>
                      </NavLink>
                    ))}
                  </div>
                </div>
              ))}
            <div className="mt-1 space-y-1">
              {navigation.groups.map((group) => {
                const open = Boolean(openGroups[group.id]);
                const GroupIcon = group.icon;
                return (
                  <div key={group.id}>
                    <button
                      aria-expanded={open}
                      className="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-fg"
                      onClick={() => toggleGroup(group.id)}
                      type="button"
                    >
                      <GroupIcon className="text-accent" size={18} />
                      <span className="flex-1 text-left">{group.title}</span>
                      <ChevronDown className={`text-muted transition-transform ${open ? "rotate-180" : ""}`} size={16} />
                    </button>
                    {open && (
                      <div className="mb-1 ml-5 space-y-0.5 border-l border-line-soft pl-3">
                        {group.items.map(({ label, to, icon: Icon }) => (
                          <NavLink
                            className={({ isActive }) =>
                              `flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm ${isActive ? "nm-active font-medium" : "text-muted"}`
                            }
                            key={to}
                            to={to}
                          >
                            <Icon size={16} />
                            {label}
                          </NavLink>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
            {navigation.admin.length > 0 && (
              <div className="mt-3 border-t border-line-soft pt-3">
                <p className="mb-1 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">Administração (Super Admin)</p>
                <div className="grid grid-cols-2 gap-1">
                  {navigation.admin.map(({ label, to, icon: Icon }) => (
                    <NavLink
                      className={({ isActive }) =>
                        `flex min-h-11 items-center gap-3 rounded-lg px-3 text-sm ${isActive ? "nm-active font-medium" : "text-fg-2"}`
                      }
                      key={to}
                      to={to}
                    >
                      <Icon className="shrink-0 text-accent" size={16} />
                      <span className="truncate">{label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-3 flex gap-2 border-t border-line-soft pt-3">
              <Link className="btn-secondary flex-1" to="/profile">Perfil</Link>
              <button className="btn-secondary flex-1" disabled={logout.isPending} onClick={() => logout.mutate()} type="button">
                Sair
              </button>
            </div>
          </section>
        </div>
      )}
      {installGuideOpen && isMobileDevice && !isStandalone && (
        <div
          className="glass-overlay fixed inset-0 z-[80] grid items-end p-3 sm:items-center sm:justify-items-center"
          onClick={dismissInstallGuide}
        >
          <section
            aria-labelledby="install-guide-title"
            aria-modal="true"
            className="glass-modal modal-enter w-full max-w-md p-4 sm:p-5"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-[0.14em] text-accent">
                  App Falcon Post
                </p>
                <h2 id="install-guide-title" className="mt-2 text-lg font-semibold text-fg">
                  Adicione à tela de início
                </h2>
              </div>
              <button
                aria-label="Fechar instruções"
                className="grid size-9 shrink-0 place-items-center rounded-lg text-muted hover:bg-well"
                onClick={dismissInstallGuide}
                type="button"
              >
                <X size={17} />
              </button>
            </div>
            {isIosDevice ? (
              <ol className="mt-4 space-y-3 text-sm leading-6 text-fg-2">
                <li className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-soft text-xs text-accent">1</span>
                  No Safari, toque em <Share className="mt-1 inline shrink-0 text-accent" size={15} />{" "}
                  Compartilhar.
                </li>
                <li className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand-soft text-xs text-accent">2</span>
                  Escolha “Adicionar à Tela de Início” e confirme em “Adicionar”.
                </li>
              </ol>
            ) : (
              <p className="mt-4 text-sm leading-6 text-fg-2">
                {installPrompt
                  ? "Adicione o Falcon Post à tela inicial para abrir em modo de aplicativo."
                  : "Abra o menu do navegador e escolha “Instalar app” ou “Adicionar à tela inicial”."}
              </p>
            )}
            <p className="mt-4 rounded-lg border border-line bg-surface p-3 text-xs leading-5 text-muted">
              {isIosDevice
                ? "Depois de adicionar, abra o ícone Falcon Post pela tela de início. O app abrirá sem a barra de endereço."
                : "A instalação mantém sua sessão e abre o Falcon Post numa janela própria."}
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                className="min-h-10 rounded-lg px-3 text-sm text-muted hover:bg-well"
                onClick={dismissInstallGuide}
                type="button"
              >
                Agora não
              </button>
              {!isIosDevice && installPrompt && (
                <button
                  className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-strong"
                  onClick={() => void installApp()}
                  type="button"
                >
                  Instalar
                </button>
              )}
              {!isIosDevice && !installPrompt && (
                <button
                  className="min-h-10 rounded-lg bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-strong"
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
          className="glass-modal modal-enter fixed left-4 right-4 top-[calc(5rem+env(safe-area-inset-top))] z-[95] mx-auto max-w-sm !rounded-2xl !border-success/30 px-4 py-3 text-sm text-success sm:left-auto sm:right-5"
          role="status"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
