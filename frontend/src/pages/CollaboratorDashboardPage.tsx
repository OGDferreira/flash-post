import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CalendarCheck2,
  CircleDollarSign,
  Flame,
  Medal,
  Target,
  TrendingUp,
  UsersRound,
  type LucideIcon,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest, type CollaboratorDashboard } from "@/services/api";

function money(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "R$ —";
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

function progressValue(value: number | undefined) {
  return Math.min(100, Math.max(0, Number(value) || 0));
}

function brazilDayLabel(dayOffset: number) {
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const [year, month, day] = today.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day - dayOffset));
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

export function CollaboratorDashboardPage() {
  const dashboard = useQuery({
    queryKey: ["collaborators", "dashboard"],
    queryFn: () => apiRequest<CollaboratorDashboard>("/api/collaborators/dashboard"),
    refetchInterval: 30_000,
    retry: false,
  });
  const ranking = useQuery({
    queryKey: ["collaborators", "ranking"],
    queryFn: () =>
      apiRequest<{
        collaborators: {
          user_id: string;
          nickname: string;
          connections: number;
          position: number;
        }[];
        total_connections: number;
      }>("/api/collaborators/ranking"),
    refetchInterval: 60_000,
    retry: false,
  });

  if (dashboard.isLoading) return <LoadingState label="Carregando seu painel" />;
  if (dashboard.error || !dashboard.data) {
    return <ErrorState message="Não foi possível carregar seu painel de produção." />;
  }

  const data = dashboard.data;
  const recentDays = Array.isArray(data.recent_days)
    ? data.recent_days.map((count) => Number(count) || 0)
    : [];
  const ratePerConnection = Number(data.rate_per_connection) || 0;
  const recentEarnings = Array.isArray(data.recent_earnings)
    ? data.recent_earnings.map((amount) => Number(amount) || 0)
    : recentDays.map((count) => count * ratePerConnection);
  const recentPayments = Array.isArray(data.recent_payments)
    ? data.recent_payments.map((amount) => Number(amount) || 0)
    : recentDays.map(() => 0);
  const weeklyConnections = recentDays.reduce((total, count) => total + count, 0);
  const rankedCollaborators = Array.isArray(ranking.data?.collaborators)
    ? ranking.data.collaborators
    : [];
  const totalRankedConnections =
    Number(ranking.data?.total_connections) ||
    rankedCollaborators.reduce((total, person) => total + (Number(person.connections) || 0), 0);
  const productionByDay = recentDays.map((connections, dayOffset) => ({
    day: brazilDayLabel(6 - dayOffset),
    connections,
  }));
  const moneyByDay = recentDays.map((_, dayOffset) => ({
    day: brazilDayLabel(6 - dayOffset),
    aReceber: Number(recentEarnings[dayOffset] ?? 0),
    recebido: Number(recentPayments[dayOffset] ?? 0),
  }));

  return (
    <div className="w-full space-y-6">
      <header className="flex items-center gap-4">
        {data.avatar_url ? (
          <img
            alt=""
            className="size-14 rounded-full border border-[#34446f] object-cover"
            src={data.avatar_url}
          />
        ) : (
          <span className="grid size-14 place-items-center rounded-full bg-[#171e31] text-lg font-semibold text-[#aab7ff]">
            {(data.full_name || data.nickname || "C").slice(0, 1).toUpperCase()}
          </span>
        )}
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Seu painel de produção
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-[#f5f7fb]">
            Olá, {data.nickname || data.full_name || "colaborador"}
          </h1>
        </div>
      </header>

      <section aria-label="Resumo de produção e pagamentos" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric icon={UsersRound} label="Conexões hoje" value={String(data.connections_today ?? 0)} />
        <Metric icon={CalendarCheck2} label="Conexões na semana" value={String(weeklyConnections)} />
        <Metric icon={BarChart3} label="Conexões no mês" value={String(data.connections_month ?? 0)} />
        <Metric icon={CircleDollarSign} label="A receber hoje" value={money(data.earnings_today)} />
        <Metric icon={TrendingUp} label="Valor gerado no mês" value={money(data.earnings_month)} />
        <Metric icon={CircleDollarSign} label="Recebido no mês" value={money(data.paid_month)} />
        <Metric icon={CircleDollarSign} label="Total recebido" value={money(data.paid_total)} />
        <Metric icon={Flame} label="Saldo a receber" value={money(data.due_month)} />
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <article className="dashboard-card space-y-4 rounded-xl p-5">
          <div className="flex items-center gap-2">
            <Target className="text-[#8295ff]" size={18} />
            <h2 className="text-sm font-semibold text-[#eef1f8]">Meta diária</h2>
          </div>
          <div className="flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold text-[#f5f7fb]">
              {data.connections_today ?? 0}
              <span className="text-base font-normal text-[#78839b]">
                {" "}/ {data.daily_connection_goal || "—"}
              </span>
            </p>
            <p className="text-lg font-semibold text-[#aab7ff]">{progressValue(data.daily_progress)}%</p>
          </div>
          <ProgressBar value={progressValue(data.daily_progress)} />
          <p className="text-xs text-[#94a3b8]">
            {progressMessage(progressValue(data.daily_progress), data.daily_connection_goal)}
          </p>
        </article>

        <article className="dashboard-card space-y-4 rounded-xl p-5">
          <div className="flex items-center gap-2">
            <Flame className="text-[#f2d48a]" size={18} />
            <h2 className="text-sm font-semibold text-[#eef1f8]">Meta mensal</h2>
          </div>
          <div className="flex items-end justify-between gap-3">
            <p className="text-3xl font-semibold text-[#f5f7fb]">
              {data.connections_month ?? 0}
              <span className="text-base font-normal text-[#78839b]">
                {" "}/ {data.monthly_connection_goal || "—"}
              </span>
            </p>
            <p className="text-lg font-semibold text-[#f2d48a]">{progressValue(data.monthly_progress)}%</p>
          </div>
          <ProgressBar value={progressValue(data.monthly_progress)} color="gold" />
          <div className="flex flex-wrap justify-between gap-2 text-xs text-[#94a3b8]">
            <span>Devido: {money(data.due_month)}</span>
            <span>Bónus da meta: {money(data.monthly_bonus)}</span>
          </div>
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <article className="dashboard-card dashboard-chart-panel rounded-xl">
          <header className="dashboard-panel-header">
            <div>
              <p className="dashboard-eyebrow">Produção</p>
              <h2 className="dashboard-panel-title">Contas conectadas por dia</h2>
            </div>
            <span className="text-xs text-[#78839b]">Últimos 7 dias</span>
          </header>
          <div className="mt-5 h-64 w-full">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={productionByDay}>
                <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="#78839b" tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} stroke="#78839b" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    background: "#10141b",
                    border: "1px solid #303954",
                    borderRadius: 8,
                    color: "#f5f7fb",
                  }}
                />
                <Bar dataKey="connections" fill="#8295ff" name="Contas conectadas" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-[#78839b]">
            Valor por primeira conexão: {money(ratePerConnection)}
          </p>
        </article>

        <article className="dashboard-card dashboard-chart-panel rounded-xl">
          <header className="dashboard-panel-header">
            <div>
              <p className="dashboard-eyebrow">Financeiro</p>
              <h2 className="dashboard-panel-title">A receber e pagamentos por dia</h2>
            </div>
            <span className="text-xs text-[#78839b]">Últimos 7 dias</span>
          </header>
          <div className="mt-5 h-64 w-full">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={moneyByDay}>
                <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" stroke="#78839b" tick={{ fontSize: 11 }} />
                <YAxis
                  stroke="#78839b"
                  tick={{ fontSize: 10 }}
                  tickFormatter={(value: number) => `R$${value}`}
                />
                <Tooltip
                  formatter={(value) => [money(Number(value)), ""]}
                  contentStyle={{
                    background: "#10141b",
                    border: "1px solid #303954",
                    borderRadius: 8,
                    color: "#f5f7fb",
                  }}
                />
                <Legend />
                <Bar dataKey="aReceber" fill="#8295ff" name="A receber" radius={[4, 4, 0, 0]} />
                <Bar dataKey="recebido" fill="#76c8a0" name="Recebido" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </article>
      </section>

      <section aria-label="Ranking mensal de produção" className="dashboard-card space-y-4 rounded-xl p-5">
        <header className="flex items-center gap-2">
          <Medal className="text-[#f2d48a]" size={18} />
          <div>
            <p className="dashboard-eyebrow">Equipe</p>
            <h2 className="dashboard-panel-title">Ranking de contas conectadas no mês</h2>
          </div>
        </header>
        {ranking.isLoading ? (
          <p className="text-sm text-[#94a3b8]">Carregando ranking...</p>
        ) : ranking.error ? (
          <p className="text-sm text-[#f1a3ad]">Não foi possível carregar o ranking.</p>
        ) : rankedCollaborators.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[360px] text-left text-sm">
              <thead className="text-xs uppercase text-[#78839b]">
                <tr>
                  <th className="py-2 pr-3 font-medium">Posição</th>
                  <th className="py-2 pr-3 font-medium">Colaborador</th>
                  <th className="py-2 text-right font-medium">Conexões</th>
                </tr>
              </thead>
              <tbody>
                {rankedCollaborators.map((person) => (
                  <tr className="border-t border-[#202838]" key={person.user_id}>
                    <td className="py-3 pr-3 font-semibold text-[#f2d48a]">#{person.position}</td>
                    <td className="py-3 pr-3 text-[#e6eaf2]">@{person.nickname}</td>
                    <td className="py-3 text-right font-semibold text-[#f5f7fb]">
                      {person.connections}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-[#34446f] text-[#cbd5e1]">
                  <th className="py-3 pr-3" colSpan={2}>Total da equipe</th>
                  <td className="py-3 text-right font-semibold">
                    {totalRankedConnections}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <p className="text-sm text-[#94a3b8]">Ainda não há produção registrada neste mês.</p>
        )}
      </section>
    </div>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
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
