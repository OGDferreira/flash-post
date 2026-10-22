import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, FolderTree, Percent, Trophy, type LucideIcon } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { PeriodFilter, isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { ApiError, apiRequest } from "@/services/api";

type Row = {
  starts: number;
  pix: number;
  sales: number;
  conversion: number | null;
  pix_conversion: number | null;
  gross: number;
  net: number;
  ticket: number | null;
};
type FlowRow = Row & { id: string; name: string; shared: boolean; plans: { id: string; name: string | null; sales: number; gross: number }[] };
type FolderRow = Row & {
  id: string;
  name: string;
  bots: string[];
  leader: string | null;
  flows: { id: string; name: string; sales: number; conversion: number | null; net: number }[];
};
type Leader = { id: string; name: string; value: number } | null;
type Strategy = {
  period_label: string;
  criteria: Record<string, string>;
  leaders: { sales: Leader; conversion: Leader; net: Leader };
  flows: FlowRow[];
  folders: FolderRow[];
};

const brl = (value: number | null | undefined) => (value ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const pct = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`);
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível carregar a estratégia.");

/** Falcon Bot > Estratégia: each funnel and each folder side by side, from this operation's real sales. */
export function StrategyPanel() {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: "", end: "" });
  const params = periodParams(period);
  const data = useQuery({
    queryKey: ["bots", "strategy", params],
    queryFn: () => apiRequest<Strategy>(`/api/bots/strategy?${new URLSearchParams(params)}`),
    enabled: isPeriodReady(period),
  });

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
        <span className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted">{data.data?.period_label ?? "Período"}</span>
        <PeriodFilter onChange={setPeriod} value={period} />
      </div>
      {data.isLoading ? (
        <LoadingState label="Calculando a estratégia" />
      ) : data.error || !data.data ? (
        <ErrorState message={errorText(data.error)} onRetry={() => void data.refetch()} />
      ) : (
        <Content data={data.data} />
      )}
    </div>
  );
}

function Leader({ icon: Icon, label, leader, format }: { icon: LucideIcon; label: string; leader: Leader; format: (v: number) => string }) {
  return (
    <div className="dashboard-card p-4">
      <p className="flex items-center gap-2 text-xs text-muted">
        <Icon className="text-accent" size={15} /> {label}
      </p>
      <p className="mt-2 truncate text-lg font-semibold text-fg">{leader?.name ?? "—"}</p>
      <p className="text-sm font-medium text-accent">{leader ? format(leader.value) : "Sem vendas no período"}</p>
    </div>
  );
}

function Content({ data }: { data: Strategy }) {
  const [open, setOpen] = useState<string | null>(null);
  if (data.flows.length === 0) return <EmptyState message="Crie um funil e conecte um robô para ver a estratégia." />;
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-3">
        <Leader format={(v) => `${v} venda(s)`} icon={Trophy} label="Vendeu mais" leader={data.leaders.sales} />
        <Leader format={pct} icon={Percent} label="Converteu mais" leader={data.leaders.conversion} />
        <Leader format={brl} icon={CircleDollarSign} label="Lucrou mais" leader={data.leaders.net} />
      </div>

      {data.folders.length > 0 && (
        <section className="space-y-2">
          <h2 className="flex items-center gap-2 px-1 text-base font-semibold text-fg">
            <FolderTree className="text-accent" size={17} /> Pastas
          </h2>
          <div className="grid gap-3 lg:grid-cols-2">
            {data.folders.map((folder) => (
              <article className="dashboard-card space-y-3 p-4" key={folder.id}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-fg">{folder.name}</p>
                    <p className="text-[11px] text-muted">{folder.bots.length ? folder.bots.map((b) => `@${b}`).join(", ") : "Nenhum robô conectado"}</p>
                  </div>
                  {folder.leader && <span className="rounded-full bg-success/15 px-2.5 py-1 text-[11px] font-semibold text-success">Na frente: {folder.leader}</span>}
                </div>
                <Totals row={folder} />
                <table className="w-full text-left text-xs">
                  <thead className="text-[10px] uppercase tracking-wide text-muted">
                    <tr><th className="py-1 font-medium">Funil</th><th className="py-1 text-right font-medium">Vendas</th><th className="py-1 text-right font-medium">Conversão</th><th className="py-1 text-right font-medium">Líquido</th></tr>
                  </thead>
                  <tbody className="divide-y divide-[color:var(--color-line-soft)]">
                    {folder.flows.map((flow) => (
                      <tr key={flow.id}>
                        <td className="max-w-[10rem] truncate py-1.5 text-fg">{flow.name}</td>
                        <td className="py-1.5 text-right text-fg">{flow.sales}</td>
                        <td className="py-1.5 text-right text-fg">{pct(flow.conversion)}</td>
                        <td className="py-1.5 text-right text-fg">{brl(flow.net)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </article>
            ))}
          </div>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="px-1 text-base font-semibold text-fg">Funis</h2>
        <div className="grid gap-3 lg:grid-cols-2 2xl:grid-cols-3">
          {[...data.flows].sort((a, b) => b.net - a.net || b.sales - a.sales).map((flow) => (
            <article className="dashboard-card space-y-3 p-4" key={flow.id}>
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate font-semibold text-fg">{flow.name}</p>
                {flow.shared && <span className="shrink-0 text-[10px] text-muted">compartilhado</span>}
              </div>
              <Totals row={flow} />
              {flow.plans.length > 0 && (
                <div>
                  <button className="text-xs font-medium text-accent hover:underline" onClick={() => setOpen(open === flow.id ? null : flow.id)} type="button">
                    {open === flow.id ? "Esconder planos" : `Vendas por plano (${flow.plans.length})`}
                  </button>
                  {open === flow.id && (
                    <ul className="mt-2 space-y-1">
                      {flow.plans.map((plan) => (
                        <li className="flex items-center justify-between gap-2 rounded-lg bg-surface-inset px-2.5 py-1.5 text-xs" key={plan.id}>
                          <span className="truncate text-fg">{plan.name ?? plan.id}</span>
                          <span className="shrink-0 text-fg-2">{plan.sales} · {brl(plan.gross)}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      </section>
      <ul className="space-y-0.5 px-1 text-[11px] text-muted">
        {Object.values(data.criteria).map((text) => <li key={text}>{text}</li>)}
      </ul>
    </>
  );
}

function Totals({ row }: { row: Row }) {
  return (
    <dl className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
      {[
        ["Starts", String(row.starts)],
        ["Pix", String(row.pix)],
        ["Vendas", String(row.sales)],
        ["Conversão", pct(row.conversion)],
        ["Bruto", brl(row.gross)],
        ["Líquido", brl(row.net)],
      ].map(([label, value]) => (
        <div className="min-w-0 rounded-lg bg-surface-inset px-1.5 py-2" key={label}>
          <dt className="text-[10px] uppercase tracking-wide text-muted">{label}</dt>
          <dd className="mt-0.5 truncate font-mono text-sm font-semibold tabular-nums text-fg" title={value}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
