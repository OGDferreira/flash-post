import {
  BarChart3,
  Blocks,
  Bug,
  ChartNoAxesCombined,
  CircleDollarSign,
  Clapperboard,
  Folder,
  GitBranch,
  Handshake,
  Home,
  Infinity as InfinityIcon,
  LifeBuoy,
  Mail,
  MessageCircle,
  MessageSquareText,
  Puzzle,
  Settings,
  Settings2,
  Trophy,
  Users,
  UsersRound,
  Wallet,
  Bell,
  BellRing,
  type LucideIcon,
} from "lucide-react";

import { FlashBotGlyph } from "@/components/FlashBotLogo";

// The FlashBot brand mark stands in for a lucide icon in the menus.
const FlashBotIcon = FlashBotGlyph as unknown as LucideIcon;

export type NavItem = { label: string; to: string; icon: LucideIcon; short?: string };
export type NavGroup = { id: string; title: string; icon: LucideIcon; items: NavItem[] };

export const adminLinks: NavItem[] = [
  { label: "Visão geral", short: "Início", to: "/admin", icon: Home },
  { label: "Usuários", to: "/admin/users", icon: Users },
  { label: "Saques dos sócios", short: "Saques", to: "/admin/partner-wallets", icon: Wallet },
  { label: "Gateways de pagamento", short: "Gateways", to: "/feature/bots?tab=gateways", icon: CircleDollarSign },
  { label: "Operações", to: "/admin/operations", icon: BarChart3 },
  { label: "Workspaces", to: "/admin/workspaces", icon: Blocks },
  { label: "Funis", to: "/admin/flows", icon: GitBranch },
  { label: "Premiações", to: "/admin/awards", icon: Trophy },
  { label: "Notificações", to: "/admin/notifications", icon: BellRing },
  { label: "Sistema", to: "/admin/system", icon: Settings2 },
];

/** Six direct shortcuts for the phone bottom bar. */
export const directLinks: NavItem[] = [
  { label: "FlashBot", to: "/feature/bots", icon: FlashBotIcon },
  { label: "Painel", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Loops", to: "/feature/loops", icon: InfinityIcon },
  { label: "Métricas", to: "/feature/analytics", icon: ChartNoAxesCombined },
  { label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound },
];

const ownerGroups: NavGroup[] = [
  {
    id: "visao-geral",
    title: "Visão geral",
    icon: Home,
    items: [
      { label: "Painel", to: "/dashboard", icon: Home },
      { label: "Métricas", to: "/feature/analytics", icon: ChartNoAxesCombined },
      { label: "Ranking", to: "/feature/ranking", icon: Trophy },
    ],
  },
  {
    id: "vendas",
    title: "Vendas",
    icon: CircleDollarSign,
    items: [
      { label: "Carteira", to: "/carteira", icon: Wallet },
      { label: "Financeiro", to: "/feature/finance", icon: CircleDollarSign },
      { label: "Sócios", to: "/feature/affiliates", icon: Handshake },
    ],
  },
  {
    id: "automacoes",
    title: "Automações",
    icon: InfinityIcon,
    items: [
      { label: "FlashBot", to: "/feature/bots", icon: FlashBotIcon },
      { label: "Loops", to: "/feature/loops", icon: InfinityIcon },
      { label: "Feed", to: "/feature/feed", icon: Clapperboard },
      { label: "Automações", to: "/feature/automations", icon: MessageSquareText },
    ],
  },
  {
    id: "integracoes",
    title: "Integrações",
    icon: Blocks,
    items: [
      { label: "Webhooks", to: "/feature/integrations", icon: Blocks },
      { label: "Apps Meta", to: "/feature/meta-apps", icon: Settings2 },
      { label: "Extensões", to: "/feature/extensions", icon: Puzzle },
    ],
  },
  {
    id: "conta",
    title: "Conta",
    icon: Users,
    items: [
      { label: "Hub de contas", to: "/feature/accounts", icon: Users },
      { label: "Pastas de perfis", to: "/feature/profile-folders", icon: Folder },
      { label: "E-mails", to: "/feature/emails", icon: Mail },
      { label: "Log de erros", to: "/feature/error-logs", icon: Bug },
      { label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound },
      { label: "Configurações", to: "/configuracoes", icon: Settings },
    ],
  },
  {
    id: "navegacao",
    title: "Navegação",
    icon: LifeBuoy,
    items: [
      { label: "Dúvidas e erros", to: "/feature/support", icon: LifeBuoy },
      { label: "Contatos", to: "/feature/contacts", icon: MessageCircle },
      { label: "Notificações", to: "/feature/notifications", icon: Bell },
    ],
  },
];

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


/** direct = phone shortcuts; groups = titled sidebar and mobile sections. */
export type NavModel = { direct: NavItem[]; flat: NavItem[]; groups: NavGroup[]; admin: NavItem[] };

export function buildNavigation(opts: {
  isAdminRoute: boolean;
  isSuperAdmin: boolean;
  workspaceRole: string | null | undefined;
}): NavModel {
  if (opts.isAdminRoute) return { direct: adminLinks, flat: [], groups: [], admin: [] };
  // Super Admin pages are a plain, always-open section (no collapsible group).
  const admin = opts.isSuperAdmin ? adminLinks : [];
  if (opts.workspaceRole === "OWNER") {
    return { direct: directLinks, flat: [], groups: ownerGroups, admin };
  }
  if (opts.workspaceRole === "COLLABORATOR") {
    const direct = directLinks.filter(({ to }) => collaboratorRoutes.has(to));
    const allowed = ownerGroups.map((group) => ({ ...group, items: group.items.filter(({ to }) => collaboratorRoutes.has(to)) }));
    return { direct, flat: [], groups: allowed.filter(({ items }) => items.length > 0), admin };
  }
  return { direct: [], flat: [], groups: [], admin };
}
