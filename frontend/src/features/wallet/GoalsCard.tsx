import { Link } from "react-router-dom";
import { Trophy } from "lucide-react";

import { AwardsCarousel } from "@/features/wallet/AwardsCarousel";
import { brl, compact, useGoals } from "@/features/wallet/api";

/** Revenue goals with award photos, for the main dashboard. */
export function GoalsCard() {
  const goals = useGoals();
  const data = goals.data;
  if (!data || !data.available) return null;
  return (
    <section className="dashboard-card space-y-3 rounded-xl p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">Premiações</p>
          <h2 className="mt-1 flex items-center gap-2 text-base font-semibold text-fg"><Trophy className="text-warning" size={17} /> Metas de faturamento</h2>
        </div>
        <Link className="text-xs font-semibold text-accent" to="/carteira">Ver carteira</Link>
      </div>
      <p className="text-xs text-muted">
        Este mês: <span className="font-semibold text-fg">{brl(data.month_revenue)}</span> · próxima meta {compact(data.target)} ({data.percent.toLocaleString("pt-BR")}%) · prêmio: {data.prize}
      </p>
      <div className="h-2 overflow-hidden rounded-full bg-well">
        <div className="h-full rounded-full bg-success transition-[width] duration-700" style={{ width: `${Math.min(100, data.percent)}%` }} />
      </div>
      <AwardsCarousel goals={data.goals} revenue={data.month_revenue} />
    </section>
  );
}
