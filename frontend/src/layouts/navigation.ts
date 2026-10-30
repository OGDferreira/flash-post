import {
  BarChart3,
  Blocks,
  Bot,
  Bug,
  ChartNoAxesCombined,
  CircleDollarSign,
  Clapperboard,
  CreditCard,
  Folder,
  GitBranch,
  Handshake,
  Home,
  Infinity as InfinityIcon,
  Inbox,
  LayoutDashboard,
  LifeBuoy,
  Mail,
  Megaphone,
  MessageCircle,
  Puzzle,
  Receipt,
  Send,
  Settings,
  Settings2,
  Trophy,
  Users,
  UsersRound,
  Wallet,
  Bell,
  BellRing,
  type LucideIcon,
  Share2,
} from "lucide-react";

import { appForPath, type AppId } from "@/lib/brand";
import type { PartnerPermissions } from "@/features/partners/api";

export type NavItem = { label: string; to: string; icon: LucideIcon; short?: string };
export type NavGroup = { id: string; title: string; icon: LucideIcon; items: NavItem[] };

/** The sócio-restrictable routes, each mapped to the permission that unlocks it.
 *  Routes not listed here are "full panel only": a restricted partner cannot open them. */
export const PARTNER_FEATURE_BY_ROUTE: Record<string, ["post" | "bot", string]> = {
  "/dashboard": ["post", "dashboard"],
  "/feature/ranking": ["post", "ranking"],
  "/feature/accounts": ["post", "accounts"],
  "/feature/meta-apps": ["post", "meta_apps"],
  "/configuracoes": ["post", "settings"],
  "/feature/contacts": ["post", "contacts"],
  "/bot": ["bot", "dashboard"],
  "/bot/vendas": ["bot", "leads"],
  "/carteira": ["bot", "wallet"],
};
// Essential account pages a sócio can always reach.
const PARTNER_ALWAYS_ALLOWED = new Set(["/profile", "/avisos"]);

function matchBase(path: string): string | null {
  const keys = [...Object.keys(PARTNER_FEATURE_BY_ROUTE), ...PARTNER_ALWAYS_ALLOWED];
  // longest match first so "/bot/vendas" wins over "/bot"
  const found = keys
    .filter((key) => path === key || path.startsWith(`${key}/`))
    .sort((a, b) => b.length - a.length)[0];
  return found ?? null;
}

/** Whether a sócio with these permissions may open a path (null permissions = unrestricted). */
export function partnerCanOpen(permissions: PartnerPermissions | null | undefined, path: string): boolean {
  if (!permissions || permissions.full_panel) return true;
  const base = matchBase(path);
  if (base === null) return false;
  if (PARTNER_ALWAYS_ALLOWED.has(base)) return true;
  const [tool, feature] = PARTNER_FEATURE_BY_ROUTE[base];
  return Boolean(permissions[tool]?.[feature]);
}

export const adminLinks: NavItem[] = [
  { label: "Visão geral", short: "Início", to: "/admin", icon: Home },
  { label: "Usuários", to: "/admin/users", icon: Users },
  { label: "Saques dos sócios", short: "Saques", to: "/admin/partner-wallets", icon: Wallet },
  { label: "Gateways de pagamento", short: "Gateways", to: "/bot/gateways", icon: CircleDollarSign },
  { label: "Operações", to: "/admin/operations", icon: BarChart3 },
  { label: "Workspaces", to: "/admin/workspaces", icon: Blocks },
  { label: "Funis", to: "/admin/flows", icon: GitBranch },
  { label: "Premiações", to: "/admin/awards", icon: Trophy },
  { label: "Notificações", to: "/admin/notifications", icon: BellRing },
  { label: "Sistema", to: "/admin/system", icon: Settings2 },
];

// ------------------------------------------------------------------ Flash
// Operational order: accounts, folders, loops and metrics first; team and settings after.

