import { useState } from "react";
import { LogOut, UserRound } from "lucide-react";

import { apiRequest } from "@/services/api";

/** Always-visible strip while a Super Admin is inside someone else's account via "Entrar". */
export function ImpersonationBanner({ userName, adminName }: { userName: string; adminName: string }) {
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

  return (
    <div
      role="status"
      className="fixed inset-x-3 z-[100] mx-auto flex max-w-xl flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-warning/50 bg-surface-raised px-3 py-2 text-sm text-fg shadow-lg sm:inset-x-auto sm:left-1/2 sm:-translate-x-1/2"
      style={{ bottom: "calc(env(safe-area-inset-bottom) + 5.5rem)" }}
    >
      <UserRound size={16} className="shrink-0 text-warning" />
      <span className="min-w-0 flex-1">
        Você ({adminName}) está na conta de <strong className="font-semibold">{userName}</strong>
      </span>
      <button
        className="inline-flex min-h-8 items-center gap-1.5 rounded-lg border border-warning/50 px-3 text-xs font-medium text-warning hover:bg-warning-soft disabled:opacity-60"
        disabled={leaving}
        onClick={() => void leave()}
        type="button"
      >
        <LogOut size={13} />
        {leaving ? "Voltando…" : "Voltar para minha conta"}
      </button>
      {error && <span className="w-full text-xs text-danger">{error}</span>}
    </div>
  );
}
