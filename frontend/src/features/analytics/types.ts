export type InstagramAnalyticsAccount = {
  account_id: string;
  username: string;
  profile_picture_url: string | null;
  follower_count: number | null;
  media_count: number | null;
  published_posts: number;
  queued_posts: number;
  failed_posts: number;
  status: "connected" | "disconnected" | "error";
  leads: number;
  pix_generated: number;
  pix_paid: number;
  pix_paid_amount: string;
};

export type InstagramAnalyticsSummary = {
  period: "today" | "yesterday" | "7d" | "30d" | "all" | "custom";
  followers_count: number | null;
  media_count: number | null;
  views_count: number;
  missing_permissions: string[];
  insights_unavailable: boolean;
  active_accounts: number;
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
};
