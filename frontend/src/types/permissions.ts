export type PlatformType = "flashpost" | "flashbot";

export interface PartnerPermissions {
  // Flash Post permissions
  can_view_dashboard: boolean;
  can_view_ranking: boolean;
  can_view_accounts: boolean;
  can_view_meta_apps: boolean;
  can_view_settings: boolean;
  can_view_contact: boolean;

  // Flash Bot permissions
  can_view_bot_dashboard: boolean;
  can_view_leads: boolean;
  can_view_wallets: boolean;
}

export interface UserPermissions {
  flashpost: PartnerPermissions;
  flashbot: PartnerPermissions;
}

export interface FeeChangeLog {
  user_id: string;
  user_name: string;
  old_fee: number | null;
  new_fee: number | null;
  is_global_change: boolean;
  reason: string | null;
  changed_by: string | null;
  changed_by_id: string | null;
  created_at: string;
}

export interface UserFeeInfo {
  user_id: string;
  user_name: string;
  current_fee: number | null;
  uses_default: boolean;
}

export interface PartnerFeeInfo {
  user_id: string;
  name: string;
  email: string;
  nickname: string;
  current_fee: number | null;
  chief_name: string | null;
  chief_id: string | null;
}
