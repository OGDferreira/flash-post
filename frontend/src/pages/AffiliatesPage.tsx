import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Handshake, Info, Plus, RefreshCw, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { ProfileLink } from "@/components/ProfileLink";
import { CopyField } from "@/components/ui/CopyField";
import { Modal } from "@/components/ui/Modal";
import {
  PeriodFilter,
  formatNumber,
  isPeriodReady,
  moneyFormat,
  periodParams,
  todayInput,
  type MetricsPeriod,
} from "@/features/analytics/period";
import { ApiError, apiRequest } from "@/services/api";
import { brl, type Operations } from "@/features/partners/api";
import { NoticesCard, SalesTable, TotalsGrid } from "@/features/partners/PartnerPanel";
import { PartnerSharesCell } from "@/features/partners/PartnerShares";
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
  accepted_percent: string | null;
  pending_acceptance: boolean;
  bot_revenue: string;
  bot_sales: number;
  bot_leads?: number;
  bot_pix?: number;
  commission_received: string;
  total_revenue?: string;
  total_sales?: number;
  total_ticket?: string | null;
  today_revenue?: string;
  withdrawn?: string;
  balance?: string;
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

function InviteModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [percentText, setPercentText] = useState("30");
  const invite = useQuery({
    queryKey: ["affiliates", "invite"],
    queryFn: () => apiRequest<{ code: string; invite_url: string }>("/api/affiliates/invite"),
    enabled: open,
    staleTime: 5 * 60_000,
  });
  const rotate = useMutation({
    mutationFn: () => apiRequest<{ code: string; invite_url: string }>("/api/affiliates/invite/rotate", { method: "POST" }),
    onSuccess: (data) => {
      queryClient.setQueryData(["affiliates", "invite"], data);
      link.reset();
    },
  });
  const link = useMutation({
    mutationFn: (percent: string) =>
      apiRequest<{ invite_url: string; percent: string }>("/api/affiliates/invite/link", { method: "POST", body: { percent } }),
  });
  const value = Number(percentText.replace(",", "."));
  const validPercent = Number.isFinite(value) && value >= 0 && value <= 90;
  return (
    <Modal
      description="Quem se cadastrar por este link já entra como seu sócio, com a comissão que você definir aplicada automaticamente."
      onClose={onClose}
      open={open}
      title="Adicionar sócio"
    >
      <div className="space-y-4">
        <div className="rounded-xl border border-line-soft bg-surface-inset p-3">
          <label className="block text-[11px] font-semibold uppercase tracking-[0.12em] text-muted" htmlFor="invite-percent">
            Comissão do novo sócio
          </label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1 rounded-xl border border-line bg-surface px-3">
              <input
                className="min-h-11 w-20 bg-transparent text-xl font-semibold text-fg outline-none"
                id="invite-percent"
                inputMode="decimal"
                onChange={(event) => {
                  setPercentText(event.target.value);
                  link.reset();
                }}
                value={percentText}
              />
              <span className="text-muted">%</span>
            </span>
            <button
              className="btn-primary"
              disabled={!validPercent || link.isPending}
              onClick={() => link.mutate(value.toFixed(2))}
              type="button"
            >
              {link.isPending ? "Gerando…" : "Gerar link"}
            </button>
          </div>
          {!validPercent && <p className="mt-1 text-xs text-danger">Use um valor de 0 a 90%.</p>}
          {link.data && (
            <div className="mt-3">
              <CopyField label={`Link de cadastro com ${Number(link.data.percent).toLocaleString("pt-BR")}% (vale 30 dias)`} value={link.data.invite_url} />
              <p className="mt-1.5 text-[11px] text-muted">
                A comissão vale automaticamente para as próximas vendas. Você pode alterá-la a qualquer momento; a mudança não exige aceite do sócio.
              </p>
            </div>
          )}
          {link.error && <p className="mt-2 text-xs text-danger">{errorText(link.error)}</p>}
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-medium text-fg">Código simples (sem comissão definida)</h4>
            <button
              className="btn-secondary !min-h-8 text-xs"
              disabled={rotate.isPending}
              onClick={async () => {
                if (await confirmAction("Gerar um novo código? O código antigo e os links já enviados deixam de funcionar para novos cadastros. Seus sócios atuais continuam vinculados.")) rotate.mutate();
              }}
              type="button"
            >
              <RefreshCw size={13} /> Novo código
            </button>
          </div>
          {invite.isLoading && <div aria-busy="true" className="skeleton h-12" />}
          {invite.error && <ErrorState message={errorText(invite.error)} onRetry={() => void invite.refetch()} />}
          {invite.data && (
            <div className="grid gap-3 md:grid-cols-2">
              <CopyField label="Código" value={invite.data.code} />
              <CopyField label="Link de cadastro" value={invite.data.invite_url} />
            </div>
          )}
          <p className="text-[11px] text-muted">Com o código simples, a comissão começa em 0% e você pode defini-la depois. Nenhum aceite do sócio é necessário.</p>
        </div>
      </div>
    </Modal>
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
  const valid = value.trim() !== "" && Number.isFinite(numeric) && numeric >= 0 && numeric <= 99;
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

type AccountFilter = "all" | "connected" | "disconnected";
const accountStatus: Record<string, string> = {
  connected: "conectada",
  error: "desconectada (erro de autorização)",
  expired: "desconectada (token expirado)",
  disconnected: "desconectada",
  manual: "desconectada manualmente",
};

function DetailModal({ id, period, onClose, initialAccounts = "all" }: {
  id: string | null;
  period: MetricsPeriod;
  onClose: () => void;
  initialAccounts?: AccountFilter;
}) {
  const [accountFilter, setAccountFilter] = useState<AccountFilter>(initialAccounts);
  // The popup has its own period, starting from the page's and changeable here.
  const [localPeriod, setLocalPeriod] = useState<MetricsPeriod>(period);
  useEffect(() => {
    if (id) setLocalPeriod(period);
    // Reset to the page period each time a different partner opens.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  const detail = useQuery({
    queryKey: ["affiliates", "detail", id, periodParams(localPeriod)],
    queryFn: () => apiRequest<Detail>(`/api/affiliates/${id}?${new URLSearchParams(periodParams(localPeriod))}`),
    enabled: Boolean(id),
  });
  const data = detail.data;
  const allLeads = data ? data.leads + (data.bot_leads ?? 0) : 0;
  const sales = data ? (data.total_sales ?? data.purchases) : 0;
  return (
    <Modal
      description="Métricas agregadas da operação do filiado no período selecionado."
      onClose={onClose}
      open={Boolean(id)}
      title={data ? data.full_name : "Filiado"}
      wide
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line-soft bg-surface-inset px-3 py-2">
        <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted">Período</span>
        <PeriodFilter onChange={setLocalPeriod} value={localPeriod} />
      </div>
      {detail.isLoading && <LoadingState label="Carregando filiado" />}
      {detail.error && <ErrorState message={errorText(detail.error)} onRetry={() => void detail.refetch()} />}
      {data && (
        <div className="space-y-4">
          {(
            [
              ["Faturamento", [
                ["Total (Shark + Flash)", money(data.total_revenue ?? data.revenue), "text-success"],
                ["Hoje", money(data.today_revenue ?? "0")],
                ["Ticket médio", data.total_ticket ? money(data.total_ticket) : "—"],
                ["Vendas pagas", formatNumber(sales)],
              ]],
              ["Funil", [
                ["Leads", formatNumber(allLeads)],
                ["Shark · Flash", `${formatNumber(data.leads)} · ${formatNumber(data.bot_leads ?? 0)}`],
                ["PIX gerados", formatNumber(data.pix_generated + (data.bot_pix ?? 0))],
                ["Lead → venda", allLeads ? `${((100 * sales) / allLeads).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%` : "—"],
              ]],
              ["Dinheiro", [
                ["Saldo na conta", money(data.balance ?? "0"), "text-success"],
                ["Sacado", money(data.withdrawn ?? "0")],
                ["Comissão recebida", money(data.commission_received)],
                [`Participação Shark (${percent(data.participation_percent)}%)`, money(data.participation_amount)],
              ]],
            ] as [string, [string, string, string?][]][]
          ).map(([group, items]) => (
            <section key={group}>
              <h4 className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{group}</h4>
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {items.map(([title, value, tone]) => (
                  <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-2.5" key={title}>
                    <dt className="text-[11px] leading-tight text-muted">{title}</dt>
                    <dd className={`mt-1 truncate text-base font-semibold sm:text-lg ${tone ?? "text-fg"}`} title={value}>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
          {data.purchases_without_amount > 0 && (
            <p className="text-xs text-warning">{data.purchases_without_amount} compra(s) paga(s) chegaram sem valor e não entram na receita.</p>
          )}
          <AccountsList accounts={data.accounts} filter={accountFilter} onFilter={setAccountFilter} />
          {id && <PartnerOperations id={id} period={localPeriod} />}
          <p className="rounded-xl border border-line-soft bg-surface-inset p-3 text-[11px] leading-5 text-muted">{data.criteria.participation}</p>
        </div>
      )}
    </Modal>
  );
}

function AccountsList({ accounts, filter, onFilter }: {
  accounts: Detail["accounts"];
  filter: AccountFilter;
  onFilter: (filter: AccountFilter) => void;
}) {
  const connected = accounts.filter((account) => account.status === "connected");
  const disconnected = accounts.filter((account) => account.status !== "connected");
  const shown = filter === "connected" ? connected : filter === "disconnected" ? disconnected : accounts;
  const chips: [AccountFilter, string, number][] = [
    ["all", "Todas", accounts.length],
    ["connected", "Conectadas", connected.length],
    ["disconnected", "Desconectadas", disconnected.length],
  ];
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-medium text-fg">Contas do Instagram</h4>
        <div className="flex gap-1 rounded-full bg-well p-1" role="tablist">
          {chips.map(([key, label, count]) => (
            <button
              aria-selected={filter === key}
              className={`rounded-full px-3 py-1 text-[11px] font-medium ${filter === key ? (key === "disconnected" ? "bg-danger text-white" : "bg-brand text-white") : "text-muted"}`}
              key={key}
              onClick={() => onFilter(key)}
              role="tab"
              type="button"
            >
              {label} ({count})
            </button>
          ))}
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="mt-2 text-xs text-muted">
          {filter === "disconnected" ? "Nenhuma conta desconectada." : filter === "connected" ? "Nenhuma conta conectada." : "Nenhuma conta."}
        </p>
      ) : (
        <ul className="mt-2 max-h-72 divide-y divide-[color:var(--color-line-soft)] overflow-y-auto rounded-xl border border-line-soft">
          {shown.map((account) => (
            <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs" key={account.account_id}>
              <span className="flex items-center gap-2 text-fg">
                <span className={`size-2 rounded-full ${account.status === "connected" ? "bg-success" : "bg-danger"}`} />
                @{account.username}
                <ProfileLink username={account.username} />
              </span>
              <span className="text-muted">
                {accountStatus[account.status] ?? account.status} · {formatNumber(account.published_posts)} publicações ·{" "}
                {account.video_views_lifetime === null ? "views indisponíveis" : `${formatNumber(account.video_views_lifetime)} views`}
                {account.follower_count !== null && ` · ${formatNumber(account.follower_count)} seguidores`}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PartnerOperations({ id, period }: { id: string; period: MetricsPeriod }) {
  const ops = useQuery({
    queryKey: ["partners", "operations", id, periodParams(period)],
    queryFn: () => apiRequest<Operations>(`/api/partners/${id}/operations?${new URLSearchParams(periodParams(period))}`),
  });
  if (ops.isLoading) return <div aria-busy="true" className="skeleton h-24" />;
  if (!ops.data) return null;
  const data = ops.data;
  const list = (title: string, rows: { key: string; left: string; right: string }[]) => (
    <div>
      <h4 className="text-sm font-medium text-fg">{title} ({rows.length})</h4>
      {rows.length === 0 ? (
        <p className="mt-1 text-xs text-muted">Nenhum.</p>
      ) : (
        <ul className="mt-2 divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft">
          {rows.map((row) => (
            <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-xs" key={row.key}>
              <span className="text-fg">{row.left}</span>
              <span className="text-muted">{row.right}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
  return (
    <div className="space-y-4">
      <h4 className="text-sm font-semibold text-fg">Operação do sócio (Flash)</h4>
      {data.totals && <TotalsGrid commissionLabel="Sua comissão" netLabel="Líquido do sócio" totals={data.totals} />}
      {list("Bots", data.bots.map((b) => ({
        key: b.id, left: `${b.name} · @${b.username}`,
        right: `${b.is_active ? b.status : "pausado"} · ${b.flow_name ?? "sem funil"} · ${b.leads} leads · ${b.sales} vendas · ${brl(b.revenue)}`,
      })))}
      {list("Funis", data.flows.map((f) => ({
        key: f.id, left: f.name,
        right: f.from_template ? (f.customized_at ? `cópia do seu modelo, alterada em ${new Date(f.customized_at).toLocaleDateString("pt-BR")}` : "cópia do seu modelo") : "próprio",
      })))}
      {list("Loops", data.loops.map((l) => ({
        key: l.id, left: l.name,
        right: `${l.status === "active" ? "ativo" : "pausado"} · ${l.accounts} conta(s) · ${l.posts} posts${l.from_template ? " · do seu modelo" : ""}`,
      })))}
      <div>
        <h4 className="mb-2 text-sm font-medium text-fg">Últimas vendas</h4>
        <SalesTable sales={data.sales} />
      </div>
    </div>
  );
}

export function AffiliatesPage() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const [open, setOpen] = useState<{ id: string; accounts: AccountFilter } | null>(null);
  const [only, setOnly] = useState<string>("");
  const [inviting, setInviting] = useState(false);
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
  const rows = data ? (only ? data.rows.filter((row) => row.id === only) : data.rows) : [];

  return (
    <div className="w-full space-y-4">
      <header className="space-y-3">
        <div>
          <h2 className="mt-2 flex items-center gap-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            <Handshake className="text-accent" size={26} /> Sócios
          </h2>
        </div>
        <PeriodFilter onChange={setPeriod} value={period} />
      </header>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="min-w-0 space-y-4">
      {list.isLoading && <LoadingState label="Carregando filiados" />}
      {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
      {data && (
        <>
          <section className="glass-panel p-4 sm:p-4">
            <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">
              {[
                ["Sócios", formatNumber(data.rows.length)],
                ["Vendas Flash dos sócios", money(data.rows.reduce((sum, row) => sum + Number(row.bot_revenue), 0).toFixed(2))],
                ["Comissão recebida", money(data.rows.reduce((sum, row) => sum + Number(row.commission_received), 0).toFixed(2))],
                ["Faturamento total (Shark + Flash)", money(data.totals_revenue)],
                ["Participação SharkBot (referência)", money(data.totals_participation)],
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
          {(
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="mr-auto flex items-center gap-2 text-base font-semibold text-fg">
                Seus sócios <span className="text-sm font-normal text-muted">({data.rows.length})</span>
              </h3>
              <button className="btn-primary !min-h-10" onClick={() => setInviting(true)} type="button">
                <Plus size={16} /> Adicionar sócio
              </button>
              {data.rows.length > 0 && <select
                aria-label="Filtrar sócio"
                className="field !w-auto min-w-[220px]"
                onChange={(event) => setOnly(event.target.value)}
                value={only}
              >
                <option value="">Todos os sócios ({data.rows.length})</option>
                {data.rows.map((row) => (
                  <option key={row.id} value={row.id}>{row.full_name}</option>
                ))}
              </select>}
              {only && (
                <button className="btn-primary !min-h-10" onClick={() => setOpen({ id: only, accounts: "all" })} type="button">
                  <BarChart3 size={15} /> Abrir painel do sócio
                </button>
              )}
            </div>
          )}
          {data.rows.length === 0 ? (
            <EmptyState message="Você ainda não tem sócios. Clique em “Adicionar sócio” para gerar o link de convite." />
          ) : (
            <div className="glass-panel overflow-x-auto">
              <table className="w-full min-w-[1420px] text-left text-xs">
                <thead className="text-muted">
                  <tr className="text-[10px] uppercase tracking-wider">
                    <th colSpan={3} />
                    <th className="border-b border-line-soft px-2 pt-3 text-center font-semibold text-accent" colSpan={3}>SharkBot</th>
                    <th className="border-b border-line-soft px-2 pt-3 text-center font-semibold text-accent" colSpan={2}>Flash</th>
                    <th className="border-b border-line-soft px-2 pt-3 text-center font-semibold text-accent" colSpan={5}>Faturamento e carteira</th>
                    <th colSpan={4} />
                  </tr>
                  <tr className="border-b border-line-soft">
                    <th className="px-4 py-3 font-medium">Sócio</th>
                    <th className="px-2 py-3 text-right font-medium">Contas</th>
                    <th className="px-2 py-3 text-right font-medium">Publicações</th>
                    <th className="px-2 py-3 text-right font-medium">Leads</th>
                    <th className="px-2 py-3 text-right font-medium">Compras</th>
                    <th className="px-2 py-3 text-right font-medium">Receita</th>
                    <th className="px-2 py-3 text-right font-medium">Leads</th>
                    <th className="px-2 py-3 text-right font-medium">Vendas</th>
                    <th className="px-2 py-3 text-right font-medium">Total</th>
                    <th className="px-2 py-3 text-right font-medium">Hoje</th>
                    <th className="px-2 py-3 text-right font-medium">Ticket médio</th>
                    <th className="px-2 py-3 text-right font-medium">Sacado</th>
                    <th className="px-2 py-3 text-right font-medium">Saldo na conta</th>
                    <th className="px-2 py-3 text-right font-medium">Comissão recebida</th>
                    <th className="px-2 py-3 font-medium">Compartilhados</th>
                    <th className="px-2 py-3 text-right font-medium">Comissão (%)</th>
                    <th className="px-4 py-3" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr className="border-b border-line-soft last:border-0" key={row.id}>
                      <td className="px-4 py-3">
                        <button className="text-left text-fg hover:text-white" onClick={() => setOpen({ id: row.id, accounts: "all" })} type="button">
                          <span className="block font-medium">{row.full_name}</span>
                          <span className="text-[10px] text-muted">{row.nickname}</span>
                        </button>
                        <button
                          className="mt-1 flex items-center gap-1 text-[10px] font-semibold text-accent"
                          onClick={() => setOpen({ id: row.id, accounts: "all" })}
                          type="button"
                        >
                          <BarChart3 size={11} /> Abrir painel
                        </button>
                      </td>
                      <td className="px-2 py-3 text-right">
                        <button
                          className="text-right"
                          onClick={() => setOpen({ id: row.id, accounts: "connected" })}
                          title="Ver as contas do sócio"
                          type="button"
                        >
                          <span className="block font-semibold text-success hover:underline">{row.accounts_connected} conectadas</span>
                        </button>
                        {row.accounts_total - row.accounts_connected > 0 && (
                          <button className="block w-full text-right" onClick={() => setOpen({ id: row.id, accounts: "disconnected" })} type="button">
                            <span className="text-[10px] text-danger hover:underline">{row.accounts_total - row.accounts_connected} desconectadas</span>
                          </button>
                        )}
                      </td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.published_posts)}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.leads)}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.purchases)}</td>
                      <td className="px-2 py-3 text-right font-semibold text-success">{money(row.revenue)}</td>
                      <td className="px-2 py-3 text-right text-fg">{formatNumber(row.bot_leads ?? 0)}</td>
                      <td className="px-2 py-3 text-right text-fg">{money(row.bot_revenue)}<span className="block text-[10px] text-muted">{row.bot_sales} {row.bot_sales === 1 ? "venda" : "vendas"}</span></td>
                      <td className="px-2 py-3 text-right font-semibold text-success">{money(row.total_revenue ?? "0")}<span className="block text-[10px] font-normal text-muted">{row.total_sales ?? 0} {row.total_sales === 1 ? "venda" : "vendas"}</span></td>
                      <td className="px-2 py-3 text-right text-fg">{money(row.today_revenue ?? "0")}</td>
                      <td className="px-2 py-3 text-right text-fg">{row.total_ticket ? money(row.total_ticket) : "—"}</td>
                      <td className="px-2 py-3 text-right text-fg">{money(row.withdrawn ?? "0")}</td>
                      <td className="px-2 py-3 text-right font-semibold text-fg">{money(row.balance ?? "0")}</td>
                      <td className="px-2 py-3 text-right font-semibold text-fg">{money(row.commission_received)}</td>
                      <td className="px-2 py-3">
                        <PartnerSharesCell affiliationId={row.id} name={row.full_name} userId={row.user_id} />
                      </td>
                      <td className="px-2 py-3">
                        <PercentEditor key={`${row.id}-${row.participation_percent}`} period={period} row={row} />
                        <p className="mt-1 text-right text-[10px] text-muted">
                          Vale automaticamente nas próximas vendas
                        </p>
                      </td>
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
      </div>
      <aside className="space-y-4 xl:sticky xl:top-[calc(72px+env(safe-area-inset-top)+16px)]">
        <NoticesCard side />
      </aside>
      </div>
      <InviteModal onClose={() => setInviting(false)} open={inviting} />
      <DetailModal
        id={open?.id ?? null}
        initialAccounts={open?.accounts ?? "all"}
        key={open ? `${open.id}-${open.accounts}` : "closed"}
        onClose={() => setOpen(null)}
        period={period}
      />
    </div>
  );
}
