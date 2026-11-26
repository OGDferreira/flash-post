import { createContext, useContext, type ReactNode } from "react";

/**
 * The flow editor and its media/group pickers normally talk to the owner's `/api/bots`
 * endpoints. A bot partner edits the same funnel through `/api/bot-partners/shared/{botId}`,
 * which is authorised by the partnership and scoped to that one bot. This context swaps the
 * URLs (and the react-query cache keys) so the very same editor serves both.
 */
export type BotApi = {
  flowUrl: (flowId: string) => string;
  summaryUrl: (flowId: string) => string;
  mediaListUrl: string;
  mediaUploadUrl: (filename: string) => string;
  mediaPreviewUrl: (id: string) => string;
  groupsUrl: string;
  /** Namespace for the media react-query cache, so owner and partner caches never collide. */
  mediaKey: string[];
  /** Hide the "Bots" section (bot↔funnel wiring) — a partner does not reassign the owner's bots. */
  showBotsSection: boolean;
};

export const ownerBotApi: BotApi = {
  flowUrl: (flowId) => `/api/bots/flows/${flowId}`,
  summaryUrl: (flowId) => `/api/bots/flows/${flowId}/summary`,
  mediaListUrl: "/api/bots/media/list",
  mediaUploadUrl: (filename) => `/api/bots/media?filename=${encodeURIComponent(filename)}`,
  mediaPreviewUrl: (id) => `/api/bots/media/${id}/preview`,
  groupsUrl: "/api/bots/groups/list",
  mediaKey: ["bots", "media"],
  showBotsSection: true,
};

export function partnerBotApi(botId: string): BotApi {
  const base = `/api/bot-partners/shared/${botId}`;
  return {
    flowUrl: (flowId) => `${base}/flows/${flowId}`,
    summaryUrl: (flowId) => `${base}/flows/${flowId}/summary`,
    mediaListUrl: `${base}/media/list`,
    mediaUploadUrl: (filename) => `${base}/media?filename=${encodeURIComponent(filename)}`,
    mediaPreviewUrl: (id) => `${base}/media/${id}/preview`,
    groupsUrl: `${base}/groups/list`,
    mediaKey: ["bot-partners", botId, "media"],
    showBotsSection: false,
  };
}

const BotApiContext = createContext<BotApi>(ownerBotApi);

export function BotApiProvider({ value, children }: { value: BotApi; children: ReactNode }) {
  return <BotApiContext.Provider value={value}>{children}</BotApiContext.Provider>;
}

export function useBotApi(): BotApi {
  return useContext(BotApiContext);
}
