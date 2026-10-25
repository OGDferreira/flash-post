import { useAuth } from "@/features/auth/AuthProvider";
import type { User } from "@/services/api";

export function usePartnerPermissions() {
  const { user } = useAuth();

  if (!user?.permissions) {
    // Se não há permissões definidas, o usuário tem acesso total (não é sócio)
    return {
      canViewFlashPostDashboard: true,
      canViewFlashPostRanking: true,
      canViewFlashPostAccounts: true,
      canViewFlashPostMetaApps: true,
      canViewFlashPostSettings: true,
      canViewFlashPostContact: true,
      canViewFlashBotDashboard: true,
      canViewFlashBotLeads: true,
      canViewFlashBotWallets: true,
      isPartner: false,
    };
  }

  return {
    canViewFlashPostDashboard: user.permissions.flashpost.can_view_dashboard,
    canViewFlashPostRanking: user.permissions.flashpost.can_view_ranking,
    canViewFlashPostAccounts: user.permissions.flashpost.can_view_accounts,
    canViewFlashPostMetaApps: user.permissions.flashpost.can_view_meta_apps,
    canViewFlashPostSettings: user.permissions.flashpost.can_view_settings,
    canViewFlashPostContact: user.permissions.flashpost.can_view_contact,
    canViewFlashBotDashboard: user.permissions.flashbot.can_view_bot_dashboard,
    canViewFlashBotLeads: user.permissions.flashbot.can_view_leads,
    canViewFlashBotWallets: user.permissions.flashbot.can_view_wallets,
    isPartner: true,
  };
}

export function hasFlashPostPermission(user: User | null, permission: keyof User['permissions']['flashpost']): boolean {
  if (!user) return false;
  if (user.role === "SUPER_ADMIN") return true;
  if (!user.permissions) return true; // Não é sócio, tem acesso total
  return user.permissions.flashpost[permission];
}

export function hasFlashBotPermission(user: User | null, permission: keyof User['permissions']['flashbot']): boolean {
  if (!user) return false;
  if (user.role === "SUPER_ADMIN") return true;
  if (!user.permissions) return true; // Não é sócio, tem acesso total
  return user.permissions.flashbot[permission];
}
