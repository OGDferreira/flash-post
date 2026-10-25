export interface ChiefPartner {
  user_id: string;
  user_name: string;
  user_email: string;
  user_nickname: string;
  workspace_id: string;
  workspace_name: string;
  account_count: number;
  folder_count: number;
  loop_count: number;
  since: string;
}

export interface PartnerFolder {
  id: string;
  name: string;
  color: string;
  auto_prefixes: string[];
  auto_enabled: boolean;
  created_at: string;
}

export interface PartnerAccount {
  id: string;
  username: string;
  profile_picture_url: string | null;
  status: string;
  folder_id: string | null;
  follower_count: number | null;
  connected_at: string;
}

export interface PartnerLoop {
  id: string;
  name: string;
  status: string;
  post_type: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  linked: boolean;
  shared: boolean;
  created_at: string;
}

export interface LoopAccount {
  loop_account_id: string;
  account_id: string;
  username: string;
  added_at: string;
}
