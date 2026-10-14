import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

type AccountState =
  | "publishing"
  | "queued"
  | "scheduled"
  | "due"
  | "daily_limit"
  | "loop_paused"
  | "disconnected"
  | "needs_review"
  | "no_media"
  | "instagram_cap"
  | "failing";

type AccountProgress = {
  account_id: string;
  username: string;
  published_today: number;
  failed_today: number;
  target: number;
  token_expires_at: string;
  state: AccountState;
  connection_status: string;
  in_loop: boolean;
  next_run_at: string | null;
  last_published_at: string | null;
  next_video_number: number | null;
  playlist_size: number;
  cycles_completed: number;
  last_error: string | null;
  last_error_at: string | null;
  review_job_id: string | null;
};

type LoopHealth = {
  target_per_account: number;
  accounts: AccountProgress[];
};

const stateLabel: Record<AccountState, { text: string; tone: "ok" | "info" | "warn" | "error" }> = {
  publishing: { text: "Publicando agora", tone: "ok" },
  queued: { text: "Na fila", tone: "ok" },
  scheduled: { text: "Aguardando intervalo", tone: "info" },
  due: { text: "Será enviada no próximo ciclo", tone: "info" },
  daily_limit: { text: "Limite diário atingido", tone: "warn" },
  loop_paused: { text: "Loop pausado", tone: "warn" },
  disconnected: { text: "Conta desconectada", tone: "error" },
  needs_review: { text: "Verificar no Instagram", tone: "error" },
  no_media: { text: "Sem vídeos no loop", tone: "warn" },
  instagram_cap: { text: "Limite de 100/24 h da Meta", tone: "warn" },
  failing: { text: "Falha na última publicação", tone: "error" },
};

const toneClass = {
  ok: "bg-[#2dd4a0]/12 text-[#7ee2bd]",
  info: "bg-[#536dfe]/14 text-[#aab7ff]",
  warn: "bg-[#f2d48a]/12 text-[#f2d48a]",
  error: "bg-[#f16f82]/12 text-[#f1a3ad]",
};

const timeFormat = new Intl.DateTimeFormat("pt-BR", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  timeZone: "America/Sao_Paulo",
});

function when(value: string | null) {
  return value ? timeFormat.format(new Date(value)) : "—";
}

export function LoopHealthPanel({ loopId }: { loopId: string }) {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const health = useQuery({
    queryKey: ["loops", "health", loopId],
    queryFn: () => apiRequest<LoopHealth>(`/api/loops/${loopId}/health`),
    enabled: open,
    refetchInterval: open ? 60_000 : false,
  });
  const resolve = useMutation({
    mutationFn: ({ jobId, published }: { jobId: string; published: boolean }) =>
      published
        ? apiRequest(`/api/loops/jobs/${jobId}/confirm-published`, { method: "POST" })
        : apiRequest("/api/loops/failures/retry", { method: "POST", body: { job_ids: [jobId] } }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["loops"] }),
  });
  const accounts = [...(health.data?.accounts ?? [])].sort((a, b) => {
    const rank = (item: AccountProgress) =>
      item.state === "needs_review" || item.state === "disconnected" || item.state === "failing" ? 0 : 1;
    return rank(a) - rank(b) || a.username.localeCompare(b.username);
  });

  return (
    <div className="mt-3">
      <button
        aria-expanded={open}
        className="text-xs text-[#aab7ff] hover:text-white"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        {open ? "Ocultar status por conta" : "Ver status e progresso por conta"}
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          {health.isLoading && (
            <div className="space-y-2" aria-busy="true">
              <div className="skeleton h-14" />
              <div className="skeleton h-14" />
            </div>
          )}
          {health.error && (
            <p className="text-xs text-[#f1a3ad]">Não foi possível carregar o status das contas.</p>
          )}
          {health.data && accounts.length === 0 && (
            <p className="text-xs text-[#94a3b8]">Nenhuma conta neste loop.</p>
          )}
          {accounts.map((account) => {
            const label = stateLabel[account.state] ?? stateLabel.due;
            const percent = Math.min(100, (account.published_today / Math.max(account.target, 1)) * 100);
            return (
              <div
                className="rounded-xl border border-line-soft bg-surface-inset p-3"
                key={account.account_id}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-sm font-medium text-[#dbe4f3]">@{account.username}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${toneClass[label.tone]}`}>
                    {label.text}
                  </span>
                </div>
                <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[11px] text-[#94a3b8] sm:grid-cols-4">
                  <span>
                    Hoje: <strong className="text-[#dbe4f3]">{account.published_today}/{account.target}</strong>
                  </span>
                  <span>
                    Próximo vídeo:{" "}
                    <strong className="text-[#dbe4f3]">
                      {account.next_video_number ? `${account.next_video_number} de ${account.playlist_size}` : "—"}
                    </strong>
                  </span>
                  <span>Última publicação: {when(account.last_published_at)}</span>
                  <span>
                    {account.state === "daily_limit" ? "Retoma: " : "Próximo envio: "}
                    {account.state === "publishing" || account.state === "queued" ? "agora" : when(account.next_run_at)}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded bg-white/5">
                  <div className="h-full rounded bg-gradient-to-r from-[#536dfe] to-[#00c9d8]" style={{ width: `${percent}%` }} />
                </div>
                {account.cycles_completed > 0 && (
                  <p className="mt-1.5 text-[11px] text-[#64748b]">
                    {account.cycles_completed} ciclo(s) completo(s) da playlist
                  </p>
                )}
                {account.last_error && (account.state === "failing" || account.state === "disconnected" || account.state === "needs_review") && (
                  <p className="mt-1.5 break-words text-[11px] leading-4 text-[#f1a3ad]">
                    {account.last_error}
                    {account.last_error_at ? ` (${when(account.last_error_at)})` : ""}
                  </p>
                )}
                {account.state === "needs_review" && account.review_job_id && (
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      className="btn-secondary !min-h-9 !px-3 text-xs"
                      disabled={resolve.isPending}
                      onClick={() => resolve.mutate({ jobId: account.review_job_id!, published: true })}
                      type="button"
                    >
                      O vídeo foi publicado
                    </button>
                    <button
                      className="btn-ghost !min-h-9 !px-3 text-xs"
                      disabled={resolve.isPending}
                      onClick={() => resolve.mutate({ jobId: account.review_job_id!, published: false })}
                      type="button"
                    >
                      Não apareceu — tentar de novo
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
