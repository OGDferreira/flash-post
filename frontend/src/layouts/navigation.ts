import {
  Blocks,
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
  MessageSquareText,
  Puzzle,
  Send,
  Settings2,
  Shield,
  Trophy,
  Users,
  UsersRound,
  Bell,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { label: string; to: string; icon: LucideIcon };
export type NavGroup = { id: string; title: string; icon: LucideIcon; items: NavItem[] };

export const adminLinks: NavItem[] = [
  { label: "Visão geral", to: "/admin", icon: Home },
  { label: "Usuários", to: "/admin/users", icon: Users },
  { label: "Workspaces", to: "/admin/workspaces", icon: Blocks },
  { label: "Sistema", to: "/admin/system", icon: Settings2 },
];

/** Six direct shortcuts, in this exact order (sidebar top and phone bottom bar). */
export const directLinks: NavItem[] = [
  { label: "Painel", to: "/dashboard", icon: Home },
  { label: "Contas", to: "/feature/accounts", icon: Users },
  { label: "Pastas", to: "/feature/profile-folders", icon: Folder },
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
    ],
  },
  {
    id: "metricas",
    title: "Métricas",
    icon: ChartNoAxesCombined,
    items: [
      { label: "Analytics", to: "/feature/analytics", icon: ChartNoAxesCombined },
      { label: "Ranking", to: "/feature/ranking", icon: Trophy },
      { label: "Financeiro", to: "/feature/finance", icon: CircleDollarSign },
    ],
  },
  {
    id: "equipe",
    title: "Equipe",
    icon: UsersRound,
    items: [
      { label: "Colaboradores", to: "/feature/collaborators", icon: UsersRound },
      { label: "Filiados", to: "/feature/affiliates", icon: Handshake },
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
]);

const adminGroup: NavGroup = { id: "admin", title: "Administração", icon: Shield, items: adminLinks };

export type NavModel = { direct: NavItem[]; groups: NavGroup[] };

export function buildNavigation(opts: {
  isAdminRoute: boolean;
  isSuperAdmin: boolean;
  workspaceRole: string | null | undefined;
}): NavModel {
  if (opts.isAdminRoute) return { direct: adminLinks, groups: [] };
  const extra = opts.isSuperAdmin ? [adminGroup] : [];
  if (opts.workspaceRole === "OWNER") return { direct: directLinks, groups: [...ownerGroups, ...extra] };
  if (opts.workspaceRole === "COLLABORATOR") {
    return {
      direct: directLinks.filter(({ to }) => collaboratorRoutes.has(to)),
      groups: ownerGroups
        .map((group) => ({ ...group, items: group.items.filter(({ to }) => collaboratorRoutes.has(to)) }))
        .filter((group) => group.items.length > 0)
        .concat(extra),
    };
  }
  return { direct: [], groups: extra };
}