/** Phone bottom bar of Flash. */
const postDirect: NavItem[] = [
  { label: "Painel", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Pastas", to: "/feature/profile-folders", icon: Folder },
  { label: "Loops", to: "/feature/loops", icon: InfinityIcon },
  { label: "Métricas", to: "/feature/analytics", icon: ChartNoAxesCombined },
];

const postGroups: NavGroup[] = [
  {
    id: "visao-geral",
    title: "Visão geral",
    icon: Home,
    items: [
      { label: "Painel", to: "/dashboard", icon: Home },
      { label: "Ranking", to: "/feature/ranking", icon: Trophy },
    ],
  },
  {
    id: "contas",
    title: "Contas",
    icon: Users,
    items: [
      { label: "Contas conectadas", short: "Contas", to: "/feature/accounts", icon: Users },
      { label: "E-mails das contas", short: "E-mails", to: "/feature/emails", icon: Mail },
    ],
  },
  {
    id: "pastas",
    title: "Pastas",
    icon: Folder,
    items: [{ label: "Pastas de perfis", short: "Pastas", to: "/feature/profile-folders", icon: Folder }],
  },
  {
    id: "loops",
    title: "Loops",
    icon: InfinityIcon,
    items: [{ label: "Loops de publicação", short: "Loops", to: "/feature/loops", icon: InfinityIcon }],
  },
  {
    id: "metricas",
    title: "Métricas e relatórios",
    icon: ChartNoAxesCombined,
    items: [
      { label: "Métricas", to: "/feature/analytics", icon: ChartNoAxesCombined },
      { label: "Financeiro", to: "/feature/finance", icon: CircleDollarSign },
    ],
  },
  {
    id: "automacoes",
    title: "Automações e filas",
    icon: Clapperboard,
    items: [
      { label: "Feed", to: "/feature/feed", icon: Clapperboard },
      { label: "Log de erros", to: "/feature/error-logs", icon: Bug },
    ],
  },
  {
    id: "equipe",
    title: "Colaboradores e compartilhamentos",
    icon: UsersRound,
    items: [{ label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound }],
  },
  {
    id: "configuracoes",
    title: "Configurações",
    icon: Settings,
    items: [
      { label: "Apps Meta", to: "/feature/meta-apps", icon: Settings2 },
      { label: "Webhooks", to: "/feature/integrations", icon: Blocks },
      { label: "Extensões", to: "/feature/extensions", icon: Puzzle },
      { label: "Notificações", to: "/feature/notifications", icon: Bell },
      { label: "Avisos", to: "/avisos", icon: Bell },
      { label: "Configurações", to: "/configuracoes", icon: Settings },
    ],
  },
  {
    id: "suporte",
    title: "Suporte",
    icon: LifeBuoy,
    items: [
      { label: "Dúvidas e erros", to: "/feature/support", icon: LifeBuoy },
      { label: "Contatos", to: "/feature/contacts", icon: MessageCircle },
    ],
  },
];

// A sócio (partner) sees a lean Flash: their accounts, the loops shared with them,
// the posts ranking and their revenue. Route guards and the API still enforce permissions.
const partnerPostRoutes = new Set([
  "/dashboard",
  "/feature/accounts",
  "/feature/meta-apps", // their own Meta apps, to connect their own accounts (only they see them)
  "/feature/loops",
  "/feature/ranking",
  "/configuracoes",
  "/avisos",
  "/feature/support",
  "/feature/contacts",
]);

// Only hides what a collaborator cannot open; route guards and the API still
// enforce permissions.
const collaboratorRoutes = new Set([
  "/dashboard",
  "/feature/accounts",
  "/feature/loops",
  "/feature/error-logs",
  "/feature/emails",
  "/feature/extensions",
  "/feature/support",
  "/feature/contacts",
  "/configuracoes",
  "/avisos",
]);

// ------------------------------------------------------------------ Flash
// Funnels, leads, sales, gateways and money. Gateway setup lives apart from daily results.

const botDirect: NavItem[] = [
  { label: "Painel", to: "/bot", icon: LayoutDashboard },
  { label: "Funis", to: "/bot/funis", icon: GitBranch },
  { label: "Bots", to: "/bot/robos", icon: Bot },
  { label: "Vendas", to: "/bot/vendas", icon: Receipt },
  { label: "Carteira", to: "/carteira", icon: Wallet },
];

const botGroups: NavGroup[] = [
  {
    id: "bot-visao",
    title: "Visão geral",
    icon: LayoutDashboard,
    items: [
      { label: "Painel", to: "/bot", icon: LayoutDashboard },
      { label: "Análises", to: "/bot/analises", icon: BarChart3 },
    ],
  },
  {
    id: "bot-funis",
    title: "Funis",
    icon: GitBranch,
    items: [
      { label: "Meus funis", to: "/bot/funis", icon: GitBranch },
      { label: "Pastas de funis", to: "/bot/pastas", icon: GitBranch },
      { label: "Compartilhados comigo", to: "/bot/compartilhados-comigo", icon: Inbox },
      { label: "Que compartilhei", to: "/bot/compartilhei", icon: Share2 },
    ],
  },
  {
    id: "bot-operacao",
    title: "Bots e leads",
    icon: Bot,
    items: [
      { label: "Meus bots", to: "/bot/robos", icon: Bot },
      { label: "Remarketing", to: "/bot/remarketing", icon: Megaphone },
    ],
  },
  {
    id: "bot-vendas",
    title: "Vendas e financeiro",
    icon: Receipt,
    items: [
      { label: "Leads, starts e vendas", short: "Vendas", to: "/bot/vendas", icon: Receipt },
      { label: "Carteira e saques", short: "Carteira", to: "/carteira", icon: Wallet },
    ],
  },
  {
    id: "bot-pagamentos",
    title: "Gateways de pagamento",
    icon: CreditCard,
    items: [{ label: "Gateways", to: "/bot/gateways", icon: CreditCard }],
  },
  {
    id: "bot-socios",
    title: "Sócios e comissões",
    icon: Handshake,
    items: [{ label: "Sócios, convites e comissões", short: "Sócios", to: "/feature/affiliates", icon: Handshake }],
  },
  {
    id: "bot-conta",
    title: "Conta",
    icon: Settings,
    items: [
      { label: "Notificações", to: "/feature/notifications", icon: Send },
      { label: "Avisos", to: "/avisos", icon: Bell },
      { label: "Configurações", to: "/configuracoes", icon: Settings },
    ],
  },
];

// A partner does not invite partners of their own.
const partnerBotHidden = new Set(["/feature/affiliates", "/bot/compartilhei"]);

/** direct = phone shortcuts; groups = titled sidebar and mobile sections. */
export type NavModel = { app: AppId; direct: NavItem[]; flat: NavItem[]; groups: NavGroup[]; admin: NavItem[] };

function only(groups: NavGroup[], keep: (to: string) => boolean): NavGroup[] {
  return groups
    .map((group) => ({ ...group, items: group.items.filter(({ to }) => keep(to)) }))
    .filter(({ items }) => items.length > 0);
}

function buildNavigationFor(opts: {
  isAdminRoute: boolean;
  isSuperAdmin: boolean;
  workspaceRole: string | null | undefined;
  pathname?: string;
  isPartner?: boolean;
  partnerPermissions?: PartnerPermissions | null;
}): NavModel {
  const app = appForPath(opts.pathname ?? "/dashboard");
  if (opts.isAdminRoute) return { app: "post", direct: adminLinks, flat: [], groups: [], admin: [] };
  // Super Admin pages are a plain, always-open section (no collapsible group).
  const admin = opts.isSuperAdmin ? adminLinks : [];
  // A restricted sócio (no full panel) only sees the tabs the admin left on.
  const restricted = Boolean(opts.isPartner) && !opts.partnerPermissions?.full_panel;
  if (opts.workspaceRole === "OWNER") {
    if (restricted) {
      const keep = (to: string) => partnerCanOpen(opts.partnerPermissions, to);
      const groups = app === "bot" ? botGroups : postGroups;
      const direct = app === "bot" ? botDirect : postDirect;
      return { app, direct: direct.filter(({ to }) => keep(to)), flat: [], groups: only(groups, keep), admin };
    }
    if (app === "bot") {
      if (opts.isPartner) {
        return { app, direct: botDirect, flat: [], groups: only(botGroups, (to) => !partnerBotHidden.has(to)), admin };
      }
      return { app, direct: botDirect, flat: [], groups: botGroups, admin };
    }
    if (opts.isPartner) {
      const keep = (to: string) => partnerPostRoutes.has(to);
      return { app, direct: postDirect.filter(({ to }) => keep(to)), flat: [], groups: only(postGroups, keep), admin };
    }
    return { app, direct: postDirect, flat: [], groups: postGroups, admin };
  }
  if (opts.workspaceRole === "COLLABORATOR") {
    const keep = (to: string) => collaboratorRoutes.has(to);
    return { app: "post", direct: postDirect.filter(({ to }) => keep(to)), flat: [], groups: only(postGroups, keep), admin };
  }
  return { app, direct: [], flat: [], groups: [], admin };
}

// Shown only to the Super Admin (the platform's Meta app is managed there).
export const SUPER_ADMIN_ONLY_ROUTES = new Set(["/feature/meta-apps"]);

export function buildNavigation(opts: Parameters<typeof buildNavigationFor>[0]): NavModel {
  const model = buildNavigationFor(opts);
  if (opts.isSuperAdmin) return model;
  const keep = (to: string) => !SUPER_ADMIN_ONLY_ROUTES.has(to);
  return { ...model, direct: model.direct.filter(({ to }) => keep(to)), groups: only(model.groups, keep) };
}
