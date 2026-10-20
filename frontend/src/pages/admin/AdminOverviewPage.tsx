import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  Blocks,
  CircleDollarSign,
  ShieldCheck,
  ShoppingBag,
  UserCheck,
  Users,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type AdminSummary } from "@/services/api";

export function AdminOverviewPage() {
  const summary = useQuery({
    queryKey: ["admin", "summary"],
    queryFn: () => apiRequest<AdminSummary>("/api/admin/summary"),
  });

  if (summary.isLoading) return <LoadingState label="Carregando indicadores" />;
  if (summary.error || !summary.data) {
    return <ErrorState message="Não foi possível carregar os dados administrativos." />;
  }

  const brl = (value: string | number) => Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const cards: { label: string; value: string | number; icon: typeof Users; hint?: string }[] = [
    {
      label: "Vendas FlashBot hoje",
      value: summary.data.flashbot_sales_today,
      icon: ShoppingBag,
      hint: `${brl(summary.data.flashbot_revenue_today)} vendidos por todas as operações`,
    },
    {
      label: "Taxa por transação hoje",
      value: brl(summary.data.transaction_fees_today),
      icon: CircleDollarSign,
      hint: `Arrecadado com a taxa FlashBot (padrão ${brl(summary.data.transaction_fee_default)} por venda)`,
    },
    { label: "Usuários totais", value: summary.data.users_total, icon: Users },
    { label: "Workspaces", value: summary.data.workspaces_total, icon: Blocks },
    { label: "Owners", value: summary.data.owners, icon: ShieldCheck },
    { label: "Collaborators", value: summary.data.collaborators, icon: UserCheck },
    { label: "Usuários ativos", value: summary.data.active_users, icon: Activity },
  ];

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">
          Plataforma
        </p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
          Visão geral
        </h2>
        <p className="mt-2 text-sm text-muted">
          Vendas do FlashBot no dia e indicadores de usuários e workspaces.
        </p>
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map(({ label, value, icon: Icon, hint }) => (
          <article
            key={label}
            className="rounded-xl border border-line-soft bg-surface p-4"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-[0.12em] text-muted">
                {label}
              </span>
              <Icon size={17} className="text-accent" strokeWidth={1.8} />
            </div>
            <p className="mt-5 text-3xl font-semibold tracking-[-0.05em] text-fg">
              {value}
            </p>
            {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
          </article>
        ))}
      </section>
    </div>
  );
}
