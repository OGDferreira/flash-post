// After a deploy the hashed page chunks change; a tab opened before it (or the
// installed app) still points at the old files, which no longer exist. The only
// fix is loading the new index.html, so we reload once instead of showing an error.

const RELOAD_KEY = "flashpost-auto-reload-at";
const RELOAD_GUARD_MS = 30_000;

export function isChunkLoadError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|ChunkLoadError|Loading chunk|Unable to preload CSS|module script.*MIME/i.test(
    text,
  );
}

/**
 * Reloads the page unless it already auto-reloaded in the last 30 s (prevents
 * reload loops). Returns false when it did not reload, so the caller can show
 * the manual "Recarregar" screen instead.
 */
export function reloadOnce(): boolean {
  try {
    const last = Number(window.sessionStorage.getItem(RELOAD_KEY) ?? 0);
    if (Date.now() - last < RELOAD_GUARD_MS) return false;
    window.sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    return false; // no storage = no loop guard, so never reload automatically
  }
  window.location.reload();
  return true;
}

/** Wraps a lazy page import: a missing chunk triggers one automatic reload. */
export function importWithReload<T>(load: () => Promise<T>): () => Promise<T> {
  return () =>
    load().catch((error: unknown) => {
      if (isChunkLoadError(error) && reloadOnce()) {
        return new Promise<T>(() => {}); // keep the loader on screen while the page reloads
      }
      throw error;
    });
}
