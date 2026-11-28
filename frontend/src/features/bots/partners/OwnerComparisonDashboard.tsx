import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Scale } from "lucide-react";

import { PeriodFilter, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { brl, ownerDashboard, type DashboardRow } from "./api";

function Line({ label, value, strong, accent }: { label: string; value: string; strong?: boolean; accent?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 text-sm">
      <span className="text-muted">{label}</span>
      <span className={`${strong ? "font-semibold" : ""} ${accent ? "text-accent" : "text-fg"}`}>{value}</span>
    </div>
  );
}

function CompareCard({ row, ownerName }: { row: DashboardRow; ownerName: string }) {
  const t = row.totals;
  const partnerName = row.partner?.name || row.partner?.email || "Parceiro";
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-surface">
      <div className="flex items-center justify-between gap-2 border-b border-line px-4 py-2.5">
        <p className="truncate text-sm font-semibold text-fg">{partnerName} <span className="font-normal text-muted">· {row.partner_percent}%</span></p>
        <span className="text-xs text-muted">{t.sales} venda(s)</span>
      </div>
      <div className="grid gap-px bg-line sm:grid-cols-3">
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Venda</p>
          <Line label="Bruto" value={brl(t.gross)} />
          <Line label="Taxas (gateway + bot)" value={`− ${brl(t.fees)}`} />
          <Line label="Líquido" value={brl(t.net)} strong />
        </div>
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Dono ({ownerName})</p>
          <Line label="Parte do dono" value={brl(t.owner_amount)} strong />
        </div>
        <div className="bg-surface px-4 py-3">
          <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Parceiro</p>
          <Line label="Parte do parceiro" value={brl(t.partner_amount)} strong accent />
        </div>
      </div>
    </div>
  );
}

/** Owner comparison: side by side (gross, fees, net, owner vs partner share) per partner,
 * filterable by period and partner. No export (by request). */
export function OwnerComparisonDashboard({ botId, partners }: { botId: string; partners: { id: string; name: string }[] }) {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const [partnerId, setPartnerId] = useState<string>("");
  const data = useQuery({
    queryKey: ["bot-partners", "dashboard", botId, partnerId, period],
    queryFn: () => ownerDashboard(botId, period, partnerId || undefined),
    enabled: Boolean(botId),
  });

  const rows = data.data?.partners ?? [];
  const ownerName = data.data?.owner?.name || "você";

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-fg"><Scale size={16} /> Dono vs parceiro</span>
        <div className="flex flex-wrap items-center gap-2">
          <select className="field !min-h-9 !w-auto !text-sm" value={partnerId} onChange={(e) => setPartnerId(e.target.value)}>
            <option value="">Todos os parceiros</option>
            {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <PeriodFilter onChange={setPeriod} value={period} />
        </div>
      </div>
      <p className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-muted">
        <CalendarDays size={13} /> {data.data?.period_label ?? ""}
      </p>

      {data.isLoading && <p className="text-sm text-muted">Carregando…</p>}
      {!data.isLoading && rows.length === 0 && (
        <p className="rounded-xl border border-line bg-surface px-4 py-6 text-center text-sm text-muted">Nenhum parceiro com vendas no período.</p>
      )}
      <div className="space-y-3">
        {rows.map((row) => <CompareCard key={row.partnership_id} row={row} ownerName={ownerName} />)}
      </div>
    </div>
  );
}
