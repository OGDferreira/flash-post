/**
 * A tab (or the installed app) left open keeps running the version it loaded. When the person
 * comes back to it, check whether a newer version was published and, if so, reload once, so
 * fixes reach everyone without asking them to close and reopen the app.
 */
const CHECK_EVERY_MS = 5 * 60 * 1000;
let lastCheck = 0;

function currentBundle(): string | null {
  const script = document.querySelector<HTMLScriptElement>('script[type="module"][src*="/assets/index-"]');
  return script ? new URL(script.src).pathname : null;
}

async function publishedBundle(): Promise<string | null> {
  const response = await fetch("/", { cache: "no-store", credentials: "same-origin" });
  if (!response.ok) return null;
  const match = (await response.text()).match(/\/assets\/index-[\w-]+\.js/);
  return match ? match[0] : null;
}

async function check() {
  if (Date.now() - lastCheck < CHECK_EVERY_MS) return;
  lastCheck = Date.now();
  const mine = currentBundle();
  if (!mine) return; // dev server: nothing to compare
  try {
    const live = await publishedBundle();
    if (live && live !== mine) window.location.reload();
  } catch {
    /* offline: try again later */
  }
}

export function startAutoUpdate() {
  lastCheck = Date.now();
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void check();
  });
  window.addEventListener("focus", () => void check());
}
