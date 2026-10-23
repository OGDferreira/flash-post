/**
 * Keeps the last data of each screen on this device, so pages open instantly with it and
 * refresh in the background. Bound to the logged-in user: another login (or the Super Admin
 * entering an account) starts from a clean cache; logout erases it.
 */
import { createSyncStoragePersister } from "@tanstack/query-sync-storage-persister";
import type { QueryClient } from "@tanstack/react-query";

const OWNER_KEY = "falcon-cache-owner";

export const cachePersister = createSyncStoragePersister({
  key: "falcon-cache-v1",
  storage: typeof window !== "undefined" ? window.localStorage : undefined,
  throttleTime: 2000,
});

export const persistOptions = {
  persister: cachePersister,
  maxAge: 24 * 60 * 60 * 1000,
  buster: "1",
  dehydrateOptions: {
    // The session itself is always asked to the server; everything else can wait a refresh.
    shouldDehydrateQuery: (query: { queryKey: readonly unknown[]; state: { status: string } }) =>
      query.state.status === "success" && query.queryKey[0] !== "auth",
  },
};

/** Called with the user the server just confirmed: drops data cached for someone else. */
export function claimCache(client: QueryClient, userId: string) {
  let owner: string | null = null;
  try {
    owner = localStorage.getItem(OWNER_KEY);
    localStorage.setItem(OWNER_KEY, userId);
  } catch {
    /* storage unavailable */
  }
  if (owner !== userId) client.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
}

export function forgetCache(client: QueryClient) {
  client.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
  void cachePersister.removeClient();
  try {
    localStorage.removeItem(OWNER_KEY);
  } catch {
    /* storage unavailable */
  }
}
