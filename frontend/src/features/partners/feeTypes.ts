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
