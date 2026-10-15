export type InstagramAnalyticsAccount = {
  account_id: string;
  username: string;
  profile_picture_url: string | null;
  follower_count: number | null;
  follows_count: number | null;
  media_count: number | null;
  insights: Record<string, number | null>;
  insights_metric_errors: Record<string, string>;
  published_posts: number;
  queued_posts: number;
  failed_posts: number;
  status: "connected" | "disconnected" | "error";
  insights_error: string | null;
  profile_metrics_error: string | null;
  leads: number;
  pix_generated: number;
  pix_paid: number;
  pix_paid_amount: string;
  /** Lifetime (cumulative) views of videos published in the period. */
  views_count: number | null;
  /** Views that happened during the period (account Insights). */
  period_views_count: number | null;
};

export type InstagramAnalyticsSummary = {
  period: "today" | "yesterday" | "7d" | "30d" | "all" | "custom";
  followers_count: number | null;
  media_count: number | null;
  /** Cumulative: lifetime views of the videos published in the period. null = unavailable. */
  views_count: number | null;
  /** Daily/period metric: views that happened in the period. null = unavailable. */
  period_views_count: number | null;
  views_partial: boolean;
  insights_checked: boolean;
  missing_permissions: string[];
  insights_unavailable: boolean;
  profile_metrics_unavailable: boolean;
  active_accounts: number;
  errored_accounts: number;
  disconnected_accounts: number;
  expired_accounts: number;
  active_collaborators: number;
  published_posts: number;
  queued_posts: number;
  failed_posts: number;
  owner_connections_today: number;
  team_connections_today: number;
  leads: number;
  pix_generated: number;
  pix_paid: number;
  pix_paid_amount: string;
  accounts: InstagramAnalyticsAccount[];
  daily_publications: { day: string; published_posts: number }[];
  daily_revenue: { day: string; amount: string }[];
  daily_account_connections: { day: string; connected_accounts: number }[];
  account_connection_ranking: ConnectionRankItem[];
  account_connection_ranking_today: ConnectionRankItem[];
  account_connection_ranking_month: ConnectionRankItem[];
  connected_today: number;
  disconnected_today: number;
  connected_period: number;
  disconnected_period: number;
  disconnected_period_accounts: {
    username: string;
    kind: "expired" | "restricted" | "suspended" | "manual";
    reason: string | null;
    at: string | null;
  }[];
  disconnected_today_accounts: {
    username: string;
    kind: "expired" | "restricted" | "suspended" | "manual";
    reason: string | null;
    at: string | null;
  }[];
};

export type ConnectionRankItem = {
  user_id: string;
  full_name: string;
  role: "OWNER" | "COLLABORATOR";
  connected_accounts: number;
  avatar_url: string | null;
};
