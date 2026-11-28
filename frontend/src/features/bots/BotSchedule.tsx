import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ApiError, apiRequest } from "@/services/api";
import type { Bot } from "./types";

/** ISO (UTC) -> value for <input type="datetime-local"> in the viewer's local time. */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** datetime-local value (local time) -> ISO (UTC), or null when empty. */
function toIso(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function fmt(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
}

export function BotSchedule({ bot }: { bot: Bot }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [activateAt, setActivateAt] = useState(toLocalInput(bot.scheduled_activate_at));
  const [deactivateAt, setDeactivateAt] = useState(toLocalInput(bot.scheduled_deactivate_at));
  const [sales, setSales] = useState(
    bot.auto_deactivate_after_sales ? String(bot.auto_deactivate_after_sales) : "",
  );
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      apiRequest<Bot>(`/api/bots/${bot.id}/schedule`, { method: "PUT", body }),
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["bots"] });
    },
    onError: (err: unknown) =>
      setError(err instanceof ApiError ? err.message : "Não foi possível salvar o agendamento."),
  });

  const waiting =
    bot.scheduled_activate_at && new Date(bot.scheduled_activate_at).getTime() > Date.now();

  return (
    <div className="rounded-xl border border-line bg-surface-inset">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-fg-2"
      >
        <CalendarClock size={15} className="text-muted" />
        <span className="flex-1">Agendamento</span>
        {waiting ? (
          <span className="rounded-full bg-amber-400/15 px-2 py-0.5 text-[11px] text-amber-500">
            aguardando {fmt(bot.scheduled_activate_at)}
          </span>
        ) : bot.scheduled_deactivate_at || bot.auto_deactivate_after_sales ? (
          <span className="text-[11px] text-muted">
            desliga {bot.scheduled_deactivate_at ? fmt(bot.scheduled_deactivate_at) : `em ${bot.auto_deactivate_after_sales} vendas`}
          </span>
        ) : (
          <span className="text-[11px] text-muted">opcional</span>
        )}
      </button>
      {open && (
        <div className="space-y-2.5 border-t border-line px-3 py-3 text-sm">
          <p className="text-[11px] text-muted">
            Segure o funil até um horário e ligue sozinho; desligue na hora marcada ou ao
            bater a meta de vendas. Enquanto aguarda, o bot fica pausado.
          </p>
          <label className="grid gap-1 text-fg-2">
            Ligar automaticamente em
            <input
              type="datetime-local"
              className="field"
              value={activateAt}
              onChange={(e) => setActivateAt(e.target.value)}
            />
          </label>
          <label className="grid gap-1 text-fg-2">
            Desligar automaticamente em
            <input
              type="datetime-local"
              className="field"
              value={deactivateAt}
              onChange={(e) => setDeactivateAt(e.target.value)}
            />
          </label>
          <label className="grid gap-1 text-fg-2">
            Ou desligar após (vendas)
            <input
              type="number"
              min={1}
              className="field"
              placeholder="ex.: 100"
              value={sales}
              onChange={(e) => setSales(e.target.value.replace(/[^0-9]/g, ""))}
            />
          </label>
          {error && <p className="text-xs text-danger">{error}</p>}
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              disabled={save.isPending}
              onClick={() =>
                save.mutate({
                  activate_at: toIso(activateAt),
                  deactivate_at: toIso(deactivateAt),
                  deactivate_after_sales: sales ? Number(sales) : null,
                })
              }
            >
              Salvar agendamento
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={save.isPending}
              onClick={() => {
                setActivateAt("");
                setDeactivateAt("");
                setSales("");
                save.mutate({ activate_at: null, deactivate_at: null, deactivate_after_sales: null });
              }}
            >
              Limpar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
