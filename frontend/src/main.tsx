import { StrictMode } from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";
import { initAppearance } from "@/lib/appearance";
import { applyTheme, getStoredTheme, getTheme } from "@/lib/theme";
import { reloadOnce } from "@/lib/chunkReload";

initAppearance();
{
  // Re-apply the saved theme in case the inline boot script could not read it.
  const saved = getStoredTheme();
  if (saved && saved !== getTheme()) applyTheme(saved);
}

// Vite reports a failed chunk/CSS preload here (typically right after a deploy):
// reload once to pick up the new build instead of breaking the page.
window.addEventListener("vite:preloadError", (event) => {
  if (reloadOnce()) event.preventDefault();
});

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    void navigator.serviceWorker
      .register("/service-worker.js")
      .catch((error: unknown) => {
        console.error("FlashPost could not register its offline app shell.", error);
      });
  });
}

// Installed app: behave like a native app, no pinch or double-tap zoom.
const isStandalone =
  window.matchMedia("(display-mode: standalone)").matches ||
  (navigator as Navigator & { standalone?: boolean }).standalone === true;
if (isStandalone) {
  document
    .querySelector('meta[name="viewport"]')
    ?.setAttribute(
      "content",
      "width=device-width, initial-scale=1, minimum-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover",
    );
  const block = (event: Event) => event.preventDefault();
  document.addEventListener("gesturestart", block);
  document.addEventListener("gesturechange", block);
  document.addEventListener("gestureend", block);
  document.addEventListener(
    "touchmove",
    (event) => {
      if (event.touches.length > 1) event.preventDefault();
    },
    { passive: false },
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      // Remounting a page within 30 s reuses cached data instead of refetching;
      // polling pages still refresh on their own intervals.
      staleTime: 30_000,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
