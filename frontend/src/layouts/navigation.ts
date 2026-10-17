import {
  BarChart3,
  Blocks,
  Bot,
  Bug,
  ChartNoAxesCombined,
  CircleDollarSign,
  Clapperboard,
  Folder,
  Handshake,
  Home,
  Infinity as InfinityIcon,
  LifeBuoy,
  Mail,
  MessageCircle,
  MessageSquareText,
  Puzzle,
  Send,
  Settings2,
  Trophy,
  Users,
  UsersRound,
  Wallet,
  Bell,
  BellRing,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { label: string; to: string; icon: LucideIcon };
export type NavGroup = { id: string; title: string; icon: LucideIcon; items: NavItem[] };

export const adminLinks: NavItem[] = [
  { label: "Visão geral", to: "/admin", icon: Home },
  { label: "Usuários", to: "/admin/users", icon: Users },
  { label: "Workspaces", to: "/admin/workspaces", icon: Blocks },
  { label: "Operações", to: "/admin/operations", icon: BarChart3 },
  { label: "Notificações", to: "/admin/notifications", icon: BellRing },
  { label: "Sistema", to: "/admin/system", icon: Settings2 },
];

/** Six direct shortcuts, in this exact order (sidebar top and phone bottom bar). */
export const directLinks: NavItem[] = [
  { label: "FlashBot", to: "/feature/bots", icon: Bot },
  { label: "Painel", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Loops", to: "/feature/loops", icon: InfinityIcon },
  { label: "Métricas", to: "/feature/analytics", icon: ChartNoAxesCombined },
  { label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound },
];

const ownerGroups: NavGroup[] = [
  {
    id: "contas",
    title: "Contas",
    icon: Users,
    items: [
      { label: "Hub de contas", to: "/feature/accounts", icon: Users },
      { label: "Pastas de perfis", to: "/feature/profile-folders", icon: Folder },
      { label: "E-mails", to: "/feature/emails", icon: Mail },
      { label: "Log de erros", to: "/feature/error-logs", icon: Bug },
    ],
  },
  {
    id: "publicacao",
    title: "Publicação",
    icon: Send,
    items: [
      { label: "Loops", to: "/feature/loops", icon: InfinityIcon },
      { label: "Feed", to: "/feature/feed", icon: Clapperboard },
      { label: "Automações", to: "/feature/automations", icon: MessageSquareText },
      { label: "FlashBot", to: "/feature/bots", icon: Bot },
    ],
  },
  {
    id: "metricas",
    title: "Métricas",
    icon: ChartNoAxesCombined,
    items: [
      { label: "Analytics", to: "/feature/analytics", icon: ChartNoAxesCombined },
      { label: "Ranking", to: "/feature/ranking", icon: Trophy },
      { label: "Carteira", to: "/carteira", icon: Wallet },
      { label: "Financeiro", to: "/feature/finance", icon: CircleDollarSign },
    ],
  },
  {
    id: "equipe",
    title: "Equipe",
    icon: UsersRound,
    items: [
      { label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound },
      { label: "Sócios", to: "/feature/affiliates", icon: Handshake },
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
    id: "suporte",
    title: "Suporte",
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
]);


/** direct = shortcuts on top; flat = every other page as a plain link; groups = collapsible (admin only). */
export type NavModel = { direct: NavItem[]; flat: NavItem[]; groups: NavGroup[]; admin: NavItem[] };

function flatten(groups: NavGroup[], direct: NavItem[]): NavItem[] {
  const seen = new Set(direct.map(({ to }) => to));
  return groups.flatMap((group) => group.items).filter(({ to }) => !seen.has(to) && seen.add(to));
}

export function buildNavigation(opts: {
  isAdminRoute: boolean;
  isSuperAdmin: boolean;
  workspaceRole: string | null | undefined;
}): NavModel {
  if (opts.isAdminRoute) return { direct: adminLinks, flat: [], groups: [], admin: [] };
  // Super Admin pages are a plain, always-open section (no collapsible group).
  const admin = opts.isSuperAdmin ? adminLinks : [];
  if (opts.workspaceRole === "OWNER") {
    const flat = flatten(ownerGroups, directLinks);
    // "Sócios" sits right under "Colaboradores" (the last shortcut).
    const partners = flat.filter(({ to }) => to === "/feature/affiliates");
    return { direct: directLinks, flat: [...partners, ...flat.filter(({ to }) => to !== "/feature/affiliates")], groups: [], admin };
  }
  if (opts.workspaceRole === "COLLABORATOR") {
    const direct = directLinks.filter(({ to }) => collaboratorRoutes.has(to));
    const allowed = ownerGroups.map((group) => ({ ...group, items: group.items.filter(({ to }) => collaboratorRoutes.has(to)) }));
    return { direct, flat: flatten(allowed, direct), groups: [], admin };
  }
  return { direct: [], flat: [], groups: [], admin };
}
