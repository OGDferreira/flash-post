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

export type NavItem = { label: string; to: string; icon: LucideIcon; short?: string };
export type NavGroup = { id: string; title: string; icon: LucideIcon; items: NavItem[] };

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

// ------------------------------------------------------------------ Falcon Post
// Operational order: accounts, folders, loops and metrics first; team and settings after.

/** Phone bottom bar of Falcon Post. */
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

// A sócio (partner) sees a lean Falcon Post: their accounts, the loops shared with them,
// the posts ranking and their revenue. Route guards and the API still enforce permissions.
const partnerPostRoutes = new Set([
  "/dashboard",
  "/feature/accounts",
  "/feature/loops",
  "/feature/ranking",
  "/configuracoes",
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
]);

// ------------------------------------------------------------------ Falcon Bot
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
    ],
  },
  {
    id: "bot-funis",
    title: "Funis",
    icon: GitBranch,
    items: [
      { label: "Meus funis", to: "/bot/funis", icon: GitBranch },
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

export function buildNavigation(opts: {
  isAdminRoute: boolean;
  isSuperAdmin: boolean;
  workspaceRole: string | null | undefined;
  pathname?: string;
  isPartner?: boolean;
}): NavModel {
  const app = appForPath(opts.pathname ?? "/dashboard");
  if (opts.isAdminRoute) return { app: "post", direct: adminLinks, flat: [], groups: [], admin: [] };
  // Super Admin pages are a plain, always-open section (no collapsible group).
  const admin = opts.isSuperAdmin ? adminLinks : [];
  if (opts.workspaceRole === "OWNER") {
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
