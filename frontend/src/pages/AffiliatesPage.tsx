import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Handshake, Info, RefreshCw, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { CopyField } from "@/components/ui/CopyField";
import { Modal } from "@/components/ui/Modal";
import {
  PeriodFilter,
  formatNumber,
  formatPercent,
  isPeriodReady,
  moneyFormat,
  periodParams,
  todayInput,
  type MetricsPeriod,
} from "@/features/analytics/period";
import { ApiError, apiRequest } from "@/services/api";
import { confirmAction } from "@/lib/confirm";

type Row = {
  id: string;
  user_id: string;
  full_name: string;
  nickname: string;
  participation_percent: string;
  since: string;
  accounts_total: number;
  accounts_connected: number;
  published_posts: number;
  leads: number;
  pix_generated: number;
  purchases: number;
  revenue: string;
  pix_to_paid_rate: number | null;
  lead_to_purchase_rate: number | null;
  average_ticket: string | null;
  participation_amount: string;
};

type Listing = {
  period_label: string;
  time_zone: string;
  basis: string;
  totals_revenue: string;
  totals_participation: string;
  rows: Row[];
};

type Detail = Row & {
  accounts: {
    account_id: string;
    username: string;
    status: string;
    follower_count: number | null;
    published_posts: number;
    video_views_lifetime: number | null;
    videos_with_views: number;
  }[];
  purchases_without_amount: number;
  leads_per_purchase: number | null;
  criteria: Record<string, string>;
};

const money = (value: string | null) => (value === null ? "—" : moneyFormat.format(Number(value)));
const percent = (value: string) => Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir a ação.");

function InviteCard() {
  const queryClient = useQueryClient();
  const invite = useQuery({
    queryKey: ["affiliates", "invite"],
    queryFn: () => apiRequest<{ code: string; invite_url: string }>("/api/affiliates/invite"),
    staleTime: 5 * 60_000,
  });
  const rotate = useMutation({
    mutationFn: () => apiRequest<{ code: string; invite_url: string }>("/api/affiliates/invite/rotate", { method: "POST" }),
    onSuccess: (data) => queryClient.setQueryData(["affiliates", "invite"], data),
  });
  return (
    <section className="glass-panel space-y-3 p-4 sm:p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-fg">Seu código de convite</h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-muted">
            Quem se cadastrar (ou informar o código no perfil) com este código vira seu filiado. Você define a porcentagem
            de participação de cada um e acompanha as métricas deles aqui. Filiados não veem seus dados.
          </p>
        </div>
        <button
          className="btn-secondary !min-h-9 text-xs"
          disabled={rotate.isPending}
          onClick={async () => {
            if (await confirmAction("Gerar um novo código? O código antigo deixa de funcionar para novos cadastros. Seus filiados atuais continuam vinculados.")) rotate.mutate();
          }}
          type="button"
        >
          <RefreshCw size={14} />
          Novo código
        </button>
      </div>
      {invite.isLoading && <div aria-busy="true" className="skeleton h-12" />}
      {invite.error && <ErrorState message="Não foi possível carregar o código." onRetry={() => void invite.refetch()} />}
      {invite.data && (
        <div className="grid gap-3 md:grid-cols-2">
          <CopyField label="Código" value={invite.data.code} />
          <CopyField label="Link de cadastro" value={invite.data.invite_url} />
        </div>
      )}
    </section>
  );
}

function PercentEditor({ row, period }: { row: Row; period: MetricsPeriod }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(percent(row.participation_percent).replace(/\./g, ""));
  const save = useMutation({
    mutationFn: () =>
      apiRequest<Row>(`/api/affiliates/${row.id}?${new URLSearchParams(periodParams(period))}`, {
        method: "PATCH",
        body: { participation_percent: value.replace(",", ".") },
      }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["affiliates"] }),
  });
  const numeric = Number(value.replace(",", "."));
  const valid = value.trim() !== "" && Number.isFinite(numeric) && numeric >= 0 && numeric <= 100;
  const dirty = valid && numeric !== Number(row.participation_percent);
  return (
    <div className="flex items-center justify-end gap-1.5">
      <input
        aria-label={`Porcentagem de ${row.full_name}`}
        className="field !min-h-8 !w-20 !px-2 text-right !text-xs"
        inputMode="decimal"
        onChange={(event) => setValue(event.target.value)}
        value={value}
      />
      <span className="text-xs text-muted">%</span>
      <button className="btn-primary !min-h-8 !px-3 text-xs" disabled={!dirty || save.isPending} onClick={() => save.mutate()} type="button">
        {save.isPending ? "…" : "Salvar"}
      </button>
      {save.error && <span className="sr-only" role="alert">{errorText(save.error)}</span>}
    </div>
  );
}

