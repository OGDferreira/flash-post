import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

type AccountProgress = {
  account_id: string;
  username: string;
  published_today: number;
  failed_today: number;
  target: number;
  token_expires_at: string;
};

type LoopHealth = {
  target_per_account: number;
  accounts: AccountProgress[];
};

export function LoopHealthPanel({ loopId }: { loopId: string }) {
  const [open, setOpen] = useState(false);
  const health = useQuery({
    queryKey: ["loops", "health", loopId],
    queryFn: () => apiRequest<LoopHealth>(`/api/loops/${loopId}/health`),
    enabled: open,
    refetchInterval: open ? 60_000 : false,
  });
  const accounts = [...(health.data?.accounts ?? [])].sort(
    (a, b) => a.published_today - b.published_today,
  );

  return (
    <div className="mt-3">
      <button
        aria-expanded={open}
        className="text-xs text-[#aab7ff] hover:text-white"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        {open ? "Ocultar meta diária por conta" : "Ver meta diária por conta"}
      </button>
      {open && (
        <div className="mt-2 space-y-2">
          {health.isLoading && <p className="text-xs text-[#94a3b8]">Carregando…</p>}
          {health.error && (
            <p className="text-xs text-[#f1a3ad]">Não foi possível carregar a meta diária.</p>
          )}
          {accounts.map((account) => {
            const percent = Math.min(100, (account.published_today / account.target) * 100);
            const late = account.published_today < account.target / 2;
            return (
              <div key={account.account_id}>
                <div className="flex justify-between text-xs">
                  <span className="text-[#dbe4f3]">@{account.username}</span>
                  <span className={late ? "text-[#f2d48a]" : "text-[#a9e5c0]"}>
                    {account.published_today}/{account.target}
                    {account.failed_today > 0 ? ` · ${account.failed_today} falhas` : ""}
                  </span>
                </div>
                <div className="mt-1 h-1.5 overflow-hidden rounded bg-[#1b2433]">
                  <div
                    className={`h-full ${late ? "bg-[#f2d48a]" : "bg-[#3ecf8e]"}`}
                    style={{ width: `${percent}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
