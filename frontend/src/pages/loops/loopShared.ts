
import { ApiError } from "@/services/api";

export type LoopAccount = {
  id: string;
  profile_folder_id: string | null;
  username: string;
  token_expires_at: string;
  connected_at: string;
  error_at: string | null;
  status: "connected" | "disconnected" | "error";
};

export type InstagramMedia = {
  id: string;
  filename: string;
  mime_type: string;
  media_type: "image" | "video";
  size_bytes: number;
  caption: string | null;
  created_at: string;
};

export type InstagramMediaResponse = {
  can_manage: boolean;
  media: InstagramMedia[];
};

export type InstagramFoldersResponse = {
  folders: { id: string; name: string; color: string }[];
};

export type InstagramLoop = {
  id: string;
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  daily_limit_per_account: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  status: "active" | "paused";
  next_run_at: string | null;
  last_run_at: string | null;
  accounts: LoopAccount[];
  active_accounts_count: number;
  media_ids: string[];
  media_names: string[];
  media_count: number;
  video_count: number;
  waiting_for_media_count: number;
  queued_publication_count: number;
  attempts_count: number;
  attempts_today_count: number;
  published_today_count: number;
  failed_today_count: number;
  failed_count: number;
  latest_failed_at: string | null;
};

export type InstagramLoopsResponse = {
  can_manage: boolean;
  can_configure: boolean;
  can_delete: boolean;
  publishing_enabled: boolean;
  loops: InstagramLoop[];
  available_accounts: LoopAccount[];
};

export type PublicationFailure = {
  id: string;
  account_id: string;
  loop_name: string;
  account_username: string;
  media_filename: string | null;
  scheduled_for: string;
  updated_at: string;
  attempts: number;
  error: string;
  account_in_loop: boolean;
  error_category?: string | null;
  account_status?: string | null;
};

export type PublicationFailuresResponse = {
  failures: PublicationFailure[];
};

export type FailureAccountGroup = {
  accountId: string;
  username: string;
  loopNames: string[];
  failures: PublicationFailure[];
  inLoop: boolean;
  accountStatus: string | null;
};

export function groupFailuresByAccount(failures: PublicationFailure[]): FailureAccountGroup[] {
  const groups = new Map<string, FailureAccountGroup>();
  for (const failure of failures) {
    const group = groups.get(failure.account_id) ?? {
      accountId: failure.account_id,
      username: failure.account_username,
      loopNames: [],
      failures: [],
      inLoop: false,
      accountStatus: failure.account_status ?? null,
    };
    group.failures.push(failure);
    if (!group.loopNames.includes(failure.loop_name)) group.loopNames.push(failure.loop_name);
    group.inLoop = group.inLoop || failure.account_in_loop;
    groups.set(failure.account_id, group);
  }
  return [...groups.values()];
}

export type LoopForm = {
  name: string;
  interval_min_minutes: number;
  interval_max_minutes: number;
  daily_limit_per_account: number;
  post_type: "reels" | "images" | "both";
  repeat_media: boolean;
  account_ids: string[];
  media_ids: string[];
};

export const emptyForm: LoopForm = {
  name: "",
  interval_min_minutes: 20,
  interval_max_minutes: 40,
  daily_limit_per_account: 24,
  post_type: "reels",
  repeat_media: true,
  account_ids: [],
  media_ids: [],
};

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export function formatDate(value: string | null): string {
  if (!value) return "Aguardando execução do agendador";
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
}

export function apiErrorMessage(error: unknown, fallback: string): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : fallback;
}

export function mediaFitsLoop(media: InstagramMedia, postType: LoopForm["post_type"]): boolean {
  return (
    postType === "both" ||
    (postType === "reels" && media.media_type === "video") ||
    (postType === "images" && media.media_type === "image")
  );
}

export function fileFitsLoop(file: File, postType: LoopForm["post_type"]): boolean {
  return (
    (file.type === "video/mp4" && (postType === "reels" || postType === "both")) ||
    (file.type === "image/jpeg" && (postType === "images" || postType === "both"))
  );
}
