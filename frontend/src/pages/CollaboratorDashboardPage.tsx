import { useQuery } from "@tanstack/react-query";
import {
  CalendarCheck2,
  CircleDollarSign,
  Flame,
  Target,
  TrendingUp,
  UsersRound,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type CollaboratorDashboard } from "@/services/api";

function money(value: number) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function progressMessage(progress: number, goal: number) {
  if (!goal) return "Peça ao administrador para definir sua meta diária.";
  if (progress >= 100) return "Meta diária concluída! Excelente trabalho.";
  if (progress >= 70) return "Está quase lá — mantenha o ritmo!";
  if (progress >= 35) return "Bom progresso. Continue avançando!";
  return "Cada conexão conta. Vamos começar!";
}

export function CollaboratorDashboardPage() {
  const dashboard = useQuery({
    queryKey: ["collaborators", "dashboard"],
    queryFn: () => apiRequest<CollaboratorDashboard>("/api/collaborators/dashboard"),
    refetchInterval: 30_000,
    retry: false,
  });

  if (dashboard.isLoading) return <LoadingState label="Carregando seu painel" />;
  if (dashboard.error || !dashboard.data) {
    return <ErrorState message="Não foi possível carregar seu painel de produção." />;
  }

  const data = dashboard.data;
  const maxCount = Math.max(1, ...data.recent_days);

  return (
    <div className="mx-auto max-w-[1160px] space-y-6">
      <header className="flex items-center gap-4">
        {data.avatar_url ? (
          <img
            alt=""
            className="size-14 rounded-full border border-[#34446f] object-cover"
            src={data.avatar_url}
          />
        ) : (
          <span className="grid size-14 place-items-center rounded-full bg-[#171e31] text-lg font-semibold text-[#aab7ff]">
            {data.full_name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Seu painel de produção
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-[#f5f7fb]">
            Olá, {data.nickname}
          </h1>
        </div>
      </header>

      <section aria-label="Resumo de produção" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={UsersRound} label="Conexões hoje" value={String(data.connections_today)} />
        <Metric icon={CircleDollarSign} label="Ganho de hoje" value={money(data.earnings_today)} />
        <Metric icon={CalendarCheck2} label="Recebido no mês" value={money(data.paid_month)} />
        <Metric icon={TrendingUp} label="Projeção ao cumprir meta" value={money(data.projected_month)} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="dashboard-card space-y-4 rounded-xl p-5">
          <div className="flex items-center gap-2">
            <Target className="text-[#8295ff]" size={18} />
            <h2 className="text-sm font-semibold text-[#eef1f8]">Meta diária</h2>
          </div>
          <div className="flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold text-[#f5f7fb]">
              {data.connections_today}
              <span className="text-base font-normal text-[#78839b]">
                {" "}/ {data.daily_connection_goal || "—"}
              </span>
            </p>
            <p className="text-lg font-semibold text-[#aab7ff]">{data.daily_progress}%</p>
          </div>
          <ProgressBar value={data.daily_progress} />
          <p className="text-xs text-[#94a3b8]">
            {progressMessage(data.daily_progress, data.daily_connection_goal)}
          </p>
        </article>

        <article className="dashboard-card space-y-4 rounded-xl p-5">
          <div className="flex items-center gap-2">
            <Flame className="text-[#f2d48a]" size={18} />
            <h2 className="text-sm font-semibold text-[#eef1f8]">Meta mensal</h2>
          </div>
          <div className="flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold text-[#f5f7fb]">
              {data.connections_month}
              <span className="text-base font-normal text-[#78839b]">
                {" "}/ {data.monthly_connection_goal || "—"}
              </span>
            </p>
            <p className="text-lg font-semibold text-[#f2d48a]">{data.monthly_progress}%</p>
          </div>
          <ProgressBar value={data.monthly_progress} color="gold" />
          <div className="flex flex-wrap justify-between gap-2 text-xs text-[#94a3b8]">
            <span>Devido: {money(data.due_month)}</span>
            <span>Bónus da meta: {money(data.monthly_bonus)}</span>
          </div>
        </article>
      </section>

      <article className="dashboard-card rounded-xl p-5">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <p className="dashboard-eyebrow">Histórico</p>
            <h2 className="dashboard-panel-title">Conexões nos últimos 7 dias</h2>
          </div>
          <p className="text-xs text-[#78839b]">R$ {data.rate_per_connection.toFixed(2)} por primeira conexão</p>
        </div>
        <div className="flex h-40 items-end gap-3">
          {data.recent_days.map((count, index) => (
            <div className="flex h-full flex-1 flex-col items-center justify-end gap-2" key={index}>
              <span className="text-xs text-[#9aa4ba]">{count}</span>
              <div
                className="w-full max-w-14 rounded-t-md bg-gradient-to-t from-[#536dfe] to-[#b171ff]"
                style={{ height: `${Math.max(4, (count / maxCount) * 100)}px` }}
              />
              <span className="text-[10px] text-[#78839b]">D-{6 - index}</span>
            </div>
          ))}
        </div>
      </article>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof UsersRound;
  label: string;
  value: string;
}) {
  return (
    <article className="dashboard-card rounded-xl p-4">
      <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
        <Icon className="text-[#8295ff]" size={15} />
        {label}
      </div>
      <p className="mt-3 text-xl font-semibold text-[#f5f7fb]">{value}</p>
    </article>
  );
}

function ProgressBar({ value, color = "blue" }: { value: number; color?: "blue" | "gold" }) {
  return (
    <div
      aria-label={`Progresso ${value}%`}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={value}
      className="h-2 overflow-hidden rounded-full bg-[#252c3e]"
      role="progressbar"
    >
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${
          color === "gold"
            ? "bg-gradient-to-r from-[#d69b44] to-[#f2d48a]"
            : "bg-gradient-to-r from-[#536dfe] to-[#b171ff]"
        }`}
        style={{ width: `${value}%` }}
      />
    </div>
  );
}