function DetailModal({ id, period, onClose }: { id: string | null; period: MetricsPeriod; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["affiliates", "detail", id, periodParams(period)],
    queryFn: () => apiRequest<Detail>(`/api/affiliates/${id}?${new URLSearchParams(periodParams(period))}`),
    enabled: Boolean(id),
  });
  const data = detail.data;
  return (
    <Modal
      description="Métricas agregadas da operação do filiado no período selecionado."
      onClose={onClose}
      open={Boolean(id)}
      title={data ? data.full_name : "Filiado"}
    >
      {detail.isLoading && <LoadingState label="Carregando filiado" />}
      {detail.error && <ErrorState message={errorText(detail.error)} onRetry={() => void detail.refetch()} />}
      {data && (
        <div className="space-y-4">
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {[
              ["Receita aprovada", money(data.revenue)],
              [`Participação (${percent(data.participation_percent)}%)`, money(data.participation_amount)],
              ["Ticket médio", money(data.average_ticket)],
              ["Leads", formatNumber(data.leads)],
              ["PIX gerados", formatNumber(data.pix_generated)],
              ["Compras pagas", formatNumber(data.purchases)],
              ["PIX pago ÷ gerado", formatPercent(data.pix_to_paid_rate)],
              ["Lead → compra", formatPercent(data.lead_to_purchase_rate)],
              ["Leads por compra", data.leads_per_purchase === null ? "—" : data.leads_per_purchase.toLocaleString("pt-BR")],
            ].map(([title, value]) => (
              <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={title}>
                <dt className="text-[11px] text-muted">{title}</dt>
                <dd className="mt-1 text-base font-semibold text-fg">{value}</dd>
              </div>
            ))}
          </dl>
          {data.purchases_without_amount > 0 && (
            <p className="text-xs text-warning">{data.purchases_without_amount} compra(s) paga(s) chegaram sem valor e não entram na receita.</p>
          )}
          <div>
            <h4 className="text-sm font-medium text-fg">Contas do Instagram ({data.accounts.length})</h4>
            {data.accounts.length === 0 ? (
              <p className="mt-2 text-xs text-muted">Nenhuma conta conectada.</p>
            ) : (
              <ul className="mt-2 divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft">
                {data.accounts.map((account) => (
                  <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs" key={account.account_id}>
                    <span className="text-fg">@{account.username}</span>
                    <span className="text-muted">
                      {account.status === "connected" ? "conectada" : account.status} · {formatNumber(account.published_posts)} publicações ·{" "}
                      {account.video_views_lifetime === null ? "views indisponíveis" : `${formatNumber(account.video_views_lifetime)} views acumuladas`}
                      {account.follower_count !== null && ` · ${formatNumber(account.follower_count)} seguidores`}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="rounded-xl border border-line-soft bg-surface-inset p-3 text-[11px] leading-5 text-muted">{data.criteria.participation}</p>
        </div>
      )}
    </Modal>
  );
}

export function AffiliatesPage() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["affiliates", "list", periodParams(period)],
    queryFn: () => apiRequest<Listing>(`/api/affiliates?${new URLSearchParams(periodParams(period))}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/affiliates/${id}`, { method: "DELETE" }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["affiliates"] }),
  });
  const data = list.data;

  return (
    <div className="mx-auto max-w-[1200px] space-y-4">
      <header className="space-y-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Rede</p>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            <Handshake className="text-accent" size={26} /> Filiados
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted">
            Acompanhe as contas e as vendas do SharkBot de quem entrou pelo seu convite e veja sua participação.
          </p>
        </div>
        <PeriodFilter onChange={setPeriod} value={period} />
      </header>

      <InviteCard />

      {list.isLoading && <LoadingState label="Carregando filiados" />}
      {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
      {data && (
        <>
          <section className="glass-panel p-4 sm:p-4">
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {[
                ["Filiados", formatNumber(data.rows.length)],
                ["Receita dos filiados", money(data.totals_revenue)],
                ["Sua participação (referência)", money(data.totals_participation)],
              ].map(([title, value]) => (
                <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={title}>
                  <dt className="text-[11px] text-muted">{title}</dt>
                  <dd className="mt-1 text-lg font-semibold text-fg">{value}</dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 flex gap-2 text-[11px] leading-5 text-muted">
              <Info className="mt-0.5 shrink-0" size={13} />
              {data.basis} Período: {data.period_label} (fuso {data.time_zone}).
            </p>
          </section>
          {data.rows.length === 0 ? (
            <EmptyState message="Você ainda não tem filiados. Compartilhe seu código ou link de cadastro." />
          ) : (
            <div className="glass-panel overflow-x-auto">
              <table className="w-full min-w-[900px] text-left text-xs">
                <thead className="text-muted">
                  <tr className="border-b border-line-soft">
                    <th className="px-4 py-3 font-medium">Filiado</th>
                    <th className="px-2 py-3 text-right font-medium">Contas</th>
                    <th className="px-2 py-3 text-right font-medium">Publicações</th>
                    <th className="px-2 py-3 text-right font-medium">Leads</th>
                    <th className="px-2 py-3 text-right font-medium">Compras</th>
                    <th className="px-2 py-3 text-right font-medium">Receita</th>
                    <th className="px-2 py-3 text-right font-medium">Participação</th>
                    <th className="px-2 py-3 text-right font-medium">% definida</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr className="border-b border-line-soft last:border-0" key={row.id}>
                      <td className="px-4 py-3">
                        <button className="text-left text-fg hover:text-white" onClick={() => setOpenId(row.id)} type="button">
                          <span className="block font-medium">{row.full_name}</span>
                          <span className="text-[10px] text-muted">{row.nickname}</span>
                        </button>
                      </td>
                      <td className="px-2 py-3 text-right text-fg">{row.accounts_connected}/{row.accounts_total}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.published_posts)}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.leads)}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.purchases)}</td>
                      <td className="px-2 py-3 text-right font-semibold text-success">{money(row.revenue)}</td>
                      <td className="px-2 py-3 text-right font-semibold text-fg">{money(row.participation_amount)}</td>
                      <td className="px-2 py-3"><PercentEditor key={`${row.id}-${row.participation_percent}`} period={period} row={row} /></td>
                      <td className="px-4 py-3 text-right">
                        <button
                          aria-label={`Remover ${row.full_name}`}
                          className="btn-ghost !min-h-8 !px-2 text-danger"
                          disabled={remove.isPending}
                          onClick={async () => {
                            if (await confirmAction(`Remover ${row.full_name} dos seus filiados? Ele continua com a própria conta, só deixa de ser filiado.`)) remove.mutate(row.id);
                          }}
                          type="button"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      <DetailModal id={openId} onClose={() => setOpenId(null)} period={period} />
    </div>
  );
}
