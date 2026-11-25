import { useQuery } from "@tanstack/react-query";
import { Layers, TrendingUp, Users, Wallet } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

type FunnelBot = {
  bot_id: string;
  bot_name: string;
  leads: number;
  pix: number;
  sales: number;
  entry_pix: number;
  entry_sales: number;
  upsell_sales: number;
  revenue: number;
  lead_to_pix: number | null;
  pix_to_sale: number | null;
  upsells: { step: number; offered: number; pix: number; paid: number; revenue: number; take_rate: number | null }[];
};

const count = (value: number) => new Intl.NumberFormat("pt-BR").format(value);
const brl = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
const rate = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("pt-BR")}%`);

/** One stage of the per-bot funnel: a labelled count with a proportional bar. */
function Stage({ icon, label, value, hint, fill, width }: {
  icon: React.ReactNode; label: string; value: string; hint?: string; fill: string; width: number;
}) {
  return (
    <div className="min-w-0 flex-1 rounded-xl border border-line-soft bg-surface-inset p-3">
      <p className="flex items-center gap-1.5 text-[11px] text-muted">
        <span className="text-accent">{icon}</span>
        {label}
      </p>
      <p className="mt-1 text-xl font-bold text-fg tabular-nums">{value}</p>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-well">
        <div className="h-full rounded-full" style={{ width: `${Math.max(value === "0" ? 0 : 4, width)}%`, background: fill }} />
      </div>
      {hint && <p className="mt-1.5 truncate text-[10px] text-muted">{hint}</p>}
    </div>
  );
}

/** Flash bot funnel per bot, as cards: leads → Pix → vendas (totals) + each upsell step. */
export function FlashFunnelPanel({ period, botId, flowId }: { period: MetricsPeriod; botId?: string; flowId?: string }) {
  const search = new URLSearchParams(periodParams(period));
  if (botId) search.set("bot_id", botId);
  if (flowId) search.set("flow_id", flowId);
  const funnel = useQuery({
    queryKey: ["analytics", "flash-funnel", search.toString()],
    queryFn: () => apiRequest<{ period_label: string; bots: FunnelBot[] }>(`/api/analytics/flash-funnel?${search}`),
    enabled: isPeriodReady(period),
    retry: false,
    placeholderData: (previous) => previous,
  });
  if (funnel.isLoading) return <LoadingState label="Carregando funil" />;
  if (funnel.error || !funnel.data) return <ErrorState message="Não foi possível carregar o funil." onRetry={() => void funnel.refetch()} />;
  if (funnel.data.bots.length === 0) return null;

  return (
    <section className="dashboard-card space-y-4 rounded-2xl p-4 sm:p-5">
      <div className="flex min-w-0 items-center gap-2.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand/12 text-accent"><Layers size={17} /></span>
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold text-fg">Funil por bot</h2>
          <p className="text-[11px] uppercase tracking-[0.12em] text-muted">Leads → Pix → vendas (com upsell) · {funnel.data.period_label}</p>
        </div>
      </div>
      <div className="grid gap-3 xl:grid-cols-2">
        {funnel.data.bots.map((bot) => {
          const top = Math.max(1, bot.leads, bot.pix, bot.sales);
          const soldInUpsell = bot.upsell_sales > 0;
          const maxTake = Math.max(1, ...bot.upsells.map((step) => step.offered));
          return (
            <article className="rounded-2xl border border-line-soft bg-surface p-3.5 sm:p-4" key={bot.bot_id}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="min-w-0 truncate text-sm font-semibold text-fg">{bot.bot_name}</h3>
                <span className="text-base font-bold text-success">{brl(bot.revenue)}</span>
              </div>
              <div className="mt-3 flex items-stretch gap-2">
                <Stage
                  fill="var(--grad-a)"
                  icon={<Users size={13} />}
                  label="Leads"
                  value={count(bot.leads)}
                  width={(bot.leads / top) * 100}
                />
                <Stage
                  fill="var(--grad-a)"
                  hint={`${rate(bot.lead_to_pix)} dos leads geraram Pix`}
                  icon={<Wallet size={13} />}
                  label="Pix gerados"
                  value={count(bot.pix)}
                  width={(bot.pix / top) * 100}
                />
                <Stage
                  fill="var(--color-success)"
                  hint={soldInUpsell ? `inclui ${count(bot.upsell_sales)} em upsell` : `${rate(bot.pix_to_sale)} dos Pix viraram venda`}
                  icon={<TrendingUp size={13} />}
                  label="Vendas"
                  value={count(bot.sales)}
                  width={(bot.sales / top) * 100}
                />
              </div>
              {bot.upsells.length > 0 && (
                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">Esteira de upsell</p>
                  <ul className="space-y-1.5">
                    {bot.upsells.map((step) => (
                      <li className="flex items-center gap-2.5" key={step.step}>
                        <span className="w-14 shrink-0 text-xs text-fg-2">Etapa {step.step}</span>
                        <div className="h-5 min-w-0 flex-1 overflow-hidden rounded-md bg-well">
                          <div
                            className="flex h-full items-center rounded-md bg-accent/70 px-2"
                            style={{ width: `${Math.max(step.offered ? 6 : 0, (step.offered / maxTake) * 100)}%` }}
                          >
                            <span className="truncate text-[10px] font-medium text-white">{count(step.paid)}/{count(step.offered)}</span>
                          </div>
                        </div>
                        <span className="w-12 shrink-0 text-right text-xs font-semibold text-accent tabular-nums">{rate(step.take_rate)}</span>
                        <span className="w-20 shrink-0 text-right text-xs font-medium text-success tabular-nums">{brl(step.revenue)}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
