import { useQuery } from "@tanstack/react-query";
import { Flame, Trophy } from "lucide-react";

import { apiRequest } from "@/services/api";

type Engagement = {
  today: number;
  goal: number;
  streak: number;
  streak_before_today: number;
  met_today: boolean;
  missing_today: number;
  best_previous: number;
  best_previous_date: string | null;
  is_record_today: boolean;
};

function shortDate(value: string | null) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}/${month}${year === String(new Date().getFullYear()) ? "" : `/${year}`}`;
}

/** Two metric cards (streak + personal record) for the dashboard grids. */
export function EngagementCards() {
  const query = useQuery({
    queryKey: ["notifications", "engagement", "me"],
    queryFn: () => apiRequest<Engagement>("/api/notifications/engagement/me"),
    refetchInterval: 120_000,
    retry: false,
  });
  const data = query.data;
  if (!data) return null;
  const streakHint = data.met_today
    ? "meta de hoje batida ✅"
    : data.streak_before_today > 0
      ? `faltam ${data.missing_today} hoje pra manter`
      : data.goal > 0
        ? `bata a meta diária (${data.goal}) pra começar`
        : "conecte hoje pra começar";
  const best = Math.max(data.best_previous, data.today);
  return (
    <>
      <article className="dashboard-card dashboard-metric-card">
        <div className="dashboard-metric-heading">
          <span className="dashboard-metric-icon text-warning">
            <Flame size={16} />
          </span>
          <h2 className="dashboard-metric-title">Sequência</h2>
        </div>
        <div>
          <p className="dashboard-metric-value">
            {data.streak > 0 ? "🔥 " : ""}
            {data.streak} {data.streak === 1 ? "dia" : "dias"}
          </p>
          <p className="text-[10px] text-muted sm:text-[11px]">{streakHint}</p>
        </div>
      </article>
      <article className="dashboard-card dashboard-metric-card">
        <div className="dashboard-metric-heading">
          <span className="dashboard-metric-icon text-accent">
            <Trophy size={16} />
          </span>
          <h2 className="dashboard-metric-title">Recorde pessoal</h2>
        </div>
        <div>
          <p className="dashboard-metric-value">{best}</p>
          <p className="text-[10px] text-muted sm:text-[11px]">
            {data.is_record_today
              ? "🏆 novo recorde hoje!"
              : best > 0
                ? `conexões em um dia${data.best_previous_date ? ` · ${shortDate(data.best_previous_date)}` : ""}`
                : "seu melhor dia aparece aqui"}
          </p>
        </div>
      </article>
    </>
  );
}
