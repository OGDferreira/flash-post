export type InstagramAnalyticsAccount = {
  account_id: string;
  username: string;
  profile_picture_url: string | null;
  follower_count: number | null;
  media_count: number | null;
  published_posts: number;
  queued_posts: number;
  failed_posts: number;
};

export type InstagramAnalyticsSummary = {
  period: "today" | "yesterday" | "7d" | "30d" | "all";
  followers_count: number | null;
  media_count: number | null;
  active_accounts: number;
  published_posts: number;
  queued_posts: number;
  failed_posts: number;
  accounts: InstagramAnalyticsAccount[];
  daily_publications: { day: string; published_posts: number }[];
};
