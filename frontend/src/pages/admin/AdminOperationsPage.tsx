import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/PageState";
import { PeriodFilter, isPeriodReady, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { brl } from "@/features/partners/api";
import { apiRequest } from "@/services/api";

type Data = {
  period_label: string;
  users: {
    user_id: string; name: string; email: string; hierarchy: string; chief: string | null; commission_percent: number | null;
    revenue: number; fees: number; commission_paid: number; commission_received: number;
  }[];
  bots: {
    id: string; name: string; username: string; status: string; owner: string; flow_name: string | null;
    leads: number; pix_generated: number; sales: number; revenue: number; conversion: number; pix_conversion: number;
  }[];
  funnels: { id: string; name: string; owner: string; shared: boolean; sales: number; revenue: number; operations: number }[];
  loops: { id: string; name: string; owner: string; status: string; accounts: number; posts: number; shared: boolean; from_template: boolean }[];
};

const hierarchy: Record<string, string> = { chief: "Chefe", partner: "Sócio", independent: "Independente" };

function Table({ title, head, rows }: { title: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <section className="glass-panel space-y-2 p-4">
      <h3 className="text-sm font-semibold text-fg">{title} ({rows.length})</h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-xs">
          <thead className="text-muted">
            <tr className="border-b border-line-soft">
              {head.map((label, index) => (
                <th className={`px-2 py-2 font-medium ${index ? "text-right" : ""}`} key={label}>{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr className="border-b border-line-soft last:border-0" key={i}>
                {row.map((cell, index) => (
                  <td className={`px-2 py-2 ${index ? "text-right text-fg-2" : "text-fg"}`} key={index}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PlatformFeeCard() {
  const fee = useQuery({ queryKey: ["admin", "platform-fee"], queryFn: () => apiRequest<{ type: "percent" | "fixed"; value: number }>("/api/admin/platform-fee") });
  const [type, setType] = useState<"percent" | "fixed">("percent");
  const [value, setValue] = useState("0");
  useEffect(() => {
    if (fee.data) {
      setType(fee.data.type);
      setValue(String(fee.data.value).replace(".", ","));
    }
  }, [fee.data]);
  const save = useMutation({
    mutationFn: () => apiRequest("/api/admin/platform-fee", { method: "PUT", body: { type, value: value.replace(",", ".") || "0" } }),
    onSuccess: () => void fee.refetch(),
  });
  return (
    <section className="glass-panel space-y-2 p-4">
      <h3 className="text-sm font-semibold text-fg">Taxa da plataforma (vendas de sócios em funis próprios)</h3>
      <p className="text-xs text-muted">
        Vendas por funil compartilhado pagam só a comissão do chefe. Vendas de sócios por funil próprio pagam só esta taxa, enviada para a
        carteira principal pelo split da SmokePay. Vale para as próximas cobranças.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <select className="field !min-h-10 !w-auto" onChange={(event) => setType(event.target.value as "percent" | "fixed")} value={type}>
          <option value="percent">% do líquido</option>
          <option value="fixed">R$ fixo por venda</option>
        </select>
        <input className="field !min-h-10 !w-28" inputMode="decimal" onChange={(event) => setValue(event.target.value)} value={value} />
        <button className="btn-primary !min-h-10" disabled={save.isPending} onClick={() => save.mutate()} type="button">
          {save.isPending ? "Salvando…" : save.isSuccess ? "Salvo ✓" : "Salvar"}
        </button>
      </div>
    </section>
  );
}

export function AdminOperationsPage() {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const query = useQuery({
    queryKey: ["admin", "operations", periodParams(period)],
    queryFn: () => apiRequest<Data>(`/api/admin/operations?${new URLSearchParams(periodParams(period))}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
  });
  const data = query.data;
  return (
    <div className="space-y-4">
      <header className="space-y-3">
        <div>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Operações</h2>
        </div>
        <PeriodFilter onChange={setPeriod} value={period} />
      </header>
      <PlatformFeeCard />
      {query.isLoading && <LoadingState label="Carregando operações" />}
      {query.error && <ErrorState message="Não foi possível carregar." onRetry={() => void query.refetch()} />}
      {data && (
        <>
          <Table
            head={["Usuário", "Tipo", "Comissão", "Faturamento", "Taxas", "Comissão paga", "Comissão recebida"]}
            rows={data.users.map((u) => [
              `${u.name} · ${u.email}`, `${hierarchy[u.hierarchy] ?? u.hierarchy}${u.chief ? ` de ${u.chief}` : ""}`,
              u.commission_percent === null ? "—" : `${u.commission_percent}%`, brl(u.revenue), brl(u.fees), brl(u.commission_paid), brl(u.commission_received),
            ])}
            title="Faturamento e comissões por usuário"
          />
          <Table
            head={["Funil (modelo original)", "Dono", "Operações usando", "Vendas", "Faturamento"]}
            rows={data.funnels.map((f) => [`${f.name}${f.shared ? " · compartilhado" : ""}`, f.owner, f.operations, f.sales, brl(f.revenue)])}
            title="Ranking de funis por faturamento"
          />
          <Table
            head={["Bot", "Dono", "Funil", "Leads", "Pix gerados", "Vendas", "Lead → venda", "Pix → venda", "Faturamento"]}
            rows={data.bots.map((b) => [
              `${b.name} · @${b.username} (${b.status})`, b.owner, b.flow_name ?? "—", b.leads, b.pix_generated, b.sales,
              `${b.conversion.toLocaleString("pt-BR")}%`, `${b.pix_conversion.toLocaleString("pt-BR")}%`, brl(b.revenue),
            ])}
            title="Comparação de bots"
          />
          <Table
            head={["Loop", "Dono", "Status", "Contas", "Posts no período", "Origem"]}
            rows={data.loops.map((l) => [
              l.name, l.owner, l.status === "active" ? "ativo" : "pausado", l.accounts, l.posts,
              l.from_template ? "cópia de modelo" : l.shared ? "modelo compartilhado" : "próprio",
            ])}
            title="Loops"
          />
          <p className="text-[11px] text-muted">Período: {data.period_label}.</p>
        </>
      )}
    </div>
  );
}
