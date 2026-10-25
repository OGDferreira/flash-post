import { useState } from "react";

import { apiRequest } from "@/services/api";

/** While the Super Admin is inside someone's account: a round Flash Adm button (blue and
 *  purple) that goes back to the admin panel. On phones it sits left of the Flash/Bot
 *  switch; on computers, left of the refresh button. */
export function ImpersonationBanner({ userName }: { userName: string; adminName: string }) {
  const [leaving, setLeaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function leave() {
    setLeaving(true);
    setError(null);
    try {
      await apiRequest("/api/auth/impersonation/stop", { method: "POST" });
      // Full reload so no cached data from the user's account survives.
      window.location.assign("/admin/users");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível voltar.");
      setLeaving(false);
    }
  }

  const label = `Na conta de ${userName} · voltar ao Flash Adm`;
  return (
    <div className="fixed bottom-[calc(env(safe-area-inset-bottom)+92px)] right-[76px] z-[100] flex flex-col items-end gap-1 lg:bottom-6 lg:right-[88px] [body[data-flow-editor]_&]:hidden">
      {error && <span className="rounded-lg bg-surface-raised px-2 py-1 text-[11px] text-danger shadow">{error}</span>}
      <button
        aria-label={label}
        className="falcon-adm-ring grid size-12 place-items-center rounded-full p-[2px] shadow-lg transition-transform active:scale-95 disabled:opacity-60"
        disabled={leaving}
        onClick={() => void leave()}
        title={label}
        type="button"
      >
        <span className="grid size-full place-items-center rounded-full bg-[var(--nm-bg)]">
          <img alt="" className={`size-8 ${leaving ? "animate-pulse" : ""}`} draggable={false} src="/brand/flash-emblem.svg" />
        </span>
      </button>
    </div>
  );
}
